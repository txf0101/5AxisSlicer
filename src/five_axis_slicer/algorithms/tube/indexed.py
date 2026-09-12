"""Wedge planning, fixed-direction slicing, and indexed thin-wall paths."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...manufacturing.setup import TubeProcessParameters
from ...manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from ...models import CadModel, Vector3
from .geometry import CenterlinePrimitive, TubeFeature
from .section import section_tube_layer


class TubePlanningError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = str(code)
        self.detail = str(detail)
        super().__init__(f"{self.code}: {self.detail}")


@dataclass(frozen=True, slots=True)
class TubeRegion:
    region_id: str
    start_distance_mm: float
    end_distance_mm: float
    fixed_build_direction: Vector3
    maximum_direction_change_rad: float
    maximum_height_error_mm: float
    source_face_id: str

    def __post_init__(self) -> None:
        if self.end_distance_mm <= self.start_distance_mm:
            raise ValueError("Tube region must have positive coverage")
        object.__setattr__(self, "fixed_build_direction", _unit(self.fixed_build_direction))


@dataclass(frozen=True, slots=True)
class TubeSliceLayer:
    layer_id: str
    region_id: str
    centerline_distance_mm: float
    plane_origin: Vector3
    plane_normal: Vector3
    ownership: str = "half_open"


@dataclass(frozen=True, slots=True)
class IndexedSlicePlan:
    regions: tuple[TubeRegion, ...]
    layers: tuple[TubeSliceLayer, ...]
    centerline_length_mm: float
    nominal_layer_height_mm: float
    contour_chord_error_mm: float = 0.01

    def __post_init__(self) -> None:
        regions, layers = tuple(self.regions), tuple(self.layers)
        if not regions or not layers:
            raise ValueError("Indexed slice plan requires regions and layers")
        if not math.isfinite(self.nominal_layer_height_mm) or self.nominal_layer_height_mm <= 0.0:
            raise ValueError("nominal_layer_height_mm must be finite and positive")
        if abs(regions[0].start_distance_mm) > 1.0e-8:
            raise ValueError("Tube region coverage must start at zero")
        if abs(regions[-1].end_distance_mm - self.centerline_length_mm) > 1.0e-8:
            raise ValueError("Tube region coverage must reach the exit")
        for left, right in zip(regions, regions[1:]):
            if abs(left.end_distance_mm - right.start_distance_mm) > 1.0e-8:
                raise ValueError("Tube region coverage contains a gap or overlap")
        object.__setattr__(self, "regions", regions)
        object.__setattr__(self, "layers", layers)


def plan_indexed_slices(
    feature: TubeFeature, parameters: TubeProcessParameters
) -> IndexedSlicePlan:
    regions = _build_regions(feature, parameters)
    distances = _layer_distances(feature.centerline_length_mm, parameters.layer_height_mm)
    layers: list[TubeSliceLayer] = []
    for index, distance in enumerate(distances):
        region = _owning_region(regions, distance)
        origin, _actual_tangent = feature.point_tangent_at(distance)
        layers.append(
            TubeSliceLayer(
                f"layer-{index + 1:05d}",
                region.region_id,
                distance,
                origin,
                region.fixed_build_direction,
                "closed_exit" if index == len(distances) - 1 else "half_open",
            )
        )
    return IndexedSlicePlan(
        tuple(regions),
        tuple(layers),
        feature.centerline_length_mm,
        parameters.layer_height_mm,
        parameters.contour_chord_error_mm,
    )


def generate_indexed_toolpath(
    operation_id: str,
    feature: TubeFeature,
    plan: IndexedSlicePlan,
    parameters: TubeProcessParameters,
    *,
    model: CadModel | None = None,
) -> GeneratedToolpath:
    """Generate mid-wall circular contours plus explicit safe transitions."""

    if parameters.safe_clearance_mm < max(parameters.bead_width_mm, parameters.layer_height_mm):
        raise TubePlanningError(
            "tube.safe_connection_clearance_insufficient",
            "clearance must cover at least one deposited bead envelope",
        )
    builder = _PathBuilder(operation_id, parameters)
    previous_region: str | None = None
    for layer in plan.layers:
        center, tangent = feature.point_tangent_at(layer.centerline_distance_mm)
        loop = (
            _exact_section_loop(model, feature, layer, parameters.contour_chord_error_mm)
            if model is not None
            else _circular_loop(
                center,
                tangent,
                feature.path_radius_mm,
                parameters.contour_chord_error_mm,
            )
        )
        builder.add_layer(layer, loop, indexed=previous_region not in {None, layer.region_id})
        previous_region = layer.region_id
    return GeneratedToolpath(
        f"{operation_id}-indexed-v1",
        operation_id,
        points=tuple(builder.points),
        events=tuple(builder.events),
    )


class _PathBuilder:
    def __init__(self, operation_id: str, parameters: TubeProcessParameters) -> None:
        self.operation_id = operation_id
        self.parameters = parameters
        self.points: list[ToolpathPoint] = []
        self.events: list[ToolpathEvent] = []
        self._sequence = 0

    def add_layer(
        self,
        layer: TubeSliceLayer,
        loop: tuple[tuple[Vector3, Vector3, Vector3], ...],
        *,
        indexed: bool,
    ) -> None:
        first_position, first_tangent, first_normal = loop[0]
        if self.points:
            self._connect(layer, first_position, first_tangent, first_normal, indexed=indexed)
        else:
            self._append_point(layer, first_position, first_tangent, first_normal, "approach")
            self._event("prime", layer)
        previous = first_position
        for position, tangent, normal in loop[1:]:
            volume = math.dist(previous, position) * (
                self.parameters.bead_width_mm * self.parameters.layer_height_mm
            )
            self._append_point(layer, position, tangent, normal, "deposition", volume)
            previous = position

    def _connect(
        self,
        layer: TubeSliceLayer,
        target: Vector3,
        tangent: Vector3,
        normal: Vector3,
        *,
        indexed: bool,
    ) -> None:
        previous = self.points[-1]
        self._event("retract", layer)
        depart = _subtract(
            previous.position, _scale(previous.nozzle_axis, self.parameters.safe_clearance_mm)
        )
        self._append_point(
            layer, depart, previous.tangent, previous.surface_normal or normal, "depart"
        )
        if indexed:
            self._event("index_start", layer)
        safe_target = _add(target, _scale(normal, self.parameters.safe_clearance_mm))
        self._append_point(layer, safe_target, tangent, normal, "travel")
        if indexed:
            self._event("index_end", layer)
        self._append_point(layer, target, tangent, normal, "approach")
        self._event("prime", layer)

    def _append_point(
        self,
        layer: TubeSliceLayer,
        position: Vector3,
        tangent: Vector3,
        normal: Vector3,
        point_type: str,
        material_volume_mm3: float = 0.0,
    ) -> None:
        self._sequence += 1
        deposition = point_type == "deposition"
        self.points.append(
            ToolpathPoint(
                point_id=f"point-{self._sequence:07d}",
                position=position,
                tangent=tangent,
                nozzle_axis=_scale(normal, -1.0),
                surface_normal=normal,
                operation_id=self.operation_id,
                stage_id=layer.region_id,
                layer_id=layer.layer_id,
                region_id=layer.region_id,
                point_type=point_type,
                extrusion_role="thin_wall" if deposition else "none",
                feedrate_mm_min=(
                    self.parameters.deposition_feedrate_mm_min
                    if deposition
                    else self.parameters.travel_feedrate_mm_min
                ),
                bead_width_mm=self.parameters.bead_width_mm if deposition else None,
                layer_height_mm=self.parameters.layer_height_mm if deposition else None,
                material_volume_mm3=material_volume_mm3,
            )
        )

    def _event(self, event_type: str, layer: TubeSliceLayer) -> None:
        context: dict[str, float | int] = {"sequence_index": self._sequence}
        if event_type in {"retract", "prime"}:
            sign = -1.0 if event_type == "retract" else 1.0
            context["extrusion_length_mm"] = sign * self.parameters.retract_length_mm
        self.events.append(
            ToolpathEvent(
                event_id=f"event-{len(self.events) + 1:07d}",
                event_type=event_type,
                operation_id=self.operation_id,
                stage_id=layer.region_id,
                layer_id=layer.layer_id,
                region_id=layer.region_id,
                context=context,
            )
        )


def _build_regions(feature: TubeFeature, parameters: TubeProcessParameters) -> list[TubeRegion]:
    result: list[TubeRegion] = []
    walked = 0.0
    for primitive in feature.centerline:
        count = _primitive_region_count(primitive, parameters)
        for index in range(count):
            start = walked + primitive.length_mm * index / count
            end = walked + primitive.length_mm * (index + 1) / count
            _point, direction = feature.point_tangent_at((start + end) * 0.5)
            angle = abs(primitive.sweep_rad) / count if primitive.kind == "arc" else 0.0
            radius = _arc_radius(primitive)
            error = 0.0 if radius is None else radius * (1.0 - math.cos(angle * 0.5))
            result.append(
                TubeRegion(
                    f"region-{len(result) + 1:04d}",
                    start,
                    end,
                    direction,
                    angle * 0.5,
                    error,
                    primitive.source_face_id,
                )
            )
        walked += primitive.length_mm
    return result


def _primitive_region_count(
    primitive: CenterlinePrimitive, parameters: TubeProcessParameters
) -> int:
    if primitive.kind == "line":
        return 1
    angle = abs(primitive.sweep_rad)
    angle_count = math.ceil(angle / math.radians(parameters.max_wedge_angle_deg))
    radius = _arc_radius(primitive)
    assert radius is not None
    ratio = min(1.0, parameters.max_bead_height_error_mm / radius)
    allowed = 2.0 * math.acos(max(-1.0, 1.0 - ratio))
    error_count = math.ceil(angle / allowed) if allowed > 1.0e-12 else angle_count
    return max(1, angle_count, error_count)


def _arc_radius(primitive: CenterlinePrimitive) -> float | None:
    if primitive.center is None:
        return None
    return math.dist(primitive.start, primitive.center)


def _layer_distances(length: float, height: float) -> tuple[float, ...]:
    count = max(1, math.ceil(length / height))
    result = []
    for index in range(count):
        lower = index * height
        upper = min(length, (index + 1) * height)
        result.append((lower + upper) * 0.5)
    return tuple(result)


def _owning_region(regions: list[TubeRegion], distance: float) -> TubeRegion:
    for index, region in enumerate(regions):
        if distance < region.end_distance_mm - 1.0e-9 or index == len(regions) - 1:
            return region
    return regions[-1]


def _circular_loop(
    center: Vector3, normal: Vector3, radius: float, chord_error: float
) -> tuple[tuple[Vector3, Vector3, Vector3], ...]:
    plane_normal = _unit(normal)
    reference = (1.0, 0.0, 0.0) if abs(plane_normal[0]) < 0.8 else (0.0, 1.0, 0.0)
    u = _unit(_cross(plane_normal, reference))
    v = _unit(_cross(plane_normal, u))
    ratio = min(1.0, chord_error / radius)
    maximum_angle = 2.0 * math.acos(max(-1.0, 1.0 - ratio))
    count = max(12, math.ceil(2.0 * math.pi / maximum_angle))
    result: list[tuple[Vector3, Vector3, Vector3]] = []
    for index in range(count + 1):
        angle = 2.0 * math.pi * index / count
        radial = _add(_scale(u, math.cos(angle)), _scale(v, math.sin(angle)))
        tangent = _add(_scale(u, -math.sin(angle)), _scale(v, math.cos(angle)))
        result.append((_add(center, _scale(radial, radius)), tangent, radial))
    return tuple(result)


def _exact_section_loop(
    model: CadModel, feature: TubeFeature, layer: TubeSliceLayer, chord_error_mm: float
) -> tuple[tuple[Vector3, Vector3, Vector3], ...]:
    section = section_tube_layer(
        model,
        feature.tube_body_id,
        layer.plane_origin,
        layer.plane_normal,
        feature.wall_thickness_mm,
        chord_error_mm=chord_error_mm,
    )
    result: list[tuple[Vector3, Vector3, Vector3]] = []
    for index, (position, normal) in enumerate(zip(section.midwall, section.normals)):
        previous = section.midwall[index - 1]
        following = section.midwall[(index + 1) % len(section.midwall)]
        tangent = _unit(_subtract(following, previous))
        result.append((position, tangent, normal))
    return tuple(result)


def _unit(value: Vector3) -> Vector3:
    length = math.sqrt(sum(item * item for item in value))
    if length <= 1.0e-12:
        raise ValueError("zero-length vector")
    return _scale(value, 1.0 / length)


def _add(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a + b for a, b in zip(left, right))  # type: ignore[return-value]


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(left, right))  # type: ignore[return-value]


def _scale(value: Vector3, factor: float) -> Vector3:
    return tuple(item * factor for item in value)  # type: ignore[return-value]


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


__all__ = [
    "IndexedSlicePlan",
    "TubePlanningError",
    "TubeRegion",
    "TubeSliceLayer",
    "generate_indexed_toolpath",
    "plan_indexed_slices",
]
