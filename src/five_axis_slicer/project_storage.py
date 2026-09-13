"""Low-level project path and atomic publication safeguards.

This module owns filesystem checks only; project schema and CAD semantics stay
in ``project_io``. Callers provide the content hash function so source-race
tests exercise the same authority used by the project transaction.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import stat
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class StorageIntegrityError(RuntimeError):
    """A path or staged file left the controlled storage boundary."""


HashFile = Callable[[Path], str]
CopyFile = Callable[..., Any]


def is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction) and bool(is_junction()):
        return True
    try:
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0))
    except FileNotFoundError:
        return False
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return bool(reparse_flag and attributes & reparse_flag)


def assert_real_directory(path: Path, *, context: str) -> None:
    absolute = Path(os.path.abspath(path))
    if is_link_or_reparse(absolute) or not absolute.is_dir():
        raise StorageIntegrityError(context)


def prepare_subdirectory(project_dir: Path, directory: Path, name: str) -> None:
    assert_real_directory(
        project_dir,
        context="project directory changed to a link or reparse point",
    )
    if directory.parent != project_dir:
        raise StorageIntegrityError(f"project {name}/ path escapes the project")
    if is_link_or_reparse(directory):
        raise StorageIntegrityError(
            f"project {name}/ directory must not be a link or reparse point"
        )
    if directory.exists() and not directory.is_dir():
        raise StorageIntegrityError(f"project {name}/ path must be a directory")
    directory.mkdir(parents=False, exist_ok=True)
    assert_real_directory(
        directory,
        context=f"project {name}/ directory must remain inside the project",
    )
    try:
        directory.resolve().relative_to(project_dir)
    except ValueError as exc:
        raise StorageIntegrityError(f"project {name}/ directory escapes the project") from exc


def assert_safe_publish_target(destination: Path, allowed_parent: Path, name: str) -> None:
    absolute = Path(os.path.abspath(destination))
    try:
        absolute.parent.relative_to(allowed_parent)
    except ValueError as exc:
        raise StorageIntegrityError(f"{name} target escapes the project") from exc
    assert_real_directory(
        absolute.parent,
        context=f"{name} parent must remain a controlled real directory",
    )
    if is_link_or_reparse(absolute):
        raise StorageIntegrityError(f"{name} target must not be a link or reparse point")


@contextmanager
def project_save_lock(project_dir: Path, timeout_seconds: float = 2.0):
    """Serialize writers to one project directory across processes."""

    assert_real_directory(
        project_dir,
        context="project directory must remain a controlled real directory",
    )
    lock_path = project_dir / ".project-save.lock"
    if is_link_or_reparse(lock_path):
        raise StorageIntegrityError("project save lock must be a regular file")
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    with lock_path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
            os.fsync(stream.fileno())
        while True:
            try:
                _lock_stream(stream)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise StorageIntegrityError(
                        "project is already being saved by another process"
                    ) from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            _unlock_stream(stream)


def atomic_copy(
    source: Path,
    destination: Path,
    *,
    hash_file: HashFile,
    expected_sha256: str | None = None,
    copy_file: CopyFile = shutil.copy2,
) -> None:
    """Publish staged bytes only after their content address is verified."""

    source = source.resolve()
    destination = Path(os.path.abspath(destination))
    if expected_sha256 is not None and not _valid_sha256(expected_sha256):
        raise StorageIntegrityError("copy digest must be a SHA-256 value")
    assert_real_directory(
        destination.parent,
        context="copy destination parent must remain a controlled real directory",
    )
    if is_link_or_reparse(destination):
        raise StorageIntegrityError("copy destination must not be a link or reparse point")
    if destination.exists() and source == destination.resolve():
        _verify_digest(source, expected_sha256, hash_file, "content-addressed source")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    assert_real_directory(
        destination.parent,
        context="copy destination parent must remain a controlled real directory",
    )
    if _matches_existing_copy(destination, expected_sha256, hash_file):
        return
    _publish_copy(source, destination, expected_sha256, hash_file, copy_file)


def _matches_existing_copy(
    destination: Path,
    expected_sha256: str | None,
    hash_file: HashFile,
) -> bool:
    if expected_sha256 is None or not destination.is_file():
        return False
    try:
        _verify_digest(
            destination,
            expected_sha256,
            hash_file,
            "existing content-addressed copy",
        )
    except (FileNotFoundError, StorageIntegrityError):
        return False
    return True


def _publish_copy(
    source: Path,
    destination: Path,
    expected_sha256: str | None,
    hash_file: HashFile,
    copy_file: CopyFile,
) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        copy_file(source, temporary)
        _verify_digest(
            temporary,
            expected_sha256,
            hash_file,
            "staged content-addressed copy",
        )
        assert_real_directory(
            destination.parent,
            context="copy destination parent changed to a link or reparse point",
        )
        if is_link_or_reparse(destination):
            raise StorageIntegrityError("copy destination changed to a link or reparse point")
        os.replace(temporary, destination)
        _sync_directory(destination.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(destination: Path, payload: Mapping[str, Any]) -> None:
    """Fsync a temporary manifest, replace the target, then sync its directory."""

    destination = Path(os.path.abspath(destination))
    assert_real_directory(
        destination.parent,
        context="project manifest parent must remain a controlled real directory",
    )
    if is_link_or_reparse(destination):
        raise StorageIntegrityError("project manifest must not be a link or reparse point")
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        assert_real_directory(
            destination.parent,
            context="project manifest parent changed to a link or reparse point",
        )
        if is_link_or_reparse(destination):
            raise StorageIntegrityError("project manifest changed to a link or reparse point")
        os.replace(temporary, destination)
        _sync_directory(destination.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _verify_digest(
    path: Path,
    expected: str | None,
    hash_file: HashFile,
    context: str,
) -> None:
    if expected is None:
        return
    before = path.stat()
    actual = hash_file(path)
    after = path.stat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or actual.lower() != expected.lower()
    ):
        raise StorageIntegrityError(f"{context} verification failed")


def _sync_directory(directory: Path) -> None:
    """Persist rename metadata where the platform supports directory fsync."""

    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _lock_stream(stream: Any) -> None:
    stream.seek(0)
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        return
    fcntl = importlib.import_module("fcntl")
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_stream(stream: Any) -> None:
    stream.seek(0)
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return
    fcntl = importlib.import_module("fcntl")
    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _valid_sha256(value: str) -> bool:
    digest = str(value).lower()
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


__all__ = [
    "StorageIntegrityError",
    "assert_real_directory",
    "assert_safe_publish_target",
    "atomic_copy",
    "atomic_write_json",
    "is_link_or_reparse",
    "prepare_subdirectory",
    "project_save_lock",
]
