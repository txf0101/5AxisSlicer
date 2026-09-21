from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtCore import QEventLoop, QSettings, Qt, QTimer
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget

from five_axis_slicer import background_load, model_commit
from five_axis_slicer.command_kernel import CommandError
from five_axis_slicer.gcode_preview import PreviewSettings, load_gcode
from five_axis_slicer.manufacturing.coordinates import RigidTransform
from five_axis_slicer.manufacturing.preview_kinematics import (
    GENERIC_XYZAC_AC_SEMANTICS,
)
from five_axis_slicer.manufacturing.setup import (
    BUILD_CS_NODE,
    MACHINE_NODE,
    MODEL_CS_NODE,
    PART_NODE,
    PLACEMENT_NODE,
    ManufacturingSetup,
    NodeState,
)
from five_axis_slicer.models import PickHit, SelectionState
from five_axis_slicer.project_io import ProjectFormatError, ProjectLoaded
from five_axis_slicer.result_state import LoadResult
from five_axis_slicer.step_loader import StepLoadError, load_step
from five_axis_slicer.tube_controller import DraftNotFoundError, TubeSetupController
from five_axis_slicer.ui import MainWindow


def complete_nozzle_options() -> dict[str, object]:
    """Measured fixture data supplied explicitly to the automation boundary."""

    return {
        "complete": True,
        "interface": "M6",
        "length_mm": 12.5,
        "construction_material": "brass",
        "flow_category": "standard",
        "temperature_limit_c": 300.0,
        "wear_resistance_rating": "standard",
        "outer_profile_rz_mm": ((0.2, 0.0), (3.0, 2.0), (3.0, 12.5)),
    }


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

    def test_http_tube_mutation_reports_shared_revision_conflicts(self) -> None:
        window = self._window()

        created = window.handle_automation(
            "/tube/operation/create",
            {"command_id": "http-1", "expected_revision": 0},
        )

        self.assertEqual(created["command"]["revision"], 1)
        self.assertEqual(created["command"]["command_id"], "http-1")
        self.assertEqual(created["command"]["changed_fields"], ["operations"])
        self.assertEqual(created["command"]["affected_nodes"], ["operation"])
        self.assertEqual(window.tube_script_service.kernel.revision, 1)
        with self.assertRaises(CommandError) as raised:
            window.handle_automation(
                "/tube/part/confirm",
                {"command_id": "http-stale", "expected_revision": 0},
            )
        self.assertEqual(raised.exception.code, "E_REVISION_CONFLICT")
        self.assertEqual(raised.exception.command_id, "http-stale")

    def test_command_adapters_publish_one_full_refresh(self) -> None:
        window = self._window()
        page = window.tube_page
        refresh = mock.Mock(wraps=page.refresh)
        page.refresh = refresh

        page._create_operation()
        self.assertEqual(refresh.call_count, 1)
        refresh.reset_mock()

        page.machine_combo.setCurrentIndex(1)  # Select a different machine from the default.
        page._apply_machine()
        self.assertEqual(refresh.call_count, 1)
        self.assertIsNotNone(page.controller.setup.machine)
        self.assertGreater(page.mount_combo.count(), 0)
        refresh.reset_mock()

        for node in (MODEL_CS_NODE, BUILD_CS_NODE):
            page.apply_numeric_coordinate(node, (0, 0, 0), (0, 0, 1), (1, 0, 0))
            self.assertEqual(refresh.call_count, 1)
            refresh.reset_mock()
        self.assertIsNotNone(page.controller.setup.build_coordinate_system)

        page.apply_placement("build_plate_mount")
        self.assertEqual(refresh.call_count, 1)
        self.assertEqual(page._view_mode, "machine")
        self.assertFalse(page.machine_view_button.isEnabled())
        self.assertIsNotNone(page.controller.setup.T_mount_from_build)
        self.assertIsNotNone(page.viewer.model_transform)

    def test_operation_editor_applies_roles_parameters_and_highlights_geometry(self) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page
        page._create_operation()
        operations_item = page.tree.topLevelItem(0).child(2)
        operation_item = operations_item.child(0)
        page.tree.setCurrentItem(operation_item)
        self.app.processEvents()

        role_ids = {
            "tube_body_id": "body_002",
            "entry_port_id": "body_002_edge_0003",
            "exit_port_id": "body_002_edge_0014",
            "substrate_body_id": "body_001",
        }
        for key, object_id in role_ids.items():
            combo = page._operation_geometry_combos[key]
            index = combo.findData(object_id)
            self.assertGreaterEqual(index, 0, f"missing operation choice: {object_id}")
            combo.setCurrentIndex(index)
        page._operation_parameter_spins["layer_height_mm"].setValue(0.25)

        self.assertEqual(page.viewer.selection.body_ids, {"body_001", "body_002"})
        self.assertEqual(
            page.viewer.selection.edge_ids,
            {"body_002_edge_0003", "body_002_edge_0014"},
        )
        QTest.mouseClick(page.operation_apply_button, Qt.LeftButton)
        self.app.processEvents()

        operation = page.controller.operations[0]
        self.assertTrue(operation.geometry.is_complete)
        self.assertEqual(operation.parameters.layer_height_mm, 0.25)
        self.assertIn("operation_geometry_changed", operation.dirty_reasons)
        self.assertIn("operation_parameters_changed", operation.dirty_reasons)
        window.set_language("en")
        self.assertEqual(
            page.operation_feedback.text(),
            "Operation geometry roles and process parameters applied.",
        )

    def test_selected_pipe_edges_bind_explicit_roles_before_generation(self) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page
        QTest.mouseClick(page.create_operation_button, Qt.LeftButton)
        self.app.processEvents()
        operation = page.controller.operations[0]
        page.tree.setCurrentItem(page._tree_items[f"operation:{operation.operation_id}"])
        self.app.processEvents()
        edges = ["body_002_edge_0003", "body_002_edge_0014"]
        window.handle_automation("/selection/set", {"edge_ids": edges})
        self.assertEqual(page.viewer.selection.edge_ids, set(edges))
        # Selection highlighting alone must not guess which edge is the inlet.
        roles = dict(
            tube_body_id="body_002",
            entry_port_id=edges[0],
            exit_port_id=edges[1],
            substrate_body_id="body_001",
        )
        for key, identifier in roles.items():
            combo = page._operation_geometry_combos[key]
            self.assertGreaterEqual(combo.findData(identifier), 0)
            combo.setCurrentIndex(combo.findData(identifier))
        QTest.mouseClick(page.operation_apply_button, Qt.LeftButton)
        self.app.processEvents()
        operation = page.controller.operations[0]
        self.assertEqual(operation.geometry.entry_port.object_id, edges[0])
        self.assertEqual(operation.geometry.exit_port.object_id, edges[1])
        restored = TubeSetupController.from_json(page.controller.to_json(), cad_model=window.model)
        self.assertEqual(restored.operations[0].geometry, operation.geometry)
        # Incomplete machine/nozzle setup must still prevent export from this UI flow.
        QTest.mouseClick(page.operation_generate_button, Qt.LeftButton)
        self.app.processEvents()
        self.assertFalse(page.operation_export_button.isEnabled())
        self.assertTrue(page.operation_generation_status.text())

    def test_operation_failure_displays_actionable_product_error(self) -> None:
        from five_axis_slicer import tube_operation_ui
        from five_axis_slicer.postprocessing.tube_product import TubeProductState

        page = self._loaded_tube_window().tube_page
        page._create_operation()
        operation = page.controller.operations[0]
        error = "tube.port_not_outer_boundary: ports must use outer circular edges"
        state = TubeProductState(operation.operation_id, "0" * 64, "error", {"error": error})
        with mock.patch.object(page.controller, "product_state", return_value=state):
            tube_operation_ui._refresh_product_status(page)
        self.assertIn(error, page.operation_generation_status.text())
        self.assertFalse(page.operation_export_button.isEnabled())
        state = TubeProductState(
            operation.operation_id,
            "0" * 64,
            "error",
            {
                "validation": {
                    "collision_check_complete": False,
                    "issues": [
                        {
                            "code": "tube.nozzle_ipw_collision",
                            "severity": "error",
                            "object_id": "p3",
                        }
                    ],
                }
            },
        )
        with mock.patch.object(page.controller, "product_state", return_value=state):
            tube_operation_ui._refresh_product_status(page)
        self.assertIn("tube.nozzle_ipw_collision", page.operation_generation_status.text())
        self.assertIn("collision_check_complete=False", page.operation_generation_status.text())
        self.assertFalse(page.operation_export_button.isEnabled())

    def test_operation_viewer_picks_bind_draft_and_reject_invalid_hits(self) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page
        page._create_operation()
        operation = page.controller.operations[0]
        page.tree.setCurrentItem(page._tree_items[f"operation:{operation.operation_id}"])
        self.app.processEvents()
        roles = {
            "tube_body_id": "body_002",
            "entry_port_id": "body_002_edge_0003",
            "exit_port_id": "body_002_edge_0014",
            "substrate_body_id": "body_001",
        }
        for field, entity in roles.items():
            QTest.mouseClick(page._operation_pick_buttons[field], Qt.LeftButton)
            kind = "body" if field.endswith("body_id") else "edge"
            self.assertEqual(page.viewer.pick_request.kind, kind)
            self.assertIn(entity, page.viewer.pick_request.allowed_ids)
            combo = page._operation_geometry_combos[field]
            before = combo.currentData()
            page.viewer.pick_callback(PickHit("vertex", entity))
            page.viewer.pick_callback(PickHit(kind, "missing-object"))
            self.assertEqual(combo.currentData(), before)
            page.viewer.pick_callback(PickHit(kind, entity))
            self.assertEqual(combo.currentData(), entity)
            self.assertIsNone(page._operation_pick_field)
        self.assertFalse(page.controller.operations[0].geometry.is_complete)
        QTest.mouseClick(page.operation_apply_button, Qt.LeftButton)
        self.assertTrue(page.controller.operations[0].geometry.is_complete)
        QTest.mouseClick(page._operation_pick_buttons["entry_port_id"], Qt.LeftButton)
        page.tree.setCurrentItem(page._tree_items[PART_NODE])
        self.assertIsNone(page._operation_pick_field)

    def test_operation_editor_keeps_apply_visible_at_laptop_size(self) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page
        page._create_operation()
        operation_item = page.tree.topLevelItem(0).child(2).child(0)
        page.tree.setCurrentItem(operation_item)
        window.resize(1366, 768)
        self.app.processEvents()

        self.assertEqual((window.width(), window.height()), (1366, 768))
        self.assertTrue(window.script_console_manager.dock.compact)
        self.assertGreaterEqual(window.script_console_manager.dock.width(), window.minimumWidth())
        self.assertTrue(page.operation_apply_button.isVisibleTo(window))
        self.assertTrue(page.operation_apply_button.isEnabled())
        self.assertGreater(page.editor_scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(
            page.tree.topLevelItem(0).child(2).text(0),
            "操作  [待更新]",
        )

        button_top_left = page.operation_apply_button.mapTo(
            window, page.operation_apply_button.rect().topLeft()
        )
        issue_top_left = page.issue_list.mapTo(window, page.issue_list.rect().topLeft())
        self.assertLess(
            button_top_left.y() + page.operation_apply_button.height(),
            issue_top_left.y(),
        )
        actions = (
            page.back_button,
            page.open_button,
            page.update_source_button,
            page.save_button,
            page.create_operation_button,
        )
        action_rects = [
            button.rect().translated(button.mapTo(window, button.rect().topLeft()))
            for button in actions
        ]
        for index, first in enumerate(action_rects):
            for second in action_rects[index + 1 :]:
                self.assertFalse(
                    first.intersects(second),
                    f"overlapping actions: {actions[index].text()} {first} / "
                    f"{actions[action_rects.index(second)].text()} {second}",
                )

    def test_http_operation_set_uses_shared_revision_and_round_trips(self) -> None:
        window = self._loaded_tube_window()
        service = window.tube_script_service
        created = window.handle_automation(
            "/tube/operation/create",
            {"expected_revision": service.kernel.revision},
        )
        updated = window.handle_automation(
            "/tube/operation/set",
            {
                "expected_revision": created["command"]["revision"],
                "tube_body_id": "body_002",
                "entry_port_id": "body_002_edge_0003",
                "exit_port_id": "body_002_edge_0014",
                "substrate_body_id": "body_001",
                "layer_height_mm": 0.3,
            },
        )

        operation = updated["command"]["payload"]
        self.assertEqual(operation["geometry"]["tube_body"]["object_id"], "body_002")
        self.assertEqual(operation["parameters"]["layer_height_mm"], 0.3)
        restored = TubeSetupController.from_json(
            page_json := window.tube_page.controller.to_json(),
            cad_model=window.model,
        )
        self.assertEqual(restored.operations[0].to_json(), operation)
        self.assertEqual(
            len(page_json["body_catalog"]), len(window.tube_page.controller.body_candidates)
        )

    def test_script_console_default_height_keeps_viewer_usable(self) -> None:
        window = self._loaded_tube_window()
        for _ in range(4):
            self.app.processEvents()

        self.assertGreaterEqual(window.script_console.height(), 170)
        self.assertLessEqual(window.script_console.height(), 230)
        self.assertGreaterEqual(window.tube_page.viewer.height(), 420)

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
        for left_row, right_row in zip(left, right, strict=False):
            self.assertEqual(len(left_row), len(right_row))
            for left_value, right_value in zip(left_row, right_row, strict=False):
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
            "制造设置 1",
            window.tube_page.tree.topLevelItem(0).child(1).text(0),
        )
        self.assertEqual(window.tube_page.title_label.text(), "管状工作台")
        self.assertEqual(window.tube_page.coordinate_apply_button.text(), "应用")
        self.assertEqual(window.tube_page.coordinate_cancel_button.text(), "取消")
        self.assertLessEqual(window.tube_page.minimumSizeHint().width(), 1600)

        window.set_language("en")
        self.assertEqual(window.tube_page.open_button.text(), "Open STEP")
        self.assertEqual(window.tube_page.issue_title.text(), "Issues")
        self.assertEqual(window.tube_page.coordinate_apply_button.text(), "Apply")

    def test_workbench_cards_and_part_roles_follow_language(self) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page

        self.assertIn("平面工作台", window.workbench_buttons["planar"].text())
        self.assertIn("[离线可用]", window.workbench_buttons["planar"].text())
        self.assertIn("回转工作台", window.workbench_buttons["rotary"].text())
        self.assertIn("[可用]", window.workbench_buttons["rotary"].text())
        self.assertIn("研究工作台", window.workbench_buttons["research"].text())
        self.assertIn("[研发]", window.workbench_buttons["research"].text())

        combo = next(iter(page._role_combos.values()))
        self.assertEqual(
            [combo.itemText(i) for i in range(combo.count())], ["零件", "忽略", "未分配"]
        )
        self.assertEqual(
            [combo.itemData(i) for i in range(combo.count())],
            ["part", "ignore", "unassigned"],
        )
        combo.setCurrentIndex(combo.findData("ignore"))

        window.set_language("en")
        self.assertIn("[Ready]", window.workbench_buttons["rotary"].text())
        combo = next(iter(page._role_combos.values()))
        self.assertEqual(
            [combo.itemText(i) for i in range(combo.count())], ["Part", "Ignore", "Unassigned"]
        )
        self.assertEqual(
            [combo.itemData(i) for i in range(combo.count())],
            ["part", "ignore", "unassigned"],
        )
        self.assertEqual(combo.currentData(), "ignore")

    def test_loaded_step_offers_coordinate_entry_without_reimport(self) -> None:
        if self.pipe2 is None:
            self.skipTest("pipe2 STEP fixture is unavailable")
        window = self._window()
        window.open_model(self.pipe2, show_dialog=False)
        model = window.model
        controller = window.tube_page.controller
        window.resize(1600, 900)
        window.show()
        self.app.processEvents()

        self.assertIs(window.stack.currentWidget(), window.session_page)
        self.assertTrue(window.tube_coordinate_button.isVisible())
        self.assertEqual(
            window.tube_coordinate_button.text(),
            "进入管状设置（定义坐标）",
        )

        QTest.mouseClick(window.tube_coordinate_button, Qt.LeftButton)
        self.app.processEvents()

        self.assertIs(window.stack.currentWidget(), window.tube_page)
        self.assertIs(window.model, model)
        self.assertIs(window.tube_page.viewer.model, model)
        self.assertIs(window.tube_page.controller, controller)
        self.assertEqual(window.current_workbench_key, "tube")
        self.assertEqual(
            window.tube_page.tree.currentItem().data(0, Qt.UserRole),
            PART_NODE,
        )

        window.tube_page.tree.setCurrentItem(window.tube_page._tree_items["model"])
        window.enter_workbench("curve")
        window.enter_workbench("tube")
        self.assertEqual(
            window.tube_page.tree.currentItem().data(0, Qt.UserRole),
            PART_NODE,
        )
        self.assertIs(window.tube_page.editor_stack.currentWidget(), window.tube_page.part_editor)

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

        origin_combo, _origin_values, origin_pick, _origin_title = page.coordinate_inputs["origin"]
        origin_combo.setCurrentIndex(self._combo_index_for_kind(origin_combo, "pick_face"))
        QTest.mouseClick(origin_pick, Qt.LeftButton)
        self.assertEqual(viewer.pick_request.kind, "face")
        face = window.model.faces[0]
        viewer.pick_callback(PickHit("face", face.face_id, face.centroid))
        self.app.processEvents()
        face_reference = page.controller.coordinate_draft(MODEL_CS_NODE).origin_reference
        self.assertEqual(face_reference.reference_type, "face_pick")
        self.assertEqual(face_reference.geometry.object_id, face.face_id)

        origin_combo.setCurrentIndex(self._combo_index_for_kind(origin_combo, "pick_vertex"))
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
        z_combo.setCurrentIndex(self._combo_index_for_kind(z_combo, "pick_two_vertices"))
        QTest.mouseClick(z_pick, Qt.LeftButton)
        self.assertEqual(viewer.pick_request.kind, "vertex")
        self.assertTrue(viewer.pick_request.multiple)
        viewer.pick_callback(PickHit("vertex", first_vertex.vertex_id))
        self.assertIn("second vertex", page.coordinate_feedback.text().lower())
        viewer.pick_callback(PickHit("vertex", second_vertex.vertex_id))
        QTest.mouseClick(page.z_confirm_button, Qt.LeftButton)

        raw_z = tuple(
            right - left
            for left, right in zip(first_vertex.point, second_vertex.point, strict=False)
        )
        z_length = math.sqrt(sum(value * value for value in raw_z))
        unit_z = tuple(value / z_length for value in raw_z)
        basis_vectors = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        x_direction = min(
            basis_vectors,
            key=lambda vector: abs(sum(a * b for a, b in zip(vector, unit_z, strict=False))),
        )
        x_combo, x_values, _x_pick, _x_title = page.coordinate_inputs["x"]
        x_combo.setCurrentIndex(self._combo_index_for_kind(x_combo, "numeric"))
        for spin, value in zip(x_values, x_direction, strict=False):
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
        self.assertEqual(frame.origin_reference.geometry.object_id, origin_vertex.vertex_id)
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
            page.controller.coordinate_draft(MODEL_CS_NODE).z_direction_reference.flipped
        )
        QTest.mouseClick(page.coordinate_cancel_button, Qt.LeftButton)
        self.assertEqual(
            page.controller.setup.model_coordinate_system.to_json(),
            applied_payload,
        )
        self.assertFalse(page.controller.has_drafts)

    def test_build_numeric_editor_round_trips_through_model_coordinates(self) -> None:
        window = self._loaded_tube_window()
        page = window.tube_page
        page.apply_numeric_coordinate(
            MODEL_CS_NODE,
            (10.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 0.0),
        )
        page.apply_numeric_coordinate(
            BUILD_CS_NODE,
            (5.0, 0.0, 0.0),
            (0.0, 0.0, 1.0),
            (1.0, 0.0, 0.0),
        )

        build = page.controller.setup.build_coordinate_system
        assert build is not None
        self.assertEqual(build.origin_reference.resolved_point, (15.0, 0.0, 0.0))

        self._select_tube_node(window, BUILD_CS_NODE)
        _combo, origin_values, _pick, _title = page.coordinate_inputs["origin"]
        self.assertAlmostEqual(origin_values[0].value(), 5.0)
        origin_values[0].setValue(6.0)
        QTest.mouseClick(page.origin_confirm_button, Qt.LeftButton)
        QTest.mouseClick(page.coordinate_apply_button, Qt.LeftButton)

        build = page.controller.setup.build_coordinate_system
        assert build is not None
        self.assertEqual(build.origin_reference.resolved_point, (16.0, 0.0, 0.0))
        with tempfile.TemporaryDirectory() as tmp:
            saved = window.save_project_to(Path(tmp) / "build-coordinate-project")
            window.open_project(saved["project_json"])
        reopened = window.tube_page.controller.setup.build_coordinate_system
        assert reopened is not None
        self.assertEqual(reopened.origin_reference.resolved_point, (16.0, 0.0, 0.0))

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
        model_origin_combo, model_origin_values, _pick, _title = page.coordinate_inputs["origin"]
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
        build_origin_combo, build_origin_values, _pick, _title = page.coordinate_inputs["origin"]
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
        self.assertEqual(page.controller.setup.placement_adjustment, committed_adjustment)
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
        self.assertEqual(page.controller.setup.placement_adjustment, committed_adjustment)
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
            {
                "kind": "nozzle",
                "identifier": "0.4",
                **complete_nozzle_options(),
            },
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
            self.assertTrue((project_dir / "manufacturing-setup.yaml").is_file())
            self.assertIsNone(saved["config_warning"])
            reopened = window.open_project(saved["project_json"])

        self.assertEqual(reopened["workbench"]["workbench"], "tube")
        self.assertTrue(reopened["tube"]["coordinates_valid"])
        self.assertEqual(window.tube_page.controller.setup.to_json(), before)

    def test_pipe2_script_transaction_reaches_ready_and_reopens_with_yaml(self) -> None:
        if self.pipe2 is None:
            self.skipTest("pipe2 STEP fixture is unavailable")
        window = self._window()
        window.open_model(self.pipe2, show_dialog=False)
        window.enter_workbench("tube")
        controller = window.tube_page.controller
        machine = next(
            profile
            for profile in controller.available_resource_profiles("machine")
            if "generic_xyzac" in profile.profile_id
        )
        nozzle = next(
            profile
            for profile in controller.available_resource_profiles("nozzle")
            if math.isclose(profile.orifice_diameter_mm, 0.4)
        )
        material = next(
            profile
            for profile in controller.available_resource_profiles("material")
            if profile.material == "PLA"
        )
        revision_before = window.tube_script_service.kernel.revision
        script = f"""
with tube.transaction():
    tube.create_operation()
    tube.confirm_part()
    tube.set_machine({json.dumps(machine.profile_id)})
    tube.set_nozzle(
        {json.dumps(nozzle.resource_id)},
        interface="M6×1",
        length_mm=12.5,
        use_collision_envelope=True,
    )
    tube.set_material({json.dumps(material.resource_id)}, review_confirmed=True)
    tube.set_model_cs()
    tube.set_build_cs()
    tube.set_placement("build_plate_mount")
"""

        output = window.tube_script_service.execute_script(script)

        self.assertNotIn("[E_", output)
        self.assertEqual(window.tube_script_service.kernel.revision, revision_before + 1)
        self.assertTrue(controller.coordinates_valid)
        self.assertTrue(controller.setup_ready)
        self.assertEqual(
            set(controller.setup.assignments.part_body_ids),
            {body.body_id for body in window.model.solid_bodies},
        )

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "pipe2-script-project"
            saved = window.save_project_to(project)
            yaml_before = (project / "manufacturing-setup.yaml").read_bytes()
            reopened = window.open_project(saved["project_json"])

        self.assertTrue(reopened["tube"]["coordinates_valid"])
        self.assertTrue(reopened["tube"]["setup_ready"])
        self.assertEqual(
            window.tube_script_service.config.state_json()["status"],
            "synced",
        )
        self.assertGreater(len(yaml_before), 0)

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
            resaved_payload = json.loads(Path(resaved["project_json"]).read_text(encoding="utf-8"))
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

    def test_failed_project_publication_restores_committed_session(self) -> None:
        window = self._loaded_tube_window()
        original_model = window.model
        original_controller = window.tube_page.controller
        body_id = original_model.bodies[0].body_id
        window.viewer.set_selection(body_ids=[body_id])
        window.tube_page.viewer.set_selection(body_ids=[body_id])
        window.tube_page._coordinate_node = BUILD_CS_NODE
        window.tube_page._pick_context = (BUILD_CS_NODE, "origin", "vertex")
        window.tube_page._two_point_hits[:] = [PickHit("vertex", "retained-hit")]
        window.tube_page._coordinate_control_dirty = {"origin"}
        window.tube_page.set_view_mode("machine")
        original_page_state = model_commit._capture_tube_page(window.tube_page)
        original_project_dir = Path("committed-project").resolve()
        window.last_project_dir = original_project_dir
        original_stack_index = window.stack.currentIndex()
        original_tab_index = window.preview_tabs.currentIndex()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gcode_path = root / "candidate.gcode"
            gcode_path.write_text("G1 X0 Y0 Z0.2\nG1 X1 Y0 Z0.2 E0.4\n", encoding="utf-8")
            candidate_preview = load_gcode(gcode_path)
            candidate_model = load_step(self.pipe2)
            loaded = ProjectLoaded(
                project_directory=root / "candidate-project",
                project_json=root / "candidate-project" / "project.json",
                model=candidate_model,
                selection=SelectionState(body_ids={candidate_model.bodies[-1].body_id}),
                workbench={"workbench": "curve", "operation": "curve_buildup"},
                setups=(ManufacturingSetup(),),
                operations=(),
                resources={},
                migrated_from_v1=False,
                payload={},
                gcode_preview=candidate_preview,
            )
            show_session = window._show_session
            failed = False
            candidate_was_visible = False

            def fail_candidate_once() -> None:
                nonlocal candidate_was_visible, failed
                show_session()
                if window.model is candidate_model and not failed:
                    candidate_was_visible = (
                        window.gcode_preview is candidate_preview
                        and window.tube_page.controller is not original_controller
                        and window.current_workbench_key == "curve"
                        and window.tube_page._pick_context is None
                    )
                    failed = True
                    raise RuntimeError("project viewer publication failed")

            with (
                mock.patch.object(
                    window,
                    "_show_session",
                    side_effect=fail_candidate_once,
                ),
                self.assertRaisesRegex(RuntimeError, "project viewer publication failed"),
            ):
                window._commit_loaded_project(loaded)

        self.assertTrue(candidate_was_visible)
        self.assertIs(window.model, original_model)
        self.assertIs(window.viewer.model, original_model)
        self.assertIs(window.tube_page.viewer.model, original_model)
        self.assertIs(window.tube_page.controller, original_controller)
        self.assertIs(original_controller._cad_model, original_model)
        self.assertIsNone(window.gcode_preview)
        self.assertIsNone(window.viewer.gcode_preview)
        self.assertEqual(window.viewer.selection.body_ids, {body_id})
        self.assertEqual(window.tube_page.viewer.selection.body_ids, {body_id})
        self.assertEqual(window.current_workbench_key, "tube")
        self.assertEqual(window.last_project_dir, original_project_dir)
        self.assertEqual(window.stack.currentIndex(), original_stack_index)
        self.assertEqual(window.preview_tabs.currentIndex(), original_tab_index)
        self.assertEqual(model_commit._capture_tube_page(window.tube_page), original_page_state)

    def test_combined_model_and_gcode_failure_rolls_back_both_stages(self) -> None:
        window = self._loaded_tube_window()
        original_model = window.model
        original_controller = window.tube_page.controller

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_gcode = root / "old.gcode"
            old_gcode.write_text(
                "G1 X0 Y0 Z0.2\nG1 X1 Y0 Z0.2 E0.4\nG1 Z0.4\nG1 X2 Y0 E0.8\n",
                encoding="utf-8",
            )
            new_gcode = root / "new.gcode"
            new_gcode.write_text("G1 X0 Y0 Z1\nG1 X3 Y0 Z1 E1\n", encoding="utf-8")
            original_preview = load_gcode(old_gcode)
            candidate_preview = load_gcode(new_gcode)
            candidate_model = load_step(self.pipe2)
            window._commit_gcode_preview(original_preview)
            retained_layer = original_preview.layer_max
            window.viewer.preview_settings.layer_min = retained_layer
            window.viewer.preview_settings.layer_max = retained_layer
            window._sync_preview_controls()
            window.preview_tabs.setCurrentIndex(1)

            load_preview = window.viewer.load_gcode_preview
            failed = False

            def fail_candidate_once(preview) -> None:
                nonlocal failed
                load_preview(preview)
                if preview is candidate_preview and not failed:
                    failed = True
                    window.viewer.preview_settings.layer_min = preview.layer_min
                    window.viewer.preview_settings.layer_max = preview.layer_max
                    raise RuntimeError("G-code publication failed")

            request_id = "gcode-combined-rollback"
            window._gcode_load_outcomes[request_id] = {"status": "loading"}
            window._gcode_load_show_errors[request_id] = False
            result = LoadResult(
                request_id=request_id,
                model=candidate_model,
                gcode_preview=candidate_preview,
            )
            with (
                mock.patch.object(
                    window.viewer,
                    "load_gcode_preview",
                    side_effect=fail_candidate_once,
                ),
                mock.patch.object(
                    model_commit,
                    "_capture",
                    wraps=model_commit._capture,
                ) as capture,
            ):
                window._on_gcode_load_completed(result)

        self.assertEqual(window._gcode_load_outcomes[request_id]["status"], "error")
        self.assertIs(window.model, original_model)
        self.assertIs(window.viewer.model, original_model)
        self.assertIs(window.tube_page.viewer.model, original_model)
        self.assertIs(window.tube_page.controller, original_controller)
        self.assertIs(original_controller._cad_model, original_model)
        self.assertIs(window.gcode_preview, original_preview)
        self.assertIs(window.viewer.gcode_preview, original_preview)
        self.assertEqual(window.viewer.preview_settings.layer_min, retained_layer)
        self.assertEqual(window.viewer.preview_settings.layer_max, retained_layer)
        self.assertEqual(window.layer_min_slider.value(), retained_layer)
        self.assertEqual(window.layer_max_slider.value(), retained_layer)
        self.assertEqual(window.preview_tabs.currentIndex(), 1)
        self.assertEqual(capture.call_count, 1)

    def test_failed_save_restores_applied_and_discarded_drafts(self) -> None:
        window = self._loaded_tube_window()
        controller = window.tube_page.controller
        controller.create_operation(operation_id="tube-save-rollback")
        controller.mark_saved()

        for resolution in ("apply", "discard"):
            with self.subTest(resolution=resolution):
                controller.begin_coordinate_draft(MODEL_CS_NODE)
                controller.set_numeric_origin(MODEL_CS_NODE, (2, 3, 4), confirmed=True)
                controller.set_numeric_direction(MODEL_CS_NODE, "z", (0, 0, 1), confirmed=True)
                controller.set_numeric_direction(MODEL_CS_NODE, "x", (1, 0, 0), confirmed=True)
                before = controller.state_json()

                with (
                    mock.patch(
                        "five_axis_slicer.ui.save_project",
                        side_effect=OSError("publication failed"),
                    ),
                    self.assertRaisesRegex(OSError, "publication failed"),
                ):
                    window.save_project_to(
                        Path("unused-project-directory"),
                        draft_resolution=resolution,
                    )

                self.assertEqual(controller.state_json(), before)
                controller.discard_all_drafts()

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
        self.assertEqual(loader.call_args_list[0].kwargs["length_unit_override"], "inch")
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
        self.assertTrue(all(thread_id != main_thread for _unit, thread_id in worker_calls))
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
                mock.patch.object(background_load, "load_step", side_effect=unknown_unit),
                mock.patch.object(window, "_prompt_unknown_step_unit", return_value=None) as prompt,
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
