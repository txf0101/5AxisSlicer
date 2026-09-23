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
    "unload",
    "switch",
    "temperature_wait",
    "load",
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
    unload_length_mm: float = 0.0
    retract_feedrate_mm_min: float = 1200.0
    unload_feedrate_mm_min: float = 300.0
    load_feedrate_mm_min: float = 300.0
    purge_feedrate_mm_min: float = 120.0
    prime_feedrate_mm_min: float = 1200.0
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
        for name in ("purge_length_mm", "load_length_mm", "retract_length_mm", "unload_length_mm"):
            numeric_value = _finite(getattr(self, name), name)
            if numeric_value < 0.0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, numeric_value)
        for name in (
            "retract_feedrate_mm_min", "unload_feedrate_mm_min", "load_feedrate_mm_min",
            "purge_feedrate_mm_min", "prime_feedrate_mm_min",
        ):
            numeric_value = _finite(getattr(self, name), name)
            if numeric_value <= 0.0:
                raise ValueError(f"{name} must be positive")
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
            unload_length_mm=float(payload.get("unload_length_mm", 0.0)),
            retract_feedrate_mm_min=float(payload.get("retract_feedrate_mm_min", 1200.0)),
            unload_feedrate_mm_min=float(payload.get("unload_feedrate_mm_min", 300.0)),
            load_feedrate_mm_min=float(payload.get("load_feedrate_mm_min", 300.0)),
            purge_feedrate_mm_min=float(payload.get("purge_feedrate_mm_min", 120.0)),
            prime_feedrate_mm_min=float(payload.get("prime_feedrate_mm_min", 1200.0)),
            requires_prepare_pause=bool(payload.get("requires_prepare_pause", False)),
        )


@dataclass(frozen=True, slots=True)
class MaterialRegion:
    region_id: str
    channel_id: str
    stage_prefix: str = ""

    def __post_init__(self) -> None:
        for name in ("region_id", "channel_id"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must not be empty")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "stage_prefix", str(self.stage_prefix).strip())

    def to_json(self) -> dict[str, str]:
        result = {"region_id": self.region_id, "channel_id": self.channel_id}
        if self.stage_prefix:
            result["stage_prefix"] = self.stage_prefix
        return result

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "MaterialRegion":
        return cls(
            str(payload.get("region_id", "")),
            str(payload.get("channel_id", "")),
            str(payload.get("stage_prefix", "")),
        )


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
    def region_map(self) -> Mapping[tuple[str, str], MaterialRegion]:
        return MappingProxyType({
            (item.stage_prefix, item.region_id): item for item in self.regions
        })

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

    points, switches = _assign_material_points(toolpath, plan)
    events = [*toolpath.events, *_material_switch_events(toolpath, plan, switches)]
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
    channel_map = plan.channel_map
    points = []
    switches: list[tuple[int, str, MaterialChannel, MaterialChannel | None]] = []
    active: str | None = None
    for index, point in enumerate(toolpath.points):
        if point.point_type != "deposition":
            points.append(point)
            continue
        assignment = _region_assignment(point, plan.regions)
        if assignment is None:
            raise ValueError(f"material.region_unassigned:{point.stage_id}:{point.region_id}")
        channel = channel_map[assignment.channel_id]
        if channel.channel_id != active:
            switches.append((index, point.region_id, channel, channel_map.get(active)))
            active = channel.channel_id
        points.append(
            replace(point, material_id=channel.material_id, channel_id=channel.channel_id)
        )
    return points, switches


def _region_assignment(point, regions):
    matches = [
        region
        for region in regions
        if (region.region_id == point.region_id or region.region_id == "*")
        and point.stage_id.startswith(region.stage_prefix)
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: (item.region_id != "*", len(item.stage_prefix)), reverse=True)
    if len(matches) > 1 and (
        (matches[0].region_id != "*", len(matches[0].stage_prefix))
        == (matches[1].region_id != "*", len(matches[1].stage_prefix))
    ):
        raise ValueError(f"material.region_ambiguous:{point.stage_id}:{point.region_id}")
    return matches[0]


def _material_switch_events(toolpath, plan, switches):
    events = []
    ordinal = 0
    for first_deposition, region_id, channel, previous_channel in switches:
        ordinal += 1
        sequence = first_deposition
        while sequence and toolpath.points[sequence - 1].point_type != "deposition":
            sequence -= 1
        initial_selection = previous_channel is None
        event_types = (
            ("switch", "temperature_wait")
            if initial_selection
            else MATERIAL_EVENT_ORDER
        )
        for event_type in event_types:
            if event_type == "prepare_pause" and not channel.requires_prepare_pause:
                continue
            event_channel = (
                previous_channel
                if event_type in {"retract", "cut", "park", "unload"}
                and previous_channel is not None
                else channel
            )
            context: dict[str, Any] = {
                "sequence_index": sequence,
                "material_plan_id": plan.plan_id,
                "material_id": event_channel.material_id,
                "channel_id": event_channel.channel_id,
                "tool_command": channel.tool_command,
                "sensor_required": plan.sensor_required,
            }
            if event_type == "retract":
                context["extrusion_length_mm"] = -event_channel.retract_length_mm
                context["feedrate_mm_min"] = event_channel.retract_feedrate_mm_min
            elif event_type == "unload":
                context["extrusion_length_mm"] = -event_channel.unload_length_mm
                context["feedrate_mm_min"] = event_channel.unload_feedrate_mm_min
            elif event_type == "load":
                context["extrusion_length_mm"] = channel.load_length_mm
                context["feedrate_mm_min"] = channel.load_feedrate_mm_min
            elif event_type == "temperature_wait":
                context.update(
                    target_temperature_c=channel.nozzle_temperature_c,
                    timeout_s=plan.temperature_timeout_s,
                )
            elif event_type == "purge":
                context["extrusion_length_mm"] = channel.purge_length_mm
                context["feedrate_mm_min"] = channel.purge_feedrate_mm_min
            elif event_type == "prime":
                context["extrusion_length_mm"] = channel.retract_length_mm
                context["feedrate_mm_min"] = channel.prime_feedrate_mm_min
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
    region_ids = [(item.region_id, item.stage_prefix) for item in regions]
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
