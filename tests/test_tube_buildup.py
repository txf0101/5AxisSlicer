from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.algorithms.tube.buildup import (  # noqa: E402
    PlanarBaseDefinition,
    TubeBuildupError,
    TubeBuildupParameters,
    generate_planar_base_toolpath,
    generate_tube_buildup_toolpath,
    plan_tube_buildup,
    sequence_buildup_operations,
)
from five_axis_slicer.algorithms.tube.geometry import (  # noqa: E402
    manual_tube_feature,
    recognise_tube,
)
from five_axis_slicer.manufacturing.coordinates import GeometryReference  # noqa: E402
from five_axis_slicer.manufacturing.references import geometry_reference  # noqa: E402
from five_axis_slicer.manufacturing.setup import TubeGeometrySelection  # noqa: E402
from five_axis_slicer.step_loader import load_step  # noqa: E402


def _outer_ports(model, outer_radius: float):
    return sorted(
        (
            edge
            for edge in model.edges
            if edge.curve_type == "circle"
            and edge.radius is not None
            and math.isclose(edge.radius, outer_radius, abs_tol=1.0e-6)
            and len(edge.face_ids) == 2
        ),
        key=lambda edge: edge.center or (0.0, 0.0, 0.0),
    )


def _recognise_single_body_tube(step_path: Path, outer_radius: float):
    model = load_step(step_path)
    ports = _outer_ports(model, outer_radius)
    selection = TubeGeometrySelection(
        geometry_reference(model, "body_001", "body"),
        geometry_reference(model, ports[0].edge_id, "edge"),
        geometry_reference(model, ports[-1].edge_id, "edge"),
        GeometryReference("analytic-substrate", "body"),
    )
    return model, recognise_tube(model, selection)


class TubeBuildupPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parameters = TubeBuildupParameters(
            bead_width_mm=1.0,
            layer_height_mm=1.0,
            maximum_pass_spacing_mm=1.0,
            safe_clearance_mm=2.0,
            contour_chord_error_mm=0.02,
        )

    def test_multi_pass_offsets_fill_wall_and_volume_is_physical(self) -> None:
        feature = manual_tube_feature(
            ((0.0, 0.0, 0.0), (0.0, 0.0, 2.0)),
            outer_radius_mm=10.0,
            inner_radius_mm=7.0,
        )
        plan = plan_tube_buildup(feature, self.parameters)
        toolpath = generate_tube_buildup_toolpath(
            "tube-buildup",
            feature,
            plan,
            self.parameters,
        )

        self.assertEqual(plan.pass_count, 3)
        self.assertEqual(plan.pass_offsets_mm, (-1.0, 0.0, 1.0))
        deposition = [point for point in toolpath.points if point.point_type == "deposition"]
        self.assertTrue(deposition)
        self.assertEqual({point.nozzle_axis for point in deposition}, {(0.0, 0.0, -1.0)})
        self.assertEqual({point.extrusion_role for point in deposition}, {"buildup"})
        self.assertTrue(all(point.material_volume_mm3 > 0.0 for point in deposition))
        ideal = 2.0 * math.pi * sum((7.5, 8.5, 9.5)) * 2.0
        actual = sum(point.material_volume_mm3 for point in deposition)
        self.assertAlmostEqual(actual, ideal, delta=ideal * 0.002)
        self.assertEqual(
            sum(point.material_volume_mm3 for point in toolpath.points),
            actual,
        )

    def test_partial_axial_layer_uses_actual_deposited_height(self) -> None:
        feature = manual_tube_feature(
            ((0.0, 0.0, 0.0), (0.0, 0.0, 2.25)),
            outer_radius_mm=10.0,
            inner_radius_mm=7.0,
        )
        plan = plan_tube_buildup(feature, self.parameters)
        toolpath = generate_tube_buildup_toolpath(
            "tube-tail",
            feature,
            plan,
            self.parameters,
        )

        self.assertEqual([layer.deposited_height_mm for layer in plan.layers], [1.0, 1.0, 0.25])
        last_layer = [point for point in toolpath.points if point.layer_id == "layer-00003"]
        self.assertEqual(
            {point.layer_height_mm for point in last_layer if point.point_type == "deposition"},
            {0.25},
        )

    def test_invalid_parameters_thin_wall_and_clearance_are_localised(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not exceed"):
            TubeBuildupParameters(bead_width_mm=0.6, maximum_pass_spacing_mm=0.7)
        thin = manual_tube_feature(
            ((0.0, 0.0, 0.0), (0.0, 0.0, 2.0)),
            outer_radius_mm=2.0,
            inner_radius_mm=1.5,
        )
        with self.assertRaises(TubeBuildupError) as thin_error:
            plan_tube_buildup(thin, self.parameters)
        self.assertEqual(thin_error.exception.code, "tube.buildup_wall_too_thin")

        feature = manual_tube_feature(
            ((0.0, 0.0, 0.0), (0.0, 0.0, 2.0)),
            outer_radius_mm=3.0,
            inner_radius_mm=1.0,
        )
        unsafe = replace(self.parameters, safe_clearance_mm=0.5)
        plan = plan_tube_buildup(feature, unsafe)
        with self.assertRaises(TubeBuildupError) as clearance_error:
            generate_tube_buildup_toolpath("unsafe", feature, plan, unsafe)
        self.assertEqual(
            clearance_error.exception.code,
            "tube.buildup_clearance_insufficient",
        )


class TubeBuildupStepParsingTests(unittest.TestCase):
    def test_straight_and_bent_step_tubes_generate_multi_pass_paths(self) -> None:
        with TemporaryDirectory() as directory:
            straight_path = Path(directory) / "straight.step"
            bent_path = Path(directory) / "bent.step"
            cq.exporters.export(
                cq.Workplane("XY").circle(10.0).circle(8.0).extrude(4.0),
                str(straight_path),
            )
            sweep_path = (
                cq.Workplane("YZ")
                .moveTo(0.0, 0.0)
                .threePointArc((5.857864, 14.142136), (20.0, 20.0))
                .wire()
            )
            cq.exporters.export(
                cq.Workplane("XY").circle(10.0).circle(8.0).sweep(sweep_path, isFrenet=True),
                str(bent_path),
            )
            parameters = TubeBuildupParameters(
                bead_width_mm=1.0,
                layer_height_mm=2.0,
                maximum_pass_spacing_mm=0.6,
                safe_clearance_mm=2.0,
                contour_chord_error_mm=0.1,
            )

            for path, expected_kinds in (
                (straight_path, ["line"]),
                (bent_path, ["arc"]),
            ):
                model, feature = _recognise_single_body_tube(path, 10.0)
                plan = plan_tube_buildup(feature, parameters)
                toolpath = generate_tube_buildup_toolpath(
                    f"parsed-{path.stem}",
                    feature,
                    plan,
                    parameters,
                    model=model,
                )
                self.assertEqual([item.kind for item in feature.centerline], expected_kinds)
                self.assertEqual(plan.pass_count, 3)
                self.assertTrue(any(point.point_type == "deposition" for point in toolpath.points))


class BaseAndOperationSequencingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parameters = TubeBuildupParameters(
            bead_width_mm=1.0,
            layer_height_mm=1.0,
            maximum_pass_spacing_mm=1.0,
            safe_clearance_mm=2.0,
            contour_chord_error_mm=0.05,
        )
        feature = manual_tube_feature(
            ((0.0, 0.0, 1.0), (0.0, 0.0, 3.0)),
            outer_radius_mm=3.0,
            inner_radius_mm=1.0,
        )
        plan = plan_tube_buildup(feature, self.parameters)
        self.tube = generate_tube_buildup_toolpath(
            "tube-operation",
            feature,
            plan,
            self.parameters,
        )
        base = PlanarBaseDefinition(
            "base-body",
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            radius_mm=5.0,
            height_mm=1.5,
        )
        self.base = generate_planar_base_toolpath("base-operation", base, self.parameters)

    def test_base_is_an_independent_nonempty_operation(self) -> None:
        self.assertEqual(self.base.operation_id, "base-operation")
        self.assertEqual(
            {point.layer_id for point in self.base.points},
            {"base-layer-00001", "base-layer-00002"},
        )
        self.assertTrue(
            all(
                point.extrusion_role == "buildup"
                for point in self.base.points
                if point.point_type == "deposition"
            )
        )
        tail = [point for point in self.base.points if point.layer_id == "base-layer-00002"]
        self.assertEqual(
            {point.layer_height_mm for point in tail if point.point_type == "deposition"},
            {0.5},
        )

    def test_base_before_and_after_orders_are_deterministic_and_safe(self) -> None:
        before = sequence_buildup_operations(
            "build-sequence",
            self.tube,
            base_toolpath=self.base,
            base_order="before_tube",
            safe_clearance_mm=2.0,
        )
        after = sequence_buildup_operations(
            "build-sequence",
            self.tube,
            base_toolpath=self.base,
            base_order="after_tube",
            safe_clearance_mm=2.0,
        )

        self.assertEqual(before.ordered_operation_ids, ("base-operation", "tube-operation"))
        self.assertEqual(after.ordered_operation_ids, ("tube-operation", "base-operation"))
        self.assertEqual(
            [event.event_type for event in before.transition_events],
            ["retract", "safe_depart", "operation_change", "safe_approach", "prime"],
        )
        self.assertEqual(
            before.transition_events[0].context["from_operation_id"],
            "base-operation",
        )
        self.assertEqual(
            before.transition_events[0].context["to_operation_id"],
            "tube-operation",
        )
        self.assertGreater(before.material_volume_mm3, 0.0)

    def test_sequence_rejects_invalid_order_duplicate_ids_and_low_clearance(self) -> None:
        with self.assertRaises(TubeBuildupError) as order_error:
            sequence_buildup_operations(
                "bad-order",
                self.tube,
                base_toolpath=self.base,
                base_order="sideways",  # type: ignore[arg-type]
                safe_clearance_mm=2.0,
            )
        self.assertEqual(order_error.exception.code, "tube.buildup_base_order_invalid")

        duplicate = replace(
            self.base,
            operation_id=self.tube.operation_id,
            points=tuple(
                replace(point, operation_id=self.tube.operation_id) for point in self.base.points
            ),
            events=tuple(
                replace(event, operation_id=self.tube.operation_id) for event in self.base.events
            ),
        )
        with self.assertRaises(TubeBuildupError) as id_error:
            sequence_buildup_operations(
                "duplicate",
                self.tube,
                base_toolpath=duplicate,
                safe_clearance_mm=2.0,
            )
        self.assertEqual(id_error.exception.code, "tube.buildup_operation_id_conflict")

        with self.assertRaises(TubeBuildupError) as clearance_error:
            sequence_buildup_operations(
                "low-clearance",
                self.tube,
                base_toolpath=self.base,
                safe_clearance_mm=0.5,
            )
        self.assertEqual(
            clearance_error.exception.code,
            "tube.buildup_transition_clearance_insufficient",
        )


if __name__ == "__main__":
    unittest.main()
