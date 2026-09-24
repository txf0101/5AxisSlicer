"""VTK Viewer implementation and runtime backend selection."""

from __future__ import annotations

import math
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import vtk
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QImage
from vtk.util.numpy_support import vtk_to_numpy
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

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
    SceneCaptureCapability,
    SelectionCallback,
    ViewerProtocol,
    apply_pick_selection,
    clamp_progress_index,
    current_progress_step,
    pick_request_for_mode,
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
from .viewer_interaction import BambuNavigationMixin, VtkCameraNavigation

_bead_frame = _viewer_common.bead_frame
_cross = _viewer_common.cross3
_dot = _viewer_common.dot3
_is_rigid_matrix = _viewer_common.is_rigid_transform
_normalize = _viewer_common.normalize3
_nozzle_axis_from_rotary = _viewer_common.nozzle_axis_from_rotary
_preview_pose_for_segment = _viewer_common.preview_pose_for_segment
_render_stride = _viewer_common.render_stride

__all__ = [
    "ModelViewer",
    "SceneCaptureCapability",
    "ViewerProtocol",
    "VtkModelViewer",
    "_bead_frame",
    "_cross",
    "_dot",
    "_is_rigid_matrix",
    "_normalize",
    "_nozzle_axis_from_rotary",
    "_preview_pose_for_segment",
    "_render_stride",
]

BG_COLOR = (0.969, 0.976, 0.988)
EDGE_COLOR = (0.31, 0.36, 0.43)
EDGE_PICK_COLOR = (0.39, 0.45, 0.54)
EDGE_SELECTED_COLOR = (0.145, 0.388, 0.922)
BODY_SELECTED_COLOR = (0.86, 0.90, 0.96)
BODY_SELECTED_EDGE_COLOR = (0.12, 0.16, 0.23)
POSE_SAMPLE_COLOR = (0.18, 0.78, 0.95)
EDGE_PICK_WIDTH = 2.6
EDGE_SELECTED_WIDTH = 5.0
BEAD_SECTION_SIDES = 8
STATIC_SOLID_SEGMENT_LIMIT = 400_000
INTERACTIVE_LINE_SEGMENT_LIMIT = 25_000
UPCOMING_OPACITY = 0.20
COMPLETED_OPACITY = 0.96
CURRENT_COLOR = (0.96, 0.39, 0.12)


@dataclass(slots=True)
class ActorRecord:
    kind: str
    object_id: str


class VtkModelViewer(BambuNavigationMixin, QVTKRenderWindowInteractor):
    backend = "vtk"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(*BG_COLOR)
        self.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = self.GetRenderWindow().GetInteractor()
        self._vtk_camera = VtkCameraNavigation(
            self.renderer, self, self._getPixelRatio, self.render
        )
        self._init_view_navigation(self._vtk_camera)

        self.model: CadModel | None = None
        self._model_visible = True
        self.selection = SelectionState()
        self.selection_callback: SelectionCallback | None = None
        self.pick_callback: PickCallback | None = None
        self.pick_request = PickRequest("edge", multiple=True)
        self.actor_records: dict[vtk.vtkActor, ActorRecord] = {}
        self.body_actors: dict[str, vtk.vtkActor] = {}
        self.face_actors: dict[str, vtk.vtkActor] = {}
        self.edge_actors: dict[str, vtk.vtkActor] = {}
        self.vertex_actors: dict[str, vtk.vtkActor] = {}
        self.edge_to_body: dict[str, str] = {}
        self.coordinate_actors: dict[str, vtk.vtkAxesActor] = {}
        self.build_surface_actor: vtk.vtkActor | None = None
        self._model_transform = np.eye(4, dtype=float)
        self.gcode_preview: GCodePreview | None = None
        self.preview_settings = PreviewSettings(render_backend=self.backend)
        self.path_actors: list[vtk.vtkActor] = []
        self.pose_actor: vtk.vtkActor | None = None
        self.visible_path_segment_count = 0
        self.drawn_path_segment_count = 0
        self.path_render_mode = "line"
        self.quality_mode = "interactive"
        self._interaction_preview = False
        self._progress_dragging = False
        self._last_progress_ms = 0.0

        self.picker = vtk.vtkCellPicker()
        self.picker.SetTolerance(0.006)

    def set_selection_callback(self, callback: SelectionCallback) -> None:
        self.selection_callback = callback

    def set_pick_callback(self, callback: PickCallback | None) -> None:
        self.pick_callback = callback

    def load_model(self, model: CadModel) -> None:
        self.model = model
        self.selection.clear()
        self.actor_records.clear()
        self.body_actors.clear()
        self.face_actors.clear()
        self.edge_actors.clear()
        self.vertex_actors.clear()
        self.edge_to_body.clear()
        self.coordinate_actors.clear()
        self.build_surface_actor = None
        self._model_transform = np.eye(4, dtype=float)
        self.path_actors.clear()
        self.pose_actor = None
        self.renderer.RemoveAllViewProps()

        for body in model.bodies:
            # 拾取模式只切换 pickable；同一 body actor 始终承载显示和高亮状态。
            polydata = shape_to_polydata(model.shapes[body.body_id])
            body.triangle_count = polydata.GetNumberOfPolys()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(polydata)
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*body.color)
            actor.GetProperty().SetOpacity(0.30 if self.gcode_preview is not None else 0.92)
            actor.GetProperty().SetSpecular(0.35)
            actor.GetProperty().SetSpecularPower(28)
            actor.GetProperty().SetInterpolationToPhong()
            self.renderer.AddActor(actor)
            self.body_actors[body.body_id] = actor
            self.actor_records[actor] = ActorRecord("body", body.body_id)

            for face_id in body.face_ids:
                face_polydata = shape_to_polydata(model.face_shapes[face_id])
                face_mapper = vtk.vtkPolyDataMapper()
                face_mapper.SetInputData(face_polydata)
                face_actor = vtk.vtkActor()
                face_actor.SetMapper(face_mapper)
                face_actor.GetProperty().SetColor(*body.color)
                face_actor.GetProperty().SetOpacity(0.92)
                face_actor.GetProperty().SetSpecular(0.25)
                face_actor.GetProperty().SetInterpolationToPhong()
                face_actor.SetVisibility(False)
                face_actor.SetPickable(False)
                self.renderer.AddActor(face_actor)
                self.face_actors[face_id] = face_actor
                self.actor_records[face_actor] = ActorRecord("face", face_id)

            for edge_id in body.edge_ids:
                # 独立 actor 保留 edge_id，VTK 命中后无需按单元序号反查拓扑。
                polyline = edge_to_polydata(model.edge_shapes[edge_id], segments=28)
                edge_mapper = vtk.vtkPolyDataMapper()
                edge_mapper.SetInputData(polyline)
                edge_actor = vtk.vtkActor()
                edge_actor.SetMapper(edge_mapper)
                edge_actor.GetProperty().SetColor(*EDGE_PICK_COLOR)
                edge_actor.GetProperty().SetLineWidth(2.0)
                edge_actor.GetProperty().SetOpacity(0.72)
                self.renderer.AddActor(edge_actor)
                self.edge_actors[edge_id] = edge_actor
                self.edge_to_body[edge_id] = body.body_id
                self.actor_records[edge_actor] = ActorRecord("edge", edge_id)

            point_radius = max((model.bounds.diagonal if model.bounds else 10.0) * 0.006, 0.15)
            for vertex_id in body.vertex_ids:
                vertex = model.vertex_map[vertex_id]
                source = vtk.vtkSphereSource()
                source.SetCenter(*vertex.point)
                source.SetRadius(point_radius)
                source.SetThetaResolution(10)
                source.SetPhiResolution(8)
                vertex_mapper = vtk.vtkPolyDataMapper()
                vertex_mapper.SetInputConnection(source.GetOutputPort())
                vertex_actor = vtk.vtkActor()
                vertex_actor.SetMapper(vertex_mapper)
                vertex_actor.GetProperty().SetColor(*EDGE_SELECTED_COLOR)
                vertex_actor.SetVisibility(False)
                vertex_actor.SetPickable(False)
                self.renderer.AddActor(vertex_actor)
                self.vertex_actors[vertex_id] = vertex_actor
                self.actor_records[vertex_actor] = ActorRecord("vertex", vertex_id)

        self.set_mode("edge")
        self.fit_view()
        self.refresh_selection()
        if self.gcode_preview is not None:
            self.refresh_path_preview()

    def load_gcode_preview(self, preview: GCodePreview) -> None:
        self.gcode_preview = preview
        self.preview_settings = preview_settings_for(preview, backend=self.backend)
        self.refresh_selection()
        self.refresh_path_preview()
        self.fit_view()

    def clear_gcode_preview(self) -> None:
        self.gcode_preview = None
        self._remove_path_actors()
        self.preview_settings = PreviewSettings(render_backend=self.backend)
        self.visible_path_segment_count = 0
        self.drawn_path_segment_count = 0
        self.path_render_mode = "line"
        self._interaction_preview = False
        self._progress_dragging = False
        self.refresh_selection()

    def set_preview_layers(self, layer_min: int, layer_max: int) -> None:
        if self.gcode_preview is None:
            return
        set_preview_layers(
            self.gcode_preview,
            self.preview_settings,
            layer_min,
            layer_max,
        )
        self.refresh_path_preview()

    def set_preview_line_range(self, line_min: int | None, line_max: int | None) -> None:
        self.preview_settings.line_min = line_min
        self.preview_settings.line_max = line_max
        if self.gcode_preview is not None:
            self.refresh_path_preview()

    def set_preview_progress(self, progress_index: int, interactive: bool | None = None) -> None:
        if self.gcode_preview is None:
            return
        started = time.perf_counter()
        if interactive is not None:
            self._progress_dragging = bool(interactive)
        self.preview_settings.progress_index = int(progress_index)
        self._clamp_progress_index()
        self.refresh_path_preview()
        self._last_progress_ms = (time.perf_counter() - started) * 1000.0

    def set_progress_interaction(self, active: bool) -> None:
        if self.gcode_preview is None:
            return
        self._progress_dragging = active
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
        if self.gcode_preview is not None:
            self.refresh_path_preview()

    def preview_state(self) -> dict:
        draw_count = len(self.path_actors) + len(self.body_actors) + len(self.edge_actors)
        return preview_state_payload(
            self.gcode_preview,
            self.preview_settings,
            backend=self.backend,
            visible_count=self.visible_path_segment_count,
            drawn_count=self.drawn_path_segment_count,
            render_mode=self.path_render_mode,
            frame_ms=0.0,
            gpu_draw_count=draw_count,
        )

    def performance_state(self) -> dict:
        return {
            "backend": self.backend,
            "quality_mode": self.preview_settings.quality_mode,
            "frame_ms_avg": 0.0,
            "frame_ms_max": 0.0,
            "fps_avg": 0.0,
            "progress_update_ms": self._last_progress_ms,
            "gpu_draw_count": len(self.path_actors) + len(self.body_actors) + len(self.edge_actors),
            "gpu_memory_estimate_mb": 0.0,
            "buffers": {},
        }

    def progress_state(self) -> dict:
        return progress_state(self.gcode_preview, self.preview_settings)

    def current_progress_step(self) -> GCodeTimelineStep | None:
        return current_progress_step(self.gcode_preview, self.preview_settings)

    def representative_path_segment(self) -> GCodePathSegment | None:
        return representative_path_segment(self.gcode_preview, self.preview_settings)

    def _clamp_progress_index(self) -> None:
        clamp_progress_index(self.gcode_preview, self.preview_settings)

    def refresh_path_preview(self) -> None:
        self._remove_path_actors()
        self.visible_path_segment_count = 0
        self.drawn_path_segment_count = 0
        if self.gcode_preview is None:
            self.path_render_mode = "line"
            self.render()
            return

        current_global_step = self.progress_state().get("current_global_step")
        interactive = self._interaction_preview or self._progress_dragging
        visible_segments = []
        for segment in self.gcode_preview.segments:
            if not self._segment_visible(segment) or not segment.has_spatial_length:
                continue
            if (
                current_global_step is not None
                and not self.preview_settings.show_upcoming
                and segment.step_index > current_global_step
            ):
                continue
            visible_segments.append(segment)
        self.visible_path_segment_count = len(visible_segments)
        if interactive or not self.preview_settings.solid_rendering:
            self.path_render_mode = "line_interactive" if interactive else "line"
            self._add_line_groups(visible_segments, current_global_step, interactive)
        else:
            self.path_render_mode = "solid"
            self._add_solid_groups(visible_segments, current_global_step)

        if self.preview_settings.show_pose_samples:
            self.pose_actor = self._make_pose_actor()
            if self.pose_actor is not None:
                self.renderer.AddActor(self.pose_actor)

        self.renderer.ResetCameraClippingRange()
        self.render()

    def clear_model(self) -> None:
        self.model = None
        self.selection.clear()
        for actor in (
            tuple(self.body_actors.values())
            + tuple(getattr(self, "face_actors", {}).values())
            + tuple(self.edge_actors.values())
            + tuple(getattr(self, "vertex_actors", {}).values())
        ):
            self.renderer.RemoveActor(actor)
        for actor in tuple(getattr(self, "coordinate_actors", {}).values()):
            self.renderer.RemoveActor(actor)
        build_surface_actor = getattr(self, "build_surface_actor", None)
        if build_surface_actor is not None:
            self.renderer.RemoveActor(build_surface_actor)
        self.actor_records.clear()
        self.body_actors.clear()
        if hasattr(self, "face_actors"):
            self.face_actors.clear()
        self.edge_actors.clear()
        if hasattr(self, "vertex_actors"):
            self.vertex_actors.clear()
        self.edge_to_body.clear()
        if hasattr(self, "coordinate_actors"):
            self.coordinate_actors.clear()
        if hasattr(self, "build_surface_actor"):
            self.build_surface_actor = None
        self.renderer.ResetCameraClippingRange()
        self.render()

    def set_mode(self, mode: str) -> None:
        request = pick_request_for_mode(mode)
        self.selection.mode = mode
        self.pick_request = request
        for actor in self.body_actors.values():
            actor.SetVisibility(self._model_visible and mode != "face")
            actor.SetPickable(self._model_visible and mode == "body")
        for actor in self.face_actors.values():
            actor.SetVisibility(self._model_visible and mode == "face")
            actor.SetPickable(self._model_visible and mode == "face")
        for actor in self.edge_actors.values():
            actor.SetVisibility(self._model_visible and mode != "face")
            actor.SetPickable(self._model_visible and mode == "edge")
            actor.GetProperty().SetLineWidth(EDGE_PICK_WIDTH)
            actor.GetProperty().SetOpacity(0.9 if mode == "edge" else 0.45)
        for actor in self.vertex_actors.values():
            actor.SetVisibility(self._model_visible and mode == "vertex")
            actor.SetPickable(self._model_visible and mode == "vertex")
        self.refresh_selection()

    def set_model_visible(self, visible: bool) -> None:
        self._model_visible = bool(visible)
        self.set_mode(self.selection.mode)

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
        path_overlay = self.gcode_preview is not None
        model = self.model
        for body_id, actor in self.body_actors.items():
            selected = body_id in self.selection.body_ids
            prop = actor.GetProperty()
            if selected:
                prop.SetColor(*BODY_SELECTED_COLOR)
                prop.SetEdgeVisibility(True)
                prop.SetEdgeColor(*BODY_SELECTED_EDGE_COLOR)
                prop.SetLineWidth(1.5)
            elif self.model:
                color = self.model.body_map[body_id].color
                prop.SetColor(*color)
                prop.SetEdgeVisibility(False)
            prop.SetOpacity(0.30 if path_overlay else 0.92)

        for face_id, actor in self.face_actors.items():
            selected = face_id in self.selection.face_ids
            prop = actor.GetProperty()
            color = (
                EDGE_SELECTED_COLOR
                if selected or model is None
                else model.body_map[model.face_map[face_id].body_id].color
            )
            prop.SetColor(*color)
            prop.SetOpacity(1.0 if selected else 0.92)

        for edge_id, actor in self.edge_actors.items():
            selected = edge_id in self.selection.edge_ids
            prop = actor.GetProperty()
            if selected:
                prop.SetColor(*EDGE_SELECTED_COLOR)
                prop.SetLineWidth(EDGE_SELECTED_WIDTH)
                prop.SetOpacity(1.0)
            else:
                prop.SetColor(*EDGE_COLOR)
                prop.SetLineWidth(EDGE_PICK_WIDTH if self.selection.mode == "edge" else 1.6)
                if path_overlay:
                    prop.SetOpacity(0.18)
                else:
                    prop.SetOpacity(0.9 if self.selection.mode == "edge" else 0.48)

        for vertex_id, actor in self.vertex_actors.items():
            selected = vertex_id in self.selection.vertex_ids
            actor.GetProperty().SetColor(*(CURRENT_COLOR if selected else EDGE_SELECTED_COLOR))
        self.render()

    def set_coordinate_frames(
        self,
        frames: Iterable[CoordinateFrameOverlay],
        active_frame_id: str | None = None,
    ) -> None:
        for actor in self.coordinate_actors.values():
            self.renderer.RemoveActor(actor)
        self.coordinate_actors.clear()
        for frame in frames:
            if not frame.visible:
                continue
            actor = vtk.vtkAxesActor()
            actor.SetShaftTypeToCylinder()
            actor.SetAxisLabels(True)
            actor.SetXAxisLabelText(f"{frame.name}:X")
            actor.SetYAxisLabelText(f"{frame.name}:Y")
            actor.SetZAxisLabelText(f"{frame.name}:Z")
            scale = float(frame.scale) * (1.18 if frame.frame_id == active_frame_id else 1.0)
            actor.SetTotalLength(scale, scale, scale)
            actor.SetCylinderRadius(0.018 if frame.frame_id == active_frame_id else 0.012)
            actor.SetConeRadius(0.08)
            actor.SetUserMatrix(
                _vtk_matrix_from_basis(frame.origin, frame.x_axis, frame.y_axis, frame.z_axis)
            )
            actor.SetPickable(False)
            self.renderer.AddActor(actor)
            self.coordinate_actors[frame.frame_id] = actor
        self.renderer.ResetCameraClippingRange()
        self.render()

    def set_build_surface(self, surface: BuildSurfaceOverlay | None) -> None:
        if self.build_surface_actor is not None:
            self.renderer.RemoveActor(self.build_surface_actor)
            self.build_surface_actor = None
        if surface is None:
            self.render()
            return
        local_points: list[tuple[float, float]]
        if surface.shape == "circle" and surface.diameter_mm is not None:
            radius = surface.diameter_mm * 0.5
            local_points = [
                (
                    radius * math.cos(2.0 * math.pi * index / 64),
                    radius * math.sin(2.0 * math.pi * index / 64),
                )
                for index in range(64)
            ]
        else:
            width = float(surface.width_mm or 100.0)
            depth = float(surface.depth_mm or width)
            local_points = [
                (-width * 0.5, -depth * 0.5),
                (width * 0.5, -depth * 0.5),
                (width * 0.5, depth * 0.5),
                (-width * 0.5, depth * 0.5),
            ]
        points = vtk.vtkPoints()
        for left, up in local_points:
            points.InsertNextPoint(
                *tuple(
                    surface.origin[index]
                    + left * surface.x_axis[index]
                    + up * surface.y_axis[index]
                    for index in range(3)
                )
            )
        line = vtk.vtkPolyLine()
        line.GetPointIds().SetNumberOfIds(len(local_points) + 1)
        for index in range(len(local_points)):
            line.GetPointIds().SetId(index, index)
        line.GetPointIds().SetId(len(local_points), 0)
        cells = vtk.vtkCellArray()
        cells.InsertNextCell(line)
        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetLines(cells)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(0.42, 0.48, 0.58)
        actor.GetProperty().SetLineWidth(2.0)
        actor.GetProperty().SetOpacity(0.75)
        actor.SetPickable(False)
        self.renderer.AddActor(actor)
        self.build_surface_actor = actor
        self.render()

    def set_model_transform(self, matrix: Iterable[Iterable[float]]) -> None:
        values = np.asarray(tuple(tuple(row) for row in matrix), dtype=float)
        if not _is_rigid_matrix(values):
            raise ValueError("model transform must be a finite right-handed rigid 4x4 matrix")
        self._model_transform = values
        vtk_matrix = _vtk_matrix(values)
        for actor in (
            tuple(self.body_actors.values())
            + tuple(self.face_actors.values())
            + tuple(self.edge_actors.values())
            + tuple(self.vertex_actors.values())
        ):
            actor.SetUserMatrix(vtk_matrix)
        self.renderer.ResetCameraClippingRange()
        self.render()

    def fit_view(self) -> None:
        self.renderer.ResetCamera()
        self.render()

    def home_view(self) -> None:
        camera = self.renderer.GetActiveCamera()
        self.renderer.ResetCamera()
        camera.Azimuth(35)
        camera.Elevation(25)
        camera.OrthogonalizeViewUp()
        self.renderer.ResetCameraClippingRange()
        self.render()

    def set_quality_mode(self, mode: str) -> None:
        if mode not in {"interactive", "paper"}:
            raise ValueError(f"Unknown quality mode: {mode}")
        self.quality_mode = mode
        self.preview_settings.quality_mode = mode
        self.preview_settings.solid_rendering = mode == "interactive"
        self.refresh_path_preview()

    def set_standard_view(self, view: str) -> None:
        view = str(view).lower()
        if view in {"home", "isometric", "iso"}:
            self.home_view()
            return
        directions = {
            "front": ((0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
            "back": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            "left": ((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            "right": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            "top": ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
            "bottom": ((0.0, 0.0, -1.0), (0.0, 1.0, 0.0)),
        }
        if view not in directions:
            raise ValueError(f"Unknown standard view: {view}")
        self.renderer.ResetCamera()
        camera = self.renderer.GetActiveCamera()
        focal = camera.GetFocalPoint()
        distance = max(camera.GetDistance(), 1.0)
        direction, up = directions[view]
        camera.SetPosition(*(focal[index] + direction[index] * distance for index in range(3)))
        camera.SetViewUp(*up)
        camera.OrthogonalizeViewUp()
        self.renderer.ResetCameraClippingRange()
        self.render()

    def camera_state(self) -> dict[str, object]:
        camera = self.renderer.GetActiveCamera()
        return {
            "position": list(camera.GetPosition()),
            "focal_point": list(camera.GetFocalPoint()),
            "view_up": list(camera.GetViewUp()),
            "parallel_scale": float(camera.GetParallelScale()),
            "view_angle": float(camera.GetViewAngle()),
        }

    def capabilities(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "offscreen_capture": True,
        }

    def render_scene_image(self, width: int, height: int) -> QImage:
        width = max(1, int(width))
        height = max(1, int(height))
        render_window = self.GetRenderWindow()
        old_size = render_window.GetSize()
        render_window.SetSize(width, height)
        self.renderer.ResetCameraClippingRange()
        render_window.Render()
        capture = vtk.vtkWindowToImageFilter()
        capture.SetInput(render_window)
        capture.SetInputBufferTypeToRGBA()
        capture.ReadFrontBufferOff()
        capture.Update()
        writer = vtk.vtkPNGWriter()
        writer.SetWriteToMemory(True)
        writer.SetInputConnection(capture.GetOutputPort())
        writer.Write()
        payload = vtk_to_numpy(writer.GetResult()).tobytes()
        image = QImage.fromData(payload, "PNG")
        render_window.SetSize(*old_size)
        render_window.Render()
        return image

    def camera_command(self, command: str, value: float = 10.0) -> None:
        camera = self.renderer.GetActiveCamera()
        if command == "fit":
            self.fit_view()
            return
        if command == "home":
            self.home_view()
            return
        if command == "azimuth":
            camera.Azimuth(value)
        elif command == "elevation":
            camera.Elevation(value)
        elif command == "zoom":
            camera.Zoom(value)
        elif command == "pan":
            self._pan(value, 0.0)
        elif command == "pan_y":
            self._pan(0.0, value)
        else:
            raise ValueError(f"Unknown camera command: {command}")
        camera.OrthogonalizeViewUp()
        self.renderer.ResetCameraClippingRange()
        self.render()

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

    def _view_left_click(self, pos: QPoint) -> None:
        x, y = self._vtk_camera.display_point(pos)
        self.picker.Pick(x, y, 0, self.renderer)
        actor = self.picker.GetActor()
        record = self.actor_records.get(actor)
        request = self.pick_request
        allowed = (
            record is not None
            and record.kind == request.kind
            and (request.allowed_ids is None or record.object_id in request.allowed_ids)
        )
        if not allowed or record is None:
            self.clear_selection()
            if self.selection_callback is not None:
                self.selection_callback(None, None)
            return

        self._apply_pick(record.kind, record.object_id)
        position = np.asarray(self.picker.GetPickPosition(), dtype=float)
        position_source: tuple[float, float, float] | None = None
        if position.shape == (3,) and np.isfinite(position).all():
            homogeneous = np.append(position, 1.0)
            position_source = vector3((np.linalg.inv(self._model_transform) @ homogeneous)[:3])
        if self.pick_callback is not None:
            self.pick_callback(PickHit(record.kind, record.object_id, position_source))

    def _view_interaction_started(self) -> None:
        if self.gcode_preview is None or self._interaction_preview:
            return
        self._interaction_preview = True
        self.refresh_path_preview()

    def _view_interaction_finished(self) -> None:
        if self.gcode_preview is None or not self._interaction_preview:
            return
        self._interaction_preview = False
        self.refresh_path_preview()

    def _apply_pick(self, kind: str, entity_id: str) -> None:
        if not apply_pick_selection(
            self.selection,
            self.pick_request,
            kind,
            entity_id,
        ):
            return
        self.refresh_selection()
        if self.selection_callback:
            self.selection_callback(kind, entity_id)

    def _toggle_edge(self, edge_id: str) -> None:
        """Keep the legacy edge toggle hook used by older integrations."""
        previous = self.pick_request
        self.pick_request = PickRequest("edge", multiple=True)
        try:
            self._apply_pick("edge", edge_id)
        finally:
            self.pick_request = previous

    def _pan(self, dx: float, dy: float) -> None:
        camera = self.renderer.GetActiveCamera()
        focal = camera.GetFocalPoint()
        position = camera.GetPosition()
        scale = max(camera.GetDistance(), 1.0)
        offset = (dx * scale, dy * scale, 0.0)
        camera.SetFocalPoint(focal[0] + offset[0], focal[1] + offset[1], focal[2] + offset[2])
        camera.SetPosition(
            position[0] + offset[0], position[1] + offset[1], position[2] + offset[2]
        )

    def _remove_path_actors(self) -> None:
        for actor in self.path_actors:
            self.renderer.RemoveActor(actor)
        self.path_actors.clear()
        if self.pose_actor is not None:
            self.renderer.RemoveActor(self.pose_actor)
            self.pose_actor = None

    def _segment_visible(self, segment) -> bool:
        return segment_visible(segment, self.preview_settings)

    def _segment_phase(self, segment: GCodePathSegment, current_global_step: int | None) -> str:
        if current_global_step is None:
            return "completed"
        if segment.step_index == current_global_step:
            return "current"
        if segment.step_index < current_global_step:
            return "completed"
        return "upcoming"

    def _add_line_groups(
        self,
        segments: list[GCodePathSegment],
        current_global_step: int | None,
        interactive: bool,
    ) -> None:
        stride = _render_stride(
            len(segments),
            (INTERACTIVE_LINE_SEGMENT_LIMIT if interactive else STATIC_SOLID_SEGMENT_LIMIT),
        )
        grouped: dict[
            tuple[str, str],
            tuple[
                tuple[float, float, float],
                list[tuple[tuple[float, float, float], tuple[float, float, float], str]],
            ],
        ] = {}
        current_lines: list[tuple[tuple[float, float, float], tuple[float, float, float], str]] = []
        for index, segment in enumerate(segments):
            phase = self._segment_phase(segment, current_global_step)
            if phase == "current":
                current_lines.append((segment.start, segment.end, segment.move_type))
                continue
            if stride > 1 and index % stride != 0:
                continue
            color_key = segment.color_key()
            grouped.setdefault((color_key, phase), (segment.color(), []))[1].append(
                (segment.start, segment.end, segment.move_type)
            )
            self.drawn_path_segment_count += 1

        for (_color_key, phase), (color, lines) in grouped.items():
            actor = self._make_line_actor(
                lines,
                color,
                self._opacity_for_phase(
                    phase, has_extrusion=any(line[2] == "extrude" for line in lines)
                ),
            )
            self.renderer.AddActor(actor)
            self.path_actors.append(actor)
        if current_lines:
            actor = self._make_line_actor(current_lines, CURRENT_COLOR, 1.0)
            actor.GetProperty().SetLineWidth(4.0)
            self.renderer.AddActor(actor)
            self.path_actors.append(actor)
            self.drawn_path_segment_count += len(current_lines)

    def _add_solid_groups(
        self, segments: list[GCodePathSegment], current_global_step: int | None
    ) -> None:
        stride = _render_stride(len(segments), STATIC_SOLID_SEGMENT_LIMIT)
        if stride > 1:
            self.path_render_mode = f"solid_adaptive_{stride}"
        solid_groups: dict[
            tuple[str, str], tuple[tuple[float, float, float], list[GCodePathSegment]]
        ] = {}
        line_groups: dict[
            tuple[str, str],
            tuple[
                tuple[float, float, float],
                list[tuple[tuple[float, float, float], tuple[float, float, float], str]],
            ],
        ] = {}
        current_segments: list[GCodePathSegment] = []
        current_lines: list[tuple[tuple[float, float, float], tuple[float, float, float], str]] = []

        for index, segment in enumerate(segments):
            phase = self._segment_phase(segment, current_global_step)
            if phase == "current":
                if segment.move_type == "extrude":
                    current_segments.append(segment)
                else:
                    current_lines.append((segment.start, segment.end, segment.move_type))
                continue
            if stride > 1 and index % stride != 0:
                continue
            if segment.move_type == "extrude":
                solid_groups.setdefault((segment.color_key(), phase), (segment.color(), []))[
                    1
                ].append(segment)
            else:
                line_groups.setdefault((segment.color_key(), phase), (segment.color(), []))[
                    1
                ].append((segment.start, segment.end, segment.move_type))
            self.drawn_path_segment_count += 1

        for (_color_key, phase), (color, group_segments) in solid_groups.items():
            actor = self._make_bead_actor(
                group_segments,
                color,
                self._opacity_for_phase(phase, has_extrusion=True),
            )
            self.renderer.AddActor(actor)
            self.path_actors.append(actor)
        for (_color_key, phase), (color, lines) in line_groups.items():
            actor = self._make_line_actor(
                lines, color, self._opacity_for_phase(phase, has_extrusion=False)
            )
            self.renderer.AddActor(actor)
            self.path_actors.append(actor)
        if current_segments:
            actor = self._make_bead_actor(current_segments, CURRENT_COLOR, 1.0)
            self.renderer.AddActor(actor)
            self.path_actors.append(actor)
            self.drawn_path_segment_count += len(current_segments)
        if current_lines:
            actor = self._make_line_actor(current_lines, CURRENT_COLOR, 1.0)
            actor.GetProperty().SetLineWidth(4.0)
            self.renderer.AddActor(actor)
            self.path_actors.append(actor)
            self.drawn_path_segment_count += len(current_lines)

    def _opacity_for_phase(self, phase: str, has_extrusion: bool) -> float:
        if phase == "upcoming":
            return UPCOMING_OPACITY if has_extrusion else 0.16
        if phase == "current":
            return 1.0
        return COMPLETED_OPACITY if has_extrusion else 0.50

    def _make_line_actor(
        self,
        lines: list[tuple[tuple[float, float, float], tuple[float, float, float], str]],
        color: tuple[float, float, float],
        opacity: float | None = None,
    ) -> vtk.vtkActor:
        points = vtk.vtkPoints()
        cells = vtk.vtkCellArray()
        has_extrusion = any(move_type == "extrude" for _, _, move_type in lines)
        for start, end, _move_type in lines:
            left = points.InsertNextPoint(*start)
            right = points.InsertNextPoint(*end)
            line = vtk.vtkLine()
            line.GetPointIds().SetId(0, left)
            line.GetPointIds().SetId(1, right)
            cells.InsertNextCell(line)
        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetLines(cells)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*color)
        actor.GetProperty().SetLineWidth(2.6 if has_extrusion else 1.5)
        actor.GetProperty().SetOpacity(
            opacity if opacity is not None else (0.95 if has_extrusion else 0.48)
        )
        actor.SetPickable(False)
        return actor

    def _make_bead_actor(
        self,
        segments: list[GCodePathSegment],
        color: tuple[float, float, float],
        opacity: float,
    ) -> vtk.vtkActor:
        points = vtk.vtkPoints()
        points.SetDataTypeToFloat()
        quads = vtk.vtkCellArray()
        controller_semantics = (
            self.gcode_preview.controller_semantics if self.gcode_preview is not None else None
        )
        for segment in segments:
            frame = _bead_frame(
                segment.start,
                segment.end,
                segment.rotary_end,
                controller_semantics=controller_semantics,
                coordinate_transform=segment.coordinate_transform,
            )
            if frame is None:
                continue
            tangent, width_axis, height_axis = frame
            del tangent
            width_radius = max(segment.bead_width, 1e-6) * 0.5
            height_radius = max(segment.bead_height, 1e-6) * 0.5
            start_ids: list[int] = []
            end_ids: list[int] = []
            for side in range(BEAD_SECTION_SIDES):
                angle = 2.0 * math.pi * side / BEAD_SECTION_SIDES
                offset = tuple(
                    math.cos(angle) * width_radius * width_axis[index]
                    + math.sin(angle) * height_radius * height_axis[index]
                    for index in range(3)
                )
                start_ids.append(
                    points.InsertNextPoint(
                        *(segment.start[index] + offset[index] for index in range(3))
                    )
                )
                end_ids.append(
                    points.InsertNextPoint(
                        *(segment.end[index] + offset[index] for index in range(3))
                    )
                )
            for side in range(BEAD_SECTION_SIDES):
                next_side = (side + 1) % BEAD_SECTION_SIDES
                quad = vtk.vtkQuad()
                quad.GetPointIds().SetId(0, start_ids[side])
                quad.GetPointIds().SetId(1, start_ids[next_side])
                quad.GetPointIds().SetId(2, end_ids[next_side])
                quad.GetPointIds().SetId(3, end_ids[side])
                quads.InsertNextCell(quad)

        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetPolys(quads)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(*color)
        prop.SetOpacity(opacity)
        prop.SetSpecular(0.18)
        prop.SetSpecularPower(16)
        prop.SetInterpolationToPhong()
        actor.SetPickable(False)
        return actor

    def _make_pose_actor(self) -> vtk.vtkActor | None:
        if self.gcode_preview is None:
            return None
        candidates = [
            segment
            for segment in self.gcode_preview.segments
            if segment.move_type == "extrude"
            and segment.has_spatial_length
            and (segment.rotary_end or segment.rotary_start)
            and self._segment_visible(segment)
        ]
        if not candidates:
            return None

        step = max(1, len(candidates) // 120)
        bounds = self.gcode_preview.bounds
        length = 4.0
        if bounds is not None:
            diag = math.dist(bounds[0], bounds[1])
            length = max(2.0, min(12.0, diag * 0.035))

        points = vtk.vtkPoints()
        cells = vtk.vtkCellArray()
        for segment in candidates[::step]:
            start, axis = _preview_pose_for_segment(
                segment,
                controller_semantics=self.gcode_preview.controller_semantics,
            )
            end = tuple(start[i] + axis[i] * length for i in range(3))
            left = points.InsertNextPoint(*start)
            right = points.InsertNextPoint(*end)
            line = vtk.vtkLine()
            line.GetPointIds().SetId(0, left)
            line.GetPointIds().SetId(1, right)
            cells.InsertNextCell(line)

        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetLines(cells)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*POSE_SAMPLE_COLOR)
        actor.GetProperty().SetLineWidth(1.2)
        actor.GetProperty().SetOpacity(0.55)
        actor.SetPickable(False)
        return actor

    def render(self) -> None:
        self.GetRenderWindow().Render()


def _vtk_matrix(values: Iterable[Iterable[float]]) -> vtk.vtkMatrix4x4:
    array = np.asarray(tuple(tuple(row) for row in values), dtype=float)
    if array.shape != (4, 4) or not np.isfinite(array).all():
        raise ValueError("VTK transform must be a finite 4x4 matrix")
    matrix = vtk.vtkMatrix4x4()
    for row in range(4):
        for column in range(4):
            matrix.SetElement(row, column, float(array[row, column]))
    return matrix


def _vtk_matrix_from_basis(
    origin: tuple[float, float, float],
    x_axis: tuple[float, float, float],
    y_axis: tuple[float, float, float],
    z_axis: tuple[float, float, float],
) -> vtk.vtkMatrix4x4:
    values = np.eye(4, dtype=float)
    values[:3, 0] = x_axis
    values[:3, 1] = y_axis
    values[:3, 2] = z_axis
    values[:3, 3] = origin
    if not _is_rigid_matrix(values, tolerance=1e-6):
        raise ValueError("coordinate frame overlay must define a right-handed orthonormal basis")
    return _vtk_matrix(values)


def _select_model_viewer_class():
    requested = os.environ.get("FIVE_AXIS_RENDER_BACKEND", "opengl").lower()
    if requested == "vtk" or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        return VtkModelViewer
    try:
        from .opengl_viewer import OPENGL_AVAILABLE, OpenGLModelViewer

        if OPENGL_AVAILABLE:
            return OpenGLModelViewer
    except Exception:
        return VtkModelViewer
    return VtkModelViewer


ModelViewer = _select_model_viewer_class()
