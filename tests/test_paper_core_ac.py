from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.controller_profile import (
    ControllerProfile,
    OWN_AC_OFFLINE_CONTROLLER,
    ToolChangeStation,
)
from five_axis_slicer.manufacturing.coordinates import RigidTransform
from five_axis_slicer.manufacturing.curve_parameters import (
    CurveGeometrySelection,
    DirectedEdgeReference,
)
from five_axis_slicer.manufacturing.freeform_parameters import (
    FreeformGeometrySelection,
    FreeformOperationDefinition,
    FreeformProcessParameters,
)
from five_axis_slicer.manufacturing.material_plan import (
    MaterialChannel,
    MaterialPlan,
    MaterialRegion,
    MaterialRuntimeNotReady,
    MaterialRuntimeState,
    apply_material_plan,
    material_statistics,
    require_material_runtime_ready,
)
from five_axis_slicer.manufacturing.own_printer import own_ac_profile
from five_axis_slicer.manufacturing.reference_descriptors import geometry_reference
from five_axis_slicer.manufacturing.resources import GENERIC_NOZZLE_0_4
from five_axis_slicer.manufacturing.toolpath import (
    GeneratedToolpath,
    ToolpathEvent,
    ToolpathPoint,
)
from five_axis_slicer.kinematics.xyzac import MachineAxisSample, MachineAxisTrajectory
from five_axis_slicer.postprocessing.freeform_product import (
    FreeformProductState,
    export_freeform_product,
    generate_freeform_product,
    state_from_freeform_result,
)
from five_axis_slicer.postprocessing.own_ac import postprocess_own_ac, readback_own_ac
from five_axis_slicer.postprocessing.tool_change_service import (
    _check_printed_part,
    _nozzle_sections,
    _section_radial_distance,
    _section_to_segment_distance,
    check_operation_transition_safety,
    plan_tool_change_service,
)
from five_axis_slicer.step_loader import load_step


def _material_plan() -> MaterialPlan:
    return MaterialPlan(
        "paper-two-channel",
        (
            MaterialChannel("T0", "PLA", "T0", 195.0, 5.0, requires_prepare_pause=False),
            MaterialChannel("T1", "PETG", "T1", 235.0, 6.0, requires_prepare_pause=False),
        ),
        (
            MaterialRegion("guide-01-pass-01", "T0"),
            MaterialRegion("guide-01-pass-02", "T1"),
        ),
        sensor_required=True,
        temperature_timeout_s=180.0,
    )


TEST_STATION_CONTROLLER = replace(
    OWN_AC_OFFLINE_CONTROLLER,
    tool_change_station=ToolChangeStation(
        clearance_z_mm=180.0,
        cutter_xyz_mm=(130.0, 100.0, 80.0),
        exchange_xyz_mm=(140.0, 100.0, 80.0),
        purge_xyz_mm=(150.0, 100.0, 80.0),
        wipe_start_xyz_mm=(160.0, 100.0, 80.0),
        wipe_end_xyz_mm=(170.0, 100.0, 80.0),
    ),
)


@pytest.fixture(scope="module")
def freeform_case():
    source = Path("example/叶轮/叶轮.stp")
    model = load_step(source)
    face_id, edge_id = "body_002_face_0006", "body_002_edge_0011"
    face = geometry_reference(model, face_id, "face")
    guide = CurveGeometrySelection(
        (DirectedEdgeReference(geometry_reference(model, edge_id, "edge"), True),),
        "adjacent_face",
        face,
    )
    operation = FreeformOperationDefinition(
        "paper-freeform-1",
        "setup-1",
        geometry=FreeformGeometrySelection((face,), (guide,)),
        parameters=FreeformProcessParameters(
            sampling_step_mm=2.0,
            path_spacing_mm=0.6,
            path_count=2,
            layer_count=1,
            feedrate_mm_min=900.0,
        ),
        material_plan=_material_plan(),
    )
    result = generate_freeform_product(
        model,
        operation,
        own_ac_profile(),
        GENERIC_NOZZLE_0_4,
        TEST_STATION_CONTROLLER,
        T_build_from_source=RigidTransform.identity("source"),
        source_path=source,
    )
    return model, operation, result


def test_pc01_contract_sources_and_unknowns_are_explicit() -> None:
    contract = json.loads(
        Path("docs/planning/paper_core_input_contract.json").read_text(encoding="utf-8")
    )
    assert contract["scope"] == "offline_only"
    assert contract["controller"]["machine_executable"] is False
    assert "actual_T0_T3_macro_files_and_hashes" in contract["known_unknowns"]
    for case in contract["cases"]:
        path, digest = case["cad_path"], case["cad_sha256"]
        if path and digest and Path(path).is_file():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest


def test_toolpath_legacy_json_remains_backward_compatible() -> None:
    payload = ToolpathPoint(
        "p1",
        (0, 0, 0),
        (1, 0, 0),
        (0, 0, -1),
        "op",
        "stage",
        "layer",
        "region",
        "deposition",
        extrusion_role="buildup",
        material_volume_mm3=1.0,
    ).to_json()
    payload.pop("material_id")
    payload.pop("channel_id")
    loaded = ToolpathPoint.from_json(payload)
    assert loaded.material_id is None and loaded.channel_id is None


def test_material_plan_assigns_identity_and_distinguishes_selection_from_transition() -> None:
    points = tuple(
        ToolpathPoint(
            f"p{index}",
            (index, 0, 0),
            (1, 0, 0),
            (0, 0, -1),
            "op",
            "stage",
            "layer",
            region,
            "deposition",
            extrusion_role="buildup",
            material_volume_mm3=1.0,
        )
        for index, region in enumerate(("guide-01-pass-01", "guide-01-pass-02"), start=1)
    )
    assigned = apply_material_plan(GeneratedToolpath("tp", "op", points=points), _material_plan())
    assert [(p.material_id, p.channel_id) for p in assigned.points] == [
        ("PLA", "T0"),
        ("PETG", "T1"),
    ]
    stats = material_statistics(assigned)
    assert stats["selection_command_count"] == 2
    assert stats["effective_channel_transition_count"] == 1
    assert stats["deposition_volume_mm3_by_material"] == {"PETG": 1.0, "PLA": 1.0}
    switch_chains = {}
    for event in assigned.events:
        if event.stage_id == "material_switch":
            switch_chains.setdefault(event.region_id, []).append(event.event_type)
    assert switch_chains == {
        "guide-01-pass-01": ["switch", "temperature_wait"],
        "guide-01-pass-02": [
            "retract",
            "cut",
            "park",
            "unload",
            "switch",
            "temperature_wait",
            "load",
            "purge",
            "prime",
            "resume",
        ],
    }


def test_stage_prefix_assigns_three_blades_and_old_channel_unload() -> None:
    plan = MaterialPlan(
        "three-colour-pla",
        (
            MaterialChannel("T0", "PLA-red", "T0", 195.0, 3.0, unload_length_mm=11.0),
            MaterialChannel("T1", "PLA-blue", "T1", 195.0, 3.0, unload_length_mm=12.0),
            MaterialChannel("T2", "PLA-yellow", "T2", 195.0, 3.0),
        ),
        (
            MaterialRegion("*", "T0", "op01-"),
            MaterialRegion("*", "T0", "op02-"),
            MaterialRegion("*", "T1", "op03-"),
            MaterialRegion("*", "T2", "op04-"),
        ),
    )
    points = tuple(
        ToolpathPoint(
            f"p{index}", (float(index), 0, 0), (1, 0, 0), (0, 0, -1),
            "op", stage, "layer", "path-00001", "deposition",
            extrusion_role="buildup", material_volume_mm3=1.0,
        )
        for index, stage in enumerate(
            ("op01-base", "op02-blade", "op03-blade", "op04-blade"), 1
        )
    )
    assigned = apply_material_plan(GeneratedToolpath("tp", "op", points=points), plan)
    assert [point.channel_id for point in assigned.points] == ["T0", "T0", "T1", "T2"]
    assert material_statistics(assigned)["effective_channel_transition_count"] == 2
    unload = [event for event in assigned.events if event.event_type == "unload"]
    assert [event.context["channel_id"] for event in unload] == ["T0", "T1"]
    assert [event.context["extrusion_length_mm"] for event in unload] == [-11.0, -12.0]


def test_colour_change_starts_before_entire_non_deposition_transition() -> None:
    def point(index, stage, point_type):
        return ToolpathPoint(
            f"p{index}", (float(index), 0, 0), (1, 0, 0), (0, 0, -1),
            "op", stage, "layer", "path-00001", point_type,
            extrusion_role="buildup" if point_type == "deposition" else "none",
            material_volume_mm3=1.0 if point_type == "deposition" else 0.0,
        )

    points = (
        point(0, "op01-base", "deposition"),
        point(1, "operation-transition", "depart"),
        point(2, "operation-transition", "travel"),
        point(3, "op02-blade", "approach"),
        point(4, "op02-blade", "deposition"),
    )
    plan = MaterialPlan(
        "two-colour", (
            MaterialChannel("T0", "PLA-red", "T0", 195.0, 3.0),
            MaterialChannel("T1", "PLA-blue", "T1", 195.0, 3.0),
        ), (
            MaterialRegion("*", "T0", "op01-"),
            MaterialRegion("*", "T1", "op02-"),
        ),
    )
    assigned = apply_material_plan(GeneratedToolpath("tp", "op", points=points), plan)
    switches = [event for event in assigned.events if event.event_type == "switch"]
    assert [event.context["sequence_index"] for event in switches] == [0, 1]
    assert assigned.points[1].point_type == "depart"


def test_controller_profile_round_trip_defaults_and_qualification_gate() -> None:
    payload = {
        "schema_version": 1,
        "profile_id": "test.controller",
        "machine_profile_id": "test.machine",
        "controller_family": "test",
    }
    profile = ControllerProfile.from_json(payload)
    assert profile.axis_mode == "absolute"
    assert profile.extrusion_mode == "relative"
    assert profile.feed_mode == "units_per_minute"
    assert profile.reorientation_absolute_z_mm == 20.0
    assert profile.cutter_relative_z_mm == 20.0
    assert not profile.machine_executable
    assert ControllerProfile.from_json(profile.to_json()) == profile
    qualified = replace(
        profile,
        controller_version="1.0",
        macro_version="1.0",
        coordinated_xyzac_verified=True,
        maximum_cumulative_c_rad=4 * math.pi,
    )
    assert qualified.machine_executable
    with pytest.raises(ValueError, match="missing required fields"):
        ControllerProfile.from_json({"schema_version": 1})


def test_material_runtime_sensor_and_temperature_fail_closed_then_recover() -> None:
    plan = _material_plan()
    bad = MaterialRuntimeState(
        {"T0": True, "T1": False},
        {"T0": 195.0, "T1": 210.0},
        temperature_tolerance_c=3.0,
    )
    with pytest.raises(MaterialRuntimeNotReady) as caught:
        require_material_runtime_ready(plan, bad)
    assert set(caught.value.issues) == {
        "material.sensor_not_ready:T1",
        "material.temperature_out_of_tolerance:T1",
    }
    ready = MaterialRuntimeState(
        {"T0": True, "T1": True},
        {"T0": 195.0, "T1": 235.0},
        temperature_tolerance_c=3.0,
    )
    require_material_runtime_ready(plan, ready)


def test_material_plan_fails_closed_for_unassigned_region() -> None:
    point = ToolpathPoint(
        "p",
        (0, 0, 0),
        (1, 0, 0),
        (0, 0, -1),
        "op",
        "stage",
        "layer",
        "missing",
        "deposition",
        extrusion_role="buildup",
        material_volume_mm3=1.0,
    )
    with pytest.raises(ValueError, match="material.region_unassigned"):
        apply_material_plan(GeneratedToolpath("tp", "op", points=(point,)), _material_plan())


def test_freeform_impeller_generates_materialized_six_file_offline_product(
    freeform_case, tmp_path: Path
) -> None:
    _model, operation, result = freeform_case
    assert result.offline_exportable and result.readback.passed
    assert not result.machine_executable
    assert len(result.plan.paths) == 2
    assert {
        point.material_id for point in result.toolpath.points if point.point_type == "deposition"
    } == {"PLA", "PETG"}
    assert {item.code for item in result.validation.issues} >= {
        "controller.version_unknown",
        "controller.macros_unverified",
        "controller.xyzac_coordination_unverified",
        "controller.cumulative_c_limit_unknown",
    }
    assert result.validation.controller_qualification["cumulative_c_travel_rad"] >= 0.0
    output = export_freeform_product(result, tmp_path / "paper-freeform")
    assert {item.name for item in output.iterdir()} == {
        "main.gcode",
        "toolpath.json",
        "machine_axes.csv",
        "warnings.json",
        "preview.json",
        "manifest.json",
    }
    state = state_from_freeform_result(operation, result)
    assert FreeformProductState.from_json(state.to_json()).status == "stale"


def test_own_ac_readback_rejects_mode_and_relative_e_tampering(freeform_case) -> None:
    _model, _operation, result = freeform_case
    bad_mode = result.gcode.replace("M83 ; relative extrusion", "M82 ; absolute extrusion", 1)
    report = readback_own_ac(
        bad_mode,
        result.toolpath,
        result.trajectory,
        own_ac_profile(),
        GENERIC_NOZZLE_0_4,
        TEST_STATION_CONTROLLER,
    )
    assert not report.passed
    assert {"mode_header_mismatch", "unexpected_absolute_extrusion"} <= set(report.issues)
    bad_e = re.sub(
        r"(; PAC POINT [^\n]+ deposition [^\n]*\nG1 [^\n]* E)([-+0-9.]+)",
        r"\g<1>999.0",
        result.gcode,
        count=1,
    )
    assert bad_e != result.gcode
    report = readback_own_ac(
        bad_e,
        result.toolpath,
        result.trajectory,
        own_ac_profile(),
        GENERIC_NOZZLE_0_4,
        TEST_STATION_CONTROLLER,
    )
    assert not report.passed and any(issue.endswith(":E") for issue in report.issues)


def test_tool_change_requires_station_and_plans_checked_route(freeform_case) -> None:
    _model, _operation, result = freeform_case
    with pytest.raises(ValueError, match="tool_change.station_unconfigured"):
        plan_tool_change_service(
            result.toolpath, result.trajectory, own_ac_profile(), GENERIC_NOZZLE_0_4,
            OWN_AC_OFFLINE_CONTROLLER,
        )
    service = plan_tool_change_service(
        result.toolpath, result.trajectory, own_ac_profile(), GENERIC_NOZZLE_0_4,
        TEST_STATION_CONTROLLER,
    )
    assert service.checked_samples > 0
    labels = [
        move.label for moves in service.moves_before_event.values() for move in moves
    ]
    assert "safe_depart" in labels
    assert "reorient_at_station" in labels
    assert "safe_approach" in labels


def test_tool_change_rejects_station_inside_printed_part(freeform_case) -> None:
    _model, _operation, result = freeform_case
    switches = [event for event in result.toolpath.events if event.event_type == "switch"]
    sequence = int(switches[1].context["sequence_index"])
    before = result.trajectory.samples[sequence - 1].joint_positions
    station = TEST_STATION_CONTROLLER.tool_change_station
    assert station is not None
    unsafe = replace(
        TEST_STATION_CONTROLLER,
        tool_change_station=replace(
            station,
            cutter_xyz_mm=(before["X"], before["Y"], before["Z"]),
        ),
    )
    with pytest.raises(ValueError, match="tool_change.printed_part_collision"):
        plan_tool_change_service(
            result.toolpath, result.trajectory, own_ac_profile(), GENERIC_NOZZLE_0_4,
            unsafe,
        )


def test_nozzle_profile_collision_uses_axial_sections_not_spheres() -> None:
    sections = _nozzle_sections(((0.2, 0.0), (3.0, 2.0), (3.0, 12.5)))
    assert len(sections) > 20
    assert max(height for _radius, height, _lower, _upper in sections) == 12.5
    assert sections[0][2] == 0.0 and sections[-1][3] == 0.0
    axis = (0.0, 0.0, 1.0)
    # A wide section at z=2 must not occupy the empty space below the tip.
    assert math.isinf(_section_radial_distance(
        (0.0, 0.0, 2.0), axis, 0.4,
        (0.0, 0.0, -0.2), (0.1, 0.0, -0.2),
    ))
    assert _section_radial_distance(
        (0.0, 0.0, 2.0), axis, 0.4,
        (0.5, 0.0, 2.0), (0.6, 0.0, 2.0),
    ) == pytest.approx(0.5)
    # Axial and radial margins must combine in 3D, not as a square box.
    assert _section_to_segment_distance(
        (0.0, 0.0, 2.0), axis, 0.25, 0.25, 0.55,
        (0.65, 0.0, 1.356), (0.65, 0.0, 1.356),
    ) > 0.4
    assert _section_to_segment_distance(
        (0.0, 0.0, 2.0), axis, 0.25, 0.25, 0.55,
        (0.55, 0.0, 2.0), (0.8, 0.0, 2.0),
    ) == pytest.approx(0.0)
    assert _section_to_segment_distance(
        (0.0, 0.0, 0.0), axis, 0.0, 0.25, 0.55,
        (0.0, 0.0, -0.3), (0.0, 0.0, -0.3),
    ) == pytest.approx(0.3)


def test_operation_transition_checks_existing_travel_against_printed_beads() -> None:
    def point(index, position, point_type, stage):
        return ToolpathPoint(
            f"motion-{index}", position, (0, 1, 0), (0, 0, -1),
            "motion", stage, "layer", "region", point_type,
            extrusion_role="buildup" if point_type == "deposition" else "none",
            bead_width_mm=0.4 if point_type == "deposition" else None,
            layer_height_mm=0.2 if point_type == "deposition" else None,
            material_volume_mm3=0.1 if point_type == "deposition" else 0.0,
        )

    points = (
        point(0, (0.0, 0.0, 10.0), "deposition", "op01-base"),
        point(1, (0.0, 1.0, 10.0), "deposition", "op01-base"),
        point(2, (0.0, 1.0, 11.0), "depart", "operation-transition"),
        point(3, (0.0, 0.5, 10.0), "travel", "operation-transition"),
    )
    toolpath = GeneratedToolpath("motion", "motion", points=points)
    trajectory = MachineAxisTrajectory(
        "motion-axes", own_ac_profile().profile_id, toolpath.toolpath_id,
        tuple(MachineAxisSample(
            item.point_id, float(index),
            {"X": item.position[0], "Y": item.position[1], "Z": item.position[2],
             "A": 0.0, "C": 0.0},
        ) for index, item in enumerate(points)),
    )
    with pytest.raises(ValueError, match="motion.printed_part_collision"):
        check_operation_transition_safety(
            toolpath, trajectory, own_ac_profile(), GENERIC_NOZZLE_0_4,
        )
    safe_path = replace(
        toolpath, points=(*points[:-1], replace(points[-1], position=(0.0, 0.5, 20.0))),
    )
    safe_trajectory = replace(
        trajectory,
        samples=(
            *trajectory.samples[:-1],
            replace(
                trajectory.samples[-1],
                joint_positions={"X": 0.0, "Y": 0.5, "Z": 20.0, "A": 0.0, "C": 0.0},
            ),
        ),
    )
    assert check_operation_transition_safety(
        safe_path, safe_trajectory, own_ac_profile(), GENERIC_NOZZLE_0_4,
    )[0] > 0


def test_tip_bond_allowance_is_limited_to_shallow_final_contact() -> None:
    points = tuple(ToolpathPoint(
        f"bond-{index}", (float(index), 0.0, 0.0), (1, 0, 0), (0, 0, -1),
        "bond", "base", "layer", "region", "deposition",
        extrusion_role="skin", bead_width_mm=0.4, layer_height_mm=0.2,
        material_volume_mm3=0.1,
    ) for index in (0, 1))
    toolpath = GeneratedToolpath("bond", "bond", points=points)
    sample = ((0.5, 0.32, 0.0), 0.2, (0.0, 0.0, 1.0), 0.0, 0.0,
              "root_approach", False, 0.0, 0.2)
    assert _check_printed_part(
        toolpath, 2, (sample,), 0.2, checkpoint=None,
        bond_tip_window_mm=0.8, bond_tip_max_overlap_mm=0.1,
    ) == 1
    with pytest.raises(ValueError, match="printed_part_collision"):
        _check_printed_part(toolpath, 2, (sample,), 0.2, checkpoint=None)
    with pytest.raises(ValueError, match="printed_part_collision"):
        _check_printed_part(
            toolpath, 2, (sample[:-2] + (0.5, 0.2),), 0.2,
            checkpoint=None, bond_tip_window_mm=0.8,
            bond_tip_max_overlap_mm=0.1,
        )


def test_own_ac_long_passes_expose_cooperative_checkpoints(freeform_case) -> None:
    _model, _operation, result = freeform_case
    post_count = 0

    def post_checkpoint() -> None:
        nonlocal post_count
        post_count += 1

    gcode = postprocess_own_ac(
        result.toolpath, result.trajectory, own_ac_profile(), GENERIC_NOZZLE_0_4,
        TEST_STATION_CONTROLLER, checkpoint=post_checkpoint,
    )
    assert gcode == result.gcode
    assert post_count >= 1

    read_count = 0

    def read_checkpoint() -> None:
        nonlocal read_count
        read_count += 1

    report = readback_own_ac(
        gcode, result.toolpath, result.trajectory, own_ac_profile(),
        GENERIC_NOZZLE_0_4, TEST_STATION_CONTROLLER,
        checkpoint=read_checkpoint,
    )
    assert report.passed
    assert read_count >= 4  # entry, regenerated NC, markers and point verification

    def cancelled() -> None:
        raise RuntimeError("user cancelled")

    with pytest.raises(RuntimeError, match="user cancelled"):
        postprocess_own_ac(
            result.toolpath, result.trajectory, own_ac_profile(), GENERIC_NOZZLE_0_4,
            TEST_STATION_CONTROLLER, checkpoint=cancelled,
        )
    with pytest.raises(RuntimeError, match="user cancelled"):
        readback_own_ac(
            gcode, result.toolpath, result.trajectory, own_ac_profile(),
            GENERIC_NOZZLE_0_4, TEST_STATION_CONTROLLER, checkpoint=cancelled,
        )


def test_own_ac_does_not_insert_unplanned_reorientation_or_park(
    freeform_case,
) -> None:
    _model, _operation, result = freeform_case
    indexed_toolpath = GeneratedToolpath(
        result.toolpath.toolpath_id,
        result.toolpath.operation_id,
        result.toolpath.coordinate_frame,
        result.toolpath.points,
        (
            ToolpathEvent(
                "test-index-start",
                "index_start",
                result.toolpath.operation_id,
                "test",
                context={"sequence_index": 0},
            ),
            *result.toolpath.events,
        ),
    )
    gcode = postprocess_own_ac(
        indexed_toolpath,
        result.trajectory,
        own_ac_profile(),
        GENERIC_NOZZLE_0_4,
        TEST_STATION_CONTROLLER,
    )
    assert "G90\nG1 Z20.000000" not in gcode
    assert "G91\nG1 Z20.000000" not in gcode
    assert "; PAC SERVICE safe_depart" in gcode
    report = readback_own_ac(
        gcode,
        indexed_toolpath,
        result.trajectory,
        own_ac_profile(),
        GENERIC_NOZZLE_0_4,
        TEST_STATION_CONTROLLER,
    )
    assert report.passed
    tampered = re.sub(
        r"(; PAC SERVICE safe_depart\nG1 [^\n]*Z)([-+0-9.]+)",
        r"\g<1>1.000000",
        gcode,
        count=1,
    )
    assert tampered != gcode
    rejected = readback_own_ac(
        tampered,
        indexed_toolpath,
        result.trajectory,
        own_ac_profile(),
        GENERIC_NOZZLE_0_4,
        TEST_STATION_CONTROLLER,
    )
    assert not rejected.passed
    assert "command_stream_mismatch" in rejected.issues
