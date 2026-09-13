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
from five_axis_slicer.postprocessing.freeform_product import (
    FreeformProductState,
    export_freeform_product,
    generate_freeform_product,
    state_from_freeform_result,
)
from five_axis_slicer.postprocessing.own_ac import postprocess_own_ac, readback_own_ac
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
        OWN_AC_OFFLINE_CONTROLLER,
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
        "guide-01-pass-01": [
            "retract",
            "cut",
            "park",
            "switch",
            "load",
            "temperature_wait",
            "purge",
            "prime",
            "resume",
        ],
        "guide-01-pass-02": [
            "retract",
            "cut",
            "park",
            "switch",
            "load",
            "temperature_wait",
            "purge",
            "prime",
            "resume",
        ],
    }


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
        OWN_AC_OFFLINE_CONTROLLER,
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
        OWN_AC_OFFLINE_CONTROLLER,
    )
    assert not report.passed and any(issue.endswith(":E") for issue in report.issues)


def test_own_ac_distinguishes_absolute_reorientation_from_relative_material_park(
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
        OWN_AC_OFFLINE_CONTROLLER,
    )
    assert "G90\nG1 Z20.000000" in gcode
    assert "G91\nG1 Z20.000000" in gcode
    report = readback_own_ac(
        gcode,
        indexed_toolpath,
        result.trajectory,
        own_ac_profile(),
        GENERIC_NOZZLE_0_4,
        OWN_AC_OFFLINE_CONTROLLER,
    )
    assert report.passed
    tampered = gcode.replace("G91\nG1 Z20.000000", "G90\nG1 Z20.000000", 1)
    rejected = readback_own_ac(
        tampered,
        indexed_toolpath,
        result.trajectory,
        own_ac_profile(),
        GENERIC_NOZZLE_0_4,
        OWN_AC_OFFLINE_CONTROLLER,
    )
    assert not rejected.passed
    assert "command_stream_mismatch" in rejected.issues
