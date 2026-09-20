"""Collect completed diagnostics without upgrading their qualification."""

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/reviews/evidence/2026-09-20_fan15_examples"
CASES = {
    "pipe2": "pipe2",
    "hemisphere_pattern": "球形NEU校徽",
    "three_leaf": "三叶扇",
    "impeller": "叶轮",
}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    results = {}
    for case, directory in CASES.items():
        folder = OUT / case

        def read(name):
            return json.loads((folder / name).read_text(encoding="utf-8"))

        result = {
            "inventory": read("inventory.json"),
            "legacy": read("legacy.json"),
            "current_modes": read("current_mode.json"),
            "planar": read("planar_diagnostic.json"),
            "comparison": read("comparison.json"),
            "manufacturing_accepted": False,
            "new_complete_nc_generated": False,
        }
        results[case] = result
        destination = ROOT / "example" / directory / "FAN15_审查结果_20260920"
        destination.mkdir(exist_ok=True)
        shutil.copy2(folder / "comparison.png", destination / "comparison.png")
        (destination / "audit.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    scripts = [
        ROOT / "scripts" / name
        for name in (
            "fan15_example_audit.py",
            "render_fan15_examples.py",
            "finalize_fan15_evidence.py",
        )
    ]
    scripts.extend(sorted((ROOT / "src/five_axis_slicer").rglob("*.py")))
    scripts.append(ROOT / "tests/test_fan15_audit.py")
    scripts.append(ROOT / "docs/reviews/2026-09-20_fan15_example_acceptance.md")
    manifest = {
        "schema_version": 1,
        "stage": "FAN15",
        "accepted": False,
        "scope": "four-example geometry and legacy diagnostic; NOT complete manufacturing programs",
        "results": results,
        "source_hashes": {str(p.relative_to(ROOT)): digest(p) for p in scripts},
        "files": {
            str(p.relative_to(OUT)): digest(p)
            for p in sorted(OUT.rglob("*"))
            if p.is_file() and p.name != "manifest.json"
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                case: {
                    "old_segments": v["legacy"]["positive_e_segments"],
                    "requested_heights": v["planar"]["requested_layers"],
                    "failed_heights": len(v["planar"]["failures"]),
                    "new_diagnostic_segments": v["planar"]["deposition_segments"],
                }
                for case, v in results.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
