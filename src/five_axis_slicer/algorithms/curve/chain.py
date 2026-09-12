"""Ordered STEP edge-chain sampling with explicit normal ownership."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.GCPnts import GCPnts_AbscissaPoint, GCPnts_UniformAbscissa
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.GeomLProp import GeomLProp_SLProps
from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_REVERSED
from OCP.gp import gp_Pnt, gp_Vec

from ...manufacturing.coordinates import RigidTransform
from ...manufacturing.curve_parameters import CurveGeometrySelection, CurveProcessParameters
from ...models import CadModel, Vector3

CancelCheck = Callable[[], bool]


class CurveGeometryError(ValueError):
    def __init__(self, code: str, object_id: str | None = None, detail: str = "") -> None:
        self.code = str(code)
        self.object_id = object_id
        self.detail = str(detail)
        suffix = f" [{object_id}]" if object_id else ""
        super().__init__(f"{self.code}{suffix}: {self.detail}".rstrip(": "))


@dataclass(frozen=True, slots=True)
class CurveSample:
    position: Vector3
    tangent: Vector3
    surface_normal: Vector3
    source_edge_id: str
    edge_parameter: float
    chain_distance_mm: float


@dataclass(frozen=True, slots=True)
class CurvePlan:
    plan_id: str
    operation_id: str
    samples: tuple[CurveSample, ...]
    edge_ids: tuple[str, ...]
    edge_lengths_mm: tuple[float, ...]
    total_length_mm: float
    closed: bool
    normal_source: str
    coordinate_frame: str = "workpiece_build"

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "plan_id": self.plan_id,
            "operation_id": self.operation_id,
            "edge_ids": list(self.edge_ids),
            "edge_lengths_mm": list(self.edge_lengths_mm),
            "total_length_mm": self.total_length_mm,
            "closed": self.closed,
            "normal_source": self.normal_source,
            "coordinate_frame": self.coordinate_frame,
            "samples": [
                {
                    "position": list(item.position),
                    "tangent": list(item.tangent),
                    "surface_normal": list(item.surface_normal),
                    "source_edge_id": item.source_edge_id,
                    "edge_parameter": item.edge_parameter,
                    "chain_distance_mm": item.chain_distance_mm,
                }
                for item in self.samples
            ],
        }


def build_curve_plan(
    model: CadModel,
    operation_id: str,
    geometry: CurveGeometrySelection,
    parameters: CurveProcessParameters,
    *,
    T_build_from_source: RigidTransform | None = None,
    cancelled: CancelCheck | None = None,
) -> CurvePlan:
    """Sample the selected chain at near-uniform arclength in Build frame."""

    if not geometry.edges:
        raise CurveGeometryError("curve.chain_empty", detail="select one or more STEP edges")
    transform = T_build_from_source or RigidTransform.identity("source")
    if transform.source_frame not in {"source", "model"}:
        raise ValueError("Curve input transform must start in Source/Model frame")
    normal_face_id = _validate_normal_source(model, geometry)
    edge_samples: list[list[tuple[Vector3, Vector3, float, float]]] = []
    lengths: list[float] = []
    for selected in geometry.edges:
        _checkpoint(cancelled)
        edge_id = selected.edge.object_id
        edge_info = model.edge_map.get(edge_id)
        shape = model.edge_shapes.get(edge_id)
        if edge_info is None or shape is None:
            raise CurveGeometryError("curve.edge_missing", edge_id)
        if edge_info.exact_length is not None and edge_info.exact_length <= 1.0e-9:
            raise CurveGeometryError("curve.edge_degenerate", edge_id, "zero-length edge")
        sampled, length = _sample_edge(shape, parameters.sampling_step_mm, selected.reversed)
        if length <= 1.0e-9 or len(sampled) < 2:
            raise CurveGeometryError("curve.edge_degenerate", edge_id, "insufficient extent")
        edge_samples.append(sampled)
        lengths.append(length)
    _validate_chain(edge_samples, geometry, parameters.chain_tolerance_mm)

    output: list[CurveSample] = []
    chain_base = 0.0
    for selected, sampled, edge_length in zip(
        geometry.edges, edge_samples, lengths, strict=True
    ):
        edge_id = selected.edge.object_id
        for index, (point, tangent, parameter, local_distance) in enumerate(sampled):
            if output and index == 0:
                continue
            normal = (
                geometry.specified_normal
                if geometry.normal_mode == "specified"
                else _face_normal(model, normal_face_id, point)
            )
            assert normal is not None
            build_point = transform.transform_point(point)
            build_tangent = _unit(transform.transform_vector(tangent), "curve.tangent_degenerate")
            build_normal = _unit(transform.transform_vector(normal), "curve.normal_degenerate")
            if abs(_dot(build_tangent, build_normal)) > 0.999:
                raise CurveGeometryError(
                    "curve.normal_parallel_tangent", edge_id, "normal cannot define nozzle pose"
                )
            output.append(
                CurveSample(
                    build_point,
                    build_tangent,
                    build_normal,
                    edge_id,
                    parameter,
                    chain_base + local_distance,
                )
            )
        chain_base += edge_length
    if len(output) < 2:
        raise CurveGeometryError("curve.chain_degenerate", detail="chain has fewer than two points")
    closed = math.dist(output[0].position, output[-1].position) <= parameters.chain_tolerance_mm
    return CurvePlan(
        f"{operation_id}-curve-plan-v1",
        operation_id,
        tuple(output),
        tuple(item.edge.object_id for item in geometry.edges),
        tuple(lengths),
        sum(lengths),
        closed,
        (
            f"specified:{geometry.specified_normal}"
            if geometry.normal_mode == "specified"
            else f"adjacent_face:{normal_face_id}"
        ),
    )


def _sample_edge(
    edge_shape: object, step_mm: float, reversed_direction: bool
) -> tuple[list[tuple[Vector3, Vector3, float, float]], float]:
    curve = BRepAdaptor_Curve(edge_shape)
    first, last = float(curve.FirstParameter()), float(curve.LastParameter())
    length = float(GCPnts_AbscissaPoint.Length_s(curve, first, last, 1.0e-9))
    count = max(2, int(math.ceil(length / step_mm)) + 1)
    sampler = GCPnts_UniformAbscissa()
    sampler.Initialize(curve, count, first, last, 1.0e-9)
    if not sampler.IsDone() or sampler.NbPoints() < 2:
        raise CurveGeometryError("curve.edge_sampling_failed")
    parameters = [float(sampler.Parameter(index)) for index in range(1, sampler.NbPoints() + 1)]
    if reversed_direction:
        parameters.reverse()
    start_parameter = parameters[0]
    result: list[tuple[Vector3, Vector3, float, float]] = []
    for parameter in parameters:
        point, derivative = gp_Pnt(), gp_Vec()
        curve.D1(parameter, point, derivative)
        tangent = (float(derivative.X()), float(derivative.Y()), float(derivative.Z()))
        if reversed_direction:
            tangent = tuple(-value for value in tangent)  # type: ignore[assignment]
        tangent = _unit(tangent, "curve.tangent_degenerate")
        local = abs(float(GCPnts_AbscissaPoint.Length_s(curve, start_parameter, parameter, 1e-9)))
        result.append((_point(point), tangent, parameter, local))
    return result, length


def _validate_chain(
    sampled_edges: list[list[tuple[Vector3, Vector3, float, float]]],
    geometry: CurveGeometrySelection,
    tolerance: float,
) -> None:
    for index, (left, right) in enumerate(zip(sampled_edges, sampled_edges[1:])):
        gap = math.dist(left[-1][0], right[0][0])
        if gap > tolerance:
            raise CurveGeometryError(
                "curve.chain_disconnected",
                geometry.edges[index + 1].edge.object_id,
                f"gap {gap:.9g} mm exceeds {tolerance:.9g} mm",
            )


def _validate_normal_source(model: CadModel, geometry: CurveGeometrySelection) -> str:
    if geometry.normal_mode == "specified":
        if geometry.specified_normal is None:
            raise CurveGeometryError("curve.normal_missing")
        return ""
    if geometry.normal_face is None:
        raise CurveGeometryError("curve.normal_face_missing")
    face_id = geometry.normal_face.object_id
    if face_id not in model.face_map or face_id not in model.face_shapes:
        raise CurveGeometryError("curve.normal_face_missing", face_id)
    for selected in geometry.edges:
        edge = model.edge_map.get(selected.edge.object_id)
        if edge is None or face_id not in edge.face_ids:
            raise CurveGeometryError(
                "curve.normal_face_not_adjacent", selected.edge.object_id, face_id
            )
    return face_id


def _face_normal(model: CadModel, face_id: str, point: Vector3) -> Vector3:
    face = model.face_shapes[face_id]
    surface = BRep_Tool.Surface_s(face)
    projector = GeomAPI_ProjectPointOnSurf(gp_Pnt(*point), surface)
    if projector.NbPoints() < 1:
        raise CurveGeometryError("curve.normal_projection_failed", face_id)
    u, v = projector.LowerDistanceParameters()
    props = GeomLProp_SLProps(surface, float(u), float(v), 1, 1.0e-9)
    if not props.IsNormalDefined():
        raise CurveGeometryError("curve.normal_undefined", face_id)
    direction = props.Normal()
    normal = (float(direction.X()), float(direction.Y()), float(direction.Z()))
    if face.Orientation() == TopAbs_REVERSED:
        normal = tuple(-value for value in normal)  # type: ignore[assignment]
    return _unit(normal, "curve.normal_undefined")


def project_point_to_face(model: CadModel, face_id: str, point: Vector3) -> Vector3:
    """Project to the authoritative surface and reject points outside its trim."""

    face = model.face_shapes.get(face_id)
    if face is None:
        raise CurveGeometryError("curve.normal_face_missing", face_id)
    surface = BRep_Tool.Surface_s(face)
    projector = GeomAPI_ProjectPointOnSurf(gp_Pnt(*point), surface)
    if projector.NbPoints() < 1:
        raise CurveGeometryError("curve.offset_projection_failed", face_id)
    projected = projector.NearestPoint()
    classifier = BRepClass_FaceClassifier(face, projected, 1.0e-7)
    if classifier.State() not in {TopAbs_IN, TopAbs_ON}:
        raise CurveGeometryError(
            "curve.offset_outside_face", face_id, "offset crosses the trimmed face boundary"
        )
    return _point(projected)


def _point(point: gp_Pnt) -> Vector3:
    return (float(point.X()), float(point.Y()), float(point.Z()))


def _unit(value: Vector3, code: str) -> Vector3:
    length = math.sqrt(sum(item * item for item in value))
    if length <= 1.0e-12:
        raise CurveGeometryError(code)
    return tuple(item / length for item in value)  # type: ignore[return-value]


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right))


def _checkpoint(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        from ...postprocessing.indexed_tube import GenerationCancelled

        raise GenerationCancelled("Curve generation cancelled")


__all__ = [
    "CurveGeometryError",
    "CurvePlan",
    "CurveSample",
    "build_curve_plan",
    "project_point_to_face",
]
