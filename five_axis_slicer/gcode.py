"""G-code export for the hybrid slicer.

The exporter writes one continuous job: first the rotary core with U/V
locked, then the five-axis conformal shell. The summary comments near the top
of the file are intentionally verbose so a student can match machine behaviour
with the software settings during calibration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .core import MachineParameters, SliceParameters, SliceResult, Toolpath
from .kinematics import (
    apply_rotary_axis_calibration,
    machine_position_for_point,
    normal_to_rotary_angles,
    shortest_angular_delta_deg,
)


@dataclass(slots=True)
class Pose:
    """Single machine pose used during export."""

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
    """Convert the hybrid slice result into one continuous G-code program.

    The important contract is that path boundaries become travel moves, not
    extrusion moves. That is what lets separate blade faces stay separate in the
    final program instead of being connected by false deposited lines.
    """

    lines: list[str] = []
    warnings = list(result.warnings)

    _append_template(lines, machine_params.start_gcode_template, result, slice_params, machine_params)
    _append_extra_gcode(lines, slice_params.start_gcode)
    lines.extend(_machine_summary_comments(result, machine_params))

    previous_end_pose: Pose | None = None
    previous_raw_v_deg: float | None = None
    previous_commanded_v_deg: float | None = machine_params.home_v_deg
    total_e = 0.0
    current_phase: str | None = None

    for toolpath in result.toolpaths:
        phase_changed = toolpath.phase != current_phase
        if phase_changed:
            lines.append(_phase_comment(toolpath.phase))
            if current_phase == "planar" and toolpath.phase == "conformal":
                _append_template(lines, machine_params.phase_change_gcode_template, result, slice_params, machine_params)
            current_phase = toolpath.phase

        poses: list[Pose] = []
        min_u_cmd = math.inf
        max_u_cmd = -math.inf
        min_v_cmd = math.inf
        max_v_cmd = -math.inf
        for point, normal in zip(toolpath.points, toolpath.normals):
            raw_u_deg, raw_v_deg = normal_to_rotary_angles(normal, previous_v_deg=previous_raw_v_deg)
            command_u_deg, command_v_deg = apply_rotary_axis_calibration(
                raw_u_deg,
                raw_v_deg,
                machine_params,
                previous_commanded_v_deg=previous_commanded_v_deg,
            )
            previous_raw_v_deg = raw_v_deg
            previous_commanded_v_deg = command_v_deg
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

        if toolpath.phase != "planar":
            if min_u_cmd < machine_params.min_u_deg or max_u_cmd > machine_params.max_u_deg:
                warnings.append(
                    f"{toolpath.name}: U range [{min_u_cmd:.2f}, {max_u_cmd:.2f}] deg exceeds configured limit "
                    f"[{machine_params.min_u_deg:.2f}, {machine_params.max_u_deg:.2f}] deg."
                )
            if min_v_cmd < machine_params.min_v_deg or max_v_cmd > machine_params.max_v_deg:
                warnings.append(
                    f"{toolpath.name}: V range [{min_v_cmd:.2f}, {max_v_cmd:.2f}] deg exceeds configured limit "
                    f"[{machine_params.min_v_deg:.2f}, {machine_params.max_v_deg:.2f}] deg."
                )

        if len(poses) < 2:
            continue

        lift_height_mm = slice_params.travel_height_mm
        if phase_changed and previous_end_pose is not None and toolpath.phase == "conformal":
            lift_height_mm = max(lift_height_mm, machine_params.phase_change_lift_mm)

        travel_lines = build_travel_sequence(
            previous_end_pose,
            poses[0],
            slice_params,
            machine_params,
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
            feed_mm_min = compensated_feed(current_pose, next_pose, segment_length, nominal_speed, machine_params)
            lines.append(format_move(next_pose, machine_params, feed_mm_min, e_delta))

        previous_end_pose = poses[-1]

    _append_extra_gcode(lines, slice_params.end_gcode)
    _append_template(lines, machine_params.end_gcode_template, result, slice_params, machine_params)
    lines.append(f"; Estimated extrusion: {total_e:.3f} mm of filament")
    return "\n".join(lines) + "\n", _deduplicate_warnings(warnings)


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
    lines: list[str] = []
    rapid_feed = slice_params.travel_speed_mm_s * 60.0

    if previous_end_pose is None:
        safe_start = _lifted_pose(next_start_pose, lift_height_mm, machine_params)
        lines.append(format_rapid(safe_start, machine_params, rapid_feed))
        lines.append(format_rapid(next_start_pose, machine_params, rapid_feed))
        return lines

    if slice_params.retraction_mm > 0.0:
        lines.append(f"G1 E{-slice_params.retraction_mm:.5f} F{slice_params.retract_speed_mm_s * 60.0:.1f}")

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
    delta_xyz = float(np.linalg.norm(nxt.xyz - current.xyz))
    delta_u_mm = math.radians(abs(nxt.command_u_deg - current.command_u_deg)) * machine_params.rotary_scale_radius_mm
    delta_v_mm = math.radians(abs(shortest_angular_delta_deg(nxt.command_v_deg, current.command_v_deg))) * machine_params.rotary_scale_radius_mm
    machine_distance = math.sqrt(delta_xyz**2 + delta_u_mm**2 + delta_v_mm**2)
    ratio = machine_distance / max(segment_length_mm, 1e-6)
    nominal = nominal_speed_mm_s * 60.0
    compensated = nominal * max(ratio, 0.1)
    return min(compensated, machine_params.max_feed_mm_min)


def format_move(pose: Pose, machine_params: MachineParameters, feed_mm_min: float, e_delta: float) -> str:
    x_name, y_name, z_name = machine_params.linear_axis_names
    u_name, v_name = machine_params.rotary_axis_names
    return (
        f"G1 {x_name}{pose.xyz[0]:.3f} {y_name}{pose.xyz[1]:.3f} {z_name}{pose.xyz[2]:.3f} "
        f"{u_name}{pose.command_u_deg:.3f} {v_name}{pose.command_v_deg:.3f} E{e_delta:.5f} F{feed_mm_min:.1f}"
    )


def format_rapid(pose: Pose, machine_params: MachineParameters, feed_mm_min: float) -> str:
    x_name, y_name, z_name = machine_params.linear_axis_names
    u_name, v_name = machine_params.rotary_axis_names
    return (
        f"G0 {x_name}{pose.xyz[0]:.3f} {y_name}{pose.xyz[1]:.3f} {z_name}{pose.xyz[2]:.3f} "
        f"{u_name}{pose.command_u_deg:.3f} {v_name}{pose.command_v_deg:.3f} F{feed_mm_min:.1f}"
    )


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
    return {
        "profile_name": machine_params.profile_name,
        "profile_description": machine_params.profile_description,
        "u_axis": machine_params.u_axis_name,
        "v_axis": machine_params.v_axis_name,
        "u_axis_name": machine_params.u_axis_name,
        "v_axis_name": machine_params.v_axis_name,
        "home_u_deg": machine_params.home_u_deg,
        "home_v_deg": machine_params.home_v_deg,
        "phase_change_lift_mm": machine_params.phase_change_lift_mm,
        "travel_feed_mm_min": slice_params.travel_speed_mm_s * 60.0,
        "travel_height_mm": slice_params.travel_height_mm,
        "transition_height_mm": float(result.metadata.get("transition_height_mm", 0.0)),
        "core_center_x_mm": float(result.metadata.get("core_center_x_mm", 0.0)),
        "core_center_y_mm": float(result.metadata.get("core_center_y_mm", 0.0)),
        "core_min_z_mm": float(result.metadata.get("core_min_z_mm", 0.0)),
        "core_max_z_mm": float(result.metadata.get("core_max_z_mm", 0.0)),
        "core_max_radius_mm": float(result.metadata.get("core_max_radius_mm", 0.0)),
        "bed_diameter_mm": machine_params.bed_diameter_mm,
    }


def _machine_summary_comments(result: SliceResult, machine_params: MachineParameters) -> list[str]:
    transition_height = float(result.metadata.get("transition_height_mm", 0.0))
    core_center_x = float(result.metadata.get("core_center_x_mm", 0.0))
    core_center_y = float(result.metadata.get("core_center_y_mm", 0.0))
    core_min_z = float(result.metadata.get("core_min_z_mm", 0.0))
    core_max_z = float(result.metadata.get("core_max_z_mm", 0.0))
    core_max_radius = float(result.metadata.get("core_max_radius_mm", 0.0))
    return [
        "; Strategy: print rotary core first with fixed U/V, then print the five-axis conformal shell.",
        "; Travel moves are inserted between disconnected patches so blade-to-blade jumps do not extrude.",
        f"; Profile description: {machine_params.profile_description}",
        f"; Rotary centre (mm): X={machine_params.rotary_center_x_mm:.3f} Y={machine_params.rotary_center_y_mm:.3f} Z={machine_params.rotary_center_z_mm:.3f}",
        f"; Build offset (mm): X={machine_params.x_offset_mm:.3f} Y={machine_params.y_offset_mm:.3f} Z={machine_params.z_offset_mm:.3f}",
        f"; Detected core centre (mm): X={core_center_x:.3f} Y={core_center_y:.3f}",
        f"; Detected core Z range (mm): [{core_min_z:.3f}, {core_max_z:.3f}]",
        f"; Detected core max radius (mm): {core_max_radius:.3f}",
        f"; U command = {machine_params.u_axis_sign:+d} * U_math + {machine_params.u_zero_offset_deg:.3f} deg",
        f"; V command = {machine_params.v_axis_sign:+d} * V_math + {machine_params.v_zero_offset_deg:.3f} deg",
        f"; U limit range: [{machine_params.min_u_deg:.3f}, {machine_params.max_u_deg:.3f}] deg",
        f"; V limit range: [{machine_params.min_v_deg:.3f}, {machine_params.max_v_deg:.3f}] deg",
        f"; Rotary core top Z / conformal handoff: {transition_height:.3f} mm",
    ]


def _deduplicate_warnings(warnings: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        deduped.append(warning)
    return deduped


