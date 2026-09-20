"""Render actual audit arrays; no cosmetic CAD projection or invented paths."""

import json
import math
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection
import numpy as np
from scipy.spatial import cKDTree

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs/reviews/evidence/2026-09-20_fan15_examples"
CASES = ("pipe2", "hemisphere_pattern", "three_leaf", "impeller")

TITLES = {
    "pipe2": "Bent pipe",
    "hemisphere_pattern": "Spherical NEU emblem",
    "three_leaf": "Three-leaf supportless sample",
    "impeller": "Impeller",
}


def plot(ax, segments, title, color, bounds=None):
    stride = max(1, math.ceil(len(segments) / 1200000))
    if len(segments):
        ax.add_collection3d(
            Line3DCollection(segments[::stride], colors=color, linewidths=0.32, alpha=0.8)
        )
        lo, hi = segments.min(axis=(0, 1)), segments.max(axis=(0, 1))
        if bounds is not None:
            lo, hi = np.asarray(bounds)
        center = (lo + hi) / 2
        radius = max(hi - lo) / 2 * 1.05
        ax.set_xlim(center[0] - radius, center[0] + radius)
        ax.set_ylim(center[1] - radius, center[1] + radius)
        ax.set_zlim(center[2] - radius, center[2] + radius)
        ax.set_box_aspect((1, 1, 1))
    ax.set_title(title + f"\n{len(segments):,} segments; display 1/{stride}", fontsize=10)
    ax.view_init(elev=25, azim=-58)
    ax.set_xlabel("X / mm")
    ax.set_ylabel("Y / mm")
    ax.set_zlabel("Z / mm")


def main(name):
    folder = OUT / name
    legacy_data = np.load(folder / "legacy.npz")
    legacy = legacy_data["segments"]
    old_info = json.loads((folder / "legacy.json").read_text(encoding="utf-8"))
    candidates = (
        ["new_indexed.npz", "new_continuous.npz"]
        if name == "pipe2"
        else ["new_freeform_0.2.npz", "new_freeform_3.0.npz"]
    )
    file = next((folder / f for f in candidates if (folder / f).exists()), None)
    current = np.load(file)["segments"] if file else np.empty((0, 2, 3))
    alternative = np.load(folder / "planar_diagnostic.npz")
    diagnostic = alternative["segments"]
    planar = json.loads((folder / "planar_diagnostic.json").read_text(encoding="utf-8"))
    if name == "hemisphere_pattern":
        # Registration documented by the original MATLAB model overlay.
        legacy = legacy * np.array([-1, -1, 1])
    metric = {
        "case": name,
        "accepted": False,
        "legacy_frame": old_info["frame"],
        "legacy_to_source_rz_deg": 180 if name == "hemisphere_pattern" else 0,
        "new_candidate_file": None if file is None else file.name,
        "planar_requested_layers": planar["requested_layers"],
        "planar_failed_layers": len(planar["failures"]),
        "metric_scope": "sampled endpoint proximity, not bead coverage or exact curve Hausdorff",
    }
    if len(current) and not old_info.get("unsupported_rotary_words"):
        old = legacy[:, 1][:: max(1, len(legacy) // 200000)]
        new = current[:, 1]
        for label, queries, reference in (("new_to_old", new, old), ("old_to_new", old, new)):
            d = cKDTree(reference).query(queries)[0]
            metric[label] = {
                "median_mm": float(np.median(d)),
                "p95_mm": float(np.percentile(d, 95)),
                "max_mm": float(d.max()),
            }
    fig = plt.figure(figsize=(19, 8), facecolor="white")
    fig.suptitle(TITLES[name] + " | FAN15 audit: NOT ACCEPTED", fontsize=18)
    ax = fig.add_subplot(131, projection="3d")
    plot(
        ax,
        legacy,
        "OLD NC: "
        + (
            "MACHINE XYZ ONLY (B unresolved)"
            if old_info.get("unsupported_rotary_words")
            else "AC inverse reference"
        ),
        "#2062a8",
    )
    if name == "hemisphere_pattern" and "custom" in legacy_data:
        marked = legacy[legacy_data["custom"]]
        ax.add_collection3d(Line3DCollection(marked, colors="#e18210", linewidths=0.55))
    bounds = (
        [legacy.min(axis=(0, 1)), legacy.max(axis=(0, 1))]
        if not old_info.get("unsupported_rotary_words")
        else None
    )
    ax = fig.add_subplot(132, projection="3d")
    if file:
        plot(ax, current, "CURRENT " + file.stem + "\nPARTIAL COVERAGE", "#c84e24", bounds)
    else:
        ax.text2D(
            0.12,
            0.5,
            "No complete five-axis generator\nfor this model",
            transform=ax.transAxes,
            color="#a32424",
        )
        ax.set_axis_off()
    ax = fig.add_subplot(133, projection="3d")
    plot(
        ax,
        diagnostic,
        f"PLANAR diagnostic: {planar['successful_layers']}/{planar['requested_layers']} height checks\nNO support/skin/NC qualification",
        "#259b76",
    )
    fig.text(
        0.02,
        0.045,
        "Actual generated/parsed segments only. Travel hidden. Planar diagnostic is not equivalent to conformal printing.",
        fontsize=11,
    )
    fig.text(
        0.02,
        0.018,
        "Unknown macros/axis mappings and failed layers remain unqualified; no machine-ready G-code is released.",
        fontsize=11,
        color="#a32424",
    )
    fig.subplots_adjust(left=0.01, right=0.99, top=0.85, bottom=0.1, wspace=0.05)
    output = folder / "comparison.png"
    fig.savefig(output, dpi=180)
    plt.close(fig)
    (folder / "comparison.json").write_text(json.dumps(metric, indent=2), encoding="utf-8")
    print(output, flush=True)


if __name__ == "__main__":
    for case in sys.argv[1:] or list(CASES):
        main(case)
