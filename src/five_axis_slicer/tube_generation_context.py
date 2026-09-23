"""Validated, immutable inputs for the Tube product boundary.

CAD authority remains in Source CS. A private rigidly transformed view feeds
the geometry algorithms in Build CS; the IK receives only the static mounting
transform relative to the machine's workpiece endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from itertools import product
import json
from pathlib import Path
from typing import Any, cast

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Trsf

from .manufacturing.coordinates import RigidTransform
from .manufacturing.setup import TubeBuildupOperationConfig, TubeOperationDefinition
from .models import BoundingBox, CadModel, EdgeInfo, FaceInfo, Vector3
from .validation.indexed_tube import CollisionBox

CONTEXT_VERSION = "tube-build-context-v5"


def tube_input_fingerprint(controller: Any, operation: TubeOperationDefinition) -> str:
    """Hash applied manufacturing inputs, excluding display and dirty flags."""
    setup = controller.setup
    build = setup.build_coordinate_system
    model = controller.cad_model
    source_path = None if model is None else Path(model.source_path)
    source_hash = (
        hashlib.sha256(source_path.read_bytes()).hexdigest()
        if source_path is not None and source_path.is_file()
        else None
    )
    operation_payload = operation.to_json()
    for key in ("name", "state", "dirty_reasons"):
        operation_payload.pop(key, None)
    payload = {
        "version": CONTEXT_VERSION,
        "source": None if model is None else model.source_hash,
        "source_on_disk": source_hash,
        "geometry": None
        if model is None
        else {
            "bodies": [item.to_json() for item in model.bodies],
            "edges": [item.to_json() for item in model.edges],
            "faces": [item.to_json() for item in model.faces],
        },
        "operation": operation_payload,
        "assignments": setup.assignments.to_json(),
        "resources": [
            None if item is None else item.content_hash
            for item in (setup.machine, setup.nozzle, setup.material)
        ],
        "build": None if build is None else build.T_target_from_source.to_json(),
        "mount": setup.mount_datum_id,
        "placement": None
        if setup.T_mount_from_build is None
        else setup.T_mount_from_build.to_json(),
        "collision": {"check_ipw": True, "environment": "build_aabb"},
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class TubeGenerationContext:
    model_in_build: CadModel
    T_workpiece_from_build: RigidTransform
    obstacles: tuple[CollisionBox, ...]
    input_sha256: str
    metadata: dict[str, Any]


def make_tube_generation_context(
    controller: Any, operation: TubeOperationDefinition
) -> TubeGenerationContext:
    report = controller.validation_report()
    if not report.setup_ready or report.has_errors or controller.draft_nodes:
        codes = ", ".join(issue.code for issue in report.issues if issue.severity.value == "error")
        raise ValueError(f"Generate requires a valid applied Setup: {codes or 'pending drafts'}")
    model = controller.cad_model
    if model is None:
        raise ValueError("Generate requires an attached CAD model")
    path = Path(model.source_path)
    if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() != model.source_hash:
        raise ValueError("CAD source changed on disk; update the model before Generate")
    setup = controller.setup
    if operation.setup_id != setup.setup_id:
        raise ValueError("Tube operation belongs to another Setup")
    build = setup.build_coordinate_system
    assert build is not None and setup.T_mount_from_build is not None
    machine = controller.machine_profile()
    mount = machine.mount_map[setup.mount_datum_id]
    # A mount on another moving branch cannot be represented by a static IK input.
    if mount.parent_link_id != machine.workpiece_link_id:
        raise ValueError("Tube mounting datum must be rigidly attached to the workpiece endpoint")
    assert mount.T_parent_from_mount is not None
    placement = mount.T_parent_from_mount @ setup.T_mount_from_build
    view = _model_in_build(model, build.T_target_from_source)
    obstacles = _collision_boxes(view, setup, operation)
    metadata = _context_metadata(build.T_target_from_source, placement, obstacles, report)
    return TubeGenerationContext(
        view, placement, obstacles, tube_input_fingerprint(controller, operation), metadata
    )


def _collision_boxes(view, setup, operation) -> tuple[CollisionBox, ...]:
    obstacles = []
    substrate = operation.geometry.substrate_body
    roles = {identifier: "fixture" for identifier in setup.assignments.fixture_body_ids}
    base_is_printed = (
        operation.operation_type == "tube_buildup"
        and isinstance(operation.type_config, TubeBuildupOperationConfig)
        and operation.type_config.include_planar_base
    )
    # A substrate generated in this sequence is not a pre-existing fixture.
    # Its deposited paths are checked by the IPW collision pass instead.
    if substrate is not None and not base_is_printed:
        roles.setdefault(substrate.object_id, "substrate")
    for identifier, role in roles.items():
        body = view.body_map.get(identifier)
        if body is None or body.bounds is None:
            raise ValueError(f"collision body has no valid bounds: {identifier}")
        obstacles.append(CollisionBox(identifier, role, body.bounds.minimum, body.bounds.maximum))
    return tuple(obstacles)


def _context_metadata(build, placement, obstacles, report) -> dict[str, Any]:
    return {
        "version": CONTEXT_VERSION,
        "T_build_from_source": build.to_json(),
        "T_workpiece_from_build": placement.to_json(),
        "collision": {
            "check_ipw": True,
            "coordinate_frame": "build",
            "obstacles": [
                {
                    "id": box.obstacle_id,
                    "role": box.role,
                    "minimum_mm": box.minimum_mm,
                    "maximum_mm": box.maximum_mm,
                }
                for box in obstacles
            ],
        },
        "setup_issues": [issue.to_json() for issue in report.issues],
    }


def _model_in_build(model: CadModel, transform: RigidTransform) -> CadModel:
    """Copy topology descriptors and kernel maps without mutating Source CAD."""
    point = transform.transform_point
    native = gp_Trsf()
    native.SetValues(*(value for row in transform.matrix[:3] for value in row))

    def shapes(values):
        return {
            key: BRepBuilderAPI_Transform(shape, native, True).Shape()
            for key, shape in values.items()
        }

    return replace(
        model,
        bodies=[
            replace(
                item,
                bounds=_transformed_bounds(item.bounds, transform),
                centroid=None if item.centroid is None else point(item.centroid),
            )
            for item in model.bodies
        ],
        edges=[_transformed_edge(item, transform) for item in model.edges],
        faces=[_transformed_face(item, transform) for item in model.faces],
        vertices=[replace(item, point=point(item.point)) for item in model.vertices],
        shapes=shapes(model.shapes),
        edge_shapes=shapes(model.edge_shapes),
        face_shapes=shapes(model.face_shapes),
        vertex_shapes=shapes(model.vertex_shapes),
        bounds=_transformed_bounds(model.bounds, transform),
    )


def _transformed_bounds(box: BoundingBox | None, transform: RigidTransform) -> BoundingBox | None:
    if box is None:
        return None
    corners = [
        transform.transform_point(values) for values in product(*zip(box.minimum, box.maximum))
    ]
    return BoundingBox(
        cast(Vector3, tuple(min(p[k] for p in corners) for k in range(3))),
        cast(Vector3, tuple(max(p[k] for p in corners) for k in range(3))),
    )


def _transformed_edge(item: EdgeInfo, transform: RigidTransform) -> EdgeInfo:
    point, vector = transform.transform_point, transform.transform_vector
    return replace(
        item,
        endpoints=None
        if item.endpoints is None
        else (point(item.endpoints[0]), point(item.endpoints[1])),
        center=None if item.center is None else point(item.center),
        arc_length_midpoint=None
        if item.arc_length_midpoint is None
        else point(item.arc_length_midpoint),
        axis_direction=None if item.axis_direction is None else vector(item.axis_direction),
    )


def _transformed_face(item: FaceInfo, transform: RigidTransform) -> FaceInfo:
    point, vector = transform.transform_point, transform.transform_vector
    bounds = _transformed_bounds(item.bounds, transform)
    assert bounds is not None
    return replace(
        item,
        centroid=point(item.centroid),
        bounds=bounds,
        normal=None if item.normal is None else vector(item.normal),
        axis_origin=None if item.axis_origin is None else point(item.axis_origin),
        axis_direction=None if item.axis_direction is None else vector(item.axis_direction),
    )
