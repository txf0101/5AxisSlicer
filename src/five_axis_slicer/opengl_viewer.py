from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import ctypes
import math
import time
from typing import Callable

import numpy as np
from PyQt5.QtCore import QPoint, Qt, QTimer
from PyQt5.QtWidgets import QOpenGLWidget

try:  # pragma: no cover - import availability is environment dependent.
    from OpenGL.GL import (
        GL_ARRAY_BUFFER,
        GL_BLEND,
        GL_COLOR_BUFFER_BIT,
        GL_DEPTH_BUFFER_BIT,
        GL_DEPTH_TEST,
        GL_FLOAT,
        GL_FRAGMENT_SHADER,
        GL_COLOR_ATTACHMENT0,
        GL_DEPTH_ATTACHMENT,
        GL_DEPTH_COMPONENT24,
        GL_FRAMEBUFFER,
        GL_FRAMEBUFFER_BINDING,
        GL_FRAMEBUFFER_COMPLETE,
        GL_LINES,
        GL_NEAREST,
        GL_ONE_MINUS_SRC_ALPHA,
        GL_RENDERBUFFER,
        GL_RGBA,
        GL_SRC_ALPHA,
        GL_STATIC_DRAW,
        GL_TEXTURE_2D,
        GL_TEXTURE_MAG_FILTER,
        GL_TEXTURE_MIN_FILTER,
        GL_TRIANGLES,
        GL_UNSIGNED_BYTE,
        GL_VERTEX_SHADER,
        glBindBuffer,
        glBindFramebuffer,
        glBindRenderbuffer,
        glBindTexture,
        glBlendFunc,
        glCheckFramebufferStatus,
        glBufferData,
        glClear,
        glClearColor,
        glDeleteBuffers,
        glDeleteFramebuffers,
        glDeleteRenderbuffers,
        glDeleteTextures,
        glDisable,
        glDrawArrays,
        glEnable,
        glEnableVertexAttribArray,
        glFramebufferRenderbuffer,
        glFramebufferTexture2D,
        glGenBuffers,
        glGenFramebuffers,
        glGenRenderbuffers,
        glGenTextures,
        glGetAttribLocation,
        glGetIntegerv,
        glGetUniformLocation,
        glLineWidth,
        glReadPixels,
        glRenderbufferStorage,
        glTexImage2D,
        glTexParameteri,
        glUniformMatrix4fv,
        glUseProgram,
        glVertexAttribPointer,
        glViewport,
    )
    from OpenGL.GL.shaders import compileProgram, compileShader

    OPENGL_AVAILABLE = True
except Exception:  # pragma: no cover - the VTK fallback handles this case.
    OPENGL_AVAILABLE = False

import vtk

from .geometry_vtk import edge_to_polydata, shape_to_polydata
from .gcode_preview import GCodePathSegment, GCodePreview, GCodeTimelineStep, PreviewSettings
from .models import CadModel, SelectionState


SelectionCallback = Callable[[str, str], None]

BG_COLOR = (0.08, 0.085, 0.09, 1.0)
EDGE_COLOR = (0.10, 0.10, 0.10, 0.84)
EDGE_SELECTED_COLOR = (1.0, 0.92, 0.42, 1.0)
BODY_SELECTED_COLOR = (0.98, 0.98, 0.98, 0.92)
CURRENT_COLOR = (1.0, 1.0, 1.0, 1.0)
BEAD_SECTION_SIDES = 6
STATIC_SOLID_SEGMENT_LIMIT = 18_000
INTERACTIVE_LINE_SEGMENT_LIMIT = 35_000
INITIAL_SOLID_SETTLE_MS = 1200


@dataclass(slots=True)
class _Buffer:
    vertices: np.ndarray
    colors: np.ndarray
    primitive: int
    vbo: int = 0
    dirty: bool = True

    @property
    def count(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def nbytes(self) -> int:
        return int(self.vertices.nbytes + self.colors.nbytes)


@dataclass(slots=True)
class _EdgeSegment:
    edge_id: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]


class OpenGLModelViewer(QOpenGLWidget):
    backend = "opengl"

    def __init__(self, parent=None) -> None:
        if not OPENGL_AVAILABLE:
            raise RuntimeError("PyOpenGL is not available")
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

        self.model: CadModel | None = None
        self.selection = SelectionState()
        self.selection_callback: SelectionCallback | None = None
        self.gcode_preview: GCodePreview | None = None
        self.preview_settings = PreviewSettings(render_backend=self.backend)
        self.visible_path_segment_count = 0
        self.drawn_path_segment_count = 0
        self.path_render_mode = "opengl_line"
        self._interaction_preview = False
        self._progress_dragging = False

        self._program = 0
        self._position_loc = -1
        self._color_loc = -1
        self._mvp_loc = -1
        self._buffers: dict[str, _Buffer] = {}
        self._edge_segments: list[_EdgeSegment] = []
        self._pick_id_to_edge: dict[int, str] = {}
        self._path_cache_key: tuple | None = None
        self._solid_stride = 1

        self._center = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self._pan = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self._radius = 80.0
        self._distance = 220.0
        self._yaw = math.radians(35.0)
        self._pitch = math.radians(25.0)
        self._last_mouse: QPoint | None = None
        self._mouse_moved = False

        self._frame_ms: deque[float] = deque(maxlen=120)
        self._last_progress_ms = 0.0
        self._last_gpu_draw_count = 0
        self._last_memory_bytes = 0
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.setInterval(150)
        self._settle_timer.timeout.connect(self._finish_interaction_preview)

    def set_selection_callback(self, callback: SelectionCallback) -> None:
        self.selection_callback = callback

    def load_model(self, model: CadModel) -> None:
        self.model = model
        self.selection.clear()
        self._edge_segments.clear()
        body_vertices: list[tuple[float, float, float]] = []
        body_colors: list[tuple[float, float, float, float]] = []

        for body in model.bodies:
            polydata = shape_to_polydata(model.shapes[body.body_id])
            body.triangle_count = polydata.GetNumberOfPolys()
            triangles = _polydata_triangles(polydata)
            color = BODY_SELECTED_COLOR if body.body_id in self.selection.body_ids else (*body.color, 0.92)
            body_vertices.extend(triangles)
            body_colors.extend([color] * len(triangles))

            for edge_id in body.edge_ids:
                edge_polydata = edge_to_polydata(model.edge_shapes[edge_id], segments=28)
                self._edge_segments.extend(
                    _EdgeSegment(edge_id, start, end)
                    for start, end in _polydata_lines(edge_polydata)
                )

        self._set_buffer("model", body_vertices, body_colors, GL_TRIANGLES)
        self._refresh_edge_buffers()
        self._path_cache_key = None
        if self.gcode_preview is not None:
            self.refresh_path_preview()
        self.fit_view()

    def load_gcode_preview(self, preview: GCodePreview) -> None:
        self.gcode_preview = preview
        self.preview_settings = PreviewSettings(
            layer_min=preview.layer_min,
            layer_max=preview.layer_max,
            show_travel=False,
            show_extrusion=True,
            show_pose_samples=False,
            render_backend=self.backend,
        )
        self.preview_settings.progress_index = max(
            0,
            preview.timeline_count_for_layers(preview.layer_min, preview.layer_max) - 1,
        )
        self._path_cache_key = None
        self._settle_timer.stop()
        self._progress_dragging = True
        self.refresh_selection()
        self.refresh_path_preview()
        self._settle_timer.start(INITIAL_SOLID_SETTLE_MS)
        self.fit_view()

    def clear_gcode_preview(self) -> None:
        self.gcode_preview = None
        self.visible_path_segment_count = 0
        self.drawn_path_segment_count = 0
        self._path_cache_key = None
        for key in ("path_line", "path_solid", "current", "pose"):
            self._set_buffer(key, [], [], GL_LINES)
        self.refresh_selection()
        self.update()

    def set_preview_layers(self, layer_min: int, layer_max: int) -> None:
        if self.gcode_preview is None:
            return
        low = max(self.gcode_preview.layer_min, min(layer_min, layer_max))
        high = min(self.gcode_preview.layer_max, max(layer_min, layer_max))
        self.preview_settings.layer_min = low
        self.preview_settings.layer_max = high
        self._clamp_progress_index()
        self._path_cache_key = None
        self.refresh_path_preview()

    def set_preview_progress(self, progress_index: int, interactive: bool | None = None) -> None:
        if self.gcode_preview is None:
            return
        started = time.perf_counter()
        if interactive is True:
            self._settle_timer.stop()
            self._progress_dragging = True
        elif interactive is False and self._progress_dragging:
            self._settle_timer.start(150)
        elif interactive is False:
            self._progress_dragging = False
        self.preview_settings.progress_index = int(progress_index)
        self._clamp_progress_index()
        self.refresh_path_preview()
        self._last_progress_ms = (time.perf_counter() - started) * 1000.0

    def set_progress_interaction(self, active: bool) -> None:
        if self.gcode_preview is None:
            return
        if active:
            self._settle_timer.stop()
            self._progress_dragging = True
            self.refresh_path_preview()
            return
        if self._progress_dragging:
            self._settle_timer.start(150)
            return
        self.refresh_path_preview()

    def set_preview_visibility(
        self,
        show_travel: bool | None = None,
        show_extrusion: bool | None = None,
        visible_roles: list[str] | set[str] | None = None,
        show_pose_samples: bool | None = None,
    ) -> None:
        if show_travel is not None:
            self.preview_settings.show_travel = bool(show_travel)
        if show_extrusion is not None:
            self.preview_settings.show_extrusion = bool(show_extrusion)
        if visible_roles is not None:
            self.preview_settings.visible_roles = set(visible_roles)
        if show_pose_samples is not None:
            self.preview_settings.show_pose_samples = bool(show_pose_samples)
        self._path_cache_key = None
        if self.gcode_preview is not None:
            self.refresh_path_preview()

    def preview_state(self) -> dict:
        perf = self.performance_state()
        return {
            "summary": None if self.gcode_preview is None else self.gcode_preview.summary(),
            "settings": self.preview_settings.to_json(),
            "visible_path_segment_count": self.visible_path_segment_count,
            "drawn_path_segment_count": self.drawn_path_segment_count,
            "render_mode": self.path_render_mode,
            "progress": self.progress_state(),
            "backend": self.backend,
            "quality_mode": self.preview_settings.quality_mode,
            "frame_ms": perf["frame_ms_avg"],
            "gpu_draw_count": perf["gpu_draw_count"],
            "cache_format": None if self.gcode_preview is None else self.gcode_preview.summary().get("cache_format"),
        }

    def performance_state(self) -> dict:
        samples = list(self._frame_ms)
        avg = sum(samples) / len(samples) if samples else 0.0
        max_frame = max(samples) if samples else 0.0
        fps = 0.0 if avg <= 0 else 1000.0 / avg
        return {
            "backend": self.backend,
            "quality_mode": self.preview_settings.quality_mode,
            "frame_ms_avg": avg,
            "frame_ms_max": max_frame,
            "fps_avg": fps,
            "progress_update_ms": self._last_progress_ms,
            "gpu_draw_count": self._last_gpu_draw_count,
            "gpu_memory_estimate_mb": self._last_memory_bytes / (1024.0 * 1024.0),
            "buffers": {key: buffer.count for key, buffer in self._buffers.items()},
        }

    def progress_state(self) -> dict:
        if self.gcode_preview is None:
            return {
                "domain": "layer_filtered_gcode_order",
                "layer_step_count": 0,
                "progress_index": 0,
                "current_global_step": None,
                "current_step": None,
            }
        return self.gcode_preview.progress_state(
            self.preview_settings.layer_min,
            self.preview_settings.layer_max,
            self.preview_settings.progress_index,
        )

    def current_progress_step(self) -> GCodeTimelineStep | None:
        if self.gcode_preview is None:
            return None
        return self.gcode_preview.timeline_step_for_layer_progress(
            self.preview_settings.layer_min,
            self.preview_settings.layer_max,
            self.preview_settings.progress_index,
        )

    def representative_path_segment(self):
        if self.gcode_preview is None:
            return None
        current = self.current_progress_step()
        if current is not None:
            index = current.path_segment_index
            if index is None:
                index = self.gcode_preview.segment_index_for_step(current.step_index)
            if index is None:
                index = self.gcode_preview.nearest_segment_index_for_step(current.step_index)
            if index is not None and 0 <= index < len(self.gcode_preview.segments):
                return self.gcode_preview.segments[index]
        for segment in self.gcode_preview.segments:
            if self._segment_visible(segment) and segment.has_spatial_length:
                return segment
        return None

    def set_mode(self, mode: str) -> None:
        if mode != "edge":
            raise ValueError("Preview picking is fixed to edge mode.")
        self.selection.mode = "edge"
        self.update()

    def set_selection(self, body_ids: list[str] | None = None, edge_ids: list[str] | None = None) -> None:
        if body_ids is not None:
            self.selection.body_ids = set(body_ids)
        if edge_ids is not None:
            self.selection.edge_ids = set(edge_ids)
        self.refresh_selection()

    def clear_selection(self) -> None:
        self.selection.clear()
        self.refresh_selection()

    def refresh_selection(self) -> None:
        self._refresh_edge_buffers()
        if self.model is not None:
            body_vertices: list[tuple[float, float, float]] = []
            body_colors: list[tuple[float, float, float, float]] = []
            alpha = 0.30 if self.gcode_preview is not None else 0.92
            for body in self.model.bodies:
                polydata = shape_to_polydata(self.model.shapes[body.body_id])
                triangles = _polydata_triangles(polydata)
                color = BODY_SELECTED_COLOR if body.body_id in self.selection.body_ids else (*body.color, alpha)
                body_vertices.extend(triangles)
                body_colors.extend([color] * len(triangles))
            self._set_buffer("model", body_vertices, body_colors, GL_TRIANGLES)
        self.update()

    def fit_view(self) -> None:
        bounds = self._scene_bounds()
        if bounds is not None:
            low, high = bounds
            self._center = (low + high) * 0.5
            diag = float(np.linalg.norm(high - low))
            self._radius = max(diag * 0.5, 1.0)
            self._distance = max(self._radius * 2.8, 20.0)
            self._pan = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self.update()

    def home_view(self) -> None:
        self._yaw = math.radians(35.0)
        self._pitch = math.radians(25.0)
        self.fit_view()

    def camera_command(self, command: str, value: float = 10.0) -> None:
        if command == "fit":
            self.fit_view()
            return
        if command == "home":
            self.home_view()
            return
        if command == "azimuth":
            self._yaw += math.radians(value)
        elif command == "elevation":
            self._pitch = max(math.radians(-85.0), min(math.radians(85.0), self._pitch + math.radians(value)))
        elif command == "zoom":
            self._distance = max(1.0, self._distance / max(value, 1e-6))
        elif command == "pan":
            self._pan[0] += value * self._radius
        elif command == "pan_y":
            self._pan[1] += value * self._radius
        else:
            raise ValueError(f"Unknown camera command: {command}")
        self.update()

    def refresh_path_preview(self) -> None:
        if self.gcode_preview is None:
            return
        state = self.progress_state()
        current_global_step = state.get("current_global_step")
        interactive = self._interaction_preview or self._progress_dragging
        solid = self.preview_settings.solid_rendering and not interactive
        mode_key = "solid" if solid else "line"
        cache_key = (
            mode_key,
            self.preview_settings.layer_min,
            self.preview_settings.layer_max,
            self.preview_settings.show_travel,
            self.preview_settings.show_extrusion,
            tuple(sorted(self.preview_settings.visible_roles)),
            self.preview_settings.show_pose_samples,
            self.preview_settings.show_upcoming,
            None if self.preview_settings.show_upcoming else current_global_step,
        )
        if cache_key != self._path_cache_key:
            self._rebuild_path_buffers(solid, current_global_step)
            self._path_cache_key = cache_key
        self._refresh_current_buffer()
        self.update()

    def render(self) -> None:
        self.update()

    def Initialize(self) -> None:  # noqa: N802 - VTK compatibility
        return

    def _finish_interaction_preview(self) -> None:
        if self.gcode_preview is None:
            return
        self._interaction_preview = False
        self._progress_dragging = False
        self.refresh_path_preview()

    def initializeGL(self) -> None:  # noqa: N802 - Qt API
        glClearColor(*BG_COLOR)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self._program = compileProgram(
            compileShader(_VERTEX_SHADER, GL_VERTEX_SHADER),
            compileShader(_FRAGMENT_SHADER, GL_FRAGMENT_SHADER),
        )
        self._position_loc = glGetAttribLocation(self._program, "position")
        self._color_loc = glGetAttribLocation(self._program, "color")
        self._mvp_loc = glGetUniformLocation(self._program, "mvp")
        for buffer in self._buffers.values():
            buffer.dirty = True

    def resizeGL(self, width: int, height: int) -> None:  # noqa: N802 - Qt API
        glViewport(0, 0, max(1, width), max(1, height))

    def paintGL(self) -> None:  # noqa: N802 - Qt API
        started = time.perf_counter()
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self._program == 0:
            return
        glUseProgram(self._program)
        mvp = self._projection_matrix() @ self._view_matrix()
        glUniformMatrix4fv(self._mvp_loc, 1, True, mvp.astype(np.float32))

        draw_count = 0
        draw_count += self._draw_buffer("model", line_width=1.0)
        draw_count += self._draw_buffer("edge", line_width=2.2)
        draw_count += self._draw_buffer("edge_selected", line_width=5.0)
        if self.path_render_mode.startswith("opengl_solid"):
            draw_count += self._draw_buffer("path_solid", line_width=1.0)
        else:
            draw_count += self._draw_buffer("path_line", line_width=2.4)
        draw_count += self._draw_buffer("pose", line_width=1.3)
        draw_count += self._draw_buffer("current", line_width=4.5)
        glUseProgram(0)

        self._last_gpu_draw_count = draw_count
        self._last_memory_bytes = sum(buffer.nbytes for buffer in self._buffers.values())
        self._frame_ms.append((time.perf_counter() - started) * 1000.0)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._last_mouse = event.pos()
        self._mouse_moved = False
        if event.button() == Qt.LeftButton and self.gcode_preview is not None:
            self._settle_timer.stop()
            self._interaction_preview = True
            self.refresh_path_preview()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._last_mouse is None:
            return
        delta = event.pos() - self._last_mouse
        if abs(delta.x()) + abs(delta.y()) > 1:
            self._mouse_moved = True
        if event.buttons() & Qt.LeftButton:
            self._yaw += delta.x() * 0.01
            self._pitch = max(math.radians(-85.0), min(math.radians(85.0), self._pitch + delta.y() * 0.01))
            self.update()
        elif event.buttons() & Qt.RightButton:
            self._pan[0] += delta.x() * self._radius / max(self.width(), 1)
            self._pan[1] -= delta.y() * self._radius / max(self.height(), 1)
            self.update()
        self._last_mouse = event.pos()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton and not self._mouse_moved:
            edge_id = self._pick_edge(event.pos())
            if edge_id is not None:
                self._toggle_edge(edge_id)
        if self.gcode_preview is not None:
            self._settle_timer.start(150)
        self._last_mouse = None
        self._mouse_moved = False

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        delta = event.angleDelta().y()
        factor = 1.12 if delta > 0 else 0.89
        self.camera_command("zoom", factor)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        modifiers = event.modifiers()
        key = event.key()
        if modifiers & Qt.ShiftModifier:
            if key == Qt.Key_Left:
                self.camera_command("pan", -0.08)
                return
            if key == Qt.Key_Right:
                self.camera_command("pan", 0.08)
                return
            if key == Qt.Key_Up:
                self.camera_command("pan_y", 0.08)
                return
            if key == Qt.Key_Down:
                self.camera_command("pan_y", -0.08)
                return
        if key == Qt.Key_Left:
            self.camera_command("azimuth", -8)
            return
        if key == Qt.Key_Right:
            self.camera_command("azimuth", 8)
            return
        if key == Qt.Key_Up:
            self.camera_command("elevation", 8)
            return
        if key == Qt.Key_Down:
            self.camera_command("elevation", -8)
            return
        super().keyPressEvent(event)

    def _clamp_progress_index(self) -> None:
        if self.gcode_preview is None:
            self.preview_settings.progress_index = 0
            return
        count = self.gcode_preview.timeline_count_for_layers(
            self.preview_settings.layer_min,
            self.preview_settings.layer_max,
        )
        self.preview_settings.progress_index = 0 if count == 0 else max(0, min(self.preview_settings.progress_index, count - 1))

    def _segment_visible(self, segment: GCodePathSegment) -> bool:
        settings = self.preview_settings
        if segment.layer < settings.layer_min or segment.layer > settings.layer_max:
            return False
        if segment.move_type == "extrude":
            return settings.show_extrusion and segment.extrusion_role in settings.visible_roles
        if segment.move_type == "travel":
            return settings.show_travel
        return settings.show_travel and segment.has_spatial_length

    def _rebuild_path_buffers(self, solid: bool, current_global_step: int | None) -> None:
        if self.gcode_preview is None:
            return
        visible = []
        for segment in self.gcode_preview.segments:
            if not self._segment_visible(segment) or not segment.has_spatial_length:
                continue
            if (
                current_global_step is not None
                and not self.preview_settings.show_upcoming
                and segment.step_index > current_global_step
            ):
                continue
            visible.append(segment)

        self.visible_path_segment_count = len(visible)
        if solid:
            stride = _render_stride(len(visible), STATIC_SOLID_SEGMENT_LIMIT)
            self._solid_stride = stride
            self.path_render_mode = "opengl_solid" if stride == 1 else f"opengl_solid_adaptive_{stride}"
            vertices, colors, drawn = _build_bead_arrays(visible, stride)
            self._set_buffer("path_solid", vertices, colors, GL_TRIANGLES)
            self._set_buffer("path_line", [], [], GL_LINES)
            self.drawn_path_segment_count = drawn
        else:
            stride = _render_stride(len(visible), INTERACTIVE_LINE_SEGMENT_LIMIT)
            self.path_render_mode = "opengl_line_interactive" if self._interaction_preview or self._progress_dragging else "opengl_line"
            vertices, colors, drawn = _build_line_arrays(visible, stride)
            self._set_buffer("path_line", vertices, colors, GL_LINES)
            self._set_buffer("path_solid", [], [], GL_TRIANGLES)
            self.drawn_path_segment_count = drawn
        self._refresh_pose_buffer(visible)

    def _refresh_current_buffer(self) -> None:
        segment = self.representative_path_segment()
        if segment is None or not segment.has_spatial_length:
            self._set_buffer("current", [], [], GL_LINES)
            return
        self._set_buffer("current", [segment.start, segment.end], [CURRENT_COLOR, CURRENT_COLOR], GL_LINES)

    def _refresh_pose_buffer(self, visible_segments: list[GCodePathSegment]) -> None:
        if not self.preview_settings.show_pose_samples:
            self._set_buffer("pose", [], [], GL_LINES)
            return
        candidates = [
            segment
            for segment in visible_segments
            if segment.move_type == "extrude" and (segment.rotary_end or segment.rotary_start)
        ]
        if not candidates:
            self._set_buffer("pose", [], [], GL_LINES)
            return
        from .viewer import _nozzle_axis_from_rotary

        step = max(1, len(candidates) // 120)
        length = 4.0
        if self.gcode_preview is not None and self.gcode_preview.bounds is not None:
            low, high = self.gcode_preview.bounds
            diag = math.dist(low, high)
            length = max(2.0, min(12.0, diag * 0.035))
        vertices: list[tuple[float, float, float]] = []
        colors: list[tuple[float, float, float, float]] = []
        color = (0.18, 0.78, 0.95, 0.55)
        for segment in candidates[::step]:
            axis = _nozzle_axis_from_rotary(segment.rotary_end or segment.rotary_start)
            start = segment.end
            end = tuple(start[index] + axis[index] * length for index in range(3))
            vertices.extend([start, end])
            colors.extend([color, color])
        self._set_buffer("pose", vertices, colors, GL_LINES)

    def _refresh_edge_buffers(self) -> None:
        edge_vertices: list[tuple[float, float, float]] = []
        edge_colors: list[tuple[float, float, float, float]] = []
        selected_vertices: list[tuple[float, float, float]] = []
        selected_colors: list[tuple[float, float, float, float]] = []
        pick_vertices: list[tuple[float, float, float]] = []
        pick_colors: list[tuple[float, float, float, float]] = []
        edge_pick_ids: dict[str, int] = {}
        self._pick_id_to_edge = {}
        for segment in self._edge_segments:
            target_vertices = selected_vertices if segment.edge_id in self.selection.edge_ids else edge_vertices
            target_colors = selected_colors if segment.edge_id in self.selection.edge_ids else edge_colors
            color = EDGE_SELECTED_COLOR if segment.edge_id in self.selection.edge_ids else EDGE_COLOR
            target_vertices.extend([segment.start, segment.end])
            target_colors.extend([color, color])
            pick_id = edge_pick_ids.get(segment.edge_id)
            if pick_id is None:
                pick_id = len(edge_pick_ids) + 1
                edge_pick_ids[segment.edge_id] = pick_id
                self._pick_id_to_edge[pick_id] = segment.edge_id
            pick_color = _encode_pick_color(pick_id)
            pick_vertices.extend([segment.start, segment.end])
            pick_colors.extend([pick_color, pick_color])
        self._set_buffer("edge", edge_vertices, edge_colors, GL_LINES)
        self._set_buffer("edge_selected", selected_vertices, selected_colors, GL_LINES)
        self._set_buffer("edge_pick", pick_vertices, pick_colors, GL_LINES)

    def _toggle_edge(self, edge_id: str) -> None:
        if edge_id in self.selection.edge_ids:
            self.selection.edge_ids.remove(edge_id)
        else:
            self.selection.edge_ids.add(edge_id)
        self.refresh_selection()
        if self.selection_callback is not None:
            self.selection_callback("edge", edge_id)

    def _pick_edge(self, pos: QPoint) -> str | None:
        picked = self._pick_edge_by_color_id(pos)
        if picked is not None:
            return picked
        return self._pick_edge_by_projection(pos)

    def _pick_edge_by_projection(self, pos: QPoint) -> str | None:
        if not self._edge_segments:
            return None
        mvp = self._projection_matrix() @ self._view_matrix()
        point = np.array([float(pos.x()), float(pos.y())], dtype=np.float32)
        best: tuple[float, str] | None = None
        for segment in self._edge_segments:
            left = self._project(segment.start, mvp)
            right = self._project(segment.end, mvp)
            if left is None or right is None:
                continue
            dist = _distance_to_screen_segment(point, left, right)
            if best is None or dist < best[0]:
                best = (dist, segment.edge_id)
        if best is not None and best[0] <= 8.0:
            return best[1]
        return None

    def _pick_edge_by_color_id(self, pos: QPoint) -> str | None:
        if self._program == 0 or not self._pick_id_to_edge or self.width() <= 0 or self.height() <= 0:
            return None
        framebuffer = texture = depth = 0
        previous_framebuffer = 0
        context_ready = False
        try:
            self.makeCurrent()
            context_ready = True
            width = max(1, int(self.width()))
            height = max(1, int(self.height()))
            previous_framebuffer = int(glGetIntegerv(GL_FRAMEBUFFER_BINDING))

            framebuffer = int(glGenFramebuffers(1))
            texture = int(glGenTextures(1))
            depth = int(glGenRenderbuffers(1))

            glBindTexture(GL_TEXTURE_2D, texture)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

            glBindRenderbuffer(GL_RENDERBUFFER, depth)
            glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, width, height)

            glBindFramebuffer(GL_FRAMEBUFFER, framebuffer)
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0)
            glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depth)
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                return None

            glViewport(0, 0, width, height)
            glDisable(GL_BLEND)
            glClearColor(0.0, 0.0, 0.0, 0.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glUseProgram(self._program)
            mvp = self._projection_matrix() @ self._view_matrix()
            glUniformMatrix4fv(self._mvp_loc, 1, True, mvp.astype(np.float32))
            self._draw_buffer("edge_pick", line_width=9.0)
            read_y = max(0, min(height - 1, height - int(pos.y()) - 1))
            read_x = max(0, min(width - 1, int(pos.x())))
            pixel = glReadPixels(read_x, read_y, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE)
            values = np.frombuffer(pixel, dtype=np.uint8)
            if values.size < 3:
                return None
            pick_id = int(values[0]) | (int(values[1]) << 8) | (int(values[2]) << 16)
            return self._pick_id_to_edge.get(pick_id)
        except Exception:
            return None
        finally:
            if context_ready:
                if previous_framebuffer:
                    glBindFramebuffer(GL_FRAMEBUFFER, previous_framebuffer)
                else:
                    glBindFramebuffer(GL_FRAMEBUFFER, 0)
                glViewport(0, 0, max(1, int(self.width())), max(1, int(self.height())))
                glClearColor(*BG_COLOR)
                glEnable(GL_BLEND)
                if depth:
                    glDeleteRenderbuffers(1, [depth])
                if texture:
                    glDeleteTextures(1, [texture])
                if framebuffer:
                    glDeleteFramebuffers(1, [framebuffer])
                self.doneCurrent()

    def _project(self, point: tuple[float, float, float], mvp: np.ndarray) -> np.ndarray | None:
        clip = mvp @ np.array([point[0], point[1], point[2], 1.0], dtype=np.float32)
        if abs(float(clip[3])) < 1e-6:
            return None
        ndc = clip[:3] / clip[3]
        x = (ndc[0] * 0.5 + 0.5) * self.width()
        y = (1.0 - (ndc[1] * 0.5 + 0.5)) * self.height()
        return np.array([x, y], dtype=np.float32)

    def _set_buffer(
        self,
        key: str,
        vertices: list[tuple[float, float, float]] | np.ndarray,
        colors: list[tuple[float, float, float, float]] | np.ndarray,
        primitive: int,
    ) -> None:
        vertex_array = np.asarray(vertices, dtype=np.float32).reshape((-1, 3)) if len(vertices) else np.empty((0, 3), dtype=np.float32)
        color_array = np.asarray(colors, dtype=np.float32).reshape((-1, 4)) if len(colors) else np.empty((0, 4), dtype=np.float32)
        old = self._buffers.get(key)
        vbo = 0 if old is None else old.vbo
        self._buffers[key] = _Buffer(vertex_array, color_array, primitive, vbo=vbo, dirty=True)

    def _draw_buffer(self, key: str, line_width: float) -> int:
        buffer = self._buffers.get(key)
        if buffer is None or buffer.count == 0:
            return 0
        if buffer.vbo == 0:
            buffer.vbo = int(glGenBuffers(1))
            buffer.dirty = True
        if buffer.dirty:
            packed = np.hstack((buffer.vertices, buffer.colors)).astype(np.float32, copy=False)
            glBindBuffer(GL_ARRAY_BUFFER, buffer.vbo)
            glBufferData(GL_ARRAY_BUFFER, packed.nbytes, packed, GL_STATIC_DRAW)
            buffer.dirty = False
        glBindBuffer(GL_ARRAY_BUFFER, buffer.vbo)
        stride = 7 * 4
        glEnableVertexAttribArray(self._position_loc)
        glEnableVertexAttribArray(self._color_loc)
        glVertexAttribPointer(self._position_loc, 3, GL_FLOAT, False, stride, ctypes.c_void_p(0))
        glVertexAttribPointer(self._color_loc, 4, GL_FLOAT, False, stride, ctypes.c_void_p(3 * 4))
        if buffer.primitive == GL_LINES:
            glLineWidth(line_width)
        glDrawArrays(buffer.primitive, 0, buffer.count)
        return 1

    def _scene_bounds(self) -> tuple[np.ndarray, np.ndarray] | None:
        points: list[np.ndarray] = []
        for key in ("model", "path_line", "path_solid"):
            buffer = self._buffers.get(key)
            if buffer is not None and buffer.count:
                points.append(buffer.vertices)
        if self.gcode_preview is not None and self.gcode_preview.bounds is not None:
            low, high = self.gcode_preview.bounds
            points.append(np.asarray([low, high], dtype=np.float32))
        if not points:
            return None
        merged = np.vstack(points)
        return np.min(merged, axis=0), np.max(merged, axis=0)

    def _view_matrix(self) -> np.ndarray:
        target = self._center + self._pan
        direction = np.array(
            [
                math.cos(self._pitch) * math.sin(self._yaw),
                math.sin(self._pitch),
                math.cos(self._pitch) * math.cos(self._yaw),
            ],
            dtype=np.float32,
        )
        eye = target + direction * self._distance
        return _look_at(eye, target, np.array([0.0, 0.0, 1.0], dtype=np.float32))

    def _projection_matrix(self) -> np.ndarray:
        aspect = max(self.width(), 1) / max(self.height(), 1)
        near = max(0.1, self._distance - self._radius * 4.0)
        far = self._distance + self._radius * 6.0 + 100.0
        return _perspective(math.radians(45.0), aspect, near, far)

    def close(self) -> bool:  # noqa: D102 - Qt API
        self.makeCurrent()
        for buffer in self._buffers.values():
            if buffer.vbo:
                glDeleteBuffers(1, [buffer.vbo])
                buffer.vbo = 0
        self.doneCurrent()
        return super().close()


def _polydata_triangles(polydata) -> list[tuple[float, float, float]]:
    points = polydata.GetPoints()
    if points is None:
        return []
    output: list[tuple[float, float, float]] = []
    ids = vtk.vtkIdList()
    polys = polydata.GetPolys()
    polys.InitTraversal()
    while polys.GetNextCell(ids):
        count = ids.GetNumberOfIds()
        if count < 3:
            continue
        first = tuple(points.GetPoint(ids.GetId(0)))
        for index in range(1, count - 1):
            output.append(first)
            output.append(tuple(points.GetPoint(ids.GetId(index))))
            output.append(tuple(points.GetPoint(ids.GetId(index + 1))))
    return output


def _polydata_lines(polydata) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    points = polydata.GetPoints()
    if points is None:
        return []
    output: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
    ids = vtk.vtkIdList()
    lines = polydata.GetLines()
    lines.InitTraversal()
    while lines.GetNextCell(ids):
        for index in range(ids.GetNumberOfIds() - 1):
            output.append((tuple(points.GetPoint(ids.GetId(index))), tuple(points.GetPoint(ids.GetId(index + 1)))))
    return output


def _build_line_arrays(
    segments: list[GCodePathSegment],
    stride: int,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float, float]], int]:
    vertices: list[tuple[float, float, float]] = []
    colors: list[tuple[float, float, float, float]] = []
    drawn = 0
    for index, segment in enumerate(segments):
        if stride > 1 and index % stride != 0:
            continue
        color = (*segment.color(), 0.96 if segment.move_type == "extrude" else 0.48)
        vertices.extend([segment.start, segment.end])
        colors.extend([color, color])
        drawn += 1
    return vertices, colors, drawn


def _build_bead_arrays(
    segments: list[GCodePathSegment],
    stride: int,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float, float]], int]:
    from .viewer import _bead_frame

    vertices: list[tuple[float, float, float]] = []
    colors: list[tuple[float, float, float, float]] = []
    drawn = 0
    for index, segment in enumerate(segments):
        if segment.move_type != "extrude":
            continue
        if stride > 1 and index % stride != 0:
            continue
        frame = _bead_frame(segment.start, segment.end, segment.rotary_end or segment.rotary_start)
        if frame is None:
            continue
        _tangent, width_axis, height_axis = frame
        width_radius = max(segment.bead_width, 1e-6) * 0.5
        height_radius = max(segment.bead_height, 1e-6) * 0.5
        start_ring: list[tuple[float, float, float]] = []
        end_ring: list[tuple[float, float, float]] = []
        for side in range(BEAD_SECTION_SIDES):
            angle = 2.0 * math.pi * side / BEAD_SECTION_SIDES
            offset = tuple(
                math.cos(angle) * width_radius * width_axis[axis]
                + math.sin(angle) * height_radius * height_axis[axis]
                for axis in range(3)
            )
            start_ring.append(tuple(segment.start[axis] + offset[axis] for axis in range(3)))
            end_ring.append(tuple(segment.end[axis] + offset[axis] for axis in range(3)))
        color = (*segment.color(), 0.96)
        for side in range(BEAD_SECTION_SIDES):
            next_side = (side + 1) % BEAD_SECTION_SIDES
            quad = [start_ring[side], start_ring[next_side], end_ring[next_side], end_ring[side]]
            vertices.extend([quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]])
            colors.extend([color] * 6)
        drawn += 1
    return vertices, colors, drawn


def _render_stride(count: int, limit: int) -> int:
    if count <= 0 or limit <= 0:
        return 1
    return max(1, math.ceil(count / limit))


def _normalize(vector: np.ndarray) -> np.ndarray:
    length = float(np.linalg.norm(vector))
    if length <= 1e-12:
        return vector
    return vector / length


def _look_at(eye: np.ndarray, target: np.ndarray, up: np.ndarray) -> np.ndarray:
    forward = _normalize(target - eye)
    side = _normalize(np.cross(forward, up))
    if float(np.linalg.norm(side)) <= 1e-12:
        side = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    true_up = np.cross(side, forward)
    matrix = np.identity(4, dtype=np.float32)
    matrix[0, :3] = side
    matrix[1, :3] = true_up
    matrix[2, :3] = -forward
    translate = np.identity(4, dtype=np.float32)
    translate[:3, 3] = -eye
    return matrix @ translate


def _perspective(fovy: float, aspect: float, near: float, far: float) -> np.ndarray:
    focal = 1.0 / math.tan(fovy * 0.5)
    matrix = np.zeros((4, 4), dtype=np.float32)
    matrix[0, 0] = focal / aspect
    matrix[1, 1] = focal
    matrix[2, 2] = (far + near) / (near - far)
    matrix[2, 3] = (2.0 * far * near) / (near - far)
    matrix[3, 2] = -1.0
    return matrix


def _distance_to_screen_segment(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    segment = end - start
    length_sq = float(np.dot(segment, segment))
    if length_sq <= 1e-12:
        return float(np.linalg.norm(point - start))
    t = max(0.0, min(1.0, float(np.dot(point - start, segment) / length_sq)))
    projection = start + t * segment
    return float(np.linalg.norm(point - projection))


def _encode_pick_color(identifier: int) -> tuple[float, float, float, float]:
    identifier = max(0, min(int(identifier), 0xFFFFFF))
    red = identifier & 0xFF
    green = (identifier >> 8) & 0xFF
    blue = (identifier >> 16) & 0xFF
    return red / 255.0, green / 255.0, blue / 255.0, 1.0


_VERTEX_SHADER = """
#version 120
attribute vec3 position;
attribute vec4 color;
uniform mat4 mvp;
varying vec4 v_color;

void main() {
    gl_Position = mvp * vec4(position, 1.0);
    v_color = color;
}
"""

_FRAGMENT_SHADER = """
#version 120
varying vec4 v_color;

void main() {
    gl_FragColor = v_color;
}
"""
