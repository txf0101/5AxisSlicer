"""Finite-width solid fill for a rectangular trimmed freeform face.

The selected root edge must be one complete parametric boundary of the face.
The explicit root-edge-outward strategy deposits root-parallel growth layers,
filling the wall thickness inside each layer. The legacy default advances
across the face inside each thickness layer. Both strategies require a bounded
parametric face; neither is a general arbitrary-face offsetter.
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
    surface_growth_strategy: str = "surface_thickness"

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
        if (
            self.surface_growth_strategy == "surface_thickness"
            and self.layer_height_mm > self.solid_thickness_mm
        ):
            raise ValueError("layer_height_mm exceeds solid thickness")
        if (
            self.surface_growth_strategy == "root_edge_outward"
            and self.layer_height_mm > self.bead_width_mm * 2
        ):
            raise ValueError("growth layer height exceeds twice the bead width")
        if self.metric_across_samples < 17 or self.metric_along_samples < 9:
            raise ValueError("surface metric sampling is too sparse")
        if self.surface_growth_strategy not in {"surface_thickness", "root_edge_outward"}:
            raise ValueError("unknown surface solid growth strategy")


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
    growth_layer_count: int = 0
    surface_growth_strategy: str = "surface_thickness"


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
    if parameters.surface_growth_strategy == "root_edge_outward":
        return _generate_root_edge_outward(
            model, selections, operation_prefix, parameters, cancelled=cancelled
        )
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


def _generate_root_edge_outward(model, selections, operation_prefix, parameters, *, cancelled):
    """Fill each root-parallel growth layer across its complete wall thickness."""

    # Each thickness pass owns one equal-width volume band. The deposited bead
    # keeps the requested physical width; neighboring tracks meet because
    # the center spacing is bounded by path_spacing_mm <= bead_width_mm.
    depth_count = math.ceil(
        parameters.solid_thickness_mm / min(parameters.bead_width_mm, parameters.path_spacing_mm)
        - 1.0e-10
    )
    depth_width = parameters.solid_thickness_mm / depth_count
    depth_centers = tuple((index + 0.5) * depth_width for index in range(depth_count))
    results = []
    paths_per_layer = []
    maximum_spacing = maximum_segment = 0.0
    thickness_values = []
    material_volume = 0.0
    root_gap = 0.0
    growth_layer_count = 0
    for selection in selections:
        _validate_selection(model, selection)
        if selection.substrate_body_id is None:
            raise ValueError(f"freeform.root_support_missing: {selection.body_id}")
        surface = BRep_Tool.Surface_s(model.face_shapes[selection.face_id])
        orientation = model.face_shapes[selection.face_id].Orientation()
        frame = _surface_frame(model, selection, surface, parameters)
        thickness = _thickness_samples(model, selection, surface, orientation)
        thickness_values.extend(thickness)
        if min(thickness) < parameters.solid_thickness_mm - 0.02:
            raise ValueError(f"freeform.solid_thickness_exceeds_body: {selection.body_id}")
        root_gap = max(root_gap, _root_edge_gap(model, selection))
        # The root edge must touch the already built substrate within the first
        # growth layer. This is a necessary local support check, not IPW proof.
        if root_gap > parameters.layer_height_mm / 2 + 0.01:
            raise ValueError(f"freeform.root_support_gap: {selection.body_id}")
        extent = max(frame.metric_grid.total_by_along)
        # The first center sits half a growth layer outside the root. Its bead
        # touches the substrate without placing the nozzle tip on the final
        # substrate track; the last center is also inside the far boundary.
        growth_count = math.ceil(extent / parameters.layer_height_mm - 1.0e-10)
        growth_height = extent / growth_count
        growth_layer_count += growth_count
        first_contours = _sample_surface_contours(
            surface,
            orientation,
            frame,
            growth_height / 2,
            parameters.sampling_step_mm,
            include_growth=True,
        )
        if not first_contours:
            raise ValueError(f"freeform.growth_layer_empty: {selection.body_id}:0")
        # The first thickness track must touch the substrate. Later tracks in
        # the same growth layer meet the preceding deposited bead side by side.
        first_support_gap = _first_track_support_gap(
            model, selection.substrate_body_id, first_contours, depth_centers[0]
        )
        if first_support_gap > growth_height / 2 + 0.01:
            raise ValueError(f"freeform.first_layer_unsupported: {selection.body_id}")
        operation_id = f"{operation_prefix}-{selection.body_id}-growth"
        builder = _SurfacePathBuilder(
            operation_id,
            selection.body_id,
            1,
            growth_count,
            depth_centers[0],
            growth_height,
            parameters,
            growth_layer_index=1,
            effective_bead_width=depth_width,
        )
        for growth_index in range(growth_count):
            _checkpoint(cancelled)
            distance = (growth_index + 0.5) * growth_height
            contours = (
                first_contours
                if growth_index == 0
                else _sample_surface_contours(
                    surface,
                    orientation,
                    frame,
                    distance,
                    parameters.sampling_step_mm,
                    include_growth=True,
                )
            )
            if not contours:
                raise ValueError(f"freeform.growth_layer_empty: {selection.body_id}:{growth_index}")
            builder.growth_layer_index = growth_index + 1
            strip_index = 0
            for depth_index, depth in enumerate(depth_centers):
                for samples in contours:
                    strip_index += 1
                    if (strip_index + growth_index) % 2 == 0:
                        samples = tuple(reversed(samples))
                    builder.add_path(
                        strip_index,
                        samples,
                        boundary_strip=depth_index in {0, depth_count - 1},
                        depth=depth,
                        growth_reference=tuple(sample[2] for sample in samples),
                    )
            paths_per_layer.append(strip_index)
            maximum_spacing = max(maximum_spacing, depth_width)
        path = builder.toolpath()
        results.append(path)
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
        growth_layer_count,
        "root_edge_outward",
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


def _sample_surface_contours(
    surface, orientation, frame, distance, maximum_step, *, include_growth=False
):
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
                    1.0 if frame.far_coordinate > frame.root_coordinate else -1.0,
                    tuple(parameters),
                    maximum_step,
                    include_growth=include_growth,
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


def _resample_surface_polyline(
    surface, orientation, across_is_u, across_sign, parameters, maximum_step, *, include_growth
):
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
        normal = _surface_normal(surface, orientation, u, v)
        across = (0.0, 0.0, 0.0)
        if include_growth:
            properties = GeomLProp_SLProps(surface, float(u), float(v), 1, 1.0e-9)
            derivative = properties.D1U() if across_is_u else properties.D1V()
            across = _scale(_unit(_direction(derivative)), across_sign)
        result.append((_point(surface.Value(u, v)), normal, across))
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
        *,
        growth_layer_index=None,
        effective_bead_width=None,
    ):
        self.operation_id = operation_id
        self.body_id = body_id
        self.depth_index = depth_index
        self.depth_count = depth_count
        self.depth = depth
        self.layer_height = layer_height
        self.parameters = parameters
        self.growth_layer_index = growth_layer_index
        self.effective_bead_width = effective_bead_width or parameters.bead_width_mm
        self.points = []
        self.events = []
        self.maximum_segment_length_mm = 0.0
        self.strip_index = 0

    def add_path(
        self, strip_index, samples, *, boundary_strip=False, depth=None, growth_reference=None
    ):
        self.strip_index = strip_index
        actual_depth = self.depth if depth is None else depth
        positions = tuple(
            _subtract(point, _scale(normal, actual_depth)) for point, normal, _ in samples
        )
        normals = tuple(normal for _, normal, _ in samples)
        nozzle_axes = (
            tuple(_scale(normal, -1.0) for normal in normals)
            if growth_reference is None
            else _growth_nozzle_axes(positions, normals, growth_reference)
        )
        path_id = f"strip-{strip_index:03d}"
        layer_id = (
            f"depth-{self.depth_index:03d}"
            if self.growth_layer_index is None
            else f"growth-{self.growth_layer_index:03d}"
        )
        region_id = f"{self.body_id}-{path_id}" if self.growth_layer_index is None else self.body_id
        tangent = _unit(_subtract(positions[1], positions[0]))
        if self.points:
            self._event("retract", layer_id, region_id)
            self._point(
                positions[0],
                normals[0],
                nozzle_axes[0],
                tangent,
                layer_id,
                region_id,
                "travel",
                "none",
                0,
            )
        else:
            self._point(
                positions[0],
                normals[0],
                nozzle_axes[0],
                tangent,
                layer_id,
                region_id,
                "approach",
                "none",
                0,
            )
        self._event("prime", layer_id, region_id)
        skin = (
            self.depth_index in {1, self.depth_count} or boundary_strip
            if self.growth_layer_index is None
            else self.growth_layer_index in {1, self.depth_count} or boundary_strip
        )
        role = "skin" if skin else "infill"
        for previous, current, normal, nozzle_axis in zip(
            positions, positions[1:], normals[1:], nozzle_axes[1:], strict=False
        ):
            length = math.dist(previous, current)
            if length <= _EPSILON:
                continue
            self.maximum_segment_length_mm = max(self.maximum_segment_length_mm, length)
            self._point(
                current,
                normal,
                nozzle_axis,
                _unit(_subtract(current, previous)),
                layer_id,
                region_id,
                "deposition",
                role,
                length * self.effective_bead_width * self.layer_height,
            )

    def _point(
        self, position, normal, nozzle_axis, tangent, layer_id, region_id, kind, role, volume
    ):
        deposition = kind == "deposition"
        point_id = (
            f"point-{len(self.points) + 1:08d}"
            if self.growth_layer_index is None
            else f"strip-{self.strip_index:03d}-point-{len(self.points) + 1:08d}"
        )
        self.points.append(
            ToolpathPoint(
                point_id,
                position,
                tangent,
                nozzle_axis,
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


def _first_track_support_gap(model, substrate_body_id, contours, first_depth):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    substrate = model.shapes[substrate_body_id]
    maximum = 0.0
    for contour in contours:
        for point, normal, _ in contour:
            center = _subtract(point, _scale(normal, first_depth))
            distance = BRepExtrema_DistShapeShape(
                BRepBuilderAPI_MakeVertex(gp_Pnt(*center)).Vertex(), substrate
            )
            distance.Perform()
            if not distance.IsDone():
                raise ValueError("freeform.first_layer_support_distance_failed")
            maximum = max(maximum, distance.Value())
    return maximum


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


def _direction(direction) -> Vector3:
    return float(direction.X()), float(direction.Y()), float(direction.Z())


def _growth_nozzle_axes(positions, normals, references):
    result = []
    for index, (normal, reference) in enumerate(zip(normals, references, strict=True)):
        before = positions[max(0, index - 1)]
        after = positions[min(len(positions) - 1, index + 1)]
        tangent = _unit(_subtract(after, before))
        across = _unit(_cross(normal, tangent))
        if _dot(across, reference) < 0:
            across = _scale(across, -1.0)
        if _dot(across, reference) < 0.5:
            raise ValueError("freeform.growth_direction_ambiguous")
        result.append(_scale(across, -1.0))
    return tuple(result)


def _cross(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _dot(left: Vector3, right: Vector3) -> float:
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


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
