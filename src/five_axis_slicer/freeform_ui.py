"""Bilingual thin GUI adapter for the restricted Freeform controller."""

from __future__ import annotations

import json
from typing import Any, cast

from PyQt5.QtWidgets import QFormLayout, QLabel, QLineEdit

from .curve_ui import CurvePage
from .freeform_commands import FreeformCommandService
from .freeform_controller import FreeformController


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
        self.face_ids_label = QLabel()
        self.guides_json_label = QLabel()
        self.material_plan_label = QLabel()
        extra.addRow(self.face_ids_label, self.face_ids_edit)
        extra.addRow(self.guides_json_label, self.guides_json_edit)
        extra.addRow(self.material_plan_label, self.material_plan_edit)
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
        self.help_label.setText(
            "选择受限面组和贴附于明确邻面的导引边链。可用普通字段编辑一条导引线，也可用 JSON 一次提交多条。输出仅供离线审查，真实宏和控制器未验证。"
            if zh
            else "Select a bounded face group and guide chains attached to explicit faces. Edit one guide with the normal fields or submit multiple guides as JSON. Output is offline-only until controller macros are qualified."
        )
        if not zh:
            self.use_selection_button.setText("Use selected edges")
            self.generate_button.setText("Generate")
            self.export_button.setText("Export bundle")

    def set_controller(self, controller):
        self.controller = controller
        self.commands = cast(Any, FreeformCommandService(controller))
        self._selected_operation_id = None
        self._last_error = None
        self._install_generation_event_pump()
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
            edge_ids, flags = self._directed_edge_inputs()
            guide_face = self.normal_face_edit.text().strip()
            face_ids = tuple(
                item.strip() for item in self.face_ids_edit.text().split(",") if item.strip()
            )
            if not face_ids and guide_face:
                face_ids = (guide_face,)
            material_text = self.material_plan_edit.text().strip()
            material = None if not material_text else json.loads(material_text)
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
                origin="gui",
                **parameters,
            )
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
        self.refresh()

    def _load_controls(self, operation):
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
        mapping = {
            "sampling_step_mm": operation.parameters.sampling_step_mm,
            "chord_error_mm": operation.parameters.chord_error_mm,
            "chain_tolerance_mm": operation.parameters.chain_tolerance_mm,
            "bead_width_mm": operation.parameters.bead_width_mm,
            "layer_height_mm": operation.parameters.layer_height_mm,
            "feedrate_mm_min": operation.parameters.feedrate_mm_min,
            "travel_feedrate_mm_min": operation.parameters.travel_feedrate_mm_min,
            "retract_length_mm": operation.parameters.retract_length_mm,
            "dwell_s": 0.0,
            "offset_spacing_mm": operation.parameters.path_spacing_mm,
            "layer_count": operation.parameters.layer_count,
            "offset_pass_count": operation.parameters.path_count,
        }
        for name, widget in self._spins.items():
            widget.setValue(mapping[name])

    def _use_selected_edges(self):
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


__all__ = ["FreeformPage"]
