from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.setup import ManufacturingSetup, NodeState
from five_axis_slicer.models import BodyInfo, BoundingBox, CadModel
from five_axis_slicer.planar_controller import PlanarController


def _model(identifier: str, *, size: float = 2.0) -> CadModel:
    body = BodyInfo(
        identifier,
        1,
        identifier,
        (0.8, 0.8, 0.8),
        bounds=BoundingBox((0.0, 0.0, 0.0), (size, size, size)),
        volume=size**3,
        surface_area=6.0 * size**2,
        centroid=(size / 2.0, size / 2.0, size / 2.0),
    )
    return CadModel(Path(f"{identifier}.step"), "a" * 64, [body], [], {identifier: object()}, {})


def _frame(frame_id: str, origin: tuple[float, float, float]) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", origin, confirmed=True),
        DirectionReference("numeric", (0.0, 0.0, 1.0), confirmed=True),
        DirectionReference("numeric", (1.0, 0.0, 0.0), confirmed=True),
    )


def test_controller_persists_operations_and_stable_body_reference() -> None:
    model = _model("body-a")
    controller = PlanarController(model)
    controller.create_operation(operation_id="planar-1")
    configured = controller.configure_operation(operation_id="planar-1", body_id="body-a")

    restored = PlanarController.from_json(controller.to_json(), cad_model=model)

    assert configured.geometry.body == controller.geometry_reference("body-a", "body")
    assert restored.operations == controller.operations
    assert restored.state_json()["capabilities"]["product_generation_available"] is True


def test_model_from_build_uses_confirmed_setup_coordinate_definitions() -> None:
    setup = ManufacturingSetup(
        model_coordinate_system=_frame("model", (10.0, 0.0, 0.0)),
        build_coordinate_system=_frame("build", (2.0, 0.0, 0.0)),
    )

    transform = PlanarController(setup=setup).T_model_from_build()

    assert transform.almost_equal(
        RigidTransform.from_translation(
            (-8.0, 0.0, 0.0), source_frame="build", target_frame="model"
        )
    )


def test_source_update_rebind_failure_keeps_reference_and_marks_invalid() -> None:
    source = _model("old-body")
    target = _model("new-body", size=3.0)
    controller = PlanarController(source)
    controller.create_operation(operation_id="planar-1")
    operation = controller.configure_operation(operation_id="planar-1", body_id="old-body")

    updated = controller.update_cad_model(target)[0]

    assert updated.state is NodeState.INVALID
    assert updated.geometry == operation.geometry
    assert "geometry_rebind_failed" in updated.dirty_reasons


def test_setup_change_marks_every_operation_dirty() -> None:
    controller = PlanarController()
    first = controller.create_operation(operation_id="one")
    second = controller.create_operation(operation_id="two")
    controller.mark_setup_changed(reason="build_changed")

    assert all(item.state is NodeState.DIRTY for item in controller.operations)
    assert all("build_changed" in item.dirty_reasons for item in controller.operations)
    assert (first.operation_id, second.operation_id) == ("one", "two")
