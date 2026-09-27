"""Area of a clipped rectangular geometric bead section, not a deposition model.

Uses successive convex half-plane clipping (Sutherland and Hodgman, 1974,
doi:10.1145/360767.360802), independently implemented in local section coordinates.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import math

from ...models import Vector3
from .wedge_boundary import PlaneHalfSpace

_Point2 = tuple[float, float]


def _vector(value: Sequence[float], label: str) -> Vector3:
    if len(value) != 3:
        raise ValueError(f"{label} must have three coordinates")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must be finite")
    return result  # type: ignore[return-value]


def _unit(value: Vector3, label: str) -> Vector3:
    result = _vector(value, label)
    length = math.hypot(*result)
    if length == 0.0 or not math.isfinite(length):
        raise ValueError(f"{label} must have finite nonzero length")
    return tuple(item / length for item in result)  # type: ignore[return-value]


def _dot(a: Vector3, b: Vector3) -> float:
    return math.fsum(x * y for x, y in zip(a, b, strict=True))


def _clip(polygon: list[_Point2], a: float, b: float, c: float) -> list[_Point2]:
    if not polygon:
        return []
    result: list[_Point2] = []
    previous = polygon[-1]
    previous_distance = a * previous[0] + b * previous[1] + c
    for current in polygon:
        distance = a * current[0] + b * current[1] + c
        if not math.isfinite(distance) or not math.isfinite(previous_distance):
            raise ValueError("section clipping distance overflow")
        if (distance >= 0.0) != (previous_distance >= 0.0):
            # Opposite signs: scaled magnitudes avoid overflow in d0 - d1.
            scale = max(abs(previous_distance), abs(distance))
            left, right = abs(previous_distance) / scale, abs(distance) / scale
            fraction = left / (left + right)
            result.append(
                (
                    (1.0 - fraction) * previous[0] + fraction * current[0],
                    (1.0 - fraction) * previous[1] + fraction * current[1],
                )
            )
        if distance >= 0.0:
            result.append(current)
        previous, previous_distance = current, distance
    return result


def clipped_bead_area(
    center: Vector3,
    width_axis: Vector3,
    build_axis: Vector3,
    width_mm: float,
    height_mm: float,
    halfspaces: Iterable[PlaneHalfSpace],
) -> float:
    """Return mm² of a centered rectangle intersected with supplied half-spaces.

    Axes are normalized and must be orthogonal within 1e-12 numerical tolerance.
    Zero dimensions yield zero after input validation. This geometric area does
    not establish that a nozzle can physically deposit the clipped polygon.
    """

    origin = _vector(center, "center")
    width = _unit(width_axis, "width_axis")
    build = _unit(build_axis, "build_axis")
    if abs(_dot(width, build)) > 1.0e-12:
        raise ValueError("width_axis and build_axis must be orthogonal")
    width_mm, height_mm = float(width_mm), float(height_mm)
    if any(not math.isfinite(value) or value < 0 for value in (width_mm, height_mm)):
        raise ValueError("section dimensions must be finite and non-negative")
    planes = tuple(halfspaces)
    if any(not isinstance(plane, PlaneHalfSpace) for plane in planes):
        raise TypeError("halfspaces must contain PlaneHalfSpace values")
    if width_mm == 0.0 or height_mm == 0.0:
        return 0.0
    w, h = width_mm / 2.0, height_mm / 2.0
    polygon = [(-w, -h), (w, -h), (w, h), (-w, h)]
    for plane in planes:
        polygon = _clip(
            polygon,
            _dot(width, plane.normal),
            _dot(build, plane.normal),
            plane.signed_distance(origin),
        )
    if len(polygon) < 3:
        return 0.0
    area = (
        abs(
            math.fsum(
                a[0] * b[1] - b[0] * a[1]
                for a, b in zip(polygon, [*polygon[1:], polygon[0]], strict=True)
            )
        )
        / 2.0
    )
    if not math.isfinite(area):
        raise ValueError("section area overflow")
    return area


__all__ = ["clipped_bead_area"]
