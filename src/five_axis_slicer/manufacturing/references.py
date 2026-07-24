"""Stable CAD references and deterministic topology rebinding.

The STEP loader deliberately exposes transient topology identifiers.  This
module keeps those identifiers out of source-update decisions: a reference is
matched from an auditable geometric descriptor and is accepted only when one
target entity satisfies that descriptor.  Candidate order is never used as a
tie breaker.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence, TypeGuard, cast

from ..models import BodyInfo, CadModel, EdgeInfo, FaceInfo, VertexInfo
from .coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    PointReference,
    Vector3,
)
from .setup import (
    BUILD_CS_NODE,
    MODEL_CS_NODE,
    PART_NODE,
    IssueSeverity,
    ManufacturingObjectAssignments,
    ValidationIssue,
)


REFERENCE_SIGNATURE_SCHEMA_VERSION = 1


class RebindStatus(str, Enum):
    """Outcome of matching one stable reference against a new CAD model."""

    MATCHED = "matched"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    INVALID_SIGNATURE = "invalid_signature"


@dataclass(frozen=True, slots=True)
class RebindTolerance:
    """Explicit comparison tolerances for STEP round trips.

    The absolute values are small relative to ordinary FFF dimensions while
    still allowing harmless OCCT import noise.  Relative tolerance covers
    large parts without weakening comparisons close to the origin.
    """

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
    """Machine-readable explanation of one rejected or accepted candidate."""

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
    """Result for one topology reference, including comparison evidence."""

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
        return (
            self.status is RebindStatus.MATCHED and self.rebound_reference is not None
        )


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
    """Applied-data replacements calculated before a controller mutates state."""

    assignments: ManufacturingObjectAssignments
    model_coordinate_system: CoordinateFrameDefinition | None
    build_coordinate_system: CoordinateFrameDefinition | None
    body_bindings: Mapping[str, str] = field(default_factory=dict, hash=False)
    invalid_nodes: frozenset[str] = field(default_factory=frozenset)
    issues: tuple[ValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "body_bindings", MappingProxyType(dict(self.body_bindings))
        )


class _CadDescriptorIndex:
    """One-pass topology lookup and descriptor cache for a CAD model."""

    __slots__ = (
        "model",
        "body_map",
        "face_map",
        "edge_map",
        "vertex_map",
        "faces_by_body",
        "edges_by_body",
        "vertices_by_body",
        "body_descriptors",
        "references",
    )

    def __init__(self, model: CadModel) -> None:
        _require_cad_model(model)
        self.model = model
        self.body_map = {item.body_id: item for item in model.bodies}
        self.face_map = {item.face_id: item for item in model.faces}
        self.edge_map = {item.edge_id: item for item in model.edges}
        self.vertex_map = {item.vertex_id: item for item in model.vertices}
        self.faces_by_body: dict[str, list[FaceInfo]] = {}
        self.edges_by_body: dict[str, list[EdgeInfo]] = {}
        self.vertices_by_body: dict[str, list[VertexInfo]] = {}
        for face in model.faces:
            self.faces_by_body.setdefault(face.body_id, []).append(face)
        for edge in model.edges:
            self.edges_by_body.setdefault(edge.body_id, []).append(edge)
        for vertex in model.vertices:
            self.vertices_by_body.setdefault(vertex.body_id, []).append(vertex)
        self.body_descriptors: dict[str, dict[str, Any]] = {}
        self.references: dict[tuple[str, str], GeometryReference] = {}

    def entities(
        self,
        geometry_type: str,
    ) -> tuple[BodyInfo | FaceInfo | EdgeInfo | VertexInfo, ...]:
        if geometry_type == "body":
            return tuple(body for body in self.model.bodies if body.is_solid)
        if geometry_type == "shell":
            return tuple(body for body in self.model.bodies if not body.is_solid)
        if geometry_type == "face":
            return tuple(self.model.faces)
        if geometry_type == "edge":
            return tuple(self.model.edges)
        if geometry_type == "vertex":
            return tuple(self.model.vertices)
        raise ValueError(f"unsupported geometry type: {geometry_type!r}")

    def locate(
        self,
        object_id: str,
        geometry_type: str | None,
    ) -> tuple[str, BodyInfo | FaceInfo | EdgeInfo | VertexInfo]:
        identifier = str(object_id).strip()
        if not identifier:
            raise ValueError("object_id must not be empty")
        canonical = (
            None if geometry_type is None else str(geometry_type).strip().lower()
        )
        if canonical in {"body", "shell"}:
            body = self.body_map.get(identifier)
            if body is None:
                raise KeyError(identifier)
            if canonical == "body" and not body.is_solid:
                raise ValueError(f"{identifier!r} is not a solid body")
            if canonical == "shell" and body.is_solid:
                raise ValueError(f"{identifier!r} is not a shell body")
            return canonical, body
        maps: dict[str, Mapping[str, Any]] = {
            "body": self.body_map,
            "face": self.face_map,
            "edge": self.edge_map,
            "vertex": self.vertex_map,
        }
        if canonical is not None:
            selected = maps.get(canonical)
            if selected is None:
                raise ValueError(f"unsupported geometry type: {geometry_type!r}")
            entity = selected.get(identifier)
            if entity is None:
                raise KeyError(identifier)
            return canonical, entity
        found = [
            (kind, items[identifier])
            for kind, items in maps.items()
            if identifier in items
        ]
        if len(found) != 1:
            raise ValueError(
                f"object_id {identifier!r} does not identify one CAD entity"
            )
        kind, entity = found[0]
        if kind == "body" and not entity.is_solid:
            kind = "shell"
        return kind, entity

    def body_descriptor(self, body: BodyInfo) -> dict[str, Any]:
        descriptor = self.body_descriptors.get(body.body_id)
        if descriptor is None:
            descriptor = _body_descriptor(self, body)
            self.body_descriptors[body.body_id] = descriptor
        return descriptor

    def reference(
        self,
        object_id: str,
        geometry_type: str | None = None,
    ) -> GeometryReference:
        entity_type, entity = self.locate(object_id, geometry_type)
        entity_id = _entity_id(entity_type, entity)
        cache_key = (entity_type, entity_id)
        cached = self.references.get(cache_key)
        if cached is not None:
            return cached
        parent_body_id = _parent_body_id(entity_type, entity)
        parent = None if parent_body_id is None else self.body_map.get(parent_body_id)
        signature: dict[str, Any] = {
            "schema_version": REFERENCE_SIGNATURE_SCHEMA_VERSION,
            "geometry_type": entity_type,
            "descriptor": _entity_descriptor(self, entity_type, entity),
            "parent_body": (None if parent is None else self.body_descriptor(parent)),
            "kernel_signature": str(getattr(entity, "signature", "")),
        }
        assembly_name = None if parent is None else parent.assembly_path
        if entity_type in {"body", "shell"}:
            assembly_name = cast(BodyInfo, entity).assembly_path
        result = GeometryReference(
            object_id=entity_id,
            geometry_type=entity_type,
            signature=signature,
            parent_body_id=parent_body_id,
            assembly_name=assembly_name,
        )
        self.references[cache_key] = result
        return result


def geometry_reference(
    model: CadModel,
    object_id: str,
    geometry_type: str | None = None,
) -> GeometryReference:
    """Build a stable, auditable reference for one entity in ``model``."""

    return _CadDescriptorIndex(model).reference(object_id, geometry_type)


def project_point_to_face(
    model: CadModel,
    face_id: str,
    point_in_source_mm: Sequence[float],
) -> Vector3:
    """Return the closest point on one authoritative trimmed CAD face.

    OCCT topology is used when available, so the result respects trimming as
    well as the supporting surface.  Synthetic kernel-free models retain a
    deterministic planar fallback for domain tests and headless integrations.
    """

    _require_cad_model(model)
    point = _vector3_value(point_in_source_mm, name="point_in_source_mm")
    identifier = str(face_id).strip()
    face = model.face_map.get(identifier)
    if face is None:
        raise KeyError(identifier)

    face_shape = model.face_shapes.get(identifier)
    if face_shape is not None:
        projected = _project_point_to_occ_face(face_shape, point)
        if projected is not None:
            return projected

    if face.surface_type == "plane" and face.normal is not None:
        normal = _unit_vector(face.normal)
        origin = face.axis_origin or face.centroid
        offset = _dot(_subtract(point, origin), normal)
        projected = _subtract(point, tuple(offset * value for value in normal))
        if _point_in_bounds(projected, face.bounds, tolerance=1.0e-7):
            return projected
        raise ValueError("point projects outside the trimmed planar face bounds")
    raise ValueError("authoritative face projection is unavailable")


def audit_coordinate_frame_references(
    frame: CoordinateFrameDefinition,
    model: CadModel,
    *,
    node: str = MODEL_CS_NODE,
) -> tuple[ValidationIssue, ...]:
    """Audit persisted coordinate inputs against the attached CAD model.

    Project loading validates the serialized domain structure.  This audit is
    intentionally performed after authoritative CAD topology is available: an
    object identifier alone cannot prove that a persisted signature, parent
    body, or resolved geometric value still describes that object.
    """

    if not isinstance(frame, CoordinateFrameDefinition):
        raise TypeError("frame must be CoordinateFrameDefinition")
    _require_cad_model(model)
    if node not in {MODEL_CS_NODE, BUILD_CS_NODE}:
        raise ValueError(f"unsupported coordinate node: {node!r}")

    index = _CadDescriptorIndex(model)
    issues: list[ValidationIssue] = []

    def authoritative_reference(
        reference: GeometryReference | None,
        *,
        component: str,
        role: str,
    ) -> GeometryReference | None:
        if reference is None:
            return None
        try:
            authoritative = index.reference(
                reference.object_id,
                reference.geometry_type,
            )
        except KeyError:
            try:
                located = index.reference(reference.object_id)
            except (KeyError, ValueError):
                issues.append(
                    _coordinate_audit_issue(
                        "COORDINATE_GEOMETRY_REFERENCE_MISSING",
                        frame,
                        node,
                        component,
                        role,
                        reference,
                        {"reason": "object_not_found"},
                    )
                )
                return None
            issues.append(
                _coordinate_audit_issue(
                    "COORDINATE_GEOMETRY_REFERENCE_MISMATCH",
                    frame,
                    node,
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
        except ValueError as exc:
            issues.append(
                _coordinate_audit_issue(
                    "COORDINATE_GEOMETRY_REFERENCE_MISMATCH",
                    frame,
                    node,
                    component,
                    role,
                    reference,
                    {"mismatch_fields": ["geometry_type"], "detail": str(exc)},
                )
            )
            return None

        mismatch_fields: list[str] = []
        if reference.geometry_type != authoritative.geometry_type:
            mismatch_fields.append("geometry_type")
        if reference.parent_body_id != authoritative.parent_body_id:
            mismatch_fields.append("parent_body_id")
        if reference.signature != authoritative.signature:
            mismatch_fields.append("signature")
        if mismatch_fields:
            issues.append(
                _coordinate_audit_issue(
                    "COORDINATE_GEOMETRY_REFERENCE_MISMATCH",
                    frame,
                    node,
                    component,
                    role,
                    reference,
                    {"mismatch_fields": mismatch_fields},
                )
            )
        return authoritative

    origin = frame.origin_reference
    if origin.reference_type != "numeric":
        authoritative = authoritative_reference(
            origin.geometry,
            component="origin",
            role="primary",
        )
        if authoritative is not None:
            try:
                resolved_point = _resolve_point(
                    origin,
                    authoritative,
                    model,
                    source_model=None,
                )
            except (KeyError, TypeError, ValueError) as exc:
                issues.append(
                    _coordinate_resolved_issue(
                        "COORDINATE_RESOLVED_POINT_MISMATCH",
                        frame,
                        node,
                        "origin",
                        "point_in_source_mm",
                        origin.geometry,
                        expected=None,
                        actual=origin.point_in_source_mm,
                        detail=str(exc),
                    )
                )
            else:
                if not _same_vector(resolved_point, origin.point_in_source_mm):
                    issues.append(
                        _coordinate_resolved_issue(
                            "COORDINATE_RESOLVED_POINT_MISMATCH",
                            frame,
                            node,
                            "origin",
                            "point_in_source_mm",
                            origin.geometry,
                            expected=resolved_point,
                            actual=origin.point_in_source_mm,
                        )
                    )

    for component, direction in (
        ("z", frame.z_direction_reference),
        ("x", frame.x_direction_reference),
    ):
        if direction.reference_type == "numeric":
            continue
        primary = authoritative_reference(
            direction.geometry,
            component=component,
            role="primary",
        )
        secondary = authoritative_reference(
            direction.secondary_geometry,
            component=component,
            role="secondary",
        )
        if direction.reference_type == "two_points":
            _audit_two_point_direction(
                frame,
                node,
                component,
                direction,
                primary,
                secondary,
                model,
                issues,
            )
            continue
        if primary is None:
            continue
        try:
            resolved_direction = _resolve_direction(
                direction.reference_type,
                primary,
                model,
            )
            resolved_direction = _align_direction(
                resolved_direction,
                direction.direction_in_source,
            )
        except (KeyError, TypeError, ValueError) as exc:
            issues.append(
                _coordinate_resolved_issue(
                    "COORDINATE_RESOLVED_DIRECTION_MISMATCH",
                    frame,
                    node,
                    component,
                    "direction_in_source",
                    direction.geometry,
                    expected=None,
                    actual=direction.direction_in_source,
                    detail=str(exc),
                )
            )
        else:
            if not _same_vector(
                resolved_direction,
                direction.direction_in_source,
            ):
                issues.append(
                    _coordinate_resolved_issue(
                        "COORDINATE_RESOLVED_DIRECTION_MISMATCH",
                        frame,
                        node,
                        component,
                        "direction_in_source",
                        direction.geometry,
                        expected=resolved_direction,
                        actual=direction.direction_in_source,
                    )
                )

    return _deduplicate_issues(issues)


def rebind_geometry_reference(
    reference: GeometryReference,
    target_model: CadModel,
    *,
    source_model: CadModel | None = None,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
    _source_index: _CadDescriptorIndex | None = None,
    _target_index: _CadDescriptorIndex | None = None,
) -> GeometryRebindResult:
    """Rebind one reference when exactly one geometric candidate matches.

    ``source_model`` upgrades legacy references that contain only the loader's
    SHA-256 geometry signature.  The old identifier is used solely to read its
    descriptor from the still-loaded source model; it never selects a target.
    """

    if not isinstance(reference, GeometryReference):
        raise TypeError("reference must be GeometryReference")
    _require_cad_model(target_model)
    if not isinstance(tolerance, RebindTolerance):
        raise TypeError("tolerance must be RebindTolerance")

    source_index = (
        _source_index
        if _source_index is not None
        else None if source_model is None else _CadDescriptorIndex(source_model)
    )
    target_index = _target_index or _CadDescriptorIndex(target_model)
    stable_reference = _upgrade_reference(reference, source_model, source_index)
    signature = stable_reference.signature
    if not _is_supported_signature(signature, stable_reference.geometry_type):
        issue = _reference_issue(
            "GEOMETRY_REFERENCE_REBIND_INVALID_SIGNATURE",
            stable_reference,
            (),
            reason="signature_schema_unsupported",
        )
        return GeometryRebindResult(
            reference,
            RebindStatus.INVALID_SIGNATURE,
            issue=issue,
        )

    audits: list[CandidateAudit] = []
    for candidate in target_index.entities(stable_reference.geometry_type):
        candidate_reference = target_index.reference(
            _entity_id(stable_reference.geometry_type, candidate),
            stable_reference.geometry_type,
        )
        mismatches = _signature_mismatches(
            signature,
            candidate_reference.signature,
            tolerance,
        )
        audits.append(CandidateAudit(candidate_reference.object_id, mismatches))

    matched_ids = tuple(audit.candidate_id for audit in audits if audit.matched)
    if len(matched_ids) == 1:
        rebound = target_index.reference(
            matched_ids[0],
            stable_reference.geometry_type,
        )
        return GeometryRebindResult(
            reference,
            RebindStatus.MATCHED,
            rebound_reference=rebound,
            audits=tuple(audits),
        )

    if not matched_ids:
        status = RebindStatus.MISSING
        code = "GEOMETRY_REFERENCE_REBIND_MISSING"
        reason = "no_geometric_match"
    else:
        status = RebindStatus.AMBIGUOUS
        code = "GEOMETRY_REFERENCE_REBIND_AMBIGUOUS"
        reason = "multiple_geometric_matches"
    issue = _reference_issue(
        code,
        stable_reference,
        matched_ids,
        reason=reason,
    )
    return GeometryRebindResult(
        reference,
        status,
        audits=tuple(audits),
        issue=issue,
    )


def rebind_point_reference(
    reference: PointReference,
    target_model: CadModel,
    *,
    source_model: CadModel | None = None,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
    _source_index: _CadDescriptorIndex | None = None,
    _target_index: _CadDescriptorIndex | None = None,
) -> PointReferenceRebindResult:
    """Rebind and recalculate one resolved origin reference."""

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
        return PointReferenceRebindResult(
            None,
            (match,),
            _issues(match.issue),
        )
    try:
        point = _resolve_point(
            reference,
            match.rebound_reference,
            target_model,
            source_model=source_model,
        )
        rebound = replace(
            reference,
            point_in_source_mm=point,
            geometry=match.rebound_reference,
        )
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
    _source_index: _CadDescriptorIndex | None = None,
    _target_index: _CadDescriptorIndex | None = None,
) -> DirectionReferenceRebindResult:
    """Rebind and recalculate one resolved axis reference."""

    if not isinstance(reference, DirectionReference):
        raise TypeError("reference must be DirectionReference")
    if reference.reference_type == "numeric":
        return DirectionReferenceRebindResult(reference)

    geometry_match: GeometryRebindResult | None = None
    secondary_match: GeometryRebindResult | None = None
    if reference.geometry is not None:
        geometry_match = rebind_geometry_reference(
            reference.geometry,
            target_model,
            source_model=source_model,
            tolerance=tolerance,
            _source_index=_source_index,
            _target_index=_target_index,
        )
    if reference.secondary_geometry is not None:
        secondary_match = rebind_geometry_reference(
            reference.secondary_geometry,
            target_model,
            source_model=source_model,
            tolerance=tolerance,
            _source_index=_source_index,
            _target_index=_target_index,
        )
    matches = tuple(
        item for item in (geometry_match, secondary_match) if item is not None
    )
    issues = _deduplicate_issues(
        item.issue for item in matches if not item.matched and item.issue is not None
    )
    if issues:
        return DirectionReferenceRebindResult(None, matches, issues)

    rebound_geometry = (
        None if geometry_match is None else geometry_match.rebound_reference
    )
    rebound_secondary = (
        None if secondary_match is None else secondary_match.rebound_reference
    )
    try:
        if reference.reference_type == "two_points":
            first = _rebound_two_point(
                reference.first_point_in_source_mm,
                reference.geometry,
                rebound_geometry,
                target_model,
            )
            second = _rebound_two_point(
                reference.second_point_in_source_mm,
                reference.secondary_geometry,
                rebound_secondary,
                target_model,
            )
            if first is None or second is None:
                raise ValueError("two point reference is incomplete")
            direction = _subtract(second, first)
            rebound = replace(
                reference,
                geometry=rebound_geometry,
                secondary_geometry=rebound_secondary,
                first_point_in_source_mm=first,
                second_point_in_source_mm=second,
                direction_in_source=direction,
            )
        else:
            if rebound_geometry is None:
                raise ValueError("direction reference has no geometry")
            direction = _resolve_direction(
                reference.reference_type,
                rebound_geometry,
                target_model,
            )
            direction = _align_direction(direction, reference.direction_in_source)
            rebound = replace(
                reference,
                direction_in_source=direction,
                geometry=rebound_geometry,
            )
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
    _source_index: _CadDescriptorIndex | None = None,
    _target_index: _CadDescriptorIndex | None = None,
) -> CoordinateFrameRebindResult:
    """Rebind all geometric inputs and rebuild a coordinate transform."""

    if not isinstance(frame, CoordinateFrameDefinition):
        raise TypeError("frame must be CoordinateFrameDefinition")
    if node not in {MODEL_CS_NODE, BUILD_CS_NODE}:
        raise ValueError(f"unsupported coordinate node: {node!r}")
    origin = rebind_point_reference(
        frame.origin_reference,
        target_model,
        source_model=source_model,
        tolerance=tolerance,
        _source_index=_source_index,
        _target_index=_target_index,
    )
    z_direction = rebind_direction_reference(
        frame.z_direction_reference,
        target_model,
        source_model=source_model,
        tolerance=tolerance,
        _source_index=_source_index,
        _target_index=_target_index,
    )
    x_direction = rebind_direction_reference(
        frame.x_direction_reference,
        target_model,
        source_model=source_model,
        tolerance=tolerance,
        _source_index=_source_index,
        _target_index=_target_index,
    )
    matches = _deduplicate_matches(
        (*origin.matches, *z_direction.matches, *x_direction.matches)
    )
    issues = _deduplicate_issues(
        (*origin.issues, *z_direction.issues, *x_direction.issues)
    )
    if (
        issues
        or origin.reference is None
        or z_direction.reference is None
        or x_direction.reference is None
    ):
        return CoordinateFrameRebindResult(frame, None, matches, issues)

    try:
        rebound = CoordinateFrameDefinition.from_references(
            frame.frame_id,
            frame.name,
            origin.reference,
            z_direction.reference,
            x_direction.reference,
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


def rebind_body_assignments(
    assignments: ManufacturingObjectAssignments,
    source_model: CadModel,
    target_model: CadModel,
    *,
    tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
    _source_index: _CadDescriptorIndex | None = None,
    _target_index: _CadDescriptorIndex | None = None,
) -> BodyAssignmentRebindResult:
    """Rebind body roles; failed Part matches remain explicit and invalid."""

    if not isinstance(assignments, ManufacturingObjectAssignments):
        raise TypeError("assignments must be ManufacturingObjectAssignments")
    _require_cad_model(source_model)
    _require_cad_model(target_model)
    source_index = _source_index or _CadDescriptorIndex(source_model)
    target_index = _target_index or _CadDescriptorIndex(target_model)

    bindings: dict[str, str] = {}
    issues: list[ValidationIssue] = []
    invalid_nodes: set[str] = set()
    occupied_targets: set[str] = set()

    def bind_group(
        identifiers: Sequence[str],
        role: str,
        *,
        preserve_failed: bool,
    ) -> tuple[str, ...]:
        rebound_ids: list[str] = []
        for body_id in identifiers:
            source_body = source_index.body_map.get(body_id)
            if source_body is None:
                issue = ValidationIssue(
                    "BODY_REFERENCE_REBIND_SOURCE_MISSING",
                    IssueSeverity.ERROR if role == "part" else IssueSeverity.WARNING,
                    body_id,
                    {"role": role, "reason": "source_body_descriptor_unavailable"},
                )
                issues.append(issue)
                if role == "part":
                    invalid_nodes.add(PART_NODE)
                if preserve_failed:
                    rebound_ids.append(body_id)
                continue
            reference_type = "body" if source_body.is_solid else "shell"
            source_reference = source_index.reference(
                body_id,
                reference_type,
            )
            result = rebind_geometry_reference(
                source_reference,
                target_model,
                tolerance=tolerance,
                _source_index=source_index,
                _target_index=target_index,
            )
            if not result.matched or result.rebound_reference is None:
                code = (
                    "PART_BODY_REBIND_AMBIGUOUS"
                    if role == "part" and result.status is RebindStatus.AMBIGUOUS
                    else (
                        "PART_BODY_REBIND_MISSING"
                        if role == "part"
                        else (
                            "BODY_REFERENCE_REBIND_AMBIGUOUS"
                            if result.status is RebindStatus.AMBIGUOUS
                            else "BODY_REFERENCE_REBIND_MISSING"
                        )
                    )
                )
                severity = (
                    IssueSeverity.ERROR if role == "part" else IssueSeverity.WARNING
                )
                issues.append(
                    ValidationIssue(
                        code,
                        severity,
                        body_id,
                        {
                            "role": role,
                            "candidate_ids": list(result.candidate_ids),
                            "geometry_type": reference_type,
                        },
                    )
                )
                if role == "part":
                    invalid_nodes.add(PART_NODE)
                if preserve_failed:
                    rebound_ids.append(body_id)
                continue
            target_id = result.rebound_reference.object_id
            if target_id in occupied_targets:
                issues.append(
                    ValidationIssue(
                        "BODY_REFERENCE_REBIND_TARGET_COLLISION",
                        IssueSeverity.ERROR,
                        body_id,
                        {"role": role, "target_body_id": target_id},
                    )
                )
                if role == "part":
                    invalid_nodes.add(PART_NODE)
                if preserve_failed:
                    rebound_ids.append(body_id)
                continue
            occupied_targets.add(target_id)
            bindings[body_id] = target_id
            rebound_ids.append(target_id)
        return tuple(rebound_ids)

    part = bind_group(assignments.part_body_ids, "part", preserve_failed=True)
    ignored = bind_group(assignments.ignored_body_ids, "ignore", preserve_failed=False)
    fixture = bind_group(assignments.fixture_body_ids, "fixture", preserve_failed=True)
    previous_unassigned = bind_group(
        assignments.unassigned_body_ids,
        "unassigned",
        preserve_failed=False,
    )
    available_target_ids = tuple(body.body_id for body in target_model.bodies)
    represented_ids = set((*part, *ignored, *fixture))
    new_unassigned = tuple(
        body_id
        for body_id in available_target_ids
        if body_id not in occupied_targets and body_id not in represented_ids
    )
    unassigned = _unique((*previous_unassigned, *new_unassigned))
    rebound = ManufacturingObjectAssignments(
        part_body_ids=part,
        ignored_body_ids=ignored,
        fixture_body_ids=fixture,
        unassigned_body_ids=unassigned,
    )
    return BodyAssignmentRebindResult(
        rebound,
        bindings,
        frozenset(invalid_nodes),
        _deduplicate_issues(issues),
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
    """Calculate every Setup reference replacement as one immutable result."""

    source_index = _CadDescriptorIndex(source_model)
    target_index = _CadDescriptorIndex(target_model)
    body_result = rebind_body_assignments(
        assignments,
        source_model,
        target_model,
        tolerance=tolerance,
        _source_index=source_index,
        _target_index=target_index,
    )
    invalid_nodes = set(body_result.invalid_nodes)
    issues = list(body_result.issues)
    rebound_model = model_coordinate_system
    rebound_build = build_coordinate_system

    for node, frame in (
        (MODEL_CS_NODE, model_coordinate_system),
        (BUILD_CS_NODE, build_coordinate_system),
    ):
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
            invalid_nodes.add(node)
            issues.extend(
                _with_node_context(issue, node, frame.frame_id)
                for issue in result.issues
            )
        elif node == MODEL_CS_NODE:
            rebound_model = result.rebound_frame
        else:
            rebound_build = result.rebound_frame

    return CadModelRebindResult(
        assignments=body_result.assignments,
        model_coordinate_system=rebound_model,
        build_coordinate_system=rebound_build,
        body_bindings=body_result.bindings,
        invalid_nodes=frozenset(invalid_nodes),
        issues=_deduplicate_issues(issues),
    )


def _upgrade_reference(
    reference: GeometryReference,
    source_model: CadModel | None,
    source_index: _CadDescriptorIndex | None,
) -> GeometryReference:
    if _is_supported_signature(reference.signature, reference.geometry_type):
        return reference
    if source_model is None:
        return reference
    try:
        index = source_index or _CadDescriptorIndex(source_model)
        return index.reference(
            reference.object_id,
            reference.geometry_type,
        )
    except (KeyError, ValueError):
        return reference


def _is_supported_signature(signature: Mapping[str, Any], geometry_type: str) -> bool:
    try:
        return bool(
            int(signature.get("schema_version", -1))
            == REFERENCE_SIGNATURE_SCHEMA_VERSION
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
    mismatches: list[str] = []
    if expected.get("geometry_type") != actual.get("geometry_type"):
        mismatches.append("geometry_type")
        return tuple(mismatches)
    _compare_descriptor(
        expected.get("parent_body"),
        actual.get("parent_body"),
        "parent_body",
        tolerance,
        mismatches,
    )
    _compare_descriptor(
        expected.get("descriptor"),
        actual.get("descriptor"),
        "descriptor",
        tolerance,
        mismatches,
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
        if not isinstance(actual, Mapping):
            mismatches.append(path)
            return
        if set(expected) != set(actual):
            mismatches.append(path + ".keys")
            return
        for key in sorted(expected):
            _compare_descriptor(
                expected[key],
                actual[key],
                f"{path}.{key}",
                tolerance,
                mismatches,
            )
        return
    if isinstance(expected, (tuple, list)):
        if not isinstance(actual, (tuple, list)) or len(expected) != len(actual):
            mismatches.append(path)
            return
        for index, (left, right) in enumerate(zip(expected, actual)):
            _compare_descriptor(
                left,
                right,
                f"{path}[{index}]",
                tolerance,
                mismatches,
            )
        return
    if isinstance(expected, bool) or isinstance(actual, bool):
        if expected != actual:
            mismatches.append(path)
        return
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        left, right = float(expected), float(actual)
        if not math.isfinite(left) or not math.isfinite(right):
            mismatches.append(path)
            return
        absolute = _absolute_tolerance(path, tolerance)
        if not math.isclose(left, right, rel_tol=tolerance.relative, abs_tol=absolute):
            mismatches.append(path)
        return
    if expected != actual:
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


def _body_descriptor(index: _CadDescriptorIndex, body: BodyInfo) -> dict[str, Any]:
    faces = index.faces_by_body.get(body.body_id, ())
    edges = index.edges_by_body.get(body.body_id, ())
    vertices = index.vertices_by_body.get(body.body_id, ())
    return {
        "kind": body.kind,
        "assembly_path": body.assembly_path,
        "bounds_mm": _bounds_descriptor(body.bounds),
        "dimensions_mm": _bounds_dimensions(body.bounds),
        "volume_mm3": body.volume,
        "surface_area_mm2": body.surface_area,
        "centroid_mm": _vector(body.centroid),
        "topology": {
            "face_count": len(faces) if faces else len(body.face_ids),
            "edge_count": len(edges) if edges else len(body.edge_ids),
            "vertex_count": len(vertices) if vertices else len(body.vertex_ids),
            "surface_types": _histogram(face.surface_type for face in faces),
            "curve_types": _histogram(edge.curve_type for edge in edges),
            "vertex_edge_degrees": sorted(len(vertex.edge_ids) for vertex in vertices),
        },
    }


def _face_descriptor(index: _CadDescriptorIndex, face: FaceInfo) -> dict[str, Any]:
    edge_map = index.edge_map
    adjacent_edges = [edge_map[item] for item in face.edge_ids if item in edge_map]
    return {
        "surface_type": face.surface_type,
        "area_mm2": face.area,
        "centroid_mm": _vector(face.centroid),
        "bounds_mm": _bounds_descriptor(face.bounds),
        "dimensions_mm": _bounds_dimensions(face.bounds),
        "normal": _canonical_axis(face.normal),
        "axis_origin_mm": _vector(face.axis_origin),
        "axis_direction": _canonical_axis(face.axis_direction),
        "radius_mm": face.radius,
        "secondary_radius_mm": face.secondary_radius,
        "semi_angle_rad": face.semi_angle_rad,
        "orientation": face.orientation,
        "adjacency": {
            "edge_count": len(face.edge_ids),
            "curve_types": sorted(edge.curve_type for edge in adjacent_edges),
            "edge_face_degrees": sorted(len(edge.face_ids) for edge in adjacent_edges),
        },
    }


def _edge_descriptor(index: _CadDescriptorIndex, edge: EdgeInfo) -> dict[str, Any]:
    face_map = index.face_map
    vertex_map = index.vertex_map
    adjacent_faces = [face_map[item] for item in edge.face_ids if item in face_map]
    adjacent_vertices = [
        vertex_map[item] for item in edge.vertex_ids if item in vertex_map
    ]
    points: list[Vector3] = []
    if edge.endpoints is not None:
        points.extend(edge.endpoints)
    for point in (edge.center, edge.arc_length_midpoint):
        if point is not None:
            points.append(point)
    return {
        "curve_type": edge.curve_type,
        "length_mm": (
            edge.exact_length if edge.exact_length is not None else edge.length_hint
        ),
        "bounds_mm": _point_bounds(points),
        "endpoints_mm": _canonical_endpoints(edge.endpoints),
        "arc_length_midpoint_mm": _vector(edge.arc_length_midpoint),
        "center_mm": _vector(edge.center),
        "axis_direction": _canonical_axis(edge.axis_direction),
        "radius_mm": edge.radius,
        "adjacency": {
            "vertex_count": len(edge.vertex_ids),
            "face_count": len(edge.face_ids),
            "face_surface_types": sorted(face.surface_type for face in adjacent_faces),
            "vertex_edge_degrees": sorted(
                len(vertex.edge_ids) for vertex in adjacent_vertices
            ),
        },
    }


def _vertex_descriptor(
    index: _CadDescriptorIndex, vertex: VertexInfo
) -> dict[str, Any]:
    edge_map = index.edge_map
    face_map = index.face_map
    adjacent_edges = [edge_map[item] for item in vertex.edge_ids if item in edge_map]
    adjacent_face_ids = {
        face_id for edge in adjacent_edges for face_id in edge.face_ids
    }
    return {
        "point_mm": _vector(vertex.point),
        "bounds_mm": {
            "minimum": _vector(vertex.point),
            "maximum": _vector(vertex.point),
        },
        "adjacency": {
            "edge_count": len(vertex.edge_ids),
            "curve_types": sorted(edge.curve_type for edge in adjacent_edges),
            "face_surface_types": sorted(
                face_map[item].surface_type
                for item in adjacent_face_ids
                if item in face_map
            ),
        },
    }


def _entity_descriptor(
    index: _CadDescriptorIndex,
    geometry_type: str,
    entity: BodyInfo | FaceInfo | EdgeInfo | VertexInfo,
) -> dict[str, Any]:
    if geometry_type in {"body", "shell"}:
        return index.body_descriptor(entity)  # type: ignore[arg-type]
    if geometry_type == "face":
        return _face_descriptor(index, entity)  # type: ignore[arg-type]
    if geometry_type == "edge":
        return _edge_descriptor(index, entity)  # type: ignore[arg-type]
    if geometry_type == "vertex":
        return _vertex_descriptor(index, entity)  # type: ignore[arg-type]
    raise ValueError(f"unsupported geometry type: {geometry_type!r}")


def _parent_body_id(
    geometry_type: str,
    entity: BodyInfo | FaceInfo | EdgeInfo | VertexInfo,
) -> str | None:
    if geometry_type in {"body", "shell"}:
        return None
    return entity.body_id  # type: ignore[union-attr]


def _entity_id(
    geometry_type: str,
    entity: BodyInfo | FaceInfo | EdgeInfo | VertexInfo,
) -> str:
    if geometry_type in {"body", "shell"}:
        return entity.body_id  # type: ignore[union-attr]
    if geometry_type == "face":
        return entity.face_id  # type: ignore[union-attr]
    if geometry_type == "edge":
        return entity.edge_id  # type: ignore[union-attr]
    if geometry_type == "vertex":
        return entity.vertex_id  # type: ignore[union-attr]
    raise ValueError(geometry_type)


def _resolve_point(
    reference: PointReference,
    rebound_geometry: GeometryReference,
    model: CadModel,
    *,
    source_model: CadModel | None,
) -> Vector3:
    object_id = rebound_geometry.object_id
    kind = reference.reference_type
    if kind == "vertex":
        return model.vertex_map[object_id].point
    if kind in {"circle_center", "ellipse_center"}:
        edge = model.edge_map[object_id]
        expected_curve = kind.removesuffix("_center")
        if edge.curve_type != expected_curve or edge.center is None:
            raise ValueError("selected edge does not expose the requested centre")
        return edge.center
    if kind == "arc_midpoint":
        point = model.edge_map[object_id].arc_length_midpoint
        if point is None:
            raise ValueError("selected edge has no arc-length midpoint")
        return point
    if kind == "face_centroid":
        return model.face_map[object_id].centroid
    if kind == "face_pick":
        face = model.face_map[object_id]
        if reference.point_in_source_mm is None:
            raise ValueError("face pick has no source point")
        old_descriptor = reference.geometry.signature.get("descriptor", {})  # type: ignore[union-attr]
        old_centroid = (
            old_descriptor.get("centroid_mm")
            if isinstance(old_descriptor, Mapping)
            else None
        )
        if not _is_vector3(old_centroid) and source_model is not None:
            old_face = source_model.face_map.get(reference.geometry.object_id)  # type: ignore[union-attr]
            if old_face is not None:
                old_centroid = old_face.centroid
        if not _is_vector3(old_centroid):
            # Matching constrains face centroid and bounds to import-noise
            # tolerances, so retaining the source point is deterministic when
            # a legacy project has no recoverable face descriptor.
            candidate = reference.point_in_source_mm
        else:
            delta = _subtract(
                face.centroid,
                tuple(float(item) for item in old_centroid),
            )
            candidate = _add(reference.point_in_source_mm, delta)
        return project_point_to_face(model, object_id, candidate)
    raise ValueError(f"unsupported point reference type: {kind!r}")


def _resolve_direction(
    reference_type: str,
    rebound_geometry: GeometryReference,
    model: CadModel,
) -> Vector3:
    object_id = rebound_geometry.object_id
    if reference_type == "line_edge":
        edge = model.edge_map[object_id]
        if edge.curve_type != "line":
            raise ValueError("selected edge is not linear")
        if edge.axis_direction is not None:
            return edge.axis_direction
        if edge.endpoints is not None:
            return _subtract(edge.endpoints[1], edge.endpoints[0])
        raise ValueError("selected line has no direction")
    face = model.face_map[object_id]
    if reference_type == "plane_normal":
        if face.surface_type != "plane" or face.normal is None:
            raise ValueError("selected face has no plane normal")
        return face.normal
    if reference_type == "surface_axis":
        if face.surface_type not in {"cylinder", "cone"} or face.axis_direction is None:
            raise ValueError("selected face has no supported surface axis")
        return face.axis_direction
    raise ValueError(f"unsupported direction reference type: {reference_type!r}")


def _rebound_two_point(
    old_point: Vector3 | None,
    old_geometry: GeometryReference | None,
    rebound_geometry: GeometryReference | None,
    model: CadModel,
) -> Vector3 | None:
    if rebound_geometry is None:
        return old_point
    object_id = rebound_geometry.object_id
    if rebound_geometry.geometry_type == "vertex":
        return model.vertex_map[object_id].point
    if rebound_geometry.geometry_type == "face":
        return model.face_map[object_id].centroid
    if rebound_geometry.geometry_type == "edge":
        edge = model.edge_map[object_id]
        candidates = [
            point
            for point in (
                edge.center,
                edge.arc_length_midpoint,
                None if edge.endpoints is None else edge.endpoints[0],
                None if edge.endpoints is None else edge.endpoints[1],
            )
            if point is not None
        ]
        if not candidates:
            raise ValueError("edge has no resolvable point")
        if old_point is None:
            return candidates[0]
        return min(candidates, key=lambda point: math.dist(point, old_point))
    if old_geometry is not None and rebound_geometry.geometry_type in {"body", "shell"}:
        body = model.body_map[object_id]
        return body.centroid
    return old_point


def _align_direction(direction: Vector3, previous: Vector3 | None) -> Vector3:
    if previous is None:
        return direction
    if _dot(direction, previous) < 0.0:
        return tuple(-value for value in direction)  # type: ignore[return-value]
    return direction


def _audit_two_point_direction(
    frame: CoordinateFrameDefinition,
    node: str,
    component: str,
    reference: DirectionReference,
    primary: GeometryReference | None,
    secondary: GeometryReference | None,
    model: CadModel,
    issues: list[ValidationIssue],
) -> None:
    try:
        first = _rebound_two_point(
            reference.first_point_in_source_mm,
            reference.geometry,
            primary,
            model,
        )
        second = _rebound_two_point(
            reference.second_point_in_source_mm,
            reference.secondary_geometry,
            secondary,
            model,
        )
    except (KeyError, TypeError, ValueError) as exc:
        issues.append(
            _coordinate_resolved_issue(
                "COORDINATE_RESOLVED_DIRECTION_MISMATCH",
                frame,
                node,
                component,
                "two_points",
                reference.geometry,
                expected=None,
                actual=reference.direction_in_source,
                detail=str(exc),
            )
        )
        return

    for field_name, expected, actual, geometry in (
        (
            "first_point_in_source_mm",
            first,
            reference.first_point_in_source_mm,
            reference.geometry,
        ),
        (
            "second_point_in_source_mm",
            second,
            reference.second_point_in_source_mm,
            reference.secondary_geometry,
        ),
    ):
        if (
            geometry is not None
            and expected is not None
            and not _same_vector(expected, actual)
        ):
            issues.append(
                _coordinate_resolved_issue(
                    "COORDINATE_RESOLVED_POINT_MISMATCH",
                    frame,
                    node,
                    component,
                    field_name,
                    geometry,
                    expected=expected,
                    actual=actual,
                )
            )

    if first is None or second is None:
        return
    expected_direction = _subtract(second, first)
    if reference.direction_in_source is not None and not _same_vector(
        expected_direction,
        reference.direction_in_source,
    ):
        issues.append(
            _coordinate_resolved_issue(
                "COORDINATE_RESOLVED_DIRECTION_MISMATCH",
                frame,
                node,
                component,
                "direction_in_source",
                reference.geometry,
                expected=expected_direction,
                actual=reference.direction_in_source,
            )
        )


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
        "reference_type": (
            frame.origin_reference.reference_type
            if component == "origin"
            else (
                frame.z_direction_reference.reference_type
                if component == "z"
                else frame.x_direction_reference.reference_type
            )
        ),
        "expected": None if expected is None else list(expected),
        "actual": None if actual is None else list(actual),
    }
    if detail:
        context["detail"] = detail
    return ValidationIssue(
        code,
        IssueSeverity.ERROR,
        frame.frame_id if reference is None else reference.object_id,
        context,
    )


def _same_vector(
    expected: Sequence[float] | None,
    actual: Sequence[float] | None,
) -> bool:
    if expected is None or actual is None:
        return expected is actual
    return len(expected) == len(actual) and all(
        float(left) == float(right) for left, right in zip(expected, actual)
    )


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


def _with_node_context(
    issue: ValidationIssue,
    node: str,
    frame_id: str,
) -> ValidationIssue:
    context = dict(issue.context)
    context.update({"node": node, "frame_id": frame_id})
    return ValidationIssue(issue.code, issue.severity, issue.object_id, context)


def _deduplicate_matches(
    matches: Iterable[GeometryRebindResult],
) -> tuple[GeometryRebindResult, ...]:
    result: list[GeometryRebindResult] = []
    seen: set[tuple[str, str]] = set()
    for match in matches:
        key = (
            match.original_reference.geometry_type,
            match.original_reference.object_id,
        )
        if key not in seen:
            seen.add(key)
            result.append(match)
    return tuple(result)


def _deduplicate_issues(
    issues: Iterable[ValidationIssue],
) -> tuple[ValidationIssue, ...]:
    result: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (issue.code, issue.object_id, repr(issue.to_json()["context"]))
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return tuple(result)


def _issues(issue: ValidationIssue | None) -> tuple[ValidationIssue, ...]:
    return () if issue is None else (issue,)


def _histogram(values: Iterable[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def _bounds_descriptor(bounds: Any) -> dict[str, list[float]] | None:
    if bounds is None:
        return None
    return {
        "minimum": list(_vector(bounds.minimum) or ()),
        "maximum": list(_vector(bounds.maximum) or ()),
    }


def _bounds_dimensions(bounds: Any) -> list[float] | None:
    if bounds is None:
        return None
    return [
        float(right) - float(left)
        for left, right in zip(bounds.minimum, bounds.maximum)
    ]


def _point_bounds(points: Sequence[Vector3]) -> dict[str, list[float]] | None:
    if not points:
        return None
    return {
        "minimum": [min(point[axis] for point in points) for axis in range(3)],
        "maximum": [max(point[axis] for point in points) for axis in range(3)],
    }


def _canonical_endpoints(
    endpoints: tuple[Vector3, Vector3] | None,
) -> list[list[float]] | None:
    if endpoints is None:
        return None
    return [list(point) for point in sorted(endpoints)]


def _canonical_axis(vector: Vector3 | None) -> list[float] | None:
    if vector is None:
        return None
    length = math.sqrt(sum(float(value) ** 2 for value in vector))
    if not math.isfinite(length) or length <= 1.0e-15:
        return None
    result = [float(value) / length for value in vector]
    for value in result:
        if abs(value) <= 1.0e-14:
            continue
        if value < 0.0:
            result = [-item for item in result]
        break
    return result


def _vector(value: Sequence[float] | None) -> list[float] | None:
    if value is None:
        return None
    return [float(item) for item in value]


def _is_vector3(value: Any) -> TypeGuard[Sequence[float]]:
    return (
        isinstance(value, (tuple, list))
        and len(value) == 3
        and all(
            isinstance(item, (int, float)) and math.isfinite(float(item))
            for item in value
        )
    )


def _vector3_value(value: Sequence[float], *, name: str) -> Vector3:
    if not _is_vector3(value):
        raise ValueError(f"{name} must contain three finite numbers")
    return tuple(float(item) for item in value)  # type: ignore[return-value]


def _unit_vector(value: Sequence[float]) -> Vector3:
    length = math.sqrt(sum(float(item) ** 2 for item in value))
    if not math.isfinite(length) or length <= 1.0e-15:
        raise ValueError("surface normal must be finite and non-zero")
    return tuple(float(item) / length for item in value)  # type: ignore[return-value]


def _point_in_bounds(
    point: Sequence[float],
    bounds: Any,
    *,
    tolerance: float,
) -> bool:
    return all(
        float(lower) - tolerance <= float(value) <= float(upper) + tolerance
        for value, lower, upper in zip(point, bounds.minimum, bounds.maximum)
    )


def _project_point_to_occ_face(
    face_shape: object,
    point: Vector3,
) -> Vector3 | None:
    try:
        from OCP.BRepBuilderAPI import (  # type: ignore[import-untyped]
            BRepBuilderAPI_MakeVertex,
        )
        from OCP.BRepExtrema import (  # type: ignore[import-untyped]
            BRepExtrema_DistShapeShape,
        )
        from OCP.gp import gp_Pnt  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
        distance = BRepExtrema_DistShapeShape(vertex, face_shape)
        distance.Perform()
        if not distance.IsDone() or distance.NbSolution() < 1:
            return None
        projected = distance.PointOnShape2(1)
        result = (float(projected.X()), float(projected.Y()), float(projected.Z()))
        return result if all(math.isfinite(item) for item in result) else None
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


def _subtract(left: Sequence[float], right: Sequence[float]) -> Vector3:
    return tuple(float(a) - float(b) for a, b in zip(left, right))  # type: ignore[return-value]


def _add(left: Sequence[float], right: Sequence[float]) -> Vector3:
    return tuple(float(a) + float(b) for a, b in zip(left, right))  # type: ignore[return-value]


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _require_cad_model(model: CadModel) -> None:
    if not isinstance(model, CadModel):
        raise TypeError("model must be CadModel")


__all__ = [
    "BodyAssignmentRebindResult",
    "CadModelRebindResult",
    "CandidateAudit",
    "CoordinateFrameRebindResult",
    "DEFAULT_REBIND_TOLERANCE",
    "DirectionReferenceRebindResult",
    "GeometryRebindResult",
    "PointReferenceRebindResult",
    "REFERENCE_SIGNATURE_SCHEMA_VERSION",
    "RebindStatus",
    "RebindTolerance",
    "audit_coordinate_frame_references",
    "geometry_reference",
    "project_point_to_face",
    "rebind_body_assignments",
    "rebind_cad_model_state",
    "rebind_coordinate_frame",
    "rebind_direction_reference",
    "rebind_geometry_reference",
    "rebind_point_reference",
]
