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


@pytest.mark.parametrize(
    "language,title,yes,no",
    [
        ("zh", "制造设置", "是", "否"),
        ("en", "Manufacturing Setup", "Yes", "No"),
    ],
)
@pytest.mark.parametrize("answer", [QMessageBox.Yes, QMessageBox.No])
def test_setup_confirmation_language_and_answer(monkeypatch, language, title, yes, no, answer):
    from five_axis_slicer.workbench_setup_panel import confirm_setup_change
    from PyQt5.QtWidgets import QWidget

    def inspect_dialog(prompt):
        assert prompt.windowTitle() == title
        assert prompt.text() == "message"
        assert prompt.button(QMessageBox.Yes).text() == yes
        assert prompt.button(QMessageBox.No).text() == no
        assert prompt.defaultButton() == prompt.button(QMessageBox.No)
        assert prompt.escapeButton() == prompt.button(QMessageBox.No)
        return answer

    monkeypatch.setattr(QMessageBox, "exec_", inspect_dialog)
    parent = QWidget()
    assert confirm_setup_change(parent, language, "message") == (answer == QMessageBox.Yes)
    parent.close()


@pytest.mark.parametrize("key", LOCAL_WORKBENCHES)
def test_common_part_entry_does_not_reopen_previous_placement_draft(key) -> None:
    window = MainWindow(http_port=0, model_viewer_factory=TubeViewerStub)
    try:
        page = window.tube_page
        page.select_setup_node("placement")
        page.controller.discard_all_drafts()
        page.refresh()
        assert not page.controller.has_drafts
        window.enter_workbench(key)
        window._edit_workbench_setup_node(key, "part")
        assert page.tree.currentItem() is page._tree_items["part"]
        assert not page.controller.has_drafts
    finally:
        window.close()


@pytest.mark.parametrize(
    "key,operation_type",
    [
        ("planar", "planar_region"),
        ("curve", "curve_buildup"),
        ("rotary", "rotary_spiral"),
        ("freeform", "freeform_surface"),
    ],
)
def test_setup_changes_preserve_unapplied_operation_inputs(
    key, operation_type, monkeypatch
) -> None:
    window = MainWindow(http_port=0, model_viewer_factory=TubeViewerStub)
    try:
        page = getattr(window, f"{key}_page")
        page.controller.create_operation(operation_type)
        page.refresh()
        spin = (
            page._spins["feedrate_mm_min"] if key in {"curve", "freeform"} else page.feedrate_spin
        )
        original = spin.value()
        spin.setValue(original + 123)
        common = window.tube_page.controller.setup
        window.tube_page.controller.replace_setup(
            replace(common, name="Edited common Setup"), reason="test_common_edit"
        )
        window.enter_workbench(key)
        assert spin.value() == original + 123
        window.tube_page.controller.replace_setup(
            replace(common, name="Edited common Setup again"), reason="test_common_sync"
        )
        window._sync_common_workbenches()
        assert spin.value() == original + 123
        window._copy_common_to_workbench(key)
        assert spin.value() == original + 123
        editor = window._local_setup_editor
        editor.controller.replace_setup(
            replace(editor.controller.setup, name="Edited local Setup"), reason="test_local_edit"
        )
        assert window._commit_local_setup_editor()
        assert spin.value() == original + 123
        monkeypatch.setattr("five_axis_slicer.ui.confirm_setup_change", lambda *_args: True)
        window._use_common_setup(key)
        assert spin.value() == original + 123
        # Explicit reload still discards the draft and restores the saved operation.
        page.refresh()
        assert spin.value() == original
    finally:
        window.close()


@pytest.mark.parametrize("size", [(1366, 768), (1600, 900), (1920, 1080)])
@pytest.mark.parametrize("language", ["zh", "en"])
def test_setup_panels_fit_window_after_language_switch(size, language) -> None:
    window = MainWindow(http_port=0, model_viewer_factory=TubeViewerStub)
    try:
        window.open_manufacturing_setup()
        window.set_language(language)
        window.tube_page.tree.setCurrentItem(window.tube_page._tree_items["nozzle"])
        window.resize(*size)
        window.show()
        APP.processEvents()
        assert (window.width(), window.height()) == size
        display = window.current_state()["display"]
        assert display["client_size"] == list(size)
        assert display["frame_size"][0] >= size[0]
        assert display["frame_size"][1] >= size[1]
        assert display["device_pixel_ratio"] > 0
        assert display["screen_logical_dpi"] > 0
        page = window.tube_page
        for panel in (page.tree_panel, page.editor_panel):
            corner = panel.mapTo(window, panel.rect().bottomRight())
            assert window.rect().contains(corner)
        for button in (page.model_view_button, page.machine_view_button):
            assert button.parentWidget().rect().contains(button.geometry())
        viewport = page.editor_scroll.viewport()
        for control in (page.nozzle_interface, page.nozzle_length, page.nozzle_apply_button):
            assert control.mapTo(viewport, control.rect().topRight()).x() < viewport.width()
    finally:
        window.close()


@pytest.mark.parametrize("size", [(1366, 768), (1600, 900), (1920, 1080)])
@pytest.mark.parametrize("language", ["zh", "en"])
def test_rotary_selection_buttons_fit_translated_text(size, language) -> None:
    window = MainWindow(http_port=0, model_viewer_factory=TubeViewerStub)
    try:
        window.set_language(language)
        window.enter_workbench("rotary")
        window.resize(*size)
        window.show()
        APP.processEvents()
        assert (window.width(), window.height()) == size
        page = window.rotary_page
        for button in (page.pick_axis_button, page.pick_contours_button, page.pick_surfaces_button):
            assert button.width() >= button.sizeHint().width()
            assert button.parentWidget().rect().contains(button.geometry())
    finally:
        window.close()


@pytest.mark.parametrize("key", LOCAL_WORKBENCHES)
def test_first_local_editor_uses_current_language(key) -> None:
    window = MainWindow(http_port=0, model_viewer_factory=TubeViewerStub)
    try:
        window.set_language("en")
        assert window._local_setup_editor is None
        window._copy_common_to_workbench(key)
        editor = window._local_setup_editor
        assert editor is not None
        assert editor.language == "en"
        assert editor.model_view_button.text() == "Model View"
        assert editor.machine_apply_button.text() == "Apply"
        window.set_language("zh")
        assert editor.model_view_button.text() == "模型视图"
    finally:
        window.close()


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
            {
                "setup_bindings": {
                    "common": common.setup_id,
                    "planar": planar.setup_id,
                    "curve": planar.setup_id,
                }
            },
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
        assert (
            window.planar_page.controller.operations[0].setup_id
            == window.planar_page.controller.setup.setup_id
        )
        assert window.curve_page.controller.setup.setup_id == common_id
        editor._execute_command("set_machine", "builtin.machine.generic_xyzac_reference.v1")
        editor.controller._setup = replace(editor.controller.setup, name="Planar local")
        window._leave_local_setup_editor()
        assert window.planar_page.controller.setup.name == "Planar local"
        assert (
            window.planar_page.controller.setup.machine.resource_id
            == "builtin.machine.generic_xyzac_reference.v1"
        )
        assert (
            window.tube_page.controller.setup.machine.resource_id
            != window.planar_page.controller.setup.machine.resource_id
        )
        assert window.tube_page.controller.setup.name != "Planar local"
        assert window._setup_panels["planar"].publish_button.isEnabled()
        assert "Generic XYZAC Reference" in window._setup_panels["planar"].resources.text()
        assert (
            "builtin.machine.generic_xyzac_reference.v1"
            not in window._setup_panels["planar"].resources.text()
        )

        monkeypatch.setattr("five_axis_slicer.ui.confirm_setup_change", lambda *_args: True)
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


@pytest.mark.parametrize("common_view", [False, True])
def test_common_setup_view_survives_project_save_and_reopen(tmp_path, common_view) -> None:
    window = MainWindow(http_port=0, model_viewer_factory=TubeViewerStub)
    try:
        window._commit_model(load_step(make_two_body_step(tmp_path)))
        window.enter_workbench("tube")
        if common_view:
            window.open_manufacturing_setup()
        project = window.save_project_to(tmp_path / "saved-view")
        window.tube_page.set_common_setup_mode(not common_view)
        window.open_project(project["project_json"])
        assert window.tube_page.common_setup_view is common_view
        assert window.tube_page.create_operation_button.isHidden() is common_view
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
        assert (
            payload["workbench"]["setup_bindings"]["curve"]
            != payload["workbench"]["setup_bindings"]["common"]
        )
        reopened = window.open_project(project["project_json"])
        assert (
            reopened["workbench"]["setup_bindings"]["curve"]
            != reopened["workbench"]["setup_bindings"]["common"]
        )
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
        assert (
            payload["workbench"]["freeform_controller_profile"]["tool_change_station"][
                "cutter_command"
            ]
            == "M98 P105"
        )
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
