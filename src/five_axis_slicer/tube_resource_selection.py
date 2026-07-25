"""Explicit resource construction used by Tube UI and automation adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any
from uuid import uuid4

from .manufacturing.resources import NozzleProfile

_NOZZLE_PHYSICAL_FIELDS = (
    "interface",
    "length_mm",
    "construction_material",
    "flow_category",
    "temperature_limit_c",
    "wear_resistance_rating",
    "outer_profile_rz_mm",
)


def configured_nozzle_copy(
    template: NozzleProfile,
    options: Mapping[str, Any],
) -> NozzleProfile:
    """Build a user profile only from caller-supplied physical data."""

    missing = tuple(field for field in _NOZZLE_PHYSICAL_FIELDS if field not in options)
    if missing:
        raise ValueError("complete nozzle requires explicit fields: " + ", ".join(missing))
    profile = replace(
        template.editable_copy(str(uuid4())),
        interface=_text(options, "interface"),
        length_mm=_positive_float(options, "length_mm"),
        construction_material=_text(options, "construction_material"),
        flow_category=_text(options, "flow_category"),
        temperature_limit_c=_positive_float(options, "temperature_limit_c"),
        wear_resistance_rating=_text(options, "wear_resistance_rating"),
        outer_profile_rz_mm=_outer_profile(options["outer_profile_rz_mm"]),
    )
    blockers = profile.readiness_blockers
    if blockers:
        fields = ", ".join(issue.field for issue in blockers)
        raise ValueError("complete nozzle contains invalid physical fields: " + fields)
    return profile


def _text(options: Mapping[str, Any], field: str) -> str:
    value = options[field]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_float(options: Mapping[str, Any], field: str) -> float:
    value = options[field]
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive number") from exc
    if result <= 0.0:
        raise ValueError(f"{field} must be a positive number")
    return result


def _outer_profile(value: Any) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ValueError("outer_profile_rz_mm must contain radius/z pairs")
    try:
        points = tuple((float(point[0]), float(point[1])) for point in value)
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError("outer_profile_rz_mm must contain radius/z pairs") from exc
    if len(points) < 2 or any(radius < 0.0 for radius, _z in points):
        raise ValueError("outer_profile_rz_mm must contain at least two valid points")
    return points


__all__ = ["configured_nozzle_copy"]
