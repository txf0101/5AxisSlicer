from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    DirectionReference,
    LocalAdjustment,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.machine import (  # noqa: E402
    CARTESIAN_REFERENCE,
    GENERIC_XYZAC_REFERENCE,
)
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    NozzleProfile,
    get_builtin_material_profile,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    BUILD_CS_NODE,
    MODEL_CS_NODE,
    PLACEMENT_NODE,
    NodeState,
    TubeOperationDefinition,
)
from five_axis_slicer.models import BodyInfo, CadModel  # noqa: E402
from five_axis_slicer.tube_controller import (  # noqa: E402
    AVAILABLE_TUBE_OPERATION_TYPES,
    BodyRole,
    OperationLimitError,
    PendingDraftError,
    TubeSetupController,
)


def cad_model(source_hash: str = "a" * 64) -> CadModel:
    bodies = [
        BodyInfo("solid-base", 1, "Base", (0.4, 0.5, 0.6), kind="solid"),
        BodyInfo("solid-tube", 2, "Tube", (0.6, 0.5, 0.4), kind="solid"),
        BodyInfo("sheet-guide", 3, "Guide", (0.3, 0.3, 0.3), kind="shell"),
    ]
    return CadModel(
        source_path=Path("pipe2.step"),
        source_hash=source_hash,
        bodies=bodies,
        edges=[],
        shapes={},
        edge_shapes={},
    )


def complete_nozzle() -> NozzleProfile:
    return NozzleProfile(
        resource_id="shop-nozzle-04",
        display_name="Shop brass 0.4 mm",
        orifice_diameter_mm=0.4,
        filament_diameter_mm=1.75,
        interface="M6",
        length_mm=12.5,
        construction_material="brass",
        flow_category="standard",
        temperature_limit_c=300.0,
        wear_resistance_rating="standard",
        outer_profile_rz_mm=((0.2, 0.0), (3.0, 2.0), (3.0, 12.5)),
    )


def apply_numeric_frame(
    controller: TubeSetupController,
    node: str,
    origin: tuple[float, float, float],
) -> None:
    controller.begin_coordinate_draft(node)
    controller.set_numeric_origin(node, origin, confirmed=True)
    controller.set_numeric_direction(node, "z", (0, 0, 1), confirmed=True)
    controller.set_numeric_direction(node, "x", (1, 0, 0), confirmed=True)
    controller.apply_coordinate_draft(node)


class TubeControllerTests(unittest.TestCase):
    def test_cad_initialisation_and_explicit_part_confirmation(self) -> None:
        controller = TubeSetupController(cad_model())

        self.assertEqual(
            [item.body_id for item in controller.part_candidates],
            ["solid-base", "solid-tube"],
        )
        self.assertEqual(
            controller.setup.assignments.unassigned_body_ids,
            ("solid-base", "solid-tube", "sheet-guide"),
        )
        with self.assertRaisesRegex(ValueError, "closed solids"):
            controller.confirm_assignments(("sheet-guide",))

        assignments = controller.confirm_body_roles(
            {
                "solid-base": BodyRole.PART,
                "solid-tube": BodyRole.PART,
                "sheet-guide": BodyRole.UNASSIGNED,
            }
        )
        self.assertEqual(assignments.part_body_ids, ("solid-base", "solid-tube"))
        self.assertEqual(assignments.unassigned_body_ids, ("sheet-guide",))

    def test_three_interactive_operations_and_round_trip(self) -> None:
        controller = TubeSetupController(cad_model())
        operation = controller.create_operation(operation_id="tube-1")

        self.assertEqual(
            AVAILABLE_TUBE_OPERATION_TYPES,
            ("tube_thin_wall_indexed", "tube_buildup", "tube_continuous"),
        )
        self.assertEqual(operation.name, "Tube Thin-Wall Indexed")
        controller.create_operation("tube_buildup", operation_id="tube-2")
        controller.create_operation("tube_continuous", operation_id="tube-3")
        with self.assertRaises(OperationLimitError):
            controller.create_operation()

        payload = controller.to_json()
        restored = TubeSetupController.from_json(
            json.loads(json.dumps(payload)),
            cad_model=cad_model(),
        )
        self.assertEqual(
            [item.operation_id for item in restored.operations],
            ["tube-1", "tube-2", "tube-3"],
        )
        self.assertFalse(restored.can_create_operation)
        self.assertNotIn(
            "TUBE_OPERATION_COUNT_UNSUPPORTED",
            {issue.code for issue in restored.validation_report().issues},
        )

    def test_coordinate_draft_requires_confirmation_and_cancel_restores_applied(
        self,
    ) -> None:
        controller = TubeSetupController(cad_model())
        controller.begin_coordinate_draft(MODEL_CS_NODE)
        controller.set_origin_reference(
            MODEL_CS_NODE,
            PointReference("numeric", (0, 0, 0)),
        )
        controller.set_direction_reference(
            MODEL_CS_NODE,
            "z",
            DirectionReference("numeric", (0, 0, 1)),
        )
        controller.set_direction_reference(
            MODEL_CS_NODE,
            "x",
            DirectionReference("numeric", (1, 0, 0)),
        )
        with self.assertRaisesRegex(ValueError, "individually confirmed"):
            controller.apply_coordinate_draft(MODEL_CS_NODE)

        for component in ("origin", "z", "x"):
            controller.confirm_coordinate_reference(MODEL_CS_NODE, component)
        frame = controller.apply_coordinate_draft(MODEL_CS_NODE)
        self.assertTrue(frame.is_valid)

        controller.begin_coordinate_draft(MODEL_CS_NODE)
        controller.set_numeric_origin(
            MODEL_CS_NODE,
            (100, 0, 0),
            confirmed=True,
        )
        controller.cancel_draft(MODEL_CS_NODE)
        self.assertEqual(
            controller.setup.model_coordinate_system.origin_reference.resolved_point,
            (0.0, 0.0, 0.0),
        )

    def test_build_numeric_input_defaults_to_applied_model_coordinates(self) -> None:
        controller = TubeSetupController(cad_model())
        apply_numeric_frame(controller, MODEL_CS_NODE, (10, 0, 0))

        controller.begin_coordinate_draft(BUILD_CS_NODE)
        controller.set_numeric_origin(BUILD_CS_NODE, (5, 0, 0), confirmed=True)
        controller.set_numeric_direction(BUILD_CS_NODE, "z", (0, 0, 1), confirmed=True)
        controller.set_numeric_direction(BUILD_CS_NODE, "x", (1, 0, 0), confirmed=True)
        build = controller.apply_coordinate_draft(BUILD_CS_NODE)

        self.assertEqual(build.origin_reference.resolved_point, (15.0, 0.0, 0.0))
        self.assertEqual(build.T_target_from_source.transform_point((15, 0, 0)), (0.0, 0.0, 0.0))

    def test_dependencies_reach_coordinates_valid_and_setup_ready(self) -> None:
        controller = TubeSetupController(cad_model())
        controller.create_operation(operation_id="tube-1")
        controller.confirm_assignments(("solid-base", "solid-tube"))
        apply_numeric_frame(controller, MODEL_CS_NODE, (0, 0, 0))
        apply_numeric_frame(controller, BUILD_CS_NODE, (0, 0, 0))
        controller.select_machine(CARTESIAN_REFERENCE)
        controller.select_nozzle(complete_nozzle())
        controller.select_material(
            get_builtin_material_profile("PLA").reviewed_copy("reviewed-pla")
        )
        controller.begin_placement_draft(mount_datum_id="build_plate_mount")
        controller.set_placement_adjustment(LocalAdjustment.from_euler_xyz((1, 2, 3), (0, 0, 0)))
        controller.apply_placement_draft()

        report = controller.validation_report()
        self.assertTrue(report.coordinates_valid)
        self.assertTrue(report.setup_ready)
        self.assertIn("MACHINE_REFERENCE_ONLY", {issue.code for issue in report.issues})
        self.assertEqual(
            controller.T_machine_from_build().translation,
            (1.0, 2.0, 3.0),
        )

        apply_numeric_frame(controller, MODEL_CS_NODE, (2, 0, 0))
        self.assertTrue(controller.coordinates_valid)
        self.assertIs(
            controller.validation_report().state_for("placement"),
            NodeState.VALID,
        )
        self.assertIn("model_cs_changed", controller.operations[0].dirty_reasons)

        apply_numeric_frame(controller, BUILD_CS_NODE, (1, 0, 0))
        self.assertFalse(controller.coordinates_valid)
        self.assertIs(
            controller.validation_report().state_for("placement"),
            NodeState.DIRTY,
        )

    def test_machine_transforms_fail_closed_for_nonvalid_placement(self) -> None:
        controller = TubeSetupController(cad_model())
        with self.assertRaisesRegex(ValueError, "current state: missing"):
            controller.T_machine_from_build()
        with self.assertRaisesRegex(ValueError, "current state: missing"):
            controller.T_machine_from_source()

        controller.confirm_assignments(("solid-base", "solid-tube"))
        apply_numeric_frame(controller, MODEL_CS_NODE, (0, 0, 0))
        apply_numeric_frame(controller, BUILD_CS_NODE, (0, 0, 0))
        controller.select_machine(CARTESIAN_REFERENCE)
        controller.begin_placement_draft(mount_datum_id="build_plate_mount")
        controller.apply_placement_draft()

        controller.begin_placement_draft()
        self.assertIs(
            controller.validation_report().state_for("placement"),
            NodeState.DRAFT,
        )
        for transform in (
            controller.T_machine_from_build,
            controller.T_machine_from_source,
        ):
            with self.subTest(state="draft", transform=transform.__name__):
                with self.assertRaisesRegex(ValueError, "current state: draft"):
                    transform()
        controller.cancel_draft("placement")

        apply_numeric_frame(controller, BUILD_CS_NODE, (10, 0, 0))
        self.assertIs(
            controller.validation_report().state_for("placement"),
            NodeState.DIRTY,
        )
        for transform in (
            controller.T_machine_from_build,
            controller.T_machine_from_source,
        ):
            with self.subTest(state="dirty", transform=transform.__name__):
                with self.assertRaisesRegex(ValueError, "current state: dirty"):
                    transform()

        invalid_setup = controller.setup.with_placement(
            "build_plate_mount",
            RigidTransform(
                RigidTransform.identity().matrix,
                source_frame="machine",
                target_frame="build_plate_mount",
            ),
        )
        invalid = TubeSetupController(cad_model(), setup=invalid_setup)
        self.assertIs(
            invalid.validation_report().state_for("placement"),
            NodeState.INVALID,
        )
        for transform in (
            invalid.T_machine_from_build,
            invalid.T_machine_from_source,
        ):
            with self.subTest(state="invalid", transform=transform.__name__):
                with self.assertRaisesRegex(ValueError, "current state: invalid"):
                    transform()

    def test_domain_authority_blocks_forged_part_mount_and_operation(self) -> None:
        controller = TubeSetupController(cad_model())
        controller.confirm_assignments(("solid-base", "solid-tube"))
        apply_numeric_frame(controller, MODEL_CS_NODE, (0, 0, 0))
        apply_numeric_frame(controller, BUILD_CS_NODE, (0, 0, 0))
        controller.select_machine(CARTESIAN_REFERENCE)
        controller.select_nozzle(complete_nozzle())
        controller.select_material(
            get_builtin_material_profile("PLA").reviewed_copy("reviewed-pla")
        )
        controller.begin_placement_draft(mount_datum_id="build_plate_mount")
        controller.apply_placement_draft()
        self.assertTrue(controller.setup_ready)

        detached = TubeSetupController(setup=controller.setup)
        detached_report = detached.validation_report()
        self.assertFalse(detached_report.setup_ready)
        self.assertIs(detached_report.state_for("part"), NodeState.INVALID)
        self.assertIn("CAD_MODEL_MISSING", {issue.code for issue in detached_report.issues})

        wrong_mount_setup = controller.setup.with_placement(
            "forged_mount",
            controller.setup.T_mount_from_build,
        )
        wrong_mount = TubeSetupController(cad_model(), setup=wrong_mount_setup)
        wrong_mount_report = wrong_mount.validation_report()
        self.assertFalse(wrong_mount_report.setup_ready)
        self.assertIs(wrong_mount_report.state_for("placement"), NodeState.INVALID)
        self.assertIn(
            "PLACEMENT_MOUNT_MISSING",
            {issue.code for issue in wrong_mount_report.issues},
        )

        wrong_operation = TubeSetupController(
            cad_model(),
            setup=controller.setup,
            operations=(TubeOperationDefinition("tube-bad", "other-setup"),),
        )
        wrong_operation_report = wrong_operation.validation_report()
        self.assertFalse(wrong_operation_report.setup_ready)
        self.assertTrue(wrong_operation_report.has_errors)
        self.assertIs(
            wrong_operation_report.state_for("operation"),
            NodeState.INVALID,
        )
        self.assertIn(
            "TUBE_OPERATION_SETUP_MISMATCH",
            {issue.code for issue in wrong_operation_report.issues},
        )
        controller.begin_placement_draft()
        controller.apply_placement_draft()
        self.assertTrue(controller.coordinates_valid)

        controller.select_machine(GENERIC_XYZAC_REFERENCE)
        self.assertIs(
            controller.validation_report().state_for("placement"),
            NodeState.DIRTY,
        )

    def test_draft_is_visible_in_state_and_blocks_project_serialisation(self) -> None:
        controller = TubeSetupController(cad_model())
        controller.begin_coordinate_draft(MODEL_CS_NODE)

        state = controller.state_json()
        self.assertTrue(state["has_drafts"])
        self.assertEqual(state["validation"]["node_states"]["model_cs"], "draft")
        with self.assertRaises(PendingDraftError) as raised:
            controller.to_json()
        self.assertEqual(raised.exception.nodes, ("model_cs",))

        controller.discard_all_drafts()
        json.dumps(controller.to_json())

    def test_apply_all_drafts_rolls_back_every_mutable_boundary_on_failure(
        self,
    ) -> None:
        controller = TubeSetupController(cad_model())
        controller.create_operation(operation_id="tube-1")
        controller.mark_saved()
        controller.begin_coordinate_draft(MODEL_CS_NODE)
        controller.set_numeric_origin(MODEL_CS_NODE, (0, 0, 0), confirmed=True)
        controller.set_numeric_direction(MODEL_CS_NODE, "z", (0, 0, 1), confirmed=True)
        controller.set_numeric_direction(MODEL_CS_NODE, "x", (1, 0, 0), confirmed=True)
        controller.begin_coordinate_draft(BUILD_CS_NODE)
        controller.set_numeric_origin(
            BUILD_CS_NODE,
            (0, 0, 0),
            input_frame="source",
            confirmed=True,
        )
        original_setup = controller.setup
        original_operations = controller.operations
        original_drafts = controller.state_json()["drafts"]
        original_modified = controller.is_modified

        with self.assertRaisesRegex(ValueError, "origin, Z, and X"):
            controller.apply_all_drafts()

        self.assertIs(controller.setup, original_setup)
        self.assertIs(controller.operations, original_operations)
        self.assertEqual(controller.state_json()["drafts"], original_drafts)
        self.assertEqual(controller.is_modified, original_modified)
        self.assertEqual(
            controller.draft_nodes,
            (BUILD_CS_NODE, MODEL_CS_NODE),
        )

    def test_outer_transaction_restores_drafts_and_cad_authority(self) -> None:
        controller = TubeSetupController(cad_model())
        controller.begin_coordinate_draft(MODEL_CS_NODE)
        before = controller.state_json()

        with self.assertRaisesRegex(OSError, "viewer commit failed"):
            with controller.draft_resolution_transaction("discard"):
                controller.update_cad_model(cad_model("b" * 64))
                raise OSError("viewer commit failed")

        self.assertEqual(controller.state_json(), before)
        self.assertEqual(controller.geometry_reference("solid-base").object_id, "solid-base")

    def test_apply_all_refreshes_placement_dependencies_after_build_commit(
        self,
    ) -> None:
        controller = TubeSetupController(cad_model())
        controller.confirm_assignments(("solid-base", "solid-tube"))
        controller.create_operation(operation_id="tube-1")
        apply_numeric_frame(controller, MODEL_CS_NODE, (0, 0, 0))
        apply_numeric_frame(controller, BUILD_CS_NODE, (0, 0, 0))
        controller.select_machine(CARTESIAN_REFERENCE)
        controller.begin_placement_draft(mount_datum_id="build_plate_mount")
        controller.apply_placement_draft()
        old_build_revision = controller.setup.build_coordinate_system.revision

        controller.begin_coordinate_draft(BUILD_CS_NODE)
        controller.set_numeric_origin(
            BUILD_CS_NODE,
            (5, 0, 0),
            input_frame="source",
            confirmed=True,
        )
        controller.begin_placement_draft()
        controller.set_placement_adjustment(LocalAdjustment.from_euler_xyz((1, 2, 3), (0, 0, 0)))
        stale_draft = controller.placement_draft()
        self.assertEqual(stale_draft.build_cs_revision, old_build_revision)

        observed: dict[str, object] = {}
        original_apply = TubeSetupController.apply_placement_draft

        def capture_dependencies(current: TubeSetupController) -> RigidTransform:
            draft = current.placement_draft()
            observed["build_cs_revision"] = draft.build_cs_revision
            observed["machine_content_hash"] = draft.machine_content_hash
            observed["placement_state"] = current.validation_report().state_for(PLACEMENT_NODE)
            return original_apply(current)

        with patch.object(
            TubeSetupController,
            "apply_placement_draft",
            new=capture_dependencies,
        ):
            controller.apply_all_drafts()

        build = controller.setup.build_coordinate_system
        machine = controller.setup.machine
        assert build is not None
        assert machine is not None
        self.assertEqual(build.revision, old_build_revision + 1)
        self.assertEqual(observed["build_cs_revision"], build.revision)
        self.assertEqual(observed["machine_content_hash"], machine.content_hash)
        self.assertIs(observed["placement_state"], NodeState.DRAFT)
        self.assertNotIn(PLACEMENT_NODE, controller.setup.dirty_nodes)
        self.assertIs(
            controller.validation_report().state_for(PLACEMENT_NODE),
            NodeState.VALID,
        )
        self.assertTrue(controller.coordinates_valid)
        self.assertEqual(controller.draft_nodes, ())


if __name__ == "__main__":
    unittest.main()
