"""Floating-point convex clipping of a straight rectangular geometric bead prism.

No sampled quadrature or physical deposition qualification is performed.
"""

from __future__ import annotations

from collections.abc import Iterable
import math

from ...models import Vector3
from .wedge_boundary import PlaneHalfSpace
from .wedge_material import _dot, _unit, _vector


def _sub(a: Vector3, b: Vector3) -> Vector3:
    return tuple(x - y for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


def _cross(a: Vector3, b: Vector3) -> Vector3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _intersection(a: Vector3, b: Vector3, da: float, db: float) -> Vector3:
    # Canonical endpoint order gives identical intersections on adjoining faces.
    if b < a:
        a, b, da, db = b, a, db, da
    scale = max(abs(da), abs(db))
    left, right = abs(da) / scale, abs(db) / scale
    fraction = left / (left + right)
    return tuple((1.0 - fraction) * x + fraction * y for x, y in zip(a, b, strict=True))  # type: ignore[return-value]


def _cap(points: set[Vector3], normal: Vector3) -> list[Vector3]:
    if len(points) < 3:
        return []
    center = _vector(tuple(math.fsum(p[i] / len(points) for p in points) for i in range(3)), "cap center")
    reference: Vector3 = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.8 else (0.0, 1.0, 0.0)
    u = _unit(_cross(normal, reference), "cap axis")
    v = _cross(normal, u)
    return sorted(
        points,
        key=lambda p: math.atan2(
            _dot(_sub(p, center), v),
            _dot(_sub(p, center), u),  # type: ignore[arg-type]
        ),
    )


def _clip_faces(
    faces: list[list[Vector3]],
    normal: Vector3,
    offset: float,
) -> list[list[Vector3]]:
    result: list[list[Vector3]] = []
    intersections: set[Vector3] = set()
    for face in faces:
        polygon: list[Vector3] = []
        previous = face[-1]
        da = _dot(previous, normal) + offset
        for current in face:
            db = _dot(current, normal) + offset
            if not math.isfinite(da) or not math.isfinite(db):
                raise ValueError("prism clipping distance overflow")
            if (da >= 0) != (db >= 0):
                point = _intersection(previous, current, da, db)
                polygon.append(point)
                intersections.add(point)
            if db >= 0:
                polygon.append(current)
            previous, da = current, db
        polygon = list(dict.fromkeys(polygon))
        if len(polygon) >= 3:
            result.append(polygon)
    cap = _cap(intersections, normal)
    if cap:
        result.append(cap)
    return result


def _volume(faces: list[list[Vector3]]) -> float:
    vertices = {p for face in faces for p in face}
    if len(vertices) < 4:
        return 0.0
    center: Vector3 = tuple(  # type: ignore[assignment]
        math.fsum(p[i] / len(vertices) for p in vertices) for i in range(3)
    )
    volumes = []
    for face in faces:
        a = _sub(face[0], center)
        for b, c in zip(face[1:], face[2:]):
            volumes.append(abs(_dot(a, _cross(_sub(b, center), _sub(c, center)))) / 6.0)
    result = math.fsum(volumes)
    if not math.isfinite(result):
        raise ValueError("prism volume overflow")
    return result


def clipped_bead_volume(
    start: Vector3,
    end: Vector3,
    width_axis: Vector3,
    build_axis: Vector3,
    width_mm: float,
    height_mm: float,
    halfspaces: Iterable[PlaneHalfSpace],
) -> float:
    """Return clipped straight-prism volume in mm³, without sampling.

    Cross-section axes are normalized. Their mutual orthogonality and their
    orthogonality to a nonzero segment are checked within 1e-12. Zero dimensions
    or a zero-length segment yield zero after validating inputs. A clipped
    prism is a geometric target, not a claim about achievable nozzle deposition.
    """

    start, end = _vector(start, "start"), _vector(end, "end")
    width, build = _unit(width_axis, "width_axis"), _unit(build_axis, "build_axis")
    if abs(_dot(width, build)) > 1e-12:
        raise ValueError("cross-section axes must be orthogonal")
    width_mm, height_mm = float(width_mm), float(height_mm)
    if any(not math.isfinite(x) or x < 0 for x in (width_mm, height_mm)):
        raise ValueError("prism dimensions must be finite and non-negative")
    planes = tuple(halfspaces)
    if any(not isinstance(p, PlaneHalfSpace) for p in planes):
        raise TypeError("halfspaces must contain PlaneHalfSpace values")
    delta = _vector(_sub(end, start), "segment")
    length = math.hypot(*delta)
    if not math.isfinite(length):
        raise ValueError("segment length overflow")
    if length == 0:
        return 0.0
    tangent = _unit(delta, "segment")
    if max(abs(_dot(tangent, width)), abs(_dot(tangent, build))) > 1e-12:
        raise ValueError("segment must be orthogonal to cross-section axes")
    if width_mm == 0 or height_mm == 0:
        return 0.0
    faces = _prism_faces(length, width_mm, height_mm)
    for plane in planes:
        normal = (_dot(tangent, plane.normal), _dot(width, plane.normal), _dot(build, plane.normal))
        faces = _clip_faces(faces, normal, plane.signed_distance(start))
        if not faces:
            return 0.0
    return _volume(faces)


def _prism_faces(length: float, width_mm: float, height_mm: float) -> list[list[Vector3]]:
    w, h = width_mm / 2, height_mm / 2
    vertices = [(x, y, z) for x in (0.0, length) for y in (-w, w) for z in (-h, h)]
    faces = [
        [vertices[i] for i in face]
        for face in (
            (0, 1, 3, 2),
            (4, 6, 7, 5),
            (0, 4, 5, 1),
            (2, 3, 7, 6),
            (0, 2, 6, 4),
            (1, 5, 7, 3),
        )
    ]
    return faces


__all__ = ["clipped_bead_volume"]
