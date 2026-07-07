from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from PyQt5.QtCore import Qt
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk

from .geometry_vtk import edge_to_polydata, shape_to_polydata
from .gcode_preview import GCodePathSegment, GCodePreview, GCodeTimelineStep, PreviewSettings
from .models import CadModel, SelectionState


SelectionCallback = Callable[[str, str], None]

BG_COLOR = (0.08, 0.085, 0.09)
EDGE_COLOR = (0.10, 0.10, 0.10)
EDGE_PICK_COLOR = (0.12, 0.12, 0.12)
EDGE_SELECTED_COLOR = (1.0, 0.92, 0.42)
BODY_SELECTED_COLOR = (0.98, 0.98, 0.98)
BODY_SELECTED_EDGE_COLOR = (0.05, 0.05, 0.05)
POSE_SAMPLE_COLOR = (0.18, 0.78, 0.95)
EDGE_PICK_WIDTH = 2.6
EDGE_SELECTED_WIDTH = 5.0
BEAD_SECTION_SIDES = 8
STATIC_SOLID_SEGMENT_LIMIT = 400_000
INTERACTIVE_LINE_SEGMENT_LIMIT = 25_000
UPCOMING_OPACITY = 0.20
COMPLETED_OPACITY = 0.96
CURRENT_COLOR = (1.0, 1.0, 1.0)


@dataclass(slots=True)
class ActorRecord:
    kind: str
    object_id: str


class ModelViewer(QVTKRenderWindowInteractor):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(*BG_COLOR)
        self.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = self.GetRenderWindow().GetInteractor()
        self.interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())

        self.model: CadModel | None = None
        self.selection = SelectionState()
        self.selection_callback: SelectionCallback | None = None
        self.actor_records: dict[vtk.vtkActor, ActorRecord] = {}
        self.body_actors: dict[str, vtk.vtkActor] = {}
        self.edge_actors: dict[str, vtk.vtkActor] = {}
        self.edge_to_body: dict[str, str] = {}
        self.gcode_preview: GCodePreview | None = None
        self.preview_settings = PreviewSettings()
        self.path_actors: list[vtk.vtkActor] = []
        self.pose_actor: vtk.vtkActor | None = None
        self.visible_path_segment_count = 0
        self.drawn_path_segment_count = 0
        self.path_render_mode = "line"
        self._interaction_preview = False
        self._progress_dragging = False

        self.picker = vtk.vtkCellPicker()
        self.picker.SetTolerance(0.006)
        self.interactor.AddObserver("LeftButtonPressEvent", self._on_left_button)
        self.interactor.AddObserver("StartInteractionEvent", self._on_interaction_start)
        self.interactor.AddObserver("EndInteractionEvent", self._on_interaction_end)

    def set_selection_callback(self, callback: SelectionCallback) -> None:
        self.selection_callback = callback

    def load_model(self, model: CadModel) -> None:
        self.model = model
        self.selection.clear()
        self.actor_records.clear()
        self.body_actors.clear()
        self.edge_actors.clear()
        self.edge_to_body.clear()
        self.path_actors.clear()
        self.pose_actor = None
        self.renderer.RemoveAllViewProps()

        for body in model.bodies:
            # body 用面片 actor 承载外观和高亮；点选权交给右侧列表，
            # 因此 actor 仍可显示，但在 set_mode("edge") 中会关闭 pickable。
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

            for edge_id in body.edge_ids:
                # edge 保持独立 actor，点击命中后可直接回到 edge_id。
                # 这种结构比合并成大 polydata 更直观，适合当前模型规模。
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

        self.set_mode("edge")
        self.fit_view()
        self.refresh_selection()
        if self.gcode_preview is not None:
            self.refresh_path_preview()

    def load_gcode_preview(self, preview: GCodePreview) -> None:
        self.gcode_preview = preview
        self.preview_settings = PreviewSettings(
            layer_min=preview.layer_min,
            layer_max=preview.layer_max,
            show_travel=False,
            show_extrusion=True,
            show_pose_samples=False,
        )
        self.preview_settings.progress_index = max(
            0,
            preview.timeline_count_for_layers(preview.layer_min, preview.layer_max) - 1,
        )
        self.refresh_selection()
        self.refresh_path_preview()
        self.fit_view()

    def clear_gcode_preview(self) -> None:
        self.gcode_preview = None
        self._remove_path_actors()
        self.refresh_selection()

    def set_preview_layers(self, layer_min: int, layer_max: int) -> None:
        if self.gcode_preview is None:
            return
        low = max(self.gcode_preview.layer_min, min(layer_min, layer_max))
        high = min(self.gcode_preview.layer_max, max(layer_min, layer_max))
        self.preview_settings.layer_min = low
        self.preview_settings.layer_max = high
        self._clamp_progress_index()
        self.refresh_path_preview()

    def set_preview_progress(self, progress_index: int, interactive: bool | None = None) -> None:
        if self.gcode_preview is None:
            return
        if interactive is not None:
            self._progress_dragging = bool(interactive)
        self.preview_settings.progress_index = int(progress_index)
        self._clamp_progress_index()
        self.refresh_path_preview()

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
        if show_travel is not None:
            self.preview_settings.show_travel = bool(show_travel)
        if show_extrusion is not None:
            self.preview_settings.show_extrusion = bool(show_extrusion)
        if visible_roles is not None:
            self.preview_settings.visible_roles = set(visible_roles)
        if show_pose_samples is not None:
            self.preview_settings.show_pose_samples = bool(show_pose_samples)
        if self.gcode_preview is not None:
            self.refresh_path_preview()

    def preview_state(self) -> dict:
        return {
            "summary": None if self.gcode_preview is None else self.gcode_preview.summary(),
            "settings": self.preview_settings.to_json(),
            "visible_path_segment_count": self.visible_path_segment_count,
            "drawn_path_segment_count": self.drawn_path_segment_count,
            "render_mode": self.path_render_mode,
            "progress": self.progress_state(),
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
        current_step = self.current_progress_step()
        if current_step is not None and current_step.path_segment_index is not None:
            if 0 <= current_step.path_segment_index < len(self.gcode_preview.segments):
                return self.gcode_preview.segments[current_step.path_segment_index]
        visible = [segment for segment in self.gcode_preview.segments if self._segment_visible(segment)]
        spatial = [segment for segment in visible if segment.has_spatial_length]
        extrusions = [segment for segment in spatial if segment.move_type == "extrude"]
        if extrusions:
            return extrusions[0]
        if spatial:
            return spatial[0]
        return visible[0] if visible else None

    def _clamp_progress_index(self) -> None:
        if self.gcode_preview is None:
            self.preview_settings.progress_index = 0
            return
        count = self.gcode_preview.timeline_count_for_layers(
            self.preview_settings.layer_min,
            self.preview_settings.layer_max,
        )
        self.preview_settings.progress_index = 0 if count == 0 else max(0, min(self.preview_settings.progress_index, count - 1))

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

    def set_mode(self, mode: str) -> None:
        if mode != "edge":
            raise ValueError(
                "Preview picking is fixed to edge mode; select bodies from the body list or /selection/set."
            )
        self.selection.mode = "edge"
        for actor in self.body_actors.values():
            actor.SetPickable(False)
        for actor in self.edge_actors.values():
            actor.SetPickable(True)
            actor.GetProperty().SetLineWidth(EDGE_PICK_WIDTH)
            actor.GetProperty().SetOpacity(0.9)
        self.render()

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
        path_overlay = self.gcode_preview is not None
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

    def _on_left_button(self, obj, event) -> None:
        x, y = self.interactor.GetEventPosition()
        self.picker.Pick(x, y, 0, self.renderer)
        actor = self.picker.GetActor()
        record = self.actor_records.get(actor)
        # 预览区固定承担 edge 点选；body 即使命中也不修改状态。
        if record is not None and record.kind == "edge":
            self._toggle_edge(record.object_id)
        self.interactor.GetInteractorStyle().OnLeftButtonDown()

    def _on_interaction_start(self, _obj, _event) -> None:
        if self.gcode_preview is None or self._interaction_preview:
            return
        self._interaction_preview = True
        self.refresh_path_preview()

    def _on_interaction_end(self, _obj, _event) -> None:
        if self.gcode_preview is None or not self._interaction_preview:
            return
        self._interaction_preview = False
        self.refresh_path_preview()

    def _toggle_edge(self, edge_id: str) -> None:
        if edge_id in self.selection.edge_ids:
            self.selection.edge_ids.remove(edge_id)
        else:
            self.selection.edge_ids.add(edge_id)
        self.refresh_selection()
        if self.selection_callback:
            self.selection_callback("edge", edge_id)

    def _pan(self, dx: float, dy: float) -> None:
        camera = self.renderer.GetActiveCamera()
        focal = camera.GetFocalPoint()
        position = camera.GetPosition()
        scale = max(camera.GetDistance(), 1.0)
        offset = (dx * scale, dy * scale, 0.0)
        camera.SetFocalPoint(focal[0] + offset[0], focal[1] + offset[1], focal[2] + offset[2])
        camera.SetPosition(position[0] + offset[0], position[1] + offset[1], position[2] + offset[2])

    def _remove_path_actors(self) -> None:
        for actor in self.path_actors:
            self.renderer.RemoveActor(actor)
        self.path_actors.clear()
        if self.pose_actor is not None:
            self.renderer.RemoveActor(self.pose_actor)
            self.pose_actor = None

    def _segment_visible(self, segment) -> bool:
        settings = self.preview_settings
        if segment.layer < settings.layer_min or segment.layer > settings.layer_max:
            return False
        if segment.move_type == "extrude":
            return settings.show_extrusion and segment.extrusion_role in settings.visible_roles
        if segment.move_type == "travel":
            return settings.show_travel
        return settings.show_travel and segment.has_spatial_length

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
        stride = _render_stride(len(segments), INTERACTIVE_LINE_SEGMENT_LIMIT if interactive else STATIC_SOLID_SEGMENT_LIMIT)
        grouped: dict[
            tuple[str, str],
            tuple[tuple[float, float, float], list[tuple[tuple[float, float, float], tuple[float, float, float], str]]],
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
            grouped.setdefault((color_key, phase), (segment.color(), []))[1].append((segment.start, segment.end, segment.move_type))
            self.drawn_path_segment_count += 1

        for (_color_key, phase), (color, lines) in grouped.items():
            actor = self._make_line_actor(lines, color, self._opacity_for_phase(phase, has_extrusion=any(line[2] == "extrude" for line in lines)))
            self.renderer.AddActor(actor)
            self.path_actors.append(actor)
        if current_lines:
            actor = self._make_line_actor(current_lines, CURRENT_COLOR, 1.0)
            actor.GetProperty().SetLineWidth(4.0)
            self.renderer.AddActor(actor)
            self.path_actors.append(actor)
            self.drawn_path_segment_count += len(current_lines)

    def _add_solid_groups(self, segments: list[GCodePathSegment], current_global_step: int | None) -> None:
        stride = _render_stride(len(segments), STATIC_SOLID_SEGMENT_LIMIT)
        if stride > 1:
            self.path_render_mode = f"solid_adaptive_{stride}"
        solid_groups: dict[tuple[str, str], tuple[tuple[float, float, float], list[GCodePathSegment]]] = {}
        line_groups: dict[
            tuple[str, str],
            tuple[tuple[float, float, float], list[tuple[tuple[float, float, float], tuple[float, float, float], str]]],
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
                solid_groups.setdefault((segment.color_key(), phase), (segment.color(), []))[1].append(segment)
            else:
                line_groups.setdefault((segment.color_key(), phase), (segment.color(), []))[1].append((segment.start, segment.end, segment.move_type))
            self.drawn_path_segment_count += 1

        for (_color_key, phase), (color, group_segments) in solid_groups.items():
            actor = self._make_bead_actor(group_segments, color, self._opacity_for_phase(phase, has_extrusion=True))
            self.renderer.AddActor(actor)
            self.path_actors.append(actor)
        for (_color_key, phase), (color, lines) in line_groups.items():
            actor = self._make_line_actor(lines, color, self._opacity_for_phase(phase, has_extrusion=False))
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
        actor.GetProperty().SetOpacity(opacity if opacity is not None else (0.95 if has_extrusion else 0.48))
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
        for segment in segments:
            frame = _bead_frame(segment.start, segment.end, segment.rotary_end or segment.rotary_start)
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
                start_ids.append(points.InsertNextPoint(*(segment.start[index] + offset[index] for index in range(3))))
                end_ids.append(points.InsertNextPoint(*(segment.end[index] + offset[index] for index in range(3))))
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
            axis = _nozzle_axis_from_rotary(segment.rotary_end or segment.rotary_start)
            start = segment.end
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


def _nozzle_axis_from_rotary(rotary: dict[str, float]) -> tuple[float, float, float]:
    vector = (0.0, 0.0, -1.0)
    vector = _rotate_x(vector, math.radians(rotary.get("A", rotary.get("U", 0.0))))
    vector = _rotate_y(vector, math.radians(rotary.get("B", rotary.get("V", 0.0))))
    vector = _rotate_z(vector, math.radians(rotary.get("C", 0.0)))
    return vector


def _bead_frame(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    rotary: dict[str, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]] | None:
    tangent = _normalize(tuple(end[index] - start[index] for index in range(3)))
    if tangent is None:
        return None
    nozzle = _normalize(_nozzle_axis_from_rotary(rotary)) or (0.0, 0.0, -1.0)
    width_axis = _normalize(_cross(nozzle, tangent))
    if width_axis is None:
        width_axis = _normalize(_cross((0.0, 0.0, 1.0), tangent))
    if width_axis is None:
        width_axis = _normalize(_cross((1.0, 0.0, 0.0), tangent))
    if width_axis is None:
        return None
    height_axis = _normalize(_cross(tangent, width_axis))
    if height_axis is None:
        return None
    if _dot(height_axis, nozzle) < 0:
        height_axis = tuple(-value for value in height_axis)
    return tangent, width_axis, height_axis


def _render_stride(count: int, limit: int) -> int:
    if count <= 0 or limit <= 0:
        return 1
    return max(1, math.ceil(count / limit))


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float] | None:
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-12:
        return None
    return tuple(value / length for value in vector)


def _cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _dot(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return sum(left[index] * right[index] for index in range(3))


def _rotate_x(vector: tuple[float, float, float], angle: float) -> tuple[float, float, float]:
    x, y, z = vector
    c = math.cos(angle)
    s = math.sin(angle)
    return x, y * c - z * s, y * s + z * c


def _rotate_y(vector: tuple[float, float, float], angle: float) -> tuple[float, float, float]:
    x, y, z = vector
    c = math.cos(angle)
    s = math.sin(angle)
    return x * c + z * s, y, -x * s + z * c


def _rotate_z(vector: tuple[float, float, float], angle: float) -> tuple[float, float, float]:
    x, y, z = vector
    c = math.cos(angle)
    s = math.sin(angle)
    return x * c - y * s, x * s + y * c, z
