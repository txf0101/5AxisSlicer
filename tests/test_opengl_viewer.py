from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from five_axis_slicer.gcode_preview import (  # noqa: E402
    GCodePathSegment,
    GCodePreview,
    GCodeTimelineStep,
    PreviewSettings,
    _timeline_arrays_from_steps,
)
from five_axis_slicer.opengl_viewer import (  # noqa: E402
    PAPER_PATH_COLOR,
    OpenGLModelViewer,
    _EdgeSegment,
    _build_continuous_line_strips,
    _build_paper_path_arrays,
)
from five_axis_slicer.models import SelectionState  # noqa: E402
from five_axis_slicer.viewer import ModelViewer  # noqa: E402


class OpenGLPaperPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_continuous_segments_join_within_tolerance_and_break_on_style(self) -> None:
        starts = np.asarray(
            [
                (0.0, 0.0, 0.0),
                (1.019, 0.0, 0.0),
                (2.0, 0.0, 0.0),
                (3.0, 0.0, 0.0),
            ],
            dtype=np.float32,
        )
        ends = np.asarray(
            [
                (1.0, 0.0, 0.0),
                (2.0, 0.0, 0.0),
                (3.0, 0.0, 0.0),
                (4.0, 0.0, 0.0),
            ],
            dtype=np.float32,
        )
        colors = np.ones((4, 4), dtype=np.float32)
        styles = np.asarray([1, 1, 0, 0], dtype=np.uint8)

        vertices, vertex_colors, draw_starts, draw_counts = _build_continuous_line_strips(
            starts,
            ends,
            colors,
            styles,
            tolerance=0.02,
        )

        self.assertEqual(draw_starts.tolist(), [0, 3])
        self.assertEqual(draw_counts.tolist(), [3, 3])
        self.assertEqual(vertices.shape, (6, 3))
        self.assertEqual(vertex_colors.shape, (6, 4))
        np.testing.assert_allclose(vertices[:3], [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)])

    def test_paper_path_reads_full_timeline_arrays_instead_of_sampled_segments(self) -> None:
        steps = [
            _step(0, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), "extrude", 0.1),
            _step(1, (1.01, 0.0, 0.0), (2.0, 0.0, 0.0), "extrude", 0.1),
            _step(2, (2.0, 0.0, 0.0), (5.0, 0.0, 0.0), "travel", 0.0),
            _step(3, (5.0, 0.0, 0.0), (6.0, 0.0, 0.0), "extrude", 0.2),
            _step(4, (6.0, 0.0, 0.0), (7.0, 0.0, 0.0), "extrude", 0.0),
        ]
        sampled = [
            GCodePathSegment(
                step_index=0,
                line_number=1,
                layer=0,
                start=steps[0].start,
                end=steps[0].end,
                move_type="extrude",
                extrusion_role="perimeter",
                delta_e=0.1,
            )
        ]
        preview = GCodePreview(
            source_path=Path("full-timeline.gcode"),
            segments=sampled,
            total_segment_count=5,
            layer_min=0,
            layer_max=0,
            bounds=((0.0, 0.0, 0.0), (7.0, 0.0, 0.0)),
            move_counts={"extrude": 4, "travel": 1},
            role_counts={"perimeter": 4},
            rotary_axes=["A", "C"],
            timeline_arrays=_timeline_arrays_from_steps(steps),
        )
        settings = PreviewSettings(
            layer_min=0,
            layer_max=0,
            show_travel=False,
            show_extrusion=True,
            show_pose_samples=False,
            quality_mode="paper",
        )

        arrays = _build_paper_path_arrays(preview, settings, current_global_step=None)

        self.assertEqual(arrays.segment_count, 3)
        self.assertEqual(arrays.draw_counts.tolist(), [3, 2])
        self.assertEqual(arrays.first_point, (0.0, 0.0, 0.0))
        self.assertEqual(arrays.last_point, (6.0, 0.0, 0.0))
        np.testing.assert_allclose(arrays.colors[0], PAPER_PATH_COLOR)

    def test_paper_path_honours_progress_without_reconstructing_steps(self) -> None:
        steps = [
            _step(0, (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), "extrude", 0.1),
            _step(1, (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), "extrude", 0.1),
        ]
        preview = GCodePreview(
            source_path=Path("progress.gcode"),
            segments=[],
            total_segment_count=2,
            layer_min=0,
            layer_max=0,
            bounds=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
            move_counts={"extrude": 2},
            role_counts={"perimeter": 2},
            rotary_axes=[],
            timeline_arrays=_timeline_arrays_from_steps(steps),
        )
        settings = PreviewSettings(
            layer_min=0,
            layer_max=0,
            show_travel=False,
            show_extrusion=True,
            show_pose_samples=False,
            show_upcoming=False,
            quality_mode="paper",
        )

        arrays = _build_paper_path_arrays(preview, settings, current_global_step=0)

        self.assertEqual(arrays.segment_count, 1)
        self.assertEqual(arrays.draw_counts.tolist(), [2])
        self.assertEqual(arrays.last_point, (1.0, 0.0, 0.0))

    def test_clear_model_removes_cpu_geometry_and_pick_identity(self) -> None:
        viewer = OpenGLModelViewer()
        self.addCleanup(viewer.deleteLater)
        viewer.model = object()  # type: ignore[assignment]
        viewer.selection.body_ids.add("body_001")
        viewer.selection.edge_ids.add("edge_001")
        viewer._edge_segments.append(
            _EdgeSegment("edge_001", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
        )
        viewer._pick_id_to_edge[1] = "edge_001"
        for key in ("model", "edge", "edge_selected", "edge_pick"):
            viewer._set_buffer(
                key,
                [(0.0, 0.0, 0.0)],
                [(1.0, 1.0, 1.0, 1.0)],
                1,
            )

        viewer.clear_model()

        self.assertIsNone(viewer.model)
        self.assertFalse(viewer.selection.body_ids)
        self.assertFalse(viewer.selection.edge_ids)
        self.assertEqual(viewer._edge_segments, [])
        self.assertEqual(viewer._pick_id_to_edge, {})
        self.assertTrue(
            all(viewer._buffers[key].count == 0 for key in ("model", "edge", "edge_selected", "edge_pick"))
        )


class VtkClearModelContractTests(unittest.TestCase):
    def test_clear_model_removes_all_body_and_edge_actors(self) -> None:
        body_actor = object()
        edge_actor = object()

        class RendererStub:
            def __init__(self) -> None:
                self.removed: list[object] = []
                self.reset_count = 0

            def RemoveActor(self, actor: object) -> None:  # noqa: N802 - VTK API spelling
                self.removed.append(actor)

            def ResetCameraClippingRange(self) -> None:  # noqa: N802 - VTK API spelling
                self.reset_count += 1

        class ViewerStub:
            def __init__(self) -> None:
                self.model = object()
                self.selection = SelectionState(
                    body_ids={"body_001"},
                    edge_ids={"edge_001"},
                )
                self.body_actors = {"body_001": body_actor}
                self.edge_actors = {"edge_001": edge_actor}
                self.actor_records = {body_actor: object(), edge_actor: object()}
                self.edge_to_body = {"edge_001": "body_001"}
                self.renderer = RendererStub()
                self.render_count = 0

            def render(self) -> None:
                self.render_count += 1

        viewer = ViewerStub()
        ModelViewer.clear_model(viewer)  # type: ignore[arg-type]

        self.assertIsNone(viewer.model)
        self.assertFalse(viewer.selection.body_ids)
        self.assertFalse(viewer.selection.edge_ids)
        self.assertEqual(viewer.renderer.removed, [body_actor, edge_actor])
        self.assertEqual(viewer.body_actors, {})
        self.assertEqual(viewer.edge_actors, {})
        self.assertEqual(viewer.actor_records, {})
        self.assertEqual(viewer.edge_to_body, {})
        self.assertEqual(viewer.renderer.reset_count, 1)
        self.assertEqual(viewer.render_count, 1)


def _step(
    index: int,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    move_type: str,
    delta_e: float,
) -> GCodeTimelineStep:
    return GCodeTimelineStep(
        step_index=index,
        line_number=index + 1,
        layer=0,
        start=start,
        end=end,
        move_type=move_type,
        extrusion_role="perimeter",
        delta_e=delta_e,
        has_spatial_axis=True,
        has_spatial_length=True,
    )


if __name__ == "__main__":
    unittest.main()
