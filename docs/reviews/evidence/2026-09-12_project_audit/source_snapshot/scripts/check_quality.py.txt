"""Run the repository's incremental static-quality gate."""

from __future__ import annotations

import subprocess
import sys

# Modules enter this list after their legacy Ruff debt is cleared.
MIGRATED_FILES = (
    "setup.py",
    "run_app.py",
    "scripts/automation_client.py",
    "scripts/check_context_budget.py",
    "scripts/check_quality.py",
    "scripts/desktop_click_smoke.py",
    "scripts/desktop_workbench_smoke.py",
    "src/five_axis_slicer/__init__.py",
    "src/five_axis_slicer/app.py",
    "src/five_axis_slicer/automation.py",
    "src/five_axis_slicer/automation_routes.py",
    "src/five_axis_slicer/background_load.py",
    "src/five_axis_slicer/gcode_arrays.py",
    "src/five_axis_slicer/gcode_cache.py",
    "src/five_axis_slicer/gcode_parser.py",
    "src/five_axis_slicer/gcode_preview.py",
    "src/five_axis_slicer/manufacturing/machine.py",
    "src/five_axis_slicer/manufacturing/nozzle_envelope.py",
    "src/five_axis_slicer/manufacturing/reference_audit.py",
    "src/five_axis_slicer/manufacturing/reference_descriptors.py",
    "src/five_axis_slicer/manufacturing/reference_rebind.py",
    "src/five_axis_slicer/manufacturing/references.py",
    "src/five_axis_slicer/manufacturing/setup.py",
    "src/five_axis_slicer/model_commit.py",
    "src/five_axis_slicer/models.py",
    "src/five_axis_slicer/opengl_picking.py",
    "src/five_axis_slicer/opengl_scene.py",
    "src/five_axis_slicer/opengl_viewer.py",
    "src/five_axis_slicer/project_assets.py",
    "src/five_axis_slicer/project_contract.py",
    "src/five_axis_slicer/project_io.py",
    "src/five_axis_slicer/project_storage.py",
    "src/five_axis_slicer/result_commit.py",
    "src/five_axis_slicer/result_preview.py",
    "src/five_axis_slicer/result_preview_layout.py",
    "src/five_axis_slicer/result_preview_text.py",
    "src/five_axis_slicer/step_loader.py",
    "src/five_axis_slicer/step_reader.py",
    "src/five_axis_slicer/step_topology.py",
    "src/five_axis_slicer/tube_controller.py",
    "src/five_axis_slicer/tube_drafts.py",
    "src/five_axis_slicer/tube_resource_context.py",
    "src/five_axis_slicer/tube_resource_selection.py",
    "src/five_axis_slicer/tube_serialization.py",
    "src/five_axis_slicer/tube_ui.py",
    "src/five_axis_slicer/tube_ui_presenter.py",
    "src/five_axis_slicer/tube_ui_text.py",
    "src/five_axis_slicer/tube_validation.py",
    "src/five_axis_slicer/ui.py",
    "src/five_axis_slicer/viewer.py",
    "src/five_axis_slicer/viewer_common.py",
    "src/five_axis_slicer/viewer_interaction.py",
    "tests/test_automation.py",
    "tests/test_project_io.py",
    "tests/test_source_update_workflow.py",
    "tests/test_tube_controller.py",
    "tests/test_tube_resource_selection.py",
    "tests/test_tube_ui.py",
    "tests/test_tube_ui_help.py",
    "tests/test_viewer_common.py",
    "tests/test_viewer_interaction.py",
)


def main() -> int:
    commands = (
        ("Ruff", ("-m", "ruff", "check", ".")),
        ("Migrated Ruff", ("-m", "ruff", "check", "--select", "I,UP,B", *MIGRATED_FILES)),
        (
            "Security Ruff",
            (
                "-m",
                "ruff",
                "check",
                "--select",
                "S",
                "scripts/automation_client.py",
                "src/five_axis_slicer/automation.py",
                "src/five_axis_slicer/project_assets.py",
                "src/five_axis_slicer/project_io.py",
                "src/five_axis_slicer/project_storage.py",
            ),
        ),
        ("Migrated format", ("-m", "ruff", "format", "--check", *MIGRATED_FILES)),
        ("Context budget", ("scripts/check_context_budget.py",)),
        ("Mypy", ("-m", "mypy", "src")),
    )
    for label, arguments in commands:
        print(f"==> {label}", flush=True)
        result = subprocess.run(  # noqa: S603 - commands are the constants above
            (sys.executable, *arguments), check=False
        )
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
