"""Independent complete-stream verification of the emitted offline XYZAC dialect.

Only the declared G21/G90/M82/G92 E0 initial state, marked G1 moves/events and
M400/M2 termination are accepted. Unknown commands, extra words and unmarked
motion fail closed; they are never skipped while looking for a POINT comment.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
import math
import re
from typing import Any

from ..kinematics.xyzac import MachineAxisTrajectory
from ..manufacturing.machine import MachineProfile
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from .gcode_contract import (
    event_extrusion_mm,
    event_feedrate_mm_min,
    events_by_sequence,
    filament_area_mm2,
    marker_identifier,
)

_WORD = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))", re.ASCII)
_E_RELATIVE_TOLERANCE = Decimal("1e-10")


@dataclass(frozen=True, slots=True)
class GCodeReadbackReport:
    """Evidence that this postprocessor's entire program matches its input."""

    expected_points: int
    read_points: int
    coordinate_mismatches: tuple[str, ...]
    feedrate_mismatches: tuple[str, ...]
    extrusion_mismatches: tuple[str, ...]
    order_mismatches: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (
            self.coordinate_mismatches
            or self.feedrate_mismatches
            or self.extrusion_mismatches
            or self.order_mismatches
            or self.expected_points != self.read_points
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "passed": self.passed,
            "expected_points": self.expected_points,
            "read_points": self.read_points,
            "coordinate_mismatches": list(self.coordinate_mismatches),
            "feedrate_mismatches": list(self.feedrate_mismatches),
            "extrusion_mismatches": list(self.extrusion_mismatches),
            "order_mismatches": list(self.order_mismatches),
        }


class _SequenceMismatch(ValueError):
    """The restricted program grammar or execution order was violated."""


@dataclass(frozen=True, slots=True)
class _Record:
    line_number: int
    code: str
    fields: tuple[str, ...] = ()
    words: dict[str, Decimal] = field(default_factory=dict)


class _Reader:
    def __init__(self, records: list[_Record], tolerance: float) -> None:
        self.records = records
        self.cursor = 0
        self.tolerance = Decimal(str(tolerance))
        self.coordinates: list[str] = []
        self.feeds: list[str] = []
        self.extrusion: list[str] = []
        self.ordering: list[str] = []
        self.expected_e = Decimal(0)
        self.actual_e = Decimal(0)

    def take(self, code: str, fields: tuple[str, ...] = ()) -> _Record:
        if self.cursor >= len(self.records):
            raise _SequenceMismatch(f"end_of_file:expected {code} {' '.join(fields)}")
        record = self.records[self.cursor]
        self.cursor += 1
        if record.code != code or record.fields != fields:
            raise _SequenceMismatch(f"line {record.line_number}:expected {code} {' '.join(fields)}")
        return record

    def command(self, code: str, expected: dict[str, float]) -> dict[str, Decimal]:
        record = self.take(code)
        if set(record.words) != set(expected):
            raise _SequenceMismatch(f"line {record.line_number}:{code} unexpected/missing words")
        return record.words

    def extrusion_move(self, words: dict[str, Decimal], delta: Decimal, label: str) -> None:
        actual = words["E"]
        actual_delta = actual - self.actual_e
        self.expected_e += delta
        # Material/actuator displacement has its own relative check. A motion
        # coordinate tolerance must not erase legitimate small deposition.
        delta_tolerance = abs(delta) * _E_RELATIVE_TOLERANCE
        total_tolerance = max(abs(self.expected_e), abs(delta)) * _E_RELATIVE_TOLERANCE
        if abs(actual_delta - delta) > delta_tolerance:
            self.extrusion.append(f"{label}:extrusion_delta")
        if abs(actual - self.expected_e) > total_tolerance:
            self.extrusion.append(f"{label}:extrusion_position")
        self.actual_e = actual

    def feedrate(self, words: dict[str, Decimal], value: float, label: str) -> None:
        if abs(words["F"] - Decimal(str(value))) > self.tolerance:
            self.feeds.append(label)

    def report(self, count: int) -> GCodeReadbackReport:
        return GCodeReadbackReport(
            count,
            sum(record.code == "POINT" for record in self.records),
            tuple(self.coordinates),
            tuple(self.feeds),
            tuple(self.extrusion),
            tuple(self.ordering),
        )


def readback_absolute_xyzac(
    gcode: str,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
    *,
    tolerance: float = 1.0e-4,
    marker_tag: str = "T08",
) -> GCodeReadbackReport:
    """Check stream, point identity, machine axes, feeds and every signed E increment."""
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("readback tolerance must be finite and nonnegative")
    filament_area_mm2(nozzle)
    marker_identifier(marker_tag)
    reader = _Reader([], tolerance)
    try:
        reader.records = _parse_records(gcode, marker_tag)
        _read_program(reader, toolpath, trajectory, machine, nozzle)
    except _SequenceMismatch as error:
        reader.ordering.append(str(error))
    return reader.report(len(toolpath.points))


def _parse_records(gcode: str, marker_tag: str) -> list[_Record]:
    result: list[_Record] = []
    prefix = f"{marker_tag} "
    for number, raw in enumerate(gcode.splitlines(), start=1):
        code, _, comment = raw.partition(";")
        if code.strip():
            result.append(_parse_command(code, number))
        elif comment.strip().startswith(prefix):
            fields = comment.strip().split()
            if len(fields) < 2 or fields[1] not in {"POINT", "EVENT"}:
                raise _SequenceMismatch(f"line {number}:invalid marker")
            result.append(_Record(number, fields[1], tuple(fields[2:])))
    return result


def _parse_command(code: str, number: int) -> _Record:
    tokens = code.upper().split()
    words: dict[str, Decimal] = {}
    for token in tokens[1:]:
        match = _WORD.fullmatch(token)
        if match is None or match[1] in words:
            raise _SequenceMismatch(f"line {number}:invalid or duplicate word {token}")
        value = Decimal(match[2])
        if not value.is_finite():
            raise _SequenceMismatch(f"line {number}:nonfinite word {token}")
        words[match[1]] = value
    return _Record(number, tokens[0], words=words)


def _read_program(
    reader: _Reader,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    machine: MachineProfile,
    nozzle: NozzleProfile,
) -> None:
    if len(toolpath.points) != len(trajectory.samples):
        raise _SequenceMismatch("toolpath and trajectory sample counts differ")
    if trajectory.source_toolpath_id != toolpath.toolpath_id:
        raise _SequenceMismatch("trajectory source does not match toolpath")
    if trajectory.machine_profile_id != machine.profile_id:
        raise _SequenceMismatch("trajectory machine profile does not match")
    for command in ("G21", "G90", "M82"):
        reader.command(command, {})
    if reader.command("G92", {"E": 0.0})["E"] != 0:
        raise _SequenceMismatch("initial extrusion must be G92 E0")
    diameter = Decimal(str(nozzle.filament_diameter_mm))
    area = Decimal(str(math.pi)) * diameter * diameter / 4
    events = events_by_sequence(toolpath)
    for index, (point, sample) in enumerate(zip(toolpath.points, trajectory.samples, strict=True)):
        _read_events(reader, toolpath, index, events.get(index, ()))
        if sample.source_point_id != point.point_id:
            raise _SequenceMismatch(f"{point.point_id}:trajectory point identity mismatch")
        reader.take("POINT", (str(index + 1), point.point_id, point.point_type))
        _read_point(reader, point, machine.controller_values(sample.joint_positions), area)
    _read_events(reader, toolpath, len(toolpath.points), events.get(len(toolpath.points), ()))
    reader.command("M400", {})
    reader.command("M2", {})
    if reader.cursor != len(reader.records):
        raise _SequenceMismatch(f"line {reader.records[reader.cursor].line_number}:after M2")


def _read_events(
    reader: _Reader,
    toolpath: GeneratedToolpath,
    sequence: int,
    events: Iterable[ToolpathEvent],
) -> None:
    for event in events:
        reader.take("EVENT", (event.event_id, event.event_type))
        delta = event_extrusion_mm(event)
        if delta is not None:
            feed = event_feedrate_mm_min(toolpath, sequence)
            words = reader.command("G1", {"E": 0.0, "F": feed})
            reader.extrusion_move(words, Decimal(str(delta)), event.event_id)
            reader.feedrate(words, feed, event.event_id)


def _read_point(
    reader: _Reader, point: ToolpathPoint, axes: dict[str, float], area: Decimal
) -> None:
    expected = axes | {"F": point.feedrate_mm_min or 1.0}
    deposition = point.point_type == "deposition"
    if deposition:
        expected["E"] = 0.0
    words = reader.command("G1", expected)
    for axis, value in axes.items():
        if abs(words[axis] - Decimal(str(value))) > reader.tolerance:
            reader.coordinates.append(f"{point.point_id}:{axis}")
    reader.feedrate(words, expected["F"], point.point_id)
    if deposition:
        reader.extrusion_move(words, Decimal(str(point.material_volume_mm3)) / area, point.point_id)
