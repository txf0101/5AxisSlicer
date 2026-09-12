from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.planar import (
    PlanarRegion,
    PlanarSliceLayer,
    SpiralParameters,
    generate_spiral_toolpath,
)
from five_axis_slicer.algorithms.planar.spiral import PlanarSpiralError


def _loop(z):
    return ((0, 0, z), (10, 0, z), (10, 10, z), (0, 10, z), (0, 0, z))


def test_spiral_has_continuous_z_and_material_after_approach():
    layers = (
        PlanarSliceLayer("l1", 0, (PlanarRegion("r1", _loop(0)),)),
        PlanarSliceLayer("l2", 1, (PlanarRegion("r1", _loop(1)),)),
    )
    path = generate_spiral_toolpath("op", layers, SpiralParameters(0.5, 0.2, 8))
    assert any(0 < point.position[2] < 1 for point in path.points)
    assert all(point.material_volume_mm3 > 0 for point in path.points[1:])


def test_multiple_islands_are_explicitly_rejected():
    region = PlanarRegion("r1", _loop(0))
    other = PlanarRegion("r2", ((20, 0, 0), (21, 0, 0), (21, 1, 0), (20, 1, 0), (20, 0, 0)))
    layers = (PlanarSliceLayer("l1", 0, (region, other)), PlanarSliceLayer("l2", 1, (region,)))
    with pytest.raises(PlanarSpiralError, match="planar.spiral_multiple_regions"):
        generate_spiral_toolpath("op", layers, SpiralParameters(0.5, 0.2, 8))


def test_spiral_checks_correspondence_closure_and_volume():
    layers = (
        PlanarSliceLayer("l1", 0, (PlanarRegion("r1", _loop(0)),)),
        PlanarSliceLayer("l2", 1, (PlanarRegion("r1", _loop(1)),)),
    )
    parameters = SpiralParameters(0.5, 0.2, 8)
    path = generate_spiral_toolpath("op", layers, parameters)
    assert path.points[-1].position == pytest.approx(path.points[8].position)
    assert path.points[-1].position[2] == pytest.approx(1.0)
    assert path.events[-1].event_type == "finish"
    assert path.events[-1].context["closed"] is True
    expected = sum(
        (
            (left.position[0] - right.position[0]) ** 2
            + (left.position[1] - right.position[1]) ** 2
            + (left.position[2] - right.position[2]) ** 2
        )
        ** 0.5
        * parameters.bead_width_mm
        * parameters.layer_height_mm
        for left, right in zip(path.points, path.points[1:], strict=False)
    )
    assert sum(point.material_volume_mm3 for point in path.points) == pytest.approx(expected)


def test_spiral_rejects_holes_topology_changes_and_bad_layer_order():
    hole = _loop(0)
    region_with_hole = PlanarRegion("r1", _loop(0), (hole,))
    with pytest.raises(PlanarSpiralError, match="planar.spiral_holes_unsupported"):
        generate_spiral_toolpath(
            "op",
            (
                PlanarSliceLayer("l1", 0, (region_with_hole,)),
                PlanarSliceLayer("l2", 1, (region_with_hole,)),
            ),
            SpiralParameters(0.5, 0.2, 8),
        )
    changed = (
        PlanarSliceLayer("l1", 0, (PlanarRegion("r1", _loop(0)),)),
        PlanarSliceLayer("l2", 1, (PlanarRegion("r2", _loop(1)),)),
    )
    with pytest.raises(PlanarSpiralError, match="planar.spiral_topology_changed"):
        generate_spiral_toolpath("op", changed, SpiralParameters(0.5, 0.2, 8))
    bad_order = (
        PlanarSliceLayer("l1", 1, (PlanarRegion("r1", _loop(1)),)),
        PlanarSliceLayer("l2", 1, (PlanarRegion("r1", _loop(1)),)),
    )
    with pytest.raises(PlanarSpiralError, match="planar.spiral_layer_order_invalid"):
        generate_spiral_toolpath("op", bad_order, SpiralParameters(0.5, 0.2, 8))


def test_spiral_rejects_degenerate_contour():
    degenerate = ((0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 0, 0))
    layers = (
        PlanarSliceLayer("l1", 0, (PlanarRegion("r1", degenerate),)),
        PlanarSliceLayer("l2", 1, (PlanarRegion("r1", degenerate),)),
    )
    with pytest.raises(PlanarSpiralError, match="planar.spiral_degenerate_contour"):
        generate_spiral_toolpath("op", layers, SpiralParameters(0.5, 0.2, 8))
