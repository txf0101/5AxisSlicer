from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stderr


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtCore import QRect
from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QImage
from PyQt5.QtWidgets import QApplication


def _load_script_module():
    path = ROOT / "scripts" / "build_four_panel_paper_figure.py"
    spec = importlib.util.spec_from_file_location("paper_panel_export_script", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script_module()


class IndependentPaperPanelExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _write_formal_png(self, path: Path, color: str) -> bytes:
        image = QImage(
            SCRIPT.CANVAS_WIDTH,
            SCRIPT.CANVAS_HEIGHT,
            QImage.Format_RGB888,
        )
        image.fill(QColor(color))
        payload = SCRIPT._encode_png(image)
        path.write_bytes(payload)
        return payload

    @staticmethod
    def _source_record(path: Path, role: str) -> dict[str, object]:
        payload = path.read_bytes()
        return {
            "role": role,
            "path": str(path.resolve()),
            "name": path.name,
            "exists": True,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }

    def _make_inputs(self, root: Path) -> tuple[Path, Path, Path, Path, Path]:
        gcode = root / "impeller.gcode"
        gcode.write_text(
            "; fixture\n"
            "G90\n"
            "M83\n"
            "G1 F600 X0.000 Y-42.000 Z22.200 A90.000 C-162.000 E0\n"
            "G1 F8052 X0.000 Y-41.950 Z12.240 A89.950 C-162.440 E0.003564\n",
            encoding="utf-8",
        )
        step = root / "impeller.stp"
        step.write_text("ISO-10303-21;", encoding="ascii")
        reference = root / "reference.png"
        reference.write_bytes(b"reference fixture")

        overall = root / "overall.png"
        overall_payload = self._write_formal_png(overall, "#EAF2FF")
        overall_sidecar = overall.with_suffix(".json")
        overall_sidecar.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "captured_at_utc": "2026-07-21T00:00:00.000Z",
                    "language": "zh",
                    "artifact": {
                        "width_px": SCRIPT.CANVAS_WIDTH,
                        "height_px": SCRIPT.CANVAS_HEIGHT,
                        "sha256": hashlib.sha256(overall_payload).hexdigest(),
                    },
                    "sources": {
                        "gcode": self._source_record(gcode, "gcode"),
                        "step_model": self._source_record(step, "step_model"),
                        "visual_reference": self._source_record(reference, "visual_reference"),
                    },
                    "statistics": {"toolpath": {"spatial_segments": 2}},
                    "camera": {"yaw_degrees": 35.0, "pitch_degrees": 55.0},
                    "display_items": {"orientation_cube": True},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        toolpath = root / "toolpath.png"
        toolpath_payload = self._write_formal_png(toolpath, "#D1FADF")
        toolpath_sidecar = toolpath.with_suffix(".json")
        toolpath_sidecar.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "artifact": {
                        "width_px": SCRIPT.CANVAS_WIDTH,
                        "height_px": SCRIPT.CANVAS_HEIGHT,
                        "sha256": hashlib.sha256(toolpath_payload).hexdigest(),
                    },
                    "camera": {"yaw_degrees": 35.0, "pitch_degrees": 55.0},
                    "display_items": {"orientation_cube": True},
                }
            ),
            encoding="utf-8",
        )
        return overall, overall_sidecar, toolpath, toolpath_sidecar, gcode

    def test_exports_four_direct_4k_pairs_without_precomposed_grid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overall, overall_sidecar, toolpath, toolpath_sidecar, gcode = self._make_inputs(root)
            output = root / "individual_panels"

            result = SCRIPT.main(
                [
                    "--overall",
                    str(overall),
                    "--overall-sidecar",
                    str(overall_sidecar),
                    "--toolpath-image",
                    str(toolpath),
                    "--toolpath-sidecar",
                    str(toolpath_sidecar),
                    "--gcode",
                    str(gcode),
                    "--output-dir",
                    str(output),
                    "--language",
                    "zh",
                    "--uncompressed-tiff",
                ]
            )
            self.assertEqual(result, 0)

            expected_stems = {
                "a": "impeller_paper_panel_a_overall_zh_3840x2160",
                "b": "impeller_paper_panel_b_process_settings_zh_3840x2160",
                "c": "impeller_paper_panel_c_five_axis_toolpath_zh_3840x2160",
                "d": "impeller_paper_panel_d_machine_gcode_zh_3840x2160",
            }
            audits: dict[str, dict[str, object]] = {}
            for panel_id, stem in expected_stems.items():
                image_path = output / f"{stem}.png"
                sidecar_path = output / f"{stem}.json"
                self.assertTrue(image_path.is_file())
                self.assertTrue(sidecar_path.is_file())
                info = SCRIPT._inspect_png(image_path.read_bytes())
                SCRIPT._verify_png_contract(info)
                audit = json.loads(sidecar_path.read_text(encoding="utf-8"))
                audits[panel_id] = audit
                self.assertEqual(audit["panel"]["id"], panel_id)
                self.assertIsNone(audit["panel"]["crop_from_composite"])
                self.assertFalse(audit["panel"]["resampling"])
                self.assertFalse(audit["panel"]["caption_baked"])
                self.assertEqual(audit["artifact"]["width_px"], 3840)
                self.assertEqual(audit["artifact"]["height_px"], 2160)
                self.assertEqual(
                    audit["artifact"]["sha256"],
                    hashlib.sha256(image_path.read_bytes()).hexdigest(),
                )
                tiff_path = output / f"{stem}.tif"
                tiff_sidecar_path = output / f"{stem}.tif.json"
                self.assertTrue(tiff_path.is_file())
                self.assertTrue(tiff_sidecar_path.is_file())
                tiff_bytes = tiff_path.read_bytes()
                tiff_info = SCRIPT._inspect_tiff(tiff_bytes)
                SCRIPT._verify_uncompressed_tiff(tiff_info)
                tiff_audit = json.loads(tiff_sidecar_path.read_text(encoding="utf-8"))
                self.assertEqual(tiff_audit["panel"]["id"], panel_id)
                self.assertEqual(tiff_audit["artifact"]["compression"], "none")
                self.assertEqual(tiff_audit["artifact"]["tiff_compression_tag"], 1)
                self.assertEqual(tiff_audit["artifact"]["samples_per_pixel"], 3)
                self.assertEqual(tiff_audit["artifact"]["bits_per_sample"], [8, 8, 8])
                self.assertEqual(
                    tiff_audit["artifact"]["sha256"],
                    hashlib.sha256(tiff_bytes).hexdigest(),
                )

            self.assertEqual((output / f"{expected_stems['a']}.png").read_bytes(), overall.read_bytes())
            self.assertEqual((output / f"{expected_stems['c']}.png").read_bytes(), toolpath.read_bytes())
            self.assertEqual(
                audits["b"]["panel"]["capture_method"],
                "direct_qt_vector_paint",
            )
            self.assertEqual(
                audits["d"]["panel"]["capture_method"],
                "direct_qt_vector_paint_from_gcode_index",
            )
            self.assertEqual(audits["d"]["panel"]["representative_gcode_line"], 4)
            self.assertIn(4, audits["d"]["panel"]["context_source_line_numbers"])
            self.assertEqual(audits["d"]["panel"]["line_number_mode"], "absolute_source_line")

            manifest_path = output / "impeller_paper_panels_zh_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["assembly"]["panel_order"], ["a", "b", "c", "d"])
            self.assertFalse(manifest["assembly"]["captions_baked"])
            self.assertFalse(manifest["assembly"]["precomposed_grid_generated"])
            self.assertTrue(manifest["assembly"]["intended_for_user_composition"])
            self.assertEqual(manifest["formats"], ["png", "tiff_uncompressed"])
            self.assertEqual(len(manifest["panels"]), 4)
            self.assertEqual(len({item["sha256"] for item in manifest["panels"]}), 4)
            for panel in manifest["panels"]:
                self.assertEqual(
                    panel["deliverables"]["tiff_uncompressed"]["tiff_compression_tag"],
                    1,
                )
            self.assertEqual(len(list(output.glob("*.png"))), 4)
            self.assertEqual(len(list(output.glob("*.tif"))), 4)

    def test_rejects_overall_preview_reused_as_toolpath_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            overall, overall_sidecar, _toolpath, _toolpath_sidecar, gcode = self._make_inputs(root)
            with self.assertRaisesRegex(RuntimeError, "independent render"):
                SCRIPT.main(
                    [
                        "--overall",
                        str(overall),
                        "--overall-sidecar",
                        str(overall_sidecar),
                        "--toolpath-image",
                        str(overall),
                        "--gcode",
                        str(gcode),
                        "--output-dir",
                        str(root / "out"),
                    ]
                )

    def test_toolpath_image_and_step_arguments_are_mutually_exclusive(self) -> None:
        parser = SCRIPT.build_parser()
        common = ["--overall", "overall.png", "--gcode", "part.gcode"]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(common)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(
                common
                + [
                    "--toolpath-image",
                    "toolpath.png",
                    "--step",
                    "part.stp",
                ]
            )

        step_args = parser.parse_args(common + ["--step", "part.stp"])
        SCRIPT._validate_cli_arguments(step_args)
        invalid_sidecar = parser.parse_args(
            common
            + [
                "--step",
                "part.stp",
                "--toolpath-sidecar",
                "toolpath.json",
            ]
        )
        with self.assertRaisesRegex(ValueError, "only be used with --toolpath-image"):
            SCRIPT._validate_cli_arguments(invalid_sidecar)

    def test_bilingual_gcode_header_and_code_body_fit_without_clipping(self) -> None:
        header = QRect(24, 24, SCRIPT.LOGICAL_WIDTH - 48, 132)
        for language in ("zh", "en"):
            with self.subTest(language=language):
                layout = SCRIPT._gcode_header_layout(header, language)
                self.assertLess(layout.title_rect.bottom(), layout.chip_band_rect.top())
                for rect in layout.chip_rects:
                    self.assertTrue(layout.chip_band_rect.contains(rect))
                for index, rect in enumerate(layout.chip_rects):
                    for other in layout.chip_rects[index + 1 :]:
                        self.assertFalse(rect.intersects(other))
                chip_font = SCRIPT._pixel_font("Microsoft YaHei UI", 16, QFont.DemiBold)
                metrics = QFontMetricsF(chip_font)
                for (text, _color), rect in zip(SCRIPT._syntax_chips(language), layout.chip_rects):
                    self.assertLessEqual(metrics.horizontalAdvance(text) + 24, rect.width())

        context = [
            (146973 + index, "G1 F8052.761063 X0.000 Y-41.950 Z12.240 A89.950 C-162.440 E0.003564")
            for index in range(21)
        ]
        target = QRect(24, 24, SCRIPT.LOGICAL_WIDTH - 48, SCRIPT.LOGICAL_HEIGHT - 48)
        body = SCRIPT._fit_gcode_body_layout(
            target,
            context,
            code_top=target.y() + 150,
            preferred_pixel_size=22,
            minimum_pixel_size=18,
        )
        metrics = QFontMetricsF(body.font)
        self.assertGreaterEqual(body.pixel_size, 18)
        self.assertLessEqual(
            max(metrics.horizontalAdvance(source) for _line, source in context),
            body.code_clip_rect.width(),
        )
        self.assertLessEqual(body.line_height * len(context), body.code_clip_rect.height())
        for language in ("zh", "en"):
            text = SCRIPT._settings_text(language)
            self.assertNotIn("imported_note", text)
            self.assertNotIn("not_applied", text)
            self.assertNotIn("parameter_note", text)
            self.assertNotIn("reference_image", text)


if __name__ == "__main__":
    unittest.main()
