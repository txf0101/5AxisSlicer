from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QComboBox, QStyle, QToolTip  # noqa: E402
from test_tube_ui import TubeViewerStub  # noqa: E402

from five_axis_slicer.manufacturing.library import UserResourceLibrary  # noqa: E402
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_NOZZLE_0_4,
    get_builtin_material_profile,
)
from five_axis_slicer.manufacturing.setup import BUILD_CS_NODE, MODEL_CS_NODE  # noqa: E402
from five_axis_slicer.tube_controller import (  # noqa: E402
    DraftNotFoundError,
    TubeSetupController,
)
from five_axis_slicer.tube_resource_selection import configured_nozzle_copy  # noqa: E402
from five_axis_slicer.tube_ui import TubeSetupPage  # noqa: E402
from five_axis_slicer.tube_ui_text import (  # noqa: E402
    TUBE_HELP_BINDINGS,
    TUBE_TEXT,
    apply_tube_help,
)


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app: QApplication) -> Iterator[TubeSetupPage]:
    with tempfile.TemporaryDirectory() as tmp:
        widget = TubeSetupPage(
            viewer_factory=TubeViewerStub,
            resource_library=UserResourceLibrary(Path(tmp)),
        )
        yield widget
        widget.close()
        widget.deleteLater()
        app.processEvents()


def _measured_nozzle_fields() -> dict[str, object]:
    return {
        "interface": "M6×1",
        "length_mm": 12.5000004,
        "construction_material": "brass",
        "flow_category": "standard",
        "temperature_limit_c": 300.0,
        "wear_resistance_rating": "standard",
        "outer_profile_rz_mm": ((0.2, 0.0), (3.0, 2.0), (3.0, 12.5000004)),
    }


def test_nozzle_help_explains_input_and_preserves_edits_on_language_change(
    page: TubeSetupPage,
) -> None:
    help_text = page.nozzle_interface.toolTip()
    assert help_text == page.nozzle_interface_label.toolTip()
    assert "M6×1" in help_text
    assert "未知时留空" in help_text
    assert "只检查文本非空" in help_text
    assert page.nozzle_interface.statusTip() == help_text
    assert page.nozzle_interface.accessibleDescription() == help_text
    assert page.nozzle_interface.placeholderText().startswith("例如")
    assert page.nozzle_length.value() == 0.0
    assert page.nozzle_length.specialValueText() == "未填写"

    page._apply_nozzle()
    editing_key = next(
        key for key in page._nozzle_profiles if key != page.nozzle_combo.currentData()
    )
    page.nozzle_combo.setCurrentIndex(page.nozzle_combo.findData(editing_key))
    page.nozzle_interface.setText("Vendor hotend R2")
    page.nozzle_length.setValue(17.25)
    page.material_review.setChecked(True)
    selected_key = page.nozzle_combo.currentData()
    state = page.controller.state_json()

    page.set_language("en")

    assert "mechanical connection" in page.nozzle_interface.toolTip()
    assert page.nozzle_interface.text() == "Vendor hotend R2"
    assert page.nozzle_length.value() == 17.25
    assert page.nozzle_combo.currentData() == selected_key
    assert page.material_review.isChecked()
    assert page.controller.state_json() == state


def test_nozzle_interface_hover_opens_the_native_tooltip(
    app: QApplication,
    page: TubeSetupPage,
) -> None:
    page.editor_stack.setCurrentWidget(page.nozzle_editor)
    page.resize(1600, 900)
    page.show()
    app.processEvents()

    QToolTip.hideText()
    QTest.mouseMove(page.nozzle_interface, page.nozzle_interface.rect().center())
    wake_delay = app.style().styleHint(QStyle.SH_ToolTip_WakeUpDelay)
    QTest.qWait(max(wake_delay, 0) + 200)

    assert QToolTip.isVisible()
    assert QToolTip.text() == page.nozzle_interface.toolTip()


def test_nozzle_length_accepts_typing_over_unset_label(
    app: QApplication,
    page: TubeSetupPage,
) -> None:
    page.editor_stack.setCurrentWidget(page.nozzle_editor)
    page.show()
    app.processEvents()

    QTest.mouseClick(page.nozzle_length.lineEdit(), Qt.LeftButton)
    app.processEvents()
    QTest.keyClicks(page.nozzle_length.lineEdit(), "12.5")
    assert page.nozzle_length.lineEdit().text() == "12.5"
    QTest.keyClick(page.nozzle_length.lineEdit(), Qt.Key_Return)
    app.processEvents()

    assert page.nozzle_length.value() == 12.5


def test_representative_setup_fields_expose_consistent_help(page: TubeSetupPage) -> None:
    widgets = (
        page.machine_combo,
        page.material_combo,
        page.material_review,
        page.mount_combo,
        page.coordinate_apply_button,
        page.coordinate_status,
        page.setup_status,
        page.issue_list,
    )
    for widget in widgets:
        assert widget.toolTip()
        assert widget.statusTip() == widget.toolTip()
        assert widget.accessibleDescription() == widget.toolTip()

    page._coordinate_node = MODEL_CS_NODE
    apply_tube_help(page)
    assert "Source CS" in page.coordinate_inputs["origin"][1][0].toolTip()
    page._coordinate_node = BUILD_CS_NODE
    apply_tube_help(page)
    assert "Model CS" in page.coordinate_inputs["origin"][1][0].toolTip()
    assert "局部 +X" in page.placement_spins["dx"].toolTip()
    assert "局部 X 轴" in page.placement_spins["rx"].toolTip()
    for key, label in page.placement_labels.items():
        assert label.toolTip() == page.placement_spins[key].toolTip()
        assert label.statusTip() == label.toolTip()
        assert label.accessibleDescription() == label.toolTip()
    assert page.coordinate_inputs["origin"][0].itemData(0, Qt.ToolTipRole)


def test_bilingual_help_catalog_and_static_bindings_are_complete(page: TubeSetupPage) -> None:
    assert TUBE_TEXT["zh"].keys() == TUBE_TEXT["en"].keys()
    for _key, control_names in TUBE_HELP_BINDINGS:
        for control_name in control_names:
            assert getattr(page, control_name).toolTip()


def test_part_role_item_help_keeps_stable_role_data(page: TubeSetupPage) -> None:
    combo = QComboBox(page)
    for role in ("part", "ignore", "unassigned"):
        combo.addItem(role, role)
    combo.setCurrentIndex(combo.findData("ignore"))
    page._role_combos = {"body": combo}

    apply_tube_help(page)
    page.set_language("en")

    assert combo.currentData() == "ignore"
    tooltip = combo.itemData(combo.findData("ignore"), Qt.ToolTipRole)
    assert "explicitly exclude" in tooltip.lower()


def test_switching_nozzle_profiles_synchronises_unknown_and_measured_fields(
    app: QApplication,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        library = UserResourceLibrary(Path(tmp))
        measured = configured_nozzle_copy(GENERIC_NOZZLE_0_4, _measured_nozzle_fields())
        library.save(measured)
        page = TubeSetupPage(viewer_factory=TubeViewerStub, resource_library=library)
        try:
            page.nozzle_combo.setCurrentIndex(page.nozzle_combo.findData(measured.resource_id))
            app.processEvents()
            assert page.nozzle_interface.text() == "M6×1"
            assert page.nozzle_length.value() == 12.5
            assert page.nozzle_collision.isChecked()
            page._apply_nozzle()
            assert page.controller.setup.nozzle is not None
            assert page.controller.setup.nozzle.resource_id == measured.resource_id
            errors: list[str] = []
            page.error_raised.connect(errors.append)
            page.nozzle_length.setValue(13.0)
            page._apply_nozzle()
            assert "先取消勾选并应用" in errors[-1]

            builtin_key = next(
                key for key, profile in page._nozzle_profiles.items() if profile.is_builtin
            )
            page.nozzle_combo.setCurrentIndex(page.nozzle_combo.findData(builtin_key))
            app.processEvents()
            assert page.nozzle_interface.text() == ""
            assert page.nozzle_length.value() == 0.0
            assert not page.nozzle_collision.isChecked()
        finally:
            page.close()
            page.deleteLater()
            app.processEvents()


def test_applying_machine_preserves_pending_nozzle_editor(page: TubeSetupPage) -> None:
    editing_key = list(page._nozzle_profiles)[1]
    page.nozzle_combo.setCurrentIndex(page.nozzle_combo.findData(editing_key))
    page.nozzle_interface.setText("Vendor hotend R2")
    page.nozzle_length.setValue(17.25)

    page._apply_machine()

    assert page.nozzle_combo.currentData() == editing_key
    assert page.nozzle_interface.text() == "Vendor hotend R2"
    assert page.nozzle_length.value() == 17.25


def test_automation_nozzle_selection_synchronises_editor(page: TubeSetupPage) -> None:
    page.nozzle_interface.setText("stale-A")
    page.nozzle_length.setValue(11.0)

    page.select_builtin_resource("nozzle", "0.6")

    selected = page._nozzle_profiles[str(page.nozzle_combo.currentData())]
    assert selected.orifice_diameter_mm == 0.6
    assert page.nozzle_interface.text() == ""
    assert page.nozzle_length.value() == 0.0


def test_material_review_follows_the_selected_profile(page: TubeSetupPage) -> None:
    page.material_review.setChecked(True)
    current_key = page.material_combo.currentData()
    next_key = next(key for key in page._material_profiles if key != current_key)

    page.material_combo.setCurrentIndex(page.material_combo.findData(next_key))

    assert not page.material_review.isChecked()


def test_controller_switch_synchronises_material_review(page: TubeSetupPage) -> None:
    reviewed = get_builtin_material_profile("PLA").reviewed_copy("reviewed-pla")
    reviewed_controller = TubeSetupController(resource_library=page.resource_library)
    reviewed_controller.select_material(reviewed)

    page.set_controller(reviewed_controller, None)

    assert page.material_review.isChecked()

    pending_controller = TubeSetupController(resource_library=page.resource_library)
    pending_controller.select_material(get_builtin_material_profile("PETG"))
    page.set_controller(pending_controller, None)

    assert not page.material_review.isChecked()


def test_language_change_preserves_unconfirmed_coordinate_candidate(
    page: TubeSetupPage,
) -> None:
    page._begin_coordinate_editor(MODEL_CS_NODE)
    combo = page.coordinate_inputs["origin"][0]
    combo.setCurrentIndex(combo.findData({"kind": "pick_vertex"}))
    assert "origin" in page._coordinate_control_dirty

    page.set_language("en")

    assert page.coordinate_inputs["origin"][0].currentData() == {"kind": "pick_vertex"}
    assert "origin" in page._coordinate_control_dirty


def test_coordinate_value_signal_requires_reconfirm_before_apply(page: TubeSetupPage) -> None:
    page._begin_coordinate_editor(MODEL_CS_NODE)
    for component in ("origin", "z", "x"):
        page._confirm_coordinate_component(component)
    page._apply_coordinate()
    applied = page.controller.setup.model_coordinate_system
    assert applied is not None

    page._begin_coordinate_editor(MODEL_CS_NODE)
    origin_x = page.coordinate_inputs["origin"][1][0]
    origin_x.setValue(origin_x.value() + 1.0)
    assert "origin" in page._coordinate_control_dirty

    page._apply_coordinate()

    assert "重新确认" in page.coordinate_feedback.text()
    assert page.controller.setup.model_coordinate_system is applied


def test_coordinate_cancel_restores_applied_values_and_removes_draft(
    page: TubeSetupPage,
) -> None:
    page._begin_coordinate_editor(MODEL_CS_NODE)
    for component in ("origin", "z", "x"):
        page._confirm_coordinate_component(component)
    page._apply_coordinate()

    page._begin_coordinate_editor(MODEL_CS_NODE)
    origin_x = page.coordinate_inputs["origin"][1][0]
    origin_x.setValue(9.0)
    page._cancel_coordinate()

    assert origin_x.value() == 0.0
    assert not page._coordinate_control_dirty
    with pytest.raises(DraftNotFoundError):
        page.controller.coordinate_draft(MODEL_CS_NODE)
