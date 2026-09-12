from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PyQt5.QtWidgets import QWidget


_FACE_TEXT_RECT = QRectF(0.0, 0.0, 100.0, 100.0)


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
    """Vector Part XYZ triad that stays crisp in high-DPI exports."""

    def __init__(self, viewer=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.viewer = viewer
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(116, 104)
        self.setToolTip("Part XYZ")

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        origin = QPointF(37, 73)
        axes = (
            (QPointF(91, 88), QColor("#E5484D"), "X"),
            (QPointF(12, 92), QColor("#2E9B61"), "Y"),
            (QPointF(37, 17), QColor("#2563EB"), "Z"),
        )
        painter.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
        for end, color, label in axes:
            painter.setPen(QPen(color, 2.4, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(origin, end)
            direction = end - origin
            length = max(1.0, (direction.x() ** 2 + direction.y() ** 2) ** 0.5)
            ux, uy = direction.x() / length, direction.y() / length
            left = QPointF(end.x() - ux * 8 - uy * 4, end.y() - uy * 8 + ux * 4)
            right = QPointF(end.x() - ux * 8 + uy * 4, end.y() - uy * 8 - ux * 4)
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([end, left, right]))
            painter.setPen(color)
            if label == "Z":
                painter.drawText(int(end.x() + 5), int(end.y() + 14), label)
            else:
                painter.drawText(int(end.x() + 3), int(end.y() + 3), label)
        painter.setPen(QColor("#475569"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(5, 12, "Part XYZ")
        painter.end()


__all__ = ["AxisTriadOverlay", "OrientationCubeOverlay"]
