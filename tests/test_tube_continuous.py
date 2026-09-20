from __future__ import annotations

import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.tube.continuous import (  # noqa: E402
    generate_continuous_toolpath,
    rotation_minimizing_frames,
    solve_continuous_xyzac_trajectory,
    validate_continuous_tube,
)
from five_axis_slicer.algorithms.tube.geometry import (  # noqa: E402
    CenterlinePrimitive,
    TubeFeature,
    manual_tube_feature,
)
from five_axis_slicer.algorithms.tube.indexed import TubePlanningError  # noqa: E402
from five_axis_slicer.kinematics.xyzac import XYZACInverseKinematicsError  # noqa: E402
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE  # noqa: E402
from five_axis_slicer.manufacturing.resources import NozzleProfile  # noqa: E402
from five_axis_slicer.manufacturing.setup import TubeProcessParameters  # noqa: E402
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath  # noqa: E402
from five_axis_slicer.validation.indexed_tube import CollisionBox  # noqa: E402


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=False))


def _straight(length=2.0):
    return manual_tube_feature(
        ((0.0, 0.0, 50.0), (0.0, 0.0, 50.0 + length)), outer_radius_mm=2.0, inner_radius_mm=1.0
    )


def _parameters(**changes):
    return replace(
        TubeProcessParameters(
            layer_height_mm=1.0,
            contour_chord_error_mm=0.02,
            deposition_feedrate_mm_min=5.0,
            travel_feedrate_mm_min=5.0,
        ),
        **changes,
    )


def _nozzle():
    return NozzleProfile(
        resource_id="continuous-test",
        display_name="slender",
        orifice_diameter_mm=0.02,
        filament_diameter_mm=1.75,
        interface="test",
        length_mm=2.0,
        outer_profile_rz_mm=((0.01, 0.0), (0.01, 2.0)),
    )


def _profile():
    # Analytic fixture is centered at the rotary origin; give the test machine
    # signed linear travel explicitly, without changing the built-in template.
    return replace(
        GENERIC_XYZAC_REFERENCE,
        joints=tuple(
            replace(j, soft_limit_min=-1000.0, soft_limit_max=1000.0)
            if j.joint_type == "linear"
            else j
            for j in GENERIC_XYZAC_REFERENCE.joints
        ),
    )


def test_straight_rmf_preserves_frame_and_right_handed_basis():
    frames = rotation_minimizing_frames(
        [(0.0, 0.0, float(i)) for i in range(5)], [(0.0, 0.0, 1.0)] * 5
    )
    for frame in frames:
        assert frame.normal == (1.0, 0.0, 0.0)
        assert frame.binormal == (0.0, 1.0, 0.0)
        assert _dot(frame.normal, frame.tangent) == pytest.approx(0)


def test_planar_arc_has_exact_transport_and_space_inflection_does_not_flip():
    angles = [i * math.pi / 200 for i in range(101)]
    frames = rotation_minimizing_frames(
        [(30 * math.cos(t), 30 * math.sin(t), 0.0) for t in angles],
        [(-math.sin(t), math.cos(t), 0.0) for t in angles],
        initial_normal=(0.0, 0.0, 1.0),
    )
    assert all(math.dist(f.normal, (0.0, 0.0, 1.0)) < 1e-12 for f in frames)
    values = [i / 50 for i in range(-50, 51)]
    space = rotation_minimizing_frames(
        [(t, 0.01 * t**3, 0.003 * t**4) for t in values],
        [(1.0, 0.03 * t**2, 0.012 * t**3) for t in values],
    )
    assert all(_dot(a.normal, b.normal) > 0.999 for a, b in zip(space, space[1:], strict=False))
    for frame in space:
        assert _dot(frame.normal, frame.normal) == pytest.approx(1)
        assert _dot(frame.tangent, frame.normal) == pytest.approx(0, abs=1e-14)
        assert _dot(frame.binormal, frame.normal) == pytest.approx(0, abs=1e-14)


@pytest.mark.parametrize(
    "points,tangents,code",
    [
        ([(0.0, 0.0, 0.0)] * 2, [(0.0, 0.0, 1.0)] * 2, "duplicate_point"),
        (
            [(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)],
            [(0.0, 0.0, 1.0), (0.0, 0.0, -1.0)],
            "tangent_reversal",
        ),
        ([(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)], [(0.0, 0.0, 0.0), (0.0, 0.0, 1.0)], "zero_direction"),
    ],
)
def test_rmf_rejects_ambiguous_samples(points, tangents, code):
    with pytest.raises(TubePlanningError, match=code):
        rotation_minimizing_frames(points, tangents)


def test_helix_pitch_seam_volume_and_partial_final_layer():
    feature = _straight(2.3)
    path = generate_continuous_toolpath("op", feature, _parameters(), seam_angle_rad=math.pi / 3)
    geometry = path.points[1:-1]
    assert len({p.layer_id for p in geometry}) == 3
    assert geometry[0].position == pytest.approx((0.75, 1.5 * math.sqrt(3) / 2, 50.0))
    for point in geometry:
        x, y, z = point.position
        phase = math.pi / 3 + 2 * math.pi * (z - 50)
        assert (x, y) == pytest.approx((1.5 * math.cos(phase), 1.5 * math.sin(phase)))
    assert geometry[-1].position[2] == pytest.approx(52.3)
    assert [e.event_type for e in path.events] == ["prime", "retract"]
    assert all(p.material_volume_mm3 == 0 for p in path.points if p.point_type != "deposition")
    volume = sum(p.material_volume_mm3 for p in path.points)
    analytic = 2.3 * math.sqrt((2 * math.pi * 1.5) ** 2 + 1) * _parameters().bead_width_mm
    assert volume == pytest.approx(analytic, rel=0.004)
    reopened = GeneratedToolpath.from_json(path.to_json())
    assert reopened.events == path.events
    for left, right in zip(reopened.points, path.points, strict=False):
        assert left.position == right.position
        assert left.nozzle_axis == pytest.approx(right.nozzle_axis)


def test_g1_spatial_arc_chain_and_nonsmooth_failure():
    # Two perpendicular quarter-circle bends share the same joint tangent.
    arc1 = CenterlinePrimitive(
        "arc",
        (0.0, 0.0, 50.0),
        (0.0, 30.0, 80.0),
        15 * math.pi,
        center=(0.0, 30.0, 50.0),
        axis=(-1.0, 0.0, 0.0),
        sweep_rad=math.pi / 2,
    )
    arc2 = CenterlinePrimitive(
        "arc",
        (0.0, 30.0, 80.0),
        (30.0, 60.0, 80.0),
        15 * math.pi,
        center=(30.0, 30.0, 80.0),
        axis=(0.0, 0.0, -1.0),
        sweep_rad=math.pi / 2,
    )
    feature = TubeFeature("body", "in", "out", 2.0, 1.0, (arc1, arc2))
    path = generate_continuous_toolpath("op", feature, _parameters())
    assert all(
        _dot(a.nozzle_axis, b.nozzle_axis) > 0.8
        for a, b in zip(path.points, path.points[1:], strict=False)
    )
    corner = manual_tube_feature(
        ((0.0, 0.0, 0.0), (0.0, 0.0, 5.0), (0.0, 5.0, 5.0)),
        outer_radius_mm=2.0,
        inner_radius_mm=1.0,
    )
    with pytest.raises(TubePlanningError, match="not_smooth"):
        generate_continuous_toolpath("op", corner, _parameters())


def test_continuous_fk_c_unwrap_and_full_motion_collision():
    feature = _straight(0.75)
    path = generate_continuous_toolpath("op", feature, _parameters())
    trajectory = solve_continuous_xyzac_trajectory(path, _profile())
    assert not trajectory.has_errors
    assert all(s.fk_position_error_mm < 1e-8 for s in trajectory.samples)
    assert all(
        abs(b.joint_positions["C"] - a.joint_positions["C"]) < math.pi
        for a, b in zip(trajectory.samples, trajectory.samples[1:], strict=False)
    )
    clear = validate_continuous_tube(feature, path, trajectory, _nozzle(), check_ipw=False)
    assert clear.ready_for_export
    # A fixture halfway through the initial clearance approach is not at a path endpoint.
    a, b = path.points[:2]
    mid = tuple((x + y) / 2 for x, y in zip(a.position, b.position, strict=False))
    obstacle = CollisionBox(
        "approach-fixture", "fixture", tuple(x - 0.03 for x in mid), tuple(x + 0.03 for x in mid)
    )
    blocked = validate_continuous_tube(
        feature,
        path,
        trajectory,
        _nozzle(),
        obstacles=(obstacle,),
        check_ipw=False,
        motion_sample_error_mm=0.02,
    )
    assert not blocked.ready_for_export
    assert blocked.collision_samples_checked > len(path.points)
    assert any(i.code == "tube.nozzle_obstacle_collision" for i in blocked.issues)


def test_continuous_rotary_exhaustion_and_motion_limits_block_export():
    # A synthetic radial-axis path exercises the discontinuity guard independently
    # of the axial-growth generator, which no longer turns C around a straight tube.
    profile = replace(
        _profile(),
        joints=tuple(
            replace(j, soft_limit_min=-math.pi, soft_limit_max=math.pi) if j.joint_id == "C" else j
            for j in _profile().joints
        ),
    )
    path = generate_continuous_toolpath("op", _straight(2), _parameters())
    radial_path = replace(
        path,
        points=tuple(
            replace(p, nozzle_axis=(-p.position[0] / 1.5, -p.position[1] / 1.5, 0.0))
            for p in path.points
        ),
    )
    axial_trajectory = solve_continuous_xyzac_trajectory(path, profile)
    assert not axial_trajectory.has_errors
    assert all(abs(s.joint_positions["C"]) < 1e-8 for s in axial_trajectory.samples)
    trajectory = solve_continuous_xyzac_trajectory(radial_path, profile)
    assert any(i.code == "tube.continuous_rotary_discontinuity" for i in trajectory.issues)
    fast = replace(path, points=tuple(replace(p, feedrate_mm_min=1e8) for p in path.points))
    codes = {i.code for i in solve_continuous_xyzac_trajectory(fast, profile).issues}
    assert "xyzac.velocity_limit_exceeded" in codes
    assert "xyzac.acceleration_limit_exceeded" in codes
    shifted = replace(
        path, points=tuple(replace(p, position=(10000.0, *p.position[1:])) for p in path.points)
    )
    with pytest.raises(XYZACInverseKinematicsError, match="axis_limit"):
        solve_continuous_xyzac_trajectory(shifted, profile)


def test_bent_axial_growth_nozzle_reaches_negative_y():
    arc = CenterlinePrimitive(
        "arc",
        (0, 0, 50),
        (0, 30, 80),
        15 * math.pi,
        center=(0, 30, 50),
        axis=(-1, 0, 0),
        sweep_rad=math.pi / 2,
    )
    feature = TubeFeature("body", "in", "out", 2, 1, (arc,))
    path = generate_continuous_toolpath("op", feature, _parameters())
    assert path.points[1].nozzle_axis == pytest.approx((0, 0, -1))
    assert path.points[-2].nozzle_axis == pytest.approx((0, -1, 0))


def test_radial_corruption_and_wrong_trajectory_are_rejected():
    feature = _straight(0.5)
    path = generate_continuous_toolpath("op", feature, _parameters())
    trajectory = solve_continuous_xyzac_trajectory(path, _profile())
    with pytest.raises(ValueError, match="correspond"):
        validate_continuous_tube(
            feature, path, replace(trajectory, source_toolpath_id="other"), _nozzle()
        )
    bad = replace(
        path,
        points=tuple(
            replace(p, position=(p.position[0] * 1.2, p.position[1] * 1.2, p.position[2]))
            for p in path.points
        ),
    )
    report = validate_continuous_tube(feature, bad, trajectory, _nozzle(), check_ipw=False)
    assert not report.ready_for_export
    assert any(i.code == "tube.maximum_radial_error_exceeded" for i in report.issues)
