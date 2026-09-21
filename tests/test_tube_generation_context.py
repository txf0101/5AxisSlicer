"""Independent geometry/forward-kinematics and cache regressions from AUD-01."""

from dataclasses import replace
import math
from pathlib import Path
import sys

import cadquery as cq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE
from five_axis_slicer.manufacturing.resources import (
    GENERIC_PLA_175,
    NozzleProfile,
    ResourceSnapshot,
)
from five_axis_slicer.manufacturing.setup import (
    ManufacturingObjectAssignments,
    ManufacturingSetup,
    TubeProcessParameters,
)
from five_axis_slicer.postprocessing.indexed_tube import GenerationCancelled
from five_axis_slicer.postprocessing.tube_product import TubeProductState
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.tube_controller import TubeSetupController


def frame(name, origin=(0, 0, 0), x=(1, 0, 0), z=(0, 0, 1)):
    return CoordinateFrameDefinition.from_references(
        name,
        name,
        PointReference("numeric", origin, confirmed=True),
        DirectionReference("numeric", z, confirmed=True),
        DirectionReference("numeric", x, confirmed=True),
    )


@pytest.fixture(scope="module")
def source_model(tmp_path_factory):
    path = tmp_path_factory.mktemp("tube-source") / "straight.step"
    tube = cq.Workplane("XY").circle(6).circle(5).extrude(0.5).translate((50, 50, 20)).val()
    base = cq.Workplane("XY").box(14, 14, 1).translate((50, 50, 15)).val()
    cq.exporters.export(cq.Compound.makeCompound([tube, base]), str(path))
    return load_step(path)


def controller(model, *, shift=0, build=None, reviewed=True):
    machine = replace(
        GENERIC_XYZAC_REFERENCE,
        joints=tuple(
            replace(joint, soft_limit_min=-1000, soft_limit_max=1000)
            if joint.joint_type == "linear"
            else joint
            for joint in GENERIC_XYZAC_REFERENCE.joints
        ),
    )
    nozzle = NozzleProfile(
        "audit-nozzle",
        "Audit nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2,
        outer_profile_rz_mm=((0.3, 0), (0.4, 2)),
    )
    setup = ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(
            part_body_ids=("body_001",), ignored_body_ids=("body_002",)
        ),
        machine=ResourceSnapshot.capture("machine", machine),
        nozzle=ResourceSnapshot.capture("nozzle", nozzle),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("audit-pla") if reviewed else GENERIC_PLA_175
        ),
        model_coordinate_system=frame("model"),
        build_coordinate_system=build or frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250 + shift, 250, -300), source_frame="build", target_frame="build_plate_mount"
        ),
    )
    ctrl = TubeSetupController(model, setup=setup)
    ctrl.create_operation(operation_id="tube")
    ports = sorted(
        [edge for edge in model.edges if edge.radius is not None and abs(edge.radius - 6) < 1e-6],
        key=lambda edge: edge.center[2],
    )
    ctrl.configure_operation(
        operation_id="tube",
        tube_body_id="body_001",
        entry_port_id=ports[0].edge_id,
        exit_port_id=ports[-1].edge_id,
        substrate_body_id="body_002",
        parameters=TubeProcessParameters(
            bead_width_mm=1,
            layer_height_mm=0.5,
            safe_clearance_mm=2,
            contour_chord_error_mm=0.001,
            deposition_feedrate_mm_min=1,
            travel_feedrate_mm_min=1,
        ),
    )
    return ctrl


@pytest.mark.parametrize(
    "build", [frame("build", (10, 0, 0)), frame("build", (10, 0, 0), x=(0, 1, 0))]
)
def test_source_build_mount_and_independent_machine_fk(source_model, build):
    source_edge_before = source_model.edges[0].to_json()
    ctrl = controller(source_model, build=build)
    result = ctrl.generate_operation("tube")
    assert ctrl.setup_ready
    assert result.exportable, result.validation.to_json()
    assert result.thermal_parameters is not None
    assert result.thermal_parameters.nozzle_c == 200.0
    assert result.thermal_parameters.bed_c == 60.0
    assert result.gcode.startswith("; OFFLINE PRINT JOB:")
    assert "M109 S200.000000" in result.gcode
    centre = build.T_target_from_source.transform_point((50, 50, 20.25))
    axis = build.T_target_from_source.transform_vector((0, 0, 1))
    for point, sample in zip(result.toolpath.points, result.trajectory.samples, strict=True):
        delta = tuple(point.position[k] - centre[k] for k in range(3))
        assert math.dist(point.nozzle_axis, tuple(-v for v in axis)) < 1e-7
        assert abs(sum(delta[k] * axis[k] for k in range(3))) < 1e-7
        assert abs(math.sqrt(sum(v * v for v in delta)) - 5.5) < 0.001
        machine = ctrl.machine_profile()
        physical = (
            machine.mount_transform(ctrl.setup.mount_datum_id, sample.joint_positions)
            @ ctrl.setup.T_mount_from_build
        ).transform_point(point.position)
        tool = machine.link_transform(machine.tool_link_id, sample.joint_positions).translation
        actual_tip = (tool[0], tool[1], tool[2] - 2)
        assert math.dist(physical, actual_tip) < 1e-7
        physical_axis = (
            machine.mount_transform(ctrl.setup.mount_datum_id, sample.joint_positions)
            @ ctrl.setup.T_mount_from_build
        ).transform_vector(point.nozzle_axis)
        assert math.dist(physical_axis, (0, 0, -1)) < 1e-7
    assert source_model.edges[0].to_json() == source_edge_before


def test_placement_changes_axes_and_stale_export_is_blocked(source_model, tmp_path):
    first, second = controller(source_model), controller(source_model, shift=100)
    a, b = first.generate_operation("tube"), second.generate_operation("tube")
    assert a.exportable and b.exportable
    assert a.gcode != b.gcode
    first.export_operation_product("tube", tmp_path / "valid")
    first.begin_placement_draft()
    first.set_placement_adjustment((100, 0, 0))
    first.apply_placement_draft()
    assert first.product_state("tube").status == "stale"
    assert first.product_result("tube") is a
    with pytest.raises(ValueError, match="exportable"):
        first.export_operation_product("tube", tmp_path / "stale")


def test_setup_errors_and_pending_drafts_block_generation(source_model):
    with pytest.raises(ValueError, match="MATERIAL_REVIEW_REQUIRED"):
        controller(source_model, reviewed=False).generate_operation("tube")
    ctrl = controller(source_model)
    ctrl.begin_placement_draft()
    with pytest.raises(ValueError, match="Setup"):
        ctrl.generate_operation("tube")


def test_cancel_preserves_previous_result_and_legacy_reopens_stale(source_model):
    ctrl = controller(source_model)
    result = ctrl.generate_operation("tube")
    state = ctrl.product_state("tube")
    with pytest.raises(GenerationCancelled):
        ctrl.generate_operation("tube", cancelled=lambda: True)
    assert ctrl.product_result("tube") is result
    assert ctrl.product_state("tube") == state
    legacy = state.to_json()
    legacy["schema_version"] = 1
    legacy.pop("input_semantic_sha256")
    restored = TubeProductState.from_json(legacy)
    assert restored.status == "stale" and restored.result_payload is not None


def test_step_chord_limit_checks_real_segment_interiors(source_model):
    result = controller(source_model).generate_operation("tube")
    assert result.exportable
    errors = []
    for left, right in zip(result.toolpath.points, result.toolpath.points[1:]):
        if right.point_type == "deposition":
            midpoint = tuple((a + b) * 0.5 for a, b in zip(left.position, right.position))
            errors.append(abs(5.5 - math.hypot(midpoint[0] - 50, midpoint[1] - 50)))
    assert max(errors) <= 0.001
    assert result.generation_context["collision"]["check_ipw"] is True
    assert {box["id"] for box in result.generation_context["collision"]["obstacles"]} == {
        "body_002"
    }


def test_resource_and_fixture_changes_invalidate_cached_products(source_model, tmp_path):
    ctrl = controller(source_model)
    ctrl.generate_operation("tube")
    changes = {
        "nozzle": lambda c: c.select_nozzle(
            replace(
                c.setup.nozzle.as_nozzle_profile(),
                length_mm=3,
                outer_profile_rz_mm=((0.3, 0), (0.4, 3)),
            )
        ),
        "material": lambda c: c.select_material(
            replace(c.setup.material.as_material_profile(), density_g_cm3=1.3)
        ),
        "machine": lambda c: c.select_machine(
            replace(c.machine_profile(), name="Changed calibrated profile")
        ),
        "fixture": lambda c: c.confirm_assignments(
            part_body_ids=("body_001",), fixture_body_ids=("body_002",)
        ),
    }
    for name, change in changes.items():
        candidate = ctrl.fork()
        change(candidate)
        assert candidate.product_state("tube").status == "stale", name
        with pytest.raises(ValueError, match="exportable"):
            candidate.export_operation_product("tube", tmp_path / name)


def test_nonzero_rotary_centres_and_mount_offset_use_one_motion_transform(source_model):
    ctrl = controller(source_model, build=frame("build", (5, 0, 0), x=(0, 1, 0)))
    machine = ctrl.machine_profile()
    machine = replace(
        machine,
        joints=tuple(
            replace(joint, rotation_center_mm=(10, 15, 5))
            if joint.joint_id in {"A", "C"}
            else joint
            for joint in machine.joints
        ),
        mount_datums=tuple(
            replace(
                mount,
                T_parent_from_mount=RigidTransform.from_translation(
                    (3, 4, 5), source_frame=mount.mount_id, target_frame=mount.parent_link_id
                ),
            )
            for mount in machine.mount_datums
        ),
    )
    ctrl = TubeSetupController(
        source_model,
        setup=replace(ctrl.setup, machine=ResourceSnapshot.capture("machine", machine)),
        operations=ctrl.operations,
    )
    result = ctrl.generate_operation("tube")
    assert result.exportable, result.validation.to_json()
    for point, sample in zip(result.toolpath.points, result.trajectory.samples, strict=True):
        physical = (
            machine.mount_transform(ctrl.setup.mount_datum_id, sample.joint_positions)
            @ ctrl.setup.T_mount_from_build
        ).transform_point(point.position)
        tool = machine.link_transform(machine.tool_link_id, sample.joint_positions).translation
        assert math.dist(physical, (tool[0], tool[1], tool[2] - 2)) < 1e-7


def test_real_intersecting_fixture_blocks_product(tmp_path):
    path = tmp_path / "intersecting-fixture.step"
    tube = cq.Workplane("XY").circle(6).circle(5).extrude(0.5).translate((50, 50, 20)).val()
    fixture = cq.Workplane("XY").box(20, 20, 10).translate((50, 50, 20)).val()
    cq.exporters.export(cq.Compound.makeCompound([tube, fixture]), str(path))
    ctrl = controller(load_step(path))
    ctrl.confirm_assignments(part_body_ids=("body_001",), fixture_body_ids=("body_002",))
    result = ctrl.generate_operation("tube")
    assert ctrl.setup_ready
    assert not result.exportable
    assert "tube.nozzle_obstacle_collision" in {issue.code for issue in result.validation.issues}
    with pytest.raises(ValueError, match="exportable"):
        ctrl.export_operation_product("tube", tmp_path / "blocked")


def test_changed_source_is_stale_and_cannot_generate_old_geometry(source_model, tmp_path):
    path = tmp_path / "source.step"
    path.write_bytes(source_model.source_path.read_bytes())
    ctrl = controller(replace(source_model, source_path=path))
    result = ctrl.generate_operation("tube")
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="exportable"):
        ctrl.export_operation_product("tube", tmp_path / "blocked")
    assert ctrl.product_state("tube").status == "stale"
    with pytest.raises(ValueError, match="source changed"):
        ctrl.generate_operation("tube")
    assert ctrl.product_result("tube") is result


def test_edit_during_generation_never_publishes_obsolete_result(source_model):
    ctrl = controller(source_model)
    previous = ctrl.generate_operation("tube")
    calls = 0

    def edit_once():
        nonlocal calls
        calls += 1
        if calls == 3:
            ctrl.select_nozzle(
                replace(
                    ctrl.setup.nozzle.as_nozzle_profile(),
                    length_mm=3,
                    outer_profile_rz_mm=((0.3, 0), (0.4, 3)),
                )
            )
        return False

    with pytest.raises(ValueError, match="inputs changed"):
        ctrl.generate_operation("tube", cancelled=edit_once)
    assert ctrl.product_result("tube") is previous
    assert ctrl.product_state("tube").status == "error"


def test_partial_tail_product_readback_and_old_context_stale(source_model, monkeypatch, tmp_path):
    import five_axis_slicer.tube_generation_context as context_module

    ctrl = controller(source_model)
    current_version = context_module.CONTEXT_VERSION
    with monkeypatch.context() as old:
        old.setattr(context_module, "CONTEXT_VERSION", "tube-build-context-v2")
        ctrl.generate_operation("tube")
    assert context_module.CONTEXT_VERSION == current_version
    with pytest.raises(ValueError, match="exportable"):
        ctrl.export_operation_product("tube", tmp_path / "old-context")
    assert ctrl.product_state("tube").status == "stale"
    operation = ctrl.operations[0]
    ctrl.configure_operation(
        operation_id="tube",
        tube_body_id=operation.geometry.tube_body.object_id,
        entry_port_id=operation.geometry.entry_port.object_id,
        exit_port_id=operation.geometry.exit_port.object_id,
        substrate_body_id=operation.geometry.substrate_body.object_id,
        parameters=replace(operation.parameters, layer_height_mm=1.0),
    )
    result = ctrl.generate_operation("tube")
    assert result.exportable and result.readback.passed
    assert result.manifest.algorithm_version == "tube-indexed-product-v3"
    deposition = [p for p in result.toolpath.points if p.point_type == "deposition"]
    assert {p.layer_height_mm for p in deposition} == {0.5}
    assert sum(p.material_volume_mm3 for p in deposition) == pytest.approx(
        math.pi * (6**2 - 5**2) * 0.5, rel=0.0001
    )
    ctrl.export_operation_product("tube", tmp_path / "current")
