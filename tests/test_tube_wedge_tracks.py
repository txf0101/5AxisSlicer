from dataclasses import replace
import math

import pytest

from five_axis_slicer.algorithms.tube.wall_tracks import WallTrackPoint
from five_axis_slicer.algorithms.tube.wedge_layers import LayerBand
from five_axis_slicer.algorithms.tube.wedge_plan import WedgeBoundaryPlane, WedgeRegionBoundary
from five_axis_slicer.algorithms.tube.wedge_tracks import _attributes, build_wedge_tracks


def band(index=0):
    return LayerBand('r', index, (0, 0, 0), (0, 0, 1), index, index + 1,
                     WedgeRegionBoundary('r', WedgeBoundaryPlane((0, 0, 0), (0, 0, 1)),
                                         WedgeBoundaryPlane((0, 0, 1), (-1, 0, 1))))


def track():
    return (WallTrackPoint((0, 0, .5), .4, (0, 1, 0)),
            WallTrackPoint((1, 0, .5), .6, (0, 1, 0)))


def test_jump_preserves_open_paths_and_interpolates_width():
    result = build_wedge_tracks(band(), track(), 1)
    assert len(result.paths) == 2
    assert result.paths[0][-1].width_mm == pytest.approx(.5)
    assert result.paths[1][0].width_mm == pytest.approx(.5)
    assert result.paths[0][-1].height_mm == pytest.approx(1.5)
    assert result.paths[1][0].height_mm == pytest.approx(1)
    assert not result.ready_for_export


def test_excluded_span_preserved():
    result = build_wedge_tracks(band(1), track(), 1)
    assert len(result.residual_tasks) == 1
    assert result.paths[0][0].width_mm == pytest.approx(.5)


def test_closed_path_and_normals():
    flat = replace(band(), boundary=WedgeRegionBoundary('r',
        WedgeBoundaryPlane((0, 0, 0), (0, 0, 1)), WedgeBoundaryPlane((0, 0, 1.2), (0, 0, 1))))
    points = tuple(WallTrackPoint(p, .5, (0, 1, 0)) for p in
                   ((0, 0, .5), (1, 0, .5), (1, 1, .5), (0, 0, .5)))
    result = build_wedge_tracks(flat, points, 1)
    assert result.paths[0][0] == result.paths[0][-1]
    assert all(math.hypot(*p.outward_normal) == pytest.approx(1) for p in result.paths[0])


def test_rotated_axis_is_equivariant():
    def rotate(v):
        return (v[2], v[1], -v[0])
    original = band()
    boundary = original.boundary
    tilted = replace(original, build_axis=rotate(original.build_axis), boundary=WedgeRegionBoundary('r',
        WedgeBoundaryPlane(rotate(boundary.entry_plane.origin), rotate(boundary.entry_plane.normal)),
        WedgeBoundaryPlane(rotate(boundary.exit_plane.origin), rotate(boundary.exit_plane.normal))))
    result = build_wedge_tracks(tilted, tuple(replace(p, position=rotate(p.position),
        outward_normal=rotate(p.outward_normal)) for p in track()), 1)
    expected = build_wedge_tracks(original, track(), 1)
    for a, b in zip(result.paths, expected.paths):
        for p, q in zip(a, b):
            assert p.position == pytest.approx(rotate(q.position))
            assert p.width_mm == pytest.approx(q.width_mm)


def test_far_projection_is_rejected():
    with pytest.raises(ValueError, match='no matching'):
        _attributes((.5, .01, 0), ((0, 0, 0), (1, 0, 0)), track())
