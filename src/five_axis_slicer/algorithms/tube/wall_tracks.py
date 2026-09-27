"""Equal-column wall-track candidates; no bead or manufacturing qualification.

Widths describe distances in the supplied section plane. On an oblique section
these differ from radial wall thickness. Nearest inner-polyline projection is a
restricted correspondence, not an implementation of Arachne or a coverage proof.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from ...models import Vector3
from .section import TubeSectionContours, _nearest_segment_point


@dataclass(frozen=True, slots=True)
class WallTrackPoint:
    position: Vector3
    width_mm: float
    outward_normal: Vector3


@dataclass(frozen=True, slots=True)
class WallTrackCandidates:
    tracks: tuple[tuple[WallTrackPoint, ...], ...]
    maximum_column_width_mm: float
    ready_for_export: bool = False
    limitations: tuple[str, ...] = (
        "nearest_polyline_columns_do_not_prove_full_area_coverage",
        "section_width_is_not_radial_thickness_on_oblique_sections",
        "minimum_printable_width_and_overlap_not_calibrated",
    )


def _validate_loop(loop: tuple[Vector3, ...]) -> None:
    if len(loop) < 4 or loop[0] != loop[-1] or len(set(loop[:-1])) < 3:
        raise ValueError("wall boundaries require closed nondegenerate loops")
    if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in loop):
        raise ValueError("wall boundary positions must be finite 3D points")
    if any(a == b for a, b in zip(loop, loop[1:])):
        raise ValueError("wall boundaries contain a zero-length segment")


def build_wall_tracks(
    section: TubeSectionContours, maximum_track_width_mm: float,
) -> WallTrackCandidates:
    """Partition each outer-to-inner column into the same number of tracks.

    Input loops must already represent the real annular section. Tracks are
    ordered inner to outer, retain the outer loop's sampling order, and close
    by repeating the exact first point. No process parameter is changed.
    """
    if not math.isfinite(maximum_track_width_mm) or maximum_track_width_mm <= 0:
        raise ValueError("maximum track width must be finite and positive")
    _validate_loop(section.outer)
    _validate_loop(section.inner)
    columns = []
    for outer in section.outer[:-1]:
        inner = min(
            (_nearest_segment_point(outer, a, b)
             for a, b in zip(section.inner, section.inner[1:])),
            key=lambda p: math.dist(outer, p),
        )
        width = math.dist(outer, inner)
        if not math.isfinite(width) or width <= 1e-12:
            raise ValueError("wall columns require positive resolvable thickness")
        normal: Vector3 = tuple((a - b) / width for a, b in zip(outer, inner))  # type: ignore[assignment]
        columns.append((inner, width, normal))
    maximum = max(width for _, width, _ in columns)
    count = math.ceil(maximum / maximum_track_width_mm)
    if count > 10000:
        raise ValueError("wall track count exceeds supported allocation")
    tracks = []
    for index in range(count):
        points = []
        for inner, width, normal in columns:
            position: Vector3 = tuple(
                p + n * width * (index + 0.5) / count for p, n in zip(inner, normal)
            )  # type: ignore[assignment]
            points.append(WallTrackPoint(position, width / count, normal))
        tracks.append(tuple([*points, points[0]]))
    return WallTrackCandidates(tuple(tracks), maximum)
