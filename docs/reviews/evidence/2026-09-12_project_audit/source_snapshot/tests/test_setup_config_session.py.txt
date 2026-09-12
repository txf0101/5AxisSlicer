from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.command_kernel import (  # noqa: E402
    CommandError,
    CommandInvocation,
    CommandKernel,
)
from five_axis_slicer.models import BodyInfo, CadModel  # noqa: E402
from five_axis_slicer.setup_config import (  # noqa: E402
    CONFIG_FILENAME,
    SetupConfigConflictError,
    atomic_write_setup_config,
    dump_setup_config,
    export_setup_config,
    load_setup_config_file,
    setup_config_fingerprint,
)
from five_axis_slicer.setup_config_session import (  # noqa: E402
    SetupConfigStore,
    apply_setup_config,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    IssueSeverity,
    ValidationIssue,
)
from five_axis_slicer.tube_commands import TubeCommandProvider  # noqa: E402
from five_axis_slicer.tube_controller import TubeSetupController  # noqa: E402


def controller() -> TubeSetupController:
    model = CadModel(
        source_path=Path("pipe.step"),
        source_hash="a" * 64,
        bodies=[BodyInfo("solid-1", 1, "Tube", (0.4, 0.5, 0.6), kind="solid")],
        edges=[],
        shapes={},
        edge_shapes={},
    )
    return TubeSetupController(model)


class SetupConfigStoreTests(unittest.TestCase):
    def test_saved_baseline_identifies_recoverable_yaml_work(self) -> None:
        live = controller()
        store = SetupConfigStore()
        store.reset_memory(live)
        with TemporaryDirectory() as folder:
            project = Path(folder)
            store.project_saved(live, project, revision=1)
            saved = live.fork()
            kernel = CommandKernel(live, TubeCommandProvider(), persist=store.persist_candidate)

            result = kernel.execute(CommandInvocation("set_model_cs", kwargs={"origin": (3, 0, 0)}))

            self.assertTrue(result.config_synced)
            inspection = store.inspect_project(saved, project)
            self.assertEqual(inspection.comparison, "recoverable")
            self.assertIn("$.setup.coordinate_systems.model", inspection.differences)
            config = load_setup_config_file(project / CONFIG_FILENAME)
            self.assertEqual(config.base_project_setup_sha256, inspection.project_hash)

    def test_part_command_is_undoable_without_changing_yaml_bytes(self) -> None:
        live = controller()
        store = SetupConfigStore()
        store.reset_memory(live)
        with TemporaryDirectory() as folder:
            project = Path(folder)
            path = store.project_saved(live, project, revision=1)
            before = path.read_bytes()
            kernel = CommandKernel(live, TubeCommandProvider(), persist=store.persist_candidate)

            result = kernel.execute(CommandInvocation("confirm_part"))

            self.assertTrue(result.project_only)
            self.assertTrue(live.setup.assignments.has_part)
            self.assertEqual(path.read_bytes(), before)
            kernel.execute(CommandInvocation("undo"))
            self.assertFalse(live.setup.assignments.has_part)
            self.assertEqual(path.read_bytes(), before)

    def test_external_change_pauses_publish_and_preserves_live_state(self) -> None:
        live = controller()
        store = SetupConfigStore()
        store.reset_memory(live)
        with TemporaryDirectory() as folder:
            path = store.project_saved(live, folder, revision=1)
            path.write_text(path.read_text(encoding="utf-8") + "# external\n", encoding="utf-8")
            kernel = CommandKernel(live, TubeCommandProvider(), persist=store.persist_candidate)

            with self.assertRaises(CommandError) as raised:
                kernel.execute(CommandInvocation("set_model_cs"))

            self.assertEqual(raised.exception.code, "E_CONFIG_DIVERGED")
            self.assertIsNone(live.setup.model_coordinate_system)
            self.assertTrue(store.suspended)
            self.assertIn("# external", path.read_text(encoding="utf-8"))

            _, preview_fingerprint = store.preview_external()
            path.write_text(
                path.read_text(encoding="utf-8") + "# changed again\n", encoding="utf-8"
            )
            with self.assertRaises(SetupConfigConflictError):
                store.accept_external(preview_fingerprint)

    def test_yaml_resolution_preserves_part_and_operation_identity(self) -> None:
        project_state = controller()
        project_state.confirm_assignments(("solid-1",))
        project_state.create_operation(operation_id="kept-operation")
        yaml_state = project_state.fork()
        yaml_state.begin_coordinate_draft("model_cs")
        yaml_state.set_numeric_origin("model_cs", (5, 0, 0), confirmed=True)
        yaml_state.set_numeric_direction("model_cs", "z", (0, 0, 1), confirmed=True)
        yaml_state.set_numeric_direction("model_cs", "x", (1, 0, 0), confirmed=True)
        yaml_state.apply_coordinate_draft("model_cs")

        with TemporaryDirectory() as folder:
            path = Path(folder) / CONFIG_FILENAME
            config = export_setup_config(
                yaml_state.setup,
                yaml_state.operations,
                base_project_setup_sha256="b" * 64,
            )
            atomic_write_setup_config(path, dump_setup_config(config), expect_missing=True)
            pending = SetupConfigStore()
            inspection = pending.inspect_project(project_state, folder)

            self.assertEqual(inspection.comparison, "diverged")
            pending.attach_project(project_state, inspection, "yaml")
            self.assertEqual(project_state.setup.assignments.part_body_ids, ("solid-1",))
            self.assertEqual(project_state.operations[0].operation_id, "kept-operation")
            frame = project_state.setup.model_coordinate_system
            assert frame is not None
            self.assertEqual(frame.origin_reference.resolved_point, (5.0, 0.0, 0.0))
            self.assertEqual(
                setup_config_fingerprint(path),
                pending.state_json()["fingerprint"],
            )

    def test_applying_portable_config_retains_project_validation_issues(self) -> None:
        live = controller()
        issue = ValidationIssue(
            "SOURCE_REFERENCE_REVIEW_REQUIRED",
            IssueSeverity.WARNING,
            live.setup.setup_id,
            {"source": "STEP update"},
        )
        checkpoint = live.command_checkpoint()
        live.restore_command_checkpoint(
            replace(checkpoint, setup=replace(live.setup, issues=(issue,)))
        )
        config = export_setup_config(replace(live.setup, name="Imported Setup"))

        apply_setup_config(live, config)

        self.assertEqual(live.setup.name, "Imported Setup")
        self.assertIn(issue, live.setup.issues)


if __name__ == "__main__":
    unittest.main()
