"""Exercise returned Error products, warnings and input gates through the Planar page."""

from dataclasses import replace
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.resources import GENERIC_PLA_175, ResourceSnapshot
from five_axis_slicer.manufacturing.setup import IssueSeverity, ValidationIssue
from five_axis_slicer.manufacturing.toolpath import GeneratedResultStatus
from five_axis_slicer.planar_ui import PlanarPage

from test_planar_ui import _app, _path_controller
from test_tube_ui import TubeViewerStub


def _page(language="zh", operation_type="planar_thin_wall"):
    _app()
    page = PlanarPage(controller=_path_controller(), viewer_factory=TubeViewerStub)
    page.operation_type_combo.setCurrentIndex(page.operation_type_combo.findData(operation_type))
    page.create_button.click()
    page.first_layer_spin.setValue(0.0)
    page.last_layer_spin.setValue(0.0)
    page.layer_height_spin.setValue(0.5)
    page.feedrate_spin.setValue(100.0)
    page.travel_feedrate_spin.setValue(100.0)
    page.apply_button.click()
    page.set_language(language)
    return page


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize(
    "code,phrases",
    [
        ("planar.bead_envelope_outside_region", ("计入道宽", "width is included")),
        (
            "planar.material_exceeds_solid_volume",
            ("超过目标实体体积", "exceeds the target solid volume"),
        ),
        ("planar.support_travel_intersects_target_cad", ("空移穿过", "travel intersects")),
        ("planar.spiral_bead_outside_cad", ("层间过渡", "between layers")),
    ],
)
def test_returned_error_product_reports_export_block_and_localized_cause(language, code, phrases):
    page = _page(language)
    page.generate_button.click()
    good = page.controller.product_result(page.controller.operations[0].operation_id)
    assert good.exportable
    issue = ValidationIssue(code, IssueSeverity.ERROR, "point-12", {"maximum_mm": 0.3})
    blocked = replace(
        good,
        validation=replace(good.validation, issues=(issue,)),
        manifest=replace(
            good.manifest,
            status=GeneratedResultStatus.ERROR,
            ready_for_export=False,
            issues=(code,),
        ),
        gcode="",
    )
    with patch(
        "five_axis_slicer.planar_controller.generate_planar_path_product", return_value=blocked
    ):
        page.generate_button.click()
    assert not page.export_button.isEnabled()
    assert ("禁止导出" if language == "zh" else "Export is blocked") in page.status_label.text()
    assert code in page.issues_label.text()
    assert phrases[language == "en"] in page.issues_label.text()
    assert "point-12" in page.issues_label.text()
    assert "0.3 mm" in page.issues_label.text()
    assert ("可以生成" if language == "zh" else "Ready to generate") not in page.status_label.text()
    page.close()


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize(
    "code,phrases",
    [
        (
            "planar.support_joint_schedule_unverified",
            ("联合逐层次序", "combined part/support layer order"),
        ),
        ("planar.spiral_cad_sampled", ("离散实体采样", "discrete solid sampling")),
    ],
)
def test_warning_product_keeps_export_state_and_explains_limit(language, code, phrases):
    page = _page(language)
    page.generate_button.click()
    good = page.controller.product_result(page.controller.operations[0].operation_id)
    warning = replace(
        good,
        validation=replace(good.validation, issues=(ValidationIssue(code, IssueSeverity.WARNING),)),
        manifest=replace(good.manifest, status=GeneratedResultStatus.WARNING, issues=(code,)),
    )
    with patch(
        "five_axis_slicer.planar_controller.generate_planar_path_product", return_value=warning
    ):
        page.generate_button.click()
    assert page.export_button.isEnabled()
    assert ("警告" if language == "zh" else "warnings") in page.status_label.text()
    assert code in page.issues_label.text()
    assert phrases[language == "en"] in page.issues_label.text()
    page.close()


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize(
    "condition", ["missing_material", "unreviewed_material", "draft", "missing_part"]
)
def test_generate_is_disabled_before_click_for_incomplete_applied_setup(language, condition):
    page = _page(language)
    setup = page.controller.setup
    if condition == "missing_material":
        setup = replace(setup, material=None)
    elif condition == "unreviewed_material":
        setup = replace(setup, material=ResourceSnapshot.capture("material", GENERIC_PLA_175))
    elif condition == "draft":
        setup = replace(setup, draft_nodes=frozenset({"material"}))
    else:
        setup = replace(setup, assignments=replace(setup.assignments, part_body_ids=()))
    page.controller.mark_setup_changed(setup)
    page.refresh()
    with patch("five_axis_slicer.planar_controller.generate_planar_path_product") as generate:
        page.generate_button.click()
    generate.assert_not_called()
    assert not page.generate_button.isEnabled()
    assert ("已应用" if language == "zh" else "applied Setup") in page.status_label.text()
    assert page.generate_button.toolTip() == page.status_label.text()
    assert page.issues_label.text()
    page.close()


def test_exception_error_survives_language_switch_with_localized_reason():
    page = _page(operation_type="planar_spiral")
    page.generate_button.click()
    assert "禁止导出" in page.status_label.text()
    assert "planar.spiral_layers_insufficient" in page.issues_label.text()
    page.set_language("en")
    assert "Export is blocked" in page.status_label.text()
    assert "at least two adjacent layers" in page.status_label.text()
    assert "at least two adjacent layers" in page.issues_label.text()
    assert not page.export_button.isEnabled()
    page.close()
