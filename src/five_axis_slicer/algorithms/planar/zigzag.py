"""Deterministic perimeter-first rectilinear fill for planar regions."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from ...models import Vector3
from .region import PlanarRegion, PlanarSliceLayer
from .offset import inset_region

_EPSILON = 1.0e-8


class PlanarZigzagError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class ZigzagParameters:
    line_spacing_mm: float
    bead_width_mm: float
    layer_height_mm: float
    deposition_feedrate_mm_min: float = 600.0
    travel_feedrate_mm_min: float = 1800.0
    retract_length_mm: float = 1.0

    def __post_init__(self) -> None:
        for name in (
            "line_spacing_mm",
            "bead_width_mm",
            "layer_height_mm",
            "deposition_feedrate_mm_min",
            "travel_feedrate_mm_min",
            "retract_length_mm",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise PlanarZigzagError("planar.zigzag_parameter_invalid", name)


def generate_zigzag_toolpath(
    operation_id: str, layers: tuple[PlanarSliceLayer, ...], parameters: ZigzagParameters
) -> GeneratedToolpath:
    """Create every boundary before clipped alternating infill.

    Separate contour and hatch paths are never bridged with deposition: each
    has an explicit retract/travel/prime transition and zero-volume travel.
    """
    if not layers:
        raise PlanarZigzagError("planar.zigzag_layers_missing", "at least one layer is required")
    builder = _ZigzagBuilder(operation_id, parameters)
    for layer in sorted(layers, key=lambda item: (item.z_mm, item.layer_id)):
        for region in sorted(layer.regions, key=_region_key):
            builder.add_region(layer, region)
    if not builder.points:
        raise PlanarZigzagError("planar.zigzag_empty", "sections contain no fillable region")
    return GeneratedToolpath(
        f"{operation_id}-zigzag-v3",
        operation_id,
        points=tuple(builder.points),
        events=tuple(builder.events),
    )


class _ZigzagBuilder:
    def __init__(self, operation_id: str, parameters: ZigzagParameters) -> None:
        self.operation_id = operation_id
        self.parameters = parameters
        self.points: list[ToolpathPoint] = []
        self.events: list[ToolpathEvent] = []
        self.sequence = 0

    def add_region(self, layer: PlanarSliceLayer, region: PlanarRegion) -> None:
        width = self.parameters.bead_width_mm
        perimeters = inset_region(region, width / 2)
        if not perimeters:
            raise PlanarZigzagError("planar.zigzag_region_too_narrow", region.region_id)
        for island in perimeters:
            for loop in (island.outer, *sorted(island.holes, key=_loop_key)):
                self._add_path(layer, region, tuple(point[:2] for point in loop), "skin")
        # The perimeter occupies one bead width of the material boundary.
        # Hatches fill the remaining domain; their endpoint caps meet the skin.
        segments = tuple(
            segment
            for island in inset_region(region, width)
            for segment in _hatch_segments(island, self.parameters.line_spacing_mm)
        )
        origin = self.points[-1].position[:2]
        for segment in _ordered_segments(segments, origin):
            self._add_path(layer, region, segment, "infill")

    def _add_path(
        self,
        layer: PlanarSliceLayer,
        region: PlanarRegion,
        points: tuple[tuple[float, float], ...],
        role: str,
    ) -> None:
        if len(points) < 2:
            return
        start = _at_z(points[0], layer.z_mm)
        tangent = _unit(_subtract(_at_z(points[1], layer.z_mm), start))
        if self.points:
            self._event("retract", layer, region)
            self._point(layer, region, start, tangent, "travel")
        else:
            self._point(layer, region, start, tangent, "approach")
        self._event("prime", layer, region)
        previous = start
        for point in points[1:]:
            current = _at_z(point, layer.z_mm)
            length = math.dist(previous, current)
            if length <= _EPSILON:
                continue
            tangent = _unit(_subtract(current, previous))
            self._point(
                layer,
                region,
                current,
                tangent,
                "deposition",
                length * self.parameters.bead_width_mm * self.parameters.layer_height_mm,
                role,
            )
            previous = current

    def _point(
        self,
        layer: PlanarSliceLayer,
        region: PlanarRegion,
        position: Vector3,
        tangent: Vector3,
        point_type: str,
        volume: float = 0.0,
        role: str = "none",
    ) -> None:
        self.sequence += 1
        deposition = point_type == "deposition"
        self.points.append(
            ToolpathPoint(
                f"point-{self.sequence:07d}",
                position,
                tangent,
                (0.0, 0.0, -1.0),
                self.operation_id,
                "planar",
                layer.layer_id,
                region.region_id,
                point_type,
                extrusion_role=role if deposition else "none",
                surface_normal=(0.0, 0.0, 1.0),
                feedrate_mm_min=(
                    self.parameters.deposition_feedrate_mm_min
                    if deposition
                    else self.parameters.travel_feedrate_mm_min
                ),
                bead_width_mm=self.parameters.bead_width_mm if deposition else None,
                layer_height_mm=self.parameters.layer_height_mm if deposition else None,
                material_volume_mm3=volume,
            )
        )

    def _event(self, event_type: str, layer: PlanarSliceLayer, region: PlanarRegion) -> None:
        amount = self.parameters.retract_length_mm * (-1.0 if event_type == "retract" else 1.0)
        self.events.append(
            ToolpathEvent(
                f"event-{len(self.events) + 1:07d}",
                event_type,
                self.operation_id,
                "planar",
                layer.layer_id,
                region.region_id,
                context={"sequence_index": self.sequence, "extrusion_length_mm": amount},
            )
        )


def _hatch_segments(
    region: PlanarRegion, spacing: float
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    """Clip horizontal lines with an even/odd rule across outer and hole loops."""
    loops = (region.outer, *region.holes)
    minimum = min(point[1] for loop in loops for point in loop[:-1])
    maximum = max(point[1] for loop in loops for point in loop[:-1])
    result = []
    for index in range(int(math.floor((maximum - minimum) / spacing + _EPSILON)) + 1):
        y = minimum + (index + 0.5) * spacing
        if y >= maximum - _EPSILON:
            continue
        crossings = _merge_nearby(sorted(x for loop in loops for x in _line_intersections(loop, y)))
        for left, right in zip(crossings[::2], crossings[1::2], strict=False):
            if right - left > _EPSILON:
                result.append(((left, y), (right, y)))
    return tuple(result)


def _ordered_segments(segments, origin):
    """Choose a nearby endpoint without extruding between disjoint intervals."""
    remaining = list(segments)
    while remaining:
        _, index, reverse = min(
            (math.dist(origin, end), index, reverse)
            for index, segment in enumerate(remaining)
            for end, reverse in ((segment[0], False), (segment[1], True))
        )
        segment = remaining.pop(index)
        if reverse:
            segment = (segment[1], segment[0])
        yield segment
        origin = segment[1]


def _line_intersections(loop: tuple[Vector3, ...], y: float) -> tuple[float, ...]:
    values = []
    for left, right in zip(loop, loop[1:], strict=False):
        # Half-open edge ownership means a vertex is counted exactly once.
        if (left[1] <= y < right[1]) or (right[1] <= y < left[1]):
            values.append(left[0] + (right[0] - left[0]) * (y - left[1]) / (right[1] - left[1]))
    return tuple(values)


def _merge_nearby(values: list[float]) -> list[float]:
    # Coincident outer/hole crossings cancel in the even/odd rule. Keeping
    # one of a pair would extrude across a hole when an inset touches itself.
    groups: list[list[float]] = []
    for value in values:
        if not groups or abs(value - groups[-1][0]) > _EPSILON:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [sum(group) / len(group) for group in groups if len(group) % 2]


def _region_key(region: PlanarRegion) -> tuple[float, float, str]:
    key = _loop_key(region.outer)
    return (key[0], key[1], region.region_id)


def _loop_key(loop: tuple[Vector3, ...]) -> tuple[float, float]:
    return (min(point[1] for point in loop[:-1]), min(point[0] for point in loop[:-1]))


def _at_z(point: tuple[float, float], z: float) -> Vector3:
    return (point[0], point[1], z)


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(left, right, strict=True))  # type: ignore[return-value]


def _unit(value: Vector3) -> Vector3:
    length = math.sqrt(sum(item * item for item in value))
    if length <= _EPSILON:
        raise PlanarZigzagError(
            "planar.zigzag_zero_segment", "clipping returned a zero length segment"
        )
    return tuple(item / length for item in value)  # type: ignore[return-value]
