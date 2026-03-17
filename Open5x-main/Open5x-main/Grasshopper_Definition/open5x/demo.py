from __future__ import annotations

import math
import numpy as np

from .models import MachineConfig, PathSpec, PrintSettings, ProjectSpec
from .vector_math import normalize_rows


def build_demo_project(turns: int = 2, samples: int = 72) -> ProjectSpec:
    radii = np.linspace(16.0, 23.0, samples)
    angles = np.linspace(0.0, turns * 2.0 * math.pi, samples)
    z_values = np.linspace(8.0, 18.0, samples)

    points = []
    normals = []
    for angle, radius, z_value in zip(angles, radii, z_values, strict=True):
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        points.append([x, y, z_value])
        normals.append([math.cos(angle), math.sin(angle), 0.35])

    point_array = np.asarray(points, dtype=float)
    normal_array = normalize_rows(np.asarray(normals, dtype=float))

    project = ProjectSpec(
        name="demo_conformal_spiral",
        comment="Synthetic conformal toolpath used to validate the Python port.",
        machine=MachineConfig(),
        print_settings=PrintSettings(),
        start_gcode=[
            "; START OPEN5X PYTHON PORT",
            "G90",
            "M83",
            "G21",
            "G92 E0",
            "M104 S205",
            "M109 S205",
        ],
        end_gcode=[
            "; END OPEN5X PYTHON PORT",
            "G1 E-1.00000 F1200.0",
            "M104 S0",
            "M84",
        ],
        paths=[
            PathSpec(
                name="spiral",
                points_mm=point_array,
                normals=normal_array,
                extrude=True,
                closed=False,
            )
        ],
    )
    return project
