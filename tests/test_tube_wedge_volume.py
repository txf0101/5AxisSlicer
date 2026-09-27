"""Analytic solid volumes for finite-width boundary material accounting."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.tube.wedge_boundary import PlaneHalfSpace
from five_axis_slicer.algorithms.tube.wedge_volume import clipped_bead_volume


def cube(planes=()):
    # Unit cube [0,1]^3, with its centreline along X.
    return clipped_bead_volume((0, 0.5, 0.5), (1, 0.5, 0.5), (0, 1, 0), (0, 0, 1), 1, 1, planes)


def test_full_and_empty_prism():
    assert cube() == pytest.approx(1)
    assert cube((PlaneHalfSpace((2, 0, 0), (1, 0, 0)),)) == 0


def test_three_axis_slant_leaves_tetrahedron():
    # x+y+z <= 1 gives the three-unit-leg tetrahedron, volume 1/6.
    plane = PlaneHalfSpace((1, 0, 0), (-1, -1, -1))
    assert cube((plane,)) == pytest.approx(1 / 6)


def test_complementary_slant_conserves_volume():
    for offset in (0.1, 0.7, 1.3, 2.8):
        below = PlaneHalfSpace((offset, 0, 0), (-1, -1, -1))
        above = PlaneHalfSpace((offset, 0, 0), (1, 1, 1))
        assert cube((below,)) + cube((above,)) == pytest.approx(1)


def test_narrow_interior_strip_is_not_missed_by_sampling():
    lower = PlaneHalfSpace((0.314159, 0, 0), (1, 0, 0))
    upper = PlaneHalfSpace((0.314160, 0, 0), (-1, 0, 0))
    assert cube((lower, upper)) == pytest.approx(1e-6, rel=1e-8, abs=1e-14)
    assert cube((upper, lower)) == pytest.approx(1e-6, rel=1e-8, abs=1e-14)


def test_repeated_boundary_does_not_add_duplicate_cap_volume():
    plane = PlaneHalfSpace((0.5, 0, 0), (1, 0, 0))
    assert cube((plane, plane)) == pytest.approx(0.5)


def test_contact_plane_has_zero_volume():
    assert cube((PlaneHalfSpace((1, 0, 0), (1, 0, 0)),)) == pytest.approx(0)


def test_corner_prism_survives_empty_centre_column():
    # Cross-section y+z >= 0.3 in [-.3,.3] x [-.1,.1] is a .005 triangle.
    plane = PlaneHalfSpace((0, 0.3, 0), (0, 1, 1))
    volume = clipped_bead_volume((0, 0, 0), (2, 0, 0), (0, 1, 0), (0, 0, 1), 0.6, 0.2, (plane,))
    assert volume == pytest.approx(0.01)


def test_translated_rotated_tetrahedron():
    # local X -> world Z, local Y -> world X, local Z -> world Y.
    plane = PlaneHalfSpace((10, 20, 31), (-1, -1, -1))
    volume = clipped_bead_volume(
        (10.5, 20.5, 30), (10.5, 20.5, 31), (2, 0, 0), (0, 4, 0), 1, 1, (plane,)
    )
    assert volume == pytest.approx(1 / 6)


def test_reversing_segment_preserves_geometry():
    plane = PlaneHalfSpace((0.2, 0, 0), (1, 0, 0))
    result = clipped_bead_volume((1, 0.5, 0.5), (0, 0.5, 0.5), (0, 1, 0), (0, 0, 1), 1, 1, (plane,))
    assert result == pytest.approx(0.8)


def test_skew_segment_rejected():
    with pytest.raises(ValueError):
        clipped_bead_volume((0, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), 1, 1, ())
