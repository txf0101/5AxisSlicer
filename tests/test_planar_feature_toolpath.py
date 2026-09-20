from __future__ import annotations

from five_axis_slicer.algorithms.planar.feature_fill import (
    FeatureFillParameters,
    FeatureLayerPlan,
    FeatureRegionPlan,
    plan_feature_fill,
)
from five_axis_slicer.algorithms.planar.feature_toolpath import (
    FeatureToolpathParameters,
    generate_feature_toolpath,
)
from five_axis_slicer.algorithms.planar.region import PlanarRegion, PlanarSliceLayer


def _rectangle(identifier: str, z_mm: float) -> PlanarRegion:
    return PlanarRegion(
        identifier,
        ((0, 0, z_mm), (8, 0, z_mm), (8, 6, z_mm), (0, 6, z_mm), (0, 0, z_mm)),
    )


def test_feature_toolpath_preserves_shell_skin_and_sparse_stage_identity() -> None:
    layers = tuple(
        PlanarSliceLayer(f"layer-{index}", index * 0.2, (_rectangle("box", index * 0.2),))
        for index in range(1, 4)
    )
    features = plan_feature_fill(
        layers,
        FeatureFillParameters(
            infill_fraction=0.2,
            top_solid_layers=1,
            bottom_solid_layers=1,
        ),
    )
    toolpath = generate_feature_toolpath(
        "feature-case", features, FeatureToolpathParameters(), stage_prefix="case"
    )
    deposition = [point for point in toolpath.points if point.point_type == "deposition"]
    stages = {point.stage_id for point in deposition}
    assert stages == {
        "case_shell",
        "case_bottom_skin",
        "case_sparse_infill",
        "case_top_skin",
    }
    assert {point.extrusion_role for point in deposition} == {"skin", "infill"}
    assert {point.layer_id for point in deposition} == {"layer-1", "layer-2", "layer-3"}
    assert sum(point.material_volume_mm3 for point in deposition) > 0.0


def test_feature_toolpath_accepts_internal_fill_when_wall_offset_is_unavailable() -> None:
    internal = _rectangle("internal", 0.2)
    region = FeatureRegionPlan(
        "layer-1",
        "box",
        "solid_infill",
        (),
        (internal,),
        (((0.2, 0.2, 0.2), (7.8, 0.2, 0.2)),),
        1.0,
    )
    toolpath = generate_feature_toolpath(
        "internal-only",
        (FeatureLayerPlan("layer-1", 0.2, (region,), False, False),),
        FeatureToolpathParameters(),
        stage_prefix="case",
    )
    deposition = [point for point in toolpath.points if point.point_type == "deposition"]
    assert len(deposition) == 1
    assert deposition[0].stage_id == "case_solid_infill"
    assert deposition[0].extrusion_role == "infill"
