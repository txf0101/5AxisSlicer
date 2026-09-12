"""Tolerance-based unique rebinding for persisted manufacturing references."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Any

from ..models import CadModel
from .coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    PointReference,
)
from .reference_descriptors import (
    REFERENCE_SIGNATURE_SCHEMA_VERSION,
    CadDescriptorIndex,
    align_direction,
    entity_id,
    rebound_two_point,
    require_cad_model,
    resolve_direction,
    resolve_point,
    subtract,
)
from .setup import (
    BUILD_CS_NODE,
    MODEL_CS_NODE,
    PART_NODE,
    IssueSeverity,
    ManufacturingObjectAssignments,
    ValidationIssue,
)


class RebindStatus(str, Enum):
    MATCHED = "matched"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    INVALID_SIGNATURE = "invalid_signature"


@dataclass(frozen=True, slots=True)
class RebindTolerance:
    """Explicit Source CS/mm tolerances used for unique geometric matching."""

    length_mm: float = 1.0e-5
    area_mm2: float = 1.0e-5
    volume_mm3: float = 1.0e-5
    angle_rad: float = 1.0e-8
    direction: float = 1.0e-8
    relative: float = 1.0e-8

    def __post_init__(self) -> None:
        for name in (
            "length_mm",
            "area_mm2",
            "volume_mm3",
            "angle_rad",
            "direction",
            "relative",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be a finite non-negative number")
            object.__setattr__(self, name, value)

    def to_json(self) -> dict[str, float]:
        return {
            "length_mm": self.length_mm,
            "area_mm2": self.area_mm2,
            "volume_mm3": self.volume_mm3,
            "angle_rad": self.angle_rad,
            "direction": self.direction,
            "relative": self.relative,
        }


DEFAULT_REBIND_TOLERANCE = RebindTolerance()


@dataclass(frozen=True, slots=True)
class CandidateAudit:
    candidate_id: str
    mismatch_fields: tuple[str, ...] = ()

    @property
    def matched(self) -> bool:
        return not self.mismatch_fields

    def to_json(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "matched": self.matched,
            "mismatch_fields": list(self.mismatch_fields),
        }


@dataclass(frozen=True, slots=True)
class GeometryRebindResult:
    original_reference: GeometryReference
    status: RebindStatus
    rebound_reference: GeometryReference | None = None
    audits: tuple[CandidateAudit, ...] = ()
    issue: ValidationIssue | None = None

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(audit.candidate_id for audit in self.audits if audit.matched)

    @property
    def matched(self) -> bool:
        return self.status is RebindStatus.MATCHED and self.rebound_reference is not None


@dataclass(frozen=True, slots=True)
class PointReferenceRebindResult:
    reference: PointReference | None
    matches: tuple[GeometryRebindResult, ...] = ()
    issues: tuple[ValidationIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class DirectionReferenceRebindResult:
    reference: DirectionReference | None
    matches: tuple[GeometryRebindResult, ...] = ()
    issues: tuple[ValidationIssue, ...] = ()


@dataclass(frozen=True, slots=True)
class CoordinateFrameRebindResult:
    original_frame: CoordinateFrameDefinition
    rebound_frame: CoordinateFrameDefinition | None
    matches: tuple[GeometryRebindResult, ...] = ()
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def matched(self) -> bool:
        return self.rebound_frame is not None and not self.issues


@dataclass(frozen=True, slots=True)
class BodyAssignmentRebindResult:
    assignments: ManufacturingObjectAssignments
    bindings: Mapping[str, str] = field(default_factory=dict, hash=False)
    invalid_nodes: frozenset[str] = field(default_factory=frozenset)
    issues: tuple[ValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", MappingProxyType(dict(self.bindings)))


@dataclass(frozen=True, slots=True)
class CadModelRebindResult:
    assignments: ManufacturingObjectAssignments
    model_coordinate_system: CoordinateFrameDefinition | None
    build_coordinate_system: CoordinateFrameDefinition | None
    body_bindings: Mapping[str, str] = field(default_factory=dict, hash=False)
    invalid_nodes: frozenset[str] = field(default_factory=frozenset)
    issues: tuple[ValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "body_bindings", MappingProxyType(dict(self.body_bindings)))


@dataclass(slots=True)
class _AssignmentBinder:
    source: CadDescriptorIndex
    target: CadDescriptorIndex
    tolerance: RebindTolerance
    bindings: dict[str, str] = field(default_factory=dict)
    issues: list[ValidationIssue] = field(default_factory=list)
    invalid_nodes: set[str] = field(default_factory=set)
    occupied_targets: set[str] = field(default_factory=set)

    def bind_group(
        self,
        identifiers: Sequence[str],
        role: str,
        *,
        preserve_failed: bool,
    ) -> tuple[str, ...]:
        result: list[str] = []
        for body_id in identifiers:
            target_id = self.bind(body_id, role)
            if target_id is not None:
                result.append(target_id)
            elif preserve_failed:
                result.append(body_id)
        return tuple(result)

    def bind(self, body_id: str, role: str) -> str | None:
        source_body = self.source.body_map.get(body_id)
        if source_body is None:
            self._source_missing(body_id, role)
            return None
        geometry_type = "body" if source_body.is_solid else "shell"
        match = rebind_geometry_reference(
            self.source.reference(body_id, geometry_type),
            self.target.model,
            tolerance=self.tolerance,
            _source_index=self.source,
            _target_index=self.target,
        )
        if not match.matched or match.rebound_reference is None:
            self._match_failed(body_id, role, geometry_type, match)
            return None
        target_id = match.rebound_reference.object_id
        if target_id in self.occupied_targets:
            self._target_collision(body_id, role, target_id)
            return None
        self.occupied_targets.add(target_id)
        self.bindings[body_id] = target_id
        return target_id

    def _source_missing(self, body_id: str, role: str) -> None:
        severity = IssueSeverity.ERROR if role == "part" else IssueSeverity.WARNING
        self.issues.append(
            ValidationIssue(
                "BODY_REFERENCE_REBIND_SOURCE_MISSING",
                severity,
                body_id,
                {"role": role, "reason": "source_body_descriptor_unavailable"},
            )
        )
        self._invalidate_part(role)

    def _match_failed(
        self,
        body_id: str,
        role: str,
        geometry_type: str,
        match: GeometryRebindResult,
    ) -> None:
        code = _body_match_issue_code(role, match.status)
        severity = IssueSeverity.ERROR if role == "part" else IssueSeverity.WARNING
        self.issues.append(
            ValidationIssue(
                code,
                severity,
                body_id,
                {
                    "role": role,
                    "candidate_ids": list(match.candidate_ids),
                    "geometry_type": geometry_type,
                },
            )
        )
        self._invalidate_part(role)

    def _target_collision(self, body_id: str, role: str, target_id: str) -> None:
        self.issues.append(
            ValidationIssue(
                "BODY_REFERENCE_REBIND_TARGET_COLLISION",
                IssueSeverity.ERROR,
                body_id,
                {"role": role, "target_body_id": target_id},
            )
        )
        self._invalidate_part(role)

    def _invalidate_part(self, role: str) -> None:
        if role == "part":
            self.invalid_nodes.add(PART_NODE)


def rebind_geometry_reference(
    reference: GeometryReference,
    target_model: CadModel,
    *,
    source_model: CadModel | None = None,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
    _source_index: CadDescriptorIndex | None = None,
    _target_index: CadDescriptorIndex | None = None,
) -> GeometryRebindResult:
    """Accept a target only when one candidate matches within tolerance."""

    _validate_rebind_input(reference, target_model, tolerance)
    source_index = _source_index or (
        None if source_model is None else CadDescriptorIndex(source_model)
    )
    target_index = _target_index or CadDescriptorIndex(target_model)
    stable = _upgrade_reference(reference, source_model, source_index)
    if not _is_supported_signature(stable.signature, stable.geometry_type):
        issue = _reference_issue(
            "GEOMETRY_REFERENCE_REBIND_INVALID_SIGNATURE",
            stable,
            (),
            reason="signature_schema_unsupported",
        )
        return GeometryRebindResult(reference, RebindStatus.INVALID_SIGNATURE, issue=issue)
    audits = _candidate_audits(stable, target_index, tolerance)
    return _geometry_match_result(reference, stable, target_index, audits)


def rebind_point_reference(
    reference: PointReference,
    target_model: CadModel,
    *,
    source_model: CadModel | None = None,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
    _source_index: CadDescriptorIndex | None = None,
    _target_index: CadDescriptorIndex | None = None,
) -> PointReferenceRebindResult:
    if not isinstance(reference, PointReference):
        raise TypeError("reference must be PointReference")
    if reference.reference_type == "numeric":
        return PointReferenceRebindResult(reference)
    assert reference.geometry is not None
    match = rebind_geometry_reference(
        reference.geometry,
        target_model,
        source_model=source_model,
        tolerance=tolerance,
        _source_index=_source_index,
        _target_index=_target_index,
    )
    if not match.matched or match.rebound_reference is None:
        return PointReferenceRebindResult(None, (match,), _issues(match.issue))
    try:
        point = resolve_point(
            reference, match.rebound_reference, target_model, source_model=source_model
        )
        rebound = replace(reference, point_in_source_mm=point, geometry=match.rebound_reference)
    except (KeyError, TypeError, ValueError):
        issue = ValidationIssue(
            "POINT_REFERENCE_REBIND_UNRESOLVED",
            IssueSeverity.ERROR,
            reference.geometry.object_id,
            {
                "reference_type": reference.reference_type,
                "target_object_id": match.rebound_reference.object_id,
            },
        )
        return PointReferenceRebindResult(None, (match,), (issue,))
    return PointReferenceRebindResult(rebound, (match,))


def rebind_direction_reference(
    reference: DirectionReference,
    target_model: CadModel,
    *,
    source_model: CadModel | None = None,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
    _source_index: CadDescriptorIndex | None = None,
    _target_index: CadDescriptorIndex | None = None,
) -> DirectionReferenceRebindResult:
    if not isinstance(reference, DirectionReference):
        raise TypeError("reference must be DirectionReference")
    if reference.reference_type == "numeric":
        return DirectionReferenceRebindResult(reference)
    primary = _optional_match(
        reference.geometry, target_model, source_model, tolerance, _source_index, _target_index
    )
    secondary = _optional_match(
        reference.secondary_geometry,
        target_model,
        source_model,
        tolerance,
        _source_index,
        _target_index,
    )
    matches = tuple(item for item in (primary, secondary) if item is not None)
    issues = deduplicate_issues(
        item.issue for item in matches if not item.matched and item.issue is not None
    )
    if issues:
        return DirectionReferenceRebindResult(None, matches, issues)
    try:
        rebound = _rebuild_direction_reference(reference, primary, secondary, target_model)
    except (KeyError, TypeError, ValueError):
        object_id = "" if reference.geometry is None else reference.geometry.object_id
        issue = ValidationIssue(
            "DIRECTION_REFERENCE_REBIND_UNRESOLVED",
            IssueSeverity.ERROR,
            object_id,
            {"reference_type": reference.reference_type},
        )
        return DirectionReferenceRebindResult(None, matches, (issue,))
    return DirectionReferenceRebindResult(rebound, matches)


def rebind_coordinate_frame(
    frame: CoordinateFrameDefinition,
    target_model: CadModel,
    *,
    source_model: CadModel | None = None,
    node: str = MODEL_CS_NODE,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
    _source_index: CadDescriptorIndex | None = None,
    _target_index: CadDescriptorIndex | None = None,
) -> CoordinateFrameRebindResult:
    if not isinstance(frame, CoordinateFrameDefinition):
        raise TypeError("frame must be CoordinateFrameDefinition")
    _validate_coordinate_node(node)
    options = source_model, tolerance, _source_index, _target_index
    origin = rebind_point_reference(
        frame.origin_reference,
        target_model,
        source_model=options[0],
        tolerance=options[1],
        _source_index=options[2],
        _target_index=options[3],
    )
    z_axis = _rebind_frame_direction(frame.z_direction_reference, target_model, options)
    x_axis = _rebind_frame_direction(frame.x_direction_reference, target_model, options)
    matches = _deduplicate_matches((*origin.matches, *z_axis.matches, *x_axis.matches))
    issues = deduplicate_issues((*origin.issues, *z_axis.issues, *x_axis.issues))
    if issues or origin.reference is None or z_axis.reference is None or x_axis.reference is None:
        return CoordinateFrameRebindResult(frame, None, matches, issues)
    return _build_rebound_frame(
        frame, node, origin.reference, z_axis.reference, x_axis.reference, matches
    )


def rebind_body_assignments(
    assignments: ManufacturingObjectAssignments,
    source_model: CadModel,
    target_model: CadModel,
    *,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
    _source_index: CadDescriptorIndex | None = None,
    _target_index: CadDescriptorIndex | None = None,
) -> BodyAssignmentRebindResult:
    if not isinstance(assignments, ManufacturingObjectAssignments):
        raise TypeError("assignments must be ManufacturingObjectAssignments")
    require_cad_model(source_model)
    require_cad_model(target_model)
    binder = _AssignmentBinder(
        _source_index or CadDescriptorIndex(source_model),
        _target_index or CadDescriptorIndex(target_model),
        tolerance,
    )
    part = binder.bind_group(assignments.part_body_ids, "part", preserve_failed=True)
    ignored = binder.bind_group(assignments.ignored_body_ids, "ignore", preserve_failed=False)
    fixture = binder.bind_group(assignments.fixture_body_ids, "fixture", preserve_failed=True)
    previous = binder.bind_group(
        assignments.unassigned_body_ids, "unassigned", preserve_failed=False
    )
    represented = set((*part, *ignored, *fixture))
    new_ids = (
        body.body_id
        for body in target_model.bodies
        if body.body_id not in binder.occupied_targets and body.body_id not in represented
    )
    rebound = ManufacturingObjectAssignments(
        part_body_ids=part,
        ignored_body_ids=ignored,
        fixture_body_ids=fixture,
        unassigned_body_ids=_unique((*previous, *new_ids)),
    )
    return BodyAssignmentRebindResult(
        rebound,
        binder.bindings,
        frozenset(binder.invalid_nodes),
        deduplicate_issues(binder.issues),
    )


def rebind_cad_model_state(
    source_model: CadModel,
    target_model: CadModel,
    assignments: ManufacturingObjectAssignments,
    model_coordinate_system: CoordinateFrameDefinition | None,
    build_coordinate_system: CoordinateFrameDefinition | None,
    *,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
) -> CadModelRebindResult:
    source_index = CadDescriptorIndex(source_model)
    target_index = CadDescriptorIndex(target_model)
    bodies = rebind_body_assignments(
        assignments,
        source_model,
        target_model,
        tolerance=tolerance,
        _source_index=source_index,
        _target_index=target_index,
    )
    rebound_model, rebound_build, frame_nodes, frame_issues = _rebind_frames(
        source_model,
        target_model,
        model_coordinate_system,
        build_coordinate_system,
        tolerance,
        source_index,
        target_index,
    )
    return CadModelRebindResult(
        bodies.assignments,
        rebound_model,
        rebound_build,
        bodies.bindings,
        frozenset((*bodies.invalid_nodes, *frame_nodes)),
        deduplicate_issues((*bodies.issues, *frame_issues)),
    )


def deduplicate_issues(issues: Iterable[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    result: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = issue.code, issue.object_id, repr(issue.to_json()["context"])
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return tuple(result)


def _validate_rebind_input(
    reference: GeometryReference,
    target_model: CadModel,
    tolerance: RebindTolerance,
) -> None:
    if not isinstance(reference, GeometryReference):
        raise TypeError("reference must be GeometryReference")
    require_cad_model(target_model)
    if not isinstance(tolerance, RebindTolerance):
        raise TypeError("tolerance must be RebindTolerance")


def _candidate_audits(
    reference: GeometryReference,
    target: CadDescriptorIndex,
    tolerance: RebindTolerance,
) -> tuple[CandidateAudit, ...]:
    result: list[CandidateAudit] = []
    for candidate in target.entities(reference.geometry_type):
        candidate_reference = target.reference(
            entity_id(reference.geometry_type, candidate), reference.geometry_type
        )
        mismatches = _signature_mismatches(
            reference.signature, candidate_reference.signature, tolerance
        )
        result.append(CandidateAudit(candidate_reference.object_id, mismatches))
    return tuple(result)


def _geometry_match_result(
    original: GeometryReference,
    stable: GeometryReference,
    target: CadDescriptorIndex,
    audits: tuple[CandidateAudit, ...],
) -> GeometryRebindResult:
    matched_ids = tuple(audit.candidate_id for audit in audits if audit.matched)
    if len(matched_ids) == 1:
        rebound = target.reference(matched_ids[0], stable.geometry_type)
        return GeometryRebindResult(original, RebindStatus.MATCHED, rebound, audits)
    status = RebindStatus.MISSING if not matched_ids else RebindStatus.AMBIGUOUS
    code = (
        "GEOMETRY_REFERENCE_REBIND_MISSING"
        if status is RebindStatus.MISSING
        else "GEOMETRY_REFERENCE_REBIND_AMBIGUOUS"
    )
    reason = (
        "no_geometric_match" if status is RebindStatus.MISSING else "multiple_geometric_matches"
    )
    issue = _reference_issue(code, stable, matched_ids, reason=reason)
    return GeometryRebindResult(original, status, audits=audits, issue=issue)


def _upgrade_reference(
    reference: GeometryReference,
    source_model: CadModel | None,
    source_index: CadDescriptorIndex | None,
) -> GeometryReference:
    if (
        _is_supported_signature(reference.signature, reference.geometry_type)
        or source_model is None
    ):
        return reference
    try:
        return (source_index or CadDescriptorIndex(source_model)).reference(
            reference.object_id, reference.geometry_type
        )
    except (KeyError, ValueError):
        return reference


def _is_supported_signature(signature: Mapping[str, Any], geometry_type: str) -> bool:
    try:
        return bool(
            int(signature.get("schema_version", -1)) == REFERENCE_SIGNATURE_SCHEMA_VERSION
            and str(signature.get("geometry_type", "")) == geometry_type
            and isinstance(signature.get("descriptor"), Mapping)
        )
    except (TypeError, ValueError):
        return False


def _signature_mismatches(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    tolerance: RebindTolerance,
) -> tuple[str, ...]:
    if expected.get("geometry_type") != actual.get("geometry_type"):
        return ("geometry_type",)
    mismatches: list[str] = []
    _compare_descriptor(
        expected.get("parent_body"), actual.get("parent_body"), "parent_body", tolerance, mismatches
    )
    _compare_descriptor(
        expected.get("descriptor"), actual.get("descriptor"), "descriptor", tolerance, mismatches
    )
    return tuple(mismatches)


def _compare_descriptor(
    expected: Any,
    actual: Any,
    path: str,
    tolerance: RebindTolerance,
    mismatches: list[str],
) -> None:
    if expected is None or actual is None:
        if expected is not actual:
            mismatches.append(path)
        return
    if isinstance(expected, Mapping):
        _compare_mapping(expected, actual, path, tolerance, mismatches)
        return
    if isinstance(expected, tuple | list):
        _compare_sequence(expected, actual, path, tolerance, mismatches)
        return
    if isinstance(expected, bool) or isinstance(actual, bool):
        if expected != actual:
            mismatches.append(path)
        return
    if isinstance(expected, int | float) and isinstance(actual, int | float):
        _compare_number(float(expected), float(actual), path, tolerance, mismatches)
        return
    if expected != actual:
        mismatches.append(path)


def _compare_mapping(
    expected: Mapping[Any, Any],
    actual: Any,
    path: str,
    tolerance: RebindTolerance,
    mismatches: list[str],
) -> None:
    if not isinstance(actual, Mapping):
        mismatches.append(path)
        return
    if set(expected) != set(actual):
        mismatches.append(path + ".keys")
        return
    for key in sorted(expected):
        _compare_descriptor(expected[key], actual[key], f"{path}.{key}", tolerance, mismatches)


def _compare_sequence(
    expected: Sequence[Any],
    actual: Any,
    path: str,
    tolerance: RebindTolerance,
    mismatches: list[str],
) -> None:
    if not isinstance(actual, tuple | list) or len(expected) != len(actual):
        mismatches.append(path)
        return
    for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
        _compare_descriptor(left, right, f"{path}[{index}]", tolerance, mismatches)


def _compare_number(
    left: float,
    right: float,
    path: str,
    tolerance: RebindTolerance,
    mismatches: list[str],
) -> None:
    if not math.isfinite(left) or not math.isfinite(right):
        mismatches.append(path)
        return
    absolute = _absolute_tolerance(path, tolerance)
    if not math.isclose(left, right, rel_tol=tolerance.relative, abs_tol=absolute):
        mismatches.append(path)


def _absolute_tolerance(path: str, tolerance: RebindTolerance) -> float:
    lowered = path.lower()
    if "area_mm2" in lowered:
        return tolerance.area_mm2
    if "volume_mm3" in lowered:
        return tolerance.volume_mm3
    if "angle_rad" in lowered:
        return tolerance.angle_rad
    if "direction" in lowered or ".normal" in lowered:
        return tolerance.direction
    return tolerance.length_mm


def _optional_match(
    reference: GeometryReference | None,
    target_model: CadModel,
    source_model: CadModel | None,
    tolerance: RebindTolerance,
    source_index: CadDescriptorIndex | None,
    target_index: CadDescriptorIndex | None,
) -> GeometryRebindResult | None:
    if reference is None:
        return None
    return rebind_geometry_reference(
        reference,
        target_model,
        source_model=source_model,
        tolerance=tolerance,
        _source_index=source_index,
        _target_index=target_index,
    )


def _rebuild_direction_reference(
    reference: DirectionReference,
    primary: GeometryRebindResult | None,
    secondary: GeometryRebindResult | None,
    model: CadModel,
) -> DirectionReference:
    primary_ref = None if primary is None else primary.rebound_reference
    secondary_ref = None if secondary is None else secondary.rebound_reference
    if reference.reference_type == "two_points":
        return _rebuild_two_point_direction(reference, primary_ref, secondary_ref, model)
    if primary_ref is None:
        raise ValueError("direction reference has no geometry")
    direction = resolve_direction(reference.reference_type, primary_ref, model)
    return replace(
        reference,
        direction_in_source=align_direction(direction, reference.direction_in_source),
        geometry=primary_ref,
    )


def _rebuild_two_point_direction(
    reference: DirectionReference,
    primary: GeometryReference | None,
    secondary: GeometryReference | None,
    model: CadModel,
) -> DirectionReference:
    first = rebound_two_point(
        reference.first_point_in_source_mm, reference.geometry, primary, model
    )
    second = rebound_two_point(
        reference.second_point_in_source_mm, reference.secondary_geometry, secondary, model
    )
    if first is None or second is None:
        raise ValueError("two point reference is incomplete")
    return replace(
        reference,
        geometry=primary,
        secondary_geometry=secondary,
        first_point_in_source_mm=first,
        second_point_in_source_mm=second,
        direction_in_source=subtract(second, first),
    )


def _rebind_frame_direction(
    reference: DirectionReference,
    target_model: CadModel,
    options: tuple[
        CadModel | None,
        RebindTolerance,
        CadDescriptorIndex | None,
        CadDescriptorIndex | None,
    ],
) -> DirectionReferenceRebindResult:
    return rebind_direction_reference(
        reference,
        target_model,
        source_model=options[0],
        tolerance=options[1],
        _source_index=options[2],
        _target_index=options[3],
    )


def _build_rebound_frame(
    frame: CoordinateFrameDefinition,
    node: str,
    origin: PointReference,
    z_axis: DirectionReference,
    x_axis: DirectionReference,
    matches: tuple[GeometryRebindResult, ...],
) -> CoordinateFrameRebindResult:
    try:
        rebound = CoordinateFrameDefinition.from_references(
            frame.frame_id,
            frame.name,
            origin,
            z_axis,
            x_axis,
            source_frame=frame.T_target_from_source.source_frame or "source",
            revision=frame.revision + 1,
        )
    except ValueError:
        issue = ValidationIssue(
            "COORDINATE_FRAME_REBIND_INVALID",
            IssueSeverity.ERROR,
            frame.frame_id,
            {"node": node, "reason": "resolved_references_do_not_form_rigid_frame"},
        )
        return CoordinateFrameRebindResult(frame, None, matches, (issue,))
    return CoordinateFrameRebindResult(frame, rebound, matches)


def _body_match_issue_code(role: str, status: RebindStatus) -> str:
    if role == "part":
        return (
            "PART_BODY_REBIND_AMBIGUOUS"
            if status is RebindStatus.AMBIGUOUS
            else "PART_BODY_REBIND_MISSING"
        )
    return (
        "BODY_REFERENCE_REBIND_AMBIGUOUS"
        if status is RebindStatus.AMBIGUOUS
        else "BODY_REFERENCE_REBIND_MISSING"
    )


def _rebind_frames(
    source_model: CadModel,
    target_model: CadModel,
    model_frame: CoordinateFrameDefinition | None,
    build_frame: CoordinateFrameDefinition | None,
    tolerance: RebindTolerance,
    source_index: CadDescriptorIndex,
    target_index: CadDescriptorIndex,
) -> tuple[
    CoordinateFrameDefinition | None,
    CoordinateFrameDefinition | None,
    set[str],
    list[ValidationIssue],
]:
    frames = {MODEL_CS_NODE: model_frame, BUILD_CS_NODE: build_frame}
    invalid: set[str] = set()
    issues: list[ValidationIssue] = []
    for node, frame in frames.items():
        if frame is None:
            continue
        result = rebind_coordinate_frame(
            frame,
            target_model,
            source_model=source_model,
            node=node,
            tolerance=tolerance,
            _source_index=source_index,
            _target_index=target_index,
        )
        if result.rebound_frame is None:
            invalid.add(node)
            issues.extend(
                _with_node_context(issue, node, frame.frame_id) for issue in result.issues
            )
        else:
            frames[node] = result.rebound_frame
    return frames[MODEL_CS_NODE], frames[BUILD_CS_NODE], invalid, issues


def _reference_issue(
    code: str,
    reference: GeometryReference,
    candidate_ids: Sequence[str],
    *,
    reason: str,
) -> ValidationIssue:
    return ValidationIssue(
        code,
        IssueSeverity.ERROR,
        reference.object_id,
        {
            "geometry_type": reference.geometry_type,
            "parent_body_id": reference.parent_body_id,
            "candidate_ids": list(candidate_ids),
            "signature_schema_version": reference.signature.get("schema_version"),
            "reason": reason,
        },
    )


def _with_node_context(issue: ValidationIssue, node: str, frame_id: str) -> ValidationIssue:
    context = dict(issue.context)
    context.update({"node": node, "frame_id": frame_id})
    return ValidationIssue(issue.code, issue.severity, issue.object_id, context)


def _deduplicate_matches(
    matches: Iterable[GeometryRebindResult],
) -> tuple[GeometryRebindResult, ...]:
    result: list[GeometryRebindResult] = []
    seen: set[tuple[str, str]] = set()
    for match in matches:
        key = match.original_reference.geometry_type, match.original_reference.object_id
        if key not in seen:
            seen.add(key)
            result.append(match)
    return tuple(result)


def _issues(issue: ValidationIssue | None) -> tuple[ValidationIssue, ...]:
    return () if issue is None else (issue,)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _validate_coordinate_node(node: str) -> None:
    if node not in {MODEL_CS_NODE, BUILD_CS_NODE}:
        raise ValueError(f"unsupported coordinate node: {node!r}")
