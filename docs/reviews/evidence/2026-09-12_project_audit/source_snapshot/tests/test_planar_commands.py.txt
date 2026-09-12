from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.planar_commands import PlanarCommandService
from five_axis_slicer.planar_controller import PlanarController
from test_planar_zigzag_product import _model


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
