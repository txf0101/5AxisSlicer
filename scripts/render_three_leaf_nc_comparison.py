"""Render legacy-axis-hypothesis and actual new three-leaf NC paths."""

from __future__ import annotations

from collections import Counter
import gzip
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
OLD_FOLDER = ROOT / "docs/reviews/evidence/2026-09-20_fan15_examples/three_leaf"
FOLDER = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs" / "three_leaf_offline_nc_20260921"
BASE_PATH = (
    ROOT
    / "docs/reviews/evidence/2026-09-20_fan15_repairs"
    / "remaining_substrates_midpoint_20260921/three_leaf_base.json.gz"
)


def main() -> None:
    legacy = np.load(OLD_FOLDER / "legacy.npz")
    old = _legacy_y_tilt_hypothesis(legacy["segments"], legacy["ac"])
    data = np.load(FOLDER / "nc_readback_paths.npz")
    new = data["deposition"]
    with gzip.open(BASE_PATH, "rt", encoding="utf-8") as stream:
        base = json.load(stream)
    base_roles = Counter(
        point["extrusion_role"] for point in base["points"] if point["point_type"] == "deposition"
    )
    base_deposition = sum(base_roles.values())
    feature = new[base_deposition:]
    skin = data["skin"][base_roles["skin"] :]
    infill = data["infill"][base_roles["infill"] :]
    old_root = old[_root_detail_mask(old)]
    feature_root = feature[_root_detail_mask(feature)]
    skin_root = skin[_root_detail_mask(skin)]
    infill_root = infill[_root_detail_mask(infill)]

    shared_bounds = (
        np.minimum(old.min(axis=(0, 1)), new.min(axis=(0, 1))),
        np.maximum(old.max(axis=(0, 1)), new.max(axis=(0, 1))),
    )
    detail_bounds = (
        np.minimum(old_root.min(axis=(0, 1)), feature_root.min(axis=(0, 1))),
        np.maximum(old_root.max(axis=(0, 1)), feature_root.max(axis=(0, 1))),
    )
    fig = plt.figure(figsize=(18, 14), facecolor="white")
    _plot(
        fig.add_subplot(2, 2, 1, projection="3d"),
        old,
        "OLD NC: Y-tilt/B hypothesis (not calibrated)",
        "#2865a8",
        shared_bounds,
    )
    _plot(
        fig.add_subplot(2, 2, 2, projection="3d"),
        new,
        "NEW NC: complete hub + 3 solid radial blades",
        "#15866f",
        shared_bounds,
    )
    _plot(
        fig.add_subplot(2, 2, 3, projection="3d"),
        old_root,
        "OLD NC detail: blade 1 root under axis hypothesis",
        "#e18a16",
        detail_bounds,
    )
    detail = fig.add_subplot(2, 2, 4, projection="3d")
    _plot(
        detail,
        feature_root,
        "NEW NC detail: blade 1 finite-width hub bond",
        "#9d3b9f",
        detail_bounds,
    )
    _add(detail, skin_root, "#c43d35", 0.5)
    _add(detail, infill_root, "#f0a51b", 0.46)
    fig.suptitle(
        "Three-leaf fan | Actual NC paths | OFFLINE complete-stream readback accepted",
        fontsize=18,
    )
    fig.text(
        0.025,
        0.035,
        "New paths are reconstructed from emitted AC NC. Red = finite-width skin; orange = internal solid fill. Every blade has two explicit hub-bond layers.",
        fontsize=10,
    )
    fig.text(
        0.025,
        0.016,
        "Old coordinates use the best documented Y-tilt/B, Z=-1.5 mm hypothesis only; legacy machine calibration remains unresolved. IPW collision is user-deferred.",
        fontsize=10,
        color="#8a3c1f",
    )
    fig.subplots_adjust(left=0.01, right=0.99, top=0.91, bottom=0.07, wspace=0.02, hspace=0.12)
    output = FOLDER / "nc_comparison.png"
    fig.savefig(output, dpi=180)
    plt.close(fig)

    old_points = old[:, 1][:: max(1, len(old) // 100_000)]
    new_points = new[:, 1][:: max(1, len(new) // 100_000)]
    old_to_new = cKDTree(new_points).query(old_points)[0]
    new_to_old = cKDTree(old_points).query(new_points)[0]
    comparison = {
        "old_positive_e_segments": len(old),
        "old_coordinate_interpretation": "Y tilt, positive A/B, Z offset -1.5 mm; hypothesis only",
        "new_complete_deposition_segments": len(new),
        "new_feature_segments": len(feature),
        "new_feature_skin_segments": len(skin),
        "new_feature_infill_segments": len(infill),
        "new_blade1_root_segments": len(feature_root),
        "endpoint_proximity_scope": "sampled endpoints; legacy axis mapping remains a hypothesis",
        "old_to_new_mm": _stats(old_to_new),
        "new_to_old_mm": _stats(new_to_old),
        "accepted_scope": "new offline AC NC geometry and complete-stream readback",
        "physical_machine_qualified": False,
    }
    (FOLDER / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(output)


def _legacy_y_tilt_hypothesis(segments, ac):
    angle_a = np.deg2rad(ac[:, 0])[:, None]
    angle_b = np.deg2rad(ac[:, 2])[:, None]
    x = segments[:, :, 0]
    y = segments[:, :, 1]
    z = segments[:, :, 2] - 1.5
    x1 = np.cos(angle_a) * x - np.sin(angle_a) * z
    z1 = np.sin(angle_a) * x + np.cos(angle_a) * z
    return np.stack(
        (
            np.cos(angle_b) * x1 + np.sin(angle_b) * y,
            -np.sin(angle_b) * x1 + np.cos(angle_b) * y,
            z1,
        ),
        axis=2,
    )


def _root_detail_mask(segments):
    midpoint = segments.mean(axis=1)
    radial = np.linalg.norm(midpoint[:, :2], axis=1)
    angle = np.arctan2(midpoint[:, 1], midpoint[:, 0])
    center = math.radians(-35)
    delta = np.abs(np.arctan2(np.sin(angle - center), np.cos(angle - center)))
    return (radial >= 9.0) & (radial <= 16.0) & (midpoint[:, 2] >= 54) & (delta <= math.radians(42))


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
    ax.view_init(elev=24, azim=-58)
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
