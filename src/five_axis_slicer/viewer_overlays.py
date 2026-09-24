from __future__ import annotations

import math

from PyQt5.QtCore import QEvent, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PyQt5.QtWidgets import QWidget


_FACE_TEXT_RECT = QRectF(0.0, 0.0, 100.0, 100.0)


def _unit3(values) -> tuple[float, float, float]:
    vector = tuple(float(value) for value in values)
    if len(vector) != 3 or not all(math.isfinite(value) for value in vector):
        raise ValueError("Expected a finite 3D camera vector")
    length = math.sqrt(sum(value * value for value in vector))
    if length < 1e-9:
        raise ValueError("Camera direction must have nonzero length")
    return tuple(value / length for value in vector)


def _cross3(left, right) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _triad_directions(camera: dict) -> dict[str, tuple[float, float]]:
    eye = tuple(float(value) for value in camera["position"])
    focal = tuple(float(value) for value in camera["focal_point"])
    forward = _unit3(tuple(focal[index] - eye[index] for index in range(3)))
    right = _unit3(_cross3(forward, _unit3(camera["view_up"])))
    up = _cross3(right, forward)
    return {
        label: (right[index], -up[index])
        for index, label in enumerate("XYZ")
    }


def _orientation_faces() -> list[tuple[QPolygonF, str]]:
    return [
        (
            QPolygonF([QPointF(56, 15), QPointF(91, 32), QPointF(56, 50), QPointF(21, 32)]),
            "top",
        ),
        (
            QPolygonF([QPointF(21, 32), QPointF(56, 50), QPointF(56, 88), QPointF(21, 69)]),
            "front",
        ),
        (
            QPolygonF([QPointF(56, 50), QPointF(91, 32), QPointF(91, 69), QPointF(56, 88)]),
            "right",
        ),
    ]


def _inset_quad(polygon: QPolygonF, factor: float = 0.70) -> QPolygonF:
    center = QPointF(
        sum(point.x() for point in polygon) / len(polygon),
        sum(point.y() for point in polygon) / len(polygon),
    )
    return QPolygonF(
        [
            QPointF(
                center.x() + (point.x() - center.x()) * factor,
                center.y() + (point.y() - center.y()) * factor,
            )
            for point in polygon
        ]
    )


def _face_text_transform(polygon: QPolygonF) -> tuple[QTransform, QPolygonF]:
    source = QPolygonF(
        [
            _FACE_TEXT_RECT.topLeft(),
            _FACE_TEXT_RECT.topRight(),
            _FACE_TEXT_RECT.bottomRight(),
            _FACE_TEXT_RECT.bottomLeft(),
        ]
    )
    target = _inset_quad(polygon)
    transform = QTransform()
    if not QTransform.quadToQuad(source, target, transform):
        raise ValueError("Orientation-cube face cannot be projected")
    return transform, target


class OrientationCubeOverlay(QWidget):
    """Compact vector orientation cube with standard-view hit targets."""

    view_requested = pyqtSignal(str)

    def __init__(self, viewer=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.viewer = viewer
        self.setFixedSize(112, 112)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Orientation cube")
        self._faces = _orientation_faces()
        self._face_label_transforms: dict[str, QTransform] = {}

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        top, front, right = (polygon for polygon, _view in self._faces)
        for polygon, color in (
            (top, QColor("#EEF4FF")),
            (front, QColor("#DCE8FA")),
            (right, QColor("#C8DAF5")),
        ):
            painter.setBrush(color)
            painter.setPen(QPen(QColor("#6B7A90"), 1.1))
            painter.drawPolygon(polygon)
        self._face_label_transforms.clear()
        for text, polygon, view in (
            ("TOP", top, "top"),
            ("FRONT", front, "front"),
            ("RIGHT", right, "right"),
        ):
            transform, _target = _face_text_transform(polygon)
            self._face_label_transforms[view] = transform
            font = QFont("Segoe UI")
            font.setPixelSize(24)
            font.setWeight(QFont.DemiBold)
            label_path = QPainterPath()
            label_path.addText(QPointF(0.0, 0.0), font, text)
            bounds = label_path.boundingRect()
            label_path.translate(
                _FACE_TEXT_RECT.center().x() - bounds.center().x(),
                _FACE_TEXT_RECT.center().y() - bounds.center().y(),
            )
            painter.fillPath(transform.map(label_path), QColor("#334155"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#64748B"))
        painter.drawText(5, 105, "L")
        painter.drawText(52, 105, "B")
        painter.drawText(101, 105, "D")
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        point = QPointF(event.pos())
        requested = None
        for polygon, view in self._faces:
            if polygon.containsPoint(point, Qt.OddEvenFill):
                requested = view
                break
        if requested is None and event.pos().y() >= 90:
            if event.pos().x() < 35:
                requested = "left"
            elif event.pos().x() < 78:
                requested = "back"
            else:
                requested = "bottom"
        if requested:
            if self.viewer is not None and hasattr(self.viewer, "set_standard_view"):
                self.viewer.set_standard_view(requested)
            self.view_requested.emit(requested)
        super().mousePressEvent(event)


class AxisTriadOverlay(QWidget):
    """Project Part XYZ with the same camera as the 3D viewer."""

    def __init__(self, viewer=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.viewer = viewer
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(116, 104)
        self.setToolTip("Part XYZ")
        self._camera_signature: tuple[float, ...] | None = None
        if viewer is not None:
            viewer.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is self.viewer and event.type() in {
            QEvent.Paint,
            QEvent.MouseMove,
            QEvent.MouseButtonRelease,
            QEvent.Wheel,
            QEvent.KeyPress,
        }:
            camera = self._camera_state()
            if camera is not None:
                try:
                    signature = tuple(
                        float(value)
                        for key in ("position", "focal_point", "view_up")
                        for value in camera[key]
                    )
                except (KeyError, TypeError, ValueError):
                    signature = None
                if signature != self._camera_signature:
                    self._camera_signature = signature
                    self.update()
        return super().eventFilter(watched, event)

    def _camera_state(self) -> dict | None:
        if self.viewer is None or not hasattr(self.viewer, "camera_state"):
            return None
        try:
            return self.viewer.camera_state()
        except (AttributeError, RuntimeError, ValueError):
            return None

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        origin = QPointF(58, 59)
        try:
            directions = _triad_directions(self._camera_state() or {})
        except (KeyError, TypeError, ValueError):
            directions = {"X": (1.0, 0.25), "Y": (-0.65, 0.5), "Z": (0.0, -1.0)}
        axes = tuple(
            (
                QPointF(origin.x() + 31 * directions[label][0], origin.y() + 31 * directions[label][1]),
                QColor(color),
                label,
            )
            for label, color in (("X", "#E5484D"), ("Y", "#2E9B61"), ("Z", "#2563EB"))
        )
        painter.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
        for end, color, label in axes:
            painter.setPen(QPen(color, 2.4, Qt.SolidLine, Qt.RoundCap))
            direction = end - origin
            length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
            if length < 4.0:
                painter.setBrush(color)
                painter.drawEllipse(origin, 3.5, 3.5)
                painter.drawText(int(origin.x() + 6), int(origin.y() - 4), label)
                continue
            painter.drawLine(origin, end)
            ux, uy = direction.x() / length, direction.y() / length
            left = QPointF(end.x() - ux * 8 - uy * 4, end.y() - uy * 8 + ux * 4)
            right = QPointF(end.x() - ux * 8 + uy * 4, end.y() - uy * 8 - ux * 4)
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([end, left, right]))
            painter.setPen(color)
            painter.drawText(int(end.x() + 3), int(end.y() + 3), label)
        painter.setPen(QColor("#475569"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(5, 12, "Part XYZ")
        painter.end()


__all__ = ["AxisTriadOverlay", "OrientationCubeOverlay"]
