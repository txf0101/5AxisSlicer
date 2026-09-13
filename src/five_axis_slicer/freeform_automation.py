"""HTTP adapters for the restricted Freeform command service."""

from __future__ import annotations

from typing import Any

from .tube_script_service import command_result_json


class FreeformAutomationRoutes:
    def __init__(self, window: Any) -> None:
        self.window = window
        self.routes = {
            "/freeform/state": self.state,
            "/freeform/issues": self.issues,
            "/freeform/validate": self.validate,
            "/freeform/operation/create": self.operation_create,
            "/freeform/operation/set": self.operation_set,
            "/freeform/operation/generate": self.operation_generate,
            "/freeform/operation/export": self.operation_export,
            "/freeform/generation/cancel": self.generation_cancel,
            "/freeform/undo": self.undo,
            "/freeform/redo": self.redo,
        }

    def state(self, _payload):
        return {"freeform": self.window.freeform_page.state_json()}

    def issues(self, _payload):
        return self._command("issues")

    def validate(self, _payload):
        return self._command("validate")

    def operation_create(self, payload):
        return self._command(
            "create_operation",
            **{
                key: payload[key]
                for key in ("operation_type", "operation_id", "name")
                if key in payload
            },
        )

    def operation_set(self, payload):
        return self._command("set_operation", **payload)

    def operation_generate(self, payload):
        return self._command("generate_operation", operation_id=payload.get("operation_id"))

    def generation_cancel(self, _payload):
        return self._command("cancel_generation")

    def undo(self, _payload):
        return self._command("undo")

    def redo(self, _payload):
        return self._command("redo")

    def operation_export(self, payload):
        destination = payload.get("destination")
        if not isinstance(destination, str) or not destination.strip():
            raise ValueError("destination is required")
        return self._command(
            "export_operation", operation_id=payload.get("operation_id"), destination=destination
        )

    def _command(self, command_name, **kwargs):
        result = self.window.freeform_command_service.execute_command(
            command_name, origin="http", **kwargs
        )
        return {
            "command": command_result_json(result),
            "freeform": self.window.freeform_page.state_json(),
        }


__all__ = ["FreeformAutomationRoutes"]
