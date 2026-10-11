"""Colours and Qt stylesheet (light, Fusion-like by default; dark available)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Theme:
    light: bool = True
    bg_top: tuple = (0.78, 0.82, 0.88)
    bg_bottom: tuple = (0.97, 0.975, 0.985)
    grid: tuple = (0.45, 0.50, 0.58)
    edge: tuple = (0.10, 0.10, 0.12)
    hover: tuple = (0.20, 0.55, 1.00)
    select: tuple = (0.05, 0.45, 0.95)
    sk_free: tuple = (0.10, 0.40, 0.90)
    sk_constrained: tuple = (0.05, 0.05, 0.07)
    sk_inactive: tuple = (0.30, 0.35, 0.45)
    sk_construction: tuple = (0.95, 0.55, 0.10)
    sk_selected: tuple = (0.10, 0.75, 1.00)
    sk_origin: tuple = (0.85, 0.20, 0.20)
    profile: tuple = (1.00, 0.70, 0.40)
    profile_sel: tuple = (0.30, 0.60, 1.00)
    construct: tuple = (0.95, 0.65, 0.20)
    axis_x: tuple = (0.85, 0.20, 0.20)
    axis_y: tuple = (0.20, 0.70, 0.25)
    axis_z: tuple = (0.20, 0.40, 0.90)
    text: tuple = (0.20, 0.22, 0.26)
    dim_text: tuple = (0.10, 0.12, 0.16)
    dim_line: tuple = (0.35, 0.38, 0.45)
    glyph: tuple = (0.15, 0.20, 0.35)
    plane_colors: dict = field(default_factory=lambda: {"XY": (0.30, 0.45, 0.95), "XZ": (0.30, 0.75, 0.35),
                                                        "YZ": (0.90, 0.35, 0.30)})


THEME = Theme()


def apply_dark():
    t = THEME
    t.light = False
    t.bg_top, t.bg_bottom = (0.30, 0.32, 0.36), (0.13, 0.14, 0.16)
    t.grid = (0.60, 0.65, 0.72)
    t.edge = (0.02, 0.02, 0.03)
    t.sk_constrained = (0.92, 0.93, 0.95)
    t.sk_free = (0.35, 0.65, 1.00)
    t.text = (0.85, 0.87, 0.90)
    t.dim_text = (0.92, 0.94, 0.97)
    t.glyph = (0.80, 0.85, 0.95)


STYLESHEET_LIGHT = """
QMainWindow, QWidget { background: #f3f4f6; color: #22262c; font-size: 9.5pt; }
QToolTip { background: #ffffff; color: #22262c; border: 1px solid #c4c8d0; padding: 4px; }
QMenuBar { background: #e9ebef; border-bottom: 1px solid #d0d4da; }
QMenuBar::item:selected { background: #d7e6fb; }
QMenu { background: #ffffff; border: 1px solid #c8ccd4; }
QMenu::item { padding: 5px 24px 5px 22px; }
QMenu::item:selected { background: #d7e6fb; }
QMenu::separator { height: 1px; background: #e0e3e8; margin: 4px 8px; }
#Ribbon { background: #fbfbfc; border-bottom: 1px solid #d4d8de; }
#RibbonTabs QPushButton { border: none; padding: 6px 14px; font-weight: 600; color: #4a5260; background: transparent; }
#RibbonTabs QPushButton:checked { color: #0a64d6; border-bottom: 2px solid #0a64d6; }
#RibbonGroupLabel { color: #6b7380; font-size: 8pt; }
QToolButton { border: 1px solid transparent; border-radius: 4px; padding: 3px; background: transparent; }
QToolButton:hover { background: #e3eefc; border-color: #b9d3f6; }
QToolButton:checked { background: #cfe2fb; border-color: #8ab6ef; }
QToolButton:disabled { color: #a0a6ae; }
QTreeWidget, QTreeView, QListWidget, QTableWidget { background: #ffffff; border: 1px solid #d4d8de;
    alternate-background-color: #f7f8fa; selection-background-color: #d7e6fb; selection-color: #1a1d22; }
QHeaderView::section { background: #eef0f3; border: none; border-right: 1px solid #d4d8de; padding: 4px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #ffffff; border: 1px solid #c4c9d1; border-radius: 3px;
    padding: 3px 5px; selection-background-color: #9cc4f5; }
QLineEdit:focus, QComboBox:focus { border-color: #0a64d6; }
QLineEdit[error="true"] { border-color: #d43c3c; background: #fff2f2; }
QPushButton { background: #ffffff; border: 1px solid #c4c9d1; border-radius: 3px; padding: 5px 14px; }
QPushButton:hover { background: #eef5fe; border-color: #8ab6ef; }
QPushButton:default, QPushButton#Primary { background: #0a64d6; color: white; border-color: #0a58bd; }
QPushButton#Primary:hover { background: #1672e6; }
QPushButton#Primary:disabled { background: #9cbfee; border-color: #9cbfee; }
QPushButton#SelButton { text-align: left; padding: 4px 8px; }
QPushButton#SelButton:checked { background: #d7e6fb; border-color: #0a64d6; }
#Panel { background: #ffffff; border: 1px solid #c8cdd5; border-radius: 6px; }
#PanelTitle { background: #2f3640; color: #ffffff; font-weight: 600; padding: 6px 10px;
    border-top-left-radius: 6px; border-top-right-radius: 6px; }
#Timeline { background: #e9ebef; border-top: 1px solid #cfd3d9; }
#StatusBar, QStatusBar { background: #e9ebef; color: #4a5260; }
QDockWidget::title { background: #e9ebef; padding: 5px; font-weight: 600; }
QSplitter::handle { background: #d4d8de; }
QScrollBar:vertical { width: 10px; background: transparent; }
QScrollBar::handle:vertical { background: #c4c9d1; border-radius: 4px; min-height: 24px; }
QScrollBar:horizontal { height: 10px; background: transparent; }
QScrollBar::handle:horizontal { background: #c4c9d1; border-radius: 4px; min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QCheckBox::indicator { width: 14px; height: 14px; }
"""

STYLESHEET_DARK = """
QMainWindow, QWidget { background: #2b2e33; color: #e3e5e8; font-size: 9.5pt; }
QToolTip { background: #3a3e45; color: #e3e5e8; border: 1px solid #555a63; padding: 4px; }
QMenuBar { background: #24272b; border-bottom: 1px solid #1b1d20; }
QMenuBar::item:selected { background: #3d4a5e; }
QMenu { background: #32363c; border: 1px solid #4a4f57; }
QMenu::item { padding: 5px 24px 5px 22px; }
QMenu::item:selected { background: #3d5a85; }
QMenu::separator { height: 1px; background: #474c54; margin: 4px 8px; }
#Ribbon { background: #303339; border-bottom: 1px solid #1d1f22; }
#RibbonTabs QPushButton { border: none; padding: 6px 14px; font-weight: 600; color: #aab1bc; background: transparent; }
#RibbonTabs QPushButton:checked { color: #5aa2ff; border-bottom: 2px solid #5aa2ff; }
#RibbonGroupLabel { color: #8d95a1; font-size: 8pt; }
QToolButton { border: 1px solid transparent; border-radius: 4px; padding: 3px; background: transparent; }
QToolButton:hover { background: #3b4552; border-color: #4d6a92; }
QToolButton:checked { background: #34507a; border-color: #5a86c4; }
QTreeWidget, QTreeView, QListWidget, QTableWidget { background: #25282c; border: 1px solid #1c1e21;
    alternate-background-color: #2a2d32; selection-background-color: #34507a; selection-color: #ffffff; }
QHeaderView::section { background: #30343a; border: none; border-right: 1px solid #1c1e21; padding: 4px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #1f2226; border: 1px solid #4a4f57; border-radius: 3px;
    padding: 3px 5px; selection-background-color: #34507a; }
QLineEdit:focus, QComboBox:focus { border-color: #5aa2ff; }
QLineEdit[error="true"] { border-color: #e05555; background: #3a2526; }
QPushButton { background: #3a3e45; border: 1px solid #50555e; border-radius: 3px; padding: 5px 14px; }
QPushButton:hover { background: #444a53; }
QPushButton#Primary { background: #2f73d9; color: white; border-color: #2a66c0; }
QPushButton#SelButton { text-align: left; padding: 4px 8px; }
QPushButton#SelButton:checked { background: #34507a; border-color: #5aa2ff; }
#Panel { background: #2f3338; border: 1px solid #1c1e21; border-radius: 6px; }
#PanelTitle { background: #1d2024; color: #ffffff; font-weight: 600; padding: 6px 10px;
    border-top-left-radius: 6px; border-top-right-radius: 6px; }
#Timeline { background: #24272b; border-top: 1px solid #1b1d20; }
QStatusBar { background: #24272b; color: #aab1bc; }
QSplitter::handle { background: #1d1f22; }
"""
