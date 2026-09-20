from __future__ import annotations

import pytest

from five_axis_slicer.algorithms.planar.feature_fill import (
    FeatureFillParameters,
    plan_feature_fill,
)
from five_axis_slicer.algorithms.planar.region import PlanarRegion, PlanarSliceLayer
from five_axis_slicer.algorithms.planar.offset import PlanarOffsetError


def _rectangle(
    region_id: str, left: float, bottom: float, right: float, top: float, z: float = 0.2, holes=()
) -> PlanarRegion:
    return PlanarRegion(
        region_id,
        ((left, bottom, z), (right, bottom, z), (right, top, z), (left, top, z), (left, bottom, z)),
        holes,
    )


def test_hole_and_multiple_islands_remain_separate() -> None:
    hole = ((4.0, 4.0, 0.2), (4.0, 6.0, 0.2), (6.0, 6.0, 0.2), (6.0, 4.0, 0.2), (4.0, 4.0, 0.2))
    layer = PlanarSliceLayer(
        "layer-1",
        0.2,
        (_rectangle("ring", 0, 0, 10, 10, holes=(hole,)), _rectangle("island", 12, 0, 16, 4)),
    )
    plan = plan_feature_fill(
        (layer,),
        FeatureFillParameters(infill_fraction=1.0, top_solid_layers=0, bottom_solid_layers=0),
    )[0]
    assert {region.region_id for region in plan.regions} == {"ring", "island"}
    ring = next(region for region in plan.regions if region.region_id == "ring")
    assert ring.internal_regions[0].holes
    assert all(
        not (4.0 < (a[0] + b[0]) / 2.0 < 6.0 and 4.0 < (a[1] + b[1]) / 2.0 < 6.0)
        for a, b in ring.infill_segments
    )


def test_zero_sparse_and_solid_infill_have_increasing_segment_counts() -> None:
    layer = PlanarSliceLayer("layer-1", 0.2, (_rectangle("box", 0, 0, 20, 20),))
    counts = []
    for fraction in (0.0, 0.2, 1.0):
        plan = plan_feature_fill(
            (layer,),
            FeatureFillParameters(
                infill_fraction=fraction, top_solid_layers=0, bottom_solid_layers=0
            ),
        )[0]
        counts.append(len(plan.regions[0].infill_segments))
    assert counts[0] == 0
    assert counts[0] < counts[1] < counts[2]


def test_top_and_bottom_layers_override_sparse_infill() -> None:
    layers = tuple(
        PlanarSliceLayer(
            f"layer-{index}", index * 0.2, (_rectangle("box", 0, 0, 10, 10, index * 0.2),)
        )
        for index in range(1, 7)
    )
    plan = plan_feature_fill(
        layers,
        FeatureFillParameters(infill_fraction=0.2, top_solid_layers=2, bottom_solid_layers=2),
    )
    assert [item.is_bottom_skin for item in plan] == [True, True, False, False, False, False]
    assert [item.is_top_skin for item in plan] == [False, False, False, False, True, True]
    assert plan[2].regions[0].infill_fraction == 0.2
    assert plan[-1].regions[0].infill_fraction == 1.0


def test_narrow_region_is_reported_as_thin_wall_without_infill() -> None:
    layer = PlanarSliceLayer("layer-1", 0.2, (_rectangle("narrow", 0, 0, 0.6, 8),))
    region = plan_feature_fill(
        (layer,),
        FeatureFillParameters(infill_fraction=1.0, top_solid_layers=0, bottom_solid_layers=0),
    )[0].regions[0]
    assert region.feature_type == "thin_wall"
    assert region.wall_contours
    assert not region.internal_regions
    assert not region.infill_segments


def test_sub_bead_region_cannot_fall_back_to_raw_boundary():
    layer = PlanarSliceLayer("layer-1", 0.2, (_rectangle("too-thin", 0, 0, 0.1, 8),))
    with pytest.raises(PlanarOffsetError):
        plan_feature_fill((layer,), FeatureFillParameters())


@pytest.mark.parametrize("failed_distance", [0.2, 0.6, 0.8])
def test_offset_failure_is_not_reported_as_success(monkeypatch, failed_distance):
    from five_axis_slicer.algorithms.planar import feature_fill

    original = feature_fill.inset_region

    def failing_offset(region, distance):
        if abs(distance - failed_distance) < 1e-8:
            raise PlanarOffsetError("planar.offset_kernel_failed", "injected kernel failure")
        return original(region, distance)

    monkeypatch.setattr(feature_fill, "inset_region", failing_offset)
    layer = PlanarSliceLayer("layer-1", 0.2, (_rectangle("box", 0, 0, 10, 10),))
    with pytest.raises(PlanarOffsetError, match="injected kernel failure"):
        plan_feature_fill((layer,), FeatureFillParameters())
