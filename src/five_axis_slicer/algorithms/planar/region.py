"""B-rep planar sections with explicit island and hole topology.

All coordinates are in the workpiece build frame and all lengths are mm.
The module intentionally returns regions before any operation-specific path
generation: infill, offsets and spiral each need to make their own safe
decisions from the same recovered topology.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Callable

from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

from ...models import BoundingBox, CadModel, Vector3
from ...manufacturing.coordinates import RigidTransform
from .section_loops import SectionLoopError, recover_section_loops

Point2 = tuple[float, float]


class PlanarSectionError(ValueError):
    """A structured, user-visible planar slicing failure."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class PlanarRegion:
    """One exterior island and its holes, oriented in the slicing plane."""

    region_id: str
    outer: tuple[Vector3, ...]
    holes: tuple[tuple[Vector3, ...], ...] = ()

    def __post_init__(self) -> None:
        if len(self.outer) < 4 or self.outer[0] != self.outer[-1]:
            raise ValueError("outer contour must be a closed loop")
        if any(len(hole) < 4 or hole[0] != hole[-1] for hole in self.holes):
            raise ValueError("hole contour must be a closed loop")


@dataclass(frozen=True, slots=True)
class PlanarSliceLayer:
    layer_id: str
    z_mm: float
    regions: tuple[PlanarRegion, ...]


def slice_planar_layers(
    model: CadModel,
    body_ids: tuple[str, ...],
    *,
    first_layer_z_mm: float,
    layer_height_mm: float,
    last_layer_z_mm: float | None = None,
    sample_segments: int = 64,
    T_model_from_build: RigidTransform | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[PlanarSliceLayer, ...]:
    """Section selected solids by horizontal Build-XY planes.

    Empty layers are retained; this lets callers identify disconnected-height
    input without silently joining it to a neighbouring deposition layer.
    """

    _validate_layer_request(body_ids, first_layer_z_mm, layer_height_mm)
    transform = T_model_from_build or RigidTransform.identity("model")
    bodies, body_bounds = _selected_bodies(model, body_ids)
    upper = _last_layer_z(model, body_bounds, last_layer_z_mm, transform)
    if upper < first_layer_z_mm:
        raise PlanarSectionError("planar.layer_range_invalid", "last layer precedes first layer")
    count = int(math.floor((upper - first_layer_z_mm) / layer_height_mm + 1.0e-9)) + 1
    return _slice_layers(
        bodies,
        first_layer_z_mm,
        layer_height_mm,
        count,
        sample_segments,
        transform,
        cancelled,
    )


def _slice_layers(
    bodies: list[object],
    first_layer_z_mm: float,
    layer_height_mm: float,
    count: int,
    sample_segments: int,
    transform: RigidTransform,
    cancelled: Callable[[], bool] | None,
) -> tuple[PlanarSliceLayer, ...]:
    layers: list[PlanarSliceLayer] = []
    for index in range(count):
        if cancelled is not None and cancelled():
            from ...postprocessing.indexed_tube import GenerationCancelled

            raise GenerationCancelled("Planar region generation cancelled")
        z_mm = first_layer_z_mm + index * layer_height_mm
        layers.append(
            PlanarSliceLayer(
                f"layer-{index + 1:05d}",
                z_mm,
                _section_regions(bodies, z_mm, sample_segments, transform),
            )
        )
    return tuple(layers)


def _validate_layer_request(
    body_ids: tuple[str, ...], first_layer_z_mm: float, layer_height_mm: float
) -> None:
    if not body_ids:
        raise PlanarSectionError("planar.body_missing", "select at least one solid body")
    if not math.isfinite(first_layer_z_mm) or not math.isfinite(layer_height_mm):
        raise PlanarSectionError("planar.layer_value_invalid", "layer values must be finite")
    if layer_height_mm <= 0.0:
        raise PlanarSectionError("planar.layer_height_invalid", "layer height must be positive")


def _selected_bodies(
    model: CadModel, body_ids: tuple[str, ...]
) -> tuple[list[object], list[BoundingBox]]:
    bodies: list[object] = []
    body_bounds = []
    for body_id in body_ids:
        shape = model.shapes.get(body_id)
        if shape is None:
            raise PlanarSectionError("planar.body_missing", body_id)
        bodies.append(shape)
        body = model.body_map.get(body_id)
        if body is not None and body.bounds is not None:
            body_bounds.append(body.bounds)
    return bodies, body_bounds


def _last_layer_z(
    model: CadModel,
    body_bounds: list[BoundingBox],
    requested: float | None,
    transform: RigidTransform,
) -> float:
    if requested is not None:
        return requested
    bounds = body_bounds or ([] if model.bounds is None else [model.bounds])
    if not bounds:
        raise PlanarSectionError("planar.bounds_missing", "model bounds are required")
    T_build_from_model = transform.inverse()
    return max(
        T_build_from_model.transform_point(corner)[2]
        for bound in bounds
        for corner in _bounds_corners(bound.minimum, bound.maximum)
    )


def _section_regions(
    bodies: list[object],
    z_mm: float,
    sample_segments: int,
    T_model_from_build: RigidTransform,
) -> tuple[PlanarRegion, ...]:
    loops: list[tuple[Vector3, ...]] = []
    origin_model = T_model_from_build.transform_point((0.0, 0.0, z_mm))
    normal_model = T_model_from_build.transform_vector((0.0, 0.0, 1.0))
    T_build_from_model = T_model_from_build.inverse()
    for body in bodies:
        plane = gp_Pln(gp_Pnt(*origin_model), gp_Dir(*normal_model))
        face = BRepBuilderAPI_MakeFace(plane, -1.0e6, 1.0e6, -1.0e6, 1.0e6).Face()
        section = BRepAlgoAPI_Section(body, face, False)
        section.ComputePCurveOn1(True)
        section.Approximation(True)
        section.Build()
        if not section.IsDone():
            raise PlanarSectionError("planar.section_kernel_failed", f"z={z_mm}")
        try:
            body_loops = _recover_loops(section.Shape(), sample_segments)
        except PlanarSectionError as error:
            raise PlanarSectionError(error.code, f"z_mm={z_mm:.9g}, {error.detail}") from error
        loops.extend(
            tuple(T_build_from_model.transform_point(point) for point in loop)
            for loop in body_loops
        )
    return _classify_loops(loops)


def _bounds_corners(minimum: Vector3, maximum: Vector3) -> tuple[Vector3, ...]:
    return tuple(
        (x, y, z)
        for x in (minimum[0], maximum[0])
        for y in (minimum[1], maximum[1])
        for z in (minimum[2], maximum[2])
    )


def _recover_loops(shape: object, sample_segments: int) -> list[tuple[Vector3, ...]]:
    try:
        return recover_section_loops(shape, sample_segments)
    except SectionLoopError as error:
        raise PlanarSectionError(error.code, error.detail) from error


def _classify_loops(loops: list[tuple[Vector3, ...]]) -> tuple[PlanarRegion, ...]:
    records = [
        (loop, abs(_area(loop)), _centroid2(loop)) for loop in loops if abs(_area(loop)) > 1.0e-9
    ]
    regions: list[PlanarRegion] = []
    for outer, area, center in sorted(records, key=lambda item: item[1], reverse=True):
        if _nesting_depth(center, area, records) % 2:
            continue
        holes = _direct_holes(outer, area, records)
        regions.append(
            PlanarRegion(
                f"region-{len(regions) + 1:04d}",
                _orient(outer, True),
                tuple(_orient(hole, False) for hole in holes),
            )
        )
    return tuple(regions)


def _nesting_depth(
    center: Point2, area: float, records: list[tuple[tuple[Vector3, ...], float, Point2]]
) -> int:
    return sum(
        candidate_area > area and _contains(center, candidate)
        for candidate, candidate_area, _ in records
    )


def _direct_holes(
    outer: tuple[Vector3, ...],
    area: float,
    records: list[tuple[tuple[Vector3, ...], float, Point2]],
) -> tuple[tuple[Vector3, ...], ...]:
    depth = _nesting_depth(_centroid2(outer), area, records)
    return tuple(
        loop
        for loop, smaller_area, center in records
        if smaller_area < area
        and _contains(center, outer)
        and _nesting_depth(center, smaller_area, records) == depth + 1
    )


def _area(loop: tuple[Vector3, ...]) -> float:
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(loop, loop[1:]))


def _centroid2(loop: tuple[Vector3, ...]) -> Point2:
    count = len(loop) - 1
    return (
        sum(point[0] for point in loop[:-1]) / count,
        sum(point[1] for point in loop[:-1]) / count,
    )


def _contains(point: Point2, loop: tuple[Vector3, ...]) -> bool:
    x, y = point
    return (
        sum(
            (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]
            for a, b in zip(loop, loop[1:])
        )
        % 2
        == 1
    )


def _orient(loop: tuple[Vector3, ...], ccw: bool) -> tuple[Vector3, ...]:
    return loop if (_area(loop) > 0.0) == ccw else tuple(reversed(loop))
