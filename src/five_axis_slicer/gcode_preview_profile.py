"""Recognize explicit supported controller declarations in imported NC."""

import json
import math
from pathlib import Path
from typing import Any

def _bundled_controller_setup(source_path: Path) -> tuple[str | None, float]:
    """Recognize only the bundled NC profile's explicit machine declaration."""

    from .manufacturing.own_printer import OWN_AC_ID
    from .manufacturing.preview_kinematics import OWN_AC_PREVIEW_SEMANTICS

    profile_id, machine_id, axis_map, tool_length = _read_header(source_path)
    if profile_id is None and machine_id == OWN_AC_ID:
        if axis_map != {axis: axis for axis in "XYZAC"}:
            return None, 0.0
        profile_id = machine_id
    if profile_id != OWN_AC_ID or machine_id not in {None, profile_id}:
        return None, 0.0
    if tool_length is None and source_path.name == "main.gcode":
        tool_length = _manifest_tool_length(source_path, OWN_AC_ID)
    if tool_length is None:
        return None, 0.0
    return OWN_AC_PREVIEW_SEMANTICS, tool_length

def _read_header(source_path: Path):
    prefix = b"; CONTROLLER_PROFILE "
    machine_prefix = b"; MACHINE_PROFILE "
    axis_prefix = b"; CONTROLLER_AXIS_MAP "
    tool_prefix = b"; TOOL_LENGTH_MM "
    profile_id: str | None = None
    machine_id: str | None = None
    axis_map: Any = None
    tool_length: float | None = None
    with source_path.open("rb") as stream:
        for line in stream.read(32768).splitlines():
            if line.startswith(prefix):
                try:
                    profile = json.loads(line[len(prefix) :])
                except (ValueError, UnicodeDecodeError):
                    return None, None, None, None
                if isinstance(profile, dict):
                    profile_id = profile.get("machine_profile_id")
            elif line.startswith(machine_prefix):
                try:
                    profile = json.loads(line[len(machine_prefix) :])
                except (ValueError, UnicodeDecodeError):
                    return None, None, None, None
                if isinstance(profile, dict):
                    machine_id = profile.get("id")
            elif line.startswith(axis_prefix):
                try:
                    axis_map = json.loads(line[len(axis_prefix) :])
                except (ValueError, UnicodeDecodeError):
                    return None, None, None, None
            elif line.startswith(tool_prefix):
                try:
                    value = float(line[len(tool_prefix) :])
                except ValueError:
                    continue
                if math.isfinite(value) and value >= 0.0:
                    tool_length = value
    return profile_id, machine_id, axis_map, tool_length


def _manifest_tool_length(source_path: Path, profile_id: str) -> float | None:
    tool_length = None
    # Older bundled exports keep this value in their adjacent manifest.
    try:
        manifest = json.loads(
            (source_path.parent / "manifest.json").read_text(encoding="utf-8")
        )
        trajectory = manifest.get("machine_trajectory_summary")
        if trajectory is None:
            trajectory = manifest["machine_trajectory"]
        sample_count = trajectory.get("sample_count")
        if sample_count is None:
            sample_count = len(trajectory["samples"])
        readback = manifest["readback"]
        if (
            manifest["manifest"]["machine_profile_id"] == profile_id
            and trajectory["machine_profile_id"] == profile_id
            and readback["passed"] is True
            and readback["expected_points"]
            == readback["read_points"]
            == sample_count
        ):
            value = float(trajectory["tool_length_mm"])
            if math.isfinite(value) and value >= 0.0:
                tool_length = value
    except (OSError, KeyError, TypeError, ValueError):
        pass
    return tool_length


