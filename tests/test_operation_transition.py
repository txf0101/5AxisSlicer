from dataclasses import replace
from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.kinematics.xyzac import solve_xyzac_trajectory
from five_axis_slicer.manufacturing.controller_profile import (
    OWN_AC_OFFLINE_CONTROLLER, ToolChangeStation,
)
from five_axis_slicer.manufacturing.coordinates import RigidTransform
from five_axis_slicer.manufacturing.material_plan import (
    MaterialChannel, MaterialPlan, MaterialRegion, apply_material_plan,
)
from five_axis_slicer.manufacturing.own_printer import own_ac_profile
from five_axis_slicer.manufacturing.resources import GENERIC_NOZZLE_0_4
from five_axis_slicer.manufacturing.toolpath import (
    GeneratedToolpath, ToolpathEvent, ToolpathPoint,
)
from five_axis_slicer.postprocessing.operation_transition import (
    OperationTransitionError,
    plan_machine_non_deposition_travels,
    plan_machine_operation_transitions,
)
from five_axis_slicer.postprocessing.own_ac import postprocess_own_ac, readback_own_ac
from five_axis_slicer.postprocessing.tool_change_service import (
    ToolChangeCollisionError,
    _PrintedSegmentIndex,
    _check_printed_part,
    _nozzle_sections,
    _planar_bead_nozzle_contact,
    _profile_to_segment_distance,
    _profile_to_segments_distance_batch,
    _sample_move,
    check_non_deposition_travel_safety,
    check_operation_transition_safety,
)
from five_axis_slicer.postprocessing.toolpath_sequence import merge_toolpath_sequence


def _operation(name, x, nozzle_axis):
    return GeneratedToolpath(
        f"{name}-path", name,
        points=(
            ToolpathPoint(
                f"{name}-approach", (x, 0, 10), (1, 0, 0), nozzle_axis,
                name, "stage", "layer", "region", "approach",
                feedrate_mm_min=600,
            ),
            ToolpathPoint(
                f"{name}-deposit", (x + 1, 0, 10), (1, 0, 0), nozzle_axis,
                name, "stage", "layer", "region", "deposition", "infill",
                feedrate_mm_min=600, bead_width_mm=0.4,
                layer_height_mm=0.2, material_volume_mm3=0.08,
            ),
        ),
        events=(ToolpathEvent(
            f"{name}-prime", "prime", name, "stage", "layer", "region",
            context={"sequence_index": 0, "extrusion_length_mm": 0.5},
        ),),
    )


def _case():
    machine = own_ac_profile()
    nozzle = replace(
        GENERIC_NOZZLE_0_4, length_mm=5.0,
        outer_profile_rz_mm=((0.2, 0.0), (0.5, 1.0), (0.7, 2.0)),
    )
    path = merge_toolpath_sequence(
        "assembly",
        (_operation("base", 0, (0, 0, -1)),
         _operation("blade", 5, (0, -1, 0))),
        safe_clearance_mm=5, travel_feedrate_mm_min=600,
        retract_length_mm=1,
    )
    axes = solve_xyzac_trajectory(path, machine, tool_length_mm=5.0)
    return path, axes, machine, nozzle


def test_machine_transition_is_sampled_and_round_trips_in_nc():
    path, axes, machine, nozzle = _case()

    revised, revised_axes = plan_machine_operation_transitions(
        path, axes, machine, nozzle, safe_clearance_mm=5.0,
    )

    assert len(revised.points) > len(path.points)
    assert len(revised.points) == len(revised_axes.samples)
    transitions = [
        (point, sample) for point, sample in zip(revised.points, revised_axes.samples)
        if point.stage_id == "operation-transition"
    ]
    assert [point.point_type for point, _ in transitions] == [
        "depart", "depart", "travel", "travel", "approach",
    ]
    assert transitions[3][1].joint_positions["Z"] == pytest.approx(
        transitions[2][1].joint_positions["Z"]
    )
    assert transitions[3][1].joint_positions["A"] == pytest.approx(
        revised_axes.samples[-2].joint_positions["A"]
    )
    assert len({point.point_id for point in revised.points}) == len(revised.points)
    assert all(point.material_volume_mm3 == 0 for point, _ in transitions)
    events = {event.event_type: event for event in revised.events}
    assert events["retract"].context["sequence_index"] == 2
    assert events["safe_depart"].context["sequence_index"] == 3
    assert events["operation_change"].context["sequence_index"] == 5
    assert events["safe_approach"].context["sequence_index"] == 6
    assert events["prime"].context["sequence_index"] == 7
    assert check_operation_transition_safety(revised, revised_axes, machine, nozzle)[0] > 0
    code = postprocess_own_ac(
        revised, revised_axes, machine, nozzle, OWN_AC_OFFLINE_CONTROLLER,
    )
    report = readback_own_ac(
        code, revised, revised_axes, machine, nozzle, OWN_AC_OFFLINE_CONTROLLER,
    )
    assert report.passed
    assert report.expected_points == len(revised.points)


def test_machine_transition_blocks_when_clearance_exceeds_axis_limit():
    path, axes, machine, nozzle = _case()
    limited = replace(machine, joints=tuple(
        replace(joint, soft_limit_max=40.0) if joint.joint_id == "Z" else joint
        for joint in machine.joints
    ))

    with pytest.raises(OperationTransitionError, match="clearance exceeds Z limit") as error:
        plan_machine_operation_transitions(
            path, axes, limited, nozzle, safe_clearance_mm=50.0,
        )

    assert error.value.context["required_machine_z_mm"] > 40
    assert error.value.context["z_soft_limit_max_mm"] == 40


def test_machine_transition_blocks_when_target_nozzle_pose_hits_printed_bead():
    _, _, machine, nozzle = _case()
    path = merge_toolpath_sequence(
        "occupied",
        (_operation("base", 0, (0, 0, -1)),
         _operation("blade", 0.5, (0, -1, 0))),
        safe_clearance_mm=5, travel_feedrate_mm_min=600,
        retract_length_mm=1,
    )
    axes = solve_xyzac_trajectory(path, machine, tool_length_mm=5)

    with pytest.raises(OperationTransitionError, match="target nozzle pose") as error:
        plan_machine_operation_transitions(
            path, axes, machine, nozzle, safe_clearance_mm=5,
        )

    assert abs(error.value.context["target_joints"]["A"]) == pytest.approx(
        1.5707963267948966
    )
    assert error.value.context["measured_distance_mm"] <= 0.2
    assert error.value.context["nozzle_section_height_mm"] >= 0


def test_material_change_stays_before_complete_transition_and_target_deposition():
    path, _, machine, nozzle = _case()
    material_plan = MaterialPlan(
        "two-colour",
        (
            MaterialChannel("T0", "PLA-red", "T0", 195, 3),
            MaterialChannel("T1", "PLA-blue", "T1", 195, 3),
        ),
        (
            MaterialRegion("region", "T0", "op01-"),
            MaterialRegion("region", "T1", "op02-"),
        ),
    )
    coloured = apply_material_plan(path, material_plan)
    axes = solve_xyzac_trajectory(coloured, machine, tool_length_mm=5.0)

    revised, revised_axes = plan_machine_operation_transitions(
        coloured, axes, machine, nozzle, safe_clearance_mm=5,
    )

    assert revised_axes.source_toolpath_id == revised.toolpath_id
    switches = [event for event in revised.events if event.event_type == "switch"]
    assert [event.context["channel_id"] for event in switches] == ["T0", "T1"]
    first_transition = next(
        index for index, point in enumerate(revised.points)
        if point.stage_id == "operation-transition"
    )
    target_deposition = next(
        index for index, point in enumerate(revised.points)
        if point.point_type == "deposition" and point.stage_id.startswith("op02-")
    )
    assert switches[1].context["sequence_index"] == first_transition
    assert first_transition < target_deposition
    assert all(
        event.context["sequence_index"] == first_transition
        for event in revised.events
        if event.stage_id == "material_switch" and event.context["channel_id"] == "T1"
        and event.event_type not in {"unload", "retract", "cut", "park"}
    )
    controller = replace(
        OWN_AC_OFFLINE_CONTROLLER,
        tool_change_station=ToolChangeStation(
            clearance_z_mm=100,
            cutter_xyz_mm=(50, 50, 20),
            exchange_xyz_mm=(60, 50, 20),
            purge_xyz_mm=(70, 50, 20),
            wipe_start_xyz_mm=(80, 50, 20),
            wipe_end_xyz_mm=(90, 50, 20),
        ),
    )
    code = postprocess_own_ac(
        revised, revised_axes, machine, nozzle, controller,
    )
    assert "T0" in code and "T1" in code
    assert code.index("T0") < code.index("T1")
    assert readback_own_ac(
        code, revised, revised_axes, machine, nozzle, controller,
    ).passed


def test_machine_waypoints_round_trip_with_nonzero_mount_translation():
    path, _, machine, nozzle = _case()
    mount = RigidTransform.from_translation(
        (12.0, -7.0, 9.0), source_frame="build", target_frame="workpiece",
    )
    axes = solve_xyzac_trajectory(
        path, machine, tool_length_mm=5.0,
        T_workpiece_from_build=mount,
    )

    revised, revised_axes = plan_machine_operation_transitions(
        path, axes, machine, nozzle, safe_clearance_mm=5,
        T_workpiece_from_build=mount,
    )

    assert check_operation_transition_safety(
        revised, revised_axes, machine, nozzle,
        T_workpiece_from_build=mount,
    )[0] > 0
    endpoint = next(
        index for index, point in enumerate(revised.points)
        if point.point_id.endswith("-arrival")
    )
    assert revised.points[endpoint].position == pytest.approx(
        revised.points[endpoint + 1].position
    )
    assert revised_axes.samples[endpoint].joint_positions == pytest.approx(
        revised_axes.samples[endpoint + 1].joint_positions
    )


def test_cached_printed_segment_candidates_match_exact_prefix_collision_check():
    _, _, machine, nozzle = _case()
    path = merge_toolpath_sequence(
        "occupied",
        (_operation("base", 0, (0, 0, -1)),
         _operation("blade", 0.5, (0, -1, 0))),
        safe_clearance_mm=5, travel_feedrate_mm_min=600,
        retract_length_mm=1,
    )
    axes = solve_xyzac_trajectory(path, machine, tool_length_mm=5)
    sequence = next(
        index for index, point in enumerate(path.points)
        if point.stage_id == "operation-transition"
    )
    sections = _nozzle_sections(nozzle.outer_profile_rz_mm)
    radius = max(section[0] for section in sections)
    printed_index = _PrintedSegmentIndex(path, radius)
    target = axes.samples[sequence + 2].joint_positions
    samples = _sample_move(
        target, target, machine, 5.0, sections, None, 0.5,
        label="endpoint", exempt_recent=False,
    )
    collision_contexts = []
    for cache in (None, printed_index):
        with pytest.raises(ToolChangeCollisionError) as error:
            _check_printed_part(
                path, sequence, samples, radius, checkpoint=None,
                printed_index=cache,
            )
        collision_contexts.append(error.value.context)
    assert collision_contexts[0] == collision_contexts[1]

    clear = dict(target) | {"Z": target["Z"] + 30.0}
    clear_samples = _sample_move(
        clear, clear, machine, 5.0, sections, None, 0.5,
        label="clear", exempt_recent=False,
    )
    assert _check_printed_part(path, sequence, clear_samples, radius, checkpoint=None) == 0
    assert _check_printed_part(
        path, sequence, clear_samples, radius, checkpoint=None,
        printed_index=printed_index,
    ) == 0


def _air_point(template, point_id, position):
    return replace(
        template, point_id=point_id, position=position, point_type="travel",
        extrusion_role="none", bead_width_mm=None, layer_height_mm=None,
        material_volume_mm3=0.0,
    )


def test_same_operation_vertical_departure_clears_completed_bead():
    _, _, machine, nozzle = _case()
    base = _operation("one", 0, (0, 0, -1))
    path = replace(base, points=(
        *base.points,
        _air_point(base.points[-1], "one-lift", (1, 0, 13)),
    ))
    axes = solve_xyzac_trajectory(path, machine, tool_length_mm=5)

    checked, _ = check_non_deposition_travel_safety(path, axes, machine, nozzle)

    assert checked > 0


def test_same_operation_travel_rejects_nozzle_body_above_tip():
    _, _, machine, nozzle = _case()
    base = _operation("one", 0, (0, 0, -1))
    high_start = replace(base.points[0], position=(0, 0, 12))
    high_deposit = replace(base.points[1], position=(1, 0, 12))
    path = replace(base, points=(
        high_start, high_deposit,
        _air_point(high_deposit, "one-lift", (1, 3, 13)),
        _air_point(high_deposit, "one-cross-under", (1, 0, 10)),
    ))
    axes = solve_xyzac_trajectory(path, machine, tool_length_mm=5)

    with pytest.raises(ToolChangeCollisionError) as error:
        check_non_deposition_travel_safety(path, axes, machine, nozzle)

    assert error.value.code == "motion.non_deposition_travel_collision"
    assert error.value.section_height_mm > 0


def test_planar_bead_uses_layer_height_and_exact_nozzle_cone_at_adjacent_start():
    _, _, machine, nozzle = _case()
    path = _operation("planar", 0, (0, 0, -1))
    profile = ((0.2, 0.0), (3.0, 2.0), (3.0, 12.5))
    sections = _nozzle_sections(profile)
    radius = max(section[0] for section in sections)
    printed_index = _PrintedSegmentIndex(path, radius)

    def inspect(x, y, tip_z, *, use_finite_bead=True):
        joints = {"X": x, "Y": y, "Z": tip_z + 12.5, "A": 0.0, "C": 0.0}
        samples = _sample_move(
            joints, joints, machine, 12.5, sections, None, 0.5,
            label="planar-target", exempt_recent=False,
        )
        return _check_printed_part(
            path, 2, samples, radius, checkpoint=None,
            nozzle_profile=profile if use_finite_bead else None,
            printed_index=printed_index,
        )

    # Bead centres are one requested width apart. Their actual 0.2 mm layer
    # height is below the tip; the enlarged axial sample bin must not invent
    # a cone collision above the layer top.
    assert inspect(1, 0.40012, 10) == 0
    with pytest.raises(ToolChangeCollisionError):
        inspect(1, 0.40012, 10, use_finite_bead=False)

    with pytest.raises(ToolChangeCollisionError) as crossing:
        inspect(0.5, 0, 10)
    assert crossing.value.section_height_mm == pytest.approx(0)

    with pytest.raises(ToolChangeCollisionError) as cone:
        inspect(1, 0.40012, 9.9)
    assert cone.value.section_height_mm > 0


def test_vertical_planar_batch_matches_finite_bead_scalar_geometry():
    path = _operation("planar", 0, (0, 0, -1))
    profile = ((0.2, 0.0), (0.7, 0.4), (3.0, 2.0), (3.0, 12.5))
    generator = np.random.default_rng(20260924)
    start, end = path.points[0].position, path.points[1].position
    for _ in range(80):
        tip = (
            float(generator.uniform(-2.0, 3.0)),
            float(generator.uniform(-1.0, 1.0)),
            float(generator.uniform(7.0, 11.0)),
        )
        direct = _planar_bead_nozzle_contact(
            tip, start, end, path.points[1].bead_width_mm,
            path.points[1].layer_height_mm, profile,
        )
        expected_collision = direct is not None and direct[0] <= direct[1]
        sample = (tip, 0.2, (0.0, 0.0, 1.0), 0.0, 0.0,
                  "random-planar", False, 0.0, 2.0)
        try:
            _check_printed_part(
                path, 2, (sample,), 3.0, checkpoint=None,
                nozzle_profile=profile,
            )
            actual_collision = False
        except ToolChangeCollisionError:
            actual_collision = True
        assert actual_collision == expected_collision


def test_same_operation_crossing_gets_machine_hop_and_strict_nc_readback():
    _, _, machine, nozzle = _case()
    base = _operation("one", 0, (0, 0, -1))
    path = replace(base, points=(
        replace(base.points[0], position=(-1, 0, 10)),
        replace(base.points[1], position=(1, 0, 10)),
        _air_point(base.points[1], "one-clear-lift", (1, 2, 13)),
        _air_point(base.points[1], "one-clear-return", (0, 2, 10)),
        _air_point(base.points[1], "one-crossing-target", (0, -2, 10)),
        replace(base.points[1], point_id="one-next-deposit", position=(0, -3, 10)),
    ), events=(
        ToolpathEvent(
            "one-retract", "retract", "one", "stage", "layer", "region",
            context={"sequence_index": 4, "extrusion_length_mm": -1.0},
        ),
        ToolpathEvent(
            "one-prime-again", "prime", "one", "stage", "layer", "region",
            context={"sequence_index": 5, "extrusion_length_mm": 1.0},
        ),
    ))
    axes = solve_xyzac_trajectory(path, machine, tool_length_mm=5)
    with pytest.raises(ToolChangeCollisionError):
        check_non_deposition_travel_safety(path, axes, machine, nozzle)

    revised, revised_axes = plan_machine_non_deposition_travels(
        path, axes, machine, nozzle, safe_clearance_mm=5,
    )

    assert len(revised.points) > len(path.points)
    assert revised_axes.source_toolpath_id == revised.toolpath_id
    assert revised.points[-2].point_id == "one-crossing-target"
    assert revised.events[0].context["sequence_index"] < revised.events[1].context["sequence_index"]
    assert check_non_deposition_travel_safety(revised, revised_axes, machine, nozzle)[0] > 0
    code = postprocess_own_ac(
        revised, revised_axes, machine, nozzle, OWN_AC_OFFLINE_CONTROLLER,
    )
    assert readback_own_ac(
        code, revised, revised_axes, machine, nozzle, OWN_AC_OFFLINE_CONTROLLER,
    ).passed


def test_planar_same_layer_endpoint_bond_is_local_to_next_deposition():
    _, _, machine, nozzle = _case()
    base = _operation("one", 0, (0, 0, -1))
    path = replace(base, points=(
        replace(base.points[0], position=(-1, 0, 10)),
        replace(base.points[1], position=(1, 0, 10)),
        _air_point(base.points[1], "one-above", (0, 0, 13)),
        replace(
            _air_point(base.points[1], "one-bond-start", (0, 0, 10)),
            stage_id="next-skin-stage",
        ),
        replace(
            base.points[1], point_id="one-bond-deposit",
            position=(0, -1, 10), stage_id="next-skin-stage",
        ),
    ))
    axes = solve_xyzac_trajectory(path, machine, tool_length_mm=5)

    checked, contacts = check_non_deposition_travel_safety(path, axes, machine, nozzle)

    assert checked > 0
    assert contacts > 0


def test_curved_bead_top_does_not_invent_material_above_the_surface():
    base = _operation("sphere", 0, (0, 0, -1))
    old_axis = (-0.09913092293022191, 0.4637878075001579, -0.8803828313484986)
    start = (-12.040856237762267, -18.62881026792301, 33.4865095250965)
    end = (3.981758737697247, -18.62881026792301, 35.36204372583136)
    target = (3.8667289248201966, -18.279612621689115, 35.556508278148655)
    path = replace(base, points=(
        replace(base.points[0], position=start, nozzle_axis=old_axis),
        replace(base.points[1], position=end, nozzle_axis=old_axis),
        _air_point(base.points[1], "sphere-next-start", target),
    ))
    profile = ((0.2, 0.0), (3.0, 2.0), (3.0, 12.5))
    outward = (0.09626711016149868, -0.455094090166534, 0.8852242724850288)

    def inspect(tip):
        sample = (tip, 0.2, outward, 0.0, 0.0, "curve-target", False, 0.0, 0.0)
        return _check_printed_part(
            path, 2, (sample,), 3.0, checkpoint=None, nozzle_profile=profile,
        )

    assert inspect(target) == 0
    with pytest.raises(ToolChangeCollisionError):
        inspect(end)


@pytest.mark.parametrize("rotary", [(0.0, 0.0), (0.25, -0.15)])
def test_planar_spatial_index_matches_full_profile_scan_at_any_pose(rotary):
    _, _, machine, nozzle = _case()
    path = _operation("planar", 0, (0, 0, -1))
    sections = _nozzle_sections(nozzle.outer_profile_rz_mm)
    radius = max(section[0] for section in sections)
    index = _PrintedSegmentIndex(path, radius)
    joints = {"X": 0.5, "Y": 0.15, "Z": 15.0, "A": rotary[0], "C": rotary[1]}
    samples = _sample_move(
        joints, joints, machine, 5.0, sections, None, 0.5,
        label="profile-index", exempt_recent=False,
    )

    def outcome(cache):
        try:
            return _check_printed_part(
                path, 2, samples, radius, checkpoint=None,
                nozzle_profile=nozzle.outer_profile_rz_mm, printed_index=cache,
            )
        except ToolChangeCollisionError as error:
            return error.context

    assert outcome(index) == outcome(None)


def test_batched_nozzle_frustum_distance_matches_scalar_geometry():
    generator = np.random.default_rng(20260924)
    starts = generator.uniform(-3.0, 3.0, size=(24, 3))
    ends = starts + generator.uniform(-1.0, 1.0, size=(24, 3))
    tip = (0.3, -0.2, 0.4)
    direction = np.asarray((0.25, -0.35, 0.9))
    direction /= np.linalg.norm(direction)
    profile = ((0.2, 0.0), (1.2, 1.5), (2.8, 4.0))

    distances, heights = _profile_to_segments_distance_batch(
        tip, direction, profile, starts, ends,
    )
    scalar = [
        _profile_to_segment_distance(tip, direction, profile, start, end)
        for start, end in zip(starts, ends)
    ]

    assert distances == pytest.approx([item[0] for item in scalar], abs=1.0e-7)
    assert heights == pytest.approx([item[1] for item in scalar], abs=1.0e-5)
