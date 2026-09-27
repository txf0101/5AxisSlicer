"""Live CAD bounded-wall Indexed generation; qualification remains downstream."""
from collections.abc import Callable
from dataclasses import dataclass
import math

from ...manufacturing.setup import TubeProcessParameters
from ...manufacturing.toolpath import GeneratedToolpath
from ...models import CadModel, Vector3
from .geometry import TubeFeature
from .indexed import IndexedSlicePlan, TubePlanningError, TubeSliceLayer, _PathBuilder
from .ruled_bead_volume import ruled_bead_volume
from .section import section_tube_layer
from .wall_tracks import build_wall_tracks
from .wedge_footprint import cad_wedge_footprint
from .wedge_layers import LayerBand, plan_layer_bands
from .wedge_plan import build_wedge_boundaries
from .wedge_material import _vector
from .wedge_tracks import WedgeTrackPoint, build_wedge_tracks


@dataclass(frozen=True, slots=True)
class BoundedIndexedSlicePlan(IndexedSlicePlan):
    generation_strategy: str = 'bounded_wall_tracks_v1'
    residual_task_count: int = 0
    maximum_track_width_mm: float = 0.6
    band_records: tuple[LayerBand, ...] = ()
    layer_bands: tuple[tuple[str, LayerBand], ...] = ()


def _checkpoint(checkpoint: Callable[[], None] | None) -> None:
    if checkpoint is not None:
        checkpoint()


def _append_path(builder: _PathBuilder, layer: TubeSliceLayer,
                 path: tuple[WedgeTrackPoint, ...], indexed: bool) -> None:
    loop: list[tuple[Vector3, Vector3, Vector3]] = []
    for index, point in enumerate(path):
        left, right = (path[index - 1], point) if index else (point, path[1])
        delta = tuple(b - a for a, b in zip(left.position, right.position))
        length = math.hypot(*delta)
        if length <= 0:
            raise ValueError('bounded path contains zero-length segment')
        loop.append((point.position, _vector(tuple(v / length for v in delta), "tangent"), point.outward_normal))
    volumes = tuple(ruled_bead_volume(
        a.position, b.position, _vector(tuple(n * a.width_mm for n in a.outward_normal), "lateral"),
        _vector(tuple(n * b.width_mm for n in b.outward_normal), "lateral"), a.height_mm, b.height_mm,
        layer.plane_normal) for a, b in zip(path, path[1:]))
    builder.add_layer(layer, tuple(loop), indexed=indexed,
                      heights_mm=tuple(p.height_mm for p in path),
                      widths_mm=tuple(p.width_mm for p in path), segment_volumes_mm3=volumes)


def _band_paths(model: CadModel, feature: TubeFeature, band: LayerBand,
                parameters: TubeProcessParameters, checkpoint: Callable[[], None] | None):
    origin = _vector(tuple(p + band.center_mm * n for p, n in zip(band.origin, band.build_axis)), "origin")
    section = section_tube_layer(model, feature.tube_body_id, origin, band.build_axis,
                                 feature.wall_thickness_mm,
                                 chord_error_mm=parameters.contour_chord_error_mm)
    paths: list[tuple[WedgeTrackPoint, ...]] = []
    residual_count = 0
    for track in build_wall_tracks(section, parameters.bead_width_mm).tracks:
        _checkpoint(checkpoint)
        candidate = build_wedge_tracks(band, track, parameters.layer_height_mm)
        paths.extend(candidate.paths)
        residual_count += len(candidate.residual_tasks)
    return tuple(paths), residual_count


def generate_bounded_indexed_toolpath(
    operation_id: str, model: CadModel, feature: TubeFeature, plan: IndexedSlicePlan,
    parameters: TubeProcessParameters, *, checkpoint: Callable[[], None] | None = None,
) -> tuple[BoundedIndexedSlicePlan, GeneratedToolpath, int]:
    """Generate from current BRep, preserving empty bands and explicit path gaps.

    New layer centerline_distance_mm is the owning region's reference station;
    it is not a plane-location or arclength-spacing assertion for this strategy.
    Actual plane origins, band bounds and per-point dimensions are authoritative.
    No failed region/section/path is silently skipped.
    """
    if parameters.safe_clearance_mm < max(parameters.bead_width_mm, parameters.layer_height_mm):
        raise TubePlanningError('tube.safe_connection_clearance_insufficient',
                                'clearance must cover at least one deposited bead envelope')
    builder = _PathBuilder(operation_id, parameters)
    bands = []
    layers: list[TubeSliceLayer] = []
    layer_bands = []
    residual_count = 0
    previous_region = None
    boundaries = build_wedge_boundaries(feature, plan.regions)
    for region, boundary in zip(plan.regions, boundaries, strict=True):
        _checkpoint(checkpoint)
        previous_layer_count = len(layers)
        footprint = cad_wedge_footprint(model, feature.tube_body_id, boundary,
                                        region.fixed_build_direction)
        candidates = plan_layer_bands(boundary, region.fixed_build_direction,
                                       footprint.vertices, parameters.layer_height_mm)
        for band in candidates.bands:
            _checkpoint(checkpoint)
            bands.append(band)
            paths, residuals = _band_paths(model, feature, band, parameters, checkpoint)
            residual_count += residuals
            if not paths:
                continue
            layer = TubeSliceLayer(f'layer-{len(layers) + 1:05d}', region.region_id,
                region.start_distance_mm,
                _vector(tuple(p + band.center_mm * n for p, n in zip(band.origin, band.build_axis)), "origin"),
                band.build_axis, parameters.layer_height_mm, 'bounded_columns')
            layers.append(layer)
            layer_bands.append((layer.layer_id, band))
            for path in paths:
                _checkpoint(checkpoint)
                _append_path(builder, layer, path, previous_region not in (None, region.region_id))
                previous_region = region.region_id
        if len(layers) == previous_layer_count:
            raise TubePlanningError("tube.empty_region", region.region_id)
    _checkpoint(checkpoint)
    actual_plan = BoundedIndexedSlicePlan(plan.regions, tuple(layers), plan.centerline_length_mm,
        plan.nominal_layer_height_mm, plan.contour_chord_error_mm,
        maximum_track_width_mm=parameters.bead_width_mm, residual_task_count=residual_count, band_records=tuple(bands), layer_bands=tuple(layer_bands))
    toolpath = GeneratedToolpath(f'{operation_id}-bounded-indexed-v1', operation_id,
                                points=tuple(builder.points), events=tuple(builder.events))
    return actual_plan, toolpath, residual_count



