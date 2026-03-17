"""Core data models shared by the slicer, kinematics and GUI.

The project is intentionally organised around a few explicit dataclasses so the
research workflow is easy to follow: load a mesh, convert it into toolpaths,
convert toolpaths into machine poses, then export G-code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class MeshModel:
    """Triangle mesh used throughout the slicing pipeline."""

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

        The method is used by the GUI placement tools, so users can rotate the
        model around its current centre and move it along X/Y/Z like in Cura.
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
        """Move the part close to the machine origin used by the slicer.

        After centring, the model sits near ``(0, 0, 0)``: its XY centre is
        moved onto the rotary centre and its lowest Z point is placed on the
        build plane. The method is intentionally idempotent so it can be used
        both when a model is loaded and again at slice time.
        """

        bounds_min = self.bounds_min
        center_xy = self.bounds_center[:2]
        offset = np.array([-center_xy[0], -center_xy[1], -bounds_min[2]], dtype=float)
        if float(np.linalg.norm(offset)) < 1e-9:
            return self

        return self.translated(offset, name=self.name)


@dataclass(slots=True)
class SurfaceMap:
    """Regular 2D parameter sampling of the printable conformal surface."""

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
    """Polyline that will later be turned into machine moves."""

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

    The conformal phase is the five-axis phase that follows the top surface.
    The planar phase is the simpler 3-axis core / substrate phase printed first.
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
    """Optional user selection that chooses which geometries take part in each phase."""

    substrate_component_index: int | None = None
    conformal_component_indices: tuple[int, ...] = ()
    substrate_face_indices: tuple[int, ...] = ()
    conformal_face_indices: tuple[int, ...] = ()


@dataclass(slots=True)
class MachineParameters:
    """Physical machine description for an Open5x-style rotary-bed printer."""

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
    rotary_axis_names: tuple[str, str] = ("U", "V")
    start_gcode_template: str = (
        "; Machine profile: {profile_name}\n"
        "; U axis: tilt bed about machine Y\n"
        "; V axis: spin tilted bed about local rotary axis\n"
        "G21\n"
        "G90\n"
        "M83\n"
        "G92 E0\n"
        "G28\n"
        "G0 {u_axis}{home_u_deg:.3f} {v_axis}{home_v_deg:.3f} F3000"
    )
    phase_change_gcode_template: str = (
        "M400\n"
        "; Switching from planar core to five-axis conformal phase\n"
        "G92 E0"
    )
    end_gcode_template: str = (
        "M400\n"
        "G92 E0\n"
        "G0 {u_axis}{home_u_deg:.3f} {v_axis}{home_v_deg:.3f} F3000\n"
        "M104 S0\n"
        "M140 S0"
    )

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
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    safe_norms = np.where(norms < 1e-9, 1.0, norms)
    normalized = vectors / safe_norms
    normalized[norms[:, 0] < 1e-9] = np.array([0.0, 0.0, 1.0])
    return normalized

