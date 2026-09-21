"""Persisted geometry and process contracts for bounded solid-fill operations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, TypeAlias

from .coordinates import GeometryReference


SOLID_FILL_OPERATION_TYPES = frozenset(
    {"spherical_solid_fill", "surface_solid_fill", "radial_solid_fill"}
)


def _reference(value: GeometryReference, geometry_type: str, name: str) -> GeometryReference:
    if not isinstance(value, GeometryReference) or value.geometry_type != geometry_type:
        raise ValueError(f"{name} must be a {geometry_type} GeometryReference")
    return value


def _finite(value: Any, name: str, *, positive: bool = True) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"{name} must be {qualifier}")
    return result


def _vector3(value: Any, name: str) -> tuple[float, float, float]:
    try:
        result = tuple(_finite(item, name, positive=False) for item in value)
    except TypeError as exc:
        raise ValueError(f"{name} must contain three finite numbers") from exc
    if len(result) != 3:
        raise ValueError(f"{name} must contain three finite numbers")
    return result  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class SphericalSolidGeometrySelection:
    bodies: tuple[GeometryReference, ...]
    center_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    substrate_body: GeometryReference | None = None

    def __post_init__(self) -> None:
        bodies = tuple(_reference(item, "body", "bodies") for item in self.bodies)
        if not bodies or len({item.object_id for item in bodies}) != len(bodies):
            raise ValueError("spherical bodies must be non-empty and unique")
        object.__setattr__(self, "bodies", bodies)
        object.__setattr__(self, "center_mm", _vector3(self.center_mm, "center_mm"))
        if self.substrate_body is not None:
            _reference(self.substrate_body, "body", "substrate_body")
            if self.substrate_body.object_id in {item.object_id for item in bodies}:
                raise ValueError("substrate_body must be distinct from spherical feature bodies")

    def to_json(self) -> dict[str, Any]:
        return {
            "operation_type": "spherical_solid_fill",
            "bodies": [item.to_json() for item in self.bodies],
            "center_mm": list(self.center_mm),
            "substrate_body": (
                None if self.substrate_body is None else self.substrate_body.to_json()
            ),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "SphericalSolidGeometrySelection":
        return cls(
            tuple(GeometryReference.from_json(item) for item in payload.get("bodies", ())),
            tuple(payload.get("center_mm", (0.0, 0.0, 0.0))),  # type: ignore[arg-type]
            (
                None
                if payload.get("substrate_body") is None
                else GeometryReference.from_json(payload["substrate_body"])
            ),
        )


@dataclass(frozen=True, slots=True)
class SurfaceSolidBodyGeometry:
    body: GeometryReference
    surface_face: GeometryReference
    opposite_face: GeometryReference
    root_edge: GeometryReference

    def __post_init__(self) -> None:
        _reference(self.body, "body", "body")
        _reference(self.surface_face, "face", "surface_face")
        _reference(self.opposite_face, "face", "opposite_face")
        _reference(self.root_edge, "edge", "root_edge")

    def to_json(self) -> dict[str, Any]:
        return {
            "body": self.body.to_json(),
            "surface_face": self.surface_face.to_json(),
            "opposite_face": self.opposite_face.to_json(),
            "root_edge": self.root_edge.to_json(),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "SurfaceSolidBodyGeometry":
        return cls(
            GeometryReference.from_json(payload["body"]),
            GeometryReference.from_json(payload["surface_face"]),
            GeometryReference.from_json(payload["opposite_face"]),
            GeometryReference.from_json(payload["root_edge"]),
        )


@dataclass(frozen=True, slots=True)
class SurfaceSolidGeometrySelection:
    bodies: tuple[SurfaceSolidBodyGeometry, ...]
    substrate_body: GeometryReference | None = None

    def __post_init__(self) -> None:
        bodies = tuple(self.bodies)
        if not bodies or any(not isinstance(item, SurfaceSolidBodyGeometry) for item in bodies):
            raise ValueError("surface solid bodies must be non-empty geometry selections")
        if len({item.body.object_id for item in bodies}) != len(bodies):
            raise ValueError("surface solid body references must be unique")
        object.__setattr__(self, "bodies", bodies)
        if self.substrate_body is not None:
            _reference(self.substrate_body, "body", "substrate_body")
            if self.substrate_body.object_id in {item.body.object_id for item in bodies}:
                raise ValueError("substrate_body must be distinct from surface feature bodies")

    def to_json(self) -> dict[str, Any]:
        return {
            "operation_type": "surface_solid_fill",
            "bodies": [item.to_json() for item in self.bodies],
            "substrate_body": (
                None if self.substrate_body is None else self.substrate_body.to_json()
            ),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "SurfaceSolidGeometrySelection":
        return cls(
            tuple(SurfaceSolidBodyGeometry.from_json(item) for item in payload.get("bodies", ())),
            (
                None
                if payload.get("substrate_body") is None
                else GeometryReference.from_json(payload["substrate_body"])
            ),
        )


@dataclass(frozen=True, slots=True)
class RadialSolidBladeGeometry:
    body: GeometryReference
    root_face: GeometryReference
    outer_face: GeometryReference

    def __post_init__(self) -> None:
        _reference(self.body, "body", "body")
        _reference(self.root_face, "face", "root_face")
        _reference(self.outer_face, "face", "outer_face")

    def to_json(self) -> dict[str, Any]:
        return {
            "body": self.body.to_json(),
            "root_face": self.root_face.to_json(),
            "outer_face": self.outer_face.to_json(),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "RadialSolidBladeGeometry":
        return cls(
            GeometryReference.from_json(payload["body"]),
            GeometryReference.from_json(payload["root_face"]),
            GeometryReference.from_json(payload["outer_face"]),
        )


@dataclass(frozen=True, slots=True)
class RadialSolidGeometrySelection:
    hub_body: GeometryReference
    blades: tuple[RadialSolidBladeGeometry, ...]
    axis_origin_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    axis_direction: tuple[float, float, float] = (0.0, 0.0, 1.0)
    substrate_body: GeometryReference | None = None

    def __post_init__(self) -> None:
        _reference(self.hub_body, "body", "hub_body")
        blades = tuple(self.blades)
        if not blades or any(not isinstance(item, RadialSolidBladeGeometry) for item in blades):
            raise ValueError("radial blades must be non-empty geometry selections")
        if len({item.body.object_id for item in blades}) != len(blades):
            raise ValueError("radial blade body references must be unique")
        origin = _vector3(self.axis_origin_mm, "axis_origin_mm")
        direction = _vector3(self.axis_direction, "axis_direction")
        length = math.sqrt(sum(item * item for item in direction))
        if length <= 1.0e-12:
            raise ValueError("axis_direction must be non-zero")
        direction = (
            direction[0] / length,
            direction[1] / length,
            direction[2] / length,
        )
        object.__setattr__(self, "blades", blades)
        object.__setattr__(self, "axis_origin_mm", origin)
        object.__setattr__(self, "axis_direction", direction)
        if self.substrate_body is not None:
            _reference(self.substrate_body, "body", "substrate_body")

    def to_json(self) -> dict[str, Any]:
        return {
            "operation_type": "radial_solid_fill",
            "hub_body": self.hub_body.to_json(),
            "blades": [item.to_json() for item in self.blades],
            "axis_origin_mm": list(self.axis_origin_mm),
            "axis_direction": list(self.axis_direction),
            "substrate_body": (
                None if self.substrate_body is None else self.substrate_body.to_json()
            ),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "RadialSolidGeometrySelection":
        return cls(
            GeometryReference.from_json(payload["hub_body"]),
            tuple(RadialSolidBladeGeometry.from_json(item) for item in payload.get("blades", ())),
            tuple(payload.get("axis_origin_mm", (0.0, 0.0, 0.0))),  # type: ignore[arg-type]
            tuple(payload.get("axis_direction", (0.0, 0.0, 1.0))),  # type: ignore[arg-type]
            (
                None
                if payload.get("substrate_body") is None
                else GeometryReference.from_json(payload["substrate_body"])
            ),
        )


SolidFillGeometrySelection: TypeAlias = (
    SphericalSolidGeometrySelection
    | SurfaceSolidGeometrySelection
    | RadialSolidGeometrySelection
)


def solid_geometry_from_json(payload: Mapping[str, Any]) -> SolidFillGeometrySelection:
    operation_type = str(payload.get("operation_type", "")).strip().lower()
    if operation_type == "spherical_solid_fill":
        return SphericalSolidGeometrySelection.from_json(payload)
    if operation_type == "surface_solid_fill":
        return SurfaceSolidGeometrySelection.from_json(payload)
    if operation_type == "radial_solid_fill":
        return RadialSolidGeometrySelection.from_json(payload)
    raise ValueError(f"unsupported solid geometry operation_type: {operation_type}")


@dataclass(frozen=True, slots=True)
class SolidFillProcessParameters:
    bead_width_mm: float = 0.4
    layer_height_mm: float = 0.2
    path_spacing_mm: float = 0.4
    sampling_step_mm: float = 0.2
    deposition_feedrate_mm_min: float = 1200.0
    travel_feedrate_mm_min: float = 3000.0
    retract_length_mm: float = 1.0
    substrate_radius_mm: float = 1.0
    radial_thickness_mm: float = 0.2
    solid_thickness_mm: float = 0.2
    safe_clearance_mm: float = 5.0
    sample_segments: int = 128
    metric_across_samples: int = 129
    metric_along_samples: int = 129
    face_metric_samples: int = 65

    def __post_init__(self) -> None:
        for name in (
            "bead_width_mm",
            "layer_height_mm",
            "path_spacing_mm",
            "sampling_step_mm",
            "deposition_feedrate_mm_min",
            "travel_feedrate_mm_min",
            "retract_length_mm",
            "substrate_radius_mm",
            "radial_thickness_mm",
            "solid_thickness_mm",
            "safe_clearance_mm",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.path_spacing_mm > self.bead_width_mm:
            raise ValueError("path_spacing_mm must not exceed bead_width_mm")
        for name, minimum in (
            ("sample_segments", 32),
            ("metric_across_samples", 17),
            ("metric_along_samples", 9),
            ("face_metric_samples", 17),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")

    def to_json(self) -> dict[str, float | int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "SolidFillProcessParameters":
        defaults = cls()
        return cls(
            **{
                name: payload.get(name, getattr(defaults, name))
                for name in cls.__dataclass_fields__
            }
        )


__all__ = [
    "SOLID_FILL_OPERATION_TYPES",
    "RadialSolidBladeGeometry",
    "RadialSolidGeometrySelection",
    "SolidFillGeometrySelection",
    "SolidFillProcessParameters",
    "SphericalSolidGeometrySelection",
    "SurfaceSolidBodyGeometry",
    "SurfaceSolidGeometrySelection",
    "solid_geometry_from_json",
]
