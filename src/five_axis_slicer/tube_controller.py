"""Qt-independent orchestration for the first Tube manufacturing workflow.

The controller owns the editable workflow state around the immutable
``ManufacturingSetup`` aggregate.  UI code can bind to this class without
learning persistence details or reproducing dependency propagation rules.
Drafts intentionally live outside the applied aggregate: an invalid Apply
never changes the last known-good Setup.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    LocalAdjustment,
    PointReference,
    RigidTransform,
)
from .manufacturing.library import (
    ResourceProfile,
    ResourceSnapshotAudit,
    UserResourceLibrary,
)
from .manufacturing.machine import MachineProfile
from .manufacturing.references import (
    DEFAULT_REBIND_TOLERANCE,
    CadModelRebindResult,
    RebindTolerance,
    rebind_cad_model_state,
)
from .manufacturing.references import geometry_reference as build_geometry_reference
from .manufacturing.resources import (
    MaterialProfile,
    NozzleProfile,
    ResourceSnapshot,
)
from .manufacturing.setup import (
    BUILD_CS_NODE,
    MACHINE_NODE,
    MATERIAL_NODE,
    MODEL_CS_NODE,
    NOZZLE_NODE,
    PART_NODE,
    PLACEMENT_NODE,
    ManufacturingObjectAssignments,
    ManufacturingSetup,
    NodeState,
    SetupValidationReport,
    TubeOperationDefinition,
    ValidationIssue,
)
from .models import CadModel
from .tube_controller_state import TubeControllerStateBoundary
from .tube_drafts import (
    BodyCandidate,
    BodyRole,
    CoordinateFrameDraft,
    DraftNotFoundError,
    OperationLimitError,
    PendingDraftError,
    PlacementDraft,
    StaleDraftError,
    TubeControllerError,
    coordinate_node,
    direction_axis,
    draft_node,
    identity_mount_transform,
    normalise_mount_transform,
    numeric_input_frame,
)
from .tube_resource_context import TubeResourceContext
from .tube_serialization import (
    TUBE_CONTROLLER_SCHEMA_VERSION,
    controller_project_json,
    controller_state_json,
    parse_controller_project,
)
from .tube_validation import (
    TubeValidationContext,
    merge_issues,
)
from .tube_validation import validation_report as build_validation_report

TUBE_OPERATION_TYPE = "tube_thin_wall_indexed"
TUBE_OPERATION_NAME = "Tube Thin-Wall Indexed"
AVAILABLE_TUBE_OPERATION_TYPES = (TUBE_OPERATION_TYPE,)
MAX_INTERACTIVE_OPERATIONS = 1

_COORDINATE_NODES = frozenset({MODEL_CS_NODE, BUILD_CS_NODE})
_DRAFT_NODES = _COORDINATE_NODES | {PLACEMENT_NODE}


class TubeSetupController(TubeControllerStateBoundary):
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
            not isinstance(operation, TubeOperationDefinition) for operation in self._operations
        ):
            raise TypeError("operations must contain TubeOperationDefinition")
        _ensure_unique_operation_ids(self._operations)

        candidates = tuple(body_catalog)
        if any(not isinstance(item, BodyCandidate) for item in candidates):
            raise TypeError("body_catalog must contain BodyCandidate")
        self._body_catalog: dict[str, BodyCandidate] = {item.body_id: item for item in candidates}
        if len(self._body_catalog) != len(candidates):
            raise ValueError("body_catalog contains duplicate body IDs")
        self._source_hash: str | None = None
        self._source_path: str | None = None
        self._cad_model: CadModel | None = None
        self._topology_ids: frozenset[str] = frozenset(self._body_catalog)
        self._drafts: dict[str, CoordinateFrameDraft | PlacementDraft] = {}
        self._resources = TubeResourceContext(resource_library)
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

    def edit_state_token(self) -> tuple[object, ...]:
        """Capture immutable identities used to reject a stale async commit."""

        return self._setup, self._operations, tuple(sorted(self._drafts.items())), self._source_hash

    @property
    def coordinates_valid(self) -> bool:
        return self.validation_report().coordinates_valid

    @property
    def setup_ready(self) -> bool:
        return self.validation_report().setup_ready

    @property
    def resource_library(self) -> UserResourceLibrary | None:
        return self._resources.library

    @property
    def resource_audits(self) -> tuple[ResourceSnapshotAudit, ...]:
        return self._resources.ordered_audits

    def set_resource_library(self, library: UserResourceLibrary | None) -> None:
        """Attach the environment's editable library and audit frozen resources."""

        self._resources.set_library(library)
        self.refresh_resource_library()

    def refresh_resource_library(self) -> tuple[ResourceSnapshotAudit, ...]:
        """Re-audit project snapshots without replacing their frozen payloads."""

        return self._resources.refresh(self._setup)

    def available_resource_profiles(self, resource_type: str) -> tuple[ResourceProfile, ...]:
        """Return immutable templates and editable user profiles for selection."""

        return self._resources.available_profiles(resource_type)

    def resolve_resource_profile(
        self,
        resource_type: str,
        resource_id: str,
    ) -> ResourceProfile:
        """Resolve one selectable profile by its stable identity."""

        return self._resources.resolve(resource_type, resource_id)

    def save_user_resource(self, profile: ResourceProfile) -> Path:
        """Persist an explicitly edited user profile and refresh library audit."""

        path = self._resources.save(profile)
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
        self._attach_cad_authority(model)
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
        result = rebind_cad_model_state(
            source_model,
            model,
            self._setup.assignments,
            self._setup.model_coordinate_system,
            self._setup.build_coordinate_system,
            tolerance=tolerance,
        )

        self._apply_rebind_result(result)
        self._attach_cad_authority(model)
        self._mark_operations_dirty("source_geometry_updated")
        self._modified = True
        return result

    def _attach_cad_authority(self, model: CadModel) -> None:
        candidates = tuple(BodyCandidate.from_body_info(body) for body in model.bodies)
        identifiers = [item.body_id for item in candidates]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("CAD model contains duplicate body IDs")
        self._body_catalog = {item.body_id: item for item in candidates}
        self._source_hash = str(model.source_hash)
        self._source_path = str(Path(model.source_path))
        self._topology_ids = frozenset(
            (
                *identifiers,
                *(face.face_id for face in model.faces),
                *(edge.edge_id for edge in model.edges),
                *(vertex.vertex_id for vertex in model.vertices),
            )
        )
        self._cad_model = model

    def _apply_rebind_result(self, result: CadModelRebindResult) -> None:
        previous = self._setup
        previous_build = previous.build_coordinate_system
        rebound_build = result.build_coordinate_system
        transform_changed = bool(
            previous_build is not None
            and rebound_build is not None
            and not previous_build.T_target_from_source.almost_equal(
                rebound_build.T_target_from_source
            )
        )
        dirty_nodes = set(previous.dirty_nodes)
        if transform_changed or BUILD_CS_NODE in result.invalid_nodes:
            dirty_nodes.add(PLACEMENT_NODE)
        retained_issues = (issue for issue in previous.issues if not _is_source_rebind_issue(issue))
        revalidated = {PART_NODE, MODEL_CS_NODE, BUILD_CS_NODE}
        self._setup = replace(
            previous,
            assignments=result.assignments,
            model_coordinate_system=result.model_coordinate_system,
            build_coordinate_system=result.build_coordinate_system,
            invalid_nodes=(previous.invalid_nodes - revalidated) | result.invalid_nodes,
            dirty_nodes=frozenset(dirty_nodes),
            issues=merge_issues(retained_issues, result.issues),
            revision=previous.revision + 1,
        )

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
        new_ids = tuple(body_id for body_id in self._body_catalog if body_id not in represented)
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
        _validate_assignment_selection(self._body_catalog, part, selected)
        unassigned = _resolve_unassigned_bodies(
            self._body_catalog,
            selected,
            unassigned_body_ids,
        )

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
                role = raw_role if isinstance(raw_role, BodyRole) else BodyRole(str(raw_role))
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

    def _select_resource(self, node: str, snapshot: ResourceSnapshot) -> ResourceSnapshot:
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
        canonical_node = coordinate_node(node)
        applied = (
            self._setup.model_coordinate_system
            if canonical_node == MODEL_CS_NODE
            else self._setup.build_coordinate_system
        )
        draft = CoordinateFrameDraft.from_applied(canonical_node, applied)
        self._drafts[canonical_node] = draft
        return draft

    def coordinate_draft(self, node: str) -> CoordinateFrameDraft:
        canonical_node = coordinate_node(node)
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
        canonical_axis = direction_axis(axis)
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
        canonical_axis = direction_axis(axis)
        reference = (
            draft.z_direction_reference if canonical_axis == "z" else draft.x_direction_reference
        )
        if reference is None:
            raise ValueError(f"{canonical_axis.upper()} reference has not been selected")
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
        canonical_node = coordinate_node(node)
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
        canonical_node = coordinate_node(node)
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
        base = numeric_input_frame(node, input_frame)
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
        base = numeric_input_frame(node, input_frame)
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
            raise ValueError(f"{frame.title()} CS must be applied before numeric conversion")
        return definition.T_target_from_source

    def apply_coordinate_draft(self, node: str) -> CoordinateFrameDefinition:
        canonical_node = coordinate_node(node)
        draft = self.coordinate_draft(canonical_node)
        applied = draft.to_applied()
        current = (
            self._setup.model_coordinate_system
            if canonical_node == MODEL_CS_NODE
            else self._setup.build_coordinate_system
        )
        if current is not None and _frame_semantics(current) == _frame_semantics(applied):
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
        machine_hash = None if self._setup.machine is None else self._setup.machine.content_hash
        selected_mount = mount_datum_id or self._setup.mount_datum_id
        selected_adjustment = adjustment or self._setup.placement_adjustment

        if reference_transform is None and self._setup.T_mount_from_build is not None:
            local_inverse = selected_adjustment.to_transform("build").inverse()
            reference_transform = self._setup.T_mount_from_build @ local_inverse
        if reference_transform is None and selected_mount is not None:
            reference_transform = identity_mount_transform(selected_mount)
        if selected_mount is not None and reference_transform is not None:
            reference_transform = normalise_mount_transform(
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
        reference = reference_transform or identity_mount_transform(mount_id)
        reference = normalise_mount_transform(mount_id, reference)
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
        canonical_node = draft_node(node)
        if canonical_node not in self._drafts:
            raise DraftNotFoundError(f"no active {canonical_node} draft")
        del self._drafts[canonical_node]

    def discard_all_drafts(self) -> None:
        self._drafts.clear()

    @contextmanager
    def draft_resolution_transaction(self, resolution: str | None) -> Iterator[None]:
        """Rollback applied state and drafts when the surrounding commit fails."""

        if resolution not in {None, "apply", "discard"}:
            raise ValueError("draft resolution must be 'apply' or 'discard'")
        if self._drafts and resolution is None:
            raise PendingDraftError(self._drafts)

        # A source refresh can change CAD authority even when no editor draft
        # exists. The transaction therefore protects domain state in both paths.
        original = (
            self._setup,
            self._operations,
            dict(self._drafts),
            self._modified,
            dict(self._body_catalog),
            self._source_hash,
            self._source_path,
            self._cad_model,
            self._topology_ids,
        )
        if self._drafts and resolution == "apply":
            self.apply_all_drafts()
        elif self._drafts:
            self.discard_all_drafts()

        published = False
        try:
            yield
            published = True
        finally:
            if not published:
                (
                    self._setup,
                    self._operations,
                    self._drafts,
                    self._modified,
                    self._body_catalog,
                    self._source_hash,
                    self._source_path,
                    self._cad_model,
                    self._topology_ids,
                ) = original

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
                        None if self._setup.machine is None else self._setup.machine.content_hash
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
            raise ValueError(f"mount datum {mount_datum_id!r} is not present in selected Machine")

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
        context = TubeValidationContext(
            setup=self._setup,
            operations=self._operations,
            body_catalog=self._body_catalog,
            cad_model=self._cad_model,
            draft_nodes=frozenset(self._drafts),
            resource_audits=self._resources.audits,
            resource_audit_failures=self._resources.audit_failures,
            resource_library_diagnostics=self._resources.diagnostics,
        )
        return build_validation_report(
            context,
            operation_type=TUBE_OPERATION_TYPE,
            operation_limit=MAX_INTERACTIVE_OPERATIONS,
        )

    def state_json(self) -> dict[str, Any]:
        """Return a JSON-compatible automation/UI snapshot, including drafts."""

        report = self.validation_report()
        return controller_state_json(
            setup=self._setup,
            operations=self._operations,
            body_candidates=self.body_candidates,
            drafts=self._drafts,
            report=report,
            source_path=self._source_path,
            source_hash=self._source_hash,
            resource_library=self._resources.state_json(),
            operation_types=AVAILABLE_TUBE_OPERATION_TYPES,
            operation_limit=MAX_INTERACTIVE_OPERATIONS,
            modified=self._modified,
        )

    def to_json(self, *, allow_drafts: bool = False) -> dict[str, Any]:
        """Return the project-format fragment owned by this controller."""

        return controller_project_json(
            self._setup, self._operations, self.draft_nodes, allow_drafts=allow_drafts
        )

    @classmethod
    def from_json(
        cls,
        payload: Mapping[str, Any],
        *,
        cad_model: CadModel | None = None,
        resource_library: UserResourceLibrary | None = None,
    ) -> TubeSetupController:
        data = parse_controller_project(payload)
        return cls(
            cad_model=cad_model,
            setup=data.setup,
            operations=data.operations,
            body_catalog=data.body_catalog,
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


def _vector3(values: Sequence[float], name: str) -> tuple[float, float, float]:
    try:
        vector = tuple(float(value) for value in values)
    except (OverflowError, TypeError, ValueError) as exc:
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


def _validate_assignment_selection(
    catalog: Mapping[str, BodyCandidate],
    part_ids: tuple[str, ...],
    selected_ids: tuple[str, ...],
) -> None:
    if not catalog:
        return
    unknown = tuple(item for item in selected_ids if item not in catalog)
    if unknown:
        raise ValueError("unknown CAD body IDs: " + ", ".join(unknown))
    ineligible = tuple(item for item in part_ids if not catalog[item].is_part_eligible)
    if ineligible:
        raise ValueError("Part accepts closed solids only: " + ", ".join(ineligible))


def _resolve_unassigned_bodies(
    catalog: Mapping[str, BodyCandidate],
    selected_ids: tuple[str, ...],
    explicit_ids: Iterable[str] | None,
) -> tuple[str, ...]:
    selected = set(selected_ids)
    if explicit_ids is None:
        return tuple(item for item in catalog if item not in selected)
    explicit = _identifier_tuple(explicit_ids, "unassigned_body_ids")
    if set(explicit) & selected:
        raise ValueError("an explicitly assigned body cannot remain unassigned")
    unknown = tuple(item for item in explicit if catalog and item not in catalog)
    if unknown:
        raise ValueError("unknown unassigned body IDs: " + ", ".join(unknown))
    explicit_set = set(explicit)
    missing = tuple(item for item in catalog if item not in selected and item not in explicit_set)
    return explicit + missing


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
        raise ValueError(f"expected {expected_type} resource, received {snapshot.resource_type}")
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


def _frame_semantics(frame: CoordinateFrameDefinition) -> dict[str, Any]:
    payload = frame.to_json()
    payload.pop("revision", None)
    return payload


def _is_source_rebind_issue(issue: ValidationIssue) -> bool:
    """Identify issues owned by the most recent explicit source update."""

    return "_REBIND_" in issue.code


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
