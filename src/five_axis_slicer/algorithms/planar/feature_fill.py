"""Shared shell, skin, and internal-fill classification for planar layer domains."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ...models import Vector3
from .offset import PlanarOffsetError, inset_region
from .region import PlanarRegion, PlanarSliceLayer
from .zigzag import _hatch_segments

Segment3 = tuple[Vector3, Vector3]


@dataclass(frozen=True, slots=True)
class FeatureFillParameters:
    bead_width_mm: float = 0.4
    wall_count: int = 2
    infill_fraction: float = 0.2
    top_solid_layers: int = 4
    bottom_solid_layers: int = 4
    alternate_angle_deg: float = 90.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.bead_width_mm) or self.bead_width_mm <= 0.0:
            raise ValueError("bead_width_mm must be finite and positive")
        if isinstance(self.wall_count, bool) or self.wall_count < 1:
            raise ValueError("wall_count must be a positive integer")
        if not math.isfinite(self.infill_fraction) or not 0.0 <= self.infill_fraction <= 1.0:
            raise ValueError("infill_fraction must be between zero and one")
        for name in ("top_solid_layers", "bottom_solid_layers"):
            value = getattr(self, name)
            if isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class FeatureRegionPlan:
    layer_id: str
    region_id: str
    feature_type: str
    wall_contours: tuple[tuple[Vector3, ...], ...]
    internal_regions: tuple[PlanarRegion, ...]
    infill_segments: tuple[Segment3, ...]
    infill_fraction: float


@dataclass(frozen=True, slots=True)
class FeatureLayerPlan:
    layer_id: str
    z_mm: float
    regions: tuple[FeatureRegionPlan, ...]
    is_bottom_skin: bool
    is_top_skin: bool


def plan_feature_fill(
    layers: tuple[PlanarSliceLayer, ...], parameters: FeatureFillParameters
) -> tuple[FeatureLayerPlan, ...]:
    """Partition every layer into walls, solid skin, and remaining infill.

    Empty section layers stay in the result.  A region consumed by its walls is
    explicitly classified as ``thin_wall`` and receives no intersecting hatch.
    """

    if not layers:
        raise ValueError("at least one layer is required")
    occupied = [index for index, layer in enumerate(layers) if layer.regions]
    if not occupied:
        return tuple(
            FeatureLayerPlan(layer.layer_id, layer.z_mm, (), False, False) for layer in layers
        )
    bottom = set(occupied[: parameters.bottom_solid_layers])
    top = set(occupied[-parameters.top_solid_layers :]) if parameters.top_solid_layers else set()
    result = []
    cache: dict[object, FeatureRegionPlan] = {}
    geometry_cache: dict[
        object, tuple[tuple[tuple[Vector3, ...], ...], tuple[PlanarRegion, ...]]
    ] = {}
    for index, layer in enumerate(layers):
        is_skin = index in bottom or index in top
        fraction = 1.0 if is_skin else parameters.infill_fraction
        angle = 0.0 if index % 2 == 0 else parameters.alternate_angle_deg
        plans = []
        for region in layer.regions:
            geometry_key = _region_xy_key(region)
            key = (geometry_key, fraction, angle, is_skin)
            template = cache.get(key)
            if template is None:
                partition = geometry_cache.get(geometry_key)
                if partition is None:
                    partition = _partition_region(region, parameters)
                    geometry_cache[geometry_key] = partition
                template = _plan_region(
                    layer, region, partition, parameters, fraction, angle, is_skin
                )
                cache[key] = template
            plans.append(_relocate_plan(template, layer, region))
        result.append(
            FeatureLayerPlan(
                layer.layer_id, layer.z_mm, tuple(plans), index in bottom, index in top
            )
        )
    return tuple(result)


def _plan_region(
    layer: PlanarSliceLayer,
    region: PlanarRegion,
    partition: tuple[tuple[tuple[Vector3, ...], ...], tuple[PlanarRegion, ...]],
    parameters: FeatureFillParameters,
    fraction: float,
    angle_deg: float,
    is_skin: bool,
) -> FeatureRegionPlan:
    walls, internal = partition
    segments: list[Segment3] = []
    if internal and fraction > 0.0:
        spacing = (
            parameters.bead_width_mm if fraction >= 1.0 else parameters.bead_width_mm / fraction
        )
        for island in internal:
            segments.extend(_angled_hatch(island, spacing, angle_deg))
    if not internal:
        feature_type = "thin_wall"
    elif fraction <= 0.0:
        feature_type = "shell_only"
    elif fraction >= 1.0:
        feature_type = "solid_skin" if is_skin else "solid_infill"
    else:
        feature_type = "sparse_infill"
    return FeatureRegionPlan(
        layer.layer_id,
        region.region_id,
        feature_type,
        walls,
        internal,
        tuple(segments),
        fraction,
    )


def _partition_region(
    region: PlanarRegion, parameters: FeatureFillParameters
) -> tuple[tuple[tuple[Vector3, ...], ...], tuple[PlanarRegion, ...]]:
    walls: list[tuple[Vector3, ...]] = []
    for pass_index in range(parameters.wall_count):
        distance = (pass_index + 0.5) * parameters.bead_width_mm
        islands = inset_region(region, distance)
        for island in islands:
            walls.extend((island.outer, *island.holes))
    internal = inset_region(region, parameters.wall_count * parameters.bead_width_mm)
    if not walls and not internal:
        raise PlanarOffsetError(
            "planar.feature_below_bead_width",
            f"{region.region_id}: no inset centreline fits the requested bead width",
        )
    return tuple(walls), tuple(internal)


def _relocate_plan(template, layer, source_region):
    def move_loop(loop):
        return tuple((point[0], point[1], layer.z_mm) for point in loop)

    internal = tuple(
        PlanarRegion(
            f"{source_region.region_id}-internal-{index:04d}",
            move_loop(region.outer),
            tuple(move_loop(hole) for hole in region.holes),
        )
        for index, region in enumerate(template.internal_regions, 1)
    )
    return FeatureRegionPlan(
        layer.layer_id,
        source_region.region_id,
        template.feature_type,
        tuple(move_loop(loop) for loop in template.wall_contours),
        internal,
        tuple(
            (move_loop((left,))[0], move_loop((right,))[0])
            for left, right in template.infill_segments
        ),
        template.infill_fraction,
    )


def _region_xy_key(region):
    return (
        tuple((round(point[0], 7), round(point[1], 7)) for point in region.outer),
        tuple(
            tuple((round(point[0], 7), round(point[1], 7)) for point in hole)
            for hole in region.holes
        ),
    )


def _angled_hatch(region: PlanarRegion, spacing: float, angle_deg: float) -> tuple[Segment3, ...]:
    angle = math.radians(angle_deg % 180.0)
    cosine, sine = math.cos(angle), math.sin(angle)

    def into(point: Vector3) -> Vector3:
        return (cosine * point[0] + sine * point[1], -sine * point[0] + cosine * point[1], point[2])

    def out(point: tuple[float, float]) -> Vector3:
        return (
            cosine * point[0] - sine * point[1],
            sine * point[0] + cosine * point[1],
            region.outer[0][2],
        )

    rotated = PlanarRegion(
        region.region_id,
        tuple(into(point) for point in region.outer),
        tuple(tuple(into(point) for point in hole) for hole in region.holes),
    )
    return tuple((out(left), out(right)) for left, right in _hatch_segments(rotated, spacing))


__all__ = [
    "FeatureFillParameters",
    "FeatureLayerPlan",
    "FeatureRegionPlan",
    "plan_feature_fill",
]
