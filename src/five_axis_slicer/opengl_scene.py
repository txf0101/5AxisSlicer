"""Build OpenGL scene arrays on the CPU without owning a GL context."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
import vtk

from .gcode_preview import (
    MOVE_CODES,
    ROLE_CODES,
    TIMELINE_FLAG_HAS_SPATIAL_LENGTH,
    GCodePathSegment,
    GCodePreview,
    GCodeTimelineStep,
    PreviewSettings,
)
from .models import BuildSurfaceOverlay, CoordinateFrameOverlay
from .viewer_common import (
    bead_frame,
    render_stride,
    validated_rigid_transform,
    vector3,
)

AXIS_X_COLOR = (0.890, 0.180, 0.150, 1.0)
AXIS_Y_COLOR = (0.120, 0.680, 0.260, 1.0)
AXIS_Z_COLOR = (0.130, 0.360, 0.920, 1.0)
PAPER_PATH_COLOR = (0.145, 0.388, 0.922, 0.94)
PAPER_TRAVEL_COLOR = (0.961, 0.620, 0.043, 0.42)
BEAD_SECTION_SIDES = 6
PAPER_PATH_JOIN_TOLERANCE_MM = 0.02


@dataclass(slots=True)
class EdgeSegment:
    edge_id: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class PaperPathArrays:
    vertices: np.ndarray
    colors: np.ndarray
    draw_starts: np.ndarray
    draw_counts: np.ndarray
    segment_count: int
    first_point: tuple[float, float, float] | None
    last_point: tuple[float, float, float] | None


def build_paper_path_arrays(
    preview: GCodePreview,
    settings: PreviewSettings,
    current_global_step: int | None,
    *,
    tolerance: float = PAPER_PATH_JOIN_TOLERANCE_MM,
) -> PaperPathArrays:
    timeline_arrays = preview.timeline_arrays
    if timeline_arrays is not None:
        count = timeline_arrays.count
        starts = timeline_arrays.starts
        ends = timeline_arrays.ends
        layers = timeline_arrays.layers
        line_numbers = timeline_arrays.line_numbers
        move_codes = timeline_arrays.move_codes
        role_codes = timeline_arrays.role_codes
        delta_es = timeline_arrays.delta_es
        spatial = (timeline_arrays.flags & TIMELINE_FLAG_HAS_SPATIAL_LENGTH) != 0
        step_indices: np.ndarray = np.arange(count, dtype=np.int64)
    else:
        # Imported NC has a full timeline; generated workbench paths provide
        # unsampled segments directly. Both must feed the same full-line view.
        timeline = cast(
            Sequence[GCodeTimelineStep | GCodePathSegment],
            preview.timeline if preview.timeline else preview.segments,
        )
        count = len(timeline)
        starts = np.asarray([step.start for step in timeline], dtype=np.float32).reshape((-1, 3))
        ends = np.asarray([step.end for step in timeline], dtype=np.float32).reshape((-1, 3))
        layers = np.asarray([step.layer for step in timeline], dtype=np.int32)
        line_numbers = np.asarray([step.line_number for step in timeline], dtype=np.int64)
        move_codes = np.asarray(
            [MOVE_CODES.get(step.move_type, MOVE_CODES["noop"]) for step in timeline],
            dtype=np.uint8,
        )
        role_codes = np.asarray(
            [ROLE_CODES.get(step.extrusion_role, ROLE_CODES["unknown"]) for step in timeline],
            dtype=np.uint8,
        )
        delta_es = np.asarray([step.delta_e for step in timeline], dtype=np.float32)
        spatial = np.asarray([step.has_spatial_length for step in timeline], dtype=np.bool_)
        step_indices = np.asarray([step.step_index for step in timeline], dtype=np.int64)

    if count == 0:
        return empty_paper_path_arrays()

    layer_mask = (layers >= min(settings.layer_min, settings.layer_max)) & (
        layers <= max(settings.layer_min, settings.layer_max)
    )
    if settings.line_min is not None:
        layer_mask &= line_numbers >= settings.line_min
    if settings.line_max is not None:
        layer_mask &= line_numbers <= settings.line_max
    extrusion_mask = (move_codes == MOVE_CODES["extrude"]) & (delta_es > 0.0) & spatial
    allowed_roles = np.asarray(
        [ROLE_CODES[role] for role in settings.visible_roles if role in ROLE_CODES],
        dtype=np.uint8,
    )
    role_mask = (
        np.isin(role_codes, allowed_roles)
        if allowed_roles.size
        else np.zeros(count, dtype=np.bool_)
    )
    selected_type = np.zeros(count, dtype=np.bool_)
    if settings.show_extrusion:
        selected_type |= extrusion_mask & role_mask
    if settings.show_travel:
        selected_type |= ~extrusion_mask
    visible = layer_mask & spatial & selected_type
    if current_global_step is not None and not settings.show_upcoming:
        visible &= step_indices <= int(current_global_step)

    indices = np.flatnonzero(visible)
    if indices.size == 0:
        return empty_paper_path_arrays()
    selected_starts = np.asarray(starts[indices], dtype=np.float32)
    selected_ends = np.asarray(ends[indices], dtype=np.float32)
    selected_extrusion = extrusion_mask[indices]
    segment_colors = np.empty((indices.size, 4), dtype=np.float32)
    segment_colors[selected_extrusion] = PAPER_PATH_COLOR
    segment_colors[~selected_extrusion] = PAPER_TRAVEL_COLOR
    vertices, colors, draw_starts, draw_counts = build_continuous_line_strips(
        selected_starts,
        selected_ends,
        segment_colors,
        selected_extrusion.astype(np.uint8),
        tolerance=tolerance,
    )
    return PaperPathArrays(
        vertices=vertices,
        colors=colors,
        draw_starts=draw_starts,
        draw_counts=draw_counts,
        segment_count=int(indices.size),
        first_point=vector3(selected_starts[0]),
        last_point=vector3(selected_ends[-1]),
    )


def empty_paper_path_arrays() -> PaperPathArrays:
    return PaperPathArrays(
        vertices=np.empty((0, 3), dtype=np.float32),
        colors=np.empty((0, 4), dtype=np.float32),
        draw_starts=np.empty((0,), dtype=np.int32),
        draw_counts=np.empty((0,), dtype=np.int32),
        segment_count=0,
        first_point=None,
        last_point=None,
    )


def build_continuous_line_strips(
    starts: np.ndarray,
    ends: np.ndarray,
    segment_colors: np.ndarray,
    style_keys: np.ndarray,
    *,
    tolerance: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    starts = np.asarray(starts, dtype=np.float32).reshape((-1, 3))
    ends = np.asarray(ends, dtype=np.float32).reshape((-1, 3))
    segment_colors = np.asarray(segment_colors, dtype=np.float32).reshape((-1, 4))
    style_keys = np.asarray(style_keys).reshape((-1,))
    count = int(starts.shape[0])
    if ends.shape[0] != count or segment_colors.shape[0] != count or style_keys.size != count:
        raise ValueError("Polyline source arrays must contain the same number of segments")
    if count == 0:
        return (
            np.empty((0, 3), dtype=np.float32),
            np.empty((0, 4), dtype=np.float32),
            np.empty((0,), dtype=np.int32),
            np.empty((0,), dtype=np.int32),
        )

    break_before = np.ones(count, dtype=np.bool_)
    if count > 1:
        gaps = starts[1:] - ends[:-1]
        distance_sq = np.einsum("ij,ij->i", gaps, gaps)
        break_before[1:] = (distance_sq > max(0.0, float(tolerance)) ** 2) | (
            style_keys[1:] != style_keys[:-1]
        )
    break_indices = np.flatnonzero(break_before).astype(np.int32, copy=False)
    polyline_ids = np.cumsum(break_before, dtype=np.int32) - 1
    start_positions = np.arange(count, dtype=np.int32) + polyline_ids
    end_positions = start_positions + 1
    vertices = np.empty((count + int(break_indices.size), 3), dtype=np.float32)
    vertices[start_positions] = starts
    vertices[end_positions] = ends
    draw_starts = break_indices + np.arange(break_indices.size, dtype=np.int32)
    run_ends = np.append(break_indices[1:], np.int32(count))
    draw_counts = (run_ends - break_indices + 1).astype(np.int32, copy=False)
    colors = np.repeat(segment_colors[break_indices], draw_counts, axis=0).astype(
        np.float32, copy=False
    )
    return vertices, colors, draw_starts, draw_counts


def points_array(points: Iterable[Iterable[float]]) -> np.ndarray:
    values = tuple(tuple(point) for point in points)
    return (
        np.asarray(values, dtype=np.float32).reshape((-1, 3))
        if values
        else np.empty((0, 3), dtype=np.float32)
    )


def validate_coordinate_frame(frame: CoordinateFrameOverlay) -> None:
    origin = np.asarray(frame.origin, dtype=np.float64)
    basis = np.column_stack((frame.x_axis, frame.y_axis, frame.z_axis)).astype(np.float64)
    if (
        origin.shape != (3,)
        or basis.shape != (3, 3)
        or not np.isfinite(origin).all()
        or not np.isfinite(basis).all()
    ):
        raise ValueError(f"coordinate frame {frame.frame_id!r} must contain finite 3D vectors")
    lengths = np.linalg.norm(basis, axis=0)
    if np.any(lengths <= 1e-12):
        raise ValueError(f"coordinate frame {frame.frame_id!r} contains a zero axis")
    normalized = basis / lengths
    if not np.allclose(normalized.T @ normalized, np.eye(3), atol=1e-5, rtol=0.0):
        raise ValueError(f"coordinate frame {frame.frame_id!r} axes must be orthogonal")
    if float(np.linalg.det(normalized)) <= 0.0:
        raise ValueError(f"coordinate frame {frame.frame_id!r} must be right-handed")
    if not math.isfinite(float(frame.scale)) or float(frame.scale) <= 0.0:
        raise ValueError(f"coordinate frame {frame.frame_id!r} scale must be positive")


def coordinate_frame_lines(
    frame: CoordinateFrameOverlay,
    scale: float,
) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[float, float, float, float]],
]:
    origin = np.asarray(frame.origin, dtype=np.float64)
    vertices: list[tuple[float, float, float]] = []
    colors: list[tuple[float, float, float, float]] = []
    for axis, color in (
        (frame.x_axis, AXIS_X_COLOR),
        (frame.y_axis, AXIS_Y_COLOR),
        (frame.z_axis, AXIS_Z_COLOR),
    ):
        lines = axis_arrow_lines(origin, np.asarray(axis, dtype=np.float64), scale)
        vertices.extend(lines)
        colors.extend([color] * len(lines))
    return vertices, colors


def axis_arrow_lines(
    origin: np.ndarray,
    direction: np.ndarray,
    scale: float,
) -> list[tuple[float, float, float]]:
    direction = direction / np.linalg.norm(direction)
    tip = origin + direction * scale
    helper = np.array((0.0, 0.0, 1.0), dtype=np.float64)
    if abs(float(np.dot(direction, helper))) > 0.88:
        helper = np.array((0.0, 1.0, 0.0), dtype=np.float64)
    side = np.cross(direction, helper)
    side /= np.linalg.norm(side)
    up = np.cross(direction, side)
    arrow_base = tip - direction * scale * 0.20
    points = [vector3(origin), vector3(tip)]
    for offset in (
        side * scale * 0.085,
        -side * scale * 0.085,
        up * scale * 0.085,
        -up * scale * 0.085,
    ):
        points.extend((vector3(tip), vector3(arrow_base + offset)))
    return points


def build_surface_lines(
    surface: BuildSurfaceOverlay,
) -> list[tuple[float, float, float]]:
    origin = np.asarray(surface.origin, dtype=np.float64)
    x_axis = np.asarray(surface.x_axis, dtype=np.float64)
    y_axis = np.asarray(surface.y_axis, dtype=np.float64)
    if (
        origin.shape != (3,)
        or x_axis.shape != (3,)
        or y_axis.shape != (3,)
        or not np.isfinite(np.concatenate((origin, x_axis, y_axis))).all()
    ):
        raise ValueError("build surface basis must contain finite 3D vectors")
    x_length, y_length = float(np.linalg.norm(x_axis)), float(np.linalg.norm(y_axis))
    if x_length <= 1e-12 or y_length <= 1e-12:
        raise ValueError("build surface axes must be nonzero")
    x_axis, y_axis = x_axis / x_length, y_axis / y_length
    if abs(float(np.dot(x_axis, y_axis))) > 1e-5:
        raise ValueError("build surface axes must be orthogonal")

    shape = str(surface.shape).lower()
    if shape == "circle":
        diameter = 100.0 if surface.diameter_mm is None else float(surface.diameter_mm)
        if not math.isfinite(diameter) or diameter <= 0.0:
            raise ValueError("circular build surface diameter must be positive")
        half_x = half_y = diameter * 0.5
        local = [
            (
                half_x * math.cos(2.0 * math.pi * index / 64),
                half_y * math.sin(2.0 * math.pi * index / 64),
            )
            for index in range(64)
        ]
    elif shape == "rectangle":
        width = 100.0 if surface.width_mm is None else float(surface.width_mm)
        depth = width if surface.depth_mm is None else float(surface.depth_mm)
        if not all(math.isfinite(value) and value > 0.0 for value in (width, depth)):
            raise ValueError("rectangular build surface dimensions must be positive")
        half_x, half_y = width * 0.5, depth * 0.5
        local = [
            (-half_x, -half_y),
            (half_x, -half_y),
            (half_x, half_y),
            (-half_x, half_y),
        ]
    else:
        raise ValueError(f"unsupported build surface shape: {surface.shape}")

    def world(point: tuple[float, float]) -> tuple[float, float, float]:
        return vector3(origin + point[0] * x_axis + point[1] * y_axis)

    vertices: list[tuple[float, float, float]] = []
    for index, point in enumerate(local):
        vertices.extend((world(point), world(local[(index + 1) % len(local)])))
    vertices.extend((world((-half_x, 0.0)), world((half_x, 0.0))))
    vertices.extend((world((0.0, -half_y)), world((0.0, half_y))))
    return vertices


def vertex_marker_lines(
    point: tuple[float, float, float],
    radius: float,
) -> list[tuple[float, float, float]]:
    center = np.asarray(point, dtype=np.float64)
    return [vector3(center + sign * axis * radius) for axis in np.eye(3) for sign in (-1.0, 1.0)]


def transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    values = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    if values.size == 0:
        return np.empty((0, 3), dtype=np.float32)
    homogeneous = np.column_stack((values, np.ones(len(values), dtype=np.float64)))
    transformed = (np.asarray(matrix, dtype=np.float64) @ homogeneous.T).T
    return np.asarray(transformed[:, :3] / transformed[:, 3, None], dtype=np.float32)


def nice_grid_step(target: float) -> float:
    target = max(float(target), 1e-6)
    magnitude = 10.0 ** math.floor(math.log10(target))
    fraction = target / magnitude
    multiplier = 1.0 if fraction <= 1.0 else 2.0 if fraction <= 2.0 else 5.0
    return (10.0 if fraction > 5.0 else multiplier) * magnitude


def inclusive_grid_values(low: float, high: float, step: float) -> list[float]:
    return [low + index * step for index in range(max(0, int(round((high - low) / step))) + 1)]


def polydata_triangles(polydata) -> list[tuple[float, float, float]]:
    points = polydata.GetPoints()
    if points is None:
        return []
    output: list[tuple[float, float, float]] = []
    ids = vtk.vtkIdList()
    polys = polydata.GetPolys()
    polys.InitTraversal()
    while polys.GetNextCell(ids):
        if ids.GetNumberOfIds() < 3:
            continue
        first = tuple(points.GetPoint(ids.GetId(0)))
        for index in range(1, ids.GetNumberOfIds() - 1):
            output.extend(
                (
                    first,
                    tuple(points.GetPoint(ids.GetId(index))),
                    tuple(points.GetPoint(ids.GetId(index + 1))),
                )
            )
    return output


def polydata_lines(
    polydata,
) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    points = polydata.GetPoints()
    if points is None:
        return []
    output: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
    ids = vtk.vtkIdList()
    lines = polydata.GetLines()
    lines.InitTraversal()
    while lines.GetNextCell(ids):
        output.extend(
            (
                tuple(points.GetPoint(ids.GetId(index))),
                tuple(points.GetPoint(ids.GetId(index + 1))),
            )
            for index in range(ids.GetNumberOfIds() - 1)
        )
    return output


def build_line_arrays(
    segments: list[GCodePathSegment],
    stride: int,
) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[float, float, float, float]],
    int,
]:
    vertices: list[tuple[float, float, float]] = []
    colors: list[tuple[float, float, float, float]] = []
    drawn = 0
    for index, segment in enumerate(segments):
        if stride > 1 and index % stride:
            continue
        color = (*segment.color(), 0.96 if segment.move_type == "extrude" else 0.48)
        vertices.extend((segment.start, segment.end))
        colors.extend((color, color))
        drawn += 1
    return vertices, colors, drawn


def build_bead_arrays(
    segments: list[GCodePathSegment],
    stride: int,
    *,
    controller_semantics: str | None = None,
) -> tuple[
    list[tuple[float, float, float]],
    list[tuple[float, float, float, float]],
    int,
]:
    vertices: list[tuple[float, float, float]] = []
    colors: list[tuple[float, float, float, float]] = []
    drawn = 0
    for index, segment in enumerate(segments):
        if segment.move_type != "extrude" or (stride > 1 and index % stride):
            continue
        frame = bead_frame(
            segment.start,
            segment.end,
            segment.rotary_end,
            controller_semantics=controller_semantics,
            coordinate_transform=segment.coordinate_transform,
        )
        if frame is None:
            continue
        _, width_axis, height_axis = frame
        width_radius = max(segment.bead_width, 1e-6) * 0.5
        height_radius = max(segment.bead_height, 1e-6) * 0.5
        rings: list[list[tuple[float, float, float]]] = [[], []]
        for side in range(BEAD_SECTION_SIDES):
            angle = 2.0 * math.pi * side / BEAD_SECTION_SIDES
            offset = vector3(
                math.cos(angle) * width_radius * width_axis[axis]
                + math.sin(angle) * height_radius * height_axis[axis]
                for axis in range(3)
            )
            for ring, point in zip(rings, (segment.start, segment.end), strict=False):
                ring.append(
                    (
                        point[0] + offset[0],
                        point[1] + offset[1],
                        point[2] + offset[2],
                    )
                )
        color = (*segment.color(), 0.96)
        for side in range(BEAD_SECTION_SIDES):
            next_side = (side + 1) % BEAD_SECTION_SIDES
            quad = [
                rings[0][side],
                rings[0][next_side],
                rings[1][next_side],
                rings[1][side],
            ]
            vertices.extend((quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]))
            colors.extend([color] * 6)
        drawn += 1
    return vertices, colors, drawn


_EdgeSegment = EdgeSegment
_PaperPathArrays = PaperPathArrays
_build_paper_path_arrays = build_paper_path_arrays
_empty_paper_path_arrays = empty_paper_path_arrays
_build_continuous_line_strips = build_continuous_line_strips
_points_array = points_array
_validated_rigid_transform = validated_rigid_transform
_validate_coordinate_frame = validate_coordinate_frame
_coordinate_frame_lines = coordinate_frame_lines
_axis_arrow_lines = axis_arrow_lines
_build_surface_lines = build_surface_lines
_vertex_marker_lines = vertex_marker_lines
_transform_points = transform_points
_nice_grid_step = nice_grid_step
_inclusive_grid_values = inclusive_grid_values
_polydata_triangles = polydata_triangles
_polydata_lines = polydata_lines
_build_line_arrays = build_line_arrays
_build_bead_arrays = build_bead_arrays
_render_stride = render_stride
