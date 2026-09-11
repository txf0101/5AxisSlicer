"""Controller-neutral product flow shared by every supported Tube operation.

The dispatcher deliberately keeps the operation-specific geometry algorithms
small.  All three operations converge on the same XYZAC, validation, manifest,
postprocessing, readback, state and six-artifact export contracts.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, cast

from ..algorithms.tube.buildup import (
    PlanarBaseDefinition,
    TubeBuildupParameters,
    TubeBuildupPlan,
    TubeBuildupSequence,
    generate_planar_base_toolpath,
    generate_tube_buildup_toolpath,
    plan_tube_buildup,
    sequence_buildup_operations,
)
from ..algorithms.tube.continuous import (
    generate_continuous_toolpath,
    solve_continuous_xyzac_trajectory,
    validate_continuous_tube,
)
from ..algorithms.tube.geometry import TubeFeature, recognise_tube
from ..algorithms.tube.indexed import IndexedSlicePlan
from ..kinematics.xyzac import MachineAxisTrajectory, solve_xyzac_trajectory
from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.machine import MachineProfile
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.setup import (
    IssueSeverity,
    TubeBuildupOperationConfig,
    TubeContinuousOperationConfig,
    TubeOperationDefinition,
    ValidationIssue,
)
from ..manufacturing.toolpath import (
    GeneratedResultManifest,
    GeneratedResultStatus,
    GeneratedToolpath,
    SourceFingerprint,
    ToolpathEvent,
    ToolpathPoint,
)
from ..models import CadModel
from ..validation.indexed_tube import (
    CollisionBox,
    IndexedValidationReport,
    ValidationMetric,
    _collision_issues,
    _unique_issues,
)
from .indexed_tube import (
    GCodeReadbackReport,
    IndexedProductResult,
    export_indexed_product,
    generate_indexed_product,
    postprocess_indexed_gcode,
    readback_indexed_gcode,
)

ALGORITHM_VERSIONS = {
    "tube_thin_wall_indexed": "tube-indexed-product-v1",
    "tube_buildup": "tube-buildup-product-v1",
    "tube_continuous": "tube-continuous-product-v1",
}
PRODUCT_STATE_SCHEMA_VERSION = 1
CancelCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class TubeProductResult:
    """Uniform product result for Indexed, Buildup and Continuous operations."""

    operation_type: str
    feature: TubeFeature
    plan: IndexedSlicePlan | TubeBuildupPlan | None
    toolpath: GeneratedToolpath
    trajectory: MachineAxisTrajectory
    validation: IndexedValidationReport
    manifest: GeneratedResultManifest
    gcode: str
    readback: GCodeReadbackReport
    operation_toolpaths: tuple[GeneratedToolpath, ...]
    buildup_sequence: TubeBuildupSequence | None = None

    @property
    def exportable(self) -> bool:
        return self.manifest.ready_for_export and self.readback.passed

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": PRODUCT_STATE_SCHEMA_VERSION,
            "operation_type": self.operation_type,
            "manifest": self.manifest.to_json(),
            "plan": _plan_json(self.plan),
            "machine_trajectory": self.trajectory.to_json(),
            "validation": self.validation.to_json(),
            "readback": self.readback.to_json(),
            "operation_sequence": [item.operation_id for item in self.operation_toolpaths],
        }


@dataclass(frozen=True, slots=True)
class TubeProductState:
    """Persistable ownership and stale state shared by all Tube products."""

    operation_id: str
    parameter_semantic_sha256: str
    status: str
    result_payload: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ready", "warning", "error", "stale", "draft"}:
            raise ValueError("unsupported Tube product state")
        if len(self.parameter_semantic_sha256) != 64:
            raise ValueError("parameter_semantic_sha256 must be a SHA-256 digest")

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": PRODUCT_STATE_SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "parameter_semantic_sha256": self.parameter_semantic_sha256,
            "status": self.status,
            "result": self.result_payload,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "TubeProductState":
        if int(payload.get("schema_version", 0)) != PRODUCT_STATE_SCHEMA_VERSION:
            raise ValueError("unsupported Tube product state schema")
        result = payload.get("result")
        if result is not None and not isinstance(result, Mapping):
            raise ValueError("Tube product result must be an object or null")
        return cls(
            operation_id=str(payload["operation_id"]),
            parameter_semantic_sha256=str(payload["parameter_semantic_sha256"]),
            status=str(payload["status"]),
            result_payload=result,
        )

    def stale_for(self, operation: TubeOperationDefinition) -> "TubeProductState":
        digest = tube_operation_semantic_sha256(operation)
        if digest == self.parameter_semantic_sha256:
            return self
        return replace(self, parameter_semantic_sha256=digest, status="stale")


class TubeProductService:
    """Stateful facade suitable for Generate/Cancel and project persistence."""

    def __init__(self, state: TubeProductState | None = None) -> None:
        self.state = state

    def mark_operation_changed(self, operation: TubeOperationDefinition) -> TubeProductState | None:
        if self.state is not None:
            self.state = self.state.stale_for(operation)
        return self.state

    def generate(
        self,
        model: CadModel,
        operation: TubeOperationDefinition,
        machine: MachineProfile,
        nozzle: NozzleProfile,
        **kwargs: Any,
    ) -> TubeProductResult:
        result = generate_tube_product(model, operation, machine, nozzle, **kwargs)
        self.state = TubeProductState(
            operation.operation_id,
            tube_operation_semantic_sha256(operation),
            cast(GeneratedResultStatus, result.manifest.status).value,
            result.to_json(),
        )
        return result


def generate_tube_product(
    model: CadModel,
    operation: TubeOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    *,
    source_path: str | Path | None = None,
    T_workpiece_from_build: RigidTransform | None = None,
    obstacles: tuple[CollisionBox, ...] = (),
    check_ipw: bool = False,
    radial_error_limit_mm: float = 0.01,
    planar_base: PlanarBaseDefinition | None = None,
    cancelled: CancelCheck | None = None,
) -> TubeProductResult:
    """Dispatch one persisted Tube operation through the complete product chain."""

    _checkpoint(cancelled)
    if not operation.enabled or not operation.geometry.is_complete:
        raise ValueError("Tube operation must be enabled and have complete geometry")
    if operation.operation_type == "tube_thin_wall_indexed":
        return _generate_indexed_tube_product(
            model,
            operation,
            machine,
            nozzle,
            source_path,
            T_workpiece_from_build,
            obstacles,
            check_ipw,
            radial_error_limit_mm,
            cancelled,
        )

    return _generate_nonindexed_tube_product(
        model,
        operation,
        machine,
        nozzle,
        source_path,
        T_workpiece_from_build,
        obstacles,
        check_ipw,
        radial_error_limit_mm,
        planar_base,
        cancelled,
    )


def _generate_nonindexed_tube_product(
    model: CadModel,
    operation: TubeOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    source_path: str | Path | None,
    transform: RigidTransform | None,
    obstacles: tuple[CollisionBox, ...],
    check_ipw: bool,
    radial_error_limit_mm: float,
    planar_base: PlanarBaseDefinition | None,
    cancelled: CancelCheck | None,
) -> TubeProductResult:
    feature = recognise_tube(model, operation.geometry)
    _checkpoint(cancelled)
    if operation.operation_type == "tube_buildup":
        return _generate_buildup_product(
            model,
            operation,
            feature,
            machine,
            nozzle,
            source_path,
            transform,
            obstacles,
            check_ipw,
            planar_base,
            cancelled,
        )
    if operation.operation_type == "tube_continuous":
        return _generate_continuous_product(
            model,
            operation,
            feature,
            machine,
            nozzle,
            source_path,
            transform,
            obstacles,
            check_ipw,
            radial_error_limit_mm,
            cancelled,
        )
    raise ValueError(f"unsupported Tube operation_type: {operation.operation_type!r}")


def _generate_indexed_tube_product(
    model: CadModel,
    operation: TubeOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    source_path: str | Path | None,
    transform: RigidTransform | None,
    obstacles: tuple[CollisionBox, ...],
    check_ipw: bool,
    radial_error_limit_mm: float,
    cancelled: CancelCheck | None,
) -> TubeProductResult:
    return _indexed_result(
        generate_indexed_product(
            model,
            operation,
            machine,
            nozzle,
            source_path=source_path,
            T_workpiece_from_build=transform,
            obstacles=obstacles,
            check_ipw=check_ipw,
            radial_error_limit_mm=radial_error_limit_mm,
            cancelled=cancelled,
        )
    )


def _generate_buildup_product(
    model: CadModel,
    operation: TubeOperationDefinition,
    feature: TubeFeature,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    source_path: str | Path | None,
    transform: RigidTransform | None,
    obstacles: tuple[CollisionBox, ...],
    check_ipw: bool,
    planar_base: PlanarBaseDefinition | None,
    cancelled: CancelCheck | None,
) -> TubeProductResult:
    config = operation.type_config
    if not isinstance(config, TubeBuildupOperationConfig):
        raise TypeError("tube_buildup requires TubeBuildupOperationConfig")
    parameters, plan, sequence = _plan_buildup_sequence(
        model, operation, feature, config, planar_base
    )
    toolpath = _merge_buildup_sequence(operation.operation_id, sequence)
    _checkpoint(cancelled)
    trajectory = solve_xyzac_trajectory(
        toolpath,
        machine,
        tool_length_mm=nozzle.length_mm or 0.0,
        T_workpiece_from_build=transform,
    )
    validation = _validate_buildup(
        plan, toolpath, trajectory, nozzle, obstacles=obstacles, check_ipw=check_ipw
    )
    return _finish_product(
        model,
        operation,
        feature,
        plan,
        toolpath,
        trajectory,
        validation,
        machine,
        nozzle,
        source_path,
        sequence.operations,
        sequence,
        cancelled,
    )


def _plan_buildup_sequence(
    model: CadModel,
    operation: TubeOperationDefinition,
    feature: TubeFeature,
    config: TubeBuildupOperationConfig,
    planar_base: PlanarBaseDefinition | None,
) -> tuple[TubeBuildupParameters, TubeBuildupPlan, TubeBuildupSequence]:
    parameters = TubeBuildupParameters(
        **operation.parameters.to_json(),
        maximum_pass_spacing_mm=config.maximum_pass_spacing_mm,
    )
    plan = plan_tube_buildup(feature, parameters)
    tube_path = generate_tube_buildup_toolpath(
        operation.operation_id,
        feature,
        plan,
        parameters,
        model=model if feature.tube_body_id in model.shapes else None,
    )
    base_path = None
    if config.include_planar_base:
        base = planar_base or _base_from_substrate(model, operation, feature)
        base_path = generate_planar_base_toolpath(
            f"{operation.operation_id}-planar-base", base, parameters
        )
    sequence = sequence_buildup_operations(
        f"{operation.operation_id}-sequence",
        tube_path,
        base_toolpath=base_path,
        base_order=config.base_order,
        safe_clearance_mm=parameters.safe_clearance_mm,
    )
    return parameters, plan, sequence


def _generate_continuous_product(
    model: CadModel,
    operation: TubeOperationDefinition,
    feature: TubeFeature,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    source_path: str | Path | None,
    transform: RigidTransform | None,
    obstacles: tuple[CollisionBox, ...],
    check_ipw: bool,
    radial_error_limit_mm: float,
    cancelled: CancelCheck | None,
) -> TubeProductResult:
    config = operation.type_config
    if not isinstance(config, TubeContinuousOperationConfig):
        raise TypeError("tube_continuous requires TubeContinuousOperationConfig")
    toolpath = generate_continuous_toolpath(
        operation.operation_id,
        feature,
        operation.parameters,
        seam_angle_rad=math.radians(config.seam_angle_deg),
    )
    _checkpoint(cancelled)
    trajectory = solve_continuous_xyzac_trajectory(
        toolpath,
        machine,
        tool_length_mm=nozzle.length_mm or 0.0,
        T_workpiece_from_build=transform,
    )
    validation = validate_continuous_tube(
        feature,
        toolpath,
        trajectory,
        nozzle,
        obstacles=obstacles,
        radial_error_limit_mm=radial_error_limit_mm,
        check_ipw=check_ipw,
    )
    return _finish_product(
        model,
        operation,
        feature,
        None,
        toolpath,
        trajectory,
        validation,
        machine,
        nozzle,
        source_path,
        (toolpath,),
        None,
        cancelled,
    )


def _finish_product(
    model: CadModel,
    operation: TubeOperationDefinition,
    feature: TubeFeature,
    plan: IndexedSlicePlan | TubeBuildupPlan | None,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    validation: IndexedValidationReport,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    source_path: str | Path | None,
    operation_toolpaths: tuple[GeneratedToolpath, ...],
    sequence: TubeBuildupSequence | None,
    cancelled: CancelCheck | None,
) -> TubeProductResult:
    _checkpoint(cancelled)
    manifest = _manifest(model, source_path, operation, machine, toolpath, validation)
    if not manifest.ready_for_export:
        return TubeProductResult(
            operation.operation_type,
            feature,
            plan,
            toolpath,
            trajectory,
            validation,
            manifest,
            "",
            GCodeReadbackReport(
                len(toolpath.points), 0, (), (), (), ("export_blocked_by_validation",)
            ),
            operation_toolpaths,
            sequence,
        )
    gcode = postprocess_tube_gcode(operation.operation_type, toolpath, trajectory, machine, nozzle)
    readback = readback_tube_gcode(gcode, toolpath, trajectory, machine)
    if not readback.passed:
        manifest = replace(
            manifest,
            status=GeneratedResultStatus.ERROR,
            ready_for_export=False,
            issues=(*manifest.issues, "tube.gcode_readback_failed"),
        )
    return TubeProductResult(
        operation.operation_type,
        feature,
        plan,
        toolpath,
        trajectory,
        validation,
        manifest,
        gcode,
        readback,
        operation_toolpaths,
        sequence,
    )


def postprocess_tube_gcode(
    operation_type: str,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
) -> str:
    """Use the checked absolute XYZAC dialect for every Tube path."""

    title = operation_type.replace("_", " ").title()
    return postprocess_indexed_gcode(toolpath, trajectory, machine, nozzle).replace(
        "; 5AxisSclicer T08 Tube Thin-Wall Indexed",
        f"; 5AxisSclicer {title}",
        1,
    )


def readback_tube_gcode(
    gcode: str,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
) -> GCodeReadbackReport:
    """Read back the shared restricted dialect and compare axes, F, E and order."""

    return readback_indexed_gcode(gcode, toolpath, trajectory, machine)


def export_tube_product(
    result: TubeProductResult,
    destination: str | Path,
    *,
    cancelled: CancelCheck | None = None,
) -> Path:
    """Publish the same six inspectable artifacts used by the Indexed flow."""

    return export_indexed_product(
        cast(IndexedProductResult, result), destination, cancelled=cancelled
    )


def tube_operation_semantic_sha256(operation: TubeOperationDefinition) -> str:
    payload = {
        "operation_id": operation.operation_id,
        "operation_type": operation.operation_type,
        "geometry": operation.geometry.to_json(),
        "parameters": operation.parameters.to_json(),
        "type_config": None if operation.type_config is None else operation.type_config.to_json(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _indexed_result(result: IndexedProductResult) -> TubeProductResult:
    return TubeProductResult(
        "tube_thin_wall_indexed",
        result.feature,
        result.plan,
        result.toolpath,
        result.trajectory,
        result.validation,
        result.manifest,
        result.gcode,
        result.readback,
        (result.toolpath,),
    )


def _base_from_substrate(
    model: CadModel,
    operation: TubeOperationDefinition,
    feature: TubeFeature,
) -> PlanarBaseDefinition:
    reference = operation.geometry.substrate_body
    if reference is None:
        raise ValueError("planar base generation requires a substrate body")
    body = model.body_map.get(reference.object_id)
    if body is None or body.bounds is None:
        raise ValueError("selected substrate body has no usable bounds")
    minimum, maximum = body.bounds.minimum, body.bounds.maximum
    spans = tuple(right - left for left, right in zip(minimum, maximum, strict=True))
    axis = min(range(3), key=spans.__getitem__)
    if spans[axis] <= 0.0:
        raise ValueError("selected substrate body has degenerate bounds")
    tube_start = feature.centerline[0].start[axis]
    positive = abs(tube_start - maximum[axis]) <= abs(tube_start - minimum[axis])
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0 if positive else -1.0
    center = [(minimum[index] + maximum[index]) * 0.5 for index in range(3)]
    center[axis] = minimum[axis] if positive else maximum[axis]
    cross_spans = [span for index, span in enumerate(spans) if index != axis]
    radius = min(cross_spans) * 0.5
    return PlanarBaseDefinition(
        reference.object_id,
        tuple(center),  # type: ignore[arg-type]
        tuple(normal),  # type: ignore[arg-type]
        radius,
        spans[axis],
    )


def _merge_buildup_sequence(operation_id: str, sequence: TubeBuildupSequence) -> GeneratedToolpath:
    points: list[ToolpathPoint] = []
    events: list[ToolpathEvent] = []
    starts: dict[str, int] = {}
    for operation_index, path in enumerate(sequence.operations, start=1):
        starts[path.operation_id] = len(points)
        prefix = f"op{operation_index:02d}"
        for point in path.points:
            points.append(
                replace(
                    point,
                    point_id=f"{prefix}-{point.point_id}",
                    operation_id=operation_id,
                    stage_id=f"{prefix}-{point.stage_id}",
                )
            )
        for event in path.events:
            context = dict(event.context)
            context["sequence_index"] = starts[path.operation_id] + int(
                context.get("sequence_index", 0)
            )
            events.append(
                replace(
                    event,
                    event_id=f"{prefix}-{event.event_id}",
                    operation_id=operation_id,
                    stage_id=f"{prefix}-{event.stage_id}",
                    context=context,
                )
            )
    for index, event in enumerate(sequence.transition_events, start=1):
        target = str(event.context.get("to_operation_id", ""))
        context = dict(event.context)
        context["sequence_index"] = starts.get(target, 0)
        events.append(
            replace(
                event,
                event_id=f"transition-{index:04d}-{event.event_id}",
                operation_id=operation_id,
                context=context,
            )
        )
    return GeneratedToolpath(
        f"{operation_id}-buildup-sequence-v1",
        operation_id,
        coordinate_frame=sequence.operations[0].coordinate_frame,
        points=tuple(points),
        events=tuple(events),
    )


def _validate_buildup(
    plan: TubeBuildupPlan,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    nozzle: NozzleProfile,
    *,
    obstacles: tuple[CollisionBox, ...],
    check_ipw: bool,
) -> IndexedValidationReport:
    offsets = plan.pass_offsets_mm
    maximum_gap = max(
        (right - left for left, right in zip(offsets, offsets[1:], strict=False)),
        default=0.0,
    )
    metric = ValidationMetric(
        "maximum_pass_spacing",
        maximum_gap,
        plan.maximum_pass_spacing_mm,
        "mm",
        maximum_gap <= plan.maximum_pass_spacing_mm + 1.0e-9,
    )
    issues = list(trajectory.issues)
    if not metric.passed:
        issues.append(
            ValidationIssue(
                "tube.maximum_pass_spacing_exceeded",
                IssueSeverity.ERROR,
                toolpath.operation_id,
                {"measured_mm": maximum_gap, "limit_mm": plan.maximum_pass_spacing_mm},
            )
        )
    collision, checked = _collision_issues(toolpath, nozzle, obstacles, 0.25, check_ipw=check_ipw)
    issues.extend(collision)
    return IndexedValidationReport(
        f"{toolpath.toolpath_id}-validation-v1",
        toolpath.toolpath_id,
        trajectory.trajectory_id,
        tuple(_unique_issues(issues)),
        (metric,),
        checked,
        0.25,
    )


def _manifest(
    model: CadModel,
    source_path: str | Path | None,
    operation: TubeOperationDefinition,
    machine: MachineProfile,
    toolpath: GeneratedToolpath,
    validation: IndexedValidationReport,
) -> GeneratedResultManifest:
    return GeneratedResultManifest(
        result_id=f"{toolpath.toolpath_id}-result-v1",
        operation_id=operation.operation_id,
        status=validation.status,
        algorithm_version=ALGORITHM_VERSIONS[operation.operation_type],
        parameter_semantic_sha256=tube_operation_semantic_sha256(operation),
        input_sources=(_source_fingerprint(model, source_path),),
        toolpath=toolpath,
        machine_profile_id=machine.profile_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        ready_for_export=validation.ready_for_export,
        issues=tuple(issue.code for issue in validation.issues),
    )


def _source_fingerprint(model: CadModel, source_path: str | Path | None) -> SourceFingerprint:
    path = Path(source_path) if source_path is not None else None
    if path is not None and path.is_file():
        return SourceFingerprint(
            "cad_source", hashlib.sha256(path.read_bytes()).hexdigest(), "tube_step", str(path)
        )
    topology = {
        "bodies": [body.body_id for body in model.bodies],
        "edges": [edge.edge_id for edge in model.edges],
    }
    digest = hashlib.sha256(json.dumps(topology, sort_keys=True).encode()).hexdigest()
    return SourceFingerprint("cad_model", digest, "tube_step", "")


def _plan_json(plan: IndexedSlicePlan | TubeBuildupPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    if isinstance(plan, TubeBuildupPlan):
        return {
            "kind": "tube_buildup",
            "wall_thickness_mm": plan.wall_thickness_mm,
            "bead_width_mm": plan.bead_width_mm,
            "maximum_pass_spacing_mm": plan.maximum_pass_spacing_mm,
            "pass_offsets_mm": list(plan.pass_offsets_mm),
            "layers": [
                {
                    "layer_id": layer.layer_id,
                    "region_id": layer.region_id,
                    "centerline_distance_mm": layer.centerline_distance_mm,
                    "plane_origin": list(layer.plane_origin),
                    "plane_normal": list(layer.plane_normal),
                    "deposited_height_mm": layer.deposited_height_mm,
                }
                for layer in plan.layers
            ],
        }
    return {
        "kind": "tube_thin_wall_indexed",
        "regions": [item.region_id for item in plan.regions],
        "layers": [item.layer_id for item in plan.layers],
    }


def _checkpoint(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        from .indexed_tube import GenerationCancelled

        raise GenerationCancelled("Tube generation cancelled before publication")


__all__ = [
    "ALGORITHM_VERSIONS",
    "TubeProductResult",
    "TubeProductService",
    "TubeProductState",
    "export_tube_product",
    "generate_tube_product",
    "postprocess_tube_gcode",
    "readback_tube_gcode",
    "tube_operation_semantic_sha256",
]
