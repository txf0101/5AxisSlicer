from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QEventLoop, QSettings, Qt, QTimer
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget

from five_axis_slicer.gcode_preview import PreviewSettings, load_gcode
from five_axis_slicer import background_load
from five_axis_slicer.manufacturing.coordinates import RigidTransform
from five_axis_slicer.manufacturing.preview_kinematics import (
    GENERIC_XYZAC_AC_SEMANTICS,
)
from five_axis_slicer.manufacturing.setup import (
    BUILD_CS_NODE,
    MACHINE_NODE,
    MODEL_CS_NODE,
    PLACEMENT_NODE,
    ManufacturingSetup,
    NodeState,
)
from five_axis_slicer.models import PickHit, SelectionState
from five_axis_slicer.project_io import ProjectFormatError, ProjectLoaded
from five_axis_slicer.step_loader import StepLoadError, load_step
from five_axis_slicer.tube_controller import DraftNotFoundError, TubeSetupController
from five_axis_slicer.ui import MainWindow


class TubeViewerStub(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = None
        self.selection = SelectionState()
        self.preview_settings = PreviewSettings()
        self.gcode_preview = None
        self.pick_callback = None
        self.pick_request = None
        self.coordinate_frames = ()
        self.active_coordinate_frame_id = None
        self.build_surface = None
        self.model_transform = None
        self.model_transform_history = []
        self.visible_path_segment_count = 0
        self.path_render_mode = "test"

    def set_selection_callback(self, _callback) -> None:
        return

    def set_pick_callback(self, callback) -> None:
        self.pick_callback = callback

    def set_pick_request(self, request) -> None:
        self.pick_request = request
        self.selection.mode = request.kind

    def load_model(self, model) -> None:
        self.model = model
        self.selection.clear()

    def clear_model(self) -> None:
        self.model = None
        self.selection.clear()

    def set_mode(self, mode: str) -> None:
        self.selection.mode = mode

    def set_selection(
        self,
        body_ids=None,
        edge_ids=None,
        face_ids=None,
        vertex_ids=None,
    ) -> None:
        if body_ids is not None:
            self.selection.body_ids = set(body_ids)
        if edge_ids is not None:
            self.selection.edge_ids = set(edge_ids)
        if face_ids is not None:
            self.selection.face_ids = set(face_ids)
        if vertex_ids is not None:
            self.selection.vertex_ids = set(vertex_ids)

    def clear_selection(self) -> None:
        self.selection.clear()

    def set_coordinate_frames(self, frames, *, active_frame_id=None) -> None:
        self.coordinate_frames = tuple(frames)
        self.active_coordinate_frame_id = active_frame_id

    def set_build_surface(self, surface) -> None:
        self.build_surface = surface

    def set_model_transform(self, matrix) -> None:
        self.model_transform = tuple(tuple(value for value in row) for row in matrix)
        self.model_transform_history.append(self.model_transform)

    def load_gcode_preview(self, preview) -> None:
        self.gcode_preview = preview
        self.visible_path_segment_count = len(preview.segments)

    def clear_gcode_preview(self) -> None:
        self.gcode_preview = None
        self.visible_path_segment_count = 0

    def preview_state(self) -> dict:
        return {"settings": self.preview_settings.to_json(), "progress": {}}

    def current_progress_step(self):
        return None

    def representative_path_segment(self):
        return None

    def set_preview_layers(self, low: int, high: int) -> None:
        self.preview_settings.layer_min = low
        self.preview_settings.layer_max = high

    def set_preview_progress(self, *_args, **_kwargs) -> None:
        return

    def set_progress_interaction(self, *_args) -> None:
        return

    def progress_state(self) -> dict:
        return {"layer_step_count": 0, "progress_index": 0, "current_step": None}

    def set_preview_visibility(self, **_kwargs) -> None:
        return

    def performance_state(self) -> dict:
        return {}

    def fit_view(self) -> None:
        return

    def home_view(self) -> None:
        return

    def camera_command(self, *_args) -> None:
        return


class TubeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        root = Path(__file__).resolve().parents[1]
        matches = list((root / "example" / "pipe2").glob("*.stp"))
        cls.pipe2 = matches[0] if matches else None

    def setUp(self) -> None:
        QSettings("5AxisSclicer", "5AxisSclicer V2.0").clear()

    def _window(self) -> MainWindow:
        window = MainWindow(http_port=0, model_viewer_factory=TubeViewerStub)
        self.addCleanup(window.close)
        return window

    def _wait_until(self, predicate, timeout: float = 8.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        self.fail("timed out while waiting for the model loader")

    def _loaded_tube_window(self) -> MainWindow:
        if self.pipe2 is None:
            self.skipTest("pipe2 STEP fixture is unavailable")
        window = self._window()
        window.open_model(self.pipe2, show_dialog=False)
        window.enter_workbench("tube")
        window.resize(1600, 900)
        window.show()
        self.app.processEvents()
        return window

    def _select_tube_node(self, window: MainWindow, node: str) -> None:
        page = window.tube_page
        item = page._tree_items[node]
        page.tree.scrollToItem(item)
        self.app.processEvents()
        rectangle = page.tree.visualItemRect(item)
        self.assertTrue(rectangle.isValid(), f"Tube tree item is not visible: {node}")
        QTest.mouseClick(page.tree.viewport(), Qt.LeftButton, pos=rectangle.center())
        self.app.processEvents()
        current = page.tree.currentItem()
        self.assertIsNotNone(current)
        self.assertEqual(current.data(0, Qt.UserRole), node)

    @staticmethod
    def _combo_index_for_kind(combo, kind: str) -> int:
        for index in range(combo.count()):
            payload = combo.itemData(index)
            if isinstance(payload, dict) and payload.get("kind") == kind:
                return index
        raise AssertionError(f"coordinate candidate kind is unavailable: {kind}")

    def _configure_coordinate_setup(
        self,
        window: MainWindow,
        *,
        create_operation: bool = False,
    ) -> None:
        page = window.tube_page
        part_ids = tuple(body.body_id for body in window.model.solid_bodies)
        page.controller.confirm_assignments(part_ids)
        page.select_builtin_resource("machine", "xyzac")
        page.apply_numeric_coordinate(
            MODEL_CS_NODE,
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 0.0),
        )
        page.apply_numeric_coordinate(
            BUILD_CS_NODE,
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 0.0),
        )
        page.apply_placement("build_plate_mount")
        if create_operation:
            page.controller.create_operation()
        page.refresh()

    def assertMatrixAlmostEqual(self, left, right, places: int = 9) -> None:
        self.assertEqual(len(left), len(right))
        for left_row, right_row in zip(left, right):
            self.assertEqual(len(left_row), len(right_row))
            for left_value, right_value in zip(left_row, right_row):
                self.assertAlmostEqual(left_value, right_value, places=places)

    def test_tube_page_has_dedicated_tree_and_bilingual_1600_layout(self) -> None:
        window = self._window()
        window.enter_workbench("tube")
        window.resize(1600, 900)
        window.show()
        self.app.processEvents()

        self.assertIs(window.stack.currentWidget(), window.tube_page)
        self.assertEqual(window.current_state()["page"], "tube")
        self.assertEqual(window.tube_page.tree.objectName(), "tubeOperationTree")
        self.assertIn(
            "Manufacturing Setup 1",
            window.tube_page.tree.topLevelItem(0).child(1).text(0),
        )
        self.assertLessEqual(window.tube_page.minimumSizeHint().width(), 1600)

        window.set_language("en")
        self.assertEqual(window.tube_page.open_button.text(), "Open STEP")
        self.assertEqual(window.tube_page.issue_title.text(), "Issues")

    def test_replacing_controller_without_model_clears_viewer_state(self) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page
        page.viewer.set_coordinate_frames((object(),), active_frame_id="stale")
        page.viewer.set_build_surface(object())
        page._pick_context = (MODEL_CS_NODE, "origin", "vertex")
        page._two_point_hits.append(object())

        page.set_controller(TubeSetupController(), None)

        self.assertIsNone(page.model)
        self.assertIsNone(page.viewer.model)
        self.assertEqual(page.viewer.selection.to_json()["body_ids"], [])
        self.assertEqual(page.viewer.coordinate_frames, ())
        self.assertIsNone(page.viewer.active_coordinate_frame_id)
        self.assertIsNone(page.viewer.build_surface)
        self.assertEqual(page.viewer.pick_request.kind, "body")
        self.assertEqual(page._candidate_payloads, {"origins": [], "directions": []})
        self.assertIsNone(page._pick_context)
        self.assertEqual(page._two_point_hits, [])

    def test_ui_rejects_multiple_setups_before_committing_project(self) -> None:
        window = MainWindow(http_port=0, model_viewer_factory=TubeViewerStub)
        loaded = ProjectLoaded(
            project_directory=Path("."),
            project_json=Path("project.json"),
            model=None,
            selection=SelectionState(),
            workbench={"workbench": "tube"},
            setups=(
                ManufacturingSetup(),
                ManufacturingSetup(setup_id="setup-2", name="Manufacturing Setup 2"),
            ),
            operations=(),
            resources={},
            migrated_from_v1=False,
            payload={},
        )

        with self.assertRaisesRegex(ProjectFormatError, "at most one"):
            window._commit_loaded_project(loaded)

    def test_ui_rejects_untyped_setup_before_mutating_committed_state(self) -> None:
        window = self._loaded_tube_window()
        committed_model = window.model
        committed_setup = window.tube_page.controller.setup
        committed_viewer_model = window.viewer.model
        loaded = ProjectLoaded(
            project_directory=Path("."),
            project_json=Path("project.json"),
            model=None,
            selection=SelectionState(),
            workbench={"workbench": "tube"},
            setups=({"name": "untyped"},),
            operations=(),
            resources={},
            migrated_from_v1=False,
            payload={},
        )

        with self.assertRaisesRegex(ProjectFormatError, "ManufacturingSetup"):
            window._commit_loaded_project(loaded)

        self.assertIs(window.model, committed_model)
        self.assertEqual(window.tube_page.controller.setup, committed_setup)
        self.assertIs(window.viewer.model, committed_viewer_model)

    def test_coordinate_geometry_picks_two_points_flip_apply_and_cancel(self) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page
        viewer = page.viewer
        self._select_tube_node(window, MODEL_CS_NODE)

        origin_combo, _origin_values, origin_pick, _origin_title = (
            page.coordinate_inputs["origin"]
        )
        origin_combo.setCurrentIndex(
            self._combo_index_for_kind(origin_combo, "pick_face")
        )
        QTest.mouseClick(origin_pick, Qt.LeftButton)
        self.assertEqual(viewer.pick_request.kind, "face")
        face = window.model.faces[0]
        viewer.pick_callback(PickHit("face", face.face_id, face.centroid))
        self.app.processEvents()
        face_reference = page.controller.coordinate_draft(
            MODEL_CS_NODE
        ).origin_reference
        self.assertEqual(face_reference.reference_type, "face_pick")
        self.assertEqual(face_reference.geometry.object_id, face.face_id)

        origin_combo.setCurrentIndex(
            self._combo_index_for_kind(origin_combo, "pick_vertex")
        )
        QTest.mouseClick(origin_pick, Qt.LeftButton)
        self.assertEqual(viewer.pick_request.kind, "vertex")
        origin_vertex = window.model.vertices[0]
        viewer.pick_callback(PickHit("vertex", origin_vertex.vertex_id))
        QTest.mouseClick(page.origin_confirm_button, Qt.LeftButton)

        first_vertex = window.model.vertices[0]
        second_vertex = next(
            vertex
            for vertex in window.model.vertices[1:]
            if math.dist(vertex.point, first_vertex.point) > 1.0e-6
        )
        z_combo, _z_values, z_pick, _z_title = page.coordinate_inputs["z"]
        z_combo.setCurrentIndex(
            self._combo_index_for_kind(z_combo, "pick_two_vertices")
        )
        QTest.mouseClick(z_pick, Qt.LeftButton)
        self.assertEqual(viewer.pick_request.kind, "vertex")
        self.assertTrue(viewer.pick_request.multiple)
        viewer.pick_callback(PickHit("vertex", first_vertex.vertex_id))
        self.assertIn("second vertex", page.coordinate_feedback.text().lower())
        viewer.pick_callback(PickHit("vertex", second_vertex.vertex_id))
        QTest.mouseClick(page.z_confirm_button, Qt.LeftButton)

        raw_z = tuple(
            right - left for left, right in zip(first_vertex.point, second_vertex.point)
        )
        z_length = math.sqrt(sum(value * value for value in raw_z))
        unit_z = tuple(value / z_length for value in raw_z)
        basis_vectors = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        x_direction = min(
            basis_vectors,
            key=lambda vector: abs(sum(a * b for a, b in zip(vector, unit_z))),
        )
        x_combo, x_values, _x_pick, _x_title = page.coordinate_inputs["x"]
        x_combo.setCurrentIndex(self._combo_index_for_kind(x_combo, "numeric"))
        for spin, value in zip(x_values, x_direction):
            spin.setValue(value)
        QTest.mouseClick(page.x_confirm_button, Qt.LeftButton)

        QTest.mouseClick(page.z_flip_button, Qt.LeftButton)
        flipped_draft = page.controller.coordinate_draft(MODEL_CS_NODE)
        self.assertTrue(flipped_draft.z_direction_reference.flipped)
        self.assertTrue(flipped_draft.z_direction_reference.confirmed)
        QTest.mouseClick(page.coordinate_apply_button, Qt.LeftButton)

        frame = page.controller.setup.model_coordinate_system
        self.assertIsNotNone(frame)
        self.assertTrue(frame.is_valid)
        self.assertEqual(frame.origin_reference.reference_type, "vertex")
        self.assertEqual(
            frame.origin_reference.geometry.object_id, origin_vertex.vertex_id
        )
        self.assertEqual(frame.z_direction_reference.reference_type, "two_points")
        self.assertEqual(
            frame.z_direction_reference.secondary_geometry.object_id,
            second_vertex.vertex_id,
        )
        self.assertTrue(frame.z_direction_reference.flipped)
        with self.assertRaises(DraftNotFoundError):
            page.controller.coordinate_draft(MODEL_CS_NODE)

        applied_payload = frame.to_json()
        self._select_tube_node(window, MACHINE_NODE)
        self._select_tube_node(window, MODEL_CS_NODE)
        QTest.mouseClick(page.z_flip_button, Qt.LeftButton)
        self.assertFalse(
            page.controller.coordinate_draft(
                MODEL_CS_NODE
            ).z_direction_reference.flipped
        )
        QTest.mouseClick(page.coordinate_cancel_button, Qt.LeftButton)
        self.assertEqual(
            page.controller.setup.model_coordinate_system.to_json(),
            applied_payload,
        )
        self.assertFalse(page.controller.has_drafts)

    def test_ui_propagates_coordinate_dirty_state_and_issue_navigation(self) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page
        viewer = page.viewer
        self._configure_coordinate_setup(window, create_operation=True)
        self.assertEqual(
            page.controller.operations[0].dirty_reasons,
            ("operation_created",),
        )

        self.assertEqual(page.state_json()["view_mode"], "machine")
        self.assertIsNotNone(viewer.build_surface)
        self.assertEqual(viewer.active_coordinate_frame_id, "machine")
        QTest.mouseClick(page.model_view_button, Qt.LeftButton)
        self.assertEqual(page.state_json()["view_mode"], "model")
        self.assertIsNone(viewer.build_surface)
        self.assertMatrixAlmostEqual(
            viewer.model_transform,
            (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            ),
        )
        QTest.mouseClick(page.machine_view_button, Qt.LeftButton)
        self.assertEqual(page.state_json()["view_mode"], "machine")
        self.assertIsNotNone(viewer.build_surface)

        self._select_tube_node(window, MODEL_CS_NODE)
        model_origin_combo, model_origin_values, _pick, _title = page.coordinate_inputs[
            "origin"
        ]
        model_origin_combo.setCurrentIndex(
            self._combo_index_for_kind(model_origin_combo, "numeric")
        )
        model_origin_values[0].setValue(2.0)
        QTest.mouseClick(page.origin_confirm_button, Qt.LeftButton)
        QTest.mouseClick(page.coordinate_apply_button, Qt.LeftButton)
        report = page.controller.validation_report()
        self.assertIs(report.state_for(PLACEMENT_NODE), NodeState.VALID)
        self.assertIn(
            "model_cs_changed",
            page.controller.operations[0].dirty_reasons,
        )

        self._select_tube_node(window, BUILD_CS_NODE)
        build_origin_combo, build_origin_values, _pick, _title = page.coordinate_inputs[
            "origin"
        ]
        build_origin_combo.setCurrentIndex(
            self._combo_index_for_kind(build_origin_combo, "numeric")
        )
        build_origin_values[0].setValue(1.0)
        QTest.mouseClick(page.origin_confirm_button, Qt.LeftButton)
        QTest.mouseClick(page.coordinate_apply_button, Qt.LeftButton)
        report = page.controller.validation_report()
        self.assertIs(report.state_for(PLACEMENT_NODE), NodeState.DIRTY)
        self.assertFalse(report.coordinates_valid)
        self.assertIn(
            "build_cs_changed",
            page.controller.operations[0].dirty_reasons,
        )

        dirty_issue = None
        for index in range(page.issue_list.count()):
            item = page.issue_list.item(index)
            payload = item.data(Qt.UserRole)
            if isinstance(payload, dict) and payload.get("code") == "PLACEMENT_DIRTY":
                dirty_issue = item
                break
        self.assertIsNotNone(dirty_issue)
        page.issue_list.setCurrentItem(dirty_issue)
        page.issue_list.setFocus()
        QTest.keyClick(page.issue_list, Qt.Key_Return)
        self.app.processEvents()
        self.assertEqual(
            page.tree.currentItem().data(0, Qt.UserRole),
            PLACEMENT_NODE,
        )
        self.assertIs(page.editor_stack.currentWidget(), page.placement_editor)
        self.assertEqual(page.state_json()["view_mode"], "machine")

    def test_placement_controls_preview_draft_and_apply_or_cancel_atomically(
        self,
    ) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page
        viewer = page.viewer
        self._configure_coordinate_setup(window, create_operation=True)
        committed_transform = page.controller.T_machine_from_source().matrix
        committed_adjustment = page.controller.setup.placement_adjustment

        self._select_tube_node(window, PLACEMENT_NODE)
        state_events = []
        page.state_changed.connect(state_events.append)
        page.placement_spins["dx"].setValue(12.5)
        self.app.processEvents()

        draft = page.controller.placement_draft()
        self.assertEqual(draft.adjustment.translation_mm, (12.5, 0.0, 0.0))
        self.assertEqual(
            page.controller.setup.placement_adjustment, committed_adjustment
        )
        expected_preview = (
            page.controller.machine_profile().mount_transform(draft.mount_datum_id)
            @ draft.T_mount_from_build
            @ page.controller.setup.build_coordinate_system.T_target_from_source
        )
        self.assertMatrixAlmostEqual(viewer.model_transform, expected_preview.matrix)
        self.assertNotEqual(viewer.model_transform, committed_transform)
        self.assertTrue(state_events)
        self.assertEqual(
            state_events[-1]["drafts"][PLACEMENT_NODE]["adjustment"]["translation_mm"],
            [12.5, 0.0, 0.0],
        )

        QTest.mouseClick(page.placement_cancel_button, Qt.LeftButton)
        with self.assertRaises(DraftNotFoundError):
            page.controller.placement_draft()
        self.assertEqual(
            page.controller.setup.placement_adjustment, committed_adjustment
        )
        self.assertMatrixAlmostEqual(viewer.model_transform, committed_transform)

        self._select_tube_node(window, MACHINE_NODE)
        self._select_tube_node(window, PLACEMENT_NODE)
        page.placement_spins["dx"].setValue(7.0)
        QTest.mouseClick(page.placement_apply_button, Qt.LeftButton)
        self.assertEqual(
            page.controller.setup.placement_adjustment.translation_mm,
            (7.0, 0.0, 0.0),
        )
        with self.assertRaises(DraftNotFoundError):
            page.controller.placement_draft()
        self.assertIn(
            "placement_changed",
            page.controller.operations[0].dirty_reasons,
        )
        self.assertMatrixAlmostEqual(
            viewer.model_transform,
            page.controller.T_machine_from_source().matrix,
        )

    def test_dirty_placement_is_not_rendered_in_machine_view(self) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page
        viewer = page.viewer
        self._configure_coordinate_setup(window)
        page.apply_placement(
            "build_plate_mount",
            translation_mm=(12.0, 0.0, 0.0),
        )
        committed_transform = page.controller.T_machine_from_source().matrix
        self.assertNotEqual(committed_transform, RigidTransform.identity().matrix)

        page.apply_numeric_coordinate(
            BUILD_CS_NODE,
            (5.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 0.0),
        )
        page.set_view_mode("machine")

        self.assertIs(
            page.controller.validation_report().state_for(PLACEMENT_NODE),
            NodeState.DIRTY,
        )
        self.assertMatrixAlmostEqual(
            viewer.model_transform,
            RigidTransform.identity().matrix,
        )
        self.assertNotEqual(viewer.model_transform, committed_transform)

    def test_pipe2_setup_reaches_ready_with_warning_and_round_trips(self) -> None:
        if self.pipe2 is None:
            self.skipTest("pipe2 STEP fixture is unavailable")
        window = self._window()
        window.open_model(self.pipe2, show_dialog=False)
        window.enter_workbench("tube")

        window.handle_automation("/tube/operation/create", {})
        part_ids = [body.body_id for body in window.model.solid_bodies]
        window.handle_automation("/tube/part/confirm", {"part_body_ids": part_ids})
        window.handle_automation(
            "/tube/resource/select",
            {"kind": "machine", "identifier": "xyzac"},
        )
        window.handle_automation(
            "/tube/resource/select",
            {"kind": "nozzle", "identifier": "0.4", "complete": True},
        )
        window.handle_automation(
            "/tube/resource/select",
            {"kind": "material", "identifier": "PLA", "review_confirmed": True},
        )
        for node in ("model_cs", "build_cs"):
            window.handle_automation(
                "/tube/coordinate/apply",
                {
                    "node": node,
                    "origin": [0, 0, 0],
                    "z_direction": [0, 0, 1],
                    "x_direction": [1, 0, 0],
                },
            )
        state = window.handle_automation(
            "/tube/placement/apply",
            {
                "mount_datum_id": "build_plate_mount",
                "translation_mm": [0, 0, 0],
                "rotation_xyz_deg": [0, 0, 0],
            },
        )["tube"]

        self.assertTrue(state["coordinates_valid"])
        self.assertTrue(state["setup_ready"])
        self.assertIn(
            "MACHINE_REFERENCE_ONLY",
            {issue["code"] for issue in state["validation"]["issues"]},
        )
        self.assertEqual(
            set(state["assignments"]["part_body_ids"]),
            set(part_ids),
        )

        before = window.tube_page.controller.setup.to_json()
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "pipe2-project"
            saved = window.save_project_to(project_dir)
            reopened = window.open_project(saved["project_json"])

        self.assertEqual(reopened["workbench"]["workbench"], "tube")
        self.assertTrue(reopened["tube"]["coordinates_valid"])
        self.assertEqual(window.tube_page.controller.setup.to_json(), before)

    def test_project_open_endpoint_replaces_or_clears_gcode_state(self) -> None:
        if self.pipe2 is None:
            self.skipTest("pipe2 STEP fixture is unavailable")
        window = self._window()
        window.open_model(self.pipe2, show_dialog=False)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean_project = window.save_project_to(root / "clean-project")
            gcode_path = root / "indexed-ac.gcode"
            gcode_path.write_text(
                "G1 X0 Y0 Z0.2\nG1 X1 Y0 Z0.2 A70.513 C15 E0.4\n",
                encoding="utf-8",
            )
            preview = load_gcode(
                gcode_path,
                controller_semantics=GENERIC_XYZAC_AC_SEMANTICS,
            )
            window.gcode_preview = preview
            window.viewer.load_gcode_preview(preview)
            gcode_project = window.save_project_to(root / "gcode-project")

            clean_state = window.handle_automation(
                "/project/open",
                {"path": clean_project["project_json"]},
            )

            self.assertEqual(
                clean_state["project"]["path"],
                clean_project["project_json"],
            )
            self.assertIsNone(window.gcode_preview)
            self.assertIsNone(window.viewer.gcode_preview)
            self.assertFalse(window.layer_min_slider.isEnabled())
            resaved = window.save_project_to(root / "clean-resaved")
            resaved_payload = json.loads(
                Path(resaved["project_json"]).read_text(encoding="utf-8")
            )
            self.assertIsNone(resaved_payload["gcode"])

            restored_state = window.handle_automation(
                "/project/open",
                {"path": gcode_project["project_json"]},
            )

            self.assertEqual(
                restored_state["project"]["path"],
                gcode_project["project_json"],
            )
            self.assertIsNotNone(window.gcode_preview)
            self.assertIs(window.viewer.gcode_preview, window.gcode_preview)
            self.assertEqual(
                window.gcode_preview.controller_semantics,
                GENERIC_XYZAC_AC_SEMANTICS,
            )
            self.assertEqual(
                window.gcode_preview.source_path.parent,
                Path(gcode_project["project_json"]).parent / "source",
            )
            self.assertTrue(window.layer_min_slider.isEnabled())
            self.assertEqual(
                window.gcode_file_label.text(),
                str(window.gcode_preview.source_path),
            )

    def test_face_and_vertex_selection_endpoints_remain_compatible(self) -> None:
        if self.pipe2 is None:
            self.skipTest("pipe2 STEP fixture is unavailable")
        window = self._window()
        window.open_model(self.pipe2, show_dialog=False)
        window.enter_workbench("tube")
        face_id = window.model.faces[0].face_id
        vertex_id = window.model.vertices[0].vertex_id

        state = window.handle_automation(
            "/selection/set",
            {"face_ids": [face_id], "vertex_ids": [vertex_id]},
        )

        self.assertEqual(state["selection"]["face_ids"], [face_id])
        self.assertEqual(state["selection"]["vertex_ids"], [vertex_id])

    def test_model_open_apis_forward_explicit_length_unit_override(self) -> None:
        if self.pipe2 is None:
            self.skipTest("pipe2 STEP fixture is unavailable")
        window = self._window()
        main_thread = threading.get_ident()
        loader_threads: list[int] = []

        def tracked_load(*args, **kwargs):
            loader_threads.append(threading.get_ident())
            return load_step(*args, **kwargs)

        with mock.patch(
            "five_axis_slicer.background_load.load_step",
            side_effect=tracked_load,
        ) as loader:
            window.open_model(
                self.pipe2,
                show_dialog=False,
                length_unit_override="inch",
            )
            window.handle_automation(
                "/model/open",
                {"path": str(self.pipe2), "length_unit_override": "cm"},
            )

        self.assertEqual(loader.call_count, 2)
        self.assertEqual(
            loader.call_args_list[0].kwargs["length_unit_override"], "inch"
        )
        self.assertEqual(loader.call_args_list[1].kwargs["length_unit_override"], "cm")
        self.assertTrue(loader_threads)
        self.assertTrue(all(item != main_thread for item in loader_threads))

    def test_repeated_sync_open_reclaims_wait_loops_and_worker_threads(
        self,
    ) -> None:
        if self.pipe2 is None:
            self.skipTest("pipe2 STEP fixture is unavailable")
        window = self._window()
        event_loop_count = len(window.findChildren(QEventLoop))
        timer_count = len(window.findChildren(QTimer))

        for _index in range(4):
            window.open_model(self.pipe2, show_dialog=False)
            self.assertFalse(window.model_loader.busy)
            self.assertIsNone(window.model_loader.active_request_id)
            self.app.processEvents()

        with tempfile.TemporaryDirectory() as tmp:
            saved = window.save_project_to(Path(tmp) / "lifecycle-project")
            for _index in range(4):
                window.open_project(saved["project_json"])
                self.assertFalse(window.project_loader.busy)
                self.assertIsNone(window.project_loader.active_request_id)
                self.app.processEvents()

        self.assertEqual(len(window.findChildren(QEventLoop)), event_loop_count)
        self.assertEqual(len(window.findChildren(QTimer)), timer_count)

    def test_sync_model_open_failure_keeps_committed_state_without_dialog(self) -> None:
        if self.pipe2 is None:
            self.skipTest("pipe2 STEP fixture is unavailable")
        window = self._loaded_tube_window()
        committed_model = window.model
        committed_setup = window.tube_page.controller.setup
        committed_viewer_model = window.viewer.model

        missing = self.pipe2.parent / "missing-background-open.step"
        with (
            mock.patch.object(window, "show_error") as show_error,
            self.assertRaises(StepLoadError),
        ):
            window.open_model(missing, show_dialog=False)

        show_error.assert_not_called()
        self.assertIs(window.model, committed_model)
        self.assertEqual(window.tube_page.controller.setup, committed_setup)
        self.assertIs(window.viewer.model, committed_viewer_model)

    def test_dialog_background_load_prompts_on_unknown_unit_and_retries(self) -> None:
        if self.pipe2 is None:
            self.skipTest("pipe2 STEP fixture is unavailable")
        model = load_step(self.pipe2)
        window = self._window()
        main_thread = threading.get_ident()
        worker_calls: list[tuple[str | None, int]] = []
        prompt_threads: list[int] = []

        def unknown_then_load(
            _path: Path,
            *,
            cancel_check,
            length_unit_override: str | None = None,
        ):
            self.assertFalse(cancel_check())
            worker_calls.append((length_unit_override, threading.get_ident()))
            if length_unit_override is None:
                raise StepLoadError(
                    "STEP length unit is missing or unsupported; "
                    "provide length_unit_override (declared=None)"
                )
            return model

        def choose_inch(_path: Path, _message: str) -> str:
            prompt_threads.append(threading.get_ident())
            return "inch"

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "unknown-unit.step"
            source.touch()
            with (
                mock.patch.object(
                    background_load,
                    "load_step",
                    side_effect=unknown_then_load,
                ),
                mock.patch.object(
                    window,
                    "_prompt_unknown_step_unit",
                    side_effect=choose_inch,
                ),
            ):
                accepted = window.start_model_load(
                    source,
                    prompt_for_unknown_unit=True,
                )
                self.assertTrue(accepted["accepted"])
                self._wait_until(
                    lambda: window.model_load_state()["status"] == "ready"
                    and not window.model_loader.busy
                )

        self.assertEqual([item[0] for item in worker_calls], [None, "inch"])
        self.assertTrue(
            all(thread_id != main_thread for _unit, thread_id in worker_calls)
        )
        self.assertEqual(prompt_threads, [main_thread])
        self.assertIs(window.model, model)
        state = window.handle_automation("/model/state", {})["model_load"]
        self.assertEqual(state["length_unit_override"], "inch")
        self.assertEqual(state["status"], "ready")

    def test_step_file_dialog_enables_unknown_unit_prompting(self) -> None:
        window = self._window()
        selected = str(Path("unknown-unit.step").resolve())
        with (
            mock.patch(
                "five_axis_slicer.ui.QFileDialog.getOpenFileName",
                return_value=(selected, "STEP Files (*.step *.stp)"),
            ),
            mock.patch.object(window, "start_model_load") as start,
        ):
            window.open_model_dialog()

        start.assert_called_once_with(selected, prompt_for_unknown_unit=True)

    def test_cancelling_unknown_unit_choice_keeps_current_model_unchanged(self) -> None:
        window = self._window()

        def unknown_unit(_path: Path, *, cancel_check) -> object:
            self.assertFalse(cancel_check())
            raise StepLoadError(
                "STEP length unit is missing or unsupported; "
                "provide length_unit_override (declared=None)"
            )

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "unknown-unit.step"
            source.touch()
            with (
                mock.patch.object(
                    background_load, "load_step", side_effect=unknown_unit
                ),
                mock.patch.object(
                    window, "_prompt_unknown_step_unit", return_value=None
                ) as prompt,
                mock.patch.object(window, "show_error") as show_error,
            ):
                window.start_model_load(source, prompt_for_unknown_unit=True)
                self._wait_until(
                    lambda: window.model_load_state()["status"] == "cancelled"
                    and not window.model_loader.busy
                )

            prompt.assert_called_once()
            show_error.assert_not_called()
        self.assertIsNone(window.model)
        self.assertEqual(
            window.model_load_state()["message"],
            "STEP unit selection cancelled",
        )


if __name__ == "__main__":
    unittest.main()
