from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from five_axis_slicer.background_load import ResultLoadCoordinator  # noqa: E402
from five_axis_slicer.models import CadModel, SelectionState  # noqa: E402
from five_axis_slicer.project_io import ProjectLoaded, save_project  # noqa: E402
from five_axis_slicer.result_state import LoadRequest, LoadResult  # noqa: E402
from five_axis_slicer.step_loader import (
    StepLoadCancelled,
    file_sha256,
    load_step,
)  # noqa: E402
from test_step_loader import make_two_body_step  # noqa: E402


class ProjectBackgroundLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _wait_until(self, predicate, timeout: float = 8.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        self.fail("timed out while waiting for project background loading")

    def test_project_request_loads_embedded_step_and_returns_verified_project(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = load_step(make_two_body_step(root))
            project_json = save_project(root / "project", model, SelectionState())
            completed: list[LoadResult] = []
            failed: list[tuple[object, str]] = []
            coordinator = ResultLoadCoordinator()
            coordinator.completed.connect(completed.append)
            coordinator.failed.connect(
                lambda request_id, message: failed.append((request_id, message))
            )

            coordinator.start(LoadRequest("project-success", project_path=project_json))
            self._wait_until(lambda: bool(completed) or bool(failed))
            self._wait_until(lambda: not coordinator.busy)

            self.assertEqual(failed, [])
            self.assertEqual(len(completed), 1)
            result = completed[0]
            self.assertIsInstance(result.project, ProjectLoaded)
            self.assertIs(result.model, result.project.model)
            self.assertEqual(len(result.model.bodies), 2)
            self.assertIn("project_step_model", result.source_audits)
            result.close()

    def test_cancel_reaches_embedded_step_parser_and_worker_is_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "embedded.step"
            source.write_bytes(b"placeholder STEP source")
            stat = source.stat()
            model = CadModel(
                source_path=source,
                source_hash=file_sha256(source),
                bodies=[],
                edges=[],
                shapes={},
                edge_shapes={},
                source_size_bytes=stat.st_size,
                source_mtime_ns=stat.st_mtime_ns,
            )
            project_json = save_project(root / "project", model, SelectionState())
            entered = threading.Event()

            def cancellable_step(
                _path: Path,
                *,
                cancel_check,
                length_unit_override=None,
            ) -> object:
                del length_unit_override
                entered.set()
                while not cancel_check():
                    time.sleep(0.001)
                raise StepLoadCancelled("cancelled inside embedded STEP parser")

            coordinator = ResultLoadCoordinator()
            completed: list[LoadResult] = []
            failed: list[tuple[object, str]] = []
            cancelled: list[object] = []
            coordinator.completed.connect(completed.append)
            coordinator.failed.connect(
                lambda request_id, message: failed.append((request_id, message))
            )
            coordinator.cancelled.connect(cancelled.append)
            with patch(
                "five_axis_slicer.project_io.load_step",
                side_effect=cancellable_step,
            ):
                coordinator.start(
                    LoadRequest("project-cancel", project_path=project_json)
                )
                self._wait_until(entered.is_set)
                coordinator.cancel()
                self._wait_until(lambda: not coordinator.busy)

            self.assertEqual(cancelled, ["project-cancel"])
            self.assertEqual(completed, [])
            self.assertEqual(failed, [])

    def test_invalid_project_reports_worker_error_without_partial_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_json = Path(tmp) / "project.json"
            project_json.write_text("{broken", encoding="utf-8")
            coordinator = ResultLoadCoordinator()
            completed: list[LoadResult] = []
            failed: list[tuple[object, str]] = []
            coordinator.completed.connect(completed.append)
            coordinator.failed.connect(
                lambda request_id, message: failed.append((request_id, message))
            )

            coordinator.start(LoadRequest("project-error", project_path=project_json))
            self._wait_until(lambda: bool(failed))
            self._wait_until(lambda: not coordinator.busy)

            self.assertEqual(completed, [])
            self.assertEqual(failed[0][0], "project-error")
            self.assertIn("invalid project JSON", failed[0][1])


if __name__ == "__main__":
    unittest.main()
