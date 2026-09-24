"""PC02-PC06 integration checks for the restricted Freeform workbench."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PyQt5.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PyQt5.QtGui import QWheelEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QPushButton  # noqa: E402

from five_axis_slicer.automation_routes import AutomationRouter  # noqa: E402
from five_axis_slicer.freeform_commands import FreeformCommandService  # noqa: E402
from five_axis_slicer.freeform_controller import FreeformController  # noqa: E402
from five_axis_slicer.freeform_ui import FreeformPage  # noqa: E402
from five_axis_slicer.material_plan_editor import MaterialPlanEditor  # noqa: E402
from five_axis_slicer.tool_change_station_editor import ToolChangeStationEditor  # noqa: E402
from five_axis_slicer.manufacturing.controller_profile import (  # noqa: E402
    OWN_AC_OFFLINE_CONTROLLER,
)
from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.freeform_parameters import (  # noqa: E402
    FreeformProcessParameters,
)
from five_axis_slicer.manufacturing.freeform_solid_parameters import (  # noqa: E402
    SolidFillProcessParameters,
)
from five_axis_slicer.manufacturing.own_printer import own_ac_profile  # noqa: E402
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_PLA_175,
    NozzleProfile,
    ResourceSnapshot,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    ManufacturingObjectAssignments,
    ManufacturingSetup,
)
from five_axis_slicer.models import SelectionState  # noqa: E402
from five_axis_slicer.postprocessing.indexed_tube import GenerationCancelled  # noqa: E402
from five_axis_slicer.project_io import load_project, save_project  # noqa: E402
from five_axis_slicer.step_loader import load_step  # noqa: E402
from test_tube_ui import TubeViewerStub  # noqa: E402

APP = QApplication.instance() or QApplication([])


def _frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", (0, 0, 0), confirmed=True),
        DirectionReference("numeric", (0, 0, 1), confirmed=True),
        DirectionReference("numeric", (1, 0, 0), confirmed=True),
    )


def _setup(model) -> ManufacturingSetup:
    nozzle = NozzleProfile(
        "freeform-test-nozzle",
        "Freeform test nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2.0,
        outer_profile_rz_mm=((0.3, 0.0), (0.4, 2.0)),
    )
    return ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(
            part_body_ids=(model.bodies[1].body_id,),
            ignored_body_ids=tuple(
                body.body_id for body in model.bodies if body.body_id != model.bodies[1].body_id
            ),
        ),
        machine=ResourceSnapshot.capture("machine", own_ac_profile()),
        nozzle=ResourceSnapshot.capture("nozzle", nozzle),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("freeform-test-pla")
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


@pytest.fixture(scope="module")
def configured():
    model = load_step(ROOT / "example" / "叶轮" / "叶轮.stp")
    controller = FreeformController(model, setup=_setup(model))
    operation = controller.create_operation("freeform_surface", operation_id="freeform-pc06")
    guides = tuple(
        {
            "edge_ids": (f"body_{index:03d}_edge_0011",),
            "reversed_flags": (True,),
            "face_id": f"body_{index:03d}_face_0006",
        }
        for index in range(2, 10)
    )
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        face_ids=tuple(item["face_id"] for item in guides),
        guides=guides,
        parameters=FreeformProcessParameters(
            sampling_step_mm=3.0,
            path_spacing_mm=0.6,
            path_count=1,
            layer_count=1,
            feedrate_mm_min=900,
        ),
    )
    return controller, operation, model, guides


def test_controller_generate_stale_undo_cancel_and_reopen(configured) -> None:
    base, operation, model, _guides = configured
    controller = base.fork()
    service = FreeformCommandService(controller)
    first = controller.generate_operation(operation.operation_id)
    assert first.offline_exportable and first.readback.passed
    service.execute_command("set_operation", operation.operation_id, bead_width_mm=0.7)
    assert controller.product_state(operation.operation_id).status == "stale"
    service.execute_command("undo")
    assert controller.product_result(operation.operation_id) is first
    with pytest.raises(GenerationCancelled):
        controller.generate_operation(operation.operation_id, cancelled=lambda: True)
    assert controller.product_result(operation.operation_id) is first
    reopened = FreeformController.from_json(controller.to_json(), cad_model=model)
    assert reopened.product_result(operation.operation_id) is None
    assert reopened.product_state(operation.operation_id).status == "stale"


def test_project_roundtrip_preserves_freeform_stable_references(configured, tmp_path) -> None:
    controller, operation, model, _guides = configured
    project = save_project(
        tmp_path / "freeform-project",
        model,
        SelectionState(face_ids={item.object_id for item in operation.geometry.faces}),
        setup=controller.setup,
        operations=(operation,),
        original_source_path=model.source_path,
    )
    restored = load_project(project).operations[0]
    assert restored == operation
    assert restored.geometry.faces[0].signature
    assert restored.geometry.guides[0].edges[0].edge.signature


def test_project_roundtrip_preserves_solid_roles_and_process(configured, tmp_path) -> None:
    base, _operation, model, _guides = configured
    controller = base.fork()
    solid = controller.create_operation("surface_solid_fill", operation_id="solid-reopen")
    solid = controller.configure_solid_operation(
        operation_id=solid.operation_id,
        solid_geometry={
            "substrate_body_id": "body_001",
            "bodies": [{
                "body_id": "body_002",
                "surface_face_id": "body_002_face_0006",
                "opposite_face_id": "body_002_face_0005",
                "root_edge_id": "body_002_edge_0011",
            }],
        },
        parameters=SolidFillProcessParameters(solid_thickness_mm=1.0),
    )
    project = save_project(
        tmp_path / "solid-project", model, SelectionState(),
        setup=controller.setup, operations=(solid,), original_source_path=model.source_path,
    )
    restored = load_project(project)
    assert restored.setup == controller.setup
    assert restored.operations == (solid,)
    assert restored.operations[0].semantic_sha256() == solid.semantic_sha256()


class _Page:
    def __init__(self, controller):
        self.controller = controller

    def state_json(self):
        return self.controller.state_json()


class _Window:
    def __init__(self, controller):
        self.freeform_page = _Page(controller)
        self.freeform_command_service = FreeformCommandService(controller)


def test_script_and_http_share_freeform_command_kernel(configured) -> None:
    base, operation, _model, _guides = configured
    scripted = base.fork()
    output = FreeformCommandService(scripted).execute_script("自由曲面.状态()")
    assert "freeform_surface" in output
    router = AutomationRouter(_Window(base.fork()))
    generated = router.dispatch(
        "/freeform/operation/generate", {"operation_id": operation.operation_id}
    )
    assert generated["command"]["payload"]["status"] == "warning"
    updated = router.dispatch(
        "/freeform/operation/set",
        {"operation_id": operation.operation_id, "bead_width_mm": 0.7},
    )
    assert updated["freeform"]["products"][0]["status"] == "stale"
    assert router.dispatch("/freeform/undo", {})["freeform"]["products"][0]["status"] == "warning"


def test_solid_fill_selection_and_parameters_share_api_script_and_http(configured) -> None:
    base, _operation, _model, _guides = configured
    controller = base.fork()
    service = FreeformCommandService(controller)
    service.execute_command(
        "create_operation",
        "spherical_solid_fill",
        operation_id="solid-shared-command",
    )
    configured_result = service.execute_command(
        "set_operation",
        "solid-shared-command",
        solid_geometry={"body_ids": ["body_002"], "center_mm": [0, 0, 0]},
        substrate_radius_mm=20.0,
        radial_thickness_mm=0.4,
    )
    assert configured_result.payload["solid_geometry"]["bodies"][0]["object_id"] == "body_002"

    output = service.execute_script(
        '自由曲面.设置操作("solid-shared-command", bead_width_mm=0.5, path_spacing_mm=0.5)'
    )
    assert json.loads(output)["solid_parameters"]["bead_width_mm"] == 0.5

    router = AutomationRouter(_Window(controller))
    response = router.dispatch(
        "/freeform/operation/set",
        {"operation_id": "solid-shared-command", "sampling_step_mm": 0.3},
    )
    operation_payload = response["command"]["payload"]
    assert operation_payload["solid_parameters"]["sampling_step_mm"] == 0.3
    assert operation_payload["solid_geometry"]["bodies"][0]["object_id"] == "body_002"


def test_surface_solid_gui_converts_selected_root_edge_and_faces(configured) -> None:
    base, _operation, _model, _guides = configured
    controller = base.fork()
    solid = controller.create_operation(
        "surface_solid_fill", operation_id="solid-gui-selection"
    )
    page = FreeformPage(controller=controller, viewer_factory=TubeViewerStub)
    page.viewer.set_selection(
        edge_ids={"body_002_edge_0011"},
        face_ids={"body_002_face_0005", "body_002_face_0006"},
    )

    page.use_selection_button.click()
    payload = json.loads(page.solid_geometry_edit.text())
    assert payload["bodies"] == [
        {
            "body_id": "body_002",
            "surface_face_id": "body_002_face_0006",
            "opposite_face_id": "body_002_face_0005",
            "root_edge_id": "body_002_edge_0011",
        }
    ]
    page.apply_button.click()

    updated = controller.operation(solid.operation_id)
    assert updated.solid_geometry is not None
    assert page.generate_button.isEnabled()
    assert page._last_error is None
    assert page.edge_ids_edit.isHidden()
    assert page.guides_json_edit.isHidden()
    assert not page.solid_geometry_edit.isHidden()
    assert page.status_label.text().startswith("状态：")
    page._generation_in_progress = True
    page._update_status_label()
    assert page.status_label.text().startswith("正在生成")
    page._generation_in_progress = False
    page.set_language("en")
    assert page.use_selection_button.text() == "Use selected geometry"
    assert page.status_label.text().startswith("Status: ")
    page.close()


def test_freeform_json_fields_show_long_inputs_without_truncating_them(configured) -> None:
    base, _operation, _model, _guides = configured
    page = FreeformPage(controller=base.fork(), viewer_factory=TubeViewerStub)
    payload = {"blades": [{"body_id": f"body_{index:03d}"} for index in range(25)]}
    source = json.dumps(payload, ensure_ascii=False, indent=2)

    page.solid_geometry_edit.setText(source)

    assert page.solid_geometry_edit.text() == source
    assert page.solid_geometry_edit.lineWrapMode() == page.solid_geometry_edit.WidgetWidth
    assert page.solid_geometry_edit.tabChangesFocus()
    assert page.solid_geometry_edit.height() >= 180
    assert "body_024" in page.solid_geometry_summary.text()
    page.solid_geometry_edit.setText("{")
    assert "JSON" in page.solid_geometry_summary.text()
    page.close()


def test_project_switch_clears_old_freeform_path_overlay(configured) -> None:
    base, _operation, model, _guides = configured
    page = FreeformPage(controller=base.fork(), viewer_factory=TubeViewerStub)
    page.viewer.gcode_preview = object()
    page.set_controller(FreeformController(model, setup=base.setup))
    assert page.viewer.gcode_preview is None
    assert page.viewer.model is model
    page.close()


def test_freeform_viewer_can_pick_body_then_face_and_preserves_mode_after_reload(configured) -> None:
    base, _operation, model, _guides = configured
    page = FreeformPage(controller=base.fork(), viewer_factory=TubeViewerStub)
    page.pick_kind_combo.setCurrentIndex(page.pick_kind_combo.findData("body"))
    assert page.viewer.selection.mode == "body"
    page.pick_kind_combo.setCurrentIndex(page.pick_kind_combo.findData("face"))
    assert page.viewer.selection.mode == "face"
    page.set_controller(FreeformController(model, setup=base.setup))
    assert page.viewer.selection.mode == "face"
    page.close()


def test_radial_solid_gui_captures_hub_and_three_blade_roles(configured) -> None:
    base, _operation, _model, _guides = configured
    model = load_step("example/三叶扇/Supportless_sample.stp")
    controller = FreeformController(model, setup=base.setup)
    operation = controller.create_operation(
        "radial_solid_fill", operation_id="three-blade-gui-selection"
    )
    page = FreeformPage(controller=controller, viewer_factory=TubeViewerStub)
    page.viewer.set_selection(
        body_ids={"body_001", "body_002", "body_003", "body_004"},
        face_ids={
            f"body_{index:03d}_face_{face:04d}"
            for index in range(2, 5) for face in (5, 6)
        },
    )

    page.use_selection_button.click()
    geometry = json.loads(page.solid_geometry_edit.text())
    assert geometry["hub_body_id"] == "body_001"
    assert geometry["substrate_body_id"] == "body_001"
    assert len(geometry["blades"]) == 3
    assert "body_002" in page.solid_geometry_summary.text()
    assert "body_004" in page.solid_geometry_summary.text()
    assert all(item["root_face_id"].endswith("face_0005") for item in geometry["blades"])
    assert all(item["outer_face_id"].endswith("face_0006") for item in geometry["blades"])
    page.apply_button.click()
    updated = controller.operation(operation.operation_id)
    assert updated.solid_geometry is not None
    assert page._last_error is None
    page.close()


def test_surface_growth_strategy_is_editable_and_keeps_legacy_default(configured) -> None:
    base, _operation, model, _guides = configured
    controller = FreeformController(model, setup=base.setup)
    operation = controller.create_operation("surface_solid_fill", operation_id="growth-gui")
    controller.configure_solid_operation(
        operation_id=operation.operation_id,
        solid_geometry={
            "substrate_body_id": "body_001",
            "bodies": [{
                "body_id": "body_002",
                "surface_face_id": "body_002_face_0006",
                "opposite_face_id": "body_002_face_0005",
                "root_edge_id": "body_002_edge_0011",
            }],
        },
        parameters=SolidFillProcessParameters(solid_thickness_mm=1.0),
    )
    page = FreeformPage(controller=controller, viewer_factory=TubeViewerStub)
    assert page.surface_growth_combo.currentData() == "surface_thickness"
    assert "surface_growth_strategy" not in page.solid_parameters_edit.text()
    page.surface_growth_combo.setCurrentIndex(
        page.surface_growth_combo.findData("root_edge_outward")
    )
    page.apply_button.click()
    assert page._last_error is None
    assert controller.operation(operation.operation_id).solid_parameters.surface_growth_strategy == (
        "root_edge_outward"
    )
    page.set_language("en")
    assert "root edge" in page.surface_growth_combo.currentText()
    page.close()


def test_tool_change_station_is_editable_and_persisted_via_freeform_ui(configured) -> None:
    base, operation, model, _guides = configured
    controller = base.fork()
    page = FreeformPage(controller=controller, viewer_factory=TubeViewerStub)
    station = {
        "clearance_z_mm": 180.0,
        "cutter_xyz_mm": [130.0, 100.0, 80.0],
        "exchange_xyz_mm": [140.0, 100.0, 80.0],
        "purge_xyz_mm": [150.0, 100.0, 80.0],
        "wipe_start_xyz_mm": [160.0, 100.0, 80.0],
        "wipe_end_xyz_mm": [170.0, 100.0, 80.0],
    }
    page.tool_change_station_edit.setText(json.dumps(station))
    page.apply_button.click()
    assert page._last_error is None
    assert controller.controller_profile.tool_change_station is not None
    restored = FreeformController.from_json(controller.to_json(), cad_model=model)
    assert restored.controller_profile.tool_change_station == controller.controller_profile.tool_change_station
    old_profile = controller.controller_profile
    page.tool_change_station_edit.setText('{"clearance_z_mm":10}')
    page.apply_button.click()
    assert page._last_error
    assert controller.controller_profile == old_profile
    page.close()


def test_material_table_button_writes_valid_plan_for_selected_operation(
    configured, monkeypatch
) -> None:
    base, operation, _model, _guides = configured
    page = FreeformPage(controller=base.fork(), viewer_factory=TubeViewerStub)

    def submit(editor):
        editor.add_channel()
        editor.add_region()
        editor.result_payload = editor.build_payload()
        return 1

    monkeypatch.setattr(MaterialPlanEditor, "exec_", submit)
    page.material_plan_button.click()
    payload = json.loads(page.material_plan_edit.text())
    assert payload["regions"] == [{
        "region_id": "*", "channel_id": "T0"
    }]
    page.apply_button.click()
    assert page._last_error is None
    assert page.controller.operation(operation.operation_id).material_plan is not None
    page.close()


def test_station_button_updates_controller_after_apply(configured, monkeypatch) -> None:
    base, _operation, _model, _guides = configured
    page = FreeformPage(controller=base.fork(), viewer_factory=TubeViewerStub)

    def submit(editor):
        values = {
            "clearance_z_mm": "180",
            "cutter_xyz_mm": "130, 100, 80",
            "exchange_xyz_mm": "140, 100, 80",
            "purge_xyz_mm": "150, 100, 80",
            "wipe_start_xyz_mm": "160, 100, 80",
            "wipe_end_xyz_mm": "170, 100, 80",
            "travel_feedrate_mm_min": "3000",
            "wipe_feedrate_mm_min": "1200",
            "wipe_passes": "2",
            "cutter_command": "M98 P100",
        }
        for name, value in values.items():
            editor.edits[name].setText(value)
        editor.result_payload = editor.build_payload()
        return 1

    monkeypatch.setattr(ToolChangeStationEditor, "exec_", submit)
    page.tool_change_station_button.click()
    assert json.loads(page.tool_change_station_edit.text())["clearance_z_mm"] == 180
    page.apply_button.click()
    assert page._last_error is None
    assert page.controller.controller_profile.tool_change_station is not None
    page.close()


def test_surface_solid_controller_blocks_unsafe_operation_transition(configured) -> None:
    base, _operation, _model, _guides = configured
    controller = base.fork()
    solid = controller.create_operation(
        "surface_solid_fill", operation_id="solid-product-readback"
    )
    controller.configure_solid_operation(
        operation_id=solid.operation_id,
        solid_geometry={
            "bodies": [
                {
                    "body_id": "body_002",
                    "surface_face_id": "body_002_face_0006",
                    "opposite_face_id": "body_002_face_0005",
                    "root_edge_id": "body_002_edge_0011",
                }
            ],
            "substrate_body_id": "body_001",
        },
        parameters=SolidFillProcessParameters(solid_thickness_mm=1.0),
    )

    result = controller.generate_operation(solid.operation_id)

    assert result.plan.operation_type == "surface_solid_fill"
    assert not result.offline_exportable
    assert not result.readback.passed
    assert not result.gcode
    rejected = next(
        issue for issue in result.validation.issues
        if issue.code == "motion.transition_route_unavailable"
    )
    if rejected.context["reason"] == "all sampled XYZAC routes rejected":
        assert rejected.context["attempted_routes"] > 0
        assert rejected.context["candidate_failures"]
    else:
        assert rejected.context["reason"] == "target nozzle pose intersects previously printed material"
        assert rejected.context["measured_distance_mm"] <= rejected.context["required_clearance_mm"]
    assert any(point.extrusion_role == "infill" for point in result.toolpath.points)
    summary = result.to_json()
    assert summary["schema_version"] == 2
    assert summary["toolpath_summary"]["point_count"] == len(result.toolpath.points)
    assert summary["machine_trajectory_summary"]["sample_count"] == len(result.trajectory.samples)
    assert "toolpath" not in summary["manifest"]
    assert "samples" not in summary["machine_trajectory_summary"]


@pytest.mark.parametrize(
    "language,size", [("zh", (1366, 768)), ("en", (1600, 900)), ("en", (1920, 1080))]
)
def test_qt_multi_guide_editor_is_bilingual_and_fits(configured, language, size) -> None:
    controller, operation, _model, guides = configured
    page = FreeformPage(controller=controller.fork(), viewer_factory=TubeViewerStub)
    page.set_language(language)
    page.resize(*size)
    page.show()
    APP.processEvents()
    page.guides_json_edit.setText(json.dumps(guides))
    page.apply_button.click()
    assert len(page.controller.operation(operation.operation_id).geometry.guides) == 8
    assert page.editor_scroll.horizontalScrollBar().maximum() == 0
    assert page.editor_scroll.width() == 620
    assert page.viewer.width() >= 500
    for button in page.findChildren(QPushButton):
        if button.isVisible():
            assert button.fontMetrics().horizontalAdvance(button.text()) <= button.width()
    page.close()


def test_freeform_editor_wheel_does_not_change_retract_length(configured) -> None:
    controller, _operation, _model, _guides = configured
    page = FreeformPage(controller=controller.fork(), viewer_factory=TubeViewerStub)
    spin = page._spins["retract_length_mm"]
    original = spin.value()
    event = QWheelEvent(
        QPointF(4, 4), QPointF(4, 4), QPoint(0, 0), QPoint(0, 120),
        Qt.NoButton, Qt.NoModifier, Qt.ScrollUpdate, False,
    )
    spin.wheelEvent(event)
    assert spin.value() == original
    assert not event.isAccepted()
    page.close()


def test_trim_failure_is_locatable_and_blocks_previous_result() -> None:
    model = load_step(ROOT / "example" / "球形NEU校徽" / "球形测试件.STEP")
    controller = FreeformController(model, setup=_setup(model))
    operation = controller.create_operation(operation_id="hemisphere-trim-failure")
    controller.configure_operation(
        operation_id=operation.operation_id,
        face_ids=("body_002_face_0001",),
        guides=(
            {
                "edge_ids": ("body_002_edge_0018",),
                "reversed_flags": (True,),
                "face_id": "body_002_face_0001",
            },
        ),
        parameters=FreeformProcessParameters(path_count=2),
    )
    with pytest.raises(Exception, match="curve.offset_outside_face"):
        controller.generate_operation(operation.operation_id)
    assert controller.product_result(operation.operation_id) is None
    assert controller.product_state(operation.operation_id).status == "error"


def test_controller_profile_remains_offline_only(configured) -> None:
    controller, _operation, _model, _guides = configured
    state = controller.state_json()
    assert state["capabilities"]["offline_only"]
    assert not OWN_AC_OFFLINE_CONTROLLER.machine_executable
