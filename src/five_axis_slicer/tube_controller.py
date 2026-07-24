"""Qt-independent orchestration for the first Tube manufacturing workflow.

The controller owns the editable workflow state around the immutable
``ManufacturingSetup`` aggregate.  UI code can bind to this class without
learning persistence details or reproducing dependency propagation rules.
Drafts intentionally live outside the applied aggregate: an invalid Apply
never changes the last known-good Setup.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    LocalAdjustment,
    PointReference,
    RigidTransform,
    apply_local_adjustment,
)
from .manufacturing.library import (
    ResourceLibraryDiagnostic,
    ResourceLibraryError,
    ResourceProfile,
    ResourceSnapshotAudit,
    UserResourceLibrary,
)
from .manufacturing.machine import MachineProfile, builtin_machine_profiles
from .manufacturing.resources import (
    MaterialProfile,
    NozzleProfile,
    ResourceSnapshot,
    builtin_material_profiles,
    builtin_nozzle_profiles,
)
from .manufacturing.references import (
    DEFAULT_REBIND_TOLERANCE,
    CadModelRebindResult,
    RebindTolerance,
    audit_coordinate_frame_references,
    geometry_reference as build_geometry_reference,
    rebind_cad_model_state,
)
from .manufacturing.setup import (
    BUILD_CS_NODE,
    MACHINE_NODE,
    MATERIAL_NODE,
    MODEL_CS_NODE,
    NOZZLE_NODE,
    OPERATION_NODE,
    PART_NODE,
    PLACEMENT_NODE,
    IssueSeverity,
    ManufacturingObjectAssignments,
    ManufacturingSetup,
    NodeState,
    SetupValidationReport,
    TubeOperationDefinition,
    ValidationIssue,
)
from .models import BodyInfo, CadModel


TUBE_CONTROLLER_SCHEMA_VERSION = 1
TUBE_OPERATION_TYPE = "tube_thin_wall_indexed"
TUBE_OPERATION_NAME = "Tube Thin-Wall Indexed"
AVAILABLE_TUBE_OPERATION_TYPES = (TUBE_OPERATION_TYPE,)
MAX_INTERACTIVE_OPERATIONS = 1

_COORDINATE_NODES = frozenset({MODEL_CS_NODE, BUILD_CS_NODE})
_DRAFT_NODES = _COORDINATE_NODES | {PLACEMENT_NODE}


class TubeControllerError(RuntimeError):
    """Base error raised at the workflow boundary."""


class OperationLimitError(TubeControllerError):
    """Raised when the first-release interactive operation limit is reached."""


class DraftNotFoundError(TubeControllerError):
    """Raised when an edit command targets a node with no active draft."""


class PendingDraftError(TubeControllerError):
    """Raised when persistence is requested while unapplied edits exist."""

    def __init__(self, nodes: Iterable[str]) -> None:
        self.nodes = tuple(sorted({str(node) for node in nodes}))
        super().__init__("pending Setup drafts: " + ", ".join(self.nodes))


class StaleDraftError(TubeControllerError):
    """Raised when a Placement draft no longer matches its dependencies."""


class BodyRole(str, Enum):
    PART = "part"
    IGNORE = "ignore"
    FIXTURE = "fixture"
    UNASSIGNED = "unassigned"


@dataclass(frozen=True, slots=True)
class BodyCandidate:
    """Kernel-independent body descriptor used by the Part editor."""

    body_id: str
    name: str
    kind: str
    signature: str = ""

    def __post_init__(self) -> None:
        body_id = str(self.body_id).strip()
        kind = str(self.kind).strip().lower()
        if not body_id:
            raise ValueError("body_id must not be empty")
        if not kind:
            raise ValueError("body kind must not be empty")
        object.__setattr__(self, "body_id", body_id)
        object.__setattr__(self, "name", str(self.name).strip() or body_id)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "signature", str(self.signature).strip())

    @classmethod
    def from_body_info(cls, body: BodyInfo) -> BodyCandidate:
        return cls(body.body_id, body.name, body.kind, body.signature)

    @property
    def is_part_eligible(self) -> bool:
        return self.kind == "solid"

    def to_json(self) -> dict[str, Any]:
        return {
            "body_id": self.body_id,
            "name": self.name,
            "kind": self.kind,
            "signature": self.signature,
            "is_part_eligible": self.is_part_eligible,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> BodyCandidate:
        if not isinstance(payload, Mapping):
            raise ValueError("body candidate payload must be an object")
        return cls(
            body_id=str(payload.get("body_id", payload.get("id", ""))),
            name=str(payload.get("name", "")),
            kind=str(payload.get("kind", "")),
            signature=str(payload.get("signature", "")),
        )


@dataclass(frozen=True, slots=True)
class CoordinateFrameDraft:
    """Partial three-reference definition kept outside the applied Setup."""

    node: str
    frame_id: str
    name: str
    origin_reference: PointReference | None = None
    z_direction_reference: DirectionReference | None = None
    x_direction_reference: DirectionReference | None = None
    base_revision: int = 0

    def __post_init__(self) -> None:
        node = _coordinate_node(self.node)
        frame_id = str(self.frame_id).strip()
        name = str(self.name).strip()
        if not frame_id or not name:
            raise ValueError("draft frame_id and name must not be empty")
        if self.origin_reference is not None and not isinstance(
            self.origin_reference, PointReference
        ):
            raise TypeError("origin_reference must be PointReference")
        for field_name in ("z_direction_reference", "x_direction_reference"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, DirectionReference):
                raise TypeError(f"{field_name} must be DirectionReference")
        base_revision = int(self.base_revision)
        if base_revision < 0:
            raise ValueError("base_revision cannot be negative")
        object.__setattr__(self, "node", node)
        object.__setattr__(self, "frame_id", frame_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "base_revision", base_revision)

    @classmethod
    def from_applied(
        cls,
        node: str,
        frame: CoordinateFrameDefinition | None,
    ) -> CoordinateFrameDraft:
        canonical_node = _coordinate_node(node)
        expected_frame_id = "model" if canonical_node == MODEL_CS_NODE else "build"
        if frame is None:
            name = "Model CS" if canonical_node == MODEL_CS_NODE else "Build CS"
            return cls(canonical_node, expected_frame_id, name)
        return cls(
            node=canonical_node,
            frame_id=expected_frame_id,
            name=frame.name,
            origin_reference=frame.origin_reference,
            z_direction_reference=frame.z_direction_reference,
            x_direction_reference=frame.x_direction_reference,
            base_revision=frame.revision,
        )

    @property
    def is_complete(self) -> bool:
        return (
            self.origin_reference is not None
            and self.z_direction_reference is not None
            and self.x_direction_reference is not None
        )

    @property
    def is_confirmed(self) -> bool:
        return bool(
            self.is_complete
            and self.origin_reference is not None
            and self.origin_reference.confirmed
            and self.z_direction_reference is not None
            and self.z_direction_reference.confirmed
            and self.x_direction_reference is not None
            and self.x_direction_reference.confirmed
        )

    def to_applied(self) -> CoordinateFrameDefinition:
        if not self.is_complete:
            raise ValueError(f"{self.node} requires origin, Z, and X references")
        if not self.is_confirmed:
            raise ValueError(f"{self.node} references must be individually confirmed")
        assert self.origin_reference is not None
        assert self.z_direction_reference is not None
        assert self.x_direction_reference is not None
        return CoordinateFrameDefinition.from_references(
            self.frame_id,
            self.name,
            self.origin_reference,
            self.z_direction_reference,
            self.x_direction_reference,
            revision=self.base_revision + 1,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "frame_id": self.frame_id,
            "name": self.name,
            "origin_reference": (
                None
                if self.origin_reference is None
                else self.origin_reference.to_json()
            ),
            "z_direction_reference": (
                None
                if self.z_direction_reference is None
                else self.z_direction_reference.to_json()
            ),
            "x_direction_reference": (
                None
                if self.x_direction_reference is None
                else self.x_direction_reference.to_json()
            ),
            "base_revision": self.base_revision,
            "complete": self.is_complete,
            "confirmed": self.is_confirmed,
        }


@dataclass(frozen=True, slots=True)
class PlacementDraft:
    """Mount pairing and local six-DOF adjustment under edit."""

    mount_datum_id: str | None = None
    T_reference_mount_from_build: RigidTransform | None = None
    adjustment: LocalAdjustment = field(default_factory=LocalAdjustment)
    build_cs_revision: int | None = None
    machine_content_hash: str | None = None

    def __post_init__(self) -> None:
        mount_id = (
            None
            if self.mount_datum_id is None
            else str(self.mount_datum_id).strip() or None
        )
        if self.T_reference_mount_from_build is not None and not isinstance(
            self.T_reference_mount_from_build, RigidTransform
        ):
            raise TypeError("T_reference_mount_from_build must be RigidTransform")
        if not isinstance(self.adjustment, LocalAdjustment):
            raise TypeError("adjustment must be LocalAdjustment")
        revision = (
            None if self.build_cs_revision is None else int(self.build_cs_revision)
        )
        if revision is not None and revision < 1:
            raise ValueError("build_cs_revision must be positive")
        machine_hash = (
            None
            if self.machine_content_hash is None
            else str(self.machine_content_hash).strip() or None
        )
        object.__setattr__(self, "mount_datum_id", mount_id)
        object.__setattr__(self, "build_cs_revision", revision)
        object.__setattr__(self, "machine_content_hash", machine_hash)

    @property
    def is_complete(self) -> bool:
        return bool(
            self.mount_datum_id is not None
            and self.T_reference_mount_from_build is not None
        )

    @property
    def T_mount_from_build(self) -> RigidTransform:
        if self.T_reference_mount_from_build is None:
            raise ValueError("Placement requires a mount reference transform")
        return apply_local_adjustment(
            self.T_reference_mount_from_build,
            self.adjustment,
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "mount_datum_id": self.mount_datum_id,
            "T_reference_mount_from_build": (
                None
                if self.T_reference_mount_from_build is None
                else self.T_reference_mount_from_build.to_json()
            ),
            "adjustment": self.adjustment.to_json(),
            "build_cs_revision": self.build_cs_revision,
            "machine_content_hash": self.machine_content_hash,
            "complete": self.is_complete,
        }


class TubeSetupController:
    """State owner for one first-release Tube Setup.

    Loaded project data may contain multiple operations for forward
    compatibility.  Interactive creation remains limited to one operation in
    this release, and only ``tube_thin_wall_indexed`` is advertised.
    """

    def __init__(
        self,
        cad_model: CadModel | None = None,
        *,
        setup: ManufacturingSetup | None = None,
        operations: Iterable[TubeOperationDefinition] = (),
        body_catalog: Iterable[BodyCandidate] = (),
        resource_library: UserResourceLibrary | None = None,
    ) -> None:
        self._setup = setup if setup is not None else ManufacturingSetup()
        if not isinstance(self._setup, ManufacturingSetup):
            raise TypeError("setup must be ManufacturingSetup")
        self._operations = tuple(operations)
        if any(
            not isinstance(operation, TubeOperationDefinition)
            for operation in self._operations
        ):
            raise TypeError("operations must contain TubeOperationDefinition")
        _ensure_unique_operation_ids(self._operations)

        candidates = tuple(body_catalog)
        if any(not isinstance(item, BodyCandidate) for item in candidates):
            raise TypeError("body_catalog must contain BodyCandidate")
        self._body_catalog: dict[str, BodyCandidate] = {
            item.body_id: item for item in candidates
        }
        if len(self._body_catalog) != len(candidates):
            raise ValueError("body_catalog contains duplicate body IDs")
        self._source_hash: str | None = None
        self._source_path: str | None = None
        self._cad_model: CadModel | None = None
        self._topology_ids: frozenset[str] = frozenset(self._body_catalog)
        self._drafts: dict[str, CoordinateFrameDraft | PlacementDraft] = {}
        if resource_library is not None and not isinstance(
            resource_library, UserResourceLibrary
        ):
            raise TypeError("resource_library must be UserResourceLibrary")
        self._resource_library = resource_library
        self._resource_catalogs: dict[str, tuple[ResourceProfile, ...]] = {}
        self._resource_audits: dict[str, ResourceSnapshotAudit] = {}
        self._resource_audit_failures: dict[str, str] = {}
        self._resource_library_diagnostics: tuple[ResourceLibraryDiagnostic, ...] = ()
        self._modified = False

        if cad_model is not None:
            self.attach_cad_model(cad_model, mark_modified=False)
        elif self._body_catalog:
            self._initialise_unassigned_candidates()
        self.refresh_resource_library()

    @property
    def setup(self) -> ManufacturingSetup:
        return self._setup

    @property
    def operations(self) -> tuple[TubeOperationDefinition, ...]:
        return self._operations

    @property
    def body_candidates(self) -> tuple[BodyCandidate, ...]:
        return tuple(self._body_catalog.values())

    @property
    def part_candidates(self) -> tuple[BodyCandidate, ...]:
        return tuple(item for item in self.body_candidates if item.is_part_eligible)

    @property
    def available_operation_types(self) -> tuple[str, ...]:
        return AVAILABLE_TUBE_OPERATION_TYPES

    @property
    def can_create_operation(self) -> bool:
        return len(self._operations) < MAX_INTERACTIVE_OPERATIONS

    @property
    def has_drafts(self) -> bool:
        return bool(self._drafts)

    @property
    def draft_nodes(self) -> tuple[str, ...]:
        return tuple(sorted(self._drafts))

    @property
    def is_modified(self) -> bool:
        return self._modified

    @property
    def coordinates_valid(self) -> bool:
        return self.validation_report().coordinates_valid

    @property
    def setup_ready(self) -> bool:
        return self.validation_report().setup_ready

    @property
    def resource_library(self) -> UserResourceLibrary | None:
        return self._resource_library

    @property
    def resource_audits(self) -> tuple[ResourceSnapshotAudit, ...]:
        return tuple(
            self._resource_audits[kind]
            for kind in ("machine", "nozzle", "material")
            if kind in self._resource_audits
        )

    def set_resource_library(self, library: UserResourceLibrary | None) -> None:
        """Attach the environment's editable library and audit frozen resources."""

        if library is not None and not isinstance(library, UserResourceLibrary):
            raise TypeError("library must be UserResourceLibrary")
        self._resource_library = library
        self.refresh_resource_library()

    def refresh_resource_library(self) -> tuple[ResourceSnapshotAudit, ...]:
        """Re-audit project snapshots without replacing their frozen payloads."""

        self._resource_audits.clear()
        self._resource_audit_failures.clear()
        self._resource_catalogs.clear()
        self._resource_library_diagnostics = ()
        library = self._resource_library
        if library is None:
            return ()
        diagnostics: list[ResourceLibraryDiagnostic] = []
        for kind in ("machine", "nozzle", "material"):
            catalog = library.catalog(kind)
            self._resource_catalogs[kind] = catalog.profiles
            diagnostics.extend(catalog.diagnostics)
        self._resource_library_diagnostics = tuple(diagnostics)
        for kind in ("machine", "nozzle", "material"):
            snapshot = getattr(self._setup, kind)
            if snapshot is None:
                continue
            try:
                self._resource_audits[kind] = library.audit_snapshot(snapshot)
            except (
                AttributeError,
                KeyError,
                ResourceLibraryError,
                TypeError,
                ValueError,
            ) as exc:
                # The project snapshot is the authority for a reopened project.
                # A damaged user-library entry is therefore diagnostic only.
                self._resource_audit_failures[kind] = str(exc)
        return self.resource_audits

    def available_resource_profiles(
        self, resource_type: str
    ) -> tuple[ResourceProfile, ...]:
        """Return immutable templates and editable user profiles for selection."""

        kind = _resource_kind(resource_type)
        if self._resource_library is not None:
            return self._resource_catalogs.get(kind, ())
        if kind == "machine":
            return tuple(builtin_machine_profiles())
        if kind == "nozzle":
            return tuple(builtin_nozzle_profiles())
        return tuple(builtin_material_profiles())

    def resolve_resource_profile(
        self,
        resource_type: str,
        resource_id: str,
    ) -> ResourceProfile:
        """Resolve one selectable profile by its stable identity."""

        kind = _resource_kind(resource_type)
        identifier = str(resource_id).strip()
        if not identifier:
            raise ValueError("resource_id must not be empty")
        if self._resource_library is not None:
            return self._resource_library.resolve(kind, identifier)
        for profile in self.available_resource_profiles(kind):
            if _profile_resource_id(profile) == identifier:
                return profile
        raise KeyError(identifier)

    def save_user_resource(self, profile: ResourceProfile) -> Path:
        """Persist an explicitly edited user profile and refresh library audit."""

        if self._resource_library is None:
            raise ResourceLibraryError("no user resource library is configured")
        path = self._resource_library.save(profile)
        self.refresh_resource_library()
        return path

    def mark_saved(self) -> None:
        self._modified = False

    def attach_cad_model(
        self,
        model: CadModel,
        *,
        mark_modified: bool = True,
    ) -> None:
        """Attach authoritative topology without silently discarding old IDs."""

        if not isinstance(model, CadModel):
            raise TypeError("model must be CadModel")
        candidates = tuple(BodyCandidate.from_body_info(body) for body in model.bodies)
        identifiers = [item.body_id for item in candidates]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("CAD model contains duplicate body IDs")
        self._body_catalog = {item.body_id: item for item in candidates}
        self._source_hash = str(model.source_hash)
        self._source_path = str(Path(model.source_path))
        self._topology_ids = frozenset(
            [
                *(body.body_id for body in model.bodies),
                *(face.face_id for face in model.faces),
                *(edge.edge_id for edge in model.edges),
                *(vertex.vertex_id for vertex in model.vertices),
            ]
        )
        self._cad_model = model
        changed = self._initialise_unassigned_candidates()
        if mark_modified and changed:
            self._modified = True

    def geometry_reference(
        self,
        object_id: str,
        geometry_type: str | None = None,
    ) -> GeometryReference:
        """Create an auditable reference from the attached authoritative CAD."""

        if self._cad_model is None:
            raise ValueError("no CAD model is attached")
        return build_geometry_reference(self._cad_model, object_id, geometry_type)

    def update_cad_model(
        self,
        model: CadModel,
        *,
        tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
    ) -> CadModelRebindResult:
        """Replace the STEP source after unique topology rebinding.

        Every replacement is calculated before controller state changes.  A
        missing or ambiguous reference stays available for diagnosis while its
        Setup node is explicitly Invalid.  Pending editor drafts must be dealt
        with by the caller before a source update.
        """

        if not isinstance(model, CadModel):
            raise TypeError("model must be CadModel")
        if not isinstance(tolerance, RebindTolerance):
            raise TypeError("tolerance must be RebindTolerance")
        if self._drafts:
            raise PendingDraftError(self._drafts)
        source_model = self._cad_model
        if source_model is None:
            raise ValueError("source update requires a previously attached CAD model")
        candidates = tuple(BodyCandidate.from_body_info(body) for body in model.bodies)
        identifiers = [item.body_id for item in candidates]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("CAD model contains duplicate body IDs")

        result = rebind_cad_model_state(
            source_model,
            model,
            self._setup.assignments,
            self._setup.model_coordinate_system,
            self._setup.build_coordinate_system,
            tolerance=tolerance,
        )

        previous_setup = self._setup
        previous_build = previous_setup.build_coordinate_system
        rebound_build = result.build_coordinate_system
        build_transform_changed = bool(
            previous_build is not None
            and rebound_build is not None
            and not previous_build.T_target_from_source.almost_equal(
                rebound_build.T_target_from_source
            )
        )
        build_invalid = BUILD_CS_NODE in result.invalid_nodes
        dirty_nodes = set(previous_setup.dirty_nodes)
        if build_transform_changed or build_invalid:
            dirty_nodes.add(PLACEMENT_NODE)

        revalidated_nodes = {PART_NODE, MODEL_CS_NODE, BUILD_CS_NODE}
        retained_issues = tuple(
            issue
            for issue in previous_setup.issues
            if not _is_source_rebind_issue(issue)
        )
        self._setup = replace(
            previous_setup,
            assignments=result.assignments,
            model_coordinate_system=result.model_coordinate_system,
            build_coordinate_system=result.build_coordinate_system,
            invalid_nodes=(previous_setup.invalid_nodes - revalidated_nodes)
            | result.invalid_nodes,
            dirty_nodes=frozenset(dirty_nodes),
            issues=_merge_issues(retained_issues, result.issues),
            revision=previous_setup.revision + 1,
        )

        self._body_catalog = {item.body_id: item for item in candidates}
        self._source_hash = str(model.source_hash)
        self._source_path = str(Path(model.source_path))
        self._topology_ids = frozenset(
            [
                *(body.body_id for body in model.bodies),
                *(face.face_id for face in model.faces),
                *(edge.edge_id for edge in model.edges),
                *(vertex.vertex_id for vertex in model.vertices),
            ]
        )
        self._cad_model = model
        self._mark_operations_dirty("source_geometry_updated")
        self._modified = True
        return result

    def _initialise_unassigned_candidates(self) -> bool:
        if not self._body_catalog:
            return False
        assignments = self._setup.assignments
        represented = set(
            assignments.part_body_ids
            + assignments.ignored_body_ids
            + assignments.fixture_body_ids
            + assignments.unassigned_body_ids
        )
        new_ids = tuple(
            body_id for body_id in self._body_catalog if body_id not in represented
        )
        if not new_ids:
            return False
        updated = replace(
            assignments,
            unassigned_body_ids=assignments.unassigned_body_ids + new_ids,
        )
        self._setup = replace(
            self._setup,
            assignments=updated,
            revision=self._setup.revision + 1,
        )
        return True

    def body_roles(self) -> Mapping[str, BodyRole]:
        assignments = self._setup.assignments
        roles: dict[str, BodyRole] = {}
        for role, identifiers in (
            (BodyRole.PART, assignments.part_body_ids),
            (BodyRole.IGNORE, assignments.ignored_body_ids),
            (BodyRole.FIXTURE, assignments.fixture_body_ids),
            (BodyRole.UNASSIGNED, assignments.unassigned_body_ids),
        ):
            roles.update((identifier, role) for identifier in identifiers)
        return MappingProxyType(roles)

    def confirm_assignments(
        self,
        part_body_ids: Iterable[str],
        *,
        ignored_body_ids: Iterable[str] = (),
        fixture_body_ids: Iterable[str] = (),
        unassigned_body_ids: Iterable[str] | None = None,
    ) -> ManufacturingObjectAssignments:
        """Atomically confirm body roles; Part must contain a known solid."""

        part = _identifier_tuple(part_body_ids, "part_body_ids")
        ignored = _identifier_tuple(ignored_body_ids, "ignored_body_ids")
        fixture = _identifier_tuple(fixture_body_ids, "fixture_body_ids")
        if not part:
            raise ValueError("Part must contain at least one solid")
        selected = part + ignored + fixture
        if len(set(selected)) != len(selected):
            raise ValueError("a body cannot be assigned to more than one role")
        if self._body_catalog:
            unknown = tuple(item for item in selected if item not in self._body_catalog)
            if unknown:
                raise ValueError("unknown CAD body IDs: " + ", ".join(unknown))
            ineligible = tuple(
                item for item in part if not self._body_catalog[item].is_part_eligible
            )
            if ineligible:
                raise ValueError(
                    "Part accepts closed solids only: " + ", ".join(ineligible)
                )

        if unassigned_body_ids is None:
            unassigned = tuple(
                item for item in self._body_catalog if item not in set(selected)
            )
        else:
            explicit = _identifier_tuple(unassigned_body_ids, "unassigned_body_ids")
            if set(explicit) & set(selected):
                raise ValueError("an explicitly assigned body cannot remain unassigned")
            if self._body_catalog:
                unknown = tuple(
                    item for item in explicit if item not in self._body_catalog
                )
                if unknown:
                    raise ValueError(
                        "unknown unassigned body IDs: " + ", ".join(unknown)
                    )
                missing = tuple(
                    item
                    for item in self._body_catalog
                    if item not in set(selected) and item not in set(explicit)
                )
                unassigned = explicit + missing
            else:
                unassigned = explicit

        assignments = ManufacturingObjectAssignments(
            part_body_ids=part,
            ignored_body_ids=ignored,
            fixture_body_ids=fixture,
            unassigned_body_ids=unassigned,
        )
        if assignments == self._setup.assignments:
            return assignments
        self._setup = replace(
            self._setup,
            assignments=assignments,
            draft_nodes=self._setup.draft_nodes - {PART_NODE},
            invalid_nodes=self._setup.invalid_nodes - {PART_NODE},
            revision=self._setup.revision + 1,
        )
        self._mark_operations_dirty("part_changed")
        self._modified = True
        return assignments

    def confirm_body_roles(
        self,
        roles: Mapping[str, BodyRole | str],
    ) -> ManufacturingObjectAssignments:
        """Convenience adapter for tree editors that expose one role per body."""

        if not isinstance(roles, Mapping):
            raise TypeError("roles must be a mapping")
        grouped: dict[BodyRole, list[str]] = {role: [] for role in BodyRole}
        for raw_id, raw_role in roles.items():
            body_id = str(raw_id).strip()
            try:
                role = (
                    raw_role
                    if isinstance(raw_role, BodyRole)
                    else BodyRole(str(raw_role))
                )
            except ValueError as exc:
                raise ValueError(f"unsupported body role: {raw_role!r}") from exc
            grouped[role].append(body_id)
        return self.confirm_assignments(
            grouped[BodyRole.PART],
            ignored_body_ids=grouped[BodyRole.IGNORE],
            fixture_body_ids=grouped[BodyRole.FIXTURE],
            unassigned_body_ids=grouped[BodyRole.UNASSIGNED],
        )

    def create_operation(
        self,
        operation_type: str = TUBE_OPERATION_TYPE,
        *,
        operation_id: str | None = None,
        name: str = TUBE_OPERATION_NAME,
    ) -> TubeOperationDefinition:
        canonical_type = str(operation_type).strip().lower()
        if canonical_type not in AVAILABLE_TUBE_OPERATION_TYPES:
            raise ValueError(f"unsupported Tube operation type: {operation_type!r}")
        if not self.can_create_operation:
            raise OperationLimitError(
                "the first Tube workbench release supports one interactive operation"
            )
        identifier = (
            _next_operation_id(self._operations)
            if operation_id is None
            else str(operation_id).strip()
        )
        if not identifier:
            raise ValueError("operation_id must not be empty")
        if any(item.operation_id == identifier for item in self._operations):
            raise ValueError(f"duplicate operation_id: {identifier}")
        operation = TubeOperationDefinition(
            operation_id=identifier,
            setup_id=self._setup.setup_id,
            name=name,
            operation_type=canonical_type,
            state=NodeState.DIRTY,
            dirty_reasons=("operation_created",),
        )
        self._operations += (operation,)
        self._modified = True
        return operation

    def select_machine(
        self,
        resource: MachineProfile | ResourceSnapshot,
    ) -> ResourceSnapshot:
        snapshot = _resource_snapshot("machine", resource)
        if snapshot.resource_type == "machine":
            MachineProfile.from_json(snapshot.payload)
        return self._select_resource(MACHINE_NODE, snapshot)

    def select_nozzle(
        self,
        resource: NozzleProfile | ResourceSnapshot,
    ) -> ResourceSnapshot:
        snapshot = _resource_snapshot("nozzle", resource)
        if snapshot.resource_type == "nozzle":
            snapshot.as_nozzle_profile()
        return self._select_resource(NOZZLE_NODE, snapshot)

    def select_material(
        self,
        resource: MaterialProfile | ResourceSnapshot,
    ) -> ResourceSnapshot:
        snapshot = _resource_snapshot("material", resource)
        if snapshot.resource_type == "material":
            snapshot.as_material_profile()
        return self._select_resource(MATERIAL_NODE, snapshot)

    def _select_resource(
        self, node: str, snapshot: ResourceSnapshot
    ) -> ResourceSnapshot:
        current = getattr(self._setup, node)
        if current is not None and current.content_hash == snapshot.content_hash:
            return current
        if node == MACHINE_NODE:
            self._setup = self._setup.with_machine(snapshot)
            self._mark_operations_dirty("machine_changed")
        elif node == NOZZLE_NODE:
            self._setup = self._setup.with_nozzle(snapshot)
            self._mark_operations_dirty("nozzle_changed")
        elif node == MATERIAL_NODE:
            self._setup = self._setup.with_material(snapshot)
            self._mark_operations_dirty("material_changed")
        else:  # pragma: no cover - private call guard
            raise ValueError(node)
        self.refresh_resource_library()
        self._modified = True
        return snapshot

    def begin_coordinate_draft(self, node: str) -> CoordinateFrameDraft:
        canonical_node = _coordinate_node(node)
        applied = (
            self._setup.model_coordinate_system
            if canonical_node == MODEL_CS_NODE
            else self._setup.build_coordinate_system
        )
        draft = CoordinateFrameDraft.from_applied(canonical_node, applied)
        self._drafts[canonical_node] = draft
        return draft

    def coordinate_draft(self, node: str) -> CoordinateFrameDraft:
        canonical_node = _coordinate_node(node)
        draft = self._drafts.get(canonical_node)
        if not isinstance(draft, CoordinateFrameDraft):
            raise DraftNotFoundError(f"no active {canonical_node} draft")
        return draft

    def set_origin_reference(
        self,
        node: str,
        reference: PointReference,
    ) -> CoordinateFrameDraft:
        if not isinstance(reference, PointReference):
            raise TypeError("reference must be PointReference")
        draft = replace(self.coordinate_draft(node), origin_reference=reference)
        self._drafts[draft.node] = draft
        return draft

    def set_direction_reference(
        self,
        node: str,
        axis: str,
        reference: DirectionReference,
    ) -> CoordinateFrameDraft:
        if not isinstance(reference, DirectionReference):
            raise TypeError("reference must be DirectionReference")
        draft = self.coordinate_draft(node)
        canonical_axis = _direction_axis(axis)
        draft = (
            replace(draft, z_direction_reference=reference)
            if canonical_axis == "z"
            else replace(draft, x_direction_reference=reference)
        )
        self._drafts[draft.node] = draft
        return draft

    def confirm_coordinate_reference(
        self,
        node: str,
        component: str,
    ) -> CoordinateFrameDraft:
        draft = self.coordinate_draft(node)
        canonical = str(component).strip().lower()
        if canonical in {"origin", "o"}:
            if draft.origin_reference is None:
                raise ValueError("origin reference has not been selected")
            draft = replace(
                draft,
                origin_reference=replace(draft.origin_reference, confirmed=True),
            )
        elif canonical in {"z", "z_direction"}:
            if draft.z_direction_reference is None:
                raise ValueError("Z reference has not been selected")
            draft = replace(
                draft,
                z_direction_reference=replace(
                    draft.z_direction_reference,
                    confirmed=True,
                ),
            )
        elif canonical in {"x", "x_direction"}:
            if draft.x_direction_reference is None:
                raise ValueError("X reference has not been selected")
            draft = replace(
                draft,
                x_direction_reference=replace(
                    draft.x_direction_reference,
                    confirmed=True,
                ),
            )
        else:
            raise ValueError(f"unsupported coordinate component: {component!r}")
        self._drafts[draft.node] = draft
        return draft

    def flip_direction(self, node: str, axis: str) -> CoordinateFrameDraft:
        draft = self.coordinate_draft(node)
        canonical_axis = _direction_axis(axis)
        reference = (
            draft.z_direction_reference
            if canonical_axis == "z"
            else draft.x_direction_reference
        )
        if reference is None:
            raise ValueError(
                f"{canonical_axis.upper()} reference has not been selected"
            )
        return self.set_direction_reference(
            draft.node,
            canonical_axis,
            replace(reference, flipped=not reference.flipped),
        )

    def set_numeric_origin(
        self,
        node: str,
        point: Sequence[float],
        *,
        input_frame: str | None = None,
        confirmed: bool = False,
    ) -> CoordinateFrameDraft:
        canonical_node = _coordinate_node(node)
        point_in_source = self._point_to_source(
            canonical_node,
            point,
            input_frame=input_frame,
        )
        return self.set_origin_reference(
            canonical_node,
            PointReference("numeric", point_in_source, confirmed=confirmed),
        )

    def set_numeric_direction(
        self,
        node: str,
        axis: str,
        direction: Sequence[float],
        *,
        input_frame: str | None = None,
        confirmed: bool = False,
    ) -> CoordinateFrameDraft:
        canonical_node = _coordinate_node(node)
        direction_in_source = self._direction_to_source(
            canonical_node,
            direction,
            input_frame=input_frame,
        )
        return self.set_direction_reference(
            canonical_node,
            axis,
            DirectionReference(
                "numeric",
                direction_in_source,
                confirmed=confirmed,
            ),
        )

    def _point_to_source(
        self,
        node: str,
        point: Sequence[float],
        *,
        input_frame: str | None,
    ) -> tuple[float, float, float]:
        base = _numeric_input_frame(node, input_frame)
        if base == "source":
            return _vector3(point, "point")
        transform = self._input_frame_from_source(base)
        return transform.inverse().transform_point(point)

    def _direction_to_source(
        self,
        node: str,
        direction: Sequence[float],
        *,
        input_frame: str | None,
    ) -> tuple[float, float, float]:
        base = _numeric_input_frame(node, input_frame)
        if base == "source":
            return _vector3(direction, "direction")
        transform = self._input_frame_from_source(base)
        return transform.inverse().transform_vector(direction)

    def _input_frame_from_source(self, frame: str) -> RigidTransform:
        if frame == "model":
            definition = self._setup.model_coordinate_system
        elif frame == "build":
            definition = self._setup.build_coordinate_system
        else:
            raise ValueError(f"unsupported numeric input frame: {frame!r}")
        if definition is None or not definition.is_valid:
            raise ValueError(
                f"{frame.title()} CS must be applied before numeric conversion"
            )
        return definition.T_target_from_source

    def apply_coordinate_draft(self, node: str) -> CoordinateFrameDefinition:
        canonical_node = _coordinate_node(node)
        draft = self.coordinate_draft(canonical_node)
        applied = draft.to_applied()
        current = (
            self._setup.model_coordinate_system
            if canonical_node == MODEL_CS_NODE
            else self._setup.build_coordinate_system
        )
        if current is not None and _frame_semantics(current) == _frame_semantics(
            applied
        ):
            del self._drafts[canonical_node]
            return current

        if canonical_node == MODEL_CS_NODE:
            self._setup = self._setup.with_model_coordinate_system(applied)
            self._mark_operations_dirty("model_cs_changed")
        else:
            self._setup = self._setup.with_build_coordinate_system(applied)
            self._mark_operations_dirty("build_cs_changed")
        del self._drafts[canonical_node]
        self._modified = True
        return applied

    def begin_placement_draft(
        self,
        *,
        mount_datum_id: str | None = None,
        reference_transform: RigidTransform | None = None,
        adjustment: LocalAdjustment | None = None,
    ) -> PlacementDraft:
        build = self._setup.build_coordinate_system
        machine_hash = (
            None if self._setup.machine is None else self._setup.machine.content_hash
        )
        selected_mount = mount_datum_id or self._setup.mount_datum_id
        selected_adjustment = adjustment or self._setup.placement_adjustment

        if reference_transform is None and self._setup.T_mount_from_build is not None:
            local_inverse = selected_adjustment.to_transform("build").inverse()
            reference_transform = self._setup.T_mount_from_build @ local_inverse
        if reference_transform is None and selected_mount is not None:
            reference_transform = _identity_mount_transform(selected_mount)
        if selected_mount is not None and reference_transform is not None:
            reference_transform = _normalise_mount_transform(
                selected_mount,
                reference_transform,
            )
        draft = PlacementDraft(
            mount_datum_id=selected_mount,
            T_reference_mount_from_build=reference_transform,
            adjustment=selected_adjustment,
            build_cs_revision=None if build is None else build.revision,
            machine_content_hash=machine_hash,
        )
        self._drafts[PLACEMENT_NODE] = draft
        return draft

    def placement_draft(self) -> PlacementDraft:
        draft = self._drafts.get(PLACEMENT_NODE)
        if not isinstance(draft, PlacementDraft):
            raise DraftNotFoundError("no active placement draft")
        return draft

    def set_placement_mount(
        self,
        mount_datum_id: str,
        *,
        reference_transform: RigidTransform | None = None,
    ) -> PlacementDraft:
        draft = self.placement_draft()
        mount_id = str(mount_datum_id).strip()
        if not mount_id:
            raise ValueError("mount_datum_id must not be empty")
        self._validate_mount_id(mount_id)
        reference = reference_transform or _identity_mount_transform(mount_id)
        reference = _normalise_mount_transform(mount_id, reference)
        draft = replace(
            draft,
            mount_datum_id=mount_id,
            T_reference_mount_from_build=reference,
        )
        self._drafts[PLACEMENT_NODE] = draft
        return draft

    def set_placement_adjustment(
        self,
        adjustment: LocalAdjustment | Sequence[float],
        rotation_xyz_rad: Sequence[float] = (0.0, 0.0, 0.0),
    ) -> PlacementDraft:
        draft = self.placement_draft()
        local = (
            adjustment
            if isinstance(adjustment, LocalAdjustment)
            else LocalAdjustment.from_euler_xyz(adjustment, rotation_xyz_rad)
        )
        draft = replace(draft, adjustment=local)
        self._drafts[PLACEMENT_NODE] = draft
        return draft

    def apply_placement_draft(self) -> RigidTransform:
        draft = self.placement_draft()
        build = self._setup.build_coordinate_system
        if build is None or not build.is_valid:
            raise ValueError("Build CS must be valid before Placement can be applied")
        if draft.build_cs_revision != build.revision:
            raise StaleDraftError("Build CS changed after the Placement draft started")
        machine = self._setup.machine
        if machine is None:
            raise ValueError("Machine must be selected before Placement can be applied")
        if draft.machine_content_hash != machine.content_hash:
            raise StaleDraftError("Machine changed after the Placement draft started")
        if not draft.is_complete or draft.mount_datum_id is None:
            raise ValueError("Placement requires a mount datum and reference transform")
        self._validate_mount_id(draft.mount_datum_id)
        transform = draft.T_mount_from_build
        unchanged = bool(
            self._setup.mount_datum_id == draft.mount_datum_id
            and self._setup.T_mount_from_build is not None
            and self._setup.T_mount_from_build.almost_equal(transform)
            and self._setup.placement_adjustment == draft.adjustment
            and PLACEMENT_NODE not in self._setup.dirty_nodes
        )
        if not unchanged:
            self._setup = self._setup.with_placement(
                draft.mount_datum_id,
                transform,
                draft.adjustment,
            )
            self._mark_operations_dirty("placement_changed")
            self._modified = True
        del self._drafts[PLACEMENT_NODE]
        return transform

    def cancel_draft(self, node: str) -> None:
        canonical_node = _draft_node(node)
        if canonical_node not in self._drafts:
            raise DraftNotFoundError(f"no active {canonical_node} draft")
        del self._drafts[canonical_node]

    def discard_all_drafts(self) -> None:
        self._drafts.clear()

    def apply_all_drafts(self) -> None:
        """Apply all active drafts as one transaction in dependency order."""

        if not self._drafts:
            return
        original_setup = self._setup
        original_operations = self._operations
        original_drafts = dict(self._drafts)
        original_modified = self._modified
        try:
            for node in (MODEL_CS_NODE, BUILD_CS_NODE):
                if node in self._drafts:
                    self.apply_coordinate_draft(node)
            if PLACEMENT_NODE in self._drafts:
                # A Placement draft deliberately records applied dependencies.
                # Applying a Build draft in the same transaction makes it stale.
                # Refreshing here is safe because none of the state has escaped.
                placement = self.placement_draft()
                build = self._setup.build_coordinate_system
                placement = replace(
                    placement,
                    build_cs_revision=None if build is None else build.revision,
                    machine_content_hash=(
                        None
                        if self._setup.machine is None
                        else self._setup.machine.content_hash
                    ),
                )
                self._drafts[PLACEMENT_NODE] = placement
                self.apply_placement_draft()
        except Exception:
            self._setup = original_setup
            self._operations = original_operations
            self._drafts = original_drafts
            self._modified = original_modified
            raise

    def _validate_mount_id(self, mount_datum_id: str) -> None:
        profile = self.machine_profile()
        if mount_datum_id not in profile.mount_map:
            raise ValueError(
                f"mount datum {mount_datum_id!r} is not present in selected Machine"
            )

    def machine_profile(self) -> MachineProfile:
        snapshot = self._setup.machine
        if snapshot is None:
            raise ValueError("Machine has not been selected")
        if snapshot.resource_type != "machine":
            raise ValueError("selected resource is not a Machine Profile")
        return MachineProfile.from_json(snapshot.payload)

    def T_machine_from_build(
        self,
        joint_positions: Mapping[str, float] | None = None,
    ) -> RigidTransform:
        placement_state = self.validation_report().state_for(PLACEMENT_NODE)
        if placement_state is not NodeState.VALID:
            raise ValueError(
                "Placement must be Valid before deriving T_machine_from_build "
                f"(current state: {placement_state.value})"
            )
        if self._setup.mount_datum_id is None or self._setup.T_mount_from_build is None:
            raise ValueError("Placement has not been applied")
        T_machine_from_mount = self.machine_profile().mount_transform(
            self._setup.mount_datum_id,
            joint_positions,
        )
        return T_machine_from_mount @ self._setup.T_mount_from_build

    def T_machine_from_source(
        self,
        joint_positions: Mapping[str, float] | None = None,
    ) -> RigidTransform:
        placement_state = self.validation_report().state_for(PLACEMENT_NODE)
        if placement_state is not NodeState.VALID:
            raise ValueError(
                "Placement must be Valid before deriving T_machine_from_source "
                f"(current state: {placement_state.value})"
            )
        build_state = self.validation_report().state_for(BUILD_CS_NODE)
        if build_state is not NodeState.VALID:
            raise ValueError(
                "Build CS must be Valid before deriving T_machine_from_source "
                f"(current state: {build_state.value})"
            )
        build = self._setup.build_coordinate_system
        if build is None or not build.is_valid:
            raise ValueError("Build CS is not valid")
        return self.T_machine_from_build(joint_positions) @ build.T_target_from_source

    def T_model_from_build(self) -> RigidTransform:
        model = self._setup.model_coordinate_system
        build = self._setup.build_coordinate_system
        if model is None or not model.is_valid:
            raise ValueError("Model CS is not valid")
        if build is None or not build.is_valid:
            raise ValueError("Build CS is not valid")
        return model.T_target_from_source @ build.T_target_from_source.inverse()

    def validation_report(self) -> SetupValidationReport:
        invalid_nodes, domain_issues = self._domain_validation()
        effective = replace(
            self._setup,
            draft_nodes=self._setup.draft_nodes | frozenset(self._drafts),
            invalid_nodes=self._setup.invalid_nodes | invalid_nodes,
            issues=_merge_issues(self._setup.issues, domain_issues),
        )
        base = effective.validation_report()
        states = dict(base.node_states)
        operation_issues: list[ValidationIssue] = []
        if not self._operations:
            states[OPERATION_NODE] = NodeState.MISSING
            operation_issues.append(
                ValidationIssue(
                    "TUBE_OPERATION_MISSING",
                    IssueSeverity.WARNING,
                    self._setup.setup_id,
                    {"supported_type": TUBE_OPERATION_TYPE},
                )
            )
        else:
            states[OPERATION_NODE] = _aggregate_operation_state(self._operations)
            if len(self._operations) > MAX_INTERACTIVE_OPERATIONS:
                operation_issues.append(
                    ValidationIssue(
                        "TUBE_OPERATION_COUNT_UNSUPPORTED",
                        IssueSeverity.WARNING,
                        self._setup.setup_id,
                        {
                            "count": len(self._operations),
                            "interactive_limit": MAX_INTERACTIVE_OPERATIONS,
                        },
                    )
                )
            for operation in self._operations:
                if operation.setup_id != self._setup.setup_id:
                    states[OPERATION_NODE] = NodeState.INVALID
                    operation_issues.append(
                        ValidationIssue(
                            "TUBE_OPERATION_SETUP_MISMATCH",
                            IssueSeverity.ERROR,
                            operation.operation_id,
                            {
                                "operation_setup_id": operation.setup_id,
                                "controller_setup_id": self._setup.setup_id,
                            },
                        )
                    )
        merged_issues = _merge_issues(base.issues, operation_issues)
        setup_ready = base.setup_ready and not any(
            issue.severity is IssueSeverity.ERROR for issue in merged_issues
        )
        return SetupValidationReport(
            issues=merged_issues,
            node_states=states,
            coordinates_valid=base.coordinates_valid,
            setup_ready=setup_ready,
        )

    def _domain_validation(self) -> tuple[frozenset[str], tuple[ValidationIssue, ...]]:
        invalid: set[str] = set()
        issues: list[ValidationIssue] = []
        assignments = self._setup.assignments
        if assignments.has_part and self._cad_model is None:
            invalid.add(PART_NODE)
            issues.append(
                ValidationIssue(
                    "CAD_MODEL_MISSING",
                    IssueSeverity.ERROR,
                    self._setup.setup_id,
                    {
                        "node": PART_NODE,
                        "part_body_ids": list(assignments.part_body_ids),
                    },
                )
            )
        elif self._body_catalog:
            known = set(self._body_catalog)
            referenced = (
                assignments.part_body_ids
                + assignments.ignored_body_ids
                + assignments.fixture_body_ids
                + assignments.unassigned_body_ids
            )
            missing = tuple(item for item in referenced if item not in known)
            if missing:
                if set(missing) & set(assignments.part_body_ids):
                    invalid.add(PART_NODE)
                issues.append(
                    ValidationIssue(
                        "CAD_BODY_REFERENCE_MISSING",
                        IssueSeverity.ERROR,
                        self._setup.setup_id,
                        {"body_ids": list(missing)},
                    )
                )
            ineligible = tuple(
                item
                for item in assignments.part_body_ids
                if item in self._body_catalog
                and not self._body_catalog[item].is_part_eligible
            )
            if ineligible:
                invalid.add(PART_NODE)
                issues.append(
                    ValidationIssue(
                        "PART_BODY_NOT_SOLID",
                        IssueSeverity.ERROR,
                        self._setup.setup_id,
                        {"body_ids": list(ineligible)},
                    )
                )

        for node, frame in (
            (MODEL_CS_NODE, self._setup.model_coordinate_system),
            (BUILD_CS_NODE, self._setup.build_coordinate_system),
        ):
            if frame is None or self._cad_model is None:
                continue
            coordinate_issues = audit_coordinate_frame_references(
                frame,
                self._cad_model,
                node=node,
            )
            if coordinate_issues:
                invalid.add(node)
                issues.extend(coordinate_issues)

        if self._setup.machine is not None:
            try:
                profile = self.machine_profile()
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                invalid.add(MACHINE_NODE)
                issues.append(
                    ValidationIssue(
                        "MACHINE_PROFILE_INVALID",
                        IssueSeverity.ERROR,
                        self._setup.machine.resource_id,
                        {"detail": str(exc)},
                    )
                )
            else:
                mount_id = self._setup.mount_datum_id
                if mount_id is not None and mount_id not in profile.mount_map:
                    invalid.add(PLACEMENT_NODE)
                    issues.append(
                        ValidationIssue(
                            "PLACEMENT_MOUNT_MISSING",
                            IssueSeverity.ERROR,
                            mount_id,
                            {"machine_id": profile.profile_id},
                        )
                    )

        mount_id = self._setup.mount_datum_id
        placement = self._setup.T_mount_from_build
        if mount_id is not None and placement is not None:
            if placement.source_frame != "build" or placement.target_frame != mount_id:
                invalid.add(PLACEMENT_NODE)
                issues.append(
                    ValidationIssue(
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
                )

        for kind, audit in self._resource_audits.items():
            if audit.status == "match":
                continue
            node = _resource_node(kind)
            code = (
                "RESOURCE_LIBRARY_DIVERGED"
                if audit.status == "diverged"
                else "RESOURCE_LIBRARY_ENTRY_MISSING"
            )
            issues.append(
                ValidationIssue(
                    code,
                    IssueSeverity.WARNING,
                    audit.resource_id,
                    {
                        "node": node,
                        "resource_type": kind,
                        "library_status": audit.status,
                        "snapshot_content_hash": audit.snapshot_content_hash,
                        "library_content_hash": audit.library_content_hash,
                        "snapshot_retained": True,
                    },
                )
            )
        for kind, detail in self._resource_audit_failures.items():
            snapshot = getattr(self._setup, kind)
            issues.append(
                ValidationIssue(
                    "RESOURCE_LIBRARY_AUDIT_FAILED",
                    IssueSeverity.WARNING,
                    (
                        self._setup.setup_id
                        if snapshot is None
                        else snapshot.resource_id
                    ),
                    {
                        "node": _resource_node(kind),
                        "resource_type": kind,
                        "detail": detail,
                        "snapshot_retained": True,
                    },
                )
            )
        for diagnostic in self._resource_library_diagnostics:
            issues.append(
                ValidationIssue(
                    "RESOURCE_LIBRARY_ENTRY_INVALID",
                    IssueSeverity.WARNING,
                    diagnostic.resource_id or diagnostic.entry_name,
                    {
                        "node": _resource_node(diagnostic.resource_type),
                        **diagnostic.to_json(),
                    },
                )
            )

        return frozenset(invalid), tuple(issues)

    def state_json(self) -> dict[str, Any]:
        """Return a JSON-compatible automation/UI snapshot, including drafts."""

        report = self.validation_report()
        return {
            "schema_version": TUBE_CONTROLLER_SCHEMA_VERSION,
            "setup_id": self._setup.setup_id,
            "setup_name": self._setup.name,
            "source": {
                "path": self._source_path,
                "hash": self._source_hash,
            },
            "capabilities": {
                "available_operation_types": list(AVAILABLE_TUBE_OPERATION_TYPES),
                "max_interactive_operations": MAX_INTERACTIVE_OPERATIONS,
                "fixture_editor_visible": False,
            },
            "body_candidates": [item.to_json() for item in self.body_candidates],
            "assignments": self._setup.assignments.to_json(),
            "resources": {
                "machine": _snapshot_identity_json(self._setup.machine),
                "nozzle": _snapshot_identity_json(self._setup.nozzle),
                "material": _snapshot_identity_json(self._setup.material),
            },
            "resource_library": {
                "configured": self._resource_library is not None,
                "audits": [audit.to_json() for audit in self.resource_audits],
                "audit_failures": [
                    {"resource_type": kind, "detail": detail}
                    for kind, detail in sorted(self._resource_audit_failures.items())
                ],
                "diagnostics": [
                    diagnostic.to_json()
                    for diagnostic in self._resource_library_diagnostics
                ],
            },
            "coordinate_systems": {
                "model": _frame_state_json(self._setup.model_coordinate_system),
                "build": _frame_state_json(self._setup.build_coordinate_system),
            },
            "placement": {
                "mount_datum_id": self._setup.mount_datum_id,
                "applied": self._setup.T_mount_from_build is not None,
            },
            "operations": [item.to_json() for item in self._operations],
            "drafts": {
                node: draft.to_json() for node, draft in sorted(self._drafts.items())
            },
            "validation": report.to_json(),
            "coordinates_valid": report.coordinates_valid,
            "setup_ready": report.setup_ready,
            "has_drafts": self.has_drafts,
            "modified": self._modified,
        }

    def to_json(self, *, allow_drafts: bool = False) -> dict[str, Any]:
        """Return the project-format fragment owned by this controller."""

        if self._drafts and not allow_drafts:
            raise PendingDraftError(self._drafts)
        return {
            "schema_version": TUBE_CONTROLLER_SCHEMA_VERSION,
            "setups": [self._setup.to_json()],
            "operations": [item.to_json() for item in self._operations],
        }

    @classmethod
    def from_json(
        cls,
        payload: Mapping[str, Any],
        *,
        cad_model: CadModel | None = None,
        resource_library: UserResourceLibrary | None = None,
    ) -> TubeSetupController:
        if not isinstance(payload, Mapping):
            raise ValueError("Tube controller payload must be an object")
        version = int(payload.get("schema_version", TUBE_CONTROLLER_SCHEMA_VERSION))
        if version > TUBE_CONTROLLER_SCHEMA_VERSION:
            raise ValueError(f"unsupported Tube controller schema {version}")
        raw_setups = payload.get("setups")
        if raw_setups is None:
            raw_setup = payload.get("setup")
            raw_setups = () if raw_setup is None else (raw_setup,)
        if not isinstance(raw_setups, (list, tuple)):
            raise ValueError("setups must be an array")
        if len(raw_setups) != 1:
            raise ValueError("TubeSetupController requires exactly one Setup")
        raw_operations = payload.get("operations", ())
        if not isinstance(raw_operations, (list, tuple)):
            raise ValueError("operations must be an array")
        raw_catalog = payload.get("body_catalog", ())
        if not isinstance(raw_catalog, (list, tuple)):
            raise ValueError("body_catalog must be an array")
        return cls(
            cad_model=cad_model,
            setup=ManufacturingSetup.from_json(raw_setups[0]),
            operations=tuple(
                TubeOperationDefinition.from_json(item) for item in raw_operations
            ),
            body_catalog=tuple(BodyCandidate.from_json(item) for item in raw_catalog),
            resource_library=resource_library,
        )

    def _mark_operations_dirty(self, reason: str) -> None:
        self._operations = tuple(
            (
                operation.mark_dirty(reason)
                if operation.setup_id == self._setup.setup_id
                else operation
            )
            for operation in self._operations
        )


def _coordinate_node(node: str) -> str:
    canonical = str(node).strip().lower()
    aliases = {
        "model": MODEL_CS_NODE,
        "model_cs": MODEL_CS_NODE,
        "build": BUILD_CS_NODE,
        "build_cs": BUILD_CS_NODE,
    }
    try:
        return aliases[canonical]
    except KeyError as exc:
        raise ValueError(f"unsupported coordinate node: {node!r}") from exc


def _draft_node(node: str) -> str:
    canonical = str(node).strip().lower()
    if canonical in {"placement", PLACEMENT_NODE}:
        return PLACEMENT_NODE
    return _coordinate_node(canonical)


def _direction_axis(axis: str) -> str:
    canonical = str(axis).strip().lower()
    if canonical in {"z", "z_direction"}:
        return "z"
    if canonical in {"x", "x_direction"}:
        return "x"
    raise ValueError(f"direction axis must be X or Z: {axis!r}")


def _numeric_input_frame(node: str, input_frame: str | None) -> str:
    if input_frame is None:
        return "source" if node == MODEL_CS_NODE else "model"
    canonical = str(input_frame).strip().lower().removesuffix("_cs")
    if canonical not in {"source", "model", "build"}:
        raise ValueError(f"unsupported numeric input frame: {input_frame!r}")
    return canonical


def _vector3(values: Sequence[float], name: str) -> tuple[float, float, float]:
    try:
        vector = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain three numbers") from exc
    if len(vector) != 3:
        raise ValueError(f"{name} must contain three numbers")
    return vector  # RigidTransform/Reference performs finite-value validation.


def _identifier_tuple(values: Iterable[str], name: str) -> tuple[str, ...]:
    try:
        sequence = tuple(str(value).strip() for value in values)
    except TypeError as exc:
        raise ValueError(f"{name} must be an iterable of identifiers") from exc
    if any(not value for value in sequence):
        raise ValueError(f"{name} contains an empty identifier")
    if len(set(sequence)) != len(sequence):
        raise ValueError(f"{name} contains duplicate identifiers")
    return sequence


def _resource_kind(value: str) -> str:
    kind = str(value).strip().lower().removesuffix("_profile")
    if kind not in {"machine", "nozzle", "material"}:
        raise ValueError(f"unsupported resource type: {value!r}")
    return kind


def _resource_node(resource_type: str) -> str:
    return {
        "machine": MACHINE_NODE,
        "nozzle": NOZZLE_NODE,
        "material": MATERIAL_NODE,
    }[_resource_kind(resource_type)]


def _profile_resource_id(profile: ResourceProfile) -> str:
    if isinstance(profile, MachineProfile):
        return profile.profile_id
    return profile.resource_id


def _resource_snapshot(
    expected_type: str,
    resource: MachineProfile | NozzleProfile | MaterialProfile | ResourceSnapshot,
) -> ResourceSnapshot:
    snapshot = (
        resource
        if isinstance(resource, ResourceSnapshot)
        else ResourceSnapshot.capture(expected_type, resource)
    )
    if snapshot.resource_type != expected_type:
        raise ValueError(
            f"expected {expected_type} resource, received {snapshot.resource_type}"
        )
    if not snapshot.verify():
        raise ValueError("resource snapshot integrity check failed")
    return snapshot


def _ensure_unique_operation_ids(
    operations: Sequence[TubeOperationDefinition],
) -> None:
    identifiers = [operation.operation_id for operation in operations]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("operations contain duplicate IDs")


def _next_operation_id(operations: Sequence[TubeOperationDefinition]) -> str:
    known = {operation.operation_id for operation in operations}
    index = 1
    while f"tube-operation-{index}" in known:
        index += 1
    return f"tube-operation-{index}"


def _aggregate_operation_state(
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


def _frame_semantics(frame: CoordinateFrameDefinition) -> dict[str, Any]:
    payload = frame.to_json()
    payload.pop("revision", None)
    return payload


def _identity_mount_transform(mount_datum_id: str) -> RigidTransform:
    identity = RigidTransform.identity()
    return RigidTransform(
        identity.matrix,
        source_frame="build",
        target_frame=mount_datum_id,
    )


def _normalise_mount_transform(
    mount_datum_id: str,
    transform: RigidTransform,
) -> RigidTransform:
    if not isinstance(transform, RigidTransform):
        raise TypeError("reference_transform must be RigidTransform")
    if transform.source_frame not in {"", "build"}:
        raise ValueError("T_mount_from_build source frame must be Build CS")
    if transform.target_frame not in {"", "mount", mount_datum_id}:
        raise ValueError("T_mount_from_build target frame must match the mount datum")
    return RigidTransform(
        transform.matrix,
        source_frame="build",
        target_frame=mount_datum_id,
    )


def _merge_issues(
    *groups: Iterable[ValidationIssue],
) -> tuple[ValidationIssue, ...]:
    result: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in (item for group in groups for item in group):
        context_key = repr(issue.to_json()["context"])
        key = (issue.code, issue.object_id, context_key)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return tuple(result)


def _is_source_rebind_issue(issue: ValidationIssue) -> bool:
    """Identify issues owned by the most recent explicit source update."""

    return "_REBIND_" in issue.code


def _snapshot_identity_json(
    snapshot: ResourceSnapshot | None,
) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "resource_type": snapshot.resource_type,
        "resource_id": snapshot.resource_id,
        "profile_version": snapshot.profile_version,
        "content_hash": snapshot.content_hash,
    }


def _frame_state_json(
    frame: CoordinateFrameDefinition | None,
) -> dict[str, Any] | None:
    if frame is None:
        return None
    return {
        "frame_id": frame.frame_id,
        "name": frame.name,
        "revision": frame.revision,
        "confirmed": frame.is_confirmed,
        "valid": frame.is_valid,
        "T_target_from_source": frame.T_target_from_source.to_json(),
    }


__all__ = [
    "AVAILABLE_TUBE_OPERATION_TYPES",
    "BodyCandidate",
    "BodyRole",
    "CoordinateFrameDraft",
    "DraftNotFoundError",
    "MAX_INTERACTIVE_OPERATIONS",
    "OperationLimitError",
    "PendingDraftError",
    "PlacementDraft",
    "StaleDraftError",
    "TUBE_CONTROLLER_SCHEMA_VERSION",
    "TUBE_OPERATION_NAME",
    "TUBE_OPERATION_TYPE",
    "TubeControllerError",
    "TubeSetupController",
]
