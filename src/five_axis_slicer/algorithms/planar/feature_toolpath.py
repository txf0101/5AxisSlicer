"""Convert shared shell/skin/infill feature plans to the public Toolpath contract."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...manufacturing.toolpath import GeneratedToolpath
from .feature_fill import FeatureLayerPlan, FeatureRegionPlan
from .region import PlanarRegion, PlanarSliceLayer
from .zigzag import ZigzagParameters, _ZigzagBuilder


@dataclass(frozen=True, slots=True)
class FeatureToolpathParameters:
    bead_width_mm: float = 0.4
    layer_height_mm: float = 0.2
    deposition_feedrate_mm_min: float = 1200.0
    travel_feedrate_mm_min: float = 3000.0
    retract_length_mm: float = 1.0

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")


def generate_feature_toolpath(
    operation_id: str,
    layers: tuple[FeatureLayerPlan, ...],
    parameters: FeatureToolpathParameters,
    *,
    stage_prefix: str,
) -> GeneratedToolpath:
    """Generate perimeter-first paths while retaining feature provenance."""

    if not operation_id.strip() or not stage_prefix.strip():
        raise ValueError("operation_id and stage_prefix must not be empty")
    process = ZigzagParameters(
        parameters.bead_width_mm,
        parameters.bead_width_mm,
        parameters.layer_height_mm,
        parameters.deposition_feedrate_mm_min,
        parameters.travel_feedrate_mm_min,
        parameters.retract_length_mm,
    )
    builder = _ZigzagBuilder(operation_id, process)
    for layer in layers:
        source_layer = PlanarSliceLayer(layer.layer_id, layer.z_mm, ())
        for region in layer.regions:
            source_region = _source_region(region)
            if source_region is None:
                continue
            for contour in region.wall_contours:
                _add_path(
                    builder,
                    source_layer,
                    source_region,
                    tuple(point[:2] for point in contour),
                    "skin",
                    f"{stage_prefix}_shell",
                )
            stage, role = _infill_semantics(layer, region, stage_prefix)
            for segment in region.infill_segments:
                _add_path(
                    builder,
                    source_layer,
                    source_region,
                    tuple(point[:2] for point in segment),
                    role,
                    stage,
                )
    if not builder.points:
        raise ValueError("feature plan contains no printable paths")
    return GeneratedToolpath(
        f"{operation_id}-features-v1",
        operation_id,
        points=tuple(builder.points),
        events=tuple(builder.events),
    )


def _add_path(builder, layer, region, points, role, stage):
    builder._add_path(layer, region, points, role, stage)


def _source_region(region: FeatureRegionPlan) -> PlanarRegion | None:
    if region.wall_contours:
        return PlanarRegion(region.region_id, region.wall_contours[0])
    if region.internal_regions:
        internal = region.internal_regions[0]
        return PlanarRegion(region.region_id, internal.outer, internal.holes)
    return None


def _infill_semantics(layer, region: FeatureRegionPlan, prefix: str) -> tuple[str, str]:
    if layer.is_bottom_skin:
        return f"{prefix}_bottom_skin", "skin"
    if layer.is_top_skin:
        return f"{prefix}_top_skin", "skin"
    if region.feature_type == "sparse_infill":
        return f"{prefix}_sparse_infill", "infill"
    return f"{prefix}_solid_infill", "infill"


__all__ = ["FeatureToolpathParameters", "generate_feature_toolpath"]
