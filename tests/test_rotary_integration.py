from __future__ import annotations

import copy
from dataclasses import replace
import math
import os
from pathlib import Path
import sys

import cadquery as cq
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt5.QtWidgets import QApplication

from five_axis_slicer.algorithms.rotary import build_rotary_plan
from five_axis_slicer.automation_routes import AutomationRouter
from five_axis_slicer.manufacturing.coordinates import RigidTransform
from five_axis_slicer.manufacturing.rotary_parameters import (
    RotaryAngularRegion,
    RotaryGeometrySelection,
    RotaryProcessParameters,
)
from five_axis_slicer.models import SelectionState
from five_axis_slicer.postprocessing.rotary_product import (
    export_rotary_product,
    generate_rotary_product,
)
from five_axis_slicer.project_io import load_project, save_project
from five_axis_slicer.restricted_script import parse_script
from five_axis_slicer.rotary_commands import RotaryCommandService
from five_axis_slicer.rotary_controller import RotaryController
from five_axis_slicer.rotary_generation_context import rotary_workpiece_from_build
from five_axis_slicer.rotary_operation_service import (
    bind_rotary_geometry_references,
    rebind_rotary_operation_geometry,
)
from five_axis_slicer.rotary_ui import RotaryPage
from five_axis_slicer.step_loader import load_step
from test_curve_workbench import _setup
from test_tube_ui import TubeViewerStub

APP = QApplication.instance() or QApplication([])


def _rotary_model(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "rotary-cylinder.step"
    cq.exporters.export(cq.Workplane("XY").circle(20).extrude(20), str(path))
    model = load_step(path)
    surface = next(face for face in model.faces if face.surface_type == "cylinder")
    axis_edge = next(edge for edge in model.edges if edge.curve_type == "line")
    return model, axis_edge, surface


def _controller(tmp_path: Path, operation_type: str):
    model, axis_edge, surface = _rotary_model(tmp_path)
    controller = RotaryController(model, setup=_setup(model.bodies[0].body_id))
    operation = controller.create_operation(operation_type)
    geometry = bind_rotary_geometry_references(
        model,
        operation.geometry,
        axis_edge_id=axis_edge.edge_id,
        surface_face_ids=(surface.face_id,),
    )
    if operation_type == "rotary_around_part":
        geometry = replace(
            geometry,
            profile=replace(geometry.profile, axial_start_mm=0, axial_end_mm=1.6),
            angular_regions=(
                RotaryAngularRegion("A", math.radians(350), math.radians(20)),
                RotaryAngularRegion("B", math.radians(120), math.radians(210)),
            ),
        )
        parameters = RotaryProcessParameters(
            axial_step_mm=0.8,
            sampling_angle_rad=math.radians(5),
            angular_velocity_rad_s=0.1,
            feedrate_mm_min=120,
            travel_feedrate_mm_min=120,
        )
    elif operation_type == "rotary_thin_wall":
        geometry = replace(
            geometry,
            profile=replace(geometry.profile, axial_start_mm=0, axial_end_mm=1.6),
        )
        parameters = RotaryProcessParameters(
            axial_step_mm=0.8,
            radial_pass_count=2,
            wall_thickness_mm=1.2,
            sampling_angle_rad=math.radians(5),
            angular_velocity_rad_s=0.1,
            feedrate_mm_min=120,
            travel_feedrate_mm_min=120,
        )
    else:
        geometry = replace(
            geometry,
            profile=replace(geometry.profile, axial_start_mm=0, axial_end_mm=5),
        )
        parameters = RotaryProcessParameters(
            pitch_mm=5,
            sampling_angle_rad=math.radians(5),
            feedrate_mm_min=600,
            travel_feedrate_mm_min=600,
        )
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        geometry=geometry,
        parameters=parameters,
    )
    return controller, operation, model, axis_edge, surface


@pytest.mark.parametrize(
    "operation_type", ["rotary_spiral", "rotary_thin_wall", "rotary_around_part"]
)
def test_r05_three_operations_generate_readback_and_export_six_pack(
    tmp_path: Path, operation_type: str
) -> None:
    controller, operation, _model, _axis, _surface = _controller(tmp_path, operation_type)
    result = controller.generate_operation(operation.operation_id)
    assert result.exportable
    assert result.readback.passed
    assert result.manifest.status.value in {"ready", "warning"}
    assert len(result.toolpath.points) == len(result.trajectory.samples)
    assert all(
        sample.source_point_id == point.point_id
        for point, sample in zip(result.toolpath.points, result.trajectory.samples, strict=True)
    )
    phases = [
        result.plan.angle_by_point_id[sample.source_point_id]
        for sample in result.trajectory.samples
    ]
    c_values = [sample.joint_positions["C"] for sample in result.trajectory.samples]
    reference_index = next(
        index
        for index, (left_phase, right_phase) in enumerate(
            zip(phases, phases[1:])
        )
        if abs(right_phase - left_phase) > 1.0e-10
    )
    phase_sign = (
        1.0
        if (c_values[reference_index + 1] - c_values[reference_index])
        * (phases[reference_index + 1] - phases[reference_index])
        > 0.0
        else -1.0
    )
    phase_reference = phases[reference_index]
    c_reference = c_values[reference_index]
    assert c_values == pytest.approx(
        [
            c_reference + phase_sign * (phase - phase_reference)
            for phase in phases
        ],
        abs=1.0e-8,
    )
    for left, right, left_phase, right_phase in zip(
        result.trajectory.samples,
        result.trajectory.samples[1:],
        phases,
        phases[1:],
    ):
        angular_duration = (
            abs(right_phase - left_phase)
            / operation.parameters.angular_velocity_rad_s
        )
        assert right.time_s - left.time_s >= angular_duration - 1.0e-9
    target = export_rotary_product(result, tmp_path / f"product-{operation_type}")
    assert {item.name for item in target.iterdir()} == {
        "main.gcode",
        "toolpath.json",
        "machine_axes.csv",
        "warnings.json",
        "preview.json",
        "manifest.json",
    }
    assert f"5AxisSclicer R0{2 + ['rotary_spiral', 'rotary_thin_wall', 'rotary_around_part'].index(operation_type)}" in result.gcode


def test_rotary_product_stale_undo_cancel_and_reopen_contract(tmp_path: Path) -> None:
    controller, operation, model, _axis, _surface = _controller(tmp_path, "rotary_spiral")
    first = controller.generate_operation(operation.operation_id)
    assert controller.product_state(operation.operation_id).status in {"ready", "warning"}
    service = RotaryCommandService(controller)
    changed = service.execute_command(
        "set_operation", operation.operation_id, bead_width_mm=0.7
    )
    assert changed.changed
    assert controller.product_state(operation.operation_id).status == "stale"
    service.execute_command("undo")
    assert controller.product_result(operation.operation_id) is first
    assert controller.product_state(operation.operation_id).status in {"ready", "warning"}

    controller.cancel_generation()
    with pytest.raises(Exception, match="cancelled"):
        controller.generate_operation(operation.operation_id, cancelled=lambda: True)
    assert controller.product_result(operation.operation_id) is first

    reopened = RotaryController.from_json(controller.to_json(), cad_model=model)
    assert reopened.product_result(operation.operation_id) is None
    assert reopened.product_state(operation.operation_id).status == "stale"


def test_rotary_project_roundtrip_preserves_stable_references(tmp_path: Path) -> None:
    controller, operation, model, axis, surface = _controller(tmp_path, "rotary_around_part")
    project_json = save_project(
        tmp_path / "rotary-project",
        model,
        SelectionState(edge_ids={axis.edge_id}, face_ids={surface.face_id}),
        {"workbench": "rotary", "operation": operation.operation_type},
        setup=controller.setup,
        operations=(operation,),
        original_source_path=model.source_path,
    )
    loaded = load_project(project_json)
    restored = loaded.operations[0]
    assert restored == operation
    assert restored.geometry.frame.axis_reference.signature
    assert restored.geometry.profile.surface_references[0].signature


class _Page:
    def __init__(self, controller):
        self.controller = controller

    def state_json(self):
        return self.controller.state_json()


class _Window:
    def __init__(self, controller):
        self.rotary_page = _Page(controller)
        self.rotary_command_service = RotaryCommandService(controller)


def test_rotary_script_and_http_use_same_command_kernel(tmp_path: Path) -> None:
    controller, operation, _model, _axis, _surface = _controller(tmp_path, "rotary_spiral")
    assert parse_script("rotary.state()\n回转.状态()\n")[1].calls[0].namespace == "rotary"
    assert "operation_type" in RotaryCommandService(controller).execute_script("回转.状态()")
    router = AutomationRouter(_Window(controller))
    generated = router.dispatch(
        "/rotary/operation/generate", {"operation_id": operation.operation_id}
    )
    assert generated["command"]["payload"]["status"] in {"ready", "warning"}
    updated = router.dispatch(
        "/rotary/operation/set",
        {"operation_id": operation.operation_id, "bead_width_mm": 0.7},
    )
    assert updated["rotary"]["products"][0]["status"] == "stale"


def test_rotary_qt_page_binds_selected_edge_and_face_and_generates(tmp_path: Path) -> None:
    controller, _operation, _model, axis, surface = _controller(tmp_path, "rotary_spiral")
    page = RotaryPage(controller=controller, viewer_factory=TubeViewerStub)
    page.set_language("en")
    page.viewer.set_selection(edge_ids=[axis.edge_id], face_ids=[surface.face_id])
    page._use_selected_axis()
    page._use_selected_surfaces()
    page.apply_button.click()
    assert controller.operation().geometry.is_complete
    assert page.generate_button.isEnabled()
    page.generate_button.click()
    assert controller.product_result(controller.operation().operation_id).readback.passed
    assert page.export_button.isEnabled()
    assert page.current_machine_trajectory() is not None


def test_preview_only_region_and_missing_reference_block_generation(tmp_path: Path) -> None:
    controller, operation, _model, _axis, _surface = _controller(tmp_path, "rotary_spiral")
    controller.configure_operation(
        operation_id=operation.operation_id,
        geometry=replace(operation.geometry, preview_only=True),
    )
    with pytest.raises(ValueError, match="preview-only"):
        controller.generate_operation(operation.operation_id)
    controller.configure_operation(
        operation_id=operation.operation_id,
        geometry=RotaryGeometrySelection(),
    )
    with pytest.raises(ValueError, match="complete axis"):
        controller.generate_operation(operation.operation_id)


def test_r01_real_rotated_cylinder_binds_exact_axis_profile_and_build_frame(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rotated-cylinder.step"
    cq.exporters.export(cq.Workplane("YZ").circle(10).extrude(30), str(path))
    model = load_step(path)
    surface = next(face for face in model.faces if face.surface_type == "cylinder")
    axis = next(
        edge
        for edge in model.edges
        if edge.curve_type == "line"
        and edge.axis_direction is not None
        and abs(edge.axis_direction[0]) > 0.999
    )
    controller = RotaryController(model, setup=_setup(model.bodies[0].body_id))
    operation = controller.create_operation("rotary_spiral")
    geometry = bind_rotary_geometry_references(
        model,
        operation.geometry,
        axis_edge_id=axis.edge_id,
        surface_face_ids=(surface.face_id,),
    )
    assert geometry.frame.axis_direction == pytest.approx((1, 0, 0))
    assert geometry.profile.axial_start_mm == pytest.approx(0.0, abs=1.0e-7)
    assert geometry.profile.axial_end_mm == pytest.approx(30.0, abs=1.0e-7)
    assert geometry.profile.radius_start_mm == pytest.approx(10.0)
    assert geometry.profile.radius_end_mm == pytest.approx(10.0)
    transform = RigidTransform.from_rotation_translation(
        ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
        (3, -4, 5),
        source_frame="source",
        target_frame="build",
    )
    plan = build_rotary_plan(
        replace(operation, geometry=geometry),
        T_build_from_source=transform,
    )
    assert plan.region_analysis.axis_direction == pytest.approx((0, 0, 1))
    assert plan.region_analysis.axis_origin_mm == pytest.approx((3, -4, 5))
    aligned_operation = replace(
        operation,
        geometry=geometry,
        parameters=replace(operation.parameters, travel_feedrate_mm_min=600),
    )
    result = generate_rotary_product(
        model,
        aligned_operation,
        controller.machine_profile(),
        controller.nozzle_profile(),
        T_build_from_source=transform,
        T_workpiece_from_build=rotary_workpiece_from_build(
            controller.setup, controller.machine_profile()
        ),
        check_ipw=True,
    )
    assert result.exportable
    assert result.readback.passed
    with pytest.raises(ValueError, match="rotary.axis_not_aligned_with_machine_c"):
        generate_rotary_product(
            model,
            aligned_operation,
            controller.machine_profile(),
            controller.nozzle_profile(),
            T_build_from_source=RigidTransform.from_rotation_translation(
                ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                source_frame="source",
                target_frame="build",
            ),
            T_workpiece_from_build=rotary_workpiece_from_build(
                controller.setup, controller.machine_profile()
            ),
        )


def test_r02_real_cone_face_drives_linear_profile_and_product(tmp_path: Path) -> None:
    cone = (
        cq.Workplane("XY")
        .circle(15)
        .workplane(offset=12)
        .circle(9)
        .loft(combine=True)
    )
    stem = cq.Workplane("XY", origin=(0, 0, -5)).circle(2).extrude(5)
    path = tmp_path / "cone-with-axis-edge.step"
    cq.exporters.export(cone.union(stem), str(path))
    model = load_step(path)
    surface = next(face for face in model.faces if face.surface_type == "cone")
    axis = next(
        edge
        for edge in model.edges
        if edge.curve_type == "line"
        and edge.axis_direction is not None
        and abs(edge.axis_direction[2]) > 0.999
    )
    controller = RotaryController(model, setup=_setup(model.bodies[0].body_id))
    operation = controller.create_operation("rotary_spiral")
    geometry = bind_rotary_geometry_references(
        model,
        operation.geometry,
        axis_edge_id=axis.edge_id,
        surface_face_ids=(surface.face_id,),
    )
    assert geometry.profile.axial_start_mm == pytest.approx(0.0, abs=1.0e-7)
    assert geometry.profile.axial_end_mm == pytest.approx(12.0, abs=1.0e-7)
    assert geometry.profile.radius_start_mm == pytest.approx(15.0, abs=1.0e-7)
    assert geometry.profile.radius_end_mm == pytest.approx(9.0, abs=1.0e-7)
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        geometry=geometry,
        parameters=RotaryProcessParameters(
            pitch_mm=6,
            end_angle_rad=4 * math.pi,
            sampling_angle_rad=math.radians(5),
            angular_velocity_rad_s=0.2,
            feedrate_mm_min=300,
        ),
    )
    result = controller.generate_operation(operation.operation_id)
    assert result.exportable
    assert result.readback.passed
    path_definition = result.plan.paths[0]
    assert result.plan.points[path_definition.start_point_index].radius_mm == pytest.approx(
        15.0, abs=1.0e-7
    )
    assert result.plan.points[path_definition.end_point_index].radius_mm == pytest.approx(
        9.0, abs=1.0e-7
    )


def test_r01_topology_drift_rebinds_axis_and_surface_to_new_ids(tmp_path: Path) -> None:
    source, axis, surface = _rotary_model(tmp_path / "source")
    controller = RotaryController(source, setup=_setup(source.bodies[0].body_id))
    operation = controller.create_operation("rotary_spiral")
    geometry = bind_rotary_geometry_references(
        source,
        operation.geometry,
        axis_edge_id=axis.edge_id,
        surface_face_ids=(surface.face_id,),
    )
    operation = replace(operation, geometry=geometry)
    original_plan = build_rotary_plan(operation)
    target = copy.copy(source)
    target.edges = [copy.copy(item) for item in source.edges]
    target.faces = [copy.copy(item) for item in source.faces]
    target.vertices = [copy.copy(item) for item in source.vertices]
    target_axis = target.edge_map[axis.edge_id]
    target_surface = target.face_map[surface.face_id]
    new_axis_id = f"{axis.edge_id}-drifted"
    new_surface_id = f"{surface.face_id}-drifted"
    target_axis.edge_id = new_axis_id
    target_surface.face_id = new_surface_id
    target_surface.edge_ids = [
        new_axis_id if item == axis.edge_id else item for item in target_surface.edge_ids
    ]
    for vertex in target.vertices:
        vertex.edge_ids = [
            new_axis_id if item == axis.edge_id else item for item in vertex.edge_ids
        ]
    for edge in target.edges:
        edge.face_ids = [
            new_surface_id if item == surface.face_id else item for item in edge.face_ids
        ]
    rebound = rebind_rotary_operation_geometry(operation, source, target)
    assert rebound.state.value == "dirty"
    assert rebound.geometry.frame.axis_reference is not None
    assert rebound.geometry.frame.axis_reference.object_id == new_axis_id
    assert rebound.geometry.profile.surface_references[0].object_id == new_surface_id
    assert rebound.geometry.is_complete
    assert rebound.geometry.frame.axis_origin_mm == pytest.approx(
        geometry.frame.axis_origin_mm
    )
    assert rebound.geometry.frame.axis_direction == pytest.approx(
        geometry.frame.axis_direction
    )
    assert rebound.geometry.profile.axial_start_mm == pytest.approx(
        geometry.profile.axial_start_mm
    )
    assert rebound.geometry.profile.axial_end_mm == pytest.approx(
        geometry.profile.axial_end_mm
    )
    assert rebound.geometry.profile.radius_start_mm == pytest.approx(
        geometry.profile.radius_start_mm
    )
    assert rebound.geometry.profile.radius_end_mm == pytest.approx(
        geometry.profile.radius_end_mm
    )
    rebound_plan = build_rotary_plan(rebound)
    assert [point.position for point in rebound_plan.points] == pytest.approx(
        [point.position for point in original_plan.points]
    )
