"""Shared GUI, restricted-script, and HTTP command entry for Planar."""

from __future__ import annotations

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
from .planar_controller import PlanarController
from .manufacturing.planar_parameters import PlanarProcessParameters
from .postprocessing.indexed_tube import GenerationCancelled
from .restricted_script import ScriptCall, ScriptParseError, parse_script

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
_PARAMETER_FIELDS = frozenset(PlanarProcessParameters.__dataclass_fields__)


class PlanarCommandProvider:
    def canonical_name(self, name: str) -> str:
        canonical = str(name).strip()
        if canonical.startswith("planar."):
            canonical = canonical[len("planar.") :]
        if canonical not in _COMMANDS:
            raise ValueError(f"unknown Planar command: {name!r}")
        return canonical

    def kind(self, name: str) -> CommandKind:
        if name in _QUERIES:
            return "query"
        if name in _MUTATIONS:
            return "mutation"
        return cast(CommandKind, _HISTORY[name])

    def allows_drafts(self, name: str) -> bool:
        return name in {"state", "issues", "validate", "help", "cancel_generation"}

    def invoke(
        self, controller: CommandController, invocation: CommandInvocation
    ) -> CommandOutcome:
        if not isinstance(controller, PlanarController):
            raise TypeError("Planar commands require PlanarController")
        handler = getattr(self, f"_command_{invocation.name}", None)
        if handler is None:
            raise CommandError("E_COMMAND_UNKNOWN", f"unknown Planar command: {invocation.name}")
        return cast(CommandOutcome, handler(controller, *invocation.args, **invocation.kwargs))

    @staticmethod
    def _command_help(controller: PlanarController, topic: str | None = None) -> CommandOutcome:
        del controller
        commands = tuple(sorted(_COMMANDS))
        return CommandOutcome(
            {"commands": commands} if topic is None else {"command": topic},
            record_history=False,
        )

    @staticmethod
    def _command_state(controller: PlanarController) -> CommandOutcome:
        return CommandOutcome(controller.state_json(), record_history=False)

    @staticmethod
    def _command_issues(controller: PlanarController) -> CommandOutcome:
        return CommandOutcome(
            tuple(item.to_json() for item in controller.validation_report().issues),
            record_history=False,
        )

    @staticmethod
    def _command_validate(controller: PlanarController) -> CommandOutcome:
        return CommandOutcome(controller.validation_report().to_json(), record_history=False)

    @staticmethod
    def _command_create_operation(
        controller: PlanarController,
        operation_type: str = "planar_region",
        operation_id: str | None = None,
        name: str | None = None,
    ) -> CommandOutcome:
        options: dict[str, Any] = {
            "operation_type": operation_type,
            "operation_id": operation_id,
        }
        if name is not None:
            options["name"] = name
        result = controller.create_operation(**options)
        return CommandOutcome(result.to_json(), ("operation",), ("operations",))

    @staticmethod
    def _command_set_operation(
        controller: PlanarController,
        operation_id: str | None = None,
        name: str | None = None,
        enabled: bool | None = None,
        body_id: str | None = None,
        **parameter_changes: Any,
    ) -> CommandOutcome:
        unknown = sorted(set(parameter_changes) - _PARAMETER_FIELDS)
        if unknown:
            raise TypeError(f"unknown Planar parameter: {', '.join(unknown)}")
        parameter_changes = {
            key: value for key, value in parameter_changes.items() if value is not None
        }
        current = controller.operation(operation_id)
        if name is not None or enabled is not None:
            current = controller.set_operation_metadata(
                current.operation_id, name=name, enabled=enabled
            )
        parameters = (
            current.parameters
            if not parameter_changes
            else replace(current.parameters, **parameter_changes)
        )
        selected_body = _selected_body_id(body_id, current)
        if selected_body is None:
            if parameter_changes:
                raise ValueError("body_id is required before setting Planar parameters")
            updated = current
        else:
            updated = controller.configure_operation(
                operation_id=current.operation_id,
                body_id=selected_body,
                parameters=parameters,
            )
        return CommandOutcome(updated.to_json(), ("operation",), ("operations", "products"))

    @staticmethod
    def _command_generate_operation(
        controller: PlanarController, operation_id: str | None = None
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
    def _command_cancel_generation(controller: PlanarController) -> CommandOutcome:
        controller.cancel_generation()
        return CommandOutcome(
            {"cancel_requested": True},
            ("operation",),
            project_only=True,
            record_history=False,
        )

    @staticmethod
    def _command_export_operation(
        controller: PlanarController,
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


class PlanarCommandService:
    """Small non-Qt facade shared by the Planar page and automation routes."""

    def __init__(self, controller: PlanarController) -> None:
        self.kernel = CommandKernel(cast(CommandController, controller), PlanarCommandProvider())

    @property
    def controller(self) -> PlanarController:
        return cast(PlanarController, self.kernel.controller)

    def execute_command(
        self, command_name: str, *args: Any, origin: str = "api", **kwargs: Any
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


def _script_invocation(call: ScriptCall) -> CommandInvocation:
    return CommandInvocation(call.name, call.args, call.kwargs, origin="script")


def _selected_body_id(body_id: str | None, operation: Any) -> str | None:
    if body_id is not None:
        return body_id
    return None if operation.geometry.body is None else operation.geometry.body.object_id


__all__ = ["PlanarCommandProvider", "PlanarCommandService"]
