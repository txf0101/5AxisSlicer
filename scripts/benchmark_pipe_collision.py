"""Measure old/new broad phases on identical real pipe deposition samples."""

import gzip
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath
from five_axis_slicer.manufacturing.resources import NozzleProfile
from five_axis_slicer.validation import indexed_tube as validation


def main():
    root = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs"
    with gzip.open(
        root / "pipe2_cadbase_20260921/wall_toolpath.json.gz", "rt", encoding="utf-8"
    ) as stream:
        payload = json.load(stream)
    payload["points"] = payload["points"][:3000]
    payload["events"] = []
    path = GeneratedToolpath.from_json(payload)
    nozzle = NozzleProfile(
        resource_id="offline",
        display_name="offline",
        orifice_diameter_mm=0.4,
        filament_diameter_mm=1.75,
        interface="M6",
        length_mm=12.5,
        outer_profile_rz_mm=((0.2, 0), (3, 2), (3, 12.5)),
    )
    new = validation._DepositedSegmentIndex.near_candidates
    results = []
    reports = []
    for mode in ("old", "new"):
        if mode == "old":
            validation._DepositedSegmentIndex.near_candidates = (
                lambda self, center, radius, *, before: self.candidates(center, before=before)
            )
        else:
            validation._DepositedSegmentIndex.near_candidates = new
        start = time.perf_counter()
        report = validation._collision_issues(path, nozzle, (), 0.25, check_ipw=True)
        reports.append(report)
        results.append(
            {
                "mode": mode,
                "seconds": time.perf_counter() - start,
                "points": len(path.points),
                "issues": len(report[0]),
                "samples": report[1],
            }
        )
        print(results[-1], flush=True)
    assert reports[0] == reports[1]
    (root / "pipe_profile_20260921/collision_benchmark.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    benchmark_ik(path, root)


def benchmark_ik(path, root):
    from five_axis_slicer.kinematics import xyzac
    from five_axis_slicer.manufacturing.own_printer import own_ac_profile

    original = xyzac._cached_workpiece_transform
    machine = own_ac_profile()
    results, reports = [], []
    for mode in ("uncached", "cached"):
        if mode == "uncached":
            xyzac._cached_workpiece_transform = lambda profile, rotary, cache: original(
                profile, rotary, {}
            )
        else:
            xyzac._cached_workpiece_transform = original
        start = time.perf_counter()
        reports.append(xyzac.solve_xyzac_trajectory(path, machine, tool_length_mm=12.5))
        results.append(
            {"mode": mode, "seconds": time.perf_counter() - start, "points": len(path.points)}
        )
        print(results[-1], flush=True)
    assert reports[0] == reports[1]
    (root / "pipe_profile_20260921/ik_benchmark.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
