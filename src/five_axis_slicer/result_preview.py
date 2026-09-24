from __future__ import annotations

"""Interactive slicing-result page used by the desktop application shell.

The page intentionally owns presentation state only. File dialogs, project
navigation, and background worker lifetime stay in dedicated application
modules. A viewer factory can be injected so Qt
integration tests do not need to create a VTK or OpenGL context.
"""

import re
from bisect import bisect_left, bisect_right
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
        QSignalBlocker,
        QSize,
        Qt,
        QThreadPool,
        QTimer,
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
        QDoubleSpinBox,
        QFrame,
        QHBoxLayout,
        QLabel,
        QScrollArea,
        QSizePolicy,
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


CONTEXT_RADIUS = 20
PLAYBACK_INTERVAL_MS = 80


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


_ROTARY_COLUMNS = {"A": 0, "B": 1, "C": 2, "U": 3, "V": 4, "W": 5}


def _timeline_axis_range(preview: Any, axis: str) -> list[float] | None:
    arrays = getattr(preview, "timeline_arrays", None)
    column = _ROTARY_COLUMNS.get(axis)
    if arrays is None or column is None or not arrays.count:
        return None
    endpoints = (arrays.rotary_starts[:, column], arrays.rotary_ends[:, column])
    finite = np.concatenate([values[np.isfinite(values)] for values in endpoints])
    if axis in getattr(preview, "rotary_axes", ()):
        finite = np.append(finite, 0.0)
    if not finite.size:
        return None
    return [float(np.min(finite)), float(np.max(finite))]


def _segment_axis_range(preview: Any, axis: str) -> list[float] | None:
    values = [
        float(rotary[axis])
        for segment in getattr(preview, "segments", [])
        for rotary in (segment.rotary_start, segment.rotary_end)
        if axis in rotary
    ]
    if not values:
        return None
    if axis in getattr(preview, "rotary_axes", ()):
        values.append(0.0)
    return [min(values), max(values)]


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
            self.setMinimumSize(540, 280)
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
        """Highlight the motion words shown in the G-code context pane."""

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
                self.setFormat(
                    source_offset + match.start(), match.end() - match.start(), self.formats[key]
                )
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

            factory = viewer_factory or _default_viewer_factory
            self.viewer = factory(self)
            if not isinstance(self.viewer, QWidget):
                raise TypeError("viewer_factory must return a QWidget-compatible viewer")

            self._playback_timer = QTimer(self)
            self._playback_timer.setInterval(PLAYBACK_INTERVAL_MS)
            self._playback_timer.timeout.connect(self._advance_playback)

            self._build_ui()
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
            from .result_preview_text import retranslate_result_preview

            retranslate_result_preview(self, language)

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
            """Validate a worker result and capture an immutable rollback snapshot."""

            from .result_commit import prepare_load_commit

            return prepare_load_commit(self, result)

        def apply_load_commit(self, prepared: PreparedLoadCommit) -> bool:
            """Apply a prepared result as one presentation transaction."""

            from .result_commit import apply_load_commit

            return apply_load_commit(self, prepared)

        def _rollback_load_commit(
            self,
            prepared: PreparedLoadCommit,
            attempted_viewer_steps: frozenset[str],
        ) -> tuple[str, ...]:
            from .result_commit import rollback_load_commit

            return rollback_load_commit(self, prepared, attempted_viewer_steps)

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

        def set_selected_model_path(self, path: str | Path | None) -> None:
            self.state.selected_model_path = (
                None if path in (None, "") else Path(path).expanduser().resolve()
            )
            self._update_sources()

        def set_selected_gcode_path(self, path: str | Path | None) -> None:
            self.state.selected_gcode_path = (
                None if path in (None, "") else Path(path).expanduser().resolve()
            )
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
            """Scroll the analysis column to a stable review section."""

            targets = {
                "top": self.status_card_title,
                "statistics": self.statistics_title,
                "thumbnail": self.thumbnail_title,
                "gcode": self.context_title,
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

        def capture_thumbnail(self) -> QImage:
            if (
                not hasattr(self.viewer, "render_scene_image")
                or self._model is None
                and self._preview is None
            ):
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
            if self._source_index is not None and self._owns_source_index:
                self._source_index.close()
            self._source_index = None
            self._owns_source_index = False

        # ------------------------------------------------------------------
        # UI construction

        def _build_ui(self) -> None:
            from .result_preview_layout import build_result_preview_ui

            build_result_preview_ui(self)

        def _build_left_column(self) -> QWidget:
            from .result_preview_layout import build_left_column

            return build_left_column(self)

        def _build_center_column(self) -> QWidget:
            from .result_preview_layout import build_center_column

            return build_center_column(self)

        def _build_right_column(self) -> QWidget:
            from .result_preview_layout import build_right_column

            return build_right_column(self)

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
                self.quality_combo.setCurrentIndex(
                    0 if self.state.quality_mode == "interactive" else 1
                )
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
            has_gcode = (
                self.state.selected_gcode_path is not None
                or self.state.active_gcode_path is not None
            )
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
            if any(stage.kind in {"blade", "operation"} for stage in stages):
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
            has_stage_markers = any(
                entry.get("kind") in {"blade", "operation"} for entry in (self._stage_entries or [])
            )
            self.stage_fallback_label.setVisible(
                self._preview is not None and not has_stage_markers
            )
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
            if kind == "operation":
                return tr(self.language, "stage_operation", number=entry.get("ordinal") or 1)
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
            if hasattr(self.viewer, "set_preview_line_range"):
                if entry.get("kind") in {"base", "blade", "operation"}:
                    self.viewer.set_preview_line_range(
                        int(entry["start_line"]), int(entry["end_line"])
                    )
                else:
                    self.viewer.set_preview_line_range(None, None)
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
                if entry.get("kind") in {"base", "blade", "operation"}:
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
            self.next_stage_button.setEnabled(
                self.stage_combo.currentIndex() + 1 < self.stage_combo.count()
            )
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
            index = max(
                0, min(self.stage_combo.currentIndex() + delta, self.stage_combo.count() - 1)
            )
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
            self.state.playback_progress = (
                value / maximum if self.progress_slider.maximum() > 0 else 0.0
            )
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
            unavailable = (
                tr(self.language, "statistics_unavailable")
                if hasattr(self, "statistic_values")
                else "—"
            )
            values: dict[str, str] = {
                key: unavailable for key in getattr(self, "statistic_values", {})
            }
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
            return _timeline_axis_range(self._preview, axis) or _segment_axis_range(
                self._preview,
                axis,
            )

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
                    tr(
                        self.language,
                        "gcode_line_out_of_range",
                        maximum=self._source_index.line_count,
                    )
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
            self._context_lines = self._source_index.read_context(
                self._current_line, CONTEXT_RADIUS
            )
            self._update_context()

        def _update_context(self) -> None:
            if not hasattr(self, "code_view"):
                return
            if self._source_index is None:
                self.code_view.clear()
                self.context_range_label.setText(tr(self.language, "statistics_unavailable"))
                return
            if not self._context_lines:
                self._context_lines = self._source_index.read_context(
                    self._current_line, CONTEXT_RADIUS
                )
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

        def _update_thumbnail_label(self) -> None:
            if self._thumbnail_image.isNull():
                if hasattr(self, "thumbnail_label"):
                    self.thumbnail_label.setPixmap(
                        self.style().standardIcon(QStyle.SP_FileDialogInfoView).pixmap(32, 32)
                    )
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
            from .result_preview_layout import _source_row

            return _source_row(parent)

        def _column_heading(self, parent: QWidget) -> QLabel:
            from .result_preview_layout import _column_heading

            return _column_heading(parent)

        def _card_title(self, parent: QWidget) -> QLabel:
            from .result_preview_layout import _card_title

            return _card_title(parent)

        def _double_spin(
            self,
            minimum: float,
            maximum: float,
            step: float,
            decimals: int,
            suffix: str,
        ) -> QDoubleSpinBox:
            from .result_preview_layout import _double_spin

            return _double_spin(self, minimum, maximum, step, decimals, suffix)

        def _scroll_column(self, content: QWidget) -> QScrollArea:
            from .result_preview_layout import _scroll_column

            return _scroll_column(self, content)

        def _apply_local_style(self) -> None:
            from .result_preview_layout import apply_local_style

            apply_local_style(self)


else:

    class GCodeSyntaxHighlighter:  # pragma: no cover - PyQt-free compatibility stub.
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("PyQt5 is required to create the result preview UI")

    class ResultPreviewPage:  # pragma: no cover - PyQt-free compatibility stub.
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("PyQt5 is required to create the result preview UI")


__all__ = [
    "CONTEXT_RADIUS",
    "GCodeSyntaxHighlighter",
    "PreparedLoadCommit",
    "QT_AVAILABLE",
    "ResultCommitError",
    "ResultPreviewPage",
]
