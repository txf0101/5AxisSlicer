from __future__ import annotations

import argparse
from pathlib import Path

from five_axis_slicer.core import MachineParameters, SliceParameters
from five_axis_slicer.gcode import generate_gcode
from five_axis_slicer.geometry import generate_demo_dome_mesh, load_mesh
from five_axis_slicer.hardware import open5x_freddi_hong_machine
from five_axis_slicer.slicer import ConformalSlicer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Five-axis hybrid slicer for Open5x-style rotary-bed printers")
    parser.add_argument("input", nargs="?", help="Path to an STL or STEP file")
    parser.add_argument("-o", "--output", help="Path to the exported G-code file")
    parser.add_argument("--demo", action="store_true", help="Use the built-in demo dome instead of loading a file")
    parser.add_argument("--headless", action="store_true", help="Run without opening the GUI")
    parser.add_argument("--layer-height", type=float, help="Override conformal layer height")
    parser.add_argument("--planar-layer-height", type=float, help="Override planar core layer height")
    parser.add_argument("--grid-step", type=float, help="Override surface sampling grid step")
    parser.add_argument("--core-top-z", "--transition-z", dest="core_top_z", type=float, help="Manual rotary core top Z (legacy alias: --transition-z)")
    parser.add_argument("--core-detection-percentile", "--transition-percentile", dest="core_detection_percentile", type=float, help="Percentile used when estimating the rotary core radius")
    parser.add_argument("--disable-planar-core", action="store_true", help="Disable the planar core phase")
    parser.add_argument("--u-sign", type=int, choices=(-1, 1), help="Machine U axis sign")
    parser.add_argument("--v-sign", type=int, choices=(-1, 1), help="Machine V axis sign")
    parser.add_argument("--u-zero", type=float, help="Machine U zero offset in degrees")
    parser.add_argument("--v-zero", type=float, help="Machine V zero offset in degrees")
    parser.add_argument("--min-u", type=float, help="Machine minimum U command angle")
    parser.add_argument("--max-u", type=float, help="Machine maximum U command angle")
    parser.add_argument("--min-v", type=float, help="Machine minimum V command angle")
    parser.add_argument("--max-v", type=float, help="Machine maximum V command angle")
    parser.add_argument("--phase-lift", type=float, help="Safe lift used when switching into five-axis mode")
    return parser


def apply_slice_overrides(params: SliceParameters, args: argparse.Namespace) -> SliceParameters:
    if args.layer_height is not None:
        params.layer_height_mm = args.layer_height
    if args.planar_layer_height is not None:
        params.planar_layer_height_mm = args.planar_layer_height
    if args.grid_step is not None:
        params.grid_step_mm = args.grid_step
    if args.core_top_z is not None:
        params.auto_core_transition = False
        params.core_transition_height_mm = args.core_top_z
    if args.core_detection_percentile is not None:
        params.core_transition_percentile = args.core_detection_percentile
    if args.disable_planar_core:
        params.enable_planar_core = False
    return params


def apply_machine_overrides(machine: MachineParameters, args: argparse.Namespace) -> MachineParameters:
    if args.u_sign is not None:
        machine.u_axis_sign = args.u_sign
    if args.v_sign is not None:
        machine.v_axis_sign = args.v_sign
    if args.u_zero is not None:
        machine.u_zero_offset_deg = args.u_zero
    if args.v_zero is not None:
        machine.v_zero_offset_deg = args.v_zero
    if args.min_u is not None:
        machine.min_u_deg = args.min_u
    if args.max_u is not None:
        machine.max_u_deg = args.max_u
    if args.min_v is not None:
        machine.min_v_deg = args.min_v
    if args.max_v is not None:
        machine.max_v_deg = args.max_v
    if args.phase_lift is not None:
        machine.phase_change_lift_mm = args.phase_lift
    return machine


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.headless and not args.input and not args.demo:
        from five_axis_slicer.gui import launch

        launch()
        return

    if args.demo:
        mesh = generate_demo_dome_mesh()
    elif args.input:
        mesh = load_mesh(args.input)
    else:
        raise SystemExit("Provide an input model or use --demo.")

    slice_params = apply_slice_overrides(SliceParameters(), args)
    machine_params = apply_machine_overrides(open5x_freddi_hong_machine(), args)
    slicer = ConformalSlicer()
    slice_result = slicer.slice(mesh, slice_params)
    gcode, warnings = generate_gcode(slice_result, slice_params, machine_params)

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")

    output_path = Path(args.output) if args.output else Path("five_axis_output.gcode")
    output_path.write_text(gcode, encoding="utf-8")
    print(f"Wrote G-code to {output_path.resolve()}")
    print(f"Paths: {len(slice_result.toolpaths)}")
    print(f"Core top Z: {slice_result.metadata.get('transition_height_mm', 0.0):.3f} mm")
    print(f"Machine profile: {machine_params.profile_name}")


if __name__ == "__main__":
    main()


