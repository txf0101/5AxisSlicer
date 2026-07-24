from __future__ import annotations

import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    BUILTIN_MATERIAL_PROFILES,
    BUILTIN_NOZZLE_PROFILES,
    CURA_FDM_MATERIALS_COMMIT,
    GENERIC_NOZZLE_0_4,
    MaterialProfile,
    NozzleProfile,
    ResourceIntegrityError,
    ResourceSnapshot,
    canonical_content_hash,
    canonical_json_bytes,
    get_builtin_material_profile,
    get_builtin_nozzle_profile,
)


class NozzleProfileTests(unittest.TestCase):
    def test_builtin_identity_templates_are_immutable_and_incomplete(self) -> None:
        self.assertEqual(
            [
                profile.orifice_diameter_mm
                for profile in BUILTIN_NOZZLE_PROFILES.values()
            ],
            [0.4, 0.6, 0.8],
        )
        for profile in BUILTIN_NOZZLE_PROFILES.values():
            self.assertTrue(profile.is_builtin)
            self.assertFalse(profile.is_ready)
            self.assertEqual(
                {issue.code for issue in profile.readiness_blockers},
                {
                    "nozzle.interface_missing",
                    "nozzle.length_missing",
                    "nozzle.outer_profile_missing",
                },
            )
            self.assertIsNone(profile.interface)
            self.assertIsNone(profile.length_mm)
            self.assertEqual(profile.outer_profile_rz_mm, ())

        with self.assertRaises(FrozenInstanceError):
            GENERIC_NOZZLE_0_4.interface = "E3D V6"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            BUILTIN_NOZZLE_PROFILES["1.0"] = GENERIC_NOZZLE_0_4  # type: ignore[index]

    def test_complete_user_nozzle_is_ready_and_round_trips(self) -> None:
        profile = NozzleProfile(
            resource_id="f9429185-b398-49e6-b6bb-25ab74127645",
            display_name="Lab brass 0.4 mm",
            orifice_diameter_mm=0.4,
            filament_diameter_mm=1.75,
            interface="E3D V6 M6 thread",
            length_mm=12.5,
            construction_material="brass",
            flow_category="standard",
            temperature_limit_c=300.0,
            wear_resistance_rating="standard",
            outer_profile_rz_mm=(
                (0.2, 0.0),
                (3.0, 2.0),
                (3.0, 12.5),
                (0.2, 12.5),
            ),
        )

        self.assertTrue(profile.is_ready)
        self.assertEqual(profile.readiness_blockers, ())
        encoded = json.loads(json.dumps(profile.to_json()))
        self.assertEqual(NozzleProfile.from_json(encoded), profile)

    def test_copying_template_does_not_mutate_builtin(self) -> None:
        copied = GENERIC_NOZZLE_0_4.editable_copy(
            "1e5ac894-3fc7-4f70-8e89-7132698fc4c3",
            display_name="Shop 0.4 mm nozzle",
        )

        self.assertFalse(copied.is_builtin)
        self.assertEqual(copied.orifice_diameter_mm, 0.4)
        self.assertTrue(GENERIC_NOZZLE_0_4.is_builtin)
        self.assertIs(get_builtin_nozzle_profile(0.4000000001), GENERIC_NOZZLE_0_4)

    def test_is_builtin_requires_a_json_boolean_and_defaults_false(self) -> None:
        for forged_value in ("false", 0, None, [], {}):
            with self.subTest(forged_value=forged_value):
                payload = json.loads(json.dumps(GENERIC_NOZZLE_0_4.to_json()))
                payload["is_builtin"] = forged_value
                with self.assertRaisesRegex(TypeError, "must be a boolean"):
                    NozzleProfile.from_json(payload)

        payload = json.loads(json.dumps(GENERIC_NOZZLE_0_4.to_json()))
        payload.pop("is_builtin")
        self.assertFalse(NozzleProfile.from_json(payload).is_builtin)


class MaterialProfileTests(unittest.TestCase):
    EXPECTED = {
        "PLA": {
            "version": 13,
            "guid": "0ff92885-617b-4144-a03c-9989872454bc",
            "density": 1.24,
            "nozzle": 200.0,
            "bed": 60.0,
            "file": "generic_pla_175.xml.fdm_material",
            "sha256": "5bc7c562e14cb10c15323bca26f1afddedcf6e18166c92adf4d638611907a4be",
        },
        "PETG": {
            "version": 7,
            "guid": "69386c85-5b6c-421a-bec5-aeb1fb33f060",
            "density": 1.27,
            "nozzle": 215.0,
            "bed": 70.0,
            "file": "generic_petg_175.xml.fdm_material",
            "sha256": "d1e41783828696f374f6267bc9f07b8336a0ceedfafbf32dcbaf930d5595c0e3",
        },
        "ABS": {
            "version": 12,
            "guid": "2780b345-577b-4a24-a2c5-12e6aad3e690",
            "density": 1.1,
            "nozzle": 230.0,
            "bed": 80.0,
            "file": "generic_abs_175.xml.fdm_material",
            "sha256": "6687016b42e144e8ae717cf87024f383815c61b3ae300ac1adb6045093c9d1b4",
        },
    }

    def test_cura_templates_have_pinned_provenance_and_single_values(self) -> None:
        for material, expected in self.EXPECTED.items():
            with self.subTest(material=material):
                profile = get_builtin_material_profile(material.lower())
                self.assertIs(profile, BUILTIN_MATERIAL_PROFILES[material])
                self.assertEqual(profile.guid, expected["guid"])
                self.assertEqual(profile.upstream_version, expected["version"])
                self.assertEqual(profile.filament_diameter_mm, 1.75)
                self.assertEqual(profile.density_g_cm3, expected["density"])
                self.assertEqual(
                    profile.recommendations.nozzle_temperature_c,
                    expected["nozzle"],
                )
                self.assertEqual(
                    profile.recommendations.build_plate_temperature_c,
                    expected["bed"],
                )
                self.assertEqual(profile.source.revision, CURA_FDM_MATERIALS_COMMIT)
                self.assertEqual(profile.source.file_path, expected["file"])
                self.assertEqual(profile.source.sha256, expected["sha256"])
                self.assertIn(CURA_FDM_MATERIALS_COMMIT, profile.source.url)
                self.assertTrue(profile.review_required)
                self.assertFalse(profile.review_confirmed)
                self.assertFalse(profile.is_ready)
                self.assertEqual(
                    [issue.code for issue in profile.readiness_blockers],
                    ["material.review_required"],
                )

                recommendation_json = profile.to_json()["recommendations"]
                self.assertEqual(
                    set(recommendation_json),
                    {"nozzle_temperature_c", "build_plate_temperature_c"},
                )
                self.assertFalse(
                    any(
                        suffix in key
                        for key in recommendation_json
                        for suffix in ("_min", "_max", "_range")
                    )
                )

    def test_reviewed_copy_is_ready_and_json_round_trip_is_lossless(self) -> None:
        template = get_builtin_material_profile("PLA")
        reviewed = template.reviewed_copy(
            "ab31d7c0-7292-4ea9-bb24-50bddfa2ad8f",
            display_name="Reviewed Generic PLA",
        )

        self.assertTrue(reviewed.is_ready)
        self.assertTrue(reviewed.review_confirmed)
        self.assertFalse(reviewed.is_builtin)
        self.assertFalse(template.review_confirmed)
        encoded = json.loads(json.dumps(reviewed.to_json()))
        self.assertEqual(MaterialProfile.from_json(encoded), reviewed)

    def test_material_templates_are_deeply_immutable(self) -> None:
        profile = get_builtin_material_profile("PETG")
        with self.assertRaises(FrozenInstanceError):
            profile.review_confirmed = True  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            profile.recommendations.nozzle_temperature_c = 220.0  # type: ignore[misc]
        with self.assertRaises(TypeError):
            BUILTIN_MATERIAL_PROFILES["TPU"] = profile  # type: ignore[index]

    def test_material_flags_require_json_booleans_and_keep_schema_defaults(
        self,
    ) -> None:
        template = get_builtin_material_profile("PLA")
        for field_name in ("review_required", "review_confirmed", "is_builtin"):
            for forged_value in ("false", 1, None, [], {}):
                with self.subTest(
                    field_name=field_name,
                    forged_value=forged_value,
                ):
                    payload = json.loads(json.dumps(template.to_json()))
                    payload[field_name] = forged_value
                    with self.assertRaisesRegex(TypeError, "must be a boolean"):
                        MaterialProfile.from_json(payload)

        payload = json.loads(json.dumps(template.to_json()))
        for field_name in ("review_required", "review_confirmed", "is_builtin"):
            payload.pop(field_name)
        restored = MaterialProfile.from_json(payload)
        self.assertTrue(restored.review_required)
        self.assertFalse(restored.review_confirmed)
        self.assertFalse(restored.is_builtin)


class ResourceSnapshotTests(unittest.TestCase):
    def test_canonical_hash_is_independent_of_mapping_order(self) -> None:
        left = {"label": "喷嘴", "value": 0.4, "nested": {"a": 1, "b": 2}}
        right = {"nested": {"b": 2, "a": 1}, "value": 0.4, "label": "喷嘴"}

        self.assertEqual(canonical_json_bytes(left), canonical_json_bytes(right))
        self.assertEqual(canonical_content_hash(left), canonical_content_hash(right))
        self.assertEqual(
            canonical_content_hash({"zero": -0.0}),
            canonical_content_hash({"zero": 0.0}),
        )
        with self.assertRaises(ValueError):
            canonical_content_hash({"bad": float("nan")})

    def test_snapshot_is_deeply_immutable_and_round_trips(self) -> None:
        snapshot = ResourceSnapshot.capture(
            "material",
            get_builtin_material_profile("ABS"),
        )

        self.assertTrue(snapshot.verify())
        with self.assertRaises(TypeError):
            snapshot.payload["display_name"] = "tampered"  # type: ignore[index]
        with self.assertRaises(TypeError):
            snapshot.payload["recommendations"][  # type: ignore[index]
                "nozzle_temperature_c"
            ] = 1.0

        encoded = json.loads(json.dumps(snapshot.to_json()))
        restored = ResourceSnapshot.from_json(encoded)
        self.assertEqual(restored, snapshot)
        self.assertEqual(
            restored.as_material_profile(),
            get_builtin_material_profile("ABS"),
        )

    def test_snapshot_detects_payload_and_envelope_tampering(self) -> None:
        snapshot = ResourceSnapshot.capture(
            "nozzle",
            get_builtin_nozzle_profile(0.6),
        )
        tampered_payload = snapshot.to_json()
        tampered_payload["payload"]["orifice_diameter_mm"] = 0.8
        with self.assertRaises(ResourceIntegrityError):
            ResourceSnapshot.from_json(tampered_payload)

        tampered_identity = snapshot.to_json()
        tampered_identity["resource_id"] = "different-resource"
        with self.assertRaises(ResourceIntegrityError):
            ResourceSnapshot.from_json(tampered_identity)

        tampered_type = snapshot.to_json()
        tampered_type["resource_type"] = "material"
        with self.assertRaises(ResourceIntegrityError):
            ResourceSnapshot.from_json(tampered_type)

    def test_capture_accepts_machine_id_and_version_convention(self) -> None:
        class MachineLikeProfile:
            def to_json(self) -> dict[str, object]:
                return {
                    "id": "builtin.machine.cartesian_reference.v1",
                    "version": 1,
                    "name": "Cartesian Reference",
                }

        snapshot = ResourceSnapshot.capture("machine", MachineLikeProfile())

        self.assertEqual(snapshot.resource_id, "builtin.machine.cartesian_reference.v1")
        self.assertEqual(snapshot.profile_version, 1)
        self.assertTrue(snapshot.verify())
        self.assertEqual(ResourceSnapshot.from_json(snapshot.to_json()), snapshot)

    def test_snapshot_type_guard_prevents_wrong_profile_restore(self) -> None:
        snapshot = ResourceSnapshot.capture(
            "material",
            get_builtin_material_profile("PLA"),
        )
        with self.assertRaises(TypeError):
            snapshot.as_nozzle_profile()


if __name__ == "__main__":
    unittest.main()
