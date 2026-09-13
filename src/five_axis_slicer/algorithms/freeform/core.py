"""Guide-driven paths on one trimmed face or a bounded explicit face group."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math

from ...manufacturing.coordinates import RigidTransform
from ...manufacturing.curve_parameters import CurveProcessParameters
from ...manufacturing.freeform_parameters import FreeformOperationDefinition
from ...models import CadModel
from ..curve.chain import (
    CurveGeometryError,
    CurveSample,
    build_curve_plan,
    face_normal_at,
    project_point_to_face,
)
from ..curve.toolpath import height_offset_curve_samples, offset_curve_samples

CancelCheck = Callable[[], bool]


class FreeformGeometryError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = str(code), str(detail)
        super().__init__(f"{self.code}: {self.detail}".rstrip(": "))


@dataclass(frozen=True, slots=True)
class FreeformPath:
    path_id: str
    guide_index: int
    face_id: str
    layer_id: str
    region_id: str
    lateral_offset_mm: float
    height_offset_mm: float
    samples: tuple[CurveSample, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "path_id": self.path_id,
            "guide_index": self.guide_index,
            "face_id": self.face_id,
            "layer_id": self.layer_id,
            "region_id": self.region_id,
            "lateral_offset_mm": self.lateral_offset_mm,
            "height_offset_mm": self.height_offset_mm,
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


@dataclass(frozen=True, slots=True)
class FreeformPlan:
    plan_id: str
    operation_id: str
    face_ids: tuple[str, ...]
    paths: tuple[FreeformPath, ...]
    coordinate_frame: str = "workpiece_build"

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "plan_id": self.plan_id,
            "operation_id": self.operation_id,
            "face_ids": list(self.face_ids),
            "coordinate_frame": self.coordinate_frame,
            "paths": [item.to_json() for item in self.paths],
        }


def build_freeform_plan(
    model: CadModel,
    operation: FreeformOperationDefinition,
    *,
    T_build_from_source: RigidTransform | None = None,
    cancelled: CancelCheck | None = None,
) -> FreeformPlan:
    if not operation.geometry.is_complete:
        raise FreeformGeometryError("freeform.geometry_incomplete")
    transform = T_build_from_source or RigidTransform.identity("source")
    if transform.source_frame not in {"source", "model"}:
        raise ValueError("Freeform transform must start in Source/Model frame")
    inverse = transform.inverse()
    curve_parameters = _curve_parameters(operation)
    paths: list[FreeformPath] = []
    for guide_index, guide in enumerate(operation.geometry.guides, start=1):
        paths.extend(
            _guide_paths(
                model,
                operation,
                guide_index,
                guide,
                transform,
                inverse,
                curve_parameters,
                len(paths),
                cancelled,
            )
        )
    if not paths:
        raise FreeformGeometryError("freeform.no_paths")
    return FreeformPlan(
        f"{operation.operation_id}-freeform-plan-v1",
        operation.operation_id,
        tuple(item.object_id for item in operation.geometry.faces),
        tuple(paths),
    )


def _curve_parameters(operation):
    parameters = operation.parameters
    return CurveProcessParameters(
        sampling_step_mm=parameters.sampling_step_mm,
        chord_error_mm=parameters.chord_error_mm,
        chain_tolerance_mm=parameters.chain_tolerance_mm,
        bead_width_mm=parameters.bead_width_mm,
        layer_height_mm=parameters.layer_height_mm,
        feedrate_mm_min=parameters.feedrate_mm_min,
        travel_feedrate_mm_min=parameters.travel_feedrate_mm_min,
        retract_length_mm=max(parameters.retract_length_mm, 1.0e-9),
        layer_count=1,
        offset_pass_count=1,
        offset_spacing_mm=parameters.path_spacing_mm,
    )


def _guide_paths(
    model,
    operation,
    guide_index,
    guide,
    transform,
    inverse,
    curve_parameters,
    start_index,
    cancelled,
):
    _checkpoint(cancelled)
    assert guide.normal_face is not None
    face_id = guide.normal_face.object_id
    try:
        base = build_curve_plan(
            model,
            f"{operation.operation_id}-guide-{guide_index:02d}",
            guide,
            curve_parameters,
            T_build_from_source=transform,
            cancelled=cancelled,
        )
    except CurveGeometryError as exc:
        raise FreeformGeometryError(exc.code, exc.detail) from exc

    def project(build_point):
        source_point = inverse.transform_point(build_point)
        projected = project_point_to_face(model, face_id, source_point)
        return transform.transform_point(projected)

    paths: list[FreeformPath] = []
    parameters = operation.parameters
    for layer in range(parameters.layer_count):
        for pass_index in range(parameters.path_count):
            paths.append(
                _offset_path(
                    model,
                    parameters,
                    base.samples,
                    face_id,
                    guide_index,
                    layer,
                    pass_index,
                    transform,
                    inverse,
                    project,
                    start_index + len(paths),
                )
            )
    return paths


def _offset_path(
    model,
    parameters,
    base_samples,
    face_id,
    guide_index,
    layer,
    pass_index,
    transform,
    inverse,
    project,
    path_index,
):
    offset = pass_index * parameters.path_spacing_mm
    try:
        samples = offset_curve_samples(
            base_samples,
            offset,
            parameters.bead_width_mm,
            project_point=project,
        )
    except CurveGeometryError as exc:
        raise FreeformGeometryError(exc.code, exc.detail) from exc
    samples = _refresh_normals(model, face_id, samples, transform, inverse)
    if layer:
        samples = height_offset_curve_samples(samples, layer * parameters.layer_height_mm)
    _validate_samples(samples, parameters.maximum_normal_change_rad)
    if (layer + pass_index + guide_index) % 2 == 0:
        samples = _reverse(samples)
    return FreeformPath(
        f"path-{path_index + 1:04d}",
        guide_index,
        face_id,
        f"layer-{layer + 1:03d}",
        f"guide-{guide_index:02d}-pass-{pass_index + 1:02d}",
        offset,
        layer * parameters.layer_height_mm,
        samples,
    )


def _refresh_normals(model, face_id, samples, transform, inverse):
    refreshed = []
    for item in samples:
        source_point = inverse.transform_point(item.position)
        normal = transform.transform_vector(face_normal_at(model, face_id, source_point))
        refreshed.append(
            CurveSample(
                item.position,
                item.tangent,
                _unit(normal),
                item.source_edge_id,
                item.edge_parameter,
                item.chain_distance_mm,
            )
        )
    return tuple(refreshed)


def _validate_samples(samples: tuple[CurveSample, ...], limit: float) -> None:
    if len(samples) < 2:
        raise FreeformGeometryError("freeform.path_degenerate")
    for left, right in zip(samples, samples[1:]):
        if math.dist(left.position, right.position) <= 1.0e-10:
            raise FreeformGeometryError("freeform.zero_segment")
        angle = math.acos(max(-1.0, min(1.0, _dot(left.surface_normal, right.surface_normal))))
        if angle > limit + 1.0e-12:
            raise FreeformGeometryError(
                "freeform.normal_discontinuity",
                f"{angle:.9g} rad exceeds {limit:.9g} rad",
            )


def _reverse(samples: tuple[CurveSample, ...]) -> tuple[CurveSample, ...]:
    return tuple(
        CurveSample(
            item.position,
            (-item.tangent[0], -item.tangent[1], -item.tangent[2]),
            item.surface_normal,
            item.source_edge_id,
            item.edge_parameter,
            item.chain_distance_mm,
        )
        for item in reversed(samples)
    )


def _unit(value):
    length = math.sqrt(_dot(value, value))
    if length <= 1.0e-12:
        raise FreeformGeometryError("freeform.normal_undefined")
    return tuple(item / length for item in value)


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def _checkpoint(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        from ...postprocessing.indexed_tube import GenerationCancelled

        raise GenerationCancelled("Freeform generation cancelled")
