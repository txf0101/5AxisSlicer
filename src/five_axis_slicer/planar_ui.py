"""Small, command-backed Planar P01 editor page."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .planar_commands import PlanarCommandService
from .planar_controller import PlanarController
from .planar_generation_context import (
    planar_workpiece_from_build,
    validate_planar_generation_inputs,
)
from .planar_ui_diagnostics import generation_error_text, product_issues_text, product_status_text
from .command_kernel import CommandError
from .gcode_preview import GCodePreview
from .generation_event_pump import throttled_event_pump
from .manufacturing.toolpath import GeneratedToolpath
from .ui_controls import ScrollSafeDoubleSpinBox, ScrollSafeSpinBox
from .viewer import ModelViewer


_TEXT = {
    "zh": {
        "title": "平面切片",
        "back": "返回",
        "open": "打开 STEP",
        "show_model": "显示模型",
        "path_lines": "完整线条（快速）",
        "path_beads": "沉积道宽",
        "operation": "新建操作类型",
        "operation_instance": "现有操作",
        "body": "实体",
        "first": "首层 Z (mm)",
        "layer": "层高 (mm)",
        "last": "末层 Z (mm)",
        "bead": "道宽 (mm)",
        "feed": "进给 (mm/min)",
        "spacing": "填充间距 (mm)",
        "travel": "空移进给 (mm/min)",
        "retract": "回抽长度 (mm)",
        "offset_passes": "偏置圈数",
        "wall_thickness": "壁厚 (mm)",
        "wall_passes": "薄壁最大道数",
        "spiral_samples": "螺旋每圈采样数",
        "support_angle": "支撑悬垂角 (deg)",
        "support_xy_gap": "支撑 XY 间隙 (mm)",
        "support_z_gap": "支撑 Z 间隙 (mm)",
        "support_spacing": "支撑线间距 (mm)",
        "support_interfaces": "支撑接触层数",
        "support_interface_spacing": "接触层间距 (mm)",
        "support_pattern": "支撑图案",
        "support_pattern_lines": "线形",
        "support_pattern_grid": "网格",
        "create": "新建操作",
        "apply": "应用",
        "generate": "生成预览",
        "export": "导出结果",
        "cancel": "取消生成",
        "undo": "撤销",
        "redo": "重做",
        "no_issues": "当前没有可定位问题。",
        "issue_location": "问题位置",
        "help": "帮助：先选择“新建操作类型”创建操作，再用“现有操作”切换、编辑、生成、查看或导出。长度单位为 mm，角度输入为 deg；修改已生成操作后结果会变为 Stale。",
        "no_cad": "请先打开 STEP 模型。",
        "no_operation": "请选择操作类型并点“新建操作”。",
        "coordinates": "坐标未就绪。请点顶部“公共制造设置”，依次完成 Model CS、Build CS 和 Placement。",
        "unsupported": "该操作当前不可用，请选择可用的平面路径类型。",
        "resources": "请点顶部“公共制造设置”，完成 Part、机床、喷嘴、已审阅材料、坐标和装夹定位；下方列出未完成项。",
        "apply_required": "请应用实体和参数后再生成。",
        "disabled": "操作已禁用，请启用后生成。",
        "source_changed": "STEP 文件已变化，请更新模型后再生成。",
        "error": "生成或检查失败，禁止导出。请查看下方缺陷原因并修正后重新生成。",
        "generated_warning": "路径已生成并完成 G-code 回读，存在警告。请核对下方原因。",
        "preview_warning": "区域预览已生成，存在警告。请核对下方原因。",
        "ready": "可以生成区域截面预览。",
        "ready_zigzag": "可以生成 Zigzag 路径。",
        "ready_path": "可以生成当前平面路径。",
        "applied": "参数已应用，已有结果已过期。",
        "stale": "输入已变化，已有结果已过期，请重新生成。",
        "preview": "已生成区域截面预览。",
        "generated": "Zigzag 路径已生成并完成 G-code 回读。",
        "generated_path": "路径已生成并完成 G-code 回读。",
        "spiral_layers_insufficient": (
            "planar.spiral_layers_insufficient：螺旋至少需要两个相邻层。"
        ),
    },
    "en": {
        "title": "Planar Slicing",
        "back": "Back",
        "open": "Open STEP",
        "show_model": "Show model",
        "path_lines": "Full lines (fast)",
        "path_beads": "Bead width",
        "operation": "New operation type",
        "operation_instance": "Existing operation",
        "body": "Body",
        "first": "First layer Z (mm)",
        "layer": "Layer height (mm)",
        "last": "Last layer Z (mm)",
        "bead": "Bead width (mm)",
        "feed": "Feedrate (mm/min)",
        "spacing": "Line spacing (mm)",
        "travel": "Travel feedrate (mm/min)",
        "retract": "Retract length (mm)",
        "offset_passes": "Offset pass count",
        "wall_thickness": "Wall thickness (mm)",
        "wall_passes": "Thin-wall max passes",
        "spiral_samples": "Spiral samples/contour",
        "support_angle": "Support overhang angle (deg)",
        "support_xy_gap": "Support XY gap (mm)",
        "support_z_gap": "Support Z gap (mm)",
        "support_spacing": "Support line spacing (mm)",
        "support_interfaces": "Support interface layers",
        "support_interface_spacing": "Interface spacing (mm)",
        "support_pattern": "Support pattern",
        "support_pattern_lines": "Lines",
        "support_pattern_grid": "Grid",
        "create": "Create operation",
        "apply": "Apply",
        "generate": "Generate preview",
        "export": "Export result",
        "cancel": "Cancel generation",
        "undo": "Undo",
        "redo": "Redo",
        "no_issues": "No locatable issues.",
        "issue_location": "Issue location",
        "help": "Help: choose New operation type to create, then use Existing operation to switch, edit, generate, inspect or export. Lengths use mm and the angle input uses deg; changing a generated operation makes its result Stale.",
        "no_cad": "Open a STEP model first.",
        "no_operation": "Choose an operation type and click Create operation.",
        "coordinates": "Coordinates are not ready. Open Manufacturing Setup in the top toolbar and complete Model CS, Build CS and Placement.",
        "unsupported": "This operation is unavailable. Select an available planar path type.",
        "resources": "Open Manufacturing Setup in the top toolbar and complete part, machine, nozzle, reviewed material, coordinates and placement. See missing items below.",
        "apply_required": "Apply the selected body and parameters before generating.",
        "disabled": "This operation is disabled. Enable it before generating.",
        "source_changed": "The STEP file changed. Update the model before generating.",
        "error": "Generation or validation failed. Export is blocked. Review the defects below, correct them and generate again.",
        "generated_warning": "Toolpath generated and G-code readback passed, with warnings. Review the reasons below.",
        "preview_warning": "Region preview generated with warnings. Review the reasons below.",
        "ready": "Ready to generate a region preview.",
        "ready_zigzag": "Ready to generate a Zigzag toolpath.",
        "ready_path": "Ready to generate the selected planar toolpath.",
        "applied": "Parameters applied; any existing result is stale.",
        "stale": "Inputs changed; the existing result is stale. Generate again.",
        "preview": "Region preview generated.",
        "generated": "Zigzag toolpath generated and G-code readback passed.",
        "generated_path": "Toolpath generated and G-code readback passed.",
        "spiral_layers_insufficient": (
            "planar.spiral_layers_insufficient: Spiral requires at least two adjacent layers."
        ),
    },
}


class _PlanarPageView(QWidget):
    """A deliberately compact UI that routes every mutation through commands."""

    back_requested = pyqtSignal()
    open_step_requested = pyqtSignal()
    preview_ready = pyqtSignal(object)

    def _create(self) -> None: ...
    def _apply(self) -> None: ...
    def _generate(self) -> None: ...
    def _export(self) -> None: ...
    def _cancel(self) -> None: ...
    def _undo(self) -> None: ...
    def _redo(self) -> None: ...
    def _operation_selection_changed(self) -> None: ...
    def _install_generation_event_pump(self) -> None: ...
    def _show_selected_result(self, operation: Any, result: Any, *, emit: bool = False) -> None: ...
    def _refresh_issue_list(self, setup_issues: Any, result: Any) -> None: ...
    def _jump_to_issue(self) -> None: ...

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        controller: PlanarController | None = None,
        viewer_factory: Callable[[QWidget], QWidget] | None = None,
    ) -> None:
        super().__init__(parent)
        self.language = "zh"
        self._last_generation_error: str | None = None
        self._selected_operation_id: str | None = None
        self._viewer_operation_id: str | None = None
        self._generation_in_progress = False
        self.controller = controller or PlanarController()
        self.viewer = (viewer_factory or ModelViewer)(self)
        self.commands = PlanarCommandService(self.controller)
        self._install_generation_event_pump()
        self._build_ui()
        if self.controller.cad_model is not None and hasattr(self.viewer, "load_model"):
            self.viewer.load_model(self.controller.cad_model)
        self.set_language("zh")
        self.refresh()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.viewer.setMinimumHeight(280)
        layout.addWidget(self.viewer, 1)
        layout.addWidget(self._build_editor_panel())

    def _build_editor_panel(self) -> QScrollArea:
        editor = QWidget(self)
        editor.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.MinimumExpanding)
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(8, 8, 8, 8)
        editor_layout.addLayout(self._build_editor_header())
        editor_layout.addLayout(self._build_parameter_form())
        self.help_label = QLabel()
        self.help_label.setObjectName("planarHelpText")
        self.help_label.setWordWrap(True)
        self.help_label.setTextFormat(Qt.PlainText)
        self.help_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        editor_layout.addWidget(self.help_label)

        actions = QGridLayout()
        self.create_button = QPushButton()
        self.apply_button = QPushButton()
        self.generate_button = QPushButton()
        self.export_button = QPushButton()
        self.cancel_button = QPushButton()
        self.undo_button = QPushButton()
        self.redo_button = QPushButton()
        self._add_action_buttons(actions)
        editor_layout.addLayout(actions)
        self.status_label = QLabel()
        self.issues_label = QLabel()
        for label in (self.status_label, self.issues_label):
            label.setWordWrap(True)
            label.setTextFormat(Qt.PlainText)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        editor_layout.addWidget(self.status_label)
        editor_layout.addWidget(self.issues_label)
        self.issue_list = QListWidget()
        self.issue_list.setObjectName("planarIssueList")
        self.issue_list.setMaximumHeight(84)
        self.issue_list.setWordWrap(False)
        self.issue_list.setTextElideMode(Qt.ElideNone)
        self.issue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.issue_list.itemActivated.connect(self._jump_to_issue)
        editor_layout.addWidget(self.issue_list)
        editor_layout.addStretch(1)
        self.editor_scroll = QScrollArea(self)
        self.editor_scroll.setWidgetResizable(True)
        self.editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.editor_scroll.setMinimumWidth(400)
        self.editor_scroll.setMaximumWidth(520)
        self.editor_scroll.setWidget(editor)
        self._connect_controls()
        return self.editor_scroll

    def _build_editor_header(self) -> QVBoxLayout:
        header = QVBoxLayout()
        self.title_label = QLabel()
        self.title_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.back_button = QPushButton()
        self.open_step_button = QPushButton()
        header.addWidget(self.title_label)
        navigation = QHBoxLayout()
        navigation.addWidget(self.back_button)
        navigation.addWidget(self.open_step_button)
        header.addLayout(navigation)
        self.show_model_checkbox = QCheckBox()
        self.show_model_checkbox.setChecked(True)
        self.path_display_combo = QComboBox()
        self.path_display_combo.addItem("", "paper")
        self.path_display_combo.addItem("", "interactive")
        display_row = QHBoxLayout()
        display_row.addWidget(self.show_model_checkbox)
        display_row.addWidget(self.path_display_combo)
        header.addLayout(display_row)
        return header

    def _build_parameter_form(self) -> QFormLayout:
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.operation_type_combo = QComboBox()
        for operation_type in self.controller.available_operation_types:
            self.operation_type_combo.addItem(operation_type, operation_type)
        self.operation_type_combo.setCurrentIndex(
            max(0, self.operation_type_combo.findData("planar_region"))
        )
        self.operation_instance_combo = QComboBox()
        self.body_combo = QComboBox()
        self.first_layer_spin = self._spin(0.2, -100000.0)
        self.layer_height_spin = self._spin(0.2, 0.000001)
        self.last_layer_spin = self._spin(0.2, -100000.0)
        self.bead_width_spin = self._spin(0.6, 0.000001)
        self.feedrate_spin = self._spin(1200.0, 0.000001)
        self.line_spacing_spin = self._spin(0.6, 0.000001)
        self.travel_feedrate_spin = self._spin(1800.0, 0.000001)
        self.retract_length_spin = self._spin(1.0, 0.000001)
        self.offset_pass_count_spin = self._integer_spin(3, 1, 1000)
        self.wall_thickness_spin = self._spin(0.6, 0.000001)
        self.thin_wall_max_passes_spin = self._integer_spin(3, 1, 1000)
        self.spiral_samples_spin = self._integer_spin(64, 8, 100000)
        self.support_angle_spin = self._spin(45.0, 0.001)
        self.support_angle_spin.setMaximum(89.999)
        self.support_xy_gap_spin = self._spin(0.4, 0.0)
        self.support_z_gap_spin = self._spin(0.2, 0.0)
        self.support_line_spacing_spin = self._spin(2.0, 0.000001)
        self.support_interface_layers_spin = self._integer_spin(2, 0, 100)
        self.support_interface_spacing_spin = self._spin(0.6, 0.000001)
        self.support_pattern_combo = QComboBox()
        self.support_pattern_combo.addItem("Lines", "lines")
        self.support_pattern_combo.addItem("Grid", "grid")
        self._labels: dict[str, QLabel] = {}
        self._add_form_rows(form)
        return form

    def _connect_controls(self) -> None:
        self.back_button.clicked.connect(self.back_requested)
        self.open_step_button.clicked.connect(self.open_step_requested)
        self.show_model_checkbox.toggled.connect(self._set_model_visible)
        self.path_display_combo.currentIndexChanged.connect(self._set_path_display)
        self.create_button.clicked.connect(self._create)
        self.apply_button.clicked.connect(self._apply)
        self.generate_button.clicked.connect(self._generate)
        self.export_button.clicked.connect(self._export)
        self.cancel_button.clicked.connect(self._cancel)
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        self.operation_type_combo.currentIndexChanged.connect(self.refresh)
        self.operation_instance_combo.currentIndexChanged.connect(self._operation_selection_changed)

    def _add_form_rows(self, form: QFormLayout) -> None:
        for key, widget in (
            ("operation", self.operation_type_combo),
            ("operation_instance", self.operation_instance_combo),
            ("body", self.body_combo),
            ("first", self.first_layer_spin),
            ("layer", self.layer_height_spin),
            ("last", self.last_layer_spin),
            ("bead", self.bead_width_spin),
            ("feed", self.feedrate_spin),
            ("spacing", self.line_spacing_spin),
            ("travel", self.travel_feedrate_spin),
            ("retract", self.retract_length_spin),
            ("offset_passes", self.offset_pass_count_spin),
            ("wall_thickness", self.wall_thickness_spin),
            ("wall_passes", self.thin_wall_max_passes_spin),
            ("spiral_samples", self.spiral_samples_spin),
            ("support_angle", self.support_angle_spin),
            ("support_xy_gap", self.support_xy_gap_spin),
            ("support_z_gap", self.support_z_gap_spin),
            ("support_spacing", self.support_line_spacing_spin),
            ("support_interfaces", self.support_interface_layers_spin),
            ("support_interface_spacing", self.support_interface_spacing_spin),
            ("support_pattern", self.support_pattern_combo),
        ):
            label = QLabel()
            label.setWordWrap(True)
            # Form labels must keep a real width in the 400 px editor panel.
            # Ignored horizontal policy lets QFormLayout collapse them to zero
            # when fields request all remaining space.
            label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumHeight(
                max(widget.sizeHint().height(), widget.minimumSizeHint().height())
            )
            self._labels[key] = label
            form.addRow(label, widget)

    def _add_action_buttons(self, actions: QGridLayout) -> None:
        for index, button in enumerate(
            (
                self.create_button,
                self.apply_button,
                self.generate_button,
                self.export_button,
            )
        ):
            actions.addWidget(button, index // 2, index % 2)
        actions.addWidget(self.cancel_button, 2, 0, 1, 2)
        actions.addWidget(self.undo_button, 3, 0)
        actions.addWidget(self.redo_button, 3, 1)

    @staticmethod
    def _spin(value: float, minimum: float) -> QDoubleSpinBox:
        spin = ScrollSafeDoubleSpinBox()
        spin.setRange(minimum, 100000.0)
        spin.setDecimals(6)
        spin.setValue(value)
        return spin

    @staticmethod
    def _integer_spin(value: int, minimum: int, maximum: int) -> QSpinBox:
        spin = ScrollSafeSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        return spin

    def set_controller(self, controller: PlanarController) -> None:
        if not isinstance(controller, PlanarController):
            raise TypeError("controller must be PlanarController")
        self.controller = controller
        self.commands = PlanarCommandService(controller)
        self._selected_operation_id = None
        self._viewer_operation_id = None
        self._install_generation_event_pump()
        self._last_generation_error = None
        if controller.cad_model is not None and hasattr(self.viewer, "load_model"):
            self.viewer.load_model(controller.cad_model)
        self.refresh()

    def set_language(self, language: str) -> None:
        self.language = "en" if str(language).lower().startswith("en") else "zh"
        t = self._t
        self.title_label.setText(t("title"))
        self.back_button.setText(t("back"))
        self.open_step_button.setText(t("open"))
        self.show_model_checkbox.setText(t("show_model"))
        self.path_display_combo.setItemText(0, t("path_lines"))
        self.path_display_combo.setItemText(1, t("path_beads"))
        self.create_button.setText(t("create"))
        self.apply_button.setText(t("apply"))
        self.generate_button.setText(t("generate"))
        self.export_button.setText(t("export"))
        self.cancel_button.setText(t("cancel"))
        self.undo_button.setText(t("undo"))
        self.redo_button.setText(t("redo"))
        self.help_label.setText(t("help"))
        for key, label in self._labels.items():
            label.setText(t(key))
        self.support_pattern_combo.setItemText(
            self.support_pattern_combo.findData("lines"), t("support_pattern_lines")
        )
        self.support_pattern_combo.setItemText(
            self.support_pattern_combo.findData("grid"), t("support_pattern_grid")
        )
        self.refresh()

    def state_json(self) -> dict[str, Any]:
        state = self.controller.state_json()
        state["ui"] = {
            "language": self.language,
            "selected_operation_type": self.operation_type_combo.currentData(),
            "selected_operation_id": self._selected_operation_id,
            "selected_body_id": self.body_combo.currentText() or None,
            "generate_enabled": self.generate_button.isEnabled(),
            "export_enabled": self.export_button.isEnabled(),
            "status": self.status_label.text(),
        }
        return state

    def _set_model_visible(self, visible: bool) -> None:
        if hasattr(self.viewer, "set_model_visible"):
            self.viewer.set_model_visible(visible)

    def _set_path_display(self, _index: int) -> None:
        if hasattr(self.viewer, "set_quality_mode") and getattr(self.viewer, "gcode_preview", None) is not None:
            self.viewer.set_quality_mode(str(self.path_display_combo.currentData()))

    def refresh(self, *_ignored: Any) -> None:
        self._refresh_operations()
        current_type = str(self.operation_type_combo.currentData() or "planar_region")
        self._refresh_bodies()
        operation = self._selected_operation()
        if operation is not None:
            self._load_operation_controls(operation)
        effective_type = current_type if operation is None else operation.operation_type
        reason = self._generation_reason(effective_type, operation is not None)
        self.generate_button.setEnabled(reason is None and not self._generation_in_progress)
        self.generate_button.setToolTip(reason or "")
        self.apply_button.setEnabled(
            self.controller.cad_model is not None
            and operation is not None
            and not self._generation_in_progress
        )
        self.create_button.setEnabled(not self._generation_in_progress)
        self.cancel_button.setEnabled(self._generation_in_progress)
        self.undo_button.setEnabled(
            self.commands.kernel.can_undo and not self._generation_in_progress
        )
        self.redo_button.setEnabled(
            self.commands.kernel.can_redo and not self._generation_in_progress
        )
        product = (
            None if operation is None else self.controller.product_state(operation.operation_id)
        )
        product_result = (
            None if operation is None else self.controller.product_result(operation.operation_id)
        )
        self._refresh_product_controls(effective_type, reason, operation, product, product_result)
        issues = self.controller.validation_report().issues
        self.issues_label.setText(
            product_issues_text(issues, product, self.language, self._last_generation_error)
        )
        self._refresh_issue_list(issues, product_result)
        self._show_selected_result(operation, product_result)

    def _refresh_operations(self) -> None:
        selected = self._selected_operation_id or self.operation_instance_combo.currentData()
        self.operation_instance_combo.blockSignals(True)
        self.operation_instance_combo.clear()
        for operation in self.controller.operations:
            self.operation_instance_combo.addItem(
                f"{operation.name} · {operation.operation_type}", operation.operation_id
            )
        index = self.operation_instance_combo.findData(selected)
        if index < 0 and self.operation_instance_combo.count():
            index = self.operation_instance_combo.count() - 1
        self.operation_instance_combo.setCurrentIndex(index)
        self.operation_instance_combo.blockSignals(False)
        self._selected_operation_id = (
            None if index < 0 else str(self.operation_instance_combo.itemData(index))
        )

    def _load_operation_controls(self, operation: Any) -> None:
        parameters = operation.parameters
        for spin, value in (
            (self.first_layer_spin, parameters.first_layer_z_mm),
            (self.layer_height_spin, parameters.layer_height_mm),
            (self.last_layer_spin, parameters.last_layer_z_mm),
            (self.bead_width_spin, parameters.bead_width_mm),
            (self.feedrate_spin, parameters.feedrate_mm_min),
            (self.line_spacing_spin, parameters.line_spacing_mm),
            (self.travel_feedrate_spin, parameters.travel_feedrate_mm_min),
            (self.retract_length_spin, parameters.retract_length_mm),
            (self.offset_pass_count_spin, parameters.offset_pass_count),
            (self.wall_thickness_spin, parameters.wall_thickness_mm),
            (self.thin_wall_max_passes_spin, parameters.thin_wall_max_passes),
            (self.spiral_samples_spin, parameters.spiral_samples_per_contour),
            (self.support_angle_spin, parameters.support_overhang_angle_deg),
            (self.support_xy_gap_spin, parameters.support_xy_gap_mm),
            (self.support_z_gap_spin, parameters.support_z_gap_mm),
            (self.support_line_spacing_spin, parameters.support_line_spacing_mm),
            (self.support_interface_layers_spin, parameters.support_interface_layers),
            (self.support_interface_spacing_spin, parameters.support_interface_spacing_mm),
        ):
            spin.setValue(value)
        pattern_index = self.support_pattern_combo.findData(parameters.support_pattern)
        if pattern_index >= 0:
            self.support_pattern_combo.setCurrentIndex(pattern_index)
        if operation.geometry.body is not None:
            self.body_combo.setCurrentText(operation.geometry.body.object_id)

    def _refresh_product_controls(
        self,
        operation_type: str,
        reason: str | None,
        operation: Any,
        product: Any,
        result: Any,
    ) -> None:
        if self._last_generation_error is not None:
            self.export_button.setEnabled(False)
            self.status_label.setText(
                self._t("error")
                + "\n"
                + generation_error_text(self._last_generation_error, self.language)
            )
            return
        self.export_button.setEnabled(self._product_is_exportable(operation, product, result))
        self.status_label.setText(
            self._product_status_text(operation_type, reason, product, result)
        )

    @staticmethod
    def _product_is_exportable(operation: Any, product: Any, result: Any) -> bool:
        return bool(
            product is not None
            and product.status in {"ready", "warning"}
            and result is not None
            and result.exportable
            and operation is not None
            and operation.operation_type != "planar_region"
        )

    def _product_status_text(
        self,
        operation_type: str,
        reason: str | None,
        product: Any,
        result: Any,
    ) -> str:
        return product_status_text(operation_type, reason, product, result, self._t)

    def _refresh_bodies(self) -> None:
        selected = self.body_combo.currentText()
        self.body_combo.blockSignals(True)
        self.body_combo.clear()
        model = self.controller.cad_model
        if model is not None:
            identifiers = [body.body_id for body in model.bodies] or sorted(model.shapes)
            self.body_combo.addItems(identifiers)
        self.body_combo.setCurrentText(selected)
        self.body_combo.blockSignals(False)

    def _selected_operation(self):
        identifier = self._selected_operation_id
        if identifier is None:
            return None
        return next(
            (item for item in self.controller.operations if item.operation_id == identifier),
            None,
        )

    def _generation_reason(self, operation_type: str, has_operation: bool) -> str | None:
        if self.controller.cad_model is None:
            return self._t("no_cad")
        if not has_operation:
            return self._t("no_operation")
        try:
            self.controller.T_model_from_build()
        except ValueError:
            return self._t("coordinates")
        if operation_type not in {
            "planar_region",
            "planar_zigzag",
            "planar_offset",
            "planar_thin_wall",
            "planar_spiral",
            "planar_support",
        }:
            return self._t("unsupported")
        if operation_type != "planar_region":
            try:
                if not self.controller.setup_ready or self.controller.has_drafts:
                    return self._t("resources")
                planar_workpiece_from_build(
                    self.controller.setup, self.controller.machine_profile()
                )
            except ValueError:
                return self._t("resources")
        if not self.body_combo.currentText():
            return self._t("apply_required")
        operation = self._selected_operation()
        if not operation.enabled:
            return self._t("disabled")
        if operation.geometry.body is None:
            return self._t("apply_required")
        try:
            validate_planar_generation_inputs(
                self.controller.setup, self.controller.cad_model, operation
            )
        except (ValueError, OSError) as error:
            return self._t(
                "source_changed" if "source changed on disk" in str(error) else "resources"
            )
        return None


class PlanarPage(_PlanarPageView):
    """Command actions and result interaction for the Planar editor."""

    def _create(self) -> None:
        self._last_generation_error = None
        result = self.commands.execute_command(
            "create_operation", str(self.operation_type_combo.currentData()), origin="gui"
        )
        self._selected_operation_id = str(result.payload["operation_id"])
        self.refresh()

    def _apply(self) -> None:
        operation = self._selected_operation()
        if operation is None:
            return
        self.commands.execute_command(
            "set_operation",
            operation_id=operation.operation_id,
            body_id=self.body_combo.currentText(),
            first_layer_z_mm=self.first_layer_spin.value(),
            layer_height_mm=self.layer_height_spin.value(),
            last_layer_z_mm=self.last_layer_spin.value(),
            bead_width_mm=self.bead_width_spin.value(),
            feedrate_mm_min=self.feedrate_spin.value(),
            line_spacing_mm=self.line_spacing_spin.value(),
            travel_feedrate_mm_min=self.travel_feedrate_spin.value(),
            retract_length_mm=self.retract_length_spin.value(),
            offset_pass_count=self.offset_pass_count_spin.value(),
            wall_thickness_mm=self.wall_thickness_spin.value(),
            thin_wall_max_passes=self.thin_wall_max_passes_spin.value(),
            spiral_samples_per_contour=self.spiral_samples_spin.value(),
            support_overhang_angle_deg=self.support_angle_spin.value(),
            support_xy_gap_mm=self.support_xy_gap_spin.value(),
            support_z_gap_mm=self.support_z_gap_spin.value(),
            support_line_spacing_mm=self.support_line_spacing_spin.value(),
            support_interface_layers=self.support_interface_layers_spin.value(),
            support_interface_spacing_mm=self.support_interface_spacing_spin.value(),
            support_pattern=str(self.support_pattern_combo.currentData()),
            origin="gui",
        )
        self._last_generation_error = None
        self.status_label.setText(self._t("applied"))
        self.refresh()

    def _generate(self) -> None:
        operation = self._selected_operation()
        if operation is None or not self.generate_button.isEnabled():
            return
        self._generation_in_progress = True
        self.refresh()
        try:
            command_result = self.commands.execute_command(
                "generate_operation", operation.operation_id, origin="gui"
            )
            if command_result.payload.get("status") == "cancelled":
                self._last_generation_error = None
                return
        except CommandError as exc:
            self._last_generation_error = str(exc)
            return
        finally:
            self._generation_in_progress = False
            self.refresh()
        self._last_generation_error = None
        result = self.controller.product_result(operation.operation_id)
        self._viewer_operation_id = None
        self._show_selected_result(operation, result, emit=True)
        self.refresh()

    def _export(self) -> None:
        operation = self._selected_operation()
        if operation is None or not self.export_button.isEnabled():
            return
        destination = QFileDialog.getExistingDirectory(self, self._t("export"))
        if destination:
            self.commands.execute_command(
                "export_operation",
                operation.operation_id,
                destination,
                origin="gui",
            )

    def _cancel(self) -> None:
        self.commands.execute_command("cancel_generation", origin="gui")

    def _undo(self) -> None:
        if self.commands.kernel.can_undo:
            self.commands.execute_command("undo", origin="gui")
            self.refresh()

    def _redo(self) -> None:
        if self.commands.kernel.can_redo:
            self.commands.execute_command("redo", origin="gui")
            self.refresh()

    def _operation_selection_changed(self) -> None:
        selected = self.operation_instance_combo.currentData()
        self._selected_operation_id = None if selected is None else str(selected)
        self._last_generation_error = None
        self._viewer_operation_id = None
        self.refresh()

    def _install_generation_event_pump(self) -> None:
        self.controller.set_generation_event_pump(
            throttled_event_pump(QApplication.processEvents)
        )

    def _show_selected_result(self, operation: Any, result: Any, *, emit: bool = False) -> None:
        if operation is None or result is None:
            return
        if self._viewer_operation_id == operation.operation_id and not emit:
            return
        if hasattr(self.viewer, "load_gcode_preview"):
            self.viewer.load_gcode_preview(
                _preview_from_generated_toolpath(result.preview_toolpath)
            )
            self._set_path_display(self.path_display_combo.currentIndex())
        self._viewer_operation_id = operation.operation_id
        if emit:
            self.preview_ready.emit(result.preview_toolpath)

    def _refresh_issue_list(self, setup_issues: Any, result: Any) -> None:
        self.issue_list.clear()
        issues = list(setup_issues)
        if result is not None and hasattr(result, "validation"):
            issues.extend(result.validation.issues)
        seen: set[tuple[str, str]] = set()
        for issue_index, issue in enumerate(issues, 1):
            key = (issue.code, issue.object_id)
            if key in seen:
                continue
            seen.add(key)
            marker = getattr(issue.severity, "value", str(issue.severity)).upper()
            short_code = issue.code.rsplit(".", 1)[-1]
            text = f"{marker[:1]}{issue_index}: {short_code}"
            while self.issue_list.fontMetrics().horizontalAdvance(text) > 250 and "_" in short_code:
                short_code = short_code.split("_", 1)[1]
                text = f"{marker[:1]}{issue_index}: {short_code}"
            tooltip = (
                f"[{marker}] {issue.code} · {issue.object_id or self.controller.setup.setup_id}"
            )
            self.issue_list.addItem(text)
            item = self.issue_list.item(self.issue_list.count() - 1)
            item.setData(Qt.UserRole, issue.to_json())
            item.setToolTip(tooltip)
        if not issues:
            self.issue_list.addItem(self._t("no_issues"))

    def _jump_to_issue(self) -> None:
        item = self.issue_list.currentItem()
        if item is None:
            return
        payload = item.data(Qt.UserRole)
        if not isinstance(payload, Mapping):
            return
        operation = self._selected_operation()
        result = (
            None if operation is None else self.controller.product_result(operation.operation_id)
        )
        object_id = str(payload.get("object_id", ""))
        if result is not None and object_id:
            for index, point in enumerate(result.preview_toolpath.points):
                if point.point_id != object_id:
                    continue
                if hasattr(self.viewer, "set_preview_progress"):
                    self.viewer.set_preview_progress(max(0, index - 1))
                if point.layer_id.startswith("layer-") and hasattr(
                    self.viewer, "set_preview_layers"
                ):
                    layer = int(point.layer_id.rsplit("-", 1)[-1])
                    self.viewer.set_preview_layers(layer, layer)
                break
        self.status_label.setText(
            f"{self.status_label.text()}\n{self._t('issue_location')}: "
            f"{payload.get('code', '')} · {object_id or self.controller.setup.setup_id}"
        )

    def _t(self, key: str) -> str:
        return _TEXT[self.language][key]


def _preview_from_generated_toolpath(toolpath: GeneratedToolpath) -> GCodePreview:
    """Build a viewer payload without presenting a generated path as imported NC."""

    segments = toolpath.to_preview_segments()
    layers = [segment.layer for segment in segments]
    points = [point for segment in segments for point in (segment.start, segment.end)]
    bounds = None
    if points:
        bounds = (
            (
                min(point[0] for point in points),
                min(point[1] for point in points),
                min(point[2] for point in points),
            ),
            (
                max(point[0] for point in points),
                max(point[1] for point in points),
                max(point[2] for point in points),
            ),
        )
    return GCodePreview(
        source_path=Path(f"<generated:{toolpath.operation_id}>"),
        segments=segments,
        total_segment_count=len(segments),
        layer_min=min(layers, default=0),
        layer_max=max(layers, default=-1),
        bounds=bounds,
        move_counts=dict(Counter(segment.move_type for segment in segments)),
        role_counts=dict(Counter(segment.extrusion_role for segment in segments)),
        rotary_axes=[],
        coordinate_transform=toolpath.coordinate_frame,
    )


__all__ = ["PlanarPage"]
