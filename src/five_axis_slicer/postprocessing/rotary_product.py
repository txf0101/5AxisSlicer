"""Rotary workbench product chain and inspectable six-file export.

Rotary path phase is a manufacturing input, not a display angle.  The phase
therefore stays continuously unwrapped in the plan and is passed explicitly to
the machine trajectory solver.  Machine controller words remain profile data
and are verified by the shared G-code readback path.
"""

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

from ..algorithms.rotary import (
    RotaryPlan,
    RotaryPlanningError,
    build_rotary_plan,
    generate_rotary_toolpath,
)
from ..kinematics.rotary import solve_prescribed_rotary_trajectory
from ..kinematics.xyzac import MachineAxisTrajectory
from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.machine import MachineProfile
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.rotary_parameters import RotaryOperationDefinition
from ..manufacturing.setup import IssueSeverity, ValidationIssue
from ..manufacturing.toolpath import (
    GeneratedResultManifest,
    GeneratedResultStatus,
    GeneratedToolpath,
    SourceFingerprint,
)
from ..models import CadModel
from ..validation.indexed_tube import CollisionBox, ValidationMetric
from .gcode_readback import GCodeReadbackReport
from .indexed_tube import postprocess_indexed_gcode, readback_indexed_gcode

ROTARY_PRODUCT_STATE_SCHEMA_VERSION = 1
ROTARY_ALGORITHM_VERSIONS = {
    "rotary_spiral": "rotary-spiral-product-v1",
    "rotary_thin_wall": "rotary-thin-wall-product-v1",
    "rotary_around_part": "rotary-around-part-product-v1",
}
ROTARY_MARKERS = {
    "rotary_spiral": "R02",
    "rotary_thin_wall": "R03",
    "rotary_around_part": "R04",
}
CancelCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class RotaryValidationReport:
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
class RotaryProductResult:
    operation_type: str
    plan: RotaryPlan
    toolpath: GeneratedToolpath
    trajectory: MachineAxisTrajectory
    validation: RotaryValidationReport
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
            "schema_version": ROTARY_PRODUCT_STATE_SCHEMA_VERSION,
            "operation_type": self.operation_type,
            "manifest": self.manifest.to_json(),
            "rotary_plan": self.plan.to_json(),
            "machine_trajectory": self.trajectory.to_json(),
            "validation": self.validation.to_json(),
            "readback": self.readback.to_json(),
            "preview_only": False,
        }


@dataclass(frozen=True, slots=True)
class RotaryProductState:
    operation_id: str
    parameter_semantic_sha256: str
    status: str
    result_payload: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ready", "warning", "error", "stale", "draft"}:
            raise ValueError("unsupported Rotary product state")
        if len(self.parameter_semantic_sha256) != 64:
            raise ValueError("parameter_semantic_sha256 must be a SHA-256 digest")

    def stale_for(self, operation: RotaryOperationDefinition) -> "RotaryProductState":
        digest = operation.semantic_sha256()
        return (
            self
            if digest == self.parameter_semantic_sha256
            else replace(self, parameter_semantic_sha256=digest, status="stale")
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": ROTARY_PRODUCT_STATE_SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "parameter_semantic_sha256": self.parameter_semantic_sha256,
            "status": self.status,
            "result": self.result_payload,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "RotaryProductState":
        if int(payload.get("schema_version", 0)) != ROTARY_PRODUCT_STATE_SCHEMA_VERSION:
            raise ValueError("unsupported Rotary product state schema")
        result = payload.get("result")
        if result is not None and not isinstance(result, Mapping):
            raise ValueError("Rotary product result must be an object or null")
        state = cls(
            str(payload["operation_id"]),
            str(payload["parameter_semantic_sha256"]),
            str(payload["status"]),
            result,
        )
        # Generated toolpath, axes and NC are rebuilt and read back after reopen.
        return replace(state, status="stale") if state.status in {"ready", "warning"} else state


def generate_rotary_product(
    model: CadModel,
    operation: RotaryOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    *,
    T_build_from_source: RigidTransform,
    T_workpiece_from_build: RigidTransform | None = None,
    source_path: str | Path | None = None,
    obstacles: tuple[CollisionBox, ...] = (),
    check_ipw: bool = False,
    motion_sample_error_mm: float = 0.25,
    cancelled: CancelCheck | None = None,
) -> RotaryProductResult:
    """Generate, qualify, postprocess and read back one Rotary operation."""

    _checkpoint(cancelled)
    _require_rotary_axis_alignment(
        operation,
        machine,
        T_build_from_source,
        T_workpiece_from_build,
    )
    try:
        plan = build_rotary_plan(
            operation,
            T_build_from_source=T_build_from_source,
            cancelled=cancelled,
        )
    except RotaryPlanningError as exc:
        if exc.code != "rotary.generation_cancelled":
            raise
        from .indexed_tube import GenerationCancelled

        raise GenerationCancelled("Rotary product generation cancelled") from exc
    toolpath = generate_rotary_toolpath(plan, operation)
    _checkpoint(cancelled)
    trajectory = solve_prescribed_rotary_trajectory(
        toolpath,
        machine,
        prescribed_angles_rad=plan.angle_by_point_id,
        angular_velocity_rad_s=operation.parameters.angular_velocity_rad_s,
        tool_length_mm=nozzle.length_mm or 0.0,
        T_workpiece_from_build=T_workpiece_from_build,
    )
    validation = _validate_rotary(
        plan,
        toolpath,
        trajectory,
        operation,
        machine,
        nozzle,
        obstacles,
        check_ipw,
        motion_sample_error_mm,
    )
    manifest = _result_manifest(model, operation, machine, toolpath, validation, source_path)
    if not manifest.ready_for_export:
        return _blocked_result(operation, plan, toolpath, trajectory, validation, manifest)
    return _postprocessed_result(
        operation,
        machine,
        nozzle,
        plan,
        toolpath,
        trajectory,
        validation,
        manifest,
    )


def _require_rotary_axis_alignment(
    operation: RotaryOperationDefinition,
    machine: MachineProfile,
    build_from_source: RigidTransform,
    workpiece_from_build: RigidTransform | None,
) -> None:
    c_axis = machine.joint_map.get("C")
    if c_axis is None or c_axis.joint_type != "rotary":
        raise ValueError("rotary.machine_c_axis_missing")
    axis = build_from_source.transform_vector(operation.geometry.frame.axis_direction)
    if workpiece_from_build is not None:
        axis = workpiece_from_build.transform_vector(axis)
    zero_transform = c_axis.T_parent_from_child_zero
    if zero_transform is not None:
        axis = zero_transform.transform_vector(axis)
    length = math.sqrt(sum(value * value for value in axis))
    if length <= 1.0e-12:
        raise ValueError("rotary.axis_not_aligned_with_machine_c")
    alignment = sum(
        value / length * expected
        for value, expected in zip(axis, c_axis.axis_direction, strict=True)
    )
    if abs(alignment) < 1.0 - 1.0e-6:
        raise ValueError("rotary.axis_not_aligned_with_machine_c")


def state_from_rotary_result(
    operation: RotaryOperationDefinition, result: RotaryProductResult
) -> RotaryProductState:
    return RotaryProductState(
        operation.operation_id,
        operation.semantic_sha256(),
        _status_value(result.manifest.status),
        result.to_json(),
    )


def export_rotary_product(
    result: RotaryProductResult,
    destination: str | Path,
    *,
    cancelled: CancelCheck | None = None,
) -> Path:
    """Atomically publish main.gcode plus the five inspectable sidecars."""

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


def _result_manifest(
    model: CadModel,
    operation: RotaryOperationDefinition,
    machine: MachineProfile,
    toolpath: GeneratedToolpath,
    validation: RotaryValidationReport,
    source_path: str | Path | None,
) -> GeneratedResultManifest:
    return GeneratedResultManifest(
        f"{toolpath.toolpath_id}-result-v1",
        operation.operation_id,
        validation.status,
        ROTARY_ALGORITHM_VERSIONS[operation.operation_type],
        operation.semantic_sha256(),
        (_source_fingerprint(model, source_path),),
        toolpath,
        machine.profile_id,
        datetime.now(timezone.utc).isoformat(),
        validation.ready_for_export,
        tuple(item.code for item in validation.issues),
    )


def _blocked_result(
    operation: RotaryOperationDefinition,
    plan: RotaryPlan,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    validation: RotaryValidationReport,
    manifest: GeneratedResultManifest,
) -> RotaryProductResult:
    return RotaryProductResult(
        operation.operation_type,
        plan,
        toolpath,
        trajectory,
        validation,
        manifest,
        "",
        GCodeReadbackReport(
            len(toolpath.points),
            0,
            (),
            (),
            (),
            ("export_blocked_by_validation",),
        ),
    )


def _postprocessed_result(
    operation: RotaryOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    plan: RotaryPlan,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    validation: RotaryValidationReport,
    manifest: GeneratedResultManifest,
) -> RotaryProductResult:
    marker = ROTARY_MARKERS[operation.operation_type]
    gcode = postprocess_indexed_gcode(
        toolpath,
        trajectory,
        machine,
        nozzle,
        header=f"5AxisSclicer {marker} {operation.name}",
        marker_tag=marker,
        inverse_time=True,
    )
    readback = readback_indexed_gcode(
        gcode,
        toolpath,
        trajectory,
        machine,
        nozzle,
        marker_tag=marker,
    )
    if not readback.passed:
        manifest = replace(
            manifest,
            status=GeneratedResultStatus.ERROR,
            ready_for_export=False,
            issues=(*manifest.issues, "rotary.gcode_readback_failed"),
        )
    return RotaryProductResult(
        operation.operation_type,
        plan,
        toolpath,
        trajectory,
        validation,
        manifest,
        gcode,
        readback,
    )


def _validate_rotary(
    plan: RotaryPlan,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    operation: RotaryOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    obstacles: tuple[CollisionBox, ...],
    check_ipw: bool,
    motion_sample_error_mm: float,
) -> RotaryValidationReport:
    if not nozzle.is_ready:
        raise ValueError("collision validation requires a complete Nozzle Profile")
    if len(toolpath.points) != len(trajectory.samples):
        raise ValueError("toolpath and machine trajectory sample counts differ")
    if not math.isfinite(motion_sample_error_mm) or motion_sample_error_mm <= 0.0:
        raise ValueError("motion_sample_error_mm must be positive")
    metrics = _rotary_metrics(plan, toolpath, trajectory, operation)
    issues = list(_plan_issues(plan))
    issues.extend(_coalesced_issues(trajectory.issues))
    issues.extend(_metric_issues(metrics))
    collision_issues, checked = _rotary_collision_issues(
        toolpath,
        nozzle,
        obstacles,
        check_ipw,
        motion_sample_error_mm,
    )
    issues.extend(collision_issues)
    if not any(item.role == "substrate" for item in obstacles):
        issues.append(
            ValidationIssue(
                "rotary.substrate_collision_geometry_unavailable",
                IssueSeverity.WARNING,
                operation.operation_id,
            )
        )
    if not any(item.role == "machine" for item in obstacles):
        issues.append(
            ValidationIssue(
                "rotary.machine_collision_geometry_unavailable",
                IssueSeverity.WARNING,
                machine.profile_id,
                {"reference_only": machine.reference_only},
            )
        )
    return RotaryValidationReport(
        f"{toolpath.toolpath_id}-validation-v1",
        toolpath.toolpath_id,
        trajectory.trajectory_id,
        tuple(issues),
        metrics,
        checked,
        float(motion_sample_error_mm),
    )


def _rotary_metrics(
    plan: RotaryPlan,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    operation: RotaryOperationDefinition,
) -> tuple[ValidationMetric, ...]:
    deposited = [
        (left, right)
        for left, right in zip(toolpath.points, toolpath.points[1:])
        if right.point_type == "deposition"
        and right.material_volume_mm3 > 0.0
    ]
    sampled_length = sum(math.dist(left.position, right.position) for left, right in deposited)
    expected_length = float(plan.deposition_length_mm)
    length_error = abs(sampled_length - expected_length)
    length_limit = max(
        1.0e-6,
        expected_length * operation.parameters.sampling_angle_rad**2 / 20.0,
    )

    actual_volume = sum(point.material_volume_mm3 for point in toolpath.points)
    geometric_volume = sum(
        math.dist(left.position, right.position)
        * float(right.bead_width_mm or 0.0)
        * float(right.layer_height_mm or 0.0)
        for left, right in deposited
    )
    volume_error = abs(actual_volume - geometric_volume)
    volume_limit = max(
        1.0e-9,
        length_limit
        * operation.parameters.bead_width_mm
        * operation.parameters.layer_height_mm,
    )

    phases = [float(plan.angle_by_point_id[point.point_id]) for point in toolpath.points]
    phase_steps = [abs(right - left) for left, right in zip(phases, phases[1:])]
    maximum_phase_step = max(phase_steps, default=0.0)
    fk_position_error = max(
        (sample.fk_position_error_mm for sample in trajectory.samples),
        default=0.0,
    )
    fk_orientation_error = max(
        (sample.fk_orientation_error_rad for sample in trajectory.samples),
        default=0.0,
    )
    return (
        ValidationMetric(
            "rotary_path_length_error",
            length_error,
            length_limit,
            "mm",
            length_error <= length_limit,
        ),
        ValidationMetric(
            "rotary_material_volume_error",
            volume_error,
            volume_limit,
            "mm3",
            volume_error <= volume_limit,
        ),
        ValidationMetric(
            "rotary_maximum_unwrapped_phase_step",
            maximum_phase_step,
            math.pi,
            "rad",
            maximum_phase_step <= math.pi + 1.0e-12,
        ),
        ValidationMetric(
            "rotary_fk_position_error",
            fk_position_error,
            0.01,
            "mm",
            fk_position_error <= 0.01,
        ),
        ValidationMetric(
            "rotary_fk_orientation_error",
            fk_orientation_error,
            math.radians(0.01),
            "rad",
            fk_orientation_error <= math.radians(0.01),
        ),
    )


def _plan_issues(plan: RotaryPlan) -> tuple[ValidationIssue, ...]:
    return tuple(
        ValidationIssue(
            code,
            (
                IssueSeverity.WARNING
                if code == "rotary.thin_wall_width_reduced"
                else IssueSeverity.ERROR
            ),
            plan.operation_id,
        )
        for code in plan.issues
    )


def _metric_issues(metrics: tuple[ValidationMetric, ...]) -> tuple[ValidationIssue, ...]:
    return tuple(
        ValidationIssue(
            f"rotary.metric.{item.name}",
            IssueSeverity.ERROR,
            context={"value": item.value, "limit": item.limit, "unit": item.unit},
        )
        for item in metrics
        if not item.passed
    )


def _rotary_collision_issues(
    toolpath: GeneratedToolpath,
    nozzle: NozzleProfile,
    obstacles: tuple[CollisionBox, ...],
    check_ipw: bool,
    motion_sample_error_mm: float,
) -> tuple[tuple[ValidationIssue, ...], int]:
    if not obstacles and not check_ipw:
        return (), 0
    from ..validation.indexed_tube import _collision_issues

    issues, checked = _collision_issues(
        toolpath,
        nozzle,
        obstacles,
        motion_sample_error_mm,
        check_ipw=check_ipw,
    )
    mapped = tuple(
        replace(issue, code=issue.code.replace("tube.", "rotary.", 1))
        if issue.code.startswith("tube.")
        else issue
        for issue in issues
    )
    return _coalesced_issues(mapped), checked


def _coalesced_issues(issues: tuple[ValidationIssue, ...]) -> tuple[ValidationIssue, ...]:
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
            "cad_source",
            hashlib.sha256(path.read_bytes()).hexdigest(),
            "rotary_step",
            str(path),
        )
    digest = hashlib.sha256(
        json.dumps(model.to_json(), ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return SourceFingerprint("cad_model", digest, "rotary_step", "")


def _write_artifacts(directory: Path, result: RotaryProductResult) -> None:
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
        writer.writerow(
            (
                "source_point_id",
                "time_s",
                "rotary_phase_rad",
                "X",
                "Y",
                "Z",
                "A_rad",
                "C_rad",
            )
        )
        for sample in result.trajectory.samples:
            joints = sample.joint_positions
            writer.writerow(
                (
                    sample.source_point_id,
                    f"{sample.time_s:.9f}",
                    f"{result.plan.angle_by_point_id[sample.source_point_id]:.9f}",
                    *(f"{joints.get(axis, 0.0):.9f}" for axis in ("X", "Y", "Z", "A", "C")),
                )
            )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _status_value(status: GeneratedResultStatus | str) -> str:
    return status.value if isinstance(status, GeneratedResultStatus) else status


def _checkpoint(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        from .indexed_tube import GenerationCancelled

        raise GenerationCancelled("Rotary product generation cancelled")


__all__ = [
    "ROTARY_ALGORITHM_VERSIONS",
    "RotaryProductResult",
    "RotaryProductState",
    "RotaryValidationReport",
    "export_rotary_product",
    "generate_rotary_product",
    "state_from_rotary_result",
]
