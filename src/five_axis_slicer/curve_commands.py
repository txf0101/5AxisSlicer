"""Shared GUI, restricted-script and HTTP command entry for Curve."""

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
from .curve_controller import CurveController
from .manufacturing.curve_parameters import CurveProcessParameters
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
_PARAMETERS = frozenset(CurveProcessParameters.__dataclass_fields__)


class CurveCommandProvider:
    def canonical_name(self, name: str) -> str:
        canonical = str(name).strip()
        if canonical.startswith("curve."):
            canonical = canonical[len("curve.") :]
        if canonical not in _COMMANDS:
            raise ValueError(f"unknown Curve command: {name!r}")
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
        self, controller: CommandController, invocation: CommandInvocation
    ) -> CommandOutcome:
        if not isinstance(controller, CurveController):
            raise TypeError("Curve commands require CurveController")
        handler = getattr(self, f"_command_{invocation.name}", None)
        if handler is None:
            raise CommandError("E_COMMAND_UNKNOWN", invocation.name)
        return cast(CommandOutcome, handler(controller, *invocation.args, **invocation.kwargs))

    @staticmethod
    def _command_help(controller: CurveController, topic: str | None = None) -> CommandOutcome:
        del controller
        return CommandOutcome(
            {"commands": tuple(sorted(_COMMANDS))} if topic is None else {"command": topic},
            record_history=False,
        )

    @staticmethod
    def _command_state(controller: CurveController) -> CommandOutcome:
        return CommandOutcome(controller.state_json(), record_history=False)

    @staticmethod
    def _command_issues(controller: CurveController) -> CommandOutcome:
        return CommandOutcome(
            tuple(item.to_json() for item in controller.validation_report().issues),
            record_history=False,
        )

    @staticmethod
    def _command_validate(controller: CurveController) -> CommandOutcome:
        return CommandOutcome(controller.validation_report().to_json(), record_history=False)

    @staticmethod
    def _command_create_operation(
        controller: CurveController,
        operation_type: str = "curve_buildup",
        operation_id: str | None = None,
        name: str | None = None,
    ) -> CommandOutcome:
        operation = controller.create_operation(
            operation_type, operation_id=operation_id, name=name
        )
        return CommandOutcome(operation.to_json(), ("operation",), ("operations",))

    @staticmethod
    def _command_set_operation(
        controller: CurveController,
        operation_id: str | None = None,
        name: str | None = None,
        enabled: bool | None = None,
        edge_ids: tuple[str, ...] | list[str] | None = None,
        reversed_flags: tuple[bool, ...] | list[bool] | None = None,
        normal_mode: str | None = None,
        normal_face_id: str | None = None,
        specified_normal: tuple[float, float, float] | list[float] | None = None,
        **parameter_changes: Any,
    ) -> CommandOutcome:
        unknown = sorted(set(parameter_changes) - _PARAMETERS)
        if unknown:
            raise TypeError(f"unknown Curve parameter: {', '.join(unknown)}")
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
        selected_edges = (
            tuple(item.edge.object_id for item in current.geometry.edges)
            if edge_ids is None
            else tuple(str(item) for item in edge_ids)
        )
        selected_flags = (
            tuple(item.reversed for item in current.geometry.edges)
            if reversed_flags is None
            else tuple(bool(item) for item in reversed_flags)
        )
        mode = normal_mode or current.geometry.normal_mode
        face_id = normal_face_id
        if normal_face_id is None and current.geometry.normal_face is not None:
            face_id = current.geometry.normal_face.object_id
        normal = (
            current.geometry.specified_normal
            if specified_normal is None
            else tuple(float(item) for item in specified_normal)
        )
        if not selected_edges:
            if parameter_changes:
                raise ValueError("edge_ids are required before setting Curve parameters")
            updated = current
        else:
            updated = controller.configure_operation(
                operation_id=current.operation_id,
                edge_ids=selected_edges,
                reversed_flags=selected_flags,
                normal_mode=mode,
                normal_face_id=face_id,
                specified_normal=normal,
                parameters=parameters,
            )
        return CommandOutcome(updated.to_json(), ("operation",), ("operations", "products"))

    @staticmethod
    def _command_generate_operation(
        controller: CurveController, operation_id: str | None = None
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
        return CommandOutcome(
            {"status": result.manifest.status.value, "result": result.to_json()},
            ("operation",),
            ("products",),
            project_only=True,
            record_history=False,
        )

    @staticmethod
    def _command_cancel_generation(controller: CurveController) -> CommandOutcome:
        controller.cancel_generation()
        return CommandOutcome(
            {"cancel_requested": True},
            ("operation",),
            project_only=True,
            record_history=False,
        )

    @staticmethod
    def _command_export_operation(
        controller: CurveController,
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


class CurveCommandService:
    def __init__(self, controller: CurveController) -> None:
        self.kernel = CommandKernel(cast(CommandController, controller), CurveCommandProvider())

    @property
    def controller(self) -> CurveController:
        return cast(CurveController, self.kernel.controller)

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
    if call.namespace != "curve":
        raise ScriptParseError(
            "E_SCRIPT_FORBIDDEN",
            "Curve command service accepts only curve/曲线 commands",
            call.line,
            call.column,
        )
    return CommandInvocation(call.name, call.args, call.kwargs, origin="script")


__all__ = ["CurveCommandProvider", "CurveCommandService"]
