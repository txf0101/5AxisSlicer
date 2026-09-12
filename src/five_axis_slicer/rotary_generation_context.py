"""Applied Rotary inputs and qualifications retained across persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .manufacturing.coordinates import RigidTransform
from .manufacturing.machine import MachineProfile
from .manufacturing.rotary_parameters import RotaryOperationDefinition
from .manufacturing.setup import ManufacturingSetup
from .models import BoundingBox, CadModel, Vector3
from .validation.indexed_tube import CollisionBox

if TYPE_CHECKING:
    from .postprocessing.rotary_product import RotaryProductState


ROTARY_CONTEXT_VERSION = "rotary-build-context-v1"


def current_rotary_algorithm(operation_type: str) -> str | None:
    from .postprocessing import rotary_product

    return rotary_product.ROTARY_ALGORITHM_VERSIONS.get(str(operation_type).strip().lower())


def rotary_input_fingerprint(
    setup: ManufacturingSetup,
    model: CadModel | None,
    operation: RotaryOperationDefinition,
) -> str:
    build = setup.build_coordinate_system
    source = None if model is None else Path(model.source_path)
    source_hash = (
        hashlib.sha256(source.read_bytes()).hexdigest()
        if source is not None and source.is_file()
        else None
    )
    payload = {
        "version": ROTARY_CONTEXT_VERSION,
        "algorithm": current_rotary_algorithm(operation.operation_type),
        "operation": operation.semantic_sha256(),
        "setup_id": setup.setup_id,
        "assignments": setup.assignments.to_json(),
        "source": None if model is None else model.source_hash,
        "source_on_disk": source_hash,
        "geometry": None
        if model is None
        else {
            "bodies": [item.to_json() for item in model.bodies],
            "faces": [item.to_json() for item in model.faces],
            "edges": [item.to_json() for item in model.edges],
        },
        "build": None if build is None else build.T_target_from_source.to_json(),
        "resources": [
            None if item is None else item.content_hash
            for item in (setup.machine, setup.nozzle, setup.material)
        ],
        "mount": setup.mount_datum_id,
        "placement": None
        if setup.T_mount_from_build is None
        else setup.T_mount_from_build.to_json(),
        "collision": {
            "check_ipw": True,
            "fixture_body_ids": list(setup.assignments.fixture_body_ids),
        },
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def record_rotary_input(state: RotaryProductState, digest: str) -> RotaryProductState:
    return replace(
        state,
        result_payload=dict(state.result_payload or {})
        | {
            "generation_input_sha256": str(digest),
            "generation_context_version": ROTARY_CONTEXT_VERSION,
        },
    )


def invalidate_legacy_rotary_state(state: RotaryProductState) -> RotaryProductState:
    """Retain inspectable old evidence while withdrawing its export qualification."""

    if state.status not in {"ready", "warning"}:
        return state
    payload = state.result_payload or {}
    manifest = payload.get("manifest", {})
    current = current_rotary_algorithm(str(payload.get("operation_type", "")))
    valid = (
        isinstance(manifest, Mapping)
        and current is not None
        and manifest.get("algorithm_version") == current
        and payload.get("generation_context_version") == ROTARY_CONTEXT_VERSION
        and isinstance(payload.get("generation_input_sha256"), str)
    )
    return state if valid else replace(state, status="stale")


def refresh_rotary_state(
    state: RotaryProductState,
    setup: ManufacturingSetup,
    model: CadModel | None,
    operation: RotaryOperationDefinition,
) -> RotaryProductState:
    state = invalidate_legacy_rotary_state(state)
    if state.status not in {"ready", "warning"}:
        return state
    payload = state.result_payload or {}
    try:
        matches = (
            model is not None
            and setup.setup_ready
            and not setup.draft_nodes
            and operation.semantic_sha256() == state.parameter_semantic_sha256
            and payload.get("operation_type") == operation.operation_type
            and payload.get("generation_input_sha256")
            == rotary_input_fingerprint(setup, model, operation)
        )
    except OSError:
        matches = False
    return state if matches else replace(state, status="stale")


def validate_rotary_generation_inputs(
    setup: ManufacturingSetup,
    model: CadModel,
    operation: RotaryOperationDefinition,
) -> None:
    if not operation.enabled or operation.setup_id != setup.setup_id:
        raise ValueError("Rotary Generate requires an enabled operation in the current Setup")
    if not operation.geometry.is_complete:
        raise ValueError("Rotary Generate requires a complete axis, profile, and angular region")
    if operation.geometry.preview_only:
        raise ValueError("preview-only Rotary regions cannot generate an exportable product")
    source = Path(model.source_path)
    if source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() != model.source_hash:
        raise ValueError("CAD source changed on disk; update the model before Generate")
    report = setup.validation_report()
    if not report.setup_ready or report.has_errors or setup.draft_nodes:
        raise ValueError("Rotary Generate requires a valid applied Setup and reviewed resources")
    if current_rotary_algorithm(operation.operation_type) is None:
        raise ValueError(f"Rotary operation has no registered algorithm: {operation.operation_type}")


def rotary_build_from_source(setup: ManufacturingSetup) -> RigidTransform:
    build = setup.build_coordinate_system
    if build is None or not build.is_valid:
        raise ValueError("Build CS is not valid")
    return build.T_target_from_source


def rotary_workpiece_from_build(
    setup: ManufacturingSetup,
    machine: MachineProfile,
) -> RigidTransform:
    if setup.mount_datum_id is None or setup.T_mount_from_build is None:
        raise ValueError("Placement has not been applied")
    mount = machine.mount_map[setup.mount_datum_id]
    if mount.parent_link_id != machine.workpiece_link_id:
        raise ValueError("Rotary mounting datum must be attached to the workpiece endpoint")
    if mount.T_parent_from_mount is None:
        raise ValueError("Mounting datum has no static transform")
    return mount.T_parent_from_mount @ setup.T_mount_from_build


def rotary_collision_boxes(
    setup: ManufacturingSetup,
    model: CadModel,
    transform: RigidTransform,
) -> tuple[CollisionBox, ...]:
    boxes = []
    for body_id in setup.assignments.fixture_body_ids:
        body = model.body_map.get(body_id)
        if body is None or body.bounds is None:
            raise ValueError(f"collision body has no valid bounds: {body_id}")
        bounds = _transformed_bounds(body.bounds, transform)
        boxes.append(CollisionBox(body_id, "fixture", bounds.minimum, bounds.maximum))
    return tuple(boxes)


def _transformed_bounds(box: BoundingBox, transform: RigidTransform) -> BoundingBox:
    corners = tuple(
        transform.transform_point((x, y, z))
        for x in (box.minimum[0], box.maximum[0])
        for y in (box.minimum[1], box.maximum[1])
        for z in (box.minimum[2], box.maximum[2])
    )
    return BoundingBox(
        cast(Vector3, tuple(min(point[index] for point in corners) for index in range(3))),
        cast(Vector3, tuple(max(point[index] for point in corners) for index in range(3))),
    )


__all__ = [
    "ROTARY_CONTEXT_VERSION",
    "current_rotary_algorithm",
    "invalidate_legacy_rotary_state",
    "record_rotary_input",
    "refresh_rotary_state",
    "rotary_build_from_source",
    "rotary_collision_boxes",
    "rotary_input_fingerprint",
    "rotary_workpiece_from_build",
    "validate_rotary_generation_inputs",
]
