"""FAN09 workpiece-frame transfer candidates and exact linear clearance checks.

These checks concern a spherical tip envelope on linear segments. They do not
qualify rotary machine interpolation, the full nozzle, fixture or A90 indexing.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.gp import gp_Pnt

from ...models import Vector3


@dataclass(frozen=True, slots=True)
class TravelClearance:
    segment_count: int
    minimum_clearance_mm: float
    collisions: tuple[tuple[int, str], ...]
    coverage: str = "linear workpiece-frame segments, spherical tip only"
    machine_qualified: bool = False


def radial_transfer(
    start: Vector3, end: Vector3, *, outside_radius_mm: float, chord_error_mm: float = 0.02
) -> tuple[Vector3, ...]:
    """Depart radially, traverse outside a supplied obstacle bound, approach.

    The caller must check departure/approach against the already printed state.
    The outside radius must include the nozzle radius and a positive clearance.
    """
    values = (*start, *end, outside_radius_mm, chord_error_mm)
    if not all(math.isfinite(v) for v in values) or chord_error_mm <= 0:
        raise ValueError("invalid radial transfer parameters")
    radii = (math.hypot(*start[:2]), math.hypot(*end[:2]))
    if min(radii) <= 0 or outside_radius_mm <= max(radii) + chord_error_mm:
        raise ValueError("outside radius must exceed both endpoints")
    a, b = math.atan2(start[1], start[0]), math.atan2(end[1], end[0])
    delta = math.remainder(b - a, 2 * math.pi)
    step = 2 * math.acos(max(-1.0, 1 - chord_error_mm / outside_radius_mm))
    count = max(1, math.ceil(abs(delta) / step))
    arc = tuple(
        (
            outside_radius_mm * math.cos(a + delta * i / count),
            outside_radius_mm * math.sin(a + delta * i / count),
            start[2] + (end[2] - start[2]) * i / count,
        )
        for i in range(count + 1)
    )
    return (start, *arc, end)


def check_linear_clearance(
    points: tuple[Vector3, ...], printed_shapes: dict[str, object], *, tip_radius_mm: float
) -> TravelClearance:
    if not math.isfinite(tip_radius_mm) or tip_radius_mm <= 0 or len(points) < 2:
        raise ValueError("positive tip radius and at least two points required")
    if not printed_shapes:
        raise ValueError("explicit already-printed obstacles required")
    minimum = math.inf
    collisions = []
    for index, (start, end) in enumerate(zip(points, points[1:])):
        if math.dist(start, end) < 1e-9:
            raise ValueError("zero-length transfer segment")
        edge = BRepBuilderAPI_MakeEdge(gp_Pnt(*start), gp_Pnt(*end)).Edge()
        for body_id, shape in printed_shapes.items():
            distance = BRepExtrema_DistShapeShape(edge, shape)
            if not distance.IsDone():
                raise ValueError("fan.travel_clearance_failed")
            clearance = distance.Value() - tip_radius_mm
            minimum = min(minimum, clearance)
            if clearance <= 0:
                collisions.append((index, body_id))
    return TravelClearance(len(points) - 1, minimum, tuple(collisions))
