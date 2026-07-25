from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt5.QtCore import QSettings  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from test_step_loader import make_two_body_step  # noqa: E402
from test_tube_ui import TubeViewerStub  # noqa: E402

from five_axis_slicer import background_load  # noqa: E402
from five_axis_slicer.manufacturing.setup import NodeState  # noqa: E402
from five_axis_slicer.tube_controller import PendingDraftError  # noqa: E402
from five_axis_slicer.ui import MainWindow  # noqa: E402


class SourceUpdateWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        QSettings("5AxisSclicer", "5AxisSclicer V2.0").clear()

    def _window(self) -> MainWindow:
        window = MainWindow(http_port=0, model_viewer_factory=TubeViewerStub)
        self.addCleanup(window.close)
        return window

    def _wait_until(self, predicate, timeout: float = 8.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        self.fail("timed out while waiting for STEP source update")

    def test_explicit_source_update_uses_worker_and_rebinds_existing_controller(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_two_body_step(Path(tmp))
            window = self._window()
            window.open_model(source, show_dialog=False)
            controller = window.tube_page.controller
            controller.create_operation()

            with (
                mock.patch(
                    "five_axis_slicer.background_load.load_step",
                    wraps=background_load.load_step,
                ) as worker_loader,
                mock.patch.object(
                    controller,
                    "update_cad_model",
                    wraps=controller.update_cad_model,
                ) as rebind,
            ):
                accepted = window.handle_automation(
                    "/tube/source/update",
                    {},
                )
                self.assertTrue(accepted["accepted"])
                self.assertEqual(
                    accepted["model_load"]["intent"],
                    "source_update",
                )
                self._wait_until(
                    lambda: window.model_load_state()["status"] == "ready"
                    and not window.model_loader.busy
                )

            worker_loader.assert_called_once()
            rebind.assert_called_once()
            self.assertIs(window.tube_page.controller, controller)
            self.assertEqual(window.model_load_state()["intent"], "source_update")
            self.assertEqual(controller.operations[0].state, NodeState.DIRTY)
            self.assertIn(
                "source_geometry_updated",
                controller.operations[0].dirty_reasons,
            )

    def test_failed_rebind_does_not_publish_worker_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_two_body_step(Path(tmp))
            window = self._window()
            window.open_model(source, show_dialog=False)
            original_model = window.model
            controller = window.tube_page.controller

            with (
                mock.patch.object(
                    controller,
                    "update_cad_model",
                    side_effect=RuntimeError("ambiguous source reference"),
                ),
                mock.patch.object(window, "show_error") as show_error,
            ):
                window.update_model_from_original_source()
                self._wait_until(
                    lambda: window.model_load_state()["status"] == "error"
                    and not window.model_loader.busy
                )

            self.assertIs(window.model, original_model)
            self.assertIs(window.tube_page.controller, controller)
            show_error.assert_not_called()
            self.assertEqual(
                window.model_load_state()["message"],
                "ambiguous source reference",
            )

    def test_pending_coordinate_draft_must_be_resolved_before_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_two_body_step(Path(tmp))
            window = self._window()
            window.open_model(source, show_dialog=False)
            state_before_update = window.model_load_state()
            window.tube_page.controller.begin_coordinate_draft("model_cs")

            with self.assertRaises(PendingDraftError):
                window.update_model_from_original_source()

            self.assertEqual(window.model_load_state(), state_before_update)

    def test_failed_source_update_restores_requested_draft_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_two_body_step(Path(tmp))
            window = self._window()
            window.open_model(source, show_dialog=False)
            controller = window.tube_page.controller
            controller.create_operation()
            controller.begin_coordinate_draft("model_cs")
            controller.set_numeric_origin("model_cs", (2, 3, 4), confirmed=True)
            controller.set_numeric_direction("model_cs", "z", (0, 0, 1), confirmed=True)
            controller.set_numeric_direction("model_cs", "x", (1, 0, 0), confirmed=True)
            before = controller.state_json()

            with mock.patch(
                "five_axis_slicer.background_load.load_step",
                side_effect=RuntimeError("STEP parse failed"),
            ):
                window.update_model_from_original_source(draft_resolution="discard")
                self._wait_until(
                    lambda: window.model_load_state()["status"] == "error"
                    and not window.model_loader.busy
                )
            self.assertEqual(controller.state_json(), before)

            with mock.patch.object(
                controller,
                "update_cad_model",
                side_effect=RuntimeError("rebind failed"),
            ):
                window.update_model_from_original_source(draft_resolution="apply")
                self._wait_until(
                    lambda: window.model_load_state()["status"] == "error"
                    and not window.model_loader.busy
                )
            self.assertEqual(controller.state_json(), before)

    def test_source_update_rejects_edits_made_while_step_is_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_two_body_step(Path(tmp))
            window = self._window()
            window.open_model(source, show_dialog=False)
            controller = window.tube_page.controller

            accepted = window.update_model_from_original_source()
            controller.begin_coordinate_draft("model_cs")
            self._wait_until(
                lambda: window.model_load_state()["status"] in {"error", "ready"}
                and not window.model_loader.busy
            )

            self.assertEqual(accepted["model_load"]["intent"], "source_update")
            self.assertEqual(window.model_load_state()["status"], "error")
            self.assertIn("changed during STEP loading", window.model_load_state()["message"])
            self.assertTrue(controller.has_drafts)

    def test_viewer_failure_rolls_back_the_visible_source_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_two_body_step(Path(tmp))
            window = self._window()
            window.open_model(source, show_dialog=False)
            original_model = window.model
            controller = window.tube_page.controller
            before = controller.state_json()
            load_model = window.tube_page.viewer.load_model
            failed = False

            def fail_new_model_once(model) -> None:
                nonlocal failed
                if model is not original_model and not failed:
                    failed = True
                    raise RuntimeError("tube viewer commit failed")
                load_model(model)

            with mock.patch.object(
                window.tube_page.viewer,
                "load_model",
                side_effect=fail_new_model_once,
            ):
                window.update_model_from_original_source()
                self._wait_until(
                    lambda: window.model_load_state()["status"] == "error"
                    and not window.model_loader.busy
                )

            self.assertEqual(window.model_load_state()["message"], "tube viewer commit failed")
            self.assertIs(window.model, original_model)
            self.assertIs(window.viewer.model, original_model)
            self.assertIs(window.tube_page.viewer.model, original_model)
            self.assertEqual(controller.state_json(), before)

    def test_regular_import_failure_restores_same_source_controller_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_two_body_step(Path(tmp))
            window = self._window()
            window.open_model(source, show_dialog=False)
            original_model = window.model
            controller = window.tube_page.controller
            replacement = background_load.load_step(source)
            body_id = original_model.bodies[0].body_id
            window.viewer.set_selection(body_ids=[body_id])
            load_model = window.tube_page.viewer.load_model
            failed = False

            def fail_replacement_once(model) -> None:
                nonlocal failed
                if model is replacement and not failed:
                    failed = True
                    raise RuntimeError("regular import publication failed")
                load_model(model)

            with (
                mock.patch.object(
                    window.tube_page.viewer,
                    "load_model",
                    side_effect=fail_replacement_once,
                ),
                self.assertRaisesRegex(RuntimeError, "regular import publication failed"),
            ):
                window._commit_model(replacement)

            self.assertIs(window.model, original_model)
            self.assertIs(window.viewer.model, original_model)
            self.assertIs(window.tube_page.model, original_model)
            self.assertIs(window.tube_page.viewer.model, original_model)
            self.assertIs(window.tube_page.controller, controller)
            self.assertIs(controller._cad_model, original_model)
            self.assertEqual(window.viewer.selection.body_ids, {body_id})

    def test_source_update_refresh_failure_restores_derived_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = make_two_body_step(Path(tmp))
            window = self._window()
            window.open_model(source, show_dialog=False)
            original_model = window.model
            candidate_model = replace(
                original_model,
                source_path=Path(tmp) / "updated-visible.step",
                source_hash="b" * 64,
                bodies=original_model.bodies[:1],
            )
            controller = window.tube_page.controller
            controller_before = controller.state_json()
            label_before = window.model_file_label.text()
            checks_before = window.checks_text.toPlainText()
            body_count_before = window.body_list.count()
            update_checks = window._update_checks
            failed = False
            candidate_was_visible = False

            def fail_new_checks_once() -> None:
                nonlocal candidate_was_visible, failed
                update_checks()
                if window.model is not original_model and not failed:
                    candidate_was_visible = (
                        window.model_file_label.text() == str(candidate_model.source_path)
                        and window.body_list.count() == 1
                    )
                    failed = True
                    raise RuntimeError("derived UI refresh failed")

            with (
                mock.patch.object(background_load, "load_step", return_value=candidate_model),
                mock.patch.object(window, "_update_checks", side_effect=fail_new_checks_once),
            ):
                window.update_model_from_original_source()
                self._wait_until(
                    lambda: window.model_load_state()["status"] == "error"
                    and not window.model_loader.busy
                )

            self.assertEqual(window.model_load_state()["message"], "derived UI refresh failed")
            self.assertTrue(candidate_was_visible)
            self.assertIs(window.model, original_model)
            self.assertIs(window.viewer.model, original_model)
            self.assertIs(window.tube_page.viewer.model, original_model)
            self.assertEqual(controller.state_json(), controller_before)
            self.assertIs(controller._cad_model, original_model)
            self.assertEqual(window.model_file_label.text(), label_before)
            self.assertEqual(window.checks_text.toPlainText(), checks_before)
            self.assertEqual(window.body_list.count(), body_count_before)

    def test_project_reopen_keeps_embedded_authority_and_external_update_path(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_two_body_step(root)
            window = self._window()
            window.open_model(source, show_dialog=False)
            saved = window.save_project_to(root / "project")

            window.open_project(saved["project_json"])
            state = window.current_state()["model"]

            self.assertEqual(Path(state["original_source_path"]), source.resolve())
            self.assertEqual(Path(state["source_path"]).parent.name, "source")


if __name__ == "__main__":
    unittest.main()
