from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt5.QtCore import Qt, QSignalBlocker
from PyQt5.QtWidgets import (
    QAction,
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .automation import AutomationServer
from .localization import tr
from .models import CadModel
from .project_io import save_project
from .step_loader import StepLoadError, load_step
from .viewer import ModelViewer


OBJECT_ID_ROLE = Qt.UserRole
DISPLAY_TEXT_ROLE = Qt.UserRole + 1


class MainWindow(QMainWindow):
    def __init__(self, http_host: str = "127.0.0.1", http_port: int = 8765) -> None:
        super().__init__()
        self.language = "zh"
        self.model: CadModel | None = None
        self.last_project_dir: Path | None = None
        self._refreshing_lists = False

        self.viewer = ModelViewer(self)
        self.viewer.set_selection_callback(self._on_viewer_selection)
        self.automation = AutomationServer(http_host, http_port, self.handle_automation)
        self.automation.start()

        self._build_ui()
        self._bind_shortcuts()
        self._apply_style()
        self.retranslate()
        self.statusBar().showMessage(tr(self.language, "http", url=self.automation.url))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.automation.stop()
        super().closeEvent(event)

    def open_model_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr(self.language, "open"),
            "",
            "STEP Files (*.step *.stp)",
        )
        if path:
            self.open_model(path)

    def open_model(self, path: str | Path, show_dialog: bool = True) -> dict[str, Any]:
        try:
            model = load_step(path)
            self.model = model
            self.viewer.load_model(model)
            self.refresh_lists()
            message = tr(
                self.language,
                "status_loaded",
                body_count=len(model.bodies),
                edge_count=len(model.edges),
            )
            if len(model.bodies) == 1:
                message += " | " + tr(self.language, "status_single_body")
            self.statusBar().showMessage(message)
            return self.current_state()
        except StepLoadError as exc:
            if show_dialog:
                self.show_error(str(exc))
            else:
                self.statusBar().showMessage(tr(self.language, "status_error", message=str(exc)))
            raise

    def save_project_dialog(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, tr(self.language, "save"), "")
        if directory:
            self.save_project_to(directory)

    def save_project_to(self, directory: str | Path) -> dict[str, Any]:
        if self.model is None:
            raise RuntimeError(tr(self.language, "no_model"))
        path = save_project(directory, self.model, self.viewer.selection)
        self.last_project_dir = Path(directory)
        self.statusBar().showMessage(tr(self.language, "status_saved", path=path))
        return {"project_json": str(path)}

    def refresh_lists(self) -> None:
        self._refreshing_lists = True
        body_blocker = QSignalBlocker(self.body_list)
        edge_blocker = QSignalBlocker(self.edge_list)
        try:
            self.body_list.clear()
            self.edge_list.clear()
            if self.model is None:
                return
            selected_bodies = self.viewer.selection.body_ids
            selected_edges = self.viewer.selection.edge_ids
            for body in self.model.bodies:
                label = f"{body.body_id}  {body.name}  edges={len(body.edge_ids)}"
                self._add_selection_item(self.body_list, body.body_id, label, body.body_id in selected_bodies)
            for edge in self.model.edges:
                length = "" if edge.length_hint is None else f"  len≈{edge.length_hint:.3f}"
                label = f"{edge.edge_id}{length}"
                self._add_selection_item(self.edge_list, edge.edge_id, label, edge.edge_id in selected_edges)
        finally:
            del body_blocker
            del edge_blocker
            self._refreshing_lists = False

    def handle_automation(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path == "/health":
            return {"status": "ready", "app": "5AxisSclicer V2.0"}
        if path == "/state":
            return self.current_state()
        if path == "/model/open":
            return self.open_model(payload["path"], show_dialog=False)
        if path == "/selection/mode":
            self.set_mode(str(payload["mode"]))
            return self.current_state()
        if path == "/selection/set":
            self.viewer.set_selection(payload.get("body_ids"), payload.get("edge_ids"))
            self.refresh_lists()
            return self.current_state()
        if path == "/selection/clear":
            self.viewer.clear_selection()
            self.refresh_lists()
            return self.current_state()
        if path == "/camera":
            self.viewer.camera_command(str(payload.get("command", "fit")), float(payload.get("value", 10.0)))
            return self.current_state()
        if path == "/project/save":
            return self.save_project_to(payload["directory"])
        raise RuntimeError(f"Unknown endpoint: {path}")

    def current_state(self) -> dict[str, Any]:
        model_state = None
        if self.model is not None:
            model_state = {
                "source_path": str(self.model.source_path),
                "source_hash": self.model.source_hash,
                "body_count": len(self.model.bodies),
                "edge_count": len(self.model.edges),
                "bodies": [body.to_json() for body in self.model.bodies],
            }
        return {
            "language": self.language,
            "model": model_state,
            "selection": self.viewer.selection.to_json(),
        }

    def set_mode(self, mode: str) -> None:
        if mode != "edge":
            raise RuntimeError(
                "Preview picking is fixed to edge mode; use /selection/set with body_ids to select bodies."
            )
        self.viewer.set_mode("edge")
        self.refresh_lists()

    def clear_selection(self) -> None:
        self.viewer.clear_selection()
        self.refresh_lists()

    def toggle_language(self) -> None:
        self.language = "en" if self.language == "zh" else "zh"
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(tr(self.language, "app_title"))
        self.open_action.setText(tr(self.language, "open"))
        self.save_action.setText(tr(self.language, "save"))
        self.clear_action.setText(tr(self.language, "clear"))
        self.fit_action.setText(tr(self.language, "fit"))
        self.home_action.setText(tr(self.language, "home"))
        self.open_button.setText(tr(self.language, "open"))
        self.save_button.setText(tr(self.language, "save"))
        self.clear_button.setText(tr(self.language, "clear"))
        self.language_button.setText(tr(self.language, "language"))
        self.left_title.setText(tr(self.language, "left_title"))
        self.right_title.setText(tr(self.language, "right_title"))
        self.body_label.setText(tr(self.language, "body_list"))
        self.edge_label.setText(tr(self.language, "edge_list"))

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(tr(self.language, "status_error", message=message))
        QMessageBox.warning(self, tr(self.language, "app_title"), message)

    def _build_ui(self) -> None:
        self.open_action = QAction(self)
        self.save_action = QAction(self)
        self.clear_action = QAction(self)
        self.fit_action = QAction(self)
        self.home_action = QAction(self)
        self.open_action.triggered.connect(self.open_model_dialog)
        self.save_action.triggered.connect(self.save_project_dialog)
        self.clear_action.triggered.connect(self.clear_selection)
        self.fit_action.triggered.connect(self.viewer.fit_view)
        self.home_action.triggered.connect(self.viewer.home_view)

        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.clear_action)
        toolbar.addSeparator()
        toolbar.addAction(self.fit_action)
        toolbar.addAction(self.home_action)
        self.addToolBar(toolbar)

        self.left_title = QLabel()
        self.open_button = QPushButton()
        self.save_button = QPushButton()
        self.clear_button = QPushButton()
        self.language_button = QPushButton()
        self.open_button.clicked.connect(self.open_model_dialog)
        self.save_button.clicked.connect(self.save_project_dialog)
        self.clear_button.clicked.connect(self.clear_selection)
        self.language_button.clicked.connect(self.toggle_language)

        left_panel = QFrame()
        left_panel.setObjectName("glassPanel")
        left_panel.setMinimumWidth(210)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(self.left_title)
        left_layout.addWidget(self.open_button)
        left_layout.addWidget(self.save_button)
        left_layout.addWidget(self.clear_button)
        left_layout.addStretch(1)
        left_layout.addWidget(self.language_button)

        self.right_title = QLabel()
        self.body_label = QLabel()
        self.edge_label = QLabel()
        self.body_list = QListWidget()
        self.edge_list = QListWidget()
        self.body_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.edge_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.body_list.itemSelectionChanged.connect(self._on_body_list_selection_changed)
        self.edge_list.itemSelectionChanged.connect(self._on_edge_list_selection_changed)
        right_panel = QFrame()
        right_panel.setObjectName("glassPanel")
        right_panel.setMinimumWidth(285)
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(self.right_title)
        right_layout.addWidget(self.body_label)
        right_layout.addWidget(self.body_list, 1)
        right_layout.addWidget(self.edge_label)
        right_layout.addWidget(self.edge_list, 2)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.viewer)
        splitter.addWidget(right_panel)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(2, False)
        splitter.setSizes([220, 850, 300])

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(splitter)
        self.setCentralWidget(container)
        self.setStatusBar(QStatusBar(self))
        self.resize(1440, 900)

    def _bind_shortcuts(self) -> None:
        self.open_action.setShortcut("Ctrl+O")
        self.save_action.setShortcut("Ctrl+S")
        self.clear_action.setShortcut("Esc")
        self.fit_action.setShortcut("F")
        self.home_action.setShortcut("H")
        zoom_in = QAction(self)
        zoom_in.setShortcut("Ctrl++")
        zoom_in.triggered.connect(lambda: self.viewer.camera_command("zoom", 1.15))
        zoom_out = QAction(self)
        zoom_out.setShortcut("Ctrl+-")
        zoom_out.triggered.connect(lambda: self.viewer.camera_command("zoom", 0.87))
        self.addActions([zoom_in, zoom_out])

    def _apply_style(self) -> None:
        QApplication.setStyle("Fusion")
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #111214;
                color: #f4f4f2;
                font-family: "Segoe UI", "Microsoft YaHei UI";
                font-size: 15px;
            }
            QToolBar {
                background: rgba(255, 255, 255, 0.08);
                border: 0;
                spacing: 8px;
                padding: 9px;
            }
            QToolButton, QPushButton {
                background: rgba(255, 255, 255, 0.16);
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 8px;
                padding: 9px 14px;
                color: #f8f8f6;
            }
            QToolButton:hover, QPushButton:hover {
                background: rgba(255, 255, 255, 0.24);
            }
            QLabel {
                color: #eeeeec;
            }
            QLabel:first-child {
                font-size: 18px;
                font-weight: 600;
            }
            #glassPanel {
                background: rgba(245, 245, 245, 0.10);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 12px;
            }
            QListWidget {
                background: rgba(0, 0, 0, 0.20);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 8px;
                padding: 7px;
            }
            QListWidget::item {
                padding: 6px;
            }
            QListWidget::item:selected {
                background: rgba(255, 255, 255, 0.20);
            }
            QStatusBar {
                background: rgba(255, 255, 255, 0.08);
                color: #d8d8d6;
            }
            """
        )

    def _on_viewer_selection(self, kind: str, object_id: str) -> None:
        self.refresh_lists()

    def _on_body_list_selection_changed(self) -> None:
        if self._refreshing_lists or self.model is None:
            return
        self.viewer.set_selection(body_ids=self._selected_item_ids(self.body_list))
        self._sync_list_item_text(self.body_list)

    def _on_edge_list_selection_changed(self) -> None:
        if self._refreshing_lists or self.model is None:
            return
        self.viewer.set_selection(edge_ids=self._selected_item_ids(self.edge_list))
        self._sync_list_item_text(self.edge_list)

    def _add_selection_item(self, list_widget: QListWidget, object_id: str, label: str, selected: bool) -> None:
        item = QListWidgetItem(f"{'✓ ' if selected else ''}{label}")
        item.setData(OBJECT_ID_ROLE, object_id)
        item.setData(DISPLAY_TEXT_ROLE, label)
        list_widget.addItem(item)
        item.setSelected(selected)

    def _selected_item_ids(self, list_widget: QListWidget) -> list[str]:
        ids: list[str] = []
        for item in list_widget.selectedItems():
            object_id = item.data(OBJECT_ID_ROLE)
            if object_id is not None:
                ids.append(str(object_id))
        return ids

    def _sync_list_item_text(self, list_widget: QListWidget) -> None:
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            label = item.data(DISPLAY_TEXT_ROLE)
            if label is not None:
                item.setText(f"{'✓ ' if item.isSelected() else ''}{label}")
