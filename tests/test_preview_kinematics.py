from __future__ import annotations

import math
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.preview_kinematics import (
    AC_INVERSE_TRANSFORM,
    DEFAULT_PREVIEW_KINEMATICS_REGISTRY,
    GENERIC_XYZAC_AC_SEMANTICS,
    MACHINE_COORDINATE_TRANSFORM,
    reconstruct_preview_motion,
    reconstruct_preview_pose,
)


class PreviewKinematicsTests(unittest.TestCase):
    def assertVectorAlmostEqual(
        self,
        actual: tuple[float, float, float],
        expected: tuple[float, float, float],
        places: int = 6,
    ) -> None:
        for actual_value, expected_value in zip(actual, expected):
            self.assertAlmostEqual(actual_value, expected_value, places=places)

    def test_generic_xyzac_semantics_is_explicitly_registered(self) -> None:
        self.assertIn(
            GENERIC_XYZAC_AC_SEMANTICS,
            DEFAULT_PREVIEW_KINEMATICS_REGISTRY.semantics_ids,
        )

    def test_ac_point_uses_rz_minus_c_after_rx_minus_a(self) -> None:
        result = reconstruct_preview_pose(
            (1.0, 2.0, 3.0),
            {"A": 90.0, "C": 90.0},
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )

        self.assertEqual(result.coordinate_transform, AC_INVERSE_TRANSFORM)
        self.assertVectorAlmostEqual(result.point, (3.0, -1.0, -2.0))
        self.assertEqual(result.issues, ())

    def test_fixed_machine_nozzle_axis_follows_same_inverse_chain(self) -> None:
        result = reconstruct_preview_pose(
            (0.0, 0.0, 0.0),
            {"A": 70.513, "C": 0.0},
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )

        self.assertVectorAlmostEqual(
            result.nozzle_axis,
            (0.0, -0.942719, -0.333588),
            places=5,
        )

    def test_nonzero_b_preserves_complete_motion_in_machine_coordinates(self) -> None:
        result = reconstruct_preview_motion(
            (1.0, 2.0, 3.0),
            (4.0, 5.0, 6.0),
            {"A": 30.0},
            {"A": 30.0, "B": 10.0},
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )

        self.assertEqual(result.start, (1.0, 2.0, 3.0))
        self.assertEqual(result.end, (4.0, 5.0, 6.0))
        self.assertEqual(result.coordinate_transform, MACHINE_COORDINATE_TRANSFORM)
        self.assertEqual(
            [issue.code for issue in result.issues],
            ["nc_preview.rotary_words_unsupported"],
        )
        self.assertEqual(
            result.issues[0].to_json()["context"]["unsupported_rotary_words"],
            ["B"],
        )

    def test_unregistered_secondary_rotary_words_are_never_silently_ignored(
        self,
    ) -> None:
        for word in ("U", "V", "W"):
            with self.subTest(word=word):
                result = reconstruct_preview_pose(
                    (1.0, 2.0, 3.0),
                    {word: 0.0},
                    controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
                )

                self.assertFalse(result.reconstructed)
                self.assertEqual(result.point, (1.0, 2.0, 3.0))
                self.assertEqual(
                    result.issues[0].code,
                    "nc_preview.rotary_words_unsupported",
                )

    def test_unknown_controller_semantics_preserves_machine_coordinates(self) -> None:
        result = reconstruct_preview_pose(
            (1.0, 2.0, 3.0),
            {"A": 45.0},
            controller_semantics="unregistered.controller.v1",
        )

        self.assertEqual(result.point, (1.0, 2.0, 3.0))
        self.assertEqual(result.coordinate_transform, MACHINE_COORDINATE_TRANSFORM)
        self.assertEqual(
            result.issues[0].code,
            "nc_preview.controller_semantics_unknown",
        )

    def test_unconfirmed_controller_semantics_preserves_machine_coordinates(
        self,
    ) -> None:
        result = reconstruct_preview_pose(
            (1.0, 2.0, 3.0),
            {"A": 45.0},
        )

        self.assertEqual(result.point, (1.0, 2.0, 3.0))
        self.assertEqual(result.coordinate_transform, MACHINE_COORDINATE_TRANSFORM)
        self.assertEqual(
            result.issues[0].code,
            "nc_preview.controller_semantics_unknown",
        )

    def test_non_finite_rotary_value_returns_stable_diagnostic(self) -> None:
        result = reconstruct_preview_pose(
            (1.0, 2.0, 3.0),
            {"A": math.inf},
        )

        self.assertEqual(result.point, (1.0, 2.0, 3.0))
        self.assertEqual(
            result.issues[0].code,
            "nc_preview.rotary_values_invalid",
        )


if __name__ == "__main__":
    unittest.main()
