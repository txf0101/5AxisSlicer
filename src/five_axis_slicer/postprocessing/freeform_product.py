"""Restricted Freeform product chain for the paper-core AC offline release."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from tempfile import mkdtemp
from typing import Any, Mapping

from ..algorithms.freeform import FreeformPlan, build_freeform_plan, generate_freeform_toolpath
from ..kinematics.xyzac import MachineAxisTrajectory, solve_xyzac_trajectory
from ..manufacturing.controller_profile import ControllerProfile
from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.freeform_parameters import FreeformOperationDefinition
from ..manufacturing.freeform_solid_parameters import SOLID_FILL_OPERATION_TYPES
from ..manufacturing.machine import MachineProfile
from ..manufacturing.material_plan import material_statistics
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.setup import IssueSeverity, ValidationIssue
from ..manufacturing.toolpath import (
    GeneratedResultManifest,
    GeneratedResultStatus,
    GeneratedToolpath,
    SourceFingerprint,
)
from ..models import CadModel
from ..validation.indexed_tube import ValidationMetric
from .own_ac import OwnACReadbackReport, postprocess_own_ac, readback_own_ac
from .operation_transition import (
    OperationTransitionError,
    plan_machine_non_deposition_travels,
    plan_machine_operation_transitions,
)
from .freeform_solid_product import SolidFillPlan, generate_solid_fill_product_path
from .tool_change_service import (
    ToolChangeCollisionError,
    ToolChangeServicePlan,
    check_non_deposition_travel_safety,
    check_operation_transition_safety,
    plan_tool_change_service,
)
from .thermal_program import (
    ThermalProgramParameters,
    unwrap_checked_thermal_program,
    wrap_thermal_program,
)

FREEFORM_ALGORITHM_VERSION = "paper-core-freeform-product-v2"
CancelCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class FreeformValidationReport:
    report_id: str
    issues: tuple[ValidationIssue, ...]
    metrics: tuple[ValidationMetric, ...]
    material_statistics: Mapping[str, Any]
    controller_qualification: Mapping[str, Any]

    @property
    def status(self) -> GeneratedResultStatus:
        if any(item.severity is IssueSeverity.ERROR for item in self.issues):
            return GeneratedResultStatus.ERROR
        return GeneratedResultStatus.WARNING if self.issues else GeneratedResultStatus.READY

    @property
    def ready_for_offline_export(self) -> bool:
        return self.status in {GeneratedResultStatus.READY, GeneratedResultStatus.WARNING}

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "report_id": self.report_id,
            "status": self.status.value,
            "ready_for_offline_export": self.ready_for_offline_export,
            "issues": [item.to_json() for item in self.issues],
            "metrics": [item.to_json() for item in self.metrics],
            "material_statistics": dict(self.material_statistics),
            "controller_qualification": dict(self.controller_qualification),
        }


@dataclass(frozen=True, slots=True)
class FreeformProductResult:
    plan: FreeformPlan | SolidFillPlan
    toolpath: GeneratedToolpath
    trajectory: MachineAxisTrajectory
    validation: FreeformValidationReport
    manifest: GeneratedResultManifest
    gcode: str
    readback: OwnACReadbackReport
    thermal_parameters: ThermalProgramParameters | None = None

    @property
    def offline_exportable(self) -> bool:
        return self.manifest.ready_for_export and self.readback.passed

    @property
    def exportable(self) -> bool:
        """Compatibility alias: export means offline review bundle here."""

        return self.offline_exportable

    @property
    def preview_toolpath(self) -> GeneratedToolpath:
        return self.toolpath

    @property
    def machine_executable(self) -> bool:
        return bool(self.validation.controller_qualification.get("machine_executable", False))

    def to_json(self) -> dict[str, Any]:
        # The full points and machine samples have their own export files. Keeping
        # them in the project/HTTP result as well made a million-point operation
        # consume gigabytes merely to refresh the workbench status.
        manifest = {
            "result_id": self.manifest.result_id,
            "operation_id": self.manifest.operation_id,
            "status": (
                self.manifest.status.value
                if isinstance(self.manifest.status, GeneratedResultStatus)
                else str(self.manifest.status)
            ),
            "algorithm_version": self.manifest.algorithm_version,
            "parameter_semantic_sha256": self.manifest.parameter_semantic_sha256,
            "input_sources": [source.to_json() for source in self.manifest.input_sources],
            "machine_profile_id": self.manifest.machine_profile_id,
            "generated_at_utc": self.manifest.generated_at_utc,
            "ready_for_export": self.manifest.ready_for_export,
            "issues": list(self.manifest.issues),
        }
        return {
            "schema_version": 2,
            "operation_type": "freeform",
            "offline_exportable": self.offline_exportable,
            "machine_executable": self.machine_executable,
            "manifest": manifest,
            "freeform_plan": self.plan.to_json(),
            "toolpath_summary": {
                "toolpath_id": self.toolpath.toolpath_id,
                "point_count": len(self.toolpath.points),
                "event_count": len(self.toolpath.events),
                "coordinate_frame": self.toolpath.coordinate_frame,
            },
            "machine_trajectory_summary": {
                "trajectory_id": self.trajectory.trajectory_id,
                "machine_profile_id": self.trajectory.machine_profile_id,
                "source_toolpath_id": self.trajectory.source_toolpath_id,
                "sample_count": len(self.trajectory.samples),
                "tool_length_mm": self.trajectory.tool_length_mm,
            },
            "validation": self.validation.to_json(),
            "readback": self.readback.to_json(),
            "thermal_parameters": (
                None
                if self.thermal_parameters is None
                else {
                    "nozzle_c": self.thermal_parameters.nozzle_c,
                    "bed_c": self.thermal_parameters.bed_c,
                }
            ),
        }


@dataclass(frozen=True, slots=True)
class FreeformProductState:
    operation_id: str
    parameter_semantic_sha256: str
    status: str
    result_payload: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        operation_id = str(self.operation_id).strip()
        if not operation_id:
            raise ValueError("operation_id must not be empty")
        object.__setattr__(self, "operation_id", operation_id)
        digest = str(self.parameter_semantic_sha256).strip().lower()
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("parameter_semantic_sha256 must be a SHA-256 hex digest")
        object.__setattr__(self, "parameter_semantic_sha256", digest)
        status = str(self.status).strip().lower()
        if status not in {"empty", "generating", "ready", "warning", "error", "stale", "cancelled"}:
            raise ValueError(f"unsupported Freeform product status: {status}")
        object.__setattr__(self, "status", status)
        if self.result_payload is not None and not isinstance(self.result_payload, Mapping):
            raise TypeError("result_payload must be an object or null")

    def stale_for(self, operation: FreeformOperationDefinition) -> "FreeformProductState":
        digest = operation.semantic_sha256()
        return (
            self
            if digest == self.parameter_semantic_sha256
            else replace(self, parameter_semantic_sha256=digest, status="stale")
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "operation_id": self.operation_id,
            "parameter_semantic_sha256": self.parameter_semantic_sha256,
            "status": self.status,
            "result": self.result_payload,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "FreeformProductState":
        if int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported Freeform product state schema")
        result = payload.get("result")
        if result is not None and not isinstance(result, Mapping):
            raise ValueError("Freeform result must be an object or null")
        state = cls(
            str(payload["operation_id"]),
            str(payload["parameter_semantic_sha256"]),
            str(payload["status"]),
            result,
        )
        if state.status in {"ready", "warning"}:
            return replace(state, status="stale")
        return state


def generate_freeform_product(
    model: CadModel,
    operation: FreeformOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    controller: ControllerProfile,
    *,
    T_build_from_source: RigidTransform,
    T_workpiece_from_build: RigidTransform | None = None,
    source_path: str | Path | None = None,
    cancelled: CancelCheck | None = None,
    thermal_parameters: ThermalProgramParameters | None = None,
) -> FreeformProductResult:
    _checkpoint(cancelled)
    plan: FreeformPlan | SolidFillPlan
    toolpath: GeneratedToolpath
    if operation.operation_type in SOLID_FILL_OPERATION_TYPES:
        solid_plan, toolpath = generate_solid_fill_product_path(
            model,
            operation,
            T_build_from_source=T_build_from_source,
            cancelled=cancelled,
        )
        plan = solid_plan
    else:
        freeform_plan = build_freeform_plan(
            model, operation, T_build_from_source=T_build_from_source, cancelled=cancelled
        )
        plan = freeform_plan
        toolpath = generate_freeform_toolpath(freeform_plan, operation, cancelled=cancelled)
    trajectory = solve_xyzac_trajectory(
        toolpath,
        machine,
        tool_length_mm=nozzle.length_mm or 0.0,
        T_workpiece_from_build=T_workpiece_from_build,
        checkpoint=lambda: _checkpoint(cancelled),
    )
    _checkpoint(cancelled)
    transition_error: ValueError | None = None
    try:
        toolpath, trajectory = plan_machine_operation_transitions(
            toolpath, trajectory, machine, nozzle,
            safe_clearance_mm=(
                operation.solid_parameters.safe_clearance_mm
                if operation.solid_parameters is not None else 5.0
            ),
            T_workpiece_from_build=T_workpiece_from_build,
            checkpoint=lambda: _checkpoint(cancelled),
        )
    except ValueError as exc:
        transition_error = exc
    travel_error: ValueError | None = None
    if transition_error is None:
        try:
            toolpath, trajectory = plan_machine_non_deposition_travels(
                toolpath, trajectory, machine, nozzle,
                safe_clearance_mm=(
                    operation.solid_parameters.safe_clearance_mm
                    if operation.solid_parameters is not None else 5.0
                ),
                T_workpiece_from_build=T_workpiece_from_build,
                checkpoint=lambda: _checkpoint(cancelled),
            )
        except ValueError as exc:
            travel_error = exc
    service_plan: ToolChangeServicePlan | None = None
    service_error: ValueError | None = None
    if transition_error is None and travel_error is None:
        try:
            service_plan = plan_tool_change_service(
                toolpath, trajectory, machine, nozzle, controller,
                T_workpiece_from_build=T_workpiece_from_build,
                checkpoint=lambda: _checkpoint(cancelled),
            )
        except ValueError as exc:
            service_error = exc
    transition_tip_contacts = 0
    if service_error is None and transition_error is None and travel_error is None:
        try:
            _, transition_tip_contacts = check_operation_transition_safety(
                toolpath, trajectory, machine, nozzle,
                T_workpiece_from_build=T_workpiece_from_build,
                checkpoint=lambda: _checkpoint(cancelled),
            )
        except ValueError as exc:
            transition_error = exc
    travel_tip_contacts = 0
    if transition_error is None and travel_error is None:
        try:
            _, travel_tip_contacts = check_non_deposition_travel_safety(
                toolpath, trajectory, machine, nozzle,
                T_workpiece_from_build=T_workpiece_from_build,
                checkpoint=lambda: _checkpoint(cancelled),
            )
        except ValueError as exc:
            travel_error = exc
    validation = _validate(
        plan, toolpath, trajectory, operation, controller,
        service_plan=service_plan, service_error=service_error,
        transition_error=transition_error,
        travel_error=travel_error,
        transition_tip_contacts=transition_tip_contacts,
        travel_tip_contacts=travel_tip_contacts,
    )
    manifest = GeneratedResultManifest(
        f"{toolpath.toolpath_id}-result-v1",
        operation.operation_id,
        validation.status,
        FREEFORM_ALGORITHM_VERSION,
        operation.semantic_sha256(),
        (_source_fingerprint(model, source_path),),
        toolpath,
        machine.profile_id,
        datetime.now(timezone.utc).isoformat(),
        validation.ready_for_offline_export,
        tuple(item.code for item in validation.issues),
    )
    if not manifest.ready_for_export:
        return FreeformProductResult(
            plan,
            toolpath,
            trajectory,
            validation,
            manifest,
            "",
            OwnACReadbackReport(
                len(toolpath.points), 0, len(toolpath.events), 0, ("blocked",), False
            ),
            thermal_parameters,
        )
    motion_gcode = postprocess_own_ac(
        toolpath, trajectory, machine, nozzle, controller,
        checkpoint=lambda: _checkpoint(cancelled),
        service_plan=service_plan,
    )
    readback = readback_own_ac(
        motion_gcode, toolpath, trajectory, machine, nozzle, controller,
        checkpoint=lambda: _checkpoint(cancelled),
        service_plan=service_plan,
    )
    gcode = motion_gcode
    if thermal_parameters is not None:
        gcode = wrap_thermal_program(motion_gcode, thermal_parameters)
        recovered = unwrap_checked_thermal_program(gcode, thermal_parameters)
        if recovered != motion_gcode:
            raise ValueError("thermal wrapper changed the checked motion program")
        readback = readback_own_ac(
            recovered, toolpath, trajectory, machine, nozzle, controller,
            checkpoint=lambda: _checkpoint(cancelled),
            service_plan=service_plan,
        )
    if not readback.passed:
        manifest = replace(
            manifest,
            status=GeneratedResultStatus.ERROR,
            ready_for_export=False,
            issues=(*manifest.issues, "freeform.gcode_readback_failed"),
        )
    return FreeformProductResult(
        plan,
        toolpath,
        trajectory,
        validation,
        manifest,
        gcode,
        readback,
        thermal_parameters,
    )


def _validate(
    plan, toolpath, trajectory, operation, controller, *,
    service_plan=None, service_error=None, transition_error=None,
    travel_error=None, transition_tip_contacts=0, travel_tip_contacts=0,
):
    metrics = _validation_metrics(plan, trajectory, operation)
    c_values = [item.joint_positions.get("C", 0.0) for item in trajectory.samples]
    cumulative_c = sum(abs(right - left) for left, right in zip(c_values, c_values[1:]))
    issues = [*trajectory.issues, *_metric_issues(metrics)]
    if service_error is not None:
        if isinstance(service_error, ToolChangeCollisionError):
            issues.append(ValidationIssue(
                "tool_change.printed_part_collision", IssueSeverity.ERROR,
                object_id=service_error.point_id, context=service_error.context,
            ))
        elif str(service_error).startswith("tool_change."):
            code, _, object_id = str(service_error).partition(":")
            issues.append(ValidationIssue(code, IssueSeverity.ERROR, object_id=object_id))
        else:
            issues.append(ValidationIssue(
                "tool_change.service_planning_failed", IssueSeverity.ERROR,
                context={"reason": str(service_error)},
            ))
    if transition_error is not None:
        if isinstance(transition_error, OperationTransitionError):
            issues.append(ValidationIssue(
                transition_error.code, IssueSeverity.ERROR,
                object_id=transition_error.point_id,
                context=transition_error.context,
            ))
        elif isinstance(transition_error, ToolChangeCollisionError):
            issues.append(ValidationIssue(
                transition_error.code, IssueSeverity.ERROR,
                object_id=transition_error.point_id,
                context=transition_error.context,
            ))
        else:
            issues.append(ValidationIssue(
                "motion.transition_check_failed", IssueSeverity.ERROR,
                context={"reason": str(transition_error)},
            ))
    if travel_error is not None:
        if isinstance(travel_error, OperationTransitionError):
            issues.append(ValidationIssue(
                travel_error.code, IssueSeverity.ERROR,
                object_id=travel_error.point_id,
                context=travel_error.context,
            ))
        elif isinstance(travel_error, ToolChangeCollisionError):
            issues.append(ValidationIssue(
                travel_error.code, IssueSeverity.ERROR,
                object_id=travel_error.point_id,
                context=travel_error.context,
            ))
        else:
            issues.append(ValidationIssue(
                "motion.non_deposition_travel_check_failed", IssueSeverity.ERROR,
                context={"reason": str(travel_error)},
            ))
    if transition_tip_contacts or travel_tip_contacts:
        issues.append(ValidationIssue(
            "motion.intentional_tip_contact", IssueSeverity.WARNING,
            context={"allowed_contact_checks": transition_tip_contacts + travel_tip_contacts,
                     "offline_only": True},
        ))
    elif service_plan is not None and service_plan.moves_before_event:
        if not service_plan.nozzle_envelope_complete:
            issues.append(ValidationIssue(
                "tool_change.nozzle_envelope_incomplete", IssueSeverity.WARNING,
                context={"offline_only": True},
            ))
        issues.append(ValidationIssue(
            "tool_change.fixture_geometry_unverified", IssueSeverity.WARNING,
            context={"offline_only": True},
        ))
    issues.extend(
        ValidationIssue(code, IssueSeverity.WARNING, context={"offline_only": True})
        for code in controller.qualification_issues
    )
    cumulative_issue = _cumulative_c_issue(controller, cumulative_c)
    if cumulative_issue is not None:
        issues.append(cumulative_issue)
    qualification = _controller_qualification(controller, c_values, cumulative_c)
    if service_error is not None or transition_error is not None:
        qualification["machine_executable"] = False
    if service_plan is not None and service_plan.moves_before_event:
        qualification["service_checked_samples"] = service_plan.checked_samples
        qualification["service_nozzle_envelope_complete"] = service_plan.nozzle_envelope_complete
        qualification["machine_executable"] = False
    return FreeformValidationReport(
        f"{toolpath.toolpath_id}-validation-v1",
        tuple(issues),
        metrics,
        material_statistics(toolpath),
        qualification,
    )


def _validation_metrics(plan, trajectory, operation):
    if isinstance(plan, SolidFillPlan):
        return _solid_validation_metrics(plan, trajectory, operation)
    expected_paths = (
        len(operation.geometry.guides)
        * operation.parameters.path_count
        * operation.parameters.layer_count
    )
    path_count = len(plan.paths)
    max_normal_change = max(
        (
            math.acos(
                max(
                    -1.0,
                    min(1.0, sum(a * b for a, b in zip(left.surface_normal, right.surface_normal))),
                )
            )
            for path in plan.paths
            for left, right in zip(path.samples, path.samples[1:])
        ),
        default=0.0,
    )
    fk_position = max((item.fk_position_error_mm for item in trajectory.samples), default=0.0)
    fk_orientation = max(
        (item.fk_orientation_error_rad for item in trajectory.samples), default=0.0
    )
    return (
        ValidationMetric(
            "freeform_path_count",
            float(path_count),
            float(expected_paths),
            "count",
            path_count == expected_paths,
        ),
        ValidationMetric(
            "freeform_max_normal_change",
            max_normal_change,
            operation.parameters.maximum_normal_change_rad,
            "rad",
            max_normal_change <= operation.parameters.maximum_normal_change_rad + 1e-12,
        ),
        ValidationMetric(
            "freeform_fk_position_error", fk_position, 0.01, "mm", fk_position <= 0.01
        ),
        ValidationMetric(
            "freeform_fk_orientation_error",
            fk_orientation,
            math.radians(0.01),
            "rad",
            fk_orientation <= math.radians(0.01),
        ),
    )


def _solid_validation_metrics(plan, trajectory, operation):
    parameters = operation.solid_parameters
    if parameters is None:
        raise ValueError("solid-fill validation requires solid parameters")
    audit = plan.audit
    metrics = []

    def add(name, field, limit, unit="mm"):
        value = float(audit[field])
        metrics.append(ValidationMetric(name, value, float(limit), unit, value <= limit + 1e-12))

    if plan.operation_type == "spherical_solid_fill":
        add("solid_maximum_cross_path_spacing", "maximum_cross_path_spacing_mm", parameters.bead_width_mm)
        add("solid_relative_volume_error", "relative_volume_error", 0.10, "ratio")
        add("solid_first_layer_root_gap", "first_layer_root_gap_mm", parameters.bead_width_mm / 2 + 0.001)
    elif plan.operation_type == "surface_solid_fill":
        add("solid_maximum_cross_path_spacing", "maximum_cross_path_spacing_mm", parameters.path_spacing_mm)
        add("solid_maximum_segment_length", "maximum_segment_length_mm", parameters.sampling_step_mm)
        add("solid_relative_volume_error", "relative_volume_error", 0.10, "ratio")
        if operation.solid_geometry.substrate_body is not None:
            add("solid_root_edge_gap", "root_edge_max_gap_mm", 0.01)
    elif plan.operation_type == "radial_solid_fill":
        add("solid_maximum_radial_spacing", "maximum_radial_spacing_mm", parameters.layer_height_mm)
        add("solid_maximum_segment_length", "maximum_segment_length_mm", parameters.sampling_step_mm)
        add("solid_first_layer_hub_gap", "first_layer_hub_gap_max_mm", parameters.bead_width_mm / 2 + 0.001)
        add("solid_relative_material_volume_error", "relative_material_volume_error", 0.10, "ratio")
        add("solid_relative_section_volume_error", "relative_section_volume_error", 0.02, "ratio")
    else:  # pragma: no cover - guarded by SolidFillPlan
        raise ValueError(f"unsupported solid-fill operation: {plan.operation_type}")
    fk_position = max((item.fk_position_error_mm for item in trajectory.samples), default=0.0)
    fk_orientation = max(
        (item.fk_orientation_error_rad for item in trajectory.samples), default=0.0
    )
    metrics.extend(
        (
            ValidationMetric(
                "freeform_fk_position_error", fk_position, 0.01, "mm", fk_position <= 0.01
            ),
            ValidationMetric(
                "freeform_fk_orientation_error",
                fk_orientation,
                math.radians(0.01),
                "rad",
                fk_orientation <= math.radians(0.01),
            ),
        )
    )
    return tuple(metrics)


def _metric_issues(metrics):
    return tuple(
        ValidationIssue(
            f"freeform.metric.{item.name}",
            IssueSeverity.ERROR,
            context={"value": item.value, "limit": item.limit, "unit": item.unit},
        )
        for item in metrics
        if not item.passed
    )


def _cumulative_c_issue(controller, cumulative_c):
    if (
        controller.maximum_cumulative_c_rad is not None
        and cumulative_c > controller.maximum_cumulative_c_rad + 1.0e-12
    ):
        return ValidationIssue(
            "controller.cumulative_c_limit_exceeded",
            IssueSeverity.ERROR,
            context={
                "value_rad": cumulative_c,
                "limit_rad": controller.maximum_cumulative_c_rad,
            },
        )
    return None


def _controller_qualification(controller, c_values, cumulative_c):
    controller_qualification = controller.to_json()
    controller_qualification["cumulative_c_travel_rad"] = cumulative_c
    controller_qualification["cumulative_c_span_rad"] = (
        0.0 if not c_values else max(c_values) - min(c_values)
    )
    return controller_qualification


def state_from_freeform_result(operation, result):
    status = (
        result.manifest.status.value
        if isinstance(result.manifest.status, GeneratedResultStatus)
        else str(result.manifest.status)
    )
    return FreeformProductState(
        operation.operation_id, operation.semantic_sha256(), status, result.to_json()
    )


def export_freeform_product(
    result: FreeformProductResult, destination: str | Path, *, cancelled: CancelCheck | None = None
) -> Path:
    if not result.offline_exportable:
        raise ValueError("validation Error or failed readback blocks offline export")
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
        moved = False
        if target.exists():
            os.replace(target, backup)
            moved = True
        try:
            os.replace(stage, target)
        except Exception:
            if moved and backup.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return target
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _write_artifacts(directory, result):
    (directory / "main.gcode").write_text(result.gcode, encoding="utf-8", newline="\n")
    _write_json(directory / "toolpath.json", result.toolpath.to_json())
    _write_json(directory / "warnings.json", result.validation.to_json())
    _write_json(
        directory / "preview.json",
        {
            "coordinate_frame": result.toolpath.coordinate_frame,
            "segments": [
                segment.to_json()
                if hasattr(segment, "to_json")
                else {
                    "start": list(segment.start),
                    "end": list(segment.end),
                    "move_type": segment.move_type,
                    "extrusion_role": segment.extrusion_role,
                    "feedrate": segment.feedrate,
                    "delta_e": segment.delta_e,
                    "width": segment.width,
                    "height": segment.height,
                    "comment": segment.comment,
                }
                for segment in result.toolpath.to_preview_segments()
            ],
        },
    )
    _write_json(directory / "manifest.json", result.to_json())
    with (directory / "machine_axes.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "point_id",
                "time_s",
                "X_mm",
                "Y_mm",
                "Z_mm",
                "A_rad",
                "C_rad",
                "material_id",
                "channel_id",
            )
        )
        for point, sample in zip(result.toolpath.points, result.trajectory.samples, strict=True):
            axes = sample.joint_positions
            writer.writerow(
                (
                    point.point_id,
                    f"{sample.time_s:.9f}",
                    *(f"{axes.get(name, 0.0):.9f}" for name in ("X", "Y", "Z", "A", "C")),
                    point.material_id or "",
                    point.channel_id or "",
                )
            )


def _source_fingerprint(model, source_path):
    path = Path(source_path) if source_path is not None else None
    if path is not None and path.is_file():
        return SourceFingerprint(
            "cad_source", hashlib.sha256(path.read_bytes()).hexdigest(), "freeform_step", str(path)
        )
    digest = hashlib.sha256(
        json.dumps([item.to_json() for item in model.faces], sort_keys=True).encode()
    ).hexdigest()
    return SourceFingerprint("cad_model", digest, "freeform_step", "")


def _write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _checkpoint(cancelled):
    if cancelled is not None and cancelled():
        from .indexed_tube import GenerationCancelled

        raise GenerationCancelled("Freeform product generation cancelled")


__all__ = [
    "FREEFORM_ALGORITHM_VERSION",
    "FreeformProductResult",
    "FreeformProductState",
    "FreeformValidationReport",
    "export_freeform_product",
    "generate_freeform_product",
    "state_from_freeform_result",
]
