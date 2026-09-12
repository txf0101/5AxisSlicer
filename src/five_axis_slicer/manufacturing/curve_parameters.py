"""Persisted geometry and process contracts for the Curve workbench."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import math
from typing import Any, Mapping

from .coordinates import GeometryReference
from .json_contract import parse_json_bool, require_bool
from .resources import canonical_json_bytes
from .setup import NodeState

CURVE_OPERATION_TYPES = frozenset(
    {"curve_buildup", "curve_multi_pass", "curve_offset_buildup"}
)


@dataclass(frozen=True, slots=True)
class DirectedEdgeReference:
    """One persisted STEP edge and its selected traversal direction."""

    edge: GeometryReference
    reversed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.edge, GeometryReference) or self.edge.geometry_type != "edge":
            raise ValueError("edge must be an edge GeometryReference")
        object.__setattr__(self, "reversed", require_bool(self.reversed, field_name="reversed"))

    def to_json(self) -> dict[str, Any]:
        return {"edge": self.edge.to_json(), "reversed": self.reversed}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "DirectedEdgeReference":
        if not isinstance(payload, Mapping):
            raise ValueError("directed edge payload must be an object")
        return cls(
            GeometryReference.from_json(payload.get("edge", {})),
            parse_json_bool(payload, "reversed", default=False),
        )


@dataclass(frozen=True, slots=True)
class CurveGeometrySelection:
    """Ordered edge chain plus an explicit normal source in Source frame."""

    edges: tuple[DirectedEdgeReference, ...] = ()
    normal_mode: str = "adjacent_face"
    normal_face: GeometryReference | None = None
    specified_normal: tuple[float, float, float] | None = None

    def __post_init__(self) -> None:
        edges = tuple(self.edges)
        if any(not isinstance(item, DirectedEdgeReference) for item in edges):
            raise TypeError("edges must contain DirectedEdgeReference values")
        mode = str(self.normal_mode).strip().lower()
        if mode not in {"adjacent_face", "specified"}:
            raise ValueError("normal_mode must be 'adjacent_face' or 'specified'")
        face = self.normal_face
        if face is not None and (
            not isinstance(face, GeometryReference) or face.geometry_type != "face"
        ):
            raise ValueError("normal_face must be a face GeometryReference")
        normal = None if self.specified_normal is None else _unit(self.specified_normal)
        if mode == "specified" and normal is None:
            raise ValueError("specified normal mode requires specified_normal")
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "normal_mode", mode)
        object.__setattr__(self, "specified_normal", normal)

    @property
    def is_complete(self) -> bool:
        return bool(self.edges) and (
            self.specified_normal is not None
            if self.normal_mode == "specified"
            else self.normal_face is not None
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "edges": [item.to_json() for item in self.edges],
            "normal_mode": self.normal_mode,
            "normal_face": None if self.normal_face is None else self.normal_face.to_json(),
            "specified_normal": (
                None if self.specified_normal is None else list(self.specified_normal)
            ),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "CurveGeometrySelection":
        if not isinstance(payload, Mapping):
            raise ValueError("Curve geometry selection payload must be an object")
        face = payload.get("normal_face")
        normal = payload.get("specified_normal")
        return cls(
            tuple(DirectedEdgeReference.from_json(item) for item in payload.get("edges", ())),
            str(payload.get("normal_mode", "adjacent_face")),
            None if face is None else GeometryReference.from_json(face),
            None if normal is None else tuple(float(value) for value in normal),
        )


@dataclass(frozen=True, slots=True)
class CurveProcessParameters:
    """Curve sampling and deposition parameters in millimetres/radians."""

    sampling_step_mm: float = 1.0
    chord_error_mm: float = 0.05
    chain_tolerance_mm: float = 0.01
    bead_width_mm: float = 0.6
    layer_height_mm: float = 0.2
    feedrate_mm_min: float = 900.0
    travel_feedrate_mm_min: float = 1800.0
    retract_length_mm: float = 1.0
    dwell_s: float = 0.0
    layer_count: int = 3
    offset_pass_count: int = 3
    offset_spacing_mm: float = 0.6

    def __post_init__(self) -> None:
        floats = (
            "sampling_step_mm",
            "chord_error_mm",
            "chain_tolerance_mm",
            "bead_width_mm",
            "layer_height_mm",
            "feedrate_mm_min",
            "travel_feedrate_mm_min",
            "retract_length_mm",
            "dwell_s",
            "offset_spacing_mm",
        )
        for name in floats:
            value = _finite(getattr(self, name), name)
            if name == "dwell_s":
                if value < 0.0:
                    raise ValueError("dwell_s must not be negative")
            elif value <= 0.0:
                raise ValueError(f"{name} must be greater than zero")
            object.__setattr__(self, name, value)
        for name in ("layer_count", "offset_pass_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
                raise ValueError(f"{name} must be an integer from 1 to 100")
        if self.layer_height_mm > self.bead_width_mm * 2.0:
            raise ValueError("layer_height_mm exceeds the supported bead aspect ratio")

    def to_json(self) -> dict[str, float | int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "CurveProcessParameters":
        if not isinstance(payload, Mapping):
            raise ValueError("Curve process parameters payload must be an object")
        defaults = cls()
        return cls(
            **{
                name: payload.get(name, getattr(defaults, name))
                for name in cls.__dataclass_fields__
            }
        )


@dataclass(frozen=True, slots=True)
class CurveOperationDefinition:
    operation_id: str
    setup_id: str
    name: str = "Curve Buildup"
    operation_type: str = "curve_buildup"
    state: NodeState = NodeState.DIRTY
    dirty_reasons: tuple[str, ...] = ()
    enabled: bool = True
    geometry: CurveGeometrySelection = field(default_factory=CurveGeometrySelection)
    parameters: CurveProcessParameters = field(default_factory=CurveProcessParameters)

    def __post_init__(self) -> None:
        operation_id = _identifier(self.operation_id, "operation_id")
        setup_id = _identifier(self.setup_id, "setup_id")
        name = _identifier(self.name, "name")
        operation_type = str(self.operation_type).strip().lower()
        if operation_type not in CURVE_OPERATION_TYPES:
            raise ValueError(f"unsupported Curve operation_type: {operation_type!r}")
        state = self.state if isinstance(self.state, NodeState) else NodeState(str(self.state))
        if not isinstance(self.geometry, CurveGeometrySelection):
            raise TypeError("geometry must be CurveGeometrySelection")
        if not isinstance(self.parameters, CurveProcessParameters):
            raise TypeError("parameters must be CurveProcessParameters")
        reasons = tuple(_identifier(item, "dirty_reasons") for item in self.dirty_reasons)
        if len(set(reasons)) != len(reasons):
            raise ValueError("dirty_reasons contains duplicate values")
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "setup_id", setup_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "operation_type", operation_type)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "dirty_reasons", reasons)
        object.__setattr__(self, "enabled", require_bool(self.enabled, field_name="enabled"))

    def mark_dirty(self, reason: str) -> "CurveOperationDefinition":
        clean = _identifier(reason, "reason")
        reasons = self.dirty_reasons
        if clean not in reasons:
            reasons += (clean,)
        return replace(self, state=NodeState.DIRTY, dirty_reasons=reasons)

    def semantic_hash_input(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "name": self.name,
            "operation_type": self.operation_type,
            "enabled": self.enabled,
            "geometry": self.geometry.to_json(),
            "parameters": self.parameters.to_json(),
        }

    def semantic_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.semantic_hash_input())).hexdigest()

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
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "CurveOperationDefinition":
        if not isinstance(payload, Mapping):
            raise ValueError("Curve operation payload must be an object")
        operation_type = str(payload.get("operation_type", "curve_buildup"))
        return cls(
            operation_id=str(payload.get("operation_id", "")),
            setup_id=str(payload.get("setup_id", "")),
            name=str(payload.get("name", _default_name(operation_type))),
            operation_type=operation_type,
            state=NodeState(str(payload.get("state", NodeState.DIRTY.value))),
            dirty_reasons=tuple(payload.get("dirty_reasons", ())),
            enabled=parse_json_bool(payload, "enabled", default=True),
            geometry=CurveGeometrySelection.from_json(payload.get("geometry", {})),
            parameters=CurveProcessParameters.from_json(payload.get("parameters", {})),
        )


def _default_name(operation_type: str) -> str:
    return {
        "curve_buildup": "Curve Buildup",
        "curve_multi_pass": "Curve Multi-pass Buildup",
        "curve_offset_buildup": "Curve Offset Buildup",
    }.get(operation_type, "Curve Buildup")


def _identifier(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _unit(value: Any) -> tuple[float, float, float]:
    values = tuple(float(item) for item in value)
    if len(values) != 3 or any(not math.isfinite(item) for item in values):
        raise ValueError("specified_normal must be a finite 3-vector")
    length = math.sqrt(sum(item * item for item in values))
    if length <= 1.0e-12:
        raise ValueError("specified_normal must not be zero")
    return tuple(item / length for item in values)  # type: ignore[return-value]


__all__ = [
    "CURVE_OPERATION_TYPES",
    "CurveGeometrySelection",
    "CurveOperationDefinition",
    "CurveProcessParameters",
    "DirectedEdgeReference",
]
