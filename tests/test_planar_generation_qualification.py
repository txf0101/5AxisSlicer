"""Planar persistence, applied-input qualification and Source/Build coordinate truth."""

from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.resources import GENERIC_PLA_175, ResourceSnapshot
from five_axis_slicer.planar_controller import PlanarController
from five_axis_slicer.planar_generation_context import PLANAR_CONTEXT_VERSION
from five_axis_slicer.postprocessing.indexed_tube import GenerationCancelled
from five_axis_slicer.postprocessing.planar_product import PlanarProductState

from test_planar_controller import _frame
from test_planar_zigzag_product import _model, _nozzle, _operation, _setup


@pytest.fixture
def ready():
    controller = PlanarController(_model(), setup=_setup(), operations=(_operation(),))
    controller.generate_operation()
    assert controller.product_state(_operation().operation_id).status in {"ready", "warning"}
    return controller


@pytest.mark.parametrize("status", ["ready", "warning"])
def test_legacy_v1_state_keeps_preview_payload_but_requires_regeneration(ready, status):
    payload = ready.to_json()
    previous = payload["product_states"][0]
    previous["status"] = status
    previous["result"]["manifest"]["algorithm_version"] = "planar-zigzag-product-v1"
    previous["result"].pop("generation_input_sha256")
    previous["result"].pop("generation_context_version")
    original_result = deepcopy(previous["result"])

    restored = PlanarController.from_json(payload, cad_model=_model())

    state = restored.product_state(_operation().operation_id)
    assert state.status == "stale"
    assert state.result_payload == original_result
    assert restored.operations == ready.operations
    assert PlanarProductState.from_json(previous).status == "stale"
    with pytest.raises(ValueError, match="no exportable"):
        restored.export_operation_product(destination="must-not-exist")


def test_current_v2_state_reopens_stale_without_runtime_product(ready):
    state = ready.product_state(_operation().operation_id)
    assert state.result_payload["generation_context_version"] == PLANAR_CONTEXT_VERSION
    restored = PlanarController.from_json(ready.to_json(), cad_model=_model())
    reopened = restored.product_state(_operation().operation_id)
    assert reopened.status == "stale"
    assert reopened.result_payload == state.result_payload
    assert restored.product_result(_operation().operation_id) is None


@pytest.mark.parametrize("change", ["placement", "nozzle", "material", "build", "parameters"])
def test_restored_state_cannot_reuse_qualification_for_changed_inputs(ready, change):
    payload = ready.to_json()
    setup = ready.setup
    if change == "placement":
        matrix = [list(row) for row in setup.T_mount_from_build.matrix]
        matrix[0][3] += 100.0
        setup = replace(
            setup,
            T_mount_from_build=replace(setup.T_mount_from_build, T_target_from_source=tuple(map(tuple, matrix))),
        )
    elif change == "nozzle":
        setup = replace(
            setup,
            nozzle=ResourceSnapshot.capture(
                "nozzle", replace(_nozzle(), filament_diameter_mm=2.85)
            ),
        )
    elif change == "material":
        setup = replace(
            setup,
            material=ResourceSnapshot.capture(
                "material", GENERIC_PLA_175.reviewed_copy("other-pla")
            ),
        )
    elif change == "build":
        setup = replace(setup, build_coordinate_system=_frame("build", (10.0, 0.0, 0.0)))
    else:
        payload["operations"][0]["parameters"]["feedrate_mm_min"] = 101.0
    payload["setups"] = [setup.to_json()]
    restored = PlanarController.from_json(payload, cad_model=_model())
    assert restored.product_state(_operation().operation_id).status == "stale"


@pytest.mark.parametrize("missing", ["material", "nozzle", "machine"])
def test_incomplete_setup_is_rejected_before_path_generation(missing):
    controller = PlanarController(
        _model(), setup=replace(_setup(), **{missing: None}), operations=(_operation(),)
    )
    with patch("five_axis_slicer.planar_controller.generate_planar_path_product") as generate:
        with pytest.raises(ValueError, match="valid applied Setup"):
            controller.generate_operation()
    generate.assert_not_called()
    assert controller.product_state(_operation().operation_id).status == "error"


def test_unreviewed_material_cannot_generate_path():
    setup = replace(_setup(), material=ResourceSnapshot.capture("material", GENERIC_PLA_175))
    controller = PlanarController(_model(), setup=setup, operations=(_operation(),))
    with pytest.raises(ValueError, match="reviewed resources"):
        controller.generate_operation()


def test_setup_change_keeps_previous_result_but_blocks_export(ready, tmp_path):
    previous = ready.product_result(_operation().operation_id)
    ready.mark_setup_changed(
        replace(
            ready.setup,
            nozzle=ResourceSnapshot.capture("nozzle", replace(_nozzle(), length_mm=3.0)),
        )
    )
    assert ready.product_result(_operation().operation_id) is previous
    assert ready.product_state(_operation().operation_id).status == "stale"
    with pytest.raises(ValueError, match="not Ready"):
        ready.export_operation_product(destination=str(tmp_path / "blocked"))
    assert not (tmp_path / "blocked").exists()


def test_parameter_change_during_generation_cannot_publish_obsolete_result(ready):
    previous = ready.product_result(_operation().operation_id)
    changed = False

    def change_once():
        nonlocal changed
        if not changed:
            changed = True
            ready.configure_operation(
                body_id="body", parameters=replace(_operation().parameters, feedrate_mm_min=101.0)
            )

    ready.set_generation_event_pump(change_once)
    with pytest.raises(GenerationCancelled, match="inputs changed"):
        ready.generate_operation()
    assert ready.product_result(_operation().operation_id) is previous
    assert ready.product_state(_operation().operation_id).status == "stale"


def test_changed_source_bytes_with_live_cad_and_old_result_block_export(tmp_path):
    source = tmp_path / "source.step"
    source.write_bytes(b"original authority identity")
    model = replace(
        _model(), source_path=source, source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    )
    controller = PlanarController(model, setup=_setup(), operations=(_operation(),))
    controller.generate_operation()
    source.write_bytes(b"new authority identity")
    with pytest.raises(ValueError, match="not Ready"):
        controller.export_operation_product(destination=str(tmp_path / "blocked"))
    assert controller.product_state(_operation().operation_id).status == "stale"
    with pytest.raises(ValueError, match="source changed on disk"):
        controller.generate_operation()


def test_model_display_frame_does_not_change_source_geometry_or_nc(ready):
    previous = ready.product_result(_operation().operation_id)
    setup = replace(ready.setup, model_coordinate_system=_frame("model", (25.0, 8.0, 10.0)))
    ready.mark_setup_changed(setup)
    current = ready.generate_operation()
    assert current.toolpath == previous.toolpath
    assert current.gcode == previous.gcode


def test_build_frame_shift_changes_source_section_coordinates_and_machine_axes(ready):
    previous = ready.product_result(_operation().operation_id)
    ready.mark_setup_changed(
        replace(ready.setup, build_coordinate_system=_frame("build", (10.0, 0.0, 0.0)))
    )
    current = ready.generate_operation()
    assert min(point.position[0] for point in current.toolpath.points) == pytest.approx(
        min(point.position[0] for point in previous.toolpath.points) - 10.0
    )
    assert min(
        sample.joint_positions["X"] for sample in current.trajectory.samples
    ) == pytest.approx(
        min(sample.joint_positions["X"] for sample in previous.trajectory.samples) - 10.0
    )
