"""Generate Planar region previews and exportable path products."""

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

from ..algorithms.planar.region import PlanarSliceLayer, slice_planar_layers
from ..algorithms.planar.offset import inward_offsets_for_regions
from ..algorithms.planar.spiral import SpiralParameters, generate_spiral_toolpath
from ..algorithms.planar.support import SupportDiagnostic
from ..algorithms.planar.thin_wall import ThinWallParameters, thin_wall_pass_count
from ..algorithms.planar.zigzag import ZigzagParameters, generate_zigzag_toolpath
from ..kinematics.xyzac import MachineAxisTrajectory, solve_xyzac_trajectory
from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.machine import MachineProfile
from ..manufacturing.planar_parameters import (
    PlanarOperationDefinition,
    planar_operation_semantic_sha256,
)
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.setup import IssueSeverity, ValidationIssue
from ..manufacturing.toolpath import (
    GeneratedResultManifest,
    GeneratedResultStatus,
    GeneratedToolpath,
    SourceFingerprint,
    ToolpathPoint,
    ToolpathEvent,
)
from ..models import CadModel, Vector3
from ..validation.planar import PlanarToolpathMeasurement, measure_planar_toolpath
from ..validation.planar_qualification import (
    measurement_issues,
    solid_volume_issues,
    operation_geometry_issues as _independent_geometry_issues,
)
from .indexed_tube import GCodeReadbackReport, postprocess_indexed_gcode, readback_indexed_gcode
from .planar_support_product import build_planar_support_geometry

PLANAR_PRODUCT_STATE_SCHEMA_VERSION = 1
PLANAR_REGION_ALGORITHM_VERSION = "planar-region-product-v4"
PLANAR_ZIGZAG_ALGORITHM_VERSION = "planar-zigzag-product-v4"
PLANAR_PATH_ALGORITHM_VERSIONS = {
    "planar_offset": "planar-offset-product-v4",
    "planar_thin_wall": "planar-thin-wall-product-v4",
    "planar_spiral": "planar-spiral-product-v4",
    "planar_support": "planar-support-product-v4",
}
PLANAR_MARKERS = {
    "planar_zigzag": "P02",
    "planar_offset": "P03",
    "planar_thin_wall": "P04",
    "planar_spiral": "P05",
    "planar_support": "P07",
}


@dataclass(frozen=True, slots=True)
class PlanarRegionProductResult:
    operation_type: str
    layers: tuple[PlanarSliceLayer, ...]
    preview_toolpath: GeneratedToolpath
    manifest: GeneratedResultManifest

    @property
    def exportable(self) -> bool:
        return False

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": PLANAR_PRODUCT_STATE_SCHEMA_VERSION,
            "operation_type": self.operation_type,
            "manifest": self.manifest.to_json(),
            "layers": [_layer_json(layer) for layer in self.layers],
            "preview_only": True,
        }


@dataclass(frozen=True, slots=True)
class PlanarValidationReport:
    """P02 geometry, material, and machine-trajectory qualification."""

    measurement: PlanarToolpathMeasurement
    trajectory_id: str
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def status(self) -> GeneratedResultStatus:
        if any(issue.severity is IssueSeverity.ERROR for issue in self.issues):
            return GeneratedResultStatus.ERROR
        if self.issues:
            return GeneratedResultStatus.WARNING
        return GeneratedResultStatus.READY

    @property
    def ready_for_export(self) -> bool:
        return self.status in {GeneratedResultStatus.READY, GeneratedResultStatus.WARNING}

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "status": self.status.value,
            "ready_for_export": self.ready_for_export,
            "trajectory_id": self.trajectory_id,
            "measurement": {
                name: getattr(self.measurement, name)
                for name in self.measurement.__dataclass_fields__
            },
            "issues": [issue.to_json() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class PlanarZigzagProductResult:
    operation_type: str
    layers: tuple[PlanarSliceLayer, ...]
    toolpath: GeneratedToolpath
    trajectory: MachineAxisTrajectory
    validation: PlanarValidationReport
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
            "schema_version": PLANAR_PRODUCT_STATE_SCHEMA_VERSION,
            "operation_type": self.operation_type,
            "manifest": self.manifest.to_json(),
            "layers": [_layer_json(layer) for layer in self.layers],
            "machine_trajectory": self.trajectory.to_json(),
            "validation": self.validation.to_json(),
            "readback": self.readback.to_json(),
            "preview_only": False,
        }


@dataclass(frozen=True, slots=True)
class PlanarProductState:
    operation_id: str
    parameter_semantic_sha256: str
    status: str
    result_payload: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ready", "warning", "error", "stale", "draft"}:
            raise ValueError("unsupported Planar product state")
        if len(self.parameter_semantic_sha256) != 64:
            raise ValueError("parameter_semantic_sha256 must be a SHA-256 digest")

    def stale_for(self, operation: PlanarOperationDefinition) -> "PlanarProductState":
        digest = planar_operation_semantic_sha256(operation)
        return (
            self
            if digest == self.parameter_semantic_sha256
            else replace(self, parameter_semantic_sha256=digest, status="stale")
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": PLANAR_PRODUCT_STATE_SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "parameter_semantic_sha256": self.parameter_semantic_sha256,
            "status": self.status,
            "result": self.result_payload,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "PlanarProductState":
        if int(payload.get("schema_version", 0)) != PLANAR_PRODUCT_STATE_SCHEMA_VERSION:
            raise ValueError("unsupported Planar product state schema")
        result = payload.get("result")
        if result is not None and not isinstance(result, Mapping):
            raise ValueError("Planar product result must be an object or null")
        result_state = cls(
            str(payload["operation_id"]),
            str(payload["parameter_semantic_sha256"]),
            str(payload["status"]),
            result,
        )
        from ..planar_generation_context import invalidate_legacy_planar_state

        return invalidate_legacy_planar_state(result_state)


def generate_planar_region_product(
    model: CadModel,
    operation: PlanarOperationDefinition,
    T_model_from_build: RigidTransform,
    *,
    machine_profile_id: str = "unresolved-planar-preview",
    source_path: str | Path | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> PlanarRegionProductResult:
    if operation.operation_type != "planar_region":
        raise ValueError("P01 region product only accepts planar_region")
    body = operation.geometry.body
    if body is None:
        raise ValueError("Planar Region requires a selected body")
    parameters = operation.parameters
    layers = slice_planar_layers(
        model,
        (body.object_id,),
        first_layer_z_mm=parameters.first_layer_z_mm,
        layer_height_mm=parameters.layer_height_mm,
        last_layer_z_mm=parameters.last_layer_z_mm,
        T_model_from_build=T_model_from_build,
        cancelled=cancelled,
    )
    preview = _outline_preview(operation.operation_id, layers, parameters.feedrate_mm_min)
    digest = planar_operation_semantic_sha256(operation)
    manifest = GeneratedResultManifest(
        f"{preview.toolpath_id}-result-v1",
        operation.operation_id,
        GeneratedResultStatus.READY,
        PLANAR_REGION_ALGORITHM_VERSION,
        digest,
        (_source_fingerprint(model, source_path),),
        preview,
        machine_profile_id,
        datetime.now(timezone.utc).isoformat(),
        False,
        ("planar.region_preview_only",),
    )
    return PlanarRegionProductResult(operation.operation_type, layers, preview, manifest)


def generate_planar_zigzag_product(
    model: CadModel,
    operation: PlanarOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    T_model_from_build: RigidTransform,
    *,
    T_workpiece_from_build: RigidTransform | None = None,
    source_path: str | Path | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> PlanarZigzagProductResult:
    """Run section -> zigzag -> XYZAC -> validation -> post -> readback."""

    if operation.operation_type != "planar_zigzag":
        raise ValueError("P02 product only accepts planar_zigzag")
    if not operation.enabled or not operation.geometry.is_complete:
        raise ValueError("Planar Zigzag must be enabled and have a selected body")
    if not nozzle.is_ready:
        raise ValueError("selected Nozzle Profile is not ready")
    _checkpoint(cancelled)
    layers, toolpath = _zigzag_geometry(model, operation, T_model_from_build, cancelled)
    measurement = measure_planar_toolpath(
        toolpath, layers, layer_height_mm=operation.parameters.layer_height_mm
    )
    trajectory = solve_xyzac_trajectory(
        toolpath,
        machine,
        tool_length_mm=nozzle.length_mm or 0.0,
        T_workpiece_from_build=T_workpiece_from_build,
    )
    validation = _validate_zigzag(measurement, trajectory)
    validation = replace(
        validation,
        issues=(
            *validation.issues,
            *solid_volume_issues(measurement, layers, operation.parameters.layer_height_mm),
        ),
    )
    manifest = _zigzag_manifest(model, operation, machine, source_path, toolpath, validation)
    _checkpoint(cancelled)
    return _postprocess_zigzag(
        operation, layers, toolpath, trajectory, validation, manifest, machine, nozzle
    )


def generate_planar_path_product(
    model: CadModel,
    operation: PlanarOperationDefinition,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    T_model_from_build: RigidTransform,
    *,
    T_workpiece_from_build: RigidTransform | None = None,
    source_path: str | Path | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> PlanarZigzagProductResult:
    """Generate any exportable Planar path operation through one product chain."""

    if operation.operation_type == "planar_zigzag":
        return generate_planar_zigzag_product(
            model,
            operation,
            machine,
            nozzle,
            T_model_from_build,
            T_workpiece_from_build=T_workpiece_from_build,
            source_path=source_path,
            cancelled=cancelled,
        )
    if operation.operation_type not in PLANAR_PATH_ALGORITHM_VERSIONS:
        raise ValueError(f"unsupported Planar path operation: {operation.operation_type}")
    if not operation.enabled or not operation.geometry.is_complete:
        raise ValueError("Planar operation must be enabled and have a selected body")
    if not nozzle.is_ready:
        raise ValueError("selected Nozzle Profile is not ready")
    _checkpoint(cancelled)
    layers = _slice_operation_layers(model, operation, T_model_from_build, cancelled)
    toolpath, diagnostics, measurement_layers = _operation_toolpath(operation, layers, cancelled)
    measurement = measure_planar_toolpath(
        toolpath, measurement_layers, layer_height_mm=operation.parameters.layer_height_mm
    )
    trajectory = solve_xyzac_trajectory(
        toolpath,
        machine,
        tool_length_mm=nozzle.length_mm or 0.0,
        T_workpiece_from_build=T_workpiece_from_build,
    )
    validation = _validate_path_operation(
        operation.operation_type, measurement, trajectory, diagnostics
    )
    extra = _independent_geometry_issues(
        model, operation, T_model_from_build, toolpath, measurement, measurement_layers, cancelled
    )
    validation = replace(validation, issues=(*validation.issues, *extra))
    manifest = _path_manifest(model, operation, machine, source_path, toolpath, validation)
    _checkpoint(cancelled)
    return _postprocess_path(
        operation, layers, toolpath, trajectory, validation, manifest, machine, nozzle
    )


def _slice_operation_layers(model, operation, transform, cancelled):
    parameters = operation.parameters
    body = operation.geometry.body
    assert body is not None
    return slice_planar_layers(
        model,
        (body.object_id,),
        first_layer_z_mm=parameters.first_layer_z_mm,
        layer_height_mm=parameters.layer_height_mm,
        last_layer_z_mm=parameters.last_layer_z_mm,
        T_model_from_build=transform,
        cancelled=cancelled,
    )


def _operation_toolpath(operation, layers, cancelled):
    parameters = operation.parameters
    if operation.operation_type == "planar_offset":
        paths: list[tuple[PlanarSliceLayer, str, tuple[Vector3, ...], str]] = []
        diagnostics: list[str] = []
        for layer in layers:
            for region_id, result in inward_offsets_for_regions(
                layer.regions,
                parameters.line_spacing_mm,
                parameters.offset_pass_count,
                initial_offset_mm=parameters.bead_width_mm / 2.0,
            ):
                paths.extend((layer, region_id, contour, "infill") for contour in result.contours)
                diagnostics.extend(item.code for item in result.diagnostics)
        return _paths_toolpath(operation, paths), tuple(diagnostics), layers
    if operation.operation_type == "planar_thin_wall":
        paths = []
        diagnostics = []
        thin = ThinWallParameters(
            parameters.bead_width_mm,
            parameters.layer_height_mm,
            parameters.thin_wall_max_passes,
            insufficient_width_strategy="reduce",
        )
        if parameters.wall_thickness_mm < thin.bead_width_mm * thin.minimum_width_ratio:
            diagnostics.append("planar.thin_wall_width_reduced")
        passes = thin_wall_pass_count(parameters.wall_thickness_mm, thin)
        for layer in layers:
            for region in layer.regions:
                # A region boundary is the material edge, so the first bead
                # centre is half a bead inside it.  Further passes are one
                # bead apart.  The OCCT region offset also handles holes and
                # split islands without placing symmetric passes outside the
                # selected solid.
                result = inward_offsets_for_regions(
                    (region,),
                    parameters.bead_width_mm,
                    passes,
                    initial_offset_mm=parameters.bead_width_mm / 2.0,
                )[0][1]
                paths.extend(
                    (layer, region.region_id, contour, "thin_wall") for contour in result.contours
                )
                diagnostics.extend(item.code for item in result.diagnostics)
        return _paths_toolpath(operation, paths), tuple(diagnostics), layers
    if operation.operation_type == "planar_spiral":
        spiral = generate_spiral_toolpath(
            operation.operation_id,
            layers,
            SpiralParameters(
                parameters.bead_width_mm,
                parameters.layer_height_mm,
                parameters.spiral_samples_per_contour,
                parameters.feedrate_mm_min,
            ),
        )
        return spiral, (), layers
    if operation.operation_type == "planar_support":
        return build_planar_support_geometry(operation, layers, cancelled=cancelled)
    raise ValueError(f"unsupported Planar path operation: {operation.operation_type}")


def _paths_toolpath(
    operation: PlanarOperationDefinition,
    paths: list[tuple[PlanarSliceLayer, str, tuple[Vector3, ...], str]],
) -> GeneratedToolpath:
    points: list[ToolpathPoint] = []
    events: list[ToolpathEvent] = []
    for layer, region_id, path, role in paths:
        _append_planar_path(points, events, operation, layer, region_id, path, role)
    if not points:
        raise ValueError(f"{operation.operation_type} produced no printable path")
    return GeneratedToolpath(
        f"{operation.operation_id}-{operation.operation_type}-v1",
        operation.operation_id,
        points=tuple(points),
        events=tuple(events),
    )


def _append_planar_path(
    points: list[ToolpathPoint],
    events: list[ToolpathEvent],
    operation: PlanarOperationDefinition,
    layer: PlanarSliceLayer,
    region_id: str,
    path: tuple[Vector3, ...],
    role: str,
) -> None:
    if len(path) < 2:
        return
    _append_path_start(points, events, operation, layer, region_id, path)
    previous = path[0]
    for current in path[1:]:
        length = math.dist(previous, current)
        if length > 1.0e-9:
            points.append(
                _deposition_point(
                    len(points), operation, layer.layer_id, region_id, role, previous, current
                )
            )
        previous = current


def _append_path_start(points, events, operation, layer, region_id, path) -> None:
    parameters = operation.parameters
    if points:
        events.append(
            ToolpathEvent(
                f"event-{len(events) + 1:07d}",
                "retract",
                operation.operation_id,
                operation.operation_type,
                layer.layer_id,
                region_id,
                context={
                    "sequence_index": len(points),
                    "extrusion_length_mm": -parameters.retract_length_mm,
                },
            )
        )
    points.append(
        ToolpathPoint(
            f"point-{len(points) + 1:07d}",
            path[0],
            _unit_xy(path[0], path[1]),
            (0.0, 0.0, -1.0),
            operation.operation_id,
            operation.operation_type,
            layer.layer_id,
            region_id,
            "travel" if points else "approach",
            surface_normal=(0.0, 0.0, 1.0),
            feedrate_mm_min=parameters.travel_feedrate_mm_min,
        )
    )
    events.append(
        ToolpathEvent(
            f"event-{len(events) + 1:07d}",
            "prime",
            operation.operation_id,
            operation.operation_type,
            layer.layer_id,
            region_id,
            context={
                "sequence_index": len(points),
                "extrusion_length_mm": parameters.retract_length_mm,
            },
        )
    )


def _deposition_point(
    index: int,
    operation: PlanarOperationDefinition,
    layer_id: str,
    region_id: str,
    role: str,
    previous: Vector3,
    current: Vector3,
) -> ToolpathPoint:
    parameters = operation.parameters
    length = math.dist(previous, current)
    return ToolpathPoint(
        f"point-{index + 1:07d}",
        current,
        _unit_xy(previous, current),
        (0.0, 0.0, -1.0),
        operation.operation_id,
        operation.operation_type,
        layer_id,
        region_id,
        "deposition",
        extrusion_role=role,
        surface_normal=(0.0, 0.0, 1.0),
        feedrate_mm_min=parameters.feedrate_mm_min,
        bead_width_mm=parameters.bead_width_mm,
        layer_height_mm=parameters.layer_height_mm,
        material_volume_mm3=length * parameters.bead_width_mm * parameters.layer_height_mm,
    )


def _validate_path_operation(operation_type, measurement, trajectory, diagnostics):
    report = (
        _validate_spiral(measurement, trajectory)
        if operation_type == "planar_spiral"
        else (
            _validate_support(measurement, trajectory)
            if operation_type == "planar_support"
            else _validate_zigzag(measurement, trajectory)
        )
    )
    issues = list(report.issues)
    issues.extend(_algorithm_diagnostic_issues(diagnostics))
    return PlanarValidationReport(measurement, trajectory.trajectory_id, tuple(issues))


def _algorithm_diagnostic_issues(diagnostics):
    issues = []
    seen: set[tuple[str, str]] = set()
    for diagnostic in diagnostics:
        if isinstance(diagnostic, SupportDiagnostic):
            key = (diagnostic.code, diagnostic.layer_id)
            if key in seen:
                continue
            seen.add(key)
            severity = (
                IssueSeverity.ERROR
                if diagnostic.code == "planar.support_unreachable_from_buildplate"
                else IssueSeverity.WARNING
            )
            issues.append(
                ValidationIssue(
                    diagnostic.code,
                    severity,
                    object_id=diagnostic.layer_id,
                    context={
                        "source": "planar_algorithm",
                        "detail": diagnostic.detail,
                        "area_mm2": diagnostic.area_mm2,
                    },
                )
            )
            continue
        code = str(diagnostic)
        key = (code, "")
        if key not in seen:
            seen.add(key)
            issues.append(
                ValidationIssue(code, IssueSeverity.WARNING, context={"source": "planar_algorithm"})
            )
    return tuple(issues)


def _validate_support(measurement, trajectory):
    issues = (*_coalesce_trajectory_issues(trajectory.issues), *measurement_issues(measurement))
    return PlanarValidationReport(measurement, trajectory.trajectory_id, issues)


def _validate_spiral(measurement, trajectory):
    issues = (
        *_coalesce_trajectory_issues(trajectory.issues),
        *measurement_issues(measurement, planar=False),
    )
    return PlanarValidationReport(measurement, trajectory.trajectory_id, issues)


def _path_manifest(model, operation, machine, source_path, toolpath, validation):
    return GeneratedResultManifest(
        f"{toolpath.toolpath_id}-result-v1",
        operation.operation_id,
        validation.status,
        PLANAR_PATH_ALGORITHM_VERSIONS[operation.operation_type],
        planar_operation_semantic_sha256(operation),
        (_source_fingerprint(model, source_path),),
        toolpath,
        machine.profile_id,
        datetime.now(timezone.utc).isoformat(),
        validation.ready_for_export,
        tuple(issue.code for issue in validation.issues),
    )


def _postprocess_path(
    operation, layers, toolpath, trajectory, validation, manifest, machine, nozzle
):
    marker = PLANAR_MARKERS[operation.operation_type]
    if not manifest.ready_for_export:
        readback = GCodeReadbackReport(
            len(toolpath.points), 0, (), (), (), ("export_blocked_by_validation",)
        )
        return PlanarZigzagProductResult(
            operation.operation_type,
            layers,
            toolpath,
            trajectory,
            validation,
            manifest,
            "",
            readback,
        )
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
            issues=(*manifest.issues, "planar.gcode_readback_failed"),
        )
    return PlanarZigzagProductResult(
        operation.operation_type,
        layers,
        toolpath,
        trajectory,
        validation,
        manifest,
        gcode,
        readback,
    )


def _zigzag_geometry(model, operation, transform, cancelled):
    parameters = operation.parameters
    body = operation.geometry.body
    assert body is not None
    layers = slice_planar_layers(
        model,
        (body.object_id,),
        first_layer_z_mm=parameters.first_layer_z_mm,
        layer_height_mm=parameters.layer_height_mm,
        last_layer_z_mm=parameters.last_layer_z_mm,
        T_model_from_build=transform,
        cancelled=cancelled,
    )
    _checkpoint(cancelled)
    toolpath = generate_zigzag_toolpath(
        operation.operation_id,
        layers,
        ZigzagParameters(
            parameters.line_spacing_mm,
            parameters.bead_width_mm,
            parameters.layer_height_mm,
            parameters.feedrate_mm_min,
            parameters.travel_feedrate_mm_min,
            parameters.retract_length_mm,
        ),
    )
    return layers, toolpath


def _zigzag_manifest(model, operation, machine, source_path, toolpath, validation):
    return GeneratedResultManifest(
        f"{toolpath.toolpath_id}-result-v1",
        operation.operation_id,
        validation.status,
        PLANAR_ZIGZAG_ALGORITHM_VERSION,
        planar_operation_semantic_sha256(operation),
        (_source_fingerprint(model, source_path),),
        toolpath,
        machine.profile_id,
        datetime.now(timezone.utc).isoformat(),
        validation.ready_for_export,
        tuple(issue.code for issue in validation.issues),
    )


def _postprocess_zigzag(
    operation, layers, toolpath, trajectory, validation, manifest, machine, nozzle
):
    if not manifest.ready_for_export:
        readback = GCodeReadbackReport(
            len(toolpath.points), 0, (), (), (), ("export_blocked_by_validation",)
        )
        return PlanarZigzagProductResult(
            operation.operation_type,
            layers,
            toolpath,
            trajectory,
            validation,
            manifest,
            "",
            readback,
        )
    gcode = postprocess_indexed_gcode(
        toolpath,
        trajectory,
        machine,
        nozzle,
        header="5AxisSclicer P02 Planar Zigzag",
        marker_tag="P02",
    )
    readback = readback_indexed_gcode(
        gcode, toolpath, trajectory, machine, nozzle, marker_tag="P02"
    )
    if not readback.passed:
        manifest = replace(
            manifest,
            status=GeneratedResultStatus.ERROR,
            ready_for_export=False,
            issues=(*manifest.issues, "planar.gcode_readback_failed"),
        )
    return PlanarZigzagProductResult(
        operation.operation_type,
        layers,
        toolpath,
        trajectory,
        validation,
        manifest,
        gcode,
        readback,
    )


def export_planar_product(
    result: PlanarZigzagProductResult,
    destination: str | Path,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    """Publish the six P02 artefacts while preserving a previous directory on failure."""

    if not result.exportable:
        raise ValueError("validation Error or failed G-code readback blocks export")
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(mkdtemp(prefix=f".{target.name}.stage-", dir=target.parent))
    backup = target.with_name(f".{target.name}.previous")
    try:
        _checkpoint(cancelled)
        _write_planar_artifacts(stage, result)
        _checkpoint(cancelled)
        if backup.exists():
            shutil.rmtree(backup)
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


def state_from_region_result(
    operation: PlanarOperationDefinition,
    result: PlanarRegionProductResult | PlanarZigzagProductResult,
) -> PlanarProductState:
    status = result.manifest.status
    status_value = status.value if isinstance(status, GeneratedResultStatus) else str(status)
    return PlanarProductState(
        operation.operation_id,
        planar_operation_semantic_sha256(operation),
        status_value,
        result.to_json(),
    )


def _validate_zigzag(
    measurement: PlanarToolpathMeasurement,
    trajectory: MachineAxisTrajectory,
) -> PlanarValidationReport:
    issues = [*_coalesce_trajectory_issues(trajectory.issues), *measurement_issues(measurement)]
    if (
        measurement.sampled_region_area_mm2 > 0.0
        and measurement.residual_area_mm2 / measurement.sampled_region_area_mm2 > 0.1
    ):
        issues.append(
            ValidationIssue(
                "planar.coverage_residual_high",
                IssueSeverity.WARNING,
                context={
                    "residual_area_mm2": measurement.residual_area_mm2,
                    "sampled_region_area_mm2": measurement.sampled_region_area_mm2,
                },
            )
        )
    return PlanarValidationReport(measurement, trajectory.trajectory_id, tuple(issues))


def _coalesce_trajectory_issues(
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


def _outline_preview(
    operation_id: str, layers: tuple[PlanarSliceLayer, ...], feedrate_mm_min: float
) -> GeneratedToolpath:
    points: list[ToolpathPoint] = []
    for layer in layers:
        for region in layer.regions:
            for loop_index, loop in enumerate((region.outer, *region.holes)):
                for point_index, point in enumerate(loop):
                    following = loop[(point_index + 1) % len(loop)]
                    tangent = _unit_xy(point, following)
                    points.append(
                        ToolpathPoint(
                            f"point-{len(points) + 1:07d}",
                            point,
                            tangent,
                            (0.0, 0.0, -1.0),
                            operation_id,
                            "planar_region_preview",
                            layer.layer_id,
                            f"{region.region_id}-loop-{loop_index}",
                            "approach" if point_index == 0 else "travel",
                            extrusion_role="none",
                            surface_normal=(0.0, 0.0, 1.0),
                            feedrate_mm_min=feedrate_mm_min,
                        )
                    )
    return GeneratedToolpath(
        f"{operation_id}-region-preview-v1", operation_id, points=tuple(points)
    )


def _unit_xy(left: Vector3, right: Vector3) -> Vector3:
    dx, dy = right[0] - left[0], right[1] - left[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 1.0e-12:
        return (1.0, 0.0, 0.0)
    return (dx / length, dy / length, 0.0)


def _source_fingerprint(model: CadModel, source_path: str | Path | None) -> SourceFingerprint:
    path = Path(source_path) if source_path is not None else None
    if path is not None and path.is_file():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return SourceFingerprint("cad_source", digest, "planar_step", str(path))
    topology = {"bodies": [body.body_id for body in model.bodies]}
    digest = hashlib.sha256(json.dumps(topology, sort_keys=True).encode()).hexdigest()
    return SourceFingerprint("cad_model", digest, "planar_step", "")


def _layer_json(layer: PlanarSliceLayer) -> dict[str, Any]:
    return {
        "layer_id": layer.layer_id,
        "z_mm": layer.z_mm,
        "regions": [
            {
                "region_id": region.region_id,
                "outer": [list(point) for point in region.outer],
                "holes": [[list(point) for point in loop] for loop in region.holes],
            }
            for region in layer.regions
        ],
    }


def _write_planar_artifacts(directory: Path, result: PlanarZigzagProductResult) -> None:
    (directory / "main.gcode").write_text(result.gcode, encoding="utf-8", newline="\n")
    _write_json(directory / "toolpath.json", result.toolpath.to_json())
    _write_json(directory / "warnings.json", result.validation.to_json())
    _write_json(
        directory / "preview.json",
        {
            "coordinate_frame": result.toolpath.coordinate_frame,
            "segments": [
                {
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


def _checkpoint(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        from .indexed_tube import GenerationCancelled

        raise GenerationCancelled("Planar product generation cancelled")


__all__ = [
    "PlanarProductState",
    "PlanarRegionProductResult",
    "PlanarValidationReport",
    "PlanarZigzagProductResult",
    "export_planar_product",
    "generate_planar_path_product",
    "generate_planar_region_product",
    "generate_planar_zigzag_product",
    "state_from_region_result",
]
