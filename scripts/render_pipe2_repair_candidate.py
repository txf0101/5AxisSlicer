"""Render real generated base/wall arrays alongside the untouched legacy path."""

from pathlib import Path
import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Line3DCollection
from render_fan15_examples import plot

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs/pipe2_candidate"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, default=FOLDER)
    folder = parser.parse_args().folder
    paths = np.load(folder / "paths.npz")
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    old = np.load(ROOT / "docs/reviews/evidence/2026-09-20_fan15_examples/pipe2/legacy.npz")[
        "segments"
    ]
    new = np.concatenate([paths["base"], paths["wall"]])
    bounds = (
        np.minimum(old.min(axis=(0, 1)), new.min(axis=(0, 1))),
        np.maximum(old.max(axis=(0, 1)), new.max(axis=(0, 1))),
    )
    fig = plt.figure(figsize=(16, 9), facecolor="white")
    plot(
        fig.add_subplot(121, projection="3d"),
        old,
        "OLD NC / AC inverse reference",
        "#2567ad",
        bounds,
    )
    ax = fig.add_subplot(122, projection="3d")
    plot(ax, new, "NEW CANDIDATE / full base + multipass wall", "#1c907d", bounds)
    ax.add_collection3d(Line3DCollection(paths["base"], colors="#d98628", linewidths=0.35))
    ratio = report["wall_volume_mm3"] / report["cad_wall_volume_mm3"]
    fig.suptitle("Pipe2 repair | actual deposition paths | NOT MACHINE QUALIFIED", fontsize=16)
    fig.text(
        0.04,
        0.08,
        f"{report['pass_count']} wall passes; {report['wall_layers']} wall layers; "
        f"{report['base_layers']} base layers. Wall commanded/CAD volume = {ratio:.4f}.",
    )
    fig.text(
        0.04,
        0.05,
        "All deposition segments shown. Travel hidden. Source/workpiece frame, mm. "
        "Base: 20% infill with skins. Orange: base; green: wall.",
    )
    fig.text(
        0.04,
        0.02,
        "Coverage, prior-material support, transitions and full machine validation remain open. No complete NC released.",
        color="#a32c25",
    )
    fig.subplots_adjust(top=0.85, bottom=0.13, left=0.01, right=0.99)
    fig.savefig(folder / "comparison_candidate.png", dpi=180)
    plt.close(fig)
    print(folder / "comparison_candidate.png")


if __name__ == "__main__":
    main()
