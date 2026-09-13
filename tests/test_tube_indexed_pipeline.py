from __future__ import annotations

import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from dataclasses import replace

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.algorithms.tube.geometry import (  # noqa: E402
    TubeRecognitionError,
    manual_tube_feature,
    recognise_tube,
)
from five_axis_slicer.algorithms.tube.indexed import (  # noqa: E402
    TubePlanningError,
    generate_indexed_toolpath,
    plan_indexed_slices,
)
from five_axis_slicer.algorithms.tube.section import section_tube_layer  # noqa: E402
from five_axis_slicer.kinematics.xyzac import (  # noqa: E402
    MachineAxisSample,
    MachineAxisTrajectory,
    XYZACInverseKinematicsError,
    solve_xyzac_trajectory,
)
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE  # noqa: E402
from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    GeometryReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.references import geometry_reference  # noqa: E402
from five_axis_slicer.manufacturing.resources import NozzleProfile  # noqa: E402
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    TubeGeometrySelection,
    TubeOperationDefinition,
    TubeProcessParameters,
)
from five_axis_slicer.manufacturing.toolpath import (  # noqa: E402
    GeneratedToolpath,
    ToolpathPoint,
)
from five_axis_slicer.models import EdgeInfo  # noqa: E402
from five_axis_slicer.step_loader import load_step  # noqa: E402
from five_axis_slicer.tube_controller import TubeSetupController  # noqa: E402
from five_axis_slicer.validation.indexed_tube import (  # noqa: E402
    CollisionBox,
    validate_indexed_tube,
)


def _selection(model, body_id: str, entry_id: str, exit_id: str, substrate_id: str):
    return TubeGeometrySelection(
        geometry_reference(model, body_id, "body"),
        geometry_reference(model, entry_id, "edge"),
        geometry_reference(model, exit_id, "edge"),
        geometry_reference(model, substrate_id, "body"),
    )


def _outer_ports(model, outer_radius: float):
    ports = [
        edge
        for edge in model.edges
        if edge.curve_type == "circle"
        and edge.radius is not None
        and math.isclose(edge.radius, outer_radius, abs_tol=1.0e-6)
        and len(edge.face_ids) == 2
    ]
    return sorted(ports, key=lambda edge: edge.center or (0.0, 0.0, 0.0))


def _toolpath_for_angles(angles: list[tuple[float, float]]) -> GeneratedToolpath:
    points = []
    profile = GENERIC_XYZAC_REFERENCE
    fixed = (0.0, 0.0, -1.0)
    for index, (a_value, c_value) in enumerate(angles):
        transform = profile.link_transform("c_table", {"A": a_value, "C": c_value})
        nozzle_axis = transform.inverse().transform_vector(fixed)
        points.append(
            ToolpathPoint(
                f"ik-{index}",
                (250.0, 250.0, 100.0 + index),
                (1.0, 0.0, 0.0),
                nozzle_axis,
                "tube-op",
                "region-1",
                "layer-1",
                "region-1",
                "travel",
                feedrate_mm_min=600.0,
            )
        )
    return GeneratedToolpath("ik-path", "tube-op", points=tuple(points))


def _fake_trajectory(toolpath: GeneratedToolpath) -> MachineAxisTrajectory:
    samples = tuple(
        MachineAxisSample(
            point.point_id,
            float(index),
            {"X": 100.0, "Y": 100.0, "Z": 100.0, "A": 0.0, "C": 0.0},
        )
        for index, point in enumerate(toolpath.points)
    )
    return MachineAxisTrajectory("fake-axis", "test-machine", toolpath.toolpath_id, samples)


def _complete_nozzle() -> NozzleProfile:
    return NozzleProfile(
        resource_id="tube-validation-nozzle",
        display_name="Tube validation nozzle",
        orifice_diameter_mm=0.6,
        filament_diameter_mm=1.75,
        interface="M6 test interface",
        length_mm=12.5,
        outer_profile_rz_mm=((0.3, 0.0), (3.0, 2.0), (3.0, 12.5), (0.3, 12.5)),
    )


class TubeInputAndGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipe2 = load_step(ROOT / "example" / "pipe2" / "弯管新.stp")

    def test_operation_roles_parameters_dirty_and_round_trip(self) -> None:
        controller = TubeSetupController(self.pipe2)
        controller.create_operation(operation_id="tube-op")
        parameters = TubeProcessParameters(layer_height_mm=0.25, max_wedge_angle_deg=12.0)
        operation = controller.configure_operation(
            tube_body_id="body_002",
            entry_port_id="body_002_edge_0003",
            exit_port_id="body_002_edge_0014",
            substrate_body_id="body_001",
            parameters=parameters,
        )

        self.assertTrue(operation.geometry.is_complete)
        self.assertEqual(operation.parameters.layer_height_mm, 0.25)
        self.assertIn("operation_geometry_changed", operation.dirty_reasons)
        self.assertEqual(TubeOperationDefinition.from_json(operation.to_json()), operation)

    def test_operation_rejects_role_aliasing_and_invalid_parameter_ranges(self) -> None:
        body = geometry_reference(self.pipe2, "body_002", "body")
        edge = geometry_reference(self.pipe2, "body_002_edge_0003", "edge")
        with self.assertRaisesRegex(ValueError, "must be different"):
            TubeGeometrySelection(body, edge, edge, body)
        with self.assertRaisesRegex(ValueError, "90 degrees"):
            TubeProcessParameters(max_wedge_angle_deg=91.0)

    def test_pipe2_recognition_uses_current_step_topology(self) -> None:
        feature = recognise_tube(
            self.pipe2,
            _selection(
                self.pipe2,
                "body_002",
                "body_002_edge_0003",
                "body_002_edge_0014",
                "body_001",
            ),
        )
        self.assertEqual([segment.kind for segment in feature.centerline], ["line", "arc", "line"])
        self.assertAlmostEqual(feature.outer_radius_mm, 16.0, 6)
        self.assertAlmostEqual(feature.inner_radius_mm, 15.0, 6)
        self.assertAlmostEqual(feature.centerline[1].sweep_rad, math.radians(-70.513331), 6)
        self.assertAlmostEqual(feature.wall_thickness_mm, 1.0, 6)

    def test_independently_generated_straight_and_arc_steps_match_truth(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            straight_path = root / "straight.step"
            arc_path = root / "arc.step"
            cq.exporters.export(
                cq.Workplane("XY").circle(10.0).circle(8.0).extrude(100.0),
                str(straight_path),
            )
            radius = 30.0
            path = (
                cq.Workplane("YZ")
                .moveTo(0.0, 0.0)
                .threePointArc(
                    (radius - radius / math.sqrt(2.0), radius / math.sqrt(2.0)),
                    (radius, radius),
                )
                .wire()
            )
            cq.exporters.export(
                cq.Workplane("XY").circle(10.0).circle(8.0).sweep(path, isFrenet=True),
                str(arc_path),
            )
            for step_path, expected_length in (
                (straight_path, 100.0),
                (arc_path, radius * math.pi * 0.5),
            ):
                model = load_step(step_path)
                ports = _outer_ports(model, 10.0)
                selection = TubeGeometrySelection(
                    geometry_reference(model, "body_001", "body"),
                    geometry_reference(model, ports[0].edge_id, "edge"),
                    geometry_reference(model, ports[-1].edge_id, "edge"),
                    geometry_reference(model, "body_001", "body").__class__(
                        "analytic-substrate", "body"
                    ),
                )
                feature = recognise_tube(model, selection)
                self.assertAlmostEqual(feature.centerline_length_mm, expected_length, 5)
                self.assertAlmostEqual(feature.wall_thickness_mm, 2.0, 6)

    def test_non_circular_port_is_localised(self) -> None:
        selection = _selection(
            self.pipe2,
            "body_002",
            "body_002_edge_0002",
            "body_002_edge_0014",
            "body_001",
        )
        with self.assertRaises(TubeRecognitionError) as raised:
            recognise_tube(self.pipe2, selection)
        self.assertEqual(raised.exception.code, "tube.port_not_circular")

    def test_selected_manual_centerline_edges_override_surface_chain(self) -> None:
        entry = self.pipe2.edge_map["body_002_edge_0003"]
        exit_port = self.pipe2.edge_map["body_002_edge_0014"]
        assert entry.center is not None and exit_port.center is not None
        manual = EdgeInfo(
            "manual_centerline_001",
            "manual-wire",
            1,
            2,
            curve_type="line",
            exact_length=math.dist(entry.center, exit_port.center),
            endpoints=(entry.center, exit_port.center),
        )
        model = replace(self.pipe2, edges=[*self.pipe2.edges, manual])
        selection = TubeGeometrySelection(
            geometry_reference(model, "body_002", "body"),
            geometry_reference(model, entry.edge_id, "edge"),
            geometry_reference(model, exit_port.edge_id, "edge"),
            geometry_reference(model, "body_001", "body"),
            (GeometryReference(manual.edge_id, "edge", parent_body_id=manual.body_id),),
        )

        feature = recognise_tube(model, selection)

        self.assertEqual(feature.source, "manual_edges")
        self.assertEqual([segment.kind for segment in feature.centerline], ["line"])


class IndexedPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.feature = manual_tube_feature(
            ((0.0, 0.0, 50.0), (0.0, 0.0, 54.0)),
            outer_radius_mm=2.0,
            inner_radius_mm=1.0,
        )
        self.parameters = TubeProcessParameters(
            bead_width_mm=0.6,
            layer_height_mm=1.0,
            contour_chord_error_mm=0.05,
        )

    def test_wedge_coverage_height_error_and_half_layer_locations(self) -> None:
        curved = manual_tube_feature(
            ((0.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 10.0, 10.0)),
            outer_radius_mm=2.0,
            inner_radius_mm=1.0,
        )
        plan = plan_indexed_slices(curved, self.parameters)
        self.assertEqual(plan.regions[0].start_distance_mm, 0.0)
        self.assertEqual(plan.regions[-1].end_distance_mm, curved.centerline_length_mm)
        self.assertEqual(plan.layers[0].centerline_distance_mm, 0.5)
        self.assertTrue(
            all(
                left.end_distance_mm == right.start_distance_mm
                for left, right in zip(plan.regions, plan.regions[1:])
            )
        )

    def test_partial_tail_gets_a_centered_owned_layer(self) -> None:
        feature = manual_tube_feature(
            ((0.0, 0.0, 0.0), (0.0, 0.0, 4.2)),
            outer_radius_mm=2.0,
            inner_radius_mm=1.0,
        )
        plan = plan_indexed_slices(feature, self.parameters)

        self.assertEqual(len(plan.layers), 5)
        self.assertAlmostEqual(plan.layers[-1].centerline_distance_mm, 4.1)
        self.assertLess(plan.layers[-1].centerline_distance_mm, feature.centerline_length_mm)

    def test_partial_tail_material_matches_analytic_annulus(self) -> None:
        # Independent solid volume; a 0.2 mm remainder must not receive 1 mm of material.
        for length in (0.2, 4.2, 4.0):
            with self.subTest(length=length):
                feature = manual_tube_feature(
                    ((0.0, 0.0, 0.0), (0.0, 0.0, length)),
                    outer_radius_mm=2.0,
                    inner_radius_mm=1.0,
                )
                parameters = replace(
                    self.parameters, bead_width_mm=1.0, contour_chord_error_mm=0.0001
                )
                plan = plan_indexed_slices(feature, parameters)
                path = generate_indexed_toolpath("partial-tail", feature, plan, parameters)
                expected = math.pi * (2.0**2 - 1.0**2) * length
                self.assertAlmostEqual(
                    sum(point.material_volume_mm3 for point in path.points),
                    expected,
                    delta=expected * 0.0001,
                )
                heights = {
                    point.layer_height_mm
                    for point in path.points
                    if point.point_type == "deposition"
                    and point.layer_id == plan.layers[-1].layer_id
                }
                self.assertEqual(len(heights), 1)
                self.assertAlmostEqual(heights.pop(), 0.2 if length != 4.0 else 1.0)

    def test_toolpath_has_closed_deposition_loops_and_explicit_safe_index_events(self) -> None:
        plan = plan_indexed_slices(self.feature, self.parameters)
        toolpath = generate_indexed_toolpath("tube-op", self.feature, plan, self.parameters)
        deposition = [point for point in toolpath.points if point.point_type == "deposition"]
        self.assertTrue(deposition)
        self.assertTrue(all(point.material_volume_mm3 > 0.0 for point in deposition))
        self.assertTrue(
            all(
                point.material_volume_mm3 == 0.0
                for point in toolpath.points
                if point.point_type != "deposition"
            )
        )
        self.assertIn("retract", {event.event_type for event in toolpath.events})
        self.assertIn("prime", {event.event_type for event in toolpath.events})
        for event in toolpath.events:
            if event.event_type == "retract":
                self.assertEqual(
                    event.context["extrusion_length_mm"],
                    -self.parameters.retract_length_mm,
                )
            elif event.event_type == "prime":
                self.assertEqual(
                    event.context["extrusion_length_mm"],
                    self.parameters.retract_length_mm,
                )
        self.assertGreater(len(toolpath.to_preview_segments()), 0)

    def test_indexed_nozzle_is_fixed_per_region_not_wall_radial(self) -> None:
        plan = plan_indexed_slices(self.feature, self.parameters)
        path = generate_indexed_toolpath("fixed-axis", self.feature, plan, self.parameters)
        layers = {layer.layer_id: layer for layer in plan.layers}
        for point in path.points:
            if point.point_type == "deposition":
                expected = tuple(-v for v in layers[point.layer_id].plane_normal)
                self.assertEqual(point.nozzle_axis, expected)
                self.assertAlmostEqual(
                    sum(a * b for a, b in zip(point.nozzle_axis, point.surface_normal)), 0.0
                )

    def test_clearance_failure_is_localised(self) -> None:
        parameters = TubeProcessParameters(
            bead_width_mm=1.0,
            layer_height_mm=0.5,
            safe_clearance_mm=0.5,
        )
        plan = plan_indexed_slices(self.feature, parameters)
        with self.assertRaises(TubePlanningError) as raised:
            generate_indexed_toolpath("tube-op", self.feature, plan, parameters)
        self.assertEqual(raised.exception.code, "tube.safe_connection_clearance_insufficient")

    def test_exact_occt_section_recovers_outer_inner_and_midwall(self) -> None:
        model = TubeInputAndGeometryTests.pipe2
        contours = section_tube_layer(
            model,
            "body_002",
            (0.0, 0.0, 10.0),
            (0.0, 0.0, 1.0),
            1.0,
            sample_segments=64,
        )
        self.assertLess(math.dist(contours.outer[0], contours.outer[-1]), 1.0e-9)
        self.assertLess(math.dist(contours.inner[0], contours.inner[-1]), 1.0e-9)
        self.assertLess(contours.maximum_half_thickness_error_mm, 1.0e-5)

    def test_pipe2_toolpath_uses_exact_occt_sections(self) -> None:
        model = TubeInputAndGeometryTests.pipe2
        selection = _selection(
            model,
            "body_002",
            "body_002_edge_0003",
            "body_002_edge_0014",
            "body_001",
        )
        feature = recognise_tube(model, selection)
        parameters = TubeProcessParameters(
            bead_width_mm=10.0,
            layer_height_mm=10.0,
            safe_clearance_mm=10.0,
        )
        plan = plan_indexed_slices(feature, parameters)
        toolpath = generate_indexed_toolpath(
            "pipe2-exact",
            feature,
            plan,
            parameters,
            model=model,
        )

        self.assertEqual(
            {point.layer_id for point in toolpath.points}, {x.layer_id for x in plan.layers}
        )
        self.assertTrue(any(point.point_type == "deposition" for point in toolpath.points))


class XYZACKinematicsTests(unittest.TestCase):
    def test_fk_round_trip_branch_unwrap_and_tool_length(self) -> None:
        toolpath = _toolpath_for_angles(
            [(math.radians(30.0), math.radians(350.0)), (math.radians(30.0), math.radians(10.0))]
        )
        zero = solve_xyzac_trajectory(toolpath, GENERIC_XYZAC_REFERENCE)
        long_tool = solve_xyzac_trajectory(toolpath, GENERIC_XYZAC_REFERENCE, tool_length_mm=20.0)
        self.assertTrue(all(sample.fk_position_error_mm < 0.01 for sample in zero.samples))
        self.assertTrue(
            all(sample.fk_orientation_error_rad < math.radians(0.01) for sample in zero.samples)
        )
        self.assertLess(
            abs(
                long_tool.samples[1].joint_positions["C"]
                - long_tool.samples[0].joint_positions["C"]
            ),
            math.pi,
        )
        self.assertAlmostEqual(
            long_tool.samples[0].joint_positions["Z"] - zero.samples[0].joint_positions["Z"],
            20.0,
            8,
        )

    def test_singularity_is_reported_and_unreachable_orientation_rejected(self) -> None:
        singular = _toolpath_for_angles([(0.0, 0.0)])
        result = solve_xyzac_trajectory(singular, GENERIC_XYZAC_REFERENCE)
        self.assertTrue(result.samples[0].singular)
        self.assertIn("xyzac.rotary_singularity", {issue.code for issue in result.issues})
        bad_point = singular.points[0]
        unreachable = GeneratedToolpath(
            "bad",
            "tube-op",
            points=(
                ToolpathPoint(
                    bad_point.point_id,
                    bad_point.position,
                    bad_point.tangent,
                    (0.0, 0.0, 1.0),
                    bad_point.operation_id,
                    bad_point.stage_id,
                    bad_point.layer_id,
                    bad_point.region_id,
                    bad_point.point_type,
                    feedrate_mm_min=600.0,
                ),
            ),
        )
        with self.assertRaises(XYZACInverseKinematicsError) as raised:
            solve_xyzac_trajectory(unreachable, GENERIC_XYZAC_REFERENCE)
        self.assertEqual(raised.exception.code, "xyzac.orientation_unreachable")

    def test_build_transform_and_nonzero_rotary_centres_close_through_fk(self) -> None:
        joints = tuple(
            replace(joint, rotation_center_mm=(10.0, 15.0, 5.0))
            if joint.joint_id in {"A", "C"}
            else joint
            for joint in GENERIC_XYZAC_REFERENCE.joints
        )
        profile = replace(GENERIC_XYZAC_REFERENCE, joints=joints)
        transform = RigidTransform.from_translation(
            (-20.0, -30.0, 10.0),
            source_frame="build",
            target_frame="workpiece",
        )
        result = solve_xyzac_trajectory(
            _toolpath_for_angles([(math.radians(25.0), math.radians(40.0))]),
            profile,
            tool_length_mm=12.0,
            T_workpiece_from_build=transform,
        )

        self.assertLess(result.samples[0].fk_position_error_mm, 0.01)
        self.assertLess(result.samples[0].fk_orientation_error_rad, math.radians(0.01))

    def test_rotary_velocity_and_acceleration_limits_are_reported(self) -> None:
        toolpath = _toolpath_for_angles(
            [
                (math.radians(30.0), math.radians(0.0)),
                (math.radians(30.0), math.radians(120.0)),
                (math.radians(30.0), math.radians(0.0)),
            ]
        )
        profile = replace(
            GENERIC_XYZAC_REFERENCE,
            joints=tuple(
                replace(joint, soft_limit_min=-1000.0, soft_limit_max=1000.0)
                if joint.joint_type == "linear"
                else joint
                for joint in GENERIC_XYZAC_REFERENCE.joints
            ),
        )
        fast_toolpath = replace(
            toolpath,
            points=tuple(replace(point, feedrate_mm_min=1.0e9) for point in toolpath.points),
        )
        result = solve_xyzac_trajectory(fast_toolpath, profile)
        codes = {issue.code for issue in result.issues}

        self.assertIn("xyzac.velocity_limit_exceeded", codes)
        self.assertIn("xyzac.acceleration_limit_exceeded", codes)


class IndexedValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.feature = manual_tube_feature(
            ((0.0, 0.0, 50.0), (0.0, 0.0, 52.0)),
            outer_radius_mm=2.0,
            inner_radius_mm=1.0,
        )
        self.parameters = TubeProcessParameters(layer_height_mm=1.0, contour_chord_error_mm=0.001)
        self.plan = plan_indexed_slices(self.feature, self.parameters)
        self.toolpath = generate_indexed_toolpath(
            "tube-op", self.feature, self.plan, self.parameters
        )
        self.trajectory = _fake_trajectory(self.toolpath)
        self.nozzle = _complete_nozzle()

    def test_clear_case_and_intermediate_swept_fixture_collision(self) -> None:
        clear = validate_indexed_tube(
            self.feature,
            self.plan,
            self.toolpath,
            self.trajectory,
            self.nozzle,
            obstacles=(
                CollisionBox("far", "fixture", (100.0, 100.0, 100.0), (101.0, 101.0, 101.0)),
            ),
            check_ipw=False,
        )
        self.assertFalse(clear.has_errors)
        first, second = self.toolpath.points[:2]
        midpoint = tuple((a + b) * 0.5 for a, b in zip(first.position, second.position))
        obstacle = CollisionBox(
            "fixture-mid-motion",
            "fixture",
            tuple(value - 0.1 for value in midpoint),
            tuple(value + 0.1 for value in midpoint),
        )
        collision = validate_indexed_tube(
            self.feature,
            self.plan,
            self.toolpath,
            self.trajectory,
            self.nozzle,
            obstacles=(obstacle,),
            check_ipw=False,
            motion_sample_error_mm=0.05,
        )
        self.assertIn("tube.nozzle_obstacle_collision", {issue.code for issue in collision.issues})
        self.assertFalse(collision.ready_for_export)
        self.assertGreater(collision.collision_samples_checked, len(self.toolpath.points))

    def test_substrate_tip_contact_is_allowed_but_fixture_contact_is_not(self) -> None:
        deposition = next(
            point for point in self.toolpath.points if point.point_type == "deposition"
        )
        bounds = (
            tuple(value - 0.02 for value in deposition.position),
            tuple(value + 0.02 for value in deposition.position),
        )
        substrate = CollisionBox("substrate", "substrate", *bounds)
        fixture = CollisionBox("fixture", "fixture", *bounds)
        slender_nozzle = replace(
            self.nozzle,
            outer_profile_rz_mm=((0.3, 0.0), (0.05, 2.0), (0.05, 12.5)),
        )
        # Isolate the deposition contact. The subsequent departure can still
        # intersect this deliberately surrounding box and must remain checked.
        contact_path = replace(self.toolpath, points=self.toolpath.points[:2], events=())
        contact_trajectory = _fake_trajectory(contact_path)

        allowed = validate_indexed_tube(
            self.feature,
            self.plan,
            contact_path,
            contact_trajectory,
            slender_nozzle,
            obstacles=(substrate,),
            check_ipw=False,
        )
        blocked = validate_indexed_tube(
            self.feature,
            self.plan,
            contact_path,
            contact_trajectory,
            slender_nozzle,
            obstacles=(fixture,),
            check_ipw=False,
        )

        self.assertNotIn("tube.nozzle_obstacle_collision", {x.code for x in allowed.issues})
        self.assertIn("tube.nozzle_obstacle_collision", {x.code for x in blocked.issues})

    def test_printed_ipw_collision_blocks_export(self) -> None:
        # Deliberately point the shank sideways into existing material.
        path = replace(
            self.toolpath,
            points=tuple(
                replace(point, nozzle_axis=(1.0, 0.0, 0.0)) for point in self.toolpath.points
            ),
        )
        report = validate_indexed_tube(
            self.feature,
            self.plan,
            path,
            self.trajectory,
            self.nozzle,
            check_ipw=True,
        )

        self.assertIn("tube.nozzle_ipw_collision", {issue.code for issue in report.issues})
        self.assertFalse(report.ready_for_export)


if __name__ == "__main__":
    unittest.main()
