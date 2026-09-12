from pathlib import Path
import sys

import cadquery as cq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.planar.region import PlanarSectionError, slice_planar_layers
from five_axis_slicer.manufacturing.coordinates import RigidTransform
from five_axis_slicer.models import BoundingBox, CadModel


def _model(shape):
    return CadModel(
        Path("planar.step"),
        "a" * 64,
        [],
        [],
        {"body": shape.val().wrapped},
        {},
        bounds=BoundingBox((0, 0, 0), (40, 20, 10)),
    )


def test_sections_keep_islands_and_holes_separate():
    outer = cq.Workplane("XY").box(20, 20, 10)
    hole = cq.Workplane("XY").cylinder(12, 3).translate((0, 0, -1))
    island = cq.Workplane("XY").box(2, 2, 10).translate((30, 0, 0))
    model = _model(outer.cut(hole).union(island))
    layer = slice_planar_layers(
        model, ("body",), first_layer_z_mm=5, layer_height_mm=1, last_layer_z_mm=5
    )[0]
    assert len(layer.regions) == 2
    assert sorted(len(region.holes) for region in layer.regions) == [0, 1]


def test_missing_body_and_invalid_layer_height_are_localised():
    model = _model(cq.Workplane("XY").box(2, 2, 2))
    with pytest.raises(PlanarSectionError, match="planar.body_missing"):
        slice_planar_layers(model, ("none",), first_layer_z_mm=0, layer_height_mm=1)
    with pytest.raises(PlanarSectionError, match="planar.layer_height_invalid"):
        slice_planar_layers(model, ("body",), first_layer_z_mm=0, layer_height_mm=0)


def test_sections_follow_build_coordinate_system_and_return_build_coordinates():
    shape = cq.Workplane("XY").box(6, 4, 4).translate((10, 0, 8))
    model = _model(shape)
    transform = RigidTransform.from_translation(
        (10, 0, 8), source_frame="build", target_frame="model"
    )

    layer = slice_planar_layers(
        model,
        ("body",),
        first_layer_z_mm=0,
        layer_height_mm=1,
        last_layer_z_mm=0,
        T_model_from_build=transform,
    )[0]

    assert len(layer.regions) == 1
    assert {round(point[2], 9) for point in layer.regions[0].outer} == {0.0}
    xs = [point[0] for point in layer.regions[0].outer]
    assert min(xs) == pytest.approx(-3.0)
    assert max(xs) == pytest.approx(3.0)
