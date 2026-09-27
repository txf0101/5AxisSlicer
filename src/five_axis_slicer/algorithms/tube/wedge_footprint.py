"""Conservative CAD-region footprints, without point-sampling extrema."""

from __future__ import annotations

from dataclasses import dataclass
import itertools

from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakeHalfSpace
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

from ...models import CadModel, Vector3
from .wedge_material import _dot, _unit, _vector
from .wedge_plan import WedgeRegionBoundary


@dataclass(frozen=True, slots=True)
class WedgeFootprint:
    vertices: tuple[Vector3, ...]
    origin: Vector3
    build_axis: Vector3
    width_axis: Vector3
    transverse_axis: Vector3
    positive_boundary_columns: bool
    limitations: tuple[str, ...] = (
        "world_aabb_projection_overbounds_clipped_cad",
        "rectangle_may_include_columns_outside_actual_wedge",
        "not_a_deposited_material_or_support_certificate",
    )


def cad_wedge_footprint(
    model: CadModel, body_id: str, boundary: WedgeRegionBoundary,
    build_axis: Vector3,
) -> WedgeFootprint:
    """Clip actual BRep to both planes, then project its tolerance-expanded box.

    OCCT MakeHalfSpace selects material using an interior reference point;
    AddOptimal(False, True) uses geometry rather than display triangulation and
    expands for shape tolerance. Rectangle corners can still lie outside the
    wedge even after BRep clipping. The explicit column flag prevents treating
    such a rectangle as directly admissible to plan_layer_bands.
    """

    shape = model.shapes.get(body_id)
    if shape is None or shape.IsNull():
        raise ValueError("selected CAD body is missing")
    axis = _unit(build_axis, "build_axis")
    limits = _clipped_bounds(shape, boundary)
    u, v = _section_basis(axis)
    origin = boundary.entry_plane.origin
    vertices = _project_rectangle(limits, origin, u, v)
    positive = _positive_columns(vertices, axis, boundary)
    return WedgeFootprint(vertices, origin, axis, u, v, positive)


def _clipped_bounds(shape, boundary: WedgeRegionBoundary):
    for halfspace in (boundary.entry_halfspace, boundary.exit_halfspace):
        face = BRepBuilderAPI_MakeFace(gp_Pln(
            gp_Pnt(*halfspace.origin), gp_Dir(*halfspace.normal),
        )).Face()
        reference = _vector(tuple(a + b for a, b in zip(
            halfspace.origin, halfspace.normal, strict=True,
        )), "half-space reference")
        solid = BRepPrimAPI_MakeHalfSpace(face, gp_Pnt(*reference)).Solid()
        common = BRepAlgoAPI_Common(shape, solid)
        common.Build()
        if not common.IsDone():
            raise ValueError("CAD wedge intersection failed")
        shape = common.Shape()
    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, bounds, False, True)
    if bounds.IsVoid() or bounds.IsOpen():
        raise ValueError("CAD wedge has empty or unbounded geometry")
    return bounds.Get()


def _section_basis(axis: Vector3) -> tuple[Vector3, Vector3]:
    reference_axis: Vector3 = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.8 else (0.0, 1.0, 0.0)
    projection = _dot(reference_axis, axis)
    u = _unit(tuple(a - projection * n for a, n in zip(
        reference_axis, axis, strict=True,
    )), "width axis")  # type: ignore[arg-type]
    v: Vector3 = (axis[1] * u[2] - axis[2] * u[1],
                  axis[2] * u[0] - axis[0] * u[2], axis[0] * u[1] - axis[1] * u[0])
    return u, v


def _project_rectangle(limits, origin: Vector3, u: Vector3, v: Vector3):
    corners = itertools.product(*[(limits[i], limits[i + 3]) for i in range(3)])
    coordinates = []
    for point in corners:
        delta = _vector(tuple(a - b for a, b in zip(point, origin, strict=True)), "box offset")
        coordinates.append((_dot(delta, u), _dot(delta, v)))
    low_u, high_u = min(p[0] for p in coordinates), max(p[0] for p in coordinates)
    low_v, high_v = min(p[1] for p in coordinates), max(p[1] for p in coordinates)
    return tuple(_vector(tuple(origin[i] + a * u[i] + b * v[i] for i in range(3)),
                         "footprint vertex")
                 for a, b in ((low_u, low_v), (high_u, low_v),
                              (high_u, high_v), (low_u, high_v)))


def _positive_columns(vertices, axis: Vector3, boundary: WedgeRegionBoundary) -> bool:
    entry_slope = _dot(axis, boundary.entry_plane.normal)
    exit_slope = _dot(axis, boundary.exit_plane.normal)
    if min(entry_slope, exit_slope) <= 1e-12:
        raise ValueError("build axis must advance through wedge planes")
    return all(
        boundary.exit_halfspace.signed_distance(p) / exit_slope
        > -boundary.entry_halfspace.signed_distance(p) / entry_slope for p in vertices
    )


__all__ = ["WedgeFootprint", "cad_wedge_footprint"]
