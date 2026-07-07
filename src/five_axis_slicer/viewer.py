from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from PyQt5.QtCore import Qt
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk

from .geometry_vtk import edge_to_polydata, shape_to_polydata
from .gcode_preview import GCodePreview, PreviewSettings
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

        self.picker = vtk.vtkCellPicker()
        self.picker.SetTolerance(0.006)
        self.interactor.AddObserver("LeftButtonPressEvent", self._on_left_button)

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
        }

    def representative_path_segment(self):
        if self.gcode_preview is None:
            return None
        visible = [segment for segment in self.gcode_preview.segments if self._segment_visible(segment)]
        spatial = [segment for segment in visible if segment.has_spatial_length]
        extrusions = [segment for segment in spatial if segment.move_type == "extrude"]
        if extrusions:
            return extrusions[0]
        if spatial:
            return spatial[0]
        return visible[0] if visible else None

    def refresh_path_preview(self) -> None:
        self._remove_path_actors()
        self.visible_path_segment_count = 0
        if self.gcode_preview is None:
            self.render()
            return

        grouped: dict[str, tuple[tuple[float, float, float], list[tuple[tuple[float, float, float], tuple[float, float, float], str]]]] = {}
        for segment in self.gcode_preview.segments:
            if not self._segment_visible(segment):
                continue
            if not segment.has_spatial_length:
                continue
            color_key = segment.color_key()
            color = segment.color()
            grouped.setdefault(color_key, (color, []) )[1].append((segment.start, segment.end, segment.move_type))
            self.visible_path_segment_count += 1

        for color, lines in grouped.values():
            actor = self._make_line_actor(lines, color)
            self.renderer.AddActor(actor)
            self.path_actors.append(actor)

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

    def _make_line_actor(
        self,
        lines: list[tuple[tuple[float, float, float], tuple[float, float, float], str]],
        color: tuple[float, float, float],
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
        actor.GetProperty().SetOpacity(0.95 if has_extrusion else 0.48)
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
