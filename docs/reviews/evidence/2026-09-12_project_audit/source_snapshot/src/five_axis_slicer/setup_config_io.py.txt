"""Bounded file I/O for the portable Manufacturing Setup codec.

The codec validates values; this module owns regular-file checks, exact byte
fingerprints, and compare-before-replace publication. A completed replacement
is treated as committed even when the later directory durability sync fails.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import stat
import tempfile
from pathlib import Path

from .project_storage import assert_real_directory, is_link_or_reparse
from .setup_config import (
    MAX_CONFIG_BYTES,
    SetupConfig,
    SetupConfigConflictError,
    SetupConfigError,
    _decode_yaml_text,
    load_setup_config,
)

LOGGER = logging.getLogger(__name__)


def load_setup_config_file(path: str | Path) -> SetupConfig:
    return load_setup_config(_read_config_bytes(Path(path)))


def read_setup_config_snapshot(path: str | Path) -> tuple[SetupConfig, str, str]:
    """Return config, text, and SHA-256 from one bounded descriptor read."""

    data = _read_config_bytes(Path(path))
    return load_setup_config(data), data.decode("utf-8"), _sha256(data)


def setup_config_fingerprint(path: str | Path) -> str | None:
    """Return the exact-byte SHA-256 used by compare-before-replace writes."""

    source = Path(path)
    if is_link_or_reparse(source):
        raise SetupConfigError("configuration target must not be a link", code="E_CONFIG_IO")
    if not source.exists():
        return None
    return _sha256(_read_config_bytes(source))


def atomic_write_setup_config(
    destination: str | Path,
    text: str | bytes,
    *,
    expected_fingerprint: str | None = None,
    expect_missing: bool = False,
) -> str:
    """Validate and atomically replace one YAML work file."""

    _validate_write_expectation(expected_fingerprint, expect_missing)
    decoded = _decode_yaml_text(text)
    config = load_setup_config(decoded)
    if not config.content_matches_metadata:
        raise SetupConfigError("metadata content_sha256 does not match portable state")
    normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    encoded = (normalized if normalized.endswith("\n") else normalized + "\n").encode("utf-8")
    destination_path = Path(os.path.abspath(destination))
    _publish_bytes(destination_path, encoded, expected_fingerprint, expect_missing)
    return _sha256(encoded)


def _publish_bytes(
    destination: Path,
    data: bytes,
    expected_fingerprint: str | None,
    expect_missing: bool,
) -> None:
    try:
        assert_real_directory(
            destination.parent,
            context="configuration parent must be a real directory",
        )
        if is_link_or_reparse(destination):
            raise SetupConfigError("configuration target must not be a link", code="E_CONFIG_IO")
        _check_fingerprint(destination, expected_fingerprint, expect_missing)
        descriptor, name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(name)
        published = False
        try:
            _write_staged(descriptor, data)
            _check_fingerprint(destination, expected_fingerprint, expect_missing)
            assert_real_directory(
                destination.parent,
                context="configuration parent changed before publication",
            )
            if is_link_or_reparse(destination):
                raise SetupConfigError(
                    "configuration target changed to a link",
                    code="E_CONFIG_IO",
                )
            os.replace(temporary, destination)
            published = True
            _sync_directory_best_effort(destination)
        finally:
            if not published:
                _remove_staged_best_effort(temporary)
    except SetupConfigError:
        raise
    except OSError as exc:
        raise SetupConfigError(f"cannot publish configuration: {exc}", code="E_CONFIG_IO") from exc


def _write_staged(descriptor: int, data: bytes) -> None:
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _check_fingerprint(path: Path, expected: str | None, expect_missing: bool) -> None:
    actual = setup_config_fingerprint(path)
    if expect_missing:
        if actual is not None:
            raise SetupConfigConflictError("configuration was created by another writer")
        return
    if expected is not None and (actual is None or not hmac.compare_digest(actual, expected)):
        raise SetupConfigConflictError("configuration changed since it was read")


def _validate_write_expectation(expected: str | None, expect_missing: bool) -> None:
    if expected is not None and (
        len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected)
    ):
        raise SetupConfigError("expected fingerprint must be lowercase SHA-256")
    if type(expect_missing) is not bool or (expect_missing and expected is not None):
        raise SetupConfigError("expect_missing is boolean and cannot accompany a fingerprint")


def _read_config_bytes(source: Path) -> bytes:
    if is_link_or_reparse(source):
        raise SetupConfigError("configuration path must not be a link", code="E_CONFIG_IO")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise SetupConfigError(
                    "configuration path must be a regular file",
                    code="E_CONFIG_IO",
                )
            if opened.st_size > MAX_CONFIG_BYTES:
                raise SetupConfigError("configuration exceeds 2 MiB")
            data = stream.read(MAX_CONFIG_BYTES + 1)
            completed = os.fstat(stream.fileno())
    except SetupConfigError:
        raise
    except OSError as exc:
        raise SetupConfigError(f"cannot read configuration: {exc}", code="E_CONFIG_IO") from exc
    if is_link_or_reparse(source):
        raise SetupConfigError("configuration path changed to a link", code="E_CONFIG_IO")
    try:
        current = os.stat(source, follow_symlinks=False)
    except OSError as exc:
        raise SetupConfigConflictError("configuration changed while being read") from exc
    if not os.path.samestat(opened, completed) or not os.path.samestat(opened, current):
        raise SetupConfigConflictError("configuration changed while being read")
    if (opened.st_size, opened.st_mtime_ns) != (completed.st_size, completed.st_mtime_ns):
        raise SetupConfigConflictError("configuration changed while being read")
    if len(data) > MAX_CONFIG_BYTES:
        raise SetupConfigError("configuration exceeds 2 MiB")
    return data


def _sync_directory_best_effort(destination: Path) -> None:
    try:
        _sync_directory(destination.parent)
    except OSError:
        LOGGER.warning(
            "configuration replaced but directory fsync failed: %s",
            destination,
            exc_info=True,
        )


def _remove_staged_best_effort(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        LOGGER.warning("cannot remove staged configuration: %s", path, exc_info=True)


def _sync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


__all__ = [
    "atomic_write_setup_config",
    "load_setup_config_file",
    "read_setup_config_snapshot",
    "setup_config_fingerprint",
]
