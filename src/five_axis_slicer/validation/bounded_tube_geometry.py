"""Sample centre containment for multiple tracks, without claiming bead coverage."""
from collections.abc import Callable
import math
from typing import cast

from ..algorithms.tube.geometry import TubeFeature
from ..manufacturing.toolpath import GeneratedToolpath
from ..models import Vector3


def sampled_wall_errors(
    feature: TubeFeature,
    toolpath: GeneratedToolpath,
    checkpoint: Callable[[], None] | None = None,
) -> tuple[float, float]:
    """Return centre-outside-wall and interpolation chord errors in mm.

    Track centres may lie anywhere inside the annular wall. These samples do
    not qualify finite-width material coverage, overlaps or boundary accuracy.
    """
    from .indexed_tube import _distance_to_centerline

    outside = chord = 0.0
    for index, (left, right) in enumerate(zip(toolpath.points, toolpath.points[1:])):
        if checkpoint is not None and index % 256 == 0:
            checkpoint()
        if right.point_type != "deposition":
            continue
        if left.layer_id != right.layer_id or left.region_id != right.region_id:
            raise ValueError("Deposited segment crosses layer or region identity")
        radii = []
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            position = cast(Vector3, tuple(a + fraction * (b - a)
                            for a, b in zip(left.position, right.position, strict=True)))
            radius = _distance_to_centerline(position, feature)
            if not math.isfinite(radius):
                raise ValueError("Nonfinite deposited centre distance")
            radii.append(radius)
            outside = max(outside, feature.inner_radius_mm - radius,
                          radius - feature.outer_radius_mm)
        chord = max(chord, *(abs(radius - ((1 - fraction) * radii[0] + fraction * radii[-1]))
                             for fraction, radius in zip((0.25, 0.5, 0.75), radii[1:-1])))
    return outside, chord


def bounded_geometry_validation(feature, plan, toolpath, radial_limit, checkpoint=None):
    """Validate strategy-specific identity and dimensions; retain deferred accuracy."""
    from .indexed_tube import ValidationMetric
    from ..manufacturing.setup import IssueSeverity, ValidationIssue
    outside, chord = sampled_wall_errors(feature, toolpath, checkpoint)
    metrics = [ValidationMetric('maximum_center_outside_wall', outside, radial_limit, 'mm', outside <= radial_limit),
               ValidationMetric('maximum_sampled_chord_error', chord, plan.contour_chord_error_mm,
                                'mm', chord <= plan.contour_chord_error_mm)]
    failures = _bounded_contract_errors(plan, toolpath, checkpoint)
    issues = [ValidationIssue('tube.bounded_contract_invalid', IssueSeverity.ERROR,
                              toolpath.toolpath_id, context={'reason': reason}) for reason in sorted(failures)]
    issues.append(ValidationIssue('tube.bounded_boundary_accuracy_deferred', IssueSeverity.WARNING,
        toolpath.toolpath_id, context={'residual_task_count': plan.residual_task_count,
        'finite_width_union_verified': False, 'machine_executable': False,
        'limitation': 'Local seam gaps, overlap and bead boundary accuracy deferred by delivery plan section 7.'}))
    return metrics, issues


def _bounded_contract_errors(plan, toolpath, checkpoint):
    failures = set()
    mapping = dict(plan.layer_bands)
    layers = {layer.layer_id: layer for layer in plan.layers}
    if len(mapping) != len(plan.layer_bands) or set(mapping) != set(layers):
        failures.add('layer_band_identity')
    failures.update(_layer_record_errors(plan, mapping))
    previous = _band_contract_errors(plan, failures)
    deposited = set()
    for index, point in enumerate(toolpath.points):
        if checkpoint is not None and index % 256 == 0:
            checkpoint()
        failures.update(_point_dimension_errors(point, plan))
        if point.point_type != 'deposition':
            continue
        deposited.add(point.layer_id)
        band = mapping.get(point.layer_id)
        if band is None or point.region_id != band.region_id:
            failures.add('point_layer_region')
            continue
        if math.dist(point.nozzle_axis, tuple(-v for v in band.build_axis)) > 1e-8:
            failures.add('point_build_axis')
    if deposited != set(layers):
        failures.add('missing_or_extra_deposition_layer')
    if set(previous) != {region.region_id for region in plan.regions}:
        failures.add('missing_region_bands')
    return failures


def _point_dimension_errors(point, plan):
    if point.point_type == 'depart':
        return set()
    failures = set()
    h, w = point.layer_height_mm, point.bead_width_mm
    if h is None or not math.isfinite(h) or not .5 * plan.nominal_layer_height_mm - 1e-8 <= h <= 1.5 * plan.nominal_layer_height_mm + 1e-8:
        failures.add('point_height')
    if w is None or not math.isfinite(w) or not 0 < w <= plan.maximum_track_width_mm + 1e-8:
        failures.add('point_width')

    return failures


def _band_contract_errors(plan, failures):
    previous: dict[str, int] = {}
    for band in plan.band_records:
        expected = previous.get(band.region_id, -1) + 1
        if band.index != expected or abs(band.lower_mm - band.index * plan.nominal_layer_height_mm) > 1e-8:
            failures.add('band_index_spacing')
        previous[band.region_id] = band.index
    return previous






def _layer_record_errors(plan, mapping):
    failures = set()
    for layer in plan.layers:
        band = mapping.get(layer.layer_id)
        if band is None:
            continue
        expected = tuple(p + band.center_mm * n for p, n in zip(band.origin, band.build_axis))
        if layer.region_id != band.region_id or math.dist(layer.plane_normal, band.build_axis) > 1e-8:
            failures.add('layer_region_axis')
        if math.dist(layer.plane_origin, expected) > 1e-8:
            failures.add('layer_plane_origin')
        if band not in plan.band_records:
            failures.add('unknown_layer_band')
    return failures
