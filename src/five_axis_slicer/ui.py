from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable

from PyQt5.QtCore import QEventLoop, QSettings, Qt, QTimer
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .automation import AutomationServer
from .background_load import ResultLoadCoordinator
from .gcode_preview import ROLE_COLORS, load_gcode, rgb_to_hex, role_label
from .localization import tr
from .models import CadModel
from .package_assets import IMPELLER_FOUR_PANEL_REFERENCE
from .paper_export import audit_source_file, export_paper_preview
from .project_io import save_project
from .result_preview import ResultCommitError, ResultPreviewPage
from .result_state import LoadRequest, LoadResult
from .selection_list import SelectionList, SelectionRow
from .step_loader import StepLoadError, load_step
from .styles import APP_STYLE
from .viewer import ModelViewer


ROOT = Path(__file__).resolve().parents[2]
DEMO_STEP = ROOT / "example" / "叶轮" / "叶轮.stp"
DEMO_GCODE = ROOT / "example" / "叶轮" / "叶轮完整.gcode"
REFERENCE_IMAGE = IMPELLER_FOUR_PANEL_REFERENCE


@dataclass(frozen=True, slots=True)
class WorkbenchInfo:
    key: str
    title_zh: str
    title_en: str
    summary_zh: str
    summary_en: str
    status_zh: str
    status_en: str


WORKBENCHES: tuple[WorkbenchInfo, ...] = (
    WorkbenchInfo(
        "planar",
        "Planar Workbench",
        "Planar Workbench",
        "平面沉积、基体打印、层状填充和薄壁轮廓。",
        "Planar deposition, base build, layer fill, and thin-wall contours.",
        "Preview",
        "Preview",
    ),
    WorkbenchInfo(
        "curve",
        "Curve Workbench",
        "Curve Workbench",
        "沿 STEP 边线和空间曲线生成单道或多道沉积路径。",
        "Single-pass or multi-pass deposition along STEP edges and spatial curves.",
        "P0",
        "P0",
    ),
    WorkbenchInfo(
        "freeform",
        "Freeform Workbench",
        "Freeform Workbench",
        "面向曲面贴合、曲面加强和导电线路沉积。",
        "Conformal coating, surface reinforcement, and conductive traces.",
        "Preview",
        "Preview",
    ),
    WorkbenchInfo(
        "rotary",
        "Rotary Workbench",
        "Rotary Workbench",
        "圆柱、回转件和轴类零件的旋转沉积。",
        "Rotary deposition for cylinders, turned parts, and shaft-like parts.",
        "Locked",
        "Locked",
    ),
    WorkbenchInfo(
        "tube",
        "Tube Workbench",
        "Tube Workbench",
        "弯管、流道和中心线驱动结构的路径预处理。",
        "Preprocessing for tubes, channels, and centerline-driven structures.",
        "Locked",
        "Locked",
    ),
    WorkbenchInfo(
        "research",
        "Research Workbench",
        "Research Workbench",
        "锥面层、标量场曲面切片和强度导向路径研究。",
        "Conical layers, scalar-field surface slicing, and research paths.",
        "R&D",
        "R&D",
    ),
)


class MainWindow(QMainWindow):
    def __init__(
        self,
        http_host: str = "127.0.0.1",
        http_port: int = 8765,
        result_viewer_factory: Callable[[QWidget], QWidget] | None = None,
    ) -> None:
        super().__init__()
        self.settings = QSettings("5AxisSclicer", "5AxisSclicer V2.0")
        saved_language = str(self.settings.value("language", "zh"))
        self.language = saved_language if saved_language in {"zh", "en"} else "zh"
        self.model: CadModel | None = None
        self.gcode_preview = None
        self.last_project_dir: Path | None = None
        self.current_workbench_key = "curve"
        self.current_operation = "imported_nc_review"
        self._updating_layer_controls = False
        self._updating_progress_controls = False
        self._result_request_sequence = 0
        self._close_pending = False
        self._result_viewer_factory = result_viewer_factory
        self._result_export_sequence = 0
        self._result_export_state: dict[str, Any] = {
            "status": "idle",
            "job_id": None,
            "outputs": [],
            "error": "",
        }
        self._result_load_metrics: dict[str, Any] = {}
        self.localized_groups: list[tuple[QGroupBox, str]] = []
        self.localized_labels: list[tuple[QLabel, str]] = []

        self.viewer = ModelViewer(self)
        self.viewer.set_selection_callback(self._on_viewer_selection)
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(250)
        self.progress_timer.timeout.connect(self._advance_progress)
        self.result_loader = ResultLoadCoordinator(self)
        self.result_loader.progress.connect(self._on_result_load_progress)
        self.result_loader.completed.connect(self._on_result_load_completed)
        self.result_loader.failed.connect(self._on_result_load_failed)
        self.result_loader.cancelled.connect(self._on_result_load_cancelled)
        self.result_loader.busy_changed.connect(self._on_result_busy_changed)
        self.automation = AutomationServer(http_host, http_port, self.handle_automation)

        self._build_ui()
        self._bind_shortcuts()
        self._apply_style()
        self.retranslate()
        self._show_home()
        self.automation.start()
        self.statusBar().showMessage(tr(self.language, "http", url=self.automation.url))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._block_ui_during_result_export():
            event.ignore()
            return
        if not self.result_loader.shutdown(timeout_ms=100):
            self._close_pending = True
            event.ignore()
            self.statusBar().showMessage(tr(self.language, "status_waiting_for_loader_shutdown"))
            QTimer.singleShot(100, self._retry_close_after_result_loader)
            return
        self._close_pending = False
        self.result_page.shutdown()
        self.automation.stop()
        super().closeEvent(event)

    def _retry_close_after_result_loader(self) -> None:
        if not self._close_pending:
            return
        if self.result_loader.wait_for_shutdown(timeout_ms=0):
            self._close_pending = False
            self.close()
            return
        QTimer.singleShot(100, self._retry_close_after_result_loader)

    def open_model_dialog(self) -> None:
        if self._block_ui_during_result_export():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr(self.language, "open_step"),
            "",
            "STEP Files (*.step *.stp)",
        )
        if path:
            self.open_model(path)

    def open_gcode_dialog(self) -> None:
        if self._block_ui_during_result_export():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr(self.language, "open_gcode"),
            "",
            "NC/G-code Files (*.gcode *.nc *.tap *.txt)",
        )
        if path:
            self.open_gcode(path)

    def open_result_model_dialog(self) -> None:
        if self._block_ui_during_result_export():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr(self.language, "dialog_open_step_title"),
            "",
            tr(self.language, "file_filter_step"),
        )
        if path:
            self.start_result_load(model_path=path)

    def open_result_gcode_dialog(self) -> None:
        if self._block_ui_during_result_export():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr(self.language, "dialog_open_gcode_title"),
            "",
            tr(self.language, "file_filter_gcode"),
        )
        if path:
            self.start_result_load(gcode_path=path)

    def load_results_demo(self) -> dict[str, Any]:
        return self.start_result_load(
            model_path=DEMO_STEP if DEMO_STEP.exists() else None,
            gcode_path=DEMO_GCODE if DEMO_GCODE.exists() else None,
        )

    def slice_results(self) -> dict[str, Any]:
        state = self.result_page.state
        model_path = state.selected_model_path or state.active_model_path
        gcode_path = state.selected_gcode_path or state.active_gcode_path
        if gcode_path is None:
            raise RuntimeError(tr(self.language, "error_invalid_gcode"))
        return self.start_result_load(model_path=model_path, gcode_path=gcode_path)

    def start_result_load(
        self,
        *,
        model_path: str | Path | None = None,
        gcode_path: str | Path | None = None,
    ) -> dict[str, Any]:
        if self._result_export_state["status"] in {"queued", "running"}:
            raise RuntimeError(tr(self.language, "error_load_while_exporting"))
        if model_path is None and gcode_path is None:
            raise RuntimeError(tr(self.language, "no_project_content"))
        self._result_request_sequence += 1
        request = LoadRequest(
            request_id=self._result_request_sequence,
            model_path=model_path,
            gcode_path=gcode_path,
        )
        self._result_load_metrics = {
            "request_id": request.request_id,
            "started_perf_counter": time.perf_counter(),
            "status": "loading",
        }
        self.result_page.begin_load(request)
        self._show_results()
        self.result_loader.start(request)
        self._update_context_actions()
        return {
            "accepted": True,
            "request_id": request.request_id,
            "results": self.result_page.state_json(),
        }

    def cancel_result_load(self) -> None:
        if self.result_loader.busy:
            self.result_loader.cancel()
            self.statusBar().showMessage(tr(self.language, "result_cancel_requested"))

    def _on_result_load_progress(self, request_id: object, phase: str, fraction: float) -> None:
        self.result_page.set_load_progress(request_id, phase, fraction)

    def _on_result_load_completed(self, result: LoadResult) -> None:
        try:
            accepted = self.result_page.commit_load(result)
        except ResultCommitError as exc:
            message = str(exc)
            self.result_page.fail_load(result.request_id, message)
            self.statusBar().showMessage(tr(self.language, "error_load_failed", message=message))
            self._update_context_actions()
            self._finish_result_load_metric(result.request_id, "error", message)
            return
        if not accepted:
            return
        if result.model is not None:
            self.model = result.model
        if result.gcode_preview is not None:
            self.gcode_preview = result.gcode_preview
        preview_summary = (
            None
            if result.gcode_preview is None
            else result.gcode_preview.summary()
        )
        started = self._result_load_metrics.pop("started_perf_counter", time.perf_counter())
        self._result_load_metrics.update(
            request_id=result.request_id,
            status="complete",
            worker_elapsed_seconds=round(float(result.elapsed_seconds), 6),
            end_to_end_seconds=round(time.perf_counter() - float(started), 6),
            cache_format=None if preview_summary is None else preview_summary.get("cache_format"),
            cache_hit=False
            if preview_summary is None
            else preview_summary.get("render_index_source") == "cache",
        )
        self._update_file_labels()
        self._update_checks()
        self._update_context_actions()
        self.statusBar().showMessage(tr(self.language, "result_state_ready_detail"))

    def _on_result_load_failed(self, request_id: object, message: str) -> None:
        if self.result_page.fail_load(request_id, message):
            self.statusBar().showMessage(tr(self.language, "error_load_failed", message=message))
        self._update_context_actions()
        self._finish_result_load_metric(request_id, "error", message)

    def _on_result_load_cancelled(self, request_id: object) -> None:
        if self.result_page.cancel_load(request_id):
            self.statusBar().showMessage(tr(self.language, "error_load_cancelled"))
        self._update_context_actions()
        self._finish_result_load_metric(request_id, "cancelled", "")

    def _on_result_busy_changed(self, _busy: bool) -> None:
        self._update_context_actions()

    def _finish_result_load_metric(self, request_id: object, status: str, message: str) -> None:
        started = self._result_load_metrics.pop("started_perf_counter", time.perf_counter())
        self._result_load_metrics.update(
            request_id=request_id,
            status=status,
            end_to_end_seconds=round(time.perf_counter() - float(started), 6),
            message=message,
        )

    def _public_load_metrics(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self._result_load_metrics.items()
            if key != "started_perf_counter"
        }

    def queue_result_export(
        self,
        *,
        mode: str = "current",
        output_directory: str | Path | None = None,
        strict: bool = True,
        analysis_section: str = "top",
    ) -> dict[str, Any]:
        if self._result_export_state["status"] in {"queued", "running"}:
            raise RuntimeError(tr(self.language, "error_export_already_running"))
        if self.result_loader.busy or self.result_page.state.status == "loading":
            raise RuntimeError(tr(self.language, "error_export_while_loading"))
        normalized = mode.strip().lower()
        if normalized == "current":
            languages = [self.language]
        elif normalized in {"both", "all"}:
            languages = ["zh", "en"]
        elif normalized in {"zh", "en"}:
            languages = [normalized]
        else:
            raise ValueError(f"Unsupported export language mode: {mode}")
        if self.result_page.model is None and self.result_page.preview is None:
            raise RuntimeError(tr(self.language, "no_project_content"))
        target = Path(output_directory or self.result_page.output_directory).expanduser().resolve()
        self.result_page.set_output_directory(target)
        self._result_export_sequence += 1
        job_id = self._result_export_sequence
        self._result_export_state = {
            "status": "queued",
            "job_id": job_id,
            "languages": list(languages),
            "analysis_section": analysis_section,
            "output_directory": str(target),
            "outputs": [],
            "error": "",
        }
        self.result_page.set_export_interaction_locked(True)
        QTimer.singleShot(
            0,
            lambda: self._perform_result_export(
                job_id,
                languages,
                target,
                strict=strict,
                analysis_section=analysis_section,
            ),
        )
        return {"accepted": True, "job_id": job_id, "export": dict(self._result_export_state)}

    def _result_export_active(self) -> bool:
        return self._result_export_state.get("status") in {"queued", "running"}

    def _block_ui_during_result_export(self) -> bool:
        if not self._result_export_active():
            return False
        self.statusBar().showMessage(tr(self.language, "error_export_already_running"))
        if hasattr(self, "result_page"):
            self._sync_result_actions()
        return True

    def _require_result_export_idle(self) -> None:
        if self._result_export_active():
            raise RuntimeError(tr(self.language, "error_export_already_running"))

    def _perform_result_export(
        self,
        job_id: int,
        languages: list[str],
        output_directory: Path,
        *,
        strict: bool,
        analysis_section: str,
    ) -> None:
        if self._result_export_state.get("job_id") != job_id:
            return
        export_started = time.perf_counter()
        self._result_export_state["status"] = "running"
        original_language = self.language
        state = self.result_page.state
        original_quality = state.quality_mode
        original_visibility = {
            "show_model": state.show_model,
            "show_extrusion": state.show_extrusion,
            "show_travel": state.show_travel,
            "show_pose_samples": state.show_pose_samples,
            "show_start_end": state.show_start_end,
            "show_axes": state.show_axes,
            "show_orientation_cube": state.show_orientation_cube,
        }
        outputs: list[dict[str, Any]] = []
        interaction_locked = True
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
            self._show_results(force=True)
            self.result_page.focus_analysis_section(analysis_section)
            quality_started = time.perf_counter()
            self.result_page.set_quality_mode("paper")
            self._result_export_state["paper_quality_prepare_seconds"] = round(
                time.perf_counter() - quality_started,
                6,
            )
            self.result_page.set_visibility(
                show_model=True,
                show_extrusion=True,
                show_travel=False,
                show_pose_samples=False,
                show_start_end=True,
                show_axes=True,
                show_orientation_cube=True,
            )
            if hasattr(self.result_page.viewer, "set_standard_view"):
                self.result_page.viewer.set_standard_view("isometric")
            representative_line = self.result_page.show_representative_instruction()
            self.result_page.set_export_interaction_locked(True)

            sources: dict[str, Path] = {}
            if state.active_model_path is not None:
                sources["step_model"] = state.active_model_path
            if state.active_gcode_path is not None:
                sources["gcode"] = state.active_gcode_path
            if REFERENCE_IMAGE.exists():
                sources["visual_reference"] = REFERENCE_IMAGE
            source_audits = self.result_page.source_audits
            if REFERENCE_IMAGE.exists():
                source_audits["visual_reference"] = audit_source_file(
                    "visual_reference",
                    REFERENCE_IMAGE,
                ).to_json()
            statistics = self.result_page.statistics_json()
            display_items = {
                "model": True,
                "positive_extrusion": True,
                "travel": False,
                "pose_samples": False,
                "start_end_points": True,
                "part_xyz_axes": True,
                "orientation_cube": True,
            }
            render_parameters = {
                "coordinate_formula": "P_part = Rz(-C) × Rx(-A) × P_machine",
                "polyline_continuity_tolerance_mm": 0.02,
                "quality_mode": "paper",
                "representative_gcode_line": representative_line,
                "source_data_policy": "imported_gcode",
                "analysis_section": analysis_section,
                "visual_depth_offset_changes_coordinates": False,
            }

            for language in languages:
                language_started = time.perf_counter()
                self.language = language
                self.retranslate()
                QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
                output_path = output_directory / f"impeller_result_preview_{language}_3840x2160.png"
                # The status bar belongs to the exported application frame.
                # Keep it on a stable ready state instead of embedding a
                # transient "exporting" notification in the paper figure.
                self.statusBar().showMessage(tr(self.language, "status_ready"))
                result = export_paper_preview(
                    self,
                    self.result_page.viewer,
                    output_path,
                    language=language,
                    sources=sources,
                    source_audits=source_audits,
                    statistics=statistics,
                    display_items=display_items,
                    viewport_widget=self.result_page.viewer,
                    overlay_widgets=(
                        self.result_page.viewer_canvas.tool_rail,
                        self.result_page.viewer_canvas.orientation_cube,
                        self.result_page.viewer_canvas.axis_triad,
                        self.result_page.viewer_canvas.legend,
                    ),
                    render_parameters=render_parameters,
                    allow_scene_fallback=not strict,
                    strict=strict,
                )
                output_payload = result.to_json()
                output_payload["elapsed_seconds"] = round(
                    time.perf_counter() - language_started,
                    6,
                )
                outputs.append(output_payload)
            self._result_export_state.update(
                status="complete",
                outputs=outputs,
                error="",
                total_elapsed_seconds=round(time.perf_counter() - export_started, 6),
            )
            self.statusBar().showMessage(
                tr(self.language, "paper_export_complete", path=output_directory)
            )
        except Exception as exc:
            self._result_export_state.update(
                status="error",
                outputs=outputs,
                error=str(exc),
                total_elapsed_seconds=round(time.perf_counter() - export_started, 6),
            )
            self.statusBar().showMessage(
                tr(self.language, "paper_export_failed", message=str(exc))
            )
        finally:
            try:
                self.language = original_language
                self.retranslate()
                self.result_page.set_visibility(**original_visibility)
                self.result_page.set_quality_mode(original_quality)
            finally:
                if interaction_locked:
                    self.result_page.set_export_interaction_locked(False)
                self._sync_result_actions()

    def open_model(self, path: str | Path, show_dialog: bool = True) -> dict[str, Any]:
        self._require_result_export_idle()
        try:
            model = load_step(path)
            self.model = model
            self.viewer.load_model(model)
            self.refresh_lists()
            self._show_session()
            self._update_file_labels()
            self._update_checks()
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

    def open_gcode(self, path: str | Path, show_dialog: bool = True) -> dict[str, Any]:
        self._require_result_export_idle()
        try:
            preview = load_gcode(path)
            self.gcode_preview = preview
            self.viewer.load_gcode_preview(preview)
            self._show_session()
            self.preview_tabs.setCurrentWidget(self.preview_tab)
            self._sync_preview_controls()
            self._update_file_labels()
            self._update_checks()
            QTimer.singleShot(1400, self._update_preview_summary)
            self.statusBar().showMessage(
                tr(
                    self.language,
                    "status_gcode_loaded",
                    segment_count=preview.summary()["segment_count"],
                    layer_count=preview.layer_count,
                )
            )
            return self.current_state()
        except Exception as exc:
            if show_dialog:
                self.show_error(str(exc))
            else:
                self.statusBar().showMessage(tr(self.language, "status_error", message=str(exc)))
            raise

    def load_demo(self) -> None:
        self._require_result_export_idle()
        if DEMO_STEP.exists():
            self.open_model(DEMO_STEP)
        if DEMO_GCODE.exists():
            self.open_gcode(DEMO_GCODE)
        self.preview_tabs.setCurrentWidget(self.preview_tab)

    def save_project_dialog(self) -> None:
        if self._block_ui_during_result_export():
            return
        directory = QFileDialog.getExistingDirectory(self, tr(self.language, "save"), "")
        if directory:
            self.save_project_to(directory)

    def save_project_to(self, directory: str | Path) -> dict[str, Any]:
        self._require_result_export_idle()
        if self.model is None and self.gcode_preview is None:
            raise RuntimeError(tr(self.language, "no_project_content"))
        path = save_project(
            directory,
            self.model,
            self.viewer.selection,
            self._workbench_state(),
            self.gcode_preview,
            self.viewer.preview_settings,
            result_preview_state=self.result_page.state,
        )
        self.last_project_dir = Path(directory)
        self.statusBar().showMessage(tr(self.language, "status_saved", path=path))
        return {"project_json": str(path)}

    def refresh_lists(self) -> None:
        if self.model is None:
            self.body_list.set_rows([], set())
            self.edge_list.set_rows([], set())
            return
        self.body_list.set_rows(self._body_rows(), self.viewer.selection.body_ids)
        self.edge_list.set_rows(self._edge_rows(), self.viewer.selection.edge_ids)

    def handle_automation(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path == "/health":
            return {"status": "ready", "app": "5AxisSclicer V2.0"}
        if path == "/state":
            return self.current_state()
        if path == "/workbench/select":
            self.enter_workbench(str(payload["key"]))
            return self.current_state()
        if path == "/demo/load":
            self.load_demo()
            return self.current_state()
        if path == "/model/open":
            return self.open_model(payload["path"], show_dialog=False)
        if path == "/gcode/open":
            return self.open_gcode(payload["path"], show_dialog=False)
        if path == "/results/demo":
            return self.load_results_demo()
        if path == "/results/open":
            model_path = payload.get("model_path")
            gcode_path = payload.get("gcode_path")
            generic_path = payload.get("path")
            if generic_path and model_path is None and gcode_path is None:
                suffix = Path(str(generic_path)).suffix.lower()
                if suffix in {".step", ".stp"}:
                    model_path = generic_path
                elif suffix in {".gcode", ".nc", ".tap", ".txt"}:
                    gcode_path = generic_path
                else:
                    raise RuntimeError(tr(self.language, "error_unsupported_file", suffix=suffix))
            return self.start_result_load(model_path=model_path, gcode_path=gcode_path)
        if path == "/results/state":
            return {
                "results": self.result_page.state_json(),
                "load_metrics": self._public_load_metrics(),
                "export": dict(self._result_export_state),
            }
        if path == "/results/perf":
            return {"results_perf": self.benchmark_result_render()}
        if path == "/results/quality":
            if self._result_export_active():
                raise RuntimeError(tr(self.language, "error_export_already_running"))
            mode = str(payload.get("mode", "interactive"))
            self.result_page.set_quality_mode(mode)
            self._sync_result_actions()
            return {"results": self.result_page.state_json()}
        if path == "/results/focus":
            if self._result_export_active():
                raise RuntimeError(tr(self.language, "error_export_already_running"))
            self.result_page.focus_analysis_section(str(payload.get("section", "top")))
            return {"results": self.result_page.state_json()}
        if path == "/results/export":
            return self.queue_result_export(
                mode=str(payload.get("language", payload.get("mode", "current"))),
                output_directory=payload.get("output_directory"),
                strict=bool(payload.get("strict", True)),
                analysis_section=str(payload.get("analysis_section", "top")),
            )
        if path == "/results/cancel":
            self.cancel_result_load()
            return {"results": self.result_page.state_json()}
        if path == "/preview/state":
            return {"preview": self.viewer.preview_state()}
        if path == "/preview/perf":
            return {"preview_perf": self.viewer.performance_state()}
        if path == "/preview/layers":
            self.viewer.set_preview_layers(int(payload["layer_min"]), int(payload["layer_max"]))
            self._sync_preview_controls()
            return {"preview": self.viewer.preview_state()}
        if path == "/preview/progress":
            index = int(payload.get("progress_index", payload.get("index", 0)))
            self.viewer.set_preview_progress(index, interactive=bool(payload.get("interactive", False)))
            self._sync_progress_controls()
            self._update_preview_summary()
            if not bool(payload.get("interactive", False)):
                QTimer.singleShot(250, self._update_preview_summary)
            return {"preview": self.viewer.preview_state()}
        if path == "/preview/visibility":
            self.viewer.set_preview_visibility(
                show_travel=payload.get("show_travel"),
                show_extrusion=payload.get("show_extrusion"),
                visible_roles=payload.get("visible_roles"),
                show_pose_samples=payload.get("show_pose_samples"),
            )
            self._sync_legend_from_settings()
            self._update_preview_summary()
            return {"preview": self.viewer.preview_state()}
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

    def benchmark_result_render(
        self,
        *,
        frames: int = 6,
        width: int = 1280,
        height: int = 720,
    ) -> dict[str, Any]:
        viewer = self.result_page.viewer
        if not hasattr(viewer, "render_scene_image"):
            raise RuntimeError(tr(self.language, "error_render_unavailable"))
        frame_count = max(1, min(int(frames), 30))
        samples: list[float] = []
        for _ in range(frame_count):
            started = time.perf_counter()
            image = viewer.render_scene_image(int(width), int(height))
            if image.isNull():
                raise RuntimeError(tr(self.language, "error_render_unavailable"))
            samples.append((time.perf_counter() - started) * 1000.0)
        average = sum(samples) / len(samples)
        return {
            "backend": self.result_page.state_json()["viewer"]["capabilities"].get("backend"),
            "quality_mode": self.result_page.state.quality_mode,
            "frame_count": frame_count,
            "frame_size_px": [int(width), int(height)],
            "frame_ms_average": round(average, 6),
            "frame_ms_maximum": round(max(samples), 6),
            "fps_equivalent": round(1000.0 / average, 3) if average > 0.0 else 0.0,
        }

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
            "page": self._current_page_name(),
            "workbench": self._workbench_state(),
            "model": model_state,
            "selection": self.viewer.selection.to_json(),
            "preview": self.viewer.preview_state(),
            "results": self.result_page.state_json(),
            "result_load_metrics": self._public_load_metrics(),
            "result_export": dict(self._result_export_state),
        }

    def enter_workbench(self, key: str) -> None:
        self._require_result_export_idle()
        if key not in {workbench.key for workbench in WORKBENCHES}:
            raise RuntimeError(f"Unknown workbench: {key}")
        self.current_workbench_key = key
        self.current_operation = "imported_nc_review"
        self.operation_combo.setCurrentIndex(0)
        self._show_session()
        self._update_workbench_texts()
        self._update_checks()

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
        self.set_language("en" if self.language == "zh" else "zh")

    def set_language(self, language: str) -> None:
        if language not in {"zh", "en"}:
            raise ValueError(f"Unsupported UI language: {language}")
        if self._block_ui_during_result_export():
            return
        self.language = language
        self.settings.setValue("language", language)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(tr(self.language, "app_title"))
        self.home_action.setText(tr(self.language, "workbench_home"))
        self.open_action.setText(tr(self.language, "open_step"))
        self.open_gcode_action.setText(tr(self.language, "open_gcode"))
        self.save_action.setText(tr(self.language, "save"))
        self.clear_action.setText(tr(self.language, "clear"))
        self.fit_action.setText(tr(self.language, "fit"))
        self.home_view_action.setText(tr(self.language, "home_view"))
        self.language_action.setText(tr(self.language, "language"))
        self._retranslate_menus()
        self.home_title.setText(tr(self.language, "home_title"))
        self.home_subtitle.setText(tr(self.language, "home_subtitle"))
        self.gcode_viewer_button.setText(tr(self.language, "gcode_viewer_entry"))
        self.back_button.setText(tr(self.language, "workbench_home"))
        self.open_button.setText(tr(self.language, "open_step"))
        self.open_gcode_button.setText(tr(self.language, "open_gcode"))
        self.save_button.setText(tr(self.language, "save"))
        self.clear_button.setText(tr(self.language, "clear"))
        self.language_button.setText(tr(self.language, "language"))
        self.operation_label.setText(tr(self.language, "operation"))
        self.model_file_title.setText(tr(self.language, "model_file"))
        self.gcode_file_title.setText(tr(self.language, "gcode_file"))
        self.preview_tabs.setTabText(0, tr(self.language, "tab_objects"))
        self.preview_tabs.setTabText(1, tr(self.language, "tab_print"))
        self.preview_tabs.setTabText(2, tr(self.language, "tab_material"))
        self.preview_tabs.setTabText(3, tr(self.language, "tab_machine"))
        self.preview_tabs.setTabText(4, tr(self.language, "tab_preview"))
        self.preview_tabs.setTabText(5, tr(self.language, "tab_checks"))
        self.body_label.setText(tr(self.language, "body_list"))
        self.edge_label.setText(tr(self.language, "edge_list"))
        self.layer_range_title.setText(tr(self.language, "layer_range"))
        self.travel_checkbox.setText(tr(self.language, "show_travel"))
        self.extrusion_checkbox.setText(tr(self.language, "show_extrusion"))
        self.pose_checkbox.setText(tr(self.language, "show_pose"))
        self.legend_title.setText(tr(self.language, "feature_legend"))
        self.preview_summary_title.setText(tr(self.language, "preview_summary"))
        self.segment_property_title.setText(tr(self.language, "segment_property"))
        self.preview_progress_title.setText(tr(self.language, "path_progress"))
        self.path_progress_title.setText(tr(self.language, "path_progress"))
        self.progress_prev_button.setToolTip(tr(self.language, "progress_prev"))
        self.progress_play_button.setToolTip(
            tr(self.language, "progress_pause") if self.progress_timer.isActive() else tr(self.language, "progress_play")
        )
        self.progress_next_button.setToolTip(tr(self.language, "progress_next"))
        self.checks_title.setText(tr(self.language, "checks_title"))
        self.result_page.retranslate(self.language)
        for group, key in self.localized_groups:
            group.setTitle(tr(self.language, key))
        for label, key in self.localized_labels:
            label.setText(tr(self.language, key))
        self._update_workbench_texts()
        self._update_operation_combo()
        self._sync_legend_labels()
        self._update_file_labels()
        self._sync_progress_controls()
        self._update_preview_summary()
        self._update_checks()
        self._sync_result_actions()

    def _retranslate_menus(self) -> None:
        self.file_menu.setTitle(tr(self.language, "menu_file"))
        self.model_menu.setTitle(tr(self.language, "menu_model"))
        self.slice_menu.setTitle(tr(self.language, "menu_slice"))
        self.preview_menu.setTitle(tr(self.language, "menu_preview"))
        self.gcode_menu.setTitle(tr(self.language, "menu_gcode"))
        self.tools_menu.setTitle(tr(self.language, "menu_tools"))
        self.help_menu.setTitle(tr(self.language, "menu_help"))
        self.standard_view_menu.setTitle(tr(self.language, "view_tools"))
        self.visibility_menu.setTitle(tr(self.language, "visibility_title"))
        self.quality_menu.setTitle(tr(self.language, "quality_mode"))
        self.language_menu.setTitle(tr(self.language, "language"))

        action_keys = {
            self.open_action: "action_open_step",
            self.open_gcode_action: "action_open_gcode",
            self.save_action: "action_save_project",
            self.open_results_action: "action_open_result_preview",
            self.load_results_demo_action: "action_load_impeller_demo",
            self.slice_results_action: "action_slice_and_preview",
            self.cancel_results_action: "action_cancel_loading",
            self.exit_action: "action_exit",
            self.fit_action: "action_fit_view",
            self.home_view_action: "action_home_view",
            self.search_gcode_action: "action_search_gcode",
            self.jump_gcode_action: "action_jump_to_line",
            self.help_action: "action_user_guide",
            self.about_action: "action_about",
        }
        for action, key in action_keys.items():
            action.setText(tr(self.language, key))

        standard_view_keys = {
            "isometric": "action_view_isometric",
            "front": "action_view_front",
            "back": "action_view_back",
            "left": "action_view_left",
            "right": "action_view_right",
            "top": "action_view_top",
            "bottom": "action_view_bottom",
        }
        for name, action in self.standard_view_actions.items():
            action.setText(tr(self.language, standard_view_keys[name]))

        visibility_keys = {
            "show_model": "action_toggle_model",
            "show_extrusion": "action_toggle_extrusion",
            "show_start_end": "action_toggle_start_end",
            "show_axes": "action_toggle_part_axes",
            "show_orientation_cube": "action_toggle_orientation_cube",
            "show_travel": "action_toggle_travel",
            "show_pose_samples": "action_toggle_pose",
        }
        for name, action in self.result_visibility_actions.items():
            action.setText(tr(self.language, visibility_keys[name]))
        self.quality_actions["interactive"].setText(tr(self.language, "action_quality_interactive"))
        self.quality_actions["paper"].setText(tr(self.language, "action_quality_paper"))
        self.language_actions["zh"].setText(tr(self.language, "action_language_chinese"))
        self.language_actions["en"].setText(tr(self.language, "action_language_english"))

        self.load_results_demo_action.setToolTip(tr(self.language, "tooltip_load_demo"))
        self.open_action.setToolTip(tr(self.language, "tooltip_open_step"))
        self.open_gcode_action.setToolTip(tr(self.language, "tooltip_open_gcode"))
        self.slice_results_action.setToolTip(tr(self.language, "tooltip_slice_preview"))
        self.cancel_results_action.setToolTip(tr(self.language, "tooltip_cancel_loading"))
        self.fit_action.setToolTip(tr(self.language, "tooltip_fit_view"))
        self.home_view_action.setToolTip(tr(self.language, "tooltip_home_view"))
        self.search_gcode_action.setToolTip(tr(self.language, "tooltip_gcode_search"))
        self.jump_gcode_action.setToolTip(tr(self.language, "tooltip_gcode_jump"))
        self.language_action.setToolTip(tr(self.language, "tooltip_language"))
        self.help_action.setToolTip(tr(self.language, "tooltip_help"))

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(tr(self.language, "status_error", message=message))
        QMessageBox.warning(self, tr(self.language, "app_title"), message)

    def _build_ui(self) -> None:
        self._build_actions()

        self.stack = QStackedWidget()
        self.home_page = self._build_home_page()
        self.session_page = self._build_session_page()
        self.result_page = ResultPreviewPage(viewer_factory=self._result_viewer_factory, parent=self)
        if REFERENCE_IMAGE.exists():
            self.result_page.set_reference_image(REFERENCE_IMAGE)
        self.result_page.back_requested.connect(self._show_home)
        self.result_page.load_demo_requested.connect(self._load_results_demo_from_ui)
        self.result_page.open_gcode_requested.connect(self.open_result_gcode_dialog)
        self.result_page.open_step_requested.connect(self.open_result_model_dialog)
        self.result_page.slice_preview_requested.connect(self._slice_results_from_ui)
        self.result_page.cancel_loading_requested.connect(self.cancel_result_load)
        self.result_page.quality_changed.connect(lambda _mode: self._sync_result_actions())
        self.result_page.display_state_changed.connect(lambda _state: self._sync_result_actions())
        self.result_page.export_requested.connect(lambda mode: self.queue_result_export(mode=mode, strict=True))
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.session_page)
        self.stack.addWidget(self.result_page)
        self.stack.currentChanged.connect(lambda _index: self._update_context_actions())
        self.setCentralWidget(self.stack)
        self.setStatusBar(QStatusBar(self))
        self.setMinimumSize(1600, 900)
        self.resize(1600, 900)

    def _build_actions(self) -> None:
        self.home_action = QAction(self)
        self.open_action = QAction(self)
        self.open_gcode_action = QAction(self)
        self.save_action = QAction(self)
        self.clear_action = QAction(self)
        self.fit_action = QAction(self)
        self.home_view_action = QAction(self)
        self.language_action = QAction(self)
        self.open_results_action = QAction(self)
        self.load_results_demo_action = QAction(self)
        self.slice_results_action = QAction(self)
        self.cancel_results_action = QAction(self)
        self.exit_action = QAction(self)
        self.search_gcode_action = QAction(self)
        self.jump_gcode_action = QAction(self)
        self.help_action = QAction(self)
        self.about_action = QAction(self)
        self.home_action.triggered.connect(self._show_home)
        self.open_action.triggered.connect(self._open_model_from_shell)
        self.open_gcode_action.triggered.connect(self._open_gcode_from_shell)
        self.save_action.triggered.connect(self.save_project_dialog)
        self.clear_action.triggered.connect(self.clear_selection)
        self.fit_action.triggered.connect(self._fit_active_view)
        self.home_view_action.triggered.connect(self._home_active_view)
        self.language_action.triggered.connect(self.toggle_language)
        self.open_results_action.triggered.connect(self._show_results)
        self.load_results_demo_action.triggered.connect(self._load_results_demo_from_ui)
        self.slice_results_action.triggered.connect(self._slice_results_from_ui)
        self.cancel_results_action.triggered.connect(self.cancel_result_load)
        self.exit_action.triggered.connect(self.close)
        self.search_gcode_action.triggered.connect(self._focus_result_gcode_search)
        self.jump_gcode_action.triggered.connect(self._focus_result_gcode_jump)
        self.help_action.triggered.connect(self._show_result_help)
        self.about_action.triggered.connect(self._show_about)

        self.standard_view_actions: dict[str, QAction] = {}
        for view in ("isometric", "front", "back", "left", "right", "top", "bottom"):
            action = QAction(self)
            action.triggered.connect(lambda _checked=False, name=view: self._set_active_standard_view(name))
            self.standard_view_actions[view] = action

        self.result_visibility_actions: dict[str, QAction] = {}
        for name in (
            "show_model",
            "show_extrusion",
            "show_start_end",
            "show_axes",
            "show_orientation_cube",
            "show_travel",
            "show_pose_samples",
        ):
            action = QAction(self)
            action.setCheckable(True)
            action.toggled.connect(
                lambda checked, attribute=name: self._set_result_visibility(attribute, checked)
            )
            self.result_visibility_actions[name] = action

        self.quality_action_group = QActionGroup(self)
        self.quality_action_group.setExclusive(True)
        self.quality_actions: dict[str, QAction] = {}
        for mode in ("interactive", "paper"):
            action = QAction(self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, value=mode: self._set_result_quality_mode(value)
            )
            self.quality_action_group.addAction(action)
            self.quality_actions[mode] = action

        self.language_action_group = QActionGroup(self)
        self.language_action_group.setExclusive(True)
        self.language_actions: dict[str, QAction] = {}
        for language in ("zh", "en"):
            action = QAction(self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, value=language: self.set_language(value)
            )
            self.language_action_group.addAction(action)
            self.language_actions[language] = action

        menu_bar = self.menuBar()
        self.file_menu = menu_bar.addMenu("")
        self.model_menu = menu_bar.addMenu("")
        self.slice_menu = menu_bar.addMenu("")
        self.preview_menu = menu_bar.addMenu("")
        self.gcode_menu = menu_bar.addMenu("")
        self.tools_menu = menu_bar.addMenu("")
        self.help_menu = menu_bar.addMenu("")

        self.file_menu.addAction(self.load_results_demo_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.open_action)
        self.file_menu.addAction(self.open_gcode_action)
        self.file_menu.addAction(self.save_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.exit_action)
        self.model_menu.addAction(self.open_action)
        self.model_menu.addAction(self.clear_action)
        self.model_menu.addAction(self.result_visibility_actions["show_model"])
        self.slice_menu.addAction(self.open_results_action)
        self.slice_menu.addAction(self.slice_results_action)
        self.slice_menu.addAction(self.cancel_results_action)
        self.preview_menu.addAction(self.fit_action)
        self.preview_menu.addAction(self.home_view_action)
        self.standard_view_menu = self.preview_menu.addMenu("")
        for action in self.standard_view_actions.values():
            self.standard_view_menu.addAction(action)
        self.visibility_menu = self.preview_menu.addMenu("")
        for action in self.result_visibility_actions.values():
            self.visibility_menu.addAction(action)
        self.quality_menu = self.preview_menu.addMenu("")
        for action in self.quality_actions.values():
            self.quality_menu.addAction(action)
        self.gcode_menu.addAction(self.open_gcode_action)
        self.gcode_menu.addAction(self.search_gcode_action)
        self.gcode_menu.addAction(self.jump_gcode_action)
        self.language_menu = self.tools_menu.addMenu("")
        for action in self.language_actions.values():
            self.language_menu.addAction(action)
        self.help_menu.addAction(self.help_action)
        self.help_menu.addAction(self.about_action)

        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        self.product_title_label = QLabel("5AxisSclicer V2.0")
        self.product_title_label.setObjectName("productTitle")
        toolbar.addWidget(self.product_title_label)
        toolbar.addSeparator()
        for action in (
            self.home_action,
            self.open_results_action,
            self.open_action,
            self.open_gcode_action,
        ):
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(self.language_action)
        self.addToolBar(toolbar)

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 28)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        self.home_title = QLabel()
        self.home_title.setObjectName("pageTitle")
        self.home_subtitle = QLabel()
        self.home_subtitle.setObjectName("mutedText")
        self.home_subtitle.setWordWrap(True)
        title_box.addWidget(self.home_title)
        title_box.addWidget(self.home_subtitle)
        self.gcode_viewer_button = QPushButton()
        self.gcode_viewer_button.setObjectName("primaryButton")
        self.gcode_viewer_button.clicked.connect(self._show_results)
        header.addLayout(title_box, 1)
        header.addWidget(self.gcode_viewer_button)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        self.workbench_buttons: dict[str, QPushButton] = {}
        for index, workbench in enumerate(WORKBENCHES):
            button = QPushButton()
            button.setObjectName("workbenchCard")
            button.setMinimumHeight(128)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            button.clicked.connect(lambda _checked=False, key=workbench.key: self.enter_workbench(key))
            self.workbench_buttons[workbench.key] = button
            grid.addWidget(button, index // 3, index % 3)
        layout.addLayout(grid, 1)
        return page

    def _build_session_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        layout.addWidget(self._build_left_panel())
        layout.addWidget(self._build_right_panel())
        layout.addWidget(self._build_viewer_panel(), 1)
        return page

    def _build_viewer_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.viewer, 1)

        progress_frame = QFrame()
        progress_frame.setObjectName("progressPanel")
        progress_layout = QHBoxLayout(progress_frame)
        progress_layout.setContentsMargins(10, 8, 10, 8)
        self.path_progress_title = QLabel()
        self.path_progress_title.setObjectName("mutedText")
        self.progress_prev_button = QPushButton("|<")
        self.progress_play_button = QPushButton(">")
        self.progress_next_button = QPushButton(">|")
        for button in (self.progress_prev_button, self.progress_play_button, self.progress_next_button):
            button.setFixedWidth(42)
        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setMinimum(0)
        self.progress_slider.setMaximum(0)
        self.progress_slider.setEnabled(False)
        self.progress_step_label = QLabel()
        self.progress_step_label.setObjectName("fileText")
        self.progress_step_label.setMinimumWidth(210)
        self.progress_prev_button.clicked.connect(lambda: self._nudge_progress(-1))
        self.progress_next_button.clicked.connect(lambda: self._nudge_progress(1))
        self.progress_play_button.clicked.connect(self._toggle_progress_playback)
        self.progress_slider.sliderPressed.connect(self._on_progress_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_progress_slider_released)
        self.progress_slider.valueChanged.connect(self._on_progress_slider_changed)
        progress_layout.addWidget(self.path_progress_title)
        progress_layout.addWidget(self.progress_prev_button)
        progress_layout.addWidget(self.progress_play_button)
        progress_layout.addWidget(self.progress_next_button)
        progress_layout.addWidget(self.progress_slider, 1)
        progress_layout.addWidget(self.progress_step_label)
        layout.addWidget(progress_frame)
        return panel

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("glassPanel")
        panel.setFixedWidth(360)
        layout = QVBoxLayout(panel)
        self.workbench_title = QLabel()
        self.workbench_title.setObjectName("panelTitle")
        self.workbench_summary = QLabel()
        self.workbench_summary.setObjectName("mutedText")
        self.workbench_summary.setWordWrap(True)
        self.operation_label = QLabel()
        self.operation_combo = QComboBox()
        self.operation_combo.currentIndexChanged.connect(self._on_operation_changed)
        self.back_button = QPushButton()
        self.open_button = QPushButton()
        self.open_gcode_button = QPushButton()
        self.save_button = QPushButton()
        self.clear_button = QPushButton()
        self.language_button = QPushButton()
        self.back_button.clicked.connect(self._show_home)
        self.open_button.clicked.connect(self.open_model_dialog)
        self.open_gcode_button.clicked.connect(self.open_gcode_dialog)
        self.save_button.clicked.connect(self.save_project_dialog)
        self.clear_button.clicked.connect(self.clear_selection)
        self.language_button.clicked.connect(self.toggle_language)

        self.model_file_title = QLabel()
        self.gcode_file_title = QLabel()
        self.model_file_label = QLabel()
        self.gcode_file_label = QLabel()
        for label in (self.model_file_label, self.gcode_file_label):
            label.setObjectName("fileText")
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        layout.addWidget(self.workbench_title)
        layout.addWidget(self.workbench_summary)
        layout.addSpacing(8)
        layout.addWidget(self.operation_label)
        layout.addWidget(self.operation_combo)
        layout.addSpacing(10)
        for button in (
            self.back_button,
            self.open_button,
            self.open_gcode_button,
            self.save_button,
            self.clear_button,
        ):
            layout.addWidget(button)
        layout.addSpacing(10)
        layout.addWidget(self.model_file_title)
        layout.addWidget(self.model_file_label)
        layout.addWidget(self.gcode_file_title)
        layout.addWidget(self.gcode_file_label)
        layout.addStretch(1)
        layout.addWidget(self.language_button)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("glassPanel")
        panel.setFixedWidth(390)
        layout = QVBoxLayout(panel)
        self.preview_tabs = QTabWidget()
        self.objects_tab = self._build_objects_tab()
        self.print_tab = self._build_print_tab()
        self.material_tab = self._build_material_tab()
        self.machine_tab = self._build_machine_tab()
        self.preview_tab = self._build_preview_tab()
        self.checks_tab = self._build_checks_tab()
        for tab in (
            self.objects_tab,
            self.print_tab,
            self.material_tab,
            self.machine_tab,
            self.preview_tab,
            self.checks_tab,
        ):
            self.preview_tabs.addTab(tab, "")
        layout.addWidget(self.preview_tabs)
        return panel

    def _build_objects_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.body_label = QLabel()
        self.edge_label = QLabel()
        self.body_list = SelectionList()
        self.edge_list = SelectionList()
        self.body_list.itemSelectionChanged.connect(self._on_body_list_selection_changed)
        self.edge_list.itemSelectionChanged.connect(self._on_edge_list_selection_changed)
        layout.addWidget(self.body_label)
        layout.addWidget(self.body_list, 1)
        layout.addWidget(self.edge_label)
        layout.addWidget(self.edge_list, 2)
        return widget

    def _build_print_tab(self) -> QWidget:
        return self._scroll_with_groups(
            (
                self._param_group(
                    "param_layer_bead",
                    (
                        ("param_layer_height", "0.20 mm"),
                        ("param_bead_width", "0.45 mm"),
                        ("param_perimeters", "2"),
                    ),
                ),
                self._param_group(
                    "param_curve_freeform",
                    (
                        ("param_sampling_spacing", "0.50 mm"),
                        ("param_surface_offset", "0.20 mm"),
                        ("param_toolpath_source", "Imported NC Review"),
                    ),
                ),
            )
        )

    def _build_material_tab(self) -> QWidget:
        return self._scroll_with_groups(
            (
                self._param_group(
                    "param_material_profile",
                    (
                        ("param_material", "PLA / Resin profile"),
                        ("param_nozzle_temp", "195 C"),
                        ("param_platform_temp", "60 C"),
                    ),
                ),
                self._param_group(
                    "param_extrusion",
                    (
                        ("param_extrusion_mode", "Relative E"),
                        ("param_retraction", "5.0 mm"),
                        ("param_cooling", "Enabled"),
                    ),
                ),
            )
        )

    def _build_machine_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        machine_group = QGroupBox()
        self.localized_groups.append((machine_group, "param_machine_profile"))
        form = QGridLayout(machine_group)
        self.axis_map_combo = QComboBox()
        self.axis_map_combo.addItems(["XYZAC", "XYZAB", "XYZUV"])
        self.nozzle_spin = QDoubleSpinBox()
        self.nozzle_spin.setRange(0.1, 3.0)
        self.nozzle_spin.setSingleStep(0.05)
        self.nozzle_spin.setValue(0.4)
        self.travel_spin = QDoubleSpinBox()
        self.travel_spin.setRange(1.0, 500.0)
        self.travel_spin.setValue(150.0)
        for row, (label, widget_item) in enumerate(
            (
                ("param_axis_mapping", self.axis_map_combo),
                ("param_nozzle_diameter", self.nozzle_spin),
                ("param_max_travel_speed", self.travel_spin),
                ("param_rotary_limits", self._translated_label("param_rotary_metadata")),
            )
        ):
            form.addWidget(self._translated_label(label), row, 0)
            form.addWidget(widget_item, row, 1)
        layout.addWidget(machine_group)
        layout.addStretch(1)
        return widget

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.preview_summary_title = QLabel()
        self.preview_summary_title.setObjectName("panelTitle")
        self.preview_summary = QLabel()
        self.preview_summary.setObjectName("mutedText")
        self.preview_summary.setWordWrap(True)
        self.preview_progress_title = QLabel()
        self.preview_progress_title.setObjectName("panelTitle")
        self.preview_progress_slider = QSlider(Qt.Horizontal)
        self.preview_progress_slider.setMinimum(0)
        self.preview_progress_slider.setMaximum(0)
        self.preview_progress_slider.setEnabled(False)
        self.preview_progress_label = QLabel()
        self.preview_progress_label.setObjectName("fileText")
        self.preview_progress_slider.sliderPressed.connect(self._on_progress_slider_pressed)
        self.preview_progress_slider.sliderReleased.connect(self._on_progress_slider_released)
        self.preview_progress_slider.valueChanged.connect(self._on_progress_slider_changed)
        self.segment_property_title = QLabel()
        self.segment_property_title.setObjectName("panelTitle")
        self.segment_property = QLabel()
        self.segment_property.setObjectName("fileText")
        self.segment_property.setWordWrap(True)
        self.layer_range_title = QLabel()
        self.layer_min_slider = QSlider(Qt.Horizontal)
        self.layer_max_slider = QSlider(Qt.Horizontal)
        self.layer_min_spin = QSpinBox()
        self.layer_max_spin = QSpinBox()
        self.layer_min_slider.valueChanged.connect(self._on_layer_range_changed)
        self.layer_max_slider.valueChanged.connect(self._on_layer_range_changed)
        self.layer_min_spin.valueChanged.connect(self._on_layer_spin_changed)
        self.layer_max_spin.valueChanged.connect(self._on_layer_spin_changed)

        layer_row = QGridLayout()
        layer_row.addWidget(self._translated_label("layer_min_label"), 0, 0)
        layer_row.addWidget(self.layer_min_slider, 0, 1)
        layer_row.addWidget(self.layer_min_spin, 0, 2)
        layer_row.addWidget(self._translated_label("layer_max_label"), 1, 0)
        layer_row.addWidget(self.layer_max_slider, 1, 1)
        layer_row.addWidget(self.layer_max_spin, 1, 2)

        self.travel_checkbox = QCheckBox()
        self.extrusion_checkbox = QCheckBox()
        self.pose_checkbox = QCheckBox()
        for checkbox in (self.travel_checkbox, self.extrusion_checkbox, self.pose_checkbox):
            checkbox.setObjectName("toggleCheck")
        self.travel_checkbox.setChecked(True)
        self.extrusion_checkbox.setChecked(True)
        self.pose_checkbox.setChecked(True)
        self.travel_checkbox.toggled.connect(self._on_preview_visibility_changed)
        self.extrusion_checkbox.toggled.connect(self._on_preview_visibility_changed)
        self.pose_checkbox.toggled.connect(self._on_preview_visibility_changed)

        self.legend_title = QLabel()
        self.legend_title.setObjectName("panelTitle")
        self.legend_container = QWidget()
        self.legend_layout = QVBoxLayout(self.legend_container)
        self.legend_layout.setContentsMargins(0, 0, 0, 0)
        self.role_checkboxes: dict[str, QCheckBox] = {}
        for role, color in ROLE_COLORS.items():
            checkbox = QCheckBox()
            checkbox.setObjectName("roleCheck")
            checkbox.setChecked(True)
            checkbox.setStyleSheet(f"QCheckBox::indicator {{ background: {rgb_to_hex(color)}; }}")
            checkbox.toggled.connect(self._on_preview_visibility_changed)
            self.role_checkboxes[role] = checkbox
            self.legend_layout.addWidget(checkbox)
        self.legend_layout.addStretch(1)
        self.legend_scroll = QScrollArea()
        self.legend_scroll.setWidgetResizable(True)
        self.legend_scroll.setWidget(self.legend_container)
        self.legend_scroll.setMinimumHeight(150)
        self.legend_scroll.setMaximumHeight(230)

        layout.addWidget(self.preview_summary_title)
        layout.addWidget(self.preview_summary)
        layout.addWidget(self.preview_progress_title)
        layout.addWidget(self.preview_progress_slider)
        layout.addWidget(self.preview_progress_label)
        layout.addWidget(self.layer_range_title)
        layout.addLayout(layer_row)
        layout.addWidget(self.travel_checkbox)
        layout.addWidget(self.extrusion_checkbox)
        layout.addWidget(self.pose_checkbox)
        layout.addWidget(self.legend_title)
        layout.addWidget(self.legend_scroll)
        layout.addWidget(self.segment_property_title)
        layout.addWidget(self.segment_property)
        layout.addStretch(1)
        return widget

    def _build_checks_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.checks_title = QLabel()
        self.checks_title.setObjectName("panelTitle")
        self.checks_text = QTextEdit()
        self.checks_text.setReadOnly(True)
        layout.addWidget(self.checks_title)
        layout.addWidget(self.checks_text, 1)
        return widget

    def _scroll_with_groups(self, groups: tuple[QGroupBox, ...]) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        for group in groups:
            layout.addWidget(group)
        layout.addStretch(1)
        scroll.setWidget(inner)
        return scroll

    def _translated_label(self, key: str) -> QLabel:
        label = QLabel()
        self.localized_labels.append((label, key))
        return label

    def _param_group(self, title_key: str, rows: tuple[tuple[str, str], ...]) -> QGroupBox:
        group = QGroupBox()
        self.localized_groups.append((group, title_key))
        layout = QGridLayout(group)
        for row, (name_key, value) in enumerate(rows):
            layout.addWidget(self._translated_label(name_key), row, 0)
            label = QLabel(value)
            label.setObjectName("valueText")
            layout.addWidget(label, row, 1)
        return group

    def _bind_shortcuts(self) -> None:
        self.home_action.setShortcut("Ctrl+W")
        self.open_action.setShortcut("Ctrl+O")
        self.open_gcode_action.setShortcut("Ctrl+G")
        self.save_action.setShortcut("Ctrl+S")
        self.clear_action.setShortcut("Esc")
        self.fit_action.setShortcut("F")
        self.home_view_action.setShortcut("H")
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

    def _show_home(self) -> None:
        if self._block_ui_during_result_export():
            return
        self.stack.setCurrentWidget(self.home_page)

    def _show_session(self) -> None:
        if self._block_ui_during_result_export():
            return
        self.stack.setCurrentWidget(self.session_page)

    def _show_results(self, *, force: bool = False) -> None:
        if not force and self._block_ui_during_result_export():
            return
        self.stack.setCurrentWidget(self.result_page)
        self._update_context_actions()

    def show_results_page(self) -> None:
        """Public CLI/automation navigation entry for an empty result page."""

        self._show_results()

    def _current_page_name(self) -> str:
        current = self.stack.currentWidget()
        if current is self.result_page:
            return "results"
        if current is self.session_page:
            return "session"
        return "workbench"

    def _open_model_from_shell(self) -> None:
        if self._block_ui_during_result_export():
            return
        if self.stack.currentWidget() is self.session_page:
            self.open_model_dialog()
        else:
            self.open_result_model_dialog()

    def _open_gcode_from_shell(self) -> None:
        if self._block_ui_during_result_export():
            return
        if self.stack.currentWidget() is self.session_page:
            self.open_gcode_dialog()
        else:
            self.open_result_gcode_dialog()

    def _load_results_demo_from_ui(self) -> None:
        if self._block_ui_during_result_export():
            return
        try:
            self.load_results_demo()
        except Exception as exc:
            self.show_error(str(exc))

    def _slice_results_from_ui(self) -> None:
        if self._block_ui_during_result_export():
            return
        try:
            self.slice_results()
        except Exception as exc:
            self.show_error(str(exc))

    def _active_viewer(self):
        return self.result_page.viewer if self.stack.currentWidget() is self.result_page else self.viewer

    def _fit_active_view(self) -> None:
        if self._block_ui_during_result_export():
            return
        viewer = self._active_viewer()
        if hasattr(viewer, "fit_view"):
            viewer.fit_view()

    def _home_active_view(self) -> None:
        if self._block_ui_during_result_export():
            return
        viewer = self._active_viewer()
        if hasattr(viewer, "home_view"):
            viewer.home_view()
        elif hasattr(viewer, "set_standard_view"):
            viewer.set_standard_view("isometric")

    def _set_active_standard_view(self, view: str) -> None:
        if self._block_ui_during_result_export():
            return
        viewer = self._active_viewer()
        if hasattr(viewer, "set_standard_view"):
            viewer.set_standard_view(view)

    def _set_result_visibility(self, attribute: str, checked: bool) -> None:
        if not hasattr(self, "result_page") or self._block_ui_during_result_export():
            return
        self.result_page.set_visibility(**{attribute: checked})

    def _set_result_quality_mode(self, mode: str) -> None:
        if self._block_ui_during_result_export():
            return
        self.result_page.set_quality_mode(mode)

    def _focus_result_gcode_search(self) -> None:
        if not self._block_ui_during_result_export():
            self.result_page.focus_gcode_search()

    def _focus_result_gcode_jump(self) -> None:
        if not self._block_ui_during_result_export():
            self.result_page.focus_gcode_jump()

    def _update_context_actions(self) -> None:
        if not hasattr(self, "result_page"):
            return
        on_results = self.stack.currentWidget() is self.result_page
        has_source_index = self.result_page.source_index is not None
        self.cancel_results_action.setEnabled(self.result_loader.busy)
        self.slice_results_action.setEnabled(
            not self.result_loader.busy
            and self.result_page.state.selected_gcode_path is not None
        )
        self.search_gcode_action.setEnabled(on_results and has_source_index)
        self.jump_gcode_action.setEnabled(on_results and has_source_index)
        for action in self.result_visibility_actions.values():
            action.setEnabled(on_results)
        for action in self.quality_actions.values():
            action.setEnabled(on_results)
        for action in self.standard_view_actions.values():
            action.setEnabled(self.stack.currentWidget() is not self.home_page)
        self._sync_result_actions()

    def _sync_result_actions(self) -> None:
        if not hasattr(self, "result_page"):
            return
        state = self.result_page.state
        visibility_values = {
            "show_model": state.show_model,
            "show_extrusion": state.show_extrusion,
            "show_start_end": state.show_start_end,
            "show_axes": state.show_axes,
            "show_orientation_cube": state.show_orientation_cube,
            "show_travel": state.show_travel,
            "show_pose_samples": state.show_pose_samples,
        }
        for name, value in visibility_values.items():
            action = self.result_visibility_actions[name]
            action.blockSignals(True)
            action.setChecked(bool(value))
            action.blockSignals(False)
        for mode, action in self.quality_actions.items():
            action.blockSignals(True)
            action.setChecked(state.quality_mode == mode)
            action.blockSignals(False)
        for language, action in self.language_actions.items():
            action.blockSignals(True)
            action.setChecked(self.language == language)
            action.blockSignals(False)

    def _show_result_help(self) -> None:
        if self._block_ui_during_result_export():
            return
        message = (
            f"{tr(self.language, 'result_preview_subtitle')}\n\n"
            f"{tr(self.language, 'statistics_coordinate_formula')}"
        )
        QMessageBox.information(self, tr(self.language, "action_user_guide"), message)

    def _show_about(self) -> None:
        if self._block_ui_during_result_export():
            return
        QMessageBox.about(
            self,
            tr(self.language, "action_about"),
            "5AxisSclicer V2.0\nPyQt5 · OpenGL/VTK · AC inverse preview",
        )

    def _on_operation_changed(self, index: int) -> None:
        data = self.operation_combo.itemData(index)
        if data:
            self.current_operation = str(data)
        self._update_checks()

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

    def _on_layer_range_changed(self) -> None:
        if self._updating_layer_controls or self.gcode_preview is None:
            return
        self._updating_layer_controls = True
        low = min(self.layer_min_slider.value(), self.layer_max_slider.value())
        high = max(self.layer_min_slider.value(), self.layer_max_slider.value())
        self.layer_min_spin.setValue(low)
        self.layer_max_spin.setValue(high)
        self._updating_layer_controls = False
        self.viewer.set_preview_layers(low, high)
        self._sync_progress_controls()
        self._update_preview_summary()

    def _on_layer_spin_changed(self) -> None:
        if self._updating_layer_controls or self.gcode_preview is None:
            return
        self._updating_layer_controls = True
        low = min(self.layer_min_spin.value(), self.layer_max_spin.value())
        high = max(self.layer_min_spin.value(), self.layer_max_spin.value())
        self.layer_min_slider.setValue(low)
        self.layer_max_slider.setValue(high)
        self._updating_layer_controls = False
        self.viewer.set_preview_layers(low, high)
        self._sync_progress_controls()
        self._update_preview_summary()

    def _on_progress_slider_pressed(self) -> None:
        self.viewer.set_progress_interaction(True)

    def _on_progress_slider_released(self) -> None:
        if self.gcode_preview is None:
            return
        slider = self._progress_sender_slider()
        self.viewer.set_preview_progress(slider.value(), interactive=False)
        self._sync_progress_controls()
        self._update_preview_summary()
        QTimer.singleShot(250, self._update_preview_summary)

    def _on_progress_slider_changed(self, value: int) -> None:
        if self._updating_progress_controls or self.gcode_preview is None:
            return
        slider = self._progress_sender_slider()
        self.viewer.set_preview_progress(value, interactive=slider.isSliderDown())
        self._sync_progress_controls()
        self._update_preview_summary()

    def _nudge_progress(self, delta: int) -> None:
        if self.gcode_preview is None:
            return
        self.viewer.set_preview_progress(self.viewer.preview_settings.progress_index + delta)
        self._sync_progress_controls()
        self._update_preview_summary()

    def _toggle_progress_playback(self) -> None:
        if self.progress_timer.isActive():
            self.progress_timer.stop()
            self.viewer.set_progress_interaction(False)
            self.progress_play_button.setText(">")
        else:
            self.progress_timer.start()
            self.progress_play_button.setText("||")
        self.progress_play_button.setToolTip(
            tr(self.language, "progress_pause") if self.progress_timer.isActive() else tr(self.language, "progress_play")
        )

    def _advance_progress(self) -> None:
        if self.gcode_preview is None:
            self.progress_timer.stop()
            return
        state = self.viewer.progress_state()
        total = int(state.get("layer_step_count", 0))
        current = int(state.get("progress_index", 0))
        if total <= 0 or current >= total - 1:
            self.progress_timer.stop()
            self.viewer.set_progress_interaction(False)
            self.progress_play_button.setText(">")
            return
        self.viewer.set_preview_progress(current + 1, interactive=True)
        self._sync_progress_controls()
        self._update_preview_summary()

    def _on_preview_visibility_changed(self) -> None:
        if self.gcode_preview is None:
            return
        visible_roles = [role for role, checkbox in self.role_checkboxes.items() if checkbox.isChecked()]
        self.viewer.set_preview_visibility(
            show_travel=self.travel_checkbox.isChecked(),
            show_extrusion=self.extrusion_checkbox.isChecked(),
            visible_roles=visible_roles,
            show_pose_samples=self.pose_checkbox.isChecked(),
        )
        self._update_preview_summary()

    def _sync_preview_controls(self) -> None:
        preview = self.gcode_preview
        if preview is None:
            return
        self._updating_layer_controls = True
        for widget in (self.layer_min_slider, self.layer_max_slider, self.layer_min_spin, self.layer_max_spin):
            widget.setMinimum(preview.layer_min)
            widget.setMaximum(preview.layer_max)
        self.layer_min_slider.setValue(preview.layer_min)
        self.layer_max_slider.setValue(preview.layer_max)
        self.layer_min_spin.setValue(preview.layer_min)
        self.layer_max_spin.setValue(preview.layer_max)
        self._updating_layer_controls = False
        self._sync_legend_from_settings()
        self._sync_progress_controls()
        self._update_preview_summary()

    def _sync_progress_controls(self) -> None:
        self._updating_progress_controls = True
        if self.gcode_preview is None:
            for slider in self._progress_sliders():
                slider.setMinimum(0)
                slider.setMaximum(0)
                slider.setValue(0)
                slider.setEnabled(False)
            for label in self._progress_labels():
                label.setText(tr(self.language, "progress_empty"))
            self._updating_progress_controls = False
            return
        state = self.viewer.progress_state()
        total = int(state.get("layer_step_count", 0))
        index = int(state.get("progress_index", 0))
        for slider in self._progress_sliders():
            slider.blockSignals(True)
            slider.setEnabled(total > 0)
            slider.setMinimum(0)
            slider.setMaximum(max(0, total - 1))
            slider.setValue(index)
            slider.blockSignals(False)
        current = state.get("current_step") or {}
        label = tr(
            self.language,
            "progress_label_text",
            current=index + 1 if total else 0,
            total=total,
            percent=float(state.get("progress_percent", 0.0)) * 100.0,
            line=current.get("line_number", "-"),
            move=current.get("move_type", "-"),
        )
        for progress_label in self._progress_labels():
            progress_label.setText(label)
        self._updating_progress_controls = False

    def _progress_sender_slider(self) -> QSlider:
        sender = self.sender()
        if isinstance(sender, QSlider):
            return sender
        return self.progress_slider

    def _progress_sliders(self) -> list[QSlider]:
        return [self.progress_slider, self.preview_progress_slider]

    def _progress_labels(self) -> list[QLabel]:
        return [self.progress_step_label, self.preview_progress_label]

    def _sync_legend_from_settings(self) -> None:
        settings = self.viewer.preview_settings
        widgets = [self.travel_checkbox, self.extrusion_checkbox, self.pose_checkbox, *self.role_checkboxes.values()]
        for widget in widgets:
            widget.blockSignals(True)
        self.travel_checkbox.setChecked(settings.show_travel)
        self.extrusion_checkbox.setChecked(settings.show_extrusion)
        self.pose_checkbox.setChecked(settings.show_pose_samples)
        for role, checkbox in self.role_checkboxes.items():
            checkbox.setChecked(role in settings.visible_roles)
        for widget in widgets:
            widget.blockSignals(False)

    def _sync_legend_labels(self) -> None:
        for role, checkbox in self.role_checkboxes.items():
            checkbox.setText(role_label(role, self.language))

    def _update_workbench_texts(self) -> None:
        current = self._current_workbench()
        self.workbench_title.setText(current.title_en if self.language == "en" else current.title_zh)
        self.workbench_summary.setText(current.summary_en if self.language == "en" else current.summary_zh)
        for workbench in WORKBENCHES:
            title = workbench.title_en if self.language == "en" else workbench.title_zh
            summary = workbench.summary_en if self.language == "en" else workbench.summary_zh
            status = workbench.status_en if self.language == "en" else workbench.status_zh
            self.workbench_buttons[workbench.key].setText(f"{title}\n{summary}\n[{status}]")

    def _update_operation_combo(self) -> None:
        current = self.current_operation
        self.operation_combo.blockSignals(True)
        self.operation_combo.clear()
        self.operation_combo.addItem(tr(self.language, "operation_imported_nc"), "imported_nc_review")
        self.operation_combo.addItem(tr(self.language, "operation_curve"), "curve_buildup")
        self.operation_combo.addItem(tr(self.language, "operation_freeform"), "freeform_coating")
        self.operation_combo.setCurrentIndex(max(0, self.operation_combo.findData(current)))
        self.operation_combo.blockSignals(False)

    def _update_file_labels(self) -> None:
        self.model_file_label.setText(
            tr(self.language, "file_none")
            if self.model is None
            else str(self.model.source_path)
        )
        self.gcode_file_label.setText(
            tr(self.language, "file_none")
            if self.gcode_preview is None
            else str(self.gcode_preview.source_path)
        )

    def _update_preview_summary(self) -> None:
        if self.gcode_preview is None:
            self.preview_summary.setText(tr(self.language, "no_gcode"))
            self._update_segment_property()
            return
        summary = self.gcode_preview.summary()
        settings = self.viewer.preview_settings
        self.preview_summary.setText(
            tr(
                self.language,
                "preview_summary_text",
                segments=summary["segment_count"],
                visible=self.viewer.visible_path_segment_count,
                steps=summary.get("timeline_step_count", 0),
                layers=f"{settings.layer_min}-{settings.layer_max}",
                roles=len(summary["role_counts"]),
                axes=", ".join(summary["rotary_axes"]) or "-",
                coord=self._coordinate_transform_label(summary.get("coordinate_transform", "machine_xyz")),
                render=self.viewer.path_render_mode,
            )
        )
        self._update_segment_property()

    def _update_segment_property(self) -> None:
        step = self.viewer.current_progress_step()
        segment = self.viewer.representative_path_segment()
        current = step or segment
        if current is None:
            self.segment_property.setText(tr(self.language, "segment_property_none"))
            return
        rotary = current.rotary_end or current.rotary_start
        rotary_text = ", ".join(f"{axis}={value:.3f}" for axis, value in sorted(rotary.items())) or "-"
        self.segment_property.setText(
            tr(
                self.language,
                "segment_property_text",
                step=current.step_index,
                line=current.line_number,
                layer=current.layer,
                move=current.move_type,
                role=role_label(current.extrusion_role, self.language),
                start=self._format_point(current.start),
                end=self._format_point(current.end),
                machine_start=self._format_point(current.machine_start or current.start),
                machine_end=self._format_point(current.machine_end or current.end),
                feedrate="-" if current.feedrate is None else f"{current.feedrate:.1f}",
                delta_e=f"{current.delta_e:.5f}",
                width="-" if current.width is None else f"{current.width:.3f}",
                height="-" if current.height is None else f"{current.height:.3f}",
                rotary=rotary_text,
                comment=current.comment or "-",
            )
        )

    def _format_point(self, point: tuple[float, float, float]) -> str:
        return f"X{point[0]:.3f}, Y{point[1]:.3f}, Z{point[2]:.3f}"

    def _coordinate_transform_label(self, transform: str) -> str:
        if transform == "ac_inverse_rz_minus_c_after_rx_minus_a":
            return tr(self.language, "coord_ac_inverse")
        return tr(self.language, "coord_machine_xyz")

    def _update_checks(self) -> None:
        lines: list[str] = []
        lines.append(tr(self.language, "check_workbench", workbench=self._current_workbench().title_en))
        if self.model is None:
            lines.append(tr(self.language, "check_no_model"))
        else:
            lines.append(
                tr(
                    self.language,
                    "check_model",
                    bodies=len(self.model.bodies),
                    edges=len(self.model.edges),
                )
            )
        if self.gcode_preview is None:
            lines.append(tr(self.language, "check_no_gcode"))
        else:
            summary = self.gcode_preview.summary()
            lines.append(
                tr(
                    self.language,
                    "check_gcode",
                    segments=summary["segment_count"],
                    layers=summary["layer_count"],
                    axes=", ".join(summary["rotary_axes"]) or "-",
                )
            )
            if "unknown" in summary["role_counts"]:
                lines.append(tr(self.language, "check_unknown_roles", count=summary["role_counts"]["unknown"]))
        lines.append(tr(self.language, "check_warning_policy"))
        self.checks_text.setPlainText("\n".join(lines))

    def _current_workbench(self) -> WorkbenchInfo:
        return next(workbench for workbench in WORKBENCHES if workbench.key == self.current_workbench_key)

    def _workbench_state(self) -> dict[str, Any]:
        return {
            "workbench": self.current_workbench_key,
            "operation": self.current_operation,
            "operation_label": tr(self.language, "operation_imported_nc")
            if self.current_operation == "imported_nc_review"
            else self.current_operation,
        }

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
