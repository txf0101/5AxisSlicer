from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cadquery as cq

from five_axis_slicer.step_loader import geometry_candidates, load_step


class StepTopologyTests(unittest.TestCase):
    def test_box_exposes_faces_edges_vertices_units_and_adjacency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "box.step"
            cq.exporters.export(cq.Workplane("XY").box(10, 20, 30), str(path))
            model = load_step(path)

        self.assertEqual(model.units.source_length_unit, "millimetre")
        self.assertEqual(model.units.internal_length_unit, "millimetre")
        self.assertEqual(len(model.solid_bodies), 1)
        self.assertEqual(len(model.faces), 6)
        self.assertEqual(len(model.edges), 12)
        self.assertEqual(len(model.vertices), 8)
        self.assertTrue(all(face.signature for face in model.faces))
        self.assertTrue(all(edge.face_ids for edge in model.edges))
        self.assertTrue(all(edge.vertex_ids for edge in model.edges))
        self.assertTrue(all(vertex.edge_ids for vertex in model.vertices))
        self.assertEqual(len({face.signature for face in model.faces}), 6)
        candidates = geometry_candidates(model)
        self.assertTrue(any(item["kind"] == "line_edge" for item in candidates["directions"]))
        self.assertTrue(any(item["kind"] == "plane_normal" for item in candidates["directions"]))

    def test_pipe2_is_the_coordinate_setup_golden_source(self) -> None:
        root = Path(__file__).resolve().parents[1]
        matches = list((root / "example" / "pipe2").glob("*.stp"))
        if not matches:
            self.skipTest("pipe2 STEP fixture is not available")
        model = load_step(matches[0])

        self.assertEqual([len(body.face_ids) for body in model.solid_bodies], [3, 8])
        self.assertEqual(model.units.scale_to_mm, 1.0)
        self.assertAlmostEqual(model.solid_bodies[0].bounds.minimum[2], 0.0, places=5)
        self.assertAlmostEqual(model.solid_bodies[0].bounds.maximum[2], 5.0, places=5)
        candidates = geometry_candidates(model)
        self.assertTrue(any(item["kind"] == "face_centroid" for item in candidates["origins"]))
        self.assertTrue(any(item["kind"] == "surface_axis" for item in candidates["directions"]))

    def test_curved_edges_expose_exact_reference_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cylinder.step"
            cq.exporters.export(cq.Workplane("XY").cylinder(5, 2), str(path))
            model = load_step(path)

        candidates = geometry_candidates(model)
        circle_centres = [item for item in candidates["origins"] if item["kind"] == "circle_center"]
        arc_midpoints = [item for item in candidates["origins"] if item["kind"] == "arc_midpoint"]
        self.assertTrue(circle_centres)
        self.assertTrue(arc_midpoints)
        self.assertTrue(all(len(item["point"]) == 3 for item in arc_midpoints))

    def test_topology_signatures_are_stable_for_repeated_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cylinder.step"
            cq.exporters.export(cq.Workplane("XY").cylinder(5, 2), str(path))
            left = load_step(path)
            right = load_step(path)

        self.assertEqual(
            [item.signature for item in left.bodies],
            [item.signature for item in right.bodies],
        )
        self.assertEqual(
            [item.signature for item in left.faces],
            [item.signature for item in right.faces],
        )
        self.assertEqual(
            [item.signature for item in left.edges],
            [item.signature for item in right.edges],
        )
        self.assertEqual(
            [item.signature for item in left.vertices],
            [item.signature for item in right.vertices],
        )


if __name__ == "__main__":
    unittest.main()
