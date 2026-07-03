from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
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
from .selection_list import SelectionList, SelectionRow
from .step_loader import StepLoadError, load_step
from .styles import APP_STYLE
from .viewer import ModelViewer


class MainWindow(QMainWindow):
    def __init__(self, http_host: str = "127.0.0.1", http_port: int = 8765) -> None:
        super().__init__()
        self.language = "zh"
        self.model: CadModel | None = None
        self.last_project_dir: Path | None = None

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
        if self.model is None:
            self.body_list.set_rows([], set())
            self.edge_list.set_rows([], set())
            return

        # 右侧列表是 SelectionState 的可视入口；预览区点选 edge 或 HTTP 写入后，
        # 这里按最新状态反向刷新勾选符号。
        self.body_list.set_rows(self._body_rows(), self.viewer.selection.body_ids)
        self.edge_list.set_rows(self._edge_rows(), self.viewer.selection.edge_ids)

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
        self.body_list = SelectionList()
        self.edge_list = SelectionList()
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
        self.setStyleSheet(APP_STYLE)

    def _on_viewer_selection(self, _kind: str, _obj_id: str) -> None:
        self.refresh_lists()

    def _on_body_list_selection_changed(self) -> None:
        if self.model is None:
            return
        self.viewer.set_selection(body_ids=self.body_list.selected_ids())
        self.body_list.sync_marks()

    def _on_edge_list_selection_changed(self) -> None:
        if self.model is None:
            return
        self.viewer.set_selection(edge_ids=self.edge_list.selected_ids())
        self.edge_list.sync_marks()

    def _body_rows(self) -> list[SelectionRow]:
        if self.model is None:
            return []
        return [
            (body.body_id, f"{body.body_id}  {body.name}  edges={len(body.edge_ids)}")
            for body in self.model.bodies
        ]

    def _edge_rows(self) -> list[SelectionRow]:
        if self.model is None:
            return []
        rows: list[SelectionRow] = []
        for edge in self.model.edges:
            length = "" if edge.length_hint is None else f"  len≈{edge.length_hint:.3f}"
            rows.append((edge.edge_id, f"{edge.edge_id}{length}"))
        return rows
