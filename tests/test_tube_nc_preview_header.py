import json
import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.gcode_preview import _bundled_controller_setup, load_gcode
from five_axis_slicer.manufacturing.preview_kinematics import OWN_AC_PREVIEW_SEMANTICS


def header(mapping=None):
    return (
        '; MACHINE_PROFILE {"id":"builtin.machine.own_ac_fdm.v1"}\n'
        + "; CONTROLLER_AXIS_MAP "
        + json.dumps(mapping or {a: a for a in "XYZAC"})
        + "\n"
    )


def test_standalone_tube_header_restores_workpiece_position(tmp_path):
    path = tmp_path / "tube.gcode"
    path.write_text(header() + "; TOOL_LENGTH_MM 18\nG21\nG90\nM82\nG1 X0 Y0 Z28 A0 C0 E1 F100\n")
    preview = load_gcode(path)
    assert preview.controller_semantics == OWN_AC_PREVIEW_SEMANTICS
    assert preview.tool_length_mm == 18
    assert preview.segments[-1].end == pytest.approx((0, 0, 10))


def test_unknown_axis_mapping_does_not_guess(tmp_path):
    path = tmp_path / "tube.gcode"
    path.write_text(header({"A": "B"}) + "; TOOL_LENGTH_MM 18\n")
    assert _bundled_controller_setup(path) == (None, 0)


def test_legacy_tube_manifest_supplies_tool_length(tmp_path):
    path = tmp_path / "main.gcode"
    path.write_text(header())
    machine = "builtin.machine.own_ac_fdm.v1"
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "manifest": {"machine_profile_id": machine},
                "machine_trajectory": {
                    "machine_profile_id": machine,
                    "tool_length_mm": 18,
                    "samples": [{}],
                },
                "readback": {"passed": True, "expected_points": 1, "read_points": 1},
            }
        )
    )
    assert _bundled_controller_setup(path) == (OWN_AC_PREVIEW_SEMANTICS, 18)


def test_missing_tool_length_does_not_guess(tmp_path):
    path = tmp_path / "tube.gcode"
    path.write_text(header())
    assert _bundled_controller_setup(path) == (None, 0)


def test_actual_tube_postprocessor_roundtrip_without_adjacent_manifest(tmp_path):
    from five_axis_slicer.kinematics.xyzac import MachineAxisSample, MachineAxisTrajectory
    from five_axis_slicer.manufacturing.own_printer import own_ac_profile
    from five_axis_slicer.manufacturing.resources import NozzleProfile
    from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
    from five_axis_slicer.postprocessing.indexed_tube import postprocess_indexed_gcode

    machine = own_ac_profile()
    point = ToolpathPoint("p1", (2, 3, 4), (1, 0, 0), (0, -1, 0), "op", "s", "l", "r", "approach")
    toolpath = GeneratedToolpath("path", "op", points=(point,))
    # Analytic Rx(90 degrees) maps (2,3,4) to (2,-4,3); add 18 mm tool length.
    trajectory = MachineAxisTrajectory(
        "axes",
        machine.profile_id,
        "path",
        (MachineAxisSample("p1", 0, {"X": 2, "Y": -4, "Z": 21, "A": math.pi / 2, "C": 0}),),
        tool_length_mm=18,
    )
    nozzle = NozzleProfile(
        resource_id="test",
        display_name="Test",
        orifice_diameter_mm=0.4,
        filament_diameter_mm=1.75,
        interface="M6",
        length_mm=18,
        outer_profile_rz_mm=((0.2, 0), (1, 18)),
    )
    path = tmp_path / "standalone.gcode"
    path.write_text(postprocess_indexed_gcode(toolpath, trajectory, machine, nozzle))
    preview = load_gcode(path)
    assert preview.controller_semantics == OWN_AC_PREVIEW_SEMANTICS
    assert preview.segments[-1].end == pytest.approx(point.position, abs=1e-9)
