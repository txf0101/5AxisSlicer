from dataclasses import replace
import math

import cadquery as cq
import pytest

from five_axis_slicer.algorithms.fan.transitions import radial_transfer, check_linear_clearance
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath, ToolpathPoint, ToolpathEvent
from five_axis_slicer.postprocessing.fan_merge import (
    merge_fan_operations,
    FAN_OPERATION_ORDER,
    fan_program_line_index,
)
from five_axis_slicer.postprocessing.own_ac import postprocess_own_ac, readback_own_ac
from five_axis_slicer.manufacturing.own_printer import own_ac_profile
from five_axis_slicer.manufacturing.resources import GENERIC_NOZZLE_0_4
from five_axis_slicer.manufacturing.controller_profile import OWN_AC_OFFLINE_CONTROLLER
from five_axis_slicer.kinematics.xyzac import solve_xyzac_trajectory


def test_transfer_wraps_outside_instead_of_crossing_hub():
    points = radial_transfer((11, 0, 1), (-11, 0, 1), outside_radius_mm=15)
    hub = cq.Workplane("XY").circle(10).extrude(2).val().wrapped
    report = check_linear_clearance(points, {"hub": hub}, tip_radius_mm=0.2)
    assert not report.collisions
    assert report.minimum_clearance_mm == pytest.approx(0.8)
    assert not report.machine_qualified
    crossing = check_linear_clearance((points[0], points[-1]), {"hub": hub}, tip_radius_mm=0.2)
    assert crossing.collisions == ((0, "hub"),)


def test_previously_printed_blade_is_an_obstacle():
    obstacle = cq.Workplane("XY").box(2, 2, 2).translate((15, 0, 1)).val().wrapped
    report = check_linear_clearance(
        ((11, 0, 1), (16, 0, 1)), {"blade1": obstacle}, tip_radius_mm=0.2
    )
    assert report.collisions == ((0, "blade1"),)


def _operations():
    result = {}
    for i, key in enumerate(FAN_OPERATION_ORDER):
        point = ToolpathPoint(
            "start",
            (i * 2, 0, 20),
            (1, 0, 0),
            (0, 0, -1),
            key,
            "s",
            "l",
            "r",
            "travel",
            feedrate_mm_min=100,
        )
        end = replace(
            point,
            point_id="end",
            position=(i * 2 + 1, 0, 20),
            point_type="deposition",
            extrusion_role="infill",
            material_volume_mm3=0.08,
        )
        if key in {"index90", "transfer12", "transfer23", "finish"}:
            end = replace(end, point_type="travel", extrusion_role="none", material_volume_mm3=0)
        event = ToolpathEvent("event", "operation_change", key, "s", context={"sequence_index": 0})
        result[key] = GeneratedToolpath(key, key, points=(point, end), events=(event,))
    return result


def test_merger_offsets_events_and_keeps_source_index():
    merged, index = merge_fan_operations(_operations(), job_id="fan")
    assert len(merged.points) == 16
    assert [e.context["sequence_index"] for e in merged.events] == list(range(0, 16, 2))
    assert index[4].operation_id == "blade2" and index[4].first_point == 9
    assert len({p.point_id for p in merged.points}) == 16
    assert sum(p.material_volume_mm3 for p in merged.points) == pytest.approx(0.32)


def test_missing_blade_and_implicit_index_are_rejected():
    operations = _operations()
    del operations["blade2"]
    with pytest.raises(ValueError, match="missing_or_unknown"):
        merge_fan_operations(operations, job_id="fan")
    operations = _operations()
    source = operations["index90"]
    operations["index90"] = replace(
        source, events=(replace(source.events[0], event_type="index_start"),)
    )
    with pytest.raises(ValueError, match="implicit_index"):
        merge_fan_operations(operations, job_id="fan")


def test_merged_program_one_global_solve_readback_and_tamper_rejection():
    merged, index = merge_fan_operations(_operations(), job_id="fan")
    machine = own_ac_profile()
    trajectory = solve_xyzac_trajectory(merged, machine)
    code = postprocess_own_ac(
        merged, trajectory, machine, GENERIC_NOZZLE_0_4, OWN_AC_OFFLINE_CONTROLLER
    )
    report = readback_own_ac(
        code, merged, trajectory, machine, GENERIC_NOZZLE_0_4, OWN_AC_OFFLINE_CONTROLLER
    )
    assert report.passed and not report.machine_executable
    line_index = fan_program_line_index(code, index)
    assert len(line_index) == 8
    assert code.splitlines()[line_index[4]["first_motion_line"] - 1].startswith("G1 ")
    changed = code.replace("M83 ; relative extrusion", "M82 ; tampered extrusion")
    assert not readback_own_ac(
        changed, merged, trajectory, machine, GENERIC_NOZZLE_0_4, OWN_AC_OFFLINE_CONTROLLER
    ).passed


def test_radial_pose_requires_changing_c_along_circumference():
    operation = _operations()["blade1"]
    points = []
    for i, theta in enumerate((0, 0.1, 0.2)):
        normal = (math.cos(theta), math.sin(theta), 0)
        points.append(
            replace(
                operation.points[0],
                point_id=f"p{i}",
                position=(20 * normal[0], 20 * normal[1], 50),
                nozzle_axis=tuple(-v for v in normal),
            )
        )
    path = replace(operation, points=tuple(points), events=())
    trajectory = solve_xyzac_trajectory(path, own_ac_profile())
    assert all(abs(abs(s.joint_positions["A"]) - math.pi / 2) < 1e-8 for s in trajectory.samples)
    assert abs(
        trajectory.samples[-1].joint_positions["C"] - trajectory.samples[0].joint_positions["C"]
    ) == pytest.approx(0.2)
