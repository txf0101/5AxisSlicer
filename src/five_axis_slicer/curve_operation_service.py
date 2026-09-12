"""Pure operation creation, configuration and reference rebinding for Curve."""

from __future__ import annotations

from dataclasses import replace

from .manufacturing.curve_parameters import (
    CURVE_OPERATION_TYPES,
    CurveGeometrySelection,
    CurveOperationDefinition,
    CurveProcessParameters,
    DirectedEdgeReference,
)
from .manufacturing.references import (
    DEFAULT_REBIND_TOLERANCE,
    RebindTolerance,
    rebind_geometry_reference,
)
from .manufacturing.setup import NodeState
from .models import CadModel


def create_curve_operation(
    operations: tuple[CurveOperationDefinition, ...],
    setup_id: str,
    operation_type: str,
    operation_id: str | None = None,
    name: str | None = None,
) -> CurveOperationDefinition:
    canonical = str(operation_type).strip().lower()
    if canonical not in CURVE_OPERATION_TYPES:
        raise ValueError(f"unsupported Curve operation type: {operation_type!r}")
    identifier = _next_id(operations) if operation_id is None else str(operation_id).strip()
    if not identifier or any(item.operation_id == identifier for item in operations):
        raise ValueError(f"invalid or duplicate operation_id: {identifier!r}")
    return CurveOperationDefinition(
        identifier,
        setup_id,
        name
        or {
            "curve_buildup": "Curve Buildup",
            "curve_multi_pass": "Curve Multi-pass Buildup",
            "curve_offset_buildup": "Curve Offset Buildup",
        }[canonical],
        canonical,
        NodeState.DIRTY,
        ("operation_created",),
    )


def configure_curve_operation(
    current: CurveOperationDefinition,
    model: CadModel,
    *,
    edge_ids: tuple[str, ...],
    reversed_flags: tuple[bool, ...] | None = None,
    normal_mode: str = "adjacent_face",
    normal_face_id: str | None = None,
    specified_normal: tuple[float, float, float] | None = None,
    parameters: CurveProcessParameters | None = None,
) -> CurveOperationDefinition:
    if not edge_ids:
        raise ValueError("Curve operation requires at least one edge")
    flags = reversed_flags or tuple(False for _ in edge_ids)
    if len(flags) != len(edge_ids):
        raise ValueError("reversed_flags must match edge_ids")
    directed = tuple(
        DirectedEdgeReference(
            _geometry_reference(model, edge_id, "edge"),
            bool(reversed_flag),
        )
        for edge_id, reversed_flag in zip(edge_ids, flags, strict=True)
    )
    mode = str(normal_mode).strip().lower()
    face_id = normal_face_id
    if mode == "adjacent_face" and face_id is None:
        common = set(model.edge_map[edge_ids[0]].face_ids)
        for edge_id in edge_ids[1:]:
            common.intersection_update(model.edge_map[edge_id].face_ids)
        if len(common) > 1:
            raise ValueError("curve.normal_ambiguous: choose one adjacent face")
        if not common:
            raise ValueError("curve.normal_missing: selected chain has no common adjacent face")
        face_id = next(iter(common))
    face = None if face_id is None else _geometry_reference(model, face_id, "face")
    geometry = CurveGeometrySelection(directed, mode, face, specified_normal)
    updated_parameters = current.parameters if parameters is None else parameters
    if geometry == current.geometry and updated_parameters == current.parameters:
        return current
    reasons = list(current.dirty_reasons)
    if geometry != current.geometry and "operation_geometry_changed" not in reasons:
        reasons.append("operation_geometry_changed")
    if updated_parameters != current.parameters and "operation_parameters_changed" not in reasons:
        reasons.append("operation_parameters_changed")
    return replace(
        current,
        geometry=geometry,
        parameters=updated_parameters,
        state=NodeState.DIRTY,
        dirty_reasons=tuple(reasons),
    )


def rebind_curve_operation_geometry(
    operation: CurveOperationDefinition,
    source_model: CadModel,
    target_model: CadModel,
    *,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
) -> CurveOperationDefinition:
    rebound_edges = []
    for selected in operation.geometry.edges:
        match = rebind_geometry_reference(
            selected.edge, target_model, source_model=source_model, tolerance=tolerance
        )
        if not match.matched or match.rebound_reference is None:
            return replace(operation.mark_dirty("geometry_rebind_failed"), state=NodeState.INVALID)
        rebound_edges.append(DirectedEdgeReference(match.rebound_reference, selected.reversed))
    face = operation.geometry.normal_face
    rebound_face = None
    if face is not None:
        match = rebind_geometry_reference(
            face, target_model, source_model=source_model, tolerance=tolerance
        )
        if not match.matched or match.rebound_reference is None:
            return replace(operation.mark_dirty("geometry_rebind_failed"), state=NodeState.INVALID)
        rebound_face = match.rebound_reference
    geometry = replace(
        operation.geometry,
        edges=tuple(rebound_edges),
        normal_face=rebound_face,
    )
    return replace(operation.mark_dirty("source_geometry_updated"), geometry=geometry)


def _geometry_reference(model: CadModel, object_id: str, geometry_type: str):
    from .manufacturing.references import geometry_reference

    return geometry_reference(model, object_id, geometry_type)


def _next_id(operations: tuple[CurveOperationDefinition, ...]) -> str:
    used = {item.operation_id for item in operations}
    index = 1
    while f"curve-operation-{index}" in used:
        index += 1
    return f"curve-operation-{index}"


__all__ = [
    "configure_curve_operation",
    "create_curve_operation",
    "rebind_curve_operation_geometry",
]
