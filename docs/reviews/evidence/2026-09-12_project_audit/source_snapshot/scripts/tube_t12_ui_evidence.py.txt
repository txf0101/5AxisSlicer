"""Render reproducible Tube T12 UI evidence at supported desktop sizes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication, QPushButton, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.postprocessing.tube_product import TubeProductState
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.tube_controller import TubeSetupController
from five_axis_slicer.tube_ui import TubeSetupPage


CASES = (
    ("zh", 1366, 768, "indexed", "ready", "01-zh-1366x768-indexed.png"),
    ("zh", 1600, 900, "buildup", "stale", "02-zh-1600x900-buildup.png"),
    ("en", 1920, 1080, "continuous", "error", "03-en-1920x1080-continuous.png"),
)


def _controller(model) -> TubeSetupController:
    controller = TubeSetupController(model)
    for operation_type, operation_id, name in (
        ("tube_thin_wall_indexed", "indexed", "Indexed Thin Wall"),
        ("tube_buildup", "buildup", "Buildup and Base"),
        ("tube_continuous", "continuous", "Continuous Helix"),
    ):
        controller.create_operation(operation_type, operation_id=operation_id, name=name)
    controller._product_states = {
        operation_id: TubeProductState(operation_id, "a" * 64, status)
        for _language, _width, _height, operation_id, status, _filename in CASES
    }
    return controller


def _button_audit(page: TubeSetupPage) -> dict[str, object]:
    buttons = {
        button.objectName() or button.text(): button
        for button in page.findChildren(QPushButton)
        if button.isVisible()
    }
    bounds = {}
    for name, button in buttons.items():
        origin = button.mapTo(page, QPoint(0, 0))
        text_width = button.fontMetrics().horizontalAdvance(button.text())
        available_text_width = max(0, button.width() - 12)
        bounds[name] = {
            "x": origin.x(),
            "y": origin.y(),
            "width": button.width(),
            "height": button.height(),
            "text": button.text(),
            "text_width": text_width,
            "available_text_width": available_text_width,
            "text_fits": text_width <= available_text_width,
        }
    collisions = []
    items = list(buttons.items())
    for index, (left_name, left) in enumerate(items):
        left_origin = left.mapTo(page, QPoint(0, 0))
        left_rect = left.geometry().translated(left_origin - left.pos())
        for right_name, right in items[index + 1 :]:
            right_origin = right.mapTo(page, QPoint(0, 0))
            right_rect = right.geometry().translated(right_origin - right.pos())
            if left_rect.intersects(right_rect):
                collisions.append([left_name, right_name])
    return {"buttons": bounds, "collisions": collisions}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="example/pipe2/弯管新.stp")
    parser.add_argument("--out", default="outputs/tube_t12_ui")
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    model = load_step(Path(args.model).resolve())
    page = TubeSetupPage(viewer_factory=lambda parent: QWidget(parent))
    page.set_controller(_controller(model), model)
    page.show()
    records = []
    for language, width, height, operation_id, status, filename in CASES:
        page.set_language(language)
        page.select_setup_node(f"operation:{operation_id}")
        page.resize(width, height)
        app.processEvents()
        page.editor_scroll.verticalScrollBar().setValue(
            page.editor_scroll.verticalScrollBar().maximum()
        )
        app.processEvents()
        path = output / filename
        if not page.grab().save(str(path)):
            raise RuntimeError(f"Could not save {path}")
        audit = _button_audit(page)
        records.append(
            {
                "language": language,
                "requested_size": [width, height],
                "rendered_size": [page.width(), page.height()],
                "operation_id": operation_id,
                "product_status": status,
                "screenshot": path.name,
                **audit,
            }
        )
    summary = {"model": str(Path(args.model).resolve()), "cases": records}
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    page.close()
    has_layout_issue = any(
        case["collisions"]
        or any(not button["text_fits"] for button in case["buttons"].values())
        for case in records
    )
    return 1 if has_layout_issue else 0


if __name__ == "__main__":
    raise SystemExit(main())
