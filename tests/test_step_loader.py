from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cadquery as cq
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import (
    STEPControl_AsIs,
    STEPControl_Controller,
    STEPControl_Writer,
)
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

from five_axis_slicer.step_loader import (
    StepLoadCancelled,
    StepLoadError,
    file_sha256,
    load_step,
)


def make_two_body_step(directory: Path) -> Path:
    path = directory / "two_boxes.step"
    assembly = cq.Assembly()
    assembly.add(cq.Workplane("XY").box(1, 1, 1), name="box_a")
    assembly.add(cq.Workplane("XY").box(1, 1, 1).translate((2, 0, 0)), name="box_b")
    assembly.save(str(path))
    return path


def make_unit_step(directory: Path, unit: str, size: float = 1.0) -> Path:
    """Write numeric STEP coordinates in the requested declared unit."""

    STEPControl_Controller.Init_s()
    previous = Interface_Static.CVal_s("write.step.unit") or "MM"
    path = directory / f"box_{unit.lower()}.step"
    try:
        if not Interface_Static.SetCVal_s("write.step.unit", unit):
            raise RuntimeError(f"OCCT does not support STEP writer unit {unit}")
        writer = STEPControl_Writer()
        shape = cq.Workplane("XY").box(size, size, size).val().wrapped
        if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
            raise RuntimeError("OCCT failed to transfer unit test shape")
        if writer.Write(str(path)) != IFSelect_RetDone:
            raise RuntimeError("OCCT failed to write unit test STEP")
    finally:
        Interface_Static.SetCVal_s("write.step.unit", previous)
    return path


def make_free_face_step(directory: Path, *, direct_face_root: bool) -> Path:
    """Write an OCCT planar face and optionally expose it as a STEP root."""

    STEPControl_Controller.Init_s()
    previous_unit = Interface_Static.CVal_s("write.step.unit") or "MM"
    path = directory / ("direct_free_face.step" if direct_face_root else "open_shell_face.step")
    face = BRepBuilderAPI_MakeFace(
        gp_Pln(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
        0.0,
        10.0,
        0.0,
        20.0,
    ).Face()
    try:
        if not Interface_Static.SetCVal_s("write.step.unit", "MM"):
            raise RuntimeError("OCCT does not support the millimetre writer unit")
        writer = STEPControl_Writer()
        if writer.Transfer(face, STEPControl_AsIs) != IFSelect_RetDone:
            raise RuntimeError("OCCT failed to transfer free-face test geometry")
        if writer.Write(str(path)) != IFSelect_RetDone:
            raise RuntimeError("OCCT failed to write free-face test STEP")
    finally:
        Interface_Static.SetCVal_s("write.step.unit", previous_unit)
    if not direct_face_root:
        return path

    # STEPControl wraps an isolated face in OPEN_SHELL.  Keep the OCCT-authored
    # entities and point the representation at its ADVANCED_FACE so the reader
    # returns the independent TopoDS_Face emitted by other STEP producers.
    payload = path.read_text(encoding="utf-8")
    shell_model = re.search(
        r"#(?P<model>\d+)\s*=\s*SHELL_BASED_SURFACE_MODEL"
        r"\([^;]*?\(#(?P<shell>\d+)\)\s*\);",
        payload,
        re.DOTALL,
    )
    if shell_model is None:
        raise RuntimeError("OCCT STEP did not contain a shell-based surface model")
    shell_id = shell_model.group("shell")
    open_shell = re.search(
        rf"#{shell_id}\s*=\s*OPEN_SHELL" r"\([^;]*?\(#(?P<face>\d+)\)\s*\);",
        payload,
        re.DOTALL,
    )
    if open_shell is None:
        raise RuntimeError("OCCT STEP did not contain the expected open shell")
    model_id = shell_model.group("model")
    face_id = open_shell.group("face")
    representation = re.compile(
        rf"(?P<prefix>MANIFOLD_SURFACE_SHAPE_REPRESENTATION\([^;]*?)"
        rf"#{model_id}(?P<suffix>[^;]*?\);)",
        re.DOTALL,
    )
    payload, replacement_count = representation.subn(
        lambda match: f"{match.group('prefix')}#{face_id}{match.group('suffix')}",
        payload,
        count=1,
    )
    if replacement_count != 1:
        raise RuntimeError("OCCT STEP surface representation could not be adjusted")
    path.write_text(payload, encoding="utf-8")
    return path


class StepLoaderTests(unittest.TestCase):
    def test_promotes_an_independent_free_face_to_a_sheet_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = make_free_face_step(Path(tmp), direct_face_root=True)
            model = load_step(step_path)

        self.assertEqual(len(model.bodies), 1)
        self.assertEqual(len(model.solid_bodies), 0)
        self.assertEqual(model.bodies[0].kind, "sheet")
        self.assertIsNone(model.bodies[0].volume)
        self.assertEqual(len(model.bodies[0].face_ids), 1)
        self.assertEqual(len(model.faces), 1)
        self.assertEqual(len(model.edges), 4)
        self.assertEqual(len(model.vertices), 4)
        self.assertAlmostEqual(model.bodies[0].surface_area or 0.0, 200.0)

    def test_does_not_duplicate_a_face_owned_by_a_free_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = make_free_face_step(Path(tmp), direct_face_root=False)
            model = load_step(step_path)

        self.assertEqual(len(model.bodies), 1)
        self.assertEqual(model.bodies[0].kind, "sheet")
        self.assertEqual(len(model.bodies[0].face_ids), 1)
        self.assertEqual(len(model.faces), 1)

    def test_file_hash_can_be_cancelled_between_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "large.step"
            source.write_bytes(b"x" * (3 * 1024 * 1024))
            checks = 0

            def cancel_during_hash() -> bool:
                nonlocal checks
                checks += 1
                return checks >= 4

            with self.assertRaises(StepLoadCancelled):
                file_sha256(source, cancel_check=cancel_during_hash)

        self.assertGreaterEqual(checks, 4)

    def test_loads_two_solids_and_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = make_two_body_step(Path(tmp))
            expected_size = step_path.stat().st_size
            expected_mtime = step_path.stat().st_mtime_ns
            model = load_step(step_path)

        self.assertEqual(len(model.bodies), 2)
        self.assertGreaterEqual(len(model.edges), 24)
        self.assertEqual(model.bodies[0].body_id, "body_001")
        self.assertTrue(model.bodies[0].edge_ids[0].startswith("body_001_edge_"))
        self.assertEqual(model.edges[0].body_id, "body_001")
        self.assertEqual(len(model.source_hash), 64)
        self.assertEqual(model.source_size_bytes, expected_size)
        self.assertEqual(model.source_mtime_ns, expected_mtime)
        self.assertEqual({body.name for body in model.bodies}, {"box_a", "box_b"})
        self.assertTrue(model.bodies[0].assembly_path.endswith("/box_a"))
        self.assertTrue(model.bodies[1].assembly_path.endswith("/box_b"))

    def test_ambiguous_product_geometry_keeps_explicit_generic_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coincident.step"
            assembly = cq.Assembly(name="root")
            assembly.add(cq.Workplane("XY").box(1, 1, 1), name="one")
            assembly.add(cq.Workplane("XY").box(1, 1, 1), name="two")
            assembly.save(str(path))
            model = load_step(path)

        self.assertEqual([body.name for body in model.bodies], ["Solid 1", "Solid 2"])
        self.assertEqual([body.assembly_path for body in model.bodies], [None, None])

    def test_loads_single_solid_without_region_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "single_box.step"
            cq.exporters.export(cq.Workplane("XY").box(1, 1, 1), str(step_path))
            model = load_step(step_path)

        self.assertEqual(len(model.bodies), 1)
        self.assertEqual(model.bodies[0].body_id, "body_001")
        self.assertGreaterEqual(len(model.bodies[0].edge_ids), 12)

    def test_rejects_a_step_source_that_changes_during_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "changing_box.step"
            cq.exporters.export(cq.Workplane("XY").box(1, 1, 1), str(step_path))
            with mock.patch(
                "five_axis_slicer.step_loader.file_sha256",
                side_effect=["a" * 64, "b" * 64],
            ):
                with self.assertRaisesRegex(RuntimeError, "changed while loading"):
                    load_step(step_path)

    def test_cancels_during_topology_enumeration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = Path(tmp) / "topology_cancel.step"
            cq.exporters.export(cq.Workplane("XY").box(1, 1, 1), str(step_path))
            cancelled = False

            def sample_then_cancel(*_args: object, **_kwargs: object) -> list[object]:
                nonlocal cancelled
                cancelled = True
                return []

            with mock.patch(
                "five_axis_slicer.step_loader.sample_edge_points",
                side_effect=sample_then_cancel,
            ):
                with self.assertRaises(StepLoadCancelled):
                    load_step(step_path, cancel_check=lambda: cancelled)

    def test_declared_millimetres_ignore_an_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = make_unit_step(Path(tmp), "MM")
            model = load_step(step_path, length_unit_override="inch")

        self.assertEqual(model.units.source_length_unit, "millimetre")
        self.assertFalse(model.units.override_applied)
        self.assertEqual(model.units.conversion_source, "step_declaration")
        self.assertAlmostEqual(model.bodies[0].bounds.maximum[0] * 2.0, 1.0, places=5)

    def test_declared_inches_are_converted_once_to_millimetres(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = make_unit_step(Path(tmp), "INCH")
            model = load_step(step_path)

        self.assertEqual(model.units.source_length_unit, "inch")
        self.assertAlmostEqual(model.units.scale_to_mm, 25.4)
        self.assertAlmostEqual(model.bodies[0].bounds.maximum[0] * 2.0, 25.4, places=4)

    def test_missing_declaration_uses_override_and_scales_numeric_geometry(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = make_unit_step(Path(tmp), "MM")
            with mock.patch(
                "five_axis_slicer.step_loader._first_ascii",
                side_effect=[None, "radian", "steradian"],
            ):
                model = load_step(step_path, length_unit_override="inch")

        self.assertTrue(model.units.override_applied)
        self.assertIsNone(model.units.declared_length_unit)
        self.assertEqual(model.units.conversion_source, "override_missing_declaration")
        self.assertAlmostEqual(model.bodies[0].bounds.maximum[0] * 2.0, 25.4, places=4)

    def test_unsupported_declaration_requires_override_without_double_scaling(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            step_path = make_unit_step(Path(tmp), "INCH")
            step_path.write_text(
                step_path.read_text().replace(
                    "CONVERSION_BASED_UNIT('INCH'",
                    "CONVERSION_BASED_UNIT('SMOOT'",
                )
            )
            with self.assertRaisesRegex(StepLoadError, "length unit"):
                load_step(step_path)
            inch_model = load_step(step_path, length_unit_override="inch")
            millimetre_model = load_step(step_path, length_unit_override="mm")

        self.assertEqual(inch_model.units.declared_length_unit, "SMOOT")
        self.assertEqual(
            inch_model.units.conversion_source,
            "override_unsupported_declaration",
        )
        self.assertAlmostEqual(
            inch_model.bodies[0].bounds.maximum[0] * 2.0,
            25.4,
            places=5,
        )
        self.assertAlmostEqual(
            millimetre_model.bodies[0].bounds.maximum[0] * 2.0,
            1.0,
            places=5,
        )


if __name__ == "__main__":
    unittest.main()
