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
    """把 OCP shape 网格化为 VTK polydata。

    OCP 仍保留在模型层；这里仅为显示生成三角面。linear_deflection 越小，
    曲面越细腻，载入时间和 actor 数据量也会增加。
    """

    BRepMesh_IncrementalMesh(shape, linear_deflection)
    points = vtk.vtkPoints()
    polys = vtk.vtkCellArray()

    face_explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while face_explorer.More():
        face = TopoDS.Face_s(face_explorer.Current())
        loc = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, loc)
        if triangulation is not None:
            # OpenCascade 的节点下标从 1 开始，VTK 的点下标从 0 开始。
            # base 记录当前 polydata 已有点数，保证多个 face 追加后索引仍正确。
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

    # 法线交给 VTK 统一生成，避免不同 STEP 导出器的面方向差异影响光照。
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(polydata)
    normals.ConsistencyOn()
    normals.AutoOrientNormalsOn()
    normals.Update()
    return normals.GetOutput()


def edge_to_polydata(edge: object, segments: int = 24) -> vtk.vtkPolyData:
    """把一条 CAD 边线采样为 VTK polyline actor 使用的数据。"""

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
