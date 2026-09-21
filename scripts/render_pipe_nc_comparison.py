"""Compare verified cached legacy NC and newly read-back offline NC, in mm."""
import hashlib
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from render_fan15_examples import plot

ROOT = Path(__file__).resolve().parents[1]
old_folder = ROOT / "docs/reviews/evidence/2026-09-20_fan15_examples/pipe2"
parser = argparse.ArgumentParser()
parser.add_argument("--folder", default="pipe_offline_nc_20260921")
folder = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs" / parser.parse_args().folder
old_info = json.loads((old_folder / "legacy.json").read_text(encoding="utf-8"))
assert hashlib.sha256((ROOT / "example/pipe2/弯管.gcode").read_bytes()).hexdigest() == old_info["sha256"]
old = np.load(old_folder / "legacy.npz")["segments"]
data = np.load(folder / "nc_readback_paths.npz")
new, travel = data["segments"], data["travel"]
bounds = (np.minimum(old.min((0,1)), new.min((0,1))), np.maximum(old.max((0,1)), new.max((0,1))))
fig = plt.figure(figsize=(18,7), facecolor="white")
for n, segs, title, color in [(1,old,"OLD NC: reference reconstruction", "#256eb3"),
                             (2,new,"NEW NC: full base + 3 wall lanes", "#198d79"),
                             (3,travel,"NEW NC: non-deposition moves", "#bd652d")]:
    plot(fig.add_subplot(1,3,n,projection="3d"), segs, title, color, bounds)
fig.suptitle("Pipe2 | Actual NC paths | OFFLINE inspection, collision deferred", fontsize=16)
fig.text(.03,.025,"Legacy: zero-centre AC reference. New: same reference frame, 12.5 mm tool length removed. No CAD surface added.",fontsize=10)
fig.subplots_adjust(left=.01,right=.99,top=.83,bottom=.1,wspace=.02)
fig.savefig(folder / "nc_comparison.png",dpi=180)
plt.close(fig)
print(folder / "nc_comparison.png")
