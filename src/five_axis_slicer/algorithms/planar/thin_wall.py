"""Explicit thin-wall centreline policy for planar deposition."""

from __future__ import annotations

from dataclasses import dataclass
import math

from ...manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from ...models import Vector3


class PlanarThinWallError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class ThinWallParameters:
    bead_width_mm: float
    layer_height_mm: float
    maximum_passes: int = 3
    minimum_width_ratio: float = 0.6
    insufficient_width_strategy: str = "reject"

    def __post_init__(self) -> None:
        if self.bead_width_mm <= 0 or self.layer_height_mm <= 0 or self.maximum_passes < 1:
            raise PlanarThinWallError(
                "planar.thin_wall_parameter_invalid", "positive bead, layer and pass count required"
            )
        if not 0.0 < self.minimum_width_ratio <= 1.0:
            raise PlanarThinWallError(
                "planar.thin_wall_parameter_invalid", "minimum width ratio must be in (0, 1]"
            )
        if self.insufficient_width_strategy not in {"reduce", "reject"}:
            raise PlanarThinWallError(
                "planar.thin_wall_parameter_invalid", "unknown insufficient width strategy"
            )


def thin_wall_pass_count(width_mm: float, parameters: ThinWallParameters) -> int:
    """Choose equal-spaced centre lines; reject walls thinner than the policy."""
    if not math.isfinite(width_mm) or width_mm <= 0.0:
        raise PlanarThinWallError("planar.thin_wall_width_invalid", "wall width must be positive")
    if (
        width_mm < parameters.bead_width_mm * parameters.minimum_width_ratio
        and parameters.insufficient_width_strategy == "reject"
    ):
        raise PlanarThinWallError("planar.thin_wall_below_minimum", f"{width_mm:g} mm")
    return min(parameters.maximum_passes, max(1, int(width_mm / parameters.bead_width_mm + 0.5)))


def generate_open_wall_toolpath(
    operation_id: str,
    centerline: tuple[Vector3, ...],
    *,
    width_mm: float,
    layer_id: str,
    parameters: ThinWallParameters,
    closed: bool = False,
) -> GeneratedToolpath:
    """Generate a centreline pass for an open wall.

    Open walls are offset in the XY plane using the local perpendicular.  This
    is a deterministic planar rule; callers with a spatial wall can supply
    already projected coordinates.  Closed loops use the same rule and close
    every pass explicitly.
    """
    if len(centerline) < 2:
        raise PlanarThinWallError("planar.thin_wall_centerline_invalid", "need two or more points")
    passes = thin_wall_pass_count(width_mm, parameters)
    points: list[ToolpathPoint] = []
    base = centerline + ((centerline[0],) if closed and centerline[-1] != centerline[0] else ())
    for pass_index in range(passes):
        offset = (pass_index - (passes - 1) / 2.0) * parameters.bead_width_mm
        pass_points = _offset_points(base, offset)
        if pass_index and points:
            _append_point(
                points,
                points[-1].position,
                pass_points[0],
                operation_id,
                layer_id,
                parameters,
            )
        _append_wall_pass(points, pass_points, pass_index, operation_id, layer_id, parameters)
    return GeneratedToolpath(f"{operation_id}-thin-wall-v1", operation_id, points=tuple(points))


def _offset_points(points: tuple[Vector3, ...], offset: float) -> tuple[Vector3, ...]:
    if abs(offset) <= 1e-12:
        return points
    # For a closed contour, offset each vertex by the intersection of its two
    # adjacent offset lines (miter construction).  Translating by the first
    # segment normal would distort corners and is unsuitable for concentric
    # multi-pass walls.
    closed = len(points) > 2 and points[0] == points[-1]
    if closed:
        out: list[Vector3] = []
        for i in range(len(points) - 1):
            prev, cur, nxt = points[i - 1], points[i], points[(i + 1) % (len(points) - 1)]
            a = _unit((cur[0] - prev[0], cur[1] - prev[1]))
            b = _unit((nxt[0] - cur[0], nxt[1] - cur[1]))
            n1, n2 = (-a[1], a[0]), (-b[1], b[0])
            bis = _unit((n1[0] + n2[0], n1[1] + n2[1]))
            denom = bis[0] * n1[0] + bis[1] * n1[1]
            scale = offset / denom if abs(denom) > 1e-9 else offset
            out.append((cur[0] + bis[0] * scale, cur[1] + bis[1] * scale, cur[2]))
        return tuple(out) + (out[0],)
    out = []
    for index, point in enumerate(points):
        if index == 0:
            tangent = _unit((points[1][0] - point[0], points[1][1] - point[1]))
            bisector, scale = (-tangent[1], tangent[0]), offset
        elif index == len(points) - 1:
            tangent = _unit((point[0] - points[index - 1][0], point[1] - points[index - 1][1]))
            bisector, scale = (-tangent[1], tangent[0]), offset
        else:
            previous, following = points[index - 1], points[index + 1]
            incoming = _unit((point[0] - previous[0], point[1] - previous[1]))
            outgoing = _unit((following[0] - point[0], following[1] - point[1]))
            first_normal = (-incoming[1], incoming[0])
            next_normal = (-outgoing[1], outgoing[0])
            bisector = _unit((first_normal[0] + next_normal[0], first_normal[1] + next_normal[1]))
            denominator = bisector[0] * first_normal[0] + bisector[1] * first_normal[1]
            scale = offset / denominator if abs(denominator) > 1e-9 else offset
        out.append((point[0] + bisector[0] * scale, point[1] + bisector[1] * scale, point[2]))
    return tuple(out)


def _append_wall_pass(
    points: list[ToolpathPoint],
    pass_points: tuple[Vector3, ...],
    pass_index: int,
    operation_id: str,
    layer_id: str,
    parameters: ThinWallParameters,
) -> None:
    previous = pass_points[0]
    for index, point in enumerate(pass_points):
        if index == 0 and pass_index:
            continue
        deposition = index > 0
        volume = (
            math.dist(previous, point) * parameters.bead_width_mm * parameters.layer_height_mm
            if deposition
            else 0.0
        )
        points.append(
            ToolpathPoint(
                f"point-{len(points) + 1:07d}",
                point,
                _tangent(pass_points, index),
                (0, 0, -1),
                operation_id,
                "planar_thin_wall",
                layer_id,
                "open-wall",
                "deposition" if deposition else "approach",
                extrusion_role="thin_wall" if deposition else "none",
                surface_normal=(0, 0, 1),
                bead_width_mm=parameters.bead_width_mm if deposition else None,
                layer_height_mm=parameters.layer_height_mm if deposition else None,
                feedrate_mm_min=600.0,
                material_volume_mm3=volume,
            )
        )
        previous = point


def _unit(vector: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(*vector)
    if length <= 1e-12:
        raise PlanarThinWallError("planar.thin_wall_centerline_invalid", "repeated point")
    return vector[0] / length, vector[1] / length


def _append_point(
    points: list[ToolpathPoint],
    start: Vector3,
    end: Vector3,
    operation_id: str,
    layer_id: str,
    parameters: ThinWallParameters,
) -> None:
    points.append(
        ToolpathPoint(
            f"point-{len(points) + 1:07d}",
            end,
            _tangent((start, end), 0),
            (0, 0, -1),
            operation_id,
            "planar_thin_wall",
            layer_id,
            "open-wall",
            "travel",
            extrusion_role="none",
            surface_normal=(0, 0, 1),
            feedrate_mm_min=600.0,
        )
    )


def _tangent(points: tuple[Vector3, ...], index: int) -> Vector3:
    left, right = (
        (points[index], points[index + 1]) if index == 0 else (points[index - 1], points[index])
    )
    vector = tuple(b - a for a, b in zip(left, right))
    length = math.sqrt(sum(item * item for item in vector))
    if length <= 1e-12:
        raise PlanarThinWallError("planar.thin_wall_centerline_invalid", "repeated point")
    return (vector[0] / length, vector[1] / length, vector[2] / length)
