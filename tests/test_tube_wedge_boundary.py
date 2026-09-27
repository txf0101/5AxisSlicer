"""Analytic boundary fixtures; these do not certify deposited-bead support."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.tube.wedge_boundary import (
    PlaneHalfSpace,
    clip_polyline,
    column_interval,
)


def test_complementary_sloped_boundary_partitions_each_column():
    # z = 1 + y/2 divides a two-millimetre column. Its total volume over
    # y in [-1, 1], x in [0, 1] is 4 mm^3, split equally by symmetry.
    below = PlaneHalfSpace((0, 0, 1), (0, 0.5, -1))
    above = PlaneHalfSpace((0, 0, 1), (0, -0.5, 1))
    old_volume = new_volume = 0.0
    for y in (-0.75, -0.25, 0.25, 0.75):
        expected = 1 + y / 2
        old = column_interval((0, y, 0), (0, 0, 1), 0, 2, (below,))
        new = column_interval((0, y, 0), (0, 0, 1), 0, 2, (above,))
        assert old == pytest.approx((0, expected))
        assert new == pytest.approx((expected, 2))
        old_volume += (old[1] - old[0]) * 0.5
        new_volume += (new[1] - new[0]) * 0.5
    assert (old_volume, new_volume) == pytest.approx((2, 2))


def test_layer_band_retains_residual_thickness():
    ceiling = PlaneHalfSpace((0, 0, 1.07), (0, 0, -1))
    actual = column_interval((0, 0, 0), (0, 0, 7), 1, 1.2, (ceiling,))
    assert actual == pytest.approx((1, 1.07))
    assert column_interval((0, 0, 0), (0, 0, 1), 1.2, 1.4, (ceiling,)) is None


def test_parallel_column_inside_and_outside():
    positive_x = PlaneHalfSpace((0, 0, 0), (3, 0, 0))
    assert column_interval((1, 0, 0), (0, 0, 1), 0, 2, (positive_x,)) == (0, 2)
    assert column_interval((-1, 0, 0), (0, 0, 1), 0, 2, (positive_x,)) is None


def test_open_segments_do_not_bridge_disconnected_visits():
    points = ((-1, 0, 0), (1, 0, 0), (-1, 2, 0), (1, 2, 0))
    positive_x = PlaneHalfSpace((0, 0, 0), (1, 0, 0))
    pieces = clip_polyline(points, (positive_x,))
    assert pieces == (
        ((0, 0, 0), (1, 0, 0), (0, 1, 0)),
        ((0, 2, 0), (1, 2, 0)),
    )


def test_closed_input_clipped_to_open_arc_without_added_chord():
    diamond = ((1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0), (1, 0, 0))
    # The stored seam is outside the retained half; one connected open arc remains.
    negative_x = PlaneHalfSpace((0, 0, 0), (-1, 0, 0))
    assert clip_polyline(diamond, (negative_x,)) == (((0, 1, 0), (-1, 0, 0), (0, -1, 0)),)


def test_touching_vertex_is_not_a_deposition_path():
    positive_x = PlaneHalfSpace((0, 0, 0), (1, 0, 0))
    assert clip_polyline(((-1, 0, 0), (0, 1, 0), (-1, 2, 0)), (positive_x,)) == ()


@pytest.mark.parametrize("normal", [(0, 0, 0), (float("nan"), 0, 1)])
def test_invalid_plane_rejected(normal):
    with pytest.raises(ValueError):
        PlaneHalfSpace((0, 0, 0), normal)


def test_zero_axis_and_reversed_band_rejected():
    with pytest.raises(ValueError):
        column_interval((0, 0, 0), (0, 0, 0), 0, 1, ())
    with pytest.raises(ValueError):
        column_interval((0, 0, 0), (0, 0, 1), 2, 1, ())
