from __future__ import annotations

from dataclasses import replace
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    CoordinateFrameDefinition,
    DirectionReference,
    GeometryReference,
    PointReference,
)
from five_axis_slicer.manufacturing.references import (  # noqa: E402
    RebindStatus,
    geometry_reference,
    rebind_geometry_reference,
)
from five_axis_slicer.manufacturing.machine import (  # noqa: E402
    CARTESIAN_REFERENCE,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    BUILD_CS_NODE,
    MODEL_CS_NODE,
    PART_NODE,
    NodeState,
)
from five_axis_slicer.models import (  # noqa: E402
    BodyInfo,
    BoundingBox,
    CadModel,
    EdgeInfo,
    FaceInfo,
    VertexInfo,
)
from five_axis_slicer.tube_controller import TubeSetupController  # noqa: E402


def _translated(point: tuple[float, float, float], delta: float) -> tuple[float, float, float]:
    return tuple(value + delta for value in point)  # type: ignore[return-value]


def cad_model(
    labels: tuple[str, ...],
    *,
    delta: float = 0.0,
    scale: float = 1.0,
) -> CadModel:
    bodies: list[BodyInfo] = []
    faces: list[FaceInfo] = []
    edges: list[EdgeInfo] = []
    vertices: list[VertexInfo] = []
    shapes: dict[str, object] = {}
    face_shapes: dict[str, object] = {}
    edge_shapes: dict[str, object] = {}
    vertex_shapes: dict[str, object] = {}

    def point(x: float, y: float, z: float) -> tuple[float, float, float]:
        return _translated((x * scale, y * scale, z * scale), delta)

    for index, label in enumerate(labels, start=1):
        body_id = f"{label}-body"
        face_id = f"{label}-face"
        edge_id = f"{label}-edge"
        first_vertex_id = f"{label}-vertex-a"
        second_vertex_id = f"{label}-vertex-b"
        body_bounds = BoundingBox(point(0, 0, 0), point(10, 20, 30))
        face_bounds = BoundingBox(point(0, 0, 0), point(10, 20, 0))
        first_point = point(0, 0, 0)
        second_point = point(10, 0, 0)

        bodies.append(
            BodyInfo(
                body_id,
                index,
                f"Body {label}",
                (0.4, 0.5, 0.6),
                kind="solid",
                bounds=body_bounds,
                volume=6000.0 * scale**3,
                surface_area=2200.0 * scale**2,
                centroid=point(5, 10, 15),
                edge_ids=[edge_id],
                face_ids=[face_id],
                vertex_ids=[first_vertex_id, second_vertex_id],
                signature=f"body-{label}",
            )
        )
        faces.append(
            FaceInfo(
                face_id,
                body_id,
                1,
                "plane",
                200.0 * scale**2,
                point(5, 10, 0),
                face_bounds,
                edge_ids=[edge_id],
                normal=(0.0, 0.0, 1.0),
                axis_origin=point(5, 10, 0),
                signature=f"face-{label}",
            )
        )
        edges.append(
            EdgeInfo(
                edge_id,
                body_id,
                1,
                2,
                length_hint=10.0 * scale,
                curve_type="line",
                exact_length=10.0 * scale,
                vertex_ids=[first_vertex_id, second_vertex_id],
                face_ids=[face_id],
                endpoints=(first_point, second_point),
                arc_length_midpoint=point(5, 0, 0),
                center=first_point,
                axis_direction=(1.0, 0.0, 0.0),
                signature=f"edge-{label}",
            )
        )
        vertices.extend(
            (
                VertexInfo(
                    first_vertex_id,
                    body_id,
                    1,
                    first_point,
                    edge_ids=[edge_id],
                    signature=f"vertex-a-{label}",
                ),
                VertexInfo(
                    second_vertex_id,
                    body_id,
                    2,
                    second_point,
                    edge_ids=[edge_id],
                    signature=f"vertex-b-{label}",
                ),
            )
        )
        shapes[body_id] = object()
        face_shapes[face_id] = object()
        edge_shapes[edge_id] = object()
        vertex_shapes[first_vertex_id] = object()
        vertex_shapes[second_vertex_id] = object()

    return CadModel(
        source_path=Path(f"{labels[0] if labels else 'empty'}.step"),
        source_hash=(labels[0][0] if labels else "0") * 64,
        bodies=bodies,
        faces=faces,
        edges=edges,
        vertices=vertices,
        shapes=shapes,
        face_shapes=face_shapes,
        edge_shapes=edge_shapes,
        vertex_shapes=vertex_shapes,
    )


def coordinate_frame(
    model: CadModel,
    *,
    frame_id: str = "model",
    legacy_hash_only: bool = False,
) -> CoordinateFrameDefinition:
    def reference(object_id: str, kind: str) -> GeometryReference:
        if not legacy_hash_only:
            return geometry_reference(model, object_id, kind)
        item = {
            "face": model.face_map,
            "edge": model.edge_map,
            "vertex": model.vertex_map,
        }[kind][object_id]
        return GeometryReference(
            object_id,
            kind,
            {"sha256": item.signature},
            parent_body_id=item.body_id,
        )

    body = model.bodies[0]
    face = model.face_map[body.face_ids[0]]
    edge = model.edge_map[body.edge_ids[0]]
    vertex = model.vertex_map[body.vertex_ids[0]]
    return CoordinateFrameDefinition.from_references(
        frame_id,
        f"{frame_id.title()} CS",
        PointReference(
            "vertex",
            vertex.point,
            geometry=reference(vertex.vertex_id, "vertex"),
            confirmed=True,
        ),
        DirectionReference(
            "plane_normal",
            face.normal,
            geometry=reference(face.face_id, "face"),
            confirmed=True,
        ),
        DirectionReference(
            "line_edge",
            edge.axis_direction,
            geometry=reference(edge.edge_id, "edge"),
            confirmed=True,
        ),
    )


def apply_coordinate_frame(
    controller: TubeSetupController,
    frame: CoordinateFrameDefinition,
    node: str = MODEL_CS_NODE,
) -> None:
    controller.begin_coordinate_draft(node)
    controller.set_origin_reference(node, frame.origin_reference)
    controller.set_direction_reference(
        node,
        "z",
        frame.z_direction_reference,
    )
    controller.set_direction_reference(
        node,
        "x",
        frame.x_direction_reference,
    )
    controller.apply_coordinate_draft(node)


class GeometryRebindingTests(unittest.TestCase):
    def test_reference_contains_auditable_parent_geometry_and_adjacency(self) -> None:
        model = cad_model(("old",))
        reference = geometry_reference(model, "old-face", "face")
        signature = reference.to_json()["signature"]

        self.assertEqual(signature["schema_version"], 1)
        self.assertEqual(signature["geometry_type"], "face")
        self.assertEqual(signature["parent_body"]["dimensions_mm"], [10.0, 20.0, 30.0])
        self.assertEqual(signature["descriptor"]["surface_type"], "plane")
        self.assertEqual(signature["descriptor"]["area_mm2"], 200.0)
        self.assertEqual(signature["descriptor"]["adjacency"]["curve_types"], ["line"])

    def test_unique_match_rebinds_part_and_recalculates_coordinate_references(
        self,
    ) -> None:
        source = cad_model(("old",))
        target = cad_model(("new",), delta=5.0e-7)
        controller = TubeSetupController(source)
        controller.confirm_assignments(("old-body",))
        controller.create_operation(operation_id="tube-1")
        apply_coordinate_frame(controller, coordinate_frame(source, legacy_hash_only=True))

        result = controller.update_cad_model(target)

        self.assertEqual(result.body_bindings, {"old-body": "new-body"})
        self.assertEqual(controller.setup.assignments.part_body_ids, ("new-body",))
        rebound = controller.setup.model_coordinate_system
        self.assertIsNotNone(rebound)
        assert rebound is not None
        self.assertEqual(rebound.origin_reference.geometry.object_id, "new-vertex-a")
        self.assertEqual(rebound.z_direction_reference.geometry.object_id, "new-face")
        self.assertEqual(rebound.x_direction_reference.geometry.object_id, "new-edge")
        self.assertEqual(rebound.origin_reference.resolved_point, (5.0e-7,) * 3)
        self.assertTrue(rebound.is_valid)
        self.assertIs(controller.validation_report().state_for(PART_NODE), NodeState.VALID)
        self.assertIs(controller.validation_report().state_for(MODEL_CS_NODE), NodeState.VALID)
        self.assertIn("source_geometry_updated", controller.operations[0].dirty_reasons)

    def test_missing_matches_keep_auditable_references_and_invalidate_nodes(
        self,
    ) -> None:
        source = cad_model(("old",))
        target = cad_model(("changed",), scale=2.0)
        controller = TubeSetupController(source)
        controller.confirm_assignments(("old-body",))
        original_frame = coordinate_frame(source)
        apply_coordinate_frame(controller, original_frame)
        original_frame = controller.setup.model_coordinate_system
        assert original_frame is not None
        apply_coordinate_frame(controller, coordinate_frame(source), BUILD_CS_NODE)

        result = controller.update_cad_model(target)
        report = controller.validation_report()

        self.assertIn(PART_NODE, result.invalid_nodes)
        self.assertIn(MODEL_CS_NODE, result.invalid_nodes)
        self.assertIn(BUILD_CS_NODE, result.invalid_nodes)
        self.assertEqual(controller.setup.assignments.part_body_ids, ("old-body",))
        self.assertIs(controller.setup.model_coordinate_system, original_frame)
        self.assertIs(report.state_for(PART_NODE), NodeState.INVALID)
        self.assertIs(report.state_for(MODEL_CS_NODE), NodeState.INVALID)
        self.assertIs(report.state_for(BUILD_CS_NODE), NodeState.INVALID)
        codes = {issue.code for issue in report.issues}
        self.assertIn("PART_BODY_REBIND_MISSING", codes)
        self.assertIn("GEOMETRY_REFERENCE_REBIND_MISSING", codes)

    def test_ambiguous_geometry_is_never_selected_by_candidate_order(self) -> None:
        source = cad_model(("old",))
        target = cad_model(("left", "right"))
        face_reference = geometry_reference(source, "old-face", "face")

        match = rebind_geometry_reference(face_reference, target)

        self.assertIs(match.status, RebindStatus.AMBIGUOUS)
        self.assertIsNone(match.rebound_reference)
        self.assertEqual(match.candidate_ids, ("left-face", "right-face"))
        self.assertEqual(match.issue.code, "GEOMETRY_REFERENCE_REBIND_AMBIGUOUS")

        controller = TubeSetupController(source)
        controller.confirm_assignments(("old-body",))
        apply_coordinate_frame(controller, coordinate_frame(source))
        result = controller.update_cad_model(target)
        codes = {issue.code for issue in result.issues}
        self.assertIn("PART_BODY_REBIND_AMBIGUOUS", codes)
        self.assertIn("GEOMETRY_REFERENCE_REBIND_AMBIGUOUS", codes)
        self.assertIs(controller.validation_report().state_for(PART_NODE), NodeState.INVALID)
        self.assertIs(controller.validation_report().state_for(MODEL_CS_NODE), NodeState.INVALID)

    def test_controller_rejects_tampered_geometry_authority_and_resolved_values(
        self,
    ) -> None:
        model = cad_model(("old",))
        controller = TubeSetupController(model)
        controller.confirm_assignments(("old-body",))
        apply_coordinate_frame(controller, coordinate_frame(model))
        apply_coordinate_frame(
            controller,
            coordinate_frame(model, frame_id="build"),
            BUILD_CS_NODE,
        )
        controller.select_machine(CARTESIAN_REFERENCE)
        controller.begin_placement_draft(mount_datum_id="build_plate_mount")
        controller.apply_placement_draft()
        self.assertTrue(controller.coordinates_valid)
        applied = controller.setup.model_coordinate_system
        assert applied is not None

        def signature_tamper() -> CoordinateFrameDefinition:
            payload = json.loads(json.dumps(applied.to_json()))
            payload["origin_reference"]["geometry"]["signature"]["descriptor"]["point_mm"][0] = 99.0
            return CoordinateFrameDefinition.from_json(payload)

        def geometry_type_tamper() -> CoordinateFrameDefinition:
            payload = json.loads(json.dumps(applied.to_json()))
            payload["origin_reference"]["geometry"]["geometry_type"] = "face"
            return CoordinateFrameDefinition.from_json(payload)

        def parent_body_tamper() -> CoordinateFrameDefinition:
            payload = json.loads(json.dumps(applied.to_json()))
            payload["origin_reference"]["geometry"]["parent_body_id"] = "forged-body"
            return CoordinateFrameDefinition.from_json(payload)

        def resolved_point_tamper() -> CoordinateFrameDefinition:
            forged_origin = replace(
                applied.origin_reference,
                point_in_source_mm=(1.0, 0.0, 0.0),
            )
            return CoordinateFrameDefinition.from_references(
                "model",
                "Model CS",
                forged_origin,
                applied.z_direction_reference,
                applied.x_direction_reference,
            )

        def resolved_direction_tamper() -> CoordinateFrameDefinition:
            forged_x = replace(
                applied.x_direction_reference,
                direction_in_source=(1.0, 1.0, 0.0),
            )
            return CoordinateFrameDefinition.from_references(
                "model",
                "Model CS",
                applied.origin_reference,
                applied.z_direction_reference,
                forged_x,
            )

        def two_point_value_tamper() -> CoordinateFrameDefinition:
            body = model.bodies[0]
            first = model.vertex_map[body.vertex_ids[0]]
            second = model.vertex_map[body.vertex_ids[1]]
            forged_x = DirectionReference(
                "two_points",
                geometry=geometry_reference(model, first.vertex_id, "vertex"),
                secondary_geometry=geometry_reference(model, second.vertex_id, "vertex"),
                first_point_in_source_mm=(1.0, 0.0, 0.0),
                second_point_in_source_mm=second.point,
                confirmed=True,
            )
            return CoordinateFrameDefinition.from_references(
                "model",
                "Model CS",
                applied.origin_reference,
                applied.z_direction_reference,
                forged_x,
            )

        def face_pick_off_surface_tamper() -> CoordinateFrameDefinition:
            body = model.bodies[0]
            face = model.face_map[body.face_ids[0]]
            forged_origin = PointReference(
                "face_pick",
                (5.0, 10.0, 10.0),
                geometry=geometry_reference(model, face.face_id, "face"),
                confirmed=True,
            )
            return CoordinateFrameDefinition.from_references(
                "model",
                "Model CS",
                forged_origin,
                applied.z_direction_reference,
                applied.x_direction_reference,
            )

        cases = (
            ("signature", signature_tamper, "COORDINATE_GEOMETRY_REFERENCE_MISMATCH"),
            (
                "geometry_type",
                geometry_type_tamper,
                "COORDINATE_GEOMETRY_REFERENCE_MISMATCH",
            ),
            (
                "parent_body_id",
                parent_body_tamper,
                "COORDINATE_GEOMETRY_REFERENCE_MISMATCH",
            ),
            (
                "resolved_point",
                resolved_point_tamper,
                "COORDINATE_RESOLVED_POINT_MISMATCH",
            ),
            (
                "resolved_direction",
                resolved_direction_tamper,
                "COORDINATE_RESOLVED_DIRECTION_MISMATCH",
            ),
            (
                "two_point_value",
                two_point_value_tamper,
                "COORDINATE_RESOLVED_POINT_MISMATCH",
            ),
            (
                "face_pick_off_surface",
                face_pick_off_surface_tamper,
                "COORDINATE_RESOLVED_POINT_MISMATCH",
            ),
        )
        for name, make_frame, expected_code in cases:
            with self.subTest(name=name):
                setup = replace(
                    controller.setup,
                    model_coordinate_system=make_frame(),
                )
                self.assertTrue(setup.coordinates_valid)
                restored = TubeSetupController(model, setup=setup)

                report = restored.validation_report()

                self.assertIs(report.state_for(MODEL_CS_NODE), NodeState.INVALID)
                self.assertFalse(report.coordinates_valid)
                self.assertIn(expected_code, {issue.code for issue in report.issues})


if __name__ == "__main__":
    unittest.main()
