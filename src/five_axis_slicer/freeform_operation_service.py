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
    return FreeformOperationDefinition(
        identifier,
        setup_id,
        name or ("Freeform Thin Wall" if canonical == "freeform_thin_wall" else "Freeform Surface"),
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


def _next_id(operations):
    used = {item.operation_id for item in operations}
    index = 1
    while f"freeform-operation-{index}" in used:
        index += 1
    return f"freeform-operation-{index}"


__all__ = [
    "configure_freeform_operation",
    "create_freeform_operation",
    "rebind_freeform_operation_geometry",
]
