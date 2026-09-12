"""HTTP adapters for the Rotary command service."""

from __future__ import annotations

from typing import Any, Callable

from .rotary_commands import ROTARY_PARAMETER_FIELDS
from .tube_script_service import command_result_json


Payload = dict[str, Any]
Response = dict[str, Any]
Route = Callable[[Payload], Response]


class RotaryAutomationRoutes:
    def __init__(self, window: Any) -> None:
        self.window = window
        self.routes: dict[str, Route] = {
            "/rotary/state": self.state,
            "/rotary/issues": self.issues,
            "/rotary/validate": self.validate,
            "/rotary/operation/create": self.operation_create,
            "/rotary/operation/set": self.operation_set,
            "/rotary/operation/generate": self.operation_generate,
            "/rotary/operation/export": self.operation_export,
            "/rotary/generation/cancel": self.generation_cancel,
            "/rotary/undo": self.undo,
            "/rotary/redo": self.redo,
        }

    def state(self, _payload: Payload) -> Response:
        return {"rotary": self.window.rotary_page.state_json()}

    def issues(self, _payload: Payload) -> Response:
        return self._command("issues")

    def validate(self, _payload: Payload) -> Response:
        return self._command("validate")

    def operation_create(self, payload: Payload) -> Response:
        allowed = ("operation_type", "operation_id", "name")
        return self._command(
            "create_operation",
            **{key: payload[key] for key in allowed if key in payload},
        )

    def operation_set(self, payload: Payload) -> Response:
        allowed = {
            "operation_id",
            "name",
            "enabled",
            "geometry",
            *ROTARY_PARAMETER_FIELDS,
        }
        return self._command(
            "set_operation",
            **{key: payload[key] for key in allowed if key in payload},
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
        result = self.window.rotary_command_service.execute_command(
            command_name,
            origin="http",
            **kwargs,
        )
        return {
            "command": command_result_json(result),
            "rotary": self.window.rotary_page.state_json(),
        }


__all__ = ["RotaryAutomationRoutes"]
