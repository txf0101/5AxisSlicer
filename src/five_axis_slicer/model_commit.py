"""Atomic publication boundaries for model and project state."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .gcode_preview import GCodePreview, PreviewSettings
from .models import CadModel, PickHit, PickRequest, SelectionState
from .tube_controller import StaleDraftError, TubeSetupController
from .viewer_common import ViewerProtocol


class TubePageProtocol(Protocol):
    controller: TubeSetupController
    viewer: ViewerProtocol
    model: CadModel | None
    _view_mode: str
    _coordinate_node: str
    _pick_context: tuple[str, str, str] | None
    _two_point_hits: list[PickHit]
    _coordinate_control_dirty: set[str]

    def set_controller(self, controller: TubeSetupController, model: CadModel | None) -> None: ...

    def set_view_mode(self, mode: str) -> None: ...


class CommandCheckpointController(Protocol):
    def command_applied_token(self) -> tuple[object, ...]: ...

    def command_checkpoint(self) -> Any: ...

    def restore_command_checkpoint(self, checkpoint: Any) -> None: ...


class WorkbenchPageProtocol(Protocol):
    controller: CommandCheckpointController
    viewer: ViewerProtocol

    def set_controller(self, controller: Any) -> None: ...


class IndexWidgetProtocol(Protocol):
    def currentIndex(self) -> int: ...

    def setCurrentIndex(self, index: int) -> None: ...


class TimerProtocol(Protocol):
    def isActive(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


class TextWidgetProtocol(Protocol):
    def text(self) -> str: ...

    def setText(self, text: str) -> None: ...

    def toolTip(self) -> str: ...

    def setToolTip(self, text: str) -> None: ...


class StatusBarProtocol(Protocol):
    def currentMessage(self) -> str: ...

    def showMessage(self, message: str) -> None: ...


class ModelHostProtocol(Protocol):
    _model_publication_depth: int
    model: CadModel | None
    _original_step_path: Path | None
    gcode_preview: GCodePreview | None
    current_workbench_key: str
    current_operation: str
    last_project_dir: Path | None
    viewer: ViewerProtocol
    tube_page: TubePageProtocol
    planar_page: WorkbenchPageProtocol
    curve_page: WorkbenchPageProtocol
    freeform_page: WorkbenchPageProtocol
    rotary_page: WorkbenchPageProtocol
    stack: IndexWidgetProtocol
    preview_tabs: IndexWidgetProtocol
    progress_timer: TimerProtocol
    progress_play_button: TextWidgetProtocol

    def statusBar(self) -> StatusBarProtocol: ...

    def refresh_lists(self) -> None: ...

    def _update_operation_combo(self) -> None: ...

    def _update_file_labels(self) -> None: ...

    def _update_workbench_texts(self) -> None: ...

    def _sync_preview_controls(self) -> None: ...

    def _update_checks(self) -> None: ...


@dataclass(frozen=True, slots=True)
class _ViewerSnapshot:
    model: CadModel | None
    gcode_preview: GCodePreview | None
    preview_settings: PreviewSettings
    selection: SelectionState
    pick_request: PickRequest | None


@dataclass(frozen=True, slots=True)
class _TubePageSnapshot:
    """UI-only editor state cleared by ``TubeSetupPage.set_controller``."""

    view_mode: str
    coordinate_node: str
    pick_context: tuple[str, str, str] | None
    two_point_hits: tuple[PickHit, ...]
    dirty_controls: frozenset[str]


@dataclass(frozen=True, slots=True)
class _PublicationSnapshot:
    """Committed state needed to undo one main-thread publication."""

    model: CadModel | None
    original_step_path: Path | None
    gcode_preview: GCodePreview | None
    controller: TubeSetupController
    model_viewer: _ViewerSnapshot
    tube_viewer: _ViewerSnapshot
    tube_page: _TubePageSnapshot
    planar_controller: CommandCheckpointController
    planar_checkpoint: object
    planar_viewer: _ViewerSnapshot
    curve_controller: CommandCheckpointController
    curve_checkpoint: object
    curve_viewer: _ViewerSnapshot
    freeform_controller: CommandCheckpointController | None
    freeform_checkpoint: object | None
    freeform_viewer: _ViewerSnapshot | None
    rotary_controller: CommandCheckpointController
    rotary_checkpoint: object
    rotary_viewer: _ViewerSnapshot
    workbench_key: str
    operation: str
    project_directory: Path | None
    stack_index: int
    preview_tab_index: int
    progress_active: bool
    progress_button_text: str
    progress_button_tooltip: str
    status_message: str


@dataclass(frozen=True, slots=True)
class SourceUpdateBaseline:
    """Controller identity captured before asynchronous STEP parsing starts."""

    controller: TubeSetupController
    edit_token: tuple[object, ...]
    planar_controller: CommandCheckpointController | None = None
    planar_token: tuple[object, ...] | None = None
    curve_controller: CommandCheckpointController | None = None
    curve_token: tuple[object, ...] | None = None
    freeform_controller: CommandCheckpointController | None = None
    freeform_token: tuple[object, ...] | None = None
    rotary_controller: CommandCheckpointController | None = None
    rotary_token: tuple[object, ...] | None = None

    @classmethod
    def capture(
        cls,
        controller: TubeSetupController,
        planar_controller: CommandCheckpointController | None = None,
        curve_controller: CommandCheckpointController | None = None,
        rotary_controller: CommandCheckpointController | None = None,
        freeform_controller: CommandCheckpointController | None = None,
    ) -> SourceUpdateBaseline:
        return cls(
            controller=controller,
            edit_token=controller.edit_state_token(),
            planar_controller=planar_controller,
            planar_token=None
            if planar_controller is None
            else planar_controller.command_applied_token(),
            curve_controller=curve_controller,
            curve_token=None
            if curve_controller is None
            else curve_controller.command_applied_token(),
            freeform_controller=freeform_controller,
            freeform_token=None
            if freeform_controller is None
            else freeform_controller.command_applied_token(),
            rotary_controller=rotary_controller,
            rotary_token=None
            if rotary_controller is None
            else rotary_controller.command_applied_token(),
        )

    def require_current(
        self,
        current: TubeSetupController,
        planar_current: CommandCheckpointController | None = None,
        curve_current: CommandCheckpointController | None = None,
        rotary_current: CommandCheckpointController | None = None,
        freeform_current: CommandCheckpointController | None = None,
    ) -> TubeSetupController:
        if current is not self.controller or current.edit_state_token() != self.edit_token:
            raise StaleDraftError("Manufacturing Setup changed during STEP loading")
        if self.planar_controller is not None and (
            planar_current is not self.planar_controller
            or planar_current.command_applied_token() != self.planar_token
        ):
            raise StaleDraftError("Planar inputs changed during STEP loading")
        if self.curve_controller is not None and (
            curve_current is not self.curve_controller
            or curve_current.command_applied_token() != self.curve_token
        ):
            raise StaleDraftError("Curve inputs changed during STEP loading")
        if self.freeform_controller is not None and (
            freeform_current is not self.freeform_controller
            or freeform_current.command_applied_token() != self.freeform_token
        ):
            raise StaleDraftError("Freeform inputs changed during STEP loading")
        if self.rotary_controller is not None and (
            rotary_current is not self.rotary_controller
            or rotary_current.command_applied_token() != self.rotary_token
        ):
            raise StaleDraftError("Rotary inputs changed during STEP loading")
        return current


@contextmanager
def publication_transaction(host: ModelHostProtocol) -> Iterator[None]:
    """Restore the last committed UI state when publication raises."""

    depth = int(getattr(host, "_model_publication_depth", 0))
    if depth:
        host._model_publication_depth = depth + 1
        try:
            yield
        finally:
            host._model_publication_depth = depth
        return
    snapshot = _capture(host)
    host._model_publication_depth = 1
    try:
        yield
    except Exception as commit_error:
        try:
            _restore(host, snapshot)
        except Exception as rollback_error:
            raise RuntimeError(
                f"state publication failed ({commit_error}); "
                f"visible-state rollback also failed ({rollback_error})"
            ) from commit_error
        raise
    finally:
        del host._model_publication_depth


@contextmanager
def source_update_transaction(
    host: ModelHostProtocol,
    controller: TubeSetupController,
    draft_resolution: str | None,
) -> Iterator[None]:
    """Roll back Controller edits before restoring their visible projection."""

    with publication_transaction(host):
        with controller.draft_resolution_transaction(draft_resolution):
            yield


def refresh_publication_ui(host: ModelHostProtocol) -> None:
    """Rebuild controls derived from the currently committed state."""

    host.refresh_lists()
    host._update_operation_combo()
    host._update_file_labels()
    host._update_workbench_texts()
    host._sync_preview_controls()
    host._update_checks()


def _capture(host: ModelHostProtocol) -> _PublicationSnapshot:
    button = host.progress_play_button
    freeform_page = getattr(host, "freeform_page", None)
    return _PublicationSnapshot(
        model=host.model,
        original_step_path=host._original_step_path,
        gcode_preview=host.gcode_preview,
        controller=host.tube_page.controller,
        model_viewer=_capture_viewer(host.viewer),
        tube_viewer=_capture_viewer(host.tube_page.viewer),
        tube_page=_capture_tube_page(host.tube_page),
        planar_controller=host.planar_page.controller,
        planar_checkpoint=host.planar_page.controller.command_checkpoint(),
        planar_viewer=_capture_viewer(host.planar_page.viewer),
        curve_controller=host.curve_page.controller,
        curve_checkpoint=host.curve_page.controller.command_checkpoint(),
        curve_viewer=_capture_viewer(host.curve_page.viewer),
        freeform_controller=None if freeform_page is None else freeform_page.controller,
        freeform_checkpoint=None
        if freeform_page is None
        else freeform_page.controller.command_checkpoint(),
        freeform_viewer=None if freeform_page is None else _capture_viewer(freeform_page.viewer),
        rotary_controller=host.rotary_page.controller,
        rotary_checkpoint=host.rotary_page.controller.command_checkpoint(),
        rotary_viewer=_capture_viewer(host.rotary_page.viewer),
        workbench_key=host.current_workbench_key,
        operation=host.current_operation,
        project_directory=host.last_project_dir,
        stack_index=host.stack.currentIndex(),
        preview_tab_index=host.preview_tabs.currentIndex(),
        progress_active=host.progress_timer.isActive(),
        progress_button_text=button.text(),
        progress_button_tooltip=button.toolTip(),
        status_message=host.statusBar().currentMessage(),
    )


def _restore(host: ModelHostProtocol, snapshot: _PublicationSnapshot) -> None:
    host.progress_timer.stop()
    reset_tube_page = (
        host.tube_page.controller is not snapshot.controller
        or host.tube_page.model is not snapshot.model
    )
    host.model = snapshot.model
    host._original_step_path = snapshot.original_step_path
    host.gcode_preview = snapshot.gcode_preview
    host.current_workbench_key = snapshot.workbench_key
    host.current_operation = snapshot.operation
    host.last_project_dir = snapshot.project_directory
    _restore_viewer(host.viewer, snapshot.model_viewer)
    if reset_tube_page:
        host.tube_page.set_controller(snapshot.controller, snapshot.model)
    _restore_viewer_projection(host.tube_page.viewer, snapshot.tube_viewer)
    _restore_tube_page(host.tube_page, snapshot.tube_page)
    snapshot.planar_controller.restore_command_checkpoint(snapshot.planar_checkpoint)
    host.planar_page.set_controller(snapshot.planar_controller)
    _restore_viewer_projection(host.planar_page.viewer, snapshot.planar_viewer)
    snapshot.curve_controller.restore_command_checkpoint(snapshot.curve_checkpoint)
    host.curve_page.set_controller(snapshot.curve_controller)
    _restore_viewer_projection(host.curve_page.viewer, snapshot.curve_viewer)
    if snapshot.freeform_controller is not None and snapshot.freeform_viewer is not None:
        snapshot.freeform_controller.restore_command_checkpoint(snapshot.freeform_checkpoint)
        host.freeform_page.set_controller(snapshot.freeform_controller)
        _restore_viewer_projection(host.freeform_page.viewer, snapshot.freeform_viewer)
    snapshot.rotary_controller.restore_command_checkpoint(snapshot.rotary_checkpoint)
    host.rotary_page.set_controller(snapshot.rotary_controller)
    _restore_viewer_projection(host.rotary_page.viewer, snapshot.rotary_viewer)
    refresh_publication_ui(host)
    host.stack.setCurrentIndex(snapshot.stack_index)
    host.preview_tabs.setCurrentIndex(snapshot.preview_tab_index)
    if snapshot.progress_active:
        host.progress_timer.start()
    else:
        host.progress_timer.stop()
    host.progress_play_button.setText(snapshot.progress_button_text)
    host.progress_play_button.setToolTip(snapshot.progress_button_tooltip)
    host.statusBar().showMessage(snapshot.status_message)


def _capture_viewer(viewer: ViewerProtocol) -> _ViewerSnapshot:
    return _ViewerSnapshot(
        model=viewer.model,
        gcode_preview=viewer.gcode_preview,
        preview_settings=deepcopy(viewer.preview_settings),
        selection=SelectionState.from_json(viewer.selection.to_json()),
        pick_request=viewer.pick_request,
    )


def _capture_tube_page(page: TubePageProtocol) -> _TubePageSnapshot:
    return _TubePageSnapshot(
        view_mode=page._view_mode,
        coordinate_node=page._coordinate_node,
        pick_context=page._pick_context,
        two_point_hits=tuple(page._two_point_hits),
        dirty_controls=frozenset(page._coordinate_control_dirty),
    )


def _restore_tube_page(page: TubePageProtocol, snapshot: _TubePageSnapshot) -> None:
    page._coordinate_node = snapshot.coordinate_node
    page._pick_context = snapshot.pick_context
    page._two_point_hits[:] = snapshot.two_point_hits
    page._coordinate_control_dirty = set(snapshot.dirty_controls)
    page.set_view_mode(snapshot.view_mode)


def _restore_viewer(viewer: ViewerProtocol, snapshot: _ViewerSnapshot) -> None:
    if snapshot.model is None:
        viewer.clear_model()
    else:
        viewer.load_model(snapshot.model)
    _restore_viewer_projection(viewer, snapshot)


def _restore_viewer_projection(viewer: ViewerProtocol, snapshot: _ViewerSnapshot) -> None:
    if snapshot.gcode_preview is None:
        viewer.clear_gcode_preview()
    else:
        viewer.load_gcode_preview(snapshot.gcode_preview)
    viewer.preview_settings = deepcopy(snapshot.preview_settings)
    refresh_path = getattr(viewer, "refresh_path_preview", None)
    if callable(refresh_path):
        refresh_path()
    if snapshot.pick_request is not None:
        viewer.set_pick_request(snapshot.pick_request)
    viewer.selection.mode = snapshot.selection.mode
    viewer.set_selection(
        body_ids=sorted(snapshot.selection.body_ids),
        edge_ids=sorted(snapshot.selection.edge_ids),
        face_ids=sorted(snapshot.selection.face_ids),
        vertex_ids=sorted(snapshot.selection.vertex_ids),
    )


__all__ = [
    "SourceUpdateBaseline",
    "publication_transaction",
    "refresh_publication_ui",
    "source_update_transaction",
]
