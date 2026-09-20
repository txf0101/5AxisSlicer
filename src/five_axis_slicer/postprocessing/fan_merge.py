"""FAN10 structural merger. No implicit travel or text-level NC concatenation."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re

from ..manufacturing.toolpath import GeneratedToolpath, ToolpathPoint, ToolpathEvent

FAN_OPERATION_ORDER = (
    "base",
    "index90",
    "blade1",
    "transfer12",
    "blade2",
    "transfer23",
    "blade3",
    "finish",
)


@dataclass(frozen=True, slots=True)
class FanProgramIndex:
    operation_id: str
    first_point: int
    last_point: int
    source_toolpath_id: str


def merge_fan_operations(operations: dict[str, GeneratedToolpath], *, job_id: str):
    """Renumber structured geometry/events; preserve provenance in an index.

    Returned geometry still requires a single global IK solve, motion/collision
    qualification and strict postprocessor readback. This function cannot release
    a program, and never silently supplies missing indexing/transfer motions.
    """
    if set(operations) != set(FAN_OPERATION_ORDER):
        raise ValueError("fan.missing_or_unknown_operation")
    points: list[ToolpathPoint] = []
    events: list[ToolpathEvent] = []
    index: list[FanProgramIndex] = []
    for operation_id in FAN_OPERATION_ORDER:
        source = operations[operation_id]
        if source.coordinate_frame != "workpiece_build" or not source.points:
            raise ValueError(f"fan.invalid_operation_frame_or_empty: {operation_id}")
        if source.points[0].point_type == "deposition":
            raise ValueError(f"fan.missing_explicit_approach: {operation_id}")
        if operation_id in {"index90", "transfer12", "transfer23", "finish"} and any(
            p.point_type == "deposition" for p in source.points
        ):
            raise ValueError(f"fan.extruding_transfer_forbidden: {operation_id}")
        offset = len(points)
        points.extend(
            replace(
                p,
                point_id=f"{operation_id}:{p.point_id}",
                operation_id=job_id,
                stage_id=f"{operation_id}:{p.stage_id}",
                layer_id=f"{operation_id}:{p.layer_id}",
            )
            for p in source.points
        )
        for event in source.events:
            sequence = event.context.get("sequence_index")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or not 0 <= sequence <= len(source.points)
            ):
                raise ValueError(f"fan.invalid_event_sequence: {event.event_id}")
            if event.event_type == "index_start":
                raise ValueError(
                    "fan.implicit_index_motion_forbidden: use explicit checked geometry"
                )
            events.append(
                replace(
                    event,
                    event_id=f"{operation_id}:{event.event_id}",
                    operation_id=job_id,
                    stage_id=f"{operation_id}:{event.stage_id}",
                    context={**event.context, "sequence_index": offset + sequence},
                )
            )
        index.append(FanProgramIndex(operation_id, offset + 1, len(points), source.toolpath_id))
    return GeneratedToolpath(
        f"{job_id}-merged", job_id, points=tuple(points), events=tuple(events)
    ), tuple(index)


def fan_program_line_index(gcode: str, index: tuple[FanProgramIndex, ...]):
    """Bind source operation ranges to the actual merged postprocessor lines."""
    markers = {}
    for line_number, line in enumerate(gcode.splitlines(), 1):
        match = re.fullmatch(r"; PAC POINT (\d+) .+", line)
        if match:
            point = int(match.group(1))
            if point in markers:
                raise ValueError("fan.duplicate_program_point")
            markers[point] = line_number + 1
    count = index[-1].last_point if index else 0
    if set(markers) != set(range(1, count + 1)):
        raise ValueError("fan.program_point_index_mismatch")
    return tuple(
        {
            "operation_id": item.operation_id,
            "source_toolpath_id": item.source_toolpath_id,
            "first_motion_line": markers[item.first_point],
            "last_motion_line": markers[item.last_point],
        }
        for item in index
    )
