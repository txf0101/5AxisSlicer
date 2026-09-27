"""Analytic independent targets for finite-width FAN measurement."""

import math

import pytest

from five_axis_slicer.algorithms.planar.region import PlanarRegion
from five_axis_slicer.validation.fan_coverage import BeadSegment, measure_chart_coverage


def _loop(x0, y0, x1, y1):
    return ((x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0), (x0, y0, 0))


def _lines(ys):
    return tuple(BeadSegment((-1, y), (5, y), 0.4, str(i)) for i, y in enumerate(ys))


@pytest.mark.parametrize("grid", [0.08, 0.04, 0.02])
def test_missing_strip_has_analytic_area_and_empty_disk(grid):
    region = PlanarRegion("rectangle", _loop(0, 0, 4, 2))
    complete = _lines((0.2, 0.6, 1.0, 1.4, 1.8))
    full = measure_chart_coverage(region, complete, grid_mm=grid)
    assert full.covered_area_mm2 == pytest.approx(8)
    assert full.overlapping_strokes_area_mm2 == pytest.approx(0)
    missing = measure_chart_coverage(region, complete[:2] + complete[3:], grid_mm=grid)
    assert missing.sampled_area_mm2 - missing.covered_area_mm2 == pytest.approx(1.6, abs=8 * grid)
    assert missing.empty_disk_diameter_lower_mm <= 0.4 + 1e-12
    assert missing.empty_disk_diameter_upper_mm >= 0.4 - 1e-12
    assert (
        missing.empty_disk_diameter_upper_mm - missing.empty_disk_diameter_lower_mm
        <= math.sqrt(2) * grid + 1e-12
    )


def test_hole_is_not_missing_material_and_split_stroke_is_not_overlap():
    region = PlanarRegion("ring", _loop(0, 0, 4, 2), (_loop(1, 0.8, 3, 1.2),))
    lines = _lines((0.2, 0.6, 1.0, 1.4, 1.8))
    split = (
        BeadSegment((-1, 0.2), (2, 0.2), 0.4, "0"),
        BeadSegment((2, 0.2), (5, 0.2), 0.4, "0"),
        *lines[1:],
    )
    result = measure_chart_coverage(region, split, grid_mm=0.02)
    assert result.sampled_area_mm2 == pytest.approx(7.2)
    assert result.covered_area_mm2 == pytest.approx(7.2)
    assert result.overlapping_strokes_area_mm2 == 0
    # The hole is excluded from target coverage, but material crossing it is
    # still counted as outside, in addition to the deliberate long line ends.
    solid = measure_chart_coverage(PlanarRegion("solid", region.outer), split, grid_mm=0.02)
    assert result.outside_area_mm2 - solid.outside_area_mm2 == pytest.approx(0.8)
    assert result.unsupported_area_mm2 is None


def test_no_paths_and_duplicated_paths_are_measured():
    region = PlanarRegion("rectangle", _loop(0, 0, 4, 2))
    empty = measure_chart_coverage(region, (), grid_mm=0.02)
    assert empty.empty_disk_diameter_lower_mm <= 2 <= empty.empty_disk_diameter_upper_mm
    assert empty.deposited_sample_count == 0
    lines = _lines((0.2, 0.6, 1.0, 1.4, 1.8))
    duplicate = tuple(BeadSegment(s.start, s.end, s.width_mm, "copy" + s.stroke_id) for s in lines)
    result = measure_chart_coverage(region, lines + duplicate, grid_mm=0.02)
    assert result.overlapping_strokes_area_mm2 == pytest.approx(8)


def test_radial_projection_preserves_previous_physical_width():
    region = PlanarRegion("patch", _loop(0, 0, 2, 1))
    current = (BeadSegment((1.5, -1), (1.5, 2), 0.4, "current"),)
    previous = (BeadSegment((1, -1), (1, 2), 0.4, "previous"),)
    kwargs = dict(grid_mm=0.02, current_radius_mm=3, previous_radius_mm=2, layer_height_mm=1)
    supported = measure_chart_coverage(region, current, previous_segments=previous, **kwargs)
    # Boundary cells need not align after extending the grid to include caps.
    assert supported.covered_area_mm2 == pytest.approx(0.4, abs=2.8 * math.sqrt(2) * 0.02)
    assert supported.unsupported_area_mm2 == 0
    unsupported = measure_chart_coverage(region, current, previous_segments=(), **kwargs)
    assert unsupported.unsupported_area_mm2 == pytest.approx(unsupported.covered_area_mm2)
    with pytest.raises(ValueError, match="nonadjacent"):
        measure_chart_coverage(
            region, current, previous_segments=previous, **{**kwargs, "layer_height_mm": 0.2}
        )
