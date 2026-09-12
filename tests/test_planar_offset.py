from pathlib import Path
import math
import sys

import cadquery as cq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.planar import (
    PlanarOffsetError,
    PlanarRegion,
    inward_offsets,
    inward_offsets_for_regions,
)


def _loop(*points):
    return tuple((*points, points[0]))


def _area(loop):
    wire = cq.Wire.makePolygon(loop[:-1], close=True)
    return cq.Face.makeFromWires(wire).Area()


def test_square_multi_pass_has_independent_area_truth_and_residual():
    region = PlanarRegion("square", _loop((0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)))
    result = inward_offsets(region, 1, 3)

    assert not result.diagnostics
    assert result.contour_pass_indices == (1, 2, 3)
    assert [_area(loop) for loop in result.contours] == pytest.approx([64, 36, 16])
    assert result.residual_area_mm2 == pytest.approx(9.0)
    assert all(loop[0] == loop[-1] for loop in result.contours)


def test_hole_and_concave_domain_keep_valid_offset_boundaries():
    holed = PlanarRegion(
        "holed",
        _loop((0, 0, 0), (20, 0, 0), (20, 20, 0), (0, 20, 0)),
        (_loop((7, 7, 0), (7, 13, 0), (13, 13, 0), (13, 7, 0)),),
    )
    concave = PlanarRegion(
        "concave",
        _loop(
            (0, 0, 0),
            (8, 0, 0),
            (8, 8, 0),
            (5, 8, 0),
            (5, 3, 0),
            (3, 3, 0),
            (3, 8, 0),
            (0, 8, 0),
        ),
    )

    holed_result = inward_offsets(holed, 1, 1)
    concave_result = inward_offsets(concave, 0.5, 1)
    assert not holed_result.diagnostics
    assert len(holed_result.contours) == 2
    assert _area(holed_result.contours[0]) == pytest.approx(324.0)
    assert _area(holed_result.contours[1]) > 36.0
    assert not concave_result.diagnostics
    assert len(concave_result.contours) == 1


def test_narrow_neck_splits_stably_and_regions_are_aggregated_by_id():
    dumbbell = PlanarRegion(
        "b",
        _loop(
            (0, 0, 0),
            (4, 0, 0),
            (4, 1.5, 0),
            (8, 1.5, 0),
            (8, 0, 0),
            (12, 0, 0),
            (12, 4, 0),
            (8, 4, 0),
            (8, 2.5, 0),
            (4, 2.5, 0),
            (4, 4, 0),
            (0, 4, 0),
        ),
    )
    square = PlanarRegion("a", _loop((20, 0, 0), (24, 0, 0), (24, 4, 0), (20, 4, 0)))

    split = inward_offsets(dumbbell, 0.6, 1)
    assert not split.diagnostics
    assert len(split.contours) == 2
    assert split.contour_pass_indices == (1, 1)
    results = inward_offsets_for_regions((dumbbell, square), 0.6, 1)
    assert [item[0] for item in results] == ["a", "b"]
    assert inward_offsets(dumbbell, 0.6, 1).contours == split.contours


def test_disappearing_narrow_region_returns_partial_passes_and_diagnostic():
    narrow = PlanarRegion("narrow", _loop((0, 0, 0), (3, 0, 0), (3, 10, 0), (0, 10, 0)))
    result = inward_offsets(narrow, 1, 2)

    assert result.contour_pass_indices == (1,)
    assert result.diagnostics[0].code == "planar.offset_region_disappeared"
    assert result.diagnostics[0].pass_index == 2


def test_self_intersection_and_bad_hole_topology_are_localised_before_occt():
    bow_tie = PlanarRegion("cross", _loop((0, 0, 0), (4, 4, 0), (0, 4, 0), (4, 0, 0)))
    outside_hole = PlanarRegion(
        "bad-hole",
        _loop((0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)),
        (_loop((12, 1, 0), (13, 1, 0), (13, 2, 0), (12, 2, 0)),),
    )

    assert inward_offsets(bow_tie, 1, 1).diagnostics[0].code == "planar.offset_self_intersection"
    assert (
        inward_offsets(outside_hole, 1, 1).diagnostics[0].code
        == "planar.offset_hole_topology_invalid"
    )


def test_residual_small_island_is_measured_and_invalid_parameters_fail():
    region = PlanarRegion("residual", _loop((0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)))
    result = inward_offsets(region, 1, 1)

    assert result.residual_area_mm2 == pytest.approx(1.0)
    assert len(result.residual_contours) == 1
    assert math.isclose(_area(result.residual_contours[0]), result.residual_area_mm2)
    with pytest.raises(PlanarOffsetError, match="planar.offset_parameter_invalid"):
        inward_offsets(region, float("nan"), 1)
    with pytest.raises(PlanarOffsetError, match="planar.offset_parameter_invalid"):
        inward_offsets(region, 1, True)


def test_consecutive_duplicate_vertex_is_cleaned_before_offset():
    region = PlanarRegion(
        "duplicate",
        ((0, 0, 0), (10, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0), (0, 0, 0)),
    )

    result = inward_offsets(region, 1, 1)
    assert not result.diagnostics
    assert _area(result.contours[0]) == pytest.approx(64.0)
