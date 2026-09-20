"""Recheck a bounded set of historical failures without overwriting audit evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.step_loader import load_step
from five_axis_slicer.algorithms.planar.region import (
    _section_regions,
    PlanarSliceLayer,
)
from five_axis_slicer.algorithms.planar.feature_fill import FeatureFillParameters, plan_feature_fill
from five_axis_slicer.manufacturing.coordinates import RigidTransform

SOURCES = {
    "pipe2": "pipe2/弯管新.stp",
    "hemisphere_pattern": "球形NEU校徽/球形测试件.STEP",
    "impeller": "叶轮/叶轮.stp",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=SOURCES)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    history = ROOT / "docs/reviews/evidence/2026-09-20_fan15_examples" / args.case
    previous = json.loads((history / "planar_diagnostic.json").read_text(encoding="utf-8"))
    failed = previous["failures"]
    if not args.all:
        codes = set()
        selected = []
        for failure in failed:
            code = failure["error"].split(":")[0]
            if code not in codes:
                selected.append(failure)
                codes.add(code)
        failed = selected
    model = load_step(ROOT / "example" / SOURCES[args.case])
    started = time.perf_counter()
    bodies = [model.shapes[b.body_id] for b in model.bodies]
    records = []
    for failure in failed:
        z = failure["z_mm"]
        row = {"z_mm": z, "previous": failure["error"]}
        try:
            regions = _section_regions(
                bodies, z, 64, RigidTransform.identity("model"), 0.001, False
            )
            fill = plan_feature_fill(
                (PlanarSliceLayer("probe", z, regions),),
                FeatureFillParameters(top_solid_layers=0, bottom_solid_layers=0),
            )
            row.update(passed=True, regions=len(fill[0].regions))
        except Exception as error:
            row.update(passed=False, error=str(error))
        records.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "source_hash": model.source_hash,
                "seconds": time.perf_counter() - started,
                "scope": "historical failed-height geometry probes only; no manufacturing qualification",
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
