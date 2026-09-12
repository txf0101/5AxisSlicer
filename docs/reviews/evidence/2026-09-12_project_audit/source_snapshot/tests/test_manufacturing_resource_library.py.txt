from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.library import (  # noqa: E402
    ResourceLibraryError,
    UserResourceLibrary,
)
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    NozzleProfile,
    ResourceSnapshot,
    get_builtin_material_profile,
    get_builtin_nozzle_profile,
)


def complete_nozzle(
    resource_id: str = "e92fc40b-f17c-4fb5-ab0d-a1996f648d87",
) -> NozzleProfile:
    return NozzleProfile(
        resource_id=resource_id,
        display_name="Lab brass 0.4 mm",
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


class UserResourceLibraryTests(unittest.TestCase):
    def test_user_profile_is_atomically_saved_and_semantically_reloaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(Path(tmp) / "library")
            profile = complete_nozzle()

            path = library.save(profile)
            restored = library.load("nozzle", profile.resource_id)

            self.assertEqual(restored, profile)
            self.assertTrue(path.is_file())
            self.assertEqual(list(path.parent.glob("*.tmp")), [])
            self.assertEqual(library.profiles("nozzle"), (profile,))
            envelope = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(envelope["resource_id"], profile.resource_id)
            self.assertNotIn(profile.resource_id, path.name)

    def test_builtins_must_be_copied_before_they_can_be_saved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(tmp)
            with self.assertRaisesRegex(ResourceLibraryError, "immutable"):
                library.save(get_builtin_nozzle_profile(0.4))
            with self.assertRaisesRegex(ResourceLibraryError, "immutable"):
                library.save(get_builtin_material_profile("PLA"))

    def test_library_divergence_does_not_mutate_the_project_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(tmp)
            profile = complete_nozzle()
            library.save(profile)
            frozen = ResourceSnapshot.capture("nozzle", profile)

            self.assertEqual(library.audit_snapshot(frozen).status, "match")
            library.save(replace(profile, display_name="Recalibrated nozzle"))
            audit = library.audit_snapshot(frozen)

            self.assertEqual(audit.status, "diverged")
            self.assertNotEqual(audit.library_content_hash, frozen.content_hash)
            self.assertEqual(frozen.as_nozzle_profile(), profile)

    def test_missing_library_entry_is_reported_without_invalidating_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(tmp)
            profile = complete_nozzle()
            frozen = ResourceSnapshot.capture("nozzle", profile)

            audit = library.audit_snapshot(frozen)

            self.assertEqual(audit.status, "missing")
            self.assertTrue(frozen.verify())

    def test_corrupt_or_future_entries_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(tmp)
            profile = complete_nozzle()
            path = library.save(profile)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["schema_version"] = 99
            path.write_text(json.dumps(envelope), encoding="utf-8")

            with self.assertRaisesRegex(ResourceLibraryError, "newer"):
                library.load("nozzle", profile.resource_id)

    def test_catalog_isolates_deeply_malformed_profile_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(tmp)
            machine_dir = Path(tmp) / "machine"
            machine_dir.mkdir(parents=True)
            path = machine_dir / "malformed.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "resource_type": "machine",
                        "resource_id": "broken-machine",
                        "profile": {
                            "id": "broken-machine",
                            "name": "Broken machine",
                            "joints": {"unexpected": "mapping"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            catalog = library.catalog("machine")

            self.assertEqual(len(catalog.diagnostics), 1)
            self.assertEqual(catalog.diagnostics[0].code, "library_entry_invalid")
            self.assertNotIn(
                "broken-machine",
                {getattr(profile, "profile_id", "") for profile in catalog.profiles},
            )


if __name__ == "__main__":
    unittest.main()
