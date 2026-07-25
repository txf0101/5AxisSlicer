"""Tube-specific validation rules kept outside the workflow state owner."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from .manufacturing.library import ResourceLibraryDiagnostic, ResourceSnapshotAudit
from .manufacturing.machine import MachineProfile
from .manufacturing.references import audit_coordinate_frame_references
from .manufacturing.setup import (
    BUILD_CS_NODE,
    MACHINE_NODE,
    MODEL_CS_NODE,
    OPERATION_NODE,
    PART_NODE,
    PLACEMENT_NODE,
    IssueSeverity,
    ManufacturingSetup,
    NodeState,
    SetupValidationReport,
    TubeOperationDefinition,
    ValidationIssue,
)
from .models import CadModel
from .tube_drafts import BodyCandidate


@dataclass(frozen=True, slots=True)
class TubeValidationContext:
    setup: ManufacturingSetup
    operations: tuple[TubeOperationDefinition, ...]
    body_catalog: Mapping[str, BodyCandidate]
    cad_model: CadModel | None
    draft_nodes: frozenset[str]
    resource_audits: Mapping[str, ResourceSnapshotAudit]
    resource_audit_failures: Mapping[str, str]
    resource_library_diagnostics: tuple[ResourceLibraryDiagnostic, ...]


def validation_report(
    context: TubeValidationContext,
    *,
    operation_type: str,
    operation_limit: int,
) -> SetupValidationReport:
    invalid_nodes, domain_issues = domain_validation(context)
    setup = replace(
        context.setup,
        draft_nodes=context.setup.draft_nodes | context.draft_nodes,
        invalid_nodes=context.setup.invalid_nodes | invalid_nodes,
        issues=merge_issues(context.setup.issues, domain_issues),
    )
    base = setup.validation_report()
    states = dict(base.node_states)
    operation_issues = _operation_issues(
        context,
        states,
        operation_type=operation_type,
        operation_limit=operation_limit,
    )
    issues = merge_issues(base.issues, operation_issues)
    return SetupValidationReport(
        issues=issues,
        node_states=states,
        coordinates_valid=base.coordinates_valid,
        setup_ready=base.setup_ready and not _has_errors(issues),
    )


def domain_validation(
    context: TubeValidationContext,
) -> tuple[frozenset[str], tuple[ValidationIssue, ...]]:
    checks: tuple[tuple[frozenset[str], tuple[ValidationIssue, ...]], ...] = (
        _part_issues(context),
        _coordinate_issues(context),
        _machine_issues(context),
        _placement_issues(context.setup),
        (frozenset(), _resource_issues(context)),
    )
    invalid = frozenset(node for nodes, _issues in checks for node in nodes)
    issues = tuple(issue for _nodes, group in checks for issue in group)
    return invalid, issues


def merge_issues(*groups: Iterable[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    result: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in (item for group in groups for item in group):
        context_key = repr(issue.to_json()["context"])
        key = (issue.code, issue.object_id, context_key)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return tuple(result)


def aggregate_operation_state(
    operations: Sequence[TubeOperationDefinition],
) -> NodeState:
    precedence = {
        NodeState.INVALID: 5,
        NodeState.DRAFT: 4,
        NodeState.DIRTY: 3,
        NodeState.MISSING: 2,
        NodeState.VALID: 1,
    }
    return max((item.state for item in operations), key=precedence.__getitem__)


def resource_node(resource_type: str) -> str:
    try:
        return {
            "machine": MACHINE_NODE,
            "nozzle": "nozzle",
            "material": "material",
        }[resource_type]
    except KeyError as exc:
        raise ValueError(f"unsupported resource type: {resource_type!r}") from exc


def _operation_issues(
    context: TubeValidationContext,
    states: dict[str, NodeState],
    *,
    operation_type: str,
    operation_limit: int,
) -> tuple[ValidationIssue, ...]:
    if not context.operations:
        states[OPERATION_NODE] = NodeState.MISSING
        return (
            ValidationIssue(
                "TUBE_OPERATION_MISSING",
                IssueSeverity.WARNING,
                context.setup.setup_id,
                {"supported_type": operation_type},
            ),
        )
    states[OPERATION_NODE] = aggregate_operation_state(context.operations)
    issues = list(_operation_count_issues(context, operation_limit))
    for operation in context.operations:
        if operation.setup_id == context.setup.setup_id:
            continue
        states[OPERATION_NODE] = NodeState.INVALID
        issues.append(
            ValidationIssue(
                "TUBE_OPERATION_SETUP_MISMATCH",
                IssueSeverity.ERROR,
                operation.operation_id,
                {
                    "operation_setup_id": operation.setup_id,
                    "controller_setup_id": context.setup.setup_id,
                },
            )
        )
    return tuple(issues)


def _operation_count_issues(
    context: TubeValidationContext,
    operation_limit: int,
) -> tuple[ValidationIssue, ...]:
    if len(context.operations) <= operation_limit:
        return ()
    return (
        ValidationIssue(
            "TUBE_OPERATION_COUNT_UNSUPPORTED",
            IssueSeverity.WARNING,
            context.setup.setup_id,
            {"count": len(context.operations), "interactive_limit": operation_limit},
        ),
    )


def _part_issues(
    context: TubeValidationContext,
) -> tuple[frozenset[str], tuple[ValidationIssue, ...]]:
    assignments = context.setup.assignments
    if assignments.has_part and context.cad_model is None:
        issue = ValidationIssue(
            "CAD_MODEL_MISSING",
            IssueSeverity.ERROR,
            context.setup.setup_id,
            {"node": PART_NODE, "part_body_ids": list(assignments.part_body_ids)},
        )
        return frozenset({PART_NODE}), (issue,)
    if not context.body_catalog:
        return frozenset(), ()

    known = set(context.body_catalog)
    referenced = (
        assignments.part_body_ids
        + assignments.ignored_body_ids
        + assignments.fixture_body_ids
        + assignments.unassigned_body_ids
    )
    missing = tuple(item for item in referenced if item not in known)
    ineligible = tuple(
        item
        for item in assignments.part_body_ids
        if item in context.body_catalog and not context.body_catalog[item].is_part_eligible
    )
    part_invalid = bool(set(missing) & set(assignments.part_body_ids) or ineligible)
    invalid = frozenset({PART_NODE}) if part_invalid else frozenset()
    issues = (
        *_missing_body_issues(context, missing),
        *_ineligible_body_issues(context, ineligible),
    )
    return invalid, issues


def _missing_body_issues(
    context: TubeValidationContext,
    body_ids: tuple[str, ...],
) -> tuple[ValidationIssue, ...]:
    if not body_ids:
        return ()
    return (
        ValidationIssue(
            "CAD_BODY_REFERENCE_MISSING",
            IssueSeverity.ERROR,
            context.setup.setup_id,
            {"body_ids": list(body_ids)},
        ),
    )


def _ineligible_body_issues(
    context: TubeValidationContext,
    body_ids: tuple[str, ...],
) -> tuple[ValidationIssue, ...]:
    if not body_ids:
        return ()
    return (
        ValidationIssue(
            "PART_BODY_NOT_SOLID",
            IssueSeverity.ERROR,
            context.setup.setup_id,
            {"body_ids": list(body_ids)},
        ),
    )


def _coordinate_issues(
    context: TubeValidationContext,
) -> tuple[frozenset[str], tuple[ValidationIssue, ...]]:
    if context.cad_model is None:
        return frozenset(), ()
    invalid: set[str] = set()
    issues: list[ValidationIssue] = []
    for node, frame in (
        (MODEL_CS_NODE, context.setup.model_coordinate_system),
        (BUILD_CS_NODE, context.setup.build_coordinate_system),
    ):
        if frame is None:
            continue
        found = audit_coordinate_frame_references(frame, context.cad_model, node=node)
        if found:
            invalid.add(node)
            issues.extend(found)
    return frozenset(invalid), tuple(issues)


def _machine_issues(
    context: TubeValidationContext,
) -> tuple[frozenset[str], tuple[ValidationIssue, ...]]:
    snapshot = context.setup.machine
    if snapshot is None:
        return frozenset(), ()
    try:
        profile = MachineProfile.from_json(snapshot.payload)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        issue = ValidationIssue(
            "MACHINE_PROFILE_INVALID",
            IssueSeverity.ERROR,
            snapshot.resource_id,
            {"detail": str(exc)},
        )
        return frozenset({MACHINE_NODE}), (issue,)
    mount_id = context.setup.mount_datum_id
    if mount_id is None or mount_id in profile.mount_map:
        return frozenset(), ()
    issue = ValidationIssue(
        "PLACEMENT_MOUNT_MISSING",
        IssueSeverity.ERROR,
        mount_id,
        {"machine_id": profile.profile_id},
    )
    return frozenset({PLACEMENT_NODE}), (issue,)


def _placement_issues(
    setup: ManufacturingSetup,
) -> tuple[frozenset[str], tuple[ValidationIssue, ...]]:
    mount_id = setup.mount_datum_id
    placement = setup.T_mount_from_build
    if mount_id is None or placement is None:
        return frozenset(), ()
    if placement.source_frame == "build" and placement.target_frame == mount_id:
        return frozenset(), ()
    issue = ValidationIssue(
        "PLACEMENT_FRAME_MISMATCH",
        IssueSeverity.ERROR,
        mount_id,
        {
            "expected_source_frame": "build",
            "actual_source_frame": placement.source_frame,
            "expected_target_frame": mount_id,
            "actual_target_frame": placement.target_frame,
        },
    )
    return frozenset({PLACEMENT_NODE}), (issue,)


def _resource_issues(context: TubeValidationContext) -> tuple[ValidationIssue, ...]:
    issues = [
        issue
        for kind, audit in context.resource_audits.items()
        if (issue := _resource_audit_issue(kind, audit)) is not None
    ]
    issues.extend(
        _resource_audit_failure(context, kind, detail)
        for kind, detail in context.resource_audit_failures.items()
    )
    issues.extend(_resource_diagnostic_issue(item) for item in context.resource_library_diagnostics)
    return tuple(issues)


def _resource_audit_issue(
    kind: str,
    audit: ResourceSnapshotAudit,
) -> ValidationIssue | None:
    if audit.status == "match":
        return None
    code = (
        "RESOURCE_LIBRARY_DIVERGED"
        if audit.status == "diverged"
        else "RESOURCE_LIBRARY_ENTRY_MISSING"
    )
    return ValidationIssue(
        code,
        IssueSeverity.WARNING,
        audit.resource_id,
        {
            "node": resource_node(kind),
            "resource_type": kind,
            "library_status": audit.status,
            "snapshot_content_hash": audit.snapshot_content_hash,
            "library_content_hash": audit.library_content_hash,
            "snapshot_retained": True,
        },
    )


def _resource_audit_failure(
    context: TubeValidationContext,
    kind: str,
    detail: str,
) -> ValidationIssue:
    snapshot = getattr(context.setup, kind)
    return ValidationIssue(
        "RESOURCE_LIBRARY_AUDIT_FAILED",
        IssueSeverity.WARNING,
        context.setup.setup_id if snapshot is None else snapshot.resource_id,
        {
            "node": resource_node(kind),
            "resource_type": kind,
            "detail": detail,
            "snapshot_retained": True,
        },
    )


def _resource_diagnostic_issue(
    diagnostic: ResourceLibraryDiagnostic,
) -> ValidationIssue:
    return ValidationIssue(
        "RESOURCE_LIBRARY_ENTRY_INVALID",
        IssueSeverity.WARNING,
        diagnostic.resource_id or diagnostic.entry_name,
        {
            "node": resource_node(diagnostic.resource_type),
            **diagnostic.to_json(),
        },
    )


def _has_errors(issues: Iterable[ValidationIssue]) -> bool:
    return any(issue.severity is IssueSeverity.ERROR for issue in issues)


__all__ = [
    "TubeValidationContext",
    "aggregate_operation_state",
    "domain_validation",
    "merge_issues",
    "resource_node",
    "validation_report",
]
