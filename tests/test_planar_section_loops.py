from pathlib import Path
import math
import sys

import cadquery as cq
import pytest
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
from OCP.Geom import Geom_Line
from OCP.TopoDS import TopoDS_Compound
from OCP.gp import gp_Dir, gp_Pnt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.planar.region import (
    PlanarSectionError,
    _recover_loops,
    slice_planar_layers,
)
from five_axis_slicer.step_loader import load_step


def _vertices(points):
    return [BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex() for point in points]


def _compound(edges):
    builder = BRep_Builder()
    shape = TopoDS_Compound()
    builder.MakeCompound(shape)
    for edge in edges:
        builder.Add(shape, edge)
    return shape


def _square(gap=0.0, *, open_endpoint=False, branch=False):
    vertices = _vertices([(0, 0, 0), (4, 0, 0), (4, 4, 0), (0, 4, 0)])
    builder = BRep_Builder()
    # Deliberately generous kernel tolerance is not the manufacturing budget.
    for vertex in vertices:
        builder.UpdateVertex(vertex, 0.1)
    last_vertex = _vertices([(0.000001, 0, 0)])[0] if open_endpoint else vertices[0]
    builder.UpdateVertex(last_vertex, 0.1)
    endpoints = [*vertices[1:], last_vertex]
    curves = [(0, gap, 1, 0), (4, 0, 0, 1), (4, 4, -1, 0), (0, 4, 0, -1)]
    edges = [
        BRepBuilderAPI_MakeEdge(
            Geom_Line(gp_Pnt(x, y, 0), gp_Dir(dx, dy, 0)), start, end, 0.0, 4.0
        ).Edge()
        for (x, y, dx, dy), start, end in zip(curves, vertices, endpoints)
    ]
    if branch:
        edges.append(BRepBuilderAPI_MakeEdge(vertices[0], vertices[2]).Edge())
    return _compound([edge.Reversed() for edge in reversed(edges)])


def _area(loop):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(loop, loop[1:]))) / 2


def test_shared_vertex_cycle_handles_reversed_edges_and_bounded_curve_endpoint_gap():
    loops = _recover_loops(_square(0.0003), 8)
    assert len(loops) == 1
    assert loops[0][0] == loops[0][-1]
    assert _area(loops[0]) == pytest.approx(16.0, abs=0.002)
    assert all(math.isfinite(value) for point in loops[0] for value in point)


def test_nearby_but_distinct_vertices_are_not_healed_into_a_cycle():
    with pytest.raises(PlanarSectionError, match="planar.section_open_contour"):
        _recover_loops(_square(open_endpoint=True), 8)


def test_shared_vertex_branch_is_rejected_instead_of_choosing_a_nearest_edge():
    with pytest.raises(PlanarSectionError, match="planar.section_branch_contour"):
        _recover_loops(_square(branch=True), 8)


def test_large_kernel_vertex_tolerance_does_not_authorise_large_coordinate_repair():
    with pytest.raises(PlanarSectionError, match="planar.section_endpoint_gap_exceeds_limit"):
        _recover_loops(_square(0.02), 8)


def test_closed_zero_area_cycle_is_rejected():
    first, last = _vertices([(0, 0, 0), (4, 0, 0)])
    edges = [
        BRepBuilderAPI_MakeEdge(first, last).Edge(),
        BRepBuilderAPI_MakeEdge(last, first).Edge(),
    ]
    with pytest.raises(PlanarSectionError, match="planar.section_degenerate_contour"):
        _recover_loops(_compound(edges), 8)


def test_single_edge_periodic_section_keeps_its_closed_loop():
    circle = cq.Edge.makeCircle(3)
    loops = _recover_loops(circle.wrapped, 128)
    assert len(loops) == 1
    assert loops[0][0] == loops[0][-1]
    assert _area(loops[0]) == pytest.approx(9 * math.pi, rel=0.0005)


@pytest.mark.parametrize(
    "relative_path,z_mm",
    [("example/三叶扇/Supportless_sample.stp", 67.7), ("example/叶轮/叶轮.stp", 20.6)],
)
def test_existing_step_shared_vertex_section_regressions(relative_path, z_mm):
    model = load_step(Path(__file__).resolve().parents[1] / relative_path)
    layer = slice_planar_layers(
        model, ("body_002",), first_layer_z_mm=z_mm, layer_height_mm=0.6, last_layer_z_mm=z_mm
    )[0]
    assert len(layer.regions) == 1
    assert layer.regions[0].outer[0] == layer.regions[0].outer[-1]
    assert _area(layer.regions[0].outer) > 1.0
    assert all(abs(point[2] - z_mm) < 1e-6 for point in layer.regions[0].outer)


def test_existing_step_excessive_section_gap_is_localised_and_rejected():
    model = load_step(Path(__file__).resolve().parents[1] / "example/叶轮/叶轮.stp")
    with pytest.raises(
        PlanarSectionError, match=r"planar.section_endpoint_gap_exceeds_limit: z_mm=41.6"
    ):
        slice_planar_layers(
            model, ("body_002",), first_layer_z_mm=41.6, layer_height_mm=0.6, last_layer_z_mm=41.6
        )
