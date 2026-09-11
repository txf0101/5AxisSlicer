"""Qt console for the restricted manufacturing Setup command language."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from typing import Any

from PyQt5.QtCore import QEvent, QObject, QSettings, Qt, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QInputMethodEvent,
    QKeyEvent,
    QTextCharFormat,
    QTextCursor,
    QResizeEvent,
)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QPlainTextEdit,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


_TEXT = {
    "zh": {
        "title": "设置脚本",
        "load_script": "加载脚本",
        "import_config": "导入配置",
        "export_config": "导出副本",
        "reveal_config": "打开位置",
        "clear": "清空输出",
        "apply_drafts": "应用草稿",
        "discard_drafts": "放弃草稿",
        "ready": "配置仅在内存中",
        "prompt": "tube",
        "history_search": "搜索命令历史",
        "history_query": "包含文本",
        "no_match": "没有匹配的历史命令",
        "placeholder": "输入 tube.help() 或 管状.帮助()",
        "unavailable": "[E_COMMAND_UNAVAILABLE] 命令服务尚未就绪",
        "failed": "[E_COMMAND_FAILED] {error}",
    },
    "en": {
        "title": "Setup Script",
        "load_script": "Load Script",
        "import_config": "Import Config",
        "export_config": "Export Copy",
        "reveal_config": "Show Location",
        "clear": "Clear Output",
        "apply_drafts": "Apply Drafts",
        "discard_drafts": "Discard Drafts",
        "ready": "Configuration is in memory only",
        "prompt": "tube",
        "history_search": "Search command history",
        "history_query": "Contains",
        "no_match": "No matching command",
        "placeholder": "Enter tube.help() or 管状.帮助()",
        "unavailable": "[E_COMMAND_UNAVAILABLE] Command service is not ready",
        "failed": "[E_COMMAND_FAILED] {error}",
    },
}

_NODE_MARKER = re.compile(r"\[\[node:([a-z_]+)\]\]")


class ScriptInput(QPlainTextEdit):
    """Small multiline editor with REPL-oriented key bindings."""

    execute_requested = pyqtSignal()
    execute_line_requested = pyqtSignal()
    complete_requested = pyqtSignal()
    previous_requested = pyqtSignal()
    next_requested = pyqtSignal()
    search_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preedit_active = False
        self.setMaximumHeight(92)
        self.setTabChangesFocus(False)
        self.setObjectName("scriptConsoleInput")

    def inputMethodEvent(self, event: QInputMethodEvent) -> None:  # noqa: N802 - Qt API
        self._preedit_active = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        key = event.key()
        modifiers = event.modifiers()
        if key in {Qt.Key_Return, Qt.Key_Enter} and not self._preedit_active:
            if modifiers & Qt.ShiftModifier:
                self.textCursor().insertText("\n")
            elif modifiers & Qt.ControlModifier:
                self.execute_requested.emit()
            else:
                self.execute_line_requested.emit()
            return
        if key == Qt.Key_Tab and not (modifiers & Qt.ControlModifier):
            self.complete_requested.emit()
            return
        if key == Qt.Key_R and modifiers & Qt.ControlModifier:
            self.search_requested.emit()
            return
        if key == Qt.Key_Up and self.document().blockCount() == 1:
            self.previous_requested.emit()
            return
        if key == Qt.Key_Down and self.document().blockCount() == 1:
            self.next_requested.emit()
            return
        if key == Qt.Key_Escape:
            self.clear()
            return
        super().keyPressEvent(event)


class ScriptOutput(QTextBrowser):
    """Bounded plain-text output with explicit Setup-node anchors."""

    node_link_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenLinks(False)
        self.document().setMaximumBlockCount(2_000)
        self.anchorClicked.connect(self._open_node_link)

    def append_message(self, text: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        if not self.document().isEmpty():
            cursor.insertBlock()
            cursor.insertBlock()
        source = str(text).rstrip()
        offset = 0
        for match in _NODE_MARKER.finditer(source):
            cursor.insertText(source[offset : match.start()])
            node = match.group(1)
            link = QTextCharFormat()
            link.setAnchor(True)
            link.setAnchorHref(f"tube-node:{node}")
            link.setFontUnderline(True)
            link.setForeground(QColor("#4ea1ff"))
            cursor.insertText(node, link)
            offset = match.end()
        cursor.insertText(source[offset:])
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _open_node_link(self, url: QUrl) -> None:
        if url.scheme() == "tube-node":
            node = url.path().lstrip("/")
            if node:
                self.node_link_requested.emit(node)


class ScriptConsoleDock(QDockWidget):
    """Presentation-only dock; parsing and execution stay behind callbacks."""

    collapsed_changed = pyqtSignal(bool)
    load_script_requested = pyqtSignal()
    import_config_requested = pyqtSignal()
    export_config_requested = pyqtSignal()
    reveal_config_requested = pyqtSignal()
    apply_drafts_requested = pyqtSignal()
    discard_drafts_requested = pyqtSignal()
    node_link_requested = pyqtSignal(str)

    def __init__(self, settings: QSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("scriptConsoleDock")
        self.setAllowedAreas(Qt.BottomDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
        self._settings = settings
        self._language = "zh"
        self._executor: Callable[[str], str] | None = None
        self._completion: Callable[[str], Sequence[str]] | None = None
        self._revision = 0
        self._collapsed = False
        self._compact = False
        self._expanded_height = 190
        self._history = self._load_history()
        self._history_index = len(self._history)

        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(5)
        toolbar = QHBoxLayout()
        self._buttons = {
            "load_script": self._button(self.load_script_requested.emit),
            "import_config": self._button(self.import_config_requested.emit),
            "export_config": self._button(self.export_config_requested.emit),
            "reveal_config": self._button(self.reveal_config_requested.emit),
            "clear": self._button(self.clear_output),
        }
        for button in self._buttons.values():
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        self.apply_drafts_button = self._button(self.apply_drafts_requested.emit)
        self.discard_drafts_button = self._button(self.discard_drafts_requested.emit)
        toolbar.addWidget(self.apply_drafts_button)
        toolbar.addWidget(self.discard_drafts_button)
        self.status_label = QLabel()
        self.status_label.setObjectName("mutedText")
        toolbar.addWidget(self.status_label)
        layout.addLayout(toolbar)

        self.output = self._build_output()
        layout.addWidget(self.output, 1)

        self.input = self._build_input()
        layout.addWidget(self.input)
        self.setWidget(content)
        self.set_draft_conflict(False)
        self.set_language("zh")
        collapsed = str(settings.value("script_console/collapsed", "false")).lower() == "true"
        self.set_collapsed(collapsed)

    def _button(self, callback: Callable[[], Any]) -> QToolButton:
        button = QToolButton()
        button.clicked.connect(callback)
        return button

    def _build_output(self) -> ScriptOutput:
        output = ScriptOutput()
        output.setObjectName("scriptConsoleOutput")
        output.node_link_requested.connect(self.node_link_requested.emit)
        output.setMinimumHeight(58)
        return output

    def _build_input(self) -> ScriptInput:
        editor = ScriptInput()
        editor.execute_requested.connect(self.execute_current)
        editor.execute_line_requested.connect(self.execute_current_line)
        editor.complete_requested.connect(self.complete_current)
        editor.previous_requested.connect(lambda: self._move_history(-1))
        editor.next_requested.connect(lambda: self._move_history(1))
        editor.search_requested.connect(self.search_history)
        return editor

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if not self._collapsed and self.isVisible() and event.size().height() >= 190:
            self._expanded_height = event.size().height()

    @property
    def expanded_height(self) -> int:
        return self._expanded_height

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    @property
    def compact(self) -> bool:
        return self._compact

    def set_compact(self, compact: bool) -> None:
        """Temporarily collapse the dock when the main window is short."""

        compact = bool(compact) and not self._collapsed
        if compact == self._compact:
            return
        self._compact = compact
        if compact:
            title_height = self.style().pixelMetric(QStyle.PM_TitleBarHeight) + 4
            parent = self.parentWidget()
            self.setMinimumWidth(parent.minimumWidth() if parent is not None else 0)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.widget().hide()
            self.setMinimumHeight(title_height)
            self.setMaximumHeight(title_height)
            self._release_focus()
            return
        self.setMaximumHeight(524_287)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.widget().show()
        self.setMinimumHeight(self._expanded_height)

    def _release_focus(self) -> None:
        focused = QApplication.focusWidget()
        if focused is self or (focused is not None and self.isAncestorOf(focused)):
            focused.clearFocus()

    def set_expanded_height(self, height: int) -> None:
        self._expanded_height = max(190, int(height))
        if not self._collapsed:
            self.setMinimumHeight(self._expanded_height)

    def release_expanded_height(self) -> None:
        if not self._collapsed:
            self.setMinimumHeight(190)

    def set_collapsed(self, collapsed: bool) -> None:
        collapsed = bool(collapsed)
        if self._compact:
            self._compact = False
        if collapsed == self._collapsed and self.widget().isVisible() != collapsed:
            return
        if collapsed:
            self._expanded_height = max(190, self.height())
            title_height = self.style().pixelMetric(QStyle.PM_TitleBarHeight) + 4
            self.widget().hide()
            self.setMinimumHeight(title_height)
            self.setMaximumHeight(title_height)
        else:
            self.setMaximumHeight(524_287)
            self.widget().show()
            self.setMinimumHeight(self._expanded_height)
        self._collapsed = collapsed
        self._settings.setValue("script_console/collapsed", collapsed)
        self.collapsed_changed.emit(collapsed)

    def set_executor(self, executor: Callable[[str], str]) -> None:
        self._executor = executor

    def set_completion_provider(
        self,
        provider: Callable[[str], Sequence[str]],
    ) -> None:
        self._completion = provider

    def set_language(self, language: str) -> None:
        default_status = self.status_label.text() in {value["ready"] for value in _TEXT.values()}
        self._language = language if language in _TEXT else "zh"
        text = _TEXT[self._language]
        self.setWindowTitle(text["title"])
        for name, button in self._buttons.items():
            button.setText(text[name])
        self.apply_drafts_button.setText(text["apply_drafts"])
        self.discard_drafts_button.setText(text["discard_drafts"])
        self.input.setPlaceholderText(text["placeholder"])
        if not self.status_label.text() or default_status:
            self.status_label.setText(text["ready"])

    def set_code_font(self, family: str, point_size: int = 10) -> None:
        font = QFont(family, point_size)
        font.setStyleHint(QFont.Monospace)
        self.output.setFont(font)
        self.input.setFont(font)

    def set_status(self, text: str, *, revision: int | None = None) -> None:
        if revision is not None:
            self._revision = int(revision)
        self.status_label.setText(str(text))

    def set_draft_conflict(self, visible: bool) -> None:
        self.apply_drafts_button.setVisible(bool(visible))
        self.discard_drafts_button.setVisible(bool(visible))

    def set_mutations_enabled(self, enabled: bool) -> None:
        self.input.setEnabled(bool(enabled))
        self._buttons["load_script"].setEnabled(bool(enabled))
        self._buttons["import_config"].setEnabled(bool(enabled))

    def has_input_focus(self) -> bool:
        return self.input.hasFocus()

    def clear_input(self) -> None:
        self.input.clear()

    def clear_output(self) -> None:
        self.output.clear()

    def append_output(self, text: str) -> None:
        self.output.append_message(text)

    def execute_current(self) -> None:
        source = self.input.toPlainText().strip()
        if not source:
            return
        self.input.clear()
        self._execute_source(source)

    def execute_current_line(self) -> None:
        text = self.input.toPlainText()
        lines = text.splitlines()
        if not lines:
            return
        index = min(text[: self.input.textCursor().position()].count("\n"), len(lines) - 1)
        source = lines.pop(index).strip()
        self.input.setPlainText("\n".join(lines))
        if lines:
            cursor = self.input.textCursor()
            cursor.movePosition(cursor.End)
            self.input.setTextCursor(cursor)
        if source:
            self._execute_source(source)

    def _execute_source(self, source: str) -> None:
        self._remember(source)
        prompt = _TEXT[self._language]["prompt"]
        self.append_output(f"{prompt} [r{self._revision}]> {source}")
        if self._executor is None:
            self.append_output(_TEXT[self._language]["unavailable"])
            return
        try:
            response = self._executor(source)
        except Exception as exc:  # UI boundary keeps the console usable.
            response = _TEXT[self._language]["failed"].format(error=exc)
        if response:
            self.append_output(response)

    def complete_current(self) -> None:
        if self._completion is None:
            return
        source = self.input.toPlainText()
        candidates = tuple(dict.fromkeys(self._completion(source)))
        if not candidates:
            return
        if len(candidates) > 1:
            self.append_output("  ".join(candidates[:20]))
            return
        candidate = candidates[0]
        cursor = self.input.textCursor()
        end = cursor.position()
        cursor.setPosition(_completion_start(self.input.toPlainText(), end))
        cursor.setPosition(end, cursor.KeepAnchor)
        cursor.insertText(candidate)
        self.input.setTextCursor(cursor)

    def search_history(self) -> None:
        text = _TEXT[self._language]
        query, accepted = QInputDialog.getText(
            self,
            text["history_search"],
            text["history_query"],
        )
        if not accepted:
            return
        match = next((item for item in reversed(self._history) if query in item), None)
        if match is None:
            self.append_output(text["no_match"])
            return
        self.input.setPlainText(match)
        self.input.moveCursor(self.input.textCursor().End)

    def _move_history(self, step: int) -> None:
        if not self._history:
            return
        self._history_index = min(
            len(self._history),
            max(0, self._history_index + int(step)),
        )
        value = (
            "" if self._history_index == len(self._history) else self._history[self._history_index]
        )
        self.input.setPlainText(value)
        self.input.moveCursor(self.input.textCursor().End)

    def _remember(self, source: str) -> None:
        if not self._history or self._history[-1] != source:
            self._history.append(source)
            del self._history[:-200]
            self._settings.setValue(
                "script_console/history",
                json.dumps(self._history, ensure_ascii=False),
            )
        self._history_index = len(self._history)

    def _load_history(self) -> list[str]:
        raw = self._settings.value("script_console/history", "[]")
        try:
            values = json.loads(str(raw))
        except (TypeError, ValueError):
            return []
        if not isinstance(values, list):
            return []
        return [str(value) for value in values[-200:] if isinstance(value, str)]


class ScriptConsoleManager(QObject):
    """Own dock visibility without adding lifecycle branches to MainWindow."""

    def __init__(
        self,
        window: QMainWindow,
        stack: QStackedWidget,
        tube_page: QWidget,
        tools_menu: QMenu,
        settings: QSettings,
        guarded_actions: Sequence[QAction] = (),
        compact_height: int | None = None,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._stack = stack
        self._tube_page = tube_page
        self._settings = settings
        self._compact_height = compact_height
        self._height_restored = False
        self._guarded_actions = tuple(guarded_actions)
        self._guarded_action_states: dict[QAction, bool] | None = None
        self.dock = ScriptConsoleDock(settings, window)
        self.dock.set_code_font("Cascadia Mono")
        application = QApplication.instance()
        if application is not None:
            application.focusChanged.connect(self._application_focus_changed)
        self.dock.collapsed_changed.connect(self._collapsed_changed)
        window.installEventFilter(self)
        window.addDockWidget(Qt.BottomDockWidgetArea, self.dock)
        self.action = QAction(window)
        self.action.setCheckable(True)
        visible = str(settings.value("script_console/visible", "true")).lower() != "false"
        self.action.setChecked(visible)
        self.action.toggled.connect(self._set_preference)
        self.dock.visibilityChanged.connect(self._visibility_changed)
        tools_menu.addSeparator()
        tools_menu.addAction(self.action)
        self.collapse_action = QAction(window)
        self.collapse_action.setCheckable(True)
        self.collapse_action.setChecked(self.dock.collapsed)
        self.collapse_action.toggled.connect(self.dock.set_collapsed)
        tools_menu.addAction(self.collapse_action)
        stack.currentChanged.connect(self._page_changed)
        self._syncing_visibility = False
        self._sync_visibility()

    def set_language(self, language: str) -> None:
        self.action.setText("设置脚本" if language == "zh" else "Setup Script")
        self.collapse_action.setText(
            "折叠设置脚本" if language == "zh" else "Collapse Setup Script"
        )
        self.dock.set_language(language)

    def save_state(self) -> None:
        self._settings.setValue("script_console/height", self.dock.expanded_height)

    def add_guarded_actions(self, actions: Sequence[QAction]) -> None:
        self._guarded_actions += tuple(actions)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if watched is self._window and event.type() == QEvent.Show:
            QTimer.singleShot(0, self._restore_height)
        elif watched is self._window and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._sync_compact_mode)
        return super().eventFilter(watched, event)

    def _application_focus_changed(
        self,
        _previous: QWidget | None,
        current: QWidget | None,
    ) -> None:
        self._set_shortcut_guard(self._owns_focus(current))

    def _set_shortcut_guard(self, guarded: bool) -> None:
        if guarded:
            if self._guarded_action_states is None:
                self._guarded_action_states = {
                    action: action.isEnabled() for action in self._guarded_actions
                }
            for action in self._guarded_actions:
                action.setEnabled(False)
            return
        states = self._guarded_action_states
        self._guarded_action_states = None
        if states is None:
            return
        for action, enabled in states.items():
            action.setEnabled(enabled)
        update = getattr(self._window, "_update_context_actions", None)
        if callable(update):
            update()

    def _owns_focus(self, widget: QWidget | None) -> bool:
        return widget is self.dock or (widget is not None and self.dock.isAncestorOf(widget))

    def _release_console_focus(self) -> None:
        focused = QApplication.focusWidget()
        if self._owns_focus(focused) and focused is not None:
            focused.clearFocus()
        self._set_shortcut_guard(False)

    def _collapsed_changed(self, collapsed: bool) -> None:
        if self.collapse_action.isChecked() != collapsed:
            self.collapse_action.setChecked(collapsed)
        if collapsed:
            self._release_console_focus()

    def _page_changed(self, _index: int) -> None:
        self._sync_visibility()
        self._sync_compact_mode()

    def _set_preference(self, enabled: bool) -> None:
        self._settings.setValue("script_console/visible", bool(enabled))
        self._sync_visibility()

    def _visibility_changed(self, visible: bool) -> None:
        if not visible:
            self.save_state()
            if (
                not self._syncing_visibility
                and self._window.isVisible()
                and self._stack.currentWidget() is self._tube_page
            ):
                self.action.setChecked(False)

    def _sync_visibility(self) -> None:
        should_show = self._stack.currentWidget() is self._tube_page and self.action.isChecked()
        if not should_show:
            self._release_console_focus()
        self._syncing_visibility = True
        try:
            self.dock.setVisible(should_show)
        finally:
            self._syncing_visibility = False
        if should_show and self._window.isVisible():
            self._set_shortcut_guard(self._owns_focus(QApplication.focusWidget()))
            QTimer.singleShot(0, self._restore_height)

    def _sync_compact_mode(self) -> None:
        compact = (
            self._compact_height is not None
            and self._window.height() < self._compact_height
            and self._stack.currentWidget() is self._tube_page
            and self.dock.isVisible()
        )
        self.dock.set_compact(compact)

    def _restore_height(self) -> None:
        if self._height_restored or not self.dock.isVisible():
            return
        height = max(140, int(self._settings.value("script_console/height", 190)))
        self.dock.set_expanded_height(height)
        self._window.resizeDocks([self.dock], [height], Qt.Vertical)
        QTimer.singleShot(0, self.dock.release_expanded_height)
        self._sync_compact_mode()
        self._height_restored = True


def _completion_start(source: str, cursor_position: int) -> int:
    before_cursor = source[:cursor_position]
    quoted = re.search(r"[\"']([^\r\n\"']*)$", before_cursor)
    if quoted is not None:
        return quoted.start(1)
    token = re.search(r"[\w\u4e00-\u9fff-]*$", before_cursor)
    return cursor_position if token is None else token.start()


def install_script_console(window: Any) -> ScriptConsoleManager:
    """Install the dock using the shell's existing widgets and actions."""

    manager = ScriptConsoleManager(
        window,
        window.stack,
        window.tube_page,
        window.tools_menu,
        window.settings,
        (window.clear_action, window.fit_action, window.home_view_action),
        compact_height=820,
    )
    window.script_console = manager.dock
    window.script_console_action = manager.action
    return manager


__all__ = [
    "ScriptConsoleDock",
    "ScriptConsoleManager",
    "ScriptInput",
    "install_script_console",
]
