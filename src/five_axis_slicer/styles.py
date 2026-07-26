from __future__ import annotations

from .theme import LIGHT_THEME, UI_TYPOGRAPHY, ThemeTokens, TypographyTokens


_APP_STYLE_TEMPLATE = r"""
QMainWindow, QDialog {
    background-color: @WINDOW@;
}
QWidget {
    color: @TEXT@;
    font-family: @UI_FONT_FAMILY@;
    font-size: @BODY_FONT_PX@px;
    selection-background-color: @SELECTED_BACKGROUND@;
    selection-color: @TEXT@;
}
QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {
    background-color: @WINDOW@;
}
QLabel {
    background-color: transparent;
}

QMenuBar {
    background-color: @PANEL@;
    border-bottom: 1px solid @BORDER@;
    padding: 2px 8px;
    spacing: 2px;
}
QMenuBar::item {
    background-color: transparent;
    border-radius: 4px;
    padding: 6px 10px;
}
QMenuBar::item:selected, QMenuBar::item:pressed {
    background-color: @SELECTED_BACKGROUND@;
    color: @PRIMARY@;
}
QMenu {
    background-color: @PANEL@;
    border: 1px solid @BORDER@;
    border-radius: 6px;
    padding: 6px;
}
QMenu::item {
    border-radius: 4px;
    padding: 7px 30px 7px 10px;
}
QMenu::item:selected {
    background-color: @SELECTED_BACKGROUND@;
    color: @PRIMARY@;
}
QMenu::item:disabled {
    color: @DISABLED_TEXT@;
}
QMenu::separator {
    background-color: @BORDER@;
    height: 1px;
    margin: 5px 8px;
}

QToolBar {
    background-color: @PANEL@;
    border: 0;
    border-bottom: 1px solid @BORDER@;
    spacing: 6px;
    padding: 6px 10px;
}
QToolBar::separator {
    background-color: @BORDER@;
    width: 1px;
    margin: 5px 7px;
}
QToolButton, QPushButton {
    background-color: @PANEL@;
    border: 1px solid @BORDER@;
    border-radius: 6px;
    color: @TEXT@;
    min-height: 18px;
    padding: 7px 12px;
}
QToolButton:hover, QPushButton:hover {
    background-color: @HOVER_BACKGROUND@;
    border-color: @PRIMARY@;
}
QToolButton:focus, QPushButton:focus {
    background-color: @PRIMARY_SUBTLE@;
    border: 2px solid @PRIMARY@;
    padding: 6px 11px;
}
QToolButton:pressed, QPushButton:pressed,
QToolButton:checked, QPushButton:checked {
    background-color: @SELECTED_BACKGROUND@;
    border-color: @PRIMARY@;
    color: @PRIMARY@;
}
QToolButton:disabled, QPushButton:disabled {
    background-color: @DISABLED_BACKGROUND@;
    border-color: @BORDER@;
    color: @DISABLED_TEXT@;
}
#primaryButton, #slicePreviewButton {
    background-color: @PRIMARY@;
    border-color: @PRIMARY@;
    color: @PANEL@;
    font-weight: 600;
    padding: 8px 14px;
}
#primaryButton:hover, #slicePreviewButton:hover {
    background-color: @PRIMARY_HOVER@;
    border-color: @PRIMARY_HOVER@;
}
#primaryButton:pressed, #slicePreviewButton:pressed {
    background-color: @PRIMARY_PRESSED@;
    border-color: @PRIMARY_PRESSED@;
}
#primaryButton:disabled, #slicePreviewButton:disabled {
    background-color: @DISABLED_BACKGROUND@;
    border-color: @BORDER@;
    color: @DISABLED_TEXT@;
}
#secondaryButton, #viewToolButton, #stageButton, #iconButton {
    background-color: @PANEL@;
}
#dangerButton {
    background-color: @PANEL@;
    border-color: @ERROR@;
    color: @ERROR@;
}
#dangerButton:hover {
    background-color: #FFF4ED;
}

#workbenchCard {
    background-color: @PANEL@;
    border: 1px solid @BORDER@;
    border-radius: 8px;
    font-size: 15px;
    padding: 18px;
    text-align: left;
}
#workbenchCard:hover {
    background-color: @PRIMARY_SUBTLE@;
    border-color: @PRIMARY@;
}
#glassPanel, #progressPanel, #resultPreviewPanel, #sourcePanel,
#viewerPanel, #detailsPanel, #codePanel, #thumbnailPanel {
    background-color: @PANEL@;
    border: 1px solid @BORDER@;
    border-radius: 8px;
}
#progressPanel {
    padding: 4px;
}
#viewerCanvas, #renderCanvas {
    background-color: @PANEL@;
    border: 1px solid @BORDER@;
    border-radius: 6px;
}
#pageTitle {
    color: @TEXT@;
    font-size: 26px;
    font-weight: 650;
}
#panelTitle, #sectionTitle {
    color: @TEXT@;
    font-size: 16px;
    font-weight: 600;
}
#mutedText, #fileText, #captionText, #helperText {
    color: @MUTED_TEXT@;
}
#valueText {
    color: @PRIMARY@;
    font-weight: 600;
}
#parameterNotice {
    background-color: #FFFAEB;
    border: 1px solid #FEDF89;
    border-radius: 6px;
    color: @WARNING@;
    padding: 8px;
}
#statusBadge {
    background-color: @DISABLED_BACKGROUND@;
    border: 1px solid @BORDER@;
    border-radius: 9px;
    color: @MUTED_TEXT@;
    font-size: @SECONDARY_FONT_PX@px;
    font-weight: 600;
    padding: 2px 8px;
}
#statusBadge[state="ready"] {
    background-color: #ECFDF3;
    border-color: #ABEFC6;
    color: @SUCCESS@;
}
#statusBadge[state="loading"] {
    background-color: @PRIMARY_SUBTLE@;
    border-color: #BFDBFE;
    color: @PRIMARY@;
}
#statusBadge[state="warning"] {
    background-color: #FFFAEB;
    border-color: #FEDF89;
    color: @WARNING@;
}
#statusBadge[state="error"] {
    background-color: #FEF3F2;
    border-color: #FECDCA;
    color: @ERROR@;
}

QGroupBox {
    background-color: @PANEL@;
    border: 1px solid @BORDER@;
    border-radius: 7px;
    font-weight: 600;
    margin-top: 14px;
    padding: 12px 9px 9px 9px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 9px;
    padding: 0 5px;
}
QTabWidget::pane {
    background-color: @PANEL@;
    border: 1px solid @BORDER@;
    border-radius: 7px;
    top: -1px;
}
QTabBar::tab {
    background-color: transparent;
    border: 0;
    border-bottom: 2px solid transparent;
    color: @MUTED_TEXT@;
    min-width: 64px;
    padding: 8px 11px;
}
QTabBar::tab:hover {
    background-color: @HOVER_BACKGROUND@;
    color: @TEXT@;
}
QTabBar::tab:selected {
    border-bottom-color: @PRIMARY@;
    color: @PRIMARY@;
    font-weight: 600;
}
QTabBar::tab:disabled {
    color: @DISABLED_TEXT@;
}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox,
QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {
    background-color: @INPUT_BACKGROUND@;
    border: 1px solid @BORDER@;
    border-radius: 5px;
    color: @TEXT@;
    min-height: 20px;
    padding: 5px 7px;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover,
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #98A2B3;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 2px solid @PRIMARY@;
    padding: 4px 6px;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    background-color: @DISABLED_BACKGROUND@;
    color: @DISABLED_TEXT@;
}
QComboBox::drop-down {
    border: 0;
    width: 22px;
}
QComboBox QAbstractItemView {
    background-color: @PANEL@;
    border: 1px solid @BORDER@;
    color: @TEXT@;
    outline: 0;
    selection-background-color: @SELECTED_BACKGROUND@;
    selection-color: @TEXT@;
}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
    background-color: @HOVER_BACKGROUND@;
    border: 0;
    border-left: 1px solid @BORDER@;
    width: 18px;
}
QPlainTextEdit#codeEditor, QTextEdit#codeEditor, #gcodeContextEditor {
    background-color: @CODE_BACKGROUND@;
    border-color: @BORDER@;
    color: @TEXT@;
    font-family: @CODE_FONT_FAMILY@;
    font-size: @CODE_FONT_PX@px;
    selection-background-color: #BFDBFE;
}
#codeLineNumberArea {
    background-color: @CODE_GUTTER@;
    border-right: 1px solid @BORDER@;
    color: @MUTED_TEXT@;
    font-family: @CODE_FONT_FAMILY@;
}

QListWidget, QTreeWidget, QTableWidget, QTableView, QTreeView {
    alternate-background-color: @HOVER_BACKGROUND@;
    background-color: @PANEL@;
    border: 1px solid @BORDER@;
    border-radius: 6px;
    color: @TEXT@;
    outline: 0;
    padding: 4px;
}
QAbstractItemView::item {
    border-radius: 4px;
    min-height: 22px;
    padding: 4px 6px;
}
QAbstractItemView::item:hover {
    background-color: @HOVER_BACKGROUND@;
}
QAbstractItemView::item:selected {
    background-color: @SELECTED_BACKGROUND@;
    color: @TEXT@;
}
QHeaderView::section {
    background-color: @HOVER_BACKGROUND@;
    border: 0;
    border-bottom: 1px solid @BORDER@;
    border-right: 1px solid @BORDER@;
    color: @MUTED_TEXT@;
    font-weight: 600;
    padding: 6px 8px;
}

QCheckBox, QRadioButton {
    background-color: transparent;
    spacing: 7px;
    padding: 3px;
}
QCheckBox::indicator, QRadioButton::indicator {
    background-color: @PANEL@;
    border: 1px solid #98A2B3;
    height: 16px;
    width: 16px;
}
QCheckBox::indicator {
    border-radius: 3px;
}
QRadioButton::indicator {
    border-radius: 7px;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: @PRIMARY@;
}
QCheckBox::indicator:checked, #toggleCheck::indicator:checked,
#roleCheck::indicator:checked {
    background-color: @PRIMARY@;
    border: 3px solid @PANEL@;
}
QRadioButton::indicator:checked {
    background-color: @PRIMARY@;
    border: 4px solid @PANEL@;
}
QCheckBox:disabled, QRadioButton:disabled {
    color: @DISABLED_TEXT@;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    background-color: @DISABLED_BACKGROUND@;
    border-color: @BORDER@;
}

QSlider::groove:horizontal {
    background-color: @BORDER@;
    border-radius: 2px;
    height: 4px;
}
QSlider::sub-page:horizontal {
    background-color: @PRIMARY@;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background-color: @PANEL@;
    border: 2px solid @PRIMARY@;
    border-radius: 7px;
    height: 14px;
    margin: -6px 0;
    width: 14px;
}
QSlider::handle:horizontal:hover {
    background-color: @PRIMARY_SUBTLE@;
}
QProgressBar {
    background-color: @DISABLED_BACKGROUND@;
    border: 0;
    border-radius: 4px;
    color: @TEXT@;
    min-height: 8px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: @PRIMARY@;
    border-radius: 4px;
}

QScrollBar:vertical {
    background-color: transparent;
    margin: 2px;
    width: 10px;
}
QScrollBar:horizontal {
    background-color: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background-color: #B8C1CE;
    border-radius: 4px;
    min-height: 28px;
    min-width: 28px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background-color: #98A2B3;
}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    background-color: transparent;
    border: 0;
    height: 0;
    width: 0;
}
QSplitter::handle {
    background-color: @BORDER@;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}
QFrame#separator {
    background-color: @BORDER@;
    border: 0;
    max-height: 1px;
}

QStatusBar {
    background-color: @PANEL@;
    border-top: 1px solid @BORDER@;
    color: @MUTED_TEXT@;
}
QStatusBar::item {
    border: 0;
}
QToolTip {
    background-color: @TEXT@;
    border: 1px solid @TEXT@;
    border-radius: 4px;
    color: @PANEL@;
    padding: 5px 7px;
}
"""


def build_app_style(
    theme: ThemeTokens = LIGHT_THEME,
    typography: TypographyTokens = UI_TYPOGRAPHY,
) -> str:
    """Build the application QSS without coupling theme data to Qt imports."""

    style = _APP_STYLE_TEMPLATE
    values = {**theme.qss_values(), **typography.qss_values()}
    for name, value in values.items():
        style = style.replace(f"@{name}@", value)
    return style


APP_STYLE = build_app_style()


__all__ = ["APP_STYLE", "build_app_style"]
