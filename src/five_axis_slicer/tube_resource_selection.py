"""Explicit resource construction used by Tube UI and automation adapters."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any
from uuid import uuid4

from .manufacturing.nozzle_envelope import normalise_outer_profile
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


class NozzleEditorError(ValueError):
    """Stable editor failure code with a developer-facing message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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
        source=None,
    )
    blockers = profile.readiness_blockers
    if blockers:
        fields = ", ".join(issue.field for issue in blockers)
        raise ValueError("complete nozzle contains invalid physical fields: " + fields)
    return profile


def nozzle_editor_profile(
    template: NozzleProfile,
    *,
    interface: str,
    length_mm: float,
    use_collision_envelope: bool,
) -> NozzleProfile:
    """Return the selected profile or a user copy containing explicit editor changes."""

    length = float(length_mm)
    if not math.isfinite(length) or length < 0.0:
        raise ValueError("length_mm must be a finite non-negative number")
    requested_interface = interface.strip()
    requested_shape = use_collision_envelope
    current_length = template.length_mm or 0.0
    unchanged = (
        requested_interface == (template.interface or "")
        and math.isclose(length, current_length, rel_tol=1.0e-9, abs_tol=1.0e-6)
        and requested_shape == bool(template.outer_profile_rz_mm)
    )
    if unchanged:
        return template

    envelope = _editor_envelope(template, length, current_length, requested_shape)
    return replace(
        template.editable_copy(
            str(uuid4()),
            display_name=f"{template.display_name} · project profile",
        ),
        interface=requested_interface or None,
        length_mm=length or None,
        outer_profile_rz_mm=envelope,
        source=None,
    )


def _editor_envelope(
    template: NozzleProfile,
    length: float,
    current_length: float,
    requested: bool,
) -> tuple[tuple[float, float], ...]:
    envelope = template.outer_profile_rz_mm if requested else ()
    if requested and not envelope:
        if length <= 0.0:
            raise NozzleEditorError(
                "nozzle_collision_length_required",
                "length_mm is required for a collision envelope",
            )
        radius = max(2.0, template.orifice_diameter_mm * 3.0)
        return ((radius * 0.45, 0.0), (radius, length))
    if requested and not math.isclose(length, current_length, rel_tol=1.0e-9, abs_tol=1.0e-6):
        raise NozzleEditorError(
            "nozzle_collision_length_changed",
            "length_mm cannot change while retaining the existing collision envelope",
        )
    return envelope


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
    try:
        points = normalise_outer_profile(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("outer_profile_rz_mm must contain radius/z pairs") from exc
    if len(points) < 2 or any(
        not math.isfinite(radius) or not math.isfinite(z) or radius < 0.0 for radius, z in points
    ):
        raise ValueError("outer_profile_rz_mm must contain at least two valid points")
    return points


__all__ = ["NozzleEditorError", "configured_nozzle_copy", "nozzle_editor_profile"]
