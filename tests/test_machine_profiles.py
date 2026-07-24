from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.coordinates import RigidTransform
from five_axis_slicer.manufacturing.machine import (
    BuildSurface,
    CARTESIAN_REFERENCE,
    GENERIC_XYZAC_REFERENCE,
    JointSpec,
    MachineProfile,
    MachineProfileValidationError,
    MountDatum,
    PostAxisMap,
    builtin_machine_profiles,
)


def make_surface() -> BuildSurface:
    return BuildSurface(
        surface_id="plate",
        name="Test plate",
        shape="rectangle",
        width_mm=100.0,
        depth_mm=80.0,
        thickness_mm=5.0,
    )


def make_profile(*joints: JointSpec) -> MachineProfile:
    surface = make_surface()
    parent_link = joints[-1].child_link_id if joints else "machine"
    return MachineProfile(
        profile_id="test.machine",
        name="Test machine",
        version=1,
        root_link_id="machine",
        tool_link_id=parent_link,
        workpiece_link_id="machine",
        reference_only=False,
        joints=tuple(joints),
        mount_datums=(
            MountDatum(
                mount_id="mount",
                name="Test mount",
                parent_link_id="machine",
                build_surface_id=surface.surface_id,
            ),
        ),
        build_surfaces=(surface,),
    )


class MachineProfileValidationTests(unittest.TestCase):
    def test_builtin_profiles_are_valid_reference_resources(self) -> None:
        profiles = builtin_machine_profiles()

        self.assertEqual(
            [profile.name for profile in profiles],
            ["Cartesian Reference", "Generic XYZAC Reference"],
        )
        for profile in profiles:
            self.assertTrue(profile.reference_only)
            self.assertIs(profile.validate(), profile)
            self.assertTrue(profile.mount_datums)
            self.assertTrue(profile.build_surfaces)

    def test_duplicate_joint_ids_are_rejected(self) -> None:
        first = JointSpec(
            "X",
            "X axis",
            "machine",
            "x_link",
            "linear",
            "tool",
            (1.0, 0.0, 0.0),
        )
        second = JointSpec(
            "X",
            "Duplicate X axis",
            "x_link",
            "tool",
            "linear",
            "tool",
            (0.0, 1.0, 0.0),
        )
        profile = make_profile(first, second)

        with self.assertRaises(MachineProfileValidationError) as captured:
            profile.validate()

        self.assertIn("joint.duplicate_id:X", captured.exception.errors)

    def test_cycles_are_rejected(self) -> None:
        first = JointSpec(
            "A",
            "A axis",
            "b_link",
            "a_link",
            "rotary",
            "workpiece",
            (1.0, 0.0, 0.0),
        )
        second = JointSpec(
            "C",
            "C axis",
            "a_link",
            "b_link",
            "rotary",
            "workpiece",
            (0.0, 0.0, 1.0),
        )
        profile = replace(
            make_profile(first, second),
            tool_link_id=None,
            workpiece_link_id="b_link",
        )

        with self.assertRaises(MachineProfileValidationError) as captured:
            profile.validate()

        self.assertTrue(
            any(error.startswith("joint.cycle:") for error in captured.exception.errors)
        )

    def test_non_unit_axis_and_reversed_limits_are_rejected(self) -> None:
        joint = JointSpec(
            "X",
            "X axis",
            "machine",
            "tool",
            "linear",
            "tool",
            (2.0, 0.0, 0.0),
            soft_limit_min=10.0,
            soft_limit_max=-10.0,
        )
        profile = make_profile(joint)

        errors = profile.validation_errors()

        self.assertIn("joint:X.axis_not_unit", errors)
        self.assertIn("joint:X.reversed_soft_limits", errors)

    def test_unknown_mount_link_and_surface_are_rejected(self) -> None:
        profile = replace(
            CARTESIAN_REFERENCE,
            mount_datums=(
                MountDatum(
                    mount_id="invalid",
                    name="Invalid mount",
                    parent_link_id="missing_link",
                    build_surface_id="missing_surface",
                ),
            ),
        )

        errors = profile.validation_errors()

        self.assertIn("mount:invalid.unknown_parent:missing_link", errors)
        self.assertIn("mount:invalid.unknown_build_surface:missing_surface", errors)

    def test_joint_zero_transform_requires_exact_frame_labels(self) -> None:
        for source_frame, target_frame in (
            ("", "machine"),
            ("tool", ""),
            ("machine", "tool"),
        ):
            with self.subTest(
                source_frame=source_frame,
                target_frame=target_frame,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "T_parent_from_child_zero .*_frame",
                ):
                    JointSpec(
                        "X",
                        "X axis",
                        "machine",
                        "tool",
                        "linear",
                        "tool",
                        (1.0, 0.0, 0.0),
                        T_parent_from_child_zero=RigidTransform(
                            RigidTransform.identity().matrix,
                            source_frame=source_frame,
                            target_frame=target_frame,
                        ),
                    )

    def test_mount_transform_requires_exact_frame_labels(self) -> None:
        for source_frame, target_frame in (
            ("", "machine"),
            ("mount", ""),
            ("machine", "mount"),
        ):
            with self.subTest(
                source_frame=source_frame,
                target_frame=target_frame,
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "T_parent_from_mount .*_frame",
                ):
                    MountDatum(
                        mount_id="mount",
                        name="Mount",
                        parent_link_id="machine",
                        build_surface_id="plate",
                        T_parent_from_mount=RigidTransform(
                            RigidTransform.identity().matrix,
                            source_frame=source_frame,
                            target_frame=target_frame,
                        ),
                    )

    def test_branching_inside_one_serial_side_is_rejected(self) -> None:
        one = JointSpec(
            "X",
            "X axis",
            "machine",
            "x_link",
            "linear",
            "tool",
            (1.0, 0.0, 0.0),
        )
        two = JointSpec(
            "Y",
            "Y axis",
            "machine",
            "y_link",
            "linear",
            "tool",
            (0.0, 1.0, 0.0),
        )
        profile = replace(make_profile(one, two), tool_link_id="y_link")

        self.assertIn("joint.branching_chain:machine:tool", profile.validation_errors())


class MachineKinematicsTests(unittest.TestCase):
    def assertVectorAlmostEqual(
        self,
        actual: tuple[float, float, float],
        expected: tuple[float, float, float],
        places: int = 8,
    ) -> None:
        for actual_value, expected_value in zip(actual, expected):
            self.assertAlmostEqual(actual_value, expected_value, places=places)

    def test_cartesian_chain_composes_parent_to_child_translations(self) -> None:
        transforms = CARTESIAN_REFERENCE.forward_kinematics(
            {"X": 10.0, "Y": 20.0, "Z": 30.0}
        )

        self.assertVectorAlmostEqual(
            transforms["tool"].transform_point((0.0, 0.0, 0.0)),
            (10.0, 20.0, 30.0),
        )
        self.assertEqual(transforms["tool"].source_frame, "tool")
        self.assertEqual(transforms["tool"].target_frame, "machine")

    def test_soft_limits_are_enforced_during_forward_kinematics(self) -> None:
        with self.assertRaisesRegex(ValueError, "above soft limit: X"):
            CARTESIAN_REFERENCE.forward_kinematics({"X": 301.0})

    def test_unknown_joint_position_is_rejected(self) -> None:
        with self.assertRaisesRegex(KeyError, "unknown joint position"):
            CARTESIAN_REFERENCE.forward_kinematics({"Q": 1.0})

    def test_xyzac_uses_a_then_c_workpiece_chain(self) -> None:
        a_angle = math.radians(35.0)
        c_angle = math.radians(20.0)
        actual = GENERIC_XYZAC_REFERENCE.link_transform(
            "c_table", {"A": a_angle, "C": c_angle}
        )
        expected = RigidTransform.from_axis_angle((1.0, 0.0, 0.0), a_angle) @ (
            RigidTransform.from_axis_angle((0.0, 0.0, 1.0), c_angle)
        )

        for actual_row, expected_row in zip(actual.matrix, expected.matrix):
            for actual_value, expected_value in zip(actual_row, expected_row):
                self.assertAlmostEqual(actual_value, expected_value, places=9)

    def test_pipe2_fixed_nozzle_direction_matches_documented_ac_inverse(self) -> None:
        a_angle = math.radians(70.513)
        machine_from_table = GENERIC_XYZAC_REFERENCE.link_transform(
            "c_table", {"A": a_angle, "C": 0.0}
        )

        direction_in_workpiece = machine_from_table.inverse().transform_vector(
            (0.0, 0.0, -1.0)
        )

        self.assertVectorAlmostEqual(
            direction_in_workpiece,
            (0.0, -0.942719, -0.333588),
            places=5,
        )

    def test_rotation_center_remains_fixed(self) -> None:
        joint = JointSpec(
            "C",
            "Offset C axis",
            "machine",
            "table",
            "rotary",
            "workpiece",
            (0.0, 0.0, 1.0),
            rotation_center_mm=(10.0, 20.0, 0.0),
            soft_limit_min=-math.pi,
            soft_limit_max=math.pi,
        )
        profile = replace(
            make_profile(joint),
            tool_link_id=None,
            workpiece_link_id="table",
        )

        transform = profile.link_transform("table", {"C": math.pi / 2.0})

        self.assertVectorAlmostEqual(
            transform.transform_point((10.0, 20.0, 0.0)),
            (10.0, 20.0, 0.0),
        )
        self.assertVectorAlmostEqual(
            transform.transform_point((11.0, 20.0, 0.0)),
            (10.0, 21.0, 0.0),
        )

    def test_mount_transform_follows_workpiece_chain(self) -> None:
        mount = GENERIC_XYZAC_REFERENCE.mount_transform(
            "build_plate_mount", {"A": math.pi / 2.0, "C": 0.0}
        )

        self.assertVectorAlmostEqual(
            mount.transform_vector((0.0, 0.0, 1.0)),
            (0.0, -1.0, 0.0),
        )
        self.assertEqual(mount.source_frame, "build_plate_mount")
        self.assertEqual(mount.target_frame, "machine")


class MachineSerializationTests(unittest.TestCase):
    def test_machine_profile_json_round_trip_is_lossless(self) -> None:
        payload = json.loads(json.dumps(GENERIC_XYZAC_REFERENCE.to_json()))

        restored = MachineProfile.from_json(payload)

        self.assertEqual(restored, GENERIC_XYZAC_REFERENCE)
        self.assertEqual(restored.to_json(), GENERIC_XYZAC_REFERENCE.to_json())

    def test_machine_profile_json_rejects_empty_rigid_frame_labels(self) -> None:
        cases = (
            ("joints", 0, "T_parent_from_child_zero", "source_frame"),
            ("joints", 0, "T_parent_from_child_zero", "target_frame"),
            ("mount_datums", 0, "T_parent_from_mount", "source_frame"),
            ("mount_datums", 0, "T_parent_from_mount", "target_frame"),
        )
        for collection, index, transform_key, frame_key in cases:
            with self.subTest(
                collection=collection,
                transform_key=transform_key,
                frame_key=frame_key,
            ):
                payload = json.loads(json.dumps(CARTESIAN_REFERENCE.to_json()))
                payload[collection][index][transform_key][frame_key] = ""
                with self.assertRaisesRegex(ValueError, "invalid Machine Profile"):
                    MachineProfile.from_json(payload)

    def test_reference_only_requires_a_json_boolean_and_defaults_true(self) -> None:
        for forged_value in ("false", 0, None, [], {}):
            with self.subTest(forged_value=forged_value):
                payload = json.loads(json.dumps(CARTESIAN_REFERENCE.to_json()))
                payload["reference_only"] = forged_value
                with self.assertRaisesRegex(ValueError, "invalid Machine Profile"):
                    MachineProfile.from_json(payload)

        payload = json.loads(json.dumps(CARTESIAN_REFERENCE.to_json()))
        payload.pop("reference_only")
        self.assertTrue(MachineProfile.from_json(payload).reference_only)

    def test_post_axis_map_converts_internal_radians_to_degrees(self) -> None:
        mapping = PostAxisMap("a", output_unit="deg", scale=-1.0, offset=5.0)

        encoded = mapping.encode(math.pi / 2.0, "rotary")

        self.assertEqual(mapping.word, "A")
        self.assertAlmostEqual(encoded, -85.0)
        self.assertAlmostEqual(mapping.decode(encoded, "rotary"), math.pi / 2.0)

    def test_controller_values_apply_zero_offset_and_units(self) -> None:
        profile = GENERIC_XYZAC_REFERENCE

        values = profile.controller_values({"A": math.pi / 4.0, "C": -math.pi})

        self.assertAlmostEqual(values["A"], 45.0)
        self.assertAlmostEqual(values["C"], -180.0)


if __name__ == "__main__":
    unittest.main()
