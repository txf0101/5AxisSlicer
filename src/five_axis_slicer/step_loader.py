"""STEP import orchestration with stable public loader and geometry helpers.

OpenCascade BRep handles remain attached to the in-memory model. Stable source
updates use geometry signatures because kernel traversal indices are local to a
single import.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from OCP.TColStd import TColStd_SequenceOfAsciiString

from .models import BodyInfo, CadModel, CadUnitInfo, EdgeInfo, FaceInfo, VertexInfo
from .step_reader import (
    ProductBodyMetadata as _ProductBodyMetadata,
)
from .step_reader import (
    StepReaderCancelled,
    StepReaderError,
    read_root_shape,
)
from .step_topology import (
    BodySummary,
    BodyTopology,
    body_shapes,
    body_summary,
    enumerate_body_topology,
    sample_edge_points,
    shape_bounds,
)
from .step_topology import (
    arc_length_midpoint as arc_length_midpoint,
)
from .step_topology import (
    edge_length_hint as edge_length_hint,
)
from .step_topology import (
    geometry_candidates as geometry_candidates,
)
from .step_topology import (
    geometry_signature as geometry_signature,
)

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
_STEP_KERNEL_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class _ResolvedBodyMetadata:
    name: str
    assembly_path: str


@dataclass(frozen=True, slots=True)
class _SourceFingerprint:
    size_bytes: int
    mtime_ns: int
    sha256: str


@dataclass(slots=True)
class _ModelParts:
    bodies: list[BodyInfo] = field(default_factory=list)
    faces: list[FaceInfo] = field(default_factory=list)
    edges: list[EdgeInfo] = field(default_factory=list)
    vertices: list[VertexInfo] = field(default_factory=list)
    shapes: dict[str, object] = field(default_factory=dict)
    face_shapes: dict[str, object] = field(default_factory=dict)
    edge_shapes: dict[str, object] = field(default_factory=dict)
    vertex_shapes: dict[str, object] = field(default_factory=dict)


class StepLoadError(RuntimeError):
    """The STEP source cannot be loaded into the supported CAD model."""


class StepLoadCancelled(StepLoadError):
    """Raised when a cooperative STEP load or source hash is cancelled."""


def file_sha256(path: Path, *, cancel_check: CancelCheck | None = None) -> str:
    _raise_if_cancelled(cancel_check)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_FILE_HASH_CHUNK_SIZE):
            _raise_if_cancelled(cancel_check)
            digest.update(chunk)
    _raise_if_cancelled(cancel_check)
    return digest.hexdigest()


def load_step(
    path: str | Path,
    *,
    cancel_check: CancelCheck | None = None,
    length_unit_override: str | None = None,
) -> CadModel:
    """Load one STEP into millimetre Source CS topology.

    OCP/XCAF calls share a process-wide slot because concurrent transfers are
    unstable in the supported Windows OCP runtime. Waiting remains cancellable.
    """

    with _step_kernel_slot(cancel_check):
        return _load_step_unlocked(
            path,
            cancel_check=cancel_check,
            length_unit_override=length_unit_override,
        )


def _load_step_unlocked(
    path: str | Path,
    *,
    cancel_check: CancelCheck | None,
    length_unit_override: str | None,
) -> CadModel:
    source_path = _resolve_step_path(path)
    initial = _source_fingerprint(source_path, cancel_check)
    root_shape, units, product_metadata = _read_root_shape(
        source_path,
        length_unit_override=length_unit_override,
        cancel_check=cancel_check,
    )
    sources = _body_shapes(root_shape)
    if not sources:
        raise StepLoadError(f"No solid, free shell, or free face found in STEP: {source_path}")
    summaries = _summarize_bodies(sources, cancel_check)
    resolved = _match_body_metadata(summaries, product_metadata, cancel_check=cancel_check)
    parts = _load_bodies(sources, summaries, resolved, cancel_check)
    _assert_source_unchanged(source_path, initial, cancel_check)
    return _cad_model(source_path, initial, units, root_shape, parts)


def _summarize_bodies(
    sources: list[tuple[str, object]],
    cancel_check: CancelCheck | None,
) -> list[BodySummary]:
    result: list[BodySummary] = []
    for kind, shape in sources:
        _raise_if_cancelled(cancel_check)
        result.append(body_summary(kind, shape))
    return result


def _load_bodies(
    sources: list[tuple[str, object]],
    summaries: list[BodySummary],
    metadata: tuple[_ResolvedBodyMetadata | None, ...],
    cancel_check: CancelCheck | None,
) -> _ModelParts:
    parts = _ModelParts()
    items = zip(sources, summaries, metadata, strict=True)
    for body_index, ((kind, shape), summary, names) in enumerate(items, start=1):
        _raise_if_cancelled(cancel_check)
        body_id = f"body_{body_index:03d}"
        topology = _enumerate_body_topology(body_id, shape, cancel_check=cancel_check)
        _append_topology(parts, topology)
        parts.shapes[body_id] = shape
        parts.bodies.append(_body_info(body_index, body_id, kind, summary, topology, names))
    return parts


def _append_topology(parts: _ModelParts, topology: BodyTopology) -> None:
    parts.faces.extend(topology.faces)
    parts.edges.extend(topology.edges)
    parts.vertices.extend(topology.vertices)
    parts.face_shapes.update(topology.face_shapes)
    parts.edge_shapes.update(topology.edge_shapes)
    parts.vertex_shapes.update(topology.vertex_shapes)


def _body_info(
    index: int,
    body_id: str,
    kind: str,
    summary: BodySummary,
    topology: BodyTopology,
    metadata: _ResolvedBodyMetadata | None,
) -> BodyInfo:
    label = "Solid" if kind == "solid" else "Sheet"
    return BodyInfo(
        body_id=body_id,
        index=index,
        name=f"{label} {index}" if metadata is None else metadata.name,
        color=PALETTE[(index - 1) % len(PALETTE)],
        kind=kind,
        assembly_path=None if metadata is None else metadata.assembly_path,
        bounds=summary.bounds,
        volume=summary.volume,
        surface_area=summary.surface_area,
        centroid=summary.centroid,
        edge_ids=[item.edge_id for item in topology.edges],
        face_ids=[item.face_id for item in topology.faces],
        vertex_ids=[item.vertex_id for item in topology.vertices],
        signature=summary.signature,
    )


def _cad_model(
    source_path: Path,
    source: _SourceFingerprint,
    units: CadUnitInfo,
    root_shape: object,
    parts: _ModelParts,
) -> CadModel:
    return CadModel(
        source_path=source_path,
        source_hash=source.sha256,
        bodies=parts.bodies,
        faces=parts.faces,
        edges=parts.edges,
        vertices=parts.vertices,
        shapes=parts.shapes,
        face_shapes=parts.face_shapes,
        edge_shapes=parts.edge_shapes,
        vertex_shapes=parts.vertex_shapes,
        units=units,
        bounds=shape_bounds(root_shape),
        source_size_bytes=source.size_bytes,
        source_mtime_ns=source.mtime_ns,
    )


def _read_root_shape(
    source_path: Path,
    *,
    length_unit_override: str | None,
    cancel_check: CancelCheck | None,
) -> tuple[object, CadUnitInfo, tuple[_ProductBodyMetadata, ...]]:
    """Keep the loader-level `_first_ascii` patch seam used by unit tests."""

    try:
        return read_root_shape(
            source_path,
            length_unit_override=length_unit_override,
            cancel_check=cancel_check,
            first_ascii=_first_ascii,
        )
    except StepReaderCancelled as exc:
        raise StepLoadCancelled(str(exc)) from exc
    except StepReaderError as exc:
        raise StepLoadError(str(exc)) from exc


def _body_shapes(root_shape: object) -> list[tuple[str, object]]:
    return body_shapes(root_shape)


def _enumerate_body_topology(
    body_id: str,
    body_shape: object,
    *,
    cancel_check: CancelCheck | None,
) -> BodyTopology:
    """Keep loader-level sampling patchable during cancellation tests."""

    return enumerate_body_topology(
        body_id,
        body_shape,
        cancel_check=cancel_check,
        cancel_guard=_raise_if_cancelled,
        sample_points=sample_edge_points,
    )


def _match_body_metadata(
    summaries: list[BodySummary],
    candidates: tuple[_ProductBodyMetadata, ...],
    *,
    cancel_check: CancelCheck | None,
) -> tuple[_ResolvedBodyMetadata | None, ...]:
    """Use XCAF names only when both geometry groups have one member."""

    body_groups: dict[str, list[int]] = {}
    for index, summary in enumerate(summaries):
        _raise_if_cancelled(cancel_check)
        body_groups.setdefault(summary.signature, []).append(index)
    candidate_groups: dict[str, list[_ProductBodyMetadata]] = {}
    for candidate in candidates:
        _raise_if_cancelled(cancel_check)
        signature = body_summary(candidate.kind, candidate.shape).signature
        candidate_groups.setdefault(signature, []).append(candidate)
    resolved: list[_ResolvedBodyMetadata | None] = [None] * len(summaries)
    for signature, body_indexes in body_groups.items():
        matches = candidate_groups.get(signature, ())
        if len(body_indexes) == 1 and len(matches) == 1:
            item = matches[0]
            resolved[body_indexes[0]] = _ResolvedBodyMetadata(item.name, item.assembly_path)
    return tuple(resolved)


def _source_fingerprint(path: Path, cancel_check: CancelCheck | None) -> _SourceFingerprint:
    _raise_if_cancelled(cancel_check)
    stat = path.stat()
    digest = file_sha256(path, cancel_check=cancel_check)
    return _SourceFingerprint(int(stat.st_size), int(stat.st_mtime_ns), digest)


def _assert_source_unchanged(
    path: Path,
    initial: _SourceFingerprint,
    cancel_check: CancelCheck | None,
) -> None:
    if _source_fingerprint(path, cancel_check) != initial:
        raise StepLoadError(f"STEP source changed while loading: {path}")


def _first_ascii(sequence: TColStd_SequenceOfAsciiString) -> str | None:
    if sequence.Length() <= 0:
        return None
    value = str(sequence.Value(1).ToCString()).strip()
    return value or None


@contextmanager
def _step_kernel_slot(cancel_check: CancelCheck | None) -> Iterator[None]:
    """Serialize OCP/XCAF access while preserving cancellation during wait."""

    while not _STEP_KERNEL_LOCK.acquire(timeout=0.05):
        _raise_if_cancelled(cancel_check)
    try:
        _raise_if_cancelled(cancel_check)
        yield
    finally:
        _STEP_KERNEL_LOCK.release()


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
