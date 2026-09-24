"""Lifecycle integration for the restricted Freeform workbench."""

from __future__ import annotations

from .freeform_controller import FreeformController
from .freeform_ui import FreeformPage
from .manufacturing.controller_profile import ControllerProfile, OWN_AC_OFFLINE_CONTROLLER
from .manufacturing.freeform_parameters import FreeformOperationDefinition


def install_freeform_page(host):
    page = FreeformPage(
        host,
        controller=FreeformController(setup=host.tube_page.controller.setup),
        viewer_factory=getattr(host, "_model_viewer_factory", None),
    )
    page.back_requested.connect(host._show_home)
    page.open_step_requested.connect(host.open_model_dialog)
    return page


def controller_for_model(previous, setup, model):
    previous_hash = None if previous.cad_model is None else previous.cad_model.source_hash
    if previous_hash not in {None, model.source_hash}:
        return FreeformController(model, setup=setup)
    payload = previous.to_json()
    payload["setups"] = [setup.to_json()]
    return FreeformController.from_json(payload, cad_model=model)


def controller_for_project(setup, model, operations, *, controller_profile_payload=None):
    profile = (
        OWN_AC_OFFLINE_CONTROLLER
        if controller_profile_payload is None
        else ControllerProfile.from_json(controller_profile_payload)
    )
    return FreeformController(
        model, setup=setup, operations=operations, controller_profile=profile
    )


def freeform_operations(operations):
    return tuple(item for item in operations if isinstance(item, FreeformOperationDefinition))


def sync_source_update(controller, setup, model):
    if controller.cad_model is None:
        controller.attach_cad_model(model)
    else:
        controller.update_cad_model(model)
    controller.mark_setup_changed(setup, reason="source_geometry_updated")


def sync_shared_setup(controller, setup):
    if controller.setup == setup:
        return False
    controller.mark_setup_changed(setup, reason="shared_setup_changed")
    return True


def current_operation(controller):
    return controller.operations[-1].operation_type if controller.operations else "freeform_surface"


def operation_label(controller):
    return controller.operations[-1].name if controller.operations else "Freeform Surface"


def populate_operation_combo(combo, controller):
    if not controller.operations:
        combo.addItem("Freeform Surface", "freeform_surface")
    else:
        for operation in controller.operations:
            combo.addItem(operation.name, operation.operation_type)


__all__ = [
    "controller_for_model",
    "controller_for_project",
    "current_operation",
    "freeform_operations",
    "install_freeform_page",
    "operation_label",
    "populate_operation_combo",
    "sync_shared_setup",
    "sync_source_update",
]
