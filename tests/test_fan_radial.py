from __future__ import annotations

import math
from pathlib import Path

import cadquery as cq
import pytest

from five_axis_slicer.algorithms.fan.program import generate_single_blade_plan
from five_axis_slicer.algorithms.fan.radial import (
    chart_to_source,
    cylindrical_section,
    radial_blade_domain,
    sample_chart_segment,
)
from five_axis_slicer.algorithms.planar.region import _area


def _sector():
    ring = cq.Workplane("XY").circle(12).circle(10).extrude(2).val()
    quadrant = cq.Workplane("XY").box(20, 20, 2, centered=(False, False, False)).val()
    return ring.intersect(quadrant).wrapped


def test_cylindrical_section_has_independent_quarter_cylinder_area():
    layer = cylindrical_section(_sector(), 11, seam_center_rad=math.pi / 4)
    assert len(layer.regions) == 1
    # Quarter circumference times axial thickness, independent analytic area.
    assert _area(layer.regions[0].outer) == pytest.approx(11 * math.pi, rel=1e-5)
    assert all(
        math.hypot(*chart_to_source(p)[:2]) == pytest.approx(11) for p in layer.regions[0].outer
    )


def test_radial_growth_starts_at_substrate_and_is_not_qualified():
    hub = cq.Workplane("XY").circle(10).extrude(2).val().wrapped
    domain = radial_blade_domain(
        _sector(), hub, substrate_radius_mm=10, last_radius_mm=11, layer_height_mm=0.2
    )
    assert [layer.z_mm for layer in domain.layers] == pytest.approx([10.2, 10.4, 10.6, 10.8, 11])
    assert domain.unsupported_root_sample_count == 0
    assert not domain.manufacturing_qualified


def test_wrong_substrate_is_rejected():
    hub = cq.Workplane("XY").circle(9).extrude(2).val().wrapped
    with pytest.raises(ValueError, match="root_not_on_substrate"):
        radial_blade_domain(_sector(), hub, substrate_radius_mm=10, last_radius_mm=11)


def test_arc_subdivision_does_not_cut_through_hub():
    points = sample_chart_segment((0, 1, 10.2), (math.pi * 10.2 / 2, 1, 10.2))
    # Closest radius of each chord: here its midpoint, with equal-radius endpoints.
    assert (
        min(math.hypot((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(points, points[1:]))
        > 10
    )
    assert points[-1] == pytest.approx((0, 10.2, 1))


def test_withdrawn_planar_generator_cannot_publish_more_blades():
    with pytest.raises(ValueError, match="strategy_withdrawn"):
        generate_single_blade_plan(None, None)


def test_real_fan_root_and_periodic_cylinder_section_regression():
    from five_axis_slicer.step_loader import load_step

    source = Path(__file__).resolve().parents[1] / "example/扇叶/风扇扇叶(1).STEP"
    model = load_step(source)
    domain = radial_blade_domain(
        model.shapes["body_001"],
        model.shapes["body_004"],
        substrate_radius_mm=17.5,
        last_radius_mm=17.7,
    )
    assert domain.root_sample_count == 768
    assert domain.unsupported_root_sample_count == 0
    section = cylindrical_section(model.shapes["body_001"], 75.7)
    assert len(section.regions) == 1
    assert _area(section.regions[0].outer) > 100
    for point in section.regions[0].outer:
        assert math.hypot(*chart_to_source(point)[:2]) == pytest.approx(75.7, abs=0.001)


@pytest.mark.parametrize("radius", [75.7, 82.3, 82.5, 82.7, 83.1, 83.3])
def test_repaired_section_endpoints_stay_on_independent_cad_boundary(radius):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt
    from five_axis_slicer.step_loader import load_step

    model = load_step(Path("example/扇叶/风扇扇叶(1).STEP"))
    shape = model.shapes["body_001"]
    section = cylindrical_section(shape, radius)
    shell = cq.Shape.cast(shape).Shells()[0].wrapped
    # The polyline retains 128 samples per OCCT edge. Check every joint and
    # edge midpoint against the shell, not the solid (inside distance is zero).
    for point in section.regions[0].outer[::64]:
        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*chart_to_source(point))).Vertex()
        distance = BRepExtrema_DistShapeShape(vertex, shell)
        assert distance.IsDone() and distance.Value() < 0.005


@pytest.mark.parametrize("radius", [46.7, 81.5, 82.1, 83.3])
def test_dense_chart_offset_failure_is_not_mislabelled_as_thin_wall(radius):
    from five_axis_slicer.step_loader import load_step
    from five_axis_slicer.algorithms.fan.chart_fill import radial_feature_fill
    from five_axis_slicer.algorithms.planar.feature_fill import FeatureFillParameters

    model = load_step(Path("example/扇叶/风扇扇叶(1).STEP"))
    section = cylindrical_section(model.shapes["body_001"], radius)
    plans = radial_feature_fill((section,), FeatureFillParameters(infill_fraction=1))
    assert len(plans[0].regions[0].wall_contours) == 2
    assert plans[0].regions[0].infill_segments
