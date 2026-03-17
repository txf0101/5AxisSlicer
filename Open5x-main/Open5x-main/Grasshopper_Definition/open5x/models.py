from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


ArrayLike = np.ndarray


@dataclass(slots=True)
class MachineConfig:
    translation_axes: tuple[str, str, str] = ("X", "Y", "Z")
    rotation_axes: tuple[str, str] = ("U", "V")
    rotation_order: tuple[str, str] = ("x", "y")
    tool_axis: tuple[float, float, float] = (0.0, 0.0, 1.0)
    origin_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    tool_offset_mm: float = 0.0
    rotation_radius_mm: float = 35.0


@dataclass(slots=True)
class PrintSettings:
    line_width_mm: float = 0.6
    layer_height_mm: float = 0.3
    filament_diameter_mm: float = 1.75
    flow_multiplier: float = 1.0
    bead_area_scale: float = 1.0
    print_feed_mm_s: float = 8.0
    travel_feed_mm_s: float = 40.0
    retraction_length_mm: float = 1.2
    retraction_feed_mm_s: float = 20.0
    prime_length_mm: float = 1.2
    travel_lift_mm: float = 2.0
    max_feed_scale: float = 3.0


@dataclass(slots=True)
class PathSpec:
    name: str
    points_mm: ArrayLike
    normals: ArrayLike
    extrude: bool = True
    closed: bool = False


@dataclass(slots=True)
class ProjectSpec:
    name: str
    paths: list[PathSpec]
    machine: MachineConfig = field(default_factory=MachineConfig)
    print_settings: PrintSettings = field(default_factory=PrintSettings)
    start_gcode: list[str] = field(default_factory=list)
    end_gcode: list[str] = field(default_factory=list)
    comment: str = ""


@dataclass(slots=True)
class Pose:
    model_point_mm: ArrayLike
    machine_point_mm: ArrayLike
    normal: ArrayLike
    rotation_deg: ArrayLike
