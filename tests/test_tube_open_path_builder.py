import json

import pytest

from five_axis_slicer.algorithms.tube.indexed import TubeSliceLayer, _PathBuilder
from five_axis_slicer.manufacturing.setup import TubeProcessParameters
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath
from five_axis_slicer.manufacturing.tube_tcp import indexed_centerline_to_tcp
from five_axis_slicer.indexed_preview_metadata import indexed_preview_comments


def test_open_variable_paths_preserve_volumes_heights_and_nonextruding_connections():
    builder = _PathBuilder("op", TubeProcessParameters())
    layer = TubeSliceLayer("l", "r", 0.1, (0, 0, 0), (0, 0, 1), 0.2)
    def loop(x):
        return (((x, 0, 0.05), (1, 0, 0), (0, 1, 0)),
                ((x + 1, 0, 0.15), (1, 0, 0), (0, 1, 0)))
    for x in (0, 3):
        builder.add_layer(layer, loop(x), indexed=False, heights_mm=(0.1, 0.3),
                          widths_mm=(0.45, 0.55), segment_volumes_mm3=(0.123,))
    points = builder.points
    assert [p.point_type for p in points] == ["approach", "deposition", "depart", "travel", "approach", "deposition"]
    assert sum(p.material_volume_mm3 for p in points) == pytest.approx(0.246)
    assert [p.layer_height_mm for p in points] == [0.1, 0.3, None, 0.1, 0.1, 0.3]
    tcp = indexed_centerline_to_tcp(GeneratedToolpath("p", "op", points=tuple(points)))
    assert tcp.points[0].position[2] == pytest.approx(0.1)
    assert tcp.points[1].position[2] == pytest.approx(0.3)
    assert points[-1].position != points[0].position
    comments = indexed_preview_comments(GeneratedToolpath("p", "op", points=tuple(points)))
    widths = [json.loads(c.split(" ", 2)[2])["width_mm"] for c in comments]
    assert widths == [0.45, 0.55, 0.55, 0.45, 0.45, 0.55]


def test_variable_height_requires_integrated_volume_before_mutating_builder():
    builder = _PathBuilder("op", TubeProcessParameters())
    layer = TubeSliceLayer("l", "r", 0.1, (0, 0, 0), (0, 0, 1), 0.2)
    loop = (((0, 0, 0), (1, 0, 0), (0, 1, 0)), ((1, 0, 0), (1, 0, 0), (0, 1, 0)))
    with pytest.raises(ValueError, match="integrated"):
        builder.add_layer(layer, loop, indexed=False, heights_mm=(0.1, 0.3))
    assert builder.points == []
    assert builder.events == []
