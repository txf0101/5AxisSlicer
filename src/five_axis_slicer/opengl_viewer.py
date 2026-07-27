"""OpenGL Viewer whose widget lifecycle owns every GL resource operation."""

from __future__ import annotations

import ctypes
import math
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from PyQt5.QtCore import QPoint, Qt, QTimer
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QOpenGLWidget

try:  # pragma: no cover - import availability is environment dependent.
    from OpenGL.GL import (
        GL_ARRAY_BUFFER,
        GL_BLEND,
        GL_COLOR_ATTACHMENT0,
        GL_COLOR_BUFFER_BIT,
        GL_DEPTH_ATTACHMENT,
        GL_DEPTH_BUFFER_BIT,
        GL_DEPTH_COMPONENT24,
        GL_DEPTH_TEST,
        GL_FLOAT,
        GL_FRAGMENT_SHADER,
        GL_FRAMEBUFFER,
        GL_FRAMEBUFFER_BINDING,
        GL_FRAMEBUFFER_COMPLETE,
        GL_LINE_STRIP,
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
        glBufferData,
        glCheckFramebufferStatus,
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

from . import opengl_picking as _picking
from . import opengl_scene as _scene
from . import viewer_common as _viewer_common
from .gcode_preview import (
    GCodePathSegment,
    GCodePreview,
    GCodeTimelineStep,
    PreviewSettings,
)
from .geometry_vtk import edge_to_polydata, shape_to_polydata
from .models import (
    BuildSurfaceOverlay,
    CadModel,
    CoordinateFrameOverlay,
    PickHit,
    PickRequest,
    SelectionState,
)
from .viewer_common import (
    PickCallback,
    SelectionCallback,
    apply_pick_selection,
    clamp_progress_index,
    current_progress_step,
    pick_request_for_mode,
    preview_pose_for_segment,
    preview_settings_for,
    preview_state_payload,
    progress_state,
    replace_selection,
    representative_path_segment,
    segment_visible,
    set_preview_layers,
    update_preview_visibility,
    vector3,
)
from .viewer_interaction import (
    BambuNavigationMixin,
    OpenGLCameraNavigation,
    z_up_orbit_direction,
)

AXIS_X_COLOR = _scene.AXIS_X_COLOR
AXIS_Y_COLOR = _scene.AXIS_Y_COLOR
AXIS_Z_COLOR = _scene.AXIS_Z_COLOR
BEAD_SECTION_SIDES = _scene.BEAD_SECTION_SIDES
PAPER_PATH_COLOR = _scene.PAPER_PATH_COLOR
PAPER_PATH_JOIN_TOLERANCE_MM = _scene.PAPER_PATH_JOIN_TOLERANCE_MM
PAPER_TRAVEL_COLOR = _scene.PAPER_TRAVEL_COLOR
_EdgeSegment = _scene.EdgeSegment
_PaperPathArrays = _scene.PaperPathArrays
_build_bead_arrays = _scene.build_bead_arrays
_build_continuous_line_strips = _scene.build_continuous_line_strips
_build_line_arrays = _scene.build_line_arrays
_build_paper_path_arrays = _scene.build_paper_path_arrays
_build_surface_lines = _scene.build_surface_lines
_coordinate_frame_lines = _scene.coordinate_frame_lines
_inclusive_grid_values = _scene.inclusive_grid_values
_nice_grid_step = _scene.nice_grid_step
_points_array = _scene.points_array
_polydata_lines = _scene.polydata_lines
_polydata_triangles = _scene.polydata_triangles
_transform_points = _scene.transform_points
_validate_coordinate_frame = _scene.validate_coordinate_frame
_vertex_marker_lines = _scene.vertex_marker_lines
_distance_to_screen_segment = _picking.distance_to_screen_segment
_encode_pick_color = _picking.encode_pick_color
_ray_triangle_intersection = _picking.ray_triangle_intersection
_screen_segment_distance_and_fraction = _picking.screen_segment_distance_and_fraction
_unproject_screen_ray = _picking.unproject_screen_ray
_render_stride = _viewer_common.render_stride
_validated_rigid_transform = _viewer_common.validated_rigid_transform

__all__ = [
    "AXIS_X_COLOR",
    "AXIS_Y_COLOR",
    "AXIS_Z_COLOR",
    "BEAD_SECTION_SIDES",
    "OPENGL_AVAILABLE",
    "OpenGLModelViewer",
    "PAPER_PATH_COLOR",
    "PAPER_TRAVEL_COLOR",
    "_EdgeSegment",
    "_PaperPathArrays",
    "_build_continuous_line_strips",
    "_build_surface_lines",
    "_distance_to_screen_segment",
    "_ray_triangle_intersection",
    "_transform_points",
    "_unproject_screen_ray",
    "_validated_rigid_transform",
]

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
MODEL_WITH_PATH_COLOR = (0.690, 0.718, 0.765, 0.76)
CURRENT_COLOR = (0.961, 0.620, 0.043, 1.0)
START_COLOR = (0.086, 0.639, 0.290, 1.0)
END_COLOR = (0.863, 0.149, 0.149, 1.0)
STATIC_SOLID_SEGMENT_LIMIT = 18_000
INTERACTIVE_LINE_SEGMENT_LIMIT = 35_000
INITIAL_SOLID_SETTLE_MS = 1200


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


class OpenGLModelViewer(BambuNavigationMixin, QOpenGLWidget):
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
        self._opengl_camera = OpenGLCameraNavigation(self)
        self._init_view_navigation(self._opengl_camera)
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
            self._body_triangles[body.body_id] = _points_array(_polydata_triangles(polydata))

            for face_id in body.face_ids:
                face_shape = model.face_shapes.get(face_id)
                if face_shape is None:
                    continue
                face_polydata = shape_to_polydata(face_shape)
                self._face_triangles[face_id] = _points_array(_polydata_triangles(face_polydata))

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
        self.preview_settings = preview_settings_for(
            preview,
            backend=self.backend,
            quality_mode=self.quality_mode,
            solid_rendering=self.quality_mode == "interactive",
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
        set_preview_layers(
            self.gcode_preview,
            self.preview_settings,
            layer_min,
            layer_max,
        )
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
        update_preview_visibility(
            self.preview_settings,
            show_travel=show_travel,
            show_extrusion=show_extrusion,
            visible_roles=visible_roles,
            show_pose_samples=show_pose_samples,
        )
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
            "front": (180.0, 90.0, (0.0, 0.0, 1.0)),
            "back": (0.0, 90.0, (0.0, 0.0, 1.0)),
            "left": (-90.0, 90.0, (0.0, 0.0, 1.0)),
            "right": (90.0, 90.0, (0.0, 0.0, 1.0)),
            "top": (0.0, 0.0, (0.0, 1.0, 0.0)),
            "bottom": (0.0, 180.0, (0.0, 1.0, 0.0)),
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
            "offscreen_capture": True,
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
        return preview_state_payload(
            self.gcode_preview,
            self.preview_settings,
            backend=self.backend,
            visible_count=self.visible_path_segment_count,
            drawn_count=self.drawn_path_segment_count,
            render_mode=self.path_render_mode,
            frame_ms=float(perf["frame_ms_avg"]),
            gpu_draw_count=int(perf["gpu_draw_count"]),
            result_visibility={
                "model": self._model_visible,
                "start_end": self._start_end_visible,
                "grid": self._grid_visible,
            },
        )

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
        return progress_state(self.gcode_preview, self.preview_settings)

    def current_progress_step(self) -> GCodeTimelineStep | None:
        return current_progress_step(self.gcode_preview, self.preview_settings)

    def representative_path_segment(self) -> GCodePathSegment | None:
        return representative_path_segment(self.gcode_preview, self.preview_settings)

    def set_mode(self, mode: str) -> None:
        request = pick_request_for_mode(mode)
        self.selection.mode = mode
        self.pick_request = request
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
        replace_selection(
            self.selection,
            body_ids=body_ids,
            edge_ids=edge_ids,
            face_ids=face_ids,
            vertex_ids=vertex_ids,
        )
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
                active_vertices if frame.frame_id == active_frame_id else normal_vertices
            )
            target_colors = active_colors if frame.frame_id == active_frame_id else normal_colors
            scale = float(frame.scale) * (1.18 if frame.frame_id == active_frame_id else 1.0)
            vertices, colors = _coordinate_frame_lines(frame, scale)
            target_vertices.extend(vertices)
            target_colors.extend(colors)
        self._set_buffer("coordinate_frames", normal_vertices, normal_colors, GL_LINES)
        self._set_buffer("coordinate_frames_active", active_vertices, active_colors, GL_LINES)
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
            self._yaw -= math.radians(value)
        elif command == "elevation":
            self._view_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            self._pitch = max(
                math.radians(1.0),
                min(math.radians(179.0), self._pitch - math.radians(value)),
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
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0)
            glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depth)
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
        self._paint_scene(max(1, self.width()), max(1, self.height()), record_metrics=True)

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
            draw_count += self._draw_buffer("face_selected", line_width=1.0, depth_bias=0.0002)
            draw_count += self._draw_buffer("edge", line_width=2.2 * line_scale, depth_bias=0.0004)
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
            draw_count += self._draw_buffer("path_solid", line_width=1.0, depth_bias=0.0004)
        else:
            draw_count += self._draw_buffer(
                "path_line",
                line_width=2.4 * line_scale,
                depth_bias=0.0004,
            )
        draw_count += self._draw_buffer("pose", line_width=1.3 * line_scale, depth_bias=0.0008)
        draw_count += self._draw_buffer("current", line_width=4.5 * line_scale, depth_bias=0.0010)
        if self._start_end_visible:
            draw_count += self._draw_buffer("start", line_width=3.2 * line_scale, depth_bias=0.0012)
            draw_count += self._draw_buffer("end", line_width=3.2 * line_scale, depth_bias=0.0012)
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
            self._last_memory_bytes = sum(buffer.nbytes for buffer in self._buffers.values())
            self._frame_ms.append((time.perf_counter() - started) * 1000.0)

    def _view_left_click(self, pos: QPoint) -> None:
        hit = self._pick(pos)
        if hit is not None:
            self._apply_pick(hit)
            return
        self.clear_selection()
        if self.selection_callback is not None:
            self.selection_callback(None, None)

    def _view_interaction_started(self) -> None:
        if self.gcode_preview is None:
            return
        self._settle_timer.stop()
        self._interaction_preview = True
        self.refresh_path_preview()

    def _view_interaction_finished(self) -> None:
        if self.gcode_preview is not None:
            self._settle_timer.start(150)

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
        clamp_progress_index(self.gcode_preview, self.preview_settings)

    def _segment_visible(self, segment: GCodePathSegment) -> bool:
        return segment_visible(segment, self.preview_settings)

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
            if segment.move_type == "extrude" and (segment.rotary_end or segment.rotary_start)
        ]
        if not candidates:
            self._set_buffer("pose", [], [], GL_LINES)
            return
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
            start, axis = preview_pose_for_segment(
                segment,
                controller_semantics=(
                    self.gcode_preview.controller_semantics
                    if self.gcode_preview is not None
                    else None
                ),
            )
            end = vector3(start[index] + axis[index] * length for index in range(3))
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
            color = GRID_MAJOR_COLOR if int(round(x / step)) % 5 == 0 else GRID_MINOR_COLOR
            vertices.extend([(x, y_min, z), (x, y_max, z)])
            colors.extend([color, color])
        for y in y_values:
            color = GRID_MAJOR_COLOR if int(round(y / step)) % 5 == 0 else GRID_MINOR_COLOR
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
                selected_vertices if segment.edge_id in self.selection.edge_ids else edge_vertices
            )
            target_colors = (
                selected_colors if segment.edge_id in self.selection.edge_ids else edge_colors
            )
            color = (
                EDGE_SELECTED_COLOR if segment.edge_id in self.selection.edge_ids else EDGE_COLOR
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
        self._set_buffer("vertex_selected", selected_vertices, selected_colors, GL_LINES)

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
            edge_color = edge_colors_by_id.get(segment.edge_id)
            if edge_color is None:
                edge_color = register("edge", segment.edge_id)
                edge_colors_by_id[segment.edge_id] = edge_color
            edge_vertices.extend([segment.start, segment.end])
            edge_colors.extend([edge_color, edge_color])
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
        if not apply_pick_selection(
            self.selection,
            self.pick_request,
            hit.kind,
            hit.entity_id,
        ):
            return
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
                return PickHit(kind, entity[1], self._hit_position_source(kind, entity[1], pos))
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

    def _pick_entity_by_color_id(self, pos: QPoint, kind: str) -> tuple[str, str] | None:
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
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0)
            glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, depth)
            if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
                return None

            glViewport(0, 0, width, height)
            glDisable(GL_BLEND)
            glClearColor(0.0, 0.0, 0.0, 0.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glUseProgram(self._program)
            mvp = self._projection_matrix() @ self._view_matrix() @ self._model_transform
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
            distance, fraction = _screen_segment_distance_and_fraction(point, left, right)
            position = vector3(
                float(segment.start[index] + fraction * (segment.end[index] - segment.start[index]))
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
                best = (distance, candidate_id, vector3(point))
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

    def _project(self, point: tuple[float, float, float], mvp: np.ndarray) -> np.ndarray | None:
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
            None if draw_starts is None else np.asarray(draw_starts, dtype=np.int32).reshape((-1,))
        )
        range_counts = (
            None if draw_counts is None else np.asarray(draw_counts, dtype=np.int32).reshape((-1,))
        )
        if (range_starts is None) != (range_counts is None):
            raise ValueError("OpenGL buffer draw ranges require both starts and counts")
        if (
            range_starts is not None
            and range_counts is not None
            and range_starts.size != range_counts.size
        ):
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
            packed = np.hstack((buffer.vertices, buffer.colors)).astype(np.float32, copy=False)
            glBindBuffer(GL_ARRAY_BUFFER, buffer.vbo)
            glBufferData(GL_ARRAY_BUFFER, packed.nbytes, packed, GL_STATIC_DRAW)
            buffer.dirty = False
        glBindBuffer(GL_ARRAY_BUFFER, buffer.vbo)
        stride = 7 * 4
        glEnableVertexAttribArray(self._position_loc)
        glEnableVertexAttribArray(self._color_loc)
        glUniform1f(self._depth_bias_loc, float(depth_bias))
        glVertexAttribPointer(self._position_loc, 3, GL_FLOAT, False, stride, ctypes.c_void_p(0))
        glVertexAttribPointer(self._color_loc, 4, GL_FLOAT, False, stride, ctypes.c_void_p(3 * 4))
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
                    for first, count in zip(buffer.draw_starts, buffer.draw_counts, strict=False):
                        glDrawArrays(buffer.primitive, int(first), int(count))
        else:
            glDrawArrays(buffer.primitive, 0, buffer.count)
        return 1

    def _scene_bounds(self) -> tuple[np.ndarray, np.ndarray] | None:
        points: list[np.ndarray] = []
        model_buffer = self._buffers.get("model")
        if model_buffer is not None and model_buffer.count:
            points.append(_transform_points(model_buffer.vertices, self._model_transform))
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
        direction = z_up_orbit_direction(self._yaw, self._pitch)
        eye = target + direction * self._distance
        return eye, target, self._view_up

    def _projection_matrix(self, width: int | None = None, height: int | None = None) -> np.ndarray:
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
