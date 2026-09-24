"""Curve workbench product chain: plan, Toolpath, axes, validation, post and readback."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import csv
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from tempfile import mkdtemp
from typing import Any

from ..algorithms.curve.chain import CurvePlan, build_curve_plan, project_point_to_face
from ..algorithms.curve.toolpath import generate_curve_toolpath
from ..kinematics.xyzac import MachineAxisTrajectory, solve_xyzac_trajectory
from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.curve_parameters import CurveOperationDefinition
from ..manufacturing.machine import MachineProfile
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.setup import IssueSeverity, ValidationIssue
from ..manufacturing.toolpath import (
    GeneratedResultManifest,
    GeneratedResultStatus,
    GeneratedToolpath,
    SourceFingerprint,
)
from ..models import CadModel, Vector3
from ..validation.indexed_tube import CollisionBox, ValidationMetric
from .gcode_readback import GCodeReadbackReport
from .indexed_tube import postprocess_indexed_gcode, readback_indexed_gcode

CURVE_PRODUCT_STATE_SCHEMA_VERSION = 1
CURVE_ALGORITHM_VERSIONS = {
    "curve_buildup": "curve-buildup-product-v1",
    "curve_multi_pass": "curve-multi-pass-product-v1",
    "curve_offset_buildup": "curve-offset-buildup-product-v1",
}
CURVE_MARKERS = {
    "curve_buildup": "C02",
    "curve_multi_pass": "C03",
    "curve_offset_buildup": "C04",
}
CancelCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class CurveValidationReport:
    report_id: str
    toolpath_id: str
    trajectory_id: str
    issues: tuple[ValidationIssue, ...]
    metrics: tuple[ValidationMetric, ...]
    collision_samples_checked: int = 0
    motion_sample_error_mm: float = 0.25

    @property
    def status(self) -> GeneratedResultStatus:
        if any(item.severity is IssueSeverity.ERROR for item in self.issues):
            return GeneratedResultStatus.ERROR
        return GeneratedResultStatus.WARNING if self.issues else GeneratedResultStatus.READY

    @property
    def ready_for_export(self) -> bool:
        return self.status in {GeneratedResultStatus.READY, GeneratedResultStatus.WARNING}

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "report_id": self.report_id,
            "toolpath_id": self.toolpath_id,
            "trajectory_id": self.trajectory_id,
            "status": self.status.value,
            "ready_for_export": self.ready_for_export,
            "issues": [item.to_json() for item in self.issues],
            "metrics": [item.to_json() for item in self.metrics],
            "collision_samples_checked": self.collision_samples_checked,
            "motion_sample_error_mm": self.motion_sample_error_mm,
        }


@dataclass(frozen=True, slots=True)
class CurveProductResult:
    operation_type: str
    plan: CurvePlan
    toolpath: GeneratedToolpath
    trajectory: MachineAxisTrajectory
    validation: CurveValidationReport
    manifest: GeneratedResultManifest
    gcode: str
    readback: GCodeReadbackReport

    @property
    def preview_toolpath(self) -> GeneratedToolpath:
        return self.toolpath

    @property
    def exportable(self) -> bool:
        return self.manifest.ready_for_export and self.readback.passed

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": CURVE_PRODUCT_STATE_SCHEMA_VERSION,
            "operation_type": self.operation_type,
            "manifest": self.manifest.to_json(),
            "curve_plan": self.plan.to_json(),
            "machine_trajectory": self.trajectory.to_json(),
            "validation": self.validation.to_json(),
            "readback": self.readback.to_json(),
            "preview_only": False,
        }


@dataclass(frozen=True, slots=True)
class CurveProductState:
    operation_id: str
    parameter_semantic_sha256: str
    status: str
    result_payload: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ready", "warning", "error", "stale", "draft"}:
            raise ValueError("unsupported Curve product state")
        if len(self.parameter_semantic_sha256) != 64:
            raise ValueError("parameter_semantic_sha256 must be a SHA-256 digest")

    def stale_for(self, operation: CurveOperationDefinition) -> "CurveProductState":
        digest = operation.semantic_sha256()
        return (
            self
            if digest == self.parameter_semantic_sha256
            else replace(self, parameter_semantic_sha256=digest, status="stale")
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": CURVE_PRODUCT_STATE_SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "parameter_semantic_sha256": self.parameter_semantic_sha256,
            "status": self.status,
            "result": self.result_payload,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "CurveProductState":
        if int(payload.get("schema_version", 0)) != CURVE_PRODUCT_STATE_SCHEMA_VERSION:
            raise ValueError("unsupported Curve product state schema")
        result = payload.get("result")
        if result is not None and not isinstance(result, Mapping):
            raise ValueError("Curve product result must be an object or null")
        state = cls(
            str(payload["operation_id"]),
            str(payload["parameter_semantic_sha256"]),
            str(payload["status"]),
            result,
        )
        # Product objects and G-code are deliberately not embedded in project.json.
        return replace(state, status="stale") if state.status in {"ready", "warning"} else state


def generate_curve_product(
    model: CadModel,
    operation: CurveOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    *,
    T_build_from_source: RigidTransform,
    T_workpiece_from_build: RigidTransform | None = None,
    source_path: str | Path | None = None,
    obstacles: tuple[CollisionBox, ...] = (),
    check_ipw: bool = False,
    cancelled: CancelCheck | None = None,
) -> CurveProductResult:
    _checkpoint(cancelled)
    plan = build_curve_plan(
        model,
        operation.operation_id,
        operation.geometry,
        operation.parameters,
        T_build_from_source=T_build_from_source,
        cancelled=cancelled,
    )
    project = _surface_projector(model, operation, T_build_from_source)
    toolpath = generate_curve_toolpath(plan, operation, cancelled=cancelled, project_point=project)
    _checkpoint(cancelled)
    trajectory = solve_xyzac_trajectory(
        toolpath,
        machine,
        tool_length_mm=nozzle.length_mm or 0.0,
        T_workpiece_from_build=T_workpiece_from_build,
    )
    validation = _validate_curve(
        plan, toolpath, trajectory, operation, nozzle, obstacles, check_ipw
    )
    manifest = _result_manifest(model, operation, machine, toolpath, validation, source_path)
    if not manifest.ready_for_export:
        return _blocked_result(operation, plan, toolpath, trajectory, validation, manifest)
    return _postprocessed_result(
        operation, machine, nozzle, plan, toolpath, trajectory, validation, manifest
    )


def _surface_projector(
    model: CadModel,
    operation: CurveOperationDefinition,
    transform: RigidTransform,
) -> Callable[[Vector3], Vector3] | None:
    if operation.operation_type != "curve_offset_buildup" or not operation.geometry.normal_face:
        return None
    face_id = operation.geometry.normal_face.object_id
    inverse = transform.inverse()

    def project(build_point: Vector3) -> Vector3:
        source_point = inverse.transform_point(build_point)
        return transform.transform_point(project_point_to_face(model, face_id, source_point))

    return project


def _result_manifest(
    model: CadModel,
    operation: CurveOperationDefinition,
    machine: MachineProfile,
    toolpath: GeneratedToolpath,
    validation: CurveValidationReport,
    source_path: str | Path | None,
) -> GeneratedResultManifest:
    return GeneratedResultManifest(
        f"{toolpath.toolpath_id}-result-v1",
        operation.operation_id,
        validation.status,
        CURVE_ALGORITHM_VERSIONS[operation.operation_type],
        operation.semantic_sha256(),
        (_source_fingerprint(model, source_path),),
        toolpath,
        machine.profile_id,
        datetime.now(timezone.utc).isoformat(),
        validation.ready_for_export,
        tuple(item.code for item in validation.issues),
    )


def _blocked_result(
    operation: CurveOperationDefinition,
    plan: CurvePlan,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    validation: CurveValidationReport,
    manifest: GeneratedResultManifest,
) -> CurveProductResult:
    return CurveProductResult(
        operation.operation_type,
        plan,
        toolpath,
        trajectory,
        validation,
        manifest,
        "",
        GCodeReadbackReport(len(toolpath.points), 0, (), (), (), ("blocked",)),
    )


def _postprocessed_result(
    operation: CurveOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    plan: CurvePlan,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    validation: CurveValidationReport,
    manifest: GeneratedResultManifest,
) -> CurveProductResult:
    marker = CURVE_MARKERS[operation.operation_type]
    gcode = postprocess_indexed_gcode(
        toolpath,
        trajectory,
        machine,
        nozzle,
        header=f"5AxisSclicer {marker} {operation.name}",
        marker_tag=marker,
    )
    readback = readback_indexed_gcode(
        gcode, toolpath, trajectory, machine, nozzle, marker_tag=marker
    )
    if not readback.passed:
        manifest = replace(
            manifest,
            status=GeneratedResultStatus.ERROR,
            ready_for_export=False,
            issues=(*manifest.issues, "curve.gcode_readback_failed"),
        )
    return CurveProductResult(
        operation.operation_type,
        plan,
        toolpath,
        trajectory,
        validation,
        manifest,
        gcode,
        readback,
    )


def state_from_curve_result(
    operation: CurveOperationDefinition, result: CurveProductResult
) -> CurveProductState:
    return CurveProductState(
        operation.operation_id,
        operation.semantic_sha256(),
        _status_value(result.manifest.status),
        result.to_json(),
    )


def export_curve_product(
    result: CurveProductResult,
    destination: str | Path,
    *,
    cancelled: CancelCheck | None = None,
) -> Path:
    if not result.exportable:
        raise ValueError("validation Error or failed G-code readback blocks export")
    from .export_target_guard import validate_export_target

    validate_export_target(Path(destination))
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(mkdtemp(prefix=f".{target.name}.stage-", dir=target.parent))
    backup = target.with_name(f".{target.name}.previous")
    try:
        _checkpoint(cancelled)
        _write_artifacts(stage, result)
        _checkpoint(cancelled)
        validate_export_target(target)
        if backup.exists():
            raise ValueError(f"previous export backup requires review: {backup}")
        moved_old = False
        if target.exists():
            os.replace(target, backup)
            moved_old = True
        try:
            os.replace(stage, target)
        except Exception:
            if moved_old and backup.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return target
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _validate_curve(
    plan: CurvePlan,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    operation: CurveOperationDefinition,
    nozzle: NozzleProfile,
    obstacles: tuple[CollisionBox, ...],
    check_ipw: bool,
) -> CurveValidationReport:
    expected_length, length_error, volume_error, length_limit = _path_measurements(
        plan, toolpath, operation
    )
    metrics = _curve_metrics(trajectory, operation, length_error, volume_error, length_limit)
    issues = list(_coalesced_trajectory_issues(trajectory.issues))
    issues.extend(_metric_issues(metrics))
    collision_issues, checked = _curve_collision_issues(toolpath, nozzle, obstacles, check_ipw)
    issues.extend(collision_issues)
    return CurveValidationReport(
        f"{toolpath.toolpath_id}-validation-v1",
        toolpath.toolpath_id,
        trajectory.trajectory_id,
        tuple(issues),
        metrics,
        checked,
    )


def _path_measurements(
    plan: CurvePlan,
    toolpath: GeneratedToolpath,
    operation: CurveOperationDefinition,
) -> tuple[float, float, float, float]:
    groups: dict[tuple[str, str], list[Any]] = {}
    for point in toolpath.points:
        groups.setdefault((point.layer_id, point.region_id), []).append(point)
    deposited_segments = [
        (math.dist(left.position, right.position), right)
        for group in groups.values()
        for left, right in zip(group, group[1:])
        if right.point_type == "deposition"
    ]
    base_group = next(iter(groups.values()), [])
    base_length = sum(
        math.dist(left.position, right.position)
        for left, right in zip(base_group, base_group[1:])
        if right.point_type == "deposition"
    )
    expected_length = plan.total_length_mm
    length_error = abs(expected_length - base_length)
    actual_volume = sum(item.material_volume_mm3 for item in toolpath.points)
    expected_volume = sum(
        length * point.bead_width_mm * point.layer_height_mm
        for length, point in deposited_segments
        if point.bead_width_mm is not None and point.layer_height_mm is not None
    )
    volume_error = abs(actual_volume - expected_volume)
    length_limit = max(operation.parameters.chord_error_mm, 1.0e-6)
    return expected_length, length_error, volume_error, length_limit


def _curve_metrics(
    trajectory: MachineAxisTrajectory,
    operation: CurveOperationDefinition,
    length_error: float,
    volume_error: float,
    length_limit: float,
) -> tuple[ValidationMetric, ...]:
    fk_position_error = max((item.fk_position_error_mm for item in trajectory.samples), default=0.0)
    fk_orientation_error = max(
        (item.fk_orientation_error_rad for item in trajectory.samples), default=0.0
    )
    return (
        ValidationMetric(
            "curve_path_length_error",
            length_error,
            length_limit,
            "mm",
            length_error <= length_limit,
        ),
        ValidationMetric(
            "curve_material_volume_error",
            volume_error,
            length_limit
            * operation.parameters.bead_width_mm
            * operation.parameters.layer_height_mm,
            "mm3",
            volume_error
            <= length_limit
            * operation.parameters.bead_width_mm
            * operation.parameters.layer_height_mm,
        ),
        ValidationMetric(
            "curve_fk_position_error",
            fk_position_error,
            0.01,
            "mm",
            fk_position_error <= 0.01,
        ),
        ValidationMetric(
            "curve_fk_orientation_error",
            fk_orientation_error,
            math.radians(0.01),
            "rad",
            fk_orientation_error <= math.radians(0.01),
        ),
    )


def _metric_issues(metrics: tuple[ValidationMetric, ...]) -> tuple[ValidationIssue, ...]:
    return tuple(
        ValidationIssue(
            f"curve.metric.{item.name}",
            IssueSeverity.ERROR,
            context={"value": item.value, "limit": item.limit, "unit": item.unit},
        )
        for item in metrics
        if not item.passed
    )


def _curve_collision_issues(
    toolpath: GeneratedToolpath,
    nozzle: NozzleProfile,
    obstacles: tuple[CollisionBox, ...],
    check_ipw: bool,
) -> tuple[tuple[ValidationIssue, ...], int]:
    if not obstacles:
        return (), 0
    from ..validation.indexed_tube import _collision_issues

    issues, checked = _collision_issues(toolpath, nozzle, obstacles, 0.25, check_ipw=check_ipw)
    mapped = tuple(
            replace(issue, code=issue.code.replace("tube.", "curve.", 1))
            if issue.code.startswith("tube.")
            else issue
            for issue in issues
    )
    return _coalesced_trajectory_issues(mapped), checked


def _status_value(status: GeneratedResultStatus | str) -> str:
    return status.value if isinstance(status, GeneratedResultStatus) else status


def _coalesced_trajectory_issues(
    issues: tuple[ValidationIssue, ...],
) -> tuple[ValidationIssue, ...]:
    grouped: dict[tuple[str, IssueSeverity], list[ValidationIssue]] = {}
    for issue in issues:
        grouped.setdefault((issue.code, issue.severity), []).append(issue)
    return tuple(
        ValidationIssue(
            code,
            severity,
            entries[0].object_id,
            {"count": len(entries), "first_context": dict(entries[0].context)},
        )
        for (code, severity), entries in grouped.items()
    )


def _source_fingerprint(model: CadModel, source_path: str | Path | None) -> SourceFingerprint:
    path = Path(source_path) if source_path is not None else None
    if path is not None and path.is_file():
        return SourceFingerprint(
            "cad_source", hashlib.sha256(path.read_bytes()).hexdigest(), "curve_step", str(path)
        )
    digest = hashlib.sha256(
        json.dumps([item.to_json() for item in model.edges], sort_keys=True).encode()
    ).hexdigest()
    return SourceFingerprint("cad_model", digest, "curve_step", "")


def _write_artifacts(directory: Path, result: CurveProductResult) -> None:
    (directory / "main.gcode").write_text(result.gcode, encoding="utf-8", newline="\n")
    _write_json(directory / "toolpath.json", result.toolpath.to_json())
    _write_json(directory / "warnings.json", result.validation.to_json())
    _write_json(
        directory / "preview.json",
        {
            "coordinate_frame": result.toolpath.coordinate_frame,
            "segments": [
                {
                    "start": list(item.start),
                    "end": list(item.end),
                    "move_type": item.move_type,
                    "extrusion_role": item.extrusion_role,
                    "feedrate": item.feedrate,
                    "delta_e": item.delta_e,
                    "width": item.width,
                    "height": item.height,
                    "comment": item.comment,
                }
                for item in result.toolpath.to_preview_segments()
            ],
        },
    )
    _write_json(directory / "manifest.json", result.to_json())
    with (directory / "machine_axes.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("source_point_id", "time_s", "X", "Y", "Z", "A_rad", "C_rad"))
        for sample in result.trajectory.samples:
            joints = sample.joint_positions
            writer.writerow(
                (
                    sample.source_point_id,
                    f"{sample.time_s:.9f}",
                    *(f"{joints.get(axis, 0.0):.9f}" for axis in ("X", "Y", "Z", "A", "C")),
                )
            )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _checkpoint(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        from .indexed_tube import GenerationCancelled

        raise GenerationCancelled("Curve product generation cancelled")


__all__ = [
    "CURVE_ALGORITHM_VERSIONS",
    "CurveProductResult",
    "CurveProductState",
    "CurveValidationReport",
    "export_curve_product",
    "generate_curve_product",
    "state_from_curve_result",
]
