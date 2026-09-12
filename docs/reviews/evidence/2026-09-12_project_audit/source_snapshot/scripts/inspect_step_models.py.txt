from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from five_axis_slicer.geometry_vtk import shape_to_polydata
from five_axis_slicer.step_loader import StepLoadError, load_step


def find_step_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".step", ".stp"}
    )


def inspect_file(path: Path, mesh: bool) -> dict:
    started = time.perf_counter()
    try:
        model = load_step(path)
        load_seconds = time.perf_counter() - started
        mesh_seconds = None
        triangle_count = None
        if mesh:
            mesh_started = time.perf_counter()
            triangle_count = 0
            for body in model.bodies:
                polydata = shape_to_polydata(model.shapes[body.body_id])
                triangle_count += polydata.GetNumberOfPolys()
            mesh_seconds = time.perf_counter() - mesh_started
        return {
            "path": str(path),
            "ok": True,
            "load_seconds": round(load_seconds, 3),
            "mesh_seconds": None if mesh_seconds is None else round(mesh_seconds, 3),
            "body_count": len(model.bodies),
            "edge_count": len(model.edges),
            "triangle_count": triangle_count,
            "sha256": model.source_hash,
        }
    except StepLoadError as exc:
        return {
            "path": str(path),
            "ok": False,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "path": str(path),
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect STEP/STP files with the project loader.")
    parser.add_argument("root", help="File or directory to inspect")
    parser.add_argument("--mesh", action="store_true", help="Also run VTK meshing conversion")
    parser.add_argument("--out", default="", help="Optional JSON output path")
    args = parser.parse_args()

    target = Path(args.root).resolve()
    files = [target] if target.is_file() else find_step_files(target)
    results = [inspect_file(path, args.mesh) for path in files]
    payload = {"root": str(target), "count": len(results), "results": results}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        output = Path(args.out).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
