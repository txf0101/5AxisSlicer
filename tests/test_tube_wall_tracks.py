import math
from dataclasses import replace

import pytest

from five_axis_slicer.algorithms.tube.section import TubeSectionContours
from five_axis_slicer.algorithms.tube.wall_tracks import build_wall_tracks


def ring(outer=16.0, inner=15.0, count=128):
    def loop(radius):
        points = tuple((radius * math.cos(i * 2 * math.pi / count),
                        radius * math.sin(i * 2 * math.pi / count), 0.0)
                       for i in range(count))
        return (*points, points[0])
    return TubeSectionContours(loop(outer), loop(inner), (), (), 0.0)


def test_circle_width_centers_and_closure():
    result = build_wall_tracks(ring(), 0.6)
    assert len(result.tracks) == 2
    assert not result.ready_for_export
    for index, track in enumerate(result.tracks):
        assert track[0] == track[-1]
        for point in track:
            assert point.width_mm == pytest.approx(0.5)
            assert math.hypot(*point.position) == pytest.approx(15.25 + index * 0.5)
            assert math.hypot(*point.outward_normal) == pytest.approx(1)


def test_circle_column_width_and_analytic_annular_area_conservation():
    result = build_wall_tracks(ring(), 0.6)
    for points in zip(*result.tracks):
        assert sum(p.width_mm for p in points) == pytest.approx(1)
    # For circular columns, area of each radial strip is exactly center radius
    # times width times 2pi; summing must recover the analytic annulus area.
    area = sum(2 * math.pi * math.hypot(*track[0].position) * track[0].width_mm
               for track in result.tracks)
    assert area == pytest.approx(math.pi * (16**2 - 15**2))


@pytest.mark.parametrize('width', [0, -1, math.nan, math.inf])
def test_invalid_width(width):
    with pytest.raises(ValueError):
        build_wall_tracks(ring(), width)


def test_open_and_collapsed_boundaries_rejected():
    section = ring()
    for invalid in (replace(section, outer=section.outer[:-1]),
                    replace(section, inner=section.outer),
                    replace(section, inner=((0., 0., 0.),) * 4)):
        with pytest.raises(ValueError):
            build_wall_tracks(invalid, 0.6)


def test_nonfinite_boundary_rejected():
    section = ring()
    bad = list(section.outer)
    bad[1] = (math.nan, 0., 0.)
    with pytest.raises(ValueError):
        build_wall_tracks(replace(section, outer=tuple(bad)), 0.6)
