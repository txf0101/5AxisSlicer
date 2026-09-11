"""T08 product flow for the constrained Tube Thin-Wall Indexed operation.

The module deliberately accepts domain objects rather than a Qt controller.  It
keeps geometry generation, XYZAC solving, validation, postprocessing and NC
readback separate, so UI/HTTP/script callers cannot accidentally use imported
NC as the source of a newly generated result.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
from tempfile import mkdtemp
from typing import Any, cast

from ..algorithms.tube.geometry import TubeFeature, recognise_tube
from ..algorithms.tube.indexed import (
    IndexedSlicePlan,
    generate_indexed_toolpath,
    plan_indexed_slices,
)
from ..kinematics.xyzac import MachineAxisTrajectory, solve_xyzac_trajectory
from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.machine import MachineProfile
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.setup import TubeOperationDefinition
from ..manufacturing.toolpath import (
    GeneratedResultManifest,
    GeneratedResultStatus,
    GeneratedToolpath,
    SourceFingerprint,
)
from ..models import CadModel
from ..validation.indexed_tube import CollisionBox, IndexedValidationReport, validate_indexed_tube

ALGORITHM_VERSION = "tube-indexed-product-v1"
PRODUCT_STATE_SCHEMA_VERSION = 1
CancelCheck = Callable[[], bool]


class GenerationCancelled(RuntimeError):
    """Raised before publication when the caller requests cancellation."""


@dataclass(frozen=True, slots=True)
class GCodeReadbackReport:
    """Evidence that this postprocessor's modal G-code still matches its input."""

    expected_points: int
    read_points: int
    coordinate_mismatches: tuple[str, ...]
    feedrate_mismatches: tuple[str, ...]
    extrusion_mismatches: tuple[str, ...]
    order_mismatches: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (
            self.coordinate_mismatches
            or self.feedrate_mismatches
            or self.extrusion_mismatches
            or self.order_mismatches
            or self.expected_points != self.read_points
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "passed": self.passed,
            "expected_points": self.expected_points,
            "read_points": self.read_points,
            "coordinate_mismatches": list(self.coordinate_mismatches),
            "feedrate_mismatches": list(self.feedrate_mismatches),
            "extrusion_mismatches": list(self.extrusion_mismatches),
            "order_mismatches": list(self.order_mismatches),
        }


@dataclass(frozen=True, slots=True)
class IndexedProductResult:
    """One successful (or warning-only) generated Tube Indexed result."""

    feature: TubeFeature
    plan: IndexedSlicePlan
    toolpath: GeneratedToolpath
    trajectory: MachineAxisTrajectory
    validation: IndexedValidationReport
    manifest: GeneratedResultManifest
    gcode: str
    readback: GCodeReadbackReport

    @property
    def exportable(self) -> bool:
        return self.manifest.ready_for_export and self.readback.passed

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": PRODUCT_STATE_SCHEMA_VERSION,
            "manifest": self.manifest.to_json(),
            "slice_plan": _plan_json(self.plan),
            "machine_trajectory": self.trajectory.to_json(),
            "validation": self.validation.to_json(),
            "readback": self.readback.to_json(),
        }


@dataclass(frozen=True, slots=True)
class IndexedProductState:
    """Persistable result ownership and stale state for a Tube operation.

    ``result_payload`` retains a last known good result while a changed
    operation is marked stale.  It is intentionally JSON data, which lets the
    project layer save/reopen it without serialising controller internals.
    """

    operation_id: str
    parameter_semantic_sha256: str
    status: str
    result_payload: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ready", "warning", "error", "stale", "draft"}:
            raise ValueError("unsupported product state")
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
    def from_json(cls, payload: Mapping[str, Any]) -> "IndexedProductState":
        if int(payload.get("schema_version", 0)) != PRODUCT_STATE_SCHEMA_VERSION:
            raise ValueError("unsupported indexed product state schema")
        result = payload.get("result")
        if result is not None and not isinstance(result, Mapping):
            raise ValueError("indexed product result must be an object or null")
        return cls(
            operation_id=str(payload["operation_id"]),
            parameter_semantic_sha256=str(payload["parameter_semantic_sha256"]),
            status=str(payload["status"]),
            result_payload=result,
        )

    def stale_for(self, operation: TubeOperationDefinition) -> "IndexedProductState":
        digest = operation_semantic_sha256(operation)
        if digest == self.parameter_semantic_sha256:
            return self
        return replace(self, parameter_semantic_sha256=digest, status="stale")


class TubeIndexedProductService:
    """Small stateful facade suitable for Generate/Cancel and project IO."""

    def __init__(self, state: IndexedProductState | None = None) -> None:
        self.state = state

    def mark_operation_changed(
        self, operation: TubeOperationDefinition
    ) -> IndexedProductState | None:
        if self.state is not None:
            self.state = self.state.stale_for(operation)
        return self.state

    def generate(
        self,
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
        cancelled: CancelCheck | None = None,
    ) -> IndexedProductResult:
        result = generate_indexed_product(
            model,
            operation,
            machine,
            nozzle,
            source_path=source_path,
            T_workpiece_from_build=T_workpiece_from_build,
            obstacles=obstacles,
            check_ipw=check_ipw,
            radial_error_limit_mm=radial_error_limit_mm,
            cancelled=cancelled,
        )
        self.state = IndexedProductState(
            operation.operation_id,
            operation_semantic_sha256(operation),
            cast(GeneratedResultStatus, result.manifest.status).value,
            result.to_json(),
        )
        return result


def generate_indexed_product(
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
    cancelled: CancelCheck | None = None,
) -> IndexedProductResult:
    """Run identify -> plan -> toolpath -> XYZAC -> validate -> post -> readback."""

    _checkpoint(cancelled)
    if not operation.enabled or not operation.geometry.is_complete:
        raise ValueError("Tube operation must be enabled and have complete geometry")
    feature, plan, toolpath = _generate_geometry(model, operation, cancelled)
    trajectory, validation = _solve_and_validate(
        feature,
        plan,
        toolpath,
        machine,
        nozzle,
        T_workpiece_from_build,
        obstacles,
        check_ipw,
        radial_error_limit_mm,
    )
    _checkpoint(cancelled)
    manifest = _manifest(model, source_path, operation, machine, toolpath, validation)
    if not manifest.ready_for_export:
        # A checked Error has a manifest but has no postprocessable artefact.
        return IndexedProductResult(
            feature,
            plan,
            toolpath,
            trajectory,
            validation,
            manifest,
            "",
            _blocked_readback(toolpath),
        )
    gcode = postprocess_indexed_gcode(toolpath, trajectory, machine, nozzle)
    readback = readback_indexed_gcode(gcode, toolpath, trajectory, machine)
    if not readback.passed:
        manifest = replace(
            manifest,
            status=GeneratedResultStatus.ERROR,
            ready_for_export=False,
            issues=(*manifest.issues, "tube.gcode_readback_failed"),
        )
    return IndexedProductResult(
        feature, plan, toolpath, trajectory, validation, manifest, gcode, readback
    )


def _generate_geometry(
    model: CadModel, operation: TubeOperationDefinition, cancelled: CancelCheck | None
) -> tuple[TubeFeature, IndexedSlicePlan, GeneratedToolpath]:
    feature = recognise_tube(model, operation.geometry)
    _checkpoint(cancelled)
    plan = plan_indexed_slices(feature, operation.parameters)
    toolpath = generate_indexed_toolpath(
        operation.operation_id, feature, plan, operation.parameters, model=model
    )
    _checkpoint(cancelled)
    return feature, plan, toolpath


def _solve_and_validate(
    feature: TubeFeature,
    plan: IndexedSlicePlan,
    toolpath: GeneratedToolpath,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    transform: RigidTransform | None,
    obstacles: tuple[CollisionBox, ...],
    check_ipw: bool,
    radial_limit: float,
) -> tuple[MachineAxisTrajectory, IndexedValidationReport]:
    trajectory = solve_xyzac_trajectory(
        toolpath,
        machine,
        tool_length_mm=nozzle.length_mm or 0.0,
        T_workpiece_from_build=transform,
    )
    validation = validate_indexed_tube(
        feature,
        plan,
        toolpath,
        trajectory,
        nozzle,
        obstacles=obstacles,
        radial_error_limit_mm=radial_limit,
        check_ipw=check_ipw,
    )
    return trajectory, validation


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
        algorithm_version=ALGORITHM_VERSION,
        parameter_semantic_sha256=operation_semantic_sha256(operation),
        input_sources=(_source_fingerprint(model, source_path),),
        toolpath=toolpath,
        machine_profile_id=machine.profile_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        ready_for_export=validation.ready_for_export,
        issues=tuple(issue.code for issue in validation.issues),
    )


def postprocess_indexed_gcode(
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
) -> str:
    """Emit conservative, absolute-position/absolute-extrusion Generic XYZAC NC."""

    if len(toolpath.points) != len(trajectory.samples):
        raise ValueError("toolpath and trajectory sample counts differ")
    filament_area = math.pi * (nozzle.filament_diameter_mm * 0.5) ** 2
    events_by_sequence: dict[int, list[Any]] = {}
    for event in toolpath.events:
        sequence = int(event.context.get("sequence_index", 0))
        events_by_sequence.setdefault(sequence, []).append(event)
    e_position = 0.0
    lines = [
        "; 5AxisSclicer T08 Tube Thin-Wall Indexed",
        "; reference XYZAC profile; offline simulation only",
        "G21 ; millimetres",
        "G90 ; absolute axes",
        "M82 ; absolute extrusion",
    ]
    for index, (point, sample) in enumerate(
        zip(toolpath.points, trajectory.samples, strict=True), start=1
    ):
        for event in events_by_sequence.get(index - 1, ()):
            delta = float(event.context.get("extrusion_length_mm", 0.0))
            if event.event_type in {"retract", "prime"}:
                e_position += delta
                lines.append(f"; T08 EVENT {event.event_id} {event.event_type}")
                lines.append(f"G1 E{e_position:.6f} F{point.feedrate_mm_min or 1.0:.3f}")
            else:
                lines.append(f"; T08 EVENT {event.event_id} {event.event_type}")
        axes = machine.controller_values(sample.joint_positions)
        if point.point_type == "deposition":
            e_position += point.material_volume_mm3 / filament_area
        words = " ".join(f"{axis}{value:.6f}" for axis, value in sorted(axes.items()))
        e_word = f" E{e_position:.6f}" if point.point_type == "deposition" else ""
        feed = point.feedrate_mm_min or 1.0
        lines.append(f"; T08 POINT {index} {point.point_id} {point.point_type}")
        lines.append(f"G1 {words}{e_word} F{feed:.3f}")
    lines.extend(("M400 ; finish queued motion", "M2"))
    return "\n".join(lines) + "\n"


def readback_indexed_gcode(
    gcode: str,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    *,
    tolerance: float = 1.0e-4,
) -> GCodeReadbackReport:
    """Read the restricted emitted dialect and compare order, axes, F and E state."""

    expected = list(zip(toolpath.points, trajectory.samples, strict=True))
    read = _read_marked_moves(gcode)
    coordinates: list[str] = []
    feeds: list[str] = []
    extrusion: list[str] = []
    ordering: list[str] = []
    previous_e = 0.0
    for index, (point, sample) in enumerate(expected):
        if index >= len(read):
            ordering.append(f"missing:{point.point_id}")
            continue
        point_id, point_type, words = read[index]
        _compare_order(index, point, point_id, point_type, ordering)
        _compare_motion(point, sample, words, machine, tolerance, coordinates, feeds)
        actual_e = _compare_extrusion(point, words, previous_e, tolerance, extrusion)
        previous_e = actual_e
    if len(read) > len(expected):
        ordering.append("unexpected_extra_points")
    return GCodeReadbackReport(
        len(expected),
        len(read),
        tuple(coordinates),
        tuple(feeds),
        tuple(extrusion),
        tuple(ordering),
    )


def _read_marked_moves(gcode: str) -> list[tuple[str, str, dict[str, float]]]:
    result: list[tuple[str, str, dict[str, float]]] = []
    marker: tuple[str, str] | None = None
    for line in (line.strip() for line in gcode.splitlines()):
        if line.startswith("; T08 POINT "):
            fields = line.split()
            marker = (fields[4], fields[5]) if len(fields) >= 6 else None
        elif marker is not None and line.startswith("G1 "):
            result.append((*marker, _words(line)))
            marker = None
    return result


def _compare_order(index: int, point: Any, read_id: str, read_type: str, issues: list[str]) -> None:
    if read_id != point.point_id or read_type != point.point_type:
        issues.append(f"{index + 1}:{read_id}!={point.point_id}")


def _compare_motion(
    point: Any,
    sample: Any,
    words: Mapping[str, float],
    machine: MachineProfile,
    tolerance: float,
    coordinates: list[str],
    feeds: list[str],
) -> None:
    for axis, value in machine.controller_values(sample.joint_positions).items():
        if axis not in words or abs(words[axis] - value) > tolerance:
            coordinates.append(f"{point.point_id}:{axis}")
    if "F" not in words or abs(words["F"] - (point.feedrate_mm_min or 1.0)) > tolerance:
        feeds.append(point.point_id)


def _compare_extrusion(
    point: Any,
    words: Mapping[str, float],
    previous_e: float,
    tolerance: float,
    issues: list[str],
) -> float:
    actual_e = words.get("E", previous_e)
    if point.point_type == "deposition" and actual_e <= previous_e + tolerance:
        issues.append(f"{point.point_id}:missing_deposition")
    elif (
        point.point_type != "deposition" and "E" in words and abs(actual_e - previous_e) > tolerance
    ):
        issues.append(f"{point.point_id}:extrusion_during_{point.point_type}")
    return actual_e


def export_indexed_product(
    result: IndexedProductResult,
    destination: str | Path,
    *,
    cancelled: CancelCheck | None = None,
) -> Path:
    """Stage all artefacts then replace the previous result directory as one unit.

    Cancellation is checked before the replacement point, so a prior result is
    preserved.  Windows cannot replace a non-empty directory in one syscall;
    the old directory is therefore renamed to a sibling backup and restored if
    publication fails.
    """

    if not result.exportable:
        raise ValueError("validation Error or failed G-code readback blocks export")
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(mkdtemp(prefix=f".{target.name}.stage-", dir=target.parent))
    backup = target.with_name(f".{target.name}.previous")
    try:
        _checkpoint(cancelled)
        _write_artifacts(stage, result)
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


def operation_semantic_sha256(operation: TubeOperationDefinition) -> str:
    payload = {
        "operation_id": operation.operation_id,
        "geometry": operation.geometry.to_json(),
        "parameters": operation.parameters.to_json(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_artifacts(directory: Path, result: IndexedProductResult) -> None:
    (directory / "main.gcode").write_text(result.gcode, encoding="utf-8", newline="\n")
    _write_json(directory / "toolpath.json", result.toolpath.to_json())
    _write_json(directory / "warnings.json", result.validation.to_json())
    _write_json(
        directory / "preview.json",
        {
            "coordinate_frame": result.toolpath.coordinate_frame,
            "segments": [_segment_json(item) for item in result.toolpath.to_preview_segments()],
        },
    )
    _write_json(directory / "manifest.json", result.to_json())
    with (directory / "machine_axes.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("point_id", "time_s", "X", "Y", "Z", "A", "C"))
        for sample in result.trajectory.samples:
            axes = sample.joint_positions
            writer.writerow(
                (
                    sample.source_point_id,
                    sample.time_s,
                    *(axes.get(name, "") for name in ("X", "Y", "Z", "A", "C")),
                )
            )


def _source_fingerprint(model: CadModel, source_path: str | Path | None) -> SourceFingerprint:
    path = Path(source_path) if source_path is not None else None
    if path is not None and path.is_file():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return SourceFingerprint("cad_source", digest, "tube_step", str(path))
    topology = {
        "bodies": [body.body_id for body in model.bodies],
        "edges": [edge.edge_id for edge in model.edges],
    }
    digest = hashlib.sha256(json.dumps(topology, sort_keys=True).encode()).hexdigest()
    return SourceFingerprint("cad_model", digest, "tube_step", "")


def _plan_json(plan: IndexedSlicePlan) -> dict[str, Any]:
    return {
        "regions": [
            {
                "region_id": item.region_id,
                "start_distance_mm": item.start_distance_mm,
                "end_distance_mm": item.end_distance_mm,
                "fixed_build_direction": list(item.fixed_build_direction),
                "maximum_direction_change_rad": item.maximum_direction_change_rad,
                "maximum_height_error_mm": item.maximum_height_error_mm,
                "source_face_id": item.source_face_id,
            }
            for item in plan.regions
        ],
        "layers": [
            {
                "layer_id": item.layer_id,
                "region_id": item.region_id,
                "centerline_distance_mm": item.centerline_distance_mm,
                "plane_origin": list(item.plane_origin),
                "plane_normal": list(item.plane_normal),
                "ownership": item.ownership,
            }
            for item in plan.layers
        ],
    }


def _segment_json(segment: Any) -> dict[str, Any]:
    return {
        "start": list(segment.start),
        "end": list(segment.end),
        "layer": segment.layer,
        "move_type": segment.move_type,
        "feedrate": segment.feedrate,
        "delta_e": segment.delta_e,
        "coordinate_transform": segment.coordinate_transform,
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _words(line: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for token in line.split()[1:]:
        if len(token) > 1 and token[0].isalpha():
            try:
                result[token[0].upper()] = float(token[1:])
            except ValueError:
                pass
    return result


def _checkpoint(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        raise GenerationCancelled("Tube Indexed generation cancelled before publication")


def _blocked_readback(toolpath: GeneratedToolpath) -> GCodeReadbackReport:
    return GCodeReadbackReport(
        len(toolpath.points), 0, (), (), (), ("export_blocked_by_validation",)
    )


__all__ = [
    "ALGORITHM_VERSION",
    "GCodeReadbackReport",
    "GenerationCancelled",
    "IndexedProductResult",
    "IndexedProductState",
    "TubeIndexedProductService",
    "export_indexed_product",
    "generate_indexed_product",
    "operation_semantic_sha256",
    "postprocess_indexed_gcode",
    "readback_indexed_gcode",
]
