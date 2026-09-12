"""Command-backed bilingual Curve C01-C05 editor and Toolpath viewer."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .command_kernel import CommandError
from .curve_commands import CurveCommandService
from .curve_controller import CurveController
from .gcode_preview import GCodePreview
from .manufacturing.toolpath import GeneratedToolpath
from .viewer import ModelViewer


_TEXT = {
    "zh": {
        "title": "曲线沉积工作台",
        "back": "返回",
        "open": "打开 STEP",
        "type": "新建操作类型",
        "existing": "现有操作",
        "edges": "有向边链（逗号分隔）",
        "reverse": "反向标志（0/1，逗号分隔）",
        "normal_mode": "法向来源",
        "adjacent": "明确邻面",
        "specified": "用户指定方向",
        "face": "法向邻面 ID",
        "normal": "指定法向 X,Y,Z",
        "sampling": "弧长采样步长 (mm)",
        "chord": "弦误差 (mm)",
        "tolerance": "链连接容差 (mm)",
        "bead": "道宽 (mm)",
        "height": "层高 (mm)",
        "feed": "沉积进给 (mm/min)",
        "travel": "空移进给 (mm/min)",
        "retract": "回抽长度 (mm)",
        "dwell": "层间停留 (s)",
        "layers": "层数",
        "passes": "横向道数",
        "spacing": "横向道间距 (mm)",
        "selected": "采用 Viewer 已选边",
        "create": "新建操作",
        "apply": "应用",
        "generate": "生成与检查",
        "cancel": "取消生成",
        "export": "导出六件套",
        "undo": "撤销",
        "redo": "重做",
        "help": "按路径顺序填写边 ID；反向标志与边一一对应。双邻面必须明确选择，或改用用户指定法向。修改输入后结果变为 Stale，Error 禁止导出。",
        "no_issues": "当前没有可定位问题。",
    },
    "en": {
        "title": "Curve Deposition Workbench",
        "back": "Back",
        "open": "Open STEP",
        "type": "New operation type",
        "existing": "Existing operation",
        "edges": "Directed edge chain (comma-separated)",
        "reverse": "Reverse flags (0/1, comma-separated)",
        "normal_mode": "Normal source",
        "adjacent": "Explicit adjacent face",
        "specified": "User-specified direction",
        "face": "Normal face ID",
        "normal": "Specified normal X,Y,Z",
        "sampling": "Arc-length sample step (mm)",
        "chord": "Chord error (mm)",
        "tolerance": "Chain tolerance (mm)",
        "bead": "Bead width (mm)",
        "height": "Layer height (mm)",
        "feed": "Deposition feed (mm/min)",
        "travel": "Travel feed (mm/min)",
        "retract": "Retract length (mm)",
        "dwell": "Inter-layer dwell (s)",
        "layers": "Layer count",
        "passes": "Lateral pass count",
        "spacing": "Lateral spacing (mm)",
        "selected": "Use Viewer-selected edges",
        "create": "Create operation",
        "apply": "Apply",
        "generate": "Generate and validate",
        "cancel": "Cancel generation",
        "export": "Export six-file bundle",
        "undo": "Undo",
        "redo": "Redo",
        "help": "Enter edge IDs in traversal order and one reverse flag per edge. Choose an explicit face for ambiguous adjacency, or use a specified normal. Input edits make results Stale; Error blocks export.",
        "no_issues": "No locatable issues.",
    },
}


class CurvePage(QWidget):
    back_requested = pyqtSignal()
    open_step_requested = pyqtSignal()
    preview_ready = pyqtSignal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        controller: CurveController,
        viewer_factory: Callable[[QWidget], QWidget] | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.commands = CurveCommandService(controller)
        self.language = "zh"
        self._selected_operation_id: str | None = None
        self._last_error: str | None = None
        self._generation_in_progress = False
        self.viewer = (viewer_factory or ModelViewer)(self)
        self._build_ui()
        self._install_generation_event_pump()
        self.refresh()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        self.editor_scroll = QScrollArea(self)
        self.editor_scroll.setWidgetResizable(True)
        editor = QWidget(self.editor_scroll)
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
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.operation_type_combo = QComboBox()
        self.operation_type_combo.addItem("Buildup", "curve_buildup")
        self.operation_type_combo.addItem("Multi-pass Buildup", "curve_multi_pass")
        self.operation_type_combo.addItem("Offset Buildup", "curve_offset_buildup")
        self.operation_combo = QComboBox()
        self.edge_ids_edit = QLineEdit()
        self.reverse_flags_edit = QLineEdit()
        self.normal_mode_combo = QComboBox()
        self.normal_mode_combo.addItem("", "adjacent_face")
        self.normal_mode_combo.addItem("", "specified")
        self.normal_face_edit = QLineEdit()
        self.specified_normal_edit = QLineEdit("0,0,1")
        self._spins: dict[str, QDoubleSpinBox | QSpinBox] = {}
        defaults = (
            ("sampling_step_mm", 1.0, 0.001),
            ("chord_error_mm", 0.05, 0.0001),
            ("chain_tolerance_mm", 0.01, 0.0001),
            ("bead_width_mm", 0.6, 0.01),
            ("layer_height_mm", 0.2, 0.01),
            ("feedrate_mm_min", 900.0, 1.0),
            ("travel_feedrate_mm_min", 1800.0, 1.0),
            ("retract_length_mm", 1.0, 0.001),
            ("dwell_s", 0.0, 0.0),
            ("offset_spacing_mm", 0.6, 0.001),
        )
        labels = ("sampling", "chord", "tolerance", "bead", "height", "feed", "travel", "retract", "dwell", "spacing")
        self._rows: list[tuple[QFormLayout, QWidget, str]] = []
        self._add_row(form, self.operation_type_combo, "type")
        self._add_row(form, self.operation_combo, "existing")
        self._add_row(form, self.edge_ids_edit, "edges")
        self._add_row(form, self.reverse_flags_edit, "reverse")
        self._add_row(form, self.normal_mode_combo, "normal_mode")
        self._add_row(form, self.normal_face_edit, "face")
        self._add_row(form, self.specified_normal_edit, "normal")
        for (name, value, minimum), label in zip(defaults, labels, strict=True):
            spin = QDoubleSpinBox()
            spin.setDecimals(4)
            spin.setRange(minimum, 1_000_000.0)
            spin.setValue(value)
            self._spins[name] = spin
            self._add_row(form, spin, label)
        for name, value, label in (("layer_count", 3, "layers"), ("offset_pass_count", 3, "passes")):
            spin = QSpinBox()
            spin.setRange(1, 100)
            spin.setValue(value)
            self._spins[name] = spin
            self._add_row(form, spin, label)
        layout.addLayout(form)
        self.use_selection_button = QPushButton()
        layout.addWidget(self.use_selection_button)
        actions = QGridLayout()
        self.create_button = QPushButton()
        self.apply_button = QPushButton()
        self.generate_button = QPushButton()
        self.cancel_button = QPushButton()
        self.export_button = QPushButton()
        self.undo_button = QPushButton()
        self.redo_button = QPushButton()
        for index, button in enumerate((self.create_button, self.apply_button, self.generate_button, self.cancel_button, self.export_button, self.undo_button, self.redo_button)):
            actions.addWidget(button, index // 2, index % 2)
        layout.addLayout(actions)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.issue_list = QListWidget()
        self.issue_list.setMinimumHeight(110)
        layout.addWidget(self.issue_list)
        self.help_label = QLabel()
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)
        layout.addStretch(1)
        self.editor_scroll.setWidget(editor)
        self.editor_scroll.setMinimumWidth(450)
        root.addWidget(self.editor_scroll, 0)
        root.addWidget(self.viewer, 1)
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
        self.use_selection_button.clicked.connect(self._use_selected_edges)
        self.issue_list.itemDoubleClicked.connect(lambda _item: self._jump_to_issue())
        self.set_language("zh")

    def _add_row(self, form: QFormLayout, widget: QWidget, key: str) -> None:
        label = QLabel()
        label.setWordWrap(True)
        form.addRow(label, widget)
        self._rows.append((form, label, key))

    def set_language(self, language: str) -> None:
        self.language = language if language in _TEXT else "zh"
        text = _TEXT[self.language]
        self.title_label.setText(text["title"])
        for _, label, key in self._rows:
            label.setText(text[key])
        self.normal_mode_combo.setItemText(0, text["adjacent"])
        self.normal_mode_combo.setItemText(1, text["specified"])
        for button, key in ((self.back_button,"back"),(self.open_button,"open"),(self.use_selection_button,"selected"),(self.create_button,"create"),(self.apply_button,"apply"),(self.generate_button,"generate"),(self.cancel_button,"cancel"),(self.export_button,"export"),(self.undo_button,"undo"),(self.redo_button,"redo")):
            button.setText(text[key])
        self.help_label.setText(text["help"])

    def set_controller(self, controller: CurveController) -> None:
        self.controller = controller
        self.commands = CurveCommandService(controller)
        self._selected_operation_id = None
        self._last_error = None
        self._install_generation_event_pump()
        if controller.cad_model is None:
            self.viewer.clear_model()
        else:
            self.viewer.load_model(controller.cad_model)
        self.refresh()

    def state_json(self) -> dict[str, Any]:
        state = self.controller.state_json()
        state.update(
            selected_operation_id=self._selected_operation_id,
            viewer=self.viewer.preview_state(),
            last_error=self._last_error,
            generation_in_progress=self._generation_in_progress,
        )
        return state

    def refresh(self, *_ignored: Any) -> None:
        operations = self.controller.operations
        ids = {item.operation_id for item in operations}
        if self._selected_operation_id not in ids:
            self._selected_operation_id = operations[-1].operation_id if operations else None
        self.operation_combo.blockSignals(True)
        self.operation_combo.clear()
        for item in operations:
            self.operation_combo.addItem(item.name, item.operation_id)
        index = self.operation_combo.findData(self._selected_operation_id)
        if index >= 0:
            self.operation_combo.setCurrentIndex(index)
        self.operation_combo.blockSignals(False)
        operation = self._selected_operation()
        if operation is not None:
            self._load_controls(operation)
        result = None if operation is None else self.controller.product_result(operation.operation_id)
        state = None if operation is None else self.controller.product_state(operation.operation_id)
        setup_issues = self.controller.validation_report().issues
        self._refresh_issues(setup_issues, result)
        complete = bool(operation and operation.geometry.is_complete)
        self.apply_button.setEnabled(operation is not None and not self._generation_in_progress)
        self.generate_button.setEnabled(complete and not self._generation_in_progress)
        exportable = bool(result and result.exportable and state and state.status in {"ready", "warning"})
        self.export_button.setEnabled(exportable and not self._generation_in_progress)
        self.cancel_button.setEnabled(self._generation_in_progress)
        self.create_button.setEnabled(self.controller.can_create_operation and not self._generation_in_progress)
        self.undo_button.setEnabled(self.commands.kernel.can_undo)
        self.redo_button.setEnabled(self.commands.kernel.can_redo)
        status = "draft" if state is None else state.status
        self.status_label.setText(self._last_error or f"Status: {status}")
        if result is not None and state is not None and state.status in {"ready", "warning"}:
            self.viewer.load_gcode_preview(_preview_from_toolpath(result.preview_toolpath))

    def _create(self) -> None:
        try:
            result = self.commands.execute_command("create_operation", str(self.operation_type_combo.currentData()), origin="gui")
            self._selected_operation_id = str(result.payload["operation_id"])
            self._last_error = None
        except (CommandError, KeyError, ValueError, TypeError) as exc:
            self._last_error = str(exc)
        self.refresh()

    def _apply(self) -> None:
        operation = self._selected_operation()
        if operation is None:
            return
        try:
            edge_ids = tuple(item.strip() for item in self.edge_ids_edit.text().split(",") if item.strip())
            flags_raw = tuple(item.strip() for item in self.reverse_flags_edit.text().split(",") if item.strip())
            flags = tuple(item.lower() in {"1", "true", "yes", "y"} for item in flags_raw)
            if flags and len(flags) != len(edge_ids):
                raise ValueError("one reverse flag is required for each edge")
            flags = flags or tuple(False for _ in edge_ids)
            normal_mode = str(self.normal_mode_combo.currentData())
            normal = tuple(float(item.strip()) for item in self.specified_normal_edit.text().split(","))
            kwargs = {name: widget.value() for name, widget in self._spins.items()}
            self.commands.execute_command(
                "set_operation",
                operation_id=operation.operation_id,
                edge_ids=edge_ids,
                reversed_flags=flags,
                normal_mode=normal_mode,
                normal_face_id=self.normal_face_edit.text().strip() or None,
                specified_normal=normal if normal_mode == "specified" else None,
                origin="gui",
                **kwargs,
            )
            self._last_error = None
        except (CommandError, KeyError, ValueError, TypeError) as exc:
            self._last_error = str(exc)
        self.refresh()

    def _generate(self) -> None:
        operation = self._selected_operation()
        if operation is None:
            return
        self._generation_in_progress = True
        self.refresh()
        try:
            response = self.commands.execute_command("generate_operation", operation.operation_id, origin="gui")
            self._last_error = None if response.payload.get("status") != "cancelled" else "Generation cancelled; previous valid result retained."
            result = self.controller.product_result(operation.operation_id)
            if result is not None:
                self.preview_ready.emit(result.preview_toolpath)
        except (CommandError, ValueError, TypeError) as exc:
            self._last_error = str(exc)
        finally:
            self._generation_in_progress = False
            self.refresh()

    def _cancel(self) -> None:
        self.commands.execute_command("cancel_generation", origin="gui")

    def _export(self) -> None:
        operation = self._selected_operation()
        if operation is None:
            return
        destination = QFileDialog.getExistingDirectory(self, self._t("export"))
        if destination:
            try:
                self.commands.execute_command("export_operation", operation.operation_id, destination, origin="gui")
                self._last_error = None
            except (CommandError, ValueError, TypeError) as exc:
                self._last_error = str(exc)
            self.refresh()

    def _undo(self) -> None:
        if self.commands.kernel.can_undo:
            self.commands.execute_command("undo", origin="gui")
            self.refresh()

    def _redo(self) -> None:
        if self.commands.kernel.can_redo:
            self.commands.execute_command("redo", origin="gui")
            self.refresh()

    def _operation_changed(self) -> None:
        value = self.operation_combo.currentData()
        self._selected_operation_id = None if value is None else str(value)
        self._last_error = None
        self.refresh()

    def _use_selected_edges(self) -> None:
        self.edge_ids_edit.setText(",".join(sorted(self.viewer.selection.edge_ids)))
        self.reverse_flags_edit.setText(",".join("0" for _ in self.viewer.selection.edge_ids))

    def _load_controls(self, operation: Any) -> None:
        self.edge_ids_edit.setText(",".join(item.edge.object_id for item in operation.geometry.edges))
        self.reverse_flags_edit.setText(",".join("1" if item.reversed else "0" for item in operation.geometry.edges))
        self.normal_mode_combo.setCurrentIndex(max(0, self.normal_mode_combo.findData(operation.geometry.normal_mode)))
        self.normal_face_edit.setText("" if operation.geometry.normal_face is None else operation.geometry.normal_face.object_id)
        if operation.geometry.specified_normal is not None:
            self.specified_normal_edit.setText(",".join(f"{item:g}" for item in operation.geometry.specified_normal))
        for name, widget in self._spins.items():
            widget.setValue(getattr(operation.parameters, name))

    def _selected_operation(self):
        if self._selected_operation_id is None:
            return None
        try:
            return self.controller.operation(self._selected_operation_id)
        except ValueError:
            return None

    def _refresh_issues(self, setup_issues: Any, result: Any) -> None:
        self.issue_list.clear()
        issues = list(setup_issues)
        if result is not None:
            issues.extend(result.validation.issues)
        for issue in issues:
            item_text = f"[{getattr(issue.severity, 'value', issue.severity).upper()}] {issue.code} · {issue.object_id}"
            self.issue_list.addItem(item_text)
            item = self.issue_list.item(self.issue_list.count() - 1)
            item.setData(Qt.UserRole, issue.to_json())
            item.setToolTip(item_text)
        if not issues:
            self.issue_list.addItem(self._t("no_issues"))

    def _jump_to_issue(self) -> None:
        item = self.issue_list.currentItem()
        payload = None if item is None else item.data(Qt.UserRole)
        if isinstance(payload, Mapping):
            object_id = str(payload.get("object_id", ""))
            if object_id.startswith("edge-"):
                self.viewer.set_selection(edge_ids=[object_id])
            elif object_id.startswith("face-"):
                self.viewer.set_selection(face_ids=[object_id])
            self.status_label.setText(f"{payload.get('code', '')} · {object_id}")

    def _install_generation_event_pump(self) -> None:
        self.controller.set_generation_event_pump(QApplication.processEvents)

    def _t(self, key: str) -> str:
        return _TEXT[self.language][key]


def _preview_from_toolpath(toolpath: GeneratedToolpath) -> GCodePreview:
    segments = toolpath.to_preview_segments()
    layers = [segment.layer for segment in segments]
    points = [point for segment in segments for point in (segment.start, segment.end)]
    bounds = None if not points else (
        tuple(min(point[i] for point in points) for i in range(3)),
        tuple(max(point[i] for point in points) for i in range(3)),
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


__all__ = ["CurvePage"]
