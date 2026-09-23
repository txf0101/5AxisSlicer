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
    ):
        self.code = code
        self.point_id = point_id
        self.label = label
        self.center = center
        self.start = start
        self.end = end
        self.distance = distance
        self.clearance = clearance
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
    profile = nozzle.outer_profile_rz_mm or ((nozzle.orifice_diameter_mm / 2.0, 0.0),)
    sections = _nozzle_sections(profile)
    radius = max(item[0] for item in sections)
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
    for sample_index in range(1, count + 1):
        fraction = sample_index / count
        joints = {
            axis: before[axis] + (after[axis] - before[axis]) * fraction
            for axis in ("X", "Y", "Z", "A", "C")
        }
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
        axis = tuple(axial[index] - origin[index] for index in range(3))
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
):
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
    points = toolpath.points
    allowed_tip_contacts = 0
    for index in range(1, sequence):
        if checkpoint is not None and index % 4096 == 0:
            checkpoint()
        right = points[index]
        if right.point_type != "deposition":
            continue
        start = points[index - 1].position
        end = right.position
        bead_radius = max(right.bead_width_mm or 0.0, right.layer_height_mm or 0.0) / 2.0
        padding = bead_radius + maximum_radius + 0.5
        if any(
            max(start[axis], end[axis]) + padding < lower[axis]
            or min(start[axis], end[axis]) - padding > upper[axis]
            for axis in range(3)
        ):
            continue
        ranges = tuple(
            range(
                math.floor((min(start[axis], end[axis]) - padding) / cell_size),
                math.floor((max(start[axis], end[axis]) + padding) / cell_size) + 1,
            )
            for axis in range(3)
        )
        visited = set()
        for key in product(*ranges):
            for sample_id in cells.get(key, ()):
                if sample_id in visited:
                    continue
                visited.add(sample_id)
                (
                    center, radius, axis, lower_step, upper_step, label, exempt_recent,
                    height, remaining,
                ) = service_samples[sample_id]
                if exempt_recent and index >= sequence - 2:
                    continue
                distance = _section_radial_distance(
                    center, axis, max(lower_step, upper_step) + bead_radius,
                    start, end,
                )
                if distance <= radius + bead_radius:
                    separation = _section_to_segment_distance(
                        center, axis, lower_step, upper_step, radius, start, end,
                    )
                    if separation <= bead_radius:
                        if (
                            bond_tip_window_mm > 0.0
                            and height <= 1.0e-9
                            and remaining <= bond_tip_window_mm
                            and bead_radius - separation <= bond_tip_max_overlap_mm
                        ):
                            allowed_tip_contacts += 1
                            continue
                        raise ToolChangeCollisionError(
                            right.point_id, label, center, start, end,
                            separation, bead_radius, code=error_code,
                        )
    return allowed_tip_contacts


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
    "check_operation_transition_safety", "plan_tool_change_service",
]
