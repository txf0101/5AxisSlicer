from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.gcode_preview import (
    load_gcode,
    normalize_role,
    parse_gcode,
    preview_from_json,
    preview_to_json,
)
from five_axis_slicer.manufacturing.preview_kinematics import (
    GENERIC_XYZAC_AC_SEMANTICS,
)


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
        preview = parse_gcode(
            text,
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )

        extrusions = [
            segment for segment in preview.segments if segment.move_type == "extrude"
        ]
        self.assertEqual(
            [segment.extrusion_role for segment in extrusions],
            ["external_perimeter", "internal_infill"],
        )
        self.assertEqual(preview.move_counts["retract"], 1)
        self.assertEqual(preview.rotary_axes, ["A", "C"])
        self.assertEqual(extrusions[0].width, 0.42)
        self.assertEqual(preview.layer_min, 0)
        self.assertEqual(preview.layer_max, 0)
        self.assertEqual(preview.summary()["timeline_step_count"], 4)

    def test_height_width_defaults_and_inheritance_feed_beads(self) -> None:
        text = """
G90
M83
;LAYER_CHANGE
;TYPE:Outer wall
G1 X0 Y0 Z0.2
G1 X1 Y0 E0.1
;HEIGHT:0.32
;WIDTH:0.55
G1 X2 Y0 E0.1
"""
        preview = parse_gcode(
            text,
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )

        extrusions = [
            segment for segment in preview.segments if segment.move_type == "extrude"
        ]
        self.assertEqual(extrusions[0].width, 0.4)
        self.assertEqual(extrusions[0].height, 0.2)
        self.assertEqual(extrusions[1].width, 0.55)
        self.assertEqual(extrusions[1].height, 0.32)
        self.assertEqual(preview.summary()["height_range"], {"min": 0.2, "max": 0.32})

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
        preview = parse_gcode(
            text,
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )
        segment = preview.segments[0]

        self.assertEqual(
            preview.summary()["coordinate_transform"],
            "ac_inverse_rz_minus_c_after_rx_minus_a",
        )
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
        self.assertEqual(preview.summary()["timeline_step_count"], 3)
        self.assertEqual(
            [step.move_type for step in preview.timeline],
            ["travel", "retract", "prime"],
        )
        self.assertEqual(preview.move_counts["travel"], 1)
        self.assertEqual(preview.move_counts["retract"], 1)
        self.assertEqual(preview.move_counts["prime"], 1)

    def test_progress_state_is_layer_filtered_and_keeps_pure_e_steps(self) -> None:
        text = """
G90
M83
;LAYER_CHANGE
G1 X0 Y0 Z0.2
G1 X1 Y0 E0.1
G1 E-0.1
;LAYER_CHANGE
G1 X2 Y0 E0.1
"""
        preview = parse_gcode(text)

        layer_zero = preview.progress_state(0, 0, 2)
        layer_one = preview.progress_state(1, 1, 0)

        self.assertEqual(layer_zero["layer_step_count"], 3)
        self.assertEqual(layer_zero["current_step"]["move_type"], "retract")
        self.assertEqual(layer_one["layer_step_count"], 1)
        self.assertEqual(layer_one["current_global_step"], 3)

    def test_timeline_remains_full_when_path_segments_are_sampled(self) -> None:
        text = """
G90
M83
;LAYER_CHANGE
G1 X0 Y0 Z0.2
G1 X1 Y0 E0.1
G1 X2 Y0 E0.1
G1 X3 Y0 E0.1
"""
        preview = parse_gcode(text, sample_stride=2)

        self.assertEqual(preview.summary()["segment_count"], 4)
        self.assertEqual(preview.summary()["timeline_step_count"], 4)
        self.assertEqual(len(preview.segments), 2)
        self.assertEqual([segment.step_index for segment in preview.segments], [1, 3])

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

    def test_nonzero_b_keeps_raw_machine_preview_and_reports_issue(self) -> None:
        preview = parse_gcode(
            "G90\nM83\nG1 X1 Y2 Z3 A45 B10 E0.1\n",
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )
        segment = preview.segments[0]

        self.assertEqual(segment.end, segment.machine_end)
        self.assertEqual(segment.coordinate_transform, "machine_xyz")
        self.assertEqual(preview.summary()["coordinate_transform"], "machine_xyz")
        self.assertEqual(
            [issue.code for issue in preview.validation_issues],
            ["nc_preview.rotary_words_unsupported"],
        )
        self.assertEqual(
            preview.summary()["validation_issues"][0]["context"][
                "unsupported_rotary_words"
            ],
            ["B"],
        )

    def test_unregistered_secondary_words_keep_complete_file_in_machine_space(
        self,
    ) -> None:
        for word in ("U", "V", "W"):
            with self.subTest(word=word):
                preview = parse_gcode(
                    f"G1 X1 Y2 Z3 A45 {word}0 E0.1\n",
                    controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
                )

                self.assertEqual(preview.segments[0].end, (1.0, 2.0, 3.0))
                self.assertEqual(
                    preview.segments[0].coordinate_transform,
                    "machine_xyz",
                )
                self.assertEqual(
                    preview.validation_issues[0].code,
                    "nc_preview.rotary_words_unsupported",
                )

    def test_unconfirmed_semantics_is_the_safe_default_for_rotary_nc(self) -> None:
        preview = parse_gcode("G1 X1 Y2 Z3 A45 C10 E0.1\n")

        self.assertIsNone(preview.controller_semantics)
        self.assertEqual(preview.coordinate_transform, "machine_xyz")
        self.assertEqual(preview.segments[0].end, (1.0, 2.0, 3.0))
        self.assertEqual(
            [issue.code for issue in preview.validation_issues],
            ["nc_preview.controller_semantics_unknown"],
        )

    def test_a_b_a_file_never_mixes_machine_and_workpiece_segments(self) -> None:
        preview = parse_gcode(
            "\n".join(
                (
                    "G90",
                    "M83",
                    "G1 X1 Y0 Z0 A30 E0.1",
                    "G1 X2 Y0 Z0 B10 E0.1",
                    "G1 X3 Y0 Z0 A45 B0 E0.1",
                )
            ),
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )

        self.assertEqual(preview.coordinate_transform, "machine_xyz")
        self.assertEqual(
            {segment.coordinate_transform for segment in preview.segments},
            {"machine_xyz"},
        )
        self.assertTrue(
            all(segment.end == segment.machine_end for segment in preview.segments)
        )
        self.assertEqual(
            [issue.code for issue in preview.validation_issues],
            ["nc_preview.rotary_words_unsupported"],
        )
        self.assertEqual(
            preview.validation_issues[0].context["unsupported_rotary_words"],
            ("B",),
        )

    def test_confirmed_ac_file_uses_one_transform_for_zero_and_rotary_segments(
        self,
    ) -> None:
        preview = parse_gcode(
            "G90\nM83\nG1 X1 Y0 Z0\nG1 X2 Y0 Z0 A30\nG1 X3 Y0 Z0 A0\n",
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )

        self.assertEqual(
            {segment.coordinate_transform for segment in preview.segments},
            {"ac_inverse_rz_minus_c_after_rx_minus_a"},
        )
        self.assertEqual(
            {step.coordinate_transform for step in preview.timeline},
            {"ac_inverse_rz_minus_c_after_rx_minus_a"},
        )

    def test_unknown_controller_semantics_keeps_raw_machine_preview(self) -> None:
        preview = parse_gcode(
            "G1 X1 Y2 Z3 A45 E0.1\n",
            controller_semantics="unknown.controller.v1",
        )

        self.assertEqual(preview.segments[0].end, (1.0, 2.0, 3.0))
        self.assertEqual(preview.controller_semantics, "unknown.controller.v1")
        self.assertEqual(
            preview.validation_issues[0].code,
            "nc_preview.controller_semantics_unknown",
        )

    def test_preview_json_round_trip_preserves_kinematic_diagnostics(self) -> None:
        preview = parse_gcode(
            "G1 X1 Y2 Z3 B10 E0.1\n",
            controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
        )

        restored = preview_from_json(
            json.loads(preview_to_json(preview)),
            Path("restored.gcode"),
        )

        self.assertEqual(restored.controller_semantics, preview.controller_semantics)
        self.assertEqual(
            [issue.to_json() for issue in restored.validation_issues],
            [issue.to_json() for issue in preview.validation_issues],
        )


if __name__ == "__main__":
    unittest.main()
