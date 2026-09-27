"""Candidate paths with terminal-column redistribution and explicit breaks."""

from __future__ import annotations

import math
from collections.abc import Sequence

from ...models import Vector3
from .column_partition import partition_column
from .wedge_layers import LayerBand, _project
from .wedge_material import _vector
from .wedge_path_candidates import (
    ResidualPoint, ResidualTask, WedgePathCandidates, _at, _heights,
)


def _breaks(first: float, last: float, index: int, height: float) -> list[float]:
    result = {0.0, 1.0}
    if first != last:
        for threshold in ((index + 0.5) * height, (index + 1.5) * height):
            t = (threshold - first) / (last - first)
            if 0 < t < 1:
                result.add(t)
    return sorted(result)


def _point(band: LayerBand, point: Vector3, height: float, terminal: bool) -> ResidualPoint:
    low, high = _heights(band, point)
    lower = low + band.index * height
    upper = high if terminal else lower + height
    base = _project(point, band.origin, band.build_axis)
    center = (lower + upper) / 2
    position = _vector(tuple(p + center * n for p, n in zip(base, band.build_axis, strict=True)), "position")
    return ResidualPoint(position, upper - lower, band.build_axis)


def build_bounded_candidates(
    band: LayerBand, midwall: Sequence[Vector3], nominal_height: float,
) -> WedgePathCandidates:
    """Keep one-sided endpoints at thickness jumps; never extrude across them.

    The section contour remains an input approximation. This does not establish
    finite-width material coverage, collision clearance or printable limits.
    """
    if not math.isfinite(nominal_height) or nominal_height <= 0:
        raise ValueError("nominal height must be positive and finite")
    if len(midwall) < 2:
        return WedgePathCandidates((), (ResidualTask(None, None, "missing_section_midwall"),))
    paths: list[list[ResidualPoint]] = []
    tasks: list[ResidualTask] = []
    for start, end in zip(midwall, midwall[1:]):
        if start == end:
            continue
        first, last = _heights(band, start), _heights(band, end)
        breaks = _breaks(first[1] - first[0], last[1] - last[0], band.index, nominal_height)
        for left, right in zip(breaks, breaks[1:]):
            a, b = _at(start, end, left), _at(start, end, right)
            low, high = _heights(band, _at(start, end, (left + right) / 2))
            partition = partition_column(low, high, nominal_height)
            if partition.interval(band.index) is None:
                tasks.append(ResidualTask(a, b, "column_has_no_layer_check_finite_width"))
                continue
            terminal = partition.count == band.index + 1
            pa, pb = _point(band, a, nominal_height, terminal), _point(band, b, nominal_height, terminal)
            if paths and paths[-1][-1] == pa:
                paths[-1].append(pb)
            else:
                paths.append([pa, pb])
    if len(paths) > 1 and midwall[0] == midwall[-1] and paths[-1][-1] == paths[0][0]:
        paths = [paths[-1] + paths[0][1:], *paths[1:-1]]
    return WedgePathCandidates(tuple(tuple(path) for path in paths), tuple(tasks), limitations=(
        "half_layer_threshold_is_geometric_not_calibrated",
        "section_midwall_does_not_prove_full_band_cad_coverage",
        "finite_width_residual_shape_and_support_not_verified",
    ))
