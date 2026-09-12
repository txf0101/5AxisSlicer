"""Build-plate-only vertical support, independently implemented from regions.

Angles are radians from the vertical. Layer Z is the deposition plane; a top
contact at Z requires at least ``layer_height + z_gap`` centreline separation.
The input first layer is the build-plate deposition layer. Empty input layers
must be retained, including below floating components.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math

import cadquery as cq

from ...manufacturing.toolpath import GeneratedToolpath
from .region import PlanarRegion, PlanarSliceLayer
from .support_geometry import (
    AREA_EPSILON,
    PlanarSupportError,
    empty_shape,
    intersect_shape,
    layer_shape,
    offset_shape,
    shape_area,
    shape_regions,
    subtract_shape,
    union_shapes,
)
from .zigzag import ZigzagParameters, _ZigzagBuilder, _hatch_segments


@dataclass(frozen=True, slots=True)
class SupportParameters:
    layer_height_mm: float
    overhang_angle_rad: float = math.pi / 4
    xy_gap_mm: float = 0.4
    z_gap_mm: float = 0.2
    interface_layers: int = 2
    line_spacing_mm: float = 2.0
    interface_spacing_mm: float = 0.4
    bead_width_mm: float = 0.4
    pattern: str = "lines"

    def __post_init__(self) -> None:
        positive = (
            self.layer_height_mm,
            self.line_spacing_mm,
            self.interface_spacing_mm,
            self.bead_width_mm,
        )
        if any(not math.isfinite(value) or value <= 0 for value in positive):
            raise PlanarSupportError(
                "planar.support_parameter_invalid", "positive dimensions required"
            )
        if any(not math.isfinite(value) or value < 0 for value in (self.xy_gap_mm, self.z_gap_mm)):
            raise PlanarSupportError("planar.support_parameter_invalid", "gaps must be nonnegative")
        if (
            not math.isfinite(self.overhang_angle_rad)
            or not 0 <= self.overhang_angle_rad < math.pi / 2
        ):
            raise PlanarSupportError(
                "planar.support_parameter_invalid", "angle must be in [0, pi/2)"
            )
        if type(self.interface_layers) is not int or not 0 <= self.interface_layers <= 100:
            raise PlanarSupportError(
                "planar.support_parameter_invalid", "interface layers must be 0..100"
            )
        if self.pattern not in {"lines", "grid"}:
            raise PlanarSupportError(
                "planar.support_parameter_invalid", "pattern must be lines or grid"
            )


@dataclass(frozen=True, slots=True)
class SupportDiagnostic:
    code: str
    layer_id: str
    detail: str
    area_mm2: float = 0.0


@dataclass(frozen=True, slots=True)
class SupportLayer:
    layer_id: str
    z_mm: float
    body_regions: tuple[PlanarRegion, ...]
    interface_regions: tuple[PlanarRegion, ...]


@dataclass(frozen=True, slots=True)
class SupportPlan:
    layers: tuple[SupportLayer, ...]
    diagnostics: tuple[SupportDiagnostic, ...]
    unsupported_area_mm2: float


def generate_support_plan(
    layers: tuple[PlanarSliceLayer, ...],
    parameters: SupportParameters,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> SupportPlan:
    """Detect unsupported cross-sections and preserve only plate-connected columns."""
    _checkpoint(cancelled)
    _validate_layers(layers, parameters.layer_height_mm)
    try:
        objects = []
        for layer in layers:
            _checkpoint(cancelled)
            objects.append(layer_shape(layer))
        return _generate_plan(layers, objects, parameters, cancelled)
    except PlanarSupportError:
        raise
    except Exception as error:
        from ...postprocessing.indexed_tube import GenerationCancelled

        if isinstance(error, GenerationCancelled):
            raise
        raise PlanarSupportError("planar.support_kernel_failed", str(error)) from error


def _validate_layers(layers: tuple[PlanarSliceLayer, ...], height: float) -> None:
    if len(layers) < 2:
        raise PlanarSupportError(
            "planar.support_layers_insufficient", "at least two layers required"
        )
    if len({layer.layer_id for layer in layers}) != len(layers):
        raise PlanarSupportError("planar.support_layer_id_duplicate", "layer ids must be unique")
    for index, layer in enumerate(layers):
        if not math.isfinite(layer.z_mm):
            raise PlanarSupportError("planar.support_layer_invalid", layer.layer_id)
        if index and not math.isclose(
            layer.z_mm - layers[index - 1].z_mm, height, rel_tol=1.0e-7, abs_tol=1.0e-7
        ):
            raise PlanarSupportError("planar.support_layer_spacing_invalid", layer.layer_id)


def _generate_plan(layers, objects, parameters, cancelled):
    allowance = parameters.layer_height_mm * math.tan(parameters.overhang_angle_rad)
    contacts = [empty_shape()]
    for index in range(1, len(layers)):
        _checkpoint(cancelled)
        contacts.append(subtract_shape(objects[index], offset_shape(objects[index - 1], allowance)))
    gap_layers = int(math.ceil(parameters.z_gap_mm / parameters.layer_height_mm - 1.0e-9))
    blockers = []
    for shape in objects:
        _checkpoint(cancelled)
        blockers.append(offset_shape(shape, parameters.xy_gap_mm))
    candidates, interfaces = _project_contacts(
        contacts, blockers, gap_layers, parameters.interface_layers, cancelled
    )
    # A column blocked at any lower layer cannot start in the air. Intersect
    # upward with plate-connected support, retaining explicit unserved warnings.
    connected: list[cq.Shape] = []
    for index, candidate in enumerate(candidates):
        _checkpoint(cancelled)
        connected.append(candidate if index == 0 else intersect_shape(candidate, connected[-1]))
    diagnostics = _contact_diagnostics(layers, contacts, connected, blockers, gap_layers)
    output = []
    for index, layer in enumerate(layers):
        _checkpoint(cancelled)
        interface = intersect_shape(connected[index], interfaces[index])
        body = subtract_shape(connected[index], interface)
        output.append(
            SupportLayer(
                layer.layer_id,
                layer.z_mm,
                shape_regions(body, layer.z_mm, "support-body"),
                shape_regions(interface, layer.z_mm, "support-interface"),
            )
        )
    return SupportPlan(
        tuple(output), tuple(diagnostics), sum(shape_area(shape) for shape in contacts)
    )


def _project_contacts(contacts, blockers, gap_layers, interface_layers, cancelled):
    candidates = [empty_shape() for _ in contacts]
    interfaces = [empty_shape() for _ in contacts]
    for contact_index, contact in enumerate(contacts):
        _checkpoint(cancelled)
        if shape_area(contact) <= AREA_EPSILON:
            continue
        top = contact_index - 1 - gap_layers
        column = contact
        # Solids inside the omitted top gap still obstruct a vertical column.
        for index in range(contact_index - 1, -1, -1):
            _checkpoint(cancelled)
            column = subtract_shape(column, blockers[index])
            if index > top:
                continue
            candidates[index] = union_shapes([candidates[index], column])
            if index > top - interface_layers:
                interfaces[index] = union_shapes([interfaces[index], column])
    return candidates, interfaces


def _contact_diagnostics(layers, contacts, connected, blockers, gap_layers):
    diagnostics = []
    for index, contact in enumerate(contacts):
        area = shape_area(contact)
        if area <= AREA_EPSILON:
            continue
        top = index - 1 - gap_layers
        service_target = contact
        if top >= 0:
            # The configured XY/Z clearance is an intentional no-support
            # domain.  Remove it from the service target before deciding
            # whether a lower obstruction broke the build-plate route.
            for blocker_index in range(index - 1, top - 1, -1):
                service_target = subtract_shape(service_target, blockers[blocker_index])
        served = connected[top] if top >= 0 else empty_shape()
        unserved = shape_area(subtract_shape(service_target, served))
        if unserved > AREA_EPSILON:
            diagnostics.append(
                SupportDiagnostic(
                    "planar.support_unreachable_from_buildplate",
                    layers[index].layer_id,
                    "Some contact area has no vertical build-plate route after XY/Z gaps",
                    unserved,
                )
            )
    return diagnostics


def generate_support_toolpath(
    operation_id: str,
    plan: SupportPlan,
    parameters: SupportParameters,
    *,
    deposition_feedrate_mm_min: float = 600.0,
    travel_feedrate_mm_min: float = 1800.0,
    retract_length_mm: float = 1.0,
    cancelled: Callable[[], bool] | None = None,
) -> GeneratedToolpath:
    """Hatch inset support domains with body/interface stage provenance.

    An empty plan returns an empty toolpath; a nonempty domain too narrow for
    its bead/spacing raises a diagnostic instead of silently losing support.
    """
    process = ZigzagParameters(
        parameters.line_spacing_mm,
        parameters.bead_width_mm,
        parameters.layer_height_mm,
        deposition_feedrate_mm_min,
        travel_feedrate_mm_min,
        retract_length_mm,
    )
    builder = _ZigzagBuilder(operation_id, process)
    stages: dict[tuple[str, str], str] = {}
    for index, layer in enumerate(plan.layers):
        _checkpoint(cancelled)
        for regions, interface in ((layer.body_regions, False), (layer.interface_regions, True)):
            spacing = parameters.interface_spacing_mm if interface else parameters.line_spacing_mm
            role = "support_interface" if interface else "support_material"
            for region in regions:
                _checkpoint(cancelled)
                stage = "planar_support_interface" if interface else "planar_support"
                stages[(layer.layer_id, region.region_id)] = stage
                _add_support_region(
                    builder, layer, region, parameters, spacing, role, index, cancelled
                )
    return _stage_toolpath(operation_id, builder, stages)


def _add_support_region(builder, layer, region, parameters, spacing, role, index, cancelled):
    source_layer = PlanarSliceLayer(layer.layer_id, layer.z_mm, (region,))
    inset = offset_shape(layer_shape(source_layer), -0.5 * parameters.bead_width_mm)
    clipped = shape_regions(inset, layer.z_mm, region.region_id)
    count = 0
    for part in clipped:
        _checkpoint(cancelled)
        # Grid alternates orthogonal line layers, avoiding double extrusion at
        # same-layer crossings. Lines keep one orientation across all layers.
        vertical = parameters.pattern == "grid" and index % 2 == 1
        oriented = _swap_xy(part) if vertical else part
        segments = _hatch_segments(oriented, spacing)
        if not segments:
            # Centre a line in a narrow residual island instead of depending
            # on an arbitrarily phased coarse hatch origin.
            height = max(p[1] for p in oriented.outer) - min(p[1] for p in oriented.outer)
            segments = _hatch_segments(oriented, height) if height > 1.0e-8 else ()
        for path_index, segment in enumerate(segments):
            _checkpoint(cancelled)
            points = tuple((point[1], point[0]) if vertical else point for point in segment)
            builder._add_path(
                source_layer,
                region,
                points if path_index % 2 == 0 else points[::-1],
                role,
            )
            count += 1
    if count == 0:
        raise PlanarSupportError(
            "planar.support_region_too_narrow",
            f"{layer.layer_id}/{region.region_id}: bead does not fit",
        )


def _swap_xy(region):
    def swap(loop):
        return tuple((point[1], point[0], point[2]) for point in loop)

    return PlanarRegion(
        region.region_id, swap(region.outer), tuple(swap(hole) for hole in region.holes)
    )


def _stage_toolpath(operation_id, builder, stages):
    from dataclasses import replace

    points = tuple(
        replace(point, stage_id=stages[(point.layer_id, point.region_id)])
        for point in builder.points
    )
    events = tuple(
        replace(event, stage_id=stages[(event.layer_id, event.region_id)])
        for event in builder.events
    )
    return GeneratedToolpath(
        f"{operation_id}-support-v1", operation_id, points=points, events=events
    )


def _checkpoint(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        from ...postprocessing.indexed_tube import GenerationCancelled

        raise GenerationCancelled("Planar support generation cancelled")
