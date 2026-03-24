from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

try:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtGui import QColor, QMatrix4x4, QPainter, QPen, QVector4D, QSurfaceFormat
    from PyQt6.QtOpenGL import (
        QOpenGLBuffer,
        QOpenGLShader,
        QOpenGLShaderProgram,
        QOpenGLVersionFunctionsFactory,
        QOpenGLVersionProfile,
    )
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget

    _LEFT_BUTTON = Qt.MouseButton.LeftButton
    _RIGHT_BUTTON = Qt.MouseButton.RightButton
    _MIDDLE_BUTTON = Qt.MouseButton.MiddleButton
    _FOCUS_POLICY = Qt.FocusPolicy.StrongFocus
    _NO_BRUSH = Qt.BrushStyle.NoBrush
    _DASH_LINE = Qt.PenStyle.DashLine
    _PAINTER_ANTIALIASING = QPainter.RenderHint.Antialiasing

except ImportError:
    from PyQt5.QtCore import QPoint, Qt
    from PyQt5.QtGui import QColor, QMatrix4x4, QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram, QPainter, QPen, QSurfaceFormat, QVector4D
    from PyQt5.QtOpenGL import QOpenGLVersionFunctionsFactory, QOpenGLVersionProfile
    from PyQt5.QtWidgets import QOpenGLWidget

    _LEFT_BUTTON = Qt.LeftButton
    _RIGHT_BUTTON = Qt.RightButton
    _MIDDLE_BUTTON = Qt.MiddleButton
    _FOCUS_POLICY = Qt.StrongFocus
    _NO_BRUSH = Qt.NoBrush
    _DASH_LINE = Qt.DashLine
    _PAINTER_ANTIALIASING = QPainter.Antialiasing

# Preview widget for inspecting mesh placement, selected faces, and generated
# toolpaths inside the application.
# 这里放的是轻量级 OpenGL 预览，用户不用离开应用就能看模型摆放、面片
# 选择和生成出来的路径。


PATH_STYLE_MAP = {
    "adhesion-skirt": {"color": "#f97316", "width": 1.55, "alpha": 0.92},
    "planar-perimeter": {"color": "#ff8f3f", "width": 1.8, "alpha": 0.98},
    "planar-infill": {"color": "#ffc857", "width": 1.25, "alpha": 0.86},
    "conformal-perimeter": {"color": "#54d2a0", "width": 1.9, "alpha": 0.98},
    "conformal-infill": {"color": "#79c7ff", "width": 1.2, "alpha": 0.88},
    "conformal-surface-finish": {"color": "#2dd4bf", "width": 2.05, "alpha": 0.99},
}
SELECTION_STYLE_MAP = {
    "substrate": {"fill": "#ffb56b", "wire": "#ff9a44", "alpha": 0.18, "wire_alpha": 0.84},
    "conformal": {"fill": "#72ddb9", "wire": "#31bea0", "alpha": 0.16, "wire_alpha": 0.82},
}

_MAX_MESH_FACES_FULL = 28000
_MAX_MESH_FACES_INTERACTIVE = 6500
_MAX_LINE_POINTS_FULL = 450000
_MAX_LINE_POINTS_INTERACTIVE = 150000

_GL_BACK = 0x0405
_GL_BLEND = 0x0BE2
_GL_CULL_FACE = 0x0B44
_GL_COLOR_BUFFER_BIT = 0x00004000
_GL_DEPTH_BUFFER_BIT = 0x00000100
_GL_DEPTH_TEST = 0x0B71
_GL_FLOAT = 0x1406
_GL_LEQUAL = 0x0203
_GL_LINES = 0x0001
_GL_LINE_SMOOTH = 0x0B20
_GL_MULTISAMPLE = 0x809D
_GL_ONE_MINUS_SRC_ALPHA = 0x0303
_GL_SRC_ALPHA = 0x0302
_GL_TRIANGLES = 0x0004

_MESH_VERTEX_SHADER = """
attribute vec3 a_position;
attribute vec3 a_normal;
uniform mat4 u_mvp;
uniform mat4 u_model_view;
varying float v_light;
void main() {
    vec3 normal = normalize((u_model_view * vec4(a_normal, 0.0)).xyz);
    vec3 light_dir = normalize(vec3(0.30, 0.45, 1.00));
    v_light = 0.24 + 0.76 * abs(dot(normal, light_dir));
    gl_Position = u_mvp * vec4(a_position, 1.0);
}
"""

_MESH_FRAGMENT_SHADER = """
uniform vec4 u_color;
varying float v_light;
void main() {
    gl_FragColor = vec4(u_color.rgb * v_light, u_color.a);
}
"""

_LINE_VERTEX_SHADER = """
attribute vec3 a_position;
uniform mat4 u_mvp;
void main() {
    gl_Position = u_mvp * vec4(a_position, 1.0);
}
"""

_LINE_FRAGMENT_SHADER = """
uniform vec4 u_color;
void main() {
    gl_FragColor = u_color;
}
"""


@dataclass(slots=True)
class _GpuBuffer:
    """Small wrapper that keeps GPU buffer metadata together.

    用来把 GPU 缓冲区对象和相关元数据放在一起的小包装。
    """

    buffer: QOpenGLBuffer | None = None
    count: int = 0
    stride_bytes: int = 0


class PreviewCanvas(QOpenGLWidget):
    """Interactive GPU preview for mesh and toolpath inspection.

    用于查看模型和路径的交互式 GPU 预览控件。

    用于查看模型和路径的交互式 GPU 预览控件。
    这个控件更看重交互流畅和路径清楚，不追求照片级渲染，所以很适合反复
    调参和检查切片结果。
    """

    def __init__(self) -> None:
        super().__init__()
        self.setFocusPolicy(_FOCUS_POLICY)
        self.setMouseTracking(True)
        self._configure_surface_format()

        self._vertices = np.empty((0, 3), dtype=np.float32)
        self._faces = np.empty((0, 3), dtype=np.int32)
        self._toolpaths: list[tuple[np.ndarray, str]] = []
        self._selection_faces: dict[str, np.ndarray] = {kind: np.empty(0, dtype=np.int32) for kind in SELECTION_STYLE_MAP}
        self._selection_triangles: dict[str, np.ndarray] = {kind: np.empty((0, 3, 3), dtype=np.float32) for kind in SELECTION_STYLE_MAP}
        self._segments_by_kind_full: dict[str, np.ndarray] = {}
        self._segments_by_kind_interactive: dict[str, np.ndarray] = {}
        self._mesh_triangles_full = np.empty((0, 3, 3), dtype=np.float32)
        self._mesh_triangles_interactive = np.empty((0, 3, 3), dtype=np.float32)
        self._mesh_triangles_occlusion = np.empty((0, 3, 3), dtype=np.float32)
        self._mesh_edges_full = np.empty((0, 3), dtype=np.float32)
        self._mesh_edges_interactive = np.empty((0, 3), dtype=np.float32)
        self._grid_lines = np.empty((0, 3), dtype=np.float32)

        self._show_mesh = True
        self._visible_kinds: set[str] = set(PATH_STYLE_MAP)
        self._interaction_active = False
        self._scene_dirty = True
        self._gl = None
        self._mesh_program: QOpenGLShaderProgram | None = None
        self._line_program: QOpenGLShaderProgram | None = None

        self._mesh_fill_full = _GpuBuffer()
        self._mesh_fill_interactive = _GpuBuffer()
        self._mesh_depth_buffer = _GpuBuffer()
        self._mesh_wire_full = _GpuBuffer()
        self._mesh_wire_interactive = _GpuBuffer()
        self._grid_buffer = _GpuBuffer()
        self._line_buffers_full: dict[str, _GpuBuffer] = {kind: _GpuBuffer() for kind in PATH_STYLE_MAP}
        self._line_buffers_interactive: dict[str, _GpuBuffer] = {kind: _GpuBuffer() for kind in PATH_STYLE_MAP}
        self._selection_fill_buffers: dict[str, _GpuBuffer] = {kind: _GpuBuffer() for kind in SELECTION_STYLE_MAP}
        self._selection_wire_buffers: dict[str, _GpuBuffer] = {kind: _GpuBuffer() for kind in SELECTION_STYLE_MAP}

        self._bounds_min: np.ndarray | None = None
        self._bounds_max: np.ndarray | None = None
        self._scene_center = np.zeros(3, dtype=np.float32)
        self._scene_radius = 1.0
        self._floor_z = 0.0

        self._yaw_deg = -46.0
        self._pitch_deg = 28.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._zoom_factor = 1.0
        self._last_mouse_pos = QPoint()
        self._press_mouse_pos = QPoint()
        self._active_button = None
        self._drag_distance_px = 0.0
        self._face_pick_enabled = False
        self._face_pick_callback: Callable[[list[int]], None] | None = None
        self._face_brush_enabled = False
        self._face_brush_radius_px = 18
        self._brush_drag_active = False
        self._brush_seen_faces: set[int] = set()
        self._hover_pos = QPoint()
        self._hover_visible = False

    def clear(self) -> None:
        """Reset the preview state back to an empty scene.

        把预览状态重置回空场景。
        """

        self._vertices = np.empty((0, 3), dtype=np.float32)
        self._faces = np.empty((0, 3), dtype=np.int32)
        self._toolpaths = []
        self._selection_faces = {kind: np.empty(0, dtype=np.int32) for kind in SELECTION_STYLE_MAP}
        self._selection_triangles = {kind: np.empty((0, 3, 3), dtype=np.float32) for kind in SELECTION_STYLE_MAP}
        self._segments_by_kind_full = {}
        self._segments_by_kind_interactive = {}
        self._mesh_triangles_full = np.empty((0, 3, 3), dtype=np.float32)
        self._mesh_triangles_interactive = np.empty((0, 3, 3), dtype=np.float32)
        self._mesh_triangles_occlusion = np.empty((0, 3, 3), dtype=np.float32)
        self._mesh_edges_full = np.empty((0, 3), dtype=np.float32)
        self._mesh_edges_interactive = np.empty((0, 3), dtype=np.float32)
        self._grid_lines = np.empty((0, 3), dtype=np.float32)
        self._bounds_min = None
        self._bounds_max = None
        self._scene_center = np.zeros(3, dtype=np.float32)
        self._scene_radius = 1.0
        self._floor_z = 0.0
        self._interaction_active = False
        self._brush_drag_active = False
        self._brush_seen_faces.clear()
        self._hover_visible = False
        self._scene_dirty = True
        self.update()

    def plot_mesh(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        selection_faces: dict[str, np.ndarray] | None = None,
        preserve_camera: bool = False,
    ) -> None:
        """Display a mesh and optional face selections in the preview.

        在预览里显示网格，以及可选的面片选择结果。
        """

        self._set_scene(vertices, faces, [], selection_faces=selection_faces, preserve_camera=preserve_camera)

    def plot_toolpaths(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        toolpaths: list[tuple[np.ndarray, str]],
        selection_faces: dict[str, np.ndarray] | None = None,
        preserve_camera: bool = False,
    ) -> None:
        """Display toolpaths on top of the current mesh scene.

        在当前网格场景上叠加显示工具路径。
        """

        self._set_scene(vertices, faces, toolpaths, selection_faces=selection_faces, preserve_camera=preserve_camera)

    def set_visibility(self, show_mesh: bool | None = None, visible_kinds: set[str] | None = None) -> None:
        if show_mesh is not None:
            self._show_mesh = bool(show_mesh)
        if visible_kinds is not None:
            self._visible_kinds = set(visible_kinds)
        self.update()

    def set_face_picking(self, enabled: bool, callback: Callable[[list[int]], None] | None = None) -> None:
        self._face_pick_enabled = bool(enabled)
        self._face_pick_callback = callback if enabled else None
        if not enabled:
            self._brush_drag_active = False
            self._brush_seen_faces.clear()
        self.update()

    def set_face_brush(self, enabled: bool, radius_px: int) -> None:
        self._face_brush_enabled = bool(enabled)
        self._face_brush_radius_px = max(int(radius_px), 8)
        if not self._face_brush_enabled:
            self._brush_drag_active = False
            self._brush_seen_faces.clear()
        self.update()

    def initializeGL(self) -> None:  # type: ignore[override]
        self._gl = self._create_gl_functions()
        if self._gl is None:
            raise RuntimeError("Failed to initialize OpenGL functions for the preview widget.")
        self._gl.initializeOpenGLFunctions()
        self._gl.glEnable(_GL_DEPTH_TEST)
        self._gl.glDepthFunc(_GL_LEQUAL)
        self._gl.glEnable(_GL_BLEND)
        self._gl.glBlendFunc(_GL_SRC_ALPHA, _GL_ONE_MINUS_SRC_ALPHA)
        self._gl.glEnable(_GL_MULTISAMPLE)
        self._gl.glEnable(_GL_LINE_SMOOTH)

        self._mesh_program = self._build_program(_MESH_VERTEX_SHADER, _MESH_FRAGMENT_SHADER)
        self._line_program = self._build_program(_LINE_VERTEX_SHADER, _LINE_FRAGMENT_SHADER)
        self._upload_scene_to_gpu()

    def resizeGL(self, width: int, height: int) -> None:  # type: ignore[override]
        if self._gl is not None:
            self._gl.glViewport(0, 0, max(width, 1), max(height, 1))

    def paintGL(self) -> None:  # type: ignore[override]
        if self._gl is None or self._mesh_program is None or self._line_program is None:
            return
        if self._scene_dirty:
            self._upload_scene_to_gpu()

        self._gl.glClearColor(0.071, 0.082, 0.102, 1.0)
        self._gl.glClear(_GL_COLOR_BUFFER_BIT | _GL_DEPTH_BUFFER_BIT)

        if self._bounds_min is None or self._bounds_max is None:
            return

        projection, model_view, mvp = self._camera_matrices()
        del projection

        self._draw_depth_prepass(self._mesh_depth_buffer, model_view, mvp)
        self._draw_lines(self._grid_buffer, QColor("#314156"), 1.0, 0.95, mvp)

        if self._show_mesh:
            mesh_fill = self._mesh_fill_interactive if self._interaction_active else self._mesh_fill_full
            mesh_wire = self._mesh_wire_interactive if self._interaction_active else self._mesh_wire_full
            self._draw_mesh(mesh_fill, model_view, mvp)
            self._draw_lines(mesh_wire, QColor("#5d7089"), 1.0, 0.26 if self._interaction_active else 0.36, mvp)

        for kind, style in SELECTION_STYLE_MAP.items():
            fill_buffer = self._selection_fill_buffers[kind]
            wire_buffer = self._selection_wire_buffers[kind]
            if fill_buffer.count > 0:
                fill_color = QColor(style["fill"])
                self._gl.glEnable(_GL_CULL_FACE)
                self._gl.glCullFace(_GL_BACK)
                self._gl.glDepthMask(False)
                self._draw_mesh(
                    fill_buffer,
                    model_view,
                    mvp,
                    color_rgba=(fill_color.redF(), fill_color.greenF(), fill_color.blueF(), style["alpha"]),
                )
                self._gl.glDepthMask(True)
                self._gl.glDisable(_GL_CULL_FACE)
            if wire_buffer.count > 0:
                self._draw_lines(wire_buffer, QColor(style["wire"]), 1.45, style["wire_alpha"], mvp)

        line_buffers = self._line_buffers_interactive if self._interaction_active else self._line_buffers_full
        for kind, style in PATH_STYLE_MAP.items():
            if kind not in self._visible_kinds:
                continue
            buffer = line_buffers.get(kind)
            if buffer is None or buffer.count <= 0:
                continue
            self._draw_lines(buffer, QColor(style["color"]), style["width"], style["alpha"], mvp)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().paintEvent(event)
        if not (self._face_pick_enabled and self._face_brush_enabled and self._hover_visible):
            return

        # Draw the brush cursor after the OpenGL frame has been composited so
        # the overlay cannot wash out the 3D preview colors.
        painter = QPainter(self)
        painter.setRenderHint(_PAINTER_ANTIALIASING, True)
        pen = QPen(QColor(228, 232, 238, 110), 1.0)
        pen.setStyle(_DASH_LINE)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(_NO_BRUSH)
        radius = self._face_brush_radius_px
        painter.drawEllipse(self._hover_pos, radius, radius)
        painter.end()

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._last_mouse_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        self._press_mouse_pos = self._last_mouse_pos
        self._hover_pos = self._last_mouse_pos
        self._hover_visible = True
        self._active_button = event.button()
        self._drag_distance_px = 0.0
        if self._active_button == _LEFT_BUTTON and self._face_pick_enabled and self._face_brush_enabled:
            self._active_button = None
            self._interaction_active = False
            self._brush_drag_active = True
            self._brush_seen_faces.clear()
            self._apply_face_brush(self._last_mouse_pos.x(), self._last_mouse_pos.y())
            self.update()
            event.accept()
            return
        self._interaction_active = True
        self.update()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        current_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        delta = current_pos - self._last_mouse_pos
        self._last_mouse_pos = current_pos
        self._hover_pos = current_pos
        self._hover_visible = True
        self._drag_distance_px = max(self._drag_distance_px, float((current_pos - self._press_mouse_pos).manhattanLength()))

        if self._brush_drag_active:
            self._apply_face_brush(current_pos.x(), current_pos.y())
            self.update()
            event.accept()
            return

        if self._active_button is None:
            if self._face_pick_enabled and self._face_brush_enabled:
                self.update()
                event.accept()
            else:
                event.ignore()
            return

        if self._active_button == _LEFT_BUTTON:
            self._yaw_deg += float(delta.x()) * 0.55
            self._pitch_deg = _wrap_angle_deg(self._pitch_deg + float(delta.y()) * 0.45)
        elif self._active_button in {_RIGHT_BUTTON, _MIDDLE_BUTTON}:
            pan_scale = self._scene_radius / max(min(self.width(), self.height()) * self._zoom_factor, 1.0)
            self._pan_x += float(delta.x()) * pan_scale * 1.6
            self._pan_y -= float(delta.y()) * pan_scale * 1.6

        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        release_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        released_button = event.button()
        self._hover_pos = release_pos
        if self._brush_drag_active and released_button == _LEFT_BUTTON:
            self._brush_drag_active = False
            self._brush_seen_faces.clear()
            self.update()
            event.accept()
            return
        self._active_button = None
        self._interaction_active = False
        if (
            released_button == _LEFT_BUTTON
            and self._face_pick_enabled
            and self._drag_distance_px <= 4.0
            and self._face_pick_callback is not None
        ):
            picked_face = self._pick_face(release_pos.x(), release_pos.y())
            if picked_face is not None:
                self._face_pick_callback([picked_face])
        self.update()
        event.accept()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hover_visible = False
        if not self._brush_drag_active:
            self.update()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._reset_camera()
        self.update()
        event.accept()

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        angle_delta = event.angleDelta().y() if hasattr(event, "angleDelta") else 0
        if angle_delta == 0:
            event.ignore()
            return
        zoom_step = 1.0 + abs(angle_delta) / 960.0
        if angle_delta > 0:
            self._zoom_factor *= zoom_step
        else:
            self._zoom_factor /= zoom_step
        self._zoom_factor = float(np.clip(self._zoom_factor, 0.35, 6.5))
        self.update()
        event.accept()

    def _configure_surface_format(self) -> None:
        surface_format = QSurfaceFormat()
        surface_format.setDepthBufferSize(24)
        surface_format.setSamples(4)
        surface_format.setVersion(2, 0)
        self.setFormat(surface_format)

    def _reset_camera(self) -> None:
        self._yaw_deg = -46.0
        self._pitch_deg = 28.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._zoom_factor = 1.0

    def _set_scene(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        toolpaths: list[tuple[np.ndarray, str]],
        selection_faces: dict[str, np.ndarray] | None = None,
        preserve_camera: bool = False,
    ) -> None:
        self._vertices = np.asarray(vertices, dtype=np.float32)
        self._faces = np.asarray(faces, dtype=np.int32)
        self._toolpaths = [(np.asarray(points, dtype=np.float32), kind) for points, kind in toolpaths]
        selection_faces = selection_faces or {}
        self._selection_faces = {
            kind: np.asarray(selection_faces.get(kind, np.empty(0, dtype=np.int32)), dtype=np.int32)
            for kind in SELECTION_STYLE_MAP
        }
        self._interaction_active = False

        if len(self._vertices) > 0:
            self._bounds_min = self._vertices.min(axis=0)
            self._bounds_max = self._vertices.max(axis=0)
            self._scene_center = (self._bounds_min + self._bounds_max) * 0.5
            scene_span = np.maximum(self._bounds_max - self._bounds_min, 1.0)
            self._scene_radius = float(np.linalg.norm(scene_span) * 0.55)
            self._floor_z = float(self._bounds_min[2])
        else:
            self._bounds_min = None
            self._bounds_max = None
            self._scene_center = np.zeros(3, dtype=np.float32)
            self._scene_radius = 1.0
            self._floor_z = 0.0

        self._mesh_triangles_full = self._sample_mesh_triangles(_MAX_MESH_FACES_FULL)
        self._mesh_triangles_interactive = self._sample_mesh_triangles(_MAX_MESH_FACES_INTERACTIVE)
        self._mesh_triangles_occlusion = np.asarray(self._vertices[self._faces], dtype=np.float32) if len(self._faces) > 0 else np.empty((0, 3, 3), dtype=np.float32)
        self._mesh_edges_full = self._triangle_edges(self._mesh_triangles_full)
        self._mesh_edges_interactive = self._triangle_edges(self._mesh_triangles_interactive)
        self._selection_triangles = {
            kind: self._selected_triangles(face_indices)
            for kind, face_indices in self._selection_faces.items()
        }
        self._segments_by_kind_full = self._build_line_cache(_MAX_LINE_POINTS_FULL)
        self._segments_by_kind_interactive = self._build_line_cache(_MAX_LINE_POINTS_INTERACTIVE)
        self._grid_lines = self._build_build_plate_grid()
        self._scene_dirty = True
        if not preserve_camera:
            self._reset_camera()
        self.update()

    def _sample_mesh_triangles(self, max_faces: int) -> np.ndarray:
        if len(self._faces) == 0 or len(self._vertices) == 0:
            return np.empty((0, 3, 3), dtype=np.float32)
        stride = max(1, int(math.ceil(len(self._faces) / max(max_faces, 1))))
        sampled_faces = self._faces[::stride]
        return np.asarray(self._vertices[sampled_faces], dtype=np.float32)

    def _selected_triangles(self, face_indices: np.ndarray) -> np.ndarray:
        if len(face_indices) == 0 or len(self._faces) == 0 or len(self._vertices) == 0:
            return np.empty((0, 3, 3), dtype=np.float32)
        valid_indices = face_indices[(face_indices >= 0) & (face_indices < len(self._faces))]
        if len(valid_indices) == 0:
            return np.empty((0, 3, 3), dtype=np.float32)
        return np.asarray(self._vertices[self._faces[valid_indices]], dtype=np.float32)

    def _triangle_edges(self, triangles: np.ndarray) -> np.ndarray:
        if len(triangles) == 0:
            return np.empty((0, 3), dtype=np.float32)
        edges = np.concatenate(
            [
                triangles[:, [0, 1], :],
                triangles[:, [1, 2], :],
                triangles[:, [2, 0], :],
            ],
            axis=0,
        )
        return edges.reshape(-1, 3).astype(np.float32, copy=False)

    def _build_line_cache(self, max_points: int) -> dict[str, np.ndarray]:
        grouped: dict[str, list[np.ndarray]] = {kind: [] for kind in PATH_STYLE_MAP}
        point_budget: dict[str, int] = {kind: 0 for kind in PATH_STYLE_MAP}
        for points, kind in self._toolpaths:
            if kind not in grouped or len(points) < 2:
                continue
            point_budget[kind] += len(points)

        stride_by_kind = {
            kind: max(1, int(math.ceil(max(point_budget[kind], 1) / max(max_points, 1))))
            for kind in PATH_STYLE_MAP
        }

        for points, kind in self._toolpaths:
            if kind not in grouped or len(points) < 2:
                continue
            reduced = self._reduce_polyline(points, stride_by_kind[kind])
            if len(reduced) < 2:
                continue
            segments = np.stack([reduced[:-1], reduced[1:]], axis=1).reshape(-1, 3)
            grouped[kind].append(segments.astype(np.float32, copy=False))

        return {
            kind: np.concatenate(segments_list, axis=0) if segments_list else np.empty((0, 3), dtype=np.float32)
            for kind, segments_list in grouped.items()
        }

    def _reduce_polyline(self, points: np.ndarray, stride: int) -> np.ndarray:
        if stride <= 1 or len(points) <= 2:
            return points.astype(np.float32, copy=False)
        reduced = points[::stride]
        if not np.allclose(reduced[-1], points[-1]):
            reduced = np.vstack([reduced, points[-1]])
        return reduced.astype(np.float32, copy=False)

    def _build_build_plate_grid(self) -> np.ndarray:
        if self._bounds_min is None or self._bounds_max is None:
            return np.empty((0, 3), dtype=np.float32)

        xy_span = np.maximum(self._bounds_max[:2] - self._bounds_min[:2], 1.0)
        half_extent = float(np.max(xy_span) * 0.68 + self._scene_radius * 0.18)
        grid_step = self._nice_step(half_extent * 2.0 / 12.0)
        x_min = self._scene_center[0] - half_extent
        x_max = self._scene_center[0] + half_extent
        y_min = self._scene_center[1] - half_extent
        y_max = self._scene_center[1] + half_extent
        z_value = self._floor_z

        lines: list[np.ndarray] = []
        x_values = np.arange(math.floor(x_min / grid_step) * grid_step, x_max + grid_step * 0.5, grid_step, dtype=np.float32)
        y_values = np.arange(math.floor(y_min / grid_step) * grid_step, y_max + grid_step * 0.5, grid_step, dtype=np.float32)
        for x_value in x_values:
            lines.append(np.array([[x_value, y_min, z_value], [x_value, y_max, z_value]], dtype=np.float32))
        for y_value in y_values:
            lines.append(np.array([[x_min, y_value, z_value], [x_max, y_value, z_value]], dtype=np.float32))

        border = np.array(
            [
                [x_min, y_min, z_value],
                [x_max, y_min, z_value],
                [x_max, y_max, z_value],
                [x_min, y_max, z_value],
                [x_min, y_min, z_value],
            ],
            dtype=np.float32,
        )
        border_segments = np.stack([border[:-1], border[1:]], axis=1).reshape(-1, 3)
        lines.append(border_segments)
        return np.concatenate(lines, axis=0) if lines else np.empty((0, 3), dtype=np.float32)

    def _nice_step(self, rough_step: float) -> float:
        rough_step = max(float(rough_step), 0.5)
        power = 10 ** math.floor(math.log10(rough_step))
        fraction = rough_step / power
        if fraction < 1.5:
            return 1.0 * power
        if fraction < 3.5:
            return 2.0 * power
        if fraction < 7.5:
            return 5.0 * power
        return 10.0 * power

    def _create_gl_functions(self):
        profile = QOpenGLVersionProfile()
        profile.setVersion(2, 0)
        functions = QOpenGLVersionFunctionsFactory.get(profile, self.context())
        if functions is not None:
            return functions
        context = self.context()
        if context is not None and hasattr(context, "functions"):
            return context.functions()
        return None

    def _build_program(self, vertex_source: str, fragment_source: str) -> QOpenGLShaderProgram:
        program = QOpenGLShaderProgram(self)
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vertex_source):
            raise RuntimeError(program.log())
        if not program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragment_source):
            raise RuntimeError(program.log())
        if not program.link():
            raise RuntimeError(program.log())
        return program

    def _upload_scene_to_gpu(self) -> None:
        if self._gl is None:
            return
        self._replace_buffer(self._mesh_fill_full, self._mesh_vertex_data(self._mesh_triangles_full))
        self._replace_buffer(self._mesh_fill_interactive, self._mesh_vertex_data(self._mesh_triangles_interactive))
        self._replace_buffer(self._mesh_depth_buffer, self._mesh_vertex_data(self._mesh_triangles_occlusion))
        self._replace_buffer(self._mesh_wire_full, self._mesh_edges_full)
        self._replace_buffer(self._mesh_wire_interactive, self._mesh_edges_interactive)
        for kind in SELECTION_STYLE_MAP:
            self._replace_buffer(self._selection_fill_buffers[kind], self._mesh_vertex_data(self._selection_triangles[kind]))
            self._replace_buffer(self._selection_wire_buffers[kind], self._triangle_edges(self._selection_triangles[kind]))
        self._replace_buffer(self._grid_buffer, self._grid_lines)
        for kind in PATH_STYLE_MAP:
            self._replace_buffer(self._line_buffers_full[kind], self._segments_by_kind_full.get(kind, np.empty((0, 3), dtype=np.float32)))
            self._replace_buffer(self._line_buffers_interactive[kind], self._segments_by_kind_interactive.get(kind, np.empty((0, 3), dtype=np.float32)))
        self._scene_dirty = False

    def _mesh_vertex_data(self, triangles: np.ndarray) -> np.ndarray:
        if len(triangles) == 0:
            return np.empty((0, 6), dtype=np.float32)
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = normals / np.where(norms < 1e-6, 1.0, norms)
        normals = np.repeat(normals, 3, axis=0)
        vertices = triangles.reshape(-1, 3)
        return np.concatenate([vertices, normals], axis=1).astype(np.float32, copy=False)

    def _replace_buffer(self, target: _GpuBuffer, data: np.ndarray) -> None:
        if target.buffer is not None:
            target.buffer.destroy()
            target.buffer = None
        target.count = 0
        target.stride_bytes = 0
        if data.size == 0:
            return

        contiguous = np.ascontiguousarray(data.astype(np.float32, copy=False))
        buffer = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        buffer.create()
        buffer.bind()
        buffer.setUsagePattern(QOpenGLBuffer.UsagePattern.StaticDraw)
        buffer.allocate(contiguous.tobytes(), contiguous.nbytes)
        buffer.release()

        target.buffer = buffer
        target.count = int(contiguous.shape[0])
        target.stride_bytes = int(contiguous.shape[1] * 4) if contiguous.ndim == 2 else 12

    def _camera_matrices(self) -> tuple[QMatrix4x4, QMatrix4x4, QMatrix4x4]:
        aspect = max(self.width(), 1) / max(self.height(), 1)
        distance = self._scene_radius * (2.55 / max(self._zoom_factor, 1e-6))

        projection = QMatrix4x4()
        projection.perspective(36.0, aspect, max(self._scene_radius * 0.05, 0.1), max(self._scene_radius * 20.0, distance + self._scene_radius * 8.0))

        view = QMatrix4x4()
        view.translate(self._pan_x, self._pan_y, -distance)
        view.rotate(self._pitch_deg, 1.0, 0.0, 0.0)
        view.rotate(self._yaw_deg, 0.0, 0.0, 1.0)

        model = QMatrix4x4()
        model.translate(-float(self._scene_center[0]), -float(self._scene_center[1]), -float(self._scene_center[2]))

        model_view = view * model
        mvp = projection * model_view
        return projection, model_view, mvp

    def _draw_mesh(
        self,
        mesh_buffer: _GpuBuffer,
        model_view: QMatrix4x4,
        mvp: QMatrix4x4,
        color_rgba: tuple[float, float, float, float] | None = None,
    ) -> None:
        if mesh_buffer.buffer is None or mesh_buffer.count <= 0 or self._mesh_program is None:
            return

        self._mesh_program.bind()
        self._mesh_program.setUniformValue("u_mvp", mvp)
        self._mesh_program.setUniformValue("u_model_view", model_view)
        rgba = color_rgba or (0.57, 0.63, 0.72, 0.24 if self._interaction_active else 0.30)
        self._mesh_program.setUniformValue("u_color", QVector4D(*rgba))

        mesh_buffer.buffer.bind()
        position_loc = self._mesh_program.attributeLocation("a_position")
        normal_loc = self._mesh_program.attributeLocation("a_normal")
        self._mesh_program.enableAttributeArray(position_loc)
        self._mesh_program.enableAttributeArray(normal_loc)
        self._mesh_program.setAttributeBuffer(position_loc, _GL_FLOAT, 0, 3, mesh_buffer.stride_bytes)
        self._mesh_program.setAttributeBuffer(normal_loc, _GL_FLOAT, 12, 3, mesh_buffer.stride_bytes)

        self._gl.glDrawArrays(_GL_TRIANGLES, 0, mesh_buffer.count)

        self._mesh_program.disableAttributeArray(position_loc)
        self._mesh_program.disableAttributeArray(normal_loc)
        mesh_buffer.buffer.release()
        self._mesh_program.release()

    def _draw_depth_prepass(
        self,
        mesh_buffer: _GpuBuffer,
        model_view: QMatrix4x4,
        mvp: QMatrix4x4,
    ) -> None:
        if self._gl is None or mesh_buffer.buffer is None or mesh_buffer.count <= 0:
            return
        self._gl.glColorMask(False, False, False, False)
        self._gl.glDepthMask(True)
        self._draw_mesh(mesh_buffer, model_view, mvp, color_rgba=(0.0, 0.0, 0.0, 0.0))
        self._gl.glColorMask(True, True, True, True)

    def _draw_lines(
        self,
        line_buffer: _GpuBuffer,
        color: QColor,
        width: float,
        alpha: float,
        mvp: QMatrix4x4,
    ) -> None:
        if line_buffer.buffer is None or line_buffer.count <= 0 or self._line_program is None:
            return

        self._line_program.bind()
        self._line_program.setUniformValue("u_mvp", mvp)
        self._line_program.setUniformValue(
            "u_color",
            QVector4D(color.redF(), color.greenF(), color.blueF(), alpha),
        )

        line_buffer.buffer.bind()
        position_loc = self._line_program.attributeLocation("a_position")
        self._line_program.enableAttributeArray(position_loc)
        self._line_program.setAttributeBuffer(position_loc, _GL_FLOAT, 0, 3, line_buffer.stride_bytes)
        self._gl.glLineWidth(max(width, 1.0))
        self._gl.glDrawArrays(_GL_LINES, 0, line_buffer.count)
        self._line_program.disableAttributeArray(position_loc)
        line_buffer.buffer.release()
        self._line_program.release()

    def _pick_face(self, pixel_x: int, pixel_y: int) -> int | None:
        if len(self._faces) == 0 or len(self._vertices) == 0 or self.width() <= 1 or self.height() <= 1:
            return None

        ndc_x = (2.0 * float(pixel_x) / float(max(self.width() - 1, 1))) - 1.0
        ndc_y = 1.0 - (2.0 * float(pixel_y) / float(max(self.height() - 1, 1)))
        _, _, mvp = self._camera_matrices_np()
        try:
            inv_mvp = np.linalg.inv(mvp)
        except np.linalg.LinAlgError:
            return None

        near_clip = np.array([ndc_x, ndc_y, -1.0, 1.0], dtype=float)
        far_clip = np.array([ndc_x, ndc_y, 1.0, 1.0], dtype=float)
        near_world = inv_mvp @ near_clip
        far_world = inv_mvp @ far_clip
        if abs(near_world[3]) < 1e-9 or abs(far_world[3]) < 1e-9:
            return None
        near_world = near_world[:3] / near_world[3]
        far_world = far_world[:3] / far_world[3]
        direction = far_world - near_world
        direction_norm = float(np.linalg.norm(direction))
        if direction_norm < 1e-9:
            return None
        direction /= direction_norm

        triangles = np.asarray(self._vertices[self._faces], dtype=float)
        v0 = triangles[:, 0]
        edge1 = triangles[:, 1] - v0
        edge2 = triangles[:, 2] - v0
        pvec = np.cross(np.broadcast_to(direction, edge2.shape), edge2)
        det = np.einsum("ij,ij->i", edge1, pvec)
        valid = np.abs(det) > 1e-9
        if not np.any(valid):
            return None

        candidate_indices = np.nonzero(valid)[0]
        inv_det = 1.0 / det[valid]
        tvec = near_world[None, :] - v0[valid]
        u = np.einsum("ij,ij->i", tvec, pvec[valid]) * inv_det
        valid_u = (u >= -1e-6) & (u <= 1.0 + 1e-6)
        if not np.any(valid_u):
            return None

        candidate_indices = candidate_indices[valid_u]
        edge1 = edge1[valid][valid_u]
        edge2 = edge2[valid][valid_u]
        inv_det = inv_det[valid_u]
        tvec = tvec[valid_u]
        u = u[valid_u]
        qvec = np.cross(tvec, edge1)
        v = np.einsum("ij,ij->i", np.broadcast_to(direction, qvec.shape), qvec) * inv_det
        valid_v = (v >= -1e-6) & ((u + v) <= 1.0 + 1e-6)
        if not np.any(valid_v):
            return None

        candidate_indices = candidate_indices[valid_v]
        edge2 = edge2[valid_v]
        inv_det = inv_det[valid_v]
        qvec = qvec[valid_v]
        t = np.einsum("ij,ij->i", edge2, qvec) * inv_det
        valid_t = t >= 1e-6
        if not np.any(valid_t):
            return None

        candidate_indices = candidate_indices[valid_t]
        t = t[valid_t]
        return int(candidate_indices[int(np.argmin(t))])

    def _apply_face_brush(self, pixel_x: int, pixel_y: int) -> None:
        if not self._face_pick_enabled or not self._face_brush_enabled or self._face_pick_callback is None:
            return
        picked_faces = self._pick_faces_in_radius(pixel_x, pixel_y, self._face_brush_radius_px)
        if not picked_faces:
            return
        fresh_faces = [face_index for face_index in picked_faces if face_index not in self._brush_seen_faces]
        if not fresh_faces:
            return
        self._brush_seen_faces.update(fresh_faces)
        self._face_pick_callback(fresh_faces)

    def _pick_faces_in_radius(self, pixel_x: int, pixel_y: int, radius_px: int) -> list[int]:
        picked: list[int] = []
        seen: set[int] = set()
        for offset_x, offset_y in _disc_sample_offsets(radius_px):
            face_index = self._pick_face(pixel_x + offset_x, pixel_y + offset_y)
            if face_index is None or face_index in seen:
                continue
            seen.add(face_index)
            picked.append(face_index)
        return picked

    def _camera_matrices_np(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        aspect = max(self.width(), 1) / max(self.height(), 1)
        distance = self._scene_radius * (2.55 / max(self._zoom_factor, 1e-6))
        near_plane = max(self._scene_radius * 0.05, 0.1)
        far_plane = max(self._scene_radius * 20.0, distance + self._scene_radius * 8.0)

        projection = _perspective_matrix(36.0, aspect, near_plane, far_plane)
        view = _translation_matrix(self._pan_x, self._pan_y, -distance) @ _rotation_x_matrix(self._pitch_deg) @ _rotation_z_matrix(self._yaw_deg)
        model = _translation_matrix(-float(self._scene_center[0]), -float(self._scene_center[1]), -float(self._scene_center[2]))
        model_view = view @ model
        mvp = projection @ model_view
        return projection, model_view, mvp


def _perspective_matrix(fov_deg: float, aspect: float, near_plane: float, far_plane: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    matrix = np.zeros((4, 4), dtype=float)
    matrix[0, 0] = f / max(aspect, 1e-6)
    matrix[1, 1] = f
    matrix[2, 2] = (far_plane + near_plane) / (near_plane - far_plane)
    matrix[2, 3] = (2.0 * far_plane * near_plane) / (near_plane - far_plane)
    matrix[3, 2] = -1.0
    return matrix


def _translation_matrix(tx: float, ty: float, tz: float) -> np.ndarray:
    matrix = np.eye(4, dtype=float)
    matrix[0, 3] = tx
    matrix[1, 3] = ty
    matrix[2, 3] = tz
    return matrix


def _rotation_x_matrix(angle_deg: float) -> np.ndarray:
    angle_rad = math.radians(angle_deg)
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, c, -s, 0.0],
            [0.0, s, c, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def _rotation_z_matrix(angle_deg: float) -> np.ndarray:
    angle_rad = math.radians(angle_deg)
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    return np.array(
        [
            [c, -s, 0.0, 0.0],
            [s, c, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def _disc_sample_offsets(radius_px: int) -> list[tuple[int, int]]:
    radius_px = max(int(radius_px), 1)
    samples: list[tuple[int, int]] = [(0, 0)]
    rings = [(0.45, 6), (0.78, 12)]
    if radius_px >= 32:
        rings.append((1.0, 18))
    seen = {(0, 0)}
    for ring_ratio, sample_count in rings:
        ring_radius = radius_px * ring_ratio
        for sample_index in range(sample_count):
            angle = (2.0 * math.pi * sample_index) / sample_count
            offset = (
                int(round(math.cos(angle) * ring_radius)),
                int(round(math.sin(angle) * ring_radius)),
            )
            if offset in seen:
                continue
            seen.add(offset)
            samples.append(offset)
    return samples


def _wrap_angle_deg(angle_deg: float) -> float:
    wrapped = math.fmod(angle_deg, 360.0)
    if wrapped <= -180.0:
        wrapped += 360.0
    elif wrapped > 180.0:
        wrapped -= 360.0
    return wrapped
