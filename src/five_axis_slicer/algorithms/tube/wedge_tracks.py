"""Attach wall-track widths to bounded-column candidates without qualification."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

from ...models import Vector3
from .bounded_wedge_paths import build_bounded_candidates
from .wall_tracks import WallTrackPoint
from .wedge_layers import LayerBand, _project
from .wedge_path_candidates import ResidualTask


@dataclass(frozen=True, slots=True)
class WedgeTrackPoint:
    position: Vector3
    height_mm: float
    width_mm: float
    outward_normal: Vector3
    build_axis: Vector3


@dataclass(frozen=True, slots=True)
class WedgeTrackCandidates:
    paths: tuple[tuple[WedgeTrackPoint, ...], ...]
    residual_tasks: tuple[ResidualTask, ...]
    ready_for_export: bool = False
    limitations: tuple[str, ...] = (
        "finite_width_volume_coverage_support_and_collision_not_verified",
        "interpolated_section_width_not_calibrated_printability",
    )


def _unit(normal: Vector3) -> Vector3:
    length = math.hypot(*normal)
    if len(normal) != 3 or not math.isfinite(length) or length <= 1e-12:
        raise ValueError("wall-track normal must be finite and nonzero")
    return tuple(v / length for v in normal)  # type: ignore[return-value]


def _attributes(
    position: Vector3, projected: tuple[Vector3, ...], track: Sequence[WallTrackPoint],
) -> tuple[float, Vector3]:
    matches = []
    for index, (a, b) in enumerate(zip(projected, projected[1:])):
        delta = tuple(y - x for x, y in zip(a, b))
        length2 = math.fsum(v * v for v in delta)
        if length2 <= 1e-24:
            continue
        t = max(0., min(1., math.fsum((p - x) * v for p, x, v in zip(position, a, delta)) / length2))
        nearest = tuple(x + t * v for x, v in zip(a, delta))
        distance = math.dist(position, nearest)
        if distance <= 1e-8:
            first, last = track[index], track[index + 1]
            width = (1 - t) * first.width_mm + t * last.width_mm
            normal = _unit(tuple((1 - t) * x + t * y for x, y in zip(
                first.outward_normal, last.outward_normal)))  # type: ignore[arg-type]
            matches.append((distance, width, normal))
    if not matches:
        raise ValueError("bounded point has no matching projected wall-track segment")
    _, width, normal = min(matches, key=lambda item: item[0])
    if any(abs(w - width) > 1e-8 or math.dist(n, normal) > 1e-8 for _, w, n in matches):
        raise ValueError("ambiguous overlapping wall-track attributes")
    return width, normal


def build_wedge_tracks(
    band: LayerBand, track: Sequence[WallTrackPoint], nominal_height: float,
) -> WedgeTrackCandidates:
    """Reuse bounded geometry; recover attributes only on matching projections."""
    for point in track:
        if not math.isfinite(point.width_mm) or point.width_mm <= 0:
            raise ValueError("wall-track width must be finite and positive")
        if len(point.position) != 3 or not all(math.isfinite(v) for v in point.position):
            raise ValueError("wall-track positions must be finite 3D points")
        _unit(point.outward_normal)
    positions = tuple(p.position for p in track)
    projected = tuple(_project(p, band.origin, band.build_axis) for p in positions)
    bounded = build_bounded_candidates(band, positions, nominal_height)
    paths = []
    for path in bounded.paths:
        points = []
        for residual in path:
            width, normal = _attributes(_project(residual.position, band.origin, band.build_axis), projected, track)
            points.append(WedgeTrackPoint(residual.position, residual.height_mm, width, normal, residual.build_axis))
        paths.append(tuple(points))
    return WedgeTrackCandidates(tuple(paths), bounded.residual_tasks)

