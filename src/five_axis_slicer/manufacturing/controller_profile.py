"""Explicit controller dialect and offline execution qualification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from .resources import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class ControllerProfile:
    profile_id: str
    machine_profile_id: str
    controller_family: str
    controller_version: str | None
    axis_mode: str = "absolute"
    extrusion_mode: str = "relative"
    feed_mode: str = "units_per_minute"
    coordinated_xyzac_verified: bool = False
    macro_version: str | None = None
    reorientation_absolute_z_mm: float = 20.0
    cutter_relative_z_mm: float = 20.0
    maximum_cumulative_c_rad: float | None = None

    def __post_init__(self) -> None:
        for name in ("profile_id", "machine_profile_id", "controller_family"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ValueError(f"{name} must not be empty")
            object.__setattr__(self, name, value)
        if self.axis_mode != "absolute":
            raise ValueError("paper-core AC dialect requires absolute machine axes")
        if self.extrusion_mode not in {"absolute", "relative"}:
            raise ValueError("unsupported extrusion mode")
        if self.feed_mode not in {"units_per_minute", "inverse_time"}:
            raise ValueError("unsupported feed mode")
        if not isinstance(self.coordinated_xyzac_verified, bool):
            raise TypeError("coordinated_xyzac_verified must be bool")
        for name in ("reorientation_absolute_z_mm", "cutter_relative_z_mm"):
            numeric_value = float(getattr(self, name))
            if numeric_value < 0.0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, numeric_value)
        if self.maximum_cumulative_c_rad is not None:
            cumulative_limit = float(self.maximum_cumulative_c_rad)
            if cumulative_limit <= 0.0:
                raise ValueError("maximum_cumulative_c_rad must be positive when specified")
            object.__setattr__(self, "maximum_cumulative_c_rad", cumulative_limit)

    @property
    def machine_executable(self) -> bool:
        return bool(
            self.controller_version
            and self.macro_version
            and self.coordinated_xyzac_verified
            and self.maximum_cumulative_c_rad is not None
        )

    @property
    def qualification_issues(self) -> tuple[str, ...]:
        issues = []
        if not self.controller_version:
            issues.append("controller.version_unknown")
        if not self.macro_version:
            issues.append("controller.macros_unverified")
        if not self.coordinated_xyzac_verified:
            issues.append("controller.xyzac_coordination_unverified")
        if self.maximum_cumulative_c_rad is None:
            issues.append("controller.cumulative_c_limit_unknown")
        return tuple(issues)

    def semantic_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_json())).hexdigest()

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            **{name: getattr(self, name) for name in self.__dataclass_fields__},
            "machine_executable": self.machine_executable,
            "qualification_issues": list(self.qualification_issues),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "ControllerProfile":
        if not isinstance(payload, Mapping) or int(payload.get("schema_version", 0)) != 1:
            raise ValueError("unsupported controller profile schema")
        required = ("profile_id", "machine_profile_id", "controller_family")
        missing = [name for name in required if name not in payload]
        if missing:
            raise ValueError(f"controller profile missing required fields: {', '.join(missing)}")
        return cls(
            profile_id=str(payload["profile_id"]),
            machine_profile_id=str(payload["machine_profile_id"]),
            controller_family=str(payload["controller_family"]),
            controller_version=(
                None
                if payload.get("controller_version") is None
                else str(payload["controller_version"])
            ),
            axis_mode=str(payload.get("axis_mode", "absolute")),
            extrusion_mode=str(payload.get("extrusion_mode", "relative")),
            feed_mode=str(payload.get("feed_mode", "units_per_minute")),
            coordinated_xyzac_verified=payload.get("coordinated_xyzac_verified", False),
            macro_version=(
                None if payload.get("macro_version") is None else str(payload["macro_version"])
            ),
            reorientation_absolute_z_mm=float(payload.get("reorientation_absolute_z_mm", 20.0)),
            cutter_relative_z_mm=float(payload.get("cutter_relative_z_mm", 20.0)),
            maximum_cumulative_c_rad=(
                None
                if payload.get("maximum_cumulative_c_rad") is None
                else float(payload["maximum_cumulative_c_rad"])
            ),
        )


OWN_AC_OFFLINE_CONTROLLER = ControllerProfile(
    "builtin.controller.own_ac.offline.v1",
    "builtin.machine.own_ac_fdm.v1",
    "custom-klipper-derived",
    None,
    extrusion_mode="relative",
    feed_mode="units_per_minute",
    coordinated_xyzac_verified=False,
    macro_version=None,
)


__all__ = ["ControllerProfile", "OWN_AC_OFFLINE_CONTROLLER"]
