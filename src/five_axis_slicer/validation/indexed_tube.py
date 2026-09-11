"""Geometric, motion, nozzle-envelope, and deposited-IPW checks.

Collision uses conservative spheres at every point in an axisymmetric nozzle
R-Z profile. Motion is subdivided so the sum of tip translation and envelope
rotation per sample does not exceed ``motion_sample_error_mm``. This is an
inspectable approximation, not a thermal or material-deformation simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from ..algorithms.tube.geometry import TubeFeature
from ..algorithms.tube.indexed import IndexedSlicePlan
from ..kinematics.xyzac import MachineAxisTrajectory
from ..manufacturing.resources import NozzleProfile
from ..manufacturing.setup import IssueSeverity, ValidationIssue
from ..manufacturing.toolpath import GeneratedResultStatus, GeneratedToolpath, ToolpathPoint
from ..models import Vector3


@dataclass(frozen=True, slots=True)
class CollisionBox:
    obstacle_id: str
    role: str
    minimum_mm: Vector3
    maximum_mm: Vector3

    def __post_init__(self) -> None:
        if self.role not in {"substrate", "fixture", "machine"}:
            raise ValueError("unsupported collision-box role")
        if any(left > right for left, right in zip(self.minimum_mm, self.maximum_mm)):
            raise ValueError("collision-box bounds are reversed")


@dataclass(frozen=True, slots=True)
class ValidationMetric:
    name: str
    value: float
    limit: float
    unit: str
    passed: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "limit": self.limit,
            "unit": self.unit,
            "passed": self.passed,
        }


@dataclass(frozen=True, slots=True)
class IndexedValidationReport:
    report_id: str
    toolpath_id: str
    trajectory_id: str
    issues: tuple[ValidationIssue, ...]
    metrics: tuple[ValidationMetric, ...]
    collision_samples_checked: int
    motion_sample_error_mm: float

    @property
    def has_errors(self) -> bool:
        return any(issue.severity is IssueSeverity.ERROR for issue in self.issues)

    @property
    def status(self) -> GeneratedResultStatus:
        if self.has_errors:
            return GeneratedResultStatus.ERROR
        if self.issues:
            return GeneratedResultStatus.WARNING
        return GeneratedResultStatus.READY

    @property
    def ready_for_export(self) -> bool:
        return not self.has_errors

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "report_id": self.report_id,
            "toolpath_id": self.toolpath_id,
            "trajectory_id": self.trajectory_id,
            "status": self.status.value,
            "ready_for_export": self.ready_for_export,
            "issues": [issue.to_json() for issue in self.issues],
            "metrics": [metric.to_json() for metric in self.metrics],
            "collision_samples_checked": self.collision_samples_checked,
            "motion_sample_error_mm": self.motion_sample_error_mm,
        }


def validate_indexed_tube(
    feature: TubeFeature,
    plan: IndexedSlicePlan,
    toolpath: GeneratedToolpath,
    trajectory: MachineAxisTrajectory,
    nozzle: NozzleProfile,
    *,
    obstacles: tuple[CollisionBox, ...] = (),
    radial_error_limit_mm: float = 0.01,
    layer_spacing_error_limit_mm: float = 0.01,
    motion_sample_error_mm: float = 0.25,
    check_ipw: bool = True,
) -> IndexedValidationReport:
    if not nozzle.is_ready:
        raise ValueError("collision validation requires a complete Nozzle Profile")
    if len(toolpath.points) != len(trajectory.samples):
        raise ValueError("toolpath and machine trajectory sample counts differ")
    if motion_sample_error_mm <= 0.0:
        raise ValueError("motion_sample_error_mm must be positive")
    metrics = _geometry_metrics(
        feature, plan, toolpath, radial_error_limit_mm, layer_spacing_error_limit_mm
    )
    issues = list(trajectory.issues)
    issues.extend(_metric_issues(metrics))
    collision_issues, checked = _collision_issues(
        toolpath,
        nozzle,
        obstacles,
        motion_sample_error_mm,
        check_ipw=check_ipw,
    )
    issues.extend(collision_issues)
    return IndexedValidationReport(
        f"{toolpath.toolpath_id}-validation-v1",
        toolpath.toolpath_id,
        trajectory.trajectory_id,
        tuple(_unique_issues(issues)),
        tuple(metrics),
        checked,
        float(motion_sample_error_mm),
    )


def _geometry_metrics(
    feature: TubeFeature,
    plan: IndexedSlicePlan,
    toolpath: GeneratedToolpath,
    radial_limit: float,
    spacing_limit: float,
) -> list[ValidationMetric]:
    layer_centers = {layer.layer_id: layer.plane_origin for layer in plan.layers}
    radial_errors = [
        abs(math.dist(point.position, layer_centers[point.layer_id]) - feature.path_radius_mm)
        for point in toolpath.points
        if point.point_type == "deposition" and point.layer_id in layer_centers
    ]
    expected_centers = _expected_layer_centers(
        feature.centerline_length_mm,
        plan.nominal_layer_height_mm,
    )
    spacing_errors = [
        abs(layer.centerline_distance_mm - expected)
        for layer, expected in zip(plan.layers, expected_centers)
    ]
    wedge_errors = [region.maximum_height_error_mm for region in plan.regions]
    return [
        _metric("maximum_radial_error", radial_errors, radial_limit, "mm"),
        _metric("maximum_layer_spacing_error", spacing_errors, spacing_limit, "mm"),
        ValidationMetric(
            "maximum_wedge_height_error",
            max(wedge_errors, default=0.0),
            max(wedge_errors, default=0.0),
            "mm",
            True,
        ),
    ]


def _metric(name: str, values: list[float], limit: float, unit: str) -> ValidationMetric:
    value = max(values, default=0.0)
    return ValidationMetric(name, value, float(limit), unit, value <= limit + 1.0e-12)


def _expected_layer_centers(length: float, height: float) -> tuple[float, ...]:
    count = max(1, math.ceil(length / height))
    return tuple(
        (index * height + min(length, (index + 1) * height)) * 0.5 for index in range(count)
    )


def _metric_issues(metrics: list[ValidationMetric]) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            f"tube.{metric.name}_exceeded",
            IssueSeverity.ERROR,
            metric.name,
            {"value": metric.value, "limit": metric.limit, "unit": metric.unit},
        )
        for metric in metrics
        if not metric.passed
    ]


def _collision_issues(
    toolpath: GeneratedToolpath,
    nozzle: NozzleProfile,
    obstacles: tuple[CollisionBox, ...],
    sample_error: float,
    *,
    check_ipw: bool,
) -> tuple[list[ValidationIssue], int]:
    issues: list[ValidationIssue] = []
    checked = 0
    deposited: list[tuple[Vector3, Vector3, float, str]] = []
    for segment_index, (left, right) in enumerate(zip(toolpath.points, toolpath.points[1:])):
        samples = _motion_samples(left, right, nozzle, sample_error)
        for motion_index, (position, axis) in enumerate(samples):
            checked += 1
            for profile_index, (radius, z_value) in enumerate(nozzle.outer_profile_rz_mm):
                center = _subtract(position, _scale(axis, z_value))
                for obstacle in obstacles:
                    if _allowed_substrate_contact(
                        obstacle,
                        left,
                        right,
                        profile_index,
                        at_segment_start=motion_index == 0,
                    ):
                        continue
                    if _sphere_box_intersects(center, radius, obstacle):
                        issues.append(
                            _collision_issue(
                                "obstacle", right.point_id, obstacle.obstacle_id, segment_index
                            )
                        )
                if check_ipw and profile_index > 0:
                    for start, end, bead_radius, source_id in deposited[:-2]:
                        if _point_segment_distance(center, start, end) <= radius + bead_radius:
                            issues.append(
                                _collision_issue("ipw", right.point_id, source_id, segment_index)
                            )
                            break
        if right.point_type == "deposition":
            radius = max(right.bead_width_mm or 0.0, right.layer_height_mm or 0.0) * 0.5
            deposited.append((left.position, right.position, radius, right.point_id))
    return issues, checked


def _motion_samples(
    left: ToolpathPoint,
    right: ToolpathPoint,
    nozzle: NozzleProfile,
    sample_error: float,
) -> tuple[tuple[Vector3, Vector3], ...]:
    dot = max(-1.0, min(1.0, _dot(left.nozzle_axis, right.nozzle_axis)))
    angle = math.acos(dot)
    reach = max(
        (math.hypot(radius, z_value) for radius, z_value in nozzle.outer_profile_rz_mm), default=0.0
    )
    motion_bound = math.dist(left.position, right.position) + angle * reach
    count = max(1, math.ceil(motion_bound / sample_error))
    result: list[tuple[Vector3, Vector3]] = []
    for index in range(count + 1):
        fraction = index / count
        position = _add(left.position, _scale(_subtract(right.position, left.position), fraction))
        axis = _unit(
            _add(_scale(left.nozzle_axis, 1.0 - fraction), _scale(right.nozzle_axis, fraction))
        )
        result.append((position, axis))
    return tuple(result)


def _allowed_substrate_contact(
    obstacle: CollisionBox,
    left: ToolpathPoint,
    right: ToolpathPoint,
    profile_index: int,
    *,
    at_segment_start: bool,
) -> bool:
    return (
        obstacle.role == "substrate"
        and profile_index == 0
        and (
            right.point_type == "deposition"
            or (at_segment_start and left.point_type == "deposition")
        )
    )


def _sphere_box_intersects(center: Vector3, radius: float, box: CollisionBox) -> bool:
    distance_sq = 0.0
    for value, low, high in zip(center, box.minimum_mm, box.maximum_mm):
        nearest = min(high, max(low, value))
        distance_sq += (value - nearest) ** 2
    return distance_sq <= radius * radius


def _point_segment_distance(point: Vector3, start: Vector3, end: Vector3) -> float:
    span = _subtract(end, start)
    length_sq = _dot(span, span)
    if length_sq <= 1.0e-18:
        return math.dist(point, start)
    fraction = max(0.0, min(1.0, _dot(_subtract(point, start), span) / length_sq))
    return math.dist(point, _add(start, _scale(span, fraction)))


def _collision_issue(kind: str, point_id: str, target_id: str, index: int) -> ValidationIssue:
    return ValidationIssue(
        f"tube.nozzle_{kind}_collision",
        IssueSeverity.ERROR,
        point_id,
        {"target_id": target_id, "segment_index": index},
    )


def _unique_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    result: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        target = str(issue.context.get("target_id", ""))
        key = (issue.code, issue.object_id, target)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def _unit(value: Vector3) -> Vector3:
    length = math.sqrt(_dot(value, value))
    if length <= 1.0e-12:
        raise ValueError("opposed nozzle axes require an explicit intermediate pose")
    return _scale(value, 1.0 / length)


def _add(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a + b for a, b in zip(left, right))  # type: ignore[return-value]


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(left, right))  # type: ignore[return-value]


def _scale(value: Vector3, factor: float) -> Vector3:
    return tuple(item * factor for item in value)  # type: ignore[return-value]


def _dot(left: Vector3, right: Vector3) -> float:
    return sum(a * b for a, b in zip(left, right))


__all__ = [
    "CollisionBox",
    "IndexedValidationReport",
    "ValidationMetric",
    "validate_indexed_tube",
]
