from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.planar_commands import PlanarCommandService
from five_axis_slicer.planar_controller import PlanarController
from test_planar_zigzag_product import _model, _operation, _setup


def test_planar_commands_publish_and_undo_through_shared_kernel() -> None:
    controller = PlanarController()
    service = PlanarCommandService(controller)

    created = service.execute_command(
        "create_operation", "planar_region", operation_id="region-1", origin="gui"
    )
    renamed = service.execute_command(
        "set_operation", operation_id="region-1", name="Base sections", origin="http"
    )

    assert created.changed
    assert renamed.changed
    assert controller.operations[0].name == "Base sections"
    service.execute_command("undo", origin="gui")
    assert controller.operations[0].name == "Planar Region"


def test_restricted_planar_script_uses_the_same_command_provider() -> None:
    controller = PlanarController(_model())
    service = PlanarCommandService(controller)

    output = service.execute_script(
        'planar.create_operation("planar_region", operation_id="script-region")'
    )

    assert "script-region" in output
    assert controller.operations[0].operation_id == "script-region"

    configured = service.execute_script(
        'planar.set_operation(operation_id="script-region", body_id="body", '
        "offset_pass_count=5, wall_thickness_mm=1.2, thin_wall_max_passes=2, "
        "spiral_samples_per_contour=80)"
    )
    assert not configured.startswith("ERROR:")
    parameters = controller.operations[0].parameters
    assert parameters.offset_pass_count == 5
    assert parameters.wall_thickness_mm == 1.2
    assert parameters.thin_wall_max_passes == 2
    assert parameters.spiral_samples_per_contour == 80


def test_undo_restores_the_runtime_result_after_parameter_change(tmp_path: Path) -> None:
    operation = _operation()
    controller = PlanarController(_model(), setup=_setup(), operations=(operation,))
    service = PlanarCommandService(controller)
    service.execute_command("generate_operation", operation.operation_id)
    previous = controller.product_result(operation.operation_id)

    service.execute_command(
        "set_operation",
        operation_id=operation.operation_id,
        body_id="body",
        feedrate_mm_min=101.0,
    )
    assert controller.product_state(operation.operation_id).status == "stale"

    service.execute_command("undo")

    assert controller.product_result(operation.operation_id) is previous
    assert controller.product_state(operation.operation_id).status in {"ready", "warning"}
    exported = controller.export_operation_product(
        operation.operation_id, str(tmp_path / "restored")
    )
    assert (exported / "main.gcode").is_file()


def test_cancel_command_reaches_the_active_generation_candidate() -> None:
    operation = _operation()
    controller = PlanarController(_model(), setup=_setup(), operations=(operation,))
    service = PlanarCommandService(controller)
    service.execute_command("generate_operation", operation.operation_id)
    previous = controller.product_result(operation.operation_id)
    requested = False

    def cancel_from_event_pump() -> None:
        nonlocal requested
        if not requested:
            requested = True
            service.execute_command("cancel_generation")

    controller.set_generation_event_pump(cancel_from_event_pump)
    result = service.execute_command("generate_operation", operation.operation_id)

    assert requested
    assert result.payload["status"] == "cancelled"
    assert controller.product_result(operation.operation_id) is previous
