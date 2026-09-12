from __future__ import annotations

from dataclasses import replace
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    LocalAdjustment,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.machine import CARTESIAN_REFERENCE
from five_axis_slicer.manufacturing.resources import (
    NozzleProfile,
    ResourceSnapshot,
    canonical_content_hash,
    get_builtin_material_profile,
)
from five_axis_slicer.manufacturing.setup import (
    BUILD_CS_NODE,
    MATERIAL_NODE,
    NOZZLE_NODE,
    ManufacturingObjectAssignments,
    ManufacturingSetup,
    NodeState,
    SetupValidationReport,
    TubeOperationDefinition,
)


def complete_nozzle() -> NozzleProfile:
    return NozzleProfile(
        resource_id="nozzle-060",
        display_name="Test nozzle",
        orifice_diameter_mm=0.6,
        filament_diameter_mm=1.75,
        interface="M6",
        length_mm=12.5,
        construction_material="brass",
        flow_category="standard",
        outer_profile_rz_mm=((0.3, 0.0), (3.0, 6.0), (4.0, 12.5)),
    )


def coordinate_frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        f"{frame_id.title()} CS",
        PointReference("numeric", (0, 0, 0), confirmed=True),
        DirectionReference("numeric", (0, 0, 1), confirmed=True),
        DirectionReference("numeric", (1, 0, 0), confirmed=True),
    )


def complete_setup(*, material_confirmed: bool = True) -> ManufacturingSetup:
    material = get_builtin_material_profile("PLA")
    if material_confirmed:
        material = material.reviewed_copy("generic-pla-reviewed")
    return ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(
            part_body_ids=("body-001", "body-002"),
            unassigned_body_ids=("sheet-001",),
        ),
        machine=ResourceSnapshot.capture("machine", CARTESIAN_REFERENCE),
        nozzle=ResourceSnapshot.capture("nozzle", complete_nozzle()),
        material=ResourceSnapshot.capture("material", material),
        model_coordinate_system=coordinate_frame("model"),
        build_coordinate_system=coordinate_frame("build"),
        mount_datum_id="build_plate_mount",
        placement_adjustment=LocalAdjustment.from_euler_xyz((1, 2, 3), (0, 0, 0)),
        T_mount_from_build=RigidTransform(
            RigidTransform.identity().matrix,
            source_frame="build",
            target_frame="build_plate_mount",
        ),
    )


class ManufacturingSetupTests(unittest.TestCase):
    def test_empty_setup_reports_all_required_nodes_missing(self) -> None:
        report = ManufacturingSetup().validation_report()

        self.assertFalse(report.coordinates_valid)
        self.assertFalse(report.setup_ready)
        self.assertTrue(report.has_errors)
        self.assertIs(report.state_for("part"), NodeState.MISSING)
        self.assertIs(report.state_for("model_cs"), NodeState.MISSING)
        self.assertIn("SETUP_PART_MISSING", {issue.code for issue in report.issues})

    def test_complete_setup_reaches_ready_with_reference_machine_warning(self) -> None:
        setup = complete_setup()
        report = setup.validation_report()

        self.assertTrue(report.coordinates_valid)
        self.assertTrue(report.setup_ready)
        self.assertFalse(report.has_errors)
        self.assertTrue(report.has_warnings)
        self.assertIn("MACHINE_REFERENCE_ONLY", {issue.code for issue in report.issues})

    def test_material_review_blocks_setup_but_not_coordinate_validity(self) -> None:
        report = complete_setup(material_confirmed=False).validation_report()

        self.assertTrue(report.coordinates_valid)
        self.assertFalse(report.setup_ready)
        self.assertIs(report.state_for(MATERIAL_NODE), NodeState.DRAFT)
        self.assertIn("MATERIAL_REVIEW_REQUIRED", {issue.code for issue in report.issues})

    def test_build_change_marks_placement_dirty_until_reapplied(self) -> None:
        setup = complete_setup().with_build_coordinate_system(coordinate_frame("build"))
        report = setup.validation_report()
        self.assertFalse(report.coordinates_valid)
        self.assertIs(report.state_for(BUILD_CS_NODE), NodeState.VALID)
        self.assertIs(report.state_for("placement"), NodeState.DIRTY)

        reapplied = setup.with_placement(
            "build_plate_mount",
            RigidTransform(
                RigidTransform.identity().matrix,
                source_frame="build",
                target_frame="build_plate_mount",
            ),
        )
        self.assertTrue(reapplied.coordinates_valid)

    def test_placement_frame_labels_are_part_of_validity(self) -> None:
        setup = complete_setup().with_placement(
            "build_plate_mount",
            RigidTransform(
                RigidTransform.identity().matrix,
                source_frame="machine",
                target_frame="build_plate_mount",
            ),
        )

        report = setup.validation_report()

        self.assertIs(report.state_for("placement"), NodeState.INVALID)
        self.assertFalse(report.coordinates_valid)
        self.assertIn("PLACEMENT_INVALID", {issue.code for issue in report.issues})

    def test_placement_mount_must_belong_to_selected_machine(self) -> None:
        setup = complete_setup().with_placement(
            "forged_mount",
            RigidTransform(
                RigidTransform.identity().matrix,
                source_frame="build",
                target_frame="forged_mount",
            ),
        )

        report = setup.validation_report()

        self.assertIs(report.state_for("placement"), NodeState.INVALID)
        self.assertFalse(report.coordinates_valid)
        self.assertFalse(report.setup_ready)
        self.assertTrue(report.has_errors)

    def test_model_and_build_slots_reject_swapped_frame_roles(self) -> None:
        setup = replace(
            complete_setup(),
            model_coordinate_system=coordinate_frame("build"),
            build_coordinate_system=coordinate_frame("model"),
        )

        report = setup.validation_report()

        self.assertIs(report.state_for("model_cs"), NodeState.INVALID)
        self.assertIs(report.state_for("build_cs"), NodeState.INVALID)
        self.assertFalse(report.coordinates_valid)
        issues = {issue.code: issue for issue in report.issues}
        self.assertEqual(
            issues["MODEL_CS_FRAME_ID_MISMATCH"].context["expected_frame_id"],
            "model",
        )
        self.assertEqual(
            issues["BUILD_CS_FRAME_ID_MISMATCH"].context["expected_frame_id"],
            "build",
        )

    def test_self_consistent_malformed_machine_snapshot_becomes_invalid(self) -> None:
        valid = ResourceSnapshot.capture("machine", CARTESIAN_REFERENCE)
        payload = valid.to_json()
        payload["payload"]["joints"] = {"unexpected": "mapping"}
        payload["content_hash"] = canonical_content_hash(
            {
                "resource_type": payload["resource_type"],
                "resource_id": payload["resource_id"],
                "profile_version": payload["profile_version"],
                "payload": payload["payload"],
            }
        )
        malformed = ResourceSnapshot.from_json(payload)
        setup = complete_setup().with_machine(malformed)

        report = setup.validation_report()

        self.assertIs(report.state_for("machine"), NodeState.INVALID)
        self.assertIs(report.state_for("placement"), NodeState.INVALID)
        self.assertFalse(report.coordinates_valid)
        self.assertFalse(report.setup_ready)

    def test_setup_and_report_json_round_trip(self) -> None:
        setup = complete_setup()
        payload = json.loads(json.dumps(setup.to_json()))
        restored = ManufacturingSetup.from_json(payload)

        self.assertEqual(restored.to_json(), payload)
        self.assertTrue(restored.setup_ready)
        report_payload = restored.validation_report().to_json()
        restored_report = SetupValidationReport.from_json(report_payload)
        self.assertEqual(restored_report.to_json(), report_payload)

    def test_legacy_inconsistent_nozzle_snapshot_fails_closed_after_round_trip(self) -> None:
        nozzle = replace(
            complete_nozzle(),
            outer_profile_rz_mm=((0.3, 0.0), (3.0, 12.0)),
        )
        setup = replace(
            complete_setup(),
            nozzle=ResourceSnapshot.capture("nozzle", nozzle),
        )

        restored = ManufacturingSetup.from_json(json.loads(json.dumps(setup.to_json())))
        report = restored.validation_report()

        self.assertIs(report.state_for(NOZZLE_NODE), NodeState.INVALID)
        self.assertFalse(report.setup_ready)
        self.assertIn("SETUP_NOZZLE_INVALID", {issue.code for issue in report.issues})

    def test_assignment_roles_must_be_disjoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "both part_body_ids and ignored_body_ids"):
            ManufacturingObjectAssignments(
                part_body_ids=("body-001",),
                ignored_body_ids=("body-001",),
            )

    def test_operation_round_trip_and_dirty_reason_deduplication(self) -> None:
        operation = TubeOperationDefinition("operation-1", "setup-1")
        operation = operation.mark_dirty("model_cs_changed").mark_dirty("model_cs_changed")

        self.assertEqual(operation.dirty_reasons, ("model_cs_changed",))
        restored = TubeOperationDefinition.from_json(operation.to_json())
        self.assertEqual(restored, operation)

    def test_json_boolean_fields_reject_truthy_substitutes_and_keep_defaults(
        self,
    ) -> None:
        operation_payload = TubeOperationDefinition("operation-1", "setup-1").to_json()
        operation_payload["enabled"] = "false"
        with self.assertRaisesRegex(TypeError, "must be a boolean"):
            TubeOperationDefinition.from_json(operation_payload)

        default_operation_payload = TubeOperationDefinition("operation-1", "setup-1").to_json()
        default_operation_payload.pop("enabled")
        self.assertTrue(TubeOperationDefinition.from_json(default_operation_payload).enabled)

        report_payload = complete_setup().validation_report().to_json()
        for field_name, forged_value in (
            ("coordinates_valid", "false"),
            ("setup_ready", 1),
        ):
            with self.subTest(field_name=field_name, forged_value=forged_value):
                forged = json.loads(json.dumps(report_payload))
                forged[field_name] = forged_value
                with self.assertRaisesRegex(TypeError, "must be a boolean"):
                    SetupValidationReport.from_json(forged)

        default_report_payload = json.loads(json.dumps(report_payload))
        default_report_payload.pop("coordinates_valid")
        default_report_payload.pop("setup_ready")
        restored_report = SetupValidationReport.from_json(default_report_payload)
        self.assertFalse(restored_report.coordinates_valid)
        self.assertFalse(restored_report.setup_ready)


if __name__ == "__main__":
    unittest.main()
