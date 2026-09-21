"""Run full shared CAD substrate generation for the remaining FAN15 examples."""
import gzip
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.algorithms.planar.substrate import generate_substrate_toolpath
from five_axis_slicer.algorithms.planar.feature_toolpath import FeatureToolpathParameters

parser = argparse.ArgumentParser()
parser.add_argument("--output", default="remaining_substrates_20260921")
OUT = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs" / parser.parse_args().output
OUT.mkdir(parents=True, exist_ok=True)
cases = {"logo": "球形NEU校徽/球形测试件.STEP", "impeller": "叶轮/叶轮.stp",
         "three_leaf": "三叶扇/Supportless_sample.stp"}
rows = []
for name, source in cases.items():
    print("START", name, flush=True)
    start = time.perf_counter()
    model = load_step(ROOT / "example" / source)
    row = {"case": name, "source_hash": model.source_hash,
           "scope": "body_001 substrate only; appendages and NC not included"}
    try:
        path = generate_substrate_toolpath(model, "body_001", name + "-base", FeatureToolpathParameters())
        with gzip.open(OUT / (name + "_base.json.gz"), "wt", encoding="utf-8") as stream:
            json.dump(path.to_json(), stream)
        row.update(passed=True, points=len(path.points), layers=len({p.layer_id for p in path.points}))
    except Exception as error:
        row.update(passed=False, error=str(error))
    row["seconds"] = time.perf_counter() - start
    rows.append(row)
    (OUT / "report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(row, ensure_ascii=False), flush=True)
