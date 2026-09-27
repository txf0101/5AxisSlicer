import pytest

from five_axis_slicer.algorithms.tube.wedge_layers import LayerBand
from five_axis_slicer.algorithms.tube.wedge_plan import WedgeBoundaryPlane, WedgeRegionBoundary
from five_axis_slicer.algorithms.tube.wedge_path_candidates import build_path_candidates


def band():
    boundary = WedgeRegionBoundary("r", WedgeBoundaryPlane((0, 0, 0), (0, 0, 1)),
                                   WedgeBoundaryPlane((0, 0, 1), (-1, 0, 1)))
    return LayerBand("r", 1, (0, 0, 0), (0, 0, 1), 1, 2, boundary)


def test_below_midplane_residual_is_retained():
    result = build_path_candidates(band(), ((0.1, 0, 1.5), (0.2, 0, 1.5)))
    assert len(result.paths) == 1
    assert result.paths[0][0].height_mm == pytest.approx(0.1)
    assert result.paths[0][0].position == pytest.approx((0.1, 0, 1.05))
    assert not result.ready_for_export


def test_zero_thickness_cut_endpoint_and_saturation_break():
    result = build_path_candidates(band(), ((-1, 0, 1.5), (2, 0, 1.5)))
    path = result.paths[0]
    assert [p.position[0] for p in path] == pytest.approx([0, 1, 2])
    assert [p.height_mm for p in path] == pytest.approx([0, 1, 1])
    assert result.residual_tasks


def test_explicit_ring_seam_stays_continuous():
    points = ((1, 0, 1.5), (0, 1, 1.5), (-1, 0, 1.5), (0, -1, 1.5), (1, 0, 1.5))
    result = build_path_candidates(band(), points)
    assert len(result.paths) == 1
    assert result.paths[0][0].position[:2] == pytest.approx((0, -1))
    assert result.paths[0][-1].position[:2] == pytest.approx((0, 1))


def test_empty_center_columns_are_explicit_residual_work():
    result = build_path_candidates(band(), ((-2, 0, 1.5), (-1, 0, 1.5)))
    assert result.paths == ()
    assert len(result.residual_tasks) == 1


def test_all_valid_closed_ring_remains_closed():
    points = ((1, 0, 1.5), (2, 0, 1.5), (2, 1, 1.5), (1, 0, 1.5))
    path = build_path_candidates(band(), points).paths[0]
    assert path[0] == path[-1]


def test_empty_midwall_requires_full_band_residual_check():
    result = build_path_candidates(band(), ())
    assert result.paths == ()
    assert result.residual_tasks[0].reason == "missing_section_midwall_check_full_band_cad_residual"
