"""Locate the saved first collision diagnostic; does not qualify physical contact."""
import gzip
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Line3DCollection

root = Path(__file__).resolve().parents[1]
folder = root / "docs/reviews/evidence/2026-09-20_fan15_repairs/pipe_product_failfast_20260921"
with gzip.open(folder / "toolpath.json.gz", "rt", encoding="utf-8") as stream:
    points = json.load(stream)["points"]
report = json.loads((folder / "validation.json").read_text(encoding="utf-8"))
issue = next(i for i in report["issues"] if i["code"] == "tube.nozzle_ipw_collision")
index = next(i for i, p in enumerate(points) if p["point_id"] == issue["object_id"])
target = next(i for i, p in enumerate(points) if p["point_id"] == issue["context"]["target_id"])
xyz = np.array([p["position"] for p in points])
pairs = np.stack([xyz[:-1], xyz[1:]], axis=1)
deposit = np.array([p["point_type"] == "deposition" for p in points[1:]])
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
fig = plt.figure(figsize=(15, 8), facecolor="white")
ax = fig.add_subplot(121, projection="3d")
ax.add_collection3d(Line3DCollection(pairs[deposit], colors="#378d99", linewidths=.12, alpha=.32))
low, high = xyz.min(0), xyz.max(0)
ax.set(xlim=(low[0], high[0]), ylim=(low[1], high[1]), zlim=(low[2], high[2]))
ax.set_box_aspect(high-low)
ax.view_init(elev=22, azim=-65)
center = xyz[index-1:index+1].mean(0)
ax.scatter(*center, s=160, c="red", edgecolors="white", depthshade=False)
ax.text(*center, "  报警：底座第一层外圈", color="#b51c19", fontsize=11)
ax.set(title="整件真实沉积路径：红点是报警段", xlabel="X / mm", ylabel="Y / mm", zlabel="Z / mm")
ax = fig.add_subplot(122)
local = xyz[:9]
ax.plot(local[:, 0], local[:, 1], "o-", color="#a6b4bd", lw=2, label="首圈路径（局部）")
for end, color, label in [(target, "#2077ba", "已沉积段 P1 → P2"), (index, "#db332b", "报警运动段 P4 → P5")]:
    line = xyz[end-1:end+1]
    ax.plot(line[:, 0], line[:, 1], "o-", color=color, lw=6, label=label)
for i, p in enumerate(xyz[:5]):
    ax.annotate(f"P{i+1}", p[:2], xytext=(13, 2), textcoords="offset points", fontsize=12)
ax.set_aspect("equal")
ax.set(xlabel="X / mm", ylabel="Y / mm", title="俯视放大：同一首圈上的两段\n路径高度 Z = 0.1923 mm")
ax.grid(alpha=.2)
ax.legend(loc="lower right", fontsize=10)
fig.suptitle("弯管碰撞报警位置（来自保存的完整切片数据）", fontsize=18)
fig.text(.06, .055, "报警对象：喷嘴包络 vs 已沉积材料；尚未确认真实喷嘴发生接触。", fontsize=12, color="#ad2825")
fig.text(.06, .025, "当前报告只定位到运动段，未记录精确接触点；红点表示报警段位置，不是精确接触点。", fontsize=10)
fig.subplots_adjust(top=.87, bottom=.15, wspace=.25)
out = folder / "collision_location.png"
fig.savefig(out, dpi=180)
print(out)
