"""Widget composition for the three-column result preview page."""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .result_preview import (
    GCodeSyntaxHighlighter,
    _Card,
    _MiddleElidingPathLabel,
    _ViewerCanvas,
    _WrappingLabel,
)
from .theme import LIGHT_THEME, UI_TYPOGRAPHY


def build_result_preview_ui(page: Any) -> None:
    page.setObjectName("resultPreviewPage")
    root = QVBoxLayout(page)
    root.setContentsMargins(14, 12, 14, 14)
    root.setSpacing(10)
    _build_header(page, root)

    columns = QHBoxLayout()
    columns.setSpacing(10)
    page.left_column = build_left_column(page)
    page.center_column = build_center_column(page)
    page.right_column = build_right_column(page)
    for column, name, minimum in (
        (page.left_column, "resultLeftColumn", 250),
        (page.center_column, "resultCenterColumn", 620),
        (page.right_column, "resultRightColumn", 330),
    ):
        column.setObjectName(name)
        column.setMinimumWidth(minimum)
    columns.addWidget(page.left_column, 18)
    columns.addWidget(page.center_column, 56)
    columns.addWidget(page.right_column, 26)
    root.addLayout(columns, 1)
    page.columns_layout = columns
    apply_local_style(page)


def _build_header(page: Any, root: QVBoxLayout) -> None:
    header = QFrame(page)
    header.setObjectName("resultHeader")
    layout = QHBoxLayout(header)
    layout.setContentsMargins(12, 8, 12, 8)
    page.back_button = QPushButton(header)
    page.back_button.setObjectName("secondaryButton")
    page.back_button.setMinimumWidth(138)
    titles = QVBoxLayout()
    titles.setSpacing(1)
    page.title_label = QLabel(header)
    page.title_label.setObjectName("resultPageTitle")
    page.subtitle_label = QLabel(header)
    page.subtitle_label.setObjectName("resultPageSubtitle")
    titles.addWidget(page.title_label)
    titles.addWidget(page.subtitle_label)
    layout.addWidget(page.back_button)
    layout.addSpacing(12)
    layout.addLayout(titles, 1)
    root.addWidget(header)


def build_left_column(page: Any) -> QWidget:
    content = QWidget(page)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    page.sources_heading = _column_heading(content)
    layout.addWidget(page.sources_heading)
    layout.addWidget(_build_source_card(page, content))
    layout.addWidget(_build_parameter_card(page, content))
    layout.addStretch(1)
    return _scroll_column(page, content)


def _build_source_card(page: Any, parent: QWidget) -> _Card:
    card = _Card(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(7)
    page.source_card_title = _card_title(card)
    layout.addWidget(page.source_card_title)
    page.model_source_title, page.model_source_value = _source_row(card)
    page.gcode_source_title, page.gcode_source_value = _source_row(card)
    page.reference_source_title, page.reference_source_value = _source_row(card)
    for title, value in (
        (page.model_source_title, page.model_source_value),
        (page.gcode_source_title, page.gcode_source_value),
    ):
        layout.addWidget(title)
        layout.addWidget(value)
    page.reference_source_title.hide()
    page.reference_source_value.hide()
    page.demo_button = QPushButton(card)
    page.demo_button.setObjectName("primaryButton")
    page.open_gcode_button = QPushButton(card)
    page.open_step_button = QPushButton(card)
    layout.addSpacing(3)
    layout.addWidget(page.demo_button)
    layout.addWidget(page.open_gcode_button)
    layout.addWidget(page.open_step_button)
    page.slice_button = QPushButton(card)
    page.slice_button.setObjectName("primaryButton")
    layout.addSpacing(4)
    layout.addWidget(page.slice_button)
    return card


def _build_parameter_card(page: Any, parent: QWidget) -> _Card:
    card = _Card(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)
    page.parameters_title = _card_title(card)
    layout.addWidget(page.parameters_title)
    page.parameters_badge = QLabel(card)
    page.parameters_badge.hide()
    page.parameters_note = QLabel(card)
    page.parameters_note.hide()
    layout.addLayout(_build_parameter_grid(page, card))
    layout.addLayout(_build_parameter_buttons(page, card))
    page.parameter_feedback = _WrappingLabel(parent=card)
    page.parameter_feedback.setObjectName("feedbackLabel")
    layout.addWidget(page.parameter_feedback)
    return card


def _build_parameter_grid(page: Any, card: _Card) -> QGridLayout:
    grid = QGridLayout()
    grid.setVerticalSpacing(4)
    page.parameter_labels = {}
    page.layer_height_spin = _double_spin(page, 0.01, 10.0, 0.01, 2, " mm")
    page.print_speed_spin = _double_spin(page, 1.0, 1_000_000.0, 10.0, 0, " mm/min")
    page.extrusion_width_spin = _double_spin(page, 0.01, 10.0, 0.01, 2, " mm")
    page.nozzle_diameter_spin = _double_spin(page, 0.01, 10.0, 0.01, 2, " mm")
    page.shell_checkbox = QCheckBox(card)
    page.top_layers_spin = QSpinBox(card)
    page.bottom_layers_spin = QSpinBox(card)
    for spin in (page.top_layers_spin, page.bottom_layers_spin):
        spin.setRange(0, 999)
    top_bottom = _top_bottom_editor(page, card)
    rows = (
        ("layer_height", page.layer_height_spin),
        ("print_speed", page.print_speed_spin),
        ("extrusion_width", page.extrusion_width_spin),
        ("nozzle_diameter", page.nozzle_diameter_spin),
        ("process_mode", page.shell_checkbox),
        ("top_bottom", top_bottom),
    )
    for row, (key, editor) in enumerate(rows):
        label = QLabel(card)
        label.setObjectName("formLabel")
        page.parameter_labels[key] = label
        grid.addWidget(label, row * 2, 0)
        grid.addWidget(editor, row * 2 + 1, 0)
    return grid


def _top_bottom_editor(page: Any, parent: QWidget) -> QWidget:
    editor = QWidget(parent)
    layout = QHBoxLayout(editor)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    slash = QLabel("/", editor)
    slash.setAlignment(Qt.AlignCenter)
    layout.addWidget(page.top_layers_spin)
    layout.addWidget(slash)
    layout.addWidget(page.bottom_layers_spin)
    return editor


def _build_parameter_buttons(page: Any, card: _Card) -> QGridLayout:
    layout = QGridLayout()
    layout.setHorizontalSpacing(6)
    layout.setVerticalSpacing(6)
    page.edit_parameters_button = QPushButton(card)
    page.save_parameters_button = QPushButton(card)
    page.reset_parameters_button = QPushButton(card)
    layout.addWidget(page.edit_parameters_button, 0, 0)
    layout.addWidget(page.save_parameters_button, 0, 1)
    layout.addWidget(page.reset_parameters_button, 1, 0, 1, 2)
    layout.setColumnStretch(0, 1)
    layout.setColumnStretch(1, 1)
    return layout


def build_center_column(page: Any) -> QWidget:
    column = QWidget(page)
    layout = QVBoxLayout(column)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    page.viewer_heading = _column_heading(column)
    layout.addWidget(page.viewer_heading)
    page.viewer_canvas = _ViewerCanvas(page.viewer, column)
    page.viewer_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    layout.addWidget(page.viewer_canvas, 1)
    layout.addWidget(_build_navigation_card(page, column))
    layout.addWidget(_build_visibility_card(page, column))
    return column


def _build_navigation_card(page: Any, parent: QWidget) -> _Card:
    card = _Card(parent)
    layout = QGridLayout(card)
    layout.setContentsMargins(12, 9, 12, 9)
    layout.setHorizontalSpacing(8)
    layout.setVerticalSpacing(6)
    _create_navigation_widgets(page, card)
    layout.addWidget(page.stage_title, 0, 0)
    layout.addWidget(page.previous_stage_button, 0, 1)
    layout.addWidget(page.stage_combo, 0, 2, 1, 3)
    layout.addWidget(page.next_stage_button, 0, 5)
    layout.addWidget(page.progress_title, 1, 0)
    layout.addWidget(page.play_button, 1, 1)
    layout.addWidget(page.progress_slider, 1, 2, 1, 3)
    layout.addWidget(page.progress_value, 1, 5)
    layout.addWidget(page.quality_title, 2, 0)
    layout.addWidget(page.quality_combo, 2, 2, 1, 2)
    page.stage_fallback_label = _WrappingLabel(parent=card)
    page.stage_fallback_label.setObjectName("mutedNote")
    layout.addWidget(page.stage_fallback_label, 3, 0, 1, 6)
    return card


def _create_navigation_widgets(page: Any, card: _Card) -> None:
    page.stage_title = QLabel(card)
    page.stage_title.setObjectName("formLabel")
    page.stage_combo = QComboBox(card)
    page.previous_stage_button = QToolButton(card)
    page.previous_stage_button.setText("‹")
    page.next_stage_button = QToolButton(card)
    page.next_stage_button.setText("›")
    page.previous_stage_button.setFixedSize(34, 34)
    page.next_stage_button.setFixedSize(34, 34)
    page.progress_title = QLabel(card)
    page.progress_title.setObjectName("formLabel")
    page.progress_slider = QSlider(Qt.Horizontal, card)
    page.play_button = QToolButton(card)
    page.play_button.setText("▶")
    page.play_button.setFixedSize(38, 34)
    page.progress_value = QLabel("0.0%", card)
    page.progress_value.setObjectName("monospaceValue")
    page.progress_value.setMinimumWidth(62)
    page.progress_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    page.quality_title = QLabel(card)
    page.quality_title.setObjectName("formLabel")
    page.quality_combo = QComboBox(card)
    page.quality_combo.addItem("", "interactive")
    page.quality_combo.addItem("", "paper")


def _build_visibility_card(page: Any, parent: QWidget) -> _Card:
    card = _Card(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(5)
    page.visibility_title = _card_title(card)
    layout.addWidget(page.visibility_title)
    grid = QGridLayout()
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(4)
    page.model_check = QCheckBox(card)
    page.extrusion_check = QCheckBox(card)
    page.travel_check = QCheckBox(card)
    page.pose_check = QCheckBox(card)
    page.start_end_check = QCheckBox(card)
    page.axes_check = QCheckBox(card)
    page.cube_check = QCheckBox(card)
    page.visibility_checks = (
        page.model_check,
        page.extrusion_check,
        page.travel_check,
        page.pose_check,
        page.start_end_check,
        page.axes_check,
        page.cube_check,
    )
    for index, checkbox in enumerate(page.visibility_checks):
        checkbox.setMinimumWidth(0)
        checkbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid.addWidget(checkbox, index // 2, index % 2)
    layout.addLayout(grid)
    return card


def build_right_column(page: Any) -> QWidget:
    content = QWidget(page)
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    page.analysis_heading = _column_heading(content)
    layout.addWidget(page.analysis_heading)
    for card in (
        _build_status_card(page, content),
        _build_statistics_card(page, content),
        _build_thumbnail_card(page, content),
        _build_context_card(page, content),
        _build_export_card(page, content),
    ):
        layout.addWidget(card)
    layout.addStretch(1)
    return _scroll_column(page, content)


def _build_status_card(page: Any, parent: QWidget) -> _Card:
    card = _Card(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 11, 12, 11)
    layout.setSpacing(6)
    page.status_card_title = _card_title(card)
    layout.addWidget(page.status_card_title)
    row = QHBoxLayout()
    page.status_indicator = QLabel(card)
    page.status_indicator.setFixedSize(11, 11)
    page.status_name = QLabel(card)
    page.status_name.setObjectName("statusName")
    row.addWidget(page.status_indicator)
    row.addWidget(page.status_name, 1)
    layout.addLayout(row)
    page.status_detail = _WrappingLabel(parent=card)
    page.status_detail.setObjectName("mutedNote")
    layout.addWidget(page.status_detail)
    page.status_progress = QProgressBar(card)
    page.status_progress.setRange(0, 1000)
    page.status_progress.setTextVisible(True)
    layout.addWidget(page.status_progress)
    page.cancel_button = QPushButton(card)
    page.cancel_button.setEnabled(False)
    layout.addWidget(page.cancel_button)
    return card


def _build_statistics_card(page: Any, parent: QWidget) -> _Card:
    card = _Card(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 11, 12, 11)
    layout.setSpacing(5)
    page.statistics_title = _card_title(card)
    layout.addWidget(page.statistics_title)
    page.statistics_grid = _build_statistics_grid(page, card)
    layout.addLayout(page.statistics_grid)
    _add_statistics_evidence(page, card, layout)
    return card


def _build_statistics_grid(page: Any, card: _Card) -> QGridLayout:
    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(4)
    page.statistic_labels = {}
    page.statistic_values = {}
    keys = (
        "bodies",
        "edges",
        "base_layers",
        "blade_stages",
        "spatial_segments",
        "extrusion_segments",
        "travel_segments",
        "layer_range",
        "a_range",
        "c_range",
    )
    for row, key in enumerate(keys):
        label = _WrappingLabel(parent=card)
        value = QLabel("—", card)
        value.setObjectName("monospaceValue")
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        page.statistic_labels[key] = label
        page.statistic_values[key] = value
        grid.addWidget(label, row, 0)
        grid.addWidget(value, row, 1)
    grid.setColumnStretch(0, 1)
    return grid


def _add_statistics_evidence(page: Any, card: _Card, layout: QVBoxLayout) -> None:
    formula = _WrappingLabel(parent=card)
    formula.setObjectName("formulaLabel")
    formula.setText("P_part = Rz(-C) × Rx(-A) × P_machine")
    formula.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(formula)
    page.continuity_label = _WrappingLabel("Polyline: 0.02 mm", card)
    page.continuity_label.setObjectName("mutedNote")
    layout.addWidget(page.continuity_label)
    page.statistics_evidence = _WrappingLabel(parent=card)
    page.statistics_evidence.setObjectName("mutedNote")
    layout.addWidget(page.statistics_evidence)


def _build_thumbnail_card(page: Any, parent: QWidget) -> _Card:
    card = _Card(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(5)
    page.thumbnail_title = _card_title(card)
    layout.addWidget(page.thumbnail_title)
    page.thumbnail_label = QLabel(card)
    page.thumbnail_label.setObjectName("thumbnailViewport")
    page.thumbnail_label.setMinimumHeight(132)
    page.thumbnail_label.setAlignment(Qt.AlignCenter)
    layout.addWidget(page.thumbnail_label)
    page.thumbnail_note = _WrappingLabel(parent=card)
    page.thumbnail_note.setObjectName("mutedNote")
    layout.addWidget(page.thumbnail_note)
    return card


def _build_context_card(page: Any, parent: QWidget) -> _Card:
    card = _Card(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(5)
    page.context_title = _card_title(card)
    layout.addWidget(page.context_title)
    layout.addLayout(_build_search_row(page, card))
    layout.addLayout(_build_jump_row(page, card))
    page.context_range_label = _WrappingLabel(parent=card)
    page.context_range_label.setObjectName("mutedNote")
    layout.addWidget(page.context_range_label)
    page.code_view = QPlainTextEdit(card)
    page.code_view.setObjectName("gcodeContextView")
    page.code_view.setReadOnly(True)
    page.code_view.setLineWrapMode(QPlainTextEdit.NoWrap)
    page.code_view.setMinimumHeight(250)
    page.code_highlighter = GCodeSyntaxHighlighter(page.code_view.document())
    layout.addWidget(page.code_view)
    page.search_feedback = QLabel(card)
    page.search_feedback.setObjectName("feedbackLabel")
    layout.addWidget(page.search_feedback)
    return card


def _build_search_row(page: Any, card: _Card) -> QHBoxLayout:
    layout = QHBoxLayout()
    page.search_edit = QLineEdit(card)
    page.search_previous_button = QToolButton(card)
    page.search_previous_button.setText("↑")
    page.search_next_button = QToolButton(card)
    page.search_next_button.setText("↓")
    layout.addWidget(page.search_edit, 1)
    layout.addWidget(page.search_previous_button)
    layout.addWidget(page.search_next_button)
    return layout


def _build_jump_row(page: Any, card: _Card) -> QHBoxLayout:
    layout = QHBoxLayout()
    page.jump_edit = QLineEdit(card)
    page.jump_edit.setMaximumWidth(110)
    page.jump_button = QPushButton(card)
    layout.addWidget(page.jump_edit)
    layout.addWidget(page.jump_button)
    return layout


def _build_export_card(page: Any, parent: QWidget) -> _Card:
    card = _Card(parent)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 11, 12, 11)
    layout.setSpacing(6)
    page.export_title = _card_title(card)
    page.export_description = _WrappingLabel(parent=card)
    page.export_description.setObjectName("mutedNote")
    layout.addWidget(page.export_title)
    layout.addWidget(page.export_description)
    page.export_preset_value = _WrappingLabel(parent=card)
    page.export_preset_value.setObjectName("exportPreset")
    layout.addWidget(page.export_preset_value)
    audit = _WrappingLabel("3840 × 2160 px  ·  300 dpi  ·  sRGB  ·  JSON", card)
    audit.setObjectName("mutedNote")
    layout.addWidget(audit)
    page.output_label = QLabel(card)
    page.output_label.setObjectName("formLabel")
    layout.addWidget(page.output_label)
    page.output_path_value = _MiddleElidingPathLabel(card)
    page.output_path_value.setObjectName("pathValue")
    output_path = str(page._output_directory)
    page.output_path_value.set_source_text(output_path, tooltip=output_path)
    page.choose_output_button = QPushButton(card)
    layout.addWidget(page.output_path_value)
    layout.addWidget(page.choose_output_button)
    page.export_current_button = QPushButton(card)
    page.export_current_button.setObjectName("primaryButton")
    page.export_both_button = QPushButton(card)
    layout.addWidget(page.export_current_button)
    layout.addWidget(page.export_both_button)
    return card


def _source_row(parent: QWidget) -> tuple[QLabel, _MiddleElidingPathLabel]:
    title = QLabel(parent)
    title.setObjectName("formLabel")
    value = _MiddleElidingPathLabel(parent)
    value.setObjectName("pathValue")
    return title, value


def _column_heading(parent: QWidget) -> QLabel:
    label = _WrappingLabel(parent=parent)
    label.setObjectName("columnHeading")
    return label


def _card_title(parent: QWidget) -> QLabel:
    label = _WrappingLabel(parent=parent)
    label.setObjectName("cardTitle")
    return label


def _double_spin(
    page: Any,
    minimum: float,
    maximum: float,
    step: float,
    decimals: int,
    suffix: str,
) -> QDoubleSpinBox:
    spin = QDoubleSpinBox(page)
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    spin.setSuffix(suffix)
    spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return spin


def _scroll_column(page: Any, content: QWidget) -> QScrollArea:
    scroll = QScrollArea(page)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setWidget(content)
    return scroll


def apply_local_style(page: Any) -> None:
    page.setStyleSheet(
        f"""
        QWidget#resultPreviewPage {{
            background: {LIGHT_THEME.window}; color: {LIGHT_THEME.text};
            font-family: {LIGHT_THEME.ui_font_family}; font-size: {UI_TYPOGRAPHY.body_px}px;
        }}
        QFrame#resultHeader, QFrame#resultCard {{
            background: {LIGHT_THEME.panel}; border: 1px solid {LIGHT_THEME.border}; border-radius: 7px;
        }}
        QLabel#resultPageTitle {{ font-size: {UI_TYPOGRAPHY.page_title_px}px; font-weight: 650; color: {LIGHT_THEME.text}; }}
        QLabel#resultPageSubtitle, QLabel#mutedNote {{ color: {LIGHT_THEME.muted_text}; font-size: {UI_TYPOGRAPHY.secondary_px}px; }}
        QLabel#columnHeading {{ font-size: {UI_TYPOGRAPHY.section_title_px}px; font-weight: 650; color: {LIGHT_THEME.text}; padding: 1px 3px; }}
        QLabel#cardTitle, QLabel#statusName {{ font-size: {UI_TYPOGRAPHY.card_title_px}px; font-weight: 650; color: {LIGHT_THEME.text}; }}
        QLabel#formLabel {{ color: {LIGHT_THEME.muted_text}; font-size: {UI_TYPOGRAPHY.label_px}px; }}
        QLabel#pathValue {{ background: {LIGHT_THEME.hover_background}; border: 1px solid {LIGHT_THEME.border}; border-radius: 4px; padding: 5px; color: {LIGHT_THEME.muted_text}; }}
        QLabel#pathValue[loaded="true"] {{ color: {LIGHT_THEME.text}; }}
        QLabel#warningBadge {{ color: {LIGHT_THEME.warning}; background: #FFF4E8; border-radius: 4px; padding: 3px 5px; font-size: {UI_TYPOGRAPHY.badge_px}px; }}
        QLabel#feedbackLabel {{ color: {LIGHT_THEME.success}; font-size: {UI_TYPOGRAPHY.secondary_px}px; }}
        QLabel#feedbackLabel[error="true"] {{ color: {LIGHT_THEME.error}; }}
        QLabel#monospaceValue, QLabel#formulaLabel {{ font-family: {LIGHT_THEME.code_font_family}; color: {LIGHT_THEME.text}; font-size: {UI_TYPOGRAPHY.code_px}px; }}
        QLabel#formulaLabel {{ background: {LIGHT_THEME.code_background}; border: 1px solid {LIGHT_THEME.border}; border-radius: 4px; padding: 6px; }}
        QLabel#thumbnailViewport {{ background: #F6F8FB; border: 1px solid {LIGHT_THEME.border}; border-radius: 5px; }}
        QLabel#exportPreset {{ color: {LIGHT_THEME.primary}; background: {LIGHT_THEME.primary_subtle}; border: 1px solid #BFDBFE; border-radius: 4px; padding: 6px; }}
        QFrame#resultViewerCanvas {{ background: #F8FAFC; border: 1px solid {LIGHT_THEME.border}; border-radius: 7px; }}
        QFrame#viewToolRail {{ background: rgba(255,255,255,232); border: 1px solid {LIGHT_THEME.border}; border-radius: 6px; }}
        QPushButton#primaryButton {{ background: {LIGHT_THEME.primary}; color: white; border-color: {LIGHT_THEME.primary}; font-weight: 600; }}
        QPushButton#primaryButton:hover {{ background: {LIGHT_THEME.primary_hover}; }}
        QPlainTextEdit#gcodeContextView {{ background: {LIGHT_THEME.code_background}; color: {LIGHT_THEME.text}; border: 1px solid {LIGHT_THEME.border}; border-radius: 4px; font-family: {LIGHT_THEME.code_font_family}; font-size: {UI_TYPOGRAPHY.code_px}px; selection-background-color: {LIGHT_THEME.selected_background}; }}
        """
    )
