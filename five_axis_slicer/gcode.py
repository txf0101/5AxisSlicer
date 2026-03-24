"""G-code export for the hybrid slicer.

The exporter writes one continuous job. It prints the rotary core with U/V
locked first, then the five-axis conformal shell. The header comments stay
detailed so calibration runs are easier to read against machine behaviour.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from .core import MachineParameters, SliceParameters, SliceResult, Toolpath
from .kinematics import (
    apply_rotary_axis_calibration,
    machine_position_for_point,
    normal_to_rotary_angles,
)
from .open5x_adapter import solve_toolpath_raw_angles_open5x

# Toolpaths arrive here in model space. This file turns them into machine
# moves that can be run on a real printer.
# 切片器把模型空间里的路径交到这里，再由这里把它们整理成真实机器可执行的
# 运动指令。

_OPEN5X_SURFACE_START_TEMPLATE = (
    "; Open5x surface-finish export\n"
    "G90\n"
    "G0 {z_axis}{rotary_safe_z_mm:.3f}\n"
    "G92 E0\n"
    "{start_heat_gcode}\n"
    "G21\n"
    "G90\n"
    "M83"
)
_OPEN5X_SURFACE_END_TEMPLATE = "M400\nG92 E0\nM104 S0\nM140 S0"
_OPEN5X_SURFACE_PREFERRED_B_MIN_DEG = -95.0
_OPEN5X_SURFACE_PREFERRED_B_MAX_DEG = 180.0



@dataclass(slots=True)
class Pose:
    """Single machine pose used while exporting G-code.

    导出 G-code 时使用的单个位姿。

    It keeps both raw rotary angles and calibrated command angles so logs and
    debugging output can show what the geometry wanted and what the printer
    saw.
    它同时记着原始回转角和标定后的指令角，排查问题时就能分清几何上想要
    什么、机器上实际发了什么。
    """

    xyz: np.ndarray
    raw_u_deg: float
    raw_v_deg: float
    command_u_deg: float
    command_v_deg: float
    point: np.ndarray
    normal: np.ndarray


class _SafeTemplateDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def generate_gcode(
    result: SliceResult,
    slice_params: SliceParameters,
    machine_params: MachineParameters,
) -> tuple[str, list[str]]:
    """Convert the slice result into a runnable G-code program.

    把切片结果整理成可以直接执行的 G-code 程序。

    Travel moves, phase transitions, rotary solving, and extrusion all come
    together here.
    空移、阶段切换、回转求解和挤出计算都会在这里串成一条完整流程。
    """

    if _uses_open5x_surface_finish(result):
        return _generate_surface_finish_hybrid_gcode(result, slice_params, machine_params)

    export_machine = machine_params

    lines: list[str] = []
    warnings = list(result.warnings)

    _append_template(lines, export_machine.start_gcode_template, result, slice_params, export_machine)
    _append_extra_gcode(lines, slice_params.start_gcode)
    lines.extend(_machine_summary_comments(result, export_machine))

    previous_end_pose: Pose | None = None
    previous_raw_v_deg: float | None = None
    previous_commanded_u_deg: float | None = export_machine.home_u_deg
    previous_commanded_v_deg: float | None = export_machine.home_v_deg
    total_e = 0.0
    current_phase: str | None = None
    open5x_fallback_emitted = False
    export_toolpaths = preview_toolpaths(result, slice_params)

    for toolpath in export_toolpaths:
        phase_changed = toolpath.phase != current_phase
        if phase_changed:
            lines.append(_phase_comment(toolpath.phase))
            if current_phase == "planar" and toolpath.phase == "conformal":
                _append_template(lines, export_machine.phase_change_gcode_template, result, slice_params, export_machine)
            current_phase = toolpath.phase

        poses: list[Pose] = []
        min_u_cmd = math.inf
        max_u_cmd = -math.inf
        min_v_cmd = math.inf
        max_v_cmd = -math.inf
        raw_angle_pairs: list[tuple[float, float]] | None = None
        if toolpath.phase != "planar":
            try:
                raw_angle_pairs = solve_toolpath_raw_angles_open5x(
                    toolpath.points,
                    toolpath.normals,
                    export_machine,
                    previous_command_u_deg=previous_commanded_u_deg,
                    previous_command_v_deg=previous_commanded_v_deg,
                )
            except Exception as exc:
                if not open5x_fallback_emitted:
                    warnings.append(
                        "Open5x Python rotary solver failed for at least one conformal path; using built-in IK fallback. "
                        f"First error: {exc}"
                    )
                    open5x_fallback_emitted = True
                raw_angle_pairs = None

        if raw_angle_pairs is None:
            if toolpath.phase != "planar" and not open5x_fallback_emitted:
                warnings.append("Open5x Python rotary solver was unavailable; using built-in IK fallback.")
                open5x_fallback_emitted = True
            raw_angle_pairs = []
            local_previous_raw_v_deg = previous_raw_v_deg
            for normal in toolpath.normals:
                raw_u_deg, raw_v_deg = normal_to_rotary_angles(normal, previous_v_deg=local_previous_raw_v_deg)
                raw_angle_pairs.append((raw_u_deg, raw_v_deg))
                local_previous_raw_v_deg = raw_v_deg

        for (point, normal), (raw_u_deg, raw_v_deg) in zip(zip(toolpath.points, toolpath.normals), raw_angle_pairs, strict=True):
            command_u_deg, command_v_deg = apply_rotary_axis_calibration(
                raw_u_deg,
                raw_v_deg,
                export_machine,
                previous_commanded_v_deg=previous_commanded_v_deg,
            )
            previous_raw_v_deg = raw_v_deg
            previous_commanded_u_deg = command_u_deg
            previous_commanded_v_deg = command_v_deg
            min_u_cmd = min(min_u_cmd, command_u_deg)
            max_u_cmd = max(max_u_cmd, command_u_deg)
            min_v_cmd = min(min_v_cmd, command_v_deg)
            max_v_cmd = max(max_v_cmd, command_v_deg)
            xyz = machine_position_for_point(point, raw_u_deg, raw_v_deg, export_machine)
            poses.append(
                Pose(
                    xyz=xyz,
                    raw_u_deg=raw_u_deg,
                    raw_v_deg=raw_v_deg,
                    command_u_deg=command_u_deg,
                    command_v_deg=command_v_deg,
                    point=point,
                    normal=normal,
                )
            )

        if poses:
            min_u_cmd = min(pose.command_u_deg for pose in poses)
            max_u_cmd = max(pose.command_u_deg for pose in poses)
            min_v_cmd = min(pose.command_v_deg for pose in poses)
            max_v_cmd = max(pose.command_v_deg for pose in poses)

        # Conformal paths need rotary angles. Try the vendored Open5x solver
        # first, but keep the local solver ready so export can still finish.
        # 共形路径需要回转角。先试仓库里带的 Open5x 求解器，本地求解器也会
        # 随时兜底，导出流程不会因为它缺失而中断。
        if toolpath.phase != "planar":
            if min_u_cmd < export_machine.min_u_deg or max_u_cmd > export_machine.max_u_deg:
                warnings.append(
                    f"{toolpath.name}: {export_machine.u_axis_name} range [{min_u_cmd:.2f}, {max_u_cmd:.2f}] deg exceeds configured limit "
                    f"[{export_machine.min_u_deg:.2f}, {export_machine.max_u_deg:.2f}] deg."
                )
            if min_v_cmd < export_machine.min_v_deg or max_v_cmd > export_machine.max_v_deg:
                warnings.append(
                    f"{toolpath.name}: {export_machine.v_axis_name} range [{min_v_cmd:.2f}, {max_v_cmd:.2f}] deg exceeds configured limit "
                    f"[{export_machine.min_v_deg:.2f}, {export_machine.max_v_deg:.2f}] deg."
                )

        if len(poses) < 2:
            continue

        lift_height_mm = slice_params.travel_height_mm
        if phase_changed and previous_end_pose is not None and toolpath.phase == "conformal":
            lift_height_mm = max(lift_height_mm, export_machine.phase_change_lift_mm)

        travel_lines = build_travel_sequence(
            previous_end_pose,
            poses[0],
            slice_params,
            export_machine,
            lift_height_mm=lift_height_mm,
        )
        lines.extend(travel_lines)

        nominal_speed = toolpath_print_speed_mm_s(toolpath, slice_params)
        for current_pose, next_pose in zip(poses[:-1], poses[1:]):
            segment_length = float(np.linalg.norm(next_pose.point - current_pose.point))
            if segment_length < 1e-9:
                continue
            e_delta = extrusion_for_segment(segment_length, toolpath, slice_params)
            total_e += e_delta
            feed_mm_min = compensated_feed(current_pose, next_pose, segment_length, nominal_speed, export_machine)
            lines.append(format_move(next_pose, export_machine, feed_mm_min, e_delta))

        previous_end_pose = poses[-1]

    _append_extra_gcode(lines, slice_params.end_gcode)
    _append_template(lines, export_machine.end_gcode_template, result, slice_params, export_machine)
    lines.append(f"; Estimated extrusion: {total_e:.3f} mm of filament")
    return "\n".join(lines) + "\n", _deduplicate_warnings(warnings)


def _uses_open5x_surface_finish(result: SliceResult) -> bool:
    return str(result.metadata.get("conformal_strategy", "")) == "open5x-surface-finish"


def preview_toolpaths(result: SliceResult, slice_params: SliceParameters) -> list[Toolpath]:
    skirt_paths = _build_skirt_toolpaths(result, slice_params)
    if not skirt_paths:
        return list(result.toolpaths)
    return skirt_paths + list(result.toolpaths)


def _build_skirt_toolpaths(result: SliceResult, slice_params: SliceParameters) -> list[Toolpath]:
    if str(slice_params.adhesion_type) != "skirt":
        return []
    mesh = result.mesh
    if mesh.vertices.size == 0:
        return []

    z_height_mm = slice_params.resolved_planar_layer_height_mm()
    line_spacing = max(slice_params.resolved_planar_line_spacing_mm(), slice_params.nozzle_diameter_mm)
    base_margin_mm = max(slice_params.skirt_margin_mm, slice_params.nozzle_diameter_mm)
    min_x, min_y = mesh.bounds_min[:2]
    max_x, max_y = mesh.bounds_max[:2]
    skirt_paths: list[Toolpath] = []
    for line_index in range(max(int(slice_params.skirt_line_count), 1)):
        offset_mm = base_margin_mm + line_index * line_spacing
        points = np.asarray(
            [
                [min_x - offset_mm, min_y - offset_mm, z_height_mm],
                [max_x + offset_mm, min_y - offset_mm, z_height_mm],
                [max_x + offset_mm, max_y + offset_mm, z_height_mm],
                [min_x - offset_mm, max_y + offset_mm, z_height_mm],
                [min_x - offset_mm, min_y - offset_mm, z_height_mm],
            ],
            dtype=float,
        )
        normals = np.tile(np.array([[0.0, 0.0, 1.0]], dtype=float), (len(points), 1))
        skirt_paths.append(
            Toolpath(
                name=f"adhesion-skirt-{line_index + 1}",
                kind="adhesion-skirt",
                points=points,
                normals=normals,
                closed=True,
                phase="planar",
                layer_index=0,
                z_height_mm=z_height_mm,
            )
        )
    return skirt_paths


def _surface_finish_export_machine(machine_params: MachineParameters) -> MachineParameters:
    return replace(
        machine_params,
        start_gcode_template=_OPEN5X_SURFACE_START_TEMPLATE,
        phase_change_gcode_template="",
        end_gcode_template=_OPEN5X_SURFACE_END_TEMPLATE,
    )


def _generate_surface_finish_hybrid_gcode(
    result: SliceResult,
    slice_params: SliceParameters,
    machine_params: MachineParameters,
) -> tuple[str, list[str]]:
    """Export the Open5x hybrid program with a planar core and surface finish.

    导出“先打平面核心、再走曲面精加工”的 Open5x 混合程序。
    """

    planar_machine = machine_params
    surface_machine = _surface_finish_export_machine(machine_params)
    planar_toolpaths = [toolpath for toolpath in preview_toolpaths(result, slice_params) if toolpath.phase == "planar"]
    surface_toolpaths = [toolpath for toolpath in result.toolpaths if toolpath.kind == "conformal-surface-finish"]

    lines: list[str] = []
    warnings = list(result.warnings)
    total_e = 0.0

    if planar_toolpaths:
        _append_template(lines, planar_machine.start_gcode_template, result, slice_params, planar_machine)
        _append_extra_gcode(lines, slice_params.start_gcode)
        lines.extend(_machine_summary_comments(result, planar_machine))
        planar_lines, planar_extrusion = _emit_planar_phase(planar_toolpaths, slice_params, planar_machine)
        lines.extend(planar_lines)
        total_e += planar_extrusion

    for path_index, toolpath in enumerate(surface_toolpaths, start=1):
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("; START 5-axis G-code")
        lines.append("; Surface-finish segment exported as an independent five-axis block.")
        _append_template(lines, surface_machine.start_gcode_template, result, slice_params, surface_machine)

        poses, pose_warnings = _resolve_rotary_toolpath_poses(
            toolpath,
            surface_machine,
            previous_command_u_deg=surface_machine.home_u_deg,
            previous_command_v_deg=surface_machine.home_v_deg,
            previous_raw_v_deg=None,
            canonicalize_surface_finish=True,
        )
        warnings.extend(pose_warnings)
        if len(poses) < 2:
            continue

        segment_lift_mm = max(slice_params.travel_height_mm, surface_machine.phase_change_lift_mm, 10.0)
        segment_feed_mm_min = min(slice_params.travel_speed_mm_s * 60.0, 600.0)
        lines.extend(_surface_finish_segment_intro(poses[0], slice_params, surface_machine, segment_lift_mm, segment_feed_mm_min))

        nominal_speed = toolpath_print_speed_mm_s(toolpath, slice_params)
        for current_pose, next_pose in zip(poses[:-1], poses[1:]):
            segment_length = float(np.linalg.norm(next_pose.point - current_pose.point))
            if segment_length < 1e-9:
                continue
            e_delta = extrusion_for_segment(segment_length, toolpath, slice_params)
            total_e += e_delta
            feed_mm_min = compensated_feed(current_pose, next_pose, segment_length, nominal_speed, surface_machine)
            lines.append(format_move(next_pose, surface_machine, feed_mm_min, e_delta))

        lines.append(
            format_partial_rapid(
                surface_machine,
                segment_feed_mm_min,
                z=max(surface_machine.rotary_safe_z_mm, poses[-1].xyz[2] + segment_lift_mm),
            )
        )

    _append_extra_gcode(lines, slice_params.end_gcode)
    if surface_toolpaths:
        lines.append("G1 E-1.00000 F1200.0")
        _append_template(lines, surface_machine.end_gcode_template, result, slice_params, surface_machine)
    else:
        _append_template(lines, planar_machine.end_gcode_template, result, slice_params, planar_machine)
    lines.append(f"; Estimated extrusion: {total_e:.3f} mm of filament")
    return "\n".join(lines) + "\n", _deduplicate_warnings(warnings)


def _emit_planar_phase(
    toolpaths: list[Toolpath],
    slice_params: SliceParameters,
    machine_params: MachineParameters,
) -> tuple[list[str], float]:
    """Emit the G-code for the planar phase and return total extrusion.

    输出平面阶段的 G-code，并返回这一阶段的总挤出量。
    """

    lines: list[str] = []
    total_e = 0.0
    previous_end_pose: Pose | None = None
    current_phase: str | None = None

    for toolpath in toolpaths:
        phase_changed = toolpath.phase != current_phase
        if phase_changed:
            lines.append(_phase_comment(toolpath.phase))
            current_phase = toolpath.phase

        poses = _planar_toolpath_poses(toolpath, machine_params)
        if len(poses) < 2:
            continue

        travel_lines = build_travel_sequence(
            previous_end_pose,
            poses[0],
            slice_params,
            machine_params,
            lift_height_mm=slice_params.travel_height_mm,
        )
        lines.extend(travel_lines)

        nominal_speed = toolpath_print_speed_mm_s(toolpath, slice_params)
        for current_pose, next_pose in zip(poses[:-1], poses[1:]):
            segment_length = float(np.linalg.norm(next_pose.point - current_pose.point))
            if segment_length < 1e-9:
                continue
            e_delta = extrusion_for_segment(segment_length, toolpath, slice_params)
            total_e += e_delta
            feed_mm_min = compensated_feed(current_pose, next_pose, segment_length, nominal_speed, machine_params)
            lines.append(format_move(next_pose, machine_params, feed_mm_min, e_delta))

        previous_end_pose = poses[-1]

    return lines, total_e


def _planar_toolpath_poses(toolpath: Toolpath, machine_params: MachineParameters) -> list[Pose]:
    home_u_deg = machine_params.home_u_deg
    home_v_deg = machine_params.home_v_deg
    poses: list[Pose] = []
    for point in np.asarray(toolpath.points, dtype=float):
        point_xyz = np.asarray(point, dtype=float)
        poses.append(
            Pose(
                xyz=point_xyz.copy(),
                raw_u_deg=home_u_deg,
                raw_v_deg=home_v_deg,
                command_u_deg=home_u_deg,
                command_v_deg=home_v_deg,
                point=point_xyz.copy(),
                normal=np.array([0.0, 0.0, 1.0], dtype=float),
            )
        )
    return poses


def _resolve_rotary_toolpath_poses(
    toolpath: Toolpath,
    machine_params: MachineParameters,
    *,
    previous_command_u_deg: float | None,
    previous_command_v_deg: float | None,
    previous_raw_v_deg: float | None,
    canonicalize_surface_finish: bool,
) -> tuple[list[Pose], list[str]]:
    """Resolve every machine pose needed for one rotary toolpath.

    求解一条回转路径上每个采样点对应的机床位姿。
    """

    warnings: list[str] = []
    raw_angle_pairs: list[tuple[float, float]] | None = None

    try:
        raw_angle_pairs = solve_toolpath_raw_angles_open5x(
            toolpath.points,
            toolpath.normals,
            machine_params,
            previous_command_u_deg=previous_command_u_deg,
            previous_command_v_deg=previous_command_v_deg,
        )
    except Exception as exc:
        warnings.append(
            "Open5x Python rotary solver failed for at least one conformal path; using built-in IK fallback. "
            f"First error: {exc}"
        )
        raw_angle_pairs = None

    if raw_angle_pairs is None:
        warnings.append("Open5x Python rotary solver was unavailable; using built-in IK fallback.")
        raw_angle_pairs = []
        local_previous_raw_v_deg = previous_raw_v_deg
        for normal in toolpath.normals:
            raw_u_deg, raw_v_deg = normal_to_rotary_angles(normal, previous_v_deg=local_previous_raw_v_deg)
            raw_angle_pairs.append((raw_u_deg, raw_v_deg))
            local_previous_raw_v_deg = raw_v_deg

    poses: list[Pose] = []
    min_u_cmd = math.inf
    max_u_cmd = -math.inf
    min_v_cmd = math.inf
    max_v_cmd = -math.inf
    local_previous_command_v_deg = previous_command_v_deg

    # Turn each geometry-space sample into a fully calibrated machine pose.
    # 把几何空间里的每个采样点都换成带完整标定的机床位姿。
    for (point, normal), (raw_u_deg, raw_v_deg) in zip(zip(toolpath.points, toolpath.normals), raw_angle_pairs, strict=True):
        command_u_deg, command_v_deg = apply_rotary_axis_calibration(
            raw_u_deg,
            raw_v_deg,
            machine_params,
            previous_commanded_v_deg=local_previous_command_v_deg,
        )
        local_previous_command_v_deg = command_v_deg
        min_u_cmd = min(min_u_cmd, command_u_deg)
        max_u_cmd = max(max_u_cmd, command_u_deg)
        min_v_cmd = min(min_v_cmd, command_v_deg)
        max_v_cmd = max(max_v_cmd, command_v_deg)
        xyz = machine_position_for_point(point, raw_u_deg, raw_v_deg, machine_params)
        poses.append(
            Pose(
                xyz=xyz,
                raw_u_deg=raw_u_deg,
                raw_v_deg=raw_v_deg,
                command_u_deg=command_u_deg,
                command_v_deg=command_v_deg,
                point=point,
                normal=normal,
            )
        )

    if canonicalize_surface_finish and toolpath.kind == "conformal-surface-finish":
        poses = _canonicalize_surface_finish_b_branch(poses, machine_params)
        if poses:
            min_u_cmd = min(pose.command_u_deg for pose in poses)
            max_u_cmd = max(pose.command_u_deg for pose in poses)
            min_v_cmd = min(pose.command_v_deg for pose in poses)
            max_v_cmd = max(pose.command_v_deg for pose in poses)

    if poses:
        if min_u_cmd < machine_params.min_u_deg or max_u_cmd > machine_params.max_u_deg:
            warnings.append(
                f"{toolpath.name}: {machine_params.u_axis_name} range [{min_u_cmd:.2f}, {max_u_cmd:.2f}] deg exceeds configured limit "
                f"[{machine_params.min_u_deg:.2f}, {machine_params.max_u_deg:.2f}] deg."
            )
        if min_v_cmd < machine_params.min_v_deg or max_v_cmd > machine_params.max_v_deg:
            warnings.append(
                f"{toolpath.name}: {machine_params.v_axis_name} range [{min_v_cmd:.2f}, {max_v_cmd:.2f}] deg exceeds configured limit "
                f"[{machine_params.min_v_deg:.2f}, {machine_params.max_v_deg:.2f}] deg."
            )

    return poses, warnings


def _surface_finish_segment_intro(
    start_pose: Pose,
    slice_params: SliceParameters,
    machine_params: MachineParameters,
    lift_height_mm: float,
    feed_mm_min: float,
) -> list[str]:
    lines = ["G1 E0.10000 F300.0"]
    retract_mm = max(slice_params.retraction_mm, 1.0)
    lines.append(f"G1 E{-retract_mm:.5f} F{slice_params.retract_speed_mm_s * 60.0:.1f}")
    lines.append(
        format_partial_rapid(
            machine_params,
            feed_mm_min,
            z=max(machine_params.rotary_safe_z_mm, start_pose.xyz[2] + lift_height_mm),
        )
    )
    lines.append(
        format_partial_rapid(
            machine_params,
            feed_mm_min,
            u=start_pose.command_u_deg,
            v=start_pose.command_v_deg,
        )
    )
    lines.append(
        format_partial_rapid(
            machine_params,
            feed_mm_min,
            x=start_pose.xyz[0],
            y=start_pose.xyz[1],
        )
    )
    lines.append(f"G1 E{retract_mm + 0.1:.5f} F{slice_params.prime_speed_mm_s * 60.0:.1f}")
    lines.append(format_partial_rapid(machine_params, feed_mm_min, z=start_pose.xyz[2]))
    return lines


def _format_surface_positioning_move(
    pose: Pose,
    machine_params: MachineParameters,
    feed_mm_min: float,
    *,
    z_override: float | None = None,
) -> str:
    x_name, y_name, z_name = machine_params.linear_axis_names
    u_name, v_name = machine_params.rotary_axis_names
    z_value = pose.xyz[2] if z_override is None else float(z_override)
    return (
        f"G1 F{feed_mm_min:.1f} "
        f"{x_name}{pose.xyz[0]:.3f} {y_name}{pose.xyz[1]:.3f} {z_name}{z_value:.3f} "
        f"{u_name}{pose.command_u_deg:.3f} {v_name}{pose.command_v_deg:.3f} E0"
    )


def _canonicalize_surface_finish_b_branch(
    poses: list[Pose],
    machine_params: MachineParameters,
) -> list[Pose]:
    if not poses:
        return poses

    command_v = np.asarray([pose.command_v_deg for pose in poses], dtype=float)
    best_shift_deg = 0.0
    best_score = float("inf")

    for turn_count in range(-2, 3):
        shift_deg = float(turn_count) * 360.0
        shifted_v = command_v + shift_deg
        if shifted_v.min() < machine_params.min_v_deg - 1e-6 or shifted_v.max() > machine_params.max_v_deg + 1e-6:
            continue
        score = _surface_finish_b_shift_score(shifted_v, shift_deg)
        if score < best_score:
            best_score = score
            best_shift_deg = shift_deg

    if math.isclose(best_shift_deg, 0.0, abs_tol=1e-9):
        return poses

    return [
        replace(
            pose,
            raw_v_deg=pose.raw_v_deg + best_shift_deg,
            command_v_deg=pose.command_v_deg + best_shift_deg,
        )
        for pose in poses
    ]


def _surface_finish_b_shift_score(command_v_deg: np.ndarray, shift_deg: float) -> float:
    low_penalty = max(_OPEN5X_SURFACE_PREFERRED_B_MIN_DEG - float(command_v_deg.min()), 0.0)
    high_penalty = max(float(command_v_deg.max()) - _OPEN5X_SURFACE_PREFERRED_B_MAX_DEG, 0.0)
    mean_v_deg = float(np.mean(command_v_deg))
    wrapped_mean_deg = mean_v_deg % 360.0
    absolute_penalty = min(abs(mean_v_deg), abs(wrapped_mean_deg - 180.0))
    return (low_penalty + high_penalty) * 1000.0 + absolute_penalty + abs(shift_deg) * 0.01


def toolpath_print_speed_mm_s(toolpath: Toolpath, slice_params: SliceParameters) -> float:
    if toolpath.phase == "planar":
        return slice_params.planar_print_speed_mm_s
    return slice_params.print_speed_mm_s


def toolpath_layer_height_mm(toolpath: Toolpath, slice_params: SliceParameters) -> float:
    if toolpath.phase == "planar":
        return slice_params.resolved_planar_layer_height_mm()
    return slice_params.layer_height_mm


def toolpath_line_width_mm(toolpath: Toolpath, slice_params: SliceParameters) -> float:
    if toolpath.phase == "planar":
        return max(slice_params.resolved_planar_line_spacing_mm(), slice_params.nozzle_diameter_mm)
    return max(slice_params.line_spacing_mm, slice_params.nozzle_diameter_mm)


def build_travel_sequence(
    previous_end_pose: Pose | None,
    next_start_pose: Pose,
    slice_params: SliceParameters,
    machine_params: MachineParameters,
    lift_height_mm: float,
) -> list[str]:
    """Build a safe travel sequence between two poses.
    在两个位姿之间拼出一段安全的空移序列。
    The sequence can include retract, lift, rapid travel, and re-prime steps.
    这段序列会按情况插入回抽、抬升、快速移动和补料。
    """

    lines: list[str] = []
    rapid_feed = slice_params.travel_speed_mm_s * 60.0

    if previous_end_pose is None:
        safe_z = _absolute_rotary_safe_z(None, next_start_pose, lift_height_mm, machine_params)
        lines.append(format_partial_rapid(machine_params, rapid_feed, z=safe_z))
        lines.append(
            format_partial_rapid(
                machine_params,
                rapid_feed,
                u=next_start_pose.command_u_deg,
                v=next_start_pose.command_v_deg,
            )
        )
        lines.append(
            format_partial_rapid(
                machine_params,
                rapid_feed,
                x=next_start_pose.xyz[0],
                y=next_start_pose.xyz[1],
            )
        )
        lines.append(format_partial_rapid(machine_params, rapid_feed, z=next_start_pose.xyz[2]))
        return lines

    if slice_params.retraction_mm > 0.0:
        lines.append(f"G1 E{-slice_params.retraction_mm:.5f} F{slice_params.retract_speed_mm_s * 60.0:.1f}")

    if _needs_absolute_rotary_safe_z(previous_end_pose, next_start_pose, machine_params):
        safe_z = _absolute_rotary_safe_z(previous_end_pose, next_start_pose, lift_height_mm, machine_params)
        lines.append(format_partial_rapid(machine_params, rapid_feed, z=safe_z))
        lines.append(
            format_partial_rapid(
                machine_params,
                rapid_feed,
                u=next_start_pose.command_u_deg,
                v=next_start_pose.command_v_deg,
            )
        )
        lines.append(
            format_partial_rapid(
                machine_params,
                rapid_feed,
                x=next_start_pose.xyz[0],
                y=next_start_pose.xyz[1],
            )
        )
        lines.append(format_partial_rapid(machine_params, rapid_feed, z=next_start_pose.xyz[2]))
    else:
        safe_prev = _lifted_pose(previous_end_pose, lift_height_mm, machine_params)
        safe_next = _lifted_pose(next_start_pose, lift_height_mm, machine_params)
        lines.append(format_rapid(safe_prev, machine_params, rapid_feed))
        lines.append(format_rapid(safe_next, machine_params, rapid_feed))
        lines.append(format_rapid(next_start_pose, machine_params, rapid_feed))

    if slice_params.retraction_mm > 0.0:
        lines.append(f"G1 E{slice_params.retraction_mm:.5f} F{slice_params.prime_speed_mm_s * 60.0:.1f}")

    return lines


def _lifted_pose(base_pose: Pose, height_mm: float, machine_params: MachineParameters) -> Pose:
    lifted_point = base_pose.point + base_pose.normal * height_mm
    lifted_xyz = machine_position_for_point(lifted_point, base_pose.raw_u_deg, base_pose.raw_v_deg, machine_params)
    return Pose(
        xyz=lifted_xyz,
        raw_u_deg=base_pose.raw_u_deg,
        raw_v_deg=base_pose.raw_v_deg,
        command_u_deg=base_pose.command_u_deg,
        command_v_deg=base_pose.command_v_deg,
        point=lifted_point,
        normal=base_pose.normal,
    )


def extrusion_for_segment(segment_length_mm: float, toolpath: Toolpath, slice_params: SliceParameters) -> float:
    """Estimate the filament needed for one printed segment.
    估算一段打印路径需要多少丝材挤出。
    """

    line_width = toolpath_line_width_mm(toolpath, slice_params)
    layer_height = toolpath_layer_height_mm(toolpath, slice_params)
    volume = line_width * layer_height * segment_length_mm * slice_params.extrusion_multiplier
    filament_area = math.pi * (slice_params.filament_diameter_mm * 0.5) ** 2
    return volume / max(filament_area, 1e-9)


def compensated_feed(
    current: Pose,
    nxt: Pose,
    segment_length_mm: float,
    nominal_speed_mm_s: float,
    machine_params: MachineParameters,
) -> float:
    """Scale nominal feed so rotary motion stays inside machine feed limits.

    调整标称进给速度，让带回转的运动也别超过机床的进给能力。
    """

    delta_xyz = float(np.linalg.norm(nxt.xyz - current.xyz))
    delta_u_mm = math.radians(abs(nxt.command_u_deg - current.command_u_deg)) * machine_params.rotary_scale_radius_mm
    delta_v_mm = math.radians(abs(nxt.command_v_deg - current.command_v_deg)) * machine_params.rotary_scale_radius_mm
    machine_distance = math.sqrt(delta_xyz**2 + delta_u_mm**2 + delta_v_mm**2)
    ratio = machine_distance / max(segment_length_mm, 1e-6)
    nominal = nominal_speed_mm_s * 60.0
    compensated = nominal * max(ratio, 0.1)
    return min(compensated, machine_params.max_feed_mm_min)


def format_move(pose: Pose, machine_params: MachineParameters, feed_mm_min: float, e_delta: float) -> str:
    """Format one coordinated printing move.
    格式化一条联动打印指令。
    """

    x_name, y_name, z_name = machine_params.linear_axis_names
    u_name, v_name = machine_params.rotary_axis_names
    return (
        f"G1 {x_name}{pose.xyz[0]:.3f} {y_name}{pose.xyz[1]:.3f} {z_name}{pose.xyz[2]:.3f} "
        f"{u_name}{pose.command_u_deg:.3f} {v_name}{pose.command_v_deg:.3f} E{e_delta:.5f} F{feed_mm_min:.1f}"
    )


def format_rapid(pose: Pose, machine_params: MachineParameters, feed_mm_min: float) -> str:
    """Format one coordinated rapid move without extrusion.
    格式化一条不带挤出的联动快速移动指令。
    """

    x_name, y_name, z_name = machine_params.linear_axis_names
    u_name, v_name = machine_params.rotary_axis_names
    return (
        f"G0 {x_name}{pose.xyz[0]:.3f} {y_name}{pose.xyz[1]:.3f} {z_name}{pose.xyz[2]:.3f} "
        f"{u_name}{pose.command_u_deg:.3f} {v_name}{pose.command_v_deg:.3f} F{feed_mm_min:.1f}"
    )


def format_partial_rapid(
    machine_params: MachineParameters,
    feed_mm_min: float,
    *,
    x: float | None = None,
    y: float | None = None,
    z: float | None = None,
    u: float | None = None,
    v: float | None = None,
) -> str:
    x_name, y_name, z_name = machine_params.linear_axis_names
    u_name, v_name = machine_params.rotary_axis_names
    tokens = ["G0"]
    if x is not None:
        tokens.append(f"{x_name}{float(x):.3f}")
    if y is not None:
        tokens.append(f"{y_name}{float(y):.3f}")
    if z is not None:
        tokens.append(f"{z_name}{float(z):.3f}")
    if u is not None:
        tokens.append(f"{u_name}{float(u):.3f}")
    if v is not None:
        tokens.append(f"{v_name}{float(v):.3f}")
    tokens.append(f"F{feed_mm_min:.1f}")
    return " ".join(tokens)


def _needs_absolute_rotary_safe_z(
    previous_end_pose: Pose | None,
    next_start_pose: Pose,
    machine_params: MachineParameters,
) -> bool:
    if previous_end_pose is None:
        return True
    rotary_delta_deg = max(
        abs(next_start_pose.command_u_deg - previous_end_pose.command_u_deg),
        abs(next_start_pose.command_v_deg - previous_end_pose.command_v_deg),
    )
    return rotary_delta_deg >= machine_params.rotary_safe_reposition_trigger_deg


def _absolute_rotary_safe_z(
    previous_end_pose: Pose | None,
    next_start_pose: Pose,
    lift_height_mm: float,
    machine_params: MachineParameters,
) -> float:
    safe_z = max(machine_params.rotary_safe_z_mm, next_start_pose.xyz[2] + lift_height_mm)
    if previous_end_pose is not None:
        safe_z = max(safe_z, previous_end_pose.xyz[2] + lift_height_mm)
    return safe_z


def _phase_comment(phase: str) -> str:
    if phase == "planar":
        return "; --- Begin planar core / substrate phase ---"
    if phase == "conformal":
        return "; --- Switch to five-axis conformal phase ---"
    return f"; --- Begin {phase} phase ---"


def _append_extra_gcode(lines: list[str], snippet: str) -> None:
    for line in snippet.splitlines():
        if line.strip():
            lines.append(line.rstrip())


def _append_template(
    lines: list[str],
    template: str,
    result: SliceResult,
    slice_params: SliceParameters,
    machine_params: MachineParameters,
) -> None:
    context = _template_context(result, slice_params, machine_params)
    rendered = template.format_map(_SafeTemplateDict(context))
    for line in rendered.splitlines():
        if line.strip():
            lines.append(line.rstrip())


def _template_context(
    result: SliceResult,
    slice_params: SliceParameters,
    machine_params: MachineParameters,
) -> dict[str, float | int | str]:
    x_axis, y_axis, z_axis = machine_params.linear_axis_names
    return {
        "profile_name": machine_params.profile_name,
        "profile_description": machine_params.profile_description,
        "x_axis": x_axis,
        "y_axis": y_axis,
        "z_axis": z_axis,
        "u_axis": machine_params.u_axis_name,
        "v_axis": machine_params.v_axis_name,
        "u_axis_name": machine_params.u_axis_name,
        "v_axis_name": machine_params.v_axis_name,
        "home_u_deg": machine_params.home_u_deg,
        "home_v_deg": machine_params.home_v_deg,
        "phase_change_lift_mm": machine_params.phase_change_lift_mm,
        "rotary_safe_z_mm": machine_params.rotary_safe_z_mm,
        "rotary_safe_reposition_trigger_deg": machine_params.rotary_safe_reposition_trigger_deg,
        "travel_feed_mm_min": slice_params.travel_speed_mm_s * 60.0,
        "travel_height_mm": slice_params.travel_height_mm,
        "nozzle_temperature_c": slice_params.nozzle_temperature_c,
        "bed_temperature_c": slice_params.bed_temperature_c,
        "start_heat_gcode": _start_heat_gcode(slice_params),
        "shutdown_heat_gcode": _shutdown_heat_gcode(),
        "adhesion_type": slice_params.adhesion_type,
        "skirt_line_count": slice_params.skirt_line_count,
        "skirt_margin_mm": slice_params.skirt_margin_mm,
        "transition_height_mm": float(result.metadata.get("transition_height_mm", 0.0)),
        "core_center_x_mm": float(result.metadata.get("core_center_x_mm", 0.0)),
        "core_center_y_mm": float(result.metadata.get("core_center_y_mm", 0.0)),
        "core_min_z_mm": float(result.metadata.get("core_min_z_mm", 0.0)),
        "core_max_z_mm": float(result.metadata.get("core_max_z_mm", 0.0)),
        "core_max_radius_mm": float(result.metadata.get("core_max_radius_mm", 0.0)),
        "bed_diameter_mm": machine_params.bed_diameter_mm,
    }


def _machine_summary_comments(result: SliceResult, machine_params: MachineParameters) -> list[str]:
    """Build the detailed header comments for slice and machine state.

    生成文件开头那段详细摘要注释，把切片结果和机床状态交代清楚。
    """

    transition_height = float(result.metadata.get("transition_height_mm", 0.0))
    core_center_x = float(result.metadata.get("core_center_x_mm", 0.0))
    core_center_y = float(result.metadata.get("core_center_y_mm", 0.0))
    core_min_z = float(result.metadata.get("core_min_z_mm", 0.0))
    core_max_z = float(result.metadata.get("core_max_z_mm", 0.0))
    core_max_radius = float(result.metadata.get("core_max_radius_mm", 0.0))
    return [
        f"; Strategy: print rotary core first with fixed {machine_params.u_axis_name}/{machine_params.v_axis_name}, then print the five-axis conformal shell.",
        "; Travel moves are inserted between disconnected patches so blade-to-blade jumps do not extrude.",
        f"; Profile description: {machine_params.profile_description}",
        f"; Rotary centre (mm): X={machine_params.rotary_center_x_mm:.3f} Y={machine_params.rotary_center_y_mm:.3f} Z={machine_params.rotary_center_z_mm:.3f}",
        f"; Build offset (mm): X={machine_params.x_offset_mm:.3f} Y={machine_params.y_offset_mm:.3f} Z={machine_params.z_offset_mm:.3f}",
        f"; Detected core centre (mm): X={core_center_x:.3f} Y={core_center_y:.3f}",
        f"; Detected core Z range (mm): [{core_min_z:.3f}, {core_max_z:.3f}]",
        f"; Detected core max radius (mm): {core_max_radius:.3f}",
        f"; {machine_params.u_axis_name} command = {machine_params.u_axis_sign:+d} * U_math + {machine_params.u_zero_offset_deg:.3f} deg",
        f"; {machine_params.v_axis_name} command = {machine_params.v_axis_sign:+d} * V_math + {machine_params.v_zero_offset_deg:.3f} deg",
        f"; {machine_params.u_axis_name} limit range: [{machine_params.min_u_deg:.3f}, {machine_params.max_u_deg:.3f}] deg",
        f"; {machine_params.v_axis_name} limit range: [{machine_params.min_v_deg:.3f}, {machine_params.max_v_deg:.3f}] deg",
        f"; Safe absolute Z before large rotary reposition: {machine_params.rotary_safe_z_mm:.3f} mm",
        f"; Rotary safe-Z trigger: {machine_params.rotary_safe_reposition_trigger_deg:.3f} deg",
        f"; Rotary core top Z / conformal handoff: {transition_height:.3f} mm",
    ]


def _start_heat_gcode(slice_params: SliceParameters) -> str:
    lines: list[str] = []
    if slice_params.bed_temperature_c > 0.0:
        lines.append(f"M140 S{slice_params.bed_temperature_c:.0f}")
        if slice_params.wait_for_bed:
            lines.append(f"M190 S{slice_params.bed_temperature_c:.0f}")
    if slice_params.nozzle_temperature_c > 0.0:
        lines.append(f"M104 S{slice_params.nozzle_temperature_c:.0f}")
        if slice_params.wait_for_nozzle:
            lines.append(f"M109 S{slice_params.nozzle_temperature_c:.0f}")
    return "\n".join(lines)


def _shutdown_heat_gcode() -> str:
    return "M104 S0\nM140 S0"


def _deduplicate_warnings(warnings: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        deduped.append(warning)
    return deduped
