from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

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
        import cadquery as cq

        cls.directory = TemporaryDirectory()
        cls.source = Path(cls.directory.name) / "straight-product.step"
        tube = cq.Workplane("XY").circle(3).circle(2).extrude(0.6).translate((0, 0, 5)).val()
        base = cq.Workplane("XY").circle(4).extrude(1).translate((0, 0, 4)).val()
        cq.exporters.export(cq.Compound.makeCompound([tube, base]), str(cls.source))
        cls.model = load_step(cls.source)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.directory.cleanup()

    def _operation(self):
        ports = sorted(
            (
                edge
                for edge in self.model.edges
                if edge.curve_type == "circle"
                and edge.radius is not None
                and abs(edge.radius - 3) < 1e-6
            ),
            key=lambda edge: edge.center[2],
        )
        body = ports[0].body_id
        substrate = next(item.body_id for item in self.model.bodies if item.body_id != body)
        controller = TubeSetupController(self.model)
        controller.create_operation(operation_id="pipe2-indexed")
        return controller.configure_operation(
            tube_body_id=body,
            entry_port_id=ports[0].edge_id,
            exit_port_id=ports[-1].edge_id,
            substrate_body_id=substrate,
            parameters=TubeProcessParameters(
                bead_width_mm=0.6,
                layer_height_mm=0.2,
                safe_clearance_mm=2.0,
                contour_chord_error_mm=0.01,
                deposition_feedrate_mm_min=60,
                travel_feedrate_mm_min=60,
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

    def test_straight_tube_generates_exports_and_reads_back(self) -> None:
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
        self.assertIn(
            "xyzac.rotary_singularity", {issue.code for issue in result.validation.issues}
        )
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

    def test_cancellation_during_layer_generation_keeps_previous_state(self) -> None:
        operation = self._operation()
        previous = IndexedProductState(operation.operation_id, "0" * 64, "stale", None)
        service = TubeIndexedProductService(previous)
        requested = False
        from five_axis_slicer.algorithms.tube import bounded_indexed

        original = bounded_indexed.generate_bounded_indexed_toolpath

        def request_during_layers(*args, **kwargs):
            nonlocal requested
            requested = True
            return original(*args, **kwargs)

        with patch.object(
            bounded_indexed, "generate_bounded_indexed_toolpath", request_during_layers
        ):
            with patch(
                "five_axis_slicer.algorithms.tube.bounded_indexed.section_tube_layer"
            ) as section:
                with self.assertRaises(GenerationCancelled):
                    service.generate(
                        self.model,
                        operation,
                        self._machine(),
                        self._nozzle(),
                        cancelled=lambda: requested,
                    )
                section.assert_not_called()
        self.assertIs(service.state, previous)

    def test_cancellation_inside_solver_and_validation_keeps_previous_state(self) -> None:
        from five_axis_slicer.postprocessing import indexed_tube

        operation = self._operation()
        for phase in ("solve_xyzac_trajectory", "validate_indexed_tube"):
            with self.subTest(phase=phase):
                previous = IndexedProductState(operation.operation_id, "0" * 64, "stale", None)
                service = TubeIndexedProductService(previous)
                requested = False
                original = getattr(indexed_tube, phase)
                completed = []

                def request_inside_phase(*args, **kwargs):
                    nonlocal requested
                    requested = True
                    result = original(*args, **kwargs)
                    completed.append(phase)
                    return result

                with patch.object(indexed_tube, phase, request_inside_phase):
                    with self.assertRaises(GenerationCancelled):
                        service.generate(
                            self.model,
                            operation,
                            self._machine(),
                            self._nozzle(),
                            cancelled=lambda: requested,
                        )
                self.assertIs(service.state, previous)
                self.assertEqual(completed, [], "Cancellation must interrupt the active phase")

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
            parameters=replace(operation.parameters, layer_height_mm=0.3),
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
        operation = replace(
            operation,
            parameters=replace(
                operation.parameters, deposition_feedrate_mm_min=1200, travel_feedrate_mm_min=3000
            ),
        )
        result = TubeIndexedProductService().generate(
            self.model,
            operation,
            self._machine(),
            self._nozzle(),
            source_path=self.source,
            T_workpiece_from_build=self._placement(),
            check_ipw=True,
        )
        self.assertIn(
            "xyzac.acceleration_limit_exceeded", {issue.code for issue in result.validation.issues}
        )
        self.assertFalse(result.manifest.ready_for_export)
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "blocks export"):
                export_indexed_product(result, Path(directory) / "blocked")


if __name__ == "__main__":
    unittest.main()
