"""Re-run the AUD-01 real-model defects without overwriting audit evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from xml.sax.saxutils import escape

import cadquery as cq

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.planar_controller import PlanarController
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.manufacturing.resources import GENERIC_PLA_175, ResourceSnapshot
from planar_p06_real_model_evidence import _nozzle, _parameters, _setup


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _projection(result, destination):
    """Source section and actual toolpath, with physical bead stroke width."""
    layers = result.layers
    layer_id = next(p.layer_id for p in result.toolpath.points if p.point_type == "deposition")
    layer = next(item for item in layers if item.layer_id == layer_id)
    all_points = [p for r in layer.regions for p in r.outer]
    lo = [min(p[i] for p in all_points) for i in range(2)]
    hi = [max(p[i] for p in all_points) for i in range(2)]
    width, height = max(1, hi[0] - lo[0]), max(1, hi[1] - lo[1])
    margin = max(width, height) * 0.06
    paths = []
    for previous, current in zip(result.toolpath.points, result.toolpath.points[1:]):
        if current.layer_id != layer_id:
            continue
        depositing = current.point_type == "deposition"
        color = "#1467ac" if depositing else "#b6bec7"
        stroke = current.bead_width_mm if depositing else max(width, height) / 800
        a, b = previous.position, current.position
        paths.append(
            f'<path d="M{a[0]},{-a[1]} L{b[0]},{-b[1]}" stroke="{color}" stroke-width="{stroke}" stroke-linecap="round"/>'
        )
    for region in layer.regions:
        for loop in (region.outer, *region.holes):
            points = " ".join(f"{p[0]},{-p[1]}" for p in loop)
            paths.append(
                f'<polyline points="{points}" fill="none" stroke="#b32222" stroke-width="{max(width, height) / 500}"/>'
            )
    title = escape(f"{destination.stem}: {layer_id}; blue=bead, grey=travel, red=CAD section")
    destination.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="700" viewBox="{lo[0] - margin} {-hi[1] - margin} {width + 2 * margin} {height + 2 * margin}"><title>{title}</title><rect x="{lo[0] - margin}" y="{-hi[1] - margin}" width="{width + 2 * margin}" height="{height + 2 * margin}" fill="white"/><g fill="none">'
        + "".join(paths)
        + "</g></svg>",
        encoding="utf-8",
    )


def _run_case(model, body, kind, first, last, output, *, height=0.6, bead=0.6, spacing=None):
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    setup = replace(
        _setup(model, body),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("aud-02-offline-pla")
        ),
        nozzle=ResourceSnapshot.capture(
            "nozzle",
            replace(
                _nozzle(), orifice_diameter_mm=bead, outer_profile_rz_mm=((bead / 2, 0), (0.4, 2))
            ),
        ),
    )
    controller = PlanarController(model, setup=setup)
    operation = controller.create_operation(kind, operation_id=f"audit-{output.name}")
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        body_id=body,
        parameters=replace(
            _parameters(first, last),
            layer_height_mm=height,
            bead_width_mm=bead,
            line_spacing_mm=bead if spacing is None else spacing,
        ),
    )
    record = {
        "operation": operation.to_json(),
        "source_sha256": model.source_hash,
        "setup": setup.to_json(),
        "scope": "offline software qualification; no machine trial",
    }
    try:
        result = controller.generate_operation(operation.operation_id)
        record.update(
            {
                "status": result.manifest.status.value,
                "exportable": result.exportable,
                "point_count": len(result.toolpath.points),
                "measurement": asdict(result.validation.measurement),
                "issues": [item.to_json() for item in result.validation.issues],
                "readback": result.readback.to_json(),
            }
        )
        lengths = {"deposition": 0.0, "travel": 0.0}
        for a, b in zip(result.toolpath.points, result.toolpath.points[1:]):
            lengths["deposition" if b.point_type == "deposition" else "travel"] += math.dist(
                a.position, b.position
            )
        record["length_mm"] = lengths
        record["travel_to_deposition_ratio"] = lengths["travel"] / max(lengths["deposition"], 1e-12)
        _write_json(output / "result.json", result.to_json())
        _write_json(output / "toolpath.json", result.toolpath.to_json())
        if result.exportable:
            controller.export_operation_product(operation.operation_id, str(output / "product"))
        else:
            try:
                controller.export_operation_product(
                    operation.operation_id, str(output / "rejected")
                )
            except ValueError as error:
                record["export_rejection"] = str(error)
        _projection(result, output / "path.svg")
    except Exception as error:
        record.update({"status": "error", "exportable": False, "error": str(error)})
    record["seconds"] = time.perf_counter() - started
    _write_json(output / "summary.json", record)
    print(
        json.dumps(
            {
                "case": output.name,
                **{k: record[k] for k in ("status", "exportable", "seconds")},
                "error": record.get("error"),
                "issues": [i["code"] for i in record.get("issues", [])],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", default="docs/reviews/evidence/2026-09-12_audit_fixes/planar_models"
    )
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rectangle = output / "rectangle.step"
    cq.exporters.export(cq.Workplane("XY").box(8, 6, 1).translate((4, 3, 0.5)), str(rectangle))
    records = {}
    model = load_step(rectangle)
    records["rectangle"] = _run_case(
        model, "body_001", "planar_zigzag", 0.5, 0.5, output / "rectangle", height=0.5
    )
    cases = (
        (
            "example/三叶扇/Supportless_sample.stp",
            (
                ("fan_local", "planar_zigzag", 60, 61.2),
                ("fan_full", "planar_zigzag", 56.3, 95.9),
                ("fan_spiral", "planar_spiral", 60, 60.6),
            ),
        ),
        ("example/pipe2/弯管新.stp", (("pipe_local", "planar_zigzag", 20, 21.2),)),
        ("example/叶轮/叶轮.stp", (("impeller_local", "planar_zigzag", 20, 21.2),)),
    )
    for path, model_cases in cases:
        model = load_step(Path(path).resolve())
        for name, kind, first, last in model_cases:
            records[name] = _run_case(model, "body_002", kind, first, last, output / name)
            _write_json(output / "summary.json", records)
    model = load_step(Path("example/pipe2/弯管新.stp").resolve())
    records["pipe_bead_04_sparse"] = _run_case(
        model,
        "body_002",
        "planar_zigzag",
        20,
        21.2,
        output / "pipe_bead_04_sparse",
        height=0.4,
        bead=0.4,
        spacing=0.5,
    )
    records["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    _write_json(output / "summary.json", records)


if __name__ == "__main__":
    main()
