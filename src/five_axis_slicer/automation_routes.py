"""Stable automation routes for the Qt application shell.

This adapter owns endpoint parsing and delegates state changes to ``MainWindow``
or its pages.  Keeping the routing table outside the window prevents network
compatibility code from inflating UI construction and lifecycle logic.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QTimer

from .localization import tr
from .tube_script_service import command_result_json

Payload = dict[str, Any]
Response = dict[str, Any]
Route = Callable[[Payload], Response]


class AutomationRouter:
    """Dispatch the public HTTP contract against one live application window."""

    def __init__(self, window: Any) -> None:
        # Duck typing avoids a UI/router import cycle; endpoint tests cover the adapter.
        self.window = window
        self._routes: dict[str, Route] = {
            "/health": self._health,
            "/state": self._state,
            "/workbench/select": self._select_workbench,
            "/demo/load": self._load_demo,
            "/model/open": self._open_model,
            "/model/state": self._model_state,
            "/model/cancel": self._cancel_model,
            "/project/open": self._open_project,
            "/project/state": self._project_state,
            "/project/cancel": self._cancel_project,
            "/project/save": self._save_project,
            "/gcode/open": self._open_gcode,
            "/results/demo": self._results_demo,
            "/results/open": self._results_open,
            "/results/state": self._results_state,
            "/results/perf": self._results_perf,
            "/results/quality": self._results_quality,
            "/results/focus": self._results_focus,
            "/results/cancel": self._results_cancel,
            "/preview/state": self._preview_state,
            "/preview/perf": self._preview_perf,
            "/preview/layers": self._preview_layers,
            "/preview/progress": self._preview_progress,
            "/preview/visibility": self._preview_visibility,
            "/selection/mode": self._selection_mode,
            "/selection/set": self._selection_set,
            "/selection/clear": self._selection_clear,
            "/camera": self._camera,
        }
        self._tube_routes: dict[str, Route] = {
            "/tube/state": self._tube_state,
            "/tube/source/update": self._tube_source_update,
            "/tube/operation/create": self._tube_operation_create,
            "/tube/operation/set": self._tube_operation_set,
            "/tube/operation/generate": self._tube_operation_generate,
            "/tube/operation/export": self._tube_operation_export,
            "/tube/generation/state": self._tube_generation_state,
            "/tube/part/confirm": self._tube_part_confirm,
            "/tube/resource/select": self._tube_resource_select,
            "/tube/coordinate/apply": self._tube_coordinate_apply,
            "/tube/placement/apply": self._tube_placement_apply,
            "/tube/draft/discard": self._tube_draft_discard,
            "/tube/view": self._tube_view,
        }
        self._planar_routes: dict[str, Route] = {
            "/planar/state": self._planar_state,
            "/planar/issues": self._planar_issues,
            "/planar/validate": self._planar_validate,
            "/planar/operation/create": self._planar_operation_create,
            "/planar/operation/set": self._planar_operation_set,
            "/planar/operation/generate": self._planar_operation_generate,
            "/planar/operation/export": self._planar_operation_export,
            "/planar/generation/cancel": self._planar_generation_cancel,
            "/planar/undo": self._planar_undo,
            "/planar/redo": self._planar_redo,
        }
        self._curve_routes: dict[str, Route] = {
            "/curve/state": self._curve_state,
            "/curve/issues": self._curve_issues,
            "/curve/validate": self._curve_validate,
            "/curve/operation/create": self._curve_operation_create,
            "/curve/operation/set": self._curve_operation_set,
            "/curve/operation/generate": self._curve_operation_generate,
            "/curve/operation/export": self._curve_operation_export,
            "/curve/generation/cancel": self._curve_generation_cancel,
            "/curve/undo": self._curve_undo,
            "/curve/redo": self._curve_redo,
        }

    def dispatch(self, path: str, payload: Payload) -> Response:
        handler = self._routes.get(path)
        if handler is not None:
            return handler(payload)
        tube_handler = self._tube_routes.get(path)
        if tube_handler is not None:
            result = tube_handler(payload)
            if result:
                return result
            return {"tube": self.window.tube_page.state_json()}
        planar_handler = self._planar_routes.get(path)
        if planar_handler is not None:
            return planar_handler(payload)
        curve_handler = self._curve_routes.get(path)
        if curve_handler is not None:
            return curve_handler(payload)
        raise RuntimeError(f"Unknown endpoint: {path}")

    def _health(self, _payload: Payload) -> Response:
        return {"status": "ready", "app": "5AxisSclicer V2.0"}

    def _state(self, _payload: Payload) -> Response:
        return self.window.current_state()

    def _select_workbench(self, payload: Payload) -> Response:
        self.window.enter_workbench(str(payload["key"]))
        return self.window.current_state()

    def _load_demo(self, _payload: Payload) -> Response:
        self.window.load_demo()
        return self.window.current_state()

    def _open_model(self, payload: Payload) -> Response:
        return self.window.open_model(
            payload["path"],
            show_dialog=False,
            length_unit_override=payload.get("length_unit_override"),
        )

    def _model_state(self, _payload: Payload) -> Response:
        return {"model_load": self.window.model_load_state()}

    def _cancel_model(self, _payload: Payload) -> Response:
        self.window.cancel_model_load()
        return {"model_load": self.window.model_load_state()}

    def _open_project(self, payload: Payload) -> Response:
        return self.window.open_project(
            payload["path"],
            wait=bool(payload.get("wait", True)),
            timeout_ms=int(payload.get("timeout_ms", 120_000)),
            length_unit_override=payload.get("length_unit_override"),
            show_dialog=False,
        )

    def _project_state(self, _payload: Payload) -> Response:
        return {"project_load": self.window.project_load_state()}

    def _cancel_project(self, _payload: Payload) -> Response:
        self.window.cancel_project_load()
        return {"project_load": self.window.project_load_state()}

    def _save_project(self, payload: Payload) -> Response:
        return self.window.save_project_to(
            payload["directory"],
            draft_resolution=payload.get("draft_resolution"),
        )

    def _open_gcode(self, payload: Payload) -> Response:
        return self.window.open_gcode(payload["path"], show_dialog=False)

    def _results_demo(self, _payload: Payload) -> Response:
        return self.window.load_results_demo()

    def _results_open(self, payload: Payload) -> Response:
        model_path = payload.get("model_path")
        gcode_path = payload.get("gcode_path")
        generic_path = payload.get("path")
        if generic_path and model_path is None and gcode_path is None:
            suffix = Path(str(generic_path)).suffix.lower()
            if suffix in {".step", ".stp"}:
                model_path = generic_path
            elif suffix in {".gcode", ".nc", ".tap", ".txt"}:
                gcode_path = generic_path
            else:
                raise RuntimeError(
                    tr(self.window.language, "error_unsupported_file", suffix=suffix)
                )
        return self.window.start_result_load(
            model_path=model_path,
            gcode_path=gcode_path,
        )

    def _results_state(self, _payload: Payload) -> Response:
        return {
            "results": self.window.result_page.state_json(),
            "load_metrics": self.window._public_load_metrics(),
        }

    def _results_perf(self, _payload: Payload) -> Response:
        return {"results_perf": self.window.benchmark_result_render()}

    def _results_quality(self, payload: Payload) -> Response:
        self.window.result_page.set_quality_mode(str(payload.get("mode", "interactive")))
        self.window._sync_result_actions()
        return {"results": self.window.result_page.state_json()}

    def _results_focus(self, payload: Payload) -> Response:
        self.window.result_page.focus_analysis_section(str(payload.get("section", "top")))
        return {"results": self.window.result_page.state_json()}

    def _results_cancel(self, _payload: Payload) -> Response:
        self.window.cancel_result_load()
        return {"results": self.window.result_page.state_json()}

    def _preview_state(self, _payload: Payload) -> Response:
        return {"preview": self.window._active_viewer().preview_state()}

    def _preview_perf(self, _payload: Payload) -> Response:
        return {"preview_perf": self.window._active_viewer().performance_state()}

    def _preview_layers(self, payload: Payload) -> Response:
        viewer = self.window._active_viewer()
        viewer.set_preview_layers(
            int(payload["layer_min"]),
            int(payload["layer_max"]),
        )
        self.window._sync_preview_controls()
        return {"preview": viewer.preview_state()}

    def _preview_progress(self, payload: Payload) -> Response:
        index = int(payload.get("progress_index", payload.get("index", 0)))
        interactive = bool(payload.get("interactive", False))
        viewer = self.window._active_viewer()
        viewer.set_preview_progress(index, interactive=interactive)
        self.window._sync_progress_controls()
        self.window._update_preview_summary()
        if not interactive:
            QTimer.singleShot(250, self.window._update_preview_summary)
        return {"preview": viewer.preview_state()}

    def _preview_visibility(self, payload: Payload) -> Response:
        viewer = self.window._active_viewer()
        viewer.set_preview_visibility(
            show_travel=payload.get("show_travel"),
            show_extrusion=payload.get("show_extrusion"),
            visible_roles=payload.get("visible_roles"),
            show_pose_samples=payload.get("show_pose_samples"),
        )
        self.window._sync_legend_from_settings()
        self.window._update_preview_summary()
        return {"preview": viewer.preview_state()}

    def _active_selection_viewer(self) -> Any:
        return self.window._active_workbench_viewer()

    def _refresh_selection(self) -> None:
        self.window._refresh_active_workbench()

    def _selection_mode(self, payload: Payload) -> Response:
        self.window.set_mode(str(payload["mode"]))
        return self.window.current_state()

    def _selection_set(self, payload: Payload) -> Response:
        self._active_selection_viewer().set_selection(
            body_ids=payload.get("body_ids"),
            edge_ids=payload.get("edge_ids"),
            face_ids=payload.get("face_ids"),
            vertex_ids=payload.get("vertex_ids"),
        )
        self._refresh_selection()
        return self.window.current_state()

    def _selection_clear(self, _payload: Payload) -> Response:
        self._active_selection_viewer().clear_selection()
        self._refresh_selection()
        return self.window.current_state()

    def _camera(self, payload: Payload) -> Response:
        self.window._active_viewer().camera_command(
            str(payload.get("command", "fit")),
            float(payload.get("value", 10.0)),
        )
        return self.window.current_state()

    def _tube_state(self, _payload: Payload) -> Response:
        state = self.window.tube_page.state_json()
        state["commands"] = self.window.tube_script_service.state_json()
        return {"tube": state}

    def _tube_source_update(self, payload: Payload) -> Response:
        return self.window.update_model_from_original_source(
            path=payload.get("path"),
            length_unit_override=payload.get("length_unit_override"),
            draft_resolution=payload.get("draft_resolution"),
            show_dialog=False,
        )

    def _tube_operation_create(self, payload: Payload) -> Response:
        kwargs = {
            key: payload[key]
            for key in ("operation_type", "operation_id", "name")
            if key in payload
        }
        return self._tube_command("create_operation", payload, **kwargs)

    def _tube_operation_set(self, payload: Payload) -> Response:
        allowed = (
            "operation_id",
            "name",
            "enabled",
            "tube_body_id",
            "entry_port_id",
            "exit_port_id",
            "substrate_body_id",
            "manual_centerline_edge_ids",
            "bead_width_mm",
            "layer_height_mm",
            "max_wedge_angle_deg",
            "max_bead_height_error_mm",
            "safe_clearance_mm",
            "retract_length_mm",
            "deposition_feedrate_mm_min",
            "travel_feedrate_mm_min",
            "contour_chord_error_mm",
            "maximum_pass_spacing_mm",
            "include_planar_base",
            "base_order",
            "seam_angle_deg",
        )
        return self._tube_command(
            "set_operation",
            payload,
            **{key: payload[key] for key in allowed if key in payload},
        )

    def _tube_operation_generate(self, payload: Payload) -> Response:
        return self._tube_command(
            "generate_operation", payload, operation_id=payload.get("operation_id")
        )

    def _tube_operation_export(self, payload: Payload) -> Response:
        return self._tube_command(
            "export_operation",
            payload,
            operation_id=str(payload["operation_id"]),
            destination=str(payload["destination"]),
        )

    def _tube_generation_state(self, _payload: Payload) -> Response:
        return {"products": self.window.tube_page.controller.state_json().get("products", [])}

    def _tube_part_confirm(self, payload: Payload) -> Response:
        return self._tube_command(
            "confirm_part",
            payload,
            part_body_ids=payload.get("part_body_ids"),
            ignored_body_ids=payload.get("ignored_body_ids", ()),
        )

    def _tube_resource_select(self, payload: Payload) -> Response:
        kind = str(payload["kind"]).strip().lower()
        identifier = str(payload["identifier"])
        resource_id = self.window.tube_script_service.resolve_resource_id(kind, identifier)
        if kind == "nozzle" and payload.get("complete"):
            fields = {
                key: payload[key]
                for key in (
                    "interface",
                    "length_mm",
                    "construction_material",
                    "flow_category",
                    "temperature_limit_c",
                    "wear_resistance_rating",
                    "outer_profile_rz_mm",
                )
                if key in payload
            }
            return self._tube_command("set_complete_nozzle", payload, resource_id, fields)
        kwargs: dict[str, Any] = {}
        if kind == "material" and "review_confirmed" in payload:
            kwargs["review_confirmed"] = payload["review_confirmed"]
        if kind == "nozzle":
            for key in ("interface", "length_mm", "use_collision_envelope"):
                if key in payload:
                    kwargs[key] = payload[key]
        return self._tube_command(f"set_{kind}", payload, resource_id, **kwargs)

    def _tube_coordinate_apply(self, payload: Payload) -> Response:
        node = str(payload["node"]).strip().lower()
        if node not in {"model_cs", "build_cs"}:
            raise ValueError(f"unsupported coordinate node: {node!r}")
        z_direction = automation_vector(payload, "z_direction", (0.0, 0.0, 1.0))
        x_direction = automation_vector(payload, "x_direction", (1.0, 0.0, 0.0))
        if bool(payload.get("flip_z", False)):
            z_direction = (-z_direction[0], -z_direction[1], -z_direction[2])
        if bool(payload.get("flip_x", False)):
            x_direction = (-x_direction[0], -x_direction[1], -x_direction[2])
        return self._tube_command(
            "set_model_cs" if node == "model_cs" else "set_build_cs",
            payload,
            origin=automation_vector(payload, "origin", (0.0, 0.0, 0.0)),
            z=z_direction,
            x=x_direction,
            input_frame=payload.get("input_frame", "source" if node == "model_cs" else "model"),
        )

    def _tube_placement_apply(self, payload: Payload) -> Response:
        return self._tube_command(
            "set_placement",
            payload,
            str(payload["mount_datum_id"]),
            translation_mm=automation_vector(payload, "translation_mm", (0.0, 0.0, 0.0)),
            rotation_xyz_deg=automation_vector(payload, "rotation_xyz_deg", (0.0, 0.0, 0.0)),
        )

    def _tube_draft_discard(self, payload: Payload) -> Response:
        return self._tube_command("discard_all_drafts", payload)

    def _tube_view(self, payload: Payload) -> Response:
        self.window.tube_page.set_view_mode(str(payload.get("mode", "model")))
        return {}

    def _tube_command(
        self,
        command_name: str,
        payload: Payload,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        result = self.window.tube_script_service.execute_command(
            command_name,
            *args,
            command_origin="http",
            command_id=payload.get("command_id"),
            expected_revision=payload.get("expected_revision"),
            **kwargs,
        )
        return {
            "command": command_result_json(result),
            "tube": self.window.tube_page.state_json(),
        }

    def _planar_state(self, _payload: Payload) -> Response:
        return {"planar": self.window.planar_page.state_json()}

    def _planar_issues(self, _payload: Payload) -> Response:
        return self._planar_command("issues")

    def _planar_validate(self, _payload: Payload) -> Response:
        return self._planar_command("validate")

    def _planar_operation_create(self, payload: Payload) -> Response:
        allowed = ("operation_type", "operation_id", "name")
        return self._planar_command(
            "create_operation",
            **{key: payload[key] for key in allowed if key in payload},
        )

    def _planar_operation_set(self, payload: Payload) -> Response:
        allowed = (
            "operation_id",
            "name",
            "enabled",
            "body_id",
            "first_layer_z_mm",
            "layer_height_mm",
            "last_layer_z_mm",
            "bead_width_mm",
            "feedrate_mm_min",
            "line_spacing_mm",
            "travel_feedrate_mm_min",
            "retract_length_mm",
            "offset_pass_count",
            "wall_thickness_mm",
            "thin_wall_max_passes",
            "spiral_samples_per_contour",
            "support_overhang_angle_deg",
            "support_xy_gap_mm",
            "support_z_gap_mm",
            "support_line_spacing_mm",
            "support_interface_layers",
            "support_interface_spacing_mm",
            "support_pattern",
        )
        return self._planar_command(
            "set_operation", **{key: payload[key] for key in allowed if key in payload}
        )

    def _planar_operation_generate(self, payload: Payload) -> Response:
        return self._planar_command("generate_operation", operation_id=payload.get("operation_id"))

    def _planar_operation_export(self, payload: Payload) -> Response:
        destination = payload.get("destination")
        if not isinstance(destination, str) or not destination.strip():
            raise ValueError("destination is required")
        return self._planar_command(
            "export_operation",
            operation_id=payload.get("operation_id"),
            destination=destination,
        )

    def _planar_generation_cancel(self, _payload: Payload) -> Response:
        return self._planar_command("cancel_generation")

    def _planar_undo(self, _payload: Payload) -> Response:
        return self._planar_command("undo")

    def _planar_redo(self, _payload: Payload) -> Response:
        return self._planar_command("redo")

    def _planar_command(self, command_name: str, **kwargs: Any) -> Response:
        result = self.window.planar_command_service.execute_command(
            command_name, origin="http", **kwargs
        )
        return {
            "command": command_result_json(result),
            "planar": self.window.planar_page.state_json(),
        }

    def _curve_state(self, _payload: Payload) -> Response:
        return {"curve": self.window.curve_page.state_json()}

    def _curve_issues(self, _payload: Payload) -> Response:
        return self._curve_command("issues")

    def _curve_validate(self, _payload: Payload) -> Response:
        return self._curve_command("validate")

    def _curve_operation_create(self, payload: Payload) -> Response:
        allowed = ("operation_type", "operation_id", "name")
        return self._curve_command(
            "create_operation", **{key: payload[key] for key in allowed if key in payload}
        )

    def _curve_operation_set(self, payload: Payload) -> Response:
        allowed = (
            "operation_id", "name", "enabled", "edge_ids", "reversed_flags",
            "normal_mode", "normal_face_id", "specified_normal", "sampling_step_mm",
            "chord_error_mm", "chain_tolerance_mm", "bead_width_mm", "layer_height_mm",
            "feedrate_mm_min", "travel_feedrate_mm_min", "retract_length_mm", "dwell_s",
            "layer_count", "offset_pass_count", "offset_spacing_mm",
        )
        return self._curve_command(
            "set_operation", **{key: payload[key] for key in allowed if key in payload}
        )

    def _curve_operation_generate(self, payload: Payload) -> Response:
        return self._curve_command("generate_operation", operation_id=payload.get("operation_id"))

    def _curve_operation_export(self, payload: Payload) -> Response:
        destination = payload.get("destination")
        if not isinstance(destination, str) or not destination.strip():
            raise ValueError("destination is required")
        return self._curve_command(
            "export_operation",
            operation_id=payload.get("operation_id"),
            destination=destination,
        )

    def _curve_generation_cancel(self, _payload: Payload) -> Response:
        return self._curve_command("cancel_generation")

    def _curve_undo(self, _payload: Payload) -> Response:
        return self._curve_command("undo")

    def _curve_redo(self, _payload: Payload) -> Response:
        return self._curve_command("redo")

    def _curve_command(self, command_name: str, **kwargs: Any) -> Response:
        result = self.window.curve_command_service.execute_command(
            command_name, origin="http", **kwargs
        )
        return {
            "command": command_result_json(result),
            "curve": self.window.curve_page.state_json(),
        }


def automation_vector(
    payload: Payload,
    key: str,
    default: tuple[float, float, float],
) -> tuple[float, float, float]:
    raw = payload.get(key, default)
    if not isinstance(raw, list | tuple) or len(raw) != 3:
        raise ValueError(f"{key} must contain three numbers")
    values = tuple(float(value) for value in raw)
    if any(not math.isfinite(value) for value in values):
        raise ValueError(f"{key} values must be finite")
    return values  # type: ignore[return-value]


__all__ = ["AutomationRouter", "automation_vector"]
