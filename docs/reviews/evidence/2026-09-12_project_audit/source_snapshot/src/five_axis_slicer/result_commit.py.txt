"""Atomic presentation transaction for ``ResultPreviewPage`` load results."""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from dataclasses import fields
from typing import TYPE_CHECKING, Any, NoReturn

from PyQt5.QtCore import QSignalBlocker, QTimer

if TYPE_CHECKING:
    from .result_preview import PreparedLoadCommit
    from .result_state import LoadResult

LOGGER = logging.getLogger(__name__)


def prepare_load_commit(page: Any, result: LoadResult) -> PreparedLoadCommit | None:
    if page.state.status != "loading" or result.request_id != page.state.current_request_id:
        return None
    _validate_result(page, result)
    from .result_preview import PreparedLoadCommit

    replacing_gcode = result.gcode_preview is not None
    preview = result.gcode_preview if replacing_gcode else page._preview
    source_index = result.gcode_source_index if replacing_gcode else page._source_index
    owns_source_index = source_index is not None if replacing_gcode else page._owns_source_index
    stage_entries = page._stage_entries_for(preview, source_index)
    source_audits = deepcopy(page._source_audits)
    source_audits.update({str(role): dict(audit) for role, audit in result.source_audits.items()})
    state_snapshot = _state_snapshot(page)
    return PreparedLoadCommit(
        result=result,
        previous_model=page._model,
        previous_preview=page._preview,
        previous_source_index=page._source_index,
        previous_owns_source_index=page._owns_source_index,
        previous_source_audits=deepcopy(page._source_audits),
        previous_state=state_snapshot,
        previous_stage_entries=deepcopy(page._stage_entries),
        previous_stage_progress_start=page._stage_progress_start,
        previous_stage_progress_end=page._stage_progress_end,
        previous_stage_uses_layer_filter=page._stage_uses_layer_filter,
        previous_progress_minimum=page.progress_slider.minimum(),
        previous_progress_maximum=page.progress_slider.maximum(),
        previous_progress_value=page.progress_slider.value(),
        previous_current_line=page._current_line,
        previous_context_lines=list(page._context_lines),
        model=result.model if result.model is not None else page._model,
        preview=preview,
        source_index=source_index,
        owns_source_index=owns_source_index,
        source_audits=source_audits,
        stage_entries=stage_entries,
        quality_mode=page.state.quality_mode,
    )


def _validate_result(page: Any, result: LoadResult) -> None:
    if result.model_path is not None and result.model is None:
        raise ValueError("The load result has a model path without model data")
    if result.gcode_path is not None and result.gcode_preview is None:
        raise ValueError("The load result has a G-code path without preview data")
    if result.gcode_source_index is not None and result.gcode_preview is None:
        raise ValueError("A source index requires matching G-code preview data")
    if page.state.quality_mode not in {"interactive", "paper"}:
        raise ValueError(f"Unsupported quality mode: {page.state.quality_mode}")


def _state_snapshot(page: Any) -> dict[str, Any]:
    return {field.name: deepcopy(getattr(page.state, field.name)) for field in fields(page.state)}


def apply_load_commit(page: Any, prepared: PreparedLoadCommit) -> bool:
    result = prepared.result
    if page.state.status != "loading" or result.request_id != page.state.current_request_id:
        page._discard_load_result(result)
        return False
    conflict = _prepared_state_conflict(page, prepared)
    if conflict is not None:
        cleanup_errors = page._discard_load_result(result)
        _raise_commit_error(result.request_id, conflict, cleanup_errors)

    previous_signal_state = page.blockSignals(True)
    attempted_viewer_steps: set[str] = set()
    try:
        page._stop_playback()
        _apply_viewer_result(page, prepared, attempted_viewer_steps)
        _publish_page_result(page, prepared)
        _refresh_committed_page(page, prepared)
    except Exception as exc:
        rollback_errors = rollback_load_commit(page, prepared, frozenset(attempted_viewer_steps))
        rollback_errors += page._discard_load_result(result)
        _raise_commit_error(result.request_id, exc, rollback_errors)
    finally:
        page.blockSignals(previous_signal_state)

    _transfer_source_index_ownership(page, prepared)
    _finish_commit_presentation(page)
    return True


def _prepared_state_conflict(page: Any, prepared: PreparedLoadCommit) -> RuntimeError | None:
    if (
        page._model is not prepared.previous_model
        or page._preview is not prepared.previous_preview
        or page._source_index is not prepared.previous_source_index
    ):
        return RuntimeError("The committed page changed after result preparation")
    if any(getattr(page.state, name) != value for name, value in prepared.previous_state.items()):
        return RuntimeError("The result state changed after result preparation")
    return None


def _raise_commit_error(
    request_id: object,
    cause: BaseException,
    rollback_errors: tuple[str, ...],
) -> NoReturn:
    from .result_preview import ResultCommitError

    raise ResultCommitError(request_id, cause, rollback_errors) from cause


def _apply_viewer_result(
    page: Any,
    prepared: PreparedLoadCommit,
    attempted: set[str],
) -> None:
    result = prepared.result
    if hasattr(page.viewer, "set_quality_mode"):
        attempted.add("quality")
        page.viewer.set_quality_mode(prepared.quality_mode)
    if result.gcode_preview is not None and hasattr(page.viewer, "load_gcode_preview"):
        attempted.add("gcode")
        page.viewer.load_gcode_preview(prepared.preview)
    if result.model is not None and hasattr(page.viewer, "load_model"):
        attempted.add("model")
        page.viewer.load_model(prepared.model)


def _publish_page_result(page: Any, prepared: PreparedLoadCommit) -> None:
    page._model = prepared.model
    page._preview = prepared.preview
    page._source_index = prepared.source_index
    page._owns_source_index = prepared.owns_source_index
    page._source_audits = deepcopy(prepared.source_audits)
    page._stage_entries = deepcopy(prepared.stage_entries)
    if prepared.source_index is not prepared.previous_source_index:
        page._search_token += 1
        page._current_line = 1
        page._context_lines = []
    if not page.state.commit_load(prepared.result):
        raise RuntimeError("The load state changed during result application")


def _refresh_committed_page(page: Any, prepared: PreparedLoadCommit) -> None:
    page._set_post_commit_status()
    with QSignalBlocker(page.quality_combo):
        page.quality_combo.setCurrentIndex(0 if prepared.quality_mode == "interactive" else 1)
    page._rebuild_stage_combo(preserve_id=page.state.selected_stage)
    page._update_sources()
    page._update_status()
    page._update_statistics()
    page._update_context()
    page._apply_visibility()
    page.cancel_button.setEnabled(False)
    if hasattr(page.viewer, "set_standard_view"):
        page.viewer.set_standard_view("isometric")
    elif hasattr(page.viewer, "home_view"):
        page.viewer.home_view()


def _transfer_source_index_ownership(page: Any, prepared: PreparedLoadCommit) -> None:
    # Ownership transfers only after every fallible Viewer and page refresh has
    # completed. The worker result can then be closed without touching the index.
    prepared.result.gcode_source_index = None
    old_index = prepared.previous_source_index
    if (
        old_index is None
        or old_index is prepared.source_index
        or not prepared.previous_owns_source_index
    ):
        return
    try:
        old_index.close()
    except Exception:
        LOGGER.warning("Failed to close the retired G-code source index", exc_info=True)


def _finish_commit_presentation(page: Any) -> None:
    try:
        page._queue_representative_line()
    except Exception:
        LOGGER.warning("Failed to schedule representative G-code lookup", exc_info=True)
    # Framebuffer capture stays on the GUI event loop after the committed layout
    # and Viewer state have processed their queued paint work.
    QTimer.singleShot(0, page.capture_thumbnail)
    page._emit_display_state()


def rollback_load_commit(
    page: Any,
    prepared: PreparedLoadCommit,
    attempted_viewer_steps: frozenset[str],
) -> tuple[str, ...]:
    errors = _restore_viewer(page, prepared, attempted_viewer_steps)
    _restore_page_snapshot(page, prepared)
    _capture_error(errors, "page controls", page._apply_state_to_controls)
    _capture_error(
        errors,
        "page stages",
        lambda: page._rebuild_stage_combo(page.state.selected_stage),
    )
    # Stage activation may alter serializable progress. Reapply the transaction
    # snapshot before restoring the exact slider and Viewer position.
    _apply_state_snapshot(page, prepared.previous_state)
    _restore_progress(page, prepared, errors)
    for name, operation in (
        ("page sources", page._update_sources),
        ("page status", page._update_status),
        ("page statistics", page._update_statistics),
        ("page context", page._update_context),
        ("page visibility", page._apply_visibility),
    ):
        _capture_error(errors, name, operation)
    return tuple(errors)


def _restore_viewer(
    page: Any,
    prepared: PreparedLoadCommit,
    attempted: frozenset[str],
) -> list[str]:
    errors: list[str] = []
    if "quality" in attempted:
        _capture_error(
            errors,
            "viewer quality",
            lambda: _restore_viewer_quality(page, prepared),
        )
    if attempted.intersection({"gcode", "model"}):
        _capture_error(
            errors,
            "viewer gcode",
            lambda: _restore_viewer_gcode(page, prepared),
        )
    if "model" in attempted:
        _capture_error(
            errors,
            "viewer model",
            lambda: _restore_viewer_model(page, prepared),
        )
    return errors


def _restore_viewer_quality(page: Any, prepared: PreparedLoadCommit) -> None:
    if hasattr(page.viewer, "set_quality_mode"):
        page.viewer.set_quality_mode(str(prepared.previous_state["quality_mode"]))


def _restore_viewer_gcode(page: Any, prepared: PreparedLoadCommit) -> None:
    if prepared.previous_preview is not None and hasattr(page.viewer, "load_gcode_preview"):
        page.viewer.load_gcode_preview(prepared.previous_preview)
    elif prepared.previous_preview is None and hasattr(page.viewer, "clear_gcode_preview"):
        page.viewer.clear_gcode_preview()


def _restore_viewer_model(page: Any, prepared: PreparedLoadCommit) -> None:
    if prepared.previous_model is not None and hasattr(page.viewer, "load_model"):
        page.viewer.load_model(prepared.previous_model)
    elif prepared.previous_model is None and hasattr(page.viewer, "clear_model"):
        page.viewer.clear_model()
    elif prepared.previous_model is None and hasattr(page.viewer, "model"):
        page.viewer.model = None
        raise RuntimeError("viewer lacks clear_model; empty-scene visual rollback is unverified")


def _restore_page_snapshot(page: Any, prepared: PreparedLoadCommit) -> None:
    page._model = prepared.previous_model
    page._preview = prepared.previous_preview
    page._source_index = prepared.previous_source_index
    page._owns_source_index = prepared.previous_owns_source_index
    page._source_audits = deepcopy(prepared.previous_source_audits)
    page._stage_entries = deepcopy(prepared.previous_stage_entries)
    page._current_line = prepared.previous_current_line
    page._context_lines = list(prepared.previous_context_lines)
    _apply_state_snapshot(page, prepared.previous_state)


def _apply_state_snapshot(page: Any, snapshot: dict[str, Any]) -> None:
    for name, value in snapshot.items():
        setattr(page.state, name, deepcopy(value))


def _restore_progress(
    page: Any,
    prepared: PreparedLoadCommit,
    errors: list[str],
) -> None:
    page._stage_progress_start = prepared.previous_stage_progress_start
    page._stage_progress_end = prepared.previous_stage_progress_end
    page._stage_uses_layer_filter = prepared.previous_stage_uses_layer_filter
    with QSignalBlocker(page.progress_slider):
        page.progress_slider.setRange(
            prepared.previous_progress_minimum,
            prepared.previous_progress_maximum,
        )
        page.progress_slider.setValue(prepared.previous_progress_value)
    page.progress_value.setText(f"{page.state.playback_progress * 100:.1f}%")
    if prepared.previous_preview is not None:
        _capture_error(
            errors,
            "viewer progress",
            lambda: page._set_viewer_progress(
                prepared.previous_stage_progress_start + prepared.previous_progress_value,
                interactive=False,
            ),
        )
    page._current_line = prepared.previous_current_line
    page._context_lines = list(prepared.previous_context_lines)


def _capture_error(
    errors: list[str],
    name: str,
    operation: Callable[[], None],
) -> None:
    try:
        operation()
    except Exception as exc:
        errors.append(f"{name}: {exc}")
