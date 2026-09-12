"""Capture reproducible Planar P02 Qt UI evidence with the real STEP sample."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("FIVE_AXIS_RENDER_BACKEND", "opengl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication, QPushButton

from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE  # noqa: E402
from five_axis_slicer.manufacturing.planar_parameters import PlanarProcessParameters  # noqa: E402
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_PLA_175,
    NozzleProfile,
    ResourceSnapshot,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    ManufacturingObjectAssignments,
    ManufacturingSetup,
)
from five_axis_slicer.planar_controller import PlanarController  # noqa: E402
from five_axis_slicer.planar_ui import PlanarPage  # noqa: E402
from five_axis_slicer.step_loader import load_step  # noqa: E402


CASES = (
    ("zh", 1366, 768, "isometric", True, "01_planar_zh_1366x768.png"),
    ("zh", 1600, 900, "top", False, "02_planar_zh_1600x900_generated.png"),
    ("en", 1920, 1080, "isometric", True, "03_planar_en_1920x1080.png"),
)


def _frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", (0.0, 0.0, 0.0), confirmed=True),
        DirectionReference("numeric", (0.0, 0.0, 1.0), confirmed=True),
        DirectionReference("numeric", (1.0, 0.0, 0.0), confirmed=True),
    )


def _controller(model, body_id: str, z_mm: float) -> PlanarController:
    machine = replace(
        GENERIC_XYZAC_REFERENCE,
        joints=tuple(
            replace(joint, soft_limit_min=-1000.0, soft_limit_max=1000.0)
            for joint in GENERIC_XYZAC_REFERENCE.joints
        ),
    )
    nozzle = NozzleProfile(
        "planar-ui-nozzle",
        "Planar UI evidence nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2.0,
        outer_profile_rz_mm=((0.3, 0.0), (0.4, 2.0)),
    )
    setup = ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(
            part_body_ids=(body_id,),
            ignored_body_ids=tuple(
                body.body_id for body in model.bodies if body.body_id != body_id
            ),
        ),
        machine=ResourceSnapshot.capture("machine", machine),
        nozzle=ResourceSnapshot.capture("nozzle", nozzle),
        material=ResourceSnapshot.capture("material", GENERIC_PLA_175),
        model_coordinate_system=_frame("model"),
        build_coordinate_system=_frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250.0, 250.0, 250.0), source_frame="build", target_frame="build_plate_mount"
        ),
    )
    controller = PlanarController(model, setup=setup)
    operation = controller.create_operation(
        "planar_zigzag", operation_id="p02-ui-real-model", name="P02 real STEP zigzag"
    )
    controller.configure_operation(
        operation_id=operation.operation_id,
        body_id=body_id,
        parameters=PlanarProcessParameters(
            first_layer_z_mm=z_mm,
            last_layer_z_mm=z_mm,
            layer_height_mm=0.6,
            bead_width_mm=0.6,
            line_spacing_mm=0.6,
            feedrate_mm_min=100.0,
            travel_feedrate_mm_min=100.0,
            retract_length_mm=1.0,
        ),
    )
    return controller


def _button_audit(page: PlanarPage) -> dict[str, object]:
    buttons = [button for button in page.findChildren(QPushButton) if button.isVisible()]
    records: dict[str, dict[str, object]] = {}
    collisions: list[list[str]] = []
    for button in buttons:
        name = button.objectName() or button.text()
        origin = button.mapTo(page, QPoint(0, 0))
        text_width = button.fontMetrics().horizontalAdvance(button.text())
        available = max(0, button.width() - 12)
        records[name] = {
            "text": button.text(),
            "x": origin.x(),
            "y": origin.y(),
            "width": button.width(),
            "height": button.height(),
            "text_width": text_width,
            "available_text_width": available,
            "text_fits": text_width <= available,
        }
    for index, left in enumerate(buttons):
        left_origin = left.mapTo(page, QPoint(0, 0))
        left_rect = left.rect().translated(left_origin)
        for right in buttons[index + 1 :]:
            right_origin = right.mapTo(page, QPoint(0, 0))
            if left_rect.intersects(right.rect().translated(right_origin)):
                collisions.append(
                    [left.objectName() or left.text(), right.objectName() or right.text()]
                )
    return {"buttons": records, "collisions": collisions}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="example/三叶扇/Supportless_sample.stp")
    parser.add_argument("--body", default="body_002")
    parser.add_argument("--z", type=float, default=60.0)
    parser.add_argument("--out", default="docs/guides/assets/planar")
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    model = load_step(Path(args.model).resolve())
    page = PlanarPage(controller=_controller(model, args.body, args.z))
    page.show()
    app.processEvents()
    page.generate_button.click()
    app.processEvents()
    if getattr(page.viewer, "gcode_preview", None) is None:
        raise RuntimeError("Planar viewer did not receive the generated G-code preview")

    cases = []
    for language, width, height, view, model_visible, filename in CASES:
        page.set_language(language)
        page.resize(width, height)
        app.processEvents()
        if hasattr(page.viewer, "set_model_visible"):
            page.viewer.set_model_visible(model_visible)
        if hasattr(page.viewer, "set_standard_view"):
            page.viewer.set_standard_view(view)
        if hasattr(page.viewer, "fit_view"):
            page.viewer.fit_view()
        app.processEvents()
        path = output / filename
        if not page.grab().save(str(path)):
            raise RuntimeError(f"Could not save {path}")
        audit = _button_audit(page)
        cases.append(
            {
                "language": language,
                "requested_size": [width, height],
                "rendered_size": [page.width(), page.height()],
                "screenshot": path.name,
                "viewer_backend": getattr(page.viewer, "backend", "unknown"),
                "standard_view": view,
                "model_visible": model_visible,
                "preview_source": str(page.viewer.gcode_preview.source_path),
                "visible_path_segment_count": getattr(
                    page.viewer, "visible_path_segment_count", None
                ),
                **audit,
            }
        )
    summary = {
        "model": str(Path(args.model).resolve()),
        "body": args.body,
        "z_mm": args.z,
        "capture_kind": "Qt widget grab with project model viewer",
        "desktop_automation_boundary": (
            "Computer Use could not enumerate the Windows application; these are direct Qt "
            "render captures, not evidence of a human-like desktop click-through."
        ),
        "cases": cases,
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    page.close()
    return (
        1
        if any(
            case["collisions"]
            or any(not button["text_fits"] for button in case["buttons"].values())
            for case in cases
        )
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
