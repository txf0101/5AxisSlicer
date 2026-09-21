"""Compare explicit legacy rotary hypotheses to CAD mesh, never rewrite old NC."""
import hashlib
import json
from pathlib import Path
import sys

import cadquery as cq
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from five_axis_slicer.step_loader import load_step

folder = ROOT / "docs/reviews/evidence/2026-09-20_fan15_examples/three_leaf"
info = json.loads((folder / "legacy.json").read_text(encoding="utf-8"))
source = ROOT / "example/三叶扇/EXAMPLE.gcode"
assert hashlib.sha256(source.read_bytes()).hexdigest() == info["sha256"]
data = np.load(folder / "legacy.npz")
mask = np.abs(data["ac"][:, 0]) > 1
xyz = data["segments"][mask, 1][::1000]
ab = data["ac"][mask][:, (0,2)][::1000]
model = load_step(ROOT / "example/三叶扇/Supportless_sample.stp")
mesh = []
for body in model.bodies:
    vertices, faces = cq.Shape.cast(model.shapes[body.body_id]).tessellate(0.03)
    mesh.extend(v.toTuple() for v in vertices)
mesh = np.asarray(mesh)
rows = []
clouds = {}
for tilt in ("X", "Y"):
    for sign_a in (-1,1):
        for sign_b in (-1,1):
            for offset in (0., -1.5):
                a, b = np.deg2rad(ab[:,0]*sign_a), np.deg2rad(ab[:,1]*sign_b)
                x,y,z = xyz.T.copy()
                z = z + offset
                if tilt == "X":
                    x1,y1,z1 = x, np.cos(a)*y + np.sin(a)*z, -np.sin(a)*y + np.cos(a)*z
                else:
                    x1,y1,z1 = np.cos(a)*x - np.sin(a)*z, y, np.sin(a)*x + np.cos(a)*z
                q = np.stack((np.cos(b)*x1 + np.sin(b)*y1,
                              -np.sin(b)*x1 + np.cos(b)*y1,z1),axis=1)
                clouds[(tilt, sign_a, sign_b, offset)] = q
                distance = np.asarray([np.sqrt(np.min(np.sum((mesh-p)**2, axis=1))) for p in q])
                rows.append({"tilt_axis": tilt, "a_sign": sign_a, "b_sign": sign_b,
                             "z_offset_mm": offset, "median_vertex_distance_mm": float(np.median(distance)),
                             "p95_vertex_distance_mm": float(np.percentile(distance,95)),
                             "bounds": [q.min(0).tolist(), q.max(0).tolist()]})
rows.sort(key=lambda row: row["median_vertex_distance_mm"])
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.gp import gp_Pnt
compound = cq.Compound.makeCompound([cq.Shape.cast(model.shapes[b.body_id]) for b in model.bodies]).wrapped
for tilt in ("X", "Y"):
    row = next(r for r in rows if r["tilt_axis"] == tilt)
    q = clouds[(tilt, row["a_sign"], row["b_sign"], row["z_offset_mm"])][::10]
    distances = []
    for point in q:
        measure = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex(), compound)
        measure.Perform()
        if not measure.IsDone():
            raise RuntimeError("CAD distance failed")
        distances.append(measure.Value())
    row["cad_probe_count"] = len(distances)
    row["cad_distance_median_mm"] = float(np.median(distances))
    row["cad_distance_p95_mm"] = float(np.percentile(distances,95))
out = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs/three_leaf_axis_hypotheses.json"
out.write_text(json.dumps({"source_sha256": info["sha256"], "cad_sha256": model.source_hash,
                          "scope": "sampled NC endpoints to mesh vertices; hypotheses only, not exact CAD distance or machine calibration",
                          "samples": len(xyz), "rows":rows},indent=2),encoding="utf-8")
print(json.dumps(rows[:4],indent=2))
