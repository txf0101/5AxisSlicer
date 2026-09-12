"""Capture real Qt/OpenGL outcomes after AUD-02; no injected product states."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("FIVE_AXIS_RENDER_BACKEND", "opengl")
sys.path[:0] = [
    str(Path(__file__).resolve().parents[1] / "src"),
    str(Path(__file__).resolve().parents[1] / "tests"),
]

from PyQt5.QtWidgets import QApplication

from five_axis_slicer.manufacturing.resources import GENERIC_PLA_175, ResourceSnapshot
from five_axis_slicer.planar_controller import PlanarController
from five_axis_slicer.planar_ui import PlanarPage
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.tube_ui import TubeSetupPage
from planar_p06_real_model_evidence import _parameters, _setup
from planar_p02_ui_evidence import _button_audit
from test_tube_generation_context import controller as tube_controller


def _page(model, body, first, last):
    setup = replace(
        _setup(model, body),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("aud-02-ui-offline-pla")
        ),
    )
    controller = PlanarController(model, setup=setup)
    operation = controller.create_operation("planar_zigzag", operation_id="audit-ui")
    controller.configure_operation(
        operation_id=operation.operation_id, body_id=body, parameters=_parameters(first, last)
    )
    page = PlanarPage(controller=controller)
    page.show()
    QApplication.processEvents()
    page._generate()
    QApplication.processEvents()
    return page


def _capture(page, path, language, size, kind):
    page.set_language(language)
    page.resize(*size)
    if hasattr(page.viewer, "set_standard_view"):
        page.viewer.set_standard_view("top")
        if hasattr(page.viewer, "set_model_visible"):
            page.viewer.set_model_visible(False)
        page.viewer.fit_view()
    QApplication.processEvents()
    page.editor_scroll.verticalScrollBar().setValue(page.editor_scroll.verticalScrollBar().maximum())
    QApplication.processEvents()
    if not page.grab().save(str(path)):
        raise RuntimeError(f"could not save {path}")
    return {
        "kind": kind,
        "language": language,
        "size": list(size),
        "status": page.status_label.text(),
        "diagnostics": page.issues_label.text(),
        "export_enabled": page.export_button.isEnabled(),
        "screenshot": path.name,
        **_button_audit(page),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="docs/reviews/evidence/2026-09-12_audit_fixes/ui")
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    model = load_step(Path("example/三叶扇/Supportless_sample.stp").resolve())
    page = _page(model, "body_002", 60, 60.6)
    assert page.export_button.isEnabled()
    records = []
    for language in ("zh", "en"):
        for size in ((1366, 768), (1600, 900), (1920, 1080)):
            records.append(
                _capture(page, output / f"fan-{language}-{size[0]}.png", language, size, "normal")
            )
    # An applied spacing change must withdraw the previous result's qualification.
    page.line_spacing_spin.setValue(0.5)
    page.apply_button.click()
    records.append(_capture(page, output / "stale-zh.png", "zh", (1600, 900), "stale"))
    assert not page.export_button.isEnabled()
    page.close()
    rectangle = Path(
        "docs/reviews/evidence/2026-09-12_project_audit/frozen_cases/analytic/rectangle_8x6x1.step"
    )
    page = _page(load_step(rectangle.resolve()), "body_001", 0.5, 0.5)
    page.layer_height_spin.setValue(0.5)
    page.line_spacing_spin.setValue(0.2)
    page.apply_button.click()
    page._generate()
    for language in ("zh", "en"):
        records.append(
            _capture(page, output / f"overfill-{language}.png", language, (1600, 900), "blocked")
        )
        assert not page.export_button.isEnabled()
        assert "planar.material_exceeds_solid_volume" in page.issues_label.text()
    page.line_spacing_spin.setValue(0.6)
    page.apply_button.click()
    page._generate()
    records.append(_capture(page, output / "recovered-zh.png", "zh", (1600, 900), "recovered"))
    assert page.export_button.isEnabled()
    page.close()
    model = load_step(
        Path(
            "docs/reviews/evidence/2026-09-12_project_audit/tube_probe/ready_setup/analytic_straight_tube.step"
        ).resolve()
    )
    ctrl = tube_controller(model)
    result = ctrl.generate_operation("tube")
    tube = TubeSetupPage()
    tube.set_controller(ctrl, model)
    tube.select_setup_node("operation:tube")
    tube.show()
    for language, size in (("zh", (1366, 768)), ("en", (1920, 1080))):
        tube.set_language(language)
        tube.resize(*size)
        tube.editor_scroll.verticalScrollBar().setValue(
            tube.editor_scroll.verticalScrollBar().maximum()
        )
        app.processEvents()
        name = f"tube-{language}.png"
        assert tube.grab().save(str(output / name))
        records.append(
            {
                "kind": "tube-generated",
                "language": language,
                "size": list(size),
                "screenshot": name,
                "export_enabled": tube.operation_export_button.isEnabled(),
                "status": tube.operation_generation_status.text(),
                "readback": result.readback.to_json(),
            }
        )
        assert tube.operation_export_button.isEnabled()
    tube.close()
    (output / "summary.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "screenshots": len(records),
                "issues": sum(bool(r.get("collisions")) for r in records),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
