"""Generated toolpath and result contracts.

Generated additive paths are expressed in the workpiece build frame.  Linear
values are millimetres, angles are radians, feed rates are millimetres per
minute, and machine-axis conversion is a later kinematics step.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from .json_contract import parse_json_bool, require_bool

if TYPE_CHECKING:
    from ..gcode_preview import GCodePathSegment

TOOLPATH_SCHEMA_VERSION = 1
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_POINT_TYPES = frozenset(
    {
        "deposition",
        "travel",
        "retract",
        "prime",
        "dwell",
        "approach",
        "depart",
    }
)
_EXTRUSION_ROLES = frozenset(
    {
        "none",
        "thin_wall",
        "buildup",
        "skin",
        "infill",
        "support",
        "custom",
    }
)
_RESULT_STATUSES = frozenset({"draft", "ready", "warning", "error", "stale"})
_PREVIEW_MOVE_TYPES = {
    "deposition": "extrude",
    "travel": "travel",
    "retract": "retract",
    "prime": "prime",
    "dwell": "noop",
    "approach": "travel",
    "depart": "travel",
}
_PREVIEW_EXTRUSION_ROLES = {
    "none": "unknown",
    "thin_wall": "external_perimeter",
    "buildup": "solid_infill",
    "skin": "top_solid_infill",
    "infill": "internal_infill",
    "support": "support_material",
    "custom": "custom",
}


class GeneratedToolpathError(ValueError):
    """Raised when generated toolpath payloads violate the public contract."""


class GeneratedResultStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    WARNING = "warning"
    ERROR = "error"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class SourceFingerprint:
    """Content identity for a generated result input or algorithm resource."""

    source_id: str
    sha256: str
    role: str
    path: str = ""

    def __post_init__(self) -> None:
        source_id = _clean_identifier(self.source_id, "source_id")
        role = _clean_identifier(self.role, "role")
        sha256 = str(self.sha256).strip().lower()
        if not _SHA256_RE.fullmatch(sha256):
            raise GeneratedToolpathError("sha256 must contain 64 lowercase hex digits")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "sha256", sha256)
        object.__setattr__(self, "path", str(self.path))

    def to_json(self) -> dict[str, str]:
        return {
            "source_id": self.source_id,
            "sha256": self.sha256,
            "role": self.role,
            "path": self.path,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> SourceFingerprint:
        if not isinstance(payload, Mapping):
            raise GeneratedToolpathError("source fingerprint must be an object")
        return cls(
            source_id=str(payload.get("source_id", "")),
            sha256=str(payload.get("sha256", "")),
            role=str(payload.get("role", "")),
            path=str(payload.get("path", "")),
        )


@dataclass(frozen=True, slots=True)
class ToolpathPoint:
    """One generated path point in workpiece build coordinates."""

    point_id: str
    position: tuple[float, float, float]
    tangent: tuple[float, float, float]
    nozzle_axis: tuple[float, float, float]
    operation_id: str
    stage_id: str
    layer_id: str
    region_id: str
    point_type: str
    extrusion_role: str = "none"
    surface_normal: tuple[float, float, float] | None = None
    feedrate_mm_min: float | None = None
    bead_width_mm: float | None = None
    layer_height_mm: float | None = None
    material_volume_mm3: float = 0.0
    issue_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "point_id", _clean_identifier(self.point_id, "point_id"))
        for field_name in ("operation_id", "stage_id", "layer_id", "region_id"):
            object.__setattr__(
                self,
                field_name,
                _clean_identifier(getattr(self, field_name), field_name),
            )
        point_type = str(self.point_type).strip().lower()
        extrusion_role = str(self.extrusion_role).strip().lower()
        if point_type not in _POINT_TYPES:
            raise GeneratedToolpathError(f"unsupported point_type: {point_type}")
        if extrusion_role not in _EXTRUSION_ROLES:
            raise GeneratedToolpathError(f"unsupported extrusion_role: {extrusion_role}")
        position = _vector3(self.position, "position")
        tangent = _unit_vector3(self.tangent, "tangent")
        nozzle_axis = _unit_vector3(self.nozzle_axis, "nozzle_axis")
        normal = (
            None
            if self.surface_normal is None
            else _unit_vector3(
                self.surface_normal,
                "surface_normal",
            )
        )
        feedrate = _optional_positive(self.feedrate_mm_min, "feedrate_mm_min")
        bead_width = _optional_positive(self.bead_width_mm, "bead_width_mm")
        layer_height = _optional_positive(self.layer_height_mm, "layer_height_mm")
        material_volume = _non_negative_finite(
            self.material_volume_mm3,
            "material_volume_mm3",
        )
        if point_type == "deposition" and extrusion_role == "none":
            raise GeneratedToolpathError("deposition points require an extrusion_role")
        if point_type != "deposition" and material_volume > 0.0:
            raise GeneratedToolpathError("non-deposition points cannot carry material volume")
        issue_ids = _unique_identifiers(self.issue_ids, "issue_ids")
        object.__setattr__(self, "point_type", point_type)
        object.__setattr__(self, "extrusion_role", extrusion_role)
        object.__setattr__(self, "position", position)
        object.__setattr__(self, "tangent", tangent)
        object.__setattr__(self, "nozzle_axis", nozzle_axis)
        object.__setattr__(self, "surface_normal", normal)
        object.__setattr__(self, "feedrate_mm_min", feedrate)
        object.__setattr__(self, "bead_width_mm", bead_width)
        object.__setattr__(self, "layer_height_mm", layer_height)
        object.__setattr__(self, "material_volume_mm3", material_volume)
        object.__setattr__(self, "issue_ids", issue_ids)

    def to_json(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "position": list(self.position),
            "surface_normal": None if self.surface_normal is None else list(self.surface_normal),
            "tangent": list(self.tangent),
            "nozzle_axis": list(self.nozzle_axis),
            "feedrate_mm_min": self.feedrate_mm_min,
            "bead_width_mm": self.bead_width_mm,
            "layer_height_mm": self.layer_height_mm,
            "material_volume_mm3": self.material_volume_mm3,
            "operation_id": self.operation_id,
            "stage_id": self.stage_id,
            "layer_id": self.layer_id,
            "region_id": self.region_id,
            "point_type": self.point_type,
            "extrusion_role": self.extrusion_role,
            "issue_ids": list(self.issue_ids),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> ToolpathPoint:
        if not isinstance(payload, Mapping):
            raise GeneratedToolpathError("toolpath point must be an object")
        return cls(
            point_id=str(payload.get("point_id", "")),
            position=_json_vector3(payload.get("position"), "position"),
            surface_normal=_optional_json_vector3(payload.get("surface_normal"), "surface_normal"),
            tangent=_json_vector3(payload.get("tangent"), "tangent"),
            nozzle_axis=_json_vector3(payload.get("nozzle_axis"), "nozzle_axis"),
            feedrate_mm_min=_optional_float(payload.get("feedrate_mm_min")),
            bead_width_mm=_optional_float(payload.get("bead_width_mm")),
            layer_height_mm=_optional_float(payload.get("layer_height_mm")),
            material_volume_mm3=float(payload.get("material_volume_mm3", 0.0)),
            operation_id=str(payload.get("operation_id", "")),
            stage_id=str(payload.get("stage_id", "")),
            layer_id=str(payload.get("layer_id", "")),
            region_id=str(payload.get("region_id", "")),
            point_type=str(payload.get("point_type", "")),
            extrusion_role=str(payload.get("extrusion_role", "none")),
            issue_ids=tuple(payload.get("issue_ids", ())),
        )


@dataclass(frozen=True, slots=True)
class ToolpathEvent:
    """Discrete non-geometric event in the generated manufacturing sequence."""

    event_id: str
    event_type: str
    operation_id: str
    stage_id: str
    layer_id: str | None = None
    region_id: str | None = None
    duration_s: float | None = None
    context: Mapping[str, Any] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        event_id = _clean_identifier(self.event_id, "event_id")
        event_type = _clean_identifier(self.event_type, "event_type").lower()
        operation_id = _clean_identifier(self.operation_id, "operation_id")
        stage_id = _clean_identifier(self.stage_id, "stage_id")
        layer_id = _optional_identifier(self.layer_id, "layer_id")
        region_id = _optional_identifier(self.region_id, "region_id")
        duration = _optional_non_negative(self.duration_s, "duration_s")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "stage_id", stage_id)
        object.__setattr__(self, "layer_id", layer_id)
        object.__setattr__(self, "region_id", region_id)
        object.__setattr__(self, "duration_s", duration)
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))

    def to_json(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "operation_id": self.operation_id,
            "stage_id": self.stage_id,
            "layer_id": self.layer_id,
            "region_id": self.region_id,
            "duration_s": self.duration_s,
            "context": dict(self.context),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> ToolpathEvent:
        if not isinstance(payload, Mapping):
            raise GeneratedToolpathError("toolpath event must be an object")
        context = payload.get("context", {})
        if not isinstance(context, Mapping):
            raise GeneratedToolpathError("toolpath event context must be an object")
        return cls(
            event_id=str(payload.get("event_id", "")),
            event_type=str(payload.get("event_type", "")),
            operation_id=str(payload.get("operation_id", "")),
            stage_id=str(payload.get("stage_id", "")),
            layer_id=_optional_string(payload.get("layer_id")),
            region_id=_optional_string(payload.get("region_id")),
            duration_s=_optional_float(payload.get("duration_s")),
            context=context,
        )


@dataclass(frozen=True, slots=True)
class GeneratedToolpath:
    """Serializable path payload produced before machine-axis solving."""

    toolpath_id: str
    operation_id: str
    coordinate_frame: str = "workpiece_build"
    points: tuple[ToolpathPoint, ...] = ()
    events: tuple[ToolpathEvent, ...] = ()

    def __post_init__(self) -> None:
        toolpath_id = _clean_identifier(self.toolpath_id, "toolpath_id")
        operation_id = _clean_identifier(self.operation_id, "operation_id")
        coordinate_frame = _clean_identifier(self.coordinate_frame, "coordinate_frame")
        points = tuple(self.points)
        events = tuple(self.events)
        if any(not isinstance(point, ToolpathPoint) for point in points):
            raise TypeError("points must contain ToolpathPoint objects")
        if any(not isinstance(event, ToolpathEvent) for event in events):
            raise TypeError("events must contain ToolpathEvent objects")
        for point in points:
            if point.operation_id != operation_id:
                raise GeneratedToolpathError("point operation_id must match toolpath operation_id")
        for event in events:
            if event.operation_id != operation_id:
                raise GeneratedToolpathError("event operation_id must match toolpath operation_id")
        _require_unique((point.point_id for point in points), "point_id")
        _require_unique((event.event_id for event in events), "event_id")
        object.__setattr__(self, "toolpath_id", toolpath_id)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "coordinate_frame", coordinate_frame)
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "events", events)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": TOOLPATH_SCHEMA_VERSION,
            "toolpath_id": self.toolpath_id,
            "operation_id": self.operation_id,
            "coordinate_frame": self.coordinate_frame,
            "units": {
                "length": "mm",
                "angle": "rad",
                "feedrate": "mm_min",
                "material_volume": "mm3",
            },
            "points": [point.to_json() for point in self.points],
            "events": [event.to_json() for event in self.events],
        }

    def to_preview_segments(self) -> list[GCodePathSegment]:
        """Adapt geometric moves to the existing result-viewer segment contract.

        The generated path is already in workpiece/build coordinates, so the
        adapter intentionally leaves machine coordinates and rotary axes empty.
        Machine-axis pose preview remains a later kinematics-stage concern.
        """

        # Local import avoids a package initialisation cycle: gcode_preview
        # imports manufacturing preview-kinematics and setup contracts.
        from ..gcode_preview import GCodePathSegment

        layer_numbers: dict[str, int] = {}
        segments: list[GCodePathSegment] = []
        for previous, current in zip(self.points, self.points[1:], strict=False):
            layer = layer_numbers.setdefault(current.layer_id, len(layer_numbers))
            segments.append(
                GCodePathSegment(
                    step_index=len(segments),
                    line_number=0,
                    layer=layer,
                    start=previous.position,
                    end=current.position,
                    move_type=_PREVIEW_MOVE_TYPES[current.point_type],
                    extrusion_role=_PREVIEW_EXTRUSION_ROLES[current.extrusion_role],
                    feedrate=current.feedrate_mm_min,
                    delta_e=current.material_volume_mm3,
                    width=current.bead_width_mm,
                    height=current.layer_height_mm,
                    comment=(
                        f"generated:{current.stage_id}:{current.region_id}:{current.extrusion_role}"
                    ),
                    coordinate_transform=self.coordinate_frame,
                )
            )
        return segments

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> GeneratedToolpath:
        if not isinstance(payload, Mapping):
            raise GeneratedToolpathError("generated toolpath must be an object")
        _require_schema_version(payload, "generated toolpath")
        return cls(
            toolpath_id=str(payload.get("toolpath_id", "")),
            operation_id=str(payload.get("operation_id", "")),
            coordinate_frame=str(payload.get("coordinate_frame", "workpiece_build")),
            points=tuple(ToolpathPoint.from_json(item) for item in payload.get("points", ())),
            events=tuple(ToolpathEvent.from_json(item) for item in payload.get("events", ())),
        )


@dataclass(frozen=True, slots=True)
class GeneratedResultManifest:
    """Top-level generated-result identity and export readiness."""

    result_id: str
    operation_id: str
    status: GeneratedResultStatus | str
    algorithm_version: str
    parameter_semantic_sha256: str
    input_sources: tuple[SourceFingerprint, ...]
    toolpath: GeneratedToolpath
    machine_profile_id: str
    generated_at_utc: str = ""
    ready_for_export: bool = False
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        result_id = _clean_identifier(self.result_id, "result_id")
        operation_id = _clean_identifier(self.operation_id, "operation_id")
        try:
            status = (
                self.status
                if isinstance(self.status, GeneratedResultStatus)
                else GeneratedResultStatus(str(self.status).strip().lower())
            )
        except ValueError as exc:
            raise GeneratedToolpathError(f"unsupported result status: {self.status!r}") from exc
        algorithm_version = _clean_identifier(self.algorithm_version, "algorithm_version")
        parameter_hash = str(self.parameter_semantic_sha256).strip().lower()
        if not _SHA256_RE.fullmatch(parameter_hash):
            raise GeneratedToolpathError("parameter_semantic_sha256 must contain 64 hex digits")
        sources = tuple(self.input_sources)
        if any(not isinstance(source, SourceFingerprint) for source in sources):
            raise TypeError("input_sources must contain SourceFingerprint objects")
        if not isinstance(self.toolpath, GeneratedToolpath):
            raise TypeError("toolpath must be GeneratedToolpath")
        if self.toolpath.operation_id != operation_id:
            raise GeneratedToolpathError("toolpath operation_id must match manifest operation_id")
        machine_profile_id = _clean_identifier(self.machine_profile_id, "machine_profile_id")
        issues = _unique_identifiers(self.issues, "issues")
        ready = require_bool(self.ready_for_export, field_name="ready_for_export")
        if ready and status not in {GeneratedResultStatus.READY, GeneratedResultStatus.WARNING}:
            raise GeneratedToolpathError("only ready or warning results can be exported")
        if ready and not self.toolpath.points:
            raise GeneratedToolpathError("exportable results require at least one toolpath point")
        object.__setattr__(self, "result_id", result_id)
        object.__setattr__(self, "operation_id", operation_id)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "algorithm_version", algorithm_version)
        object.__setattr__(self, "parameter_semantic_sha256", parameter_hash)
        object.__setattr__(self, "input_sources", sources)
        object.__setattr__(self, "machine_profile_id", machine_profile_id)
        object.__setattr__(self, "ready_for_export", ready)
        object.__setattr__(self, "issues", issues)

    def to_json(self) -> dict[str, Any]:
        status = (
            self.status
            if isinstance(self.status, GeneratedResultStatus)
            else (GeneratedResultStatus(str(self.status)))
        )
        return {
            "schema_version": TOOLPATH_SCHEMA_VERSION,
            "result_id": self.result_id,
            "operation_id": self.operation_id,
            "status": status.value,
            "algorithm_version": self.algorithm_version,
            "parameter_semantic_sha256": self.parameter_semantic_sha256,
            "input_sources": [source.to_json() for source in self.input_sources],
            "machine_profile_id": self.machine_profile_id,
            "generated_at_utc": self.generated_at_utc,
            "ready_for_export": self.ready_for_export,
            "issues": list(self.issues),
            "toolpath": self.toolpath.to_json(),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> GeneratedResultManifest:
        if not isinstance(payload, Mapping):
            raise GeneratedToolpathError("generated result manifest must be an object")
        _require_schema_version(payload, "generated result manifest")
        return cls(
            result_id=str(payload.get("result_id", "")),
            operation_id=str(payload.get("operation_id", "")),
            status=str(payload.get("status", "")),
            algorithm_version=str(payload.get("algorithm_version", "")),
            parameter_semantic_sha256=str(payload.get("parameter_semantic_sha256", "")),
            input_sources=tuple(
                SourceFingerprint.from_json(item) for item in payload.get("input_sources", ())
            ),
            machine_profile_id=str(payload.get("machine_profile_id", "")),
            generated_at_utc=str(payload.get("generated_at_utc", "")),
            ready_for_export=parse_json_bool(
                payload,
                "ready_for_export",
                default=False,
                field_name="ready_for_export",
            ),
            issues=tuple(payload.get("issues", ())),
            toolpath=GeneratedToolpath.from_json(payload.get("toolpath", {})),
        )


def _require_schema_version(payload: Mapping[str, Any], name: str) -> None:
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise GeneratedToolpathError(f"{name} schema_version must be {TOOLPATH_SCHEMA_VERSION}")
    if version != TOOLPATH_SCHEMA_VERSION:
        raise GeneratedToolpathError(f"{name} schema_version must be {TOOLPATH_SCHEMA_VERSION}")


def _clean_identifier(value: Any, name: str) -> str:
    result = str(value).strip()
    if not result:
        raise GeneratedToolpathError(f"{name} must not be empty")
    return result


def _optional_identifier(value: Any, name: str) -> str | None:
    if value in (None, ""):
        return None
    return _clean_identifier(value, name)


def _unique_identifiers(values: Iterable[Any], name: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        identifier = _clean_identifier(value, f"{name}[{index}]")
        if identifier not in seen:
            seen.add(identifier)
            result.append(identifier)
    return tuple(result)


def _require_unique(values: Iterable[str], name: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise GeneratedToolpathError(f"duplicate {name}: {', '.join(sorted(duplicates))}")


def _vector3(value: Iterable[float], name: str) -> tuple[float, float, float]:
    try:
        result = tuple(float(component) for component in value)
    except (TypeError, ValueError) as exc:
        raise GeneratedToolpathError(f"{name} must contain three finite values") from exc
    if len(result) != 3 or not all(math.isfinite(component) for component in result):
        raise GeneratedToolpathError(f"{name} must contain three finite values")
    return result  # type: ignore[return-value]


def _unit_vector3(value: Iterable[float], name: str) -> tuple[float, float, float]:
    vector = _vector3(value, name)
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 1.0e-12:
        raise GeneratedToolpathError(f"{name} must not be zero")
    return tuple(component / length for component in vector)  # type: ignore[return-value]


def _json_vector3(value: Any, name: str) -> tuple[float, float, float]:
    return _vector3(value, name)


def _optional_json_vector3(value: Any, name: str) -> tuple[float, float, float] | None:
    return None if value is None else _json_vector3(value, name)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_positive(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise GeneratedToolpathError(f"{name} must be a finite positive number")
    return result


def _optional_non_negative(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    return _non_negative_finite(value, name)


def _non_negative_finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise GeneratedToolpathError(f"{name} must be finite and non-negative")
    return result


__all__ = [
    "GeneratedResultManifest",
    "GeneratedResultStatus",
    "GeneratedToolpath",
    "GeneratedToolpathError",
    "SourceFingerprint",
    "TOOLPATH_SCHEMA_VERSION",
    "ToolpathEvent",
    "ToolpathPoint",
]
