"""Applied Curve input fingerprints and Source/Build/Workpiece transforms."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from .manufacturing.coordinates import RigidTransform
from .manufacturing.curve_parameters import CurveOperationDefinition
from .manufacturing.machine import MachineProfile
from .manufacturing.setup import ManufacturingSetup
from .models import BoundingBox, CadModel, Vector3
from .postprocessing.curve_product import CURVE_ALGORITHM_VERSIONS
from .validation.indexed_tube import CollisionBox

CURVE_CONTEXT_VERSION = "curve-build-context-v2"


def curve_input_fingerprint(
    setup: ManufacturingSetup, model: CadModel | None, operation: CurveOperationDefinition
) -> str:
    build = setup.build_coordinate_system
    source = None if model is None else Path(model.source_path)
    source_hash = (
        hashlib.sha256(source.read_bytes()).hexdigest()
        if source is not None and source.is_file()
        else None
    )
    payload = {
        "version": CURVE_CONTEXT_VERSION,
        "algorithm": CURVE_ALGORITHM_VERSIONS[operation.operation_type],
        "operation": operation.semantic_sha256(),
        "setup_id": setup.setup_id,
        "assignments": setup.assignments.to_json(),
        "source": None if model is None else model.source_hash,
        "source_on_disk": source_hash,
        "edges": None if model is None else [item.to_json() for item in model.edges],
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


def validate_curve_generation_inputs(
    setup: ManufacturingSetup, model: CadModel, operation: CurveOperationDefinition
) -> None:
    if not operation.enabled or operation.setup_id != setup.setup_id:
        raise ValueError("Curve Generate requires an enabled operation in the current Setup")
    if not operation.geometry.is_complete:
        raise ValueError("Curve Generate requires an edge chain and explicit normal source")
    source = Path(model.source_path)
    if source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() != model.source_hash:
        raise ValueError("CAD source changed on disk; update the model before Generate")
    report = setup.validation_report()
    if not report.setup_ready or report.has_errors or setup.draft_nodes:
        raise ValueError("Curve Generate requires a valid applied Setup and reviewed resources")


def curve_build_from_source(setup: ManufacturingSetup) -> RigidTransform:
    build = setup.build_coordinate_system
    if build is None or not build.is_valid:
        raise ValueError("Build CS is not valid")
    return build.T_target_from_source


def curve_workpiece_from_build(
    setup: ManufacturingSetup, machine: MachineProfile
) -> RigidTransform:
    if setup.mount_datum_id is None or setup.T_mount_from_build is None:
        raise ValueError("Placement has not been applied")
    mount = machine.mount_map[setup.mount_datum_id]
    if mount.parent_link_id != machine.workpiece_link_id:
        raise ValueError("Curve mounting datum must be attached to the workpiece endpoint")
    if mount.T_parent_from_mount is None:
        raise ValueError("Mounting datum has no static transform")
    return mount.T_parent_from_mount @ setup.T_mount_from_build


def curve_collision_boxes(
    setup: ManufacturingSetup,
    model: CadModel,
    transform: RigidTransform,
) -> tuple[CollisionBox, ...]:
    """Resolve Setup fixture bodies to conservative Build-frame AABBs."""

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
    "CURVE_CONTEXT_VERSION",
    "curve_build_from_source",
    "curve_collision_boxes",
    "curve_input_fingerprint",
    "curve_workpiece_from_build",
    "validate_curve_generation_inputs",
]
