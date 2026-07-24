from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.STEPConstruct import STEPConstruct_UnitContext
from OCP.StepData import StepData_Factors, StepData_StepModel
from OCP.StepGeom import (
    StepGeom_GeomRepContextAndGlobUnitAssCtxAndGlobUncertaintyAssCtx,
    StepGeom_GeometricRepresentationContextAndGlobalUnitAssignedContext,
)
from OCP.TColStd import TColStd_SequenceOfAsciiString
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_AttributeIterator, TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_REVERSED,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool
from OCP.XCAFApp import XCAFApp_Application
from OCP.gp import gp_Pnt, gp_Trsf

from .models import (
    BodyInfo,
    BoundingBox,
    CadModel,
    CadUnitInfo,
    EdgeInfo,
    FaceInfo,
    Vector3,
    VertexInfo,
)


PALETTE: tuple[tuple[float, float, float], ...] = (
    (0.86, 0.86, 0.84),
    (0.72, 0.78, 0.84),
    (0.82, 0.76, 0.68),
    (0.64, 0.74, 0.70),
    (0.78, 0.72, 0.82),
    (0.84, 0.72, 0.72),
    (0.68, 0.72, 0.78),
    (0.78, 0.80, 0.68),
)
STEP_SUFFIXES = {".step", ".stp"}
_FILE_HASH_CHUNK_SIZE = 1024 * 1024
_UNIT_TO_MM = {
    "millimetre": 1.0,
    "millimeter": 1.0,
    "mm": 1.0,
    "centimetre": 10.0,
    "centimeter": 10.0,
    "cm": 10.0,
    "metre": 1000.0,
    "meter": 1000.0,
    "m": 1000.0,
    "inch": 25.4,
    "in": 25.4,
    "foot": 304.8,
    "feet": 304.8,
    "ft": 304.8,
    "micrometre": 0.001,
    "micrometer": 0.001,
    "um": 0.001,
}

CancelCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class _ProductBodyMetadata:
    shape: object
    kind: str
    name: str
    assembly_path: str


@dataclass(frozen=True, slots=True)
class _ResolvedBodyMetadata:
    name: str
    assembly_path: str


class StepLoadError(RuntimeError):
    """The STEP source cannot be loaded into the supported CAD model."""


class StepLoadCancelled(StepLoadError):
    """Raised when a cooperative STEP load or source hash is cancelled."""


def file_sha256(path: Path, *, cancel_check: CancelCheck | None = None) -> str:
    _raise_if_cancelled(cancel_check)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            _raise_if_cancelled(cancel_check)
            chunk = stream.read(_FILE_HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            _raise_if_cancelled(cancel_check)
    _raise_if_cancelled(cancel_check)
    return digest.hexdigest()


def load_step(
    path: str | Path,
    *,
    cancel_check: CancelCheck | None = None,
    length_unit_override: str | None = None,
) -> CadModel:
    """Load one STEP source and retain exact BRep topology plus descriptors.

    OpenCascade is explicitly asked to transfer into its millimetre system.
    ``length_unit_override`` is reserved for STEP files whose unit declaration
    is absent or unsupported; it never changes a valid file declaration.
    """

    _raise_if_cancelled(cancel_check)
    source_path = _resolve_step_path(path)
    source_stat = source_path.stat()
    source_hash = file_sha256(source_path, cancel_check=cancel_check)
    _raise_if_cancelled(cancel_check)
    root_shape, units, product_metadata = _read_root_shape(
        source_path,
        length_unit_override=length_unit_override,
        cancel_check=cancel_check,
    )
    _raise_if_cancelled(cancel_check)

    body_shapes = _body_shapes(root_shape)
    if not body_shapes:
        raise StepLoadError(
            f"No solid, free shell, or free face found in STEP: {source_path}"
        )
    resolved_metadata = _match_body_metadata(
        body_shapes,
        product_metadata,
        cancel_check=cancel_check,
    )

    bodies: list[BodyInfo] = []
    faces: list[FaceInfo] = []
    edges: list[EdgeInfo] = []
    vertices: list[VertexInfo] = []
    shapes: dict[str, object] = {}
    face_shapes: dict[str, object] = {}
    edge_shapes: dict[str, object] = {}
    vertex_shapes: dict[str, object] = {}

    for body_index, (kind, body_shape) in enumerate(body_shapes, start=1):
        _raise_if_cancelled(cancel_check)
        body_id = f"body_{body_index:03d}"
        shapes[body_id] = body_shape
        topology = _enumerate_body_topology(
            body_id,
            body_shape,
            cancel_check=cancel_check,
        )
        faces.extend(topology["faces"])
        edges.extend(topology["edges"])
        vertices.extend(topology["vertices"])
        face_shapes.update(topology["face_shapes"])
        edge_shapes.update(topology["edge_shapes"])
        vertex_shapes.update(topology["vertex_shapes"])

        bounds = shape_bounds(body_shape)
        surface_props = _shape_properties(body_shape, surface=True)
        volume_props = (
            _shape_properties(body_shape, surface=False) if kind == "solid" else None
        )
        centroid = (
            volume_props[1]
            if volume_props is not None and volume_props[0] > 0.0
            else surface_props[1]
        )
        descriptor = {
            "kind": kind,
            "bounds": bounds.to_json(),
            "volume": None if volume_props is None else volume_props[0],
            "surface_area": surface_props[0],
            "centroid": centroid,
            "face_count": len(topology["faces"]),
            "edge_count": len(topology["edges"]),
            "vertex_count": len(topology["vertices"]),
        }
        body_label = "Solid" if kind == "solid" else "Sheet"
        body_metadata = resolved_metadata[body_index - 1]
        bodies.append(
            BodyInfo(
                body_id=body_id,
                index=body_index,
                name=(
                    f"{body_label} {body_index}"
                    if body_metadata is None
                    else body_metadata.name
                ),
                color=PALETTE[(body_index - 1) % len(PALETTE)],
                kind=kind,
                assembly_path=(
                    None if body_metadata is None else body_metadata.assembly_path
                ),
                bounds=bounds,
                volume=None if volume_props is None else volume_props[0],
                surface_area=surface_props[0],
                centroid=centroid,
                edge_ids=[edge.edge_id for edge in topology["edges"]],
                face_ids=[face.face_id for face in topology["faces"]],
                vertex_ids=[vertex.vertex_id for vertex in topology["vertices"]],
                signature=geometry_signature("body", descriptor),
            )
        )

    _raise_if_cancelled(cancel_check)
    final_stat = source_path.stat()
    final_hash = file_sha256(source_path, cancel_check=cancel_check)
    if (
        final_stat.st_size != source_stat.st_size
        or final_stat.st_mtime_ns != source_stat.st_mtime_ns
        or final_hash != source_hash
    ):
        raise StepLoadError(f"STEP source changed while loading: {source_path}")

    return CadModel(
        source_path=source_path,
        source_hash=source_hash,
        bodies=bodies,
        faces=faces,
        edges=edges,
        vertices=vertices,
        shapes=shapes,
        face_shapes=face_shapes,
        edge_shapes=edge_shapes,
        vertex_shapes=vertex_shapes,
        units=units,
        bounds=shape_bounds(root_shape),
        source_size_bytes=int(source_stat.st_size),
        source_mtime_ns=int(source_stat.st_mtime_ns),
    )


def geometry_signature(kind: str, descriptor: dict[str, Any]) -> str:
    """Return a deterministic, source-independent geometric signature."""

    payload = {
        "kind": str(kind),
        "geometry": _rounded_json_value(descriptor),
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def shape_bounds(shape: object) -> BoundingBox:
    box = Bnd_Box()
    box.SetGap(0.0)
    BRepBndLib.Add_s(shape, box)
    if box.IsVoid():
        return BoundingBox((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    values = tuple(float(value) for value in box.Get())
    return BoundingBox(values[:3], values[3:])


def sample_edge_points(edge: object, target_segments: int = 24) -> list[Vector3]:
    curve = BRepAdaptor_Curve(edge)
    first = float(curve.FirstParameter())
    last = float(curve.LastParameter())
    if not math.isfinite(first) or not math.isfinite(last) or first == last:
        return []

    count = max(2, target_segments + 1)
    points: list[Vector3] = []
    for index in range(count):
        parameter = first + (last - first) * (index / (count - 1))
        points.append(_point(curve.Value(parameter)))
    return points


def edge_length_hint(points: list[Vector3]) -> float | None:
    if len(points) < 2:
        return None
    return sum(math.dist(left, right) for left, right in zip(points, points[1:]))


def arc_length_midpoint(points: list[Vector3]) -> Vector3 | None:
    """Return the half-length point of a sampled curve polyline."""

    if len(points) < 2:
        return None
    lengths = [math.dist(left, right) for left, right in zip(points, points[1:])]
    total = sum(lengths)
    if total <= 1.0e-12:
        return points[0]
    target = total * 0.5
    walked = 0.0
    for left, right, segment_length in zip(points, points[1:], lengths):
        if walked + segment_length >= target and segment_length > 0.0:
            fraction = (target - walked) / segment_length
            return tuple(
                start + (end - start) * fraction for start, end in zip(left, right)
            )  # type: ignore[return-value]
        walked += segment_length
    return points[-1]


def geometry_candidates(model: CadModel) -> dict[str, list[dict[str, Any]]]:
    """Build auditable coordinate-reference candidates from exact topology."""

    origins: list[dict[str, Any]] = []
    directions: list[dict[str, Any]] = []
    for vertex in model.vertices:
        origins.append(
            {
                "kind": "vertex",
                "entity_id": vertex.vertex_id,
                "point": list(vertex.point),
            }
        )
    for edge in model.edges:
        if edge.center is not None and edge.curve_type in {"circle", "ellipse"}:
            origins.append(
                {
                    "kind": f"{edge.curve_type}_center",
                    "entity_id": edge.edge_id,
                    "point": list(edge.center),
                }
            )
        if edge.curve_type != "line" and edge.arc_length_midpoint is not None:
            origins.append(
                {
                    "kind": "arc_midpoint",
                    "entity_id": edge.edge_id,
                    "point": list(edge.arc_length_midpoint),
                }
            )
        if edge.curve_type == "line" and edge.axis_direction is not None:
            directions.append(
                {
                    "kind": "line_edge",
                    "entity_id": edge.edge_id,
                    "vector": list(edge.axis_direction),
                }
            )
    for face in model.faces:
        origins.append(
            {
                "kind": "face_centroid",
                "entity_id": face.face_id,
                "point": list(face.centroid),
            }
        )
        if face.surface_type == "plane" and face.normal is not None:
            directions.append(
                {
                    "kind": "plane_normal",
                    "entity_id": face.face_id,
                    "vector": list(face.normal),
                }
            )
        elif (
            face.surface_type in {"cylinder", "cone"}
            and face.axis_direction is not None
        ):
            directions.append(
                {
                    "kind": "surface_axis",
                    "entity_id": face.face_id,
                    "vector": list(face.axis_direction),
                }
            )
    return {"origins": origins, "directions": directions}


def _enumerate_body_topology(
    body_id: str,
    body_shape: object,
    *,
    cancel_check: CancelCheck | None,
) -> dict[str, Any]:
    face_map = _indexed_shapes(body_shape, TopAbs_FACE)
    edge_map = _indexed_shapes(body_shape, TopAbs_EDGE)
    vertex_map = _indexed_shapes(body_shape, TopAbs_VERTEX)

    face_ids = {
        index: f"{body_id}_face_{index:04d}"
        for index in range(1, face_map.Extent() + 1)
    }
    edge_ids = {
        index: f"{body_id}_edge_{index:04d}"
        for index in range(1, edge_map.Extent() + 1)
    }
    vertex_ids = {
        index: f"{body_id}_vertex_{index:04d}"
        for index in range(1, vertex_map.Extent() + 1)
    }

    edge_face_ids: dict[int, list[str]] = {index: [] for index in edge_ids}
    edge_vertex_ids: dict[int, list[str]] = {index: [] for index in edge_ids}
    vertex_edge_ids: dict[int, list[str]] = {index: [] for index in vertex_ids}
    face_edge_ids: dict[int, list[str]] = {index: [] for index in face_ids}

    for face_index in face_ids:
        _raise_if_cancelled(cancel_check)
        face = TopoDS.Face_s(face_map.FindKey(face_index))
        explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while explorer.More():
            index = edge_map.FindIndex(explorer.Current())
            if index > 0:
                edge_id = edge_ids[index]
                if edge_id not in face_edge_ids[face_index]:
                    face_edge_ids[face_index].append(edge_id)
                if face_ids[face_index] not in edge_face_ids[index]:
                    edge_face_ids[index].append(face_ids[face_index])
            explorer.Next()

    for edge_index in edge_ids:
        _raise_if_cancelled(cancel_check)
        edge = TopoDS.Edge_s(edge_map.FindKey(edge_index))
        explorer = TopExp_Explorer(edge, TopAbs_VERTEX)
        while explorer.More():
            index = vertex_map.FindIndex(explorer.Current())
            if index > 0:
                vertex_id = vertex_ids[index]
                if vertex_id not in edge_vertex_ids[edge_index]:
                    edge_vertex_ids[edge_index].append(vertex_id)
                if edge_ids[edge_index] not in vertex_edge_ids[index]:
                    vertex_edge_ids[index].append(edge_ids[edge_index])
            explorer.Next()

    vertex_infos: list[VertexInfo] = []
    vertex_shapes: dict[str, object] = {}
    for index, vertex_id in vertex_ids.items():
        _raise_if_cancelled(cancel_check)
        vertex = TopoDS.Vertex_s(vertex_map.FindKey(index))
        point = _point(BRep_Tool.Pnt_s(vertex))
        adjacent = vertex_edge_ids[index]
        vertex_infos.append(
            VertexInfo(
                vertex_id=vertex_id,
                body_id=body_id,
                index=index,
                point=point,
                edge_ids=adjacent,
                signature=geometry_signature(
                    "vertex",
                    {"point": point, "edge_degree": len(adjacent)},
                ),
            )
        )
        vertex_shapes[vertex_id] = vertex

    vertex_lookup = {item.vertex_id: item for item in vertex_infos}
    edge_infos: list[EdgeInfo] = []
    edge_shapes: dict[str, object] = {}
    for index, edge_id in edge_ids.items():
        _raise_if_cancelled(cancel_check)
        edge = TopoDS.Edge_s(edge_map.FindKey(index))
        samples = sample_edge_points(edge, target_segments=16)
        curve = BRepAdaptor_Curve(edge)
        curve_type = _enum_kind(curve.GetType())
        midpoint_samples = (
            samples
            if curve_type == "line"
            else sample_edge_points(edge, target_segments=96)
        )
        exact_length = _shape_properties(edge, linear=True)[0]
        adjacent_vertices = edge_vertex_ids[index]
        endpoints = _edge_endpoints(adjacent_vertices, vertex_lookup, samples)
        center, axis_direction, radius = _curve_geometry(curve, curve_type)
        descriptor = {
            "curve_type": curve_type,
            "length": exact_length,
            "endpoints": endpoints,
            "center": center,
            "axis_direction": axis_direction,
            "radius": radius,
            "face_degree": len(edge_face_ids[index]),
        }
        edge_infos.append(
            EdgeInfo(
                edge_id=edge_id,
                body_id=body_id,
                index=index,
                point_count=len(samples),
                length_hint=edge_length_hint(samples),
                curve_type=curve_type,
                exact_length=exact_length,
                vertex_ids=adjacent_vertices,
                face_ids=edge_face_ids[index],
                endpoints=endpoints,
                arc_length_midpoint=arc_length_midpoint(midpoint_samples),
                center=center,
                axis_direction=axis_direction,
                radius=radius,
                signature=geometry_signature("edge", descriptor),
            )
        )
        edge_shapes[edge_id] = edge

    face_infos: list[FaceInfo] = []
    face_shapes: dict[str, object] = {}
    for index, face_id in face_ids.items():
        _raise_if_cancelled(cancel_check)
        face = TopoDS.Face_s(face_map.FindKey(index))
        surface = BRepAdaptor_Surface(face, True)
        surface_type = _enum_kind(surface.GetType())
        area, centroid = _shape_properties(face, surface=True)
        metadata = _surface_geometry(
            surface, surface_type, face.Orientation() == TopAbs_REVERSED
        )
        bounds = shape_bounds(face)
        descriptor = {
            "surface_type": surface_type,
            "area": area,
            "centroid": centroid,
            "bounds": bounds.to_json(),
            "edge_count": len(face_edge_ids[index]),
            **metadata,
        }
        face_infos.append(
            FaceInfo(
                face_id=face_id,
                body_id=body_id,
                index=index,
                surface_type=surface_type,
                area=area,
                centroid=centroid,
                bounds=bounds,
                edge_ids=face_edge_ids[index],
                normal=metadata["normal"],
                axis_origin=metadata["axis_origin"],
                axis_direction=metadata["axis_direction"],
                radius=metadata["radius"],
                secondary_radius=metadata["secondary_radius"],
                semi_angle_rad=metadata["semi_angle_rad"],
                orientation=(
                    "reversed" if face.Orientation() == TopAbs_REVERSED else "forward"
                ),
                signature=geometry_signature("face", descriptor),
            )
        )
        face_shapes[face_id] = face

    return {
        "faces": face_infos,
        "edges": edge_infos,
        "vertices": vertex_infos,
        "face_shapes": face_shapes,
        "edge_shapes": edge_shapes,
        "vertex_shapes": vertex_shapes,
    }


def _body_shapes(root_shape: object) -> list[tuple[str, object]]:
    solids: list[object] = []
    solid_index = TopTools_IndexedMapOfShape()
    solid_explorer = TopExp_Explorer(root_shape, TopAbs_SOLID)
    while solid_explorer.More():
        solid = TopoDS.Solid_s(solid_explorer.Current())
        _append_unique_shape(solids, solid_index, solid)
        solid_explorer.Next()

    owned_shell_index = TopTools_IndexedMapOfShape()
    for solid in solids:
        shell_explorer = TopExp_Explorer(solid, TopAbs_SHELL)
        while shell_explorer.More():
            shell = TopoDS.Shell_s(shell_explorer.Current())
            owned_shell_index.Add(shell)
            shell_explorer.Next()

    free_shells: list[object] = []
    free_shell_index = TopTools_IndexedMapOfShape()
    shell_explorer = TopExp_Explorer(root_shape, TopAbs_SHELL)
    while shell_explorer.More():
        shell = TopoDS.Shell_s(shell_explorer.Current())
        if not owned_shell_index.Contains(shell):
            _append_unique_shape(free_shells, free_shell_index, shell)
        shell_explorer.Next()

    owned_face_index = TopTools_IndexedMapOfShape()
    for owner in [*solids, *free_shells]:
        face_explorer = TopExp_Explorer(owner, TopAbs_FACE)
        while face_explorer.More():
            face = TopoDS.Face_s(face_explorer.Current())
            owned_face_index.Add(face)
            face_explorer.Next()

    free_faces: list[object] = []
    free_face_index = TopTools_IndexedMapOfShape()
    face_explorer = TopExp_Explorer(root_shape, TopAbs_FACE)
    while face_explorer.More():
        face = TopoDS.Face_s(face_explorer.Current())
        if not owned_face_index.Contains(face):
            _append_unique_shape(free_faces, free_face_index, face)
        face_explorer.Next()

    return (
        [("solid", shape) for shape in solids]
        + [("sheet", shape) for shape in free_shells]
        + [("sheet", shape) for shape in free_faces]
    )


def _append_unique_shape(
    shapes: list[object],
    shape_index: TopTools_IndexedMapOfShape,
    candidate: Any,
) -> None:
    if shape_index.Contains(candidate):
        return
    shape_index.Add(candidate)
    shapes.append(candidate)


def _indexed_shapes(shape: object, kind: object) -> TopTools_IndexedMapOfShape:
    result = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, result)
    return result


def _read_root_shape(
    source_path: Path,
    *,
    length_unit_override: str | None,
    cancel_check: CancelCheck | None,
) -> tuple[object, CadUnitInfo, tuple[_ProductBodyMetadata, ...]]:
    _raise_if_cancelled(cancel_check)
    caf_reader = STEPCAFControl_Reader()
    caf_reader.SetNameMode(True)
    status = caf_reader.ReadFile(str(source_path))
    if status != IFSelect_RetDone:
        raise StepLoadError(f"OpenCascade failed to read STEP: {source_path}")
    _raise_if_cancelled(cancel_check)
    reader = caf_reader.ChangeReader()

    length_units = TColStd_SequenceOfAsciiString()
    angle_units = TColStd_SequenceOfAsciiString()
    solid_angle_units = TColStd_SequenceOfAsciiString()
    reader.FileUnits(length_units, angle_units, solid_angle_units)
    declared_length = _first_ascii(length_units)
    normalized_declared = _normalize_unit(declared_length)
    override = (
        None if length_unit_override is None else _normalize_unit(length_unit_override)
    )
    declaration_supported = normalized_declared in _UNIT_TO_MM
    if declaration_supported:
        source_unit = normalized_declared
        override_applied = False
        conversion_source = "step_declaration"
    elif override in _UNIT_TO_MM:
        source_unit = override
        override_applied = True
        conversion_source = (
            "override_missing_declaration"
            if normalized_declared is None
            else "override_unsupported_declaration"
        )
    else:
        raise StepLoadError(
            "STEP length unit is missing or unsupported; provide length_unit_override "
            f"(declared={declared_length!r})"
        )
    assert source_unit is not None

    # OCCT converts every declared representation context into millimetres.
    # When the application override replaces a missing or unsupported name,
    # the post-transfer ratio accounts for any conversion factor OCCT already
    # obtained from the STEP unit entity.  This prevents double scaling.
    declared_factor_mm = _step_length_factor_mm(
        reader.StepModel(),
        cancel_check=cancel_check,
    )
    reader.SetSystemLengthUnit(1.0)
    application = XCAFApp_Application.GetApplication_s()
    document_format = TCollection_ExtendedString("MDTV-XCAF")
    document = TDocStd_Document(document_format)
    application.NewDocument(document_format, document)
    product_metadata: tuple[_ProductBodyMetadata, ...] = ()
    transferred = False
    try:
        transferred = bool(caf_reader.Transfer(document))
        _raise_if_cancelled(cancel_check)
        if transferred:
            product_metadata = _collect_product_metadata(
                document,
                cancel_check=cancel_check,
            )
    except StepLoadCancelled:
        raise
    except Exception:
        # Geometry remains authoritative when optional XCAF names cannot be
        # decoded.  Generic Solid/Sheet labels make this degradation visible.
        transferred = False
        product_metadata = ()
    finally:
        try:
            application.Close(document)
        except Exception:
            pass

    root_shape = reader.OneShape()
    if root_shape.IsNull():
        transferred_roots = reader.TransferRoots()
        root_shape = reader.OneShape()
    else:
        transferred_roots = 1 if transferred else reader.NbShapes()
    if transferred_roots <= 0 or root_shape.IsNull():
        raise StepLoadError(f"STEP file contains no transferable roots: {source_path}")
    _raise_if_cancelled(cancel_check)

    if override_applied:
        reader_factor = (
            1.0
            if declared_factor_mm is None or declared_factor_mm <= 0.0
            else declared_factor_mm
        )
        correction = _UNIT_TO_MM[source_unit] / reader_factor
        if not math.isclose(correction, 1.0, rel_tol=1.0e-12, abs_tol=1.0e-12):
            root_shape = _scaled_shape(root_shape, correction)
            product_metadata = tuple(
                _ProductBodyMetadata(
                    shape=_scaled_shape(item.shape, correction),
                    kind=item.kind,
                    name=item.name,
                    assembly_path=item.assembly_path,
                )
                for item in product_metadata
            )

    return (
        root_shape,
        CadUnitInfo(
            source_length_unit=source_unit,
            scale_to_mm=_UNIT_TO_MM[source_unit],
            angle_unit=_first_ascii(angle_units),
            solid_angle_unit=_first_ascii(solid_angle_units),
            override_applied=override_applied,
            declared_length_unit=declared_length,
            conversion_source=conversion_source,
        ),
        product_metadata,
    )


def _step_length_factor_mm(
    model: StepData_StepModel,
    *,
    cancel_check: CancelCheck | None,
) -> float | None:
    """Read the STEP context's numeric length factor without guessing names."""

    factors: list[float] = []
    context_types = (
        StepGeom_GeomRepContextAndGlobUnitAssCtxAndGlobUncertaintyAssCtx,
        StepGeom_GeometricRepresentationContextAndGlobalUnitAssignedContext,
    )
    for index in range(1, model.NbEntities() + 1):
        if index == 1 or index % 256 == 0:
            _raise_if_cancelled(cancel_check)
        entity = model.Value(index)
        if not isinstance(entity, context_types):
            continue
        assigned_context = entity.GlobalUnitAssignedContext()
        local_factors = StepData_Factors()
        local_factors.InitializeFactors(1.0, 1.0, 1.0)
        local_factors.SetCascadeUnit(1.0)
        unit_context = STEPConstruct_UnitContext()
        status = unit_context.ComputeFactors(assigned_context, local_factors)
        if status != 0 or not unit_context.LengthDone():
            continue
        factor = float(unit_context.LengthFactor())
        if math.isfinite(factor) and factor > 0.0:
            factors.append(factor)
    unique: list[float] = []
    for factor in factors:
        if not any(
            math.isclose(factor, known, rel_tol=1.0e-12, abs_tol=1.0e-12)
            for known in unique
        ):
            unique.append(factor)
    if len(unique) > 1:
        raise StepLoadError("STEP contains multiple incompatible length-unit contexts")
    _raise_if_cancelled(cancel_check)
    return None if not unique else unique[0]


def _collect_product_metadata(
    document: TDocStd_Document,
    *,
    cancel_check: CancelCheck | None,
) -> tuple[_ProductBodyMetadata, ...]:
    """Collect leaf product shapes and their XCAF label paths."""

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    free_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free_labels)
    result: list[_ProductBodyMetadata] = []

    def visit(label: TDF_Label, parent_path: tuple[str, ...]) -> None:
        _raise_if_cancelled(cancel_check)
        label_name = _meaningful_xcaf_name(_xcaf_label_name(label))
        referred_name = ""
        referred = TDF_Label()
        if XCAFDoc_ShapeTool.GetReferredShape_s(label, referred):
            referred_name = _meaningful_xcaf_name(_xcaf_label_name(referred))
        effective_name = label_name or referred_name
        current_path = (
            parent_path if not effective_name else (*parent_path, effective_name)
        )

        components = TDF_LabelSequence()
        has_components = XCAFDoc_ShapeTool.GetComponents_s(
            label,
            components,
            False,
        )
        if has_components and components.Length() > 0:
            for component_index in range(1, components.Length() + 1):
                visit(components.Value(component_index), current_path)
            return

        shape = XCAFDoc_ShapeTool.GetShape_s(label)
        display_name = effective_name or (current_path[-1] if current_path else "")
        if shape.IsNull() or not display_name:
            return
        assembly_path = "/".join(current_path)
        for kind, body_shape in _body_shapes(shape):
            _raise_if_cancelled(cancel_check)
            result.append(
                _ProductBodyMetadata(
                    body_shape,
                    kind,
                    display_name,
                    assembly_path,
                )
            )

    for label_index in range(1, free_labels.Length() + 1):
        visit(free_labels.Value(label_index), ())
    return tuple(result)


def _xcaf_label_name(label: TDF_Label) -> str:
    iterator = TDF_AttributeIterator(label)
    name_attribute: TDataStd_Name | None = None
    while iterator.More():
        attribute = iterator.Value()
        if isinstance(attribute, TDataStd_Name):
            name_attribute = attribute
            break
        iterator.Next()
    if name_attribute is None:
        return ""
    extended = name_attribute.Get()
    value = (
        "".join(extended.Value(index) for index in range(1, extended.Length() + 1))
        .replace("\x00", "")
        .strip()
    )
    return " ".join(value.split())


def _meaningful_xcaf_name(value: str) -> str:
    if not value or value.startswith("=>["):
        return ""
    if value.upper() in {"COMPOUND", "SOLID", "SHELL", "SHAPE"}:
        return ""
    return value


def _match_body_metadata(
    body_shapes: list[tuple[str, object]],
    candidates: tuple[_ProductBodyMetadata, ...],
    *,
    cancel_check: CancelCheck | None,
) -> tuple[_ResolvedBodyMetadata | None, ...]:
    """Map XCAF products only when both sides have one geometric match."""

    body_groups: dict[str, list[int]] = {}
    for index, (kind, shape) in enumerate(body_shapes):
        _raise_if_cancelled(cancel_check)
        signature = geometry_signature(
            "body",
            _body_shape_descriptor(kind, shape),
        )
        body_groups.setdefault(signature, []).append(index)

    candidate_groups: dict[str, list[_ProductBodyMetadata]] = {}
    for candidate in candidates:
        _raise_if_cancelled(cancel_check)
        signature = geometry_signature(
            "body",
            _body_shape_descriptor(candidate.kind, candidate.shape),
        )
        candidate_groups.setdefault(signature, []).append(candidate)

    resolved: list[_ResolvedBodyMetadata | None] = [None] * len(body_shapes)
    for signature, body_indexes in body_groups.items():
        metadata = candidate_groups.get(signature, ())
        if len(body_indexes) != 1 or len(metadata) != 1:
            continue
        candidate = metadata[0]
        resolved[body_indexes[0]] = _ResolvedBodyMetadata(
            candidate.name,
            candidate.assembly_path,
        )
    return tuple(resolved)


def _body_shape_descriptor(kind: str, shape: object) -> dict[str, Any]:
    bounds = shape_bounds(shape)
    surface_props = _shape_properties(shape, surface=True)
    volume_props = _shape_properties(shape, surface=False) if kind == "solid" else None
    centroid = (
        volume_props[1]
        if volume_props is not None and volume_props[0] > 0.0
        else surface_props[1]
    )
    return {
        "kind": kind,
        "bounds": bounds.to_json(),
        "volume": None if volume_props is None else volume_props[0],
        "surface_area": surface_props[0],
        "centroid": centroid,
        "face_count": _indexed_shapes(shape, TopAbs_FACE).Extent(),
        "edge_count": _indexed_shapes(shape, TopAbs_EDGE).Extent(),
        "vertex_count": _indexed_shapes(shape, TopAbs_VERTEX).Extent(),
    }


def _scaled_shape(shape: object, factor: float) -> object:
    transform = gp_Trsf()
    transform.SetScale(gp_Pnt(0.0, 0.0, 0.0), factor)
    return BRepBuilderAPI_Transform(shape, transform, True).Shape()


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
        if surface_type == "plane":
            plane = surface.Plane()
            normal = _direction(plane.Axis().Direction())
            if reversed_orientation:
                normal = tuple(-value for value in normal)
            metadata["normal"] = normal
            metadata["axis_origin"] = _point(plane.Location())
        elif surface_type == "cylinder":
            cylinder = surface.Cylinder()
            metadata["axis_origin"] = _point(cylinder.Axis().Location())
            metadata["axis_direction"] = _direction(cylinder.Axis().Direction())
            metadata["radius"] = float(cylinder.Radius())
        elif surface_type == "cone":
            cone = surface.Cone()
            metadata["axis_origin"] = _point(cone.Axis().Location())
            metadata["axis_direction"] = _direction(cone.Axis().Direction())
            metadata["radius"] = float(cone.RefRadius())
            metadata["semi_angle_rad"] = float(cone.SemiAngle())
        elif surface_type == "sphere":
            sphere = surface.Sphere()
            metadata["axis_origin"] = _point(sphere.Location())
            metadata["axis_direction"] = _direction(sphere.Axis().Direction())
            metadata["radius"] = float(sphere.Radius())
        elif surface_type == "torus":
            torus = surface.Torus()
            metadata["axis_origin"] = _point(torus.Location())
            metadata["axis_direction"] = _direction(torus.Axis().Direction())
            metadata["radius"] = float(torus.MajorRadius())
            metadata["secondary_radius"] = float(torus.MinorRadius())
    except Exception:
        # The generic descriptor remains usable even if a specialised adaptor
        # rejects a trimmed or degenerate analytic surface.
        pass
    return metadata


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
    return tuple(component / length for component in vector)  # type: ignore[return-value]


def _enum_kind(value: object) -> str:
    name = str(value).rsplit(".", 1)[-1]
    return name.removeprefix("GeomAbs_").lower()


def _first_ascii(sequence: TColStd_SequenceOfAsciiString) -> str | None:
    if sequence.Length() <= 0:
        return None
    value = str(sequence.Value(1).ToCString()).strip()
    return value or None


def _normalize_unit(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("µ", "u")
    aliases = {
        "millimeters": "millimetre",
        "millimeter": "millimetre",
        "millimetres": "millimetre",
        "centimeters": "centimetre",
        "centimeter": "centimetre",
        "centimetres": "centimetre",
        "meters": "metre",
        "meter": "metre",
        "metres": "metre",
        "inches": "inch",
        "micrometers": "micrometre",
        "micrometer": "micrometre",
        "micrometres": "micrometre",
    }
    return aliases.get(normalized, normalized)


def _rounded_json_value(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("geometry signature values must be finite")
        return round(value, 8)
    if isinstance(value, dict):
        return {str(key): _rounded_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_rounded_json_value(item) for item in value]
    return value


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise StepLoadCancelled("STEP loading cancelled")


def _resolve_step_path(path: str | Path) -> Path:
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists():
        raise StepLoadError(f"STEP file not found: {source_path}")
    if source_path.suffix.lower() not in STEP_SUFFIXES:
        raise StepLoadError(f"Expected .step or .stp file: {source_path}")
    return source_path
