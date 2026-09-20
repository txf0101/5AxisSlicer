"""FAN06/FAN07 full-height base and single-blade manufacturing plans."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...manufacturing.fan_job import FanManufacturingContract
from ...manufacturing.toolpath import GeneratedToolpath
from ...models import CadModel
from ..freeform.layer_domain import BladeLayerDomainAudit
from ..planar.feature_fill import FeatureFillParameters, FeatureLayerPlan, plan_feature_fill
from ..planar.feature_toolpath import FeatureToolpathParameters, generate_feature_toolpath
from ..planar.region import PlanarSliceLayer, slice_planar_layers
from ..planar.support import (
    SupportParameters,
    SupportPlan,
    generate_support_plan,
    generate_support_toolpath,
)


@dataclass(frozen=True, slots=True)
class FanLayerScheduleEntry:
    layer_id: str
    z_mm: float
    support_region_count: int
    part_region_count: int
    ordered_stages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FanBasePlan:
    layers: tuple[PlanarSliceLayer, ...]
    features: tuple[FeatureLayerPlan, ...]
    support: SupportPlan
    part_toolpath: GeneratedToolpath
    support_toolpath: GeneratedToolpath
    schedule: tuple[FanLayerScheduleEntry, ...]

    @property
    def all_layers_scheduled(self) -> bool:
        return len(self.layers) == len(self.schedule) and all(
            item.part_region_count for item in self.schedule
        )


@dataclass(frozen=True, slots=True)
class FanBladePlan:
    audit: BladeLayerDomainAudit
    features: tuple[FeatureLayerPlan, ...]
    toolpath: GeneratedToolpath

    @property
    def deposition_volume_mm3(self) -> float:
        return sum(point.material_volume_mm3 for point in self.toolpath.points)


def generate_fan_base_plan(model: CadModel, contract: FanManufacturingContract) -> FanBasePlan:
    """Generate the complete hub/base volume and its build-plate support schedule."""

    parameters = contract.parameters
    body_id = contract.geometry.hub.object_id
    body = model.body_map.get(body_id)
    if body is None or body.bounds is None:
        raise ValueError(f"bounded hub body is required: {body_id}")
    transform = contract.source_to_build.inverse()
    build_bounds = [
        contract.source_to_build.transform_point(point)[2]
        for point in _bounds_corners(body.bounds.minimum, body.bounds.maximum)
    ]
    first = max(parameters.layer_height_mm, min(build_bounds) + parameters.layer_height_mm)
    last = math.floor(max(build_bounds) / parameters.layer_height_mm) * parameters.layer_height_mm
    layers = slice_planar_layers(
        model,
        (body_id,),
        first_layer_z_mm=first,
        last_layer_z_mm=last,
        layer_height_mm=parameters.layer_height_mm,
        sample_segments=64,
        max_endpoint_correction_mm=parameters.chord_error_mm / 2.0,
        allow_bounded_topology_repair=True,
        T_model_from_build=transform,
    )
    features = plan_feature_fill(layers, _base_feature_parameters(contract))
    path_parameters = _path_parameters(contract)
    part_toolpath = generate_feature_toolpath(
        "fan-base", features, path_parameters, stage_prefix="fan_base"
    )
    support_parameters = _support_parameters(contract)
    support = generate_support_plan(layers, support_parameters)
    support_toolpath = generate_support_toolpath(
        "fan-base-support",
        support,
        support_parameters,
        deposition_feedrate_mm_min=parameters.deposition_feedrate_mm_min,
        travel_feedrate_mm_min=parameters.travel_feedrate_mm_min,
        retract_length_mm=parameters.retract_length_mm,
    )
    schedule = _base_schedule(layers, support)
    return FanBasePlan(layers, features, support, part_toolpath, support_toolpath, schedule)


def generate_single_blade_plan(
    model: CadModel,
    contract: FanManufacturingContract,
    *,
    blade_index: int = 0,
) -> FanBladePlan:
    """Reject the withdrawn indexed-planar blade strategy.

    A constant A pose does not define the required cylindrical growth layers.
    The experimental radial domain is deliberately separate until coverage,
    support, transitions and controller readback have been qualified.
    """
    raise ValueError(
        "fan.blade_strategy_withdrawn: fixed-A planar sections do not grow from "
        "the hub surface; radial replacement is preview-only pending qualification"
    )


def _path_parameters(contract):
    parameters = contract.parameters
    return FeatureToolpathParameters(
        bead_width_mm=parameters.bead_width_mm,
        layer_height_mm=parameters.layer_height_mm,
        deposition_feedrate_mm_min=parameters.deposition_feedrate_mm_min,
        travel_feedrate_mm_min=parameters.travel_feedrate_mm_min,
        retract_length_mm=parameters.retract_length_mm,
    )


def _base_feature_parameters(contract):
    parameters = contract.parameters
    return FeatureFillParameters(
        bead_width_mm=parameters.bead_width_mm,
        wall_count=parameters.wall_count,
        infill_fraction=parameters.base_infill_fraction,
        top_solid_layers=_solid_layers(
            parameters.top_solid_thickness_mm, parameters.layer_height_mm
        ),
        bottom_solid_layers=_solid_layers(
            parameters.bottom_solid_thickness_mm, parameters.layer_height_mm
        ),
    )


def _support_parameters(contract):
    parameters = contract.parameters
    return SupportParameters(
        parameters.layer_height_mm,
        xy_gap_mm=parameters.bead_width_mm,
        z_gap_mm=parameters.layer_height_mm,
        interface_layers=2,
        line_spacing_mm=2.0,
        interface_spacing_mm=parameters.bead_width_mm,
        bead_width_mm=parameters.bead_width_mm,
        pattern="grid",
    )


def _base_schedule(layers, support):
    result = []
    for layer, support_layer in zip(layers, support.layers, strict=True):
        support_count = len(support_layer.body_regions) + len(support_layer.interface_regions)
        stages = (("support",) if support_count else ()) + ("part",)
        result.append(
            FanLayerScheduleEntry(
                layer.layer_id,
                layer.z_mm,
                support_count,
                len(layer.regions),
                stages,
            )
        )
    return tuple(result)


def _solid_layers(thickness_mm, layer_height_mm):
    return max(1, int(math.ceil(thickness_mm / layer_height_mm - 1.0e-9)))


def _bounds_corners(minimum, maximum):
    return tuple(
        (x, y, z)
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    )


__all__ = [
    "FanBasePlan",
    "FanBladePlan",
    "FanLayerScheduleEntry",
    "generate_fan_base_plan",
    "generate_single_blade_plan",
]
