"""Thin integration helpers that keep Planar out of the legacy UI monolith."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .manufacturing.planar_parameters import PlanarOperationDefinition
from .manufacturing.setup import ManufacturingSetup, TubeOperationDefinition
from .models import CadModel
from .planar_controller import PlanarController
from .planar_ui import PlanarPage


def install_planar_page(host: Any) -> PlanarPage:
    page = PlanarPage(
        host,
        controller=PlanarController(setup=host.tube_page.controller.setup),
        viewer_factory=getattr(host, "_model_viewer_factory", None),
    )
    page.back_requested.connect(host._show_home)
    page.open_step_requested.connect(host.open_model_dialog)
    return page


def controller_for_model(
    previous: PlanarController,
    setup: ManufacturingSetup,
    model: CadModel,
) -> PlanarController:
    previous_hash = None if previous.cad_model is None else previous.cad_model.source_hash
    if previous_hash not in {None, model.source_hash}:
        return PlanarController(model, setup=setup)
    payload = previous.to_json()
    payload["setups"] = [setup.to_json()]
    return PlanarController.from_json(payload, cad_model=model)


def sync_source_update(
    controller: PlanarController,
    setup: ManufacturingSetup,
    model: CadModel,
) -> None:
    if controller.cad_model is None:
        controller.attach_cad_model(model)
    else:
        controller.update_cad_model(model)
    controller.mark_setup_changed(setup, reason="source_geometry_updated")


def split_operations(
    operations: Iterable[Any],
) -> tuple[tuple[TubeOperationDefinition, ...], tuple[PlanarOperationDefinition, ...]]:
    values = tuple(operations)
    return (
        tuple(item for item in values if isinstance(item, TubeOperationDefinition)),
        tuple(item for item in values if isinstance(item, PlanarOperationDefinition)),
    )


def sync_shared_setup(planar: PlanarController, tube_setup: ManufacturingSetup) -> bool:
    if planar.setup == tube_setup:
        return False
    planar.mark_setup_changed(tube_setup, reason="shared_setup_changed")
    return True


def operation_label(controller: PlanarController) -> str:
    return controller.operations[-1].name if controller.operations else "Planar Region"


def populate_operation_combo(combo: Any, controller: PlanarController) -> None:
    if not controller.operations:
        combo.addItem("Planar Region", "planar_region")
        return
    for operation in controller.operations:
        combo.addItem(operation.name, operation.operation_type)


def active_session_page(host: Any) -> Any:
    if host.current_workbench_key == "tube":
        return host.tube_page
    if host.current_workbench_key == "planar":
        return host.planar_page
    return host.session_page


def current_operation(controller: PlanarController) -> str:
    return controller.operations[-1].operation_type if controller.operations else "planar_region"


def page_name(host: Any) -> str:
    current = host.stack.currentWidget()
    if current is host.result_page:
        return "results"
    if current is host.tube_page:
        return "tube"
    if current is host.planar_page:
        return "planar"
    if current is host.session_page:
        return "session"
    return "workbench"


__all__ = [
    "controller_for_model",
    "active_session_page",
    "current_operation",
    "install_planar_page",
    "operation_label",
    "page_name",
    "populate_operation_combo",
    "split_operations",
    "sync_shared_setup",
    "sync_source_update",
]
