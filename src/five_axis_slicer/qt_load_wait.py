"""Bounded nested Qt wait used by synchronous compatibility APIs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt5.QtCore import QEventLoop, QTimer

from .background_load import ResultLoadCoordinator


def wait_for_loader_outcome(
    loader: ResultLoadCoordinator,
    outcomes: dict[object, dict[str, Any]],
    request_id: object,
    *,
    timeout_ms: int,
    timeout_message: str,
    cancel: Callable[[], None],
) -> dict[str, Any]:
    """Dispatch GUI events until a request and its worker are both settled."""

    outcome = outcomes[request_id]
    if outcome["status"] != "loading" and not loader.busy:
        return outcome
    loop = QEventLoop()
    timed_out = False

    def settled() -> bool:
        request_finished = outcomes[request_id]["status"] != "loading"
        worker_released = loader.active_request_id != request_id or not loader.busy
        return bool(request_finished and worker_released)

    def finish_if_settled(*_args: object) -> None:
        if settled():
            loop.quit()

    def expire() -> None:
        nonlocal timed_out
        timed_out = True
        loop.quit()

    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(expire)
    signals = (loader.completed, loader.failed, loader.cancelled, loader.busy_changed)
    for signal in signals:
        signal.connect(finish_if_settled)
    try:
        timeout.start(max(1, int(timeout_ms)))
        finish_if_settled()
        if not settled():
            loop.exec()
    finally:
        timeout.stop()
        timeout.timeout.disconnect(expire)
        for signal in signals:
            signal.disconnect(finish_if_settled)

    if timed_out and not settled():
        outcomes[request_id].update(status="cancelled", message=timeout_message)
        if loader.busy:
            cancel()
        raise TimeoutError(timeout_message)
    return outcomes[request_id]


__all__ = ["wait_for_loader_outcome"]
