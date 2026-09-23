"""Controller mixin for Tube product generation and persisted result state."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import Any

from .manufacturing.setup import NodeState, TubeOperationDefinition
from .models import CadModel
from .tube_generation_context import make_tube_generation_context, tube_input_fingerprint
from .postprocessing.indexed_tube import GenerationCancelled
from .postprocessing.tube_product import (
    TubeProductResult,
    TubeProductService,
    TubeProductState,
    export_tube_product,
    tube_operation_semantic_sha256,
)
from .postprocessing.thermal_program import ThermalProgramParameters


class TubeGenerationControllerMixin:
    """Keep generated-product ownership outside the Setup orchestration class."""

    @property
    def cad_model(self: Any) -> CadModel | None:
        """The authoritative CAD model in Source CS."""
        return self._cad_model

    def _initialise_product_state(self: Any, states: Iterable[TubeProductState]) -> None:
        values = tuple(states)
        if any(not isinstance(item, TubeProductState) for item in values):
            raise TypeError("product_states must contain TubeProductState")
        self._product_states = {
            item.operation_id: (
                replace(item, status="stale")
                if item.status in {"ready", "warning"} and item.input_semantic_sha256 is None
                else item
            )
            for item in values
        }
        self._product_results: dict[str, TubeProductResult] = {}
        self._generation_cancelled = Event()
        self._generation_event_pump: Callable[[], None] | None = None

    def product_state(self: Any, operation_id: str) -> TubeProductState | None:
        return self._product_states.get(str(operation_id).strip())

    def product_result(self: Any, operation_id: str) -> TubeProductResult | None:
        return self._product_results.get(str(operation_id).strip())

    def generate_operation(
        self: Any,
        operation_id: str | None = None,
        *,
        cancelled: Any = None,
    ) -> TubeProductResult:
        operation = self._operation_for_id(operation_id)
        service = TubeProductService(self._product_states.get(operation.operation_id))
        self._generation_cancelled.clear()
        cancel_check = cancelled or self._generation_cancel_requested
        try:
            if cancel_check():
                raise GenerationCancelled("Tube generation cancelled before publication")
            context = make_tube_generation_context(self, operation)
            nozzle = self._setup.nozzle
            assert nozzle is not None
            material = self._setup.material
            assert material is not None
            recommendations = material.as_material_profile().recommendations
            result = service.generate(
                context.model_in_build,
                operation,
                self.machine_profile(),
                nozzle.as_nozzle_profile(),
                source_path=self._source_path,
                T_workpiece_from_build=context.T_workpiece_from_build,
                obstacles=context.obstacles,
                check_ipw=True,
                input_semantic_sha256=context.input_sha256,
                generation_context=context.metadata,
                cancelled=cancel_check,
                thermal_parameters=ThermalProgramParameters(
                    recommendations.nozzle_temperature_c,
                    recommendations.build_plate_temperature_c,
                ),
            )
            if context.input_sha256 != tube_input_fingerprint(
                self, self._operation_for_id(operation.operation_id)
            ):
                self._mark_product_stale(self._operation_for_id(operation.operation_id))
                raise ValueError("Tube inputs changed during generation; regenerate current inputs")
        except GenerationCancelled:
            raise
        except Exception as exc:
            self._product_states[operation.operation_id] = TubeProductState(
                operation.operation_id,
                tube_operation_semantic_sha256(operation),
                "error",
                {"error": str(exc)},
                tube_input_fingerprint(self, operation),
            )
            raise
        assert service.state is not None
        self._product_states[operation.operation_id] = service.state
        self._product_results[operation.operation_id] = result
        self._operations = tuple(
            replace(item, state=NodeState.VALID, dirty_reasons=())
            if item.operation_id == operation.operation_id
            else item
            for item in self._operations
        )
        self._modified = True
        return result

    def cancel_generation(self: Any) -> None:
        self._generation_cancelled.set()

    def set_generation_event_pump(self: Any, callback: Callable[[], None] | None) -> None:
        self._generation_event_pump = callback

    def _generation_cancel_requested(self: Any) -> bool:
        if self._generation_event_pump is not None:
            self._generation_event_pump()
        return self._generation_cancelled.is_set()

    def export_operation_product(self: Any, operation_id: str, destination: str | Path) -> Path:
        identifier = str(operation_id).strip()
        operation = self._operation_for_id(identifier)
        self._mark_product_stale(operation)
        state = self._product_states.get(identifier)
        if state is None or state.status not in {"ready", "warning"}:
            raise ValueError("Generate a current exportable result before export")
        result = self._product_results.get(identifier)
        if result is None:
            raise ValueError("Generate the current operation before export")
        if self.has_drafts or not self.validation_report().setup_ready:
            raise ValueError("Export requires a valid applied Setup")
        if result.input_semantic_sha256 != state.input_semantic_sha256:
            raise ValueError("Generate a current exportable result before export")
        return export_tube_product(result, destination)

    def _mark_product_stale(self: Any, operation: TubeOperationDefinition) -> None:
        state = self._product_states.get(operation.operation_id)
        if state is not None:
            digest = tube_input_fingerprint(self, operation)
            if state.input_semantic_sha256 != digest:
                self._product_states[operation.operation_id] = replace(state, status="stale")

    def _operation_for_id(self: Any, operation_id: str | None) -> TubeOperationDefinition:
        if operation_id is None:
            if len(self._operations) == 1:
                return self._operations[0]
            raise ValueError("operation_id is required when more than one Tube operation exists")
        identifier = str(operation_id).strip()
        for operation in self._operations:
            if operation.operation_id == identifier:
                return operation
        raise ValueError(f"unknown operation_id: {identifier}")


__all__ = ["TubeGenerationControllerMixin"]
