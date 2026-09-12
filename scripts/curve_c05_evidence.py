"""Generate reproducible C01-C05 real-STEP products and Qt screenshots."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("FIVE_AXIS_RENDER_BACKEND", "opengl")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication, QPushButton  # noqa: E402

from five_axis_slicer.curve_controller import CurveController  # noqa: E402
from five_axis_slicer.curve_ui import CurvePage  # noqa: E402
from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.curve_parameters import (  # noqa: E402
    CurveProcessParameters,
)
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE  # noqa: E402
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_PLA_175,
    NozzleProfile,
    ResourceSnapshot,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    ManufacturingObjectAssignments,
    ManufacturingSetup,
)
from five_axis_slicer.step_loader import load_step  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
REAL_STEP = ROOT / "example" / "叶轮" / "叶轮.stp"
RECTANGLE_STEP = (
    ROOT
    / "docs"
    / "reviews"
    / "evidence"
    / "2026-09-12_project_audit"
    / "frozen_cases"
    / "analytic"
    / "rectangle_8x6x1.step"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", (0.0, 0.0, 0.0), confirmed=True),
        DirectionReference("numeric", (0.0, 0.0, 1.0), confirmed=True),
        DirectionReference("numeric", (1.0, 0.0, 0.0), confirmed=True),
    )


def _setup(model, body_id: str) -> ManufacturingSetup:
    machine = replace(
        GENERIC_XYZAC_REFERENCE,
        joints=tuple(
            replace(joint, soft_limit_min=-1000.0, soft_limit_max=1000.0)
            for joint in GENERIC_XYZAC_REFERENCE.joints
        ),
    )
    nozzle = NozzleProfile(
        "curve-c05-nozzle",
        "Curve C05 evidence nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2.0,
        outer_profile_rz_mm=((0.3, 0.0), (0.4, 2.0)),
    )
    return ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(
            part_body_ids=(body_id,),
            ignored_body_ids=tuple(
                body.body_id for body in model.bodies if body.body_id != body_id
            ),
        ),
        machine=ResourceSnapshot.capture("machine", machine),
        nozzle=ResourceSnapshot.capture("nozzle", nozzle),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("curve-c05-evidence-pla")
        ),
        model_coordinate_system=_frame("model"),
        build_coordinate_system=_frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250.0, 250.0, 250.0),
            source_frame="build",
            target_frame="build_plate_mount",
        ),
    )


def _configured(model, operation_type: str, edge_id: str, face_id: str) -> CurveController:
    controller = CurveController(model, setup=_setup(model, model.bodies[1].body_id))
    operation = controller.create_operation(operation_type)
    controller.configure_operation(
        operation_id=operation.operation_id,
        edge_ids=(edge_id,),
        reversed_flags=(operation_type == "curve_offset_buildup",),
        normal_mode="adjacent_face",
        normal_face_id=face_id,
        parameters=CurveProcessParameters(
            sampling_step_mm=1.0,
            layer_height_mm=0.8,
            layer_count=3,
            offset_pass_count=3,
            offset_spacing_mm=3.0,
        ),
    )
    return controller


def _capture(
    page: CurvePage,
    path: Path,
    *,
    language: str,
    size: tuple[int, int],
    model_visible: bool = True,
    scroll_to_bottom: bool = True,
) -> dict:
    page.set_language(language)
    page.resize(*size)
    page.show()
    QApplication.processEvents()
    if hasattr(page.viewer, "set_model_visible"):
        page.viewer.set_model_visible(model_visible)
    if hasattr(page.viewer, "set_standard_view"):
        page.viewer.set_standard_view("isometric")
    if hasattr(page.viewer, "fit_view"):
        page.viewer.fit_view()
    page.editor_scroll.verticalScrollBar().setValue(
        page.editor_scroll.verticalScrollBar().maximum() if scroll_to_bottom else 0
    )
    QApplication.processEvents()
    if not page.grab().save(str(path)):
        raise RuntimeError(f"could not save screenshot {path}")
    clipped = []
    for button in page.findChildren(QPushButton):
        visible = button.visibleRegion().boundingRect()
        if (
            not visible.isEmpty()
            and (visible.left() > button.rect().left() or visible.right() < button.rect().right())
        ):
            clipped.append(button.text())
    return {
        "file": path.name,
        "sha256": _sha256(path),
        "language": language,
        "size": [page.width(), page.height()],
        "capture_method": "Qt QWidget.grab; actual CurvePage and generated Toolpath",
        "viewer_backend": getattr(page.viewer, "backend", "unknown"),
        "model_visible": model_visible,
        "visible_segments": getattr(page.viewer, "visible_path_segment_count", None),
        "status": page.status_label.text(),
        "export_enabled": page.export_button.isEnabled(),
        "clipped_visible_buttons": clipped,
        "horizontal_scroll_max": page.editor_scroll.horizontalScrollBar().maximum(),
    }


def generate(output: Path, images: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    images.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    model = load_step(REAL_STEP)
    records = []
    shots = []
    cases = (
        ("curve_buildup", "zh", (1366, 768)),
        ("curve_multi_pass", "en", (1600, 900)),
        ("curve_offset_buildup", "en", (1920, 1080)),
    )
    for index, (operation_type, language, size) in enumerate(cases, 1):
        controller = _configured(
            model,
            operation_type,
            "body_002_edge_0011",
            "body_002_face_0006",
        )
        page = CurvePage(controller=controller)
        page.generate_button.click()
        app.processEvents()
        operation = controller.operations[0]
        result = controller.product_result(operation.operation_id)
        if result is None or not result.exportable or not result.readback.passed:
            raise RuntimeError(f"{operation_type} did not produce an exportable readback result")
        product_dir = output / "products" / operation_type
        controller.export_operation_product(operation.operation_id, str(product_dir))
        package = {item.name: _sha256(item) for item in sorted(product_dir.iterdir())}
        records.append(
            {
                "operation_type": operation_type,
                "operation_semantic_sha256": operation.semantic_sha256(),
                "plan_length_mm": result.plan.total_length_mm,
                "toolpath_points": len(result.toolpath.points),
                "trajectory_samples": len(result.trajectory.samples),
                "status": result.manifest.status.value,
                "readback_passed": result.readback.passed,
                "bundle_sha256": package,
            }
        )
        shots.append(
            _capture(
                page,
                images / f"0{index}_{operation_type}_{language}_{size[0]}x{size[1]}.png",
                language=language,
                size=size,
            )
        )
        shots.append(
            _capture(
                page,
                images
                / f"{index + 5:02d}_{operation_type}_{language}_{size[0]}x{size[1]}_path_only.png",
                language=language,
                size=size,
                model_visible=False,
            )
        )
        if index == 1:
            shots.append(
                _capture(
                    page,
                    images / "09_curve_overview_edge_normal_zh_1366x768.png",
                    language="zh",
                    size=(1366, 768),
                    scroll_to_bottom=False,
                )
            )
        page.close()

    rectangle = load_step(RECTANGLE_STEP)
    error_controller = CurveController(
        rectangle, setup=_setup(rectangle, rectangle.bodies[0].body_id)
    )
    operation = error_controller.create_operation("curve_offset_buildup")
    error_controller.configure_operation(
        operation_id=operation.operation_id,
        edge_ids=("body_001_edge_0012",),
        normal_mode="adjacent_face",
        normal_face_id="body_001_face_0006",
        parameters=CurveProcessParameters(offset_pass_count=3, offset_spacing_mm=0.6),
    )
    page = CurvePage(controller=error_controller)
    page.generate_button.click()
    app.processEvents()
    if "curve.offset_outside_face" not in page.status_label.text() or page.export_button.isEnabled():
        raise RuntimeError("deliberate trimmed-face failure was not visible and export-blocking")
    shots.append(
        _capture(
            page,
            images / "04_offset_failure_zh_1366x768.png",
            language="zh",
            size=(1366, 768),
        )
    )
    page.edge_ids_edit.setText("body_001_edge_0010")
    page.reverse_flags_edit.setText("0")
    page.apply_button.click()
    page.generate_button.click()
    app.processEvents()
    recovered = error_controller.product_result(operation.operation_id)
    if recovered is None or not recovered.exportable:
        raise RuntimeError("trimmed-face failure did not recover after selecting the valid edge")
    shots.append(
        _capture(
            page,
            images / "05_offset_recovered_zh_1366x768.png",
            language="zh",
            size=(1366, 768),
        )
    )
    page.close()
    manifest = {
        "schema_version": 1,
        "source": {
            "path": str(REAL_STEP.relative_to(ROOT)).replace("\\", "/"),
            "sha256": _sha256(REAL_STEP),
            "stable_edge_id": "body_002_edge_0011",
            "stable_face_id": "body_002_face_0006",
            "frame": "Source/Model -> Build -> Workpiece/Machine",
        },
        "failure_fixture": {
            "path": str(RECTANGLE_STEP.relative_to(ROOT)).replace("\\", "/"),
            "sha256": _sha256(RECTANGLE_STEP),
            "expected_error": "curve.offset_outside_face",
        },
        "products": records,
        "screenshots": shots,
        "limits": [
            "Generic XYZAC and offline FK/readback only",
            "No real controller, calibration, site collision, material qualification, or trial build",
        ],
    }
    (output / "evidence_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "reviews" / "evidence" / "2026-09-12_curve_workbench_final",
    )
    parser.add_argument(
        "--images",
        type=Path,
        default=ROOT / "docs" / "guides" / "assets" / "curve" / "current_c01_c05",
    )
    args = parser.parse_args()
    manifest = generate(args.output.resolve(), args.images.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
