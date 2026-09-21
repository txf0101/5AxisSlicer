"""Independent CAD substrate shape and process checks."""

import cadquery as cq
import pytest

from five_axis_slicer.algorithms.planar.feature_toolpath import FeatureToolpathParameters
from five_axis_slicer.algorithms.planar.substrate import generate_substrate_toolpath
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.algorithms.tube.geometry import manual_tube_feature
from five_axis_slicer.algorithms.tube.buildup import TubeBuildupParameters
from five_axis_slicer.manufacturing.coordinates import GeometryReference
from five_axis_slicer.manufacturing.setup import TubeGeometrySelection, TubeOperationDefinition
from five_axis_slicer.postprocessing.tube_product import _cad_substrate_toolpath


def test_rectangular_substrate_preserves_hole_and_corners(tmp_path):
    solid = cq.Workplane("XY").rect(20, 12).rect(4, 4).extrude(1.05)
    source = tmp_path / "substrate.step"
    cq.exporters.export(solid, str(source))
    model = load_step(source)
    path = generate_substrate_toolpath(
        model, model.bodies[0].body_id, "base", FeatureToolpathParameters()
    )
    deposited = [p for p in path.points if p.point_type == "deposition"]
    assert len({p.layer_id for p in deposited}) == 6
    assert max(p.position[2] for p in deposited) == pytest.approx(1.05)
    assert {round(p.layer_height_mm, 6) for p in deposited} == {0.175}
    # An inscribed bounding disk would omit these rectangular corner paths.
    assert any(abs(p.position[0]) > 9 and abs(p.position[1]) > 5 for p in deposited)
    for a, b in zip(path.points, path.points[1:]):
        if b.point_type != "deposition":
            continue
        for t in (0, 0.25, 0.5, 0.75, 1):
            x, y, _ = (a.position[i] * (1 - t) + b.position[i] * t for i in range(3))
            assert not (abs(x) < 2 and abs(y) < 2), "deposition crosses the real hole"
            assert abs(x) <= 9.801 and abs(y) <= 5.801


def test_missing_substrate_cad_is_rejected(tmp_path):
    source = tmp_path / "base.step"
    cq.exporters.export(cq.Workplane("XY").box(10, 10, 1), str(source))
    model = load_step(source)
    with pytest.raises(ValueError, match="no CAD shape"):
        generate_substrate_toolpath(model, "missing", "base", FeatureToolpathParameters())


def test_hemisphere_apex_has_a_real_final_slab(tmp_path):
    import math

    solid = (
        cq.Workplane("XY")
        .sphere(4)
        .intersect(cq.Workplane("XY").box(10, 10, 4, centered=(True, True, False)))
    )
    source = tmp_path / "hemisphere.step"
    cq.exporters.export(solid, str(source))
    model = load_step(source)
    path = generate_substrate_toolpath(
        model, model.bodies[0].body_id, "sphere-base", FeatureToolpathParameters()
    )
    deposits = [p for p in path.points if p.point_type == "deposition"]
    top = max(p.position[2] for p in deposits)
    assert top == pytest.approx(4, abs=1e-6)
    cap = [p for p in deposits if abs(p.position[2] - top) < 1e-7]
    assert cap and sum(p.material_volume_mm3 for p in cap) > 0
    height = cap[0].layer_height_mm
    # Independent spherical section at the middle of the last slab.
    radius = math.sqrt(16 - (4 - height / 2) ** 2)
    assert max(math.hypot(*p.position[:2]) for p in cap) <= radius - 0.2 + 0.005
    assert min(p.position[2] for p in deposits) == pytest.approx(height, abs=1e-6)


@pytest.mark.parametrize("direction", [(0, 0, 1), (1, 0, 0)])
def test_product_substrate_uses_cad_and_rejects_unestablished_pose(tmp_path, direction):
    source = tmp_path / "product-base.step"
    cq.exporters.export(cq.Workplane("XY").rect(20, 12).rect(4, 4).extrude(1), str(source))
    model = load_step(source)
    operation = TubeOperationDefinition(
        "tube",
        "setup",
        geometry=TubeGeometrySelection(
            substrate_body=GeometryReference(model.bodies[0].body_id, "body")
        ),
    )
    feature = manual_tube_feature(
        ((5, 0, 1), tuple(5 * (i == 0) + (i == 2) + direction[i] for i in range(3))),
        outer_radius_mm=2,
        inner_radius_mm=1,
    )
    if direction != (0, 0, 1):
        with pytest.raises(ValueError, match="explicit \\+Z"):
            _cad_substrate_toolpath(model, operation, feature, TubeBuildupParameters())
    else:
        path = _cad_substrate_toolpath(model, operation, feature, TubeBuildupParameters())
        assert path.operation_id == "tube-planar-base"
        assert any(abs(p.position[0]) > 9 for p in path.points if p.point_type == "deposition")
