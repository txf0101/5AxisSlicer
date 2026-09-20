"""Compare face-wise and solid-wise OCCT intersections at the recorded failure."""

import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.Geom import Geom_CylindricalSurface
from OCP.gp import gp_Ax3, gp_Pnt, gp_Dir
from OCP.BRep import BRep_Builder
from OCP.TopoDS import TopoDS_Compound
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.algorithms.planar.section_loops import recover_section_loops
import math

model = load_step("example/扇叶/风扇扇叶(1).STEP")
shape = model.shapes["body_001"]
print("solid valid", BRepCheck_Analyzer(shape).IsValid(), flush=True)
cylinder = BRepBuilderAPI_MakeFace(
    Geom_CylindricalSurface(gp_Ax3(gp_Pnt(), gp_Dir(0, 0, 1)), 75.7),
    -math.pi,
    math.pi,
    48,
    60,
    1e-7,
).Face()
builder = BRep_Builder()
compound = TopoDS_Compound()
builder.MakeCompound(compound)
for i, face in enumerate(cq.Shape.cast(shape).Faces()):
    section = BRepAlgoAPI_Section(face.wrapped, cylinder, False)
    section.Build()
    edges = cq.Shape.cast(section.Shape()).Edges()
    print(
        i,
        face.geomType(),
        "valid",
        BRepCheck_Analyzer(face.wrapped).IsValid(),
        "edges",
        len(edges),
        flush=True,
    )
    for edge in edges:
        print("  ", edge.startPoint().toTuple(), edge.endPoint().toTuple(), flush=True)
        builder.Add(compound, edge.wrapped)
try:
    loops = recover_section_loops(
        compound, 128, max_endpoint_correction_mm=0.001, allow_bounded_topology_repair=True
    )
    print("FACEWISE CLOSED", len(loops), flush=True)
except ValueError as exc:
    print("FACEWISE FAILED", exc, flush=True)

from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert

for label, target in [("nurbs", BRepBuilderAPI_NurbsConvert(cylinder).Shape())]:
    section = BRepAlgoAPI_Section(shape, target, False)
    section.Build()
    try:
        loops = recover_section_loops(
            section.Shape(),
            128,
            max_endpoint_correction_mm=0.001,
            allow_bounded_topology_repair=True,
        )
        print(label, "CLOSED", len(loops), flush=True)
    except ValueError as exc:
        print(label, "FAILED", exc, flush=True)
patches = TopoDS_Compound()
builder.MakeCompound(patches)
for low, high in [(-math.pi, 0), (0, math.pi)]:
    patch = BRepBuilderAPI_MakeFace(
        Geom_CylindricalSurface(gp_Ax3(gp_Pnt(), gp_Dir(0, 0, 1)), 75.7), low, high, 48, 60, 1e-7
    ).Face()
    section = BRepAlgoAPI_Section(shape, patch, False)
    section.Build()
    print("patch", low, high, "edges", len(cq.Shape.cast(section.Shape()).Edges()), flush=True)
    builder.Add(patches, section.Shape())
try:
    loops = recover_section_loops(
        patches, 128, max_endpoint_correction_mm=0.001, allow_bounded_topology_repair=True
    )
    print("HALVES CLOSED", len(loops), flush=True)
except ValueError as exc:
    print("HALVES FAILED", exc, flush=True)
