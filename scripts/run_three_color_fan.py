"""Exercise the public Freeform product chain on a three-colour PLA fan.

The service station below is a synthetic offline fixture. Its coordinates and
macro must be replaced with measured machine data before physical printing.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.freeform_operation_service import (  # noqa: E402
    configure_freeform_solid_operation,
    create_freeform_operation,
)
from five_axis_slicer.manufacturing.controller_profile import (  # noqa: E402
    OWN_AC_OFFLINE_CONTROLLER,
    ToolChangeStation,
)
from five_axis_slicer.manufacturing.coordinates import RigidTransform  # noqa: E402
from five_axis_slicer.manufacturing.freeform_solid_parameters import (  # noqa: E402
    SolidFillProcessParameters,
)
from five_axis_slicer.manufacturing.material_plan import (  # noqa: E402
    MaterialChannel,
    MaterialPlan,
    MaterialRegion,
)
from five_axis_slicer.manufacturing.own_printer import own_ac_profile  # noqa: E402
from five_axis_slicer.postprocessing.freeform_product import (  # noqa: E402
    generate_freeform_product,
)
from five_axis_slicer.step_loader import load_step  # noqa: E402

from run_fan15_solid_product import CASES, reference_nozzle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--layer-height", type=float, default=0.4)
    parser.add_argument("--sampling-step", type=float, default=0.8)
    parser.add_argument("--safe-clearance", type=float, default=20.0)
    parser.add_argument(
        "--tip-only", action="store_true",
        help="offline tip-only service check; outer nozzle envelope remains unverified",
    )
    args = parser.parse_args()
    source = CASES["three_leaf"]["source"]
    started = time.perf_counter()
    model = load_step(source)
    operation = create_freeform_operation(
        (), "fan-three-colour-setup", "radial_solid_fill", operation_id="fan-three-colour"
    )
    operation = configure_freeform_solid_operation(
        operation,
        model,
        geometry=CASES["three_leaf"]["geometry"](model),
        parameters=SolidFillProcessParameters(
            layer_height_mm=args.layer_height, sampling_step_mm=args.sampling_step,
            safe_clearance_mm=args.safe_clearance,
        ),
    )
    material_plan = MaterialPlan(
        "fan-three-colour-pla",
        (
            MaterialChannel("T0", "PLA-red", "T0", 195.0, 8.0, load_length_mm=20.0,
                            unload_length_mm=20.0),
            MaterialChannel("T1", "PLA-blue", "T1", 195.0, 8.0, load_length_mm=20.0,
                            unload_length_mm=20.0),
            MaterialChannel("T2", "PLA-yellow", "T2", 195.0, 8.0, load_length_mm=20.0,
                            unload_length_mm=20.0),
        ),
        (
            MaterialRegion("*", "T0", "op01-"),
            MaterialRegion("*", "T0", "op02-"),
            MaterialRegion("*", "T1", "op03-"),
            MaterialRegion("*", "T2", "op04-"),
        ),
        sensor_required=True,
    )
    operation = replace(operation, material_plan=material_plan)
    station = ToolChangeStation(
        clearance_z_mm=180.0,
        cutter_xyz_mm=(130.0, 100.0, 80.0),
        exchange_xyz_mm=(140.0, 100.0, 80.0),
        purge_xyz_mm=(150.0, 100.0, 80.0),
        wipe_start_xyz_mm=(160.0, 100.0, 80.0),
        wipe_end_xyz_mm=(170.0, 100.0, 80.0),
    )
    controller = replace(OWN_AC_OFFLINE_CONTROLLER, tool_change_station=station)
    nozzle = reference_nozzle()
    if args.tip_only:
        nozzle = replace(nozzle, outer_profile_rz_mm=())
    print("Generating complete three-colour fan through Freeform product chain", flush=True)
    result = generate_freeform_product(
        model, operation, own_ac_profile(), nozzle, controller,
        T_build_from_source=RigidTransform.identity("build"), source_path=source,
    )
    report = {
        "source": str(source),
        "operation_semantic_sha256": operation.semantic_sha256(),
        "controller_semantic_sha256": controller.semantic_sha256(),
        "offline_station_only": True,
        "nozzle_envelope": "tip_only_unverified" if args.tip_only else "reference_profile",
        "machine_executable": result.machine_executable,
        "status": result.manifest.status.value,
        "offline_exportable": result.offline_exportable,
        "point_count": len(result.toolpath.points),
        "layer_height_mm": args.layer_height,
        "sampling_step_mm": args.sampling_step,
        "safe_clearance_mm": args.safe_clearance,
        "material_statistics": result.validation.material_statistics,
        "issue_codes": [item.code for item in result.validation.issues],
        "issues": [item.to_json() for item in result.validation.issues],
        "readback": result.readback.to_json(),
        "elapsed_s": time.perf_counter() - started,
    }
    report["colour_boundaries"] = [
        {
            "channel": event.context["channel_id"],
            "sequence_index": index,
            "before": {
                "point_id": result.toolpath.points[index - 1].point_id,
                "stage_id": result.toolpath.points[index - 1].stage_id,
                "point_type": result.toolpath.points[index - 1].point_type,
                "build_xyz_mm": result.toolpath.points[index - 1].position,
                "machine_axes": dict(result.trajectory.samples[index - 1].joint_positions),
            } if index else None,
            "after": {
                "point_id": result.toolpath.points[index].point_id,
                "stage_id": result.toolpath.points[index].stage_id,
                "point_type": result.toolpath.points[index].point_type,
                "build_xyz_mm": result.toolpath.points[index].position,
                "machine_axes": dict(result.trajectory.samples[index].joint_positions),
            },
        }
        for event in result.toolpath.events
        if event.event_type == "switch"
        for index in (int(event.context["sequence_index"]),)
    ]
    args.output.mkdir(parents=True, exist_ok=True)
    preview_path = args.output / "three_color_fan_candidate_preview.png"
    try:
        _write_colour_preview(result, preview_path)
        report["candidate_preview_png"] = preview_path.name
    except Exception as exc:
        report["candidate_preview_error"] = f"{type(exc).__name__}: {exc}"
    if result.offline_exportable:
        commands = re.findall(r"^T\d+$", result.gcode, flags=re.MULTILINE)
        if commands != ["T0", "T1", "T2"]:
            raise RuntimeError(f"unexpected tool-selection sequence: {commands}")
        if result.gcode.count("; PAC SERVICE cutter\n") != 2:
            raise RuntimeError("expected one cutter visit per effective colour transition")
        report["tool_commands"] = commands
        report["cutter_visits"] = 2
        nc_path = args.output / "three_color_fan.gcode"
        nc_path.write_bytes(result.gcode.encode("utf-8"))
        nc_bytes = nc_path.read_bytes()
        report["nc_sha256"] = hashlib.sha256(nc_bytes).hexdigest()
        report["nc_size_bytes"] = len(nc_bytes)
    (args.output / "acceptance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def _write_colour_preview(result, destination: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    groups = {
        "op01-": ("Hub/base (T0)", "#8493a5"),
        "op02-": ("Blade 1: red PLA (T0)", "#d94a43"),
        "op03-": ("Blade 2: blue PLA (T1)", "#2775c9"),
        "op04-": ("Blade 3: yellow PLA (T2)", "#d49b00"),
    }
    segments = {prefix: [] for prefix in groups}
    deposition = [point for point in result.toolpath.points if point.point_type == "deposition"]
    stride = max(1, len(deposition) // 80000)
    for index in range(1, len(result.toolpath.points), stride):
        left = result.toolpath.points[index - 1]
        right = result.toolpath.points[index]
        if left.point_type != "deposition" or right.point_type != "deposition":
            continue
        prefix = next((key for key in groups if right.stage_id.startswith(key)), None)
        if prefix is not None and left.stage_id.startswith(prefix):
            segments[prefix].append((left.position, right.position))
    image = Image.new("RGB", (1800, 1250), "#f7f9fc")
    draw = ImageDraw.Draw(image)
    font_path = "C:/Windows/Fonts/arial.ttf"
    try:
        title_font = ImageFont.truetype(font_path, 34)
        body_font = ImageFont.truetype(font_path, 22)
    except OSError:
        title_font = body_font = ImageFont.load_default()

    def project(point):
        x, y, z = point
        return 0.9063 * x + 0.4226 * y, -0.1786 * x + 0.3830 * y + 0.9063 * z

    positions = [project(point.position) for point in deposition]
    low_u = min(point[0] for point in positions)
    high_u = max(point[0] for point in positions)
    low_v = min(point[1] for point in positions)
    high_v = max(point[1] for point in positions)
    scale = min(1630 / max(1.0, high_u - low_u), 1020 / max(1.0, high_v - low_v))
    offset_u = 900 - scale * (low_u + high_u) / 2
    offset_v = 610 + scale * (low_v + high_v) / 2

    def pixel(point):
        u, v = project(point)
        return round(offset_u + scale * u), round(offset_v - scale * v)

    draw.rounded_rectangle((30, 82, 1770, 1130), radius=16, fill="white", outline="#d4dce8")
    for prefix, (_name, color) in groups.items():
        for left, right in segments[prefix]:
            draw.line((pixel(left), pixel(right)), fill=color, width=1)
    for issue in result.validation.issues:
        if issue.code not in {"motion.printed_part_collision", "tool_change.printed_part_collision"}:
            continue
        center = issue.context.get("nozzle_center_build_mm")
        if center is not None:
            x, y = pixel(center)
            draw.ellipse((x - 10, y - 10, x + 10, y + 10), outline="#141a27", width=4)
            draw.text((x + 14, y - 12), "blocked point", fill="#141a27", font=body_font)
        break
    status = "NC readback passed" if result.offline_exportable else "NC blocked by validation"
    draw.text((44, 25), f"Three-colour PLA fan | {status}", fill="#172033", font=title_font)
    legend_x = (72, 480, 920, 1355)
    for (name, color), x in zip(groups.values(), legend_x):
        draw.line((x, 1170, x + 55, 1170), fill=color, width=8)
        draw.text((x + 65, 1156), name, fill="#273345", font=body_font)
    draw.text(
        (55, 1211),
        "Planned deposition paths in build coordinates; service moves omitted. "
        "See acceptance.json for validation.",
        fill="#526174", font=body_font,
    )
    image.save(destination)


if __name__ == "__main__":
    main()
