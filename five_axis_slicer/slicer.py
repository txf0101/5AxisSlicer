"""Hybrid slicing pipeline.

The slicer follows the Open5X-style intent more closely:
1. detect the central rotary body and print it first with fixed U/V,
2. remove that body from the conformal surface map,
3. generate five-axis paths for the surrounding blades / shell.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import ndimage
from skimage import measure

from .core import MeshModel, SliceParameters, SliceResult, SurfaceMap, Toolpath
from .geometry import resample_polyline
from .planar import RotaryCoreProfile, estimate_rotary_core_profile, point_in_polygon, slice_planar_core


class ConformalSlicer:
    """Main entry point for hybrid slicing."""

    def slice(self, mesh: MeshModel, params: SliceParameters) -> SliceResult:
        working_mesh = mesh.centered_for_build() if params.auto_center_model else mesh
        warnings: list[str] = []
        toolpaths: list[Toolpath] = []

        if params.enable_planar_core:
            core_profile = estimate_rotary_core_profile(working_mesh, params)
        else:
            core_profile = RotaryCoreProfile(
                center_xy=np.zeros(2, dtype=float),
                z_levels_mm=np.zeros(0, dtype=float),
                radii_mm=np.zeros(0, dtype=float),
            )

        planar_toolpaths: list[Toolpath] = []
        planar_meta: dict[str, int | float] = {
            "layer_count": 0,
            "path_count": 0,
            "transition_height_mm": 0.0,
        }
        if params.enable_planar_core and not core_profile.is_empty:
            planar_toolpaths, planar_meta, planar_warnings = slice_planar_core(working_mesh, core_profile, params)
            toolpaths.extend(planar_toolpaths)
            warnings.extend(planar_warnings)
        elif params.enable_planar_core:
            warnings.append("No stable rotary core was detected near the model centre, so the planar core phase was skipped.")

        full_surface_map = build_surface_map(working_mesh, params)
        conformal_surface_map = exclude_rotary_core_from_surface(
            full_surface_map,
            core_profile,
            margin_mm=max(params.line_spacing_mm * 0.45, params.nozzle_diameter_mm * 0.35),
        )

        conformal_perimeters = generate_conformal_perimeter_paths(conformal_surface_map, params, core_profile=core_profile)
        if not conformal_perimeters:
            warnings.append("No conformal perimeter paths were generated. The model may only support open edge segments after the rotary core is removed.")

        conformal_infill: list[Toolpath] = []
        if params.include_infill:
            conformal_infill = generate_conformal_infill_paths(conformal_surface_map, params)
            if not conformal_infill:
                warnings.append("No conformal infill paths were generated for the selected surface.")

        conformal_toolpaths = conformal_perimeters + conformal_infill
        toolpaths.extend(conformal_toolpaths)

        metadata = {
            "path_count": len(toolpaths),
            "planar_path_count": len(planar_toolpaths),
            "conformal_path_count": len(conformal_toolpaths),
            "conformal_perimeter_count": len(conformal_perimeters),
            "conformal_infill_count": len(conformal_infill),
            "planar_layer_count": int(planar_meta.get("layer_count", 0)),
            "model_size_mm": working_mesh.size.tolist(),
            "surface_samples": int(conformal_surface_map.valid_mask.sum()),
            "full_surface_samples": int(full_surface_map.valid_mask.sum()),
            "transition_height_mm": float(planar_meta.get("transition_height_mm", 0.0)),
            "surface_min_z_mm": float(np.nanmin(conformal_surface_map.z_map)) if np.any(conformal_surface_map.valid_mask) else 0.0,
            "surface_max_z_mm": float(np.nanmax(conformal_surface_map.z_map)) if np.any(conformal_surface_map.valid_mask) else 0.0,
            "core_center_x_mm": float(core_profile.center_xy[0]) if len(core_profile.center_xy) == 2 else 0.0,
            "core_center_y_mm": float(core_profile.center_xy[1]) if len(core_profile.center_xy) == 2 else 0.0,
            "core_max_radius_mm": float(np.max(core_profile.radii_mm)) if len(core_profile.radii_mm) else 0.0,
            "core_min_z_mm": float(core_profile.min_z_mm) if not core_profile.is_empty else 0.0,
            "core_max_z_mm": float(core_profile.max_z_mm) if not core_profile.is_empty else 0.0,
        }

        return SliceResult(
            mesh=working_mesh,
            surface_map=conformal_surface_map,
            toolpaths=toolpaths,
            warnings=warnings,
            metadata=metadata,
        )


def build_surface_map(mesh: MeshModel, params: SliceParameters) -> SurfaceMap:
    """Sample the printable top surface on a regular XY grid."""

    bounds_min = mesh.bounds_min
    bounds_max = mesh.bounds_max
    step = max(params.grid_step_mm, 0.1)

    x_coords = np.arange(bounds_min[0], bounds_max[0] + step, step, dtype=float)
    y_coords = np.arange(bounds_min[1], bounds_max[1] + step, step, dtype=float)

    z_map = np.full((len(y_coords), len(x_coords)), -np.inf, dtype=float)
    normal_map = np.zeros((len(y_coords), len(x_coords), 3), dtype=float)

    tri_vertices = mesh.face_vertices
    tri_vertex_normals = mesh.vertex_normals[mesh.faces]

    for tri, normals in zip(tri_vertices, tri_vertex_normals):
        projected = tri[:, :2]
        normal_hint = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        if np.linalg.norm(normal_hint) < 1e-9:
            continue
        face_normal = normal_hint / np.linalg.norm(normal_hint)
        if face_normal[2] < params.top_normal_threshold:
            continue

        x_min, y_min = projected.min(axis=0)
        x_max, y_max = projected.max(axis=0)
        col_start = max(0, int(math.floor((x_min - x_coords[0]) / step)))
        col_end = min(len(x_coords) - 1, int(math.ceil((x_max - x_coords[0]) / step)))
        row_start = max(0, int(math.floor((y_min - y_coords[0]) / step)))
        row_end = min(len(y_coords) - 1, int(math.ceil((y_max - y_coords[0]) / step)))
        if col_end <= col_start or row_end <= row_start:
            continue

        xs = x_coords[col_start : col_end + 1]
        ys = y_coords[row_start : row_end + 1]
        xx, yy = np.meshgrid(xs, ys)
        bary = _barycentric_2d(projected, xx, yy)
        inside = np.all(bary >= -1e-6, axis=-1)
        if not np.any(inside):
            continue

        zz = bary[..., 0] * tri[0, 2] + bary[..., 1] * tri[1, 2] + bary[..., 2] * tri[2, 2]
        interp_normals = bary[..., 0, None] * normals[0] + bary[..., 1, None] * normals[1] + bary[..., 2, None] * normals[2]
        interp_normals = _normalize(interp_normals)

        current = z_map[row_start : row_end + 1, col_start : col_end + 1]
        better = inside & (zz > current)
        if np.any(better):
            current[better] = zz[better]
            z_map[row_start : row_end + 1, col_start : col_end + 1] = current
            block = normal_map[row_start : row_end + 1, col_start : col_end + 1]
            block[better] = interp_normals[better]
            normal_map[row_start : row_end + 1, col_start : col_end + 1] = block

    valid_mask = np.isfinite(z_map)
    z_map[~valid_mask] = np.nan
    normal_map[~valid_mask] = np.array([0.0, 0.0, 1.0])

    return SurfaceMap(
        x_min=float(x_coords[0]),
        y_min=float(y_coords[0]),
        step_mm=step,
        x_coords=x_coords,
        y_coords=y_coords,
        z_map=z_map,
        normal_map=normal_map,
        valid_mask=valid_mask,
    )


def exclude_rotary_core_from_surface(
    surface_map: SurfaceMap,
    core_profile: RotaryCoreProfile,
    margin_mm: float,
) -> SurfaceMap:
    """Remove the already-printed rotary core from the conformal surface mask."""

    if core_profile.is_empty or not np.any(surface_map.valid_mask):
        return surface_map

    xx, yy = np.meshgrid(surface_map.x_coords, surface_map.y_coords)
    radial_distance = np.sqrt((xx - core_profile.center_xy[0]) ** 2 + (yy - core_profile.center_xy[1]) ** 2)

    filtered_valid = surface_map.valid_mask.copy()
    valid_rows, valid_cols = np.nonzero(filtered_valid)
    if len(valid_rows) == 0:
        return surface_map

    valid_z = surface_map.z_map[valid_rows, valid_cols]
    core_radii = np.interp(valid_z, core_profile.z_levels_mm, core_profile.radii_mm, left=0.0, right=0.0)
    # Everything inside the detected rotary core is treated as already printed by the
    # planar phase, so the conformal phase must stay outside this radius.
    keep = radial_distance[valid_rows, valid_cols] > (core_radii + margin_mm)
    filtered_valid[valid_rows, valid_cols] = keep

    z_map = surface_map.z_map.copy()
    normal_map = surface_map.normal_map.copy()
    z_map[~filtered_valid] = np.nan
    normal_map[~filtered_valid] = np.array([0.0, 0.0, 1.0])
    return SurfaceMap(
        x_min=surface_map.x_min,
        y_min=surface_map.y_min,
        step_mm=surface_map.step_mm,
        x_coords=surface_map.x_coords.copy(),
        y_coords=surface_map.y_coords.copy(),
        z_map=z_map,
        normal_map=normal_map,
        valid_mask=filtered_valid,
    )


def generate_conformal_perimeter_paths(
    surface_map: SurfaceMap,
    params: SliceParameters,
    core_profile: RotaryCoreProfile | None = None,
) -> list[Toolpath]:
    paths: list[Toolpath] = []
    if not np.any(surface_map.valid_mask):
        return paths

    component_maps = split_surface_map_by_height(
        surface_map,
        z_jump_threshold_mm=max(surface_map.step_mm * 3.5, params.layer_height_mm * 8.0, 3.0),
        min_component_size=18,
    )

    for component_index, component_map in enumerate(component_maps, start=1):
        distance_mm = ndimage.distance_transform_edt(component_map.valid_mask) * component_map.step_mm
        max_distance = float(np.nanmax(distance_mm)) if np.any(component_map.valid_mask) else 0.0
        for idx in range(max(params.perimeters, 0)):
            offset = params.nozzle_diameter_mm * 0.5 + idx * params.line_spacing_mm
            if offset >= max_distance:
                break
            contours = measure.find_contours(distance_mm, level=offset)
            for loop_index, contour in enumerate(contours, start=1):
                if len(contour) < 10:
                    continue
                xy = contour_to_xy(component_map, contour)
                if core_profile is not None and not core_profile.is_empty and point_in_polygon(core_profile.center_xy, xy):
                    radial_distance = np.linalg.norm(xy - core_profile.center_xy[None, :], axis=1)
                    interface_radius_limit = float(np.max(core_profile.radii_mm)) + params.line_spacing_mm * 3.0
                    if float(np.percentile(radial_distance, 75.0)) <= interface_radius_limit:
                        continue
                xy = resample_polyline(xy, params.segment_length_mm, closed=True)
                segments = sample_surface_segments(component_map, xy, closed=True)
                for segment_index, (points, normals, is_closed) in enumerate(segments, start=1):
                    if len(points) < 4:
                        continue
                    name_suffix = f"-{segment_index}" if len(segments) > 1 else ""
                    paths.append(
                        Toolpath(
                            name=f"Conformal Perimeter C{component_index}-{idx + 1}-{loop_index}{name_suffix}",
                            kind="conformal-perimeter",
                            points=points,
                            normals=normals,
                            closed=is_closed,
                            phase="conformal",
                        )
                    )
    return paths


def generate_conformal_infill_paths(surface_map: SurfaceMap, params: SliceParameters) -> list[Toolpath]:
    if not np.any(surface_map.valid_mask):
        return []

    angle = math.radians(params.infill_angle_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    component_maps = split_surface_map_by_height(
        surface_map,
        z_jump_threshold_mm=max(surface_map.step_mm * 3.5, params.layer_height_mm * 8.0, 3.0),
        min_component_size=18,
    )

    paths: list[Toolpath] = []
    line_index = 0
    for component_index, component_map in enumerate(component_maps, start=1):
        yy, xx = np.nonzero(component_map.valid_mask)
        if len(xx) == 0:
            continue
        surface_points = np.column_stack([component_map.x_coords[xx], component_map.y_coords[yy]])
        u_coords = surface_points[:, 0] * cos_a + surface_points[:, 1] * sin_a
        v_coords = -surface_points[:, 0] * sin_a + surface_points[:, 1] * cos_a

        u_min, u_max = float(u_coords.min()), float(u_coords.max())
        v_min, v_max = float(v_coords.min()), float(v_coords.max())

        line_step = max(params.line_spacing_mm, component_map.step_mm)
        sample_step = max(params.segment_length_mm * 0.5, component_map.step_mm * 0.75)

        for v_value in np.arange(v_min, v_max + line_step, line_step):
            u_values = np.arange(u_min, u_max + sample_step, sample_step)
            x_values = u_values * cos_a - v_value * sin_a
            y_values = u_values * sin_a + v_value * cos_a
            inside = sample_valid(component_map, x_values, y_values)

            segments = _split_boolean_runs(inside)
            for segment in segments:
                if len(segment) < 3:
                    continue
                xy = np.column_stack([x_values[segment], y_values[segment]])
                if line_index % 2 == 1:
                    xy = xy[::-1]
                xy = resample_polyline(xy, params.segment_length_mm, closed=False)
                sampled_segments = sample_surface_segments(component_map, xy, closed=False)
                for points, normals, _ in sampled_segments:
                    if len(points) < 2:
                        continue
                    paths.append(
                        Toolpath(
                            name=f"Conformal Infill C{component_index}-{line_index + 1}",
                            kind="conformal-infill",
                            points=points,
                            normals=normals,
                            closed=False,
                            phase="conformal",
                        )
                    )
                    line_index += 1
    return paths


def split_surface_map_by_height(
    surface_map: SurfaceMap,
    z_jump_threshold_mm: float,
    min_component_size: int,
) -> list[SurfaceMap]:
    """Split the projected top surface into height-continuous patches."""

    if not np.any(surface_map.valid_mask):
        return []

    labels = np.zeros(surface_map.valid_mask.shape, dtype=np.int32)
    component_id = 0
    for row_index in range(surface_map.valid_mask.shape[0]):
        for col_index in range(surface_map.valid_mask.shape[1]):
            if not surface_map.valid_mask[row_index, col_index] or labels[row_index, col_index] != 0:
                continue
            component_id += 1
            stack = [(row_index, col_index)]
            labels[row_index, col_index] = component_id
            while stack:
                current_row, current_col = stack.pop()
                current_z = surface_map.z_map[current_row, current_col]
                for row_offset, col_offset in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    next_row = current_row + row_offset
                    next_col = current_col + col_offset
                    if next_row < 0 or next_col < 0 or next_row >= surface_map.valid_mask.shape[0] or next_col >= surface_map.valid_mask.shape[1]:
                        continue
                    if not surface_map.valid_mask[next_row, next_col] or labels[next_row, next_col] != 0:
                        continue
                    if abs(float(surface_map.z_map[next_row, next_col] - current_z)) > z_jump_threshold_mm:
                        continue
                    labels[next_row, next_col] = component_id
                    stack.append((next_row, next_col))

    component_maps: list[SurfaceMap] = []
    for component_index in range(1, component_id + 1):
        component_valid = labels == component_index
        if int(component_valid.sum()) < min_component_size:
            continue
        component_z_map = surface_map.z_map.copy()
        component_normal_map = surface_map.normal_map.copy()
        component_z_map[~component_valid] = np.nan
        component_normal_map[~component_valid] = np.array([0.0, 0.0, 1.0])
        component_maps.append(
            SurfaceMap(
                x_min=surface_map.x_min,
                y_min=surface_map.y_min,
                step_mm=surface_map.step_mm,
                x_coords=surface_map.x_coords.copy(),
                y_coords=surface_map.y_coords.copy(),
                z_map=component_z_map,
                normal_map=component_normal_map,
                valid_mask=component_valid,
            )
        )

    return component_maps if component_maps else [surface_map]


def contour_to_xy(surface_map: SurfaceMap, contour: np.ndarray) -> np.ndarray:
    rows = contour[:, 0]
    cols = contour[:, 1]
    x = surface_map.x_coords[0] + cols * surface_map.step_mm
    y = surface_map.y_coords[0] + rows * surface_map.step_mm
    return np.column_stack([x, y])


def sample_valid(surface_map: SurfaceMap, x_values: np.ndarray, y_values: np.ndarray) -> np.ndarray:
    rows = np.rint((y_values - surface_map.y_coords[0]) / surface_map.step_mm).astype(int)
    cols = np.rint((x_values - surface_map.x_coords[0]) / surface_map.step_mm).astype(int)
    inside = (
        (rows >= 0)
        & (rows < surface_map.valid_mask.shape[0])
        & (cols >= 0)
        & (cols < surface_map.valid_mask.shape[1])
    )
    result = np.zeros_like(rows, dtype=bool)
    result[inside] = surface_map.valid_mask[rows[inside], cols[inside]]
    return result


def sample_surface(surface_map: SurfaceMap, xy_points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Compatibility helper that returns the first contiguous valid segment."""

    segments = sample_surface_segments(surface_map, xy_points, closed=False)
    if not segments:
        return np.empty((0, 3), dtype=float), np.empty((0, 3), dtype=float)
    points, normals, _ = segments[0]
    return points, normals


def sample_surface_segments(
    surface_map: SurfaceMap,
    xy_points: np.ndarray,
    closed: bool,
) -> list[tuple[np.ndarray, np.ndarray, bool]]:
    xy_points = np.asarray(xy_points, dtype=float)
    if len(xy_points) == 0:
        return []

    if closed and np.linalg.norm(xy_points[0] - xy_points[-1]) > 1e-6:
        xy_points = np.vstack([xy_points, xy_points[0]])

    segments: list[tuple[np.ndarray, np.ndarray, bool]] = []
    current_points: list[np.ndarray] = []
    current_normals: list[np.ndarray] = []
    had_gap = False
    # A large 3D jump usually means the XY contour crossed onto another face patch.
    # We split there so the exporter can insert travel instead of false extrusion.
    jump_threshold_mm = max(surface_map.step_mm * 2.4, 2.0)

    for x_value, y_value in xy_points:
        point, normal = sample_surface_point(surface_map, float(x_value), float(y_value))
        if point is None:
            had_gap = True
            _flush_surface_segment(
                segments,
                current_points,
                current_normals,
                is_closed=False,
                jump_threshold_mm=jump_threshold_mm,
            )
            current_points = []
            current_normals = []
            continue
        current_points.append(point)
        current_normals.append(normal)

    _flush_surface_segment(
        segments,
        current_points,
        current_normals,
        is_closed=closed and not had_gap,
        jump_threshold_mm=jump_threshold_mm,
    )
    return segments


def _flush_surface_segment(
    segments: list[tuple[np.ndarray, np.ndarray, bool]],
    points: list[np.ndarray],
    normals: list[np.ndarray],
    is_closed: bool,
    jump_threshold_mm: float,
) -> None:
    if not points:
        return
    points_array = np.asarray(points, dtype=float)
    normals_array = _normalize(np.asarray(normals, dtype=float))
    if len(points_array) > 1:
        dedup_mask = np.ones(len(points_array), dtype=bool)
        deltas = np.linalg.norm(np.diff(points_array, axis=0), axis=1)
        dedup_mask[1:] = deltas > 1e-6
        points_array = points_array[dedup_mask]
        normals_array = normals_array[dedup_mask]
    if len(points_array) < 2:
        return

    deltas = np.diff(points_array, axis=0)
    segment_lengths = np.linalg.norm(deltas, axis=1)
    z_jumps = np.abs(deltas[:, 2])
    split_after = (segment_lengths > jump_threshold_mm) | (z_jumps > jump_threshold_mm)

    start_index = 0
    for split_index, should_split in enumerate(split_after):
        if not should_split:
            continue
        _append_surface_subsegment(
            segments,
            points_array[start_index : split_index + 1],
            normals_array[start_index : split_index + 1],
            False,
        )
        start_index = split_index + 1
    _append_surface_subsegment(
        segments,
        points_array[start_index:],
        normals_array[start_index:],
        is_closed and not np.any(split_after),
    )


def _append_surface_subsegment(
    segments: list[tuple[np.ndarray, np.ndarray, bool]],
    points_array: np.ndarray,
    normals_array: np.ndarray,
    is_closed: bool,
) -> None:
    if len(points_array) < 2:
        return
    segments.append((points_array, normals_array, is_closed))


def _nearest_valid_surface_sample(
    surface_map: SurfaceMap,
    fx: float,
    fy: float,
    x_value: float,
    y_value: float,
) -> tuple[np.ndarray, np.ndarray] | None:
    nearest_row = int(np.clip(round(fy), 0, surface_map.z_map.shape[0] - 1))
    nearest_col = int(np.clip(round(fx), 0, surface_map.z_map.shape[1] - 1))
    best: tuple[int, int] | None = None
    best_distance = math.inf
    for row_offset in range(-2, 3):
        for col_offset in range(-2, 3):
            row_index = nearest_row + row_offset
            col_index = nearest_col + col_offset
            if row_index < 0 or col_index < 0 or row_index >= surface_map.z_map.shape[0] or col_index >= surface_map.z_map.shape[1]:
                continue
            if not surface_map.valid_mask[row_index, col_index]:
                continue
            distance = (row_index - fy) ** 2 + (col_index - fx) ** 2
            if distance < best_distance:
                best_distance = distance
                best = (row_index, col_index)
    if best is None or best_distance > 2.5:
        return None
    row_index, col_index = best
    z_value = surface_map.z_map[row_index, col_index]
    normal = surface_map.normal_map[row_index, col_index]
    return np.array([x_value, y_value, z_value], dtype=float), normal


def sample_surface_point(surface_map: SurfaceMap, x_value: float, y_value: float) -> tuple[np.ndarray | None, np.ndarray]:
    fx = (x_value - surface_map.x_coords[0]) / surface_map.step_mm
    fy = (y_value - surface_map.y_coords[0]) / surface_map.step_mm
    col = int(math.floor(fx))
    row = int(math.floor(fy))

    if row < 0 or col < 0 or row >= surface_map.z_map.shape[0] - 1 or col >= surface_map.z_map.shape[1] - 1:
        fallback = _nearest_valid_surface_sample(surface_map, fx, fy, x_value, y_value)
        if fallback is not None:
            return fallback
        return None, np.array([0.0, 0.0, 1.0])

    tx = fx - col
    ty = fy - row
    corners = [
        (row, col, (1 - tx) * (1 - ty)),
        (row, col + 1, tx * (1 - ty)),
        (row + 1, col, (1 - tx) * ty),
        (row + 1, col + 1, tx * ty),
    ]

    z_acc = 0.0
    normal_acc = np.zeros(3, dtype=float)
    total_weight = 0.0
    for row_index, col_index, weight in corners:
        if not surface_map.valid_mask[row_index, col_index]:
            continue
        z_acc += surface_map.z_map[row_index, col_index] * weight
        normal_acc += surface_map.normal_map[row_index, col_index] * weight
        total_weight += weight

    if total_weight < 1e-6:
        fallback = _nearest_valid_surface_sample(surface_map, fx, fy, x_value, y_value)
        if fallback is not None:
            return fallback
        return None, np.array([0.0, 0.0, 1.0])

    z_value = z_acc / total_weight
    normal = normal_acc / total_weight
    normal = normal / max(np.linalg.norm(normal), 1e-9)
    return np.array([x_value, y_value, z_value], dtype=float), normal


def _barycentric_2d(projected_triangle: np.ndarray, xx: np.ndarray, yy: np.ndarray) -> np.ndarray:
    x0, y0 = projected_triangle[0]
    x1, y1 = projected_triangle[1]
    x2, y2 = projected_triangle[2]
    denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if math.isclose(denom, 0.0, abs_tol=1e-12):
        return np.full(xx.shape + (3,), -1.0, dtype=float)
    l1 = ((y1 - y2) * (xx - x2) + (x2 - x1) * (yy - y2)) / denom
    l2 = ((y2 - y0) * (xx - x2) + (x0 - x2) * (yy - y2)) / denom
    l3 = 1.0 - l1 - l2
    return np.stack([l1, l2, l3], axis=-1)


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    safe = np.where(norms < 1e-9, 1.0, norms)
    normalized = vectors / safe
    normalized[np.squeeze(norms, axis=-1) < 1e-9] = np.array([0.0, 0.0, 1.0])
    return normalized


def _split_boolean_runs(mask: np.ndarray) -> list[np.ndarray]:
    runs: list[np.ndarray] = []
    start = None
    for idx, value in enumerate(mask):
        if value and start is None:
            start = idx
        if not value and start is not None:
            runs.append(np.arange(start, idx))
            start = None
    if start is not None:
        runs.append(np.arange(start, len(mask)))
    return runs


