"""Core data models shared by the slicer, kinematics and GUI.

The project is built around a small set of explicit dataclasses. That keeps
the research workflow easy to follow. Load a mesh, turn it into toolpaths,
turn toolpaths into machine poses, then export G-code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Keep the shared data objects here so geometry, slicing, export, and GUI all
# speak the same language.
# 核心数据对象集中放在这里，geometry、slicer、gcode、gui 之间传的都是这一套。


def _normalize_axis_name(value: object, fallback: str) -> str:
    text = str(value or "").strip().upper()
    for character in text:
        if character.isalpha():
            return character
    return fallback


def _normalize_rotary_axis_names(value: object) -> tuple[str, str]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        raw_u, raw_v = value[0], value[1]
    else:
        raw_u, raw_v = "A", "B"
    u_name = _normalize_axis_name(raw_u, "A")
    v_name = _normalize_axis_name(raw_v, "B")
    if v_name == u_name:
        for candidate in ("B", "C", "V", "U", "A"):
            if candidate != u_name:
                v_name = candidate
                break
    return u_name, v_name


def _normalize_linear_axis_names(value: object) -> tuple[str, str, str]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        raw_x, raw_y, raw_z = value[0], value[1], value[2]
    else:
        raw_x, raw_y, raw_z = "X", "Y", "Z"
    return (
        _normalize_axis_name(raw_x, "X"),
        _normalize_axis_name(raw_y, "Y"),
        _normalize_axis_name(raw_z, "Z"),
    )


@dataclass(slots=True)
class MeshModel:
    """Triangle mesh carried through the whole slicing pipeline.

    贯穿整个切片流程的三角网格对象。

    It keeps topology and precomputed normals together so later stages can
    focus on sampling, path planning, and machine mapping.
    它把拓扑信息和预计算法向放在一起，后面的采样、路径规划和机床映射
    就不用反复整理底层网格数据了。
    """

    name: str
    vertices: np.ndarray
    faces: np.ndarray
    face_normals: np.ndarray
    vertex_normals: np.ndarray
    source_path: str | None = None

    @property
    def bounds_min(self) -> np.ndarray:
        return self.vertices.min(axis=0)

    @property
    def bounds_max(self) -> np.ndarray:
        return self.vertices.max(axis=0)

    @property
    def bounds_center(self) -> np.ndarray:
        return (self.bounds_min + self.bounds_max) * 0.5

    @property
    def size(self) -> np.ndarray:
        return self.bounds_max - self.bounds_min

    @property
    def face_vertices(self) -> np.ndarray:
        return self.vertices[self.faces]

    def rigid_transformed(
        self,
        rotation: np.ndarray | None = None,
        translation: np.ndarray | None = None,
        center: np.ndarray | None = None,
        name: str | None = None,
    ) -> "MeshModel":
        """Return a rigidly transformed copy of the mesh.

        返回经过刚体变换后的网格副本。

        The GUI uses this for model placement, so the part can be rotated
        around its current centre and nudged along X/Y/Z the way people expect
        in slicers.
        GUI 的摆放操作会用到它，这样模型就能像常见切片软件里那样，
        围绕当前中心旋转，再沿 X/Y/Z 方向平移。
        """

        rotation_matrix = np.eye(3, dtype=float) if rotation is None else np.asarray(rotation, dtype=float)
        translation_vector = np.zeros(3, dtype=float) if translation is None else np.asarray(translation, dtype=float)
        pivot = np.zeros(3, dtype=float) if center is None else np.asarray(center, dtype=float)

        transformed_vertices = (self.vertices - pivot) @ rotation_matrix.T + pivot + translation_vector
        transformed_face_normals = _normalize_vectors(self.face_normals @ rotation_matrix.T)
        transformed_vertex_normals = _normalize_vectors(self.vertex_normals @ rotation_matrix.T)
        return MeshModel(
            name=name or self.name,
            vertices=transformed_vertices,
            faces=self.faces.copy(),
            face_normals=transformed_face_normals,
            vertex_normals=transformed_vertex_normals,
            source_path=self.source_path,
        )

    def translated(self, offset: np.ndarray, name: str | None = None) -> "MeshModel":
        offset = np.asarray(offset, dtype=float)
        return self.rigid_transformed(translation=offset, name=name)

    def rotated(self, axis: str, angle_deg: float, center: np.ndarray | None = None, name: str | None = None) -> "MeshModel":
        return self.rigid_transformed(rotation=_rotation_matrix(axis, angle_deg), center=center, name=name)

    def centered_for_build(self) -> "MeshModel":
        """Move the part onto the slicer's default machine origin.

        把模型放到切片器默认的机床原点附近。

        After this step, the XY centre sits on the rotary centre and the
        lowest Z point rests on the build plane. The method is idempotent, so
        it is safe to call both on load and again right before slicing.
        处理后，XY 中心会落到回转中心附近，最低 Z 点会贴到打印基面。
        这个方法本身是幂等的，所以既能在载入时调用，也能在正式切片前
        再调用一次。
        """

        bounds_min = self.bounds_min
        center_xy = self.bounds_center[:2]
        offset = np.array([-center_xy[0], -center_xy[1], -bounds_min[2]], dtype=float)
        if float(np.linalg.norm(offset)) < 1e-9:
            return self

        return self.translated(offset, name=self.name)


@dataclass(slots=True)
class SurfaceMap:
    """Regular 2D sampling of the printable conformal surface.

    可打印共形表面的规则二维采样结果。

    It turns irregular mesh geometry into arrays that are cheap to query for
    height, normals, and valid regions during path generation.
    它把不规则网格整理成便于查询的数组，后面生成路径时读高度、法向和
    有效区域都会快很多。
    """

    x_min: float
    y_min: float
    step_mm: float
    x_coords: np.ndarray
    y_coords: np.ndarray
    z_map: np.ndarray
    normal_map: np.ndarray
    valid_mask: np.ndarray
    point_map: np.ndarray | None = None

    @property
    def shape(self) -> tuple[int, int]:
        return self.z_map.shape

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (
            float(self.x_coords[0]),
            float(self.x_coords[-1]),
            float(self.y_coords[0]),
            float(self.y_coords[-1]),
        )


@dataclass(slots=True)
class Toolpath:
    """Polyline that will later become machine motion.

    后面会落成机床运动指令的折线路径。

    The slicer keeps toolpaths in model space first. The G-code layer then
    decides how to map them into XYZUV moves and extrusion.
    切片阶段先把路径保存在模型坐标系里，到了 G-code 层再决定怎么映射成
    XYZUV 运动和挤出。
    """

    name: str
    kind: str
    points: np.ndarray
    normals: np.ndarray
    closed: bool = False
    phase: str = "conformal"
    layer_index: int | None = None
    z_height_mm: float | None = None

    @property
    def point_count(self) -> int:
        return int(len(self.points))

    @property
    def length_mm(self) -> float:
        if len(self.points) < 2:
            return 0.0
        diffs = np.diff(self.points, axis=0)
        return float(np.linalg.norm(diffs, axis=1).sum())


@dataclass(slots=True)
class SliceParameters:
    """User-facing process settings.

    面向用户的一组切片工艺参数。

    Planar settings and conformal settings live side by side here so the whole
    job can be described with one object.
    平面阶段和共形阶段的参数都放在同一个对象里，整套工艺就能用一份配置
    说清楚。
    """

    nozzle_diameter_mm: float = 0.4
    layer_height_mm: float = 0.2
    line_spacing_mm: float = 0.45
    perimeters: int = 2
    infill_angle_deg: float = 45.0
    segment_length_mm: float = 0.8
    grid_step_mm: float = 0.6
    top_normal_threshold: float = -0.4
    include_infill: bool = True
    auto_center_model: bool = True
    print_speed_mm_s: float = 18.0
    planar_print_speed_mm_s: float = 24.0
    travel_speed_mm_s: float = 60.0
    travel_height_mm: float = 2.0
    nozzle_temperature_c: float = 220.0
    bed_temperature_c: float = 50.0
    wait_for_nozzle: bool = True
    wait_for_bed: bool = True
    adhesion_type: str = "none"
    skirt_line_count: int = 1
    skirt_margin_mm: float = 5.0
    filament_diameter_mm: float = 1.75
    extrusion_multiplier: float = 1.0
    retraction_mm: float = 0.8
    retract_speed_mm_s: float = 25.0
    prime_speed_mm_s: float = 20.0
    enable_planar_core: bool = True
    auto_core_transition: bool = True
    core_transition_height_mm: float = 0.0
    core_transition_percentile: float = 0.0
    planar_layer_height_mm: float = 0.0
    planar_line_spacing_mm: float = 0.0
    planar_perimeters: int = 1
    planar_include_infill: bool = True
    planar_infill_angle_deg: float = 0.0
    start_gcode: str = ""
    end_gcode: str = ""

    def resolved_planar_layer_height_mm(self) -> float:
        return self.planar_layer_height_mm if self.planar_layer_height_mm > 0.0 else self.layer_height_mm

    def resolved_planar_line_spacing_mm(self) -> float:
        return self.planar_line_spacing_mm if self.planar_line_spacing_mm > 0.0 else self.line_spacing_mm


@dataclass(slots=True)
class SliceSelection:
    """Optional user selection that decides what goes into each phase.

    可选的用户选择结果，用来决定哪些几何进入哪个打印阶段。

    The GUI can fill this from connected-component picks or painted faces,
    which makes it possible to override the automatic split when needed.
    GUI 可以通过组件选择或面片刷选来填这个对象，必要时就能覆盖自动分区
    结果。
    """

    substrate_component_index: int | None = None
    conformal_component_indices: tuple[int, ...] = ()
    substrate_face_indices: tuple[int, ...] = ()
    conformal_face_indices: tuple[int, ...] = ()


@dataclass(slots=True)
class MachineParameters:
    """Physical machine description for an Open5x-style rotary-bed printer.

    Open5x 风格回转床打印机的机床参数描述。

    This is where axis directions, zero offsets, travel limits, and template
    G-code come together.
    轴方向、零位补偿、行程限制和模板 G-code 都收在这里。
    """

    profile_name: str = "Open5x / Prusa i3 MK3s (Freddi Hong style)"
    profile_description: str = (
        "U tilts the rotary bed about the machine Y axis. V then spins the already tilted bed "
        "about its local rotary axis."
    )
    x_offset_mm: float = 0.0
    y_offset_mm: float = 0.0
    z_offset_mm: float = 0.0
    rotary_center_x_mm: float = 0.0
    rotary_center_y_mm: float = 0.0
    rotary_center_z_mm: float = 0.0
    bed_diameter_mm: float = 90.0
    rotary_scale_radius_mm: float = 35.0
    phase_change_lift_mm: float = 8.0
    rotary_safe_z_mm: float = 150.0
    rotary_safe_reposition_trigger_deg: float = 25.0
    u_axis_sign: int = 1
    v_axis_sign: int = 1
    u_zero_offset_deg: float = 0.0
    v_zero_offset_deg: float = 0.0
    home_u_deg: float = 0.0
    home_v_deg: float = 0.0
    min_u_deg: float = -95.0
    max_u_deg: float = 95.0
    min_v_deg: float = -540.0
    max_v_deg: float = 540.0
    max_feed_mm_min: float = 9000.0
    linear_axis_names: tuple[str, str, str] = ("X", "Y", "Z")
    rotary_axis_names: tuple[str, str] = ("A", "B")
    start_gcode_template: str = (
        "; Machine profile: {profile_name}\n"
        "; {u_axis_name} axis: tilt bed about machine Y\n"
        "; {v_axis_name} axis: spin tilted bed about local rotary axis\n"
        "G21\n"
        "G90\n"
        "M83\n"
        "G92 E0\n"
        "{start_heat_gcode}\n"
        "G28\n"
        "G0 {z_axis}{rotary_safe_z_mm:.3f} F3000\n"
        "G0 {u_axis}{home_u_deg:.3f} {v_axis}{home_v_deg:.3f} F3000"
    )
    phase_change_gcode_template: str = (
        "M400\n"
        "; Switching from planar core to five-axis conformal phase\n"
        "G92 E0\n"
        "G0 {z_axis}{rotary_safe_z_mm:.3f} F{travel_feed_mm_min:.1f}"
    )
    end_gcode_template: str = (
        "M400\n"
        "G92 E0\n"
        "G0 {z_axis}{rotary_safe_z_mm:.3f} F3000\n"
        "G0 {u_axis}{home_u_deg:.3f} {v_axis}{home_v_deg:.3f} F3000\n"
        "{shutdown_heat_gcode}"
    )

    def __post_init__(self) -> None:
        self.linear_axis_names = _normalize_linear_axis_names(self.linear_axis_names)
        self.rotary_axis_names = _normalize_rotary_axis_names(self.rotary_axis_names)

    @property
    def rotary_center(self) -> np.ndarray:
        return np.array(
            [self.rotary_center_x_mm, self.rotary_center_y_mm, self.rotary_center_z_mm],
            dtype=float,
        )

    @property
    def build_offset(self) -> np.ndarray:
        return np.array([self.x_offset_mm, self.y_offset_mm, self.z_offset_mm], dtype=float)

    @property
    def u_axis_name(self) -> str:
        return self.rotary_axis_names[0]

    @property
    def v_axis_name(self) -> str:
        return self.rotary_axis_names[1]

    def is_u_within_limits(self, angle_deg: float) -> bool:
        return self.min_u_deg <= angle_deg <= self.max_u_deg

    def is_v_within_limits(self, angle_deg: float) -> bool:
        return self.min_v_deg <= angle_deg <= self.max_v_deg


@dataclass(slots=True)
class SliceResult:
    """Final in-memory result from one slicing run.

    一次切片运行在内存里的最终结果。

    Besides the generated toolpaths, it also carries warnings and metadata so
    the GUI, CLI, and exporter can report the same picture.
    除了生成出来的路径，它还会带上警告和元数据，GUI、CLI、导出器看到的
    结果就能保持一致。
    """

    mesh: MeshModel
    surface_map: SurfaceMap | None
    toolpaths: list[Toolpath]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_path_length_mm(self) -> float:
        return float(sum(path.length_mm for path in self.toolpaths))

    @property
    def total_points(self) -> int:
        return int(sum(path.point_count for path in self.toolpaths))


def _rotation_matrix(axis: str, angle_deg: float) -> np.ndarray:
    """Return the standard right-handed rotation matrix for ``axis``.

    返回围绕 ``axis`` 的标准右手旋转矩阵。

    This helper is used for model placement transforms.
    它给模型摆放变换用。
    """

    axis_name = axis.upper()
    angle_rad = math.radians(angle_deg)
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    if axis_name == "X":
        return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=float)
    if axis_name == "Y":
        return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=float)
    if axis_name == "Z":
        return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)
    raise ValueError(f"Unsupported rotation axis: {axis}")


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    """Normalize row vectors and keep degenerate rows well-defined.

    按行归一化向量，并给退化行一个稳定结果。

    Zero-length rows fall back to ``[0, 0, 1]`` so downstream code never has
    to deal with NaNs from missing normals.
    零长度行会回退到 ``[0, 0, 1]``，这样下游代码就不用处理因为法向缺失
    带来的 NaN。
    """

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    safe_norms = np.where(norms < 1e-9, 1.0, norms)
    normalized = vectors / safe_norms
    normalized[norms[:, 0] < 1e-9] = np.array([0.0, 0.0, 1.0])
    return normalized
