from __future__ import annotations

"""Interactive slicing-result page used by the desktop application shell.

The page intentionally owns presentation state only.  File dialogs, project
navigation, background worker lifetime, and paper-image composition stay in
their dedicated application modules.  A viewer factory can be injected so Qt
integration tests do not need to create a VTK or OpenGL context.
"""

from bisect import bisect_left, bisect_right
from copy import deepcopy
from dataclasses import dataclass, fields
import logging
from pathlib import Path
import re
from typing import Any, Callable

import numpy as np

from .gcode_source import GCodeSourceIndex
from .localization import tr
from .result_state import (
    IllustrativeProcessParameters,
    LoadRequest,
    LoadResult,
    ResultPreviewState,
)
from .theme import LIGHT_THEME, UI_TYPOGRAPHY


try:  # Importing data modules remains possible in headless/minimal installs.
    from PyQt5.QtCore import (
        QEvent,
        QObject,
        QRect,
        QRunnable,
        QSize,
        QSignalBlocker,
        QThreadPool,
        QTimer,
        Qt,
        pyqtSignal,
        pyqtSlot,
    )
    from PyQt5.QtGui import (
        QColor,
        QFont,
        QFontMetrics,
        QImage,
        QPainter,
        QPen,
        QSyntaxHighlighter,
        QTextCharFormat,
        QTextCursor,
    )
    from PyQt5.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSlider,
        QSpinBox,
        QStyle,
        QTextEdit,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

    from .viewer_overlays import AxisTriadOverlay, OrientationCubeOverlay

    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the GUI extra.
    QT_AVAILABLE = False


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIRECTORY = ROOT / "outputs" / "paper_preview_acceptance"
CONTEXT_RADIUS = 20
PLAYBACK_INTERVAL_MS = 80
LOGGER = logging.getLogger(__name__)


class ResultCommitError(RuntimeError):
    """A prepared result could not be applied without reverting the page."""

    def __init__(
        self,
        request_id: object,
        cause: BaseException,
        rollback_errors: tuple[str, ...] = (),
    ) -> None:
        detail = f"Failed to commit result request {request_id!r}: {cause}"
        if rollback_errors:
            detail += f"; rollback diagnostics: {'; '.join(rollback_errors)}"
        super().__init__(detail)
        self.request_id = request_id
        self.cause = cause
        self.rollback_errors = rollback_errors


@dataclass(frozen=True, slots=True)
class PreparedLoadCommit:
    """Validated page transaction carrying a detached rollback snapshot."""

    result: LoadResult
    previous_model: Any | None
    previous_preview: Any | None
    previous_source_index: GCodeSourceIndex | None
    previous_owns_source_index: bool
    previous_source_audits: dict[str, dict[str, Any]]
    previous_state: dict[str, Any]
    previous_stage_entries: list[dict[str, Any]]
    previous_stage_progress_start: int
    previous_stage_progress_end: int
    previous_stage_uses_layer_filter: bool
    previous_progress_minimum: int
    previous_progress_maximum: int
    previous_progress_value: int
    previous_current_line: int
    previous_context_lines: list[tuple[int, str]]
    model: Any | None
    preview: Any | None
    source_index: GCodeSourceIndex | None
    owns_source_index: bool
    source_audits: dict[str, dict[str, Any]]
    stage_entries: list[dict[str, Any]]
    quality_mode: str


def _default_viewer_factory(parent: Any) -> Any:
    from .viewer import ModelViewer

    return ModelViewer(parent)


def _compact_number(value: float, precision: int = 6) -> str:
    if not np.isfinite(value):
        return "—"
    if abs(value - round(value)) <= 1e-9:
        return str(int(round(value)))
    return f"{value:.{precision}f}".rstrip("0").rstrip(".")


if QT_AVAILABLE:

    class _Card(QFrame):
        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setObjectName("resultCard")
            self.setFrameShape(QFrame.NoFrame)


    class _MiddleElidingPathLabel(QLabel):
        """Single-line source label that never dictates the sidebar width."""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._full_text = ""
            self.setMinimumWidth(0)
            self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            self.setTextInteractionFlags(Qt.TextSelectableByMouse)

        def set_source_text(self, text: str, *, tooltip: str = "") -> None:
            self._full_text = str(text)
            self.setToolTip(tooltip)
            self.setAccessibleName(self._full_text)
            self.setAccessibleDescription(tooltip)
            self._refresh_elision()

        def full_text(self) -> str:
            return self._full_text

        def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
            hint = super().minimumSizeHint()
            hint.setWidth(0)
            return hint

        def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            self._refresh_elision()

        def changeEvent(self, event) -> None:  # noqa: N802 - Qt API
            super().changeEvent(event)
            if event.type() in {QEvent.FontChange, QEvent.StyleChange}:
                self._refresh_elision()

        def _refresh_elision(self) -> None:
            width = max(0, self.contentsRect().width())
            elided = self.fontMetrics().elidedText(self._full_text, Qt.ElideMiddle, width)
            if super().text() != elided:
                super().setText(elided)


    class _WrappingLabel(QLabel):
        """Width-neutral label with deterministic height-for-width geometry."""

        def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
            super().__init__(text, parent)
            self.setWordWrap(True)
            self.setMinimumWidth(0)
            self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt API
            return True

        def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt API
            margins = self.contentsMargins()
            text_width = max(1, width - margins.left() - margins.right())
            bounds = self.fontMetrics().boundingRect(
                QRect(0, 0, text_width, 10_000),
                Qt.TextWordWrap,
                self.text(),
            )
            return bounds.height() + margins.top() + margins.bottom()

        def setText(self, text: str) -> None:  # noqa: N802 - Qt API
            super().setText(text)
            self._sync_minimum_height()

        def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            self._sync_minimum_height()

        def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
            width = max(1, self.width())
            return QSize(0, self.heightForWidth(width))

        def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
            margins = self.contentsMargins()
            return QSize(0, self.fontMetrics().height() + margins.top() + margins.bottom())

        def _sync_minimum_height(self) -> None:
            required = self.heightForWidth(max(1, self.width()))
            if self.minimumHeight() != required:
                self.setMinimumHeight(required)
                self.updateGeometry()


    class _ColorLegend(QWidget):
        """Small, export-safe legend drawn without icon assets."""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.start_text = "Start"
            self.end_text = "End"
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._font = QFont("Segoe UI")
            self._font.setPixelSize(UI_TYPOGRAPHY.body_px)
            self._refresh_size()

        def set_texts(self, start: str, end: str) -> None:
            self.start_text = start
            self.end_text = end
            self._refresh_size()
            self.update()

        def _refresh_size(self) -> None:
            metrics = QFontMetrics(self._font)
            text_width = metrics.horizontalAdvance(self.start_text) + metrics.horizontalAdvance(
                self.end_text
            )
            self.setFixedSize(max(210, 72 + text_width), 42)

        def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor(LIGHT_THEME.border), 1))
            painter.setBrush(QColor(255, 255, 255, 228))
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
            painter.setFont(self._font)
            painter.setPen(QColor(LIGHT_THEME.text))
            painter.setBrush(QColor("#16845B"))
            painter.drawEllipse(10, 16, 10, 10)
            painter.drawText(27, 27, self.start_text)
            first_width = QFontMetrics(self._font).horizontalAdvance(self.start_text)
            second_x = 27 + first_width + 24
            painter.setBrush(QColor("#D92D20"))
            painter.drawEllipse(second_x, 16, 10, 10)
            painter.drawText(second_x + 17, 27, self.end_text)
            painter.end()


    class _ViewerCanvas(QFrame):
        """Viewer host with vector overlays kept separate from render geometry."""

        def __init__(self, viewer: QWidget, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setObjectName("resultViewerCanvas")
            self.setMinimumSize(540, 390)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(viewer)
            self.viewer = viewer

            self.orientation_cube = OrientationCubeOverlay(viewer, self)
            self.axis_triad = AxisTriadOverlay(viewer, self)
            self.legend = _ColorLegend(self)
            self.tool_rail = QFrame(self)
            self.tool_rail.setObjectName("viewToolRail")
            rail_layout = QHBoxLayout(self.tool_rail)
            rail_layout.setContentsMargins(5, 5, 5, 5)
            rail_layout.setSpacing(4)
            self.fit_button = QToolButton(self.tool_rail)
            self.home_button = QToolButton(self.tool_rail)
            self.fit_button.setText("FIT")
            self.home_button.setText("ISO")
            for button in (self.fit_button, self.home_button):
                button.setFixedSize(68, 36)
                rail_layout.addWidget(button)
            self.tool_rail.adjustSize()

            self.fit_button.clicked.connect(self._fit_view)
            self.home_button.clicked.connect(self._home_view)

        def _fit_view(self) -> None:
            if hasattr(self.viewer, "fit_view"):
                self.viewer.fit_view()

        def _home_view(self) -> None:
            if hasattr(self.viewer, "home_view"):
                self.viewer.home_view()
            elif hasattr(self.viewer, "set_standard_view"):
                self.viewer.set_standard_view("isometric")

        def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            margin = 12
            self.tool_rail.adjustSize()
            self.tool_rail.move(margin, margin)
            self.orientation_cube.move(
                max(margin, self.width() - self.orientation_cube.width() - margin),
                margin,
            )
            self.axis_triad.move(
                margin,
                max(margin, self.height() - self.axis_triad.height() - margin),
            )
            self.legend.move(
                max(margin, self.width() - self.legend.width() - margin),
                max(margin, self.height() - self.legend.height() - margin),
            )
            for child in (self.tool_rail, self.orientation_cube, self.axis_triad, self.legend):
                child.raise_()


    class GCodeSyntaxHighlighter(QSyntaxHighlighter):
        """Highlight the five G-code word groups used by the paper figure."""

        _WORD_PATTERN = re.compile(
            r"(?<![A-Za-z])(?P<axis>[FXYZACE])\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?",
            re.IGNORECASE,
        )

        def __init__(self, document) -> None:
            super().__init__(document)
            self.formats: dict[str, QTextCharFormat] = {}
            for key, color in (
                ("F", "#2563EB"),
                ("XYZ", "#16845B"),
                ("AC", "#E26A00"),
                ("E", "#7A5AF8"),
            ):
                text_format = QTextCharFormat()
                text_format.setForeground(QColor(color))
                text_format.setFontWeight(QFont.DemiBold)
                self.formats[key] = text_format
            self.comment_format = QTextCharFormat()
            self.comment_format.setForeground(QColor(LIGHT_THEME.muted_text))

        def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API
            code_start = text.find("  ")
            source = text[code_start + 2 :] if code_start >= 0 else text
            source_offset = code_start + 2 if code_start >= 0 else 0
            comment_offset = source.find(";")
            code = source if comment_offset < 0 else source[:comment_offset]
            for match in self._WORD_PATTERN.finditer(code):
                axis = match.group("axis").upper()
                key = "XYZ" if axis in "XYZ" else "AC" if axis in "AC" else axis
                self.setFormat(source_offset + match.start(), match.end() - match.start(), self.formats[key])
            if comment_offset >= 0:
                self.setFormat(
                    source_offset + comment_offset,
                    len(source) - comment_offset,
                    self.comment_format,
                )


    class _IndexTaskSignals(QObject):
        finished = pyqtSignal(int, str, object, object)


    class _IndexTask(QRunnable):
        """One cancellable-by-generation read operation on a source index."""

        def __init__(
            self,
            token: int,
            operation: str,
            index: GCodeSourceIndex,
            *,
            query: str = "",
            start_line: int = 1,
            forward: bool = True,
        ) -> None:
            super().__init__()
            self.token = token
            self.operation = operation
            self.index = index
            self.query = query
            self.start_line = start_line
            self.forward = forward
            self.signals = _IndexTaskSignals()

        @pyqtSlot()
        def run(self) -> None:
            try:
                if self.operation == "representative":
                    result = self.index.representative_five_axis_line()
                else:
                    result = self.index.search(self.query, self.start_line, self.forward)
                error = None
            except Exception as exc:  # The UI also tolerates an index replaced mid-search.
                result = None
                error = str(exc)
            self.signals.finished.emit(self.token, self.operation, result, error)


    class ResultPreviewPage(QWidget):
        """Three-column slicing-result page with atomic load presentation."""

        _EXPORT_BLOCKED_EVENT_TYPES = frozenset(
            {
                QEvent.MouseButtonPress,
                QEvent.MouseButtonRelease,
                QEvent.MouseButtonDblClick,
                QEvent.MouseMove,
                QEvent.Enter,
                QEvent.Leave,
                QEvent.HoverEnter,
                QEvent.HoverMove,
                QEvent.HoverLeave,
                QEvent.Wheel,
                QEvent.KeyPress,
                QEvent.KeyRelease,
                QEvent.Shortcut,
                QEvent.ShortcutOverride,
                QEvent.ContextMenu,
                QEvent.InputMethod,
                QEvent.TouchBegin,
                QEvent.TouchUpdate,
                QEvent.TouchEnd,
                QEvent.TouchCancel,
                QEvent.TabletPress,
                QEvent.TabletMove,
                QEvent.TabletRelease,
                QEvent.Gesture,
                QEvent.GestureOverride,
                QEvent.NativeGesture,
                QEvent.DragEnter,
                QEvent.DragMove,
                QEvent.DragLeave,
                QEvent.Drop,
            }
        )

        back_requested = pyqtSignal()
        load_demo_requested = pyqtSignal()
        open_gcode_requested = pyqtSignal()
        open_step_requested = pyqtSignal()
        slice_preview_requested = pyqtSignal()
        cancel_loading_requested = pyqtSignal()
        parameters_changed = pyqtSignal(object)
        quality_changed = pyqtSignal(str)
        stage_changed = pyqtSignal(str)
        display_state_changed = pyqtSignal(object)
        export_requested = pyqtSignal(str)
        output_directory_changed = pyqtSignal(str)

        def __init__(
            self,
            state: ResultPreviewState | None = None,
            viewer_factory: Callable[[QWidget], QWidget] | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.state = state or ResultPreviewState()
            self.language = "zh"
            self._model: Any | None = None
            self._preview: Any | None = None
            self._source_index: GCodeSourceIndex | None = None
            self._source_audits: dict[str, dict[str, Any]] = {}
            self._reference_image_path: Path | None = None
            self._owns_source_index = False
            self._search_token = 0
            self._search_tasks: set[_IndexTask] = set()
            self._current_line = 1
            self._context_lines: list[tuple[int, str]] = []
            self._stage_entries: list[dict[str, Any]] = []
            self._stage_progress_start = 0
            self._stage_progress_end = 0
            self._stage_uses_layer_filter = False
            self._playback_tick = 0
            self._thumbnail_image = QImage()
            self._thread_pool = QThreadPool.globalInstance()
            self._output_directory = DEFAULT_OUTPUT_DIRECTORY
            self._export_interaction_locked = False

            factory = viewer_factory or _default_viewer_factory
            self.viewer = factory(self)
            if not isinstance(self.viewer, QWidget):
                raise TypeError("viewer_factory must return a QWidget-compatible viewer")

            self._playback_timer = QTimer(self)
            self._playback_timer.setInterval(PLAYBACK_INTERVAL_MS)
            self._playback_timer.timeout.connect(self._advance_playback)

            self._build_ui()
            self._event_filter_application = QApplication.instance()
            if self._event_filter_application is not None:
                self._event_filter_application.installEventFilter(self)
            self._connect_controls()
            self._load_parameters_into_editors()
            self._apply_state_to_controls()
            self.retranslate(self.language)
            self._update_sources()
            self._update_status()
            self._update_statistics()
            self._update_context()

        # ------------------------------------------------------------------
        # Public integration contract

        def retranslate(self, language: str) -> None:
            self.language = language if language in {"zh", "en"} else "zh"
            self.title_label.setText(tr(self.language, "result_preview_title"))
            self.subtitle_label.setText(tr(self.language, "result_preview_subtitle"))
            self.back_button.setText(tr(self.language, "result_back_to_workbench"))
            self.sources_heading.setText(tr(self.language, "result_column_sources"))
            self.viewer_heading.setText(tr(self.language, "result_column_viewer"))
            self.analysis_heading.setText(tr(self.language, "result_column_analysis"))
            self.source_card_title.setText(tr(self.language, "result_current_source"))
            self.model_source_title.setText(tr(self.language, "result_model_source"))
            self.gcode_source_title.setText(tr(self.language, "result_gcode_source"))
            self.reference_source_title.setText(tr(self.language, "result_reference_image"))
            self.demo_button.setText(tr(self.language, "result_load_impeller_demo"))
            self.open_gcode_button.setText(tr(self.language, "result_open_existing_gcode"))
            self.open_step_button.setText(tr(self.language, "result_open_step"))
            self.slice_button.setText(tr(self.language, "result_slice_and_preview"))
            self.parameters_title.setText(tr(self.language, "process_parameters"))
            self.parameter_labels["layer_height"].setText(tr(self.language, "parameter_layer_height"))
            self.parameter_labels["print_speed"].setText(tr(self.language, "parameter_print_speed"))
            self.parameter_labels["extrusion_width"].setText(tr(self.language, "parameter_extrusion_width"))
            self.parameter_labels["nozzle_diameter"].setText(tr(self.language, "parameter_nozzle_diameter"))
            self.parameter_labels["process_mode"].setText(tr(self.language, "parameter_process_mode"))
            self.parameter_labels["top_bottom"].setText(tr(self.language, "parameter_top_bottom_layers"))
            self.shell_checkbox.setText(tr(self.language, "parameter_process_mode_shell"))
            self.edit_parameters_button.setText(tr(self.language, "parameter_edit"))
            self.save_parameters_button.setText(tr(self.language, "parameter_save"))
            self.reset_parameters_button.setText(tr(self.language, "parameter_reset"))
            self.parameter_feedback.setText("")

            self.viewer_canvas.fit_button.setToolTip(tr(self.language, "tooltip_fit_view"))
            self.viewer_canvas.home_button.setToolTip(tr(self.language, "tooltip_home_view"))
            self.viewer_canvas.orientation_cube.setToolTip(tr(self.language, "tooltip_orientation_cube"))
            self.viewer_canvas.axis_triad.setToolTip(tr(self.language, "view_part_axes"))
            self.viewer_canvas.legend.set_texts(
                tr(self.language, "legend_start"),
                tr(self.language, "legend_end"),
            )
            self.stage_title.setText(tr(self.language, "stage_navigation"))
            self.stage_combo.setToolTip(tr(self.language, "tooltip_stage_navigation"))
            self.stage_fallback_label.setText(tr(self.language, "stage_marker_fallback"))
            self.previous_stage_button.setToolTip(tr(self.language, "result_progress_previous"))
            self.next_stage_button.setToolTip(tr(self.language, "result_progress_next"))
            self.progress_title.setText(tr(self.language, "result_progress"))
            self.progress_slider.setToolTip(tr(self.language, "tooltip_progress"))
            self.quality_title.setText(tr(self.language, "quality_mode"))
            self.quality_combo.setItemText(0, tr(self.language, "quality_interactive"))
            self.quality_combo.setItemText(1, tr(self.language, "quality_paper"))
            self.quality_combo.setToolTip(tr(self.language, "tooltip_quality_mode"))
            self.visibility_title.setText(tr(self.language, "visibility_title"))
            visibility_keys = (
                "visibility_model",
                "visibility_extrusion",
                "visibility_travel",
                "visibility_pose",
                "visibility_start_end",
                "visibility_part_axes",
                "visibility_orientation_cube",
            )
            for checkbox, key in zip(self.visibility_checks, visibility_keys):
                checkbox.setText(tr(self.language, key))

            self.status_card_title.setText(tr(self.language, "result_state"))
            self.statistics_title.setText(tr(self.language, "result_summary"))
            self.thumbnail_title.setText(tr(self.language, "result_thumbnail"))
            self.thumbnail_note.setText(tr(self.language, "result_thumbnail_fixed_camera"))
            self.context_title.setText(tr(self.language, "gcode_context"))
            self.search_edit.setPlaceholderText(tr(self.language, "gcode_search_placeholder"))
            self.search_previous_button.setToolTip(tr(self.language, "gcode_search_previous"))
            self.search_next_button.setToolTip(tr(self.language, "gcode_search_next"))
            self.jump_edit.setPlaceholderText(tr(self.language, "gcode_jump_placeholder"))
            self.jump_button.setText(tr(self.language, "gcode_jump_go"))
            self.export_title.setText(tr(self.language, "paper_export"))
            self.export_description.setText(tr(self.language, "paper_export_description"))
            self.export_preset_value.setText(tr(self.language, "paper_export_preset_4k"))
            self.output_label.setText(tr(self.language, "paper_export_output_folder"))
            self.choose_output_button.setText(tr(self.language, "paper_export_choose_folder"))
            self.export_current_button.setText(tr(self.language, "paper_export_current"))
            self.export_both_button.setText(tr(self.language, "paper_export_both_languages"))
            self.export_current_button.setToolTip(tr(self.language, "tooltip_paper_export"))
            self.export_both_button.setToolTip(tr(self.language, "tooltip_paper_export"))

            self.demo_button.setToolTip(tr(self.language, "tooltip_load_demo"))
            self.open_gcode_button.setToolTip(tr(self.language, "tooltip_open_gcode"))
            self.open_step_button.setToolTip(tr(self.language, "tooltip_open_step"))
            self.slice_button.setToolTip(tr(self.language, "tooltip_slice_preview"))
            self.cancel_button.setToolTip(tr(self.language, "tooltip_cancel_loading"))
            self.edit_parameters_button.setToolTip(tr(self.language, "tooltip_parameter_edit"))
            self.save_parameters_button.setToolTip(tr(self.language, "tooltip_parameter_save"))
            self.reset_parameters_button.setToolTip(tr(self.language, "tooltip_parameter_reset"))
            self.search_edit.setToolTip(tr(self.language, "tooltip_gcode_search"))
            self.jump_edit.setToolTip(tr(self.language, "tooltip_gcode_jump"))

            self._retranslate_statistics()
            if self.stage_combo.count():
                with QSignalBlocker(self.stage_combo):
                    for index in range(self.stage_combo.count()):
                        entry = self.stage_combo.itemData(index)
                        if isinstance(entry, dict):
                            self.stage_combo.setItemText(index, self._stage_text(entry))
            else:
                self._rebuild_stage_combo(preserve_id=self.state.selected_stage)
            self._update_sources()
            self._update_status()
            self._update_statistics()
            self._update_context_labels()
            self._update_thumbnail_label()
            self._refresh_wrapped_text_geometry()

        def begin_load(self, request: LoadRequest) -> None:
            self._stop_playback()
            self.state.begin_load(request)
            self._update_sources()
            self._update_status()
            self.cancel_button.setEnabled(True)
            self._emit_display_state()

        def set_load_progress(self, request_id: object, phase: str, fraction: float) -> bool:
            accepted = self.state.update_progress(request_id, fraction, phase)
            if accepted:
                self._update_status()
            return accepted

        def commit_load(self, result: LoadResult) -> bool:
            """Prepare and atomically present one current worker result.

            Stale results retain the historical ``False`` return contract.
            Application failures raise :class:`ResultCommitError` after the
            previous page and viewer state have been restored.
            """

            try:
                prepared = self.prepare_load_commit(result)
            except Exception as exc:
                cleanup_errors = self._discard_load_result(result)
                raise ResultCommitError(result.request_id, exc, cleanup_errors) from exc
            if prepared is None:
                self._discard_load_result(result)
                return False
            return self.apply_load_commit(prepared)

        def prepare_load_commit(self, result: LoadResult) -> PreparedLoadCommit | None:
            """Validate a result and capture rollback state without UI mutation."""

            if self.state.status != "loading" or result.request_id != self.state.current_request_id:
                return None
            if result.model_path is not None and result.model is None:
                raise ValueError("The load result has a model path without model data")
            if result.gcode_path is not None and result.gcode_preview is None:
                raise ValueError("The load result has a G-code path without preview data")
            if result.gcode_source_index is not None and result.gcode_preview is None:
                raise ValueError("A source index requires matching G-code preview data")
            if self.state.quality_mode not in {"interactive", "paper"}:
                raise ValueError(f"Unsupported quality mode: {self.state.quality_mode}")

            replacing_gcode = result.gcode_preview is not None
            preview = result.gcode_preview if replacing_gcode else self._preview
            source_index = result.gcode_source_index if replacing_gcode else self._source_index
            owns_source_index = (
                source_index is not None
                if replacing_gcode
                else self._owns_source_index
            )
            stage_entries = self._stage_entries_for(preview, source_index)
            source_audits = deepcopy(self._source_audits)
            source_audits.update(
                {
                    str(role): dict(audit)
                    for role, audit in result.source_audits.items()
                }
            )
            state_snapshot = {
                field.name: deepcopy(getattr(self.state, field.name))
                for field in fields(self.state)
            }
            return PreparedLoadCommit(
                result=result,
                previous_model=self._model,
                previous_preview=self._preview,
                previous_source_index=self._source_index,
                previous_owns_source_index=self._owns_source_index,
                previous_source_audits=deepcopy(self._source_audits),
                previous_state=state_snapshot,
                previous_stage_entries=deepcopy(self._stage_entries),
                previous_stage_progress_start=self._stage_progress_start,
                previous_stage_progress_end=self._stage_progress_end,
                previous_stage_uses_layer_filter=self._stage_uses_layer_filter,
                previous_progress_minimum=self.progress_slider.minimum(),
                previous_progress_maximum=self.progress_slider.maximum(),
                previous_progress_value=self.progress_slider.value(),
                previous_current_line=self._current_line,
                previous_context_lines=list(self._context_lines),
                model=result.model if result.model is not None else self._model,
                preview=preview,
                source_index=source_index,
                owns_source_index=owns_source_index,
                source_audits=source_audits,
                stage_entries=stage_entries,
                quality_mode=self.state.quality_mode,
            )

        def apply_load_commit(self, prepared: PreparedLoadCommit) -> bool:
            """Apply a prepared transaction and transfer its source-index ownership."""

            result = prepared.result
            if self.state.status != "loading" or result.request_id != self.state.current_request_id:
                self._discard_load_result(result)
                return False
            if (
                self._model is not prepared.previous_model
                or self._preview is not prepared.previous_preview
                or self._source_index is not prepared.previous_source_index
            ):
                cause = RuntimeError("The committed page changed after result preparation")
                cleanup_errors = self._discard_load_result(result)
                raise ResultCommitError(result.request_id, cause, cleanup_errors) from cause
            if any(
                getattr(self.state, name) != value
                for name, value in prepared.previous_state.items()
            ):
                cause = RuntimeError("The result state changed after result preparation")
                cleanup_errors = self._discard_load_result(result)
                raise ResultCommitError(result.request_id, cause, cleanup_errors) from cause

            previous_signal_state = self.blockSignals(True)
            attempted_viewer_steps: set[str] = set()
            try:
                self._stop_playback()
                if hasattr(self.viewer, "set_quality_mode"):
                    attempted_viewer_steps.add("quality")
                    self.viewer.set_quality_mode(prepared.quality_mode)
                if result.gcode_preview is not None and hasattr(self.viewer, "load_gcode_preview"):
                    attempted_viewer_steps.add("gcode")
                    self.viewer.load_gcode_preview(prepared.preview)
                if result.model is not None and hasattr(self.viewer, "load_model"):
                    attempted_viewer_steps.add("model")
                    self.viewer.load_model(prepared.model)

                self._model = prepared.model
                self._preview = prepared.preview
                self._source_index = prepared.source_index
                self._owns_source_index = prepared.owns_source_index
                self._source_audits = deepcopy(prepared.source_audits)
                self._stage_entries = deepcopy(prepared.stage_entries)
                if prepared.source_index is not prepared.previous_source_index:
                    self._search_token += 1
                    self._current_line = 1
                    self._context_lines = []

                if not self.state.commit_load(result):
                    raise RuntimeError("The load state changed during result application")
                self._set_post_commit_status()
                with QSignalBlocker(self.quality_combo):
                    self.quality_combo.setCurrentIndex(
                        0 if prepared.quality_mode == "interactive" else 1
                    )
                self._rebuild_stage_combo(preserve_id=self.state.selected_stage)
                self._update_sources()
                self._update_status()
                self._update_statistics()
                self._update_context()
                self._apply_visibility()
                self.cancel_button.setEnabled(False)
                if hasattr(self.viewer, "set_standard_view"):
                    self.viewer.set_standard_view("isometric")
                elif hasattr(self.viewer, "home_view"):
                    self.viewer.home_view()
            except Exception as exc:
                rollback_errors = self._rollback_load_commit(
                    prepared,
                    frozenset(attempted_viewer_steps),
                )
                rollback_errors += self._discard_load_result(result)
                raise ResultCommitError(result.request_id, exc, rollback_errors) from exc
            finally:
                self.blockSignals(previous_signal_state)

            # Ownership changes only after every fallible presentation step has
            # completed.  A result closed by the caller can no longer affect the
            # page's active source index.
            result.gcode_source_index = None
            old_index = prepared.previous_source_index
            if (
                old_index is not None
                and old_index is not prepared.source_index
                and prepared.previous_owns_source_index
            ):
                try:
                    old_index.close()
                except Exception:
                    LOGGER.warning("Failed to close the retired G-code source index", exc_info=True)
            try:
                self._queue_representative_line()
            except Exception:
                LOGGER.warning("Failed to schedule representative G-code lookup", exc_info=True)
            QTimer.singleShot(0, self.capture_thumbnail)
            self._emit_display_state()
            return True

        def _rollback_load_commit(
            self,
            prepared: PreparedLoadCommit,
            attempted_viewer_steps: frozenset[str],
        ) -> tuple[str, ...]:
            """Best-effort viewer compensation followed by exact page-state restore."""

            errors: list[str] = []

            def restore_quality() -> None:
                if hasattr(self.viewer, "set_quality_mode"):
                    self.viewer.set_quality_mode(
                        str(prepared.previous_state["quality_mode"])
                    )

            def restore_gcode() -> None:
                if prepared.previous_preview is not None:
                    if hasattr(self.viewer, "load_gcode_preview"):
                        self.viewer.load_gcode_preview(prepared.previous_preview)
                elif hasattr(self.viewer, "clear_gcode_preview"):
                    self.viewer.clear_gcode_preview()

            def restore_model() -> None:
                if prepared.previous_model is not None:
                    if hasattr(self.viewer, "load_model"):
                        self.viewer.load_model(prepared.previous_model)
                elif hasattr(self.viewer, "clear_model"):
                    self.viewer.clear_model()
                elif hasattr(self.viewer, "model"):
                    self.viewer.model = None
                    raise RuntimeError(
                        "viewer lacks clear_model; empty-scene visual rollback is unverified"
                    )

            operations: list[tuple[str, Callable[[], None]]] = []
            if "quality" in attempted_viewer_steps:
                operations.append(("quality", restore_quality))
            if attempted_viewer_steps.intersection({"gcode", "model"}):
                operations.append(("gcode", restore_gcode))
            if "model" in attempted_viewer_steps:
                operations.append(("model", restore_model))
            for name, operation in operations:
                try:
                    operation()
                except Exception as exc:  # Preserve the primary commit cause.
                    errors.append(f"viewer {name}: {exc}")

            self._model = prepared.previous_model
            self._preview = prepared.previous_preview
            self._source_index = prepared.previous_source_index
            self._owns_source_index = prepared.previous_owns_source_index
            self._source_audits = deepcopy(prepared.previous_source_audits)
            self._stage_entries = deepcopy(prepared.previous_stage_entries)
            self._current_line = prepared.previous_current_line
            self._context_lines = list(prepared.previous_context_lines)
            for name, value in prepared.previous_state.items():
                setattr(self.state, name, deepcopy(value))

            for name, operation in (
                ("controls", self._apply_state_to_controls),
                ("stages", lambda: self._rebuild_stage_combo(self.state.selected_stage)),
            ):
                try:
                    operation()
                except Exception as exc:
                    errors.append(f"page {name}: {exc}")

            # Stage activation is intentionally presentation-oriented and may
            # update serializable progress.  Reapply the exact transaction
            # snapshot and the prior slider/viewer position after rebuilding
            # its widgets.
            for name, value in prepared.previous_state.items():
                setattr(self.state, name, deepcopy(value))
            self._stage_progress_start = prepared.previous_stage_progress_start
            self._stage_progress_end = prepared.previous_stage_progress_end
            self._stage_uses_layer_filter = prepared.previous_stage_uses_layer_filter
            with QSignalBlocker(self.progress_slider):
                self.progress_slider.setRange(
                    prepared.previous_progress_minimum,
                    prepared.previous_progress_maximum,
                )
                self.progress_slider.setValue(prepared.previous_progress_value)
            self.progress_value.setText(f"{self.state.playback_progress * 100:.1f}%")
            if prepared.previous_preview is not None:
                try:
                    self._set_viewer_progress(
                        prepared.previous_stage_progress_start
                        + prepared.previous_progress_value,
                        interactive=False,
                    )
                except Exception as exc:
                    errors.append(f"viewer progress: {exc}")
            self._current_line = prepared.previous_current_line
            self._context_lines = list(prepared.previous_context_lines)

            for name, operation in (
                ("sources", self._update_sources),
                ("status", self._update_status),
                ("statistics", self._update_statistics),
                ("context", self._update_context),
                ("visibility", self._apply_visibility),
            ):
                try:
                    operation()
                except Exception as exc:
                    errors.append(f"page {name}: {exc}")
            return tuple(errors)

        def _discard_load_result(self, result: LoadResult) -> tuple[str, ...]:
            """Close an uncommitted index without closing the active index."""

            if result.gcode_source_index is self._source_index:
                result.gcode_source_index = None
                return ()
            try:
                result.close()
            except Exception as exc:
                return (f"result cleanup: {exc}",)
            return ()

        def fail_load(self, request_id: object, message: str) -> bool:
            if not self.state.fail_load(request_id, message):
                return False
            self._stop_playback()
            self.cancel_button.setEnabled(False)
            self._update_status()
            self._emit_display_state()
            return True

        def cancel_load(self, request_id: object) -> bool:
            if not self.state.cancel_load(request_id):
                return False
            self.cancel_button.setEnabled(False)
            self._update_status()
            self._emit_display_state()
            return True

        def set_warning(self, message: str) -> None:
            self.state.status = "warning"
            self.state.message = str(message)
            self._update_status()
            self._emit_display_state()

        def set_model(self, model: Any | None) -> None:
            self._model = model
            if model is not None and hasattr(self.viewer, "load_model"):
                self.viewer.load_model(model)
            self._update_statistics()

        def set_gcode(
            self,
            preview: Any | None,
            source_index: GCodeSourceIndex | None = None,
            *,
            owns_index: bool = False,
        ) -> None:
            self._stop_playback()
            self._replace_source_index(source_index, owns_index)
            self._preview = preview
            if preview is None:
                if hasattr(self.viewer, "clear_gcode_preview"):
                    self.viewer.clear_gcode_preview()
            elif hasattr(self.viewer, "load_gcode_preview"):
                self.viewer.load_gcode_preview(preview)
            self._build_stage_entries()
            self._rebuild_stage_combo(preserve_id=self.state.selected_stage)
            self._update_statistics()
            self._queue_representative_line()
            self._sync_slice_button()

        def set_reference_image(self, path: str | Path | None) -> None:
            self._reference_image_path = None if path in (None, "") else Path(path).expanduser().resolve()
            self._update_sources()

        def set_selected_model_path(self, path: str | Path | None) -> None:
            self.state.selected_model_path = None if path in (None, "") else Path(path).expanduser().resolve()
            self._update_sources()

        def set_selected_gcode_path(self, path: str | Path | None) -> None:
            self.state.selected_gcode_path = None if path in (None, "") else Path(path).expanduser().resolve()
            self._update_sources()
            self._sync_slice_button()

        def set_quality_mode(self, mode: str, *, emit_signal: bool = True) -> None:
            if mode not in {"interactive", "paper"}:
                raise ValueError(f"Unsupported quality mode: {mode}")
            self.state.quality_mode = mode
            with QSignalBlocker(self.quality_combo):
                self.quality_combo.setCurrentIndex(0 if mode == "interactive" else 1)
            if hasattr(self.viewer, "set_quality_mode"):
                self.viewer.set_quality_mode(mode)
            if emit_signal:
                self.quality_changed.emit(mode)
                self._emit_display_state()

        def set_visibility(
            self,
            *,
            show_model: bool | None = None,
            show_extrusion: bool | None = None,
            show_travel: bool | None = None,
            show_pose_samples: bool | None = None,
            show_start_end: bool | None = None,
            show_axes: bool | None = None,
            show_orientation_cube: bool | None = None,
        ) -> None:
            """Apply shell/menu visibility actions without desynchronizing controls."""

            updates = (
                ("show_model", self.model_check, show_model),
                ("show_extrusion", self.extrusion_check, show_extrusion),
                ("show_travel", self.travel_check, show_travel),
                ("show_pose_samples", self.pose_check, show_pose_samples),
                ("show_start_end", self.start_end_check, show_start_end),
                ("show_axes", self.axes_check, show_axes),
                ("show_orientation_cube", self.cube_check, show_orientation_cube),
            )
            changed = False
            for attribute, checkbox, value in updates:
                if value is None:
                    continue
                normalized = bool(value)
                setattr(self.state, attribute, normalized)
                with QSignalBlocker(checkbox):
                    checkbox.setChecked(normalized)
                changed = True
            if changed:
                self._apply_visibility()
                self._emit_display_state()

        def focus_gcode_search(self) -> None:
            self.search_edit.setFocus(Qt.ShortcutFocusReason)
            self.search_edit.selectAll()

        def focus_gcode_jump(self) -> None:
            self.jump_edit.setFocus(Qt.ShortcutFocusReason)
            self.jump_edit.selectAll()

        def show_representative_instruction(self) -> int | None:
            """Lock the context window to a real F/XYZ/A/C/E instruction."""

            if self._source_index is None:
                return None
            line = self._source_index.representative_five_axis_line()
            if line is not None:
                self._set_context_line(line)
            return line

        def focus_analysis_section(self, section: str) -> None:
            """Scroll the analysis column to a stable section for review/export."""

            targets = {
                "top": self.status_card_title,
                "statistics": self.statistics_title,
                "thumbnail": self.thumbnail_title,
                "gcode": self.context_title,
                "export": self.export_title,
            }
            key = str(section).strip().lower()
            if key not in targets:
                raise ValueError(f"Unknown analysis section: {section}")
            self.right_column.ensureWidgetVisible(targets[key], 0, 8)
            if key == "gcode":
                self.show_representative_instruction()

        @property
        def model(self) -> Any | None:
            return self._model

        @property
        def preview(self) -> Any | None:
            return self._preview

        @property
        def source_index(self) -> GCodeSourceIndex | None:
            return self._source_index

        @property
        def source_audits(self) -> dict[str, dict[str, Any]]:
            return deepcopy(self._source_audits)

        def statistics_json(self) -> dict[str, Any]:
            model_counts = {
                "bodies": 0 if self._model is None else len(getattr(self._model, "bodies", [])),
                "edges": 0 if self._model is None else len(getattr(self._model, "edges", [])),
            }
            if self._preview is None:
                toolpath: dict[str, Any] = {
                    "spatial_segments": 0,
                    "positive_extrusion_segments": 0,
                    "travel_or_non_extrusion_segments": 0,
                    "base_layers": 0,
                    "blade_stages": 0,
                    "layer_range": None,
                    "a_axis_range_deg": None,
                    "c_axis_range_deg": None,
                }
            else:
                total = int(self._preview.total_segment_count)
                extrusion = int(self._preview.move_counts.get("extrude", 0))
                blade_count = 0
                if self._source_index is not None:
                    blade_count = sum(stage.kind == "blade" for stage in self._source_index.stages)
                toolpath = {
                    "spatial_segments": total,
                    "positive_extrusion_segments": extrusion,
                    "travel_or_non_extrusion_segments": max(0, total - extrusion),
                    "base_layers": int(self._preview.layer_count),
                    "blade_stages": blade_count,
                    "layer_range": [int(self._preview.layer_min), int(self._preview.layer_max)],
                    "a_axis_range_deg": self._axis_range_values("A"),
                    "c_axis_range_deg": self._axis_range_values("C"),
                    "coordinate_transform": self._preview.coordinate_transform,
                    "polyline_continuity_tolerance_mm": 0.02,
                }
            return {"geometry": model_counts, "toolpath": toolpath}

        def state_json(self) -> dict[str, Any]:
            payload = self.state.to_json()
            payload["statistics"] = self.statistics_json()
            payload["source_audits"] = self.source_audits
            payload["source_index"] = None
            if self._source_index is not None:
                payload["source_index"] = {
                    **self._source_index.source_signature,
                    "line_count": self._source_index.line_count,
                    "stages": [stage.to_json() for stage in self._source_index.stages],
                    "current_line": self._current_line,
                }
            payload["output_directory"] = str(self._output_directory)
            payload["viewer"] = {
                "capabilities": self._viewer_capabilities(),
                "camera": self._viewer_camera_state(),
                "performance": self.viewer.performance_state()
                if hasattr(self.viewer, "performance_state")
                else {},
            }
            return payload

        def current_state(self) -> dict[str, Any]:
            return self.state_json()

        @property
        def output_directory(self) -> Path:
            return self._output_directory

        def set_output_directory(self, path: str | Path) -> None:
            self._output_directory = Path(path).expanduser().resolve()
            output_path = str(self._output_directory)
            self.output_path_value.set_source_text(output_path, tooltip=output_path)
            self.output_directory_changed.emit(str(self._output_directory))

        def set_export_interaction_locked(self, locked: bool) -> None:
            self._export_interaction_locked = bool(locked)

        def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
            if (
                self._export_interaction_locked
                and isinstance(watched, QWidget)
                and (watched is self or self.isAncestorOf(watched))
                and event.type() in self._EXPORT_BLOCKED_EVENT_TYPES
            ):
                return True
            return super().eventFilter(watched, event)

        def capture_thumbnail(self) -> QImage:
            if not hasattr(self.viewer, "render_scene_image") or self._model is None and self._preview is None:
                self._thumbnail_image = QImage()
                self._update_thumbnail_label()
                return self._thumbnail_image
            try:
                image = self.viewer.render_scene_image(640, 360)
                self._thumbnail_image = image.copy() if isinstance(image, QImage) else QImage()
            except Exception:
                self._thumbnail_image = QImage()
            self._update_thumbnail_label()
            return self._thumbnail_image

        def shutdown(self) -> None:
            self._stop_playback()
            self._search_token += 1
            if self._event_filter_application is not None:
                self._event_filter_application.removeEventFilter(self)
                self._event_filter_application = None
            if self._source_index is not None and self._owns_source_index:
                self._source_index.close()
            self._source_index = None
            self._owns_source_index = False

        # ------------------------------------------------------------------
        # UI construction

        def _build_ui(self) -> None:
            self.setObjectName("resultPreviewPage")
            root_layout = QVBoxLayout(self)
            root_layout.setContentsMargins(14, 12, 14, 14)
            root_layout.setSpacing(10)

            header = QFrame(self)
            header.setObjectName("resultHeader")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(12, 8, 12, 8)
            self.back_button = QPushButton(header)
            self.back_button.setObjectName("secondaryButton")
            self.back_button.setMinimumWidth(138)
            title_layout = QVBoxLayout()
            title_layout.setSpacing(1)
            self.title_label = QLabel(header)
            self.title_label.setObjectName("resultPageTitle")
            self.subtitle_label = QLabel(header)
            self.subtitle_label.setObjectName("resultPageSubtitle")
            title_layout.addWidget(self.title_label)
            title_layout.addWidget(self.subtitle_label)
            header_layout.addWidget(self.back_button)
            header_layout.addSpacing(12)
            header_layout.addLayout(title_layout, 1)
            root_layout.addWidget(header)

            columns = QHBoxLayout()
            columns.setSpacing(10)
            self.left_column = self._build_left_column()
            self.center_column = self._build_center_column()
            self.right_column = self._build_right_column()
            self.left_column.setObjectName("resultLeftColumn")
            self.center_column.setObjectName("resultCenterColumn")
            self.right_column.setObjectName("resultRightColumn")
            self.left_column.setMinimumWidth(250)
            self.center_column.setMinimumWidth(620)
            self.right_column.setMinimumWidth(330)
            columns.addWidget(self.left_column, 18)
            columns.addWidget(self.center_column, 56)
            columns.addWidget(self.right_column, 26)
            root_layout.addLayout(columns, 1)
            self.columns_layout = columns
            self._apply_local_style()

        def _build_left_column(self) -> QWidget:
            content = QWidget(self)
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 0, 0)
            content_layout.setSpacing(8)
            self.sources_heading = self._column_heading(content)
            self.sources_heading.setWordWrap(True)
            content_layout.addWidget(self.sources_heading)

            source_card = _Card(content)
            source_layout = QVBoxLayout(source_card)
            source_layout.setContentsMargins(12, 12, 12, 12)
            source_layout.setSpacing(7)
            self.source_card_title = self._card_title(source_card)
            source_layout.addWidget(self.source_card_title)
            self.model_source_title, self.model_source_value = self._source_row(source_card)
            self.gcode_source_title, self.gcode_source_value = self._source_row(source_card)
            self.reference_source_title, self.reference_source_value = self._source_row(source_card)
            for title, value in (
                (self.model_source_title, self.model_source_value),
                (self.gcode_source_title, self.gcode_source_value),
            ):
                source_layout.addWidget(title)
                source_layout.addWidget(value)
            self.reference_source_title.hide()
            self.reference_source_value.hide()
            self.demo_button = QPushButton(source_card)
            self.demo_button.setObjectName("primaryButton")
            self.open_gcode_button = QPushButton(source_card)
            self.open_step_button = QPushButton(source_card)
            source_layout.addSpacing(3)
            source_layout.addWidget(self.demo_button)
            source_layout.addWidget(self.open_gcode_button)
            source_layout.addWidget(self.open_step_button)
            self.slice_button = QPushButton(source_card)
            self.slice_button.setObjectName("primaryButton")
            source_layout.addSpacing(4)
            source_layout.addWidget(self.slice_button)
            content_layout.addWidget(source_card)

            parameter_card = _Card(content)
            parameter_layout = QVBoxLayout(parameter_card)
            parameter_layout.setContentsMargins(12, 12, 12, 12)
            parameter_layout.setSpacing(8)
            self.parameters_title = self._card_title(parameter_card)
            self.parameters_title.setWordWrap(True)
            parameter_layout.addWidget(self.parameters_title)
            # Retained as hidden compatibility attributes for callers that inspect
            # an older ResultPreviewPage instance.  Production UI omits the
            # Reference evidence remains in the audit record and is not part of the product UI.
            self.parameters_badge = QLabel(parameter_card)
            self.parameters_badge.hide()
            self.parameters_note = QLabel(parameter_card)
            self.parameters_note.hide()

            grid = QGridLayout()
            grid.setVerticalSpacing(4)
            self.parameter_labels: dict[str, QLabel] = {}
            self.layer_height_spin = self._double_spin(0.01, 10.0, 0.01, 2, " mm")
            self.print_speed_spin = self._double_spin(1.0, 1_000_000.0, 10.0, 0, " mm/min")
            self.extrusion_width_spin = self._double_spin(0.01, 10.0, 0.01, 2, " mm")
            self.nozzle_diameter_spin = self._double_spin(0.01, 10.0, 0.01, 2, " mm")
            self.shell_checkbox = QCheckBox(parameter_card)
            self.top_layers_spin = QSpinBox(parameter_card)
            self.bottom_layers_spin = QSpinBox(parameter_card)
            for spin in (self.top_layers_spin, self.bottom_layers_spin):
                spin.setRange(0, 999)
            top_bottom_widget = QWidget(parameter_card)
            top_bottom_layout = QHBoxLayout(top_bottom_widget)
            top_bottom_layout.setContentsMargins(0, 0, 0, 0)
            top_bottom_layout.setSpacing(4)
            slash = QLabel("/", top_bottom_widget)
            slash.setAlignment(Qt.AlignCenter)
            top_bottom_layout.addWidget(self.top_layers_spin)
            top_bottom_layout.addWidget(slash)
            top_bottom_layout.addWidget(self.bottom_layers_spin)
            parameter_rows = (
                ("layer_height", self.layer_height_spin),
                ("print_speed", self.print_speed_spin),
                ("extrusion_width", self.extrusion_width_spin),
                ("nozzle_diameter", self.nozzle_diameter_spin),
                ("process_mode", self.shell_checkbox),
                ("top_bottom", top_bottom_widget),
            )
            for row, (key, editor) in enumerate(parameter_rows):
                label = QLabel(parameter_card)
                label.setObjectName("formLabel")
                self.parameter_labels[key] = label
                grid.addWidget(label, row * 2, 0)
                grid.addWidget(editor, row * 2 + 1, 0)
            parameter_layout.addLayout(grid)
            parameter_buttons = QGridLayout()
            parameter_buttons.setHorizontalSpacing(6)
            parameter_buttons.setVerticalSpacing(6)
            self.edit_parameters_button = QPushButton(parameter_card)
            self.save_parameters_button = QPushButton(parameter_card)
            self.reset_parameters_button = QPushButton(parameter_card)
            parameter_buttons.addWidget(self.edit_parameters_button, 0, 0)
            parameter_buttons.addWidget(self.save_parameters_button, 0, 1)
            parameter_buttons.addWidget(self.reset_parameters_button, 1, 0, 1, 2)
            parameter_buttons.setColumnStretch(0, 1)
            parameter_buttons.setColumnStretch(1, 1)
            parameter_layout.addLayout(parameter_buttons)
            self.parameter_feedback = _WrappingLabel(parent=parameter_card)
            self.parameter_feedback.setObjectName("feedbackLabel")
            self.parameter_feedback.setWordWrap(True)
            parameter_layout.addWidget(self.parameter_feedback)
            content_layout.addWidget(parameter_card)
            content_layout.addStretch(1)
            return self._scroll_column(content)

        def _build_center_column(self) -> QWidget:
            column = QWidget(self)
            layout = QVBoxLayout(column)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            self.viewer_heading = self._column_heading(column)
            layout.addWidget(self.viewer_heading)
            self.viewer_canvas = _ViewerCanvas(self.viewer, column)
            self.viewer_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            layout.addWidget(self.viewer_canvas, 1)

            navigation = _Card(column)
            nav_layout = QGridLayout(navigation)
            nav_layout.setContentsMargins(12, 9, 12, 9)
            nav_layout.setHorizontalSpacing(8)
            nav_layout.setVerticalSpacing(6)
            self.stage_title = QLabel(navigation)
            self.stage_title.setObjectName("formLabel")
            self.stage_combo = QComboBox(navigation)
            self.previous_stage_button = QToolButton(navigation)
            self.previous_stage_button.setText("‹")
            self.next_stage_button = QToolButton(navigation)
            self.next_stage_button.setText("›")
            self.previous_stage_button.setFixedSize(34, 34)
            self.next_stage_button.setFixedSize(34, 34)
            self.progress_title = QLabel(navigation)
            self.progress_title.setObjectName("formLabel")
            self.progress_slider = QSlider(Qt.Horizontal, navigation)
            self.play_button = QToolButton(navigation)
            self.play_button.setText("▶")
            self.play_button.setFixedSize(38, 34)
            self.progress_value = QLabel("0.0%", navigation)
            self.progress_value.setObjectName("monospaceValue")
            self.progress_value.setMinimumWidth(62)
            self.progress_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.quality_title = QLabel(navigation)
            self.quality_title.setObjectName("formLabel")
            self.quality_combo = QComboBox(navigation)
            self.quality_combo.addItem("", "interactive")
            self.quality_combo.addItem("", "paper")
            nav_layout.addWidget(self.stage_title, 0, 0)
            nav_layout.addWidget(self.previous_stage_button, 0, 1)
            nav_layout.addWidget(self.stage_combo, 0, 2, 1, 3)
            nav_layout.addWidget(self.next_stage_button, 0, 5)
            nav_layout.addWidget(self.progress_title, 1, 0)
            nav_layout.addWidget(self.play_button, 1, 1)
            nav_layout.addWidget(self.progress_slider, 1, 2, 1, 3)
            nav_layout.addWidget(self.progress_value, 1, 5)
            nav_layout.addWidget(self.quality_title, 2, 0)
            nav_layout.addWidget(self.quality_combo, 2, 2, 1, 2)
            self.stage_fallback_label = _WrappingLabel(parent=navigation)
            self.stage_fallback_label.setObjectName("mutedNote")
            self.stage_fallback_label.setWordWrap(True)
            nav_layout.addWidget(self.stage_fallback_label, 3, 0, 1, 6)
            layout.addWidget(navigation)

            visibility = _Card(column)
            visibility_layout = QVBoxLayout(visibility)
            visibility_layout.setContentsMargins(12, 8, 12, 8)
            visibility_layout.setSpacing(5)
            self.visibility_title = self._card_title(visibility)
            visibility_layout.addWidget(self.visibility_title)
            check_layout = QGridLayout()
            check_layout.setHorizontalSpacing(12)
            check_layout.setVerticalSpacing(4)
            self.model_check = QCheckBox(visibility)
            self.extrusion_check = QCheckBox(visibility)
            self.travel_check = QCheckBox(visibility)
            self.pose_check = QCheckBox(visibility)
            self.start_end_check = QCheckBox(visibility)
            self.axes_check = QCheckBox(visibility)
            self.cube_check = QCheckBox(visibility)
            self.visibility_checks = (
                self.model_check,
                self.extrusion_check,
                self.travel_check,
                self.pose_check,
                self.start_end_check,
                self.axes_check,
                self.cube_check,
            )
            for index, checkbox in enumerate(self.visibility_checks):
                checkbox.setMinimumWidth(0)
                checkbox.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                check_layout.addWidget(checkbox, index // 2, index % 2)
            visibility_layout.addLayout(check_layout)
            layout.addWidget(visibility)
            return column

        def _build_right_column(self) -> QWidget:
            content = QWidget(self)
            layout = QVBoxLayout(content)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            self.analysis_heading = self._column_heading(content)
            layout.addWidget(self.analysis_heading)

            status_card = _Card(content)
            status_layout = QVBoxLayout(status_card)
            status_layout.setContentsMargins(12, 11, 12, 11)
            status_layout.setSpacing(6)
            self.status_card_title = self._card_title(status_card)
            status_layout.addWidget(self.status_card_title)
            status_row = QHBoxLayout()
            self.status_indicator = QLabel(status_card)
            self.status_indicator.setFixedSize(11, 11)
            self.status_name = QLabel(status_card)
            self.status_name.setObjectName("statusName")
            status_row.addWidget(self.status_indicator)
            status_row.addWidget(self.status_name, 1)
            status_layout.addLayout(status_row)
            self.status_detail = _WrappingLabel(parent=status_card)
            self.status_detail.setWordWrap(True)
            self.status_detail.setObjectName("mutedNote")
            status_layout.addWidget(self.status_detail)
            self.status_progress = QProgressBar(status_card)
            self.status_progress.setRange(0, 1000)
            self.status_progress.setTextVisible(True)
            status_layout.addWidget(self.status_progress)
            self.cancel_button = QPushButton(status_card)
            self.cancel_button.setEnabled(False)
            status_layout.addWidget(self.cancel_button)
            layout.addWidget(status_card)

            statistics_card = _Card(content)
            statistics_layout = QVBoxLayout(statistics_card)
            statistics_layout.setContentsMargins(12, 11, 12, 11)
            statistics_layout.setSpacing(5)
            self.statistics_title = self._card_title(statistics_card)
            statistics_layout.addWidget(self.statistics_title)
            self.statistics_grid = QGridLayout()
            self.statistics_grid.setHorizontalSpacing(10)
            self.statistics_grid.setVerticalSpacing(4)
            self.statistic_labels: dict[str, QLabel] = {}
            self.statistic_values: dict[str, QLabel] = {}
            statistic_keys = (
                "bodies",
                "edges",
                "base_layers",
                "blade_stages",
                "spatial_segments",
                "extrusion_segments",
                "travel_segments",
                "layer_range",
                "a_range",
                "c_range",
            )
            for row, key in enumerate(statistic_keys):
                label = _WrappingLabel(parent=statistics_card)
                value = QLabel("—", statistics_card)
                value.setObjectName("monospaceValue")
                value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.statistic_labels[key] = label
                self.statistic_values[key] = value
                self.statistics_grid.addWidget(label, row, 0)
                self.statistics_grid.addWidget(value, row, 1)
            self.statistics_grid.setColumnStretch(0, 1)
            self.statistics_grid.setColumnStretch(1, 0)
            statistics_layout.addLayout(self.statistics_grid)
            formula_label = _WrappingLabel(parent=statistics_card)
            formula_label.setObjectName("formulaLabel")
            formula_label.setText("P_part = Rz(-C) × Rx(-A) × P_machine")
            formula_label.setWordWrap(True)
            formula_label.setMinimumWidth(0)
            formula_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            formula_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            statistics_layout.addWidget(formula_label)
            self.continuity_label = _WrappingLabel("Polyline: 0.02 mm", statistics_card)
            self.continuity_label.setObjectName("mutedNote")
            self.continuity_label.setWordWrap(True)
            self.continuity_label.setMinimumWidth(0)
            self.continuity_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            statistics_layout.addWidget(self.continuity_label)
            self.statistics_evidence = _WrappingLabel(parent=statistics_card)
            self.statistics_evidence.setObjectName("mutedNote")
            self.statistics_evidence.setWordWrap(True)
            statistics_layout.addWidget(self.statistics_evidence)
            layout.addWidget(statistics_card)

            thumbnail_card = _Card(content)
            thumbnail_layout = QVBoxLayout(thumbnail_card)
            thumbnail_layout.setContentsMargins(12, 10, 12, 10)
            thumbnail_layout.setSpacing(5)
            self.thumbnail_title = self._card_title(thumbnail_card)
            thumbnail_layout.addWidget(self.thumbnail_title)
            self.thumbnail_label = QLabel(thumbnail_card)
            self.thumbnail_label.setObjectName("thumbnailViewport")
            self.thumbnail_label.setMinimumHeight(132)
            self.thumbnail_label.setAlignment(Qt.AlignCenter)
            thumbnail_layout.addWidget(self.thumbnail_label)
            self.thumbnail_note = _WrappingLabel(parent=thumbnail_card)
            self.thumbnail_note.setObjectName("mutedNote")
            self.thumbnail_note.setWordWrap(True)
            thumbnail_layout.addWidget(self.thumbnail_note)
            layout.addWidget(thumbnail_card)

            context_card = _Card(content)
            context_layout = QVBoxLayout(context_card)
            context_layout.setContentsMargins(12, 10, 12, 10)
            context_layout.setSpacing(5)
            self.context_title = self._card_title(context_card)
            context_layout.addWidget(self.context_title)
            search_row = QHBoxLayout()
            self.search_edit = QLineEdit(context_card)
            self.search_previous_button = QToolButton(context_card)
            self.search_previous_button.setText("↑")
            self.search_next_button = QToolButton(context_card)
            self.search_next_button.setText("↓")
            search_row.addWidget(self.search_edit, 1)
            search_row.addWidget(self.search_previous_button)
            search_row.addWidget(self.search_next_button)
            context_layout.addLayout(search_row)
            jump_row = QHBoxLayout()
            self.jump_edit = QLineEdit(context_card)
            self.jump_edit.setMaximumWidth(110)
            self.jump_button = QPushButton(context_card)
            self.context_range_label = _WrappingLabel(parent=context_card)
            self.context_range_label.setObjectName("mutedNote")
            jump_row.addWidget(self.jump_edit)
            jump_row.addWidget(self.jump_button)
            context_layout.addLayout(jump_row)
            self.context_range_label.setWordWrap(True)
            context_layout.addWidget(self.context_range_label)
            self.code_view = QPlainTextEdit(context_card)
            self.code_view.setObjectName("gcodeContextView")
            self.code_view.setReadOnly(True)
            self.code_view.setLineWrapMode(QPlainTextEdit.NoWrap)
            self.code_view.setMinimumHeight(250)
            self.code_highlighter = GCodeSyntaxHighlighter(self.code_view.document())
            context_layout.addWidget(self.code_view)
            self.search_feedback = QLabel(context_card)
            self.search_feedback.setObjectName("feedbackLabel")
            context_layout.addWidget(self.search_feedback)
            layout.addWidget(context_card)

            export_card = _Card(content)
            export_layout = QVBoxLayout(export_card)
            export_layout.setContentsMargins(12, 11, 12, 11)
            export_layout.setSpacing(6)
            self.export_title = self._card_title(export_card)
            self.export_description = _WrappingLabel(parent=export_card)
            self.export_description.setObjectName("mutedNote")
            self.export_description.setWordWrap(True)
            export_layout.addWidget(self.export_title)
            export_layout.addWidget(self.export_description)
            self.export_preset_value = _WrappingLabel(parent=export_card)
            self.export_preset_value.setObjectName("exportPreset")
            self.export_preset_value.setWordWrap(True)
            export_layout.addWidget(self.export_preset_value)
            audit_line = _WrappingLabel(
                "3840 × 2160 px  ·  300 dpi  ·  sRGB  ·  JSON",
                export_card,
            )
            audit_line.setObjectName("mutedNote")
            audit_line.setWordWrap(True)
            audit_line.setMinimumWidth(0)
            audit_line.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            export_layout.addWidget(audit_line)
            self.output_label = QLabel(export_card)
            self.output_label.setObjectName("formLabel")
            export_layout.addWidget(self.output_label)
            self.output_path_value = _MiddleElidingPathLabel(export_card)
            self.output_path_value.setObjectName("pathValue")
            output_path = str(self._output_directory)
            self.output_path_value.set_source_text(output_path, tooltip=output_path)
            self.choose_output_button = QPushButton(export_card)
            export_layout.addWidget(self.output_path_value)
            export_layout.addWidget(self.choose_output_button)
            self.export_current_button = QPushButton(export_card)
            self.export_current_button.setObjectName("primaryButton")
            self.export_both_button = QPushButton(export_card)
            export_layout.addWidget(self.export_current_button)
            export_layout.addWidget(self.export_both_button)
            layout.addWidget(export_card)
            layout.addStretch(1)
            return self._scroll_column(content)

        def _connect_controls(self) -> None:
            self.back_button.clicked.connect(self.back_requested)
            self.demo_button.clicked.connect(self.load_demo_requested)
            self.open_gcode_button.clicked.connect(self.open_gcode_requested)
            self.open_step_button.clicked.connect(self.open_step_requested)
            self.slice_button.clicked.connect(self.slice_preview_requested)
            self.cancel_button.clicked.connect(self._request_cancel)
            self.edit_parameters_button.clicked.connect(lambda: self._set_parameter_editing(True))
            self.save_parameters_button.clicked.connect(self._save_parameters)
            self.reset_parameters_button.clicked.connect(self._reset_parameters)
            self.stage_combo.currentIndexChanged.connect(self._on_stage_changed)
            self.previous_stage_button.clicked.connect(lambda: self._nudge_stage(-1))
            self.next_stage_button.clicked.connect(lambda: self._nudge_stage(1))
            self.progress_slider.sliderPressed.connect(self._on_progress_pressed)
            self.progress_slider.sliderReleased.connect(self._on_progress_released)
            self.progress_slider.valueChanged.connect(self._on_progress_changed)
            self.play_button.clicked.connect(self._toggle_playback)
            self.quality_combo.currentIndexChanged.connect(self._on_quality_changed)
            for checkbox in self.visibility_checks:
                checkbox.toggled.connect(self._on_visibility_changed)
            self.search_edit.returnPressed.connect(lambda: self._start_search(True))
            self.search_previous_button.clicked.connect(lambda: self._start_search(False))
            self.search_next_button.clicked.connect(lambda: self._start_search(True))
            self.jump_edit.returnPressed.connect(self._jump_to_line)
            self.jump_button.clicked.connect(self._jump_to_line)
            self.choose_output_button.clicked.connect(self._choose_output_directory)
            self.export_current_button.clicked.connect(lambda: self.export_requested.emit("current"))
            self.export_both_button.clicked.connect(lambda: self.export_requested.emit("both"))

        # ------------------------------------------------------------------
        # State presentation and controls

        def _apply_state_to_controls(self) -> None:
            with QSignalBlocker(self.model_check):
                self.model_check.setChecked(self.state.show_model)
            with QSignalBlocker(self.extrusion_check):
                self.extrusion_check.setChecked(self.state.show_extrusion)
            with QSignalBlocker(self.travel_check):
                self.travel_check.setChecked(self.state.show_travel)
            with QSignalBlocker(self.pose_check):
                self.pose_check.setChecked(self.state.show_pose_samples)
            with QSignalBlocker(self.start_end_check):
                self.start_end_check.setChecked(self.state.show_start_end)
            with QSignalBlocker(self.axes_check):
                self.axes_check.setChecked(self.state.show_axes)
            with QSignalBlocker(self.cube_check):
                self.cube_check.setChecked(self.state.show_orientation_cube)
            with QSignalBlocker(self.quality_combo):
                self.quality_combo.setCurrentIndex(0 if self.state.quality_mode == "interactive" else 1)
            self._set_parameter_editing(False)
            self._sync_slice_button()

        def _update_sources(self) -> None:
            self._set_path_label(
                self.model_source_value,
                self.state.active_model_path or self.state.selected_model_path,
            )
            self._set_path_label(
                self.gcode_source_value,
                self.state.active_gcode_path or self.state.selected_gcode_path,
            )
            self._set_path_label(self.reference_source_value, self._reference_image_path)
            self._sync_slice_button()

        def _set_path_label(self, label: _MiddleElidingPathLabel, path: Path | None) -> None:
            if path is None:
                label.set_source_text(tr(self.language, "result_source_not_loaded"))
                label.setProperty("loaded", False)
            else:
                label.set_source_text(path.name, tooltip=str(path))
                label.setProperty("loaded", True)
            label.style().unpolish(label)
            label.style().polish(label)

        def _update_status(self) -> None:
            status = self.state.status
            colors = {
                "empty": LIGHT_THEME.muted_text,
                "loading": LIGHT_THEME.primary,
                "ready": LIGHT_THEME.success,
                "warning": LIGHT_THEME.warning,
                "error": LIGHT_THEME.error,
            }
            self.status_indicator.setStyleSheet(
                f"background:{colors.get(status, LIGHT_THEME.muted_text)}; border-radius:5px;"
            )
            self.status_name.setText(tr(self.language, f"result_state_{status}"))
            detail = tr(self.language, f"result_state_{status}_detail")
            if self.state.message:
                if status == "loading":
                    detail = tr(
                        self.language,
                        "result_loading_progress",
                        percent=self.state.progress * 100.0,
                        phase=self.state.message,
                    )
                else:
                    detail = f"{detail}\n{self.state.message}"
            self.status_detail.setText(detail)
            self.status_progress.setVisible(status == "loading")
            self.status_progress.setValue(round(self.state.progress * 1000))
            self.status_progress.setFormat(f"{self.state.progress * 100:.1f}%")
            self.cancel_button.setText(tr(self.language, "action_cancel_loading"))
            self.cancel_button.setVisible(status == "loading")
            self.cancel_button.setEnabled(status == "loading")

        def _set_post_commit_status(self) -> None:
            has_model = self._model is not None
            has_gcode = self._preview is not None
            if has_model and has_gcode:
                self.state.status = "ready"
                self.state.message = ""
            elif has_gcode:
                self.state.status = "warning"
                self.state.message = tr(self.language, "check_no_model")
            elif has_model:
                self.state.status = "warning"
                self.state.message = tr(self.language, "check_no_gcode")
            else:
                self.state.status = "empty"
                self.state.message = ""

        def _request_cancel(self) -> None:
            if self.state.status != "loading":
                return
            self.status_detail.setText(tr(self.language, "result_cancel_requested"))
            self.cancel_button.setEnabled(False)
            self.cancel_loading_requested.emit()

        def _sync_slice_button(self) -> None:
            has_gcode = self.state.selected_gcode_path is not None or self.state.active_gcode_path is not None
            self.slice_button.setEnabled(has_gcode and self.state.status != "loading")

        def _load_parameters_into_editors(self) -> None:
            parameters = self.state.parameters
            self.layer_height_spin.setValue(parameters.layer_height_mm)
            self.print_speed_spin.setValue(parameters.print_speed_mm_min)
            self.extrusion_width_spin.setValue(parameters.extrusion_width_mm)
            self.nozzle_diameter_spin.setValue(parameters.nozzle_diameter_mm)
            self.shell_checkbox.setChecked(parameters.shell_enabled)
            self.top_layers_spin.setValue(parameters.top_layers)
            self.bottom_layers_spin.setValue(parameters.bottom_layers)

        def _set_parameter_editing(self, enabled: bool) -> None:
            for editor in (
                self.layer_height_spin,
                self.print_speed_spin,
                self.extrusion_width_spin,
                self.nozzle_diameter_spin,
                self.shell_checkbox,
                self.top_layers_spin,
                self.bottom_layers_spin,
            ):
                editor.setEnabled(enabled)
            self.save_parameters_button.setEnabled(enabled)
            self.reset_parameters_button.setEnabled(enabled)
            self.edit_parameters_button.setEnabled(not enabled)

        def _save_parameters(self) -> None:
            try:
                parameters = IllustrativeProcessParameters(
                    layer_height_mm=self.layer_height_spin.value(),
                    print_speed_mm_min=self.print_speed_spin.value(),
                    extrusion_width_mm=self.extrusion_width_spin.value(),
                    nozzle_diameter_mm=self.nozzle_diameter_spin.value(),
                    shell_enabled=self.shell_checkbox.isChecked(),
                    top_layers=self.top_layers_spin.value(),
                    bottom_layers=self.bottom_layers_spin.value(),
                )
            except (TypeError, ValueError):
                self.parameter_feedback.setText(tr(self.language, "parameter_invalid"))
                self.parameter_feedback.setProperty("error", True)
                return
            self.state.parameters = parameters
            self.parameter_feedback.setProperty("error", False)
            self.parameter_feedback.setText(tr(self.language, "parameter_saved"))
            self._set_parameter_editing(False)
            self.parameters_changed.emit(parameters)
            self._emit_display_state()

        def _reset_parameters(self) -> None:
            self.state.parameters = IllustrativeProcessParameters()
            self._load_parameters_into_editors()
            self.parameter_feedback.setText("")

        def _on_quality_changed(self, index: int) -> None:
            mode = self.quality_combo.itemData(index)
            if mode in {"interactive", "paper"}:
                self.set_quality_mode(str(mode))

        def _on_visibility_changed(self, _checked: bool) -> None:
            self.state.show_model = self.model_check.isChecked()
            self.state.show_extrusion = self.extrusion_check.isChecked()
            self.state.show_travel = self.travel_check.isChecked()
            self.state.show_pose_samples = self.pose_check.isChecked()
            self.state.show_start_end = self.start_end_check.isChecked()
            self.state.show_axes = self.axes_check.isChecked()
            self.state.show_orientation_cube = self.cube_check.isChecked()
            self._apply_visibility()
            self._emit_display_state()

        def _apply_visibility(self) -> None:
            if hasattr(self.viewer, "set_result_visibility"):
                self.viewer.set_result_visibility(
                    model=self.state.show_model,
                    start_end=self.state.show_start_end,
                    grid=True,
                )
            else:
                if hasattr(self.viewer, "set_model_visible"):
                    self.viewer.set_model_visible(self.state.show_model)
                else:
                    for actor_group in ("body_actors", "edge_actors"):
                        for actor in getattr(self.viewer, actor_group, {}).values():
                            actor.SetVisibility(self.state.show_model)
                if hasattr(self.viewer, "set_start_end_visible"):
                    self.viewer.set_start_end_visible(self.state.show_start_end)
                if hasattr(self.viewer, "set_grid_visible"):
                    self.viewer.set_grid_visible(True)
            if hasattr(self.viewer, "set_preview_visibility"):
                self.viewer.set_preview_visibility(
                    show_travel=self.state.show_travel,
                    show_extrusion=self.state.show_extrusion,
                    show_pose_samples=self.state.show_pose_samples,
                )
            self.viewer_canvas.axis_triad.setVisible(self.state.show_axes)
            self.viewer_canvas.orientation_cube.setVisible(self.state.show_orientation_cube)
            self.viewer_canvas.legend.setVisible(self.state.show_start_end)
            if hasattr(self.viewer, "render"):
                self.viewer.render()

        # ------------------------------------------------------------------
        # Stage and progress navigation

        def _build_stage_entries(self) -> None:
            self._stage_entries = self._stage_entries_for(self._preview, self._source_index)

        @staticmethod
        def _stage_entries_for(
            preview: Any | None,
            source_index: GCodeSourceIndex | None,
        ) -> list[dict[str, Any]]:
            """Build stage metadata without mutating page or viewer state."""

            entries: list[dict[str, Any]] = [{"id": "all", "kind": "all"}]
            stages = () if source_index is None else tuple(source_index.stages)
            if any(stage.kind == "blade" for stage in stages):
                for stage in stages:
                    entries.append(
                        {
                            "id": stage.stage_id,
                            "kind": stage.kind,
                            "ordinal": stage.ordinal,
                            "start_line": stage.start_line,
                            "end_line": stage.end_line,
                        }
                    )
                return entries
            if preview is None or preview.layer_count <= 0:
                return entries
            low = int(preview.layer_min)
            high = int(preview.layer_max)
            chunk_size = max(1, min(25, high - low + 1))
            for start in range(low, high + 1, chunk_size):
                end = min(high, start + chunk_size - 1)
                entries.append(
                    {
                        "id": f"layers_{start}_{end}",
                        "kind": "layers",
                        "layer_min": start,
                        "layer_max": end,
                    }
                )
            return entries

        def _rebuild_stage_combo(self, preserve_id: str | None = None) -> None:
            if not hasattr(self, "stage_combo"):
                return
            selected_id = preserve_id or self.state.selected_stage
            with QSignalBlocker(self.stage_combo):
                self.stage_combo.clear()
                for entry in self._stage_entries or [{"id": "all", "kind": "all"}]:
                    self.stage_combo.addItem(self._stage_text(entry), entry)
                selected_index = 0
                for index in range(self.stage_combo.count()):
                    if self.stage_combo.itemData(index).get("id") == selected_id:
                        selected_index = index
                        break
                self.stage_combo.setCurrentIndex(selected_index)
            has_blade_markers = any(
                entry.get("kind") == "blade" for entry in (self._stage_entries or [])
            )
            self.stage_fallback_label.setVisible(self._preview is not None and not has_blade_markers)
            self._activate_stage(self.stage_combo.currentData() or {"id": "all", "kind": "all"})

        def _stage_text(self, entry: dict[str, Any]) -> str:
            kind = entry.get("kind")
            if kind == "all":
                return tr(self.language, "stage_all")
            if kind == "base":
                return tr(self.language, "stage_base")
            if kind == "blade":
                ordinal = int(entry.get("ordinal") or 1)
                return tr(self.language, f"stage_blade_{max(1, min(8, ordinal))}")
            if kind == "layers":
                return tr(
                    self.language,
                    "stage_layer_range",
                    start=entry["layer_min"],
                    end=entry["layer_max"],
                )
            return str(entry.get("id", ""))

        def _on_stage_changed(self, index: int) -> None:
            entry = self.stage_combo.itemData(index)
            if isinstance(entry, dict):
                self._activate_stage(entry)

        def _activate_stage(self, entry: dict[str, Any]) -> None:
            self._stop_playback()
            stage_id = str(entry.get("id", "all"))
            if self._preview is None:
                self._stage_progress_start = 0
                self._stage_progress_end = 0
                self._stage_uses_layer_filter = False
                with QSignalBlocker(self.progress_slider):
                    self.progress_slider.setRange(0, 0)
                    self.progress_slider.setValue(0)
                self.progress_value.setText("0.0%")
                self.previous_stage_button.setEnabled(False)
                self.next_stage_button.setEnabled(False)
                return
            self.state.selected_stage = stage_id
            self._stage_uses_layer_filter = entry.get("kind") == "layers"
            if self._stage_uses_layer_filter:
                low = int(entry["layer_min"])
                high = int(entry["layer_max"])
                if hasattr(self.viewer, "set_preview_layers"):
                    self.viewer.set_preview_layers(low, high)
                count = int(self._preview.timeline_count_for_layers(low, high))
                self._stage_progress_start = 0
                self._stage_progress_end = max(0, count - 1)
            else:
                if hasattr(self.viewer, "set_preview_layers"):
                    self.viewer.set_preview_layers(self._preview.layer_min, self._preview.layer_max)
                if entry.get("kind") in {"base", "blade"}:
                    start, end = self._timeline_bounds_for_lines(
                        int(entry["start_line"]),
                        int(entry["end_line"]),
                    )
                else:
                    count = int(
                        self._preview.timeline_count_for_layers(
                            self._preview.layer_min,
                            self._preview.layer_max,
                        )
                    )
                    start, end = 0, max(0, count - 1)
                self._stage_progress_start = start
                self._stage_progress_end = end
            maximum = max(0, self._stage_progress_end - self._stage_progress_start)
            with QSignalBlocker(self.progress_slider):
                self.progress_slider.setRange(0, maximum)
                self.progress_slider.setValue(maximum)
            self._set_viewer_progress(self._stage_progress_end, interactive=False)
            self.state.playback_progress = 1.0 if maximum > 0 else 0.0
            self.progress_value.setText(f"{self.state.playback_progress * 100:.1f}%")
            self.previous_stage_button.setEnabled(self.stage_combo.currentIndex() > 0)
            self.next_stage_button.setEnabled(self.stage_combo.currentIndex() + 1 < self.stage_combo.count())
            self.stage_changed.emit(stage_id)
            self._sync_context_from_viewer()
            self._emit_display_state()

        def _timeline_bounds_for_lines(self, start_line: int, end_line: int) -> tuple[int, int]:
            if self._preview is None:
                return 0, 0
            arrays = getattr(self._preview, "timeline_arrays", None)
            if arrays is not None and arrays.count:
                lines = arrays.line_numbers
                start = int(np.searchsorted(lines, start_line, side="left"))
                end = int(np.searchsorted(lines, end_line, side="right")) - 1
                last = arrays.count - 1
                return max(0, min(start, last)), max(0, min(max(start, end), last))
            timeline = getattr(self._preview, "timeline", [])
            if not timeline:
                return 0, 0
            lines = [step.line_number for step in timeline]
            start = bisect_left(lines, start_line)
            end = bisect_right(lines, end_line) - 1
            last = len(lines) - 1
            return max(0, min(start, last)), max(0, min(max(start, end), last))

        def _nudge_stage(self, delta: int) -> None:
            index = max(0, min(self.stage_combo.currentIndex() + delta, self.stage_combo.count() - 1))
            self.stage_combo.setCurrentIndex(index)

        def _on_progress_pressed(self) -> None:
            if hasattr(self.viewer, "set_progress_interaction"):
                self.viewer.set_progress_interaction(True)

        def _on_progress_released(self) -> None:
            if hasattr(self.viewer, "set_progress_interaction"):
                self.viewer.set_progress_interaction(False)
            self._set_viewer_progress(self._viewer_progress_from_slider(), interactive=False)
            self._sync_context_from_viewer()

        def _on_progress_changed(self, value: int) -> None:
            maximum = max(1, self.progress_slider.maximum())
            self.state.playback_progress = value / maximum if self.progress_slider.maximum() > 0 else 0.0
            self.progress_value.setText(f"{self.state.playback_progress * 100:.1f}%")
            self._set_viewer_progress(self._viewer_progress_from_slider(), interactive=True)
            if not self.progress_slider.isSliderDown() and not self._playback_timer.isActive():
                self._sync_context_from_viewer()

        def _viewer_progress_from_slider(self) -> int:
            if self._stage_uses_layer_filter:
                return self.progress_slider.value()
            return self._stage_progress_start + self.progress_slider.value()

        def _set_viewer_progress(self, value: int, *, interactive: bool) -> None:
            if self._preview is not None and hasattr(self.viewer, "set_preview_progress"):
                self.viewer.set_preview_progress(int(value), interactive=interactive)

        def _toggle_playback(self) -> None:
            if self._playback_timer.isActive():
                self._stop_playback()
                return
            if self.progress_slider.value() >= self.progress_slider.maximum():
                self.progress_slider.setValue(0)
            self._playback_tick = 0
            self._playback_timer.start()
            self.play_button.setText("❚❚")
            self.play_button.setToolTip(tr(self.language, "result_progress_pause"))

        def _advance_playback(self) -> None:
            maximum = self.progress_slider.maximum()
            if maximum <= 0 or self.progress_slider.value() >= maximum:
                self._stop_playback()
                self._sync_context_from_viewer()
                return
            step = max(1, maximum // 160)
            self.progress_slider.setValue(min(maximum, self.progress_slider.value() + step))
            self._playback_tick += 1
            if self._playback_tick % 8 == 0:
                self._sync_context_from_viewer()

        def _stop_playback(self) -> None:
            if hasattr(self, "_playback_timer"):
                self._playback_timer.stop()
            if hasattr(self, "play_button"):
                self.play_button.setText("▶")
                self.play_button.setToolTip(tr(self.language, "result_progress_play"))
            if hasattr(self.viewer, "set_progress_interaction"):
                self.viewer.set_progress_interaction(False)

        # ------------------------------------------------------------------
        # Statistics, source context, and export options

        def _retranslate_statistics(self) -> None:
            keys = {
                "bodies": "statistics_bodies",
                "edges": "statistics_edges",
                "base_layers": "statistics_base_layers",
                "blade_stages": "statistics_blade_stages",
                "spatial_segments": "statistics_spatial_segments",
                "extrusion_segments": "statistics_extrusion_segments",
                "travel_segments": "statistics_travel_segments",
                "layer_range": "statistics_layer_range",
                "a_range": "statistics_a_range",
                "c_range": "statistics_c_range",
            }
            for name, key in keys.items():
                self.statistic_labels[name].setText(tr(self.language, key))
            self.statistics_evidence.setText(tr(self.language, "statistics_actual_data"))
            self.continuity_label.setText(
                f"{tr(self.language, 'statistics_continuity_tolerance')}: 0.02 mm"
            )

        def _update_statistics(self) -> None:
            unavailable = tr(self.language, "statistics_unavailable") if hasattr(self, "statistic_values") else "—"
            values: dict[str, str] = {key: unavailable for key in getattr(self, "statistic_values", {})}
            if self._model is not None:
                values["bodies"] = f"{len(getattr(self._model, 'bodies', [])):,}"
                values["edges"] = f"{len(getattr(self._model, 'edges', [])):,}"
            if self._preview is not None:
                total = int(getattr(self._preview, "total_segment_count", 0))
                moves = getattr(self._preview, "move_counts", {})
                extrusion = int(moves.get("extrude", 0))
                values.update(
                    {
                        "base_layers": f"{int(getattr(self._preview, 'layer_count', 0)):,}",
                        "spatial_segments": f"{total:,}",
                        "extrusion_segments": f"{extrusion:,}",
                        "travel_segments": f"{max(0, total - extrusion):,}",
                        "layer_range": (
                            f"[{int(self._preview.layer_min):,}, {int(self._preview.layer_max):,}]"
                        ),
                        "a_range": self._axis_range_text("A"),
                        "c_range": self._axis_range_text("C"),
                    }
                )
            if self._source_index is not None:
                blade_count = sum(stage.kind == "blade" for stage in self._source_index.stages)
                values["blade_stages"] = f"{blade_count:,}"
            for key, label in getattr(self, "statistic_values", {}).items():
                label.setText(values.get(key, unavailable))

        def _axis_range_text(self, axis: str) -> str:
            bounds = self._axis_range_values(axis)
            if bounds is None:
                return "—"
            return f"[{_compact_number(bounds[0])}, {_compact_number(bounds[1])}]°"

        def _axis_range_values(self, axis: str) -> list[float] | None:
            if self._preview is None:
                return None
            values: list[np.ndarray] = []
            arrays = getattr(self._preview, "timeline_arrays", None)
            column = {"A": 0, "B": 1, "C": 2, "U": 3, "V": 4, "W": 5}.get(axis)
            if arrays is not None and column is not None and arrays.count:
                values.extend((arrays.rotary_starts[:, column], arrays.rotary_ends[:, column]))
                finite = np.concatenate([value[np.isfinite(value)] for value in values])
                if axis in getattr(self._preview, "rotary_axes", ()):
                    finite = np.append(finite, 0.0)
                if finite.size:
                    return [float(np.min(finite)), float(np.max(finite))]
            minimum: float | None = None
            maximum: float | None = None
            for segment in getattr(self._preview, "segments", []):
                for rotary in (segment.rotary_start, segment.rotary_end):
                    if axis not in rotary:
                        continue
                    value = float(rotary[axis])
                    minimum = value if minimum is None else min(minimum, value)
                    maximum = value if maximum is None else max(maximum, value)
            if minimum is None or maximum is None:
                return None
            if axis in getattr(self._preview, "rotary_axes", ()):
                minimum = min(minimum, 0.0)
                maximum = max(maximum, 0.0)
            return [minimum, maximum]

        def _replace_source_index(self, index: GCodeSourceIndex | None, owns_index: bool) -> None:
            self._search_token += 1
            previous = self._source_index
            previous_owned = self._owns_source_index
            self._source_index = index
            self._owns_source_index = owns_index
            if previous is not None and previous is not index and previous_owned:
                previous.close()
            self._current_line = 1
            self._context_lines = []
            self._update_context()

        def _queue_representative_line(self) -> None:
            if self._source_index is None:
                self._update_context()
                return
            self._search_token += 1
            token = self._search_token
            task = _IndexTask(token, "representative", self._source_index)
            task.signals.finished.connect(self._on_index_task_finished)
            self._search_tasks.add(task)
            self.search_feedback.setText(tr(self.language, "gcode_searching"))
            self._thread_pool.start(task)

        def _start_search(self, forward: bool) -> None:
            if self._source_index is None:
                return
            query = self.search_edit.text().strip()
            if not query:
                return
            self._search_token += 1
            token = self._search_token
            start_line = self._current_line + (1 if forward else -1)
            task = _IndexTask(
                token,
                "search",
                self._source_index,
                query=query,
                start_line=max(1, min(start_line, self._source_index.line_count)),
                forward=forward,
            )
            task.signals.finished.connect(self._on_index_task_finished)
            self._search_tasks.add(task)
            self.search_feedback.setText(tr(self.language, "gcode_searching"))
            self._thread_pool.start(task)

        @pyqtSlot(int, str, object, object)
        def _on_index_task_finished(
            self,
            token: int,
            operation: str,
            result: object,
            error: object,
        ) -> None:
            self._search_tasks = {task for task in self._search_tasks if task.token != token}
            if token != self._search_token or self._source_index is None:
                return
            if error:
                self.search_feedback.setText(str(error))
                return
            if result is None:
                self.search_feedback.setText(tr(self.language, "gcode_no_matches"))
                if operation == "representative":
                    self._set_context_line(1)
                return
            self.search_feedback.setText("")
            self._set_context_line(int(result))

        def _jump_to_line(self) -> None:
            if self._source_index is None:
                return
            try:
                line = int(self.jump_edit.text().strip())
            except ValueError:
                line = 0
            if not 1 <= line <= self._source_index.line_count:
                self.search_feedback.setText(
                    tr(self.language, "gcode_line_out_of_range", maximum=self._source_index.line_count)
                )
                return
            self.search_feedback.setText("")
            self._set_context_line(line)

        def _sync_context_from_viewer(self) -> None:
            if self._source_index is None or not hasattr(self.viewer, "current_progress_step"):
                return
            step = self.viewer.current_progress_step()
            if step is not None and getattr(step, "line_number", None):
                self._set_context_line(int(step.line_number))

        def _set_context_line(self, line: int) -> None:
            if self._source_index is None:
                return
            self._current_line = max(1, min(int(line), self._source_index.line_count))
            self._context_lines = self._source_index.read_context(self._current_line, CONTEXT_RADIUS)
            self._update_context()

        def _update_context(self) -> None:
            if not hasattr(self, "code_view"):
                return
            if self._source_index is None:
                self.code_view.clear()
                self.context_range_label.setText(tr(self.language, "statistics_unavailable"))
                return
            if not self._context_lines:
                self._context_lines = self._source_index.read_context(self._current_line, CONTEXT_RADIUS)
            width = max(6, len(str(self._source_index.line_count)))
            text = "\n".join(f"{line:>{width}}  {source}" for line, source in self._context_lines)
            self.code_view.setPlainText(text)
            self._highlight_current_context_line()
            self._update_context_labels()

        def _highlight_current_context_line(self) -> None:
            selections: list[QTextEdit.ExtraSelection] = []
            for block_index, (line, _source) in enumerate(self._context_lines):
                if line != self._current_line:
                    continue
                cursor = QTextCursor(self.code_view.document().findBlockByNumber(block_index))
                selection = QTextEdit.ExtraSelection()
                selection.cursor = cursor
                selection.format.setBackground(QColor(LIGHT_THEME.primary_subtle))
                selection.format.setProperty(QTextCharFormat.FullWidthSelection, True)
                selections.append(selection)
                self.code_view.setTextCursor(cursor)
                self.code_view.centerCursor()
                break
            self.code_view.setExtraSelections(selections)

        def _update_context_labels(self) -> None:
            if self._source_index is None:
                self.context_range_label.setText(tr(self.language, "statistics_unavailable"))
                return
            if self._context_lines:
                start = self._context_lines[0][0]
                end = self._context_lines[-1][0]
                self.context_range_label.setText(
                    f"{tr(self.language, 'gcode_current_line', line=self._current_line)}  ·  "
                    f"{tr(self.language, 'gcode_window_range', start=start, end=end)}"
                )

        def _choose_output_directory(self) -> None:
            if self._export_interaction_locked:
                return
            selected = QFileDialog.getExistingDirectory(
                self,
                tr(self.language, "dialog_select_output_title"),
                str(self._output_directory),
            )
            if selected:
                self.set_output_directory(selected)

        def _update_thumbnail_label(self) -> None:
            if self._thumbnail_image.isNull():
                if hasattr(self, "thumbnail_label"):
                    self.thumbnail_label.setPixmap(self.style().standardIcon(QStyle.SP_FileDialogInfoView).pixmap(32, 32))
                    self.thumbnail_label.setToolTip(tr(self.language, "statistics_unavailable"))
                return
            available = self.thumbnail_label.contentsRect().size()
            pixmap = self._thumbnail_image.scaled(
                max(1, available.width()),
                max(1, available.height()),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            from PyQt5.QtGui import QPixmap

            self.thumbnail_label.setPixmap(QPixmap.fromImage(pixmap))
            self.thumbnail_label.setToolTip(tr(self.language, "result_thumbnail_fixed_camera"))

        def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            if not self._thumbnail_image.isNull():
                self._update_thumbnail_label()

        # ------------------------------------------------------------------
        # Small builders and styling

        def _viewer_capabilities(self) -> dict[str, Any]:
            if not hasattr(self.viewer, "capabilities"):
                return {"backend": getattr(self.viewer, "backend", "unknown")}
            try:
                return dict(self.viewer.capabilities())
            except Exception:
                return {"backend": getattr(self.viewer, "backend", "unknown")}

        def _viewer_camera_state(self) -> dict[str, Any]:
            if not hasattr(self.viewer, "camera_state"):
                return {}
            try:
                return dict(self.viewer.camera_state())
            except Exception:
                return {}

        def _emit_display_state(self) -> None:
            self.display_state_changed.emit(self.state_json())

        def _refresh_wrapped_text_geometry(self) -> None:
            """Recompute height-for-width labels after a bilingual text change."""

            wrapped_labels = [label for label in self.findChildren(QLabel) if label.wordWrap()]
            layout_widgets = (
                self,
                self.left_column.widget(),
                self.center_column,
                self.right_column.widget(),
            )
            for label in wrapped_labels:
                label.updateGeometry()
            for widget in layout_widgets:
                layout = widget.layout() if widget is not None else None
                if layout is not None:
                    layout.invalidate()
                    layout.activate()

        def _source_row(self, parent: QWidget) -> tuple[QLabel, _MiddleElidingPathLabel]:
            title = QLabel(parent)
            title.setObjectName("formLabel")
            value = _MiddleElidingPathLabel(parent)
            value.setObjectName("pathValue")
            return title, value

        def _column_heading(self, parent: QWidget) -> QLabel:
            label = _WrappingLabel(parent=parent)
            label.setObjectName("columnHeading")
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            return label

        def _card_title(self, parent: QWidget) -> QLabel:
            label = _WrappingLabel(parent=parent)
            label.setObjectName("cardTitle")
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            return label

        def _double_spin(
            self,
            minimum: float,
            maximum: float,
            step: float,
            decimals: int,
            suffix: str,
        ) -> QDoubleSpinBox:
            spin = QDoubleSpinBox(self)
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)
            spin.setDecimals(decimals)
            spin.setSuffix(suffix)
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            return spin

        def _scroll_column(self, content: QWidget) -> QScrollArea:
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setWidget(content)
            return scroll

        def _apply_local_style(self) -> None:
            self.setStyleSheet(
                f"""
                QWidget#resultPreviewPage {{
                    background: {LIGHT_THEME.window}; color: {LIGHT_THEME.text};
                    font-family: {LIGHT_THEME.ui_font_family}; font-size: {UI_TYPOGRAPHY.body_px}px;
                }}
                QFrame#resultHeader, QFrame#resultCard {{
                    background: {LIGHT_THEME.panel};
                    border: 1px solid {LIGHT_THEME.border};
                    border-radius: 7px;
                }}
                QLabel#resultPageTitle {{ font-size: {UI_TYPOGRAPHY.page_title_px}px; font-weight: 650; color: {LIGHT_THEME.text}; }}
                QLabel#resultPageSubtitle, QLabel#mutedNote {{ color: {LIGHT_THEME.muted_text}; font-size: {UI_TYPOGRAPHY.secondary_px}px; }}
                QLabel#columnHeading {{ font-size: {UI_TYPOGRAPHY.section_title_px}px; font-weight: 650; color: {LIGHT_THEME.text}; padding: 1px 3px; }}
                QLabel#cardTitle, QLabel#statusName {{ font-size: {UI_TYPOGRAPHY.card_title_px}px; font-weight: 650; color: {LIGHT_THEME.text}; }}
                QLabel#formLabel {{ color: {LIGHT_THEME.muted_text}; font-size: {UI_TYPOGRAPHY.label_px}px; }}
                QLabel#pathValue {{
                    background: {LIGHT_THEME.hover_background}; border: 1px solid {LIGHT_THEME.border};
                    border-radius: 4px; padding: 5px; color: {LIGHT_THEME.muted_text};
                }}
                QLabel#pathValue[loaded="true"] {{ color: {LIGHT_THEME.text}; }}
                QLabel#warningBadge {{
                    color: {LIGHT_THEME.warning}; background: #FFF4E8; border-radius: 4px;
                    padding: 3px 5px; font-size: {UI_TYPOGRAPHY.badge_px}px;
                }}
                QLabel#feedbackLabel {{ color: {LIGHT_THEME.success}; font-size: {UI_TYPOGRAPHY.secondary_px}px; }}
                QLabel#feedbackLabel[error="true"] {{ color: {LIGHT_THEME.error}; }}
                QLabel#monospaceValue, QLabel#formulaLabel {{
                    font-family: {LIGHT_THEME.code_font_family}; color: {LIGHT_THEME.text}; font-size: {UI_TYPOGRAPHY.code_px}px;
                }}
                QLabel#formulaLabel {{
                    background: {LIGHT_THEME.code_background}; border: 1px solid {LIGHT_THEME.border};
                    border-radius: 4px; padding: 6px;
                }}
                QLabel#thumbnailViewport {{
                    background: #F6F8FB; border: 1px solid {LIGHT_THEME.border}; border-radius: 5px;
                }}
                QLabel#exportPreset {{
                    color: {LIGHT_THEME.primary}; background: {LIGHT_THEME.primary_subtle};
                    border: 1px solid #BFDBFE; border-radius: 4px; padding: 6px;
                }}
                QFrame#resultViewerCanvas {{
                    background: #F8FAFC; border: 1px solid {LIGHT_THEME.border}; border-radius: 7px;
                }}
                QFrame#viewToolRail {{
                    background: rgba(255,255,255,232); border: 1px solid {LIGHT_THEME.border}; border-radius: 6px;
                }}
                QPushButton#primaryButton {{
                    background: {LIGHT_THEME.primary}; color: white; border-color: {LIGHT_THEME.primary};
                    font-weight: 600;
                }}
                QPushButton#primaryButton:hover {{ background: {LIGHT_THEME.primary_hover}; }}
                QPlainTextEdit#gcodeContextView {{
                    background: {LIGHT_THEME.code_background}; color: {LIGHT_THEME.text};
                    border: 1px solid {LIGHT_THEME.border}; border-radius: 4px;
                    font-family: {LIGHT_THEME.code_font_family}; font-size: {UI_TYPOGRAPHY.code_px}px;
                    selection-background-color: {LIGHT_THEME.selected_background};
                }}
                """
            )


else:

    class GCodeSyntaxHighlighter:  # pragma: no cover - PyQt-free compatibility stub.
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("PyQt5 is required to create the result preview UI")


    class ResultPreviewPage:  # pragma: no cover - PyQt-free compatibility stub.
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("PyQt5 is required to create the result preview UI")


__all__ = [
    "CONTEXT_RADIUS",
    "DEFAULT_OUTPUT_DIRECTORY",
    "GCodeSyntaxHighlighter",
    "PreparedLoadCommit",
    "QT_AVAILABLE",
    "ResultCommitError",
    "ResultPreviewPage",
]
