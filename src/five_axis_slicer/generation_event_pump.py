"""Bounded UI event processing during synchronous path generation."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter


def throttled_event_pump(
    process_events: Callable[[], None],
    *,
    interval_s: float = 0.05,
    clock: Callable[[], float] = perf_counter,
) -> Callable[[], None]:
    """Keep cancellation responsive without repainting for every path point."""

    last_run = float("-inf")
    active = False

    def pump() -> None:
        nonlocal last_run, active
        now = clock()
        if active or now - last_run < interval_s:
            return
        last_run = now
        active = True
        try:
            process_events()
        finally:
            active = False

    return pump
