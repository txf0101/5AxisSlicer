"""Command-line entry points for the five-axis slicer.

五轴切片器的命令行入口。

The CLI maps arguments onto the same slicer, machine, and export objects used
by the GUI, so batch runs and interactive runs still share one pipeline.
命令行参数最后会落到和 GUI 共用的切片、机床、导出对象上，批处理和交互式
运行走的是同一条流程。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from five_axis_slicer.core import MachineParameters, SliceParameters, SliceSelection
from five_axis_slicer.gcode import generate_gcode
from five_axis_slicer.geometry import generate_demo_dome_mesh, load_mesh
from five_axis_slicer.hardware import open5x_freddi_hong_machine
from five_axis_slicer.slicer import ConformalSlicer, slice_planar_model


def _normalize_axis_name(value: str | None, fallback: str) -> str:
    text = str(value or "").strip().upper()
    for character in text:
        if character.isalpha():
            return character
    return fallback


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser used by ``main()``.

    构建 ``main()`` 使用的命令行解析器。
    """

    parser = argparse.ArgumentParser(description="Five-axis hybrid slicer for Open5x-style rotary-bed printers")
    parser.add_argument("input", nargs="?", help="Path to an STL or STEP file")
    parser.add_argument("-o", "--output", help="Path to the exported G-code file")
    parser.add_argument("--demo", action="store_true", help="Use the built-in demo dome instead of loading a file")
    parser.add_argument("--headless", action="store_true", help="Run without opening the GUI")
    parser.add_argument("--slice-mode", choices=("hybrid", "planar"), default="hybrid", help="Choose the hybrid five-axis workflow or a pure planar three-axis slice")
    parser.add_argument("--layer-height", type=float, help="Override conformal layer height")
    parser.add_argument("--planar-layer-height", type=float, help="Override planar core layer height")
    parser.add_argument("--grid-step", type=float, help="Override surface sampling grid step")
    parser.add_argument("--nozzle-temp", type=float, help="Override nozzle temperature used by the default templates")
    parser.add_argument("--bed-temp", type=float, help="Override bed temperature used by the default templates")
    parser.add_argument("--no-wait-nozzle", action="store_true", help="Use M104 without waiting for nozzle temperature")
    parser.add_argument("--no-wait-bed", action="store_true", help="Use M140 without waiting for bed temperature")
    parser.add_argument("--adhesion-type", choices=("none", "skirt"), help="Build-plate adhesion helper to emit before the main print")
    parser.add_argument("--skirt-lines", type=int, help="Number of skirt loops when --adhesion-type skirt is used")
    parser.add_argument("--skirt-margin", type=float, help="Skirt distance from the model outline in mm")
    parser.add_argument("--core-top-z", "--transition-z", dest="core_top_z", type=float, help="Manual rotary core top Z (legacy alias: --transition-z)")
    parser.add_argument("--core-detection-percentile", "--transition-percentile", dest="core_detection_percentile", type=float, help="Percentile used when estimating the rotary core radius")
    parser.add_argument("--disable-planar-core", action="store_true", help="Disable the planar core phase")
    parser.add_argument("--substrate-component", type=int, help="Connected component index used as the planar substrate geometry")
    parser.add_argument("--conformal-components", help="Comma-separated component indices used for conformal printing")
    parser.add_argument("--u-name", help="Command letter/name for the first rotary axis")
    parser.add_argument("--v-name", help="Command letter/name for the second rotary axis")
    parser.add_argument("--u-sign", type=int, choices=(-1, 1), help="Machine U axis sign")
    parser.add_argument("--v-sign", type=int, choices=(-1, 1), help="Machine V axis sign")
    parser.add_argument("--u-zero", type=float, help="Machine U zero offset in degrees")
    parser.add_argument("--v-zero", type=float, help="Machine V zero offset in degrees")
    parser.add_argument("--min-u", type=float, help="Machine minimum U command angle")
    parser.add_argument("--max-u", type=float, help="Machine maximum U command angle")
    parser.add_argument("--min-v", type=float, help="Machine minimum V command angle")
    parser.add_argument("--max-v", type=float, help="Machine maximum V command angle")
    parser.add_argument("--rotary-safe-z", type=float, help="Absolute safe Z used before large rotary repositioning")
    parser.add_argument("--rotary-safe-trigger", type=float, help="Rotary angle delta threshold that triggers the safe Z sequence")
    parser.add_argument("--phase-lift", type=float, help="Safe lift used when switching into five-axis mode")
    return parser


def apply_slice_overrides(params: SliceParameters, args: argparse.Namespace) -> SliceParameters:
    """Apply CLI overrides onto slicer process settings.

    把命令行里的切片参数覆盖到当前工艺设置上。
    """

    if args.layer_height is not None:
        params.layer_height_mm = args.layer_height
    if args.planar_layer_height is not None:
        params.planar_layer_height_mm = args.planar_layer_height
    if args.grid_step is not None:
        params.grid_step_mm = args.grid_step
    if args.nozzle_temp is not None:
        params.nozzle_temperature_c = args.nozzle_temp
    if args.bed_temp is not None:
        params.bed_temperature_c = args.bed_temp
    if args.no_wait_nozzle:
        params.wait_for_nozzle = False
    if args.no_wait_bed:
        params.wait_for_bed = False
    if args.adhesion_type is not None:
        params.adhesion_type = args.adhesion_type
    if args.skirt_lines is not None:
        params.skirt_line_count = max(args.skirt_lines, 1)
    if args.skirt_margin is not None:
        params.skirt_margin_mm = max(args.skirt_margin, 0.5)
    if args.core_top_z is not None:
        params.auto_core_transition = False
        params.core_transition_height_mm = args.core_top_z
    if args.core_detection_percentile is not None:
        params.core_transition_percentile = args.core_detection_percentile
    if args.disable_planar_core:
        params.enable_planar_core = False
    return params


def apply_machine_overrides(machine: MachineParameters, args: argparse.Namespace) -> MachineParameters:
    """Apply CLI calibration overrides onto a machine profile.

    把命令行里的机床标定覆盖到当前机床预设上。
    """

    if args.u_name is not None or args.v_name is not None:
        machine.rotary_axis_names = (
            _normalize_axis_name(args.u_name, machine.u_axis_name),
            _normalize_axis_name(args.v_name, machine.v_axis_name),
        )
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
    if args.rotary_safe_z is not None:
        machine.rotary_safe_z_mm = args.rotary_safe_z
    if args.rotary_safe_trigger is not None:
        machine.rotary_safe_reposition_trigger_deg = args.rotary_safe_trigger
    if args.phase_lift is not None:
        machine.phase_change_lift_mm = args.phase_lift
    return machine


def build_slice_selection(args: argparse.Namespace) -> SliceSelection | None:
    """Translate component-selection CLI flags into a selection object.

    把组件选择相关的命令行参数整理成 ``SliceSelection``。
    """

    substrate_index = args.substrate_component
    conformal_indices: tuple[int, ...] = ()
    if args.conformal_components:
        parsed = []
        for token in args.conformal_components.split(","):
            token = token.strip()
            if not token:
                continue
            parsed.append(int(token))
        conformal_indices = tuple(parsed)
    if substrate_index is None and not conformal_indices:
        return None
    return SliceSelection(substrate_component_index=substrate_index, conformal_component_indices=conformal_indices)


def main() -> None:
    """Run the CLI workflow or launch the GUI when no headless input is given.

    在给出命令行输入时运行 CLI 流程，否则启动 GUI。
    """

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
    slice_selection = build_slice_selection(args)
    if args.slice_mode == "planar":
        slice_result = slice_planar_model(mesh, slice_params)
    else:
        slicer = ConformalSlicer()
        slice_result = slicer.slice(mesh, slice_params, selection=slice_selection)

    gcode, warnings = generate_gcode(slice_result, slice_params, machine_params)

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")

    output_path = Path(args.output) if args.output else Path("five_axis_output.gcode")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(gcode, encoding="utf-8")
    print(f"Wrote G-code to {output_path.resolve()}")
    print(f"Paths: {len(slice_result.toolpaths)}")
    print(f"Core top Z: {slice_result.metadata.get('transition_height_mm', 0.0):.3f} mm")
    print(f"Machine profile: {machine_params.profile_name}")


if __name__ == "__main__":
    main()
