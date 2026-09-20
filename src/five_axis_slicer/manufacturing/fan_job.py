"""Manufacturing contract and dependency graph for the complete fan program.

The contract is intentionally limited to the first fan closed loop.  It keeps
paper-derived values, engineering defaults, and machine measurements separate
so an offline-qualified job cannot accidentally be presented as machine-ready.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from .coordinates import GeometryReference, RigidTransform
from .json_contract import parse_json_bool
from .resources import canonical_json_bytes

FAN_JOB_SCHEMA_VERSION = 1


class ParameterSource(str, Enum):
    PAPER = "paper"
    ENGINEERING_DEFAULT = "engineering_default"
    USER = "user"
    MEASURED = "measured"
    PENDING_MEASUREMENT = "pending_measurement"


@dataclass(frozen=True, slots=True)
class SourcedValue:
    value: Any
    source: ParameterSource | str
    note: str = ""

    def __post_init__(self) -> None:
        source = (
            self.source
            if isinstance(self.source, ParameterSource)
            else ParameterSource(self.source)
        )
        object.__setattr__(self, "source", source)

    def to_json(self) -> dict[str, Any]:
        source = (
            self.source
            if isinstance(self.source, ParameterSource)
            else ParameterSource(self.source)
        )
        return {"value": self.value, "source": source.value, "note": self.note}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "SourcedValue":
        return cls(
            payload.get("value"), str(payload.get("source", "")), str(payload.get("note", ""))
        )


@dataclass(frozen=True, slots=True)
class FanProcessParameters:
    nozzle_diameter_mm: float = 0.4
    filament_diameter_mm: float = 1.75
    layer_height_mm: float = 0.2
    bead_width_mm: float = 0.4
    deposition_feedrate_mm_min: float = 1200.0
    travel_feedrate_mm_min: float = 3000.0
    nozzle_temperature_c: float = 205.0
    bed_temperature_c: float = 60.0
    retract_length_mm: float = 1.0
    wall_count: int = 2
    top_solid_thickness_mm: float = 0.8
    bottom_solid_thickness_mm: float = 0.8
    base_infill_fraction: float = 0.2
    blade_infill_fraction: float = 1.0
    indexing_a_deg: float = 90.0
    indexing_machine_z_mm: float = 20.0
    a_limit_deg: tuple[float, float] = (-180.0, 180.0)
    c_limit_deg: tuple[float, float] = (-360.0, 360.0)
    chord_error_mm: float = 0.02
    fk_position_tolerance_mm: float = 0.001
    fk_angle_tolerance_deg: float = 0.001

    def __post_init__(self) -> None:
        positive = (
            "nozzle_diameter_mm",
            "filament_diameter_mm",
            "layer_height_mm",
            "bead_width_mm",
            "deposition_feedrate_mm_min",
            "travel_feedrate_mm_min",
            "retract_length_mm",
            "top_solid_thickness_mm",
            "bottom_solid_thickness_mm",
            "chord_error_mm",
            "fk_position_tolerance_mm",
            "fk_angle_tolerance_deg",
        )
        for name in positive:
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        if isinstance(self.wall_count, bool) or self.wall_count < 1:
            raise ValueError("wall_count must be a positive integer")
        for name in ("base_infill_fraction", "blade_infill_fraction"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between zero and one")
        for name in ("a_limit_deg", "c_limit_deg"):
            lower, upper = getattr(self, name)
            if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
                raise ValueError(f"{name} must be an increasing finite interval")
        if not self.a_limit_deg[0] <= self.indexing_a_deg <= self.a_limit_deg[1]:
            raise ValueError("indexing_a_deg lies outside the configured A range")

    def to_json(self) -> dict[str, Any]:
        result = {name: getattr(self, name) for name in self.__dataclass_fields__}
        result["a_limit_deg"] = list(self.a_limit_deg)
        result["c_limit_deg"] = list(self.c_limit_deg)
        return result

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "FanProcessParameters":
        defaults = cls()
        values = {
            name: payload.get(name, getattr(defaults, name)) for name in cls.__dataclass_fields__
        }
        values["a_limit_deg"] = tuple(values["a_limit_deg"])
        values["c_limit_deg"] = tuple(values["c_limit_deg"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class FanGeometrySelection:
    hub: GeometryReference
    blades: tuple[GeometryReference, GeometryReference, GeometryReference]

    def __post_init__(self) -> None:
        references = (self.hub, *self.blades)
        if any(item.geometry_type != "body" for item in references):
            raise ValueError("fan geometry must contain body references")
        if len({item.object_id for item in references}) != 4:
            raise ValueError("hub and three blades must be distinct")

    def to_json(self) -> dict[str, Any]:
        return {"hub": self.hub.to_json(), "blades": [item.to_json() for item in self.blades]}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "FanGeometrySelection":
        blades = tuple(GeometryReference.from_json(item) for item in payload.get("blades", ()))
        if len(blades) != 3:
            raise ValueError("fan geometry requires exactly three blades")
        return cls(GeometryReference.from_json(payload["hub"]), blades)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class FanManufacturingContract:
    contract_id: str
    source_sha256: str
    geometry: FanGeometrySelection
    source_to_build: RigidTransform
    parameters: FanProcessParameters = field(default_factory=FanProcessParameters)
    controller_profile_id: str = "own-ac-offline-reference"
    material_profile_id: str = "generic-pla-175"
    material_channel_id: str = "T0"
    parameter_sources: Mapping[str, SourcedValue] = field(default_factory=dict, hash=False)
    machine_measurements_complete: bool = False

    def __post_init__(self) -> None:
        if not self.contract_id.strip():
            raise ValueError("contract_id must not be empty")
        digest = self.source_sha256.strip().lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("source_sha256 must contain 64 lowercase hex digits")
        if (
            self.source_to_build.source_frame != "source"
            or self.source_to_build.target_frame != "build"
        ):
            raise ValueError(
                "source_to_build must transform source coordinates to build coordinates"
            )
        sources = dict(self.parameter_sources)
        if any(not isinstance(item, SourcedValue) for item in sources.values()):
            raise TypeError("parameter_sources values must be SourcedValue objects")
        object.__setattr__(self, "source_sha256", digest)
        object.__setattr__(self, "parameter_sources", sources)

    @property
    def offline_ready(self) -> bool:
        return True

    @property
    def machine_ready(self) -> bool:
        return self.machine_measurements_complete

    def semantic_hash_input(self) -> dict[str, Any]:
        return {
            "schema_version": FAN_JOB_SCHEMA_VERSION,
            "contract_id": self.contract_id,
            "source_sha256": self.source_sha256,
            "geometry": self.geometry.to_json(),
            "source_to_build": self.source_to_build.to_json(),
            "parameters": self.parameters.to_json(),
            "controller_profile_id": self.controller_profile_id,
            "material_profile_id": self.material_profile_id,
            "material_channel_id": self.material_channel_id,
            "parameter_sources": {
                key: value.to_json() for key, value in sorted(self.parameter_sources.items())
            },
            "machine_measurements_complete": self.machine_measurements_complete,
        }

    def semantic_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.semantic_hash_input())).hexdigest()

    def to_json(self) -> dict[str, Any]:
        return self.semantic_hash_input()

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "FanManufacturingContract":
        return cls(
            contract_id=str(payload.get("contract_id", "")),
            source_sha256=str(payload.get("source_sha256", "")),
            geometry=FanGeometrySelection.from_json(payload.get("geometry", {})),
            source_to_build=RigidTransform.from_json(payload.get("source_to_build", {})),
            parameters=FanProcessParameters.from_json(payload.get("parameters", {})),
            controller_profile_id=str(payload.get("controller_profile_id", "")),
            material_profile_id=str(payload.get("material_profile_id", "")),
            material_channel_id=str(payload.get("material_channel_id", "")),
            parameter_sources={
                key: SourcedValue.from_json(value)
                for key, value in payload.get("parameter_sources", {}).items()
            },
            machine_measurements_complete=parse_json_bool(
                payload,
                "machine_measurements_complete",
                default=False,
                field_name="fan_contract.machine_measurements_complete",
            ),
        )


class FanOperationState(str, Enum):
    DIRTY = "dirty"
    GENERATING = "generating"
    READY = "ready"
    ERROR = "error"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class FanJobOperation:
    operation_id: str
    operation_type: str
    dependencies: tuple[str, ...] = ()
    state: FanOperationState | str = FanOperationState.DIRTY
    result_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.operation_id.strip() or not self.operation_type.strip():
            raise ValueError("operation identifiers must not be empty")
        if self.operation_id in self.dependencies or len(set(self.dependencies)) != len(
            self.dependencies
        ):
            raise ValueError("dependencies must be unique and cannot contain the operation itself")
        state = (
            self.state
            if isinstance(self.state, FanOperationState)
            else FanOperationState(self.state)
        )
        object.__setattr__(self, "state", state)

    def to_json(self) -> dict[str, Any]:
        state = (
            self.state
            if isinstance(self.state, FanOperationState)
            else FanOperationState(self.state)
        )
        return {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "dependencies": list(self.dependencies),
            "state": state.value,
            "result_sha256": self.result_sha256,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "FanJobOperation":
        return cls(
            str(payload.get("operation_id", "")),
            str(payload.get("operation_type", "")),
            tuple(payload.get("dependencies", ())),
            str(payload.get("state", "dirty")),
            payload.get("result_sha256"),
        )


@dataclass(frozen=True, slots=True)
class FanManufacturingJob:
    job_id: str
    contract_sha256: str
    operations: tuple[FanJobOperation, ...]

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id must not be empty")
        operation_map = {item.operation_id: item for item in self.operations}
        if len(operation_map) != len(self.operations):
            raise ValueError("operation_id values must be unique")
        missing = sorted(
            {dep for item in self.operations for dep in item.dependencies} - operation_map.keys()
        )
        if missing:
            raise ValueError(f"missing dependencies: {', '.join(missing)}")
        self.topological_order()

    def topological_order(self) -> tuple[str, ...]:
        remaining = {item.operation_id: set(item.dependencies) for item in self.operations}
        ordered: list[str] = []
        while remaining:
            ready = sorted(key for key, dependencies in remaining.items() if not dependencies)
            if not ready:
                raise ValueError("operation graph contains a cycle")
            ordered.extend(ready)
            for key in ready:
                del remaining[key]
            for dependencies in remaining.values():
                dependencies.difference_update(ready)
        return tuple(ordered)

    def affected_operations(self, changed: tuple[str, ...]) -> tuple[str, ...]:
        unknown = set(changed) - {item.operation_id for item in self.operations}
        if unknown:
            raise ValueError(f"unknown changed operations: {', '.join(sorted(unknown))}")
        affected = set(changed)
        progress = True
        while progress:
            progress = False
            for item in self.operations:
                if item.operation_id not in affected and affected.intersection(item.dependencies):
                    affected.add(item.operation_id)
                    progress = True
        return tuple(item for item in self.topological_order() if item in affected)

    def semantic_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_json())).hexdigest()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": FAN_JOB_SCHEMA_VERSION,
            "job_id": self.job_id,
            "contract_sha256": self.contract_sha256,
            "operations": [item.to_json() for item in self.operations],
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "FanManufacturingJob":
        if int(payload.get("schema_version", 0)) != FAN_JOB_SCHEMA_VERSION:
            raise ValueError("unsupported fan job schema_version")
        return cls(
            str(payload.get("job_id", "")),
            str(payload.get("contract_sha256", "")),
            tuple(FanJobOperation.from_json(item) for item in payload.get("operations", ())),
        )


class FanJobPublication:
    """Atomic publication slot; cancellation retains the last valid result."""

    def __init__(self, published_sha256: str | None = None) -> None:
        self.published_sha256 = published_sha256
        self._candidate: str | None = None

    def stage(self, candidate_sha256: str) -> None:
        self._candidate = candidate_sha256

    def cancel(self) -> None:
        self._candidate = None

    def commit(self) -> str:
        if self._candidate is None:
            raise ValueError("no candidate result has been staged")
        self.published_sha256 = self._candidate
        self._candidate = None
        return self.published_sha256


__all__ = [
    "FAN_JOB_SCHEMA_VERSION",
    "FanGeometrySelection",
    "FanJobOperation",
    "FanJobPublication",
    "FanManufacturingContract",
    "FanManufacturingJob",
    "FanOperationState",
    "FanProcessParameters",
    "ParameterSource",
    "SourcedValue",
]
