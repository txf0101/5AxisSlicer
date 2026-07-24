from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from five_axis_slicer import project_io
from five_axis_slicer.gcode_preview import PreviewSettings, load_gcode, parse_gcode
from five_axis_slicer.manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
)
from five_axis_slicer.manufacturing.machine import (
    CARTESIAN_REFERENCE,
    GENERIC_XYZAC_REFERENCE,
)
from five_axis_slicer.manufacturing.preview_kinematics import (
    GENERIC_XYZAC_AC_SEMANTICS,
)
from five_axis_slicer.manufacturing.resources import (
    ResourceSnapshot,
    canonical_content_hash,
)
from five_axis_slicer.manufacturing.references import geometry_reference
from five_axis_slicer.manufacturing.setup import (
    BUILD_CS_NODE,
    MODEL_CS_NODE,
    ManufacturingSetup,
    NodeState,
    TubeOperationDefinition,
)
from five_axis_slicer.models import CadModel, CadUnitInfo, SelectionState
from five_axis_slicer.project_io import (
    PROJECT_VERSION,
    ProjectFormatError,
    ProjectIntegrityError,
    UnsupportedProjectVersionError,
    load_project,
    save_project,
)
from five_axis_slicer.step_loader import file_sha256, load_step
from five_axis_slicer.tube_controller import TubeSetupController
from test_step_loader import make_two_body_step


class ProjectIoTests(unittest.TestCase):
    def test_saves_v2_project_json_and_authoritative_source_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path = make_two_body_step(root)
            model = load_step(step_path)
            selection = SelectionState(mode="edge")
            selection.body_ids.add("body_001")
            selection.edge_ids.add(model.bodies[0].edge_ids[0])

            project_json = save_project(root / "project", model, selection)
            payload = json.loads(project_json.read_text(encoding="utf-8"))

            embedded = root / "project" / payload["source"]["project_path"]
            self.assertTrue(embedded.exists())
            self.assertEqual(
                embedded.name,
                f"{payload['source']['sha256']}{step_path.suffix}",
            )
            self.assertEqual(payload["version"], PROJECT_VERSION)
            self.assertEqual(payload["model"]["body_count"], 2)
            self.assertGreater(payload["model"]["face_count"], 0)
            self.assertEqual(payload["selection"]["mode"], "edge")
            self.assertEqual(payload["setups"], [])
            self.assertEqual(payload["operations"], [])
            self.assertEqual(payload["resources"], {})
            self.assertIn("created_at", payload)
            self.assertIn("updated_at", payload)

    def test_saves_workbench_and_gcode_preview_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path = make_two_body_step(root)
            gcode_path = root / "demo.gcode"
            gcode_path.write_text(";TYPE:Outer wall\nG1 X1 Y0 E1\n", encoding="utf-8")
            model = load_step(step_path)
            preview = load_gcode(gcode_path)
            settings = PreviewSettings(layer_min=0, layer_max=0, show_travel=False)

            project_json = save_project(
                root / "project",
                model,
                SelectionState(),
                {"workbench": "curve", "operation": "imported_nc_review"},
                preview,
                settings,
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))

            self.assertEqual(payload["workbench"]["workbench"], "curve")
            self.assertEqual(payload["gcode"]["summary"]["segment_count"], 1)
            self.assertEqual(len(payload["gcode"]["sha256"]), 64)
            self.assertEqual(
                Path(payload["gcode"]["project_path"]).name,
                f"{payload['gcode']['sha256']}{gcode_path.suffix}",
            )
            self.assertFalse(payload["preview"]["gcode"]["show_travel"])

    def test_load_restores_embedded_gcode_and_controller_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gcode_path = root / "indexed-ac.gcode"
            gcode_path.write_text(
                "G1 X0 Y0 Z0.2\nG1 X1 Y0 Z0.2 A70.513 C15 E0.4\n",
                encoding="utf-8",
            )
            preview = load_gcode(
                gcode_path,
                controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
            )
            project_json = save_project(
                root / "project",
                None,
                SelectionState(),
                {"workbench": "curve"},
                preview,
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            embedded = project_json.parent / payload["gcode"]["project_path"]
            gcode_path.unlink()

            loaded = load_project(project_json)

            self.assertIsNotNone(loaded.gcode_preview)
            assert loaded.gcode_preview is not None
            self.assertEqual(loaded.gcode_preview.source_path, embedded.resolve())
            self.assertEqual(
                loaded.gcode_preview.controller_semantics,
                GENERIC_XYZAC_AC_SEMANTICS,
            )
            self.assertEqual(
                loaded.gcode_preview.summary()["controller_semantics"],
                payload["gcode"]["summary"]["controller_semantics"],
            )
            self.assertIsNotNone(loaded.gcode_preview.source_fingerprint)
            assert loaded.gcode_preview.source_fingerprint is not None
            self.assertEqual(
                loaded.gcode_preview.source_fingerprint.to_json(),
                payload["gcode"]["source_fingerprint"],
            )

    def test_old_gcode_manifest_without_fingerprint_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gcode_path = root / "legacy.gcode"
            gcode_path.write_text("G1 X1 Y0 E0.2\n", encoding="utf-8")
            project_json = save_project(
                root / "project",
                None,
                SelectionState(),
                gcode_preview=load_gcode(gcode_path),
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            payload["gcode"].pop("source_fingerprint")
            project_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            loaded = load_project(project_json)

            self.assertIsNotNone(loaded.gcode_preview)
            assert loaded.gcode_preview is not None
            self.assertIsNotNone(loaded.gcode_preview.source_fingerprint)
            assert loaded.gcode_preview.source_fingerprint is not None
            self.assertEqual(
                loaded.gcode_preview.source_fingerprint.sha256,
                payload["gcode"]["sha256"],
            )

    def test_embedded_gcode_mtime_change_does_not_break_portable_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gcode_path = root / "portable.gcode"
            gcode_path.write_text("G1 X1 Y0 E0.2\n", encoding="utf-8")
            project_json = save_project(
                root / "project",
                None,
                SelectionState(),
                gcode_preview=load_gcode(gcode_path),
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            embedded = project_json.parent / payload["gcode"]["project_path"]
            original_mtime = payload["gcode"]["source_fingerprint"]["mtime_ns"]
            stat = embedded.stat()
            os.utime(
                embedded,
                ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000),
            )

            loaded = load_project(project_json)

            self.assertIsNotNone(loaded.gcode_preview)
            assert loaded.gcode_preview is not None
            self.assertIsNotNone(loaded.gcode_preview.source_fingerprint)
            assert loaded.gcode_preview.source_fingerprint is not None
            self.assertNotEqual(
                loaded.gcode_preview.source_fingerprint.mtime_ns,
                original_mtime,
            )
            self.assertEqual(
                loaded.gcode_preview.source_fingerprint.sha256,
                payload["gcode"]["sha256"],
            )

    def test_save_requires_loaded_gcode_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gcode_path = root / "direct.gcode"
            gcode_path.write_text("G1 X1 Y0 E0.2\n", encoding="utf-8")
            preview = parse_gcode(
                gcode_path.read_text(encoding="utf-8"),
                gcode_path,
            )

            self.assertIsNone(preview.source_fingerprint)
            with self.assertRaisesRegex(ProjectIntegrityError, "fingerprint"):
                save_project(
                    root / "project",
                    None,
                    SelectionState(),
                    gcode_preview=preview,
                )

    def test_changed_gcode_source_cannot_replace_saved_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gcode_path = root / "mutable.gcode"
            gcode_path.write_text("G1 X1 Y0 E0.2\n", encoding="utf-8")
            preview = load_gcode(gcode_path)
            project_json = save_project(
                root / "project",
                None,
                SelectionState(),
                gcode_preview=preview,
            )
            manifest_before = project_json.read_bytes()
            payload = json.loads(manifest_before)
            embedded = project_json.parent / payload["gcode"]["project_path"]
            embedded_before = embedded.read_bytes()

            gcode_path.write_text("G1 X9 Y0 E0.9\n", encoding="utf-8")
            with self.assertRaisesRegex(ProjectIntegrityError, "changed"):
                save_project(
                    project_json.parent,
                    None,
                    SelectionState(),
                    gcode_preview=preview,
                )

            self.assertEqual(project_json.read_bytes(), manifest_before)
            self.assertEqual(embedded.read_bytes(), embedded_before)
            self.assertIsNotNone(load_project(project_json).gcode_preview)

    def test_load_uses_embedded_step_after_original_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = make_two_body_step(root)
            model = load_step(original)
            selection = SelectionState(
                mode="face",
                body_ids={"body_001"},
                face_ids={model.bodies[0].face_ids[0]},
            )
            project_json = save_project(
                root / "project",
                model,
                selection,
                {"workbench": "tube"},
            )
            original.unlink()

            loaded = load_project(project_json)

            self.assertIsNotNone(loaded.model)
            assert loaded.model is not None
            self.assertEqual(len(loaded.model.bodies), 2)
            self.assertEqual(loaded.model.source_path.parent.name, "source")
            self.assertEqual(loaded.selection.face_ids, selection.face_ids)
            self.assertEqual(loaded.workbench, {"workbench": "tube"})
            self.assertFalse(loaded.migrated_from_v1)

    def test_v2_topology_identity_round_trip_matches_embedded_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = load_step(make_two_body_step(root))
            project_json = save_project(root / "project", model, SelectionState())

            loaded = load_project(project_json)

            assert loaded.model is not None
            for collection_name, identifier_attribute in (
                ("bodies", "body_id"),
                ("faces", "face_id"),
                ("edges", "edge_id"),
                ("vertices", "vertex_id"),
            ):
                expected = {
                    getattr(item, identifier_attribute): item.signature
                    for item in getattr(model, collection_name)
                }
                actual = {
                    getattr(item, identifier_attribute): item.signature
                    for item in getattr(loaded.model, collection_name)
                }
                self.assertEqual(actual, expected)

    def test_v2_rejects_tampered_topology_ids_signatures_and_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = load_step(make_two_body_step(root))
            project_json = save_project(root / "project", model, SelectionState())
            baseline = json.loads(project_json.read_text(encoding="utf-8"))

            for collection_name in ("bodies", "faces", "edges", "vertices"):
                for field_name in ("id", "signature"):
                    with self.subTest(
                        collection=collection_name,
                        field=field_name,
                    ):
                        tampered = json.loads(json.dumps(baseline))
                        if field_name == "id":
                            tampered["model"][collection_name][0]["id"] += "_changed"
                        else:
                            original = tampered["model"][collection_name][0][
                                "signature"
                            ]
                            tampered["model"][collection_name][0]["signature"] = (
                                "0" * 64 if original != "0" * 64 else "1" * 64
                            )
                        project_json.write_text(
                            json.dumps(tampered, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                        with (
                            patch(
                                "five_axis_slicer.project_io.load_step",
                                return_value=model,
                            ),
                            self.assertRaisesRegex(
                                ProjectIntegrityError,
                                collection_name,
                            ),
                        ):
                            load_project(project_json)

            for collection_name, count_name in (
                ("bodies", "body_count"),
                ("faces", "face_count"),
                ("edges", "edge_count"),
                ("vertices", "vertex_count"),
            ):
                with self.subTest(collection=collection_name, field=count_name):
                    tampered = json.loads(json.dumps(baseline))
                    tampered["model"][count_name] += 1
                    project_json.write_text(
                        json.dumps(tampered, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    with (
                        patch(
                            "five_axis_slicer.project_io.load_step",
                            return_value=model,
                        ),
                        self.assertRaisesRegex(
                            ProjectIntegrityError,
                            collection_name,
                        ),
                    ):
                        load_project(project_json)

    def test_resave_preserves_external_source_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = make_two_body_step(root)
            model = load_step(original)
            project_json = save_project(root / "project", model, SelectionState())
            loaded = load_project(project_json)
            assert loaded.model is not None

            save_project(
                project_json.parent,
                loaded.model,
                loaded.selection,
                original_source_path=original,
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))

            self.assertEqual(
                Path(payload["source"]["original_path"]),
                original.resolve(),
            )
            self.assertEqual(
                loaded.model.source_path,
                project_json.parent / payload["source"]["project_path"],
            )

    def test_setup_operation_and_resource_snapshot_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = load_step(make_two_body_step(root))
            machine = ResourceSnapshot.capture("machine", CARTESIAN_REFERENCE)
            setup = ManufacturingSetup().with_machine(machine)
            operation = TubeOperationDefinition("tube-op-1", setup.setup_id)

            project_json = save_project(
                root / "project",
                model,
                SelectionState(),
                setup=setup,
                operations=(operation,),
                resources={"machine": machine},
            )
            loaded = load_project(project_json)

            self.assertIsInstance(loaded.setup, ManufacturingSetup)
            self.assertEqual(loaded.setup, setup)
            self.assertEqual(loaded.operations, (operation,))
            self.assertIsInstance(loaded.resources["machine"], ResourceSnapshot)
            self.assertTrue(loaded.resources["machine"].verify())

    def test_conflicting_setup_and_top_level_resource_snapshots_are_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            machine = ResourceSnapshot.capture("machine", CARTESIAN_REFERENCE)
            setup = ManufacturingSetup().with_machine(machine)
            project_json = save_project(
                root / "project",
                None,
                SelectionState(),
                setup=setup,
                resources={"machine": machine},
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            payload["resources"]["machine"]["content_hash"] = "0" * 64
            project_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ProjectIntegrityError, "diverges"):
                load_project(project_json)

        divergent = ResourceSnapshot.capture("machine", GENERIC_XYZAC_REFERENCE)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ProjectIntegrityError, "diverges"):
                save_project(
                    Path(tmp) / "project",
                    None,
                    SelectionState(),
                    setup=setup,
                    resources={"machine": divergent},
                )

    def test_hash_consistent_malformed_machine_snapshot_loads_as_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            machine = ResourceSnapshot.capture("machine", CARTESIAN_REFERENCE)
            setup = ManufacturingSetup().with_machine(machine)
            project_json = save_project(
                root / "project",
                None,
                SelectionState(),
                setup=setup,
                resources={"machine": machine},
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            snapshots = (
                payload["setups"][0]["resources"]["machine"],
                payload["resources"]["machine"],
            )
            for snapshot in snapshots:
                snapshot["payload"]["joints"] = {"unexpected": "mapping"}
                snapshot["content_hash"] = canonical_content_hash(
                    {
                        "resource_type": snapshot["resource_type"],
                        "resource_id": snapshot["resource_id"],
                        "profile_version": snapshot["profile_version"],
                        "payload": snapshot["payload"],
                    }
                )
            project_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            loaded = load_project(project_json)

            self.assertIsInstance(loaded.setup, ManufacturingSetup)
            report = loaded.setup.validation_report()
            self.assertIs(report.state_for("machine"), NodeState.INVALID)
            self.assertFalse(report.setup_ready)

    def test_tampered_embedded_step_is_rejected_before_cad_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = load_step(make_two_body_step(root))
            project_json = save_project(root / "project", model, SelectionState())
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            embedded = project_json.parent / payload["source"]["project_path"]
            with embedded.open("ab") as stream:
                stream.write(b"tampered")

            with self.assertRaisesRegex(ProjectIntegrityError, "hash mismatch"):
                load_project(project_json)

    def test_tampered_resource_snapshot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            machine = ResourceSnapshot.capture("machine", CARTESIAN_REFERENCE)
            project_json = save_project(
                root / "project",
                None,
                SelectionState(),
                resources={"machine": machine},
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            payload["resources"]["machine"]["payload"]["name"] = "Tampered"
            project_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ProjectIntegrityError, "resource snapshot"):
                load_project(project_json)

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = load_step(make_two_body_step(root))
            project_json = save_project(root / "project", model, SelectionState())
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            payload["source"]["project_path"] = "../two_boxes.step"
            project_json.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ProjectIntegrityError, "escapes"):
                load_project(project_json)

    def test_v1_load_migrates_in_memory_and_first_v2_save_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = load_step(make_two_body_step(root))
            project_json = save_project(root / "project", model, SelectionState())
            original_payload = json.loads(project_json.read_text(encoding="utf-8"))
            original_payload["version"] = 1
            original_payload.pop("setups")
            original_payload.pop("operations")
            original_payload.pop("resources")
            original_payload["model"].pop("face_count")
            original_payload["model"].pop("vertex_count")
            original_payload["model"].pop("faces")
            original_payload["model"].pop("vertices")
            for collection_name in ("bodies", "edges"):
                for item in original_payload["model"][collection_name]:
                    item.pop("signature")
            project_json.write_text(
                json.dumps(original_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            loaded = load_project(project_json)

            self.assertTrue(loaded.migrated_from_v1)
            self.assertEqual(loaded.payload["version"], PROJECT_VERSION)
            self.assertEqual(len(loaded.setups), 1)
            self.assertIsInstance(loaded.setup, ManufacturingSetup)
            self.assertFalse(loaded.setup.coordinates_valid)
            on_disk = json.loads(project_json.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["version"], 1)
            assert loaded.model is not None

            save_project(
                project_json.parent,
                loaded.model,
                loaded.selection,
                loaded.workbench,
                setups=loaded.setups,
                operations=loaded.operations,
                resources=loaded.resources,
            )

            backup = project_json.parent / "project.v1.json"
            self.assertTrue(backup.exists())
            backup_payload = json.loads(backup.read_text(encoding="utf-8"))
            saved_payload = json.loads(project_json.read_text(encoding="utf-8"))
            self.assertEqual(backup_payload["version"], 1)
            self.assertEqual(saved_payload["version"], PROJECT_VERSION)
            self.assertEqual(
                saved_payload["created_at"], original_payload["created_at"]
            )

    def test_future_version_and_corrupt_json_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_json = root / "project.json"
            project_json.write_text('{"version": 999}', encoding="utf-8")
            with self.assertRaises(UnsupportedProjectVersionError):
                load_project(project_json)

            project_json.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ProjectFormatError):
                load_project(project_json)

    def test_atomic_save_preserves_created_at_and_leaves_no_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "project"
            project_json = save_project(project_dir, None, SelectionState())
            first = json.loads(project_json.read_text(encoding="utf-8"))

            save_project(
                project_dir,
                None,
                SelectionState(),
                {"workbench": "tube"},
            )
            second = json.loads(project_json.read_text(encoding="utf-8"))

            self.assertEqual(second["created_at"], first["created_at"])
            self.assertEqual(second["workbench"], {"workbench": "tube"})
            self.assertEqual(list(project_dir.glob(".project.json.*.tmp")), [])

    def test_failed_resave_keeps_previous_manifest_and_embedded_files_loadable(
        self,
    ) -> None:
        for failure_mode in ("serialization", "json_write"):
            with (
                self.subTest(failure_mode=failure_mode),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                old_dir = root / "old"
                new_dir = root / "new"
                old_dir.mkdir()
                new_dir.mkdir()
                old_step = make_two_body_step(old_dir)
                old_model = load_step(old_step)
                old_gcode = old_dir / "toolpath.gcode"
                old_gcode.write_text("G1 X1 Y0 E1\n", encoding="utf-8")
                old_preview = load_gcode(old_gcode)
                project_json = save_project(
                    root / "project",
                    old_model,
                    SelectionState(),
                    {"generation": "old"},
                    old_preview,
                )
                manifest_before = project_json.read_bytes()
                old_payload = json.loads(manifest_before)
                old_embedded_step = (
                    project_json.parent / old_payload["source"]["project_path"]
                )
                old_embedded_gcode = (
                    project_json.parent / old_payload["gcode"]["project_path"]
                )
                old_step_bytes = old_embedded_step.read_bytes()
                old_gcode_bytes = old_embedded_gcode.read_bytes()

                new_step = new_dir / old_step.name
                new_step.write_bytes(old_step.read_bytes() + b"\n")
                new_model = load_step(new_step)
                new_gcode = new_dir / old_gcode.name
                new_gcode.write_text("G1 X2 Y0 E2\n", encoding="utf-8")
                new_preview = load_gcode(new_gcode)
                save_arguments = (
                    project_json.parent,
                    new_model,
                    SelectionState(),
                    {"generation": "new"},
                    new_preview,
                )

                if failure_mode == "serialization":
                    with self.assertRaises(TypeError):
                        save_project(
                            *save_arguments,
                            resources={"unsupported": object()},
                        )
                else:
                    with (
                        patch(
                            "five_axis_slicer.project_io._atomic_write_json",
                            side_effect=OSError("simulated manifest write failure"),
                        ),
                        self.assertRaisesRegex(OSError, "simulated"),
                    ):
                        save_project(*save_arguments)

                self.assertEqual(project_json.read_bytes(), manifest_before)
                self.assertEqual(old_embedded_step.read_bytes(), old_step_bytes)
                self.assertEqual(old_embedded_gcode.read_bytes(), old_gcode_bytes)
                loaded = load_project(project_json)
                self.assertEqual(loaded.workbench, {"generation": "old"})
                assert loaded.model is not None
                self.assertEqual(loaded.model.source_hash, old_model.source_hash)

    def test_staged_content_address_copy_preserves_authoritative_file_on_race(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path = make_two_body_step(root)
            model = load_step(step_path)
            project_json = save_project(root / "project", model, SelectionState())
            manifest_before = project_json.read_bytes()
            payload = json.loads(manifest_before)
            embedded = project_json.parent / payload["source"]["project_path"]
            embedded_before = embedded.read_bytes()
            source_before = step_path.read_bytes()
            real_hash = project_io.file_sha256
            real_copy = shutil.copy2
            embedded_hash_calls = 0

            def force_staging(path, *args, **kwargs):
                nonlocal embedded_hash_calls
                candidate = Path(path).resolve()
                if candidate == embedded.resolve() and embedded_hash_calls == 0:
                    embedded_hash_calls += 1
                    return "0" * 64
                return real_hash(path, *args, **kwargs)

            def mutate_during_copy(source, destination, *args, **kwargs):
                step_path.write_bytes(source_before + b"\n/* changed during copy */\n")
                return real_copy(source, destination, *args, **kwargs)

            with (
                patch.object(project_io, "file_sha256", side_effect=force_staging),
                patch.object(
                    project_io.shutil,
                    "copy2",
                    side_effect=mutate_during_copy,
                ),
                self.assertRaisesRegex(ProjectIntegrityError, "staged"),
            ):
                save_project(project_json.parent, model, SelectionState())

            self.assertEqual(project_json.read_bytes(), manifest_before)
            self.assertEqual(embedded.read_bytes(), embedded_before)
            self.assertIsNotNone(load_project(project_json).model)

    def test_atomic_copy_reuses_valid_content_addressed_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.bin"
            destination = root / "destination.bin"
            source.write_bytes(b"stable-content")
            destination.write_bytes(source.read_bytes())
            digest = project_io.file_sha256(source)

            with patch.object(project_io.shutil, "copy2") as copy_mock:
                project_io._atomic_copy(
                    source,
                    destination,
                    expected_sha256=digest,
                )

            copy_mock.assert_not_called()
            self.assertEqual(destination.read_bytes(), b"stable-content")

    def test_content_addressed_symlink_target_outside_project_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path = make_two_body_step(root)
            model = load_step(step_path)
            project_dir = root / "project"
            source_dir = project_dir / "source"
            source_dir.mkdir(parents=True)
            external = root / "outside.step"
            external.write_bytes(b"outside-must-stay-unchanged")
            target = source_dir / f"{model.source_hash}{step_path.suffix}"
            try:
                target.symlink_to(external)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"file symlink unavailable: {exc}")

            with self.assertRaisesRegex(
                ProjectIntegrityError,
                "link or reparse point",
            ):
                save_project(project_dir, model, SelectionState())

            self.assertEqual(external.read_bytes(), b"outside-must-stay-unchanged")
            self.assertTrue(target.is_symlink())
            self.assertFalse((project_dir / "project.json").exists())

    def test_project_source_directory_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "project"
            project_dir.mkdir()
            external_source = root / "outside-source"
            external_source.mkdir()
            source_link = project_dir / "source"
            try:
                source_link.symlink_to(external_source, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")

            with self.assertRaisesRegex(
                ProjectIntegrityError,
                "link or reparse point",
            ):
                save_project(project_dir, None, SelectionState())

            self.assertEqual(list(external_source.iterdir()), [])
            self.assertFalse((project_dir / "project.json").exists())

    def test_v2_setup_without_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_json = save_project(
                Path(tmp) / "project",
                None,
                SelectionState(),
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            payload["setups"] = [{"name": "opaque setup"}]
            project_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFormatError):
                load_project(project_json)

    def test_save_rejects_setup_with_uncommitted_draft_nodes(self) -> None:
        setup = ManufacturingSetup(draft_nodes=frozenset({MODEL_CS_NODE}))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ProjectFormatError, "draft_nodes"):
                save_project(
                    Path(tmp) / "project",
                    None,
                    SelectionState(),
                    setup=setup,
                )

    def test_load_rejects_persisted_setup_draft_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_json = save_project(
                Path(tmp) / "project",
                None,
                SelectionState(),
                setup=ManufacturingSetup(),
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            payload["setups"][0]["draft_nodes"] = [MODEL_CS_NODE]
            project_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ProjectFormatError, "draft_nodes"):
                load_project(project_json)

    def test_v2_unknown_operation_type_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_json = save_project(
                Path(tmp) / "project",
                None,
                SelectionState(),
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            payload["operations"] = [
                {
                    "operation_id": "future-op",
                    "setup_id": "setup-1",
                    "operation_type": "future_operation",
                }
            ]
            project_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaises(ProjectFormatError):
                load_project(project_json)

    def test_v2_duplicate_operation_ids_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            operation = TubeOperationDefinition("duplicate-op", "setup-1")
            project_json = save_project(
                Path(tmp) / "project",
                None,
                SelectionState(),
                operations=(operation, operation),
            )

            with self.assertRaisesRegex(ProjectFormatError, "manufacturing state"):
                load_project(project_json)

    def test_unknown_step_unit_override_is_persisted_for_embedded_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "unknown-unit.step"
            source.write_bytes(b"ISO-10303-21;\nEND-ISO-10303-21;\n")
            source_hash = file_sha256(source)
            overridden_units = CadUnitInfo(
                source_length_unit="inch",
                scale_to_mm=25.4,
                override_applied=True,
            )
            model = CadModel(
                source_path=source,
                source_hash=source_hash,
                bodies=[],
                edges=[],
                shapes={},
                edge_shapes={},
                units=overridden_units,
                source_size_bytes=source.stat().st_size,
                source_mtime_ns=source.stat().st_mtime_ns,
            )
            project_json = save_project(root / "project", model, SelectionState())
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            self.assertTrue(payload["model"]["units"]["override_applied"])
            self.assertEqual(payload["model"]["units"]["source_length_unit"], "inch")

            observed: dict[str, object] = {}

            def reopen_unknown_step(
                embedded: Path,
                *,
                length_unit_override: str | None,
                cancel_check,
            ) -> CadModel:
                observed["override"] = length_unit_override
                observed["cancel_check"] = cancel_check
                stat = embedded.stat()
                return CadModel(
                    source_path=embedded,
                    source_hash=file_sha256(embedded),
                    bodies=[],
                    edges=[],
                    shapes={},
                    edge_shapes={},
                    units=overridden_units,
                    source_size_bytes=stat.st_size,
                    source_mtime_ns=stat.st_mtime_ns,
                )

            with patch(
                "five_axis_slicer.project_io.load_step",
                side_effect=reopen_unknown_step,
            ):
                loaded = load_project(project_json, cancel_check=lambda: False)

            self.assertEqual(observed["override"], "inch")
            self.assertTrue(callable(observed["cancel_check"]))
            assert loaded.model is not None
            self.assertTrue(loaded.model.units.override_applied)
            self.assertEqual(loaded.model.units.scale_to_mm, 25.4)

    def test_non_boolean_persisted_unit_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = load_step(make_two_body_step(root))
            project_json = save_project(root / "project", model, SelectionState())
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            payload["model"]["units"]["override_applied"] = "false"
            project_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ProjectFormatError, "boolean"):
                load_project(project_json)

    def test_non_boolean_coordinate_confirmation_is_rejected_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = load_step(make_two_body_step(root))
            controller = TubeSetupController(model)
            controller.confirm_assignments(
                tuple(body.body_id for body in model.bodies if body.is_solid)
            )
            for node in (MODEL_CS_NODE, BUILD_CS_NODE):
                controller.begin_coordinate_draft(node)
                controller.set_numeric_origin(node, (0, 0, 0), confirmed=True)
                controller.set_numeric_direction(node, "z", (0, 0, 1), confirmed=True)
                controller.set_numeric_direction(node, "x", (1, 0, 0), confirmed=True)
                controller.apply_coordinate_draft(node)
            controller.select_machine(CARTESIAN_REFERENCE)
            controller.begin_placement_draft(mount_datum_id="build_plate_mount")
            controller.apply_placement_draft()
            self.assertTrue(controller.coordinates_valid)

            project_json = save_project(
                root / "project",
                model,
                SelectionState(),
                setup=controller.setup,
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            payload["setups"][0]["coordinate_systems"]["model"]["origin_reference"][
                "confirmed"
            ] = "false"
            project_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ProjectFormatError, "invalid manufacturing state"
            ) as captured:
                load_project(project_json)
            self.assertIsInstance(captured.exception.__cause__, TypeError)
            self.assertIn("must be a boolean", str(captured.exception.__cause__))

    def test_loaded_coordinate_signature_is_audited_against_embedded_cad(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = load_step(make_two_body_step(root))
            body = next(body for body in model.bodies if body.is_solid)
            vertex = model.vertex_map[body.vertex_ids[0]]
            face = next(
                model.face_map[face_id]
                for face_id in body.face_ids
                if model.face_map[face_id].normal is not None
            )
            assert face.normal is not None
            edge = next(
                model.edge_map[edge_id]
                for edge_id in body.edge_ids
                if model.edge_map[edge_id].axis_direction is not None
                and abs(
                    sum(
                        left * right
                        for left, right in zip(
                            model.edge_map[edge_id].axis_direction,
                            face.normal,
                        )
                    )
                )
                < 0.5
            )
            assert edge.axis_direction is not None

            origin = PointReference(
                "vertex",
                vertex.point,
                geometry=geometry_reference(model, vertex.vertex_id, "vertex"),
                confirmed=True,
            )
            z_direction = DirectionReference(
                "plane_normal",
                face.normal,
                geometry=geometry_reference(model, face.face_id, "face"),
                confirmed=True,
            )
            x_direction = DirectionReference(
                "line_edge",
                edge.axis_direction,
                geometry=geometry_reference(model, edge.edge_id, "edge"),
                confirmed=True,
            )
            controller = TubeSetupController(model)
            controller.confirm_assignments(
                tuple(item.body_id for item in model.bodies if item.is_solid)
            )
            for node, frame_id in (
                (MODEL_CS_NODE, "model"),
                (BUILD_CS_NODE, "build"),
            ):
                frame = CoordinateFrameDefinition.from_references(
                    frame_id,
                    f"{frame_id.title()} CS",
                    origin,
                    z_direction,
                    x_direction,
                )
                controller.begin_coordinate_draft(node)
                controller.set_origin_reference(node, frame.origin_reference)
                controller.set_direction_reference(
                    node, "z", frame.z_direction_reference
                )
                controller.set_direction_reference(
                    node, "x", frame.x_direction_reference
                )
                controller.apply_coordinate_draft(node)
            controller.select_machine(CARTESIAN_REFERENCE)
            controller.begin_placement_draft(mount_datum_id="build_plate_mount")
            controller.apply_placement_draft()
            self.assertTrue(controller.coordinates_valid)

            project_json = save_project(
                root / "project",
                model,
                SelectionState(),
                setup=controller.setup,
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))
            payload["setups"][0]["coordinate_systems"]["model"]["origin_reference"][
                "geometry"
            ]["signature"]["kernel_signature"] = "forged"
            project_json.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            loaded = load_project(project_json)

            assert loaded.model is not None
            assert loaded.setup is not None
            self.assertTrue(loaded.setup.coordinates_valid)
            restored = TubeSetupController(loaded.model, setup=loaded.setup)
            report = restored.validation_report()
            self.assertIs(report.state_for(MODEL_CS_NODE), NodeState.INVALID)
            self.assertFalse(report.coordinates_valid)
            self.assertIn(
                "COORDINATE_GEOMETRY_REFERENCE_MISMATCH",
                {issue.code for issue in report.issues},
            )


if __name__ == "__main__":
    unittest.main()
