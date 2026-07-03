from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt5.QtCore import Qt
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtk

from .geometry_vtk import edge_to_polydata, shape_to_polydata
from .models import CadModel, SelectionState


SelectionCallback = Callable[[str, str], None]

BG_COLOR = (0.08, 0.085, 0.09)
EDGE_COLOR = (0.10, 0.10, 0.10)
EDGE_PICK_COLOR = (0.12, 0.12, 0.12)
EDGE_SELECTED_COLOR = (1.0, 0.92, 0.42)
BODY_SELECTED_COLOR = (0.98, 0.98, 0.98)
BODY_SELECTED_EDGE_COLOR = (0.05, 0.05, 0.05)
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
            actor.GetProperty().SetOpacity(0.92)
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

    def render(self) -> None:
        self.GetRenderWindow().Render()
