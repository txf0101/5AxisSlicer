from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtCore import QObject, pyqtSignal  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from five_axis_slicer.command_kernel import CommandInvocation  # noqa: E402
from five_axis_slicer.models import BodyInfo, CadModel  # noqa: E402
from five_axis_slicer.tube_controller import TubeSetupController  # noqa: E402
from five_axis_slicer.tube_script_service import TubeScriptService  # noqa: E402


def controller() -> TubeSetupController:
    model = CadModel(
        source_path=Path("pipe.step"),
        source_hash="a" * 64,
        bodies=[BodyInfo("solid-1", 1, "Tube", (0.4, 0.5, 0.6), kind="solid")],
        edges=[],
        shapes={},
        edge_shapes={},
    )
    return TubeSetupController(model)


class FakePage(QObject):
    state_changed = pyqtSignal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.controller = controller()
        self.executor = None
        self.refresh_count = 0
        self.selected_node = None

    def set_command_executor(self, callback) -> None:
        self.executor = callback

    def refresh(self) -> None:
        self.refresh_count += 1
        self.state_changed.emit(self.controller.state_json())

    def select_setup_node(self, node: str) -> bool:
        self.selected_node = node
        return True


class FakeConsole(QObject):
    load_script_requested = pyqtSignal()
    import_config_requested = pyqtSignal()
    export_config_requested = pyqtSignal()
    reveal_config_requested = pyqtSignal()
    apply_drafts_requested = pyqtSignal()
    discard_drafts_requested = pyqtSignal()
    node_link_requested = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.executor = None
        self.completion = None
        self.outputs: list[str] = []
        self.status = ""
        self.revision = 0
        self.draft_conflict = False

    def set_executor(self, callback) -> None:
        self.executor = callback

    def set_completion_provider(self, callback) -> None:
        self.completion = callback

    def append_output(self, text: str) -> None:
        self.outputs.append(text)

    def set_status(self, text: str, *, revision: int | None = None) -> None:
        self.status = text
        if revision is not None:
            self.revision = revision

    def set_draft_conflict(self, visible: bool) -> None:
        self.draft_conflict = visible


class FakeStatusBar:
    def __init__(self) -> None:
        self.message = ""

    def showMessage(self, message: str) -> None:  # noqa: N802 - Qt API shape
        self.message = message


class FakeWindow:
    def __init__(self) -> None:
        self.language = "zh"
        self.tube_page = FakePage()
        self.load_coordinator = SimpleNamespace(busy=False)
        self.last_project_dir = None
        self._status = FakeStatusBar()

    def statusBar(self) -> FakeStatusBar:  # noqa: N802 - Qt API shape
        return self._status


class TubeScriptServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = FakeWindow()
        self.console = FakeConsole()
        self.service = TubeScriptService(self.window, self.console)

    def test_transaction_publishes_once_and_updates_memory_config(self) -> None:
        result = self.service.execute_script(
            "with tube.transaction():\n"
            "    tube.create_operation()\n"
            "    tube.confirm_part()\n"
            "    tube.set_model_cs()\n"
        )

        self.assertEqual(self.service.kernel.revision, 1)
        self.assertEqual(self.window.tube_page.refresh_count, 1)
        self.assertTrue(self.window.tube_page.controller.setup.assignments.has_part)
        self.assertIn("内存配置已更新", result)
        self.assertIn("修改字段：operations, setup.assignments", result)
        self.assertIn("受影响节点：operation, part", result)
        self.assertEqual(self.service.state_json()["config"]["status"], "memory")

    def test_forbidden_script_does_not_reach_controller(self) -> None:
        response = self.service.execute_script("import os\nos.system('whoami')")

        self.assertIn("E_SCRIPT_FORBIDDEN", response)
        self.assertEqual(self.service.kernel.revision, 0)
        self.assertEqual(self.window.tube_page.controller.operations, ())

    def test_query_remains_available_while_mutation_reports_load_busy(self) -> None:
        self.window.load_coordinator.busy = True

        state = self.service.execute_script("tube.state()")
        blocked = self.service.execute_script("tube.create_operation()")

        self.assertIn('"setup_id"', state)
        self.assertIn("E_LOAD_BUSY", blocked)
        self.assertEqual(self.service.kernel.revision, 0)

    def test_gui_invocation_uses_same_revision_and_refresh_boundary(self) -> None:
        assert self.window.tube_page.executor is not None
        result = self.window.tube_page.executor(
            CommandInvocation("create_operation", origin="gui", command_id="gui-1")
        )

        self.assertEqual(result.revision, 1)
        self.assertEqual(result.command_id, "gui-1")
        self.assertEqual(self.window.tube_page.refresh_count, 1)
        self.assertEqual(self.console.revision, 1)

    def test_completion_matches_full_quoted_resource_identifier(self) -> None:
        candidates = self.service.completions('tube.set_machine("builtin.machine.cart')

        self.assertIn("builtin.machine.cartesian_reference.v1", candidates)

    def test_english_error_and_file_dialog_text(self) -> None:
        self.window.language = "en"

        response = self.service.execute_script("import os")
        with mock.patch(
            "five_axis_slicer.tube_script_service.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ) as dialog:
            self.service.load_script_dialog()

        self.assertIn("line 1, column 1", response)
        self.assertNotIn("第 1 行", response)
        self.assertEqual(dialog.call_args.args[1], "Load Tube Setup Script")

    def test_domain_error_exposes_clickable_setup_node(self) -> None:
        response = self.service.execute_script("tube.set_model_cs(z=(0, 0, 0))")
        self.console.node_link_requested.emit("model_cs")

        self.assertIn("[[node:model_cs]]", response)
        self.assertEqual(self.window.tube_page.selected_node, "model_cs")


if __name__ == "__main__":
    unittest.main()
