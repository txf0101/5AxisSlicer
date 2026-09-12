"""Shared GUI, restricted-script, and HTTP command entry for Rotary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import json
from typing import Any, cast

from .command_kernel import (
    CommandController,
    CommandError,
    CommandInvocation,
    CommandKernel,
    CommandKind,
    CommandOutcome,
    CommandResult,
)
from .manufacturing.rotary_parameters import (
    RotaryGeometrySelection,
    RotaryProcessParameters,
)
from .postprocessing.indexed_tube import GenerationCancelled
from .restricted_script import ScriptCall, ScriptParseError, parse_script
from .rotary_controller import RotaryController


_QUERIES = frozenset({"help", "state", "issues", "validate"})
_MUTATIONS = frozenset(
    {
        "create_operation",
        "set_operation",
        "generate_operation",
        "cancel_generation",
        "export_operation",
    }
)
_HISTORY = {"undo": "undo", "redo": "redo"}
_COMMANDS = _QUERIES | _MUTATIONS | _HISTORY.keys()
ROTARY_PARAMETER_FIELDS = frozenset(RotaryProcessParameters.__dataclass_fields__)


class RotaryCommandProvider:
    def canonical_name(self, name: str) -> str:
        canonical = str(name).strip()
        if canonical.startswith("rotary."):
            canonical = canonical[len("rotary.") :]
        if canonical not in _COMMANDS:
            raise ValueError(f"unknown Rotary command: {name!r}")
        return canonical

    def kind(self, name: str) -> CommandKind:
        if name in _QUERIES:
            return "query"
        if name in _MUTATIONS:
            return "mutation"
        return cast(CommandKind, _HISTORY[name])

    def allows_drafts(self, name: str) -> bool:
        return name in {"help", "state", "issues", "validate", "cancel_generation"}

    def invoke(
        self,
        controller: CommandController,
        invocation: CommandInvocation,
    ) -> CommandOutcome:
        if not isinstance(controller, RotaryController):
            raise TypeError("Rotary commands require RotaryController")
        handler = getattr(self, f"_command_{invocation.name}", None)
        if handler is None:
            raise CommandError("E_COMMAND_UNKNOWN", invocation.name)
        return cast(CommandOutcome, handler(controller, *invocation.args, **invocation.kwargs))

    @staticmethod
    def _command_help(controller: RotaryController, topic: str | None = None) -> CommandOutcome:
        del controller
        return CommandOutcome(
            {"commands": tuple(sorted(_COMMANDS))} if topic is None else {"command": topic},
            record_history=False,
        )

    @staticmethod
    def _command_state(controller: RotaryController) -> CommandOutcome:
        return CommandOutcome(controller.state_json(), record_history=False)

    @staticmethod
    def _command_issues(controller: RotaryController) -> CommandOutcome:
        issues = [item.to_json() for item in controller.validation_report().issues]
        for state in (controller.product_state(item.operation_id) for item in controller.operations):
            if state is None or not isinstance(state.result_payload, Mapping):
                continue
            issue = state.result_payload.get("issue")
            if isinstance(issue, Mapping):
                issues.append(dict(issue))
        return CommandOutcome(
            tuple(issues),
            record_history=False,
        )

    @staticmethod
    def _command_validate(controller: RotaryController) -> CommandOutcome:
        return CommandOutcome(controller.validation_report().to_json(), record_history=False)

    @staticmethod
    def _command_create_operation(
        controller: RotaryController,
        operation_type: str = "rotary_spiral",
        operation_id: str | None = None,
        name: str | None = None,
    ) -> CommandOutcome:
        operation = controller.create_operation(
            operation_type,
            operation_id=operation_id,
            name=name,
        )
        return CommandOutcome(operation.to_json(), ("operation",), ("operations",))

    @staticmethod
    def _command_set_operation(
        controller: RotaryController,
        operation_id: str | None = None,
        name: str | None = None,
        enabled: bool | None = None,
        geometry: RotaryGeometrySelection | Mapping[str, Any] | None = None,
        **parameter_changes: Any,
    ) -> CommandOutcome:
        unknown = sorted(set(parameter_changes) - ROTARY_PARAMETER_FIELDS)
        if unknown:
            raise TypeError(f"unknown Rotary parameter: {', '.join(unknown)}")
        current = controller.operation(operation_id)
        if name is not None or enabled is not None:
            current = controller.set_operation_metadata(
                current.operation_id,
                name=name,
                enabled=enabled,
            )
        selected_geometry = _geometry_value(geometry, current.geometry)
        changes = {key: value for key, value in parameter_changes.items() if value is not None}
        parameters = current.parameters if not changes else replace(current.parameters, **changes)
        updated = controller.configure_operation(
            operation_id=current.operation_id,
            geometry=selected_geometry,
            parameters=parameters,
        )
        return CommandOutcome(updated.to_json(), ("operation",), ("operations", "products"))

    @staticmethod
    def _command_generate_operation(
        controller: RotaryController,
        operation_id: str | None = None,
    ) -> CommandOutcome:
        try:
            result = controller.generate_operation(operation_id)
        except GenerationCancelled as exc:
            return CommandOutcome(
                {"status": "cancelled", "message": str(exc)},
                ("operation",),
                project_only=True,
                record_history=False,
            )
        status = result.manifest.status
        return CommandOutcome(
            {
                "status": status.value if hasattr(status, "value") else str(status),
                "result": result.to_json(),
            },
            ("operation",),
            ("products",),
            project_only=True,
            record_history=False,
        )

    @staticmethod
    def _command_cancel_generation(controller: RotaryController) -> CommandOutcome:
        controller.cancel_generation()
        return CommandOutcome(
            {"cancel_requested": True},
            ("operation",),
            project_only=True,
            record_history=False,
        )

    @staticmethod
    def _command_export_operation(
        controller: RotaryController,
        operation_id: str | None = None,
        destination: str = "",
    ) -> CommandOutcome:
        path = controller.export_operation_product(operation_id, destination)
        return CommandOutcome(
            {"destination": str(path)},
            ("operation",),
            project_only=True,
            record_history=False,
        )


class RotaryCommandService:
    def __init__(self, controller: RotaryController) -> None:
        self.kernel = CommandKernel(cast(CommandController, controller), RotaryCommandProvider())

    @property
    def controller(self) -> RotaryController:
        return cast(RotaryController, self.kernel.controller)

    def execute_command(
        self,
        command_name: str,
        *args: Any,
        origin: str = "api",
        **kwargs: Any,
    ) -> CommandResult:
        return self.kernel.execute(CommandInvocation(command_name, args, kwargs, origin=origin))

    def execute_script(self, source: str) -> str:
        try:
            outputs = []
            for group in parse_script(source):
                calls = tuple(_script_invocation(item) for item in group.calls)
                result = (
                    self.kernel.transaction(calls, origin="script")
                    if group.atomic
                    else self.kernel.execute(calls[0])
                )
                outputs.append(json.dumps(result.payload, ensure_ascii=False, sort_keys=True))
            return "\n".join(outputs)
        except (CommandError, ScriptParseError, TypeError, ValueError) as exc:
            return f"ERROR: {exc}"


def _geometry_value(
    value: RotaryGeometrySelection | Mapping[str, Any] | None,
    current: RotaryGeometrySelection,
) -> RotaryGeometrySelection:
    if value is None:
        return current
    if isinstance(value, RotaryGeometrySelection):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("geometry must be RotaryGeometrySelection or an object")
    return RotaryGeometrySelection.from_json(value)


def _script_invocation(call: ScriptCall) -> CommandInvocation:
    if call.namespace != "rotary":
        raise ScriptParseError(
            "E_SCRIPT_FORBIDDEN",
            "Rotary command service accepts only rotary/回转 commands",
            call.line,
            call.column,
        )
    return CommandInvocation(call.name, call.args, call.kwargs, origin="script")


__all__ = [
    "ROTARY_PARAMETER_FIELDS",
    "RotaryCommandProvider",
    "RotaryCommandService",
]
