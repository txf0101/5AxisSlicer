from __future__ import annotations

import math

import numpy as np

from .models import MachineConfig, Pose


def effective_move_distance_mm(previous_pose: Pose, next_pose: Pose, machine: MachineConfig) -> float:
    linear = float(np.linalg.norm(next_pose.machine_point_mm - previous_pose.machine_point_mm))
    delta_deg = next_pose.rotation_deg - previous_pose.rotation_deg
    rotational = machine.rotation_radius_mm * float(np.linalg.norm(np.deg2rad(delta_deg)))
    return math.hypot(linear, rotational)


def compensated_feed_mm_min(
    base_feed_mm_s: float,
    deposition_length_mm: float,
    effective_distance_mm: float,
    max_scale: float,
) -> float:
    if deposition_length_mm <= 1e-9:
        return base_feed_mm_s * 60.0
    scale = effective_distance_mm / deposition_length_mm
    scale = min(scale, max_scale)
    return base_feed_mm_s * 60.0 * scale
