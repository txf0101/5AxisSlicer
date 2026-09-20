"""Independent modal and unsupported-axis counterexamples for the audit reader."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fan15_example_audit.py"
spec = importlib.util.spec_from_file_location("fan15_audit", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_modal_e_and_inverse_known_quarter_turn(tmp_path):
    nc = tmp_path / "input.gcode"
    nc.write_text("G90\nM82\nG1 X0 Y0 Z10 A90 E0\nG1 Y-2 E1\nG92 E0\nM83\nG1 Y-3 E.5\nG1 Y-4 E-1\n")
    report = audit.legacy(nc, tmp_path)
    segments = np.load(tmp_path / "legacy.npz")["segments"]
    assert report["positive_e_segments"] == 2
    assert report["positive_e_mm"] == 1.5
    assert segments[-1, 1] == pytest.approx((0, 10, 3))


def test_unknown_b_preserves_machine_frame(tmp_path):
    nc = tmp_path / "input.gcode"
    nc.write_text("M83\nG1 X2 Y3 Z4 A90 B45 E1\n")
    report = audit.legacy(nc, tmp_path)
    assert report["unsupported_rotary_words"] == ["B"]
    assert np.load(tmp_path / "legacy.npz")["segments"][-1, 1] == pytest.approx((2, 3, 4))


def test_arc_not_silently_discarded(tmp_path):
    nc = tmp_path / "input.gcode"
    nc.write_text("G2 X1 Y2 I3 J4 E1\n")
    with pytest.raises(ValueError, match="unsupported G2"):
        audit.legacy(nc, tmp_path)


def test_nested_positive_solids_require_union_not_hole(tmp_path):
    import cadquery as cq
    from five_axis_slicer.algorithms.planar.region import slice_planar_layers
    from five_axis_slicer.step_loader import load_step

    outer = cq.Workplane("XY").box(10, 10, 2).val()
    inner = cq.Workplane("XY").box(4, 4, 2).val()
    source = tmp_path / "nested_positive_solids.step"
    cq.exporters.export(cq.Compound.makeCompound([outer, inner]), str(source))
    model = load_step(source)
    layer = slice_planar_layers(
        model,
        tuple(b.body_id for b in model.bodies),
        first_layer_z_mm=0.2,
        last_layer_z_mm=0.2,
        layer_height_mm=0.2,
    )[0]

    def area(loop):
        return abs(sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(loop, loop[1:])) / 2)

    actual = sum(area(r.outer) - sum(area(h) for h in r.holes) for r in layer.regions)
    assert actual == pytest.approx(100.0)


def test_straight_pipe_axial_growth_requires_axial_nozzle():
    from five_axis_slicer.algorithms.tube.geometry import TubeFeature, CenterlinePrimitive
    from five_axis_slicer.algorithms.tube.continuous import generate_continuous_toolpath
    from five_axis_slicer.manufacturing.setup import TubeProcessParameters

    feature = TubeFeature(
        "tube", "entry", "exit", 16, 15, (CenterlinePrimitive("line", (0, 0, 5), (0, 0, 7), 2),)
    )
    path = generate_continuous_toolpath(
        "axial-growth", feature, TubeProcessParameters(layer_height_mm=0.2, bead_width_mm=0.4)
    )
    point = next(p for p in path.points if p.point_type == "deposition")
    assert point.nozzle_axis == pytest.approx((0, 0, -1))
