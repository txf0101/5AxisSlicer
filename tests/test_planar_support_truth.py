"""Hand-derived P07 truths independent of the support implementation formulae."""

from dataclasses import replace
import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.planar import (  # noqa: E402
    PlanarRegion,
    PlanarSliceLayer,
    PlanarSupportError,
    SupportLayer,
    SupportParameters,
    SupportPlan,
    generate_support_plan,
    generate_support_toolpath,
)


def _rectangle(region_id: str, z_mm: float, x0: float, y0: float, x1: float, y1: float):
    return PlanarRegion(
        region_id,
        (
            (x0, y0, z_mm),
            (x1, y0, z_mm),
            (x1, y1, z_mm),
            (x0, y1, z_mm),
            (x0, y0, z_mm),
        ),
    )


def _polygon_area(region: PlanarRegion) -> float:
    """Shoelace measurement deliberately independent of the OCCT helpers."""

    def loop_area(loop) -> float:
        return (
            abs(
                sum(
                    left[0] * right[1] - right[0] * left[1]
                    for left, right in zip(loop, loop[1:], strict=False)
                )
            )
            / 2.0
        )

    return loop_area(region.outer) - sum(loop_area(hole) for hole in region.holes)


def _bounds(region: PlanarRegion) -> tuple[float, float, float, float]:
    points = region.outer[:-1]
    return (
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    )


def _cantilever_layers() -> tuple[PlanarSliceLayer, ...]:
    layers = []
    for index in range(5):
        layers.append(
            PlanarSliceLayer(
                f"L{index}",
                float(index),
                (_rectangle("part", float(index), 0.0, 0.0, 4.0, 4.0),),
            )
        )
    layers.append(PlanarSliceLayer("L5", 5.0, (_rectangle("part", 5.0, 0.0, 0.0, 8.0, 4.0),)))
    return tuple(layers)


def _truth_parameters(pattern: str) -> SupportParameters:
    return SupportParameters(
        layer_height_mm=1.0,
        overhang_angle_rad=math.atan(0.5),
        xy_gap_mm=1.0,
        z_gap_mm=1.1,
        interface_layers=1,
        line_spacing_mm=1.0,
        interface_spacing_mm=0.5,
        bead_width_mm=0.4,
        pattern=pattern,
    )


def _deposition_segments(path):
    return tuple(
        (current.layer_id, current.stage_id, previous.position, current.position)
        for previous, current in zip(path.points, path.points[1:], strict=False)
        if current.point_type == "deposition"
    )


def _assert_segments(actual, expected) -> None:
    assert len(actual) == len(expected)
    for observed, truth in zip(actual, expected, strict=True):
        assert observed[:2] == truth[:2]
        assert observed[2] == pytest.approx(truth[2], abs=1.0e-7)
        assert observed[3] == pytest.approx(truth[3], abs=1.0e-7)


def test_hand_derived_threshold_xy_z_gap_and_support_stages() -> None:
    layers = _cantilever_layers()
    parameters = _truth_parameters("lines")

    plan = generate_support_plan(layers, parameters)

    # At atan(0.5), the upper layer may grow 0.5 mm from the prior wall.
    # The raw 3.5 x 4 overhang is 14 mm2.  A 1 mm XY gap leaves a fixed
    # 3 x 4 support column.  A 1.1 mm Z gap consumes two whole layers.
    assert plan.unsupported_area_mm2 == pytest.approx(14.0)
    assert not plan.diagnostics
    expected = (
        ("body", 0.0, 12.0, (5.0, 0.0, 8.0, 4.0)),
        ("body", 1.0, 12.0, (5.0, 0.0, 8.0, 4.0)),
        ("interface", 2.0, 12.0, (5.0, 0.0, 8.0, 4.0)),
        ("empty", 3.0, 0.0, None),
        ("empty", 4.0, 0.0, None),
        ("empty", 5.0, 0.0, None),
    )
    observed = []
    for layer in plan.layers:
        regions = (*layer.body_regions, *layer.interface_regions)
        stage = (
            "body" if layer.body_regions else "interface" if layer.interface_regions else "empty"
        )
        area = sum(_polygon_area(region) for region in regions)
        bounds = _bounds(regions[0]) if regions else None
        observed.append((stage, layer.z_mm, area, bounds))
    for result, truth in zip(observed, expected, strict=True):
        assert result[:2] == truth[:2]
        assert result[2] == pytest.approx(truth[2], abs=1.0e-7)
        if truth[3] is None:
            assert result[3] is None
        else:
            assert result[3] == pytest.approx(truth[3], abs=1.0e-7)

    steeper_allowance = generate_support_plan(
        layers,
        replace(parameters, overhang_angle_rad=math.atan(1.5)),
    )
    assert steeper_allowance.unsupported_area_mm2 == pytest.approx(10.0)


def test_hand_derived_lines_coordinates_order_spacing_events_and_volume() -> None:
    parameters = _truth_parameters("lines")
    plan = generate_support_plan(_cantilever_layers(), parameters)
    path = generate_support_toolpath("truth-lines", plan, parameters)
    expected = (
        ("L0", "planar_support", (5.2, 0.7, 0.0), (7.8, 0.7, 0.0)),
        ("L0", "planar_support", (7.8, 1.7, 0.0), (5.2, 1.7, 0.0)),
        ("L0", "planar_support", (5.2, 2.7, 0.0), (7.8, 2.7, 0.0)),
        ("L0", "planar_support", (7.8, 3.7, 0.0), (5.2, 3.7, 0.0)),
        ("L1", "planar_support", (5.2, 0.7, 1.0), (7.8, 0.7, 1.0)),
        ("L1", "planar_support", (7.8, 1.7, 1.0), (5.2, 1.7, 1.0)),
        ("L1", "planar_support", (5.2, 2.7, 1.0), (7.8, 2.7, 1.0)),
        ("L1", "planar_support", (7.8, 3.7, 1.0), (5.2, 3.7, 1.0)),
        ("L2", "planar_support_interface", (5.2, 0.45, 2.0), (7.8, 0.45, 2.0)),
        ("L2", "planar_support_interface", (7.8, 0.95, 2.0), (5.2, 0.95, 2.0)),
        ("L2", "planar_support_interface", (5.2, 1.45, 2.0), (7.8, 1.45, 2.0)),
        ("L2", "planar_support_interface", (7.8, 1.95, 2.0), (5.2, 1.95, 2.0)),
        ("L2", "planar_support_interface", (5.2, 2.45, 2.0), (7.8, 2.45, 2.0)),
        ("L2", "planar_support_interface", (7.8, 2.95, 2.0), (5.2, 2.95, 2.0)),
        ("L2", "planar_support_interface", (5.2, 3.45, 2.0), (7.8, 3.45, 2.0)),
    )
    _assert_segments(_deposition_segments(path), expected)

    assert len(path.points) == 30
    assert sum(point.material_volume_mm3 for point in path.points) == pytest.approx(15.60)
    assert [(event.event_type, event.context["sequence_index"]) for event in path.events] == [
        ("prime", 1),
        ("retract", 2),
        ("prime", 3),
        ("retract", 4),
        ("prime", 5),
        ("retract", 6),
        ("prime", 7),
        ("retract", 8),
        ("prime", 9),
        ("retract", 10),
        ("prime", 11),
        ("retract", 12),
        ("prime", 13),
        ("retract", 14),
        ("prime", 15),
        ("retract", 16),
        ("prime", 17),
        ("retract", 18),
        ("prime", 19),
        ("retract", 20),
        ("prime", 21),
        ("retract", 22),
        ("prime", 23),
        ("retract", 24),
        ("prime", 25),
        ("retract", 26),
        ("prime", 27),
        ("retract", 28),
        ("prime", 29),
    ]


def test_hand_derived_grid_coordinates_order_spacing_events_and_volume() -> None:
    parameters = _truth_parameters("grid")
    plan = generate_support_plan(_cantilever_layers(), parameters)
    path = generate_support_toolpath("truth-grid", plan, parameters)
    expected = (
        ("L0", "planar_support", (5.2, 0.7, 0.0), (7.8, 0.7, 0.0)),
        ("L0", "planar_support", (7.8, 1.7, 0.0), (5.2, 1.7, 0.0)),
        ("L0", "planar_support", (5.2, 2.7, 0.0), (7.8, 2.7, 0.0)),
        ("L0", "planar_support", (7.8, 3.7, 0.0), (5.2, 3.7, 0.0)),
        ("L1", "planar_support", (5.7, 0.2, 1.0), (5.7, 3.8, 1.0)),
        ("L1", "planar_support", (6.7, 3.8, 1.0), (6.7, 0.2, 1.0)),
        ("L1", "planar_support", (7.7, 0.2, 1.0), (7.7, 3.8, 1.0)),
        ("L2", "planar_support_interface", (5.2, 0.45, 2.0), (7.8, 0.45, 2.0)),
        ("L2", "planar_support_interface", (7.8, 0.95, 2.0), (5.2, 0.95, 2.0)),
        ("L2", "planar_support_interface", (5.2, 1.45, 2.0), (7.8, 1.45, 2.0)),
        ("L2", "planar_support_interface", (7.8, 1.95, 2.0), (5.2, 1.95, 2.0)),
        ("L2", "planar_support_interface", (5.2, 2.45, 2.0), (7.8, 2.45, 2.0)),
        ("L2", "planar_support_interface", (7.8, 2.95, 2.0), (5.2, 2.95, 2.0)),
        ("L2", "planar_support_interface", (5.2, 3.45, 2.0), (7.8, 3.45, 2.0)),
    )
    _assert_segments(_deposition_segments(path), expected)

    assert len(path.points) == 28
    assert sum(point.material_volume_mm3 for point in path.points) == pytest.approx(15.76)
    assert [(event.event_type, event.context["sequence_index"]) for event in path.events] == [
        ("prime", 1),
        ("retract", 2),
        ("prime", 3),
        ("retract", 4),
        ("prime", 5),
        ("retract", 6),
        ("prime", 7),
        ("retract", 8),
        ("prime", 9),
        ("retract", 10),
        ("prime", 11),
        ("retract", 12),
        ("prime", 13),
        ("retract", 14),
        ("prime", 15),
        ("retract", 16),
        ("prime", 17),
        ("retract", 18),
        ("prime", 19),
        ("retract", 20),
        ("prime", 21),
        ("retract", 22),
        ("prime", 23),
        ("retract", 24),
        ("prime", 25),
        ("retract", 26),
        ("prime", 27),
    ]


def test_hand_derived_narrow_region_is_centred_instead_of_disappearing() -> None:
    narrow = _rectangle("narrow", 0.0, 0.0, 0.0, 3.0, 0.6)
    plan = SupportPlan((SupportLayer("L0", 0.0, (narrow,), ()),), (), 1.8)
    parameters = SupportParameters(
        1.0,
        xy_gap_mm=0.0,
        z_gap_mm=0.0,
        interface_layers=0,
        line_spacing_mm=1.0,
        interface_spacing_mm=0.5,
        bead_width_mm=0.4,
        pattern="lines",
    )

    path = generate_support_toolpath("truth-narrow", plan, parameters)
    _assert_segments(
        _deposition_segments(path),
        (("L0", "planar_support", (0.2, 0.3, 0.0), (2.8, 0.3, 0.0)),),
    )
    assert len(path.points) == 2
    assert sum(point.material_volume_mm3 for point in path.points) == pytest.approx(1.04)
    assert [(event.event_type, event.context["sequence_index"]) for event in path.events] == [
        ("prime", 1)
    ]


def test_hand_derived_disappearing_region_rejects_the_whole_path() -> None:
    printable = _rectangle("printable", 0.0, 0.0, 0.0, 3.0, 0.6)
    disappears_after_bead_inset = _rectangle("vanishing", 1.0, 0.0, 0.0, 0.3, 3.0)
    plan = SupportPlan(
        (
            SupportLayer("L0", 0.0, (printable,), ()),
            SupportLayer("L1", 1.0, (disappears_after_bead_inset,), ()),
        ),
        (),
        2.7,
    )
    parameters = SupportParameters(
        1.0,
        xy_gap_mm=0.0,
        z_gap_mm=0.0,
        interface_layers=0,
        line_spacing_mm=1.0,
        interface_spacing_mm=0.5,
        bead_width_mm=0.4,
        pattern="lines",
    )

    with pytest.raises(PlanarSupportError, match="planar.support_region_too_narrow"):
        generate_support_toolpath("truth-disappearing", plan, parameters)
