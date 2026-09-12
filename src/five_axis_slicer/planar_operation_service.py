"""Pure Planar-operation creation, configuration, and geometry rebinding."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from .manufacturing.coordinates import GeometryReference
from .manufacturing.planar_parameters import (
    PlanarGeometrySelection,
    PlanarOperationDefinition,
    PlanarProcessParameters,
)
from .manufacturing.references import (
    DEFAULT_REBIND_TOLERANCE,
    RebindTolerance,
    rebind_geometry_reference,
)
from .manufacturing.setup import NodeState
from .models import CadModel

ReferenceBuilder = Callable[[str, str], GeometryReference]
PLANAR_OPERATION_TYPES = frozenset(
    {
        "planar_region",
        "planar_zigzag",
        "planar_offset",
        "planar_thin_wall",
        "planar_spiral",
        "planar_support",
    }
)


def create_planar_operation(
    operations: tuple[PlanarOperationDefinition, ...],
    setup_id: str,
    operation_type: str = "planar_region",
    operation_id: str | None = None,
    name: str = "Planar Region",
) -> PlanarOperationDefinition:
    """Create an unconfigured operation, preserving stable operation identities."""

    _require_operations(operations)
    canonical_type = str(operation_type).strip().lower()
    if canonical_type not in PLANAR_OPERATION_TYPES:
        raise ValueError(f"unsupported Planar operation type: {operation_type!r}")
    identifier = (
        _next_operation_id(operations) if operation_id is None else str(operation_id).strip()
    )
    if not identifier:
        raise ValueError("operation_id must not be empty")
    if any(item.operation_id == identifier for item in operations):
        raise ValueError(f"duplicate operation_id: {identifier}")
    return PlanarOperationDefinition(
        operation_id=identifier,
        setup_id=setup_id,
        name=name,
        operation_type=canonical_type,
        state=NodeState.DIRTY,
        dirty_reasons=("operation_created",),
    )


def configure_planar_operation(
    current: PlanarOperationDefinition,
    reference_builder: ReferenceBuilder,
    *,
    body_id: str,
    parameters: PlanarProcessParameters | None = None,
) -> PlanarOperationDefinition:
    """Bind a stable body reference and mark a changed operation dirty."""

    if not isinstance(current, PlanarOperationDefinition):
        raise TypeError("current must be PlanarOperationDefinition")
    body = reference_builder(body_id, "body")
    geometry = PlanarGeometrySelection(body)
    updated_parameters = current.parameters if parameters is None else parameters
    if not isinstance(updated_parameters, PlanarProcessParameters):
        raise TypeError("parameters must be PlanarProcessParameters")
    if geometry == current.geometry and updated_parameters == current.parameters:
        return current
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


def rebind_planar_operation_geometry(
    operation: PlanarOperationDefinition,
    source_model: CadModel,
    target_model: CadModel,
    *,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
) -> PlanarOperationDefinition:
    """Rebind the selected body uniquely; unresolved geometry makes it invalid."""

    if not isinstance(operation, PlanarOperationDefinition):
        raise TypeError("operation must be PlanarOperationDefinition")
    body = operation.geometry.body
    if body is None:
        return operation
    match = rebind_geometry_reference(
        body, target_model, source_model=source_model, tolerance=tolerance
    )
    if not match.matched or match.rebound_reference is None:
        return replace(operation.mark_dirty("geometry_rebind_failed"), state=NodeState.INVALID)
    if match.rebound_reference == body:
        return operation
    return replace(
        operation.mark_dirty("source_geometry_updated"),
        geometry=PlanarGeometrySelection(match.rebound_reference),
    )


def _require_operations(operations: tuple[PlanarOperationDefinition, ...]) -> None:
    if any(not isinstance(item, PlanarOperationDefinition) for item in operations):
        raise TypeError("operations must contain PlanarOperationDefinition")


def _next_operation_id(operations: tuple[PlanarOperationDefinition, ...]) -> str:
    used = {item.operation_id for item in operations}
    index = 1
    while f"planar-operation-{index}" in used:
        index += 1
    return f"planar-operation-{index}"


__all__ = [
    "PLANAR_OPERATION_TYPES",
    "configure_planar_operation",
    "create_planar_operation",
    "rebind_planar_operation_geometry",
]
