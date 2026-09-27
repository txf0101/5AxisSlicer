"""Geometric half-space clipping; does not qualify deposited material or support."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
import math

from ...models import Vector3


def _vector(value: Sequence[float], label: str) -> Vector3:
    if len(value) != 3:
        raise ValueError(f"{label} must have three coordinates")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must be finite")
    return result  # type: ignore[return-value]


def _unit(value: Sequence[float], label: str) -> Vector3:
    vector = _vector(value, label)
    length = math.hypot(*vector)
    if length == 0.0 or not math.isfinite(length):
        raise ValueError(f"{label} must have a finite nonzero length")
    return tuple(item / length for item in vector)  # type: ignore[return-value]


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


@dataclass(frozen=True, slots=True)
class PlaneHalfSpace:
    """Keep points satisfying dot(point - origin, normal) >= 0."""

    origin: Vector3
    normal: Vector3

    def __post_init__(self) -> None:
        object.__setattr__(self, "origin", _vector(self.origin, "origin"))
        object.__setattr__(self, "normal", _unit(self.normal, "normal"))

    def signed_distance(self, point: Vector3) -> float:
        delta = tuple(a - b for a, b in zip(point, self.origin, strict=True))
        distance = _dot(delta, self.normal)  # type: ignore[arg-type]
        if not math.isfinite(distance):
            raise ValueError("half-space distance overflow")
        return distance


def _planes(halfspaces: Iterable[PlaneHalfSpace]) -> tuple[PlaneHalfSpace, ...]:
    planes = tuple(halfspaces)
    if any(not isinstance(plane, PlaneHalfSpace) for plane in planes):
        raise TypeError("halfspaces must contain PlaneHalfSpace values")
    return planes


def _interval(
    base: Vector3,
    direction: Vector3,
    lower: float,
    upper: float,
    planes: tuple[PlaneHalfSpace, ...],
) -> tuple[float, float] | None:
    for plane in planes:
        distance = plane.signed_distance(base)
        slope = _dot(direction, plane.normal)
        if not math.isfinite(slope):
            raise ValueError("half-space direction overflow")
        if slope == 0.0:
            if distance < 0.0:
                return None
            continue
        crossing = -distance / slope
        if slope > 0.0:
            lower = max(lower, crossing)
        else:
            upper = min(upper, crossing)
        if lower >= upper:
            return None
    return lower, upper


def column_interval(
    base: Vector3,
    axis: Vector3,
    lower: float,
    upper: float,
    halfspaces: Iterable[PlaneHalfSpace],
) -> tuple[float, float] | None:
    """Intersect base + unit(axis)*z with a finite nominal layer band.

    Returned distances are measured along the normalized axis. A parallel
    half-space either keeps the band or excludes it; a zero-thickness contact
    returns None. No minimum printable thickness is inferred here.
    """

    origin = _vector(base, "base")
    direction = _unit(axis, "axis")
    lower, upper = float(lower), float(upper)
    if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
        raise ValueError("layer band must have finite lower < upper")
    return _interval(origin, direction, lower, upper, _planes(halfspaces))


def _lerp(start: Vector3, end: Vector3, fraction: float) -> Vector3:
    if fraction == 0.0:
        return start
    if fraction == 1.0:
        return end
    result = tuple((1.0 - fraction) * a + fraction * b for a, b in zip(start, end, strict=True))
    return _vector(result, "clipped point")


def clip_polyline(
    points: Iterable[Vector3], halfspaces: Iterable[PlaneHalfSpace]
) -> tuple[tuple[Vector3, ...], ...]:
    """Clip only supplied segments, preserving order and disconnected pieces.

    No closing segment is added. An explicitly repeated first vertex preserves
    that supplied closing segment, but pieces separated by excluded geometry
    are never connected. Isolated contacts and duplicate vertices add no path.
    """

    vertices = tuple(_vector(point, "point") for point in points)
    planes = _planes(halfspaces)
    pieces: list[tuple[Vector3, ...]] = []
    current: list[Vector3] = []
    previous_reached_vertex = False
    for start, end in zip(vertices, vertices[1:]):
        if start == end:
            continue
        direction = _vector(tuple(b - a for a, b in zip(start, end, strict=True)), "segment")
        interval = _interval(start, direction, 0.0, 1.0, planes)
        if interval is None:
            if current:
                pieces.append(tuple(current))
                current = []
            previous_reached_vertex = False
            continue
        lower, upper = interval
        first, last = _lerp(start, end, lower), _lerp(start, end, upper)
        if first == last:
            previous_reached_vertex = False
            continue
        connected = previous_reached_vertex and lower == 0.0 and current and current[-1] == first
        if connected:
            current.append(last)
        else:
            if current:
                pieces.append(tuple(current))
            current = [first, last]
        previous_reached_vertex = upper == 1.0
    if current:
        pieces.append(tuple(current))
    return tuple(pieces)


__all__ = ["PlaneHalfSpace", "clip_polyline", "column_interval"]
