"""Stream the legacy fan NC with modal axes; do not infer blade fill from base tags."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

WORDS = re.compile(r"([A-Z])([-+]?(?:\d+(?:\.\d*)?|\.\d+))")


def audit(path: Path) -> dict:
    axes = dict.fromkeys("XYZAC", 0.0)
    absolute, relative_e, extrusion = True, False, 0.0
    counts, changes, radii = Counter(), Counter(), Counter()
    ranges, examples, modes = {}, [], Counter()
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for total, raw in enumerate(stream, 1):
            digest.update(raw)
            command = raw.decode("utf-8", errors="replace").split(";", 1)[0].strip()
            code = command.split(maxsplit=1)[0] if command else ""
            words = {key: float(value) for key, value in WORDS.findall(command)}
            if code in {"G90", "G91", "M82", "M83", "G20", "G21"}:
                modes[code] += 1
                if code == "G20":
                    raise ValueError(f"unsupported inch input at {total}")
                if code in {"G90", "G91"}:
                    absolute = code == "G90"
                if code in {"M82", "M83"}:
                    relative_e = code == "M83"
            if code == "G92":
                extrusion = words.get("E", extrusion)
                axes.update({key: words[key] for key in axes if key in words})
            if code not in {"G0", "G1"}:
                continue
            previous = axes.copy()
            axes.update(
                {k: v if absolute else previous[k] + v for k, v in words.items() if k in axes}
            )
            delta_e = words.get("E", 0.0) if relative_e else words.get("E", extrusion) - extrusion
            extrusion = extrusion + delta_e
            phase = "blade_a90" if abs(axes["A"] - 90.0) < 1e-6 else "other"
            counts[f"{phase}_moves"] += 1
            if delta_e <= 0 or axes == previous:
                continue
            counts[f"{phase}_positive_e_moves"] += 1
            if phase != "blade_a90":
                continue
            for key, value in axes.items():
                interval = ranges.setdefault(key, [value, value])
                interval[:] = [min(interval[0], value), max(interval[1], value)]
                changes[key] += abs(value - previous[key]) > 1e-7
            radii[round(axes["Z"], 3)] += 1
            if len(examples) < 12:
                examples.append({"line": total, "command": command})
    return {
        "source": str(path),
        "sha256": digest.hexdigest(),
        "lines": total,
        "modes": dict(modes),
        "counts": dict(counts),
        "blade_axis_bounds": ranges,
        "blade_deposition_axis_change_counts": dict(changes),
        "blade_machine_z_histogram": dict(sorted(radii.items())),
        "first_blade_moves": examples,
        "interpretation_boundary": "Machine Z is radial only after verifying AC centres and inverse order; positive E includes unretraction. No fill classification from inherited TYPE tags.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "blade_machine_z_histogram"},
            ensure_ascii=False,
            indent=2,
        )
    )
