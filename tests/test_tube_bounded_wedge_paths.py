from dataclasses import replace

import pytest

from five_axis_slicer.algorithms.tube.bounded_wedge_paths import build_bounded_candidates
from five_axis_slicer.algorithms.tube.wedge_layers import LayerBand
from five_axis_slicer.algorithms.tube.wedge_plan import WedgeBoundaryPlane, WedgeRegionBoundary


def band(index=0):
    boundary = WedgeRegionBoundary("r", WedgeBoundaryPlane((0, 0, 0), (0, 0, 1)),
                                   WedgeBoundaryPlane((0, 0, 1), (-1, 0, 1)))
    return LayerBand("r", index, (0, 0, 0), (0, 0, 1), index, index + 1, boundary)


def test_jump_has_two_one_sided_endpoints_without_connecting_extrusion():
    result = build_bounded_candidates(band(), ((0, 0, 0.5), (1, 0, 0.5)), 1)
    assert len(result.paths) == 2
    assert result.paths[0][-1].position == pytest.approx((0.5, 0, 0.75))
    assert result.paths[1][0].position == pytest.approx((0.5, 0, 0.5))
    assert result.paths[0][-1].height_mm == pytest.approx(1.5)
    assert result.paths[1][0].height_mm == pytest.approx(1)
    assert not result.ready_for_export


def test_new_layer_starts_with_half_height_and_explicit_excluded_span():
    result = build_bounded_candidates(band(1), ((0, 0, 1.5), (1, 0, 1.5)), 1)
    assert len(result.paths) == 1
    assert result.paths[0][0].height_mm == pytest.approx(0.5)
    assert result.paths[0][0].position == pytest.approx((0.5, 0, 1.25))
    assert len(result.residual_tasks) == 1


def test_column_material_intervals_tile_without_gap():
    for x in (0.1, 0.49, 0.5, 0.51, 1.49, 1.5, 2.2):
        intervals = []
        for index in range(4):
            result = build_bounded_candidates(band(index), ((x, 0, 0), (x, 1, 0)), 1)
            if result.paths:
                p = result.paths[0][0]
                intervals.append((p.position[2] - p.height_mm / 2,
                                  p.position[2] + p.height_mm / 2))
                assert 0.5 <= p.height_mm <= 1.5
        assert intervals[0][0] == pytest.approx(0)
        assert intervals[-1][1] == pytest.approx(1 + x)
        assert all(a[1] == pytest.approx(b[0]) for a, b in zip(intervals, intervals[1:]))


def test_closed_flat_contour_remains_closed():
    flat = replace(band(), boundary=WedgeRegionBoundary(
        "r", WedgeBoundaryPlane((0, 0, 0), (0, 0, 1)),
        WedgeBoundaryPlane((0, 0, 1.2), (0, 0, 1))))
    ring = ((0, 0, 0.5), (1, 0, 0.5), (1, 1, 0.5), (0, 0, 0.5))
    result = build_bounded_candidates(flat, ring, 1)
    assert len(result.paths) == 1
    assert result.paths[0][0] == result.paths[0][-1]
    assert not result.residual_tasks
