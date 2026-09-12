"""C05 Qt, HTTP, restricted-script and persistence integration checks."""

from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt5.QtWidgets import QApplication

from five_axis_slicer.automation_routes import AutomationRouter
from five_axis_slicer.curve_commands import CurveCommandService
from five_axis_slicer.curve_ui import CurvePage
from five_axis_slicer.manufacturing.curve_parameters import CurveOperationDefinition
from five_axis_slicer.models import SelectionState
from five_axis_slicer.project_io import load_project, save_project
from five_axis_slicer.restricted_script import ScriptParseError, parse_script
from test_curve_workbench import _configured, _line_model
from test_tube_ui import TubeViewerStub

APP = QApplication.instance() or QApplication([])


class _Page:
    def __init__(self, controller):
        self.controller = controller

    def state_json(self):
        return self.controller.state_json()


class _Window:
    def __init__(self, controller):
        self.curve_page = _Page(controller)
        self.curve_command_service = CurveCommandService(controller)


def test_curve_qt_generates_shared_toolpath_and_switches_language(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller, operation = _configured(model, edge.edge_id, "curve_multi_pass")
    page = CurvePage(controller=controller, viewer_factory=TubeViewerStub)
    page.set_language("en")

    assert page.generate_button.isEnabled()
    page.generate_button.click()

    result = controller.product_result(operation.operation_id)
    assert result is not None and result.readback.passed
    assert str(page.viewer.gcode_preview.source_path) == f"<generated:{operation.operation_id}>"
    assert page.viewer.visible_path_segment_count > 0
    assert page.export_button.isEnabled()
    assert page.title_label.text() == "Curve Deposition Workbench"
    assert "Stale" in page.help_label.text()


def test_curve_qt_error_then_parameter_recovery(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller, operation = _configured(model, edge.edge_id)
    page = CurvePage(controller=controller, viewer_factory=TubeViewerStub)
    page.edge_ids_edit.setText("missing-edge")
    page.apply_button.click()
    assert "missing-edge" in page.status_label.text()

    page.edge_ids_edit.setText(edge.edge_id)
    page.reverse_flags_edit.setText("0")
    page.normal_mode_combo.setCurrentIndex(page.normal_mode_combo.findData("specified"))
    page.specified_normal_edit.setText("0,0,1")
    page.apply_button.click()
    page.generate_button.click()

    assert controller.product_result(operation.operation_id) is not None
    assert page.export_button.isEnabled()


def test_curve_http_routes_share_the_domain_command_entrypoint(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller, _operation = _configured(model, edge.edge_id)
    window = _Window(controller)
    router = AutomationRouter(window)
    operation_id = controller.operations[0].operation_id

    generated = router.dispatch("/curve/operation/generate", {"operation_id": operation_id})
    state = router.dispatch("/curve/state", {})
    updated = router.dispatch(
        "/curve/operation/set",
        {"operation_id": operation_id, "bead_width_mm": 0.75},
    )

    assert generated["command"]["payload"]["status"] in {"ready", "warning"}
    assert state["curve"]["products"][0]["status"] in {"ready", "warning"}
    assert updated["curve"]["products"][0]["status"] == "stale"
    assert router.dispatch("/curve/undo", {})["curve"]["products"][0]["status"] in {
        "ready",
        "warning",
    }


def test_curve_operation_round_trips_through_project_default_loader(tmp_path: Path) -> None:
    operation = CurveOperationDefinition("curve-1", "setup-1")
    project_json = save_project(
        tmp_path / "curve-project",
        None,
        SelectionState(),
        operations=(operation,),
    )
    loaded = load_project(project_json)
    assert loaded.operations == (operation,)
    assert isinstance(loaded.operations[0], CurveOperationDefinition)


def test_restricted_script_preserves_namespace_and_rejects_cross_domain_transaction() -> None:
    groups = parse_script("curve.state()\n平面.状态()\n")
    assert [group.calls[0].namespace for group in groups] == ["curve", "planar"]
    try:
        parse_script("with curve.transaction():\n    planar.create_operation()\n")
    except ScriptParseError as exc:
        assert exc.code == "E_SCRIPT_FORBIDDEN"
    else:
        raise AssertionError("cross-workbench transaction was accepted")


def test_curve_service_rejects_planar_namespace(tmp_path: Path) -> None:
    model, edge = _line_model(tmp_path)
    controller, _operation = _configured(model, edge.edge_id)
    output = CurveCommandService(controller).execute_script("planar.state()")
    assert output.startswith("ERROR")
    assert "only curve" in output.lower()
