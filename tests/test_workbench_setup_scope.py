from __future__ import annotations

import os
import json
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMessageBox

from five_axis_slicer.manufacturing.setup import ManufacturingSetup
from five_axis_slicer.manufacturing.controller_profile import ToolChangeStation
from five_axis_slicer.ui import MainWindow
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.workbench_setup_scope import (
    LOCAL_WORKBENCHES,
    binding_ids,
    local_copy,
    publish_to_common,
    resolve_bindings,
)
from test_tube_ui import TubeViewerStub
from test_step_loader import make_two_body_step


APP = QApplication.instance() or QApplication([])


def test_setup_bindings_preserve_local_identity_and_reject_ambiguity() -> None:
    common = ManufacturingSetup(setup_id="plant-common")
    planar = local_copy(common, "planar")
    bindings = {key: common for key in LOCAL_WORKBENCHES}
    bindings["planar"] = planar
    resolved_common, resolved = resolve_bindings(
        (common, planar), {"setup_bindings": binding_ids(common, bindings)}
    )
    assert resolved_common == common
    assert resolved["planar"] == planar
    assert resolved["curve"] == common
    assert publish_to_common(planar, common).setup_id == common.setup_id
    with pytest.raises(ValueError, match="explicit"):
        resolve_bindings((common, planar), {})
    with pytest.raises(ValueError, match="duplicate"):
        resolve_bindings((common, common), {"setup_bindings": {"common": common.setup_id}})
    with pytest.raises(ValueError, match="cannot share"):
        resolve_bindings(
            (common, planar),
            {"setup_bindings": {"common": common.setup_id, "planar": planar.setup_id, "curve": planar.setup_id}},
        )


def test_workbench_sidebar_local_edit_and_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    window = MainWindow(
        http_port=0,
        model_viewer_factory=lambda parent: TubeViewerStub(parent),
        result_viewer_factory=lambda parent: TubeViewerStub(parent),
    )
    try:
        common_id = window.tube_page.controller.setup.setup_id
        for key in LOCAL_WORKBENCHES:
            panel = window._setup_panels[key]
            assert panel.parent() is getattr(window, f"{key}_page")
            assert panel.nodes.count() == 7
            assert panel.copy_button.isEnabled()

        window.planar_page.controller.create_operation("planar_region")
        window._copy_common_to_workbench("planar")
        editor = window._local_setup_editor
        assert editor is not None
        assert editor is window.stack.currentWidget()
        assert editor.create_operation_button.isHidden()
        assert "操作" not in " ".join(
            editor.tree.topLevelItem(0).child(index).text(0)
            for index in range(editor.tree.topLevelItem(0).childCount())
        )
        assert window.planar_page.controller.setup.setup_id != common_id
        assert window.planar_page.controller.operations[0].setup_id == window.planar_page.controller.setup.setup_id
        assert window.curve_page.controller.setup.setup_id == common_id
        editor._execute_command("set_machine", "builtin.machine.generic_xyzac_reference.v1")
        editor.controller._setup = replace(editor.controller.setup, name="Planar local")
        window._leave_local_setup_editor()
        assert window.planar_page.controller.setup.name == "Planar local"
        assert (
            window.planar_page.controller.setup.machine.resource_id
            == "builtin.machine.generic_xyzac_reference.v1"
        )
        assert window.tube_page.controller.setup.machine.resource_id != window.planar_page.controller.setup.machine.resource_id
        assert window.tube_page.controller.setup.name != "Planar local"
        assert window._setup_panels["planar"].publish_button.isEnabled()
        assert "Generic XYZAC Reference" in window._setup_panels["planar"].resources.text()
        assert "builtin.machine.generic_xyzac_reference.v1" not in window._setup_panels["planar"].resources.text()

        monkeypatch.setattr(QMessageBox, "question", lambda *_args: QMessageBox.Yes)
        window._publish_workbench_setup("planar")
        assert window.tube_page.controller.setup.name != "Planar local"
        assert window.planar_page.controller.setup.name == "Planar local"
        assert window.curve_page.controller.setup == window.tube_page.controller.setup

        window._use_common_setup("planar")
        assert window.planar_page.controller.setup == window.tube_page.controller.setup
        assert window.planar_page.controller.operations[0].setup_id == common_id
        assert window._setup_panels["planar"].copy_button.isEnabled()
    finally:
        window.close()


def test_local_setup_survives_project_save_and_reopen(tmp_path) -> None:
    step = make_two_body_step(tmp_path)
    window = MainWindow(
        http_port=0,
        model_viewer_factory=lambda parent: TubeViewerStub(parent),
        result_viewer_factory=lambda parent: TubeViewerStub(parent),
    )
    try:
        window._commit_model(load_step(step))
        window._copy_common_to_workbench("curve")
        assert window._local_setup_editor is not None
        window._local_setup_editor.controller._setup = replace(
            window._local_setup_editor.controller.setup, name="Curve independent"
        )
        window._leave_local_setup_editor()
        project = window.save_project_to(tmp_path / "saved")
        payload = json.loads(Path(project["project_json"]).read_text(encoding="utf-8"))
        assert len(payload["setups"]) == 2
        assert payload["workbench"]["setup_bindings"]["curve"] != payload["workbench"][
            "setup_bindings"
        ]["common"]
        reopened = window.open_project(project["project_json"])
        assert reopened["workbench"]["setup_bindings"]["curve"] != reopened["workbench"][
            "setup_bindings"
        ]["common"]
        assert window.curve_page.controller.setup.name == "Curve independent"
        assert window.planar_page.controller.setup == window.tube_page.controller.setup
    finally:
        window.close()


def test_freeform_tool_change_station_survives_actual_project_save_and_reopen(tmp_path) -> None:
    step = make_two_body_step(tmp_path)
    window = MainWindow(
        http_port=0,
        model_viewer_factory=lambda parent: TubeViewerStub(parent),
        result_viewer_factory=lambda parent: TubeViewerStub(parent),
    )
    try:
        window._commit_model(load_step(step))
        station = ToolChangeStation(
            clearance_z_mm=180,
            cutter_xyz_mm=(130, 100, 80),
            exchange_xyz_mm=(140, 100, 80),
            purge_xyz_mm=(150, 100, 80),
            wipe_start_xyz_mm=(160, 100, 80),
            wipe_end_xyz_mm=(170, 100, 80),
            cutter_command="M98 P105",
        )
        window.freeform_page.controller.configure_tool_change_station(station)
        project = window.save_project_to(tmp_path / "with-station")
        payload = json.loads(Path(project["project_json"]).read_text(encoding="utf-8"))
        assert payload["workbench"]["freeform_controller_profile"][
            "tool_change_station"
        ]["cutter_command"] == "M98 P105"
        window.freeform_page.controller.configure_tool_change_station(None)
        window.open_project(project["project_json"])
        assert window.freeform_page.controller.controller_profile.tool_change_station == station
    finally:
        window.close()


def test_setup_sidebar_actions_remain_scrollable_on_short_window() -> None:
    window = MainWindow(
        http_port=0,
        model_viewer_factory=lambda parent: TubeViewerStub(parent),
        result_viewer_factory=lambda parent: TubeViewerStub(parent),
    )
    try:
        window.resize(1366, 768)
        window.show()
        window.enter_workbench("planar")
        APP.processEvents()
        panel = window._setup_panels["planar"]
        assert not panel.copy_button.visibleRegion().isEmpty()
        panel.setFixedHeight(360)
        APP.processEvents()
        assert panel.verticalScrollBar().maximum() > 0
        panel.ensureWidgetVisible(panel.publish_button)
        APP.processEvents()
        assert not panel.publish_button.visibleRegion().isEmpty()
    finally:
        window.close()
