"""Record blocked pillar/roof support and a clear floating-roof control product."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.coordinates import GeometryReference, RigidTransform
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE
from five_axis_slicer.manufacturing.planar_parameters import (
    PlanarGeometrySelection,
    PlanarOperationDefinition,
    PlanarProcessParameters,
)
from five_axis_slicer.manufacturing.resources import NozzleProfile
from five_axis_slicer.postprocessing.planar_product import (
    export_planar_product,
    generate_planar_path_product,
)
from five_axis_slicer.step_loader import load_step


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _operation(body_id):
    return PlanarOperationDefinition(
        "support-motion-evidence",
        "setup-1",
        "Support motion evidence",
        "planar_support",
        geometry=PlanarGeometrySelection(GeometryReference(body_id, "body", {"schema_version": 1})),
        parameters=PlanarProcessParameters(
            first_layer_z_mm=0.5,
            layer_height_mm=0.5,
            last_layer_z_mm=3,
            bead_width_mm=0.6,
            feedrate_mm_min=100,
            travel_feedrate_mm_min=100,
            line_spacing_mm=0.6,
            support_xy_gap_mm=0.4,
            support_z_gap_mm=0,
            support_overhang_angle_deg=45,
            support_line_spacing_mm=1,
            support_interface_spacing_mm=0.6,
            support_interface_layers=2,
            support_pattern="grid",
        ),
    )


def _generate(shape, output):
    output.mkdir(parents=True, exist_ok=True)
    path = output / "model.step"
    cq.exporters.export(shape, str(path))
    model = load_step(path)
    assert len(model.bodies) == 1
    operation = _operation(model.bodies[0].body_id)
    machine = replace(
        GENERIC_XYZAC_REFERENCE,
        joints=tuple(
            replace(joint, soft_limit_min=-1000, soft_limit_max=1000)
            for joint in GENERIC_XYZAC_REFERENCE.joints
        ),
    )
    nozzle = NozzleProfile(
        "support-evidence-nozzle",
        "Support evidence nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2,
        outer_profile_rz_mm=((0.3, 0), (0.4, 2)),
    )
    result = generate_planar_path_product(
        model,
        operation,
        machine,
        nozzle,
        RigidTransform.identity("build"),
        T_workpiece_from_build=RigidTransform.from_translation(
            (250, 250, 250),
            source_frame="build",
            target_frame="workpiece",
        ),
        source_path=path,
    )
    (output / "toolpath_for_inspection.json").write_text(
        json.dumps(result.toolpath.to_json(), indent=2),
        encoding="utf-8",
    )
    record = {
        "model_path": str(path),
        "model_sha256": _hash(path),
        "operation": operation.to_json(),
        "point_count": len(result.toolpath.points),
        "exportable": result.exportable,
        "status": result.manifest.status.value,
        "gcode_characters": len(result.gcode),
        "readback": result.readback.to_json(),
        "measurement": asdict(result.validation.measurement),
        "issues": [issue.to_json() for issue in result.validation.issues],
    }
    return result, record


def _interior_interval(start, end, lower=(4, 2, 0), upper=(8, 8, 2.4)):
    # Independent slab intersection, with a 1 um inset to exclude mere contact.
    first, last = 0.0, 1.0
    for a, b, low, high in zip(start, end, lower, upper):
        low, high = low + 1e-6, high - 1e-6
        if abs(b - a) < 1e-12:
            if not low < a < high:
                return None
            continue
        left, right = sorted(((low - a) / (b - a), (high - a) / (b - a)))
        first, last = max(first, left), min(last, right)
        if first >= last:
            return None
    return [first, last]


def _blocked_case(output):
    pillar = cq.Workplane("XY").box(4, 6, 2.4).translate((6, 5, 1.2))
    roof = cq.Workplane("XY").box(12, 10, 1).translate((6, 5, 2.7))
    result, record = _generate(pillar.union(roof), output)
    hits = []
    for previous, current in zip(result.toolpath.points, result.toolpath.points[1:]):
        interval = _interior_interval(previous.position, current.position)
        if interval is not None:
            hits.append(
                {
                    "previous": previous.point_id,
                    "current": current.point_id,
                    "point_type": current.point_type,
                    "start_build_mm": previous.position,
                    "end_build_mm": current.position,
                    "interior_interval": interval,
                }
            )
    assert hits and all(hit["point_type"] == "travel" for hit in hits)
    assert not result.exportable and not result.gcode
    assert "planar.support_travel_intersects_target_cad" in result.manifest.issues
    try:
        export_planar_product(result, output / "must_not_export")
    except ValueError as error:
        record["export_rejection"] = str(error)
    else:
        raise RuntimeError("Target-intersecting support was incorrectly exported")
    assert not (output / "must_not_export").exists()
    record["independent_pillar_interior_intersections"] = hits
    record["independent_intersection_count"] = len(hits)
    return record


def _clear_case(output):
    result, record = _generate(cq.Workplane("XY").box(8, 6, 1).translate((8, 5, 2.7)), output)
    assert result.exportable and result.readback.passed
    assert "planar.support_joint_schedule_unverified" in result.manifest.issues
    product = export_planar_product(result, output / "product")
    record["artifacts_sha256"] = {_file.name: _hash(_file) for _file in product.iterdir()}
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", default="docs/reviews/evidence/2026-09-12_audit_fixes/support_motion"
    )
    output = Path(parser.parse_args().out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "qualification_boundary": "Target CAD is an exclusion domain; no printed-state or nozzle-sweep proof.",
        "pillar_roof": _blocked_case(output / "pillar_roof"),
        "floating_roof": _clear_case(output / "floating_roof"),
        "source_sha256": {
            str(ROOT / file): _hash(ROOT / file)
            for file in (
                "src/five_axis_slicer/validation/planar_travel.py",
                "src/five_axis_slicer/postprocessing/planar_product.py",
                "src/five_axis_slicer/algorithms/planar/support.py",
                "src/five_axis_slicer/algorithms/planar/zigzag.py",
                "scripts/planar_support_motion_evidence.py",
            )
        },
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                name: {key: summary[name][key] for key in ("status", "exportable", "point_count")}
                for name in ("pillar_roof", "floating_roof")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
