"""Event placement and numeric inputs for the offline absolute XYZAC dialect."""

from __future__ import annotations

import math

from ..manufacturing.resources import NozzleProfile
from ..manufacturing.toolpath import GeneratedToolpath, ToolpathEvent

_ANNOTATION_EVENTS = frozenset(
    {"index_start", "index_end", "operation_change", "safe_depart", "safe_approach", "finish"}
)


def filament_area_mm2(nozzle: NozzleProfile) -> float:
    diameter = nozzle.filament_diameter_mm
    area = math.pi * (diameter * 0.5) ** 2
    if not math.isfinite(diameter) or diameter <= 0.0 or not math.isfinite(area) or area <= 0.0:
        raise ValueError("filament diameter must define a finite positive cross section")
    return area


def event_extrusion_mm(event: ToolpathEvent) -> float | None:
    """Return a signed actuator displacement, or a supported annotation event."""
    if event.event_type in _ANNOTATION_EVENTS:
        return None
    if event.event_type not in {"retract", "prime"}:
        raise ValueError(f"unsupported Generic XYZAC event: {event.event_type}")
    value = event.context.get("extrusion_length_mm")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{event.event_id}: explicit finite extrusion_length_mm is required")
    if (event.event_type == "retract" and value > 0.0) or (
        event.event_type == "prime" and value < 0.0
    ):
        raise ValueError(f"{event.event_id}: extrusion sign disagrees with {event.event_type}")
    return float(value)


def events_by_sequence(toolpath: GeneratedToolpath) -> dict[int, list[ToolpathEvent]]:
    """Sequence N executes after N path points, including terminal events at len(points)."""
    result: dict[int, list[ToolpathEvent]] = {}
    count = len(toolpath.points)
    for event in toolpath.events:
        default = count if event.event_type == "finish" else None
        sequence = event.context.get("sequence_index", default)
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or not 0 <= sequence <= count
        ):
            raise ValueError(f"{event.event_id}: sequence_index must be an integer in [0, {count}]")
        if event.event_type == "finish" and sequence != count:
            raise ValueError(f"{event.event_id}: finish must follow all path points")
        event_extrusion_mm(event)
        result.setdefault(sequence, []).append(event)
    return result


def event_feedrate_mm_min(toolpath: GeneratedToolpath, sequence: int) -> float:
    """Use the following motion feed, or the final motion feed for terminal events."""
    if not toolpath.points:
        return 1.0
    return toolpath.points[min(sequence, len(toolpath.points) - 1)].feedrate_mm_min or 1.0


def marker_identifier(value: str) -> str:
    if not value or any(character.isspace() or character == ";" for character in value):
        raise ValueError("G-code marker identifiers must be nonempty single words")
    return value
