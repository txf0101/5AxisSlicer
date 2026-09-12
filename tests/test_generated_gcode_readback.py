"""Independent hand-authored NC truth and deliberate corruptions of the output."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import math
from pathlib import Path
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.kinematics.xyzac import MachineAxisSample, MachineAxisTrajectory
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE
from five_axis_slicer.manufacturing.resources import NozzleProfile
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from five_axis_slicer.postprocessing.indexed_tube import (
    postprocess_indexed_gcode,
    readback_indexed_gcode,
)


@pytest.fixture
def program():
    # Diameter 2 gives area pi: the two declared volumes demand exactly
    # 3 mm and 0.25 mm of filament, independent of postprocessor code.
    nozzle = NozzleProfile("truth", "truth", 0.4, 2.0, "M6", length_mm=2.0)
    kinds = ("approach", "deposition", "travel", "deposition", "depart")
    volumes = (0.0, 3.0 * math.pi, 0.0, 0.25 * math.pi, 0.0)
    points = tuple(
        ToolpathPoint(
            f"p{index}",
            (float(index), 2.0, 3.0),
            (1.0, 0.0, 0.0),
            (0.0, 0.0, -1.0),
            "op",
            "stage",
            "layer",
            "region",
            kind,
            extrusion_role="infill" if kind == "deposition" else "none",
            feedrate_mm_min=60.0,
            material_volume_mm3=volume,
        )
        for index, (kind, volume) in enumerate(zip(kinds, volumes, strict=True), start=1)
    )
    events = tuple(
        ToolpathEvent(
            name,
            kind,
            "op",
            "stage",
            context={"sequence_index": sequence, "extrusion_length_mm": delta},
        )
        for name, kind, sequence, delta in (
            ("prime1", "prime", 1, 0.75),
            ("retract1", "retract", 2, -0.75),
            ("prime2", "prime", 3, 0.75),
            ("retract2", "retract", 5, -0.75),
        )
    ) + (ToolpathEvent("done", "finish", "op", "stage"),)
    path = GeneratedToolpath("truth-path", "op", points=points, events=events)
    samples = tuple(
        MachineAxisSample(
            point.point_id,
            float(index),
            {"X": point.position[0], "Y": 2.0, "Z": 3.0, "A": 0.0, "C": 0.0},
        )
        for index, point in enumerate(points)
    )
    trajectory = MachineAxisTrajectory(
        "truth-axis", GENERIC_XYZAC_REFERENCE.profile_id, path.toolpath_id, samples
    )
    return path, trajectory, nozzle


HANDWRITTEN = """; Independent known-area fixture
G21
G90
M82
G92 E0
; T08 POINT 1 p1 approach
G1 X1 Y2 Z3 A0 C0 F60
; T08 EVENT prime1 prime
G1 E0.75 F60
; T08 POINT 2 p2 deposition
G1 X2 Y2 Z3 A0 C0 E3.75 F60
; T08 EVENT retract1 retract
G1 E3 F60
; T08 POINT 3 p3 travel
G1 X3 Y2 Z3 A0 C0 F60
; T08 EVENT prime2 prime
G1 E3.75 F60
; T08 POINT 4 p4 deposition
G1 X4 Y2 Z3 A0 C0 E4 F60
; T08 POINT 5 p5 depart
G1 X5 Y2 Z3 A0 C0 F60
; T08 EVENT retract2 retract
G1 E3.25 F60
; T08 EVENT done finish
M400
M2
"""


def _check(gcode, program, **kwargs):
    path, trajectory, nozzle = program
    return readback_indexed_gcode(
        gcode, path, trajectory, GENERIC_XYZAC_REFERENCE, nozzle, **kwargs
    )


def test_handwritten_material_and_terminal_event_truth(program):
    report = _check(HANDWRITTEN, program)
    assert report.passed, report.to_json()
    assert report.expected_points == report.read_points == 5


def test_writer_preserves_events_including_after_last_point_and_sets_initial_e(program):
    path, trajectory, nozzle = program
    gcode = postprocess_indexed_gcode(path, trajectory, GENERIC_XYZAC_REFERENCE, nozzle)
    assert gcode.index("G92 E0") < gcode.index("POINT 1")
    assert gcode.index("POINT 5") < gcode.index("EVENT retract2") < gcode.index("EVENT done")
    assert gcode.index("EVENT done") < gcode.index("M400") < gcode.index("M2")
    assert _check(gcode, program).passed
    # Check emitted E against known actuator truth without calling readback.
    actual = [Decimal(match[1]) for match in re.finditer(r"\bE([-+\d.]+)", gcode)]
    expected = list(map(Decimal, ("0", ".75", "3.75", "3", "3.75", "4", "3.25")))
    assert all(abs(a - b) < Decimal("1e-12") for a, b in zip(actual, expected, strict=True))


def _double_e(gcode):
    return re.sub(r"\bE([-+\d.]+)", lambda match: f"E{Decimal(match[1]) * 2}", gcode)


def _remove_extrusion_events(gcode):
    return re.sub(r"; T08 EVENT \S+ (?:retract|prime)\nG1 E[^\n]+\n", "", gcode)


@pytest.mark.parametrize(
    "mutate",
    [
        _double_e,
        lambda code: code.replace("G90", "G91"),
        lambda code: code.replace("M82", "M83"),
        _remove_extrusion_events,
        lambda code: code.replace("M400", "G1 X999 Y999 Z999 E999\nM400"),
    ],
    ids=["extrusion_x2", "relative_axes", "relative_extrusion", "events_removed", "unmarked_move"],
)
def test_all_five_audit_mutations_are_rejected(program, mutate):
    assert not _check(mutate(HANDWRITTEN), program).passed


@pytest.mark.parametrize(
    "before,after",
    [
        ("G21\n", ""),
        ("G21", "G20"),
        ("G90\n", ""),
        ("M82\n", ""),
        ("G92 E0\n", ""),
        ("G92 E0", "G92 E5"),
        ("G1 X3", "G91\nG90\nG1 X3"),
        ("G1 X3", "G92 E0\nG1 X3"),
        ("E3.75 F60\n; T08 EVENT retract1", "E4.75 F60\n; T08 EVENT retract1"),
        ("G1 E3 F60", "G1 E3.1 F60"),
        ("G1 E0.75 F60", "G1 E0.75 F61"),
        ("G1 X4 Y2", "G1 X4 Y5"),
        ("G1 X4 Y2", "G1 X4 X4 Y2"),
        ("G1 X3 Y2", "G1 X3 E3 Y2"),
        ("G1 X3 Y2", "G1 X3 U0 Y2"),
        ("G1 X3 Y2", "G1 Xnan Y2"),
        ("G1 X3 Y2", "G1 Xinf Y2"),
        ("G1 X3 Y2", "G1 X3 Y2 BAD"),
        ("G1 X3 Y2", "G0 X3 Y2"),
        ("; T08 POINT 4 p4", "; T08 POINT 3 p4"),
        ("; T08 POINT 4 p4", "; T08 POINT 4 p2"),
        ("; T08 EVENT prime2 prime", "; T08 EVENT prime1 prime"),
        ("; T08 EVENT done finish\n", ""),
        ("M400\n", ""),
        ("M2\n", ""),
        ("M400\nM2", "M2\nM400"),
        ("M2\n", "M2\nG1 X999 F60\n"),
    ],
)
def test_complete_instruction_stream_and_each_event_are_checked(program, before, after):
    changed = HANDWRITTEN.replace(before, after)
    assert changed != HANDWRITTEN
    assert not _check(changed, program).passed


def test_finish_moved_before_motion_is_rejected(program):
    changed = HANDWRITTEN.replace("; T08 EVENT done finish\n", "")
    changed = changed.replace("; T08 POINT 1", "; T08 EVENT done finish\n; T08 POINT 1")
    assert not _check(changed, program).passed


@pytest.mark.parametrize("filament_mm", [1.0e-6, 1.0e-12, 1.0e-16, 0.0])
def test_small_and_zero_volume_deposition_are_not_confused_with_missing_extrusion(
    program, filament_mm
):
    path, trajectory, nozzle = program
    points = (path.points[0], replace(path.points[1], material_volume_mm3=filament_mm * math.pi))
    path = replace(path, points=points, events=())
    trajectory = replace(trajectory, samples=trajectory.samples[:2])
    inputs = path, trajectory, nozzle
    gcode = postprocess_indexed_gcode(path, trajectory, GENERIC_XYZAC_REFERENCE, nozzle)
    assert _check(gcode, inputs).passed
    if filament_mm > 0:
        assert not _check(_double_e(gcode), inputs).passed
        deleted = re.sub(r" E[-+\d.]+(?= F)", " E0", gcode)
        assert not _check(deleted, inputs).passed


def test_wrong_filament_diameter_is_detected(program):
    path, trajectory, nozzle = program
    assert not _check(
        HANDWRITTEN, (path, trajectory, replace(nozzle, filament_diameter_mm=1.75))
    ).passed


def test_marker_tag_and_fractional_feed_are_preserved(program):
    path, trajectory, nozzle = program
    path = replace(
        path, points=tuple(replace(point, feedrate_mm_min=60.123456) for point in path.points)
    )
    gcode = postprocess_indexed_gcode(
        path, trajectory, GENERIC_XYZAC_REFERENCE, nozzle, marker_tag="P02"
    )
    assert _check(gcode, (path, trajectory, nozzle), marker_tag="P02").passed


@pytest.mark.parametrize(
    "context",
    [
        {},
        {"sequence_index": -1},
        {"sequence_index": 6},
        {"sequence_index": 1.5},
        {"sequence_index": True},
        {"sequence_index": 1, "extrusion_length_mm": -0.75},
    ],
)
def test_ambiguous_or_wrong_signed_extrusion_events_cannot_be_emitted(program, context):
    path, trajectory, nozzle = program
    path = replace(path, events=(replace(path.events[0], context=context),))
    with pytest.raises(ValueError):
        postprocess_indexed_gcode(path, trajectory, GENERIC_XYZAC_REFERENCE, nozzle)


def test_finish_with_explicit_early_sequence_cannot_be_emitted(program):
    path, trajectory, nozzle = program
    path = replace(path, events=(replace(path.events[-1], context={"sequence_index": 0}),))
    with pytest.raises(ValueError, match="finish must follow"):
        postprocess_indexed_gcode(path, trajectory, GENERIC_XYZAC_REFERENCE, nozzle)
