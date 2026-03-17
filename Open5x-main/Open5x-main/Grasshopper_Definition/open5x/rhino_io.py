from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import rhino3dm

from .vector_math import estimate_radial_normals


def inspect_3dm(path: str | Path) -> dict:
    model = rhino3dm.File3dm.Read(str(path))
    if model is None:
        raise ValueError(f"Could not read 3DM file: {path}")
    type_counts = Counter(str(item.Geometry.ObjectType) for item in model.Objects)
    layers = [layer.Name for layer in model.Layers]
    return {
        "layers": layers,
        "object_count": len(model.Objects),
        "type_counts": dict(type_counts),
    }


def extract_first_polyline(
    path: str | Path,
    *,
    layer_name: str | None = None,
    closed: bool | None = None,
) -> tuple[np.ndarray, bool]:
    model = rhino3dm.File3dm.Read(str(path))
    if model is None:
        raise ValueError(f"Could not read 3DM file: {path}")
    for obj in model.Objects:
        layer = model.Layers[obj.Attributes.LayerIndex].Name
        if layer_name and layer != layer_name:
            continue
        curve = obj.Geometry
        if not getattr(curve, "IsPolyline", lambda: False)():
            continue
        polyline = curve.TryGetPolyline()
        points = np.array([[pt.X, pt.Y, pt.Z] for pt in polyline], dtype=float)
        curve_closed = bool(getattr(curve, "IsClosed", False))
        if len(points) >= 2 and np.allclose(points[0], points[-1]):
            points = points[:-1]
            curve_closed = True
        if closed is not None:
            curve_closed = closed
        return points, curve_closed
    if layer_name:
        raise ValueError(f"No polyline curve found on layer {layer_name!r} in {path}")
    raise ValueError(f"No polyline curve found in {path}")


def polyline_to_radial_spec(path: str | Path, *, layer_name: str | None = None) -> dict:
    points, closed = extract_first_polyline(path, layer_name=layer_name)
    normals = estimate_radial_normals(points)
    return {
        "name": Path(path).stem,
        "points": points.round(6).tolist(),
        "normals": normals.round(6).tolist(),
        "closed": closed,
        "extrude": True,
    }
