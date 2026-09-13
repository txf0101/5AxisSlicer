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

from PyQt5.QtWidgets import QApplication, QPushButton  # noqa: E402

from five_axis_slicer.automation_routes import AutomationRouter  # noqa: E402
from five_axis_slicer.freeform_commands import FreeformCommandService  # noqa: E402
from five_axis_slicer.freeform_controller import FreeformController  # noqa: E402
from five_axis_slicer.freeform_ui import FreeformPage  # noqa: E402
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
    for button in page.findChildren(QPushButton):
        if button.isVisible():
            assert button.fontMetrics().horizontalAdvance(button.text()) <= button.width()
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
