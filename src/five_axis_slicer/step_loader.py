from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Callable

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
STEP_SUFFIXES = {".step", ".stp"}
_FILE_HASH_CHUNK_SIZE = 1024 * 1024

CancelCheck = Callable[[], bool]


class StepLoadError(RuntimeError):
    """STEP/STP 文件无法读取为可用 CAD 模型时抛出。"""


class StepLoadCancelled(StepLoadError):
    """Raised when a cooperative STEP load or source hash is cancelled."""


def file_sha256(path: Path, *, cancel_check: CancelCheck | None = None) -> str:
    """计算源文件哈希，保存项目时用于确认模型来源。"""

    _raise_if_cancelled(cancel_check)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            _raise_if_cancelled(cancel_check)
            chunk = stream.read(_FILE_HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            _raise_if_cancelled(cancel_check)
    _raise_if_cancelled(cancel_check)
    return digest.hexdigest()


def load_step(
    path: str | Path,
    *,
    cancel_check: CancelCheck | None = None,
) -> CadModel:
    _raise_if_cancelled(cancel_check)
    source_path = _resolve_step_path(path)
    _raise_if_cancelled(cancel_check)
    source_stat = source_path.stat()
    source_hash = file_sha256(source_path, cancel_check=cancel_check)
    _raise_if_cancelled(cancel_check)
    root_shape = _read_root_shape(source_path)
    _raise_if_cancelled(cancel_check)
    solid_explorer = TopExp_Explorer(root_shape, TopAbs_SOLID)

    bodies: list[BodyInfo] = []
    edges: list[EdgeInfo] = []
    shapes: dict[str, object] = {}
    edge_shapes: dict[str, object] = {}

    solid_index = 0
    while solid_explorer.More():
        _raise_if_cancelled(cancel_check)
        solid_index += 1
        body_id = f"body_{solid_index:03d}"
        solid = TopoDS.Solid_s(solid_explorer.Current())
        shapes[body_id] = solid

        # OpenCascade 的 edge 枚举来自真实 BRep 拓扑。这里不先转网格，
        # 以免丢失后续制造分组可能需要的边线身份。
        body_edges: list[str] = []
        edge_explorer = TopExp_Explorer(solid, TopAbs_EDGE)
        edge_index = 0
        while edge_explorer.More():
            _raise_if_cancelled(cancel_check)
            edge_index += 1
            edge_id = f"{body_id}_edge_{edge_index:04d}"
            edge = TopoDS.Edge_s(edge_explorer.Current())
            samples = sample_edge_points(edge, target_segments=16)
            _raise_if_cancelled(cancel_check)
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

        _raise_if_cancelled(cancel_check)
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

    _raise_if_cancelled(cancel_check)
    final_stat = source_path.stat()
    final_hash = file_sha256(source_path, cancel_check=cancel_check)
    _raise_if_cancelled(cancel_check)
    if (
        final_stat.st_size != source_stat.st_size
        or final_stat.st_mtime_ns != source_stat.st_mtime_ns
        or final_hash != source_hash
    ):
        raise StepLoadError(f"STEP source changed while loading: {source_path}")

    return CadModel(
        source_path=source_path,
        source_hash=source_hash,
        bodies=bodies,
        edges=edges,
        shapes=shapes,
        edge_shapes=edge_shapes,
        source_size_bytes=int(source_stat.st_size),
        source_mtime_ns=int(source_stat.st_mtime_ns),
    )


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise StepLoadCancelled("STEP loading cancelled")


def _resolve_step_path(path: str | Path) -> Path:
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists():
        raise StepLoadError(f"STEP file not found: {source_path}")
    if source_path.suffix.lower() not in STEP_SUFFIXES:
        raise StepLoadError(f"Expected .step or .stp file: {source_path}")
    return source_path


def _read_root_shape(source_path: Path) -> object:
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(source_path))
    if status != IFSelect_RetDone:
        raise StepLoadError(f"OpenCascade failed to read STEP: {source_path}")
    transferred = reader.TransferRoots()
    if transferred <= 0:
        raise StepLoadError(f"STEP file contains no transferable roots: {source_path}")
    return reader.OneShape()


def sample_edge_points(edge: object, target_segments: int = 24) -> list[tuple[float, float, float]]:
    """按参数区间均匀采样边线，用于预览 polyline 和长度提示。"""

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
    """根据采样点累计折线长度，给右侧列表提供近似值。"""

    if len(points) < 2:
        return None
    total = 0.0
    for left, right in zip(points, points[1:]):
        total += math.dist(left, right)
    return total
