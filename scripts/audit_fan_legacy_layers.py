"""Modal, chronological blade runs from the untouched old NC (no TYPE inference)."""

from collections import Counter
import json
from pathlib import Path

from audit_fan_rotary_motion import WORDS

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "example/扇叶/风扇扇叶完整新.gcode"
OUT = ROOT / "docs/reviews/evidence/2026-09-20_fan_complete_program/radial_repair_full"


def main():
    axes = dict.fromkeys("XYZAC", 0.0)
    absolute, relative_e, extrusion = True, False, 0.0
    run = None
    runs = []
    phase = 1
    previous_radius = None
    steps = Counter()
    with SOURCE.open(encoding="utf8") as stream:
        for number, line in enumerate(stream, 1):
            command = line.split(";", 1)[0].strip()
            code = command.split(maxsplit=1)[0] if command else ""
            words = {k: float(v) for k, v in WORDS.findall(command)}
            if code in {"G90", "G91"}:
                absolute = code == "G90"
            if code in {"M82", "M83"}:
                relative_e = code == "M83"
            if code == "G20":
                raise ValueError("inch input unsupported")
            if code == "G92":
                extrusion = words.get("E", extrusion)
                axes.update({k: words[k] for k in axes if k in words})
            if code not in {"G0", "G1"}:
                continue
            old = axes.copy()
            axes.update({k: v if absolute else old[k] + v for k, v in words.items() if k in axes})
            de = words.get("E", 0.0) if relative_e else words.get("E", extrusion) - extrusion
            extrusion += de
            depositing = de > 0 and abs(axes["A"] - 90) < 1e-6 and axes != old
            radius = round(axes["Z"], 3)
            if not depositing or (run and radius != run["radius_mm"]):
                if run:
                    runs.append(run)
                run = None
            if not depositing:
                continue
            if previous_radius is not None and radius != previous_radius:
                steps[round(radius - previous_radius, 3)] += 1
                if radius < previous_radius - 5:
                    phase += 1
            previous_radius = radius
            if run is None:
                run = {
                    "phase": phase,
                    "radius_mm": radius,
                    "first_line": number,
                    "last_line": number,
                    "count": 0,
                    "C_start": axes["C"],
                    "C_end": axes["C"],
                    "C_min": axes["C"],
                    "C_max": axes["C"],
                    "Y_min": axes["Y"],
                    "Y_max": axes["Y"],
                    "C_direction_reversals": 0,
                    "last_C_direction": 0,
                }
            delta = axes["C"] - old["C"]
            direction = 1 if delta > 1e-7 else -1 if delta < -1e-7 else 0
            if direction and run["last_C_direction"] and direction != run["last_C_direction"]:
                run["C_direction_reversals"] += 1
            if direction:
                run["last_C_direction"] = direction
            run.update(
                last_line=number,
                count=run["count"] + 1,
                C_end=axes["C"],
                C_min=min(run["C_min"], axes["C"]),
                C_max=max(run["C_max"], axes["C"]),
                Y_min=min(run["Y_min"], axes["Y"]),
                Y_max=max(run["Y_max"], axes["Y"]),
            )
    if run:
        runs.append(run)
    result = {
        "source": str(SOURCE),
        "radial_resets_detected": phase - 1,
        "runs": runs,
        "radial_step_histogram": dict(sorted(steps.items())),
        "interpretation": "Constant machine-Z extrusion runs; phase boundaries inferred only from >5 mm positive-extrusion radius resets. Not automatic wall/infill labels.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "legacy_layer_runs.json").write_text(json.dumps(result, indent=2), encoding="utf8")
    print(
        json.dumps(
            {"runs": len(runs), "phases": phase, "steps": dict(steps), "first_runs": runs[:4]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
