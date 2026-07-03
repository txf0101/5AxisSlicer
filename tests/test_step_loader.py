from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cadquery as cq

from five_axis_slicer.step_loader import load_step


def make_two_body_step(directory: Path) -> Path:
    path = directory / "two_boxes.step"
    assembly = cq.Assembly()
    assembly.add(cq.Workplane("XY").box(1, 1, 1), name="box_a")
    assembly.add(cq.Workplane("XY").box(1, 1, 1).translate((2, 0, 0)), name="box_b")
    assembly.save(str(path))
    return path


class StepLoaderTests(unittest.TestCase):
    def test_loads_two_solids_and_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = make_two_body_step(Path(tmp))
            model = load_step(step_path)

        self.assertEqual(len(model.bodies), 2)
        self.assertGreaterEqual(len(model.edges), 24)
        self.assertEqual(model.bodies[0].body_id, "body_001")
        self.assertTrue(model.bodies[0].edge_ids[0].startswith("body_001_edge_"))
        self.assertEqual(model.edges[0].body_id, "body_001")
        self.assertEqual(len(model.source_hash), 64)

    def test_loads_single_solid_without_region_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "single_box.step"
            cq.exporters.export(cq.Workplane("XY").box(1, 1, 1), str(step_path))
            model = load_step(step_path)

        self.assertEqual(len(model.bodies), 1)
        self.assertEqual(model.bodies[0].body_id, "body_001")
        self.assertGreaterEqual(len(model.bodies[0].edge_ids), 12)


if __name__ == "__main__":
    unittest.main()
