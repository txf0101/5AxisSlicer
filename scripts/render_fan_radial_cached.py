"""Render this run's full-resolution blade caches; regenerate the hub paths."""

import gzip
import hashlib
import json
from PIL import Image, ImageDraw, ImageFont
from generate_fan_radial_assembly import ROOT, OUT, save
from probe_fan_radial_layers import draw_panel
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.manufacturing.fan_job import FanManufacturingContract
from five_axis_slicer.algorithms.fan.program import generate_fan_base_plan
from five_axis_slicer.manufacturing.reference_descriptors import geometry_reference


def main():
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf8"))
    source = ROOT / "example/扇叶/风扇扇叶(1).STEP"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == summary["source_sha256"]
    model = load_step(source)
    curves = []
    root = []
    for body in ("body_001", "body_002", "body_003"):
        with gzip.open(OUT / (body + "_paths.json.gz"), "rt", encoding="utf8") as stream:
            data = json.load(stream)
        assert data["summary"]["reference"] == geometry_reference(model, body, "body").to_json()
        assert not data["summary"]["unresolved"]
        curves.extend((p["role"], p["points"]) for p in data["paths"] if p["layer"] % 10 == 0)
        if body == "body_001":
            root = [
                (p["role"], p["points"])
                for p in data["paths"]
                if p["layer"] < 25 and p["layer"] % 2 == 0
            ]
    contract = FanManufacturingContract.from_json(
        json.loads(
            (
                ROOT / "docs/reviews/evidence/2026-09-20_fan_complete_program/fan_contract_v1.json"
            ).read_text(encoding="utf8")
        )
    )
    print(
        "Regenerating base for render; blade caches validated against source and references",
        flush=True,
    )
    base = generate_fan_base_plan(model, contract)
    inverse = contract.source_to_build.inverse()
    layers = {layer.layer_id: i for i, layer in enumerate(base.layers)}
    hub = []
    for path in (base.part_toolpath, base.support_toolpath):
        for a, b in zip(path.points, path.points[1:]):
            if b.point_type == "deposition" and layers.get(b.layer_id, 0) % 8 == 0:
                hub.append(
                    (
                        "hub",
                        [inverse.transform_point(a.position), inverse.transform_point(b.position)],
                    )
                )
    save(
        "base_display_paths.json.gz",
        {"display_only": True, "source_sha256": summary["source_sha256"], "curves": hub},
    )
    print("Rendering", len(curves), "blade paths and", len(hub), "hub segments", flush=True)
    canvas = Image.new("RGB", (2600, 1800), "#edf3f7")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 28)
    draw.text(
        (35, 22),
        "NEW CAD-generated radial paths | three independent blades + full-height hub",
        font=font,
        fill="#203449",
    )
    draw_panel(
        draw,
        (30, 90, 2570, 1650),
        hub + curves,
        "Assembly / Source coordinates",
        "Red: curved shells; orange: internal fill; blue: hub + support paths. Display subsampling only.",
    )
    draw.text(
        (40, 1690),
        "Deposition candidates only. Travel, bead coverage and full machine collision qualification remain pending.",
        font=font,
        fill="#203449",
    )
    canvas.save(OUT / "fan_new_radial_full.png")
    detail = Image.new("RGB", (2400, 1400), "#edf3f7")
    draw_panel(
        ImageDraw.Draw(detail),
        (30, 30, 2370, 1370),
        root,
        "NEW blade 1 root detail - first 5 mm radial growth",
        "Actual curved paths; every second layer; same data as the complete blade",
    )
    detail.save(OUT / "fan_new_radial_root_detail.png")
    print("Saved full assembly and root detail", flush=True)


if __name__ == "__main__":
    main()
