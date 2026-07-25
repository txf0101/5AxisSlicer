"""Project-format adapter for the Qt-independent Tube controller."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .manufacturing.coordinates import CoordinateFrameDefinition
from .manufacturing.resources import ResourceSnapshot
from .manufacturing.setup import (
    ManufacturingSetup,
    SetupValidationReport,
    TubeOperationDefinition,
)
from .tube_drafts import (
    BodyCandidate,
    CoordinateFrameDraft,
    PendingDraftError,
    PlacementDraft,
)

TUBE_CONTROLLER_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class TubeControllerData:
    setup: ManufacturingSetup
    operations: tuple[TubeOperationDefinition, ...]
    body_catalog: tuple[BodyCandidate, ...]


def controller_project_json(
    setup: ManufacturingSetup,
    operations: tuple[TubeOperationDefinition, ...],
    draft_nodes: tuple[str, ...],
    *,
    allow_drafts: bool,
) -> dict[str, Any]:
    if draft_nodes and not allow_drafts:
        raise PendingDraftError(draft_nodes)
    return {
        "schema_version": TUBE_CONTROLLER_SCHEMA_VERSION,
        "setups": [setup.to_json()],
        "operations": [operation.to_json() for operation in operations],
    }


def parse_controller_project(payload: Mapping[str, Any]) -> TubeControllerData:
    if not isinstance(payload, Mapping):
        raise ValueError("Tube controller payload must be an object")
    version = int(payload.get("schema_version", TUBE_CONTROLLER_SCHEMA_VERSION))
    if version > TUBE_CONTROLLER_SCHEMA_VERSION:
        raise ValueError(f"unsupported Tube controller schema {version}")
    raw_setups = payload.get("setups")
    if raw_setups is None:
        raw_setup = payload.get("setup")
        raw_setups = () if raw_setup is None else (raw_setup,)
    if not isinstance(raw_setups, list | tuple):
        raise ValueError("setups must be an array")
    if len(raw_setups) != 1:
        raise ValueError("TubeSetupController requires exactly one Setup")
    raw_operations = payload.get("operations", ())
    raw_catalog = payload.get("body_catalog", ())
    if not isinstance(raw_operations, list | tuple):
        raise ValueError("operations must be an array")
    if not isinstance(raw_catalog, list | tuple):
        raise ValueError("body_catalog must be an array")
    return TubeControllerData(
        ManufacturingSetup.from_json(raw_setups[0]),
        tuple(TubeOperationDefinition.from_json(item) for item in raw_operations),
        tuple(BodyCandidate.from_json(item) for item in raw_catalog),
    )


def snapshot_identity_json(snapshot: ResourceSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "resource_type": snapshot.resource_type,
        "resource_id": snapshot.resource_id,
        "profile_version": snapshot.profile_version,
        "content_hash": snapshot.content_hash,
    }


def frame_state_json(frame: CoordinateFrameDefinition | None) -> dict[str, Any] | None:
    if frame is None:
        return None
    return {
        "frame_id": frame.frame_id,
        "name": frame.name,
        "revision": frame.revision,
        "confirmed": frame.is_confirmed,
        "valid": frame.is_valid,
        "T_target_from_source": frame.T_target_from_source.to_json(),
    }


def controller_state_json(
    *,
    setup: ManufacturingSetup,
    operations: tuple[TubeOperationDefinition, ...],
    body_candidates: tuple[BodyCandidate, ...],
    drafts: Mapping[str, CoordinateFrameDraft | PlacementDraft],
    report: SetupValidationReport,
    source_path: str | None,
    source_hash: str | None,
    resource_library: dict[str, object],
    operation_types: tuple[str, ...],
    operation_limit: int,
    modified: bool,
) -> dict[str, Any]:
    return {
        "schema_version": TUBE_CONTROLLER_SCHEMA_VERSION,
        "setup_id": setup.setup_id,
        "setup_name": setup.name,
        "source": {"path": source_path, "hash": source_hash},
        "capabilities": {
            "available_operation_types": list(operation_types),
            "max_interactive_operations": operation_limit,
            "fixture_editor_visible": False,
        },
        "body_candidates": [candidate.to_json() for candidate in body_candidates],
        "assignments": setup.assignments.to_json(),
        "resources": {
            "machine": snapshot_identity_json(setup.machine),
            "nozzle": snapshot_identity_json(setup.nozzle),
            "material": snapshot_identity_json(setup.material),
        },
        "resource_library": resource_library,
        "coordinate_systems": {
            "model": frame_state_json(setup.model_coordinate_system),
            "build": frame_state_json(setup.build_coordinate_system),
        },
        "placement": {
            "mount_datum_id": setup.mount_datum_id,
            "applied": setup.T_mount_from_build is not None,
        },
        "operations": [operation.to_json() for operation in operations],
        "drafts": {node: draft.to_json() for node, draft in sorted(drafts.items())},
        "validation": report.to_json(),
        "coordinates_valid": report.coordinates_valid,
        "setup_ready": report.setup_ready,
        "has_drafts": bool(drafts),
        "modified": modified,
    }


__all__ = [
    "TUBE_CONTROLLER_SCHEMA_VERSION",
    "TubeControllerData",
    "controller_project_json",
    "controller_state_json",
    "frame_state_json",
    "parse_controller_project",
    "snapshot_identity_json",
]
