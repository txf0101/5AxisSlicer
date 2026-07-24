from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import ctypes
import math
import time
from typing import Callable, Iterable

import numpy as np
from PyQt5.QtCore import QPoint, Qt, QTimer
from PyQt5.QtGui import QImage
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
        GL_LINE_STRIP,
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
        glMultiDrawArrays,
        glReadPixels,
        glRenderbufferStorage,
        glTexImage2D,
        glTexParameteri,
        glUniform1f,
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
from .gcode_preview import (
    MOVE_CODES,
    ROLE_CODES,
    TIMELINE_FLAG_HAS_SPATIAL_LENGTH,
    GCodePathSegment,
    GCodePreview,
    GCodeTimelineStep,
    PreviewSettings,
)
from .models import (
    BuildSurfaceOverlay,
    CadModel,
    CoordinateFrameOverlay,
    PickHit,
    PickRequest,
    SelectionState,
)


SelectionCallback = Callable[[str, str], None]
PickCallback = Callable[[PickHit], None]

BG_COLOR = (0.965, 0.973, 0.984, 1.0)
GRID_MINOR_COLOR = (0.839, 0.871, 0.910, 0.58)
GRID_MAJOR_COLOR = (0.714, 0.761, 0.824, 0.74)
EDGE_COLOR = (0.298, 0.345, 0.416, 0.72)
EDGE_SELECTED_COLOR = (0.145, 0.388, 0.922, 1.0)
BODY_SELECTED_COLOR = (0.776, 0.816, 0.875, 0.96)
FACE_SELECTED_COLOR = (0.961, 0.620, 0.043, 0.96)
VERTEX_COLOR = (0.145, 0.388, 0.922, 0.92)
VERTEX_SELECTED_COLOR = (0.961, 0.388, 0.120, 1.0)
BUILD_SURFACE_COLOR = (0.420, 0.480, 0.580, 0.78)
AXIS_X_COLOR = (0.890, 0.180, 0.150, 1.0)
AXIS_Y_COLOR = (0.120, 0.680, 0.260, 1.0)
AXIS_Z_COLOR = (0.130, 0.360, 0.920, 1.0)
MODEL_WITH_PATH_COLOR = (0.690, 0.718, 0.765, 0.76)
CURRENT_COLOR = (0.961, 0.620, 0.043, 1.0)
PAPER_PATH_COLOR = (0.145, 0.388, 0.922, 0.94)
PAPER_TRAVEL_COLOR = (0.961, 0.620, 0.043, 0.42)
START_COLOR = (0.086, 0.639, 0.290, 1.0)
END_COLOR = (0.863, 0.149, 0.149, 1.0)
BEAD_SECTION_SIDES = 6
STATIC_SOLID_SEGMENT_LIMIT = 18_000
INTERACTIVE_LINE_SEGMENT_LIMIT = 35_000
INITIAL_SOLID_SETTLE_MS = 1200
PAPER_PATH_JOIN_TOLERANCE_MM = 0.02


@dataclass(slots=True)
class _Buffer:
    vertices: np.ndarray
    colors: np.ndarray
    primitive: int
    draw_starts: np.ndarray | None = None
    draw_counts: np.ndarray | None = None
    vbo: int = 0
    dirty: bool = True

    @property
    def count(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def nbytes(self) -> int:
        ranges = 0
        if self.draw_starts is not None:
            ranges += self.draw_starts.nbytes
        if self.draw_counts is not None:
            ranges += self.draw_counts.nbytes
        return int(self.vertices.nbytes + self.colors.nbytes + ranges)


@dataclass(slots=True)
class _EdgeSegment:
    edge_id: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class _PaperPathArrays:
    vertices: np.ndarray
    colors: np.ndarray
    draw_starts: np.ndarray
    draw_counts: np.ndarray
    segment_count: int
    first_point: tuple[float, float, float] | None
    last_point: tuple[float, float, float] | None


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
        self.pick_callback: PickCallback | None = None
        self.pick_request = PickRequest("edge", multiple=True)
        self.gcode_preview: GCodePreview | None = None
        self.quality_mode = "interactive"
        self.preview_settings = PreviewSettings(
            quality_mode=self.quality_mode,
            render_backend=self.backend,
        )
        self._model_visible = True
        self._start_end_visible = True
        self._grid_visible = True
        self._endpoint_points: tuple[
            tuple[float, float, float] | None,
            tuple[float, float, float] | None,
        ] = (None, None)
        self.visible_path_segment_count = 0
        self.drawn_path_segment_count = 0
        self.path_render_mode = "opengl_line"
        self._interaction_preview = False
        self._progress_dragging = False

        self._program = 0
        self._position_loc = -1
        self._color_loc = -1
        self._mvp_loc = -1
        self._depth_bias_loc = -1
        self._buffers: dict[str, _Buffer] = {}
        self._body_triangles: dict[str, np.ndarray] = {}
        self._face_triangles: dict[str, np.ndarray] = {}
        self._edge_segments: list[_EdgeSegment] = []
        self._vertex_positions: dict[str, tuple[float, float, float]] = {}
        self._vertex_marker_size = 0.15
        self._pick_id_to_entity: dict[int, tuple[str, str]] = {}
        self._pick_id_to_edge: dict[int, str] = {}
        self._coordinate_frames: tuple[CoordinateFrameOverlay, ...] = ()
        self._active_frame_id: str | None = None
        self._build_surface: BuildSurfaceOverlay | None = None
        self._model_transform = np.eye(4, dtype=np.float32)
        self._path_cache_key: tuple | None = None
        self._solid_stride = 1

        self._center = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self._pan = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self._radius = 80.0
        self._distance = 220.0
        self._yaw = math.radians(35.0)
        self._pitch = math.radians(55.0)
        self._view_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
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
        self._refresh_grid_buffer()

    def set_selection_callback(self, callback: SelectionCallback) -> None:
        self.selection_callback = callback

    def set_pick_callback(self, callback: PickCallback | None) -> None:
        self.pick_callback = callback

    def load_model(self, model: CadModel) -> None:
        self.model = model
        self.selection.clear()
        self._body_triangles.clear()
        self._face_triangles.clear()
        self._edge_segments.clear()
        self._vertex_positions.clear()
        self._model_transform = np.eye(4, dtype=np.float32)

        for body in model.bodies:
            shape = model.shapes.get(body.body_id)
            if shape is None:
                continue
            polydata = shape_to_polydata(shape)
            body.triangle_count = polydata.GetNumberOfPolys()
            self._body_triangles[body.body_id] = _points_array(
                _polydata_triangles(polydata)
            )

            for face_id in body.face_ids:
                face_shape = model.face_shapes.get(face_id)
                if face_shape is None:
                    continue
                face_polydata = shape_to_polydata(face_shape)
                self._face_triangles[face_id] = _points_array(
                    _polydata_triangles(face_polydata)
                )

            for edge_id in body.edge_ids:
                edge_shape = model.edge_shapes.get(edge_id)
                if edge_shape is None:
                    continue
                edge_polydata = edge_to_polydata(edge_shape, segments=28)
                self._edge_segments.extend(
                    _EdgeSegment(edge_id, start, end)
                    for start, end in _polydata_lines(edge_polydata)
                )

            for vertex_id in body.vertex_ids:
                vertex = model.vertex_map.get(vertex_id)
                if vertex is not None:
                    self._vertex_positions[vertex_id] = vertex.point

        diagonal = model.bounds.diagonal if model.bounds is not None else 10.0
        self._vertex_marker_size = max(float(diagonal) * 0.006, 0.15)
        self._coordinate_frames = ()
        self._active_frame_id = None
        self._build_surface = None
        self._set_buffer("coordinate_frames", [], [], GL_LINES)
        self._set_buffer("coordinate_frames_active", [], [], GL_LINES)
        self._set_buffer("build_surface", [], [], GL_LINES)
        self.pick_request = PickRequest("edge", multiple=True)
        self.selection.mode = "edge"
        self.refresh_selection()
        self._refresh_pick_buffers()
        self._path_cache_key = None
        if self.gcode_preview is not None:
            self.refresh_path_preview()
        self._refresh_grid_buffer()
        self.fit_view()

    def load_gcode_preview(self, preview: GCodePreview) -> None:
        self.gcode_preview = preview
        self.preview_settings = PreviewSettings(
            layer_min=preview.layer_min,
            layer_max=preview.layer_max,
            show_travel=False,
            show_extrusion=True,
            show_pose_samples=False,
            solid_rendering=self.quality_mode == "interactive",
            quality_mode=self.quality_mode,
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
        self._refresh_grid_buffer()
        self.fit_view()

    def clear_gcode_preview(self) -> None:
        self.gcode_preview = None
        self.preview_settings = PreviewSettings(render_backend=self.backend)
        self.visible_path_segment_count = 0
        self.drawn_path_segment_count = 0
        self.path_render_mode = "line"
        self._path_cache_key = None
        self._settle_timer.stop()
        self._interaction_preview = False
        self._progress_dragging = False
        for key in (
            "path_line",
            "path_solid",
            "path_paper",
            "current",
            "pose",
            "start",
            "end",
        ):
            self._set_buffer(key, [], [], GL_LINES)
        self._endpoint_points = (None, None)
        self.refresh_selection()
        self._refresh_grid_buffer()
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

    def set_preview_progress(
        self, progress_index: int, interactive: bool | None = None
    ) -> None:
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

    def set_quality_mode(self, mode: str) -> None:
        mode = str(mode).lower()
        if mode not in {"interactive", "paper"}:
            raise ValueError(f"Unknown quality mode: {mode}")
        expected_solid = mode == "interactive"
        if (
            mode == self.quality_mode
            and self.preview_settings.quality_mode == mode
            and self.preview_settings.solid_rendering == expected_solid
            and not self._interaction_preview
            and not self._progress_dragging
        ):
            return
        self._settle_timer.stop()
        self._interaction_preview = False
        self._progress_dragging = False
        self.quality_mode = mode
        self.preview_settings.quality_mode = mode
        self.preview_settings.solid_rendering = expected_solid
        self._path_cache_key = None
        if self.gcode_preview is not None:
            self.refresh_path_preview()
        else:
            self.update()

    def set_standard_view(self, view: str) -> None:
        view = str(view).lower()
        if view in {"home", "isometric", "iso"}:
            self.home_view()
            return
        views = {
            "front": (0.0, -90.0, (0.0, 0.0, 1.0)),
            "back": (0.0, 90.0, (0.0, 0.0, 1.0)),
            "left": (-90.0, 0.0, (0.0, 0.0, 1.0)),
            "right": (90.0, 0.0, (0.0, 0.0, 1.0)),
            "top": (0.0, 0.0, (0.0, 1.0, 0.0)),
            "bottom": (180.0, 0.0, (0.0, 1.0, 0.0)),
        }
        if view not in views:
            raise ValueError(f"Unknown standard view: {view}")
        yaw, pitch, up = views[view]
        self._yaw = math.radians(yaw)
        self._pitch = math.radians(pitch)
        self._view_up = np.asarray(up, dtype=np.float32)
        self.fit_view()

    def camera_state(self) -> dict[str, object]:
        eye, target, view_up = self._camera_vectors()
        return {
            "position": eye.astype(float).tolist(),
            "focal_point": target.astype(float).tolist(),
            "view_up": view_up.astype(float).tolist(),
            "distance": float(self._distance),
            "yaw_degrees": float(math.degrees(self._yaw)),
            "pitch_degrees": float(math.degrees(self._pitch)),
            "parallel_scale": float(self._radius),
            "view_angle": 45.0,
        }

    def capabilities(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "quality_mode": self.quality_mode,
            "paper_quality_active": (
                self.quality_mode == "paper"
                and not self._interaction_preview
                and not self._progress_dragging
            ),
            "quality_modes": ["interactive", "paper"],
            "offscreen_export": True,
            "full_timeline_paper_path": True,
            "standard_views": [
                "isometric",
                "front",
                "back",
                "left",
                "right",
                "top",
                "bottom",
            ],
            "result_visibility": ["model", "start_end", "grid"],
            "selection_kinds": ["body", "face", "edge", "vertex"],
            "pick_hit_position": "source",
            "coordinate_frame_overlays": True,
            "build_surface_overlay": True,
            "rigid_model_transform": True,
        }

    def clear_model(self) -> None:
        self.model = None
        self.selection.clear()
        self._body_triangles.clear()
        self._face_triangles.clear()
        self._edge_segments.clear()
        self._vertex_positions.clear()
        self._pick_id_to_entity.clear()
        self._pick_id_to_edge.clear()
        self._model_transform = np.eye(4, dtype=np.float32)
        self._coordinate_frames = ()
        self._active_frame_id = None
        self._build_surface = None
        for key in ("model", "face_selected", "body_pick", "face_pick"):
            self._set_buffer(key, [], [], GL_TRIANGLES)
        for key in (
            "edge",
            "edge_selected",
            "edge_pick",
            "vertex",
            "vertex_selected",
            "vertex_pick",
            "coordinate_frames",
            "coordinate_frames_active",
            "build_surface",
        ):
            self._set_buffer(key, [], [], GL_LINES)
        self._refresh_grid_buffer()
        self.update()

    def set_model_visible(self, visible: bool) -> None:
        self._model_visible = bool(visible)
        self.update()

    def set_start_end_visible(self, visible: bool) -> None:
        self._start_end_visible = bool(visible)
        self.update()

    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = bool(visible)
        self.update()

    def set_result_visibility(
        self,
        *,
        model: bool | None = None,
        start_end: bool | None = None,
        grid: bool | None = None,
    ) -> None:
        if model is not None:
            self._model_visible = bool(model)
        if start_end is not None:
            self._start_end_visible = bool(start_end)
        if grid is not None:
            self._grid_visible = bool(grid)
        self.update()

    def preview_state(self) -> dict:
        perf = self.performance_state()
        return {
            "summary": (
                None if self.gcode_preview is None else self.gcode_preview.summary()
            ),
            "settings": self.preview_settings.to_json(),
            "visible_path_segment_count": self.visible_path_segment_count,
            "drawn_path_segment_count": self.drawn_path_segment_count,
            "render_mode": self.path_render_mode,
            "progress": self.progress_state(),
            "backend": self.backend,
            "quality_mode": self.preview_settings.quality_mode,
            "frame_ms": perf["frame_ms_avg"],
            "gpu_draw_count": perf["gpu_draw_count"],
            "cache_format": (
                None
                if self.gcode_preview is None
                else self.gcode_preview.summary().get("cache_format")
            ),
            "result_visibility": {
                "model": self._model_visible,
                "start_end": self._start_end_visible,
                "grid": self._grid_visible,
            },
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
                index = self.gcode_preview.nearest_segment_index_for_step(
                    current.step_index
                )
            if index is not None and 0 <= index < len(self.gcode_preview.segments):
                return self.gcode_preview.segments[index]
        for segment in self.gcode_preview.segments:
            if self._segment_visible(segment) and segment.has_spatial_length:
                return segment
        return None

    def set_mode(self, mode: str) -> None:
        if mode not in {"body", "face", "edge", "vertex"}:
            raise ValueError(f"Unsupported picking mode: {mode}")
        self.selection.mode = mode
        self.pick_request = PickRequest(mode, multiple=mode in {"body", "edge"})
        self.refresh_selection()

    def set_pick_request(self, request: PickRequest) -> None:
        self.set_mode(request.kind)
        self.pick_request = request

    def set_selection(
        self,
        body_ids: list[str] | None = None,
        edge_ids: list[str] | None = None,
        face_ids: list[str] | None = None,
        vertex_ids: list[str] | None = None,
    ) -> None:
        if body_ids is not None:
            self.selection.body_ids = set(body_ids)
        if face_ids is not None:
            self.selection.face_ids = set(face_ids)
        if edge_ids is not None:
            self.selection.edge_ids = set(edge_ids)
        if vertex_ids is not None:
            self.selection.vertex_ids = set(vertex_ids)
        self.refresh_selection()

    def clear_selection(self) -> None:
        self.selection.clear()
        self.refresh_selection()

    def refresh_selection(self) -> None:
        self._refresh_body_buffer()
        self._refresh_face_buffer()
        self._refresh_edge_buffers()
        self._refresh_vertex_buffers()
        self.update()

    def set_coordinate_frames(
        self,
        frames: Iterable[CoordinateFrameOverlay],
        active_frame_id: str | None = None,
    ) -> None:
        values = tuple(frames)
        for frame in values:
            _validate_coordinate_frame(frame)
        self._coordinate_frames = values
        self._active_frame_id = active_frame_id
        normal_vertices: list[tuple[float, float, float]] = []
        normal_colors: list[tuple[float, float, float, float]] = []
        active_vertices: list[tuple[float, float, float]] = []
        active_colors: list[tuple[float, float, float, float]] = []
        for frame in values:
            if not frame.visible:
                continue
            target_vertices = (
                active_vertices
                if frame.frame_id == active_frame_id
                else normal_vertices
            )
            target_colors = (
                active_colors if frame.frame_id == active_frame_id else normal_colors
            )
            scale = float(frame.scale) * (
                1.18 if frame.frame_id == active_frame_id else 1.0
            )
            vertices, colors = _coordinate_frame_lines(frame, scale)
            target_vertices.extend(vertices)
            target_colors.extend(colors)
        self._set_buffer("coordinate_frames", normal_vertices, normal_colors, GL_LINES)
        self._set_buffer(
            "coordinate_frames_active", active_vertices, active_colors, GL_LINES
        )
        self._refresh_grid_buffer()
        self.update()

    def set_build_surface(self, surface: BuildSurfaceOverlay | None) -> None:
        if surface is None:
            self._build_surface = None
            self._set_buffer("build_surface", [], [], GL_LINES)
            self._refresh_grid_buffer()
            self.update()
            return
        vertices = _build_surface_lines(surface)
        self._build_surface = surface
        self._set_buffer(
            "build_surface",
            vertices,
            [BUILD_SURFACE_COLOR] * len(vertices),
            GL_LINES,
        )
        self._refresh_grid_buffer()
        self.update()

    def set_model_transform(self, matrix: Iterable[Iterable[float]]) -> None:
        self._model_transform = _validated_rigid_transform(matrix).astype(np.float32)
        self._refresh_grid_buffer()
        self.update()

    def fit_view(self) -> None:
        bounds = self._scene_bounds()
        if bounds is not None:
            low, high = bounds
            self._center = (low + high) * 0.5
            diag = float(np.linalg.norm(high - low))
            self._radius = max(diag * 0.5, 1.0)
            self._distance = max(self._radius * 1.78, 20.0)
            self._pan = np.array([0.0, 0.0, 0.0], dtype=np.float32)
        self._refresh_endpoint_buffers(*self._endpoint_points)
        self.update()

    def home_view(self) -> None:
        self._yaw = math.radians(35.0)
        self._pitch = math.radians(55.0)
        self._view_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        self.fit_view()

    def camera_command(self, command: str, value: float = 10.0) -> None:
        if command == "fit":
            self.fit_view()
            return
        if command == "home":
            self.home_view()
            return
        if command == "azimuth":
            self._view_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            self._yaw += math.radians(value)
        elif command == "elevation":
            self._view_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            self._pitch = max(
                math.radians(-85.0),
                min(math.radians(85.0), self._pitch + math.radians(value)),
            )
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
        paper = self.quality_mode == "paper" and not interactive
        solid = self.preview_settings.solid_rendering and not interactive and not paper
        mode_key = "paper" if paper else ("solid" if solid else "line")
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
            if paper:
                self._rebuild_paper_path_buffer(current_global_step)
            else:
                self._rebuild_path_buffers(solid, current_global_step)
            self._path_cache_key = cache_key
        self._refresh_current_buffer()
        self.update()

    def render(self) -> None:
        self.update()

    def render_scene_image(self, width: int, height: int) -> QImage:
        width = max(1, int(width))
        height = max(1, int(height))
        framebuffer = texture = depth = 0
        previous_framebuffer = 0
        context_ready = False
        try:
            self.makeCurrent()
            context = self.context()
            if context is None or not context.isValid():
                raise RuntimeError("OpenGL viewer has no valid context")
            context_ready = True
            if self._program == 0:
                raise RuntimeError("OpenGL viewer is not initialized")
            previous_framebuffer = int(glGetIntegerv(GL_FRAMEBUFFER_BINDING))
            framebuffer = int(glGenFramebuffers(1))
            texture = int(glGenTextures(1))
            depth = int(glGenRenderbuffers(1))

            glBindTexture(GL_TEXTURE_2D, texture)
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA,
                width,
                height,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                None,
            )
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glBindRenderbuffer(GL_RENDERBUFFER, depth)
            glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, width, height)
            glBindFramebuffer(GL_FRAMEBUFFER, framebuffer)
            glFramebufferTexture2D(
                GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0
            )
            glFramebufferRenderbuffer(
                GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depth
            )
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("Unable to create the OpenGL export framebuffer")

            glViewport(0, 0, width, height)
            self._paint_scene(width, height, record_metrics=False)
            payload = glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE)
            pixels = np.frombuffer(payload, dtype=np.uint8).reshape((height, width, 4))
            pixels = np.ascontiguousarray(np.flipud(pixels))
            return QImage(
                pixels.data,
                width,
                height,
                width * 4,
                QImage.Format_RGBA8888,
            ).copy()
        finally:
            if context_ready:
                glBindFramebuffer(GL_FRAMEBUFFER, previous_framebuffer)
                glViewport(0, 0, max(1, int(self.width())), max(1, int(self.height())))
                glClearColor(*BG_COLOR)
                if depth:
                    glDeleteRenderbuffers(1, [depth])
                if texture:
                    glDeleteTextures(1, [texture])
                if framebuffer:
                    glDeleteFramebuffers(1, [framebuffer])
                self.doneCurrent()

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
        self._depth_bias_loc = glGetUniformLocation(self._program, "depth_bias")
        for buffer in self._buffers.values():
            buffer.dirty = True

    def resizeGL(self, width: int, height: int) -> None:  # noqa: N802 - Qt API
        glViewport(0, 0, max(1, width), max(1, height))

    def paintGL(self) -> None:  # noqa: N802 - Qt API
        self._paint_scene(
            max(1, self.width()), max(1, self.height()), record_metrics=True
        )

    def _paint_scene(self, width: int, height: int, *, record_metrics: bool) -> None:
        started = time.perf_counter()
        glClearColor(*BG_COLOR)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self._program == 0:
            return
        glUseProgram(self._program)
        scene_mvp = self._projection_matrix(width, height) @ self._view_matrix()
        model_mvp = scene_mvp @ self._model_transform
        self._set_shader_mvp(scene_mvp)
        line_scale = max(
            0.5,
            min(
                4.0,
                min(
                    width / max(1, self.width()),
                    height / max(1, self.height()),
                ),
            ),
        )

        draw_count = 0
        if self._grid_visible:
            draw_count += self._draw_buffer("grid", line_width=1.0 * line_scale)
        draw_count += self._draw_buffer(
            "build_surface", line_width=2.0 * line_scale, depth_bias=0.0002
        )
        if self._model_visible:
            self._set_shader_mvp(model_mvp)
            draw_count += self._draw_buffer("model", line_width=1.0)
            draw_count += self._draw_buffer(
                "face_selected", line_width=1.0, depth_bias=0.0002
            )
            draw_count += self._draw_buffer(
                "edge", line_width=2.2 * line_scale, depth_bias=0.0004
            )
            draw_count += self._draw_buffer(
                "edge_selected",
                line_width=5.0 * line_scale,
                depth_bias=0.0007,
            )
            if self.selection.mode == "vertex":
                draw_count += self._draw_buffer(
                    "vertex", line_width=3.0 * line_scale, depth_bias=0.0008
                )
                draw_count += self._draw_buffer(
                    "vertex_selected",
                    line_width=5.0 * line_scale,
                    depth_bias=0.0010,
                )
            self._set_shader_mvp(scene_mvp)
        if self.path_render_mode == "opengl_paper_full_timeline":
            draw_count += self._draw_buffer(
                "path_paper",
                line_width=0.70 * line_scale,
                depth_bias=0.0010,
            )
        elif self.path_render_mode.startswith("opengl_solid"):
            draw_count += self._draw_buffer(
                "path_solid", line_width=1.0, depth_bias=0.0004
            )
        else:
            draw_count += self._draw_buffer(
                "path_line",
                line_width=2.4 * line_scale,
                depth_bias=0.0004,
            )
        draw_count += self._draw_buffer(
            "pose", line_width=1.3 * line_scale, depth_bias=0.0008
        )
        draw_count += self._draw_buffer(
            "current", line_width=4.5 * line_scale, depth_bias=0.0010
        )
        if self._start_end_visible:
            draw_count += self._draw_buffer(
                "start", line_width=3.2 * line_scale, depth_bias=0.0012
            )
            draw_count += self._draw_buffer(
                "end", line_width=3.2 * line_scale, depth_bias=0.0012
            )
        draw_count += self._draw_buffer(
            "coordinate_frames", line_width=2.4 * line_scale, depth_bias=0.0014
        )
        draw_count += self._draw_buffer(
            "coordinate_frames_active",
            line_width=4.2 * line_scale,
            depth_bias=0.0016,
        )
        glUseProgram(0)

        if record_metrics:
            self._last_gpu_draw_count = draw_count
            self._last_memory_bytes = sum(
                buffer.nbytes for buffer in self._buffers.values()
            )
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
            self._view_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            self._yaw += delta.x() * 0.01
            self._pitch = max(
                math.radians(-85.0),
                min(math.radians(85.0), self._pitch + delta.y() * 0.01),
            )
            self.update()
        elif event.buttons() & Qt.RightButton:
            self._pan[0] += delta.x() * self._radius / max(self.width(), 1)
            self._pan[1] -= delta.y() * self._radius / max(self.height(), 1)
            self.update()
        self._last_mouse = event.pos()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.LeftButton and not self._mouse_moved:
            hit = self._pick(event.pos())
            if hit is not None:
                self._apply_pick(hit)
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
        self.preview_settings.progress_index = (
            0
            if count == 0
            else max(0, min(self.preview_settings.progress_index, count - 1))
        )

    def _segment_visible(self, segment: GCodePathSegment) -> bool:
        settings = self.preview_settings
        if segment.layer < settings.layer_min or segment.layer > settings.layer_max:
            return False
        if segment.move_type == "extrude":
            return (
                settings.show_extrusion
                and segment.extrusion_role in settings.visible_roles
            )
        if segment.move_type == "travel":
            return settings.show_travel
        return settings.show_travel and segment.has_spatial_length

    def _rebuild_path_buffers(
        self, solid: bool, current_global_step: int | None
    ) -> None:
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
        self._set_buffer("path_paper", [], [], GL_LINE_STRIP)
        if solid:
            stride = _render_stride(len(visible), STATIC_SOLID_SEGMENT_LIMIT)
            self._solid_stride = stride
            self.path_render_mode = (
                "opengl_solid" if stride == 1 else f"opengl_solid_adaptive_{stride}"
            )
            vertices, colors, drawn = _build_bead_arrays(
                visible,
                stride,
                controller_semantics=self.gcode_preview.controller_semantics,
            )
            self._set_buffer("path_solid", vertices, colors, GL_TRIANGLES)
            self._set_buffer("path_line", [], [], GL_LINES)
            self.drawn_path_segment_count = drawn
        else:
            stride = _render_stride(len(visible), INTERACTIVE_LINE_SEGMENT_LIMIT)
            self.path_render_mode = (
                "opengl_line_interactive"
                if self._interaction_preview or self._progress_dragging
                else "opengl_line"
            )
            vertices, colors, drawn = _build_line_arrays(visible, stride)
            self._set_buffer("path_line", vertices, colors, GL_LINES)
            self._set_buffer("path_solid", [], [], GL_TRIANGLES)
            self.drawn_path_segment_count = drawn
        self._refresh_pose_buffer(visible)
        first = visible[0].start if visible else None
        last = visible[-1].end if visible else None
        self._refresh_endpoint_buffers(first, last)

    def _rebuild_paper_path_buffer(self, current_global_step: int | None) -> None:
        if self.gcode_preview is None:
            return
        arrays = _build_paper_path_arrays(
            self.gcode_preview,
            self.preview_settings,
            current_global_step,
            tolerance=PAPER_PATH_JOIN_TOLERANCE_MM,
        )
        self.visible_path_segment_count = arrays.segment_count
        self.drawn_path_segment_count = arrays.segment_count
        self.path_render_mode = "opengl_paper_full_timeline"
        self._set_buffer(
            "path_paper",
            arrays.vertices,
            arrays.colors,
            GL_LINE_STRIP,
            draw_starts=arrays.draw_starts,
            draw_counts=arrays.draw_counts,
        )
        self._set_buffer("path_line", [], [], GL_LINES)
        self._set_buffer("path_solid", [], [], GL_TRIANGLES)
        self._set_buffer("pose", [], [], GL_LINES)
        self._refresh_endpoint_buffers(arrays.first_point, arrays.last_point)

    def _refresh_current_buffer(self) -> None:
        if self.quality_mode == "paper" and not (
            self._interaction_preview or self._progress_dragging
        ):
            self._set_buffer("current", [], [], GL_LINES)
            return
        segment = self.representative_path_segment()
        if segment is None or not segment.has_spatial_length:
            self._set_buffer("current", [], [], GL_LINES)
            return
        self._set_buffer(
            "current",
            [segment.start, segment.end],
            [CURRENT_COLOR, CURRENT_COLOR],
            GL_LINES,
        )

    def _refresh_endpoint_buffers(
        self,
        first: tuple[float, float, float] | None,
        last: tuple[float, float, float] | None,
    ) -> None:
        self._endpoint_points = (first, last)
        radius = max(0.8, min(3.2, self._radius * 0.025))
        self._set_marker_buffer("start", first, radius, START_COLOR)
        self._set_marker_buffer("end", last, radius, END_COLOR)

    def _set_marker_buffer(
        self,
        key: str,
        point: tuple[float, float, float] | None,
        radius: float,
        color: tuple[float, float, float, float],
    ) -> None:
        if point is None:
            self._set_buffer(key, [], [], GL_LINES)
            return
        x, y, z = point
        vertices = [
            (x - radius, y, z),
            (x + radius, y, z),
            (x, y - radius, z),
            (x, y + radius, z),
            (x, y, z - radius),
            (x, y, z + radius),
        ]
        self._set_buffer(key, vertices, [color] * len(vertices), GL_LINES)

    def _refresh_pose_buffer(self, visible_segments: list[GCodePathSegment]) -> None:
        if not self.preview_settings.show_pose_samples:
            self._set_buffer("pose", [], [], GL_LINES)
            return
        candidates = [
            segment
            for segment in visible_segments
            if segment.move_type == "extrude"
            and (segment.rotary_end or segment.rotary_start)
        ]
        if not candidates:
            self._set_buffer("pose", [], [], GL_LINES)
            return
        from .viewer import _preview_pose_for_segment

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
            start, axis = _preview_pose_for_segment(
                segment,
                controller_semantics=(
                    self.gcode_preview.controller_semantics
                    if self.gcode_preview is not None
                    else None
                ),
            )
            end = tuple(start[index] + axis[index] * length for index in range(3))
            vertices.extend([start, end])
            colors.extend([color, color])
        self._set_buffer("pose", vertices, colors, GL_LINES)

    def _refresh_grid_buffer(self) -> None:
        bounds = self._scene_bounds()
        if bounds is None:
            low = np.array([-50.0, -50.0, 0.0], dtype=np.float32)
            high = np.array([50.0, 50.0, 0.0], dtype=np.float32)
        else:
            low, high = bounds
        span = max(float(high[0] - low[0]), float(high[1] - low[1]), 20.0)
        step = _nice_grid_step(span / 12.0)
        x_min = math.floor((float(low[0]) - step) / step) * step
        x_max = math.ceil((float(high[0]) + step) / step) * step
        y_min = math.floor((float(low[1]) - step) / step) * step
        y_max = math.ceil((float(high[1]) + step) / step) * step
        z = float(low[2]) - max(0.02, span * 0.002)
        vertices: list[tuple[float, float, float]] = []
        colors: list[tuple[float, float, float, float]] = []

        x_values = _inclusive_grid_values(x_min, x_max, step)
        y_values = _inclusive_grid_values(y_min, y_max, step)
        for x in x_values:
            color = (
                GRID_MAJOR_COLOR if int(round(x / step)) % 5 == 0 else GRID_MINOR_COLOR
            )
            vertices.extend([(x, y_min, z), (x, y_max, z)])
            colors.extend([color, color])
        for y in y_values:
            color = (
                GRID_MAJOR_COLOR if int(round(y / step)) % 5 == 0 else GRID_MINOR_COLOR
            )
            vertices.extend([(x_min, y, z), (x_max, y, z)])
            colors.extend([color, color])
        self._set_buffer("grid", vertices, colors, GL_LINES)

    def _refresh_body_buffer(self) -> None:
        vertices: list[tuple[float, float, float]] = []
        colors: list[tuple[float, float, float, float]] = []
        if self.model is not None:
            for body in self.model.bodies:
                triangles = self._body_triangles.get(body.body_id)
                if triangles is None or not len(triangles):
                    continue
                if body.body_id in self.selection.body_ids:
                    color = BODY_SELECTED_COLOR
                elif self.gcode_preview is not None:
                    color = MODEL_WITH_PATH_COLOR
                else:
                    color = (*body.color, 0.92)
                vertices.extend(map(tuple, triangles))
                colors.extend([color] * len(triangles))
        self._set_buffer("model", vertices, colors, GL_TRIANGLES)

    def _refresh_face_buffer(self) -> None:
        vertices: list[tuple[float, float, float]] = []
        colors: list[tuple[float, float, float, float]] = []
        for face_id in self.selection.face_ids:
            triangles = self._face_triangles.get(face_id)
            if triangles is None or not len(triangles):
                continue
            vertices.extend(map(tuple, triangles))
            colors.extend([FACE_SELECTED_COLOR] * len(triangles))
        self._set_buffer("face_selected", vertices, colors, GL_TRIANGLES)

    def _refresh_edge_buffers(self) -> None:
        edge_vertices: list[tuple[float, float, float]] = []
        edge_colors: list[tuple[float, float, float, float]] = []
        selected_vertices: list[tuple[float, float, float]] = []
        selected_colors: list[tuple[float, float, float, float]] = []
        for segment in self._edge_segments:
            target_vertices = (
                selected_vertices
                if segment.edge_id in self.selection.edge_ids
                else edge_vertices
            )
            target_colors = (
                selected_colors
                if segment.edge_id in self.selection.edge_ids
                else edge_colors
            )
            color = (
                EDGE_SELECTED_COLOR
                if segment.edge_id in self.selection.edge_ids
                else EDGE_COLOR
            )
            target_vertices.extend([segment.start, segment.end])
            target_colors.extend([color, color])
        self._set_buffer("edge", edge_vertices, edge_colors, GL_LINES)
        self._set_buffer("edge_selected", selected_vertices, selected_colors, GL_LINES)

    def _refresh_vertex_buffers(self) -> None:
        vertices: list[tuple[float, float, float]] = []
        colors: list[tuple[float, float, float, float]] = []
        selected_vertices: list[tuple[float, float, float]] = []
        selected_colors: list[tuple[float, float, float, float]] = []
        for vertex_id, point in self._vertex_positions.items():
            marker = _vertex_marker_lines(point, self._vertex_marker_size)
            if vertex_id in self.selection.vertex_ids:
                selected_vertices.extend(marker)
                selected_colors.extend([VERTEX_SELECTED_COLOR] * len(marker))
            else:
                vertices.extend(marker)
                colors.extend([VERTEX_COLOR] * len(marker))
        self._set_buffer("vertex", vertices, colors, GL_LINES)
        self._set_buffer(
            "vertex_selected", selected_vertices, selected_colors, GL_LINES
        )

    def _refresh_pick_buffers(self) -> None:
        self._pick_id_to_entity.clear()
        self._pick_id_to_edge.clear()

        def register(kind: str, entity_id: str) -> tuple[float, float, float, float]:
            pick_id = len(self._pick_id_to_entity) + 1
            if pick_id > 0xFFFFFF:
                raise ValueError("OpenGL pick identity capacity exceeded")
            self._pick_id_to_entity[pick_id] = (kind, entity_id)
            if kind == "edge":
                self._pick_id_to_edge[pick_id] = entity_id
            return _encode_pick_color(pick_id)

        body_vertices: list[tuple[float, float, float]] = []
        body_colors: list[tuple[float, float, float, float]] = []
        if self.model is not None:
            for body in self.model.bodies:
                triangles = self._body_triangles.get(body.body_id)
                if triangles is None or not len(triangles):
                    continue
                color = register("body", body.body_id)
                body_vertices.extend(map(tuple, triangles))
                body_colors.extend([color] * len(triangles))
        self._set_buffer("body_pick", body_vertices, body_colors, GL_TRIANGLES)

        face_vertices: list[tuple[float, float, float]] = []
        face_colors: list[tuple[float, float, float, float]] = []
        if self.model is not None:
            for face in self.model.faces:
                triangles = self._face_triangles.get(face.face_id)
                if triangles is None or not len(triangles):
                    continue
                color = register("face", face.face_id)
                face_vertices.extend(map(tuple, triangles))
                face_colors.extend([color] * len(triangles))
        self._set_buffer("face_pick", face_vertices, face_colors, GL_TRIANGLES)

        edge_vertices: list[tuple[float, float, float]] = []
        edge_colors: list[tuple[float, float, float, float]] = []
        edge_colors_by_id: dict[str, tuple[float, float, float, float]] = {}
        for segment in self._edge_segments:
            color = edge_colors_by_id.get(segment.edge_id)
            if color is None:
                color = register("edge", segment.edge_id)
                edge_colors_by_id[segment.edge_id] = color
            edge_vertices.extend([segment.start, segment.end])
            edge_colors.extend([color, color])
        self._set_buffer("edge_pick", edge_vertices, edge_colors, GL_LINES)

        vertex_vertices: list[tuple[float, float, float]] = []
        vertex_colors: list[tuple[float, float, float, float]] = []
        for vertex_id, point in self._vertex_positions.items():
            marker = _vertex_marker_lines(point, self._vertex_marker_size)
            color = register("vertex", vertex_id)
            vertex_vertices.extend(marker)
            vertex_colors.extend([color] * len(marker))
        self._set_buffer("vertex_pick", vertex_vertices, vertex_colors, GL_LINES)

    def _apply_pick(self, hit: PickHit) -> None:
        request = self.pick_request
        if hit.kind != request.kind or not self._entity_allowed(hit.entity_id):
            return
        selected: set[str] = getattr(self.selection, f"{hit.kind}_ids")
        if request.multiple:
            if hit.entity_id in selected:
                selected.remove(hit.entity_id)
            else:
                selected.add(hit.entity_id)
        else:
            selected.clear()
            selected.add(hit.entity_id)
        self.refresh_selection()
        if self.selection_callback is not None:
            self.selection_callback(hit.kind, hit.entity_id)
        if self.pick_callback is not None:
            self.pick_callback(hit)

    def _toggle_edge(self, edge_id: str) -> None:
        if edge_id in self.selection.edge_ids:
            self.selection.edge_ids.remove(edge_id)
        else:
            self.selection.edge_ids.add(edge_id)
        self.refresh_selection()
        if self.selection_callback is not None:
            self.selection_callback("edge", edge_id)

    def _entity_allowed(self, entity_id: str) -> bool:
        allowed = self.pick_request.allowed_ids
        return allowed is None or entity_id in allowed

    def _pick(self, pos: QPoint) -> PickHit | None:
        if self.model is None or not self._model_visible:
            return None
        kind = self.pick_request.kind
        entity = self._pick_entity_by_color_id(pos, kind)
        if entity is not None:
            if entity[0] == kind and self._entity_allowed(entity[1]):
                return PickHit(
                    kind, entity[1], self._hit_position_source(kind, entity[1], pos)
                )
            return None
        return self._pick_by_projection(pos, kind)

    def _pick_edge(self, pos: QPoint) -> str | None:
        picked = self._pick_edge_by_color_id(pos)
        if picked is not None:
            return picked
        return self._pick_edge_by_projection(pos)

    def _pick_edge_by_projection(self, pos: QPoint) -> str | None:
        hit = self._pick_edge_projection_hit(pos)
        return None if hit is None else hit.entity_id

    def _pick_edge_by_color_id(self, pos: QPoint) -> str | None:
        entity = self._pick_entity_by_color_id(pos, "edge")
        if entity is None or entity[0] != "edge":
            return None
        return entity[1]

    def _pick_entity_by_color_id(
        self, pos: QPoint, kind: str
    ) -> tuple[str, str] | None:
        buffer_key = f"{kind}_pick"
        buffer = self._buffers.get(buffer_key)
        if (
            self._program == 0
            or buffer is None
            or buffer.count == 0
            or self.width() <= 0
            or self.height() <= 0
        ):
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
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA,
                width,
                height,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                None,
            )
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

            glBindRenderbuffer(GL_RENDERBUFFER, depth)
            glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, width, height)

            glBindFramebuffer(GL_FRAMEBUFFER, framebuffer)
            glFramebufferTexture2D(
                GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0
            )
            glFramebufferRenderbuffer(
                GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depth
            )
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                return None

            glViewport(0, 0, width, height)
            glDisable(GL_BLEND)
            glClearColor(0.0, 0.0, 0.0, 0.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glUseProgram(self._program)
            mvp = (
                self._projection_matrix() @ self._view_matrix() @ self._model_transform
            )
            self._set_shader_mvp(mvp)
            if kind in {"edge", "vertex"}:
                self._draw_buffer("body_pick", line_width=1.0)
            line_width = 11.0 if kind == "vertex" else 9.0
            self._draw_buffer(buffer_key, line_width=line_width, depth_bias=0.0008)
            read_y = max(0, min(height - 1, height - int(pos.y()) - 1))
            read_x = max(0, min(width - 1, int(pos.x())))
            pixel = glReadPixels(read_x, read_y, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE)
            values = np.frombuffer(pixel, dtype=np.uint8)
            if values.size < 3:
                return None
            pick_id = int(values[0]) | (int(values[1]) << 8) | (int(values[2]) << 16)
            return self._pick_id_to_entity.get(pick_id)
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

    def _pick_by_projection(self, pos: QPoint, kind: str) -> PickHit | None:
        if kind == "edge":
            return self._pick_edge_projection_hit(pos)
        if kind == "vertex":
            return self._pick_vertex_projection_hit(pos)
        if kind in {"body", "face"}:
            return self._pick_triangle_hit(pos, kind)
        return None

    def _pick_edge_projection_hit(
        self,
        pos: QPoint,
        entity_id: str | None = None,
    ) -> PickHit | None:
        if not self._edge_segments:
            return None
        mvp = self._projection_matrix() @ self._view_matrix() @ self._model_transform
        point = np.array([float(pos.x()), float(pos.y())], dtype=np.float64)
        best: tuple[float, str, tuple[float, float, float]] | None = None
        for segment in self._edge_segments:
            if entity_id is not None and segment.edge_id != entity_id:
                continue
            if entity_id is None and not self._entity_allowed(segment.edge_id):
                continue
            left = self._project(segment.start, mvp)
            right = self._project(segment.end, mvp)
            if left is None or right is None:
                continue
            distance, fraction = _screen_segment_distance_and_fraction(
                point, left, right
            )
            position = tuple(
                float(
                    segment.start[index]
                    + fraction * (segment.end[index] - segment.start[index])
                )
                for index in range(3)
            )
            if best is None or distance < best[0]:
                best = (distance, segment.edge_id, position)
        if best is not None and best[0] <= 8.0:
            return PickHit("edge", best[1], best[2])
        return None

    def _pick_vertex_projection_hit(self, pos: QPoint) -> PickHit | None:
        if not self._vertex_positions:
            return None
        mvp = self._projection_matrix() @ self._view_matrix() @ self._model_transform
        point = np.array([float(pos.x()), float(pos.y())], dtype=np.float64)
        best: tuple[float, str, tuple[float, float, float]] | None = None
        for vertex_id, position in self._vertex_positions.items():
            if not self._entity_allowed(vertex_id):
                continue
            projected = self._project(position, mvp)
            if projected is None:
                continue
            distance = float(np.linalg.norm(point - projected))
            if best is None or distance < best[0]:
                best = (distance, vertex_id, position)
        if best is not None and best[0] <= 10.0:
            return PickHit("vertex", best[1], best[2])
        return None

    def _pick_triangle_hit(
        self,
        pos: QPoint,
        kind: str,
        entity_id: str | None = None,
    ) -> PickHit | None:
        geometry = self._body_triangles if kind == "body" else self._face_triangles
        if not geometry:
            return None
        ray = self._screen_ray_source(pos)
        if ray is None:
            return None
        origin, direction = ray
        best: tuple[float, str, tuple[float, float, float]] | None = None
        for candidate_id, vertices in geometry.items():
            if entity_id is not None and candidate_id != entity_id:
                continue
            if entity_id is None and not self._entity_allowed(candidate_id):
                continue
            for triangle in vertices.reshape((-1, 3, 3)):
                distance = _ray_triangle_intersection(origin, direction, triangle)
                if distance is None or (best is not None and distance >= best[0]):
                    continue
                point = origin + direction * distance
                best = (distance, candidate_id, tuple(map(float, point)))
        if best is None:
            return None
        return PickHit(kind, best[1], best[2])

    def _screen_ray_source(self, pos: QPoint) -> tuple[np.ndarray, np.ndarray] | None:
        mvp = self._projection_matrix() @ self._view_matrix() @ self._model_transform
        return _unproject_screen_ray(
            float(pos.x()),
            float(pos.y()),
            max(1, self.width()),
            max(1, self.height()),
            mvp,
        )

    def _hit_position_source(
        self,
        kind: str,
        entity_id: str,
        pos: QPoint,
    ) -> tuple[float, float, float] | None:
        if kind == "vertex":
            return self._vertex_positions.get(entity_id)
        if kind == "edge":
            hit = self._pick_edge_projection_hit(pos, entity_id)
            if hit is not None:
                return hit.position_source
        if kind in {"body", "face"}:
            hit = self._pick_triangle_hit(pos, kind, entity_id)
            if hit is not None:
                return hit.position_source
        if self.model is None:
            return None
        if kind == "face":
            face = self.model.face_map.get(entity_id)
            return None if face is None else face.centroid
        if kind == "body":
            body = self.model.body_map.get(entity_id)
            return None if body is None else body.centroid
        return None

    def _project(
        self, point: tuple[float, float, float], mvp: np.ndarray
    ) -> np.ndarray | None:
        clip = mvp @ np.array([point[0], point[1], point[2], 1.0], dtype=np.float32)
        if float(clip[3]) <= 1e-6:
            return None
        ndc = clip[:3] / clip[3]
        if not np.isfinite(ndc).all() or float(ndc[2]) < -1.01 or float(ndc[2]) > 1.01:
            return None
        x = (ndc[0] * 0.5 + 0.5) * self.width()
        y = (1.0 - (ndc[1] * 0.5 + 0.5)) * self.height()
        return np.array([x, y], dtype=np.float32)

    def _set_shader_mvp(self, matrix: np.ndarray) -> None:
        glUniformMatrix4fv(self._mvp_loc, 1, True, np.asarray(matrix, dtype=np.float32))

    def _set_buffer(
        self,
        key: str,
        vertices: list[tuple[float, float, float]] | np.ndarray,
        colors: list[tuple[float, float, float, float]] | np.ndarray,
        primitive: int,
        *,
        draw_starts: np.ndarray | None = None,
        draw_counts: np.ndarray | None = None,
    ) -> None:
        vertex_array = (
            np.asarray(vertices, dtype=np.float32).reshape((-1, 3))
            if len(vertices)
            else np.empty((0, 3), dtype=np.float32)
        )
        color_array = (
            np.asarray(colors, dtype=np.float32).reshape((-1, 4))
            if len(colors)
            else np.empty((0, 4), dtype=np.float32)
        )
        if vertex_array.shape[0] != color_array.shape[0]:
            raise ValueError("OpenGL buffer vertex and color counts must match")
        range_starts = (
            None
            if draw_starts is None
            else np.asarray(draw_starts, dtype=np.int32).reshape((-1,))
        )
        range_counts = (
            None
            if draw_counts is None
            else np.asarray(draw_counts, dtype=np.int32).reshape((-1,))
        )
        if (range_starts is None) != (range_counts is None):
            raise ValueError("OpenGL buffer draw ranges require both starts and counts")
        if range_starts is not None and range_starts.size != range_counts.size:
            raise ValueError("OpenGL buffer draw range counts must match")
        old = self._buffers.get(key)
        vbo = 0 if old is None else old.vbo
        self._buffers[key] = _Buffer(
            vertex_array,
            color_array,
            primitive,
            draw_starts=range_starts,
            draw_counts=range_counts,
            vbo=vbo,
            dirty=True,
        )

    def _draw_buffer(self, key: str, line_width: float, depth_bias: float = 0.0) -> int:
        buffer = self._buffers.get(key)
        if buffer is None or buffer.count == 0:
            return 0
        if buffer.vbo == 0:
            buffer.vbo = int(glGenBuffers(1))
            buffer.dirty = True
        if buffer.dirty:
            packed = np.hstack((buffer.vertices, buffer.colors)).astype(
                np.float32, copy=False
            )
            glBindBuffer(GL_ARRAY_BUFFER, buffer.vbo)
            glBufferData(GL_ARRAY_BUFFER, packed.nbytes, packed, GL_STATIC_DRAW)
            buffer.dirty = False
        glBindBuffer(GL_ARRAY_BUFFER, buffer.vbo)
        stride = 7 * 4
        glEnableVertexAttribArray(self._position_loc)
        glEnableVertexAttribArray(self._color_loc)
        glUniform1f(self._depth_bias_loc, float(depth_bias))
        glVertexAttribPointer(
            self._position_loc, 3, GL_FLOAT, False, stride, ctypes.c_void_p(0)
        )
        glVertexAttribPointer(
            self._color_loc, 4, GL_FLOAT, False, stride, ctypes.c_void_p(3 * 4)
        )
        if buffer.primitive == GL_LINES:
            glLineWidth(line_width)
        elif buffer.primitive == GL_LINE_STRIP:
            glLineWidth(line_width)
        if buffer.draw_starts is not None and buffer.draw_counts is not None:
            range_count = int(buffer.draw_starts.size)
            if range_count == 1:
                glDrawArrays(
                    buffer.primitive,
                    int(buffer.draw_starts[0]),
                    int(buffer.draw_counts[0]),
                )
            elif range_count > 1:
                try:
                    glMultiDrawArrays(
                        buffer.primitive,
                        buffer.draw_starts,
                        buffer.draw_counts,
                        range_count,
                    )
                except Exception:
                    for first, count in zip(buffer.draw_starts, buffer.draw_counts):
                        glDrawArrays(buffer.primitive, int(first), int(count))
        else:
            glDrawArrays(buffer.primitive, 0, buffer.count)
        return 1

    def _scene_bounds(self) -> tuple[np.ndarray, np.ndarray] | None:
        points: list[np.ndarray] = []
        model_buffer = self._buffers.get("model")
        if model_buffer is not None and model_buffer.count:
            points.append(
                _transform_points(model_buffer.vertices, self._model_transform)
            )
        for key in (
            "path_line",
            "path_solid",
            "path_paper",
            "coordinate_frames",
            "coordinate_frames_active",
            "build_surface",
        ):
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
        eye, target, view_up = self._camera_vectors()
        return _look_at(eye, target, view_up)

    def _camera_vectors(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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
        return eye, target, self._view_up

    def _projection_matrix(
        self, width: int | None = None, height: int | None = None
    ) -> np.ndarray:
        width = self.width() if width is None else int(width)
        height = self.height() if height is None else int(height)
        aspect = max(width, 1) / max(height, 1)
        near = max(0.1, self._distance - self._radius * 1.6)
        far = self._distance + self._radius * 2.5 + 20.0
        return _perspective(math.radians(45.0), aspect, near, far)

    def close(self) -> bool:  # noqa: D102 - Qt API
        self.makeCurrent()
        for buffer in self._buffers.values():
            if buffer.vbo:
                glDeleteBuffers(1, [buffer.vbo])
                buffer.vbo = 0
        self.doneCurrent()
        return super().close()


def _build_paper_path_arrays(
    preview: GCodePreview,
    settings: PreviewSettings,
    current_global_step: int | None,
    *,
    tolerance: float = PAPER_PATH_JOIN_TOLERANCE_MM,
) -> _PaperPathArrays:
    timeline_arrays = preview.timeline_arrays
    if timeline_arrays is not None:
        count = timeline_arrays.count
        starts = timeline_arrays.starts
        ends = timeline_arrays.ends
        layers = timeline_arrays.layers
        move_codes = timeline_arrays.move_codes
        role_codes = timeline_arrays.role_codes
        delta_es = timeline_arrays.delta_es
        spatial = (timeline_arrays.flags & TIMELINE_FLAG_HAS_SPATIAL_LENGTH) != 0
        step_indices = np.arange(count, dtype=np.int64)
    else:
        timeline = preview.timeline
        count = len(timeline)
        starts = np.asarray(
            [step.start for step in timeline], dtype=np.float32
        ).reshape((-1, 3))
        ends = np.asarray([step.end for step in timeline], dtype=np.float32).reshape(
            (-1, 3)
        )
        layers = np.asarray([step.layer for step in timeline], dtype=np.int32)
        move_codes = np.asarray(
            [MOVE_CODES.get(step.move_type, MOVE_CODES["noop"]) for step in timeline],
            dtype=np.uint8,
        )
        role_codes = np.asarray(
            [
                ROLE_CODES.get(step.extrusion_role, ROLE_CODES["unknown"])
                for step in timeline
            ],
            dtype=np.uint8,
        )
        delta_es = np.asarray([step.delta_e for step in timeline], dtype=np.float32)
        spatial = np.asarray(
            [step.has_spatial_length for step in timeline], dtype=np.bool_
        )
        step_indices = np.asarray(
            [step.step_index for step in timeline], dtype=np.int64
        )

    if count == 0:
        return _empty_paper_path_arrays()

    low = min(settings.layer_min, settings.layer_max)
    high = max(settings.layer_min, settings.layer_max)
    layer_mask = (layers >= low) & (layers <= high)
    extrusion_mask = (move_codes == MOVE_CODES["extrude"]) & (delta_es > 0.0) & spatial
    if settings.visible_roles:
        allowed_roles = np.asarray(
            [ROLE_CODES[role] for role in settings.visible_roles if role in ROLE_CODES],
            dtype=np.uint8,
        )
        role_mask = (
            np.isin(role_codes, allowed_roles)
            if allowed_roles.size
            else np.zeros(count, dtype=np.bool_)
        )
    else:
        role_mask = np.zeros(count, dtype=np.bool_)

    visible = layer_mask & spatial
    selected_type = np.zeros(count, dtype=np.bool_)
    if settings.show_extrusion:
        selected_type |= extrusion_mask & role_mask
    if settings.show_travel:
        selected_type |= ~extrusion_mask
    visible &= selected_type
    if current_global_step is not None and not settings.show_upcoming:
        visible &= step_indices <= int(current_global_step)

    indices = np.flatnonzero(visible)
    if indices.size == 0:
        return _empty_paper_path_arrays()

    selected_starts = np.asarray(starts[indices], dtype=np.float32)
    selected_ends = np.asarray(ends[indices], dtype=np.float32)
    selected_extrusion = extrusion_mask[indices]
    segment_colors = np.empty((indices.size, 4), dtype=np.float32)
    segment_colors[selected_extrusion] = PAPER_PATH_COLOR
    segment_colors[~selected_extrusion] = PAPER_TRAVEL_COLOR
    style_keys = selected_extrusion.astype(np.uint8)
    vertices, colors, draw_starts, draw_counts = _build_continuous_line_strips(
        selected_starts,
        selected_ends,
        segment_colors,
        style_keys,
        tolerance=tolerance,
    )
    return _PaperPathArrays(
        vertices=vertices,
        colors=colors,
        draw_starts=draw_starts,
        draw_counts=draw_counts,
        segment_count=int(indices.size),
        first_point=tuple(float(value) for value in selected_starts[0]),
        last_point=tuple(float(value) for value in selected_ends[-1]),
    )


def _empty_paper_path_arrays() -> _PaperPathArrays:
    return _PaperPathArrays(
        vertices=np.empty((0, 3), dtype=np.float32),
        colors=np.empty((0, 4), dtype=np.float32),
        draw_starts=np.empty((0,), dtype=np.int32),
        draw_counts=np.empty((0,), dtype=np.int32),
        segment_count=0,
        first_point=None,
        last_point=None,
    )


def _build_continuous_line_strips(
    starts: np.ndarray,
    ends: np.ndarray,
    segment_colors: np.ndarray,
    style_keys: np.ndarray,
    *,
    tolerance: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    starts = np.asarray(starts, dtype=np.float32).reshape((-1, 3))
    ends = np.asarray(ends, dtype=np.float32).reshape((-1, 3))
    segment_colors = np.asarray(segment_colors, dtype=np.float32).reshape((-1, 4))
    style_keys = np.asarray(style_keys).reshape((-1,))
    count = int(starts.shape[0])
    if (
        ends.shape[0] != count
        or segment_colors.shape[0] != count
        or style_keys.size != count
    ):
        raise ValueError(
            "Polyline source arrays must contain the same number of segments"
        )
    if count == 0:
        return (
            np.empty((0, 3), dtype=np.float32),
            np.empty((0, 4), dtype=np.float32),
            np.empty((0,), dtype=np.int32),
            np.empty((0,), dtype=np.int32),
        )

    break_before = np.ones(count, dtype=np.bool_)
    if count > 1:
        gaps = starts[1:] - ends[:-1]
        distance_sq = np.einsum("ij,ij->i", gaps, gaps)
        break_before[1:] = (distance_sq > max(0.0, float(tolerance)) ** 2) | (
            style_keys[1:] != style_keys[:-1]
        )
    break_indices = np.flatnonzero(break_before).astype(np.int32, copy=False)
    polyline_ids = np.cumsum(break_before, dtype=np.int32) - 1
    start_positions = np.arange(count, dtype=np.int32) + polyline_ids
    end_positions = start_positions + 1
    vertex_count = count + int(break_indices.size)
    vertices = np.empty((vertex_count, 3), dtype=np.float32)
    vertices[start_positions] = starts
    vertices[end_positions] = ends

    draw_starts = break_indices + np.arange(break_indices.size, dtype=np.int32)
    segment_run_ends = np.append(break_indices[1:], np.int32(count))
    draw_counts = (segment_run_ends - break_indices + 1).astype(np.int32, copy=False)
    colors = np.repeat(segment_colors[break_indices], draw_counts, axis=0).astype(
        np.float32, copy=False
    )
    return vertices, colors, draw_starts, draw_counts


def _points_array(points: Iterable[Iterable[float]]) -> np.ndarray:
    values = tuple(tuple(point) for point in points)
    if not values:
        return np.empty((0, 3), dtype=np.float32)
    return np.asarray(values, dtype=np.float32).reshape((-1, 3))


def _validated_rigid_transform(matrix: Iterable[Iterable[float]]) -> np.ndarray:
    values = np.asarray(tuple(tuple(row) for row in matrix), dtype=np.float64)
    if values.shape != (4, 4) or not np.isfinite(values).all():
        raise ValueError("model transform must be a finite 4x4 matrix")
    if not np.allclose(values[3], (0.0, 0.0, 0.0, 1.0), atol=1e-7, rtol=0.0):
        raise ValueError("model transform must use homogeneous rigid coordinates")
    rotation = values[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6, rtol=0.0):
        raise ValueError("model transform rotation must be orthonormal")
    if not math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-6):
        raise ValueError("model transform must preserve right-handed orientation")
    return values


def _validate_coordinate_frame(frame: CoordinateFrameOverlay) -> None:
    origin = np.asarray(frame.origin, dtype=np.float64)
    basis = np.column_stack(
        (
            np.asarray(frame.x_axis, dtype=np.float64),
            np.asarray(frame.y_axis, dtype=np.float64),
            np.asarray(frame.z_axis, dtype=np.float64),
        )
    )
    if (
        origin.shape != (3,)
        or basis.shape != (3, 3)
        or not np.isfinite(origin).all()
        or not np.isfinite(basis).all()
    ):
        raise ValueError(
            f"coordinate frame {frame.frame_id!r} must contain finite 3D vectors"
        )
    lengths = np.linalg.norm(basis, axis=0)
    if np.any(lengths <= 1e-12):
        raise ValueError(f"coordinate frame {frame.frame_id!r} contains a zero axis")
    normalized = basis / lengths
    if not np.allclose(normalized.T @ normalized, np.eye(3), atol=1e-5, rtol=0.0):
        raise ValueError(f"coordinate frame {frame.frame_id!r} axes must be orthogonal")
    if float(np.linalg.det(normalized)) <= 0.0:
        raise ValueError(f"coordinate frame {frame.frame_id!r} must be right-handed")
    if not math.isfinite(float(frame.scale)) or float(frame.scale) <= 0.0:
        raise ValueError(f"coordinate frame {frame.frame_id!r} scale must be positive")


def _coordinate_frame_lines(
    frame: CoordinateFrameOverlay,
    scale: float,
) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[float, float, float, float]],
]:
    origin = np.asarray(frame.origin, dtype=np.float64)
    vertices: list[tuple[float, float, float]] = []
    colors: list[tuple[float, float, float, float]] = []
    for axis, color in (
        (frame.x_axis, AXIS_X_COLOR),
        (frame.y_axis, AXIS_Y_COLOR),
        (frame.z_axis, AXIS_Z_COLOR),
    ):
        axis_vertices = _axis_arrow_lines(
            origin, np.asarray(axis, dtype=np.float64), scale
        )
        vertices.extend(axis_vertices)
        colors.extend([color] * len(axis_vertices))
    return vertices, colors


def _axis_arrow_lines(
    origin: np.ndarray,
    direction: np.ndarray,
    scale: float,
) -> list[tuple[float, float, float]]:
    direction = direction / np.linalg.norm(direction)
    tip = origin + direction * scale
    helper = np.array((0.0, 0.0, 1.0), dtype=np.float64)
    if abs(float(np.dot(direction, helper))) > 0.88:
        helper = np.array((0.0, 1.0, 0.0), dtype=np.float64)
    side = np.cross(direction, helper)
    side /= np.linalg.norm(side)
    up = np.cross(direction, side)
    arrow_base = tip - direction * scale * 0.20
    wing = scale * 0.085
    points = [tuple(map(float, origin)), tuple(map(float, tip))]
    for offset in (side * wing, -side * wing, up * wing, -up * wing):
        points.extend((tuple(map(float, tip)), tuple(map(float, arrow_base + offset))))
    return points


def _build_surface_lines(
    surface: BuildSurfaceOverlay,
) -> list[tuple[float, float, float]]:
    origin = np.asarray(surface.origin, dtype=np.float64)
    x_axis = np.asarray(surface.x_axis, dtype=np.float64)
    y_axis = np.asarray(surface.y_axis, dtype=np.float64)
    if (
        origin.shape != (3,)
        or x_axis.shape != (3,)
        or y_axis.shape != (3,)
        or not np.isfinite(np.concatenate((origin, x_axis, y_axis))).all()
    ):
        raise ValueError("build surface basis must contain finite 3D vectors")
    x_length = float(np.linalg.norm(x_axis))
    y_length = float(np.linalg.norm(y_axis))
    if x_length <= 1e-12 or y_length <= 1e-12:
        raise ValueError("build surface axes must be nonzero")
    x_axis /= x_length
    y_axis /= y_length
    if abs(float(np.dot(x_axis, y_axis))) > 1e-5:
        raise ValueError("build surface axes must be orthogonal")

    shape = str(surface.shape).lower()
    if shape == "circle":
        diameter = 100.0 if surface.diameter_mm is None else float(surface.diameter_mm)
        if not math.isfinite(diameter) or diameter <= 0.0:
            raise ValueError("circular build surface diameter must be positive")
        half_x = half_y = diameter * 0.5
        local = [
            (
                half_x * math.cos(2.0 * math.pi * index / 64),
                half_y * math.sin(2.0 * math.pi * index / 64),
            )
            for index in range(64)
        ]
    elif shape == "rectangle":
        width = 100.0 if surface.width_mm is None else float(surface.width_mm)
        depth = width if surface.depth_mm is None else float(surface.depth_mm)
        if (
            not math.isfinite(width)
            or not math.isfinite(depth)
            or width <= 0.0
            or depth <= 0.0
        ):
            raise ValueError("rectangular build surface dimensions must be positive")
        half_x = width * 0.5
        half_y = depth * 0.5
        local = [
            (-half_x, -half_y),
            (half_x, -half_y),
            (half_x, half_y),
            (-half_x, half_y),
        ]
    else:
        raise ValueError(f"unsupported build surface shape: {surface.shape}")

    def world(point: tuple[float, float]) -> tuple[float, float, float]:
        value = origin + point[0] * x_axis + point[1] * y_axis
        return tuple(map(float, value))

    vertices: list[tuple[float, float, float]] = []
    for index, point in enumerate(local):
        vertices.extend((world(point), world(local[(index + 1) % len(local)])))
    vertices.extend((world((-half_x, 0.0)), world((half_x, 0.0))))
    vertices.extend((world((0.0, -half_y)), world((0.0, half_y))))
    return vertices


def _vertex_marker_lines(
    point: tuple[float, float, float],
    radius: float,
) -> list[tuple[float, float, float]]:
    center = np.asarray(point, dtype=np.float64)
    vertices: list[tuple[float, float, float]] = []
    for axis in np.eye(3):
        vertices.extend(
            (
                tuple(map(float, center - axis * radius)),
                tuple(map(float, center + axis * radius)),
            )
        )
    return vertices


def _transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    values = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    if values.size == 0:
        return np.empty((0, 3), dtype=np.float32)
    homogeneous = np.column_stack((values, np.ones(len(values), dtype=np.float64)))
    transformed = (np.asarray(matrix, dtype=np.float64) @ homogeneous.T).T
    return np.asarray(transformed[:, :3] / transformed[:, 3, None], dtype=np.float32)


def _screen_segment_distance_and_fraction(
    point: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
) -> tuple[float, float]:
    segment = end - start
    length_sq = float(np.dot(segment, segment))
    if length_sq <= 1e-12:
        return float(np.linalg.norm(point - start)), 0.0
    fraction = max(0.0, min(1.0, float(np.dot(point - start, segment) / length_sq)))
    projection = start + fraction * segment
    return float(np.linalg.norm(point - projection)), fraction


def _unproject_screen_ray(
    x: float,
    y: float,
    width: int,
    height: int,
    mvp: np.ndarray,
) -> tuple[np.ndarray, np.ndarray] | None:
    if width <= 0 or height <= 0:
        return None
    try:
        inverse = np.linalg.inv(np.asarray(mvp, dtype=np.float64))
    except np.linalg.LinAlgError:
        return None
    ndc_x = 2.0 * float(x) / float(width) - 1.0
    ndc_y = 1.0 - 2.0 * float(y) / float(height)
    near = inverse @ np.array((ndc_x, ndc_y, -1.0, 1.0), dtype=np.float64)
    far = inverse @ np.array((ndc_x, ndc_y, 1.0, 1.0), dtype=np.float64)
    if abs(float(near[3])) <= 1e-12 or abs(float(far[3])) <= 1e-12:
        return None
    origin = near[:3] / near[3]
    far_point = far[:3] / far[3]
    direction = far_point - origin
    length = float(np.linalg.norm(direction))
    if length <= 1e-12 or not np.isfinite(direction).all():
        return None
    return origin, direction / length


def _ray_triangle_intersection(
    origin: np.ndarray,
    direction: np.ndarray,
    triangle: np.ndarray,
) -> float | None:
    first, second, third = np.asarray(triangle, dtype=np.float64)
    edge_one = second - first
    edge_two = third - first
    cross = np.cross(direction, edge_two)
    determinant = float(np.dot(edge_one, cross))
    if abs(determinant) <= 1e-10:
        return None
    inverse = 1.0 / determinant
    offset = origin - first
    u = inverse * float(np.dot(offset, cross))
    if u < -1e-9 or u > 1.0 + 1e-9:
        return None
    second_cross = np.cross(offset, edge_one)
    v = inverse * float(np.dot(direction, second_cross))
    if v < -1e-9 or u + v > 1.0 + 1e-9:
        return None
    distance = inverse * float(np.dot(edge_two, second_cross))
    return distance if distance >= 0.0 else None


def _nice_grid_step(target: float) -> float:
    target = max(float(target), 1e-6)
    magnitude = 10.0 ** math.floor(math.log10(target))
    fraction = target / magnitude
    if fraction <= 1.0:
        multiplier = 1.0
    elif fraction <= 2.0:
        multiplier = 2.0
    elif fraction <= 5.0:
        multiplier = 5.0
    else:
        multiplier = 10.0
    return multiplier * magnitude


def _inclusive_grid_values(low: float, high: float, step: float) -> list[float]:
    count = max(0, int(round((high - low) / step)))
    return [low + index * step for index in range(count + 1)]


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


def _polydata_lines(
    polydata,
) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    points = polydata.GetPoints()
    if points is None:
        return []
    output: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
    ids = vtk.vtkIdList()
    lines = polydata.GetLines()
    lines.InitTraversal()
    while lines.GetNextCell(ids):
        for index in range(ids.GetNumberOfIds() - 1):
            output.append(
                (
                    tuple(points.GetPoint(ids.GetId(index))),
                    tuple(points.GetPoint(ids.GetId(index + 1))),
                )
            )
    return output


def _build_line_arrays(
    segments: list[GCodePathSegment],
    stride: int,
) -> tuple[
    list[tuple[float, float, float]], list[tuple[float, float, float, float]], int
]:
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
    *,
    controller_semantics: str | None = None,
) -> tuple[
    list[tuple[float, float, float]], list[tuple[float, float, float, float]], int
]:
    from .viewer import _bead_frame

    vertices: list[tuple[float, float, float]] = []
    colors: list[tuple[float, float, float, float]] = []
    drawn = 0
    for index, segment in enumerate(segments):
        if segment.move_type != "extrude":
            continue
        if stride > 1 and index % stride != 0:
            continue
        frame = _bead_frame(
            segment.start,
            segment.end,
            segment.rotary_end,
            controller_semantics=controller_semantics,
            coordinate_transform=segment.coordinate_transform,
        )
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
            start_ring.append(
                tuple(segment.start[axis] + offset[axis] for axis in range(3))
            )
            end_ring.append(
                tuple(segment.end[axis] + offset[axis] for axis in range(3))
            )
        color = (*segment.color(), 0.96)
        for side in range(BEAD_SECTION_SIDES):
            next_side = (side + 1) % BEAD_SECTION_SIDES
            quad = [
                start_ring[side],
                start_ring[next_side],
                end_ring[next_side],
                end_ring[side],
            ]
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


def _distance_to_screen_segment(
    point: np.ndarray, start: np.ndarray, end: np.ndarray
) -> float:
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
uniform float depth_bias;
varying vec4 v_color;

void main() {
    vec4 clip_position = mvp * vec4(position, 1.0);
    clip_position.z -= depth_bias * clip_position.w;
    gl_Position = clip_position;
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
