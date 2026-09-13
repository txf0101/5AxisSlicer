"""Convert a checked Freeform plan into the shared Toolpath contract."""

from __future__ import annotations

from collections.abc import Callable
import math

from ...manufacturing.freeform_parameters import FreeformOperationDefinition
from ...manufacturing.material_plan import apply_material_plan
from ...manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from .core import FreeformGeometryError, FreeformPlan

CancelCheck = Callable[[], bool]


def generate_freeform_toolpath(
    plan: FreeformPlan,
    operation: FreeformOperationDefinition,
    *,
    cancelled: CancelCheck | None = None,
) -> GeneratedToolpath:
    points: list[ToolpathPoint] = []
    events: list[ToolpathEvent] = []
    for path_index, path in enumerate(plan.paths):
        _checkpoint(cancelled)
        _append_path(points, events, operation, path, path_index)
    result = GeneratedToolpath(
        f"{operation.operation_id}-{operation.operation_type}-v1",
        operation.operation_id,
        points=tuple(points),
        events=tuple(events),
    )
    return (
        result
        if operation.material_plan is None
        else apply_material_plan(result, operation.material_plan)
    )


def _append_path(points, events, operation, path, path_index):
    parameters = operation.parameters
    if path_index and parameters.retract_length_mm:
        events.append(
            _extrusion_event(
                operation,
                path,
                len(points),
                "retract",
                -parameters.retract_length_mm,
                len(events),
            )
        )
    first, second = path.samples[0], path.samples[1]
    points.append(_travel_point(points, operation, path, first, second, path_index))
    if parameters.retract_length_mm:
        events.append(
            _extrusion_event(
                operation,
                path,
                len(points),
                "prime",
                parameters.retract_length_mm,
                len(events),
            )
        )
    previous = first
    for sample in path.samples[1:]:
        distance = math.dist(previous.position, sample.position)
        if distance <= 1.0e-10:
            raise FreeformGeometryError("freeform.zero_segment")
        points.append(_deposition_point(points, operation, path, previous, sample, distance))
        previous = sample


def _travel_point(points, operation, path, first, second, path_index):
    return ToolpathPoint(
        f"point-{len(points) + 1:07d}",
        first.position,
        _tangent(first.position, second.position),
        _negative(first.surface_normal),
        operation.operation_id,
        operation.operation_type,
        path.layer_id,
        path.region_id,
        "approach" if path_index == 0 else "travel",
        surface_normal=first.surface_normal,
        feedrate_mm_min=operation.parameters.travel_feedrate_mm_min,
    )


def _deposition_point(points, operation, path, previous, sample, distance):
    parameters = operation.parameters
    return ToolpathPoint(
        f"point-{len(points) + 1:07d}",
        sample.position,
        _tangent(previous.position, sample.position),
        _negative(sample.surface_normal),
        operation.operation_id,
        operation.operation_type,
        path.layer_id,
        path.region_id,
        "deposition",
        extrusion_role="buildup",
        surface_normal=sample.surface_normal,
        feedrate_mm_min=parameters.feedrate_mm_min,
        bead_width_mm=parameters.bead_width_mm,
        layer_height_mm=parameters.layer_height_mm,
        material_volume_mm3=distance * parameters.bead_width_mm * parameters.layer_height_mm,
    )


def _extrusion_event(operation, path, sequence, kind, amount, ordinal):
    return ToolpathEvent(
        f"event-{ordinal + 1:07d}",
        kind,
        operation.operation_id,
        operation.operation_type,
        path.layer_id,
        path.region_id,
        context={"sequence_index": sequence, "extrusion_length_mm": amount},
    )


def _tangent(left, right):
    delta = tuple(b - a for a, b in zip(left, right))
    length = math.sqrt(sum(item * item for item in delta))
    if length <= 1.0e-12:
        raise FreeformGeometryError("freeform.zero_segment")
    return tuple(item / length for item in delta)


def _negative(value):
    return tuple(-item for item in value)


def _checkpoint(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        from ...postprocessing.indexed_tube import GenerationCancelled

        raise GenerationCancelled("Freeform generation cancelled")


__all__ = ["generate_freeform_toolpath"]
