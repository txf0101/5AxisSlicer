import math

import cadquery as cq
import pytest

from five_axis_slicer.algorithms.freeform.spherical_fill import (
    SphericalFillParameters,
    generate_spherical_solid_fill,
)
from five_axis_slicer.step_loader import load_step


def test_spherical_fill_has_complete_layers_spacing_normals_and_root_contact(tmp_path):
    base = cq.Workplane("XY").sphere(10)
    raised = (
        cq.Workplane("XY")
        .sphere(10.6)
        .intersect(cq.Workplane("XY").box(8, 6, 20).translate((0, 0, 5)))
        .cut(cq.Workplane("XY").sphere(10))
    )
    source = tmp_path / "raised.step"
    cq.exporters.export(cq.Compound.makeCompound([base.val(), raised.val()]), str(source))
    model = load_step(source)
    path, audit = generate_spherical_solid_fill(
        model,
        ("body_002",),
        "logo",
        SphericalFillParameters(10, 0.6, layer_height_mm=0.2, bead_width_mm=0.4),
    )
    deposits = [point for point in path.points if point.point_type == "deposition"]
    assert audit.layer_count == 3 and audit.bodies_per_layer == (1, 1, 1)
    assert audit.maximum_cross_path_spacing_mm <= 0.4 + 1e-9
    assert audit.first_layer_root_gap_mm == pytest.approx(0)
    assert {point.extrusion_role for point in deposits} == {"skin", "infill"}
    assert {point.layer_id for point in deposits} == {
        "sphere-layer-001",
        "sphere-layer-002",
        "sphere-layer-003",
    }
    assert min(math.dist(point.position, (0, 0, 0)) for point in deposits) == pytest.approx(10.2)
    assert max(math.dist(point.position, (0, 0, 0)) for point in deposits) == pytest.approx(10.6)
    for point in deposits[:: max(1, len(deposits) // 50)]:
        normal = tuple(value / math.dist(point.position, (0, 0, 0)) for value in point.position)
        assert point.surface_normal == pytest.approx(normal)
        assert point.nozzle_axis == pytest.approx(tuple(-v for v in normal))


def test_spherical_fill_rejects_duplicate_or_unknown_bodies(tmp_path):
    source = tmp_path / "sphere.step"
    cq.exporters.export(cq.Workplane("XY").sphere(10), str(source))
    model = load_step(source)
    parameters = SphericalFillParameters(9, 1)
    with pytest.raises(ValueError, match="unique"):
        generate_spherical_solid_fill(model, ("body_001", "body_001"), "op", parameters)
    with pytest.raises(ValueError, match="unknown"):
        generate_spherical_solid_fill(model, ("missing",), "op", parameters)
