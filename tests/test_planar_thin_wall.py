from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.planar import (
    ThinWallParameters,
    generate_open_wall_toolpath,
    thin_wall_pass_count,
)
from five_axis_slicer.algorithms.planar.thin_wall import PlanarThinWallError


def test_open_wall_has_one_centreline_deposition_and_material_volume():
    parameters = ThinWallParameters(0.6, 0.2)
    path = generate_open_wall_toolpath(
        "op", ((0, 0, 1), (10, 0, 1)), width_mm=0.6, layer_id="layer-1", parameters=parameters
    )
    assert path.points[-1].material_volume_mm3 == pytest.approx(1.2)
    assert path.points[-1].extrusion_role == "thin_wall"


def test_below_minimum_rejects_but_multi_pass_open_wall_is_supported():
    parameters = ThinWallParameters(0.6, 0.2)
    with pytest.raises(PlanarThinWallError, match="planar.thin_wall_below_minimum"):
        thin_wall_pass_count(0.3, parameters)
    path = generate_open_wall_toolpath(
        "op", ((0, 0, 1), (10, 0, 1)), width_mm=1.2, layer_id="layer-1", parameters=parameters
    )
    assert len(path.points) == 4
    assert any(point.point_type == "travel" for point in path.points)
    assert path.points[-1].material_volume_mm3 > 0


def test_closed_wall_closes_each_pass_and_reduce_policy_accepts_narrow_wall():
    reduced = ThinWallParameters(0.6, 0.2, insufficient_width_strategy="reduce")
    path = generate_open_wall_toolpath(
        "closed",
        ((0, 0, 1), (4, 0, 1), (4, 4, 1), (0, 4, 1)),
        width_mm=0.3,
        layer_id="layer-1",
        parameters=reduced,
        closed=True,
    )
    assert path.points[-1].position == path.points[0].position
    assert sum(point.material_volume_mm3 for point in path.points) > 0
