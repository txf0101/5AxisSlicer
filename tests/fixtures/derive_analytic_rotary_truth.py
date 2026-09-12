"""Recompute Rotary truth constants without importing application code.

The cone length uses composite Simpson quadrature over the parametric curve;
the application planner instead sums its sampled Toolpath chords.  The other
cases use closed-form circumference/helix relations, so the fixture is not a
copy of the production sampling loop.
"""

from __future__ import annotations

import json
import math


def _simpson(function, start: float, end: float, intervals: int = 100_000) -> float:
    if intervals % 2:
        raise ValueError("Simpson intervals must be even")
    step = (end - start) / intervals
    total = function(start) + function(end)
    total += 4.0 * sum(function(start + step * index) for index in range(1, intervals, 2))
    total += 2.0 * sum(function(start + step * index) for index in range(2, intervals, 2))
    return total * step / 3.0


def derive() -> dict[str, object]:
    origin = (10.0, -20.0, 5.0)
    cylinder_radius = 12.0
    cylinder_start_angle = math.radians(30.0)
    cylinder_sweep = 6.0 * math.pi
    cylinder_axial_start = 4.0
    cylinder_rise = 24.0
    cylinder_length = math.hypot(cylinder_radius * cylinder_sweep, cylinder_rise)

    cone_sweep = 4.0 * math.pi
    cone_axial_rise = 12.0
    cone_radius_start = 15.0
    cone_radius_end = 9.0
    radius_rate = (cone_radius_end - cone_radius_start) / cone_sweep
    axial_rate = cone_axial_rise / cone_sweep

    def cone_speed(angle: float) -> float:
        radius = cone_radius_start + radius_rate * angle
        dx = radius_rate * math.cos(angle) - radius * math.sin(angle)
        dy = radius_rate * math.sin(angle) + radius * math.cos(angle)
        return math.sqrt(dx * dx + dy * dy + axial_rate * axial_rate)

    cone_length = _simpson(cone_speed, 0.0, cone_sweep)
    thin_radii = (10.4, 11.2, 12.0)
    thin_length = 4.0 * sum(math.tau * radius for radius in thin_radii)
    around_length = 3.0 * 20.0 * math.radians(30.0 + 90.0)
    end_angle = cylinder_start_angle + cylinder_sweep

    return {
        "schema_version": 1,
        "independent_of": "five_axis_slicer.algorithms.rotary",
        "units": {"length": "mm", "angle": "rad", "volume": "mm3"},
        "frame": {
            "origin": list(origin),
            "axis": [0.0, 0.0, 1.0],
            "zero_direction": [1.0, 0.0, 0.0],
        },
        "cylinder_spiral": {
            "radius": cylinder_radius,
            "axial_start": cylinder_axial_start,
            "start_angle": cylinder_start_angle,
            "end_angle": end_angle,
            "pitch": 8.0,
            "turns": 3,
            "start": [
                origin[0] + cylinder_radius * math.cos(cylinder_start_angle),
                origin[1] + cylinder_radius * math.sin(cylinder_start_angle),
                origin[2] + cylinder_axial_start,
            ],
            "end": [
                origin[0] + cylinder_radius * math.cos(end_angle),
                origin[1] + cylinder_radius * math.sin(end_angle),
                origin[2] + cylinder_axial_start + cylinder_rise,
            ],
            "length": cylinder_length,
            "volume": cylinder_length * 0.8 * 0.4,
        },
        "cone_spiral": {
            "radius_start": cone_radius_start,
            "radius_end": cone_radius_end,
            "axial_start": 0.0,
            "axial_end": cone_axial_rise,
            "start_angle": 0.0,
            "end_angle": cone_sweep,
            "pitch": 6.0,
            "length": cone_length,
            "volume": cone_length * 0.75 * 0.3,
        },
        "thin_wall": {
            "axial": [2.0, 6.0, 10.0, 14.0],
            "radii": list(thin_radii),
            "layers": 4,
            "passes_per_layer": 3,
            "length": thin_length,
            "volume": thin_length * 0.8 * 0.4,
        },
        "around_part": {
            "radius": 20.0,
            "axial": [0.0, 0.8, 1.6],
            "regions_deg": [[350.0, 380.0], [480.0, 570.0]],
            "deposition_stripes": 6,
            "length": around_length,
            "volume": around_length * 0.8 * 0.4,
        },
    }


if __name__ == "__main__":
    print(json.dumps(derive(), indent=2, sort_keys=True))
