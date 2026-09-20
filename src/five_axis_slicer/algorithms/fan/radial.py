"""Experimental cylindrical blade layers, in Source coordinates about Source Z.

The chart is (u = radius * theta, v = axial z). Its metric is Euclidean on
each cylinder. This is a geometry preview, NOT a collision-qualified program.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRep import BRep_Builder
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.Bnd import Bnd_Box
from OCP.Geom import Geom_CylindricalSurface
from OCP.TopAbs import TopAbs_IN, TopAbs_ON
from OCP.TopoDS import TopoDS_Compound
from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt

from ...models import Vector3
from ..planar.region import PlanarSliceLayer, _classify_loops
from ..planar.section_loops import SectionLoopError, recover_section_loops


@dataclass(frozen=True, slots=True)
class RadialBladeDomain:
    layers: tuple[PlanarSliceLayer, ...]
    substrate_radius_mm: float
    layer_height_mm: float
    root_sample_count: int
    unsupported_root_sample_count: int
    source_frame: str = "source_z_cylindrical_chart"
    manufacturing_qualified: bool = False


def chart_to_source(point: Vector3) -> Vector3:
    """Map (arc length, axial height, radius) to the workpiece, not machine XYZ."""
    u, axial, radius = point
    if radius <= 0 or not all(math.isfinite(v) for v in point):
        raise ValueError("finite cylindrical chart with positive radius required")
    theta = u / radius
    return radius * math.cos(theta), radius * math.sin(theta), axial


def cylindrical_section(
    shape: object,
    radius_mm: float,
    *,
    sample_segments: int = 128,
    seam_center_rad: float = 0.0,
) -> PlanarSliceLayer:
    """Section a BRep with an actual cylinder; reject charts crossing their seam."""
    if radius_mm <= 0 or not math.isfinite(radius_mm) or sample_segments < 8:
        raise ValueError("invalid cylindrical section parameters")
    surface = Geom_CylindricalSurface(gp_Ax3(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), radius_mm)
    bounds = Bnd_Box()
    BRepBndLib.Add_s(shape, bounds)
    _, _, zmin, _, _, zmax = bounds.Get()
    # Finite face bounds avoid OCCT's unbounded surface/solid failure on the
    # real blade at R29.7; no radius shift or fuzzy tolerance is introduced.
    face = BRepBuilderAPI_MakeFace(
        surface,
        seam_center_rad - math.pi,
        seam_center_rad + math.pi,
        zmin - 1.0,
        zmax + 1.0,
        1e-7,
    ).Face()
    section = BRepAlgoAPI_Section(shape, face, False)
    section.Build()
    if not section.IsDone():
        raise ValueError(f"fan.cylindrical_section_failed: r={radius_mm}")
    try:
        loops = recover_section_loops(
            section.Shape(),
            sample_segments,
            max_endpoint_correction_mm=0.001,
            allow_bounded_topology_repair=True,
        )
    except SectionLoopError:
        # A full-period cylinder can lose a side-face intersection in OCCT.
        # Re-section the SAME surface in two bounded parameter patches. This
        # neither moves the radius nor bridges the missing physical boundary.
        loops = _split_cylinder_loops(shape, surface, seam_center_rad, zmin, zmax, sample_segments)
    charts = [_unwrap_loop(loop, radius_mm, seam_center_rad) for loop in loops]
    return PlanarSliceLayer(f"radius-{radius_mm:.6f}", radius_mm, _classify_loops(charts))


def _split_cylinder_loops(shape, surface, center, zmin, zmax, samples):
    for partitions in (2, 4, 8, 16, 32, 64):
        compound = _cylinder_patch_sections(shape, surface, center, zmin, zmax, partitions)
        try:
            return recover_section_loops(
                # Reserve one quarter of the 0.02 mm chord-error budget for
                # independent face-intersection endpoints; never bridge gaps.
                compound,
                samples,
                max_endpoint_correction_mm=0.005,
                allow_bounded_topology_repair=True,
            )
        except SectionLoopError as error:
            last_error = error
    raise ValueError(f"fan.cylindrical_section_invalid: r={surface.Radius()}; {last_error}")


def _cylinder_patch_sections(shape, surface, center, zmin, zmax, partitions):
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for index in range(partitions):
        low = center - math.pi + index * 2 * math.pi / partitions
        high = center - math.pi + (index + 1) * 2 * math.pi / partitions
        patch = BRepBuilderAPI_MakeFace(surface, low, high, zmin - 1, zmax + 1, 1e-7).Face()
        section = BRepAlgoAPI_Section(shape, patch, False)
        section.Build()
        if not section.IsDone():
            raise ValueError("fan.cylindrical_patch_failed")
        builder.Add(compound, section.Shape())
    return compound


def _unwrap_loop(loop, radius, center):
    result = []
    for x, y, z in loop:
        if abs(math.hypot(x, y) - radius) > 0.001:
            raise ValueError("fan.section_radius_error")
        theta = center + math.remainder(math.atan2(y, x) - center, 2 * math.pi)
        result.append((radius * theta, z, radius))
    if any(abs(b[0] - a[0]) > math.pi * radius for a, b in zip(result, result[1:])):
        raise ValueError("fan.cylindrical_chart_crosses_seam")
    result[-1] = result[0]
    return tuple(result)


def radial_blade_domain(
    blade: object,
    hub: object,
    *,
    substrate_radius_mm: float,
    last_radius_mm: float,
    layer_height_mm: float = 0.2,
    seam_center_rad: float = 0.0,
    sample_segments: int = 128,
) -> RadialBladeDomain:
    """Grow from a verified cylindrical substrate; never use the blade XY bbox as root."""
    if (
        not all(
            math.isfinite(v) and v > 0
            for v in (
                substrate_radius_mm,
                last_radius_mm,
                layer_height_mm,
            )
        )
        or last_radius_mm <= substrate_radius_mm
    ):
        raise ValueError("invalid radial layer range")
    # Avoid coincident CAD faces at the interface. Probe 0.01 mm outside,
    # then project to 0.01 mm inside the substrate for an independent test.
    root = cylindrical_section(
        blade,
        substrate_radius_mm + 0.01,
        sample_segments=sample_segments,
        seam_center_rad=seam_center_rad,
    )
    samples, unsupported = _root_support(root, hub, substrate_radius_mm)
    if not samples or unsupported:
        raise ValueError(f"fan.root_not_on_substrate: {unsupported}/{samples}")
    count = math.ceil((last_radius_mm - substrate_radius_mm) / layer_height_mm)
    layers = tuple(
        cylindrical_section(
            blade,
            substrate_radius_mm + index * layer_height_mm,
            sample_segments=sample_segments,
            seam_center_rad=seam_center_rad,
        )
        for index in range(1, count + 1)
    )
    return RadialBladeDomain(layers, substrate_radius_mm, layer_height_mm, samples, unsupported)


def _root_support(root, hub, substrate_radius_mm):
    classifier = BRepClass3d_SolidClassifier(hub)
    count = unsupported = 0
    for region in root.regions:
        for loop in (region.outer, *region.holes):
            for point in loop[:-1]:
                x, y, z = chart_to_source(point)
                factor = (substrate_radius_mm - 0.01) / root.z_mm
                classifier.Perform(gp_Pnt(x * factor, y * factor, z), 1e-6)
                unsupported += classifier.State() not in (TopAbs_IN, TopAbs_ON)
                count += 1
    return count, unsupported


def sample_chart_segment(start: Vector3, end: Vector3, max_step_mm: float = 0.2):
    """Subdivide in the cylinder chart before mapping, avoiding long inward chords."""
    if start[2] != end[2] or max_step_mm <= 0:
        raise ValueError("same-radius segment and positive step required")
    steps = max(1, math.ceil(math.dist(start, end) / max_step_mm))
    return tuple(
        chart_to_source(
            (
                start[0] + (end[0] - start[0]) * index / steps,
                start[1] + (end[1] - start[1]) * index / steps,
                start[2],
            )
        )
        for index in range(steps + 1)
    )
