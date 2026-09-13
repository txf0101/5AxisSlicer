"""Versioned project manifests and embedded source verification.

Embedded STEP and G-code copies are authoritative when a project reopens;
external paths are provenance for an explicit source update. The manifest is
published with fsync and replace. A failed save may leave an unreferenced
content-addressed copy, while the published manifest keeps its prior state.
"""

from __future__ import annotations

import hmac
import json
import math
import os
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, NoReturn

from . import project_assets, project_storage
from .gcode_preview import (
    GCodePreview,
    GCodeSourceFingerprint,
    PreviewSettings,
    load_gcode,
)
from .models import CadModel, SelectionState
from .project_contract import (
    ProjectError,
    ProjectFormatError,
    ProjectIntegrityError,
    ProjectLoadCancelled,
    UnsupportedProjectVersionError,
)
from .step_loader import file_sha256, load_step

PROJECT_VERSION = 2
PROJECT_FILE_NAME = "project.json"
V1_BACKUP_FILE_NAME = "project.v1.json"
_SHA256_LENGTH = 64


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


@dataclass(frozen=True, slots=True)
class ProjectSaveDocument:
    """Typed snapshot consumed by one project-save transaction."""

    directory: Path
    model: CadModel | None
    selection: SelectionState
    workbench: dict[str, Any]
    gcode_preview: GCodePreview | None
    preview_settings: PreviewSettings | None
    result_preview_state: Any | None
    setups: tuple[Any, ...]
    operations: tuple[Any, ...]
    resources: Any
    original_source_path: Path | None


@dataclass(frozen=True, slots=True)
class _ProjectManifest:
    project_json: Path
    project_directory: Path
    payload: dict[str, Any]
    migrated_from_v1: bool


@dataclass(frozen=True, slots=True)
class _ProjectDomainState:
    selection: SelectionState
    workbench: dict[str, Any]
    setups: tuple[Any, ...]
    operations: tuple[Any, ...]
    resources: Any


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
    document = ProjectSaveDocument(
        directory=Path(directory),
        model=model,
        selection=selection,
        workbench=dict(workbench_state or {}),
        gcode_preview=gcode_preview,
        preview_settings=preview_settings,
        result_preview_state=result_preview_state,
        setups=(setup,) if setup is not None else _collection_values(setups),
        operations=_collection_values(operations),
        resources={} if resources is None else resources,
        original_source_path=(None if original_source_path is None else Path(original_source_path)),
    )
    return _save_project_document(document)


def _save_project_document(document: ProjectSaveDocument) -> Path:
    project_dir, source_dir, output = _prepare_save_destination(document.directory)
    try:
        with project_storage.project_save_lock(project_dir):
            return _save_project_document_locked(document, project_dir, source_dir, output)
    except project_storage.StorageIntegrityError as exc:
        raise ProjectIntegrityError(str(exc)) from exc


def _save_project_document_locked(
    document: ProjectSaveDocument,
    project_dir: Path,
    source_dir: Path,
    output: Path,
) -> Path:
    previous_payload = _read_existing_for_save(output)
    source_payload, model_payload = _embed_model_source(
        document.model,
        source_dir,
        document.original_source_path,
    )
    gcode_payload = _embed_gcode_source(document.gcode_preview, source_dir)
    setups, operations, resources = _serialize_domain_state(document)
    created_at = _existing_created_at(previous_payload) or _utc_now()
    payload = _build_project_manifest(
        document,
        created_at=created_at,
        source_payload=source_payload,
        model_payload=model_payload,
        gcode_payload=gcode_payload,
        setups=setups,
        operations=operations,
        resources=resources,
    )
    _backup_v1_manifest(project_dir, output, previous_payload)
    _atomic_write_json(output, payload)
    return output


def _prepare_save_destination(
    directory: Path,
) -> tuple[Path, Path, Path]:
    requested = Path(os.path.abspath(directory.expanduser()))
    if _is_link_or_reparse(requested):
        raise ProjectIntegrityError("project directory must not be a link or reparse point")
    requested.mkdir(parents=True, exist_ok=True)
    if _is_link_or_reparse(requested):
        raise ProjectIntegrityError("project directory changed to a link or reparse point")
    project_dir = requested.resolve()
    _assert_real_directory(
        project_dir,
        context="project directory must remain a controlled real directory",
    )
    source_dir = project_dir / "source"
    _prepare_project_subdirectory(project_dir, source_dir, "source")
    _prepare_project_subdirectory(project_dir, project_dir / "preview", "preview")
    output = project_dir / PROJECT_FILE_NAME
    _assert_safe_publish_target(output, project_dir, PROJECT_FILE_NAME)
    return project_dir, source_dir, output


def _embed_model_source(
    model: CadModel | None,
    source_dir: Path,
    original_source_path: Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if model is None:
        return None, None
    source_path = Path(model.source_path).expanduser().resolve()
    if not source_path.is_file():
        raise ProjectIntegrityError(f"STEP source does not exist: {source_path}")
    actual_hash = file_sha256(source_path)
    expected_hash = str(model.source_hash).lower()
    if not _valid_sha256(expected_hash):
        raise ProjectIntegrityError("CAD model has an invalid source hash")
    if not hmac.compare_digest(actual_hash, expected_hash):
        raise ProjectIntegrityError("STEP source changed after it was loaded")

    source_copy = _content_addressed_path(source_dir, source_path, actual_hash)
    _atomic_copy(source_path, source_copy, expected_sha256=actual_hash)
    if not hmac.compare_digest(file_sha256(source_path), expected_hash):
        raise ProjectIntegrityError("STEP source changed while saving")
    copied_hash = file_sha256(source_copy)
    if not hmac.compare_digest(copied_hash, actual_hash):
        raise ProjectIntegrityError("embedded STEP verification failed after copy")

    model_payload = _model_payload(model)
    project_assets.verify_persisted_topology(model_payload, model)
    provenance = (
        source_path if original_source_path is None else original_source_path.expanduser().resolve()
    )
    source_payload = {
        "original_path": str(provenance),
        "project_path": (Path("source") / source_copy.name).as_posix(),
        "sha256": copied_hash,
    }
    return source_payload, model_payload


def _embed_gcode_source(preview: GCodePreview | None, source_dir: Path) -> dict[str, Any] | None:
    if preview is None:
        return None
    source = Path(preview.source_path).expanduser().resolve()
    fingerprint = preview.source_fingerprint
    if isinstance(fingerprint, GCodeSourceFingerprint) and not source.is_file():
        raise ProjectIntegrityError(
            "verified G-code source no longer exists; reload it before saving"
        )

    embedded: GCodeSourceFingerprint | None = None
    project_path: str | None = None
    if source.is_file():
        if not isinstance(fingerprint, GCodeSourceFingerprint):
            raise ProjectIntegrityError(
                "G-code source fingerprint is missing; reload the source before saving"
            )
        _verify_gcode_source_fingerprint(
            source,
            fingerprint,
            context="G-code source changed after it was loaded",
        )
        destination = _content_addressed_path(source_dir, source, fingerprint.sha256)
        _atomic_copy(source, destination, expected_sha256=fingerprint.sha256)
        _verify_gcode_source_fingerprint(
            source,
            fingerprint,
            context="G-code source changed while saving",
        )
        embedded = _stable_file_fingerprint(
            destination,
            expected_sha256=fingerprint.sha256,
            context="embedded G-code verification failed after copy",
        )
        project_path = (Path("source") / destination.name).as_posix()

    return {
        "original_path": str(source),
        "project_path": project_path,
        "sha256": None if embedded is None else embedded.sha256,
        "source_fingerprint": None if embedded is None else embedded.to_json(),
        "summary": _json_value(preview.summary(), path="gcode.summary"),
    }


def _serialize_domain_state(
    document: ProjectSaveDocument,
) -> tuple[list[Any], list[Any], Any]:
    setups = [
        _json_value(value, path=f"setups[{index}]") for index, value in enumerate(document.setups)
    ]
    operations = [
        _json_value(value, path=f"operations[{index}]")
        for index, value in enumerate(document.operations)
    ]
    resources = _json_value(document.resources, path="resources")
    _validate_no_persisted_setup_drafts(setups)
    _validate_setup_resource_mirror(setups, resources)
    return setups, operations, resources


def _build_project_manifest(
    document: ProjectSaveDocument,
    *,
    created_at: str,
    source_payload: dict[str, Any] | None,
    model_payload: dict[str, Any] | None,
    gcode_payload: dict[str, Any] | None,
    setups: list[Any],
    operations: list[Any],
    resources: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": PROJECT_VERSION,
        "created_at": created_at,
        "updated_at": _utc_now(),
        "workbench": _json_value(document.workbench, path="workbench"),
        "source": source_payload,
        "gcode": gcode_payload,
        "model": model_payload,
        "selection": document.selection.to_json(),
        "setups": setups,
        "operations": operations,
        "resources": resources,
        # Schema v1 readers still inspect this field.
        "manufacturable_feature_groups": [],
        "preview": {
            "glb": None,
            "gcode": (
                None if document.preview_settings is None else document.preview_settings.to_json()
            ),
        },
    }
    if document.result_preview_state is not None:
        payload["result_preview"] = _json_value(
            document.result_preview_state,
            path="result_preview",
        )
    return payload


def _backup_v1_manifest(
    project_dir: Path,
    output: Path,
    previous_payload: Mapping[str, Any] | None,
) -> None:
    if previous_payload is None or previous_payload.get("version") != 1:
        return
    backup = project_dir / V1_BACKUP_FILE_NAME
    if not backup.exists():
        _atomic_copy(output, backup)


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

    manifest = _load_project_manifest(path, cancel_check, progress_callback)
    model = project_assets.load_embedded_model(
        manifest.project_directory,
        manifest.payload,
        length_unit_override=length_unit_override,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
        verify_topology=not manifest.migrated_from_v1,
        hash_file=file_sha256,
        step_loader=load_step,
    )
    _raise_if_load_cancelled(cancel_check)
    gcode_preview = project_assets.load_embedded_gcode(
        manifest.project_directory,
        manifest.payload,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
        gcode_loader=load_gcode,
    )
    _raise_if_load_cancelled(cancel_check)
    project_assets.verify_optional_project_files(
        manifest.project_directory,
        manifest.payload,
        cancel_check=cancel_check,
    )
    _report_load_progress(progress_callback, "project_domain", 0.88)
    domain = _load_project_domain(
        manifest.payload,
        setup_loader=setup_loader,
        operation_loader=operation_loader,
        cancel_check=cancel_check,
    )

    loaded = ProjectLoaded(
        project_directory=manifest.project_directory,
        project_json=manifest.project_json,
        model=model,
        selection=domain.selection,
        workbench=domain.workbench,
        setups=domain.setups,
        operations=domain.operations,
        resources=domain.resources,
        migrated_from_v1=manifest.migrated_from_v1,
        payload=manifest.payload,
        gcode_preview=gcode_preview,
    )
    _report_load_progress(progress_callback, "project_ready", 1.0)
    return loaded


def _load_project_manifest(
    path: str | Path,
    cancel_check: CancelCheck | None,
    progress_callback: ProgressCallback | None,
) -> _ProjectManifest:
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
    migrated = version == 1
    payload = _migrate_v1_payload(raw_payload) if migrated else raw_payload
    _validate_v2_root(payload)
    _validate_setup_resource_mirror(payload["setups"], payload["resources"])
    _report_load_progress(progress_callback, "project_metadata", 0.08)
    return _ProjectManifest(
        project_json=project_json,
        project_directory=project_json.parent.resolve(),
        payload=payload,
        migrated_from_v1=migrated,
    )


def _load_project_domain(
    payload: Mapping[str, Any],
    *,
    setup_loader: SetupLoader | None,
    operation_loader: OperationLoader | None,
    cancel_check: CancelCheck | None,
) -> _ProjectDomainState:
    try:
        _raise_if_load_cancelled(cancel_check)
        workbench = payload.get("workbench", {})
        setups = payload.get("setups", [])
        operations = payload.get("operations", [])
        if not isinstance(workbench, Mapping):
            raise ValueError("workbench must be an object")
        if not isinstance(setups, list):
            raise ValueError("setups must be an array")
        if not isinstance(operations, list):
            raise ValueError("operations must be an array")
        loaded_setups = _load_domain_array(
            setups,
            setup_loader or _default_setup_loader,
            "setups",
        )
        _raise_if_load_cancelled(cancel_check)
        loaded_operations = _load_domain_array(
            operations,
            operation_loader or _default_operation_loader,
            "operations",
        )
        _validate_unique_operation_ids(loaded_operations)
        state = _ProjectDomainState(
            selection=SelectionState.from_json(payload.get("selection")),
            workbench=_json_clone(workbench),
            setups=loaded_setups,
            operations=loaded_operations,
            resources=_load_resource_state(payload.get("resources", {})),
        )
        _raise_if_load_cancelled(cancel_check)
        return state
    except Exception as exc:
        _raise_domain_load_error(exc)


def _load_domain_array(
    values: Sequence[Any],
    loader: Callable[[Mapping[str, Any]], Any],
    field: str,
) -> tuple[Any, ...]:
    return tuple(
        _load_domain_item(item, loader, f"{field}[{index}]") for index, item in enumerate(values)
    )


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
    if isinstance(value, str | bytes | bytearray | Mapping) or hasattr(value, "to_json"):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _json_value(value: Any, *, path: str) -> Any:
    value = _json_adapt(value)
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return 0.0 if value == 0.0 else value
    if isinstance(value, Mapping):
        return _json_mapping(value, path)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise TypeError(f"{path} contains unsupported value type {type(value).__name__}")


def _json_adapt(value: Any) -> Any:
    if hasattr(value, "to_json") and not isinstance(value, Mapping):
        return value.to_json()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    return value


def _json_mapping(value: Mapping[Any, Any], path: str) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{path} contains a non-string mapping key")
        output[key] = _json_value(item, path=f"{path}.{key}")
    return output


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


def _default_setup_loader(payload: Mapping[str, Any]) -> Any:
    from .manufacturing.setup import ManufacturingSetup

    setup_id = payload.get("setup_id")
    if not isinstance(setup_id, str) or not setup_id.strip():
        raise ValueError("manufacturing Setup requires a non-empty setup_id")
    return ManufacturingSetup.from_json(payload)


def _default_operation_loader(payload: Mapping[str, Any]) -> Any:
    from .manufacturing.curve_parameters import CurveOperationDefinition
    from .manufacturing.freeform_parameters import FreeformOperationDefinition
    from .manufacturing.planar_parameters import PlanarOperationDefinition
    from .manufacturing.rotary_parameters import RotaryOperationDefinition
    from .manufacturing.setup import TubeOperationDefinition

    operation_type = str(payload.get("operation_type", "")).strip().lower()
    if operation_type.startswith("tube_"):
        return TubeOperationDefinition.from_json(payload)
    if operation_type.startswith("planar_"):
        return PlanarOperationDefinition.from_json(payload)
    if operation_type.startswith("curve_"):
        return CurveOperationDefinition.from_json(payload)
    if operation_type.startswith("freeform_"):
        return FreeformOperationDefinition.from_json(payload)
    if operation_type.startswith("rotary_"):
        return RotaryOperationDefinition.from_json(payload)
    raise ValueError(f"unsupported operation_type: {operation_type!r}")


def _load_domain_item(value: Any, loader: Callable[[Mapping[str, Any]], Any], path: str) -> Any:
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
            raise ValueError(f"operations[{index}].operation_id must be a non-empty string")
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


def _raise_domain_load_error(exc: Exception) -> NoReturn:
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
    return project_storage.is_link_or_reparse(path)


def _assert_real_directory(path: Path, *, context: str) -> None:
    try:
        project_storage.assert_real_directory(path, context=context)
    except project_storage.StorageIntegrityError as exc:
        raise ProjectIntegrityError(str(exc)) from exc


def _prepare_project_subdirectory(
    project_dir: Path,
    directory: Path,
    name: str,
) -> None:
    try:
        project_storage.prepare_subdirectory(project_dir, directory, name)
    except project_storage.StorageIntegrityError as exc:
        raise ProjectIntegrityError(str(exc)) from exc


def _assert_safe_publish_target(
    destination: Path,
    allowed_parent: Path,
    name: str,
) -> None:
    try:
        project_storage.assert_safe_publish_target(destination, allowed_parent, name)
    except project_storage.StorageIntegrityError as exc:
        raise ProjectIntegrityError(str(exc)) from exc


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
    try:
        project_storage.atomic_copy(
            source,
            destination,
            expected_sha256=expected_sha256,
            hash_file=file_sha256,
            copy_file=shutil.copy2,
        )
    except project_storage.StorageIntegrityError as exc:
        raise ProjectIntegrityError(str(exc)) from exc


def _atomic_write_json(destination: Path, payload: Mapping[str, Any]) -> None:
    """Publish a manifest with staged-file and directory durability."""

    try:
        project_storage.atomic_write_json(destination, payload)
    except project_storage.StorageIntegrityError as exc:
        raise ProjectIntegrityError(str(exc)) from exc


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
