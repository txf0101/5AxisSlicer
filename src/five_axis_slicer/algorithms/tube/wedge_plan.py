"""Shared geometric boundaries for Indexed regions; no deposition qualification."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

from ...models import Vector3
from .geometry import TubeFeature
from .indexed import TubeRegion
from .wedge_boundary import PlaneHalfSpace


@dataclass(frozen=True, slots=True)
class WedgeBoundaryPlane:
    """A forward-oriented shared plane, independent of material-side ownership."""

    origin: Vector3
    normal: Vector3

    def __post_init__(self) -> None:
        plane = PlaneHalfSpace(self.origin, self.normal)
        object.__setattr__(self, "origin", plane.origin)
        object.__setattr__(self, "normal", plane.normal)


@dataclass(frozen=True, slots=True)
class WedgeRegionBoundary:
    region_id: str
    entry_plane: WedgeBoundaryPlane
    exit_plane: WedgeBoundaryPlane

    @property
    def entry_halfspace(self) -> PlaneHalfSpace:
        return PlaneHalfSpace(self.entry_plane.origin, self.entry_plane.normal)

    @property
    def exit_halfspace(self) -> PlaneHalfSpace:
        normal: Vector3 = tuple(-v for v in self.exit_plane.normal)  # type: ignore[assignment]
        return PlaneHalfSpace(self.exit_plane.origin, normal)


def _dot(a: Vector3, b: Vector3) -> float:
    result = math.fsum(x * y for x, y in zip(a, b, strict=True))
    if not math.isfinite(result):
        raise ValueError("region boundary projection overflow")
    return result


def _validate_regions(feature: TubeFeature, regions: tuple[TubeRegion, ...]) -> None:
    length = feature.centerline_length_mm
    if not math.isfinite(length) or length <= 0 or not regions:
        raise ValueError("positive centerline length and nonempty regions required")
    _validate_identifiers(regions)
    previous = 0.0
    for region in regions:
        start, end = region.start_distance_mm, region.end_distance_mm
        if not all(math.isfinite(v) for v in (start, end)) or start < 0 or end <= start:
            raise ValueError("regions require finite forward distance intervals")
        if not math.isclose(start, previous, rel_tol=0, abs_tol=1e-8):
            raise ValueError("regions must cover the centerline in continuous order")
        if end > length + 1e-8:
            raise ValueError("region exceeds centerline length")
        previous = end
    if not math.isclose(previous, length, rel_tol=0, abs_tol=1e-8):
        raise ValueError("regions must reach the centerline exit")


def _validate_identifiers(regions: tuple[TubeRegion, ...]) -> None:
    identifiers = [region.region_id for region in regions]
    if any(not value for value in identifiers) or len(set(identifiers)) != len(identifiers):
        raise ValueError("region identifiers must be nonempty and unique")


def build_wedge_boundaries(
    feature: TubeFeature,
    regions: Sequence[TubeRegion],
) -> tuple[WedgeRegionBoundary, ...]:
    """Construct common planes and complementary material half-spaces.

    Interior normals use the following region's fixed direction. The real
    endpoint tangents define first/last planes. Neighbor records share the
    actual plane object; no independent refitting or boundary displacement is
    performed. Checks establish local forward geometry, not global absence of
    intersections in a returning or self-overlapping tube.
    """

    ordered = tuple(regions)
    _validate_regions(feature, ordered)
    first_origin, first_tangent = feature.point_tangent_at(0.0)
    planes = [WedgeBoundaryPlane(first_origin, first_tangent)]
    for left, right in zip(ordered, ordered[1:]):
        origin, _tangent = feature.point_tangent_at(left.end_distance_mm)
        planes.append(WedgeBoundaryPlane(origin, right.fixed_build_direction))
    last_origin, last_tangent = feature.point_tangent_at(feature.centerline_length_mm)
    planes.append(WedgeBoundaryPlane(last_origin, last_tangent))
    result = []
    for region, entry, exit_plane in zip(ordered, planes, planes[1:]):
        direction = PlaneHalfSpace(entry.origin, region.fixed_build_direction).normal
        displacement: Vector3 = tuple(  # type: ignore[assignment]
            b - a for a, b in zip(entry.origin, exit_plane.origin, strict=True)
        )
        if min(_dot(direction, entry.normal), _dot(direction, exit_plane.normal)) <= 1e-12:
            raise ValueError("region axis must advance through both boundary planes")
        if _dot(displacement, direction) <= 0:
            raise ValueError("region boundary origins must advance along the fixed axis")
        if min(_dot(displacement, entry.normal), _dot(displacement, exit_plane.normal)) <= 0:
            raise ValueError("boundary centerline endpoints lie outside the forward wedge")
        result.append(WedgeRegionBoundary(region.region_id, entry, exit_plane))
    return tuple(result)


__all__ = ["WedgeBoundaryPlane", "WedgeRegionBoundary", "build_wedge_boundaries"]
