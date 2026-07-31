from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    LocalAdjustment,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.machine import CARTESIAN_REFERENCE  # noqa: E402
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    NozzleProfile,
    ResourceSnapshot,
    get_builtin_material_profile,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    ManufacturingObjectAssignments,
    ManufacturingSetup,
    TubeOperationDefinition,
)
from five_axis_slicer.setup_config import (  # noqa: E402
    MAX_CONFIG_BYTES,
    SetupConfigConflictError,
    SetupConfigError,
    atomic_write_setup_config,
    dump_setup_config,
    export_setup_config,
    load_setup_config,
    load_setup_config_file,
    schema_path,
    semantic_hash,
    setup_config_fingerprint,
)


def _frame(frame_id: str, *, geometry: bool = False) -> CoordinateFrameDefinition:
    if geometry:
        face = GeometryReference(
            "face-project-only",
            "face",
            signature={"surface_type": "plane"},
            parent_body_id="body-project-only",
        )
        origin = PointReference("face_centroid", (1, 2, 3), geometry=face, confirmed=True)
        z_axis = DirectionReference("plane_normal", (0, 0, 1), geometry=face, confirmed=True)
    else:
        origin = PointReference("numeric", (1, 2, 3), confirmed=True)
        z_axis = DirectionReference("numeric", (0, 0, 1), confirmed=True)
    return CoordinateFrameDefinition.from_references(
        frame_id,
        f"{frame_id.title()} CS",
        origin,
        z_axis,
        DirectionReference("numeric", (1, 0, 0.2), confirmed=True),
    )


def _setup() -> ManufacturingSetup:
    nozzle = NozzleProfile(
        resource_id="lab-nozzle-060",
        display_name="Lab nozzle",
        orifice_diameter_mm=0.6,
        filament_diameter_mm=1.75,
        interface="M6 x 1",
        length_mm=12.5,
        construction_material="brass",
        flow_category="standard",
        outer_profile_rz_mm=((0.3, 0.0), (3.0, 6.0), (4.0, 12.5)),
    )
    material = get_builtin_material_profile("PLA").reviewed_copy("reviewed-pla")
    adjustment = LocalAdjustment.from_euler_xyz(
        (1.0, 2.0, 3.0),
        (math.radians(5.0), math.radians(-7.0), math.radians(11.0)),
    )
    reference = RigidTransform.from_axis_angle(
        (0, 0, 1),
        math.radians(30.0),
        translation=(8, 9, 10),
        source_frame="build",
        target_frame="build_plate_mount",
    )
    return ManufacturingSetup(
        setup_id="project-setup-id",
        assignments=ManufacturingObjectAssignments(
            part_body_ids=("body-001", "body-002"),
            ignored_body_ids=("body-ignored",),
        ),
        machine=ResourceSnapshot.capture("machine", CARTESIAN_REFERENCE),
        nozzle=ResourceSnapshot.capture("nozzle", nozzle),
        material=ResourceSnapshot.capture("material", material),
        model_coordinate_system=_frame("model", geometry=True),
        build_coordinate_system=_frame("build"),
        mount_datum_id="build_plate_mount",
        placement_adjustment=adjustment,
        T_mount_from_build=adjustment.apply_to(reference),
        draft_nodes=frozenset({"nozzle"}),
    )


def _operation() -> TubeOperationDefinition:
    return TubeOperationDefinition(
        "project-operation-id",
        "project-setup-id",
        name="Tube sample",
    )


class SetupConfigRoundTripTests(unittest.TestCase):
    def test_export_is_portable_and_apply_preserves_project_identities(self) -> None:
        source_setup = _setup()
        config = export_setup_config(source_setup, (_operation(),))
        text = dump_setup_config(config)

        for excluded in (
            "body-001",
            "body-project-only",
            "project-setup-id",
            "project-operation-id",
            "draft_nodes",
            "issues",
        ):
            self.assertNotIn(excluded, text)
        coordinate_document = config.to_document()["setup"]["coordinate_systems"]
        self.assertNotIn("T_target_from_source", json.dumps(coordinate_document))
        self.assertIn("geometry_resolved: true", text)
        self.assertIn("content_hash:", text)

        loaded = load_setup_config(text)
        current = ManufacturingSetup(
            setup_id="current-setup",
            assignments=ManufacturingObjectAssignments(part_body_ids=("current-part",)),
        )
        current_operation = TubeOperationDefinition("current-operation", "current-setup")
        applied, operations = loaded.apply_to_domain(current, (current_operation,))

        self.assertEqual(applied.setup_id, "current-setup")
        self.assertEqual(applied.assignments.part_body_ids, ("current-part",))
        self.assertEqual(operations[0].operation_id, "current-operation")
        self.assertEqual(operations[0].setup_id, "current-setup")
        self.assertTrue(loaded.geometry_review_required)
        self.assertTrue(loaded.content_matches_metadata)
        self.assertTrue(applied.T_mount_from_build.almost_equal(source_setup.T_mount_from_build))
        self.assertEqual(applied.machine, source_setup.machine)

    def test_new_operation_requires_provider_owned_id(self) -> None:
        config = export_setup_config(_setup(), (_operation(),))
        current = ManufacturingSetup(
            setup_id="current",
            assignments=ManufacturingObjectAssignments(part_body_ids=("part",)),
        )

        with self.assertRaisesRegex(SetupConfigError, "new_operation_id"):
            config.apply_to_domain(current, ())
        _, operations = config.apply_to_domain(current, (), new_operation_id="generated-id")
        self.assertEqual(operations[0].operation_id, "generated-id")

    def test_comments_quotes_and_canonical_field_order_survive_update(self) -> None:
        config = export_setup_config(_setup(), (_operation(),))
        original = dump_setup_config(config)
        annotated = original.replace("setup:\n", "# operator note\nsetup:\n").replace(
            "name: Manufacturing Setup 1",
            'name: "Manufacturing Setup 1"',
            1,
        )

        updated = dump_setup_config(
            replace(config, setup_name="Calibrated Setup"),
            existing_text=annotated,
        )

        self.assertIn("# operator note", updated)
        self.assertIn('name: "Calibrated Setup"', updated)
        keys = (
            "format:",
            "schema_version:",
            "units:",
            "coordinate_convention:",
            "part_policy:",
            "metadata:",
            "setup:",
            "operations:",
        )
        positions = [updated.index(key) for key in keys]
        self.assertEqual(positions, sorted(positions))

    def test_semantic_hash_excludes_metadata_and_comments(self) -> None:
        text = dump_setup_config(export_setup_config(_setup(), (_operation(),)))
        config = load_setup_config(text)
        changed_metadata = config.to_document()
        changed_metadata["metadata"]["revision"] += 20
        changed_metadata["metadata"]["base_project_setup_sha256"] = "a" * 64

        self.assertEqual(semantic_hash(config), semantic_hash(changed_metadata))
        annotated = text.replace("setup:\n", "# review comment\nsetup:\n")
        self.assertEqual(load_setup_config(annotated).semantic_sha256, config.semantic_sha256)

    def test_external_semantic_edit_is_reported_as_metadata_divergence(self) -> None:
        text = dump_setup_config(export_setup_config(_setup()))
        edited = text.replace("name: Manufacturing Setup 1", "name: Externally Edited")

        loaded = load_setup_config(edited)

        self.assertEqual(loaded.setup_name, "Externally Edited")
        self.assertFalse(loaded.content_matches_metadata)


class SetupConfigSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = dump_setup_config(export_setup_config(ManufacturingSetup()))

    def assertRejected(self, text: str | bytes, expected: str) -> None:
        with self.assertRaisesRegex(SetupConfigError, expected):
            load_setup_config(text)

    def test_rejects_duplicate_keys_tags_anchors_aliases_and_merge_keys(self) -> None:
        self.assertRejected(self.text + "format: duplicate\n", "duplicate key")
        self.assertRejected(
            self.text.replace("name: Manufacturing Setup 1", "name: !unsafe value"),
            "YAML tags",
        )
        self.assertRejected(
            "!!python/object/apply:os.system\n" + self.text,
            "explicit YAML tags",
        )
        self.assertRejected(
            self.text.replace("operations: []", "operations: !!python/object/apply:os.system []"),
            "explicit YAML tags",
        )
        self.assertRejected(
            self.text.replace(
                "format: five-axis-slicer.manufacturing-setup",
                "format: &shared five-axis-slicer.manufacturing-setup",
            ),
            "anchors",
        )
        self.assertRejected(
            self.text.replace(
                "coordinate_convention: source_mm_right_handed_column_vector",
                "coordinate_convention: *shared",
            ),
            "aliases",
        )
        merged = self.text.replace("metadata:\n  revision: 1", "metadata:\n  <<: {revision: 1}")
        self.assertRejected(merged, "merge keys")

    def test_rejects_nonfinite_values_unknown_fields_and_newer_versions(self) -> None:
        self.assertRejected(self.text.replace("revision: 1", "revision: .nan", 1), "NaN")
        self.assertRejected(self.text + "unknown: true\n", "Additional properties")
        future = self.text.replace("schema_version: 1", "schema_version: 2", 1)
        with self.assertRaises(SetupConfigError) as caught:
            load_setup_config(future)
        self.assertEqual(caught.exception.code, "E_CONFIG_VERSION")

    def test_rejects_resource_payload_unknown_fields_even_with_valid_snapshot_hash(self) -> None:
        document = export_setup_config(_setup()).to_document()
        machine = document["setup"]["resources"]["machine"]
        machine["payload"]["unknown_field"] = "forged"
        hash_content = {
            "resource_type": machine["resource_type"],
            "resource_id": machine["resource_id"],
            "profile_version": machine["profile_version"],
            "payload": machine["payload"],
        }
        from five_axis_slicer.manufacturing.resources import canonical_content_hash

        machine["content_hash"] = canonical_content_hash(hash_content)
        document["metadata"]["content_sha256"] = semantic_hash(document)

        with self.assertRaisesRegex(SetupConfigError, "unknown fields"):
            dump_setup_config(document)

    def test_enforces_size_depth_node_and_operation_limits(self) -> None:
        self.assertRejected(b"x" * (MAX_CONFIG_BYTES + 1), "2 MiB")
        self.assertRejected("root: " + "[" * 33 + "0" + "]" * 33, "nesting")
        self.assertRejected("\n".join("- 0" for _ in range(50_001)), "50000 nodes")
        document = export_setup_config(_setup(), (_operation(),)).to_document()
        document["operations"].append(dict(document["operations"][0]))
        with self.assertRaisesRegex(SetupConfigError, "too long"):
            dump_setup_config(document)

    def test_public_schema_uses_json_schema_2020_12(self) -> None:
        schema = json.loads(schema_path().read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])


class SetupConfigStorageTests(unittest.TestCase):
    def test_file_reader_rejects_symbolic_links(self) -> None:
        text = dump_setup_config(export_setup_config(ManufacturingSetup()))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.yaml"
            link = Path(directory) / "manufacturing-setup.yaml"
            target.write_text(text, encoding="utf-8")
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"file symlink unavailable: {exc}")

            with self.assertRaisesRegex(SetupConfigError, "link"):
                load_setup_config_file(link)

    def test_atomic_write_normalises_lf_and_honours_expected_fingerprint(self) -> None:
        initial = dump_setup_config(export_setup_config(ManufacturingSetup()))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "manufacturing-setup.yaml"
            first = atomic_write_setup_config(
                target,
                initial.replace("\n", "\r\n"),
                expect_missing=True,
            )
            self.assertEqual(first, setup_config_fingerprint(target))
            self.assertNotIn(b"\r\n", target.read_bytes())

            updated_config = replace(load_setup_config(initial), revision=2)
            updated = dump_setup_config(updated_config)
            second = atomic_write_setup_config(
                target,
                updated,
                expected_fingerprint=first,
            )
            self.assertNotEqual(first, second)
            with self.assertRaises(SetupConfigConflictError):
                atomic_write_setup_config(
                    target,
                    initial,
                    expected_fingerprint=first,
                )
            with self.assertRaises(SetupConfigConflictError):
                atomic_write_setup_config(target, initial, expect_missing=True)

    def test_expect_missing_detects_a_file_created_during_staging(self) -> None:
        text = dump_setup_config(export_setup_config(ManufacturingSetup()))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "manufacturing-setup.yaml"

            def competing_write(_: int) -> None:
                target.write_text("competing writer\n", encoding="utf-8")

            with mock.patch(
                "five_axis_slicer.setup_config_io.os.fsync",
                side_effect=competing_write,
            ):
                with self.assertRaises(SetupConfigConflictError):
                    atomic_write_setup_config(target, text, expect_missing=True)
            self.assertEqual(target.read_text(encoding="utf-8"), "competing writer\n")

    def test_atomic_write_rejects_stale_declared_semantic_hash(self) -> None:
        text = dump_setup_config(export_setup_config(ManufacturingSetup()))
        stale = text.replace("name: Manufacturing Setup 1", "name: stale")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "manufacturing-setup.yaml"
            with self.assertRaisesRegex(SetupConfigError, "content_sha256"):
                atomic_write_setup_config(target, stale)
            self.assertFalse(target.exists())

    def test_directory_sync_failure_does_not_report_a_replaced_file_as_uncommitted(self) -> None:
        text = dump_setup_config(export_setup_config(ManufacturingSetup()))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "manufacturing-setup.yaml"
            with (
                mock.patch(
                    "five_axis_slicer.setup_config_io._sync_directory",
                    side_effect=OSError("durability unavailable"),
                ),
                self.assertLogs("five_axis_slicer.setup_config_io", level="WARNING"),
            ):
                fingerprint = atomic_write_setup_config(target, text, expect_missing=True)

            self.assertEqual(fingerprint, setup_config_fingerprint(target))
            self.assertEqual(
                load_setup_config(target.read_bytes()).setup_name, "Manufacturing Setup 1"
            )


if __name__ == "__main__":
    unittest.main()
