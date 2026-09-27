"""Closed-form finite-width sections, independent of the clipping algorithm."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.tube.wedge_boundary import PlaneHalfSpace
from five_axis_slicer.algorithms.tube.wedge_material import clipped_bead_area


def area(planes=(), center=(0, 0, 0), width_axis=(1, 0, 0), build_axis=(0, 0, 1)):
    return clipped_bead_area(center, width_axis, build_axis, 0.6, 0.2, planes)


def test_uncut_and_half_rectangle():
    assert area() == pytest.approx(0.12)
    assert area((PlaneHalfSpace((0, 0, 0), (1, 0, 0)),)) == pytest.approx(0.06)


def test_corner_triangle_exists_when_center_column_is_empty():
    # x + z >= 0.3 intersects the rectangle only at its upper-right corner.
    # Two 0.1 mm perpendicular legs give area 0.005, although x=0 has no material.
    plane = PlaneHalfSpace((0.3, 0, 0), (1, 0, 1))
    assert area((plane,)) == pytest.approx(0.005)


def test_complementary_planes_preserve_finite_width_material():
    for offset in (-0.41, -0.3, -0.07, 0.11, 0.3, 0.41):
        positive = PlaneHalfSpace((offset, 0, 0), (1, 0, 1))
        negative = PlaneHalfSpace((offset, 0, 0), (-1, 0, -1))
        assert area((positive,)) + area((negative,)) == pytest.approx(0.12)


def test_two_cuts_leave_known_rectangle_and_do_not_depend_on_order():
    right = PlaneHalfSpace((0.1, 0, 0), (1, 0, 0))
    top = PlaneHalfSpace((0, 0, 0.02), (0, 0, 1))
    assert area((right, top)) == pytest.approx(0.2 * 0.08)
    assert area((top, right)) == pytest.approx(0.2 * 0.08)


def test_rigidly_rotated_and_translated_triangle():
    # Map local x to world y and local z to world x, then translate.
    plane = PlaneHalfSpace((2, 3.3, 4), (1, 1, 0))
    assert area((plane,), (2, 3, 4), (0, 2, 0), (3, 0, 0)) == pytest.approx(0.005)


def test_parallel_plane_retains_or_excludes_whole_section():
    assert area((PlaneHalfSpace((0, -1, 0), (0, 1, 0)),)) == pytest.approx(0.12)
    assert area((PlaneHalfSpace((0, 1, 0), (0, 1, 0)),)) == 0


@pytest.mark.parametrize("width,height", [(0, 0.2), (0.6, 0), (0, 0)])
def test_zero_measure_is_empty(width, height):
    assert clipped_bead_area((0, 0, 0), (1, 0, 0), (0, 0, 1), width, height, ()) == 0


@pytest.mark.parametrize("width,height", [(-0.6, 0.2), (0.6, -0.2), (float("nan"), 1)])
def test_invalid_sizes_rejected(width, height):
    with pytest.raises(ValueError):
        clipped_bead_area((0, 0, 0), (1, 0, 0), (0, 0, 1), width, height, ())


def test_skew_axes_rejected_instead_of_silently_changing_cross_section():
    with pytest.raises(ValueError):
        area(width_axis=(1, 0, 1))
