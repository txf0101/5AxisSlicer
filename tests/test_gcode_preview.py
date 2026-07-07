from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.gcode_preview import load_gcode, normalize_role, parse_gcode


class GCodePreviewTests(unittest.TestCase):
    def test_maps_orca_type_tags_and_relative_extrusion(self) -> None:
        text = """
G90
M83
;LAYER_CHANGE
;TYPE:Outer wall
;WIDTH:0.42
G1 X0 Y0 Z0.2 F3000
G1 X10 Y0 E0.5 F1200
G1 E-1.2 F1800
;TYPE:Sparse infill
G1 X10 Y10 E0.4 A12 C-3
"""
        preview = parse_gcode(text)

        extrusions = [segment for segment in preview.segments if segment.move_type == "extrude"]
        self.assertEqual([segment.extrusion_role for segment in extrusions], ["external_perimeter", "internal_infill"])
        self.assertEqual(preview.move_counts["retract"], 1)
        self.assertEqual(preview.rotary_axes, ["A", "C"])
        self.assertEqual(extrusions[0].width, 0.42)
        self.assertEqual(preview.layer_min, 0)
        self.assertEqual(preview.layer_max, 0)

    def test_reads_fractal_layer_comments_and_absolute_e(self) -> None:
        text = """
M82
;Layer 7
;Brim
G0 F1800.0 z0.2 A0 B0
G1 F3000.0 X1 Y0 z0.2 A0 B0 E0.25
G1 F1200.0 E0.1 ; Retraction
G1 F1200.0 E0.25 ; Reversed Retraction
"""
        preview = parse_gcode(text)

        self.assertEqual(preview.layer_min, 7)
        self.assertEqual(preview.role_counts["skirt_brim"], 1)
        self.assertEqual(preview.move_counts["travel"], 1)
        self.assertEqual(preview.move_counts["retract"], 1)
        self.assertEqual(preview.move_counts["prime"], 1)
        self.assertEqual(preview.rotary_axes, [])

    def test_loads_gcode_file_and_keeps_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.gcode"
            path.write_text(";TYPE:Support interface\nG1 X1 Y0 E1\n", encoding="utf-8")
            preview = load_gcode(path)

        self.assertEqual(preview.summary()["segment_count"], 1)
        self.assertEqual(preview.role_counts["support_interface"], 1)

    def test_unknown_type_falls_back_to_unknown(self) -> None:
        self.assertEqual(normalize_role("Not A Known Role"), "unknown")


if __name__ == "__main__":
    unittest.main()
