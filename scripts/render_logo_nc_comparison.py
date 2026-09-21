"""Render actual old and strictly read-back new spherical-logo NC paths."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Line3DCollection
import numpy as np
from scipy.spatial import cKDTree

from render_fan15_examples import plot


ROOT = Path(__file__).resolve().parents[1]
OLD_FOLDER = ROOT / "docs/reviews/evidence/2026-09-20_fan15_examples/hemisphere_pattern"
FOLDER = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs" / "logo_offline_nc_20260921"


def main() -> None:
    legacy_data = np.load(OLD_FOLDER / "legacy.npz")
    # The legacy MATLAB overlay records a 180-degree registration about Z.
    old = legacy_data["segments"] * np.array([-1.0, -1.0, 1.0])
    old_logo = old[legacy_data["custom"]]
    data = np.load(FOLDER / "nc_readback_paths.npz")
    new = data["deposition"]
    radial = np.linalg.norm(new, axis=2)
    feature_mask = radial.mean(axis=1) > 40.05
    new_logo = new[feature_mask]
    skin = data["skin"]
    infill = data["infill"]
    skin = skin[np.linalg.norm(skin, axis=2).mean(axis=1) > 40.05]
    infill = infill[np.linalg.norm(infill, axis=2).mean(axis=1) > 40.05]

    shared_bounds = (
        np.minimum(old.min(axis=(0, 1)), new.min(axis=(0, 1))),
        np.maximum(old.max(axis=(0, 1)), new.max(axis=(0, 1))),
    )
    detail_bounds = (
        np.minimum(old_logo.min(axis=(0, 1)), new_logo.min(axis=(0, 1))),
        np.maximum(old_logo.max(axis=(0, 1)), new_logo.max(axis=(0, 1))),
    )
    fig = plt.figure(figsize=(18, 14), facecolor="white")
    plot(
        fig.add_subplot(2, 2, 1, projection="3d"),
        old,
        "OLD NC: complete positive-E reconstruction",
        "#2865a8",
        shared_bounds,
    )
    plot(
        fig.add_subplot(2, 2, 2, projection="3d"),
        new,
        "NEW NC: 201-layer hemisphere + 3-layer solid emblem",
        "#15866f",
        shared_bounds,
    )
    plot(
        fig.add_subplot(2, 2, 3, projection="3d"),
        old_logo,
        "OLD NC detail: CUSTOM-marked emblem paths",
        "#e18a16",
        detail_bounds,
    )
    detail = fig.add_subplot(2, 2, 4, projection="3d")
    plot(detail, new_logo, "NEW NC detail: complete raised-solid emblem", "#9d3b9f", detail_bounds)
    if len(skin):
        detail.add_collection3d(Line3DCollection(skin, colors="#c43d35", linewidths=0.55))
    if len(infill):
        detail.add_collection3d(Line3DCollection(infill, colors="#f0a51b", linewidths=0.48))
    fig.suptitle(
        "Spherical NEU emblem | Actual NC paths | OFFLINE readback accepted",
        fontsize=18,
    )
    fig.text(
        0.025,
        0.035,
        "New path is reconstructed from emitted XYZAC NC. Red = finite-width skin; orange = internal solid fill. CAD surfaces are not drawn.",
        fontsize=10,
    )
    fig.text(
        0.025,
        0.016,
        "Machine calibration, controller macros and IPW collision remain outside this offline acceptance.",
        fontsize=10,
        color="#8a3c1f",
    )
    fig.subplots_adjust(left=0.01, right=0.99, top=0.91, bottom=0.07, wspace=0.02, hspace=0.12)
    output = FOLDER / "nc_comparison.png"
    fig.savefig(output, dpi=180)
    plt.close(fig)

    old_points = old_logo[:, 1][:: max(1, len(old_logo) // 100_000)]
    new_points = new_logo[:, 1][:: max(1, len(new_logo) // 100_000)]
    old_to_new = cKDTree(new_points).query(old_points)[0]
    new_to_old = cKDTree(old_points).query(new_points)[0]
    comparison = {
        "old_complete_positive_e_segments": len(old),
        "old_custom_logo_segments": len(old_logo),
        "new_complete_deposition_segments": len(new),
        "new_feature_segments": len(new_logo),
        "new_feature_skin_segments": len(skin),
        "new_feature_infill_segments": len(infill),
        "legacy_registration": "Rz(180 deg), documented by the existing MATLAB overlay",
        "endpoint_proximity_scope": "sampled endpoints only; fill strategy and radial thickness differ",
        "old_logo_to_new_logo_mm": _stats(old_to_new),
        "new_logo_to_old_logo_mm": _stats(new_to_old),
        "accepted_scope": "offline NC geometry and complete-stream readback",
        "physical_machine_qualified": False,
    }
    (FOLDER / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(output)


def _stats(values):
    return {
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "maximum": float(values.max()),
    }


if __name__ == "__main__":
    main()
