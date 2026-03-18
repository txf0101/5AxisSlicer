"""Hybrid slicing pipeline.

The slicer follows the Open5X-style intent more closely:
1. detect the central rotary body and print it first with fixed U/V,
2. remove that body from the conformal surface map,
3. generate five-axis paths for the surrounding blades / shell.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
from scipy import ndimage
from skimage import measure

from .core import MeshModel, SliceParameters, SliceResult, SliceSelection, SurfaceMap, Toolpath
from .geometry import combine_meshes, extract_submesh, resample_polyline, split_mesh_into_components
from .planar import (
    HorizontalSectionExtractor,
    RotaryCoreProfile,
    estimate_rotary_core_profile,
    point_in_polygon,
    slice_planar_core,
    slice_planar_mesh,
)

# This file is the conductor. It decides what belongs to the planar phase and
# what belongs to the conformal phase, then hands the actual geometry work to
# the helper modules.
# 这里管的是总流程。先判断哪些几何进平面阶段，哪些进共形阶段，再把具体
# 几何计算分给下面的辅助模块。


class ConformalSlicer:
    """Main entry point for the hybrid slicing pipeline.

    混合切片流程的主入口。

    Automatic core detection, component selection, and face-painted selection
    all meet here.
    自动核心识别、组件选择和面片刷选最后都会收口到这里。
    """

    def slice(self, mesh: MeshModel, params: SliceParameters, selection: SliceSelection | None = None) -> SliceResult:
        """Slice a mesh into planar and conformal toolpaths.

        将网格切分为平面阶段和共形阶段路径。

        It first settles the phase split, then generates the matching paths
        and metadata.
        先把阶段划分定下来，再生成对应的路径和元数据。
        """

        working_mesh = mesh.centered_for_build() if params.auto_center_model else mesh
        warnings: list[str] = []
        toolpaths: list[Toolpath] = []
        components = split_mesh_into_components(working_mesh)
        component_mode = len(components) > 1
        face_selection_active = selection is not None and (bool(selection.substrate_face_indices) or bool(selection.conformal_face_indices))
        selected_substrate_faces = np.empty(0, dtype=np.int32)
        selected_conformal_faces = np.empty(0, dtype=np.int32)
        substrate_index: int | None = None
        conformal_indices: tuple[int, ...] = ()
        substrate_mesh: MeshModel | None = None
        conformal_mesh: MeshModel | None = None

        # Phase splitting comes first. Explicit face picks win over component
        # heuristics, and component heuristics win over full automatic
        # detection.
        # 阶段划分是第一步。显式的面片选择优先级最高，其次是组件选择，最后
        # 才是全自动检测。
        if face_selection_active and selection is not None:
            face_count = len(working_mesh.faces)
            substrate_set = {int(index) for index in selection.substrate_face_indices if 0 <= int(index) < face_count}
            conformal_set = {int(index) for index in selection.conformal_face_indices if 0 <= int(index) < face_count}
            conformal_set.difference_update(substrate_set)
            selected_substrate_faces = np.asarray(sorted(substrate_set), dtype=np.int32)
            selected_conformal_faces = np.asarray(sorted(conformal_set), dtype=np.int32)
            if len(selected_substrate_faces):
                substrate_mesh = extract_submesh(
                    working_mesh,
                    selected_substrate_faces,
                    name=f"{working_mesh.name} [Selected Substrate Faces]",
                )
            if len(selected_conformal_faces):
                conformal_mesh = extract_submesh(
                    working_mesh,
                    selected_conformal_faces,
                    name=f"{working_mesh.name} [Selected Conformal Faces]",
                )
        else:
            substrate_index, conformal_indices = _resolve_component_selection(working_mesh, components, selection)
            substrate_mesh = components[substrate_index] if component_mode and substrate_index is not None else None
            conformal_mesh = (
                combine_meshes([components[index] for index in conformal_indices], name=f"{working_mesh.name} [Conformal Selection]")
                if component_mode and conformal_indices
                else None
            )

        explicit_selection_mode = face_selection_active or component_mode
        use_open5x_surface_finish = explicit_selection_mode and conformal_mesh is not None

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

        # The planar/base phase depends on how the user split the model: picked
        # faces, picked components, or a fully automatic rotary core.
        # 平面和基底阶段怎么走，取决于模型是按面片拆、按组件拆，还是完全
        # 自动恢复回转核心。
        if face_selection_active:
            if params.enable_planar_core and substrate_mesh is not None:
                planar_toolpaths, planar_meta, planar_warnings = slice_planar_mesh(substrate_mesh, params)
                toolpaths.extend(planar_toolpaths)
                warnings.extend(planar_warnings)
            elif params.enable_planar_core:
                warnings.append("No substrate faces were selected, so the planar base phase was skipped.")
        elif component_mode:
            if params.enable_planar_core and substrate_mesh is not None:
                planar_toolpaths, planar_meta, planar_warnings = slice_planar_mesh(substrate_mesh, params)
                toolpaths.extend(planar_toolpaths)
                warnings.extend(planar_warnings)
            elif params.enable_planar_core:
                warnings.append("No substrate geometry was selected, so the planar base phase was skipped.")
        else:
            if params.enable_planar_core:
                core_profile = estimate_rotary_core_profile(working_mesh, params)
            if params.enable_planar_core and not core_profile.is_empty:
                planar_toolpaths, planar_meta, planar_warnings = slice_planar_core(working_mesh, core_profile, params)
                toolpaths.extend(planar_toolpaths)
                warnings.extend(planar_warnings)
            elif params.enable_planar_core:
                warnings.append("No stable rotary core was detected near the model centre, so the planar core phase was skipped.")

        conformal_meta: dict[str, float | int | str] = {
            "layer_count": 0,
            "strategy": "top-surface",
        }
        conformal_perimeters: list[Toolpath] = []
        conformal_infill: list[Toolpath] = []
        # Once the planar phase is settled, pick the conformal strategy that
        # matches the current selection mode.
        # 平面阶段定下来以后，再按当前选择模式去决定共形阶段走哪条策略。
        if use_open5x_surface_finish:
            reference_center_xy = substrate_mesh.bounds_center[:2] if substrate_mesh is not None else working_mesh.bounds_center[:2]
            radius_source_mesh = substrate_mesh if substrate_mesh is not None else conformal_mesh
            reference_radius_mm = (
                _cylindrical_reference_radius(radius_source_mesh, reference_center_xy, params)
                if radius_source_mesh is not None
                else None
            )
            conformal_surface_map, conformal_perimeters, conformal_meta = generate_open5x_surface_finish_paths(
                conformal_mesh,
                reference_center_xy,
                params,
                reference_radius_mm=reference_radius_mm,
            )
            full_surface_map = conformal_surface_map
        elif face_selection_active:
            if conformal_mesh is None:
                full_surface_map = _empty_surface_map()
                conformal_surface_map = full_surface_map
                if params.include_infill or params.perimeters > 0:
                    warnings.append("No conformal faces were selected, so the conformal phase was skipped.")
            else:
                if substrate_mesh is not None:
                    conformal_surface_map, full_surface_map, thickness_map = build_conformal_base_surface_maps(
                        substrate_mesh,
                        conformal_mesh,
                        params,
                    )
                    conformal_perimeters, conformal_infill, conformal_meta = generate_conformal_paths_from_base_surface(
                        conformal_surface_map,
                        thickness_map,
                        params,
                    )
                else:
                    center_xy = working_mesh.bounds_center[:2]
                    full_surface_map = build_cylindrical_surface_map(conformal_mesh, center_xy, params)
                    conformal_surface_map = full_surface_map
                    conformal_perimeters = generate_conformal_perimeter_paths(
                        conformal_surface_map,
                        params,
                        core_profile=None,
                    )
                    conformal_infill = generate_conformal_infill_paths(conformal_surface_map, params) if params.include_infill else []
        elif component_mode:
            if conformal_mesh is None:
                full_surface_map = _empty_surface_map()
                conformal_surface_map = full_surface_map
                if params.include_infill or params.perimeters > 0:
                    warnings.append("No conformal geometry was selected, so the conformal phase was skipped.")
            else:
                if substrate_mesh is not None:
                    conformal_surface_map, full_surface_map, thickness_map = build_conformal_base_surface_maps(
                        substrate_mesh,
                        conformal_mesh,
                        params,
                    )
                    conformal_perimeters, conformal_infill, conformal_meta = generate_conformal_paths_from_base_surface(
                        conformal_surface_map,
                        thickness_map,
                        params,
                    )
                else:
                    center_xy = working_mesh.bounds_center[:2]
                    full_surface_map = build_cylindrical_surface_map(conformal_mesh, center_xy, params)
                    conformal_surface_map = full_surface_map
                    conformal_perimeters = generate_conformal_perimeter_paths(
                        conformal_surface_map,
                        params,
                        core_profile=None,
                    )
                    conformal_infill = generate_conformal_infill_paths(conformal_surface_map, params) if params.include_infill else []
        else:
            surface_finish_params = replace(
                params,
                grid_step_mm=min(params.grid_step_mm, 0.1),
                segment_length_mm=min(params.segment_length_mm, 0.1),
            )
            full_surface_map = build_cylindrical_surface_map(
                working_mesh,
                core_profile.center_xy,
                surface_finish_params,
            )
            conformal_surface_map = exclude_rotary_core_from_surface(
                full_surface_map,
                core_profile,
                margin_mm=max(surface_finish_params.line_spacing_mm * 0.45, surface_finish_params.nozzle_diameter_mm * 0.35),
            )
            conformal_perimeters, conformal_meta = generate_open5x_surface_finish_paths_from_surface_map(
                conformal_surface_map,
                core_profile.center_xy,
                surface_finish_params,
            )
            conformal_infill = []

        has_target_surface = (explicit_selection_mode and conformal_mesh is not None) or (not explicit_selection_mode and np.any(conformal_surface_map.valid_mask))
        if not conformal_perimeters and has_target_surface:
            warnings.append("No conformal perimeter paths were generated for the selected surface or geometry.")

        if params.include_infill and not conformal_infill and has_target_surface and str(conformal_meta.get("strategy", "")) != "open5x-surface-finish":
            warnings.append("No conformal infill paths were generated for the selected surface or geometry.")

        conformal_toolpaths = conformal_perimeters + conformal_infill
        toolpaths.extend(conformal_toolpaths)

        core_center_xy = substrate_mesh.bounds_center[:2] if substrate_mesh is not None else core_profile.center_xy
        core_min_z_mm = float(substrate_mesh.bounds_min[2]) if substrate_mesh is not None else float(core_profile.min_z_mm) if not core_profile.is_empty else 0.0
        core_max_z_mm = float(substrate_mesh.bounds_max[2]) if substrate_mesh is not None else float(core_profile.max_z_mm) if not core_profile.is_empty else 0.0
        core_max_radius_mm = (
            float(np.max(np.linalg.norm(substrate_mesh.vertices[:, :2] - substrate_mesh.bounds_center[:2], axis=1)))
            if substrate_mesh is not None and len(substrate_mesh.vertices)
            else float(np.max(core_profile.radii_mm)) if len(core_profile.radii_mm) else 0.0
        )

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
            "conformal_layer_count": int(conformal_meta.get("layer_count", 0)),
            "conformal_strategy": str(conformal_meta.get("strategy", "top-surface")),
            "core_center_x_mm": float(core_center_xy[0]) if len(core_center_xy) == 2 else 0.0,
            "core_center_y_mm": float(core_center_xy[1]) if len(core_center_xy) == 2 else 0.0,
            "core_max_radius_mm": core_max_radius_mm,
            "core_min_z_mm": core_min_z_mm,
            "core_max_z_mm": core_max_z_mm,
            "component_count": len(components),
            "substrate_component_index": -1 if substrate_index is None else int(substrate_index),
            "conformal_component_indices": list(int(index) for index in conformal_indices),
            "selection_mode": "faces" if face_selection_active else "components" if component_mode else "auto",
            "selected_substrate_face_count": int(len(selected_substrate_faces)),
            "selected_conformal_face_count": int(len(selected_conformal_faces)),
        }

        return SliceResult(
            mesh=working_mesh,
            surface_map=conformal_surface_map,
            toolpaths=toolpaths,
            warnings=warnings,
            metadata=metadata,
        )


def slice_planar_model(mesh: MeshModel, params: SliceParameters) -> SliceResult:
    """Slice the whole mesh with ordinary horizontal layers for 3-axis mode.

    在纯三轴模式下，用普通水平分层对整个模型进行切片。
    """

    working_mesh = mesh.centered_for_build() if params.auto_center_model else mesh
    toolpaths, planar_meta, warnings = slice_planar_mesh(working_mesh, params)
    metadata = {
        "path_count": len(toolpaths),
        "planar_path_count": len(toolpaths),
        "conformal_path_count": 0,
        "conformal_perimeter_count": 0,
        "conformal_infill_count": 0,
        "planar_layer_count": int(planar_meta.get("layer_count", 0)),
        "model_size_mm": working_mesh.size.tolist(),
        "surface_samples": 0,
        "full_surface_samples": 0,
        "transition_height_mm": float(planar_meta.get("transition_height_mm", 0.0)),
        "surface_min_z_mm": 0.0,
        "surface_max_z_mm": 0.0,
        "core_center_x_mm": float(planar_meta.get("core_center_x_mm", working_mesh.bounds_center[0])),
        "core_center_y_mm": float(planar_meta.get("core_center_y_mm", working_mesh.bounds_center[1])),
        "core_max_radius_mm": float(planar_meta.get("core_max_radius_mm", 0.0)),
        "core_min_z_mm": float(working_mesh.bounds_min[2]),
        "core_max_z_mm": float(working_mesh.bounds_max[2]),
        "component_count": len(split_mesh_into_components(working_mesh)),
        "substrate_component_index": -1,
        "conformal_component_indices": [],
        "selection_mode": "planar-only",
        "selected_substrate_face_count": 0,
        "selected_conformal_face_count": 0,
    }
    return SliceResult(
        mesh=working_mesh,
        surface_map=_empty_surface_map(),
        toolpaths=toolpaths,
        warnings=warnings,
        metadata=metadata,
    )


def _empty_surface_map() -> SurfaceMap:
    """Return a tiny placeholder ``SurfaceMap`` for empty states.

    返回一个给空状态占位的小 ``SurfaceMap``。
    """

    x_coords = np.array([0.0], dtype=float)
    y_coords = np.array([0.0], dtype=float)
    return SurfaceMap(
        x_min=0.0,
        y_min=0.0,
        step_mm=1.0,
        x_coords=x_coords,
        y_coords=y_coords,
        z_map=np.full((1, 1), np.nan, dtype=float),
        normal_map=np.array([[[0.0, 0.0, 1.0]]], dtype=float),
        valid_mask=np.zeros((1, 1), dtype=bool),
        point_map=np.array([[[0.0, 0.0, 0.0]]], dtype=float),
    )


def _resolve_component_selection(
    working_mesh: MeshModel,
    components: list[MeshModel],
    selection: SliceSelection | None,
) -> tuple[int | None, tuple[int, ...]]:
    if len(components) <= 1:
        return None, ()

    selected_substrate = selection.substrate_component_index if selection is not None else None
    if selected_substrate is None or not (0 <= selected_substrate < len(components)):
        selected_substrate = _detect_default_substrate_component(working_mesh, components)

    selected_conformal = tuple(index for index in (selection.conformal_component_indices if selection is not None else ()) if 0 <= index < len(components) and index != selected_substrate)
    if not selected_conformal:
        selected_conformal = tuple(index for index in range(len(components)) if index != selected_substrate)
    return selected_substrate, selected_conformal


def _detect_default_substrate_component(working_mesh: MeshModel, components: list[MeshModel]) -> int:
    overall_center_xy = working_mesh.bounds_center[:2]
    best_index = 0
    best_score = (math.inf, math.inf, math.inf)
    for index, component in enumerate(components):
        radial_distance = float(np.linalg.norm(component.bounds_center[:2] - overall_center_xy))
        score = (
            radial_distance,
            -float(component.size[2]),
            -float(len(component.faces)),
        )
        if score < best_score:
            best_index = index
            best_score = score
    return best_index


def build_surface_map(
    mesh: MeshModel,
    params: SliceParameters,
    x_coords: np.ndarray | None = None,
    y_coords: np.ndarray | None = None,
) -> SurfaceMap:
    """Sample the printable top surface on a regular XY grid.

    在规则 XY 网格上采样可打印顶部表面。

    This turns the triangle mesh into a height/normal raster that is easy to
    query later.
    它会把三角网格整理成后面容易查询的高度和法向栅格。
    """

    bounds_min = mesh.bounds_min
    bounds_max = mesh.bounds_max
    if x_coords is None or y_coords is None:
        step = max(params.grid_step_mm, 0.1)
        x_coords = np.arange(bounds_min[0], bounds_max[0] + step, step, dtype=float)
        y_coords = np.arange(bounds_min[1], bounds_max[1] + step, step, dtype=float)
    else:
        x_coords = np.asarray(x_coords, dtype=float)
        y_coords = np.asarray(y_coords, dtype=float)
        if len(x_coords) == 0 or len(y_coords) == 0:
            return _empty_surface_map()
        step_x = float(np.mean(np.diff(x_coords))) if len(x_coords) > 1 else max(params.grid_step_mm, 0.1)
        step_y = float(np.mean(np.diff(y_coords))) if len(y_coords) > 1 else max(params.grid_step_mm, 0.1)
        step = max(min(step_x, step_y), 0.1)

    z_map = np.full((len(y_coords), len(x_coords)), -np.inf, dtype=float)
    normal_map = np.zeros((len(y_coords), len(x_coords), 3), dtype=float)

    tri_vertices = mesh.face_vertices
    tri_vertex_normals = mesh.vertex_normals[mesh.faces]

    # Rasterize each upward-facing triangle into the XY grid and keep the
    # highest valid hit in every sample cell.
    # 把每个朝上的三角面片栅格化到 XY 网格里，每个采样格只保留最高的
    # 有效命中。
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

    xx, yy = np.meshgrid(x_coords, y_coords)
    point_map = np.stack([xx, yy, z_map], axis=-1)

    return SurfaceMap(
        x_min=float(x_coords[0]),
        y_min=float(y_coords[0]),
        step_mm=step,
        x_coords=x_coords,
        y_coords=y_coords,
        z_map=z_map,
        normal_map=normal_map,
        valid_mask=valid_mask,
        point_map=point_map,
    )


def build_conformal_base_surface_maps(
    substrate_mesh: MeshModel,
    conformal_mesh: MeshModel,
    params: SliceParameters,
) -> tuple[SurfaceMap, SurfaceMap, np.ndarray]:
    """Estimate conformal thickness on top of a substrate surface.

    从基底网格和共形网格估计“基底上方还有多厚的共形材料”。

    The idea is close to Open5x: sample the substrate first, then measure how
    much conformal material sits above each sample.
    思路和 Open5x 比较接近，先把基底表面采出来，再去量每个采样点上方还有
    多少共形材料。
    """

    center_xy = substrate_mesh.bounds_center[:2]
    reference_radius_mm = _cylindrical_reference_radius(substrate_mesh, center_xy, params)
    substrate_surface_map = build_cylindrical_surface_map(
        substrate_mesh,
        center_xy,
        params,
        reference_radius_mm=reference_radius_mm,
    )
    conformal_top_map = build_cylindrical_surface_map(
        conformal_mesh,
        center_xy,
        params,
        x_coords=substrate_surface_map.x_coords,
        y_coords=substrate_surface_map.y_coords,
        reference_radius_mm=reference_radius_mm,
    )
    base_points = (
        substrate_surface_map.point_map.copy()
        if substrate_surface_map.point_map is not None
        else np.zeros((*substrate_surface_map.z_map.shape, 3), dtype=float)
    )
    base_normals = _normalize(substrate_surface_map.normal_map.copy())
    overlap_mask = substrate_surface_map.valid_mask & conformal_top_map.valid_mask

    thickness_map = np.zeros(substrate_surface_map.z_map.shape, dtype=float)
    if np.any(overlap_mask):
        delta_points = conformal_top_map.point_map - base_points
        signed_gap = np.einsum("...i,...i->...", delta_points, base_normals)
        thickness_map[overlap_mask] = np.maximum(signed_gap[overlap_mask], 0.0)

    base_reference_map = build_offset_surface_map(
        substrate_surface_map,
        thickness_map,
        offset_mm=0.0,
        min_remaining_mm=max(params.layer_height_mm * 0.2, params.nozzle_diameter_mm * 0.15),
    )
    if substrate_surface_map.point_map is not None:
        base_reference_map = SurfaceMap(
            x_min=base_reference_map.x_min,
            y_min=base_reference_map.y_min,
            step_mm=base_reference_map.step_mm,
            x_coords=base_reference_map.x_coords.copy(),
            y_coords=base_reference_map.y_coords.copy(),
            z_map=base_reference_map.z_map.copy(),
            normal_map=base_reference_map.normal_map.copy(),
            valid_mask=base_reference_map.valid_mask.copy(),
            point_map=base_reference_map.point_map.copy(),
        )
    return base_reference_map, conformal_top_map, thickness_map


def build_offset_surface_map(
    base_surface_map: SurfaceMap,
    thickness_map: np.ndarray,
    offset_mm: float,
    min_remaining_mm: float,
) -> SurfaceMap:
    """Offset a surface map along its normals and respect remaining thickness.

    沿法向偏移表面图，同时顾及剩余材料厚度约束。
    """

    point_map = (
        base_surface_map.point_map.copy()
        if base_surface_map.point_map is not None
        else np.zeros((*base_surface_map.z_map.shape, 3), dtype=float)
    )
    normal_map = _normalize(base_surface_map.normal_map.copy())
    valid_mask = base_surface_map.valid_mask & (thickness_map >= (offset_mm + min_remaining_mm))
    offset_points = point_map + normal_map * float(offset_mm)
    z_map = offset_points[..., 2].copy()
    z_map[~valid_mask] = np.nan
    normal_map[~valid_mask] = np.array([0.0, 0.0, 1.0])
    offset_points[~valid_mask] = np.array([0.0, 0.0, 0.0])
    return SurfaceMap(
        x_min=base_surface_map.x_min,
        y_min=base_surface_map.y_min,
        step_mm=base_surface_map.step_mm,
        x_coords=base_surface_map.x_coords.copy(),
        y_coords=base_surface_map.y_coords.copy(),
        z_map=z_map,
        normal_map=normal_map,
        valid_mask=valid_mask,
        point_map=offset_points,
    )


def generate_open5x_surface_finish_paths(
    conformal_mesh: MeshModel,
    center_xy: np.ndarray,
    params: SliceParameters,
    *,
    reference_radius_mm: float | None = None,
) -> tuple[SurfaceMap, list[Toolpath], dict[str, float | int | str]]:
    """Generate single-pass Open5x-style surface-finish paths from a mesh.

    从网格直接生成 Open5x 风格的单道曲面精加工路径。
    """

    surface_finish_params = replace(
        params,
        grid_step_mm=min(params.grid_step_mm, 0.1),
        segment_length_mm=min(params.segment_length_mm, 0.1),
    )
    full_surface_map = build_cylindrical_surface_map(
        conformal_mesh,
        center_xy,
        surface_finish_params,
        reference_radius_mm=reference_radius_mm,
    )
    if not np.any(full_surface_map.valid_mask):
        return full_surface_map, [], {"layer_count": 0, "strategy": "open5x-surface-finish"}
    seam_shift_cols = _surface_finish_seam_shift(full_surface_map)
    full_surface_map = _roll_surface_map_columns(full_surface_map, -seam_shift_cols)

    paths: list[Toolpath] = []
    component_meshes = split_mesh_into_components(conformal_mesh)
    component_meshes = sorted(
        component_meshes,
        key=lambda component: _surface_finish_component_angle_deg(component, center_xy),
    )
    for component_index, component_mesh in enumerate(component_meshes, start=1):
        component_surface_map = build_cylindrical_surface_map(
            component_mesh,
            center_xy,
            surface_finish_params,
            x_coords=full_surface_map.x_coords,
            y_coords=full_surface_map.y_coords,
            reference_radius_mm=reference_radius_mm,
        )
        component_surface_map = _roll_surface_map_columns(component_surface_map, -seam_shift_cols)
        paths.extend(_surface_finish_component_toolpaths(component_surface_map, component_index, center_xy))

    metadata = {
        "layer_count": 1 if paths else 0,
        "strategy": "open5x-surface-finish",
        "path_count": len(paths),
        "component_count": len(component_meshes),
        "sample_step_mm": surface_finish_params.grid_step_mm,
    }
    return full_surface_map, paths, metadata


def generate_open5x_surface_finish_paths_from_surface_map(
    surface_map: SurfaceMap,
    center_xy: np.ndarray,
    params: SliceParameters,
) -> tuple[list[Toolpath], dict[str, float | int | str]]:
    """Generate Open5x-style surface-finish paths from an existing surface map.

    基于现成的表面图生成 Open5x 风格的曲面精加工路径。

    Use this when the surface map is already available and only the final
    single-pass path extraction is left.
    当项目已经拿到表面图，只剩最后那一步单道路径提取时，就走这个变体。
    """

    if surface_map.point_map is None or not np.any(surface_map.valid_mask):
        return [], {"layer_count": 0, "strategy": "open5x-surface-finish", "path_count": 0, "component_count": 0}
    surface_map = _roll_surface_map_columns(surface_map, -_surface_finish_seam_shift(surface_map))

    component_labels, component_count = ndimage.label(surface_map.valid_mask.astype(np.int8))
    component_sizes = [int(np.count_nonzero(component_labels == component_index)) for component_index in range(1, int(component_count) + 1)]
    largest_component = max(component_sizes, default=0)
    minimum_component_size = max(64, int(largest_component * 0.005))
    component_surfaces: list[tuple[float, SurfaceMap]] = []
    for component_index in range(1, int(component_count) + 1):
        component_mask = component_labels == component_index
        if int(np.count_nonzero(component_mask)) < minimum_component_size:
            continue
        component_surface_map = SurfaceMap(
            x_min=surface_map.x_min,
            y_min=surface_map.y_min,
            step_mm=surface_map.step_mm,
            x_coords=surface_map.x_coords.copy(),
            y_coords=surface_map.y_coords.copy(),
            z_map=surface_map.z_map.copy(),
            normal_map=surface_map.normal_map.copy(),
            valid_mask=component_mask,
            point_map=None if surface_map.point_map is None else surface_map.point_map.copy(),
        )
        component_surfaces.append((_surface_finish_component_angle_from_surface(component_surface_map, center_xy), component_surface_map))

    component_surfaces.sort(key=lambda item: item[0])
    paths: list[Toolpath] = []
    for component_index, (_, component_surface_map) in enumerate(component_surfaces, start=1):
        paths.extend(_surface_finish_component_toolpaths(component_surface_map, component_index, center_xy))

    metadata = {
        "layer_count": 1 if paths else 0,
        "strategy": "open5x-surface-finish",
        "path_count": len(paths),
        "component_count": len(component_surfaces),
        "sample_step_mm": params.grid_step_mm,
    }
    return paths, metadata


def _surface_finish_component_angle_deg(component_mesh: MeshModel, center_xy: np.ndarray) -> float:
    radial_xy = np.asarray(component_mesh.bounds_center[:2], dtype=float) - np.asarray(center_xy, dtype=float)
    return math.degrees(math.atan2(float(radial_xy[1]), float(radial_xy[0]))) % 360.0


def _surface_finish_component_angle_from_surface(surface_map: SurfaceMap, center_xy: np.ndarray) -> float:
    if surface_map.point_map is None or not np.any(surface_map.valid_mask):
        return 0.0
    points = np.asarray(surface_map.point_map[surface_map.valid_mask], dtype=float)
    mean_xy = points[:, :2].mean(axis=0)
    radial_xy = mean_xy - np.asarray(center_xy, dtype=float)
    return math.degrees(math.atan2(float(radial_xy[1]), float(radial_xy[0]))) % 360.0


def _surface_finish_seam_shift(surface_map: SurfaceMap) -> int:
    if surface_map.point_map is None or not np.any(surface_map.valid_mask):
        return 0
    valid_counts = np.count_nonzero(surface_map.valid_mask, axis=0)
    if len(valid_counts) == 0:
        return 0
    return int(np.argmin(valid_counts))


def _roll_surface_map_columns(surface_map: SurfaceMap, shift_cols: int) -> SurfaceMap:
    if surface_map.point_map is None or not np.any(surface_map.valid_mask):
        return surface_map
    column_count = surface_map.valid_mask.shape[1]
    if column_count == 0:
        return surface_map
    normalized_shift = int(shift_cols) % column_count
    if normalized_shift == 0:
        return surface_map
    return SurfaceMap(
        x_min=surface_map.x_min,
        y_min=surface_map.y_min,
        step_mm=surface_map.step_mm,
        x_coords=surface_map.x_coords.copy(),
        y_coords=surface_map.y_coords.copy(),
        z_map=np.roll(surface_map.z_map, normalized_shift, axis=1),
        normal_map=np.roll(surface_map.normal_map, normalized_shift, axis=1),
        valid_mask=np.roll(surface_map.valid_mask, normalized_shift, axis=1),
        point_map=np.roll(surface_map.point_map, normalized_shift, axis=1),
    )


def _surface_finish_component_toolpaths(
    surface_map: SurfaceMap,
    component_index: int,
    center_xy: np.ndarray,
) -> list[Toolpath]:
    row_runs = _surface_finish_row_runs(surface_map)
    if not row_runs:
        return []

    stitched_paths = _stitch_surface_finish_row_runs(row_runs, surface_map.step_mm)
    toolpaths: list[Toolpath] = []
    for path_index, (points, normals) in enumerate(stitched_paths, start=1):
        points, normals = _resample_surface_finish_path(
            points,
            normals,
            spacing_mm=_surface_finish_sample_step(surface_map.step_mm),
        )
        if len(points) < 16:
            continue
        name_suffix = f"-{path_index}" if len(stitched_paths) > 1 else ""
        radial_normals = _surface_finish_open5x_normals(points, normals, center_xy)
        toolpaths.append(
            Toolpath(
                name=f"Open5x Surface C{component_index}{name_suffix}",
                kind="conformal-surface-finish",
                points=points,
                normals=radial_normals,
                closed=False,
                phase="conformal",
                layer_index=1,
                z_height_mm=0.0,
            )
        )
    return toolpaths


def _surface_finish_sample_step(step_mm: float) -> float:
    return max(min(float(step_mm) * 1.5, 0.15), float(step_mm))


def _resample_surface_finish_path(
    points: np.ndarray,
    normals: np.ndarray,
    spacing_mm: float,
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points, dtype=float)
    normals = _normalize(np.asarray(normals, dtype=float))
    if len(points) < 2:
        return points.copy(), normals.copy()

    spacing_mm = max(float(spacing_mm), 1e-6)
    segment_vectors = np.diff(points, axis=0)
    segment_lengths = np.linalg.norm(segment_vectors, axis=1)
    total_length_mm = float(segment_lengths.sum())
    if total_length_mm <= spacing_mm:
        return points.copy(), normals.copy()

    cumulative = np.concatenate([[0.0], np.cumsum(segment_lengths)])
    samples = np.arange(0.0, total_length_mm, spacing_mm, dtype=float)
    if len(samples) == 0 or not math.isclose(samples[-1], total_length_mm, rel_tol=1e-6, abs_tol=1e-6):
        samples = np.append(samples, total_length_mm)

    sampled_points: list[np.ndarray] = []
    sampled_normals: list[np.ndarray] = []
    segment_index = 0
    for target_mm in samples:
        while segment_index < len(segment_lengths) - 1 and cumulative[segment_index + 1] < target_mm:
            segment_index += 1
        start_mm = cumulative[segment_index]
        end_mm = cumulative[segment_index + 1]
        ratio = 0.0 if math.isclose(end_mm, start_mm) else (target_mm - start_mm) / (end_mm - start_mm)
        sampled_points.append(points[segment_index] * (1.0 - ratio) + points[segment_index + 1] * ratio)
        sampled_normals.append(normals[segment_index] * (1.0 - ratio) + normals[segment_index + 1] * ratio)

    return np.asarray(sampled_points, dtype=float), _normalize(np.asarray(sampled_normals, dtype=float))


def _surface_finish_open5x_normals(
    points: np.ndarray,
    reference_normals: np.ndarray,
    center_xy: np.ndarray,
) -> np.ndarray:
    radial = np.asarray(points, dtype=float).copy()
    radial[:, 0] -= float(center_xy[0])
    radial[:, 1] -= float(center_xy[1])
    radial[:, 2] = 0.0
    radial = _normalize(radial)

    reference_normals = _normalize(np.asarray(reference_normals, dtype=float))
    z_component = reference_normals[:, 2].astype(float, copy=False)
    if len(z_component) >= 5:
        kernel_size = min(9, len(z_component) if len(z_component) % 2 == 1 else len(z_component) - 1)
        kernel_size = max(kernel_size, 3)
        pad = kernel_size // 2
        padded = np.pad(z_component, (pad, pad), mode="edge")
        kernel = np.full(kernel_size, 1.0 / kernel_size, dtype=float)
        z_component = np.convolve(padded, kernel, mode="valid")

    slope_z = np.clip(z_component * 0.088, -0.088, 0.088)
    xy_scale = np.sqrt(np.maximum(1.0 - slope_z**2, 1e-6))
    blended = radial * xy_scale[:, None]
    blended[:, 2] = slope_z
    return _normalize(blended)


def _surface_finish_row_runs(surface_map: SurfaceMap) -> list[tuple[int, np.ndarray, np.ndarray]]:
    if surface_map.point_map is None or not np.any(surface_map.valid_mask):
        return []

    row_runs: list[tuple[int, np.ndarray, np.ndarray]] = []
    for row_index in range(surface_map.valid_mask.shape[0]):
        cols = np.flatnonzero(surface_map.valid_mask[row_index])
        if len(cols) < 3:
            continue
        runs = _split_index_runs(cols)
        if not runs:
            continue
        best_run = max(runs, key=len)
        if len(best_run) < 3:
            continue
        points = surface_map.point_map[row_index, best_run].copy()
        normals = _normalize(surface_map.normal_map[row_index, best_run].copy())
        row_runs.append((row_index, points, normals))
    return row_runs


def _stitch_surface_finish_row_runs(
    row_runs: list[tuple[int, np.ndarray, np.ndarray]],
    step_mm: float,
) -> list[tuple[np.ndarray, np.ndarray]]:
    if not row_runs:
        return []

    stitched_paths: list[tuple[np.ndarray, np.ndarray]] = []
    # Surface-finish sweeps should favor a few long continuous paths. The earlier
    # 4 mm threshold fragmented blade surfaces into many short blocks.
    connect_threshold_mm = max(step_mm * 160.0, 16.0)
    current_points = row_runs[0][1].copy()
    current_normals = row_runs[0][2].copy()

    for _, points, normals in row_runs[1:]:
        forward = (points, normals)
        backward = (points[::-1].copy(), normals[::-1].copy())
        best_points, best_normals = min(
            (forward, backward),
            key=lambda candidate: float(np.linalg.norm(candidate[0][0] - current_points[-1])),
        )
        gap_mm = float(np.linalg.norm(best_points[0] - current_points[-1]))
        if gap_mm > connect_threshold_mm:
            stitched_paths.append((current_points, _normalize(current_normals)))
            current_points = best_points.copy()
            current_normals = best_normals.copy()
            continue

        bridge_points, bridge_normals = _surface_finish_bridge(
            current_points[-1],
            current_normals[-1],
            best_points[0],
            best_normals[0],
            step_mm,
        )
        current_points = np.vstack([current_points, bridge_points[1:], best_points[1:]])
        current_normals = np.vstack([current_normals, bridge_normals[1:], best_normals[1:]])

    stitched_paths.append((current_points, _normalize(current_normals)))
    return stitched_paths


def _surface_finish_bridge(
    start_point: np.ndarray,
    start_normal: np.ndarray,
    end_point: np.ndarray,
    end_normal: np.ndarray,
    step_mm: float,
) -> tuple[np.ndarray, np.ndarray]:
    gap_mm = float(np.linalg.norm(end_point - start_point))
    if gap_mm <= 1e-9:
        return (
            np.vstack([start_point, end_point]),
            _normalize(np.vstack([start_normal, end_normal])),
        )

    steps = max(2, int(math.ceil(gap_mm / max(step_mm, 1e-6))) + 1)
    t_values = np.linspace(0.0, 1.0, steps)
    bridge_points = start_point[None, :] * (1.0 - t_values[:, None]) + end_point[None, :] * t_values[:, None]
    bridge_normals = start_normal[None, :] * (1.0 - t_values[:, None]) + end_normal[None, :] * t_values[:, None]
    return bridge_points, _normalize(bridge_normals)


def _split_index_runs(indices: np.ndarray) -> list[np.ndarray]:
    if len(indices) == 0:
        return []
    split_points = np.where(np.diff(indices) > 1)[0] + 1
    return [run for run in np.split(indices, split_points) if len(run) > 0]


def generate_conformal_paths_from_base_surface(
    base_surface_map: SurfaceMap,
    thickness_map: np.ndarray,
    params: SliceParameters,
) -> tuple[list[Toolpath], list[Toolpath], dict[str, float | int | str]]:
    """Create layered conformal perimeters and infill from a thickness field.

    根据厚度场生成分层的共形外轮廓和填充路径。
    """

    if not np.any(base_surface_map.valid_mask):
        return [], [], {"layer_count": 0, "strategy": "substrate-offset"}

    max_thickness_mm = float(np.max(thickness_map[base_surface_map.valid_mask])) if np.any(base_surface_map.valid_mask) else 0.0
    if max_thickness_mm <= 1e-6:
        return [], [], {"layer_count": 0, "strategy": "substrate-offset"}

    layer_step = max(params.layer_height_mm, 1e-3)
    perimeter_paths: list[Toolpath] = []
    infill_paths: list[Toolpath] = []
    emitted_layers = 0

    layer_offsets = np.arange(0.0, max_thickness_mm + layer_step * 0.5, layer_step, dtype=float)
    for layer_index, offset_mm in enumerate(layer_offsets, start=1):
        layer_surface_map = build_offset_surface_map(
            base_surface_map,
            thickness_map,
            offset_mm=float(offset_mm),
            min_remaining_mm=max(layer_step * 0.15, params.nozzle_diameter_mm * 0.1),
        )
        if not np.any(layer_surface_map.valid_mask):
            continue

        layer_perimeters = generate_conformal_perimeter_paths(layer_surface_map, params)
        layer_infill = generate_conformal_infill_paths(layer_surface_map, params) if params.include_infill else []
        if not layer_perimeters and not layer_infill:
            continue

        emitted_layers += 1
        perimeter_paths.extend(_annotate_conformal_layer_paths(layer_perimeters, layer_index, float(offset_mm)))
        infill_paths.extend(_annotate_conformal_layer_paths(layer_infill, layer_index, float(offset_mm)))

    return perimeter_paths, infill_paths, {"layer_count": emitted_layers, "strategy": "substrate-offset"}


def _annotate_conformal_layer_paths(toolpaths: list[Toolpath], layer_index: int, offset_mm: float) -> list[Toolpath]:
    annotated_paths: list[Toolpath] = []
    for toolpath in toolpaths:
        annotated_paths.append(
            Toolpath(
                name=f"{toolpath.name} L{layer_index}",
                kind=toolpath.kind,
                points=toolpath.points,
                normals=toolpath.normals,
                closed=toolpath.closed,
                phase=toolpath.phase,
                layer_index=layer_index,
                z_height_mm=offset_mm,
            )
        )
    return annotated_paths


def build_cylindrical_surface_map(
    mesh: MeshModel,
    center_xy: np.ndarray,
    params: SliceParameters,
    x_coords: np.ndarray | None = None,
    y_coords: np.ndarray | None = None,
    reference_radius_mm: float | None = None,
) -> SurfaceMap:
    """Sample conformal geometry around the substrate in cylindrical form.

    以柱坐标的方式围绕基底中心采样共形几何。

    The X axis of the map is arc length around the rotary centre, and the Y
    axis is Z height.
    结果里的 X 轴表示绕回转中心展开后的弧长，Y 轴表示 Z 高度。
    """

    z_step = max(params.grid_step_mm, 0.1)
    reference_radius = reference_radius_mm or _cylindrical_reference_radius(mesh, center_xy, params)

    if y_coords is None:
        z_coords = np.arange(mesh.bounds_min[2], mesh.bounds_max[2] + z_step * 0.5, z_step, dtype=float)
        if len(z_coords) == 0:
            z_coords = np.array([mesh.bounds_center[2]], dtype=float)
    else:
        z_coords = np.asarray(y_coords, dtype=float)
        if len(z_coords) == 0:
            return _empty_surface_map()

    if x_coords is None:
        circumference_mm = max(2.0 * math.pi * reference_radius, params.grid_step_mm * 16.0)
        theta_count = max(int(math.ceil(circumference_mm / z_step)), 64)
        x_coords = np.arange(theta_count, dtype=float) * z_step
    else:
        x_coords = np.asarray(x_coords, dtype=float)
        if len(x_coords) == 0:
            return _empty_surface_map()
    theta_values = x_coords / max(reference_radius, 1e-6)

    point_map = np.zeros((len(z_coords), len(x_coords), 3), dtype=float)
    normal_map = np.zeros((len(z_coords), len(x_coords), 3), dtype=float)
    z_map = np.full((len(z_coords), len(x_coords)), np.nan, dtype=float)
    valid_mask = np.zeros((len(z_coords), len(x_coords)), dtype=bool)

    # Walk upward one Z slice at a time and, for each angular sample, search
    # the nearest hit along the radial direction.
    # 这里按 Z 切片一层层往上扫，并在每个角度采样位置沿径向找最近命中点。
    extractor = HorizontalSectionExtractor(mesh)
    for row_index, z_value in enumerate(z_coords):
        segments = extractor.segments_with_normals(float(z_value))
        if not segments:
            continue
        for col_index, theta in enumerate(theta_values):
            direction = np.array([math.cos(theta), math.sin(theta)], dtype=float)
            hit = _nearest_cylindrical_hit(center_xy, direction, float(z_value), segments)
            if hit is None:
                continue
            point, normal = hit
            point_map[row_index, col_index] = point
            normal_map[row_index, col_index] = normal
            z_map[row_index, col_index] = point[2]
            valid_mask[row_index, col_index] = True

    normal_map[~valid_mask] = np.array([0.0, 0.0, 1.0])
    point_map[~valid_mask] = np.array([0.0, 0.0, 0.0])
    return SurfaceMap(
        x_min=float(x_coords[0]),
        y_min=float(z_coords[0]),
        step_mm=z_step,
        x_coords=x_coords,
        y_coords=z_coords,
        z_map=z_map,
        normal_map=normal_map,
        valid_mask=valid_mask,
        point_map=point_map,
    )


def _cylindrical_reference_radius(mesh: MeshModel, center_xy: np.ndarray, params: SliceParameters) -> float:
    radial_distances = np.linalg.norm(mesh.vertices[:, :2] - center_xy[None, :], axis=1)
    positive_radii = radial_distances[radial_distances > 1e-6]
    return float(np.median(positive_radii)) if len(positive_radii) else max(params.nozzle_diameter_mm * 4.0, 1.0)


def exclude_rotary_core_from_surface(
    surface_map: SurfaceMap,
    core_profile: RotaryCoreProfile,
    margin_mm: float,
) -> SurfaceMap:
    """Remove the already-printed rotary core from the conformal surface mask.

    从共形表面掩码里移除平面阶段已经打完的回转核心区域。
    """

    if core_profile.is_empty or not np.any(surface_map.valid_mask):
        return surface_map

    filtered_valid = surface_map.valid_mask.copy()
    valid_rows, valid_cols = np.nonzero(filtered_valid)
    if len(valid_rows) == 0:
        return surface_map

    valid_z = surface_map.z_map[valid_rows, valid_cols]
    core_radii = np.interp(valid_z, core_profile.z_levels_mm, core_profile.radii_mm, left=0.0, right=0.0)
    if surface_map.point_map is not None:
        valid_points = np.asarray(surface_map.point_map[valid_rows, valid_cols], dtype=float)
        radial_distance = np.linalg.norm(valid_points[:, :2] - core_profile.center_xy[None, :], axis=1)
    else:
        xx, yy = np.meshgrid(surface_map.x_coords, surface_map.y_coords)
        radial_grid = np.sqrt((xx - core_profile.center_xy[0]) ** 2 + (yy - core_profile.center_xy[1]) ** 2)
        radial_distance = radial_grid[valid_rows, valid_cols]
    # Everything inside the detected rotary core is treated as already printed
    # by the planar phase, so conformal paths stay outside this radius.
    # 落在回转核心半径以内的区域都视为平面阶段已经完成，共形路径要绕开
    # 这部分范围。
    keep = radial_distance > (core_radii + margin_mm)
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
        point_map=surface_map.point_map.copy() if surface_map.point_map is not None else None,
    )


def generate_conformal_perimeter_paths(
    surface_map: SurfaceMap,
    params: SliceParameters,
    core_profile: RotaryCoreProfile | None = None,
) -> list[Toolpath]:
    """Extract conformal perimeter paths from one or more surface patches.

    从一个或多个表面图分区中提取共形外轮廓路径。
    """

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
    """Generate conformal infill by scanning the surface map in rotated strips.

    通过沿旋转方向扫描表面图来生成共形填充路径。
    """

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
    """Split the projected top surface into height-continuous patches.

    按高度连续性把投影后的顶部表面拆成多个区域块。

    This avoids joining blades or shells that happen to overlap in XY but are
    actually far apart in height.
    这样可以避免把只是在 XY 投影上挨得近、实际高度差很大的叶片或壳体
    错误拼到一起。
    """

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
        component_point_map = surface_map.point_map.copy() if surface_map.point_map is not None else None
        component_z_map[~component_valid] = np.nan
        component_normal_map[~component_valid] = np.array([0.0, 0.0, 1.0])
        if component_point_map is not None:
            component_point_map[~component_valid] = np.array([0.0, 0.0, 0.0])
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
                point_map=component_point_map,
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
    """Compatibility helper that returns the first contiguous valid segment.

    兼容性辅助函数，返回第一段连续有效的表面采样结果。
    """

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
    """Sample a polyline against the surface map and split it at invalid gaps.

    将一条折线投射到表面图上，并在无效区间处自动断开。
    """

    xy_points = np.asarray(xy_points, dtype=float)
    if len(xy_points) == 0:
        return []

    if closed and np.linalg.norm(xy_points[0] - xy_points[-1]) > 1e-6:
        xy_points = np.vstack([xy_points, xy_points[0]])

    segments: list[tuple[np.ndarray, np.ndarray, bool]] = []
    current_points: list[np.ndarray] = []
    current_normals: list[np.ndarray] = []
    had_gap = False
    # A large 3D jump usually means the XY contour stepped onto another face
    # patch. Split there so the exporter inserts a travel move.
    # 三维跳变一旦太大，通常就说明 XY 轮廓跨到了另一块面片区域。这时直接
    # 断开，让导出器插入空移就行。
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
    if surface_map.point_map is not None:
        point = surface_map.point_map[row_index, col_index]
    else:
        z_value = surface_map.z_map[row_index, col_index]
        point = np.array([x_value, y_value, z_value], dtype=float)
    normal = surface_map.normal_map[row_index, col_index]
    return np.asarray(point, dtype=float), normal


def sample_surface_point(surface_map: SurfaceMap, x_value: float, y_value: float) -> tuple[np.ndarray | None, np.ndarray]:
    """Bilinearly sample one XY position from a surface map.

    对表面图中的单个 XY 位置做双线性采样。

    When the query falls outside the main bilinear cell, the helper first
    tries a nearby valid fallback sample.
    查询点落在主双线性单元之外时，会先试着找附近还能用的采样点。
    """

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

    point_acc = np.zeros(3, dtype=float)
    normal_acc = np.zeros(3, dtype=float)
    total_weight = 0.0
    for row_index, col_index, weight in corners:
        if not surface_map.valid_mask[row_index, col_index]:
            continue
        if surface_map.point_map is not None:
            point_acc += surface_map.point_map[row_index, col_index] * weight
        else:
            point_acc += np.array([x_value, y_value, surface_map.z_map[row_index, col_index]], dtype=float) * weight
        normal_acc += surface_map.normal_map[row_index, col_index] * weight
        total_weight += weight

    if total_weight < 1e-6:
        fallback = _nearest_valid_surface_sample(surface_map, fx, fy, x_value, y_value)
        if fallback is not None:
            return fallback
        return None, np.array([0.0, 0.0, 1.0])

    point = point_acc / total_weight
    normal = normal_acc / total_weight
    normal = normal / max(np.linalg.norm(normal), 1e-9)
    return point, normal


def _nearest_cylindrical_hit(
    center_xy: np.ndarray,
    direction_xy: np.ndarray,
    z_value: float,
    segments: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray] | None:
    best_radius = math.inf
    best_point: np.ndarray | None = None
    best_normal: np.ndarray | None = None
    radial_direction = np.array([direction_xy[0], direction_xy[1], 0.0], dtype=float)
    for segment_points, segment_normals in segments:
        hit = _ray_segment_intersection_with_u(center_xy, direction_xy, segment_points[0], segment_points[1])
        if hit is None:
            continue
        radius_mm, segment_u = hit
        if radius_mm <= 1e-4 or radius_mm >= best_radius:
            continue
        point_xy = center_xy + direction_xy * radius_mm
        normal = segment_normals[0] * (1.0 - segment_u) + segment_normals[1] * segment_u
        normal = _normalize(np.asarray([normal], dtype=float))[0]
        if float(np.dot(normal, radial_direction)) < 0.0:
            normal = -normal
        best_radius = radius_mm
        best_point = np.array([point_xy[0], point_xy[1], z_value], dtype=float)
        best_normal = normal
    if best_point is None or best_normal is None:
        return None
    return best_point, best_normal


def _ray_segment_intersection_with_u(
    center_xy: np.ndarray,
    direction_xy: np.ndarray,
    point_a: np.ndarray,
    point_b: np.ndarray,
) -> tuple[float, float] | None:
    segment_vector = point_b - point_a
    denom = direction_xy[0] * segment_vector[1] - direction_xy[1] * segment_vector[0]
    if abs(denom) < 1e-9:
        return None

    delta = point_a - center_xy
    ray_t = (delta[0] * segment_vector[1] - delta[1] * segment_vector[0]) / denom
    segment_u = (delta[0] * direction_xy[1] - delta[1] * direction_xy[0]) / denom
    if ray_t >= 0.0 and -1e-6 <= segment_u <= 1.0 + 1e-6:
        return float(ray_t), float(np.clip(segment_u, 0.0, 1.0))
    return None


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
