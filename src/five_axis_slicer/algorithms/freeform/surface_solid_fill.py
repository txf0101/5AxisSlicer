"""Finite-width solid fill for a rectangular trimmed freeform face.

The selected root edge must be one complete parametric boundary of the face.
Paths advance across the face from that supported boundary, then repeat through
the solid thickness along the inward face normal. This is the bounded topology
used by the paper impeller: it is not a general arbitrary-face offsetter.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable
from dataclasses import dataclass
import math

from OCP.BRep import BRep_Tool
from OCP.BRepTools import BRepTools
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.GeomLProp import GeomLProp_SLProps
from OCP.TopAbs import TopAbs_REVERSED
from OCP.gp import gp_Pnt

from ...manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from ...models import CadModel, Vector3
from ...step_topology import sample_edge_points

_EPSILON = 1.0e-9


@dataclass(frozen=True, slots=True)
class SurfaceSolidFillParameters:
    solid_thickness_mm: float
    layer_height_mm: float = 0.2
    bead_width_mm: float = 0.4
    path_spacing_mm: float = 0.4
    sampling_step_mm: float = 0.2
    deposition_feedrate_mm_min: float = 1200.0
    travel_feedrate_mm_min: float = 3000.0
    retract_length_mm: float = 1.0
    metric_across_samples: int = 129
    metric_along_samples: int = 129

    def __post_init__(self) -> None:
        for name in (
            "solid_thickness_mm",
            "layer_height_mm",
            "bead_width_mm",
            "path_spacing_mm",
            "sampling_step_mm",
            "deposition_feedrate_mm_min",
            "travel_feedrate_mm_min",
            "retract_length_mm",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.path_spacing_mm > self.bead_width_mm:
            raise ValueError("path_spacing_mm must not exceed bead_width_mm")
        if self.layer_height_mm > self.solid_thickness_mm:
            raise ValueError("layer_height_mm exceeds solid thickness")
        if self.metric_across_samples < 17 or self.metric_along_samples < 9:
            raise ValueError("surface metric sampling is too sparse")


@dataclass(frozen=True, slots=True)
class SurfaceSolidBodySelection:
    body_id: str
    face_id: str
    opposite_face_id: str
    root_edge_id: str
    substrate_body_id: str | None = None


@dataclass(frozen=True, slots=True)
class SurfaceSolidFillAudit:
    body_count: int
    depth_layer_count: int
    paths_per_body_layer: tuple[int, ...]
    maximum_cross_path_spacing_mm: float
    maximum_segment_length_mm: float
    thickness_min_mm: float
    thickness_max_mm: float
    material_volume_mm3: float
    cad_volume_mm3: float
    relative_volume_error: float
    root_edge_max_gap_mm: float


def generate_surface_solid_fill(
    model: CadModel,
    selections: tuple[SurfaceSolidBodySelection, ...],
    operation_prefix: str,
    parameters: SurfaceSolidFillParameters,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[tuple[GeneratedToolpath, ...], SurfaceSolidFillAudit]:
    """Generate one independently transitionable toolpath per body/depth layer."""

    if not selections or len({item.body_id for item in selections}) != len(selections):
        raise ValueError("unique non-empty body selections required")
    depth_count = math.ceil(parameters.solid_thickness_mm / parameters.layer_height_mm - 1e-10)
    depth_height = parameters.solid_thickness_mm / depth_count
    results = []
    paths_per_layer = []
    maximum_spacing = maximum_segment = 0.0
    thickness_values = []
    material_volume = 0.0
    root_gap = 0.0
    for selection in selections:
        _validate_selection(model, selection)
        surface = BRep_Tool.Surface_s(model.face_shapes[selection.face_id])
        orientation = model.face_shapes[selection.face_id].Orientation()
        frame = _surface_frame(model, selection, surface, parameters)
        thickness = _thickness_samples(model, selection, surface, orientation)
        thickness_values.extend(thickness)
        if min(thickness) < parameters.solid_thickness_mm - 0.02:
            raise ValueError(f"freeform.solid_thickness_exceeds_body: {selection.body_id}")
        if selection.substrate_body_id is not None:
            root_gap = max(root_gap, _root_edge_gap(model, selection))
        for depth_index in range(1, depth_count + 1):
            _checkpoint(cancelled)
            operation_id = f"{operation_prefix}-{selection.body_id}-depth-{depth_index:03d}"
            builder = _SurfacePathBuilder(
                operation_id,
                selection.body_id,
                depth_index,
                depth_count,
                depth_index * depth_height,
                depth_height,
                parameters,
            )
            strip_index = 0
            for target_index, target_distance in enumerate(frame.target_distances_mm):
                contours = _sample_surface_contours(
                    surface,
                    orientation,
                    frame,
                    target_distance,
                    parameters.sampling_step_mm,
                )
                for samples in contours:
                    strip_index += 1
                    if (strip_index + depth_index) % 2:
                        samples = tuple(reversed(samples))
                    builder.add_path(
                        strip_index,
                        samples,
                        boundary_strip=target_index in {0, len(frame.target_distances_mm) - 1},
                    )
            path = builder.toolpath()
            results.append(path)
            paths_per_layer.append(strip_index)
            maximum_spacing = max(maximum_spacing, frame.maximum_spacing_mm)
            maximum_segment = max(maximum_segment, builder.maximum_segment_length_mm)
            material_volume += math.fsum(point.material_volume_mm3 for point in path.points)
    cad_volume = math.fsum(model.body_map[item.body_id].volume or 0 for item in selections)
    return tuple(results), SurfaceSolidFillAudit(
        len(selections),
        depth_count,
        tuple(paths_per_layer),
        maximum_spacing,
        maximum_segment,
        min(thickness_values),
        max(thickness_values),
        material_volume,
        cad_volume,
        abs(material_volume - cad_volume) / cad_volume,
        root_gap,
    )


@dataclass(frozen=True, slots=True)
class _SurfaceFrame:
    across_is_u: bool
    root_coordinate: float
    far_coordinate: float
    along_low: float
    along_high: float
    metric_grid: _MetricGrid
    target_distances_mm: tuple[float, ...]
    maximum_spacing_mm: float


@dataclass(frozen=True, slots=True)
class _MetricGrid:
    across_coordinates: tuple[float, ...]
    along_coordinates: tuple[float, ...]
    cumulative_by_along: tuple[tuple[float, ...], ...]
    total_by_along: tuple[float, ...]


def _surface_frame(model, selection, surface, parameters):
    u_low, u_high, v_low, v_high = BRepTools.UVBounds_s(model.face_shapes[selection.face_id])
    edge = sample_edge_points(model.edge_shapes[selection.root_edge_id], 32)
    uv = []
    for point in edge:
        projector = GeomAPI_ProjectPointOnSurf(gp_Pnt(*point), surface)
        if projector.NbPoints() < 1:
            raise ValueError(f"freeform.root_edge_projection_failed: {selection.root_edge_id}")
        uv.append(tuple(float(value) for value in projector.LowerDistanceParameters()))
    u_span = max(value[0] for value in uv) - min(value[0] for value in uv)
    v_span = max(value[1] for value in uv) - min(value[1] for value in uv)
    tolerance = max(u_high - u_low, v_high - v_low) * 1.0e-3
    if u_span <= tolerance and v_span > tolerance:
        across_is_u = True
        root = math.fsum(value[0] for value in uv) / len(uv)
        low, high = u_low, u_high
        along_low, along_high = v_low, v_high
    elif v_span <= tolerance and u_span > tolerance:
        across_is_u = False
        root = math.fsum(value[1] for value in uv) / len(uv)
        low, high = v_low, v_high
        along_low, along_high = u_low, u_high
    else:
        raise ValueError(f"freeform.root_edge_not_parametric_boundary: {selection.root_edge_id}")
    if abs(root - low) <= tolerance:
        root, far = low, high
    elif abs(root - high) <= tolerance:
        root, far = high, low
    else:
        raise ValueError(f"freeform.root_edge_not_face_boundary: {selection.root_edge_id}")
    metric_grid = _metric_grid(
        surface,
        across_is_u,
        root,
        far,
        along_low,
        along_high,
        parameters.metric_across_samples,
        parameters.metric_along_samples,
    )
    usable = max(0.0, max(metric_grid.total_by_along) - parameters.bead_width_mm / 2)
    intervals = max(1, math.ceil(usable / parameters.path_spacing_mm - 1.0e-12))
    targets = tuple(index * usable / intervals for index in range(intervals + 1))
    maximum = max((right - left for left, right in zip(targets, targets[1:])), default=0.0)
    return _SurfaceFrame(
        across_is_u,
        root,
        far,
        along_low,
        along_high,
        metric_grid,
        targets,
        maximum,
    )


def _metric_grid(surface, across_is_u, root, far, along_low, along_high, across_count, along_count):
    coordinates = tuple(
        root + (far - root) * index / (across_count - 1) for index in range(across_count)
    )
    along = tuple(
        along_low + (along_high - along_low) * index / (along_count - 1)
        for index in range(along_count)
    )
    cumulative_by_along: list[tuple[float, ...]] = []
    for along_coordinate in along:
        points = tuple(
            _surface_point(surface, across_is_u, coordinate, along_coordinate)
            for coordinate in coordinates
        )
        cumulative = [0.0]
        for left, right in zip(points, points[1:]):
            cumulative.append(cumulative[-1] + math.dist(left, right))
        cumulative_by_along.append(tuple(cumulative))
    cumulative_grid = tuple(cumulative_by_along)
    return _MetricGrid(
        coordinates,
        along,
        cumulative_grid,
        tuple(values[-1] for values in cumulative_grid),
    )


def _interpolate_cumulative(coordinates, cumulative, target):
    index = min(max(1, bisect_left(cumulative, target)), len(cumulative) - 1)
    left, right = cumulative[index - 1], cumulative[index]
    ratio = 0.0 if right - left <= _EPSILON else (target - left) / (right - left)
    return coordinates[index - 1] + (coordinates[index] - coordinates[index - 1]) * ratio


def _sample_surface_contours(surface, orientation, frame, distance, maximum_step):
    grid = frame.metric_grid
    raw: list[tuple[float, float] | None] = []
    for index, total in enumerate(grid.total_by_along):
        if total + 1.0e-8 < distance:
            raw.append(None)
            continue
        across = _interpolate_cumulative(
            grid.across_coordinates,
            grid.cumulative_by_along[index],
            min(distance, total),
        )
        raw.append((across, grid.along_coordinates[index]))
    runs = []
    index = 0
    while index < len(raw):
        if raw[index] is None:
            index += 1
            continue
        start = index
        while index + 1 < len(raw) and raw[index + 1] is not None:
            index += 1
        end = index
        parameters = []
        if start > 0:
            parameters.append(_terminal_parameter(frame, distance, start - 1, start))
        parameters.extend(raw[start : end + 1])
        if end + 1 < len(raw):
            parameters.append(_terminal_parameter(frame, distance, end + 1, end))
        if len(parameters) >= 2:
            runs.append(
                _resample_surface_polyline(
                    surface,
                    orientation,
                    frame.across_is_u,
                    tuple(parameters),
                    maximum_step,
                )
            )
        index += 1
    return tuple(run for run in runs if len(run) >= 2)


def _terminal_parameter(frame, distance, invalid_index, valid_index):
    grid = frame.metric_grid
    invalid_total = grid.total_by_along[invalid_index]
    valid_total = grid.total_by_along[valid_index]
    ratio = (distance - invalid_total) / (valid_total - invalid_total)
    along = grid.along_coordinates[invalid_index] + ratio * (
        grid.along_coordinates[valid_index] - grid.along_coordinates[invalid_index]
    )
    return frame.far_coordinate, along


def _resample_surface_polyline(surface, orientation, across_is_u, parameters, maximum_step):
    points = tuple(
        _surface_point(surface, across_is_u, across, along) for across, along in parameters
    )
    cumulative = [0.0]
    for left, right in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + math.dist(left, right))
    # UV interpolation between samples lies on the surface rather than on the
    # chord used by the coarse metric estimate. Keep a small margin so the
    # audited three-dimensional segment cannot drift above the requested cap.
    count = max(1, math.ceil(cumulative[-1] / (maximum_step * 0.98) - 1.0e-12))
    result = []
    for index in range(count + 1):
        target = index * cumulative[-1] / count
        right = min(max(1, bisect_left(cumulative, target)), len(cumulative) - 1)
        low, high = cumulative[right - 1], cumulative[right]
        ratio = 0.0 if high - low <= _EPSILON else (target - low) / (high - low)
        first, second = parameters[right - 1], parameters[right]
        across = first[0] + (second[0] - first[0]) * ratio
        along = first[1] + (second[1] - first[1]) * ratio
        u, v = (across, along) if across_is_u else (along, across)
        result.append((_point(surface.Value(u, v)), _surface_normal(surface, orientation, u, v)))
    return tuple(result)


class _SurfacePathBuilder:
    def __init__(
        self,
        operation_id,
        body_id,
        depth_index,
        depth_count,
        depth,
        layer_height,
        parameters,
    ):
        self.operation_id = operation_id
        self.body_id = body_id
        self.depth_index = depth_index
        self.depth_count = depth_count
        self.depth = depth
        self.layer_height = layer_height
        self.parameters = parameters
        self.points = []
        self.events = []
        self.maximum_segment_length_mm = 0.0

    def add_path(self, strip_index, samples, *, boundary_strip=False):
        positions = tuple(_subtract(point, _scale(normal, self.depth)) for point, normal in samples)
        normals = tuple(normal for _, normal in samples)
        path_id = f"strip-{strip_index:03d}"
        layer_id = f"depth-{self.depth_index:03d}"
        region_id = f"{self.body_id}-{path_id}"
        tangent = _unit(_subtract(positions[1], positions[0]))
        if self.points:
            self._event("retract", layer_id, region_id)
            self._point(positions[0], normals[0], tangent, layer_id, region_id, "travel", "none", 0)
        else:
            self._point(
                positions[0], normals[0], tangent, layer_id, region_id, "approach", "none", 0
            )
        self._event("prime", layer_id, region_id)
        skin = self.depth_index in {1, self.depth_count} or boundary_strip
        role = "skin" if skin else "infill"
        for previous, current, normal in zip(positions, positions[1:], normals[1:], strict=False):
            length = math.dist(previous, current)
            if length <= _EPSILON:
                continue
            self.maximum_segment_length_mm = max(self.maximum_segment_length_mm, length)
            self._point(
                current,
                normal,
                _unit(_subtract(current, previous)),
                layer_id,
                region_id,
                "deposition",
                role,
                length * self.parameters.bead_width_mm * self.layer_height,
            )

    def _point(self, position, normal, tangent, layer_id, region_id, kind, role, volume):
        deposition = kind == "deposition"
        self.points.append(
            ToolpathPoint(
                f"point-{len(self.points) + 1:08d}",
                position,
                tangent,
                tuple(-value for value in normal),
                self.operation_id,
                "surface-solid-fill",
                layer_id,
                region_id,
                kind,
                extrusion_role=role,
                surface_normal=normal,
                feedrate_mm_min=(
                    self.parameters.deposition_feedrate_mm_min
                    if deposition
                    else self.parameters.travel_feedrate_mm_min
                ),
                bead_width_mm=self.parameters.bead_width_mm if deposition else None,
                layer_height_mm=self.layer_height if deposition else None,
                material_volume_mm3=volume,
            )
        )

    def _event(self, kind, layer_id, region_id):
        amount = self.parameters.retract_length_mm * (-1 if kind == "retract" else 1)
        self.events.append(
            ToolpathEvent(
                f"event-{len(self.events) + 1:08d}",
                kind,
                self.operation_id,
                "surface-solid-fill",
                layer_id,
                region_id,
                context={"sequence_index": len(self.points), "extrusion_length_mm": amount},
            )
        )

    def toolpath(self):
        return GeneratedToolpath(
            self.operation_id + "-surface-solid-v1",
            self.operation_id,
            points=tuple(self.points),
            events=tuple(self.events),
        )


def _thickness_samples(model, selection, surface, orientation):
    opposite = BRep_Tool.Surface_s(model.face_shapes[selection.opposite_face_id])
    u_low, u_high, v_low, v_high = BRepTools.UVBounds_s(model.face_shapes[selection.face_id])
    values = []
    for u_index in range(5):
        for v_index in range(5):
            u = u_low + (u_high - u_low) * u_index / 4
            v = v_low + (v_high - v_low) * v_index / 4
            point = surface.Value(u, v)
            projector = GeomAPI_ProjectPointOnSurf(point, opposite)
            if projector.NbPoints() < 1:
                raise ValueError(f"freeform.opposite_face_projection_failed: {selection.body_id}")
            nearest = projector.NearestPoint()
            normal = _surface_normal(surface, orientation, u, v)
            delta = (
                nearest.X() - point.X(),
                nearest.Y() - point.Y(),
                nearest.Z() - point.Z(),
            )
            distance = math.sqrt(math.fsum(value * value for value in delta))
            inward = -math.fsum(a * b for a, b in zip(delta, normal, strict=True))
            if inward < distance - 0.01:
                raise ValueError(f"freeform.opposite_face_not_normal_offset: {selection.body_id}")
            values.append(distance)
    return tuple(values)


def _root_edge_gap(model, selection):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    substrate = model.shapes.get(selection.substrate_body_id)
    if substrate is None:
        raise ValueError(f"unknown substrate body: {selection.substrate_body_id}")
    result = 0.0
    for point in sample_edge_points(model.edge_shapes[selection.root_edge_id], 64):
        distance = BRepExtrema_DistShapeShape(
            BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex(), substrate
        )
        distance.Perform()
        if not distance.IsDone():
            raise ValueError("freeform.root_support_distance_failed")
        result = max(result, distance.Value())
    return result


def _validate_selection(model, selection):
    if selection.body_id not in model.shapes:
        raise ValueError(f"unknown body: {selection.body_id}")
    for identifier, values in (
        (selection.face_id, model.face_shapes),
        (selection.opposite_face_id, model.face_shapes),
        (selection.root_edge_id, model.edge_shapes),
    ):
        if identifier not in values:
            raise ValueError(f"unknown topology reference: {identifier}")
    if model.face_map[selection.face_id].body_id != selection.body_id:
        raise ValueError("selected face belongs to another body")
    if model.face_map[selection.opposite_face_id].body_id != selection.body_id:
        raise ValueError("opposite face belongs to another body")
    if selection.face_id not in model.edge_map[selection.root_edge_id].face_ids:
        raise ValueError("root edge is not on selected face")


def _surface_point(surface, across_is_u, across, along):
    u, v = (across, along) if across_is_u else (along, across)
    return _point(surface.Value(u, v))


def _surface_normal(surface, orientation, u, v):
    properties = GeomLProp_SLProps(surface, float(u), float(v), 1, 1.0e-9)
    if not properties.IsNormalDefined():
        raise ValueError("freeform.surface_normal_undefined")
    direction = properties.Normal()
    normal: Vector3 = (float(direction.X()), float(direction.Y()), float(direction.Z()))
    if orientation == TopAbs_REVERSED:
        normal = (-normal[0], -normal[1], -normal[2])
    return _unit(normal)


def _point(point) -> Vector3:
    return float(point.X()), float(point.Y()), float(point.Z())


def _subtract(left: Vector3, right: Vector3) -> Vector3:
    return left[0] - right[0], left[1] - right[1], left[2] - right[2]


def _scale(value: Vector3, factor: float) -> Vector3:
    return value[0] * factor, value[1] * factor, value[2] * factor


def _unit(value: Vector3) -> Vector3:
    length = math.sqrt(math.fsum(item * item for item in value))
    if length <= _EPSILON:
        raise ValueError("freeform.zero_length_vector")
    return value[0] / length, value[1] / length, value[2] / length


def _checkpoint(cancelled):
    if cancelled is not None and cancelled():
        from ...postprocessing.indexed_tube import GenerationCancelled

        raise GenerationCancelled("Surface solid fill generation cancelled")


__all__ = [
    "SurfaceSolidBodySelection",
    "SurfaceSolidFillAudit",
    "SurfaceSolidFillParameters",
    "generate_surface_solid_fill",
]
