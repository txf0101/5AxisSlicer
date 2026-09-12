"""Analytical truth for the audit's perimeter and overfill failures."""

from dataclasses import replace
import math

import pytest

from five_axis_slicer.algorithms.planar import (
    PlanarRegion,
    PlanarSliceLayer,
    ZigzagParameters,
    generate_zigzag_toolpath,
)
from five_axis_slicer.validation.planar import measure_planar_toolpath
from five_axis_slicer.validation.planar_qualification import measurement_issues, solid_volume_issues


def _rectangle():
    region = PlanarRegion("r", ((0, 0, 0.5), (8, 0, 0.5), (8, 6, 0.5), (0, 6, 0.5), (0, 0, 0.5)))
    return (PlanarSliceLayer("l", 0.5, (region,)),)


def test_half_bead_inset_has_independent_exact_box_volume():
    layers = _rectangle()
    path = generate_zigzag_toolpath("op", layers, ZigzagParameters(0.6, 0.6, 0.5))
    skin = [p for p in path.points if p.extrusion_role == "skin"]
    assert min(p.position[0] for p in skin) == pytest.approx(0.3)
    assert max(p.position[0] for p in skin) == pytest.approx(7.7)
    assert min(p.position[1] for p in skin) == pytest.approx(0.3)
    assert max(p.position[1] for p in skin) == pytest.approx(5.7)
    measurement = measure_planar_toolpath(path, layers, grid_mm=0.05)
    assert measurement.target_solid_volume_mm3 == pytest.approx(8 * 6 * 0.5)
    assert measurement.material_volume_mm3 == pytest.approx(24)
    assert measurement.geometric_region_area_mm2 == pytest.approx(48)
    assert measurement.bead_outside_max_mm <= 1e-8
    assert measurement.residual_area_mm2 < 0.25
    assert not measurement_issues(measurement)
    assert not solid_volume_issues(measurement, layers, 0.5)


def test_original_boundary_centreline_and_self_consistent_e_do_not_qualify_bead():
    layers = _rectangle()
    path = generate_zigzag_toolpath("op", layers, ZigzagParameters(0.6, 0.6, 0.5))
    points = path.points[:5]
    positions = layers[0].regions[0].outer
    changed = tuple(
        replace(
            p,
            position=xyz,
            material_volume_mm3=(0 if i == 0 else math.dist(positions[i - 1], xyz) * 0.6 * 0.5),
        )
        for i, (p, xyz) in enumerate(zip(points, positions))
    )
    bad = replace(path, points=changed, events=())
    m = measure_planar_toolpath(bad, layers)
    assert m.deposition_outside_max_mm == pytest.approx(0)
    assert m.volume_difference_mm3 == pytest.approx(0)
    assert m.bead_outside_max_mm == pytest.approx(0.3)
    assert "planar.bead_envelope_outside_region" in {i.code for i in measurement_issues(m)}


def test_dense_overlapping_hatches_cannot_exceed_full_solid_volume():
    layers = _rectangle()
    path = generate_zigzag_toolpath("op", layers, ZigzagParameters(0.2, 0.6, 0.5))
    m = measure_planar_toolpath(path, layers)
    assert m.overlap_area_mm2 > 20
    assert m.material_excess_mm3 > 30
    assert solid_volume_issues(m, layers, 0.5)[0].code == "planar.material_exceeds_solid_volume"


@pytest.mark.parametrize("grid", [0, -1, float("inf"), float("nan")])
def test_invalid_sampling_grid_is_rejected(grid):
    layers = _rectangle()
    path = generate_zigzag_toolpath("op", layers, ZigzagParameters(0.6, 0.6, 0.5))
    with pytest.raises(ValueError, match="measurement_grid_invalid"):
        measure_planar_toolpath(path, layers, grid_mm=grid)


def test_missing_provenance_cannot_silently_drop_material():
    path = generate_zigzag_toolpath("op", _rectangle(), ZigzagParameters(0.6, 0.6, 0.5))
    with pytest.raises(ValueError, match="measurement_region_missing"):
        measure_planar_toolpath(path, ())


def test_underfilled_island_cannot_hide_narrow_region_overfill():
    narrow = PlanarRegion(
        "narrow", ((0, 0, 0.5), (1, 0, 0.5), (1, 6, 0.5), (0, 6, 0.5), (0, 0, 0.5))
    )
    large = PlanarRegion(
        "large", ((5, 0, 0.5), (25, 0, 0.5), (25, 20, 0.5), (5, 20, 0.5), (5, 0, 0.5))
    )
    layers = (PlanarSliceLayer("l", 0.5, (narrow, large)),)
    path = generate_zigzag_toolpath("op", layers, ZigzagParameters(20, 0.6, 0.5))
    measurement = measure_planar_toolpath(path, layers)
    assert measurement.material_excess_mm3 == 0
    issues = solid_volume_issues(measurement, layers, 0.5)
    assert len(issues) == 1
    assert issues[0].context["region_id"] == "narrow"


def test_opposite_material_errors_cannot_cancel_between_regions():
    region = _rectangle()[0].regions[0]
    other = replace(
        region, region_id="other", outer=tuple((x + 12, y, z) for x, y, z in region.outer)
    )
    layers = (PlanarSliceLayer("l", 0.5, (region, other)),)
    path = generate_zigzag_toolpath("op", layers, ZigzagParameters(0.6, 0.6, 0.5))
    path = replace(
        path,
        points=tuple(
            replace(
                p, material_volume_mm3=p.material_volume_mm3 * (1.5 if p.region_id == "r" else 0.5)
            )
            for p in path.points
        ),
    )
    m = measure_planar_toolpath(path, layers)
    assert m.volume_difference_mm3 == pytest.approx(0)
    assert m.absolute_volume_difference_mm3 == pytest.approx(24)
    assert "planar.material_volume_mismatch" in {i.code for i in measurement_issues(m)}
    issues = solid_volume_issues(m, layers, 0.5)
    assert issues[0].context["region_id"] == "r"
    assert issues[0].context["commanded_mm3"] == pytest.approx(36)
