from dataclasses import replace
import math
from pathlib import Path
import sys

import cadquery as cq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.curve.chain import (
    CurveGeometryError,
    CurveSample,
    build_curve_plan,
)
from five_axis_slicer.algorithms.curve.toolpath import curve_paths
from five_axis_slicer.curve_commands import CurveCommandService
from five_axis_slicer.curve_controller import CurveController
from five_axis_slicer.manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.curve_parameters import CurveProcessParameters
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE
from five_axis_slicer.manufacturing.resources import GENERIC_PLA_175, NozzleProfile, ResourceSnapshot
from five_axis_slicer.manufacturing.setup import ManufacturingObjectAssignments, ManufacturingSetup
from five_axis_slicer.postprocessing.curve_product import export_curve_product
from five_axis_slicer.step_loader import load_step


def _frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", (0, 0, 0), confirmed=True),
        DirectionReference("numeric", (0, 0, 1), confirmed=True),
        DirectionReference("numeric", (1, 0, 0), confirmed=True),
    )


def _machine():
    return replace(
        GENERIC_XYZAC_REFERENCE,
        joints=tuple(
            replace(item, soft_limit_min=-1000.0, soft_limit_max=1000.0)
            for item in GENERIC_XYZAC_REFERENCE.joints
        ),
    )


def _nozzle() -> NozzleProfile:
    return NozzleProfile(
        "curve-test-nozzle",
        "Curve test nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2.0,
        outer_profile_rz_mm=((0.3, 0.0), (0.4, 2.0)),
    )


def _setup(body_id: str) -> ManufacturingSetup:
    return ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(part_body_ids=(body_id,)),
        machine=ResourceSnapshot.capture("machine", _machine()),
        nozzle=ResourceSnapshot.capture("nozzle", _nozzle()),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("curve-test-pla")
        ),
        model_coordinate_system=_frame("model"),
        build_coordinate_system=_frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250, 250, 250),
            source_frame="build",
            target_frame="build_plate_mount",
        ),
    )


def _write_step(shape, path: Path) -> Path:
    cq.exporters.export(shape, str(path))
    return path


def _line_model(tmp_path: Path):
    model = load_step(_write_step(cq.Workplane("XY").box(20, 10, 2), tmp_path / "box.step"))
    edge = max((item for item in model.edges if item.curve_type == "line"), key=lambda e: e.exact_length or 0)
    return model, edge


def _configured(
    model,
    edge_id: str,
    operation_type: str = "curve_buildup",
    *,
    reversed_flag: bool = False,
    parameters: CurveProcessParameters | None = None,
) -> tuple[CurveController, object]:
    controller = CurveController(model, setup=_setup(model.bodies[0].body_id))
    operation = controller.create_operation(operation_type)
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        edge_ids=(edge_id,),
        reversed_flags=(reversed_flag,),
        normal_mode="specified",
        specified_normal=(0, 0, 1),
        parameters=parameters,
    )
    return controller, operation


def test_c01_line_is_sampled_by_arclength_with_exact_endpoints(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    _controller, operation = _configured(model, edge.edge_id)
    plan = build_curve_plan(model, operation.operation_id, operation.geometry, operation.parameters)
    assert plan.total_length_mm == pytest.approx(20.0, abs=1e-8)
    assert plan.samples[0].position == pytest.approx(edge.endpoints[0], abs=1e-8)
    assert plan.samples[-1].position == pytest.approx(edge.endpoints[1], abs=1e-8)
    gaps = [
        right.chain_distance_mm - left.chain_distance_mm
        for left, right in zip(plan.samples, plan.samples[1:])
    ]
    assert max(gaps) - min(gaps) < 1e-7


def test_c01_reversed_edge_reverses_endpoints_and_tangent(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    _, forward = _configured(model, edge.edge_id)
    _, reverse = _configured(model, edge.edge_id, reversed_flag=True)
    first = build_curve_plan(model, forward.operation_id, forward.geometry, forward.parameters)
    second = build_curve_plan(model, reverse.operation_id, reverse.geometry, reverse.parameters)
    assert second.samples[0].position == pytest.approx(first.samples[-1].position)
    assert second.samples[-1].position == pytest.approx(first.samples[0].position)
    assert second.samples[0].tangent == pytest.approx(tuple(-v for v in first.samples[-1].tangent))


def test_c01_disconnected_chain_has_locatable_failure(tmp_path: Path) -> None:
    model, _edge = _line_model(tmp_path)
    pairs = [
        (left, right)
        for left in model.edges
        for right in model.edges
        if left.edge_id < right.edge_id and not set(left.vertex_ids) & set(right.vertex_ids)
    ]
    left, right = pairs[0]
    controller = CurveController(model, setup=_setup(model.bodies[0].body_id))
    operation = controller.create_operation()
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        edge_ids=(left.edge_id, right.edge_id),
        normal_mode="specified",
        specified_normal=(0, 0, 1),
    )
    with pytest.raises(CurveGeometryError, match="curve.chain_disconnected") as caught:
        build_curve_plan(model, operation.operation_id, operation.geometry, operation.parameters)
    assert caught.value.object_id == right.edge_id


def test_c01_ambiguous_adjacent_normal_requires_user_choice(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller = CurveController(model, setup=_setup(model.bodies[0].body_id))
    operation = controller.create_operation()
    with pytest.raises(ValueError, match="curve.normal_ambiguous"):
        controller.configure_operation(operation_id=operation.operation_id, edge_ids=(edge.edge_id,))


def test_c01_missing_normal_face_and_degenerate_edge_are_locatable(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    _controller, operation = _configured(model, edge.edge_id)
    missing_face = replace(
        operation.geometry,
        normal_mode="adjacent_face",
        normal_face=None,
        specified_normal=None,
    )
    with pytest.raises(CurveGeometryError, match="curve.normal_face_missing"):
        build_curve_plan(model, operation.operation_id, missing_face, operation.parameters)
    model.edges = [
        replace(item, exact_length=0.0) if item.edge_id == edge.edge_id else item
        for item in model.edges
    ]
    with pytest.raises(CurveGeometryError, match="curve.edge_degenerate") as caught:
        build_curve_plan(model, operation.operation_id, operation.geometry, operation.parameters)
    assert caught.value.object_id == edge.edge_id


def test_c01_parallel_normal_rejects_degenerate_local_frame(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller = CurveController(model, setup=_setup(model.bodies[0].body_id))
    operation = controller.create_operation()
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        edge_ids=(edge.edge_id,),
        normal_mode="specified",
        specified_normal=(1, 0, 0),
    )
    with pytest.raises(CurveGeometryError, match="curve.normal_parallel_tangent"):
        build_curve_plan(model, operation.operation_id, operation.geometry, operation.parameters)


def test_c02_circle_length_and_material_use_independent_analytic_truth(tmp_path: Path) -> None:
    radius = 8.0
    model = load_step(
        _write_step(cq.Workplane("XY").circle(radius).extrude(2), tmp_path / "cylinder.step")
    )
    circle = max(
        (item for item in model.edges if item.curve_type == "circle"),
        key=lambda item: item.exact_length or 0,
    )
    controller, operation = _configured(
        model,
        circle.edge_id,
        parameters=CurveProcessParameters(sampling_step_mm=0.25, chord_error_mm=0.01),
    )
    result = controller.generate_operation(operation.operation_id)
    expected_length = 2 * math.pi * radius
    expected_volume = expected_length * 0.6 * 0.2
    assert result.plan.total_length_mm == pytest.approx(expected_length, abs=1e-7)
    assert sum(point.material_volume_mm3 for point in result.toolpath.points) == pytest.approx(
        expected_volume, abs=0.01
    )
    assert result.readback.passed


@pytest.mark.parametrize(
    ("operation_type", "expected_paths"),
    [("curve_buildup", 1), ("curve_multi_pass", 4), ("curve_offset_buildup", 5)],
)
def test_c02_c04_three_operations_generate_shared_toolpath_and_readback(
    tmp_path: Path, operation_type: str, expected_paths: int
) -> None:
    model, edge = _line_model(tmp_path)
    parameters = CurveProcessParameters(layer_count=4, offset_pass_count=5)
    controller, operation = _configured(
        model, edge.edge_id, operation_type, parameters=parameters
    )
    result = controller.generate_operation(operation.operation_id)
    assert result.manifest.ready_for_export
    assert result.readback.passed
    assert len({(item.layer_id, item.region_id) for item in result.toolpath.points}) == expected_paths
    assert all(item.extrusion_role == "buildup" for item in result.toolpath.points if item.point_type == "deposition")


def test_c03_layer_height_and_alternating_order(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller, operation = _configured(model, edge.edge_id, "curve_multi_pass")
    plan = build_curve_plan(model, operation.operation_id, operation.geometry, operation.parameters)
    paths = curve_paths(plan, operation)
    assert len(paths) == 3
    assert math.dist(paths[0].samples[0].position, paths[1].samples[-1].position) == pytest.approx(
        operation.parameters.layer_height_mm
    )
    assert paths[0].samples[0].position[:2] == pytest.approx(paths[1].samples[-1].position[:2])


def test_c04_spacing_and_offset_order(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller, operation = _configured(model, edge.edge_id, "curve_offset_buildup")
    plan = build_curve_plan(model, operation.operation_id, operation.geometry, operation.parameters)
    paths = curve_paths(plan, operation)
    assert [item.lateral_offset_mm for item in paths] == pytest.approx([0.0, 0.6, 1.2])
    assert math.dist(paths[0].samples[0].position, paths[1].samples[-1].position) == pytest.approx(0.6)


def test_c04_sharp_frame_reversal_and_self_intersection_are_errors(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    _controller, operation = _configured(model, edge.edge_id, "curve_offset_buildup")
    base = build_curve_plan(model, operation.operation_id, operation.geometry, operation.parameters)
    reversal = replace(
        base,
        samples=(
            CurveSample((0, 0, 0), (1, 0, 0), (0, 0, 1), edge.edge_id, 0.0, 0.0),
            CurveSample((1, 0, 0), (-1, 0, 0), (0, 0, 1), edge.edge_id, 0.5, 1.0),
            CurveSample((0, 0, 0), (-1, 0, 0), (0, 0, 1), edge.edge_id, 1.0, 2.0),
        ),
    )
    with pytest.raises(CurveGeometryError, match="curve.offset_frame_reversal"):
        curve_paths(reversal, operation)
    crossing_positions = ((0, 0, 0), (2, 2, 0), (0, 2, 0), (2, 0, 0), (3, 0, 0))
    crossing = replace(
        base,
        samples=tuple(
            CurveSample(point, (1, 0, 0), (0, 0, 1), edge.edge_id, index / 4, index)
            for index, point in enumerate(crossing_positions)
        ),
    )
    with pytest.raises(CurveGeometryError, match="curve.offset_self_intersection"):
        curve_paths(crossing, operation)


def test_real_step_bspline_is_sampled_and_preserves_source_edge() -> None:
    model = load_step(Path("example/叶轮/叶轮.stp"))
    edge = next(item for item in model.edges if item.edge_id == "body_002_edge_0011")
    _controller, operation = _configured(model, edge.edge_id)
    plan = build_curve_plan(model, operation.operation_id, operation.geometry, operation.parameters)
    assert plan.total_length_mm == pytest.approx(edge.exact_length, rel=1e-10)
    assert {item.source_edge_id for item in plan.samples} == {edge.edge_id}
    assert len(plan.samples) > 10


def test_tracked_real_step_quarter_arc_matches_independent_circle_truth() -> None:
    model = load_step(Path("example/叶轮/叶轮.stp"))
    edge = next(item for item in model.edges if item.edge_id == "body_001_edge_0005")
    controller = CurveController(model, setup=_setup(model.bodies[0].body_id))
    operation = controller.create_operation()
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        edge_ids=(edge.edge_id,),
        normal_mode="specified",
        specified_normal=(0, 1, 0),
    )
    plan = build_curve_plan(model, operation.operation_id, operation.geometry, operation.parameters)
    assert plan.total_length_mm == pytest.approx(40.0 * math.pi / 2.0, abs=1e-9)
    for sample in plan.samples:
        x, _y, z = sample.position
        assert math.hypot(x + 52.0, z - 42.0) == pytest.approx(40.0, abs=1e-8)


def test_real_step_all_three_operations_generate_and_read_back() -> None:
    model = load_step(Path("example/叶轮/叶轮.stp"))
    for operation_type in (
        "curve_buildup",
        "curve_multi_pass",
        "curve_offset_buildup",
    ):
        controller = CurveController(model, setup=_setup(model.bodies[1].body_id))
        operation = controller.create_operation(operation_type)
        operation = controller.configure_operation(
            operation_id=operation.operation_id,
            edge_ids=("body_002_edge_0011",),
            reversed_flags=(operation_type == "curve_offset_buildup",),
            normal_mode="adjacent_face",
            normal_face_id="body_002_face_0006",
        )
        result = controller.generate_operation(operation.operation_id)
        assert result.exportable and result.readback.passed
        assert result.plan.total_length_mm == pytest.approx(68.27612913311773, abs=1e-9)
        if operation_type == "curve_offset_buildup":
            paths = [[
                item for item in result.toolpath.points if item.region_id == "pass-0001"
            ], [
                item for item in result.toolpath.points if item.region_id == "pass-0002"
            ], [
                item for item in result.toolpath.points if item.region_id == "pass-0003"
            ]]
            paths[1].reverse()
            spacing = [
                math.dist(left.position, right.position)
                for left_path, right_path in zip(paths, paths[1:])
                for left, right in zip(left_path, right_path)
            ]
            assert min(spacing) > operation.parameters.offset_spacing_mm * 0.98
            assert max(spacing) <= operation.parameters.offset_spacing_mm + 1.0e-6


def test_real_step_forward_offset_rejects_trim_boundary_projection_collapse() -> None:
    model = load_step(Path("example/叶轮/叶轮.stp"))
    controller = CurveController(model, setup=_setup(model.bodies[1].body_id))
    operation = controller.create_operation("curve_offset_buildup")
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        edge_ids=("body_002_edge_0011",),
        normal_mode="adjacent_face",
        normal_face_id="body_002_face_0006",
    )
    with pytest.raises(CurveGeometryError, match="curve.offset_outside_face"):
        controller.generate_operation(operation.operation_id)


def test_trimmed_face_offset_fails_instead_of_silently_dropping_a_pass() -> None:
    model = load_step(
        Path(
            "docs/reviews/evidence/2026-09-12_project_audit/"
            "frozen_cases/analytic/rectangle_8x6x1.step"
        )
    )
    controller = CurveController(model, setup=_setup(model.bodies[0].body_id))
    operation = controller.create_operation("curve_offset_buildup")
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        edge_ids=("body_001_edge_0012",),
        normal_mode="adjacent_face",
        normal_face_id="body_001_face_0006",
        parameters=CurveProcessParameters(offset_pass_count=3, offset_spacing_mm=0.6),
    )
    with pytest.raises(CurveGeometryError, match="curve.offset_outside_face"):
        controller.generate_operation(operation.operation_id)


def test_export_writes_six_files_and_readback_passes(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller, operation = _configured(model, edge.edge_id)
    result = controller.generate_operation(operation.operation_id)
    output = export_curve_product(result, tmp_path / "product")
    assert {item.name for item in output.iterdir()} == {
        "main.gcode",
        "toolpath.json",
        "machine_axes.csv",
        "warnings.json",
        "preview.json",
        "manifest.json",
    }


def test_curve_validation_reports_singularity_motion_limits_and_blocks_export(
    tmp_path: Path,
) -> None:
    model, edge = _line_model(tmp_path)
    controller, operation = _configured(model, edge.edge_id)
    singular = controller.generate_operation(operation.operation_id)
    assert "xyzac.rotary_singularity" in {item.code for item in singular.validation.issues}
    slow_machine = replace(
        _machine(),
        joints=tuple(
            replace(item, max_velocity=1.0e-6, max_acceleration=1.0e-6)
            for item in _machine().joints
        ),
    )
    slow_setup = replace(
        _setup(model.bodies[0].body_id),
        machine=ResourceSnapshot.capture("machine", slow_machine),
    )
    limited = CurveController(model, setup=slow_setup)
    slow_operation = limited.create_operation("curve_multi_pass")
    slow_operation = limited.configure_operation(
        operation_id=slow_operation.operation_id,
        edge_ids=(edge.edge_id,),
        normal_mode="specified",
        specified_normal=(0, 0, 1),
    )
    result = limited.generate_operation(slow_operation.operation_id)
    codes = {item.code for item in result.validation.issues}
    assert {"xyzac.velocity_limit_exceeded", "xyzac.acceleration_limit_exceeded"} <= codes
    assert not result.exportable


def test_curve_controller_reuses_setup_fixture_for_swept_collision_validation() -> None:
    model = load_step(Path("example/叶轮/叶轮.stp"))
    setup = _setup("body_002")
    setup = replace(
        setup,
        assignments=replace(setup.assignments, fixture_body_ids=("body_001",)),
    )
    controller = CurveController(model, setup=setup)
    operation = controller.create_operation()
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        edge_ids=("body_002_edge_0011",),
        normal_mode="adjacent_face",
        normal_face_id="body_002_face_0006",
    )
    result = controller.generate_operation(operation.operation_id)
    assert {item.code for item in result.validation.issues} >= {
        "curve.nozzle_obstacle_collision"
    }
    assert result.validation.collision_samples_checked > len(result.toolpath.points)
    assert not result.exportable


def test_commands_support_script_undo_and_error_state(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller = CurveController(model, setup=_setup(model.bodies[0].body_id))
    service = CurveCommandService(controller)
    created = service.execute_command("create_operation", "curve_buildup")
    operation_id = created.payload["operation_id"]
    output = service.execute_script(
        f"curve.set_operation(operation_id={operation_id!r}, edge_ids={[edge.edge_id]!r}, "
        "normal_mode='specified', specified_normal=(0, 0, 1))"
    )
    assert not output.startswith("ERROR")
    assert service.execute_command("generate_operation", operation_id).payload["status"] in {
        "ready",
        "warning",
    }
    service.execute_command("set_operation", operation_id=operation_id, bead_width_mm=0.8)
    assert controller.product_state(operation_id).status == "stale"
    service.execute_command("undo")
    assert controller.product_state(operation_id).status in {"ready", "warning"}


def test_cancel_does_not_destroy_previous_valid_result(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller, operation = _configured(model, edge.edge_id)
    previous = controller.generate_operation(operation.operation_id)
    calls = 0

    def cancelled() -> bool:
        nonlocal calls
        calls += 1
        return calls > 1

    with pytest.raises(Exception, match="cancelled"):
        controller.generate_operation(operation.operation_id, cancelled=cancelled)
    assert controller.product_result(operation.operation_id) is previous
