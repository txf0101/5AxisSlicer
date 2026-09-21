"""Persisted contract for the bounded paper-core Freeform operation."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import math
from typing import Any, Mapping

from .coordinates import GeometryReference
from .curve_parameters import CurveGeometrySelection
from .freeform_solid_parameters import (
    SOLID_FILL_OPERATION_TYPES,
    SolidFillGeometrySelection,
    SolidFillProcessParameters,
    solid_geometry_from_json,
)
from .json_contract import parse_json_bool, require_bool
from .material_plan import MaterialPlan
from .resources import canonical_json_bytes
from .setup import NodeState


FREEFORM_OPERATION_TYPES = frozenset(
    {"freeform_surface", "freeform_thin_wall", *SOLID_FILL_OPERATION_TYPES}
)


@dataclass(frozen=True, slots=True)
class FreeformGeometrySelection:
    """One trimmed face or a small explicit face group with guide chains."""

    faces: tuple[GeometryReference, ...] = ()
    guides: tuple[CurveGeometrySelection, ...] = ()

    def __post_init__(self) -> None:
        faces, guides = tuple(self.faces), tuple(self.guides)
        if len(faces) > 16 or len(guides) > 32:
            raise ValueError("restricted Freeform accepts at most 16 faces and 32 guides")
        if any(
            not isinstance(item, GeometryReference) or item.geometry_type != "face"
            for item in faces
        ):
            raise ValueError("faces must contain face GeometryReference values")
        if any(not isinstance(item, CurveGeometrySelection) for item in guides):
            raise TypeError("guides must contain CurveGeometrySelection values")
        ids = [item.object_id for item in faces]
        if len(set(ids)) != len(ids):
            raise ValueError("faces contain duplicate references")
        allowed = set(ids)
        for guide in guides:
            if guide.normal_mode != "adjacent_face" or guide.normal_face is None:
                raise ValueError("Freeform guides require an explicit adjacent normal face")
            if guide.normal_face.object_id not in allowed:
                raise ValueError("every guide normal face must belong to the selected face group")
        object.__setattr__(self, "faces", faces)
        object.__setattr__(self, "guides", guides)

    @property
    def is_complete(self) -> bool:
        return bool(self.faces and self.guides) and all(item.is_complete for item in self.guides)

    def to_json(self) -> dict[str, Any]:
        return {
            "faces": [item.to_json() for item in self.faces],
            "guides": [item.to_json() for item in self.guides],
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "FreeformGeometrySelection":
        if not isinstance(payload, Mapping):
            raise ValueError("Freeform geometry payload must be an object")
        return cls(
            tuple(GeometryReference.from_json(item) for item in payload.get("faces", ())),
            tuple(CurveGeometrySelection.from_json(item) for item in payload.get("guides", ())),
        )


@dataclass(frozen=True, slots=True)
class FreeformProcessParameters:
    sampling_step_mm: float = 1.0
    chord_error_mm: float = 0.05
    chain_tolerance_mm: float = 0.01
    bead_width_mm: float = 0.4
    layer_height_mm: float = 0.2
    path_spacing_mm: float = 0.4
    path_count: int = 1
    layer_count: int = 1
    feedrate_mm_min: float = 9000.0
    travel_feedrate_mm_min: float = 3000.0
    retract_length_mm: float = 1.0
    maximum_normal_change_rad: float = math.radians(10.0)

    def __post_init__(self) -> None:
        for name in (
            "sampling_step_mm",
            "chord_error_mm",
            "chain_tolerance_mm",
            "bead_width_mm",
            "layer_height_mm",
            "path_spacing_mm",
            "feedrate_mm_min",
            "travel_feedrate_mm_min",
            "retract_length_mm",
            "maximum_normal_change_rad",
        ):
            value = _finite(getattr(self, name), name)
            if name == "retract_length_mm":
                if value < 0.0:
                    raise ValueError("retract_length_mm must be non-negative")
            elif value <= 0.0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)
        for name, limit in (("path_count", 64), ("layer_count", 32)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= limit:
                raise ValueError(f"{name} must be an integer in [1, {limit}]")
        if self.layer_height_mm > self.bead_width_mm * 2.0:
            raise ValueError("layer height exceeds the supported bead aspect ratio")
        if self.maximum_normal_change_rad > math.pi / 2.0:
            raise ValueError("maximum_normal_change_rad must not exceed pi/2")

    def to_json(self) -> dict[str, float | int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "FreeformProcessParameters":
        if not isinstance(payload, Mapping):
            raise ValueError("Freeform parameters must be an object")
        defaults = cls()
        return cls(
            **{
                name: payload.get(name, getattr(defaults, name))
                for name in cls.__dataclass_fields__
            }
        )


@dataclass(frozen=True, slots=True)
class FreeformOperationDefinition:
    operation_id: str
    setup_id: str
    name: str = "Freeform Surface"
    operation_type: str = "freeform_surface"
    state: NodeState = NodeState.DIRTY
    dirty_reasons: tuple[str, ...] = ()
    enabled: bool = True
    geometry: FreeformGeometrySelection = field(default_factory=FreeformGeometrySelection)
    parameters: FreeformProcessParameters = field(default_factory=FreeformProcessParameters)
    material_plan: MaterialPlan | None = None
    solid_geometry: SolidFillGeometrySelection | None = None
    solid_parameters: SolidFillProcessParameters | None = None

    def __post_init__(self) -> None:
        for name in ("operation_id", "setup_id", "name"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must not be empty")
            object.__setattr__(self, name, value)
        operation_type = str(self.operation_type).strip().lower()
        if operation_type not in FREEFORM_OPERATION_TYPES:
            raise ValueError(f"unsupported Freeform operation_type: {operation_type}")
        state = self.state if isinstance(self.state, NodeState) else NodeState(str(self.state))
        if not isinstance(self.geometry, FreeformGeometrySelection):
            raise TypeError("geometry must be FreeformGeometrySelection")
        if not isinstance(self.parameters, FreeformProcessParameters):
            raise TypeError("parameters must be FreeformProcessParameters")
        if self.material_plan is not None and not isinstance(self.material_plan, MaterialPlan):
            raise TypeError("material_plan must be MaterialPlan or None")
        is_solid = operation_type in SOLID_FILL_OPERATION_TYPES
        if is_solid:
            if (
                self.solid_geometry is not None
                and self.solid_geometry.to_json()["operation_type"] != operation_type
            ):
                raise ValueError("solid geometry type must match operation_type")
            if self.solid_parameters is None:
                object.__setattr__(self, "solid_parameters", SolidFillProcessParameters())
        elif self.solid_geometry is not None or self.solid_parameters is not None:
            raise ValueError("guide-driven Freeform operations cannot contain solid-fill inputs")
        reasons = tuple(str(item).strip() for item in self.dirty_reasons)
        if any(not item for item in reasons) or len(set(reasons)) != len(reasons):
            raise ValueError("dirty_reasons must contain unique nonempty values")
        object.__setattr__(self, "operation_type", operation_type)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "dirty_reasons", reasons)
        object.__setattr__(self, "enabled", require_bool(self.enabled, field_name="enabled"))

    def mark_dirty(self, reason: str) -> "FreeformOperationDefinition":
        clean = str(reason).strip()
        if not clean:
            raise ValueError("reason must not be empty")
        reasons = (
            self.dirty_reasons if clean in self.dirty_reasons else (*self.dirty_reasons, clean)
        )
        return replace(self, state=NodeState.DIRTY, dirty_reasons=reasons)

    def semantic_hash_input(self) -> dict[str, Any]:
        payload = {
            "operation_id": self.operation_id,
            "name": self.name,
            "operation_type": self.operation_type,
            "enabled": self.enabled,
            "geometry": self.geometry.to_json(),
            "parameters": self.parameters.to_json(),
            "material_plan": None if self.material_plan is None else self.material_plan.to_json(),
        }
        if self.operation_type in SOLID_FILL_OPERATION_TYPES:
            payload.update(
                solid_geometry=(
                    None if self.solid_geometry is None else self.solid_geometry.to_json()
                ),
                solid_parameters=self.solid_parameters.to_json(),  # type: ignore[union-attr]
            )
        return payload

    def semantic_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.semantic_hash_input())).hexdigest()

    def to_json(self) -> dict[str, Any]:
        return {
            **self.semantic_hash_input(),
            "setup_id": self.setup_id,
            "state": self.state.value,
            "dirty_reasons": list(self.dirty_reasons),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "FreeformOperationDefinition":
        if not isinstance(payload, Mapping):
            raise ValueError("Freeform operation payload must be an object")
        material = payload.get("material_plan")
        operation_type = str(payload.get("operation_type", "freeform_surface"))
        solid_geometry = payload.get("solid_geometry")
        solid_parameters = payload.get("solid_parameters")
        return cls(
            str(payload.get("operation_id", "")),
            str(payload.get("setup_id", "")),
            str(payload.get("name", "Freeform Surface")),
            operation_type,
            NodeState(str(payload.get("state", NodeState.DIRTY.value))),
            tuple(payload.get("dirty_reasons", ())),
            parse_json_bool(payload, "enabled", default=True),
            FreeformGeometrySelection.from_json(payload.get("geometry", {})),
            FreeformProcessParameters.from_json(payload.get("parameters", {})),
            None if material is None else MaterialPlan.from_json(material),
            (
                None
                if solid_geometry is None
                else solid_geometry_from_json(solid_geometry)
            ),
            (
                None
                if operation_type not in SOLID_FILL_OPERATION_TYPES
                else SolidFillProcessParameters.from_json(solid_parameters or {})
            ),
        )


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


__all__ = [
    "FREEFORM_OPERATION_TYPES",
    "FreeformGeometrySelection",
    "FreeformOperationDefinition",
    "FreeformProcessParameters",
]
