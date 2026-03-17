"""Thin adapter for the local Open5x Python port.

This module intentionally only imports the pure-Python Open5x code under
``Open5x-main/.../open5x``. Rhino-dependent helpers are not used here.
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

_OPEN5X_REFINEMENT_INTERVAL = 128
_OPEN5X_SINGULAR_NORMAL_Z = 0.9995


@lru_cache(maxsize=1)
def _open5x_api():
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
    return machine_params.v_axis_sign * (command_v_deg - machine_params.v_zero_offset_deg)


def _should_refine_with_open5x(index: int, point_count: int, normal: np.ndarray) -> bool:
    if point_count <= 0:
        return False
    if index == 0:
        return True
    if index % _OPEN5X_REFINEMENT_INTERVAL == 0:
        return True
    return abs(float(normal[2])) >= _OPEN5X_SINGULAR_NORMAL_Z


def _align_equivalent_angle(angle_deg: float, reference_deg: float) -> float:
    return reference_deg + shortest_angular_delta_deg(angle_deg, reference_deg)


def _select_best_candidate(
    base_u_deg: float,
    base_v_deg: float,
    machine_params: MachineParameters,
    *,
    reference_u_deg: float,
    reference_v_deg: float,
) -> tuple[float, float, float, float]:
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
