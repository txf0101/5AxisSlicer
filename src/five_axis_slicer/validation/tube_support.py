"""Necessary endpoint contact checks at indexed tube region transitions.

Passing this conservative envelope test does not establish complete support,
bead stability, or printability. Only previously deposited material is used.
"""

from __future__ import annotations

from collections.abc import Callable
import math

import numpy as np

from ..manufacturing.setup import IssueSeverity, ValidationIssue
from ..manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from ..models import Vector3


def transition_support_issues(
    toolpath: GeneratedToolpath,
    *,
    substrate_bounds: tuple[tuple[Vector3, Vector3], ...] = (),
    checkpoint: Callable[[], None] | None = None,
) -> tuple[ValidationIssue, ...]:
    """Check transition-layer endpoints against prior bead bounding envelopes.

    A bead is enclosed by a sphere swept along its centerline, with radius
    hypot(width/2, height/2). Substrate boxes are conservative solid envelopes.
    No contact means a necessary support condition fails; contact is not proof
    of adequate support. Current-layer segments never count as prior support.
    """
    deposition, targets, issues, segment_data = _scan_deposition(toolpath.points, checkpoint)
    boxes = _substrate_boxes(substrate_bounds)
    arrays = _segment_arrays(segment_data)
    for index, point, radius in deposition:
        if (point.region_id, point.layer_id) not in targets:
            continue
        if checkpoint is not None:
            checkpoint()
        position = np.asarray(point.position)
        if any(
            np.linalg.norm(position - np.clip(position, low, high)) <= radius + 1e-8
            for low, high in boxes
        ):
            continue
        eligible = (arrays[4] < index) & (arrays[5] != point.layer_id)
        chosen = np.flatnonzero(eligible)
        supported, best = _closest_contact(position, radius, chosen, arrays, checkpoint)
        if not supported:
            issues.append(_gap_issue(point, best, len(chosen)))
    return tuple(issues)


def _valid_dimensions(width, height) -> bool:
    return all(
        value is not None and math.isfinite(value) and value > 0 for value in (width, height)
    )


def _dimension_issue(point: ToolpathPoint) -> ValidationIssue:
    return ValidationIssue(
        "tube.transition_support_dimensions_missing",
        IssueSeverity.ERROR,
        point.point_id,
        {"layer_id": point.layer_id, "region_id": point.region_id},
    )


def _scan_deposition(points, checkpoint):
    issues: list[ValidationIssue] = []
    starts, ends, radii, indices, layers = [], [], [], [], []
    targets: set[tuple[str, str]] = set()
    previous_region = None
    deposition = []
    for index, point in enumerate(points):
        if checkpoint is not None and index % 128 == 0:
            checkpoint()
        if point.point_type != "deposition":
            continue
        if previous_region is not None and point.region_id != previous_region:
            targets.add((point.region_id, point.layer_id))
        previous_region = point.region_id
        width, height = point.bead_width_mm, point.layer_height_mm
        if not _valid_dimensions(width, height):
            issues.append(_dimension_issue(point))
            continue
        radius = math.hypot(width / 2, height / 2)
        deposition.append((index, point, radius))
        if index:
            starts.append(points[index - 1].position)
            ends.append(point.position)
            start = points[index - 1]
            # A linearly changing cross-section is enclosed by the larger
            # endpoint radius. Legacy constant-width approaches omit dimensions.
            start_radius = (math.hypot(start.bead_width_mm / 2, start.layer_height_mm / 2)
                            if _valid_dimensions(start.bead_width_mm, start.layer_height_mm) else radius)
            radii.append(max(radius, start_radius))
            indices.append(index)
            layers.append(point.layer_id)
    return deposition, targets, issues, (starts, ends, radii, indices, layers)


def _substrate_boxes(substrate_bounds):
    boxes = []
    for low, high in substrate_bounds:
        low_array, high_array = np.asarray(low, dtype=float), np.asarray(high, dtype=float)
        if (
            low_array.shape != (3,)
            or high_array.shape != (3,)
            or not np.isfinite(low_array).all()
            or not np.isfinite(high_array).all()
            or np.any(low_array > high_array)
        ):
            raise ValueError("substrate bounds must be finite ordered XYZ triples")
        boxes.append((low_array, high_array))
    return boxes


def _segment_arrays(segment_data):
    starts, ends, radii, indices, layers = segment_data
    start_array = np.asarray(starts, dtype=float).reshape((-1, 3))
    vectors = np.asarray(ends, dtype=float).reshape((-1, 3)) - start_array
    lengths_sq = np.einsum("ij,ij->i", vectors, vectors)
    radius_array = np.asarray(radii)
    index_array = np.asarray(indices)
    layer_array = np.asarray(layers)
    return start_array, vectors, lengths_sq, radius_array, index_array, layer_array


def _closest_contact(position, radius, chosen, arrays, checkpoint):
    start_array, vectors, lengths_sq, radius_array, _, _ = arrays
    best = None
    supported = False
    for offset in range(0, len(chosen), 4096):
        if checkpoint is not None:
            checkpoint()
        selection = chosen[offset : offset + 4096]
        span = vectors[selection]
        delta = position - start_array[selection]
        fractions = np.clip(
            np.einsum("ij,ij->i", delta, span) / np.maximum(lengths_sq[selection], 1e-30),
            0,
            1,
        )
        distances = np.linalg.norm(delta - fractions[:, None] * span, axis=1)
        limits = radius + radius_array[selection]
        clearance = distances - limits
        if np.any(clearance <= 1e-8):
            supported = True
            break
        local = int(np.argmin(clearance))
        candidate = (float(clearance[local]), float(distances[local]), float(limits[local]))
        if best is None or candidate[0] < best[0]:
            best = candidate
    return supported, best


def _gap_issue(point: ToolpathPoint, best, prior_segment_count: int) -> ValidationIssue:
    return ValidationIssue(
        "tube.transition_support_gap",
        IssueSeverity.ERROR,
        point.point_id,
        {
            "point_id": point.point_id,
            "layer_id": point.layer_id,
            "region_id": point.region_id,
            "distance_mm": None if best is None else best[1],
            "limit_mm": None if best is None else best[2],
            "prior_segment_count": int(prior_segment_count),
            "criterion": "necessary_endpoint_envelope_contact",
        },
    )
