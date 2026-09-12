from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    LocalAdjustment,
    PointReference,
    RigidTransform,
    apply_local_adjustment,
)


class RigidTransformTests(unittest.TestCase):
    def assertVectorAlmostEqual(self, actual, expected, places: int = 9) -> None:
        self.assertEqual(len(actual), len(expected))
        for actual_value, expected_value in zip(actual, expected):
            self.assertAlmostEqual(actual_value, expected_value, places=places)

    def test_inverse_and_compose_preserve_frame_chain(self) -> None:
        rotate = RigidTransform.from_axis_angle(
            (0, 0, 1),
            math.pi / 2,
            source_frame="a",
            target_frame="b",
        )
        translate = RigidTransform.from_translation(
            (2, 0, 0),
            source_frame="b",
            target_frame="c",
        )

        combined = translate @ rotate
        self.assertEqual(combined.source_frame, "a")
        self.assertEqual(combined.target_frame, "c")
        self.assertVectorAlmostEqual(combined.transform_point((1, 0, 0)), (2, 1, 0))
        self.assertVectorAlmostEqual(
            combined.inverse().transform_point((2, 1, 0)),
            (1, 0, 0),
        )
        self.assertTrue((combined.inverse() @ combined).almost_equal(RigidTransform.identity("a")))

    def test_from_frame_projects_x_and_constructs_right_handed_basis(self) -> None:
        transform = RigidTransform.from_frame(
            (10, 20, 30),
            (1, 0, 0.25),
            (0, 0, 1),
            target_frame="model",
        )

        self.assertVectorAlmostEqual(transform.transform_point((10, 20, 30)), (0, 0, 0))
        self.assertVectorAlmostEqual(transform.transform_vector((1, 0, 0)), (1, 0, 0))
        self.assertAlmostEqual(transform.rotation[0][0], 1.0)
        self.assertAlmostEqual(transform.rotation[1][1], 1.0)
        self.assertAlmostEqual(transform.rotation[2][2], 1.0)

    def test_rejects_collinear_nonfinite_and_nonrigid_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "collinear"):
            RigidTransform.from_frame((0, 0, 0), (0, 0, 2), (0, 0, 1), target_frame="model")
        with self.assertRaisesRegex(ValueError, "finite"):
            RigidTransform.from_translation((math.nan, 0, 0))
        with self.assertRaisesRegex(ValueError, "orthonormal"):
            RigidTransform(
                (
                    (2, 0, 0, 0),
                    (0, 1, 0, 0),
                    (0, 0, 1, 0),
                    (0, 0, 0, 1),
                )
            )
        with self.assertRaisesRegex(ValueError, "right-handed"):
            RigidTransform(
                (
                    (-1, 0, 0, 0),
                    (0, 1, 0, 0),
                    (0, 0, 1, 0),
                    (0, 0, 0, 1),
                )
            )

    def test_local_adjustment_uses_reference_translate_rx_ry_rz_order(self) -> None:
        reference = RigidTransform.from_axis_angle((0, 0, 1), math.pi / 2)
        adjustment = LocalAdjustment.from_euler_xyz(
            translation_mm=(2, 0, 0),
            rotation_xyz_rad=(math.pi / 2, 0, 0),
        )

        adjusted = apply_local_adjustment(reference, adjustment)
        self.assertVectorAlmostEqual(adjusted.transform_point((0, 0, 0)), (0, 2, 0))
        self.assertVectorAlmostEqual(adjusted.transform_vector((0, 1, 0)), (0, 0, 1))
        self.assertEqual(
            LocalAdjustment.from_json(adjustment.to_json()).to_json(),
            adjustment.to_json(),
        )

    def test_local_adjustment_exposes_euler_values_for_editor_round_trip(self) -> None:
        expected = (math.radians(17.0), math.radians(-23.0), math.radians(41.0))
        adjustment = LocalAdjustment.from_euler_xyz((1, 2, 3), expected)

        self.assertVectorAlmostEqual(adjustment.euler_xyz_rad, expected)

    def test_exact_half_turn_quaternion_has_one_stable_serialization(self) -> None:
        positive = LocalAdjustment((0, 0, 0), (1, 0, 0, 0))
        negative = LocalAdjustment((0, 0, 0), (-1, 0, 0, 0))
        near_boundary = LocalAdjustment((0, 0, 0), (-1, 0, 0, -1.0e-16))

        self.assertEqual(positive.to_json(), negative.to_json())
        self.assertEqual(positive.to_json(), near_boundary.to_json())
        self.assertEqual(positive.quaternion_xyzw, (1.0, 0.0, 0.0, 0.0))

    def test_transform_and_coordinate_definition_json_round_trip(self) -> None:
        face = GeometryReference(
            "face-001",
            "face",
            signature={"surface": "plane", "centroid_mm": [1, 2, 3]},
            parent_body_id="body-001",
        )
        origin = PointReference(
            "face_centroid",
            (1, 2, 3),
            geometry=face,
            confirmed=True,
        )
        z_direction = DirectionReference(
            "plane_normal",
            (0, 0, 1),
            geometry=face,
            confirmed=True,
        )
        x_direction = DirectionReference(
            "numeric",
            (1, 0, 0.2),
            confirmed=True,
        )
        frame = CoordinateFrameDefinition.from_references(
            "model",
            "Model CS",
            origin,
            z_direction,
            x_direction,
        )

        payload = json.loads(json.dumps(frame.to_json()))
        restored = CoordinateFrameDefinition.from_json(payload)
        self.assertTrue(restored.is_valid)
        self.assertEqual(restored.to_json(), payload)
        self.assertEqual(restored.origin_reference.geometry.stable_id, "face-001")

    def test_confirmed_frame_rejects_a_transform_unrelated_to_references(self) -> None:
        origin = PointReference("numeric", (10, 0, 0), confirmed=True)
        z_direction = DirectionReference("numeric", (0, 0, 1), confirmed=True)
        x_direction = DirectionReference("numeric", (1, 0, 0), confirmed=True)
        valid = CoordinateFrameDefinition.from_references(
            "model", "Model CS", origin, z_direction, x_direction
        )
        payload = valid.to_json()
        payload["T_target_from_source"] = RigidTransform.identity("model").to_json()
        payload["T_target_from_source"]["source_frame"] = "source"

        with self.assertRaisesRegex(ValueError, "do not match"):
            CoordinateFrameDefinition.from_json(payload)

    def test_coordinate_definition_requires_explicit_source_and_target_labels(
        self,
    ) -> None:
        frame = CoordinateFrameDefinition.from_references(
            "model",
            "Model CS",
            PointReference("numeric", (0, 0, 0), confirmed=True),
            DirectionReference("numeric", (0, 0, 1), confirmed=True),
            DirectionReference("numeric", (1, 0, 0), confirmed=True),
        )

        for field_name, value, message in (
            ("source_frame", "", "source_frame"),
            ("source_frame", "machine", "source_frame"),
            ("target_frame", "", "target_frame"),
            ("target_frame", "build", "target_frame"),
        ):
            with self.subTest(field_name=field_name, value=value):
                payload = json.loads(json.dumps(frame.to_json()))
                payload["T_target_from_source"][field_name] = value
                with self.assertRaisesRegex(ValueError, message):
                    CoordinateFrameDefinition.from_json(payload)

    def test_coordinate_json_rejects_truthy_non_boolean_flags(self) -> None:
        frame = CoordinateFrameDefinition.from_references(
            "model",
            "Model CS",
            PointReference("numeric", (0, 0, 0), confirmed=True),
            DirectionReference("numeric", (0, 0, 1), confirmed=True),
            DirectionReference("numeric", (1, 0, 0), confirmed=True),
        )
        cases = (
            ("origin_reference", "confirmed", "false"),
            ("z_direction_reference", "confirmed", 1),
            ("z_direction_reference", "flipped", "false"),
            ("x_direction_reference", "flipped", 1),
        )

        for reference_key, flag, forged_value in cases:
            with self.subTest(
                reference_key=reference_key,
                flag=flag,
                forged_value=forged_value,
            ):
                payload = json.loads(json.dumps(frame.to_json()))
                payload[reference_key][flag] = forged_value
                with self.assertRaisesRegex(TypeError, "must be a boolean"):
                    CoordinateFrameDefinition.from_json(payload)

        with self.assertRaisesRegex(TypeError, "confirmed must be a boolean"):
            PointReference("numeric", (0, 0, 0), confirmed=1)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
