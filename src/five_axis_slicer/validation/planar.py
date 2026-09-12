"""Independent polygon, bead-envelope, coverage and material checks."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ..algorithms.planar.region import PlanarSliceLayer
from ..manufacturing.toolpath import GeneratedToolpath
from .planar_geometry import (
    boundary_edges,
    polygon_area,
    sample_region_coverage,
    segment_outside,
    valid_grid,
)


@dataclass(frozen=True, slots=True)
class PlanarToolpathMeasurement:
    """XY capsule coverage and rectangular width × height commanded volume.

    Area sampling is reported with its resolution; it is not a physical bead
    simulation. Target solid volume is independently integrated from sections,
    and is a reference only for intentionally sparse or wall-only operations.
    """

    deposition_outside_max_mm: float
    covered_area_mm2: float
    residual_area_mm2: float
    sampled_region_area_mm2: float
    material_volume_mm3: float
    geometric_volume_mm3: float
    volume_difference_mm3: float
    bead_outside_max_mm: float = 0.0
    overlap_area_mm2: float = 0.0
    geometric_region_area_mm2: float = 0.0
    target_solid_volume_mm3: float = 0.0
    material_excess_mm3: float = 0.0
    sample_grid_mm: float = 0.0
    # layer, region, target volume, path volume, boundary perimeter
    region_volumes: tuple[tuple[str, str, float, float, float], ...] = ()
    absolute_volume_difference_mm3: float = 0.0


def measure_planar_toolpath(
    toolpath: GeneratedToolpath,
    layers: tuple[PlanarSliceLayer, ...],
    *,
    grid_mm: float | None = None,
    layer_height_mm: float | None = None,
) -> PlanarToolpathMeasurement:
    """Check full segment clearance independently of offset/hatch generation."""
    regions = {
        (layer.layer_id, region.region_id): region for layer in layers for region in layer.regions
    }
    deposited, material, geometric, heights, commanded, absolute_error = _deposition_segments(
        toolpath, regions
    )
    widths = [item[4] for segments in deposited.values() for item in segments]
    cell = valid_grid(grid_mm if grid_mm is not None else min(0.25, min(widths, default=0.75) / 3))
    if layer_height_mm is not None:
        valid_grid(layer_height_mm)
    outside = bead_outside = sampled = covered = overlap = area = target = 0.0
    volumes = []
    for key, region in regions.items():
        segments = deposited.get(key, [])
        edges = boundary_edges(region)
        for _, _, a, b, width, _ in segments:
            centre, bead = segment_outside(a, b, width, region, edges)
            outside, bead_outside = max(outside, centre), max(bead_outside, bead)
        domain, filled, doubled = sample_region_coverage(region, segments, cell)
        sampled, covered, overlap = sampled + domain, covered + filled, overlap + doubled
        region_area = polygon_area(region)
        area += region_area
        height = layer_height_mm if layer_height_mm is not None else heights.get(key[0], 0.0)
        target += region_area * height
        volumes.append((*key, region_area * height, commanded.get(key, 0.0), _perimeter(region)))
    return PlanarToolpathMeasurement(
        outside,
        covered,
        max(0.0, sampled - covered),
        sampled,
        material,
        geometric,
        material - geometric,
        bead_outside,
        overlap,
        area,
        target,
        max(0.0, material - target),
        cell,
        tuple(volumes),
        absolute_error,
    )


def _perimeter(region):
    return sum(
        math.dist(a, b) for loop in (region.outer, *region.holes) for a, b in zip(loop, loop[1:])
    )


def _deposition_segments(toolpath, regions):
    deposited: dict = {}
    heights: dict[str, float] = {}
    commanded: dict = {}
    material = geometric = absolute_error = 0.0
    stroke = 0
    for previous, current in zip(toolpath.points, toolpath.points[1:], strict=False):
        if current.point_type != "deposition":
            stroke += 1
            continue
        key = (current.layer_id, current.region_id)
        if key not in regions:
            raise ValueError(f"planar.measurement_region_missing: {key}")
        width, height = current.bead_width_mm or 0.0, current.layer_height_mm or 0.0
        if width <= 0 or height <= 0:
            raise ValueError(f"planar.measurement_bead_dimensions_missing: {current.point_id}")
        if current.layer_id in heights and abs(heights[current.layer_id] - height) > 1e-9:
            raise ValueError("planar.measurement_layer_height_inconsistent")
        heights[current.layer_id] = height
        material += current.material_volume_mm3
        expected = math.dist(previous.position, current.position) * width * height
        geometric += expected
        absolute_error += abs(current.material_volume_mm3 - expected)
        commanded[key] = commanded.get(key, 0.0) + current.material_volume_mm3
        deposited.setdefault(key, []).append(
            (*key, previous.position, current.position, width, stroke)
        )
    return deposited, material, geometric, heights, commanded, absolute_error
