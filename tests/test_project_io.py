from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from five_axis_slicer.models import SelectionState
from five_axis_slicer.project_io import save_project
from five_axis_slicer.gcode_preview import PreviewSettings, parse_gcode
from five_axis_slicer.step_loader import load_step
from test_step_loader import make_two_body_step


class ProjectIoTests(unittest.TestCase):
    def test_saves_project_json_and_source_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path = make_two_body_step(root)
            model = load_step(step_path)
            selection = SelectionState(mode="edge")
            selection.body_ids.add("body_001")
            selection.edge_ids.add(model.bodies[0].edge_ids[0])
            project_json = save_project(root / "project", model, selection)
            payload = json.loads(project_json.read_text(encoding="utf-8"))

            self.assertTrue((root / "project" / "source" / step_path.name).exists())
            self.assertEqual(payload["version"], 1)
            self.assertEqual(payload["model"]["body_count"], 2)
            self.assertEqual(payload["selection"]["mode"], "edge")
            self.assertEqual(payload["manufacturable_feature_groups"], [])
            self.assertIn("preview", payload)

    def test_saves_workbench_and_gcode_preview_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            step_path = make_two_body_step(root)
            gcode_path = root / "demo.gcode"
            gcode_path.write_text(";TYPE:Outer wall\nG1 X1 Y0 E1\n", encoding="utf-8")
            model = load_step(step_path)
            preview = parse_gcode(gcode_path.read_text(encoding="utf-8"), gcode_path)
            settings = PreviewSettings(layer_min=0, layer_max=0, show_travel=False)

            project_json = save_project(
                root / "project",
                model,
                SelectionState(),
                {"workbench": "curve", "operation": "imported_nc_review"},
                preview,
                settings,
            )
            payload = json.loads(project_json.read_text(encoding="utf-8"))

            self.assertEqual(payload["workbench"]["workbench"], "curve")
            self.assertEqual(payload["gcode"]["summary"]["segment_count"], 1)
            self.assertFalse(payload["preview"]["gcode"]["show_travel"])


if __name__ == "__main__":
    unittest.main()
