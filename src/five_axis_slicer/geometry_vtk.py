from __future__ import annotations

from OCP.BRep import BRep_Tool
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
import vtk

from .step_loader import sample_edge_points


def shape_to_polydata(shape: object, linear_deflection: float = 0.35) -> vtk.vtkPolyData:
    BRepMesh_IncrementalMesh(shape, linear_deflection)
    points = vtk.vtkPoints()
    polys = vtk.vtkCellArray()

    face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while face_explorer.More():
        face = TopoDS.Face_s(face_explorer.Current())
        loc = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, loc)
        if triangulation is not None:
            transform = loc.Transformation()
            base = points.GetNumberOfPoints()
            for index in range(1, triangulation.NbNodes() + 1):
                pnt = triangulation.Node(index).Transformed(transform)
                points.InsertNextPoint(pnt.X(), pnt.Y(), pnt.Z())
            for index in range(1, triangulation.NbTriangles() + 1):
                n1, n2, n3 = triangulation.Triangle(index).Get()
                triangle = vtk.vtkTriangle()
                triangle.GetPointIds().SetId(0, base + n1 - 1)
                triangle.GetPointIds().SetId(1, base + n2 - 1)
                triangle.GetPointIds().SetId(2, base + n3 - 1)
                polys.InsertNextCell(triangle)
        face_explorer.Next()

    polydata = vtk.vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetPolys(polys)

    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(polydata)
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.Update()
    return normals.GetOutput()


def edge_to_polydata(edge: object, segments: int = 24) -> vtk.vtkPolyData:
    sampled = sample_edge_points(edge, target_segments=segments)
    points = vtk.vtkPoints()
    lines = vtk.vtkCellArray()
    if len(sampled) >= 2:
        polyline = vtk.vtkPolyLine()
        polyline.GetPointIds().SetNumberOfIds(len(sampled))
        for index, point in enumerate(sampled):
            vtk_index = points.InsertNextPoint(*point)
            polyline.GetPointIds().SetId(index, vtk_index)
        lines.InsertNextCell(polyline)
    polydata = vtk.vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetLines(lines)
    return polydata

