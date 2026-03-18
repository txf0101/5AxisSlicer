"""Kinematics helpers for the Open5x-style rotary-bed printer.

The math follows the idea described by Freddie Hong's paper:
1. tilt the bed by U about the machine Y axis,
2. rotate by V about the moving local axis [sin(U), 0, cos(U)].
"""

from __future__ import annotations

import math

import numpy as np

from .core import MachineParameters

# These helpers stay in mathematical bed-angle space first. Machine
# calibration gets applied later so the geometry math stays easier to reason
# about.
# 这些辅助函数先处理“数学上的床面角度”，机床标定留到后面再叠加，几何关系
# 会更清楚。


def normal_to_rotary_angles(normal: np.ndarray, previous_v_deg: float | None = None) -> tuple[float, float]:
    """Convert a target surface normal into bed angles.

    把目标表面法向换成床面该到的角度。

    The returned values are still the mathematical angles from the kinematic
    model.
    真正的机床符号和零位补偿还没加进去，返回的仍是运动学模型里的数学角度。
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
    """Map mathematical bed angles onto the command angles sent to the machine.
    把数学模型中的床面角度映射为真实机床指令角度。
    Axis sign, zero offset, and bounded equivalent-angle selection all happen
    here.
    轴方向、零位补偿和行程范围内的等价角选择都在这里处理。
    """

    commanded_u = machine.u_zero_offset_deg + machine.u_axis_sign * u_deg
    commanded_v = machine.v_zero_offset_deg + machine.v_axis_sign * v_deg
    reference_v_deg = previous_commanded_v_deg if previous_commanded_v_deg is not None else machine.home_v_deg
    commanded_v = choose_bounded_equivalent_angle(
        commanded_v,
        reference_v_deg,
        machine.min_v_deg,
        machine.max_v_deg,
    )
    return commanded_u, commanded_v


def machine_position_for_point(
    point: np.ndarray,
    u_deg: float,
    v_deg: float,
    machine: MachineParameters,
) -> np.ndarray:
    """Forward-kinematic position of a model point after the bed rotates.

    计算模型点在床面旋转之后对应的前向运动学位置。

    The returned XYZ is already shifted by the configured machine build
    offset.
    返回的 XYZ 已经叠加了配置里的机床建系偏移。
    """

    point = np.asarray(point, dtype=float)
    rotation = compose_bed_rotation(u_deg, v_deg)
    rotated = rotation @ (point - machine.rotary_center) + machine.rotary_center
    return rotated + machine.build_offset


def compose_bed_rotation(u_deg: float, v_deg: float) -> np.ndarray:
    """Compose the two-stage bed rotation used by Open5x-style machines.

    组合 Open5x 风格机床使用的两级床面旋转。

    The bed tilts around machine Y by ``U`` and then spins around the tilted
    local axis by ``V``.
    床面先绕机器 Y 轴按 ``U`` 倾斜，再绕倾斜后的局部轴按 ``V`` 旋转。
    """

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
    """Return a Rodrigues rotation matrix for an arbitrary axis.

    使用 Rodrigues 公式生成任意旋转轴的旋转矩阵。
    """

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
    """Pick the equivalent angle closest to the previous command.

    在一组等价角里挑出最接近上一条指令的那个。

    That keeps the exported motion from adding needless full turns.
    这样能少掉很多没必要的大回转。
    """

    candidates = [angle_deg + k * 360.0 for k in (-1, 0, 1)]
    return min(candidates, key=lambda candidate: abs(candidate - reference_deg))


def choose_bounded_equivalent_angle(
    angle_deg: float,
    reference_deg: float,
    min_deg: float,
    max_deg: float,
) -> float:
    """Pick the equivalent angle that stays inside machine travel.

    选出既落在机床行程里、又最贴近参考角的那个等价角。
    """

    if min_deg > max_deg:
        min_deg, max_deg = max_deg, min_deg

    min_turns = math.ceil((min_deg - angle_deg) / 360.0)
    max_turns = math.floor((max_deg - angle_deg) / 360.0)
    if min_turns <= max_turns:
        candidates = [angle_deg + 360.0 * turns for turns in range(min_turns, max_turns + 1)]
        return min(candidates, key=lambda candidate: (abs(candidate - reference_deg), abs(candidate)))

    return unwrap_angle(angle_deg, reference_deg)


def shortest_angular_delta_deg(target_deg: float, source_deg: float) -> float:
    """Compute the signed shortest angular difference from source to target.

    计算从源角度到目标角度的带符号最短角差。
    """

    delta = target_deg - source_deg
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return delta
