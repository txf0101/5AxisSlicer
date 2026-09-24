"""Offline-only self-owned AC dialect with relative E and material macros."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, Callable

from ..kinematics.xyzac import MachineAxisTrajectory
from ..manufacturing.controller_profile import ControllerProfile
from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.machine import MachineProfile
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.toolpath import GeneratedToolpath, ToolpathEvent
from .tool_change_service import ToolChangeServicePlan, plan_tool_change_service
from .gcode_contract import filament_area_mm2, marker_identifier

_WORD = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))")


@dataclass(frozen=True, slots=True)
class OwnACReadbackReport:
    expected_points: int
    read_points: int
    expected_events: int
    read_events: int
    issues: tuple[str, ...]
    machine_executable: bool

    @property
    def passed(self) -> bool:
        return (
            not self.issues
            and self.expected_points == self.read_points
            and self.expected_events == self.read_events
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "passed": self.passed,
            "expected_points": self.expected_points,
            "read_points": self.read_points,
            "expected_events": self.expected_events,
            "read_events": self.read_events,
            "machine_executable": self.machine_executable,
            "issues": list(self.issues),
        }


def postprocess_own_ac(
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    controller: ControllerProfile,
    *,
    marker_tag: str = "PAC",
    checkpoint: Callable[[], None] | None = None,
    service_plan: ToolChangeServicePlan | None = None,
    T_workpiece_from_build: RigidTransform | None = None,
) -> str:
    if trajectory.source_toolpath_id != toolpath.toolpath_id:
        raise ValueError("trajectory source does not match toolpath")
    if trajectory.machine_profile_id != machine.profile_id:
        raise ValueError("trajectory machine does not match")
    if controller.machine_profile_id != machine.profile_id:
        raise ValueError("controller profile does not match machine")
    if len(toolpath.points) != len(trajectory.samples):
        raise ValueError("toolpath and trajectory point counts differ")
    machine.validate()
    marker_identifier(marker_tag)
    if service_plan is None:
        service_plan = plan_tool_change_service(
            toolpath, trajectory, machine, nozzle, controller,
            T_workpiece_from_build=T_workpiece_from_build,
        )
    area = filament_area_mm2(nozzle)
    events = _own_events_by_sequence(toolpath)
    lines = [
        "; 5AxisSclicer paper-core AC offline review program",
        "; CONTROLLER_PROFILE "
        + json.dumps(controller.to_json(), sort_keys=True, separators=(",", ":")),
        f"; TOOL_LENGTH_MM {trajectory.tool_length_mm:.6f}",
        "; EXECUTION_QUALIFICATION "
        + (
            "machine_executable"
            if controller.machine_executable and not service_plan.moves_before_event
            else "offline_only"
        ),
        "G21 ; millimetres",
        "G90 ; absolute machine axes",
        "M83 ; relative extrusion",
        "G94 ; units per minute",
        "G92 E0 ; explicit extrusion origin",
    ]
    axis_encoder = _validated_axis_encoder(machine)
    for index, (point, sample) in enumerate(zip(toolpath.points, trajectory.samples, strict=True)):
        if checkpoint is not None and index % 512 == 0:
            checkpoint()
        _emit_events(
            lines, events.get(index, ()), controller, marker_tag, point.feedrate_mm_min or 1.0,
            axis_encoder, service_plan,
        )
        axes = axis_encoder(sample.joint_positions)
        axis_words = " ".join(f"{name}{value:.6f}" for name, value in sorted(axes.items()))
        e_word = ""
        if point.point_type == "deposition":
            e_word = f" E{point.material_volume_mm3 / area:.12f}"
        material = "-" if point.material_id is None else point.material_id
        channel = "-" if point.channel_id is None else point.channel_id
        lines.append(
            f"; {marker_tag} POINT {index + 1} {point.point_id} {point.point_type} {material} {channel}"
        )
        lines.append(f"G1 {axis_words}{e_word} F{(point.feedrate_mm_min or 1.0):.6f}")
    _emit_events(
        lines, events.get(len(toolpath.points), ()), controller, marker_tag, 1.0,
        axis_encoder, service_plan,
    )
    lines.extend(
        (
            "G90 ; restore absolute axes",
            "M83 ; restore relative extrusion",
            "G94 ; restore units per minute",
            "M400",
            "M2",
        )
    )
    return "\n".join(lines) + "\n"


def _validated_axis_encoder(machine):
    joints = tuple(machine.joints)

    def encode(positions):
        result = {}
        for joint in joints:
            if joint.joint_id not in positions:
                continue
            axis = joint.post_axis_map
            if axis is None:
                raise ValueError(f"joint has no controller mapping: {joint.joint_id}")
            value = joint.effective_position(positions[joint.joint_id])
            result[axis.word] = axis.encode(value, joint.joint_type)
        return result

    return encode


def _emit_events(lines, events, controller, marker_tag, feed, axis_encoder, service_plan):
    for event in events:
        payload = json.dumps(dict(event.context), sort_keys=True, separators=(",", ":"))
        lines.append(f"; {marker_tag} EVENT {event.event_id} {event.event_type}")
        lines.append(f"; {marker_tag} EVENT_CONTEXT {payload}")
        for move in service_plan.moves_before_event.get(event.event_id, ()):
            axes = axis_encoder(move.joints)
            words = " ".join(f"{name}{value:.6f}" for name, value in sorted(axes.items()))
            lines.append(f"; {marker_tag} SERVICE {move.label}")
            lines.append(f"G1 {words} F{move.feedrate_mm_min:.6f}")
        kind = event.event_type
        value = float(event.context.get("extrusion_length_mm", 0.0))
        if kind == "prepare_pause":
            lines.append("M0 ; operator material preparation")
        elif kind in {"retract", "unload", "load", "purge", "prime"}:
            event_feed = float(event.context.get("feedrate_mm_min", feed))
            lines.append(f"G1 E{value:.12f} F{event_feed:.6f}")
        elif kind == "cut":
            assert controller.tool_change_station is not None
            lines.append(controller.tool_change_station.cutter_command)
        elif kind == "park":
            continue
        elif kind == "switch":
            lines.append(str(event.context["tool_command"]))
        elif kind == "temperature_wait":
            lines.append(f"M109 S{float(event.context['target_temperature_c']):.3f}")
        elif kind == "resume":
            continue
        elif kind == "index_start":
            continue
        elif kind in {"index_end", "operation_change", "safe_depart", "safe_approach", "finish"}:
            continue
        else:
            raise ValueError(f"unsupported own AC event: {kind}")


def readback_own_ac(
    gcode: str,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    controller: ControllerProfile,
    *,
    tolerance: float = 1.0e-4,
    marker_tag: str = "PAC",
    checkpoint: Callable[[], None] | None = None,
    service_plan: ToolChangeServicePlan | None = None,
    T_workpiece_from_build: RigidTransform | None = None,
) -> OwnACReadbackReport:
    """Strictly verify modes, marker order, XYZAC/F, relative E and macro balance."""

    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("tolerance must be finite and non-negative")
    machine.validate()
    if checkpoint is not None:
        checkpoint()
    if service_plan is None:
        service_plan = plan_tool_change_service(
            toolpath, trajectory, machine, nozzle, controller,
            T_workpiece_from_build=T_workpiece_from_build,
        )
    lines = gcode.splitlines()
    command_lines = [
        line.partition(";")[0].strip() for line in lines if line.partition(";")[0].strip()
    ]
    issues = _command_stream_issues(
        command_lines,
        toolpath,
        trajectory,
        machine,
        nozzle,
        controller,
        marker_tag,
        checkpoint,
        service_plan,
    )
    point_markers, event_markers = _markers(lines, marker_tag, checkpoint)
    expected_events = _expected_events(toolpath)
    if [(parts[0], parts[1]) for parts in event_markers] != [
        (event.event_id, event.event_type) for event in expected_events
    ]:
        issues.append("event_order_mismatch")
    issues.extend(
        _point_readback_issues(
            lines,
            point_markers,
            toolpath,
            trajectory,
            _validated_axis_encoder(machine),
            nozzle,
            tolerance,
            checkpoint,
        )
    )
    return OwnACReadbackReport(
        len(toolpath.points),
        len(point_markers),
        len(expected_events),
        len(event_markers),
        tuple(dict.fromkeys(issues)),
        controller.machine_executable and not bool(service_plan.moves_before_event),
    )


def _command_stream_issues(
    command_lines, toolpath, trajectory, machine, nozzle, controller, marker_tag, checkpoint,
    service_plan,
):
    issues = []
    required_prefix = ["G21", "G90", "M83", "G94", "G92 E0"]
    if command_lines[:5] != required_prefix:
        issues.append("mode_header_mismatch")
    if command_lines[-5:] != ["G90", "M83", "G94", "M400", "M2"]:
        issues.append("mode_footer_mismatch")
    if controller.extrusion_mode == "relative" and any(line == "M82" for line in command_lines):
        issues.append("unexpected_absolute_extrusion")
    expected_commands = [
        line.partition(";")[0].strip()
        for line in postprocess_own_ac(
            toolpath, trajectory, machine, nozzle, controller,
            marker_tag=marker_tag, checkpoint=checkpoint,
            service_plan=service_plan,
        ).splitlines()
        if line.partition(";")[0].strip()
    ]
    if command_lines != expected_commands:
        issues.append("command_stream_mismatch")
    return issues


def _markers(lines, marker_tag, checkpoint=None):
    point_markers = []
    event_markers = []
    for index, line in enumerate(lines):
        if checkpoint is not None and index % 4096 == 0:
            checkpoint()
        prefix = f"; {marker_tag} POINT "
        if line.startswith(prefix):
            point_markers.append((index, line[len(prefix) :].split()))
        event_prefix = f"; {marker_tag} EVENT "
        if line.startswith(event_prefix) and not line.startswith(f"; {marker_tag} EVENT_CONTEXT"):
            event_markers.append(line[len(event_prefix) :].split())
    return point_markers, event_markers


def _expected_events(toolpath):
    grouped_events = _own_events_by_sequence(toolpath)
    return [event for sequence in sorted(grouped_events) for event in grouped_events[sequence]]


def _point_readback_issues(
    lines, point_markers, toolpath, trajectory, axis_encoder, nozzle, tolerance, checkpoint=None
):
    issues = []
    area = filament_area_mm2(nozzle)
    if len(point_markers) != len(toolpath.points):
        issues.append("point_count_mismatch")
    for ordinal, ((line_index, fields), point, sample) in enumerate(
        zip(point_markers, toolpath.points, trajectory.samples), start=1
    ):
        if checkpoint is not None and ordinal % 512 == 1:
            checkpoint()
        issues.extend(
            _point_issues(
                lines,
                line_index,
                fields,
                ordinal,
                point,
                sample,
                axis_encoder,
                area,
                tolerance,
            )
        )
    return issues


def _point_issues(lines, line_index, fields, ordinal, point, sample, axis_encoder, area, tolerance):
    material = "-" if point.material_id is None else point.material_id
    channel = "-" if point.channel_id is None else point.channel_id
    if fields != [str(ordinal), point.point_id, point.point_type, material, channel]:
        return [f"{point.point_id}:marker"]
    cursor = line_index + 1
    while cursor < len(lines) and not lines[cursor].partition(";")[0].strip():
        cursor += 1
    if cursor >= len(lines):
        return [f"{point.point_id}:missing_motion"]
    words = _parse_g1(lines[cursor].partition(";")[0].strip())
    if words is None:
        return [f"{point.point_id}:invalid_motion"]
    issues = _axis_issues(words, point, sample, axis_encoder, tolerance)
    issues.extend(_process_word_issues(words, point, area, tolerance))
    return issues


def _process_word_issues(words, point, area, tolerance):
    issues = []
    expected_e = point.material_volume_mm3 / area if point.point_type == "deposition" else None
    if expected_e is None and "E" in words:
        issues.append(f"{point.point_id}:unexpected_e")
    if expected_e is not None and (
        "E" not in words or abs(words["E"] - expected_e) > max(tolerance, abs(expected_e) * 1e-9)
    ):
        issues.append(f"{point.point_id}:E")
    expected_feed = point.feedrate_mm_min or 1.0
    if "F" not in words or abs(words["F"] - expected_feed) > tolerance:
        issues.append(f"{point.point_id}:F")
    return issues


def _axis_issues(words, point, sample, axis_encoder, tolerance):
    expected_axes = axis_encoder(sample.joint_positions)
    return [
        f"{point.point_id}:{name}"
        for name, value in expected_axes.items()
        if name not in words or abs(words[name] - value) > tolerance
    ]


def _parse_g1(line: str) -> dict[str, float] | None:
    tokens = line.upper().split()
    if not tokens or tokens[0] != "G1":
        return None
    words: dict[str, float] = {}
    for token in tokens[1:]:
        match = _WORD.fullmatch(token)
        if match is None or match.group(1) in words:
            return None
        words[match.group(1)] = float(match.group(2))
    return words


def _own_events_by_sequence(toolpath: GeneratedToolpath) -> dict[int, list[ToolpathEvent]]:
    result: dict[int, list[ToolpathEvent]] = {}
    count = len(toolpath.points)
    for event in toolpath.events:
        sequence = event.context.get(
            "sequence_index", count if event.event_type == "finish" else None
        )
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or not 0 <= sequence <= count
        ):
            raise ValueError(f"{event.event_id}: invalid sequence_index")
        result.setdefault(sequence, []).append(event)
    return result


__all__ = ["OwnACReadbackReport", "postprocess_own_ac", "readback_own_ac"]
