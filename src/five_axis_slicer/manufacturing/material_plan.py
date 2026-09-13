"""Serializable predefined material regions and deterministic channel events.

The paper-core workflow intentionally accepts only explicit region assignments.
It does not infer materials from colour, geometry, or a slicer heuristic.  This
keeps material changes reviewable and makes the generated event chain part of
the operation semantic hash.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import math
from types import MappingProxyType
from typing import Any, Mapping

from .resources import canonical_json_bytes
from .toolpath import GeneratedToolpath, ToolpathEvent


MATERIAL_EVENT_ORDER = (
    "prepare_pause",
    "retract",
    "cut",
    "park",
    "switch",
    "load",
    "temperature_wait",
    "purge",
    "prime",
    "resume",
)


@dataclass(frozen=True, slots=True)
class MaterialChannel:
    channel_id: str
    material_id: str
    tool_command: str
    nozzle_temperature_c: float
    purge_length_mm: float
    load_length_mm: float = 0.0
    retract_length_mm: float = 1.0
    requires_prepare_pause: bool = False

    def __post_init__(self) -> None:
        for name in ("channel_id", "material_id", "tool_command"):
            value = str(getattr(self, name)).strip()
            if not value or any(character.isspace() for character in value):
                raise ValueError(f"{name} must be a nonempty single token")
            object.__setattr__(self, name, value)
        if not self.tool_command.startswith("T") or not self.tool_command[1:].isdigit():
            raise ValueError("tool_command must use the T0..Tn form")
        temperature = _finite(self.nozzle_temperature_c, "nozzle_temperature_c")
        if not 0.0 < temperature <= 500.0:
            raise ValueError("nozzle_temperature_c must be in (0, 500]")
        object.__setattr__(self, "nozzle_temperature_c", temperature)
        for name in ("purge_length_mm", "load_length_mm", "retract_length_mm"):
            numeric_value = _finite(getattr(self, name), name)
            if numeric_value < 0.0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, numeric_value)
        if not isinstance(self.requires_prepare_pause, bool):
            raise TypeError("requires_prepare_pause must be bool")

    def to_json(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "MaterialChannel":
        if not isinstance(payload, Mapping):
            raise ValueError("material channel must be an object")
        return cls(
            channel_id=str(payload.get("channel_id", "")),
            material_id=str(payload.get("material_id", "")),
            tool_command=str(payload.get("tool_command", "")),
            nozzle_temperature_c=float(payload.get("nozzle_temperature_c", 0.0)),
            purge_length_mm=float(payload.get("purge_length_mm", 0.0)),
            load_length_mm=float(payload.get("load_length_mm", 0.0)),
            retract_length_mm=float(payload.get("retract_length_mm", 1.0)),
            requires_prepare_pause=bool(payload.get("requires_prepare_pause", False)),
        )


@dataclass(frozen=True, slots=True)
class MaterialRegion:
    region_id: str
    channel_id: str

    def __post_init__(self) -> None:
        for name in ("region_id", "channel_id"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must not be empty")
            object.__setattr__(self, name, value)

    def to_json(self) -> dict[str, str]:
        return {"region_id": self.region_id, "channel_id": self.channel_id}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "MaterialRegion":
        return cls(str(payload.get("region_id", "")), str(payload.get("channel_id", "")))


@dataclass(frozen=True, slots=True)
class MaterialPlan:
    plan_id: str
    channels: tuple[MaterialChannel, ...]
    regions: tuple[MaterialRegion, ...]
    sensor_required: bool = True
    temperature_timeout_s: float = 180.0
    context: Mapping[str, Any] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        plan_id = str(self.plan_id).strip()
        if not plan_id:
            raise ValueError("plan_id must not be empty")
        channels, regions = tuple(self.channels), tuple(self.regions)
        _validate_plan_members(channels, regions)
        timeout = _finite(self.temperature_timeout_s, "temperature_timeout_s")
        if timeout <= 0.0:
            raise ValueError("temperature_timeout_s must be positive")
        if not isinstance(self.sensor_required, bool):
            raise TypeError("sensor_required must be bool")
        object.__setattr__(self, "plan_id", plan_id)
        object.__setattr__(self, "channels", channels)
        object.__setattr__(self, "regions", regions)
        object.__setattr__(self, "temperature_timeout_s", timeout)
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))

    @property
    def channel_map(self) -> Mapping[str, MaterialChannel]:
        return MappingProxyType({item.channel_id: item for item in self.channels})

    @property
    def region_map(self) -> Mapping[str, MaterialRegion]:
        return MappingProxyType({item.region_id: item for item in self.regions})

    def semantic_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_json())).hexdigest()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "plan_id": self.plan_id,
            "channels": [item.to_json() for item in self.channels],
            "regions": [item.to_json() for item in self.regions],
            "sensor_required": self.sensor_required,
            "temperature_timeout_s": self.temperature_timeout_s,
            "context": dict(self.context),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "MaterialPlan":
        if not isinstance(payload, Mapping) or int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported material plan schema")
        context = payload.get("context", {})
        if not isinstance(context, Mapping):
            raise ValueError("material plan context must be an object")
        return cls(
            str(payload.get("plan_id", "")),
            tuple(MaterialChannel.from_json(item) for item in payload.get("channels", ())),
            tuple(MaterialRegion.from_json(item) for item in payload.get("regions", ())),
            bool(payload.get("sensor_required", True)),
            float(payload.get("temperature_timeout_s", 180.0)),
            context,
        )


@dataclass(frozen=True, slots=True)
class MaterialRuntimeState:
    """Observed preflight state used before a material program reaches a machine."""

    sensor_ready_by_channel: Mapping[str, bool]
    measured_temperature_c_by_channel: Mapping[str, float]
    temperature_tolerance_c: float = 5.0

    def __post_init__(self) -> None:
        sensors = {str(key): value for key, value in self.sensor_ready_by_channel.items()}
        if any(not isinstance(value, bool) for value in sensors.values()):
            raise TypeError("sensor readiness values must be bool")
        temperatures = {
            str(key): _finite(value, f"measured_temperature_c_by_channel[{key}]")
            for key, value in self.measured_temperature_c_by_channel.items()
        }
        tolerance = _finite(self.temperature_tolerance_c, "temperature_tolerance_c")
        if tolerance < 0.0:
            raise ValueError("temperature_tolerance_c must be non-negative")
        object.__setattr__(self, "sensor_ready_by_channel", MappingProxyType(sensors))
        object.__setattr__(
            self,
            "measured_temperature_c_by_channel",
            MappingProxyType(temperatures),
        )
        object.__setattr__(self, "temperature_tolerance_c", tolerance)


class MaterialRuntimeNotReady(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def material_runtime_issues(plan: MaterialPlan, state: MaterialRuntimeState) -> tuple[str, ...]:
    """Return fail-closed sensor and temperature diagnostics for used channels."""

    used = {region.channel_id for region in plan.regions}
    issues: list[str] = []
    for channel_id in sorted(used):
        channel = plan.channel_map[channel_id]
        if plan.sensor_required and state.sensor_ready_by_channel.get(channel_id) is not True:
            issues.append(f"material.sensor_not_ready:{channel_id}")
        measured = state.measured_temperature_c_by_channel.get(channel_id)
        if measured is None:
            issues.append(f"material.temperature_missing:{channel_id}")
        elif abs(measured - channel.nozzle_temperature_c) > state.temperature_tolerance_c:
            issues.append(f"material.temperature_out_of_tolerance:{channel_id}")
    return tuple(issues)


def require_material_runtime_ready(plan: MaterialPlan, state: MaterialRuntimeState) -> None:
    issues = material_runtime_issues(plan, state)
    if issues:
        raise MaterialRuntimeNotReady(issues)


def apply_material_plan(toolpath: GeneratedToolpath, plan: MaterialPlan) -> GeneratedToolpath:
    """Assign deposition identities and add a deterministic switch chain.

    The first selection is emitted as a switch but is not counted as a channel
    transition.  Repeated regions on the active channel do not emit duplicate
    switch events.  Existing path events are retained.
    """

    points, first_sequence_by_region = _assign_material_points(toolpath, plan)
    events = [*toolpath.events, *_material_switch_events(toolpath, plan, first_sequence_by_region)]
    event_priority = {name: index for index, name in enumerate(MATERIAL_EVENT_ORDER)}
    events.sort(key=lambda item: _event_sort_key(item, event_priority, len(points)))
    return GeneratedToolpath(
        toolpath.toolpath_id,
        toolpath.operation_id,
        toolpath.coordinate_frame,
        tuple(points),
        tuple(events),
    )


def _assign_material_points(toolpath, plan):
    region_map, channel_map = plan.region_map, plan.channel_map
    points = []
    first_sequence_by_region: dict[str, int] = {}
    for index, point in enumerate(toolpath.points):
        if point.point_type != "deposition":
            points.append(point)
            continue
        assignment = region_map.get(point.region_id)
        if assignment is None:
            raise ValueError(f"material.region_unassigned:{point.region_id}")
        channel = channel_map[assignment.channel_id]
        first_sequence_by_region.setdefault(point.region_id, index)
        points.append(
            replace(point, material_id=channel.material_id, channel_id=channel.channel_id)
        )
    return points, first_sequence_by_region


def _material_switch_events(toolpath, plan, first_sequence_by_region):
    region_map, channel_map = plan.region_map, plan.channel_map
    events = []
    active: str | None = None
    ordinal = 0
    ordered_regions = sorted(first_sequence_by_region, key=first_sequence_by_region.get)
    for region_id in ordered_regions:
        assignment = region_map[region_id]
        if assignment.channel_id == active:
            continue
        ordinal += 1
        channel = channel_map[assignment.channel_id]
        sequence = first_sequence_by_region[region_id]
        for event_type in MATERIAL_EVENT_ORDER:
            if event_type == "prepare_pause" and not channel.requires_prepare_pause:
                continue
            context: dict[str, Any] = {
                "sequence_index": sequence,
                "material_plan_id": plan.plan_id,
                "material_id": channel.material_id,
                "channel_id": channel.channel_id,
                "tool_command": channel.tool_command,
                "sensor_required": plan.sensor_required,
            }
            if event_type == "retract":
                context["extrusion_length_mm"] = -channel.retract_length_mm
            elif event_type == "load":
                context["extrusion_length_mm"] = channel.load_length_mm
            elif event_type == "temperature_wait":
                context.update(
                    target_temperature_c=channel.nozzle_temperature_c,
                    timeout_s=plan.temperature_timeout_s,
                )
            elif event_type == "purge":
                context["extrusion_length_mm"] = channel.purge_length_mm
            elif event_type == "prime":
                context["extrusion_length_mm"] = channel.retract_length_mm
            events.append(
                ToolpathEvent(
                    f"material-{ordinal:04d}-{event_type}",
                    event_type,
                    toolpath.operation_id,
                    "material_switch",
                    region_id=region_id,
                    context=context,
                )
            )
        active = assignment.channel_id
    return events


def _event_sort_key(item, event_priority, point_count):
    return (
        int(item.context.get("sequence_index", point_count)),
        0 if item.stage_id == "material_switch" else 1,
        event_priority.get(item.event_type, len(event_priority)),
        item.event_id,
    )


def material_statistics(toolpath: GeneratedToolpath) -> dict[str, Any]:
    by_material: dict[str, float] = {}
    selections = transitions = 0
    active: str | None = None
    for point in toolpath.points:
        if point.point_type == "deposition" and point.material_id is not None:
            by_material[point.material_id] = (
                by_material.get(point.material_id, 0.0) + point.material_volume_mm3
            )
    for event in toolpath.events:
        if event.event_type != "switch":
            continue
        selections += 1
        channel = str(event.context.get("channel_id", ""))
        if active is not None and channel != active:
            transitions += 1
        active = channel
    purge = sum(
        float(event.context.get("extrusion_length_mm", 0.0))
        for event in toolpath.events
        if event.event_type == "purge"
    )
    return {
        "deposition_volume_mm3_by_material": dict(sorted(by_material.items())),
        "selection_command_count": selections,
        "effective_channel_transition_count": transitions,
        "purge_length_mm": purge,
    }


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _validate_plan_members(channels, regions):
    if not channels or not regions:
        raise ValueError("material plan requires channels and regions")
    if any(not isinstance(item, MaterialChannel) for item in channels):
        raise TypeError("channels must contain MaterialChannel")
    if any(not isinstance(item, MaterialRegion) for item in regions):
        raise TypeError("regions must contain MaterialRegion")
    channel_ids = [item.channel_id for item in channels]
    region_ids = [item.region_id for item in regions]
    if len(set(channel_ids)) != len(channel_ids):
        raise ValueError("channel_id values must be unique")
    if len(set(region_ids)) != len(region_ids):
        raise ValueError("region_id values must be unique")
    if any(item.channel_id not in set(channel_ids) for item in regions):
        raise ValueError("every material region must reference a declared channel")


__all__ = [
    "MATERIAL_EVENT_ORDER",
    "MaterialChannel",
    "MaterialPlan",
    "MaterialRegion",
    "MaterialRuntimeNotReady",
    "MaterialRuntimeState",
    "apply_material_plan",
    "material_runtime_issues",
    "material_statistics",
    "require_material_runtime_ready",
]
