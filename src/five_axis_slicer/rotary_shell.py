"""Thin application-shell lifecycle integration for the Rotary workbench."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .manufacturing.rotary_parameters import RotaryOperationDefinition
from .manufacturing.setup import ManufacturingSetup
from .models import CadModel
from .rotary_controller import RotaryController
from .rotary_ui import RotaryPage


def install_rotary_page(host: Any) -> RotaryPage:
    page = RotaryPage(
        host,
        controller=RotaryController(setup=host.tube_page.controller.setup),
        viewer_factory=getattr(host, "_model_viewer_factory", None),
    )
    page.back_requested.connect(host._show_home)
    page.open_step_requested.connect(host.open_model_dialog)
    return page


def controller_for_model(
    previous: RotaryController,
    setup: ManufacturingSetup,
    model: CadModel,
) -> RotaryController:
    previous_hash = None if previous.cad_model is None else previous.cad_model.source_hash
    if previous_hash not in {None, model.source_hash}:
        return RotaryController(model, setup=setup)
    payload = previous.to_json()
    payload["setups"] = [setup.to_json()]
    return RotaryController.from_json(payload, cad_model=model)


def controller_for_project(
    setup: ManufacturingSetup,
    model: CadModel | None,
    operations: Iterable[RotaryOperationDefinition],
) -> RotaryController:
    """Restore operations and explicitly expose absent runtime products as Stale."""

    return RotaryController.reopened_without_generated_products(
        model,
        setup=setup,
        operations=tuple(operations),
    )


def sync_source_update(
    controller: RotaryController,
    setup: ManufacturingSetup,
    model: CadModel,
) -> None:
    if controller.cad_model is None:
        controller.attach_cad_model(model)
    else:
        controller.update_cad_model(model)
    controller.mark_setup_changed(setup, reason="source_geometry_updated")


def rotary_operations(operations: Iterable[Any]) -> tuple[RotaryOperationDefinition, ...]:
    return tuple(item for item in operations if isinstance(item, RotaryOperationDefinition))


def sync_shared_setup(rotary: RotaryController, tube_setup: ManufacturingSetup) -> bool:
    if rotary.setup == tube_setup:
        return False
    rotary.mark_setup_changed(tube_setup, reason="shared_setup_changed")
    return True


def current_operation(controller: RotaryController) -> str:
    return controller.operations[-1].operation_type if controller.operations else "rotary_spiral"


def operation_label(controller: RotaryController) -> str:
    return controller.operations[-1].name if controller.operations else "Rotary Spiral"


def populate_operation_combo(combo: Any, controller: RotaryController) -> None:
    if not controller.operations:
        combo.addItem("Rotary Spiral", "rotary_spiral")
        combo.addItem("Rotary Thin Wall", "rotary_thin_wall")
        combo.addItem("Rotary Around Part", "rotary_around_part")
        return
    for operation in controller.operations:
        combo.addItem(operation.name, operation.operation_type)


__all__ = [
    "controller_for_model",
    "controller_for_project",
    "current_operation",
    "install_rotary_page",
    "operation_label",
    "populate_operation_combo",
    "rotary_operations",
    "sync_shared_setup",
    "sync_source_update",
]
