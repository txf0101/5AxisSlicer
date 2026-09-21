"""Pure creation, configuration and rebinding for restricted Freeform."""

from __future__ import annotations

from dataclasses import replace

from .manufacturing.curve_parameters import CurveGeometrySelection, DirectedEdgeReference
from .manufacturing.freeform_parameters import (
    FREEFORM_OPERATION_TYPES,
    FreeformGeometrySelection,
    FreeformOperationDefinition,
    FreeformProcessParameters,
)
from .manufacturing.freeform_solid_parameters import (
    SOLID_FILL_OPERATION_TYPES,
    RadialSolidBladeGeometry,
    RadialSolidGeometrySelection,
    SolidFillProcessParameters,
    SphericalSolidGeometrySelection,
    SurfaceSolidBodyGeometry,
    SurfaceSolidGeometrySelection,
)
from .manufacturing.material_plan import MaterialPlan
from .manufacturing.reference_descriptors import geometry_reference
from .manufacturing.reference_rebind import DEFAULT_REBIND_TOLERANCE, RebindTolerance
from .manufacturing.references import rebind_geometry_reference
from .manufacturing.setup import NodeState
from .models import CadModel


def create_freeform_operation(
    operations: tuple[FreeformOperationDefinition, ...],
    setup_id: str,
    operation_type: str = "freeform_surface",
    operation_id: str | None = None,
    name: str | None = None,
) -> FreeformOperationDefinition:
    canonical = str(operation_type).strip().lower()
    if canonical not in FREEFORM_OPERATION_TYPES:
        raise ValueError(f"unsupported Freeform operation type: {operation_type}")
    identifier = operation_id or _next_id(operations)
    if any(item.operation_id == identifier for item in operations):
        raise ValueError(f"duplicate operation_id: {identifier}")
    labels = {
        "freeform_surface": "Freeform Surface",
        "freeform_thin_wall": "Freeform Thin Wall",
        "spherical_solid_fill": "Spherical Solid Fill",
        "surface_solid_fill": "Surface Solid Fill",
        "radial_solid_fill": "Radial Solid Fill",
    }
    return FreeformOperationDefinition(
        identifier,
        setup_id,
        name or labels[canonical],
        canonical,
        NodeState.DIRTY,
        ("operation_created",),
    )


def configure_freeform_operation(
    current: FreeformOperationDefinition,
    model: CadModel,
    *,
    face_ids: tuple[str, ...],
    guides: tuple[dict[str, object], ...],
    parameters: FreeformProcessParameters | None = None,
    material_plan: MaterialPlan | None = None,
) -> FreeformOperationDefinition:
    if not face_ids or not guides:
        raise ValueError("Freeform requires selected faces and guides")
    faces = tuple(geometry_reference(model, face_id, "face") for face_id in face_ids)
    guide_values = []
    for item in guides:
        raw_edge_ids = item.get("edge_ids", ())
        if not isinstance(raw_edge_ids, (list, tuple)):
            raise ValueError("guide edge_ids must be an array")
        edge_ids = tuple(str(value) for value in raw_edge_ids)
        if not edge_ids:
            raise ValueError("each Freeform guide requires edge_ids")
        raw_flags = item.get("reversed_flags", (False,) * len(edge_ids))
        if not isinstance(raw_flags, (list, tuple)):
            raise ValueError("guide reversed_flags must be an array")
        flags = tuple(bool(value) for value in raw_flags)
        if len(flags) != len(edge_ids):
            raise ValueError("guide reversed_flags must match edge_ids")
        face_id = str(item.get("face_id", ""))
        if face_id not in face_ids:
            raise ValueError("guide face_id must be selected")
        guide_values.append(
            CurveGeometrySelection(
                tuple(
                    DirectedEdgeReference(geometry_reference(model, edge_id, "edge"), flag)
                    for edge_id, flag in zip(edge_ids, flags, strict=True)
                ),
                "adjacent_face",
                geometry_reference(model, face_id, "face"),
            )
        )
    geometry = FreeformGeometrySelection(faces, tuple(guide_values))
    updated = replace(
        current,
        geometry=geometry,
        parameters=current.parameters if parameters is None else parameters,
        material_plan=material_plan,
        state=NodeState.DIRTY,
        dirty_reasons=tuple(
            dict.fromkeys((*current.dirty_reasons, "operation_configuration_changed"))
        ),
    )
    return updated


def configure_freeform_solid_operation(
    current: FreeformOperationDefinition,
    model: CadModel,
    *,
    geometry: dict[str, object],
    parameters: SolidFillProcessParameters | None = None,
    material_plan: MaterialPlan | None = None,
) -> FreeformOperationDefinition:
    if current.operation_type not in SOLID_FILL_OPERATION_TYPES:
        raise ValueError("solid geometry requires a solid-fill Freeform operation")
    selection = _solid_geometry_selection(current.operation_type, model, geometry)
    return replace(
        current,
        solid_geometry=selection,
        solid_parameters=current.solid_parameters if parameters is None else parameters,
        material_plan=material_plan,
        state=NodeState.DIRTY,
        dirty_reasons=tuple(
            dict.fromkeys((*current.dirty_reasons, "operation_configuration_changed"))
        ),
    )


def rebind_freeform_operation_geometry(
    operation: FreeformOperationDefinition,
    source_model: CadModel,
    target_model: CadModel,
    *,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
) -> FreeformOperationDefinition:
    def rebound(reference):
        match = rebind_geometry_reference(
            reference, target_model, source_model=source_model, tolerance=tolerance
        )
        if not match.matched or match.rebound_reference is None:
            raise ValueError("freeform.geometry_rebind_failed")
        return match.rebound_reference

    try:
        if operation.operation_type in SOLID_FILL_OPERATION_TYPES:
            return replace(
                operation.mark_dirty("source_geometry_updated"),
                solid_geometry=_rebind_solid_geometry(operation.solid_geometry, rebound),
            )
        faces = tuple(rebound(item) for item in operation.geometry.faces)
        guides = tuple(
            replace(
                guide,
                edges=tuple(
                    DirectedEdgeReference(rebound(item.edge), item.reversed) for item in guide.edges
                ),
                normal_face=rebound(guide.normal_face),
            )
            for guide in operation.geometry.guides
        )
    except ValueError:
        return replace(operation.mark_dirty("geometry_rebind_failed"), state=NodeState.INVALID)
    return replace(
        operation.mark_dirty("source_geometry_updated"),
        geometry=FreeformGeometrySelection(faces, guides),
    )


def _solid_geometry_selection(operation_type, model, payload):
    if not isinstance(payload, dict):
        raise ValueError("solid_geometry must be an object")
    if operation_type == "spherical_solid_fill":
        body_ids = _string_tuple(payload.get("body_ids"), "body_ids")
        return SphericalSolidGeometrySelection(
            tuple(geometry_reference(model, item, "body") for item in body_ids),
            tuple(payload.get("center_mm", (0.0, 0.0, 0.0))),
            _optional_body_reference(model, payload.get("substrate_body_id")),
        )
    if operation_type == "surface_solid_fill":
        return SurfaceSolidGeometrySelection(
            tuple(_surface_body_geometry(model, item) for item in _mapping_tuple(payload, "bodies")),
            _optional_body_reference(model, payload.get("substrate_body_id")),
        )
    if operation_type == "radial_solid_fill":
        hub_id = str(payload.get("hub_body_id", "")).strip()
        if not hub_id:
            raise ValueError("hub_body_id is required")
        return RadialSolidGeometrySelection(
            geometry_reference(model, hub_id, "body"),
            tuple(_radial_blade_geometry(model, item) for item in _mapping_tuple(payload, "blades")),
            tuple(payload.get("axis_origin_mm", (0.0, 0.0, 0.0))),
            tuple(payload.get("axis_direction", (0.0, 0.0, 1.0))),
            _optional_body_reference(model, payload.get("substrate_body_id")),
        )
    raise ValueError(f"unsupported solid-fill operation: {operation_type}")


def _surface_body_geometry(model, payload):
    body_id = _required_id(payload, "body_id")
    result = SurfaceSolidBodyGeometry(
        geometry_reference(model, body_id, "body"),
        geometry_reference(model, _required_id(payload, "surface_face_id"), "face"),
        geometry_reference(model, _required_id(payload, "opposite_face_id"), "face"),
        geometry_reference(model, _required_id(payload, "root_edge_id"), "edge"),
    )
    _require_parent(result.surface_face, body_id)
    _require_parent(result.opposite_face, body_id)
    _require_parent(result.root_edge, body_id)
    return result


def _radial_blade_geometry(model, payload):
    body_id = _required_id(payload, "body_id")
    result = RadialSolidBladeGeometry(
        geometry_reference(model, body_id, "body"),
        geometry_reference(model, _required_id(payload, "root_face_id"), "face"),
        geometry_reference(model, _required_id(payload, "outer_face_id"), "face"),
    )
    _require_parent(result.root_face, body_id)
    _require_parent(result.outer_face, body_id)
    return result


def _rebind_solid_geometry(selection, rebound):
    if selection is None:
        return None
    if isinstance(selection, SphericalSolidGeometrySelection):
        return SphericalSolidGeometrySelection(
            tuple(rebound(item) for item in selection.bodies),
            selection.center_mm,
            None if selection.substrate_body is None else rebound(selection.substrate_body),
        )
    if isinstance(selection, SurfaceSolidGeometrySelection):
        return SurfaceSolidGeometrySelection(
            tuple(
                SurfaceSolidBodyGeometry(
                    rebound(item.body),
                    rebound(item.surface_face),
                    rebound(item.opposite_face),
                    rebound(item.root_edge),
                )
                for item in selection.bodies
            ),
            None if selection.substrate_body is None else rebound(selection.substrate_body),
        )
    return RadialSolidGeometrySelection(
        rebound(selection.hub_body),
        tuple(
            RadialSolidBladeGeometry(
                rebound(item.body), rebound(item.root_face), rebound(item.outer_face)
            )
            for item in selection.blades
        ),
        selection.axis_origin_mm,
        selection.axis_direction,
        None if selection.substrate_body is None else rebound(selection.substrate_body),
    )


def _optional_body_reference(model, value):
    if value is None or not str(value).strip():
        return None
    return geometry_reference(model, str(value).strip(), "body")


def _mapping_tuple(payload, name):
    value = payload.get(name)
    if not isinstance(value, (list, tuple)) or not value or any(
        not isinstance(item, dict) for item in value
    ):
        raise ValueError(f"{name} must be a non-empty array of objects")
    return tuple(value)


def _string_tuple(value, name):
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be an array")
    result = tuple(str(item).strip() for item in value)
    if not result or any(not item for item in result):
        raise ValueError(f"{name} must contain non-empty IDs")
    return result


def _required_id(payload, name):
    result = str(payload.get(name, "")).strip()
    if not result:
        raise ValueError(f"{name} is required")
    return result


def _require_parent(reference, body_id):
    if reference.parent_body_id != body_id:
        raise ValueError(f"{reference.object_id} does not belong to {body_id}")


def _next_id(operations):
    used = {item.operation_id for item in operations}
    index = 1
    while f"freeform-operation-{index}" in used:
        index += 1
    return f"freeform-operation-{index}"


__all__ = [
    "configure_freeform_operation",
    "configure_freeform_solid_operation",
    "create_freeform_operation",
    "rebind_freeform_operation_geometry",
]
