"""Reproducible radial geometry/fill preview; intentionally produces no NC."""

from __future__ import annotations

import gzip
import argparse
import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from five_axis_slicer.algorithms.fan.radial import radial_blade_domain, sample_chart_segment
from five_axis_slicer.algorithms.planar.feature_fill import FeatureFillParameters
from five_axis_slicer.algorithms.fan.chart_fill import radial_feature_fill
from five_axis_slicer.algorithms.planar.region import _area
from five_axis_slicer.step_loader import load_step

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/reviews/evidence/2026-09-20_fan_complete_program/radial_correction"


def preview_paths(domain):
    features = radial_feature_fill(domain.layers, FeatureFillParameters(infill_fraction=1))
    paths, unresolved = [], []
    for index, (source, layer) in enumerate(zip(domain.layers, features, strict=True)):
        for original, region in zip(source.regions, layer.regions, strict=True):
            if region.wall_contours and region.wall_contours[0] == original.outer:
                unresolved.append(layer.layer_id)
                continue  # The old boundary-centred narrow-wall fallback is not accepted.
            for role, curves in (
                ("shell", region.wall_contours),
                ("infill", region.infill_segments),
            ):
                for curve in curves:
                    points = []
                    for left, right in zip(curve, curve[1:]):
                        segment = sample_chart_segment(left, right)
                        points.extend(segment if not points else segment[1:])
                    paths.append(
                        {"layer": index, "radius": layer.z_mm, "role": role, "points": points}
                    )
    return paths, unresolved


def hub_lines(zmin=0, zmax=65):
    lines = []
    for z in (zmin, zmax):
        lines.append(
            [
                (17.5 * math.cos(t * math.pi / 90), 17.5 * math.sin(t * math.pi / 90), z)
                for t in range(181)
            ]
        )
    for t in range(0, 180, 15):
        x, y = 17.5 * math.cos(t * math.pi / 90), 17.5 * math.sin(t * math.pi / 90)
        lines.append([(x, y, zmin), (x, y, zmax)])
    return lines


def draw_panel(draw, box, curves, title, subtitle):
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 25)
    small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    left, top, right, bottom = box
    draw.rounded_rectangle(box, 15, fill="white", outline="#c7d4df", width=2)
    draw.text((left + 20, top + 18), title, fill="#203449", font=font)
    draw.text((left + 20, top + 55), subtitle, fill="#51697e", font=small)
    projected = [
        (role, [(p[0] - 0.62 * p[1], -p[2] + 0.28 * (p[0] + p[1])) for p in points])
        for role, points in curves
        if len(points) > 1
    ]
    xs = [p[0] for _, line in projected for p in line]
    ys = [p[1] for _, line in projected for p in line]
    xmin, ymin = min(xs), min(ys)
    scale = min(
        (right - left - 60) / (max(xs) - min(xs)), (bottom - top - 130) / (max(ys) - min(ys))
    )
    colors = {"hub": "#729ab0", "shell": "#c44537", "infill": "#e69d56"}
    for role, line in projected:
        pixel = [(left + 30 + (x - xmin) * scale, top + 100 + (y - ymin) * scale) for x, y in line]
        draw.line(pixel, fill=colors[role], width=2 if role != "infill" else 1)


def render(paths):
    canvas = Image.new("RGB", (2400, 1350), "#edf3f7")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 32)
    draw.text(
        (35, 22),
        "FAN radial correction - CAD-derived preview / NOT qualified for printing",
        fill="#203449",
        font=font,
    )
    overview = [("hub", line) for line in hub_lines()]
    overview += [(p["role"], p["points"]) for p in paths if p["layer"] % 10 == 0]
    root = [("hub", line) for line in hub_lines(49, 59)]
    root += [(p["role"], p["points"]) for p in paths if p["layer"] < 25 and p["layer"] % 2 == 0]
    draw_panel(
        draw,
        (30, 85, 1190, 1250),
        overview,
        "Hub + sampled radial layers (partial when range is limited)",
        "Hub envelope shown in blue; blade layers sampled every 10 layers",
    )
    draw_panel(
        draw,
        (1210, 85, 2370, 1250),
        root,
        "Root detail: starts at R17.7 on R17.5 substrate",
        "First 5 mm of growth; every 2 layers shown; no travel moves shown",
    )
    draw.text(
        (40, 1280),
        "Red: perimeter candidates   Orange: internal-fill candidates   Blue: CAD hub envelope (not support)",
        fill="#203449",
        font=font,
    )
    canvas.save(OUT / "fan_radial_root_preview.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--last-radius", type=float, default=111.0)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / "example/扇叶/风扇扇叶(1).STEP"
    model = load_step(source)
    print("Loaded CAD. Computing actual cylindrical sections...", flush=True)
    domain = radial_blade_domain(
        model.shapes["body_001"],
        model.shapes["body_004"],
        substrate_radius_mm=17.5,
        last_radius_mm=args.last_radius,
    )
    print("Cylindrical sections complete. Computing chart fill...", flush=True)
    paths, unresolved = preview_paths(domain)
    occupied = [layer for layer in domain.layers if layer.regions]
    volume = sum(
        sum(_area(r.outer) + sum(_area(h) for h in r.holes) for r in layer.regions)
        * domain.layer_height_mm
        for layer in domain.layers
    )
    summary = {
        "status": "experimental_preview_not_manufacturing_qualified",
        "requested_last_radius_mm": args.last_radius,
        "scope": "Only the requested radial range; not proof of whole-blade coverage",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "coordinate_frame": "Source XYZ; cylinder axis Source Z; no display registration",
        "root_samples": domain.root_sample_count,
        "unsupported_root_samples": domain.unsupported_root_sample_count,
        "root_probe": "CAD section R17.51 projected to hub R17.49; boundary samples only",
        "first_last_occupied_radius_mm": [occupied[0].z_mm, occupied[-1].z_mm],
        "occupied_layer_count": len(occupied),
        "layer_height_mm": 0.2,
        "section_integrated_volume_mm3": volume,
        "cad_blade_volume_mm3": model.body_map["body_001"].volume,
        "path_count": len(paths),
        "unresolved_narrow_layer_ids": unresolved,
        "not_verified": [
            "bead-envelope coverage and overlaps",
            "layer-to-layer support of actual deposited beads",
            "nozzle/fixture/printed-part swept collision",
            "safe non-extruding travel",
            "controller trajectory and independent NC readback",
            "physical printing",
        ],
    }
    with gzip.open(OUT / "radial_preview_paths.json.gz", "wt", encoding="utf-8") as stream:
        json.dump({"metadata": summary, "paths": paths}, stream)
    (OUT / "radial_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    render(paths)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
