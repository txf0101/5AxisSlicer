"""Independent finite-width measurements in a common cylindrical arc-length chart.

Each bead is a union of round-ended strips. Area values are grid estimates;
the largest empty disk also has a spatial sampling bound. This is an offline
geometric model, not a thermal or physical bonding simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from ..algorithms.planar.region import PlanarRegion
from .planar_geometry import boundary_edges, inside_points, point_segment_distances, valid_grid


@dataclass(frozen=True, slots=True)
class BeadSegment:
    start: tuple[float, float]
    end: tuple[float, float]
    width_mm: float
    stroke_id: str

    def __post_init__(self) -> None:
        values = (*self.start, *self.end, self.width_mm)
        if len(self.start) != 2 or len(self.end) != 2 or not all(map(math.isfinite, values)):
            raise ValueError("fan.coverage_invalid_segment")
        if self.width_mm <= 0 or not self.stroke_id:
            raise ValueError("fan.coverage_invalid_bead")


@dataclass(frozen=True, slots=True)
class CoverageMeasurement:
    grid_mm: float
    sampled_area_mm2: float
    covered_area_mm2: float
    outside_area_mm2: float
    overlapping_strokes_area_mm2: float
    empty_disk_diameter_lower_mm: float
    empty_disk_diameter_upper_mm: float
    deposited_sample_count: int
    unsupported_area_mm2: float | None


def _distances(points, segments):
    clearance = np.full(len(points), np.inf)
    strokes: dict[str, np.ndarray] = {}
    for segment in segments:
        distance = (
            point_segment_distances(points, np.asarray(segment.start), np.asarray(segment.end))
            - segment.width_mm / 2
        )
        clearance = np.minimum(clearance, distance)
        mask = strokes.setdefault(segment.stroke_id, np.zeros(len(points), dtype=bool))
        mask |= distance <= 1e-12
    counts = np.zeros(len(points), dtype=np.uint32)
    for mask in strokes.values():
        counts += mask
    return clearance, counts


def _grid(region, segments, cell):
    bounds = np.asarray(region.outer)[:, :2]
    low, high = bounds.min(axis=0), bounds.max(axis=0)
    if not np.all(np.isfinite(bounds)) or np.any(high <= low):
        raise ValueError("fan.coverage_invalid_domain")
    for segment in segments:
        ends = np.asarray((segment.start, segment.end))
        low = np.minimum(low, ends.min(axis=0) - segment.width_mm / 2)
        high = np.maximum(high, ends.max(axis=0) + segment.width_mm / 2)
    nx, ny = (int(math.ceil(value / cell)) for value in high - low)
    dx, dy = (high - low) / (nx, ny)
    x = low[0] + (np.arange(nx) + 0.5) * dx
    for row in range(ny):
        points = np.column_stack((x, np.full(nx, low[1] + (row + 0.5) * dy)))
        yield points, float(dx * dy), float(math.hypot(dx, dy) / 2)


def measure_chart_coverage(
    region: PlanarRegion,
    segments: tuple[BeadSegment, ...],
    *,
    grid_mm: float,
    previous_segments: tuple[BeadSegment, ...] | None = None,
    current_radius_mm: float | None = None,
    previous_radius_mm: float | None = None,
    layer_height_mm: float | None = None,
) -> CoverageMeasurement:
    """Measure a solid target and optionally its preceding deposited layer.

    Both charts must use the same axis, seam and angular origin; u = radius *
    theta, v = axial position. Previous footprints are evaluated at the same
    angle, preserving their original physical width. None means unmeasured
    support; an empty previous tuple means no existing deposited material.
    """
    cell = valid_grid(grid_mm)
    scale = _support_scale(
        previous_segments, current_radius_mm, previous_radius_mm, layer_height_mm
    )
    area = covered = outside = overlap = unsupported = max_disk_radius = uncertainty = 0.0
    deposited = 0
    edges = boundary_edges(region)
    for points, pixel_area, uncertainty in _grid(region, segments, cell):
        inside = inside_points(points, region)
        clearance, counts = _distances(points, segments)
        boundary_distance = np.full(len(points), np.inf)
        for start, end in zip(*edges):
            boundary_distance = np.minimum(
                boundary_distance, point_segment_distances(points, start, end)
            )
        # A disk contained in the target excludes holes and exterior material.
        disk = np.where(inside, np.maximum(0, np.minimum(clearance, boundary_distance)), 0)
        max_disk_radius = max(max_disk_radius, float(np.max(disk)))
        mask = inside & (counts > 0)
        deposited += int(np.count_nonzero(mask))
        area += np.count_nonzero(inside) * pixel_area
        covered += np.count_nonzero(mask) * pixel_area
        outside += np.count_nonzero(~inside & (counts > 0)) * pixel_area
        overlap += np.count_nonzero(inside & (counts > 1)) * pixel_area
        if previous_segments is not None:
            projected = points[mask] * (scale, 1.0)
            _, previous_counts = _distances(projected, previous_segments)
            unsupported += np.count_nonzero(previous_counts == 0) * pixel_area
    return CoverageMeasurement(
        cell,
        float(area),
        float(covered),
        float(outside),
        float(overlap),
        2 * max_disk_radius,
        2 * (max_disk_radius + uncertainty),
        deposited,
        float(unsupported) if previous_segments is not None else None,
    )


def _support_scale(previous, current_radius, previous_radius, height):
    if previous is None:
        return 1.0
    values = (current_radius, previous_radius, height)
    if any(value is None or not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError("fan.support_radii_and_height_required")
    if not math.isclose(current_radius - previous_radius, height, abs_tol=1e-9, rel_tol=0):
        raise ValueError("fan.support_nonadjacent_layer")
    return previous_radius / current_radius
