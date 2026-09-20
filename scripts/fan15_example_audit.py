"""Reproducible example audit; failed or partial paths never acquire NC qualification."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.algorithms.planar.region import slice_planar_layers
from five_axis_slicer.algorithms.planar.feature_fill import FeatureFillParameters, plan_feature_fill
from five_axis_slicer.algorithms.planar.offset import inset_region
from five_axis_slicer.algorithms.tube.geometry import recognise_tube
from five_axis_slicer.algorithms.tube.continuous import generate_continuous_toolpath
from five_axis_slicer.algorithms.tube.indexed import plan_indexed_slices, generate_indexed_toolpath
from five_axis_slicer.manufacturing.setup import TubeProcessParameters
from five_axis_slicer.tube_controller import TubeSetupController
from five_axis_slicer.algorithms.freeform import build_freeform_plan
import paper_core_ac_evidence as pc

OUT = ROOT / "docs/reviews/evidence/2026-09-20_fan15_examples"
CASES = {
    "pipe2": ("pipe2/弯管新.stp", "pipe2/弯管.gcode"),
    "hemisphere_pattern": ("球形NEU校徽/球形测试件.STEP", "球形NEU校徽/NEU校徽划线.gcode"),
    "three_leaf": ("三叶扇/Supportless_sample.stp", "三叶扇/EXAMPLE.gcode"),
    "impeller": ("叶轮/叶轮.stp", "叶轮/叶轮完整.gcode"),
}
WORDS = re.compile(r"([A-Z])\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))")


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def inverse(a):
    x, y, z, av, cv = a
    av, cv = math.radians(av), math.radians(cv)
    v = math.cos(av) * y + math.sin(av) * z
    return (
        math.cos(cv) * x + math.sin(cv) * v,
        -math.sin(cv) * x + math.cos(cv) * v,
        -math.sin(av) * y + math.cos(av) * z,
    )


def source_lines(path):
    with path.open("rb") as stream:
        yield from stream


def legacy(path, folder):
    """Diagnostic zero-centre AC reconstruction, not a machine safety validator."""
    axes = np.zeros(6)
    absolute, relative_e, e = True, False, 0.0
    counts, types = Counter(), Counter()
    segments, machine_segments, deltas, line_ids, angles = [], [], [], [], []
    unsupported_rotary = set()
    custom_flags = []
    role = "unspecified"
    digest = hashlib.sha256()
    for line_id, raw in enumerate(source_lines(path), 1):
        digest.update(raw)
        line = raw.decode("utf-8", errors="replace").upper()
        if ";TYPE:" in line:
            role = line.split(";TYPE:", 1)[1].strip()
        command = line.split(";", 1)[0].strip()
        if not command:
            continue
        words = dict((k, float(v)) for k, v in WORDS.findall(command))
        code = command.split()[0]
        counts[code] += 1
        if code in {"G0", "G1", "G92"}:
            unsupported_rotary.update(set(words) & set("BUVW"))
        if code in {"G20", "G2", "G3"}:
            raise ValueError(f"diagnostic parser unsupported {code} line {line_id}")
        if code in {"G90", "G91"}:
            absolute = code == "G90"
        if code in {"M82", "M83"}:
            relative_e = code == "M83"
        if code == "G92":
            e = words.get("E", e)
            for i, key in enumerate("XYZACB"):
                axes[i] = words.get(key, axes[i])
        if code not in {"G0", "G1"}:
            continue
        previous = axes.copy()
        for i, key in enumerate("XYZACB"):
            if key in words:
                axes[i] = words[key] + (0 if absolute else axes[i])
        de = words.get("E", 0) if relative_e else words.get("E", e) - e
        e += de
        if de > 0 and np.any(axes != previous):
            segments.append((inverse(previous[:5]), inverse(axes[:5])))
            machine_segments.append((previous[:3].copy(), axes[:3].copy()))
            deltas.append(de)
            line_ids.append(line_id)
            angles.append(axes[3:].copy())
            types[role] += 1
            custom_flags.append(role == "CUSTOM")
    array = np.asarray(machine_segments if unsupported_rotary else segments)
    np.savez_compressed(
        folder / "legacy.npz",
        segments=array,
        e=deltas,
        lines=line_ids,
        ac=angles,
        custom=custom_flags,
    )
    result = {
        "source": str(path),
        "sha256": digest.hexdigest(),
        "lines": line_id,
        "positive_e_segments": len(array),
        "commands": dict(counts),
        "types": dict(types),
        "bounds": [array.min(axis=(0, 1)).tolist(), array.max(axis=(0, 1)).tolist()],
        "positive_e_mm": sum(deltas),
        "length_mm": float(np.linalg.norm(array[:, 1] - array[:, 0], axis=1).sum()),
        "ac_bounds": [np.min(angles, axis=0).tolist(), np.max(angles, axis=0).tolist()],
        "frame": "machine XYZ: unsupported rotary mapping"
        if unsupported_rotary
        else "zero-centre Rz(-C)Rx(-A), registration to CAD not assumed",
        "unsupported_rotary_words": sorted(unsupported_rotary),
        "offset_macro_unresolved": bool(counts["SET_GCODE_OFFSET"]),
        "boundary": "G0/G1 positive-E only; positive E is not automatically valid deposition",
    }
    save_json(folder / "legacy.json", result)
    return result


def path_segments(path):
    return [
        (left.position, right.position)
        for left, right in zip(path.points, path.points[1:])
        if right.point_type == "deposition"
    ]


def current_mode(name, model, folder):
    results = {}
    if name == "pipe2":
        controller = TubeSetupController(model)
        controller.create_operation(operation_id="fan15-pipe")
        params = TubeProcessParameters(
            bead_width_mm=0.4,
            layer_height_mm=0.2,
            safe_clearance_mm=5,
            retract_length_mm=1,
            deposition_feedrate_mm_min=1200,
            travel_feedrate_mm_min=3000,
            contour_chord_error_mm=0.02,
        )
        operation = controller.configure_operation(
            tube_body_id="body_002",
            entry_port_id="body_002_edge_0003",
            exit_port_id="body_002_edge_0014",
            substrate_body_id="body_001",
            parameters=params,
        )
        feature = recognise_tube(model, operation.geometry)
        for mode in ("indexed", "continuous"):
            path = (
                generate_continuous_toolpath("fan15-pipe", feature, params)
                if mode == "continuous"
                else generate_indexed_toolpath(
                    "fan15-pipe", feature, plan_indexed_slices(feature, params), params, model=model
                )
            )
            array = np.asarray(path_segments(path))
            np.savez_compressed(folder / f"new_{mode}.npz", segments=array)
            results[mode] = {
                "segments": len(array),
                "volume_mm3": sum(p.material_volume_mm3 for p in path.points),
                "cad_tube_volume_mm3": model.body_map["body_002"].volume,
                "wall_thickness_mm": feature.wall_thickness_mm,
                "bead_width_mm": 0.4,
                "scope": "single mid-wall path, substrate excluded; no full wall fill",
            }
    elif name in pc.CASES:
        operation = pc._operation(model, name, pc.CASES[name], channels=1)
        operation = replace(
            operation,
            parameters=replace(
                operation.parameters,
                bead_width_mm=0.4,
                layer_height_mm=0.2,
                path_spacing_mm=0.4,
                sampling_step_mm=0.2,
                feedrate_mm_min=1200,
            ),
        )
        for step in (0.2, 3.0):
            try:
                plan = build_freeform_plan(
                    model,
                    replace(
                        operation, parameters=replace(operation.parameters, sampling_step_mm=step)
                    ),
                )
                array = np.asarray(
                    [
                        (a.position, b.position)
                        for p in plan.paths
                        for a, b in zip(p.samples, p.samples[1:])
                    ]
                )
                np.savez_compressed(folder / f"new_freeform_{step}.npz", segments=array)
                results[str(step)] = {
                    "paths": len(plan.paths),
                    "segments": len(array),
                    "scope": "existing selected guides only, not complete solid or logo",
                }
            except Exception as exc:
                results[str(step)] = {"error": str(exc)}
    else:
        results["five_axis"] = {"error": "No whole-solid five-axis partition generator registered"}
    save_json(folder / "current_mode.json", results)
    return results


def planar_diagnostic(model, folder):
    """Attempt every height, retaining failures; planar alternative is not conformal equivalence."""
    bodies = tuple(b.body_id for b in model.bodies)
    top = max(b.bounds.maximum[2] for b in model.bodies)
    all_segments, contours, failures = [], [], []
    completed = 0
    for i in range(1, math.floor((top + 1e-5) / 0.2) + 1):
        z = round(i * 0.2, 8)
        try:
            layer = slice_planar_layers(
                model,
                bodies,
                first_layer_z_mm=z,
                last_layer_z_mm=z,
                layer_height_mm=0.2,
                sample_segments=64,
            )[0]
            for region in layer.regions:
                for loop in (region.outer, *region.holes):
                    contours.extend(zip(loop, loop[1:]))
                # Independently probe errors currently swallowed by shared feature_fill.
                for d in (0.2, 0.6, 0.8):
                    inset_region(region, d)
            fill = plan_feature_fill(
                (layer,),
                FeatureFillParameters(
                    top_solid_layers=0, bottom_solid_layers=0, infill_fraction=0.2
                ),
            )[0]
            for region, planned in zip(layer.regions, fill.regions):
                if planned.wall_contours and planned.wall_contours[0] == region.outer:
                    raise ValueError("unsafe original-boundary wall fallback")
                for loop in planned.wall_contours:
                    all_segments.extend(zip(loop, loop[1:]))
                all_segments.extend(planned.infill_segments)
            completed += 1
        except Exception as exc:
            failures.append({"z_mm": z, "error": str(exc)})
        if i % 25 == 0:
            print(f"planar {folder.name} {i} layers; failed {len(failures)}", flush=True)
    np.savez_compressed(
        folder / "planar_diagnostic.npz",
        segments=np.asarray(all_segments).reshape(-1, 2, 3),
        contours=np.asarray(contours).reshape(-1, 2, 3),
    )
    result = {
        "requested_layers": i,
        "successful_layers": completed,
        "failures": failures,
        "deposition_segments": len(all_segments),
        "section_segments": len(contours),
        "scope": "full-height diagnostic alternative: no supports, no skin, no machine qualification",
        "accepted": False,
    }
    save_json(folder / "planar_diagnostic.json", result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--phase", choices=("audit", "planar"), default="audit")
    args = parser.parse_args()
    source, old = [ROOT / "example" / p for p in CASES[args.case]]
    folder = OUT / args.case
    folder.mkdir(parents=True, exist_ok=True)
    model = load_step(source)
    if args.phase == "planar":
        planar_diagnostic(model, folder)
        return
    inventory = {
        "source": str(source),
        "sha256": model.source_hash,
        "bodies": [
            {"id": b.body_id, "volume_mm3": b.volume, "bounds": b.bounds.to_json()}
            for b in model.bodies
        ],
    }
    save_json(folder / "inventory.json", inventory)
    print(args.case, "legacy", flush=True)
    legacy(old, folder)
    print(args.case, "current generator", flush=True)
    current_mode(args.case, model, folder)
    print(args.case, "done", flush=True)


if __name__ == "__main__":
    main()
