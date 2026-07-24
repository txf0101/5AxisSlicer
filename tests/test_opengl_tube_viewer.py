from __future__ import annotations

import math
import os
from pathlib import Path
import sys
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from five_axis_slicer.models import (  # noqa: E402
    BuildSurfaceOverlay,
    CoordinateFrameOverlay,
    PickHit,
    PickRequest,
)
from five_axis_slicer.opengl_viewer import (  # noqa: E402
    OpenGLModelViewer,
    _EdgeSegment,
    _build_surface_lines,
    _ray_triangle_intersection,
    _transform_points,
    _unproject_screen_ray,
    _validated_rigid_transform,
)


class OpenGLTubeViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_viewer(self) -> OpenGLModelViewer:
        viewer = OpenGLModelViewer()
        self.addCleanup(viewer.deleteLater)
        return viewer

    def test_all_topology_modes_share_pick_request_contract(self) -> None:
        viewer = self.make_viewer()

        for kind, multiple in (
            ("body", True),
            ("face", False),
            ("edge", True),
            ("vertex", False),
        ):
            viewer.set_mode(kind)
            self.assertEqual(viewer.selection.mode, kind)
            self.assertEqual(viewer.pick_request, PickRequest(kind, multiple=multiple))

        with self.assertRaisesRegex(ValueError, "Unsupported picking mode"):
            viewer.set_mode("assembly")

    def test_single_and_multiple_pick_requests_update_the_matching_selection(
        self,
    ) -> None:
        viewer = self.make_viewer()
        selection_events: list[tuple[str, str]] = []
        pick_events: list[PickHit] = []
        viewer.set_selection_callback(
            lambda kind, entity_id: selection_events.append((kind, entity_id))
        )
        viewer.set_pick_callback(pick_events.append)

        viewer.set_pick_request(PickRequest("face", frozenset({"face_a", "face_b"})))
        viewer._apply_pick(PickHit("face", "face_a", (1.0, 2.0, 3.0)))
        viewer._apply_pick(PickHit("face", "face_b", (4.0, 5.0, 6.0)))
        viewer._apply_pick(PickHit("face", "face_blocked", (0.0, 0.0, 0.0)))

        self.assertEqual(viewer.selection.face_ids, {"face_b"})
        self.assertEqual(selection_events, [("face", "face_a"), ("face", "face_b")])
        self.assertEqual(
            [hit.position_source for hit in pick_events],
            [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
        )

        viewer.set_pick_request(PickRequest("body", multiple=True))
        viewer._apply_pick(PickHit("body", "body_a"))
        viewer._apply_pick(PickHit("body", "body_b"))
        viewer._apply_pick(PickHit("body", "body_a"))
        self.assertEqual(viewer.selection.body_ids, {"body_b"})

    def test_static_pick_buffers_keep_entity_identity_for_every_topology_kind(
        self,
    ) -> None:
        viewer = self.make_viewer()
        viewer._body_triangles = {
            "body_a": np.asarray([(0, 0, 0), (1, 0, 0), (0, 1, 0)], dtype=np.float32)
        }
        viewer._face_triangles = {
            "face_a": np.asarray([(0, 0, 0), (1, 0, 0), (0, 1, 0)], dtype=np.float32)
        }
        viewer._edge_segments = [_EdgeSegment("edge_a", (0, 0, 0), (1, 0, 0))]
        viewer._vertex_positions = {"vertex_a": (0.0, 0.0, 0.0)}

        class Entity:
            def __init__(self, identifier: str, attribute: str) -> None:
                setattr(self, attribute, identifier)

        class Model:
            bodies = [Entity("body_a", "body_id")]
            faces = [Entity("face_a", "face_id")]

        viewer.model = Model()  # type: ignore[assignment]
        viewer._refresh_pick_buffers()

        self.assertEqual(
            set(viewer._pick_id_to_entity.values()),
            {
                ("body", "body_a"),
                ("face", "face_a"),
                ("edge", "edge_a"),
                ("vertex", "vertex_a"),
            },
        )
        self.assertEqual(viewer._buffers["body_pick"].count, 3)
        self.assertEqual(viewer._buffers["face_pick"].count, 3)
        self.assertEqual(viewer._buffers["edge_pick"].count, 2)
        self.assertEqual(viewer._buffers["vertex_pick"].count, 6)

    def test_coordinate_frames_and_oriented_build_surface_have_dedicated_buffers(
        self,
    ) -> None:
        viewer = self.make_viewer()
        source = CoordinateFrameOverlay("source", "Source", (0.0, 0.0, 0.0), scale=10.0)
        build = CoordinateFrameOverlay("build", "Build", (20.0, 0.0, 0.0), scale=8.0)

        viewer.set_coordinate_frames((source, build), active_frame_id="build")

        self.assertEqual(viewer._buffers["coordinate_frames"].count, 30)
        self.assertEqual(viewer._buffers["coordinate_frames_active"].count, 30)
        self.assertGreater(
            float(np.max(viewer._buffers["coordinate_frames_active"].vertices[:, 0])),
            20.0,
        )

        surface = BuildSurfaceOverlay(
            "plate",
            "rectangle",
            origin=(1.0, 2.0, 3.0),
            x_axis=(0.0, 1.0, 0.0),
            y_axis=(-1.0, 0.0, 0.0),
            width_mm=20.0,
            depth_mm=10.0,
        )
        viewer.set_build_surface(surface)

        plate = viewer._buffers["build_surface"].vertices
        self.assertEqual(plate.shape, (12, 3))
        np.testing.assert_allclose(np.min(plate, axis=0), (-4.0, -8.0, 3.0))
        np.testing.assert_allclose(np.max(plate, axis=0), (6.0, 12.0, 3.0))

    def test_model_transform_requires_a_right_handed_rigid_matrix(self) -> None:
        angle = math.radians(90.0)
        matrix = np.asarray(
            [
                [math.cos(angle), -math.sin(angle), 0.0, 10.0],
                [math.sin(angle), math.cos(angle), 0.0, -2.0],
                [0.0, 0.0, 1.0, 4.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )

        validated = _validated_rigid_transform(matrix)
        transformed = _transform_points(np.asarray([(2.0, 0.0, 1.0)]), validated)
        np.testing.assert_allclose(transformed, ((10.0, 0.0, 5.0),), atol=1e-6)

        for invalid in (
            np.diag((2.0, 1.0, 1.0, 1.0)),
            np.asarray(
                [
                    [-1.0, 0.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0, 0, 0, 1],
                ]
            ),
            np.asarray(
                [
                    [1.0, 0.2, 0.0, 0.0],
                    [0.0, 1.0, 0.0, 0.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0, 0, 0, 1],
                ]
            ),
        ):
            with self.assertRaises(ValueError):
                _validated_rigid_transform(invalid)

    def test_unprojection_and_triangle_intersection_return_source_coordinates(
        self,
    ) -> None:
        model_transform = np.eye(4)
        model_transform[0, 3] = 0.5
        ray = _unproject_screen_ray(75.0, 50.0, 100, 100, model_transform)
        self.assertIsNotNone(ray)
        origin, direction = ray  # type: ignore[misc]
        triangle = np.asarray([(-0.5, -0.5, 0.0), (0.5, -0.5, 0.0), (0.0, 0.5, 0.0)])

        distance = _ray_triangle_intersection(origin, direction, triangle)

        self.assertIsNotNone(distance)
        hit = origin + direction * float(distance)
        np.testing.assert_allclose(hit, (0.0, 0.0, 0.0), atol=1e-7)

    def test_build_surface_rejects_invalid_geometry(self) -> None:
        with self.assertRaisesRegex(ValueError, "dimensions must be positive"):
            _build_surface_lines(
                BuildSurfaceOverlay("bad", "rectangle", width_mm=-1.0, depth_mm=10.0)
            )
        with self.assertRaisesRegex(ValueError, "unsupported build surface shape"):
            _build_surface_lines(BuildSurfaceOverlay("bad", "hexagon"))


if __name__ == "__main__":
    unittest.main()
