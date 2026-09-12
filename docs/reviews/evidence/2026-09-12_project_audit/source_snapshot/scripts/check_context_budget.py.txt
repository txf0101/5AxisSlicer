"""Reject source objects that exceed the repository's context-size ratchet."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 development environments.
    import tomli as tomllib


@dataclass(frozen=True)
class Metric:
    kind: str
    name: str
    value: int


class SourceMetrics(ast.NodeVisitor):
    """Collect qualified object sizes without importing application modules."""

    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        self.scope: list[str] = []
        self.metrics: list[Metric] = []

    def _visit_object(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        name = ".".join((*self.scope, node.name))
        key = f"{self.relative_path}:{name}"
        size = (node.end_lineno or node.lineno) - node.lineno + 1
        if isinstance(node, ast.ClassDef):
            self.metrics.append(Metric("class", key, size))
        else:
            self.metrics.extend(
                (Metric("function", key, size), Metric("complexity", key, complexity(node)))
            )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = _visit_object
    visit_ClassDef = _visit_object
    visit_FunctionDef = _visit_object


class Complexity(ast.NodeVisitor):
    """Small McCabe-style counter used only as a stable repository ratchet."""

    def __init__(self) -> None:
        self.value = 1

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.value += max(1, len(node.values) - 1)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.value += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.value += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.value += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.value += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.value += 1
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.value += len(node.handlers) + bool(node.orelse) + bool(node.finalbody)
        self.generic_visit(node)

    visit_TryStar = visit_Try

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.value += 1 + len(node.ifs)
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.value += max(0, len(node.cases) - 1)
        self.generic_visit(node)

    # A nested callable has its own metric and must not inflate its parent's score.
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return None

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return None

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return None


def complexity(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    counter = Complexity()
    for statement in node.body:
        counter.visit(statement)
    return counter.value


def load_config(project_file: Path) -> dict[str, Any]:
    with project_file.open("rb") as stream:
        return tomllib.load(stream)["tool"]["context-budget"]


def collect(root: Path) -> list[Metric]:
    metrics: list[Metric] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        metrics.append(Metric("module", relative, len(source.splitlines())))
        visitor = SourceMetrics(relative)
        visitor.visit(ast.parse(source, filename=str(path)))
        metrics.extend(visitor.metrics)
    return metrics


def violations(metrics: list[Metric], config: dict[str, Any]) -> list[tuple[Metric, int]]:
    failed: list[tuple[Metric, int]] = []
    for metric in metrics:
        limit_key = f"{metric.kind}_lines" if metric.kind != "complexity" else metric.kind
        relative_path = metric.name.partition(":")[0]
        allowed = int(
            config.get("legacy", {}).get(relative_path, {}).get(limit_key, config[limit_key])
        )
        if metric.value > allowed:
            failed.append((metric, allowed))
    return failed


def print_baseline(metrics: list[Metric], config: dict[str, Any]) -> None:
    by_file: dict[str, dict[str, int]] = {}
    for metric in metrics:
        limit_key = f"{metric.kind}_lines" if metric.kind != "complexity" else metric.kind
        if metric.value <= config[limit_key]:
            continue
        relative_path = metric.name.partition(":")[0]
        current = by_file.setdefault(relative_path, {}).get(limit_key, 0)
        by_file[relative_path][limit_key] = max(current, metric.value)

    if by_file:
        print("[tool.context-budget.legacy]")
    order = ("module_lines", "class_lines", "function_lines", "complexity")
    for relative_path, limits in sorted(by_file.items()):
        fields = ", ".join(f"{key} = {limits[key]}" for key in order if key in limits)
        print(f'"{relative_path}" = {{ {fields} }}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-baseline", action="store_true")
    args = parser.parse_args()

    project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
    config = load_config(project_file)
    metrics = collect(project_file.parent / config["source_root"])
    if args.print_baseline:
        print_baseline(metrics, config)
        return 0

    failed = violations(metrics, config)
    for metric, allowed in failed:
        print(f"{metric.kind}: {metric.name} is {metric.value}; budget is {allowed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
