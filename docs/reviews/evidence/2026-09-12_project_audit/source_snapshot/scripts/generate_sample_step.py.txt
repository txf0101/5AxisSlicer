from __future__ import annotations

import argparse
from pathlib import Path

import cadquery as cq


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a two-body STEP sample.")
    parser.add_argument("output", nargs="?", default="samples/two_boxes.step")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    assembly = cq.Assembly()
    assembly.add(cq.Workplane("XY").box(20, 20, 12), name="block_a")
    assembly.add(cq.Workplane("XY").box(14, 18, 18).translate((34, 0, 3)), name="block_b")
    assembly.save(str(output))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
