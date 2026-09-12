"""Qt-free presentation and pick resolution for the Tube Setup page.

All geometry entering this module is expressed in Source CS millimetres.  The
viewer matrix maps Source CS into the active display frame and preserves the
right-handed basis used by manufacturing transforms.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    PointReference,
    RigidTransform,
)
from .manufacturing.references import project_point_to_face
from .manufacturing.setup import BUILD_CS_NODE, MODEL_CS_NODE
from .models import (
    BuildSurfaceOverlay,
    CadModel,
    CoordinateFrameOverlay,
    PickHit,
)
from .tube_controller import DraftNotFoundError, TubeSetupController

IDENTITY_MATRIX = RigidTransform.identity().matrix
GeometryResolver = Callable[[str], GeometryReference]


@dataclass(frozen=True, slots=True)
class ViewerPresentation:
    model_matrix: tuple[tuple[float, float, float, float], ...]
    coordinate_frames: tuple[CoordinateFrameOverlay, ...]
    active_frame_id: str | None
    build_surface: BuildSurfaceOverlay | None


def reference_display_value(
    controller: TubeSetupController,
    node: str,
    reference: PointReference | DirectionReference,
) -> tuple[float, float, float]:
    """Return numeric editor values in the node's documented input frame."""

    if isinstance(reference, PointReference):
        value = reference.resolved_point
        is_point = True
    else:
        value = reference.direction_in_source or reference.resolved_direction
        is_point = False
    if node != BUILD_CS_NODE or reference.reference_type != "numeric":
        return value
    model = controller.setup.model_coordinate_system
    if model is None or not model.is_valid:
        return value
    transform = model.T_target_from_source
    return transform.transform_point(value) if is_point else transform.transform_vector(value)


def viewer_presentation(
    controller: TubeSetupController,
    *,
    has_model: bool,
    view_mode: str,
    active_coordinate_node: str,
) -> ViewerPresentation:
    if not has_model:
        return ViewerPresentation(IDENTITY_MATRIX, (), None, None)
    transform = _display_transform(controller, view_mode)
    overlays = _coordinate_overlays(controller, transform)
    if view_mode == "machine":
        overlays.append(
            CoordinateFrameOverlay("machine", "Machine CS", (0.0, 0.0, 0.0), scale=24.0)
        )
    active = (
        "machine"
        if view_mode == "machine"
        else "build"
        if active_coordinate_node == BUILD_CS_NODE
        else "model"
    )
    surface = _machine_surface_overlay(controller) if view_mode == "machine" else None
    matrix = IDENTITY_MATRIX if transform is None else transform.matrix
    return ViewerPresentation(matrix, tuple(overlays), active, surface)


def resolve_origin_pick(
    model: CadModel,
    hit: PickHit,
    requested_kind: str,
    geometry: GeometryReference,
) -> PointReference:
    if hit.kind == "vertex":
        return PointReference("vertex", model.vertex_map[hit.entity_id].point, geometry=geometry)
    if hit.kind == "face" and hit.position_source is not None:
        face_point = project_point_to_face(model, hit.entity_id, hit.position_source)
        return PointReference("face_pick", face_point, geometry=geometry)
    if hit.kind != "edge":
        raise ValueError("unsupported origin pick")
    edge = model.edge_map[hit.entity_id]
    kind = (
        requested_kind
        if requested_kind in {"circle_center", "ellipse_center", "arc_midpoint"}
        else "arc_midpoint"
    )
    edge_point = edge.center if kind.endswith("center") else edge.arc_length_midpoint
    if edge_point is None:
        raise ValueError("the selected edge does not provide this origin reference")
    return PointReference(kind, edge_point, geometry=geometry)


def resolve_direction_pick(
    model: CadModel,
    hit: PickHit,
    requested_kind: str,
    geometry: GeometryReference,
    *,
    first_vertex_hit: PickHit | None = None,
    geometry_resolver: GeometryResolver,
) -> DirectionReference:
    if requested_kind == "pick_two_vertices":
        if first_vertex_hit is None:
            raise ValueError("two-point direction requires the first vertex")
        first_id = first_vertex_hit.entity_id
        return DirectionReference(
            "two_points",
            geometry=geometry_resolver(first_id),
            secondary_geometry=geometry,
            first_point_in_source_mm=model.vertex_map[first_id].point,
            second_point_in_source_mm=model.vertex_map[hit.entity_id].point,
        )
    if hit.kind == "edge":
        edge = model.edge_map[hit.entity_id]
        if edge.curve_type != "line" or edge.axis_direction is None:
            raise ValueError("direction picking requires a straight edge")
        return DirectionReference("line_edge", edge.axis_direction, geometry=geometry)
    if hit.kind == "face":
        kind, direction = _face_direction(model, hit.entity_id)
        return DirectionReference(kind, direction, geometry=geometry)
    raise ValueError("unsupported direction pick")


def _face_direction(
    model: CadModel,
    face_id: str,
) -> tuple[str, tuple[float, float, float]]:
    face = model.face_map[face_id]
    if face.surface_type == "plane" and face.normal is not None:
        return "plane_normal", face.normal
    if face.surface_type in {"cylinder", "cone"} and face.axis_direction is not None:
        return "surface_axis", face.axis_direction
    raise ValueError("direction picking requires a plane, cylinder, or cone")


def _display_transform(
    controller: TubeSetupController,
    view_mode: str,
) -> RigidTransform | None:
    if view_mode != "machine":
        return None
    draft = _draft_machine_from_source(controller)
    if draft is not None:
        return draft
    try:
        return controller.T_machine_from_source()
    except ValueError:
        return None


def _coordinate_overlays(
    controller: TubeSetupController,
    transform: RigidTransform | None,
) -> list[CoordinateFrameOverlay]:
    overlays = [
        _display_overlay(frame, transform)
        for frame in (
            controller.setup.model_coordinate_system,
            controller.setup.build_coordinate_system,
        )
        if frame is not None
    ]
    for node in (MODEL_CS_NODE, BUILD_CS_NODE):
        draft_frame = _draft_frame(controller, node)
        if draft_frame is not None:
            overlays.append(_display_overlay(draft_frame, transform))
    return overlays


def _draft_frame(
    controller: TubeSetupController,
    node: str,
) -> CoordinateFrameDefinition | None:
    try:
        draft = controller.coordinate_draft(node)
        if not draft.is_complete:
            return None
        assert draft.origin_reference is not None
        assert draft.z_direction_reference is not None
        assert draft.x_direction_reference is not None
        return CoordinateFrameDefinition.from_references(
            f"{draft.frame_id}-draft",
            f"{draft.name} Draft",
            draft.origin_reference,
            draft.z_direction_reference,
            draft.x_direction_reference,
        )
    except (DraftNotFoundError, TypeError, ValueError):
        return None


def _display_overlay(
    frame: CoordinateFrameDefinition,
    transform: RigidTransform | None,
) -> CoordinateFrameOverlay:
    overlay = _overlay_from_frame(frame)
    return overlay if transform is None else _transform_overlay(overlay, transform)


def _machine_surface_overlay(
    controller: TubeSetupController,
) -> BuildSurfaceOverlay | None:
    setup = controller.setup
    mount_id = setup.mount_datum_id
    try:
        draft = controller.placement_draft()
        mount_id = draft.mount_datum_id or mount_id
    except DraftNotFoundError:
        pass
    if setup.machine is None or mount_id is None:
        return None
    try:
        profile = controller.machine_profile()
        mount = profile.mount_map[mount_id]
        surface = profile.build_surface_map[mount.build_surface_id]
        transform = profile.mount_transform(mount.mount_id)
    except (KeyError, ValueError):
        return None
    rotation = transform.rotation
    return BuildSurfaceOverlay(
        surface.surface_id,
        surface.shape,
        origin=transform.translation,
        x_axis=(rotation[0][0], rotation[1][0], rotation[2][0]),
        y_axis=(rotation[0][1], rotation[1][1], rotation[2][1]),
        width_mm=surface.width_mm,
        depth_mm=surface.depth_mm,
        diameter_mm=surface.diameter_mm,
    )


def _draft_machine_from_source(
    controller: TubeSetupController,
) -> RigidTransform | None:
    setup = controller.setup
    build = setup.build_coordinate_system
    machine = setup.machine
    if build is None or not build.is_valid or machine is None:
        return None
    try:
        draft = controller.placement_draft()
    except DraftNotFoundError:
        return None
    mount_id = draft.mount_datum_id
    dependencies_match = (
        draft.is_complete
        and mount_id is not None
        and draft.build_cs_revision == build.revision
        and draft.machine_content_hash == machine.content_hash
    )
    if not dependencies_match:
        return None
    try:
        assert mount_id is not None
        machine_from_mount = controller.machine_profile().mount_transform(mount_id)
        return machine_from_mount @ draft.T_mount_from_build @ build.T_target_from_source
    except (KeyError, TypeError, ValueError):
        return None


def _overlay_from_frame(frame: CoordinateFrameDefinition) -> CoordinateFrameOverlay:
    transform = frame.T_target_from_source.inverse()
    return CoordinateFrameOverlay(
        frame.frame_id,
        frame.name,
        transform.transform_point((0.0, 0.0, 0.0)),
        transform.transform_vector((1.0, 0.0, 0.0)),
        transform.transform_vector((0.0, 1.0, 0.0)),
        transform.transform_vector((0.0, 0.0, 1.0)),
        scale=20.0,
    )


def _transform_overlay(
    overlay: CoordinateFrameOverlay,
    transform: RigidTransform,
) -> CoordinateFrameOverlay:
    return CoordinateFrameOverlay(
        overlay.frame_id,
        overlay.name,
        transform.transform_point(overlay.origin),
        x_axis=transform.transform_vector(overlay.x_axis),
        y_axis=transform.transform_vector(overlay.y_axis),
        z_axis=transform.transform_vector(overlay.z_axis),
        scale=overlay.scale,
        visible=overlay.visible,
    )


__all__ = [
    "IDENTITY_MATRIX",
    "ViewerPresentation",
    "reference_display_value",
    "resolve_direction_pick",
    "resolve_origin_pick",
    "viewer_presentation",
]
