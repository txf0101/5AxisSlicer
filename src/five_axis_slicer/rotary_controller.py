"""Qt-free Rotary operation lifecycle and generated-product ownership."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from threading import Event
from typing import Any

from .algorithms.rotary import RotaryPlanningError
from .kinematics.xyzac import XYZACInverseKinematicsError
from .manufacturing.coordinates import RigidTransform
from .manufacturing.machine import MachineProfile
from .manufacturing.references import DEFAULT_REBIND_TOLERANCE, RebindTolerance
from .manufacturing.resources import NozzleProfile
from .manufacturing.rotary_parameters import (
    ROTARY_OPERATION_TYPES,
    RotaryGeometrySelection,
    RotaryOperationDefinition,
    RotaryProcessParameters,
)
from .manufacturing.setup import ManufacturingSetup, NodeState, PLACEMENT_NODE
from .models import CadModel
from .postprocessing.indexed_tube import GenerationCancelled
from .postprocessing.rotary_product import (
    RotaryProductResult,
    RotaryProductState,
    export_rotary_product,
    generate_rotary_product,
    state_from_rotary_result,
)
from .rotary_generation_context import (
    record_rotary_input,
    refresh_rotary_state,
    rotary_build_from_source,
    rotary_collision_boxes,
    rotary_input_fingerprint,
    rotary_workpiece_from_build,
    validate_rotary_generation_inputs,
)
from .rotary_operation_service import (
    configure_rotary_operation,
    create_rotary_operation,
    rebind_rotary_operation_geometry,
)


ROTARY_CONTROLLER_SCHEMA_VERSION = 1
MAX_ROTARY_OPERATIONS = 12


@dataclass(frozen=True, slots=True)
class RotaryControllerCheckpoint:
    setup: ManufacturingSetup
    operations: tuple[RotaryOperationDefinition, ...]
    product_states: tuple[RotaryProductState, ...]
    product_results: tuple[tuple[str, RotaryProductResult], ...]
    modified: bool

    def without_drafts(self) -> "RotaryControllerCheckpoint":
        return self


class RotaryController:
    def __init__(
        self,
        cad_model: CadModel | None = None,
        *,
        setup: ManufacturingSetup | None = None,
        operations: Iterable[RotaryOperationDefinition] = (),
        product_states: Iterable[RotaryProductState] = (),
    ) -> None:
        self._setup = ManufacturingSetup() if setup is None else setup
        self._operations = tuple(operations)
        if any(not isinstance(item, RotaryOperationDefinition) for item in self._operations):
            raise TypeError("operations must contain RotaryOperationDefinition")
        if len(self._operations) > MAX_ROTARY_OPERATIONS:
            raise ValueError(
                f"Rotary workbench supports at most {MAX_ROTARY_OPERATIONS} operations"
            )
        identifiers = [item.operation_id for item in self._operations]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("operations contain duplicate IDs")
        states = tuple(product_states)
        if any(not isinstance(item, RotaryProductState) for item in states):
            raise TypeError("product_states must contain RotaryProductState")
        self._product_states = {item.operation_id: item for item in states}
        if not set(self._product_states).issubset(identifiers):
            raise ValueError("product state refers to an unknown Rotary operation")
        self._product_results: dict[str, RotaryProductResult] = {}
        self._cad_model: CadModel | None = None
        self._generation_cancelled = Event()
        self._generation_event_pump: Callable[[], None] | None = None
        self._modified = False
        if cad_model is not None:
            self.attach_cad_model(cad_model, mark_modified=False)
        self._refresh_product_states()

    @property
    def setup(self) -> ManufacturingSetup:
        return self._setup

    @property
    def operations(self) -> tuple[RotaryOperationDefinition, ...]:
        return self._operations

    @property
    def cad_model(self) -> CadModel | None:
        return self._cad_model

    @property
    def is_modified(self) -> bool:
        return self._modified

    @property
    def has_drafts(self) -> bool:
        return bool(self._setup.draft_nodes)

    @property
    def coordinates_valid(self) -> bool:
        return self._setup.coordinates_valid

    @property
    def setup_ready(self) -> bool:
        return self._setup.setup_ready

    @property
    def available_operation_types(self) -> tuple[str, ...]:
        return tuple(sorted(ROTARY_OPERATION_TYPES))

    @property
    def can_create_operation(self) -> bool:
        return len(self._operations) < MAX_ROTARY_OPERATIONS

    def validation_report(self):
        return self._setup.validation_report()

    def attach_cad_model(self, model: CadModel, *, mark_modified: bool = True) -> None:
        if not isinstance(model, CadModel):
            raise TypeError("model must be CadModel")
        changed = self._cad_model is not model
        self._cad_model = model
        if changed and mark_modified:
            self._mark_all_products_stale()
            self._modified = True

    def create_operation(
        self,
        operation_type: str = "rotary_spiral",
        *,
        operation_id: str | None = None,
        name: str | None = None,
    ) -> RotaryOperationDefinition:
        if not self.can_create_operation:
            raise ValueError(
                f"Rotary workbench supports at most {MAX_ROTARY_OPERATIONS} operations"
            )
        operation = create_rotary_operation(
            self._operations,
            self._setup.setup_id,
            operation_type,
            operation_id,
            name,
        )
        self._operations += (operation,)
        self._modified = True
        return operation

    def configure_operation(
        self,
        *,
        operation_id: str | None = None,
        geometry: RotaryGeometrySelection | None = None,
        parameters: RotaryProcessParameters | None = None,
    ) -> RotaryOperationDefinition:
        current = self._operation_by_id(operation_id)
        updated = configure_rotary_operation(
            current,
            geometry=geometry,
            parameters=parameters,
        )
        if updated != current:
            self._replace_operation(updated)
            self._mark_product_stale(updated)
            self._modified = True
        return updated

    def set_operation_metadata(
        self,
        operation_id: str,
        *,
        name: str | None = None,
        enabled: bool | None = None,
    ) -> RotaryOperationDefinition:
        current = self._operation_by_id(operation_id)
        updated = replace(
            current,
            name=current.name if name is None else name,
            enabled=current.enabled if enabled is None else enabled,
        )
        if updated != current:
            updated = updated.mark_dirty("operation_metadata_changed")
            self._replace_operation(updated)
            self._mark_product_stale(updated)
            self._modified = True
        return updated

    def operation(self, operation_id: str | None = None) -> RotaryOperationDefinition:
        return self._operation_by_id(operation_id)

    def product_state(self, operation_id: str) -> RotaryProductState | None:
        identifier = str(operation_id).strip()
        state = self._product_states.get(identifier)
        if state is not None:
            state = refresh_rotary_state(
                state,
                self._setup,
                self._cad_model,
                self._operation_by_id(identifier),
            )
            self._product_states[identifier] = state
        return state

    def product_result(self, operation_id: str) -> RotaryProductResult | None:
        return self._product_results.get(str(operation_id).strip())

    def generate_operation(
        self,
        operation_id: str | None = None,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> RotaryProductResult:
        operation = self._operation_by_id(operation_id)
        if self._cad_model is None:
            raise ValueError("Generate requires an attached CAD model")
        self._generation_cancelled.clear()
        cancel_check = cancelled or self._generation_cancel_requested
        try:
            validate_rotary_generation_inputs(self._setup, self._cad_model, operation)
            input_digest = rotary_input_fingerprint(self._setup, self._cad_model, operation)
            machine = self.machine_profile()
            build_from_source = rotary_build_from_source(self._setup)
            result = generate_rotary_product(
                self._cad_model,
                operation,
                machine,
                self.nozzle_profile(),
                T_build_from_source=build_from_source,
                T_workpiece_from_build=rotary_workpiece_from_build(self._setup, machine),
                source_path=self._cad_model.source_path,
                obstacles=rotary_collision_boxes(
                    self._setup,
                    self._cad_model,
                    build_from_source,
                ),
                check_ipw=True,
                cancelled=cancel_check,
            )
        except GenerationCancelled:
            raise
        except Exception as exc:
            issue = _generation_issue_payload(exc, operation.operation_id)
            self._product_states[operation.operation_id] = RotaryProductState(
                operation.operation_id,
                operation.semantic_sha256(),
                "error",
                {"error": str(exc), "issue": issue},
            )
            raise
        self._check_generation_input(operation.operation_id, input_digest)
        state = record_rotary_input(state_from_rotary_result(operation, result), input_digest)
        self._product_states[operation.operation_id] = state
        self._product_results[operation.operation_id] = result
        self._modified = True
        return result

    def export_operation_product(
        self,
        operation_id: str | None,
        destination: str,
        *,
        cancelled: Callable[[], bool] | None = None,
    ):
        operation = self._operation_by_id(operation_id)
        state = self.product_state(operation.operation_id)
        result = self._product_results.get(operation.operation_id)
        if result is None or state is None or state.status not in {"ready", "warning"}:
            raise ValueError("Rotary product is not Ready for export")
        if not str(destination).strip():
            raise ValueError("destination is required")
        return export_rotary_product(result, destination, cancelled=cancelled)

    def cancel_generation(self) -> None:
        self._generation_cancelled.set()

    def set_generation_event_pump(self, callback: Callable[[], None] | None) -> None:
        self._generation_event_pump = callback

    def _generation_cancel_requested(self) -> bool:
        if self._generation_event_pump is not None:
            self._generation_event_pump()
        return self._generation_cancelled.is_set()

    def update_cad_model(
        self,
        model: CadModel,
        *,
        tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE,
    ) -> tuple[RotaryOperationDefinition, ...]:
        if self._cad_model is None:
            raise ValueError("source update requires a previously attached CAD model")
        source = self._cad_model
        self._operations = tuple(
            rebind_rotary_operation_geometry(item, source, model, tolerance=tolerance)
            for item in self._operations
        )
        self._cad_model = model
        self._mark_all_products_stale()
        self._modified = True
        return self._operations

    def mark_setup_changed(
        self,
        setup: ManufacturingSetup | None = None,
        *,
        reason: str = "setup_changed",
    ) -> None:
        if setup is not None:
            if not isinstance(setup, ManufacturingSetup):
                raise TypeError("setup must be ManufacturingSetup")
            self._setup = setup
        self._operations = tuple(item.mark_dirty(reason) for item in self._operations)
        self._mark_all_products_stale()
        self._modified = True

    def machine_profile(self) -> MachineProfile:
        snapshot = self._setup.machine
        if snapshot is None or snapshot.resource_type != "machine":
            raise ValueError("Machine has not been selected")
        return MachineProfile.from_json(snapshot.payload)

    def nozzle_profile(self) -> NozzleProfile:
        if self._setup.nozzle is None:
            raise ValueError("Nozzle has not been selected")
        return self._setup.nozzle.as_nozzle_profile()

    def T_machine_from_build(
        self,
        joint_positions: Mapping[str, float] | None = None,
    ) -> RigidTransform:
        state = self.validation_report().state_for(PLACEMENT_NODE)
        if state is not NodeState.VALID:
            raise ValueError("Placement must be Valid before deriving machine coordinates")
        if self._setup.mount_datum_id is None or self._setup.T_mount_from_build is None:
            raise ValueError("Placement has not been applied")
        return (
            self.machine_profile().mount_transform(self._setup.mount_datum_id, joint_positions)
            @ self._setup.T_mount_from_build
        )

    def state_json(self) -> dict[str, Any]:
        self._refresh_product_states()
        return {
            "schema_version": ROTARY_CONTROLLER_SCHEMA_VERSION,
            "setup_id": self._setup.setup_id,
            "capabilities": {
                "available_operation_types": list(self.available_operation_types),
                "max_interactive_operations": MAX_ROTARY_OPERATIONS,
                "product_generation_available": True,
            },
            "cad_attached": self._cad_model is not None,
            "operations": [item.to_json() for item in self._operations],
            "products": [item.to_json() for item in self._product_states.values()],
            "modified": self._modified,
        }

    def command_checkpoint(self) -> RotaryControllerCheckpoint:
        return RotaryControllerCheckpoint(
            self._setup,
            self._operations,
            tuple(self._product_states.values()),
            tuple(sorted(self._product_results.items())),
            self._modified,
        )

    def restore_command_checkpoint(self, checkpoint: RotaryControllerCheckpoint) -> None:
        if not isinstance(checkpoint, RotaryControllerCheckpoint):
            raise TypeError("checkpoint must be RotaryControllerCheckpoint")
        self._setup = checkpoint.setup
        self._operations = checkpoint.operations
        self._product_states = {item.operation_id: item for item in checkpoint.product_states}
        self._product_results = dict(checkpoint.product_results)
        self._modified = checkpoint.modified

    def command_applied_token(self) -> tuple[object, ...]:
        return (
            self._setup,
            self._operations,
            tuple(
                (key, value.parameter_semantic_sha256, value.status)
                for key, value in sorted(self._product_states.items())
            ),
            self._modified,
        )

    def fork(self) -> "RotaryController":
        candidate = RotaryController(
            self._cad_model,
            setup=self._setup,
            operations=self._operations,
            product_states=self._product_states.values(),
        )
        candidate._modified = self._modified
        candidate._product_results = dict(self._product_results)
        candidate._generation_cancelled = self._generation_cancelled
        candidate._generation_event_pump = self._generation_event_pump
        return candidate

    def publish_from(self, candidate: "RotaryController") -> None:
        if not isinstance(candidate, RotaryController):
            raise TypeError("candidate must be RotaryController")
        self._setup = candidate._setup
        self._operations = candidate._operations
        self._cad_model = candidate._cad_model
        self._product_states = dict(candidate._product_states)
        self._product_results = dict(candidate._product_results)
        self._modified = candidate._modified

    def to_json(self) -> dict[str, Any]:
        self._refresh_product_states()
        return {
            "schema_version": ROTARY_CONTROLLER_SCHEMA_VERSION,
            "setups": [self._setup.to_json()],
            "operations": [item.to_json() for item in self._operations],
            "product_states": [item.to_json() for item in self._product_states.values()],
        }

    @classmethod
    def from_json(
        cls,
        payload: Mapping[str, Any],
        *,
        cad_model: CadModel | None = None,
    ) -> "RotaryController":
        if not isinstance(payload, Mapping):
            raise ValueError("Rotary controller payload must be an object")
        version = int(payload.get("schema_version", ROTARY_CONTROLLER_SCHEMA_VERSION))
        if version > ROTARY_CONTROLLER_SCHEMA_VERSION:
            raise ValueError(f"unsupported Rotary controller schema {version}")
        setups = payload.get("setups")
        if setups is None:
            setup = payload.get("setup")
            setups = () if setup is None else (setup,)
        operations_payload = payload.get("operations", ())
        states_payload = payload.get("product_states", payload.get("products", ()))
        if not isinstance(setups, list | tuple) or len(setups) != 1:
            raise ValueError("RotaryController requires exactly one Setup")
        operations = tuple(
            RotaryOperationDefinition.from_json(item) for item in operations_payload
        )
        # Generated Toolpath/G-code objects are runtime products and are not
        # reconstructed from project metadata.  Persisted qualifications must
        # therefore reopen as Stale even when their input digest still matches.
        states = tuple(
            replace(state, status="stale")
            if state.status in {"ready", "warning"}
            else state
            for state in (RotaryProductState.from_json(item) for item in states_payload)
        )
        return cls(
            cad_model,
            setup=ManufacturingSetup.from_json(setups[0]),
            operations=operations,
            product_states=states,
        )

    @classmethod
    def reopened_without_generated_products(
        cls,
        cad_model: CadModel | None,
        *,
        setup: ManufacturingSetup,
        operations: Iterable[RotaryOperationDefinition],
    ) -> "RotaryController":
        """Reopen persisted operations while explicitly withdrawing runtime results."""

        values = tuple(operations)
        states = tuple(
            RotaryProductState(
                item.operation_id,
                item.semantic_sha256(),
                "stale",
                {
                    "operation_type": item.operation_type,
                    "stale_reason": "generated_product_not_embedded",
                },
            )
            for item in values
        )
        return cls(cad_model, setup=setup, operations=values, product_states=states)

    def _check_generation_input(self, operation_id: str, expected: str) -> None:
        operation = self._operation_by_id(operation_id)
        try:
            assert self._cad_model is not None
            validate_rotary_generation_inputs(self._setup, self._cad_model, operation)
            matches = rotary_input_fingerprint(self._setup, self._cad_model, operation) == expected
        except (ValueError, OSError, AssertionError):
            matches = False
        if not matches:
            self._mark_all_products_stale()
            raise GenerationCancelled("Rotary inputs changed during generation; regenerate")

    def _refresh_product_states(self) -> None:
        for operation in self._operations:
            self.product_state(operation.operation_id)

    def _mark_product_stale(self, operation: RotaryOperationDefinition) -> None:
        state = self._product_states.get(operation.operation_id)
        if state is not None:
            self._product_states[operation.operation_id] = state.stale_for(operation)

    def _mark_all_products_stale(self) -> None:
        self._product_states = {
            key: replace(value, status="stale")
            for key, value in self._product_states.items()
        }

    def _replace_operation(self, updated: RotaryOperationDefinition) -> None:
        self._operations = tuple(
            updated if item.operation_id == updated.operation_id else item
            for item in self._operations
        )

    def _operation_by_id(self, operation_id: str | None) -> RotaryOperationDefinition:
        if operation_id is None:
            if len(self._operations) == 1:
                return self._operations[0]
            raise ValueError("operation_id is required unless exactly one Rotary operation exists")
        identifier = str(operation_id).strip()
        for item in self._operations:
            if item.operation_id == identifier:
                return item
        raise ValueError(f"unknown operation_id: {identifier}")


def _generation_issue_payload(exc: Exception, operation_id: str) -> dict[str, Any]:
    if isinstance(exc, RotaryPlanningError):
        details = list(exc.context)
        return {
            "code": exc.code,
            "severity": "error",
            "object_id": details[0] if details else operation_id,
            "context": {"details": details},
        }
    if isinstance(exc, XYZACInverseKinematicsError):
        return {
            "code": exc.code,
            "severity": "error",
            "object_id": exc.point_id or operation_id,
            "context": {"detail": exc.detail},
        }
    return {
        "code": "rotary.generation_failed",
        "severity": "error",
        "object_id": operation_id,
        "context": {
            "exception_type": type(exc).__name__,
            "detail": str(exc),
        },
    }


__all__ = [
    "MAX_ROTARY_OPERATIONS",
    "ROTARY_CONTROLLER_SCHEMA_VERSION",
    "RotaryController",
    "RotaryControllerCheckpoint",
]
