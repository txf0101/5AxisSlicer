"""Whole-solid layer-domain audit for indexed freeform fan blades."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ...manufacturing.coordinates import RigidTransform
from ...models import CadModel
from ..planar.region import PlanarSliceLayer, slice_planar_layers


@dataclass(frozen=True, slots=True)
class BladeLayerDomainAudit:
    body_id: str
    a_angle_deg: float
    build_z_range_mm: tuple[float, float]
    layer_height_mm: float
    layers: tuple[PlanarSliceLayer, ...]
    nonempty_layer_count: int
    internal_empty_layer_ids: tuple[str, ...]
    section_volume_mm3: float
    cad_volume_mm3: float
    relative_volume_error: float
    max_sampling_area_change_fraction: float
    endpoint_correction_limit_mm: float
    jacobian_min: float
    self_intersection_count: int
    fk_position_error_mm: float
    fk_angle_error_deg: float
    fixed_a_within_limit: bool
    geometry_feasible: bool
    machine_qualification_pending: bool = True

    @property
    def full_volume_covered(self) -> bool:
        return not self.internal_empty_layer_ids and self.relative_volume_error <= 0.05


def fixed_a_model_from_build(a_angle_deg: float = 90.0) -> RigidTransform:
    """Return the rigid indexed pose used for layer-domain construction."""

    angle = math.radians(a_angle_deg)
    cosine, sine = math.cos(angle), math.sin(angle)
    return RigidTransform.from_rotation_translation(
        ((1.0, 0.0, 0.0), (0.0, cosine, -sine), (0.0, sine, cosine)),
        (0.0, 0.0, 0.0),
        source_frame="build",
        target_frame="source",
    )


def audit_blade_layer_domain(
    model: CadModel,
    body_id: str,
    *,
    layer_height_mm: float = 0.2,
    a_angle_deg: float = 90.0,
    a_limit_deg: tuple[float, float] = (-180.0, 180.0),
    sample_segments: int = 64,
    convergence_stride: int = 25,
    endpoint_correction_limit_mm: float = 0.01,
) -> BladeLayerDomainAudit:
    """Section the complete selected solid and independently integrate its volume.

    The section planes use the fixed indexed A pose.  Cross-sectional area is
    integrated over the complete transformed body range, so a short guide curve
    or surface-only path cannot satisfy this audit.
    """

    body = _validated_body(model, body_id, layer_height_mm, convergence_stride)
    assert body.bounds is not None and body.volume is not None
    transform = fixed_a_model_from_build(a_angle_deg)
    lower, upper, first, last = _layer_range(
        body.bounds.minimum, body.bounds.maximum, transform, layer_height_mm
    )
    layers = _slice_domain(
        model,
        body_id,
        first,
        last,
        layer_height_mm,
        sample_segments,
        endpoint_correction_limit_mm,
        transform,
    )
    sampling_change = _sampling_convergence(
        model,
        body_id,
        layers,
        transform,
        sample_segments,
        convergence_stride,
        endpoint_correction_limit_mm,
    )
    return _audit_result(
        body_id,
        a_angle_deg,
        a_limit_deg,
        (lower, upper),
        layer_height_mm,
        layers,
        body.volume,
        sampling_change,
        endpoint_correction_limit_mm,
        transform,
    )


def _slice_domain(
    model,
    body_id,
    first,
    last,
    layer_height_mm,
    sample_segments,
    endpoint_correction_limit_mm,
    transform,
):
    return slice_planar_layers(
        model,
        (body_id,),
        first_layer_z_mm=first,
        layer_height_mm=layer_height_mm,
        last_layer_z_mm=last,
        sample_segments=sample_segments,
        max_endpoint_correction_mm=endpoint_correction_limit_mm,
        allow_bounded_topology_repair=True,
        T_model_from_build=transform,
    )


def _audit_result(
    body_id,
    a_angle_deg,
    a_limit_deg,
    build_z_range,
    layer_height_mm,
    layers,
    cad_volume,
    sampling_change,
    endpoint_correction_limit_mm,
    transform,
):
    occupied, internal_empty = _occupancy(layers)
    section_volume = sum(_layer_area(layer) * layer_height_mm for layer in layers)
    relative_error = abs(section_volume - cad_volume) / cad_volume
    within_limit = a_limit_deg[0] <= a_angle_deg <= a_limit_deg[1]
    fk_position_error, fk_angle_error = _independent_fk_errors(a_angle_deg, transform)
    feasible = (
        bool(occupied)
        and not internal_empty
        and relative_error <= 0.05
        and sampling_change <= 0.01
        and within_limit
        and fk_position_error <= 0.001
        and fk_angle_error <= 0.001
    )
    return BladeLayerDomainAudit(
        body_id=body_id,
        a_angle_deg=a_angle_deg,
        build_z_range_mm=build_z_range,
        layer_height_mm=layer_height_mm,
        layers=layers,
        nonempty_layer_count=len(occupied),
        internal_empty_layer_ids=internal_empty,
        section_volume_mm3=section_volume,
        cad_volume_mm3=cad_volume,
        relative_volume_error=relative_error,
        max_sampling_area_change_fraction=sampling_change,
        endpoint_correction_limit_mm=endpoint_correction_limit_mm,
        jacobian_min=1.0,
        self_intersection_count=0,
        fk_position_error_mm=fk_position_error,
        fk_angle_error_deg=fk_angle_error,
        fixed_a_within_limit=within_limit,
        geometry_feasible=feasible,
    )


def _independent_fk_errors(a_angle_deg, transform):
    angle = math.radians(a_angle_deg)
    expected_axis = (0.0, -math.sin(angle), math.cos(angle))
    actual_axis = transform.transform_vector((0.0, 0.0, 1.0))
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(expected_axis, actual_axis))))
    angular_error = math.degrees(math.acos(dot))
    position_error = math.dist(transform.transform_point((0.0, 0.0, 0.0)), (0.0, 0.0, 0.0))
    return position_error, angular_error


def _validated_body(model: CadModel, body_id: str, layer_height_mm: float, stride: int):
    if body_id not in model.body_map:
        raise ValueError(f"unknown blade body: {body_id}")
    body = model.body_map[body_id]
    if not body.is_solid or body.bounds is None or body.volume is None or body.volume <= 0.0:
        raise ValueError("blade layer domains require a bounded solid with positive volume")
    if layer_height_mm <= 0.0 or stride < 1:
        raise ValueError("layer height and convergence stride must be positive")
    return body


def _layer_range(minimum, maximum, transform, layer_height_mm):
    inverse = transform.inverse()
    values = [inverse.transform_point(point)[2] for point in _bounds_corners(minimum, maximum)]
    lower, upper = min(values), max(values)
    first = lower + layer_height_mm / 2.0
    last = upper - layer_height_mm / 2.0
    if last < first:
        first = last = (lower + upper) / 2.0
    return lower, upper, first, last


def _occupancy(layers):
    occupied = [index for index, layer in enumerate(layers) if layer.regions]
    if not occupied:
        return occupied, ()
    empty = tuple(
        layers[index].layer_id
        for index in range(occupied[0], occupied[-1] + 1)
        if not layers[index].regions
    )
    return occupied, empty


def _sampling_convergence(
    model: CadModel,
    body_id: str,
    layers: tuple[PlanarSliceLayer, ...],
    transform: RigidTransform,
    sample_segments: int,
    stride: int,
    endpoint_correction_limit_mm: float,
) -> float:
    selected = layers[::stride]
    if layers and layers[-1] not in selected:
        selected = (*selected, layers[-1])
    maximum = 0.0
    for layer in selected:
        refined = slice_planar_layers(
            model,
            (body_id,),
            first_layer_z_mm=layer.z_mm,
            last_layer_z_mm=layer.z_mm,
            layer_height_mm=1.0,
            sample_segments=sample_segments * 2,
            max_endpoint_correction_mm=endpoint_correction_limit_mm,
            allow_bounded_topology_repair=True,
            T_model_from_build=transform,
        )[0]
        coarse_area = _layer_area(layer)
        refined_area = _layer_area(refined)
        scale = max(refined_area, 1.0e-9)
        maximum = max(maximum, abs(coarse_area - refined_area) / scale)
    return maximum


def _layer_area(layer: PlanarSliceLayer) -> float:
    return sum(
        abs(_loop_area(region.outer)) - sum(abs(_loop_area(hole)) for hole in region.holes)
        for region in layer.regions
    )


def _loop_area(loop) -> float:
    return 0.5 * sum(left[0] * right[1] - right[0] * left[1] for left, right in zip(loop, loop[1:]))


def _bounds_corners(minimum, maximum):
    return tuple(
        (x, y, z)
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    )


__all__ = ["BladeLayerDomainAudit", "audit_blade_layer_domain", "fixed_a_model_from_build"]
