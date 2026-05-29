#!/usr/bin/env python3
"""
Engine Tuner Pro v10.1 - Single File Edition
EngineFile parser included (ISI .eng/.ini and JSON formats).
"""
import os
import json
from collections import OrderedDict


class EngineFile:
    def __init__(self):
        self.filepath = ""
        self.filename = ""
        self.torque_data = []
        self.file_structure = []
        self.was_json = False
        self.original_json_data = None
        self.json_format = None
        self.original_json_string = ""
        self.curve_data_is_string = False
        self.rev_limit = None
        self._json_bom = False
    
    def calculate_power_hp(self, rpm: float, torque_nm: float) -> float:
        if rpm == 0:
            return 0.0
        return (rpm * torque_nm * 0.737562) / 5252.0
    
    def load_file(self, filepath: str) -> bool:
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.torque_data = []
        self.file_structure = []
        self.was_json = False
        self.original_json_data = None
        self.json_format = None
        self.original_json_string = ""
        self.curve_data_is_string = False
        self.rev_limit = None
        ext = os.path.splitext(filepath)[1].lower()
        try:
            if ext == ".json":
                self.was_json = True
                return self._load_json(filepath)
            else:
                return self._load_eng_or_ini(filepath)
        except Exception as e:
            raise Exception(f"Error loading file: {e}")
    
    def _load_eng_or_ini(self, filepath):
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        for line in lines:
            stripped = line.strip()
            is_torque_line = False
            if stripped.upper().startswith('REVLIMITRANGE') and '=' in stripped:
                try:
                    inside = stripped[stripped.find('(')+1 : stripped.find(')')]
                    parts = [p.strip() for p in inside.split(',')]
                    if parts:
                        self.rev_limit = float(parts[0])
                except Exception:
                    pass
            if 'RPMTORQUE=' in stripped.upper() and not (
                    stripped.startswith('//') or stripped.startswith(';')):
                s = stripped.find('(')
                e = stripped.find(')')
                if s != -1 and e != -1:
                    parts = [p.strip() for p in
                             stripped[s+1:e].replace(',', ' ').split() if p.strip()]
                    if len(parts) >= 3:
                        try:
                            rpm = float(parts[0])
                            compression = float(parts[1])
                            torque_nm = float(parts[2])
                            power_hp = self.calculate_power_hp(rpm, torque_nm)
                            self.torque_data.append({
                                'rpm': rpm, 'compression': compression,
                                'torque_nm': torque_nm,
                                'torque_lbft': torque_nm * 0.737562,
                                'power_hp': power_hp,
                                'power_kw': power_hp * 0.7457
                            })
                            self.file_structure.append(None)
                            is_torque_line = True
                        except ValueError:
                            pass
            if not is_torque_line:
                self.file_structure.append(line)
        if self.torque_data:
            self.json_format = "ISI " + os.path.splitext(filepath)[1].lower()
        return bool(self.torque_data)
    
    def _load_json(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                raw = f.read()
        except Exception:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                raw = f.read()
        cleaned = "".join(c for c in raw if ord(c) in (0x09, 0x0A, 0x0D) or ord(c) >= 0x20)
        self.original_json_string = cleaned
        self._json_bom = raw.startswith('\ufeff')
        try:
            self.original_json_data = json.loads(
                cleaned, object_pairs_hook=OrderedDict, strict=False)
        except json.JSONDecodeError as e:
            raise Exception(f"JSON parse error at line {e.lineno}: {e.msg}")
        if isinstance(self.original_json_data, dict):
            curve = self._find_torque_curve(self.original_json_data)
            if curve and isinstance(curve, list) and len(curve) > 0:
                first = curve[0]
                self.json_format = 'nested' if isinstance(first, list) else 'flat'
                if self.json_format == 'nested':
                    self.curve_data_is_string = bool(first) and isinstance(first[0], str)
                    self._parse_nested(curve)
                else:
                    self.curve_data_is_string = isinstance(curve[0], str)
                    self._parse_flat(curve)
        return bool(self.torque_data)
    
    def _find_torque_curve(self, data):
        if isinstance(data, dict):
            if "torqueCurve" in data:
                return data["torqueCurve"]
            for v in data.values():
                r = self._find_torque_curve(v)
                if r:
                    return r
        elif isinstance(data, list):
            for item in data:
                r = self._find_torque_curve(item)
                if r:
                    return r
        return None
    
    def _parse_nested(self, data_list):
        for item in data_list:
            try:
                if isinstance(item, list) and len(item) >= 2:
                    rpm = float(str(item[0]).strip())
                    tnm = float(str(item[1]).strip())
                    if 0 <= rpm <= 30000 and abs(tnm) <= 10000:
                        hp = self.calculate_power_hp(rpm, tnm)
                        self.torque_data.append({
                            'rpm': rpm, 'compression': 0.0,
                            'torque_nm': tnm, 'torque_lbft': tnm * 0.737562,
                            'power_hp': hp, 'power_kw': hp * 0.7457
                        })
            except (ValueError, TypeError):
                continue
        self.torque_data.sort(key=lambda x: x['rpm'])
    
    def _parse_flat(self, data_list):
        if len(data_list) % 2 != 0:
            return
        for i in range(0, len(data_list), 2):
            try:
                rpm = float(data_list[i])
                tnm = float(data_list[i+1])
                if 0 <= rpm <= 30000 and abs(tnm) <= 10000:
                    hp = self.calculate_power_hp(rpm, tnm)
                    self.torque_data.append({
                        'rpm': rpm, 'compression': 0.0,
                        'torque_nm': tnm, 'torque_lbft': tnm * 0.737562,
                        'power_hp': hp, 'power_kw': hp * 0.7457
                    })
            except (ValueError, TypeError):
                continue
        self.torque_data.sort(key=lambda x: x['rpm'])
    
    def update_rpm(self, index: int, rpm: float):
        if 0 <= index < len(self.torque_data):
            p = self.torque_data[index]
            p['rpm'] = rpm
            p['power_hp'] = self.calculate_power_hp(rpm, p['torque_nm'])
            p['power_kw'] = p['power_hp'] * 0.7457
    
    def update_compression(self, index: int, compression: float):
        if 0 <= index < len(self.torque_data):
            self.torque_data[index]['compression'] = compression
    
    def update_torque(self, index: int, torque_nm: float):
        if 0 <= index < len(self.torque_data):
            p = self.torque_data[index]
            p['torque_nm'] = torque_nm
            p['torque_lbft'] = torque_nm * 0.737562
            p['power_hp'] = self.calculate_power_hp(p['rpm'], torque_nm)
            p['power_kw'] = p['power_hp'] * 0.7457
    
    def update_power(self, index: int, power_hp: float):
        if 0 <= index < len(self.torque_data):
            p = self.torque_data[index]
            p['power_hp'] = power_hp
            p['power_kw'] = power_hp * 0.7457
            torque_nm = (power_hp * 5252.0) / p['rpm'] / 0.737562 if p['rpm'] > 0 else 0
            p['torque_nm'] = torque_nm
            p['torque_lbft'] = torque_nm * 0.737562
    
    def scale_all_torque(self, factor: float):
        for i in range(len(self.torque_data)):
            self.update_torque(i, self.torque_data[i]['torque_nm'] * factor)
    
    def add_point(self, rpm: float, torque_nm: float, compression: float = 0.0):
        power_hp = self.calculate_power_hp(rpm, torque_nm)
        self.torque_data.append({
            'rpm': rpm, 'compression': compression,
            'torque_nm': torque_nm, 'torque_lbft': torque_nm * 0.737562,
            'power_hp': power_hp, 'power_kw': power_hp * 0.7457
        })
        self.torque_data.sort(key=lambda x: x['rpm'])
        if not self.was_json:
            self.file_structure.append(None)
    
    def delete_point(self, index: int):
        if 0 <= index < len(self.torque_data):
            self.torque_data.pop(index)
            if not self.was_json:
                for i in range(len(self.file_structure) - 1, -1, -1):
                    if self.file_structure[i] is None:
                        self.file_structure.pop(i)
                        break
    
    def save_file(self, filepath=None) -> bool:
        if not filepath:
            filepath = self.filepath
        ext = os.path.splitext(filepath)[1].lower()
        try:
            return (self._save_json_preserve(filepath)
                    if ext == ".json" else self._save_eng(filepath))
        except Exception as e:
            raise Exception(f"Error saving: {e}")
    
    def _save_eng(self, filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            if self.file_structure:
                ti = 0
                for item in self.file_structure:
                    if item is None:
                        if ti < len(self.torque_data):
                            p = self.torque_data[ti]
                            f.write(f"RPMTorque=(\t{p['rpm']:>6.0f}\t,\t"
                                    f"{p['compression']:>8.2f}\t,\t{p['torque_nm']:>8.2f}\t)\n")
                            ti += 1
                    else:
                        f.write(item)
            else:
                f.write("// Engine file created by Engine Tuner Pro v10\n")
                for p in self.torque_data:
                    f.write(f"RPMTorque=(\t{p['rpm']:>6.0f}\t,\t"
                            f"{p['compression']:>8.2f}\t,\t{p['torque_nm']:>8.2f}\t)\n")
        return True
    
    def _save_json_preserve(self, filepath):
        if not self.original_json_data or not self.original_json_string:
            return self._save_json_simple(filepath)
        
        def cn(v):
            return int(v) if isinstance(v, float) and v.is_integer() else v
        
        orig_curve = self._find_torque_curve(self.original_json_data)
        orig_decimals = 0
        if orig_curve and self.curve_data_is_string:
            for item in orig_curve[:5]:
                try:
                    s = str(item[1]).strip() if isinstance(item, list) else str(item)
                    if '.' in s:
                        orig_decimals = max(orig_decimals, len(s.split('.')[1]))
                except Exception:
                    pass
        
        def fmt_torque(v):
            if orig_decimals == 0:
                return str(int(round(v)))
            return str(round(v, orig_decimals))
        
        new_items = []
        for p in self.torque_data:
            r = cn(p['rpm'])
            if self.curve_data_is_string:
                r = str(int(r)) if isinstance(r, float) and r.is_integer() else str(r)
                t = fmt_torque(p['torque_nm'])
            else:
                t = cn(p['torque_nm'])
            new_items.append([r, t])
        
        text = self.original_json_string
        mi = text.find('"torqueCurve"')
        if mi == -1:
            return self._save_json_simple(filepath)
        
        sb = -1
        for i in range(mi + 13, len(text)):
            if text[i] == '[':
                sb = i
                break
        if sb == -1:
            return self._save_json_simple(filepath)
        
        bc, in_str, esc, eb = 0, False, False, -1
        for i in range(sb, len(text)):
            c = text[i]
            if esc:
                esc = False
                continue
            if c == '\\':
                esc = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if not in_str:
                if c == '[':
                    bc += 1
                elif c == ']':
                    bc -= 1
                    if bc == 0:
                        eb = i
                        break
        if eb == -1:
            return self._save_json_simple(filepath)
        
        orig = text[sb+1:eb]
        nl = '\r\n' if '\r\n' in orig else '\n'
        orig_lines = orig.split(nl)
        new_orig_lines = list(orig_lines)
        item_idx = 0
        for i, line in enumerate(orig_lines):
            stripped = line.strip()
            if stripped.startswith('[') and (stripped.endswith(']') or stripped.endswith('],')):
                if item_idx < len(new_items):
                    prefix = line[:len(line) - len(line.lstrip())]
                    comma = '' if item_idx == len(new_items) - 1 else ','
                    new_orig_lines[i] = prefix + json.dumps(
                        new_items[item_idx], separators=(',', ':'),
                        ensure_ascii=False) + comma
                    item_idx += 1
        
        out = text[:sb] + '[' + nl.join(new_orig_lines) + ']' + text[eb+1:]
        bom = '\ufeff' if self._json_bom else ''
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(bom + out)
        return True
    
    def _save_json_simple(self, filepath):
        def cn(v):
            return int(v) if isinstance(v, float) and v.is_integer() else v
        curve = []
        for p in self.torque_data:
            r, t = cn(p['rpm']), cn(p['torque_nm'])
            if self.curve_data_is_string:
                r, t = str(r), str(t)
            curve.append([r, t])
        out = OrderedDict([("name", "Modified by Engine Tuner Pro v10"),
                           ("torqueCurve", curve)])
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(out, f, indent="  ", separators=(',', ': '), ensure_ascii=False)
        return True

# ============================================================
# GUI
# ============================================================
import sys
import os
import copy
import math
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QFileDialog, QMessageBox, QDialog,
    QDialogButtonBox, QLineEdit, QInputDialog, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QShortcut, QKeySequence

import pyqtgraph as pg
import qtawesome as qta
import numpy as np

# Disable __pycache__ on desktop
sys.dont_write_bytecode = True


APP_NAME = "Engine Tuner Pro v10.1"


class EditDialog(QDialog):
    def __init__(self, parent, title, label, default_value):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(320)
        self.setStyleSheet("""
            QDialog { background: #0d1117; color: #e6edf3; }
            QLabel { color: #e6edf3; }
            QLineEdit { background: #161b22; border: 1px solid #30363d; border-radius: 4px;
                        color: #e6edf3; padding: 8px; font-family: Consolas; font-size: 14px; }
            QLineEdit:focus { border-color: #2f81f7; }
            QPushButton { background: #21262d; border: 1px solid #30363d; border-radius: 4px;
                         color: #e6edf3; padding: 6px 14px; }
            QPushButton:hover { background: #30363d; border-color: #2f81f7; }
        """)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(12)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet('color: #ff6b81; font-size: 14px; font-weight: 700;')
        v.addWidget(title_lbl)
        v.addWidget(QLabel(label))
        self.entry = QLineEdit(str(default_value))
        self.entry.selectAll()
        v.addWidget(self.entry)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)
        self.entry.setFocus()

    def get_value(self):
        try:
            return float(self.entry.text())
        except ValueError:
            return None


# ===== QSS THEME (constant - never reapplied) =====
THEME_QSS = """
QMainWindow, QWidget {
    background: #0d1117;
    color: #e6edf3;
    font-family: 'Segoe UI';
    font-size: 12px;
}
QPushButton {
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    color: #e6edf3;
    padding: 6px 10px;
    font-weight: 600;
    font-size: 11px;
}
QPushButton:hover {
    background: #2d333b;
    border-color: #2f81f7;
    color: #2f81f7;
}
QPushButton:disabled {
    background: #161b22;
    color: #484f58;
    border-color: #21262d;
}
QPushButton#primary {
    background: #2f81f7;
    color: #fff;
    border-color: #2f81f7;
}
QPushButton#primary:hover {
    background: #388bfd;
    border-color: #388bfd;
}
QPushButton#success {
    background: #238636;
    color: #fff;
    border-color: #2ea043;
}
QPushButton#success:hover {
    background: #2ea043;
}
QPushButton#engParams {
    color: #2f81f7;
    border-color: #2f81f7;
}
QPushButton#engParams:hover {
    background: #0d1b2e;
    border-color: #61afef;
    color: #61afef;
}
QPushButton#compareOff {
    color: #a8e6a3;
    border-color: #30363d;
}
QPushButton#compareOn {
    color: #ffd600;
    border-color: #ffd600;
    background: #2a2218;
}
QPushButton#compareOn:hover {
    background: #332a10;
    border-color: #ffd600;
    color: #ffe033;
}
QPushButton#unitActive {
    background: #2f81f7;
    color: #fff;
    border: 1px solid #2f81f7;
    font-weight: 700;
}
QPushButton#unitActive:hover {
    background: #388bfd;
    border-color: #388bfd;
    color: #fff;
}
QPushButton#unitActiveMetric {
    background: #238636;
    color: #fff;
    border: 1px solid #2ea043;
    font-weight: 700;
}
QPushButton#unitActiveMetric:hover {
    background: #2ea043;
    border-color: #2ea043;
    color: #fff;
}
QPushButton#unitInactive {
    background: #21262d;
    color: #7d8590;
    border: 1px solid #30363d;
}
QPushButton#unitInactive:hover {
    background: #2d333b;
    color: #a8e6a3;
    border-color: #30363d;
}
QLabel#brandTitle {
    color: #2f81f7;
    font-size: 20px;
    font-weight: 700;
}
QLabel#brandVersion {
    color: #2f81f7;
    font-size: 10px;
    font-weight: 700;
    background: #0d1f3a;
    padding: 4px 12px;
    border-radius: 4px;
    border: 1px solid #2f81f7;
}
QFrame#statsCell {
    background: #080e08;
    border: none;
    border-radius: 0px;
}
QLabel#cellLabel {
    color: #00aa55;
    font-size: 9px;
    font-weight: 700;
    background: transparent;
    border: none;
}
QLabel#cellValue {
    color: #00ff88;
    font-size: 13px;
    font-weight: 700;
    background: transparent;
    border: none;
    font-family: 'Consolas';
}
QLabel#cellSub {
    color: #007740;
    font-size: 9px;
    font-weight: 700;
    background: transparent;
    border: none;
}
QFrame#sectionFrame {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
}
QLabel#sectionTitle {
    color: #ff6b81;
    font-size: 13px;
    font-weight: 700;
    padding: 8px;
    background: transparent;
}
QTableWidget {
    background: #161b22;
    gridline-color: #30363d;
    border: none;
    color: #e6edf3;
    font-family: 'Consolas';
    font-size: 15px;
}
QTableWidget::item {
    padding: 8px 6px;
}
QTableWidget::item:selected {
    background: #2f81f7;
    color: #fff;
}
QHeaderView::section {
    background: #21262d;
    color: #7d8590;
    padding: 10px 8px;
    font-size: 13px;
    border: none;
    border-bottom: 2px solid #30363d;
    font-weight: 700;
}
QSplitter::handle {
    background: #30363d;
    width: 2px;
}
"""


class EngineTunerV10(QMainWindow):
    # Boje (konstante)
    COL_TQ = '#61afef'
    COL_PW = '#e06c75'
    COL_TQ_FILL = (97, 175, 239, 40)
    COL_PW_FILL = (224, 108, 117, 40)
    COL_PEAK_TQ = '#e5a550'
    COL_PEAK_PW = '#5bcc7a'
    COL_REDLINE = '#ff6b81'

    ENG_PARAMS = [
        ('RevLimitLogic',           'Rev Limit Logic',     'scalar', 0),
        ('RevLimitRange',           'Rev Limit Range',     'tuple3', 0),
        ('RevLimitSetting',         'Setting',             'int',    1),
        ('RevLimitAvailable',       'Limiter Available',   'int',    1),
        ('EngineMapRange',          'Engine Map Range',    'tuple3', 0),
        ('EngineMapSetting',        'Setting',             'int',    1),
        ('EngineBrakingMapRange',   'Brake Map Range',     'tuple3', 0),
        ('EngineBrakingMapSetting', 'Setting',             'int',    1),
        ('EngineSpeedHeat',         'Engine Speed Heat',   'scalar', 0),
        ('EngineInertia',           'Engine Inertia',      'scalar', 1),
        ('IdleRPMLogic',            'Idle RPM Logic',      'tuple2', 0),
        ('IdleThrottle',            'Idle Throttle',       'scalar', 1),
        ('OilWaterHeatTransfer',    'O-W Heat Transfer',   'tuple2', 0),
        ('OilMinimumCooling',       'Oil Min. Cooling',    'scalar', 1),
        ('OptimumOilTemp',          'Oil Optimum Temp',    'scalar', 0),
        ('CombustionHeat',          'Combustion Heat',     'scalar', 1),
        ('WaterMinimumCooling',     'Water Min. Cooling',  'scalar', 0),
        ('RadiatorCooling',         'Radiator Cooling',    'tuple2', 1),
        ('LifetimeEngineRPM',       'Lifetime Eng. RPM',   'tuple2', 0),
        ('LifetimeAvg',             'Lifetime AVG',        'int',    1),
        ('LifetimeOilTemp',         'Lifetime Oil Temp',   'tuple2', 0),
        ('LifetimeVar',             'Lifetime VAR',        'int',    1),
        ('EngineEmission',          'Engine Emission',     'tuple3', 0),
        ('EngineSound',             'Engine Sound',        'tuple3', 0),
        ('StarterTiming',           'Starter Timing',      'tuple3', 0),
        ('LaunchRPMLogic',          'Launch RPM Logic',    'tuple2', 0),
        ('LaunchEfficiency',        'Launch Efficiency',   'scalar', 1),
        ('SpeedLimiter',            'Speed Limiter',       'int',    0),
        ('OnboardStarter',          'Onboard Starter',     'int',    1),
        ('FuelConsumption',         'Fuel Consumption',    'scalar', 0),
        ('FuelEstimate',            'Fuel Estimate',       'scalar', 1),
        ('EngineBoostRange',        'Engine Boost Range',  'tuple3', 0),
        ('EngineBoostSetting',      'Setting',             'int',    1),
        ('BoostEffects',            'Boost Effects',       'tuple3', 0),
        ('BoostTorque',             'Boost Torque',        'scalar', 0),
        ('BoostPower',              'Boost Power',         'scalar', 1),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1450, 880)
        self.setAcceptDrops(True)

        self.engine = EngineFile()
        self.compare_engine = None
        self._anim_cmp_torque_curve = None
        self._anim_cmp_power_curve = None
        self._ref_line_tq = None
        self._ref_line_pw = None
        self._cmp_peak_tq_marker = None
        self._cmp_peak_pw_marker = None
        self._cmp_peak_tq_glow = None
        self._cmp_peak_pw_glow = None
        self._cmp_peak_tq_glow_outer = None
        self._cmp_peak_pw_glow_outer = None
        self._cmp_tq_label = None
        self._cmp_pw_label = None
        self._peak_tq_label = None
        self._peak_pw_label = None
        self.current_units = 'imperial'
        self._history = []
        self._hist_idx = -1
        self._ch_vline = None
        self._ch_label = None
        self._legend = None

        # Apply theme ONCE
        self.setStyleSheet(THEME_QSS)
        # Pulse animacija markera (sin wave)
        self._pulse_phase = 0.0
        self._smooth_mode = False
        # Numpy array cache — rebuilt on _refresh_all, reused elsewhere
        self._cache_rpms = None
        self._cache_torques = None
        self._cache_powers = None
        self._cache_units = None
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._update_pulse)
        self._pulse_timer.start(50)  # 20 FPS - dovoljno za smooth pulse

        self._build_ui()
        self._setup_shortcuts()
        self._load_demo_data()

        # Setup resize timer for maintaining splitter proportions
        self.resizeTimer = QTimer(self)
        self.resizeTimer.setSingleShot(True)
        self.resizeTimer.timeout.connect(self._restore_splitter_sizes)

    def resizeEvent(self, event):
        """Maintain splitter proportions when window is resized."""
        super().resizeEvent(event)
        self.resizeTimer.stop()
        self.resizeTimer.start(100)

    def _restore_splitter_sizes(self):
        """Restore splitter sizes after resize to maintain 60/40 ratio."""
        if hasattr(self, '_main_splitter') and self._main_splitter is not None:
            try:
                available = self._main_splitter.size().width()
                if available > 0:
                    chart_min = self._chart_section.minimumSizeHint().width()
                    table_min = self._table_section.minimumSizeHint().width()
                    min_total = chart_min + table_min + 10

                    if available >= min_total:
                        chart_w = int(available * 0.6)
                        table_w = available - chart_w
                    else:
                        ratio = chart_min / min_total
                        chart_w = max(int(available * ratio), chart_min)
                        table_w = available - chart_w

                    self._main_splitter.setSizes([max(chart_w, 500), max(table_w, 350)])
            except Exception:
                pass

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        v.addLayout(self._make_header())
        v.addLayout(self._make_toolbar())
        # stats bar je sada UNUTAR chart frame-a (iznad grafika)

        split = QSplitter(Qt.Orientation.Horizontal)
        # Store widget references to prevent recreation
        self._chart_section = self._make_chart_section()
        self._table_section = self._make_table_section()
        split.addWidget(self._chart_section)
        split.addWidget(self._table_section)
        # Proper 60/40 split - both can grow/shrink
        split.setStretchFactor(0, 6)
        split.setStretchFactor(1, 4)
        # Set initial sizes based on window width
        total_w = 1450 - 24  # margins
        split.setSizes([int(total_w * 0.6), int(total_w * 0.4)])
        split.setCollapsible(0, False)
        split.setCollapsible(1, False)
        # Store reference for resize handling
        self._main_splitter = split
        v.addWidget(split, stretch=1)

        # ── FOOTER BAR ──────────────────────────────────────────────────
        footer = QFrame()
        footer.setStyleSheet('background: #161b22; border-top: 1px solid #30363d;')
        fh = QHBoxLayout(footer)
        fh.setContentsMargins(8, 4, 12, 4)
        fh.setSpacing(0)

        self._dot_label = QLabel('●')
        self._dot_label.setStyleSheet(
            'color: #7d8590; font-size: 11px; padding-right: 6px; font-family: Consolas;')
        fh.addWidget(self._dot_label)

        self.status_label = QLabel('Ready  —  Open an .eng / .ini / .json file')
        self.status_label.setStyleSheet(
            'color: #7d8590; font-family: Consolas; font-size: 10px; padding: 2px 0;')
        fh.addWidget(self.status_label)

        fh.addStretch()

        self._footer_compare = QLabel('')
        self._footer_compare.setStyleSheet(
            'color: #ffd600; font-family: Consolas; font-size: 10px; padding: 2px 0;')
        self._footer_compare.hide()
        fh.addWidget(self._footer_compare)

        fh.addSpacing(18)

        self._footer_history = QLabel('')
        self._footer_history.setStyleSheet(
            'color: #5a5e72; font-family: Consolas; font-size: 10px; padding: 2px 0;')
        fh.addWidget(self._footer_history)

        v.addWidget(footer)



    def _make_header(self):
        h = QHBoxLayout()
        h.setSpacing(10)
        
        # Gear ikona - PLAVA (umjesto pink)
        gear_lbl = QLabel()
        gear_lbl.setPixmap(qta.icon('fa5s.cog', color='#2f81f7').pixmap(28, 28))
        h.addWidget(gear_lbl)
        
        # ENGINE TUNER PRO - PLAVO (umjesto crveno)
        title = QLabel('ENGINE TUNER PRO')
        title.setObjectName('brandTitle')
        title.setStyleSheet('color: #2f81f7; font-size: 20px; font-weight: 700;')
        h.addWidget(title)
        
        # Verzija - kompaktno "v1.0 ULTIMATE" sa plavim okvirom
        version = QLabel('v1.0  ULTIMATE')
        version.setObjectName('brandVersion')
        version.setStyleSheet(
            'color: #2f81f7; font-size: 10px; font-weight: 700; '
            'background: #0d1f3a; padding: 4px 12px; border-radius: 4px; '
            'border: 1px solid #2f81f7;'
        )
        h.addWidget(version)
        
        h.addSpacing(20)
        
        # File ikona
        file_icon = QLabel()
        file_icon.setPixmap(qta.icon('fa5s.file-alt', color='#7d8590').pixmap(14, 14))
        h.addWidget(file_icon)
        h.addWidget(QLabel('File:'))
        
        # Glavni fajl - zeleni
        self.file_label = QLabel('No file loaded')
        self.file_label.setStyleSheet('color: #3fb950; font-weight: 700; font-size: 13px;')
        h.addWidget(self.file_label)
        
        # Compare separator + label - zuti (sakriven dok nema compare)
        self.compare_separator = QLabel('  vs  ')
        self.compare_separator.setStyleSheet('color: #7d8590; font-weight: 700; font-size: 13px;')
        self.compare_separator.hide()
        h.addWidget(self.compare_separator)
        
        self.compare_file_label = QLabel('')
        self.compare_file_label.setStyleSheet('color: #ffd600; font-weight: 700; font-size: 13px;')
        self.compare_file_label.hide()
        h.addWidget(self.compare_file_label)
        
        h.addStretch()

        # GPU MODE — gore desno u headeru
        gpu_container = QWidget()
        gpu_container.setStyleSheet('background:#1a0810; border:1px solid #ff6b81; border-radius:4px;')
        gpu_layout = QHBoxLayout(gpu_container)
        gpu_layout.setContentsMargins(8, 4, 10, 4)
        gpu_layout.setSpacing(5)
        gpu_icon = QLabel()
        gpu_icon.setPixmap(qta.icon('fa5s.bolt', color='#ffa500').pixmap(11, 11))
        gpu_icon.setStyleSheet('background: transparent; border: none;')
        gpu_layout.addWidget(gpu_icon)
        mode_lbl = QLabel('GPU MODE')
        mode_lbl.setStyleSheet('color:#ff6b81; background:transparent; border:none; font-size:10px; font-weight:700;')
        gpu_layout.addWidget(mode_lbl)
        h.addWidget(gpu_container)

        # Toast — statican label u headeru desno od GPU MODE
        self._toast = QLabel('')
        self._toast.setStyleSheet(
            'color: #a8e6a3; font-family: Consolas; font-size: 10px; font-weight: 600; '
            'background: #0d1f18; padding: 4px 14px; border-radius: 4px; '
            'border: 1px solid #a8e6a344; margin-left: 8px;')
        self._toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._toast.setFixedHeight(28)
        self._toast.hide()
        h.addWidget(self._toast)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast.hide)

        return h
    def _make_toolbar(self):
        h = QHBoxLayout()
        h.setSpacing(3)

        BTN_H = 32

        def btn(text, icon_name, icon_color, obj_name='', callback=None, width=None):
            b = QPushButton(qta.icon(icon_name, color=icon_color), '  ' + text)
            if obj_name:
                b.setObjectName(obj_name)
            b.setFixedHeight(BTN_H)
            if width:
                b.setFixedWidth(width)
            if callback:
                b.clicked.connect(callback)
            return b

        # File ops - vece sirine da tekst stane
        h.addWidget(btn('Open File',   'fa5s.folder-open',  'white',    'primary',  self.open_file,        width=115))
        h.addWidget(btn('Save',        'fa5s.save',         'white',    'success',  self.save_file,        width=82))
        h.addWidget(btn('Save As',     'fa5s.copy',         '#7d8590',  '',         self.save_as,          width=92))
        h.addWidget(self._sep())
        # Edit ops
        h.addWidget(btn('Set Max HP',  'fa5s.bolt',         '#ffd600',  '',         self.set_max_hp,       width=110))
        h.addWidget(btn('Scale Curve', 'fa5s.chart-line',   '#61afef',  '',         self.scale_curve,      width=115))

        # Smooth toggle
        self.btn_smooth = QPushButton(qta.icon('fa5s.wave-square', color='#c9a84c'), '  Smooth')
        self.btn_smooth.setObjectName('smoothOff')
        self.btn_smooth.setFixedHeight(BTN_H)
        self.btn_smooth.setFixedWidth(105)
        self.btn_smooth.setCheckable(True)
        self.btn_smooth.clicked.connect(self._toggle_smooth)
        h.addWidget(self.btn_smooth)

        h.addWidget(self._sep())
        # Engine Params - plava
        self.btn_eng_params = btn('Engine Params', 'fa5s.sliders-h', '#2f81f7', 'engParams',
                                   self.edit_engine_params, width=130)
        h.addWidget(self.btn_eng_params)
        # Compare - zuta
        self.btn_compare = btn('Compare', 'fa5s.balance-scale', '#ffd600', 'compareOff',
                                self.compare_files, width=105)
        h.addWidget(self.btn_compare)
        # Refresh - plavi sync
        h.addWidget(btn('Refresh',     'fa5s.sync-alt',     '#61afef',  '',         self._refresh_with_anim,     width=98))
        h.addWidget(self._sep())
        # Undo/Redo
        h.addWidget(btn('Undo',        'fa5s.undo',         '#7d8590',  '',         self.undo,             width=82))
        h.addWidget(btn('Redo',        'fa5s.redo',         '#7d8590',  '',         self.redo,             width=82))
        h.addWidget(self._sep())
        # Export
        h.addWidget(btn('Export PNG',  'fa5s.image',        '#a8b8e8',  '',         self.export_png,       width=115))
        h.addWidget(btn('Copy CSV',    'fa5s.table',        '#a8b8e8',  '',         self.copy_csv,         width=105))
        h.addStretch()

        lbl = QLabel('UNITS:')
        lbl.setStyleSheet('color: #7d8590; font-weight: 700; font-size: 10px;')
        h.addWidget(lbl)

        self.btn_imperial = QPushButton('HP / LB-FT')
        self.btn_imperial.setObjectName('unitActive')
        self.btn_imperial.setFixedHeight(BTN_H)
        self.btn_imperial.setFixedWidth(105)
        self.btn_imperial.clicked.connect(lambda: self.set_units('imperial'))
        h.addWidget(self.btn_imperial)

        self.btn_metric = QPushButton('KW / NM')
        self.btn_metric.setObjectName('unitInactive')
        self.btn_metric.setFixedHeight(BTN_H)
        self.btn_metric.setFixedWidth(95)
        self.btn_metric.clicked.connect(lambda: self.set_units('metric'))
        h.addWidget(self.btn_metric)

        return h

    def _toggle_smooth(self):
        self._smooth_mode = self.btn_smooth.isChecked()
        if self._smooth_mode:
            self.btn_smooth.setObjectName('smoothOn')
            self.btn_smooth.setStyleSheet(
                'QPushButton { background: #2a2200; border: 1px solid #c9a84c; '
                'color: #ffd600; border-radius: 4px; font-weight: 700; }')
            self._show_toast('  Smooth curve: ON (cubic spline)', '#c9a84c')
        else:
            self.btn_smooth.setObjectName('smoothOff')
            self.btn_smooth.setStyleSheet('')
            self._show_toast('  Smooth curve: OFF', '#7d8590')
        if self.engine.torque_data:
            self._refresh_chart()

    def _sep(self):
        s = QFrame()
        s.setFrameShape(QFrame.Shape.VLine)
        s.setStyleSheet('color: #30363d; max-width: 1px;')
        return s

    def _make_stats_bar(self):
        h = QHBoxLayout()
        h.setSpacing(0)
        h.setContentsMargins(0, 0, 0, 0)
        self.stat_widgets = {}
        cells = [
            ('peak_tq',    'PEAK TORQUE',  'fa5s.balance-scale-right'),
            ('peak_pw',    'PEAK POWER',   'fa5s.bolt'),
            ('rpm_range',  'RPM RANGE',    'fa5s.tachometer-alt'),
            ('power_band', 'POWER BAND',   'fa5s.wave-square'),
            ('rev_limit',  'REV LIMIT',    'fa5s.exclamation-triangle'),
        ]
        for idx, (key, label, icon_name) in enumerate(cells):
            cell = QFrame()
            cell.setStyleSheet('background:transparent; border:none;')
            cell.setMinimumHeight(68)
            cell.setMaximumHeight(72)
            cv = QVBoxLayout(cell)
            cv.setContentsMargins(10, 4, 10, 4)
            cv.setSpacing(2)
            lr = QHBoxLayout()
            lr.setSpacing(4)
            ico = QLabel()
            ico.setPixmap(qta.icon(icon_name, color='#00aa55').pixmap(10, 10))
            lr.addWidget(ico)
            ll = QLabel(label)
            ll.setStyleSheet('color:#00aa55; font-size:10px; font-weight:700; background:transparent; border:none;')
            lr.addWidget(ll)
            lr.addStretch()
            cv.addLayout(lr)
            lv = QLabel('—')
            lv.setStyleSheet('color:#00ff88; font-size:15px; font-weight:700; font-family:Consolas; background:transparent; border:none;')
            cv.addWidget(lv)
            ls = QLabel('—')
            ls.setStyleSheet('color:#007740; font-size:10px; font-weight:700; background:transparent; border:none;')
            cv.addWidget(ls)
            h.addWidget(cell, stretch=1)
            self.stat_widgets[key] = (lv, ls)
        return h

    def _make_chart_section(self):
        frame = QFrame()
        frame.setObjectName('chartFrame')
        frame.setMinimumWidth(500)  # Prevent collapse when loading JSON
        frame.setMinimumHeight(400)  # Prevent vertical shrinking
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame.setStyleSheet(
            'QFrame#chartFrame {'
            '  background: #0d1117;'
            '  border: 1px solid #4a6fa5;'
            '  border-radius: 8px;'
            '}'
        )
        # Neon bijeli glow oko charta
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        from PyQt6.QtGui import QColor as _GC
        _glow = QGraphicsDropShadowEffect()
        _glow.setBlurRadius(22)
        _glow.setColor(_GC(180, 210, 255, 110))
        _glow.setOffset(0, 0)
        frame.setGraphicsEffect(_glow)
        v = QVBoxLayout(frame)
        v.setContentsMargins(12, 8, 12, 12)
        v.setSpacing(0)

        # STATS BAR — scanline, header red + celije sve u jednom bloku kao v9
        class _ScanFrame(QWidget):
            def paintEvent(self_, ev):
                from PyQt6.QtGui import QPainter, QColor, QPen, QFont
                from PyQt6.QtCore import Qt
                p = QPainter(self_)
                w, h = self_.width(), self_.height()
                # Pozadina
                p.fillRect(0, 0, w, h, QColor('#080e08'))
                # Scanlines
                p.setPen(QPen(QColor('#0a140a'), 1))
                for y in range(0, h, 3):
                    p.drawLine(0, y, w, y)
                # Gornji i donji border
                p.setPen(QPen(QColor('#1a5a2a'), 1))
                p.drawLine(0, 0, w, 0)
                p.drawLine(0, h-1, w, h-1)
                # Vertikalni separatori između 5 ćelija (ispod header reda)
                HDR = 20
                cw = w // 5
                for i in range(1, 5):
                    p.drawLine(i*cw, HDR, i*cw, h-2)
                p.end()
        _sw = _ScanFrame()
        _sw.setMinimumHeight(100)
        _sw.setMaximumHeight(110)
        _swl = QVBoxLayout(_sw)
        _swl.setContentsMargins(0, 0, 0, 0)
        _swl.setSpacing(0)
        # Header red unutar scan frame-a
        _hdr = QHBoxLayout()
        _hdr.setContentsMargins(8, 2, 8, 2)
        _hdr.setSpacing(6)
        _hico = QLabel()
        _hico.setPixmap(qta.icon('fa5s.chart-line', color='#ff6b81').pixmap(12, 12))
        _hico.setStyleSheet('background:transparent;')
        _hdr.addWidget(_hico)
        _htitle = QLabel('RPM CURVE')
        _htitle.setStyleSheet('color:#ff6b81; font-size:11px; font-weight:700; background:transparent;')
        _hdr.addWidget(_htitle)
        _hdr.addStretch()
        self._fps_lbl = QLabel('GPU -- FPS  |  pyqtgraph')
        self._fps_lbl.setStyleSheet('color:#7d8590; font-size:10px; background:transparent;')
        _hdr.addWidget(self._fps_lbl)
        _swl.addLayout(_hdr)
        _swl.addLayout(self._make_stats_bar())
        v.addWidget(_sw)

        pg.setConfigOption('background', '#0a0a12')
        pg.setConfigOption('foreground', '#7d8590')
        pg.setConfigOption('antialias', True)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#0a0a12')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', 'Torque (lb-ft)', color=self.COL_TQ, size='11pt')
        self.plot_widget.setLabel('bottom', '<b>Engine RPM</b>', color='#ff6b81', size='12pt')
        self.plot_widget.setLabel('right', 'Power (HP)', color=self.COL_PW, size='11pt')
        self.plot_widget.showAxis('right')

        # FIKSNE OSE - osiguraj da 1600 i 24000 budu uvijek vidljivi
        self.plot_widget.setXRange(0, 24000, padding=0.05)
        self.plot_widget.setYRange(0, 1600, padding=0.08)
        self.plot_widget.setLimits(xMin=-500, xMax=24500, yMin=-2, yMax=1680)
        # Eksplicitni ticks — 24000 i 1600 uvijek vidljivi
        _xticks = [(0, '0'), (4000, '4000'), (8000, '8000'), (12000, '12000'),
                   (16000, '16000'), (20000, '20000'), (24000, '24000')]
        _yticks = [(0, '0'), (200, '200'), (400, '400'), (600, '600'),
                   (800, '800'), (1000, '1000'), (1200, '1200'), (1400, '1400'), (1600, '1600')]
        self.plot_widget.getAxis('bottom').setTicks([_xticks])
        self.plot_widget.getAxis('left').setTicks([_yticks])
        self.plot_widget.getAxis('right').setTicks([_yticks])
        # Disable auto-range
        self.plot_widget.enableAutoRange(axis='x', enable=False)
        self.plot_widget.enableAutoRange(axis='y', enable=False)
        self.plot_widget.disableAutoRange()
        # Blokirati scroll/zoom mišem - ose su fiksne
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.getViewBox().setMouseEnabled(x=False, y=False)
        self.plot_widget.getViewBox().setBorder(pen=None)

        for axis_name in ['left', 'right', 'bottom', 'top']:
            ax = self.plot_widget.getAxis(axis_name)
            ax.setPen(pg.mkPen('#30363d', width=1))
            ax.setTextPen('#7d8590')

        # Left axis blue (torque), right axis green/red (power), bottom axis pink (RPM)
        self.plot_widget.getAxis('left').setTextPen(self.COL_TQ)
        self.plot_widget.getAxis('right').setTextPen(self.COL_PW)
        self.plot_widget.getAxis('bottom').setTextPen('#cc5566')

        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self.plot_widget.leaveEvent = lambda e: self._on_mouse_leave()

        # Live FPS counter — broji Paint evente na viewportu
        from PyQt6.QtCore import QObject as _QObj, QEvent as _QEv
        class _FpsFilter(_QObj):
            def __init__(self, cnt):
                super().__init__()
                self._cnt = cnt
            def eventFilter(self, obj, event):
                if event.type() == _QEv.Type.Paint:
                    self._cnt[0] += 1
                return False
        self._fps_cnt = [0]
        self._fps_filter = _FpsFilter(self._fps_cnt)
        self.plot_widget.viewport().installEventFilter(self._fps_filter)
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(1000)

        v.addWidget(self.plot_widget, stretch=1)

        # === LEGENDA ZONA (ispod charta, kao Arena) ===
        self._legend_bar = QWidget()
        self._legend_bar.setFixedHeight(28)
        self._legend_bar.setStyleSheet('background: #0a0a12;')
        _lb = QHBoxLayout(self._legend_bar)
        _lb.setContentsMargins(16, 0, 16, 4)
        _lb.setSpacing(18)
        _lb.addStretch()

        def _mk_leg(color, label):
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(5)
            dot = QLabel('━━')
            dot.setStyleSheet(f'color:{color}; font-size:10px; background:transparent;')
            lbl = QLabel(label)
            lbl.setStyleSheet(f'color:#7d8590; font-size:10px; background:transparent;')
            hl.addWidget(dot)
            hl.addWidget(lbl)
            return w

        self._leg_tq_w   = _mk_leg(self.COL_TQ,   'Torque')
        self._leg_pw_w   = _mk_leg(self.COL_PW,   'Power (HP)')
        self._leg_ctq_w  = _mk_leg('#ffd600',      'Cmp Torque')
        self._leg_cpw_w  = _mk_leg('#c084fc',      'Cmp Power')

        for w in (self._leg_tq_w, self._leg_pw_w, self._leg_ctq_w, self._leg_cpw_w):
            _lb.addWidget(w)
        _lb.addStretch()

        self._leg_ctq_w.hide()
        self._leg_cpw_w.hide()
        v.addWidget(self._legend_bar)

        return frame

    def _make_table_section(self):
        frame = QFrame()
        frame.setObjectName('sectionFrame')
        # Allow proper resize with splitter - no fixed width
        frame.setMinimumWidth(350)
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Vehicle info panel - v9 STYLE (name+brand row, specs row below)
        self.veh_frame = QFrame()
        self.veh_frame.setStyleSheet('''
            QFrame {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0e1c2e,stop:1 #080f18);
                border: none;
            }
            QLabel { background: transparent; border: none; }
        ''')
        # VERTICAL layout — top row (name+brand), bottom row (specs)
        veh_outer = QVBoxLayout(self.veh_frame)
        veh_outer.setContentsMargins(12, 5, 12, 5)
        veh_outer.setSpacing(2)

        # --- TOP ROW: car icon + name (left) ... brand (far right) ---
        veh_top = QHBoxLayout()
        veh_top.setContentsMargins(0, 0, 0, 0)
        veh_top.setSpacing(6)

        veh_car_icon = QLabel()
        veh_car_icon.setPixmap(qta.icon('fa5s.car', color='#61afef').pixmap(13, 13))
        veh_top.addWidget(veh_car_icon)

        self.veh_name_lbl = QLabel('')
        self.veh_name_lbl.setStyleSheet(
            'color: #e6edf3; font-weight: 700; font-size: 12px; background: transparent;'
        )
        veh_top.addWidget(self.veh_name_lbl)

        veh_top.addSpacing(20)

        self.veh_brand_lbl = QLabel('')
        self.veh_brand_lbl.setStyleSheet(
            'color: #7d8590; font-size: 10px; font-style: italic; background: transparent;'
        )
        veh_top.addWidget(self.veh_brand_lbl)
        veh_top.addStretch()
        veh_outer.addLayout(veh_top)

        # --- BOTTOM ROW: specs (full width) ---
        self.veh_specs_lbl = QLabel('')
        self.veh_specs_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.veh_specs_lbl.setStyleSheet(
            'color: #5aa8d8; font-family: Segoe UI; font-size: 10px; background: transparent;'
        )
        veh_outer.addWidget(self.veh_specs_lbl)

        self.veh_frame.setMinimumHeight(52)
        self.veh_frame.setMaximumHeight(56)
        self.veh_frame.hide()
        v.addWidget(self.veh_frame)

        # Clean table header — ONLY title, points count, and buttons
        hdr_widget = QWidget()
        hdr_widget.setStyleSheet('QWidget { background: #1a1f2e; }')
        tr = QHBoxLayout(hdr_widget)
        tr.setContentsMargins(8, 6, 8, 6)
        tr.setSpacing(6)
        ico = QLabel()
        ico.setPixmap(qta.icon('fa5s.table', color='#3fb950').pixmap(14, 14))
        ico.setStyleSheet('background: transparent;')
        tr.addWidget(ico)
        title = QLabel('TORQUE CURVE DATA')
        title.setStyleSheet(
            'color: #3fb950; font-size: 13px; font-weight: 700; background: transparent;'
        )
        tr.addWidget(title)
        tr.addStretch()
        self.points_label = QLabel('0 pts')
        self.points_label.setStyleSheet(
            'color:#7d8590; font-size:10px; background:#21262d; padding:4px 8px; border-radius:4px;'
        )
        tr.addWidget(self.points_label)
        ba = QPushButton(qta.icon('fa5s.plus', color='#3fb950'), ' Add')
        ba.setFixedHeight(26)
        ba.setFixedWidth(70)
        ba.setStyleSheet(
            'QPushButton { color: #3fb950; background: #0d2218; border: 1px solid #238636;'
            ' border-radius: 5px; font-size: 11px; font-weight: 600; padding: 0 6px; }'
            'QPushButton:hover { background: #1a3d28; border-color: #3fb950; color: #4ec760; }'
            'QPushButton:pressed { background: #0a1a10; }'
        )
        ba.clicked.connect(self.add_point)
        tr.addWidget(ba)
        bd = QPushButton(qta.icon('fa5s.trash-alt', color='#f85149'), ' Del')
        bd.setFixedHeight(26)
        bd.setFixedWidth(66)
        bd.setStyleSheet(
            'QPushButton { color: #f85149; background: #200d0d; border: 1px solid #6e1a1a;'
            ' border-radius: 5px; font-size: 11px; font-weight: 600; padding: 0 6px; }'
            'QPushButton:hover { background: #3a1010; border-color: #f85149; color: #ff6b6b; }'
            'QPushButton:pressed { background: #180808; }'
        )
        bd.clicked.connect(self.delete_point)
        tr.addWidget(bd)
        v.addWidget(hdr_widget)

        # Auto-focus on hover — fix za scroll bez klika
        class _AutoFocusTable(QTableWidget):
            def enterEvent(self, event):
                self.setFocus()
                super().enterEvent(event)
            def wheelEvent(self, event):
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() - event.angleDelta().y() // 8
                )
                event.accept()

        self.table = _AutoFocusTable()
        self.table.setColumnCount(6)

        # Custom QHeaderView subclass — only guaranteed way to color sections in Qt6
        from PyQt6.QtWidgets import QHeaderView as _QHV
        from PyQt6.QtGui import QColor as _QCol, QFont as _QFnt
        from PyQt6.QtCore import Qt as _QtH

        class _ColoredHeader(_QHV):
            def __init__(self, parent=None):
                super().__init__(_QtH.Orientation.Horizontal, parent)
                self._col_colors = ['#ffffff', '#ffffff', '#61afef', '#e06c75', '#c9a84c', '#a8e6a3']
                self.setDefaultSectionSize(38)

            def set_unit_colors(self, tq_col, pw_col):
                self._col_colors[2] = tq_col
                self._col_colors[3] = pw_col
                self.viewport().update()

            def paintSection(self, painter, rect, logicalIndex):
                painter.save()
                painter.fillRect(rect, _QCol('#1a1f2e'))
                # Bottom border
                painter.setPen(_QCol('#2a3050'))
                painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
                # Column divider (right edge, subtle)
                painter.setPen(_QCol('#252c3e'))
                painter.drawLine(rect.right(), rect.top() + 4, rect.right(), rect.bottom() - 4)
                # Text
                c = self._col_colors[logicalIndex] if logicalIndex < len(self._col_colors) else '#7d8590'
                painter.setPen(_QCol(c))
                f = _QFnt('Segoe UI', 10)
                f.setBold(True)
                painter.setFont(f)
                lbl = self.model().headerData(
                    logicalIndex, _QtH.Orientation.Horizontal,
                    _QtH.ItemDataRole.DisplayRole)
                painter.drawText(rect, _QtH.AlignmentFlag.AlignCenter, str(lbl) if lbl else '')
                painter.restore()

        self._colored_header = _ColoredHeader(self.table)
        self._colored_header.setStretchLastSection(True)
        self._colored_header.setSectionResizeMode(_QHV.ResizeMode.Stretch)
        self.table.setHorizontalHeader(self._colored_header)
        self.table.setHorizontalHeaderLabels(['RPM', 'Compr.', 'Torque', 'Power', '% Peak', 'Δ HP'])
        self.table.hideColumn(5)  # delta kolona sakrivena dok nema compare fajla
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        v.addWidget(self.table)
        return frame

    def _setup_shortcuts(self):
        QShortcut(QKeySequence('Ctrl+O'), self).activated.connect(self.open_file)
        QShortcut(QKeySequence('Ctrl+S'), self).activated.connect(self.save_file)
        QShortcut(QKeySequence('Ctrl+Shift+S'), self).activated.connect(self.save_as)
        QShortcut(QKeySequence('Ctrl+Z'), self).activated.connect(self.undo)
        QShortcut(QKeySequence('Ctrl+Y'), self).activated.connect(self.redo)
        QShortcut(QKeySequence('Ctrl+E'), self).activated.connect(self.export_png)

    # ===== DRAG & DROP =====
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith(('.eng', '.ini', '.json')):
                event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isfile(path):
                self._load_file(path)

    # ===== DEMO =====
    def _load_demo_data(self):
        SAMPLE = [
            (0, -42.20), (500, 0.95), (1000, 20.6), (1500, 46.7), (2000, 72.0),
            (2500, 94.9), (3000, 117.7), (3500, 139.5), (4000, 159.9), (4500, 180.1),
            (5000, 200.0), (5500, 216.7), (6000, 230.4), (6500, 242.6), (7000, 252.0),
            (7500, 261.0), (8000, 268.0), (8500, 278.0), (9000, 289.1), (9500, 301.0),
            (10000, 312.0), (10500, 322.0), (11000, 333.1), (11500, 345.1), (12000, 353.1),
            (12500, 359.3), (13000, 366.1), (13500, 373.0), (14000, 376.9), (14500, 379.8),
            (15000, 382.6), (15500, 384.7), (16000, 384.0), (16500, 379.8), (17000, 372.9),
            (17500, 363.4), (18000, 349.8), (18500, 332.2), (19000, 309.2)
        ]
        self.engine.torque_data = []
        for rpm, tnm in SAMPLE:
            hp = self.engine.calculate_power_hp(rpm, tnm)
            self.engine.torque_data.append({
                'rpm': rpm, 'compression': 0.0,
                'torque_nm': tnm, 'torque_lbft': tnm * 0.737562,
                'power_hp': hp, 'power_kw': hp * 0.7457
            })
        self.engine.filename = "Demo Engine"
        self.engine.rev_limit = 18200
        self.file_label.setText('Demo Engine (Built-in Sample)')
        self._push_history()
        self._refresh_all()

    # ===== FILE OPS =====
    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Engine File", "",
            "Engine Files (*.eng *.ini *.json);;All (*)")
        if path:
            self._load_file(path)

    def _load_file(self, path):
        try:
            if self.engine.load_file(path):
                self.file_label.setText(self.engine.filename)
                self._history = []
                self._hist_idx = -1
                self._push_history()
                # Engine Params dugme — samo za ISI fajlove
                self.btn_eng_params.setEnabled(not self.engine.was_json)
                # Vehicle info panel
                if self.engine.was_json and self.engine.original_json_data:
                    self._update_vehicle_panel(self.engine.original_json_data)
                    self.veh_frame.show()
                else:
                    self.veh_name_lbl.setText('')
                    self.veh_specs_lbl.setText('')
                    self.veh_brand_lbl.setText('')
                    self.veh_frame.hide()
                self._refresh_all()
                self._set_status(f'{self.engine.filename}  |  {len(self.engine.torque_data)} pts', '#00ff88')
                self._show_toast(f'✓  File loaded: {self.engine.filename}', '#a8e6a3')
                self._update_footer_dot()
            else:
                QMessageBox.warning(self, "Error", "No valid engine data found.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def save_file(self):
        if not self.engine.filepath:
            self.save_as()
            return
        try:
            if self.engine.save_file():
                self._set_status(f'Saved: {self.engine.filename}', '#61afef')
                self._show_toast(f'✓  Saved: {self.engine.filename}', '#61afef')
                QMessageBox.information(self, "Saved", f"Saved:\n{self.engine.filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def save_as(self):
        if not self.engine.torque_data:
            return
        orig_ext = os.path.splitext(self.engine.filepath)[1].lower() if self.engine.filepath else '.ini'
        if orig_ext not in ('.json', '.eng', '.ini'):
            orig_ext = '.ini'
        path, _ = QFileDialog.getSaveFileName(self, "Save As",
            self.engine.filename or 'engine',
            "INI (*.ini);;ENG (*.eng);;JSON (*.json);;All (*)")
        if path:
            try:
                if self.engine.save_file(path):
                    self.engine.filepath = path
                    self.engine.filename = os.path.basename(path)
                    self.file_label.setText(self.engine.filename)
                    self._set_status(f'Saved as: {self.engine.filename}', '#61afef')
                    self._show_toast(f'✓  Saved as: {self.engine.filename}', '#61afef')
                    QMessageBox.information(self, "Saved", f"Saved as:\n{self.engine.filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    # ===== UNDO/REDO =====
    def _push_history(self):
        snapshot = copy.deepcopy(self.engine.torque_data)
        self._history = self._history[:self._hist_idx + 1]
        self._history.append(snapshot)
        if len(self._history) > 30:
            self._history.pop(0)
        self._hist_idx = len(self._history) - 1

    def undo(self):
        if self._hist_idx > 0:
            self._hist_idx -= 1
            self.engine.torque_data = copy.deepcopy(self._history[self._hist_idx])
            self._refresh_all()

    def redo(self):
        if self._hist_idx < len(self._history) - 1:
            self._hist_idx += 1
            self.engine.torque_data = copy.deepcopy(self._history[self._hist_idx])
            self._refresh_all()

    # ===== EDIT =====
    def set_max_hp(self):
        if not self.engine.torque_data:
            return
        unit = "kW" if self.current_units == 'metric' else "HP"
        key = 'power_kw' if self.current_units == 'metric' else 'power_hp'
        cur_max = max(p[key] for p in self.engine.torque_data)
        text, ok = QInputDialog.getText(self, f"Set Max {unit}",
            f"Current max: {cur_max:.1f} {unit}\nNew target:", text=f"{cur_max:.1f}")
        if ok and text:
            try:
                target = float(text)
                if target > 0:
                    self._push_history()
                    self.engine.scale_all_torque(target / cur_max)
                    self._refresh_all()
            except ValueError:
                QMessageBox.warning(self, "Error", "Invalid number")

    def scale_curve(self):
        if not self.engine.torque_data:
            return
        text, ok = QInputDialog.getText(self, "Scale Torque Curve",
            "Enter % change (e.g. +5 or -10):", text="0")
        if ok and text:
            try:
                pct = float(text)
                self._push_history()
                self.engine.scale_all_torque(1.0 + pct / 100.0)
                self._refresh_all()
            except ValueError:
                QMessageBox.warning(self, "Error", "Invalid number")

    def add_point(self):
        if not self.engine.torque_data:
            self.engine.add_point(1000, 100.0)
            self._push_history()
            self._refresh_all()
            return
        last = self.engine.torque_data[-1]
        text, ok = QInputDialog.getText(self, "Add Point",
            f"Enter RPM,Torque(Nm):", text=f"{last['rpm']+500},{last['torque_nm']:.1f}")
        if ok and text:
            try:
                parts = text.replace(' ', '').split(',')
                if len(parts) >= 2:
                    self._push_history()
                    self.engine.add_point(float(parts[0]), float(parts[1]))
                    self._refresh_all()
            except ValueError:
                QMessageBox.warning(self, "Error", "Format: RPM,Torque")

    def delete_point(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.engine.torque_data):
            p = self.engine.torque_data[row]
            r = QMessageBox.question(self, "Delete", f"Delete @ {p['rpm']:.0f} RPM?")
            if r == QMessageBox.StandardButton.Yes:
                self._push_history()
                self.engine.delete_point(row)
                self._refresh_all()

    def _on_cell_double_clicked(self, row, col):
        if not (0 <= row < len(self.engine.torque_data)):
            return
        p = self.engine.torque_data[row]
        is_metric = self.current_units == 'metric'
        if col == 0:
            dlg = EditDialog(self, "Edit RPM", f"RPM:", f"{p['rpm']:.0f}")
            if dlg.exec() and (val := dlg.get_value()) is not None:
                self._push_history(); self.engine.update_rpm(row, val); self._refresh_all()
        elif col == 1:
            dlg = EditDialog(self, "Edit Compression", "Compression:", f"{p['compression']:.2f}")
            if dlg.exec() and (val := dlg.get_value()) is not None:
                self._push_history(); self.engine.update_compression(row, val); self._refresh_all()
        elif col == 2:
            unit = "Nm" if is_metric else "lb-ft"
            cur = p['torque_nm'] if is_metric else p['torque_lbft']
            dlg = EditDialog(self, f"Edit Torque @ {p['rpm']:.0f}", f"Torque ({unit}):", f"{cur:.2f}")
            if dlg.exec() and (val := dlg.get_value()) is not None:
                val_nm = val if is_metric else val / 0.737562
                self._push_history(); self.engine.update_torque(row, val_nm); self._refresh_all()
        elif col == 3:
            unit = "kW" if is_metric else "HP"
            cur = p['power_kw'] if is_metric else p['power_hp']
            dlg = EditDialog(self, f"Edit Power @ {p['rpm']:.0f}", f"Power ({unit}):", f"{cur:.2f}")
            if dlg.exec() and (val := dlg.get_value()) is not None:
                val_hp = val / 0.7457 if is_metric else val
                self._push_history(); self.engine.update_power(row, val_hp); self._refresh_all()

    # ===== UNITS =====
    def set_units(self, val):
        """Prebaci jedinice + GLATKA INTERPOLACIJA krivulja."""
        if val == self.current_units:
            return
        old_units = self.current_units
        self.current_units = val
        self._rebuild_cache()  # units changed → invalidate cache

        # Update toggle dugmad - HP=plavo, kW=zeleno
        if val == 'imperial':
            self.btn_imperial.setObjectName('unitActive')        # plavo
            self.btn_metric.setObjectName('unitInactive')        # sivo
        else:
            self.btn_imperial.setObjectName('unitInactive')      # sivo
            self.btn_metric.setObjectName('unitActiveMetric')    # zeleno
        for b in (self.btn_imperial, self.btn_metric):
            b.style().unpolish(b)
            b.style().polish(b)

        # Tabela - obican refresh
        self._refresh_table()

        # Legenda ispod charta — prati units
        if hasattr(self, '_leg_pw_w'):
            p_lbl = "Power (kW)" if val == 'metric' else "Power (HP)"
            t_lbl = "Torque (Nm)" if val == 'metric' else "Torque (lb-ft)"
            col_pw = '#5bcc7a' if val == 'metric' else '#e06c75'
            # Pronadi labele unutar widget-a i update-aj ih
            for child in self._leg_pw_w.findChildren(QLabel):
                if child.text() not in ('━━',):
                    child.setText(p_lbl)
                else:
                    child.setStyleSheet(f'color:{col_pw}; font-size:10px; background:transparent;')
            for child in self._leg_tq_w.findChildren(QLabel):
                if child.text() not in ('━━',):
                    child.setText(t_lbl)

        # DISPLAY CELIJE (gore) - glatka animacija cifara
        self._animate_stats_units(old_units, val)

        # Krivulje - glatka tranzicija
        self._animate_units_change(old_units, val)

    def _animate_units_change(self, old_units, new_units):
        """Glatka tranzicija krivulja izmedju Imperial i Metric jedinica."""
        if not self.engine.torque_data:
            self._refresh_chart()
            return

        # Zaustavi prethodnu animaciju
        if hasattr(self, '_units_timer') and self._units_timer is not None:
            try:
                self._units_timer.stop()
                self._units_timer.deleteLater()
            except Exception:
                pass
            self._units_timer = None

        # Ako nema postojecih krivulja - mora se nacrtati
        if not hasattr(self, '_anim_torque_curve') or self._anim_torque_curve is None:
            self._refresh_chart()
            return

        rpms = np.array([p['rpm'] for p in self.engine.torque_data])

        # Stare vrijednosti (sa kojih krecemo)
        old_is_metric = (old_units == 'metric')
        old_torques = np.array([p['torque_nm'] if old_is_metric else p['torque_lbft']
                                 for p in self.engine.torque_data])
        old_powers = np.array([p['power_kw'] if old_is_metric else p['power_hp']
                                for p in self.engine.torque_data])

        # Nove vrijednosti (do kojih idemo)
        new_is_metric = (new_units == 'metric')
        new_torques = np.array([p['torque_nm'] if new_is_metric else p['torque_lbft']
                                 for p in self.engine.torque_data])
        new_powers = np.array([p['power_kw'] if new_is_metric else p['power_hp']
                                for p in self.engine.torque_data])

        # Update boja Power krivulje
        col_pw = '#98c379' if new_is_metric else self.COL_PW
        col_pw_fill = (152, 195, 121, 40) if new_is_metric else self.COL_PW_FILL

        try:
            self._anim_power_curve.setPen(pg.mkPen(col_pw, width=3))
            self._anim_power_curve.setFillBrush(pg.mkBrush(*col_pw_fill))
        except Exception:
            pass

        # Update axis labels
        t_lbl = "Nm" if new_is_metric else "lb-ft"
        p_lbl = "kW" if new_is_metric else "HP"
        self.plot_widget.setLabel('left', f'Torque ({t_lbl})', color=self.COL_TQ, size='11pt')
        self.plot_widget.setLabel('right', f'Power ({p_lbl})', color=col_pw, size='11pt')
        self.plot_widget.getAxis('right').setTextPen(col_pw)

        # COMPARE krivulje - takodje se transformisu pri HP <-> kW
        cmp_old_torques = cmp_new_torques = cmp_old_powers = cmp_new_powers = None
        cmp_rpms_arr = None
        if self.compare_engine and self.compare_engine.torque_data and \
           hasattr(self, '_anim_cmp_torque_curve') and self._anim_cmp_torque_curve:
            cmp_data = self.compare_engine.torque_data
            cmp_rpms_arr = np.array([p['rpm'] for p in cmp_data])
            cmp_old_torques = np.array([p['torque_nm'] if old_is_metric else p['torque_lbft'] for p in cmp_data])
            cmp_new_torques = np.array([p['torque_nm'] if new_is_metric else p['torque_lbft'] for p in cmp_data])
            cmp_old_powers = np.array([p['power_kw'] if old_is_metric else p['power_hp'] for p in cmp_data])
            cmp_new_powers = np.array([p['power_kw'] if new_is_metric else p['power_hp'] for p in cmp_data])

        # Animacija parametri
        STEPS = 25
        DURATION_MS = 16

        # Capture closure variables
        anim_step = [0]
        torque_curve = self._anim_torque_curve
        power_curve = self._anim_power_curve

        timer = QTimer(self)
        timer.setSingleShot(False)
        self._units_timer = timer

        def _interp_tick():
            step = anim_step[0]
            if step > STEPS:
                # Finalni - postavimo tacno nove vrijednosti + update marker boje
                try:
                    torque_curve.setData(rpms, new_torques)
                    power_curve.setData(rpms, new_powers)
                    # Final compare
                    if cmp_rpms_arr is not None and cmp_new_torques is not None:
                        if hasattr(self, '_anim_cmp_torque_curve') and self._anim_cmp_torque_curve:
                            self._anim_cmp_torque_curve.setData(cmp_rpms_arr, cmp_new_torques)
                        if hasattr(self, '_anim_cmp_power_curve') and self._anim_cmp_power_curve:
                            self._anim_cmp_power_curve.setData(cmp_rpms_arr, cmp_new_powers)
                    # Final peak markeri sa NOVIM bojama prema units
                    final_max_tq = new_torques.max()
                    final_max_pw = new_powers.max()
                    final_ptr = rpms[new_torques.argmax()]
                    final_ppr = rpms[new_powers.argmax()]
                    is_metric_final = (new_units == 'metric')
                    new_pw_color = '#5bcc7a' if is_metric_final else '#e06c75'
                    new_pw_glow_brush = pg.mkBrush(91, 204, 122, 180) if is_metric_final else pg.mkBrush(224, 108, 117, 180)
                    if hasattr(self, '_peak_tq_marker') and self._peak_tq_marker:
                        self._peak_tq_marker.setData([final_ptr], [final_max_tq])
                    if hasattr(self, '_peak_pw_marker') and self._peak_pw_marker:
                        self._peak_pw_marker.setData(
                            [final_ppr], [final_max_pw],
                            brush=pg.mkBrush(new_pw_color),
                            pen=pg.mkPen('white', width=2))
                    if hasattr(self, '_peak_tq_glow') and self._peak_tq_glow:
                        self._peak_tq_glow.setData([final_ptr], [final_max_tq])
                    if hasattr(self, '_peak_pw_glow') and self._peak_pw_glow:
                        self._peak_pw_glow.setData(
                            [final_ppr], [final_max_pw],
                            brush=new_pw_glow_brush,
                            pen=pg.mkPen(None))
                except Exception:
                    pass
                timer.stop()
                try:
                    timer.deleteLater()
                except Exception:
                    pass
                self._units_timer = None
                # Refresh legend
                self._refresh_legend_only()
                # Reset axis to fixed 1600/24000
                self.plot_widget.getViewBox().setRange(xRange=(0, 24000), yRange=(0, 1600), padding=0.05)
                self.plot_widget.getViewBox().setLimits(xMin=-500, xMax=24500, yMin=-2, yMax=1680)
                return

            # Smoothstep ease in-out
            t = step / STEPS
            ease = t * t * (3 - 2 * t)

            cur_tq = old_torques + (new_torques - old_torques) * ease
            cur_pw = old_powers + (new_powers - old_powers) * ease

            try:
                torque_curve.setData(rpms, cur_tq)
                power_curve.setData(rpms, cur_pw)
                # COMPARE krivulje takodje
                if cmp_rpms_arr is not None and cmp_old_torques is not None:
                    cmp_cur_tq = cmp_old_torques + (cmp_new_torques - cmp_old_torques) * ease
                    cmp_cur_pw = cmp_old_powers + (cmp_new_powers - cmp_old_powers) * ease
                    if hasattr(self, '_anim_cmp_torque_curve') and self._anim_cmp_torque_curve:
                        self._anim_cmp_torque_curve.setData(cmp_rpms_arr, cmp_cur_tq)
                    if hasattr(self, '_anim_cmp_power_curve') and self._anim_cmp_power_curve:
                        self._anim_cmp_power_curve.setData(cmp_rpms_arr, cmp_cur_pw)
                    # Update compare peak markere
                    cmp_cur_max_tq = cmp_cur_tq.max()
                    cmp_cur_max_pw = cmp_cur_pw.max()
                    cmp_cur_ptr = cmp_rpms_arr[cmp_cur_tq.argmax()]
                    cmp_cur_ppr = cmp_rpms_arr[cmp_cur_pw.argmax()]
                    if hasattr(self, '_cmp_peak_tq_marker') and self._cmp_peak_tq_marker:
                        self._cmp_peak_tq_marker.setData([cmp_cur_ptr], [cmp_cur_max_tq])
                    if hasattr(self, '_cmp_peak_pw_marker') and self._cmp_peak_pw_marker:
                        self._cmp_peak_pw_marker.setData([cmp_cur_ppr], [cmp_cur_max_pw])
                    if hasattr(self, '_cmp_peak_tq_glow') and self._cmp_peak_tq_glow:
                        self._cmp_peak_tq_glow.setData([cmp_cur_ptr], [cmp_cur_max_tq])
                    if hasattr(self, '_cmp_peak_pw_glow') and self._cmp_peak_pw_glow:
                        self._cmp_peak_pw_glow.setData([cmp_cur_ppr], [cmp_cur_max_pw])
                    # Outer glow + labels
                    if hasattr(self, '_cmp_peak_tq_glow_outer') and self._cmp_peak_tq_glow_outer:
                        self._cmp_peak_tq_glow_outer.setData([cmp_cur_ptr], [cmp_cur_max_tq])
                    if hasattr(self, '_cmp_peak_pw_glow_outer') and self._cmp_peak_pw_glow_outer:
                        self._cmp_peak_pw_glow_outer.setData([cmp_cur_ppr], [cmp_cur_max_pw])
                    if hasattr(self, '_cmp_tq_label') and self._cmp_tq_label:
                        self._cmp_tq_label.setHtml(f'<div style="background:rgba(15,15,25,230); padding:2px 6px; border-radius:3px; font-family:Segoe UI; font-size:9pt; color:#ffd600; font-weight:600;">Cmp Tq: <b>{cmp_cur_max_tq:.0f}</b></div>')
                        self._cmp_tq_label.setPos(cmp_cur_ptr, cmp_cur_max_tq)
                    if hasattr(self, '_cmp_pw_label') and self._cmp_pw_label:
                        self._cmp_pw_label.setHtml(f'<div style="background:rgba(15,15,25,230); padding:2px 6px; border-radius:3px; font-family:Segoe UI; font-size:9pt; color:#c084fc; font-weight:600;">Cmp Pw: <b>{cmp_cur_max_pw:.0f}</b></div>')
                        self._cmp_pw_label.setPos(cmp_cur_ppr, cmp_cur_max_pw)
                # Update peak markere da prate krivulje
                cur_max_tq = cur_tq.max()
                cur_max_pw = cur_pw.max()
                cur_ptr = rpms[cur_tq.argmax()]
                cur_ppr = rpms[cur_pw.argmax()]
                if hasattr(self, '_peak_tq_marker') and self._peak_tq_marker:
                    self._peak_tq_marker.setData([cur_ptr], [cur_max_tq])
                if hasattr(self, '_peak_pw_marker') and self._peak_pw_marker:
                    self._peak_pw_marker.setData([cur_ppr], [cur_max_pw])
                if hasattr(self, '_peak_tq_glow') and self._peak_tq_glow:
                    self._peak_tq_glow.setData([cur_ptr], [cur_max_tq])
                if hasattr(self, '_peak_pw_glow') and self._peak_pw_glow:
                    self._peak_pw_glow.setData([cur_ppr], [cur_max_pw])
                # Single labeli - update vrijednosti i pozicije
                if hasattr(self, '_peak_tq_label') and self._peak_tq_label:
                    self._peak_tq_label.setHtml(f'<div style="background:rgba(15,15,25,230); padding:2px 6px; border-radius:3px; font-family:Segoe UI; font-size:9pt; color:#61afef; font-weight:600;">Peak Tq: <b>{cur_max_tq:.0f}</b></div>')
                    self._peak_tq_label.setPos(cur_ptr, cur_max_tq)
                if hasattr(self, '_peak_pw_label') and self._peak_pw_label:
                    pw_color_now = '#5bcc7a' if self.current_units == 'metric' else '#e06c75'
                    self._peak_pw_label.setHtml(f'<div style="background:rgba(15,15,25,230); padding:2px 6px; border-radius:3px; font-family:Segoe UI; font-size:9pt; color:{pw_color_now}; font-weight:600;">Peak Pw: <b>{cur_max_pw:.0f}</b></div>')
                    self._peak_pw_label.setPos(cur_ppr, cur_max_pw)
            except Exception:
                pass

            # Drzi fiksne ose
            vb = self.plot_widget.getViewBox()
            vb.disableAutoRange()
            vb.setRange(xRange=(0, 24000), yRange=(0, 1600), padding=0.05)
            vb.setLimits(xMin=-500, xMax=24500, yMin=-2, yMax=1680)

            anim_step[0] += 1

        timer.timeout.connect(_interp_tick)
        timer.start(DURATION_MS)

    def _refresh_legend_only(self):
        """Update samo legendu sa novim peak vrijednostima."""
        if not self.engine.torque_data or self._legend is None:
            return
        is_metric = self.current_units == 'metric'
        if self._cache_rpms is None or self._cache_units != self.current_units:
            self._rebuild_cache()
        torques = self._cache_torques
        powers  = self._cache_powers
        t_lbl = "Nm" if is_metric else "lb-ft"
        p_lbl = "kW" if is_metric else "HP"
        max_tq = torques.max()
        max_pw = powers.max()

        try:
            self._legend.clear()
            if hasattr(self, '_anim_torque_curve') and self._anim_torque_curve:
                self._legend.addItem(self._anim_torque_curve, f'Torque ({max_tq:.1f} {t_lbl} peak)')
            if hasattr(self, '_anim_power_curve') and self._anim_power_curve:
                self._legend.addItem(self._anim_power_curve, f'Power ({max_pw:.1f} {p_lbl} peak)')
        except Exception:
            pass

    def export_png(self):
        if not self.engine.torque_data:
            return
        default = os.path.splitext(self.engine.filename)[0] if self.engine.filename else 'chart'
        path, _ = QFileDialog.getSaveFileName(self, "Export", f"{default}_chart.png", "PNG (*.png)")
        if path:
            try:
                from pyqtgraph.exporters import ImageExporter
                exporter = ImageExporter(self.plot_widget.plotItem)
                exporter.parameters()['width'] = 1920
                exporter.export(path)
                self._set_status(f'Exported: {os.path.basename(path)}', '#a8e6a3')
                self._show_toast(f'✓  Exported PNG', '#a8e6a3')
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def copy_csv(self):
        if not self.engine.torque_data:
            return
        is_metric = self.current_units == 'metric'
        tq_l = 'Torque_Nm' if is_metric else 'Torque_lbft'
        pw_l = 'Power_kW' if is_metric else 'Power_HP'
        lines = [f"RPM,Compression,{tq_l},{pw_l}"]
        for p in self.engine.torque_data:
            tq = p['torque_nm'] if is_metric else p['torque_lbft']
            pw = p['power_kw'] if is_metric else p['power_hp']
            lines.append(f"{p['rpm']:.0f},{p['compression']:.2f},{tq:.4f},{pw:.4f}")
        QApplication.clipboard().setText('\n'.join(lines))
        self._set_status(f'Copied {len(self.engine.torque_data)} rows to clipboard', '#a8e6a3')
        self._show_toast(f'✓  CSV copied ({len(self.engine.torque_data)} rows)', '#a8e6a3')

    def compare_files(self):
        # Toggle: ako vec ima compare, ugasi
        if self.compare_engine and self.compare_engine.torque_data:
            self.compare_engine = None
            self.btn_compare.setObjectName('compareOff')
            self.btn_compare.style().unpolish(self.btn_compare)
            self.btn_compare.style().polish(self.btn_compare)
            self._set_status('Compare cleared', '#7d8590')
            self._update_footer_compare(None)
            self._show_toast('Compare removed', '#7d8590')
            # Sakri compare label
            if hasattr(self, 'compare_file_label'):
                self.compare_file_label.hide()
                self.compare_separator.hide()
            self._refresh_all()
            return
        path, _ = QFileDialog.getOpenFileName(self, "Compare", "", "Engine (*.eng *.ini *.json);;All (*)")
        if path:
            try:
                cmp = EngineFile()
                if cmp.load_file(path):
                    self.compare_engine = cmp
                    self.btn_compare.setObjectName('compareOn')
                    self.btn_compare.style().unpolish(self.btn_compare)
                    self.btn_compare.style().polish(self.btn_compare)
                    self._set_status(f'Compare: {cmp.filename}', '#ffd600')
                    self._update_footer_compare(cmp.filename)
                    self._show_toast(f'✓  Compare loaded: {cmp.filename}', '#ffd600')
                    # Prikazi compare label u headeru
                    if hasattr(self, 'compare_file_label'):
                        self.compare_file_label.setText(cmp.filename)
                        self.compare_file_label.show()
                        self.compare_separator.show()
                    self._refresh_chart()
                    self._refresh_table()
                    self._refresh_stats()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    # ===== REFRESH =====
    def _rebuild_cache(self):
        """Rebuild numpy cache. Called once per _refresh_all."""
        is_metric = self.current_units == 'metric'
        d = self.engine.torque_data
        if not d:
            self._cache_rpms = None
            self._cache_torques = None
            self._cache_powers = None
            self._cache_units = None
            return
        self._cache_rpms    = np.array([p['rpm'] for p in d])
        self._cache_torques = np.array([p['torque_nm'] if is_metric else p['torque_lbft'] for p in d])
        self._cache_powers  = np.array([p['power_kw'] if is_metric else p['power_hp'] for p in d])
        self._cache_units   = self.current_units

    def _update_pulse(self):
        """Update pulse phase i prerenderuje markere sa novim sin wave vrijednostima."""
        if not self.engine.torque_data:
            return
        if not hasattr(self, '_peak_tq_marker') or self._peak_tq_marker is None:
            return
        
        self._pulse_phase += 0.08  # brzina pulsiranja
        
        # SINGLE markeri - svaki sa svojim phase offset
        # Tq phase=0, Pw phase=1.4
        is_metric = self.current_units == 'metric'
        # Use cached arrays — rebuilt on _refresh_all, no per-tick allocation
        if self._cache_rpms is None or self._cache_units != self.current_units:
            return
        rpms    = self._cache_rpms
        torques = self._cache_torques
        powers  = self._cache_powers
        
        max_tq = torques.max()
        max_pw = powers.max()
        ptr = rpms[torques.argmax()]
        ppr = rpms[powers.argmax()]
        
        col_tq_marker = '#61afef'
        col_pw_marker = '#5bcc7a' if is_metric else '#e06c75'
        
        # Sin pulse za TQ (phase 0)
        pulse_tq = 0.5 + 0.5 * math.sin(self._pulse_phase * 2.1 + 0.0)
        # Sin pulse za PW (phase 1.4)
        pulse_pw = 0.5 + 0.5 * math.sin(self._pulse_phase * 2.1 + 1.4)
        
        # Update glow size (alpha + radius pulsing)
        # Single Tq glow
        if hasattr(self, '_peak_tq_glow') and self._peak_tq_glow:
            try:
                # Velicina raste sa pulsom
                glow_size_tq = 14 + pulse_tq * 12  # 14 -> 26
                glow_alpha_tq = int(80 + pulse_tq * 100)  # 80 -> 180
                # RGB iz col_tq_marker (#61afef)
                self._peak_tq_glow.setSize(glow_size_tq)
                self._peak_tq_glow.setBrush(pg.mkBrush(97, 175, 239, glow_alpha_tq))
            except Exception:
                pass
        
        # Single Pw glow
        if hasattr(self, '_peak_pw_glow') and self._peak_pw_glow:
            try:
                glow_size_pw = 14 + pulse_pw * 12
                glow_alpha_pw = int(80 + pulse_pw * 100)
                # RGB iz col_pw_marker
                if is_metric:
                    self._peak_pw_glow.setBrush(pg.mkBrush(91, 204, 122, glow_alpha_pw))
                else:
                    self._peak_pw_glow.setBrush(pg.mkBrush(224, 108, 117, glow_alpha_pw))
                self._peak_pw_glow.setSize(glow_size_pw)
            except Exception:
                pass
        
        # COMPARE markeri - phase offset 0.7 i 2.1
        if self.compare_engine and self.compare_engine.torque_data and \
           hasattr(self, '_cmp_peak_tq_glow') and self._cmp_peak_tq_glow:
            pulse_cmp_tq = 0.5 + 0.5 * math.sin(self._pulse_phase * 2.1 + 0.7)
            pulse_cmp_pw = 0.5 + 0.5 * math.sin(self._pulse_phase * 2.1 + 2.1)
            
            try:
                # Compare TQ (zuta) glow
                glow_size_ctq = 12 + pulse_cmp_tq * 10
                glow_alpha_ctq = int(60 + pulse_cmp_tq * 100)
                self._cmp_peak_tq_glow.setSize(glow_size_ctq)
                self._cmp_peak_tq_glow.setBrush(pg.mkBrush(255, 214, 0, glow_alpha_ctq))
                
                # Compare PW (ljubicasta) glow
                glow_size_cpw = 12 + pulse_cmp_pw * 10
                glow_alpha_cpw = int(60 + pulse_cmp_pw * 100)
                self._cmp_peak_pw_glow.setSize(glow_size_cpw)
                self._cmp_peak_pw_glow.setBrush(pg.mkBrush(192, 132, 252, glow_alpha_cpw))
                
                # Outer glow (jos sporije pulsiranje)
                if hasattr(self, '_cmp_peak_tq_glow_outer') and self._cmp_peak_tq_glow_outer:
                    glow_size_octq = 14 + pulse_cmp_tq * 8
                    glow_alpha_octq = int(40 + pulse_cmp_tq * 60)
                    self._cmp_peak_tq_glow_outer.setSize(glow_size_octq)
                    self._cmp_peak_tq_glow_outer.setBrush(pg.mkBrush(255, 214, 0, glow_alpha_octq))
                if hasattr(self, '_cmp_peak_pw_glow_outer') and self._cmp_peak_pw_glow_outer:
                    glow_size_ocpw = 14 + pulse_cmp_pw * 8
                    glow_alpha_ocpw = int(40 + pulse_cmp_pw * 60)
                    self._cmp_peak_pw_glow_outer.setSize(glow_size_ocpw)
                    self._cmp_peak_pw_glow_outer.setBrush(pg.mkBrush(192, 132, 252, glow_alpha_ocpw))
            except Exception:
                pass

    # ===== STATUS / TOAST HELPERS =====
    def _update_fps(self):
        """Live FPS - broji pyqtgraph Paint evente u posljednjoj sekundi."""
        fps = self._fps_cnt[0]
        self._fps_cnt[0] = 0
        col = '#3fb950' if fps >= 55 else '#d29922' if fps >= 30 else '#f85149'
        if hasattr(self, '_fps_lbl'):
            self._fps_lbl.setText(f'GPU {fps} FPS  |  pyqtgraph')
            self._fps_lbl.setStyleSheet(f'color: {col}; font-size: 10px; padding: 4px;')

    def _set_status(self, text, color='#7d8590'):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f'color: {color}; font-family: Consolas; font-size: 10px; padding: 2px 0;')

    def _update_footer_dot(self):
        has_data = bool(self.engine.torque_data)
        col = '#00ff88' if has_data else '#7d8590'
        self._dot_label.setStyleSheet(
            f'color: {col}; font-size: 11px; padding-right: 6px; font-family: Consolas;')

    def _update_footer_history(self):
        if self._history:
            self._footer_history.setText(f'History {self._hist_idx + 1}/{len(self._history)}')
        else:
            self._footer_history.setText('')

    def _update_footer_compare(self, name=None):
        if name:
            self._footer_compare.setText(f'Compare: {name}')
            self._footer_compare.show()
        else:
            self._footer_compare.hide()

    def _show_toast(self, text, color='#a8e6a3'):
        self._toast.setText(text)
        bg_map = {'#a8e6a3': '#0d1f18', '#61afef': '#0d1628', '#ffd600': '#1f1a00',
                  '#d29922': '#1f1500', '#7d8590': '#1a1a22'}
        bg = bg_map.get(color, '#1e2128')
        self._toast.setStyleSheet(
            f'color: {color}; font-family: Consolas; font-size: 10px; font-weight: 600; '
            f'background: {bg}; padding: 4px 14px; border-radius: 4px; '
            f'border: 1px solid {color}66; margin-left: 8px;')
        self._toast.show()
        self._toast_timer.start(2500)

    def _refresh_all(self):
        self._rebuild_cache()
        self._refresh_chart()
        self._refresh_table()
        self._refresh_stats()
        self._update_footer_dot()
        self._update_footer_history()


    def _refresh_with_anim(self):
        """Refresh sa animacijom SVIH 5 display celija (Peak TQ, Peak PW, RPM Range, Power Band, Rev Limit)."""
        if not self.engine.torque_data:
            self._refresh_all()
            return
        
        is_metric = self.current_units == 'metric'
        rpms = [p['rpm'] for p in self.engine.torque_data]
        torques = [p['torque_nm'] if is_metric else p['torque_lbft'] for p in self.engine.torque_data]
        powers = [p['power_kw'] if is_metric else p['power_hp'] for p in self.engine.torque_data]
        max_tq = max(torques); max_pw = max(powers)
        
        # Refresh chart i tabelu prvo
        self._refresh_chart()
        self._refresh_table()
        
        # Compare aktivan
        has_compare = self.compare_engine is not None and self.compare_engine.torque_data
        
        # Power Band threshold
        threshold = max_pw * 0.90
        band_rpms = [r for r, p in zip(rpms, powers) if p >= threshold]
        pb_min = min(band_rpms) if band_rpms else 0
        pb_max = max(band_rpms) if band_rpms else 0
        
        rev = self.engine.rev_limit if self.engine.rev_limit else 0
        
        # Compare data za subtitle animaciju
        cmp = self.compare_engine
        cmp_data_r = cmp.torque_data if cmp else []
        cmp_max_tq_r = cmp_max_pw_r = 0
        cmp_rpms_r = cmp_band_r = []
        cmp_rev_r = None
        if cmp_data_r:
            _cm = is_metric
            _ctr = [p['torque_nm'] if _cm else p['torque_lbft'] for p in cmp_data_r]
            _cpr = [p['power_kw']  if _cm else p['power_hp']    for p in cmp_data_r]
            cmp_max_tq_r = max(_ctr)
            cmp_max_pw_r = max(_cpr)
            cmp_rpms_r   = [p['rpm'] for p in cmp_data_r]
            cmp_band_r   = [r for r, p in zip(cmp_rpms_r, _cpr) if p >= cmp_max_pw_r * 0.90]
            cmp_rev_r    = cmp.rev_limit
        
        if hasattr(self, '_refresh_pulse_timer') and self._refresh_pulse_timer is not None:
            try:
                self._refresh_pulse_timer.stop()
                self._refresh_pulse_timer.deleteLater()
            except: pass
            self._refresh_pulse_timer = None
        
        STEPS = 20
        anim_step = [0]
        t_l = "Nm" if is_metric else "lb-ft"
        p_l = "kW" if is_metric else "HP"
        min_rpm = min(rpms); max_rpm = max(rpms)
        
        timer = QTimer(self)
        timer.setSingleShot(False)
        self._refresh_pulse_timer = timer
        
        def _pulse_tick():
            step = anim_step[0]
            if step > STEPS:
                self._refresh_stats()
                timer.stop()
                try: timer.deleteLater()
                except: pass
                self._refresh_pulse_timer = None
                return
            
            t = step / STEPS
            ease = t * t * (3 - 2 * t)
            
            # 1. Peak TQ
            cur_tq = max_tq * ease
            lv1, ls1 = self.stat_widgets['peak_tq']
            lv1.setText(f'{cur_tq:.1f} {t_l}')
            if cmp_data_r:
                d = cur_tq - cmp_max_tq_r
                ar = '▲' if d >= 0 else '▼'
                sg = '+' if d >= 0 else ''
                ls1.setText(f'{ar} VS {cmp_max_tq_r:.1f} ({sg}{d:.1f}) {t_l}')
                ls1.setStyleSheet('color: #ffd600; font-size: 13px; font-weight: 700; background: transparent; border: none;')
            
            # 2. Peak PW
            cur_pw = max_pw * ease
            lv2, ls2 = self.stat_widgets['peak_pw']
            lv2.setText(f'{cur_pw:.1f} {p_l}')
            if cmp_data_r:
                d2 = cur_pw - cmp_max_pw_r
                ar2 = '▲' if d2 >= 0 else '▼'
                sg2 = '+' if d2 >= 0 else ''
                ls2.setText(f'{ar2} VS {cmp_max_pw_r:.1f} ({sg2}{d2:.1f}) {p_l}')
                ls2.setStyleSheet('color: #ffd600; font-size: 13px; font-weight: 700; background: transparent; border: none;')
            
            # 3. RPM Range
            cur_max_rpm = int(max_rpm * ease)
            lv3, ls3 = self.stat_widgets['rpm_range']
            lv3.setText(f'{min_rpm:.0f} — {cur_max_rpm} RPM')
            if cmp_data_r and cmp_rpms_r:
                cur_cmp_max_rpm = int(max(cmp_rpms_r) * ease)
                mw = max(rpms) - min(rpms)
                cw = max(cmp_rpms_r) - min(cmp_rpms_r)
                ar3 = '▲' if mw >= cw else '▼'
                ls3.setText(f'{ar3} VS {min(cmp_rpms_r):.0f} — {cur_cmp_max_rpm} RPM')
                ls3.setStyleSheet('color: #ffd600; font-size: 13px; font-weight: 700; background: transparent; border: none;')
            
            # 4. Power Band
            cur_pb_max = int(pb_max * ease) if pb_max else 0
            cur_pb_min = int(pb_min * ease) if pb_min else 0
            lv4, ls4 = self.stat_widgets['power_band']
            if pb_max > 0:
                lv4.setText(f'{cur_pb_min} — {cur_pb_max} RPM')
            if cmp_data_r and cmp_band_r:
                cur_cmp_pb = int(max(cmp_band_r) * ease)
                cur_cmp_pm = int(min(cmp_band_r) * ease)
                mbw = (pb_max - pb_min) if pb_max else 0
                cbw = (max(cmp_band_r) - min(cmp_band_r)) if cmp_band_r else 0
                ar4 = '▲' if mbw >= cbw else '▼'
                ls4.setText(f'{ar4} VS {cur_cmp_pm} — {cur_cmp_pb} RPM')
                ls4.setStyleSheet('color: #ffd600; font-size: 13px; font-weight: 700; background: transparent; border: none;')
            
            # 5. Rev Limit
            cur_rev = int(rev * ease)
            lv5, ls5 = self.stat_widgets['rev_limit']
            if rev > 0:
                lv5.setText(f'{cur_rev} RPM')
            if cmp_data_r and cmp_rev_r:
                cur_cmp_rev = int(cmp_rev_r * ease)
                d5 = rev - cmp_rev_r
                ar5 = '▲' if d5 >= 0 else '▼'
                sg5 = '+' if d5 >= 0 else ''
                ls5.setText(f'{ar5} VS {cur_cmp_rev} ({sg5}{int(d5 * ease)}) RPM')
                ls5.setStyleSheet('color: #ffd600; font-size: 13px; font-weight: 700; background: transparent; border: none;')
            
            anim_step[0] += 1
        
        timer.timeout.connect(_pulse_tick)
        timer.start(20)
    def _refresh_stats(self):
        """Display celije + animacija cifara pri promjeni units."""
        if not self.engine.torque_data:
            for key, (val, sub) in self.stat_widgets.items():
                val.setText('—'); sub.setText('—')
            return
        is_metric = self.current_units == 'metric'
        rpms    = [p['rpm']        for p in self.engine.torque_data]
        torques = [p['torque_nm']  if is_metric else p['torque_lbft'] for p in self.engine.torque_data]
        powers  = [p['power_kw']   if is_metric else p['power_hp']    for p in self.engine.torque_data]
        max_tq  = max(torques); max_pw = max(powers)
        ptr     = rpms[torques.index(max_tq)]
        ppr     = rpms[powers.index(max_pw)]
        t_l = "Nm" if is_metric else "lb-ft"
        p_l = "kW" if is_metric else "HP"

        threshold = max_pw * 0.90
        band_rpms = [r for r, p in zip(rpms, powers) if p >= threshold]
        if band_rpms:
            pb_str = f'{min(band_rpms):.0f} — {max(band_rpms):.0f} RPM'
            pb_sub = '90% THRESHOLD'
        else:
            pb_str = '—'; pb_sub = '90% THRESHOLD'

        cmp = self.compare_engine
        cmp_data = cmp.torque_data if cmp else []

        def delta_str(main_val, cmp_val, unit=''):
            d = main_val - cmp_val
            arrow = '▲' if d >= 0 else '▼'
            sign = '+' if d >= 0 else ''
            return f'{arrow} VS {cmp_val:.1f} ({sign}{d:.1f}) {unit}'.strip()

        def range_arrow_str(main_min, main_max, cmp_min, cmp_max, unit='RPM'):
            main_w = main_max - main_min
            cmp_w  = cmp_max  - cmp_min
            arrow  = '▲' if main_w >= cmp_w else '▼'
            return f'{arrow} VS {cmp_min:.0f} — {cmp_max:.0f} {unit}'

        def rev_arrow_str(main_val, cmp_val):
            d = main_val - cmp_val
            arrow = '▲' if d >= 0 else '▼'
            sign  = '+' if d >= 0 else ''
            return f'{arrow} VS {cmp_val:.0f} ({sign}{d:.0f}) RPM'

        def sub_color(text):
            return '#ffd600'  # uvijek zuta — to je compare boja

        stats = {
            'peak_tq':   (f'{max_tq:.1f} {t_l}',  f'@ {ptr:.0f} RPM'),
            'peak_pw':   (f'{max_pw:.1f} {p_l}',   f'@ {ppr:.0f} RPM'),
            'rpm_range': (f'{min(rpms):.0f} — {max(rpms):.0f} RPM', f'{len(rpms)} POINTS'),
            'power_band':(pb_str, pb_sub),
            'rev_limit': (f'{self.engine.rev_limit:.0f} RPM' if self.engine.rev_limit else '—',
                          'MAX ENGINE RPM' if self.engine.rev_limit else 'not set'),
        }

        if cmp_data:
            cmp_rpms    = [p['rpm']       for p in cmp_data]
            cmp_torques = [p['torque_nm'] if is_metric else p['torque_lbft'] for p in cmp_data]
            cmp_powers  = [p['power_kw']  if is_metric else p['power_hp']    for p in cmp_data]
            cmp_max_tq  = max(cmp_torques); cmp_max_pw = max(cmp_powers)
            cmp_band    = [r for r, p in zip(cmp_rpms, cmp_powers) if p >= cmp_max_pw * 0.90]

            cmp_subs = {
                'peak_tq':    delta_str(max_tq, cmp_max_tq, t_l),
                'peak_pw':    delta_str(max_pw, cmp_max_pw, p_l),
                'rpm_range':  range_arrow_str(min(rpms), max(rpms), min(cmp_rpms), max(cmp_rpms)),
                'power_band': range_arrow_str(min(band_rpms) if band_rpms else 0,
                                              max(band_rpms) if band_rpms else 0,
                                              min(cmp_band) if cmp_band else 0,
                                              max(cmp_band) if cmp_band else 0),
                'rev_limit':  rev_arrow_str(self.engine.rev_limit or 0, cmp.rev_limit) \
                              if cmp and cmp.rev_limit else '—',
            }
            for key, (val_txt, _) in stats.items():
                lv, ls = self.stat_widgets[key]
                lv.setText(val_txt)
                sub_txt = cmp_subs.get(key, '—')
                ls.setText(sub_txt)
                col = sub_color(sub_txt)
                ls.setStyleSheet(f'color: {col}; font-size: 13px; font-weight: 700; background: transparent; border: none;')
        else:
            for key, (val_txt, sub_txt) in stats.items():
                lv, ls = self.stat_widgets[key]
                lv.setText(val_txt)
                ls.setText(sub_txt)
                ls.setStyleSheet('color: #007740; font-size: 11px; font-weight: 700; background: transparent; border: none;')

    def _animate_stats_units(self, old_units, new_units):
        """SVE display celije se animiraju pri HP <-> kW (Peak TQ, Peak PW, RPM Range, Power Band, Rev Limit)."""
        if not self.engine.torque_data:
            return
        old_is_metric = (old_units == 'metric')
        new_is_metric = (new_units == 'metric')

        rpms = [p['rpm'] for p in self.engine.torque_data]
        old_torques = [p['torque_nm'] if old_is_metric else p['torque_lbft'] for p in self.engine.torque_data]
        new_torques = [p['torque_nm'] if new_is_metric else p['torque_lbft'] for p in self.engine.torque_data]
        old_powers = [p['power_kw'] if old_is_metric else p['power_hp'] for p in self.engine.torque_data]
        new_powers = [p['power_kw'] if new_is_metric else p['power_hp'] for p in self.engine.torque_data]

        old_max_tq = max(old_torques); new_max_tq = max(new_torques)
        old_max_pw = max(old_powers); new_max_pw = max(new_powers)
        ptr = rpms[new_torques.index(new_max_tq)]
        ppr = rpms[new_powers.index(new_max_pw)]

        new_t_l = "Nm" if new_is_metric else "lb-ft"
        new_p_l = "kW" if new_is_metric else "HP"

        # Power Band (90% threshold)
        new_threshold = new_max_pw * 0.90
        new_band = [r for r, p in zip(rpms, new_powers) if p >= new_threshold]
        new_band_str = f'{min(new_band):.0f} — {max(new_band):.0f} RPM' if new_band else '—'

        # Rev limit (RPM bez jedinica - statican)
        rev_str = f'{self.engine.rev_limit:.0f} RPM' if self.engine.rev_limit else '—'

        # Compare deltas
        cmp = self.compare_engine
        cmp_data = cmp.torque_data if cmp else []
        new_cmp_max_tq = new_cmp_max_pw = 0
        cmp_rpms_anim = cmp_band_anim = []
        cmp_rev_anim = None
        if cmp_data:
            cmp_torques = [p['torque_nm'] if new_is_metric else p['torque_lbft'] for p in cmp_data]
            cmp_powers = [p['power_kw'] if new_is_metric else p['power_hp'] for p in cmp_data]
            new_cmp_max_tq = max(cmp_torques)
            new_cmp_max_pw = max(cmp_powers)
            cmp_rpms_anim  = [p['rpm'] for p in cmp_data]
            cmp_band_anim  = [r for r, p in zip(cmp_rpms_anim, cmp_powers) if p >= new_cmp_max_pw * 0.90]
            cmp_rev_anim   = cmp.rev_limit if cmp else None

        # Zaustavi prethodnu animaciju
        if hasattr(self, '_stats_timer') and self._stats_timer is not None:
            try:
                self._stats_timer.stop()
                self._stats_timer.deleteLater()
            except Exception:
                pass
            self._stats_timer = None

        STEPS = 25
        anim_step = [0]

        timer = QTimer(self)
        timer.setSingleShot(False)
        self._stats_timer = timer

        def _stats_tick():
            step = anim_step[0]
            if step > STEPS:
                self._refresh_stats()
                timer.stop()
                try: timer.deleteLater()
                except: pass
                self._stats_timer = None
                return

            t = step / STEPS
            ease = t * t * (3 - 2 * t)

            cur_max_tq = old_max_tq + (new_max_tq - old_max_tq) * ease
            cur_max_pw = old_max_pw + (new_max_pw - old_max_pw) * ease

            # 1. Peak TQ celija
            lv, ls = self.stat_widgets['peak_tq']
            lv.setText(f'{cur_max_tq:.1f} {new_t_l}')
            if cmp_data:
                d_tq = cur_max_tq - new_cmp_max_tq
                arrow = '▲' if d_tq >= 0 else '▼'
                sign = '+' if d_tq >= 0 else ''
                sub = f'{arrow} VS {new_cmp_max_tq:.1f} ({sign}{d_tq:.1f}) {new_t_l}'
                ls.setText(sub)
                ls.setStyleSheet('color: #ffd600; font-size: 13px; font-weight: 700; background: transparent; border: none;')
            else:
                ls.setText(f'@ {ptr:.0f} RPM')

            # 2. Peak PW celija
            lv2, ls2 = self.stat_widgets['peak_pw']
            lv2.setText(f'{cur_max_pw:.1f} {new_p_l}')
            if cmp_data:
                d_pw = cur_max_pw - new_cmp_max_pw
                arrow = '▲' if d_pw >= 0 else '▼'
                sign = '+' if d_pw >= 0 else ''
                sub2 = f'{arrow} VS {new_cmp_max_pw:.1f} ({sign}{d_pw:.1f}) {new_p_l}'
                ls2.setText(sub2)
                ls2.setStyleSheet('color: #ffd600; font-size: 13px; font-weight: 700; background: transparent; border: none;')
            else:
                ls2.setText(f'@ {ppr:.0f} RPM')

            # 3. RPM Range
            lv3, ls3 = self.stat_widgets['rpm_range']
            lv3.setText(f'{min(rpms):.0f} — {max(rpms):.0f} RPM')
            if cmp_data and cmp_rpms_anim:
                main_w = max(rpms) - min(rpms)
                cmp_w  = max(cmp_rpms_anim) - min(cmp_rpms_anim)
                ar3 = '▲' if main_w >= cmp_w else '▼'
                sub3 = f'{ar3} VS {min(cmp_rpms_anim):.0f} — {max(cmp_rpms_anim):.0f} RPM'
                ls3.setText(sub3)
                ls3.setStyleSheet('color: #ffd600; font-size: 13px; font-weight: 700; background: transparent; border: none;')

            # 4. Power Band
            lv4, ls4 = self.stat_widgets['power_band']
            lv4.setText(new_band_str)
            if cmp_data and cmp_band_anim:
                main_bw = (max(new_band) - min(new_band)) if new_band else 0
                cmp_bw  = (max(cmp_band_anim) - min(cmp_band_anim)) if cmp_band_anim else 0
                ar4 = '▲' if main_bw >= cmp_bw else '▼'
                sub4 = f'{ar4} VS {min(cmp_band_anim):.0f} — {max(cmp_band_anim):.0f} RPM'
                ls4.setText(sub4)
                ls4.setStyleSheet('color: #ffd600; font-size: 13px; font-weight: 700; background: transparent; border: none;')

            # 5. Rev Limit
            lv5, ls5 = self.stat_widgets['rev_limit']
            lv5.setText(rev_str)
            if cmp_data and cmp_rev_anim:
                d_rev = (self.engine.rev_limit or 0) - cmp_rev_anim
                ar5 = '▲' if d_rev >= 0 else '▼'
                sign5 = '+' if d_rev >= 0 else ''
                sub5 = f'{ar5} VS {cmp_rev_anim:.0f} ({sign5}{d_rev:.0f}) RPM'
                ls5.setText(sub5)
                ls5.setStyleSheet('color: #ffd600; font-size: 13px; font-weight: 700; background: transparent; border: none;')

            anim_step[0] += 1

        timer.timeout.connect(_stats_tick)
        timer.start(16)
    def _refresh_chart(self):
        """Render chart sa STAGGERED RISE animacijom (lijevo -> desno talas)."""
        import math
        # Sacuvaj postojece state pre clearovanja
        had_main_curves = (hasattr(self, '_anim_torque_curve') and self._anim_torque_curve is not None)
        
        self.plot_widget.getPlotItem().clear()
        
        # Reset reference
        self._anim_torque_curve = None
        self._anim_power_curve = None
        self._ref_line_tq = None
        self._ref_line_pw = None
        self._peak_tq_marker = None
        self._peak_pw_marker = None
        self._peak_tq_glow = None
        self._peak_pw_glow = None
        self._peak_tq_label = None
        self._peak_pw_label = None
        self._anim_cmp_torque_curve = None
        self._anim_cmp_power_curve = None
        self._cmp_peak_tq_marker = None
        self._cmp_peak_pw_marker = None
        self._cmp_peak_tq_glow = None
        self._cmp_peak_pw_glow = None
        self._cmp_peak_tq_glow_outer = None
        self._cmp_peak_pw_glow_outer = None
        self._cmp_tq_label = None
        self._cmp_pw_label = None
        if hasattr(self, '_legend') and self._legend:
            try: self._legend.scene().removeItem(self._legend)
            except: pass
            self._legend = None
        
        if not self.engine.torque_data:
            self._show_intro_text()
            return
        
        is_metric = self.current_units == 'metric'
        rpms = np.array([p['rpm'] for p in self.engine.torque_data])
        torques_target = np.array([p['torque_nm'] if is_metric else p['torque_lbft'] for p in self.engine.torque_data])
        powers_target = np.array([p['power_kw'] if is_metric else p['power_hp'] for p in self.engine.torque_data])
        
        col_pw = '#5bcc7a' if is_metric else '#e06c75'
        col_pw_fill = (91, 204, 122, 40) if is_metric else (224, 108, 117, 40)
        col_tq_marker = '#61afef'
        col_pw_marker = '#5bcc7a' if is_metric else '#e06c75'
        
        # Update axis labels
        t_lbl = "Nm" if is_metric else "lb-ft"
        p_lbl = "kW" if is_metric else "HP"
        self.plot_widget.setLabel('left', f'Torque ({t_lbl})', color=col_tq_marker, size='11pt')
        self.plot_widget.setLabel('right', f'Power ({p_lbl})', color=col_pw, size='11pt')
        self.plot_widget.getAxis('right').setTextPen(col_pw)
        
        # === GRID LINIJE (3 horizontalne) ===
        for grid_y in [400, 800, 1200]:
            grid_line = pg.InfiniteLine(
                pos=grid_y, angle=0,
                pen=pg.mkPen('#2a2a3e', width=1, style=Qt.PenStyle.DashLine))
            grid_line.setZValue(-20)
            self.plot_widget.addItem(grid_line)
        
        # === REFERENCE VERTIKALNE LINIJE (Peak Tq, Peak Pw) ===
        # Narandzasta = Peak Torque RPM
        # Zelena = Peak Power RPM
        # Crvena (Rev Limit) se dodaje na kraju u original kodu
        peak_tq_rpm_ref = rpms[torques_target.argmax()]
        peak_pw_rpm_ref = rpms[powers_target.argmax()]
        
        self._ref_line_tq = pg.InfiniteLine(
            pos=peak_tq_rpm_ref, angle=90,
            pen=pg.mkPen('#ff8c00', width=1, style=Qt.PenStyle.DashLine))  # narandzasta
        self._ref_line_tq.setZValue(5)
        self.plot_widget.addItem(self._ref_line_tq)
        
        self._ref_line_pw = pg.InfiniteLine(
            pos=peak_pw_rpm_ref, angle=90,
            pen=pg.mkPen('#3fb950', width=1, style=Qt.PenStyle.DashLine))  # zelena
        self._ref_line_pw.setZValue(5)
        self.plot_widget.addItem(self._ref_line_pw)
        
        # === RISE WAVE ANIMATION SETUP ===
        # Pocni od 0 i animiraj prema target vrijednostima
        # Staggered: svaka tacka kasni proporcionalno svojoj poziciji
        
        n = len(rpms)
        
        # Glavne krivulje - pocni od nula vektora
        torque_curve = pg.PlotDataItem(
            rpms, np.zeros_like(torques_target),
            pen=pg.mkPen(col_tq_marker, width=3),
            fillLevel=0, brush=pg.mkBrush(97, 175, 239, 40))
        power_curve = pg.PlotDataItem(
            rpms, np.zeros_like(powers_target),
            pen=pg.mkPen(col_pw, width=3),
            fillLevel=0, brush=pg.mkBrush(*col_pw_fill))
        torque_curve.setZValue(10)
        power_curve.setZValue(10)
        self.plot_widget.addItem(torque_curve)
        self.plot_widget.addItem(power_curve)
        self._anim_torque_curve = torque_curve
        self._anim_power_curve = power_curve
        
        # Compare krivulje (ako ima)
        cmp_torques_target = None
        cmp_powers_target = None
        cmp_rpms_arr = None
        if self.compare_engine and self.compare_engine.torque_data:
            cmp_data = self.compare_engine.torque_data
            cmp_rpms_arr = np.array([p['rpm'] for p in cmp_data])
            cmp_torques_target = np.array([p['torque_nm'] if is_metric else p['torque_lbft'] for p in cmp_data])
            cmp_powers_target = np.array([p['power_kw'] if is_metric else p['power_hp'] for p in cmp_data])
            
            COL_CMP_TQ = '#ffd600'
            COL_CMP_PW = '#c084fc'
            
            self._anim_cmp_torque_curve = pg.PlotDataItem(
                cmp_rpms_arr, np.zeros_like(cmp_torques_target),
                pen=pg.mkPen(COL_CMP_TQ, width=2, style=Qt.PenStyle.DashLine),
                fillLevel=0, brush=pg.mkBrush(255, 214, 0, 25))
            self._anim_cmp_power_curve = pg.PlotDataItem(
                cmp_rpms_arr, np.zeros_like(cmp_powers_target),
                pen=pg.mkPen(COL_CMP_PW, width=2, style=Qt.PenStyle.DashLine),
                fillLevel=0, brush=pg.mkBrush(192, 132, 252, 25))
            self._anim_cmp_torque_curve.setZValue(8)
            self._anim_cmp_power_curve.setZValue(8)
            self.plot_widget.addItem(self._anim_cmp_torque_curve)
            self.plot_widget.addItem(self._anim_cmp_power_curve)
            # Show compare legend entries
            if hasattr(self, '_leg_ctq_w'):
                self._leg_ctq_w.show()
                self._leg_cpw_w.show()
        else:
            # Hide compare legend entries when no compare
            if hasattr(self, '_leg_ctq_w'):
                self._leg_ctq_w.hide()
                self._leg_cpw_w.hide()
        
        # Postavi axis range
        vb = self.plot_widget.getViewBox()
        vb.disableAutoRange()
        vb.setRange(xRange=(0, 24000), yRange=(0, 1600), padding=0.05)
        vb.setLimits(xMin=-500, xMax=24500, yMin=-2, yMax=1680)
        vb.setBorder(pen=None)
        
        # Pripremi peak metadata (za markere koji ce se pojaviti na kraju)
        max_tq_final = torques_target.max()
        max_pw_final = powers_target.max()
        ptr_final = rpms[torques_target.argmax()]
        ppr_final = rpms[powers_target.argmax()]
        
        # === STAGGERED RISE ANIMATION ===
        if hasattr(self, '_rise_timer') and self._rise_timer is not None:
            try:
                self._rise_timer.stop()
                self._rise_timer.deleteLater()
            except: pass
            self._rise_timer = None
        
        TOTAL_FRAMES = 60  # ~1 sekunda na 60 FPS
        anim_step = [0]
        markers_added = [False]
        
        def ease_out(x):
            return 1 - pow(1 - x, 3)
        
        def _rise_tick():
            step = anim_step[0]
            if step > TOTAL_FRAMES:
                # Final - postavi tacne vrijednosti (ili smooth interpolirane) i dodaj markere
                try:
                    if getattr(self, '_smooth_mode', False) and len(rpms) >= 4:
                        dense = np.linspace(rpms.min(), rpms.max(), 600)
                        try:
                            from scipy.interpolate import CubicSpline
                            tq_s = np.clip(CubicSpline(rpms, torques_target)(dense), 0, None)
                            pw_s = np.clip(CubicSpline(rpms, powers_target)(dense), 0, None)
                        except ImportError:
                            # Pure-numpy natural cubic spline (vectorised)
                            _n = len(rpms) - 1
                            _h = np.diff(rpms.astype(float))
                            _dt = np.diff(torques_target.astype(float))
                            _dp2 = np.diff(powers_target.astype(float))
                            _A = np.zeros((_n+1, _n+1))
                            _A[0, 0] = 1.0; _A[_n, _n] = 1.0
                            _bt = np.zeros(_n+1); _bp = np.zeros(_n+1)
                            for _ii in range(1, _n):
                                _A[_ii,_ii-1]=_h[_ii-1]; _A[_ii,_ii]=2*(_h[_ii-1]+_h[_ii]); _A[_ii,_ii+1]=_h[_ii]
                                _bt[_ii]=3*(_dt[_ii]/_h[_ii]-_dt[_ii-1]/_h[_ii-1])
                                _bp[_ii]=3*(_dp2[_ii]/_h[_ii]-_dp2[_ii-1]/_h[_ii-1])
                            _ct = np.linalg.solve(_A, _bt); _cp = np.linalg.solve(_A, _bp)
                            _btc = _dt/_h - _h*(2*_ct[:-1]+_ct[1:])/3
                            _bpc = _dp2/_h - _h*(2*_cp[:-1]+_cp[1:])/3
                            _dtc = np.diff(_ct)/(3*_h); _dpc = np.diff(_cp)/(3*_h)
                            _ki = np.clip(np.searchsorted(rpms, dense) - 1, 0, _n-1)
                            _dx = dense - rpms[_ki]
                            tq_s = np.clip(torques_target[_ki]+_btc[_ki]*_dx+_ct[_ki]*_dx**2+_dtc[_ki]*_dx**3, 0, None)
                            pw_s = np.clip(powers_target[_ki]+_bpc[_ki]*_dx+_cp[_ki]*_dx**2+_dpc[_ki]*_dx**3, 0, None)
                        torque_curve.setData(dense, tq_s)
                        power_curve.setData(dense, pw_s)
                    else:
                        torque_curve.setData(rpms, torques_target)
                        power_curve.setData(rpms, powers_target)
                    if cmp_torques_target is not None:
                        self._anim_cmp_torque_curve.setData(cmp_rpms_arr, cmp_torques_target)
                        self._anim_cmp_power_curve.setData(cmp_rpms_arr, cmp_powers_target)
                except Exception:
                    pass
                
                # Dodaj markere TEK SAD - posle animacije
                if not markers_added[0]:
                    self._add_peak_markers(rpms, torques_target, powers_target,
                                            cmp_rpms_arr, cmp_torques_target, cmp_powers_target,
                                            col_tq_marker, col_pw_marker, is_metric)
                    markers_added[0] = True
                
                # Legend
                self._refresh_legend_only()
                
                self._rise_timer.stop()
                try: self._rise_timer.deleteLater()
                except: pass
                self._rise_timer = None
                return
            
            t = step / TOTAL_FRAMES  # 0 -> 1 (ukupna animacija)
            
            # Staggered: svaka tacka ima svoj progres
            cur_tq = np.zeros_like(torques_target)
            cur_pw = np.zeros_like(powers_target)
            for i in range(n):
                stagger = i / max(1, n - 1)  # 0 za prvu, 1 za zadnju
                # Svaka tacka pocinje da se podize sa svojim delay-em
                local_t = max(0, min(1, (t - stagger * 0.55) / 0.45))
                eased = ease_out(local_t)
                cur_tq[i] = torques_target[i] * eased
                # Power kasni za 0.18 (180ms na 1s)
                power_offset = 0.18
                local_t_pw = max(0, min(1, (t - stagger * 0.55 - power_offset) / (0.45 - power_offset)))
                eased_pw = ease_out(max(0, local_t_pw))
                cur_pw[i] = powers_target[i] * eased_pw
            
            try:
                torque_curve.setData(rpms, cur_tq)
                power_curve.setData(rpms, cur_pw)
            except Exception:
                pass
            
            # Compare animacija takodje
            if cmp_torques_target is not None and cmp_rpms_arr is not None:
                n_cmp = len(cmp_rpms_arr)
                cmp_cur_tq = np.zeros_like(cmp_torques_target)
                cmp_cur_pw = np.zeros_like(cmp_powers_target)
                for i in range(n_cmp):
                    stagger = i / max(1, n_cmp - 1)
                    local_t = max(0, min(1, (t - stagger * 0.55 - 0.05) / 0.45))
                    eased = ease_out(local_t)
                    cmp_cur_tq[i] = cmp_torques_target[i] * eased
                    local_t_pw = max(0, min(1, (t - stagger * 0.55 - 0.18 - 0.05) / 0.45))
                    eased_pw = ease_out(max(0, local_t_pw))
                    cmp_cur_pw[i] = cmp_powers_target[i] * eased_pw
                try:
                    self._anim_cmp_torque_curve.setData(cmp_rpms_arr, cmp_cur_tq)
                    self._anim_cmp_power_curve.setData(cmp_rpms_arr, cmp_cur_pw)
                except Exception:
                    pass
            
            # Drzi fiksne ose
            vb.disableAutoRange()
            vb.setRange(xRange=(0, 24000), yRange=(0, 1600), padding=0.05)
            vb.setLimits(xMin=-500, xMax=24500, yMin=-2, yMax=1680)
            
            anim_step[0] += 1
        
        timer = QTimer(self)
        timer.setSingleShot(False)
        self._rise_timer = timer
        timer.timeout.connect(_rise_tick)
        timer.start(16)  # ~60 FPS
        
        # Crosshair (bez animacije)
        self._ch_vline = pg.InfiniteLine(angle=90, movable=False,
            pen=pg.mkPen('#ffffff', width=1, style=Qt.PenStyle.DotLine))
        self._ch_vline.hide()
        self._ch_vline.setZValue(20)
        self.plot_widget.addItem(self._ch_vline, ignoreBounds=True)
        
        self._ch_label = pg.TextItem(anchor=(0, 1), color='#e6edf3',
            fill=pg.mkBrush(13, 17, 23, 240), border=pg.mkPen('#2f81f7'))
        self._ch_label.hide()
        self._ch_label.setZValue(150)
        self.plot_widget.addItem(self._ch_label, ignoreBounds=True)
        
        # Redline (samo za ENG/INI)
        if self.engine.rev_limit and not getattr(self.engine, 'was_json', False):
            self._redline_value = self.engine.rev_limit
            self._redline_line = pg.InfiniteLine(
                pos=self.engine.rev_limit, angle=90,
                pen=pg.mkPen('#ff6b81', width=1, style=Qt.PenStyle.DashLine))
            self._redline_line.setZValue(15)
            self.plot_widget.addItem(self._redline_line)
            self._redline_hover_label = pg.TextItem(
                text=f'Redline {self.engine.rev_limit:.0f}',
                color='#ff6b81',
                anchor=(0.5, 1),
                fill=pg.mkBrush('#1a0008'),
                border=pg.mkPen('#ff6b81'))
            self._redline_hover_label.setPos(self.engine.rev_limit, 1500)
            self._redline_hover_label.setZValue(160)
            self.plot_widget.addItem(self._redline_hover_label, ignoreBounds=True)
            self._redline_hover_label.hide()
        else:
            self._redline_value = None
            self._redline_line = None
            self._redline_hover_label = None
    
    def _add_peak_markers(self, rpms, torques, powers, cmp_rpms, cmp_torques, cmp_powers, col_tq, col_pw, is_metric):
        """Dodaj peak markere POSLE rise animacije."""
        max_tq = torques.max()
        max_pw = powers.max()
        ptr = rpms[torques.argmax()]
        ppr = rpms[powers.argmax()]
        
        # Single TQ glow + marker + label
        self._peak_tq_glow = pg.ScatterPlotItem(
            [ptr], [max_tq], symbol='o', size=14,
            brush=pg.mkBrush(97, 175, 239, 100),
            pen=pg.mkPen(None))
        self._peak_tq_glow.setZValue(50)
        self.plot_widget.addItem(self._peak_tq_glow)
        
        self._peak_tq_marker = pg.ScatterPlotItem(
            [ptr], [max_tq], symbol='o', size=10,
            brush=pg.mkBrush(col_tq),
            pen=pg.mkPen('#ffffff', width=1.5))
        self._peak_tq_marker.setZValue(100)
        self.plot_widget.addItem(self._peak_tq_marker)
        
        self._peak_tq_label = pg.TextItem(
            html=f'<div style="background:rgba(15,15,25,230); padding:2px 6px; border-radius:3px; font-family:Segoe UI; font-size:9pt; color:{col_tq}; font-weight:600;">Peak Tq: <b>{max_tq:.0f}</b></div>',
            anchor=(0.5, 1.4))
        self._peak_tq_label.setPos(ptr, max_tq)
        self._peak_tq_label.setZValue(150)
        self.plot_widget.addItem(self._peak_tq_label, ignoreBounds=True)
        
        # Single PW glow + marker + label
        if is_metric:
            self._peak_pw_glow = pg.ScatterPlotItem(
                [ppr], [max_pw], symbol='o', size=14,
                brush=pg.mkBrush(91, 204, 122, 100),
                pen=pg.mkPen(None))
        else:
            self._peak_pw_glow = pg.ScatterPlotItem(
                [ppr], [max_pw], symbol='o', size=14,
                brush=pg.mkBrush(224, 108, 117, 100),
                pen=pg.mkPen(None))
        self._peak_pw_glow.setZValue(50)
        self.plot_widget.addItem(self._peak_pw_glow)
        
        self._peak_pw_marker = pg.ScatterPlotItem(
            [ppr], [max_pw], symbol='o', size=10,
            brush=pg.mkBrush(col_pw),
            pen=pg.mkPen('#ffffff', width=1.5))
        self._peak_pw_marker.setZValue(100)
        self.plot_widget.addItem(self._peak_pw_marker)
        
        self._peak_pw_label = pg.TextItem(
            html=f'<div style="background:rgba(15,15,25,230); padding:2px 6px; border-radius:3px; font-family:Segoe UI; font-size:9pt; color:{col_pw}; font-weight:600;">Peak Pw: <b>{max_pw:.0f}</b></div>',
            anchor=(0.5, 1.4))
        self._peak_pw_label.setPos(ppr, max_pw)
        self._peak_pw_label.setZValue(150)
        self.plot_widget.addItem(self._peak_pw_label, ignoreBounds=True)
        
        # Compare markeri (ako ima)
        if cmp_torques is not None and cmp_rpms is not None:
            COL_CMP_TQ = '#ffd600'
            COL_CMP_PW = '#c084fc'
            cmp_max_tq = cmp_torques.max()
            cmp_max_pw = cmp_powers.max()
            cmp_ptr = cmp_rpms[cmp_torques.argmax()]
            cmp_ppr = cmp_rpms[cmp_powers.argmax()]
            
            # Outer glow Tq (zuti)
            self._cmp_peak_tq_glow_outer = pg.ScatterPlotItem(
                [cmp_ptr], [cmp_max_tq], symbol='o', size=14,
                brush=pg.mkBrush(255, 214, 0, 60), pen=pg.mkPen(None))
            self._cmp_peak_tq_glow_outer.setZValue(40)
            self.plot_widget.addItem(self._cmp_peak_tq_glow_outer)
            
            # Outer glow Pw (ljubicasta)
            self._cmp_peak_pw_glow_outer = pg.ScatterPlotItem(
                [cmp_ppr], [cmp_max_pw], symbol='o', size=14,
                brush=pg.mkBrush(192, 132, 252, 60), pen=pg.mkPen(None))
            self._cmp_peak_pw_glow_outer.setZValue(40)
            self.plot_widget.addItem(self._cmp_peak_pw_glow_outer)
            
            # Glow Tq
            self._cmp_peak_tq_glow = pg.ScatterPlotItem(
                [cmp_ptr], [cmp_max_tq], symbol='o', size=12,
                brush=pg.mkBrush(255, 214, 0, 100), pen=pg.mkPen(None))
            self._cmp_peak_tq_glow.setZValue(45)
            self.plot_widget.addItem(self._cmp_peak_tq_glow)
            
            # Glow Pw
            self._cmp_peak_pw_glow = pg.ScatterPlotItem(
                [cmp_ppr], [cmp_max_pw], symbol='o', size=12,
                brush=pg.mkBrush(192, 132, 252, 100), pen=pg.mkPen(None))
            self._cmp_peak_pw_glow.setZValue(45)
            self.plot_widget.addItem(self._cmp_peak_pw_glow)
            
            # Marker Tq
            self._cmp_peak_tq_marker = pg.ScatterPlotItem(
                [cmp_ptr], [cmp_max_tq], symbol='o', size=9,
                brush=pg.mkBrush(COL_CMP_TQ),
                pen=pg.mkPen('#ffffff', width=1.5))
            self._cmp_peak_tq_marker.setZValue(95)
            self.plot_widget.addItem(self._cmp_peak_tq_marker)
            
            # Marker Pw
            self._cmp_peak_pw_marker = pg.ScatterPlotItem(
                [cmp_ppr], [cmp_max_pw], symbol='o', size=9,
                brush=pg.mkBrush(COL_CMP_PW),
                pen=pg.mkPen('#ffffff', width=1.5))
            self._cmp_peak_pw_marker.setZValue(95)
            self.plot_widget.addItem(self._cmp_peak_pw_marker)
            
            # Compare labeli (ispod markera)
            self._cmp_tq_label = pg.TextItem(
                html=f'<div style="background:rgba(15,15,25,230); padding:2px 6px; border-radius:3px; font-family:Segoe UI; font-size:9pt; color:#ffd600; font-weight:600;">Cmp Tq: <b>{cmp_max_tq:.0f}</b></div>',
                anchor=(0.5, -0.4))
            self._cmp_tq_label.setPos(cmp_ptr, cmp_max_tq)
            self._cmp_tq_label.setZValue(150)
            self.plot_widget.addItem(self._cmp_tq_label, ignoreBounds=True)
            
            self._cmp_pw_label = pg.TextItem(
                html=f'<div style="background:rgba(15,15,25,230); padding:2px 6px; border-radius:3px; font-family:Segoe UI; font-size:9pt; color:#c084fc; font-weight:600;">Cmp Pw: <b>{cmp_max_pw:.0f}</b></div>',
                anchor=(0.5, -0.4))
            self._cmp_pw_label.setPos(cmp_ppr, cmp_max_pw)
            self._cmp_pw_label.setZValue(150)
            self.plot_widget.addItem(self._cmp_pw_label, ignoreBounds=True)
    
    def _show_intro_text(self):
        """Prikazi intro text kad nema podataka."""
        intro = pg.TextItem(
            text='Open an .eng / .ini / .json file',
            color='#7d8590', anchor=(0.5, 0.5))
        intro.setPos(12000, 800)
        self.plot_widget.addItem(intro)


    def _on_mouse_leave(self, _=None):
        """Sakrij crosshair kad mis napusti plot."""
        if self._ch_vline:
            self._ch_vline.hide()
        if self._ch_label:
            self._ch_label.hide()
        if hasattr(self, '_redline_hover_label') and self._redline_hover_label:
            self._redline_hover_label.hide()

    def _on_mouse_moved(self, scene_pos):
        if not self.engine.torque_data or self._ch_vline is None:
            return
        if not self.plot_widget.plotItem.vb.sceneBoundingRect().contains(scene_pos):
            self._on_mouse_leave()
            return

        mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(scene_pos)
        x = mouse_point.x()
        is_metric = self.current_units == 'metric'
        # Use cached arrays — no allocation on every mouse event
        if self._cache_rpms is None or self._cache_units != self.current_units:
            return
        rpms    = self._cache_rpms
        torques = self._cache_torques
        powers  = self._cache_powers
        t_l = "Nm" if is_metric else "lb-ft"
        p_l = "kW" if is_metric else "HP"

        if rpms[0] <= x <= rpms[-1]:
            tq_i = float(np.interp(x, rpms, torques))
            pw_i = float(np.interp(x, rpms, powers))
            self._ch_vline.setPos(x)
            self._ch_vline.show()

            # Provjeri blizinu svih peak markera (main + compare), 300 RPM tolerancija
            TOLS = 300
            label_text = None

            # Main TQ peak
            try:
                d = self._peak_tq_marker.getData()
                if d[0] is not None and len(d[0]) > 0 and abs(x - d[0][0]) < TOLS:
                    label_text = f"★ PEAK TORQUE\nRPM: {x:.0f}\nTq:  {tq_i:.1f} {t_l}\nPw:  {pw_i:.1f} {p_l}"
            except Exception:
                pass

            # Main PW peak
            if label_text is None:
                try:
                    d = self._peak_pw_marker.getData()
                    if d[0] is not None and len(d[0]) > 0 and abs(x - d[0][0]) < TOLS:
                        label_text = f"★ PEAK POWER\nRPM: {x:.0f}\nTq:  {tq_i:.1f} {t_l}\nPw:  {pw_i:.1f} {p_l}"
                except Exception:
                    pass

            # Compare TQ peak
            if label_text is None and self.compare_engine and self.compare_engine.torque_data:
                try:
                    d = self._cmp_peak_tq_marker.getData()
                    if d[0] is not None and len(d[0]) > 0 and abs(x - d[0][0]) < TOLS:
                        cmp_is_metric = is_metric
                        cmp_tqs = np.array([p['torque_nm'] if cmp_is_metric else p['torque_lbft']
                                            for p in self.compare_engine.torque_data])
                        cmp_pws = np.array([p['power_kw'] if cmp_is_metric else p['power_hp']
                                            for p in self.compare_engine.torque_data])
                        cmp_rpms = np.array([p['rpm'] for p in self.compare_engine.torque_data])
                        cmp_tq_i = float(np.interp(x, cmp_rpms, cmp_tqs))
                        cmp_pw_i = float(np.interp(x, cmp_rpms, cmp_pws))
                        label_text = f"★ CMP PEAK TORQUE\nRPM: {x:.0f}\nTq:  {cmp_tq_i:.1f} {t_l}\nPw:  {cmp_pw_i:.1f} {p_l}"
                except Exception:
                    pass

            # Compare PW peak
            if label_text is None and self.compare_engine and self.compare_engine.torque_data:
                try:
                    d = self._cmp_peak_pw_marker.getData()
                    if d[0] is not None and len(d[0]) > 0 and abs(x - d[0][0]) < TOLS:
                        cmp_is_metric = is_metric
                        cmp_tqs = np.array([p['torque_nm'] if cmp_is_metric else p['torque_lbft']
                                            for p in self.compare_engine.torque_data])
                        cmp_pws = np.array([p['power_kw'] if cmp_is_metric else p['power_hp']
                                            for p in self.compare_engine.torque_data])
                        cmp_rpms = np.array([p['rpm'] for p in self.compare_engine.torque_data])
                        cmp_tq_i = float(np.interp(x, cmp_rpms, cmp_tqs))
                        cmp_pw_i = float(np.interp(x, cmp_rpms, cmp_pws))
                        label_text = f"★ CMP PEAK POWER\nRPM: {x:.0f}\nTq:  {cmp_tq_i:.1f} {t_l}\nPw:  {cmp_pw_i:.1f} {p_l}"
                except Exception:
                    pass

            if label_text is None:
                label_text = f"RPM: {x:.0f}\nTq:  {tq_i:.1f} {t_l}\nPw:  {pw_i:.1f} {p_l}"

            self._ch_label.setText(label_text)
            self._ch_label.setPos(x, 1500)
            self._ch_label.show()
        else:
            self._ch_vline.hide()
            self._ch_label.hide()

        # Redline hover
        if hasattr(self, '_redline_hover_label') and self._redline_hover_label \
           and hasattr(self, '_redline_value') and self._redline_value:
            if abs(x - self._redline_value) < 500:
                self._redline_hover_label.show()
            else:
                self._redline_hover_label.hide()

    def _refresh_table(self):
        """Render tabele bez animacije, sa header bojama prema units."""
        from PyQt6.QtGui import QColor
        is_metric = self.current_units == 'metric'
        t_l = "Nm" if is_metric else "lb-ft"
        p_l = "kW" if is_metric else "HP"
        col_pw_hdr = '#5bcc7a' if is_metric else '#e06c75'
        col_tq_hdr = '#61afef'

        # Compression kolona vidljiva samo za ENG/INI
        # (JSON nema compression — uvijek 0.00, bespotrebna kolona)
        main_is_json  = getattr(self.engine, 'was_json', False)
        cmp_is_json   = getattr(self.compare_engine, 'was_json', False) \
                        if self.compare_engine else True
        show_compr = (not main_is_json) and (not cmp_is_json)
        if show_compr:
            self.table.showColumn(1)
        else:
            self.table.hideColumn(1)

        self.table.setHorizontalHeaderLabels(
            ['RPM', 'Compr.', f'Torque ({t_l})', f'Power ({p_l})', '% Peak', ''])

        # Update header colours whenever units change
        if hasattr(self, '_colored_header'):
            self._colored_header.set_unit_colors(col_tq_hdr, col_pw_hdr)

        d = self.engine.torque_data
        self.points_label.setText(f'{len(d)} pts')
        self.table.setRowCount(len(d))
        if not d:
            return

        pws = [p['power_kw'] if is_metric else p['power_hp'] for p in d]
        tqs = [p['torque_nm'] if is_metric else p['torque_lbft'] for p in d]
        rpms = [p['rpm'] for p in d]
        max_pw = max(pws) if pws else 1
        max_tq = max((v for v in tqs if v > 0), default=1)
        min_rpm = min(rpms) if rpms else 0
        max_rpm = max(rpms) if rpms else 1
        peak_pw_row = pws.index(max(pws)) if pws else -1

        # Compare delta — samo kada je compare aktivan
        has_cmp = (self.compare_engine is not None and
                   bool(getattr(self.compare_engine, 'torque_data', None)))
        delta_map = {}
        if has_cmp:
            cmp_d = self.compare_engine.torque_data
            cmp_rpms = [p['rpm'] for p in cmp_d]
            cmp_pws  = [p['power_kw'] if is_metric else p['power_hp'] for p in cmp_d]
            def _interp_cmp(rpm):
                if not cmp_rpms: return 0.0
                if rpm <= cmp_rpms[0]:  return cmp_pws[0]
                if rpm >= cmp_rpms[-1]: return cmp_pws[-1]
                for j in range(len(cmp_rpms) - 1):
                    if cmp_rpms[j] <= rpm <= cmp_rpms[j+1]:
                        t = (rpm - cmp_rpms[j]) / max(cmp_rpms[j+1] - cmp_rpms[j], 0.001)
                        return cmp_pws[j] + t * (cmp_pws[j+1] - cmp_pws[j])
                return 0.0
            for i, p in enumerate(d):
                main_pw = p['power_kw'] if is_metric else p['power_hp']
                delta_map[i] = main_pw - _interp_cmp(p['rpm'])
            # Pokazi delta kolonu i azuriraj header
            p_l2 = "kW" if is_metric else "HP"
            self.table.showColumn(5)
            self.table.setHorizontalHeaderLabels(
                ['RPM', 'Compr.', f'Torque ({t_l})', f'Power ({p_l})', '% Peak', f'Δ {p_l2}'])
            if not show_compr:
                self.table.hideColumn(1)
            if hasattr(self, '_colored_header'):
                self._colored_header._col_colors[5] = '#a8e6a3'
                self._colored_header.viewport().update()
        else:
            self.table.hideColumn(5)

        # Row height
        self.table.verticalHeader().setDefaultSectionSize(34)

        if not hasattr(self, '_cell_bar_delegate'):
            from PyQt6.QtWidgets import QStyledItemDelegate, QStyle
            from PyQt6.QtGui import QColor as QC, QLinearGradient, QBrush
            from PyQt6.QtCore import Qt as QtC, QRect

            class CellBarDelegate(QStyledItemDelegate):
                def __init__(self):
                    super().__init__()
                    self.max_tq = 1.0
                    self.max_pw = 1.0
                    self.is_metric = False
                    self.peak_pw_row = -1
                    self.min_rpm = 0.0
                    self.max_rpm = 1.0
                    self.delta_map = {}   # {row_index: delta_hp}
                    self.has_compare = False

                def paint(self, painter, option, index):
                    from PyQt6.QtWidgets import QStyle
                    from PyQt6.QtGui import QColor as QC, QLinearGradient, QBrush
                    from PyQt6.QtCore import Qt as QtC, QRect

                    col = index.column()
                    row = index.row()
                    rect = option.rect
                    selected = bool(option.state & QStyle.StateFlag.State_Selected)
                    is_peak_row = (row == self.peak_pw_row)

                    painter.save()

                    # Row background — sa delta tintom kada je compare aktivan
                    if selected:
                        painter.fillRect(rect, QC('#2f81f7'))
                    elif is_peak_row:
                        painter.fillRect(rect, QC('#1c1600'))
                    else:
                        base_c = QC('#1a1f2e') if row % 2 == 0 else QC('#12151e')
                        painter.fillRect(rect, base_c)
                        if self.has_compare and row in self.delta_map:
                            dv = self.delta_map[row]
                            if dv > 0.5:
                                tint = QC(20, 90, 30, 38)   # zeleni overlay
                            elif dv < -0.5:
                                tint = QC(100, 18, 18, 38)  # crveni overlay
                            else:
                                tint = None
                            if tint:
                                painter.fillRect(rect, QBrush(tint))

                    # Torque gradient bar (bottom strip)
                    if col == 2 and not selected:
                        try:
                            val = float(index.data(QtC.ItemDataRole.DisplayRole) or 0)
                        except Exception:
                            val = 0.0
                        if val > 0 and self.max_tq > 0:
                            ratio = min(val / self.max_tq, 1.0)
                            bar_w = int((rect.width() - 6) * ratio)
                            if bar_w > 2:
                                bar_rect = QRect(rect.left() + 3,
                                                 rect.bottom() - 5,
                                                 bar_w, 4)
                                grad = QLinearGradient(bar_rect.left(), 0, bar_rect.right(), 0)
                                grad.setColorAt(0.0, QC('#0d3358'))
                                grad.setColorAt(0.55, QC('#1a6299'))
                                grad.setColorAt(1.0, QC('#61afef'))
                                painter.fillRect(bar_rect, QBrush(grad))

                    # Power gradient bar (bottom strip)
                    elif col == 3 and not selected:
                        try:
                            val = float(index.data(QtC.ItemDataRole.DisplayRole) or 0)
                        except Exception:
                            val = 0.0
                        if val > 0 and self.max_pw > 0:
                            ratio = min(val / self.max_pw, 1.0)
                            bar_w = int((rect.width() - 6) * ratio)
                            if bar_w > 2:
                                bar_rect = QRect(rect.left() + 3,
                                                 rect.bottom() - 5,
                                                 bar_w, 4)
                                grad = QLinearGradient(bar_rect.left(), 0, bar_rect.right(), 0)
                                if self.is_metric:
                                    grad.setColorAt(0.0, QC('#0a2e14'))
                                    grad.setColorAt(0.55, QC('#165c28'))
                                    grad.setColorAt(1.0, QC('#5bcc7a'))
                                else:
                                    grad.setColorAt(0.0, QC('#2e0a0e'))
                                    grad.setColorAt(0.55, QC('#761520'))
                                    grad.setColorAt(1.0, QC('#e06c75'))
                                painter.fillRect(bar_rect, QBrush(grad))

                    # % Peak heat bar (bottom strip, col 4)
                    elif col == 4 and not selected:
                        try:
                            text = str(index.data(QtC.ItemDataRole.DisplayRole) or '0')
                            val = float(text.replace('%', '').strip())
                        except Exception:
                            val = 0.0
                        ratio = min(val / 100.0, 1.0)
                        bar_w = int((rect.width() - 6) * ratio)
                        if bar_w > 1:
                            bar_rect = QRect(rect.left() + 3,
                                             rect.bottom() - 5,
                                             bar_w, 4)
                            if val >= 95:
                                bar_c = QC('#f85149')
                            elif val >= 75:
                                bar_c = QC('#d29922')
                            elif val >= 40:
                                bar_c = QC('#2f81f7')
                            else:
                                bar_c = QC('#2a3050')
                            painter.fillRect(bar_rect, bar_c)

                    # RPM kolona — delta traka (10px) kad compare aktivan, inace heat stripe (3px)
                    elif col == 0 and not selected:
                        if self.has_compare and row in self.delta_map:
                            dv = self.delta_map[row]
                            if dv > 0.5:
                                stripe_c = QC('#3fb950')   # zelena = jaci
                            elif dv < -0.5:
                                stripe_c = QC('#f85149')   # crvena = slabiji
                            else:
                                stripe_c = QC('#7d8590')   # siva = isti
                            painter.fillRect(QRect(rect.left(), rect.top(), 10, rect.height()), stripe_c)
                        else:
                            rpm_range = max(self.max_rpm - self.min_rpm, 1.0)
                            try:
                                rpm_val = float(index.data(QtC.ItemDataRole.DisplayRole) or 0)
                            except Exception:
                                rpm_val = self.min_rpm
                            t = min(max((rpm_val - self.min_rpm) / rpm_range, 0.0), 1.0)
                            if t < 0.33:
                                stripe_c = QC('#1a4a70')
                            elif t < 0.66:
                                stripe_c = QC('#7a5500')
                            else:
                                stripe_c = QC('#7a1e1e')
                            painter.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), stripe_c)

                    # Peak row: gold right-edge accent
                    if is_peak_row and not selected:
                        painter.fillRect(
                            QRect(rect.right() - 2, rect.top(), 2, rect.height()),
                            QC('#ffd600'))

                    # Row separator
                    if not selected:
                        painter.setPen(QC('#1e2438'))
                        painter.drawLine(rect.left(), rect.bottom(),
                                         rect.right(), rect.bottom())

                    painter.restore()
                    super().paint(painter, option, index)

            self._cell_bar_delegate = CellBarDelegate()
            self.table.setItemDelegate(self._cell_bar_delegate)

        # Update delegate data
        self._cell_bar_delegate.max_tq = max_tq
        self._cell_bar_delegate.max_pw = max_pw
        self._cell_bar_delegate.is_metric = is_metric
        self._cell_bar_delegate.peak_pw_row = peak_pw_row
        self._cell_bar_delegate.min_rpm = min_rpm
        self._cell_bar_delegate.max_rpm = max_rpm
        self._cell_bar_delegate.delta_map = delta_map
        self._cell_bar_delegate.has_compare = has_cmp
        rpm_range = max(max_rpm - min_rpm, 1.0)

        for i, p in enumerate(d):
            tq = p['torque_nm'] if is_metric else p['torque_lbft']
            pw = p['power_kw'] if is_metric else p['power_hp']
            pct = (pw / max_pw * 100) if max_pw > 0 else 0
            is_peak = (i == peak_pw_row)

            # RPM heat colour
            rpm_t = min(max((p['rpm'] - min_rpm) / rpm_range, 0.0), 1.0)
            if rpm_t < 0.33:
                rpm_col = '#61afef'
            elif rpm_t < 0.66:
                rpm_col = '#d29922'
            else:
                rpm_col = '#f08070'

            items = [
                QTableWidgetItem(f'{p["rpm"]:.0f}'),
                QTableWidgetItem(f'{p["compression"]:.2f}'),
                QTableWidgetItem(f'{tq:.1f}'),
                QTableWidgetItem(f'{pw:.1f}'),
                QTableWidgetItem(f'{pct:.0f}%'),
            ]
            for j, it in enumerate(items):
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if j == 0:
                    it.setForeground(QColor('#ffffff'))
                    if is_peak:
                        font = QFont('Consolas', 13); font.setBold(True); it.setFont(font)
                elif j == 1:
                    it.setForeground(QColor('#ffffff'))
                elif j == 2:
                    it.setForeground(QColor(self.COL_TQ))
                    if is_peak:
                        font = QFont('Consolas', 13); font.setBold(True); it.setFont(font)
                elif j == 3:
                    if is_peak:
                        it.setForeground(QColor('#f85149' if not is_metric else '#5bcc7a'))
                        font = QFont('Consolas', 14); font.setBold(True); it.setFont(font)
                    else:
                        it.setForeground(QColor(col_pw_hdr))
                elif j == 4:
                    if pct >= 95:
                        it.setForeground(QColor('#f85149'))
                        font = QFont('Consolas', 13); font.setBold(True); it.setFont(font)
                    elif pct >= 75:
                        it.setForeground(QColor('#d29922'))
                    elif pct >= 40:
                        it.setForeground(QColor('#2f81f7'))
                    else:
                        it.setForeground(QColor('#3a4560'))
                self.table.setItem(i, j, it)

            # Delta kolona (col 5) — vidljiva samo kad je compare aktivan
            if has_cmp and i in delta_map:
                dv = delta_map[i]
                delta_it = QTableWidgetItem(f'{dv:+.1f}')
                delta_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                font_d = QFont('Consolas', 11)
                font_d.setBold(True)
                delta_it.setFont(font_d)
                if dv > 0.5:
                    delta_it.setForeground(QColor('#4ec760'))   # zelena
                elif dv < -0.5:
                    delta_it.setForeground(QColor('#f85149'))   # crvena
                else:
                    delta_it.setForeground(QColor('#7d8590'))   # siva ≈ isti
                self.table.setItem(i, 5, delta_it)
            else:
                self.table.setItem(i, 5, QTableWidgetItem(''))

        # Forsiraj repaint — delegate ima nove podatke ali Qt ne zna
        # da treba precrtat vec nacrtane celije (kockice, piramide)
        self.table.viewport().update()


    def _update_vehicle_panel(self, data):
        import re as _re
        if not isinstance(data, dict):
            self.veh_name_lbl.setText('')
            self.veh_specs_lbl.setText('')
            self.veh_brand_lbl.setText('')
            return
        name  = data.get('name', '') or data.get('carName', '')
        brand = data.get('brand', '')
        specs = data.get('specs', {})
        self.veh_name_lbl.setText(str(name) if name else '')
        self.veh_brand_lbl.setText(str(brand) if brand else '')

        if isinstance(specs, dict):
            def extract_number(v):
                s = str(v).strip()
                m = _re.match(r'^\s*(-?\d+\.?\d*)', s)
                return m.group(1) if m else s

            def fmt_val(k, v):
                kl = str(k).lower().strip()
                if 'bhp' in kl or kl == 'hp' or kl == 'power':
                    label, unit = 'bhp', 'BHP'
                elif 'torque' in kl or kl == 'tq':
                    label, unit = 'torque', 'Nm'
                elif 'weight' in kl or 'mass' in kl:
                    label, unit = 'weight', 'kg'
                elif 'topspeed' in kl or 'top_speed' in kl or 'maxspeed' in kl:
                    label, unit = 'topspeed', 'km/h'
                elif 'accel' in kl or '0_100' in kl or '0-100' in kl:
                    label, unit = 'acceleration', 's'
                elif 'pwratio' in kl or 'power_ratio' in kl or 'powerweight' in kl:
                    label, unit = 'pwratio', 'kg/BHP'
                else:
                    label = str(k).replace('_', ' ').lower()
                    unit = ''
                clean_num = extract_number(v)
                val_str = f'{clean_num}{unit}' if unit else clean_num
                return (f'<span style="color:#e6edf3;">{label}:</span>'
                        f'&nbsp;<span style="color:#61afef;font-weight:600;">{val_str}</span>')

            parts = []
            for k, v in list(specs.items())[:6]:
                if isinstance(v, (str, int, float)):
                    parts.append(fmt_val(k, v))

            sep = '&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'
            if len(parts) > 3:
                html = sep.join(parts[:3]) + '<br>' + sep.join(parts[3:])
            else:
                html = sep.join(parts)

            self.veh_specs_lbl.setText(html)
        else:
            self.veh_specs_lbl.setText('')


    # ===== ENGINE PARAMS (ISI only) =====
    def _parse_eng_params(self):
        values = {}
        for item in self.engine.file_structure:
            if item is None:
                continue
            line = item.strip()
            if not line or line.startswith('//') or line.startswith(';') or '=' not in line:
                continue
            key, _, rest = line.partition('=')
            key = key.strip()
            val_str = rest.split('//')[0].strip()
            values[key] = val_str
        return values

    def _format_value(self, val_str, typ):
        val_str = val_str.strip()
        if typ in ('scalar', 'int'):
            return [val_str]
        inner = val_str.strip('()')
        return [p.strip() for p in inner.split(',')]

    def _save_eng_param(self, key, typ, parts):
        new_val = parts[0].strip() if typ in ('scalar', 'int') \
                  else '(' + ', '.join(p.strip() for p in parts) + ')'
        for i, item in enumerate(self.engine.file_structure):
            if item is None:
                continue
            stripped = item.strip()
            if not stripped or '=' not in stripped:
                continue
            k = stripped.split('=')[0].strip()
            if k == key:
                leading = item[:len(item) - len(item.lstrip())]
                if '//' in item:
                    comment_pos = item.index('//')
                    comment_text = item[comment_pos:].rstrip('\r\n')
                    new_line = leading + key + '=' + new_val
                    pad = comment_pos - len(new_line)
                    if pad < 2: pad = 2
                    new_line += ' ' * pad + comment_text + '\n'
                else:
                    new_line = leading + key + '=' + new_val + '\n'
                self.engine.file_structure[i] = new_line
                return True
        return False

    def edit_engine_params(self):
        if not self.engine.torque_data or self.engine.was_json:
            return
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                                      QScrollArea, QWidget, QLabel, QLineEdit,
                                      QPushButton, QFrame)
        from PyQt6.QtCore import Qt, QTimer

        # Samo za ISI .eng / .ini fajlove — JSON asseti nemaju ove parametre
        if getattr(self.engine, 'was_json', False):
            from PyQt6.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setWindowTitle('Engine Parameters')
            msg.setText('Engine Parameters nije dostupan za JSON assete.\n\n'
                        'Ova funkcija radi samo sa ISI .eng / .ini fajlovima.')
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setStyleSheet('QMessageBox { background: #0a0a12; color: #e6edf3; }'
                              'QLabel { color: #e6edf3; font-size: 11px; }'
                              'QPushButton { background: #21262d; border: 1px solid #30363d; '
                              'border-radius: 4px; color: #e6edf3; padding: 6px 18px; }')
            msg.exec()
            return

        raw_values = self._parse_eng_params()
        param_map  = {p[0]: p for p in self.ENG_PARAMS}

        SECTIONS = [
            [('RevLimitLogic','RevLimitAvailable'),
             ('RevLimitRange','RevLimitSetting'),
             ('EngineMapRange','EngineMapSetting'),
             ('EngineBrakingMapRange','EngineBrakingMapSetting')],
            [('EngineSpeedHeat','EngineInertia'),
             ('IdleRPMLogic','IdleThrottle'),
             ('OilWaterHeatTransfer','OilMinimumCooling'),
             ('OptimumOilTemp','CombustionHeat'),
             ('WaterMinimumCooling','RadiatorCooling')],
            [('LifetimeEngineRPM','LifetimeAvg'),
             ('LifetimeOilTemp','LifetimeVar'),
             ('EngineEmission', None),
             ('EngineSound', None),
             ('StarterTiming', None)],
            [('LaunchRPMLogic','LaunchEfficiency'),
             ('SpeedLimiter','OnboardStarter'),
             ('FuelConsumption','FuelEstimate')],
            [('EngineBoostRange','EngineBoostSetting'),
             ('BoostEffects', None),
             ('BoostTorque','BoostPower')],
        ]

        def get_parts(key):
            p = param_map.get(key)
            if not p: return ('scalar', ['0'])
            typ = p[2]
            raw = raw_values.get(key, '')
            if raw:
                parts = self._format_value(raw, typ)
            else:
                parts = ['0'] if typ in ('scalar','int') else \
                        ['0','0'] if typ == 'tuple2' else ['0','0','0']
            return (typ, parts)

        # Fiksne sirine za savrsenu poravnanost
        LABEL_W = 160       # sirina labele
        INPUT_BOX_W = 240   # sirina celog input containera (uvek isto)

        dlg = QDialog(self)
        dlg.setWindowTitle('Edit Engine Parameters')
        dlg.resize(900, 820)
        dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dlg.setStyleSheet("""
            QDialog { background: #0a0a12; color: #e6edf3;
                      border: 1px solid #ff6b81; border-radius: 6px; }
            QLabel  { color: #8a90aa; font-size: 11px; }
            QLabel#secTitle { color: #ff6b81; font-weight: 700; font-size: 11px;
                              border-bottom: 1px solid #2a2a3e; padding-bottom: 4px; }
            QLineEdit { background: #08080e; border: 1px solid #2a2a3e; border-radius: 3px;
                        color: #00ff88; font-family: Consolas; font-size: 11px;
                        padding: 4px 6px; }
            QLineEdit:focus { border-color: #ff6b81; }
            QPushButton { background: #21262d; border: 1px solid #30363d;
                          border-radius: 4px; color: #e6edf3; padding: 6px 18px; font-weight: 600; }
            QPushButton:hover { background: #30363d; }
            QPushButton#okBtn { background: #ff6b81; color: #fff; border-color: #ff6b81; }
            QPushButton#okBtn:hover { background: #c45b6a; }
        """)

        outer_v = QVBoxLayout(dlg)
        outer_v.setContentsMargins(0, 0, 0, 0)
        outer_v.setSpacing(0)

        # Header
        hdr = QFrame(); hdr.setStyleSheet('background: #ff6b81;'); hdr.setFixedHeight(3)
        outer_v.addWidget(hdr)
        hdr2 = QWidget(); hdr2.setStyleSheet('background: #0a0a12;')
        hdr2_l = QHBoxLayout(hdr2); hdr2_l.setContentsMargins(12, 8, 12, 8)
        # Gear icon
        gear_lbl = QLabel()
        gear_lbl.setPixmap(qta.icon('fa5s.cog', color='#ff6b81').pixmap(18, 18))
        gear_lbl.setStyleSheet('background: transparent;')
        hdr2_l.addWidget(gear_lbl)
        # Title + subtitle stacked vertically
        titles_w = QWidget(); titles_w.setStyleSheet('background: transparent;')
        titles_v = QVBoxLayout(titles_w); titles_v.setContentsMargins(6, 0, 0, 0); titles_v.setSpacing(1)
        t1 = QLabel('EDIT ENGINE PARAMETERS')
        t1.setStyleSheet('color: #e6edf3; font-size: 12px; font-weight: 700; background: transparent;')
        t2 = QLabel('RFACTOR / ISI POWERTRAIN CONFIGURATION')
        t2.setStyleSheet('color: #7d8590; font-size: 9px; background: transparent; letter-spacing: 1px;')
        titles_v.addWidget(t1); titles_v.addWidget(t2)
        hdr2_l.addWidget(titles_w)
        hdr2_l.addStretch()
        # Red X close button
        btn_x = QPushButton('✕')
        btn_x.setFixedSize(28, 28)
        btn_x.setStyleSheet(
            'QPushButton { background: #3a1015; border: 1px solid #5a2030; border-radius: 4px; '
            'color: #ff6b81; font-size: 14px; font-weight: 700; }'
            'QPushButton:hover { background: #ff6b81; color: #fff; border-color: #ff6b81; }')
        btn_x.clicked.connect(dlg.reject)
        hdr2_l.addWidget(btn_x)

        # Drag-to-move (needed because frameless window)
        _dp = [None]
        def _hdr_press(ev):
            if ev.button() == Qt.MouseButton.LeftButton:
                _dp[0] = ev.globalPosition().toPoint() - dlg.frameGeometry().topLeft()
        def _hdr_move(ev):
            if ev.buttons() == Qt.MouseButton.LeftButton and _dp[0] is not None:
                dlg.move(ev.globalPosition().toPoint() - _dp[0])
        def _hdr_release(ev):
            _dp[0] = None
        hdr2.mousePressEvent   = _hdr_press
        hdr2.mouseMoveEvent    = _hdr_move
        hdr2.mouseReleaseEvent = _hdr_release

        outer_v.addWidget(hdr2)
        div = QFrame(); div.setFixedHeight(1); div.setStyleSheet('background: #2a2a3e;')
        outer_v.addWidget(div)

        # Scrollable body
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet('QScrollArea { border: none; background: #0a0a0f; }')
        body = QWidget(); body.setStyleSheet('background: #0a0a0f;')
        body_v = QVBoxLayout(body); body_v.setContentsMargins(20, 10, 20, 10); body_v.setSpacing(0)
        scroll.setWidget(body)
        outer_v.addWidget(scroll, stretch=1)

        entries = {}

        SEC_TITLES = ['Rev / Map Limiters', 'Thermals', 'Durability & Effects',
                      'Launch & Fuel', 'Boost']

        def make_input_box(typ, parts):
            """Vrati QWidget fiksne sirine INPUT_BOX_W sa 1/2/3 inputa unutra."""
            box = QWidget()
            box.setFixedWidth(INPUT_BOX_W)
            box.setStyleSheet('background: transparent;')
            bl = QHBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(4)
            n = 3 if typ == 'tuple3' else 2 if typ == 'tuple2' else 1
            # Sirina svakog inputa: (BOX_W - spacings) / n
            spacing_total = 4 * (n - 1)
            input_w = (INPUT_BOX_W - spacing_total) // n
            edits = []
            for vi in range(n):
                le = QLineEdit(parts[vi] if vi < len(parts) else '0')
                le.setFixedWidth(input_w)
                le.setAlignment(Qt.AlignmentFlag.AlignCenter)
                bl.addWidget(le)
                edits.append(le)
            return box, edits

        for si, section_rows in enumerate(SECTIONS):
            sec_title = QLabel(SEC_TITLES[si])
            sec_title.setObjectName('secTitle')
            body_v.addWidget(sec_title)
            body_v.addSpacing(6)

            # Svaki red ima 4 kolone: Label1 | Input1 | Label2 | Input2
            for left_key, right_key in section_rows:
                row = QWidget(); row.setStyleSheet('background: transparent;')
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(10)

                # LIJEVA polovina
                for key in (left_key,):
                    if not key:
                        # Prazno mjesto - drzi sirinu
                        spacer = QWidget()
                        spacer.setFixedWidth(LABEL_W + INPUT_BOX_W + 8)
                        rl.addWidget(spacer)
                        continue
                    p = param_map.get(key)
                    if not p: continue
                    typ, parts = get_parts(key)
                    lbl = QLabel(p[1] + ':')
                    lbl.setFixedWidth(LABEL_W)
                    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    lbl.setStyleSheet('color: #8a90aa; font-size: 10px; background: transparent;')
                    rl.addWidget(lbl)
                    box, edits = make_input_box(typ, parts)
                    rl.addWidget(box)
                    entries[key] = (typ, edits)

                # Razmak izmedju lijeve i desne strane
                rl.addSpacing(20)

                # DESNA polovina
                for key in (right_key,):
                    if not key:
                        spacer = QWidget()
                        spacer.setFixedWidth(LABEL_W + INPUT_BOX_W + 8)
                        rl.addWidget(spacer)
                        continue
                    p = param_map.get(key)
                    if not p: continue
                    typ, parts = get_parts(key)
                    lbl = QLabel(p[1] + ':')
                    lbl.setFixedWidth(LABEL_W)
                    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    lbl.setStyleSheet('color: #8a90aa; font-size: 10px; background: transparent;')
                    rl.addWidget(lbl)
                    box, edits = make_input_box(typ, parts)
                    rl.addWidget(box)
                    entries[key] = (typ, edits)

                rl.addStretch()
                body_v.addWidget(row)
                body_v.addSpacing(4)

            if si < len(SECTIONS) - 1:
                body_v.addSpacing(8)
                sep = QFrame(); sep.setFixedHeight(1)
                sep.setStyleSheet('background: #2a2a3e;')
                body_v.addWidget(sep)
                body_v.addSpacing(8)

        body_v.addStretch()

        # Footer
        div2 = QFrame(); div2.setFixedHeight(1); div2.setStyleSheet('background: #2a2a3e;')
        outer_v.addWidget(div2)
        foot = QWidget(); foot.setStyleSheet('background: #0a0a12; padding: 6px;')
        foot_h = QHBoxLayout(foot); foot_h.setContentsMargins(16, 8, 16, 8)
        foot_h.addStretch()
        btn_cancel = QPushButton('Cancel'); btn_cancel.clicked.connect(dlg.reject)
        btn_ok = QPushButton('Apply'); btn_ok.setObjectName('okBtn')

        def apply():
            for key, (typ, vars_list) in entries.items():
                parts = [le.text() for le in vars_list]
                if any(p.strip() for p in parts):
                    self._save_eng_param(key, typ, parts)
            dlg.accept()
            self._set_status('Engine parameters updated — save file to write to disk.', '#d29922')
            self._show_toast('✓  Engine params updated', '#d29922')

        btn_ok.clicked.connect(apply)
        foot_h.addWidget(btn_cancel); foot_h.addWidget(btn_ok)
        outer_v.addWidget(foot)

        dlg.exec()
if __name__ == '__main__':
    app = QApplication(sys.argv)
    font = app.font()
    if font.pointSize() <= 0:
        font.setPointSize(9)
    app.setFont(font)
    win = EngineTunerV10()
    win.show()
    print("=" * 60)
    print(f"{APP_NAME} Started")
    print(f"PyQt6: {__import__('PyQt6.QtCore', fromlist=['QT_VERSION_STR']).QT_VERSION_STR}")
    print(f"pyqtgraph: {pg.__version__}")
    print(f"qtawesome: {qta.__version__}")
    print("=" * 60)
    sys.exit(app.exec())