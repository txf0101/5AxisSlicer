"""Applied Planar inputs and qualifications that survive controller persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from .manufacturing.coordinates import RigidTransform
from .manufacturing.machine import MachineProfile
from .manufacturing.planar_parameters import PlanarOperationDefinition
from .manufacturing.setup import ManufacturingSetup
from .models import CadModel

if TYPE_CHECKING:
    from .postprocessing.planar_product import PlanarProductState

PLANAR_CONTEXT_VERSION = "planar-build-context-v2"


def current_planar_algorithm(operation_type: str) -> str | None:
    # Runtime lookup keeps the product's registered versions authoritative and
    # avoids importing the result module while its classes are being defined.
    from .postprocessing import planar_product

    versions = planar_product.PLANAR_PATH_ALGORITHM_VERSIONS | {
        "planar_region": planar_product.PLANAR_REGION_ALGORITHM_VERSION,
        "planar_zigzag": planar_product.PLANAR_ZIGZAG_ALGORITHM_VERSION,
    }
    return versions.get(operation_type)


def planar_input_fingerprint(
    setup: ManufacturingSetup, model: CadModel | None, operation: PlanarOperationDefinition
) -> str:
    build = setup.build_coordinate_system
    source = None if model is None else Path(model.source_path)
    source_hash = (
        hashlib.sha256(source.read_bytes()).hexdigest()
        if source is not None and source.is_file()
        else None
    )
    payload = {
        "version": PLANAR_CONTEXT_VERSION,
        "algorithm": current_planar_algorithm(operation.operation_type),
        "operation": operation.semantic_sha256(),
        "setup_id": setup.setup_id,
        "assignments": setup.assignments.to_json(),
        "source": None if model is None else model.source_hash,
        "source_on_disk": source_hash,
        "geometry": None if model is None else [item.to_json() for item in model.bodies],
        "build": None if build is None else build.T_target_from_source.to_json(),
        "resources": [
            None if resource is None else resource.content_hash
            for resource in (setup.machine, setup.nozzle, setup.material)
        ],
        "mount": setup.mount_datum_id,
        "placement": None
        if setup.T_mount_from_build is None
        else setup.T_mount_from_build.to_json(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def record_planar_input(state: PlanarProductState, digest: str) -> PlanarProductState:
    return replace(
        state,
        result_payload=dict(state.result_payload or {})
        | {"generation_input_sha256": digest, "generation_context_version": PLANAR_CONTEXT_VERSION},
    )


def invalidate_legacy_planar_state(state: PlanarProductState) -> PlanarProductState:
    """Retain old preview/evidence while withdrawing obsolete Ready/Warning status."""
    if state.status not in {"ready", "warning"}:
        return state
    payload = state.result_payload or {}
    manifest = payload.get("manifest", {})
    current = current_planar_algorithm(str(payload.get("operation_type", "")))
    valid = (
        isinstance(manifest, Mapping)
        and current is not None
        and manifest.get("algorithm_version") == current
        and payload.get("generation_context_version") == PLANAR_CONTEXT_VERSION
        and isinstance(payload.get("generation_input_sha256"), str)
    )
    return state if valid else replace(state, status="stale")


def refresh_planar_state(
    state: PlanarProductState,
    setup: ManufacturingSetup,
    model: CadModel | None,
    operation: PlanarOperationDefinition,
) -> PlanarProductState:
    state = invalidate_legacy_planar_state(state)
    if state.status not in {"ready", "warning"}:
        return state
    payload = state.result_payload or {}
    try:
        matches = (
            model is not None
            and (operation.operation_type == "planar_region" or setup.setup_ready)
            and not setup.draft_nodes
            and operation.semantic_sha256() == state.parameter_semantic_sha256
            and payload.get("operation_type") == operation.operation_type
            and payload.get("generation_input_sha256")
            == planar_input_fingerprint(setup, model, operation)
        )
    except OSError:
        matches = False
    return state if matches else replace(state, status="stale")


def validate_planar_generation_inputs(
    setup: ManufacturingSetup, model: CadModel, operation: PlanarOperationDefinition
) -> None:
    if not operation.enabled or operation.setup_id != setup.setup_id:
        raise ValueError("Planar Generate requires an enabled operation in the current Setup")
    if operation.geometry.body is None:
        raise ValueError("Planar Generate requires a selected body")
    source = Path(model.source_path)
    if source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() != model.source_hash:
        raise ValueError("CAD source changed on disk; update the model before Generate")
    if operation.operation_type == "planar_region":
        return
    report = setup.validation_report()
    if not report.setup_ready or report.has_errors or setup.draft_nodes:
        raise ValueError(
            "Planar path Generate requires a valid applied Setup and reviewed resources"
        )


def planar_source_from_build(setup: ManufacturingSetup) -> RigidTransform:
    build = setup.build_coordinate_system
    if build is None or not build.is_valid:
        raise ValueError("Build CS is not valid")
    # The low-level slicer calls its raw BRep frame 'model'; the CAD authority
    # still stores Source coordinates. Model CS is a separate display frame.
    return RigidTransform(
        build.T_target_from_source.inverse().matrix,
        source_frame="build",
        target_frame="model",
    )


def planar_workpiece_from_build(
    setup: ManufacturingSetup, machine: MachineProfile
) -> RigidTransform:
    if setup.mount_datum_id is None or setup.T_mount_from_build is None:
        raise ValueError("Placement has not been applied")
    mount = machine.mount_map[setup.mount_datum_id]
    if mount.parent_link_id != machine.workpiece_link_id:
        raise ValueError("Planar mounting datum must be rigidly attached to the workpiece endpoint")
    if mount.T_parent_from_mount is None:
        raise ValueError("Mounting datum has no static transform")
    return mount.T_parent_from_mount @ setup.T_mount_from_build
