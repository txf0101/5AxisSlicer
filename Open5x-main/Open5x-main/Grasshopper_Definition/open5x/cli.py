from __future__ import annotations

import argparse
from pathlib import Path

from .demo import build_demo_project
from .pipeline import build_gcode_program
from .rhino_io import inspect_3dm, polyline_to_radial_spec
from .spec import load_project_spec, write_project_spec


def _cmd_demo(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    project = build_demo_project(turns=args.turns, samples=args.samples)
    spec_path = output_dir / "demo_spec.json"
    gcode_path = output_dir / "demo_output.gcode"
    write_project_spec(project, spec_path)
    result = build_gcode_program(project)
    gcode_path.write_text(result.gcode, encoding="utf-8")
    print(f"Wrote demo spec to {spec_path}")
    print(f"Wrote demo G-code to {gcode_path} ({result.line_count} lines)")
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    spec = load_project_spec(args.spec)
    result = build_gcode_program(spec)
    Path(args.output).write_text(result.gcode, encoding="utf-8")
    print(f"Wrote {result.line_count} G-code lines to {args.output}")
    return 0


def _cmd_inspect_3dm(args: argparse.Namespace) -> int:
    info = inspect_3dm(args.input)
    print(f"Objects: {info['object_count']}")
    print("Types:")
    for name, count in info["type_counts"].items():
        print(f"  {name}: {count}")
    print("Layers:")
    for layer in info["layers"]:
        print(f"  {layer}")
    return 0


def _cmd_from_3dm_polyline(args: argparse.Namespace) -> int:
    payload = polyline_to_radial_spec(args.input, layer_name=args.layer)
    project = build_demo_project()
    project.name = payload["name"]
    project.comment = "Polyline curve imported from 3DM with radial normals placeholder."
    project.paths = []
    from .models import PathSpec
    from .vector_math import as_array_2d

    project.paths.append(
        PathSpec(
            name=payload["name"],
            points_mm=as_array_2d(payload["points"], 3),
            normals=as_array_2d(payload["normals"], 3),
            extrude=payload["extrude"],
            closed=payload["closed"],
        )
    )
    write_project_spec(project, args.output)
    print(f"Wrote JSON spec to {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open5x Python port")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser("demo", help="Generate a runnable demo spec and G-code")
    demo_parser.add_argument("--output-dir", default="outputs", help="Directory for generated demo files")
    demo_parser.add_argument("--turns", type=int, default=2)
    demo_parser.add_argument("--samples", type=int, default=72)
    demo_parser.set_defaults(func=_cmd_demo)

    build_parser = subparsers.add_parser("build", help="Build G-code from a JSON project spec")
    build_parser.add_argument("spec", help="JSON project spec")
    build_parser.add_argument("output", help="Output G-code path")
    build_parser.set_defaults(func=_cmd_build)

    inspect_parser = subparsers.add_parser("inspect-3dm", help="Inspect the content of a Rhino .3dm file")
    inspect_parser.add_argument("input", help="Input 3DM path")
    inspect_parser.set_defaults(func=_cmd_inspect_3dm)

    import_parser = subparsers.add_parser(
        "from-3dm-polyline",
        help="Create a JSON spec from the first polyline curve in a .3dm file",
    )
    import_parser.add_argument("input", help="Input 3DM path")
    import_parser.add_argument("output", help="Output JSON path")
    import_parser.add_argument("--layer", help="Optional layer filter")
    import_parser.set_defaults(func=_cmd_from_3dm_polyline)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
