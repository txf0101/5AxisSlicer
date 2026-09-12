from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.coordinates import GeometryReference, RigidTransform
from five_axis_slicer.manufacturing.planar_parameters import PlanarGeometrySelection
from five_axis_slicer.planar_controller import PlanarController
from five_axis_slicer.postprocessing.planar_product import (
    export_planar_product,
    generate_planar_path_product,
)
from test_planar_zigzag_product import _machine, _model, _nozzle, _operation, _setup


def _thin_operation():
    return replace(
        _operation(),
        operation_id="planar-thin-wall-1",
        operation_type="planar_thin_wall",
        geometry=PlanarGeometrySelection(GeometryReference("body", "body", {"schema_version": 1})),
        parameters=replace(_operation().parameters, wall_thickness_mm=1.2, thin_wall_max_passes=2),
    )


def test_thin_wall_product_is_exportable_and_contains_p04_bundle(tmp_path: Path):
    result = generate_planar_path_product(
        _model(), _thin_operation(), _machine(), _nozzle(), RigidTransform.identity("build")
    )
    assert result.exportable and result.readback.passed
    assert result.manifest.algorithm_version.startswith("planar-thin-wall")
    assert "; P04" in result.gcode
    destination = export_planar_product(result, tmp_path / "p04-output")
    assert {item.name for item in destination.iterdir()} == {
        "machine_axes.csv",
        "main.gcode",
        "manifest.json",
        "preview.json",
        "toolpath.json",
        "warnings.json",
    }


def test_thin_wall_max_passes_changes_product_semantic_hash():
    first = generate_planar_path_product(
        _model(), _thin_operation(), _machine(), _nozzle(), RigidTransform.identity("build")
    )
    changed = replace(
        _thin_operation(), parameters=replace(_thin_operation().parameters, thin_wall_max_passes=3)
    )
    second = generate_planar_path_product(
        _model(), changed, _machine(), _nozzle(), RigidTransform.identity("build")
    )
    assert first.manifest.parameter_semantic_sha256 != second.manifest.parameter_semantic_sha256


def test_thin_wall_parameter_change_marks_ready_product_stale():
    operation = _thin_operation()
    controller = PlanarController(_model(), setup=_setup(), operations=(operation,))
    controller.generate_operation(operation.operation_id)

    controller.configure_operation(
        operation_id=operation.operation_id,
        body_id="body",
        parameters=replace(operation.parameters, wall_thickness_mm=1.8),
    )

    assert controller.product_state(operation.operation_id).status == "stale"


def test_thin_wall_narrow_reduce_policy_is_a_visible_warning():
    operation = replace(
        _thin_operation(),
        parameters=replace(_thin_operation().parameters, wall_thickness_mm=0.3),
    )

    result = generate_planar_path_product(
        _model(), operation, _machine(), _nozzle(), RigidTransform.identity("build")
    )

    assert result.manifest.status.value == "warning"
    assert "planar.thin_wall_width_reduced" in result.manifest.issues
    assert result.exportable and result.readback.passed
