"""Small Qt-free integration contracts for the Tube T12 workflow."""

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.automation_routes import AutomationRouter
from five_axis_slicer.command_kernel import CommandInvocation
from five_axis_slicer.curve_commands import CurveCommandService
from five_axis_slicer.curve_controller import CurveController
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE
from five_axis_slicer.planar_commands import PlanarCommandService
from five_axis_slicer.planar_controller import PlanarController
from five_axis_slicer.postprocessing.indexed_tube import GenerationCancelled
from five_axis_slicer.postprocessing.tube_product import TubeProductState
from five_axis_slicer.rotary_commands import RotaryCommandService
from five_axis_slicer.rotary_controller import RotaryController
from five_axis_slicer.tube_commands import TubeCommandProvider
from five_axis_slicer.tube_controller import TubeSetupController
from five_axis_slicer.tube_script_service import (
    TubeScriptService,
    _sync_shared_workbench_setups,
)


def _controller() -> TubeSetupController:
    controller = TubeSetupController()
    controller.create_operation(operation_id="op-1")
    return controller


def test_fork_shares_cancel_event_but_keeps_product_state_and_result_isolated():
    controller = _controller()
    digest = "a" * 64
    controller._product_states["op-1"] = TubeProductState("op-1", digest, "ready", {"old": 1})
    fork = controller.fork()
    assert fork._generation_cancelled is controller._generation_cancelled
    controller.cancel_generation()
    with pytest.raises(GenerationCancelled):
        if fork._generation_cancel_requested():
            raise GenerationCancelled("cancelled")
    fork._product_states["op-1"] = TubeProductState("op-1", digest, "error", {"error": "new"})
    fork._product_results["op-1"] = object()
    assert controller.product_state("op-1").status == "ready"
    assert controller.product_result("op-1") is None


@pytest.mark.parametrize("status", ["stale", "error"])
def test_stale_or_error_product_cannot_export(status):
    controller = _controller()
    controller._product_states["op-1"] = TubeProductState("op-1", "a" * 64, status)
    with pytest.raises(ValueError, match="exportable"):
        controller.export_operation_product("op-1", Path("tmp") / "out.json")


def test_command_provider_generation_failure_is_error_payload_and_project_only(monkeypatch):
    controller = _controller()

    def fail(_operation_id=None):
        raise RuntimeError("generation boom")

    monkeypatch.setattr(controller, "generate_operation", fail)
    outcome = TubeCommandProvider().invoke(controller, CommandInvocation("generate_operation"))
    assert outcome.payload["status"] == "error"
    assert "generation boom" in outcome.payload["message"]
    assert outcome.project_only is True
    assert outcome.record_history is False
    assert outcome.changed_fields == ("products",)


class _Page:
    def state_json(self):
        return {"page": "tube"}


class _Window:
    def __init__(self):
        self.tube_page = _Page()
        self.tube_page.controller = type("C", (), {"state_json": lambda s: {"products": ["p"]}})()
        self.calls = []
        self.tube_script_service = type(
            "S",
            (),
            {
                "execute_command": lambda s, command_name, *args, **kwargs: self.calls.append(
                    (command_name, args, kwargs)
                )
                or type(
                    "R",
                    (),
                    {
                        "command": command_name,
                        "revision": 1,
                        "changed": False,
                        "payload": {"ok": 1},
                        "affected_nodes": (),
                        "changed_fields": (),
                        "project_only": False,
                        "coordinates_valid": True,
                        "setup_ready": True,
                        "issue_codes": (),
                        "origin": "http",
                        "command_id": None,
                        "config_synced": True,
                    },
                )(),
                "state_json": lambda s: {},
            },
        )()


def test_automation_tube_routes_forward_minimal_payloads():
    window = _Window()
    router = AutomationRouter(window)
    create = router.dispatch(
        "/tube/operation/create",
        {"operation_type": "tube_continuous", "operation_id": "op-2", "name": "Helix"},
    )
    generate = router.dispatch("/tube/operation/generate", {"operation_id": "op-1"})
    export = router.dispatch(
        "/tube/operation/export", {"operation_id": "op-1", "destination": "tmp/x"}
    )
    state = router.dispatch("/tube/generation/state", {})
    assert [call[0] for call in window.calls] == [
        "create_operation",
        "generate_operation",
        "export_operation",
    ]
    assert window.calls[0][2]["name"] == "Helix"
    assert window.calls[1][2]["operation_id"] == "op-1"
    assert window.calls[2][2]["operation_id"] == "op-1"
    assert create["command"]["payload"] == {"ok": 1}
    assert generate["command"]["payload"] == {"ok": 1}
    assert export["command"]["payload"] == {"ok": 1}
    assert state == {"products": ["p"]}


def test_global_axis_map_route_forwards_to_shared_machine_command():
    window = _Window()
    router = AutomationRouter(window)

    response = router.dispatch(
        "/setup/machine/axis-map",
        {"mapping": {"A": "U", "C": "W"}, "name": "DIY U/W", "command_id": "map-1"},
    )

    command, args, kwargs = window.calls[-1]
    assert command == "set_machine_axis_words"
    assert args == ()
    assert kwargs["mapping"] == {"A": "U", "C": "W"}
    assert kwargs["name"] == "DIY U/W"
    assert kwargs["command_id"] == "map-1"
    assert response["command"]["payload"] == {"ok": 1}


def test_shared_machine_publish_updates_every_loaded_workbench_and_kernel_epoch():
    tube = TubeSetupController()
    tube.select_machine(GENERIC_XYZAC_REFERENCE)
    planar = PlanarController(setup=tube.setup)
    curve = CurveController(setup=tube.setup)
    rotary = RotaryController(setup=tube.setup)
    mapped = GENERIC_XYZAC_REFERENCE.with_rotary_axis_words({"A": "U", "C": "W"})
    tube.select_machine(mapped)

    def page(controller):
        return SimpleNamespace(controller=controller, refresh=lambda: None)

    window = SimpleNamespace(
        planar_page=page(planar),
        curve_page=page(curve),
        rotary_page=page(rotary),
        planar_command_service=PlanarCommandService(planar),
        curve_command_service=CurveCommandService(curve),
        rotary_command_service=RotaryCommandService(rotary),
    )
    service = object.__new__(TubeScriptService)
    service.page = page(tube)
    service.window = window

    _sync_shared_workbench_setups(service)

    for controller in (planar, curve, rotary):
        assert dict(controller.machine_profile().rotary_axis_words) == {"A": "U", "C": "W"}
    assert window.planar_command_service.kernel.revision == 1
    assert window.curve_command_service.kernel.revision == 1
    assert window.rotary_command_service.kernel.revision == 1


def test_shared_machine_publish_finishes_all_syncs_when_an_early_refresh_fails():
    tube = TubeSetupController()
    tube.select_machine(GENERIC_XYZAC_REFERENCE)
    planar = PlanarController(setup=tube.setup)
    curve = CurveController(setup=tube.setup)
    rotary = RotaryController(setup=tube.setup)
    tube.select_machine(GENERIC_XYZAC_REFERENCE.with_rotary_axis_words({"A": "U", "C": "W"}))

    refreshes: list[str] = []

    def page(controller, name: str, *, fail: bool = False):
        def refresh() -> None:
            refreshes.append(name)
            if fail:
                raise RuntimeError("simulated refresh failure")

        return SimpleNamespace(controller=controller, refresh=refresh)

    window = SimpleNamespace(
        planar_page=page(planar, "planar", fail=True),
        curve_page=page(curve, "curve"),
        rotary_page=page(rotary, "rotary"),
        planar_command_service=PlanarCommandService(planar),
        curve_command_service=CurveCommandService(curve),
        rotary_command_service=RotaryCommandService(rotary),
    )
    service = object.__new__(TubeScriptService)
    service.page = page(tube, "tube")
    service.window = window

    _sync_shared_workbench_setups(service)

    assert refreshes == ["planar", "curve", "rotary"]
    for controller in (planar, curve, rotary):
        assert dict(controller.machine_profile().rotary_axis_words) == {"A": "U", "C": "W"}
    assert window.planar_command_service.kernel.revision == 1
    assert window.curve_command_service.kernel.revision == 1
    assert window.rotary_command_service.kernel.revision == 1
