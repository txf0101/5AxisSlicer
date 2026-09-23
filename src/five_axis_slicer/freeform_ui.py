"""Bilingual thin GUI adapter for the restricted Freeform controller."""

from __future__ import annotations

import json
from typing import Any, cast

from PyQt5.QtWidgets import QFormLayout, QLabel, QLineEdit

from .curve_ui import CurvePage
from .freeform_commands import FreeformCommandService
from .freeform_controller import FreeformController
from .manufacturing.freeform_solid_parameters import SOLID_FILL_OPERATION_TYPES


class FreeformPage(CurvePage):
    """Reuse the proven Curve editor shell while exposing Freeform semantics."""

    def __init__(self, parent=None, *, controller: FreeformController, viewer_factory=None):
        super().__init__(
            parent,
            controller=cast(Any, controller),
            viewer_factory=viewer_factory,
        )
        self.editor_scroll.setMinimumWidth(620)
        self.commands = cast(Any, FreeformCommandService(controller))
        self.operation_type_combo.clear()
        self.operation_type_combo.addItem("Surface / 曲面贴合", "freeform_surface")
        self.operation_type_combo.addItem("Thin Wall / 薄壁", "freeform_thin_wall")
        self.operation_type_combo.addItem("Spherical Solid / 球面实体", "spherical_solid_fill")
        self.operation_type_combo.addItem("Surface Solid / 曲面实体", "surface_solid_fill")
        self.operation_type_combo.addItem("Radial Solid / 径向实体", "radial_solid_fill")
        self.normal_mode_combo.setVisible(False)
        self.specified_normal_edit.setVisible(False)
        self._install_generation_event_pump()
        self.set_language(self.language)
        self.refresh()

    def _build_parameter_form(self, layout):
        super()._build_parameter_form(layout)
        extra = QFormLayout()
        extra.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        extra.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self.face_ids_edit = QLineEdit()
        self.guides_json_edit = QLineEdit()
        guides_example = '[{"edge_ids":["..."],"reversed_flags":[false],"face_id":"..."}]'
        self.guides_json_edit.setPlaceholderText("[{...}]")
        self.guides_json_edit.setToolTip(guides_example)
        self.material_plan_edit = QLineEdit()
        self.material_plan_edit.setPlaceholderText("{...}")
        self.material_plan_edit.setToolTip('{"schema_version":1,"plan_id":"..."}')
        self.tool_change_station_edit = QLineEdit()
        self.tool_change_station_edit.setPlaceholderText('{"clearance_z_mm":...,"cutter_xyz_mm":[...]}')
        self.face_ids_label = QLabel()
        self.guides_json_label = QLabel()
        self.material_plan_label = QLabel()
        self.tool_change_station_label = QLabel()
        self.solid_geometry_edit = QLineEdit()
        self.solid_geometry_edit.setPlaceholderText('{"body_ids":["..."]}')
        self.solid_parameters_edit = QLineEdit()
        self.solid_parameters_edit.setPlaceholderText('{"substrate_radius_mm":40.0}')
        self.solid_geometry_label = QLabel()
        self.solid_parameters_label = QLabel()
        extra.addRow(self.face_ids_label, self.face_ids_edit)
        extra.addRow(self.guides_json_label, self.guides_json_edit)
        extra.addRow(self.solid_geometry_label, self.solid_geometry_edit)
        extra.addRow(self.solid_parameters_label, self.solid_parameters_edit)
        extra.addRow(self.material_plan_label, self.material_plan_edit)
        extra.addRow(self.tool_change_station_label, self.tool_change_station_edit)
        layout.addLayout(extra)

    def set_language(self, language):
        super().set_language(language)
        if not hasattr(self, "face_ids_label"):
            return
        zh = self.language == "zh"
        self.title_label.setText("自由曲面离线工作台" if zh else "Freeform Offline Workbench")
        self.face_ids_label.setText("受限面组 ID" if zh else "Bounded face IDs")
        self.guides_json_label.setText("多导引线 JSON" if zh else "Multiple guides JSON")
        self.material_plan_label.setText("材料计划 JSON" if zh else "Material plan JSON")
        self.tool_change_station_label.setText(
            "换料站坐标 JSON" if zh else "Tool-change station JSON"
        )
        self.solid_geometry_label.setText(
            "实体曲层选择 JSON" if zh else "Solid-fill selection JSON"
        )
        self.solid_parameters_label.setText(
            "实体曲层附加参数 JSON" if zh else "Solid-fill extra parameters JSON"
        )
        self._refresh_mode_text(self._selected_operation())
        if not zh:
            self.generate_button.setText("Generate")
            self.export_button.setText("Export bundle")

    def set_controller(self, controller):
        self.controller = controller
        self.commands = cast(Any, FreeformCommandService(controller))
        self._selected_operation_id = None
        self._last_error = None
        self._install_generation_event_pump()
        # A result preview belongs to its source project; the VTK viewer otherwise
        # repaints the previous project's paths over the newly loaded STEP.
        self.viewer.clear_gcode_preview()
        if controller.cad_model is None:
            self.viewer.clear_model()
        else:
            self.viewer.load_model(controller.cad_model)
        self.refresh()

    def _apply(self):
        operation = self._selected_operation()
        if operation is None:
            return
        try:
            if operation.operation_type in SOLID_FILL_OPERATION_TYPES:
                self._apply_solid(operation)
                self._last_error = None
                self.refresh()
                return
            edge_ids, flags = self._directed_edge_inputs()
            guide_face = self.normal_face_edit.text().strip()
            face_ids = tuple(
                item.strip() for item in self.face_ids_edit.text().split(",") if item.strip()
            )
            if not face_ids and guide_face:
                face_ids = (guide_face,)
            material_text = self.material_plan_edit.text().strip()
            material = None if not material_text else json.loads(material_text)
            station_text = self.tool_change_station_edit.text().strip()
            station = None if not station_text else json.loads(station_text)
            guides_text = self.guides_json_edit.text().strip()
            guides = (
                tuple(json.loads(guides_text))
                if guides_text
                else ({"edge_ids": edge_ids, "reversed_flags": flags, "face_id": guide_face},)
            )
            if not guides or any(not isinstance(item, dict) for item in guides):
                raise ValueError("multiple guides JSON must be a non-empty array of objects")
            values = {name: widget.value() for name, widget in self._spins.items()}
            parameters = {
                "sampling_step_mm": values["sampling_step_mm"],
                "chord_error_mm": values["chord_error_mm"],
                "chain_tolerance_mm": values["chain_tolerance_mm"],
                "bead_width_mm": values["bead_width_mm"],
                "layer_height_mm": values["layer_height_mm"],
                "feedrate_mm_min": values["feedrate_mm_min"],
                "travel_feedrate_mm_min": values["travel_feedrate_mm_min"],
                "retract_length_mm": values["retract_length_mm"],
                "path_spacing_mm": values["offset_spacing_mm"],
                "path_count": values["offset_pass_count"],
                "layer_count": values["layer_count"],
            }
            self.commands.execute_command(
                "set_operation",
                operation_id=operation.operation_id,
                face_ids=face_ids,
                guides=guides,
                material_plan=material,
                tool_change_station=station,
                origin="gui",
                **parameters,
            )
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
        self.refresh()

    def _apply_solid(self, operation):
        geometry_text = self.solid_geometry_edit.text().strip()
        if not geometry_text:
            raise ValueError("solid-fill selection JSON is required")
        geometry = json.loads(geometry_text)
        if not isinstance(geometry, dict):
            raise ValueError("solid-fill selection JSON must be an object")
        extra_text = self.solid_parameters_edit.text().strip()
        extra = {} if not extra_text else json.loads(extra_text)
        if not isinstance(extra, dict):
            raise ValueError("solid-fill extra parameters JSON must be an object")
        values = {name: widget.value() for name, widget in self._spins.items()}
        parameters = {
            "sampling_step_mm": values["sampling_step_mm"],
            "bead_width_mm": values["bead_width_mm"],
            "layer_height_mm": values["layer_height_mm"],
            "deposition_feedrate_mm_min": values["feedrate_mm_min"],
            "travel_feedrate_mm_min": values["travel_feedrate_mm_min"],
            "retract_length_mm": values["retract_length_mm"],
            "path_spacing_mm": values["offset_spacing_mm"],
            **extra,
        }
        material_text = self.material_plan_edit.text().strip()
        material = None if not material_text else json.loads(material_text)
        station_text = self.tool_change_station_edit.text().strip()
        station = None if not station_text else json.loads(station_text)
        self.commands.execute_command(
            "set_operation",
            operation_id=operation.operation_id,
            solid_geometry=geometry,
            material_plan=material,
            tool_change_station=station,
            origin="gui",
            **parameters,
        )

    def _load_controls(self, operation):
        is_solid = operation.operation_type in SOLID_FILL_OPERATION_TYPES
        self._set_mode_visibility(is_solid)
        self._refresh_mode_text(operation)
        self.solid_geometry_edit.setText(
            "" if operation.solid_geometry is None else _solid_geometry_input_json(operation)
        )
        self.solid_parameters_edit.setText(
            ""
            if not is_solid or operation.solid_parameters is None
            else json.dumps(
                _solid_extra_parameters(operation.solid_parameters),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        guide = operation.geometry.guides[0] if operation.geometry.guides else None
        self.face_ids_edit.setText(",".join(item.object_id for item in operation.geometry.faces))
        self.edge_ids_edit.setText(
            "" if guide is None else ",".join(item.edge.object_id for item in guide.edges)
        )
        self.reverse_flags_edit.setText(
            "" if guide is None else ",".join("1" if item.reversed else "0" for item in guide.edges)
        )
        self.normal_face_edit.setText(
            "" if guide is None or guide.normal_face is None else guide.normal_face.object_id
        )
        self.guides_json_edit.setText(_guides_json(operation))
        self.material_plan_edit.setText(
            ""
            if operation.material_plan is None
            else json.dumps(
                operation.material_plan.to_json(), ensure_ascii=False, separators=(",", ":")
            )
        )
        station = self.controller.controller_profile.tool_change_station
        self.tool_change_station_edit.setText(
            "" if station is None else json.dumps(
                station.to_json(), ensure_ascii=False, separators=(",", ":")
            )
        )
        source_parameters = (
            operation.solid_parameters if is_solid else operation.parameters
        )
        mapping = {
            "sampling_step_mm": source_parameters.sampling_step_mm,
            "chord_error_mm": operation.parameters.chord_error_mm,
            "chain_tolerance_mm": operation.parameters.chain_tolerance_mm,
            "bead_width_mm": source_parameters.bead_width_mm,
            "layer_height_mm": source_parameters.layer_height_mm,
            "feedrate_mm_min": (
                source_parameters.deposition_feedrate_mm_min
                if is_solid
                else source_parameters.feedrate_mm_min
            ),
            "travel_feedrate_mm_min": source_parameters.travel_feedrate_mm_min,
            "retract_length_mm": source_parameters.retract_length_mm,
            "dwell_s": 0.0,
            "offset_spacing_mm": source_parameters.path_spacing_mm,
            "layer_count": 1 if is_solid else operation.parameters.layer_count,
            "offset_pass_count": 1 if is_solid else operation.parameters.path_count,
        }
        for name, widget in self._spins.items():
            widget.setValue(mapping[name])

    def _set_mode_visibility(self, is_solid: bool) -> None:
        hidden_for_solid = {
            "edges", "reverse", "normal_mode", "face", "normal", "chord",
            "tolerance", "dwell", "layers", "passes",
        }
        for form, label, key in self._rows:
            row, _role = form.getWidgetPosition(label)
            field = form.itemAt(row, QFormLayout.FieldRole)
            visible = key not in hidden_for_solid if is_solid else key != "normal_mode"
            label.setVisible(visible)
            if field is not None and field.widget() is not None:
                field.widget().setVisible(visible)
        for label, field in (
            (self.face_ids_label, self.face_ids_edit),
            (self.guides_json_label, self.guides_json_edit),
        ):
            label.setVisible(not is_solid)
            field.setVisible(not is_solid)
        for label, field in (
            (self.solid_geometry_label, self.solid_geometry_edit),
            (self.solid_parameters_label, self.solid_parameters_edit),
        ):
            label.setVisible(is_solid)
            field.setVisible(is_solid)

    def _refresh_mode_text(self, operation) -> None:
        solid = operation is not None and operation.operation_type in SOLID_FILL_OPERATION_TYPES
        zh = self.language == "zh"
        if solid:
            self.use_selection_button.setText(
                "从 Viewer 已选几何建立候选" if zh else "Use selected geometry"
            )
            self.help_label.setText(
                "核对实体、基体、面和根边的角色及生长轴，再应用。多实体自动候选按体积推断基体，必须人工复核。输出仅供离线检查。"
                if zh else
                "Confirm feature/substrate bodies, surface/root roles and growth axis before Apply. The multi-body candidate guesses the substrate by volume; verify it. Offline review only."
            )
        else:
            self.use_selection_button.setText(
                "采用 Viewer 已选边" if zh else "Use selected edges"
            )
            self.help_label.setText(
                "选择受限面组和贴附于明确邻面的导引边链。可用普通字段编辑一条导引线，也可用 JSON 一次提交多条。输出仅供离线审查，真实宏和控制器未验证。"
                if zh else
                "Select a bounded face group and guide chains attached to explicit faces. Edit one guide with the normal fields or submit multiple guides as JSON. Output is offline-only until controller macros are qualified."
            )

    def _refresh_buttons(self, operation, result, state):
        super()._refresh_buttons(operation, result, state)
        if operation is not None and operation.operation_type in SOLID_FILL_OPERATION_TYPES:
            complete = operation.solid_geometry is not None
            self.generate_button.setEnabled(complete and not self._generation_in_progress)

    def _use_selected_edges(self):
        operation = self._selected_operation()
        if operation is not None and operation.operation_type in SOLID_FILL_OPERATION_TYPES:
            try:
                payload = _solid_selection_from_viewer(operation.operation_type, self.controller.cad_model, self.viewer.selection)
                self.solid_geometry_edit.setText(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                )
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
            self.status_label.setText(self._last_error or "Selection captured; apply to persist it.")
            return
        super()._use_selected_edges()
        faces = sorted(self.viewer.selection.face_ids)
        if faces:
            self.face_ids_edit.setText(",".join(faces))
            self.normal_face_edit.setText(faces[0])


def _guides_json(operation):
    if len(operation.geometry.guides) <= 1:
        return ""
    payload = [
        {
            "edge_ids": [item.edge.object_id for item in guide.edges],
            "reversed_flags": [item.reversed for item in guide.edges],
            "face_id": guide.normal_face.object_id,
        }
        for guide in operation.geometry.guides
    ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _solid_geometry_input_json(operation):
    payload = operation.solid_geometry.to_json()
    operation_type = payload.pop("operation_type")
    substrate = payload.pop("substrate_body", None)
    if substrate is not None:
        payload["substrate_body_id"] = substrate["object_id"]
    if operation_type == "spherical_solid_fill":
        payload["body_ids"] = [item["object_id"] for item in payload.pop("bodies")]
    elif operation_type == "surface_solid_fill":
        payload["bodies"] = [
            {
                "body_id": item["body"]["object_id"],
                "surface_face_id": item["surface_face"]["object_id"],
                "opposite_face_id": item["opposite_face"]["object_id"],
                "root_edge_id": item["root_edge"]["object_id"],
            }
            for item in payload["bodies"]
        ]
    else:
        payload["hub_body_id"] = payload.pop("hub_body")["object_id"]
        payload["blades"] = [
            {
                "body_id": item["body"]["object_id"],
                "root_face_id": item["root_face"]["object_id"],
                "outer_face_id": item["outer_face"]["object_id"],
            }
            for item in payload["blades"]
        ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _solid_extra_parameters(parameters):
    common = {
        "sampling_step_mm",
        "bead_width_mm",
        "layer_height_mm",
        "deposition_feedrate_mm_min",
        "travel_feedrate_mm_min",
        "retract_length_mm",
        "path_spacing_mm",
    }
    return {key: value for key, value in parameters.to_json().items() if key not in common}


def _solid_selection_from_viewer(operation_type, model, selection):
    if model is None:
        raise ValueError("no CAD model is attached")
    body_ids = sorted(selection.body_ids)
    face_ids = sorted(selection.face_ids)
    edge_ids = sorted(selection.edge_ids)
    if operation_type == "spherical_solid_fill":
        if not body_ids:
            raise ValueError("select at least one solid body")
        substrate = None
        if len(body_ids) > 1:
            substrate = max(
                (model.body_map[item] for item in body_ids), key=lambda item: item.volume or 0.0
            ).body_id
            body_ids.remove(substrate)
        return {
            "body_ids": body_ids,
            "center_mm": [0.0, 0.0, 0.0],
            **({} if substrate is None else {"substrate_body_id": substrate}),
        }
    if operation_type == "surface_solid_fill":
        bodies = []
        for edge_id in edge_ids:
            edge = model.edge_map[edge_id]
            selected_faces = [
                model.face_map[item]
                for item in face_ids
                if model.face_map[item].body_id == edge.body_id
            ]
            surface = next((item for item in selected_faces if item.face_id in edge.face_ids), None)
            opposite = next((item for item in selected_faces if item is not surface), None)
            if surface is None or opposite is None:
                raise ValueError("each surface-solid body needs a root edge and two selected faces")
            bodies.append(
                {
                    "body_id": edge.body_id,
                    "surface_face_id": surface.face_id,
                    "opposite_face_id": opposite.face_id,
                    "root_edge_id": edge_id,
                }
            )
        if not bodies:
            raise ValueError("select root edge plus surface and opposite face for each body")
        selected_body_ids = set(body_ids) - {item["body_id"] for item in bodies}
        substrate = (
            None
            if not selected_body_ids
            else max(
                (model.body_map[item] for item in selected_body_ids),
                key=lambda item: item.volume or 0.0,
            ).body_id
        )
        return {
            "bodies": bodies,
            **({} if substrate is None else {"substrate_body_id": substrate}),
        }
    if len(body_ids) < 2:
        raise ValueError("select the hub body and at least one blade body")
    hub = max((model.body_map[item] for item in body_ids), key=lambda item: item.volume or 0.0)
    blades = []
    for body_id in body_ids:
        if body_id == hub.body_id:
            continue
        faces = [model.face_map[item] for item in face_ids if model.face_map[item].body_id == body_id]
        if len(faces) != 2:
            raise ValueError("each radial blade needs exactly two selected radial boundary faces")
        faces.sort(key=lambda item: (item.centroid[0] ** 2 + item.centroid[1] ** 2) ** 0.5)
        blades.append(
            {
                "body_id": body_id,
                "root_face_id": faces[0].face_id,
                "outer_face_id": faces[1].face_id,
            }
        )
    return {
        "hub_body_id": hub.body_id,
        "blades": blades,
        "axis_origin_mm": [0.0, 0.0, 0.0],
        "axis_direction": [0.0, 0.0, 1.0],
        "substrate_body_id": hub.body_id,
    }


__all__ = ["FreeformPage"]
