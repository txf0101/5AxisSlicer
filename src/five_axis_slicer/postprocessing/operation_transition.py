"""Plan inter-operation travel in machine axes and retain it in the toolpath.

An XYZAC table can rotate a completed part under a stationary nozzle.  A
clearance specified only in workpiece Z therefore does not describe a safe
machine move.  This planner checks the actual joint interpolation and stores
the selected route as ordinary non-depositing path points for NC/readback.
"""

from __future__ import annotations

from dataclasses import replace
from collections.abc import Callable, Mapping
import math

from ..kinematics.xyzac import (
    MachineAxisSample,
    MachineAxisTrajectory,
    _motion_limit_issues,
    _singularity_issues,
)
from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.machine import MachineProfile
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from .tool_change_service import (
    ToolChangeCollisionError,
    _PrintedSegmentIndex,
    _check_printed_part,
    _nozzle_sections,
    _sample_move,
)


class OperationTransitionError(ValueError):
    """No verified route exists for a particular operation boundary."""

    def __init__(
        self, point_id: str, reason: str, *, context: Mapping | None = None,
        code: str = "motion.transition_route_unavailable",
    ):
        self.code = code
        self.point_id = point_id
        self.context = {"reason": reason, **dict(context or {})}
        super().__init__(f"{self.code}:{point_id}:{reason}")


def plan_machine_operation_transitions(
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    *,
    safe_clearance_mm: float,
    T_workpiece_from_build: RigidTransform | None = None,
    sample_step_mm: float = 0.5,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[GeneratedToolpath, MachineAxisTrajectory]:
    """Replace geometric transition guesses with sampled XYZAC routes.

    Previously deposited beads are obstacles.  The first move leaves the last
    printed point at fixed A/C; reorientation only occurs at a machine-Z plane
    above a conservative rotary sweep bound.  Each candidate is checked over
    its full joint interpolation before it is accepted.
    """

    if len(toolpath.points) != len(trajectory.samples):
        raise ValueError("transition planning requires aligned points and axes")
    if not math.isfinite(safe_clearance_mm) or safe_clearance_mm <= 0:
        raise ValueError("safe_clearance_mm must be finite and positive")
    if not math.isfinite(sample_step_mm) or sample_step_mm <= 0:
        raise ValueError("sample_step_mm must be finite and positive")
    points = toolpath.points
    groups = _transition_groups(points)
    if not groups:
        return toolpath, trajectory
    sections = _nozzle_sections(
        nozzle.outer_profile_rz_mm or ((nozzle.orifice_diameter_mm / 2, 0.0),)
    )
    radius = max(section[0] for section in sections)
    printed_index = _PrintedSegmentIndex(toolpath, radius, checkpoint=checkpoint)
    new_points: list[ToolpathPoint] = []
    new_samples: list[MachineAxisSample] = []
    index_map: dict[int, int] = {}
    event_positions: dict[int, dict[str, int]] = {}
    old_index = 0
    deposited_radius = 0.0
    group_by_start = {start: end for start, end in groups}
    while old_index < len(points):
        if checkpoint is not None and old_index % 512 == 0:
            checkpoint()
        if old_index in group_by_start:
            end = group_by_start[old_index]
            previous = trajectory.samples[old_index - 1].joint_positions
            target = trajectory.samples[end].joint_positions
            clearance_z = _conservative_clearance_z(
                toolpath, old_index, machine, nozzle, trajectory.tool_length_mm,
                previous, target, safe_clearance_mm, deposited_radius,
            )
            route = _find_route(
                toolpath, old_index, previous, target, clearance_z,
                machine, nozzle, trajectory.tool_length_mm, sections, radius,
                T_workpiece_from_build, sample_step_mm, checkpoint, printed_index,
                source_deposition=points[old_index - 1].point_type == "deposition",
            )
            first = len(new_points)
            for label, joints in route:
                route_point = _point_from_machine(
                    points[old_index], label, joints, machine,
                    trajectory.tool_length_mm, T_workpiece_from_build,
                )
                new_points.append(route_point)
                _append_sample(new_samples, route_point, joints, machine, trajectory.tool_length_mm)
            index_map[old_index] = first
            for skipped in range(old_index + 1, end):
                index_map[skipped] = len(new_points) - 1
            event_positions[old_index] = {
                "retract": first,
                "safe_depart": first + 1,
                "operation_change": next(
                    first + index for index, (label, _) in enumerate(route)
                    if label == "orient"
                ),
                "safe_approach": len(new_points) - 1,
            }
            old_index = end
            continue
        index_map[old_index] = len(new_points)
        point = points[old_index]
        old_sample = trajectory.samples[old_index]
        new_points.append(point)
        if point.point_type == "deposition":
            position = (
                point.position if T_workpiece_from_build is None
                else T_workpiece_from_build.transform_point(point.position)
            )
            deposited_radius = max(
                deposited_radius, math.sqrt(sum(value * value for value in position)),
            )
        _append_sample(
            new_samples, point, old_sample.joint_positions,
            machine, trajectory.tool_length_mm,
            tool_tip_machine_mm=old_sample.tool_tip_machine_mm,
            singular=old_sample.singular,
            fk_position_error=old_sample.fk_position_error_mm,
            fk_orientation_error=old_sample.fk_orientation_error_rad,
        )
        old_index += 1
    index_map[len(points)] = len(new_points)
    new_events = []
    for event in toolpath.events:
        original = int(event.context.get("sequence_index", 0))
        event_index = index_map[original]
        if original in event_positions:
            event_index = event_positions[original].get(event.event_type, event_index)
        else:
            for start, end in groups:
                if start < original <= end:
                    event_index = event_positions[start].get(event.event_type, event_index)
                    break
        new_events.append(replace(event, context=dict(event.context) | {"sequence_index": event_index}))
    revised_path = replace(
        toolpath,
        toolpath_id=f"{toolpath.toolpath_id}-machine-transition-v1",
        points=tuple(new_points), events=tuple(new_events),
    )
    retained_issues = tuple(
        issue for issue in trajectory.issues
        if issue.code not in {
            "xyzac.rotary_singularity", "xyzac.velocity_limit_exceeded",
            "xyzac.acceleration_limit_exceeded",
        }
    )
    revised_issues = (
        *retained_issues,
        *_singularity_issues(new_samples),
        *_motion_limit_issues(new_samples, machine),
    )
    revised_trajectory = replace(
        trajectory,
        trajectory_id=f"{trajectory.trajectory_id}-machine-transition-v1",
        source_toolpath_id=revised_path.toolpath_id,
        samples=tuple(new_samples), issues=tuple(revised_issues),
    )
    return revised_path, revised_trajectory


def plan_machine_non_deposition_travels(
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    *,
    safe_clearance_mm: float,
    T_workpiece_from_build: RigidTransform | None = None,
    sample_step_mm: float = 0.5,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[GeneratedToolpath, MachineAxisTrajectory]:
    """Replace colliding same-operation air moves with checked machine hops.

    A direct air move is retained when its full nozzle envelope clears the
    printed prefix. Otherwise the target pose is checked, then a retract,
    high machine-Z traverse, and approach are sampled before being inserted
    into the exported path. Depositing points and event order are preserved.
    """

    if len(toolpath.points) != len(trajectory.samples):
        raise ValueError("air-move planning requires aligned points and axes")
    if safe_clearance_mm <= 0 or not math.isfinite(safe_clearance_mm):
        raise ValueError("safe_clearance_mm must be finite and positive")
    if sample_step_mm <= 0 or not math.isfinite(sample_step_mm):
        raise ValueError("sample_step_mm must be finite and positive")
    points = toolpath.points
    if not any(
        points[index].point_type != "deposition"
        and points[index - 1].stage_id != "operation-transition"
        and points[index].stage_id != "operation-transition"
        for index in range(1, len(points))
    ):
        return toolpath, trajectory
    profile = nozzle.outer_profile_rz_mm or ((nozzle.orifice_diameter_mm / 2.0, 0.0),)
    sections = _nozzle_sections(profile)
    radius = max(section[0] for section in sections)
    printed_index = _PrintedSegmentIndex(toolpath, radius, checkpoint=checkpoint)
    new_points: list[ToolpathPoint] = []
    new_samples: list[MachineAxisSample] = []
    index_map: dict[int, int] = {}
    deposited_radius = 0.0
    have_deposition = False
    changed = False
    for index, point in enumerate(points):
        if checkpoint is not None and index % 128 == 0:
            checkpoint()
        old_sample = trajectory.samples[index]
        if (
            have_deposition and index > 0 and point.point_type != "deposition"
            and points[index - 1].stage_id != "operation-transition"
            and point.stage_id != "operation-transition"
        ):
            before = trajectory.samples[index - 1].joint_positions
            after = old_sample.joint_positions
            travel_length = math.dist(
                tuple(before[axis] for axis in ("X", "Y", "Z")),
                tuple(after[axis] for axis in ("X", "Y", "Z")),
            )
            samples = _sample_move(
                before, after, machine, trajectory.tool_length_mm,
                sections, T_workpiece_from_build, sample_step_mm,
                label=f"same_operation_direct:{points[index - 1].point_id}->{point.point_id}",
                exempt_recent=False,
            )
            target_tip_bond = (
                index + 1 < len(points) and points[index + 1].point_type == "deposition"
            )
            try:
                _check_printed_part(
                    toolpath, index, samples, radius,
                    checkpoint=checkpoint,
                    error_code="motion.non_deposition_travel_collision",
                    bond_tip_window_mm=(
                        2.0 * nozzle.orifice_diameter_mm if target_tip_bond else 0.0
                    ),
                    depart_tip_window_mm=(
                        2.0 * nozzle.orifice_diameter_mm
                        if points[index - 1].point_type == "deposition" else 0.0
                    ),
                    move_length_mm=travel_length,
                    bond_tip_max_overlap_mm=nozzle.orifice_diameter_mm / 4.0,
                    nozzle_profile=profile,
                    printed_index=printed_index,
                )
            except ToolChangeCollisionError:
                local_z = max(before["Z"], after["Z"]) + safe_clearance_mm
                try:
                    machine.joint_map["Z"].effective_position(local_z)
                    route = _find_route(
                        toolpath, index, before, after, local_z,
                        machine, nozzle, trajectory.tool_length_mm, sections, radius,
                        T_workpiece_from_build, sample_step_mm, checkpoint, printed_index,
                        source_deposition=points[index - 1].point_type == "deposition",
                        target_tip_bond=target_tip_bond,
                        route_kind="same_operation_hop",
                    )
                except (OperationTransitionError, ValueError) as local_error:
                    if (
                        isinstance(local_error, OperationTransitionError)
                        and local_error.context["reason"]
                        == "target nozzle pose intersects previously printed material"
                    ):
                        raise OperationTransitionError(
                            point.point_id, local_error.context["reason"],
                            context=local_error.context,
                            code="motion.non_deposition_route_unavailable",
                        ) from local_error
                    clearance_z = _conservative_clearance_z(
                        toolpath, index, machine, nozzle, trajectory.tool_length_mm,
                        before, after, safe_clearance_mm, deposited_radius,
                    )
                    try:
                        route = _find_route(
                            toolpath, index, before, after, clearance_z,
                            machine, nozzle, trajectory.tool_length_mm, sections, radius,
                            T_workpiece_from_build, sample_step_mm, checkpoint,
                            printed_index,
                            source_deposition=points[index - 1].point_type == "deposition",
                            target_tip_bond=target_tip_bond,
                            route_kind="same_operation_hop",
                        )
                    except OperationTransitionError as exc:
                        raise OperationTransitionError(
                            point.point_id, exc.context["reason"], context=exc.context,
                            code="motion.non_deposition_route_unavailable",
                        ) from exc
                if not route:
                    raise OperationTransitionError(
                        point.point_id, "empty safe air route",
                        code="motion.non_deposition_route_unavailable",
                    )
                changed = True
                index_map[index] = len(new_points)
                for label, joints in route[:-1]:
                    route_point = _point_from_machine(
                        point, f"air-hop-{label}", joints, machine,
                        trajectory.tool_length_mm, T_workpiece_from_build,
                    )
                    new_points.append(route_point)
                    _append_sample(
                        new_samples, route_point, joints, machine,
                        trajectory.tool_length_mm,
                    )
        index_map.setdefault(index, len(new_points))
        new_points.append(point)
        _append_sample(
            new_samples, point, old_sample.joint_positions,
            machine, trajectory.tool_length_mm,
            tool_tip_machine_mm=old_sample.tool_tip_machine_mm,
            singular=old_sample.singular,
            fk_position_error=old_sample.fk_position_error_mm,
            fk_orientation_error=old_sample.fk_orientation_error_rad,
        )
        if point.point_type == "deposition":
            have_deposition = True
            position = (
                point.position if T_workpiece_from_build is None
                else T_workpiece_from_build.transform_point(point.position)
            )
            deposited_radius = max(
                deposited_radius, math.sqrt(sum(value * value for value in position)),
            )
    if not changed:
        return toolpath, trajectory
    index_map[len(points)] = len(new_points)
    revised_path = replace(
        toolpath,
        toolpath_id=f"{toolpath.toolpath_id}-machine-air-v1",
        points=tuple(new_points),
        events=tuple(replace(
            event,
            context=dict(event.context) | {
                "sequence_index": index_map[int(event.context.get("sequence_index", 0))]
            },
        ) for event in toolpath.events),
    )
    retained_issues = tuple(
        issue for issue in trajectory.issues
        if issue.code not in {
            "xyzac.rotary_singularity", "xyzac.velocity_limit_exceeded",
            "xyzac.acceleration_limit_exceeded",
        }
    )
    revised_trajectory = replace(
        trajectory,
        trajectory_id=f"{trajectory.trajectory_id}-machine-air-v1",
        source_toolpath_id=revised_path.toolpath_id,
        samples=tuple(new_samples),
        issues=(
            *retained_issues, *_singularity_issues(new_samples),
            *_motion_limit_issues(new_samples, machine),
        ),
    )
    return revised_path, revised_trajectory


def _transition_groups(points):
    groups = []
    index = 0
    while index < len(points):
        if points[index].stage_id != "operation-transition":
            index += 1
            continue
        end = index + 1
        while end < len(points) and points[end].stage_id == "operation-transition":
            end += 1
        if index == 0 or end == len(points) or end - index != 2:
            raise OperationTransitionError(
                points[index].point_id, "unsupported transition point sequence",
                context={"start_index": index, "point_count": end - index},
            )
        groups.append((index, end))
        index = end
    return groups


def _conservative_clearance_z(
    toolpath, sequence, machine, nozzle, tool_length, before, after,
    clearance, max_radius,
):
    assert machine.workpiece_link_id is not None
    center_z = -math.inf
    for index in range(33):
        fraction = index / 32
        rotations = {
            name: before[name] + fraction * (after[name] - before[name])
            for name in ("A", "C")
        }
        center_z = max(
            center_z,
            machine.link_transform(machine.workpiece_link_id, rotations).translation[2],
        )
    # The continuous rotary sweep can amplify offset-link translations even
    # when they cancel at zero pose. Bound each calibrated link separately;
    # using only the zero-pose table origin would miss that movement.
    parents = {joint.child_link_id: joint for joint in machine.joints}
    workpiece_link = machine.workpiece_link_id
    continuous_bound = 0.0
    while workpiece_link != machine.root_link_id:
        joint = parents[workpiece_link]
        assert joint.T_parent_from_child_zero is not None
        continuous_bound += math.sqrt(sum(
            value * value for value in joint.T_parent_from_child_zero.translation
        ))
        if joint.joint_type == "rotary":
            continuous_bound += 2.0 * math.sqrt(sum(
                value * value for value in joint.rotation_center_mm
            ))
        workpiece_link = joint.parent_link_id
    center_z = max(center_z, continuous_bound)
    nozzle_height = max((section[1] for section in nozzle.outer_profile_rz_mm), default=0.0)
    nozzle_radius = max((section[0] for section in nozzle.outer_profile_rz_mm), default=nozzle.orifice_diameter_mm / 2)
    safe_z = max(
        before["Z"] + clearance,
        after["Z"] + clearance,
        center_z + max_radius + nozzle_height + nozzle_radius + tool_length + clearance,
    )
    z_axis = machine.joint_map["Z"]
    try:
        z_axis.effective_position(safe_z)
    except ValueError as exc:
        raise OperationTransitionError(
            toolpath.points[sequence].point_id, "rotary-sweep clearance exceeds Z limit",
            context={"required_machine_z_mm": safe_z,
                     "z_soft_limit_max_mm": z_axis.soft_limit_max},
        ) from exc
    return safe_z


def _find_route(
    toolpath, sequence, before, after, safe_z, machine, nozzle, tool_length,
    sections, radius, transform, sample_step, checkpoint, printed_index, *,
    source_deposition, target_tip_bond=True, route_kind="transition",
):
    # A route cannot repair an occupied final nozzle pose.  Check it once
    # before searching approach shapes; this also distinguishes an unreachable
    # contact from a collision only along the approach.
    endpoint_samples = _sample_move(
        after, after, machine, tool_length, sections, transform,
        sample_step, label=f"{route_kind}:target_pose", exempt_recent=False,
    )
    try:
        _check_printed_part(
            toolpath, sequence, endpoint_samples, radius,
            checkpoint=checkpoint, error_code="motion.printed_part_collision",
            bond_tip_window_mm=(
                2.0 * nozzle.orifice_diameter_mm if target_tip_bond else 0.0
            ),
            bond_tip_max_overlap_mm=nozzle.orifice_diameter_mm / 4.0,
            nozzle_profile=nozzle.outer_profile_rz_mm,
            printed_index=printed_index,
        )
    except ToolChangeCollisionError as exc:
        raise OperationTransitionError(
            toolpath.points[sequence].point_id,
            "target nozzle pose intersects previously printed material",
            context={
                "required_machine_z_mm": safe_z,
                "target_joints": dict(after),
                **exc.context,
            },
        ) from exc
    offset = max(10.0, 4.0 * radius)
    modes = ("direct", "x_plus", "x_minus", "y_plus", "y_minus")
    last_error = None
    attempted = 0
    failures = []
    for depart_mode in modes:
        for approach_mode in modes:
            route = _candidate_route(before, after, safe_z, offset, depart_mode, approach_mode)
            attempted += 1
            try:
                samples_before_final = []
                previous = before
                release_label, release_joint = route[0]
                for axis, value in release_joint.items():
                    machine.joint_map[axis].effective_position(value)
                release_samples = _sample_move(
                    previous, release_joint, machine, tool_length, sections, transform,
                    sample_step, label=f"{route_kind}:{release_label}", exempt_recent=False,
                )
                release_length = math.dist(
                    tuple(previous[axis] for axis in ("X", "Y", "Z")),
                    tuple(release_joint[axis] for axis in ("X", "Y", "Z")),
                )
                _check_printed_part(
                    toolpath, sequence, release_samples, radius,
                    checkpoint=checkpoint, error_code="motion.printed_part_collision",
                    depart_tip_window_mm=(
                        2.0 * nozzle.orifice_diameter_mm if source_deposition else 0.0
                    ),
                    move_length_mm=release_length,
                    bond_tip_max_overlap_mm=nozzle.orifice_diameter_mm / 4.0,
                    nozzle_profile=nozzle.outer_profile_rz_mm,
                    printed_index=printed_index,
                )
                previous = release_joint
                for label, joints in route[1:-1]:
                    for axis, value in joints.items():
                        machine.joint_map[axis].effective_position(value)
                    samples_before_final.extend(_sample_move(
                        previous, joints, machine, tool_length, sections, transform,
                        sample_step, label=f"{route_kind}:{label}",
                        exempt_recent=False,
                    ))
                    previous = joints
                _check_printed_part(
                    toolpath, sequence, samples_before_final, radius,
                    checkpoint=checkpoint, error_code="motion.printed_part_collision",
                    nozzle_profile=nozzle.outer_profile_rz_mm,
                    printed_index=printed_index,
                )
                label, joints = route[-1]
                for axis, value in joints.items():
                    machine.joint_map[axis].effective_position(value)
                final_samples = _sample_move(
                    previous, joints, machine, tool_length, sections, transform,
                    sample_step, label=f"{route_kind}:{label}", exempt_recent=False,
                )
                _check_printed_part(
                    toolpath, sequence, final_samples, radius,
                    checkpoint=checkpoint, error_code="motion.printed_part_collision",
                    bond_tip_window_mm=(
                        2.0 * nozzle.orifice_diameter_mm if target_tip_bond else 0.0
                    ),
                    bond_tip_max_overlap_mm=nozzle.orifice_diameter_mm / 4.0,
                    nozzle_profile=nozzle.outer_profile_rz_mm,
                    printed_index=printed_index,
                )
                return route
            except (ToolChangeCollisionError, ValueError) as exc:
                last_error = exc
                if isinstance(exc, ToolChangeCollisionError):
                    failures.append({
                        "depart_mode": depart_mode,
                        "approach_mode": approach_mode,
                        "move": exc.label,
                        "overlap_mm": exc.clearance - exc.distance,
                        "nozzle_section_height_mm": exc.section_height_mm,
                        "remaining_travel_mm": exc.remaining_travel_mm,
                    })
                else:
                    failures.append({
                        "depart_mode": depart_mode,
                        "approach_mode": approach_mode,
                        "reason": str(exc),
                    })
                if checkpoint is not None:
                    checkpoint()
    context = {"attempted_routes": attempted, "required_machine_z_mm": safe_z,
               "candidate_failures": failures}
    if isinstance(last_error, ToolChangeCollisionError):
        context.update(last_error.context)
    elif last_error is not None:
        context["last_error"] = str(last_error)
    raise OperationTransitionError(
        toolpath.points[sequence].point_id, "all sampled XYZAC routes rejected",
        context=context,
    )


def _candidate_route(before, after, safe_z, offset, depart_mode, approach_mode):
    old = {axis: before[axis] for axis in ("A", "C")}
    new = {axis: after[axis] for axis in ("A", "C")}

    def side(mode, x, y):
        if mode == "direct":
            return x, y
        axis, direction = mode.split("_")
        amount = offset if direction == "plus" else -offset
        return (x + amount, y) if axis == "x" else (x, y + amount)

    departure_xy = side(depart_mode, before["X"], before["Y"])
    arrival_xy = side(approach_mode, after["X"], after["Y"])
    release_height = min(0.8, max(0.4, safe_z - before["Z"]))
    route = [("release", {"X": before["X"], "Y": before["Y"],
                          "Z": before["Z"] + release_height, **old})]
    if depart_mode != "direct":
        route.append(("depart_side", {"X": departure_xy[0], "Y": departure_xy[1],
                                      "Z": before["Z"] + release_height, **old}))
    route.append(("depart", {"X": departure_xy[0], "Y": departure_xy[1],
                             "Z": safe_z, **old}))
    route.append(("traverse", {"X": arrival_xy[0], "Y": arrival_xy[1],
                               "Z": safe_z, **old}))
    route.append(("orient", {"X": arrival_xy[0], "Y": arrival_xy[1],
                             "Z": safe_z, **new}))
    if approach_mode != "direct":
        route.append(("approach_side", {"X": arrival_xy[0], "Y": arrival_xy[1],
                                     "Z": after["Z"], **new}))
    route.append(("arrival", dict(after)))
    return tuple(route)


def _point_from_machine(template, label, joints, machine, tool_length, transform):
    assert machine.tool_link_id is not None and machine.workpiece_link_id is not None
    transforms = machine.forward_kinematics(joints)
    tool_mount = transforms[machine.tool_link_id].translation
    tip = (tool_mount[0], tool_mount[1], tool_mount[2] - tool_length)
    workpiece_inverse = transforms[machine.workpiece_link_id].inverse()
    position = workpiece_inverse.transform_point(tip)
    nozzle_axis = workpiece_inverse.transform_vector((0.0, 0.0, -1.0))
    if transform is not None:
        inverse = transform.inverse()
        position = inverse.transform_point(position)
        nozzle_axis = inverse.transform_vector(nozzle_axis)
    return replace(
        template,
        point_id=f"{template.point_id}-{label}",
        position=position,
        nozzle_axis=nozzle_axis,
        surface_normal=None,
        point_type=(
            "depart" if label in {"release", "depart", "depart_side"}
            else "approach" if label == "arrival" else "travel"
        ),
        extrusion_role="none", bead_width_mm=None, layer_height_mm=None,
        material_volume_mm3=0.0, material_id=None, channel_id=None,
        issue_ids=(),
    )


def _append_sample(
    samples, point, joints, machine, tool_length, *, singular=False,
    fk_position_error=0.0, fk_orientation_error=0.0,
    tool_tip_machine_mm=None,
):
    duration = 0.0
    if samples:
        previous = samples[-1].joint_positions
        distance = math.dist(
            tuple(previous[axis] for axis in ("X", "Y", "Z")),
            tuple(joints[axis] for axis in ("X", "Y", "Z")),
        )
        angular = sum(abs(joints[axis] - previous[axis]) for axis in ("A", "C"))
        workpiece_radius = max(1.0, math.sqrt(sum(value * value for value in point.position)))
        duration = max(
            1.0e-6,
            60.0 * (distance + angular * workpiece_radius)
            / (point.feedrate_mm_min or 60.0),
        )
        for axis in ("A", "C"):
            velocity = machine.joint_map[axis].max_velocity
            if velocity is not None:
                duration = max(duration, abs(joints[axis] - previous[axis]) / velocity)
    if tool_tip_machine_mm is None:
        transforms = machine.forward_kinematics(joints)
        assert machine.tool_link_id is not None
        mount = transforms[machine.tool_link_id].translation
        tool_tip_machine_mm = (mount[0], mount[1], mount[2] - tool_length)
    samples.append(MachineAxisSample(
        point.point_id,
        (samples[-1].time_s if samples else 0.0) + duration,
        joints,
        tool_tip_machine_mm,
        fk_position_error, fk_orientation_error, singular,
    ))


__all__ = [
    "OperationTransitionError", "plan_machine_non_deposition_travels",
    "plan_machine_operation_transitions",
]
