"""Stable public facade for CAD reference audit and unique rebinding."""

from .coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    PointReference,
    Vector3,
)
from .reference_audit import audit_coordinate_frame_references
from .reference_descriptors import (
    REFERENCE_SIGNATURE_SCHEMA_VERSION,
    geometry_reference,
    project_point_to_face,
)
from .reference_rebind import (
    DEFAULT_REBIND_TOLERANCE,
    BodyAssignmentRebindResult,
    CadModelRebindResult,
    CandidateAudit,
    CoordinateFrameRebindResult,
    DirectionReferenceRebindResult,
    GeometryRebindResult,
    PointReferenceRebindResult,
    RebindStatus,
    RebindTolerance,
    rebind_body_assignments,
    rebind_cad_model_state,
    rebind_coordinate_frame,
    rebind_direction_reference,
    rebind_geometry_reference,
    rebind_point_reference,
)

__all__ = [
    "BodyAssignmentRebindResult",
    "CadModelRebindResult",
    "CandidateAudit",
    "CoordinateFrameDefinition",
    "CoordinateFrameRebindResult",
    "DEFAULT_REBIND_TOLERANCE",
    "DirectionReference",
    "DirectionReferenceRebindResult",
    "GeometryReference",
    "GeometryRebindResult",
    "PointReference",
    "PointReferenceRebindResult",
    "REFERENCE_SIGNATURE_SCHEMA_VERSION",
    "RebindStatus",
    "RebindTolerance",
    "Vector3",
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
