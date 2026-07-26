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

Payload = dict[str, Any]
Response = dict[str, Any]
Route = Callable[[Payload], Response]


class AutomationRouter:
    """Dispatch the public HTTP contract against one live application window."""

    def __init__(self, window: Any) -> None:
        # MainWindow is intentionally duck-typed here to avoid a UI/router
        # import cycle.  Endpoint tests exercise this narrow adapter boundary.
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
            "/tube/part/confirm": self._tube_part_confirm,
            "/tube/resource/select": self._tube_resource_select,
            "/tube/coordinate/apply": self._tube_coordinate_apply,
            "/tube/placement/apply": self._tube_placement_apply,
            "/tube/draft/discard": self._tube_draft_discard,
            "/tube/view": self._tube_view,
        }

    def dispatch(self, path: str, payload: Payload) -> Response:
        handler = self._routes.get(path)
        if handler is not None:
            return handler(payload)
        tube_handler = self._tube_routes.get(path)
        if tube_handler is not None:
            result = tube_handler(payload)
            self.window.tube_page.refresh()
            return result or {"tube": self.window.tube_page.state_json()}
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
        return {"preview": self.window.viewer.preview_state()}

    def _preview_perf(self, _payload: Payload) -> Response:
        return {"preview_perf": self.window.viewer.performance_state()}

    def _preview_layers(self, payload: Payload) -> Response:
        self.window.viewer.set_preview_layers(
            int(payload["layer_min"]),
            int(payload["layer_max"]),
        )
        self.window._sync_preview_controls()
        return {"preview": self.window.viewer.preview_state()}

    def _preview_progress(self, payload: Payload) -> Response:
        index = int(payload.get("progress_index", payload.get("index", 0)))
        interactive = bool(payload.get("interactive", False))
        self.window.viewer.set_preview_progress(index, interactive=interactive)
        self.window._sync_progress_controls()
        self.window._update_preview_summary()
        if not interactive:
            QTimer.singleShot(250, self.window._update_preview_summary)
        return {"preview": self.window.viewer.preview_state()}

    def _preview_visibility(self, payload: Payload) -> Response:
        self.window.viewer.set_preview_visibility(
            show_travel=payload.get("show_travel"),
            show_extrusion=payload.get("show_extrusion"),
            visible_roles=payload.get("visible_roles"),
            show_pose_samples=payload.get("show_pose_samples"),
        )
        self.window._sync_legend_from_settings()
        self.window._update_preview_summary()
        return {"preview": self.window.viewer.preview_state()}

    def _active_selection_viewer(self) -> Any:
        if self.window.current_workbench_key == "tube":
            return self.window.tube_page.viewer
        return self.window.viewer

    def _refresh_selection(self) -> None:
        if self.window.current_workbench_key == "tube":
            self.window.tube_page.refresh()
        else:
            self.window.refresh_lists()

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
        self.window.viewer.camera_command(
            str(payload.get("command", "fit")),
            float(payload.get("value", 10.0)),
        )
        return self.window.current_state()

    def _tube_state(self, _payload: Payload) -> Response:
        return {"tube": self.window.tube_page.state_json()}

    def _tube_source_update(self, payload: Payload) -> Response:
        return self.window.update_model_from_original_source(
            path=payload.get("path"),
            length_unit_override=payload.get("length_unit_override"),
            draft_resolution=payload.get("draft_resolution"),
            show_dialog=False,
        )

    def _tube_operation_create(self, payload: Payload) -> Response:
        self.window.tube_page.controller.create_operation(operation_id=payload.get("operation_id"))
        return {}

    def _tube_part_confirm(self, payload: Payload) -> Response:
        self.window.tube_page.controller.confirm_assignments(
            payload.get("part_body_ids", ()),
            ignored_body_ids=payload.get("ignored_body_ids", ()),
            unassigned_body_ids=payload.get("unassigned_body_ids"),
        )
        return {}

    def _tube_resource_select(self, payload: Payload) -> Response:
        kind = str(payload["kind"]).strip().lower()
        identifier = str(payload["identifier"])
        options = {
            key: value for key, value in payload.items() if key not in {"kind", "identifier"}
        }
        self.window.tube_page.select_builtin_resource(kind, identifier, **options)
        return {}

    def _tube_coordinate_apply(self, payload: Payload) -> Response:
        self.window.tube_page.apply_numeric_coordinate(
            str(payload["node"]),
            automation_vector(payload, "origin", (0.0, 0.0, 0.0)),
            automation_vector(payload, "z_direction", (0.0, 0.0, 1.0)),
            automation_vector(payload, "x_direction", (1.0, 0.0, 0.0)),
            flip_z=bool(payload.get("flip_z", False)),
            flip_x=bool(payload.get("flip_x", False)),
        )
        return {}

    def _tube_placement_apply(self, payload: Payload) -> Response:
        self.window.tube_page.apply_placement(
            str(payload["mount_datum_id"]),
            automation_vector(payload, "translation_mm", (0.0, 0.0, 0.0)),
            automation_vector(payload, "rotation_xyz_deg", (0.0, 0.0, 0.0)),
        )
        return {}

    def _tube_draft_discard(self, _payload: Payload) -> Response:
        self.window.tube_page.controller.discard_all_drafts()
        return {}

    def _tube_view(self, payload: Payload) -> Response:
        self.window.tube_page.set_view_mode(str(payload.get("mode", "model")))
        return {}


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
