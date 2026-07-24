from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import threading
import time

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from .gcode_preview import GCodeLoadCancelled, load_gcode
from .gcode_source import GCodeSourceIndex, GCodeSourceIndexCancelled
from .project_io import ProjectLoadCancelled, load_project
from .result_state import LoadRequest, LoadResult
from .step_loader import StepLoadCancelled, file_sha256, load_step


class LoadCancelled(RuntimeError):
    pass


# A worker may be inside a third-party STEP parser that cannot observe the
# cancellation event.  Keep both Python wrappers alive independently of the
# coordinator in that case.  This prevents QObject teardown from destroying a
# running QThread when an application elects to close after a bounded wait.
_LIVE_WORKERS_LOCK = threading.Lock()
_LIVE_WORKERS: dict[QThread, "_ResultLoadWorker"] = {}


def _retain_worker(thread: QThread, worker: "_ResultLoadWorker") -> None:
    with _LIVE_WORKERS_LOCK:
        _LIVE_WORKERS[thread] = worker


def _release_worker(thread: QThread) -> None:
    with _LIVE_WORKERS_LOCK:
        _LIVE_WORKERS.pop(thread, None)


def _source_audit(
    path: Path,
    sha256: object = None,
    *,
    size_bytes: int | None = None,
    mtime_ns: int | None = None,
) -> dict[str, object]:
    """Capture file identity at the point a worker accepts loaded data."""

    resolved_size = size_bytes
    resolved_mtime = mtime_ns
    if resolved_size is None or resolved_mtime is None:
        stat = path.stat()
        if resolved_size is None:
            resolved_size = int(stat.st_size)
        if resolved_mtime is None:
            resolved_mtime = int(stat.st_mtime_ns)
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": int(resolved_size),
        "mtime_ns": int(resolved_mtime),
        "sha256": None if sha256 is None else str(sha256),
    }


class _ResultLoadWorker(QObject):
    progress = pyqtSignal(object, str, float)
    completed = pyqtSignal(object)
    failed = pyqtSignal(object, str)
    cancelled = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, request: LoadRequest, cancel_event: threading.Event) -> None:
        super().__init__()
        self.request = request
        self.cancel_event = cancel_event

    @pyqtSlot()
    def run(self) -> None:
        started = time.perf_counter()
        source_index: GCodeSourceIndex | None = None
        try:
            self._check_cancelled()
            model = None
            preview = None
            project = None
            source_audits: dict[str, dict[str, object]] = {}
            if self.request.project_path is not None:
                self.progress.emit(self.request.request_id, "project", 0.01)

                def report_project(phase: str, fraction: float) -> None:
                    self._check_cancelled()
                    self.progress.emit(self.request.request_id, phase, fraction)

                project = load_project(
                    self.request.project_path,
                    length_unit_override=self.request.length_unit_override,
                    cancel_check=self.cancel_event.is_set,
                    progress_callback=report_project,
                )
                self._check_cancelled()
                model = project.model
                if model is not None:
                    source_audits["project_step_model"] = _source_audit(
                        Path(model.source_path),
                        getattr(model, "source_hash", None),
                        size_bytes=getattr(model, "source_size_bytes", None),
                        mtime_ns=getattr(model, "source_mtime_ns", None),
                    )

            if self.request.model_path is not None:
                self.progress.emit(self.request.request_id, "model", 0.05)
                step_options: dict[str, object] = {
                    "cancel_check": self.cancel_event.is_set,
                }
                if self.request.length_unit_override is not None:
                    step_options["length_unit_override"] = (
                        self.request.length_unit_override
                    )
                model = load_step(self.request.model_path, **step_options)
                self._check_cancelled()
                source_audits["step_model"] = _source_audit(
                    self.request.model_path,
                    getattr(model, "source_hash", None),
                    size_bytes=getattr(model, "source_size_bytes", None),
                    mtime_ns=getattr(model, "source_mtime_ns", None),
                )
                self.progress.emit(self.request.request_id, "model", 0.22)

            if self.request.gcode_path is not None:
                gcode_load_hash = file_sha256(
                    self.request.gcode_path,
                    cancel_check=self.cancel_event.is_set,
                )

                def report(fraction: float, phase: str = "gcode") -> None:
                    self._check_cancelled()
                    mapped = 0.22 + max(0.0, min(1.0, float(fraction))) * 0.63
                    self.progress.emit(self.request.request_id, phase, mapped)

                preview = load_gcode(
                    self.request.gcode_path,
                    progress_callback=report,
                    cancel_check=self.cancel_event.is_set,
                    source_sha256=gcode_load_hash,
                )
                source_fingerprint = getattr(preview, "source_fingerprint", None)
                if source_fingerprint is None:
                    gcode_load_audit = _source_audit(
                        self.request.gcode_path,
                        gcode_load_hash,
                    )
                else:
                    gcode_load_audit = _source_audit(
                        self.request.gcode_path,
                        source_fingerprint.sha256,
                        size_bytes=source_fingerprint.size_bytes,
                        mtime_ns=source_fingerprint.mtime_ns,
                    )
                self._check_cancelled()
                self.progress.emit(self.request.request_id, "source_index", 0.88)

                def report_index(fraction: float, phase: str = "source_index") -> None:
                    self._check_cancelled()
                    mapped = 0.88 + max(0.0, min(1.0, float(fraction))) * 0.10
                    self.progress.emit(self.request.request_id, phase, mapped)

                source_index = GCodeSourceIndex(
                    self.request.gcode_path,
                    progress_callback=report_index,
                    cancel_check=self.cancel_event.is_set,
                )
                signature = getattr(source_index, "source_signature", None)
                indexed_audit = (
                    dict(signature)
                    if isinstance(signature, Mapping)
                    else _source_audit(
                        self.request.gcode_path,
                        file_sha256(
                            self.request.gcode_path,
                            cancel_check=self.cancel_event.is_set,
                        ),
                    )
                )
                if any(
                    indexed_audit.get(field) != gcode_load_audit.get(field)
                    for field in ("path", "size_bytes", "mtime_ns", "sha256")
                ):
                    raise RuntimeError(
                        f"G-code source changed while loading: {self.request.gcode_path}"
                    )
                source_audits["gcode"] = gcode_load_audit

            self._check_cancelled()
            effective_unit_override = self.request.length_unit_override
            loaded_units = None if model is None else getattr(model, "units", None)
            if loaded_units is not None and bool(
                getattr(loaded_units, "override_applied", False)
            ):
                effective_unit_override = str(loaded_units.source_length_unit)
            result = LoadResult(
                request_id=self.request.request_id,
                model_path=self.request.model_path,
                gcode_path=self.request.gcode_path,
                project_path=self.request.project_path,
                length_unit_override=effective_unit_override,
                model=model,
                project=project,
                gcode_preview=preview,
                gcode_source_index=source_index,
                source_audits=source_audits,
                elapsed_seconds=time.perf_counter() - started,
            )
            source_index = None
            self.progress.emit(self.request.request_id, "commit", 1.0)
            self.completed.emit(result)
        except (
            LoadCancelled,
            ProjectLoadCancelled,
            StepLoadCancelled,
            GCodeLoadCancelled,
            GCodeSourceIndexCancelled,
        ):
            self.cancelled.emit(self.request.request_id)
        except Exception as exc:  # UI turns this into a localized message.
            self.failed.emit(self.request.request_id, str(exc))
        finally:
            if source_index is not None:
                source_index.close()
            self.finished.emit()

    def _check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise LoadCancelled("Loading cancelled")


class ResultLoadCoordinator(QObject):
    """Own one worker thread and discard results from superseded requests."""

    progress = pyqtSignal(object, str, float)
    completed = pyqtSignal(object)
    failed = pyqtSignal(object, str)
    cancelled = pyqtSignal(object)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _ResultLoadWorker | None = None
        self._cancel_event: threading.Event | None = None
        self._active_request_id: object | None = None
        self._pending_request: LoadRequest | None = None

    @property
    def busy(self) -> bool:
        # Keep the coordinator busy until the thread-finished event has been
        # consumed on this QObject's thread. This prevents a second launch from
        # replacing references while an earlier finished signal is still queued.
        return self._thread is not None

    @property
    def active_request_id(self) -> object | None:
        return self._active_request_id

    def start(self, request: LoadRequest) -> None:
        if self.busy:
            self._pending_request = request
            # Signals already queued by the superseded worker are stale as soon
            # as the newer request is accepted.
            self._active_request_id = request.request_id
            self._request_worker_cancel()
            return
        self._launch(request)

    def cancel(self) -> None:
        request_id = self._active_request_id
        if request_id is None:
            return
        self._pending_request = None
        self._active_request_id = None
        self._request_worker_cancel()
        # The state transition is deterministic even when a worker has already
        # queued a completion just before cancellation. Later worker signals are
        # discarded because there is no active request id.
        self.cancelled.emit(request_id)

    def _request_worker_cancel(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        """Request cancellation and report whether the worker has stopped.

        STEP parsing is currently a non-cooperative dependency.  A ``False``
        result therefore means the owner must keep the application open and
        call :meth:`wait_for_shutdown` again.  The coordinator remains busy and
        retains its active thread until a subsequent wait or the normal
        ``finished`` delivery completes the lifecycle.
        """

        self._pending_request = None
        self._active_request_id = None
        self._request_worker_cancel()
        return self.wait_for_shutdown(timeout_ms)

    def wait_for_shutdown(self, timeout_ms: int = 5000) -> bool:
        """Wait for a prior shutdown request; safe to call repeatedly."""

        thread = self._thread
        if thread is None:
            return True
        if QThread.currentThread() is thread:
            return False
        if thread.isRunning():
            # quit() is thread-safe and records the request even while run() is
            # occupied by a blocking parser.  The event loop exits as soon as
            # that parser returns.
            thread.quit()
            if not thread.wait(max(0, int(timeout_ms))):
                return False
        self._finalize_thread(thread)
        return True

    def _launch(self, request: LoadRequest, *, emit_busy: bool = True) -> None:
        self._active_request_id = request.request_id
        self._cancel_event = threading.Event()
        # Do not parent a potentially non-cooperative QThread to the
        # coordinator.  _LIVE_WORKERS provides the destruction guard until the
        # native thread has actually stopped.
        thread = QThread()
        worker = _ResultLoadWorker(request, self._cancel_event)
        _retain_worker(thread, worker)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._forward_progress)
        worker.completed.connect(self._forward_completed)
        worker.failed.connect(self._forward_failed)
        worker.cancelled.connect(self._forward_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(lambda thread=thread: _release_worker(thread))
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        if emit_busy:
            self.busy_changed.emit(True)
        thread.start()

    @pyqtSlot(object, str, float)
    def _forward_progress(
        self, request_id: object, phase: str, fraction: float
    ) -> None:
        if request_id == self._active_request_id:
            self.progress.emit(request_id, phase, fraction)

    @pyqtSlot(object)
    def _forward_completed(self, result: LoadResult) -> None:
        if result.request_id == self._active_request_id:
            self.completed.emit(result)
        else:
            result.close()

    @pyqtSlot(object, str)
    def _forward_failed(self, request_id: object, message: str) -> None:
        if request_id == self._active_request_id:
            self.failed.emit(request_id, message)

    @pyqtSlot(object)
    def _forward_cancelled(self, request_id: object) -> None:
        if request_id == self._active_request_id:
            self.cancelled.emit(request_id)

    @pyqtSlot()
    def _thread_finished(self) -> None:
        sender = self.sender()
        thread = sender if isinstance(sender, QThread) else self._thread
        if thread is not None:
            self._finalize_thread(thread)

    def _finalize_thread(self, thread: QThread) -> None:
        """Finalize exactly one stopped thread on the coordinator thread."""

        if thread is not self._thread or thread.isRunning():
            return
        self._thread = None
        self._worker = None
        self._cancel_event = None
        _release_worker(thread)
        pending = self._pending_request
        self._pending_request = None
        if pending is not None:
            # A replacement is one continuous busy interval from the UI's
            # perspective, so avoid a transient False/True signal pair.
            self._launch(pending, emit_busy=False)
        else:
            self._active_request_id = None
            self.busy_changed.emit(False)


__all__ = ["LoadCancelled", "ResultLoadCoordinator"]
