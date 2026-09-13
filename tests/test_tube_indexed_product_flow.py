from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE  # noqa: E402
from five_axis_slicer.manufacturing.coordinates import RigidTransform  # noqa: E402
from five_axis_slicer.manufacturing.resources import NozzleProfile  # noqa: E402
from five_axis_slicer.manufacturing.setup import TubeProcessParameters  # noqa: E402
from five_axis_slicer.postprocessing.indexed_tube import (  # noqa: E402
    GenerationCancelled,
    IndexedProductState,
    TubeIndexedProductService,
    export_indexed_product,
)
from five_axis_slicer.step_loader import load_step  # noqa: E402
from five_axis_slicer.tube_controller import TubeSetupController  # noqa: E402


class TubeIndexedProductFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = ROOT / "example" / "pipe2" / "弯管新.stp"
        cls.model = load_step(cls.source)

    def _operation(self):
        controller = TubeSetupController(self.model)
        controller.create_operation(operation_id="pipe2-indexed")
        return controller.configure_operation(
            tube_body_id="body_002",
            entry_port_id="body_002_edge_0003",
            exit_port_id="body_002_edge_0014",
            substrate_body_id="body_001",
            parameters=TubeProcessParameters(
                bead_width_mm=10.0,
                layer_height_mm=10.0,
                safe_clearance_mm=10.0,
                contour_chord_error_mm=0.01,
            ),
        )

    @staticmethod
    def _placement() -> RigidTransform:
        return RigidTransform.from_translation(
            (250.0, 250.0, -300.0), source_frame="build", target_frame="workpiece"
        )

    @staticmethod
    def _machine():
        return replace(
            GENERIC_XYZAC_REFERENCE,
            joints=tuple(
                replace(joint, soft_limit_min=-1000.0, soft_limit_max=1000.0)
                for joint in GENERIC_XYZAC_REFERENCE.joints
            ),
        )

    @staticmethod
    def _nozzle() -> NozzleProfile:
        return NozzleProfile(
            resource_id="pipe2-test-nozzle",
            display_name="Pipe2 test nozzle",
            orifice_diameter_mm=0.4,
            filament_diameter_mm=1.75,
            interface="M6",
            length_mm=2.0,
            outer_profile_rz_mm=((0.2, 0.0), (0.3, 2.0)),
        )

    def test_pipe2_generates_exports_and_reads_back(self) -> None:
        operation = self._operation()
        service = TubeIndexedProductService()
        result = service.generate(
            self.model,
            operation,
            self._machine(),
            self._nozzle(),
            source_path=self.source,
            T_workpiece_from_build=self._placement(),
            radial_error_limit_mm=0.025,
        )

        self.assertTrue(result.exportable)
        self.assertTrue(result.readback.passed)
        self.assertEqual(result.manifest.status.value, "warning")
        self.assertEqual(service.state.status, "warning")
        self.assertIn("xyzac.rotary_singularity", {issue.code for issue in result.validation.issues})
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "pipe2-output"
            export_indexed_product(result, destination)
            self.assertEqual(
                {item.name for item in destination.iterdir()},
                {
                    "machine_axes.csv",
                    "main.gcode",
                    "manifest.json",
                    "preview.json",
                    "toolpath.json",
                    "warnings.json",
                },
            )
            self.assertIn("T08 POINT", (destination / "main.gcode").read_text(encoding="utf-8"))

    def test_changed_parameters_become_stale_and_state_reopens(self) -> None:
        operation = self._operation()
        service = TubeIndexedProductService()
        service.generate(
            self.model,
            operation,
            self._machine(),
            self._nozzle(),
            source_path=self.source,
            T_workpiece_from_build=self._placement(),
            radial_error_limit_mm=0.025,
        )
        assert service.state is not None
        reopened = IndexedProductState.from_json(service.state.to_json())
        changed = replace(
            operation,
            parameters=replace(operation.parameters, layer_height_mm=8.0),
        )

        stale = reopened.stale_for(changed)

        self.assertEqual(stale.status, "stale")
        self.assertIsNotNone(stale.result_payload)

    def test_cancelled_export_leaves_last_complete_result_in_place(self) -> None:
        operation = self._operation()
        result = TubeIndexedProductService().generate(
            self.model,
            operation,
            self._machine(),
            self._nozzle(),
            source_path=self.source,
            T_workpiece_from_build=self._placement(),
            radial_error_limit_mm=0.025,
        )
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "pipe2-output"
            export_indexed_product(result, destination)
            original = (destination / "main.gcode").read_text(encoding="utf-8")
            with self.assertRaises(GenerationCancelled):
                export_indexed_product(result, destination, cancelled=lambda: True)
            self.assertEqual((destination / "main.gcode").read_text(encoding="utf-8"), original)

    def test_validation_error_cannot_be_exported(self) -> None:
        operation = self._operation()
        result = TubeIndexedProductService().generate(
            self.model,
            operation,
            self._machine(),
            self._nozzle(),
            source_path=self.source,
            T_workpiece_from_build=self._placement(),
            check_ipw=True,
        )
        self.assertFalse(result.manifest.ready_for_export)
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "blocks export"):
                export_indexed_product(result, Path(directory) / "blocked")


if __name__ == "__main__":
    unittest.main()
