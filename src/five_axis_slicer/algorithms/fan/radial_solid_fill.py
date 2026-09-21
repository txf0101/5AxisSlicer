"""Finite-width radial solid fill with an explicit hub-to-blade bond.

The blade is sliced by concentric cylinders about source Z.  When the CAD
leaves a small assembly gap at the blade root, the first section is projected
inward until a finite-width bead touches the hub, then regular radial layers
continue into the blade.  No fixed hub radius is assumed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from collections.abc import Callable

from OCP.BRep import BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepTools import BRepTools
from OCP.gp import gp_Pnt

from ...manufacturing.toolpath import GeneratedToolpath, ToolpathEvent, ToolpathPoint
from ...models import CadModel, Vector3
from ..planar.feature_fill import FeatureFillParameters
from ..planar.region import PlanarSliceLayer, _area
from .assembly import blade_chart_center
from .chart_fill import radial_feature_fill
from .radial import chart_to_source, cylindrical_section, sample_chart_segment

_EPSILON = 1.0e-9


@dataclass(frozen=True, slots=True)
class RadialSolidBladeSelection:
    body_id: str
    hub_body_id: str
    root_face_id: str
    outer_face_id: str


@dataclass(frozen=True, slots=True)
class RadialSolidFillParameters:
    layer_height_mm: float = 0.2
    bead_width_mm: float = 0.4
    sampling_step_mm: float = 0.4
    deposition_feedrate_mm_min: float = 1200.0
    travel_feedrate_mm_min: float = 3000.0
    retract_length_mm: float = 1.0
    sample_segments: int = 128
    face_metric_samples: int = 65

    def __post_init__(self) -> None:
        for name in (
            "layer_height_mm",
            "bead_width_mm",
            "sampling_step_mm",
            "deposition_feedrate_mm_min",
            "travel_feedrate_mm_min",
            "retract_length_mm",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if self.sample_segments < 32 or self.face_metric_samples < 17:
            raise ValueError("radial solid sampling is too sparse")


@dataclass(frozen=True, slots=True)
class RadialSolidFillAudit:
    body_count: int
    layer_counts: tuple[int, ...]
    occupied_layer_counts: tuple[int, ...]
    bridge_layer_counts: tuple[int, ...]
    paths_per_body: tuple[int, ...]
    supported_first_radii_mm: tuple[float, ...]
    cad_root_section_radii_mm: tuple[float, ...]
    cad_outer_radii_mm: tuple[float, ...]
    maximum_radial_spacing_mm: float
    maximum_segment_length_mm: float
    first_layer_hub_gap_max_mm: float
    material_volume_mm3: float
    section_integral_volume_mm3: float
    cad_volume_mm3: float
    relative_material_volume_error: float
    relative_section_volume_error: float


def generate_radial_solid_fill(
    model: CadModel,
    selections: tuple[RadialSolidBladeSelection, ...],
    operation_prefix: str,
    parameters: RadialSolidFillParameters,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[tuple[GeneratedToolpath, ...], RadialSolidFillAudit]:
    if not selections or len({item.body_id for item in selections}) != len(selections):
        raise ValueError("unique non-empty blade selections required")
    results = []
    layer_counts = []
    occupied_counts = []
    bridge_counts = []
    path_counts = []
    supported_radii = []
    root_radii = []
    outer_radii = []
    maximum_segment = first_gap = material_volume = section_volume = 0.0
    for selection in selections:
        _checkpoint(cancelled)
        _validate_selection(model, selection)
        layers, bridge_count, supported_radius, root_radius, outer_radius = _manufacturing_layers(
            model, selection, parameters
        )
        plans = radial_feature_fill(
            layers,
            FeatureFillParameters(
                bead_width_mm=parameters.bead_width_mm,
                wall_count=2,
                infill_fraction=1.0,
                top_solid_layers=4,
                bottom_solid_layers=4,
            ),
        )
        builder = _RadialPathBuilder(
            f"{operation_prefix}-{selection.body_id}", parameters, bridge_count
        )
        for layer_index, plan in enumerate(plans):
            builder.add_layer(layer_index, plan)
        path = builder.toolpath()
        results.append(path)
        layer_counts.append(len(layers))
        occupied_counts.append(sum(bool(layer.regions) for layer in layers))
        bridge_counts.append(bridge_count)
        path_counts.append(builder.path_count)
        supported_radii.append(supported_radius)
        root_radii.append(root_radius)
        outer_radii.append(outer_radius)
        maximum_segment = max(maximum_segment, builder.maximum_segment_length_mm)
        first_gap = max(
            first_gap,
            _first_layer_hub_gap(model.shapes[selection.hub_body_id], builder.first_layer_points),
        )
        material_volume += math.fsum(point.material_volume_mm3 for point in path.points)
        section_volume += parameters.layer_height_mm * math.fsum(
            _area(region.outer) + math.fsum(_area(hole) for hole in region.holes)
            for layer in layers
            for region in layer.regions
        )
    cad_volume = math.fsum(model.body_map[item.body_id].volume or 0 for item in selections)
    return tuple(results), RadialSolidFillAudit(
        len(selections),
        tuple(layer_counts),
        tuple(occupied_counts),
        tuple(bridge_counts),
        tuple(path_counts),
        tuple(supported_radii),
        tuple(root_radii),
        tuple(outer_radii),
        parameters.layer_height_mm,
        maximum_segment,
        first_gap,
        material_volume,
        section_volume,
        cad_volume,
        abs(material_volume - cad_volume) / cad_volume,
        abs(section_volume - cad_volume) / cad_volume,
    )


def _checkpoint(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        from ...postprocessing.indexed_tube import GenerationCancelled

        raise GenerationCancelled("radial solid-fill generation cancelled")


def _manufacturing_layers(model, selection, parameters):
    root_min, _ = _face_radial_range(
        model.face_shapes[selection.root_face_id], parameters.face_metric_samples
    )
    _, outer_max = _face_radial_range(
        model.face_shapes[selection.outer_face_id], parameters.face_metric_samples
    )
    source_radius = root_min + 0.01
    center = blade_chart_center(model, selection.body_id)
    seed = cylindrical_section(
        model.shapes[selection.body_id],
        source_radius,
        sample_segments=parameters.sample_segments,
        seam_center_rad=center,
    )
    if not seed.regions:
        raise ValueError(f"fan.root_section_empty: {selection.body_id}")
    support_radius = _supported_projection_radius(
        seed,
        model.shapes[selection.hub_body_id],
        source_radius,
        parameters.bead_width_mm / 2,
    )
    count = math.ceil(
        (outer_max + parameters.layer_height_mm / 2 - support_radius) / parameters.layer_height_mm
    )
    radii = tuple(support_radius + index * parameters.layer_height_mm for index in range(count + 1))
    layers = []
    bridge_count = 0
    for radius in radii:
        if radius < source_radius - _EPSILON:
            layers.append(_relocate_layer(seed, radius))
            bridge_count += 1
        else:
            layers.append(
                cylindrical_section(
                    model.shapes[selection.body_id],
                    radius,
                    sample_segments=parameters.sample_segments,
                    seam_center_rad=center,
                )
            )
    return tuple(layers), bridge_count, support_radius, source_radius, outer_max


def _supported_projection_radius(seed, hub, source_radius, support_distance):
    source = tuple(
        chart_to_source(point)
        for region in seed.regions
        for loop in (region.outer, *region.holes)
        for point in loop[:-1]
    )
    low = max(_EPSILON, source_radius - 2.0)
    high = source_radius
    if _projected_gap(source, hub, low) > support_distance + 0.001:
        raise ValueError("fan.hub_bond_search_failed")
    if _projected_gap(source, hub, high) <= support_distance:
        return high
    for _ in range(20):
        middle = (low + high) / 2
        if _projected_gap(source, hub, middle) <= support_distance:
            low = middle
        else:
            high = middle
    return low


def _projected_gap(source, hub, target_radius):
    maximum = 0.0
    stride = max(1, len(source) // 64)
    for x, y, z in source[::stride]:
        scale = target_radius / math.hypot(x, y)
        maximum = max(maximum, _point_shape_gap((x * scale, y * scale, z), hub))
    return maximum


def _relocate_layer(layer: PlanarSliceLayer, radius: float) -> PlanarSliceLayer:
    def relocate(point):
        return point[0] / point[2] * radius, point[1], radius

    return replace(
        layer,
        layer_id=f"radius-{radius:.6f}",
        z_mm=radius,
        regions=tuple(
            replace(
                region,
                outer=tuple(relocate(point) for point in region.outer),
                holes=tuple(tuple(relocate(point) for point in hole) for hole in region.holes),
            )
            for region in layer.regions
        ),
    )


def _face_radial_range(face, count):
    surface = BRep_Tool.Surface_s(face)
    u_low, u_high, v_low, v_high = BRepTools.UVBounds_s(face)
    values = []
    for u_index in range(count):
        for v_index in range(count):
            point = surface.Value(
                u_low + (u_high - u_low) * u_index / (count - 1),
                v_low + (v_high - v_low) * v_index / (count - 1),
            )
            values.append(math.hypot(point.X(), point.Y()))
    return min(values), max(values)


class _RadialPathBuilder:
    def __init__(self, operation_id, parameters, bridge_count):
        self.operation_id = operation_id
        self.parameters = parameters
        self.bridge_count = bridge_count
        self.points = []
        self.events = []
        self.path_count = 0
        self.maximum_segment_length_mm = 0.0
        self.first_layer_points = []

    def add_layer(self, layer_index, plan):
        curves: list[tuple[str, tuple[Vector3, ...]]] = []
        for region in plan.regions:
            curves.extend(("skin", curve) for curve in region.wall_contours)
            infill_role = "skin" if plan.is_bottom_skin or plan.is_top_skin else "infill"
            curves.extend((infill_role, curve) for curve in region.infill_segments)
        for role, curve in curves:
            samples: list[Vector3] = []
            for left, right in zip(curve, curve[1:]):
                segment = sample_chart_segment(
                    left, right, max_step_mm=self.parameters.sampling_step_mm
                )
                samples.extend(segment if not samples else segment[1:])
            if len(samples) < 2:
                continue
            self.path_count += 1
            if (self.path_count + layer_index) % 2:
                samples.reverse()
            self._add_curve(layer_index, plan.layer_id, role, tuple(samples))

    def _add_curve(self, layer_index, layer_id, role, positions):
        region_id = f"path-{self.path_count:05d}"
        axes = tuple(_radial_axis(point) for point in positions)
        tangent = _unit(_subtract(positions[1], positions[0]))
        if self.points:
            self._event("retract", layer_id, region_id)
            self._point(positions[0], axes[0], tangent, layer_id, region_id, "travel", "none", 0)
        else:
            self._point(positions[0], axes[0], tangent, layer_id, region_id, "approach", "none", 0)
        self._event("prime", layer_id, region_id)
        for previous, current, axis in zip(positions, positions[1:], axes[1:], strict=False):
            length = math.dist(previous, current)
            if length <= _EPSILON:
                continue
            self.maximum_segment_length_mm = max(self.maximum_segment_length_mm, length)
            self._point(
                current,
                axis,
                _unit(_subtract(current, previous)),
                layer_id,
                region_id,
                "deposition",
                role,
                length * self.parameters.bead_width_mm * self.parameters.layer_height_mm,
            )
            if layer_index == 0:
                self.first_layer_points.append(current)

    def _point(self, position, axis, tangent, layer_id, region_id, kind, role, volume):
        deposition = kind == "deposition"
        normal = tuple(-value for value in axis)
        self.points.append(
            ToolpathPoint(
                f"point-{len(self.points) + 1:08d}",
                position,
                tangent,
                axis,
                self.operation_id,
                "radial-solid-fill",
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
                layer_height_mm=self.parameters.layer_height_mm if deposition else None,
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
                "radial-solid-fill",
                layer_id,
                region_id,
                context={"sequence_index": len(self.points), "extrusion_length_mm": amount},
            )
        )

    def toolpath(self):
        return GeneratedToolpath(
            self.operation_id + "-radial-solid-v1",
            self.operation_id,
            points=tuple(self.points),
            events=tuple(self.events),
        )


def _first_layer_hub_gap(hub, points):
    if not points:
        raise ValueError("fan.empty_root_bond_layer")
    stride = max(1, len(points) // 512)
    return max(_point_shape_gap(point, hub) for point in points[::stride])


def _point_shape_gap(point, shape):
    distance = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex(), shape)
    distance.Perform()
    if not distance.IsDone():
        raise ValueError("fan.hub_bond_distance_failed")
    return distance.Value()


def _validate_selection(model, selection):
    if selection.body_id not in model.shapes or selection.hub_body_id not in model.shapes:
        raise ValueError("unknown blade or hub body")
    for face_id in (selection.root_face_id, selection.outer_face_id):
        if face_id not in model.face_shapes:
            raise ValueError(f"unknown topology reference: {face_id}")
        if model.face_map[face_id].body_id != selection.body_id:
            raise ValueError("selected face belongs to another body")


def _radial_axis(point):
    radius = math.hypot(point[0], point[1])
    return -point[0] / radius, -point[1] / radius, 0.0


def _subtract(left, right):
    return tuple(a - b for a, b in zip(left, right, strict=True))


def _unit(vector):
    length = math.sqrt(math.fsum(value * value for value in vector))
    if length <= _EPSILON:
        return 1.0, 0.0, 0.0
    return tuple(value / length for value in vector)
