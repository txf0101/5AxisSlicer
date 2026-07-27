"""Axisymmetric nozzle-envelope parsing and physical consistency rules."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

OuterProfile = tuple[tuple[float, float], ...]


def normalise_outer_profile(value: Any) -> OuterProfile:
    """Freeze strict ``(radius, z)`` pairs as floats."""

    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise TypeError("outer_profile_rz_mm must contain (radius, z) pairs")
    try:
        if any(
            not isinstance(point, Sequence)
            or isinstance(point, str | bytes | bytearray)
            or len(point) != 2
            for point in value
        ):
            raise TypeError
        return tuple((float(point[0]), float(point[1])) for point in value)
    except (TypeError, ValueError, IndexError) as exc:
        raise TypeError("outer_profile_rz_mm must contain (radius, z) pairs") from exc


def is_consistent_outer_profile(
    points: OuterProfile,
    length_mm: float | None,
    orifice_diameter_mm: float,
) -> bool:
    """Check the tip datum, finite envelope, axial span, and declared length."""

    if not _valid_points(points, orifice_diameter_mm):
        return False
    z_values = tuple(z for _radius, z in points)
    if not math.isclose(z_values[0], 0.0, abs_tol=1.0e-6):
        return False
    if points[0][0] < orifice_diameter_mm * 0.5 - 1.0e-6:
        return False
    if any(
        current < previous - 1.0e-6
        for previous, current in zip(z_values, z_values[1:], strict=False)
    ):
        return False
    if max(z_values) - min(z_values) <= 1.0e-6:
        return False
    if not _positive(length_mm):
        return True
    assert isinstance(length_mm, int | float) and not isinstance(length_mm, bool)
    return math.isclose(
        max(z_values),
        float(length_mm),
        rel_tol=1.0e-9,
        abs_tol=1.0e-6,
    )


def _valid_points(points: OuterProfile, orifice_diameter_mm: float) -> bool:
    if not _positive(orifice_diameter_mm) or len(points) < 2:
        return False
    return not any(
        not math.isfinite(radius) or not math.isfinite(z) or radius < 0.0 or z < 0.0
        for radius, z in points
    )


def _positive(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int | float)
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


__all__ = ["OuterProfile", "is_consistent_outer_profile", "normalise_outer_profile"]
