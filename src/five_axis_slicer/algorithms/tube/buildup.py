"""Restricted multi-pass Tube buildup and planar-base operation sequencing.

The module keeps geometric path generation separate from persisted operation
definitions.  Tube passes fill the selected CAD wall from the inner bead
centre to the outer bead centre.  A printable planar base is emitted as its
own :class:`GeneratedToolpath`; callers then order the independent operations
with explicit safe transition events.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

from ...manufacturing.setup import TubeProcessParameters
from ...manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from ...models import CadModel, Vector3
from .geometry import TubeFeature
from .indexed import TubeSliceLayer, plan_indexed_slices
from .section import section_tube_layer


class TubeBuildupError(ValueError):
    """A stable, localisable failure in restricted Tube buildup generation."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = str(code)
        self.detail = str(detail)
        super().__init__(f"{self.code}: {self.detail}")


@dataclass(frozen=True, slots=True)
class TubeBuildupParameters:
    """Explicit-unit process parameters for thick-wall Tube buildup."""

    bead_width_mm: float = 0.8
    layer_height_mm: float = 0.3
    maximum_pass_spacing_mm: float = 0.6
    max_wedge_angle_deg: float = 15.0
    max_bead_height_error_mm: float = 0.05
    safe_clearance_mm: float = 5.0
    retract_length_mm: float = 1.0
    deposition_feedrate_mm_min: float = 1200.0
    travel_feedrate_mm_min: float = 3000.0
    contour_chord_error_mm: float = 0.02

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and greater than zero")
            object.__setattr__(self, name, value)
        if self.maximum_pass_spacing_mm > self.bead_width_mm:
            raise ValueError("maximum_pass_spacing_mm must not exceed bead_width_mm")
        if self.max_wedge_angle_deg > 90.0:
            raise ValueError("max_wedge_angle_deg must not exceed 90 degrees")
        if self.layer_height_mm > self.bead_width_mm * 2.0:
            raise ValueError("layer_height_mm exceeds the supported bead aspect ratio")

    def indexed_parameters(self) -> TubeProcessParameters:
        """Adapt shared wedge planning without weakening its validation."""

        return TubeProcessParameters(
            bead_width_mm=self.bead_width_mm,
            layer_height_mm=self.layer_height_mm,
            max_wedge_angle_deg=self.max_wedge_angle_deg,
            max_bead_height_error_mm=self.max_bead_height_error_mm,
            safe_clearance_mm=self.safe_clearance_mm,
            retract_length_mm=self.retract_length_mm,
            deposition_feedrate_mm_min=self.deposition_feedrate_mm_min,
            travel_feedrate_mm_min=self.travel_feedrate_mm_min,
            contour_chord_error_mm=self.contour_chord_error_mm,
        )


@dataclass(frozen=True, slots=True)
class TubeBuildupPass:
    pass_id: str
    pass_index: int
    radial_offset_mm: float

    def __post_init__(self) -> None:
        if not str(self.pass_id).strip():
            raise ValueError("pass_id must not be empty")
        if int(self.pass_index) < 0:
            raise ValueError("pass_index must be non-negative")
        if not math.isfinite(float(self.radial_offset_mm)):
            raise ValueError("radial_offset_mm must be finite")


@dataclass(frozen=True, slots=True)
class TubeBuildupLayer:
    layer_id: str
    region_id: str
    centerline_distance_mm: float
    plane_origin: Vector3
    plane_normal: Vector3
    deposited_height_mm: float
    passes: tuple[TubeBuildupPass, ...]

    def __post_init__(self) -> None:
        passes = tuple(self.passes)
        if len(passes) < 2:
            raise ValueError("Tube buildup layers require at least two radial passes")
        if self.deposited_height_mm <= 0.0 or not math.isfinite(self.deposited_height_mm):
            raise ValueError("deposited_height_mm must be finite and positive")
        object.__setattr__(self, "passes", passes)


@dataclass(frozen=True, slots=True)
class TubeBuildupPlan:
    layers: tuple[TubeBuildupLayer, ...]
    wall_thickness_mm: float
    bead_width_mm: float
    maximum_pass_spacing_mm: float

    def __post_init__(self) -> None:
        layers = tuple(self.layers)
        if not layers:
            raise ValueError("Tube buildup plan requires at least one layer")
        expected = layers[0].passes
        if any(layer.passes != expected for layer in layers[1:]):
            raise ValueError("Tube buildup pass layout must be stable across layers")
        object.__setattr__(self, "layers", layers)

    @property
    def pass_offsets_mm(self) -> tuple[float, ...]:
        return tuple(item.radial_offset_mm for item in self.layers[0].passes)

    @property
    def pass_count(self) -> int:
        return len(self.layers[0].passes)


@dataclass(frozen=True, slots=True)
class PlanarBaseDefinition:
    """Analytic circular base printed independently of the Tube body."""

    base_id: str
    center: Vector3
    normal: Vector3
    radius_mm: float
    height_mm: float

    def __post_init__(self) -> None:
        if not str(self.base_id).strip():
            raise ValueError("base_id must not be empty")
        center = _vector3(self.center, "center")
        normal = _unit(_vector3(self.normal, "normal"))
        radius = float(self.radius_mm)
        height = float(self.height_mm)
        if not math.isfinite(radius) or radius <= 0.0:
            raise ValueError("radius_mm must be finite and positive")
        if not math.isfinite(height) or height <= 0.0:
            raise ValueError("height_mm must be finite and positive")
        object.__setattr__(self, "base_id", str(self.base_id).strip())
        object.__setattr__(self, "center", center)
        object.__setattr__(self, "normal", normal)
        object.__setattr__(self, "radius_mm", radius)
        object.__setattr__(self, "height_mm", height)


@dataclass(frozen=True, slots=True)
class TubeBuildupSequence:
    """Ordered independent operations plus events at operation boundaries."""

    sequence_id: str
    operations: tuple[GeneratedToolpath, ...]
    transition_events: tuple[ToolpathEvent, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.sequence_id).strip():
            raise ValueError("sequence_id must not be empty")
        operations = tuple(self.operations)
        events = tuple(self.transition_events)
        identifiers = tuple(item.operation_id for item in operations)
        if not operations or len(set(identifiers)) != len(identifiers):
            raise ValueError("operations must be non-empty and have unique operation_id values")
        object.__setattr__(self, "sequence_id", str(self.sequence_id).strip())
        object.__setattr__(self, "operations", operations)
        object.__setattr__(self, "transition_events", events)

    @property
    def ordered_operation_ids(self) -> tuple[str, ...]:
        return tuple(item.operation_id for item in self.operations)

    @property
    def material_volume_mm3(self) -> float:
        return sum(point.material_volume_mm3 for path in self.operations for point in path.points)


def plan_tube_buildup(
    feature: TubeFeature,
    parameters: TubeBuildupParameters,
) -> TubeBuildupPlan:
    """Plan axial layers and radial passes for a constant-wall Tube feature."""

    if not isinstance(feature, TubeFeature):
        raise TypeError("feature must be TubeFeature")
    if not isinstance(parameters, TubeBuildupParameters):
        raise TypeError("parameters must be TubeBuildupParameters")
    offsets = _pass_offsets(feature.wall_thickness_mm, parameters)
    indexed = plan_indexed_slices(feature, parameters.indexed_parameters())
    passes = tuple(
        TubeBuildupPass(f"pass-{index + 1:04d}", index, offset)
        for index, offset in enumerate(offsets)
    )
    layers = tuple(
        _buildup_layer(layer, passes, index, feature.centerline_length_mm, parameters)
        for index, layer in enumerate(indexed.layers)
    )
    return TubeBuildupPlan(
        layers,
        feature.wall_thickness_mm,
        parameters.bead_width_mm,
        parameters.maximum_pass_spacing_mm,
    )


def generate_tube_buildup_toolpath(
    operation_id: str,
    feature: TubeFeature,
    plan: TubeBuildupPlan,
    parameters: TubeBuildupParameters,
    *,
    model: CadModel | None = None,
) -> GeneratedToolpath:
    """Generate closed contours for every planned axial layer and radial pass."""

    _validate_generation_inputs(operation_id, feature, plan, parameters)
    builder = _BuildupPathBuilder(operation_id, parameters)
    for layer_index, layer in enumerate(plan.layers):
        midwall = _midwall_loop(feature, layer, parameters, model)
        ordered_passes = layer.passes if layer_index % 2 == 0 else tuple(reversed(layer.passes))
        for radial_pass in ordered_passes:
            loop = _offset_loop(midwall, radial_pass.radial_offset_mm)
            if (layer_index + radial_pass.pass_index) % 2:
                loop = tuple(reversed(loop))
            builder.add_path(layer, radial_pass.pass_id, loop, layer.deposited_height_mm)
    return builder.toolpath(f"{operation_id}-tube-buildup-v1")


def generate_planar_base_toolpath(
    operation_id: str,
    base: PlanarBaseDefinition,
    parameters: TubeBuildupParameters,
) -> GeneratedToolpath:
    """Generate alternating clipped hatch lines for an independent circular base."""

    if not str(operation_id).strip():
        raise ValueError("operation_id must not be empty")
    if base.radius_mm < parameters.bead_width_mm:
        raise TubeBuildupError(
            "tube.buildup_base_too_small",
            "base radius must accommodate at least one full bead-width hatch",
        )
    _require_safe_clearance(parameters)
    builder = _BuildupPathBuilder(str(operation_id).strip(), parameters)
    layer_count = math.ceil(base.height_mm / parameters.layer_height_mm)
    for layer_index in range(layer_count):
        layer = _base_layer(base, parameters, layer_index)
        lines = _base_hatch_lines(base, parameters, layer_index, layer.plane_origin)
        for line_index, line in enumerate(lines):
            path = line if (layer_index + line_index) % 2 == 0 else tuple(reversed(line))
            builder.add_path(layer, f"hatch-{line_index + 1:04d}", path, layer.deposited_height_mm)
    return builder.toolpath(f"{operation_id}-planar-base-v1")


def sequence_buildup_operations(
    sequence_id: str,
    tube_toolpath: GeneratedToolpath,
    *,
    base_toolpath: GeneratedToolpath | None = None,
    base_order: Literal["before_tube", "after_tube"] = "before_tube",
    safe_clearance_mm: float,
) -> TubeBuildupSequence:
    """Order base/Tube operations and create deterministic boundary events."""

    if base_order not in {"before_tube", "after_tube"}:
        raise TubeBuildupError("tube.buildup_base_order_invalid", str(base_order))
    clearance = float(safe_clearance_mm)
    if not math.isfinite(clearance) or clearance <= 0.0:
        raise ValueError("safe_clearance_mm must be finite and positive")
    operations = _ordered_operations(tube_toolpath, base_toolpath, base_order)
    _validate_operation_sequence(operations, clearance)
    events: list[ToolpathEvent] = []
    for boundary_index, (source, target) in enumerate(zip(operations, operations[1:])):
        events.extend(_transition_events(sequence_id, boundary_index, source, target, clearance))
    return TubeBuildupSequence(sequence_id, operations, tuple(events))


orchestrate_buildup_operations = sequence_buildup_operations


class _BuildupPathBuilder:
    def __init__(self, operation_id: str, parameters: TubeBuildupParameters) -> None:
        self.operation_id = str(operation_id).strip()
        self.parameters = parameters
        self.points: list[ToolpathPoint] = []
        self.events: list[ToolpathEvent] = []

    def add_path(
        self,
        layer: TubeBuildupLayer,
        path_id: str,
        path: tuple[tuple[Vector3, Vector3, Vector3], ...],
        deposited_height_mm: float,
    ) -> None:
        if len(path) < 2:
            raise TubeBuildupError("tube.buildup_empty_pass", path_id)
        position, tangent, normal = path[0]
        if self.points:
            self._connect(layer, path_id, position, tangent, normal)
        else:
            self._point(layer, path_id, position, tangent, normal, "approach")
            self._event("prime", layer, path_id)
        previous = position
        for position, tangent, normal in path[1:]:
            volume = math.dist(previous, position) * self.parameters.bead_width_mm
            volume *= deposited_height_mm
            self._point(layer, path_id, position, tangent, normal, "deposition", volume)
            previous = position

    def _connect(
        self,
        layer: TubeBuildupLayer,
        path_id: str,
        target: Vector3,
        tangent: Vector3,
        normal: Vector3,
    ) -> None:
        previous = self.points[-1]
        self._event("retract", layer, path_id)
        depart = _subtract(
            previous.position, _scale(previous.nozzle_axis, self.parameters.safe_clearance_mm)
        )
        self._point(
            layer,
            path_id,
            depart,
            previous.tangent,
            previous.surface_normal or normal,
            "depart",
            nozzle_axis=previous.nozzle_axis,
        )
        safe_target = _add(target, _scale(layer.plane_normal, self.parameters.safe_clearance_mm))
        self._point(layer, path_id, safe_target, tangent, normal, "travel")
        self._point(layer, path_id, target, tangent, normal, "approach")
        self._event("prime", layer, path_id)

    def _point(
        self,
        layer: TubeBuildupLayer,
        path_id: str,
        position: Vector3,
        tangent: Vector3,
        normal: Vector3,
        point_type: str,
        volume: float = 0.0,
        *,
        nozzle_axis: Vector3 | None = None,
    ) -> None:
        deposition = point_type == "deposition"
        self.points.append(
            ToolpathPoint(
                point_id=f"point-{len(self.points) + 1:07d}",
                position=position,
                tangent=tangent,
                nozzle_axis=nozzle_axis or _scale(layer.plane_normal, -1.0),
                surface_normal=normal,
                operation_id=self.operation_id,
                stage_id=layer.region_id,
                layer_id=layer.layer_id,
                region_id=path_id,
                point_type=point_type,
                extrusion_role="buildup" if deposition else "none",
                feedrate_mm_min=(
                    self.parameters.deposition_feedrate_mm_min
                    if deposition
                    else self.parameters.travel_feedrate_mm_min
                ),
                bead_width_mm=self.parameters.bead_width_mm if deposition else None,
                layer_height_mm=layer.deposited_height_mm if deposition else None,
                material_volume_mm3=volume,
            )
        )

    def _event(self, event_type: str, layer: TubeBuildupLayer, path_id: str) -> None:
        context: dict[str, float | int] = {"sequence_index": len(self.points)}
        if event_type in {"retract", "prime"}:
            sign = -1.0 if event_type == "retract" else 1.0
            context["extrusion_length_mm"] = sign * self.parameters.retract_length_mm
        self.events.append(
            ToolpathEvent(
                event_id=f"event-{len(self.events) + 1:07d}",
                event_type=event_type,
                operation_id=self.operation_id,
                stage_id=layer.region_id,
                layer_id=layer.layer_id,
                region_id=path_id,
                context=context,
            )
        )

    def toolpath(self, toolpath_id: str) -> GeneratedToolpath:
        return GeneratedToolpath(
            toolpath_id,
            self.operation_id,
            points=tuple(self.points),
            events=tuple(self.events),
        )


def _pass_offsets(
    wall_thickness_mm: float,
    parameters: TubeBuildupParameters,
) -> tuple[float, ...]:
    usable = wall_thickness_mm - parameters.bead_width_mm
    if usable <= 1.0e-9:
        raise TubeBuildupError(
            "tube.buildup_wall_too_thin",
            "wall must fit at least two bead-centre passes",
        )
    intervals = max(1, math.ceil(usable / parameters.maximum_pass_spacing_mm))
    if intervals < 1 or usable / intervals > parameters.bead_width_mm + 1.0e-9:
        raise TubeBuildupError("tube.buildup_pass_gap", "computed radial passes leave a gap")
    return tuple(-0.5 * usable + usable * index / intervals for index in range(intervals + 1))


def _buildup_layer(
    layer: TubeSliceLayer,
    passes: tuple[TubeBuildupPass, ...],
    index: int,
    total_length_mm: float,
    parameters: TubeBuildupParameters,
) -> TubeBuildupLayer:
    remaining = total_length_mm - index * parameters.layer_height_mm
    height = min(parameters.layer_height_mm, remaining)
    return TubeBuildupLayer(
        layer.layer_id,
        layer.region_id,
        layer.centerline_distance_mm,
        layer.plane_origin,
        layer.plane_normal,
        height,
        passes,
    )


def _validate_generation_inputs(
    operation_id: str,
    feature: TubeFeature,
    plan: TubeBuildupPlan,
    parameters: TubeBuildupParameters,
) -> None:
    if not str(operation_id).strip():
        raise ValueError("operation_id must not be empty")
    if not math.isclose(plan.wall_thickness_mm, feature.wall_thickness_mm, abs_tol=1.0e-8):
        raise TubeBuildupError("tube.buildup_plan_feature_mismatch", "wall thickness changed")
    if not math.isclose(plan.bead_width_mm, parameters.bead_width_mm, abs_tol=1.0e-8):
        raise TubeBuildupError("tube.buildup_plan_parameter_mismatch", "bead width changed")
    _require_safe_clearance(parameters)


def _require_safe_clearance(parameters: TubeBuildupParameters) -> None:
    required = max(parameters.bead_width_mm, parameters.layer_height_mm)
    if parameters.safe_clearance_mm < required:
        raise TubeBuildupError(
            "tube.buildup_clearance_insufficient",
            "clearance must cover at least one deposited bead envelope",
        )


def _midwall_loop(
    feature: TubeFeature,
    layer: TubeBuildupLayer,
    parameters: TubeBuildupParameters,
    model: CadModel | None,
) -> tuple[tuple[Vector3, Vector3, Vector3], ...]:
    if model is None:
        center, _tangent = feature.point_tangent_at(layer.centerline_distance_mm)
        return _circular_loop(
            center,
            layer.plane_normal,
            feature.path_radius_mm,
            parameters.contour_chord_error_mm,
        )
    section = section_tube_layer(
        model,
        feature.tube_body_id,
        layer.plane_origin,
        layer.plane_normal,
        feature.wall_thickness_mm,
        chord_error_mm=parameters.contour_chord_error_mm,
    )
    return _section_loop(section.midwall, section.normals)


def _section_loop(
    positions: tuple[Vector3, ...],
    normals: tuple[Vector3, ...],
) -> tuple[tuple[Vector3, Vector3, Vector3], ...]:
    result: list[tuple[Vector3, Vector3, Vector3]] = []
    for index, (position, normal) in enumerate(zip(positions, normals)):
        previous = positions[index - 1]
        following = positions[(index + 1) % len(positions)]
        result.append((position, _unit(_subtract(following, previous)), normal))
    return tuple(result)


def _offset_loop(
    loop: tuple[tuple[Vector3, Vector3, Vector3], ...],
    offset_mm: float,
) -> tuple[tuple[Vector3, Vector3, Vector3], ...]:
    return tuple(
        (_add(position, _scale(normal, offset_mm)), tangent, normal)
        for position, tangent, normal in loop
    )


def _circular_loop(
    center: Vector3,
    normal: Vector3,
    radius_mm: float,
    chord_error_mm: float,
) -> tuple[tuple[Vector3, Vector3, Vector3], ...]:
    plane_normal = _unit(normal)
    u, v = _plane_basis(plane_normal)
    ratio = min(1.0, chord_error_mm / radius_mm)
    maximum_angle = 2.0 * math.acos(max(-1.0, 1.0 - ratio))
    count = max(12, math.ceil(2.0 * math.pi / maximum_angle))
    result: list[tuple[Vector3, Vector3, Vector3]] = []
    for index in range(count + 1):
        angle = 2.0 * math.pi * index / count
        radial = _add(_scale(u, math.cos(angle)), _scale(v, math.sin(angle)))
        tangent = _add(_scale(u, -math.sin(angle)), _scale(v, math.cos(angle)))
        result.append((_add(center, _scale(radial, radius_mm)), tangent, radial))
    return tuple(result)


def _base_layer(
    base: PlanarBaseDefinition,
    parameters: TubeBuildupParameters,
    layer_index: int,
) -> TubeBuildupLayer:
    lower = layer_index * parameters.layer_height_mm
    upper = min(base.height_mm, lower + parameters.layer_height_mm)
    origin = _add(base.center, _scale(base.normal, (lower + upper) * 0.5))
    dummy_passes = (
        TubeBuildupPass("base-hatch-layout-1", 0, -0.5),
        TubeBuildupPass("base-hatch-layout-2", 1, 0.5),
    )
    return TubeBuildupLayer(
        f"base-layer-{layer_index + 1:05d}",
        f"base-{base.base_id}",
        (lower + upper) * 0.5,
        origin,
        base.normal,
        upper - lower,
        dummy_passes,
    )


def _base_hatch_lines(
    base: PlanarBaseDefinition,
    parameters: TubeBuildupParameters,
    layer_index: int,
    origin: Vector3,
) -> tuple[tuple[tuple[Vector3, Vector3, Vector3], ...], ...]:
    u, v = _plane_basis(base.normal)
    if layer_index % 2:
        u, v = v, _scale(u, -1.0)
    effective_radius = base.radius_mm - parameters.bead_width_mm * 0.5
    line_count = max(1, math.ceil(2.0 * effective_radius / parameters.maximum_pass_spacing_mm))
    spacing = 2.0 * effective_radius / line_count
    offsets = tuple(-effective_radius + spacing * (index + 0.5) for index in range(line_count))
    return tuple(
        _hatch_line(origin, base.normal, u, v, offset, effective_radius) for offset in offsets
    )


def _hatch_line(
    origin: Vector3,
    normal: Vector3,
    u: Vector3,
    v: Vector3,
    offset: float,
    radius: float,
) -> tuple[tuple[Vector3, Vector3, Vector3], ...]:
    half_length = math.sqrt(max(0.0, radius * radius - offset * offset))
    center = _add(origin, _scale(v, offset))
    start = _subtract(center, _scale(u, half_length))
    end = _add(center, _scale(u, half_length))
    return ((start, u, normal), (end, u, normal))


def _ordered_operations(
    tube: GeneratedToolpath,
    base: GeneratedToolpath | None,
    base_order: str,
) -> tuple[GeneratedToolpath, ...]:
    if base is None:
        return (tube,)
    return (base, tube) if base_order == "before_tube" else (tube, base)


def _validate_operation_sequence(
    operations: tuple[GeneratedToolpath, ...],
    clearance_mm: float,
) -> None:
    if any(not operation.points for operation in operations):
        raise TubeBuildupError("tube.buildup_empty_operation", "all operations need path points")
    identifiers = tuple(operation.operation_id for operation in operations)
    if len(set(identifiers)) != len(identifiers):
        raise TubeBuildupError("tube.buildup_operation_id_conflict", str(identifiers))
    frames = {operation.coordinate_frame for operation in operations}
    if len(frames) != 1:
        raise TubeBuildupError("tube.buildup_coordinate_frame_mismatch", str(sorted(frames)))
    required = max(
        max(point.bead_width_mm or 0.0, point.layer_height_mm or 0.0)
        for operation in operations
        for point in operation.points
    )
    if clearance_mm < required:
        raise TubeBuildupError(
            "tube.buildup_transition_clearance_insufficient",
            f"required at least {required:g} mm",
        )


def _transition_events(
    sequence_id: str,
    boundary_index: int,
    source: GeneratedToolpath,
    target: GeneratedToolpath,
    clearance_mm: float,
) -> tuple[ToolpathEvent, ...]:
    prefix = f"{sequence_id}-transition-{boundary_index + 1:03d}"
    common = {
        "from_operation_id": source.operation_id,
        "to_operation_id": target.operation_id,
        "safe_clearance_mm": clearance_mm,
        "from_position": source.points[-1].position,
        "to_position": target.points[0].position,
    }
    phases = (
        ("retract", source.operation_id, source.points[-1]),
        ("safe_depart", source.operation_id, source.points[-1]),
        ("operation_change", target.operation_id, target.points[0]),
        ("safe_approach", target.operation_id, target.points[0]),
        ("prime", target.operation_id, target.points[0]),
    )
    return tuple(
        ToolpathEvent(
            event_id=f"{prefix}-{index + 1:02d}",
            event_type=event_type,
            operation_id=operation_id,
            stage_id="operation-transition",
            layer_id=point.layer_id,
            region_id=point.region_id,
            context=common | {"phase_index": index},
        )
        for index, (event_type, operation_id, point) in enumerate(phases)
    )


def _vector3(value: Vector3, name: str) -> Vector3:
    result = tuple(float(item) for item in value)
    if len(result) != 3 or not all(math.isfinite(item) for item in result):
        raise ValueError(f"{name} must contain three finite coordinates")
    return result  # type: ignore[return-value]


def _plane_basis(normal: Vector3) -> tuple[Vector3, Vector3]:
    reference = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.8 else (0.0, 1.0, 0.0)
    u = _unit(_cross(normal, reference))
    return u, _unit(_cross(normal, u))


def _unit(value: Vector3) -> Vector3:
    length = math.sqrt(sum(item * item for item in value))
    if length <= 1.0e-12:
        raise ValueError("zero-length vector")
    return _scale(value, 1.0 / length)


def _add(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a + b for a, b in zip(left, right))  # type: ignore[return-value]


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return tuple(a - b for a, b in zip(left, right))  # type: ignore[return-value]


def _scale(value: Vector3, factor: float) -> Vector3:
    return tuple(item * factor for item in value)  # type: ignore[return-value]


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


__all__ = [
    "PlanarBaseDefinition",
    "TubeBuildupError",
    "TubeBuildupLayer",
    "TubeBuildupParameters",
    "TubeBuildupPass",
    "TubeBuildupPlan",
    "TubeBuildupSequence",
    "generate_planar_base_toolpath",
    "generate_tube_buildup_toolpath",
    "orchestrate_buildup_operations",
    "plan_tube_buildup",
    "sequence_buildup_operations",
]
