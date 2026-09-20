import math

import cadquery as cq
import pytest

from five_axis_slicer.algorithms.freeform.spherical_domain import SphericalChart, spherical_section


def test_chart_metric_and_nonzero_center():
    chart = SphericalChart((4, -5, 6))
    p = (6, 0, 10)
    assert chart.lift(p) == pytest.approx((10, -5, 14))
    assert chart.project(chart.lift(p), 10) == pytest.approx(p)
    assert chart.normal(p) == pytest.approx((0.6, 0, 0.8))
    assert chart.area_scale(p) == pytest.approx(1.25)
    assert chart.tangent_length(p, 1, 0) == pytest.approx(1.25)
    assert chart.tangent_length(p, 0, 1) == pytest.approx(1)


@pytest.mark.parametrize("point", [(10, 0, 10), (0, 0, 0), (float("nan"), 0, 10)])
def test_chart_rejects_singular_or_invalid_input(point):
    with pytest.raises(ValueError):
        SphericalChart().lift(point)


def test_solid_sphere_section_keeps_real_hole():
    solid = cq.Workplane("XY").circle(3).circle(1).extrude(12).val()
    layer = spherical_section(solid.wrapped, 10, sample_segments=256)
    assert len(layer.regions) == 1
    region = layer.regions[0]
    assert len(region.holes) == 1
    for loop, radius in [(region.outer, 3), (region.holes[0], 1)]:
        for p in loop:
            # Same 0.001 mm section budget enforced by the domain, not exact CAD arithmetic.
            assert math.hypot(p[0], p[1]) == pytest.approx(radius, abs=0.001)
            source = SphericalChart().lift(p)
            assert sum(v * v for v in source) == pytest.approx(100)
    def area(loop):
        return abs(sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(loop, loop[1:])) / 2)
    assert area(region.outer) - area(region.holes[0]) == pytest.approx(8 * math.pi, rel=0.001)
    measured = sum(
        SphericalChart().signed_surface_area(loop) for loop in (region.outer, *region.holes)
    )
    assert measured == pytest.approx(20 * math.pi * (math.sqrt(99) - math.sqrt(91)), rel=0.001)


def test_spherical_cap_surface_area_matches_independent_closed_form():
    chart = SphericalChart()
    count = 10000
    dr = 6 / count
    measured = sum(
        2 * math.pi * ((i + 0.5) * dr) * dr * chart.area_scale(((i + 0.5) * dr, 0, 10))
        for i in range(count)
    )
    # Cap height is 2 mm: exact area 2*pi*R*h; projected area would be 36*pi.
    assert measured == pytest.approx(40 * math.pi, rel=1e-8)
