"""Independent polygon and bead-sweep measurements; no path-generation helpers."""

from __future__ import annotations

import math

import numpy as np

from ..algorithms.planar.region import PlanarRegion


def polygon_area(region: PlanarRegion) -> float:
    def area(loop):
        return abs(sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(loop, loop[1:]))) / 2

    return area(region.outer) - sum(area(hole) for hole in region.holes)


def boundary_edges(region: PlanarRegion):
    edges = [
        (a[:2], b[:2]) for loop in (region.outer, *region.holes) for a, b in zip(loop, loop[1:])
    ]
    values = np.asarray(edges, dtype=float)
    return values[:, 0], values[:, 1]


def point_segment_distances(points, a, b):
    delta = b - a
    length2 = np.sum(delta * delta, axis=-1)
    fraction = np.sum((points - a) * delta, axis=-1) / np.maximum(length2, 1e-30)
    return np.linalg.norm(points - (a + np.clip(fraction, 0, 1)[..., None] * delta), axis=-1)


def inside_points(points, region: PlanarRegion):
    result = np.zeros(len(points), dtype=bool)
    on_boundary = np.zeros(len(points), dtype=bool)
    x, y = points[:, 0], points[:, 1]
    for a, b in zip(*boundary_edges(region)):
        on_boundary |= point_segment_distances(points, a, b) <= 1e-8
        if a[1] != b[1]:
            result ^= ((a[1] > y) != (b[1] > y)) & (
                x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]
            )
    return result | on_boundary


def segment_clearance(a, b, edges) -> float:
    """Exact minimum XY distance to every polygon boundary segment."""
    a, b = np.asarray(a[:2]), np.asarray(b[:2])
    c, d = edges
    minimum = min(
        float(np.min(point_segment_distances(c, a, b))),
        float(np.min(point_segment_distances(d, a, b))),
        float(np.min(point_segment_distances(a, c, d))),
        float(np.min(point_segment_distances(b, c, d))),
    )
    direction, other = b - a, d - c
    denominator = direction[0] * other[:, 1] - direction[1] * other[:, 0]
    valid = np.abs(denominator) > 1e-14
    difference = c[valid] - a
    t = (difference[:, 0] * other[valid, 1] - difference[:, 1] * other[valid, 0]) / denominator[
        valid
    ]
    u = (difference[:, 0] * direction[1] - difference[:, 1] * direction[0]) / denominator[valid]
    if np.any((t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)):
        return 0.0
    return minimum


def segment_outside(a, b, width, region: PlanarRegion, edges) -> tuple[float, float]:
    samples = np.linspace(np.asarray(a[:2]), np.asarray(b[:2]), 17)
    outside = samples[~inside_points(samples, region)]
    centre_error = 0.0
    for point in outside:
        centre_error = max(centre_error, float(np.min(point_segment_distances(point, *edges))))
    clearance = segment_clearance(a, b, edges)
    bead_error = max(0.0, width / 2 - clearance, centre_error + width / 2 if len(outside) else 0)
    return centre_error, bead_error


def sample_region_coverage(region, segments, cell):
    """Count unions of continuous strokes, avoiding false overlap at tessellation joints."""
    outer = np.asarray(region.outer)
    low, high = outer[:, :2].min(axis=0), outer[:, :2].max(axis=0)
    x = np.arange(low[0] + cell / 2, high[0], cell)
    y = np.arange(low[1] + cell / 2, high[1], cell)
    strokes: dict[int, list] = {}
    for segment in segments:
        strokes.setdefault(segment[5], []).append(segment)
    sampled = covered = overlap = 0
    # Bound memory even when a caller requests a fine grid over a large part.
    for row in range(0, len(y), max(1, 65536 // max(1, len(x)))):
        ys = y[row : row + max(1, 65536 // max(1, len(x)))]
        xx, yy = np.meshgrid(x, ys)
        points = np.column_stack((xx.ravel(), yy.ravel()))
        points = points[inside_points(points, region)]
        counts = np.zeros(len(points), dtype=np.uint32)
        for stroke in strokes.values():
            mask = np.zeros(len(points), dtype=bool)
            for _, _, a, b, width, _ in stroke:
                mask |= (
                    point_segment_distances(points, np.asarray(a[:2]), np.asarray(b[:2]))
                    <= width / 2 + 1e-9
                )
            counts += mask
        sampled += len(points)
        covered += int(np.count_nonzero(counts))
        overlap += int(np.count_nonzero(counts > 1))
    return tuple(value * cell * cell for value in (sampled, covered, overlap))


def valid_grid(value: float) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError("planar.measurement_grid_invalid")
    return value
