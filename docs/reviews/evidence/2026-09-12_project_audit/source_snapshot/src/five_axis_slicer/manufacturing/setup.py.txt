"""Manufacturing Setup aggregate, operation state, and validation reporting.

State precedence is Invalid, Draft, Dirty, then the computed base state.
Coordinates Valid requires Part, Machine, Model CS, Build CS, and Placement.
Setup Ready additionally requires a complete Nozzle, reviewed Material, and no
Error issue. Reports are derived snapshots and are never persisted as authority.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any

from .coordinates import (
    CoordinateFrameDefinition,
    LocalAdjustment,
    RigidTransform,
)
from .json_contract import parse_json_bool, require_bool
from .resources import ResourceSnapshot
from .tube_parameters import (
    TubeBuildupOperationConfig,
    TubeContinuousOperationConfig,
    TubeGeometrySelection,
    TubeProcessParameters,
)


class NodeState(str, Enum):
    """Lifecycle state shown by a Setup or operation tree node."""

    MISSING = "missing"
    DRAFT = "draft"
    VALID = "valid"
    DIRTY = "dirty"
    INVALID = "invalid"


class IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


PART_NODE = "part"
MACHINE_NODE = "machine"
NOZZLE_NODE = "nozzle"
MATERIAL_NODE = "material"
MODEL_CS_NODE = "model_cs"
BUILD_CS_NODE = "build_cs"
PLACEMENT_NODE = "placement"
OPERATION_NODE = "operation"

_SETUP_NODES = frozenset(
    {
        PART_NODE,
        MACHINE_NODE,
        NOZZLE_NODE,
        MATERIAL_NODE,
        MODEL_CS_NODE,
        BUILD_CS_NODE,
        PLACEMENT_NODE,
    }
)
_ALL_STATE_NODES = _SETUP_NODES | {OPERATION_NODE}
_COORDINATE_FRAME_IDS = {
    MODEL_CS_NODE: "model",
    BUILD_CS_NODE: "build",
}
_MISSING_ISSUES = {
    PART_NODE: "SETUP_PART_MISSING",
    MACHINE_NODE: "SETUP_MACHINE_MISSING",
    NOZZLE_NODE: "SETUP_NOZZLE_MISSING",
    MATERIAL_NODE: "SETUP_MATERIAL_MISSING",
    MODEL_CS_NODE: "MODEL_CS_MISSING",
    BUILD_CS_NODE: "BUILD_CS_MISSING",
    PLACEMENT_NODE: "PLACEMENT_MISSING",
}
_TUBE_OPERATION_TYPES = frozenset({"tube_thin_wall_indexed", "tube_buildup", "tube_continuous"})
_BUILDUP_CONFIG_KEYS = (
    "maximum_pass_spacing_mm",
    "include_planar_base",
    "base_order",
)
_INVALID_ISSUES = {
    PART_NODE: "SETUP_PART_INVALID",
    MACHINE_NODE: "SETUP_MACHINE_INVALID",
    NOZZLE_NODE: "SETUP_NOZZLE_INVALID",
    MATERIAL_NODE: "SETUP_MATERIAL_INVALID",
    MODEL_CS_NODE: "MODEL_CS_INVALID",
    BUILD_CS_NODE: "BUILD_CS_INVALID",
    PLACEMENT_NODE: "PLACEMENT_INVALID",
}
_COORDINATE_NODES = (
    PART_NODE,
    MACHINE_NODE,
    MODEL_CS_NODE,
    BUILD_CS_NODE,
    PLACEMENT_NODE,
)
_READY_NODES = _COORDINATE_NODES + (NOZZLE_NODE, MATERIAL_NODE)


def _clean_identifier(value: Any, *, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result


def _unique_identifiers(values: Iterable[Any], *, name: str) -> tuple[str, ...]:
    try:
        raw_values = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{name} must be a sequence of identifiers") from exc
    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(raw_values):
        identifier = _clean_identifier(value, name=f"{name}[{index}]")
        if identifier not in seen:
            seen.add(identifier)
            result.append(identifier)
    return tuple(result)


def _freeze_context(value: Any, *, name: str = "context") -> Any:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_context(item, name=f"{name}.{key}") for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(
            _freeze_context(item, name=f"{name}[{index}]") for index, item in enumerate(value)
        )
    raise ValueError(f"{name} contains a value that is not JSON-compatible")


def _thaw_context(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw_context(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_context(item) for item in value]
    return value


def _node_set(values: Iterable[Any], *, name: str) -> frozenset[str]:
    nodes = frozenset(str(value).strip().lower() for value in values)
    invalid = sorted(node for node in nodes if node not in _ALL_STATE_NODES)
    if invalid:
        raise ValueError(f"{name} contains unsupported nodes: {', '.join(invalid)}")
    return nodes


def _resource_payload(snapshot: ResourceSnapshot) -> Mapping[str, Any]:
    payload = snapshot.payload
    if not isinstance(payload, Mapping):
        return {}
    return payload


def _resource_type_matches(snapshot: ResourceSnapshot, expected: str) -> bool:
    resource_type = str(snapshot.resource_type).strip().lower()
    return resource_type in {expected, f"{expected}_profile"}


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Stable issue code plus machine-readable context; UI text is localised elsewhere."""

    code: str
    severity: IssueSeverity
    object_id: str = ""
    context: Mapping[str, Any] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        code = _clean_identifier(self.code, name="code")
        try:
            severity = (
                self.severity
                if isinstance(self.severity, IssueSeverity)
                else IssueSeverity(str(self.severity).strip().lower())
            )
        except ValueError as exc:
            raise ValueError(f"unsupported issue severity: {self.severity!r}") from exc
        object_id = str(self.object_id).strip()
        if not isinstance(self.context, Mapping):
            raise ValueError("context must be an object")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "object_id", object_id)
        object.__setattr__(self, "context", _freeze_context(self.context))

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "object_id": self.object_id,
            "context": _thaw_context(self.context),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> ValidationIssue:
        if not isinstance(payload, Mapping):
            raise ValueError("validation issue payload must be an object")
        return cls(
            code=str(payload.get("code", "")),
            severity=IssueSeverity(str(payload.get("severity", ""))),
            object_id=str(payload.get("object_id", "")),
            context=payload.get("context", {}),
        )


@dataclass(frozen=True, slots=True)
class SetupValidationReport:
    """Immutable, serializable result of one Setup validation pass."""

    issues: tuple[ValidationIssue, ...]
    node_states: Mapping[str, NodeState] = field(hash=False)
    coordinates_valid: bool = False
    setup_ready: bool = False

    def __post_init__(self) -> None:
        issues = tuple(self.issues)
        if any(not isinstance(issue, ValidationIssue) for issue in issues):
            raise TypeError("issues must contain ValidationIssue objects")
        if not isinstance(self.node_states, Mapping):
            raise ValueError("node_states must be an object")
        states: dict[str, NodeState] = {}
        for raw_node, raw_state in self.node_states.items():
            node = str(raw_node).strip().lower()
            if node not in _ALL_STATE_NODES:
                raise ValueError(f"unsupported node state key: {node!r}")
            try:
                state = raw_state if isinstance(raw_state, NodeState) else NodeState(str(raw_state))
            except ValueError as exc:
                raise ValueError(f"unsupported node state: {raw_state!r}") from exc
            states[node] = state
        object.__setattr__(self, "issues", issues)
        object.__setattr__(self, "node_states", MappingProxyType(states))
        object.__setattr__(
            self,
            "coordinates_valid",
            require_bool(self.coordinates_valid, field_name="coordinates_valid"),
        )
        object.__setattr__(
            self,
            "setup_ready",
            require_bool(self.setup_ready, field_name="setup_ready"),
        )

    @property
    def has_errors(self) -> bool:
        return any(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.severity is IssueSeverity.WARNING for issue in self.issues)

    def state_for(self, node: str) -> NodeState:
        key = str(node).strip().lower()
        if key not in self.node_states:
            raise KeyError(key)
        return self.node_states[key]

    def to_json(self) -> dict[str, Any]:
        return {
            "issues": [issue.to_json() for issue in self.issues],
            "node_states": {node: state.value for node, state in sorted(self.node_states.items())},
            "coordinates_valid": self.coordinates_valid,
            "setup_ready": self.setup_ready,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> SetupValidationReport:
        if not isinstance(payload, Mapping):
            raise ValueError("setup validation report payload must be an object")
        return cls(
            issues=tuple(ValidationIssue.from_json(item) for item in payload.get("issues", ())),
            node_states=payload.get("node_states", {}),
            coordinates_valid=parse_json_bool(
                payload,
                "coordinates_valid",
                default=False,
                field_name="setup_validation_report.coordinates_valid",
            ),
            setup_ready=parse_json_bool(
                payload,
                "setup_ready",
                default=False,
                field_name="setup_validation_report.setup_ready",
            ),
        )


@dataclass(frozen=True, slots=True)
class ManufacturingObjectAssignments:
    """Explicit body roles for one Setup.

    Part accepts one or more closed solids.  Fixture is persisted as a reserved
    role while its editor remains outside this delivery slice.
    """

    part_body_ids: tuple[str, ...] = ()
    ignored_body_ids: tuple[str, ...] = ()
    fixture_body_ids: tuple[str, ...] = ()
    unassigned_body_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        groups = {
            "part_body_ids": _unique_identifiers(self.part_body_ids, name="part_body_ids"),
            "ignored_body_ids": _unique_identifiers(self.ignored_body_ids, name="ignored_body_ids"),
            "fixture_body_ids": _unique_identifiers(self.fixture_body_ids, name="fixture_body_ids"),
            "unassigned_body_ids": _unique_identifiers(
                self.unassigned_body_ids, name="unassigned_body_ids"
            ),
        }
        owner: dict[str, str] = {}
        for group_name, identifiers in groups.items():
            for identifier in identifiers:
                if identifier in owner:
                    raise ValueError(
                        f"body {identifier!r} is assigned to both "
                        f"{owner[identifier]} and {group_name}"
                    )
                owner[identifier] = group_name
        for group_name, identifiers in groups.items():
            object.__setattr__(self, group_name, identifiers)

    @property
    def has_part(self) -> bool:
        return bool(self.part_body_ids)

    @property
    def assigned_body_ids(self) -> tuple[str, ...]:
        return self.part_body_ids + self.ignored_body_ids + self.fixture_body_ids

    def to_json(self) -> dict[str, Any]:
        return {
            "part_body_ids": list(self.part_body_ids),
            "ignored_body_ids": list(self.ignored_body_ids),
            "fixture_body_ids": list(self.fixture_body_ids),
            "unassigned_body_ids": list(self.unassigned_body_ids),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> ManufacturingObjectAssignments:
        if not isinstance(payload, Mapping):
            raise ValueError("manufacturing object assignments payload must be an object")
        return cls(
            part_body_ids=tuple(payload.get("part_body_ids", ())),
            ignored_body_ids=tuple(payload.get("ignored_body_ids", ())),
            fixture_body_ids=tuple(payload.get("fixture_body_ids", ())),
            unassigned_body_ids=tuple(payload.get("unassigned_body_ids", ())),
        )


@dataclass(frozen=True, slots=True)
class TubeOperationDefinition:
    """Persisted definition for one supported Tube operation."""

    operation_id: str
    setup_id: str
    name: str = "Tube Thin-Wall Indexed"
    operation_type: str = "tube_thin_wall_indexed"
    state: NodeState = NodeState.DIRTY
    dirty_reasons: tuple[str, ...] = ()
    enabled: bool = True
    geometry: TubeGeometrySelection = field(default_factory=TubeGeometrySelection)
    parameters: TubeProcessParameters = field(default_factory=TubeProcessParameters)
    type_config: TubeBuildupOperationConfig | TubeContinuousOperationConfig | None = None

    def __post_init__(self) -> None:
        operation_id = _clean_identifier(self.operation_id, name="operation_id")
        setup_id = _clean_identifier(self.setup_id, name="setup_id")
        name = _clean_identifier(self.name, name="name")
        operation_type = str(self.operation_type).strip().lower()
        if operation_type not in _TUBE_OPERATION_TYPES:
            raise ValueError(f"unsupported Tube operation_type: {operation_type!r}")
        try:
            state = self.state if isinstance(self.state, NodeState) else NodeState(str(self.state))
        except ValueError as exc:
            raise ValueError(f"unsupported operation state: {self.state!r}") from exc
        reasons = _unique_identifiers(self.dirty_reasons, name="dirty_reasons")
        if not isinstance(self.geometry, TubeGeometrySelection):
            raise TypeError("geometry must be TubeGeometrySelection")
        if not isinstance(self.parameters, TubeProcessParameters):
            raise TypeError("parameters must be TubeProcessParameters")
        config = _normalise_operation_config(operation_type, self.type_config)
        if name == "Tube Thin-Wall Indexed" and operation_type != "tube_thin_wall_indexed":
            name = _operation_default_name(operation_type)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "setup_id", setup_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "operation_type", operation_type)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "dirty_reasons", reasons)
        object.__setattr__(self, "type_config", config)
        object.__setattr__(
            self,
            "enabled",
            require_bool(self.enabled, field_name="enabled"),
        )

    def mark_dirty(self, reason: str) -> TubeOperationDefinition:
        clean_reason = _clean_identifier(reason, name="reason")
        reasons = self.dirty_reasons
        if clean_reason not in reasons:
            reasons += (clean_reason,)
        return replace(self, state=NodeState.DIRTY, dirty_reasons=reasons)

    def to_json(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "setup_id": self.setup_id,
            "name": self.name,
            "operation_type": self.operation_type,
            "state": self.state.value,
            "dirty_reasons": list(self.dirty_reasons),
            "enabled": self.enabled,
            "geometry": self.geometry.to_json(),
            "parameters": self.parameters.to_json(),
            "type_config": None if self.type_config is None else self.type_config.to_json(),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> TubeOperationDefinition:
        if not isinstance(payload, Mapping):
            raise ValueError("Tube operation payload must be an object")
        operation_type = str(payload.get("operation_type", "tube_thin_wall_indexed"))
        raw_config = payload.get("type_config")
        # Accept the initial T09/T11 flat fields as a short-lived migration path.
        if raw_config is None and operation_type == "tube_buildup":
            raw_config = {key: payload[key] for key in _BUILDUP_CONFIG_KEYS if key in payload}
        if (
            raw_config is None
            and operation_type == "tube_continuous"
            and "seam_angle_deg" in payload
        ):
            raw_config = {"seam_angle_deg": payload["seam_angle_deg"]}
        return cls(
            operation_id=str(payload.get("operation_id", "")),
            setup_id=str(payload.get("setup_id", "")),
            name=str(payload.get("name", _operation_default_name(operation_type))),
            operation_type=operation_type,
            state=NodeState(str(payload.get("state", NodeState.DIRTY.value))),
            dirty_reasons=tuple(payload.get("dirty_reasons", ())),
            enabled=parse_json_bool(
                payload,
                "enabled",
                default=True,
                field_name="tube_operation.enabled",
            ),
            geometry=TubeGeometrySelection.from_json(payload.get("geometry", {})),
            parameters=TubeProcessParameters.from_json(payload.get("parameters", {})),
            type_config=_operation_config_from_json(operation_type, raw_config),
        )


def _operation_default_name(operation_type: str) -> str:
    return {
        "tube_thin_wall_indexed": "Tube Thin-Wall Indexed",
        "tube_buildup": "Tube Buildup",
        "tube_continuous": "Tube Continuous",
    }.get(str(operation_type).strip().lower(), "Tube Thin-Wall Indexed")


def _normalise_operation_config(
    operation_type: str,
    config: TubeBuildupOperationConfig | TubeContinuousOperationConfig | None,
) -> TubeBuildupOperationConfig | TubeContinuousOperationConfig | None:
    if operation_type == "tube_thin_wall_indexed":
        if config is not None:
            raise ValueError("tube_thin_wall_indexed does not accept a type_config")
        return None
    if operation_type == "tube_buildup":
        if config is None:
            return TubeBuildupOperationConfig()
        if not isinstance(config, TubeBuildupOperationConfig):
            raise TypeError("tube_buildup requires TubeBuildupOperationConfig")
        return config
    if operation_type == "tube_continuous":
        if config is None:
            return TubeContinuousOperationConfig()
        if not isinstance(config, TubeContinuousOperationConfig):
            raise TypeError("tube_continuous requires TubeContinuousOperationConfig")
        return config
    raise AssertionError(operation_type)  # guarded by __post_init__


def _operation_config_from_json(
    operation_type: str,
    payload: Any,
) -> TubeBuildupOperationConfig | TubeContinuousOperationConfig | None:
    canonical = str(operation_type).strip().lower()
    if canonical == "tube_thin_wall_indexed":
        if payload not in (None, {}):
            raise ValueError("tube_thin_wall_indexed does not accept a type_config")
        return None
    if payload is None:
        return None
    if canonical == "tube_buildup":
        return TubeBuildupOperationConfig.from_json(payload)
    if canonical == "tube_continuous":
        return TubeContinuousOperationConfig.from_json(payload)
    return None


@dataclass(frozen=True, slots=True)
class ManufacturingSetup:
    """Immutable aggregate for manufacturing objects, resources, and coordinates."""

    setup_id: str = "setup-1"
    name: str = "Manufacturing Setup 1"
    assignments: ManufacturingObjectAssignments = field(
        default_factory=ManufacturingObjectAssignments
    )
    machine: ResourceSnapshot | None = None
    nozzle: ResourceSnapshot | None = None
    material: ResourceSnapshot | None = None
    model_coordinate_system: CoordinateFrameDefinition | None = None
    build_coordinate_system: CoordinateFrameDefinition | None = None
    mount_datum_id: str | None = None
    placement_adjustment: LocalAdjustment = field(default_factory=LocalAdjustment)
    T_mount_from_build: RigidTransform | None = None
    draft_nodes: frozenset[str] = field(default_factory=frozenset)
    dirty_nodes: frozenset[str] = field(default_factory=frozenset)
    invalid_nodes: frozenset[str] = field(default_factory=frozenset)
    issues: tuple[ValidationIssue, ...] = ()
    revision: int = 1

    def __post_init__(self) -> None:
        setup_id = _clean_identifier(self.setup_id, name="setup_id")
        name = _clean_identifier(self.name, name="name")
        if not isinstance(self.assignments, ManufacturingObjectAssignments):
            raise TypeError("assignments must be ManufacturingObjectAssignments")
        for resource_name in ("machine", "nozzle", "material"):
            resource = getattr(self, resource_name)
            if resource is not None and not isinstance(resource, ResourceSnapshot):
                raise TypeError(f"{resource_name} must be a ResourceSnapshot")
        for frame_name in ("model_coordinate_system", "build_coordinate_system"):
            frame = getattr(self, frame_name)
            if frame is not None and not isinstance(frame, CoordinateFrameDefinition):
                raise TypeError(f"{frame_name} must be CoordinateFrameDefinition")
        mount_datum_id = (
            None if self.mount_datum_id is None else str(self.mount_datum_id).strip() or None
        )
        if not isinstance(self.placement_adjustment, LocalAdjustment):
            raise TypeError("placement_adjustment must be LocalAdjustment")
        if self.T_mount_from_build is not None and not isinstance(
            self.T_mount_from_build, RigidTransform
        ):
            raise TypeError("T_mount_from_build must be RigidTransform")
        draft_nodes = _node_set(self.draft_nodes, name="draft_nodes")
        dirty_nodes = _node_set(self.dirty_nodes, name="dirty_nodes")
        invalid_nodes = _node_set(self.invalid_nodes, name="invalid_nodes")
        issues = tuple(self.issues)
        if any(not isinstance(issue, ValidationIssue) for issue in issues):
            raise TypeError("issues must contain ValidationIssue objects")
        revision = int(self.revision)
        if revision < 1:
            raise ValueError("revision must be at least 1")
        object.__setattr__(self, "setup_id", setup_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "mount_datum_id", mount_datum_id)
        object.__setattr__(self, "draft_nodes", draft_nodes)
        object.__setattr__(self, "dirty_nodes", dirty_nodes)
        object.__setattr__(self, "invalid_nodes", invalid_nodes)
        object.__setattr__(self, "issues", issues)
        object.__setattr__(self, "revision", revision)

    def _resource_state(self, node: str, snapshot: ResourceSnapshot | None) -> NodeState:
        if snapshot is None:
            return NodeState.MISSING
        if not _resource_type_matches(snapshot, node):
            return NodeState.INVALID
        if node == NOZZLE_NODE:
            try:
                nozzle_profile = snapshot.as_nozzle_profile()
            except (AttributeError, KeyError, TypeError, ValueError):
                return NodeState.INVALID
            if nozzle_profile.readiness_blockers:
                return NodeState.INVALID
        if node == MATERIAL_NODE:
            try:
                material_profile = snapshot.as_material_profile()
            except (AttributeError, KeyError, TypeError, ValueError):
                return NodeState.INVALID
            non_review_blockers = tuple(
                issue
                for issue in material_profile.readiness_blockers
                if issue.code != "material.review_required"
            )
            if non_review_blockers:
                return NodeState.INVALID
            if material_profile.review_required and not material_profile.review_confirmed:
                return NodeState.DRAFT
        if node == MACHINE_NODE:
            try:
                from .machine import MachineProfile

                MachineProfile.from_json(snapshot.payload)
            except (AttributeError, KeyError, TypeError, ValueError):
                return NodeState.INVALID
        return NodeState.VALID

    def _base_node_states(self) -> dict[str, NodeState]:
        states = {
            PART_NODE: (NodeState.VALID if self.assignments.has_part else NodeState.MISSING),
            MACHINE_NODE: self._resource_state(MACHINE_NODE, self.machine),
            NOZZLE_NODE: self._resource_state(NOZZLE_NODE, self.nozzle),
            MATERIAL_NODE: self._resource_state(MATERIAL_NODE, self.material),
            MODEL_CS_NODE: self._frame_state(
                self.model_coordinate_system,
                expected_frame_id=_COORDINATE_FRAME_IDS[MODEL_CS_NODE],
            ),
            BUILD_CS_NODE: self._frame_state(
                self.build_coordinate_system,
                expected_frame_id=_COORDINATE_FRAME_IDS[BUILD_CS_NODE],
            ),
            PLACEMENT_NODE: self._placement_state(),
        }
        for node in self.dirty_nodes:
            if node in states and states[node] is not NodeState.INVALID:
                states[node] = NodeState.DIRTY
        for node in self.draft_nodes:
            if node in states and states[node] is not NodeState.INVALID:
                states[node] = NodeState.DRAFT
        for node in self.invalid_nodes:
            if node in states:
                states[node] = NodeState.INVALID
        return states

    def _placement_state(self) -> NodeState:
        """Validate the persisted frame semantics of ``T_mount_from_build``.

        The selected Machine Profile owns the mount identifier, while the
        Setup owns the Build-to-mount pairing.  Keeping both frame labels
        explicit prevents a numerically rigid matrix with reversed or stale
        semantics from being accepted after project deserialisation.
        """

        mount_id = self.mount_datum_id
        transform = self.T_mount_from_build
        if mount_id is None and transform is None:
            return NodeState.MISSING
        if mount_id is None or transform is None:
            return NodeState.INVALID
        if transform.source_frame != "build":
            return NodeState.INVALID
        if transform.target_frame != mount_id:
            return NodeState.INVALID
        if self.machine is not None:
            try:
                from .machine import MachineProfile

                machine = MachineProfile.from_json(self.machine.payload)
            except (AttributeError, KeyError, TypeError, ValueError):
                return NodeState.INVALID
            if mount_id not in machine.mount_map:
                return NodeState.INVALID
        return NodeState.VALID

    @staticmethod
    def _frame_state(
        frame: CoordinateFrameDefinition | None,
        *,
        expected_frame_id: str,
    ) -> NodeState:
        if frame is None:
            return NodeState.MISSING
        if frame.frame_id != expected_frame_id:
            return NodeState.INVALID
        if not frame.is_confirmed:
            return NodeState.DRAFT
        return NodeState.VALID if frame.is_valid else NodeState.INVALID

    def validation_report(self) -> SetupValidationReport:
        return _validate_setup(self, self._base_node_states())

    @property
    def coordinates_valid(self) -> bool:
        return self.validation_report().coordinates_valid

    @property
    def setup_ready(self) -> bool:
        return self.validation_report().setup_ready

    def with_model_coordinate_system(self, frame: CoordinateFrameDefinition) -> ManufacturingSetup:
        return replace(
            self,
            model_coordinate_system=frame,
            draft_nodes=self.draft_nodes - {MODEL_CS_NODE},
            invalid_nodes=self.invalid_nodes - {MODEL_CS_NODE},
            revision=self.revision + 1,
        )

    def with_build_coordinate_system(self, frame: CoordinateFrameDefinition) -> ManufacturingSetup:
        return replace(
            self,
            build_coordinate_system=frame,
            draft_nodes=self.draft_nodes - {BUILD_CS_NODE},
            invalid_nodes=self.invalid_nodes - {BUILD_CS_NODE},
            dirty_nodes=self.dirty_nodes | {PLACEMENT_NODE},
            revision=self.revision + 1,
        )

    def with_machine(self, snapshot: ResourceSnapshot) -> ManufacturingSetup:
        return replace(
            self,
            machine=snapshot,
            dirty_nodes=self.dirty_nodes | {PLACEMENT_NODE},
            revision=self.revision + 1,
        )

    def with_nozzle(self, snapshot: ResourceSnapshot) -> ManufacturingSetup:
        return replace(self, nozzle=snapshot, revision=self.revision + 1)

    def with_material(self, snapshot: ResourceSnapshot) -> ManufacturingSetup:
        return replace(self, material=snapshot, revision=self.revision + 1)

    def with_placement(
        self,
        mount_datum_id: str,
        T_mount_from_build: RigidTransform,
        adjustment: LocalAdjustment | None = None,
    ) -> ManufacturingSetup:
        return replace(
            self,
            mount_datum_id=_clean_identifier(mount_datum_id, name="mount_datum_id"),
            T_mount_from_build=T_mount_from_build,
            placement_adjustment=(self.placement_adjustment if adjustment is None else adjustment),
            dirty_nodes=self.dirty_nodes - {PLACEMENT_NODE},
            draft_nodes=self.draft_nodes - {PLACEMENT_NODE},
            invalid_nodes=self.invalid_nodes - {PLACEMENT_NODE},
            revision=self.revision + 1,
        )

    def to_json(self) -> dict[str, Any]:
        placement = None
        if self.mount_datum_id is not None or self.T_mount_from_build is not None:
            placement = {
                "mount_datum_id": self.mount_datum_id,
                "adjustment": self.placement_adjustment.to_json(),
                "T_mount_from_build": (
                    None if self.T_mount_from_build is None else self.T_mount_from_build.to_json()
                ),
            }
        return {
            "setup_id": self.setup_id,
            "name": self.name,
            "assignments": self.assignments.to_json(),
            "resources": {
                "machine": None if self.machine is None else self.machine.to_json(),
                "nozzle": None if self.nozzle is None else self.nozzle.to_json(),
                "material": None if self.material is None else self.material.to_json(),
            },
            "coordinate_systems": {
                "model": (
                    None
                    if self.model_coordinate_system is None
                    else self.model_coordinate_system.to_json()
                ),
                "build": (
                    None
                    if self.build_coordinate_system is None
                    else self.build_coordinate_system.to_json()
                ),
            },
            "placement": placement,
            "draft_nodes": sorted(self.draft_nodes),
            "dirty_nodes": sorted(self.dirty_nodes),
            "invalid_nodes": sorted(self.invalid_nodes),
            "issues": [issue.to_json() for issue in self.issues],
            "revision": self.revision,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> ManufacturingSetup:
        if not isinstance(payload, Mapping):
            raise ValueError("manufacturing Setup payload must be an object")
        resources = payload.get("resources", {})
        coordinates = payload.get("coordinate_systems", {})
        placement = payload.get("placement")
        if not isinstance(resources, Mapping):
            raise ValueError("Setup resources must be an object")
        if not isinstance(coordinates, Mapping):
            raise ValueError("Setup coordinate_systems must be an object")
        if placement is not None and not isinstance(placement, Mapping):
            raise ValueError("Setup placement must be an object or null")

        def resource(name: str) -> ResourceSnapshot | None:
            resource_payload = resources.get(name)
            return (
                None if resource_payload is None else ResourceSnapshot.from_json(resource_payload)
            )

        model_payload = coordinates.get("model")
        build_payload = coordinates.get("build")
        transform_payload = None if placement is None else placement.get("T_mount_from_build")
        adjustment_payload = None if placement is None else placement.get("adjustment")
        return cls(
            setup_id=str(payload.get("setup_id", "setup-1")),
            name=str(payload.get("name", "Manufacturing Setup 1")),
            assignments=ManufacturingObjectAssignments.from_json(payload.get("assignments", {})),
            machine=resource("machine"),
            nozzle=resource("nozzle"),
            material=resource("material"),
            model_coordinate_system=(
                None
                if model_payload is None
                else CoordinateFrameDefinition.from_json(model_payload)
            ),
            build_coordinate_system=(
                None
                if build_payload is None
                else CoordinateFrameDefinition.from_json(build_payload)
            ),
            mount_datum_id=(None if placement is None else placement.get("mount_datum_id")),
            placement_adjustment=(
                LocalAdjustment()
                if adjustment_payload is None
                else LocalAdjustment.from_json(adjustment_payload)
            ),
            T_mount_from_build=(
                None if transform_payload is None else RigidTransform.from_json(transform_payload)
            ),
            draft_nodes=frozenset(payload.get("draft_nodes", ())),
            dirty_nodes=frozenset(payload.get("dirty_nodes", ())),
            invalid_nodes=frozenset(payload.get("invalid_nodes", ())),
            issues=tuple(ValidationIssue.from_json(item) for item in payload.get("issues", ())),
            revision=int(payload.get("revision", 1)),
        )


def _validate_setup(
    setup: ManufacturingSetup, states: Mapping[str, NodeState]
) -> SetupValidationReport:
    issues = list(setup.issues)
    issue_codes = {issue.code for issue in issues}
    frame_mismatches = _append_frame_role_issues(setup, issues, issue_codes)
    _append_node_state_issues(
        setup.setup_id,
        states,
        frame_mismatches,
        issues,
        issue_codes,
    )
    _append_reference_machine_issue(setup.machine, issues, issue_codes)
    coordinates_valid = all(states[node] is NodeState.VALID for node in _COORDINATE_NODES)
    setup_ready = all(states[node] is NodeState.VALID for node in _READY_NODES) and not any(
        issue.severity is IssueSeverity.ERROR for issue in issues
    )
    return SetupValidationReport(
        issues=tuple(issues),
        node_states=states,
        coordinates_valid=coordinates_valid,
        setup_ready=setup_ready,
    )


def _append_frame_role_issues(
    setup: ManufacturingSetup,
    issues: list[ValidationIssue],
    issue_codes: set[str],
) -> set[str]:
    mismatches: set[str] = set()
    frames = (
        (MODEL_CS_NODE, setup.model_coordinate_system),
        (BUILD_CS_NODE, setup.build_coordinate_system),
    )
    for node, frame in frames:
        expected = _COORDINATE_FRAME_IDS[node]
        if frame is None or frame.frame_id == expected:
            continue
        mismatches.add(node)
        code = f"{node.upper()}_FRAME_ID_MISMATCH"
        if code in issue_codes:
            continue
        issues.append(
            ValidationIssue(
                code=code,
                severity=IssueSeverity.ERROR,
                object_id=frame.frame_id,
                context={
                    "node": node,
                    "expected_frame_id": expected,
                    "actual_frame_id": frame.frame_id,
                },
            )
        )
        issue_codes.add(code)
    return mismatches


def _append_node_state_issues(
    setup_id: str,
    states: Mapping[str, NodeState],
    frame_mismatches: set[str],
    issues: list[ValidationIssue],
    issue_codes: set[str],
) -> None:
    for node, state in states.items():
        code = _node_state_issue_code(node, state, frame_mismatches)
        if code is None or code in issue_codes:
            continue
        issues.append(
            ValidationIssue(
                code=code,
                severity=IssueSeverity.ERROR,
                object_id=setup_id,
                context={"node": node, "state": state.value},
            )
        )
        issue_codes.add(code)


def _node_state_issue_code(node: str, state: NodeState, frame_mismatches: set[str]) -> str | None:
    if state is NodeState.MISSING:
        return _MISSING_ISSUES[node]
    if state is NodeState.INVALID:
        return None if node in frame_mismatches else _INVALID_ISSUES[node]
    if state is NodeState.DIRTY:
        return f"{node.upper()}_DIRTY"
    if state is NodeState.DRAFT:
        return "MATERIAL_REVIEW_REQUIRED" if node == MATERIAL_NODE else f"{node.upper()}_DRAFT"
    return None


def _append_reference_machine_issue(
    machine: ResourceSnapshot | None,
    issues: list[ValidationIssue],
    issue_codes: set[str],
) -> None:
    if machine is None or "MACHINE_REFERENCE_ONLY" in issue_codes:
        return
    try:
        reference_only = parse_json_bool(
            _resource_payload(machine),
            "reference_only",
            default=True,
            field_name="machine.reference_only",
        )
    except TypeError:
        reference_only = False
    if reference_only:
        issues.append(
            ValidationIssue(
                code="MACHINE_REFERENCE_ONLY",
                severity=IssueSeverity.WARNING,
                object_id=machine.resource_id,
                context={"resource_type": machine.resource_type},
            )
        )


__all__ = [
    "BUILD_CS_NODE",
    "IssueSeverity",
    "MACHINE_NODE",
    "MATERIAL_NODE",
    "MODEL_CS_NODE",
    "ManufacturingObjectAssignments",
    "ManufacturingSetup",
    "NOZZLE_NODE",
    "NodeState",
    "OPERATION_NODE",
    "PART_NODE",
    "PLACEMENT_NODE",
    "SetupValidationReport",
    "TubeGeometrySelection",
    "TubeBuildupOperationConfig",
    "TubeContinuousOperationConfig",
    "TubeOperationDefinition",
    "TubeProcessParameters",
    "ValidationIssue",
]
