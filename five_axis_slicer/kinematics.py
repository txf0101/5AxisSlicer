"""Kinematics helpers for the Open5x-style rotary-bed printer.

The math follows the idea described by Freddie Hong's paper:
1. tilt the bed by U about the machine Y axis,
2. rotate by V about the moving local axis [sin(U), 0, cos(U)].
"""

from __future__ import annotations

import math

import numpy as np

from .core import MachineParameters


def normal_to_rotary_angles(normal: np.ndarray, previous_v_deg: float | None = None) -> tuple[float, float]:
    """Convert a target surface normal into physical bed angles.

    Returned values are the *mathematical* bed angles used by the kinematic
    model, before any machine-specific sign inversion or zero offset is applied.
    """

    normal = np.asarray(normal, dtype=float)
    length = float(np.linalg.norm(normal))
    if length < 1e-9:
        return 0.0, previous_v_deg or 0.0
    normal = normal / length

    nz = float(np.clip(normal[2], -1.0, 1.0))
    u_rad = math.acos(nz)
    sin_u = math.sin(u_rad)
    if abs(sin_u) < 1e-9:
        v_deg = previous_v_deg or 0.0
    else:
        v_deg = math.degrees(math.atan2(normal[1], -normal[0]))
        if previous_v_deg is not None:
            v_deg = unwrap_angle(v_deg, previous_v_deg)
    return math.degrees(u_rad), v_deg


def apply_rotary_axis_calibration(
    u_deg: float,
    v_deg: float,
    machine: MachineParameters,
    previous_commanded_v_deg: float | None = None,
) -> tuple[float, float]:
    """Map mathematical bed angles to the actual machine command angles."""

    commanded_u = machine.u_zero_offset_deg + machine.u_axis_sign * u_deg
    commanded_v = machine.v_zero_offset_deg + machine.v_axis_sign * v_deg
    if previous_commanded_v_deg is not None:
        commanded_v = unwrap_angle(commanded_v, previous_commanded_v_deg)
    return commanded_u, commanded_v


def machine_position_for_point(
    point: np.ndarray,
    u_deg: float,
    v_deg: float,
    machine: MachineParameters,
) -> np.ndarray:
    """Forward-kinematic position of a model point after the bed rotates."""

    point = np.asarray(point, dtype=float)
    rotation = compose_bed_rotation(u_deg, v_deg)
    rotated = rotation @ (point - machine.rotary_center) + machine.rotary_center
    return rotated + machine.build_offset


def compose_bed_rotation(u_deg: float, v_deg: float) -> np.ndarray:
    u_rad = math.radians(u_deg)
    v_rad = math.radians(v_deg)
    ry = np.array(
        [
            [math.cos(u_rad), 0.0, math.sin(u_rad)],
            [0.0, 1.0, 0.0],
            [-math.sin(u_rad), 0.0, math.cos(u_rad)],
        ],
        dtype=float,
    )
    axis = np.array([math.sin(u_rad), 0.0, math.cos(u_rad)], dtype=float)
    rv = axis_angle_rotation(axis, v_rad)
    return rv @ ry


def axis_angle_rotation(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    axis_length = float(np.linalg.norm(axis))
    if axis_length < 1e-9 or abs(angle_rad) < 1e-12:
        return np.eye(3, dtype=float)
    axis = axis / axis_length
    x, y, z = axis
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    one_c = 1.0 - c
    return np.array(
        [
            [c + x * x * one_c, x * y * one_c - z * s, x * z * one_c + y * s],
            [y * x * one_c + z * s, c + y * y * one_c, y * z * one_c - x * s],
            [z * x * one_c - y * s, z * y * one_c + x * s, c + z * z * one_c],
        ],
        dtype=float,
    )


def unwrap_angle(angle_deg: float, reference_deg: float) -> float:
    """Return the equivalent angle closest to the previous command."""

    candidates = [angle_deg + k * 360.0 for k in (-1, 0, 1)]
    return min(candidates, key=lambda candidate: abs(candidate - reference_deg))


def shortest_angular_delta_deg(target_deg: float, source_deg: float) -> float:
    delta = target_deg - source_deg
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return delta
