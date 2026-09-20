"""Qt controls for editing and generating one Tube operation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .ui_controls import OptionalDoubleSpinBox
from .models import PickHit, PickRequest

GEOMETRY_FIELDS = (
    ("tube_body_id", "tube_body"),
    ("entry_port_id", "entry_port"),
    ("exit_port_id", "exit_port"),
    ("substrate_body_id", "substrate"),
)
PARAMETER_FIELDS = (
    ("bead_width_mm", "bead_width", 0.01, 100.0),
    ("layer_height_mm", "layer_height", 0.01, 100.0),
    ("max_wedge_angle_deg", "max_wedge_angle", 0.1, 90.0),
    ("max_bead_height_error_mm", "max_bead_error", 0.0001, 100.0),
    ("safe_clearance_mm", "safe_clearance", 0.01, 10000.0),
    ("retract_length_mm", "retract_length", 0.01, 1000.0),
    ("deposition_feedrate_mm_min", "deposition_feedrate", 0.1, 1.0e6),
    ("travel_feedrate_mm_min", "travel_feedrate", 0.1, 1.0e6),
    ("contour_chord_error_mm", "chord_error", 0.0001, 100.0),
)
_BUILDUP_FIELDS = ("maximum_pass_spacing_mm", "include_planar_base", "base_order")
_CONTINUOUS_FIELDS = ("seam_angle_deg",)


def _spin(low: float, high: float, value: float, decimals: int) -> OptionalDoubleSpinBox:
    spin = OptionalDoubleSpinBox()
    spin.setRange(low, high)
    spin.setDecimals(decimals)
    spin.setValue(value)
    spin.setKeyboardTracking(False)
    return spin


def _add_geometry_controls(page: Any, form: QFormLayout) -> None:
    page._operation_geometry_combos = {}
    page._operation_pick_buttons = {}
    page._operation_pick_field = None
    for key, _label_key in GEOMETRY_FIELDS:
        combo = QComboBox()
        combo.setObjectName(f"operation_{key}")
        combo.currentIndexChanged.connect(lambda _index, owner=page: role_changed(owner))
        label = QLabel()
        setattr(page, f"operation_{key}_label", label)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(combo, 1)
        button = QPushButton()
        button.setObjectName(f"pick_{key}")
        button.clicked.connect(lambda _checked=False, field=key: start_pick(page, field))
        row_layout.addWidget(button)
        page._operation_pick_buttons[key] = button
        form.addRow(label, row)
        page._operation_geometry_combos[key] = combo


def build_editor(page: Any) -> QWidget:
    editor = QWidget()
    layout = QVBoxLayout(editor)
    page.operation_help = QLabel()
    page.operation_help.setObjectName("mutedText")
    page.operation_help.setWordWrap(True)
    form = QFormLayout()
    page.operation_type_value = QLabel()
    page.operation_type_value.setObjectName("valueText")
    page.operation_type_label = QLabel()
    form.addRow(page.operation_type_label, page.operation_type_value)
    _add_geometry_controls(page, form)
    page._operation_parameter_spins = {}
    for key, _label_key, low, high in PARAMETER_FIELDS:
        spin = _spin(low, high, low, 4)
        spin.setObjectName(f"operation_{key}")
        label = QLabel()
        setattr(page, f"operation_{key}_label", label)
        form.addRow(label, spin)
        page._operation_parameter_spins[key] = spin
    _add_type_config_controls(page, form)
    page.operation_apply_button = QPushButton()
    page.operation_apply_button.setObjectName("primaryButton")
    page.operation_apply_button.clicked.connect(lambda _checked=False, owner=page: apply(owner))
    page.operation_feedback = QLabel()
    page.operation_feedback.setWordWrap(True)
    page._operation_feedback_key = None
    layout.addWidget(page.operation_help)
    layout.addLayout(form)
    actions = QGridLayout()
    page.operation_generate_button = QPushButton()
    page.operation_cancel_button = QPushButton()
    page.operation_preview_button = QPushButton()
    page.operation_export_button = QPushButton()
    actions.addWidget(page.operation_generate_button, 0, 0)
    actions.addWidget(page.operation_cancel_button, 0, 1)
    actions.addWidget(page.operation_preview_button, 1, 0)
    actions.addWidget(page.operation_export_button, 1, 1)
    page.operation_generate_button.clicked.connect(
        lambda _checked=False, owner=page: generate(owner)
    )
    page.operation_cancel_button.clicked.connect(lambda _checked=False, owner=page: cancel(owner))
    page.operation_preview_button.clicked.connect(lambda _checked=False, owner=page: preview(owner))
    page.operation_export_button.clicked.connect(lambda _checked=False, owner=page: export(owner))
    page.operation_generation_status = QLabel()
    page.operation_generation_status.setWordWrap(True)
    layout.addLayout(actions)
    layout.addWidget(page.operation_generation_status)
    layout.addStretch(1)
    return editor


def _add_type_config_controls(page: Any, form: QFormLayout) -> None:
    page._operation_type_controls = {}
    page.operation_maximum_pass_spacing_mm = _spin(0.01, 100.0, 0.6, 4)
    page.operation_maximum_pass_spacing_mm_label = QLabel()
    form.addRow(
        page.operation_maximum_pass_spacing_mm_label,
        page.operation_maximum_pass_spacing_mm,
    )
    page._operation_type_controls["maximum_pass_spacing_mm"] = (
        page.operation_maximum_pass_spacing_mm_label,
        page.operation_maximum_pass_spacing_mm,
    )
    page.operation_include_planar_base = QCheckBox()
    page.operation_include_planar_base_label = QLabel()
    form.addRow(page.operation_include_planar_base_label, page.operation_include_planar_base)
    page._operation_type_controls["include_planar_base"] = (
        page.operation_include_planar_base_label,
        page.operation_include_planar_base,
    )
    page.operation_base_order = QComboBox()
    page.operation_base_order.addItem("before_tube", "before_tube")
    page.operation_base_order.addItem("after_tube", "after_tube")
    page.operation_base_order_label = QLabel()
    form.addRow(page.operation_base_order_label, page.operation_base_order)
    page._operation_type_controls["base_order"] = (
        page.operation_base_order_label,
        page.operation_base_order,
    )
    page.operation_seam_angle_deg = _spin(-36000.0, 36000.0, 0.0, 3)
    page.operation_seam_angle_deg_label = QLabel()
    form.addRow(page.operation_seam_angle_deg_label, page.operation_seam_angle_deg)
    page._operation_type_controls["seam_angle_deg"] = (
        page.operation_seam_angle_deg_label,
        page.operation_seam_angle_deg,
    )


def role_changed(page: Any) -> None:
    body_ids = _selected_ids(page, ("tube_body_id", "substrate_body_id"))
    edge_ids = _selected_ids(page, ("entry_port_id", "exit_port_id"))
    if hasattr(page.viewer, "set_selection"):
        page.viewer.set_selection(body_ids=body_ids, edge_ids=edge_ids)


def start_pick(page: Any, field: str) -> None:
    """Select an explicit role before accepting one hit from the model viewer."""
    combo = page._operation_geometry_combos[field]
    allowed = frozenset(str(combo.itemData(i)) for i in range(1, combo.count()))
    page._pick_context = None
    page._operation_pick_field = field
    page.set_view_mode("model")
    page.viewer.set_pick_request(
        PickRequest("body" if field.endswith("body_id") else "edge", allowed_ids=allowed)
    )
    page._operation_feedback_key = "operation_pick_pending"
    page.operation_feedback.setText(page._t("operation_pick_pending"))


def accept_pick(page: Any, hit: PickHit) -> bool:
    field = page._operation_pick_field
    if field is None:
        return False
    combo = page._operation_geometry_combos[field]
    expected = "body" if field.endswith("body_id") else "edge"
    index = combo.findData(hit.entity_id)
    if hit.kind != expected or index < 1:
        return True  # Ignore stale or wrong-kind hits without changing the draft.
    combo.setCurrentIndex(index)
    page._operation_pick_field = None
    page.viewer.set_pick_request(PickRequest("edge", multiple=True))
    role_changed(page)
    page._operation_feedback_key = "operation_pick_bound"
    page.operation_feedback.setText(page._t("operation_pick_bound"))
    return True


def apply(page: Any) -> None:
    try:
        kwargs = {
            key: combo.currentData()
            for key, combo in page._operation_geometry_combos.items()
            if combo.currentData()
        }
        kwargs.update({key: spin.value() for key, spin in page._operation_parameter_spins.items()})
        kwargs["operation_id"] = page._selected_operation_id
        operation_type = page._selected_operation_type
        if operation_type == "tube_buildup":
            kwargs.update(
                maximum_pass_spacing_mm=page.operation_maximum_pass_spacing_mm.value(),
                include_planar_base=page.operation_include_planar_base.isChecked(),
                base_order=page.operation_base_order.currentData(),
            )
        elif operation_type == "tube_continuous":
            kwargs["seam_angle_deg"] = page.operation_seam_angle_deg.value()
        page._execute_command("set_operation", **kwargs)
        page._operation_feedback_key = "operation_applied"
        page.operation_feedback.setText(page._t(page._operation_feedback_key))
    except Exception as exc:
        page._operation_feedback_key = None
        page._report_error(exc, page.operation_feedback)


def generate(page: Any) -> None:
    _set_generation_busy(page, True)
    page.controller.set_generation_event_pump(QApplication.processEvents)
    try:
        page.operation_generation_status.setText(page._t("generation_running"))
        payload = page._execute_command(
            "generate_operation", operation_id=page._selected_operation_id
        )
        _refresh_product_status(page)
        if isinstance(payload, dict) and payload.get("status") == "cancelled":
            page.operation_generation_status.setText(page._t("generation_cancelled"))
    except Exception as exc:
        page._report_error(exc, page.operation_generation_status)
    finally:
        page.controller.set_generation_event_pump(None)
        _set_generation_busy(page, False)
        _refresh_product_status(page, preserve_message=True)


def cancel(page: Any) -> None:
    page._execute_command("cancel_generation")
    page.operation_generation_status.setText(page._t("generation_cancel_requested"))


def preview(page: Any) -> None:
    try:
        from .gcode_preview import parse_gcode

        state = page.controller.product_state(page._selected_operation_id)
        result = page.controller.product_result(page._selected_operation_id)
        if state is None or state.status not in {"ready", "warning"}:
            raise ValueError(page._t("generation_preview_unavailable"))
        if result is None or not result.gcode:
            raise ValueError(page._t("generation_preview_unavailable"))
        gcode = parse_gcode(result.gcode, f"{page._selected_operation_id}.gcode")
        if hasattr(page.viewer, "load_gcode_preview"):
            page.viewer.load_gcode_preview(gcode)
        page.operation_generation_status.setText(page._t("generation_preview_ready"))
    except Exception as exc:
        page._report_error(exc, page.operation_generation_status)


def export(page: Any) -> None:
    destination = QFileDialog.getExistingDirectory(page, page._t("export_result"))
    if not destination:
        return
    try:
        page._execute_command(
            "export_operation",
            page._selected_operation_id,
            destination,
        )
        page.operation_generation_status.setText(page._t("generation_exported"))
    except Exception as exc:
        page._report_error(exc, page.operation_generation_status)


def populate_editor(page: Any, operation_id: str | None = None) -> None:
    page._operation_pick_field = None
    if not page.controller.operations:
        return
    operation = _selected_operation(page, operation_id)
    page._selected_operation_id = operation.operation_id
    page._selected_operation_type = operation.operation_type
    page.editor_title.setText(_operation_type_label(page, operation.operation_type))
    page.operation_type_value.setText(_operation_type_label(page, operation.operation_type))
    bodies = () if page.model is None else page.model.solid_bodies
    circular_edges = (
        ()
        if page.model is None
        else tuple(edge for edge in page.model.edges if edge.curve_type == "circle")
    )
    for key, combo in page._operation_geometry_combos.items():
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(page._t("not_set"), None)
        if key in {"tube_body_id", "substrate_body_id"}:
            for body in bodies:
                combo.addItem(f"{body.body_id} · {body.name}", body.body_id)
        else:
            for edge in circular_edges:
                radius = "?" if edge.radius is None else f"{edge.radius:.3f} mm"
                combo.addItem(f"{edge.edge_id} · R={radius}", edge.edge_id)
        reference = getattr(operation.geometry, key.removesuffix("_id"), None)
        combo.setCurrentIndex(max(0, combo.findData(reference.object_id if reference else None)))
        combo.blockSignals(False)
    for key, spin in page._operation_parameter_spins.items():
        spin.setValue(float(getattr(operation.parameters, key)))
    _populate_type_config(page, operation)
    _refresh_product_status(page)


def retranslate(page: Any, translate: Callable[[str], str]) -> None:
    page.operation_type_label.setText(translate("operation_type"))
    for field, label_key in GEOMETRY_FIELDS:
        getattr(page, f"operation_{field}_label").setText(translate(label_key))
        page._operation_pick_buttons[field].setText(translate("operation_pick"))
    for field, label_key, _low, _high in PARAMETER_FIELDS:
        getattr(page, f"operation_{field}_label").setText(translate(label_key))
    page.operation_maximum_pass_spacing_mm_label.setText(translate("maximum_pass_spacing"))
    page.operation_include_planar_base_label.setText(translate("include_planar_base"))
    page.operation_include_planar_base.setText(translate("include_planar_base"))
    page.operation_base_order_label.setText(translate("base_order"))
    page.operation_base_order.setItemText(0, translate("before_tube"))
    page.operation_base_order.setItemText(1, translate("after_tube"))
    page.operation_seam_angle_deg_label.setText(translate("seam_angle"))
    page.operation_generate_button.setText(translate("generate"))
    page.operation_cancel_button.setText(translate("cancel_generation"))
    page.operation_preview_button.setText(translate("preview_result"))
    page.operation_export_button.setText(translate("export_result"))
    if page._operation_feedback_key is not None:
        page.operation_feedback.setText(translate(page._operation_feedback_key))


def _selected_ids(page: Any, fields: tuple[str, ...]) -> list[str]:
    return [
        str(page._operation_geometry_combos[key].currentData())
        for key in fields
        if page._operation_geometry_combos[key].currentData()
    ]


def _selected_operation(page: Any, operation_id: str | None) -> Any:
    return next(
        (item for item in page.controller.operations if item.operation_id == operation_id),
        page.controller.operations[0],
    )


def _populate_type_config(page: Any, operation: Any) -> None:
    _set_type_control_visibility(page, operation.operation_type)
    if operation.operation_type == "tube_buildup":
        config = operation.type_config
        page.operation_maximum_pass_spacing_mm.setValue(float(config.maximum_pass_spacing_mm))
        page.operation_include_planar_base.setChecked(config.include_planar_base)
        page.operation_base_order.setCurrentIndex(
            max(0, page.operation_base_order.findData(config.base_order))
        )
    elif operation.operation_type == "tube_continuous":
        page.operation_seam_angle_deg.setValue(float(operation.type_config.seam_angle_deg))


def _set_type_control_visibility(page: Any, operation_type: str) -> None:
    visible = set(
        _BUILDUP_FIELDS
        if operation_type == "tube_buildup"
        else _CONTINUOUS_FIELDS
        if operation_type == "tube_continuous"
        else ()
    )
    for key, controls in page._operation_type_controls.items():
        for control in controls:
            control.setVisible(key in visible)


def _operation_type_label(page: Any, operation_type: str) -> str:
    return page._t(f"operation_type_{operation_type}")


def _refresh_product_status(page: Any, *, preserve_message: bool = False) -> None:
    state = page.controller.product_state(page._selected_operation_id)
    status = "draft" if state is None else state.status
    if not preserve_message:
        message = page._t(f"generation_{status}")
        if state is not None and status == "error" and state.result_payload:
            detail = state.result_payload.get("error")
            if detail:
                message += "\n" + str(detail)
        page.operation_generation_status.setText(message)
    page.operation_preview_button.setEnabled(status in {"ready", "warning"})
    page.operation_export_button.setEnabled(status in {"ready", "warning"})
    page.operation_generate_button.setEnabled(
        page.model is not None and page.controller.setup_ready and not page.controller.has_drafts
    )
    page.operation_cancel_button.setEnabled(status == "running")


def _set_generation_busy(page: Any, busy: bool) -> None:
    page.operation_apply_button.setEnabled(not busy)
    page.operation_generate_button.setEnabled(
        not busy
        and page.model is not None
        and page.controller.setup_ready
        and not page.controller.has_drafts
    )
    if busy:
        page.operation_preview_button.setEnabled(False)
        page.operation_export_button.setEnabled(False)
    page.operation_cancel_button.setEnabled(busy)


__all__ = [
    "apply",
    "build_editor",
    "cancel",
    "export",
    "generate",
    "populate_editor",
    "preview",
    "retranslate",
    "role_changed",
]
