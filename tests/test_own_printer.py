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
from five_axis_slicer.machine_profile_ui import read_machine, save_copy
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
