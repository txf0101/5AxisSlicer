"""Audit persisted coordinate references against authoritative CAD topology."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..models import CadModel
from .coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
)
from .reference_descriptors import (
    CadDescriptorIndex,
    align_direction,
    rebound_two_point,
    require_cad_model,
    resolve_direction,
    resolve_point,
    subtract,
)
from .reference_rebind import deduplicate_issues
from .setup import (
    BUILD_CS_NODE,
    MODEL_CS_NODE,
    IssueSeverity,
    ValidationIssue,
)


@dataclass(slots=True)
class _AuditContext:
    frame: CoordinateFrameDefinition
    model: CadModel
    node: str
    index: CadDescriptorIndex
    issues: list[ValidationIssue] = field(default_factory=list)

    def authoritative(
        self,
        reference: GeometryReference | None,
        *,
        component: str,
        role: str,
    ) -> GeometryReference | None:
        if reference is None:
            return None
        try:
            authoritative = self.index.reference(reference.object_id, reference.geometry_type)
        except KeyError:
            return self._recover_reference(reference, component, role)
        except ValueError as exc:
            self.issues.append(
                _coordinate_audit_issue(
                    "COORDINATE_GEOMETRY_REFERENCE_MISMATCH",
                    self.frame,
                    self.node,
                    component,
                    role,
                    reference,
                    {"mismatch_fields": ["geometry_type"], "detail": str(exc)},
                )
            )
            return None
        mismatch_fields = _reference_mismatches(reference, authoritative)
        if mismatch_fields:
            self.issues.append(
                _coordinate_audit_issue(
                    "COORDINATE_GEOMETRY_REFERENCE_MISMATCH",
                    self.frame,
                    self.node,
                    component,
                    role,
                    reference,
                    {"mismatch_fields": mismatch_fields},
                )
            )
        return authoritative

    def _recover_reference(
        self,
        reference: GeometryReference,
        component: str,
        role: str,
    ) -> GeometryReference | None:
        try:
            located = self.index.reference(reference.object_id)
        except (KeyError, ValueError):
            self.issues.append(
                _coordinate_audit_issue(
                    "COORDINATE_GEOMETRY_REFERENCE_MISSING",
                    self.frame,
                    self.node,
                    component,
                    role,
                    reference,
                    {"reason": "object_not_found"},
                )
            )
            return None
        self.issues.append(
            _coordinate_audit_issue(
                "COORDINATE_GEOMETRY_REFERENCE_MISMATCH",
                self.frame,
                self.node,
                component,
                role,
                reference,
                {
                    "mismatch_fields": ["geometry_type"],
                    "actual_geometry_type": located.geometry_type,
                },
            )
        )
        return located


def audit_coordinate_frame_references(
    frame: CoordinateFrameDefinition,
    model: CadModel,
    *,
    node: str = MODEL_CS_NODE,
) -> tuple[ValidationIssue, ...]:
    """Audit stored Source CS/mm values after authoritative CAD is available."""

    if not isinstance(frame, CoordinateFrameDefinition):
        raise TypeError("frame must be CoordinateFrameDefinition")
    require_cad_model(model)
    if node not in {MODEL_CS_NODE, BUILD_CS_NODE}:
        raise ValueError(f"unsupported coordinate node: {node!r}")
    context = _AuditContext(frame, model, node, CadDescriptorIndex(model))
    _audit_origin(context)
    _audit_direction(context, "z", frame.z_direction_reference)
    _audit_direction(context, "x", frame.x_direction_reference)
    return deduplicate_issues(context.issues)


def _audit_origin(context: _AuditContext) -> None:
    reference = context.frame.origin_reference
    if reference.reference_type == "numeric":
        return
    authoritative = context.authoritative(reference.geometry, component="origin", role="primary")
    if authoritative is None:
        return
    try:
        resolved = resolve_point(reference, authoritative, context.model, source_model=None)
    except (KeyError, TypeError, ValueError) as exc:
        context.issues.append(
            _coordinate_resolved_issue(
                "COORDINATE_RESOLVED_POINT_MISMATCH",
                context.frame,
                context.node,
                "origin",
                "point_in_source_mm",
                reference.geometry,
                expected=None,
                actual=reference.point_in_source_mm,
                detail=str(exc),
            )
        )
        return
    _append_value_mismatch(
        context,
        "COORDINATE_RESOLVED_POINT_MISMATCH",
        "origin",
        "point_in_source_mm",
        reference.geometry,
        resolved,
        reference.point_in_source_mm,
    )


def _audit_direction(
    context: _AuditContext,
    component: str,
    reference: DirectionReference,
) -> None:
    if reference.reference_type == "numeric":
        return
    primary = context.authoritative(reference.geometry, component=component, role="primary")
    secondary = context.authoritative(
        reference.secondary_geometry, component=component, role="secondary"
    )
    if reference.reference_type == "two_points":
        _audit_two_point_direction(context, component, reference, primary, secondary)
        return
    if primary is None:
        return
    try:
        resolved = resolve_direction(reference.reference_type, primary, context.model)
        resolved = align_direction(resolved, reference.direction_in_source)
    except (KeyError, TypeError, ValueError) as exc:
        context.issues.append(
            _coordinate_resolved_issue(
                "COORDINATE_RESOLVED_DIRECTION_MISMATCH",
                context.frame,
                context.node,
                component,
                "direction_in_source",
                reference.geometry,
                expected=None,
                actual=reference.direction_in_source,
                detail=str(exc),
            )
        )
        return
    _append_value_mismatch(
        context,
        "COORDINATE_RESOLVED_DIRECTION_MISMATCH",
        component,
        "direction_in_source",
        reference.geometry,
        resolved,
        reference.direction_in_source,
    )


def _audit_two_point_direction(
    context: _AuditContext,
    component: str,
    reference: DirectionReference,
    primary: GeometryReference | None,
    secondary: GeometryReference | None,
) -> None:
    try:
        first = rebound_two_point(
            reference.first_point_in_source_mm, reference.geometry, primary, context.model
        )
        second = rebound_two_point(
            reference.second_point_in_source_mm,
            reference.secondary_geometry,
            secondary,
            context.model,
        )
    except (KeyError, TypeError, ValueError) as exc:
        context.issues.append(
            _coordinate_resolved_issue(
                "COORDINATE_RESOLVED_DIRECTION_MISMATCH",
                context.frame,
                context.node,
                component,
                "two_points",
                reference.geometry,
                expected=None,
                actual=reference.direction_in_source,
                detail=str(exc),
            )
        )
        return
    _audit_two_point_values(context, component, reference, first, second)


def _audit_two_point_values(
    context: _AuditContext,
    component: str,
    reference: DirectionReference,
    first: Sequence[float] | None,
    second: Sequence[float] | None,
) -> None:
    _append_geometry_value_mismatch(
        context,
        component,
        "first_point_in_source_mm",
        reference.geometry,
        first,
        reference.first_point_in_source_mm,
    )
    _append_geometry_value_mismatch(
        context,
        component,
        "second_point_in_source_mm",
        reference.secondary_geometry,
        second,
        reference.second_point_in_source_mm,
    )
    if first is None or second is None:
        return
    _append_value_mismatch(
        context,
        "COORDINATE_RESOLVED_DIRECTION_MISMATCH",
        component,
        "direction_in_source",
        reference.geometry,
        subtract(second, first),
        reference.direction_in_source,
    )


def _append_geometry_value_mismatch(
    context: _AuditContext,
    component: str,
    field_name: str,
    geometry: GeometryReference | None,
    expected: Sequence[float] | None,
    actual: Sequence[float] | None,
) -> None:
    if geometry is None or expected is None:
        return
    _append_value_mismatch(
        context,
        "COORDINATE_RESOLVED_POINT_MISMATCH",
        component,
        field_name,
        geometry,
        expected,
        actual,
    )


def _append_value_mismatch(
    context: _AuditContext,
    code: str,
    component: str,
    field_name: str,
    reference: GeometryReference | None,
    expected: Sequence[float] | None,
    actual: Sequence[float] | None,
) -> None:
    if _same_vector(expected, actual):
        return
    context.issues.append(
        _coordinate_resolved_issue(
            code,
            context.frame,
            context.node,
            component,
            field_name,
            reference,
            expected=expected,
            actual=actual,
        )
    )


def _reference_mismatches(
    reference: GeometryReference,
    authoritative: GeometryReference,
) -> list[str]:
    result: list[str] = []
    if reference.geometry_type != authoritative.geometry_type:
        result.append("geometry_type")
    if reference.parent_body_id != authoritative.parent_body_id:
        result.append("parent_body_id")
    if reference.signature != authoritative.signature:
        result.append("signature")
    return result


def _coordinate_audit_issue(
    code: str,
    frame: CoordinateFrameDefinition,
    node: str,
    component: str,
    role: str,
    reference: GeometryReference,
    extra_context: Mapping[str, Any],
) -> ValidationIssue:
    return ValidationIssue(
        code,
        IssueSeverity.ERROR,
        reference.object_id,
        {
            "node": node,
            "frame_id": frame.frame_id,
            "component": component,
            "reference_role": role,
            "geometry_type": reference.geometry_type,
            "parent_body_id": reference.parent_body_id,
            **extra_context,
        },
    )


def _coordinate_resolved_issue(
    code: str,
    frame: CoordinateFrameDefinition,
    node: str,
    component: str,
    field_name: str,
    reference: GeometryReference | None,
    *,
    expected: Sequence[float] | None,
    actual: Sequence[float] | None,
    detail: str | None = None,
) -> ValidationIssue:
    context: dict[str, Any] = {
        "node": node,
        "frame_id": frame.frame_id,
        "component": component,
        "field": field_name,
        "reference_type": _frame_reference_type(frame, component),
        "expected": None if expected is None else list(expected),
        "actual": None if actual is None else list(actual),
    }
    if detail:
        context["detail"] = detail
    object_id = frame.frame_id if reference is None else reference.object_id
    return ValidationIssue(code, IssueSeverity.ERROR, object_id, context)


def _frame_reference_type(frame: CoordinateFrameDefinition, component: str) -> str:
    if component == "origin":
        return frame.origin_reference.reference_type
    if component == "z":
        return frame.z_direction_reference.reference_type
    return frame.x_direction_reference.reference_type


def _same_vector(
    expected: Sequence[float] | None,
    actual: Sequence[float] | None,
) -> bool:
    if expected is None or actual is None:
        return expected is actual
    return len(expected) == len(actual) and all(
        float(left) == float(right) for left, right in zip(expected, actual, strict=False)
    )
