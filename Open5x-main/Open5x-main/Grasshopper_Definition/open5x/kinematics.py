from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .models import MachineConfig, PathSpec, Pose
from .vector_math import AXIS_MAP, normalize, unwrap_degrees


def rotation_from_axis_pair(axes: tuple[str, str], angles_rad: np.ndarray) -> Rotation:
    rotation = Rotation.identity()
    for axis_name, angle in zip(axes, angles_rad, strict=True):
        rotation = Rotation.from_rotvec(AXIS_MAP[axis_name] * angle) * rotation
    return rotation


def _solve_single_pose(
    normal: np.ndarray,
    machine: MachineConfig,
    seed_rad: np.ndarray | None,
) -> np.ndarray:
    target = normalize(np.asarray(machine.tool_axis, dtype=float))
    source = normalize(normal)
    axes = machine.rotation_order

    def residual(angles: np.ndarray) -> np.ndarray:
        rotation = rotation_from_axis_pair(axes, angles)
        return rotation.apply(source) - target

    if seed_rad is not None:
        result = least_squares(residual, x0=seed_rad, xtol=1e-10, ftol=1e-10, gtol=1e-10)
        if float(np.linalg.norm(residual(result.x))) <= 1e-5:
            return result.x

    guesses = [
        np.zeros(2, dtype=float),
        np.array([np.pi / 2.0, 0.0]),
        np.array([-np.pi / 2.0, 0.0]),
        np.array([0.0, np.pi / 2.0]),
        np.array([0.0, -np.pi / 2.0]),
    ]
    best = None
    best_cost = float("inf")
    for guess in guesses:
        result = least_squares(residual, x0=guess, xtol=1e-10, ftol=1e-10, gtol=1e-10)
        cost = float(np.linalg.norm(residual(result.x)))
        if cost < best_cost:
            best = result.x
            best_cost = cost
    if best is None or best_cost > 1e-5:
        raise RuntimeError(f"Could not solve inverse kinematics for normal {source}")
    return best


def solve_rotation(
    normal: np.ndarray,
    machine: MachineConfig,
    seed_rotation_deg: np.ndarray | None = None,
) -> np.ndarray:
    seed_rad: np.ndarray | None = None
    if seed_rotation_deg is not None:
        seed_deg = np.asarray(seed_rotation_deg, dtype=float)
        if seed_deg.shape != (2,):
            raise ValueError("seed_rotation_deg must be a 2-element angle pair in degrees.")
        if np.all(np.isfinite(seed_deg)):
            seed_rad = np.deg2rad(seed_deg)
    return np.rad2deg(_solve_single_pose(normal, machine, seed_rad))


def solve_path_rotations(
    normals: np.ndarray,
    machine: MachineConfig,
    seed_rotations_deg: np.ndarray | None = None,
) -> np.ndarray:
    normals = np.asarray(normals, dtype=float)
    if normals.ndim != 2 or normals.shape[1] != 3:
        raise ValueError("normals must have shape (n, 3).")

    if len(normals) == 0:
        return np.zeros((0, 2), dtype=float)

    if seed_rotations_deg is not None:
        seed_rotations_deg = np.asarray(seed_rotations_deg, dtype=float)
        if seed_rotations_deg.shape != (len(normals), 2):
            raise ValueError("seed_rotations_deg must have shape (n, 2).")

    rotations_rad = np.zeros((len(normals), 2), dtype=float)
    seed_rad: np.ndarray | None = None
    for index, normal in enumerate(normals):
        current_seed = seed_rad
        if seed_rotations_deg is not None:
            candidate_seed_deg = seed_rotations_deg[index]
            if np.all(np.isfinite(candidate_seed_deg)):
                current_seed = np.deg2rad(candidate_seed_deg)
        rotations_rad[index] = _solve_single_pose(normal, machine, current_seed)
        seed_rad = rotations_rad[index]

    return np.column_stack(
        [unwrap_degrees(np.rad2deg(rotations_rad[:, 0])), unwrap_degrees(np.rad2deg(rotations_rad[:, 1]))]
    )


def solve_path_poses(
    path: PathSpec,
    machine: MachineConfig,
    seed_rotations_deg: np.ndarray | None = None,
) -> list[Pose]:
    rotations_deg = solve_path_rotations(path.normals, machine, seed_rotations_deg=seed_rotations_deg)

    tool_axis = np.asarray(machine.tool_axis, dtype=float)
    tool_axis = normalize(tool_axis)
    origin = np.asarray(machine.origin_mm, dtype=float)

    poses: list[Pose] = []
    for point, normal, angles_deg in zip(path.points_mm, path.normals, rotations_deg, strict=True):
        rotation = rotation_from_axis_pair(machine.rotation_order, np.deg2rad(angles_deg))
        machine_point = rotation.apply(point) + origin + tool_axis * machine.tool_offset_mm
        poses.append(
            Pose(
                model_point_mm=np.asarray(point, dtype=float),
                machine_point_mm=np.asarray(machine_point, dtype=float),
                normal=np.asarray(normal, dtype=float),
                rotation_deg=np.asarray(angles_deg, dtype=float),
            )
        )
    return poses
