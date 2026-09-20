"""Generate reproducible FAN01-FAN05 evidence from the real fan inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from five_axis_slicer.algorithms.freeform.layer_domain import audit_blade_layer_domain
from five_axis_slicer.manufacturing.coordinates import GeometryReference, RigidTransform
from five_axis_slicer.manufacturing.fan_job import (
    FanGeometrySelection,
    FanJobOperation,
    FanManufacturingContract,
    FanManufacturingJob,
    FanProcessParameters,
    ParameterSource,
    SourcedValue,
)
from five_axis_slicer.step_loader import load_step

_AXIS_RE = re.compile(rb"(?:^|\s)([XYZACEF])(-?(?:\d+(?:\.\d*)?|\.\d+))")


def parse_gcode(path: Path) -> dict[str, object]:
    """Stream an independent lexical baseline without the product G-code parser."""

    digest = hashlib.sha256()
    line_count = motion_count = deposition_count = retract_count = layer_count = 0
    current_type = "unclassified"
    type_motion: Counter[str] = Counter()
    type_deposition: Counter[str] = Counter()
    bounds: dict[str, list[float]] = {}
    with path.open("rb") as stream:
        for raw in stream:
            digest.update(raw)
            line_count += 1
            stripped = raw.strip()
            if stripped.startswith(b";TYPE:"):
                current_type = stripped[6:].decode("utf-8", errors="replace") or "unclassified"
            if stripped == b";LAYER_CHANGE":
                layer_count += 1
            command = stripped.split(b";", 1)[0].strip()
            if not (command.startswith(b"G0 ") or command.startswith(b"G1 ")):
                continue
            motion_count += 1
            type_motion[current_type] += 1
            axes = {
                match.group(1).decode("ascii"): float(match.group(2))
                for match in _AXIS_RE.finditer(command)
            }
            for axis in "XYZAC":
                if axis in axes:
                    interval = bounds.setdefault(axis, [axes[axis], axes[axis]])
                    interval[0] = min(interval[0], axes[axis])
                    interval[1] = max(interval[1], axes[axis])
            if axes.get("E", 0.0) > 0.0:
                deposition_count += 1
                type_deposition[current_type] += 1
            elif axes.get("E", 0.0) < 0.0:
                retract_count += 1
    return {
        "path": str(path),
        "sha256": digest.hexdigest(),
        "size_bytes": path.stat().st_size,
        "line_count": line_count,
        "motion_count": motion_count,
        "deposition_move_count": deposition_count,
        "retract_move_count": retract_count,
        "layer_change_count": layer_count,
        "motion_by_type": dict(sorted(type_motion.items())),
        "deposition_by_type": dict(sorted(type_deposition.items())),
        "axis_word_bounds": bounds,
    }


def body_reference(body) -> GeometryReference:
    return GeometryReference(
        body.body_id,
        "body",
        {
            "geometry_sha256": body.signature,
            "volume_mm3": body.volume,
            "centroid_mm": list(body.centroid or ()),
        },
        assembly_name=body.name,
    )


def build_contract(model) -> FanManufacturingContract:
    blades = tuple(sorted(model.bodies[:3], key=lambda item: item.body_id))
    hub = model.bodies[3]
    sources = {
        "nozzle_diameter_mm": SourcedValue(0.4, ParameterSource.PAPER, "论文给定"),
        "filament_diameter_mm": SourcedValue(1.75, ParameterSource.PAPER, "论文给定"),
        "a_limit_deg": SourcedValue([-180.0, 180.0], ParameterSource.PAPER, "论文给定"),
        "c_limit_deg": SourcedValue([-360.0, 360.0], ParameterSource.PAPER, "论文给定"),
        "indexing_machine_z_mm": SourcedValue(20.0, ParameterSource.PAPER, "论文给定"),
        "material": SourcedValue("PLA", ParameterSource.USER, "用户指定"),
        "layer_height_mm": SourcedValue(0.2, ParameterSource.ENGINEERING_DEFAULT),
        "bead_width_mm": SourcedValue(0.4, ParameterSource.ENGINEERING_DEFAULT),
        "base_infill_fraction": SourcedValue(0.2, ParameterSource.ENGINEERING_DEFAULT),
        "blade_infill_fraction": SourcedValue(1.0, ParameterSource.ENGINEERING_DEFAULT),
        "nozzle_envelope": SourcedValue(None, ParameterSource.PENDING_MEASUREMENT, "实机资格门"),
        "machine_zero": SourcedValue(None, ParameterSource.PENDING_MEASUREMENT, "实机资格门"),
        "controller_macro_version": SourcedValue(
            None, ParameterSource.PENDING_MEASUREMENT, "实机资格门"
        ),
    }
    source_to_build = RigidTransform.from_rotation_translation(
        ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
        source_frame="source",
        target_frame="build",
    )
    return FanManufacturingContract(
        "fan-complete-reference-v1",
        model.source_hash,
        FanGeometrySelection(body_reference(hub), tuple(body_reference(item) for item in blades)),
        source_to_build,
        FanProcessParameters(),
        parameter_sources=sources,
    )


def build_job(contract: FanManufacturingContract) -> FanManufacturingJob:
    operations = (
        FanJobOperation("base", "planar_complete"),
        FanJobOperation("support", "support", ("base",)),
        FanJobOperation("index-a90", "indexed_reorientation", ("support",)),
        FanJobOperation("blade-1", "freeform_volume", ("index-a90",)),
        FanJobOperation("blade-2", "freeform_volume", ("blade-1",)),
        FanJobOperation("blade-3", "freeform_volume", ("blade-2",)),
        FanJobOperation("validation", "whole_job_validation", ("blade-3",)),
        FanJobOperation("program", "combined_postprocess", ("validation",)),
    )
    return FanManufacturingJob("fan-complete-reference-job", contract.semantic_sha256(), operations)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fan_dir = repo / "example" / "扇叶"
    model = load_step(fan_dir / "风扇扇叶(1).STEP")
    contract = build_contract(model)
    job = build_job(contract)
    audit = audit_blade_layer_domain(
        model,
        contract.geometry.blades[0].object_id,
        layer_height_mm=contract.parameters.layer_height_mm,
    )
    body_summary = [
        {
            "body_id": body.body_id,
            "signature": body.signature,
            "volume_mm3": body.volume,
            "surface_area_mm2": body.surface_area,
            "centroid_mm": body.centroid,
            "bounds_mm": None if body.bounds is None else body.bounds.to_json(),
            "role": "hub" if body.body_id == contract.geometry.hub.object_id else "blade",
        }
        for body in model.bodies
    ]
    layer_audit = {
        "body_id": audit.body_id,
        "a_angle_deg": audit.a_angle_deg,
        "build_z_range_mm": audit.build_z_range_mm,
        "layer_height_mm": audit.layer_height_mm,
        "layer_count": len(audit.layers),
        "nonempty_layer_count": audit.nonempty_layer_count,
        "internal_empty_layer_ids": audit.internal_empty_layer_ids,
        "section_volume_mm3": audit.section_volume_mm3,
        "cad_volume_mm3": audit.cad_volume_mm3,
        "relative_volume_error": audit.relative_volume_error,
        "max_sampling_area_change_fraction": audit.max_sampling_area_change_fraction,
        "endpoint_correction_limit_mm": audit.endpoint_correction_limit_mm,
        "jacobian_min": audit.jacobian_min,
        "self_intersection_count": audit.self_intersection_count,
        "fk_position_error_mm": audit.fk_position_error_mm,
        "fk_angle_error_deg": audit.fk_angle_error_deg,
        "fixed_a_within_limit": audit.fixed_a_within_limit,
        "geometry_feasible": audit.geometry_feasible,
        "machine_qualification_pending": audit.machine_qualification_pending,
    }
    baseline = {
        "step": {
            "path": str(model.source_path),
            "sha256": model.source_hash,
            "bounds_mm": None if model.bounds is None else model.bounds.to_json(),
            "bodies": body_summary,
        },
        "old_manual_program": parse_gcode(fan_dir / "风扇扇叶完整新.gcode"),
        "previous_software_program": parse_gcode(
            fan_dir / "风扇扇叶_本软件五轴_PLA_20260920.gcode"
        ),
        "coordinate_registration": {
            "source_to_build_rotation_deg_about_z": 180.0,
            "status": "frozen_offline_reference",
        },
    }
    files = {
        "fan_contract_v1.json": contract.to_json(),
        "fan_job_v1.json": job.to_json(),
        "fan_independent_baseline.json": baseline,
        "fan_blade_a90_layer_domain.json": layer_audit,
    }
    for name, payload in files.items():
        (output / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "output": str(output),
                "layer_audit": layer_audit,
                "gcode": {
                    key: baseline[key]
                    for key in ("old_manual_program", "previous_software_program")
                },
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
