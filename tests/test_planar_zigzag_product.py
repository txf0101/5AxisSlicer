from dataclasses import replace
from pathlib import Path
import sys

import cadquery as cq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE  # noqa: E402
from five_axis_slicer.manufacturing.planar_parameters import (  # noqa: E402
    PlanarGeometrySelection,
    PlanarOperationDefinition,
    PlanarProcessParameters,
)
from five_axis_slicer.manufacturing.resources import GENERIC_PLA_175, NozzleProfile, ResourceSnapshot  # noqa: E402
from five_axis_slicer.manufacturing.setup import ManufacturingObjectAssignments, ManufacturingSetup  # noqa: E402
from five_axis_slicer.models import BodyInfo, BoundingBox, CadModel  # noqa: E402
from five_axis_slicer.planar_controller import PlanarController  # noqa: E402
from five_axis_slicer.postprocessing.planar_product import (  # noqa: E402
    export_planar_product,
    generate_planar_zigzag_product,
)
from five_axis_slicer.postprocessing.indexed_tube import GenerationCancelled  # noqa: E402


def _frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", (0, 0, 0), confirmed=True),
        DirectionReference("numeric", (0, 0, 1), confirmed=True),
        DirectionReference("numeric", (1, 0, 0), confirmed=True),
    )


def _model() -> CadModel:
    shape = cq.Workplane("XY").box(8, 6, 1).translate((4, 3, 0.5))
    bounds = BoundingBox((0, 0, 0), (8, 6, 1))
    return CadModel(
        Path("planar-zigzag.step"),
        "b" * 64,
        [BodyInfo("body", 1, "body", (0.8, 0.8, 0.8), bounds=bounds)],
        [],
        {"body": shape.val().wrapped},
        {},
        bounds=bounds,
    )


def _operation() -> PlanarOperationDefinition:
    return PlanarOperationDefinition(
        "planar-zigzag-1",
        "setup-1",
        operation_type="planar_zigzag",
        geometry=PlanarGeometrySelection(GeometryReference("body", "body", {"schema_version": 1})),
        parameters=PlanarProcessParameters(
            first_layer_z_mm=0.5,
            layer_height_mm=0.5,
            last_layer_z_mm=0.5,
            bead_width_mm=0.6,
            feedrate_mm_min=100.0,
            line_spacing_mm=0.6,
            travel_feedrate_mm_min=100.0,
        ),
    )


def _machine():
    return replace(
        GENERIC_XYZAC_REFERENCE,
        joints=tuple(
            replace(joint, soft_limit_min=-1000.0, soft_limit_max=1000.0)
            for joint in GENERIC_XYZAC_REFERENCE.joints
        ),
    )


def _nozzle() -> NozzleProfile:
    return NozzleProfile(
        "planar-test-nozzle",
        "Planar test nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2.0,
        outer_profile_rz_mm=((0.3, 0.0), (0.4, 2.0)),
    )


def _setup() -> ManufacturingSetup:
    machine = _machine()
    return ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(part_body_ids=("body",)),
        machine=ResourceSnapshot.capture("machine", machine),
        nozzle=ResourceSnapshot.capture("nozzle", _nozzle()),
        material=ResourceSnapshot.capture("material", GENERIC_PLA_175.reviewed_copy("planar-test-pla")),
        model_coordinate_system=_frame("model"),
        build_coordinate_system=_frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250, 250, 250), source_frame="build", target_frame="build_plate_mount"
        ),
    )


def test_zigzag_product_generates_reads_back_and_exports_six_files(tmp_path: Path) -> None:
    result = generate_planar_zigzag_product(
        _model(),
        _operation(),
        _machine(),
        _nozzle(),
        RigidTransform(
            RigidTransform.identity().matrix,
            source_frame="build",
            target_frame="model",
        ),
        T_workpiece_from_build=RigidTransform.from_translation(
            (250, 250, 250), source_frame="build", target_frame="workpiece"
        ),
    )

    assert result.exportable
    assert result.readback.passed
    assert result.validation.measurement.deposition_outside_max_mm == 0.0
    assert abs(result.validation.measurement.volume_difference_mm3) < 1e-9
    assert "; P02 POINT" in result.gcode
    destination = export_planar_product(result, tmp_path / "p02-output")
    assert {item.name for item in destination.iterdir()} == {
        "machine_axes.csv",
        "main.gcode",
        "manifest.json",
        "preview.json",
        "toolpath.json",
        "warnings.json",
    }


def test_controller_zigzag_generation_and_export(tmp_path: Path) -> None:
    controller = PlanarController(_model(), setup=_setup(), operations=(_operation(),))

    result = controller.generate_operation("planar-zigzag-1")
    destination = controller.export_operation_product(
        "planar-zigzag-1", str(tmp_path / "controller-output")
    )

    assert result.exportable
    assert controller.product_state("planar-zigzag-1").status in {"ready", "warning"}
    assert (destination / "main.gcode").is_file()


def test_zigzag_cancel_preserves_ready_then_parameter_change_is_stale() -> None:
    controller = PlanarController(_model(), setup=_setup(), operations=(_operation(),))
    ready = controller.generate_operation("planar-zigzag-1")
    ready_state = controller.product_state("planar-zigzag-1")

    with pytest.raises(GenerationCancelled):
        controller.generate_operation("planar-zigzag-1", cancelled=lambda: True)

    assert controller.product_result("planar-zigzag-1") is ready
    assert controller.product_state("planar-zigzag-1") is ready_state
    changed = replace(_operation().parameters, line_spacing_mm=0.5)
    controller.configure_operation(
        operation_id="planar-zigzag-1", body_id="body", parameters=changed
    )
    assert controller.product_state("planar-zigzag-1").status == "stale"
    restored = PlanarController.from_json(controller.to_json(), cad_model=_model())
    assert restored.operation("planar-zigzag-1").parameters.line_spacing_mm == 0.5
    assert restored.product_state("planar-zigzag-1").status == "stale"
