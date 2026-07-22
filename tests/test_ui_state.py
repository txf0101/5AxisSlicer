from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtWidgets import QApplication, QWidget

from five_axis_slicer.gcode_preview import PreviewSettings, parse_gcode
from five_axis_slicer.ui import MainWindow


class ResultViewerStub(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = None
        self.gcode_preview = None
        self.quality_mode = "interactive"
        self.progress_index = 0
        self.standard_view_calls: list[str] = []

    def load_model(self, model) -> None:
        self.model = model

    def load_gcode_preview(self, preview) -> None:
        self.gcode_preview = preview
        self.progress_index = max(0, len(preview.timeline) - 1)

    def clear_gcode_preview(self) -> None:
        self.gcode_preview = None
        self.progress_index = 0

    def set_preview_layers(self, _low: int, _high: int) -> None:
        return

    def set_preview_progress(self, value: int, interactive: bool | None = None) -> None:
        del interactive
        self.progress_index = max(0, int(value))

    def set_progress_interaction(self, _active: bool) -> None:
        return

    def progress_state(self) -> dict:
        total = 0 if self.gcode_preview is None else len(self.gcode_preview.timeline)
        return {
            "layer_step_count": total,
            "progress_index": min(self.progress_index, max(0, total - 1)),
            "current_step": None,
        }

    def set_preview_visibility(self, **_values) -> None:
        return

    def set_result_visibility(self, **_values) -> None:
        return

    def set_quality_mode(self, mode: str) -> None:
        self.quality_mode = mode

    def set_standard_view(self, view: str) -> None:
        self.standard_view_calls.append(view)

    def fit_view(self) -> None:
        return

    def home_view(self) -> None:
        return

    def camera_state(self) -> dict[str, object]:
        return {"position": [120.0, -120.0, 90.0], "focal_point": [0.0, 0.0, 20.0]}

    def capabilities(self) -> dict[str, object]:
        return {"backend": "test", "offscreen_export": True}

    def render_scene_image(self, width: int, height: int) -> QImage:
        image = QImage(width, height, QImage.Format_RGB888)
        image.fill(QColor("#EEF2F6"))
        return image

    def render(self) -> None:
        return


class UiStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        QSettings("5AxisSclicer", "5AxisSclicer V2.0").clear()

    def test_workbench_and_language_state_are_exposed(self) -> None:
        window = MainWindow(http_port=0)
        self.addCleanup(window.close)

        window.enter_workbench("freeform")
        self.assertEqual(window.current_state()["workbench"]["workbench"], "freeform")

        window.toggle_language()
        self.assertEqual(window.current_state()["language"], "en")
        self.assertIn("Imported NC", window.operation_combo.itemText(0))

    def test_home_gcode_viewer_entry_opens_empty_result_preview(self) -> None:
        window = MainWindow(http_port=0)
        self.addCleanup(window.close)

        self.assertEqual(window.gcode_viewer_button.text(), "切片成果预览")
        window.gcode_viewer_button.click()

        self.assertIs(window.stack.currentWidget(), window.result_page)
        self.assertEqual(window.result_page.state.status, "empty")
        window.toggle_language()
        self.assertEqual(window.gcode_viewer_button.text(), "Slicing Result Preview")

    def test_result_menus_and_language_preference_are_global(self) -> None:
        window = MainWindow(http_port=0, result_viewer_factory=ResultViewerStub)
        self.addCleanup(window.close)
        self.assertEqual(
            [action.text() for action in window.menuBar().actions()],
            ["文件", "模型", "切片", "预览", "G-code", "工具", "帮助"],
        )

        window.set_language("en")
        self.assertEqual(
            [action.text() for action in window.menuBar().actions()],
            ["File", "Model", "Slice", "Preview", "G-code", "Tools", "Help"],
        )
        second = MainWindow(http_port=0, result_viewer_factory=ResultViewerStub)
        self.addCleanup(second.close)
        self.assertEqual(second.language, "en")

    def test_result_source_paths_elide_without_widening_the_supported_layout(self) -> None:
        window = MainWindow(http_port=0, result_viewer_factory=ResultViewerStub)
        self.addCleanup(window.close)
        page = window.result_page
        long_stem = "impeller_result_source_" + "0123456789" * 12
        paths = {
            page.model_source_value: Path(f"{long_stem}.step").resolve(),
            page.gcode_source_value: Path(f"{long_stem}.gcode").resolve(),
            page.reference_source_value: Path(f"{long_stem}.png").resolve(),
        }
        page.set_selected_model_path(paths[page.model_source_value])
        page.set_selected_gcode_path(paths[page.gcode_source_value])
        page.set_reference_image(paths[page.reference_source_value])
        window.show_results_page()
        window.show()

        for language in ("zh", "en"):
            for width, height in ((1600, 900), (1920, 1080)):
                with self.subTest(language=language, size=(width, height)):
                    window.set_language(language)
                    window.resize(width, height)
                    self.app.processEvents()
                    scroll = page.left_column
                    content = scroll.widget()
                    self.assertLessEqual(content.minimumSizeHint().width(), scroll.viewport().width())
                    self.assertLessEqual(content.width(), scroll.viewport().width())
                    self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                    for label, path in paths.items():
                        self.assertEqual(label.toolTip(), str(path))
                        self.assertEqual(label.full_text(), path.name)
                        self.assertIn("…", label.text())

    def test_results_open_endpoint_commits_background_gcode_atomically(self) -> None:
        window = MainWindow(http_port=0, result_viewer_factory=ResultViewerStub)
        self.addCleanup(window.close)
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "result.gcode"
            source.write_text(
                ";LAYER_CHANGE\n"
                "G1 X0 Y0 Z0.2 F3000\n"
                "G1 X1 Y0 Z0.2 A10 C-4 E0.3 F1200\n",
                encoding="utf-8",
            )
            accepted = window.handle_automation("/results/open", {"path": str(source)})
            self.assertTrue(accepted["accepted"])
            deadline = time.monotonic() + 5.0
            while window.result_page.state.status == "loading" and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.005)
            try:
                self.assertIn(window.result_page.state.status, {"ready", "warning"})
                self.assertIs(window.stack.currentWidget(), window.result_page)
                statistics = window.result_page.statistics_json()["toolpath"]
                self.assertEqual(statistics["positive_extrusion_segments"], 1)
                source_audit = window.result_page.state_json()["source_audits"]["gcode"]
                self.assertEqual(source_audit["path"], str(source.resolve()))
                self.assertEqual(source_audit["size_bytes"], source.stat().st_size)
                self.assertEqual(len(source_audit["sha256"]), 64)
                quality = window.handle_automation("/results/quality", {"mode": "paper"})
                self.assertEqual(quality["results"]["display"]["quality_mode"], "paper")
                self.assertEqual(window.result_page.viewer.quality_mode, "paper")
            finally:
                window.result_page.shutdown()

    def test_result_load_and_export_jobs_are_mutually_exclusive(self) -> None:
        window = MainWindow(http_port=0, result_viewer_factory=ResultViewerStub)
        self.addCleanup(window.close)

        window._result_export_state["status"] = "running"
        with self.assertRaisesRegex(RuntimeError, "正在导出"):
            window.start_result_load(gcode_path=Path("pending.gcode"))

        window._result_export_state["status"] = "idle"
        window.result_page.state.status = "loading"
        with self.assertRaisesRegex(RuntimeError, "仍在加载"):
            window.queue_result_export(mode="zh")

    def test_result_export_lock_preserves_shell_and_result_interaction_state(self) -> None:
        window = MainWindow(http_port=0, result_viewer_factory=ResultViewerStub)
        self.addCleanup(window.close)
        window._show_results()
        original_page = window.stack.currentWidget()
        original_language = window.language
        original_model_visibility = window.result_page.state.show_model
        original_quality = window.result_page.state.quality_mode
        window._result_export_state["status"] = "running"
        window.result_page.set_export_interaction_locked(True)

        try:
            window.language_actions["en"].trigger()
            window.result_visibility_actions["show_model"].trigger()
            window.quality_actions["paper"].trigger()
            window._set_active_standard_view("front")
            window._show_home()
            window._show_session()
            window.load_results_demo_action.trigger()

            self.assertEqual(window.language, original_language)
            self.assertEqual(window.result_page.state.show_model, original_model_visibility)
            self.assertEqual(window.result_page.state.quality_mode, original_quality)
            self.assertTrue(window.result_visibility_actions["show_model"].isChecked())
            self.assertTrue(window.quality_actions["interactive"].isChecked())
            self.assertTrue(window.language_actions["zh"].isChecked())
            self.assertEqual(window.result_page.viewer.standard_view_calls, [])
            self.assertIs(window.stack.currentWidget(), original_page)
            self.assertFalse(window.result_loader.busy)

            with self.assertRaisesRegex(RuntimeError, "正在执行"):
                window.handle_automation("/results/quality", {"mode": "paper"})
            with self.assertRaisesRegex(RuntimeError, "正在执行"):
                window.handle_automation("/results/focus", {"section": "code"})
            with self.assertRaisesRegex(RuntimeError, "正在导出"):
                window.load_results_demo()
            with self.assertRaisesRegex(RuntimeError, "正在执行"):
                window.save_project_to(Path("unused-project-directory"))

            with (
                mock.patch(
                    "five_axis_slicer.ui.QFileDialog.getOpenFileName"
                ) as open_dialog,
                mock.patch(
                    "five_axis_slicer.ui.QFileDialog.getExistingDirectory"
                ) as directory_dialog,
            ):
                window.open_model_dialog()
                window.open_gcode_dialog()
                window.open_result_model_dialog()
                window.open_result_gcode_dialog()
                window.save_project_dialog()

            open_dialog.assert_not_called()
            directory_dialog.assert_not_called()
        finally:
            window._result_export_state["status"] = "idle"
            window.result_page.set_export_interaction_locked(False)

    def test_preview_visibility_endpoint_updates_settings(self) -> None:
        window = MainWindow(http_port=0)
        self.addCleanup(window.close)

        result = window.handle_automation(
            "/preview/visibility",
            {"show_travel": False, "show_extrusion": True, "visible_roles": ["external_perimeter"]},
        )
        settings = result["preview"]["settings"]
        self.assertFalse(settings["show_travel"])
        self.assertEqual(settings["visible_roles"], ["external_perimeter"])

    def test_parameter_labels_and_segment_panel_are_translated(self) -> None:
        window = MainWindow(http_port=0)
        self.addCleanup(window.close)

        preview = parse_gcode(
            """
;LAYER_CHANGE
;TYPE:External perimeter
G1 X0 Y0 Z0.2 F3000
G1 X1 Y0 E0.4 A12 C-4 F1200
"""
        )
        window.gcode_preview = preview
        window.viewer.gcode_preview = preview
        window.viewer.preview_settings = PreviewSettings(
            layer_min=preview.layer_min,
            layer_max=preview.layer_max,
        )
        window.viewer.visible_path_segment_count = len(preview.segments)
        window._sync_preview_controls()

        self.assertIn("行号", window.segment_property.text())
        window.toggle_language()
        self.assertEqual(window.segment_property_title.text(), "Segment Properties")
        self.assertEqual(window.localized_groups[0][0].title(), "Layer and Bead")

    def test_preview_progress_endpoint_updates_current_step(self) -> None:
        window = MainWindow(http_port=0)
        self.addCleanup(window.close)

        preview = parse_gcode(
            """
;LAYER_CHANGE
;TYPE:Outer wall
G1 X0 Y0 Z0.2
G1 X1 Y0 E0.4
G1 E-0.2
"""
        )
        window.gcode_preview = preview
        window.viewer.gcode_preview = preview
        window.viewer.preview_settings = PreviewSettings(layer_min=preview.layer_min, layer_max=preview.layer_max)
        window.viewer.refresh_path_preview = lambda: None
        window._sync_preview_controls()

        result = window.handle_automation("/preview/progress", {"progress_index": 1})

        progress = result["preview"]["progress"]
        self.assertEqual(progress["progress_index"], 1)
        self.assertEqual(progress["current_step"]["move_type"], "extrude")
        self.assertEqual(window.progress_slider.value(), 1)
        self.assertEqual(window.preview_progress_slider.value(), 1)
        self.assertIn("行号", window.segment_property.text())


if __name__ == "__main__":
    unittest.main()
