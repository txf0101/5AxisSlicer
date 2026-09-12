from dataclasses import replace
from pathlib import Path
import sys

import cadquery as cq

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.planar_parameters import (
    PlanarGeometrySelection,
    PlanarOperationDefinition,
    PlanarProcessParameters,
)
from five_axis_slicer.models import BoundingBox, CadModel
from five_axis_slicer.manufacturing.setup import ManufacturingSetup
from five_axis_slicer.planar_controller import PlanarController
from five_axis_slicer.postprocessing.indexed_tube import GenerationCancelled
from five_axis_slicer.postprocessing.planar_product import (
    generate_planar_region_product,
    state_from_region_result,
)


def _model() -> CadModel:
    shape = cq.Workplane("XY").box(10, 8, 2).translate((5, 0, 3))
    return CadModel(
        Path("planar.step"),
        "a" * 64,
        [],
        [],
        {"body": shape.val().wrapped},
        {},
        bounds=BoundingBox((0, -4, 2), (10, 4, 4)),
    )


def _operation() -> PlanarOperationDefinition:
    return PlanarOperationDefinition(
        "planar-region-1",
        "setup-1",
        geometry=PlanarGeometrySelection(GeometryReference("body", "body", {"schema_version": 1})),
        parameters=PlanarProcessParameters(0.0, 1.0, 0.0, 0.6, 900.0),
    )


def _frame(frame_id: str, origin: tuple[float, float, float]) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", origin, confirmed=True),
        DirectionReference("numeric", (0.0, 0.0, 1.0), confirmed=True),
        DirectionReference("numeric", (1.0, 0.0, 0.0), confirmed=True),
    )


def test_region_product_uses_build_frame_and_is_preview_only() -> None:
    transform = RigidTransform.from_translation(
        (5, 0, 3), source_frame="build", target_frame="model"
    )

    result = generate_planar_region_product(_model(), _operation(), transform)

    assert len(result.layers) == 1
    assert len(result.layers[0].regions) == 1
    assert {round(point.position[2], 9) for point in result.preview_toolpath.points} == {0.0}
    assert result.manifest.status.value == "ready"
    assert not result.manifest.ready_for_export
    assert not result.exportable
    assert "planar.region_preview_only" in result.manifest.issues


def test_region_product_state_becomes_stale_after_parameter_change() -> None:
    operation = _operation()
    result = generate_planar_region_product(
        _model(),
        operation,
        RigidTransform.from_translation((5, 0, 3), source_frame="build", target_frame="model"),
    )
    state = state_from_region_result(operation, result)
    changed = replace(
        operation,
        parameters=replace(operation.parameters, feedrate_mm_min=1200.0),
    )

    assert state.status == "ready"
    assert state.stale_for(changed).status == "stale"
    assert state.stale_for(operation) is state


def test_controller_generation_and_cancel_keep_previous_ready_result() -> None:
    setup = ManufacturingSetup(
        model_coordinate_system=_frame("model", (0.0, 0.0, 0.0)),
        build_coordinate_system=_frame("build", (5.0, 0.0, 3.0)),
    )
    controller = PlanarController(_model(), setup=setup, operations=(_operation(),))

    first = controller.generate_operation("planar-region-1")
    ready_state = controller.product_state("planar-region-1")
    with pytest.raises(GenerationCancelled):
        controller.generate_operation("planar-region-1", cancelled=lambda: True)

    assert controller.product_result("planar-region-1") is first
    assert controller.product_state("planar-region-1") is ready_state
