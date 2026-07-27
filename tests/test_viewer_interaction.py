from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PyQt5.QtGui import QFocusEvent, QMouseEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402

from five_axis_slicer.viewer_interaction import (  # noqa: E402
    BambuNavigationMixin,
    DragAction,
    DragUpdate,
    OpenGLCameraNavigation,
    PointerButton,
    PointerGesture,
    VtkCameraNavigation,
    wheel_zoom_factor,
    z_up_orbit_direction,
)


@pytest.mark.parametrize("yaw_degrees", (0.0, 90.0, 180.0, 270.0))
def test_opengl_downward_drag_raises_z_up_orbit_at_every_azimuth(
    yaw_degrees: float,
) -> None:
    initial_pitch = math.radians(55.0)
    yaw = math.radians(yaw_degrees)
    host = SimpleNamespace(
        _pitch=initial_pitch,
        _yaw=yaw,
        _view_up=None,
        update=Mock(),
    )
    navigation = OpenGLCameraNavigation(host)
    initial_height = z_up_orbit_direction(yaw, initial_pitch)[2]

    navigation.rotate(0, 10)

    assert host._pitch == pytest.approx(initial_pitch - 0.1)
    assert z_up_orbit_direction(yaw, host._pitch)[2] > initial_height
    host.update.assert_called_once_with()

    navigation.rotate(0, -10)
    assert host._pitch == pytest.approx(initial_pitch)


def test_vtk_downward_drag_uses_positive_elevation() -> None:
    camera = Mock()
    renderer = Mock()
    renderer.GetActiveCamera.return_value = camera
    widget = SimpleNamespace(width=lambda: 800, height=lambda: 400)
    render = Mock()
    navigation = VtkCameraNavigation(renderer, widget, lambda: 1.0, render)

    navigation.rotate(8, 10)

    camera.Azimuth.assert_called_once_with(-4.0)
    camera.Elevation.assert_called_once_with(10.0)
    camera.OrthogonalizeViewUp.assert_called_once_with()
    renderer.ResetCameraClippingRange.assert_called_once_with()
    render.assert_called_once_with()


@pytest.mark.parametrize(
    ("azimuth", "zenith", "expected"),
    (
        (180.0, 90.0, (0.0, -1.0, 0.0)),
        (0.0, 90.0, (0.0, 1.0, 0.0)),
        (-90.0, 90.0, (-1.0, 0.0, 0.0)),
        (90.0, 90.0, (1.0, 0.0, 0.0)),
        (0.0, 0.0, (0.0, 0.0, 1.0)),
        (0.0, 180.0, (0.0, 0.0, -1.0)),
    ),
)
def test_z_up_orbit_preserves_standard_view_directions(
    azimuth: float,
    zenith: float,
    expected: tuple[float, float, float],
) -> None:
    direction = z_up_orbit_direction(math.radians(azimuth), math.radians(zenith))

    assert direction == pytest.approx(expected, abs=1.0e-7)


def test_drag_threshold_uses_displacement_from_press_point() -> None:
    gesture = PointerGesture(threshold_px=3)
    gesture.press("left", (0, 0))

    assert gesture.move((1, 0)) is None
    assert gesture.move((2, 0)) is None
    assert gesture.move((3, 0)) == DragUpdate("rotate", 3, 0, True)


def test_returning_to_press_point_remains_a_drag_after_threshold() -> None:
    gesture = PointerGesture(threshold_px=3)
    gesture.press("left", (0, 0))

    assert gesture.move((3, 0)) == DragUpdate("rotate", 3, 0, True)
    assert gesture.move((0, 0)) == DragUpdate("rotate", -3, 0, False)
    assert gesture.release("left") == "drag"


@pytest.mark.parametrize(
    ("button", "action"),
    (("left", "rotate"), ("middle", "pan"), ("right", "pan")),
)
def test_button_maps_to_expected_drag_action(
    button: PointerButton,
    action: DragAction,
) -> None:
    gesture = PointerGesture(threshold_px=3)
    gesture.press(button, (2, 4))

    update = gesture.move((5, 8))

    assert update == DragUpdate(action, 3, 4, True)


def test_wrong_button_release_does_not_commit_click_or_reset_press() -> None:
    gesture = PointerGesture(threshold_px=3)
    gesture.press("left", (0, 0))

    assert gesture.release("right") is None
    assert gesture.button == "left"
    assert gesture.release("left") == "click"


def test_second_button_does_not_replace_an_active_drag() -> None:
    app = QApplication.instance() or QApplication([])
    viewer = _NavigationHarness()
    try:
        viewer.mousePressEvent(_mouse_event(QEvent.MouseButtonPress, 0, Qt.LeftButton))
        distance = viewer._view_gesture.threshold_px
        viewer.mouseMoveEvent(_mouse_event(QEvent.MouseMove, distance, Qt.NoButton, Qt.LeftButton))

        viewer.mousePressEvent(
            _mouse_event(
                QEvent.MouseButtonPress,
                distance,
                Qt.RightButton,
                Qt.LeftButton | Qt.RightButton,
            )
        )
        viewer.mouseReleaseEvent(
            _mouse_event(QEvent.MouseButtonRelease, distance, Qt.RightButton, Qt.LeftButton)
        )

        assert viewer._view_gesture.button == "left"
        assert viewer.finished == 0
        viewer.mouseReleaseEvent(
            _mouse_event(QEvent.MouseButtonRelease, distance, Qt.LeftButton, Qt.NoButton)
        )
        assert viewer.finished == 1
    finally:
        viewer.deleteLater()
        app.processEvents()


def test_empty_gesture_and_zero_wheel_are_no_ops() -> None:
    gesture = PointerGesture(threshold_px=3)

    assert gesture.move((1, 1)) is None
    assert gesture.release("left") is None
    assert not gesture.cancel()
    assert wheel_zoom_factor(0) is None


def test_wheel_notches_preserve_direction_and_magnitude() -> None:
    zoom_in = wheel_zoom_factor(120)
    zoom_out = wheel_zoom_factor(-120)
    two_notches = wheel_zoom_factor(240)

    assert zoom_in is not None and zoom_out is not None and two_notches is not None
    assert zoom_in * zoom_out == pytest.approx(1.0)
    assert two_notches == pytest.approx(zoom_in**2)


@pytest.mark.parametrize("cleanup", ("cancel", "focus", "leave"))
def test_interrupted_drag_cleans_state_and_finishes_interaction(cleanup: str) -> None:
    app = QApplication.instance() or QApplication([])
    viewer = _NavigationHarness()
    try:
        viewer.mousePressEvent(_mouse_event(QEvent.MouseButtonPress, 0, Qt.LeftButton))
        distance = viewer._view_gesture.threshold_px
        viewer.mouseMoveEvent(_mouse_event(QEvent.MouseMove, distance, Qt.NoButton, Qt.LeftButton))
        assert viewer.started == 1

        if cleanup == "cancel":
            viewer._cancel_view_navigation()
        elif cleanup == "focus":
            viewer.focusOutEvent(QFocusEvent(QEvent.FocusOut))
        else:
            viewer.leaveEvent(QEvent(QEvent.Leave))

        assert viewer.finished == 1
        assert viewer._view_gesture.button is None
        assert viewer._view_gesture.start is None
        assert viewer._view_gesture.last is None
        assert not viewer._view_gesture.dragged
    finally:
        viewer.deleteLater()
        app.processEvents()


class _NavigationHarness(BambuNavigationMixin, QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.started = 0
        self.finished = 0
        self._init_view_navigation()

    def _view_rotate(self, dx: int, dy: int) -> None:
        return

    def _view_pan(self, dx: int, dy: int) -> None:
        return

    def _view_zoom(self, factor: float, pos: QPoint) -> None:
        return

    def _view_left_click(self, pos: QPoint) -> None:
        return

    def _view_interaction_started(self) -> None:
        self.started += 1

    def _view_interaction_finished(self) -> None:
        self.finished += 1


def _mouse_event(
    event_type: QEvent.Type,
    x: int,
    button: Qt.MouseButton,
    buttons: Qt.MouseButtons | None = None,
) -> QMouseEvent:
    held = button if buttons is None else buttons
    return QMouseEvent(event_type, QPointF(x, 0), button, held, Qt.NoModifier)
