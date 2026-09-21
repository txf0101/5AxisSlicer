"""Package thermally wrapped offline NC and independently reconstruct its points."""
import gzip
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from five_axis_slicer.manufacturing.own_printer import own_ac_document
from five_axis_slicer.postprocessing.thermal_program import (
    ThermalProgramParameters, wrap_thermal_program, unwrap_checked_thermal_program,
)

parser = argparse.ArgumentParser()
parser.add_argument("--folder", default="pipe_offline_nc_20260921")
parser.add_argument("--suffix", default="20260921")
args = parser.parse_args()
folder = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs" / args.folder
motion = (folder / "offline_diagnostic.gcode").read_text(encoding="utf-8")
scope = json.loads((folder / "inspection_scope.json").read_text(encoding="utf-8"))
assert scope["readback"]["passed"]
pla = next(m for m in own_ac_document()["process_reference"]["materials"] if m["material"] == "PLA")
thermal = ThermalProgramParameters(pla["nozzle_c"], pla["standalone_bed_c"])
code = wrap_thermal_program(motion, thermal)
assert unwrap_checked_thermal_program(code, thermal) == motion
# The selected offline fixture has zero centres/offsets, +X A / +Z C and a
# 12.5 mm tool length. This independent expression is not general machine IK.
reconstructed = []
pending = False
for line in code.splitlines():
    if line.startswith("; T08 POINT "):
        pending = True
    elif pending and line.startswith("G1 "):
        values = {k: float(v) for k, v in re.findall(r"([XYZAC])([-+0-9.]+)", line)}
        x, y, z = values["X"], values["Y"], values["Z"] - 12.5
        a, c = math.radians(values["A"]), math.radians(values["C"])
        v = math.cos(a) * y + math.sin(a) * z
        reconstructed.append((math.cos(c)*x + math.sin(c)*v,
                              -math.sin(c)*x + math.cos(c)*v,
                              -math.sin(a)*y + math.cos(a)*z))
        pending = False
with gzip.open(folder / "toolpath.json.gz", "rt", encoding="utf-8") as stream:
    path = json.load(stream)
expected = np.asarray([p["position"] for p in path["points"]])
actual = np.asarray(reconstructed)
assert actual.shape == expected.shape
errors = np.linalg.norm(actual - expected, axis=1)
assert errors.max() < 1e-4
pairs = np.stack((actual[:-1], actual[1:]), axis=1)
deposit = np.asarray([p["point_type"] == "deposition" for p in path["points"][1:]])
np.savez_compressed(folder / "nc_readback_paths.npz", segments=pairs[deposit], travel=pairs[~deposit])
target = ROOT / "example/pipe2" / ("弯管_新算法_离线检查_" + args.suffix + ".gcode")
if target.exists() and target.read_text(encoding="utf-8") != code:
    raise RuntimeError("Refusing to overwrite a different existing NC")
target.write_text(code, encoding="utf-8")
report = {
    **scope,
    "output": str(target),
    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    "motion_sha256": hashlib.sha256((folder / "offline_diagnostic.gcode").read_bytes()).hexdigest(),
    "thermal_wrapper_checked": True,
    "thermal_motion_unchanged": True,
    "pla_nozzle_c": thermal.nozzle_c, "pla_bed_c": thermal.bed_c,
    "thermal_source": "bundled own_ac_fdm.json process_reference (paper extraction)",
    "independent_inverse_max_error_mm": float(errors.max()),
    "points": len(actual), "deposition_segments": int(deposit.sum()),
    "travel_segments": int((~deposit).sum()),
    "still_pending": ["IPW collision", "physical machine calibration", "axis dynamic limits", "local bead support/coverage", "native GUI full product export"],
}
(folder / "delivery.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
