"""Continuous helical tube paths using Wang et al. (2008), Table I RMF.

Frames use double reflection, independently implemented from the published
equations. The STEP recogniser still accepts G1 line/arc chains; the frame
function also accepts sampled spatial curves with their analytic tangents.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace

from ...kinematics.xyzac import MachineAxisTrajectory, solve_xyzac_trajectory
from ...manufacturing.coordinates import RigidTransform
from ...manufacturing.machine import MachineProfile
from ...manufacturing.resources import NozzleProfile
from ...manufacturing.setup import IssueSeverity, TubeProcessParameters, ValidationIssue
from ...manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from ...models import Vector3
from ...validation.indexed_tube import (
    CollisionBox,
    IndexedValidationReport,
    ValidationMetric,
    _collision_issues,
    _metric_issues,
    _unique_issues,
)
from .geometry import TubeFeature
from .indexed import TubePlanningError


@dataclass(frozen=True, slots=True)
class RotationMinimizingFrame:
    origin: Vector3
    tangent: Vector3
    normal: Vector3
    binormal: Vector3


def rotation_minimizing_frames(
    points: Sequence[Vector3],
    tangents: Sequence[Vector3],
    *,
    initial_normal: Vector3 | None = None,
) -> tuple[RotationMinimizingFrame, ...]:
    """Transport an orthonormal right-handed frame without curvature division.

    Repeated samples, opposite tangents and an initial normal parallel to the
    tangent are rejected explicitly; silently choosing a frame there would
    hide an ambiguous seam or a cusp.
    """
    if len(points) != len(tangents) or len(points) < 2:
        raise TubePlanningError("tube.rmf_samples_invalid", "need matching samples >= 2")
    origins = tuple(_finite_vector(point) for point in points)
    directions = tuple(_unit(tangent) for tangent in tangents)
    direction = directions[0]
    reference = initial_normal
    if reference is None:
        basis: tuple[Vector3, ...] = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        reference = min(basis, key=lambda value: abs(_dot(value, direction)))
    reference = _finite_vector(reference)
    normal = _unit(_sub(reference, _scale(direction, _dot(reference, direction))))
    frames = [RotationMinimizingFrame(origins[0], direction, normal, _cross(direction, normal))]
    for index in range(1, len(origins)):
        chord = _sub(origins[index], origins[index - 1])
        chord_sq = _dot(chord, chord)
        if chord_sq <= 1.0e-20:
            raise TubePlanningError("tube.rmf_duplicate_point", str(index))
        next_direction = directions[index]
        if _dot(direction, next_direction) <= -1.0 + 1.0e-8:
            raise TubePlanningError("tube.rmf_tangent_reversal", str(index))
        reflected_normal = _sub(normal, _scale(chord, 2.0 * _dot(chord, normal) / chord_sq))
        reflected_tangent = _sub(direction, _scale(chord, 2.0 * _dot(chord, direction) / chord_sq))
        second = _sub(next_direction, reflected_tangent)
        second_sq = _dot(second, second)
        normal = reflected_normal
        if second_sq > 1.0e-20:
            normal = _sub(normal, _scale(second, 2.0 * _dot(second, normal) / second_sq))
        direction = next_direction
        normal = _unit(_sub(normal, _scale(direction, _dot(normal, direction))))
        frames.append(
            RotationMinimizingFrame(origins[index], direction, normal, _cross(direction, normal))
        )
    return tuple(frames)


def generate_continuous_toolpath(
    operation_id: str,
    feature: TubeFeature,
    parameters: TubeProcessParameters,
    *,
    seam_angle_rad: float = 0.0,
) -> GeneratedToolpath:
    """Generate one uninterrupted helix, with layer height as axial pitch.

    Layer IDs track complete turns, with a partial final turn reaching the
    exit. A single start seam avoids one retract/prime pair per layer. There
    is an explicit approach and final retract/depart, carrying zero material.
    """
    if not math.isfinite(seam_angle_rad):
        raise TubePlanningError("tube.continuous_seam_invalid", "seam must be finite")
    if parameters.safe_clearance_mm < max(parameters.bead_width_mm, parameters.layer_height_mm):
        raise TubePlanningError("tube.safe_connection_clearance_insufficient", "bead envelope")
    _check_centerline(feature)
    distances = _continuous_distances(feature, parameters)
    positions, normals = _helix_geometry(feature, parameters, distances, seam_angle_rad)
    points = _helix_points(operation_id, parameters, distances, positions, normals)
    events = _add_clearance_and_events(operation_id, parameters, points, normals)
    return GeneratedToolpath(
        f"{operation_id}-continuous-v1", operation_id, points=tuple(points), events=events
    )


def _continuous_distances(feature: TubeFeature, parameters: TubeProcessParameters) -> list[float]:
    radius = feature.path_radius_mm
    pitch = parameters.layer_height_mm
    length = feature.centerline_length_mm
    # Bound circumferential and centreline bending contributions separately.
    angular_step = min(
        math.pi / 12.0,
        2.0 * math.acos(max(-1.0, 1.0 - min(1.0, parameters.contour_chord_error_mm / radius / 2))),
    )
    step = pitch * angular_step / (2.0 * math.pi)
    for primitive in feature.centerline:
        if primitive.kind == "arc":
            bend_radius = primitive.length_mm / abs(primitive.sweep_rad)
            step = min(step, math.sqrt(4.0 * parameters.contour_chord_error_mm * bend_radius))
    count = max(2, math.ceil(length / step))
    if count > 250_000:
        raise TubePlanningError("tube.continuous_sampling_limit", str(count))
    distances = {length * index / count for index in range(count + 1)}
    walked = 0.0
    for primitive in feature.centerline[:-1]:
        walked += primitive.length_mm
        distances.add(walked)
    return sorted(distances)


def _helix_geometry(
    feature: TubeFeature,
    parameters: TubeProcessParameters,
    distances: list[float],
    seam_angle_rad: float,
) -> tuple[list[Vector3], list[Vector3]]:
    samples = [feature.point_tangent_at(distance) for distance in distances]
    frames = rotation_minimizing_frames([x[0] for x in samples], [x[1] for x in samples])
    positions: list[Vector3] = []
    normals: list[Vector3] = []
    for distance, frame in zip(distances, frames, strict=True):
        angle = seam_angle_rad + 2.0 * math.pi * distance / parameters.layer_height_mm
        normal = _add(
            _scale(frame.normal, math.cos(angle)), _scale(frame.binormal, math.sin(angle))
        )
        positions.append(_add(frame.origin, _scale(normal, feature.path_radius_mm)))
        normals.append(normal)
    return positions, normals


def _helix_points(
    operation_id: str,
    parameters: TubeProcessParameters,
    distances: list[float],
    positions: list[Vector3],
    normals: list[Vector3],
) -> list[ToolpathPoint]:
    pitch = parameters.layer_height_mm
    points: list[ToolpathPoint] = []
    layer_count = max(1, math.ceil(distances[-1] / pitch))
    for index, (position, normal, distance) in enumerate(
        zip(positions, normals, distances, strict=True)
    ):
        left, right = max(0, index - 1), min(len(positions) - 1, index + 1)
        tangent = _unit(_sub(positions[right], positions[left]))
        deposition = index > 0
        points.append(
            ToolpathPoint(
                point_id=f"point-{index + 2:07d}",
                position=position,
                tangent=tangent,
                nozzle_axis=_scale(normal, -1.0),
                surface_normal=normal,
                operation_id=operation_id,
                stage_id="continuous",
                layer_id=f"layer-{min(layer_count, int(distance / pitch) + 1):05d}",
                region_id="continuous",
                point_type="deposition" if deposition else "approach",
                extrusion_role="thin_wall" if deposition else "none",
                feedrate_mm_min=(
                    parameters.deposition_feedrate_mm_min
                    if deposition
                    else parameters.travel_feedrate_mm_min
                ),
                bead_width_mm=parameters.bead_width_mm if deposition else None,
                layer_height_mm=pitch if deposition else None,
                material_volume_mm3=(
                    math.dist(positions[index - 1], position) * parameters.bead_width_mm * pitch
                    if deposition
                    else 0.0
                ),
            )
        )
    return points


def _add_clearance_and_events(
    operation_id: str,
    parameters: TubeProcessParameters,
    points: list[ToolpathPoint],
    normals: list[Vector3],
) -> tuple[ToolpathEvent, ...]:
    points.insert(
        0,
        replace(
            points[0],
            point_id="point-0000001",
            position=_add(points[0].position, _scale(normals[0], parameters.safe_clearance_mm)),
            point_type="travel",
        ),
    )
    final = points[-1]
    points.append(
        replace(
            final,
            point_id=f"point-{len(points) + 1:07d}",
            position=_add(final.position, _scale(normals[-1], parameters.safe_clearance_mm)),
            point_type="depart",
            extrusion_role="none",
            material_volume_mm3=0.0,
            bead_width_mm=None,
            layer_height_mm=None,
            feedrate_mm_min=parameters.travel_feedrate_mm_min,
        )
    )
    return tuple(
        ToolpathEvent(
            event_id=f"event-{index + 1:07d}",
            event_type=kind,
            operation_id=operation_id,
            stage_id="continuous",
            context={"sequence_index": sequence, "extrusion_length_mm": amount},
        )
        for index, (kind, sequence, amount) in enumerate(
            (
                ("prime", 2, parameters.retract_length_mm),
                ("retract", len(points) - 1, -parameters.retract_length_mm),
            )
        )
    )


def solve_continuous_xyzac_trajectory(
    toolpath: GeneratedToolpath,
    profile: MachineProfile,
    *,
    tool_length_mm: float = 0.0,
    T_workpiece_from_build: RigidTransform | None = None,
) -> MachineAxisTrajectory:
    """Reject branch changes that would unwind an axis during deposition."""
    trajectory = solve_xyzac_trajectory(
        toolpath,
        profile,
        tool_length_mm=tool_length_mm,
        T_workpiece_from_build=T_workpiece_from_build,
    )
    issues = list(trajectory.issues)
    for index, (left, right) in enumerate(
        zip(trajectory.samples, trajectory.samples[1:], strict=False), 1
    ):
        if toolpath.points[index].point_type != "deposition":
            continue
        if (
            abs(right.joint_positions["C"] - left.joint_positions["C"]) > math.pi
            or abs(right.joint_positions["A"] - left.joint_positions["A"]) > math.pi / 2
        ):
            issues.append(
                ValidationIssue(
                    "tube.continuous_rotary_discontinuity",
                    IssueSeverity.ERROR,
                    right.source_point_id,
                    {"segment_index": index},
                )
            )
    return replace(trajectory, issues=tuple(issues))


def validate_continuous_tube(
    feature: TubeFeature,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    nozzle: NozzleProfile,
    *,
    obstacles: tuple[CollisionBox, ...] = (),
    radial_error_limit_mm: float = 0.01,
    motion_sample_error_mm: float = 0.25,
    check_ipw: bool = True,
) -> IndexedValidationReport:
    """Check radial geometry and all deposition/approach/depart motions."""
    if (
        not nozzle.is_ready
        or not math.isfinite(motion_sample_error_mm)
        or motion_sample_error_mm <= 0
    ):
        raise ValueError("complete nozzle and finite positive motion sample error required")
    if not toolpath.points or len(toolpath.points) != len(trajectory.samples):
        raise ValueError("nonempty matching toolpath and trajectory required")
    if trajectory.source_toolpath_id != toolpath.toolpath_id or any(
        point.point_id != sample.source_point_id
        for point, sample in zip(toolpath.points, trajectory.samples, strict=False)
    ):
        raise ValueError("machine trajectory does not correspond to toolpath")
    errors = [
        abs(_centerline_distance(feature, point.position) - feature.path_radius_mm)
        for point in toolpath.points
        if point.point_type == "deposition"
    ]
    radial = max(errors, default=math.inf)
    metrics = [
        ValidationMetric(
            "maximum_radial_error",
            radial,
            radial_error_limit_mm,
            "mm",
            radial <= radial_error_limit_mm,
        )
    ]
    issues = list(trajectory.issues)
    issues.extend(_metric_issues(metrics))
    collision, checked = _collision_issues(
        toolpath,
        nozzle,
        obstacles,
        motion_sample_error_mm,
        check_ipw=check_ipw,
    )
    issues.extend(collision)
    return IndexedValidationReport(
        f"{toolpath.toolpath_id}-validation-v1",
        toolpath.toolpath_id,
        trajectory.trajectory_id,
        tuple(_unique_issues(issues)),
        tuple(metrics),
        checked,
        motion_sample_error_mm,
    )


def _check_centerline(feature: TubeFeature) -> None:
    for left, right in zip(feature.centerline, feature.centerline[1:], strict=False):
        if _dot(left.point_tangent(1.0)[1], right.point_tangent(0.0)[1]) < 1.0 - 1.0e-6:
            raise TubePlanningError("tube.continuous_centerline_not_smooth", right.source_face_id)
    for primitive in feature.centerline:
        if primitive.kind == "arc":
            if abs(primitive.sweep_rad) < 1.0e-12:
                raise TubePlanningError("tube.continuous_arc_invalid", primitive.source_face_id)
            radius = primitive.length_mm / abs(primitive.sweep_rad)
            if radius <= feature.outer_radius_mm:
                raise TubePlanningError(
                    "tube.continuous_curvature_too_high", primitive.source_face_id
                )


def _centerline_distance(feature: TubeFeature, position: Vector3) -> float:
    distances: list[float] = []
    for primitive in feature.centerline:
        if primitive.kind == "line":
            span = _sub(primitive.end, primitive.start)
            fraction = max(
                0.0, min(1.0, _dot(_sub(position, primitive.start), span) / _dot(span, span))
            )
            distances.append(math.dist(position, _add(primitive.start, _scale(span, fraction))))
        else:
            assert primitive.center is not None and primitive.axis is not None
            radial = _sub(primitive.start, primitive.center)
            offset = _sub(position, primitive.center)
            angle = math.atan2(_dot(primitive.axis, _cross(radial, offset)), _dot(radial, offset))
            candidates = [0.0, 1.0]
            for turn in range(-2, 3):
                fraction = (angle + turn * 2 * math.pi) / primitive.sweep_rad
                if 0 <= fraction <= 1:
                    candidates.append(fraction)
            distances.append(
                min(math.dist(position, primitive.point_tangent(f)[0]) for f in candidates)
            )
    return min(distances)


def _finite_vector(value: Vector3) -> Vector3:
    if len(value) != 3 or not all(math.isfinite(component) for component in value):
        raise TubePlanningError("tube.rmf_vector_invalid", str(value))
    return value


def _unit(value: Vector3) -> Vector3:
    value = _finite_vector(value)
    length = math.sqrt(_dot(value, value))
    if length <= 1.0e-12:
        raise TubePlanningError("tube.rmf_zero_direction", str(value))
    return _scale(value, 1.0 / length)


def _add(left: Vector3, right: Vector3) -> Vector3:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def _sub(left: Vector3, right: Vector3) -> Vector3:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _scale(value: Vector3, factor: float) -> Vector3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )
