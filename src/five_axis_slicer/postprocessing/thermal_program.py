"""Explicit offline thermal wrapper; geometry and motion readback remain separate.

This template assumes an already homed and calibrated machine. It deliberately
does not invent machine-specific homing, probing, parking or tool-change macros.
"""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class ThermalProgramParameters:
    nozzle_c: float
    bed_c: float

    def __post_init__(self) -> None:
        for value in (self.nozzle_c, self.bed_c):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("positive finite thermal setpoints required")


def wrap_thermal_program(motion_gcode: str, parameters: ThermalProgramParameters) -> str:
    """Add waits before motion and heater shutdown after the queued moves finish."""
    lines = motion_gcode.splitlines()
    if not lines or lines[-1].partition(";")[0].strip() != "M2":
        raise ValueError("motion program must terminate with M2")
    prefix = [
        "; OFFLINE PRINT JOB: homing/calibration and collision qualification pending",
        f"M140 S{parameters.bed_c:.6f}",
        f"M104 S{parameters.nozzle_c:.6f}",
        f"M190 S{parameters.bed_c:.6f}",
        f"M109 S{parameters.nozzle_c:.6f}",
    ]
    suffix = ["M400", "M104 S0", "M140 S0", "M107", "M2"]
    return "\n".join([*prefix, *lines[:-1], *suffix]) + "\n"


def unwrap_checked_thermal_program(gcode: str, parameters: ThermalProgramParameters) -> str:
    """Check all wrapper commands and return motion for the strict motion reader.

    Returning successfully alone does not qualify the NC: callers must validate
    the returned program with its corresponding complete-stream motion reader.
    """
    lines = gcode.splitlines()
    active = [(i, line.partition(";")[0].strip()) for i, line in enumerate(lines)]
    active = [(i, code) for i, code in active if code]
    if len(active) < 9:
        raise ValueError("incomplete thermal program")
    expected = (
        ("M140", parameters.bed_c),
        ("M104", parameters.nozzle_c),
        ("M190", parameters.bed_c),
        ("M109", parameters.nozzle_c),
    )
    for (_, code), (command, value) in zip(active[:4], expected, strict=True):
        words = code.split()
        if len(words) != 2 or words[0] != command or not words[1].startswith("S"):
            raise ValueError("thermal startup order/words mismatch")
        if not math.isclose(float(words[1][1:]), value, rel_tol=0, abs_tol=5e-7):
            raise ValueError("thermal setpoint mismatch")
    if [code for _, code in active[-5:]] != ["M400", "M104 S0", "M140 S0", "M107", "M2"]:
        raise ValueError("thermal shutdown mismatch")
    return "\n".join(lines[active[3][0] + 1 : active[-5][0]] + ["M2"]) + "\n"
