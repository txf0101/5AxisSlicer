"""Keep legacy context exceptions scoped to the recorded source object."""

from scripts.check_context_budget import Metric, violations


def test_legacy_function_budget_does_not_exempt_new_functions() -> None:
    config = {
        "module_lines": 1000,
        "class_lines": 500,
        "function_lines": 60,
        "complexity": 15,
        "legacy": {"example.py": {"function_lines": 100}},
        "legacy-object": {"example.py:existing": {"function_lines": 82}},
    }
    metrics = [
        Metric("function", "example.py:existing", 82),
        Metric("function", "example.py:new", 61),
    ]

    assert violations(metrics, config) == [(metrics[1], 60)]
