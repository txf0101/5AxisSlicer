"""Exact three-lane partition must not grow an extra pass due to roundoff."""

import pytest
import math

from five_axis_slicer.algorithms.tube.buildup import TubeBuildupParameters, plan_tube_buildup
from five_axis_slicer.algorithms.tube.geometry import manual_tube_feature


def test_one_mm_wall_uses_three_equal_lanes():
    feature = manual_tube_feature(((0, 0, 0), (0, 0, 2)), outer_radius_mm=16, inner_radius_mm=15)
    parameters = TubeBuildupParameters(bead_width_mm=1 / 3, maximum_pass_spacing_mm=1 / 3)
    plan = plan_tube_buildup(feature, parameters)
    assert plan.pass_count == 3
    assert plan.pass_offsets_mm == pytest.approx((-1 / 3, 0, 1 / 3))
    assert plan.pass_count * plan.bead_width_mm == pytest.approx(1.0)


def test_bend_layers_follow_axis_and_local_material_jacobian():
    from five_axis_slicer.algorithms.tube.geometry import CenterlinePrimitive, TubeFeature
    from five_axis_slicer.algorithms.tube.buildup import generate_tube_buildup_toolpath

    arc = CenterlinePrimitive(
        "arc",
        (0, 0, 0),
        (0, 30, 30),
        15 * math.pi,
        center=(0, 30, 0),
        axis=(-1, 0, 0),
        sweep_rad=math.pi / 2,
    )
    feature = TubeFeature("tube", "in", "out", 16, 15, (arc,))
    parameters = TubeBuildupParameters(
        bead_width_mm=1 / 3, maximum_pass_spacing_mm=1 / 3, layer_height_mm=0.2
    )
    plan = plan_tube_buildup(feature, parameters)
    assert sum(layer.deposited_height_mm for layer in plan.layers) == pytest.approx(15 * math.pi)
    for layer in plan.layers:
        angle = layer.centerline_distance_mm / 30
        assert layer.plane_normal == pytest.approx((0, math.sin(angle), math.cos(angle)))
    path = generate_tube_buildup_toolpath("bend", feature, plan, parameters)
    points = [p for p in path.points if p.point_type == "deposition"]
    assert all(0 < p.layer_height_mm <= 0.2 for p in points)
    assert max(p.layer_height_mm for p in points) > 2 * min(
        p.layer_height_mm for p in points[:-200]
    )
    target = math.pi * (16**2 - 15**2) * 15 * math.pi
    assert sum(p.material_volume_mm3 for p in points) == pytest.approx(target, rel=0.002)
