"""Exact OCCT plane sections and mid-wall contour recovery for Tube layers."""

from __future__ import annotations

from dataclasses import dataclass
import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

from ...models import CadModel, Vector3
from ...step_topology import sample_edge_points


class TubeSectionError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = str(code)
        self.detail = str(detail)
        super().__init__(f"{self.code}: {self.detail}")


@dataclass(frozen=True, slots=True)
class TubeSectionContours:
    outer: tuple[Vector3, ...]
    inner: tuple[Vector3, ...]
    midwall: tuple[Vector3, ...]
    normals: tuple[Vector3, ...]
    maximum_half_thickness_error_mm: float


def section_tube_layer(
    model: CadModel,
    body_id: str,
    plane_origin: Vector3,
    plane_normal: Vector3,
    wall_thickness_mm: float,
    *,
    sample_segments: int = 128,
) -> TubeSectionContours:
    """Intersect one selected body and return the nearest closed annular pair."""

    shape = model.shapes.get(body_id)
    if shape is None:
        raise TubeSectionError("tube.section_body_missing", body_id)
    normal = _unit(plane_normal)
    extent = max(model.bounds.diagonal if model.bounds is not None else 1000.0, 1.0) * 2.0
    plane = gp_Pln(gp_Pnt(*plane_origin), gp_Dir(*normal))
    face = BRepBuilderAPI_MakeFace(plane, -extent, extent, -extent, extent).Face()
    section = BRepAlgoAPI_Section(shape, face, False)
    section.ComputePCurveOn1(True)
    section.Approximation(True)
    section.Build()
    if not section.IsDone():
        raise TubeSectionError("tube.section_kernel_failed", body_id)
    loops = _section_loops(section.Shape(), sample_segments)
    if len(loops) < 2:
        raise TubeSectionError("tube.section_not_annular", f"recovered {len(loops)} loops")
    paired = _nearest_annular_pair(loops, plane_origin, normal)
    outer, inner = _orient_pair(*paired, normal)
    midwall, normals, error = _midwall(outer, inner, wall_thickness_mm)
    return TubeSectionContours(outer, inner, midwall, normals, error)


def _section_loops(shape: object, sample_segments: int) -> list[tuple[Vector3, ...]]:
    chains: list[list[Vector3]] = []
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        points = sample_edge_points(edge, sample_segments)
        if len(points) >= 2:
            chains.append(points)
        explorer.Next()
    loops: list[tuple[Vector3, ...]] = []
    while chains:
        current = chains.pop(0)
        while math.dist(current[0], current[-1]) > 1.0e-4:
            match = _next_chain(current[-1], chains)
            if match is None:
                raise TubeSectionError("tube.section_open_contour", f"gap at {current[-1]}")
            index, reverse = match
            addition = chains.pop(index)
            if reverse:
                addition.reverse()
            current.extend(addition[1:])
        current[-1] = current[0]
        loops.append(tuple(current))
    return loops


def _next_chain(point: Vector3, chains: list[list[Vector3]]) -> tuple[int, bool] | None:
    candidates: list[tuple[float, int, bool]] = []
    for index, chain in enumerate(chains):
        candidates.append((math.dist(point, chain[0]), index, False))
        candidates.append((math.dist(point, chain[-1]), index, True))
    if not candidates:
        return None
    distance, index, reverse = min(candidates)
    return (index, reverse) if distance <= 1.0e-4 else None


def _nearest_annular_pair(
    loops: list[tuple[Vector3, ...]], origin: Vector3, normal: Vector3
) -> tuple[tuple[Vector3, ...], tuple[Vector3, ...]]:
    u, v = _plane_basis(normal)
    records = [
        (loop, abs(_signed_area(loop, origin, u, v)), math.dist(_centroid(loop), origin))
        for loop in loops
    ]
    pairs: list[tuple[float, tuple[Vector3, ...], tuple[Vector3, ...]]] = []
    for left_index, left in enumerate(records):
        for right in records[left_index + 1 :]:
            outer, inner = (left, right) if left[1] >= right[1] else (right, left)
            if outer[1] <= inner[1] + 1.0e-8:
                continue
            pairs.append((outer[2] + inner[2], outer[0], inner[0]))
    if not pairs:
        raise TubeSectionError("tube.section_pair_ambiguous", "no nested loop-area pair")
    _distance, outer_loop, inner_loop = min(pairs, key=lambda item: item[0])
    return outer_loop, inner_loop


def _orient_pair(
    outer: tuple[Vector3, ...], inner: tuple[Vector3, ...], normal: Vector3
) -> tuple[tuple[Vector3, ...], tuple[Vector3, ...]]:
    origin = _centroid(outer)
    u, v = _plane_basis(normal)
    if _signed_area(outer, origin, u, v) < 0.0:
        outer = tuple(reversed(outer))
    if _signed_area(inner, origin, u, v) > 0.0:
        inner = tuple(reversed(inner))
    return outer, inner


def _midwall(
    outer: tuple[Vector3, ...], inner: tuple[Vector3, ...], wall_thickness: float
) -> tuple[tuple[Vector3, ...], tuple[Vector3, ...], float]:
    points: list[Vector3] = []
    normals: list[Vector3] = []
    errors: list[float] = []
    for outer_point in outer[:-1]:
        inner_point = min(inner[:-1], key=lambda item: math.dist(item, outer_point))
        distance = math.dist(outer_point, inner_point)
        points.append(_scale(_add(outer_point, inner_point), 0.5))
        normals.append(_unit(_subtract(outer_point, inner_point)))
        errors.append(abs(distance - wall_thickness) * 0.5)
    points.append(points[0])
    normals.append(normals[0])
    return tuple(points), tuple(normals), max(errors, default=0.0)


def _signed_area(points: tuple[Vector3, ...], origin: Vector3, u: Vector3, v: Vector3) -> float:
    projected = [
        (_dot(_subtract(point, origin), u), _dot(_subtract(point, origin), v)) for point in points
    ]
    return 0.5 * sum(
        left[0] * right[1] - right[0] * left[1] for left, right in zip(projected, projected[1:])
    )


def _plane_basis(normal: Vector3) -> tuple[Vector3, Vector3]:
    reference = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.8 else (0.0, 1.0, 0.0)
    u = _unit(_cross(normal, reference))
    return u, _unit(_cross(normal, u))


def _centroid(points: tuple[Vector3, ...]) -> Vector3:
    count = max(1, len(points) - 1)
    return tuple(sum(point[index] for point in points[:-1]) / count for index in range(3))  # type: ignore[return-value]


def _unit(value: Vector3) -> Vector3:
    length = math.sqrt(_dot(value, value))
    if length <= 1.0e-12:
        raise ValueError("zero-length vector")
    return _scale(value, 1.0 / length)


def _add(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a + b for a, b in zip(left, right))  # type: ignore[return-value]


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(left, right))  # type: ignore[return-value]


def _scale(value: Vector3, factor: float) -> Vector3:
    return tuple(item * factor for item in value)  # type: ignore[return-value]


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right))


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


__all__ = ["TubeSectionContours", "TubeSectionError", "section_tube_layer"]
