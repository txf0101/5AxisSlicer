from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.gcode_preview import parse_gcode
from five_axis_slicer.manufacturing.preview_kinematics import (
    GENERIC_XYZAC_AC_SEMANTICS,
)
from five_axis_slicer.viewer import (
    VtkModelViewer,
    _bead_frame,
    _dot,
    _nozzle_axis_from_rotary,
    _preview_pose_for_segment,
)


class ViewerGeometryTests(unittest.TestCase):
    def assertVectorAlmostEqual(
        self,
        actual: tuple[float, float, float],
        expected: tuple[float, float, float],
        places: int = 6,
    ) -> None:
        for actual_value, expected_value in zip(actual, expected):
            self.assertAlmostEqual(actual_value, expected_value, places=places)

    def test_nozzle_axis_uses_registered_ac_inverse_and_raw_machine_fallback(
        self,
    ) -> None:
        ac_axis = _nozzle_axis_from_rotary(
            {"A": 70.513, "C": 0.0},
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )
        unsupported_axis = _nozzle_axis_from_rotary(
            {"A": 70.513, "B": 5.0},
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )
        raw_axis = _nozzle_axis_from_rotary(
            {"A": 70.513},
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
            coordinate_transform="machine_xyz",
        )

        self.assertVectorAlmostEqual(
            ac_axis,
            (0.0, -0.942719, -0.333588),
            places=5,
        )
        self.assertEqual(unsupported_axis, (0.0, 0.0, -1.0))
        self.assertEqual(raw_axis, (0.0, 0.0, -1.0))

    def test_bead_frame_is_orthogonal_for_ac_rotary_pose(self) -> None:
        frame = _bead_frame(
            (0.0, 0.0, 0.0),
            (1.0, 0.2, 0.0),
            {"A": 35.0, "C": -20.0},
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )

        self.assertIsNotNone(frame)
        tangent, width_axis, height_axis = frame
        nozzle = _nozzle_axis_from_rotary(
            {"A": 35.0, "C": -20.0},
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )
        self.assertAlmostEqual(_dot(tangent, width_axis), 0.0, places=6)
        self.assertAlmostEqual(_dot(tangent, height_axis), 0.0, places=6)
        self.assertAlmostEqual(_dot(width_axis, height_axis), 0.0, places=6)
        self.assertGreater(_dot(height_axis, nozzle), 0.0)

    def test_vtk_pose_actor_matches_each_segments_coordinate_space(self) -> None:
        cases = (
            (
                "G90\nM83\nG1 X1 Y0 Z0 A70.513 E0.1\n",
                (0.0, -0.942719, -0.333588),
            ),
            (
                "G90\nM83\nG1 X1 Y0 Z0 A70.513 B5 E0.1\n",
                (0.0, 0.0, -1.0),
            ),
        )

        for source, expected_axis in cases:
            with self.subTest(source=source):
                preview = parse_gcode(
                    source,
                    controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
                )

                class ViewerStub:
                    gcode_preview = preview

                    @staticmethod
                    def _segment_visible(_segment) -> bool:
                        return True

                actor = VtkModelViewer._make_pose_actor(ViewerStub())
                self.assertIsNotNone(actor)
                polydata = actor.GetMapper().GetInput()
                start = polydata.GetPoint(0)
                end = polydata.GetPoint(1)
                delta = tuple(end[index] - start[index] for index in range(3))
                length = sum(value * value for value in delta) ** 0.5
                axis = tuple(value / length for value in delta)

                self.assertVectorAlmostEqual(axis, expected_axis, places=5)

    def test_segment_pose_reconstructs_point_and_axis_as_one_result(self) -> None:
        ac_preview = parse_gcode(
            "G90\nM83\nG1 X0 Y-42 Z12.2 A90 C-162 E0.1\n",
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )
        raw_preview = parse_gcode(
            "G90\nM83\nG1 X0 Y-42 Z12.2 A90 B5 C-162 E0.1\n",
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )

        ac_point, ac_axis = _preview_pose_for_segment(
            ac_preview.segments[0],
            controller_semantics=ac_preview.controller_semantics,
        )
        raw_point, raw_axis = _preview_pose_for_segment(
            raw_preview.segments[0],
            controller_semantics=raw_preview.controller_semantics,
        )

        self.assertVectorAlmostEqual(ac_point, ac_preview.segments[0].end)
        self.assertNotEqual(ac_point, ac_preview.segments[0].machine_end)
        self.assertVectorAlmostEqual(ac_axis, (0.309016994, 0.951056516, 0.0))
        self.assertEqual(raw_point, raw_preview.segments[0].machine_end)
        self.assertEqual(raw_axis, (0.0, 0.0, -1.0))


if __name__ == "__main__":
    unittest.main()
