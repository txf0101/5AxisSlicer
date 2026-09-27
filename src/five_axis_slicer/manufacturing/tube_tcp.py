"""Explicit one-way conversion of Indexed Tube bead centers to nozzle TCPs.

This adapter accepts only the approach/deposition/depart/travel connection
sequence emitted by Tube's Indexed builder. It is not a generic path adapter.
The caller must retain the original centerline for material-volume geometry.
"""

from dataclasses import replace
import math

from .toolpath import GeneratedToolpath, ToolpathPoint


def indexed_centerline_to_tcp(toolpath: GeneratedToolpath) -> GeneratedToolpath:
    """Offset toward the nozzle by half the associated deposited layer height.

    Call exactly once on an Indexed centerline path. The returned path retains
    IDs and metadata and does not itself carry a repeat-conversion marker.
    """
    _validate_sequence(toolpath.points)
    following = _following_deposition(toolpath.points)
    previous: ToolpathPoint | None = None
    reference: ToolpathPoint | None
    converted = []
    for index, point in enumerate(toolpath.points):
        if point.point_type == "deposition":
            reference = point
            previous = point
        elif point.point_type == "depart":
            reference = previous
        else:
            reference = following[index]
        if reference is None:
            raise ValueError(f"Indexed point {point.point_id} has no associated deposition")
        # Variable-height open paths must retain their start thickness at the
        # approach point; the first deposition endpoint may have another height.
        height = point.layer_height_mm if point.layer_height_mm is not None else reference.layer_height_mm
        if height is None or not math.isfinite(height) or height <= 0:
            raise ValueError(f"Indexed deposition {reference.point_id} requires layer height")
        axis_length = math.sqrt(sum(value * value for value in point.nozzle_axis))
        if not math.isfinite(axis_length) or axis_length <= 1e-12:
            raise ValueError(f"Indexed point {point.point_id} requires a finite nozzle axis")
        position = tuple(
            value - axis / axis_length * height / 2
            for value, axis in zip(point.position, point.nozzle_axis, strict=True)
        )
        converted.append(replace(point, position=(position[0], position[1], position[2])))
    return replace(toolpath, points=tuple(converted))


def _validate_sequence(points: tuple[ToolpathPoint, ...]) -> None:
    if not points:
        raise ValueError("Indexed centerline requires approach and deposition points")
    allowed = {
        None: {"approach"},
        "approach": {"deposition"},
        "deposition": {"deposition", "depart"},
        "depart": {"travel"},
        "travel": {"approach"},
    }
    previous = None
    for point in points:
        if point.point_type not in allowed[previous]:
            raise ValueError(f"Unsupported Indexed connection at {point.point_id}")
        previous = point.point_type
    if previous != "deposition":
        raise ValueError("Indexed centerline must end with deposition")


def _following_deposition(points: tuple[ToolpathPoint, ...]) -> list[ToolpathPoint | None]:
    following: list[ToolpathPoint | None] = [None] * len(points)
    reference = None
    for index in range(len(points) - 1, -1, -1):
        if points[index].point_type == "deposition":
            reference = points[index]
        following[index] = reference
    return following
