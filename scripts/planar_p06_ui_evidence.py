"""Capture P06 Planar Qt evidence with the repository's real STEP sample."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("FIVE_AXIS_RENDER_BACKEND", "opengl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication

from five_axis_slicer.planar_controller import PlanarController  # noqa: E402
from five_axis_slicer.planar_ui import PlanarPage  # noqa: E402
from five_axis_slicer.step_loader import load_step  # noqa: E402
from planar_p02_ui_evidence import _button_audit, _controller  # noqa: E402


CASES = (
    ("planar_offset", "zh", 1366, 768, "top", False),
    ("planar_offset", "en", 1600, 900, "isometric", True),
    ("planar_thin_wall", "zh", 1600, 900, "top", False),
    ("planar_thin_wall", "en", 1920, 1080, "isometric", True),
    ("planar_spiral", "zh", 1920, 1080, "isometric", True),
    ("planar_spiral", "en", 1366, 768, "top", False),
)


def _page(model, body_id: str, operation_type: str, *, spiral_valid: bool = True) -> PlanarPage:
    setup = _controller(model, body_id, 60.0).setup
    page = PlanarPage(controller=PlanarController(model, setup=setup))
    index = page.operation_type_combo.findData(operation_type)
    if index < 0:
        raise RuntimeError(f"operation type is not present in UI: {operation_type}")
    page.operation_type_combo.setCurrentIndex(index)
    page.create_button.click()
    page.body_combo.setCurrentText(body_id)
    page.first_layer_spin.setValue(60.0)
    page.last_layer_spin.setValue(
        60.6 if operation_type == "planar_spiral" and spiral_valid else 60.0
    )
    page.layer_height_spin.setValue(0.6)
    page.bead_width_spin.setValue(0.6)
    page.line_spacing_spin.setValue(0.6)
    page.feedrate_spin.setValue(100.0)
    page.travel_feedrate_spin.setValue(100.0)
    page.wall_thickness_spin.setValue(1.2)
    page.offset_pass_count_spin.setValue(3)
    page.thin_wall_max_passes_spin.setValue(3)
    page.spiral_samples_spin.setValue(64)
    page.apply_button.click()
    page.show()
    QApplication.processEvents()
    return page


def _capture(page: PlanarPage, output: Path, filename: str, case: dict) -> dict:
    language, width, height = case["language"], case["width"], case["height"]
    page.set_language(language)
    page.resize(width, height)
    if hasattr(page.viewer, "set_model_visible"):
        page.viewer.set_model_visible(case["model_visible"])
    if hasattr(page.viewer, "set_standard_view"):
        page.viewer.set_standard_view(case["view"])
    if hasattr(page.viewer, "fit_view"):
        page.viewer.fit_view()
    QApplication.processEvents()
    path = output / filename
    if not page.grab().save(str(path)):
        raise RuntimeError(f"could not save {path}")
    return {
        **case,
        "screenshot": path.name,
        "rendered_size": [page.width(), page.height()],
        "status_text": page.status_label.text(),
        "export_enabled": page.export_button.isEnabled(),
        "path_segment_count": getattr(page.viewer, "visible_path_segment_count", None),
        "preview_source": str(getattr(page.viewer.gcode_preview, "source_path", "")),
        **_button_audit(page),
    }


def _normal_cases(app, model, body_id: str, output: Path) -> list[dict]:
    records = []
    for index, (operation, language, width, height, view, visible) in enumerate(CASES, 1):
        page = _page(model, body_id, operation)
        page._generate()
        app.processEvents()
        result = page.controller.product_result(page.controller.operations[-1].operation_id)
        if result is None or not result.exportable or not result.readback.passed:
            raise RuntimeError(f"{operation} did not produce an exportable read-back result")
        case = {
            "kind": "normal",
            "operation_type": operation,
            "language": language,
            "width": width,
            "height": height,
            "view": view,
            "model_visible": visible,
        }
        filename = f"{index:02d}_{operation}_{language}_{width}x{height}.png"
        records.append(_capture(page, output, filename, case))
        page.close()
    return records


def _error_recovery(app, model, body_id: str, output: Path) -> list[dict]:
    page = _page(model, body_id, "planar_spiral", spiral_valid=False)
    page._generate()
    app.processEvents()
    if "planar.spiral_layers_insufficient" not in page.status_label.text():
        raise RuntimeError("Spiral single-layer error was not visible in the UI")
    error = _capture(
        page,
        output,
        "07_planar_spiral_error_zh_1366x768.png",
        {
            "kind": "error",
            "operation_type": "planar_spiral",
            "language": "zh",
            "width": 1366,
            "height": 768,
            "view": "isometric",
            "model_visible": True,
        },
    )
    page.last_layer_spin.setValue(60.6)
    page.apply_button.click()
    page._generate()
    app.processEvents()
    result = page.controller.product_result(page.controller.operations[-1].operation_id)
    if result is None or not result.exportable:
        raise RuntimeError("Spiral did not recover after the layer range was corrected")
    recovered = _capture(
        page,
        output,
        "08_planar_spiral_recovered_en_1600x900.png",
        {
            "kind": "recovered",
            "operation_type": "planar_spiral",
            "language": "en",
            "width": 1600,
            "height": 900,
            "view": "top",
            "model_visible": False,
        },
    )
    page.close()
    return [error, recovered]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="example/三叶扇/Supportless_sample.stp")
    parser.add_argument("--body", default="body_002")
    parser.add_argument("--out", default="docs/reviews/evidence/2026-09-12_p06_planar/ui")
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    model_path = Path(args.model).resolve()
    model = load_step(model_path)
    cases = _normal_cases(app, model, args.body, output)
    cases.extend(_error_recovery(app, model, args.body, output))
    summary = {
        "schema_version": 1,
        "model": str(model_path),
        "body": args.body,
        "feedrate_mm_min": 100.0,
        "capture_kind": "Qt widget grab with the project OpenGL viewer",
        "desktop_automation_boundary": (
            "Direct Qt render captures; they are not human-like desktop click-through evidence."
        ),
        "cases": cases,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    bad_layout = any(
        case["collisions"] or any(not button["text_fits"] for button in case["buttons"].values())
        for case in cases
    )
    return 1 if bad_layout else 0


if __name__ == "__main__":
    raise SystemExit(main())
