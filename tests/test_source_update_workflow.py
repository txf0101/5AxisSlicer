from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt5.QtCore import QSettings  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from five_axis_slicer import background_load  # noqa: E402
from five_axis_slicer.manufacturing.setup import NodeState  # noqa: E402
from five_axis_slicer.tube_controller import PendingDraftError  # noqa: E402
from five_axis_slicer.ui import MainWindow  # noqa: E402
from test_step_loader import make_two_body_step  # noqa: E402
from test_tube_ui import TubeViewerStub  # noqa: E402


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
