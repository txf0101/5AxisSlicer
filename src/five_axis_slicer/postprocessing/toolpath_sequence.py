"""Merge independently generated operations with explicit safe transitions."""

from __future__ import annotations

from dataclasses import replace
import math

from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint


def transform_toolpath(
    toolpath: GeneratedToolpath,
    transform: RigidTransform,
    *,
    coordinate_frame: str = "workpiece_build",
) -> GeneratedToolpath:
    """Map a complete toolpath between rigid coordinate frames.

    Positions include translation. Tangents, nozzle axes and surface normals
    use only the rotation. Event sequence indices remain unchanged.
    """

    if not isinstance(toolpath, GeneratedToolpath):
        raise TypeError("toolpath must be a GeneratedToolpath")
    if not isinstance(transform, RigidTransform):
        raise TypeError("transform must be a RigidTransform")
    return replace(
        toolpath,
        coordinate_frame=str(coordinate_frame).strip(),
        points=tuple(
            replace(
                point,
                position=transform.transform_point(point.position),
                tangent=transform.transform_vector(point.tangent),
                nozzle_axis=transform.transform_vector(point.nozzle_axis),
                surface_normal=(
                    None
                    if point.surface_normal is None
                    else transform.transform_vector(point.surface_normal)
                ),
            )
            for point in toolpath.points
        ),
    )


def merge_toolpath_sequence(
    operation_id: str,
    toolpaths: tuple[GeneratedToolpath, ...],
    *,
    safe_clearance_mm: float,
    travel_feedrate_mm_min: float,
    retract_length_mm: float,
) -> GeneratedToolpath:
    """Merge operations without inventing deposition across operation boundaries."""

    operation_id = str(operation_id).strip()
    if not operation_id:
        raise ValueError("operation_id must not be empty")
    if not toolpaths or any(not path.points for path in toolpaths):
        raise ValueError("toolpaths must be non-empty and contain points")
    if len({path.operation_id for path in toolpaths}) != len(toolpaths):
        raise ValueError("source operation identifiers must be unique")
    frames = {path.coordinate_frame for path in toolpaths}
    if len(frames) != 1:
        raise ValueError("source toolpaths must use one coordinate frame")
    for name, value in (
        ("safe_clearance_mm", safe_clearance_mm),
        ("travel_feedrate_mm_min", travel_feedrate_mm_min),
        ("retract_length_mm", retract_length_mm),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")

    points: list[ToolpathPoint] = []
    events: list[ToolpathEvent] = []
    for operation_index, source in enumerate(toolpaths, 1):
        if points:
            _append_transition(
                operation_id,
                operation_index,
                points,
                events,
                source.points[0],
                safe_clearance_mm,
                travel_feedrate_mm_min,
                retract_length_mm,
            )
        start = len(points)
        prefix = f"op{operation_index:02d}"
        points.extend(
            replace(
                point,
                point_id=f"{prefix}-{point.point_id}",
                operation_id=operation_id,
                stage_id=f"{prefix}-{point.stage_id}",
            )
            for point in source.points
        )
        for event in source.events:
            context = dict(event.context)
            context["sequence_index"] = start + int(context.get("sequence_index", 0))
            events.append(
                replace(
                    event,
                    event_id=f"{prefix}-{event.event_id}",
                    operation_id=operation_id,
                    stage_id=f"{prefix}-{event.stage_id}",
                    context=context,
                )
            )
    return GeneratedToolpath(
        f"{operation_id}-sequence-v1",
        operation_id,
        coordinate_frame=toolpaths[0].coordinate_frame,
        points=tuple(points),
        events=tuple(events),
    )


def _append_transition(
    operation_id,
    operation_index,
    points,
    events,
    target,
    clearance,
    travel_feed,
    retract_length,
):
    start = len(points)
    previous = points[-1]
    for label, point in (("depart", previous), ("travel", target)):
        position = tuple(
            coordinate - axis * clearance
            for coordinate, axis in zip(point.position, point.nozzle_axis, strict=True)
        )
        points.append(
            replace(
                point,
                point_id=f"transition-{operation_index:02d}-{label}",
                operation_id=operation_id,
                stage_id="operation-transition",
                position=position,
                point_type=label,
                extrusion_role="none",
                bead_width_mm=None,
                layer_height_mm=None,
                material_volume_mm3=0.0,
                feedrate_mm_min=travel_feed,
                material_id=None,
                channel_id=None,
                issue_ids=(),
            )
        )
    for event_index, (kind, sequence_index) in enumerate(
        (
            ("retract", start),
            ("safe_depart", start + 1),
            ("operation_change", start + 1),
            ("safe_approach", start + 2),
        ),
        1,
    ):
        context = {"sequence_index": sequence_index}
        if kind == "retract":
            context["extrusion_length_mm"] = -retract_length
        events.append(
            ToolpathEvent(
                f"transition-{operation_index:02d}-{event_index:02d}-{kind}",
                kind,
                operation_id,
                "operation-transition",
                target.layer_id,
                target.region_id,
                context=context,
            )
        )


__all__ = ["merge_toolpath_sequence", "transform_toolpath"]
