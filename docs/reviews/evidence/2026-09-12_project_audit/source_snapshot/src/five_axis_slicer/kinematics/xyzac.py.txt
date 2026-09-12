"""Analytic inverse kinematics for the registered XYZAC reference topology.

The workpiece transform is evaluated by ``MachineProfile`` rather than copied
into this module. The analytic orientation solve assumes the registered A-then-C
workpiece chain and a fixed machine nozzle axis. FK reconstruction closes every
accepted sample and includes both the configured rotary centres and tool length.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
from types import MappingProxyType
from typing import Any, Mapping

from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.machine import JointSpec, MachineProfile
from ..manufacturing.setup import IssueSeverity, ValidationIssue
from ..manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from ..models import Vector3

_ORIENTATION_TOLERANCE_RAD = math.radians(0.01)
_POSITION_TOLERANCE_MM = 0.01


class XYZACInverseKinematicsError(ValueError):
    def __init__(self, code: str, point_id: str, detail: str = "") -> None:
        self.code = str(code)
        self.point_id = str(point_id)
        self.detail = str(detail)
        super().__init__(f"{self.code} at {self.point_id}: {self.detail}")


@dataclass(frozen=True, slots=True)
class MachineAxisSample:
    source_point_id: str
    time_s: float
    joint_positions: Mapping[str, float] = field(hash=False)
    tool_tip_machine_mm: Vector3 = (0.0, 0.0, 0.0)
    fk_position_error_mm: float = 0.0
    fk_orientation_error_rad: float = 0.0
    singular: bool = False

    def __post_init__(self) -> None:
        positions = {str(key): float(value) for key, value in self.joint_positions.items()}
        if not positions or any(not math.isfinite(value) for value in positions.values()):
            raise ValueError("joint_positions must contain finite values")
        if not math.isfinite(self.time_s) or self.time_s < 0.0:
            raise ValueError("time_s must be finite and non-negative")
        object.__setattr__(self, "joint_positions", MappingProxyType(positions))

    def to_json(self) -> dict[str, Any]:
        return {
            "source_point_id": self.source_point_id,
            "time_s": self.time_s,
            "joint_positions": dict(self.joint_positions),
            "tool_tip_machine_mm": list(self.tool_tip_machine_mm),
            "fk_position_error_mm": self.fk_position_error_mm,
            "fk_orientation_error_rad": self.fk_orientation_error_rad,
            "singular": self.singular,
        }


@dataclass(frozen=True, slots=True)
class MachineAxisTrajectory:
    trajectory_id: str
    machine_profile_id: str
    source_toolpath_id: str
    samples: tuple[MachineAxisSample, ...]
    issues: tuple[ValidationIssue, ...] = ()
    tool_length_mm: float = 0.0

    def __post_init__(self) -> None:
        samples, issues = tuple(self.samples), tuple(self.issues)
        if any(not isinstance(item, MachineAxisSample) for item in samples):
            raise TypeError("samples must contain MachineAxisSample")
        if any(not isinstance(item, ValidationIssue) for item in issues):
            raise TypeError("issues must contain ValidationIssue")
        if not math.isfinite(self.tool_length_mm) or self.tool_length_mm < 0.0:
            raise ValueError("tool_length_mm must be finite and non-negative")
        if any(right.time_s <= left.time_s for left, right in zip(samples, samples[1:])):
            raise ValueError("trajectory sample time must be strictly increasing")
        object.__setattr__(self, "samples", samples)
        object.__setattr__(self, "issues", issues)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "trajectory_id": self.trajectory_id,
            "machine_profile_id": self.machine_profile_id,
            "source_toolpath_id": self.source_toolpath_id,
            "tool_length_mm": self.tool_length_mm,
            "samples": [sample.to_json() for sample in self.samples],
            "issues": [issue.to_json() for issue in self.issues],
        }


def solve_xyzac_trajectory(
    toolpath: GeneratedToolpath,
    profile: MachineProfile,
    *,
    tool_length_mm: float = 0.0,
    fixed_machine_nozzle_axis: Vector3 = (0.0, 0.0, -1.0),
    T_workpiece_from_build: RigidTransform | None = None,
) -> MachineAxisTrajectory:
    """Solve XYZAC samples and report motion-limit violations."""

    axes = _xyzac_axes(profile)
    fixed_axis = _unit(fixed_machine_nozzle_axis)
    samples: list[MachineAxisSample] = []
    issues: list[ValidationIssue] = []
    previous: Mapping[str, float] | None = None
    elapsed = 0.0
    for point in toolpath.points:
        target = _transform_toolpath_point(point, T_workpiece_from_build)
        rotary, singular = _solve_rotary(target, axes["A"], axes["C"], fixed_axis, previous)
        positions, contact = _solve_linear(target, profile, rotary, fixed_axis, tool_length_mm)
        if previous is not None:
            elapsed += _requested_duration(point, positions, previous)
        reconstructed, angular_error = _fk_reconstruct(
            target, profile, positions, fixed_axis, tool_length_mm
        )
        position_error = math.dist(reconstructed, target.position)
        if position_error > _POSITION_TOLERANCE_MM or angular_error > _ORIENTATION_TOLERANCE_RAD:
            raise XYZACInverseKinematicsError(
                "xyzac.fk_round_trip_failed", point.point_id, f"{position_error}, {angular_error}"
            )
        if singular:
            issues.append(
                ValidationIssue(
                    "xyzac.rotary_singularity",
                    IssueSeverity.WARNING,
                    point.point_id,
                    {"retained_c_rad": positions["C"]},
                )
            )
        samples.append(
            MachineAxisSample(
                point.point_id,
                elapsed,
                positions,
                contact,
                position_error,
                angular_error,
                singular,
            )
        )
        previous = positions
    issues.extend(_motion_limit_issues(samples, profile))
    return MachineAxisTrajectory(
        f"{toolpath.toolpath_id}-xyzac-v1",
        profile.profile_id,
        toolpath.toolpath_id,
        tuple(samples),
        tuple(issues),
        float(tool_length_mm),
    )


def _transform_toolpath_point(
    point: ToolpathPoint,
    transform: RigidTransform | None,
) -> ToolpathPoint:
    if transform is None:
        return point
    return replace(
        point,
        position=transform.transform_point(point.position),
        tangent=transform.transform_vector(point.tangent),
        nozzle_axis=transform.transform_vector(point.nozzle_axis),
        surface_normal=(
            None
            if point.surface_normal is None
            else transform.transform_vector(point.surface_normal)
        ),
    )


def _xyzac_axes(profile: MachineProfile) -> dict[str, JointSpec]:
    profile.validate()
    axes = profile.joint_map
    required = {"X": "linear", "Y": "linear", "Z": "linear", "A": "rotary", "C": "rotary"}
    if any(name not in axes or axes[name].joint_type != kind for name, kind in required.items()):
        raise ValueError("profile does not provide the required XYZAC axes")
    if axes["A"].motion_side != "workpiece" or axes["C"].motion_side != "workpiece":
        raise ValueError("A and C must be workpiece-side axes")
    if profile.workpiece_link_id is None:
        raise ValueError("profile requires a workpiece endpoint")
    return {name: axes[name] for name in required}


def _solve_rotary(
    point: ToolpathPoint,
    a_axis: JointSpec,
    c_axis: JointSpec,
    fixed_axis: Vector3,
    previous: Mapping[str, float] | None,
) -> tuple[dict[str, float], bool]:
    if math.dist(fixed_axis, (0.0, 0.0, -1.0)) > 1.0e-9:
        raise ValueError("the analytic XYZAC solver requires fixed machine nozzle axis (0,0,-1)")
    qx, qy, qz = _unit(point.nozzle_axis)
    radial = math.hypot(qx, qy)
    if radial <= 1.0e-8:
        if qz > 0.0:
            raise XYZACInverseKinematicsError("xyzac.orientation_unreachable", point.point_id)
        c_value = 0.0 if previous is None else previous["C"]
        return {"A": 0.0, "C": c_value}, True
    angle = math.acos(max(-1.0, min(1.0, -qz)))
    candidates = (
        (angle, math.atan2(-qx, -qy)),
        (-angle, math.atan2(qx, qy)),
    )
    feasible: list[tuple[float, float]] = []
    for a_value, base_c in candidates:
        if not _within(a_axis, a_value):
            continue
        feasible.extend(
            (a_value, c_value)
            for c_value in _angle_equivalents(base_c, c_axis)
            if _within(c_axis, c_value)
        )
    if not feasible:
        raise XYZACInverseKinematicsError("xyzac.orientation_unreachable", point.point_id)
    seed_a = 0.0 if previous is None else previous["A"]
    seed_c = 0.0 if previous is None else previous["C"]
    a_value, c_value = min(
        feasible,
        key=lambda item: abs(item[0] - seed_a) + abs(item[1] - seed_c),
    )
    return {"A": a_value, "C": c_value}, False


def _solve_linear(
    point: ToolpathPoint,
    profile: MachineProfile,
    rotary: Mapping[str, float],
    fixed_axis: Vector3,
    tool_length_mm: float,
) -> tuple[dict[str, float], Vector3]:
    assert profile.workpiece_link_id is not None
    transform = profile.link_transform(profile.workpiece_link_id, rotary)
    contact = transform.transform_point(point.position)
    mount = _subtract(contact, _scale(fixed_axis, float(tool_length_mm)))
    positions = {"X": mount[0], "Y": mount[1], "Z": mount[2], **rotary}
    for name, value in positions.items():
        axis = profile.joint_map[name]
        try:
            axis.effective_position(value)
        except ValueError as exc:
            raise XYZACInverseKinematicsError("xyzac.axis_limit", point.point_id, name) from exc
    return positions, contact


def _fk_reconstruct(
    point: ToolpathPoint,
    profile: MachineProfile,
    positions: Mapping[str, float],
    fixed_axis: Vector3,
    tool_length_mm: float,
) -> tuple[Vector3, float]:
    assert profile.tool_link_id is not None and profile.workpiece_link_id is not None
    transforms = profile.forward_kinematics(positions)
    mount = transforms[profile.tool_link_id].translation
    tip = _add(mount, _scale(fixed_axis, float(tool_length_mm)))
    workpiece = transforms[profile.workpiece_link_id]
    reconstructed = workpiece.inverse().transform_point(tip)
    reconstructed_axis = workpiece.inverse().transform_vector(fixed_axis)
    angular_error = math.acos(
        max(-1.0, min(1.0, _dot(_unit(reconstructed_axis), _unit(point.nozzle_axis))))
    )
    return reconstructed, angular_error


def _requested_duration(
    point: ToolpathPoint,
    positions: Mapping[str, float],
    previous: Mapping[str, float],
) -> float:
    distance = math.dist(
        (positions["X"], positions["Y"], positions["Z"]),
        (previous["X"], previous["Y"], previous["Z"]),
    )
    feed = point.feedrate_mm_min or 60.0
    return max(distance / feed * 60.0, 1.0e-6)


def _motion_limit_issues(
    samples: list[MachineAxisSample], profile: MachineProfile
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    velocities: list[dict[str, float]] = []
    for index, (left, right) in enumerate(zip(samples, samples[1:])):
        duration = right.time_s - left.time_s
        velocity = {
            name: (right.joint_positions[name] - left.joint_positions[name]) / duration
            for name in left.joint_positions
        }
        velocities.append(velocity)
        for name, value in velocity.items():
            limit = profile.joint_map[name].max_velocity
            if limit is not None and abs(value) > limit + 1.0e-9:
                issues.append(_limit_issue("velocity", name, index + 1, value, limit))
    for index, (left_velocity, right_velocity) in enumerate(zip(velocities, velocities[1:])):
        duration = (samples[index + 2].time_s - samples[index].time_s) * 0.5
        for name in left_velocity:
            value = (right_velocity[name] - left_velocity[name]) / duration
            limit = profile.joint_map[name].max_acceleration
            if limit is not None and abs(value) > limit + 1.0e-9:
                issues.append(_limit_issue("acceleration", name, index + 1, value, limit))
    return issues


def _limit_issue(kind: str, axis: str, index: int, value: float, limit: float) -> ValidationIssue:
    return ValidationIssue(
        f"xyzac.{kind}_limit_exceeded",
        IssueSeverity.ERROR,
        f"sample-{index}",
        {"axis": axis, "value": value, "limit": limit},
    )


def _angle_equivalents(value: float, axis: JointSpec) -> tuple[float, ...]:
    low = -2.0 * math.pi if axis.soft_limit_min is None else axis.soft_limit_min
    high = 2.0 * math.pi if axis.soft_limit_max is None else axis.soft_limit_max
    minimum = math.floor((low - value) / (2.0 * math.pi)) - 1
    maximum = math.ceil((high - value) / (2.0 * math.pi)) + 1
    return tuple(value + turn * 2.0 * math.pi for turn in range(minimum, maximum + 1))


def _within(axis: JointSpec, value: float) -> bool:
    try:
        axis.effective_position(value)
    except ValueError:
        return False
    return True


def _unit(value: Vector3) -> Vector3:
    length = math.sqrt(_dot(value, value))
    if length <= 1.0e-12:
        raise ValueError("zero-length vector")
    return _scale(value, 1.0 / length)


def _add(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a + b for a, b in zip(left, right))  # type: ignore[return-value]


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(left, right))  # type: ignore[return-value]


def _scale(value: Vector3, factor: float) -> Vector3:
    return tuple(item * factor for item in value)  # type: ignore[return-value]


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right))


__all__ = [
    "MachineAxisSample",
    "MachineAxisTrajectory",
    "XYZACInverseKinematicsError",
    "solve_xyzac_trajectory",
]
