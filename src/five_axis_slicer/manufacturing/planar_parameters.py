"""Persisted geometry and process contracts for Planar operations.

This module deliberately depends only on shared manufacturing value objects.
It keeps Planar operation persistence separate from the Tube-only setup model.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from .coordinates import GeometryReference
from .json_contract import parse_json_bool, require_bool
from .resources import canonical_json_bytes
from .setup import NodeState


_PLANAR_OPERATION_TYPES = frozenset(
    {
        "planar_region",
        "planar_zigzag",
        "planar_offset",
        "planar_thin_wall",
        "planar_spiral",
        "planar_support",
    }
)
_FLOAT_PARAMETER_NAMES = (
    "first_layer_z_mm",
    "layer_height_mm",
    "last_layer_z_mm",
    "bead_width_mm",
    "feedrate_mm_min",
    "line_spacing_mm",
    "travel_feedrate_mm_min",
    "retract_length_mm",
    "wall_thickness_mm",
    "support_overhang_angle_deg",
    "support_xy_gap_mm",
    "support_z_gap_mm",
    "support_line_spacing_mm",
    "support_interface_spacing_mm",
)


@dataclass(frozen=True, slots=True)
class PlanarGeometrySelection:
    """Stable body reference for a Planar operation."""

    body: GeometryReference | None = None

    def __post_init__(self) -> None:
        if self.body is not None and not isinstance(self.body, GeometryReference):
            raise TypeError("body must be GeometryReference")
        if self.body is not None and self.body.geometry_type != "body":
            raise ValueError("body must reference body geometry")

    @property
    def is_complete(self) -> bool:
        return self.body is not None

    def to_json(self) -> dict[str, Any]:
        return {"body": None if self.body is None else self.body.to_json()}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "PlanarGeometrySelection":
        if not isinstance(payload, Mapping):
            raise ValueError("Planar geometry selection payload must be an object")
        raw_body = payload.get("body")
        return cls(None if raw_body is None else GeometryReference.from_json(raw_body))


@dataclass(frozen=True, slots=True)
class PlanarProcessParameters:
    """Layer bounds and deposition settings, all in explicit millimetre units."""

    first_layer_z_mm: float = 0.2
    layer_height_mm: float = 0.2
    last_layer_z_mm: float = 0.2
    bead_width_mm: float = 0.6
    feedrate_mm_min: float = 1200.0
    line_spacing_mm: float = 0.6
    travel_feedrate_mm_min: float = 1800.0
    retract_length_mm: float = 1.0
    offset_pass_count: int = 3
    wall_thickness_mm: float = 0.6
    thin_wall_max_passes: int = 3
    spiral_samples_per_contour: int = 64
    support_overhang_angle_deg: float = 45.0
    support_xy_gap_mm: float = 0.4
    support_z_gap_mm: float = 0.2
    support_line_spacing_mm: float = 2.0
    support_interface_layers: int = 2
    support_interface_spacing_mm: float = 0.6
    support_pattern: str = "lines"

    def __post_init__(self) -> None:
        values = {name: _finite_float(getattr(self, name), name) for name in _FLOAT_PARAMETER_NAMES}
        offset_pass_count = _positive_int(self.offset_pass_count, "offset_pass_count")
        thin_wall_max_passes = _positive_int(self.thin_wall_max_passes, "thin_wall_max_passes")
        spiral_samples = _positive_int(
            self.spiral_samples_per_contour, "spiral_samples_per_contour"
        )
        support_interface_layers = _non_negative_int(
            self.support_interface_layers, "support_interface_layers"
        )
        support_pattern = str(self.support_pattern).strip().lower()
        _validate_common_parameters(values, spiral_samples)
        _validate_support_parameters(values, support_pattern)
        for name, value in values.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "offset_pass_count", offset_pass_count)
        object.__setattr__(self, "thin_wall_max_passes", thin_wall_max_passes)
        object.__setattr__(self, "spiral_samples_per_contour", spiral_samples)
        object.__setattr__(self, "support_interface_layers", support_interface_layers)
        object.__setattr__(self, "support_pattern", support_pattern)

    def to_json(self) -> dict[str, float | int | str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "PlanarProcessParameters":
        if not isinstance(payload, Mapping):
            raise ValueError("Planar process parameters payload must be an object")
        defaults = cls()
        return cls(
            **{
                name: payload.get(name, getattr(defaults, name))
                for name in cls.__dataclass_fields__
            }
        )


@dataclass(frozen=True, slots=True)
class PlanarOperationDefinition:
    """Persisted definition for one supported Planar operation."""

    operation_id: str
    setup_id: str
    name: str = "Planar Region"
    operation_type: str = "planar_region"
    state: NodeState = NodeState.DIRTY
    dirty_reasons: tuple[str, ...] = ()
    enabled: bool = True
    geometry: PlanarGeometrySelection = field(default_factory=PlanarGeometrySelection)
    parameters: PlanarProcessParameters = field(default_factory=PlanarProcessParameters)

    def __post_init__(self) -> None:
        operation_id = _identifier(self.operation_id, "operation_id")
        setup_id = _identifier(self.setup_id, "setup_id")
        name = _identifier(self.name, "name")
        operation_type = str(self.operation_type).strip().lower()
        if operation_type not in _PLANAR_OPERATION_TYPES:
            raise ValueError(f"unsupported Planar operation_type: {operation_type!r}")
        try:
            state = self.state if isinstance(self.state, NodeState) else NodeState(str(self.state))
        except ValueError as exc:
            raise ValueError(f"unsupported operation state: {self.state!r}") from exc
        if not isinstance(self.geometry, PlanarGeometrySelection):
            raise TypeError("geometry must be PlanarGeometrySelection")
        if not isinstance(self.parameters, PlanarProcessParameters):
            raise TypeError("parameters must be PlanarProcessParameters")
        reasons = tuple(_identifier(reason, "dirty_reasons") for reason in self.dirty_reasons)
        if len(set(reasons)) != len(reasons):
            raise ValueError("dirty_reasons contains duplicate values")
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "setup_id", setup_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "operation_type", operation_type)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "dirty_reasons", reasons)
        object.__setattr__(self, "enabled", require_bool(self.enabled, field_name="enabled"))

    def mark_dirty(self, reason: str) -> "PlanarOperationDefinition":
        clean_reason = _identifier(reason, "reason")
        reasons = self.dirty_reasons
        if clean_reason not in reasons:
            reasons += (clean_reason,)
        return replace(self, state=NodeState.DIRTY, dirty_reasons=reasons)

    def semantic_hash_input(self) -> dict[str, Any]:
        """Return only values whose change makes a generated path stale."""

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
    def from_json(cls, payload: Mapping[str, Any]) -> "PlanarOperationDefinition":
        if not isinstance(payload, Mapping):
            raise ValueError("Planar operation payload must be an object")
        operation_type = str(payload.get("operation_type", "planar_region"))
        return cls(
            operation_id=str(payload.get("operation_id", "")),
            setup_id=str(payload.get("setup_id", "")),
            name=str(payload.get("name", _default_name(operation_type))),
            operation_type=operation_type,
            state=NodeState(str(payload.get("state", NodeState.DIRTY.value))),
            dirty_reasons=tuple(payload.get("dirty_reasons", ())),
            enabled=parse_json_bool(
                payload, "enabled", default=True, field_name="planar_operation.enabled"
            ),
            geometry=PlanarGeometrySelection.from_json(payload.get("geometry", {})),
            parameters=PlanarProcessParameters.from_json(payload.get("parameters", {})),
        )


def planar_operation_semantic_hash_input(operation: PlanarOperationDefinition) -> dict[str, Any]:
    if not isinstance(operation, PlanarOperationDefinition):
        raise TypeError("operation must be PlanarOperationDefinition")
    return operation.semantic_hash_input()


def planar_operation_semantic_sha256(operation: PlanarOperationDefinition) -> str:
    return hashlib.sha256(
        canonical_json_bytes(planar_operation_semantic_hash_input(operation))
    ).hexdigest()


def _finite_float(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    if value > 100:
        raise ValueError(f"{name} must not exceed 100")
    return value


def _validate_common_parameters(values: Mapping[str, float], spiral_samples: int) -> None:
    for name in (
        "layer_height_mm",
        "bead_width_mm",
        "feedrate_mm_min",
        "line_spacing_mm",
        "travel_feedrate_mm_min",
        "retract_length_mm",
        "wall_thickness_mm",
    ):
        if values[name] <= 0.0:
            raise ValueError(f"{name} must be greater than zero")
    if spiral_samples < 8:
        raise ValueError("spiral_samples_per_contour must be at least 8")
    if values["last_layer_z_mm"] < values["first_layer_z_mm"]:
        raise ValueError("last_layer_z_mm must not be below first_layer_z_mm")
    if values["layer_height_mm"] > values["bead_width_mm"] * 2.0:
        raise ValueError("layer_height_mm exceeds the supported bead aspect ratio")


def _validate_support_parameters(values: Mapping[str, float], pattern: str) -> None:
    if not 0.0 < values["support_overhang_angle_deg"] < 90.0:
        raise ValueError("support_overhang_angle_deg must be between 0 and 90")
    for name in ("support_xy_gap_mm", "support_z_gap_mm"):
        if values[name] < 0.0:
            raise ValueError(f"{name} must not be negative")
    for name in ("support_line_spacing_mm", "support_interface_spacing_mm"):
        if values[name] <= 0.0:
            raise ValueError(f"{name} must be greater than zero")
    if pattern not in {"lines", "grid"}:
        raise ValueError("support_pattern must be 'lines' or 'grid'")


def _identifier(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise ValueError(f"{name} must not be empty")
    return result


def _default_name(operation_type: str) -> str:
    return {
        "planar_region": "Planar Region",
        "planar_zigzag": "Planar Zigzag",
        "planar_offset": "Planar Offset",
        "planar_thin_wall": "Planar Thin Wall",
        "planar_spiral": "Planar Spiral",
        "planar_support": "Planar Support",
    }.get(str(operation_type).strip().lower(), "Planar Region")


__all__ = [
    "PlanarGeometrySelection",
    "PlanarOperationDefinition",
    "PlanarProcessParameters",
    "planar_operation_semantic_hash_input",
    "planar_operation_semantic_sha256",
]
