import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cadquery as cq
import pytest
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication

from five_axis_slicer.manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
)
from five_axis_slicer.manufacturing.setup import ManufacturingSetup
from five_axis_slicer.models import BodyInfo, BoundingBox, CadModel
from five_axis_slicer.planar_controller import PlanarController
from five_axis_slicer.planar_ui import PlanarPage
from five_axis_slicer.ui import MainWindow
from test_tube_ui import TubeViewerStub
from test_planar_zigzag_product import _setup

APP = QApplication.instance() or QApplication([])


def _app() -> QApplication:
    return APP


def _frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", (0.0, 0.0, 0.0), confirmed=True),
        DirectionReference("numeric", (0.0, 0.0, 1.0), confirmed=True),
        DirectionReference("numeric", (1.0, 0.0, 0.0), confirmed=True),
    )


def _controller() -> PlanarController:
    shape = cq.Workplane("XY").box(4.0, 4.0, 2.0)
    body = BodyInfo(
        "body",
        1,
        "body",
        (0.8, 0.8, 0.8),
        bounds=BoundingBox((-2.0, -2.0, -1.0), (2.0, 2.0, 1.0)),
        volume=32.0,
        surface_area=64.0,
        centroid=(0.0, 0.0, 0.0),
    )
    model = CadModel(
        Path("planar-ui.step"), "a" * 64, [body], [], {"body": shape.val().wrapped}, {}
    )
    setup = ManufacturingSetup(
        model_coordinate_system=_frame("model"), build_coordinate_system=_frame("build")
    )
    return PlanarController(model, setup=setup)


def _path_controller() -> PlanarController:
    controller = _controller()
    controller.mark_setup_changed(_setup(), reason="test_ready_setup")
    return controller


def test_loaded_model_without_operation_prompts_for_creation_in_both_languages() -> None:
    page = PlanarPage(controller=_controller(), viewer_factory=TubeViewerStub)
    assert "新建操作" in page.status_label.text()
    assert "打开 STEP" not in page.status_label.text()
    page.set_language("en")
    assert "Create operation" in page.status_label.text()
    page.close()


def test_model_visibility_toggle_exposes_internal_planar_paths() -> None:
    page = PlanarPage(controller=_controller(), viewer_factory=TubeViewerStub)
    calls: list[bool] = []
    page.viewer.set_model_visible = calls.append

    assert page.show_model_checkbox.text() == "显示模型"
    assert page.path_display_combo.currentData() == "paper"
    assert page.path_display_combo.currentText() == "完整线条（快速）"
    page.show_model_checkbox.setChecked(False)
    assert calls == [False]
    page.set_language("en")
    assert page.show_model_checkbox.text() == "Show model"
    assert page.path_display_combo.currentText() == "Full lines (fast)"
    page.show_model_checkbox.setChecked(True)
    assert calls == [False, True]
    page.close()


def test_generated_planar_preview_defaults_to_full_lines_and_can_show_beads() -> None:
    page = PlanarPage(controller=_path_controller(), viewer_factory=TubeViewerStub)
    page.operation_type_combo.setCurrentIndex(page.operation_type_combo.findData("planar_zigzag"))
    page.create_button.click()
    page.first_layer_spin.setValue(0.0)
    page.last_layer_spin.setValue(0.0)
    page.feedrate_spin.setValue(100.0)
    page.travel_feedrate_spin.setValue(100.0)
    page.apply_button.click()
    page.generate_button.click()

    assert page.viewer.gcode_preview is not None
    assert page.viewer.quality_mode == "paper"
    page.path_display_combo.setCurrentIndex(1)
    assert page.viewer.quality_mode == "interactive"
    page.close()


def test_apply_routes_planar_inputs_through_gui_command_service() -> None:
    _app()
    page = PlanarPage(controller=_controller(), viewer_factory=TubeViewerStub)
    page.create_button.click()
    page.first_layer_spin.setValue(0.0)
    page.last_layer_spin.setValue(0.0)
    page.feedrate_spin.setValue(900.0)
    page.line_spacing_spin.setValue(0.55)
    page.travel_feedrate_spin.setValue(1700.0)
    page.retract_length_spin.setValue(0.8)
    page.apply_button.click()

    operation = page.controller.operations[0]
    assert operation.geometry.body is not None
    assert operation.geometry.body.object_id == "body"
    assert operation.parameters.feedrate_mm_min == 900.0
    assert operation.parameters.line_spacing_mm == 0.55
    assert operation.parameters.travel_feedrate_mm_min == 1700.0
    assert operation.parameters.retract_length_mm == 0.8


def test_apply_routes_p03_p05_parameters_and_english_labels() -> None:
    page = PlanarPage(controller=_controller(), viewer_factory=TubeViewerStub)
    page.operation_type_combo.setCurrentIndex(page.operation_type_combo.findData("planar_offset"))
    page.create_button.click()
    page.offset_pass_count_spin.setValue(5)
    page.wall_thickness_spin.setValue(1.2)
    page.thin_wall_max_passes_spin.setValue(2)
    page.spiral_samples_spin.setValue(80)
    page.apply_button.click()
    page.set_language("en")

    parameters = page.controller.operations[-1].parameters
    assert parameters.offset_pass_count == 5
    assert parameters.wall_thickness_mm == 1.2
    assert parameters.thin_wall_max_passes == 2
    assert parameters.spiral_samples_per_contour == 80
    assert "Offset" in page._labels["offset_passes"].text()
    assert "Spiral" in page._labels["spiral_samples"].text()


@pytest.mark.parametrize("operation_type", ["planar_offset", "planar_thin_wall", "planar_spiral"])
def test_p03_p05_gui_generate_and_export_enable(operation_type: str) -> None:
    page = PlanarPage(controller=_path_controller(), viewer_factory=TubeViewerStub)
    page.operation_type_combo.setCurrentIndex(page.operation_type_combo.findData(operation_type))
    page.create_button.click()
    page.first_layer_spin.setValue(-0.5 if operation_type == "planar_spiral" else 0.0)
    page.last_layer_spin.setValue(0.0)
    page.layer_height_spin.setValue(0.5)
    page.feedrate_spin.setValue(100.0)
    page.travel_feedrate_spin.setValue(100.0)
    page.apply_button.click()

    assert page.generate_button.isEnabled()
    page.generate_button.click()

    result = page.controller.product_result(page.controller.operations[-1].operation_id)
    assert result is not None and result.exportable
    assert page.export_button.isEnabled(), page.state_json()
    assert page.viewer.visible_path_segment_count > 0


def test_spiral_gui_reports_error_and_recovers_after_layer_fix() -> None:
    page = PlanarPage(controller=_path_controller(), viewer_factory=TubeViewerStub)
    page.operation_type_combo.setCurrentIndex(page.operation_type_combo.findData("planar_spiral"))
    page.create_button.click()
    page.first_layer_spin.setValue(0.0)
    page.last_layer_spin.setValue(0.0)
    page.feedrate_spin.setValue(100.0)
    page.travel_feedrate_spin.setValue(100.0)
    page.apply_button.click()

    page._generate()

    assert "planar.spiral_layers_insufficient" in page.status_label.text()
    assert not page.export_button.isEnabled()

    page.first_layer_spin.setValue(-0.5)
    page.last_layer_spin.setValue(0.0)
    page.layer_height_spin.setValue(0.5)
    page.apply_button.click()
    page._generate()

    assert page.export_button.isEnabled()
    assert "G-code" in page.status_label.text()


def test_generate_emits_the_generated_preview_toolpath() -> None:
    _app()
    page = PlanarPage(controller=_controller(), viewer_factory=TubeViewerStub)
    page.create_button.click()
    page.first_layer_spin.setValue(0.0)
    page.last_layer_spin.setValue(0.0)
    page.apply_button.click()
    previews = []
    page.preview_ready.connect(previews.append)

    page.generate_button.click()

    assert len(previews) == 1
    assert previews[0].operation_id == page.controller.operations[0].operation_id
    assert page.viewer.model is page.controller.cad_model
    operation_id = page.controller.operations[0].operation_id
    assert str(page.viewer.gcode_preview.source_path) == f"<generated:{operation_id}>"
    assert page.viewer.visible_path_segment_count > 0


def test_existing_operations_can_be_selected_and_previewed_independently() -> None:
    page = PlanarPage(controller=_path_controller(), viewer_factory=TubeViewerStub)
    page.create_button.click()
    region_id = page.controller.operations[-1].operation_id
    page.first_layer_spin.setValue(0.0)
    page.last_layer_spin.setValue(0.0)
    page.apply_button.click()
    page.generate_button.click()

    page.operation_type_combo.setCurrentIndex(page.operation_type_combo.findData("planar_offset"))
    page.create_button.click()
    zigzag_id = page.controller.operations[-1].operation_id
    page.first_layer_spin.setValue(0.0)
    page.last_layer_spin.setValue(0.0)
    page.feedrate_spin.setValue(100.0)
    page.travel_feedrate_spin.setValue(100.0)
    page.apply_button.click()
    page.generate_button.click()

    page.operation_instance_combo.setCurrentIndex(page.operation_instance_combo.findData(region_id))
    _app().processEvents()
    assert page.state_json()["ui"]["selected_operation_id"] == region_id
    assert str(page.viewer.gcode_preview.source_path) == f"<generated:{region_id}>"

    page.operation_instance_combo.setCurrentIndex(page.operation_instance_combo.findData(zigzag_id))
    _app().processEvents()
    assert page.state_json()["ui"]["selected_operation_id"] == zigzag_id
    assert str(page.viewer.gcode_preview.source_path) == f"<generated:{zigzag_id}>"
    selected = page.controller.operation(zigzag_id)
    product = page.controller.product_state(zigzag_id)
    result = page.controller.product_result(zigzag_id)
    assert page.export_button.isEnabled(), (
        selected.operation_type,
        product,
        None if result is None else result.exportable,
        page._last_generation_error,
        page.status_label.text(),
    )


def test_qt_cancel_button_preserves_the_previous_generated_result() -> None:
    page = PlanarPage(controller=_path_controller(), viewer_factory=TubeViewerStub)
    page.operation_type_combo.setCurrentIndex(page.operation_type_combo.findData("planar_offset"))
    page.create_button.click()
    page.first_layer_spin.setValue(0.0)
    page.last_layer_spin.setValue(0.0)
    page.feedrate_spin.setValue(100.0)
    page.travel_feedrate_spin.setValue(100.0)
    page.apply_button.click()
    page.generate_button.click()
    operation_id = page.controller.operations[-1].operation_id
    previous = page.controller.product_result(operation_id)

    QTimer.singleShot(0, page.cancel_button.click)
    page.generate_button.click()

    assert page.controller.product_result(operation_id) is previous
    assert page.controller.product_state(operation_id).status in {"ready", "warning"}
    assert page.export_button.isEnabled()


def test_all_planar_operation_types_survive_reopen_and_remain_selectable() -> None:
    page = PlanarPage(controller=_path_controller(), viewer_factory=TubeViewerStub)
    operation_types = tuple(page.controller.available_operation_types)
    for operation_type in operation_types:
        page.operation_type_combo.setCurrentIndex(
            page.operation_type_combo.findData(operation_type)
        )
        page.create_button.click()

    assert page.operation_instance_combo.count() == len(operation_types) == 6
    assert {item.operation_type for item in page.controller.operations} == set(operation_types)
    payload = page.controller.to_json()
    restored = PlanarController.from_json(payload, cad_model=page.controller.cad_model)
    page.set_controller(restored)

    assert page.operation_instance_combo.count() == 6
    for operation in restored.operations:
        page.operation_instance_combo.setCurrentIndex(
            page.operation_instance_combo.findData(operation.operation_id)
        )
        assert page.state_json()["ui"]["selected_operation_id"] == operation.operation_id


def test_issue_list_activation_exposes_a_locatable_problem_and_help_is_bilingual() -> None:
    page = PlanarPage(controller=_controller(), viewer_factory=TubeViewerStub)
    page.resize(1366, 768)
    page.show()
    _app().processEvents()
    assert all(label.width() > 0 and label.text() for label in page._labels.values())
    assert page.issue_list.horizontalScrollBar().maximum() == 0
    assert page.issue_list.count() > 0
    item = page.issue_list.item(0)
    assert page.issue_list.fontMetrics().horizontalAdvance(item.text()) <= 250
    assert item.data(Qt.UserRole)["code"] in item.toolTip()
    page.issue_list.setCurrentItem(item)
    page.issue_list.itemActivated.emit(item)
    assert item.data(Qt.UserRole)["code"] in page.status_label.text()
    assert "mm" in page.help_label.text()

    page.set_language("en")
    assert "Existing operation" in page._labels["operation_instance"].text()
    assert "Stale" in page.help_label.text()


def test_invalid_generation_is_disabled_and_english_text_is_applied() -> None:
    _app()
    page = PlanarPage(viewer_factory=TubeViewerStub)
    page.set_language("en")

    assert not page.generate_button.isEnabled()
    assert "Open a STEP" in page.status_label.text()
    assert page.generate_button.text() == "Generate preview"


@pytest.mark.parametrize(
    ("width", "height", "diagnostic"),
    (
        (
            1366,
            768,
            "planar.support_region_too_narrow: generated support region contains no "
            "printable bead-width segment",
        ),
        (
            1920,
            1080,
            "planar.support_buildplate_first_layer_required: first requested layer "
            "must represent the buildplate deposition layer",
        ),
    ),
)
def test_editor_contains_long_support_status_without_horizontal_overflow(
    width: int, height: int, diagnostic: str
) -> None:
    page = PlanarPage(controller=_path_controller(), viewer_factory=TubeViewerStub)
    page.status_label.setText(diagnostic)
    page.issues_label.setText("planar.support_unreachable_from_buildplate")
    page.resize(width, height)
    page.show()
    _app().processEvents()
    vertical_scroll = page.editor_scroll.verticalScrollBar()
    vertical_scroll.setValue(vertical_scroll.maximum())
    _app().processEvents()

    viewport = page.editor_scroll.viewport()
    assert page.editor_scroll.horizontalScrollBar().maximum() == 0
    assert page.editor_scroll.widget().width() <= viewport.width()
    assert page.editor_scroll.geometry().right() < page.width()
    for widget in (page.export_button, page.status_label, page.issues_label):
        assert widget.visibleRegion().boundingRect() == widget.rect()

    page.close()


def test_main_window_routes_planar_workbench_and_exposes_state() -> None:
    _app()
    window = MainWindow(
        model_viewer_factory=lambda parent: TubeViewerStub(parent),
        result_viewer_factory=lambda parent: TubeViewerStub(parent),
    )

    window.enter_workbench("planar")
    state = window.current_state()

    assert window.stack.currentWidget() is window.planar_page
    assert state["page"] == "planar"
    assert state["workbench"]["operation"] == "planar_region"
    assert "planar" in state
    window.close()
