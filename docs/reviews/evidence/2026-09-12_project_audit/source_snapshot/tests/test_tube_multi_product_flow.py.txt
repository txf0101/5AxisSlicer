from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.tube.buildup import PlanarBaseDefinition
from five_axis_slicer.algorithms.tube.geometry import manual_tube_feature
from five_axis_slicer.manufacturing.coordinates import GeometryReference, RigidTransform
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE
from five_axis_slicer.manufacturing.resources import NozzleProfile
from five_axis_slicer.manufacturing.setup import (
    TubeBuildupOperationConfig,
    TubeContinuousOperationConfig,
    TubeGeometrySelection,
    TubeOperationDefinition,
    TubeProcessParameters,
)
from five_axis_slicer.models import CadModel
from five_axis_slicer.postprocessing.tube_product import (
    TubeProductService,
    export_tube_product,
    generate_tube_product,
)
from five_axis_slicer.validation.indexed_tube import CollisionBox


@pytest.fixture
def feature():
    return manual_tube_feature(
        ((0.0, 0.0, 50.0), (0.0, 0.0, 50.75)),
        outer_radius_mm=3.0,
        inner_radius_mm=1.0,
        tube_body_id="tube-body",
    )


@pytest.fixture
def model(tmp_path: Path) -> CadModel:
    return CadModel(tmp_path / "analytic.step", "0" * 64, [], [], {}, {})


@pytest.fixture
def machine():
    return replace(
        GENERIC_XYZAC_REFERENCE,
        joints=tuple(
            replace(joint, soft_limit_min=-1000.0, soft_limit_max=1000.0)
            if joint.joint_type == "linear"
            else joint
            for joint in GENERIC_XYZAC_REFERENCE.joints
        ),
    )


@pytest.fixture
def nozzle() -> NozzleProfile:
    return NozzleProfile(
        resource_id="multi-product-test",
        display_name="slender",
        orifice_diameter_mm=0.02,
        filament_diameter_mm=1.75,
        interface="test",
        length_mm=2.0,
        outer_profile_rz_mm=((0.01, 0.0), (0.01, 2.0)),
    )


@pytest.fixture
def placement() -> RigidTransform:
    return RigidTransform.from_translation(
        (250.0, 250.0, -300.0), source_frame="build", target_frame="workpiece"
    )


def _operation(operation_type: str, type_config=None) -> TubeOperationDefinition:
    geometry = TubeGeometrySelection(
        tube_body=GeometryReference("tube-body", "body"),
        entry_port=GeometryReference("entry", "edge", parent_body_id="tube-body"),
        exit_port=GeometryReference("exit", "edge", parent_body_id="tube-body"),
        substrate_body=GeometryReference("base-body", "body"),
    )
    return TubeOperationDefinition(
        "tube-op",
        "setup-1",
        operation_type=operation_type,
        geometry=geometry,
        parameters=TubeProcessParameters(
            bead_width_mm=1.0,
            layer_height_mm=1.0,
            safe_clearance_mm=2.0,
            contour_chord_error_mm=0.2,
            deposition_feedrate_mm_min=1.0,
            travel_feedrate_mm_min=1.0,
        ),
        type_config=type_config,
    )


def _generate_continuous(model, feature, machine, nozzle, placement):
    operation = _operation("tube_continuous", TubeContinuousOperationConfig(30.0))
    with patch("five_axis_slicer.postprocessing.tube_product.recognise_tube", return_value=feature):
        return (
            generate_tube_product(
                model, operation, machine, nozzle, T_workpiece_from_build=placement
            ),
            operation,
        )


def test_indexed_dispatch_reuses_t08_product(model, machine, nozzle) -> None:
    operation = _operation("tube_thin_wall_indexed")
    upstream = SimpleNamespace(
        feature=object(),
        plan=object(),
        toolpath=object(),
        trajectory=object(),
        validation=object(),
        manifest=object(),
        gcode="G21\n",
        readback=object(),
    )
    with patch(
        "five_axis_slicer.postprocessing.tube_product.generate_indexed_product",
        return_value=upstream,
    ) as generate:
        result = generate_tube_product(model, operation, machine, nozzle)

    assert result.operation_type == "tube_thin_wall_indexed"
    assert result.operation_toolpaths == (upstream.toolpath,)
    generate.assert_called_once()


@pytest.mark.parametrize(
    "base_order,expected",
    [
        ("before_tube", ("tube-op-planar-base", "tube-op")),
        ("after_tube", ("tube-op", "tube-op-planar-base")),
    ],
)
def test_buildup_keeps_base_independent_and_orders_safe_transition(
    model, feature, machine, nozzle, placement, base_order, expected
) -> None:
    operation = _operation("tube_buildup", TubeBuildupOperationConfig(1.0, True, base_order))
    base = PlanarBaseDefinition("base", (0.0, 0.0, 48.0), (0.0, 0.0, 1.0), 2.0, 1.0)
    with patch("five_axis_slicer.postprocessing.tube_product.recognise_tube", return_value=feature):
        result = generate_tube_product(
            model,
            operation,
            machine,
            nozzle,
            planar_base=base,
            T_workpiece_from_build=placement,
        )

    assert result.exportable
    assert result.readback.passed
    assert tuple(item.operation_id for item in result.operation_toolpaths) == expected
    assert result.buildup_sequence is not None
    assert [event.event_type for event in result.buildup_sequence.transition_events] == [
        "retract",
        "safe_depart",
        "operation_change",
        "safe_approach",
        "prime",
    ]


def test_continuous_reads_back_exports_six_artifacts_and_reopens_state(
    tmp_path, model, feature, machine, nozzle, placement
) -> None:
    result, operation = _generate_continuous(model, feature, machine, nozzle, placement)

    assert result.operation_type == "tube_continuous"
    assert result.exportable and result.readback.passed
    assert result.manifest.algorithm_version == "tube-continuous-product-v1"
    destination = export_tube_product(result, tmp_path / "continuous-result")
    assert {item.name for item in destination.iterdir()} == {
        "machine_axes.csv",
        "main.gcode",
        "manifest.json",
        "preview.json",
        "toolpath.json",
        "warnings.json",
    }
    service = TubeProductService()
    with patch("five_axis_slicer.postprocessing.tube_product.recognise_tube", return_value=feature):
        service.generate(model, operation, machine, nozzle, T_workpiece_from_build=placement)
    assert service.state is not None
    assert service.state.status == "ready"


def test_continuous_collision_error_blocks_nc_and_export(
    tmp_path, model, feature, machine, nozzle, placement
) -> None:
    clear, operation = _generate_continuous(model, feature, machine, nozzle, placement)
    left, right = clear.toolpath.points[:2]
    midpoint = tuple((a + b) * 0.5 for a, b in zip(left.position, right.position, strict=True))
    obstacle = CollisionBox(
        "fixture",
        "fixture",
        tuple(value - 0.03 for value in midpoint),
        tuple(value + 0.03 for value in midpoint),
    )
    with patch("five_axis_slicer.postprocessing.tube_product.recognise_tube", return_value=feature):
        blocked = generate_tube_product(
            model,
            operation,
            machine,
            nozzle,
            obstacles=(obstacle,),
            T_workpiece_from_build=placement,
        )

    assert blocked.manifest.status.value == "error"
    assert blocked.gcode == ""
    assert not blocked.readback.passed
    with pytest.raises(ValueError, match="blocks export"):
        export_tube_product(blocked, tmp_path / "blocked")
