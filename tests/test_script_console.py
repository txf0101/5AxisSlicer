from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QSettings, Qt, QUrl
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QAction, QApplication, QMainWindow, QMenu, QStackedWidget, QWidget

from five_axis_slicer.script_console import ScriptConsoleDock, ScriptConsoleManager


class ScriptConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.settings = QSettings(str(Path(directory.name) / "settings.ini"), QSettings.IniFormat)
        self.settings.setValue("script_console/visible", True)

    def test_console_is_hidden_on_first_use_and_can_be_opened(self) -> None:
        self.settings.remove("script_console/visible")
        window = QMainWindow()
        self.addCleanup(window.close)
        stack = QStackedWidget()
        stack.addWidget(QWidget())
        tube = QWidget()
        stack.addWidget(tube)
        window.setCentralWidget(stack)
        manager = ScriptConsoleManager(window, stack, tube, QMenu(window), self.settings)
        window.show()
        stack.setCurrentWidget(tube)
        self.app.processEvents()
        self.assertFalse(manager.action.isChecked())
        self.assertFalse(manager.dock.isVisible())

        manager.action.setChecked(True)
        self.app.processEvents()
        self.assertTrue(manager.dock.isVisible())

    def test_executes_buffer_and_persists_deduplicated_history(self) -> None:
        dock = ScriptConsoleDock(self.settings)
        self.addCleanup(dock.close)
        seen: list[str] = []
        dock.set_executor(lambda source: seen.append(source) or "ok r1")

        dock.input.setPlainText("tube.state()")
        dock.execute_current()
        dock.input.setPlainText("tube.state()")
        dock.execute_current()

        self.assertEqual(seen, ["tube.state()", "tube.state()"])
        history = json.loads(str(self.settings.value("script_console/history")))
        self.assertEqual(history, ["tube.state()"])
        self.assertIn("ok r1", dock.output.toPlainText())

    def test_enter_executes_line_and_control_enter_executes_block(self) -> None:
        dock = ScriptConsoleDock(self.settings)
        self.addCleanup(dock.close)
        seen: list[str] = []
        dock.set_executor(lambda source: seen.append(source) or "ok")
        dock.show()
        dock.input.setFocus()

        QTest.keyClicks(dock.input, "tube.state()")
        QTest.keyClick(dock.input, Qt.Key_Return, Qt.ShiftModifier)
        QTest.keyClicks(dock.input, "tube.issues()")
        QTest.keyClick(dock.input, Qt.Key_Return)

        self.assertEqual(seen, ["tube.issues()"])
        self.assertEqual(dock.input.toPlainText(), "tube.state()")

        QTest.keyClick(dock.input, Qt.Key_Return, Qt.ShiftModifier)
        QTest.keyClicks(dock.input, "tube.validate()")
        QTest.keyClick(dock.input, Qt.Key_Return, Qt.ControlModifier)

        self.assertEqual(seen[-1], "tube.state()\ntube.validate()")

    def test_completion_uses_provider_without_executing(self) -> None:
        dock = ScriptConsoleDock(self.settings)
        self.addCleanup(dock.close)
        dock.set_completion_provider(lambda _source: ("set_machine",))
        dock.input.setPlainText("set_mac")
        dock.input.moveCursor(dock.input.textCursor().End)
        dock.complete_current()

        self.assertEqual(dock.input.toPlainText(), "set_machine")

    def test_completion_replaces_full_quoted_resource_id_prefix(self) -> None:
        dock = ScriptConsoleDock(self.settings)
        self.addCleanup(dock.close)
        resource_id = "0ff92885-617b-4144-a03c-9989872454bc"
        dock.set_completion_provider(lambda _source: (resource_id,))
        source = 'tube.set_nozzle("0ff92885-617")'
        dock.input.setPlainText(source)
        cursor = dock.input.textCursor()
        cursor.setPosition(source.index('")'))
        dock.input.setTextCursor(cursor)

        dock.complete_current()

        self.assertEqual(dock.input.toPlainText(), f'tube.set_nozzle("{resource_id}")')

    def test_output_renders_setup_node_marker_as_link(self) -> None:
        dock = ScriptConsoleDock(self.settings)
        self.addCleanup(dock.close)
        seen: list[str] = []
        dock.node_link_requested.connect(seen.append)

        dock.append_output("[E_ARGUMENT_INVALID]\n节点：[[node:model_cs]]")
        dock.output.anchorClicked.emit(QUrl("tube-node:model_cs"))

        self.assertIn("节点：model_cs", dock.output.toPlainText())
        self.assertNotIn("[[node:", dock.output.toPlainText())
        self.assertEqual(seen, ["model_cs"])

    def test_manager_tracks_tube_context_and_guards_viewer_shortcuts(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        stack = QStackedWidget()
        home = QWidget()
        tube = QWidget()
        stack.addWidget(home)
        stack.addWidget(tube)
        window.setCentralWidget(stack)
        menu = QMenu(window)
        actions = tuple(QAction(window) for _ in range(3))
        actions[-1].setEnabled(False)
        window._update_context_actions = lambda: None
        manager = ScriptConsoleManager(
            window,
            stack,
            tube,
            menu,
            self.settings,
            actions,
        )
        window.show()
        self.app.processEvents()

        self.assertFalse(manager.dock.isVisible())
        stack.setCurrentWidget(tube)
        self.app.processEvents()
        self.assertTrue(manager.dock.isVisible())
        manager.dock.input.setFocus()
        self.app.processEvents()
        self.assertTrue(all(not action.isEnabled() for action in actions))
        tube.setFocus()
        self.app.processEvents()
        self.assertEqual([action.isEnabled() for action in actions], [True, True, False])

    def test_parent_visibility_close_and_explicit_collapse_preserve_preference(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        stack = QStackedWidget()
        home = QWidget()
        tube = QWidget()
        stack.addWidget(home)
        stack.addWidget(tube)
        window.setCentralWidget(stack)
        manager = ScriptConsoleManager(window, stack, tube, QMenu(window), self.settings)
        window.show()
        stack.setCurrentWidget(tube)
        self.app.processEvents()

        window.hide()
        self.app.processEvents()
        self.assertTrue(manager.action.isChecked())
        window.show()
        self.app.processEvents()
        self.assertTrue(manager.dock.isVisible())

        window.close()
        self.app.processEvents()
        self.assertTrue(manager.action.isChecked())
        window.show()
        self.app.processEvents()
        self.assertTrue(manager.dock.isVisible())

        manager.collapse_action.setChecked(True)
        self.app.processEvents()
        self.assertTrue(manager.action.isChecked())
        self.assertTrue(manager.dock.isVisible())
        self.assertFalse(manager.dock.widget().isVisible())

        manager.collapse_action.setChecked(False)
        manager.dock.close()
        self.app.processEvents()
        self.assertFalse(manager.action.isChecked())
        self.assertFalse(manager.dock.isVisible())

        manager.action.setChecked(True)
        self.app.processEvents()
        self.assertTrue(manager.dock.isVisible())
        self.assertTrue(manager.dock.widget().isVisible())

    def test_manager_guards_all_dock_focus_and_releases_when_hidden(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        stack = QStackedWidget()
        home = QWidget()
        tube = QWidget()
        stack.addWidget(home)
        stack.addWidget(tube)
        window.setCentralWidget(stack)
        guarded = QAction(window)
        guarded.setEnabled(True)
        window._update_context_actions = lambda: None
        manager = ScriptConsoleManager(
            window,
            stack,
            tube,
            QMenu(window),
            self.settings,
            (guarded,),
        )
        window.show()
        stack.setCurrentWidget(tube)
        self.app.processEvents()

        manager.dock._buttons["clear"].setFocus()
        self.app.processEvents()
        self.assertIs(self.app.focusWidget(), manager.dock._buttons["clear"])
        self.assertFalse(guarded.isEnabled())

        stack.setCurrentWidget(home)
        self.app.processEvents()
        self.assertFalse(manager.dock.isVisible())
        self.assertTrue(guarded.isEnabled())

    def test_manager_saves_height_after_splitter_resize(self) -> None:
        window = QMainWindow()
        self.addCleanup(window.close)
        window.resize(900, 700)
        stack = QStackedWidget()
        tube = QWidget()
        stack.addWidget(tube)
        window.setCentralWidget(stack)
        manager = ScriptConsoleManager(window, stack, tube, QMenu(window), self.settings)
        window.show()
        self.app.processEvents()

        window.resizeDocks([manager.dock], [280], Qt.Vertical)
        self.app.processEvents()
        manager.save_state()

        self.assertGreater(manager.dock.height(), 190)
        self.assertEqual(manager.dock.expanded_height, manager.dock.height())
        self.assertEqual(
            self.settings.value("script_console/height", type=int),
            manager.dock.height(),
        )


if __name__ == "__main__":
    unittest.main()
