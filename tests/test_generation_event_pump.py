from five_axis_slicer.generation_event_pump import throttled_event_pump


def test_generation_event_pump_limits_repaints_but_keeps_cancellation_checks_fast():
    now = [0.0]
    calls = []
    pump = throttled_event_pump(lambda: calls.append(now[0]), clock=lambda: now[0])
    for _ in range(1000):
        pump()
    assert calls == [0.0]
    now[0] = 0.051
    pump()
    assert calls == [0.0, 0.051]


def test_generation_event_pump_does_not_reenter_and_recovers_after_error():
    now = [0.0]
    calls = []

    def callback():
        calls.append(now[0])
        pump()
        if len(calls) == 1:
            raise RuntimeError("paint failure")

    pump = throttled_event_pump(callback, clock=lambda: now[0])
    try:
        pump()
    except RuntimeError:
        pass
    else:
        raise AssertionError("event-pump callback error was swallowed")
    now[0] = 0.1
    pump()
    assert calls == [0.0, 0.1]
