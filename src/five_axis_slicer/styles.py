from __future__ import annotations


# 界面样式集中在单独模块，主窗口只负责行为编排。
# 后续若要做主题切换或字号配置，可以在这里扩展，避免把 QSS 混入窗口逻辑。
APP_STYLE = """
QMainWindow, QWidget {
    background: #111214;
    color: #f4f4f2;
    font-family: "Segoe UI", "Microsoft YaHei UI";
    font-size: 15px;
}
QToolBar {
    background: rgba(255, 255, 255, 0.08);
    border: 0;
    spacing: 8px;
    padding: 9px;
}
QToolButton, QPushButton {
    background: rgba(255, 255, 255, 0.16);
    border: 1px solid rgba(255, 255, 255, 0.22);
    border-radius: 8px;
    padding: 9px 14px;
    color: #f8f8f6;
}
QToolButton:hover, QPushButton:hover {
    background: rgba(255, 255, 255, 0.24);
}
QLabel {
    color: #eeeeec;
}
QLabel:first-child {
    font-size: 18px;
    font-weight: 600;
}
#glassPanel {
    background: rgba(245, 245, 245, 0.10);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 12px;
}
QListWidget {
    background: rgba(0, 0, 0, 0.20);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 7px;
}
QListWidget::item {
    padding: 6px;
}
QListWidget::item:selected {
    background: rgba(255, 255, 255, 0.20);
}
QStatusBar {
    background: rgba(255, 255, 255, 0.08);
    color: #d8d8d6;
}
"""
