"""Pure helpers for Tube operation creation, configuration, and rebinding."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace

from .manufacturing.coordinates import GeometryReference
from .manufacturing.references import RebindTolerance, rebind_geometry_reference
from .manufacturing.setup import NodeState, TubeOperationDefinition
from .manufacturing.tube_parameters import TubeGeometrySelection, TubeProcessParameters
from .models import CadModel
from .tube_drafts import BodyRole, OperationLimitError

ReferenceBuilder = Callable[[str, str], GeometryReference]


class TubeOperationControllerMixin:
    """Controller-side mutation wrapper kept outside the large Setup controller."""

    _operations: tuple[TubeOperationDefinition, ...]
    _modified: bool

    def geometry_reference(self, object_id: str, geometry_type: str) -> GeometryReference:
        raise NotImplementedError

    def configure_operation(
        self,
        *,
        operation_id: str | None = None,
        tube_body_id: str,
        entry_port_id: str,
        exit_port_id: str,
        substrate_body_id: str,
        manual_centerline_edge_ids: Iterable[str] = (),
        parameters: TubeProcessParameters | None = None,
    ) -> TubeOperationDefinition:
        current = _operation_by_id(self._operations, operation_id)
        updated = configure_tube_operation(
            current,
            self.geometry_reference,
            tube_body_id=tube_body_id,
            entry_port_id=entry_port_id,
            exit_port_id=exit_port_id,
            substrate_body_id=substrate_body_id,
            manual_centerline_edge_ids=manual_centerline_edge_ids,
            parameters=parameters,
        )
        if updated != current:
            self._operations = tuple(
                updated if item.operation_id == current.operation_id else item
                for item in self._operations
            )
            self._modified = True
            marker = getattr(self, "_mark_product_stale", None)
            if callable(marker):
                marker(updated)
        return updated


def group_body_roles(roles: Mapping[str, BodyRole | str]) -> dict[BodyRole, tuple[str, ...]]:
    if not isinstance(roles, Mapping):
        raise TypeError("roles must be a mapping")
    grouped: dict[BodyRole, list[str]] = {role: [] for role in BodyRole}
    for raw_id, raw_role in roles.items():
        body_id = str(raw_id).strip()
        try:
            role = raw_role if isinstance(raw_role, BodyRole) else BodyRole(str(raw_role))
        except ValueError as exc:
            raise ValueError(f"unsupported body role: {raw_role!r}") from exc
        grouped[role].append(body_id)
    return {role: tuple(values) for role, values in grouped.items()}


def create_tube_operation(
    operations: tuple[TubeOperationDefinition, ...],
    setup_id: str,
    operation_type: str,
    operation_id: str | None,
    name: str,
    *,
    available_types: tuple[str, ...],
    operation_limit: int,
) -> TubeOperationDefinition:
    canonical_type = str(operation_type).strip().lower()
    if canonical_type not in available_types:
        raise ValueError(f"unsupported Tube operation type: {operation_type!r}")
    if len(operations) >= operation_limit:
        raise OperationLimitError(
            f"the Tube workbench supports at most {operation_limit} interactive operations"
        )
    identifier = (
        _next_operation_id(operations) if operation_id is None else str(operation_id).strip()
    )
    if not identifier:
        raise ValueError("operation_id must not be empty")
    if any(item.operation_id == identifier for item in operations):
        raise ValueError(f"duplicate operation_id: {identifier}")
    return TubeOperationDefinition(
        operation_id=identifier,
        setup_id=setup_id,
        name=name,
        operation_type=canonical_type,
        state=NodeState.DIRTY,
        dirty_reasons=("operation_created",),
    )


def configure_tube_operation(
    current: TubeOperationDefinition,
    reference_builder: ReferenceBuilder,
    *,
    tube_body_id: str,
    entry_port_id: str,
    exit_port_id: str,
    substrate_body_id: str,
    manual_centerline_edge_ids: Iterable[str],
    parameters: TubeProcessParameters | None,
) -> TubeOperationDefinition:
    body = reference_builder(tube_body_id, "body")
    substrate = reference_builder(substrate_body_id, "body")
    entry = reference_builder(entry_port_id, "edge")
    exit_port = reference_builder(exit_port_id, "edge")
    if entry.parent_body_id != body.object_id or exit_port.parent_body_id != body.object_id:
        raise ValueError("entry_port and exit_port must belong to tube_body")
    manual_edges = tuple(
        reference_builder(identifier, "edge") for identifier in manual_centerline_edge_ids
    )
    geometry = TubeGeometrySelection(body, entry, exit_port, substrate, manual_edges)
    updated_parameters = current.parameters if parameters is None else parameters
    reasons = current.dirty_reasons
    if geometry != current.geometry and "operation_geometry_changed" not in reasons:
        reasons += ("operation_geometry_changed",)
    if updated_parameters != current.parameters and "operation_parameters_changed" not in reasons:
        reasons += ("operation_parameters_changed",)
    return replace(
        current,
        geometry=geometry,
        parameters=updated_parameters,
        state=NodeState.DIRTY,
        dirty_reasons=reasons,
    )


def rebind_operation_geometry(
    operations: tuple[TubeOperationDefinition, ...],
    source_model: CadModel,
    target_model: CadModel,
    *,
    tolerance: RebindTolerance,
) -> tuple[TubeOperationDefinition, ...]:
    return tuple(
        _rebind_one_operation(operation, source_model, target_model, tolerance)
        for operation in operations
    )


def _rebind_one_operation(
    operation: TubeOperationDefinition,
    source_model: CadModel,
    target_model: CadModel,
    tolerance: RebindTolerance,
) -> TubeOperationDefinition:
    references = (
        operation.geometry.tube_body,
        operation.geometry.entry_port,
        operation.geometry.exit_port,
        operation.geometry.substrate_body,
        *operation.geometry.manual_centerline_edges,
    )
    if not any(references):
        return operation
    matches = tuple(
        None
        if reference is None
        else rebind_geometry_reference(
            reference,
            target_model,
            source_model=source_model,
            tolerance=tolerance,
        )
        for reference in references
    )
    if any(item is not None and not item.matched for item in matches):
        return replace(operation.mark_dirty("geometry_rebind_failed"), state=NodeState.INVALID)
    resolved = tuple(None if item is None else item.rebound_reference for item in matches)
    return replace(
        operation.mark_dirty("source_geometry_updated"),
        geometry=TubeGeometrySelection(
            resolved[0],
            resolved[1],
            resolved[2],
            resolved[3],
            tuple(item for item in resolved[4:] if item is not None),
        ),
    )


def _next_operation_id(operations: tuple[TubeOperationDefinition, ...]) -> str:
    used = {item.operation_id for item in operations}
    index = 1
    while f"tube-operation-{index}" in used:
        index += 1
    return f"tube-operation-{index}"


def _operation_by_id(
    operations: tuple[TubeOperationDefinition, ...],
    operation_id: str | None,
) -> TubeOperationDefinition:
    if operation_id is None:
        if len(operations) == 1:
            return operations[0]
        raise ValueError("operation_id is required when more than one Tube operation exists")
    identifier = str(operation_id).strip()
    for operation in operations:
        if operation.operation_id == identifier:
            return operation
    raise ValueError(f"unknown operation_id: {identifier}")


__all__ = [
    "TubeOperationControllerMixin",
    "configure_tube_operation",
    "create_tube_operation",
    "group_body_roles",
    "rebind_operation_geometry",
]
