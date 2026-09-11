"""Geometry roles and explicit-unit parameters for indexed Tube operations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Mapping, cast

from .coordinates import GeometryReference


@dataclass(frozen=True, slots=True)
class TubeGeometrySelection:
    """Auditable geometry roles required by one indexed Tube operation."""

    tube_body: GeometryReference | None = None
    entry_port: GeometryReference | None = None
    exit_port: GeometryReference | None = None
    substrate_body: GeometryReference | None = None
    manual_centerline_edges: tuple[GeometryReference, ...] = ()

    def __post_init__(self) -> None:
        _validate_optional_reference(self.tube_body, "tube_body", "body")
        _validate_optional_reference(self.entry_port, "entry_port", "edge")
        _validate_optional_reference(self.exit_port, "exit_port", "edge")
        _validate_optional_reference(self.substrate_body, "substrate_body", "body")
        edges = tuple(self.manual_centerline_edges)
        for edge in edges:
            _validate_optional_reference(edge, "manual_centerline_edges", "edge")
        identifiers = tuple(item.object_id for item in edges)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("manual_centerline_edges contains duplicate references")
        _validate_distinct_roles(
            self.tube_body,
            self.substrate_body,
            "tube_body",
            "substrate_body",
        )
        _validate_distinct_roles(
            self.entry_port,
            self.exit_port,
            "entry_port",
            "exit_port",
        )
        object.__setattr__(self, "manual_centerline_edges", edges)

    @property
    def is_complete(self) -> bool:
        return all(
            item is not None
            for item in (self.tube_body, self.entry_port, self.exit_port, self.substrate_body)
        )

    def to_json(self) -> dict[str, Any]:
        return {
            name: None if getattr(self, name) is None else getattr(self, name).to_json()
            for name in ("tube_body", "entry_port", "exit_port", "substrate_body")
        } | {"manual_centerline_edges": [item.to_json() for item in self.manual_centerline_edges]}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> TubeGeometrySelection:
        if not isinstance(payload, Mapping):
            raise ValueError("Tube geometry selection payload must be an object")

        def optional_reference(name: str) -> GeometryReference | None:
            value = payload.get(name)
            return GeometryReference.from_json(value) if isinstance(value, Mapping) else None

        return cls(
            tube_body=optional_reference("tube_body"),
            entry_port=optional_reference("entry_port"),
            exit_port=optional_reference("exit_port"),
            substrate_body=optional_reference("substrate_body"),
            manual_centerline_edges=tuple(
                GeometryReference.from_json(item)
                for item in payload.get("manual_centerline_edges", ())
            ),
        )


@dataclass(frozen=True, slots=True)
class TubeProcessParameters:
    """Indexed Tube parameters in explicit public units."""

    bead_width_mm: float = 0.6
    layer_height_mm: float = 0.2
    max_wedge_angle_deg: float = 15.0
    max_bead_height_error_mm: float = 0.05
    safe_clearance_mm: float = 5.0
    retract_length_mm: float = 1.0
    deposition_feedrate_mm_min: float = 1200.0
    travel_feedrate_mm_min: float = 3000.0
    contour_chord_error_mm: float = 0.02

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and greater than zero")
            object.__setattr__(self, name, value)
        if self.max_wedge_angle_deg > 90.0:
            raise ValueError("max_wedge_angle_deg must not exceed 90 degrees")
        if self.layer_height_mm > self.bead_width_mm * 2.0:
            raise ValueError("layer_height_mm exceeds the supported bead aspect ratio")

    def to_json(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> TubeProcessParameters:
        if not isinstance(payload, Mapping):
            raise ValueError("Tube process parameters payload must be an object")
        defaults = cls()
        return cls(
            **{
                name: float(payload.get(name, getattr(defaults, name)))
                for name in cls.__dataclass_fields__
            }
        )


@dataclass(frozen=True, slots=True)
class TubeBuildupOperationConfig:
    """Settings unique to the multi-pass Tube Buildup operation."""

    maximum_pass_spacing_mm: float = 0.6
    include_planar_base: bool = False
    base_order: Literal["before_tube", "after_tube"] = "before_tube"

    def __post_init__(self) -> None:
        spacing = float(self.maximum_pass_spacing_mm)
        if not math.isfinite(spacing) or spacing <= 0.0:
            raise ValueError("maximum_pass_spacing_mm must be finite and greater than zero")
        if not isinstance(self.include_planar_base, bool):
            raise TypeError("include_planar_base must be a bool")
        if self.base_order not in {"before_tube", "after_tube"}:
            raise ValueError("base_order must be before_tube or after_tube")
        object.__setattr__(self, "maximum_pass_spacing_mm", spacing)

    def to_json(self) -> dict[str, Any]:
        return {
            "maximum_pass_spacing_mm": self.maximum_pass_spacing_mm,
            "include_planar_base": self.include_planar_base,
            "base_order": self.base_order,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> TubeBuildupOperationConfig:
        if not isinstance(payload, Mapping):
            raise ValueError("Tube Buildup configuration payload must be an object")
        return cls(
            maximum_pass_spacing_mm=float(payload.get("maximum_pass_spacing_mm", 0.6)),
            include_planar_base=bool(payload.get("include_planar_base", False)),
            base_order=cast(
                Literal["before_tube", "after_tube"],
                str(payload.get("base_order", "before_tube")),
            ),
        )


@dataclass(frozen=True, slots=True)
class TubeContinuousOperationConfig:
    """Settings unique to the continuous-helical Tube operation."""

    seam_angle_deg: float = 0.0

    def __post_init__(self) -> None:
        angle = float(self.seam_angle_deg)
        if not math.isfinite(angle):
            raise ValueError("seam_angle_deg must be finite")
        object.__setattr__(self, "seam_angle_deg", angle)

    def to_json(self) -> dict[str, float]:
        return {"seam_angle_deg": self.seam_angle_deg}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> TubeContinuousOperationConfig:
        if not isinstance(payload, Mapping):
            raise ValueError("Tube Continuous configuration payload must be an object")
        return cls(seam_angle_deg=float(payload.get("seam_angle_deg", 0.0)))


def _validate_optional_reference(
    reference: GeometryReference | None,
    name: str,
    geometry_type: str,
) -> None:
    if reference is not None and not isinstance(reference, GeometryReference):
        raise TypeError(f"{name} must be GeometryReference")
    if reference is not None and reference.geometry_type != geometry_type:
        raise ValueError(f"{name} must reference {geometry_type} geometry")


def _validate_distinct_roles(
    left: GeometryReference | None,
    right: GeometryReference | None,
    left_name: str,
    right_name: str,
) -> None:
    if left is not None and right is not None and left.object_id == right.object_id:
        raise ValueError(f"{left_name} and {right_name} must be different")


__all__ = [
    "TubeBuildupOperationConfig",
    "TubeContinuousOperationConfig",
    "TubeGeometrySelection",
    "TubeProcessParameters",
]
