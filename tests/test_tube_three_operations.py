from __future__ import annotations

import json
import sys
from pathlib import Path
from dataclasses import replace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.command_kernel import CommandInvocation
from five_axis_slicer.manufacturing.setup import TubeOperationDefinition
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE
from five_axis_slicer.manufacturing.resources import NozzleProfile
from five_axis_slicer.manufacturing.setup import TubeProcessParameters
from five_axis_slicer.models import BodyInfo, CadModel
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.tube_commands import TubeCommandProvider
from five_axis_slicer.tube_controller import TubeSetupController


def _controller() -> TubeSetupController:
    model = CadModel(
        source_path=Path("pipe.step"),
        source_hash="a" * 64,
        bodies=[BodyInfo("tube", 1, "Tube", (1.0, 1.0, 1.0), kind="solid")],
        edges=[],
        shapes={},
        edge_shapes={},
    )
    return TubeSetupController(model)


def test_three_types_round_trip_and_legacy_defaults_to_indexed() -> None:
    controller = _controller()
    indexed = controller.create_operation(operation_id="indexed")
    buildup = controller.create_operation("tube_buildup", operation_id="buildup")
    continuous = controller.create_operation("tube_continuous", operation_id="continuous")

    assert indexed.type_config is None
    assert buildup.type_config.maximum_pass_spacing_mm == 0.6
    assert continuous.type_config.seam_angle_deg == 0.0
    restored = TubeSetupController.from_json(json.loads(json.dumps(controller.to_json())), cad_model=None)
    assert [item.operation_type for item in restored.operations] == [
        "tube_thin_wall_indexed",
        "tube_buildup",
        "tube_continuous",
    ]
    legacy = TubeOperationDefinition.from_json({"operation_id": "old", "setup_id": "setup-1"})
    assert legacy.operation_type == "tube_thin_wall_indexed"
    assert legacy.type_config is None


def test_command_targets_operation_id_and_persists_special_fields() -> None:
    controller = _controller()
    provider = TubeCommandProvider()
    for operation_type, operation_id in (
        ("tube_thin_wall_indexed", "indexed"),
        ("tube_buildup", "buildup"),
        ("tube_continuous", "continuous"),
    ):
        provider.invoke(
            controller,
            CommandInvocation("create_operation", (operation_type,), {"operation_id": operation_id}),
        )

    provider.invoke(
        controller,
        CommandInvocation(
            "set_operation",
            kwargs={
                "operation_id": "buildup",
                "maximum_pass_spacing_mm": 0.45,
                "include_planar_base": True,
                "base_order": "after_tube",
            },
        ),
    )
    provider.invoke(
        controller,
        CommandInvocation("set_operation", kwargs={"operation_id": "continuous", "seam_angle_deg": 35}),
    )
    operations = {item.operation_id: item for item in controller.operations}
    assert operations["buildup"].type_config.maximum_pass_spacing_mm == pytest.approx(0.45)
    assert operations["buildup"].type_config.include_planar_base
    assert operations["buildup"].type_config.base_order == "after_tube"
    assert operations["continuous"].type_config.seam_angle_deg == pytest.approx(35.0)
    with pytest.raises(Exception, match="operation_id is required"):
        provider.invoke(controller, CommandInvocation("set_operation", kwargs={"name": "ambiguous"}))


def test_controller_product_state_becomes_stale_and_reopens() -> None:
    source = Path(__file__).resolve().parents[1] / "example" / "pipe2" / "弯管新.stp"
    controller = TubeSetupController(load_step(source))
    controller.create_operation(operation_id="indexed")
    controller.configure_operation(
        tube_body_id="body_002",
        entry_port_id="body_002_edge_0003",
        exit_port_id="body_002_edge_0014",
        substrate_body_id="body_001",
        parameters=TubeProcessParameters(bead_width_mm=10.0, layer_height_mm=10.0, safe_clearance_mm=15.0),
    )
    controller.select_machine(
        replace(
            GENERIC_XYZAC_REFERENCE,
            joints=tuple(
                replace(item, soft_limit_min=-1000.0, soft_limit_max=1000.0)
                for item in GENERIC_XYZAC_REFERENCE.joints
            ),
        )
    )
    controller.select_nozzle(
        NozzleProfile(
            resource_id="test-nozzle",
            display_name="Test nozzle",
            orifice_diameter_mm=0.4,
            filament_diameter_mm=1.75,
            interface="M6",
            length_mm=2.0,
            outer_profile_rz_mm=((0.2, 0.0), (0.3, 2.0)),
        )
    )
    controller.generate_operation("indexed")
    assert controller.product_state("indexed") is not None
    restored = TubeSetupController.from_json(json.loads(json.dumps(controller.to_json())))
    assert restored.product_state("indexed") is not None
    controller.configure_operation(
        operation_id="indexed",
        tube_body_id="body_002",
        entry_port_id="body_002_edge_0003",
        exit_port_id="body_002_edge_0014",
        substrate_body_id="body_001",
        parameters=TubeProcessParameters(bead_width_mm=10.0, layer_height_mm=9.0, safe_clearance_mm=15.0),
    )
    assert controller.product_state("indexed").status == "stale"
