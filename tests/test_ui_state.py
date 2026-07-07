from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication

from five_axis_slicer.gcode_preview import PreviewSettings, parse_gcode
from five_axis_slicer.ui import MainWindow


class UiStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_workbench_and_language_state_are_exposed(self) -> None:
        window = MainWindow(http_port=0)
        self.addCleanup(window.close)

        window.enter_workbench("freeform")
        self.assertEqual(window.current_state()["workbench"]["workbench"], "freeform")

        window.toggle_language()
        self.assertEqual(window.current_state()["language"], "en")
        self.assertIn("Imported NC", window.operation_combo.itemText(0))

    def test_preview_visibility_endpoint_updates_settings(self) -> None:
        window = MainWindow(http_port=0)
        self.addCleanup(window.close)

        result = window.handle_automation(
            "/preview/visibility",
            {"show_travel": False, "show_extrusion": True, "visible_roles": ["external_perimeter"]},
        )
        settings = result["preview"]["settings"]
        self.assertFalse(settings["show_travel"])
        self.assertEqual(settings["visible_roles"], ["external_perimeter"])

    def test_parameter_labels_and_segment_panel_are_translated(self) -> None:
        window = MainWindow(http_port=0)
        self.addCleanup(window.close)

        preview = parse_gcode(
            """
;LAYER_CHANGE
;TYPE:External perimeter
G1 X0 Y0 Z0.2 F3000
G1 X1 Y0 E0.4 A12 C-4 F1200
"""
        )
        window.gcode_preview = preview
        window.viewer.gcode_preview = preview
        window.viewer.preview_settings = PreviewSettings(
            layer_min=preview.layer_min,
            layer_max=preview.layer_max,
        )
        window.viewer.visible_path_segment_count = len(preview.segments)
        window._sync_preview_controls()

        self.assertIn("行号", window.segment_property.text())
        window.toggle_language()
        self.assertEqual(window.segment_property_title.text(), "Segment Properties")
        self.assertEqual(window.localized_groups[0][0].title(), "Layer and Bead")


if __name__ == "__main__":
    unittest.main()
