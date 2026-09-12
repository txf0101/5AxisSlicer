"""Command-backed bilingual Rotary workbench editor and result viewer."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import math
from pathlib import Path
from typing import Any, Callable, cast

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
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .command_kernel import CommandError
from .gcode_preview import GCodePreview
from .manufacturing.rotary_parameters import (
    RotaryAngularRegion,
    RotaryFrame,
    RotaryGeometrySelection,
    RotaryProfile,
)
from .manufacturing.toolpath import GeneratedToolpath
from .models import Vector3
from .rotary_commands import RotaryCommandService
from .rotary_controller import RotaryController
from .rotary_operation_service import bind_rotary_geometry_references
from .viewer import ModelViewer


_TEXT = {
    "zh": {
        "title": "Rotary 回转增材工作台",
        "back": "返回",
        "open": "打开 STEP",
        "new_type": "新建操作类型",
        "existing": "现有操作",
        "spiral": "回转螺旋",
        "thin_wall": "回转薄壁",
        "around_part": "局部环绕零件",
        "axis_edge": "回转轴向参考边",
        "contour_edges": "轮廓边",
        "surface_faces": "回转表面",
        "pick_axis": "采用 Viewer 已选轴向边",
        "pick_contours": "采用 Viewer 已选轮廓边",
        "pick_surfaces": "采用 Viewer 已选表面",
        "axis_origin": "轴原点 X,Y,Z (Source mm)",
        "axis_direction": "轴单位方向 X,Y,Z",
        "zero_direction": "零角方向 X,Y,Z",
        "positive": "正回转方向",
        "positive_ccw": "+1（右手/逆时针）",
        "positive_cw": "-1（反向/顺时针）",
        "axial_start": "轴向起点 (mm)",
        "axial_end": "轴向终点 (mm)",
        "radius_start": "起始半径 (mm)",
        "radius_end": "终止半径 (mm)",
        "regions": "局部角区间 (deg，如 350:20;120:210)",
        "region_direction": "区域展开方向",
        "preview_only": "仅分析/预览 Region（禁止产品生成）",
        "pitch": "螺距 (mm/rev)",
        "path_direction": "路径回转方向",
        "start_angle": "起始角 (deg)",
        "end_angle": "终止/展开角 (deg)",
        "angular_velocity": "回转角速度 (rad/s)",
        "sampling_angle": "角度采样步长 (deg)",
        "bead": "道宽 (mm)",
        "layer": "层高 (mm)",
        "feed": "沉积进给 (mm/min)",
        "travel": "空移进给 (mm/min)",
        "retract": "回抽长度 (mm)",
        "dwell": "层间停留 (s)",
        "axial_step": "轴向步距 (mm)",
        "radial_passes": "径向道数",
        "radial_spacing": "径向道间距 (mm)",
        "wall_thickness": "目标壁厚 (mm)",
        "thin_wall_policy": "不足一道宽策略",
        "policy_error": "报错并禁止导出",
        "policy_reduce": "缩减为单道并警告",
        "clearance": "安全连接间隙 (mm)",
        "create": "新建操作",
        "apply": "应用几何与参数",
        "generate": "生成与检查",
        "cancel": "取消生成",
        "export": "导出六件套",
        "undo": "撤销",
        "redo": "重做",
        "no_issues": "当前没有可定位问题。",
        "status": "状态",
        "draft": "已建立操作，请应用几何与参数。",
        "ready": "已就绪，可生成并检查完整产品链。",
        "warning": "已生成，存在警告；导出前请核对问题。",
        "error": "生成或检查失败，已禁止导出。",
        "stale": "输入已变更，旧结果为 Stale，请重新生成。",
        "cancelled": "生成已取消，旧的有效结果仍保留。",
        "no_cad": "请先打开 STEP 模型。",
        "setup": "需要完整且已应用的 Setup：坐标、机型、喷嘴、材料与安装。",
        "operation_required": "请先新建操作。",
        "region_required": "Around Part 至少需要一个有向角区间。",
        "select_one_axis": "请在 Viewer 中只选一条可确定轴向的边。",
        "select_contours": "请在 Viewer 中选择一条或多条轮廓边。",
        "select_surfaces": "请在 Viewer 中选择一个或多个圆柱/圆锥面。",
        "selection_staged": "已记录 Viewer 选择；点击“应用几何与参数”保存稳定引用。",
        "help": (
            "Viewer 几何选择是预期流程：分别选一条有轴向的边、轮廓边和圆柱/"
            "圆锥面，再点击对应的“采用”按钮。应用时会保存稳定拓扑引用，并从面真值派生轴与"
            "profile；数值是无几何引用时的显式备用。界面角度为 deg，内部为 rad；350→20 按所选方向连续"
            "展开。参数或回转几何变更会使旧结果 Stale，Error 禁止导出。"
        ),
    },
    "en": {
        "title": "Rotary Additive Workbench",
        "back": "Back",
        "open": "Open STEP",
        "new_type": "New operation type",
        "existing": "Existing operation",
        "spiral": "Rotary Spiral",
        "thin_wall": "Rotary Thin Wall",
        "around_part": "Around Part",
        "axis_edge": "Rotary axis-direction edge",
        "contour_edges": "Profile edges",
        "surface_faces": "Rotary surfaces",
        "pick_axis": "Use Viewer-selected axis-direction edge",
        "pick_contours": "Use Viewer-selected profile edges",
        "pick_surfaces": "Use Viewer-selected surfaces",
        "axis_origin": "Axis origin X,Y,Z (Source mm)",
        "axis_direction": "Axis unit direction X,Y,Z",
        "zero_direction": "Zero-angle direction X,Y,Z",
        "positive": "Positive rotary direction",
        "positive_ccw": "+1 (right-hand/CCW)",
        "positive_cw": "-1 (opposite/CW)",
        "axial_start": "Axial start (mm)",
        "axial_end": "Axial end (mm)",
        "radius_start": "Start radius (mm)",
        "radius_end": "End radius (mm)",
        "regions": "Local angle regions (deg, e.g. 350:20;120:210)",
        "region_direction": "Region unwrap direction",
        "preview_only": "Analyse/preview Region only (blocks product generation)",
        "pitch": "Pitch (mm/rev)",
        "path_direction": "Path rotary direction",
        "start_angle": "Start angle (deg)",
        "end_angle": "End/unwrapped angle (deg)",
        "angular_velocity": "Rotary angular velocity (rad/s)",
        "sampling_angle": "Angular sample step (deg)",
        "bead": "Bead width (mm)",
        "layer": "Layer height (mm)",
        "feed": "Deposition feedrate (mm/min)",
        "travel": "Travel feedrate (mm/min)",
        "retract": "Retract length (mm)",
        "dwell": "Inter-layer dwell (s)",
        "axial_step": "Axial step (mm)",
        "radial_passes": "Radial pass count",
        "radial_spacing": "Radial pass spacing (mm)",
        "wall_thickness": "Target wall thickness (mm)",
        "thin_wall_policy": "Below-one-bead policy",
        "policy_error": "Error and block export",
        "policy_reduce": "Reduce to one pass with warning",
        "clearance": "Safe connection clearance (mm)",
        "create": "Create operation",
        "apply": "Apply geometry and parameters",
        "generate": "Generate and validate",
        "cancel": "Cancel generation",
        "export": "Export six-file bundle",
        "undo": "Undo",
        "redo": "Redo",
        "no_issues": "No locatable issues.",
        "status": "Status",
        "draft": "Operation created; apply geometry and parameters.",
        "ready": "Ready to generate and validate the complete product chain.",
        "warning": "Generated with warnings; review the issues before export.",
        "error": "Generation or validation failed; export is blocked.",
        "stale": "Inputs changed; the previous result is Stale. Generate again.",
        "cancelled": "Generation cancelled; the previous valid result was retained.",
        "no_cad": "Open a STEP model first.",
        "setup": "A complete applied Setup is required: coordinates, machine, nozzle, material and placement.",
        "operation_required": "Create an operation first.",
        "region_required": "Around Part requires at least one directed angular region.",
        "select_one_axis": "Select exactly one axis-bearing edge in Viewer.",
        "select_contours": "Select one or more profile edges in Viewer.",
        "select_surfaces": "Select one or more cylindrical/conical faces in Viewer.",
        "selection_staged": "Viewer selection staged; use Apply geometry and parameters to save stable references.",
        "help": (
            "Viewer selection is the intended geometry workflow: select an axis-bearing edge, profile edges "
            "and cylindrical/conical faces in turn, then use the matching buttons. Apply stores stable "
            "topology references and derives the axis/profile from the surface truth; numeric values are an "
            "explicit fallback when no references are used. UI angles are deg and internal angles are rad; "
            "350→20 unwraps continuously in the selected direction. Parameter or rotary-geometry changes "
            "make previous results Stale, and Error blocks export."
        ),
    },
}


class RotaryPage(QWidget):
    """Visible editor for all three Rotary operations using one command service."""

    back_requested = pyqtSignal()
    open_step_requested = pyqtSignal()
    preview_ready = pyqtSignal(object)
    machine_trajectory_ready = pyqtSignal(object)
    state_changed = pyqtSignal(object)

    def __init__(
        self,
        host: QWidget | None = None,
        *,
        controller: RotaryController | None = None,
        viewer_factory: Callable[[QWidget], QWidget] | None = None,
    ) -> None:
        super().__init__(host)
        self.host = host
        self.controller = controller or RotaryController()
        self.commands = RotaryCommandService(self.controller)
        self.language = _normalise_language(getattr(host, "language", "zh"))
        self._selected_operation_id: str | None = None
        self._viewer_operation_id: str | None = None
        self._last_error: str | None = None
        self._generation_in_progress = False
        self.viewer = (viewer_factory or ModelViewer)(self)
        self._build_ui()
        self._install_generation_event_pump()
        self._load_model_into_viewer()
        self.set_language(self.language)
        self.refresh()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)
        self.editor_scroll = QScrollArea(self)
        self.editor_scroll.setWidgetResizable(True)
        self.editor_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.editor_scroll.setMinimumWidth(450)
        editor = QWidget(self.editor_scroll)
        editor.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.MinimumExpanding)
        layout = QVBoxLayout(editor)
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(self.title_label)
        nav = QHBoxLayout()
        self.back_button = QPushButton()
        self.open_button = QPushButton()
        nav.addWidget(self.back_button)
        nav.addWidget(self.open_button)
        layout.addLayout(nav)
        self._build_form(layout)
        self._build_actions(layout)
        self.editor_scroll.setWidget(editor)
        root.addWidget(self.editor_scroll, 0)
        self.viewer.setMinimumHeight(280)
        root.addWidget(self.viewer, 1)
        self._connect_controls()

    def _build_form(self, layout: QVBoxLayout) -> None:
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._rows: dict[str, tuple[QLabel, QWidget]] = {}

        self.operation_type_combo = QComboBox()
        for operation_type in (
            "rotary_spiral",
            "rotary_thin_wall",
            "rotary_around_part",
        ):
            self.operation_type_combo.addItem("", operation_type)
        self.operation_combo = QComboBox()
        self._add_row(form, "new_type", self.operation_type_combo)
        self._add_row(form, "existing", self.operation_combo)

        self.axis_edge_edit = QLineEdit()
        self.contour_edges_edit = QLineEdit()
        self.surface_faces_edit = QLineEdit()
        self._add_row(form, "axis_edge", self.axis_edge_edit)
        self._add_row(form, "contour_edges", self.contour_edges_edit)
        self._add_row(form, "surface_faces", self.surface_faces_edit)

        selection_actions = QGridLayout()
        self.pick_axis_button = QPushButton()
        self.pick_contours_button = QPushButton()
        self.pick_surfaces_button = QPushButton()
        selection_actions.addWidget(self.pick_axis_button, 0, 0)
        selection_actions.addWidget(self.pick_contours_button, 0, 1)
        selection_actions.addWidget(self.pick_surfaces_button, 1, 0, 1, 2)
        layout.addLayout(form)
        layout.addLayout(selection_actions)

        geometry_form = QFormLayout()
        geometry_form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        geometry_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.axis_origin_edit = QLineEdit("0,0,0")
        self.axis_direction_edit = QLineEdit("0,0,1")
        self.zero_direction_edit = QLineEdit("1,0,0")
        self.positive_direction_combo = QComboBox()
        self.positive_direction_combo.addItem("", 1)
        self.positive_direction_combo.addItem("", -1)
        for key, widget in (
            ("axis_origin", self.axis_origin_edit),
            ("axis_direction", self.axis_direction_edit),
            ("zero_direction", self.zero_direction_edit),
            ("positive", self.positive_direction_combo),
        ):
            self._add_row(geometry_form, key, widget)

        self.axial_start_spin = self._double_spin(0.0, -1_000_000.0)
        self.axial_end_spin = self._double_spin(10.0, -1_000_000.0)
        self.radius_start_spin = self._double_spin(10.0, 0.001)
        self.radius_end_spin = self._double_spin(10.0, 0.001)
        for key, widget in (
            ("axial_start", self.axial_start_spin),
            ("axial_end", self.axial_end_spin),
            ("radius_start", self.radius_start_spin),
            ("radius_end", self.radius_end_spin),
        ):
            self._add_row(geometry_form, key, widget)

        self.region_intervals_edit = QLineEdit()
        self.region_direction_combo = self._direction_combo()
        self.preview_only_check = QCheckBox()
        self._add_row(geometry_form, "regions", self.region_intervals_edit)
        self._add_row(geometry_form, "region_direction", self.region_direction_combo)
        self._add_row(geometry_form, "preview_only", self.preview_only_check)
        layout.addLayout(geometry_form)

        process_form = QFormLayout()
        process_form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        process_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.path_direction_combo = self._direction_combo()
        self.pitch_spin = self._double_spin(5.0, 0.001)
        self.start_angle_spin = self._angle_spin(0.0)
        self.end_angle_spin = self._angle_spin(360.0)
        self.angular_velocity_spin = self._double_spin(0.5, 0.001)
        self.sampling_angle_spin = self._double_spin(5.0, 0.01)
        self.bead_width_spin = self._double_spin(0.6, 0.001)
        self.layer_height_spin = self._double_spin(0.2, 0.001)
        self.feedrate_spin = self._double_spin(900.0, 0.001)
        self.travel_feedrate_spin = self._double_spin(1800.0, 0.001)
        self.retract_length_spin = self._double_spin(1.0, 0.0)
        self.dwell_spin = self._double_spin(0.0, 0.0)
        self.axial_step_spin = self._double_spin(2.0, 0.001)
        self.radial_pass_count_spin = QSpinBox()
        self.radial_pass_count_spin.setRange(1, 100)
        self.radial_pass_count_spin.setValue(1)
        self.radial_spacing_spin = self._double_spin(0.6, 0.001)
        self.wall_thickness_spin = self._double_spin(0.6, 0.001)
        self.thin_wall_policy_combo = QComboBox()
        self.thin_wall_policy_combo.addItem("", "error")
        self.thin_wall_policy_combo.addItem("", "reduce")
        self.connection_clearance_spin = self._double_spin(1.0, 0.001)
        for key, widget in (
            ("pitch", self.pitch_spin),
            ("path_direction", self.path_direction_combo),
            ("start_angle", self.start_angle_spin),
            ("end_angle", self.end_angle_spin),
            ("angular_velocity", self.angular_velocity_spin),
            ("sampling_angle", self.sampling_angle_spin),
            ("bead", self.bead_width_spin),
            ("layer", self.layer_height_spin),
            ("feed", self.feedrate_spin),
            ("travel", self.travel_feedrate_spin),
            ("retract", self.retract_length_spin),
            ("dwell", self.dwell_spin),
            ("axial_step", self.axial_step_spin),
            ("radial_passes", self.radial_pass_count_spin),
            ("radial_spacing", self.radial_spacing_spin),
            ("wall_thickness", self.wall_thickness_spin),
            ("thin_wall_policy", self.thin_wall_policy_combo),
            ("clearance", self.connection_clearance_spin),
        ):
            self._add_row(process_form, key, widget)
        layout.addLayout(process_form)

    def _build_actions(self, layout: QVBoxLayout) -> None:
        actions = QGridLayout()
        self.create_button = QPushButton()
        self.apply_button = QPushButton()
        self.generate_button = QPushButton()
        self.cancel_button = QPushButton()
        self.export_button = QPushButton()
        self.undo_button = QPushButton()
        self.redo_button = QPushButton()
        for index, button in enumerate(
            (
                self.create_button,
                self.apply_button,
                self.generate_button,
                self.cancel_button,
                self.export_button,
                self.undo_button,
                self.redo_button,
            )
        ):
            actions.addWidget(button, index // 2, index % 2)
        layout.addLayout(actions)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextFormat(Qt.PlainText)
        layout.addWidget(self.status_label)
        self.issue_list = QListWidget()
        self.issue_list.setObjectName("rotaryIssueList")
        self.issue_list.setMinimumHeight(100)
        self.issue_list.setMaximumHeight(150)
        self.issue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.issue_list)
        self.help_label = QLabel()
        self.help_label.setObjectName("rotaryHelpText")
        self.help_label.setWordWrap(True)
        self.help_label.setTextFormat(Qt.PlainText)
        self.help_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.help_label)
        layout.addStretch(1)

    def _connect_controls(self) -> None:
        self.back_button.clicked.connect(self.back_requested.emit)
        self.open_button.clicked.connect(self.open_step_requested.emit)
        self.create_button.clicked.connect(self._create)
        self.apply_button.clicked.connect(self._apply)
        self.generate_button.clicked.connect(self._generate)
        self.cancel_button.clicked.connect(self._cancel)
        self.export_button.clicked.connect(self._export)
        self.undo_button.clicked.connect(self._undo)
        self.redo_button.clicked.connect(self._redo)
        self.operation_combo.currentIndexChanged.connect(self._operation_changed)
        self.operation_type_combo.currentIndexChanged.connect(self._update_operation_visibility)
        self.pick_axis_button.clicked.connect(self._use_selected_axis)
        self.pick_contours_button.clicked.connect(self._use_selected_contours)
        self.pick_surfaces_button.clicked.connect(self._use_selected_surfaces)
        self.issue_list.itemActivated.connect(self._jump_to_issue)

    def set_controller(self, controller: RotaryController) -> None:
        if not isinstance(controller, RotaryController):
            raise TypeError("controller must be RotaryController")
        self.controller = controller
        self.commands = RotaryCommandService(controller)
        self._selected_operation_id = None
        self._viewer_operation_id = None
        self._last_error = None
        self._install_generation_event_pump()
        self._load_model_into_viewer()
        self.refresh()

    def set_language(self, language: str) -> None:
        self.language = _normalise_language(language)
        for key, (label, _widget) in self._rows.items():
            label.setText(self._t(key))
        for index, key in enumerate(("spiral", "thin_wall", "around_part")):
            self.operation_type_combo.setItemText(index, self._t(key))
        self.positive_direction_combo.setItemText(0, self._t("positive_ccw"))
        self.positive_direction_combo.setItemText(1, self._t("positive_cw"))
        for combo in (self.region_direction_combo, self.path_direction_combo):
            combo.setItemText(combo.findData("ccw"), "CCW")
            combo.setItemText(combo.findData("cw"), "CW")
        self.thin_wall_policy_combo.setItemText(0, self._t("policy_error"))
        self.thin_wall_policy_combo.setItemText(1, self._t("policy_reduce"))
        self.title_label.setText(self._t("title"))
        for button, key in (
            (self.back_button, "back"),
            (self.open_button, "open"),
            (self.pick_axis_button, "pick_axis"),
            (self.pick_contours_button, "pick_contours"),
            (self.pick_surfaces_button, "pick_surfaces"),
            (self.create_button, "create"),
            (self.apply_button, "apply"),
            (self.generate_button, "generate"),
            (self.cancel_button, "cancel"),
            (self.export_button, "export"),
            (self.undo_button, "undo"),
            (self.redo_button, "redo"),
        ):
            button.setText(self._t(key))
        self.preview_only_check.setText("")
        self.help_label.setText(self._t("help"))
        self.refresh()

    def state_json(self) -> dict[str, Any]:
        state = self.controller.state_json()
        operation = self._selected_operation()
        result = None if operation is None else self.controller.product_result(operation.operation_id)
        trajectory = None if result is None else result.trajectory.to_json()
        state["ui"] = {
            "language": self.language,
            "selected_operation_type": self.operation_type_combo.currentData(),
            "selected_operation_id": self._selected_operation_id,
            "generate_enabled": self.generate_button.isEnabled(),
            "export_enabled": self.export_button.isEnabled(),
            "generation_in_progress": self._generation_in_progress,
            "status": self.status_label.text(),
            "last_error": self._last_error,
            "viewer": self.viewer.preview_state() if hasattr(self.viewer, "preview_state") else {},
            "machine_trajectory": trajectory,
        }
        return state

    def current_machine_trajectory(self) -> Any | None:
        """Return the selected result trajectory for axis-table/viewer consumers."""

        operation = self._selected_operation()
        result = None if operation is None else self.controller.product_result(operation.operation_id)
        return None if result is None else result.trajectory

    def refresh(self, *_ignored: Any) -> None:
        self._refresh_operations()
        operation = self._selected_operation()
        if operation is not None:
            self._load_operation_controls(operation)
        self._update_operation_visibility()
        result = None if operation is None else self.controller.product_result(operation.operation_id)
        product = None if operation is None else self.controller.product_state(operation.operation_id)
        self._refresh_issues(result)
        reason = self._generation_reason(operation)
        self.generate_button.setEnabled(reason is None and not self._generation_in_progress)
        self.generate_button.setToolTip(reason or "")
        self.apply_button.setEnabled(operation is not None and not self._generation_in_progress)
        self.cancel_button.setEnabled(self._generation_in_progress)
        self.create_button.setEnabled(
            self.controller.can_create_operation and not self._generation_in_progress
        )
        exportable = bool(
            operation
            and product
            and product.status in {"ready", "warning"}
            and result
            and result.exportable
        )
        self.export_button.setEnabled(exportable and not self._generation_in_progress)
        self.undo_button.setEnabled(self.commands.kernel.can_undo and not self._generation_in_progress)
        self.redo_button.setEnabled(self.commands.kernel.can_redo and not self._generation_in_progress)
        self.status_label.setText(self._status_text(product, reason))
        self._show_result(operation, result)
        self.state_changed.emit(self.state_json())

    def _create(self) -> None:
        try:
            response = self.commands.execute_command(
                "create_operation",
                str(self.operation_type_combo.currentData()),
                origin="gui",
            )
            self._selected_operation_id = str(response.payload["operation_id"])
            self._last_error = None
        except (CommandError, KeyError, TypeError, ValueError) as exc:
            self._last_error = str(exc)
        self.refresh()

    def _apply(self) -> None:
        operation = self._selected_operation()
        if operation is None:
            return
        try:
            geometry = self._geometry_from_controls(operation.geometry)
            self.commands.execute_command(
                "set_operation",
                operation_id=operation.operation_id,
                geometry=geometry,
                pitch_mm=self.pitch_spin.value(),
                direction=str(self.path_direction_combo.currentData()),
                start_angle_rad=math.radians(self.start_angle_spin.value()),
                end_angle_rad=math.radians(self.end_angle_spin.value()),
                angular_velocity_rad_s=self.angular_velocity_spin.value(),
                sampling_angle_rad=math.radians(self.sampling_angle_spin.value()),
                bead_width_mm=self.bead_width_spin.value(),
                layer_height_mm=self.layer_height_spin.value(),
                feedrate_mm_min=self.feedrate_spin.value(),
                travel_feedrate_mm_min=self.travel_feedrate_spin.value(),
                retract_length_mm=self.retract_length_spin.value(),
                dwell_s=self.dwell_spin.value(),
                axial_step_mm=self.axial_step_spin.value(),
                radial_pass_count=self.radial_pass_count_spin.value(),
                radial_spacing_mm=self.radial_spacing_spin.value(),
                wall_thickness_mm=self.wall_thickness_spin.value(),
                thin_wall_width_policy=str(self.thin_wall_policy_combo.currentData()),
                connection_clearance_mm=self.connection_clearance_spin.value(),
                origin="gui",
            )
            self._last_error = None
            self._viewer_operation_id = None
        except (CommandError, KeyError, TypeError, ValueError) as exc:
            self._last_error = str(exc)
        self.refresh()

    def _geometry_from_controls(
        self, current: RotaryGeometrySelection
    ) -> RotaryGeometrySelection:
        regions = self._parse_regions()
        frame = RotaryFrame(
            self._vector(self.axis_origin_edit.text(), "axis_origin_mm"),
            self._vector(self.axis_direction_edit.text(), "axis_direction"),
            self._vector(self.zero_direction_edit.text(), "zero_direction"),
            int(self.positive_direction_combo.currentData()),
        )
        profile = RotaryProfile(
            self.axial_start_spin.value(),
            self.axial_end_spin.value(),
            self.radius_start_spin.value(),
            self.radius_end_spin.value(),
        )
        geometry = RotaryGeometrySelection(
            frame,
            profile,
            regions,
            self.preview_only_check.isChecked(),
        )
        axis_id = self.axis_edge_edit.text().strip()
        contour_ids = self._identifiers(self.contour_edges_edit.text())
        surface_ids = self._identifiers(self.surface_faces_edit.text())
        if axis_id or contour_ids or surface_ids:
            if self.controller.cad_model is None:
                raise ValueError(self._t("no_cad"))
            if not axis_id or not surface_ids:
                raise ValueError("rotary.axis_or_surface_reference_missing")
            geometry = bind_rotary_geometry_references(
                self.controller.cad_model,
                geometry,
                axis_edge_id=axis_id,
                contour_edge_ids=contour_ids,
                surface_face_ids=surface_ids,
            )
        return geometry

    def _parse_regions(self) -> tuple[RotaryAngularRegion, ...]:
        source = self.region_intervals_edit.text().strip()
        if not source:
            return ()
        direction = str(self.region_direction_combo.currentData())
        regions = []
        for index, token in enumerate(source.replace(",", ";").split(";"), 1):
            clean = token.strip()
            if not clean:
                continue
            parts = clean.split(":")
            if len(parts) != 2:
                raise ValueError("regions must use start:end pairs separated by semicolons")
            regions.append(
                RotaryAngularRegion(
                    f"region-{index:04d}",
                    math.radians(float(parts[0].strip())),
                    math.radians(float(parts[1].strip())),
                    direction,
                )
            )
        return tuple(regions)

    def _generate(self) -> None:
        operation = self._selected_operation()
        if operation is None or not self.generate_button.isEnabled():
            return
        self._generation_in_progress = True
        self.refresh()
        try:
            response = self.commands.execute_command(
                "generate_operation", operation.operation_id, origin="gui"
            )
            self._last_error = (
                self._t("cancelled") if response.payload.get("status") == "cancelled" else None
            )
            self._viewer_operation_id = None
        except (CommandError, TypeError, ValueError) as exc:
            self._last_error = str(exc)
        finally:
            self._generation_in_progress = False
            self.refresh()
        result = self.controller.product_result(operation.operation_id)
        if result is not None:
            self.preview_ready.emit(result.preview_toolpath)
            self.machine_trajectory_ready.emit(result.trajectory)

    def _cancel(self) -> None:
        try:
            self.commands.execute_command("cancel_generation", origin="gui")
        except CommandError as exc:
            self._last_error = str(exc)

    def _export(self) -> None:
        operation = self._selected_operation()
        if operation is None or not self.export_button.isEnabled():
            return
        destination = QFileDialog.getExistingDirectory(self, self._t("export"))
        if destination:
            try:
                self.commands.execute_command(
                    "export_operation", operation.operation_id, destination, origin="gui"
                )
                self._last_error = None
            except (CommandError, TypeError, ValueError) as exc:
                self._last_error = str(exc)
            self.refresh()

    def _undo(self) -> None:
        if self.commands.kernel.can_undo:
            self.commands.execute_command("undo", origin="gui")
            self._viewer_operation_id = None
            self.refresh()

    def _redo(self) -> None:
        if self.commands.kernel.can_redo:
            self.commands.execute_command("redo", origin="gui")
            self._viewer_operation_id = None
            self.refresh()

    def _operation_changed(self) -> None:
        selected = self.operation_combo.currentData()
        self._selected_operation_id = None if selected is None else str(selected)
        self._last_error = None
        self._viewer_operation_id = None
        self.refresh()

    def _use_selected_axis(self) -> None:
        edge_ids = sorted(self.viewer.selection.edge_ids)
        if len(edge_ids) != 1:
            self._last_error = self._t("select_one_axis")
        else:
            self.axis_edge_edit.setText(edge_ids[0])
            self._last_error = None
        self.status_label.setText(self._last_error or self._t("selection_staged"))

    def _use_selected_contours(self) -> None:
        edge_ids = sorted(self.viewer.selection.edge_ids)
        if not edge_ids:
            self._last_error = self._t("select_contours")
        else:
            self.contour_edges_edit.setText(",".join(edge_ids))
            self._last_error = None
        self.status_label.setText(self._last_error or self._t("selection_staged"))

    def _use_selected_surfaces(self) -> None:
        face_ids = sorted(self.viewer.selection.face_ids)
        if not face_ids:
            self._last_error = self._t("select_surfaces")
        else:
            self.surface_faces_edit.setText(",".join(face_ids))
            self._last_error = None
        self.status_label.setText(self._last_error or self._t("selection_staged"))

    def _refresh_operations(self) -> None:
        operations = self.controller.operations
        identifiers = {item.operation_id for item in operations}
        if self._selected_operation_id not in identifiers:
            self._selected_operation_id = operations[-1].operation_id if operations else None
        self.operation_combo.blockSignals(True)
        self.operation_combo.clear()
        for item in operations:
            self.operation_combo.addItem(f"{item.name} · {item.operation_type}", item.operation_id)
        index = self.operation_combo.findData(self._selected_operation_id)
        if index >= 0:
            self.operation_combo.setCurrentIndex(index)
        self.operation_combo.blockSignals(False)

    def _load_operation_controls(self, operation: Any) -> None:
        operation_index = self.operation_type_combo.findData(operation.operation_type)
        if operation_index >= 0:
            self.operation_type_combo.blockSignals(True)
            self.operation_type_combo.setCurrentIndex(operation_index)
            self.operation_type_combo.blockSignals(False)
        geometry = operation.geometry
        frame = geometry.frame
        profile = geometry.profile
        parameters = operation.parameters
        self.axis_edge_edit.setText(
            "" if frame.axis_reference is None else frame.axis_reference.object_id
        )
        self.contour_edges_edit.setText(
            ",".join(item.object_id for item in profile.contour_references)
        )
        self.surface_faces_edit.setText(
            ",".join(item.object_id for item in profile.surface_references)
        )
        self.axis_origin_edit.setText(self._format_vector(frame.axis_origin_mm))
        self.axis_direction_edit.setText(self._format_vector(frame.axis_direction))
        self.zero_direction_edit.setText(self._format_vector(frame.zero_direction))
        self.positive_direction_combo.setCurrentIndex(
            max(0, self.positive_direction_combo.findData(frame.positive_direction))
        )
        for widget, value in (
            (self.axial_start_spin, profile.axial_start_mm),
            (self.axial_end_spin, profile.axial_end_mm),
            (self.radius_start_spin, profile.radius_start_mm),
            (self.radius_end_spin, profile.radius_end_mm),
            (self.pitch_spin, parameters.pitch_mm),
            (self.start_angle_spin, math.degrees(parameters.start_angle_rad)),
            (self.end_angle_spin, math.degrees(parameters.end_angle_rad)),
            (self.angular_velocity_spin, parameters.angular_velocity_rad_s),
            (self.sampling_angle_spin, math.degrees(parameters.sampling_angle_rad)),
            (self.bead_width_spin, parameters.bead_width_mm),
            (self.layer_height_spin, parameters.layer_height_mm),
            (self.feedrate_spin, parameters.feedrate_mm_min),
            (self.travel_feedrate_spin, parameters.travel_feedrate_mm_min),
            (self.retract_length_spin, parameters.retract_length_mm),
            (self.dwell_spin, parameters.dwell_s),
            (self.axial_step_spin, parameters.axial_step_mm),
            (self.radial_pass_count_spin, parameters.radial_pass_count),
            (self.radial_spacing_spin, parameters.radial_spacing_mm),
            (self.wall_thickness_spin, parameters.wall_thickness_mm),
            (self.connection_clearance_spin, parameters.connection_clearance_mm),
        ):
            widget.setValue(value)
        self.path_direction_combo.setCurrentIndex(
            max(0, self.path_direction_combo.findData(parameters.direction))
        )
        self.thin_wall_policy_combo.setCurrentIndex(
            max(
                0,
                self.thin_wall_policy_combo.findData(parameters.thin_wall_width_policy),
            )
        )
        if geometry.angular_regions:
            self.region_direction_combo.setCurrentIndex(
                max(0, self.region_direction_combo.findData(geometry.angular_regions[0].direction))
            )
        self.region_intervals_edit.setText(
            ";".join(
                f"{math.degrees(item.start_angle_rad):g}:"
                f"{math.degrees(item.end_angle_rad):g}"
                for item in geometry.angular_regions
            )
        )
        self.preview_only_check.setChecked(geometry.preview_only)

    def _update_operation_visibility(self) -> None:
        operation = self._selected_operation()
        operation_type = (
            str(self.operation_type_combo.currentData())
            if operation is None
            else operation.operation_type
        )
        around = operation_type == "rotary_around_part"
        thin_wall = operation_type == "rotary_thin_wall"
        spiral = operation_type == "rotary_spiral"
        for key in ("regions", "region_direction"):
            self._set_row_visible(key, around)
        for key in ("axial_step",):
            self._set_row_visible(key, around or thin_wall)
        for key in (
            "radial_passes",
            "radial_spacing",
            "wall_thickness",
            "thin_wall_policy",
        ):
            self._set_row_visible(key, thin_wall)
        self._set_row_visible("pitch", spiral)

    def _generation_reason(self, operation: Any) -> str | None:
        if operation is None:
            return self._t("operation_required")
        if self.controller.cad_model is None:
            return self._t("no_cad")
        if self.controller.has_drafts or not self.controller.setup_ready:
            return self._t("setup")
        if not operation.enabled:
            return self._t("error")
        if operation.geometry.preview_only:
            return self._t("preview_only")
        if operation.operation_type == "rotary_around_part" and not operation.geometry.angular_regions:
            return self._t("region_required")
        return None

    def _status_text(self, product: Any, reason: str | None) -> str:
        if self._last_error:
            return f"{self._t('status')}: {self._last_error}"
        if product is not None:
            return f"{self._t('status')}: {product.status.upper()} · {self._t(product.status)}"
        return f"{self._t('status')}: {reason or self._t('draft')}"

    def _refresh_issues(self, result: Any) -> None:
        self.issue_list.clear()
        issues: list[Any] = list(self.controller.validation_report().issues)
        if result is not None:
            issues.extend(result.validation.issues)
        operation = self._selected_operation()
        state = None if operation is None else self.controller.product_state(operation.operation_id)
        failure = (
            None
            if state is None or not isinstance(state.result_payload, Mapping)
            else state.result_payload.get("issue")
        )
        if isinstance(failure, Mapping):
            issues.append(failure)
        seen: set[tuple[str, str]] = set()
        for index, issue in enumerate(issues, 1):
            payload = issue if isinstance(issue, Mapping) else issue.to_json()
            code = str(payload.get("code", ""))
            object_id = str(payload.get("object_id", ""))
            key = (code, object_id)
            if key in seen:
                continue
            seen.add(key)
            severity = str(payload.get("severity", "error")).upper()
            text = f"{severity[:1]}{index}: {code.rsplit('.', 1)[-1]}"
            self.issue_list.addItem(text)
            item = self.issue_list.item(self.issue_list.count() - 1)
            item.setData(Qt.UserRole, dict(payload))
            item.setToolTip(f"[{severity}] {code} · {object_id}")
        if not seen:
            self.issue_list.addItem(self._t("no_issues"))

    def _jump_to_issue(self) -> None:
        item = self.issue_list.currentItem()
        payload = None if item is None else item.data(Qt.UserRole)
        if not isinstance(payload, Mapping):
            return
        object_id = str(payload.get("object_id", ""))
        model = self.controller.cad_model
        if model is not None and object_id in model.edge_map:
            self.viewer.set_selection(edge_ids=[object_id])
        elif model is not None and object_id in model.face_map:
            self.viewer.set_selection(face_ids=[object_id])
        else:
            result = self._selected_result()
            if result is not None:
                for index, point in enumerate(result.preview_toolpath.points):
                    if point.point_id == object_id and hasattr(self.viewer, "set_preview_progress"):
                        self.viewer.set_preview_progress(max(0, index - 1))
                        break
        self.status_label.setText(
            f"{self.status_label.text()}\n{payload.get('code', '')} · {object_id}"
        )

    def _show_result(self, operation: Any, result: Any) -> None:
        if operation is None or result is None:
            return
        if self._viewer_operation_id == operation.operation_id:
            return
        if hasattr(self.viewer, "load_gcode_preview"):
            self.viewer.load_gcode_preview(_preview_from_toolpath(result.preview_toolpath))
        self._viewer_operation_id = operation.operation_id

    def _selected_operation(self) -> Any | None:
        if self._selected_operation_id is None:
            return None
        try:
            return self.controller.operation(self._selected_operation_id)
        except ValueError:
            return None

    def _selected_result(self) -> Any | None:
        operation = self._selected_operation()
        return None if operation is None else self.controller.product_result(operation.operation_id)

    def _load_model_into_viewer(self) -> None:
        model = self.controller.cad_model
        if model is None:
            if hasattr(self.viewer, "clear_model"):
                self.viewer.clear_model()
        elif hasattr(self.viewer, "load_model"):
            self.viewer.load_model(model)

    def _install_generation_event_pump(self) -> None:
        self.controller.set_generation_event_pump(QApplication.processEvents)

    def _add_row(self, form: QFormLayout, key: str, widget: QWidget) -> None:
        label = QLabel()
        label.setWordWrap(True)
        form.addRow(label, widget)
        self._rows[key] = (label, widget)

    def _set_row_visible(self, key: str, visible: bool) -> None:
        label, widget = self._rows[key]
        label.setVisible(visible)
        widget.setVisible(visible)

    @staticmethod
    def _double_spin(value: float, minimum: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(4)
        spin.setRange(minimum, 1_000_000.0)
        spin.setValue(value)
        return spin

    @staticmethod
    def _angle_spin(value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(4)
        spin.setRange(-1_000_000.0, 1_000_000.0)
        spin.setValue(value)
        return spin

    @staticmethod
    def _direction_combo() -> QComboBox:
        combo = QComboBox()
        combo.addItem("CCW", "ccw")
        combo.addItem("CW", "cw")
        return combo

    @staticmethod
    def _identifiers(source: str) -> tuple[str, ...]:
        return tuple(item.strip() for item in source.split(",") if item.strip())

    @staticmethod
    def _vector(source: str, name: str) -> tuple[float, float, float]:
        values = tuple(float(item.strip()) for item in source.split(","))
        if len(values) != 3 or any(not math.isfinite(item) for item in values):
            raise ValueError(f"{name} must contain three finite numbers")
        return values

    @staticmethod
    def _format_vector(vector: tuple[float, float, float]) -> str:
        return ",".join(f"{value:g}" for value in vector)

    def _t(self, key: str) -> str:
        return _TEXT[self.language][key]


def _normalise_language(value: Any) -> str:
    return "en" if str(value).lower().startswith("en") else "zh"


def _preview_from_toolpath(toolpath: GeneratedToolpath) -> GCodePreview:
    """Adapt generated geometry without presenting it as imported NC."""

    segments = toolpath.to_preview_segments()
    layers = [segment.layer for segment in segments]
    points = [point for segment in segments for point in (segment.start, segment.end)]
    bounds = None
    if points:
        bounds = (
            cast(Vector3, tuple(min(point[axis] for point in points) for axis in range(3))),
            cast(Vector3, tuple(max(point[axis] for point in points) for axis in range(3))),
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


__all__ = ["RotaryPage"]
