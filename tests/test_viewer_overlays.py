from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget

from five_axis_slicer.viewer_overlays import (
    AxisTriadOverlay,
    OrientationCubeOverlay,
    _FACE_TEXT_RECT,
    _triad_directions,
)


class _ViewerStub:
    def __init__(self) -> None:
        self.views: list[str] = []

    def set_standard_view(self, view: str) -> None:
        self.views.append(view)


class OrientationCubeOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_face_labels_follow_each_projected_face(self) -> None:
        cube = OrientationCubeOverlay()
        self.addCleanup(cube.close)
        image = QImage(cube.size(), QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        cube.render(painter)
        painter.end()

        transforms = cube._face_label_transforms
        self.assertEqual(set(transforms), {"top", "front", "right"})
        source_left = QPointF(_FACE_TEXT_RECT.left(), _FACE_TEXT_RECT.center().y())
        source_right = QPointF(_FACE_TEXT_RECT.right(), _FACE_TEXT_RECT.center().y())
        slopes = {}
        for view, transform in transforms.items():
            left = transform.map(source_left)
            right = transform.map(source_right)
            slopes[view] = right.y() - left.y()
        self.assertGreater(slopes["top"], 5.0)
        self.assertGreater(slopes["front"], 5.0)
        self.assertLess(slopes["right"], -5.0)

    def test_projected_labels_do_not_change_face_hit_targets(self) -> None:
        viewer = _ViewerStub()
        cube = OrientationCubeOverlay(viewer)
        self.addCleanup(cube.close)
        cube.show()
        self.app.processEvents()

        for point, expected in (
            (QPointF(56, 28), "top"),
            (QPointF(38, 58), "front"),
            (QPointF(75, 58), "right"),
        ):
            QTest.mouseClick(cube, Qt.LeftButton, pos=point.toPoint())
            self.assertEqual(viewer.views[-1], expected)


class AxisTriadOverlayTests(unittest.TestCase):
    def test_part_axes_follow_camera_orientation(self) -> None:
        front = _triad_directions(
            {"position": [0, -10, 0], "focal_point": [0, 0, 0], "view_up": [0, 0, 1]}
        )
        right = _triad_directions(
            {"position": [10, 0, 0], "focal_point": [0, 0, 0], "view_up": [0, 0, 1]}
        )
        self.assertGreater(front["X"][0], 0.9)
        self.assertLess(front["Z"][1], -0.9)
        self.assertAlmostEqual(front["Y"][0], 0.0)
        self.assertGreater(right["Y"][0], 0.9)
        self.assertAlmostEqual(right["X"][0], 0.0)

    def test_camera_repaint_updates_overlay(self) -> None:
        app = QApplication.instance() or QApplication([])

        class CameraViewer(QWidget):
            def __init__(self) -> None:
                super().__init__()
                self.position = [0, -10, 0]

            def camera_state(self) -> dict:
                return {
                    "position": self.position,
                    "focal_point": [0, 0, 0],
                    "view_up": [0, 0, 1],
                }

        viewer = CameraViewer()
        overlay = AxisTriadOverlay(viewer)
        self.addCleanup(viewer.close)
        self.addCleanup(overlay.close)
        viewer.show()
        overlay.show()
        app.processEvents()
        before = overlay._camera_signature
        viewer.position = [10, 0, 0]
        viewer.repaint()
        app.processEvents()
        self.assertNotEqual(overlay._camera_signature, before)


if __name__ == "__main__":
    unittest.main()
