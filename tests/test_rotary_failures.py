from __future__ import annotations

from dataclasses import replace
import math
import os
from pathlib import Path
import re
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from five_axis_slicer.algorithms.rotary import RotaryPlanningError, build_rotary_plan
from five_axis_slicer.kinematics.rotary import solve_prescribed_rotary_trajectory
from five_axis_slicer.kinematics.xyzac import MachineAxisSample, _motion_limit_issues
from five_axis_slicer.manufacturing.machine import PostAxisMap
from five_axis_slicer.manufacturing.resources import ResourceSnapshot
from five_axis_slicer.manufacturing.rotary_parameters import (
    RotaryAngularRegion,
)
from five_axis_slicer.postprocessing.indexed_tube import readback_indexed_gcode
from five_axis_slicer.postprocessing.rotary_product import generate_rotary_product
from five_axis_slicer.rotary_controller import RotaryController
from five_axis_slicer.rotary_generation_context import (
    rotary_build_from_source,
    rotary_workpiece_from_build,
)
from five_axis_slicer.validation.indexed_tube import CollisionBox
from test_rotary_integration import _controller


def test_failure_matrix_overlap_empty_and_excess_radial_width(tmp_path: Path) -> None:
    controller, operation, _model, _axis, _surface = _controller(
        tmp_path, "rotary_around_part"
    )
    overlap = replace(
        operation.geometry,
        angular_regions=(
            RotaryAngularRegion("A", 0, math.pi),
            RotaryAngularRegion("B", math.pi / 2, math.pi * 1.5),
        ),
    )
    with pytest.raises(RotaryPlanningError, match="rotary.region_overlap"):
        build_rotary_plan(replace(operation, geometry=overlap))
    with pytest.raises(RotaryPlanningError, match="rotary.region_empty"):
        build_rotary_plan(
            replace(operation, geometry=replace(operation.geometry, angular_regions=()))
        )

    thin_controller, thin, *_ = _controller(tmp_path / "thin", "rotary_thin_wall")
    del thin_controller
    too_many = replace(
        thin,
        parameters=replace(
            thin.parameters,
            radial_pass_count=3,
            radial_spacing_mm=0.6,
            wall_thickness_mm=1.0,
        ),
    )
    with pytest.raises(RotaryPlanningError, match="rotary.thin_wall_passes_exceed_width"):
        build_rotary_plan(too_many)


def test_failure_matrix_axis_limit_and_acceleration_block_products(tmp_path: Path) -> None:
    controller, operation, model, _axis, _surface = _controller(
        tmp_path / "axis", "rotary_spiral"
    )
    machine = controller.machine_profile()
    limited = replace(
        machine,
        joints=tuple(
            replace(joint, soft_limit_min=-0.01, soft_limit_max=0.01)
            if joint.joint_id == "C"
            else joint
            for joint in machine.joints
        ),
    )
    limited_setup = replace(
        controller.setup,
        machine=ResourceSnapshot.capture("machine", limited),
    )
    limited_controller = RotaryController(
        model, setup=limited_setup, operations=(operation,)
    )
    with pytest.raises(ValueError, match="xyzac.orientation_unreachable"):
        limited_controller.generate_operation(operation.operation_id)
    failed_state = limited_controller.product_state(operation.operation_id)
    assert failed_state is not None
    assert failed_state.status == "error"
    assert failed_state.result_payload["issue"]["code"] == "xyzac.orientation_unreachable"
    assert failed_state.result_payload["issue"]["object_id"].startswith("point-")

    fast_controller, fast, *_ = _controller(tmp_path / "accel", "rotary_thin_wall")
    fast = fast_controller.configure_operation(
        operation_id=fast.operation_id,
        parameters=replace(
            fast.parameters,
            angular_velocity_rad_s=0.5,
            feedrate_mm_min=600,
            travel_feedrate_mm_min=1800,
        ),
    )
    result = fast_controller.generate_operation(fast.operation_id)
    assert result.manifest.status.value == "error"
    assert "xyzac.acceleration_limit_exceeded" in result.manifest.issues
    assert not result.exportable


def test_failure_matrix_collision_checks_segment_interior_and_blocks_export(
    tmp_path: Path,
) -> None:
    controller, operation, model, _axis, _surface = _controller(
        tmp_path, "rotary_spiral"
    )
    setup = controller.setup
    machine = controller.machine_profile()
    result = generate_rotary_product(
        model,
        operation,
        machine,
        controller.nozzle_profile(),
        T_build_from_source=rotary_build_from_source(setup),
        T_workpiece_from_build=rotary_workpiece_from_build(setup, machine),
        obstacles=(CollisionBox("fixture-hit", "fixture", (19.5, -0.5, -0.5), (20.5, 0.5, 0.5)),),
        check_ipw=False,
        motion_sample_error_mm=0.1,
    )
    assert result.validation.collision_samples_checked > len(result.toolpath.points)
    assert any(issue.code == "rotary.nozzle_obstacle_collision" for issue in result.validation.issues)
    assert not result.exportable


def test_failure_matrix_readback_detects_rotary_word_and_event_tampering(tmp_path: Path) -> None:
    controller, operation, _model, _axis, _surface = _controller(
        tmp_path, "rotary_spiral"
    )
    result = controller.generate_operation(operation.operation_id)
    assert result.readback.passed
    changed_c = re.sub(r"\bC(-?\d+(?:\.\d+)?)", "C999", result.gcode, count=1)
    report = readback_indexed_gcode(
        changed_c,
        result.toolpath,
        result.trajectory,
        controller.machine_profile(),
        controller.nozzle_profile(),
        marker_tag="R02",
    )
    assert not report.passed
    assert report.coordinate_mismatches
    without_prime = re.sub(
        r" EVENT (\S+) prime",
        r" EVENT \1 removed",
        result.gcode,
        count=1,
    )
    event_report = readback_indexed_gcode(
        without_prime,
        result.toolpath,
        result.trajectory,
        controller.machine_profile(),
        controller.nozzle_profile(),
        marker_tag="R02",
    )
    assert not event_report.passed
    assert event_report.order_mismatches

    without_inverse_time = result.gcode.replace(
        "G93 ; inverse-time coordinated motion",
        "G94 ; inverse-time mode removed",
        1,
    )
    mode_report = readback_indexed_gcode(
        without_inverse_time,
        result.toolpath,
        result.trajectory,
        controller.machine_profile(),
        controller.nozzle_profile(),
        marker_tag="R02",
    )
    assert not mode_report.passed
    assert mode_report.order_mismatches or mode_report.feedrate_mismatches

    wrong_inverse_feed = re.sub(
        r"(; R02 POINT 1[^\n]*\nG1 [^\n]* F)(-?\d+(?:\.\d+)?)",
        r"\g<1>999999",
        result.gcode,
        count=1,
    )
    feed_report = readback_indexed_gcode(
        wrong_inverse_feed,
        result.toolpath,
        result.trajectory,
        controller.machine_profile(),
        controller.nozzle_profile(),
        marker_tag="R02",
    )
    assert not feed_report.passed
    assert feed_report.feedrate_mismatches


def test_failure_matrix_controller_axis_semantics_are_not_silently_accepted(
    tmp_path: Path,
) -> None:
    controller, operation, model, _axis, _surface = _controller(
        tmp_path, "rotary_spiral"
    )
    machine = controller.machine_profile()
    invalid = replace(
        machine,
        joints=tuple(
            replace(joint, post_axis_map=PostAxisMap("X", "deg"))
            if joint.joint_id == "C"
            else joint
            for joint in machine.joints
        ),
    )
    setup = replace(
        controller.setup,
        machine=ResourceSnapshot.capture("machine", invalid),
    )
    broken = RotaryController(model, setup=setup, operations=(operation,))
    with pytest.raises(ValueError, match="valid applied Setup"):
        broken.generate_operation(operation.operation_id)


def test_failure_matrix_dwell_is_explicitly_unsupported_until_roundtrip_exists(
    tmp_path: Path,
) -> None:
    _controller_value, operation, *_ = _controller(tmp_path, "rotary_spiral")
    with pytest.raises(RotaryPlanningError, match="rotary.dwell_unsupported"):
        build_rotary_plan(
            replace(operation, parameters=replace(operation.parameters, dwell_s=1.5))
        )


def test_failure_matrix_prescribed_phase_map_rejects_missing_extra_and_nonfinite(
    tmp_path: Path,
) -> None:
    controller, operation, _model, _axis, _surface = _controller(
        tmp_path, "rotary_spiral"
    )
    result = controller.generate_operation(operation.operation_id)
    phases = dict(result.plan.angle_by_point_id)
    missing = dict(phases)
    missing.pop(next(iter(missing)))
    extra = dict(phases) | {"not-a-toolpath-point": 0.0}
    nonfinite = dict(phases)
    nonfinite[next(iter(nonfinite))] = math.nan
    for values, code in (
        (missing, "rotary.prescribed_phase_mismatch"),
        (extra, "rotary.prescribed_phase_mismatch"),
        (nonfinite, "rotary.period_non_finite"),
    ):
        with pytest.raises(ValueError, match=code):
            solve_prescribed_rotary_trajectory(
                result.toolpath,
                controller.machine_profile(),
                prescribed_angles_rad=values,
                angular_velocity_rad_s=operation.parameters.angular_velocity_rad_s,
                tool_length_mm=controller.nozzle_profile().length_mm or 0.0,
                T_workpiece_from_build=rotary_workpiece_from_build(
                    controller.setup, controller.machine_profile()
                ),
            )


def test_failure_matrix_rotary_velocity_limit_is_reported_separately(
    tmp_path: Path,
) -> None:
    controller, operation, model, _axis, _surface = _controller(
        tmp_path, "rotary_spiral"
    )
    machine = controller.machine_profile()
    limited = replace(
        machine,
        joints=tuple(
            replace(joint, max_velocity=0.05)
            if joint.joint_id == "C"
            else joint
            for joint in machine.joints
        ),
    )
    setup = replace(
        controller.setup,
        machine=ResourceSnapshot.capture("machine", limited),
    )
    broken = RotaryController(model, setup=setup, operations=(operation,))
    result = broken.generate_operation(operation.operation_id)
    assert result.manifest.status.value == "error"
    assert "xyzac.velocity_limit_exceeded" in result.manifest.issues
    assert not result.exportable


def test_failure_matrix_motion_limits_include_start_and_stop_acceleration(
    tmp_path: Path,
) -> None:
    controller, _operation, _model, _axis, _surface = _controller(
        tmp_path, "rotary_spiral"
    )
    machine = replace(
        controller.machine_profile(),
        joints=tuple(
            replace(joint, max_acceleration=0.5)
            if joint.joint_id == "X"
            else joint
            for joint in controller.machine_profile().joints
        ),
    )
    zero = {name: 0.0 for name in ("X", "Y", "Z", "A", "C")}
    moving = dict(zero) | {"X": 1.0}
    samples = [
        MachineAxisSample("start", 0.0, zero),
        MachineAxisSample("middle", 1.0, moving),
        MachineAxisSample("end", 2.0, dict(moving) | {"X": 2.0}),
    ]
    issues = _motion_limit_issues(samples, machine)
    boundaries = {
        issue.context.get("boundary")
        for issue in issues
        if issue.code == "xyzac.acceleration_limit_exceeded"
    }
    assert boundaries == {"start", "end"}
