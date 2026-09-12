"""P01 Planar automation adapter contracts (Qt-free)."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.automation_routes import AutomationRouter
from five_axis_slicer.planar_commands import PlanarCommandService
from five_axis_slicer.planar_controller import PlanarController
from test_planar_zigzag_product import _model, _operation, _setup


class _Page:
    def __init__(self, controller):
        self.controller = controller

    def state_json(self):
        return self.controller.state_json()


class _Window:
    def __init__(self, controller=None):
        controller = controller or PlanarController(_model())
        self.planar_page = _Page(controller)
        self.planar_command_service = PlanarCommandService(controller)


def test_planar_routes_use_the_shared_command_entrypoint():
    window = _Window()
    router = AutomationRouter(window)

    state = router.dispatch("/planar/state", {})
    created = router.dispatch(
        "/planar/operation/create",
        {"operation_type": "planar_region", "operation_id": "op-1", "name": "Floor"},
    )
    updated = router.dispatch(
        "/planar/operation/set",
        {
            "operation_id": "op-1",
            "name": "Floor 2",
            "enabled": False,
            "body_id": "body",
            "offset_pass_count": 5,
            "wall_thickness_mm": 1.2,
            "thin_wall_max_passes": 2,
            "spiral_samples_per_contour": 80,
        },
    )

    assert state["planar"]["operations"] == []
    assert created["command"]["payload"]["operation_id"] == "op-1"
    assert updated["command"]["payload"]["name"] == "Floor 2"
    assert updated["command"]["payload"]["enabled"] is False
    assert window.planar_page.controller.operations[0].name == "Floor 2"
    parameters = window.planar_page.controller.operations[0].parameters
    assert parameters.offset_pass_count == 5
    assert parameters.wall_thickness_mm == 1.2
    assert parameters.thin_wall_max_passes == 2
    assert parameters.spiral_samples_per_contour == 80

    issues = router.dispatch("/planar/issues", {})["command"]["payload"]
    assert {item["code"] for item in issues} >= {"SETUP_PART_MISSING"}
    assert router.dispatch("/planar/validate", {})["command"]["payload"]["setup_ready"] is False
    assert router.dispatch("/planar/undo", {})["planar"]["operations"][0]["name"] == "Floor"
    assert router.dispatch("/planar/redo", {})["planar"]["operations"][0]["name"] == "Floor 2"


def test_http_cancel_reaches_generation_through_the_shared_command_service():
    operation = _operation()
    controller = PlanarController(_model(), setup=_setup(), operations=(operation,))
    window = _Window(controller)
    router = AutomationRouter(window)
    router.dispatch("/planar/operation/generate", {"operation_id": operation.operation_id})
    previous = controller.product_result(operation.operation_id)
    cancelled = False

    def cancel_from_event_pump():
        nonlocal cancelled
        if not cancelled:
            cancelled = True
            response = router.dispatch("/planar/generation/cancel", {})
            assert response["command"]["payload"]["cancel_requested"] is True

    controller.set_generation_event_pump(cancel_from_event_pump)
    response = router.dispatch(
        "/planar/operation/generate", {"operation_id": operation.operation_id}
    )

    assert cancelled
    assert response["command"]["payload"]["status"] == "cancelled"
    assert controller.product_result(operation.operation_id) is previous
