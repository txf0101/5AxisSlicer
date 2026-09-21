"""Handwritten wrapper truth and deliberate corruptions, without a printer."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.postprocessing.thermal_program import (
    ThermalProgramParameters,
    unwrap_checked_thermal_program,
    wrap_thermal_program,
)

PARAMETERS = ThermalProgramParameters(195, 45)
MOTION = "G21\nG90\nM82\nG92 E0\nG1 X1 F60\nM400\nM2\n"
HANDWRITTEN = (
    "M140 S45\nM104 S195\nM190 S45\nM109 S195\n"
    + MOTION[:-3]
    + "M400\nM104 S0\nM140 S0\nM107\nM2\n"
)


def test_handwritten_and_emitted_wrapper_preserve_complete_motion():
    assert unwrap_checked_thermal_program(HANDWRITTEN, PARAMETERS) == MOTION
    assert (
        unwrap_checked_thermal_program(wrap_thermal_program(MOTION, PARAMETERS), PARAMETERS)
        == MOTION
    )


@pytest.mark.parametrize(
    "old,new",
    [
        ("M109 S195", "M109 S210"),
        ("M190 S45", "M140 S45"),
        ("M104 S0", "M104 S195"),
        ("M107", "G1 X99"),
        ("M109 S195", "M109 S195 X1"),
        ("M109 S195", "M109 Snan"),
    ],
)
def test_thermal_corruptions_rejected(old, new):
    with pytest.raises(ValueError):
        unwrap_checked_thermal_program(HANDWRITTEN.replace(old, new), PARAMETERS)


def test_extra_motion_is_retained_for_strict_motion_reader():
    code = HANDWRITTEN.replace("G1 X1 F60", "G1 X99 F60\nG1 X1 F60")
    assert "G1 X99 F60" in unwrap_checked_thermal_program(code, PARAMETERS)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0])
def test_invalid_setpoint_rejected(value):
    with pytest.raises(ValueError):
        ThermalProgramParameters(value, 45)
