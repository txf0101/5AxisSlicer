from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtWidgets import QApplication, QWidget  # noqa: E402

from five_axis_slicer.command_kernel import CommandKernel  # noqa: E402
from five_axis_slicer.manufacturing.library import (  # noqa: E402
    ResourceLibraryError,
    UserResourceLibrary,
)
from five_axis_slicer.manufacturing.machine import (  # noqa: E402
    CARTESIAN_REFERENCE,
)
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    NozzleProfile,
    ResourceSnapshot,
    get_builtin_material_profile,
    get_builtin_nozzle_profile,
)
from five_axis_slicer.manufacturing.setup import NodeState  # noqa: E402
from five_axis_slicer.tube_controller import TubeSetupController  # noqa: E402
from five_axis_slicer.tube_commands import TubeCommandProvider  # noqa: E402
from five_axis_slicer.tube_drafts import BodyCandidate  # noqa: E402
from five_axis_slicer.tube_ui import TubeSetupPage  # noqa: E402


def complete_nozzle(resource_id: str = "shop-nozzle-04") -> NozzleProfile:
    return NozzleProfile(
        resource_id=resource_id,
        display_name="Shop brass 0.4 mm",
        orifice_diameter_mm=0.4,
        filament_diameter_mm=1.75,
        interface="M6",
        length_mm=12.5,
        construction_material="brass",
        flow_category="standard",
        temperature_limit_c=300.0,
        wear_resistance_rating="standard",
        outer_profile_rz_mm=((0.2, 0.0), (3.0, 2.0), (3.0, 12.5)),
    )


class ViewerStub(QWidget):
    def set_pick_callback(self, callback) -> None:
        self.pick_callback = callback

    def set_coordinate_frames(self, *_args, **_kwargs) -> None:
        return

    def set_build_surface(self, *_args, **_kwargs) -> None:
        return

    def set_model_transform(self, *_args, **_kwargs) -> None:
        return


class ResourceLibraryControllerTests(unittest.TestCase):
    def test_catalog_combines_builtins_and_user_profiles_without_shadowing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(tmp)
            nozzle = complete_nozzle()
            machine = replace(
                CARTESIAN_REFERENCE,
                profile_id="shop-cartesian",
                name="Shop Cartesian",
            )
            material = get_builtin_material_profile("PLA").reviewed_copy("shop-pla")
            library.save(nozzle)
            library.save(machine)
            library.save(material)

            nozzle_catalog = library.available_profiles("nozzle")
            machine_catalog = library.available_profiles("machine")

            self.assertIn(nozzle, nozzle_catalog)
            self.assertIn(machine, machine_catalog)
            self.assertIn(material, library.available_profiles("material"))
            builtin = get_builtin_nozzle_profile(0.4)
            self.assertIn(builtin, nozzle_catalog)
            self.assertIs(library.resolve("nozzle", builtin.resource_id), builtin)
            self.assertEqual(
                library.audit_snapshot(ResourceSnapshot.capture("nozzle", builtin)).status,
                "match",
            )

            spoofed_builtin = replace(builtin, is_builtin=False)
            with self.assertRaisesRegex(ResourceLibraryError, "immutable"):
                library.save(spoofed_builtin)

    def test_diverged_and_missing_library_entries_warn_and_retain_snapshot(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(Path(tmp) / "library")
            nozzle = complete_nozzle()
            library.save(nozzle)
            controller = TubeSetupController(resource_library=library)
            frozen = controller.select_nozzle(nozzle)

            library.save(replace(nozzle, display_name="Recalibrated nozzle"))
            controller.refresh_resource_library()
            report = controller.validation_report()

            self.assertEqual(controller.setup.nozzle, frozen)
            self.assertIs(report.state_for("nozzle"), NodeState.VALID)
            self.assertIn(
                "RESOURCE_LIBRARY_DIVERGED",
                {issue.code for issue in report.issues},
            )
            self.assertEqual(controller.resource_audits[0].status, "diverged")

            empty_library = UserResourceLibrary(Path(tmp) / "empty")
            controller.set_resource_library(empty_library)
            missing_report = controller.validation_report()
            self.assertEqual(controller.setup.nozzle, frozen)
            self.assertIn(
                "RESOURCE_LIBRARY_ENTRY_MISSING",
                {issue.code for issue in missing_report.issues},
            )

            restored = TubeSetupController.from_json(
                controller.to_json(),
                resource_library=empty_library,
            )
            self.assertEqual(restored.setup.nozzle, frozen)
            self.assertEqual(restored.resource_audits[0].status, "missing")

    def test_deeply_corrupt_matching_entry_is_isolated_during_snapshot_audit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(Path(tmp) / "library")
            machine = replace(
                CARTESIAN_REFERENCE,
                profile_id="shop-corrupt-machine",
                name="Shop corrupt machine",
            )
            path = library.save(machine)
            controller = TubeSetupController()
            frozen = controller.select_machine(machine)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["profile"]["joints"] = {"unexpected": "mapping"}
            path.write_text(json.dumps(envelope), encoding="utf-8")

            controller.set_resource_library(library)
            report = controller.validation_report()

            self.assertEqual(controller.setup.machine, frozen)
            self.assertIn(
                "RESOURCE_LIBRARY_ENTRY_INVALID",
                {issue.code for issue in report.issues},
            )
            self.assertIn(
                "RESOURCE_LIBRARY_AUDIT_FAILED",
                {issue.code for issue in report.issues},
            )


class ResourceLibraryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_page_lists_user_resources_and_keeps_editor_copies_in_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(tmp)
            user_nozzle = complete_nozzle()
            user_machine = replace(
                CARTESIAN_REFERENCE,
                profile_id="shop-cartesian",
                name="Shop Cartesian",
            )
            user_material = get_builtin_material_profile("PETG").reviewed_copy("shop-petg")
            library.save(user_nozzle)
            library.save(user_machine)
            library.save(user_material)
            page = TubeSetupPage(
                viewer_factory=ViewerStub,
                resource_library=library,
            )
            self.addCleanup(page.close)

            self.assertGreaterEqual(page.nozzle_combo.findData(user_nozzle.resource_id), 0)
            self.assertGreaterEqual(page.machine_combo.findData(user_machine.profile_id), 0)
            self.assertGreaterEqual(
                page.material_combo.findData(user_material.resource_id),
                0,
            )
            self.assertIn(
                "用户库",
                page.nozzle_combo.itemText(page.nozzle_combo.findData(user_nozzle.resource_id)),
            )

            builtin_key = next(
                key
                for key, profile in page._nozzle_profiles.items()
                if profile.is_builtin and profile.orifice_diameter_mm == 0.4
            )
            page.nozzle_combo.setCurrentIndex(page.nozzle_combo.findData(builtin_key))
            page.nozzle_interface.setText("M6")
            page.nozzle_length.setValue(18.0)
            page.nozzle_collision.setChecked(True)
            page._apply_nozzle()

            selected = page.controller.setup.nozzle
            assert selected is not None
            self.assertNotEqual(selected.resource_id, builtin_key)
            self.assertEqual(len(library.profiles("nozzle")), 1)
            self.assertEqual(
                library.audit_snapshot(selected).status,
                "missing",
            )
            self.assertTrue(get_builtin_nozzle_profile(0.4).is_builtin)

            builtin_material_key = next(
                key
                for key, profile in page._material_profiles.items()
                if profile.is_builtin and profile.material == "PLA"
            )
            page.material_combo.setCurrentIndex(page.material_combo.findData(builtin_material_key))
            page.material_review.setChecked(True)
            page._apply_material()
            selected_material = page.controller.setup.material
            assert selected_material is not None
            self.assertNotEqual(selected_material.resource_id, builtin_material_key)
            self.assertEqual(len(library.profiles("material")), 1)
            self.assertEqual(
                library.audit_snapshot(selected_material).status,
                "missing",
            )

    def test_applied_page_actions_use_injected_command_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(tmp)
            controller = TubeSetupController(
                body_catalog=(
                    BodyCandidate("solid-1", "Tube", "solid"),
                    BodyCandidate("sheet-1", "Reference", "shell"),
                ),
                resource_library=library,
            )
            page = TubeSetupPage(viewer_factory=ViewerStub, resource_library=library)
            self.addCleanup(page.close)
            page.set_controller(controller, None)
            kernel = CommandKernel(controller, TubeCommandProvider())
            invocations = []

            def execute(invocation):
                invocations.append(invocation)
                return kernel.execute(invocation)

            page.set_command_executor(execute)
            page._role_combos["solid-1"].setCurrentIndex(
                page._role_combos["solid-1"].findData("part")
            )
            page._role_combos["sheet-1"].setCurrentIndex(
                page._role_combos["sheet-1"].findData("ignore")
            )
            page._confirm_part()
            page._create_operation()
            page._apply_machine()
            page._apply_nozzle()
            page.material_review.setChecked(True)
            page._apply_material()
            for node in ("model_cs", "build_cs"):
                page.apply_numeric_coordinate(node, (0, 0, 0), (0, 0, 1), (1, 0, 0))
            page.apply_placement("build_plate_mount")

            page._coordinate_node = "model_cs"
            controller.begin_coordinate_draft("model_cs")
            controller.set_numeric_origin("model_cs", (0, 0, 0), confirmed=True)
            controller.set_numeric_direction("model_cs", "z", (0, 0, 1), confirmed=True)
            controller.set_numeric_direction("model_cs", "x", (1, 0, 0), confirmed=True)
            page._apply_coordinate()
            controller.begin_placement_draft(mount_datum_id="build_plate_mount")
            page._apply_placement()

            self.assertEqual(
                [item.name for item in invocations],
                [
                    "confirm_part",
                    "create_operation",
                    "set_machine",
                    "set_nozzle",
                    "set_material",
                    "set_model_cs",
                    "set_build_cs",
                    "set_placement",
                    "apply_coordinate_draft",
                    "apply_placement_draft",
                ],
            )
            self.assertEqual(
                [item.origin for item in invocations[5:8]],
                ["automation", "automation", "automation"],
            )

    def test_damaged_user_entry_does_not_block_page_startup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broken = root / "nozzle" / "broken.json"
            broken.parent.mkdir(parents=True)
            broken.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
            library = UserResourceLibrary(root)

            page = TubeSetupPage(
                viewer_factory=ViewerStub,
                resource_library=library,
            )
            self.addCleanup(page.close)

            self.assertGreaterEqual(page.nozzle_combo.count(), 3)
            issues = page.controller.validation_report().issues
            diagnostic = next(
                issue for issue in issues if issue.code == "RESOURCE_LIBRARY_ENTRY_INVALID"
            )
            self.assertEqual(diagnostic.context["entry_name"], "broken.json")
            self.assertEqual(diagnostic.severity.value, "warning")

    def test_diverged_project_snapshot_is_a_distinct_selected_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            library = UserResourceLibrary(tmp)
            nozzle = complete_nozzle()
            library.save(nozzle)
            controller = TubeSetupController(resource_library=library)
            frozen = controller.select_nozzle(nozzle)
            library.save(replace(nozzle, display_name="Current library revision"))
            controller.refresh_resource_library()

            page = TubeSetupPage(
                viewer_factory=ViewerStub,
                resource_library=library,
            )
            self.addCleanup(page.close)
            page.set_controller(controller, None)

            selected_key = str(page.nozzle_combo.currentData())
            self.assertTrue(selected_key.startswith("project-snapshot:nozzle:"))
            self.assertIn("项目快照", page.nozzle_combo.currentText())
            self.assertIn("已分叉", page.nozzle_combo.currentText())
            self.assertGreaterEqual(page.nozzle_combo.findData(nozzle.resource_id), 0)
            self.assertEqual(page.controller.setup.nozzle, frozen)
            issue_codes = {issue.code for issue in page.controller.validation_report().issues}
            self.assertIn("RESOURCE_LIBRARY_DIVERGED", issue_codes)


if __name__ == "__main__":
    unittest.main()
