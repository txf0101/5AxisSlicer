from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QRect, QSize, Qt
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from five_axis_slicer.paper_export import (
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    PIXELS_PER_METER,
    PaperExportError,
    RenderSnapshot,
    _interprocess_artifact_lock,
    export_paper_preview,
)


class StubViewer(QWidget):
    backend = "opengl"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.last_request: tuple[int, int] | None = None
        self.logical_size_at_capture: QSize | None = None
        self.logical_geometry_at_capture: QRect | None = None
        self.setStyleSheet("background: #EEF2F6")

    def render_scene_image(self, width: int, height: int) -> QImage:
        self.last_request = (width, height)
        self.logical_size_at_capture = self.size()
        self.logical_geometry_at_capture = self.geometry()
        image = QImage(width, height, QImage.Format_RGB888)
        image.fill(QColor("#2563EB"))
        return image

    def camera_state(self) -> dict[str, object]:
        return {
            "position": [120.0, -120.0, 90.0],
            "focal_point": [0.0, 0.0, 20.0],
            "view_up": [0.0, 0.0, 1.0],
        }

    def capabilities(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "quality_mode": "paper",
            "paper_quality_active": True,
            "offscreen_export": True,
            "full_timeline_paper_path": True,
        }


class FallbackViewer(StubViewer):
    def render_scene_image(self, width: int, height: int) -> QImage:
        del width, height
        raise RuntimeError("FBO unavailable in test backend")

    def grabFramebuffer(self) -> QImage:  # noqa: N802 - Qt API spelling
        image = QImage(max(1, self.width()), max(1, self.height()), QImage.Format_RGB888)
        image.fill(QColor("#16845B"))
        return image


class VtkViewer(StubViewer):
    backend = "vtk"

    def capabilities(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "quality_mode": "paper",
            "paper_quality_active": True,
            "offscreen_export": True,
            "full_timeline_paper_path": False,
        }


class MissingTimelineViewer(StubViewer):
    def capabilities(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "quality_mode": "paper",
            "paper_quality_active": True,
            "offscreen_export": True,
        }


class InteractiveViewer(StubViewer):
    def capabilities(self) -> dict[str, object]:
        values = super().capabilities()
        values.update(quality_mode="interactive", paper_quality_active=False)
        return values


class PaperExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_root(self, viewer_type: type[StubViewer] = StubViewer) -> tuple[QWidget, StubViewer]:
        root = QWidget()
        root.setObjectName("paper_export_test_root")
        root.setStyleSheet("#paper_export_test_root { background: #F3F5F7; }")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(12)
        title = QLabel("5AxisSclicer V2.0 | Result Preview")
        title.setFixedHeight(44)
        layout.addWidget(title)
        viewer = viewer_type(root)
        layout.addWidget(viewer, 1)
        root.resize(640, 360)
        root.show()
        self.app.processEvents()
        self.addCleanup(root.close)
        return root, viewer

    def test_exports_exact_opaque_4k_png_and_complete_sidecar(self) -> None:
        root, viewer = self.make_root()
        old_size = root.size()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "impeller_result_preview_en_3840x2160.png"
            source = Path(tmp) / "small.gcode"
            source_payload = b"G1 X1 Y2 Z3 A90 C-10 E0.4 F1200\n"
            source.write_bytes(source_payload)

            result = export_paper_preview(
                root,
                viewer,
                output,
                language="en-US",
                sources={"gcode": source},
                statistics={"space_segments": 12, "positive_extrusion_segments": 10},
                display_items={"travel": False, "pose_samples": False},
                render_parameters={"continuity_tolerance_mm": 0.02},
            )

            self.assertEqual(root.size(), old_size)
            self.assertEqual(result.image_path, output.resolve())
            self.assertEqual(result.sidecar_path, output.with_suffix(".json").resolve())
            self.assertIsNotNone(viewer.logical_size_at_capture)
            self.assertEqual(
                viewer.last_request,
                (
                    viewer.logical_size_at_capture.width() * 2,
                    viewer.logical_size_at_capture.height() * 2,
                ),
            )

            image = QImage(str(output))
            self.assertEqual((image.width(), image.height()), (OUTPUT_WIDTH, OUTPUT_HEIGHT))
            self.assertFalse(image.hasAlphaChannel())
            self.assertIsNotNone(viewer.logical_geometry_at_capture)
            scene_rect = viewer.logical_geometry_at_capture
            scene_center = image.pixelColor(
                (scene_rect.x() + scene_rect.width() // 2) * 2,
                (scene_rect.y() + scene_rect.height() // 2) * 2,
            )
            self.assertEqual(scene_center.name().upper(), "#2563EB")

            audit = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
            self.assertEqual(audit["schema_version"], 1)
            self.assertEqual(audit["language"], "en")
            self.assertEqual(audit["artifact"]["width_px"], 3840)
            self.assertEqual(audit["artifact"]["height_px"], 2160)
            self.assertTrue(audit["artifact"]["opaque"])
            self.assertEqual(audit["artifact"]["color_space"], "sRGB")
            self.assertEqual(audit["sources"]["gcode"]["size_bytes"], len(source_payload))
            self.assertEqual(
                audit["sources"]["gcode"]["sha256"],
                hashlib.sha256(source_payload).hexdigest(),
            )
            self.assertIsInstance(audit["sources"]["gcode"]["mtime_ns"], int)
            self.assertEqual(audit["statistics"]["positive_extrusion_segments"], 10)
            self.assertEqual(audit["camera"]["position"], [120.0, -120.0, 90.0])
            self.assertFalse(audit["render_parameters"]["degraded"])
            self.assertEqual(
                audit["render_parameters"]["caller"]["continuity_tolerance_mm"],
                0.02,
            )
            self.assertEqual(
                audit["artifact"]["sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )

            chunks = _png_chunks(output.read_bytes())
            self.assertIn(b"sRGB", chunks)
            self.assertIn(b"pHYs", chunks)
            ppm_x, ppm_y, unit = struct.unpack(">IIB", chunks[b"pHYs"])
            self.assertEqual((ppm_x, ppm_y, unit), (PIXELS_PER_METER, PIXELS_PER_METER, 1))

    def test_framebuffer_fallback_is_explicitly_audited(self) -> None:
        root, viewer = self.make_root(FallbackViewer)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "fallback.png"
            result = export_paper_preview(
                root,
                viewer,
                output,
                language="zh",
                sources={},
                statistics={},
            )
            audit = result.snapshot.to_json()
            render = audit["render_parameters"]
            self.assertTrue(render["degraded"])
            self.assertEqual(render["scene_capture_method"], "viewer.grabFramebuffer (degraded)")
            self.assertEqual(render["degradations"][0]["component"], "scene_capture")

    def test_strict_export_rejects_vtk_and_missing_full_timeline_before_render(self) -> None:
        cases = (
            (VtkViewer, "backend='opengl'"),
            (MissingTimelineViewer, "full_timeline_paper_path capability is missing"),
            (InteractiveViewer, "active paper quality"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            for index, (viewer_type, expected) in enumerate(cases):
                with self.subTest(viewer=viewer_type.__name__):
                    root, viewer = self.make_root(viewer_type)
                    output = Path(tmp) / f"strict_capability_{index}.png"
                    with self.assertRaisesRegex(PaperExportError, expected):
                        export_paper_preview(
                            root,
                            viewer,
                            output,
                            language="en",
                            sources={},
                            statistics={},
                            strict=True,
                        )
                    self.assertIsNone(viewer.last_request)
                    self.assertFalse(output.exists())
                    self.assertFalse(output.with_suffix(".json").exists())

    def test_nonstrict_vtk_export_records_formal_capability_degradations(self) -> None:
        root, viewer = self.make_root(VtkViewer)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "vtk_degraded.png"
            result = export_paper_preview(
                root,
                viewer,
                output,
                language="zh",
                sources={},
                statistics={},
                strict=False,
            )
            render = result.snapshot.to_json()["render_parameters"]
            self.assertTrue(render["degraded"])
            components = {item["component"] for item in render["degradations"]}
            self.assertEqual(
                components,
                {"paper_export_backend", "full_timeline_paper_path"},
            )
            self.assertEqual(render["scene_capture_method"], "viewer.render_scene_image")

    def test_qt_overlays_are_restored_above_the_scene_capture(self) -> None:
        root, viewer = self.make_root()
        overlay = QLabel("XYZ", root)
        overlay.setObjectName("axis_overlay_test")
        overlay.setStyleSheet("background: #E5484D; color: white")
        overlay.setAlignment(Qt.AlignCenter)
        overlay.setGeometry(36, 92, 90, 44)
        overlay.show()
        overlay.raise_()
        self.app.processEvents()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "overlay.png"
            result = export_paper_preview(
                root,
                viewer,
                output,
                language="en",
                sources={},
                statistics={},
                overlay_widgets=(overlay,),
            )
            image = QImage(str(output))
            color = image.pixelColor((overlay.x() + 45) * 2, (overlay.y() + 22) * 2)
            self.assertEqual(color.name().upper(), "#E5484D")
            self.assertEqual(
                result.snapshot.to_json()["render_parameters"]["qt_overlay_widgets"],
                ["axis_overlay_test"],
            )

    def test_strict_scene_capture_does_not_write_partial_artifact(self) -> None:
        root, viewer = self.make_root(FallbackViewer)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "strict.png"
            with self.assertRaisesRegex(PaperExportError, "Formal scene capture failed"):
                export_paper_preview(
                    root,
                    viewer,
                    output,
                    language="en",
                    sources={},
                    statistics={},
                    allow_scene_fallback=False,
                )
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".json").exists())

    def test_sidecar_replace_failure_restores_existing_artifact_pair(self) -> None:
        root, viewer = self.make_root()
        with tempfile.TemporaryDirectory() as tmp:
            output = (Path(tmp) / "existing.png").resolve()
            sidecar = output.with_suffix(".json")
            old_png = b"previous-png-payload"
            old_json = b'{"generation": "previous"}\n'
            output.write_bytes(old_png)
            sidecar.write_bytes(old_json)
            real_replace = os.replace

            def replace_with_sidecar_failure(source: object, destination: object) -> None:
                source_path = Path(source)  # type: ignore[arg-type]
                destination_path = Path(destination)  # type: ignore[arg-type]
                if destination_path == sidecar and source_path.suffix == ".new":
                    raise OSError("injected sidecar replacement failure")
                real_replace(source, destination)

            with mock.patch(
                "five_axis_slicer.paper_export.os.replace",
                side_effect=replace_with_sidecar_failure,
            ):
                with self.assertRaisesRegex(PaperExportError, "artifact pair"):
                    export_paper_preview(
                        root,
                        viewer,
                        output,
                        language="en",
                        sources={},
                        statistics={},
                    )

            self.assertEqual(output.read_bytes(), old_png)
            self.assertEqual(sidecar.read_bytes(), old_json)
            remaining_names = {path.name for path in Path(tmp).iterdir()}
            self.assertEqual(remaining_names, {output.name, sidecar.name})

    def test_artifact_pair_lock_rejects_concurrent_same_target_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = (Path(tmp) / "shared.png").resolve()
            sidecar = output.with_suffix(".json")
            locked = threading.Event()
            release = threading.Event()
            worker_errors: list[BaseException] = []

            def hold_lock() -> None:
                try:
                    with _interprocess_artifact_lock(output, sidecar):
                        locked.set()
                        release.wait(timeout=2.0)
                except BaseException as exc:  # surfaced on the test thread below
                    worker_errors.append(exc)
                    locked.set()

            worker = threading.Thread(target=hold_lock, daemon=True)
            worker.start()
            self.assertTrue(locked.wait(timeout=2.0))
            try:
                self.assertFalse(worker_errors)
                with self.assertRaisesRegex(PaperExportError, "another process"):
                    with _interprocess_artifact_lock(
                        output,
                        sidecar,
                        timeout_seconds=0.05,
                    ):
                        self.fail("A concurrent writer acquired the same artifact lock")
            finally:
                release.set()
                worker.join(timeout=2.0)

            self.assertFalse(worker.is_alive())
            self.assertFalse(worker_errors)

    def test_precomputed_source_audit_is_retained_and_changed_source_is_audited(self) -> None:
        root, viewer = self.make_root()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "snapshot.gcode"
            loaded_payload = b"G1 X1 E1\n"
            source.write_bytes(loaded_payload)
            loaded_stat = source.stat()
            loaded_sha256 = hashlib.sha256(loaded_payload).hexdigest()
            load_snapshot = {
                "path": str(source),
                "name": source.name,
                "size_bytes": loaded_stat.st_size,
                "mtime_ns": loaded_stat.st_mtime_ns,
                "sha256": loaded_sha256,
            }
            source.write_bytes(b"G1 X100 Y200 E5\n")

            strict_output = Path(tmp) / "changed_strict.png"
            with self.assertRaisesRegex(PaperExportError, "changed after loading"):
                export_paper_preview(
                    root,
                    viewer,
                    strict_output,
                    language="en",
                    sources={"gcode": source},
                    source_audits={"gcode": load_snapshot},
                    statistics={},
                    strict=True,
                )
            self.assertIsNone(viewer.last_request)
            self.assertFalse(strict_output.exists())
            self.assertFalse(strict_output.with_suffix(".json").exists())

            output = Path(tmp) / "changed_nonstrict.png"
            result = export_paper_preview(
                root,
                viewer,
                output,
                language="en",
                sources={"gcode": source},
                precomputed_source_audits={"gcode": load_snapshot},
                statistics={},
            )
            load_snapshot["sha256"] = "f" * 64
            audit = result.snapshot.to_json()
            self.assertEqual(audit["sources"]["gcode"]["name"], source.name)
            self.assertEqual(audit["sources"]["gcode"]["sha256"], loaded_sha256)
            self.assertEqual(audit["render_parameters"]["source_audit_basis"], "load_snapshot")
            self.assertTrue(audit["render_parameters"]["source_snapshot_checked"])
            self.assertTrue(audit["render_parameters"]["degraded"])
            self.assertIn(
                "source_snapshot",
                {item["component"] for item in audit["render_parameters"]["degradations"]},
            )

    def test_strict_export_requires_load_time_audit_for_declared_sources(self) -> None:
        root, viewer = self.make_root()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "declared.gcode"
            source.write_text("G1 X1 E0.1\n", encoding="utf-8")
            output = Path(tmp) / "missing_snapshot.png"

            with self.assertRaisesRegex(PaperExportError, "load-time source_audits"):
                export_paper_preview(
                    root,
                    viewer,
                    output,
                    language="en",
                    sources={"gcode": source},
                    strict=True,
                )

            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".json").exists())

    def test_render_snapshot_is_deeply_immutable(self) -> None:
        snapshot = RenderSnapshot(
            captured_at_utc="2026-07-21T00:00:00.000Z",
            language="zh-CN",
            sources=(),
            statistics={"counts": {"segments": 3}, "axes": ["A", "C"]},
            camera={"position": [1.0, 2.0, 3.0]},
            display_items={"travel": False},
            render_parameters={"scale": 2},
            artifact={"width_px": 3840},
        )
        self.assertEqual(snapshot.language, "zh")
        with self.assertRaises(TypeError):
            snapshot.statistics["counts"] = {}  # type: ignore[index]
        with self.assertRaises(TypeError):
            snapshot.statistics["counts"]["segments"] = 4  # type: ignore[index]
        self.assertEqual(snapshot.to_json()["statistics"]["axes"], ["A", "C"])


def _png_chunks(payload: bytes) -> dict[bytes, bytes]:
    self_signature = b"\x89PNG\r\n\x1a\n"
    if not payload.startswith(self_signature):
        raise AssertionError("not a PNG")
    offset = len(self_signature)
    chunks: dict[bytes, bytes] = {}
    while offset + 12 <= len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        kind = payload[offset + 4 : offset + 8]
        data = payload[offset + 8 : offset + 8 + length]
        chunks[kind] = data
        offset += length + 12
        if kind == b"IEND":
            break
    return chunks


if __name__ == "__main__":
    unittest.main()
