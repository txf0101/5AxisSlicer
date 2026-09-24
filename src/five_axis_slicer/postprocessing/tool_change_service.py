"""Explicit machine-frame service routes for single-nozzle material changes.

Station positions are calibrated nozzle-tip coordinates. The route is planned
and checked before G-code emission; controller macros only actuate hardware.
The check covers previously deposited beads and the configured nozzle profile,
not an unmodelled cutter, fixture, or machine frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from itertools import product
import math
from types import MappingProxyType
from typing import Mapping

import numpy as np

from ..kinematics.xyzac import MachineAxisTrajectory
from ..manufacturing.controller_profile import ControllerProfile, ToolChangeStation
from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.machine import MachineProfile
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.toolpath import GeneratedToolpath


class ToolChangeCollisionError(ValueError):
    def __init__(
        self, point_id, label, center, start, end, distance, clearance, *,
        code="tool_change.printed_part_collision",
        section_height_mm=None, remaining_travel_mm=None,
    ):
        self.code = code
        self.point_id = point_id
        self.label = label
        self.center = center
        self.start = start
        self.end = end
        self.distance = distance
        self.clearance = clearance
        self.section_height_mm = section_height_mm
        self.remaining_travel_mm = remaining_travel_mm
        super().__init__(f"{code}:{point_id}:{label}")

    @property
    def context(self):
        return {
            "service_move": self.label,
            "nozzle_center_build_mm": list(self.center),
            "printed_segment_start_build_mm": list(self.start),
            "printed_segment_end_build_mm": list(self.end),
            "measured_distance_mm": self.distance,
            "required_clearance_mm": self.clearance,
            "nozzle_section_height_mm": self.section_height_mm,
            "remaining_travel_mm": self.remaining_travel_mm,
        }


@dataclass(frozen=True, slots=True)
class ServiceMove:
    label: str
    joints: Mapping[str, float]
    feedrate_mm_min: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "joints", MappingProxyType(dict(self.joints)))


@dataclass(frozen=True, slots=True)
class ToolChangeServicePlan:
    moves_before_event: Mapping[str, tuple[ServiceMove, ...]]
    checked_samples: int
    nozzle_envelope_complete: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "moves_before_event",
            MappingProxyType({key: tuple(value) for key, value in self.moves_before_event.items()}),
        )


def check_operation_transition_safety(
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    *,
    T_workpiece_from_build: RigidTransform | None = None,
    sample_step_mm: float = 0.5,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[int, int]:
    """Check every generated inter-operation travel and subsequent approach.

    The departure from a deposited endpoint is excluded because contact at
    its start is intentional. The ensuing travel and approach must clear all
    previously deposited beads, including the base below a lateral blade.
    """

    if len(toolpath.points) != len(trajectory.samples):
        raise ValueError("operation transition requires aligned toolpath and trajectory")
    if sample_step_mm <= 0 or not math.isfinite(sample_step_mm):
        raise ValueError("sample_step_mm must be finite and positive")
    if not any(point.stage_id == "operation-transition" for point in toolpath.points):
        return 0, 0
    profile = nozzle.outer_profile_rz_mm or ((nozzle.orifice_diameter_mm / 2.0, 0.0),)
    sections = _nozzle_sections(profile)
    radius = max(item[0] for item in sections)
    printed_index = _PrintedSegmentIndex(toolpath, radius, checkpoint=checkpoint)
    checked = allowed_tip_contacts = 0
    for index in range(1, len(toolpath.points)):
        left, right = toolpath.points[index - 1:index + 1]
        if not (
            left.point_type != "deposition"
            and right.point_type != "deposition"
            and (left.stage_id == "operation-transition" or right.stage_id == "operation-transition")
        ):
            continue
        if checkpoint is not None:
            checkpoint()
        samples = _sample_move(
            trajectory.samples[index - 1].joint_positions,
            trajectory.samples[index].joint_positions,
            machine,
            trajectory.tool_length_mm,
            sections,
            T_workpiece_from_build,
            sample_step_mm,
            label=f"operation_transition:{left.point_id}->{right.point_id}",
            exempt_recent=False,
        )
        checked += len(samples) // len(sections)
        allowed_tip_contacts += _check_printed_part(
            toolpath, index + 1, samples, radius,
            checkpoint=checkpoint,
            error_code="motion.printed_part_collision",
            bond_tip_window_mm=(2.0 * nozzle.orifice_diameter_mm)
            if right.point_type == "approach" else 0.0,
            bond_tip_max_overlap_mm=nozzle.orifice_diameter_mm / 4.0,
            nozzle_profile=profile,
            printed_index=printed_index,
        )
    return checked, allowed_tip_contacts


def check_non_deposition_travel_safety(
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    *,
    T_workpiece_from_build: RigidTransform | None = None,
    sample_step_mm: float = 0.5,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[int, int]:
    """Check same-operation air moves against the printed prefix.

    Inter-operation moves are handled separately by the route planner. A
    finite-width tip may make shallow bond contact only close to a departure
    or arrival; every other nozzle section must remain clear.
    """

    if len(toolpath.points) != len(trajectory.samples):
        raise ValueError("travel safety requires aligned toolpath and trajectory")
    if sample_step_mm <= 0 or not math.isfinite(sample_step_mm):
        raise ValueError("sample_step_mm must be finite and positive")
    moves = tuple(
        index for index in range(1, len(toolpath.points))
        if toolpath.points[index].point_type != "deposition"
        and toolpath.points[index - 1].stage_id != "operation-transition"
        and toolpath.points[index].stage_id != "operation-transition"
    )
    if not moves:
        return 0, 0
    profile = nozzle.outer_profile_rz_mm or ((nozzle.orifice_diameter_mm / 2.0, 0.0),)
    sections = _nozzle_sections(profile)
    radius = max(item[0] for item in sections)
    printed_index = _PrintedSegmentIndex(toolpath, radius, checkpoint=checkpoint)
    checked = allowed_tip_contacts = 0
    for index in moves:
        if checkpoint is not None and index % 128 == 0:
            checkpoint()
        left, right = toolpath.points[index - 1:index + 1]
        before = trajectory.samples[index - 1].joint_positions
        after = trajectory.samples[index].joint_positions
        travel_length = math.dist(
            tuple(before[axis] for axis in ("X", "Y", "Z")),
            tuple(after[axis] for axis in ("X", "Y", "Z")),
        )
        samples = _sample_move(
            before, after, machine, trajectory.tool_length_mm,
            sections, T_workpiece_from_build, sample_step_mm,
            label=f"same_operation_travel:{left.point_id}->{right.point_id}",
            exempt_recent=False,
        )
        checked += len(samples) // len(sections)
        allowed_tip_contacts += _check_printed_part(
            toolpath, index, samples, radius,
            checkpoint=checkpoint,
            error_code="motion.non_deposition_travel_collision",
            bond_tip_window_mm=(
                2.0 * nozzle.orifice_diameter_mm
                if index + 1 < len(toolpath.points)
                and toolpath.points[index + 1].point_type == "deposition"
                else 0.0
            ),
            depart_tip_window_mm=(
                2.0 * nozzle.orifice_diameter_mm
                if left.point_type == "deposition" else 0.0
            ),
            move_length_mm=travel_length,
            bond_tip_max_overlap_mm=nozzle.orifice_diameter_mm / 4.0,
            nozzle_profile=profile,
            printed_index=printed_index,
        )
    return checked, allowed_tip_contacts


def plan_tool_change_service(
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    controller: ControllerProfile,
    *,
    T_workpiece_from_build: RigidTransform | None = None,
    sample_step_mm: float = 0.5,
    checkpoint: Callable[[], None] | None = None,
) -> ToolChangeServicePlan:
    """Plan service moves for effective T transitions, rejecting missing stations.

    The initial T selection does not visit the station. At each later switch,
    the path leaves the completed deposition before the next region's travel.
    A/C are held during station travel; reorientation occurs at clearance.
    """

    if sample_step_mm <= 0 or not math.isfinite(sample_step_mm):
        raise ValueError("sample_step_mm must be finite and positive")
    if len(toolpath.points) != len(trajectory.samples):
        raise ValueError("tool-change planning requires aligned toolpath and trajectory")
    switches = sorted(
        (event for event in toolpath.events if event.event_type == "switch"),
        key=lambda event: int(event.context["sequence_index"]),
    )
    if len(switches) < 2:
        return ToolChangeServicePlan({}, 0, nozzle.is_ready)
    station = controller.tool_change_station
    if station is None:
        raise ValueError("tool_change.station_unconfigured")
    profile = nozzle.outer_profile_rz_mm or ((nozzle.orifice_diameter_mm / 2.0, 0.0),)
    sections = _nozzle_sections(profile)
    radius = max(item[0] for item in sections)
    printed_index = _PrintedSegmentIndex(toolpath, radius, checkpoint=checkpoint)
    moves: dict[str, tuple[ServiceMove, ...]] = {}
    checked = 0
    active = str(switches[0].context["channel_id"])
    for switch in switches[1:]:
        channel = str(switch.context["channel_id"])
        if channel == active:
            continue
        active = channel
        sequence = int(switch.context["sequence_index"])
        if not 0 < sequence < len(toolpath.points):
            raise ValueError("tool_change.invalid_boundary")
        before = trajectory.samples[sequence - 1].joint_positions
        after = trajectory.samples[sequence].joint_positions
        if before["Z"] - trajectory.tool_length_mm >= station.clearance_z_mm:
            raise ValueError("tool_change.clearance_below_departure")
        if after["Z"] - trajectory.tool_length_mm >= station.clearance_z_mm:
            raise ValueError("tool_change.clearance_below_return")
        group = {
            event.event_type: event
            for event in toolpath.events
            if event.stage_id == "material_switch"
            and event.region_id == switch.region_id
            and event.context.get("sequence_index") == sequence
        }
        required = {"cut", "park", "switch", "unload", "load", "purge", "resume"}
        if not required.issubset(group):
            raise ValueError("tool_change.incomplete_event_chain")
        last_error = None
        failed_depart_modes = set()
        candidates = product(
            ("direct", "x_plus", "x_minus", "y_plus", "y_minus"),
            ("direct", "vertical", "x_plus", "x_minus", "y_plus", "y_minus"),
        )
        for depart_mode, approach_mode in candidates:
            if depart_mode in failed_depart_modes:
                continue
            route = _service_route(
                before, after, station, trajectory.tool_length_mm,
                depart_mode=depart_mode, approach_mode=approach_mode,
                lateral_offset=max(10.0, 4.0 * radius),
            )
            try:
                service_samples = []
                position = dict(before)
                for stage_moves in route.values():
                    for move in stage_moves:
                        service_samples.extend(_sample_move(
                            position,
                            move.joints,
                            machine,
                            trajectory.tool_length_mm,
                            sections,
                            T_workpiece_from_build,
                            sample_step_mm,
                            label=move.label,
                            exempt_recent=move.label == "safe_depart",
                        ))
                        position = dict(move.joints)
                checked += len(service_samples) // len(sections)
                _check_printed_part(
                    toolpath, sequence, service_samples, radius,
                    checkpoint=checkpoint,
                    nozzle_profile=profile,
                    printed_index=printed_index,
                )
            except ValueError as exc:
                if not (
                    str(exc).startswith("tool_change.printed_part_collision:")
                    or str(exc).startswith("joint position ")
                ):
                    raise
                if str(exc).startswith("tool_change.printed_part_collision:") or last_error is None:
                    last_error = exc
                if isinstance(exc, ToolChangeCollisionError) and exc.label in {
                    "safe_depart_lateral", "safe_depart", "cutter_above", "cutter",
                    "leave_cutter", "exchange_above", "exchange", "leave_exchange",
                    "purge_above", "purge",
                }:
                    failed_depart_modes.add(depart_mode)
                continue
            for kind, stage_moves in route.items():
                moves[group[kind].event_id] = stage_moves
            break
        else:
            assert last_error is not None
            raise last_error
    return ToolChangeServicePlan(moves, checked, nozzle.is_ready)


def _service_route(
    before, after, station: ToolChangeStation, tool_length, *,
    depart_mode="direct", approach_mode="vertical", lateral_offset=20.0,
):
    safe = station.clearance_z_mm + tool_length
    old_rotary = {axis: before[axis] for axis in ("A", "C")}
    new_rotary = {axis: after[axis] for axis in ("A", "C")}

    def move(label, x, y, z, rotary=old_rotary, feed=None):
        return ServiceMove(
            label,
            {"X": x, "Y": y, "Z": z, **rotary},
            station.travel_feedrate_mm_min if feed is None else feed,
        )

    def above(label, xyz, rotary=old_rotary):
        return move(label, xyz[0], xyz[1], safe, rotary)

    def at(label, xyz, rotary=old_rotary, feed=None):
        return move(label, xyz[0], xyz[1], xyz[2] + tool_length, rotary, feed)

    departure = dict(before)
    cut_moves = []
    if depart_mode != "direct":
        axis, direction = depart_mode.split("_")
        offset = lateral_offset if direction == "plus" else -lateral_offset
        departure[axis.upper()] += offset
        cut_moves.append(move(
            "safe_depart_lateral", departure["X"], departure["Y"], departure["Z"],
        ))
    cut_moves.extend((
        move("safe_depart", departure["X"], departure["Y"], safe),
        above("cutter_above", station.cutter_xyz_mm),
        at("cutter", station.cutter_xyz_mm),
    ))
    cut = tuple(cut_moves)
    park = (
        above("leave_cutter", station.cutter_xyz_mm),
        above("exchange_above", station.exchange_xyz_mm),
        at("exchange", station.exchange_xyz_mm),
    )
    purge = (
        above("leave_exchange", station.exchange_xyz_mm),
        above("purge_above", station.purge_xyz_mm),
        at("purge", station.purge_xyz_mm),
    )
    resume: list[ServiceMove] = [
        above("leave_purge", station.purge_xyz_mm),
        above("reorient_at_station", station.purge_xyz_mm, new_rotary),
        above("wipe_above", station.wipe_start_xyz_mm, new_rotary),
        at("wipe_start", station.wipe_start_xyz_mm, new_rotary),
    ]
    for pass_index in range(station.wipe_passes):
        resume.extend((
            at(f"wipe_out_{pass_index}", station.wipe_end_xyz_mm, new_rotary,
               station.wipe_feedrate_mm_min),
            at(f"wipe_back_{pass_index}", station.wipe_start_xyz_mm, new_rotary,
               station.wipe_feedrate_mm_min),
        ))
    resume.append(above("leave_wipe", station.wipe_start_xyz_mm, new_rotary))
    if approach_mode == "vertical":
        resume.append(move("return_above", after["X"], after["Y"], safe, new_rotary))
    elif approach_mode != "direct":
        axis, direction = approach_mode.split("_")
        offset = lateral_offset if direction == "plus" else -lateral_offset
        x = after["X"] + (offset if axis == "x" else 0.0)
        y = after["Y"] + (offset if axis == "y" else 0.0)
        resume.append(move("return_via_side", x, y, safe, new_rotary))
    resume.append(ServiceMove("safe_approach", dict(after), station.travel_feedrate_mm_min))
    return {"cut": cut, "park": park, "purge": purge, "resume": tuple(resume)}


def _nozzle_sections(profile, maximum_axial_step=0.5):
    if len(profile) == 1:
        return ((profile[0][0], profile[0][1], 0.0, 0.0),)
    values = []
    for (radius_a, height_a), (radius_b, height_b) in zip(profile, profile[1:]):
        subdivisions = max(1, math.ceil((height_b - height_a) / maximum_axial_step))
        for index in range(subdivisions):
            fraction = index / subdivisions
            values.append((
                radius_a + (radius_b - radius_a) * fraction,
                height_a + (height_b - height_a) * fraction,
            ))
    values.append(profile[-1])
    sections = []
    for index, (radius, height) in enumerate(values):
        lower_step = (height - values[index - 1][1]) / 2.0 if index else 0.0
        upper_step = (
            (values[index + 1][1] - height) / 2.0
            if index + 1 < len(values) else 0.0
        )
        slope = max(
            (abs(values[neighbor][0] - radius) / abs(values[neighbor][1] - height)
             for neighbor in (index - 1, index + 1)
             if 0 <= neighbor < len(values)
             and abs(values[neighbor][1] - height) > 1.0e-12),
            default=0.0,
        )
        sections.append((
            radius + slope * max(lower_step, upper_step),
            height, lower_step, upper_step,
        ))
    return tuple(sections)


def _sample_move(
    before, after, machine, tool_length, sections, T_workpiece_from_build,
    sample_step, *, label, exempt_recent,
):
    delta_xyz = math.dist(
        (before["X"], before["Y"], before["Z"]),
        (after["X"], after["Y"], after["Z"]),
    )
    reach = max(
        math.hypot(radius, height)
        for radius, height, _lower_step, _upper_step in sections
    )
    angular = abs(after["A"] - before["A"]) + abs(after["C"] - before["C"])
    count = max(1, math.ceil((delta_xyz + angular * reach) / sample_step))
    samples = []
    fixed_rotary = angular <= 1.0e-12

    def tool_pose(joints):
        transforms = machine.forward_kinematics(joints)
        assert machine.workpiece_link_id is not None and machine.tool_link_id is not None
        to_workpiece = transforms[machine.workpiece_link_id].inverse()
        mount = transforms[machine.tool_link_id].translation
        tip = (mount[0], mount[1], mount[2] - tool_length)
        origin = to_workpiece.transform_point(tip)
        axial = to_workpiece.transform_point((tip[0], tip[1], tip[2] + 1.0))
        if T_workpiece_from_build is not None:
            inverse = T_workpiece_from_build.inverse()
            origin = inverse.transform_point(origin)
            axial = inverse.transform_point(axial)
        return origin, tuple(axial[index] - origin[index] for index in range(3))

    if fixed_rotary:
        first_origin, first_axis = tool_pose(before)
        last_origin, last_axis = tool_pose(after)
    for sample_index in range(1, count + 1):
        fraction = sample_index / count
        if fixed_rotary:
            origin = tuple(
                first_origin[index] + (last_origin[index] - first_origin[index]) * fraction
                for index in range(3)
            )
            axis = tuple(
                first_axis[index] + (last_axis[index] - first_axis[index]) * fraction
                for index in range(3)
            )
        else:
            joints = {
                axis: before[axis] + (after[axis] - before[axis]) * fraction
                for axis in ("X", "Y", "Z", "A", "C")
            }
            origin, axis = tool_pose(joints)
        for radius, height, lower_step, upper_step in sections:
            center = tuple(origin[index] + axis[index] * height for index in range(3))
            samples.append((
                center, radius, axis, lower_step, upper_step, label,
                exempt_recent and sample_index == 1,
                height, delta_xyz * (1.0 - fraction),
            ))
    return samples


def _check_printed_part(
    toolpath, sequence, service_samples, maximum_radius, *, checkpoint,
    error_code="tool_change.printed_part_collision",
    bond_tip_window_mm=0.0, bond_tip_max_overlap_mm=0.0,
    depart_tip_window_mm=0.0, move_length_mm=0.0,
    nozzle_profile=None,
    printed_index=None,
):
    query_samples = service_samples
    if nozzle_profile is not None:
        # A tip pose defines the entire revolved nozzle. Checking every
        # conservative axial section would enlarge the orifice spuriously.
        service_samples = [sample for sample in service_samples if sample[7] <= 1.0e-9]
    # Index the short service route, not the potentially million-segment part.
    # Each deposited segment is visited once and can be discarded immediately.
    cell_size = max(1.0, 2.0 * maximum_radius)
    cells = {}
    for sample_id, (
        center, _radius, _axis, _lower_step, _upper_step, _label, _exempt,
        _height, _remaining,
    ) in enumerate(service_samples):
        key = tuple(math.floor(value / cell_size) for value in center)
        cells.setdefault(key, []).append(sample_id)
    lower = tuple(min(item[0][axis] for item in service_samples) for axis in range(3))
    upper = tuple(max(item[0][axis] for item in service_samples) for axis in range(3))
    vertical_nozzle = (
        nozzle_profile is not None
        and all(math.dist(sample[2], (0.0, 0.0, 1.0)) <= 1.0e-6
                for sample in service_samples)
    )
    points = toolpath.points
    allowed_tip_contacts = 0
    candidates = (
        range(1, sequence)
        if printed_index is None
        else printed_index.candidates(
            query_samples, sequence, planar_exact=nozzle_profile is not None,
            maximum_height=(nozzle_profile[-1][1] if nozzle_profile is not None else None),
        )
    )
    if nozzle_profile is not None and not vertical_nozzle:
        return _check_profiled_tilted_samples(
            points, sequence, service_samples, candidates, nozzle_profile,
            maximum_radius, checkpoint=checkpoint, error_code=error_code,
            bond_tip_window_mm=bond_tip_window_mm,
            bond_tip_max_overlap_mm=bond_tip_max_overlap_mm,
            depart_tip_window_mm=depart_tip_window_mm,
            move_length_mm=move_length_mm,
        )
    if nozzle_profile is not None and vertical_nozzle:
        deposited = [index for index in candidates if points[index].point_type == "deposition"]
        if deposited and all(
            points[index].bead_width_mm is not None
            and points[index].layer_height_mm is not None
            and abs(points[index - 1].position[2] - points[index].position[2]) <= 1.0e-6
            and math.dist(points[index].nozzle_axis, (0.0, 0.0, -1.0)) <= 1.0e-6
            for index in deposited
        ):
            return _check_profiled_vertical_planar_samples(
                points, sequence, service_samples, deposited, nozzle_profile,
                error_code=error_code, bond_tip_window_mm=bond_tip_window_mm,
                bond_tip_max_overlap_mm=bond_tip_max_overlap_mm,
                depart_tip_window_mm=depart_tip_window_mm,
                move_length_mm=move_length_mm,
            )
    for index in candidates:
        if checkpoint is not None and index % 4096 == 0:
            checkpoint()
        right = points[index]
        if right.point_type != "deposition":
            continue
        start = points[index - 1].position
        end = right.position
        bead_radius = max(right.bead_width_mm or 0.0, right.layer_height_mm or 0.0) / 2.0
        planar_bead = (
            nozzle_profile is not None
            and right.bead_width_mm is not None
            and right.layer_height_mm is not None
            and abs(start[2] - end[2]) <= 1.0e-6
            and math.dist(right.nozzle_axis, (0.0, 0.0, -1.0)) <= 1.0e-6
        )
        planar_vertical = planar_bead and vertical_nozzle
        padding = bead_radius + maximum_radius + 0.5
        if nozzle_profile is not None and not planar_vertical:
            padding += nozzle_profile[-1][1]
        if any(
            max(start[axis], end[axis]) + padding < lower[axis]
            or min(start[axis], end[axis]) - padding > upper[axis]
            for axis in range(3)
        ):
            continue
        if nozzle_profile is not None and not planar_vertical:
            sample_ids = range(len(service_samples))
        else:
            ranges = tuple(
                range(
                    math.floor((min(start[axis], end[axis]) - padding) / cell_size),
                    math.floor((max(start[axis], end[axis]) + padding) / cell_size) + 1,
                )
                for axis in range(3)
            )
            sample_ids = {
                sample_id
                for key in product(*ranges)
                for sample_id in cells.get(key, ())
            }
        for sample_id in sample_ids:
                (
                    center, radius, axis, lower_step, upper_step, label, exempt_recent,
                    height, remaining,
                ) = service_samples[sample_id]
                if any(
                    center[coordinate] < min(start[coordinate], end[coordinate]) - padding
                    or center[coordinate] > max(start[coordinate], end[coordinate]) + padding
                    for coordinate in range(3)
                ):
                    continue
                if exempt_recent and index >= sequence - 2:
                    continue
                if planar_vertical:
                    contact = _planar_bead_nozzle_contact(
                        center, start, end, right.bead_width_mm,
                        right.layer_height_mm, nozzle_profile,
                    )
                    if contact is None:
                        continue
                    separation, bead_radius, contact_height = contact
                    collision_center = (
                        center[0], center[1], center[2] + contact_height
                    )
                elif nozzle_profile is not None:
                    # Non-planar path coordinates are the deposited layer's
                    # exposed surface. Place the conservative round-bead
                    # surrogate inside that surface, tangent at the path,
                    # instead of letting half its diameter protrude through
                    # the nozzle-side surface.
                    first_axis = points[index - 1].nozzle_axis
                    shifted_start = tuple(
                        start[coordinate] + first_axis[coordinate] * bead_radius
                        for coordinate in range(3)
                    )
                    shifted_end = tuple(
                        end[coordinate] + right.nozzle_axis[coordinate] * bead_radius
                        for coordinate in range(3)
                    )
                    if _section_radial_distance(
                        center, axis, nozzle_profile[-1][1] + bead_radius,
                        shifted_start, shifted_end,
                    ) > maximum_radius + bead_radius:
                        continue
                    separation, contact_height = _profile_to_segment_distance(
                        center, axis, nozzle_profile, shifted_start, shifted_end,
                    )
                    collision_center = tuple(
                        center[coordinate] + axis[coordinate] * contact_height
                        for coordinate in range(3)
                    )
                else:
                    distance = _section_radial_distance(
                        center, axis, max(lower_step, upper_step) + bead_radius,
                        start, end,
                    )
                    if distance > radius + bead_radius:
                        continue
                    separation = _section_to_segment_distance(
                        center, axis, lower_step, upper_step, radius, start, end,
                    )
                    contact_height = height
                    collision_center = center
                if separation <= bead_radius:
                        target = points[sequence] if sequence < len(points) else None
                        next_deposition = (
                            sequence + 1 < len(points)
                            and points[sequence + 1].point_type == "deposition"
                        )
                        planar_same_layer_bond = (
                            planar_bead
                            and next_deposition
                            and target is not None
                            and target.operation_id == right.operation_id
                            and target.layer_id == right.layer_id
                            and target.region_id == right.region_id
                            and bond_tip_window_mm > 0.0
                            and remaining <= 1.0e-9
                            and contact_height <= 1.0e-9
                            and center[2] >= end[2] - 1.0e-6
                        )
                        if planar_same_layer_bond:
                            allowed_tip_contacts += 1
                            continue
                        if (
                            (
                                (bond_tip_window_mm > 0.0
                                 and remaining <= bond_tip_window_mm)
                                or (depart_tip_window_mm > 0.0
                                    and move_length_mm > 0.0
                                    and move_length_mm - remaining <= depart_tip_window_mm)
                            )
                            and contact_height <= 1.0e-9
                            and bead_radius - separation <= bond_tip_max_overlap_mm
                        ):
                            allowed_tip_contacts += 1
                            continue
                        raise ToolChangeCollisionError(
                            right.point_id, label, collision_center, start, end,
                            separation, bead_radius, code=error_code,
                            section_height_mm=contact_height,
                            remaining_travel_mm=remaining,
                        )
    return allowed_tip_contacts


def _check_profiled_tilted_samples(
    points, sequence, samples, candidates, profile, maximum_radius, *,
    checkpoint, error_code, bond_tip_window_mm, bond_tip_max_overlap_mm,
    depart_tip_window_mm, move_length_mm,
):
    records = []
    shifted_starts = []
    shifted_ends = []
    bead_radii = []
    for index in candidates:
        if checkpoint is not None and index % 4096 == 0:
            checkpoint()
        right = points[index]
        if right.point_type != "deposition":
            continue
        left = points[index - 1]
        bead_radius = max(right.bead_width_mm or 0.0, right.layer_height_mm or 0.0) / 2.0
        records.append((index, left.position, right.position, right))
        shifted_starts.append(tuple(
            left.position[coordinate] + left.nozzle_axis[coordinate] * bead_radius
            for coordinate in range(3)
        ))
        shifted_ends.append(tuple(
            right.position[coordinate] + right.nozzle_axis[coordinate] * bead_radius
            for coordinate in range(3)
        ))
        bead_radii.append(bead_radius)
    if not records:
        return 0
    starts = np.asarray(shifted_starts, dtype=float)
    ends = np.asarray(shifted_ends, dtype=float)
    radii = np.asarray(bead_radii, dtype=float)
    allowed_tip_contacts = 0
    profile_height = profile[-1][1]
    for center, _radius, axis, _lower, _upper, label, exempt_recent, _, remaining in samples:
        direction = np.asarray(axis, dtype=float)
        tip = np.asarray(center, dtype=float)
        offset = starts - tip
        span = ends - starts
        axial_start = offset @ direction
        axial_span = span @ direction
        radial_start = offset - axial_start[:, None] * direction
        radial_span = span - axial_span[:, None] * direction
        radial_start_squared = np.einsum("ij,ij->i", radial_start, radial_start)
        radial_span_squared = np.einsum("ij,ij->i", radial_span, radial_span)
        radial_cross = np.einsum("ij,ij->i", radial_start, radial_span)
        nearest = np.clip(
            -radial_cross / np.maximum(radial_span_squared, 1.0e-18),
            0.0, 1.0,
        )
        minimum_radial = np.sqrt(np.maximum(
            0.0,
            radial_start_squared + nearest * (
                2.0 * radial_cross + nearest * radial_span_squared
            ),
        ))
        axial_end = axial_start + axial_span
        possible = (
            (minimum_radial <= maximum_radius + radii)
            & (np.maximum(axial_start, axial_end) >= -radii)
            & (np.minimum(axial_start, axial_end) <= profile_height + radii)
        )
        if exempt_recent:
            possible &= np.asarray([record[0] < sequence - 2 for record in records])
        active = np.flatnonzero(possible)
        if len(active) == 0:
            continue
        distances, contact_heights = _profile_to_segments_distance_batch(
            center, axis, profile, starts[active], ends[active],
        )
        colliding = np.flatnonzero(distances <= radii[active])
        for hit in colliding:
            record_index = active[hit]
            index, start, end, right = records[record_index]
            separation = float(distances[hit])
            contact_height = float(contact_heights[hit])
            bead_radius = bead_radii[record_index]
            target = points[sequence] if sequence < len(points) else None
            next_deposition = (
                sequence + 1 < len(points)
                and points[sequence + 1].point_type == "deposition"
            )
            planar_bead = (
                right.bead_width_mm is not None
                and right.layer_height_mm is not None
                and abs(start[2] - end[2]) <= 1.0e-6
                and math.dist(right.nozzle_axis, (0.0, 0.0, -1.0)) <= 1.0e-6
            )
            planar_same_layer_bond = (
                planar_bead and next_deposition and target is not None
                and target.operation_id == right.operation_id
                and target.layer_id == right.layer_id
                and target.region_id == right.region_id
                and bond_tip_window_mm > 0.0
                and remaining <= 1.0e-9
                and contact_height <= 1.0e-9
                and center[2] >= end[2] - 1.0e-6
            )
            if planar_same_layer_bond:
                allowed_tip_contacts += 1
                continue
            if (
                (
                    (bond_tip_window_mm > 0.0 and remaining <= bond_tip_window_mm)
                    or (depart_tip_window_mm > 0.0 and move_length_mm > 0.0
                        and move_length_mm - remaining <= depart_tip_window_mm)
                )
                and contact_height <= 1.0e-9
                and bead_radius - separation <= bond_tip_max_overlap_mm
            ):
                allowed_tip_contacts += 1
                continue
            collision_center = tuple(
                center[coordinate] + axis[coordinate] * contact_height
                for coordinate in range(3)
            )
            raise ToolChangeCollisionError(
                right.point_id, label, collision_center, start, end,
                separation, bead_radius, code=error_code,
                section_height_mm=contact_height,
                remaining_travel_mm=remaining,
            )
    return allowed_tip_contacts


def _check_profiled_vertical_planar_samples(
    points, sequence, samples, deposited, profile, *, error_code,
    bond_tip_window_mm, bond_tip_max_overlap_mm,
    depart_tip_window_mm, move_length_mm,
):
    """Check finite planar beads against a vertical nozzle in XY/Z batches.

    The printed point is the bead's exposed layer top. Only the actual
    layer-height interval below it is occupied; a spherical width radius
    would incorrectly put material above that surface.
    """
    starts = np.asarray([points[index - 1].position[:2] for index in deposited])
    ends = np.asarray([points[index].position[:2] for index in deposited])
    tops = np.asarray([points[index].position[2] for index in deposited])
    heights = np.asarray([points[index].layer_height_mm for index in deposited])
    radii = np.asarray([points[index].bead_width_mm / 2.0 for index in deposited])
    span = ends - starts
    span_squared = np.einsum("ij,ij->i", span, span)
    profile_heights = np.asarray([height for _, height in profile])
    profile_radii = np.asarray([radius for radius, _ in profile])
    target = points[sequence] if sequence < len(points) else None
    next_deposition = (
        sequence + 1 < len(points)
        and points[sequence + 1].point_type == "deposition"
    )
    allowed = 0
    for center, _radius, _axis, _lower, _upper, label, exempt_recent, _, remaining in samples:
        low = np.maximum(0.0, tops - heights - center[2])
        high = np.minimum(profile_heights[-1], tops - center[2])
        possible = high >= low - 1.0e-9
        if exempt_recent:
            possible &= np.asarray(deposited) < sequence - 2
        active = np.flatnonzero(possible)
        if not len(active):
            continue
        lower = low[active]
        upper = high[active]
        lower_radius = np.interp(lower, profile_heights, profile_radii)
        upper_radius = np.interp(upper, profile_heights, profile_radii)
        nozzle_radius = np.maximum(lower_radius, upper_radius)
        contact_height = np.where(lower_radius >= upper_radius, lower, upper)
        for radius, height in profile:
            inside = (lower < height) & (height < upper) & (radius > nozzle_radius)
            nozzle_radius = np.where(inside, radius, nozzle_radius)
            contact_height = np.where(inside, height, contact_height)
        offset = np.asarray(center[:2]) - starts[active]
        fraction = np.clip(
            np.einsum("ij,ij->i", offset, span[active])
            / np.maximum(span_squared[active], 1.0e-18), 0.0, 1.0,
        )
        delta = offset - fraction[:, None] * span[active]
        distance_xy = np.linalg.norm(delta, axis=1)
        separation = np.maximum(0.0, distance_xy - nozzle_radius)
        for hit in np.flatnonzero(separation <= radii[active]):
            record = active[hit]
            index = deposited[record]
            right = points[index]
            section_height = float(contact_height[hit])
            distance = float(separation[hit])
            bead_radius = float(radii[record])
            planar_same_layer_bond = (
                next_deposition and target is not None
                and target.operation_id == right.operation_id
                and target.layer_id == right.layer_id
                and target.region_id == right.region_id
                and bond_tip_window_mm > 0.0
                and remaining <= 1.0e-9
                and section_height <= 1.0e-9
                and center[2] >= tops[record] - 1.0e-6
            )
            if planar_same_layer_bond:
                allowed += 1
                continue
            if (
                ((bond_tip_window_mm > 0.0 and remaining <= bond_tip_window_mm)
                 or (depart_tip_window_mm > 0.0 and move_length_mm > 0.0
                     and move_length_mm - remaining <= depart_tip_window_mm))
                and section_height <= 1.0e-9
                and bead_radius - distance <= bond_tip_max_overlap_mm
            ):
                allowed += 1
                continue
            raise ToolChangeCollisionError(
                right.point_id, label,
                (center[0], center[1], center[2] + section_height),
                points[index - 1].position, right.position,
                distance, bead_radius, code=error_code,
                section_height_mm=section_height,
                remaining_travel_mm=remaining,
            )
    return allowed


def _planar_bead_nozzle_contact(tip, start, end, bead_width, layer_height, profile):
    """Exact vertical overlap of a horizontal bead and piecewise-linear cone.

    A planar path position is the printed layer top. The bead occupies only
    the layer-height interval below it, with bead width in XY. Profile radii
    are evaluated at their actual heights, not an inflated axial sample bin.
    """

    top = end[2]
    lower = max(0.0, top - layer_height - tip[2])
    upper = min(profile[-1][1], top - tip[2])
    if upper < lower - 1.0e-9:
        return None

    def radius_at(height):
        if height <= profile[0][1]:
            return profile[0][0]
        for (first_radius, first_height), (last_radius, last_height) in zip(
            profile, profile[1:]
        ):
            if height <= last_height:
                ratio = (height - first_height) / (last_height - first_height)
                return first_radius + ratio * (last_radius - first_radius)
        return profile[-1][0]

    heights = (lower, upper, *(height for _, height in profile if lower < height < upper))
    contact_height = max(heights, key=radius_at)
    nozzle_radius = radius_at(contact_height)
    span_x, span_y = end[0] - start[0], end[1] - start[1]
    length_squared = span_x * span_x + span_y * span_y
    fraction = (
        0.0 if length_squared <= 1.0e-18
        else max(0.0, min(1.0,
            ((tip[0] - start[0]) * span_x + (tip[1] - start[1]) * span_y)
            / length_squared,
        ))
    )
    distance_xy = math.hypot(
        tip[0] - start[0] - fraction * span_x,
        tip[1] - start[1] - fraction * span_y,
    )
    bead_radius = bead_width / 2.0
    separation = max(0.0, distance_xy - nozzle_radius)
    return separation, bead_radius, contact_height


def _profile_to_segment_distance(tip, axis, profile, start, end):
    """Distance from a deposited centreline to the actual revolved nozzle.

    Each consecutive profile pair forms a convex truncated cone. Distance to
    one cone is convex along a straight deposited segment, so the bounded
    search checks the continuous profile without inflating the orifice radius
    to cover an axial sampling bin.
    """

    offset = tuple(start[index] - tip[index] for index in range(3))
    span = tuple(end[index] - start[index] for index in range(3))
    axial_start = sum(offset[index] * axis[index] for index in range(3))
    axial_span = sum(span[index] * axis[index] for index in range(3))
    radial_start = tuple(
        offset[index] - axis[index] * axial_start for index in range(3)
    )
    radial_span = tuple(
        span[index] - axis[index] * axial_span for index in range(3)
    )
    radial_constant = sum(value * value for value in radial_start)
    radial_linear = sum(a * b for a, b in zip(radial_start, radial_span))
    radial_quadratic = sum(value * value for value in radial_span)
    pairs = tuple(zip(profile, profile[1:])) or ((profile[0], profile[0]),)
    best = (math.inf, 0.0)
    for first, last in pairs:
        first_radius, first_height = first
        last_radius, last_height = last
        profile_height = last_height - first_height
        profile_radius = last_radius - first_radius
        edges = (
            (first_height, 0.0, 0.0, first_radius, first_radius * first_radius),
            (first_height, first_radius, profile_height, profile_radius,
             profile_height * profile_height + profile_radius * profile_radius),
            (last_height, last_radius, 0.0, -last_radius, last_radius * last_radius),
        )

        def separation(fraction):
            height = axial_start + fraction * axial_span
            radial = math.sqrt(max(
                0.0,
                radial_constant + fraction * (2.0 * radial_linear + fraction * radial_quadratic),
            ))
            if first_height <= height <= last_height:
                along = 0.0 if profile_height == 0.0 else (height - first_height) / profile_height
                if radial <= first_radius + profile_radius * along:
                    return 0.0, height
            nearest = (math.inf, 0.0)
            for edge_height, edge_radius, dh, dr, length_squared in edges:
                along = (
                    0.0 if length_squared <= 1.0e-18
                    else max(0.0, min(1.0,
                        ((height - edge_height) * dh + (radial - edge_radius) * dr)
                        / length_squared,
                    ))
                )
                closest_height = edge_height + along * dh
                distance = math.hypot(
                    height - closest_height,
                    radial - edge_radius - along * dr,
                )
                if distance < nearest[0]:
                    nearest = (distance, closest_height)
            return nearest

        lower, upper = 0.0, 1.0
        for _ in range(28):
            left = lower + (upper - lower) * 0.3819660112501051
            right = upper - (upper - lower) * 0.3819660112501051
            if separation(left)[0] <= separation(right)[0]:
                upper = right
            else:
                lower = left
        for fraction in (0.0, 1.0, (lower + upper) / 2.0):
            candidate = separation(fraction)
            if candidate[0] < best[0]:
                best = candidate
    return best


def _profile_to_segments_distance_batch(tip, axis, profile, starts, ends):
    """Evaluate the same convex frustum distance for many candidate beads."""

    offset = starts - np.asarray(tip, dtype=float)
    span = ends - starts
    direction = np.asarray(axis, dtype=float)
    axial_start = offset @ direction
    axial_span = span @ direction
    radial_start = offset - axial_start[:, None] * direction
    radial_span = span - axial_span[:, None] * direction
    radial_constant = np.einsum("ij,ij->i", radial_start, radial_start)
    radial_linear = np.einsum("ij,ij->i", radial_start, radial_span)
    radial_quadratic = np.einsum("ij,ij->i", radial_span, radial_span)
    count = len(starts)
    best_distance = np.full(count, np.inf)
    best_height = np.zeros(count)

    for (first_radius, first_height), (last_radius, last_height) in (
        tuple(zip(profile, profile[1:])) or ((profile[0], profile[0]),)
    ):
        profile_height = last_height - first_height
        profile_radius = last_radius - first_radius
        edges = (
            (first_height, 0.0, 0.0, first_radius, first_radius * first_radius),
            (first_height, first_radius, profile_height, profile_radius,
             profile_height * profile_height + profile_radius * profile_radius),
            (last_height, last_radius, 0.0, -last_radius, last_radius * last_radius),
        )

        def separation(fraction):
            height = axial_start + fraction * axial_span
            radial = np.sqrt(np.maximum(
                0.0,
                radial_constant + fraction * (2.0 * radial_linear + fraction * radial_quadratic),
            ))
            distance = np.full(count, np.inf)
            contact_height = np.zeros(count)
            for edge_height, edge_radius, dh, dr, length_squared in edges:
                along = (
                    np.zeros(count) if length_squared <= 1.0e-18
                    else np.clip(
                        ((height - edge_height) * dh + (radial - edge_radius) * dr)
                        / length_squared, 0.0, 1.0,
                    )
                )
                closest_height = edge_height + along * dh
                candidate = np.hypot(
                    height - closest_height,
                    radial - edge_radius - along * dr,
                )
                better = candidate < distance
                distance = np.where(better, candidate, distance)
                contact_height = np.where(better, closest_height, contact_height)
            if profile_height == 0.0:
                radius_at_height = np.full(count, first_radius)
            else:
                radius_at_height = first_radius + profile_radius * (
                    (height - first_height) / profile_height
                )
            inside = (
                (height >= first_height) & (height <= last_height)
                & (radial <= radius_at_height)
            )
            return np.where(inside, 0.0, distance), np.where(
                inside, height, contact_height,
            )

        lower = np.zeros(count)
        upper = np.ones(count)
        for _ in range(28):
            left = lower + (upper - lower) * 0.3819660112501051
            right = upper - (upper - lower) * 0.3819660112501051
            left_distance, _ = separation(left)
            right_distance, _ = separation(right)
            choose_left = left_distance <= right_distance
            upper = np.where(choose_left, right, upper)
            lower = np.where(choose_left, lower, left)
        for fraction in (np.zeros(count), np.ones(count), (lower + upper) / 2.0):
            candidate_distance, candidate_height = separation(fraction)
            better = candidate_distance < best_distance
            best_distance = np.where(better, candidate_distance, best_distance)
            best_height = np.where(better, candidate_height, best_height)
    return best_distance, best_height


class _PrintedSegmentIndex:
    """Conservative spatial cache for deposited segments before a service move.

    Each segment occupies every grid cell intersecting its bead/nozzle-padded
    bounding box. Querying sample-centre cells can only add candidates; the
    existing exact section-to-segment check remains the collision criterion.
    """

    def __init__(self, toolpath, maximum_radius, *, checkpoint=None):
        self.cell_size = max(1.0, 4.0 * maximum_radius)
        self.planar_xy_size = max(1.0, 2.0 * maximum_radius)
        self.planar_z_size = 1.0
        self.nonplanar_cells = {}
        self.planar_cells = {}
        self.planar_broad_cells = None
        self._planar_bounds = []
        self.maximum_radius = maximum_radius
        points = toolpath.points
        for index in range(1, len(points)):
            if checkpoint is not None and index % 4096 == 0:
                checkpoint()
            right = points[index]
            if right.point_type != "deposition":
                continue
            start, end = points[index - 1].position, right.position
            bead_radius = max(right.bead_width_mm or 0.0, right.layer_height_mm or 0.0) / 2.0
            padding = bead_radius + maximum_radius + 0.5
            planar = (
                right.bead_width_mm is not None
                and right.layer_height_mm is not None
                and abs(start[2] - end[2]) <= 1.0e-6
                and math.dist(right.nozzle_axis, (0.0, 0.0, -1.0)) <= 1.0e-6
            )
            if planar:
                self._planar_bounds.append((index, start, end, padding))
                xy_ranges = tuple(
                    range(
                        math.floor((min(start[axis], end[axis]) - padding) / self.planar_xy_size),
                        math.floor((max(start[axis], end[axis]) + padding) / self.planar_xy_size) + 1,
                    )
                    for axis in (0, 1)
                )
                top_bucket = math.floor(end[2] / self.planar_z_size)
                for xy in product(*xy_ranges):
                    self.planar_cells.setdefault((*xy, top_bucket), []).append(index)
                continue
            ranges = tuple(
                range(
                    math.floor((min(start[axis], end[axis]) - padding) / self.cell_size),
                    math.floor((max(start[axis], end[axis]) + padding) / self.cell_size) + 1,
                )
                for axis in range(3)
            )
            for key in product(*ranges):
                self.nonplanar_cells.setdefault(key, []).append(index)

    def _build_planar_broad_cells(self):
        if self.planar_broad_cells is not None:
            return
        broad = {}
        for index, start, end, padding in self._planar_bounds:
            ranges = tuple(
                range(
                    math.floor((min(start[axis], end[axis]) - padding) / self.cell_size),
                    math.floor((max(start[axis], end[axis]) + padding) / self.cell_size) + 1,
                )
                for axis in range(3)
            )
            for key in product(*ranges):
                broad.setdefault(key, []).append(index)
        self.planar_broad_cells = broad

    def candidates(
        self, service_samples, sequence, *, planar_exact=True, maximum_height=None,
    ):
        candidate_indices = set()
        vertical_tip_positions = set()
        need_planar_broad = False
        if maximum_height is None:
            maximum_height = max(sample[7] for sample in service_samples)
        for center, _radius, axis, _lower, _upper, _label, _exempt, height, _remaining in service_samples:
            key = tuple(math.floor(value / self.cell_size) for value in center)
            candidate_indices.update(self.nonplanar_cells.get(key, ()))
            if planar_exact and math.dist(axis, (0.0, 0.0, 1.0)) <= 1.0e-6:
                if height <= 1.0e-9:
                    vertical_tip_positions.add(tuple(center))
            else:
                need_planar_broad = True
        for tip in vertical_tip_positions:
            x_bucket = math.floor(tip[0] / self.planar_xy_size)
            y_bucket = math.floor(tip[1] / self.planar_xy_size)
            # A horizontal bead can meet the vertical nozzle only at or above
            # the tip.  Query its actual layer-top bin, not every lower layer
            # inside the nozzle's broad 3-D sphere.
            first_z = math.floor((tip[2] - 1.0e-9) / self.planar_z_size)
            last_z = math.floor((tip[2] + maximum_height + 1.0e-9) / self.planar_z_size)
            for z_bucket in range(first_z, last_z + 1):
                candidate_indices.update(self.planar_cells.get(
                    (x_bucket, y_bucket, z_bucket), (),
                ))
        if need_planar_broad:
            self._build_planar_broad_cells()
            assert self.planar_broad_cells is not None
            for center, _radius, axis, *_ in service_samples:
                if planar_exact and math.dist(axis, (0.0, 0.0, 1.0)) <= 1.0e-6:
                    continue
                key = tuple(math.floor(value / self.cell_size) for value in center)
                candidate_indices.update(self.planar_broad_cells.get(key, ()))
        return sorted(index for index in candidate_indices if index < sequence)


def _section_radial_distance(center, axis, axial_tolerance, start, end):
    offset = tuple(start[index] - center[index] for index in range(3))
    span = tuple(end[index] - start[index] for index in range(3))
    axial_start = sum(offset[index] * axis[index] for index in range(3))
    axial_span = sum(span[index] * axis[index] for index in range(3))
    if abs(axial_span) <= 1.0e-12:
        if abs(axial_start) > axial_tolerance:
            return math.inf
        lower, upper = 0.0, 1.0
    else:
        first = (-axial_tolerance - axial_start) / axial_span
        second = (axial_tolerance - axial_start) / axial_span
        lower, upper = max(0.0, min(first, second)), min(1.0, max(first, second))
        if lower > upper:
            return math.inf
    radial_start = tuple(offset[index] - axis[index] * axial_start for index in range(3))
    radial_span = tuple(span[index] - axis[index] * axial_span for index in range(3))
    denominator = sum(value * value for value in radial_span)
    optimum = (
        lower if denominator <= 1.0e-18
        else max(lower, min(upper, -sum(a * b for a, b in zip(radial_start, radial_span)) / denominator))
    )
    return math.sqrt(sum(
        (radial_start[index] + optimum * radial_span[index]) ** 2 for index in range(3)
    ))


def _section_to_segment_distance(
    center, axis, lower_step, upper_step, radius, start, end,
):
    """Minimum distance from a deposited centreline to a finite nozzle section.

    A section is a closed cylinder. Its distance function is convex along a
    straight segment, so bounded golden-section search covers the corner where
    separate radial and axial clearances would otherwise give a false hit.
    """

    offset = tuple(start[index] - center[index] for index in range(3))
    span = tuple(end[index] - start[index] for index in range(3))

    def distance_squared(fraction):
        position = tuple(offset[index] + fraction * span[index] for index in range(3))
        axial = sum(position[index] * axis[index] for index in range(3))
        radial_squared = max(
            0.0, sum(value * value for value in position) - axial * axial,
        )
        axial_gap = max(0.0, -lower_step - axial, axial - upper_step)
        radial_gap = max(0.0, math.sqrt(radial_squared) - radius)
        return axial_gap * axial_gap + radial_gap * radial_gap

    lower, upper = 0.0, 1.0
    golden = (math.sqrt(5.0) - 1.0) / 2.0
    left = upper - golden * (upper - lower)
    right = lower + golden * (upper - lower)
    left_value, right_value = distance_squared(left), distance_squared(right)
    for _ in range(32):
        if left_value <= right_value:
            upper, right, right_value = right, left, left_value
            left = upper - golden * (upper - lower)
            left_value = distance_squared(left)
        else:
            lower, left, left_value = left, right, right_value
            right = lower + golden * (upper - lower)
            right_value = distance_squared(right)
    return math.sqrt(min(
        distance_squared(0.0), distance_squared(1.0),
        left_value, right_value,
    ))


__all__ = [
    "ServiceMove", "ToolChangeCollisionError", "ToolChangeServicePlan",
    "check_non_deposition_travel_safety", "check_operation_transition_safety",
    "plan_tool_change_service",
]
