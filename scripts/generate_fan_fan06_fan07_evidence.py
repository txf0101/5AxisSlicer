"""Generate FAN06/FAN07 real-model summaries and an actual-path preview."""

from __future__ import annotations

import argparse
from collections import Counter
import gc
import json
from pathlib import Path
import time

from PIL import Image, ImageDraw, ImageFont

from five_axis_slicer.algorithms.freeform.layer_domain import fixed_a_model_from_build
from five_axis_slicer.algorithms.fan import (
    generate_fan_base_plan,
    generate_single_blade_plan,
)
from five_axis_slicer.manufacturing.fan_job import FanManufacturingContract
from five_axis_slicer.step_loader import load_step


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs/reviews/evidence/2026-09-20_fan_complete_program/fan06_fan07"
COLORS = {
    "hub_shell": (36, 112, 171),
    "hub_skin": (237, 175, 83),
    "hub_infill": (85, 173, 151),
    "support": (191, 169, 213),
    "blade_shell": (196, 57, 48),
    "blade_skin": (242, 132, 35),
    "blade_infill": (222, 91, 73),
}


def _deposition_segments(
    toolpath,
    layer_stride: int,
    *,
    component: str,
    category: str | None = None,
    transform=None,
):
    result = {name: [] for name in COLORS}
    layer_order = {}
    previous = None
    for point in toolpath.points:
        layer_index = layer_order.setdefault(point.layer_id, len(layer_order))
        selected = layer_index % layer_stride == 0
        if selected and point.point_type == "deposition" and previous is not None:
            if previous.layer_id == point.layer_id:
                feature = _path_category(point.stage_id, point.extrusion_role)
                name = category or f"{component}_{feature}"
                start = previous.position
                end = point.position
                if transform is not None:
                    start = transform(start)
                    end = transform(end)
                result[name].append((start, end))
        previous = point
    return result


def _path_category(stage_id: str, role: str) -> str:
    if "shell" in stage_id:
        return "shell"
    if "skin" in stage_id or role == "skin":
        return "skin"
    return "infill"


def _merge_segments(*groups):
    merged = {name: [] for name in COLORS}
    for group in groups:
        for name, segments in group.items():
            merged[name].extend(segments)
    return merged


def _project(point):
    x_mm, y_mm, z_mm = point
    return x_mm - 0.62 * y_mm, -z_mm + 0.28 * (x_mm + y_mm)


def _draw_panel(draw, box, segments, title, subtitle):
    left, top, right, bottom = box
    projected = [
        (_project(start), _project(end), name)
        for name, values in segments.items()
        for start, end in values
    ]
    values = [point for start, end, _ in projected for point in (start, end)]
    minimum_x = min(point[0] for point in values)
    maximum_x = max(point[0] for point in values)
    minimum_y = min(point[1] for point in values)
    maximum_y = max(point[1] for point in values)
    width = max(maximum_x - minimum_x, 1.0)
    height = max(maximum_y - minimum_y, 1.0)
    scale = min((right - left - 70) / width, (bottom - top - 125) / height)

    def canvas(point):
        return (
            left + 35 + (point[0] - minimum_x) * scale,
            top + 85 + (point[1] - minimum_y) * scale,
        )

    draw.rounded_rectangle(box, radius=18, fill=(250, 252, 254), outline=(207, 215, 224), width=2)
    draw.text((left + 28, top + 22), title, fill=(28, 38, 49), font=ImageFont.load_default(20))
    draw.text((left + 28, top + 49), subtitle, fill=(80, 92, 105), font=ImageFont.load_default(14))
    for start, end, name in projected:
        draw.line((*canvas(start), *canvas(end)), fill=COLORS[name], width=1)


def _toolpath_summary(toolpath):
    deposition = [point for point in toolpath.points if point.point_type == "deposition"]
    return {
        "point_count": len(toolpath.points),
        "event_count": len(toolpath.events),
        "deposition_point_count": len(deposition),
        "deposition_volume_mm3": sum(point.material_volume_mm3 for point in deposition),
        "stage_counts": dict(Counter(point.stage_id for point in deposition)),
        "extrusion_role_counts": dict(Counter(point.extrusion_role for point in deposition)),
        "deposition_layer_count": len({point.layer_id for point in deposition}),
    }


def _feature_counts(features):
    return dict(Counter(region.feature_type for layer in features for region in layer.regions))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    model = load_step(ROOT / "example/扇叶/风扇扇叶(1).STEP")
    contract = FanManufacturingContract.from_json(
        json.loads(
            (
                ROOT / "docs/reviews/evidence/2026-09-20_fan_complete_program/fan_contract_v1.json"
            ).read_text(encoding="utf-8")
        )
    )

    started = time.perf_counter()
    base = generate_fan_base_plan(model, contract)
    base_seconds = time.perf_counter() - started
    base_segments = _merge_segments(
        _deposition_segments(base.part_toolpath, 10, component="hub"),
        _deposition_segments(base.support_toolpath, 3, component="hub", category="support"),
    )
    base_summary = {
        "layer_count": len(base.layers),
        "nonempty_layer_count": sum(bool(layer.regions) for layer in base.layers),
        "all_layers_scheduled": base.all_layers_scheduled,
        "support_layer_count": sum(
            bool(layer.body_regions or layer.interface_regions) for layer in base.support.layers
        ),
        "support_diagnostic_count": len(base.support.diagnostics),
        "unsupported_contact_area_mm2": base.support.unsupported_area_mm2,
        "feature_counts": _feature_counts(base.features),
        "part_toolpath": _toolpath_summary(base.part_toolpath),
        "support_toolpath": _toolpath_summary(base.support_toolpath),
        "generation_seconds": base_seconds,
    }
    del base
    gc.collect()

    started = time.perf_counter()
    blade = generate_single_blade_plan(model, contract)
    blade_seconds = time.perf_counter() - started
    indexed_to_source = fixed_a_model_from_build(blade.audit.a_angle_deg)

    def blade_to_common_build(point):
        source_point = indexed_to_source.transform_point(point)
        return contract.source_to_build.transform_point(source_point)

    blade_segments = _deposition_segments(
        blade.toolpath,
        4,
        component="blade",
        transform=blade_to_common_build,
    )
    assembly_segments = _merge_segments(base_segments, blade_segments)
    blade_path_summary = _toolpath_summary(blade.toolpath)
    blade_summary = {
        "body_id": blade.audit.body_id,
        "a_angle_deg": blade.audit.a_angle_deg,
        "layer_count": len(blade.audit.layers),
        "nonempty_layer_count": blade.audit.nonempty_layer_count,
        "internal_empty_layer_ids": blade.audit.internal_empty_layer_ids,
        "geometry_feasible": blade.audit.geometry_feasible,
        "machine_qualification_pending": blade.audit.machine_qualification_pending,
        "cad_volume_mm3": blade.audit.cad_volume_mm3,
        "section_volume_mm3": blade.audit.section_volume_mm3,
        "section_relative_volume_error": blade.audit.relative_volume_error,
        "feature_counts": _feature_counts(blade.features),
        "toolpath": blade_path_summary,
        "toolpath_to_cad_volume_error": (
            blade_path_summary["deposition_volume_mm3"] / blade.audit.cad_volume_mm3 - 1.0
        ),
        "generation_seconds": blade_seconds,
    }
    preview = {
        "coordinate_frame": "common build frame before A indexing",
        "blade_mapping": "indexed build -> source -> common build",
        "base_layer_stride": 10,
        "support_layer_stride": 3,
        "blade_layer_stride": 4,
        "rendered_segment_counts": {
            "base": {key: len(value) for key, value in base_segments.items()},
            "blade": {key: len(value) for key, value in blade_segments.items()},
        },
        "note": (
            "The image combines the hub and blade in one assembly frame and samples complete "
            "generated toolpaths by layer for legible rendering."
        ),
    }
    summary = {
        "source_step": str(model.source_path),
        "source_sha256": model.source_hash,
        "contract_sha256": contract.semantic_sha256(),
        "base": base_summary,
        "blade_1": blade_summary,
        "preview": preview,
    }
    (output / "fan06_fan07_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    image = Image.new("RGB", (2200, 1500), (238, 243, 248))
    draw = ImageDraw.Draw(image)
    draw.text(
        (60, 28),
        "FAN07 complete assembly - hub with blade 1",
        fill=(20, 31, 43),
        font=ImageFont.load_default(28),
    )
    _draw_panel(
        draw,
        (55, 90, 2145, 1370),
        assembly_segments,
        "Combined path view in one assembly coordinate frame",
        (
            "Hub: 20% infill + support | Blade: A=90 deg generation mapped back to "
            "assembly pose | root-to-tip"
        ),
    )
    legend_x = 180
    for name, color in COLORS.items():
        draw.line((legend_x, 1430, legend_x + 42, 1430), fill=color, width=5)
        draw.text(
            (legend_x + 50, 1420),
            name.replace("_", " ").title(),
            fill=(45, 56, 68),
            font=ImageFont.load_default(14),
        )
        legend_x += 285
    image.save(output / "fan_fan07_toolpath_preview.png")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
