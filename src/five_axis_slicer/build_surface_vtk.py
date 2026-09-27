"""VTK adapter for the shared platform display geometry."""

import vtk

from .models import BuildSurfaceOverlay
from .opengl_scene import build_surface_grid, build_surface_lines, build_surface_triangles


def build_surface_actor(surface: BuildSurfaceOverlay) -> vtk.vtkActor:
    points = vtk.vtkPoints()
    lines, polygons = vtk.vtkCellArray(), vtk.vtkCellArray()
    colors = vtk.vtkUnsignedCharArray()
    colors.SetNumberOfComponents(3)
    for vertices, size, cells, color in (
        (build_surface_lines(surface), 2, lines, (107, 122, 148)),
        (build_surface_grid(surface), 2, lines, (115, 130, 150)),
        (build_surface_triangles(surface), 3, polygons, (46, 54, 64)),
    ):
        for start in range(0, len(vertices), size):
            cells.InsertNextCell(size)
            for point in vertices[start : start + size]:
                cells.InsertCellPoint(points.InsertNextPoint(*point))
            colors.InsertNextTuple3(*color)
    data = vtk.vtkPolyData()
    data.SetPoints(points)
    data.SetLines(lines)
    data.SetPolys(polygons)
    data.GetCellData().SetScalars(colors)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(data)
    mapper.SetScalarModeToUseCellData()
    mapper.SetColorModeToDirectScalars()
    mapper.SetResolveCoincidentTopologyToPolygonOffset()
    mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(1.0, 1.0)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().LightingOff()
    actor.GetProperty().SetLineWidth(1.5)
    actor.SetPickable(False)
    return actor
