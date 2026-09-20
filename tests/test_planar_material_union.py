"""Analytic area oracles for positive solids and genuine voids."""

import cadquery as cq
import pytest

from five_axis_slicer.algorithms.planar.region import slice_planar_layers
from five_axis_slicer.step_loader import load_step


@pytest.mark.parametrize("offset,expected", [(0, 100), (4, 104), (7, 116), (10, 116)])
def test_positive_solid_union(tmp_path, offset, expected):
    outer = cq.Workplane("XY").box(10, 10, 2).val()
    other = cq.Workplane("XY").box(4, 4, 2).translate((offset, 0, 0)).val()
    assert _section_area(tmp_path, [outer, other]) == pytest.approx(expected)


@pytest.mark.parametrize("island,expected", [(False, 64), (True, 68)])
def test_real_hole_and_positive_island(tmp_path, island, expected):
    ring = cq.Workplane("XY").box(10, 10, 2).cut(cq.Workplane("XY").box(6, 6, 4)).val()
    bodies = [ring]
    if island:
        bodies.append(cq.Workplane("XY").box(2, 2, 2).val())
    assert _section_area(tmp_path, bodies) == pytest.approx(expected)


def test_concave_disjoint_body_is_not_a_hole(tmp_path):
    u_shape = (
        cq.Workplane("XY")
        .box(10, 10, 2)
        .cut(cq.Workplane("XY").box(9, 10, 4).translate((0, 0.5, 0)))
        .val()
    )
    island = cq.Workplane("XY").box(6, 6, 2).val()
    # U area = 100 - 9*9.5; the separate square occupies its open notch.
    assert _section_area(tmp_path, [u_shape, island]) == pytest.approx(50.5)


def _section_area(tmp_path, bodies):
    source = tmp_path / "materials.step"
    cq.exporters.export(cq.Compound.makeCompound(bodies), str(source))
    model = load_step(source)
    layers = slice_planar_layers(
        model,
        tuple(b.body_id for b in model.bodies),
        first_layer_z_mm=0.2,
        last_layer_z_mm=0.2,
        layer_height_mm=0.2,
    )

    def area(loop):
        return abs(sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(loop, loop[1:])) / 2)

    return sum(area(r.outer) - sum(area(h) for h in r.holes) for r in layers[0].regions)
