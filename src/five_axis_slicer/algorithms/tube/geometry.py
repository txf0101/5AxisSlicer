"""Circular tube recognition from the exact STEP topology descriptors.

The supported graph is deliberately small: one unbranched chain made from
cylindrical and toroidal faces with constant inner and outer radii. Circular
port edges select direction. Kernel edges remain evidence; they are never
treated as centreline geometry.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from ...manufacturing.setup import TubeGeometrySelection
from ...models import CadModel, EdgeInfo, FaceInfo, Vector3

_TOLERANCE_MM = 1.0e-5


class TubeRecognitionError(ValueError):
    """A stable, localisable failure in the restricted Tube recogniser."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = str(code)
        self.detail = str(detail)
        super().__init__(f"{self.code}: {self.detail}")


@dataclass(frozen=True, slots=True)
class CenterlinePrimitive:
    kind: str
    start: Vector3
    end: Vector3
    length_mm: float
    source_face_id: str = "manual"
    center: Vector3 | None = None
    axis: Vector3 | None = None
    sweep_rad: float = 0.0

    def __post_init__(self) -> None:
        kind = str(self.kind).lower()
        if kind not in {"line", "arc"}:
            raise ValueError(f"unsupported centerline primitive: {kind}")
        if not math.isfinite(self.length_mm) or self.length_mm <= 0.0:
            raise ValueError("centerline primitive length must be positive")
        if kind == "arc" and (self.center is None or self.axis is None):
            raise ValueError("arc centerline primitive requires center and axis")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "start", _vector3(self.start))
        object.__setattr__(self, "end", _vector3(self.end))
        if self.center is not None:
            object.__setattr__(self, "center", _vector3(self.center))
        if self.axis is not None:
            object.__setattr__(self, "axis", _unit(self.axis))

    def reversed(self) -> CenterlinePrimitive:
        return CenterlinePrimitive(
            self.kind,
            self.end,
            self.start,
            self.length_mm,
            self.source_face_id,
            self.center,
            self.axis,
            -self.sweep_rad,
        )

    def point_tangent(self, fraction: float) -> tuple[Vector3, Vector3]:
        value = min(1.0, max(0.0, float(fraction)))
        if self.kind == "line":
            direction = _unit(_subtract(self.end, self.start))
            return _add(self.start, _scale(_subtract(self.end, self.start), value)), direction
        assert self.center is not None and self.axis is not None
        radial = _subtract(self.start, self.center)
        rotated = _rotate(radial, self.axis, self.sweep_rad * value)
        point = _add(self.center, rotated)
        tangent = _unit(_cross(self.axis, rotated))
        if self.sweep_rad < 0.0:
            tangent = _scale(tangent, -1.0)
        return point, tangent


@dataclass(frozen=True, slots=True)
class TubeFeature:
    tube_body_id: str
    entry_port_id: str
    exit_port_id: str
    outer_radius_mm: float
    inner_radius_mm: float
    centerline: tuple[CenterlinePrimitive, ...]
    source: str = "step_cylinder_torus"

    def __post_init__(self) -> None:
        segments = tuple(self.centerline)
        if not segments:
            raise ValueError("Tube centerline must contain at least one primitive")
        if self.outer_radius_mm <= self.inner_radius_mm or self.inner_radius_mm <= 0.0:
            raise ValueError("Tube radii must satisfy outer > inner > 0")
        for left, right in zip(segments, segments[1:]):
            if math.dist(left.end, right.start) > _TOLERANCE_MM:
                raise ValueError("Tube centerline primitives are disconnected")
        object.__setattr__(self, "centerline", segments)

    @property
    def wall_thickness_mm(self) -> float:
        return self.outer_radius_mm - self.inner_radius_mm

    @property
    def centerline_length_mm(self) -> float:
        return sum(item.length_mm for item in self.centerline)

    @property
    def path_radius_mm(self) -> float:
        return (self.outer_radius_mm + self.inner_radius_mm) * 0.5

    def point_tangent_at(self, distance_mm: float) -> tuple[Vector3, Vector3]:
        distance = min(self.centerline_length_mm, max(0.0, float(distance_mm)))
        walked = 0.0
        for segment in self.centerline:
            if distance <= walked + segment.length_mm + _TOLERANCE_MM:
                return segment.point_tangent((distance - walked) / segment.length_mm)
            walked += segment.length_mm
        return self.centerline[-1].point_tangent(1.0)


def recognise_tube(model: CadModel, selection: TubeGeometrySelection) -> TubeFeature:
    """Recognise one directed cylinder/torus chain selected by the user."""

    if not selection.is_complete:
        raise TubeRecognitionError("tube.geometry_roles_incomplete", "four geometry roles required")
    tube_body = selection.tube_body
    entry_port_ref = selection.entry_port
    exit_port_ref = selection.exit_port
    assert tube_body is not None and entry_port_ref is not None and exit_port_ref is not None
    body_id = tube_body.object_id
    body = model.body_map.get(body_id)
    if body is None or not body.is_solid:
        raise TubeRecognitionError("tube.body_missing", body_id)
    entry = _circular_port(model, entry_port_ref.object_id, body_id)
    exit_port = _circular_port(model, exit_port_ref.object_id, body_id)
    assert entry.center is not None and exit_port.center is not None
    outer_radius, inner_radius = _constant_radii(model, body_id)
    if not _close(entry.radius, outer_radius) or not _close(exit_port.radius, outer_radius):
        raise TubeRecognitionError(
            "tube.port_not_outer_boundary", "ports must use outer circular edges"
        )
    raw = (
        _manual_edge_primitives(model, selection)
        if selection.manual_centerline_edges
        else _surface_primitives(model, body_id, outer_radius)
    )
    ordered = _ordered_chain(raw, entry.center, exit_port.center)
    return TubeFeature(
        body_id,
        entry.edge_id,
        exit_port.edge_id,
        outer_radius,
        inner_radius,
        ordered,
        "manual_edges" if selection.manual_centerline_edges else "step_cylinder_torus",
    )


def _manual_edge_primitives(
    model: CadModel,
    selection: TubeGeometrySelection,
) -> tuple[CenterlinePrimitive, ...]:
    result: list[CenterlinePrimitive] = []
    for reference in selection.manual_centerline_edges:
        edge = _manual_edge(model, reference.object_id)
        if edge.endpoints is None:
            raise TubeRecognitionError(
                "tube.manual_centerline_edge_open_geometry_missing",
                reference.object_id,
            )
        start, end = edge.endpoints
        if edge.curve_type == "line":
            result.append(
                CenterlinePrimitive(
                    "line",
                    start,
                    end,
                    math.dist(start, end),
                    reference.object_id,
                )
            )
            continue
        if edge.curve_type != "circle" or edge.center is None or edge.axis_direction is None:
            raise TubeRecognitionError(
                "tube.manual_centerline_edge_unsupported",
                reference.object_id,
            )
        result.append(_manual_arc_primitive(edge, start, end, reference.object_id))
    if not result:
        raise TubeRecognitionError("tube.manual_centerline_too_short", "no selected edges")
    return tuple(result)


def _manual_arc_primitive(
    edge: EdgeInfo,
    start: Vector3,
    end: Vector3,
    edge_id: str,
) -> CenterlinePrimitive:
    if edge.center is None or edge.axis_direction is None:
        raise TubeRecognitionError("tube.manual_centerline_edge_unsupported", edge_id)
    radius = edge.radius
    if radius is None or radius <= _TOLERANCE_MM:
        raise TubeRecognitionError("tube.manual_centerline_arc_incomplete", edge_id)
    left = _unit(_subtract(start, edge.center))
    right = _unit(_subtract(end, edge.center))
    axis = _unit(edge.axis_direction)
    signed_minor = math.atan2(_dot(axis, _cross(left, right)), _dot(left, right))
    if abs(signed_minor) <= 1.0e-10:
        raise TubeRecognitionError("tube.manual_centerline_arc_ambiguous", edge_id)
    length = edge.exact_length or edge.length_hint or abs(radius * signed_minor)
    return CenterlinePrimitive(
        "arc",
        start,
        end,
        float(length),
        edge_id,
        edge.center,
        axis,
        math.copysign(float(length) / radius, signed_minor),
    )


def _manual_edge(model: CadModel, edge_id: str) -> EdgeInfo:
    edge = model.edge_map.get(edge_id)
    if edge is None:
        raise TubeRecognitionError("tube.manual_centerline_edge_missing", edge_id)
    return edge


def manual_tube_feature(
    points: Iterable[Vector3],
    *,
    outer_radius_mm: float,
    inner_radius_mm: float,
    tube_body_id: str = "manual-tube",
) -> TubeFeature:
    values = tuple(_vector3(point) for point in points)
    if len(values) < 2:
        raise TubeRecognitionError(
            "tube.manual_centerline_too_short", "at least two points required"
        )
    segments = tuple(
        CenterlinePrimitive("line", left, right, math.dist(left, right))
        for left, right in zip(values, values[1:])
        if math.dist(left, right) > _TOLERANCE_MM
    )
    if len(segments) != len(values) - 1:
        raise TubeRecognitionError("tube.manual_centerline_repeated_point", "zero-length span")
    return TubeFeature(
        tube_body_id,
        "manual-entry",
        "manual-exit",
        float(outer_radius_mm),
        float(inner_radius_mm),
        segments,
        "manual_polyline",
    )


def _circular_port(model: CadModel, edge_id: str, body_id: str) -> EdgeInfo:
    edge = model.edge_map.get(edge_id)
    if edge is None or edge.body_id != body_id:
        raise TubeRecognitionError("tube.port_body_mismatch", edge_id)
    if edge.curve_type != "circle" or edge.center is None or edge.radius is None:
        raise TubeRecognitionError("tube.port_not_circular", edge_id)
    return edge


def _constant_radii(model: CadModel, body_id: str) -> tuple[float, float]:
    faces = [face for face in model.faces if face.body_id == body_id]
    section_radii = [
        value for face in faces for value in (_section_radius(face),) if value is not None
    ]
    distinct = _cluster_values(section_radii)
    if len(distinct) != 2:
        raise TubeRecognitionError(
            "tube.cross_section_not_constant",
            f"expected two constant radii, measured {distinct}",
        )
    inner, outer = distinct
    return outer, inner


def _section_radius(face: FaceInfo) -> float | None:
    if face.surface_type == "cylinder":
        return face.radius
    if face.surface_type == "torus":
        return face.secondary_radius
    return None


def _cluster_values(values: Iterable[float], tolerance: float = _TOLERANCE_MM) -> list[float]:
    clusters: list[list[float]] = []
    for value in sorted(float(item) for item in values):
        if not clusters or abs(value - sum(clusters[-1]) / len(clusters[-1])) > tolerance:
            clusters.append([value])
        else:
            clusters[-1].append(value)
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _surface_primitives(
    model: CadModel, body_id: str, outer_radius: float
) -> tuple[CenterlinePrimitive, ...]:
    edges = model.edge_map
    result: list[CenterlinePrimitive] = []
    for face in model.faces:
        if face.body_id != body_id or not _close(_section_radius(face), outer_radius):
            continue
        boundary = [
            edges[edge_id]
            for edge_id in face.edge_ids
            if edge_id in edges
            and edges[edge_id].curve_type == "circle"
            and edges[edge_id].center is not None
            and _close(edges[edge_id].radius, outer_radius)
        ]
        if len(boundary) != 2:
            raise TubeRecognitionError("tube.surface_boundary_ambiguous", face.face_id)
        start, end = boundary[0].center, boundary[1].center
        assert start is not None and end is not None
        if face.surface_type == "cylinder":
            result.append(
                CenterlinePrimitive("line", start, end, math.dist(start, end), face.face_id)
            )
        elif face.surface_type == "torus":
            result.append(_torus_primitive(face, start, end))
    if not result:
        raise TubeRecognitionError("tube.centerline_not_found", body_id)
    return tuple(result)


def _torus_primitive(face: FaceInfo, start: Vector3, end: Vector3) -> CenterlinePrimitive:
    if face.axis_origin is None or face.axis_direction is None or face.radius is None:
        raise TubeRecognitionError("tube.torus_geometry_incomplete", face.face_id)
    left = _unit(_subtract(start, face.axis_origin))
    right = _unit(_subtract(end, face.axis_origin))
    axis = _unit(face.axis_direction)
    sweep = math.atan2(_dot(axis, _cross(left, right)), _dot(left, right))
    if abs(sweep) <= 1.0e-10:
        raise TubeRecognitionError("tube.torus_sweep_ambiguous", face.face_id)
    return CenterlinePrimitive(
        "arc",
        start,
        end,
        abs(face.radius * sweep),
        face.face_id,
        face.axis_origin,
        axis,
        sweep,
    )


def _ordered_chain(
    primitives: tuple[CenterlinePrimitive, ...], entry: Vector3, exit_point: Vector3
) -> tuple[CenterlinePrimitive, ...]:
    unused = list(primitives)
    ordered: list[CenterlinePrimitive] = []
    current = entry
    while unused:
        matches: list[tuple[int, CenterlinePrimitive]] = []
        for index, primitive in enumerate(unused):
            if math.dist(primitive.start, current) <= _TOLERANCE_MM:
                matches.append((index, primitive))
            elif math.dist(primitive.end, current) <= _TOLERANCE_MM:
                matches.append((index, primitive.reversed()))
        if len(matches) != 1:
            code = "tube.centerline_branch" if len(matches) > 1 else "tube.centerline_disconnected"
            raise TubeRecognitionError(code, f"at {current}")
        index, primitive = matches[0]
        ordered.append(primitive)
        current = primitive.end
        unused.pop(index)
    if math.dist(current, exit_point) > _TOLERANCE_MM:
        raise TubeRecognitionError("tube.exit_not_reached", f"ended at {current}")
    return tuple(ordered)


def _vector3(value: Iterable[float]) -> Vector3:
    result = tuple(float(item) for item in value)
    if len(result) != 3 or not all(math.isfinite(item) for item in result):
        raise ValueError("expected three finite coordinates")
    return result  # type: ignore[return-value]


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


def _rotate(value: Vector3, axis: Vector3, angle: float) -> Vector3:
    cosine, sine = math.cos(angle), math.sin(angle)
    return _add(
        _add(_scale(value, cosine), _scale(_cross(axis, value), sine)),
        _scale(axis, _dot(axis, value) * (1.0 - cosine)),
    )


def _close(left: float | None, right: float | None) -> bool:
    return left is not None and right is not None and abs(left - right) <= _TOLERANCE_MM


__all__ = [
    "CenterlinePrimitive",
    "TubeFeature",
    "TubeRecognitionError",
    "manual_tube_feature",
    "recognise_tube",
]
