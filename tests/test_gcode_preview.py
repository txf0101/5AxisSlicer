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

    def test_ac_rotary_coordinates_are_inversed_for_preview(self) -> None:
        text = """
G90
M83
;LAYER_CHANGE
;TYPE:External perimeter
G1 F600 X0 Y-42 Z12.2 A90 C-162 E0.1
"""
        preview = parse_gcode(text)
        segment = preview.segments[0]

        self.assertEqual(preview.summary()["coordinate_transform"], "ac_inverse_rz_minus_c_after_rx_minus_a")
        self.assertEqual(segment.machine_end, (0.0, -42.0, 12.2))
        self.assertAlmostEqual(segment.end[2], 42.0, places=6)
        self.assertNotAlmostEqual(segment.end[1], segment.machine_end[1], places=3)

    def test_pure_e_moves_are_counted_but_not_path_segments(self) -> None:
        text = """
G90
M83
;LAYER_CHANGE
G1 X1 Y0 F1200
G1 E-1 F1800
G1 E1 F1800
"""
        preview = parse_gcode(text)

        self.assertEqual(preview.summary()["segment_count"], 1)
        self.assertEqual(len(preview.segments), 1)
        self.assertEqual(preview.move_counts["travel"], 1)
        self.assertEqual(preview.move_counts["retract"], 1)
        self.assertEqual(preview.move_counts["prime"], 1)

    def test_zero_length_spatial_line_keeps_matlab_segment_count(self) -> None:
        text = """
G90
M83
;LAYER_CHANGE
G1 X0 Y0 Z0 A0 C0 F1200
G1 X1 Y0 E0.1
"""
        preview = parse_gcode(text)

        self.assertEqual(preview.summary()["segment_count"], 2)
        self.assertEqual(preview.move_counts["travel"], 1)
        self.assertEqual(preview.move_counts["extrude"], 1)
        self.assertFalse(preview.segments[0].has_spatial_length)

    def test_modal_g1_lines_follow_previous_motion_command(self) -> None:
        text = """
G90
M83
;LAYER_CHANGE
G1 X0 Y0 Z0.2 F1000
X1 Y0 E0.1
Y1 E0.1
"""
        preview = parse_gcode(text)

        self.assertEqual(preview.summary()["segment_count"], 3)
        self.assertEqual(preview.move_counts["extrude"], 2)
        self.assertAlmostEqual(preview.segments[-1].end[1], 1.0)

    def test_units_and_g92_apply_to_machine_axes_and_absolute_e(self) -> None:
        text = """
G20
G90
M82
;LAYER_CHANGE
G92 X1 Y0 Z0 E3
G1 X2 Y0 E4
G1 E3.5
G1 X2 Y0
G1 X2.5 Y0 E4.25
"""
        preview = parse_gcode(text)

        self.assertEqual(preview.summary()["segment_count"], 3)
        self.assertEqual(preview.move_counts["extrude"], 2)
        self.assertEqual(preview.move_counts["retract"], 1)
        self.assertEqual(preview.move_counts["travel"], 1)
        self.assertAlmostEqual(preview.segments[0].machine_start[0], 25.4)
        self.assertAlmostEqual(preview.segments[0].machine_end[0], 50.8)
        self.assertAlmostEqual(preview.segments[-1].machine_end[0], 63.5)


if __name__ == "__main__":
    unittest.main()
