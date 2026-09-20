"""Show actual spherical intersections, explicitly not extrusion paths."""
from pathlib import Path
import json
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from render_fan15_examples import plot

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs/spherical_domain_20260921"


def main():
    data = np.load(FOLDER / "boundaries.npz")["segments"]
    report = json.loads((FOLDER / "report.json").read_text(encoding="utf-8"))
    fig = plt.figure(figsize=(14, 8), facecolor="white")
    for index, (elev, azim, title) in enumerate(((35, -60, "Oblique view"), (90, -90, "Top view")), 1):
        ax = fig.add_subplot(1, 2, index, projection="3d")
        plot(ax, data, title, "#197884")
        ax.view_init(elev=elev, azim=azim)
    fig.suptitle("NEU: all 37 raised solids | spherical layer boundaries", fontsize=17)
    worst = max(abs(r["relative_error"]) for r in report["volumes"])
    fig.text(0.04, 0.08, f"111/111 sections recovered. Maximum per-solid integral/CAD volume difference: {worst:.3%}.")
    fig.text(0.04, 0.045, "Actual CAD intersections at three radii; Source coordinates, mm. All boundary segments shown.")
    fig.text(0.04, 0.01, "NOT DEPOSITION PATHS: no bead-width fill, base, safe travel or NC qualification yet.", color="#ac302c")
    fig.subplots_adjust(top=0.84, bottom=0.16)
    fig.savefig(FOLDER / "spherical_domains.png", dpi=200)


if __name__ == "__main__":
    main()
