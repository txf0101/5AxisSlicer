"""Recover section cycles from OCCT shared vertices, with bounded endpoint repair."""

from __future__ import annotations

from dataclasses import dataclass
import math

from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FORWARD
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS

from ...models import Vector3
from ...step_topology import sample_edge_points

# This bounds actual coordinate changes, independently of the CAD vertex's
# tolerance. A large imported tolerance must never authorise a large repair.
MAX_ENDPOINT_CORRECTION_MM = 0.001


class SectionLoopError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass
class _SectionEdge:
    start: int
    end: int
    points: list[Vector3]


def recover_section_loops(
    shape: object,
    sample_segments: int,
    *,
    max_endpoint_correction_mm: float = MAX_ENDPOINT_CORRECTION_MM,
    allow_bounded_topology_repair: bool = False,
) -> list[tuple[Vector3, ...]]:
    """Use topology for adjacency and curve parameters for traversal direction.

    Shared vertices are preferred. OCCT section output can duplicate a vertex
    at the same bounded location, so unmatched degree-one endpoints are paired
    only when their sampled endpoints require no more than the caller's repair
    limit. The midpoint is the sole coordinate correction.
    """
    if not math.isfinite(max_endpoint_correction_mm) or max_endpoint_correction_mm <= 0.0:
        raise ValueError("max_endpoint_correction_mm must be finite and positive")
    edges, incidence = _section_graph(shape, sample_segments)
    if allow_bounded_topology_repair:
        _join_bounded_open_endpoints(edges, incidence, max_endpoint_correction_mm)
    _join_shared_endpoints(edges, incidence, max_endpoint_correction_mm)
    unused = set(range(len(edges)))
    loops = []
    while unused:
        loop = _walk_cycle(edges, incidence, unused)
        if not _has_area(loop):
            raise SectionLoopError("planar.section_degenerate_contour", "zero-area cycle")
        loops.append(tuple(loop))
    return loops


def _section_graph(shape, sample_segments):
    edge_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, edge_map)
    vertices = TopTools_IndexedMapOfShape()
    edges: list[_SectionEdge] = []
    incidence: dict[int, list[tuple[int, bool]]] = {}
    for index in range(1, edge_map.Extent() + 1):
        # sample_edge_points follows increasing curve parameter regardless of
        # occurrence orientation. FORWARD makes First/LastVertex agree with it.
        edge = TopoDS.Edge_s(edge_map.FindKey(index).Oriented(TopAbs_FORWARD))
        first, last = TopExp.FirstVertex_s(edge), TopExp.LastVertex_s(edge)
        if first.IsNull() or last.IsNull():
            raise SectionLoopError("planar.section_open_contour", "edge has missing endpoint")
        if BRep_Tool.Degenerated_s(edge):
            raise SectionLoopError("planar.section_degenerate_contour", f"edge={index}")
        points = sample_edge_points(edge, sample_segments)
        if len(points) < 2 or any(
            not all(math.isfinite(value) for value in point) for point in points
        ):
            raise SectionLoopError("planar.section_degenerate_contour", f"edge={index}")
        start, end = vertices.Add(first), vertices.Add(last)
        incidence.setdefault(start, []).append((len(edges), True))
        incidence.setdefault(end, []).append((len(edges), False))
        edges.append(_SectionEdge(start, end, points))
    return edges, incidence


def _join_shared_endpoints(edges, incidence, max_endpoint_correction_mm):
    for vertex_id, ends in incidence.items():
        if len(ends) != 2:
            code = (
                "planar.section_open_contour" if len(ends) < 2 else "planar.section_branch_contour"
            )
            raise SectionLoopError(code, f"vertex={vertex_id}, degree={len(ends)}")
        samples = [edges[index].points[0 if start else -1] for index, start in ends]
        correction = math.dist(*samples) / 2.0
        if correction > max_endpoint_correction_mm:
            raise SectionLoopError(
                "planar.section_endpoint_gap_exceeds_limit",
                f"vertex={vertex_id}, correction_mm={correction:.9g}, "
                f"limit_mm={max_endpoint_correction_mm:.9g}",
            )
        joined: Vector3 = tuple((a + b) / 2 for a, b in zip(*samples))  # type: ignore[assignment]
        for index, start in ends:
            edges[index].points[0 if start else -1] = joined


def _join_bounded_open_endpoints(edges, incidence, max_endpoint_correction_mm):
    open_vertices = [vertex_id for vertex_id, ends in incidence.items() if len(ends) == 1]
    while open_vertices:
        left = open_vertices.pop(0)
        left_end = incidence[left][0]
        left_point = edges[left_end[0]].points[0 if left_end[1] else -1]
        candidates = []
        for right in open_vertices:
            right_end = incidence[right][0]
            right_point = edges[right_end[0]].points[0 if right_end[1] else -1]
            candidates.append((math.dist(left_point, right_point), right))
        if not candidates:
            return
        distance, right = min(candidates)
        if distance / 2.0 > max_endpoint_correction_mm:
            continue
        open_vertices.remove(right)
        right_end = incidence.pop(right)[0]
        incidence[left].append(right_end)
        edge = edges[right_end[0]]
        if right_end[1]:
            edge.start = left
        else:
            edge.end = left


def _walk_cycle(edges, incidence, unused):
    seed = min(unused)
    start = current = edges[seed].start
    loop: list[Vector3] = []
    index = seed
    while True:
        unused.remove(index)
        edge = edges[index]
        forward = edge.start == current
        points = edge.points if forward else list(reversed(edge.points))
        loop.extend(points if not loop else points[1:])
        current = edge.end if forward else edge.start
        if current == start:
            return loop
        candidates = [item for item, _ in incidence[current] if item in unused]
        if len(candidates) != 1:
            raise SectionLoopError(
                "planar.section_open_contour", f"cycle stopped at vertex={current}"
            )
        index = candidates[0]


def _has_area(loop: list[Vector3]) -> bool:
    if len(loop) < 4:
        return False
    origin = loop[0]
    shifted = [tuple(a - b for a, b in zip(point, origin)) for point in loop]
    area = [0.0, 0.0, 0.0]
    for left, right in zip(shifted, shifted[1:]):
        for axis in range(3):
            i, j = (axis + 1) % 3, (axis + 2) % 3
            area[axis] += left[i] * right[j] - left[j] * right[i]
    return math.sqrt(sum(value * value for value in area)) > 2.0e-9
