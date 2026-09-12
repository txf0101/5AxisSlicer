from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from five_axis_slicer.gcode_preview import (  # noqa: E402
    GCodePathSegment,
    GCodePreview,
    PreviewSettings,
)
from five_axis_slicer.models import PickRequest, SelectionState  # noqa: E402
from five_axis_slicer.opengl_viewer import OpenGLModelViewer  # noqa: E402
from five_axis_slicer.viewer_common import (  # noqa: E402
    SceneCaptureCapability,
    ViewerProtocol,
    apply_pick_selection,
    representative_path_segment,
)


def test_viewer_protocols_expose_common_and_scene_capture_capabilities() -> None:
    app = QApplication.instance() or QApplication([])
    viewer = OpenGLModelViewer()
    try:
        assert isinstance(viewer, ViewerProtocol)
        assert isinstance(viewer, SceneCaptureCapability)
    finally:
        viewer.deleteLater()
        app.processEvents()


def test_pick_selection_enforces_request_kind_cardinality_and_allowlist() -> None:
    selection = SelectionState()
    single_face = PickRequest("face", frozenset({"face_a", "face_b"}))

    assert apply_pick_selection(selection, single_face, "face", "face_a")
    assert apply_pick_selection(selection, single_face, "face", "face_b")
    assert selection.face_ids == {"face_b"}
    assert not apply_pick_selection(selection, single_face, "face", "blocked")
    assert not apply_pick_selection(selection, single_face, "edge", "face_b")

    multiple = PickRequest("edge", multiple=True)
    assert apply_pick_selection(selection, multiple, "edge", "edge_a")
    assert apply_pick_selection(selection, multiple, "edge", "edge_a")
    assert not selection.edge_ids


def test_representative_segment_prefers_a_visible_extrusion_without_progress() -> None:
    travel = _segment(0, "travel")
    extrusion = _segment(1, "extrude")
    preview = GCodePreview(
        source_path=Path("representative.gcode"),
        segments=[travel, extrusion],
        total_segment_count=2,
        layer_min=0,
        layer_max=0,
        bounds=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)),
        move_counts={"travel": 1, "extrude": 1},
        role_counts={"perimeter": 1},
        rotary_axes=[],
    )
    settings = PreviewSettings(
        layer_min=0,
        layer_max=0,
        show_travel=True,
        show_extrusion=True,
        visible_roles={"perimeter"},
    )

    assert representative_path_segment(preview, settings) is extrusion


def _segment(step_index: int, move_type: str) -> GCodePathSegment:
    return GCodePathSegment(
        step_index=step_index,
        line_number=step_index + 1,
        layer=0,
        start=(float(step_index), 0.0, 0.0),
        end=(float(step_index + 1), 0.0, 0.0),
        move_type=move_type,
        extrusion_role="perimeter",
        delta_e=0.1 if move_type == "extrude" else 0.0,
    )
