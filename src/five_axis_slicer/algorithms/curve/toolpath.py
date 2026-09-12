"""C02-C04 Curve Buildup toolpath generation from a sampled CurvePlan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math

from ...manufacturing.curve_parameters import CurveOperationDefinition
from ...manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from ...models import Vector3
from .chain import CurveGeometryError, CurvePlan, CurveSample

CancelCheck = Callable[[], bool]
ProjectPoint = Callable[[Vector3], Vector3]


@dataclass(frozen=True, slots=True)
class CurvePathDefinition:
    layer_id: str
    region_id: str
    lateral_offset_mm: float
    height_offset_mm: float
    samples: tuple[CurveSample, ...]


def curve_paths(
    plan: CurvePlan,
    operation: CurveOperationDefinition,
    *,
    project_point: ProjectPoint | None = None,
) -> tuple[CurvePathDefinition, ...]:
    """Expand the base chain into the bounded C02/C03/C04 path set."""

    parameters = operation.parameters
    if operation.operation_type == "curve_buildup":
        return (CurvePathDefinition("layer-0001", "pass-0001", 0.0, 0.0, plan.samples),)
    if operation.operation_type == "curve_multi_pass":
        paths = []
        for layer in range(parameters.layer_count):
            samples = _height_offset(plan.samples, layer * parameters.layer_height_mm)
            if layer % 2:
                samples = _reverse_samples(samples)
            paths.append(
                CurvePathDefinition(
                    f"layer-{layer + 1:04d}",
                    "pass-0001",
                    0.0,
                    layer * parameters.layer_height_mm,
                    samples,
                )
            )
        return tuple(paths)
    if operation.operation_type == "curve_offset_buildup":
        paths = []
        for pass_index in range(parameters.offset_pass_count):
            # The selected edge is pass zero. Positive offsets follow the
            # explicit normal x tangent lateral; reversing the edge flips the
            # side. This makes trim ownership and recovery deterministic.
            offset = pass_index * parameters.offset_spacing_mm
            samples = _lateral_offset(
                plan.samples, offset, parameters.bead_width_mm, project_point=project_point
            )
            if pass_index % 2:
                samples = _reverse_samples(samples)
            paths.append(
                CurvePathDefinition(
                    "layer-0001",
                    f"pass-{pass_index + 1:04d}",
                    offset,
                    0.0,
                    samples,
                )
            )
        return tuple(paths)
    raise ValueError(f"unsupported Curve operation type: {operation.operation_type}")


def generate_curve_toolpath(
    plan: CurvePlan,
    operation: CurveOperationDefinition,
    *,
    cancelled: CancelCheck | None = None,
    project_point: ProjectPoint | None = None,
) -> GeneratedToolpath:
    paths = curve_paths(plan, operation, project_point=project_point)
    points: list[ToolpathPoint] = []
    events: list[ToolpathEvent] = []
    for path_index, path in enumerate(paths):
        _checkpoint(cancelled)
        _append_path(points, events, operation, path, path_index)
    if len(points) < 2:
        raise CurveGeometryError("curve.toolpath_empty")
    return GeneratedToolpath(
        f"{operation.operation_id}-{operation.operation_type}-v1",
        operation.operation_id,
        points=tuple(points),
        events=tuple(events),
    )


def _append_path(
    points: list[ToolpathPoint],
    events: list[ToolpathEvent],
    operation: CurveOperationDefinition,
    path: CurvePathDefinition,
    path_index: int,
) -> None:
    samples = path.samples
    if len(samples) < 2:
        raise CurveGeometryError("curve.path_degenerate", path.region_id)
    parameters = operation.parameters
    if points:
        events.append(
            ToolpathEvent(
                f"event-{len(events) + 1:07d}",
                "retract",
                operation.operation_id,
                operation.operation_type,
                path.layer_id,
                path.region_id,
                context={
                    "sequence_index": len(points),
                    "extrusion_length_mm": -parameters.retract_length_mm,
                },
            )
        )
    first, following = samples[0], samples[1]
    points.append(
        ToolpathPoint(
            f"point-{len(points) + 1:07d}",
            first.position,
            _segment_tangent(first.position, following.position),
            _negate(first.surface_normal),
            operation.operation_id,
            operation.operation_type,
            path.layer_id,
            path.region_id,
            "approach" if path_index == 0 else "travel",
            surface_normal=first.surface_normal,
            feedrate_mm_min=parameters.travel_feedrate_mm_min,
        )
    )
    events.append(
        ToolpathEvent(
            f"event-{len(events) + 1:07d}",
            "prime",
            operation.operation_id,
            operation.operation_type,
            path.layer_id,
            path.region_id,
            context={
                "sequence_index": len(points),
                "extrusion_length_mm": parameters.retract_length_mm,
            },
        )
    )
    previous = first
    for current in samples[1:]:
        length = math.dist(previous.position, current.position)
        if length <= 1.0e-10:
            raise CurveGeometryError(
                "curve.path_zero_segment", current.source_edge_id, path.region_id
            )
        points.append(
            ToolpathPoint(
                f"point-{len(points) + 1:07d}",
                current.position,
                _segment_tangent(previous.position, current.position),
                _negate(current.surface_normal),
                operation.operation_id,
                operation.operation_type,
                path.layer_id,
                path.region_id,
                "deposition",
                extrusion_role="buildup",
                surface_normal=current.surface_normal,
                feedrate_mm_min=parameters.feedrate_mm_min,
                bead_width_mm=parameters.bead_width_mm,
                layer_height_mm=parameters.layer_height_mm,
                material_volume_mm3=(
                    length * parameters.bead_width_mm * parameters.layer_height_mm
                ),
            )
        )
        previous = current
    if parameters.dwell_s > 0.0:
        events.append(
            ToolpathEvent(
                f"event-{len(events) + 1:07d}",
                "dwell",
                operation.operation_id,
                operation.operation_type,
                path.layer_id,
                path.region_id,
                duration_s=parameters.dwell_s,
                context={"sequence_index": len(points)},
            )
        )


def _height_offset(samples: tuple[CurveSample, ...], distance: float) -> tuple[CurveSample, ...]:
    return tuple(
        CurveSample(
            _add(item.position, _scale(item.surface_normal, distance)),
            item.tangent,
            item.surface_normal,
            item.source_edge_id,
            item.edge_parameter,
            item.chain_distance_mm,
        )
        for item in samples
    )


def _lateral_offset(
    samples: tuple[CurveSample, ...],
    distance: float,
    bead_width_mm: float,
    *,
    project_point: ProjectPoint | None,
) -> tuple[CurveSample, ...]:
    laterals: list[Vector3] = []
    for item in samples:
        lateral = _cross(item.surface_normal, item.tangent)
        laterals.append(_unit(lateral, "curve.offset_frame_degenerate", item.source_edge_id))
    for left, right in zip(laterals, laterals[1:]):
        if _dot(left, right) < -0.25:
            raise CurveGeometryError(
                "curve.offset_frame_reversal", detail="lateral frame reverses at a sharp turn"
            )
    result = tuple(
        CurveSample(
            (
                shifted
                if project_point is None
                else project_point(shifted)
            ),
            item.tangent,
            item.surface_normal,
            item.source_edge_id,
            item.edge_parameter,
            item.chain_distance_mm,
        )
        for item, lateral in zip(samples, laterals, strict=True)
        for shifted in (_add(item.position, _scale(lateral, distance)),)
    )
    if abs(distance) > 1.0e-12 and _polyline_self_intersects(result, bead_width_mm * 0.05):
        raise CurveGeometryError(
            "curve.offset_self_intersection",
            detail=f"offset {distance:.9g} mm creates a self-intersection",
        )
    return result


def _reverse_samples(samples: tuple[CurveSample, ...]) -> tuple[CurveSample, ...]:
    return tuple(
        CurveSample(
            item.position,
            _negate(item.tangent),
            item.surface_normal,
            item.source_edge_id,
            item.edge_parameter,
            item.chain_distance_mm,
        )
        for item in reversed(samples)
    )


def _polyline_self_intersects(samples: tuple[CurveSample, ...], tolerance: float) -> bool:
    segments = list(zip(samples, samples[1:]))
    for first_index, first in enumerate(segments):
        for second_index in range(first_index + 2, len(segments)):
            if first_index == 0 and second_index == len(segments) - 1:
                continue
            second = segments[second_index]
            if _segment_distance(
                first[0].position,
                first[1].position,
                second[0].position,
                second[1].position,
            ) <= tolerance:
                return True
    return False


def _segment_distance(a: Vector3, b: Vector3, c: Vector3, d: Vector3) -> float:
    """Shortest distance between finite 3-D segments (Ericson formulation)."""

    u, v, w = _subtract(b, a), _subtract(d, c), _subtract(a, c)
    aa, bb, cc = _dot(u, u), _dot(u, v), _dot(v, v)
    dd, ee = _dot(u, w), _dot(v, w)
    denominator = aa * cc - bb * bb
    small = 1.0e-15
    s_n, s_d = denominator, denominator
    t_n, t_d = denominator, denominator
    if denominator < small:
        s_n, s_d, t_n, t_d = 0.0, 1.0, ee, cc
    else:
        s_n, t_n = bb * ee - cc * dd, aa * ee - bb * dd
        if s_n < 0.0:
            s_n, t_n, t_d = 0.0, ee, cc
        elif s_n > s_d:
            s_n, t_n, t_d = s_d, ee + bb, cc
    if t_n < 0.0:
        t_n = 0.0
        if -dd < 0.0:
            s_n = 0.0
        elif -dd > aa:
            s_n = s_d
        else:
            s_n, s_d = -dd, aa
    elif t_n > t_d:
        t_n = t_d
        if -dd + bb < 0.0:
            s_n = 0.0
        elif -dd + bb > aa:
            s_n = s_d
        else:
            s_n, s_d = -dd + bb, aa
    sc = 0.0 if abs(s_n) < small else s_n / s_d
    tc = 0.0 if abs(t_n) < small else t_n / t_d
    delta = _add(w, _subtract(_scale(u, sc), _scale(v, tc)))
    return math.sqrt(_dot(delta, delta))


def _segment_tangent(left: Vector3, right: Vector3) -> Vector3:
    return _unit(_subtract(right, left), "curve.path_zero_segment")


def _unit(value: Vector3, code: str, object_id: str | None = None) -> Vector3:
    length = math.sqrt(_dot(value, value))
    if length <= 1.0e-12:
        raise CurveGeometryError(code, object_id)
    return tuple(item / length for item in value)  # type: ignore[return-value]


def _add(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a + b for a, b in zip(left, right))  # type: ignore[return-value]


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(left, right))  # type: ignore[return-value]


def _scale(value: Vector3, factor: float) -> Vector3:
    return tuple(item * factor for item in value)  # type: ignore[return-value]


def _negate(value: Vector3) -> Vector3:
    return _scale(value, -1.0)


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right))


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _checkpoint(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        from ...postprocessing.indexed_tube import GenerationCancelled

        raise GenerationCancelled("Curve generation cancelled")


__all__ = ["CurvePathDefinition", "curve_paths", "generate_curve_toolpath"]
