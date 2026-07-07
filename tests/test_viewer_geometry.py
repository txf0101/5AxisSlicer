from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.viewer import _bead_frame, _dot, _nozzle_axis_from_rotary


class ViewerGeometryTests(unittest.TestCase):
    def test_bead_frame_is_orthogonal_for_ac_rotary_pose(self) -> None:
        frame = _bead_frame((0.0, 0.0, 0.0), (1.0, 0.2, 0.0), {"A": 35.0, "C": -20.0})

        self.assertIsNotNone(frame)
        tangent, width_axis, height_axis = frame
        nozzle = _nozzle_axis_from_rotary({"A": 35.0, "C": -20.0})
        self.assertAlmostEqual(_dot(tangent, width_axis), 0.0, places=6)
        self.assertAlmostEqual(_dot(tangent, height_axis), 0.0, places=6)
        self.assertAlmostEqual(_dot(width_axis, height_axis), 0.0, places=6)
        self.assertGreater(_dot(height_axis, nozzle), 0.0)


if __name__ == "__main__":
    unittest.main()
