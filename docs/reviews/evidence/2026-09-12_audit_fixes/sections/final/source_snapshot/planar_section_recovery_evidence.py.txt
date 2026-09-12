"""Record full-height Planar section recovery and explicit geometric rejections."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.algorithms.planar.region import PlanarSectionError, slice_planar_layers
from five_axis_slicer.algorithms.planar.section_loops import MAX_ENDPOINT_CORRECTION_MM
from five_axis_slicer.step_loader import load_step


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_layer(layer):
    areas = []
    for region in layer.regions:
        face = cq.Face.makeFromWires(
            cq.Wire.makePolygon(region.outer[:-1], close=True),
            [cq.Wire.makePolygon(hole[:-1], close=True) for hole in region.holes],
        )
        if not face.isValid() or face.Area() <= 0:
            raise RuntimeError(
                f"Recovered region is not a valid positive-area face: {layer.layer_id}"
            )
        areas.append(face.Area())
    return {"z_mm": layer.z_mm, "region_count": len(layer.regions), "areas_mm2": areas}


def _case(name, relative_model, first_z, output, *, fail_on_rejection):
    path = ROOT / relative_model
    model = load_step(path)
    started = time.perf_counter()
    records = []
    recovered = []
    if fail_on_rejection:
        layers = slice_planar_layers(
            model,
            ("body_002",),
            first_layer_z_mm=first_z,
            last_layer_z_mm=first_z + 66 * 0.6,
            layer_height_mm=0.6,
        )
        records.extend(_check_layer(layer) for layer in layers)
        recovered.extend(asdict(layer) for layer in layers)
    else:
        for index in range(67):
            z_mm = first_z + index * 0.6
            try:
                layer = slice_planar_layers(
                    model,
                    ("body_002",),
                    first_layer_z_mm=z_mm,
                    last_layer_z_mm=z_mm,
                    layer_height_mm=0.6,
                )[0]
            except PlanarSectionError as error:
                records.append({"z_mm": z_mm, "error_code": error.code, "detail": error.detail})
                continue
            records.append(_check_layer(layer))
            recovered.append(asdict(layer))
    layers_path = output / f"{name}_accepted_layers.json"
    layers_path.write_text(json.dumps(recovered, ensure_ascii=False), encoding="utf-8")
    return {
        "model": str(path),
        "model_sha256": _sha256(path),
        "body": "body_002",
        "first_z_mm": first_z,
        "last_z_mm": first_z + 66 * 0.6,
        "layer_height_mm": 0.6,
        "sample_segments_per_edge": 64,
        "requested_layer_count": 67,
        "accepted_layer_count": len(recovered),
        "rejected_layer_count": 67 - len(recovered),
        "records": records,
        "elapsed_seconds": time.perf_counter() - started,
        "layers_artifact": str(layers_path),
        "layers_sha256": _sha256(layers_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="docs/reviews/evidence/2026-09-12_audit_fixes/sections",
    )
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "max_endpoint_correction_mm": MAX_ENDPOINT_CORRECTION_MM,
        "boundary": "Shared vertices only; no proximity healing or relaxed kernel tolerances.",
        "fan": _case(
            "fan", "example/三叶扇/Supportless_sample.stp", 56.3, output, fail_on_rejection=True
        ),
        "impeller": _case(
            "impeller", "example/叶轮/叶轮.stp", 2.6, output, fail_on_rejection=False
        ),
        "source_sha256": {
            str(path): _sha256(path)
            for path in (
                Path(__file__).resolve(),
                ROOT / "src/five_axis_slicer/algorithms/planar/region.py",
                ROOT / "src/five_axis_slicer/algorithms/planar/section_loops.py",
                ROOT / "src/five_axis_slicer/step_topology.py",
                ROOT / "tests/test_planar_section_loops.py",
            )
        },
    }
    (output / "full_height_sections.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                name: {
                    key: summary[name][key]
                    for key in ("accepted_layer_count", "rejected_layer_count")
                }
                for name in ("fan", "impeller")
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
