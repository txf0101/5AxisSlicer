"""Independent geometric checks for the Indexed centerline/TCP boundary."""

from dataclasses import replace
import math

import pytest

from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from five_axis_slicer.manufacturing.tube_tcp import indexed_centerline_to_tcp


def point(i, kind, height=None, axis=(0, 0, -1), layer="l1"):
    return ToolpathPoint(
        point_id=f"p{i}",
        position=(0, 0, 5.1),
        tangent=(1, 0, 0),
        nozzle_axis=axis,
        operation_id="op",
        stage_id="s",
        layer_id=layer,
        region_id="r",
        point_type=kind,
        extrusion_role="thin_wall" if kind == "deposition" else "none",
        layer_height_mm=height,
        bead_width_mm=0.6 if kind == "deposition" else None,
        material_volume_mm3=0.12 if kind == "deposition" else 0,
    )


def path(points):
    return GeneratedToolpath(
        "t",
        "op",
        points=tuple(points),
        events=(ToolpathEvent("e", "prime", "op", "s", context={"sequence_index": 1}),),
    )


def test_horizontal_first_layer_and_metadata():
    source = path([point(0, "approach"), point(1, "deposition", 0.2)])
    tcp = indexed_centerline_to_tcp(source)
    assert all(p.position == pytest.approx((0, 0, 5.2)) for p in tcp.points)
    assert source.points[1].position == (0, 0, 5.1)
    assert tcp.events == source.events
    for old, new in zip(source.points, tcp.points):
        assert replace(new, position=old.position) == old


def test_tilted_layer_offset_is_along_nozzle_axis():
    axis = (0, -math.sqrt(0.5), -math.sqrt(0.5))
    tcp = indexed_centerline_to_tcp(
        path(
            [
                point(0, "approach", axis=axis),
                point(1, "deposition", 0.2, axis),
            ]
        )
    )
    assert tcp.points[1].position == pytest.approx(
        (0, math.sqrt(0.5) * 0.1, 5.1 + math.sqrt(0.5) * 0.1)
    )


def test_variable_segment_approach_preserves_its_own_start_height():
    source = path([point(0, "approach", 0.1), point(1, "deposition", 0.3)])
    tcp = indexed_centerline_to_tcp(source)
    assert tcp.points[0].position[2] == pytest.approx(5.15)
    assert tcp.points[1].position[2] == pytest.approx(5.25)


def test_depart_uses_previous_height_despite_next_layer_label():
    source = path(
        [
            point(0, "approach"),
            point(1, "deposition", 0.2),
            point(2, "depart", layer="l2"),
            point(3, "travel", layer="l2"),
            point(4, "approach", layer="l2"),
            point(5, "deposition", 0.4, layer="l2"),
        ]
    )
    tcp = indexed_centerline_to_tcp(source)
    assert [p.position[2] for p in tcp.points] == pytest.approx([5.2, 5.2, 5.2, 5.3, 5.3, 5.3])


@pytest.mark.parametrize(
    "points",
    [
        [],
        [point(0, "approach")],
        [point(0, "travel"), point(1, "deposition", 0.2)],
        [point(0, "approach"), point(1, "deposition")],
        [point(0, "approach"), point(1, "deposition", 0.2), point(2, "retract")],
    ],
)
def test_unsupported_or_incomplete_connections_fail(points):
    with pytest.raises(ValueError):
        indexed_centerline_to_tcp(path(points))
