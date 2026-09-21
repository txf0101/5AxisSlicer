"""XYZAC trajectory solving with an explicit Rotary path phase.

The generic XYZAC solver is free to choose equivalent rotary solutions.  A
Rotary operation is different: its unwrapped workpiece phase is part of the
manufacturing plan.  This adapter keeps that phase beside every toolpath point,
uses it when selecting the next equivalent IK branch, and timestamps motion
against both the requested linear feed and the requested angular-speed limit.
Machine A/C values remain the result of IK; a workpiece phase is not assumed to
be the controller C word for a generally oriented Build coordinate system.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.machine import MachineProfile
from ..manufacturing.setup import ValidationIssue
from ..manufacturing.toolpath import GeneratedToolpath
from ..models import Vector3
from .xyzac import (
    MachineAxisSample,
    MachineAxisTrajectory,
    XYZACInverseKinematicsError,
    _fk_reconstruct,
    _motion_limit_issues,
    _singularity_issues,
    _solve_linear,
    _solve_rotary,
    _transform_toolpath_point,
    _unit,
    _xyzac_axes,
)


def solve_prescribed_rotary_trajectory(
    toolpath: GeneratedToolpath,
    profile: MachineProfile,
    *,
    prescribed_angles_rad: Mapping[str, float],
    angular_velocity_rad_s: float,
    tool_length_mm: float = 0.0,
    fixed_machine_nozzle_axis: Vector3 = (0.0, 0.0, -1.0),
    T_workpiece_from_build: RigidTransform | None = None,
) -> MachineAxisTrajectory:
    """Solve a Rotary path without discarding its continuous workpiece phase.

    ``prescribed_angles_rad`` is keyed by the stable ``ToolpathPoint.point_id``.
    It is used for winding continuity and timing.  The first two non-singular
    solutions establish whether the selected XYZAC branch maps increasing
    workpiece phase to increasing or decreasing C.  Later equivalent C
    candidates are selected against that prescribed winding, so a 0/360
    crossing or complete turn cannot silently collapse to a shorter branch.
    The accepted A/C values are checked by FK for every point.
    """

    if not math.isfinite(angular_velocity_rad_s) or angular_velocity_rad_s <= 0.0:
        raise ValueError("rotary.angular_velocity_rad_s_invalid")
    if not math.isfinite(tool_length_mm) or tool_length_mm < 0.0:
        raise ValueError("tool_length_mm must be finite and non-negative")
    point_ids = {point.point_id for point in toolpath.points}
    missing = point_ids - set(prescribed_angles_rad)
    extra = set(prescribed_angles_rad) - point_ids
    if missing or extra:
        raise ValueError(
            f"rotary.prescribed_phase_mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    angles = {key: float(value) for key, value in prescribed_angles_rad.items()}
    if any(not math.isfinite(value) for value in angles.values()):
        raise ValueError("rotary.period_non_finite")

    axes = _xyzac_axes(profile)
    fixed_axis = _unit(fixed_machine_nozzle_axis)
    samples: list[MachineAxisSample] = []
    issues: list[ValidationIssue] = []
    previous_positions: Mapping[str, float] | None = None
    previous_point = None
    previous_angle: float | None = None
    phase_reference: float | None = None
    c_reference: float | None = None
    phase_to_c_sign: float | None = None
    elapsed = 0.0

    for point in toolpath.points:
        target = _transform_toolpath_point(point, T_workpiece_from_build)
        phase = angles[point.point_id]
        preferred_c = None
        if phase_to_c_sign is not None and phase_reference is not None and c_reference is not None:
            preferred_c = c_reference + phase_to_c_sign * (phase - phase_reference)
        rotary, singular = _solve_rotary(
            target,
            axes["A"],
            axes["C"],
            fixed_axis,
            previous_positions,
            preferred_c=preferred_c,
        )
        if preferred_c is not None and abs(rotary["C"] - preferred_c) > 1.0e-7:
            raise XYZACInverseKinematicsError(
                "rotary.phase_machine_axis_mismatch",
                point.point_id,
                f"phase={phase}, expected_c={preferred_c}, solved_c={rotary['C']}",
            )
        if not singular and abs(rotary["A"]) > 1.0e-8:
            if phase_reference is None or c_reference is None:
                phase_reference = phase
                c_reference = rotary["C"]
            elif phase_to_c_sign is None:
                phase_delta = phase - phase_reference
                c_delta = rotary["C"] - c_reference
                if abs(phase_delta) > 1.0e-10:
                    if abs(abs(c_delta) - abs(phase_delta)) > 1.0e-7:
                        raise XYZACInverseKinematicsError(
                            "rotary.phase_machine_axis_mismatch",
                            point.point_id,
                            f"phase_delta={phase_delta}, c_delta={c_delta}",
                        )
                    phase_to_c_sign = 1.0 if c_delta * phase_delta > 0.0 else -1.0
        positions, contact = _solve_linear(
            target,
            profile,
            rotary,
            fixed_axis,
            tool_length_mm,
        )
        if previous_positions is not None and previous_point is not None:
            assert previous_angle is not None
            path_distance = math.dist(previous_point.position, point.position)
            feed = point.feedrate_mm_min or 60.0
            linear_duration = path_distance / feed * 60.0
            angular_duration = abs(phase - previous_angle) / angular_velocity_rad_s
            elapsed += max(linear_duration, angular_duration, 1.0e-6)
        reconstructed, angular_error = _fk_reconstruct(
            target,
            profile,
            positions,
            fixed_axis,
            tool_length_mm,
        )
        position_error = math.dist(reconstructed, target.position)
        if position_error > 0.01 or angular_error > math.radians(0.01):
            raise XYZACInverseKinematicsError(
                "xyzac.fk_round_trip_failed",
                point.point_id,
                f"{position_error}, {angular_error}",
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
        previous_positions = positions
        previous_point = point
        previous_angle = phase

    issues.extend(_singularity_issues(samples))
    issues.extend(_motion_limit_issues(samples, profile))
    return MachineAxisTrajectory(
        f"{toolpath.toolpath_id}-rotary-xyzac-v1",
        profile.profile_id,
        toolpath.toolpath_id,
        tuple(samples),
        tuple(issues),
        float(tool_length_mm),
    )


__all__ = ["solve_prescribed_rotary_trajectory"]
