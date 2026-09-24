"""Qt-independent owner for restricted Freeform generation and persistence."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
from threading import Event
from typing import Any

from .curve_generation_context import curve_build_from_source, curve_workpiece_from_build
from .freeform_operation_service import (
    configure_freeform_operation,
    configure_freeform_solid_operation,
    create_freeform_operation,
    rebind_freeform_operation_geometry,
)
from .manufacturing.controller_profile import (
    ControllerProfile,
    OWN_AC_OFFLINE_CONTROLLER,
    ToolChangeStation,
)
from .manufacturing.freeform_parameters import (
    FREEFORM_OPERATION_TYPES,
    FreeformOperationDefinition,
)
from .manufacturing.freeform_solid_parameters import SOLID_FILL_OPERATION_TYPES
from .manufacturing.machine import MachineProfile
from .manufacturing.reference_rebind import DEFAULT_REBIND_TOLERANCE, RebindTolerance
from .manufacturing.setup import ManufacturingSetup
from .models import CadModel
from .postprocessing.freeform_product import (
    FREEFORM_ALGORITHM_VERSION,
    FreeformProductResult,
    FreeformProductState,
    export_freeform_product,
    generate_freeform_product,
    state_from_freeform_result,
)
from .postprocessing.indexed_tube import GenerationCancelled
from .postprocessing.thermal_program import ThermalProgramParameters

FREEFORM_CONTROLLER_SCHEMA_VERSION = 1
MAX_FREEFORM_OPERATIONS = 16


@dataclass(frozen=True, slots=True)
class FreeformControllerCheckpoint:
    setup: ManufacturingSetup
    operations: tuple[FreeformOperationDefinition, ...]
    product_states: tuple[FreeformProductState, ...]
    product_results: tuple[tuple[str, FreeformProductResult], ...]
    controller_profile: ControllerProfile
    modified: bool

    def without_drafts(self):
        return self


class FreeformController:
    def __init__(
        self,
        cad_model: CadModel | None = None,
        *,
        setup: ManufacturingSetup | None = None,
        operations: Iterable[FreeformOperationDefinition] = (),
        product_states: Iterable[FreeformProductState] = (),
        controller_profile: ControllerProfile = OWN_AC_OFFLINE_CONTROLLER,
    ) -> None:
        self._setup = ManufacturingSetup() if setup is None else setup
        self._operations = tuple(operations)
        if any(not isinstance(item, FreeformOperationDefinition) for item in self._operations):
            raise TypeError("operations must contain FreeformOperationDefinition")
        if len(self._operations) > MAX_FREEFORM_OPERATIONS:
            raise ValueError("too many Freeform operations")
        if len({item.operation_id for item in self._operations}) != len(self._operations):
            raise ValueError("duplicate Freeform operation IDs")
        self._product_states = {item.operation_id: item for item in product_states}
        self._product_results: dict[str, FreeformProductResult] = {}
        self._controller_profile = controller_profile
        self._cad_model = cad_model
        self._generation_cancelled = Event()
        self._generation_event_pump: Callable[[], None] | None = None
        self._modified = False
        self._refresh_product_states()

    @property
    def setup(self):
        return self._setup

    @property
    def operations(self):
        return self._operations

    @property
    def cad_model(self):
        return self._cad_model

    @property
    def controller_profile(self) -> ControllerProfile:
        return self._controller_profile

    def configure_tool_change_station(self, station: ToolChangeStation | None) -> None:
        if station is not None and not isinstance(station, ToolChangeStation):
            raise TypeError("station must be ToolChangeStation or None")
        updated = replace(self._controller_profile, tool_change_station=station)
        if updated != self._controller_profile:
            self._controller_profile = updated
            self._mark_all_products_stale()
            self._modified = True

    @property
    def is_modified(self):
        return self._modified

    @property
    def has_drafts(self):
        return bool(self._setup.draft_nodes)

    @property
    def available_operation_types(self):
        return tuple(sorted(FREEFORM_OPERATION_TYPES))

    @property
    def can_create_operation(self):
        return len(self._operations) < MAX_FREEFORM_OPERATIONS

    def validation_report(self):
        return self._setup.validation_report()

    def attach_cad_model(self, model: CadModel, *, mark_modified: bool = True):
        if not isinstance(model, CadModel):
            raise TypeError("model must be CadModel")
        if self._cad_model is not model:
            self._cad_model = model
            if mark_modified:
                self._mark_all_products_stale()
                self._modified = True

    def create_operation(self, operation_type="freeform_surface", *, operation_id=None, name=None):
        if len(self._operations) >= MAX_FREEFORM_OPERATIONS:
            raise ValueError("Freeform operation limit reached")
        operation = create_freeform_operation(
            self._operations, self._setup.setup_id, operation_type, operation_id, name
        )
        self._operations += (operation,)
        self._modified = True
        return operation

    def configure_operation(
        self, *, face_ids, guides, operation_id=None, parameters=None, material_plan=None
    ):
        if self._cad_model is None:
            raise ValueError("no CAD model is attached")
        current = self.operation(operation_id)
        updated = configure_freeform_operation(
            current,
            self._cad_model,
            face_ids=tuple(face_ids),
            guides=tuple(guides),
            parameters=parameters,
            material_plan=material_plan,
        )
        if updated != current:
            self._replace_operation(updated)
            self._mark_product_stale(updated)
            self._modified = True
        return updated

    def configure_solid_operation(
        self, *, solid_geometry, operation_id=None, parameters=None, material_plan=None
    ):
        if self._cad_model is None:
            raise ValueError("no CAD model is attached")
        current = self.operation(operation_id)
        updated = configure_freeform_solid_operation(
            current,
            self._cad_model,
            geometry=dict(solid_geometry),
            parameters=parameters,
            material_plan=material_plan,
        )
        if updated != current:
            self._replace_operation(updated)
            self._mark_product_stale(updated)
            self._modified = True
        return updated

    def set_operation_metadata(self, operation_id, *, name=None, enabled=None):
        current = self.operation(operation_id)
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

    def operation(self, operation_id=None):
        if operation_id is None:
            if len(self._operations) == 1:
                return self._operations[0]
            raise ValueError("operation_id is required unless exactly one operation exists")
        identifier = str(operation_id)
        for item in self._operations:
            if item.operation_id == identifier:
                return item
        raise ValueError(f"unknown operation_id: {identifier}")

    def generate_operation(self, operation_id=None, *, cancelled=None):
        operation = self.operation(operation_id)
        if self._cad_model is None:
            raise ValueError("Generate requires an attached CAD model")
        self._validate_generation(operation)
        digest = self._input_fingerprint(operation)
        self._generation_cancelled.clear()
        check = cancelled or self._generation_cancel_requested
        try:
            machine = self.machine_profile()
            result = generate_freeform_product(
                self._cad_model,
                operation,
                machine,
                self.nozzle_profile(),
                self._controller_profile,
                T_build_from_source=curve_build_from_source(self._setup),
                T_workpiece_from_build=curve_workpiece_from_build(self._setup, machine),
                source_path=self._cad_model.source_path,
                cancelled=check,
                thermal_parameters=self.thermal_parameters(),
            )
        except GenerationCancelled:
            raise
        except Exception as exc:
            self._product_states[operation.operation_id] = FreeformProductState(
                operation.operation_id, operation.semantic_sha256(), "error", {"error": str(exc)}
            )
            raise
        if digest != self._input_fingerprint(self.operation(operation.operation_id)):
            self._mark_all_products_stale()
            raise GenerationCancelled("Freeform inputs changed during generation")
        state = state_from_freeform_result(operation, result)
        payload = dict(state.result_payload or {})
        payload.update(
            generation_input_sha256=digest, generation_context_version="paper-core-freeform-v1"
        )
        self._product_states[operation.operation_id] = replace(state, result_payload=payload)
        self._product_results[operation.operation_id] = result
        self._modified = True
        return result

    def product_state(self, operation_id):
        identifier = str(operation_id)
        state = self._product_states.get(identifier)
        if state is not None:
            operation = self.operation(identifier)
            if state.status in {"ready", "warning"}:
                try:
                    matches = state.parameter_semantic_sha256 == operation.semantic_sha256() and (
                        state.result_payload or {}
                    ).get("generation_input_sha256") == self._input_fingerprint(operation)
                except (OSError, ValueError):
                    matches = False
                if not matches:
                    state = replace(state, status="stale")
                    self._product_states[identifier] = state
        return state

    def product_result(self, operation_id):
        return self._product_results.get(str(operation_id))

    def export_operation_product(self, operation_id, destination, *, cancelled=None):
        operation = self.operation(operation_id)
        state, result = (
            self.product_state(operation.operation_id),
            self.product_result(operation.operation_id),
        )
        if result is None or state is None or state.status not in {"ready", "warning"}:
            raise ValueError("Freeform product is not Ready for offline export")
        return export_freeform_product(result, destination, cancelled=cancelled)

    def cancel_generation(self):
        self._generation_cancelled.set()

    def set_generation_event_pump(self, callback):
        self._generation_event_pump = callback

    def _generation_cancel_requested(self):
        if self._generation_event_pump is not None:
            self._generation_event_pump()
        return self._generation_cancelled.is_set()

    def update_cad_model(self, model, *, tolerance: RebindTolerance = DEFAULT_REBIND_TOLERANCE):
        if self._cad_model is None:
            raise ValueError("source update requires an attached model")
        source = self._cad_model
        self._operations = tuple(
            rebind_freeform_operation_geometry(item, source, model, tolerance=tolerance)
            for item in self._operations
        )
        self._cad_model = model
        self._mark_all_products_stale()
        self._modified = True
        return self._operations

    def mark_setup_changed(self, setup=None, *, reason="setup_changed"):
        if setup is not None:
            self._setup = setup
        self._operations = tuple(
            replace(item, setup_id=self._setup.setup_id).mark_dirty(reason)
            for item in self._operations
        )
        self._mark_all_products_stale()
        self._modified = True

    def machine_profile(self):
        if self._setup.machine is None:
            raise ValueError("Machine has not been selected")
        return MachineProfile.from_json(self._setup.machine.payload)

    def nozzle_profile(self):
        if self._setup.nozzle is None:
            raise ValueError("Nozzle has not been selected")
        return self._setup.nozzle.as_nozzle_profile()

    def material_profile(self):
        if self._setup.material is None:
            raise ValueError("Material has not been selected")
        return self._setup.material.as_material_profile()

    def thermal_parameters(self):
        recommendations = self.material_profile().recommendations
        return ThermalProgramParameters(
            recommendations.nozzle_temperature_c,
            recommendations.build_plate_temperature_c,
        )

    def state_json(self):
        self._refresh_product_states()
        return {
            "schema_version": FREEFORM_CONTROLLER_SCHEMA_VERSION,
            "setup_id": self._setup.setup_id,
            "capabilities": {
                "available_operation_types": list(self.available_operation_types),
                "max_interactive_operations": MAX_FREEFORM_OPERATIONS,
                "product_generation_available": True,
                "offline_only": not self._controller_profile.machine_executable,
            },
            "cad_attached": self._cad_model is not None,
            "operations": [item.to_json() for item in self._operations],
            "products": [item.to_json() for item in self._product_states.values()],
            "controller_profile": self._controller_profile.to_json(),
            "modified": self._modified,
        }

    def to_json(self):
        return {
            "schema_version": FREEFORM_CONTROLLER_SCHEMA_VERSION,
            "setups": [self._setup.to_json()],
            "operations": [item.to_json() for item in self._operations],
            "product_states": [item.to_json() for item in self._product_states.values()],
            "controller_profile": self._controller_profile.to_json(),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any], *, cad_model=None):
        if int(payload.get("schema_version", 0)) != FREEFORM_CONTROLLER_SCHEMA_VERSION:
            raise ValueError("unsupported Freeform controller schema")
        setups = payload.get("setups", ())
        if not isinstance(setups, (list, tuple)) or len(setups) != 1:
            raise ValueError("Freeform controller requires exactly one Setup")
        return cls(
            cad_model,
            setup=ManufacturingSetup.from_json(setups[0]),
            operations=tuple(
                FreeformOperationDefinition.from_json(item)
                for item in payload.get("operations", ())
            ),
            product_states=tuple(
                FreeformProductState.from_json(item) for item in payload.get("product_states", ())
            ),
            controller_profile=ControllerProfile.from_json(payload.get("controller_profile", {})),
        )

    def command_checkpoint(self):
        return FreeformControllerCheckpoint(
            self._setup,
            self._operations,
            tuple(self._product_states.values()),
            tuple(sorted(self._product_results.items())),
            self._controller_profile,
            self._modified,
        )

    def restore_command_checkpoint(self, checkpoint):
        self._setup, self._operations = checkpoint.setup, checkpoint.operations
        self._product_states = {item.operation_id: item for item in checkpoint.product_states}
        self._product_results = dict(checkpoint.product_results)
        self._controller_profile, self._modified = (
            checkpoint.controller_profile,
            checkpoint.modified,
        )

    def command_applied_token(self):
        return (
            self._setup,
            self._operations,
            tuple(
                (key, value.parameter_semantic_sha256, value.status)
                for key, value in sorted(self._product_states.items())
            ),
            self._controller_profile,
            self._modified,
        )

    def fork(self):
        candidate = FreeformController(
            self._cad_model,
            setup=self._setup,
            operations=self._operations,
            product_states=self._product_states.values(),
            controller_profile=self._controller_profile,
        )
        candidate._product_results = dict(self._product_results)
        candidate._modified = self._modified
        candidate._generation_cancelled = self._generation_cancelled
        candidate._generation_event_pump = self._generation_event_pump
        return candidate

    def publish_from(self, candidate):
        self.restore_command_checkpoint(candidate.command_checkpoint())
        self._cad_model = candidate._cad_model

    def _validate_generation(self, operation):
        model = self._cad_model
        if model is None:
            raise ValueError("Freeform Generate requires an attached CAD model")
        geometry_complete = (
            operation.solid_geometry is not None
            if operation.operation_type in SOLID_FILL_OPERATION_TYPES
            else operation.geometry.is_complete
        )
        if not operation.enabled or operation.setup_id != self._setup.setup_id or not geometry_complete:
            raise ValueError("Freeform Generate requires a complete enabled operation")
        report = self._setup.validation_report()
        if not report.setup_ready or report.has_errors or self._setup.draft_nodes:
            raise ValueError("Freeform Generate requires a valid applied Setup")
        source = Path(model.source_path)
        if (
            source.is_file()
            and hashlib.sha256(source.read_bytes()).hexdigest() != model.source_hash
        ):
            raise ValueError("CAD source changed on disk")
        if self._controller_profile.machine_profile_id != self.machine_profile().profile_id:
            raise ValueError("controller profile does not match selected machine")

    def _input_fingerprint(self, operation):
        source = Path(self._cad_model.source_path) if self._cad_model is not None else None
        payload = {
            "version": "paper-core-freeform-v1",
            "algorithm": FREEFORM_ALGORITHM_VERSION,
            "operation": operation.semantic_sha256(),
            "setup": self._setup.to_json(),
            "controller": self._controller_profile.semantic_sha256(),
            "source": None if self._cad_model is None else self._cad_model.source_hash,
            "source_on_disk": hashlib.sha256(source.read_bytes()).hexdigest()
            if source is not None and source.is_file()
            else None,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _replace_operation(self, updated):
        self._operations = tuple(
            updated if item.operation_id == updated.operation_id else item
            for item in self._operations
        )

    def _mark_product_stale(self, operation):
        state = self._product_states.get(operation.operation_id)
        if state is not None:
            self._product_states[operation.operation_id] = state.stale_for(operation)

    def _mark_all_products_stale(self):
        self._product_states = {
            key: replace(value, status="stale") for key, value in self._product_states.items()
        }

    def _refresh_product_states(self):
        for operation in self._operations:
            self.product_state(operation.operation_id)


__all__ = [
    "FREEFORM_CONTROLLER_SCHEMA_VERSION",
    "FreeformController",
    "FreeformControllerCheckpoint",
]
