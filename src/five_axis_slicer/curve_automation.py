"""HTTP adapters for the Curve command service."""

from __future__ import annotations

from typing import Any, Callable

from .tube_script_service import command_result_json

Payload = dict[str, Any]
Response = dict[str, Any]
Route = Callable[[Payload], Response]


class CurveAutomationRoutes:
    def __init__(self, window: Any) -> None:
        self.window = window
        self.routes: dict[str, Route] = {
            "/curve/state": self.state,
            "/curve/issues": self.issues,
            "/curve/validate": self.validate,
            "/curve/operation/create": self.operation_create,
            "/curve/operation/set": self.operation_set,
            "/curve/operation/generate": self.operation_generate,
            "/curve/operation/export": self.operation_export,
            "/curve/generation/cancel": self.generation_cancel,
            "/curve/undo": self.undo,
            "/curve/redo": self.redo,
        }

    def state(self, _payload: Payload) -> Response:
        return {"curve": self.window.curve_page.state_json()}

    def issues(self, _payload: Payload) -> Response:
        return self._command("issues")

    def validate(self, _payload: Payload) -> Response:
        return self._command("validate")

    def operation_create(self, payload: Payload) -> Response:
        allowed = ("operation_type", "operation_id", "name")
        return self._command(
            "create_operation", **{key: payload[key] for key in allowed if key in payload}
        )

    def operation_set(self, payload: Payload) -> Response:
        allowed = (
            "operation_id",
            "name",
            "enabled",
            "edge_ids",
            "reversed_flags",
            "normal_mode",
            "normal_face_id",
            "specified_normal",
            "sampling_step_mm",
            "chord_error_mm",
            "chain_tolerance_mm",
            "bead_width_mm",
            "layer_height_mm",
            "feedrate_mm_min",
            "travel_feedrate_mm_min",
            "retract_length_mm",
            "dwell_s",
            "layer_count",
            "offset_pass_count",
            "offset_spacing_mm",
        )
        return self._command(
            "set_operation", **{key: payload[key] for key in allowed if key in payload}
        )

    def operation_generate(self, payload: Payload) -> Response:
        return self._command("generate_operation", operation_id=payload.get("operation_id"))

    def operation_export(self, payload: Payload) -> Response:
        destination = payload.get("destination")
        if not isinstance(destination, str) or not destination.strip():
            raise ValueError("destination is required")
        return self._command(
            "export_operation",
            operation_id=payload.get("operation_id"),
            destination=destination,
        )

    def generation_cancel(self, _payload: Payload) -> Response:
        return self._command("cancel_generation")

    def undo(self, _payload: Payload) -> Response:
        return self._command("undo")

    def redo(self, _payload: Payload) -> Response:
        return self._command("redo")

    def _command(self, command_name: str, **kwargs: Any) -> Response:
        result = self.window.curve_command_service.execute_command(
            command_name, origin="http", **kwargs
        )
        return {
            "command": command_result_json(result),
            "curve": self.window.curve_page.state_json(),
        }


__all__ = ["CurveAutomationRoutes"]
