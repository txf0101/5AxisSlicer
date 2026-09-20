"""All-solid spherical-domain evidence; not deposition or NC qualification."""

from pathlib import Path
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.algorithms.freeform.spherical_domain import SphericalChart, spherical_section


def main():
    out = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs/spherical_domain_20260921"
    out.mkdir(parents=True, exist_ok=True)
    model = load_step(ROOT / "example/球形NEU校徽/球形测试件.STEP")
    chart = SphericalChart()
    rows, segments = [], []
    # The model's 0.5 mm raised shell is inspected at three interior radii.
    # This is a domain probe, not a layer-height/deposition convention.
    for body in model.bodies[1:]:
        for radius in (40 + 1 / 12, 40.25, 40 + 5 / 12):
            row = {"body_id": body.body_id, "radius_mm": radius}
            try:
                layer = spherical_section(model.shapes[body.body_id], radius)
                contours = [
                    loop for region in layer.regions for loop in (region.outer, *region.holes)
                ]
                for loop in contours:
                    points = [chart.lift(p) for p in loop]
                    segments.extend(zip(points, points[1:]))
                row.update(
                    regions=len(layer.regions), contours=len(contours), passed=bool(contours)
                )
                row["surface_area_mm2"] = sum(chart.signed_surface_area(loop) for loop in contours)
            except Exception as error:
                row.update(passed=False, error=str(error))
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    np.savez_compressed(out / "boundaries.npz", segments=np.asarray(segments))
    volumes = []
    for body in model.bodies[1:]:
        group = [r for r in rows if r["body_id"] == body.body_id]
        if all(r["passed"] for r in group):
            volume = sum(r["surface_area_mm2"] for r in group) / 6
            volumes.append(
                {
                    "body_id": body.body_id,
                    "spherical_integral_mm3": volume,
                    "cad_volume_mm3": body.volume,
                    "relative_error": (volume - body.volume) / body.volume,
                }
            )
    (out / "report.json").write_text(
        json.dumps(
            {
                "source_hash": model.source_hash,
                "scope": "section boundaries only; no bead, support or NC qualification",
                "records": rows,
                "volumes": volumes,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
