from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hmac
import json
import math
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence

from .gcode_preview import (
    GCodeLoadCancelled,
    GCodePreview,
    GCodeSourceFingerprint,
    GCodeSourceIntegrityError,
    PreviewSettings,
    load_gcode,
)
from .models import CadModel, SelectionState
from .step_loader import StepLoadCancelled, StepLoadError, file_sha256, load_step


PROJECT_VERSION = 2
PROJECT_FILE_NAME = "project.json"
V1_BACKUP_FILE_NAME = "project.v1.json"
_SHA256_LENGTH = 64


class ProjectError(RuntimeError):
    """Base class for project persistence failures."""


class ProjectFormatError(ProjectError):
    """The project JSON structure or a persisted domain object is invalid."""


class ProjectIntegrityError(ProjectError):
    """An embedded file or immutable resource differs from its saved hash."""


class UnsupportedProjectVersionError(ProjectFormatError):
    """The project was written by a newer unsupported schema."""


class ProjectLoadCancelled(ProjectError):
    """A cooperative project verification or embedded STEP load was cancelled."""


SetupLoader = Callable[[Mapping[str, Any]], Any]
OperationLoader = Callable[[Mapping[str, Any]], Any]
CancelCheck = Callable[[], bool]
ProgressCallback = Callable[[str, float], None]


@dataclass(frozen=True, slots=True)
class ProjectLoaded:
    """A fully verified project reconstructed from its embedded source."""

    project_directory: Path
    project_json: Path
    model: CadModel | None
    selection: SelectionState
    workbench: dict[str, Any]
    setups: tuple[Any, ...]
    operations: tuple[Any, ...]
    resources: Any
    migrated_from_v1: bool
    payload: dict[str, Any]
    gcode_preview: GCodePreview | None = None

    @property
    def setup(self) -> Any | None:
        return self.setups[0] if self.setups else None

    @property
    def workbench_state(self) -> dict[str, Any]:
        return self.workbench

    @property
    def migration_required(self) -> bool:
        return self.migrated_from_v1


def save_project(
    directory: str | Path,
    model: CadModel | None,
    selection: SelectionState,
    workbench_state: dict[str, Any] | None = None,
    gcode_preview: GCodePreview | None = None,
    preview_settings: PreviewSettings | None = None,
    result_preview_state: Any | None = None,
    *,
    setup: Any | None = None,
    setups: Iterable[Any] | Any | None = None,
    operations: Iterable[Any] | Any | None = None,
    resources: Any | None = None,
    original_source_path: str | Path | None = None,
) -> Path:
    """Save a schema-v2 project while retaining the original positional API.

    The STEP copy under ``source/`` is authoritative for subsequent opens.
    Domain values may be dataclasses exposing ``to_json`` or plain
    JSON-compatible mappings, which keeps this persistence boundary usable by
    workbenches introduced after schema v2.
    """

    if not isinstance(selection, SelectionState):
        raise TypeError("selection must be a SelectionState")
    if setup is not None and setups is not None:
        raise ValueError("pass setup or setups, not both")

    requested_project_dir = Path(os.path.abspath(Path(directory).expanduser()))
    if _is_link_or_reparse(requested_project_dir):
        raise ProjectIntegrityError(
            "project directory must not be a link or reparse point"
        )
    requested_project_dir.mkdir(parents=True, exist_ok=True)
    if _is_link_or_reparse(requested_project_dir):
        raise ProjectIntegrityError(
            "project directory changed to a link or reparse point"
        )
    project_dir = requested_project_dir.resolve()
    _assert_real_directory(
        project_dir,
        context="project directory must remain a controlled real directory",
    )
    source_dir = project_dir / "source"
    preview_dir = project_dir / "preview"
    _prepare_project_subdirectory(project_dir, source_dir, "source")
    _prepare_project_subdirectory(project_dir, preview_dir, "preview")
    output = project_dir / PROJECT_FILE_NAME
    _assert_safe_publish_target(output, project_dir, "project.json")

    previous_payload = _read_existing_for_save(output)
    created_at = _existing_created_at(previous_payload) or _utc_now()

    source_payload: dict[str, Any] | None = None
    model_payload: dict[str, Any] | None = None
    if model is not None:
        source_path = Path(model.source_path).expanduser().resolve()
        if not source_path.is_file():
            raise ProjectIntegrityError(f"STEP source does not exist: {source_path}")
        actual_hash = file_sha256(source_path)
        expected_hash = str(model.source_hash).lower()
        if not _valid_sha256(expected_hash):
            raise ProjectIntegrityError("CAD model has an invalid source hash")
        if not hmac.compare_digest(actual_hash, expected_hash):
            raise ProjectIntegrityError("STEP source changed after it was loaded")
        source_copy = _content_addressed_path(
            source_dir,
            source_path,
            actual_hash,
        )
        _atomic_copy(
            source_path,
            source_copy,
            expected_sha256=actual_hash,
        )
        final_source_hash = file_sha256(source_path)
        if not hmac.compare_digest(final_source_hash, expected_hash):
            raise ProjectIntegrityError("STEP source changed while saving")
        copied_hash = file_sha256(source_copy)
        if not hmac.compare_digest(copied_hash, actual_hash):
            raise ProjectIntegrityError("embedded STEP verification failed after copy")
        source_payload = {
            # The embedded copy remains authoritative for project reopen.  This
            # provenance path is consulted only after an explicit user request
            # to update the model from its external source.
            "original_path": str(
                source_path
                if original_source_path is None
                else Path(original_source_path).expanduser().resolve()
            ),
            "project_path": (Path("source") / source_copy.name).as_posix(),
            "sha256": copied_hash,
        }
        model_payload = _model_payload(model)
        _verify_persisted_topology(model_payload, model)

    gcode_payload: dict[str, Any] | None = None
    if gcode_preview is not None:
        gcode_source = Path(gcode_preview.source_path).expanduser().resolve()
        source_fingerprint = gcode_preview.source_fingerprint
        project_path: str | None = None
        source_hash: str | None = None
        embedded_fingerprint: GCodeSourceFingerprint | None = None
        if isinstance(source_fingerprint, GCodeSourceFingerprint) and not (
            gcode_source.is_file()
        ):
            raise ProjectIntegrityError(
                "verified G-code source no longer exists; reload it before saving"
            )
        if gcode_source.is_file():
            if not isinstance(source_fingerprint, GCodeSourceFingerprint):
                raise ProjectIntegrityError(
                    "G-code source fingerprint is missing; reload the source before saving"
                )
            _verify_gcode_source_fingerprint(
                gcode_source,
                source_fingerprint,
                context="G-code source changed after it was loaded",
            )
            gcode_copy = _content_addressed_path(
                source_dir,
                gcode_source,
                source_fingerprint.sha256,
            )
            _atomic_copy(
                gcode_source,
                gcode_copy,
                expected_sha256=source_fingerprint.sha256,
            )
            _verify_gcode_source_fingerprint(
                gcode_source,
                source_fingerprint,
                context="G-code source changed while saving",
            )
            embedded_fingerprint = _stable_file_fingerprint(
                gcode_copy,
                expected_sha256=source_fingerprint.sha256,
                context="embedded G-code verification failed after copy",
            )
            source_hash = embedded_fingerprint.sha256
            project_path = (Path("source") / gcode_copy.name).as_posix()
        gcode_payload = {
            "original_path": str(gcode_source),
            "project_path": project_path,
            "sha256": source_hash,
            "source_fingerprint": (
                None if embedded_fingerprint is None else embedded_fingerprint.to_json()
            ),
            "summary": _json_value(gcode_preview.summary(), path="gcode.summary"),
        }

    setup_values = (setup,) if setup is not None else _collection_values(setups)
    operation_values = _collection_values(operations)
    serialized_setups = [
        _json_value(value, path=f"setups[{index}]")
        for index, value in enumerate(setup_values)
    ]
    serialized_operations = [
        _json_value(value, path=f"operations[{index}]")
        for index, value in enumerate(operation_values)
    ]
    serialized_resources = _json_value(
        {} if resources is None else resources,
        path="resources",
    )
    _validate_no_persisted_setup_drafts(serialized_setups)
    _validate_setup_resource_mirror(serialized_setups, serialized_resources)

    payload: dict[str, Any] = {
        "version": PROJECT_VERSION,
        "created_at": created_at,
        "updated_at": _utc_now(),
        "workbench": _json_value(workbench_state or {}, path="workbench"),
        "source": source_payload,
        "gcode": gcode_payload,
        "model": model_payload,
        "selection": selection.to_json(),
        "setups": serialized_setups,
        "operations": serialized_operations,
        "resources": serialized_resources,
        # Retained for readers of the teaching-preview v1 format.
        "manufacturable_feature_groups": [],
        "preview": {
            "glb": None,
            "gcode": None if preview_settings is None else preview_settings.to_json(),
        },
    }
    if result_preview_state is not None:
        payload["result_preview"] = _json_value(
            result_preview_state,
            path="result_preview",
        )

    if previous_payload is not None and previous_payload.get("version") == 1:
        backup = project_dir / V1_BACKUP_FILE_NAME
        if not backup.exists():
            _atomic_copy(output, backup)

    _atomic_write_json(output, payload)
    return output


def load_project(
    path: str | Path,
    *,
    setup_loader: SetupLoader | None = None,
    operation_loader: OperationLoader | None = None,
    length_unit_override: str | None = None,
    cancel_check: CancelCheck | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ProjectLoaded:
    """Load and verify a v1 or v2 project without reading original paths."""

    _raise_if_load_cancelled(cancel_check)
    _report_load_progress(progress_callback, "project_metadata", 0.02)
    project_json = _resolve_project_json(path)
    raw_payload = _read_project_payload(project_json)
    _raise_if_load_cancelled(cancel_check)
    version = _project_version(raw_payload)
    if version > PROJECT_VERSION:
        raise UnsupportedProjectVersionError(
            f"project schema {version} is newer than supported schema {PROJECT_VERSION}"
        )
    if version < 1:
        raise UnsupportedProjectVersionError(f"unsupported project schema {version}")

    migrated_from_v1 = version == 1
    payload = _migrate_v1_payload(raw_payload) if migrated_from_v1 else raw_payload
    _validate_v2_root(payload)
    _validate_setup_resource_mirror(
        payload["setups"],
        payload["resources"],
    )
    project_dir = project_json.parent.resolve()
    _report_load_progress(progress_callback, "project_metadata", 0.08)

    model = _load_embedded_model(
        project_dir,
        payload,
        length_unit_override=length_unit_override,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
        verify_topology=not migrated_from_v1,
    )
    _raise_if_load_cancelled(cancel_check)
    gcode_preview = _load_embedded_gcode(
        project_dir,
        payload,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
    )
    _raise_if_load_cancelled(cancel_check)
    _verify_optional_project_files(
        project_dir,
        payload,
        cancel_check=cancel_check,
    )
    _report_load_progress(progress_callback, "project_domain", 0.88)

    try:
        _raise_if_load_cancelled(cancel_check)
        selection = SelectionState.from_json(payload.get("selection"))
        workbench_payload = payload.get("workbench", {})
        if not isinstance(workbench_payload, Mapping):
            raise ValueError("workbench must be an object")
        workbench = _json_clone(workbench_payload)

        setup_values = payload.get("setups", [])
        operation_values = payload.get("operations", [])
        if not isinstance(setup_values, list):
            raise ValueError("setups must be an array")
        if not isinstance(operation_values, list):
            raise ValueError("operations must be an array")
        resolved_setup_loader = setup_loader or _default_setup_loader
        resolved_operation_loader = operation_loader or _default_operation_loader
        loaded_setups = tuple(
            _load_domain_item(item, resolved_setup_loader, f"setups[{index}]")
            for index, item in enumerate(setup_values)
        )
        _raise_if_load_cancelled(cancel_check)
        loaded_operations = tuple(
            _load_domain_item(
                item,
                resolved_operation_loader,
                f"operations[{index}]",
            )
            for index, item in enumerate(operation_values)
        )
        _validate_unique_operation_ids(loaded_operations)
        resources = _load_resource_state(payload.get("resources", {}))
        _raise_if_load_cancelled(cancel_check)
    except Exception as exc:
        _raise_domain_load_error(exc)

    loaded = ProjectLoaded(
        project_directory=project_dir,
        project_json=project_json,
        model=model,
        selection=selection,
        workbench=workbench,
        setups=loaded_setups,
        operations=loaded_operations,
        resources=resources,
        migrated_from_v1=migrated_from_v1,
        payload=payload,
        gcode_preview=gcode_preview,
    )
    _report_load_progress(progress_callback, "project_ready", 1.0)
    return loaded


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _raise_if_load_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise ProjectLoadCancelled("project loading cancelled")


def _report_load_progress(
    callback: ProgressCallback | None,
    phase: str,
    fraction: float,
) -> None:
    if callback is not None:
        callback(str(phase), max(0.0, min(1.0, float(fraction))))


def _model_payload(model: CadModel) -> dict[str, Any]:
    return {
        "body_count": len(model.bodies),
        "face_count": len(model.faces),
        "edge_count": len(model.edges),
        "vertex_count": len(model.vertices),
        "units": model.units.to_json(),
        "bounds": None if model.bounds is None else model.bounds.to_json(),
        "bodies": [body.to_json() for body in model.bodies],
        "faces": [face.to_json() for face in model.faces],
        "edges": [edge.to_json() for edge in model.edges],
        "vertices": [vertex.to_json() for vertex in model.vertices],
    }


def _collection_values(value: Iterable[Any] | Any | None) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, bytearray, Mapping)) or hasattr(value, "to_json"):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _json_value(value: Any, *, path: str) -> Any:
    if hasattr(value, "to_json") and not isinstance(value, Mapping):
        value = value.to_json()
    elif isinstance(value, Enum):
        value = value.value
    elif isinstance(value, Path):
        value = str(value)

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return 0.0 if value == 0.0 else value
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} contains a non-string mapping key")
            output[key] = _json_value(item, path=f"{path}.{key}")
        return output
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{path} contains unsupported value type {type(value).__name__}")


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _read_existing_for_save(output: Path) -> dict[str, Any] | None:
    if not output.exists():
        return None
    payload = _read_project_payload(output)
    version = _project_version(payload)
    if version > PROJECT_VERSION:
        raise UnsupportedProjectVersionError(
            f"refusing to overwrite newer project schema {version}"
        )
    return payload


def _existing_created_at(payload: Mapping[str, Any] | None) -> str | None:
    if payload is None:
        return None
    value = payload.get("created_at")
    return value if isinstance(value, str) and value.strip() else None


def _read_project_payload(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectFormatError(f"cannot read project file: {path}") from exc
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProjectFormatError(f"invalid project JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ProjectFormatError("project root must be a JSON object")
    return payload


def _project_version(payload: Mapping[str, Any]) -> int:
    version = payload.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ProjectFormatError("project version must be an integer")
    return version


def _resolve_project_json(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_dir():
        candidate = candidate / PROJECT_FILE_NAME
    elif not candidate.exists() and candidate.suffix.lower() != ".json":
        candidate = candidate / PROJECT_FILE_NAME
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise ProjectFormatError(f"project file does not exist: {candidate}")
    return candidate


def _migrate_v1_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    migrated = _json_clone(payload)
    migrated["version"] = PROJECT_VERSION
    migrated.setdefault("updated_at", migrated.get("created_at", _utc_now()))
    from .manufacturing.setup import ManufacturingSetup

    migrated["setups"] = [ManufacturingSetup().to_json()]
    migrated["operations"] = []
    migrated["resources"] = {}
    return migrated


def _validate_v2_root(payload: Mapping[str, Any]) -> None:
    if payload.get("version") != PROJECT_VERSION:
        raise ProjectFormatError("project was not migrated to schema v2")
    for field_name in ("setups", "operations"):
        if not isinstance(payload.get(field_name), list):
            raise ProjectFormatError(f"{field_name} must be an array")
    if "resources" not in payload:
        raise ProjectFormatError("resources field is required")
    if not isinstance(payload.get("selection", {}), Mapping):
        raise ProjectFormatError("selection must be an object")
    _validate_no_persisted_setup_drafts(payload["setups"])


def _validate_no_persisted_setup_drafts(setups: Any) -> None:
    if not isinstance(setups, list):
        raise ProjectFormatError("setups must be an array")
    for index, setup in enumerate(setups):
        if not isinstance(setup, Mapping):
            continue
        draft_nodes = setup.get("draft_nodes", [])
        if not isinstance(draft_nodes, list):
            raise ProjectFormatError(f"setups[{index}].draft_nodes must be an array")
        if draft_nodes:
            raise ProjectFormatError(
                f"setups[{index}].draft_nodes must be empty before persistence"
            )


def _validate_setup_resource_mirror(setups: Any, resources: Any) -> None:
    """Reject conflicting copies of a selected Tube resource snapshot.

    A Manufacturing Setup owns the selected snapshots.  The project-level
    ``resources`` object remains a compatibility mirror for existing callers.
    Missing entries are accepted, while two present copies must be identical.
    Multiple setups are left to a future project-level resource registry.
    """

    if not isinstance(setups, list) or len(setups) != 1:
        return
    setup = setups[0]
    if not isinstance(setup, Mapping) or "setup_id" not in setup:
        return
    setup_resources = setup.get("resources")
    if not isinstance(setup_resources, Mapping) or not isinstance(resources, Mapping):
        return
    for resource_type in ("machine", "nozzle", "material"):
        setup_snapshot = setup_resources.get(resource_type)
        mirrored_snapshot = resources.get(resource_type)
        if setup_snapshot is None or mirrored_snapshot is None:
            continue
        if setup_snapshot != mirrored_snapshot:
            raise ProjectIntegrityError(
                f"top-level {resource_type} resource diverges from Setup snapshot"
            )


def _load_embedded_model(
    project_dir: Path,
    payload: Mapping[str, Any],
    *,
    length_unit_override: str | None,
    cancel_check: CancelCheck | None,
    progress_callback: ProgressCallback | None,
    verify_topology: bool,
) -> CadModel | None:
    _raise_if_load_cancelled(cancel_check)
    source = payload.get("source")
    model_payload = payload.get("model")
    if source is None:
        if model_payload is not None:
            raise ProjectFormatError("model metadata exists without an embedded source")
        return None
    if not isinstance(source, Mapping):
        raise ProjectFormatError("source must be an object or null")
    embedded = _safe_project_file(project_dir, source.get("project_path"), "source")
    expected_hash = source.get("sha256")
    if not isinstance(expected_hash, str) or not _valid_sha256(expected_hash.lower()):
        raise ProjectFormatError("source.sha256 must be a SHA-256 value")
    _report_load_progress(progress_callback, "project_source_hash", 0.12)
    actual_hash = file_sha256(embedded, cancel_check=cancel_check)
    if not hmac.compare_digest(actual_hash, expected_hash.lower()):
        raise ProjectIntegrityError(
            f"embedded STEP hash mismatch: expected {expected_hash.lower()}, "
            f"calculated {actual_hash}"
        )
    persisted_units: Mapping[str, Any] | None = None
    if isinstance(model_payload, Mapping) and isinstance(
        model_payload.get("units"), Mapping
    ):
        persisted_units = model_payload["units"]
    override_applied = False
    if persisted_units is not None:
        persisted_override = persisted_units.get("override_applied", False)
        if not isinstance(persisted_override, bool):
            raise ProjectFormatError("model.units.override_applied must be a boolean")
        override_applied = persisted_override
    effective_override = length_unit_override
    if effective_override is None and persisted_units is not None:
        if override_applied:
            stored_unit = persisted_units.get("source_length_unit")
            if isinstance(stored_unit, str) and stored_unit.strip():
                effective_override = stored_unit
    _raise_if_load_cancelled(cancel_check)
    _report_load_progress(progress_callback, "project_step", 0.20)
    try:
        model = load_step(
            embedded,
            length_unit_override=effective_override,
            cancel_check=cancel_check,
        )
    except StepLoadCancelled as exc:
        raise ProjectLoadCancelled("project STEP loading cancelled") from exc
    except StepLoadError as exc:
        raise ProjectIntegrityError(
            f"embedded STEP cannot be loaded: {embedded}"
        ) from exc
    _raise_if_load_cancelled(cancel_check)
    _report_load_progress(progress_callback, "project_step", 0.82)
    if not hmac.compare_digest(model.source_hash, expected_hash.lower()):
        raise ProjectIntegrityError("embedded STEP changed during project loading")
    if persisted_units is not None:
        saved_scale = persisted_units.get("scale_to_mm")
        if isinstance(saved_scale, (int, float)) and not math.isclose(
            model.units.scale_to_mm,
            float(saved_scale),
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ProjectIntegrityError(
                "embedded STEP unit conversion differs from the project"
            )
    if verify_topology:
        _verify_persisted_topology(model_payload, model)
    return model


def _verify_persisted_topology(model_payload: Any, model: CadModel) -> None:
    """Verify that persisted stable references still describe the STEP model."""

    if not isinstance(model_payload, Mapping):
        raise ProjectFormatError(
            "schema-v2 source requires persisted model topology metadata"
        )
    specifications = (
        ("bodies", "body_count", model.bodies, "body_id"),
        ("faces", "face_count", model.faces, "face_id"),
        ("edges", "edge_count", model.edges, "edge_id"),
        ("vertices", "vertex_count", model.vertices, "vertex_id"),
    )
    for (
        collection_name,
        count_name,
        actual_items,
        identifier_attribute,
    ) in specifications:
        persisted_count = model_payload.get(count_name)
        if (
            isinstance(persisted_count, bool)
            or not isinstance(persisted_count, int)
            or persisted_count < 0
        ):
            raise ProjectFormatError(
                f"model.{count_name} must be a non-negative integer"
            )
        persisted_items = model_payload.get(collection_name)
        if not isinstance(persisted_items, list):
            raise ProjectFormatError(f"model.{collection_name} must be an array")
        if persisted_count != len(persisted_items):
            raise ProjectIntegrityError(
                f"persisted {collection_name} count does not match its topology array"
            )
        if persisted_count != len(actual_items):
            raise ProjectIntegrityError(
                f"persisted {collection_name} count differs from embedded STEP"
            )
        persisted_signatures = _persisted_topology_signatures(
            persisted_items,
            collection_name,
        )
        actual_signatures = _actual_topology_signatures(
            actual_items,
            collection_name,
            identifier_attribute,
        )
        if persisted_signatures == actual_signatures:
            continue
        if persisted_signatures.keys() != actual_signatures.keys():
            detail = "IDs"
        else:
            detail = "signatures"
        raise ProjectIntegrityError(
            f"persisted {collection_name} {detail} differ from embedded STEP"
        )


def _persisted_topology_signatures(
    items: Sequence[Any],
    collection_name: str,
) -> dict[str, str]:
    signatures: dict[str, str] = {}
    for index, item in enumerate(items):
        path = f"model.{collection_name}[{index}]"
        if not isinstance(item, Mapping):
            raise ProjectFormatError(f"{path} must be an object")
        identifier = item.get("id")
        signature = item.get("signature")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ProjectFormatError(f"{path}.id must be a non-empty string")
        if not isinstance(signature, str) or not _valid_sha256(signature):
            raise ProjectFormatError(f"{path}.signature must be a SHA-256 value")
        if identifier in signatures:
            raise ProjectFormatError(
                f"model.{collection_name} contains duplicate ID {identifier!r}"
            )
        signatures[identifier] = signature
    return signatures


def _actual_topology_signatures(
    items: Sequence[Any],
    collection_name: str,
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
            or not _valid_sha256(signature)
            or identifier in signatures
        ):
            raise ProjectIntegrityError(
                f"embedded STEP produced invalid {collection_name} identity metadata"
            )
        signatures[identifier] = signature
    return signatures


def _verify_optional_project_files(
    project_dir: Path,
    payload: Mapping[str, Any],
    *,
    cancel_check: CancelCheck | None,
) -> None:
    _raise_if_load_cancelled(cancel_check)
    preview = payload.get("preview")
    if isinstance(preview, Mapping) and preview.get("glb") is not None:
        _safe_project_file(project_dir, preview.get("glb"), "preview.glb")
    _raise_if_load_cancelled(cancel_check)


def _load_embedded_gcode(
    project_dir: Path,
    payload: Mapping[str, Any],
    *,
    cancel_check: CancelCheck | None,
    progress_callback: ProgressCallback | None,
) -> GCodePreview | None:
    """Verify and parse the authoritative project-local G-code copy."""

    _raise_if_load_cancelled(cancel_check)
    gcode = payload.get("gcode")
    if gcode is None:
        return None
    if not isinstance(gcode, Mapping):
        raise ProjectFormatError("gcode must be an object or null")

    project_path = gcode.get("project_path")
    if project_path is None:
        return None
    embedded = _safe_project_file(project_dir, project_path, "gcode")
    expected_hash = gcode.get("sha256")
    if not isinstance(expected_hash, str) or not _valid_sha256(expected_hash.lower()):
        raise ProjectFormatError("gcode.sha256 must be a SHA-256 value")
    expected_hash = expected_hash.lower()

    manifest_fingerprint: GCodeSourceFingerprint | None = None
    fingerprint_payload = gcode.get("source_fingerprint")
    if fingerprint_payload is not None:
        if not isinstance(fingerprint_payload, Mapping):
            raise ProjectFormatError("gcode.source_fingerprint must be an object")
        try:
            manifest_fingerprint = GCodeSourceFingerprint.from_json(fingerprint_payload)
        except (TypeError, ValueError) as exc:
            raise ProjectFormatError("gcode.source_fingerprint is invalid") from exc
        if not hmac.compare_digest(manifest_fingerprint.sha256, expected_hash):
            raise ProjectIntegrityError(
                "G-code manifest fingerprint diverges from gcode.sha256"
            )

    _report_load_progress(progress_callback, "project_gcode_hash", 0.83)

    summary = gcode.get("summary", {})
    if not isinstance(summary, Mapping):
        raise ProjectFormatError("gcode.summary must be an object")
    controller_semantics = summary.get("controller_semantics")
    if controller_semantics is not None and (
        not isinstance(controller_semantics, str) or not controller_semantics.strip()
    ):
        raise ProjectFormatError(
            "gcode.summary.controller_semantics must be a non-empty string or null"
        )

    def report_gcode(fraction: float, phase: str = "gcode") -> None:
        mapped = 0.83 + max(0.0, min(1.0, float(fraction))) * 0.04
        _report_load_progress(progress_callback, f"project_gcode_{phase}", mapped)

    try:
        preview = load_gcode(
            embedded,
            progress_callback=report_gcode,
            cancel_check=cancel_check,
            source_sha256=expected_hash,
            controller_semantics=controller_semantics,
        )
    except GCodeLoadCancelled as exc:
        raise ProjectLoadCancelled("project G-code loading cancelled") from exc
    except GCodeSourceIntegrityError as exc:
        raise ProjectIntegrityError("embedded G-code hash mismatch") from exc
    except (OSError, UnicodeError, ValueError) as exc:
        raise ProjectIntegrityError(
            f"embedded G-code cannot be loaded: {embedded}"
        ) from exc

    _raise_if_load_cancelled(cancel_check)
    loaded_fingerprint = preview.source_fingerprint
    if not isinstance(loaded_fingerprint, GCodeSourceFingerprint):
        raise ProjectIntegrityError("loaded G-code has no verified source fingerprint")
    if manifest_fingerprint is not None and (
        not hmac.compare_digest(
            loaded_fingerprint.sha256,
            manifest_fingerprint.sha256,
        )
        or loaded_fingerprint.size_bytes != manifest_fingerprint.size_bytes
    ):
        raise ProjectIntegrityError("embedded G-code fingerprint mismatch")
    return preview


def _safe_project_file(project_dir: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProjectFormatError(f"{field}.project_path must be a relative path")
    relative = Path(value)
    if relative.is_absolute() or relative.drive or relative.root:
        raise ProjectIntegrityError(f"{field} path must stay inside the project")
    candidate = (project_dir / relative).resolve()
    try:
        candidate.relative_to(project_dir)
    except ValueError as exc:
        raise ProjectIntegrityError(
            f"{field} path escapes the project directory"
        ) from exc
    if not candidate.is_file():
        raise ProjectIntegrityError(f"embedded {field} file does not exist: {value}")
    return candidate


def _default_setup_loader(payload: Mapping[str, Any]) -> Any:
    from .manufacturing.setup import ManufacturingSetup

    setup_id = payload.get("setup_id")
    if not isinstance(setup_id, str) or not setup_id.strip():
        raise ValueError("manufacturing Setup requires a non-empty setup_id")
    return ManufacturingSetup.from_json(payload)


def _default_operation_loader(payload: Mapping[str, Any]) -> Any:
    from .manufacturing.setup import TubeOperationDefinition

    operation_type = payload.get("operation_type")
    if operation_type != "tube_thin_wall_indexed":
        raise ValueError(f"unsupported operation_type: {operation_type!r}")
    return TubeOperationDefinition.from_json(payload)


def _load_domain_item(
    value: Any, loader: Callable[[Mapping[str, Any]], Any], path: str
) -> Any:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    return loader(value)


def _validate_unique_operation_ids(operations: Sequence[Any]) -> None:
    seen: set[str] = set()
    for index, operation in enumerate(operations):
        operation_id = getattr(operation, "operation_id", None)
        if operation_id is None and isinstance(operation, Mapping):
            operation_id = operation.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError(
                f"operations[{index}].operation_id must be a non-empty string"
            )
        canonical_id = operation_id.strip()
        if canonical_id in seen:
            raise ValueError(f"duplicate operation_id: {canonical_id}")
        seen.add(canonical_id)


def _load_resource_state(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_load_resource_state(item) for item in value)
    if not isinstance(value, Mapping):
        return _json_clone(value)
    snapshot_keys = {
        "resource_type",
        "resource_id",
        "profile_version",
        "payload",
        "content_hash",
    }
    if snapshot_keys.issubset(value):
        from .manufacturing.resources import ResourceSnapshot

        return ResourceSnapshot.from_json(value)
    return {str(key): _load_resource_state(item) for key, item in value.items()}


def _raise_domain_load_error(exc: Exception) -> None:
    if exc.__class__.__name__ == "ResourceIntegrityError":
        raise ProjectIntegrityError("resource snapshot integrity check failed") from exc
    if isinstance(exc, ProjectError):
        raise exc
    raise ProjectFormatError("invalid manufacturing state in project") from exc


def _valid_sha256(value: str) -> bool:
    return len(value) == _SHA256_LENGTH and all(
        character in "0123456789abcdef" for character in value
    )


def _content_addressed_path(directory: Path, source: Path, digest: str) -> Path:
    if not _valid_sha256(digest):
        raise ProjectIntegrityError("content address must be a SHA-256 value")
    return directory / f"{digest}{source.suffix}"


def _is_link_or_reparse(path: Path) -> bool:
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


def _assert_real_directory(path: Path, *, context: str) -> None:
    absolute = Path(os.path.abspath(path))
    if _is_link_or_reparse(absolute) or not absolute.is_dir():
        raise ProjectIntegrityError(context)


def _prepare_project_subdirectory(
    project_dir: Path,
    directory: Path,
    name: str,
) -> None:
    _assert_real_directory(
        project_dir,
        context="project directory changed to a link or reparse point",
    )
    if directory.parent != project_dir:
        raise ProjectIntegrityError(f"project {name}/ path escapes the project")
    if _is_link_or_reparse(directory):
        raise ProjectIntegrityError(
            f"project {name}/ directory must not be a link or reparse point"
        )
    if directory.exists() and not directory.is_dir():
        raise ProjectIntegrityError(f"project {name}/ path must be a directory")
    directory.mkdir(parents=False, exist_ok=True)
    _assert_real_directory(
        directory,
        context=f"project {name}/ directory must remain inside the project",
    )
    try:
        directory.resolve().relative_to(project_dir)
    except ValueError as exc:
        raise ProjectIntegrityError(
            f"project {name}/ directory escapes the project"
        ) from exc


def _assert_safe_publish_target(
    destination: Path,
    allowed_parent: Path,
    name: str,
) -> None:
    absolute = Path(os.path.abspath(destination))
    try:
        absolute.parent.relative_to(allowed_parent)
    except ValueError as exc:
        raise ProjectIntegrityError(f"{name} target escapes the project") from exc
    _assert_real_directory(
        absolute.parent,
        context=f"{name} parent must remain a controlled real directory",
    )
    if _is_link_or_reparse(absolute):
        raise ProjectIntegrityError(
            f"{name} target must not be a link or reparse point"
        )


def _stable_file_fingerprint(
    path: Path,
    *,
    expected_sha256: str | None = None,
    context: str,
) -> GCodeSourceFingerprint:
    before = path.stat()
    digest = file_sha256(path)
    after = path.stat()
    if int(after.st_size) != int(before.st_size) or int(after.st_mtime_ns) != int(
        before.st_mtime_ns
    ):
        raise ProjectIntegrityError(context)
    fingerprint = GCodeSourceFingerprint(
        sha256=digest,
        size_bytes=int(after.st_size),
        mtime_ns=int(after.st_mtime_ns),
    )
    if expected_sha256 is not None and not hmac.compare_digest(
        fingerprint.sha256,
        expected_sha256,
    ):
        raise ProjectIntegrityError(context)
    return fingerprint


def _verify_gcode_source_fingerprint(
    path: Path,
    expected: GCodeSourceFingerprint,
    *,
    context: str,
) -> None:
    actual = _stable_file_fingerprint(
        path,
        expected_sha256=expected.sha256,
        context=context,
    )
    if actual != expected:
        raise ProjectIntegrityError(context)


def _atomic_copy(
    source: Path,
    destination: Path,
    *,
    expected_sha256: str | None = None,
) -> None:
    """Publish a copy only after its staged bytes match the content address."""

    source = source.resolve()
    destination = Path(os.path.abspath(destination))
    if expected_sha256 is not None:
        expected_sha256 = str(expected_sha256).lower()
        if not _valid_sha256(expected_sha256):
            raise ProjectIntegrityError("copy digest must be a SHA-256 value")
    _assert_real_directory(
        destination.parent,
        context="copy destination parent must remain a controlled real directory",
    )
    if _is_link_or_reparse(destination):
        raise ProjectIntegrityError(
            "copy destination must not be a link or reparse point"
        )
    if destination.exists() and source == destination.resolve():
        if expected_sha256 is not None:
            _stable_file_fingerprint(
                source,
                expected_sha256=expected_sha256,
                context="content-addressed source verification failed",
            )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    _assert_real_directory(
        destination.parent,
        context="copy destination parent must remain a controlled real directory",
    )
    if expected_sha256 is not None and destination.is_file():
        try:
            _stable_file_fingerprint(
                destination,
                expected_sha256=expected_sha256,
                context="existing content-addressed copy is invalid",
            )
        except (FileNotFoundError, ProjectIntegrityError):
            pass
        else:
            return
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        if expected_sha256 is not None:
            _stable_file_fingerprint(
                temporary,
                expected_sha256=expected_sha256,
                context="staged content-addressed copy verification failed",
            )
        _assert_real_directory(
            destination.parent,
            context="copy destination parent changed to a link or reparse point",
        )
        if _is_link_or_reparse(destination):
            raise ProjectIntegrityError(
                "copy destination changed to a link or reparse point"
            )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(destination: Path, payload: Mapping[str, Any]) -> None:
    destination = Path(os.path.abspath(destination))
    _assert_real_directory(
        destination.parent,
        context="project manifest parent must remain a controlled real directory",
    )
    if _is_link_or_reparse(destination):
        raise ProjectIntegrityError(
            "project manifest must not be a link or reparse point"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _assert_real_directory(
            destination.parent,
            context="project manifest parent changed to a link or reparse point",
        )
        if _is_link_or_reparse(destination):
            raise ProjectIntegrityError(
                "project manifest changed to a link or reparse point"
            )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


__all__ = [
    "PROJECT_FILE_NAME",
    "PROJECT_VERSION",
    "ProjectError",
    "ProjectFormatError",
    "ProjectIntegrityError",
    "ProjectLoadCancelled",
    "ProjectLoaded",
    "UnsupportedProjectVersionError",
    "V1_BACKUP_FILE_NAME",
    "load_project",
    "save_project",
]
