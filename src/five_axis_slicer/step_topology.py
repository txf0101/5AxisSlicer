"""Compact OpenCascade topology enumeration for STEP imports."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_REVERSED,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedMapOfShape

from .models import BoundingBox, CadModel, EdgeInfo, FaceInfo, Vector3, VertexInfo

CancelCheck = Callable[[], bool]
CancelGuard = Callable[[CancelCheck | None], None]
SamplePoints = Callable[[object, int], list[Vector3]]


@dataclass(frozen=True, slots=True)
class BodySummary:
    """Serializable body measurements shared by naming and model assembly."""

    bounds: BoundingBox
    volume: float | None
    surface_area: float
    centroid: Vector3
    face_count: int
    edge_count: int
    vertex_count: int
    signature: str


@dataclass(frozen=True, slots=True)
class BodyTopology:
    faces: tuple[FaceInfo, ...]
    edges: tuple[EdgeInfo, ...]
    vertices: tuple[VertexInfo, ...]
    face_shapes: dict[str, object]
    edge_shapes: dict[str, object]
    vertex_shapes: dict[str, object]


@dataclass(frozen=True, slots=True)
class _TopologyIndex:
    faces: TopTools_IndexedMapOfShape
    edges: TopTools_IndexedMapOfShape
    vertices: TopTools_IndexedMapOfShape
    face_ids: dict[int, str]
    edge_ids: dict[int, str]
    vertex_ids: dict[int, str]


@dataclass(frozen=True, slots=True)
class _Adjacency:
    face_edges: dict[int, list[str]]
    edge_faces: dict[int, list[str]]
    edge_vertices: dict[int, list[str]]
    vertex_edges: dict[int, list[str]]


def geometry_signature(kind: str, descriptor: dict[str, Any]) -> str:
    """Return a deterministic signature independent of traversal order."""

    payload = {"kind": str(kind), "geometry": _rounded_json_value(descriptor)}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def shape_bounds(shape: object) -> BoundingBox:
    box = Bnd_Box()
    box.SetGap(0.0)
    BRepBndLib.Add_s(shape, box)
    if box.IsVoid():
        return BoundingBox((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    values = tuple(float(value) for value in box.Get())
    return BoundingBox(
        (values[0], values[1], values[2]),
        (values[3], values[4], values[5]),
    )


def sample_edge_points(edge: object, target_segments: int = 24) -> list[Vector3]:
    curve = BRepAdaptor_Curve(edge)
    first = float(curve.FirstParameter())
    last = float(curve.LastParameter())
    if not math.isfinite(first) or not math.isfinite(last) or first == last:
        return []
    count = max(2, target_segments + 1)
    return [
        _point(curve.Value(first + (last - first) * (index / (count - 1))))
        for index in range(count)
    ]


def edge_length_hint(points: list[Vector3]) -> float | None:
    if len(points) < 2:
        return None
    return sum(math.dist(left, right) for left, right in zip(points, points[1:], strict=False))


def arc_length_midpoint(points: list[Vector3]) -> Vector3 | None:
    """Return the half-length point of a sampled curve polyline."""

    if len(points) < 2:
        return None
    lengths = [math.dist(left, right) for left, right in zip(points, points[1:], strict=False)]
    total = sum(lengths)
    if total <= 1.0e-12:
        return points[0]
    target = total * 0.5
    walked = 0.0
    for left, right, length in zip(points, points[1:], lengths, strict=False):
        if walked + length >= target and length > 0.0:
            ratio = (target - walked) / length
            return (
                left[0] + (right[0] - left[0]) * ratio,
                left[1] + (right[1] - left[1]) * ratio,
                left[2] + (right[2] - left[2]) * ratio,
            )
        walked += length
    return points[-1]


def geometry_candidates(model: CadModel) -> dict[str, list[dict[str, Any]]]:
    """Build coordinate-reference candidates from exact topology."""

    return {"origins": _origin_candidates(model), "directions": _direction_candidates(model)}


def body_summary(kind: str, shape: object) -> BodySummary:
    bounds = shape_bounds(shape)
    surface_area, surface_centroid = _shape_properties(shape, surface=True)
    volume_props = _shape_properties(shape) if kind == "solid" else None
    volume = None if volume_props is None else volume_props[0]
    centroid = (
        volume_props[1] if volume_props is not None and volume_props[0] > 0.0 else surface_centroid
    )
    counts = (
        _indexed_shapes(shape, TopAbs_FACE).Extent(),
        _indexed_shapes(shape, TopAbs_EDGE).Extent(),
        _indexed_shapes(shape, TopAbs_VERTEX).Extent(),
    )
    descriptor = _body_descriptor(kind, bounds, volume, surface_area, centroid, counts)
    return BodySummary(
        bounds, volume, surface_area, centroid, *counts, geometry_signature("body", descriptor)
    )


def enumerate_body_topology(
    body_id: str,
    body_shape: object,
    *,
    cancel_check: CancelCheck | None,
    cancel_guard: CancelGuard,
    sample_points: SamplePoints,
) -> BodyTopology:
    index = _topology_index(body_id, body_shape)
    adjacency = _build_adjacency(index, cancel_check, cancel_guard)
    vertices, vertex_shapes = _enumerate_vertices(
        body_id, index, adjacency, cancel_check, cancel_guard
    )
    edges, edge_shapes = _enumerate_edges(
        body_id, index, adjacency, vertices, cancel_check, cancel_guard, sample_points
    )
    faces, face_shapes = _enumerate_faces(body_id, index, adjacency, cancel_check, cancel_guard)
    return BodyTopology(
        tuple(faces), tuple(edges), tuple(vertices), face_shapes, edge_shapes, vertex_shapes
    )


def body_shapes(root_shape: object) -> list[tuple[str, object]]:
    """Return solids plus free shells/faces without duplicating owned topology."""

    solids = _unique_explored_shapes(root_shape, TopAbs_SOLID, TopoDS.Solid_s)
    owned_shells = _owned_shapes(solids, TopAbs_SHELL, TopoDS.Shell_s)
    free_shells = _free_shapes(root_shape, TopAbs_SHELL, owned_shells, TopoDS.Shell_s)
    owned_faces = _owned_shapes([*solids, *free_shells], TopAbs_FACE, TopoDS.Face_s)
    free_faces = _free_shapes(root_shape, TopAbs_FACE, owned_faces, TopoDS.Face_s)
    return (
        [("solid", shape) for shape in solids]
        + [("sheet", shape) for shape in free_shells]
        + [("sheet", shape) for shape in free_faces]
    )


def _origin_candidates(model: CadModel) -> list[dict[str, Any]]:
    result = [
        {"kind": "vertex", "entity_id": item.vertex_id, "point": list(item.point)}
        for item in model.vertices
    ]
    for edge in model.edges:
        if edge.center is not None and edge.curve_type in {"circle", "ellipse"}:
            result.append(
                {
                    "kind": f"{edge.curve_type}_center",
                    "entity_id": edge.edge_id,
                    "point": list(edge.center),
                }
            )
        if edge.curve_type != "line" and edge.arc_length_midpoint is not None:
            result.append(
                {
                    "kind": "arc_midpoint",
                    "entity_id": edge.edge_id,
                    "point": list(edge.arc_length_midpoint),
                }
            )
    result.extend(
        {"kind": "face_centroid", "entity_id": face.face_id, "point": list(face.centroid)}
        for face in model.faces
    )
    return result


def _direction_candidates(model: CadModel) -> list[dict[str, Any]]:
    result = [
        {
            "kind": "line_edge",
            "entity_id": edge.edge_id,
            "vector": list(edge.axis_direction),
        }
        for edge in model.edges
        if edge.curve_type == "line" and edge.axis_direction is not None
    ]
    for face in model.faces:
        if face.surface_type == "plane" and face.normal is not None:
            result.append(
                {"kind": "plane_normal", "entity_id": face.face_id, "vector": list(face.normal)}
            )
        elif face.surface_type in {"cylinder", "cone"} and face.axis_direction is not None:
            result.append(
                {
                    "kind": "surface_axis",
                    "entity_id": face.face_id,
                    "vector": list(face.axis_direction),
                }
            )
    return result


def _body_descriptor(
    kind: str,
    bounds: BoundingBox,
    volume: float | None,
    surface_area: float,
    centroid: Vector3,
    counts: tuple[int, int, int],
) -> dict[str, Any]:
    return {
        "kind": kind,
        "bounds": bounds.to_json(),
        "volume": volume,
        "surface_area": surface_area,
        "centroid": centroid,
        "face_count": counts[0],
        "edge_count": counts[1],
        "vertex_count": counts[2],
    }


def _topology_index(body_id: str, shape: object) -> _TopologyIndex:
    faces = _indexed_shapes(shape, TopAbs_FACE)
    edges = _indexed_shapes(shape, TopAbs_EDGE)
    vertices = _indexed_shapes(shape, TopAbs_VERTEX)
    return _TopologyIndex(
        faces,
        edges,
        vertices,
        _object_ids(body_id, "face", faces.Extent()),
        _object_ids(body_id, "edge", edges.Extent()),
        _object_ids(body_id, "vertex", vertices.Extent()),
    )


def _object_ids(body_id: str, kind: str, count: int) -> dict[int, str]:
    return {index: f"{body_id}_{kind}_{index:04d}" for index in range(1, count + 1)}


def _build_adjacency(
    index: _TopologyIndex,
    cancel_check: CancelCheck | None,
    cancel_guard: CancelGuard,
) -> _Adjacency:
    adjacency = _Adjacency(
        {item: [] for item in index.face_ids},
        {item: [] for item in index.edge_ids},
        {item: [] for item in index.edge_ids},
        {item: [] for item in index.vertex_ids},
    )
    _map_face_edges(index, adjacency, cancel_check, cancel_guard)
    _map_edge_vertices(index, adjacency, cancel_check, cancel_guard)
    return adjacency


def _map_face_edges(
    index: _TopologyIndex,
    adjacency: _Adjacency,
    cancel_check: CancelCheck | None,
    cancel_guard: CancelGuard,
) -> None:
    for face_index, face_id in index.face_ids.items():
        cancel_guard(cancel_check)
        face = TopoDS.Face_s(index.faces.FindKey(face_index))
        explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while explorer.More():
            edge_index = index.edges.FindIndex(explorer.Current())
            if edge_index > 0:
                _append_unique(adjacency.face_edges[face_index], index.edge_ids[edge_index])
                _append_unique(adjacency.edge_faces[edge_index], face_id)
            explorer.Next()


def _map_edge_vertices(
    index: _TopologyIndex,
    adjacency: _Adjacency,
    cancel_check: CancelCheck | None,
    cancel_guard: CancelGuard,
) -> None:
    for edge_index, edge_id in index.edge_ids.items():
        cancel_guard(cancel_check)
        edge = TopoDS.Edge_s(index.edges.FindKey(edge_index))
        explorer = TopExp_Explorer(edge, TopAbs_VERTEX)
        while explorer.More():
            vertex_index = index.vertices.FindIndex(explorer.Current())
            if vertex_index > 0:
                _append_unique(adjacency.edge_vertices[edge_index], index.vertex_ids[vertex_index])
                _append_unique(adjacency.vertex_edges[vertex_index], edge_id)
            explorer.Next()


def _enumerate_vertices(
    body_id: str,
    index: _TopologyIndex,
    adjacency: _Adjacency,
    cancel_check: CancelCheck | None,
    cancel_guard: CancelGuard,
) -> tuple[list[VertexInfo], dict[str, object]]:
    infos: list[VertexInfo] = []
    shapes: dict[str, object] = {}
    for item_index, object_id in index.vertex_ids.items():
        cancel_guard(cancel_check)
        shape = TopoDS.Vertex_s(index.vertices.FindKey(item_index))
        point = _point(BRep_Tool.Pnt_s(shape))
        edge_ids = adjacency.vertex_edges[item_index]
        descriptor = {"point": point, "edge_degree": len(edge_ids)}
        infos.append(
            VertexInfo(
                object_id,
                body_id,
                item_index,
                point,
                edge_ids,
                geometry_signature("vertex", descriptor),
            )
        )
        shapes[object_id] = shape
    return infos, shapes


def _enumerate_edges(
    body_id: str,
    index: _TopologyIndex,
    adjacency: _Adjacency,
    vertices: list[VertexInfo],
    cancel_check: CancelCheck | None,
    cancel_guard: CancelGuard,
    sample_points: SamplePoints,
) -> tuple[list[EdgeInfo], dict[str, object]]:
    lookup = {item.vertex_id: item for item in vertices}
    infos: list[EdgeInfo] = []
    shapes: dict[str, object] = {}
    for item_index, object_id in index.edge_ids.items():
        cancel_guard(cancel_check)
        shape = TopoDS.Edge_s(index.edges.FindKey(item_index))
        infos.append(
            _edge_info(body_id, item_index, object_id, shape, adjacency, lookup, sample_points)
        )
        shapes[object_id] = shape
    return infos, shapes


def _edge_info(
    body_id: str,
    index: int,
    edge_id: str,
    edge: object,
    adjacency: _Adjacency,
    vertex_lookup: dict[str, VertexInfo],
    sample_points: SamplePoints,
) -> EdgeInfo:
    samples = sample_points(edge, 16)
    curve = BRepAdaptor_Curve(edge)
    curve_type = _enum_kind(curve.GetType())
    midpoint_samples = samples if curve_type == "line" else sample_points(edge, 96)
    exact_length = _shape_properties(edge, linear=True)[0]
    vertex_ids = adjacency.edge_vertices[index]
    endpoints = _edge_endpoints(vertex_ids, vertex_lookup, samples)
    center, axis_direction, radius = _curve_geometry(curve, curve_type)
    descriptor = {
        "curve_type": curve_type,
        "length": exact_length,
        "endpoints": endpoints,
        "center": center,
        "axis_direction": axis_direction,
        "radius": radius,
        "face_degree": len(adjacency.edge_faces[index]),
    }
    return EdgeInfo(
        edge_id=edge_id,
        body_id=body_id,
        index=index,
        point_count=len(samples),
        length_hint=edge_length_hint(samples),
        curve_type=curve_type,
        exact_length=exact_length,
        vertex_ids=vertex_ids,
        face_ids=adjacency.edge_faces[index],
        endpoints=endpoints,
        arc_length_midpoint=arc_length_midpoint(midpoint_samples),
        center=center,
        axis_direction=axis_direction,
        radius=radius,
        signature=geometry_signature("edge", descriptor),
    )


def _enumerate_faces(
    body_id: str,
    index: _TopologyIndex,
    adjacency: _Adjacency,
    cancel_check: CancelCheck | None,
    cancel_guard: CancelGuard,
) -> tuple[list[FaceInfo], dict[str, object]]:
    infos: list[FaceInfo] = []
    shapes: dict[str, object] = {}
    for item_index, object_id in index.face_ids.items():
        cancel_guard(cancel_check)
        shape = TopoDS.Face_s(index.faces.FindKey(item_index))
        infos.append(_face_info(body_id, item_index, object_id, shape, adjacency))
        shapes[object_id] = shape
    return infos, shapes


def _face_info(
    body_id: str,
    index: int,
    face_id: str,
    face: Any,
    adjacency: _Adjacency,
) -> FaceInfo:
    surface = BRepAdaptor_Surface(face, True)
    surface_type = _enum_kind(surface.GetType())
    area, centroid = _shape_properties(face, surface=True)
    reversed_orientation = face.Orientation() == TopAbs_REVERSED
    metadata = _surface_geometry(surface, surface_type, reversed_orientation)
    bounds = shape_bounds(face)
    descriptor = {
        "surface_type": surface_type,
        "area": area,
        "centroid": centroid,
        "bounds": bounds.to_json(),
        "edge_count": len(adjacency.face_edges[index]),
        **metadata,
    }
    return FaceInfo(
        face_id=face_id,
        body_id=body_id,
        index=index,
        surface_type=surface_type,
        area=area,
        centroid=centroid,
        bounds=bounds,
        edge_ids=adjacency.face_edges[index],
        normal=metadata["normal"],
        axis_origin=metadata["axis_origin"],
        axis_direction=metadata["axis_direction"],
        radius=metadata["radius"],
        secondary_radius=metadata["secondary_radius"],
        semi_angle_rad=metadata["semi_angle_rad"],
        orientation="reversed" if reversed_orientation else "forward",
        signature=geometry_signature("face", descriptor),
    )


def _unique_explored_shapes(
    owner: object,
    kind: object,
    converter: Callable[[object], object],
) -> list[object]:
    result: list[object] = []
    seen = TopTools_IndexedMapOfShape()
    explorer = TopExp_Explorer(owner, kind)
    while explorer.More():
        _append_unique_shape(result, seen, converter(explorer.Current()))
        explorer.Next()
    return result


def _owned_shapes(
    owners: list[object],
    kind: object,
    converter: Callable[[object], object],
) -> TopTools_IndexedMapOfShape:
    result = TopTools_IndexedMapOfShape()
    for owner in owners:
        explorer = TopExp_Explorer(owner, kind)
        while explorer.More():
            result.Add(converter(explorer.Current()))
            explorer.Next()
    return result


def _free_shapes(
    root: object,
    kind: object,
    owned: TopTools_IndexedMapOfShape,
    converter: Callable[[object], object],
) -> list[object]:
    result: list[object] = []
    seen = TopTools_IndexedMapOfShape()
    explorer = TopExp_Explorer(root, kind)
    while explorer.More():
        shape = converter(explorer.Current())
        if not owned.Contains(shape):
            _append_unique_shape(result, seen, shape)
        explorer.Next()
    return result


def _append_unique_shape(
    shapes: list[object],
    shape_index: TopTools_IndexedMapOfShape,
    candidate: object,
) -> None:
    if shape_index.Contains(candidate):
        return
    shape_index.Add(candidate)
    shapes.append(candidate)


def _indexed_shapes(shape: object, kind: object) -> TopTools_IndexedMapOfShape:
    result = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, result)
    return result


def _shape_properties(
    shape: object,
    *,
    surface: bool = False,
    linear: bool = False,
) -> tuple[float, Vector3]:
    props = GProp_GProps()
    if linear:
        BRepGProp.LinearProperties_s(shape, props)
    elif surface:
        BRepGProp.SurfaceProperties_s(shape, props)
    else:
        BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass()), _point(props.CentreOfMass())


def _surface_geometry(
    surface: BRepAdaptor_Surface,
    surface_type: str,
    reversed_orientation: bool,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "normal": None,
        "axis_origin": None,
        "axis_direction": None,
        "radius": None,
        "secondary_radius": None,
        "semi_angle_rad": None,
    }
    try:
        _fill_surface_geometry(metadata, surface, surface_type, reversed_orientation)
    except Exception:
        # Trimmed or degenerate analytic adaptors may reject specialised accessors.
        pass
    return metadata


def _fill_surface_geometry(
    result: dict[str, Any],
    surface: BRepAdaptor_Surface,
    kind: str,
    reversed_orientation: bool,
) -> None:
    if kind == "plane":
        plane = surface.Plane()
        normal = _direction(plane.Axis().Direction())
        result["normal"] = tuple(-value for value in normal) if reversed_orientation else normal
        result["axis_origin"] = _point(plane.Location())
    elif kind == "cylinder":
        cylinder = surface.Cylinder()
        _set_axis(result, cylinder)
        result["radius"] = float(cylinder.Radius())
    elif kind == "cone":
        cone = surface.Cone()
        _set_axis(result, cone)
        result["radius"] = float(cone.RefRadius())
        result["semi_angle_rad"] = float(cone.SemiAngle())
    elif kind == "sphere":
        sphere = surface.Sphere()
        _set_axis(result, sphere)
        result["radius"] = float(sphere.Radius())
    elif kind == "torus":
        torus = surface.Torus()
        _set_axis(result, torus)
        result["radius"] = float(torus.MajorRadius())
        result["secondary_radius"] = float(torus.MinorRadius())


def _set_axis(result: dict[str, Any], geometry: Any) -> None:
    result["axis_origin"] = _point(geometry.Location())
    result["axis_direction"] = _direction(geometry.Axis().Direction())


def _curve_geometry(
    curve: BRepAdaptor_Curve,
    curve_type: str,
) -> tuple[Vector3 | None, Vector3 | None, float | None]:
    try:
        if curve_type == "line":
            line = curve.Line()
            return _point(line.Location()), _direction(line.Direction()), None
        if curve_type == "circle":
            circle = curve.Circle()
            return (
                _point(circle.Location()),
                _direction(circle.Axis().Direction()),
                float(circle.Radius()),
            )
        if curve_type == "ellipse":
            ellipse = curve.Ellipse()
            return (
                _point(ellipse.Location()),
                _direction(ellipse.Axis().Direction()),
                float(ellipse.MajorRadius()),
            )
    except Exception:
        pass
    return None, None, None


def _edge_endpoints(
    adjacent_vertex_ids: list[str],
    vertex_lookup: dict[str, VertexInfo],
    samples: list[Vector3],
) -> tuple[Vector3, Vector3] | None:
    if len(adjacent_vertex_ids) >= 2:
        return (
            vertex_lookup[adjacent_vertex_ids[0]].point,
            vertex_lookup[adjacent_vertex_ids[-1]].point,
        )
    if len(samples) >= 2:
        return samples[0], samples[-1]
    return None


def _point(value: Any) -> Vector3:
    return float(value.X()), float(value.Y()), float(value.Z())


def _direction(value: object) -> Vector3:
    vector = _point(value)
    length = math.sqrt(sum(component * component for component in vector))
    if length <= 0.0:
        return 0.0, 0.0, 0.0
    return vector[0] / length, vector[1] / length, vector[2] / length


def _enum_kind(value: object) -> str:
    return str(value).rsplit(".", 1)[-1].removeprefix("GeomAbs_").lower()


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _rounded_json_value(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("geometry signature values must be finite")
        return round(value, 8)
    if isinstance(value, dict):
        return {str(key): _rounded_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_rounded_json_value(item) for item in value]
    return value
