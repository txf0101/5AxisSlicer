from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cadquery as cq

from five_axis_slicer.step_loader import StepLoadCancelled, file_sha256, load_step


def make_two_body_step(directory: Path) -> Path:
    path = directory / "two_boxes.step"
    assembly = cq.Assembly()
    assembly.add(cq.Workplane("XY").box(1, 1, 1), name="box_a")
    assembly.add(cq.Workplane("XY").box(1, 1, 1).translate((2, 0, 0)), name="box_b")
    assembly.save(str(path))
    return path


class StepLoaderTests(unittest.TestCase):
    def test_file_hash_can_be_cancelled_between_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "large.step"
            source.write_bytes(b"x" * (3 * 1024 * 1024))
            checks = 0

            def cancel_during_hash() -> bool:
                nonlocal checks
                checks += 1
                return checks >= 4

            with self.assertRaises(StepLoadCancelled):
                file_sha256(source, cancel_check=cancel_during_hash)

        self.assertGreaterEqual(checks, 4)

    def test_loads_two_solids_and_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = make_two_body_step(Path(tmp))
            expected_size = step_path.stat().st_size
            expected_mtime = step_path.stat().st_mtime_ns
            model = load_step(step_path)

        self.assertEqual(len(model.bodies), 2)
        self.assertGreaterEqual(len(model.edges), 24)
        self.assertEqual(model.bodies[0].body_id, "body_001")
        self.assertTrue(model.bodies[0].edge_ids[0].startswith("body_001_edge_"))
        self.assertEqual(model.edges[0].body_id, "body_001")
        self.assertEqual(len(model.source_hash), 64)
        self.assertEqual(model.source_size_bytes, expected_size)
        self.assertEqual(model.source_mtime_ns, expected_mtime)

    def test_loads_single_solid_without_region_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "single_box.step"
            cq.exporters.export(cq.Workplane("XY").box(1, 1, 1), str(step_path))
            model = load_step(step_path)

        self.assertEqual(len(model.bodies), 1)
        self.assertEqual(model.bodies[0].body_id, "body_001")
        self.assertGreaterEqual(len(model.bodies[0].edge_ids), 12)

    def test_rejects_a_step_source_that_changes_during_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "changing_box.step"
            cq.exporters.export(cq.Workplane("XY").box(1, 1, 1), str(step_path))
            with mock.patch(
                "five_axis_slicer.step_loader.file_sha256",
                side_effect=["a" * 64, "b" * 64],
            ):
                with self.assertRaisesRegex(RuntimeError, "changed while loading"):
                    load_step(step_path)

    def test_cancels_during_topology_enumeration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "topology_cancel.step"
            cq.exporters.export(cq.Workplane("XY").box(1, 1, 1), str(step_path))
            cancelled = False

            def sample_then_cancel(*_args: object, **_kwargs: object) -> list[object]:
                nonlocal cancelled
                cancelled = True
                return []

            with mock.patch(
                "five_axis_slicer.step_loader.sample_edge_points",
                side_effect=sample_then_cancel,
            ):
                with self.assertRaises(StepLoadCancelled):
                    load_step(step_path, cancel_check=lambda: cancelled)


if __name__ == "__main__":
    unittest.main()
