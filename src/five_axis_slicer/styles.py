from __future__ import annotations


# 样式集中在单独模块。窗口类只负责页面和行为编排，后续主题和字号调整在这里收口。
APP_STYLE = """
QMainWindow, QWidget {
    background: #111214;
    color: #f4f4f2;
    font-family: "Segoe UI", "Microsoft YaHei UI";
    font-size: 14px;
}
QToolBar {
    background: rgba(255, 255, 255, 0.08);
    border: 0;
    spacing: 8px;
    padding: 8px;
}
QToolButton, QPushButton {
    background: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 8px;
    padding: 8px 12px;
    color: #f8f8f6;
}
QToolButton:hover, QPushButton:hover {
    background: rgba(255, 255, 255, 0.22);
}
QToolButton:pressed, QPushButton:pressed {
    background: rgba(255, 255, 255, 0.28);
}
#primaryButton {
    background: #d5a642;
    color: #171512;
    border: 1px solid #e8c16f;
    font-weight: 600;
    padding: 10px 18px;
}
#workbenchCard {
    text-align: left;
    padding: 18px;
    background: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 8px;
    font-size: 15px;
}
#workbenchCard:hover {
    background: rgba(255, 255, 255, 0.16);
    border-color: rgba(213, 166, 66, 0.72);
}
#glassPanel {
    background: rgba(245, 245, 245, 0.09);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 8px;
}
#pageTitle {
    font-size: 28px;
    font-weight: 650;
    color: #ffffff;
}
#panelTitle {
    font-size: 17px;
    font-weight: 600;
    color: #ffffff;
}
#mutedText, #fileText {
    color: #c8c8c4;
}
#valueText {
    color: #f0d391;
}
QLabel {
    color: #eeeeec;
}
QComboBox, QSpinBox, QDoubleSpinBox {
    background: rgba(0, 0, 0, 0.24);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 6px;
    padding: 6px;
    color: #f4f4f2;
}
QTabWidget::pane {
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 8px;
    background: rgba(0, 0, 0, 0.16);
}
QTabBar::tab {
    background: rgba(255, 255, 255, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.12);
    padding: 7px 9px;
    margin-right: 3px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: rgba(213, 166, 66, 0.32);
    color: #ffffff;
}
QGroupBox {
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QListWidget, QTextEdit {
    background: rgba(0, 0, 0, 0.22);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 7px;
}
QListWidget::item {
    padding: 6px;
}
QListWidget::item:selected {
    background: rgba(213, 166, 66, 0.34);
}
QCheckBox {
    spacing: 8px;
    padding: 3px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid rgba(255, 255, 255, 0.40);
}
QCheckBox::indicator:checked {
    border: 2px solid #ffffff;
}
#toggleCheck::indicator:checked {
    background: #d5a642;
    border: 2px solid #ffffff;
}
#toggleCheck::indicator:unchecked {
    background: rgba(0, 0, 0, 0.18);
}
#progressPanel {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 8px;
}
QSlider::groove:horizontal {
    height: 5px;
    border-radius: 2px;
    background: rgba(255, 255, 255, 0.18);
}
QSlider::handle:horizontal {
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: #d5a642;
}
QStatusBar {
    background: rgba(255, 255, 255, 0.08);
    color: #d8d8d6;
}
QScrollArea {
    border: 0;
}
"""
