"""Thin lifecycle integration for the Curve workbench."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .curve_controller import CurveController
from .curve_ui import CurvePage
from .manufacturing.curve_parameters import CurveOperationDefinition
from .manufacturing.setup import ManufacturingSetup, TubeOperationDefinition
from .manufacturing.planar_parameters import PlanarOperationDefinition
from .models import CadModel


def install_curve_page(host: Any) -> CurvePage:
    page = CurvePage(
        host,
        controller=CurveController(setup=host.tube_page.controller.setup),
        viewer_factory=getattr(host, "_model_viewer_factory", None),
    )
    page.back_requested.connect(host._show_home)
    page.open_step_requested.connect(host.open_model_dialog)
    return page


def controller_for_model(
    previous: CurveController,
    setup: ManufacturingSetup,
    model: CadModel,
) -> CurveController:
    previous_hash = None if previous.cad_model is None else previous.cad_model.source_hash
    if previous_hash not in {None, model.source_hash}:
        return CurveController(model, setup=setup)
    payload = previous.to_json()
    payload["setups"] = [setup.to_json()]
    return CurveController.from_json(payload, cad_model=model)


def sync_source_update(
    controller: CurveController,
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
) -> tuple[
    tuple[TubeOperationDefinition, ...],
    tuple[PlanarOperationDefinition, ...],
    tuple[CurveOperationDefinition, ...],
]:
    values = tuple(operations)
    return (
        tuple(item for item in values if isinstance(item, TubeOperationDefinition)),
        tuple(item for item in values if isinstance(item, PlanarOperationDefinition)),
        tuple(item for item in values if isinstance(item, CurveOperationDefinition)),
    )


def sync_shared_setup(curve: CurveController, tube_setup: ManufacturingSetup) -> bool:
    if curve.setup == tube_setup:
        return False
    curve.mark_setup_changed(tube_setup, reason="shared_setup_changed")
    return True


def current_operation(controller: CurveController) -> str:
    return controller.operations[-1].operation_type if controller.operations else "curve_buildup"


def operation_label(controller: CurveController) -> str:
    return controller.operations[-1].name if controller.operations else "Curve Buildup"


def populate_operation_combo(combo: Any, controller: CurveController) -> None:
    if not controller.operations:
        combo.addItem("Curve Buildup", "curve_buildup")
        return
    for operation in controller.operations:
        combo.addItem(operation.name, operation.operation_type)


__all__ = [
    "controller_for_model",
    "current_operation",
    "install_curve_page",
    "operation_label",
    "populate_operation_combo",
    "split_operations",
    "sync_shared_setup",
    "sync_source_update",
]
