"""Capture P07 support UI states on a reproducible floating-beam STEP."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("FIVE_AXIS_RENDER_BACKEND", "opengl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication, QPushButton

from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_PLA_175,
    ResourceSnapshot,
)
from five_axis_slicer.planar_controller import PlanarController  # noqa: E402
from five_axis_slicer.planar_ui import PlanarPage  # noqa: E402
from five_axis_slicer.step_loader import load_step  # noqa: E402
from planar_p02_ui_evidence import _button_audit  # noqa: E402
from planar_p07_real_model_evidence import (  # noqa: E402
    _setup,
    _sha256,
    _write_floating_beam,
)


READY_CASES = (
    ("grid", "zh", 1366, 768, "isometric", True),
    ("lines", "en", 1600, 900, "top", False),
    ("grid", "en", 1920, 1080, "isometric", True),
)


def _reviewed_setup(model, body_id: str):
    """Use an applied material-review snapshot so UI evidence crosses the current gate."""
    base = _setup(model, body_id)
    material = GENERIC_PLA_175.reviewed_copy("planar-p07-ui-evidence-material")
    return replace(base, material=ResourceSnapshot.capture("material", material))


def _page(
    model,
    body_id: str,
    *,
    pattern: str = "grid",
    bead_width_mm: float = 0.6,
) -> PlanarPage:
    page = PlanarPage(controller=PlanarController(model, setup=_reviewed_setup(model, body_id)))
    operation_index = page.operation_type_combo.findData("planar_support")
    if operation_index < 0:
        raise RuntimeError("planar_support is not present in the Planar operation selector")
    page.operation_type_combo.setCurrentIndex(operation_index)
    page.create_button.click()
    page.body_combo.setCurrentText(body_id)
    page.first_layer_spin.setValue(0.5)
    page.last_layer_spin.setValue(3.0)
    page.layer_height_spin.setValue(0.5)
    page.bead_width_spin.setValue(bead_width_mm)
    page.line_spacing_spin.setValue(0.6)
    page.feedrate_spin.setValue(100.0)
    page.travel_feedrate_spin.setValue(100.0)
    page.retract_length_spin.setValue(1.0)
    page.support_angle_spin.setValue(45.0)
    page.support_xy_gap_spin.setValue(0.0)
    page.support_z_gap_spin.setValue(0.0)
    page.support_line_spacing_spin.setValue(1.0)
    page.support_interface_layers_spin.setValue(2)
    page.support_interface_spacing_spin.setValue(0.6)
    pattern_index = page.support_pattern_combo.findData(pattern)
    if pattern_index < 0:
        raise RuntimeError(f"support pattern is not present in the UI: {pattern}")
    page.support_pattern_combo.setCurrentIndex(pattern_index)
    page.apply_button.click()
    page.show()
    QApplication.processEvents()
    return page


def _product_record(page: PlanarPage) -> dict[str, object]:
    operation = page.controller.operations[-1]
    state = page.controller.product_state(operation.operation_id)
    result = page.controller.product_result(operation.operation_id)
    return {
        "operation_id": operation.operation_id,
        "operation_type": operation.operation_type,
        "product_status": None if state is None else state.status,
        "parameter_semantic_sha256": operation.semantic_sha256(),
        "result_retained": result is not None,
        "result_exportable": False if result is None else result.exportable,
        "readback_passed": False if result is None else result.readback.passed,
        "toolpath_point_count": 0 if result is None else len(result.toolpath.points),
    }


def _support_control_record(page: PlanarPage) -> dict[str, object]:
    return {
        "overhang_angle_deg": page.support_angle_spin.value(),
        "xy_gap_mm": page.support_xy_gap_spin.value(),
        "z_gap_mm": page.support_z_gap_spin.value(),
        "line_spacing_mm": page.support_line_spacing_spin.value(),
        "interface_layers": page.support_interface_layers_spin.value(),
        "interface_spacing_mm": page.support_interface_spacing_spin.value(),
        "pattern": page.support_pattern_combo.currentData(),
        "pattern_text": page.support_pattern_combo.currentText(),
        "labels": {
            key: page._labels[key].text()
            for key in (
                "support_angle",
                "support_xy_gap",
                "support_z_gap",
                "support_spacing",
                "support_interfaces",
                "support_interface_spacing",
                "support_pattern",
            )
        },
    }


def _viewport_audit(page: PlanarPage) -> dict[str, object]:
    clipped: dict[str, dict[str, object]] = {}
    for button in page.findChildren(QPushButton):
        visible = button.visibleRegion().boundingRect()
        if visible.isEmpty() or visible == button.rect():
            continue
        clipped[button.objectName() or button.text()] = {
            "button_rect": list(button.rect().getRect()),
            "visible_rect": list(visible.getRect()),
        }
    return {
        "clipped_visible_buttons": clipped,
        "horizontal_scroll_max": page.editor_scroll.horizontalScrollBar().maximum(),
    }


def _capture(page: PlanarPage, output: Path, filename: str, case: dict[str, object]) -> dict:
    language = str(case["language"])
    width, height = int(case["width"]), int(case["height"])
    page.set_language(language)
    page.resize(width, height)
    QApplication.processEvents()
    if hasattr(page.viewer, "set_model_visible"):
        page.viewer.set_model_visible(bool(case["model_visible"]))
    if hasattr(page.viewer, "set_standard_view"):
        page.viewer.set_standard_view(str(case["view"]))
    if hasattr(page.viewer, "fit_view"):
        page.viewer.fit_view()
    scroll_bar = page.editor_scroll.verticalScrollBar()
    scroll_bar.setValue(scroll_bar.maximum())
    QApplication.processEvents()
    path = output / filename
    if not page.grab().save(str(path)):
        raise RuntimeError(f"could not save {path}")
    preview = getattr(page.viewer, "gcode_preview", None)
    return {
        **case,
        "screenshot": path.name,
        "rendered_size": [page.width(), page.height()],
        "viewer_backend": getattr(page.viewer, "backend", "unknown"),
        "status_text": page.status_label.text(),
        "issues_text": page.issues_label.text(),
        "generate_enabled": page.generate_button.isEnabled(),
        "export_enabled": page.export_button.isEnabled(),
        "editor_scroll": [scroll_bar.value(), scroll_bar.maximum()],
        "path_segment_count": getattr(page.viewer, "visible_path_segment_count", None),
        "preview_source": "" if preview is None else str(preview.source_path),
        "support_controls": _support_control_record(page),
        "product": _product_record(page),
        **_viewport_audit(page),
        **_button_audit(page),
    }


def _require_ready(page: PlanarPage, context: str) -> None:
    record = _product_record(page)
    if (
        record["product_status"] not in {"ready", "warning"}
        or not record["result_exportable"]
        or not record["readback_passed"]
        or not page.export_button.isEnabled()
    ):
        raise RuntimeError(f"{context} did not reach an exportable Ready state: {record}")


def _ready_cases(app, model, body_id: str, output: Path) -> list[dict]:
    records = []
    for index, (pattern, language, width, height, view, visible) in enumerate(READY_CASES, 1):
        page = _page(model, body_id, pattern=pattern)
        page.generate_button.click()
        app.processEvents()
        _require_ready(page, f"{pattern} support")
        case = {
            "kind": "ready",
            "expected_state": "ready_or_warning",
            "pattern": pattern,
            "language": language,
            "width": width,
            "height": height,
            "view": view,
            "model_visible": visible,
        }
        records.append(
            _capture(
                page,
                output,
                f"{index:02d}_support_{pattern}_{language}_{width}x{height}_ready.png",
                case,
            )
        )
        page.close()
    return records


def _error_recovery(app, model, body_id: str, output: Path) -> list[dict]:
    page = _page(model, body_id, pattern="grid", bead_width_mm=20.0)
    page.generate_button.click()
    app.processEvents()
    record = _product_record(page)
    if (
        "planar.support_region_too_narrow" not in page.status_label.text()
        or page.export_button.isEnabled()
        or record["result_retained"]
    ):
        raise RuntimeError(
            f"The deliberate sub-bead support case was not visible as Error: {record}"
        )
    error = _capture(
        page,
        output,
        "04_support_error_en_1366x768.png",
        {
            "kind": "error",
            "expected_state": "visible_error_command_rolled_back",
            "pattern": "grid",
            "language": "en",
            "width": 1366,
            "height": 768,
            "view": "isometric",
            "model_visible": True,
            "trigger": "20 mm bead cannot fit the analytic 8 x 6 mm support domain",
            "transaction_boundary": (
                "The GUI command is atomic: the controller candidate carrying Error is rolled "
                "back, while the real diagnostic remains visible and export stays disabled."
            ),
        },
    )

    page.bead_width_spin.setValue(0.6)
    page.apply_button.click()
    page.generate_button.click()
    app.processEvents()
    _require_ready(page, "Error recovery")
    recovered = _capture(
        page,
        output,
        "05_support_error_recovered_zh_1600x900.png",
        {
            "kind": "recovered",
            "expected_state": "ready_or_warning",
            "recovered_from": "error",
            "pattern": "grid",
            "language": "zh",
            "width": 1600,
            "height": 900,
            "view": "top",
            "model_visible": False,
            "repair": "restore bead width to 0.6 mm, Apply, then Generate",
        },
    )
    page.close()
    return [error, recovered]


def _stale_recovery(app, model, body_id: str, output: Path) -> list[dict]:
    page = _page(model, body_id, pattern="lines")
    page.generate_button.click()
    app.processEvents()
    _require_ready(page, "Stale precursor")
    retained = page.controller.product_result(page.controller.operations[-1].operation_id)
    page.support_line_spacing_spin.setValue(1.2)
    page.apply_button.click()
    app.processEvents()
    record = _product_record(page)
    if (
        record["product_status"] != "stale"
        or page.export_button.isEnabled()
        or page.controller.product_result(page.controller.operations[-1].operation_id)
        is not retained
    ):
        raise RuntimeError(
            f"Support parameter change did not retain a disabled Stale result: {record}"
        )
    stale = _capture(
        page,
        output,
        "06_support_stale_en_1920x1080.png",
        {
            "kind": "stale",
            "expected_state": "stale",
            "pattern": "lines",
            "language": "en",
            "width": 1920,
            "height": 1080,
            "view": "top",
            "model_visible": True,
            "trigger": "support line spacing changed from 1.0 mm to 1.2 mm",
        },
    )

    page.generate_button.click()
    app.processEvents()
    _require_ready(page, "Stale recovery")
    recovered = _capture(
        page,
        output,
        "07_support_stale_recovered_zh_1600x900.png",
        {
            "kind": "recovered",
            "expected_state": "ready_or_warning",
            "recovered_from": "stale",
            "pattern": "lines",
            "language": "zh",
            "width": 1600,
            "height": 900,
            "view": "isometric",
            "model_visible": False,
            "repair": "Generate the changed operation again",
        },
    )
    page.close()
    return [stale, recovered]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture bilingual P07 Ready, Error, Stale, and recovery UI evidence."
    )
    parser.add_argument(
        "--out",
        default="docs/reviews/evidence/2026-09-12_p07_planar_support/ui",
    )
    args = parser.parse_args()

    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    model_path = _write_floating_beam(output / "input" / "analytic_floating_beam.step")
    model = load_step(model_path)
    if len(model.bodies) != 1:
        raise RuntimeError(f"Analytic UI STEP should contain one body, found {len(model.bodies)}")
    body_id = model.bodies[0].body_id
    app = QApplication.instance() or QApplication(sys.argv[:1])

    cases = _ready_cases(app, model, body_id, output)
    cases.extend(_error_recovery(app, model, body_id, output))
    cases.extend(_stale_recovery(app, model, body_id, output))
    summary = {
        "schema_version": 1,
        "task": "P07",
        "model": {
            "path": str(model_path),
            "sha256": _sha256(model_path),
            "selected_body": body_id,
            "analytic_bounds_mm": {
                "minimum": [4.0, 2.0, 2.2],
                "maximum": [12.0, 8.0, 3.2],
            },
        },
        "capture_kind": "Qt widget grab with the project OpenGL viewer",
        "desktop_automation_boundary": (
            "Direct Qt render captures; they are not human-like desktop click-through evidence."
        ),
        "cases": cases,
        "source_sha256": {
            str(path): _sha256(path)
            for path in (
                Path(__file__).resolve(),
                Path("src/five_axis_slicer/planar_ui.py").resolve(),
                Path("src/five_axis_slicer/algorithms/planar/support.py").resolve(),
                Path("src/five_axis_slicer/postprocessing/planar_product.py").resolve(),
            )
        },
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    bad_layout = any(
        case["collisions"]
        or case["clipped_visible_buttons"]
        or case["horizontal_scroll_max"]
        or any(not button["text_fits"] for button in case["buttons"].values())
        for case in cases
    )
    return 1 if bad_layout else 0


if __name__ == "__main__":
    raise SystemExit(main())
