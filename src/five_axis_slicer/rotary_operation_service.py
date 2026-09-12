"""Pure creation, configuration, and reference rebinding for Rotary operations."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import cast

from .manufacturing.rotary_parameters import (
    ROTARY_OPERATION_TYPES,
    RotaryGeometrySelection,
    RotaryOperationDefinition,
    RotaryProcessParameters,
)
from .manufacturing.reference_descriptors import geometry_reference
from .manufacturing.references import (
    DEFAULT_REBIND_TOLERANCE,
    RebindTolerance,
    rebind_geometry_reference,
)
from .manufacturing.setup import NodeState
from .models import CadModel, Vector3


_DEFAULT_NAMES = {
    "rotary_spiral": "Rotary Spiral",
    "rotary_thin_wall": "Rotary Thin Wall",
    "rotary_around_part": "Rotary Around Part",
}


def bind_rotary_geometry_references(
    model: CadModel,
    current: RotaryGeometrySelection,
    *,
    axis_edge_id: str,
    surface_face_ids: tuple[str, ...],
    contour_edge_ids: tuple[str, ...] = (),
) -> RotaryGeometrySelection:
    """Bind selected CAD edges/faces and derive a stable rotary frame/profile.

    Surface metadata is used only when the STEP reader identified a cylinder or
    cone.  Explicit values already entered by the user remain the fallback, so
    a selection never silently invents a radius or axis.
    """

    edge = model.edge_map.get(str(axis_edge_id))
    if edge is None or edge.axis_direction is None:
        raise ValueError("rotary.axis_reference_invalid")
    faces = []
    for face_id in surface_face_ids:
        face = model.face_map.get(str(face_id))
        if face is None or face.surface_type not in {"cylinder", "cone"}:
            raise ValueError("rotary.surface_reference_invalid")
        faces.append(face)
    if not faces:
        raise ValueError("rotary.surface_reference_missing")
    for edge_id in contour_edge_ids:
        if str(edge_id) not in model.edge_map:
            raise ValueError("rotary.contour_reference_missing")

    direction = _unit3(edge.axis_direction, "rotary.axis_invalid")
    primary = faces[0]
    if any(face.surface_type != primary.surface_type for face in faces[1:]):
        raise ValueError("rotary.surface_type_mismatch")
    if primary.axis_direction is not None:
        face_direction = _unit3(primary.axis_direction, "rotary.axis_invalid")
        if _dot3(face_direction, direction) < 0.0:
            face_direction = _scale3(face_direction, -1.0)
        if abs(_dot3(face_direction, direction)) < 1.0 - 1.0e-6:
            raise ValueError("rotary.axis_surface_mismatch")
        direction = face_direction
    origin = primary.axis_origin or edge.center
    if origin is None and edge.endpoints is not None:
        origin = _midpoint(edge.endpoints)
    if origin is None:
        raise ValueError("rotary.axis_origin_unresolved")

    for face in faces:
        if face.axis_direction is None or face.axis_origin is None:
            raise ValueError("rotary.surface_axis_unresolved")
        face_direction = _unit3(face.axis_direction, "rotary.axis_invalid")
        if abs(_dot3(face_direction, direction)) < 1.0 - 1.0e-6:
            raise ValueError("rotary.selected_surfaces_not_coaxial")
        origin_delta = tuple(
            value - base
            for value, base in zip(face.axis_origin, origin, strict=True)
        )
        axial_offset = _dot3(origin_delta, direction)
        transverse = tuple(
            value - axial_offset * axis
            for value, axis in zip(origin_delta, direction, strict=True)
        )
        if math.sqrt(_dot3(transverse, transverse)) > 1.0e-5:
            raise ValueError("rotary.selected_surfaces_not_coaxial")

    projection = _dot3(current.frame.zero_direction, direction)
    zero = tuple(
        component - projection * axis
        for component, axis in zip(current.frame.zero_direction, direction, strict=True)
    )
    if math.sqrt(_dot3(zero, zero)) <= 1.0e-12:
        zero = _stable_perpendicular(direction)
    else:
        zero = _unit3(zero, "rotary.zero_direction_invalid")
    surface_axial_values = [
        _axial_coordinate(point, origin, direction)
        for face in faces
        for point in _face_boundary_points(model, face)
    ]
    if not surface_axial_values:
        raise ValueError("rotary.surface_boundary_unresolved")
    surface_start = min(surface_axial_values)
    surface_end = max(surface_axial_values)
    contour_points = [
        point
        for edge_id in contour_edge_ids
        for point in _edge_reference_points(model.edge_map[str(edge_id)])
    ]
    if contour_edge_ids and not contour_points:
        raise ValueError("rotary.contour_reference_unresolved")
    if contour_points:
        contour_axial = [
            _axial_coordinate(point, origin, direction) for point in contour_points
        ]
        axial_start = min(contour_axial)
        axial_end = max(contour_axial)
        if axial_start < surface_start - 1.0e-6 or axial_end > surface_end + 1.0e-6:
            raise ValueError("rotary.contour_outside_surface")
    else:
        axial_start, axial_end = surface_start, surface_end
    if axial_end - axial_start <= 1.0e-9:
        raise ValueError("rotary.profile_axial_range_invalid")
    radius_start = current.profile.radius_start_mm
    radius_end = current.profile.radius_end_mm
    if primary.surface_type == "cylinder":
        radii = [float(face.radius or 0.0) for face in faces]
        if not radii or min(radii) <= 0.0:
            raise ValueError("rotary.radius_invalid")
        if max(radii) - min(radii) > 1.0e-6:
            raise ValueError("rotary.selected_surfaces_radius_mismatch")
        radius_start = radius_end = radii[0]
    elif primary.surface_type == "cone":
        if primary.radius is None or primary.semi_angle_rad is None:
            raise ValueError("rotary.cone_parameters_unresolved")
        primary_axis = _unit3(primary.axis_direction, "rotary.axis_invalid")
        slope = math.tan(float(primary.semi_angle_rad))
        if _dot3(primary_axis, direction) < 0.0:
            slope = -slope
        reference_axial = _axial_coordinate(primary.axis_origin, origin, direction)
        radius_start = float(primary.radius) + (axial_start - reference_axial) * slope
        radius_end = float(primary.radius) + (axial_end - reference_axial) * slope
        if min(radius_start, radius_end) <= 1.0e-9:
            raise ValueError("rotary.cone_apex_degenerate")
        _validate_cone_faces(faces, origin, direction, primary, slope)

    return replace(
        current,
        frame=replace(
            current.frame,
            axis_origin_mm=origin,
            axis_direction=direction,
            zero_direction=zero,
            axis_reference=geometry_reference(model, edge.edge_id, "edge"),
        ),
        profile=replace(
            current.profile,
            axial_start_mm=axial_start,
            axial_end_mm=axial_end,
            radius_start_mm=radius_start,
            radius_end_mm=radius_end,
            contour_references=tuple(
                geometry_reference(model, edge_id, "edge") for edge_id in contour_edge_ids
            ),
            surface_references=tuple(
                geometry_reference(model, face.face_id, "face") for face in faces
            ),
        ),
    )


def create_rotary_operation(
    operations: tuple[RotaryOperationDefinition, ...],
    setup_id: str,
    operation_type: str,
    operation_id: str | None = None,
    name: str | None = None,
) -> RotaryOperationDefinition:
    canonical = str(operation_type).strip().lower()
    if canonical not in ROTARY_OPERATION_TYPES:
        raise ValueError(f"unsupported Rotary operation type: {operation_type!r}")
    identifier = _next_id(operations) if operation_id is None else str(operation_id).strip()
    if not identifier or any(item.operation_id == identifier for item in operations):
        raise ValueError(f"invalid or duplicate operation_id: {identifier!r}")
    return RotaryOperationDefinition(
        operation_id=identifier,
        setup_id=setup_id,
        name=name or _DEFAULT_NAMES.get(canonical, "Rotary Operation"),
        operation_type=canonical,
        state=NodeState.DIRTY,
        dirty_reasons=("operation_created",),
    )


def configure_rotary_operation(
    current: RotaryOperationDefinition,
    *,
    geometry: RotaryGeometrySelection | None = None,
    parameters: RotaryProcessParameters | None = None,
) -> RotaryOperationDefinition:
    updated_geometry = current.geometry if geometry is None else geometry
    updated_parameters = current.parameters if parameters is None else parameters
    if not isinstance(updated_geometry, RotaryGeometrySelection):
        raise TypeError("geometry must be RotaryGeometrySelection")
    if not isinstance(updated_parameters, RotaryProcessParameters):
        raise TypeError("parameters must be RotaryProcessParameters")
    if updated_geometry == current.geometry and updated_parameters == current.parameters:
        return current
    reasons = list(current.dirty_reasons)
    if updated_geometry != current.geometry:
        _append_once(reasons, "operation_geometry_changed")
    if updated_parameters != current.parameters:
        _append_once(reasons, "operation_parameters_changed")
    return replace(
        current,
        geometry=updated_geometry,
        parameters=updated_parameters,
        state=NodeState.DIRTY,
        dirty_reasons=tuple(reasons),
    )


def rebind_rotary_operation_geometry(
    operation: RotaryOperationDefinition,
    source_model: CadModel,
    target_model: CadModel,
    *,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
) -> RotaryOperationDefinition:
    """Rebind every stable reference or return a locatable Invalid operation.

    The geometry contract owns the traversal of its nested frame, profile, and
    angular-region references.  Keeping that traversal next to the domain type
    avoids teaching this lifecycle service each future Rotary region variant.
    """

    try:
        geometry = _rebind_geometry(operation.geometry, source_model, target_model, tolerance)
    except (KeyError, TypeError, ValueError):
        return replace(operation.mark_dirty("geometry_rebind_failed"), state=NodeState.INVALID)
    if geometry is None or not isinstance(geometry, RotaryGeometrySelection):
        return replace(operation.mark_dirty("geometry_rebind_failed"), state=NodeState.INVALID)
    return replace(
        operation.mark_dirty("source_geometry_updated"),
        geometry=geometry,
    )


def _rebind_geometry(
    geometry: RotaryGeometrySelection,
    source_model: CadModel,
    target_model: CadModel,
    tolerance: RebindTolerance,
) -> RotaryGeometrySelection | None:
    frame = geometry.frame
    axis_reference = frame.axis_reference
    if axis_reference is not None:
        axis_reference = _rebound(axis_reference, source_model, target_model, tolerance)
        if axis_reference is None:
            return None
        edge = target_model.edge_map.get(axis_reference.object_id)
        if edge is None or edge.axis_direction is None:
            return None
        direction = cast(Vector3, tuple(float(item) for item in edge.axis_direction))
        if sum(a * b for a, b in zip(direction, frame.axis_direction, strict=True)) < 0.0:
            direction = _scale3(direction, -1.0)
        length = math.sqrt(sum(item * item for item in direction))
        if length <= 1.0e-12:
            return None
        direction = _scale3(direction, 1.0 / length)
        zero_projection = sum(
            a * b for a, b in zip(frame.zero_direction, direction, strict=True)
        )
        zero = tuple(
            value - zero_projection * axis
            for value, axis in zip(frame.zero_direction, direction, strict=True)
        )
        zero_length = math.sqrt(sum(item * item for item in zero))
        if zero_length <= 1.0e-12:
            return None
        zero = cast(Vector3, tuple(item / zero_length for item in zero))
        frame = replace(
            frame,
            axis_reference=axis_reference,
            axis_direction=direction,
            zero_direction=zero,
        )
    contours = tuple(
        _rebound(item, source_model, target_model, tolerance)
        for item in geometry.profile.contour_references
    )
    surfaces = tuple(
        _rebound(item, source_model, target_model, tolerance)
        for item in geometry.profile.surface_references
    )
    if any(item is None for item in (*contours, *surfaces)):
        return None
    profile = replace(
        geometry.profile,
        contour_references=tuple(item for item in contours if item is not None),
        surface_references=tuple(item for item in surfaces if item is not None),
    )
    rebound = replace(geometry, frame=frame, profile=profile)
    if axis_reference is None or not surfaces:
        return rebound
    # Re-run the face-derived axis/profile calculation used by initial
    # binding. An axis-bearing edge may be a cylindrical seam, so its centre
    # must never replace the analytical rotary-axis origin after rebinding.
    return bind_rotary_geometry_references(
        target_model,
        rebound,
        axis_edge_id=axis_reference.object_id,
        contour_edge_ids=tuple(item.object_id for item in contours if item is not None),
        surface_face_ids=tuple(item.object_id for item in surfaces if item is not None),
    )


def _rebound(reference, source_model, target_model, tolerance):
    match = rebind_geometry_reference(
        reference,
        target_model,
        source_model=source_model,
        tolerance=tolerance,
    )
    return match.rebound_reference if match.matched else None


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _unit3(value, code: str) -> Vector3:
    vector = tuple(float(item) for item in value)
    length = math.sqrt(sum(item * item for item in vector))
    if len(vector) != 3 or length <= 1.0e-12:
        raise ValueError(code)
    return cast(Vector3, tuple(item / length for item in vector))


def _dot3(left, right):
    return sum(a * b for a, b in zip(left, right, strict=True))


def _scale3(value: Vector3, factor: float) -> Vector3:
    return cast(Vector3, tuple(item * factor for item in value))


def _midpoint(endpoints: tuple[Vector3, Vector3]) -> Vector3:
    return cast(
        Vector3,
        tuple((a + b) * 0.5 for a, b in zip(*endpoints, strict=True)),
    )


def _stable_perpendicular(direction):
    seed = min(
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        key=lambda item: abs(_dot3(item, direction)),
    )
    projection = _dot3(seed, direction)
    return _unit3(
        tuple(
            value - projection * axis
            for value, axis in zip(seed, direction, strict=True)
        ),
        "rotary.zero_direction_invalid",
    )


def _axial_coordinate(point, origin, direction):
    return _dot3(
        tuple(value - base for value, base in zip(point, origin, strict=True)),
        direction,
    )


def _edge_reference_points(edge):
    points = []
    if edge.endpoints is not None:
        points.extend(edge.endpoints)
    for point in (edge.center, edge.arc_length_midpoint):
        if point is not None:
            points.append(point)
    return tuple(points)


def _face_boundary_points(model: CadModel, face):
    points = [
        point
        for edge_id in face.edge_ids
        if edge_id in model.edge_map
        for point in _edge_reference_points(model.edge_map[edge_id])
    ]
    points.extend(
        model.vertex_map[vertex_id].point
        for edge_id in face.edge_ids
        if edge_id in model.edge_map
        for vertex_id in model.edge_map[edge_id].vertex_ids
        if vertex_id in model.vertex_map
    )
    return tuple(points)


def _validate_cone_faces(faces, origin, direction, primary, primary_slope):
    primary_reference = _axial_coordinate(primary.axis_origin, origin, direction)
    for face in faces:
        if face.radius is None or face.semi_angle_rad is None or face.axis_direction is None:
            raise ValueError("rotary.cone_parameters_unresolved")
        face_axis = _unit3(face.axis_direction, "rotary.axis_invalid")
        face_slope = math.tan(float(face.semi_angle_rad))
        if _dot3(face_axis, direction) < 0.0:
            face_slope = -face_slope
        sample_axial = _axial_coordinate(face.centroid, origin, direction)
        primary_radius = float(primary.radius) + (
            sample_axial - primary_reference
        ) * primary_slope
        face_reference = _axial_coordinate(face.axis_origin, origin, direction)
        face_radius = float(face.radius) + (
            sample_axial - face_reference
        ) * face_slope
        if min(primary_radius, face_radius) <= 1.0e-9:
            raise ValueError("rotary.cone_apex_degenerate")
        if abs(primary_radius - face_radius) > 1.0e-5:
            raise ValueError("rotary.selected_surfaces_radius_mismatch")


def _next_id(operations: tuple[RotaryOperationDefinition, ...]) -> str:
    used = {item.operation_id for item in operations}
    index = 1
    while f"rotary-operation-{index}" in used:
        index += 1
    return f"rotary-operation-{index}"


__all__ = [
    "bind_rotary_geometry_references",
    "configure_rotary_operation",
    "create_rotary_operation",
    "rebind_rotary_operation_geometry",
]
