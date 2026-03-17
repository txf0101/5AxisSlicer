from __future__ import annotations

import math

from .models import PrintSettings


def extrusion_for_segment(length_mm: float, settings: PrintSettings) -> float:
    if length_mm <= 0.0:
        return 0.0
    bead_area = settings.line_width_mm * settings.layer_height_mm * settings.bead_area_scale
    filament_area = math.pi * (settings.filament_diameter_mm / 2.0) ** 2
    return bead_area * length_mm / filament_area * settings.flow_multiplier
