"""Planar three-axis slicing helpers for the rotary core phase.

The current project no longer assumes that the planar phase is simply “the low
Z part of the model”. Instead, it tries to recover the central rotary body that
Open5X-style workflows build first with fixed U/V axes, then prints that body
with ordinary XYZ layers before the five-axis blade / conformal phase starts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .core import MeshModel, SliceParameters, Toolpath
from .geometry import resample_polyline

_EDGE_PAIRS = ((0, 1), (1, 2), (2, 0))

# The planar phase prints the rotary core or chosen substrate first while U/V
# stay fixed.
# 平面阶段会在 U/V 固定的情况下先打回转核心或选中的基底。
# Its job is to build a stable three-axis body for the later five-axis phase.
# 它先做出一个稳定的三轴实体，后面的五轴路径再接着往上走。


@dataclass(slots=True)
class RotaryCoreProfile:
    """Axisymmetric core estimated around the printer's rotary axis.

    围绕打印机回转轴估出来的轴对称核心轮廓。

    It stores one radius per Z layer so the planar phase can build a printable
    cylindrical core before switching to conformal paths.
    它按 Z 层保存半径，平面阶段就能先长出一个可打印的近圆柱核心，再切到
    共形路径。
    """

    center_xy: np.ndarray
    z_levels_mm: np.ndarray
    radii_mm: np.ndarray

    @property
    def max_z_mm(self) -> float:
        active = self.radii_mm > 1e-6
        if not np.any(active):
            return 0.0
        return float(self.z_levels_mm[active][-1])

    @property
    def min_z_mm(self) -> float:
        active = self.radii_mm > 1e-6
        if not np.any(active):
            return 0.0
        return float(self.z_levels_mm[active][0])

    @property
    def is_empty(self) -> bool:
        return not np.any(self.radii_mm > 1e-6)

    def radius_at_z(self, z_mm: float) -> float:
        if self.is_empty:
            return 0.0
        return float(np.interp(z_mm, self.z_levels_mm, self.radii_mm, left=0.0, right=0.0))


class HorizontalSectionExtractor:
    """Extract XY contour loops from a mesh at a chosen Z height.

    在指定 Z 高度上从网格里提取 XY 截面轮廓。

    Core detection and planar slicing both rely on this repeated horizontal
    intersection step.
    核心识别和平面切片都会反复用到这一步水平求交。
    """

    def __init__(self, mesh: MeshModel, tolerance_mm: float = 1e-4) -> None:
        self.triangles = mesh.face_vertices
        self.triangle_vertex_normals = mesh.vertex_normals[mesh.faces]
        self.tolerance_mm = tolerance_mm
        self.z_values = self.triangles[:, :, 2]
        self.z_min = self.z_values.min(axis=1)
        self.z_max = self.z_values.max(axis=1)

    def loops(self, z_mm: float) -> list[np.ndarray]:
        segments = [segment for segment, _ in self.segments_with_normals(z_mm)]
        return _stitch_segments_to_loops(segments, max(self.tolerance_mm, 1e-3))

    def segments_with_normals(self, z_mm: float) -> list[tuple[np.ndarray, np.ndarray]]:
        tol = self.tolerance_mm
        active = (self.z_min <= z_mm + tol) & (self.z_max >= z_mm - tol)
        segments: list[tuple[np.ndarray, np.ndarray]] = []

        for tri, tri_normals in zip(self.triangles[active], self.triangle_vertex_normals[active]):
            points, normals = _triangle_plane_intersections(tri, tri_normals, z_mm, tol)
            if len(points) < 2:
                continue
            if len(points) > 2:
                point_a, point_b, index_a, index_b = _farthest_pair_with_indices(points)
                points = [point_a, point_b]
                normals = [normals[index_a], normals[index_b]]
            segments.append((np.asarray(points[:2], dtype=float), _normalize_rows(np.asarray(normals[:2], dtype=float))))
        return segments


def estimate_rotary_core_profile(mesh: MeshModel, params: SliceParameters) -> RotaryCoreProfile:
    """Estimate the central rotary body that should be printed first.

    估计出那根应该先在 U/V 固定状态下打印的中心回转实体。

    The profile is described by one XY centre and one radius per planar layer.
    The radius comes from the largest radial region that stays inside the
    model.
    这个轮廓由一个 XY 中心和每层一个半径组成。半径取自围绕中心、又始终
    落在模型内部的最大径向区域。
    """

    layer_height = max(params.resolved_planar_layer_height_mm(), 1e-3)
    z_levels = np.arange(mesh.bounds_min[2] + layer_height, mesh.bounds_max[2] + layer_height * 0.5, layer_height)
    if len(z_levels) == 0:
        z_levels = np.array([mesh.bounds_min[2] + layer_height], dtype=float)

    extractor = HorizontalSectionExtractor(mesh)
    # Keep every horizontal slice so the later centre/radius estimate can ask
    # which XY location stays inside the model most reliably.
    # 把所有水平截面都留下来，后面的中心和半径估计才好回答一个简单问题。
    # 哪个 XY 位置在各层里最稳定地待在实体内部？
    loops_by_z: list[list[np.ndarray]] = []
    for z_mm in z_levels:
        loops = extractor.loops(float(z_mm))
        loops = [loop for loop in loops if abs(polygon_area(loop)) >= max(params.nozzle_diameter_mm**2 * 0.25, 0.05)]
        loops_by_z.append(loops)

    center_xy = estimate_rotary_core_center(mesh, loops_by_z, params)
    radius_percentile = 10.0 + float(np.clip(params.core_transition_percentile, 0.0, 25.0))
    radii = np.array(
        [
            _estimate_slice_core_radius(center_xy, loops, params.nozzle_diameter_mm, radius_percentile)
            for loops in loops_by_z
        ],
        dtype=float,
    )
    # Smooth slice-to-slice noise so the recovered core prints more like a real
    # rotary body.
    # 把层与层之间的小噪声抹平一点，恢复出来的核心才更像能直接打印的回转体。
    radii = _smooth_positive_radii(radii)
    radii = _keep_primary_core_run(radii, min_radius_mm=max(params.nozzle_diameter_mm * 1.15, 0.6))

    if not params.auto_core_transition and params.core_transition_height_mm > 0.0:
        radii[z_levels > params.core_transition_height_mm] = 0.0

    return RotaryCoreProfile(center_xy=np.asarray(center_xy, dtype=float), z_levels_mm=z_levels, radii_mm=radii)


def estimate_rotary_core_center(mesh: MeshModel, loops_by_z: list[list[np.ndarray]], params: SliceParameters) -> np.ndarray:
    """Find the XY point that stays inside the solid most consistently.

    在所有水平截面里找出那个最稳定落在实体内部的 XY 点。
    """

    bbox_center = mesh.bounds_center[:2]
    focus_half_size = np.maximum(mesh.size[:2] * 0.35, 6.0)
    sample_step = max(params.resolved_planar_line_spacing_mm() * 2.0, params.nozzle_diameter_mm * 2.0, 1.5)

    xs = np.arange(bbox_center[0] - focus_half_size[0], bbox_center[0] + focus_half_size[0] + sample_step, sample_step)
    ys = np.arange(bbox_center[1] - focus_half_size[1], bbox_center[1] + focus_half_size[1] + sample_step, sample_step)
    if len(xs) == 0 or len(ys) == 0:
        return bbox_center.copy()

    occupancy = np.zeros((len(ys), len(xs)), dtype=int)
    for loops in loops_by_z:
        if not loops:
            continue
        occupancy += _loops_occupancy_mask(xs, ys, loops)

    max_hits = int(occupancy.max())
    if max_hits <= 0:
        return bbox_center.copy()

    high_mask = occupancy >= max(1, int(math.ceil(max_hits * 0.8)))
    coords = np.column_stack(np.nonzero(high_mask))
    if len(coords) == 0:
        row_index, col_index = np.unravel_index(int(np.argmax(occupancy)), occupancy.shape)
        return np.array([xs[col_index], ys[row_index]], dtype=float)

    # Average the best occupied cells. A single lucky grid hit is too noisy to
    # trust on its own.
    # 不去赌某一个碰巧最优的网格点，而是把最好那一片区域取平均，结果会稳一些。
    sampled_points = np.column_stack([xs[coords[:, 1]], ys[coords[:, 0]]])
    return sampled_points.mean(axis=0)


def slice_planar_core(
    mesh: MeshModel,
    core_profile: RotaryCoreProfile,
    params: SliceParameters,
) -> tuple[list[Toolpath], dict[str, float | int], list[str]]:
    """Slice the recovered rotary core with ordinary horizontal layers.

    使用普通水平分层方式切出识别得到的回转核心。
    """

    warnings: list[str] = []
    toolpaths: list[Toolpath] = []
    if core_profile.is_empty:
        return [], {"layer_count": 0, "path_count": 0, "transition_height_mm": 0.0}, warnings

    emitted_layers = 0
    for layer_index, (z_mm, radius_mm) in enumerate(zip(core_profile.z_levels_mm, core_profile.radii_mm), start=1):
        if radius_mm < max(params.nozzle_diameter_mm * 0.85, 0.4):
            continue

        perimeter_loops = build_rotary_core_perimeter_loops(core_profile.center_xy, float(radius_mm), params)
        if not perimeter_loops:
            continue

        emitted_layers += 1
        toolpaths.extend(generate_planar_perimeter_paths(perimeter_loops, float(z_mm), layer_index, params))
        if params.planar_include_infill:
            outer_loop = build_circle_loop(core_profile.center_xy, float(radius_mm), params.segment_length_mm)
            toolpaths.extend(generate_planar_infill_paths([outer_loop], float(z_mm), layer_index, params))

    metadata = {
        "layer_count": emitted_layers,
        "path_count": len(toolpaths),
        "transition_height_mm": float(core_profile.max_z_mm),
        "core_center_x_mm": float(core_profile.center_xy[0]),
        "core_center_y_mm": float(core_profile.center_xy[1]),
        "core_max_radius_mm": float(np.max(core_profile.radii_mm)) if len(core_profile.radii_mm) else 0.0,
    }
    return toolpaths, metadata, warnings


def slice_planar_mesh(
    mesh: MeshModel,
    params: SliceParameters,
) -> tuple[list[Toolpath], dict[str, float | int], list[str]]:
    """Slice a selected substrate mesh directly from its true section contours.

    直接依据真实截面轮廓对选中的基底网格进行平面切片。
    """

    warnings: list[str] = []
    toolpaths: list[Toolpath] = []
    layer_height = max(params.resolved_planar_layer_height_mm(), 1e-3)
    z_levels = np.arange(mesh.bounds_min[2] + layer_height, mesh.bounds_max[2] + layer_height * 0.5, layer_height)
    if len(z_levels) == 0:
        z_levels = np.array([mesh.bounds_min[2] + layer_height], dtype=float)

    extractor = HorizontalSectionExtractor(mesh)
    emitted_layers = 0
    last_z_mm = 0.0
    for layer_index, z_mm in enumerate(z_levels, start=1):
        loops = extractor.loops(float(z_mm))
        loops = [loop for loop in loops if abs(polygon_area(loop)) >= max(params.nozzle_diameter_mm**2 * 0.25, 0.05)]
        if not loops:
            continue

        emitted_layers += 1
        last_z_mm = float(z_mm)
        toolpaths.extend(generate_planar_perimeter_paths(loops, float(z_mm), layer_index, params))
        if params.planar_include_infill:
            toolpaths.extend(generate_planar_infill_paths(loops, float(z_mm), layer_index, params))

    metadata = {
        "layer_count": emitted_layers,
        "path_count": len(toolpaths),
        "transition_height_mm": last_z_mm,
        "core_center_x_mm": float(mesh.bounds_center[0]),
        "core_center_y_mm": float(mesh.bounds_center[1]),
        "core_max_radius_mm": float(np.max(np.linalg.norm(mesh.vertices[:, :2] - mesh.bounds_center[:2], axis=1))) if len(mesh.vertices) else 0.0,
    }
    return toolpaths, metadata, warnings


def build_rotary_core_perimeter_loops(center_xy: np.ndarray, radius_mm: float, params: SliceParameters) -> list[np.ndarray]:
    """Generate concentric perimeter loops for one planar core layer.

    为单层回转核心生成同心外轮廓环。
    """

    loops: list[np.ndarray] = []
    line_spacing = params.resolved_planar_line_spacing_mm()
    perimeter_count = max(params.planar_perimeters, 1)
    for perimeter_index in range(perimeter_count):
        perimeter_radius = radius_mm - perimeter_index * line_spacing
        if perimeter_radius < max(params.nozzle_diameter_mm * 0.6, 0.25):
            break
        loops.append(build_circle_loop(center_xy, perimeter_radius, params.segment_length_mm))
    return loops


def build_circle_loop(center_xy: np.ndarray, radius_mm: float, segment_length_mm: float) -> np.ndarray:
    """Approximate a circle with a polyline at the requested segment length.

    按给定离散段长用折线近似一个圆。
    """

    circumference = max(2.0 * math.pi * radius_mm, segment_length_mm * 6.0)
    point_count = max(int(math.ceil(circumference / max(segment_length_mm, 1e-3))), 24)
    angles = np.linspace(0.0, 2.0 * math.pi, point_count, endpoint=False)
    return np.column_stack(
        [
            center_xy[0] + radius_mm * np.cos(angles),
            center_xy[1] + radius_mm * np.sin(angles),
        ]
    )


def generate_planar_perimeter_paths(
    loops: list[np.ndarray],
    z_mm: float,
    layer_index: int,
    params: SliceParameters,
) -> list[Toolpath]:
    """Turn planar contour loops into perimeter toolpaths.

    把平面轮廓环转换为外轮廓路径。
    """

    paths: list[Toolpath] = []
    for loop_index, loop in enumerate(sorted(loops, key=lambda item: -abs(polygon_area(item))), start=1):
        sampled_xy = resample_polyline(loop, params.segment_length_mm, closed=True)
        points = np.column_stack([sampled_xy, np.full(len(sampled_xy), z_mm)])
        normals = np.tile(np.array([[0.0, 0.0, 1.0]]), (len(points), 1))
        paths.append(
            Toolpath(
                name=f"Core Layer {layer_index} Perimeter {loop_index}",
                kind="planar-perimeter",
                points=points,
                normals=normals,
                closed=True,
                phase="planar",
                layer_index=layer_index,
                z_height_mm=z_mm,
            )
        )
    return paths


def generate_planar_infill_paths(
    loops: list[np.ndarray],
    z_mm: float,
    layer_index: int,
    params: SliceParameters,
) -> list[Toolpath]:
    """Generate simple scanline infill inside planar loops.

    在平面轮廓内部生成简单的扫描线填充路径。
    """

    line_spacing = params.resolved_planar_line_spacing_mm()
    if line_spacing <= 1e-6:
        return []

    angle = math.radians(params.planar_infill_angle_deg)
    uv_loops = [rotate_xy(loop, angle) for loop in loops]
    u_min = min(float(loop[:, 0].min()) for loop in uv_loops)
    u_max = max(float(loop[:, 0].max()) for loop in uv_loops)
    v_min = min(float(loop[:, 1].min()) for loop in uv_loops)
    v_max = max(float(loop[:, 1].max()) for loop in uv_loops)
    sample_step = max(params.segment_length_mm, line_spacing * 0.75)

    line_counter = 0
    paths: list[Toolpath] = []
    for v_value in np.arange(v_min, v_max + line_spacing * 0.5, line_spacing):
        u_segments = scanline_segments(uv_loops, float(v_value), tolerance=max(sample_step * 0.2, 1e-6))
        for u_start, u_end in u_segments:
            if u_end - u_start < line_spacing * 0.25:
                continue
            u_values = np.arange(u_start, u_end + sample_step * 0.5, sample_step)
            if len(u_values) < 2:
                u_values = np.array([u_start, u_end], dtype=float)
            if (layer_index + line_counter) % 2 == 1:
                u_values = u_values[::-1]
            uv_points = np.column_stack([u_values, np.full(len(u_values), v_value)])
            xy_points = inverse_rotate_xy(uv_points, angle)
            xy_points = resample_polyline(xy_points, params.segment_length_mm, closed=False)
            points = np.column_stack([xy_points, np.full(len(xy_points), z_mm)])
            normals = np.tile(np.array([[0.0, 0.0, 1.0]]), (len(points), 1))
            paths.append(
                Toolpath(
                    name=f"Core Layer {layer_index} Infill {line_counter + 1}",
                    kind="planar-infill",
                    points=points,
                    normals=normals,
                    closed=False,
                    phase="planar",
                    layer_index=layer_index,
                    z_height_mm=z_mm,
                )
            )
            line_counter += 1
    return paths


def scanline_segments(uv_loops: list[np.ndarray], v_value: float, tolerance: float = 1e-6) -> list[tuple[float, float]]:
    """Intersect rotated loops with one horizontal scanline in UV space.

    在 UV 空间里求旋转后轮廓与一条水平扫描线的交段。
    """

    intersections: list[float] = []
    for loop in uv_loops:
        start = loop
        end = np.roll(loop, -1, axis=0)
        y0 = start[:, 1]
        y1 = end[:, 1]
        crosses = ((y0 <= v_value) & (y1 > v_value)) | ((y1 <= v_value) & (y0 > v_value))
        if not np.any(crosses):
            continue
        u_values = start[crosses, 0] + (v_value - y0[crosses]) * (end[crosses, 0] - start[crosses, 0]) / (y1[crosses] - y0[crosses])
        intersections.extend(float(value) for value in u_values)

    if len(intersections) < 2:
        return []

    intersections.sort()
    merged: list[float] = []
    for value in intersections:
        if not merged or abs(value - merged[-1]) > tolerance:
            merged.append(value)

    segments = []
    for idx in range(0, len(merged) - 1, 2):
        segments.append((merged[idx], merged[idx + 1]))
    return segments


def rotate_xy(points: np.ndarray, angle_rad: float) -> np.ndarray:
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    x = points[:, 0] * cos_a + points[:, 1] * sin_a
    y = -points[:, 0] * sin_a + points[:, 1] * cos_a
    return np.column_stack([x, y])


def inverse_rotate_xy(points: np.ndarray, angle_rad: float) -> np.ndarray:
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    x = points[:, 0] * cos_a - points[:, 1] * sin_a
    y = points[:, 0] * sin_a + points[:, 1] * cos_a
    return np.column_stack([x, y])


def polygon_area(points: np.ndarray) -> float:
    if len(points) < 3:
        return 0.0
    shifted = np.roll(points, -1, axis=0)
    return 0.5 * float(np.sum(points[:, 0] * shifted[:, 1] - shifted[:, 0] * points[:, 1]))


def point_in_loops(point: np.ndarray, loops: list[np.ndarray]) -> bool:
    inside = False
    for loop in loops:
        if point_in_polygon(point, loop):
            inside = not inside
    return inside


def point_in_polygon(point: np.ndarray, polygon: np.ndarray) -> bool:
    x_value = float(point[0])
    y_value = float(point[1])
    inside = False
    prev_index = len(polygon) - 1
    for index in range(len(polygon)):
        x0, y0 = polygon[index]
        x1, y1 = polygon[prev_index]
        if (y0 > y_value) != (y1 > y_value):
            denom = y1 - y0
            if abs(denom) < 1e-12:
                denom = 1e-12
            x_cross = (x1 - x0) * (y_value - y0) / denom + x0
            if x_value < x_cross:
                inside = not inside
        prev_index = index
    return inside


def _loops_occupancy_mask(x_coords: np.ndarray, y_coords: np.ndarray, loops: list[np.ndarray]) -> np.ndarray:
    mask = np.zeros((len(y_coords), len(x_coords)), dtype=bool)
    for loop in loops:
        if len(loop) < 3:
            continue

        x_min = float(np.min(loop[:, 0]))
        x_max = float(np.max(loop[:, 0]))
        y_min = float(np.min(loop[:, 1]))
        y_max = float(np.max(loop[:, 1]))
        col_mask = (x_coords >= x_min) & (x_coords <= x_max)
        row_mask = (y_coords >= y_min) & (y_coords <= y_max)
        if not np.any(col_mask) or not np.any(row_mask):
            continue

        local_mask = _polygon_mask(x_coords[col_mask], y_coords[row_mask], loop)
        mask[np.ix_(row_mask, col_mask)] ^= local_mask
    return mask


def _polygon_mask(x_coords: np.ndarray, y_coords: np.ndarray, polygon: np.ndarray) -> np.ndarray:
    if len(polygon) < 3:
        return np.zeros((len(y_coords), len(x_coords)), dtype=bool)

    xx, yy = np.meshgrid(x_coords, y_coords)
    start = polygon
    end = np.roll(polygon, -1, axis=0)

    x0 = start[:, 0][None, None, :]
    y0 = start[:, 1][None, None, :]
    x1 = end[:, 0][None, None, :]
    y1 = end[:, 1][None, None, :]

    yy_expanded = yy[:, :, None]
    xx_expanded = xx[:, :, None]
    crosses = (y0 > yy_expanded) != (y1 > yy_expanded)
    denom = np.where(np.abs(y1 - y0) < 1e-12, 1e-12, y1 - y0)
    x_cross = (x1 - x0) * (yy_expanded - y0) / denom + x0
    hits = crosses & (xx_expanded < x_cross)
    return (np.count_nonzero(hits, axis=2) % 2) == 1


def _estimate_slice_core_radius(
    center_xy: np.ndarray,
    loops: list[np.ndarray],
    nozzle_diameter_mm: float,
    radius_percentile: float,
) -> float:
    if not loops or not point_in_loops(center_xy, loops):
        return 0.0

    angles = np.linspace(0.0, 2.0 * math.pi, 96, endpoint=False)
    radii: list[float] = []
    for angle in angles:
        direction = np.array([math.cos(angle), math.sin(angle)], dtype=float)
        hit_radius = _first_boundary_radius(center_xy, direction, loops)
        if hit_radius is not None:
            radii.append(hit_radius)

    if len(radii) < 24:
        return 0.0

    percentile_value = float(np.percentile(radii, radius_percentile)) - nozzle_diameter_mm * 0.5
    return max(percentile_value, 0.0)


def _first_boundary_radius(center_xy: np.ndarray, direction: np.ndarray, loops: list[np.ndarray]) -> float | None:
    hits: list[float] = []
    for loop in loops:
        start = loop
        end = np.roll(loop, -1, axis=0)
        for point_a, point_b in zip(start, end):
            hit_radius = _ray_segment_intersection_radius(center_xy, direction, point_a, point_b)
            if hit_radius is not None and hit_radius > 1e-4:
                hits.append(hit_radius)
    if not hits:
        return None
    return min(hits)


def _ray_segment_intersection_radius(
    center_xy: np.ndarray,
    direction: np.ndarray,
    point_a: np.ndarray,
    point_b: np.ndarray,
) -> float | None:
    segment_vector = point_b - point_a
    denom = direction[0] * segment_vector[1] - direction[1] * segment_vector[0]
    if abs(denom) < 1e-9:
        return None

    delta = point_a - center_xy
    ray_t = (delta[0] * segment_vector[1] - delta[1] * segment_vector[0]) / denom
    segment_u = (delta[0] * direction[1] - delta[1] * direction[0]) / denom
    if ray_t >= 0.0 and -1e-6 <= segment_u <= 1.0 + 1e-6:
        return float(ray_t)
    return None


def _smooth_positive_radii(radii_mm: np.ndarray) -> np.ndarray:
    if len(radii_mm) < 3:
        return radii_mm.copy()
    kernel = np.array([1.0, 2.0, 1.0], dtype=float)
    smoothed = radii_mm.copy()
    for index in range(len(radii_mm)):
        left = max(0, index - 1)
        right = min(len(radii_mm), index + 2)
        window = radii_mm[left:right]
        weights = kernel[1 - (index - left) : 1 + (right - index)]
        positive = window > 1e-6
        if not np.any(positive):
            smoothed[index] = 0.0
            continue
        smoothed[index] = float(np.sum(window[positive] * weights[positive]) / np.sum(weights[positive]))
    return smoothed


def _keep_primary_core_run(radii_mm: np.ndarray, min_radius_mm: float) -> np.ndarray:
    active = radii_mm >= min_radius_mm
    if not np.any(active):
        return np.zeros_like(radii_mm)

    best_slice = slice(0, 0)
    best_score = -1.0
    start = None
    for index, is_active in enumerate(active):
        if is_active and start is None:
            start = index
        if start is not None and ((not is_active) or index == len(active) - 1):
            end = index if not is_active else index + 1
            score = float(radii_mm[start:end].sum())
            if score > best_score:
                best_score = score
                best_slice = slice(start, end)
            start = None

    kept = np.zeros_like(radii_mm)
    if best_score <= 0.0:
        return kept

    start_index = best_slice.start or 0
    end_index = best_slice.stop or len(radii_mm)
    while start_index > 0 and radii_mm[start_index - 1] >= min_radius_mm * 0.3:
        start_index -= 1
    while end_index < len(radii_mm) and radii_mm[end_index] >= min_radius_mm * 0.3:
        end_index += 1
    kept[start_index:end_index] = radii_mm[start_index:end_index]
    return kept


def _stitch_segments_to_loops(segments: list[np.ndarray], tolerance: float) -> list[np.ndarray]:
    if not segments:
        return []

    quant = 1.0 / max(tolerance, 1e-6)
    adjacency: dict[tuple[int, int], list[tuple[tuple[int, int], int]]] = {}
    points: dict[tuple[int, int], np.ndarray] = {}
    segment_keys: list[tuple[tuple[int, int], tuple[int, int]]] = []

    for segment_index, segment in enumerate(segments):
        keys = []
        for point in segment:
            key = tuple(np.round(point * quant).astype(int))
            keys.append(key)
            points.setdefault(key, np.asarray(point, dtype=float))
        if keys[0] == keys[1]:
            continue
        a_key, b_key = keys[0], keys[1]
        adjacency.setdefault(a_key, []).append((b_key, segment_index))
        adjacency.setdefault(b_key, []).append((a_key, segment_index))
        segment_keys.append((a_key, b_key))

    visited_segments: set[int] = set()
    loops: list[np.ndarray] = []
    for segment_index, key_pair in enumerate(segment_keys):
        if segment_index in visited_segments:
            continue
        start_key, next_key = key_pair
        current_key = start_key
        previous_key: tuple[int, int] | None = None
        ordered_keys = [start_key]

        while True:
            ordered_keys.append(next_key)
            visited_segments.add(segment_index)
            previous_key, current_key = current_key, next_key
            if current_key == start_key:
                break

            candidates = adjacency.get(current_key, [])
            next_candidate = None
            for candidate_key, candidate_segment_index in candidates:
                if candidate_segment_index in visited_segments:
                    continue
                if candidate_key != previous_key or len(candidates) == 1:
                    next_candidate = (candidate_key, candidate_segment_index)
                    break
            if next_candidate is None:
                break
            next_key, segment_index = next_candidate

        coords = np.asarray([points[key] for key in ordered_keys], dtype=float)
        if len(coords) >= 3 and np.linalg.norm(coords[0] - coords[-1]) < tolerance * 2.0:
            coords = coords[:-1]
        coords = _deduplicate_path(coords, tolerance)
        if len(coords) >= 3:
            loops.append(coords)

    return loops


def _deduplicate_points(points: list[np.ndarray], tolerance: float) -> list[np.ndarray]:
    unique: list[np.ndarray] = []
    for point in points:
        point_arr = np.asarray(point, dtype=float)
        if not any(np.linalg.norm(point_arr - existing) <= tolerance for existing in unique):
            unique.append(point_arr)
    return unique


def _deduplicate_points_with_normals(
    points: list[np.ndarray],
    normals: list[np.ndarray],
    tolerance: float,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    unique_points: list[np.ndarray] = []
    unique_normals: list[np.ndarray] = []
    for point, normal in zip(points, normals):
        point_arr = np.asarray(point, dtype=float)
        normal_arr = np.asarray(normal, dtype=float)
        merged_index = None
        for index, existing in enumerate(unique_points):
            if np.linalg.norm(point_arr - existing) <= tolerance:
                merged_index = index
                break
        if merged_index is None:
            unique_points.append(point_arr)
            unique_normals.append(normal_arr)
        else:
            unique_normals[merged_index] = _normalize_rows(np.asarray([unique_normals[merged_index] + normal_arr], dtype=float))[0]
    return unique_points, unique_normals


def _farthest_pair(points: list[np.ndarray]) -> list[np.ndarray]:
    best_pair = [points[0], points[1]]
    best_distance = -1.0
    for idx, point_a in enumerate(points):
        for point_b in points[idx + 1 :]:
            distance = float(np.linalg.norm(point_a - point_b))
            if distance > best_distance:
                best_distance = distance
                best_pair = [point_a, point_b]
    return best_pair


def _farthest_pair_with_indices(points: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray, int, int]:
    best_pair = (points[0], points[1], 0, 1)
    best_distance = -1.0
    for idx, point_a in enumerate(points):
        for next_index, point_b in enumerate(points[idx + 1 :], start=idx + 1):
            distance = float(np.linalg.norm(point_a - point_b))
            if distance > best_distance:
                best_distance = distance
                best_pair = (point_a, point_b, idx, next_index)
    return best_pair


def _deduplicate_path(points: np.ndarray, tolerance: float) -> np.ndarray:
    if len(points) < 2:
        return points
    deduped = [points[0]]
    for point in points[1:]:
        if np.linalg.norm(point - deduped[-1]) > tolerance:
            deduped.append(point)
    return np.asarray(deduped, dtype=float)


def _triangle_plane_intersections(
    triangle: np.ndarray,
    triangle_normals: np.ndarray,
    z_mm: float,
    tolerance_mm: float,
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    points: list[np.ndarray] = []
    normals: list[np.ndarray] = []
    for a_idx, b_idx in _EDGE_PAIRS:
        point_a = triangle[a_idx]
        point_b = triangle[b_idx]
        normal_a = triangle_normals[a_idx]
        normal_b = triangle_normals[b_idx]
        delta_a = point_a[2] - z_mm
        delta_b = point_b[2] - z_mm
        if abs(delta_a) <= tolerance_mm and abs(delta_b) <= tolerance_mm:
            continue
        if delta_a * delta_b > tolerance_mm * tolerance_mm:
            continue
        if abs(delta_a) <= tolerance_mm:
            points.append(point_a[:2].copy())
            normals.append(normal_a.copy())
            continue
        if abs(delta_b) <= tolerance_mm:
            points.append(point_b[:2].copy())
            normals.append(normal_b.copy())
            continue
        if abs(point_b[2] - point_a[2]) <= tolerance_mm:
            continue
        ratio = (z_mm - point_a[2]) / (point_b[2] - point_a[2])
        if -tolerance_mm <= ratio <= 1.0 + tolerance_mm:
            points.append((point_a + ratio * (point_b - point_a))[:2])
            normals.append(normal_a * (1.0 - ratio) + normal_b * ratio)
    return _deduplicate_points_with_normals(points, normals, tolerance_mm)


def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    safe_norms = np.where(norms < 1e-9, 1.0, norms)
    normalized = vectors / safe_norms
    normalized[norms[:, 0] < 1e-9] = np.array([0.0, 0.0, 1.0])
    return normalized
