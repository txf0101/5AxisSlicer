"""Volume of a ruled bead with linearly varying lateral span and thickness.

The build axis stays fixed. This geometric volume neither clips to CAD/wedges
nor proves that extrusion forms the assumed cross-section.
"""

import math

from ...models import Vector3
from .wedge_material import _dot, _unit, _vector
from .wedge_volume import _cross


def ruled_bead_volume(
    start: Vector3, end: Vector3, lateral_start: Vector3, lateral_end: Vector3,
    height_start: float, height_end: float, build_axis: Vector3,
) -> float:
    """Integrate the ruled volume exactly, excluding folds and zero-width spans.

    Lateral vectors include their full width. The mapping is c(t)+s*r(t)+u*h(t)*n,
    t in [0,1], s,u in [-1/2,1/2]. Integrating its signed Jacobian removes the
    odd s/u terms and leaves a quadratic in t. All four lateral-edge corner
    Jacobians must have the same sign so taking absolute volume cannot hide a fold.
    """
    a, b = _vector(start, "start"), _vector(end, "end")
    r0, r1 = _vector(lateral_start, "lateral start"), _vector(lateral_end, "lateral end")
    axis = _unit(build_axis, "build axis")
    if any(not math.isfinite(h) or h <= 0 for h in (height_start, height_end)):
        raise ValueError("ruled bead requires positive finite heights")
    if any(abs(_dot(r, axis)) > 1e-10 for r in (r0, r1)):
        raise ValueError("lateral span must lie in the build plane")
    delta = _vector(tuple(y - x for x, y in zip(a, b)), "segment")
    dr = _vector(tuple(y - x for x, y in zip(r0, r1)), "lateral change")
    jacobians = [
        _dot(_cross(_vector(tuple(d + s * v for d, v in zip(delta, dr)), "edge"), r), axis)
        for s in (-0.5, 0.5) for r in (r0, r1)
    ]
    if min(jacobians) <= 0 <= max(jacobians):
        raise ValueError("ruled bead is degenerate or folded")
    j0, j1 = _dot(_cross(delta, r0), axis), _dot(_cross(delta, r1), axis)
    volume = abs((2 * height_start * j0 + height_start * j1
                  + height_end * j0 + 2 * height_end * j1) / 6)
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("ruled bead volume is not finite and positive")
    return volume
