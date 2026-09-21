"""Generate and verify the complete spherical NEU-logo offline NC product."""

from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.algorithms.freeform.spherical_fill import (  # noqa: E402
    SphericalFillParameters,
    generate_spherical_solid_fill,
)
from five_axis_slicer.kinematics.xyzac import solve_xyzac_trajectory  # noqa: E402
from five_axis_slicer.manufacturing.own_printer import (  # noqa: E402
    own_ac_document,
    own_ac_profile,
)
from five_axis_slicer.manufacturing.resources import NozzleProfile  # noqa: E402
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath  # noqa: E402
from five_axis_slicer.postprocessing.gcode_readback import (  # noqa: E402
    readback_absolute_xyzac,
)
from five_axis_slicer.postprocessing.indexed_tube import (  # noqa: E402
    postprocess_indexed_gcode,
)
from five_axis_slicer.postprocessing.thermal_program import (  # noqa: E402
    ThermalProgramParameters,
    unwrap_checked_thermal_program,
    wrap_thermal_program,
)
from five_axis_slicer.postprocessing.toolpath_sequence import (  # noqa: E402
    merge_toolpath_sequence,
)
from five_axis_slicer.step_loader import load_step  # noqa: E402


SOURCE = ROOT / "example/球形NEU校徽/球形测试件.STEP"
OLD = ROOT / "example/球形NEU校徽/NEU校徽划线.gcode"
TARGET = ROOT / "example/球形NEU校徽/球形NEU校徽_新算法_离线检查_20260921.gcode"
EVIDENCE = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs" / "logo_offline_nc_20260921"
BASE_PATH = (
    ROOT
    / "docs/reviews/evidence/2026-09-20_fan15_repairs"
    / "remaining_substrates_midpoint_20260921/logo_base.json.gz"
)
WORDS = re.compile(r"([XYZAC])([-+0-9.]+)")


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}
    started = time.perf_counter()
    model = load_step(SOURCE)
    timings["load_step"] = time.perf_counter() - started
    with gzip.open(BASE_PATH, "rt", encoding="utf-8") as stream:
        base = GeneratedToolpath.from_json(json.load(stream))
    feature_ids = tuple(body.body_id for body in model.bodies if body.body_id != "body_001")
    parameters = SphericalFillParameters(
        substrate_radius_mm=40.0,
        radial_thickness_mm=0.5,
        layer_height_mm=0.2,
        bead_width_mm=0.4,
        deposition_feedrate_mm_min=1200.0,
        travel_feedrate_mm_min=3000.0,
        retract_length_mm=1.0,
        sample_segments=128,
    )
    started = time.perf_counter()
    feature, fill_audit = generate_spherical_solid_fill(
        model, feature_ids, "fan15-logo-feature", parameters
    )
    timings["spherical_solid_fill"] = time.perf_counter() - started
    combined = merge_toolpath_sequence(
        "fan15-logo-complete",
        (base, feature),
        safe_clearance_mm=5.0,
        travel_feedrate_mm_min=3000.0,
        retract_length_mm=1.0,
    )
    nozzle = NozzleProfile(
        resource_id="offline-envelope",
        display_name="Offline reference only",
        orifice_diameter_mm=0.4,
        filament_diameter_mm=1.75,
        interface="M6",
        length_mm=12.5,
        outer_profile_rz_mm=((0.2, 0), (3, 2), (3, 12.5)),
    )
    machine = own_ac_profile()
    started = time.perf_counter()
    trajectory = solve_xyzac_trajectory(combined, machine, tool_length_mm=nozzle.length_mm or 0)
    timings["xyzac_inverse_kinematics"] = time.perf_counter() - started
    started = time.perf_counter()
    motion = postprocess_indexed_gcode(
        combined,
        trajectory,
        machine,
        nozzle,
        header="FAN15 spherical NEU logo complete offline NC",
        marker_tag="F15L",
    )
    readback = readback_absolute_xyzac(
        motion, combined, trajectory, machine, nozzle, marker_tag="F15L"
    )
    if not readback.passed:
        raise RuntimeError(f"strict readback failed: {readback.to_json()}")
    pla = next(
        item
        for item in own_ac_document()["process_reference"]["materials"]
        if item["material"] == "PLA"
    )
    thermal = ThermalProgramParameters(pla["nozzle_c"], pla["standalone_bed_c"])
    code = wrap_thermal_program(motion, thermal)
    recovered_motion = unwrap_checked_thermal_program(code, thermal)
    if recovered_motion != motion:
        raise RuntimeError("thermal wrapper changed the checked motion program")
    wrapped_readback = readback_absolute_xyzac(
        recovered_motion, combined, trajectory, machine, nozzle, marker_tag="F15L"
    )
    if not wrapped_readback.passed:
        raise RuntimeError("wrapped NC did not survive strict readback")
    timings["postprocess_and_readback"] = time.perf_counter() - started

    actual, types = _independent_reconstruction(code, nozzle.length_mm or 0)
    expected = np.asarray([point.position for point in combined.points])
    errors = np.linalg.norm(actual - expected, axis=1)
    if len(actual) != len(expected) or float(errors.max()) >= 1.0e-4:
        raise RuntimeError("independent NC reconstruction failed")
    pairs = np.stack((actual[:-1], actual[1:]), axis=1)
    deposition = np.asarray([kind == "deposition" for kind in types[1:]])
    roles = np.asarray([point.extrusion_role for point in combined.points[1:]])
    np.savez_compressed(
        EVIDENCE / "nc_readback_paths.npz",
        deposition=pairs[deposition],
        travel=pairs[~deposition],
        skin=pairs[deposition & (roles == "skin")],
        infill=pairs[deposition & (roles == "infill")],
    )
    with gzip.open(EVIDENCE / "toolpath.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(combined.to_json(), stream)
    if TARGET.exists() and TARGET.read_text(encoding="utf-8") != code:
        raise RuntimeError(f"refusing to overwrite different NC: {TARGET}")
    TARGET.write_text(code, encoding="utf-8")
    role_counts = Counter(
        point.extrusion_role for point in combined.points if point.point_type == "deposition"
    )
    report = {
        "status": "offline_nc_readback_passed",
        "physical_machine_qualified": False,
        "source": str(SOURCE),
        "source_sha256": model.source_hash,
        "old_gcode": str(OLD),
        "old_gcode_sha256": _sha256(OLD),
        "output": str(TARGET),
        "output_sha256": _sha256(TARGET),
        "machine_profile": machine.profile_id,
        "machine_reference_only": machine.reference_only,
        "controller_rotary_words": dict(machine.rotary_axis_words),
        "feature_body_count": len(feature_ids),
        "base_points": len(base.points),
        "feature_points": len(feature.points),
        "combined_points": len(combined.points),
        "deposition_segment_roles": dict(role_counts),
        "fill_audit": {key: getattr(fill_audit, key) for key in fill_audit.__dataclass_fields__},
        "readback": wrapped_readback.to_json(),
        "independent_inverse_max_error_mm": float(errors.max()),
        "fk_position_max_error_mm": max(
            sample.fk_position_error_mm for sample in trajectory.samples
        ),
        "fk_orientation_max_error_rad": max(
            sample.fk_orientation_error_rad for sample in trajectory.samples
        ),
        "trajectory_issues": [issue.to_json() for issue in trajectory.issues],
        "thermal": {
            "material": "PLA",
            "nozzle_c": pla["nozzle_c"],
            "bed_c": pla["standalone_bed_c"],
        },
        "timings_s": timings,
        "acceptance": {
            "all_37_feature_bodies_present_in_all_3_layers": fill_audit.bodies_per_layer
            == (37, 37, 37),
            "maximum_cross_path_spacing_le_0_4_mm": fill_audit.maximum_cross_path_spacing_mm
            <= 0.4 + 1.0e-9,
            "first_feature_layer_touches_radius_40_substrate": abs(
                fill_audit.first_layer_root_gap_mm
            )
            <= 1.0e-8,
            "finite_width_volume_error_le_10_percent": fill_audit.relative_volume_error <= 0.10,
            "strict_complete_stream_readback": wrapped_readback.passed,
            "independent_inverse_le_0_0001_mm": float(errors.max()) < 1.0e-4,
        },
        "deferred": [
            "IPW collision qualification (user-deferred)",
            "physical axis calibration and dynamic limits",
            "controller-specific homing/probing/tool macros",
        ],
    }
    if not all(report["acceptance"].values()):
        raise RuntimeError(f"offline acceptance failed: {report['acceptance']}")
    (EVIDENCE / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": report["output"],
                "combined_points": report["combined_points"],
                "readback": report["readback"],
                "acceptance": report["acceptance"],
                "trajectory_issue_count": len(report["trajectory_issues"]),
                "timings_s": timings,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _independent_reconstruction(code: str, tool_length: float):
    points = []
    types = []
    pending = None
    for line in code.splitlines():
        if line.startswith("; F15L POINT "):
            pending = line.split()[-1]
        elif pending is not None and line.startswith("G1 "):
            values = {key: float(value) for key, value in WORDS.findall(line)}
            x, y, z = values["X"], values["Y"], values["Z"] - tool_length
            a, c = math.radians(values["A"]), math.radians(values["C"])
            intermediate = math.cos(a) * y + math.sin(a) * z
            points.append(
                (
                    math.cos(c) * x + math.sin(c) * intermediate,
                    -math.sin(c) * x + math.cos(c) * intermediate,
                    -math.sin(a) * y + math.cos(a) * z,
                )
            )
            types.append(pending)
            pending = None
    return np.asarray(points), tuple(types)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
