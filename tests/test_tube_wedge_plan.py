from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.tube.geometry import manual_tube_feature
from five_axis_slicer.algorithms.tube.indexed import TubeRegion
from five_axis_slicer.algorithms.tube.wedge_plan import build_wedge_boundaries


def fixture():
    feature = manual_tube_feature(((0, 0, 0), (0, 0, 10)), outer_radius_mm=2, inner_radius_mm=1)
    regions = (
        TubeRegion("r1", 0, 5, (0, 0, 1), 0, 0, "face"),
        TubeRegion("r2", 5, 10, (0, 0, 1), 0, 0, "face"),
    )
    return feature, regions


def test_adjacent_regions_share_one_plane_and_opposite_ownership():
    feature, regions = fixture()
    left, right = build_wedge_boundaries(feature, regions)
    assert left.exit_plane is right.entry_plane
    assert left.exit_plane.origin == pytest.approx((0, 0, 5))
    for z in (4, 6):
        assert left.exit_halfspace.signed_distance((0, 0, z)) == pytest.approx(
            -right.entry_halfspace.signed_distance((0, 0, z))
        )


def test_gap_in_regions_rejected():
    feature, regions = fixture()
    with pytest.raises(ValueError):
        build_wedge_boundaries(feature, (regions[0], replace(regions[1], start_distance_mm=6)))


def test_backward_build_axis_rejected():
    feature, regions = fixture()
    with pytest.raises(ValueError):
        build_wedge_boundaries(
            feature, (regions[0], replace(regions[1], fixed_build_direction=(0, 0, -1)))
        )
