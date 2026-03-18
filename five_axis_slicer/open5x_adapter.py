"""Thin adapter for the local Open5x Python port.

Only the pure-Python Open5x code under ``Open5x-main/.../open5x`` is imported
here. Rhino-facing helpers are left out.
"""

from __future__ import annotations

import importlib
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

from .core import MachineParameters
from .kinematics import (
    apply_rotary_axis_calibration,
    normal_to_rotary_angles,
    shortest_angular_delta_deg,
)

# The vendored Open5x Python port is used here as an optional refinement pass.
# If it is missing, the local solver still carries the job.
# 这里把仓库内的 Open5x Python 移植版当成可选的精修求解器。

_OPEN5X_REFINEMENT_INTERVAL = 128
_OPEN5X_SINGULAR_NORMAL_Z = 0.9995


@lru_cache(maxsize=1)
def _open5x_api():
    """Locate and import the vendored pure-Python Open5x modules.

    定位并导入仓库里附带的纯 Python Open5x 模块。

    This project only needs the math and model pieces, so Rhino-facing helpers
    are left alone.
    这个项目只用得上里面的数学层和模型层，依赖 Rhino 的那部分先不碰。
    """

    grasshopper_dir = Path(__file__).resolve().parents[1] / 'Open5x-main' / 'Open5x-main' / 'Grasshopper_Definition'
    package_dir = grasshopper_dir / 'open5x'
    if not package_dir.exists():
        return None

    grasshopper_dir_str = str(grasshopper_dir)
    if grasshopper_dir_str not in sys.path:
        sys.path.insert(0, grasshopper_dir_str)

    try:
        models = importlib.import_module('open5x.models')
        kinematics = importlib.import_module('open5x.kinematics')
    except Exception:
        return None
    return models, kinematics


def has_open5x_solver() -> bool:
    """Return whether the local Open5x solver entry point is available.

    判断本地 Open5x 求解器入口当前是否可用。
    """

    api = _open5x_api()
    return api is not None and hasattr(api[1], 'solve_rotation')


def solve_toolpath_raw_angles_open5x(
    points: np.ndarray,
    normals: np.ndarray,
    machine_params: MachineParameters,
    *,
    previous_command_u_deg: float | None,
    previous_command_v_deg: float | None,
) -> list[tuple[float, float]] | None:
    """Resolve raw rotary angles with Open5x help when it is available.
    能借到 Open5x 的时候，就用它帮整条路径求原始回转角。
    The returned values are still raw mathematical angles. Machine calibration
    gets applied later in the G-code layer.
    返回的仍然是原始数学角度，真正的机床补偿会在后面的 G-code 层再加上去。
    """

    del points

    api = _open5x_api()
    if api is None:
        return None

    models, kinematics = api
    if not hasattr(kinematics, 'solve_rotation'):
        raise RuntimeError('Local Open5x Python package does not expose solve_rotation().')

    machine = models.MachineConfig(rotation_order=('z', 'y'))
    normals = np.asarray(normals, dtype=float)
    if len(normals) == 0:
        return []

    resolved_angles: list[tuple[float, float]] = []
    reference_u_deg = machine_params.home_u_deg if previous_command_u_deg is None else previous_command_u_deg
    reference_v_deg = machine_params.home_v_deg if previous_command_v_deg is None else previous_command_v_deg
    previous_raw_v_deg = _command_to_raw_v(reference_v_deg, machine_params)

    # Start with the local analytic solution for every point, then occasionally
    # let Open5x refine the awkward parts such as singular poses or long paths.
    # 每个点都会先走本地解析解，遇到奇异姿态附近或较长路径时，再周期性让
    # Open5x 补一刀精修。
    for index, normal in enumerate(normals):
        base_u_deg, base_v_deg = normal_to_rotary_angles(normal, previous_v_deg=previous_raw_v_deg)
        if _should_refine_with_open5x(index, len(normals), normal):
            solved_rotation_deg = np.asarray(
                kinematics.solve_rotation(
                    normal,
                    machine,
                    seed_rotation_deg=np.array([base_v_deg, base_u_deg], dtype=float),
                ),
                dtype=float,
            )
            if solved_rotation_deg.shape != (2,):
                raise RuntimeError('Open5x solve_rotation() returned an invalid rotation shape.')
            base_v_deg = _align_equivalent_angle(float(solved_rotation_deg[0]), base_v_deg)
            base_u_deg = _align_equivalent_angle(float(solved_rotation_deg[1]), base_u_deg)

        raw_u_deg, raw_v_deg, command_u_deg, command_v_deg = _select_best_candidate(
            base_u_deg,
            base_v_deg,
            machine_params,
            reference_u_deg=reference_u_deg,
            reference_v_deg=reference_v_deg,
        )
        resolved_angles.append((raw_u_deg, raw_v_deg))
        previous_raw_v_deg = raw_v_deg
        reference_u_deg = command_u_deg
        reference_v_deg = command_v_deg

    return resolved_angles


def _command_to_raw_v(command_v_deg: float, machine_params: MachineParameters) -> float:
    """Convert a V-axis command angle back into raw mathematical angle space.

    把 V 轴指令角换回原始数学角空间。
    """

    return machine_params.v_axis_sign * (command_v_deg - machine_params.v_zero_offset_deg)


def _should_refine_with_open5x(index: int, point_count: int, normal: np.ndarray) -> bool:
    """Cheap heuristic for deciding when Open5x refinement is worth using.

    用一个轻量启发式判断什么时候值得调用更贵的 Open5x 精修。
    """

    if point_count <= 0:
        return False
    if index == 0:
        return True
    if index % _OPEN5X_REFINEMENT_INTERVAL == 0:
        return True
    return abs(float(normal[2])) >= _OPEN5X_SINGULAR_NORMAL_Z


def _align_equivalent_angle(angle_deg: float, reference_deg: float) -> float:
    """Move an angle onto the equivalent branch closest to ``reference_deg``.

    把角度移动到最接近 ``reference_deg`` 的等价分支上。
    """

    return reference_deg + shortest_angular_delta_deg(angle_deg, reference_deg)


def _select_best_candidate(
    base_u_deg: float,
    base_v_deg: float,
    machine_params: MachineParameters,
    *,
    reference_u_deg: float,
    reference_v_deg: float,
) -> tuple[float, float, float, float]:
    """Choose the equivalent rotary solution that is friendliest to the machine.
    从一组等价回转解里挑出最适合真实机床的那一个。
    Solutions that stay within travel and remain close to the previous command
    score better.
    优先考虑不越界、而且离上一条指令更近的解。
    """

    best: tuple[float, float, float, float] | None = None
    best_score = float('inf')

    for raw_u_deg, raw_v_deg in _candidate_raw_pairs(base_u_deg, base_v_deg):
        command_u_deg, command_v_deg = apply_rotary_axis_calibration(
            raw_u_deg,
            raw_v_deg,
            machine_params,
            previous_commanded_v_deg=reference_v_deg,
        )
        score = _candidate_score(
            command_u_deg,
            command_v_deg,
            machine_params,
            reference_u_deg=reference_u_deg,
            reference_v_deg=reference_v_deg,
        )
        if score < best_score:
            best_score = score
            best = (raw_u_deg, raw_v_deg, command_u_deg, command_v_deg)

    if best is None:
        raise RuntimeError('Open5x angle candidate selection failed.')
    return best


def _candidate_raw_pairs(base_u_deg: float, base_v_deg: float) -> list[tuple[float, float]]:
    """Enumerate analytically equivalent raw ``(U, V)`` angle pairs.

    枚举解析上等价的 ``(U, V)`` 原始角组合。
    """

    return [
        (base_u_deg, base_v_deg),
        (-base_u_deg, base_v_deg + 180.0),
        (-base_u_deg, base_v_deg - 180.0),
    ]


def _candidate_score(
    command_u_deg: float,
    command_v_deg: float,
    machine_params: MachineParameters,
    *,
    reference_u_deg: float,
    reference_v_deg: float,
) -> float:
    """Score a candidate by travel-limit pressure and motion continuity.
    按行程压力和运动连续性给候选指令角打分。
    Lower is better for the real machine.
    分数越低，对真实机床越稳妥。
    """

    outside_u_deg = 0.0
    if command_u_deg < machine_params.min_u_deg:
        outside_u_deg = machine_params.min_u_deg - command_u_deg
    elif command_u_deg > machine_params.max_u_deg:
        outside_u_deg = command_u_deg - machine_params.max_u_deg

    outside_v_deg = 0.0
    if command_v_deg < machine_params.min_v_deg:
        outside_v_deg = machine_params.min_v_deg - command_v_deg
    elif command_v_deg > machine_params.max_v_deg:
        outside_v_deg = command_v_deg - machine_params.max_v_deg

    delta_u_deg = abs(command_u_deg - reference_u_deg)
    delta_v_deg = abs(shortest_angular_delta_deg(command_v_deg, reference_v_deg))

    return outside_u_deg * 1000.0 + outside_v_deg * 1000.0 + delta_u_deg + delta_v_deg
