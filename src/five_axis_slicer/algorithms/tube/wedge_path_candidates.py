"""Fixed-axis centre-column residual candidates, never ready deposition paths."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ...models import Vector3
from .wedge_layers import LayerBand, _project
from .wedge_material import _dot, _vector


@dataclass(frozen=True, slots=True)
class ResidualPoint:
    position: Vector3
    height_mm: float
    build_axis: Vector3


@dataclass(frozen=True, slots=True)
class ResidualTask:
    start: Vector3 | None
    end: Vector3 | None
    reason: str = "no_positive_center_column_check_finite_width_material"


@dataclass(frozen=True, slots=True)
class WedgePathCandidates:
    paths: tuple[tuple[ResidualPoint, ...], ...]
    residual_tasks: tuple[ResidualTask, ...]
    ready_for_export: bool = False
    limitations: tuple[str, ...] = (
        "zero_height_endpoints_are_geometric_boundaries_not_deposition_commands",
        "section_midwall_does_not_prove_full_band_cad_coverage",
        "finite_width_residual_shape_and_support_not_verified",
    )


def _heights(band: LayerBand, point: Vector3) -> tuple[float, float]:
    base = _project(point, band.origin, band.build_axis)
    entry, exit_plane = band.boundary.entry_plane, band.boundary.exit_plane
    a, b = _dot(band.build_axis, entry.normal), _dot(band.build_axis, exit_plane.normal)
    if min(a, b) <= 1e-12:
        raise ValueError("candidate axis must advance through both boundary planes")
    return (-band.boundary.entry_halfspace.signed_distance(base) / a,
            band.boundary.exit_halfspace.signed_distance(base) / b)


def _at(start: Vector3, end: Vector3, t: float) -> Vector3:
    if t == 0:
        return start
    if t == 1:
        return end
    return _vector(tuple((1 - t) * a + t * b for a, b in zip(start, end, strict=True)), "point")


def _breaks(band: LayerBand, start: Vector3, end: Vector3) -> list[float]:
    first, last = _heights(band, start), _heights(band, end)
    functions = [(first[0], last[0]), (first[1], last[1]),
                 (band.lower_mm, band.lower_mm), (band.upper_mm, band.upper_mm)]
    result = {0.0, 1.0}
    for i, a in enumerate(functions):
        for b in functions[i + 1:]:
            left, right = a[0] - b[0], a[1] - b[1]
            if left != right:
                t = left / (left - right)
                if 0 < t < 1:
                    result.add(t)
    return sorted(result)


def _point(band: LayerBand, point: Vector3) -> ResidualPoint:
    low, high = _heights(band, point)
    low, high = max(low, band.lower_mm), min(high, band.upper_mm)
    base = _project(point, band.origin, band.build_axis)
    center = low + (high - low) / 2
    position = _vector(tuple(p + center * n for p, n in zip(base, band.build_axis, strict=True)),
                       "candidate position")
    return ResidualPoint(position, max(0.0, high - low), band.build_axis)


def build_path_candidates(band: LayerBand, midwall: Sequence[Vector3]) -> WedgePathCandidates:
    """Split actual input segments at every affine column-height topology break.

    Positive residual columns survive even if the supplied nominal midplane is
    above their top. No missing CAD contours are invented. Excluded segments
    remain explicit tasks because their finite-width corners may contain
    material. A supplied closed seam is rejoined only when both seam sides are
    positive; no closing chord is introduced across excluded geometry.
    """
    vertices = tuple(_vector(p, "midwall point") for p in midwall)
    if len(vertices) < 2:
        task = ResidualTask(None, None, "missing_section_midwall_check_full_band_cad_residual")
        return WedgePathCandidates((), (task,))
    paths: list[list[ResidualPoint]] = []
    tasks: list[ResidualTask] = []
    current: list[ResidualPoint] = []
    for start, end in zip(vertices, vertices[1:]):
        if start == end:
            continue
        breaks = _breaks(band, start, end)
        for left, right in zip(breaks, breaks[1:]):
            a, b = _at(start, end, left), _at(start, end, right)
            middle = _point(band, _at(start, end, (left + right) / 2))
            if middle.height_mm <= 0:
                if current:
                    paths.append(current)
                    current = []
                tasks.append(ResidualTask(a, b))
                continue
            pa, pb = _point(band, a), _point(band, b)
            if not current:
                current = [pa]
            elif current[-1] != pa:
                paths.append(current)
                current = [pa]
            current.append(pb)
    if current:
        paths.append(current)
    if len(paths) > 1 and vertices[0] == vertices[-1] and paths[-1][-1] == paths[0][0]:
        paths = [paths[-1] + paths[0][1:], *paths[1:-1]]
    return WedgePathCandidates(tuple(tuple(path) for path in paths), tuple(tasks))


__all__ = ["ResidualPoint", "ResidualTask", "WedgePathCandidates", "build_path_candidates"]
