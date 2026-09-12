from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.command_kernel import (  # noqa: E402
    CommandError,
    CommandInvocation,
    CommandKernel,
)
from five_axis_slicer.manufacturing.machine import (  # noqa: E402
    CARTESIAN_REFERENCE,
    GENERIC_XYZAC_REFERENCE,
)
from five_axis_slicer.manufacturing.library import (  # noqa: E402
    UserResourceLibrary,
)
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    builtin_material_profiles,
    builtin_nozzle_profiles,
)
from five_axis_slicer.manufacturing.setup import MODEL_CS_NODE  # noqa: E402
from five_axis_slicer.models import BodyInfo, CadModel  # noqa: E402
from five_axis_slicer.tube_commands import TubeCommandProvider  # noqa: E402
from five_axis_slicer.tube_controller import TubeSetupController  # noqa: E402


def cad_model(source_hash: str = "a" * 64) -> CadModel:
    return CadModel(
        source_path=Path("pipe2.step"),
        source_hash=source_hash,
        bodies=[
            BodyInfo("solid-base", 1, "Base", (0.4, 0.5, 0.6), kind="solid"),
            BodyInfo("solid-tube", 2, "Tube", (0.6, 0.5, 0.4), kind="solid"),
            BodyInfo("sheet-guide", 3, "Guide", (0.3, 0.3, 0.3), kind="shell"),
        ],
        edges=[],
        shapes={},
        edge_shapes={},
    )


def invocation(command: str, *args: object, **kwargs: object) -> CommandInvocation:
    return CommandInvocation(command, args, kwargs)


def numeric_draft(
    controller: TubeSetupController,
    origin: tuple[float, float, float],
) -> None:
    controller.begin_coordinate_draft(MODEL_CS_NODE)
    controller.set_numeric_origin(MODEL_CS_NODE, origin, confirmed=True)
    controller.set_numeric_direction(MODEL_CS_NODE, "z", (0, 0, 1), confirmed=True)
    controller.set_numeric_direction(MODEL_CS_NODE, "x", (1, 0, 0), confirmed=True)


class CommandKernelTests(unittest.TestCase):
    def test_query_alias_revision_and_operation_update(self) -> None:
        controller = TubeSetupController(cad_model())
        published = []
        kernel = CommandKernel(
            controller,
            TubeCommandProvider(),
            on_publish=published.append,
        )

        state = kernel.execute(CommandInvocation("管状.状态", command_id="query-1"))
        self.assertEqual(state.command, "state")
        self.assertEqual(state.revision, 0)
        self.assertFalse(state.changed)
        self.assertEqual(state.command_id, "query-1")
        self.assertFalse(kernel.can_undo)
        self.assertEqual(published, [])

        created = kernel.execute(invocation("create_operation", name="Tube pass"))
        self.assertEqual(created.revision, 1)
        self.assertEqual(controller.operations[0].name, "Tube pass")
        updated = kernel.execute(invocation("set_operation", name="Indexed", enabled=False))
        self.assertEqual(updated.revision, 2)
        self.assertEqual(controller.operations[0].name, "Indexed")
        self.assertFalse(controller.operations[0].enabled)
        self.assertEqual(len(published), 2)

        with self.assertRaises(CommandError) as raised:
            kernel.execute(
                CommandInvocation(
                    "state",
                    expected_revision=1,
                    command_id="stale-1",
                )
            )
        self.assertEqual(raised.exception.code, "E_REVISION_CONFLICT")
        self.assertEqual(raised.exception.command_id, "stale-1")

    def test_failed_domain_or_persistence_does_not_publish_candidate(self) -> None:
        controller = TubeSetupController(cad_model())
        persisted = []
        kernel = CommandKernel(
            controller,
            TubeCommandProvider(),
            persist=lambda candidate, revision, project_only: persisted.append(
                (candidate, revision, project_only)
            ),
        )

        with self.assertRaises(CommandError) as raised:
            kernel.execute(invocation("set_model_cs", z=(0, 0, 0)))
        self.assertEqual(raised.exception.code, "E_DOMAIN_VALIDATION")
        self.assertIsNone(controller.setup.model_coordinate_system)
        self.assertFalse(controller.has_drafts)
        self.assertEqual(kernel.revision, 0)
        self.assertEqual(persisted, [])

        failing = CommandKernel(
            controller,
            TubeCommandProvider(),
            persist=lambda *_: (_ for _ in ()).throw(OSError("disk full")),
        )
        with self.assertRaises(CommandError) as raised:
            failing.execute(invocation("create_operation"))
        self.assertEqual(raised.exception.code, "E_CONFIG_IO")
        self.assertEqual(controller.operations, ())
        self.assertEqual(failing.revision, 0)

        with self.assertRaises(CommandError):
            kernel.transaction(
                (
                    invocation("create_operation"),
                    invocation("set_model_cs", z=(0, 0, 0)),
                )
            )
        self.assertEqual(controller.operations, ())
        self.assertIsNone(controller.setup.model_coordinate_system)
        self.assertEqual(persisted, [])

    def test_notification_failure_does_not_reverse_a_committed_command(self) -> None:
        controller = TubeSetupController(cad_model())
        kernel = CommandKernel(
            controller,
            TubeCommandProvider(),
            on_publish=lambda _result: (_ for _ in ()).throw(RuntimeError("refresh failed")),
        )

        with self.assertLogs("five_axis_slicer.command_kernel", level="ERROR"):
            result = kernel.execute(invocation("create_operation"))

        self.assertTrue(result.changed)
        self.assertEqual(result.revision, 1)
        self.assertEqual(len(controller.operations), 1)
        self.assertTrue(kernel.can_undo)

    def test_validation_report_is_computed_before_persistence_and_publication(self) -> None:
        controller = TubeSetupController(cad_model())
        persisted: list[int] = []
        kernel = CommandKernel(
            controller,
            TubeCommandProvider(),
            persist=lambda _candidate, revision, _project_only: persisted.append(revision),
        )

        with (
            mock.patch.object(
                TubeSetupController,
                "validation_report",
                side_effect=RuntimeError("validation unavailable"),
            ),
            self.assertRaisesRegex(RuntimeError, "validation unavailable"),
        ):
            kernel.execute(invocation("create_operation"))

        self.assertEqual(controller.operations, ())
        self.assertEqual(persisted, [])
        self.assertEqual(kernel.revision, 0)

    def test_busy_guard_and_strict_command_signature(self) -> None:
        controller = TubeSetupController(cad_model())
        busy = [True]
        kernel = CommandKernel(
            controller,
            TubeCommandProvider(),
            is_busy=lambda: busy[0],
        )

        self.assertFalse(kernel.execute(invocation("state")).changed)
        with self.assertRaises(CommandError) as raised:
            kernel.execute(invocation("create_operation"))
        self.assertEqual(raised.exception.code, "E_LOAD_BUSY")

        busy[0] = False
        with self.assertRaises(CommandError) as raised:
            kernel.execute(invocation("create_operation", unsupported=True))
        self.assertEqual(raised.exception.code, "E_ARGUMENT_INVALID")
        self.assertEqual(controller.operations, ())
        with self.assertRaises(CommandError) as raised:
            kernel.execute(invocation("unknown"))
        self.assertEqual(raised.exception.code, "E_COMMAND_UNKNOWN")

    def test_persistence_observes_candidate_before_live_publication(self) -> None:
        controller = TubeSetupController(cad_model())
        observations: list[tuple[int, int]] = []

        def persist(candidate: object, _revision: int, _project_only: bool) -> bool:
            proposed = candidate
            assert isinstance(proposed, TubeSetupController)
            observations.append((len(controller.operations), len(proposed.operations)))
            return True

        kernel = CommandKernel(controller, TubeCommandProvider(), persist=persist)
        result = kernel.execute(invocation("create_operation"))

        self.assertTrue(result.config_synced)
        self.assertEqual(observations, [(0, 1)])
        self.assertEqual(len(controller.operations), 1)

    def test_transaction_undo_redo_and_new_branch(self) -> None:
        controller = TubeSetupController(cad_model())
        persisted: list[tuple[int, bool]] = []
        kernel = CommandKernel(
            controller,
            TubeCommandProvider(),
            persist=lambda _, revision, project_only: persisted.append((revision, project_only)),
        )
        result = kernel.transaction(
            (
                invocation("create_operation"),
                invocation("confirm_part"),
                invocation("set_model_cs"),
            ),
            origin="script",
            command_id="block-1",
        )

        self.assertEqual(result.command, "transaction")
        self.assertEqual(result.revision, 1)
        self.assertEqual(result.origin, "script")
        self.assertFalse(result.project_only)
        self.assertEqual(
            result.changed_fields,
            ("operations", "setup.assignments", "setup.coordinate_systems.model"),
        )
        self.assertEqual(persisted, [(1, False)])
        self.assertEqual(len(controller.operations), 1)
        self.assertTrue(controller.setup.assignments.has_part)
        self.assertIsNotNone(controller.setup.model_coordinate_system)

        undone = kernel.execute(invocation("undo"))
        self.assertEqual(undone.revision, 2)
        self.assertEqual(undone.changed_fields, result.changed_fields)
        self.assertEqual(controller.operations, ())
        self.assertFalse(controller.setup.assignments.has_part)
        self.assertIsNone(controller.setup.model_coordinate_system)
        self.assertTrue(kernel.can_redo)

        redone = kernel.execute(invocation("redo"))
        self.assertEqual(redone.revision, 3)
        self.assertEqual(redone.changed_fields, result.changed_fields)
        self.assertEqual(len(controller.operations), 1)
        self.assertTrue(controller.setup.assignments.has_part)

        kernel.execute(invocation("undo"))
        branch = kernel.execute(invocation("confirm_part"))
        self.assertTrue(branch.project_only)
        self.assertFalse(kernel.can_redo)
        with self.assertRaises(CommandError) as raised:
            kernel.execute(invocation("redo"))
        self.assertEqual(raised.exception.code, "E_DOMAIN_VALIDATION")

    def test_draft_guard_internal_apply_and_discard_semantics(self) -> None:
        controller = TubeSetupController(cad_model())
        persisted: list[tuple[int, bool]] = []
        kernel = CommandKernel(
            controller,
            TubeCommandProvider(),
            persist=lambda _, revision, project_only: persisted.append((revision, project_only)),
        )
        kernel.execute(invocation("set_model_cs"))
        numeric_draft(controller, (5, 0, 0))

        with self.assertRaises(CommandError) as raised:
            kernel.execute(invocation("set_machine", CARTESIAN_REFERENCE.profile_id))
        self.assertEqual(raised.exception.code, "E_DRAFT_ACTIVE")
        applied = kernel.execute(invocation("apply_coordinate_draft", MODEL_CS_NODE))
        self.assertTrue(applied.changed)
        self.assertFalse(controller.has_drafts)
        model = controller.setup.model_coordinate_system
        assert model is not None
        self.assertEqual(model.origin_reference.resolved_point, (5.0, 0.0, 0.0))

        kernel.execute(invocation("undo"))
        model = controller.setup.model_coordinate_system
        assert model is not None
        self.assertEqual(model.origin_reference.resolved_point, (0.0, 0.0, 0.0))
        self.assertFalse(controller.has_drafts)
        self.assertTrue(kernel.can_redo)

        controller.begin_coordinate_draft("build_cs")
        discarded = kernel.execute(invocation("discard_all_drafts"))
        self.assertTrue(discarded.changed)
        self.assertTrue(discarded.project_only)
        self.assertFalse(controller.has_drafts)
        self.assertFalse(kernel.can_redo)
        self.assertTrue(kernel.can_undo)
        revision = kernel.revision
        unchanged = kernel.execute(invocation("discard_all_drafts"))
        self.assertFalse(unchanged.changed)
        self.assertEqual(kernel.revision, revision)
        self.assertEqual(persisted[-1], (4, True))

    def test_resource_overrides_are_replay_stable_and_library_read_only(self) -> None:
        nozzle_id = builtin_nozzle_profiles()[0].resource_id
        material_id = builtin_material_profiles()[0].resource_id
        with TemporaryDirectory() as folder:
            library = UserResourceLibrary(folder)
            first = TubeSetupController(cad_model(), resource_library=library)
            second = TubeSetupController(cad_model(), resource_library=library)
            first_kernel = CommandKernel(first, TubeCommandProvider())
            second_kernel = CommandKernel(second, TubeCommandProvider())
            nozzle = invocation(
                "set_nozzle",
                nozzle_id,
                interface="M6×1",
                length_mm=12.5,
                use_collision_envelope=True,
            )
            material = invocation(
                "set_material",
                material_id,
                review_confirmed=True,
            )

            first_kernel.execute(nozzle)
            first_kernel.execute(material)
            second_kernel.execute(nozzle)
            second_kernel.execute(material)

            assert first.setup.nozzle is not None
            assert first.setup.material is not None
            assert second.setup.nozzle is not None
            assert second.setup.material is not None
            self.assertEqual(first.setup.nozzle.content_hash, second.setup.nozzle.content_hash)
            self.assertEqual(first.setup.nozzle.resource_id, second.setup.nozzle.resource_id)
            self.assertEqual(first.setup.material.content_hash, second.setup.material.content_hash)
            self.assertEqual(first.setup.material.resource_id, second.setup.material.resource_id)
            self.assertEqual([path for path in Path(folder).rglob("*") if path.is_file()], [])

            replay = first_kernel.execute(nozzle)
            self.assertFalse(replay.changed)
            with self.assertRaises(CommandError) as raised:
                first_kernel.execute(invocation("set_machine", "missing-machine"))
            self.assertEqual(raised.exception.code, "E_RESOURCE_NOT_FOUND")

            with self.assertRaises(CommandError) as raised:
                first_kernel.execute(invocation("set_nozzle", nozzle_id, length_mm=10**4000))
            self.assertEqual(raised.exception.code, "E_ARGUMENT_INVALID")

    def test_rotary_axis_words_are_a_transactional_machine_command(self) -> None:
        controller = TubeSetupController(cad_model())
        kernel = CommandKernel(controller, TubeCommandProvider())
        kernel.execute(invocation("set_machine", GENERIC_XYZAC_REFERENCE.profile_id))
        assert controller.setup.machine is not None
        original_hash = controller.setup.machine.content_hash

        result = kernel.execute(
            invocation(
                "set_machine_axis_words",
                {"A": "u", "C": "w"},
                name="DIY U/W controller",
            )
        )

        self.assertTrue(result.changed)
        self.assertEqual(dict(controller.machine_profile().rotary_axis_words), {"A": "U", "C": "W"})
        self.assertEqual(controller.machine_profile().name, "DIY U/W controller")
        assert controller.setup.machine is not None
        self.assertNotEqual(controller.setup.machine.content_hash, original_hash)
        self.assertIn("setup.resources.machine.rotary_axis_words", result.changed_fields)

        kernel.execute(invocation("undo"))
        assert controller.setup.machine is not None
        self.assertEqual(controller.setup.machine.content_hash, original_hash)
        kernel.execute(invocation("set_machine_axis_words", {"A": "U", "C": "W"}))
        self.assertEqual(controller.machine_profile().name, GENERIC_XYZAC_REFERENCE.name)
        kernel.execute(invocation("undo"))
        with self.assertRaises(CommandError) as raised:
            kernel.execute(invocation("set_machine_axis_words", {"A": "E"}))
        self.assertEqual(raised.exception.code, "E_ARGUMENT_INVALID")

    def test_coordinate_and_placement_commands_reach_coordinates_valid(self) -> None:
        controller = TubeSetupController(cad_model())
        persisted = []
        kernel = CommandKernel(
            controller,
            TubeCommandProvider(),
            persist=lambda candidate, revision, project_only: persisted.append(
                (candidate.setup, revision, project_only)
            ),
        )
        result = kernel.transaction(
            (
                invocation("confirm_part"),
                invocation("set_machine", CARTESIAN_REFERENCE.profile_id),
                invocation("set_model_cs"),
                invocation("set_build_cs"),
                invocation(
                    "set_placement",
                    "build_plate_mount",
                    translation_mm=(1, 2, 3),
                    rotation_xyz_deg=(90, 0, 0),
                ),
            )
        )

        self.assertTrue(result.coordinates_valid)
        self.assertTrue(controller.coordinates_valid)
        self.assertEqual(len(persisted), 1)
        adjustment = controller.setup.placement_adjustment
        self.assertEqual(adjustment.translation_mm, (1.0, 2.0, 3.0))
        self.assertAlmostEqual(abs(adjustment.quaternion_xyzw[0]), math.sqrt(0.5), places=7)
        self.assertAlmostEqual(abs(adjustment.quaternion_xyzw[3]), math.sqrt(0.5), places=7)
        self.assertIn("MACHINE_REFERENCE_ONLY", result.issue_codes)

    def test_external_state_detection_rebind_and_bounded_history(self) -> None:
        controller = TubeSetupController(cad_model())
        kernel = CommandKernel(controller, TubeCommandProvider(), history_limit=2)
        kernel.execute(invocation("set_model_cs", origin=(0, 0, 0)))
        kernel.execute(invocation("set_model_cs", origin=(1, 0, 0)))
        kernel.execute(invocation("set_model_cs", origin=(2, 0, 0)))
        kernel.execute(invocation("undo"))
        kernel.execute(invocation("undo"))
        with self.assertRaises(CommandError):
            kernel.execute(invocation("undo"))

        controller.create_operation(operation_id="external-operation")
        revision = kernel.revision
        observed = kernel.execute(invocation("state"))
        self.assertEqual(observed.revision, revision + 1)
        self.assertEqual(kernel.revision, revision + 1)
        self.assertFalse(kernel.can_undo)
        self.assertFalse(kernel.synchronize_external_state())

        replacement = TubeSetupController(cad_model("b" * 64))
        rebound_revision = kernel.rebind(replacement)
        self.assertTrue(kernel.is_bound_to(replacement))
        self.assertEqual(kernel.revision, rebound_revision)
        self.assertEqual(kernel.reset_external_state(), rebound_revision + 1)


if __name__ == "__main__":
    unittest.main()
