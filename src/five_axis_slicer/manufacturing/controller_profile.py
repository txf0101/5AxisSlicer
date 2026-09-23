"""Explicit controller dialect and offline execution qualification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Mapping

from .resources import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class ToolChangeStation:
    """Calibrated machine-frame nozzle-tip positions for one material station."""

    clearance_z_mm: float
    cutter_xyz_mm: tuple[float, float, float]
    exchange_xyz_mm: tuple[float, float, float]
    purge_xyz_mm: tuple[float, float, float]
    wipe_start_xyz_mm: tuple[float, float, float]
    wipe_end_xyz_mm: tuple[float, float, float]
    travel_feedrate_mm_min: float = 3000.0
    wipe_feedrate_mm_min: float = 1200.0
    wipe_passes: int = 2
    cutter_command: str = "M98 P100"

    def __post_init__(self) -> None:
        for name in (
            "clearance_z_mm",
            "travel_feedrate_mm_min",
            "wipe_feedrate_mm_min",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, value)
        for name in (
            "cutter_xyz_mm",
            "exchange_xyz_mm",
            "purge_xyz_mm",
            "wipe_start_xyz_mm",
            "wipe_end_xyz_mm",
        ):
            values = tuple(float(value) for value in getattr(self, name))
            if len(values) != 3 or any(not math.isfinite(value) for value in values):
                raise ValueError(f"{name} must contain three finite machine coordinates")
            if values[2] >= self.clearance_z_mm:
                raise ValueError(f"{name} must be below clearance_z_mm")
            object.__setattr__(self, name, values)
        if type(self.wipe_passes) is not int or not 1 <= self.wipe_passes <= 20:
            raise ValueError("wipe_passes must be an integer in [1, 20]")
        command = str(self.cutter_command).strip().upper()
        if not command or "\n" in command or ";" in command:
            raise ValueError("cutter_command must be one G-code command")
        object.__setattr__(self, "cutter_command", command)

    def to_json(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "ToolChangeStation":
        return cls(**{name: payload[name] for name in (
            "clearance_z_mm", "cutter_xyz_mm", "exchange_xyz_mm", "purge_xyz_mm",
            "wipe_start_xyz_mm", "wipe_end_xyz_mm",
        )}, **{name: payload[name] for name in (
            "travel_feedrate_mm_min", "wipe_feedrate_mm_min", "wipe_passes", "cutter_command",
        ) if name in payload})


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
    tool_change_station: ToolChangeStation | None = None

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
        if self.tool_change_station is not None and not isinstance(
            self.tool_change_station, ToolChangeStation
        ):
            raise TypeError("tool_change_station must be a ToolChangeStation or None")

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
            **{
                name: (
                    None if value is None else value.to_json()
                ) if name == "tool_change_station" else value
                for name in self.__dataclass_fields__
                for value in (getattr(self, name),)
            },
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
            tool_change_station=(
                None
                if payload.get("tool_change_station") is None
                else ToolChangeStation.from_json(payload["tool_change_station"])
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


__all__ = ["ControllerProfile", "ToolChangeStation", "OWN_AC_OFFLINE_CONTROLLER"]
