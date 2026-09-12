"""Restricted continuous-Z contour interpolation for Planar Spiral."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from ...models import Vector3
from .region import PlanarSliceLayer
from .offset import inset_region

_EPSILON = 1.0e-9


class PlanarSpiralError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class SpiralParameters:
    bead_width_mm: float
    layer_height_mm: float
    samples_per_contour: int = 64
    feedrate_mm_min: float = 600.0

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.bead_width_mm)
            or not math.isfinite(self.layer_height_mm)
            or not math.isfinite(self.feedrate_mm_min)
            or self.bead_width_mm <= 0
            or self.layer_height_mm <= 0
            or self.feedrate_mm_min <= 0
            or self.samples_per_contour < 8
        ):
            raise PlanarSpiralError(
                "planar.spiral_parameter_invalid",
                "positive bead/layer/feedrate and at least 8 samples required",
            )


def generate_spiral_toolpath(
    operation_id: str, layers: tuple[PlanarSliceLayer, ...], parameters: SpiralParameters
) -> GeneratedToolpath:
    """Join one corresponding, hole-free contour per layer with a continuous Z ramp."""
    contours = _spiral_contours(layers, parameters)
    points = _spiral_points(operation_id, layers, contours, parameters)
    _validate_material_volume(points, parameters)
    event = ToolpathEvent(
        f"event-{len(points) + 1:07d}",
        "finish",
        operation_id,
        "planar_spiral",
        layers[-1].layer_id,
        layers[-1].regions[0].region_id,
        context={"closed": True, "continuous_z": True, "sequence_index": len(points)},
    )
    return GeneratedToolpath(
        f"{operation_id}-spiral-v3", operation_id, points=tuple(points), events=(event,)
    )


def _spiral_contours(
    layers: tuple[PlanarSliceLayer, ...], parameters: SpiralParameters
) -> tuple[tuple[tuple[float, float, float], ...], ...]:
    if len(layers) < 2:
        raise PlanarSpiralError(
            "planar.spiral_layers_insufficient", "at least two layers are required"
        )
    if any(
        not math.isfinite(layer.z_mm)
        or (index > 0 and layer.z_mm <= layers[index - 1].z_mm + _EPSILON)
        for index, layer in enumerate(layers)
    ):
        raise PlanarSpiralError(
            "planar.spiral_layer_order_invalid", "layer Z values must be finite and increasing"
        )
    contours: list[tuple[tuple[float, float, float], ...]] = []
    previous_id: str | None = None
    previous_sign: int | None = None
    for layer in layers:
        if len(layer.regions) != 1:
            raise PlanarSpiralError(
                "planar.spiral_multiple_regions", f"{layer.layer_id} is not single connected"
            )
        region = layer.regions[0]
        if region.holes:
            raise PlanarSpiralError(
                "planar.spiral_holes_unsupported", f"{layer.layer_id} contains holes"
            )
        if previous_id is not None and region.region_id != previous_id:
            raise PlanarSpiralError(
                "planar.spiral_topology_changed", "corresponding region identifiers differ"
            )
        contour = _inset_spiral_contour(region, parameters, layer.layer_id)
        sign = 1 if _area(contour) > 0 else -1
        if previous_sign is not None and sign != previous_sign:
            raise PlanarSpiralError(
                "planar.spiral_topology_changed", "contour orientation changes between layers"
            )
        contours.append(contour)
        previous_id, previous_sign = region.region_id, sign
    return tuple(contours)


def _inset_spiral_contour(region, parameters, layer_id):
    # Diagnose input topology before asking the kernel to offset it.
    _resample(region.outer, parameters.samples_per_contour)
    islands = inset_region(region, parameters.bead_width_mm / 2)
    if len(islands) != 1 or islands[0].holes:
        raise PlanarSpiralError("planar.spiral_inset_topology_changed", layer_id)
    return _resample(islands[0].outer, parameters.samples_per_contour)


def _spiral_points(
    operation_id: str,
    layers: tuple[PlanarSliceLayer, ...],
    contours: tuple[tuple[tuple[float, float, float], ...], ...],
    parameters: SpiralParameters,
) -> list[ToolpathPoint]:
    points: list[ToolpathPoint] = []
    count = parameters.samples_per_contour
    for layer_index, (layer, contour) in enumerate(zip(layers, contours)):
        next_contour = contours[layer_index + 1] if layer_index + 1 < len(layers) else contour
        next_z = layers[layer_index + 1].z_mm if layer_index + 1 < len(layers) else layer.z_mm
        for index in range(count + 1):
            fraction = index / count
            position = _spiral_position(
                contour, next_contour, index % count, fraction, layer.z_mm, next_z
            )
            if index == 0 and points:
                continue
            previous = points[-1].position if points else None
            if previous is not None:
                _check_segment(
                    contour,
                    next_contour,
                    previous,
                    position,
                    layer.z_mm,
                    next_z,
                    (index - 1) / count,
                    fraction,
                    layer_index,
                )
            points.append(
                _spiral_point(
                    len(points),
                    operation_id,
                    layer,
                    position,
                    previous,
                    next_contour,
                    next_z,
                    parameters,
                )
            )
    return points


def _spiral_position(lower, upper, point_index, fraction, lower_z, upper_z) -> Vector3:
    left, right = lower[point_index], upper[point_index]
    return (
        left[0] + (right[0] - left[0]) * fraction,
        left[1] + (right[1] - left[1]) * fraction,
        lower_z + (upper_z - lower_z) * fraction,
    )


def _spiral_point(index, operation_id, layer, position, previous, next_contour, next_z, parameters):
    deposition = previous is not None
    if deposition:
        delta = tuple(position[axis] - previous[axis] for axis in range(3))
        volume = (
            math.dist(previous, position) * parameters.bead_width_mm * parameters.layer_height_mm
        )
    else:
        following = next_contour[1]
        delta = (following[0] - position[0], following[1] - position[1], next_z - position[2])
        volume = 0.0
    return ToolpathPoint(
        f"point-{index + 1:07d}",
        position,
        _unit(delta),
        (0.0, 0.0, -1.0),
        operation_id,
        "planar_spiral",
        layer.layer_id,
        layer.regions[0].region_id,
        "deposition" if deposition else "approach",
        extrusion_role="thin_wall" if deposition else "none",
        surface_normal=(0.0, 0.0, 1.0),
        bead_width_mm=parameters.bead_width_mm if deposition else None,
        layer_height_mm=parameters.layer_height_mm if deposition else None,
        feedrate_mm_min=parameters.feedrate_mm_min,
        material_volume_mm3=volume,
    )


def _check_segment(
    lower: tuple[tuple[float, float, float], ...],
    upper: tuple[tuple[float, float, float], ...],
    start: Vector3,
    end: Vector3,
    lower_z: float,
    upper_z: float,
    start_fraction: float,
    end_fraction: float,
    layer_index: int,
) -> None:
    for sample in range(5):
        local_fraction = sample / 4
        fraction = start_fraction + (end_fraction - start_fraction) * local_fraction
        point = (
            start[0] + (end[0] - start[0]) * local_fraction,
            start[1] + (end[1] - start[1]) * local_fraction,
        )
        interpolated = tuple(
            (
                left[0] + (right[0] - left[0]) * fraction,
                left[1] + (right[1] - left[1]) * fraction,
                lower_z + (upper_z - lower_z) * fraction,
            )
            for left, right in zip(lower, upper, strict=True)
        )
        if not _inside_or_boundary(point, interpolated):
            raise PlanarSpiralError(
                "planar.spiral_interpolation_outside",
                f"segment {layer_index} leaves interpolated contour",
            )


def _validate_material_volume(points: list[ToolpathPoint], parameters: SpiralParameters) -> None:
    expected = sum(
        math.dist(previous.position, current.position)
        * parameters.bead_width_mm
        * parameters.layer_height_mm
        for previous, current in zip(points, points[1:], strict=False)
    )
    actual = sum(point.material_volume_mm3 for point in points)
    if not math.isfinite(actual) or abs(actual - expected) > max(1.0e-8, expected * 1.0e-10):
        raise PlanarSpiralError(
            "planar.spiral_volume_inconsistent", "material volume is inconsistent"
        )


def _resample(
    loop: tuple[tuple[float, float, float], ...], count: int
) -> tuple[tuple[float, float, float], ...]:
    if (
        len(loop) < 4
        or loop[0] != loop[-1]
        or any(not all(math.isfinite(value) for value in point) for point in loop)
    ):
        raise PlanarSpiralError(
            "planar.spiral_degenerate_contour", "contour is not finite and closed"
        )
    edges = list(zip(loop, loop[1:], strict=False))
    lengths = [math.dist(left, right) for left, right in edges]
    if any(length <= _EPSILON for length in lengths) or abs(_area(loop)) <= _EPSILON:
        raise PlanarSpiralError("planar.spiral_degenerate_contour", "zero perimeter or area")
    total = sum(lengths)
    values: list[tuple[float, float, float]] = []
    for index in range(count):
        target, walked = total * index / count, 0.0
        for (left, right), length in zip(edges, lengths, strict=True):
            if target <= walked + length:
                fraction = (target - walked) / length
                values.append(
                    (
                        left[0] + (right[0] - left[0]) * fraction,
                        left[1] + (right[1] - left[1]) * fraction,
                        left[2] + (right[2] - left[2]) * fraction,
                    )
                )
                break
            walked += length
    return tuple(values)


def _area(loop: tuple[tuple[float, float, float], ...]) -> float:
    return 0.5 * sum(left[0] * right[1] - right[0] * left[1] for left, right in _closed_edges(loop))


def _inside_or_boundary(
    point: tuple[float, float], loop: tuple[tuple[float, float, float], ...]
) -> bool:
    if _distance_to_loop(point, loop) <= 1.0e-7:
        return True
    crossings = sum(
        (left[1] > point[1]) != (right[1] > point[1])
        and point[0] < (right[0] - left[0]) * (point[1] - left[1]) / (right[1] - left[1]) + left[0]
        for left, right in _closed_edges(loop)
    )
    return bool(crossings % 2)


def _distance_to_loop(
    point: tuple[float, float], loop: tuple[tuple[float, float, float], ...]
) -> float:
    return min(_distance_point_segment(point, left, right) for left, right in _closed_edges(loop))


def _closed_edges(loop):
    return zip(loop, (*loop[1:], loop[0]), strict=True)


def _distance_point_segment(
    point: tuple[float, float], start: tuple[float, float, float], end: tuple[float, float, float]
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    ratio = (
        0.0
        if length2 <= _EPSILON
        else max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length2))
    )
    return math.dist(point, (start[0] + ratio * dx, start[1] + ratio * dy))


def _unit(value: tuple[float, float, float]) -> Vector3:
    length = math.sqrt(sum(item * item for item in value))
    if length <= _EPSILON:
        raise PlanarSpiralError("planar.spiral_degenerate_contour", "zero tangent")
    return (value[0] / length, value[1] / length, value[2] / length)


__all__ = ["PlanarSpiralError", "SpiralParameters", "generate_spiral_toolpath"]
