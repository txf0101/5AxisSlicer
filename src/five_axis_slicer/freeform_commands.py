"""Shared GUI, restricted-script and HTTP command entry for Freeform."""

from __future__ import annotations

from dataclasses import replace
import json
from typing import Any, cast

from .command_kernel import CommandError, CommandInvocation, CommandKernel, CommandOutcome
from .freeform_controller import FreeformController
from .manufacturing.controller_profile import ToolChangeStation
from .manufacturing.freeform_parameters import FreeformProcessParameters
from .manufacturing.freeform_solid_parameters import (
    SOLID_FILL_OPERATION_TYPES,
    SolidFillProcessParameters,
)
from .manufacturing.material_plan import MaterialPlan
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
_PARAMETERS = frozenset(FreeformProcessParameters.__dataclass_fields__)
_SOLID_PARAMETERS = frozenset(SolidFillProcessParameters.__dataclass_fields__)
_UNSET = object()


class FreeformCommandProvider:
    def canonical_name(self, name):
        canonical = str(name).strip()
        if canonical.startswith("freeform."):
            canonical = canonical[9:]
        if canonical not in _COMMANDS:
            raise ValueError(f"unknown Freeform command: {name}")
        return canonical

    def kind(self, name):
        return (
            "query" if name in _QUERIES else ("mutation" if name in _MUTATIONS else _HISTORY[name])
        )

    def allows_drafts(self, name):
        return name in {"help", "state", "issues", "validate", "cancel_generation"}

    def invoke(self, controller, invocation):
        if not isinstance(controller, FreeformController):
            raise TypeError("Freeform commands require FreeformController")
        handler = getattr(self, f"_command_{invocation.name}", None)
        if handler is None:
            raise CommandError("E_COMMAND_UNKNOWN", invocation.name)
        return handler(controller, *invocation.args, **invocation.kwargs)

    @staticmethod
    def _command_help(controller, topic=None):
        del controller
        return CommandOutcome(
            {"commands": tuple(sorted(_COMMANDS))} if topic is None else {"command": topic},
            record_history=False,
        )

    @staticmethod
    def _command_state(controller):
        return CommandOutcome(controller.state_json(), record_history=False)

    @staticmethod
    def _command_issues(controller):
        return CommandOutcome(
            tuple(item.to_json() for item in controller.validation_report().issues),
            record_history=False,
        )

    @staticmethod
    def _command_validate(controller):
        return CommandOutcome(controller.validation_report().to_json(), record_history=False)

    @staticmethod
    def _command_create_operation(
        controller, operation_type="freeform_surface", operation_id=None, name=None
    ):
        operation = controller.create_operation(
            operation_type, operation_id=operation_id, name=name
        )
        return CommandOutcome(operation.to_json(), ("operation",), ("operations",))

    @staticmethod
    def _command_set_operation(
        controller,
        operation_id=None,
        name=None,
        enabled=None,
        face_ids=None,
        guides=None,
        solid_geometry=None,
        material_plan=None,
        tool_change_station=_UNSET,
        **parameter_changes,
    ):
        if tool_change_station is not _UNSET:
            if tool_change_station is not None and not isinstance(tool_change_station, dict):
                raise ValueError("tool_change_station must be an object or null")
            controller.configure_tool_change_station(
                None if tool_change_station is None
                else ToolChangeStation.from_json(tool_change_station)
            )
        current = controller.operation(operation_id)
        allowed = _SOLID_PARAMETERS if current.operation_type in SOLID_FILL_OPERATION_TYPES else _PARAMETERS
        unknown = sorted(set(parameter_changes) - allowed)
        if unknown:
            raise TypeError(f"unknown Freeform parameter: {', '.join(unknown)}")
        if name is not None or enabled is not None:
            current = controller.set_operation_metadata(
                current.operation_id, name=name, enabled=enabled
            )
        if current.operation_type in SOLID_FILL_OPERATION_TYPES:
            parameters = _updated_solid_parameters(current, parameter_changes)
            geometry = _selected_solid_geometry(current, solid_geometry)
            plan = _material_plan(current, material_plan)
            if geometry is None:
                if parameter_changes or material_plan is not None:
                    raise ValueError("solid_geometry is required before solid-fill parameters")
                return CommandOutcome(current.to_json(), ("operation",), ("operations", "products"))
            updated = controller.configure_solid_operation(
                operation_id=current.operation_id,
                solid_geometry=geometry,
                parameters=parameters,
                material_plan=plan,
            )
            return CommandOutcome(updated.to_json(), ("operation",), ("operations", "products"))
        parameters = _updated_parameters(current, parameter_changes)
        selected_faces = _selected_faces(current, face_ids)
        selected_guides = _selected_guides(current, guides)
        plan = _material_plan(current, material_plan)
        if not selected_faces or not selected_guides:
            if parameter_changes or material_plan is not None:
                raise ValueError("face_ids and guides are required before Freeform parameters")
            return CommandOutcome(current.to_json(), ("operation",), ("operations", "products"))
        updated = controller.configure_operation(
            operation_id=current.operation_id,
            face_ids=selected_faces,
            guides=selected_guides,
            parameters=parameters,
            material_plan=plan,
        )
        return CommandOutcome(updated.to_json(), ("operation",), ("operations", "products"))

    @staticmethod
    def _command_generate_operation(controller, operation_id=None):
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
    def _command_cancel_generation(controller):
        controller.cancel_generation()
        return CommandOutcome(
            {"cancel_requested": True}, ("operation",), project_only=True, record_history=False
        )

    @staticmethod
    def _command_export_operation(controller, operation_id=None, destination=""):
        path = controller.export_operation_product(operation_id, destination)
        return CommandOutcome(
            {"destination": str(path)}, ("operation",), project_only=True, record_history=False
        )


class FreeformCommandService:
    def __init__(self, controller):
        self.kernel = CommandKernel(cast(Any, controller), FreeformCommandProvider())

    @property
    def controller(self):
        return cast(FreeformController, self.kernel.controller)

    def execute_command(self, command_name, *args, origin="api", **kwargs):
        return self.kernel.execute(CommandInvocation(command_name, args, kwargs, origin=origin))

    def execute_script(self, source):
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


def _script_invocation(call: ScriptCall):
    if call.namespace != "freeform":
        raise ScriptParseError(
            "E_SCRIPT_FORBIDDEN",
            "Freeform service accepts only freeform/自由曲面 commands",
            call.line,
            call.column,
        )
    return CommandInvocation(call.name, call.args, call.kwargs, origin="script")


def _updated_parameters(current, changes):
    values = {key: value for key, value in changes.items() if value is not None}
    return current.parameters if not values else replace(current.parameters, **values)


def _updated_solid_parameters(current, changes):
    values = {key: value for key, value in changes.items() if value is not None}
    return (
        current.solid_parameters
        if not values
        else replace(current.solid_parameters, **values)
    )


def _selected_solid_geometry(current, payload):
    if payload is not None:
        if not isinstance(payload, dict):
            raise ValueError("solid_geometry must be an object")
        return dict(payload)
    selection = current.solid_geometry
    if selection is None:
        return None
    data = selection.to_json()
    operation_type = data.pop("operation_type")
    substrate = data.pop("substrate_body", None)
    if substrate is not None:
        data["substrate_body_id"] = substrate["object_id"]
    if operation_type == "spherical_solid_fill":
        data["body_ids"] = [item["object_id"] for item in data.pop("bodies")]
    elif operation_type == "surface_solid_fill":
        data["bodies"] = [
            {
                "body_id": item["body"]["object_id"],
                "surface_face_id": item["surface_face"]["object_id"],
                "opposite_face_id": item["opposite_face"]["object_id"],
                "root_edge_id": item["root_edge"]["object_id"],
            }
            for item in data["bodies"]
        ]
    else:
        data["hub_body_id"] = data.pop("hub_body")["object_id"]
        data["blades"] = [
            {
                "body_id": item["body"]["object_id"],
                "root_face_id": item["root_face"]["object_id"],
                "outer_face_id": item["outer_face"]["object_id"],
            }
            for item in data["blades"]
        ]
    return data


def _selected_faces(current, face_ids):
    if face_ids is not None:
        return tuple(str(item) for item in face_ids)
    return tuple(item.object_id for item in current.geometry.faces)


def _selected_guides(current, guides):
    if guides is not None:
        return tuple(dict(item) for item in guides)
    return tuple(
        {
            "edge_ids": tuple(item.edge.object_id for item in guide.edges),
            "reversed_flags": tuple(item.reversed for item in guide.edges),
            "face_id": guide.normal_face.object_id,
        }
        for guide in current.geometry.guides
    )


def _material_plan(current, payload):
    if payload is None:
        return current.material_plan
    return payload if isinstance(payload, MaterialPlan) else MaterialPlan.from_json(payload)


__all__ = ["FreeformCommandProvider", "FreeformCommandService"]
