"""Pure geometry planning for Rotary additive operations.

Lengths are millimetres and angles are radians.  Input rotary geometry is in
Source coordinates.  Returned points are in the workpiece Build frame after
the optional rigid transform has been applied.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import math

from ...manufacturing.coordinates import RigidTransform
from ...manufacturing.rotary_parameters import (
    RotaryAngularRegion,
    RotaryFrame,
    RotaryGeometrySelection,
    RotaryOperationDefinition,
    RotaryProfile,
)
from ...manufacturing.toolpath import ToolpathEvent

Vector3 = tuple[float, float, float]
CancelCheck = Callable[[], bool]
_EPSILON = 1.0e-10


class RotaryPlanningError(ValueError):
    """A stable, user-locatable Rotary planning failure."""

    def __init__(self, code: str, *context: str) -> None:
        self.code = str(code)
        self.context = tuple(str(item) for item in context)
        detail = ": ".join((self.code, *self.context))
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class RotaryRegionSpan:
    """One analysed, continuously unwrapped angular region."""

    region_id: str
    start_angle_rad: float
    end_angle_rad: float
    direction: str

    @property
    def sweep_rad(self) -> float:
        return self.end_angle_rad - self.start_angle_rad


@dataclass(frozen=True, slots=True)
class RotaryRegionAnalysis:
    """Kernel-independent interpretation of selected edges/faces.

    This result is also suitable for a region-only preview.  It deliberately
    retains the stable references in ``selection`` rather than replacing them
    with transient topology indices.
    """

    selection: RotaryGeometrySelection
    axis_origin_mm: Vector3
    axis_direction: Vector3
    zero_direction: Vector3
    transverse_direction: Vector3
    spans: tuple[RotaryRegionSpan, ...]
    preview_only: bool
    issues: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RotaryPlanPoint:
    """A plan point with the prescribed continuous rotary coordinate."""

    point_id: str
    position: Vector3
    tangent: Vector3
    surface_normal: Vector3
    nozzle_axis: Vector3
    unwrapped_angle_rad: float
    axial_mm: float
    radius_mm: float
    stage_id: str
    layer_id: str
    region_id: str
    point_type: str
    extrusion_role: str = "none"
    feedrate_mm_min: float | None = None
    bead_width_mm: float | None = None
    layer_height_mm: float | None = None
    material_volume_mm3: float = 0.0


@dataclass(frozen=True, slots=True)
class RotaryPathDefinition:
    """One deposition stripe or loop inside a Rotary plan."""

    path_id: str
    layer_id: str
    region_id: str
    start_point_index: int
    end_point_index: int
    start_angle_rad: float
    end_angle_rad: float
    direction: str
    reversed_from_declared: bool


@dataclass(frozen=True, slots=True)
class RotaryPlan:
    """Machine-independent Rotary slice plan.

    ``points`` and the generated Toolpath are intentionally one-to-one.  This
    makes ``unwrapped_angle_rad`` a prescribed machine coordinate rather than
    an angle that a generic IK solver may replace with another branch.
    """

    operation_id: str
    operation_type: str
    points: tuple[RotaryPlanPoint, ...]
    events: tuple[ToolpathEvent, ...]
    paths: tuple[RotaryPathDefinition, ...]
    region_analysis: RotaryRegionAnalysis
    issues: tuple[str, ...] = ()

    @property
    def samples(self) -> tuple[RotaryPlanPoint, ...]:
        return self.points

    @property
    def angle_by_point_id(self) -> Mapping[str, float]:
        return {point.point_id: point.unwrapped_angle_rad for point in self.points}

    @property
    def total_length_mm(self) -> float:
        """Length of all geometric moves, including structured connections."""

        return sum(
            math.dist(previous.position, current.position)
            for previous, current in zip(self.points, self.points[1:], strict=False)
        )

    @property
    def deposition_length_mm(self) -> float:
        """Length of segments whose destination point deposits material."""

        return sum(
            math.dist(previous.position, current.position)
            for previous, current in zip(self.points, self.points[1:], strict=False)
            if current.point_type == "deposition"
        )

    @property
    def material_volume_mm3(self) -> float:
        return sum(point.material_volume_mm3 for point in self.points)

    def to_json(self) -> dict[str, object]:
        """Return the inspectable plan payload stored beside generated output."""

        return {
            "schema_version": 1,
            "plan_id": f"{self.operation_id}-{self.operation_type}-plan-v1",
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "coordinate_frame": "workpiece_build",
            "units": {"length": "mm", "angle": "rad", "volume": "mm3"},
            "total_length_mm": self.total_length_mm,
            "deposition_length_mm": self.deposition_length_mm,
            "material_volume_mm3": self.material_volume_mm3,
            "issues": list(self.issues),
            "region_analysis": {
                "selection": self.region_analysis.selection.to_json(),
                "axis_origin_mm": list(self.region_analysis.axis_origin_mm),
                "axis_direction": list(self.region_analysis.axis_direction),
                "zero_direction": list(self.region_analysis.zero_direction),
                "transverse_direction": list(self.region_analysis.transverse_direction),
                "preview_only": self.region_analysis.preview_only,
                "issues": list(self.region_analysis.issues),
                "spans": [
                    {
                        "region_id": span.region_id,
                        "start_angle_rad": span.start_angle_rad,
                        "end_angle_rad": span.end_angle_rad,
                        "sweep_rad": span.sweep_rad,
                        "direction": span.direction,
                    }
                    for span in self.region_analysis.spans
                ],
            },
            "paths": [
                {
                    "path_id": path.path_id,
                    "layer_id": path.layer_id,
                    "region_id": path.region_id,
                    "start_point_index": path.start_point_index,
                    "end_point_index": path.end_point_index,
                    "start_angle_rad": path.start_angle_rad,
                    "end_angle_rad": path.end_angle_rad,
                    "direction": path.direction,
                    "reversed_from_declared": path.reversed_from_declared,
                }
                for path in self.paths
            ],
            "points": [
                {
                    "point_id": point.point_id,
                    "position": list(point.position),
                    "tangent": list(point.tangent),
                    "surface_normal": list(point.surface_normal),
                    "nozzle_axis": list(point.nozzle_axis),
                    "unwrapped_angle_rad": point.unwrapped_angle_rad,
                    "axial_mm": point.axial_mm,
                    "radius_mm": point.radius_mm,
                    "stage_id": point.stage_id,
                    "layer_id": point.layer_id,
                    "region_id": point.region_id,
                    "point_type": point.point_type,
                    "extrusion_role": point.extrusion_role,
                    "feedrate_mm_min": point.feedrate_mm_min,
                    "bead_width_mm": point.bead_width_mm,
                    "layer_height_mm": point.layer_height_mm,
                    "material_volume_mm3": point.material_volume_mm3,
                }
                for point in self.points
            ],
            "events": [event.to_json() for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class _SurfaceSample:
    position: Vector3
    tangent: Vector3
    normal: Vector3
    angle_rad: float
    axial_mm: float
    radius_mm: float


@dataclass(frozen=True, slots=True)
class _DepositionPath:
    layer_id: str
    region_id: str
    samples: tuple[_SurfaceSample, ...]
    extrusion_role: str
    bead_width_mm: float | None = None


def analyse_rotary_region(
    selection: RotaryGeometrySelection,
    *,
    T_build_from_source: RigidTransform | None = None,
) -> RotaryRegionAnalysis:
    """Resolve the selected rotary frame and directed angular regions."""

    transform = _checked_transform(T_build_from_source)
    frame = selection.frame
    spans = tuple(
        RotaryRegionSpan(
            item.region_id,
            item.start_angle_rad,
            item.unwrapped_end_angle_rad,
            item.direction,
        )
        for item in selection.angular_regions
    )
    issues: list[str] = []
    if selection.preview_only:
        issues.append("rotary.region_preview_only")
    if _regions_overlap(spans):
        issues.append("rotary.region_overlap")
    return RotaryRegionAnalysis(
        selection=selection,
        axis_origin_mm=_transform_point(transform, frame.axis_origin_mm),
        axis_direction=_transform_vector(transform, frame.axis_direction),
        zero_direction=_transform_vector(transform, frame.zero_direction),
        transverse_direction=_transform_vector(transform, frame.transverse_direction),
        spans=spans,
        preview_only=selection.preview_only,
        issues=tuple(issues),
    )


def build_rotary_plan(
    operation: RotaryOperationDefinition,
    *,
    T_build_from_source: RigidTransform | None = None,
    cancelled: CancelCheck | None = None,
) -> RotaryPlan:
    """Build a complete geometric plan for one of the three Rotary operations."""

    _checkpoint(cancelled)
    analysis = analyse_rotary_region(operation.geometry, T_build_from_source=T_build_from_source)
    if analysis.preview_only:
        raise RotaryPlanningError("rotary.region_preview_only")
    if "rotary.region_overlap" in analysis.issues:
        raise RotaryPlanningError("rotary.region_overlap")
    if operation.parameters.dwell_s > 0.0:
        raise RotaryPlanningError("rotary.dwell_unsupported")
    transform = _checked_transform(T_build_from_source)
    if operation.operation_type == "rotary_spiral":
        paths = _spiral_paths(operation, transform, cancelled)
    elif operation.operation_type == "rotary_thin_wall":
        paths = _thin_wall_paths(operation, transform, cancelled)
    elif operation.operation_type == "rotary_around_part":
        paths = _around_part_paths(operation, transform, cancelled)
    else:
        raise RotaryPlanningError("rotary.operation_unsupported", operation.operation_type)
    if not paths:
        raise RotaryPlanningError("rotary.toolpath_empty")
    points, events, definitions = _connect_paths(operation, paths, transform, cancelled)
    issues = list(analysis.issues)
    if operation.operation_type == "rotary_thin_wall":
        if operation.parameters.wall_thickness_mm < operation.parameters.bead_width_mm:
            issues.append("rotary.thin_wall_width_reduced")
    return RotaryPlan(
        operation.operation_id,
        operation.operation_type,
        tuple(points),
        tuple(events),
        tuple(definitions),
        analysis,
        tuple(issues),
    )


def _spiral_paths(
    operation: RotaryOperationDefinition,
    transform: RigidTransform | None,
    cancelled: CancelCheck | None,
) -> tuple[_DepositionPath, ...]:
    parameters = operation.parameters
    start, end = _directed_span(
        parameters.start_angle_rad, parameters.end_angle_rad, parameters.direction
    )
    sweep = end - start
    axial_start = operation.geometry.profile.axial_start_mm
    axial_end = axial_start + abs(sweep) / math.tau * parameters.pitch_mm
    profile = operation.geometry.profile
    if axial_end > profile.axial_end_mm + 1.0e-8:
        raise RotaryPlanningError("rotary.pitch_exceeds_profile")
    samples = _sample_surface_curve(
        operation.geometry.frame,
        profile,
        start,
        end,
        axial_start,
        axial_end,
        parameters.sampling_angle_rad,
        transform,
        cancelled,
    )
    return (_DepositionPath("layer-0001", "spiral", samples, "buildup"),)


def _thin_wall_paths(
    operation: RotaryOperationDefinition,
    transform: RigidTransform | None,
    cancelled: CancelCheck | None,
) -> tuple[_DepositionPath, ...]:
    parameters = operation.parameters
    profile = operation.geometry.profile
    axial_values = _inclusive_values(
        profile.axial_start_mm, profile.axial_end_mm, parameters.axial_step_mm
    )
    base_start, base_end = _directed_span(
        parameters.start_angle_rad, parameters.end_angle_rad, parameters.direction
    )
    if abs(abs(base_end - base_start) - math.tau) > 1.0e-8:
        raise RotaryPlanningError("rotary.thin_wall_period_invalid")
    paths: list[_DepositionPath] = []
    effective_width = parameters.bead_width_mm
    if parameters.wall_thickness_mm < parameters.bead_width_mm:
        if parameters.thin_wall_width_policy == "error":
            raise RotaryPlanningError("rotary.thin_wall_below_minimum")
        effective_width = parameters.wall_thickness_mm
    required_width = effective_width + (
        parameters.radial_pass_count - 1
    ) * parameters.radial_spacing_mm
    if required_width > parameters.wall_thickness_mm + 1.0e-10:
        raise RotaryPlanningError("rotary.thin_wall_passes_exceed_width")
    phase = base_start
    direction_sign = 1.0 if base_end > base_start else -1.0
    path_index = 0
    for layer_index, axial in enumerate(axial_values):
        for radial_index in range(parameters.radial_pass_count):
            _checkpoint(cancelled)
            sign = direction_sign if path_index % 2 == 0 else -direction_sign
            start = phase
            end = start + sign * math.tau
            radius_offset = 0.5 * effective_width + radial_index * parameters.radial_spacing_mm
            samples = _sample_surface_curve(
                operation.geometry.frame,
                profile,
                start,
                end,
                axial,
                axial,
                parameters.sampling_angle_rad,
                transform,
                cancelled,
                radius_offset_mm=radius_offset,
            )
            paths.append(
                _DepositionPath(
                    f"layer-{layer_index + 1:04d}",
                    f"radial-{radial_index + 1:04d}",
                    samples,
                    "thin_wall",
                    effective_width,
                )
            )
            phase = end
            path_index += 1
    return tuple(paths)


def _around_part_paths(
    operation: RotaryOperationDefinition,
    transform: RigidTransform | None,
    cancelled: CancelCheck | None,
) -> tuple[_DepositionPath, ...]:
    regions = operation.geometry.angular_regions
    if not regions:
        raise RotaryPlanningError("rotary.region_empty")
    parameters = operation.parameters
    profile = operation.geometry.profile
    axial_values = _inclusive_values(
        profile.axial_start_mm, profile.axial_end_mm, parameters.axial_step_mm
    )
    paths: list[_DepositionPath] = []
    previous_end: float | None = None
    for region in regions:
        raw_start, raw_end = _region_span(region)
        for layer_index, axial in enumerate(axial_values):
            _checkpoint(cancelled)
            if layer_index % 2 == 0:
                canonical_start, canonical_end = raw_start, raw_end
            else:
                canonical_start, canonical_end = raw_end, raw_start
            start = (
                canonical_start
                if previous_end is None
                else _nearest_equivalent(canonical_start, previous_end)
            )
            end = start + (canonical_end - canonical_start)
            samples = _sample_surface_curve(
                operation.geometry.frame,
                profile,
                start,
                end,
                axial,
                axial,
                parameters.sampling_angle_rad,
                transform,
                cancelled,
            )
            paths.append(
                _DepositionPath(
                    f"layer-{layer_index + 1:04d}",
                    region.region_id,
                    samples,
                    "buildup",
                )
            )
            previous_end = end
    return tuple(paths)


def _connect_paths(
    operation: RotaryOperationDefinition,
    paths: tuple[_DepositionPath, ...],
    transform: RigidTransform | None,
    cancelled: CancelCheck | None,
) -> tuple[list[RotaryPlanPoint], list[ToolpathEvent], list[RotaryPathDefinition]]:
    points: list[RotaryPlanPoint] = []
    events: list[ToolpathEvent] = []
    definitions: list[RotaryPathDefinition] = []
    parameters = operation.parameters
    for path_index, path in enumerate(paths):
        _checkpoint(cancelled)
        if len(path.samples) < 2:
            raise RotaryPlanningError("rotary.path_degenerate", path.region_id)
        first = path.samples[0]
        if points:
            previous_layer_id = points[-1].layer_id
            previous_region_id = points[-1].region_id
            connection_start = len(points)
            events.append(
                ToolpathEvent(
                    _event_id(events),
                    "retract",
                    operation.operation_id,
                    operation.operation_type,
                    path.layer_id,
                    path.region_id,
                    context={
                        "sequence_index": len(points),
                        "extrusion_length_mm": -parameters.retract_length_mm,
                    },
                )
            )
            _append_safe_connection(points, operation, path, first, transform)
            events.append(
                ToolpathEvent(
                    _event_id(events),
                    "safe_depart",
                    operation.operation_id,
                    operation.operation_type,
                    path.layer_id,
                    path.region_id,
                    context={
                        "sequence_index": connection_start,
                        "from_layer_id": previous_layer_id,
                        "from_region_id": previous_region_id,
                        "clearance_mm": parameters.connection_clearance_mm,
                        "semantic": "safe_connection",
                    },
                )
            )
            if previous_layer_id != path.layer_id:
                events.append(
                    ToolpathEvent(
                        _event_id(events),
                        "operation_change",
                        operation.operation_id,
                        operation.operation_type,
                        path.layer_id,
                        path.region_id,
                        context={
                            "sequence_index": len(points) - 1,
                            "from_layer_id": previous_layer_id,
                            "to_layer_id": path.layer_id,
                            "semantic": "layer_change",
                        },
                    )
                )
            events.append(
                ToolpathEvent(
                    _event_id(events),
                    "safe_approach",
                    operation.operation_id,
                    operation.operation_type,
                    path.layer_id,
                    path.region_id,
                    context={
                        "sequence_index": len(points) - 1,
                        "from_layer_id": previous_layer_id,
                        "from_region_id": previous_region_id,
                        "clearance_mm": parameters.connection_clearance_mm,
                        "semantic": "safe_connection",
                    },
                )
            )
        else:
            _append_initial_safe_approach(
                points, operation, path, first, transform
            )
            events.append(
                ToolpathEvent(
                    _event_id(events),
                    "safe_approach",
                    operation.operation_id,
                    operation.operation_type,
                    path.layer_id,
                    path.region_id,
                    context={
                        "sequence_index": len(points) - 1,
                        "clearance_mm": parameters.connection_clearance_mm,
                        "semantic": "initial_clearance_entry",
                    },
                )
            )
        events.append(
            ToolpathEvent(
                _event_id(events),
                "index_start",
                operation.operation_id,
                operation.operation_type,
                path.layer_id,
                path.region_id,
                context={
                    "sequence_index": len(points),
                    "unwrapped_angle_rad": first.angle_rad,
                    "axial_mm": first.axial_mm,
                    "radius_mm": first.radius_mm,
                    "semantic": "seam",
                    "reversed_from_declared": _path_is_reversed(operation, path),
                },
            )
        )
        events.append(
            ToolpathEvent(
                _event_id(events),
                "prime",
                operation.operation_id,
                operation.operation_type,
                path.layer_id,
                path.region_id,
                context={
                    "sequence_index": len(points),
                    "extrusion_length_mm": parameters.retract_length_mm,
                },
            )
        )
        # The path owns its non-depositing start point as well as all segment
        # endpoints.  This preserves the complete first deposition segment.
        start_index = len(points) - 1
        previous = first
        for sample in path.samples[1:]:
            segment_length = math.dist(previous.position, sample.position)
            if segment_length <= _EPSILON:
                raise RotaryPlanningError("rotary.path_zero_segment", path.region_id)
            _append_plan_point(
                points,
                operation,
                path,
                sample,
                "deposition",
                path.extrusion_role,
                parameters.feedrate_mm_min,
                segment_length
                * (path.bead_width_mm or parameters.bead_width_mm)
                * parameters.layer_height_mm,
            )
            previous = sample
        definitions.append(
            RotaryPathDefinition(
                f"path-{path_index + 1:04d}",
                path.layer_id,
                path.region_id,
                start_index,
                len(points) - 1,
                path.samples[0].angle_rad,
                path.samples[-1].angle_rad,
                "ccw" if path.samples[-1].angle_rad > path.samples[0].angle_rad else "cw",
                _path_is_reversed(operation, path),
            )
        )
        events.append(
            ToolpathEvent(
                _event_id(events),
                "index_end",
                operation.operation_id,
                operation.operation_type,
                path.layer_id,
                path.region_id,
                context={
                    "sequence_index": len(points),
                    "unwrapped_angle_rad": path.samples[-1].angle_rad,
                    "semantic": "deposition_path_end",
                    "reversed_from_declared": _path_is_reversed(operation, path),
                },
            )
        )
    events.append(
        ToolpathEvent(
            _event_id(events),
            "retract",
            operation.operation_id,
            operation.operation_type,
            points[-1].layer_id,
            points[-1].region_id,
            context={
                "sequence_index": len(points),
                "extrusion_length_mm": -parameters.retract_length_mm,
            },
        )
    )
    final_connection_start = len(points)
    events.append(
        ToolpathEvent(
            _event_id(events),
            "safe_depart",
            operation.operation_id,
            operation.operation_type,
            points[-1].layer_id,
            points[-1].region_id,
            context={
                "sequence_index": final_connection_start,
                "clearance_mm": parameters.connection_clearance_mm,
                "semantic": "final_clearance_exit",
            },
        )
    )
    _append_final_safe_depart(points, operation, paths[-1], transform)
    events.append(
        ToolpathEvent(
            _event_id(events),
            "finish",
            operation.operation_id,
            operation.operation_type,
            points[-1].layer_id,
            points[-1].region_id,
            context={
                "sequence_index": len(points),
                "semantic": "safe_program_end",
            },
        )
    )
    return points, events, definitions


def _append_initial_safe_approach(
    points: list[RotaryPlanPoint],
    operation: RotaryOperationDefinition,
    path: _DepositionPath,
    target: _SurfaceSample,
    transform: RigidTransform | None,
) -> None:
    clearance = _surface_sample(
        operation.geometry.frame,
        operation.geometry.profile,
        target.angle_rad,
        target.axial_mm,
        target.radius_mm + operation.parameters.connection_clearance_mm,
        0.0,
        transform,
    )
    inward = _unit(_subtract(target.position, clearance.position), "rotary.connection_degenerate")
    clearance = _SurfaceSample(
        clearance.position,
        inward,
        clearance.normal,
        clearance.angle_rad,
        clearance.axial_mm,
        clearance.radius_mm,
    )
    _append_plan_point(
        points,
        operation,
        path,
        clearance,
        "travel",
        "none",
        operation.parameters.travel_feedrate_mm_min,
        0.0,
    )
    _append_connection_point(points, operation, path, target, "approach")


def _append_final_safe_depart(
    points: list[RotaryPlanPoint],
    operation: RotaryOperationDefinition,
    path: _DepositionPath,
    transform: RigidTransform | None,
) -> None:
    previous = points[-1]
    clearance = _surface_sample(
        operation.geometry.frame,
        operation.geometry.profile,
        previous.unwrapped_angle_rad,
        previous.axial_mm,
        previous.radius_mm + operation.parameters.connection_clearance_mm,
        0.0,
        transform,
    )
    _append_connection_point(points, operation, path, clearance, "depart")


def _append_safe_connection(
    points: list[RotaryPlanPoint],
    operation: RotaryOperationDefinition,
    path: _DepositionPath,
    target: _SurfaceSample,
    transform: RigidTransform | None,
) -> None:
    previous = points[-1]
    clearance_radius = max(previous.radius_mm, target.radius_mm) + (
        operation.parameters.connection_clearance_mm
    )
    frame = operation.geometry.frame
    profile = operation.geometry.profile
    depart = _surface_sample(
        frame,
        profile,
        previous.unwrapped_angle_rad,
        previous.axial_mm,
        clearance_radius,
        0.0,
        transform,
    )
    _append_connection_point(points, operation, path, depart, "depart")
    angle_delta = target.angle_rad - previous.unwrapped_angle_rad
    axial_delta = target.axial_mm - previous.axial_mm
    transit_count = max(
        1,
        int(math.ceil(abs(angle_delta) / operation.parameters.sampling_angle_rad)),
    )
    for index in range(1, transit_count + 1):
        fraction = index / transit_count
        transit = _surface_sample(
            frame,
            profile,
            previous.unwrapped_angle_rad + fraction * angle_delta,
            previous.axial_mm + fraction * axial_delta,
            clearance_radius,
            0.0,
            transform,
        )
        if math.dist(points[-1].position, transit.position) > _EPSILON:
            _append_connection_point(points, operation, path, transit, "travel")
    _append_connection_point(points, operation, path, target, "approach")


def _append_connection_point(
    points: list[RotaryPlanPoint],
    operation: RotaryOperationDefinition,
    path: _DepositionPath,
    sample: _SurfaceSample,
    point_type: str,
) -> None:
    previous_position = points[-1].position
    movement = _subtract(sample.position, previous_position)
    # The surface approach is also the owned start of the following
    # deposition path, so retain its analytic path tangent.  Depart/travel
    # points describe the actual clearance motion instead.
    tangent = (
        sample.tangent
        if point_type == "approach"
        else _unit(movement, "rotary.connection_degenerate")
    )
    sample = _SurfaceSample(
        sample.position,
        tangent,
        sample.normal,
        sample.angle_rad,
        sample.axial_mm,
        sample.radius_mm,
    )
    _append_plan_point(
        points,
        operation,
        path,
        sample,
        point_type,
        "none",
        operation.parameters.travel_feedrate_mm_min,
        0.0,
    )


def _append_plan_point(
    points: list[RotaryPlanPoint],
    operation: RotaryOperationDefinition,
    path: _DepositionPath,
    sample: _SurfaceSample,
    point_type: str,
    extrusion_role: str,
    feedrate_mm_min: float,
    volume_mm3: float,
) -> None:
    parameters = operation.parameters
    points.append(
        RotaryPlanPoint(
            point_id=f"point-{len(points) + 1:07d}",
            position=sample.position,
            tangent=sample.tangent,
            surface_normal=sample.normal,
            nozzle_axis=_scale(sample.normal, -1.0),
            unwrapped_angle_rad=sample.angle_rad,
            axial_mm=sample.axial_mm,
            radius_mm=sample.radius_mm,
            stage_id=operation.operation_type,
            layer_id=path.layer_id,
            region_id=path.region_id,
            point_type=point_type,
            extrusion_role=extrusion_role,
            feedrate_mm_min=feedrate_mm_min,
            bead_width_mm=(
                (path.bead_width_mm or parameters.bead_width_mm)
                if point_type == "deposition"
                else None
            ),
            layer_height_mm=(parameters.layer_height_mm if point_type == "deposition" else None),
            material_volume_mm3=volume_mm3,
        )
    )


def _sample_surface_curve(
    frame: RotaryFrame,
    profile: RotaryProfile,
    start_angle: float,
    end_angle: float,
    axial_start: float,
    axial_end: float,
    sampling_angle: float,
    transform: RigidTransform | None,
    cancelled: CancelCheck | None,
    *,
    radius_offset_mm: float = 0.0,
) -> tuple[_SurfaceSample, ...]:
    count = max(1, int(math.ceil(abs(end_angle - start_angle) / sampling_angle)))
    samples: list[_SurfaceSample] = []
    for index in range(count + 1):
        _checkpoint(cancelled)
        fraction = index / count
        angle = start_angle + fraction * (end_angle - start_angle)
        axial = axial_start + fraction * (axial_end - axial_start)
        radius = profile.radius_at(axial) + radius_offset_mm
        if radius <= _EPSILON:
            raise RotaryPlanningError("rotary.cone_apex_degenerate")
        ds_dtheta = (
            0.0
            if abs(end_angle - start_angle) <= _EPSILON
            else (axial_end - axial_start) / (end_angle - start_angle)
        )
        sample = _surface_sample(
            frame,
            profile,
            angle,
            axial,
            radius,
            ds_dtheta,
            transform,
        )
        if end_angle < start_angle:
            sample = _SurfaceSample(
                sample.position,
                _scale(sample.tangent, -1.0),
                sample.normal,
                sample.angle_rad,
                sample.axial_mm,
                sample.radius_mm,
            )
        samples.append(sample)
    return tuple(samples)


def _surface_sample(
    frame: RotaryFrame,
    profile: RotaryProfile,
    angle: float,
    axial: float,
    radius: float,
    ds_dtheta: float,
    transform: RigidTransform | None,
) -> _SurfaceSample:
    radial = _add(
        _scale(frame.zero_direction, math.cos(angle)),
        _scale(frame.transverse_direction, math.sin(angle)),
    )
    azimuthal = _add(
        _scale(frame.zero_direction, -math.sin(angle)),
        _scale(frame.transverse_direction, math.cos(angle)),
    )
    slope = (profile.radius_end_mm - profile.radius_start_mm) / (
        profile.axial_end_mm - profile.axial_start_mm
    )
    dr_dtheta = slope * ds_dtheta
    source_position = _add(
        frame.axis_origin_mm,
        _add(_scale(frame.axis_direction, axial), _scale(radial, radius)),
    )
    source_normal = _unit(
        _subtract(radial, _scale(frame.axis_direction, slope)),
        "rotary.surface_normal_invalid",
    )
    source_tangent = _unit(
        _add(
            _scale(azimuthal, radius),
            _add(
                _scale(radial, dr_dtheta),
                _scale(frame.axis_direction, ds_dtheta),
            ),
        ),
        "rotary.tangent_invalid",
    )
    return _SurfaceSample(
        _transform_point(transform, source_position),
        _transform_vector(transform, source_tangent),
        _transform_vector(transform, source_normal),
        angle,
        axial,
        radius,
    )


def _inclusive_values(start: float, end: float, step: float) -> tuple[float, ...]:
    span = end - start
    if span < _EPSILON:
        raise RotaryPlanningError("rotary.profile_axial_range_invalid")
    count = int(math.floor(span / step + 1.0e-10))
    values = [start + index * step for index in range(count + 1)]
    if end - values[-1] > 1.0e-8:
        values.append(end)
    else:
        values[-1] = end
    return tuple(values)


def _directed_span(start: float, end: float, direction: str) -> tuple[float, float]:
    if direction == "ccw":
        while end <= start:
            end += math.tau
    elif direction == "cw":
        while end >= start:
            end -= math.tau
    else:
        raise RotaryPlanningError("rotary.direction_invalid")
    if abs(end - start) <= _EPSILON:
        raise RotaryPlanningError("rotary.period_ambiguous")
    return start, end


def _region_span(region: RotaryAngularRegion) -> tuple[float, float]:
    return region.start_angle_rad, region.unwrapped_end_angle_rad


def _path_is_reversed(operation: RotaryOperationDefinition, path: _DepositionPath) -> bool:
    declared_direction = operation.parameters.direction
    if operation.operation_type == "rotary_around_part":
        declared_direction = next(
            region.direction
            for region in operation.geometry.angular_regions
            if region.region_id == path.region_id
        )
    declared_sign = 1.0 if declared_direction == "ccw" else -1.0
    actual_sweep = path.samples[-1].angle_rad - path.samples[0].angle_rad
    return actual_sweep * declared_sign < 0.0


def _nearest_equivalent(angle: float, reference: float) -> float:
    turns = math.floor((reference - angle) / math.tau + 0.5)
    return angle + turns * math.tau


def _regions_overlap(spans: tuple[RotaryRegionSpan, ...]) -> bool:
    normalised: list[tuple[float, float]] = []
    for span in spans:
        sweep = span.sweep_rad
        if abs(sweep) >= math.tau - 1.0e-10:
            return len(spans) > 1
        start = span.start_angle_rad % math.tau
        extent = abs(sweep)
        low = start if sweep > 0.0 else (start - extent) % math.tau
        high = low + extent
        pieces = ((low, high),) if high <= math.tau else ((low, math.tau), (0.0, high - math.tau))
        for piece in pieces:
            if any(
                min(piece[1], other[1]) - max(piece[0], other[0]) > 1.0e-10 for other in normalised
            ):
                return True
            normalised.append(piece)
    return False


def _checked_transform(transform: RigidTransform | None) -> RigidTransform | None:
    if transform is None:
        return None
    if not isinstance(transform, RigidTransform):
        raise TypeError("T_build_from_source must be a RigidTransform")
    if transform.source_frame != "source":
        raise RotaryPlanningError("rotary.source_frame_invalid")
    if transform.target_frame != "build":
        raise RotaryPlanningError("rotary.build_frame_invalid")
    return transform


def _transform_point(transform: RigidTransform | None, value: Vector3) -> Vector3:
    return value if transform is None else transform.transform_point(value)


def _transform_vector(transform: RigidTransform | None, value: Vector3) -> Vector3:
    return _unit(
        value if transform is None else transform.transform_vector(value),
        "rotary.transform_vector_invalid",
    )


def _checkpoint(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        raise RotaryPlanningError("rotary.generation_cancelled")


def _event_id(events: list[ToolpathEvent]) -> str:
    return f"event-{len(events) + 1:07d}"


def _add(left: Vector3, right: Vector3) -> Vector3:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _scale(value: Vector3, factor: float) -> Vector3:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _unit(value: Vector3, code: str) -> Vector3:
    length = math.sqrt(sum(item * item for item in value))
    if length <= _EPSILON:
        raise RotaryPlanningError(code)
    return (value[0] / length, value[1] / length, value[2] / length)


__all__ = [
    "RotaryPathDefinition",
    "RotaryPlan",
    "RotaryPlanningError",
    "RotaryPlanPoint",
    "RotaryRegionAnalysis",
    "RotaryRegionSpan",
    "analyse_rotary_region",
    "build_rotary_plan",
]
