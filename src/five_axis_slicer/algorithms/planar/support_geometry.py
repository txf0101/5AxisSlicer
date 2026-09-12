"""Planar support Boolean geometry using the existing OCCT offset backend."""

from __future__ import annotations

import math

import cadquery as cq

from .offset import _area, _contains, _offset_loops, _prepare_region, _wire_loop
from .region import PlanarRegion, PlanarSliceLayer

AREA_EPSILON = 1.0e-7


class PlanarSupportError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def empty_shape() -> cq.Shape:
    return cq.Compound.makeCompound([])


def shape_area(shape: cq.Shape) -> float:
    return sum(face.Area() for face in shape.Faces())


def union_shapes(shapes: list[cq.Shape]) -> cq.Shape:
    nonempty = [shape for shape in shapes if shape.Faces()]
    if not nonempty:
        return empty_shape()
    return nonempty[0] if len(nonempty) == 1 else nonempty[0].fuse(*nonempty[1:])


def subtract_shape(left: cq.Shape, right: cq.Shape) -> cq.Shape:
    return left.cut(right) if left.Faces() and right.Faces() else left


def intersect_shape(left: cq.Shape, right: cq.Shape) -> cq.Shape:
    return left.intersect(right) if left.Faces() and right.Faces() else empty_shape()


def layer_shape(layer: PlanarSliceLayer) -> cq.Shape:
    """Validate at the supplied Z before moving faces to a common XY plane."""
    faces: list[cq.Shape] = []
    if len({region.region_id for region in layer.regions}) != len(layer.regions):
        raise PlanarSupportError("planar.support_region_id_duplicate", layer.layer_id)
    for region in layer.regions:
        points = [point for loop in (region.outer, *region.holes) for point in loop]
        if any(
            not all(math.isfinite(value) for value in point) or abs(point[2] - layer.z_mm) > 1.0e-6
            for point in points
        ):
            raise PlanarSupportError("planar.support_geometry_invalid", layer.layer_id)
        face, problem = _prepare_region(region)
        if problem is not None or face is None or not face.isValid():
            detail = str(problem) if problem else "OCCT invalid face"
            raise PlanarSupportError(
                "planar.support_geometry_invalid", f"{layer.layer_id}/{region.region_id}: {detail}"
            )
        faces.append(face.translate((0, 0, -layer.z_mm)))
    return union_shapes(faces)


def offset_shape(shape: cq.Shape, distance_mm: float) -> cq.Shape:
    """Positive expands material, negative erodes it; holes retain topology."""
    if abs(distance_mm) <= 1.0e-9:
        return shape
    faces: list[cq.Shape] = []
    for face in shape.Faces():
        loops, error = _offset_loops(face, -distance_mm)
        if error:
            raise PlanarSupportError("planar.support_offset_failed", str(error))
        outers = [loop for loop in loops if _area(loop) > AREA_EPSILON]
        holes = [loop for loop in loops if _area(loop) < -AREA_EPSILON]
        for outer in outers:
            direct_holes = [
                hole
                for hole in holes
                if _contains(hole[0], outer)
                and not any(
                    abs(_area(other)) < abs(_area(outer)) and _contains(hole[0], other)
                    for other in outers
                )
            ]
            faces.append(
                cq.Face.makeFromWires(
                    cq.Wire.makePolygon(outer[:-1], close=True),
                    [cq.Wire.makePolygon(hole[:-1], close=True) for hole in direct_holes],
                )
            )
    return union_shapes(faces)


def shape_regions(shape: cq.Shape, z_mm: float, prefix: str) -> tuple[PlanarRegion, ...]:
    faces = sorted(
        [face for face in shape.Faces() if face.Area() > AREA_EPSILON],
        key=lambda face: (face.BoundingBox().ymin, face.BoundingBox().xmin, -face.Area()),
    )
    regions = []
    for index, face in enumerate(faces):
        outer_wire = face.outerWire()
        outer = _loop_at_z(_wire_loop(outer_wire), z_mm)
        holes = tuple(
            sorted(
                (_loop_at_z(_wire_loop(wire), z_mm) for wire in face.innerWires()),
                key=lambda loop: loop[0],
            )
        )
        regions.append(PlanarRegion(f"{prefix}-{index + 1:04d}", outer, holes))
    return tuple(regions)


def _loop_at_z(loop, z_mm):
    return tuple((point[0], point[1], z_mm) for point in loop)
