"""Dense NumPy codec for preview segments and timeline steps."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from .manufacturing.preview_kinematics import (
    AC_INVERSE_TRANSFORM,
    MACHINE_COORDINATE_TRANSFORM,
)

if TYPE_CHECKING:
    from .gcode_preview import (
        GCodePathSegment,
        GCodeTimelineArrays,
        GCodeTimelineStep,
    )


def _build_role_move_chunks(
    segments: list[GCodePathSegment],
) -> list[dict[str, Any]]:
    if not segments:
        return []
    chunks: list[dict[str, Any]] = []
    start = 0
    previous = _segment_key(segments[0])
    for index, segment in enumerate(segments[1:], start=1):
        current = _segment_key(segment)
        if current == previous:
            continue
        chunks.append(_role_move_chunk(start, index, previous))
        start, previous = index, current
    chunks.append(_role_move_chunk(start, len(segments), previous))
    return chunks


def _segment_key(segment: GCodePathSegment) -> tuple[int, str, str, str]:
    return (
        segment.layer,
        segment.move_type,
        segment.extrusion_role,
        segment.color_key(),
    )


def _role_move_chunk(start: int, end: int, key: tuple[int, str, str, str]) -> dict[str, Any]:
    layer, move_type, role, color_key = key
    return {
        "start": start,
        "end": end,
        "layer": layer,
        "move_type": move_type,
        "extrusion_role": role,
        "color_key": color_key,
    }


def _timeline_arrays_from_steps(
    steps: list[GCodeTimelineStep],
) -> GCodeTimelineArrays:
    from .gcode_preview import MOVE_CODES, ROLE_CODES, GCodeTimelineArrays

    return GCodeTimelineArrays(
        line_numbers=np.asarray([step.line_number for step in steps], dtype=np.int32),
        layers=np.asarray([step.layer for step in steps], dtype=np.int32),
        starts=_points_array([step.start for step in steps]),
        ends=_points_array([step.end for step in steps]),
        rotary_starts=_rotary_array([step.rotary_start for step in steps]),
        rotary_ends=_rotary_array([step.rotary_end for step in steps]),
        move_codes=np.asarray(
            [MOVE_CODES.get(step.move_type, MOVE_CODES["noop"]) for step in steps],
            dtype=np.uint8,
        ),
        role_codes=np.asarray(
            [ROLE_CODES.get(step.extrusion_role, ROLE_CODES["unknown"]) for step in steps],
            dtype=np.uint8,
        ),
        feedrates=np.asarray([_nan_if_none(step.feedrate) for step in steps], dtype=np.float32),
        delta_es=np.asarray([step.delta_e for step in steps], dtype=np.float32),
        widths=np.asarray([_nan_if_none(step.width) for step in steps], dtype=np.float32),
        heights=np.asarray([_nan_if_none(step.height) for step in steps], dtype=np.float32),
        machine_starts=_optional_points_array([step.machine_start for step in steps]),
        machine_ends=_optional_points_array([step.machine_end for step in steps]),
        flags=np.asarray([_timeline_flags(step) for step in steps], dtype=np.uint8),
        path_segment_indices=np.asarray(
            [-1 if step.path_segment_index is None else step.path_segment_index for step in steps],
            dtype=np.int32,
        ),
    )


def _timeline_arrays_from_npz(payload: Any) -> GCodeTimelineArrays:
    from .gcode_preview import GCodeTimelineArrays

    return GCodeTimelineArrays(
        line_numbers=np.asarray(payload["timeline_line_numbers"], dtype=np.int32),
        layers=np.asarray(payload["timeline_layers"], dtype=np.int32),
        starts=np.asarray(payload["timeline_starts"], dtype=np.float32),
        ends=np.asarray(payload["timeline_ends"], dtype=np.float32),
        rotary_starts=np.asarray(payload["timeline_rotary_starts"], dtype=np.float32),
        rotary_ends=np.asarray(payload["timeline_rotary_ends"], dtype=np.float32),
        move_codes=np.asarray(payload["timeline_move_codes"], dtype=np.uint8),
        role_codes=np.asarray(payload["timeline_role_codes"], dtype=np.uint8),
        feedrates=np.asarray(payload["timeline_feedrates"], dtype=np.float32),
        delta_es=np.asarray(payload["timeline_delta_es"], dtype=np.float32),
        widths=np.asarray(payload["timeline_widths"], dtype=np.float32),
        heights=np.asarray(payload["timeline_heights"], dtype=np.float32),
        machine_starts=np.asarray(payload["timeline_machine_starts"], dtype=np.float32),
        machine_ends=np.asarray(payload["timeline_machine_ends"], dtype=np.float32),
        flags=np.asarray(payload["timeline_flags"], dtype=np.uint8),
        path_segment_indices=np.asarray(payload["timeline_path_segment_indices"], dtype=np.int32),
    )


def _segment_npz_arrays(
    segments: list[GCodePathSegment],
) -> dict[str, np.ndarray]:
    from .gcode_preview import MOVE_CODES, ROLE_CODES

    return {
        "segment_step_indices": np.asarray(
            [segment.step_index for segment in segments], dtype=np.int32
        ),
        "segment_line_numbers": np.asarray(
            [segment.line_number for segment in segments], dtype=np.int32
        ),
        "segment_layers": np.asarray([segment.layer for segment in segments], dtype=np.int32),
        "segment_starts": _points_array([segment.start for segment in segments]),
        "segment_ends": _points_array([segment.end for segment in segments]),
        "segment_rotary_starts": _rotary_array([segment.rotary_start for segment in segments]),
        "segment_rotary_ends": _rotary_array([segment.rotary_end for segment in segments]),
        "segment_move_codes": np.asarray(
            [MOVE_CODES.get(segment.move_type, MOVE_CODES["noop"]) for segment in segments],
            dtype=np.uint8,
        ),
        "segment_role_codes": np.asarray(
            [ROLE_CODES.get(segment.extrusion_role, ROLE_CODES["unknown"]) for segment in segments],
            dtype=np.uint8,
        ),
        "segment_feedrates": np.asarray(
            [_nan_if_none(segment.feedrate) for segment in segments],
            dtype=np.float32,
        ),
        "segment_delta_es": np.asarray([segment.delta_e for segment in segments], dtype=np.float32),
        "segment_widths": np.asarray(
            [_nan_if_none(segment.width) for segment in segments], dtype=np.float32
        ),
        "segment_heights": np.asarray(
            [_nan_if_none(segment.height) for segment in segments], dtype=np.float32
        ),
        "segment_machine_starts": _optional_points_array(
            [segment.machine_start for segment in segments]
        ),
        "segment_machine_ends": _optional_points_array(
            [segment.machine_end for segment in segments]
        ),
        "segment_coordinate_flags": np.asarray(
            [
                1 if segment.coordinate_transform == AC_INVERSE_TRANSFORM else 0
                for segment in segments
            ],
            dtype=np.uint8,
        ),
    }


def _segments_from_npz(payload: Any) -> list[GCodePathSegment]:
    from .gcode_preview import GCodePathSegment

    step_indices = np.asarray(payload["segment_step_indices"], dtype=np.int32)
    line_numbers = np.asarray(payload["segment_line_numbers"], dtype=np.int32)
    layers = np.asarray(payload["segment_layers"], dtype=np.int32)
    starts = np.asarray(payload["segment_starts"], dtype=np.float32)
    ends = np.asarray(payload["segment_ends"], dtype=np.float32)
    rotary_starts = np.asarray(payload["segment_rotary_starts"], dtype=np.float32)
    rotary_ends = np.asarray(payload["segment_rotary_ends"], dtype=np.float32)
    move_codes = np.asarray(payload["segment_move_codes"], dtype=np.uint8)
    role_codes = np.asarray(payload["segment_role_codes"], dtype=np.uint8)
    feedrates = np.asarray(payload["segment_feedrates"], dtype=np.float32)
    delta_es = np.asarray(payload["segment_delta_es"], dtype=np.float32)
    widths = np.asarray(payload["segment_widths"], dtype=np.float32)
    heights = np.asarray(payload["segment_heights"], dtype=np.float32)
    machine_starts = np.asarray(payload["segment_machine_starts"], dtype=np.float32)
    machine_ends = np.asarray(payload["segment_machine_ends"], dtype=np.float32)
    coordinate_flags = np.asarray(payload["segment_coordinate_flags"], dtype=np.uint8)
    return [
        GCodePathSegment(
            step_index=int(step_indices[index]),
            line_number=int(line_numbers[index]),
            layer=int(layers[index]),
            start=_tuple3(starts[index]),
            end=_tuple3(ends[index]),
            rotary_start=_rotary_row_to_dict(rotary_starts[index]),
            rotary_end=_rotary_row_to_dict(rotary_ends[index]),
            move_type=_move_from_code(int(move_codes[index])),
            extrusion_role=_role_from_code(int(role_codes[index])),
            feedrate=_none_if_nan(float(feedrates[index])),
            delta_e=float(delta_es[index]),
            width=_none_if_nan(float(widths[index])),
            height=_none_if_nan(float(heights[index])),
            machine_start=_tuple3_or_none(machine_starts[index]),
            machine_end=_tuple3_or_none(machine_ends[index]),
            coordinate_transform=(
                AC_INVERSE_TRANSFORM
                if int(coordinate_flags[index]) == 1
                else MACHINE_COORDINATE_TRANSFORM
            ),
        )
        for index in range(len(line_numbers))
    ]


def _timeline_flags(step: GCodeTimelineStep) -> int:
    from .gcode_preview import (
        TIMELINE_FLAG_AC_TRANSFORM,
        TIMELINE_FLAG_HAS_SPATIAL_AXIS,
        TIMELINE_FLAG_HAS_SPATIAL_LENGTH,
    )

    flags = TIMELINE_FLAG_HAS_SPATIAL_AXIS if step.has_spatial_axis else 0
    if step.has_spatial_length:
        flags |= TIMELINE_FLAG_HAS_SPATIAL_LENGTH
    if step.coordinate_transform == AC_INVERSE_TRANSFORM:
        flags |= TIMELINE_FLAG_AC_TRANSFORM
    return flags


def _points_array(points: list[tuple[float, float, float]]) -> np.ndarray:
    if not points:
        return np.empty((0, 3), dtype=np.float32)
    return np.asarray(points, dtype=np.float32)


def _optional_points_array(
    points: list[tuple[float, float, float] | None],
) -> np.ndarray:
    if not points:
        return np.empty((0, 3), dtype=np.float32)
    return np.asarray(
        [point if point is not None else (np.nan, np.nan, np.nan) for point in points],
        dtype=np.float32,
    )


def _rotary_array(rotaries: list[dict[str, float]]) -> np.ndarray:
    from .gcode_preview import ROTARY_AXES

    if not rotaries:
        return np.empty((0, len(ROTARY_AXES)), dtype=np.float32)
    return np.asarray(
        [[values.get(axis, 0.0) for axis in ROTARY_AXES] for values in rotaries],
        dtype=np.float32,
    )


def _rotary_row_to_dict(row: np.ndarray) -> dict[str, float]:
    from .gcode_preview import ROTARY_AXES

    return {
        axis: float(row[index])
        for index, axis in enumerate(ROTARY_AXES)
        if abs(float(row[index])) > 1.0e-9
    }


def _tuple3(row: np.ndarray) -> tuple[float, float, float]:
    return (float(row[0]), float(row[1]), float(row[2]))


def _tuple3_or_none(row: np.ndarray) -> tuple[float, float, float] | None:
    if np.isnan(row).all():
        return None
    return _tuple3(row)


def _none_if_nan(value: float) -> float | None:
    return None if np.isnan(value) else value


def _nan_if_none(value: float | None) -> float:
    return np.nan if value is None else float(value)


def _index_or_none(value: int) -> int | None:
    return None if value < 0 else value


def _move_from_code(code: int) -> str:
    from .gcode_preview import MOVE_NAMES

    return MOVE_NAMES[code] if 0 <= code < len(MOVE_NAMES) else "noop"


def _role_from_code(code: int) -> str:
    from .gcode_preview import ROLE_NAMES

    return ROLE_NAMES[code] if 0 <= code < len(ROLE_NAMES) else "unknown"
