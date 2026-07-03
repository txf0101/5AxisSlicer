from __future__ import annotations

import hashlib
import math
from pathlib import Path

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from .models import BodyInfo, CadModel, EdgeInfo


PALETTE: tuple[tuple[float, float, float], ...] = (
    (0.86, 0.86, 0.84),
    (0.72, 0.78, 0.84),
    (0.82, 0.76, 0.68),
    (0.64, 0.74, 0.70),
    (0.78, 0.72, 0.82),
    (0.84, 0.72, 0.72),
    (0.68, 0.72, 0.78),
    (0.78, 0.80, 0.68),
)


class StepLoadError(RuntimeError):
    """Raised when a STEP/STP file cannot be loaded into a usable model."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_step(path: str | Path) -> CadModel:
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists():
        raise StepLoadError(f"STEP file not found: {source_path}")
    if source_path.suffix.lower() not in {".step", ".stp"}:
        raise StepLoadError(f"Expected .step or .stp file: {source_path}")

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(source_path))
    if status != IFSelect_RetDone:
        raise StepLoadError(f"OpenCascade failed to read STEP: {source_path}")
    transferred = reader.TransferRoots()
    if transferred <= 0:
        raise StepLoadError(f"STEP file contains no transferable roots: {source_path}")

    root_shape = reader.OneShape()
    solid_explorer = TopExp_Explorer(root_shape, TopAbs_SOLID)

    bodies: list[BodyInfo] = []
    edges: list[EdgeInfo] = []
    shapes: dict[str, object] = {}
    edge_shapes: dict[str, object] = {}

    solid_index = 0
    while solid_explorer.More():
        solid_index += 1
        body_id = f"body_{solid_index:03d}"
        solid = TopoDS.Solid_s(solid_explorer.Current())
        shapes[body_id] = solid

        body_edges: list[str] = []
        edge_explorer = TopExp_Explorer(solid, TopAbs_EDGE)
        edge_index = 0
        while edge_explorer.More():
            edge_index += 1
            edge_id = f"{body_id}_edge_{edge_index:04d}"
            edge = TopoDS.Edge_s(edge_explorer.Current())
            samples = sample_edge_points(edge, target_segments=16)
            edge_shapes[edge_id] = edge
            body_edges.append(edge_id)
            edges.append(
                EdgeInfo(
                    edge_id=edge_id,
                    body_id=body_id,
                    index=edge_index,
                    point_count=len(samples),
                    length_hint=edge_length_hint(samples),
                )
            )
            edge_explorer.Next()

        bodies.append(
            BodyInfo(
                body_id=body_id,
                index=solid_index,
                name=f"Solid {solid_index}",
                color=PALETTE[(solid_index - 1) % len(PALETTE)],
                edge_ids=body_edges,
            )
        )
        solid_explorer.Next()

    if not bodies:
        raise StepLoadError(f"No solid/body found in STEP: {source_path}")

    return CadModel(
        source_path=source_path,
        source_hash=file_sha256(source_path),
        bodies=bodies,
        edges=edges,
        shapes=shapes,
        edge_shapes=edge_shapes,
    )


def sample_edge_points(edge: object, target_segments: int = 24) -> list[tuple[float, float, float]]:
    curve = BRepAdaptor_Curve(edge)
    first = float(curve.FirstParameter())
    last = float(curve.LastParameter())
    if not math.isfinite(first) or not math.isfinite(last) or first == last:
        return []

    count = max(2, target_segments + 1)
    points: list[tuple[float, float, float]] = []
    for i in range(count):
        t = first + (last - first) * (i / (count - 1))
        pnt = curve.Value(t)
        points.append((float(pnt.X()), float(pnt.Y()), float(pnt.Z())))
    return points


def edge_length_hint(points: list[tuple[float, float, float]]) -> float | None:
    if len(points) < 2:
        return None
    total = 0.0
    for left, right in zip(points, points[1:]):
        total += math.dist(left, right)
    return total

