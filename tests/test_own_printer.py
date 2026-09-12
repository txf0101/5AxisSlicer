from dataclasses import replace
import json
import math
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from PyQt5.QtWidgets import QApplication, QWidget
from five_axis_slicer import machine_profile_ui
from five_axis_slicer.machine_profile_ui import (
    RotaryAxisWordDialog,
    read_machine,
    remap_rotary_axis_words,
    save_copy,
)
from five_axis_slicer.manufacturing.library import UserResourceLibrary
from five_axis_slicer.manufacturing.machine import CARTESIAN_REFERENCE
from five_axis_slicer.manufacturing.own_printer import (
    OWN_AC_ID,
    default_printer_setup,
    own_ac_document,
    own_ac_profile,
)
from five_axis_slicer.manufacturing.setup import ManufacturingSetup
from five_axis_slicer.tube_controller import TubeSetupController
from five_axis_slicer.tube_ui import TubeSetupPage


def test_paper_values_unknown_limits_and_portable_file():
    profile = read_machine(json.dumps(own_ac_document()))
    assert profile == own_ac_profile()
    assert profile.reference_only
    assert profile.joint_map["A"].soft_limit_max == math.pi
    assert profile.joint_map["C"].soft_limit_min == -2 * math.pi
    assert profile.build_surfaces[0].diameter_mm == 180
    for joint in profile.joints:
        assert joint.max_velocity is None
        assert joint.max_acceleration is None
        if joint.joint_type == "linear":
            assert joint.soft_limit_min is None and joint.soft_limit_max is None
    settings = own_ac_document()["process_reference"]
    assert settings["layer_height_mm"] == 0.2
    assert settings["materials"][2]["nozzle_c"] == 275
    assert settings["pla_base_multimaterial_bed_c"] == 45


@pytest.mark.parametrize(
    "payload",
    [
        {"printer_model": "external-format"},
        [],
        {"schema_version": 2, "resource_type": "machine", "profile": {}},
    ],
)
def test_foreign_or_invalid_file_is_rejected(payload):
    with pytest.raises(ValueError):
        read_machine(json.dumps(payload))


def test_saved_projects_keep_machine_or_explicit_empty_setup():
    controller = TubeSetupController(setup=default_printer_setup())
    assert (
        TubeSetupController.from_json(controller.to_json()).machine_profile().profile_id
        == OWN_AC_ID
    )
    controller.select_machine(CARTESIAN_REFERENCE)
    assert (
        TubeSetupController.from_json(controller.to_json()).machine_profile() == CARTESIAN_REFERENCE
    )
    empty = TubeSetupController(setup=ManufacturingSetup())
    assert TubeSetupController.from_json(empty.to_json()).setup.machine is None


def test_ui_default_customize_reload_and_apply(tmp_path):
    app = QApplication.instance() or QApplication([])
    library = UserResourceLibrary(tmp_path / "library")
    page = TubeSetupPage(viewer_factory=QWidget, resource_library=library)
    try:
        assert page.controller.machine_profile().profile_id == OWN_AC_ID
        assert page.machine_combo.currentData() == OWN_AC_ID
        copy = save_copy(page, replace(own_ac_profile(), name="Custom machine"), "Shop AC")
        assert copy.profile_id != OWN_AC_ID
        assert library.load("machine", copy.profile_id) == copy
        assert page.controller.machine_profile().profile_id == OWN_AC_ID
        page._apply_machine()
        assert page.controller.machine_profile() == copy
        page.reload_resource_library()
        assert page.machine_combo.currentData() == copy.profile_id
        restored = TubeSetupController.from_json(
            page.controller.to_json(), resource_library=library
        )
        assert restored.machine_profile() == copy
        for language in ("zh", "en"):
            page.set_language(language)
            assert all(button.text() for button in page.machine_file_buttons)
        app.processEvents()
    finally:
        page.close()


def test_rotary_axis_word_dialog_exposes_only_output_words_and_read_only_kinematics():
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.language = "zh"
    dialog = RotaryAxisWordDialog(parent, own_ac_profile())
    try:
        assert set(dialog.axis_word_edits) == {"A", "C"}
        assert all(editor.maxLength() == 1 for editor in dialog.axis_word_edits.values())
        assert "不变" in dialog.help_label.text()
        assert "运动学" in dialog.help_label.text()
        labels = {label.text() for label in dialog.findChildren(machine_profile_ui.QLabel)}
        assert "(1, 0, 0)" in labels
        assert "(0, 0, 1)" in labels
        assert "工件侧" in labels
        assert {
            button.text() for button in dialog.findChildren(machine_profile_ui.QPushButton)
        } >= {
            "保存",
            "取消",
        }

        dialog.axis_word_edits["A"].setText("u")
        dialog.axis_word_edits["C"].setText("w")
        mapped = dialog.mapped_profile()

        assert mapped.joint_map["A"].post_axis_map.word == "U"
        assert mapped.joint_map["C"].post_axis_map.word == "W"
        assert mapped.joint_map["A"].axis_direction == (1.0, 0.0, 0.0)
        assert mapped.joint_map["C"].motion_side == "workpiece"
        assert mapped.joint_map["A"].post_axis_map.output_unit == "deg"
    finally:
        dialog.close()
        parent.close()
        app.processEvents()

    english_parent = QWidget()
    english_parent.language = "en"
    english_dialog = RotaryAxisWordDialog(english_parent, own_ac_profile())
    try:
        assert "kinematics remain unchanged" in english_dialog.help_label.text()
        labels = {label.text() for label in english_dialog.findChildren(machine_profile_ui.QLabel)}
        assert "Axis direction (read-only)" in labels
        assert "Motion side (read-only)" in labels
    finally:
        english_dialog.close()
        english_parent.close()
        app.processEvents()


def test_rotary_axis_word_remap_rejects_incomplete_invalid_and_duplicate_words():
    profile = own_ac_profile()
    with pytest.raises(ValueError, match="every rotary joint"):
        remap_rotary_axis_words(profile, {"A": "U"})
    with pytest.raises(ValueError, match="invalid machine profile"):
        remap_rotary_axis_words(profile, {"A": "AA", "C": "W"})
    with pytest.raises(ValueError, match="duplicate_word"):
        remap_rotary_axis_words(profile, {"A": "U", "C": "U"})


def test_rotary_axis_word_action_saves_selects_and_applies_through_page_command(
    tmp_path, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    library = UserResourceLibrary(tmp_path / "library")
    page = TubeSetupPage(viewer_factory=QWidget, resource_library=library)
    try:
        mapped = remap_rotary_axis_words(own_ac_profile(), {"A": "U", "C": "W"})
        monkeypatch.setattr(machine_profile_ui, "edit_rotary_axis_words", lambda *_: mapped)
        monkeypatch.setattr(
            machine_profile_ui.QInputDialog,
            "getText",
            lambda *_args, **_kwargs: ("DIY U/W", True),
        )

        machine_profile_ui.file_action(page, "axis_words")

        applied = page.controller.machine_profile()
        assert applied.profile_id.startswith("user.machine.")
        assert applied.name == "DIY U/W"
        assert applied.joint_map["A"].post_axis_map.word == "U"
        assert applied.joint_map["C"].post_axis_map.word == "W"
        assert library.load("machine", applied.profile_id) == applied
        page._update_machine_detail()
        assert "A→U" in page.machine_detail.text()
        assert "C→W" in page.machine_detail.text()
    finally:
        page.close()
        app.processEvents()
