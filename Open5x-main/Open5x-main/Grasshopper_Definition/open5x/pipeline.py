from __future__ import annotations

from dataclasses import dataclass

from .extrusion import extrusion_for_segment
from .feedrate import compensated_feed_mm_min, effective_move_distance_mm
from .gcode import GCodeBuilder
from .kinematics import solve_path_poses
from .models import Pose, ProjectSpec
from .vector_math import segment_lengths


@dataclass(slots=True)
class BuildResult:
    gcode: str
    line_count: int


def _travel_with_retraction(builder: GCodeBuilder, previous_pose: Pose, next_pose: Pose, project: ProjectSpec) -> None:
    settings = project.print_settings
    travel_feed = settings.travel_feed_mm_s * 60.0
    retract_feed = settings.retraction_feed_mm_s * 60.0

    if settings.retraction_length_mm > 0.0:
        builder.comment("Retract before non-printing travel")
        builder.extruder_only(-settings.retraction_length_mm, retract_feed)

    lift = previous_pose.machine_point_mm.copy()
    lift[2] += settings.travel_lift_mm
    if settings.travel_lift_mm > 0.0:
        builder.move(previous_pose, feed_mm_min=travel_feed, machine_point_override=lift, command="G0")

    lifted_target = next_pose.machine_point_mm.copy()
    lifted_target[2] += settings.travel_lift_mm
    builder.move(next_pose, feed_mm_min=travel_feed, machine_point_override=lifted_target, command="G0")

    if settings.travel_lift_mm > 0.0:
        builder.move(next_pose, feed_mm_min=travel_feed, command="G0")

    if settings.prime_length_mm > 0.0:
        builder.comment("Prime after non-printing travel")
        builder.extruder_only(settings.prime_length_mm, retract_feed)


def build_gcode_program(project: ProjectSpec) -> BuildResult:
    builder = GCodeBuilder(machine=project.machine)
    builder.comment(f"Open5x Python port - {project.name}")
    if project.comment:
        builder.comment(project.comment)

    if project.start_gcode:
        builder.extend(project.start_gcode)
    else:
        builder.extend(
            [
                "G90",
                "M83",
                "G21",
                "G92 E0",
            ]
        )

    previous_last_pose: Pose | None = None
    for path in project.paths:
        poses = solve_path_poses(path, project.machine)
        if not poses:
            continue
        builder.comment(f"Path: {path.name}")
        if previous_last_pose is not None:
            _travel_with_retraction(builder, previous_last_pose, poses[0], project)
        else:
            first_feed = project.print_settings.travel_feed_mm_s * 60.0
            builder.move(poses[0], feed_mm_min=first_feed, command="G0")

        lengths = segment_lengths(path.points_mm, closed=path.closed)
        stop = len(poses) if path.closed else len(poses) - 1
        for index in range(stop):
            current_pose = poses[index]
            next_pose = poses[(index + 1) % len(poses)]
            segment_length = float(lengths[index])
            effective_distance = effective_move_distance_mm(current_pose, next_pose, project.machine)
            if path.extrude:
                extrusion = extrusion_for_segment(segment_length, project.print_settings)
                feed = compensated_feed_mm_min(
                    project.print_settings.print_feed_mm_s,
                    segment_length,
                    effective_distance,
                    project.print_settings.max_feed_scale,
                )
                builder.move(next_pose, feed_mm_min=feed, extrusion_delta_mm=extrusion, command="G1")
            else:
                feed = compensated_feed_mm_min(
                    project.print_settings.travel_feed_mm_s,
                    max(segment_length, 1e-9),
                    effective_distance,
                    project.print_settings.max_feed_scale,
                )
                builder.move(next_pose, feed_mm_min=feed, command="G0")
        previous_last_pose = poses[-1]

    if project.end_gcode:
        builder.extend(project.end_gcode)
    else:
        builder.extend(
            [
                "G1 E-1.00000 F1200.0",
                "M104 S0",
                "M140 S0",
            ]
        )
    return BuildResult(gcode=builder.emit_program(), line_count=len(builder.lines))
