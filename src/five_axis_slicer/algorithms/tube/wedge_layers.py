"""Fixed-axis candidate layer bands over a supplied full wedge footprint.

The caller must provide a convex footprint enclosing the complete CAD region
projection. This module does not recover that footprint, generate beads, or
qualify support. Boundary heights are affine, so their extrema occur at its
vertices; centreline-only bounds are explicitly not accepted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

from ...models import Vector3
from .wedge_boundary import column_interval
from .wedge_material import _dot, _unit, _vector
from .wedge_plan import WedgeRegionBoundary


@dataclass(frozen=True, slots=True)
class LayerBand:
    region_id: str
    index: int
    origin: Vector3
    build_axis: Vector3
    lower_mm: float
    upper_mm: float
    boundary: WedgeRegionBoundary

    @property
    def center_mm(self) -> float:
        return self.lower_mm + (self.upper_mm - self.lower_mm) / 2

    def column(self, point: Vector3) -> tuple[float, float] | None:
        """Effective axial interval; point is projected into the origin plane."""
        base = _project(_vector(point, "point"), self.origin, self.build_axis)
        return column_interval(
            base,
            self.build_axis,
            self.lower_mm,
            self.upper_mm,
            (self.boundary.entry_halfspace, self.boundary.exit_halfspace),
        )


@dataclass(frozen=True, slots=True)
class WedgeLayerCandidates:
    bands: tuple[LayerBand, ...]
    axial_min_mm: float
    axial_max_mm: float
    footprint: tuple[Vector3, ...]
    ready_for_export: bool = False
    limitations: tuple[str, ...] = (
        "caller_must_verify_full_cad_footprint_coverage",
        "bands_are_geometric_candidates_not_deposited_paths",
        "finite_width_residual_volume_and_support_not_verified",
    )


def _project(point: Vector3, origin: Vector3, axis: Vector3) -> Vector3:
    delta: Vector3 = tuple(a - b for a, b in zip(point, origin, strict=True))  # type: ignore[assignment]
    height = _dot(delta, axis)
    return _vector(tuple(p - height * n for p, n in zip(point, axis, strict=True)), "projection")


def plan_layer_bands(
    boundary: WedgeRegionBoundary,
    build_axis: Vector3,
    footprint_vertices: Sequence[Vector3],
    layer_height_mm: float,
) -> WedgeLayerCandidates:
    """Cover the full supplied footprint from entry minimum to exit maximum.

    Heights are distances from the entry origin along the normalized fixed
    axis. Nominal bands start at the true minimum entry height and the last
    band ends exactly at the maximum exit height. Each column separately clips
    its residual thickness to both planes. At least three noncollinear projected
    footprint vertices are required; supplying vertices asserts an enclosing
    footprint, not that this function has independently checked the CAD.
    """

    axis = _unit(build_axis, "build_axis")
    height = float(layer_height_mm)
    if not math.isfinite(height) or height <= 0:
        raise ValueError("layer height must be finite and positive")
    origin = boundary.entry_plane.origin
    footprint = tuple(
        _project(_vector(p, "footprint vertex"), origin, axis) for p in footprint_vertices
    )
    _validate_footprint(footprint)
    lower, upper = _axial_limits(boundary, axis, footprint)
    count_value = (upper - lower) / height
    if not math.isfinite(count_value) or count_value > 1_000_000:
        raise ValueError("candidate layer count exceeds supported allocation")
    count = math.ceil(count_value)
    bands = tuple(
        LayerBand(
            boundary.region_id,
            i,
            origin,
            axis,
            lower + i * height,
            min(upper, lower + (i + 1) * height),
            boundary,
        )
        for i in range(count)
    )
    if any(b.upper_mm <= b.lower_mm for b in bands):
        raise ValueError("layer band cannot be resolved at this numeric scale")
    return WedgeLayerCandidates(bands, lower, upper, footprint)


def _validate_footprint(footprint: tuple[Vector3, ...]) -> None:
    if len(set(footprint)) < 3:
        raise ValueError("full footprint requires at least three distinct projected vertices")
    first = footprint[0]
    differences = [tuple(a - b for a, b in zip(p, first, strict=True)) for p in footprint[1:]]
    noncollinear = any(
        math.hypot(
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )
        > 0
        for a in differences
        for b in differences
    )
    if not noncollinear:
        raise ValueError("footprint must span a two-dimensional region")


def _axial_limits(
    boundary: WedgeRegionBoundary, axis: Vector3, footprint: tuple[Vector3, ...]
) -> tuple[float, float]:
    entry, exit_plane = boundary.entry_plane, boundary.exit_plane
    entry_slope, exit_slope = _dot(axis, entry.normal), _dot(axis, exit_plane.normal)
    if min(entry_slope, exit_slope) <= 1e-12:
        raise ValueError("fixed axis must advance through entry and exit planes")
    intervals = []
    for point in footprint:
        low = -boundary.entry_halfspace.signed_distance(point) / entry_slope
        high = boundary.exit_halfspace.signed_distance(point) / exit_slope
        if not math.isfinite(low) or not math.isfinite(high) or high <= low:
            raise ValueError("footprint has crossed or degenerate wedge boundary columns")
        intervals.append((low, high))
    lower, upper = min(p[0] for p in intervals), max(p[1] for p in intervals)
    return lower, upper


__all__ = ["LayerBand", "WedgeLayerCandidates", "plan_layer_bands"]
