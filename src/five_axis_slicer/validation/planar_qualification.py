"""Manufacturing checks independent of the Planar path generators."""

from __future__ import annotations

import math

from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_IN, TopAbs_ON
from OCP.gp import gp_Pnt

from ..manufacturing.setup import IssueSeverity, ValidationIssue
from .planar import PlanarToolpathMeasurement
from .planar_travel import support_cad_issues

BEAD_ENVELOPE_TOLERANCE_MM = 0.001


def measurement_issues(measurement: PlanarToolpathMeasurement, *, planar: bool = True):
    issues = []
    if planar and measurement.deposition_outside_max_mm > 1e-6:
        issues.append(
            _error(
                "planar.deposition_outside_region",
                {
                    "maximum_mm": measurement.deposition_outside_max_mm,
                },
            )
        )
    if planar and measurement.bead_outside_max_mm > BEAD_ENVELOPE_TOLERANCE_MM:
        issues.append(
            _error(
                "planar.bead_envelope_outside_region",
                {
                    "maximum_mm": measurement.bead_outside_max_mm,
                    "tolerance_mm": BEAD_ENVELOPE_TOLERANCE_MM,
                },
            )
        )
    limit = max(1e-6, abs(measurement.geometric_volume_mm3) * 1e-9)
    if (
        max(abs(measurement.volume_difference_mm3), measurement.absolute_volume_difference_mm3)
        > limit
    ):
        issues.append(
            _error(
                "planar.material_volume_mismatch",
                {
                    "difference_mm3": measurement.volume_difference_mm3,
                    "absolute_segment_difference_mm3": measurement.absolute_volume_difference_mm3,
                },
            )
        )
    return tuple(issues)


def solid_volume_issues(measurement, layers, layer_height):
    """Bound only boundary-discretisation uncertainty, not intentional overfill.

    Moving each boundary by epsilon changes area by at most P*epsilon plus
    circular corner terms. Hatch quantisation is a path error, not additional
    permission to overfill. Sparse patterns still cannot exceed the full solid.
    """
    issues = []
    epsilon = BEAD_ENVELOPE_TOLERANCE_MM
    lookup = {(layer.layer_id, r.region_id): r for layer in layers for r in layer.regions}
    for layer_id, region_id, target, commanded, perimeter in measurement.region_volumes:
        region = lookup[(layer_id, region_id)]
        limit = max(
            1e-6,
            (perimeter * epsilon + (1 + len(region.holes)) * math.pi * epsilon**2) * layer_height,
        )
        if commanded > target + limit:
            issues.append(
                _error(
                    "planar.material_exceeds_solid_volume",
                    {
                        "layer_id": layer_id,
                        "region_id": region_id,
                        "target_mm3": target,
                        "commanded_mm3": commanded,
                        "excess_mm3": commanded - target,
                        "boundary_uncertainty_mm3": limit,
                    },
                )
            )
    return tuple(issues)


def spiral_cad_issues(toolpath, model, body_id, transform, *, cancelled=None):
    """Sample the actual selected BRep at intermediate Z and around each bead.

    This independently catches false contour interpolation. The report states
    its spatial/angular resolution; it does not claim a continuous sweep proof.
    """
    shape = model.shapes.get(body_id)
    if shape is None:
        return (_error("planar.spiral_cad_unavailable", {"body_id": body_id}),)
    classifier = BRepClass3d_SolidClassifier(shape)
    count = 0
    max_step = 0.1
    for previous, current in zip(toolpath.points, toolpath.points[1:]):
        if current.point_type != "deposition":
            continue
        if cancelled is not None and cancelled():
            from ..postprocessing.indexed_tube import GenerationCancelled

            raise GenerationCancelled("Planar generation cancelled")
        radius = (current.bead_width_mm or 0.0) / 2
        step = min(max_step, max(radius / 2, 1e-4))
        n = max(1, math.ceil(math.dist(previous.position, current.position) / step))
        if n > 100000:
            return (_error("planar.spiral_cad_sampling_limit", {"point_id": current.point_id}),)
        for sample in range(n + 1):
            centre = tuple(
                a + (b - a) * sample / n for a, b in zip(previous.position, current.position)
            )
            for point in _footprint_samples(centre, radius):
                count += 1
                classifier.Perform(
                    gp_Pnt(*transform.transform_point(point)), BEAD_ENVELOPE_TOLERANCE_MM
                )
                if classifier.State() not in {TopAbs_IN, TopAbs_ON}:
                    return (
                        _error(
                            "planar.spiral_bead_outside_cad",
                            {
                                "point_id": current.point_id,
                                "build_point_mm": list(point),
                                "sample_step_mm": step,
                                "azimuth_samples": 16,
                            },
                        ),
                    )
    return (
        ValidationIssue(
            "planar.spiral_cad_sampled",
            IssueSeverity.WARNING,
            context={
                "samples": count,
                "maximum_step_mm": max_step,
                "azimuth_samples": 16,
                "tolerance_mm": BEAD_ENVELOPE_TOLERANCE_MM,
            },
        ),
    )


def _footprint_samples(centre, radius):
    yield centre
    for index in range(16):
        angle = index * math.tau / 16
        yield (
            centre[0] + radius * math.cos(angle),
            centre[1] + radius * math.sin(angle),
            centre[2],
        )


def _error(code, context):
    return ValidationIssue(code, IssueSeverity.ERROR, context=context)


def operation_geometry_issues(
    model, operation, transform, toolpath, measurement, layers, cancelled
):
    if operation.operation_type == "planar_spiral":
        return spiral_cad_issues(
            toolpath, model, operation.geometry.body.object_id, transform, cancelled=cancelled
        )
    if operation.operation_type == "planar_support":
        return (
            *solid_volume_issues(measurement, layers, operation.parameters.layer_height_mm),
            *support_cad_issues(
                toolpath, model, operation.geometry.body.object_id, transform, cancelled=cancelled
            ),
        )
    return solid_volume_issues(measurement, layers, operation.parameters.layer_height_mm)
