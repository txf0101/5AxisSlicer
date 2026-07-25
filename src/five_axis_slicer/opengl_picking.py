"""Coordinate-preserving CPU picking math shared by OpenGL hit paths."""

from __future__ import annotations

import numpy as np


def screen_segment_distance_and_fraction(
    point: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
) -> tuple[float, float]:
    segment = end - start
    length_sq = float(np.dot(segment, segment))
    if length_sq <= 1e-12:
        return float(np.linalg.norm(point - start)), 0.0
    fraction = max(0.0, min(1.0, float(np.dot(point - start, segment) / length_sq)))
    projection = start + fraction * segment
    return float(np.linalg.norm(point - projection)), fraction


def unproject_screen_ray(
    x: float,
    y: float,
    width: int,
    height: int,
    mvp: np.ndarray,
) -> tuple[np.ndarray, np.ndarray] | None:
    if width <= 0 or height <= 0:
        return None
    try:
        inverse = np.linalg.inv(np.asarray(mvp, dtype=np.float64))
    except np.linalg.LinAlgError:
        return None
    ndc_x = 2.0 * float(x) / float(width) - 1.0
    ndc_y = 1.0 - 2.0 * float(y) / float(height)
    near = inverse @ np.array((ndc_x, ndc_y, -1.0, 1.0), dtype=np.float64)
    far = inverse @ np.array((ndc_x, ndc_y, 1.0, 1.0), dtype=np.float64)
    if abs(float(near[3])) <= 1e-12 or abs(float(far[3])) <= 1e-12:
        return None
    origin = near[:3] / near[3]
    far_point = far[:3] / far[3]
    direction = far_point - origin
    length = float(np.linalg.norm(direction))
    if length <= 1e-12 or not np.isfinite(direction).all():
        return None
    return origin, direction / length


def ray_triangle_intersection(
    origin: np.ndarray,
    direction: np.ndarray,
    triangle: np.ndarray,
) -> float | None:
    first, second, third = np.asarray(triangle, dtype=np.float64)
    edge_one = second - first
    edge_two = third - first
    cross = np.cross(direction, edge_two)
    determinant = float(np.dot(edge_one, cross))
    if abs(determinant) <= 1e-10:
        return None
    inverse = 1.0 / determinant
    offset = origin - first
    u = inverse * float(np.dot(offset, cross))
    if u < -1e-9 or u > 1.0 + 1e-9:
        return None
    second_cross = np.cross(offset, edge_one)
    v = inverse * float(np.dot(direction, second_cross))
    if v < -1e-9 or u + v > 1.0 + 1e-9:
        return None
    distance = inverse * float(np.dot(edge_two, second_cross))
    return distance if distance >= 0.0 else None


def distance_to_screen_segment(
    point: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
) -> float:
    return screen_segment_distance_and_fraction(point, start, end)[0]


def encode_pick_color(identifier: int) -> tuple[float, float, float, float]:
    identifier = max(0, min(int(identifier), 0xFFFFFF))
    return (
        (identifier & 0xFF) / 255.0,
        ((identifier >> 8) & 0xFF) / 255.0,
        ((identifier >> 16) & 0xFF) / 255.0,
        1.0,
    )


_screen_segment_distance_and_fraction = screen_segment_distance_and_fraction
_unproject_screen_ray = unproject_screen_ray
_ray_triangle_intersection = ray_triangle_intersection
_distance_to_screen_segment = distance_to_screen_segment
_encode_pick_color = encode_pick_color
