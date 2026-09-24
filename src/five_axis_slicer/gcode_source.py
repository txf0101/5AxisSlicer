from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import tempfile
from typing import Callable, Iterable

import numpy as np


_BLADE_MARKER = re.compile(rb"^[ \t]*;[ \t]*\xe5\x8f\xb6\xe8\xbd\xae[ \t]*([1-8])[ \t]*$")
_OPERATION_POINT = re.compile(rb"^[ \t]*;[ \t]*PAC[ \t]+POINT[ \t]+\d+[ \t]+(op\d{1,6})-")
_FIVE_AXIS_WORDS = tuple(axis.encode("ascii") for axis in ("F", "X", "Y", "Z", "A", "C", "E"))
_SOURCE_HASH_CHUNK_SIZE = 1024 * 1024

ProgressCallback = Callable[[float, str], None]
CancelCheck = Callable[[], bool]


class GCodeSourceIndexCancelled(RuntimeError):
    pass


def _qt_cache_location() -> Path | None:
    try:
        from PyQt5.QtCore import QStandardPaths

        location = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        return Path(location) if location else None
    except Exception:
        return None


@lru_cache(maxsize=None)
def application_cache_dir(component: str) -> Path:
    """Return a writable per-user cache directory for one application component.

    Qt's cache location keeps installed applications independent of the current
    working directory.  A temporary cache directory is the safe fallback
    for portable/headless environments or locked-down user profiles.
    """

    safe_component = re.sub(r"[^A-Za-z0-9_.-]+", "_", component).strip("._") or "cache"
    candidates: list[Path] = []
    qt_location = _qt_cache_location()
    if qt_location is not None:
        candidates.append(qt_location / "5AxisSclicer_V2.0" / safe_component)

    fallback = Path(tempfile.gettempdir()) / "5AxisSclicer_V2.0" / safe_component
    candidates.append(fallback)
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=candidate):
                pass
            return candidate
        except OSError:
            continue
    return fallback


@dataclass(frozen=True, slots=True)
class GCodeStage:
    stage_id: str
    kind: str
    ordinal: int | None
    start_line: int
    end_line: int

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.stage_id,
            "kind": self.kind,
            "ordinal": self.ordinal,
            "start_line": self.start_line,
            "end_line": self.end_line,
        }


class GCodeSourceIndex:
    """Memory-mapped line index for large G-code source files.

    The offset table is cached as uint64 data. Source text remains in its
    original file and only the requested context window is decoded.
    """

    def __init__(
        self,
        path: str | Path,
        cache_dir: str | Path | None = None,
        *,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.exists():
            raise FileNotFoundError(f"G-code file not found: {self.path}")
        self._stream = None
        self._mmap = None
        self._offsets = np.asarray([0], dtype=np.uint64)
        self._source_signature: dict[str, object] = {}
        self._cache_dir = (
            Path(cache_dir) if cache_dir else application_cache_dir("gcode_source_index")
        )
        self._progress_callback = progress_callback
        self._cancel_check = cancel_check
        try:
            self._raise_if_cancelled()
            self._stream = self.path.open("rb")
            source_size = os.fstat(self._stream.fileno()).st_size
            self._mmap = (
                mmap.mmap(self._stream.fileno(), 0, access=mmap.ACCESS_READ)
                if source_size
                else None
            )
            self._source_signature = self._capture_source_signature()
            if self._mmap is None:
                blade_markers: list[tuple[int, int]] = []
                operation_markers: list[tuple[int, str]] = []
            else:
                self._offsets, blade_markers, operation_markers = self._load_or_build_index()
            self.stages = self._build_stages(blade_markers, operation_markers)
            self._report_progress(1.0)
        except Exception:
            self.close()
            raise

    @property
    def line_count(self) -> int:
        return max(0, int(self._offsets.size) - 1)

    @property
    def source_signature(self) -> dict[str, object]:
        return dict(self._source_signature)

    def read_line(self, line_number: int) -> str:
        if line_number < 1 or line_number > self.line_count:
            raise IndexError(f"Line number out of range: {line_number}")
        start = int(self._offsets[line_number - 1])
        end = int(self._offsets[line_number])
        return self._mmap[start:end].rstrip(b"\r\n").decode("utf-8", errors="replace")

    def read_context(self, line_number: int, radius: int = 20) -> list[tuple[int, str]]:
        if self.line_count == 0:
            return []
        center = max(1, min(int(line_number), self.line_count))
        low = max(1, center - max(0, int(radius)))
        high = min(self.line_count, center + max(0, int(radius)))
        return [(number, self.read_line(number)) for number in range(low, high + 1)]

    def search(self, query: str, start_line: int = 1, forward: bool = True) -> int | None:
        needle = query.strip().encode("utf-8")
        if not needle or self.line_count == 0:
            return None
        line = max(1, min(int(start_line), self.line_count))
        expression = re.compile(re.escape(needle), re.IGNORECASE)
        assert self._mmap is not None
        if forward:
            match = expression.search(self._mmap, int(self._offsets[line - 1]))
            if match is None and line > 1:
                match = expression.search(self._mmap, 0, int(self._offsets[line - 1]))
        else:
            boundary = int(self._offsets[line])
            match = None
            for candidate in expression.finditer(self._mmap, 0, boundary):
                match = candidate
            if match is None:
                for candidate in expression.finditer(self._mmap, boundary):
                    match = candidate
        if match is None:
            return None
        return self.line_number_for_offset(match.start())

    def line_number_for_offset(self, byte_offset: int) -> int:
        index = bisect_right(self._offsets, int(byte_offset)) - 1
        return max(1, min(index + 1, self.line_count))

    def representative_five_axis_line(self) -> int | None:
        start_line = 1
        blades = [stage for stage in self.stages if stage.kind == "blade"]
        if blades:
            start_line = blades[0].start_line
        for number in range(start_line, min(self.line_count, start_line + 100_000) + 1):
            raw = self._line_bytes(number).strip().upper()
            if not raw.startswith((b"G0", b"G1")):
                continue
            if all(
                re.search(rb"(?:^|[ \t])" + word + rb"[-+.]?\d", raw) for word in _FIVE_AXIS_WORDS
            ):
                return number
        return None

    def close(self) -> None:
        mapping = getattr(self, "_mmap", None)
        if mapping is not None:
            mapping.close()
            self._mmap = None
        stream = getattr(self, "_stream", None)
        if stream is not None:
            stream.close()
            self._stream = None
        offsets = getattr(self, "_offsets", None)
        if isinstance(offsets, np.memmap):
            mapping = getattr(offsets, "_mmap", None)
            if mapping is not None:
                mapping.close()

    def __enter__(self) -> "GCodeSourceIndex":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _line_bytes(self, line_number: int) -> bytes:
        if self._mmap is None:
            return b""
        start = int(self._offsets[line_number - 1])
        end = int(self._offsets[line_number])
        return self._mmap[start:end].rstrip(b"\r\n")

    def _cache_key(self) -> str:
        signature = self._source_signature
        value = (
            "gcode-source-v3|"
            f"{signature['path']}|{signature['size_bytes']}|{signature['mtime_ns']}|"
            f"{signature['sha256']}"
        ).encode("utf-8")
        return hashlib.sha1(value).hexdigest()

    def _capture_source_signature(self) -> dict[str, object]:
        assert self._stream is not None
        stat = os.fstat(self._stream.fileno())
        digest = hashlib.sha256()
        if self._mmap is not None:
            source_view = memoryview(self._mmap)
            try:
                for start in range(0, len(source_view), _SOURCE_HASH_CHUNK_SIZE):
                    self._raise_if_cancelled()
                    chunk_view = source_view[start : start + _SOURCE_HASH_CHUNK_SIZE]
                    try:
                        digest.update(chunk_view)
                    finally:
                        chunk_view.release()
                    self._raise_if_cancelled()
            finally:
                source_view.release()
        else:
            self._raise_if_cancelled()
        self._raise_if_cancelled()
        return {
            "path": str(self.path),
            "name": self.path.name,
            "size_bytes": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "sha256": digest.hexdigest(),
        }

    def _load_or_build_index(
        self,
    ) -> tuple[np.ndarray, list[tuple[int, int]], list[tuple[int, str]]]:
        self._raise_if_cancelled()
        key = self._cache_key()
        offsets_path = self._cache_dir / f"{key}.npy"
        metadata_path = self._cache_dir / f"{key}.json"
        offsets: np.ndarray | None = None
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            offsets = np.load(offsets_path, mmap_mode="r", allow_pickle=False)
            if not self._valid_offsets(offsets):
                raise ValueError("Invalid G-code source-index offsets")
            markers = self._validated_markers(payload, line_count=max(0, int(offsets.size) - 1))
            operations = self._validated_operation_markers(
                payload, line_count=max(0, int(offsets.size) - 1)
            )
        except Exception:
            if isinstance(offsets, np.memmap):
                mapping = getattr(offsets, "_mmap", None)
                if mapping is not None:
                    mapping.close()
        else:
            assert offsets is not None
            self._raise_if_cancelled()
            self._report_progress(1.0)
            return offsets, markers, operations

        offsets: list[int] = [0]
        markers: list[tuple[int, int]] = []
        operations: list[tuple[int, str]] = []
        self._mmap.seek(0)
        line_number = 0
        while True:
            raw = self._mmap.readline()
            if not raw:
                break
            line_number += 1
            offsets.append(self._mmap.tell())
            match = _BLADE_MARKER.match(raw.rstrip(b"\r\n"))
            if match:
                markers.append((line_number, int(match.group(1))))
            operation = _OPERATION_POINT.match(raw)
            if operation:
                operation_id = operation.group(1).decode("ascii")
                if not operations or operation_id != operations[-1][1]:
                    operations.append((line_number, operation_id))
            if line_number % 4096 == 0:
                self._raise_if_cancelled()
                self._report_progress(self._mmap.tell() / max(1, len(self._mmap)))
        self._raise_if_cancelled()
        if offsets[-1] != len(self._mmap):
            offsets.append(len(self._mmap))
        array = np.asarray(offsets, dtype=np.uint64)
        try:
            self._write_cache(offsets_path, metadata_path, array, markers, operations)
        except GCodeSourceIndexCancelled:
            raise
        except Exception:
            # Index persistence is an optimization; source-backed operations stay
            # available when a profile, roaming drive, or explicit cache is read-only.
            self._raise_if_cancelled()
        self._report_progress(1.0)
        return array, markers, operations

    def _valid_offsets(self, offsets: np.ndarray) -> bool:
        if offsets.dtype != np.uint64 or offsets.ndim != 1 or offsets.size < 1:
            return False
        if int(offsets[0]) != 0 or int(offsets[-1]) != len(self._mmap):
            return False
        return bool(np.all(offsets[1:] >= offsets[:-1]))

    def _validated_markers(self, payload: object, *, line_count: int) -> list[tuple[int, int]]:
        if not isinstance(payload, dict):
            raise ValueError("Invalid G-code source-index metadata")
        markers: list[tuple[int, int]] = []
        previous_line = 0
        for item in payload.get("markers", []):
            if not isinstance(item, dict):
                raise ValueError("Invalid G-code stage marker")
            line = int(item["line"])
            ordinal = int(item["ordinal"])
            if line <= previous_line or line < 1 or line > line_count or ordinal not in range(1, 9):
                raise ValueError("Invalid G-code stage marker")
            markers.append((line, ordinal))
            previous_line = line
        return markers

    def _validated_operation_markers(
        self, payload: object, *, line_count: int
    ) -> list[tuple[int, str]]:
        if not isinstance(payload, dict) or "operations" not in payload:
            raise ValueError("Missing G-code operation metadata")
        operations: list[tuple[int, str]] = []
        previous_line = 0
        for item in payload["operations"]:
            if not isinstance(item, dict):
                raise ValueError("Invalid G-code operation marker")
            line = int(item["line"])
            operation_id = str(item["id"])
            if (
                line <= previous_line
                or line < 1
                or line > line_count
                or re.fullmatch(r"op\d{1,6}", operation_id) is None
            ):
                raise ValueError("Invalid G-code operation marker")
            operations.append((line, operation_id))
            previous_line = line
        return operations

    def _raise_if_cancelled(self) -> None:
        if self._cancel_check is not None and self._cancel_check():
            raise GCodeSourceIndexCancelled("G-code source indexing cancelled")

    def _report_progress(self, fraction: float) -> None:
        if self._progress_callback is not None:
            self._progress_callback(max(0.0, min(1.0, float(fraction))), "source_index")

    def _write_cache(
        self,
        offsets_path: Path,
        metadata_path: Path,
        offsets: np.ndarray,
        markers: Iterable[tuple[int, int]],
        operations: Iterable[tuple[int, str]],
    ) -> None:
        self._raise_if_cancelled()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        temp_offsets: Path | None = None
        temp_metadata: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self._cache_dir, suffix=".npy", delete=False
            ) as stream:
                temp_offsets = Path(stream.name)
                np.save(stream, offsets, allow_pickle=False)
            self._raise_if_cancelled()
            metadata = {
                "markers": [{"line": line, "ordinal": ordinal} for line, ordinal in markers],
                "operations": [{"line": line, "id": op_id} for line, op_id in operations],
            }
            with tempfile.NamedTemporaryFile(
                dir=self._cache_dir,
                suffix=".json",
                mode="w",
                encoding="utf-8",
                delete=False,
            ) as stream:
                temp_metadata = Path(stream.name)
                json.dump(metadata, stream, ensure_ascii=False)
            self._raise_if_cancelled()
            os.replace(temp_offsets, offsets_path)
            temp_offsets = None
            self._raise_if_cancelled()
            os.replace(temp_metadata, metadata_path)
            temp_metadata = None
        finally:
            if temp_offsets is not None:
                try:
                    temp_offsets.unlink(missing_ok=True)
                except OSError:
                    pass
            if temp_metadata is not None:
                try:
                    temp_metadata.unlink(missing_ok=True)
                except OSError:
                    pass

    def _build_stages(
        self,
        marker_rows: list[tuple[int, int]],
        operation_rows: list[tuple[int, str]],
    ) -> list[GCodeStage]:
        if not marker_rows and operation_rows:
            stages: list[GCodeStage] = []
            occurrences: dict[str, int] = {}
            for index, (line, operation_id) in enumerate(operation_rows):
                occurrences[operation_id] = occurrences.get(operation_id, 0) + 1
                occurrence = occurrences[operation_id]
                stage_id = operation_id if occurrence == 1 else f"{operation_id}_{occurrence}"
                start = 1 if index == 0 else line
                end = (
                    operation_rows[index + 1][0] - 1
                    if index + 1 < len(operation_rows)
                    else self.line_count
                )
                stages.append(
                    GCodeStage(stage_id, "operation", int(operation_id[2:]), start, end)
                )
            return stages
        if not marker_rows:
            return [GCodeStage("all", "all", None, 1, max(1, self.line_count))]
        stages: list[GCodeStage] = []
        first_marker_line = marker_rows[0][0]
        if first_marker_line > 1:
            stages.append(GCodeStage("base", "base", None, 1, first_marker_line - 1))
        for index, (line, ordinal) in enumerate(marker_rows):
            end = marker_rows[index + 1][0] - 1 if index + 1 < len(marker_rows) else self.line_count
            stages.append(GCodeStage(f"blade_{ordinal}", "blade", ordinal, line, end))
        return stages


__all__ = [
    "GCodeSourceIndex",
    "GCodeSourceIndexCancelled",
    "GCodeStage",
    "application_cache_dir",
]
