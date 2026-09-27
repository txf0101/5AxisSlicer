from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.tube.wedge_layers import plan_layer_bands
from five_axis_slicer.algorithms.tube.wedge_plan import WedgeBoundaryPlane, WedgeRegionBoundary


FOOTPRINT = ((-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0))


def boundary(exit_normal=(0, 0, 1)):
    return WedgeRegionBoundary(
        "r1",
        WedgeBoundaryPlane((0, 0, 0), (0, 0, 1)),
        WedgeBoundaryPlane((0, 0, 1), exit_normal),
    )


def test_flat_region_has_short_tail_and_no_export_qualification():
    result = plan_layer_bands(boundary(), (0, 0, 2), FOOTPRINT, 0.3)
    assert [b.lower_mm for b in result.bands] == pytest.approx([0, 0.3, 0.6, 0.9])
    assert [b.upper_mm for b in result.bands] == pytest.approx([0.3, 0.6, 0.9, 1])
    assert result.bands[-1].column((0, 0, 99)) == pytest.approx((0.9, 1))
    assert not result.ready_for_export


def test_sloped_exit_covers_material_above_centerline_endpoint():
    result = plan_layer_bands(boundary((-0.2, 0, 1)), (0, 0, 1), FOOTPRINT, 0.25)
    assert result.axial_max_mm == pytest.approx(1.2)
    tail = result.bands[-1]
    assert tail.column((1, 0, 0)) == pytest.approx((1, 1.2))
    assert tail.column((-1, 0, 0)) is None
    # Integrate each column's intervals: analytic thickness is 1 + 0.2*x.
    for x in (-1, -0.5, 0, 0.5, 1):
        intervals = [b.column((x, 0, 0)) for b in result.bands]
        assert sum(v[1] - v[0] for v in intervals if v) == pytest.approx(1 + 0.2 * x)


@pytest.mark.parametrize("footprint", [((0, 0, 0),), ((-1, 0, 0), (0, 0, 0), (1, 0, 0))])
def test_centerline_or_collinear_footprints_rejected(footprint):
    with pytest.raises(ValueError, match="footprint"):
        plan_layer_bands(boundary(), (0, 0, 1), footprint, 0.2)


def test_crossed_boundary_columns_rejected():
    with pytest.raises(ValueError, match="crossed"):
        plan_layer_bands(boundary((-2, 0, 1)), (0, 0, 1), FOOTPRINT, 0.2)
