from __future__ import annotations

import numpy as np


AXIS_MAP = {
    "x": np.array([1.0, 0.0, 0.0]),
    "y": np.array([0.0, 1.0, 0.0]),
    "z": np.array([0.0, 0.0, 1.0]),
    "-x": np.array([-1.0, 0.0, 0.0]),
    "-y": np.array([0.0, -1.0, 0.0]),
    "-z": np.array([0.0, 0.0, -1.0]),
}


def as_array_2d(values: list[list[float]] | np.ndarray, expected_width: int) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 2 or array.shape[1] != expected_width:
        raise ValueError(f"Expected an N x {expected_width} array, got shape {array.shape!r}")
    return array


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm <= 1e-12:
        raise ValueError("Cannot normalize a zero-length vector")
    return vector / norm


def normalize_rows(values: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if np.any(norms <= 1e-12):
        raise ValueError("Cannot normalize a row with zero length")
    return values / norms


def segment_lengths(points: np.ndarray, closed: bool = False) -> np.ndarray:
    if len(points) < 2:
        return np.zeros(0, dtype=float)
    rolled = np.roll(points, -1, axis=0)
    deltas = rolled - points if closed else np.diff(points, axis=0)
    return np.linalg.norm(deltas, axis=1)


def estimate_radial_normals(points: np.ndarray, center: np.ndarray | None = None) -> np.ndarray:
    if center is None:
        center = points.mean(axis=0)
    vectors = points - center
    return normalize_rows(vectors)


def unwrap_degrees(values: np.ndarray) -> np.ndarray:
    return np.rad2deg(np.unwrap(np.deg2rad(values)))

