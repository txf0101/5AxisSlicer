"""Record evidence hashes and the intentionally incomplete release qualification."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/reviews/evidence/2026-09-20_fan_complete_program/radial_repair_full"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    sources = list((ROOT / "src/five_axis_slicer/algorithms/fan").glob("*.py")) + [
        ROOT / "src/five_axis_slicer/postprocessing/fan_merge.py",
        ROOT / "scripts/probe_fan_radial_layers.py",
        ROOT / "scripts/generate_fan_radial_assembly.py",
        ROOT / "scripts/render_fan_radial_cached.py",
        ROOT / "tests/test_fan_radial.py",
        ROOT / "tests/test_fan_stages.py",
    ]
    evidence = [p for p in OUT.iterdir() if p.is_file() and p.name != "manifest.json"]
    payload = {
        "python": sys.executable,
        "machine_executable": False,
        "full_new_nc_generated": False,
        "FAN08_FAN09_FAN10_accepted": False,
        "scope": "Complete CAD-derived deposition candidates; partial transition/merge implementation",
        "tests": "33 related tests passed; latest affected 6 tests passed after merge changes",
        "quality": "check_quality.py passed: Ruff, formatting, context budget, mypy 173 source files",
        "pending": [
            "actual bead coverage and layer support",
            "radial Toolpath and safe links",
            "full machine/nozzle/fixture swept collision",
            "full fan NC readback and thermal start/end",
        ],
        "sha256": {p.relative_to(ROOT).as_posix(): digest(p) for p in sources + evidence},
    }
    (OUT / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf8")
    print("Recorded", len(payload["sha256"]), "file hashes; not qualified for printing")


if __name__ == "__main__":
    main()
