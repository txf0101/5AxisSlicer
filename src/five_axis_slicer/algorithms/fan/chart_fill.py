"""Bounded chart polyline reduction before kernel offsets.

Dense nearly collinear cylinder samples can create spurious tiny offset loops.
Reduction is bounded to 0.001 mm in the isometric cylindrical chart; it does
not permit crossing output, empty fallback contours, or unreported missing fill.
"""

from __future__ import annotations

from dataclasses import replace
import math

from ..planar.feature_fill import FeatureFillParameters, plan_feature_fill


def radial_feature_fill(layers, parameters: FeatureFillParameters):
    simplified = tuple(
        replace(
            layer,
            regions=tuple(
                replace(
                    region,
                    outer=_closed_reduce(region.outer),
                    holes=tuple(_closed_reduce(hole) for hole in region.holes),
                )
                for region in layer.regions
            ),
        )
        for layer in layers
    )
    plans = plan_feature_fill(simplified, parameters)
    for source, plan in zip(simplified, plans, strict=True):
        for region, filled in zip(source.regions, plan.regions, strict=True):
            if filled.wall_contours and filled.wall_contours[0] == region.outer:
                raise ValueError(f"fan.unresolved_chart_fill: {source.layer_id}")
    return plans


def _closed_reduce(loop):
    split = max(range(1, len(loop) - 1), key=lambda i: math.dist(loop[0], loop[i]))
    return tuple(_reduce(loop[: split + 1])[:-1] + _reduce(loop[split:]))


def _reduce(points):
    if len(points) <= 2:
        return list(points)
    a, b = points[0], points[-1]
    delta = tuple(y - x for x, y in zip(a, b))
    length2 = sum(v * v for v in delta)
    distances = []
    for point in points[1:-1]:
        t = (
            min(1.0, max(0.0, sum((p - x) * d for p, x, d in zip(point, a, delta)) / length2))
            if length2
            else 0.0
        )
        distances.append(math.dist(point, tuple(x + t * d for x, d in zip(a, delta))))
    maximum = max(distances)
    if maximum <= 0.001:
        return [a, b]
    split = distances.index(maximum) + 1
    return _reduce(points[: split + 1])[:-1] + _reduce(points[split:])
