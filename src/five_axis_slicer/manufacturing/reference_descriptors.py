"""Source CS/mm descriptors and geometric value resolution for CAD references."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, TypeGuard, cast

from ..models import BodyInfo, CadModel, EdgeInfo, FaceInfo, VertexInfo
from .coordinates import GeometryReference, PointReference, Vector3

REFERENCE_SIGNATURE_SCHEMA_VERSION = 1
CadEntity = BodyInfo | FaceInfo | EdgeInfo | VertexInfo


class CadDescriptorIndex:
    """One-pass topology lookup and descriptor cache for one CAD model."""

    def __init__(self, model: CadModel) -> None:
        require_cad_model(model)
        self.model = model
        self.body_map = {item.body_id: item for item in model.bodies}
        self.face_map = {item.face_id: item for item in model.faces}
        self.edge_map = {item.edge_id: item for item in model.edges}
        self.vertex_map = {item.vertex_id: item for item in model.vertices}
        self.faces_by_body = _group_by_body(model.faces)
        self.edges_by_body = _group_by_body(model.edges)
        self.vertices_by_body = _group_by_body(model.vertices)
        self.body_descriptors: dict[str, dict[str, Any]] = {}
        self.references: dict[tuple[str, str], GeometryReference] = {}

    def entities(self, geometry_type: str) -> tuple[CadEntity, ...]:
        if geometry_type == "body":
            return tuple(body for body in self.model.bodies if body.is_solid)
        if geometry_type == "shell":
            return tuple(body for body in self.model.bodies if not body.is_solid)
        if geometry_type == "face":
            return tuple(self.model.faces)
        if geometry_type == "edge":
            return tuple(self.model.edges)
        if geometry_type == "vertex":
            return tuple(self.model.vertices)
        raise ValueError(f"unsupported geometry type: {geometry_type!r}")

    def locate(self, object_id: str, geometry_type: str | None) -> tuple[str, CadEntity]:
        identifier = str(object_id).strip()
        if not identifier:
            raise ValueError("object_id must not be empty")
        canonical = None if geometry_type is None else str(geometry_type).strip().lower()
        if canonical in {"body", "shell"}:
            return self._locate_body(identifier, canonical)
        maps: dict[str, Mapping[str, CadEntity]] = {
            "body": self.body_map,
            "face": self.face_map,
            "edge": self.edge_map,
            "vertex": self.vertex_map,
        }
        if canonical is not None:
            return canonical, _mapped_entity(maps, canonical, identifier, geometry_type)
        found = [(kind, items[identifier]) for kind, items in maps.items() if identifier in items]
        if len(found) != 1:
            raise ValueError(f"object_id {identifier!r} does not identify one CAD entity")
        kind, entity = found[0]
        return ("shell" if kind == "body" and not cast(BodyInfo, entity).is_solid else kind), entity

    def _locate_body(self, identifier: str, geometry_type: str) -> tuple[str, BodyInfo]:
        body = self.body_map.get(identifier)
        if body is None:
            raise KeyError(identifier)
        if geometry_type == "body" and not body.is_solid:
            raise ValueError(f"{identifier!r} is not a solid body")
        if geometry_type == "shell" and body.is_solid:
            raise ValueError(f"{identifier!r} is not a shell body")
        return geometry_type, body

    def body_descriptor(self, body: BodyInfo) -> dict[str, Any]:
        descriptor = self.body_descriptors.get(body.body_id)
        if descriptor is None:
            descriptor = _body_descriptor(self, body)
            self.body_descriptors[body.body_id] = descriptor
        return descriptor

    def reference(self, object_id: str, geometry_type: str | None = None) -> GeometryReference:
        entity_type, entity = self.locate(object_id, geometry_type)
        object_id = entity_id(entity_type, entity)
        cache_key = entity_type, object_id
        if cached := self.references.get(cache_key):
            return cached
        parent_id = _parent_body_id(entity_type, entity)
        parent = None if parent_id is None else self.body_map.get(parent_id)
        signature = {
            "schema_version": REFERENCE_SIGNATURE_SCHEMA_VERSION,
            "geometry_type": entity_type,
            "descriptor": _entity_descriptor(self, entity_type, entity),
            "parent_body": None if parent is None else self.body_descriptor(parent),
            "kernel_signature": str(getattr(entity, "signature", "")),
        }
        assembly_name = _assembly_name(entity_type, entity, parent)
        result = GeometryReference(object_id, entity_type, signature, parent_id, assembly_name)
        self.references[cache_key] = result
        return result


def geometry_reference(
    model: CadModel,
    object_id: str,
    geometry_type: str | None = None,
) -> GeometryReference:
    return CadDescriptorIndex(model).reference(object_id, geometry_type)


def project_point_to_face(
    model: CadModel,
    face_id: str,
    point_in_source_mm: Sequence[float],
) -> Vector3:
    """Project a Source CS/mm point onto an authoritative trimmed face."""

    require_cad_model(model)
    point = vector3_value(point_in_source_mm, name="point_in_source_mm")
    identifier = str(face_id).strip()
    face = model.face_map.get(identifier)
    if face is None:
        raise KeyError(identifier)
    if shape := model.face_shapes.get(identifier):
        if projected := _project_point_to_occ_face(shape, point):
            return projected
    return _project_point_to_planar_face(face, point)


def resolve_point(
    reference: PointReference,
    rebound_geometry: GeometryReference,
    model: CadModel,
    *,
    source_model: CadModel | None,
) -> Vector3:
    object_id = rebound_geometry.object_id
    kind = reference.reference_type
    if kind == "vertex":
        return model.vertex_map[object_id].point
    if kind in {"circle_center", "ellipse_center"}:
        return _edge_center(model.edge_map[object_id], kind)
    if kind == "arc_midpoint":
        point = model.edge_map[object_id].arc_length_midpoint
        if point is None:
            raise ValueError("selected edge has no arc-length midpoint")
        return point
    if kind == "face_centroid":
        return model.face_map[object_id].centroid
    if kind == "face_pick":
        return _resolve_face_pick(reference, model, object_id, source_model)
    raise ValueError(f"unsupported point reference type: {kind!r}")


def resolve_direction(
    reference_type: str,
    rebound_geometry: GeometryReference,
    model: CadModel,
) -> Vector3:
    object_id = rebound_geometry.object_id
    if reference_type == "line_edge":
        return _line_direction(model.edge_map[object_id])
    face = model.face_map[object_id]
    if reference_type == "plane_normal":
        if face.surface_type != "plane" or face.normal is None:
            raise ValueError("selected face has no plane normal")
        return face.normal
    if reference_type == "surface_axis":
        if face.surface_type not in {"cylinder", "cone"} or face.axis_direction is None:
            raise ValueError("selected face has no supported surface axis")
        return face.axis_direction
    raise ValueError(f"unsupported direction reference type: {reference_type!r}")


def rebound_two_point(
    old_point: Vector3 | None,
    old_geometry: GeometryReference | None,
    rebound_geometry: GeometryReference | None,
    model: CadModel,
) -> Vector3 | None:
    if rebound_geometry is None:
        return old_point
    object_id = rebound_geometry.object_id
    if rebound_geometry.geometry_type == "vertex":
        return model.vertex_map[object_id].point
    if rebound_geometry.geometry_type == "face":
        return model.face_map[object_id].centroid
    if rebound_geometry.geometry_type == "edge":
        return _nearest_edge_point(model.edge_map[object_id], old_point)
    if old_geometry is not None and rebound_geometry.geometry_type in {"body", "shell"}:
        return model.body_map[object_id].centroid
    return old_point


def align_direction(direction: Vector3, previous: Vector3 | None) -> Vector3:
    if previous is not None and dot(direction, previous) < 0.0:
        return -direction[0], -direction[1], -direction[2]
    return direction


def entity_id(geometry_type: str, entity: CadEntity) -> str:
    if geometry_type in {"body", "shell"}:
        return cast(BodyInfo, entity).body_id
    if geometry_type == "face":
        return cast(FaceInfo, entity).face_id
    if geometry_type == "edge":
        return cast(EdgeInfo, entity).edge_id
    if geometry_type == "vertex":
        return cast(VertexInfo, entity).vertex_id
    raise ValueError(geometry_type)


def require_cad_model(model: CadModel) -> None:
    if not isinstance(model, CadModel):
        raise TypeError("model must be CadModel")


def subtract(left: Sequence[float], right: Sequence[float]) -> Vector3:
    return (
        float(left[0]) - float(right[0]),
        float(left[1]) - float(right[1]),
        float(left[2]) - float(right[2]),
    )


def add(left: Sequence[float], right: Sequence[float]) -> Vector3:
    return (
        float(left[0]) + float(right[0]),
        float(left[1]) + float(right[1]),
        float(left[2]) + float(right[2]),
    )


def dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(left, right, strict=False))


def _group_by_body(items: Iterable[Any]) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for item in items:
        result.setdefault(item.body_id, []).append(item)
    return result


def _mapped_entity(
    maps: Mapping[str, Mapping[str, CadEntity]],
    geometry_type: str,
    identifier: str,
    original_type: str | None,
) -> CadEntity:
    selected = maps.get(geometry_type)
    if selected is None:
        raise ValueError(f"unsupported geometry type: {original_type!r}")
    entity = selected.get(identifier)
    if entity is None:
        raise KeyError(identifier)
    return entity


def _assembly_name(
    geometry_type: str,
    entity: CadEntity,
    parent: BodyInfo | None,
) -> str | None:
    if geometry_type in {"body", "shell"}:
        return cast(BodyInfo, entity).assembly_path
    return None if parent is None else parent.assembly_path


def _body_descriptor(index: CadDescriptorIndex, body: BodyInfo) -> dict[str, Any]:
    faces = index.faces_by_body.get(body.body_id, ())
    edges = index.edges_by_body.get(body.body_id, ())
    vertices = index.vertices_by_body.get(body.body_id, ())
    return {
        "kind": body.kind,
        "assembly_path": body.assembly_path,
        "bounds_mm": _bounds_descriptor(body.bounds),
        "dimensions_mm": _bounds_dimensions(body.bounds),
        "volume_mm3": body.volume,
        "surface_area_mm2": body.surface_area,
        "centroid_mm": _vector(body.centroid),
        "topology": {
            "face_count": len(faces) if faces else len(body.face_ids),
            "edge_count": len(edges) if edges else len(body.edge_ids),
            "vertex_count": len(vertices) if vertices else len(body.vertex_ids),
            "surface_types": _histogram(face.surface_type for face in faces),
            "curve_types": _histogram(edge.curve_type for edge in edges),
            "vertex_edge_degrees": sorted(len(vertex.edge_ids) for vertex in vertices),
        },
    }


def _face_descriptor(index: CadDescriptorIndex, face: FaceInfo) -> dict[str, Any]:
    adjacent = [index.edge_map[item] for item in face.edge_ids if item in index.edge_map]
    return {
        "surface_type": face.surface_type,
        "area_mm2": face.area,
        "centroid_mm": _vector(face.centroid),
        "bounds_mm": _bounds_descriptor(face.bounds),
        "dimensions_mm": _bounds_dimensions(face.bounds),
        "normal": _canonical_axis(face.normal),
        "axis_origin_mm": _vector(face.axis_origin),
        "axis_direction": _canonical_axis(face.axis_direction),
        "radius_mm": face.radius,
        "secondary_radius_mm": face.secondary_radius,
        "semi_angle_rad": face.semi_angle_rad,
        "orientation": face.orientation,
        "adjacency": {
            "edge_count": len(face.edge_ids),
            "curve_types": sorted(edge.curve_type for edge in adjacent),
            "edge_face_degrees": sorted(len(edge.face_ids) for edge in adjacent),
        },
    }


def _edge_descriptor(index: CadDescriptorIndex, edge: EdgeInfo) -> dict[str, Any]:
    faces = [index.face_map[item] for item in edge.face_ids if item in index.face_map]
    vertices = [index.vertex_map[item] for item in edge.vertex_ids if item in index.vertex_map]
    points = list(edge.endpoints or ())
    points.extend(point for point in (edge.center, edge.arc_length_midpoint) if point is not None)
    return {
        "curve_type": edge.curve_type,
        "length_mm": edge.exact_length if edge.exact_length is not None else edge.length_hint,
        "bounds_mm": _point_bounds(points),
        "endpoints_mm": _canonical_endpoints(edge.endpoints),
        "arc_length_midpoint_mm": _vector(edge.arc_length_midpoint),
        "center_mm": _vector(edge.center),
        "axis_direction": _canonical_axis(edge.axis_direction),
        "radius_mm": edge.radius,
        "adjacency": {
            "vertex_count": len(edge.vertex_ids),
            "face_count": len(edge.face_ids),
            "face_surface_types": sorted(face.surface_type for face in faces),
            "vertex_edge_degrees": sorted(len(vertex.edge_ids) for vertex in vertices),
        },
    }


def _vertex_descriptor(index: CadDescriptorIndex, vertex: VertexInfo) -> dict[str, Any]:
    edges = [index.edge_map[item] for item in vertex.edge_ids if item in index.edge_map]
    face_ids = {face_id for edge in edges for face_id in edge.face_ids}
    return {
        "point_mm": _vector(vertex.point),
        "bounds_mm": {"minimum": _vector(vertex.point), "maximum": _vector(vertex.point)},
        "adjacency": {
            "edge_count": len(vertex.edge_ids),
            "curve_types": sorted(edge.curve_type for edge in edges),
            "face_surface_types": sorted(
                index.face_map[item].surface_type for item in face_ids if item in index.face_map
            ),
        },
    }


def _entity_descriptor(
    index: CadDescriptorIndex,
    geometry_type: str,
    entity: CadEntity,
) -> dict[str, Any]:
    factories: dict[str, Callable[[], dict[str, Any]]] = {
        "body": lambda: index.body_descriptor(cast(BodyInfo, entity)),
        "shell": lambda: index.body_descriptor(cast(BodyInfo, entity)),
        "face": lambda: _face_descriptor(index, cast(FaceInfo, entity)),
        "edge": lambda: _edge_descriptor(index, cast(EdgeInfo, entity)),
        "vertex": lambda: _vertex_descriptor(index, cast(VertexInfo, entity)),
    }
    try:
        return factories[geometry_type]()
    except KeyError as exc:
        raise ValueError(f"unsupported geometry type: {geometry_type!r}") from exc


def _parent_body_id(geometry_type: str, entity: CadEntity) -> str | None:
    return None if geometry_type in {"body", "shell"} else entity.body_id


def _edge_center(edge: EdgeInfo, reference_type: str) -> Vector3:
    expected_curve = reference_type.removesuffix("_center")
    if edge.curve_type != expected_curve or edge.center is None:
        raise ValueError("selected edge does not expose the requested centre")
    return edge.center


def _resolve_face_pick(
    reference: PointReference,
    model: CadModel,
    object_id: str,
    source_model: CadModel | None,
) -> Vector3:
    if reference.point_in_source_mm is None or reference.geometry is None:
        raise ValueError("face pick has no source point or geometry")
    face = model.face_map[object_id]
    descriptor = reference.geometry.signature.get("descriptor", {})
    old_centroid = descriptor.get("centroid_mm") if isinstance(descriptor, Mapping) else None
    if not _is_vector3(old_centroid) and source_model is not None:
        old_face = source_model.face_map.get(reference.geometry.object_id)
        if old_face is not None:
            old_centroid = old_face.centroid
    candidate = reference.point_in_source_mm
    if _is_vector3(old_centroid):
        candidate = add(candidate, subtract(face.centroid, old_centroid))
    return project_point_to_face(model, object_id, candidate)


def _line_direction(edge: EdgeInfo) -> Vector3:
    if edge.curve_type != "line":
        raise ValueError("selected edge is not linear")
    if edge.axis_direction is not None:
        return edge.axis_direction
    if edge.endpoints is not None:
        return subtract(edge.endpoints[1], edge.endpoints[0])
    raise ValueError("selected line has no direction")


def _nearest_edge_point(edge: EdgeInfo, old_point: Vector3 | None) -> Vector3:
    values = (
        edge.center,
        edge.arc_length_midpoint,
        None if edge.endpoints is None else edge.endpoints[0],
        None if edge.endpoints is None else edge.endpoints[1],
    )
    candidates = [point for point in values if point is not None]
    if not candidates:
        raise ValueError("edge has no resolvable point")
    return (
        candidates[0]
        if old_point is None
        else min(candidates, key=lambda p: math.dist(p, old_point))
    )


def _project_point_to_planar_face(face: FaceInfo, point: Vector3) -> Vector3:
    if face.surface_type != "plane" or face.normal is None:
        raise ValueError("authoritative face projection is unavailable")
    normal = _unit_vector(face.normal)
    origin = face.axis_origin or face.centroid
    offset = dot(subtract(point, origin), normal)
    projected = subtract(point, tuple(offset * value for value in normal))
    if not _point_in_bounds(projected, face.bounds, tolerance=1.0e-7):
        raise ValueError("point projects outside the trimmed planar face bounds")
    return projected


def _project_point_to_occ_face(face_shape: object, point: Vector3) -> Vector3 | None:
    """Use OCP lazily so descriptor-only domain tests remain kernel independent."""

    try:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape
        from OCP.gp import gp_Pnt
    except ImportError:
        return None
    try:
        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
        distance = BRepExtrema_DistShapeShape(vertex, face_shape)
        distance.Perform()
        if not distance.IsDone() or distance.NbSolution() < 1:
            return None
        projected = distance.PointOnShape2(1)
        result = float(projected.X()), float(projected.Y()), float(projected.Z())
        return result if all(math.isfinite(item) for item in result) else None
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


def _histogram(values: Iterable[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def _bounds_descriptor(bounds: Any) -> dict[str, list[float]] | None:
    if bounds is None:
        return None
    return {
        "minimum": list(_vector(bounds.minimum) or ()),
        "maximum": list(_vector(bounds.maximum) or ()),
    }


def _bounds_dimensions(bounds: Any) -> list[float] | None:
    if bounds is None:
        return None
    return [
        float(right) - float(left)
        for left, right in zip(bounds.minimum, bounds.maximum, strict=False)
    ]


def _point_bounds(points: Sequence[Vector3]) -> dict[str, list[float]] | None:
    if not points:
        return None
    return {
        "minimum": [min(point[axis] for point in points) for axis in range(3)],
        "maximum": [max(point[axis] for point in points) for axis in range(3)],
    }


def _canonical_endpoints(
    endpoints: tuple[Vector3, Vector3] | None,
) -> list[list[float]] | None:
    return None if endpoints is None else [list(point) for point in sorted(endpoints)]


def _canonical_axis(vector: Vector3 | None) -> list[float] | None:
    if vector is None:
        return None
    length = math.sqrt(sum(float(value) ** 2 for value in vector))
    if not math.isfinite(length) or length <= 1.0e-15:
        return None
    result = [float(value) / length for value in vector]
    for value in result:
        if abs(value) > 1.0e-14:
            return [-item for item in result] if value < 0.0 else result
    return result


def _vector(value: Sequence[float] | None) -> list[float] | None:
    return None if value is None else [float(item) for item in value]


def _is_vector3(value: Any) -> TypeGuard[Sequence[float]]:
    return (
        isinstance(value, tuple | list)
        and len(value) == 3
        and all(isinstance(item, int | float) and math.isfinite(float(item)) for item in value)
    )


def vector3_value(value: Sequence[float], *, name: str) -> Vector3:
    if not _is_vector3(value):
        raise ValueError(f"{name} must contain three finite numbers")
    return float(value[0]), float(value[1]), float(value[2])


def _unit_vector(value: Sequence[float]) -> Vector3:
    length = math.sqrt(sum(float(item) ** 2 for item in value))
    if not math.isfinite(length) or length <= 1.0e-15:
        raise ValueError("surface normal must be finite and non-zero")
    return float(value[0]) / length, float(value[1]) / length, float(value[2]) / length


def _point_in_bounds(point: Sequence[float], bounds: Any, *, tolerance: float) -> bool:
    return all(
        float(lower) - tolerance <= float(value) <= float(upper) + tolerance
        for value, lower, upper in zip(point, bounds.minimum, bounds.maximum, strict=False)
    )
