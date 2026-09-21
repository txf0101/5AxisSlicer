"""Render the actual full merged product toolpath, including a separate travel view."""

import gzip
import argparse
import json
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from render_fan15_examples import plot

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs/pipe_profile_optimized_20260921"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, default=FOLDER)
    folder = parser.parse_args().folder
    with gzip.open(folder / "toolpath.json.gz", "rt", encoding="utf-8") as stream:
        path = json.load(stream)
    points = path["points"]
    xyz = np.asarray([p["position"] for p in points])
    pairs = np.stack((xyz[:-1], xyz[1:]), axis=1)
    deposition = np.asarray([p["point_type"] == "deposition" for p in points[1:]])
    bounds = (xyz.min(axis=0), xyz.max(axis=0))
    fig = plt.figure(figsize=(16, 8), facecolor="white")
    plot(
        fig.add_subplot(121, projection="3d"),
        pairs[deposition],
        "FULL MERGED PRODUCT: actual deposition",
        "#158f87",
        bounds,
    )
    plot(
        fig.add_subplot(122, projection="3d"),
        pairs[~deposition],
        "ALL non-deposition moves / inspect clearance",
        "#c25430",
        bounds,
    )
    fig.suptitle("Pipe2 full slicing diagnostic | NOT APPROVED FOR PRINTING", fontsize=16)
    fig.text(
        0.04,
        0.04,
        f"{len(points):,} points. All segments shown; source/build frame, mm. No geometry drawn from CAD.",
    )
    fig.text(
        0.04,
        0.015,
        "No NC qualification: collision and layer-contact checks must pass separately.",
        color="#a32c25",
    )
    fig.subplots_adjust(top=0.88, bottom=0.12)
    fig.savefig(folder / "full_product_paths.png", dpi=180)
    plt.close(fig)
    print(folder / "full_product_paths.png")


if __name__ == "__main__":
    main()
