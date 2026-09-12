"""Content-addressed preview cache with atomic manifest publication."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .gcode_arrays import _segment_npz_arrays, _timeline_arrays_from_steps
from .gcode_preview import (
    CACHE_VERSION,
    LEGACY_CACHE_VERSIONS,
    CancelCheck,
    GCodeLoadCancelled,
    GCodePreview,
    GCodeRenderIndex,
    GCodeSourceFingerprint,
    GCodeSourceIntegrityError,
    GCodeTimelineArrays,
    _preview_from_binary_cache,
    preview_from_json,
)
from .gcode_source import application_cache_dir

CacheStemFactory = Callable[..., Path]


def file_sha256(source_path: Path, *, cancel_check: CancelCheck | None = None) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            _raise_if_cancelled(cancel_check)
            digest.update(chunk)
    _raise_if_cancelled(cancel_check)
    return digest.hexdigest()


def capture_source_fingerprint(
    source_path: Path,
    *,
    expected_sha256: str | None = None,
    cancel_check: CancelCheck | None = None,
) -> GCodeSourceFingerprint:
    """Hash one stable source snapshot and optionally bind it to an expected hash."""

    before = source_path.stat()
    digest = file_sha256(source_path, cancel_check=cancel_check)
    after = source_path.stat()
    if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
        raise GCodeSourceIntegrityError(f"G-code source changed while hashing: {source_path}")
    fingerprint = GCodeSourceFingerprint(
        sha256=digest,
        size_bytes=int(after.st_size),
        mtime_ns=int(after.st_mtime_ns),
    )
    if expected_sha256 is None:
        return fingerprint
    normalized_expected = str(expected_sha256).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized_expected):
        raise GCodeSourceIntegrityError("expected G-code source SHA-256 must contain 64 hex digits")
    if fingerprint.sha256 != normalized_expected:
        raise GCodeSourceIntegrityError(f"G-code source hash mismatch: {source_path}")
    return fingerprint


def cache_stem(
    source_path: Path,
    version: str = CACHE_VERSION,
    *,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
) -> Path:
    stat = source_path.stat()
    if version == CACHE_VERSION:
        identity = source_sha256 or file_sha256(source_path)
        semantics_key = (
            "<unconfirmed>" if controller_semantics is None else str(controller_semantics).strip()
        )
        key_text = (
            f"{version}|{source_path}|{stat.st_size}|{stat.st_mtime_ns}|{identity}|{semantics_key}"
        )
    else:
        key_text = f"{version}|{source_path}|{stat.st_size}|{stat.st_mtime_ns}"
    key = hashlib.sha1(key_text.encode("utf-8", errors="replace")).hexdigest()
    return application_cache_dir("gcode_preview_cache") / key


def load_preview_cache(
    source_path: Path,
    *,
    stem_factory: CacheStemFactory,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
) -> GCodePreview | None:
    """Return a complete cache generation; corrupt or partial generations miss."""

    if source_path.stat().st_size < 25_000_000:
        return None
    for version in (CACHE_VERSION, *LEGACY_CACHE_VERSIONS):
        try:
            preview = _load_generation(
                source_path,
                version,
                stem_factory,
                source_sha256 if version == CACHE_VERSION else None,
                controller_semantics if version == CACHE_VERSION else None,
            )
            if preview is None or preview.controller_semantics != controller_semantics:
                continue
            if version != CACHE_VERSION:
                try:
                    write_preview_cache(preview, stem_factory=stem_factory)
                except Exception:
                    pass
            preview._index().source = "cache"
            return preview
        except Exception:
            continue
    return None


def _load_generation(
    source_path: Path,
    version: str,
    stem_factory: CacheStemFactory,
    source_sha256: str | None,
    controller_semantics: str | None,
) -> GCodePreview | None:
    manifest_path = _cache_path(
        source_path,
        version,
        stem_factory,
        source_sha256,
        controller_semantics,
        ".json.gz",
    )
    if not manifest_path.exists():
        return None
    with gzip.open(manifest_path, "rt", encoding="utf-8") as stream:
        payload = json.load(stream)
    index_path = _cache_path(
        source_path,
        version,
        stem_factory,
        source_sha256,
        controller_semantics,
        ".npz",
    )
    binary_name = payload.get("binary_arrays")
    if isinstance(binary_name, str) and binary_name:
        index_path = manifest_path.parent / Path(binary_name).name
    if binary_name and index_path.exists():
        return _preview_from_binary_cache(payload, source_path, index_path)

    preview = preview_from_json(payload, source_path)
    if index_path.exists():
        try:
            preview.render_index = GCodeRenderIndex.from_npz(index_path, preview.segments)
        except Exception:
            preview.render_index = None
    if preview.render_index is None and version != CACHE_VERSION:
        preview._index().cache_format = "legacy-json.gz+rebuilt-render-index-v2"
    return preview


def write_preview_cache(
    preview: GCodePreview,
    *,
    stem_factory: CacheStemFactory,
    cancel_check: CancelCheck | None = None,
    source_sha256: str | None = None,
) -> None:
    """Publish one cache generation without exposing a partial binary.

    A unique NPZ generation is closed before the gzip manifest replaces the
    previous manifest. Readers use only the manifest target. Failed publication
    removes the unpublished generation and leaves the prior generation valid.
    """

    source_path = preview.source_path
    if source_path == Path("<memory>") or source_path.stat().st_size < 25_000_000:
        return
    _raise_if_cancelled(cancel_check)
    manifest_path = _cache_path(
        source_path,
        CACHE_VERSION,
        stem_factory,
        source_sha256,
        preview.controller_semantics,
        ".json.gz",
    )
    legacy_index_path = _cache_path(
        source_path,
        CACHE_VERSION,
        stem_factory,
        source_sha256,
        preview.controller_semantics,
        ".npz",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    index = preview._index()
    index.cache_format = "json.gz+npz-render-index-v2"
    timeline_arrays = preview.timeline_arrays or _timeline_arrays_from_steps(preview.timeline)
    previous_index = _previous_index_path(manifest_path, legacy_index_path)

    temporary_index: Path | None = None
    temporary_manifest: Path | None = None
    generation_index: Path | None = None
    manifest_committed = False
    try:
        temporary_index = _write_temporary_index(
            legacy_index_path.parent, preview, index, timeline_arrays
        )
        _raise_if_cancelled(cancel_check)
        generation_index = legacy_index_path.with_name(
            f"{legacy_index_path.stem}.{uuid.uuid4().hex}{legacy_index_path.suffix}"
        )
        os.replace(temporary_index, generation_index)
        temporary_index = None
        temporary_manifest = _write_temporary_manifest(
            manifest_path.parent,
            {"summary": preview.summary(), "binary_arrays": generation_index.name},
        )
        _raise_if_cancelled(cancel_check)
        os.replace(temporary_manifest, manifest_path)
        temporary_manifest = None
        manifest_committed = True
        for obsolete in (previous_index, legacy_index_path):
            if obsolete is not None and obsolete != generation_index:
                _unlink_quietly(obsolete)
    finally:
        _unlink_quietly(temporary_index)
        _unlink_quietly(temporary_manifest)
        if not manifest_committed:
            _unlink_quietly(generation_index)


def _cache_path(
    source_path: Path,
    version: str,
    stem_factory: CacheStemFactory,
    source_sha256: str | None,
    controller_semantics: str | None,
    suffix: str,
) -> Path:
    if source_sha256 is None and controller_semantics is None:
        stem = stem_factory(source_path, version)
    else:
        stem = stem_factory(
            source_path,
            version,
            source_sha256=source_sha256,
            controller_semantics=controller_semantics,
        )
    return stem.with_suffix(suffix)


def _previous_index_path(manifest_path: Path, legacy_path: Path) -> Path | None:
    if not manifest_path.exists():
        return None
    try:
        with gzip.open(manifest_path, "rt", encoding="utf-8") as stream:
            name = json.load(stream).get("binary_arrays")
        if isinstance(name, str) and name:
            return manifest_path.parent / Path(name).name
        return legacy_path if name else None
    except Exception:
        return None


def _write_temporary_index(
    directory: Path,
    preview: GCodePreview,
    index: GCodeRenderIndex,
    timeline: GCodeTimelineArrays,
) -> Path:
    temporary_path: Path | None = None
    complete = False
    try:
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".npz", delete=False) as stream:
            temporary_path = Path(stream.name)
            np.savez(
                stream,
                layer_min=np.asarray([index.layer_min], dtype=np.int32),
                layer_max=np.asarray([index.layer_max], dtype=np.int32),
                layer_prefix_counts=index.layer_prefix_counts.astype(np.int32, copy=False),
                timeline_indices=index.timeline_indices.astype(np.int32, copy=False),
                segment_indices=index.segment_indices.astype(np.int32, copy=False),
                source=np.asarray([index.source]),
                timeline_line_numbers=timeline.line_numbers,
                timeline_layers=timeline.layers,
                timeline_starts=timeline.starts,
                timeline_ends=timeline.ends,
                timeline_rotary_starts=timeline.rotary_starts,
                timeline_rotary_ends=timeline.rotary_ends,
                timeline_move_codes=timeline.move_codes,
                timeline_role_codes=timeline.role_codes,
                timeline_feedrates=timeline.feedrates,
                timeline_delta_es=timeline.delta_es,
                timeline_widths=timeline.widths,
                timeline_heights=timeline.heights,
                timeline_machine_starts=timeline.machine_starts,
                timeline_machine_ends=timeline.machine_ends,
                timeline_flags=timeline.flags,
                timeline_path_segment_indices=timeline.path_segment_indices,
                # NumPy's stub reserves arbitrary keyword names for
                # ``allow_pickle`` even though these keys are fixed array names.
                **_segment_npz_arrays(preview.segments),  # type: ignore[arg-type]
            )
        complete = True
        return temporary_path
    finally:
        if not complete:
            _unlink_quietly(temporary_path)


def _write_temporary_manifest(directory: Path, payload: dict[str, object]) -> Path:
    temporary_path: Path | None = None
    complete = False
    try:
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".json.gz", delete=False) as stream:
            temporary_path = Path(stream.name)
        with gzip.open(temporary_path, "wt", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        complete = True
        return temporary_path
    finally:
        if not complete:
            _unlink_quietly(temporary_path)


def _unlink_quietly(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise GCodeLoadCancelled("G-code loading cancelled")
