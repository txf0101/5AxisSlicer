"""Controller mixin for Tube product generation and persisted result state."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from threading import Event
from typing import Any

from .manufacturing.setup import TubeOperationDefinition
from .postprocessing.indexed_tube import GenerationCancelled
from .postprocessing.tube_product import (
    TubeProductResult,
    TubeProductService,
    TubeProductState,
    export_tube_product,
    tube_operation_semantic_sha256,
)


class TubeGenerationControllerMixin:
    """Keep generated-product ownership outside the Setup orchestration class."""

    def _initialise_product_state(self: Any, states: Iterable[TubeProductState]) -> None:
        values = tuple(states)
        if any(not isinstance(item, TubeProductState) for item in values):
            raise TypeError("product_states must contain TubeProductState")
        self._product_states = {item.operation_id: item for item in values}
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
        if self._cad_model is None:
            raise ValueError("Generate requires an attached CAD model")
        nozzle = self._setup.nozzle
        if nozzle is None:
            raise ValueError("Generate requires a selected Nozzle")
        service = TubeProductService(self._product_states.get(operation.operation_id))
        self._generation_cancelled.clear()
        cancel_check = cancelled or self._generation_cancel_requested
        try:
            result = service.generate(
                self._cad_model,
                operation,
                self.machine_profile(),
                nozzle.as_nozzle_profile(),
                source_path=self._source_path,
                cancelled=cancel_check,
            )
        except GenerationCancelled:
            raise
        except Exception as exc:
            self._product_states[operation.operation_id] = TubeProductState(
                operation.operation_id,
                tube_operation_semantic_sha256(operation),
                "error",
                {"error": str(exc)},
            )
            raise
        assert service.state is not None
        self._product_states[operation.operation_id] = service.state
        self._product_results[operation.operation_id] = result
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
        state = self._product_states.get(identifier)
        if state is None or state.status not in {"ready", "warning"}:
            raise ValueError("Generate a current exportable result before export")
        result = self._product_results.get(identifier)
        if result is None:
            raise ValueError("Generate the current operation before export")
        return export_tube_product(result, destination)

    def _mark_product_stale(self: Any, operation: TubeOperationDefinition) -> None:
        state = self._product_states.get(operation.operation_id)
        if state is not None:
            self._product_states[operation.operation_id] = state.stale_for(operation)

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
