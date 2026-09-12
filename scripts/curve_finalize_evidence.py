"""Assemble the reproducible Curve C01-C05 validation manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "reviews" / "evidence" / "2026-09-12_curve_workbench_final"

SOURCE_PATHS = (
    "scripts/curve_c05_evidence.py",
    "src/five_axis_slicer/algorithms/curve/chain.py",
    "src/five_axis_slicer/algorithms/curve/toolpath.py",
    "src/five_axis_slicer/curve_automation.py",
    "src/five_axis_slicer/curve_commands.py",
    "src/five_axis_slicer/curve_controller.py",
    "src/five_axis_slicer/curve_generation_context.py",
    "src/five_axis_slicer/curve_operation_service.py",
    "src/five_axis_slicer/curve_shell.py",
    "src/five_axis_slicer/curve_ui.py",
    "src/five_axis_slicer/gcode_cache.py",
    "src/five_axis_slicer/opengl_scene.py",
    "src/five_axis_slicer/postprocessing/curve_product.py",
    "tests/test_curve_workbench.py",
    "tests/test_curve_integration.py",
    "docs/guides/curve_workbench_zh.md",
    "docs/reviews/2026-09-12_curve_workbench_review.md",
)

EXTERNAL_EVIDENCE = (
    "docs/reviews/evidence/2026-09-12_curve_workbench_final/history/curve_c01_c04_initial.xml",
    "docs/reviews/evidence/2026-09-12_curve_workbench_final/history/curve_c01_c04_retry1.xml",
    "docs/reviews/evidence/2026-09-12_curve_workbench_final/history/curve_c01_c05_integration1.xml",
    "docs/reviews/evidence/2026-09-12_curve_workbench_final/history/curve_c05_code_gate.xml",
    "docs/reviews/evidence/2026-09-12_curve_workbench_final/history/curve_c05_refactor_gate.xml",
    "docs/reviews/evidence/2026-09-12_curve_workbench_final/history/curve_integration_retry1.xml",
    "docs/reviews/evidence/2026-09-12_curve_workbench_final/history/curve_shared_qt_integration1.xml",
    "docs/reviews/evidence/2026-09-12_curve_workbench_final/history/curve_shared_source_project1.xml",
    "docs/reviews/evidence/2026-09-12_curve_workbench_final/history/curve_workbench_retry2.xml",
)


def _record(path: Path) -> dict[str, object]:
    relative = path.relative_to(ROOT).as_posix()
    return {
        "path": relative,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _existing_records(paths: tuple[str, ...]) -> list[dict[str, object]]:
    return [_record(ROOT / item) for item in paths if (ROOT / item).is_file()]


def _evidence_records() -> list[dict[str, object]]:
    excluded = {"validation_manifest.json"}
    return [
        _record(path)
        for path in sorted(EVIDENCE.rglob("*"))
        if path.is_file() and path.name not in excluded
    ]


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _git_source_head() -> str:
    return subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", "src"], cwd=ROOT, text=True
    ).strip()


def _validation_runs() -> list[dict[str, object]]:
    return [
        {
            "name": "preflight_closeout",
            "command": (
                "tmp/pytest9/Scripts/python.exe -X utf8 "
                "C:/Users/Tang Xufeng/.codex/skills/five-axis-slicer-validation/"
                "scripts/preflight.py --repo <repo>"
            ),
            "exit": 0,
            "result": "dependency probe passed; QSettings writable",
            "evidence": "preflight_closeout.log",
        },
        {
            "name": "curve_and_shared_direct_closeout",
            "command": (
                "tmp/pytest9/Scripts/python.exe -X faulthandler -m pytest -q -ra "
                "tests/test_curve_workbench.py tests/test_curve_integration.py "
                "tests/test_preview_index.py tests/test_opengl_viewer.py "
                "--basetemp=tmp/pytest_curve_closeout_direct_20260912_2"
            ),
            "exit": 0,
            "result": "40 passed, 2 subtests passed",
            "evidence": "junit_curve_closeout_direct_retry1.xml",
        },
        {
            "name": "planar_shared",
            "exit": 0,
            "result": "225 passed, 555 deselected",
        },
        {
            "name": "tube_shared_retry1",
            "exit": 0,
            "result": "167 passed, 613 deselected, 8 subtests passed",
        },
        {
            "name": "full_closeout_numpy22",
            "command": (
                "tmp/pytest9/Scripts/python.exe -X faulthandler -m pytest -q -ra "
                "--basetemp=tmp/pytest_full_curve_closeout_20260912_1"
            ),
            "exit": 0,
            "result": "783 passed, 3 skipped, 130 subtests passed in 300.54s",
            "evidence": "junit_full_closeout.xml",
        },
        {
            "name": "quality_release",
            "command": "tmp/pytest9/Scripts/python.exe -X utf8 scripts/check_quality.py",
            "exit": 0,
            "result": "Ruff/format/context budget/Mypy passed; 134 source files",
            "evidence": "check_quality_release.log",
        },
        {
            "name": "pip_check_clean_env",
            "command": "tmp/curve_cleancheck/Scripts/python.exe -m pip check",
            "exit": 0,
            "result": "No broken requirements found",
            "evidence": "pip_check_clean_env_closeout.log",
        },
        {
            "name": "build_release",
            "command": (
                "tmp/pytest9/Scripts/python.exe -m build --outdir "
                "docs/reviews/evidence/2026-09-12_curve_workbench_final/packages"
            ),
            "exit": 0,
            "result": "sdist and wheel built from the recorded acceptance commit",
            "evidence": "build_release.log",
        },
        {
            "name": "twine_release",
            "command": "tmp/pytest9/Scripts/python.exe -m twine check <wheel> <sdist>",
            "exit": 0,
            "result": "2 artifacts PASSED",
            "evidence": "twine_release.log",
        },
        {
            "name": "native_preview_current",
            "command": (
                "tmp/curve_cleancheck/Scripts/python.exe -m pytest -q "
                "tests/test_preview_index.py"
            ),
            "exit": 0,
            "result": "native import passed; 3 tests passed",
            "evidence": "pytest_native_preview_closeout.log",
        },
    ]


def _failure_history() -> list[dict[str, object]]:
    return [
        {
            "stage": "curve initial",
            "result": "1 passed, 13 errors",
            "cause": "system pytest temp directory permission",
            "fix": "unique repository-local --basetemp",
        },
        {
            "stage": "curve final first attempt",
            "result": "23 passed, 1 failed",
            "cause": "test read GeometryReference kernel signature from wrong field",
            "fix": "read signature['kernel_signature']",
        },
        {
            "stage": "tube shared first attempt",
            "result": "166 passed, 1 failed, 8 subtests passed",
            "cause": "STEP import navigation opened CurvePage for a generic session",
            "fix": "shared show_after_model_import routing",
        },
        {
            "stage": "real Offset evidence",
            "result": "projection collapsed onto trimmed boundary",
            "cause": "edge direction selected the outside lateral",
            "fix": "reject collapsed projection and explicitly reverse the edge",
        },
        {
            "stage": "quality first attempt",
            "result": "2 mypy errors under NumPy 2.2.6 stubs",
            "cause": "np.savez keyword expansion and ndarray shape inference",
            "fix": "targeted stub suppression and explicit ndarray annotation",
        },
        {
            "stage": "quality closeout first retry",
            "result": "context budget exceeded by one line",
            "cause": "the explicit ndarray annotation added a function-body line",
            "fix": "place the annotation on the existing assignment line",
        },
        {
            "stage": "direct closeout first attempt",
            "result": "no tests collected; pytest exit 4",
            "cause": "PowerShell corrupted an absolute Chinese --junitxml path",
            "fix": "use repository-relative output and a new basetemp",
        },
        {
            "stage": "native closeout first attempt",
            "result": "import assertion exit 1 before tests",
            "cause": "the validation command used a non-existent NATIVE_AVAILABLE name",
            "fix": "use NATIVE_INDEX_AVAILABLE and verify the returned source is native",
        },
        {
            "stage": "new clean environment full run",
            "result": "native exit 0xC0000409 before pytest output",
            "cause": "unqualified new Qt/VTK environment",
            "fix": "retain as failure; qualify with the project-validated interpreter",
        },
    ]


def main() -> int:
    product_manifest = json.loads((EVIDENCE / "evidence_manifest.json").read_text("utf-8"))
    manifest = {
        "schema_version": 1,
        "task": "Curve C01-C05 final acceptance",
        "baseline_commit": "125942f2863009f4a20e273bc1207dbd4d992eb8",
        "code_commit": _git_source_head(),
        "acceptance_commit": _git_head(),
        "branch": "codex/curve-workbench-c01-c05",
        "environment": {
            "qualified_interpreter": "tmp/pytest9/Scripts/python.exe",
            "python": "3.12.7",
            "pytest": "9.1.1",
            "numpy": "2.2.6",
            "ocp": "7.8.1.1.post1",
            "qt": "5.15.2",
            "vtk": "9.3.1",
            "pytest_basetemp": "unique repository-local directory per run",
        },
        "product_evidence": product_manifest,
        "validation_runs": _validation_runs(),
        "failure_history": _failure_history(),
        "source_files": _existing_records(SOURCE_PATHS),
        "external_evidence": _existing_records(EXTERNAL_EVIDENCE),
        "evidence_files": _evidence_records(),
        "machine_boundary": [
            "Generic XYZAC and offline IK/FK/readback only",
            "Real controller, calibration, site collision, material qualification, and trial build are unverified",
        ],
    }
    output = EVIDENCE / "validation_manifest.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(output.relative_to(ROOT).as_posix())
    print(hashlib.sha256(output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
