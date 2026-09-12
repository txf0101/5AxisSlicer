"""Streaming G-code parser and file-level coordinate policy."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .gcode_preview import (
    AXIS_RE,
    COMMAND_RE,
    COMMENT_ROLE_HINTS,
    DEFAULT_BEAD_WIDTH,
    DEFAULT_LAYER_HEIGHT,
    HEIGHT_RE,
    LAYER_RE,
    ROTARY_AXES,
    TYPE_RE,
    TYPE_ROLE_MAP,
    WIDTH_RE,
    CancelCheck,
    GCodeLoadCancelled,
    GCodePathSegment,
    GCodePreview,
    GCodeTimelineStep,
    ProgressCallback,
)
from .manufacturing.preview_kinematics import (
    DEFAULT_PREVIEW_KINEMATICS_REGISTRY,
    MACHINE_COORDINATE_TRANSFORM,
    NC_PREVIEW_OBJECT_ID,
    reconstruct_preview_motion,
)
from .manufacturing.setup import IssueSeverity, ValidationIssue

LINEAR_AXES = ("X", "Y", "Z")
SPATIAL_AXES = (*LINEAR_AXES, *ROTARY_AXES)


def parse_lines(
    lines: Any,
    source_path: str | Path = "<memory>",
    sample_stride: int = 1,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    controller_semantics: str | None = None,
) -> GCodePreview:
    """Parse a line source and commit one coordinate space for the whole file."""

    source = Path(source_path)
    state = _ParserState()
    segments: list[GCodePathSegment] = []
    timeline: list[GCodeTimelineStep] = []
    stats = _PreviewStats(controller_semantics)
    sample_stride = max(1, int(sample_stride))

    total_lines = len(lines) if hasattr(lines, "__len__") else None
    for line_number, raw_line in enumerate(lines, start=1):
        if line_number == 1 or line_number % 4096 == 0:
            _raise_if_cancelled(cancel_check)
            if progress_callback is not None and total_lines:
                progress_callback(min(1.0, line_number / total_lines), "parse")
        raw = raw_line.strip()
        if not raw:
            continue

        values, comment = _motion_from_line(state, raw)
        if values is None:
            continue
        _append_motion(
            values,
            stats,
            segments,
            timeline,
            line_number,
            raw,
            comment,
            sample_stride,
            controller_semantics,
        )

    # Per-step reconstruction is provisional. One unresolved rotary word makes
    # every step fall back to raw Machine XYZ, so mixed coordinate spaces never
    # escape a single imported file.
    _finalize_file_coordinate_policy(segments, timeline, stats)
    _raise_if_cancelled(cancel_check)
    if progress_callback is not None:
        progress_callback(1.0, "parse")
    return _build_preview(source, segments, timeline, stats)


def normalize_role(raw_role: str) -> str:
    role = re.sub(r"\s+", " ", raw_role.strip()).lower().replace("_", " ")
    return TYPE_ROLE_MAP.get(role, "unknown")


class _ParserState:
    def __init__(self) -> None:
        self.axes = {axis: 0.0 for axis in (*SPATIAL_AXES, "E")}
        self.unregistered_rotary_words_seen: set[str] = set()
        self.feedrate: float | None = None
        self.absolute_xyz = True
        self.relative_e = True
        self.units = 1.0
        self.motion_command: str | None = None
        self.layer = -1
        self.current_role = "unknown"
        self.current_width: float | None = DEFAULT_BEAD_WIDTH
        self.current_height: float | None = DEFAULT_LAYER_HEIGHT


@dataclass(slots=True)
class _MotionValues:
    move_type: str
    extrusion_role: str
    layer: int
    start_xyz: tuple[float, float, float]
    end_xyz: tuple[float, float, float]
    rotary_start: dict[str, float]
    rotary_end: dict[str, float]
    feedrate: float | None
    delta_e: float
    width: float | None
    height: float | None
    count_path_segment: bool


def _split_comment(line: str) -> tuple[str, str]:
    if ";" not in line:
        return line.strip(), ""
    code, comment = line.split(";", 1)
    return code.strip(), comment.strip()


def _motion_from_line(state: _ParserState, raw: str) -> tuple[_MotionValues | None, str]:
    code, comment = _split_comment(raw)
    if comment:
        _apply_comment_tag(state, comment)
    if not code:
        return None, comment

    command, words = _parse_code(code)
    if command is None:
        _apply_modal_command(state, code)
        command = state.motion_command if words else None
    if command is None or _apply_control_command(state, command, words):
        return None, comment

    state.motion_command = command
    return _apply_motion_words(state, command, words), comment


def _apply_control_command(state: _ParserState, command: str, words: dict[str, float]) -> bool:
    if command in {"G90", "G91"}:
        state.absolute_xyz = command == "G90"
    elif command in {"G20", "G21"}:
        state.units = 25.4 if command == "G20" else 1.0
    elif command == "G92":
        _apply_g92_words(state, words)
    elif command == "G28":
        selected = set(words) & set(LINEAR_AXES)
        for axis in selected or LINEAR_AXES:
            state.axes[axis] = 0.0
    else:
        return command not in {"G0", "G1"}
    return True


def _parse_words(code: str) -> dict[str, float]:
    return {axis.upper(): float(value) for axis, value in AXIS_RE.findall(code)}


def _parse_code(code: str) -> tuple[str | None, dict[str, float]]:
    command: str | None = None
    words: dict[str, float] = {}
    for token in code.split():
        if not token:
            continue
        head, value = token[0].upper(), token[1:]
        if head == "G":
            try:
                number = int(float(value))
            except ValueError:
                continue
            if number in {0, 1, 20, 21, 28, 90, 91, 92}:
                command = f"G{number}"
        elif head in "XYZABCUVWEF" and value:
            try:
                words[head] = float(value)
            except ValueError:
                continue
    if command is None and "G" in code.upper():
        match = COMMAND_RE.search(code)
        if match is not None:
            command = f"G{match.group(1)}".upper()
    if not words and any(axis in code.upper() for axis in "XYZABCUVWEF"):
        words = _parse_words(code)
    return command, words


def _apply_modal_command(state: _ParserState, code: str) -> None:
    upper = code.upper()
    if "M82" in upper:
        state.relative_e = False
    elif "M83" in upper:
        state.relative_e = True


def _apply_g92_words(state: _ParserState, words: dict[str, float]) -> None:
    state.unregistered_rotary_words_seen.update(axis for axis in ("U", "V", "W") if axis in words)
    for axis in (*SPATIAL_AXES, "E"):
        if axis in words:
            state.axes[axis] = words[axis] * state.units if axis in LINEAR_AXES else words[axis]


def _apply_comment_tag(state: _ParserState, comment: str) -> None:
    type_match = TYPE_RE.match(comment)
    if type_match is not None:
        state.current_role = normalize_role(type_match.group(1))
        return
    width_match = WIDTH_RE.match(comment)
    if width_match is not None:
        state.current_width = float(width_match.group(1))
        return
    height_match = HEIGHT_RE.match(comment)
    if height_match is not None:
        state.current_height = float(height_match.group(1))
        return
    if comment.upper().startswith("LAYER_CHANGE"):
        state.layer = 0 if state.layer < 0 else state.layer + 1
        return
    layer_match = LAYER_RE.match(comment)
    if layer_match is not None:
        state.layer = int(layer_match.group(1))
        return
    hinted = _role_from_comment_hint(comment)
    if hinted is not None:
        state.current_role = hinted


def _role_from_comment_hint(comment: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z ]+", " ", comment).lower()).strip()
    return next((role for token, role in COMMENT_ROLE_HINTS if token in cleaned), None)


def _apply_motion_words(
    state: _ParserState,
    command: str,
    words: dict[str, float],
) -> _MotionValues | None:
    start_xyz = _current_point(state)
    start_rotary = _current_rotaries(state)
    if "F" in words:
        state.feedrate = words["F"]

    has_spatial_axis = _apply_spatial_words(state, words)
    delta_e = _apply_extrusion_word(state, words)
    end_xyz = _current_point(state)
    end_rotary = _current_rotaries(state)
    linear_motion = _points_differ(start_xyz, end_xyz)
    rotary_motion = any(abs(start_rotary[axis] - end_rotary[axis]) > 1e-9 for axis in start_rotary)
    e_motion = abs(delta_e) > 1e-12
    if not has_spatial_axis and not e_motion:
        return None

    move_type = _classify_move(command, linear_motion or rotary_motion, linear_motion, delta_e)
    if has_spatial_axis and not e_motion and move_type == "noop":
        move_type = "travel"
    return _MotionValues(
        move_type,
        state.current_role,
        max(state.layer, 0),
        start_xyz,
        end_xyz,
        _reported_rotaries(start_rotary, state.unregistered_rotary_words_seen),
        _reported_rotaries(end_rotary, state.unregistered_rotary_words_seen),
        state.feedrate,
        delta_e,
        state.current_width,
        state.current_height,
        has_spatial_axis,
    )


def _current_point(state: _ParserState) -> tuple[float, float, float]:
    return (state.axes["X"], state.axes["Y"], state.axes["Z"])


def _current_rotaries(state: _ParserState) -> dict[str, float]:
    return {axis: state.axes[axis] for axis in ROTARY_AXES}


def _apply_spatial_words(state: _ParserState, words: dict[str, float]) -> bool:
    state.unregistered_rotary_words_seen.update(axis for axis in ("U", "V", "W") if axis in words)
    for axis in SPATIAL_AXES:
        if axis not in words:
            continue
        value = words[axis] * state.units if axis in LINEAR_AXES else words[axis]
        state.axes[axis] = state.axes[axis] + value if not state.absolute_xyz else value
    return any(axis in words for axis in SPATIAL_AXES)


def _apply_extrusion_word(state: _ParserState, words: dict[str, float]) -> float:
    if "E" not in words:
        return 0.0
    if state.relative_e:
        state.axes["E"] += words["E"]
        return words["E"]
    delta_e = words["E"] - state.axes["E"]
    state.axes["E"] = words["E"]
    return delta_e


def _reported_rotaries(values: dict[str, float], present_words: set[str]) -> dict[str, float]:
    return {
        axis: value for axis, value in values.items() if abs(value) > 1e-9 or axis in present_words
    }


def _append_motion(
    values: _MotionValues,
    stats: _PreviewStats,
    segments: list[GCodePathSegment],
    timeline: list[GCodeTimelineStep],
    line_number: int,
    raw: str,
    comment: str,
    sample_stride: int,
    controller_semantics: str | None,
) -> None:
    step_index = stats.timeline_step_count
    reconstruction = reconstruct_preview_motion(
        values.start_xyz,
        values.end_xyz,
        values.rotary_start,
        values.rotary_end,
        controller_semantics=controller_semantics,
    )
    display_start, display_end = reconstruction.start, reconstruction.end
    has_spatial_length = _points_differ(display_start, display_end)
    stats.add_values(
        values,
        display_start,
        display_end,
        has_spatial_length,
        reconstruction.issues,
    )
    path_segment_index = None
    if values.count_path_segment and stats.total_segment_count % sample_stride == 0:
        path_segment_index = len(segments)
        segments.append(
            _make_segment(
                values,
                step_index,
                line_number,
                raw,
                comment,
                display_start,
                display_end,
                reconstruction.coordinate_transform,
            )
        )
    timeline.append(
        _make_timeline_step(
            values,
            step_index,
            line_number,
            raw,
            comment,
            display_start,
            display_end,
            reconstruction.coordinate_transform,
            has_spatial_length,
            path_segment_index,
        )
    )


def _make_segment(
    values: _MotionValues,
    step_index: int,
    line_number: int,
    raw: str,
    comment: str,
    display_start: tuple[float, float, float],
    display_end: tuple[float, float, float],
    coordinate_transform: str,
) -> GCodePathSegment:
    return GCodePathSegment(
        step_index=step_index,
        line_number=line_number,
        layer=values.layer,
        start=display_start,
        end=display_end,
        rotary_start=values.rotary_start,
        rotary_end=values.rotary_end,
        move_type=values.move_type,
        extrusion_role=values.extrusion_role,
        feedrate=values.feedrate,
        delta_e=values.delta_e,
        width=values.width,
        height=values.height,
        comment=comment,
        raw=raw,
        machine_start=values.start_xyz,
        machine_end=values.end_xyz,
        coordinate_transform=coordinate_transform,
    )


def _make_timeline_step(
    values: _MotionValues,
    step_index: int,
    line_number: int,
    raw: str,
    comment: str,
    display_start: tuple[float, float, float],
    display_end: tuple[float, float, float],
    coordinate_transform: str,
    has_spatial_length: bool,
    path_segment_index: int | None,
) -> GCodeTimelineStep:
    return GCodeTimelineStep(
        step_index=step_index,
        line_number=line_number,
        layer=values.layer,
        start=display_start,
        end=display_end,
        rotary_start=values.rotary_start,
        rotary_end=values.rotary_end,
        move_type=values.move_type,
        extrusion_role=values.extrusion_role,
        feedrate=values.feedrate,
        delta_e=values.delta_e,
        width=values.width,
        height=values.height,
        comment=comment,
        raw=raw,
        machine_start=values.start_xyz,
        machine_end=values.end_xyz,
        coordinate_transform=coordinate_transform,
        has_spatial_axis=values.count_path_segment,
        has_spatial_length=has_spatial_length,
        path_segment_index=path_segment_index,
    )


def _finalize_file_coordinate_policy(
    segments: list[GCodePathSegment],
    timeline: list[GCodeTimelineStep],
    stats: _PreviewStats,
) -> None:
    present_words, active_words = _file_rotary_words(timeline)
    transform, issues = _file_coordinate_policy(stats, present_words, active_words)
    _apply_file_coordinate_result(segments, timeline, stats, transform, issues)


def _file_rotary_words(
    timeline: list[GCodeTimelineStep],
) -> tuple[set[str], set[str]]:
    present: set[str] = set()
    active: set[str] = set()
    for step in timeline:
        for rotary in (step.rotary_start, step.rotary_end):
            present.update(rotary)
            active.update(word for word, value in rotary.items() if abs(float(value)) > 1e-12)
    return present, active


def _file_coordinate_policy(
    stats: _PreviewStats,
    present_words: set[str],
    active_words: set[str],
) -> tuple[str, tuple[ValidationIssue, ...]]:
    required_words = active_words | (present_words & {"U", "V", "W"})
    if not required_words:
        return MACHINE_COORDINATE_TRANSFORM, ()

    semantics = DEFAULT_PREVIEW_KINEMATICS_REGISTRY.get(stats.controller_semantics)
    if semantics is None:
        return MACHINE_COORDINATE_TRANSFORM, (
            _coordinate_issue(
                "nc_preview.controller_semantics_unknown",
                controller_semantics=stats.controller_semantics or "",
                active_rotary_words=sorted(active_words),
                present_rotary_words=sorted(present_words),
            ),
        )

    unsupported_words = sorted(
        (active_words - semantics.supported_rotary_words)
        | ((present_words & {"U", "V", "W"}) - semantics.supported_rotary_words)
    )
    if unsupported_words:
        return MACHINE_COORDINATE_TRANSFORM, (
            _coordinate_issue(
                "nc_preview.rotary_words_unsupported",
                controller_semantics=semantics.semantics_id,
                unsupported_rotary_words=unsupported_words,
                active_rotary_words=sorted(active_words),
                present_rotary_words=sorted(present_words),
            ),
        )
    if stats.validation_issues:
        return MACHINE_COORDINATE_TRANSFORM, tuple(stats.validation_issues)
    return semantics.transform_name, ()


def _coordinate_issue(code: str, **context: Any) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=IssueSeverity.WARNING,
        object_id=NC_PREVIEW_OBJECT_ID,
        context=context,
    )


def _apply_file_coordinate_result(
    segments: list[GCodePathSegment],
    timeline: list[GCodeTimelineStep],
    stats: _PreviewStats,
    coordinate_transform: str,
    issues: tuple[ValidationIssue, ...],
) -> None:
    use_machine_coordinates = coordinate_transform == MACHINE_COORDINATE_TRANSFORM
    for segment in segments:
        if use_machine_coordinates:
            if segment.machine_start is not None:
                segment.start = segment.machine_start
            if segment.machine_end is not None:
                segment.end = segment.machine_end
        segment.coordinate_transform = coordinate_transform
    for step in timeline:
        if use_machine_coordinates:
            if step.machine_start is not None:
                step.start = step.machine_start
            if step.machine_end is not None:
                step.end = step.machine_end
        step.coordinate_transform = coordinate_transform
        step.has_spatial_length = _points_differ(step.start, step.end)
    stats.finalize_coordinate_result(timeline, coordinate_transform, issues)


def _points_differ(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> bool:
    return any(abs(left - right) > 1e-9 for left, right in zip(start, end, strict=False))


def _classify_move(command: str, has_motion: bool, linear_motion: bool, delta_e: float) -> str:
    if command == "G0":
        return "travel"
    if delta_e < -1e-12:
        return "travel" if has_motion else "retract"
    if delta_e > 1e-12:
        return "extrude" if has_motion else "prime"
    return "travel" if linear_motion or has_motion else "noop"


class _PreviewStats:
    def __init__(self, controller_semantics: str | None = None) -> None:
        self.total_segment_count = 0
        self.timeline_step_count = 0
        self.move_counts: dict[str, int] = {}
        self.role_counts: dict[str, int] = {}
        self.rotary_axes: set[str] = set()
        self.layer_min: int | None = None
        self.layer_max: int | None = None
        self.bounds_min: list[float] | None = None
        self.bounds_max: list[float] | None = None
        self.height_min: float | None = None
        self.height_max: float | None = None
        self.coordinate_transform = MACHINE_COORDINATE_TRANSFORM
        self.controller_semantics = controller_semantics
        self.validation_issues: list[ValidationIssue] = []
        self._issue_keys: set[str] = set()

    def add_values(
        self,
        values: _MotionValues,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        has_spatial_length: bool,
        validation_issues: tuple[ValidationIssue, ...],
    ) -> None:
        self.timeline_step_count += 1
        if values.count_path_segment:
            self.total_segment_count += 1
        self._add_issues(validation_issues)
        self.move_counts[values.move_type] = self.move_counts.get(values.move_type, 0) + 1
        if values.move_type == "extrude":
            self.role_counts[values.extrusion_role] = (
                self.role_counts.get(values.extrusion_role, 0) + 1
            )
        if values.height is not None:
            self.height_min = (
                values.height if self.height_min is None else min(self.height_min, values.height)
            )
            self.height_max = (
                values.height if self.height_max is None else max(self.height_max, values.height)
            )
        self.rotary_axes.update(values.rotary_start)
        self.rotary_axes.update(values.rotary_end)
        self.layer_min = (
            values.layer if self.layer_min is None else min(self.layer_min, values.layer)
        )
        self.layer_max = (
            values.layer if self.layer_max is None else max(self.layer_max, values.layer)
        )
        if has_spatial_length:
            self._include_points(start, end)

    def finalize_coordinate_result(
        self,
        timeline: list[GCodeTimelineStep],
        coordinate_transform: str,
        issues: tuple[ValidationIssue, ...],
    ) -> None:
        self.coordinate_transform = coordinate_transform
        self.validation_issues = []
        self._issue_keys = set()
        self._add_issues(issues)
        self.bounds_min = None
        self.bounds_max = None
        for step in timeline:
            if step.has_spatial_length:
                self._include_points(step.start, step.end)

    def _add_issues(self, issues: tuple[ValidationIssue, ...]) -> None:
        for issue in issues:
            key = json.dumps(issue.to_json(), ensure_ascii=True, sort_keys=True)
            if key in self._issue_keys:
                continue
            self._issue_keys.add(key)
            self.validation_issues.append(issue)

    def _include_points(self, *points: tuple[float, float, float]) -> None:
        for point in points:
            if self.bounds_min is None or self.bounds_max is None:
                self.bounds_min = list(point)
                self.bounds_max = list(point)
                continue
            for index, value in enumerate(point):
                self.bounds_min[index] = min(self.bounds_min[index], value)
                self.bounds_max[index] = max(self.bounds_max[index], value)


def _build_preview(
    source: Path,
    segments: list[GCodePathSegment],
    timeline: list[GCodeTimelineStep],
    stats: _PreviewStats,
) -> GCodePreview:
    if stats.timeline_step_count == 0:
        return GCodePreview(
            source,
            [],
            0,
            0,
            -1,
            None,
            {},
            {},
            [],
            timeline=[],
            controller_semantics=stats.controller_semantics,
            validation_issues=tuple(stats.validation_issues),
        )
    bounds = None
    if stats.bounds_min is not None and stats.bounds_max is not None:
        bounds = (
            (stats.bounds_min[0], stats.bounds_min[1], stats.bounds_min[2]),
            (stats.bounds_max[0], stats.bounds_max[1], stats.bounds_max[2]),
        )
    return GCodePreview(
        source,
        segments,
        stats.total_segment_count,
        stats.layer_min or 0,
        stats.layer_max if stats.layer_max is not None else -1,
        bounds,
        stats.move_counts,
        stats.role_counts,
        sorted(stats.rotary_axes),
        stats.coordinate_transform,
        timeline,
        stats.height_min,
        stats.height_max,
        controller_semantics=stats.controller_semantics,
        validation_issues=tuple(stats.validation_issues),
    )


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise GCodeLoadCancelled("G-code loading cancelled")
