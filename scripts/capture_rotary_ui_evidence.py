"""Capture deterministic Rotary UI evidence without invoking VTK/OpenGL."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from PyQt5.QtCore import QPointF, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QPainter, QPen  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from five_axis_slicer.rotary_controller import RotaryController  # noqa: E402
from five_axis_slicer.rotary_ui import RotaryPage  # noqa: E402
from test_rotary_integration import _controller  # noqa: E402
from test_tube_ui import TubeViewerStub  # noqa: E402

ASSET_ROOT = ROOT / "docs" / "guides" / "assets" / "rotary" / "current_r01_r05"


class EvidenceViewer(TubeViewerStub):
    """Qt paint harness driven by the real generated preview segment payload."""

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#17212b"))
        painter.setRenderHint(QPainter.Antialiasing)
        margin = 55.0
        width = max(1.0, self.width() - margin * 2)
        height = max(1.0, self.height() - margin * 2)
        preview = self.gcode_preview
        segments = () if preview is None else tuple(preview.segments)
        projected = []
        for segment in segments:
            start = segment.start
            end = segment.end
            projected.append(
                (
                    (start[0] - start[1] * 0.45, start[2] + start[1] * 0.25),
                    (end[0] - end[1] * 0.45, end[2] + end[1] * 0.25),
                    segment.move_type,
                )
            )
        values = [point for line in projected for point in line[:2]]
        if values:
            min_x = min(point[0] for point in values)
            max_x = max(point[0] for point in values)
            min_y = min(point[1] for point in values)
            max_y = max(point[1] for point in values)
            scale = min(width / max(max_x - min_x, 1.0), height / max(max_y - min_y, 1.0))

            def screen(point) -> QPointF:
                return QPointF(
                    margin + (point[0] - min_x) * scale,
                    self.height() - margin - (point[1] - min_y) * scale,
                )

            for start, end, move_type in projected:
                color = QColor("#4cc9f0") if move_type == "extrude" else QColor("#f4a261")
                painter.setPen(QPen(color, 2.2 if move_type == "extrude" else 1.2))
                painter.drawLine(screen(start), screen(end))
        painter.setPen(QColor("#dbe7f3"))
        painter.drawText(20, 30, "Rotary toolpath · current generated preview payload")
        painter.setPen(QColor("#91a7bd"))
        painter.drawText(20, 50, f"Qt evidence paint harness · {len(segments)} segments")
        painter.end()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _page(tmp_root: Path, operation_type: str, language: str) -> RotaryPage:
    controller, operation, *_ = _controller(tmp_root, operation_type)
    controller.generate_operation(operation.operation_id)
    page = RotaryPage(controller=controller, viewer_factory=EvidenceViewer)
    page.set_language(language)
    page.refresh()
    return page


def _capture(
    page: RotaryPage,
    filename: str,
    size: tuple[int, int],
    *,
    scroll: int = 0,
) -> dict[str, object]:
    page.resize(*size)
    page.show()
    QApplication.processEvents()
    page.editor_scroll.verticalScrollBar().setValue(scroll)
    QApplication.processEvents()
    target = ASSET_ROOT / filename
    if not page.grab().save(str(target), "PNG"):
        raise RuntimeError(f"failed to save {target}")
    state = page.state_json()
    ui_state = state["ui"]
    page.hide()
    return {
        "width": size[0],
        "height": size[1],
        "language": page.language,
        "backend": "qt_evidence_paint_harness",
        "status": ui_state["status"],
        "export_enabled": ui_state["export_enabled"],
        "sha256": _sha256(target),
    }


def main() -> int:
    app = QApplication.instance() or QApplication([])
    del app
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    work = ROOT / "tmp" / "rotary_ui_evidence"
    spiral_zh = _page(work / "spiral-zh", "rotary_spiral", "zh")
    thin_en = _page(work / "thin-en", "rotary_thin_wall", "en")
    around_en = _page(work / "around-en", "rotary_around_part", "en")
    around_zh = _page(work / "around-zh", "rotary_around_part", "zh")
    records = {
        "01_rotary_overview_zh_1366x768.png": _capture(
            spiral_zh, "01_rotary_overview_zh_1366x768.png", (1366, 768)
        ),
        "02_rotary_coordinates_zh_1366x768.png": _capture(
            spiral_zh, "02_rotary_coordinates_zh_1366x768.png", (1366, 768), scroll=180
        ),
        "03_rotary_spiral_zh_1366x768.png": _capture(
            spiral_zh, "03_rotary_spiral_zh_1366x768.png", (1366, 768), scroll=520
        ),
        "04_rotary_thin_wall_en_1600x900.png": _capture(
            thin_en, "04_rotary_thin_wall_en_1600x900.png", (1600, 900), scroll=570
        ),
        "05_rotary_around_part_en_1920x1080.png": _capture(
            around_en, "05_rotary_around_part_en_1920x1080.png", (1920, 1080), scroll=420
        ),
        "06_rotary_cross_zero_zh_1366x768.png": _capture(
            around_zh, "06_rotary_cross_zero_zh_1366x768.png", (1366, 768), scroll=360
        ),
    }

    error_controller, error_operation, *_ = _controller(work / "limit-error", "rotary_spiral")
    error_operation = error_controller.configure_operation(
        operation_id=error_operation.operation_id,
        parameters=replace(
            error_operation.parameters,
            angular_velocity_rad_s=0.5,
            feedrate_mm_min=600.0,
            travel_feedrate_mm_min=1800.0,
        ),
    )
    error_controller.generate_operation(error_operation.operation_id)
    error_page = RotaryPage(controller=error_controller, viewer_factory=EvidenceViewer)
    error_page.set_language("zh")
    error_page.refresh()
    for row in range(error_page.issue_list.count()):
        payload = error_page.issue_list.item(row).data(Qt.UserRole)
        if isinstance(payload, dict) and "acceleration" in str(payload.get("code", "")):
            error_page.issue_list.setCurrentRow(row)
            break
    error_page._jump_to_issue()
    records["07_rotary_axis_limit_error_zh_1366x768.png"] = _capture(
        error_page,
        "07_rotary_axis_limit_error_zh_1366x768.png",
        (1366, 768),
        scroll=100_000,
    )

    recovered = error_controller.configure_operation(
        operation_id=error_operation.operation_id,
        parameters=replace(
            error_operation.parameters,
            angular_velocity_rad_s=0.1,
            travel_feedrate_mm_min=300.0,
        ),
    )
    error_controller.generate_operation(recovered.operation_id)
    error_page.refresh()
    records["08_rotary_axis_limit_recovered_zh_1366x768.png"] = _capture(
        error_page,
        "08_rotary_axis_limit_recovered_zh_1366x768.png",
        (1366, 768),
        scroll=100_000,
    )
    records["09_rotary_export_zh_1600x900.png"] = _capture(
        error_page,
        "09_rotary_export_zh_1600x900.png",
        (1600, 900),
        scroll=100_000,
    )

    reopened = RotaryController.from_json(
        around_en.controller.to_json(), cad_model=around_en.controller.cad_model
    )
    reopened_page = RotaryPage(controller=reopened, viewer_factory=EvidenceViewer)
    reopened_page.set_language("en")
    reopened_page.refresh()
    records["10_rotary_reopen_stale_en_1920x1080.png"] = _capture(
        reopened_page,
        "10_rotary_reopen_stale_en_1920x1080.png",
        (1920, 1080),
        scroll=100_000,
    )
    summary = {
        "schema_version": 1,
        "capture_scope": "current RotaryPage controls and real generated preview payload",
        "viewer_note": (
            "The Qt evidence paint harness avoids VTK/OpenGL; production viewer qualification "
            "is recorded separately."
        ),
        "screenshots": records,
    }
    (ASSET_ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
