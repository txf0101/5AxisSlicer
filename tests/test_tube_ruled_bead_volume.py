import math

import pytest

from five_axis_slicer.algorithms.tube.ruled_bead_volume import ruled_bead_volume


def test_linear_width_times_height_has_exact_cross_term():
    # Integral_0^1 (1+t)(2+t) dt = 23/6; projected length is 3.
    volume = ruled_bead_volume((0, 0, 0), (3, 0, 4), (0, 1, 0), (0, 2, 0), 2, 3, (0, 0, 1))
    assert volume == pytest.approx(11.5)


def test_rigid_rotation_preserves_volume():
    v = math.sqrt(0.5)
    volume = ruled_bead_volume((0, 0, 0), (3, -4*v, 4*v), (0, v, v),
                              (0, 2*v, 2*v), 2, 3, (0, -v, v))
    assert volume == pytest.approx(11.5)


def test_circular_annular_sector_chord_cell_matches_polygon_area():
    angle = 0.1
    a = (2, 0, 0)
    b = (2*math.cos(angle), 2*math.sin(angle), 0)
    volume = ruled_bead_volume(a, b, (1, 0, 0), (math.cos(angle), math.sin(angle), 0), .2, .2, (0, 0, 1))
    expected = .5 * (2.5**2 - 1.5**2) * math.sin(angle) * .2
    assert volume == pytest.approx(expected)


def test_crossing_lateral_edges_are_rejected():
    with pytest.raises(ValueError, match="folded"):
        ruled_bead_volume((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, -1, 0), .2, .2, (0, 0, 1))
