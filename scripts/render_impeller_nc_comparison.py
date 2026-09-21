"""Render actual old and strictly read-back new impeller NC paths."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection
import numpy as np
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[1]
OLD_FOLDER = ROOT / "docs/reviews/evidence/2026-09-20_fan15_examples/impeller"
FOLDER = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs" / "impeller_offline_nc_20260921"


def main() -> None:
    old = np.load(OLD_FOLDER / "legacy.npz")["segments"]
    data = np.load(FOLDER / "nc_readback_paths.npz")
    new = data["deposition"]
    skin = data["skin"]
    infill = data["infill"]
    old_blades = old[_blade_mask(old)]
    new_blades = new[_blade_mask(new)]
    skin_blades = skin[_blade_mask(skin)]
    infill_blades = infill[_blade_mask(infill)]

    shared_bounds = (
        np.minimum(old.min(axis=(0, 1)), new.min(axis=(0, 1))),
        np.maximum(old.max(axis=(0, 1)), new.max(axis=(0, 1))),
    )
    detail_bounds = (
        np.minimum(old_blades.min(axis=(0, 1)), new_blades.min(axis=(0, 1))),
        np.maximum(old_blades.max(axis=(0, 1)), new_blades.max(axis=(0, 1))),
    )
    fig = plt.figure(figsize=(18, 14), facecolor="white")
    _plot(
        fig.add_subplot(2, 2, 1, projection="3d"),
        old,
        "OLD NC: complete positive-E reconstruction",
        "#2865a8",
        shared_bounds,
    )
    _plot(
        fig.add_subplot(2, 2, 2, projection="3d"),
        new,
        "NEW NC: base + 8 solid conformal blades",
        "#15866f",
        shared_bounds,
    )
    _plot(
        fig.add_subplot(2, 2, 3, projection="3d"),
        old_blades,
        "OLD NC detail: blade region",
        "#e18a16",
        detail_bounds,
    )
    detail = fig.add_subplot(2, 2, 4, projection="3d")
    _plot(
        detail,
        new_blades,
        "NEW NC detail: supported root-to-tip solid layers",
        "#9d3b9f",
        detail_bounds,
    )
    _add(detail, skin_blades, "#c43d35", 0.46)
    _add(detail, infill_blades, "#f0a51b", 0.42)
    fig.suptitle(
        "Impeller | Actual NC paths | OFFLINE complete-stream readback accepted",
        fontsize=18,
    )
    fig.text(
        0.025,
        0.035,
        "New blade paths are reconstructed from emitted XYZAC NC. Red = finite-width skin; orange = internal solid fill. CAD surfaces are not drawn.",
        fontsize=10,
    )
    fig.text(
        0.025,
        0.016,
        "Each blade has five 0.2 mm thickness layers; every layer begins at the selected supported root. IPW collision remains user-deferred.",
        fontsize=10,
        color="#8a3c1f",
    )
    fig.subplots_adjust(left=0.01, right=0.99, top=0.91, bottom=0.07, wspace=0.02, hspace=0.12)
    output = FOLDER / "nc_comparison.png"
    fig.savefig(output, dpi=180)
    plt.close(fig)

    old_points = old_blades[:, 1][:: max(1, len(old_blades) // 100_000)]
    new_points = new_blades[:, 1][:: max(1, len(new_blades) // 100_000)]
    old_to_new = cKDTree(new_points).query(old_points)[0]
    new_to_old = cKDTree(old_points).query(new_points)[0]
    comparison = {
        "old_complete_positive_e_segments": len(old),
        "new_complete_deposition_segments": len(new),
        "blade_region_definition": "segment midpoint Z > 5 mm and XY radius > 17 mm",
        "old_blade_region_segments": len(old_blades),
        "new_blade_region_segments": len(new_blades),
        "new_blade_skin_segments": len(skin_blades),
        "new_blade_infill_segments": len(infill_blades),
        "endpoint_proximity_scope": "sampled endpoints only; old and new bead/layer strategies differ",
        "old_blade_to_new_blade_mm": _stats(old_to_new),
        "new_blade_to_old_blade_mm": _stats(new_to_old),
        "accepted_scope": "offline NC geometry and complete-stream readback",
        "physical_machine_qualified": False,
    }
    (FOLDER / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(output)


def _blade_mask(segments):
    midpoint = segments.mean(axis=1)
    radial = np.linalg.norm(midpoint[:, :2], axis=1)
    return (midpoint[:, 2] > 5.0) & (radial > 17.0)


def _plot(ax, segments, title, color, bounds):
    _add(ax, segments, color, 0.34)
    low, high = np.asarray(bounds)
    center = (low + high) / 2
    radius = max(high - low) / 2 * 1.05
    ax.set_xlim(center[0] - radius, center[0] + radius)
    ax.set_ylim(center[1] - radius, center[1] + radius)
    ax.set_zlim(center[2] - radius, center[2] + radius)
    ax.set_box_aspect((1, 1, 1))
    stride = max(1, math.ceil(len(segments) / 180_000))
    ax.set_title(f"{title}\n{len(segments):,} segments; display 1/{stride}", fontsize=10)
    ax.view_init(elev=27, azim=-55)
    ax.set_xlabel("X / mm")
    ax.set_ylabel("Y / mm")
    ax.set_zlabel("Z / mm")


def _add(ax, segments, color, width):
    stride = max(1, math.ceil(len(segments) / 180_000))
    if len(segments):
        ax.add_collection3d(
            Line3DCollection(segments[::stride], colors=color, linewidths=width, alpha=0.78)
        )


def _stats(values):
    return {
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "maximum": float(values.max()),
    }


if __name__ == "__main__":
    main()
