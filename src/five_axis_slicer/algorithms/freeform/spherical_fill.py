"""Finite-width solid fill on concentric upper-hemisphere layers.

The section domain uses orthographic ``(x, y)`` coordinates. Horizontal
scanlines are distributed uniformly in meridional arc length, because the
surface-normal distance between neighbouring horizontal curves is
``R d(asin(y/R))``. This gives an explicit physical spacing bound instead of
treating the chart as an isometric plane.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Callable

from ...manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from ...models import CadModel, Vector3
from .._segment_pairs import nonadjacent_overlap_pairs
from ..planar.region import PlanarRegion
from .spherical_domain import SphericalChart, spherical_section

_EPSILON = 1.0e-8


@dataclass(frozen=True, slots=True)
class SphericalFillParameters:
    substrate_radius_mm: float
    radial_thickness_mm: float
    layer_height_mm: float = 0.2
    bead_width_mm: float = 0.4
    deposition_feedrate_mm_min: float = 1200.0
    travel_feedrate_mm_min: float = 3000.0
    retract_length_mm: float = 1.0
    sample_segments: int = 128

    def __post_init__(self) -> None:
        for name in (
            "substrate_radius_mm",
            "radial_thickness_mm",
            "layer_height_mm",
            "bead_width_mm",
            "deposition_feedrate_mm_min",
            "travel_feedrate_mm_min",
            "retract_length_mm",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if isinstance(self.sample_segments, bool) or self.sample_segments < 8:
            raise ValueError("sample_segments must be an integer >= 8")


@dataclass(frozen=True, slots=True)
class SphericalFillAudit:
    layer_count: int
    body_count: int
    bodies_per_layer: tuple[int, ...]
    maximum_cross_path_spacing_mm: float
    material_volume_mm3: float
    cad_volume_mm3: float
    relative_volume_error: float
    first_layer_root_gap_mm: float
    raster_only_region_count: int


def generate_spherical_solid_fill(
    model: CadModel,
    body_ids: tuple[str, ...],
    operation_id: str,
    parameters: SphericalFillParameters,
    *,
    chart: SphericalChart = SphericalChart(),
    cancelled: Callable[[], bool] | None = None,
) -> tuple[GeneratedToolpath, SphericalFillAudit]:
    """Section every selected solid at slab mid-radii and fill every domain."""
    if not body_ids or len(set(body_ids)) != len(body_ids):
        raise ValueError("unique non-empty body_ids required")
    unknown = [body_id for body_id in body_ids if body_id not in model.shapes]
    if unknown:
        raise ValueError(f"unknown spherical fill bodies: {', '.join(unknown)}")
    count = math.ceil(parameters.radial_thickness_mm / parameters.layer_height_mm - 1e-10)
    height = parameters.radial_thickness_mm / count
    builder = _SphericalBuilder(operation_id, parameters, chart, height)
    bodies_per_layer = []
    for layer_index in range(count):
        _checkpoint(cancelled)
        inner = parameters.substrate_radius_mm + layer_index * height
        middle = inner + height / 2
        outer = inner + height
        occupied = 0
        for body_id in body_ids:
            section = spherical_section(
                model.shapes[body_id],
                middle,
                chart=chart,
                sample_segments=parameters.sample_segments,
            )
            if section.regions:
                occupied += 1
            for region in section.regions:
                builder.add_region(layer_index + 1, body_id, region, middle, outer)
        bodies_per_layer.append(occupied)
    if not builder.points:
        raise ValueError("spherical fill generated no printable paths")
    toolpath = GeneratedToolpath(
        f"{operation_id}-spherical-solid-v1",
        operation_id,
        points=tuple(builder.points),
        events=tuple(builder.events),
    )
    cad_volume = math.fsum(model.body_map[body_id].volume or 0.0 for body_id in body_ids)
    material = math.fsum(point.material_volume_mm3 for point in builder.points)
    return toolpath, SphericalFillAudit(
        count,
        len(body_ids),
        tuple(bodies_per_layer),
        builder.maximum_spacing,
        material,
        cad_volume,
        abs(material - cad_volume) / cad_volume,
        builder.minimum_deposition_radius_mm - height - parameters.substrate_radius_mm,
        builder.raster_only_region_count,
    )


class _SphericalBuilder:
    def __init__(self, operation_id, parameters, chart, layer_height):
        self.operation_id = operation_id
        self.parameters = parameters
        self.chart = chart
        self.layer_height = layer_height
        self.points: list[ToolpathPoint] = []
        self.events: list[ToolpathEvent] = []
        self.maximum_spacing = 0.0
        self.minimum_deposition_radius_mm = math.inf
        self.raster_only_region_count = 0

    def add_region(self, layer_index, body_id, region, middle_radius, outer_radius):
        layer_id = f"sphere-layer-{layer_index:03d}"
        shell_offset = self.parameters.bead_width_mm / 2
        shell_region = _polygon_inset(region, shell_offset)
        if shell_region is None:
            # Features narrower than one bead cannot contain a valid perimeter
            # centreline. A clipped full-domain raster is the finite-width,
            # non-overlapping fallback; silently keeping the CAD boundary as a
            # centreline would extrude half the bead outside the selected solid.
            self.raster_only_region_count += 1
            self._add_hatches(layer_id, body_id, region, middle_radius, outer_radius)
            return
        for loop_index, loop in enumerate((shell_region.outer, *shell_region.holes), 1):
            self._add_path(
                layer_id,
                body_id,
                f"shell-{loop_index:03d}",
                loop,
                middle_radius,
                outer_radius,
                "skin",
            )
        interior = _polygon_inset(region, self.parameters.bead_width_mm)
        if interior is not None:
            self._add_hatches(layer_id, body_id, interior, middle_radius, outer_radius)

    def _add_hatches(self, layer_id, body_id, region, middle_radius, outer_radius):
        segments, maximum = _meridional_hatches(
            region, middle_radius, self.parameters.bead_width_mm
        )
        self.maximum_spacing = max(self.maximum_spacing, maximum)
        for index, segment in enumerate(segments, 1):
            self._add_path(
                layer_id,
                body_id,
                f"infill-{index:04d}",
                segment,
                middle_radius,
                outer_radius,
                "infill",
            )

    def _add_path(
        self, layer_id, region_id, path_id, chart_points, middle_radius, outer_radius, role
    ):
        if len(chart_points) < 2:
            return
        positions = tuple(
            _outer_position(self.chart, point, middle_radius, outer_radius)
            for point in chart_points
        )
        positions = tuple(
            point
            for index, point in enumerate(positions)
            if index == 0 or math.dist(point, positions[index - 1]) > _EPSILON
        )
        if len(positions) < 2:
            return
        tangent = _unit(_subtract(positions[1], positions[0]))
        if self.points:
            self._event("retract", layer_id, region_id)
            self._point(positions[0], tangent, layer_id, region_id, path_id, "travel")
        else:
            self._point(positions[0], tangent, layer_id, region_id, path_id, "approach")
        self._event("prime", layer_id, region_id)
        previous = positions[0]
        for current in positions[1:]:
            length = math.dist(previous, current)
            if length > _EPSILON:
                self.minimum_deposition_radius_mm = min(
                    self.minimum_deposition_radius_mm,
                    math.dist(current, self.chart.center),
                )
                self._point(
                    current,
                    _unit(_subtract(current, previous)),
                    layer_id,
                    region_id,
                    path_id,
                    "deposition",
                    role,
                    length * self.parameters.bead_width_mm * self.layer_height,
                )
            previous = current

    def _point(
        self, position, tangent, layer_id, region_id, path_id, point_type, role="none", volume=0.0
    ):
        normal = _unit(_subtract(position, self.chart.center))
        deposition = point_type == "deposition"
        self.points.append(
            ToolpathPoint(
                f"sphere-point-{len(self.points) + 1:08d}",
                position,
                tangent,
                (-normal[0], -normal[1], -normal[2]),
                self.operation_id,
                "spherical-solid-fill",
                layer_id,
                region_id,
                point_type,
                extrusion_role=role if deposition else "none",
                surface_normal=normal,
                feedrate_mm_min=(
                    self.parameters.deposition_feedrate_mm_min
                    if deposition
                    else self.parameters.travel_feedrate_mm_min
                ),
                bead_width_mm=self.parameters.bead_width_mm if deposition else None,
                layer_height_mm=self.layer_height if deposition else None,
                material_volume_mm3=volume,
            )
        )

    def _event(self, kind, layer_id, region_id):
        amount = self.parameters.retract_length_mm * (-1 if kind == "retract" else 1)
        self.events.append(
            ToolpathEvent(
                f"sphere-event-{len(self.events) + 1:08d}",
                kind,
                self.operation_id,
                "spherical-solid-fill",
                layer_id,
                region_id,
                context={"sequence_index": len(self.points), "extrusion_length_mm": amount},
            )
        )


def _meridional_hatches(region: PlanarRegion, radius: float, spacing: float):
    loops = (region.outer, *region.holes)
    minimum = max(-radius + _EPSILON, min(p[1] for loop in loops for p in loop[:-1]))
    maximum = min(radius - _EPSILON, max(p[1] for loop in loops for p in loop[:-1]))
    low, high = math.asin(minimum / radius), math.asin(maximum / radius)
    step = spacing / radius
    count = max(1, math.ceil((high - low) / step))
    actual = (high - low) * radius / count
    result = []
    for index in range(count):
        angle = low + (index + 0.5) * (high - low) / count
        y = radius * math.sin(angle)
        crossings = _merged_crossings(loops, y)
        pairs = list(zip(crossings[::2], crossings[1::2], strict=False))
        if index % 2:
            pairs.reverse()
        for left, right in pairs:
            if right - left > _EPSILON:
                result.append(
                    ((right, y, radius), (left, y, radius))
                    if index % 2
                    else ((left, y, radius), (right, y, radius))
                )
    return tuple(result), actual


def _merged_crossings(loops, y):
    values: list[float] = []
    for loop in loops:
        for left, right in zip(loop, loop[1:], strict=False):
            if (left[1] <= y < right[1]) or (right[1] <= y < left[1]):
                values.append(left[0] + (right[0] - left[0]) * (y - left[1]) / (right[1] - left[1]))
    groups: list[list[float]] = []
    for value in sorted(values):
        if not groups or abs(value - groups[-1][0]) > _EPSILON:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [math.fsum(group) / len(group) for group in groups if len(group) % 2]


def _polygon_inset(region: PlanarRegion, distance: float) -> PlanarRegion | None:
    """Construct a bounded finite-width centreline inset without a CAD-kernel offset.

    The spherical sections are already dense polygonal approximations. Intersecting
    adjacent offset lines is deterministic and avoids the unbounded runtime seen
    when a general B-rep offset is applied independently to hundreds of tiny glyph
    loops. Any collapsed, crossing or topologically suspect result fails closed so
    the caller can use the clipped raster fallback.
    """

    outer = _offset_loop(region.outer, distance, material_is_inside=True)
    holes = tuple(
        shifted
        for loop in region.holes
        if (shifted := _offset_loop(loop, distance, material_is_inside=False)) is not None
    )
    if outer is None or len(holes) != len(region.holes):
        return None
    candidate = PlanarRegion(region.region_id + "-inset", outer, holes)
    if any(not _point_in_material(point, region) for point in outer[:-1]):
        return None
    for source, shifted in zip(region.holes, holes, strict=True):
        if any(_point_in_loop(point, source) for point in shifted[:-1]):
            return None
        if any(not _point_in_loop(point, outer) for point in shifted[:-1]):
            return None
    return candidate


def _offset_loop(loop, distance, *, material_is_inside):
    vertices = _simplified_vertices(loop)
    if len(vertices) < 3:
        return None
    area = _signed_area(loop)
    if abs(area) <= _EPSILON:
        return None
    # For an outer, material is toward the polygon interior; for a hole it is
    # toward the polygon exterior. Account for either source orientation.
    side = math.copysign(1.0, area) * (1.0 if material_is_inside else -1.0)
    shifted = []
    for index, current in enumerate(vertices):
        previous = vertices[index - 1]
        following = vertices[(index + 1) % len(vertices)]
        first = _unit2((current[0] - previous[0], current[1] - previous[1]))
        second = _unit2((following[0] - current[0], following[1] - current[1]))
        if first is None or second is None:
            return None
        first_normal = (-first[1] * side, first[0] * side)
        second_normal = (-second[1] * side, second[0] * side)
        left = (current[0] + first_normal[0] * distance, current[1] + first_normal[1] * distance)
        right = (
            current[0] + second_normal[0] * distance,
            current[1] + second_normal[1] * distance,
        )
        denominator = _cross2(first, second)
        if abs(denominator) <= 1.0e-10:
            xy = ((left[0] + right[0]) / 2, (left[1] + right[1]) / 2)
        else:
            delta = (right[0] - left[0], right[1] - left[1])
            scale = _cross2(delta, second) / denominator
            xy = (left[0] + first[0] * scale, left[1] + first[1] * scale)
        if math.dist((current[0], current[1]), xy) > distance * 4.0:
            # Bound acute/re-entrant mitres with a bevel. The subsequent
            # topology checks still reject crossings and collapsed loops.
            xy = ((left[0] + right[0]) / 2, (left[1] + right[1]) / 2)
        shifted.append((xy[0], xy[1], current[2]))
    shifted.append(shifted[0])
    result = tuple(shifted)
    result_area = _signed_area(result)
    if result_area * area <= 0 or _self_intersects(result):
        return None
    if material_is_inside and abs(result_area) >= abs(area) - _EPSILON:
        return None
    if not material_is_inside and abs(result_area) <= abs(area) + _EPSILON:
        return None
    return result


def _simplified_vertices(loop):
    vertices: list[Vector3] = []
    for point in loop[:-1]:
        if not vertices or math.dist(point, vertices[-1]) > _EPSILON:
            vertices.append(point)
    changed = True
    while changed and len(vertices) >= 3:
        changed = False
        retained: list[Vector3] = []
        for index, current in enumerate(vertices):
            previous = vertices[index - 1]
            following = vertices[(index + 1) % len(vertices)]
            first = _unit2((current[0] - previous[0], current[1] - previous[1]))
            second = _unit2((following[0] - current[0], following[1] - current[1]))
            if (
                first is not None
                and second is not None
                and abs(_cross2(first, second)) <= 1.0e-7
                and first[0] * second[0] + first[1] * second[1] > 0.0
            ):
                changed = True
                continue
            retained.append(current)
        vertices = retained
    return tuple(vertices)


def _self_intersects(loop):
    edges = tuple(zip(loop, loop[1:], strict=False))
    return any(
        _segments_cross(*edges[left], *edges[right])
        for left, right in nonadjacent_overlap_pairs(loop, tolerance=_EPSILON)
    )


def _segments_cross(a, b, c, d):
    ab_c = _cross2((b[0] - a[0], b[1] - a[1]), (c[0] - a[0], c[1] - a[1]))
    ab_d = _cross2((b[0] - a[0], b[1] - a[1]), (d[0] - a[0], d[1] - a[1]))
    cd_a = _cross2((d[0] - c[0], d[1] - c[1]), (a[0] - c[0], a[1] - c[1]))
    cd_b = _cross2((d[0] - c[0], d[1] - c[1]), (b[0] - c[0], b[1] - c[1]))
    return ab_c * ab_d < -_EPSILON and cd_a * cd_b < -_EPSILON


def _point_in_material(point, region):
    return _point_in_loop(point, region.outer) and not any(
        _point_in_loop(point, hole) for hole in region.holes
    )


def _point_in_loop(point, loop):
    inside = False
    x, y = point[:2]
    for left, right in zip(loop, loop[1:], strict=False):
        if (left[1] > y) != (right[1] > y):
            crossing = left[0] + (right[0] - left[0]) * (y - left[1]) / (right[1] - left[1])
            if crossing > x:
                inside = not inside
    return inside


def _signed_area(loop):
    return (
        math.fsum(
            left[0] * right[1] - right[0] * left[1]
            for left, right in zip(loop, loop[1:], strict=False)
        )
        / 2
    )


def _unit2(value):
    length = math.hypot(*value)
    return None if length <= _EPSILON else (value[0] / length, value[1] / length)


def _cross2(left, right):
    return left[0] * right[1] - left[1] * right[0]


def _outer_position(chart, point, middle_radius, outer_radius) -> Vector3:
    middle = chart.lift((point[0], point[1], middle_radius))
    local = _subtract(middle, chart.center)
    scale = outer_radius / middle_radius
    return (
        chart.center[0] + local[0] * scale,
        chart.center[1] + local[1] * scale,
        chart.center[2] + local[2] * scale,
    )


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(left, right, strict=True))  # type: ignore[return-value]


def _unit(value: Vector3) -> Vector3:
    length = math.sqrt(math.fsum(item * item for item in value))
    if length <= _EPSILON:
        raise ValueError("zero spherical path segment")
    return tuple(item / length for item in value)  # type: ignore[return-value]


def _checkpoint(cancelled):
    if cancelled is not None and cancelled():
        from ...postprocessing.indexed_tube import GenerationCancelled

        raise GenerationCancelled("Spherical fill generation cancelled")


__all__ = ["SphericalFillAudit", "SphericalFillParameters", "generate_spherical_solid_fill"]
