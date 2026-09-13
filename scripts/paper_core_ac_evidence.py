"""Generate PC01-PC07 real-case products, projects, UI images and evidence."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("FIVE_AXIS_RENDER_BACKEND", "opengl")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtCore import QPointF  # noqa: E402
from PyQt5.QtGui import QColor, QPainter, QPen  # noqa: E402
from PyQt5.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402

from five_axis_slicer.freeform_controller import FreeformController  # noqa: E402
from five_axis_slicer.freeform_ui import FreeformPage  # noqa: E402
from five_axis_slicer.gcode_preview import PreviewSettings  # noqa: E402
from five_axis_slicer.manufacturing.controller_profile import (  # noqa: E402
    OWN_AC_OFFLINE_CONTROLLER,
)
from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.curve_parameters import (  # noqa: E402
    CurveGeometrySelection,
    DirectedEdgeReference,
)
from five_axis_slicer.manufacturing.freeform_parameters import (  # noqa: E402
    FreeformGeometrySelection,
    FreeformOperationDefinition,
    FreeformProcessParameters,
)
from five_axis_slicer.manufacturing.material_plan import (  # noqa: E402
    MaterialChannel,
    MaterialPlan,
    MaterialRegion,
)
from five_axis_slicer.manufacturing.own_printer import own_ac_profile  # noqa: E402
from five_axis_slicer.manufacturing.reference_descriptors import (  # noqa: E402
    geometry_reference,
)
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_PLA_175,
    NozzleProfile,
    ResourceSnapshot,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    ManufacturingObjectAssignments,
    ManufacturingSetup,
    TubeProcessParameters,
)
from five_axis_slicer.models import SelectionState  # noqa: E402
from five_axis_slicer.postprocessing.freeform_product import (  # noqa: E402
    export_freeform_product,
    generate_freeform_product,
)
from five_axis_slicer.postprocessing.own_ac import (  # noqa: E402
    postprocess_own_ac,
    readback_own_ac,
)
from five_axis_slicer.postprocessing.tube_product import (  # noqa: E402
    export_tube_product,
    generate_tube_product,
)
from five_axis_slicer.project_io import load_project, save_project  # noqa: E402
from five_axis_slicer.step_loader import load_step  # noqa: E402
from five_axis_slicer.tube_controller import TubeSetupController  # noqa: E402

EVIDENCE = ROOT / "docs" / "reviews" / "evidence" / "2026-09-13_paper_core_ac"
IMAGES = ROOT / "docs" / "guides" / "assets" / "paper_core_ac"
SIX_FILES = {
    "main.gcode",
    "toolpath.json",
    "machine_axes.csv",
    "warnings.json",
    "preview.json",
    "manifest.json",
}
CASES = {
    "hemisphere_pattern": {
        "cad": ROOT / "example" / "球形NEU校徽" / "球形测试件.STEP",
        "historical": ROOT / "example" / "球形NEU校徽" / "NEU校徽划线.gcode",
        "selections": tuple(
            ("body_002_face_0001", f"body_002_edge_{index:04d}", True)
            for index in (1, 5, 7, 9, 12, 14, 16)
        ),
        "path_count": 1,
    },
    "fan_blade": {
        "cad": ROOT / "example" / "扇叶" / "风扇扇叶(1).STEP",
        "historical": ROOT / "example" / "扇叶" / "风扇扇叶完整新.gcode",
        "selections": (
            ("body_001_face_0002", "body_001_edge_0009", True),
            ("body_002_face_0002", "body_002_edge_0009", True),
            ("body_003_face_0003", "body_003_edge_0012", True),
        ),
        "path_count": 1,
    },
    "impeller": {
        "cad": ROOT / "example" / "叶轮" / "叶轮.stp",
        "historical": ROOT / "example" / "叶轮" / "叶轮完整.gcode",
        "selections": tuple(
            (f"body_{index:03d}_face_0006", f"body_{index:03d}_edge_0011", True)
            for index in range(2, 10)
        ),
        "path_count": 2,
    },
}


class EvidenceViewer(QWidget):
    """Deterministic Qt renderer driven by the real generated preview payload."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.selection = SelectionState()
        self.preview_settings = PreviewSettings()
        self.gcode_preview = None
        self.visible_path_segment_count = 0

    def load_model(self, model):
        self.model = model
        self.selection.clear()

    def clear_model(self):
        self.model = None
        self.selection.clear()

    def load_gcode_preview(self, preview):
        self.gcode_preview = preview
        self.visible_path_segment_count = len(preview.segments)
        self.update()

    def clear_gcode_preview(self):
        self.gcode_preview = None
        self.visible_path_segment_count = 0

    def preview_state(self):
        return {"settings": self.preview_settings.to_json(), "progress": {}}

    def set_selection(self, *, body_ids=None, edge_ids=None, face_ids=None, vertex_ids=None):
        for name, values in (
            ("body_ids", body_ids),
            ("edge_ids", edge_ids),
            ("face_ids", face_ids),
            ("vertex_ids", vertex_ids),
        ):
            if values is not None:
                setattr(self.selection, name, set(values))

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#17212b"))
        painter.setRenderHint(QPainter.Antialiasing)
        segments = () if self.gcode_preview is None else tuple(self.gcode_preview.segments)
        projected = [
            (
                (item.start[0] - 0.45 * item.start[1], item.start[2] + 0.25 * item.start[1]),
                (item.end[0] - 0.45 * item.end[1], item.end[2] + 0.25 * item.end[1]),
                item.move_type,
            )
            for item in segments
        ]
        values = [point for line in projected for point in line[:2]]
        if values:
            min_x, max_x = min(p[0] for p in values), max(p[0] for p in values)
            min_y, max_y = min(p[1] for p in values), max(p[1] for p in values)
            margin = 45.0
            scale = min(
                max(1.0, self.width() - 2 * margin) / max(max_x - min_x, 1.0),
                max(1.0, self.height() - 2 * margin) / max(max_y - min_y, 1.0),
            )

            def screen(point):
                return QPointF(
                    margin + (point[0] - min_x) * scale,
                    self.height() - margin - (point[1] - min_y) * scale,
                )

            for start, end, move_type in projected:
                color = QColor("#4cc9f0") if move_type == "extrude" else QColor("#f4a261")
                painter.setPen(QPen(color, 2.0 if move_type == "extrude" else 1.0))
                painter.drawLine(screen(start), screen(end))
        painter.setPen(QColor("#dbe7f3"))
        painter.drawText(20, 30, "Paper Core AC · current generated Freeform payload")
        painter.setPen(QColor("#91a7bd"))
        painter.drawText(20, 50, f"Qt evidence renderer · {len(segments)} segments")
        painter.end()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", (0, 0, 0), confirmed=True),
        DirectionReference("numeric", (0, 0, 1), confirmed=True),
        DirectionReference("numeric", (1, 0, 0), confirmed=True),
    )


def _nozzle() -> NozzleProfile:
    return NozzleProfile(
        "paper-core-ac-nozzle",
        "Paper Core AC evidence nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2.0,
        outer_profile_rz_mm=((0.3, 0.0), (0.4, 2.0)),
    )


def _setup(model) -> ManufacturingSetup:
    return ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(
            part_body_ids=tuple(body.body_id for body in model.bodies)
        ),
        machine=ResourceSnapshot.capture("machine", own_ac_profile()),
        nozzle=ResourceSnapshot.capture("nozzle", _nozzle()),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("paper-core-ac-pla")
        ),
        model_coordinate_system=_frame("model"),
        build_coordinate_system=_frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250, 250, 250),
            source_frame="build",
            target_frame="build_plate_mount",
        ),
    )


def _material_plan(name: str, guide_count: int, path_count: int, channels: int) -> MaterialPlan:
    channel_values = (
        MaterialChannel("T0", "PLA", "T0", 195, 5, requires_prepare_pause=False),
        MaterialChannel("T1", "PETG", "T1", 235, 6, requires_prepare_pause=False),
        MaterialChannel("T2", "PA", "T2", 275, 7, requires_prepare_pause=True),
        MaterialChannel("T3", "ABS", "T3", 250, 8, requires_prepare_pause=True),
    )[:channels]
    regions = tuple(
        MaterialRegion(
            f"guide-{guide:02d}-pass-{pass_index:02d}",
            channel_values[(guide + pass_index - 2) % channels].channel_id,
        )
        for guide in range(1, guide_count + 1)
        for pass_index in range(1, path_count + 1)
    )
    return MaterialPlan(
        f"{name}-materials",
        channel_values,
        regions,
        context={"assignment": "explicit", "scope": "offline_only"},
    )


def _operation(model, name: str, spec, *, channels: int = 4):
    faces: dict[str, GeometryReference] = {}
    guides = []
    for face_id, edge_id, reversed_flag in spec["selections"]:
        face = geometry_reference(model, face_id, "face")
        faces[face_id] = face
        guides.append(
            CurveGeometrySelection(
                (DirectedEdgeReference(geometry_reference(model, edge_id, "edge"), reversed_flag),),
                "adjacent_face",
                face,
            )
        )
    path_count = int(spec["path_count"])
    return FreeformOperationDefinition(
        f"pc06-{name}",
        "setup-1",
        name.replace("_", " ").title(),
        "freeform_thin_wall" if name == "fan_blade" else "freeform_surface",
        geometry=FreeformGeometrySelection(tuple(faces.values()), tuple(guides)),
        parameters=FreeformProcessParameters(
            sampling_step_mm=3.0,
            path_spacing_mm=0.6,
            path_count=path_count,
            layer_count=1,
            feedrate_mm_min=900,
        ),
        material_plan=_material_plan(name, len(guides), path_count, channels),
    )


def _file_map(directory: Path) -> dict[str, str]:
    files = {item.name: _sha256(item) for item in sorted(directory.iterdir()) if item.is_file()}
    if set(files) != SIX_FILES:
        raise RuntimeError(f"{directory.name} violates the six-file contract: {sorted(files)}")
    return files


def _save_project(name, model, setup, operation, target):
    selected = SelectionState(
        edge_ids={guide.edges[0].edge.object_id for guide in operation.geometry.guides},
        face_ids={face.object_id for face in operation.geometry.faces},
    )
    project_json = save_project(
        target,
        model,
        selected,
        {"workbench": "freeform", "case": name},
        setup=setup,
        operations=(operation,),
        original_source_path=model.source_path,
    )
    loaded = load_project(project_json)
    if loaded.operations != (operation,):
        raise RuntimeError(f"{name} project round-trip changed the operation")
    (project_json.parent / ".project-save.lock").unlink(missing_ok=True)
    return str(project_json.relative_to(ROOT)).replace("\\", "/")


def _run_freeform(name: str, spec) -> tuple[dict, object, object, object]:
    source = Path(spec["cad"])
    model = load_step(source)
    operation = _operation(model, name, spec)
    result = generate_freeform_product(
        model,
        operation,
        own_ac_profile(),
        _nozzle(),
        OWN_AC_OFFLINE_CONTROLLER,
        T_build_from_source=RigidTransform.identity("source"),
        source_path=source,
    )
    if not result.offline_exportable or not result.readback.passed:
        raise RuntimeError(f"{name} did not pass offline generation/readback")
    target = export_freeform_product(result, EVIDENCE / "products" / name)
    project_path = _save_project(
        name, model, _setup(model), operation, EVIDENCE / "projects" / name
    )
    record = {
        "cad_path": str(source.relative_to(ROOT)).replace("\\", "/"),
        "cad_sha256": _sha256(source),
        "operation_semantic_sha256": operation.semantic_sha256(),
        "status": result.manifest.status.value,
        "offline_exportable": result.offline_exportable,
        "machine_executable": result.machine_executable,
        "paths": len(result.plan.paths),
        "points": len(result.toolpath.points),
        "readback": result.readback.to_json(),
        "material_statistics": dict(result.validation.material_statistics),
        "controller_qualification": dict(result.validation.controller_qualification),
        "project": project_path,
        "files": _file_map(target),
    }
    return record, model, operation, result


def _tube_operation(model):
    controller = TubeSetupController(model)
    controller.create_operation(operation_id="pc06-pipe2-indexed")
    return controller.configure_operation(
        tube_body_id="body_002",
        entry_port_id="body_002_edge_0003",
        exit_port_id="body_002_edge_0014",
        substrate_body_id="body_001",
        parameters=TubeProcessParameters(
            bead_width_mm=10,
            layer_height_mm=10,
            safe_clearance_mm=10,
            contour_chord_error_mm=0.01,
        ),
    )


def _run_pipe2() -> dict:
    source = ROOT / "example" / "pipe2" / "弯管新.stp"
    model = load_step(source)
    operation = _tube_operation(model)
    transform = RigidTransform.from_translation(
        (250, 250, -300), source_frame="build", target_frame="workpiece"
    )
    result = generate_tube_product(
        model,
        operation,
        own_ac_profile(),
        _nozzle(),
        source_path=source,
        T_workpiece_from_build=transform,
        radial_error_limit_mm=0.025,
    )
    if not result.exportable or not result.readback.passed:
        raise RuntimeError("pipe2 Tube product did not pass the existing strict chain")
    target = export_tube_product(result, EVIDENCE / "products" / "pipe2")
    own_gcode = postprocess_own_ac(
        result.toolpath,
        result.trajectory,
        own_ac_profile(),
        _nozzle(),
        OWN_AC_OFFLINE_CONTROLLER,
        marker_tag="PC05",
    )
    own_report = readback_own_ac(
        own_gcode,
        result.toolpath,
        result.trajectory,
        own_ac_profile(),
        _nozzle(),
        OWN_AC_OFFLINE_CONTROLLER,
        marker_tag="PC05",
    )
    own_path = EVIDENCE / "products" / "pipe2_own_ac.gcode"
    own_path.write_text(own_gcode, encoding="utf-8", newline="\n")
    setup = _setup(model)
    project = save_project(
        EVIDENCE / "projects" / "pipe2",
        model,
        SelectionState(body_ids={"body_001", "body_002"}),
        {"workbench": "tube", "case": "pipe2"},
        setup=setup,
        operations=(replace(operation, setup_id=setup.setup_id),),
        original_source_path=model.source_path,
    )
    loaded = load_project(project)
    if len(loaded.operations) != 1:
        raise RuntimeError("pipe2 project round-trip failed")
    (project.parent / ".project-save.lock").unlink(missing_ok=True)
    return {
        "cad_path": str(source.relative_to(ROOT)).replace("\\", "/"),
        "cad_sha256": _sha256(source),
        "status": result.manifest.status.value,
        "points": len(result.toolpath.points),
        "existing_readback": result.readback.to_json(),
        "own_ac_readback": own_report.to_json(),
        "own_ac_gcode": str(own_path.relative_to(ROOT)).replace("\\", "/"),
        "own_ac_gcode_sha256": _sha256(own_path),
        "absolute_index_z20": "G90\nG1 Z20.000000" in own_gcode,
        "relative_material_park_z20": "G91\nG1 Z20.000000" in own_gcode,
        "project": str(project.relative_to(ROOT)).replace("\\", "/"),
        "files": _file_map(target),
    }


def _historical_summary(path: Path) -> dict:
    modes = {key: 0 for key in ("G90", "G91", "G93", "G94", "M82", "M83")}
    motion = rotary = tools = 0
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            code = line.partition(";")[0].strip().upper()
            if not code:
                continue
            head = code.split()[0]
            if head in modes:
                modes[head] += 1
            if head in {"G0", "G00", "G1", "G01"}:
                motion += 1
                rotary += int(bool(re.search(r"(?:^|\s)[AC][-+0-9.]", code)))
            if re.fullmatch(r"T\d+", head):
                tools += 1
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": _sha256(path),
        "motion_lines": motion,
        "motion_lines_with_A_or_C": rotary,
        "tool_selection_lines": tools,
        "mode_counts": modes,
        "use": "frame_strategy_and_command_count_comparison_only",
    }


def _dual_channel_case(model, source) -> dict:
    spec = {
        "selections": CASES["impeller"]["selections"][:2],
        "path_count": 1,
    }
    operation = _operation(model, "dual_channel_preloaded", spec, channels=2)
    result = generate_freeform_product(
        model,
        operation,
        own_ac_profile(),
        _nozzle(),
        OWN_AC_OFFLINE_CONTROLLER,
        T_build_from_source=RigidTransform.identity("source"),
        source_path=source,
    )
    target = export_freeform_product(result, EVIDENCE / "products" / "dual_channel_preloaded")
    event_types = [item.event_type for item in result.toolpath.events]
    if "prepare_pause" in event_types or not result.readback.passed:
        raise RuntimeError("preloaded dual-channel case inserted a preparation pause or failed")
    return {
        "status": result.manifest.status.value,
        "points": len(result.toolpath.points),
        "event_types": event_types,
        "material_statistics": dict(result.validation.material_statistics),
        "files": _file_map(target),
    }


def _failure_cases() -> list[dict]:
    source = Path(CASES["hemisphere_pattern"]["cad"])
    model = load_step(source)
    spec = {
        "selections": (("body_002_face_0001", "body_002_edge_0018", True),),
        "path_count": 2,
    }
    try:
        generate_freeform_product(
            model,
            _operation(model, "trim_failure", spec, channels=1),
            own_ac_profile(),
            _nozzle(),
            OWN_AC_OFFLINE_CONTROLLER,
            T_build_from_source=RigidTransform.identity("source"),
            source_path=source,
        )
    except Exception as exc:
        return [
            {
                "case": "hemisphere_trim_boundary",
                "expected": "curve.offset_outside_face",
                "actual": str(exc),
                "export_blocked": True,
            },
            {
                "case": "material_sensor_and_temperature",
                "expected": [
                    "material.sensor_not_ready:T1",
                    "material.temperature_out_of_tolerance:T1",
                ],
                "evidence": "tests/test_paper_core_ac.py",
                "recovery_tested": True,
            },
            {
                "case": "tampered_relative_extrusion_or_command_stream",
                "expected": "strict readback rejection",
                "evidence": "tests/test_paper_core_ac.py",
                "export_blocked": True,
            },
        ]
    raise RuntimeError("deliberate trimmed-face failure unexpectedly generated")


def _capture_ui(controller: FreeformController) -> list[dict]:
    app = QApplication.instance() or QApplication([])
    page = FreeformPage(controller=controller, viewer_factory=EvidenceViewer)
    records = []
    for index, (language, size) in enumerate(
        (("zh", (1366, 768)), ("en", (1600, 900)), ("en", (1920, 1080))), start=1
    ):
        page.set_language(language)
        page.resize(*size)
        page.show()
        app.processEvents()
        page.editor_scroll.verticalScrollBar().setValue(
            0 if index == 1 else page.editor_scroll.verticalScrollBar().maximum()
        )
        app.processEvents()
        target = IMAGES / f"{index:02d}_freeform_{language}_{size[0]}x{size[1]}.png"
        if not page.grab().save(str(target), "PNG"):
            raise RuntimeError(f"could not capture {target}")
        clipped = []
        for button in page.findChildren(QPushButton):
            if (
                button.isVisible()
                and button.fontMetrics().horizontalAdvance(button.text()) > button.width()
            ):
                clipped.append(button.text())
        records.append(
            {
                "path": str(target.relative_to(ROOT)).replace("\\", "/"),
                "sha256": _sha256(target),
                "language": language,
                "size": list(size),
                "viewer": "Qt evidence renderer driven by production generated preview payload",
                "visible_segments": page.viewer.visible_path_segment_count,
                "status": page.status_label.text(),
                "export_enabled": page.export_button.isEnabled(),
                "horizontal_scroll_max": page.editor_scroll.horizontalScrollBar().maximum(),
                "clipped_buttons": clipped,
            }
        )
    page.close()
    return records


def _ui_controller(model, operation):
    controller = FreeformController(model, setup=_setup(model))
    controller._operations = (replace(operation, setup_id=controller.setup.setup_id),)
    controller.generate_operation(operation.operation_id)
    return controller


def _snapshot_files() -> list[dict]:
    rows = []
    for root in (EVIDENCE, IMAGES):
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name != "validation_manifest.json":
                rows.append(
                    {
                        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "bytes": path.stat().st_size,
                        "sha256": _sha256(path),
                    }
                )
    return rows


def main() -> int:
    global EVIDENCE
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    EVIDENCE = args.output.resolve()
    (EVIDENCE / "products").mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "projects").mkdir(parents=True, exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    products = {}
    contexts = {}
    for name, spec in CASES.items():
        record, model, operation, result = _run_freeform(name, spec)
        products[name] = record
        contexts[name] = (model, operation, result)
    products["pipe2"] = _run_pipe2()
    impeller_model, impeller_operation, _result = contexts["impeller"]
    products["dual_channel_preloaded"] = _dual_channel_case(
        impeller_model, Path(CASES["impeller"]["cad"])
    )
    screenshots = _capture_ui(_ui_controller(impeller_model, impeller_operation))
    historical = {
        name: _historical_summary(Path(spec["historical"])) for name, spec in CASES.items()
    }
    historical["pipe2"] = _historical_summary(ROOT / "example" / "pipe2" / "弯管.gcode")
    manifest = {
        "schema_version": 1,
        "scope": "paper_core_ac_offline_only",
        "products": products,
        "historical_nc_comparison": historical,
        "failure_cases": _failure_cases(),
        "entrypoints": {
            "gui": "FreeformPage",
            "restricted_script": "FreeformCommandService",
            "http": "FreeformAutomationRoutes",
            "verification": "tests/test_freeform_integration.py",
        },
        "screenshots": screenshots,
        "known_limits": [
            "controller and macro versions are unknown",
            "coordinated XYZAC, cumulative C limit, calibration and site collision are unverified",
            "all generated NC is offline review output and is not qualified for machine execution",
            "historical NC is comparison evidence, not current geometry or material truth",
            "local user CAD/NC redistribution licences remain unknown",
            "production VTK/OpenGL screenshot capture was unavailable in this headless session",
        ],
    }
    manifest["files"] = _snapshot_files()
    (EVIDENCE / "validation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"products": list(products), "files": len(manifest["files"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
