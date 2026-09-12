from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"


_VTK_TUBE_SMOKE_SCRIPT = textwrap.dedent(
    r"""
    from __future__ import annotations

    import json
    import math
    from pathlib import Path
    import sys

    import numpy as np
    from PyQt5.QtCore import QPoint
    from PyQt5.QtWidgets import QApplication

    from five_axis_slicer.models import (
        BuildSurfaceOverlay,
        CoordinateFrameOverlay,
        PickRequest,
    )
    from five_axis_slicer.step_loader import load_step
    from five_axis_slicer.viewer import VtkModelViewer


    def vtk_matrix_values(matrix):
        return np.asarray(
            [
                [matrix.GetElement(row, column) for column in range(4)]
                for row in range(4)
            ],
            dtype=float,
        )


    step_path = Path(sys.argv[1]).resolve()
    model = load_step(step_path)
    assert len(model.bodies) == 2
    assert sorted(len(body.face_ids) for body in model.bodies) == [3, 8]
    assert len(model.faces) == 11
    assert len(model.edges) == 17
    assert len(model.vertices) == 10

    app = QApplication.instance() or QApplication([])
    viewer = VtkModelViewer()
    viewer.resize(640, 480)
    render_window = viewer.GetRenderWindow()
    render_window.SetOffScreenRendering(1)
    render_window.SetSize(640, 480)

    try:
        viewer.load_model(model)
        assert set(viewer.body_actors) == set(model.body_map)
        assert set(viewer.face_actors) == set(model.face_map)
        assert set(viewer.edge_actors) == set(model.edge_map)
        assert set(viewer.vertex_actors) == set(model.vertex_map)
        assert len(viewer.actor_records) == 40

        for actor in viewer.body_actors.values():
            actor.GetMapper().Update()
            assert actor.GetMapper().GetInput().GetNumberOfPolys() > 0
        for actor in viewer.face_actors.values():
            actor.GetMapper().Update()
            assert actor.GetMapper().GetInput().GetNumberOfPolys() > 0
        for actor in viewer.edge_actors.values():
            actor.GetMapper().Update()
            assert actor.GetMapper().GetInput().GetNumberOfPoints() > 1
        for actor in viewer.vertex_actors.values():
            actor.GetMapper().Update()
            assert actor.GetMapper().GetInput().GetNumberOfPoints() > 0

        topology = {
            "body": (model.bodies[0].body_id, True),
            "face": (model.faces[0].face_id, False),
            "edge": (model.edges[0].edge_id, True),
            "vertex": (model.vertices[0].vertex_id, False),
        }
        selection_events = []
        viewer.set_selection_callback(
            lambda kind, entity_id: selection_events.append((kind, entity_id))
        )
        for kind, (entity_id, multiple) in topology.items():
            viewer.set_pick_request(PickRequest(kind, multiple=multiple))
            assert viewer.selection.mode == kind
            assert viewer.pick_request == PickRequest(kind, multiple=multiple)
            viewer.clear_selection()
            viewer._apply_pick(kind, entity_id)
            assert getattr(viewer.selection, f"{kind}_ids") == {entity_id}
            viewer._apply_pick(kind, entity_id)
            expected_after_second_pick = set() if multiple else {entity_id}
            assert getattr(viewer.selection, f"{kind}_ids") == expected_after_second_pick
            viewer.set_selection(**{f"{kind}_ids": [entity_id]})
            assert getattr(viewer.selection, f"{kind}_ids") == {entity_id}
            actors = getattr(viewer, f"{kind}_actors")
            assert actors[entity_id].GetPickable() == 1
        assert len(selection_events) == 8

        frames = (
            CoordinateFrameOverlay(
                "model",
                "Model",
                (0.0, 0.0, 0.0),
                scale=18.0,
            ),
            CoordinateFrameOverlay(
                "build",
                "Build",
                (25.0, -10.0, 5.0),
                x_axis=(0.0, 1.0, 0.0),
                y_axis=(-1.0, 0.0, 0.0),
                z_axis=(0.0, 0.0, 1.0),
                scale=16.0,
            ),
            CoordinateFrameOverlay(
                "machine",
                "Machine",
                (-40.0, 15.0, -8.0),
                scale=22.0,
            ),
        )
        viewer.set_coordinate_frames(frames, active_frame_id="build")
        assert set(viewer.coordinate_actors) == {"model", "build", "machine"}
        assert all(actor.GetPickable() == 0 for actor in viewer.coordinate_actors.values())
        build_matrix = vtk_matrix_values(viewer.coordinate_actors["build"].GetUserMatrix())
        np.testing.assert_allclose(build_matrix[:3, 3], (25.0, -10.0, 5.0))
        np.testing.assert_allclose(build_matrix[:3, 0], (0.0, 1.0, 0.0))

        plate = BuildSurfaceOverlay(
            "plate",
            "rectangle",
            origin=(-40.0, 15.0, -8.0),
            x_axis=(1.0, 0.0, 0.0),
            y_axis=(0.0, 1.0, 0.0),
            width_mm=260.0,
            depth_mm=220.0,
        )
        viewer.set_build_surface(plate)
        assert viewer.build_surface_actor is not None
        viewer.build_surface_actor.GetMapper().Update()
        plate_data = viewer.build_surface_actor.GetMapper().GetInput()
        assert plate_data.GetNumberOfPoints() == 4
        assert plate_data.GetNumberOfLines() == 1
        assert viewer.build_surface_actor.GetPickable() == 0

        angle = math.radians(32.0)
        fixture_transform = np.asarray(
            [
                [math.cos(angle), -math.sin(angle), 0.0, 42.0],
                [math.sin(angle), math.cos(angle), 0.0, -17.0],
                [0.0, 0.0, 1.0, 9.5],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        )
        viewer.set_model_transform(fixture_transform)
        np.testing.assert_allclose(viewer._model_transform, fixture_transform)
        topology_actors = (
            tuple(viewer.body_actors.values())
            + tuple(viewer.face_actors.values())
            + tuple(viewer.edge_actors.values())
            + tuple(viewer.vertex_actors.values())
        )
        assert len(topology_actors) == 40
        for actor in topology_actors:
            np.testing.assert_allclose(
                vtk_matrix_values(actor.GetUserMatrix()),
                fixture_transform,
                atol=1.0e-9,
            )

        viewer.fit_view()
        render_window.Render()
        app.processEvents()

        camera = viewer.renderer.GetActiveCamera()
        anchor = QPoint(470, 190)
        anchor_before = viewer._vtk_camera.focal_plane_point(anchor)
        viewer._view_zoom(1.12, anchor)
        anchor_after = viewer._vtk_camera.focal_plane_point(anchor)
        np.testing.assert_allclose(anchor_after, anchor_before, atol=1.0e-8)

        forward = np.asarray(camera.GetDirectionOfProjection())
        right = np.cross(forward, np.asarray(camera.GetViewUp()))
        right /= np.linalg.norm(right)
        focal_before = np.asarray(camera.GetFocalPoint())
        viewer._view_pan(24, 0)
        pan_offset = np.asarray(camera.GetFocalPoint()) - focal_before
        assert np.dot(pan_offset, right) < 0.0
        assert abs(np.dot(pan_offset, forward)) < 1.0e-8

        viewer.set_selection(body_ids=[model.bodies[0].body_id])
        for actor in viewer.actor_records:
            actor.SetPickable(False)
        viewer._view_left_click(QPoint(320, 240))
        assert not viewer.selection.body_ids
        assert selection_events[-1] == (None, None)

        print(
            json.dumps(
                {
                    "status": "ok",
                    "actors": {
                        "body": len(viewer.body_actors),
                        "face": len(viewer.face_actors),
                        "edge": len(viewer.edge_actors),
                        "vertex": len(viewer.vertex_actors),
                        "coordinate": len(viewer.coordinate_actors),
                        "build_surface": int(viewer.build_surface_actor is not None),
                    },
                    "offscreen": bool(render_window.GetOffScreenRendering()),
                },
                sort_keys=True,
            ),
            flush=True,
        )
    finally:
        viewer.set_build_surface(None)
        viewer.set_coordinate_frames(())
        viewer.clear_model()
        render_window.Finalize()
        viewer.close()
        viewer.deleteLater()
        app.processEvents()
        app.quit()
    """
)


class VtkTubeOffscreenSmokeTests(unittest.TestCase):
    def test_pipe2_topology_overlays_and_fixture_transform_in_isolated_process(
        self,
    ) -> None:
        step_files = list((ROOT / "example" / "pipe2").glob("*.stp"))
        self.assertEqual(len(step_files), 1, "pipe2 must contain one STEP golden source")
        environment = os.environ.copy()
        # Standard VTK wheels still need a native OpenGL context even when the
        # render window's offscreen flag is enabled.
        if os.name == "nt":
            environment["QT_QPA_PLATFORM"] = "windows"
        elif sys.platform == "darwin":
            environment["QT_QPA_PLATFORM"] = "cocoa"
        elif environment.get("DISPLAY"):
            environment["QT_QPA_PLATFORM"] = "xcb"
        elif environment.get("WAYLAND_DISPLAY"):
            environment["QT_QPA_PLATFORM"] = "wayland"
        else:
            self.skipTest("standard VTK wheel has no native headless OpenGL context")
        environment["FIVE_AXIS_RENDER_BACKEND"] = "vtk"
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(
                None,
                (str(SOURCE_ROOT), environment.get("PYTHONPATH", "")),
            )
        )

        completed = subprocess.run(
            [sys.executable, "-c", _VTK_TUBE_SMOKE_SCRIPT, str(step_files[0])],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            f"isolated VTK smoke failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        self.assertNotIn(" ERR|", completed.stderr, completed.stderr)
        self.assertNotIn("Traceback", completed.stderr, completed.stderr)
        records = []
        for line in completed.stdout.splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        self.assertTrue(records, f"missing smoke result in stdout:\n{completed.stdout}")
        self.assertEqual(
            records[-1],
            {
                "actors": {
                    "body": 2,
                    "build_surface": 1,
                    "coordinate": 3,
                    "edge": 17,
                    "face": 11,
                    "vertex": 10,
                },
                "offscreen": True,
                "status": "ok",
            },
        )


if __name__ == "__main__":
    unittest.main()
