from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .core import MachineParameters, MeshModel, SliceParameters, SliceResult, SliceSelection
from .gcode import generate_gcode
from .geometry import generate_demo_dome_mesh, grow_face_selection, load_mesh, selection_boundary_edges, split_mesh_into_components
from .gui_text import AXES, PATH_KIND_LABEL_KEYS, PATH_KIND_ORDER, UI_TEXT
from .hardware import machine_profile_summary, open5x_freddi_hong_machine
from .qt_compat import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
    PLAIN_TEXT_NO_WRAP,
    QT_API,
    QT_HORIZONTAL,
    qt_exec,
)
from .slicer import ConformalSlicer, slice_planar_model
from .viewer import PATH_STYLE_MAP, PreviewCanvas


class _NoWheelMixin:
    """Ignore mouse-wheel changes so scrolling the panel does not edit values."""

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        event.ignore()


class NoWheelComboBox(_NoWheelMixin, QComboBox):
    pass


class NoWheelDoubleSpinBox(_NoWheelMixin, QDoubleSpinBox):
    pass


class NoWheelSpinBox(_NoWheelMixin, QSpinBox):
    pass


def _set_button_selected(button: QPushButton, selected: bool) -> None:
    button.setProperty("selected", selected)
    style = button.style()
    if style is not None:
        style.unpolish(button)
        style.polish(button)
    button.update()


class BooleanChoice(QWidget):
    """Compact yes/no selector used for boolean process settings."""

    def __init__(self, checked: bool = False) -> None:
        super().__init__()
        self._checked = bool(checked)
        self._callbacks: list = []

        self.yes_button = QPushButton()
        self.no_button = QPushButton()
        for button in (self.yes_button, self.no_button):
            button.setObjectName("choiceButton")
            button.setCheckable(True)
            button.setMinimumWidth(52)

        self.yes_button.clicked.connect(lambda: self.setChecked(True))
        self.no_button.clicked.connect(lambda: self.setChecked(False))

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.yes_button)
        layout.addWidget(self.no_button)
        self.setLayout(layout)

        if hasattr(QSizePolicy, "Policy"):
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        else:
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.setChecked(self._checked)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        checked = bool(checked)
        changed = checked != self._checked
        self._checked = checked
        self.yes_button.setChecked(checked)
        self.no_button.setChecked(not checked)
        _set_button_selected(self.yes_button, checked)
        _set_button_selected(self.no_button, not checked)
        if changed:
            for callback in list(self._callbacks):
                callback(self._checked)

    def set_labels(self, yes_text: str, no_text: str) -> None:
        self.yes_button.setText(yes_text)
        self.no_button.setText(no_text)

    def on_changed(self, callback) -> None:
        self._callbacks.append(callback)


class CollapsibleSection(QWidget):
    def __init__(self, title: str = "", expanded: bool = True) -> None:
        super().__init__()
        self._title = title
        self._expanded = bool(expanded)

        self.header_button = QPushButton()
        self.header_button.setObjectName("collapsibleHeader")
        self.header_button.clicked.connect(self.toggle)
        self.content_widget = QWidget()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.header_button)
        layout.addWidget(self.content_widget)
        self.setLayout(layout)

        self.set_title(title)
        self.set_expanded(expanded)

    def set_title(self, title: str) -> None:
        self._title = title
        prefix = "[-]" if self._expanded else "[+]"
        self.header_button.setText(f"{prefix} {self._title}")

    def set_content_layout(self, content_layout: QVBoxLayout) -> None:
        self.content_widget.setLayout(content_layout)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        self.content_widget.setVisible(self._expanded)
        self.set_title(self._title)

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.language = "zh"
        self.default_machine = open5x_freddi_hong_machine()

        self.source_mesh: MeshModel | None = None
        self.mesh: MeshModel | None = None
        self.component_meshes: list[MeshModel] = []
        self.slice_result: SliceResult | None = None
        self.generated_gcode: str | None = None
        self.export_warnings: list[str] = []
        self.placement_rotation_deg = np.zeros(3, dtype=float)
        self.placement_translation_mm = np.zeros(3, dtype=float)
        self.selected_substrate_component_index: int | None = None
        self.selected_conformal_component_indices: set[int] = set()
        self.selected_substrate_face_indices: set[int] = set()
        self.selected_conformal_face_indices: set[int] = set()

        self.slicer = ConformalSlicer()
        self.slice_controls: dict[str, object] = {}
        self.machine_controls: dict[str, object] = {}
        self.slice_label_widgets: dict[str, QLabel] = {}
        self.machine_label_widgets: dict[str, QLabel] = {}
        self.path_filter_checks: dict[str, QCheckBox] = {}

        self.preview = PreviewCanvas()
        self.log_box = QPlainTextEdit()
        self.log_box.setObjectName("logBox")
        self.log_box.setReadOnly(True)
        self.log_box.setLineWrapMode(PLAIN_TEXT_NO_WRAP)

        self.model_info = QLabel()
        self.model_info.setWordWrap(True)
        self.slice_mode_label = QLabel()
        self.slice_mode_combo = NoWheelComboBox()
        self.slice_mode_combo.setObjectName("softInput")
        self.slice_mode_combo.addItem("", "hybrid")
        self.slice_mode_combo.addItem("", "planar")
        self.slice_mode_combo.currentIndexChanged.connect(self._on_slice_mode_changed)
        self._set_expand_policy(self.slice_mode_combo)
        self.face_selection_title = QLabel()
        self.face_selection_title.setWordWrap(True)
        self.face_selection_help = QLabel()
        self.face_selection_help.setWordWrap(True)
        self.enable_face_picking_checkbox = QCheckBox()
        self.enable_face_picking_checkbox.toggled.connect(self._on_face_picking_toggled)
        self.face_pick_target_label = QLabel()
        self.face_pick_target_combo = NoWheelComboBox()
        self.face_pick_target_combo.setObjectName("softInput")
        self.face_pick_target_combo.addItem("", "substrate")
        self.face_pick_target_combo.addItem("", "conformal")
        self._set_expand_policy(self.face_pick_target_combo)
        self.clear_substrate_faces_button = QPushButton()
        self.clear_substrate_faces_button.setObjectName("secondaryButton")
        self.clear_substrate_faces_button.clicked.connect(lambda: self._clear_face_selection("substrate"))
        self.clear_conformal_faces_button = QPushButton()
        self.clear_conformal_faces_button.setObjectName("secondaryButton")
        self.clear_conformal_faces_button.clicked.connect(lambda: self._clear_face_selection("conformal"))
        self.face_selection_summary = QLabel()
        self.face_selection_summary.setWordWrap(True)
        self.face_brush_help = QLabel()
        self.face_brush_help.setWordWrap(True)
        self.face_brush_label = QLabel()
        self.face_brush_enabled = BooleanChoice(False)
        self.face_brush_enabled.on_changed(lambda _: self._on_face_brush_settings_changed())
        self.face_brush_size_label = QLabel()
        self.face_brush_size_combo = NoWheelComboBox()
        self.face_brush_size_combo.setObjectName("softInput")
        self.face_brush_size_combo.addItem("", 18)
        self.face_brush_size_combo.addItem("", 30)
        self.face_brush_size_combo.addItem("", 44)
        self.face_brush_size_combo.setCurrentIndex(1)
        self.face_brush_size_combo.currentIndexChanged.connect(self._on_face_brush_settings_changed)
        self._set_expand_policy(self.face_brush_size_combo)
        self.component_selection_title = QLabel()
        self.component_selection_title.setWordWrap(True)
        self.component_summary = QLabel()
        self.component_summary.setWordWrap(True)
        self.selection_section = CollapsibleSection()
        self.substrate_component_label = QLabel()
        self.substrate_component_combo = NoWheelComboBox()
        self.substrate_component_combo.setObjectName("softInput")
        self.substrate_component_combo.currentIndexChanged.connect(self._on_component_selection_changed)
        self._set_expand_policy(self.substrate_component_combo)
        self.conformal_components_label = QLabel()
        self.conformal_components_host = QWidget()
        self.conformal_components_layout = QVBoxLayout()
        self.conformal_components_layout.setContentsMargins(0, 0, 0, 0)
        self.conformal_components_layout.setSpacing(6)
        self.conformal_components_host.setLayout(self.conformal_components_layout)
        self.conformal_component_checks: dict[int, QCheckBox] = {}
        self.stats_info = QLabel()
        self.stats_info.setWordWrap(True)
        self.machine_profile_info = QLabel()
        self.machine_profile_info.setWordWrap(True)
        self.transform_info = QLabel()
        self.transform_info.setWordWrap(True)
        self.transform_help = QLabel()
        self.transform_help.setWordWrap(True)

        self._build_ui()
        self._apply_theme()
        self.reset_machine_defaults(log=False)
        self._retranslate_ui()
        self._set_path_filter_enabled(False)
        self._append_log(self.t("ready_log"))

    def t(self, key: str, **kwargs: object) -> str:
        return UI_TEXT[self.language][key].format(**kwargs)

    def _build_ui(self) -> None:
        self.open_button = QPushButton()
        self.open_button.setObjectName("secondaryButton")
        self.open_button.clicked.connect(self.open_model)
        self.demo_button = QPushButton()
        self.demo_button.setObjectName("secondaryButton")
        self.demo_button.clicked.connect(self.load_demo)
        self.slice_button = QPushButton()
        self.slice_button.setObjectName("primaryButton")
        self.slice_button.clicked.connect(self.run_slice)
        self.export_button = QPushButton()
        self.export_button.setObjectName("primaryButton")
        self.export_button.clicked.connect(self.export_gcode)

        self.language_label = QLabel()
        self.language_combo = NoWheelComboBox()
        self.language_combo.setObjectName("softInput")
        self.language_combo.addItem("中文", "zh")
        self.language_combo.addItem("English", "en")
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self._set_expand_policy(self.language_combo)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addWidget(self.open_button)
        button_row.addWidget(self.demo_button)
        button_row.addWidget(self.slice_button)
        button_row.addWidget(self.export_button)
        button_row.addStretch(1)
        button_row.addWidget(self.language_label)
        button_row.addWidget(self.language_combo)

        left_layout = QVBoxLayout()
        left_layout.setSpacing(14)
        left_layout.addLayout(button_row)
        left_layout.addWidget(self._build_model_group())
        left_layout.addWidget(self._build_transform_group())
        left_layout.addWidget(self._build_slice_group())
        left_layout.addWidget(self._build_machine_group())
        left_layout.addStretch(1)

        left_panel = QWidget()
        left_panel.setLayout(left_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left_panel)
        scroll.setMinimumWidth(560)

        right_layout = QVBoxLayout()
        right_layout.setSpacing(12)
        right_layout.addWidget(self._build_preview_group())
        right_layout.addWidget(self.preview, stretch=4)
        self.log_title = QLabel()
        right_layout.addWidget(self.log_title)
        right_layout.addWidget(self.log_box, stretch=2)

        right_panel = QWidget()
        right_panel.setLayout(right_layout)

        splitter = QSplitter(QT_HORIZONTAL)
        splitter.addWidget(scroll)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)
        layout.addWidget(splitter)
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.resize(1500, 920)

    def _apply_theme(self) -> None:
        checkmark_icon = (Path(__file__).resolve().parent / "assets" / "checkmark_black.svg").as_posix()
        style = """
            QMainWindow, QWidget {
                background: #f5f5f7;
                color: #1d1d1f;
                font-family: 'Segoe UI';
                font-size: 13px;
            }
            QScrollArea, QScrollArea > QWidget > QWidget {
                background: transparent;
                border: none;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 18px;
                margin-top: 18px;
                padding: 18px 16px 14px 16px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                background: #f5f5f7;
                color: #1d1d1f;
            }
            QLabel {
                background: transparent;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 14px;
                padding: 10px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #ececf0;
                border-color: #b8b8be;
            }
            QPushButton:pressed {
                background: #d9d9de;
            }
            QPushButton#primaryButton {
                background: #1d1d1f;
                color: #f5f5f7;
                border: 1px solid #1d1d1f;
            }
            QPushButton#primaryButton:hover {
                background: #313135;
                border-color: #313135;
            }
            QPushButton#primaryButton:pressed {
                background: #111113;
                border-color: #111113;
            }
            QPushButton#secondaryButton {
                background: #ffffff;
                color: #1d1d1f;
            }
            QComboBox, QDoubleSpinBox, QSpinBox, QPlainTextEdit {
                background: #ffffff;
                border: 1px solid #d2d2d7;
                border-radius: 12px;
                padding: 8px 10px;
                selection-background-color: #1d1d1f;
                selection-color: #f5f5f7;
            }
            QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover, QPlainTextEdit:hover {
                border-color: #b8b8be;
            }
            QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QPlainTextEdit:focus {
                border: 1px solid #1d1d1f;
            }
            QComboBox::drop-down {
                width: 28px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                margin-right: 6px;
            }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
            QSpinBox::up-button, QSpinBox::down-button {
                width: 0px;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            QPlainTextEdit#logBox {
                background: #fbfbfd;
                font-family: 'Consolas';
                font-size: 12px;
            }
            QCheckBox {
                spacing: 8px;
                background: transparent;
            }
            QCheckBox:disabled {
                color: #8e8e93;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #6e6e73;
                border-radius: 6px;
                background: #ffffff;
            }
            QCheckBox::indicator:hover {
                border-color: #1d1d1f;
                background: #f7f7fa;
            }
            QCheckBox::indicator:pressed {
                background: #e6e6ea;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #1d1d1f;
                background: #ffffff;
                image: url("__CHECKMARK_ICON__");
            }
            QCheckBox::indicator:checked:hover {
                background: #f7f7fa;
            }
            QCheckBox::indicator:disabled {
                border-color: #c7c7cc;
                background: #f0f0f3;
            }
            QPushButton#choiceButton {
                border-radius: 12px;
                padding: 8px 14px;
                font-weight: 700;
            }
            QPushButton#choiceButton[selected="true"] {
                background: #1d1d1f;
                color: #f5f5f7;
                border: 1px solid #1d1d1f;
            }
            QPushButton#choiceButton[selected="true"]:hover {
                background: #313135;
                border-color: #313135;
            }
            QPushButton#choiceButton[selected="false"] {
                background: #ffffff;
                color: #6e6e73;
                border: 1px solid #c7c7cc;
            }
            QPushButton#choiceButton[selected="false"]:hover {
                background: #f7f7fa;
                color: #1d1d1f;
                border-color: #8e8e93;
            }
            QPushButton#collapsibleHeader {
                background: #fbfbfd;
                border: 1px solid #d2d2d7;
                border-radius: 14px;
                padding: 10px 14px;
                font-weight: 700;
                text-align: left;
            }
            QPushButton#collapsibleHeader:hover {
                background: #f0f0f4;
                border-color: #b8b8be;
            }
            QSplitter::handle {
                background: #d2d2d7;
                width: 2px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 6px 0 6px 0;
            }
            QScrollBar::handle:vertical {
                background: #c2c2c7;
                border-radius: 5px;
                min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 10px;
                margin: 0 6px 0 6px;
            }
            QScrollBar::handle:horizontal {
                background: #c2c2c7;
                border-radius: 5px;
                min-width: 24px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
                border: none;
            }
            """
        self.setStyleSheet(style.replace("__CHECKMARK_ICON__", checkmark_icon))

    def _build_model_group(self) -> QGroupBox:
        self.model_group = QGroupBox()
        layout = QVBoxLayout()
        layout.addWidget(self.model_info)
        mode_form = QFormLayout()
        mode_form.addRow(self.slice_mode_label, self.slice_mode_combo)
        layout.addLayout(mode_form)

        selection_layout = QVBoxLayout()
        selection_layout.setContentsMargins(0, 0, 0, 0)
        selection_layout.setSpacing(10)
        selection_layout.addWidget(self.face_selection_title)
        selection_layout.addWidget(self.face_selection_help)
        selection_layout.addWidget(self.enable_face_picking_checkbox)
        face_form = QFormLayout()
        face_form.addRow(self.face_pick_target_label, self.face_pick_target_combo)
        face_form.addRow(self.face_brush_label, self.face_brush_enabled)
        face_form.addRow(self.face_brush_size_label, self.face_brush_size_combo)
        selection_layout.addLayout(face_form)
        selection_layout.addWidget(self.face_brush_help)
        face_button_row = QHBoxLayout()
        face_button_row.setSpacing(10)
        face_button_row.addWidget(self.clear_substrate_faces_button)
        face_button_row.addWidget(self.clear_conformal_faces_button)
        face_button_row.addStretch(1)
        selection_layout.addLayout(face_button_row)
        selection_layout.addWidget(self.face_selection_summary)
        selection_layout.addWidget(self.component_selection_title)
        selection_layout.addWidget(self.component_summary)

        component_form = QFormLayout()
        component_form.addRow(self.substrate_component_label, self.substrate_component_combo)
        component_form.addRow(self.conformal_components_label, self.conformal_components_host)
        selection_layout.addLayout(component_form)
        self.selection_section.set_content_layout(selection_layout)
        layout.addWidget(self.selection_section)
        layout.addWidget(self.stats_info)
        self.model_group.setLayout(layout)
        return self.model_group

    def _build_preview_group(self) -> QGroupBox:
        self.preview_group = QGroupBox()
        layout = QVBoxLayout()

        self.preview_help_label = QLabel()
        self.preview_help_label.setWordWrap(True)
        layout.addWidget(self.preview_help_label)

        self.show_mesh_checkbox = QCheckBox()
        self.show_mesh_checkbox.setChecked(True)
        self.show_mesh_checkbox.toggled.connect(self._update_preview_visibility)
        layout.addWidget(self.show_mesh_checkbox)

        for kind in PATH_KIND_ORDER:
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            checkbox.setStyleSheet(f"color: {PATH_STYLE_MAP[kind]['color']}; font-weight: 600;")
            checkbox.toggled.connect(self._update_preview_visibility)
            self.path_filter_checks[kind] = checkbox
            layout.addWidget(checkbox)

        self.preview_group.setLayout(layout)
        return self.preview_group

    def _build_transform_group(self) -> QGroupBox:
        self.transform_group = QGroupBox()
        layout = QVBoxLayout()
        layout.addWidget(self.transform_help)

        form = QFormLayout()
        self.transform_rotation_axis_label = QLabel()
        self.transform_rotation_angle_label = QLabel()
        self.transform_translation_axis_label = QLabel()
        self.transform_translation_distance_label = QLabel()

        self.rotation_axis_combo = NoWheelComboBox()
        self.translation_axis_combo = NoWheelComboBox()
        for axis in AXES:
            self.rotation_axis_combo.addItem(axis, axis)
            self.translation_axis_combo.addItem(axis, axis)
        self._set_expand_policy(self.rotation_axis_combo)
        self._set_expand_policy(self.translation_axis_combo)

        self.rotation_angle_spin = self._double_spin(-360.0, 360.0, 90.0, 1.0)
        self.translation_distance_spin = self._double_spin(-1000.0, 1000.0, 10.0, 1.0)

        form.addRow(self.transform_rotation_axis_label, self.rotation_axis_combo)
        form.addRow(self.transform_rotation_angle_label, self.rotation_angle_spin)
        form.addRow(self.transform_translation_axis_label, self.translation_axis_combo)
        form.addRow(self.transform_translation_distance_label, self.translation_distance_spin)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.apply_rotation_button = QPushButton()
        self.apply_rotation_button.clicked.connect(self.apply_rotation)
        self.apply_translation_button = QPushButton()
        self.apply_translation_button.clicked.connect(self.apply_translation)
        self.reset_placement_button = QPushButton()
        self.reset_placement_button.clicked.connect(self.reset_placement)
        button_row.addWidget(self.apply_rotation_button)
        button_row.addWidget(self.apply_translation_button)
        button_row.addWidget(self.reset_placement_button)

        layout.addLayout(form)
        layout.addLayout(button_row)
        layout.addWidget(self.transform_info)
        self.transform_group.setLayout(layout)
        return self.transform_group

    def _build_slice_group(self) -> QGroupBox:
        self.slice_group = QGroupBox()
        form = QFormLayout()

        self.slice_controls["nozzle_diameter_mm"] = self._double_spin(0.2, 5.0, 0.4, 0.05)
        self.slice_controls["layer_height_mm"] = self._double_spin(0.05, 20.0, 0.2, 0.05)
        self.slice_controls["line_spacing_mm"] = self._double_spin(0.2, 20.0, 0.45, 0.05)
        self.slice_controls["perimeters"] = self._int_spin(0, 8, 2, 1)
        self.slice_controls["infill_angle_deg"] = self._double_spin(0.0, 180.0, 45.0, 5.0)
        self.slice_controls["segment_length_mm"] = self._double_spin(0.1, 20.0, 0.8, 0.1)
        self.slice_controls["grid_step_mm"] = self._double_spin(0.1, 20.0, 0.6, 0.1)
        self.slice_controls["top_normal_threshold"] = self._double_spin(-1.0, 1.0, -0.4, 0.05)
        self.slice_controls["print_speed_mm_s"] = self._double_spin(1.0, 500.0, 18.0, 1.0)
        self.slice_controls["planar_print_speed_mm_s"] = self._double_spin(1.0, 500.0, 24.0, 1.0)
        self.slice_controls["travel_speed_mm_s"] = self._double_spin(1.0, 500.0, 60.0, 5.0)
        self.slice_controls["travel_height_mm"] = self._double_spin(0.0, 50.0, 2.0, 0.2)
        self.slice_controls["filament_diameter_mm"] = self._double_spin(1.0, 5.0, 1.75, 0.05)
        self.slice_controls["extrusion_multiplier"] = self._double_spin(0.2, 3.0, 1.0, 0.05)
        self.slice_controls["retraction_mm"] = self._double_spin(0.0, 20.0, 0.8, 0.1)
        self.slice_controls["retract_speed_mm_s"] = self._double_spin(1.0, 200.0, 25.0, 1.0)
        self.slice_controls["prime_speed_mm_s"] = self._double_spin(1.0, 200.0, 20.0, 1.0)
        self.slice_controls["core_transition_height_mm"] = self._double_spin(0.0, 2000.0, 0.0, 1.0)
        self.slice_controls["core_transition_percentile"] = self._double_spin(0.0, 25.0, 0.0, 0.1)
        self.slice_controls["planar_layer_height_mm"] = self._double_spin(0.0, 50.0, 0.0, 0.1)
        self.slice_controls["planar_line_spacing_mm"] = self._double_spin(0.0, 50.0, 0.0, 0.1)
        self.slice_controls["planar_perimeters"] = self._int_spin(1, 4, 1, 1)
        self.slice_controls["planar_infill_angle_deg"] = self._double_spin(0.0, 180.0, 0.0, 5.0)

        include_infill = BooleanChoice(True)
        self.slice_controls["include_infill"] = include_infill

        auto_center = BooleanChoice(True)
        self.slice_controls["auto_center_model"] = auto_center

        enable_planar = BooleanChoice(True)
        self.slice_controls["enable_planar_core"] = enable_planar

        auto_transition = BooleanChoice(True)
        self.slice_controls["auto_core_transition"] = auto_transition

        planar_include_infill = BooleanChoice(True)
        self.slice_controls["planar_include_infill"] = planar_include_infill

        field_pairs = [
            ("nozzle_diameter_mm", self.slice_controls["nozzle_diameter_mm"]),
            ("layer_height_mm", self.slice_controls["layer_height_mm"]),
            ("line_spacing_mm", self.slice_controls["line_spacing_mm"]),
            ("perimeters", self.slice_controls["perimeters"]),
            ("include_infill", include_infill),
            ("infill_angle_deg", self.slice_controls["infill_angle_deg"]),
            ("segment_length_mm", self.slice_controls["segment_length_mm"]),
            ("grid_step_mm", self.slice_controls["grid_step_mm"]),
            ("top_normal_threshold", self.slice_controls["top_normal_threshold"]),
            ("auto_center_model", auto_center),
            ("enable_planar_core", enable_planar),
            ("auto_core_transition", auto_transition),
            ("core_transition_height_mm", self.slice_controls["core_transition_height_mm"]),
            ("core_transition_percentile", self.slice_controls["core_transition_percentile"]),
            ("planar_layer_height_mm", self.slice_controls["planar_layer_height_mm"]),
            ("planar_line_spacing_mm", self.slice_controls["planar_line_spacing_mm"]),
            ("planar_perimeters", self.slice_controls["planar_perimeters"]),
            ("planar_include_infill", planar_include_infill),
            ("planar_infill_angle_deg", self.slice_controls["planar_infill_angle_deg"]),
            ("print_speed_mm_s", self.slice_controls["print_speed_mm_s"]),
            ("planar_print_speed_mm_s", self.slice_controls["planar_print_speed_mm_s"]),
            ("travel_speed_mm_s", self.slice_controls["travel_speed_mm_s"]),
            ("travel_height_mm", self.slice_controls["travel_height_mm"]),
            ("filament_diameter_mm", self.slice_controls["filament_diameter_mm"]),
            ("extrusion_multiplier", self.slice_controls["extrusion_multiplier"]),
            ("retraction_mm", self.slice_controls["retraction_mm"]),
            ("retract_speed_mm_s", self.slice_controls["retract_speed_mm_s"]),
            ("prime_speed_mm_s", self.slice_controls["prime_speed_mm_s"]),
        ]
        for key, field in field_pairs:
            self._add_form_row(form, self.slice_label_widgets, key, field)

        self.slice_group.setLayout(form)
        return self.slice_group

    def _build_machine_group(self) -> QGroupBox:
        self.machine_group = QGroupBox()
        layout = QVBoxLayout()

        self.machine_intro = QLabel()
        self.machine_intro.setWordWrap(True)
        self.reset_machine_button = QPushButton()
        self.reset_machine_button.clicked.connect(self.reset_machine_defaults)

        header_row = QHBoxLayout()
        header_row.addWidget(self.reset_machine_button)
        header_row.addStretch(1)

        form = QFormLayout()
        self.machine_controls["x_offset_mm"] = self._double_spin(-1000.0, 1000.0, 0.0, 1.0)
        self.machine_controls["y_offset_mm"] = self._double_spin(-1000.0, 1000.0, 0.0, 1.0)
        self.machine_controls["z_offset_mm"] = self._double_spin(-1000.0, 1000.0, 0.0, 1.0)
        self.machine_controls["rotary_center_x_mm"] = self._double_spin(-1000.0, 1000.0, 0.0, 1.0)
        self.machine_controls["rotary_center_y_mm"] = self._double_spin(-1000.0, 1000.0, 0.0, 1.0)
        self.machine_controls["rotary_center_z_mm"] = self._double_spin(-1000.0, 1000.0, 0.0, 1.0)
        self.machine_controls["bed_diameter_mm"] = self._double_spin(10.0, 500.0, 90.0, 1.0)
        self.machine_controls["rotary_scale_radius_mm"] = self._double_spin(1.0, 1000.0, 35.0, 1.0)
        self.machine_controls["phase_change_lift_mm"] = self._double_spin(0.0, 100.0, 8.0, 0.5)
        self.machine_controls["u_axis_sign"] = self._sign_combo(1)
        self.machine_controls["v_axis_sign"] = self._sign_combo(1)
        self.machine_controls["u_zero_offset_deg"] = self._double_spin(-720.0, 720.0, 0.0, 1.0)
        self.machine_controls["v_zero_offset_deg"] = self._double_spin(-720.0, 720.0, 0.0, 1.0)
        self.machine_controls["home_u_deg"] = self._double_spin(-720.0, 720.0, 0.0, 1.0)
        self.machine_controls["home_v_deg"] = self._double_spin(-720.0, 720.0, 0.0, 1.0)
        self.machine_controls["min_u_deg"] = self._double_spin(-1440.0, 1440.0, -95.0, 1.0)
        self.machine_controls["max_u_deg"] = self._double_spin(-1440.0, 1440.0, 95.0, 1.0)
        self.machine_controls["min_v_deg"] = self._double_spin(-1440.0, 1440.0, -540.0, 5.0)
        self.machine_controls["max_v_deg"] = self._double_spin(-1440.0, 1440.0, 540.0, 5.0)
        self.machine_controls["max_feed_mm_min"] = self._double_spin(100.0, 50000.0, 9000.0, 100.0)
        self.machine_controls["start_gcode_template"] = self._plain_text_box(84)
        self.machine_controls["phase_change_gcode_template"] = self._plain_text_box(68)
        self.machine_controls["end_gcode_template"] = self._plain_text_box(84)

        field_pairs = [
            ("preset_summary", self.machine_profile_info),
            ("x_offset_mm", self.machine_controls["x_offset_mm"]),
            ("y_offset_mm", self.machine_controls["y_offset_mm"]),
            ("z_offset_mm", self.machine_controls["z_offset_mm"]),
            ("rotary_center_x_mm", self.machine_controls["rotary_center_x_mm"]),
            ("rotary_center_y_mm", self.machine_controls["rotary_center_y_mm"]),
            ("rotary_center_z_mm", self.machine_controls["rotary_center_z_mm"]),
            ("bed_diameter_mm", self.machine_controls["bed_diameter_mm"]),
            ("rotary_scale_radius_mm", self.machine_controls["rotary_scale_radius_mm"]),
            ("phase_change_lift_mm", self.machine_controls["phase_change_lift_mm"]),
            ("u_axis_sign", self.machine_controls["u_axis_sign"]),
            ("v_axis_sign", self.machine_controls["v_axis_sign"]),
            ("u_zero_offset_deg", self.machine_controls["u_zero_offset_deg"]),
            ("v_zero_offset_deg", self.machine_controls["v_zero_offset_deg"]),
            ("home_u_deg", self.machine_controls["home_u_deg"]),
            ("home_v_deg", self.machine_controls["home_v_deg"]),
            ("min_u_deg", self.machine_controls["min_u_deg"]),
            ("max_u_deg", self.machine_controls["max_u_deg"]),
            ("min_v_deg", self.machine_controls["min_v_deg"]),
            ("max_v_deg", self.machine_controls["max_v_deg"]),
            ("max_feed_mm_min", self.machine_controls["max_feed_mm_min"]),
            ("start_gcode_template", self.machine_controls["start_gcode_template"]),
            ("phase_change_gcode_template", self.machine_controls["phase_change_gcode_template"]),
            ("end_gcode_template", self.machine_controls["end_gcode_template"]),
        ]
        for key, field in field_pairs:
            self._add_form_row(form, self.machine_label_widgets, key, field)

        layout.addWidget(self.machine_intro)
        layout.addLayout(header_row)
        layout.addLayout(form)
        self.machine_group.setLayout(layout)
        return self.machine_group

    def _hide_spin_buttons(self, widget: QAbstractSpinBox) -> None:
        if hasattr(QAbstractSpinBox, "ButtonSymbols"):
            widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        else:
            widget.setButtonSymbols(QAbstractSpinBox.NoButtons)

    def _double_spin(self, minimum: float, maximum: float, value: float, step: float) -> QDoubleSpinBox:
        widget = NoWheelDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSingleStep(step)
        widget.setDecimals(4 if step < 0.1 else 3)
        self._hide_spin_buttons(widget)
        self._set_expand_policy(widget)
        return widget

    def _int_spin(self, minimum: int, maximum: int, value: int, step: int) -> QSpinBox:
        widget = NoWheelSpinBox()
        widget.setRange(minimum, maximum)
        widget.setValue(value)
        widget.setSingleStep(step)
        self._hide_spin_buttons(widget)
        self._set_expand_policy(widget)
        return widget

    def _sign_combo(self, sign_value: int) -> QComboBox:
        widget = NoWheelComboBox()
        widget.addItem("1", 1)
        widget.addItem("-1", -1)
        widget.setCurrentIndex(0 if sign_value >= 0 else 1)
        self._set_expand_policy(widget)
        return widget

    def _plain_text_box(self, minimum_height: int) -> QPlainTextEdit:
        widget = QPlainTextEdit()
        widget.setLineWrapMode(PLAIN_TEXT_NO_WRAP)
        widget.setMinimumHeight(minimum_height)
        if hasattr(QSizePolicy, "Policy"):
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        else:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return widget

    def _set_expand_policy(self, widget: QWidget) -> None:
        if hasattr(QSizePolicy, "Policy"):
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _add_form_row(self, form: QFormLayout, store: dict[str, QLabel], key: str, field: QWidget) -> None:
        label = QLabel()
        label.setWordWrap(True)
        store[key] = label
        form.addRow(label, field)

    def _file_dialog_option(self):
        option_enum = getattr(QFileDialog, "Option", None)
        if option_enum is not None:
            return option_enum.DontUseNativeDialog
        return QFileDialog.DontUseNativeDialog

    def _default_model_directory(self) -> str:
        example_dir = Path("model-example")
        return str(example_dir.resolve()) if example_dir.exists() else ""

    def _get_open_file_name(self, caption: str, directory: str, file_filter: str) -> tuple[str, str]:
        # Avoid native Windows dialog crashes caused by shell extensions or Qt/plugin mismatches.
        return QFileDialog.getOpenFileName(
            self,
            caption,
            directory,
            file_filter,
            options=self._file_dialog_option(),
        )

    def _get_save_file_name(self, caption: str, directory: str, file_filter: str) -> tuple[str, str]:
        return QFileDialog.getSaveFileName(
            self,
            caption,
            directory,
            file_filter,
            options=self._file_dialog_option(),
        )

    def _on_language_changed(self) -> None:
        language = str(self.language_combo.currentData())
        if language == self.language:
            return
        self.language = language
        self._retranslate_ui()

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self.t("app_title", api=QT_API))
        self.open_button.setText(self.t("open_model"))
        self.demo_button.setText(self.t("load_demo"))
        self.slice_button.setText(self.t("slice"))
        self.export_button.setText(self.t("export_gcode"))
        self.language_label.setText(self.t("language"))
        self.log_title.setText(self.t("log_title"))
        self.language_combo.setItemText(0, self.t("language_name_zh"))
        self.language_combo.setItemText(1, self.t("language_name_en"))

        self.model_group.setTitle(self.t("model_group"))
        self.preview_group.setTitle(self.t("preview_group"))
        self.transform_group.setTitle(self.t("transform_group"))
        self.slice_group.setTitle(self.t("slicing_group"))
        self.machine_group.setTitle(self.t("machine_group"))
        self.slice_mode_label.setText(self.t("slice_mode"))
        self.slice_mode_combo.setItemText(0, self.t("slice_mode_hybrid"))
        self.slice_mode_combo.setItemText(1, self.t("slice_mode_planar"))
        self.face_selection_title.setText(self.t("face_selection"))
        self.face_selection_help.setText(self.t("face_selection_help"))
        self.enable_face_picking_checkbox.setText(self.t("enable_face_picking"))
        self.face_pick_target_label.setText(self.t("face_pick_target"))
        self.face_pick_target_combo.setItemText(0, self.t("face_pick_target_substrate"))
        self.face_pick_target_combo.setItemText(1, self.t("face_pick_target_conformal"))
        self.face_brush_label.setText(self.t("face_brush"))
        self.face_brush_help.setText(self.t("face_brush_help"))
        self.face_brush_size_label.setText(self.t("face_brush_size"))
        self.face_brush_size_combo.setItemText(0, self.t("brush_size_small"))
        self.face_brush_size_combo.setItemText(1, self.t("brush_size_medium"))
        self.face_brush_size_combo.setItemText(2, self.t("brush_size_large"))
        self.clear_substrate_faces_button.setText(self.t("clear_substrate_faces"))
        self.clear_conformal_faces_button.setText(self.t("clear_conformal_faces"))
        self.component_selection_title.setText(self.t("component_selection"))
        self.selection_section.set_title(self.t("selection_tools_section"))
        self.substrate_component_label.setText(self.t("substrate_component"))
        self.conformal_components_label.setText(self.t("conformal_components"))

        self.preview_help_label.setText(self.t("preview_help"))
        self.show_mesh_checkbox.setText(self.t("show_mesh"))
        for kind in PATH_KIND_ORDER:
            self.path_filter_checks[kind].setText(self.t(PATH_KIND_LABEL_KEYS[kind]))

        self.transform_help.setText(self.t("transform_help"))
        self.transform_rotation_axis_label.setText(self.t("rotation_axis"))
        self.transform_rotation_angle_label.setText(self.t("rotation_angle_deg"))
        self.transform_translation_axis_label.setText(self.t("translation_axis"))
        self.transform_translation_distance_label.setText(self.t("translation_distance_mm"))
        self.apply_rotation_button.setText(self.t("apply_rotation"))
        self.apply_translation_button.setText(self.t("apply_translation"))
        self.reset_placement_button.setText(self.t("reset_placement"))

        for key, label in self.slice_label_widgets.items():
            label.setText(self.t(key))
        for key, label in self.machine_label_widgets.items():
            label.setText(self.t(key))

        self.machine_intro.setText(self.t("machine_intro"))
        self.reset_machine_button.setText(self.t("machine_reset"))
        self._update_sign_combo_text(self.machine_controls["u_axis_sign"])
        self._update_sign_combo_text(self.machine_controls["v_axis_sign"])
        for control in self.slice_controls.values():
            if isinstance(control, BooleanChoice):
                control.set_labels(self.t("choice_yes"), self.t("choice_no"))
        self.face_brush_enabled.set_labels(self.t("choice_yes"), self.t("choice_no"))

        self._refresh_model_info()
        self._refresh_transform_info()
        self._refresh_machine_profile_info()
        self._refresh_stats(self.export_warnings)
        self._refresh_face_selection_summary()
        self._sync_face_brush_state()
        self._sync_component_widgets()

    def _update_sign_combo_text(self, combo: object) -> None:
        if isinstance(combo, QComboBox):
            combo.setItemText(0, self.t("sign_same_math"))
            combo.setItemText(1, self.t("sign_invert_direction"))

    def _set_path_filter_enabled(self, enabled: bool) -> None:
        for checkbox in self.path_filter_checks.values():
            checkbox.setEnabled(True)
            checkbox.setToolTip(self.t("path_filter_ready_tooltip") if enabled else self.t("path_filter_waiting_tooltip"))

    def _selected_visible_kinds(self) -> set[str]:
        return {kind for kind, checkbox in self.path_filter_checks.items() if checkbox.isChecked()}

    def _update_preview_visibility(self) -> None:
        self.preview.set_visibility(
            show_mesh=self.show_mesh_checkbox.isChecked(),
            visible_kinds=self._selected_visible_kinds(),
        )

    def _current_slice_mode(self) -> str:
        return str(self.slice_mode_combo.currentData() or "hybrid")

    def _selection_cache_path(self) -> Path:
        return Path("outputs") / "selection_cache.json"

    def _mesh_selection_cache_key(self) -> str | None:
        if self.mesh is None:
            return None
        source = self.mesh.source_path or f"demo::{self.mesh.name}"
        if self.mesh.source_path:
            try:
                source = str(Path(source).resolve())
            except OSError:
                source = str(source)
        return f"{source}|faces={len(self.mesh.faces)}|verts={len(self.mesh.vertices)}"

    def _load_cached_face_selection(self) -> None:
        self.selected_substrate_face_indices.clear()
        self.selected_conformal_face_indices.clear()
        cache_key = self._mesh_selection_cache_key()
        if cache_key is None:
            return
        cache_path = self._selection_cache_path()
        if not cache_path.exists():
            return
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return
        entries = payload.get("entries", {})
        entry = entries.get(cache_key, {})
        face_count = len(self.mesh.faces) if self.mesh is not None else 0
        self.selected_substrate_face_indices = {
            int(index) for index in entry.get("substrate_faces", []) if 0 <= int(index) < face_count
        }
        self.selected_conformal_face_indices = {
            int(index) for index in entry.get("conformal_faces", []) if 0 <= int(index) < face_count
        }
        self.selected_conformal_face_indices.difference_update(self.selected_substrate_face_indices)
        if self.selected_substrate_face_indices or self.selected_conformal_face_indices:
            self._append_log(
                self.t(
                    "selection_cache_loaded_log",
                    substrate=len(self.selected_substrate_face_indices),
                    conformal=len(self.selected_conformal_face_indices),
                )
            )

    def _save_cached_face_selection(self) -> None:
        cache_key = self._mesh_selection_cache_key()
        if cache_key is None:
            return
        cache_path = self._selection_cache_path()
        try:
            if cache_path.exists():
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
            else:
                payload = {}
        except Exception:
            payload = {}
        entries = payload.setdefault("entries", {})
        if self.selected_substrate_face_indices or self.selected_conformal_face_indices:
            entries[cache_key] = {
                "substrate_faces": sorted(int(index) for index in self.selected_substrate_face_indices),
                "conformal_faces": sorted(int(index) for index in self.selected_conformal_face_indices),
            }
        else:
            entries.pop(cache_key, None)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _refresh_face_selection_summary(self) -> None:
        substrate_count = len(self.selected_substrate_face_indices)
        conformal_count = len(self.selected_conformal_face_indices)
        self.face_selection_summary.setText(
            self.t(
                "face_selection_summary",
                substrate_count=substrate_count,
                conformal_count=conformal_count,
                pick_state=self.t("face_picking_on") if self.enable_face_picking_checkbox.isChecked() else self.t("face_picking_off"),
                target=self.t(
                    "face_pick_target_substrate"
                    if self._current_face_pick_target() == "substrate"
                    else "face_pick_target_conformal"
                ),
                brush_state=(
                    self.t("face_picking_on")
                    if self.enable_face_picking_checkbox.isChecked() and self.face_brush_enabled.isChecked()
                    else self.t("face_picking_off")
                ),
                brush_size=self._current_face_brush_label(),
            )
        )
        self.clear_substrate_faces_button.setEnabled(substrate_count > 0)
        self.clear_conformal_faces_button.setEnabled(conformal_count > 0)

    def _clear_face_selection(self, group: str | None = None) -> None:
        if group == "substrate":
            self.selected_substrate_face_indices.clear()
        elif group == "conformal":
            self.selected_conformal_face_indices.clear()
        else:
            self.selected_substrate_face_indices.clear()
            self.selected_conformal_face_indices.clear()
        self._save_cached_face_selection()
        self._invalidate_slice_result()
        self._refresh_face_selection_summary()
        self._render_current_preview(preserve_camera=True)

    def _on_slice_mode_changed(self) -> None:
        self._invalidate_slice_result()
        self._refresh_face_selection_summary()

    def _on_face_picking_toggled(self, checked: bool) -> None:
        self.preview.set_face_picking(checked, self._on_preview_faces_picked if checked else None)
        self._sync_face_brush_state()
        self._refresh_face_selection_summary()

    def _current_face_pick_target(self) -> str:
        return str(self.face_pick_target_combo.currentData() or "substrate")

    def _current_face_brush_label(self) -> str:
        label_keys = ["brush_size_small", "brush_size_medium", "brush_size_large"]
        current_index = min(max(self.face_brush_size_combo.currentIndex(), 0), len(label_keys) - 1)
        return self.t(label_keys[current_index])

    def _on_face_brush_settings_changed(self) -> None:
        self._sync_face_brush_state()
        self._refresh_face_selection_summary()

    def _sync_face_brush_state(self) -> None:
        picking_enabled = self.enable_face_picking_checkbox.isChecked()
        self.face_brush_enabled.setEnabled(picking_enabled)
        self.face_brush_size_combo.setEnabled(picking_enabled)
        brush_enabled = picking_enabled and self.face_brush_enabled.isChecked()
        self.preview.set_face_brush(brush_enabled, int(self.face_brush_size_combo.currentData() or 18))

    def _on_preview_faces_picked(self, face_indices: list[int]) -> None:
        if self.mesh is None:
            return
        valid_faces = sorted({int(face_index) for face_index in face_indices if 0 <= int(face_index) < len(self.mesh.faces)})
        if not valid_faces:
            return

        target = self._current_face_pick_target()
        brush_enabled = self.enable_face_picking_checkbox.isChecked() and self.face_brush_enabled.isChecked()
        changed = False
        for face_index in valid_faces:
            if target == "substrate":
                if brush_enabled:
                    if face_index not in self.selected_substrate_face_indices:
                        self.selected_substrate_face_indices.add(face_index)
                        self.selected_conformal_face_indices.discard(face_index)
                        changed = True
                    continue
                if face_index in self.selected_substrate_face_indices:
                    self.selected_substrate_face_indices.discard(face_index)
                else:
                    self.selected_substrate_face_indices.add(face_index)
                    self.selected_conformal_face_indices.discard(face_index)
                changed = True
            else:
                if brush_enabled:
                    if face_index not in self.selected_conformal_face_indices:
                        self.selected_conformal_face_indices.add(face_index)
                        self.selected_substrate_face_indices.discard(face_index)
                        changed = True
                    continue
                if face_index in self.selected_conformal_face_indices:
                    self.selected_conformal_face_indices.discard(face_index)
                else:
                    self.selected_conformal_face_indices.add(face_index)
                    self.selected_substrate_face_indices.discard(face_index)
                changed = True
        if not changed:
            return

        self._save_cached_face_selection()
        self._invalidate_slice_result()
        self._refresh_face_selection_summary()
        self._render_current_preview(preserve_camera=True)

    def _selection_faces_for_preview(self) -> dict[str, np.ndarray]:
        return {
            "substrate": np.asarray(sorted(self.selected_substrate_face_indices), dtype=np.int32),
            "conformal": np.asarray(sorted(self.selected_conformal_face_indices), dtype=np.int32),
        }

    def _selection_center_xy(self, face_indices: set[int]) -> np.ndarray:
        if self.mesh is None or not face_indices:
            return np.zeros(2, dtype=float)
        triangles = self.mesh.face_vertices[np.asarray(sorted(face_indices), dtype=np.int32)]
        return triangles.mean(axis=(0, 1))[:2]

    def _maybe_autoclose_substrate_selection(self) -> bool:
        if self.mesh is None or not self.selected_substrate_face_indices:
            return False

        boundary_edges = selection_boundary_edges(self.mesh, self.selected_substrate_face_indices)
        if not boundary_edges:
            return False

        center_xy = self._selection_center_xy(self.selected_substrate_face_indices)
        grown_selection, added_faces = grow_face_selection(
            self.mesh,
            self.selected_substrate_face_indices,
            center_xy,
            max_layers=2,
            max_added_faces=max(24, int(len(self.selected_substrate_face_indices) * 0.18)),
        )

        small_gap_limit = max(12, int(len(self.selected_substrate_face_indices) * 0.12))
        if 0 < len(added_faces) <= small_gap_limit:
            should_close = self._ask_yes_no(
                self.t("selection_not_closed_title"),
                self.t("selection_not_closed_message_small", added=len(added_faces)),
                default_yes=True,
            )
            if should_close:
                self.selected_substrate_face_indices = {int(index) for index in grown_selection.tolist()}
                self.selected_conformal_face_indices.difference_update(self.selected_substrate_face_indices)
                self._save_cached_face_selection()
                self._refresh_face_selection_summary()
                self._render_current_preview(preserve_camera=True)
                self._append_log(self.t("selection_autoclosed_log", added=len(added_faces)))
            return False

        large_gap_limit = max(24, int(len(self.selected_substrate_face_indices) * 0.3))
        if len(added_faces) > large_gap_limit or len(boundary_edges) > max(40, int(len(self.selected_substrate_face_indices) * 0.8)):
            return self._ask_yes_no(
                self.t("selection_not_closed_title"),
                self.t("selection_not_closed_message_large"),
                default_yes=False,
            )
        return False

    def _ask_yes_no(self, title: str, message: str, *, default_yes: bool) -> bool:
        icon_enum = getattr(QMessageBox, "Icon", QMessageBox)
        role_enum = getattr(QMessageBox, "ButtonRole", QMessageBox)
        msg_box = QMessageBox(self)
        msg_box.setIcon(icon_enum.Question)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        yes_button = msg_box.addButton(self.t("choice_yes"), role_enum.YesRole)
        no_button = msg_box.addButton(self.t("choice_no"), role_enum.NoRole)
        yes_button.setObjectName("choiceButton")
        no_button.setObjectName("choiceButton")
        _set_button_selected(yes_button, True)
        _set_button_selected(no_button, False)
        msg_box.setDefaultButton(yes_button if default_yes else no_button)
        msg_box.exec()
        return msg_box.clickedButton() == yes_button

    def reset_machine_defaults(self, log: bool = True) -> None:
        self._set_machine_controls_from_params(open5x_freddi_hong_machine())
        if log:
            self._append_log(self.t("reset_machine_log"))

    def _set_machine_controls_from_params(self, machine: MachineParameters) -> None:
        for key, control in self.machine_controls.items():
            value = getattr(machine, key)
            if isinstance(control, QDoubleSpinBox):
                control.setValue(float(value))
            elif isinstance(control, QSpinBox):
                control.setValue(int(value))
            elif isinstance(control, QComboBox):
                index = control.findData(int(value))
                if index >= 0:
                    control.setCurrentIndex(index)
            elif isinstance(control, QPlainTextEdit):
                control.setPlainText(str(value))
        self._refresh_machine_profile_info()

    def _load_mesh_into_workspace(self, mesh: MeshModel, log_message: str) -> None:
        initial_mesh = mesh.centered_for_build()
        self.source_mesh = initial_mesh
        self.mesh = initial_mesh
        self.placement_rotation_deg[:] = 0.0
        self.placement_translation_mm[:] = 0.0
        self.show_mesh_checkbox.setChecked(True)

        auto_center = self.slice_controls.get("auto_center_model")
        if isinstance(auto_center, BooleanChoice):
            auto_center.setChecked(True)

        self._load_cached_face_selection()
        self._refresh_component_controls(reset_defaults=True)
        self._invalidate_slice_result()
        self._refresh_model_info()
        self._refresh_transform_info()
        self._refresh_face_selection_summary()
        self._render_current_preview()
        self._sync_face_brush_state()
        self._append_log(log_message)

    def open_model(self) -> None:
        file_path, _ = self._get_open_file_name(
            self.t("open_cad_model"),
            self._default_model_directory(),
            "CAD Model (*.stl *.step *.stp)",
        )
        if not file_path:
            return
        try:
            mesh = load_mesh(file_path)
        except Exception as exc:
            self._show_error(self.t("failed_to_load_model", error=exc))
            return
        self._load_mesh_into_workspace(mesh, self.t("loaded_model_log", path=file_path))

    def load_demo(self) -> None:
        self._load_mesh_into_workspace(generate_demo_dome_mesh(), self.t("loaded_demo_log"))

    def apply_rotation(self) -> None:
        if self.mesh is None:
            self._show_error(self.t("need_load_model"))
            return

        axis = str(self.rotation_axis_combo.currentData())
        angle = float(self.rotation_angle_spin.value())
        if abs(angle) < 1e-9:
            return

        self._disable_auto_center_for_manual_placement()
        self.mesh = self.mesh.rotated(axis, angle, center=self.mesh.bounds_center)
        self.placement_rotation_deg[_axis_index(axis)] += angle
        self._on_mesh_transform_applied(self.t("rotation_applied_log", axis=axis, angle=angle))

    def apply_translation(self) -> None:
        if self.mesh is None:
            self._show_error(self.t("need_load_model"))
            return

        axis = str(self.translation_axis_combo.currentData())
        distance = float(self.translation_distance_spin.value())
        if abs(distance) < 1e-9:
            return

        self._disable_auto_center_for_manual_placement()
        offset = np.zeros(3, dtype=float)
        offset[_axis_index(axis)] = distance
        self.mesh = self.mesh.translated(offset)
        self.placement_translation_mm[_axis_index(axis)] += distance
        self._on_mesh_transform_applied(self.t("translation_applied_log", axis=axis, distance=distance))

    def reset_placement(self) -> None:
        if self.source_mesh is None:
            self._show_error(self.t("need_load_model"))
            return

        self.mesh = self.source_mesh
        self.placement_rotation_deg[:] = 0.0
        self.placement_translation_mm[:] = 0.0
        self.show_mesh_checkbox.setChecked(True)
        self._on_mesh_transform_applied(self.t("placement_reset_log"))

    def _disable_auto_center_for_manual_placement(self) -> None:
        auto_center = self.slice_controls.get("auto_center_model")
        if isinstance(auto_center, BooleanChoice) and auto_center.isChecked():
            auto_center.setChecked(False)
            self._append_log(self.t("auto_center_disabled_log"))

    def _on_mesh_transform_applied(self, log_message: str) -> None:
        self._invalidate_slice_result()
        self._render_current_preview()
        self._refresh_model_info()
        self._refresh_transform_info()
        self._refresh_component_controls(reset_defaults=False)
        self._append_log(log_message)

    def run_slice(self) -> None:
        if self.mesh is None:
            self._show_error(self.t("need_load_model"))
            return

        try:
            slice_params = self._collect_slice_parameters()
            machine_params = self._current_machine_parameters()
            slice_mode = self._current_slice_mode()

            if slice_mode == "hybrid" and self.selected_conformal_face_indices and not self.selected_substrate_face_indices:
                should_switch_planar = self._ask_yes_no(
                    self.t("missing_substrate_title"),
                    self.t("missing_substrate_message"),
                    default_yes=False,
                )
                if should_switch_planar:
                    combo_index = self.slice_mode_combo.findData("planar")
                    if combo_index >= 0:
                        self.slice_mode_combo.setCurrentIndex(combo_index)
                    slice_mode = "planar"
                    self._append_log(self.t("switched_planar_log"))

            if slice_mode == "hybrid" and self._maybe_autoclose_substrate_selection():
                combo_index = self.slice_mode_combo.findData("planar")
                if combo_index >= 0:
                    self.slice_mode_combo.setCurrentIndex(combo_index)
                slice_mode = "planar"
                self._append_log(self.t("switched_planar_log"))

            if slice_mode == "planar":
                self.slice_result = slice_planar_model(self.mesh, slice_params)
            else:
                slice_selection = self._collect_slice_selection()
                self.slice_result = self.slicer.slice(self.mesh, slice_params, selection=slice_selection)
            self.generated_gcode, self.export_warnings = generate_gcode(
                self.slice_result,
                slice_params,
                machine_params,
            )
        except Exception as exc:
            self._show_error(self.t("slicing_failed", error=exc))
            return

        self._set_path_filter_enabled(True)
        self._render_current_preview()
        self._refresh_stats(self.export_warnings)
        self._append_log(
            self.t(
                "slicing_complete_log",
                path_count=len(self.slice_result.toolpaths),
                length=self.slice_result.total_path_length_mm,
            )
        )
        self._append_log(self.t("machine_profile_log", profile=machine_params.profile_name))
        if self.export_warnings:
            self._append_log(self.t("warnings_header") + ":\n- " + "\n- ".join(self.export_warnings))

    def export_gcode(self) -> None:
        if not self.generated_gcode:
            self._show_error(self.t("need_slice_first"))
            return

        default_name = "five_axis_toolpath.gcode"
        if self.mesh and self.mesh.source_path:
            default_name = f"{Path(self.mesh.source_path).stem}_hybrid_5axis.gcode"

        file_path, _ = self._get_save_file_name(
            self.t("save_gcode"),
            default_name,
            "G-code (*.gcode *.nc *.txt)",
        )
        if not file_path:
            return

        output_path = Path(file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.generated_gcode, encoding="utf-8")
        self._append_log(self.t("saved_gcode_log", path=file_path))

    def _collect_slice_parameters(self) -> SliceParameters:
        values = {}
        for key, control in self.slice_controls.items():
            if isinstance(control, BooleanChoice):
                values[key] = control.isChecked()
            elif isinstance(control, (QDoubleSpinBox, QSpinBox)):
                values[key] = control.value()
        return SliceParameters(**values)

    def _collect_slice_selection(self) -> SliceSelection | None:
        has_face_selection = bool(self.selected_substrate_face_indices or self.selected_conformal_face_indices)
        substrate_index = self.selected_substrate_component_index
        conformal_indices = tuple(sorted(self.selected_conformal_component_indices))
        if not has_face_selection and len(self.component_meshes) <= 1:
            return None
        return SliceSelection(
            substrate_component_index=substrate_index,
            conformal_component_indices=conformal_indices,
            substrate_face_indices=tuple(sorted(self.selected_substrate_face_indices)),
            conformal_face_indices=tuple(sorted(self.selected_conformal_face_indices)),
        )

    def _current_machine_parameters(self) -> MachineParameters:
        values = {}
        for key, control in self.machine_controls.items():
            if isinstance(control, (QDoubleSpinBox, QSpinBox)):
                values[key] = control.value()
            elif isinstance(control, QComboBox):
                values[key] = int(control.currentData())
            elif isinstance(control, QPlainTextEdit):
                values[key] = control.toPlainText().strip()
        return MachineParameters(**values)

    def _refresh_machine_profile_info(self) -> None:
        try:
            machine = self._current_machine_parameters()
        except Exception:
            machine = open5x_freddi_hong_machine()
        self.machine_profile_info.setText(machine_profile_summary(machine, language=self.language))

    def _refresh_component_controls(self, reset_defaults: bool) -> None:
        if self.mesh is None:
            self.component_meshes = []
            self.selected_substrate_component_index = None
            self.selected_conformal_component_indices.clear()
            self._sync_component_widgets()
            return

        self.component_meshes = split_mesh_into_components(self.mesh)
        if len(self.component_meshes) <= 1:
            self.selected_substrate_component_index = None
            self.selected_conformal_component_indices.clear()
            self._sync_component_widgets()
            return

        if reset_defaults or self.selected_substrate_component_index is None or self.selected_substrate_component_index >= len(self.component_meshes):
            self.selected_substrate_component_index = self._default_substrate_component_index()
        valid_indices = {index for index in self.selected_conformal_component_indices if index < len(self.component_meshes)}
        if reset_defaults or not valid_indices:
            valid_indices = {index for index in range(len(self.component_meshes)) if index != self.selected_substrate_component_index}
        self.selected_conformal_component_indices = valid_indices
        self._sync_component_widgets()

    def _default_substrate_component_index(self) -> int:
        if not self.component_meshes or self.mesh is None:
            return 0
        overall_center_xy = self.mesh.bounds_center[:2]
        best_index = 0
        best_score = (float("inf"), float("inf"), float("inf"))
        for index, component in enumerate(self.component_meshes):
            radial_distance = float(np.linalg.norm(component.bounds_center[:2] - overall_center_xy))
            score = (radial_distance, -float(component.size[2]), -float(len(component.faces)))
            if score < best_score:
                best_index = index
                best_score = score
        return best_index

    def _sync_component_widgets(self) -> None:
        self.substrate_component_combo.blockSignals(True)
        self.substrate_component_combo.clear()
        for checkbox in self.conformal_component_checks.values():
            self.conformal_components_layout.removeWidget(checkbox)
            checkbox.deleteLater()
        self.conformal_component_checks.clear()

        has_components = len(self.component_meshes) > 1
        self.component_selection_title.setVisible(has_components)
        self.component_summary.setVisible(has_components)
        self.substrate_component_label.setVisible(has_components)
        self.substrate_component_combo.setVisible(has_components)
        self.conformal_components_label.setVisible(has_components)
        self.conformal_components_host.setVisible(has_components)
        if not has_components:
            self.component_summary.setText("")
            self.substrate_component_combo.blockSignals(False)
            return

        summary_lines = []
        for index, component in enumerate(self.component_meshes):
            center = component.bounds_center
            size = component.size
            radial = float(np.linalg.norm(center[:2] - self.mesh.bounds_center[:2])) if self.mesh is not None else 0.0
            label = self.t(
                "component_item",
                index=index,
                faces=len(component.faces),
                center_x=center[0],
                center_y=center[1],
                center_z=center[2],
                size_x=size[0],
                size_y=size[1],
                size_z=size[2],
                radial=radial,
            )
            summary_lines.append(label)
            self.substrate_component_combo.addItem(label, index)

            checkbox = QCheckBox(label)
            checkbox.setChecked(index in self.selected_conformal_component_indices)
            checkbox.toggled.connect(lambda checked, component_index=index: self._on_conformal_component_toggled(component_index, checked))
            self.conformal_components_layout.addWidget(checkbox)
            self.conformal_component_checks[index] = checkbox

        self.component_summary.setText("\n".join(summary_lines))
        if self.selected_substrate_component_index is not None:
            combo_index = self.substrate_component_combo.findData(self.selected_substrate_component_index)
            if combo_index >= 0:
                self.substrate_component_combo.setCurrentIndex(combo_index)
        self.substrate_component_combo.blockSignals(False)
        self._apply_component_checkbox_rules()

    def _apply_component_checkbox_rules(self) -> None:
        for index, checkbox in self.conformal_component_checks.items():
            is_substrate = index == self.selected_substrate_component_index
            checkbox.blockSignals(True)
            if is_substrate:
                checkbox.setChecked(False)
                checkbox.setEnabled(False)
            else:
                checkbox.setEnabled(True)
                checkbox.setChecked(index in self.selected_conformal_component_indices)
            checkbox.blockSignals(False)

    def _on_component_selection_changed(self) -> None:
        current_index = self.substrate_component_combo.currentData()
        self.selected_substrate_component_index = int(current_index) if current_index is not None else None
        if self.selected_substrate_component_index in self.selected_conformal_component_indices:
            self.selected_conformal_component_indices.discard(self.selected_substrate_component_index)
        self._apply_component_checkbox_rules()
        self._invalidate_slice_result()

    def _on_conformal_component_toggled(self, component_index: int, checked: bool) -> None:
        if checked:
            self.selected_conformal_component_indices.add(component_index)
        else:
            self.selected_conformal_component_indices.discard(component_index)
        self._invalidate_slice_result()

    def _refresh_model_info(self) -> None:
        if self.mesh is None:
            self.model_info.setText(self.t("no_model_loaded"))
            if self.slice_result is None:
                self.stats_info.setText(self.t("slice_result_placeholder"))
            return

        source = self.mesh.source_path or self.t("demo_model")
        size = self.mesh.size
        self.model_info.setText(
            self.t(
                "model_info_text",
                name=self.mesh.name,
                source=source,
                vertex_count=len(self.mesh.vertices),
                face_count=len(self.mesh.faces),
                size_x=size[0],
                size_y=size[1],
                size_z=size[2],
            )
        )
        if self.slice_result is None:
            self.stats_info.setText(self.t("slice_result_placeholder"))

    def _refresh_transform_info(self) -> None:
        if self.mesh is None or (
            np.allclose(self.placement_rotation_deg, 0.0)
            and np.allclose(self.placement_translation_mm, 0.0)
        ):
            self.transform_info.setText(self.t("transform_empty"))
            return

        self.transform_info.setText(
            self.t(
                "transform_status",
                rx=self.placement_rotation_deg[0],
                ry=self.placement_rotation_deg[1],
                rz=self.placement_rotation_deg[2],
                tx=self.placement_translation_mm[0],
                ty=self.placement_translation_mm[1],
                tz=self.placement_translation_mm[2],
            )
        )

    def _refresh_stats(self, warnings: list[str]) -> None:
        if self.slice_result is None:
            self.stats_info.setText(self.t("slice_result_placeholder"))
            return

        meta = self.slice_result.metadata
        summary = self.t(
            "stats_summary",
            path_count=meta["path_count"],
            planar_count=meta["planar_path_count"],
            conformal_count=meta["conformal_path_count"],
            planar_layers=meta["planar_layer_count"],
            transition=meta["transition_height_mm"],
            points=self.slice_result.total_points,
            length=self.slice_result.total_path_length_mm,
            surface_samples=meta["surface_samples"],
        )
        if warnings:
            summary += self.t("stats_warnings", count=len(warnings))
        self.stats_info.setText(summary)

    def _invalidate_slice_result(self) -> None:
        self.slice_result = None
        self.generated_gcode = None
        self.export_warnings = []
        self._set_path_filter_enabled(False)
        self.stats_info.setText(self.t("slice_result_placeholder"))

    def _render_current_preview(self, preserve_camera: bool = False) -> None:
        if self.mesh is None:
            self.preview.clear()
            return

        selection_faces = self._selection_faces_for_preview()
        if self.slice_result is None:
            self.preview.plot_mesh(
                self.mesh.vertices,
                self.mesh.faces,
                selection_faces=selection_faces,
                preserve_camera=preserve_camera,
            )
        else:
            toolpaths = [(path.points, path.kind) for path in self.slice_result.toolpaths]
            self.preview.plot_toolpaths(
                self.slice_result.mesh.vertices,
                self.slice_result.mesh.faces,
                toolpaths,
                selection_faces=selection_faces,
                preserve_camera=preserve_camera,
            )
        self.preview.set_face_picking(
            self.enable_face_picking_checkbox.isChecked(),
            self._on_preview_faces_picked if self.enable_face_picking_checkbox.isChecked() else None,
        )
        self._sync_face_brush_state()
        self._update_preview_visibility()

    def _append_log(self, text: str) -> None:
        existing = self.log_box.toPlainText().strip()
        self.log_box.setPlainText((existing + "\n" + text).strip())
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, self.t("error_title"), message)
        self._append_log(message)


def _axis_index(axis: str) -> int:
    return {"X": 0, "Y": 1, "Z": 2}[axis.upper()]


def launch() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    qt_exec(app)
