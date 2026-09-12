"""Render measured old/new deposition paths as standalone engineering figures."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from mpl_toolkits.mplot3d.art3d import Line3DCollection
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/reviews/evidence/2026-09-12_audit_fixes"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _segments(path):
    points = _read(path)["points"]
    deposited, travel = [], []
    for a, b in zip(points, points[1:]):
        (deposited if b["point_type"] == "deposition" else travel).append((a["position"], b["position"]))
    return np.asarray(deposited), np.asarray(travel)


def main():
    output = EVIDENCE / "figures"
    output.mkdir(exist_ok=True)
    old = ROOT / "docs/reviews/evidence/2026-09-12_project_audit/frozen_cases/analytic/product/toolpath.json"
    new = EVIDENCE / "planar_models_final/rectangle/toolpath.json"
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), constrained_layout=True)
    for ax, path, title in zip(axes, (old, new), ("Before: 32.4 mm³ (+35%)", "After: 24.0 mm³ (target: 24.0)")):
        ax.set(xlim=(-.6,8.6),ylim=(-.6,6.6),xlabel="Build X (mm)",ylabel="Build Y (mm)",title=title)
        ax.set_aspect("equal")
        ax.grid(color="#e0e4e9",zorder=0)
    fig.canvas.draw()
    for ax, path in zip(axes,(old,new)):
        dep,travel = _segments(path)
        scale=ax.get_window_extent().width/9.2*72/fig.dpi
        ax.add_collection(LineCollection(dep[:,:,:2],colors="#2475af",linewidths=.6*scale,capstyle="round",zorder=2))
        ax.add_collection(LineCollection(travel[:,:,:2],colors="#89929e",linewidths=.65,zorder=3))
        ax.plot((0,8,8,0,0),(0,0,6,6,0),color="#be2a29",lw=1.2,zorder=4)
    axes[0].legend(handles=[Line2D([],[],color="#2475af",lw=5,label="0.6 mm bead envelope"),Line2D([],[],color="#be2a29",label="CAD boundary"),Line2D([],[],color="#89929e",label="Travel")],loc="upper center",fontsize=8)
    fig.savefig(output/"rectangle_before_after.png",dpi=180)
    plt.close(fig)
    path=EVIDENCE/"fan_full_sparse/toolpath.json"
    if path.exists():
        dep,travel=_segments(path)
        fig=plt.figure(figsize=(8,7),layout="constrained")
        ax=fig.add_subplot(projection="3d")
        ax.add_collection3d(Line3DCollection(dep,colors="#2475af",linewidths=.45))
        ax.add_collection3d(Line3DCollection(travel,colors="#99a3ae",linewidths=.2,alpha=.4))
        values=np.concatenate((dep.reshape(-1,3),travel.reshape(-1,3)))
        ax.auto_scale_xyz(values[:,0],values[:,1],values[:,2])
        ax.set(xlabel="Build X (mm)",ylabel="Build Y (mm)",zlabel="Build Z (mm)",title="Three-blade fan, body_002: 67 layers, sparse fill\nBead 0.60 mm / spacing 0.65 mm; deposition blue, travel grey")
        fig.savefig(output/"fan_full_toolpath.png",dpi=180)
        plt.close(fig)


if __name__=="__main__":
    main()
