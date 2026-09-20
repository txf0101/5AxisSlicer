"""Generate each blade from its own BRep and render NEW deposition candidates."""

from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from five_axis_slicer.algorithms.fan.assembly import audit_fan_interfaces, blade_chart_center
from five_axis_slicer.algorithms.fan.radial import radial_blade_domain
from five_axis_slicer.algorithms.fan.program import generate_fan_base_plan
from five_axis_slicer.algorithms.planar.region import _area
from five_axis_slicer.manufacturing.fan_job import FanManufacturingContract, FanGeometrySelection
from five_axis_slicer.manufacturing.reference_descriptors import geometry_reference
from five_axis_slicer.step_loader import load_step
from probe_fan_radial_layers import preview_paths, draw_panel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/reviews/evidence/2026-09-20_fan_complete_program/radial_repair_full"


def save(name, payload):
    with gzip.open(OUT / name, "wt", encoding="utf8") as stream:
        json.dump(payload, stream)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / "example/扇叶/风扇扇叶(1).STEP"
    model = load_step(source)
    selection = FanGeometrySelection(
        geometry_reference(model, "body_004", "body"),
        tuple(geometry_reference(model, f"body_{i:03d}", "body") for i in (1, 2, 3)),
    )
    interfaces = audit_fan_interfaces(model, selection)
    summary = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "interfaces": asdict(interfaces),
        "blades": [],
        "qualification": "deposition candidates only; no NC / collision or bead coverage qualification",
    }
    all_paths = []
    for reference in selection.blades:
        body_id = reference.object_id
        print("Generating independent CAD blade", body_id, flush=True)
        domain = radial_blade_domain(
            model.shapes[body_id],
            model.shapes["body_004"],
            substrate_radius_mm=17.5,
            last_radius_mm=85,
            seam_center_rad=blade_chart_center(model, body_id),
        )
        paths, unresolved = preview_paths(domain)
        occupied = [layer for layer in domain.layers if layer.regions]
        stats = {
            "body_id": body_id,
            "reference": reference.to_json(),
            "occupied_layers": len(occupied),
            "first_radius": occupied[0].z_mm,
            "last_radius": occupied[-1].z_mm,
            "paths": len(paths),
            "unresolved": unresolved,
            "root_samples": domain.root_sample_count,
            "volume_integral_mm3": 0.2
            * sum(
                _area(r.outer) + sum(_area(h) for h in r.holes)
                for layer in domain.layers
                for r in layer.regions
            ),
            "cad_volume_mm3": model.body_map[body_id].volume,
        }
        save(body_id + "_paths.json.gz", {"summary": stats, "paths": paths})
        print(json.dumps({k: v for k, v in stats.items() if k != "reference"}), flush=True)
        summary["blades"].append(stats)
        all_paths.extend((body_id, p) for p in paths if p["layer"] % 10 == 0)
        if body_id == "body_001":
            root_paths = [
                (p["role"], p["points"]) for p in paths if p["layer"] < 25 and p["layer"] % 2 == 0
            ]
    contract = FanManufacturingContract.from_json(
        json.loads(
            (
                ROOT / "docs/reviews/evidence/2026-09-20_fan_complete_program/fan_contract_v1.json"
            ).read_text(encoding="utf8")
        )
    )
    print("Generating full-height hub and support", flush=True)
    base = generate_fan_base_plan(model, contract)
    hub = []
    inverse = contract.source_to_build.inverse()
    for path in (base.part_toolpath, base.support_toolpath):
        layer_ids = {layer.layer_id: i for i, layer in enumerate(base.layers)}
        for a, b in zip(path.points, path.points[1:]):
            if b.point_type == "deposition" and layer_ids.get(b.layer_id, 0) % 8 == 0:
                hub.append(
                    (
                        "hub",
                        [inverse.transform_point(a.position), inverse.transform_point(b.position)],
                    )
                )
    summary["base"] = {
        "layers": len(base.layers),
        "part_points": len(base.part_toolpath.points),
        "support_points": len(base.support_toolpath.points),
        "display_layer_stride": 8,
    }
    summary["blade_display_layer_stride"] = 10
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8"
    )
    canvas = Image.new("RGB", (2600, 1800), "#edf3f7")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 30)
    draw.text(
        (35, 22),
        "NEW CAD-generated radial paths | all three independent blades + full-height hub",
        font=font,
        fill="#203449",
    )
    curves = hub + [(p["role"], p["points"]) for _, p in all_paths]
    draw_panel(
        draw,
        (30, 90, 2570, 1650),
        curves,
        "Assembly / Source coordinates",
        "Red: curved shells; orange: internal fill; blue: hub + support paths. Display subsampling only.",
    )
    draw.text(
        (40, 1690),
        "Research preview: deposition only. Travel, bead coverage and full machine collision qualification remain pending.",
        font=font,
        fill="#203449",
    )
    canvas.save(OUT / "fan_new_radial_full.png")
    detail = Image.new("RGB", (2400, 1400), "#edf3f7")
    draw_panel(
        ImageDraw.Draw(detail),
        (30, 30, 2370, 1370),
        root_paths,
        "NEW blade 1 root detail - first 5 mm radial growth",
        "Actual curved paths; every second layer; same data as the complete blade",
    )
    detail.save(OUT / "fan_new_radial_root_detail.png")
    print("Saved full assembly and root detail", flush=True)


if __name__ == "__main__":
    main()
