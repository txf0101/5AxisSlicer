"""Bambu Studio-style pointer navigation shared by both viewer backends."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

import numpy as np
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QApplication, QWidget

from .opengl_picking import unproject_screen_ray

PointerButton = Literal["left", "middle", "right"]
DragAction = Literal["rotate", "pan"]
ReleaseAction = Literal["click", "drag"]


class CameraNavigation(Protocol):
    def rotate(self, dx: int, dy: int) -> None: ...

    def pan(self, dx: int, dy: int) -> None: ...

    def zoom(self, factor: float, pos: QPoint) -> None: ...


class _OpenGLCameraHost(Protocol):
    _distance: float
    _pan: np.ndarray
    _pitch: float
    _view_up: np.ndarray
    _yaw: float

    def width(self) -> int: ...

    def height(self) -> int: ...

    def update(self) -> None: ...

    def _camera_vectors(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...

    def _projection_matrix(self) -> np.ndarray: ...

    def _view_matrix(self) -> np.ndarray: ...


class OpenGLCameraNavigation:
    def __init__(self, host: _OpenGLCameraHost) -> None:
        self.host = host

    def rotate(self, dx: int, dy: int) -> None:
        host = self.host
        host._view_up = np.asarray((0.0, 0.0, 1.0), dtype=np.float32)
        host._yaw += dx * 0.01
        # The legacy `_pitch` field stores zenith: 0 points along world +Z.
        host._pitch = max(
            math.radians(1.0),
            min(math.radians(179.0), host._pitch - dy * 0.01),
        )
        host.update()

    def pan(self, dx: int, dy: int) -> None:
        host = self.host
        eye, target, view_up = host._camera_vectors()
        forward = _unit(target - eye)
        right = _unit(np.cross(forward, view_up))
        screen_up = _unit(np.cross(right, forward))
        scale = 2.0 * host._distance * math.tan(math.radians(22.5)) / max(host.height(), 1)
        host._pan += (-dx * right + dy * screen_up) * scale
        host.update()

    def zoom(self, factor: float, pos: QPoint) -> None:
        before = self.target_plane_point(pos)
        self.host._distance = max(1.0, self.host._distance / factor)
        after = self.target_plane_point(pos)
        if before is not None and after is not None:
            self.host._pan += before - after
        self.host.update()

    def target_plane_point(self, pos: QPoint) -> np.ndarray | None:
        host = self.host
        ray = unproject_screen_ray(
            pos.x(),
            pos.y(),
            host.width(),
            host.height(),
            host._projection_matrix() @ host._view_matrix(),
        )
        if ray is None:
            return None
        origin, direction = ray
        eye, target, _view_up = host._camera_vectors()
        normal = _unit(target - eye)
        denominator = float(np.dot(direction, normal))
        if abs(denominator) <= 1e-9:
            return None
        distance = float(np.dot(target - origin, normal) / denominator)
        return origin + direction * distance if distance >= 0.0 else None


class VtkCameraNavigation:
    def __init__(
        self,
        renderer: Any,
        widget: QWidget,
        pixel_ratio: Callable[[], float],
        render: Callable[[], None],
    ) -> None:
        self.renderer = renderer
        self.widget = widget
        self.pixel_ratio = pixel_ratio
        self.render = render

    def rotate(self, dx: int, dy: int) -> None:
        camera = self.renderer.GetActiveCamera()
        camera.Azimuth(-400.0 * dx / max(self.widget.width(), 1))
        camera.Elevation(400.0 * dy / max(self.widget.height(), 1))
        camera.OrthogonalizeViewUp()
        self._refresh()

    def pan(self, dx: int, dy: int) -> None:
        camera = self.renderer.GetActiveCamera()
        forward = _unit(np.asarray(camera.GetDirectionOfProjection(), dtype=float))
        right = _unit(np.cross(forward, np.asarray(camera.GetViewUp(), dtype=float)))
        screen_up = _unit(np.cross(right, forward))
        height = (
            2.0 * camera.GetParallelScale()
            if camera.GetParallelProjection()
            else 2.0 * camera.GetDistance() * math.tan(math.radians(camera.GetViewAngle()) * 0.5)
        )
        self._translate((-dx * right + dy * screen_up) * height / max(self.widget.height(), 1))
        self._refresh()

    def zoom(self, factor: float, pos: QPoint) -> None:
        before = self.focal_plane_point(pos)
        self.renderer.GetActiveCamera().Zoom(factor)
        after = self.focal_plane_point(pos)
        if before is not None and after is not None:
            self._translate(before - after)
        self._refresh()

    def display_point(self, pos: QPoint) -> tuple[int, int]:
        # Qt and VTK use opposite display-Y origins.
        scale = self.pixel_ratio()
        return round(pos.x() * scale), round((self.widget.height() - pos.y() - 1) * scale)

    def focal_plane_point(self, pos: QPoint) -> np.ndarray | None:
        focal = self.renderer.GetActiveCamera().GetFocalPoint()
        self.renderer.SetWorldPoint(*focal, 1.0)
        self.renderer.WorldToDisplay()
        depth = self.renderer.GetDisplayPoint()[2]
        x, y = self.display_point(pos)
        self.renderer.SetDisplayPoint(x, y, depth)
        self.renderer.DisplayToWorld()
        world = np.asarray(self.renderer.GetWorldPoint(), dtype=float)
        if world.shape != (4,) or not np.isfinite(world).all() or abs(world[3]) <= 1e-12:
            return None
        return world[:3] / world[3]

    def _translate(self, offset: np.ndarray) -> None:
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(*(np.asarray(camera.GetFocalPoint()) + offset))
        camera.SetPosition(*(np.asarray(camera.GetPosition()) + offset))

    def _refresh(self) -> None:
        self.renderer.ResetCameraClippingRange()
        self.render()


@dataclass(frozen=True, slots=True)
class DragUpdate:
    action: DragAction
    dx: int
    dy: int
    started: bool


@dataclass(slots=True)
class PointerGesture:
    """Separate a click from a drag using displacement from the press point."""

    threshold_px: int
    button: PointerButton | None = None
    start: tuple[int, int] | None = None
    last: tuple[int, int] | None = None
    dragged: bool = False

    def press(self, button: PointerButton, point: tuple[int, int]) -> None:
        if self.button is not None:
            return
        self.button = button
        self.start = point
        self.last = point
        self.dragged = False

    def move(self, point: tuple[int, int]) -> DragUpdate | None:
        if self.button is None or self.start is None or self.last is None:
            return None
        started = not self.dragged and _distance(self.start, point) >= self.threshold_px
        if not self.dragged and not started:
            self.last = point
            return None
        previous = self.start if started else self.last
        self.dragged = True
        self.last = point
        action: DragAction = "rotate" if self.button == "left" else "pan"
        return DragUpdate(action, point[0] - previous[0], point[1] - previous[1], started)

    def release(self, button: PointerButton) -> ReleaseAction | None:
        if button != self.button:
            return None
        action: ReleaseAction = "drag" if self.dragged else "click"
        self.cancel()
        return action

    def cancel(self) -> bool:
        dragged = self.dragged
        self.button = None
        self.start = None
        self.last = None
        self.dragged = False
        return dragged


def wheel_zoom_factor(delta: int) -> float | None:
    """Return a bounded factor while preserving high-resolution wheel deltas."""

    if delta == 0:
        return None
    return min(10.0, max(0.1, 1.12 ** (float(delta) / 120.0)))


def z_up_orbit_direction(azimuth_rad: float, zenith_rad: float) -> np.ndarray:
    """Return a unit orbit direction with azimuth around world +Z."""

    radial = math.sin(zenith_rad)
    return np.asarray(
        (
            radial * math.sin(azimuth_rad),
            radial * math.cos(azimuth_rad),
            math.cos(zenith_rad),
        ),
        dtype=np.float32,
    )


class BambuNavigationMixin:
    """Map Qt pointer events while each backend owns its camera mathematics."""

    def _init_view_navigation(self, camera: CameraNavigation | None = None) -> None:
        self._view_gesture = PointerGesture(max(3, QApplication.startDragDistance()))
        self._view_camera = camera

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        button = _button_name(event.button())
        if button is None:
            self._forward_view_event("mousePressEvent", event)
            return
        cast(QWidget, self).setFocus(Qt.MouseFocusReason)
        self._view_gesture.press(button, _point(event.pos()))
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        button = self._view_gesture.button
        if button is None:
            self._forward_view_event("mouseMoveEvent", event)
            return
        if not event.buttons() & _qt_button(button):
            self._cancel_view_navigation()
            event.accept()
            return
        update = self._view_gesture.move(_point(event.pos()))
        if update is not None:
            if update.started:
                cast(QWidget, self).setCursor(Qt.ClosedHandCursor)
                self._view_interaction_started()
            if update.action == "rotate":
                self._view_rotate(update.dx, update.dy)
            else:
                self._view_pan(update.dx, update.dy)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        button = _button_name(event.button())
        if button is None:
            self._forward_view_event("mouseReleaseEvent", event)
            return
        action = self._view_gesture.release(button)
        if action is None:
            event.accept()
            return
        if action == "click" and button == "left":
            # Picking commits on release so a camera drag cannot change geometry selection.
            self._view_left_click(event.pos())
        elif action == "drag":
            self._view_interaction_finished()
        cast(QWidget, self).unsetCursor()
        event.accept()

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        factor = wheel_zoom_factor(event.angleDelta().y())
        if factor is None:
            event.ignore()
            return
        self._view_zoom(factor, event.pos())
        event.accept()

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._cancel_view_navigation()
        self._forward_view_event("focusOutEvent", event)

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._cancel_view_navigation()
        self._forward_view_event("hideEvent", event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if QApplication.mouseButtons() == Qt.NoButton:
            self._cancel_view_navigation()
        self._forward_view_event("leaveEvent", event)

    def _cancel_view_navigation(self) -> None:
        if self._view_gesture.cancel():
            self._view_interaction_finished()
        cast(QWidget, self).unsetCursor()

    def _forward_view_event(self, name: str, event) -> None:
        handler = getattr(super(), name, None)
        if handler is not None:
            handler(event)

    def _view_rotate(self, dx: int, dy: int) -> None:
        if self._view_camera is None:
            raise RuntimeError("Camera navigation is not configured")
        self._view_camera.rotate(dx, dy)

    def _view_pan(self, dx: int, dy: int) -> None:
        if self._view_camera is None:
            raise RuntimeError("Camera navigation is not configured")
        self._view_camera.pan(dx, dy)

    def _view_zoom(self, factor: float, pos: QPoint) -> None:
        if self._view_camera is None:
            raise RuntimeError("Camera navigation is not configured")
        self._view_camera.zoom(factor, pos)

    def _view_left_click(self, pos: QPoint) -> None:
        raise NotImplementedError

    def _view_interaction_started(self) -> None:
        return

    def _view_interaction_finished(self) -> None:
        return


def _distance(first: tuple[int, int], second: tuple[int, int]) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def _point(point: QPoint) -> tuple[int, int]:
    return int(point.x()), int(point.y())


def _button_name(button) -> PointerButton | None:
    if button == Qt.LeftButton:
        return "left"
    if button == Qt.MiddleButton:
        return "middle"
    if button == Qt.RightButton:
        return "right"
    return None


def _qt_button(button: PointerButton):
    return {
        "left": Qt.LeftButton,
        "middle": Qt.MiddleButton,
        "right": Qt.RightButton,
    }[button]


def _unit(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    return vector if length <= 1e-12 else vector / length
