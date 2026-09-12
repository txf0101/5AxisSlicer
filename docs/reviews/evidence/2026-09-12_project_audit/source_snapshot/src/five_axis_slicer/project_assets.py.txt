"""Verification and loading of project-local STEP and G-code assets.

The manifest reader supplies its module-level loader functions.  That keeps
asset verification deterministic while preserving the public fault-injection
boundary used by persistence tests.
"""

from __future__ import annotations

import hmac
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .gcode_preview import (
    GCodeLoadCancelled,
    GCodePreview,
    GCodeSourceFingerprint,
    GCodeSourceIntegrityError,
)
from .models import CadModel
from .project_contract import (
    ProjectFormatError,
    ProjectIntegrityError,
    ProjectLoadCancelled,
)
from .step_loader import StepLoadCancelled, StepLoadError

CancelCheck = Callable[[], bool]
ProgressCallback = Callable[[str, float], None]
HashFile = Callable[..., str]
StepLoader = Callable[..., CadModel]
GCodeLoader = Callable[..., GCodePreview]


@dataclass(frozen=True, slots=True)
class _EmbeddedStepSpec:
    path: Path
    sha256: str
    model_payload: Any
    persisted_units: Mapping[str, Any] | None
    length_unit_override: str | None


@dataclass(frozen=True, slots=True)
class _EmbeddedGcodeSpec:
    path: Path
    sha256: str
    fingerprint: GCodeSourceFingerprint | None
    controller_semantics: str | None


def load_embedded_model(
    project_dir: Path,
    payload: Mapping[str, Any],
    *,
    length_unit_override: str | None,
    cancel_check: CancelCheck | None,
    progress_callback: ProgressCallback | None,
    verify_topology: bool,
    hash_file: HashFile,
    step_loader: StepLoader,
) -> CadModel | None:
    _check_cancelled(cancel_check)
    spec = _embedded_step_spec(project_dir, payload, length_unit_override)
    if spec is None:
        return None
    _report(progress_callback, "project_source_hash", 0.12)
    _verify_file_hash(spec, cancel_check, hash_file)
    _check_cancelled(cancel_check)
    _report(progress_callback, "project_step", 0.20)
    model = _load_project_step(spec, cancel_check, step_loader)
    _check_cancelled(cancel_check)
    _report(progress_callback, "project_step", 0.82)
    _verify_loaded_step(model, spec, verify_topology)
    return model


def _embedded_step_spec(
    project_dir: Path,
    payload: Mapping[str, Any],
    length_unit_override: str | None,
) -> _EmbeddedStepSpec | None:
    source = payload.get("source")
    model_payload = payload.get("model")
    if source is None:
        if model_payload is not None:
            raise ProjectFormatError("model metadata exists without an embedded source")
        return None
    if not isinstance(source, Mapping):
        raise ProjectFormatError("source must be an object or null")
    expected_hash = source.get("sha256")
    if not isinstance(expected_hash, str) or not valid_sha256(expected_hash.lower()):
        raise ProjectFormatError("source.sha256 must be a SHA-256 value")
    persisted_units = _persisted_units(model_payload)
    return _EmbeddedStepSpec(
        path=safe_project_file(project_dir, source.get("project_path"), "source"),
        sha256=expected_hash.lower(),
        model_payload=model_payload,
        persisted_units=persisted_units,
        length_unit_override=_saved_unit_override(
            persisted_units,
            length_unit_override,
        ),
    )


def _persisted_units(model_payload: Any) -> Mapping[str, Any] | None:
    if not isinstance(model_payload, Mapping):
        return None
    units = model_payload.get("units")
    return units if isinstance(units, Mapping) else None


def _saved_unit_override(
    persisted_units: Mapping[str, Any] | None,
    requested: str | None,
) -> str | None:
    if persisted_units is None:
        return requested
    override_applied = persisted_units.get("override_applied", False)
    if not isinstance(override_applied, bool):
        raise ProjectFormatError("model.units.override_applied must be a boolean")
    if requested is not None:
        return requested
    stored = persisted_units.get("source_length_unit")
    if override_applied and isinstance(stored, str) and stored.strip():
        return stored
    return None


def _verify_file_hash(
    spec: _EmbeddedStepSpec,
    cancel_check: CancelCheck | None,
    hash_file: HashFile,
) -> None:
    actual_hash = hash_file(spec.path, cancel_check=cancel_check)
    if not hmac.compare_digest(actual_hash, spec.sha256):
        raise ProjectIntegrityError(
            f"embedded STEP hash mismatch: expected {spec.sha256}, calculated {actual_hash}"
        )


def _load_project_step(
    spec: _EmbeddedStepSpec,
    cancel_check: CancelCheck | None,
    step_loader: StepLoader,
) -> CadModel:
    try:
        return step_loader(
            spec.path,
            length_unit_override=spec.length_unit_override,
            cancel_check=cancel_check,
        )
    except StepLoadCancelled as exc:
        raise ProjectLoadCancelled("project STEP loading cancelled") from exc
    except StepLoadError as exc:
        raise ProjectIntegrityError(f"embedded STEP cannot be loaded: {spec.path}") from exc


def _verify_loaded_step(
    model: CadModel,
    spec: _EmbeddedStepSpec,
    verify_topology: bool,
) -> None:
    if not hmac.compare_digest(model.source_hash, spec.sha256):
        raise ProjectIntegrityError("embedded STEP changed during project loading")
    if spec.persisted_units is not None:
        saved_scale = spec.persisted_units.get("scale_to_mm")
        if isinstance(saved_scale, int | float) and not math.isclose(
            model.units.scale_to_mm,
            float(saved_scale),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ProjectIntegrityError("embedded STEP unit conversion differs from the project")
    if verify_topology:
        verify_persisted_topology(spec.model_payload, model)


def verify_persisted_topology(model_payload: Any, model: CadModel) -> None:
    """Verify that saved stable IDs and signatures describe the embedded STEP."""

    if not isinstance(model_payload, Mapping):
        raise ProjectFormatError("schema-v2 source requires persisted model topology metadata")
    specifications = (
        ("bodies", "body_count", model.bodies, "body_id"),
        ("faces", "face_count", model.faces, "face_id"),
        ("edges", "edge_count", model.edges, "edge_id"),
        ("vertices", "vertex_count", model.vertices, "vertex_id"),
    )
    for collection, count_field, actual_items, identifier_attribute in specifications:
        _verify_topology_collection(
            model_payload,
            collection,
            count_field,
            actual_items,
            identifier_attribute,
        )


def _verify_topology_collection(
    model_payload: Mapping[str, Any],
    collection: str,
    count_field: str,
    actual_items: Sequence[Any],
    identifier_attribute: str,
) -> None:
    persisted_count = model_payload.get(count_field)
    if (
        isinstance(persisted_count, bool)
        or not isinstance(persisted_count, int)
        or persisted_count < 0
    ):
        raise ProjectFormatError(f"model.{count_field} must be a non-negative integer")
    persisted_items = model_payload.get(collection)
    if not isinstance(persisted_items, list):
        raise ProjectFormatError(f"model.{collection} must be an array")
    if persisted_count != len(persisted_items):
        raise ProjectIntegrityError(
            f"persisted {collection} count does not match its topology array"
        )
    if persisted_count != len(actual_items):
        raise ProjectIntegrityError(f"persisted {collection} count differs from embedded STEP")
    persisted = _persisted_topology_signatures(persisted_items, collection)
    actual = _actual_topology_signatures(
        actual_items,
        collection,
        identifier_attribute,
    )
    if persisted == actual:
        return
    detail = "IDs" if persisted.keys() != actual.keys() else "signatures"
    raise ProjectIntegrityError(f"persisted {collection} {detail} differ from embedded STEP")


def _persisted_topology_signatures(
    items: Sequence[Any],
    collection: str,
) -> dict[str, str]:
    signatures: dict[str, str] = {}
    for index, item in enumerate(items):
        path = f"model.{collection}[{index}]"
        if not isinstance(item, Mapping):
            raise ProjectFormatError(f"{path} must be an object")
        identifier = item.get("id")
        signature = item.get("signature")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ProjectFormatError(f"{path}.id must be a non-empty string")
        if not isinstance(signature, str) or not valid_sha256(signature):
            raise ProjectFormatError(f"{path}.signature must be a SHA-256 value")
        if identifier in signatures:
            raise ProjectFormatError(f"model.{collection} contains duplicate ID {identifier!r}")
        signatures[identifier] = signature
    return signatures


def _actual_topology_signatures(
    items: Sequence[Any],
    collection: str,
    identifier_attribute: str,
) -> dict[str, str]:
    signatures: dict[str, str] = {}
    for item in items:
        identifier = getattr(item, identifier_attribute, None)
        signature = getattr(item, "signature", None)
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or not isinstance(signature, str)
            or not valid_sha256(signature)
            or identifier in signatures
        ):
            raise ProjectIntegrityError(
                f"embedded STEP produced invalid {collection} identity metadata"
            )
        signatures[identifier] = signature
    return signatures


def verify_optional_project_files(
    project_dir: Path,
    payload: Mapping[str, Any],
    *,
    cancel_check: CancelCheck | None,
) -> None:
    _check_cancelled(cancel_check)
    preview = payload.get("preview")
    if isinstance(preview, Mapping) and preview.get("glb") is not None:
        safe_project_file(project_dir, preview.get("glb"), "preview.glb")
    _check_cancelled(cancel_check)


def load_embedded_gcode(
    project_dir: Path,
    payload: Mapping[str, Any],
    *,
    cancel_check: CancelCheck | None,
    progress_callback: ProgressCallback | None,
    gcode_loader: GCodeLoader,
) -> GCodePreview | None:
    _check_cancelled(cancel_check)
    spec = _embedded_gcode_spec(project_dir, payload)
    if spec is None:
        return None
    _report(progress_callback, "project_gcode_hash", 0.83)

    def report_gcode(fraction: float, phase: str = "gcode") -> None:
        mapped = 0.83 + max(0.0, min(1.0, float(fraction))) * 0.04
        _report(progress_callback, f"project_gcode_{phase}", mapped)

    preview = _parse_project_gcode(spec, cancel_check, report_gcode, gcode_loader)
    _check_cancelled(cancel_check)
    _verify_loaded_gcode_fingerprint(preview, spec.fingerprint)
    return preview


def _embedded_gcode_spec(
    project_dir: Path,
    payload: Mapping[str, Any],
) -> _EmbeddedGcodeSpec | None:
    gcode = payload.get("gcode")
    if gcode is None:
        return None
    if not isinstance(gcode, Mapping):
        raise ProjectFormatError("gcode must be an object or null")
    project_path = gcode.get("project_path")
    if project_path is None:
        return None
    expected_hash = gcode.get("sha256")
    if not isinstance(expected_hash, str) or not valid_sha256(expected_hash.lower()):
        raise ProjectFormatError("gcode.sha256 must be a SHA-256 value")
    expected_hash = expected_hash.lower()
    return _EmbeddedGcodeSpec(
        path=safe_project_file(project_dir, project_path, "gcode"),
        sha256=expected_hash,
        fingerprint=_manifest_gcode_fingerprint(
            gcode.get("source_fingerprint"),
            expected_hash,
        ),
        controller_semantics=_controller_semantics(gcode.get("summary", {})),
    )


def _manifest_gcode_fingerprint(
    value: Any,
    expected_hash: str,
) -> GCodeSourceFingerprint | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ProjectFormatError("gcode.source_fingerprint must be an object")
    try:
        fingerprint = GCodeSourceFingerprint.from_json(value)
    except (TypeError, ValueError) as exc:
        raise ProjectFormatError("gcode.source_fingerprint is invalid") from exc
    if not hmac.compare_digest(fingerprint.sha256, expected_hash):
        raise ProjectIntegrityError("G-code manifest fingerprint diverges from gcode.sha256")
    return fingerprint


def _controller_semantics(summary: Any) -> str | None:
    if not isinstance(summary, Mapping):
        raise ProjectFormatError("gcode.summary must be an object")
    value = summary.get("controller_semantics")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProjectFormatError(
            "gcode.summary.controller_semantics must be a non-empty string or null"
        )
    return value


def _parse_project_gcode(
    spec: _EmbeddedGcodeSpec,
    cancel_check: CancelCheck | None,
    progress_callback: Callable[..., None],
    gcode_loader: GCodeLoader,
) -> GCodePreview:
    try:
        return gcode_loader(
            spec.path,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
            source_sha256=spec.sha256,
            controller_semantics=spec.controller_semantics,
        )
    except GCodeLoadCancelled as exc:
        raise ProjectLoadCancelled("project G-code loading cancelled") from exc
    except GCodeSourceIntegrityError as exc:
        raise ProjectIntegrityError("embedded G-code hash mismatch") from exc
    except (OSError, UnicodeError, ValueError) as exc:
        raise ProjectIntegrityError(f"embedded G-code cannot be loaded: {spec.path}") from exc


def _verify_loaded_gcode_fingerprint(
    preview: GCodePreview,
    manifest_fingerprint: GCodeSourceFingerprint | None,
) -> None:
    loaded = preview.source_fingerprint
    if not isinstance(loaded, GCodeSourceFingerprint):
        raise ProjectIntegrityError("loaded G-code has no verified source fingerprint")
    if manifest_fingerprint is None:
        return
    if not hmac.compare_digest(loaded.sha256, manifest_fingerprint.sha256):
        raise ProjectIntegrityError("embedded G-code fingerprint mismatch")
    if loaded.size_bytes != manifest_fingerprint.size_bytes:
        raise ProjectIntegrityError("embedded G-code fingerprint mismatch")


def safe_project_file(project_dir: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProjectFormatError(f"{field}.project_path must be a relative path")
    relative = Path(value)
    if relative.is_absolute() or relative.drive or relative.root:
        raise ProjectIntegrityError(f"{field} path must stay inside the project")
    candidate = (project_dir / relative).resolve()
    try:
        candidate.relative_to(project_dir)
    except ValueError as exc:
        raise ProjectIntegrityError(f"{field} path escapes the project directory") from exc
    if not candidate.is_file():
        raise ProjectIntegrityError(f"embedded {field} file does not exist: {value}")
    return candidate


def valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _check_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise ProjectLoadCancelled("project loading cancelled")


def _report(
    callback: ProgressCallback | None,
    phase: str,
    fraction: float,
) -> None:
    if callback is not None:
        callback(phase, max(0.0, min(1.0, float(fraction))))


__all__ = [
    "load_embedded_gcode",
    "load_embedded_model",
    "safe_project_file",
    "valid_sha256",
    "verify_optional_project_files",
    "verify_persisted_topology",
]
