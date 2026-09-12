"""Persisted Rotary frame, region and process contracts.

All internal lengths are millimetres and angles are radians.  The geometry is
defined in Source coordinates and transformed to Build coordinates only when a
plan is generated.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import math
from typing import Any, Mapping, cast

from .coordinates import GeometryReference
from .json_contract import parse_json_bool, require_bool
from .resources import canonical_json_bytes
from .setup import NodeState

ROTARY_OPERATION_TYPES = frozenset(
    {"rotary_spiral", "rotary_thin_wall", "rotary_around_part"}
)
Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class RotaryFrame:
    """Right-handed rotary frame in Source coordinates."""

    axis_origin_mm: Vector3 = (0.0, 0.0, 0.0)
    axis_direction: Vector3 = (0.0, 0.0, 1.0)
    zero_direction: Vector3 = (1.0, 0.0, 0.0)
    positive_direction: int = 1
    axis_reference: GeometryReference | None = None

    def __post_init__(self) -> None:
        origin = _vector(self.axis_origin_mm, "axis_origin_mm")
        axis = _unit(self.axis_direction, "rotary.axis_invalid")
        zero = _unit(self.zero_direction, "rotary.zero_direction_invalid")
        if abs(_dot(axis, zero)) > 1.0e-8:
            raise ValueError("rotary.zero_direction_invalid: zero direction must be perpendicular")
        direction = self.positive_direction
        if isinstance(direction, bool) or direction not in {-1, 1}:
            raise ValueError("positive_direction must be +1 or -1")
        reference = self.axis_reference
        if reference is not None and reference.geometry_type != "edge":
            raise ValueError("axis_reference must identify an edge")
        object.__setattr__(self, "axis_origin_mm", origin)
        object.__setattr__(self, "axis_direction", axis)
        object.__setattr__(self, "zero_direction", zero)

    @property
    def transverse_direction(self) -> Vector3:
        return _scale(_cross(self.axis_direction, self.zero_direction), self.positive_direction)

    def to_json(self) -> dict[str, Any]:
        return {
            "axis_origin_mm": list(self.axis_origin_mm),
            "axis_direction": list(self.axis_direction),
            "zero_direction": list(self.zero_direction),
            "positive_direction": self.positive_direction,
            "axis_reference": (
                None if self.axis_reference is None else self.axis_reference.to_json()
            ),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "RotaryFrame":
        reference = payload.get("axis_reference")
        return cls(
            cast(Vector3, tuple(payload.get("axis_origin_mm", (0.0, 0.0, 0.0)))),
            cast(Vector3, tuple(payload.get("axis_direction", (0.0, 0.0, 1.0)))),
            cast(Vector3, tuple(payload.get("zero_direction", (1.0, 0.0, 0.0)))),
            int(payload.get("positive_direction", 1)),
            None if reference is None else GeometryReference.from_json(reference),
        )


@dataclass(frozen=True, slots=True)
class RotaryProfile:
    """Cylinder or linearly varying cone profile along the rotary axis."""

    axial_start_mm: float = 0.0
    axial_end_mm: float = 10.0
    radius_start_mm: float = 10.0
    radius_end_mm: float = 10.0
    contour_references: tuple[GeometryReference, ...] = ()
    surface_references: tuple[GeometryReference, ...] = ()

    def __post_init__(self) -> None:
        for name in ("axial_start_mm", "axial_end_mm", "radius_start_mm", "radius_end_mm"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.axial_end_mm <= self.axial_start_mm:
            raise ValueError("rotary.profile_axial_range_invalid")
        if self.radius_start_mm <= 0.0 or self.radius_end_mm <= 0.0:
            raise ValueError("rotary.radius_invalid")
        contours = tuple(self.contour_references)
        surfaces = tuple(self.surface_references)
        if any(item.geometry_type != "edge" for item in contours):
            raise ValueError("contour_references must identify edges")
        if any(item.geometry_type != "face" for item in surfaces):
            raise ValueError("surface_references must identify faces")
        object.__setattr__(self, "contour_references", contours)
        object.__setattr__(self, "surface_references", surfaces)

    @property
    def is_conical(self) -> bool:
        return abs(self.radius_end_mm - self.radius_start_mm) > 1.0e-12

    def radius_at(self, axial_mm: float) -> float:
        fraction = (axial_mm - self.axial_start_mm) / (
            self.axial_end_mm - self.axial_start_mm
        )
        return self.radius_start_mm + fraction * (
            self.radius_end_mm - self.radius_start_mm
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "axial_start_mm": self.axial_start_mm,
            "axial_end_mm": self.axial_end_mm,
            "radius_start_mm": self.radius_start_mm,
            "radius_end_mm": self.radius_end_mm,
            "contour_references": [item.to_json() for item in self.contour_references],
            "surface_references": [item.to_json() for item in self.surface_references],
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "RotaryProfile":
        return cls(
            payload.get("axial_start_mm", 0.0),
            payload.get("axial_end_mm", 10.0),
            payload.get("radius_start_mm", 10.0),
            payload.get("radius_end_mm", 10.0),
            tuple(GeometryReference.from_json(item) for item in payload.get("contour_references", ())),
            tuple(GeometryReference.from_json(item) for item in payload.get("surface_references", ())),
        )


@dataclass(frozen=True, slots=True)
class RotaryAngularRegion:
    """One directed angular coverage interval; wrapped end values are allowed."""

    region_id: str
    start_angle_rad: float
    end_angle_rad: float
    direction: str = "ccw"

    def __post_init__(self) -> None:
        identifier = _identifier(self.region_id, "region_id")
        start = _finite(self.start_angle_rad, "start_angle_rad")
        end = _finite(self.end_angle_rad, "end_angle_rad")
        direction = str(self.direction).strip().lower()
        if direction not in {"ccw", "cw"}:
            raise ValueError("rotary.period_ambiguous: direction must be cw or ccw")
        if abs(end - start) <= 1.0e-12:
            raise ValueError("rotary.period_ambiguous: angular span must be explicit")
        object.__setattr__(self, "region_id", identifier)
        object.__setattr__(self, "start_angle_rad", start)
        object.__setattr__(self, "end_angle_rad", end)
        object.__setattr__(self, "direction", direction)

    @property
    def unwrapped_end_angle_rad(self) -> float:
        end = self.end_angle_rad
        if self.direction == "ccw":
            while end <= self.start_angle_rad:
                end += math.tau
        else:
            while end >= self.start_angle_rad:
                end -= math.tau
        return end

    @property
    def crosses_zero(self) -> bool:
        low = min(self.start_angle_rad, self.end_angle_rad)
        high = max(self.start_angle_rad, self.end_angle_rad)
        return abs(self.unwrapped_end_angle_rad - self.end_angle_rad) > 1.0e-12 or (
            low < 0.0 < high
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "start_angle_rad": self.start_angle_rad,
            "end_angle_rad": self.end_angle_rad,
            "direction": self.direction,
            "unwrapped_end_angle_rad": self.unwrapped_end_angle_rad,
            "crosses_zero": self.crosses_zero,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "RotaryAngularRegion":
        return cls(
            str(payload.get("region_id", "")),
            payload.get("start_angle_rad", 0.0),
            payload.get("end_angle_rad", 0.0),
            str(payload.get("direction", "ccw")),
        )


@dataclass(frozen=True, slots=True)
class RotaryGeometrySelection:
    frame: RotaryFrame = field(default_factory=RotaryFrame)
    profile: RotaryProfile = field(default_factory=RotaryProfile)
    angular_regions: tuple[RotaryAngularRegion, ...] = ()
    preview_only: bool = False

    def __post_init__(self) -> None:
        regions = tuple(self.angular_regions)
        identifiers = [item.region_id for item in regions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("rotary.region_duplicate")
        object.__setattr__(self, "angular_regions", regions)
        object.__setattr__(
            self, "preview_only", require_bool(self.preview_only, field_name="preview_only")
        )

    @property
    def is_complete(self) -> bool:
        return self.frame.axis_reference is not None and bool(
            self.profile.surface_references
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "frame": self.frame.to_json(),
            "profile": self.profile.to_json(),
            "angular_regions": [item.to_json() for item in self.angular_regions],
            "preview_only": self.preview_only,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "RotaryGeometrySelection":
        return cls(
            RotaryFrame.from_json(payload.get("frame", {})),
            RotaryProfile.from_json(payload.get("profile", {})),
            tuple(RotaryAngularRegion.from_json(item) for item in payload.get("angular_regions", ())),
            parse_json_bool(payload, "preview_only", default=False),
        )


@dataclass(frozen=True, slots=True)
class RotaryProcessParameters:
    pitch_mm: float = 5.0
    direction: str = "ccw"
    start_angle_rad: float = 0.0
    end_angle_rad: float = math.tau
    angular_velocity_rad_s: float = 0.5
    sampling_angle_rad: float = math.radians(5.0)
    bead_width_mm: float = 0.6
    layer_height_mm: float = 0.2
    feedrate_mm_min: float = 900.0
    travel_feedrate_mm_min: float = 1800.0
    retract_length_mm: float = 1.0
    dwell_s: float = 0.0
    axial_step_mm: float = 2.0
    radial_pass_count: int = 1
    radial_spacing_mm: float = 0.6
    wall_thickness_mm: float = 0.6
    thin_wall_width_policy: str = "error"
    connection_clearance_mm: float = 1.0

    def __post_init__(self) -> None:
        positive = (
            "pitch_mm",
            "angular_velocity_rad_s",
            "sampling_angle_rad",
            "bead_width_mm",
            "layer_height_mm",
            "feedrate_mm_min",
            "travel_feedrate_mm_min",
            "axial_step_mm",
            "radial_spacing_mm",
            "wall_thickness_mm",
            "connection_clearance_mm",
        )
        for name in positive:
            value = _finite(getattr(self, name), name)
            if value <= 0.0:
                raise ValueError(f"rotary.{name}_invalid")
            object.__setattr__(self, name, value)
        for name in ("start_angle_rad", "end_angle_rad", "retract_length_mm", "dwell_s"):
            value = _finite(getattr(self, name), name)
            if name in {"retract_length_mm", "dwell_s"} and value < 0.0:
                raise ValueError(f"rotary.{name}_invalid")
            object.__setattr__(self, name, value)
        direction = str(self.direction).strip().lower()
        if direction not in {"ccw", "cw"}:
            raise ValueError("rotary.direction_invalid")
        object.__setattr__(self, "direction", direction)
        if abs(self.end_angle_rad - self.start_angle_rad) <= 1.0e-12:
            raise ValueError("rotary.period_ambiguous")
        count = self.radial_pass_count
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 100:
            raise ValueError("rotary.radial_pass_count_invalid")
        policy = str(self.thin_wall_width_policy).strip().lower()
        if policy not in {"error", "reduce"}:
            raise ValueError("rotary.thin_wall_width_policy_invalid")
        object.__setattr__(self, "thin_wall_width_policy", policy)

    def to_json(self) -> dict[str, float | int | str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "RotaryProcessParameters":
        defaults = cls()
        return cls(
            **{name: payload.get(name, getattr(defaults, name)) for name in cls.__dataclass_fields__}
        )


@dataclass(frozen=True, slots=True)
class RotaryOperationDefinition:
    operation_id: str
    setup_id: str
    name: str = "Rotary Spiral"
    operation_type: str = "rotary_spiral"
    state: NodeState = NodeState.DIRTY
    dirty_reasons: tuple[str, ...] = ()
    enabled: bool = True
    geometry: RotaryGeometrySelection = field(default_factory=RotaryGeometrySelection)
    parameters: RotaryProcessParameters = field(default_factory=RotaryProcessParameters)

    def __post_init__(self) -> None:
        for name in ("operation_id", "setup_id", "name"):
            object.__setattr__(self, name, _identifier(getattr(self, name), name))
        operation_type = str(self.operation_type).strip().lower()
        if operation_type not in ROTARY_OPERATION_TYPES:
            raise ValueError(f"unsupported Rotary operation_type: {operation_type!r}")
        object.__setattr__(self, "operation_type", operation_type)
        object.__setattr__(
            self, "state", self.state if isinstance(self.state, NodeState) else NodeState(str(self.state))
        )
        object.__setattr__(self, "enabled", require_bool(self.enabled, field_name="enabled"))
        reasons = tuple(_identifier(item, "dirty_reason") for item in self.dirty_reasons)
        object.__setattr__(self, "dirty_reasons", reasons)

    def mark_dirty(self, reason: str) -> "RotaryOperationDefinition":
        clean = _identifier(reason, "reason")
        reasons = self.dirty_reasons if clean in self.dirty_reasons else (*self.dirty_reasons, clean)
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
    def from_json(cls, payload: Mapping[str, Any]) -> "RotaryOperationDefinition":
        operation_type = str(payload.get("operation_type", "rotary_spiral"))
        return cls(
            str(payload.get("operation_id", "")),
            str(payload.get("setup_id", "")),
            str(payload.get("name", _default_name(operation_type))),
            operation_type,
            NodeState(str(payload.get("state", NodeState.DIRTY.value))),
            tuple(payload.get("dirty_reasons", ())),
            parse_json_bool(payload, "enabled", default=True),
            RotaryGeometrySelection.from_json(payload.get("geometry", {})),
            RotaryProcessParameters.from_json(payload.get("parameters", {})),
        )


def _default_name(operation_type: str) -> str:
    return {
        "rotary_spiral": "Rotary Spiral",
        "rotary_thin_wall": "Rotary Thin Wall",
        "rotary_around_part": "Rotary Around Part",
    }.get(operation_type, "Rotary Spiral")


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


def _vector(value: Any, code: str) -> Vector3:
    values = tuple(float(item) for item in value)
    if len(values) != 3 or any(not math.isfinite(item) for item in values):
        raise ValueError(code)
    return cast(Vector3, values)


def _unit(value: Any, code: str) -> Vector3:
    vector = _vector(value, code)
    length = math.sqrt(_dot(vector, vector))
    if length <= 1.0e-12:
        raise ValueError(code)
    return cast(Vector3, tuple(item / length for item in vector))


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _scale(value: Vector3, factor: float) -> Vector3:
    return cast(Vector3, tuple(item * factor for item in value))


__all__ = [
    "ROTARY_OPERATION_TYPES",
    "RotaryAngularRegion",
    "RotaryFrame",
    "RotaryGeometrySelection",
    "RotaryOperationDefinition",
    "RotaryProcessParameters",
    "RotaryProfile",
]
