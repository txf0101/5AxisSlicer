"""Tube Setup commands registered with the shared command kernel.

The provider contains domain adapters only.  It never writes the user resource
library; nozzle and material overrides become project-owned frozen snapshots.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

from .command_kernel import (
    CommandController,
    CommandError,
    CommandInvocation,
    CommandKind,
    CommandOutcome,
)
from .manufacturing.coordinates import LocalAdjustment
from .manufacturing.library import ResourceLibraryError
from .manufacturing.resources import (
    MaterialProfile,
    NozzleProfile,
    canonical_content_hash,
)
from .manufacturing.setup import (
    BUILD_CS_NODE,
    MODEL_CS_NODE,
    PLACEMENT_NODE,
    TubeOperationDefinition,
)
from .manufacturing.tube_parameters import (
    TubeBuildupOperationConfig,
    TubeContinuousOperationConfig,
)
from .postprocessing.indexed_tube import GenerationCancelled
from .setup_config import SetupConfig
from .setup_config_session import apply_setup_config
from .tube_controller import TubeSetupController
from .tube_drafts import OperationLimitError, TubeControllerError
from .tube_resource_selection import configured_nozzle_copy, nozzle_editor_profile

_QUERY_COMMANDS = frozenset({"help", "state", "issues", "validate"})
_MUTATION_COMMANDS = frozenset(
    {
        "create_operation",
        "set_operation",
        "generate_operation",
        "cancel_generation",
        "export_operation",
        "confirm_part",
        "set_machine",
        "set_nozzle",
        "set_material",
        "set_model_cs",
        "set_build_cs",
        "set_placement",
        "apply_coordinate_draft",
        "apply_placement_draft",
        "apply_all_drafts",
        "apply_setup_config",
        "set_complete_nozzle",
        "discard_all_drafts",
    }
)
_HISTORY_COMMANDS = {"undo": "undo", "redo": "redo"}
_INTERNAL_COMMANDS = frozenset(
    {
        "apply_coordinate_draft",
        "apply_placement_draft",
        "apply_all_drafts",
        "apply_setup_config",
        "set_complete_nozzle",
        "discard_all_drafts",
    }
)
_DRAFT_COMMANDS = frozenset(
    {"apply_coordinate_draft", "apply_placement_draft", "apply_all_drafts", "discard_all_drafts"}
)
_NODE_FIELDS = {
    MODEL_CS_NODE: "setup.coordinate_systems.model",
    BUILD_CS_NODE: "setup.coordinate_systems.build",
    PLACEMENT_NODE: "setup.placement",
}
_ALIASES = {
    "帮助": "help",
    "状态": "state",
    "问题": "issues",
    "校验": "validate",
    "创建操作": "create_operation",
    "设置操作": "set_operation",
    "生成操作": "generate_operation",
    "取消生成": "cancel_generation",
    "导出操作": "export_operation",
    "确认零件": "confirm_part",
    "设置机床": "set_machine",
    "设置喷嘴": "set_nozzle",
    "设置材料": "set_material",
    "设置模型坐标": "set_model_cs",
    "设置构建坐标": "set_build_cs",
    "设置装夹": "set_placement",
    "撤销": "undo",
    "重做": "redo",
}
_PUBLIC_COMMANDS = (
    "help",
    "state",
    "issues",
    "validate",
    "create_operation",
    "set_operation",
    "generate_operation",
    "cancel_generation",
    "export_operation",
    "confirm_part",
    "set_machine",
    "set_nozzle",
    "set_material",
    "set_model_cs",
    "set_build_cs",
    "set_placement",
    "undo",
    "redo",
)
_HELP = {
    "create_operation": "create_operation(operation_type='tube_thin_wall_indexed', operation_id=None, name=None)",
    "set_operation": (
        "set_operation(operation_id=None, name=None, enabled=None, tube_body_id=None, entry_port_id=None, "
        "exit_port_id=None, substrate_body_id=None, manual_centerline_edge_ids=None, "
        "bead_width_mm=None, layer_height_mm=None, max_wedge_angle_deg=None, "
        "max_bead_height_error_mm=None, safe_clearance_mm=None, retract_length_mm=None, "
        "deposition_feedrate_mm_min=None, travel_feedrate_mm_min=None, "
        "contour_chord_error_mm=None, maximum_pass_spacing_mm=None, include_planar_base=None, "
        "base_order=None, seam_angle_deg=None)"
    ),
    "generate_operation": "generate_operation(operation_id=None)",
    "cancel_generation": "cancel_generation()",
    "export_operation": "export_operation(operation_id, destination)",
    "confirm_part": "confirm_part(part_body_ids=None, ignored_body_ids=())",
    "set_machine": "set_machine(resource_id)",
    "set_nozzle": (
        "set_nozzle(resource_id, interface=None, length_mm=None, use_collision_envelope=None)"
    ),
    "set_material": "set_material(resource_id, review_confirmed=None)",
    "set_model_cs": "set_model_cs(origin, z, x, input_frame='source')",
    "set_build_cs": "set_build_cs(origin, z, x, input_frame='model')",
    "set_placement": ("set_placement(mount_id, translation_mm=(0,0,0), rotation_xyz_deg=(0,0,0))"),
}
_OPERATION_GEOMETRY_FIELDS = (
    "tube_body_id",
    "entry_port_id",
    "exit_port_id",
    "substrate_body_id",
)
_OPERATION_PARAMETER_FIELDS = (
    "bead_width_mm",
    "layer_height_mm",
    "max_wedge_angle_deg",
    "max_bead_height_error_mm",
    "safe_clearance_mm",
    "retract_length_mm",
    "deposition_feedrate_mm_min",
    "travel_feedrate_mm_min",
    "contour_chord_error_mm",
)


class TubeCommandProvider:
    """Command metadata and handlers for one ``TubeSetupController``."""

    @property
    def public_commands(self) -> tuple[str, ...]:
        return _PUBLIC_COMMANDS

    @property
    def internal_commands(self) -> tuple[str, ...]:
        return tuple(sorted(_INTERNAL_COMMANDS))

    def canonical_name(self, name: str) -> str:
        canonical = str(name).strip()
        for prefix in ("tube.", "管状."):
            if canonical.startswith(prefix):
                canonical = canonical[len(prefix) :]
                break
        canonical = _ALIASES.get(canonical, canonical)
        if canonical not in _QUERY_COMMANDS | _MUTATION_COMMANDS | _HISTORY_COMMANDS.keys():
            raise ValueError(f"unknown Tube command: {name!r}")
        return canonical

    def kind(self, name: str) -> CommandKind:
        if name in _QUERY_COMMANDS:
            return "query"
        if name in _MUTATION_COMMANDS:
            return "mutation"
        return cast(CommandKind, _HISTORY_COMMANDS[name])

    def allows_drafts(self, name: str) -> bool:
        return name in _DRAFT_COMMANDS

    def invoke(
        self,
        controller: CommandController,
        invocation: CommandInvocation,
    ) -> CommandOutcome:
        if not isinstance(controller, TubeSetupController):
            raise TypeError("Tube commands require TubeSetupController")
        handler = getattr(self, f"_command_{invocation.name}", None)
        if handler is None:
            raise CommandError(
                "E_COMMAND_UNKNOWN",
                f"command {invocation.name!r} is handled by the kernel",
                command=invocation.name,
                command_id=invocation.command_id,
            )
        try:
            return cast(CommandOutcome, handler(controller, *invocation.args, **invocation.kwargs))
        except CommandError:
            raise
        except (OperationLimitError, TubeControllerError) as exc:
            raise CommandError(
                "E_DOMAIN_VALIDATION",
                str(exc),
                command=invocation.name,
                command_id=invocation.command_id,
            ) from exc

    def _command_help(
        self,
        controller: TubeSetupController,
        topic: str | None = None,
    ) -> CommandOutcome:
        del controller
        if topic is None:
            return CommandOutcome({"commands": self.public_commands}, record_history=False)
        command = self.canonical_name(topic)
        if command in _INTERNAL_COMMANDS:
            raise ValueError("internal commands are not part of script help")
        return CommandOutcome(
            {"command": command, "signature": _HELP.get(command, f"{command}()")},
            record_history=False,
        )

    @staticmethod
    def _command_state(controller: TubeSetupController) -> CommandOutcome:
        return CommandOutcome(controller.state_json(), record_history=False)

    @staticmethod
    def _command_issues(controller: TubeSetupController) -> CommandOutcome:
        issues = tuple(issue.to_json() for issue in controller.validation_report().issues)
        return CommandOutcome(issues, record_history=False)

    @staticmethod
    def _command_validate(controller: TubeSetupController) -> CommandOutcome:
        return CommandOutcome(controller.validation_report().to_json(), record_history=False)

    @staticmethod
    def _command_create_operation(
        controller: TubeSetupController,
        operation_type: str = "tube_thin_wall_indexed",
        operation_id: str | None = None,
        name: str | None = None,
    ) -> CommandOutcome:
        options: dict[str, Any] = {"operation_type": operation_type, "operation_id": operation_id}
        if name is not None:
            options["name"] = name
        operation = controller.create_operation(**options)
        return CommandOutcome(
            operation.to_json(),
            ("operation",),
            changed_fields=("operations",),
        )

    @staticmethod
    def _command_set_operation(
        controller: TubeSetupController,
        operation_id: str | None = None,
        name: str | None = None,
        enabled: bool | None = None,
        tube_body_id: str | None = None,
        entry_port_id: str | None = None,
        exit_port_id: str | None = None,
        substrate_body_id: str | None = None,
        manual_centerline_edge_ids: Any = None,
        bead_width_mm: float | None = None,
        layer_height_mm: float | None = None,
        max_wedge_angle_deg: float | None = None,
        max_bead_height_error_mm: float | None = None,
        safe_clearance_mm: float | None = None,
        retract_length_mm: float | None = None,
        deposition_feedrate_mm_min: float | None = None,
        travel_feedrate_mm_min: float | None = None,
        contour_chord_error_mm: float | None = None,
        maximum_pass_spacing_mm: float | None = None,
        include_planar_base: bool | None = None,
        base_order: str | None = None,
        seam_angle_deg: float | None = None,
    ) -> CommandOutcome:
        payload = dict(locals())
        payload.pop("controller")
        updated = _set_operation_from_payload(controller, payload)
        fields = _operation_changed_fields(payload)
        return CommandOutcome(updated.to_json(), ("operation",), changed_fields=fields)

    @staticmethod
    def _command_generate_operation(
        controller: TubeSetupController,
        operation_id: str | None = None,
    ) -> CommandOutcome:
        try:
            result = controller.generate_operation(operation_id)
        except GenerationCancelled as exc:
            return CommandOutcome(
                {"status": "cancelled", "message": str(exc)},
                ("operation",),
                changed_fields=(),
                project_only=True,
                record_history=False,
            )
        except Exception as exc:
            return CommandOutcome(
                {"status": "error", "message": str(exc)},
                ("operation",),
                changed_fields=("products",),
                project_only=True,
                record_history=False,
            )
        return CommandOutcome(
            {"status": "ready", "result": result.to_json()},
            ("operation",),
            changed_fields=("products",),
            project_only=True,
        )

    @staticmethod
    def _command_cancel_generation(controller: TubeSetupController) -> CommandOutcome:
        controller.cancel_generation()
        return CommandOutcome({"cancel_requested": True}, ("operation",), record_history=False)

    @staticmethod
    def _command_export_operation(
        controller: TubeSetupController,
        operation_id: str,
        destination: str,
    ) -> CommandOutcome:
        path = controller.export_operation_product(operation_id, destination)
        return CommandOutcome({"destination": str(path)}, ("operation",), record_history=False)

    @staticmethod
    def _command_confirm_part(
        controller: TubeSetupController,
        part_body_ids: Any = None,
        ignored_body_ids: Any = (),
    ) -> CommandOutcome:
        ignored = tuple(ignored_body_ids)
        excluded = set(ignored) | set(controller.setup.assignments.fixture_body_ids)
        part = (
            tuple(
                item.body_id for item in controller.part_candidates if item.body_id not in excluded
            )
            if part_body_ids is None
            else tuple(part_body_ids)
        )
        assignments = controller.confirm_assignments(
            part,
            ignored_body_ids=ignored,
            fixture_body_ids=controller.setup.assignments.fixture_body_ids,
        )
        return CommandOutcome(
            assignments.to_json(),
            ("part", "operation"),
            changed_fields=("setup.assignments", "operations"),
            project_only=True,
        )

    def _command_set_machine(
        self,
        controller: TubeSetupController,
        resource_id: str,
    ) -> CommandOutcome:
        profile = self._resolve(controller, "machine", resource_id, "set_machine")
        snapshot = controller.select_machine(profile)
        return CommandOutcome(
            snapshot.to_json(),
            ("machine", "placement", "operation"),
            changed_fields=("setup.resources.machine", "setup.placement", "operations"),
        )

    def _command_set_nozzle(
        self,
        controller: TubeSetupController,
        resource_id: str,
        interface: str | None = None,
        length_mm: float | None = None,
        use_collision_envelope: bool | None = None,
    ) -> CommandOutcome:
        resolved = self._resolve(controller, "nozzle", resource_id, "set_nozzle")
        if not isinstance(resolved, NozzleProfile):
            raise TypeError("resolved resource is not a Nozzle Profile")
        if interface is not None and not isinstance(interface, str):
            raise TypeError("interface must be str or None")
        if length_mm is not None:
            length_mm = _finite_number(length_mm, "length_mm")
        if use_collision_envelope is not None and not isinstance(use_collision_envelope, bool):
            raise TypeError("use_collision_envelope must be bool or None")
        changed = any(value is not None for value in (interface, length_mm, use_collision_envelope))
        profile = resolved
        if changed:
            profile = nozzle_editor_profile(
                resolved,
                interface=resolved.interface or "" if interface is None else interface,
                length_mm=resolved.length_mm or 0.0 if length_mm is None else length_mm,
                use_collision_envelope=(
                    bool(resolved.outer_profile_rz_mm)
                    if use_collision_envelope is None
                    else use_collision_envelope
                ),
            )
            if profile != resolved:
                profile = replace(
                    profile,
                    resource_id=_project_resource_id(
                        "nozzle",
                        resolved.to_json(),
                        {
                            "interface": profile.interface,
                            "length_mm": profile.length_mm,
                            "use_collision_envelope": bool(profile.outer_profile_rz_mm),
                        },
                    ),
                )
        snapshot = controller.select_nozzle(profile)
        return CommandOutcome(
            snapshot.to_json(),
            ("nozzle", "operation"),
            changed_fields=_nozzle_changed_fields(
                interface,
                length_mm,
                use_collision_envelope,
            ),
        )

    def _command_set_material(
        self,
        controller: TubeSetupController,
        resource_id: str,
        review_confirmed: bool | None = None,
    ) -> CommandOutcome:
        resolved = self._resolve(controller, "material", resource_id, "set_material")
        if not isinstance(resolved, MaterialProfile):
            raise TypeError("resolved resource is not a Material Profile")
        if review_confirmed is not None and not isinstance(review_confirmed, bool):
            raise TypeError("review_confirmed must be bool or None")
        profile = resolved
        if review_confirmed is not None and review_confirmed != resolved.review_confirmed:
            profile = replace(
                resolved,
                resource_id=_project_resource_id(
                    "material",
                    resolved.to_json(),
                    {"review_confirmed": review_confirmed},
                ),
                display_name=f"{resolved.display_name} · project profile",
                profile_version=1,
                review_confirmed=review_confirmed,
                is_builtin=False,
            )
        snapshot = controller.select_material(profile)
        fields = ["setup.resources.material", "operations"]
        if review_confirmed is not None:
            fields.append("setup.resources.material.review_confirmed")
        return CommandOutcome(
            snapshot.to_json(),
            ("material", "operation"),
            changed_fields=tuple(fields),
        )

    @staticmethod
    def _command_set_model_cs(
        controller: TubeSetupController,
        origin: Any = (0, 0, 0),
        z: Any = (0, 0, 1),
        x: Any = (1, 0, 0),
        input_frame: str = "source",
    ) -> CommandOutcome:
        frame = _set_coordinate(controller, MODEL_CS_NODE, origin, z, x, input_frame)
        return CommandOutcome(
            frame.to_json(),
            ("model_cs", "operation"),
            changed_fields=("setup.coordinate_systems.model", "operations"),
        )

    @staticmethod
    def _command_set_build_cs(
        controller: TubeSetupController,
        origin: Any = (0, 0, 0),
        z: Any = (0, 0, 1),
        x: Any = (1, 0, 0),
        input_frame: str = "model",
    ) -> CommandOutcome:
        frame = _set_coordinate(controller, BUILD_CS_NODE, origin, z, x, input_frame)
        return CommandOutcome(
            frame.to_json(),
            ("build_cs", "placement", "operation"),
            changed_fields=(
                "setup.coordinate_systems.build",
                "setup.placement",
                "operations",
            ),
        )

    @staticmethod
    def _command_set_placement(
        controller: TubeSetupController,
        mount_id: str,
        translation_mm: Any = (0, 0, 0),
        rotation_xyz_deg: Any = (0, 0, 0),
    ) -> CommandOutcome:
        if not isinstance(mount_id, str) or not mount_id.strip():
            raise ValueError("mount_id must be a non-empty string")
        translation = _finite_vector3(translation_mm, "translation_mm")
        degrees = _finite_vector3(rotation_xyz_deg, "rotation_xyz_deg")
        adjustment = LocalAdjustment.from_euler_xyz(
            translation,
            tuple(math.radians(value) for value in degrees),
        )
        try:
            controller.begin_placement_draft(mount_datum_id=mount_id)
            controller.set_placement_adjustment(adjustment)
            transform = controller.apply_placement_draft()
        except ValueError as exc:
            raise CommandError(
                "E_DOMAIN_VALIDATION",
                str(exc),
                command="set_placement",
            ) from exc
        return CommandOutcome(
            {"adjustment": adjustment.to_json(), "T_mount_from_build": transform.to_json()},
            ("placement", "operation"),
            changed_fields=("setup.placement", "operations"),
        )

    @staticmethod
    def _command_apply_coordinate_draft(
        controller: TubeSetupController,
        node: str,
    ) -> CommandOutcome:
        frame = controller.apply_coordinate_draft(node)
        affected = (
            ("model_cs", "operation")
            if node.strip().lower() in {"model", "model_cs"}
            else ("build_cs", "placement", "operation")
        )
        field = (
            "setup.coordinate_systems.model"
            if affected[0] == "model_cs"
            else "setup.coordinate_systems.build"
        )
        fields = (
            (field, "operations")
            if affected[0] == "model_cs"
            else (field, "setup.placement", "operations")
        )
        return CommandOutcome(
            frame.to_json(),
            affected,
            changed_fields=fields,
        )

    @staticmethod
    def _command_apply_placement_draft(controller: TubeSetupController) -> CommandOutcome:
        transform = controller.apply_placement_draft()
        return CommandOutcome(
            transform.to_json(),
            ("placement", "operation"),
            changed_fields=("setup.placement", "operations"),
        )

    @staticmethod
    def _command_apply_all_drafts(controller: TubeSetupController) -> CommandOutcome:
        affected = controller.draft_nodes
        controller.apply_all_drafts()
        fields = tuple(_NODE_FIELDS[node] for node in affected if node in _NODE_FIELDS)
        return CommandOutcome(
            {"applied_nodes": affected},
            affected + ("operation",),
            changed_fields=fields + ("operations",),
        )

    @staticmethod
    def _command_apply_setup_config(
        controller: TubeSetupController,
        config: SetupConfig,
    ) -> CommandOutcome:
        if not isinstance(config, SetupConfig):
            raise TypeError("config must be a validated SetupConfig")
        apply_setup_config(controller, config)
        return CommandOutcome(
            config.to_document(),
            (
                "machine",
                "nozzle",
                "material",
                "model_cs",
                "build_cs",
                "placement",
                "operation",
            ),
            changed_fields=("setup", "operations"),
        )

    def _command_set_complete_nozzle(
        self,
        controller: TubeSetupController,
        resource_id: str,
        options: Any,
    ) -> CommandOutcome:
        resolved = self._resolve(controller, "nozzle", resource_id, "set_complete_nozzle")
        if not isinstance(resolved, NozzleProfile):
            raise TypeError("resolved resource is not a Nozzle Profile")
        if not isinstance(options, dict):
            raise TypeError("options must be an object")
        profile = configured_nozzle_copy(resolved, options)
        profile = replace(
            profile,
            resource_id=_project_resource_id("nozzle", resolved.to_json(), options),
        )
        snapshot = controller.select_nozzle(profile)
        return CommandOutcome(
            snapshot.to_json(),
            ("nozzle", "operation"),
            changed_fields=("setup.resources.nozzle", "operations"),
        )

    @staticmethod
    def _command_discard_all_drafts(controller: TubeSetupController) -> CommandOutcome:
        affected = controller.draft_nodes
        controller.discard_all_drafts()
        return CommandOutcome(
            {"discarded_nodes": affected},
            affected,
            changed_fields=("setup.draft_nodes",),
            project_only=True,
            record_history=False,
        )

    @staticmethod
    def _resolve(
        controller: TubeSetupController,
        resource_type: str,
        resource_id: str,
        command: str,
    ) -> Any:
        try:
            return controller.resolve_resource_profile(resource_type, resource_id)
        except (KeyError, ResourceLibraryError) as exc:
            raise CommandError(
                "E_RESOURCE_NOT_FOUND",
                f"{resource_type} resource {resource_id!r} was not found",
                command=command,
                details={"resource_type": resource_type, "resource_id": str(resource_id)},
            ) from exc


def _set_coordinate(
    controller: TubeSetupController,
    node: str,
    origin: Any,
    z_direction: Any,
    x_direction: Any,
    input_frame: str,
) -> Any:
    try:
        controller.begin_coordinate_draft(node)
        controller.set_numeric_origin(node, origin, input_frame=input_frame, confirmed=True)
        controller.set_numeric_direction(
            node, "z", z_direction, input_frame=input_frame, confirmed=True
        )
        controller.set_numeric_direction(
            node, "x", x_direction, input_frame=input_frame, confirmed=True
        )
        return controller.apply_coordinate_draft(node)
    except ValueError as exc:
        raise CommandError(
            "E_DOMAIN_VALIDATION",
            str(exc),
            command="set_model_cs" if node == MODEL_CS_NODE else "set_build_cs",
        ) from exc


def _set_operation_from_payload(
    controller: TubeSetupController,
    payload: dict[str, Any],
) -> TubeOperationDefinition:
    current = _operation_from_id(controller, payload["operation_id"])
    updated = replace(
        current,
        name=current.name if payload["name"] is None else payload["name"],
        enabled=current.enabled if payload["enabled"] is None else payload["enabled"],
    )
    _publish_operation(controller, updated, current)
    configured_fields = (*_OPERATION_GEOMETRY_FIELDS, *_OPERATION_PARAMETER_FIELDS)
    updated = _with_type_config(updated, payload)
    _publish_operation(controller, updated, _operation_from_id(controller, current.operation_id))
    manual = payload["manual_centerline_edge_ids"]
    if manual is None and not _has_operation_values(payload, configured_fields):
        return updated
    geometry = updated.geometry
    current_ids = (
        geometry.tube_body,
        geometry.entry_port,
        geometry.exit_port,
        geometry.substrate_body,
    )
    required_ids = tuple(
        payload[key] or (None if reference is None else reference.object_id)
        for key, reference in zip(_OPERATION_GEOMETRY_FIELDS, current_ids, strict=True)
    )
    if any(value is None for value in required_ids):
        raise ValueError("all Tube geometry roles are required when configuring operation")
    parameters = replace(
        updated.parameters,
        **{key: payload[key] for key in _OPERATION_PARAMETER_FIELDS if payload[key] is not None},
    )
    return controller.configure_operation(
        operation_id=current.operation_id,
        tube_body_id=str(required_ids[0]),
        entry_port_id=str(required_ids[1]),
        exit_port_id=str(required_ids[2]),
        substrate_body_id=str(required_ids[3]),
        manual_centerline_edge_ids=(
            tuple(item.object_id for item in geometry.manual_centerline_edges)
            if manual is None
            else tuple(manual)
        ),
        parameters=parameters,
    )


def _publish_operation(
    controller: TubeSetupController,
    updated: TubeOperationDefinition,
    current: TubeOperationDefinition,
) -> None:
    if updated == current:
        return
    checkpoint = controller.command_checkpoint()
    operations = tuple(
        updated if item.operation_id == current.operation_id else item
        for item in checkpoint.operations
    )
    controller.restore_command_checkpoint(replace(checkpoint, operations=operations, modified=True))
    controller._mark_product_stale(updated)


def _operation_changed_fields(payload: dict[str, Any]) -> tuple[str, ...]:
    fields = []
    operation_id = payload["operation_id"]
    target = "operations" if operation_id is None else f"operations[{operation_id}]"
    if payload["name"] is not None:
        fields.append(f"{target}.name")
    if payload["enabled"] is not None:
        fields.append(f"{target}.enabled")
    if payload["manual_centerline_edge_ids"] is not None or any(
        payload[key] is not None for key in _OPERATION_GEOMETRY_FIELDS
    ):
        fields.append(f"{target}.geometry")
    if any(payload[key] is not None for key in _OPERATION_PARAMETER_FIELDS):
        fields.append(f"{target}.parameters")
    if any(
        payload[key] is not None
        for key in (
            "maximum_pass_spacing_mm",
            "include_planar_base",
            "base_order",
            "seam_angle_deg",
        )
    ):
        fields.append(f"{target}.type_config")
    return tuple(fields)


def _operation_from_id(
    controller: TubeSetupController,
    operation_id: str | None,
) -> TubeOperationDefinition:
    if operation_id is None:
        if len(controller.operations) == 1:
            return controller.operations[0]
        raise CommandError(
            "E_DOMAIN_VALIDATION",
            "operation_id is required when more than one Tube operation exists",
            command="set_operation",
        )
    identifier = str(operation_id).strip()
    for operation in controller.operations:
        if operation.operation_id == identifier:
            return operation
    raise CommandError(
        "E_DOMAIN_VALIDATION",
        f"unknown operation_id: {identifier}",
        command="set_operation",
    )


def _with_type_config(
    operation: TubeOperationDefinition,
    payload: dict[str, Any],
) -> TubeOperationDefinition:
    if operation.operation_type == "tube_buildup":
        if payload["seam_angle_deg"] is not None:
            raise ValueError("seam_angle_deg applies only to tube_continuous")
        config = operation.type_config
        assert isinstance(config, TubeBuildupOperationConfig)
        changes = {
            key: payload[key]
            for key in ("maximum_pass_spacing_mm", "include_planar_base", "base_order")
            if payload[key] is not None
        }
        return replace(operation, type_config=replace(config, **changes))
    if operation.operation_type == "tube_continuous":
        if any(
            payload[key] is not None
            for key in ("maximum_pass_spacing_mm", "include_planar_base", "base_order")
        ):
            raise ValueError("Buildup configuration applies only to tube_buildup")
        config = operation.type_config
        assert isinstance(config, TubeContinuousOperationConfig)
        if payload["seam_angle_deg"] is not None:
            return replace(
                operation, type_config=replace(config, seam_angle_deg=payload["seam_angle_deg"])
            )
    special = ("maximum_pass_spacing_mm", "include_planar_base", "base_order", "seam_angle_deg")
    if any(payload[key] is not None for key in special):
        raise ValueError(f"type-specific parameters do not apply to {operation.operation_type}")
    return operation


def _finite_vector3(value: Any, field_name: str) -> tuple[float, float, float]:
    if isinstance(value, str):
        raise TypeError(f"{field_name} must contain three numbers")
    try:
        vector = tuple(float(item) for item in value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must contain three numbers") from exc
    if len(vector) != 3 or any(not math.isfinite(item) for item in vector):
        raise ValueError(f"{field_name} must contain three finite numbers")
    return cast(tuple[float, float, float], vector)


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    return number


def _project_resource_id(kind: str, template: Any, overrides: Any) -> str:
    """Derive a replay-stable local identity from source content and inputs."""

    content = canonical_content_hash({"template": template, "overrides": overrides})
    return str(uuid5(NAMESPACE_URL, f"five-axis-slicer:{kind}:{content}"))


def _nozzle_changed_fields(
    interface: str | None,
    length_mm: float | None,
    use_collision_envelope: bool | None,
) -> tuple[str, ...]:
    optional = (
        ("setup.resources.nozzle.interface", interface),
        ("setup.resources.nozzle.length_mm", length_mm),
        ("setup.resources.nozzle.outer_profile_rz_mm", use_collision_envelope),
    )
    return ("setup.resources.nozzle", "operations") + tuple(
        field for field, value in optional if value is not None
    )


def _has_operation_values(payload: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return any(payload[key] is not None for key in fields)


__all__ = ["TubeCommandProvider"]
