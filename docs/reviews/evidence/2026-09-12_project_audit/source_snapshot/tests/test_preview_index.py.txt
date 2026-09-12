from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.gcode_preview import GCodeRenderIndex, parse_gcode
from five_axis_slicer.native_preview_index import build_preview_index


class PreviewIndexTests(unittest.TestCase):
    def test_layer_prefix_matches_progress_queries(self) -> None:
        preview = parse_gcode(
            """
G90
M83
;LAYER_CHANGE
G1 X0 Y0 Z0.2
G1 X1 Y0 E0.1
G1 E-0.1
;LAYER_CHANGE
G1 X2 Y0 E0.1
G1 X3 Y0 E0.1
"""
        )

        index = preview._index()

        self.assertEqual(index.count_for_layers(0, 0), 3)
        self.assertEqual(index.count_for_layers(1, 1), 2)
        self.assertEqual(preview.progress_state(1, 1, 1)["current_global_step"], 4)
        self.assertEqual(preview.segment_index_for_step(1), 1)
        self.assertEqual(preview.nearest_segment_index_for_step(2), 1)

    def test_python_and_native_entry_points_share_shape(self) -> None:
        packed = build_preview_index([0, 0, 1, 1, 2], [0, 2, 4], 0, 2)

        self.assertEqual(packed.layer_prefix_counts.tolist(), [0, 2, 4, 5])
        self.assertEqual(packed.timeline_indices.tolist(), [0, 1, 2, 3, 4])
        self.assertEqual(packed.segment_indices.tolist(), [0, 1, 2])

    def test_npz_round_trip_preserves_lookup_arrays(self) -> None:
        preview = parse_gcode(
            """
;LAYER_CHANGE
G1 X0 Y0 Z0.2
G1 X1 Y0 E0.1
;LAYER_CHANGE
G1 X2 Y0 E0.1
"""
        )
        index = preview._index()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.npz"
            index.to_npz(path)
            loaded = GCodeRenderIndex.from_npz(path, preview.segments)

        self.assertEqual(loaded.count_for_layers(0, 1), index.count_for_layers(0, 1))
        self.assertEqual(loaded.segment_index_for_step(2), index.segment_index_for_step(2))
        self.assertEqual(loaded.cache_format, "json.gz+npz-render-index-v2")


if __name__ == "__main__":
    unittest.main()
