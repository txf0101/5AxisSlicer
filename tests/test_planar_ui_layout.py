"""Long real product diagnostics must grow the scroll area without flattening fields."""

from dataclasses import replace
from itertools import combinations
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
from PyQt5.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.setup import IssueSeverity, ValidationIssue
from five_axis_slicer.manufacturing.toolpath import GeneratedResultStatus

from test_planar_ui import _app
from test_planar_ui_diagnostics import _page


@pytest.mark.parametrize("size", [(1366, 768), (1600, 900), (1920, 1080)])
@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("severity", [IssueSeverity.ERROR, IssueSeverity.WARNING])
def test_long_product_diagnostics_preserve_every_form_control_height(size, language, severity):
    page = _page(language)
    page.generate_button.click()
    result = page.controller.product_result(page.controller.operations[0].operation_id)
    codes = (
        (
            "planar.bead_envelope_outside_region",
            "planar.material_exceeds_solid_volume",
            "planar.support_travel_intersects_target_cad",
            "planar.spiral_bead_outside_cad",
        )
        if severity is IssueSeverity.ERROR
        else ("planar.spiral_cad_sampled", "planar.support_joint_schedule_unverified")
    )
    result = replace(
        result,
        validation=replace(
            result.validation, issues=tuple(ValidationIssue(code, severity) for code in codes)
        ),
        manifest=replace(
            result.manifest,
            status=GeneratedResultStatus(severity.value),
            ready_for_export=severity is IssueSeverity.WARNING,
            issues=codes,
        ),
    )
    with patch(
        "five_axis_slicer.planar_controller.generate_planar_path_product", return_value=result
    ):
        page.generate_button.click()
    page.resize(*size)
    page.show()
    _app().processEvents()

    fields = [
        widget
        for kind in (QComboBox, QDoubleSpinBox, QSpinBox)
        for widget in page.findChildren(kind)
    ]
    controls = [*fields, *page._labels.values()]
    for widget in controls:
        required = max(widget.sizeHint().height(), widget.minimumSizeHint().height())
        assert widget.height() >= required, (type(widget).__name__, widget.height(), required)
        assert widget.geometry().right() < page.editor_scroll.widget().width()
    for left, right in combinations(controls, 2):
        assert not left.geometry().intersects(right.geometry()), (left.geometry(), right.geometry())
    assert page.title_label.width() >= page.title_label.sizeHint().width()
    assert page.title_label.height() >= page.title_label.sizeHint().height()
    assert page.editor_scroll.horizontalScrollBar().maximum() == 0
    assert page.editor_scroll.verticalScrollBar().maximum() > 0
    assert all(code in page.issues_label.text() for code in codes)

    page.editor_scroll.verticalScrollBar().setValue(
        page.editor_scroll.verticalScrollBar().maximum()
    )
    _app().processEvents()
    for widget in fields:
        assert widget.height() >= max(widget.sizeHint().height(), widget.minimumSizeHint().height())
    page.close()
