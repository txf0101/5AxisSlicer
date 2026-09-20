"""Solid/sphere intersection domains with an explicit non-isometric chart.

The upper-hemisphere chart stores local (x, y, radius). It is intended for
layer-domain construction; planar distances/areas MUST NOT be used as surface
distances/areas. This module alone grants no manufacturing qualification.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...models import Vector3
from ..planar.region import PlanarSliceLayer, _classify_loops
from ..planar.section_loops import recover_section_loops


@dataclass(frozen=True, slots=True)
class SphericalChart:
    center: Vector3 = (0.0, 0.0, 0.0)
    minimum_normal_z: float = 0.1

    def __post_init__(self):
        if len(self.center) != 3 or not all(math.isfinite(v) for v in self.center):
            raise ValueError("finite sphere center required")
        if not 0 < self.minimum_normal_z <= 1:
            raise ValueError("minimum_normal_z must be in (0, 1]")

    def lift(self, point: Vector3) -> Vector3:
        x, y, radius = point
        z = self._height(point)
        return x + self.center[0], y + self.center[1], z + self.center[2]

    def normal(self, point: Vector3) -> Vector3:
        x, y, radius = point
        return x / radius, y / radius, self._height(point) / radius

    def area_scale(self, point: Vector3) -> float:
        """Surface area / projected area; derived from |dX/dx cross dX/dy|."""
        return point[2] / self._height(point)

    def tangent_length(self, point: Vector3, dx: float, dy: float) -> float:
        z = self._height(point)
        return math.sqrt(dx * dx + dy * dy + ((point[0] * dx + point[1] * dy) / z) ** 2)

    def project(self, point: Vector3, radius: float) -> Vector3:
        local = tuple(a - b for a, b in zip(point, self.center, strict=True))
        if abs(math.sqrt(sum(v * v for v in local)) - radius) > 0.001:
            raise ValueError("freeform.sphere_section_radius_error")
        chart = (local[0], local[1], radius)
        if local[2] <= 0:
            raise ValueError("freeform.sphere_chart_wrong_hemisphere")
        self._height(chart)
        return chart

    def _height(self, point: Vector3) -> float:
        x, y, radius = point
        if not all(math.isfinite(v) for v in point) or radius <= 0:
            raise ValueError("finite spherical chart with positive radius required")
        square = radius * radius - x * x - y * y
        if square <= 0 or math.sqrt(square) / radius < self.minimum_normal_z:
            raise ValueError("freeform.sphere_chart_singular")
        return math.sqrt(square)

    def signed_surface_area(self, loop: tuple[Vector3, ...]) -> float:
        """Area of the geodesic polygon through sampled boundary points.

        Signed solid angles retain hole orientation. Curved BRep edges still
        require sampling convergence; chart shoelace area is not substituted.
        """
        if len(loop) < 4 or loop[0] != loop[-1]:
            raise ValueError("closed spherical loop required")
        radius = loop[0][2]
        if any(abs(p[2] - radius) > 1e-9 for p in loop):
            raise ValueError("spherical loop must have one radius")
        normals = [self.normal(p) for p in loop]
        angles = []
        for a, b in zip(normals, normals[1:]):
            numerator = a[0] * b[1] - a[1] * b[0]
            denominator = 1 + a[2] + b[2] + sum(x * y for x, y in zip(a, b))
            angles.append(2 * math.atan2(numerator, denominator))
        return radius * radius * math.fsum(angles)


def spherical_section(
    shape: object,
    radius_mm: float,
    *,
    chart: SphericalChart = SphericalChart(),
    sample_segments: int = 128,
) -> PlanarSliceLayer:
    """Intersect the complete selected solid; retain all islands and holes.

    No radius shifting, guide-count truncation or boundary-gap bridging is used.
    A failed section is an error, never an empty successful manufacturing layer.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.Geom import Geom_SphericalSurface
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt

    if not math.isfinite(radius_mm) or radius_mm <= 0 or sample_segments < 8:
        raise ValueError("invalid spherical section parameters")
    sphere = Geom_SphericalSurface(gp_Ax3(gp_Pnt(*chart.center), gp_Dir(0, 0, 1)), radius_mm)
    face = BRepBuilderAPI_MakeFace(sphere, -math.pi, math.pi, 0.0, math.pi / 2, 1e-7).Face()
    section = BRepAlgoAPI_Section(shape, face, False)
    section.Build()
    if not section.IsDone():
        raise ValueError("freeform.sphere_section_failed")
    loops = recover_section_loops(
        section.Shape(),
        sample_segments,
        max_endpoint_correction_mm=0.001,
        allow_bounded_topology_repair=False,
    )
    projected = [tuple(chart.project(p, radius_mm) for p in loop) for loop in loops]
    return PlanarSliceLayer(f"sphere-{radius_mm:.6f}", radius_mm, _classify_loops(projected))
