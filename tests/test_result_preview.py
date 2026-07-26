from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication, QLabel, QWidget

from five_axis_slicer.gcode_preview import parse_gcode
from five_axis_slicer.gcode_source import GCodeSourceIndex
from five_axis_slicer.result_preview import ResultCommitError, ResultPreviewPage
from five_axis_slicer.result_state import LoadRequest, LoadResult
from five_axis_slicer.theme import UI_TYPOGRAPHY


class _FakeViewer(QWidget):
    backend = "test"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.model = None
        self.preview = None
        self.layer_min = 0
        self.layer_max = 0
        self.progress_index = 0
        self.quality_mode = "interactive"
        self.visibility: dict[str, object] = {}
        self.failures: dict[str, int] = {}

    def fail_next(self, operation: str) -> None:
        self.failures[operation] = self.failures.get(operation, 0) + 1

    def _raise_if_requested(self, operation: str) -> None:
        remaining = self.failures.get(operation, 0)
        if remaining <= 0:
            return
        self.failures[operation] = remaining - 1
        raise RuntimeError(f"simulated {operation} failure")

    def load_model(self, model) -> None:
        self._raise_if_requested("load_model")
        self.model = model

    def clear_model(self) -> None:
        self.model = None

    def load_gcode_preview(self, preview) -> None:
        self._raise_if_requested("load_gcode_preview")
        self.preview = preview
        self.layer_min = preview.layer_min
        self.layer_max = preview.layer_max

    def clear_gcode_preview(self) -> None:
        self.preview = None

    def set_preview_layers(self, layer_min: int, layer_max: int) -> None:
        self.layer_min = layer_min
        self.layer_max = layer_max

    def set_preview_progress(self, progress_index: int, interactive=None) -> None:
        self.progress_index = progress_index

    def set_progress_interaction(self, _active: bool) -> None:
        pass

    def current_progress_step(self):
        if self.preview is None:
            return None
        return self.preview.timeline_step_for_layer_progress(
            self.layer_min,
            self.layer_max,
            self.progress_index,
        )

    def set_preview_visibility(self, **values) -> None:
        self.visibility.update(values)

    def set_result_visibility(self, **values) -> None:
        self.visibility.update(values)

    def set_quality_mode(self, mode: str) -> None:
        self._raise_if_requested("set_quality_mode")
        self.quality_mode = mode

    def set_standard_view(self, _view: str) -> None:
        pass

    def fit_view(self) -> None:
        pass

    def home_view(self) -> None:
        pass

    def render(self) -> None:
        pass

    def render_scene_image(self, width: int, height: int) -> QImage:
        image = QImage(width, height, QImage.Format_RGB32)
        image.fill(0xFFF8FAFC)
        return image

    def capabilities(self) -> dict[str, object]:
        return {"backend": self.backend, "offscreen_capture": True}

    def camera_state(self) -> dict[str, object]:
        return {"position": [1.0, 1.0, 1.0]}


class _TrackingSourceIndex(GCodeSourceIndex):
    def __init__(self, *args, **kwargs) -> None:
        self.close_count = 0
        super().__init__(*args, **kwargs)

    def close(self) -> None:
        self.close_count += 1
        super().close()


class _BrokenSourceIndex:
    def __init__(self) -> None:
        self.closed = False

    @property
    def stages(self):
        raise RuntimeError("damaged source index")

    def close(self) -> None:
        self.closed = True


class ResultPreviewPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_page(self) -> ResultPreviewPage:
        page = ResultPreviewPage(viewer_factory=_FakeViewer)
        self.addCleanup(page.shutdown)
        self.addCleanup(page.close)
        return page

    def test_three_column_ratio_translation_and_parameter_save_are_presentation_only(self) -> None:
        page = self.make_page()
        self.assertEqual(
            [page.columns_layout.stretch(index) for index in range(3)],
            [18, 56, 26],
        )
        page.retranslate("en")
        self.assertEqual(page.title_label.text(), "Slicing Result Preview")

        slice_requests: list[bool] = []
        parameter_events: list[object] = []
        page.slice_preview_requested.connect(lambda: slice_requests.append(True))
        page.parameters_changed.connect(parameter_events.append)
        page.edit_parameters_button.click()
        page.layer_height_spin.setValue(0.24)
        page.save_parameters_button.click()

        self.assertEqual(slice_requests, [])
        self.assertEqual(len(parameter_events), 1)
        self.assertAlmostEqual(page.state.parameters.layer_height_mm, 0.24)
        self.assertFalse(page.save_parameters_button.isEnabled())

    def test_left_column_buttons_fit_at_minimum_supported_window_in_both_languages(self) -> None:
        page = self.make_page()
        page.resize(1570, 780)
        page.show()

        buttons = (
            page.demo_button,
            page.open_gcode_button,
            page.open_step_button,
            page.slice_button,
            page.edit_parameters_button,
            page.save_parameters_button,
            page.reset_parameters_button,
        )
        for language in ("zh", "en"):
            with self.subTest(language=language):
                page.retranslate(language)
                self.app.processEvents()
                scroll = page.left_column
                content = scroll.widget()
                self.assertLessEqual(
                    content.minimumSizeHint().width(),
                    scroll.viewport().width(),
                )
                for button in buttons:
                    right_edge = button.mapTo(content, button.rect().topRight()).x()
                    self.assertLess(right_edge, content.width(), button.objectName())

    def test_bilingual_type_ramp_is_readable_and_product_text_is_not_clipped(self) -> None:
        page = self.make_page()
        page.resize(1570, 780)
        page.show()

        buttons = (
            page.back_button,
            page.demo_button,
            page.open_gcode_button,
            page.open_step_button,
            page.slice_button,
            page.edit_parameters_button,
            page.save_parameters_button,
            page.reset_parameters_button,
            page.cancel_button,
            page.jump_button,
            page.viewer_canvas.fit_button,
            page.viewer_canvas.home_button,
        )
        single_line_labels = (
            page.title_label,
            page.sources_heading,
            page.viewer_heading,
            page.analysis_heading,
            page.source_card_title,
            page.status_card_title,
            page.statistics_title,
            page.thumbnail_title,
            page.context_title,
            *page.statistic_values.values(),
        )
        for language in ("zh", "en"):
            with self.subTest(language=language):
                page.retranslate(language)
                self.app.processEvents()
                self.assertGreaterEqual(page.title_label.font().pixelSize(), UI_TYPOGRAPHY.page_title_px)
                self.assertGreaterEqual(page.context_title.font().pixelSize(), UI_TYPOGRAPHY.card_title_px)
                self.assertGreaterEqual(page.code_view.font().pixelSize(), UI_TYPOGRAPHY.code_px)
                for button in buttons:
                    if not button.isVisible():
                        continue
                    required = button.fontMetrics().horizontalAdvance(button.text()) + 4
                    self.assertGreaterEqual(button.contentsRect().width(), required, button.text())
                for checkbox in page.visibility_checks:
                    required = checkbox.fontMetrics().horizontalAdvance(checkbox.text()) + 34
                    self.assertGreaterEqual(checkbox.contentsRect().width(), required, checkbox.text())
                for label in single_line_labels:
                    if label.text() and not label.wordWrap():
                        required = label.fontMetrics().horizontalAdvance(label.text())
                        self.assertGreaterEqual(label.contentsRect().width(), required, label.text())
                for label in page.findChildren(QLabel):
                    if not label.isVisible() or not label.wordWrap() or not label.text():
                        continue
                    bounds = label.fontMetrics().boundingRect(
                        QRect(0, 0, max(1, label.contentsRect().width()), 10_000),
                        Qt.TextWordWrap,
                        label.text(),
                    )
                    self.assertGreaterEqual(
                        label.contentsRect().height(),
                        bounds.height(),
                        label.text(),
                    )
                for combo in (page.stage_combo, page.quality_combo):
                    required = max(
                        combo.fontMetrics().horizontalAdvance(combo.itemText(index))
                        for index in range(combo.count())
                    )
                    self.assertGreaterEqual(combo.contentsRect().width() - 30, required)
                visible_fragments = [
                    label.text() for label in page.findChildren(QLabel) if label.isVisible()
                ]
                for widget in (*buttons, *page.visibility_checks):
                    if widget.isVisible():
                        visible_fragments.extend((widget.text(), widget.toolTip()))
                for combo in (page.stage_combo, page.quality_combo):
                    visible_fragments.append(combo.toolTip())
                    visible_fragments.extend(
                        combo.itemText(index) for index in range(combo.count())
                    )
                visible_copy = "".join(visible_fragments).replace(" ", "").casefold()
                for forbidden in (
                    "当前版本使用已导入g-code结果",
                    "thecurrentversionusestheimportedg-coderesult",
                    "代表性五轴指令",
                    "representativefive-axisinstruction",
                    "示意",
                    "演示",
                    "illustrative",
                    "demo",
                    "未应用于",
                    "notapplied",
                    "仅用于说明",
                    "forreferenceonly",
                    "previewonly",
                ):
                    self.assertNotIn(forbidden.replace(" ", "").casefold(), visible_copy)
                self.assertEqual(page.left_column.horizontalScrollBar().maximum(), 0)
                self.assertEqual(page.right_column.horizontalScrollBar().maximum(), 0)

    def test_export_controls_are_absent(self) -> None:
        page = self.make_page()
        for name in (
            "export_title",
            "export_description",
            "export_preset_value",
            "output_label",
            "output_path_value",
            "choose_output_button",
            "export_current_button",
            "export_both_button",
        ):
            self.assertFalse(hasattr(page, name), name)

    def test_source_markers_drive_stage_navigation_and_context_window(self) -> None:
        source = """;LAYER_CHANGE
G1 X0 Y0 Z0.2 F3000
G1 X1 Y0 Z0.2 A0 C0 E0.2 F1200
;叶轮1
G1 X2 Y0 Z0.3 A90 C-20 E0.2 F1200
;叶轮2
G1 X3 Y0 Z0.4 A90 C-40 E0.2 F1200
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "stages.gcode"
            path.write_text(source, encoding="utf-8")
            index = GCodeSourceIndex(path, Path(tmpdir) / "index")
            page = self.make_page()
            page.set_gcode(parse_gcode(source), index, owns_index=True)

            stage_ids = [
                page.stage_combo.itemData(row)["id"]
                for row in range(page.stage_combo.count())
            ]
            self.assertEqual(stage_ids, ["all", "base", "blade_1", "blade_2"])
            self.assertEqual(page.statistic_values["blade_stages"].text(), "2")
            self.assertEqual(page.statistic_values["a_range"].text(), "[0, 90]°")
            page._set_context_line(5)
            rendered_lines = page.code_view.toPlainText().splitlines()
            self.assertLessEqual(len(rendered_lines), 41)
            self.assertTrue(any("A90" in line and "C-20" in line for line in rendered_lines))

            page.shutdown()
            self.app.processEvents()

    def test_failed_replacement_retains_the_committed_scene(self) -> None:
        source = """;LAYER_CHANGE
G1 X0 Y0 Z0.2 F3000
G1 X1 Y0 Z0.2 A45 C-30 E0.2 F1200
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            step_path = root / "part.stp"
            gcode_path = root / "part.gcode"
            failed_path = root / "failed.gcode"
            step_path.write_bytes(b"STEP")
            gcode_path.write_text(source, encoding="utf-8")
            failed_path.write_text("broken", encoding="utf-8")
            index = GCodeSourceIndex(gcode_path, root / "index")
            model = SimpleNamespace(bodies=[object()] * 9, edges=[object()] * 206)
            preview = parse_gcode(source)
            page = self.make_page()

            first = LoadRequest("first", step_path, gcode_path)
            page.begin_load(first)
            self.assertTrue(
                page.commit_load(
                    LoadResult(
                        "first",
                        step_path,
                        gcode_path,
                        model=model,
                        gcode_preview=preview,
                        gcode_source_index=index,
                    )
                )
            )
            previous_model = page.viewer.model
            previous_preview = page.viewer.preview

            replacement = LoadRequest("replacement", gcode_path=failed_path)
            page.begin_load(replacement)
            self.assertTrue(page.fail_load("replacement", "parse error"))
            self.assertEqual(page.state.status, "error")
            self.assertIs(page.viewer.model, previous_model)
            self.assertIs(page.viewer.preview, previous_preview)
            self.assertIn("parse error", page.status_detail.text())

            page.shutdown()
            self.app.processEvents()

    def test_commit_failures_restore_scene_state_and_index_ownership(self) -> None:
        old_source = """;LAYER_CHANGE
G1 X0 Y0 Z0.2 F3000
G1 X1 Y0 Z0.2 A45 C-30 E0.2 F1200
"""
        new_source = """;LAYER_CHANGE
G1 X0 Y0 Z0.3 F3000
G1 X2 Y0 Z0.3 A90 C-60 E0.3 F1200
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            old_step = root / "old.step"
            old_gcode = root / "old.gcode"
            old_step.touch()
            old_gcode.write_text(old_source, encoding="utf-8")
            old_index = _TrackingSourceIndex(old_gcode, root / "old-index")
            old_model = SimpleNamespace(bodies=[object()], edges=[object()])
            old_preview = parse_gcode(old_source)
            old_audits = {"gcode": {"path": str(old_gcode.resolve()), "sha256": "a" * 64}}
            page = self.make_page()

            page.begin_load(LoadRequest("initial", old_step, old_gcode))
            self.assertTrue(
                page.commit_load(
                    LoadResult(
                        "initial",
                        old_step,
                        old_gcode,
                        model=old_model,
                        gcode_preview=old_preview,
                        gcode_source_index=old_index,
                        source_audits=old_audits,
                    )
                )
            )

            for sequence, operation in enumerate(
                ("set_quality_mode", "load_gcode_preview", "load_model"),
                start=1,
            ):
                with self.subTest(operation=operation):
                    new_step = root / f"new-{sequence}.step"
                    new_gcode = root / f"new-{sequence}.gcode"
                    new_step.touch()
                    new_gcode.write_text(new_source, encoding="utf-8")
                    new_index = _TrackingSourceIndex(new_gcode, root / f"new-index-{sequence}")
                    new_model = SimpleNamespace(bodies=[object()] * 2, edges=[object()] * 3)
                    new_preview = parse_gcode(new_source)
                    request_id = f"replacement-{sequence}"

                    page.begin_load(LoadRequest(request_id, new_step, new_gcode))
                    page.viewer.fail_next(operation)
                    with self.assertRaisesRegex(ResultCommitError, operation):
                        page.commit_load(
                            LoadResult(
                                request_id,
                                new_step,
                                new_gcode,
                                model=new_model,
                                gcode_preview=new_preview,
                                gcode_source_index=new_index,
                                source_audits={
                                    "gcode": {
                                        "path": str(new_gcode.resolve()),
                                        "sha256": "b" * 64,
                                    }
                                },
                            )
                        )

                    self.assertEqual(page.state.status, "loading")
                    self.assertEqual(page.state.active_model_path, old_step.resolve())
                    self.assertEqual(page.state.active_gcode_path, old_gcode.resolve())
                    self.assertIs(page.model, old_model)
                    self.assertIs(page.preview, old_preview)
                    self.assertIs(page.source_index, old_index)
                    self.assertEqual(page.source_audits, old_audits)
                    self.assertIs(page.viewer.model, old_model)
                    self.assertIs(page.viewer.preview, old_preview)
                    self.assertEqual(page.viewer.quality_mode, "interactive")
                    self.assertEqual(old_index.close_count, 0)
                    self.assertEqual(new_index.close_count, 1)

                    self.assertTrue(page.fail_load(request_id, "commit failed"))

            page.shutdown()
            self.app.processEvents()

    def test_prepare_failure_does_not_touch_viewer_or_state_and_closes_candidate_index(self) -> None:
        source = ";LAYER_CHANGE\nG1 X0 Y0 Z0.2 E0.1\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gcode_path = root / "candidate.gcode"
            gcode_path.write_text(source, encoding="utf-8")
            broken_index = _BrokenSourceIndex()
            page = self.make_page()
            page.begin_load(LoadRequest("broken-index", gcode_path=gcode_path))

            with self.assertRaisesRegex(ResultCommitError, "damaged source index"):
                page.commit_load(
                    LoadResult(
                        "broken-index",
                        gcode_path=gcode_path,
                        gcode_preview=parse_gcode(source),
                        gcode_source_index=broken_index,
                    )
                )

            self.assertEqual(page.state.status, "loading")
            self.assertIsNone(page.model)
            self.assertIsNone(page.preview)
            self.assertIsNone(page.source_index)
            self.assertIsNone(page.viewer.model)
            self.assertIsNone(page.viewer.preview)
            self.assertTrue(broken_index.closed)

    def test_prepared_commit_rejects_intervening_state_change_without_viewer_mutation(self) -> None:
        source = ";LAYER_CHANGE\nG1 X0 Y0 Z0.2 E0.1\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gcode_path = root / "candidate.gcode"
            gcode_path.write_text(source, encoding="utf-8")
            index = _TrackingSourceIndex(gcode_path, root / "index")
            page = self.make_page()
            result = LoadResult(
                "prepared",
                gcode_path=gcode_path,
                gcode_preview=parse_gcode(source),
                gcode_source_index=index,
            )
            page.begin_load(LoadRequest("prepared", gcode_path=gcode_path))

            prepared = page.prepare_load_commit(result)
            self.assertIsNotNone(prepared)
            self.assertIsNone(page.viewer.preview)
            self.assertEqual(index.close_count, 0)

            page.state.progress = 0.5
            with self.assertRaisesRegex(ResultCommitError, "state changed"):
                page.apply_load_commit(prepared)

            self.assertIsNone(page.viewer.preview)
            self.assertIsNone(page.source_index)
            self.assertEqual(index.close_count, 1)


if __name__ == "__main__":
    unittest.main()
