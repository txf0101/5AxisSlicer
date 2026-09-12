from pathlib import Path
from dataclasses import replace
import math
import sys

import cadquery as cq
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.algorithms.planar.region import slice_planar_layers
from five_axis_slicer.algorithms.planar.support import (
    SupportParameters,
    generate_support_plan,
    generate_support_toolpath,
)
from five_axis_slicer.manufacturing.coordinates import RigidTransform
from five_axis_slicer.manufacturing.setup import IssueSeverity
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from five_axis_slicer.models import CadModel
from five_axis_slicer.postprocessing.indexed_tube import GenerationCancelled
from five_axis_slicer.validation.planar_travel import support_cad_issues
from five_axis_slicer.validation import planar_travel


def _model(shape):
    return CadModel(
        Path("support-motion.step"), "a" * 64, [], [], {"body": shape.val().wrapped}, {}
    )


def _path(positions, kind="travel"):
    points = []
    for index, position in enumerate(positions):
        deposition = index > 0 and kind == "deposition"
        volume = math.dist(positions[index - 1], position) * 0.4 * 0.2 if deposition else 0.0
        points.append(
            ToolpathPoint(
                f"point-{index + 1}",
                position,
                (1, 0, 0),
                (0, 0, -1),
                "support-op",
                "support",
                "l1",
                "r1",
                kind if index else "approach",
                extrusion_role="support" if deposition else "none",
                bead_width_mm=0.4 if deposition else None,
                layer_height_mm=0.2 if deposition else None,
                material_volume_mm3=volume,
            )
        )
    return GeneratedToolpath("support-path", "support-op", points=tuple(points))


def _check(model, path, transform=None, **kwargs):
    return support_cad_issues(
        path,
        model,
        "body",
        transform or RigidTransform.identity("build"),
        **kwargs,
    )


def _errors(issues):
    return [issue for issue in issues if issue.severity is IssueSeverity.ERROR]


@pytest.mark.parametrize("kind", ["travel", "deposition"])
def test_complete_segment_detects_thin_obstacle_between_coarse_samples(kind):
    model = _model(cq.Workplane("XY").box(0.005, 2, 2).translate((1.303, 0, 0)))
    issues = _check(model, _path([(0, 0, 0), (10, 0, 0)], kind))
    assert [issue.code for issue in _errors(issues)] == [
        f"planar.support_{kind}_intersects_target_cad"
    ]
    assert _errors(issues)[0].object_id == "point-2"
    assert _errors(issues)[0].context["already_printed_state_assumed"] is False


def test_cross_layer_diagonal_travel_is_checked_between_its_endpoint_planes():
    model = _model(cq.Workplane("XY").box(0.05, 0.1, 0.05).translate((5, 0, 1)))
    assert _errors(_check(model, _path([(0, 0, 0), (10, 0, 2)])))


def test_isolated_boundary_tangency_is_conservatively_rejected():
    model = _model(cq.Workplane("XY").box(2, 2, 2))
    # The segment touches only the (-1, 1, 0) corner; both endpoints are outside.
    assert _errors(_check(model, _path([(-3, -1, 0), (1, 3, 0)])))


def test_initial_point_inside_target_is_checked_without_an_incoming_segment():
    model = _model(cq.Workplane("XY").box(2, 2, 2))
    issues = _errors(_check(model, _path([(0, 0, 0)])))
    assert len(issues) == 1
    assert issues[0].context["first_point_type"] == "approach"


def test_target_check_uses_build_to_model_rotation_and_translation():
    model = _model(cq.Workplane("XY").box(0.5, 0.01, 0.5).translate((10, 5, 6)))
    path = _path([(0, 0, 0), (10, 0, 0)])
    transform = RigidTransform(
        ((0, -1, 0, 10), (1, 0, 0, 0), (0, 0, 1, 6), (0, 0, 0, 1)),
        source_frame="build",
        target_frame="model",
    )
    assert not _errors(_check(model, path))
    assert _errors(_check(model, path, transform))


def test_clear_path_still_reports_independent_operation_and_schedule_boundary():
    model = _model(cq.Workplane("XY").box(2, 2, 2))
    issues = _check(model, _path([(-3, 3, 0), (3, 3, 0)]))
    assert not _errors(issues)
    assert len(issues) == 1
    assert issues[0].code == "planar.support_joint_schedule_unverified"
    assert issues[0].context["joint_layer_schedule_verified"] is False
    assert issues[0].context["full_nozzle_sweep_verified"] is False


def test_kernel_failure_does_not_become_a_clear_path(monkeypatch):
    def fail(*args):
        raise RuntimeError("synthetic extrema failure")

    monkeypatch.setattr(planar_travel, "_intersects_shape", fail)
    model = _model(cq.Workplane("XY").box(2, 2, 2))
    issues = _errors(_check(model, _path([(-3, 0, 0), (3, 0, 0)])))
    assert issues[0].code == "planar.support_cad_check_failed"


def test_cancellation_during_target_check_is_not_converted_to_kernel_failure():
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 3

    model = _model(cq.Workplane("XY").box(2, 2, 2))
    with pytest.raises(GenerationCancelled, match="support CAD validation cancelled"):
        _check(model, _path([(-3, 0, 0), (3, 0, 0)]), cancelled=cancelled)


def test_missing_cad_or_unknown_path_frame_blocks_qualification():
    model = _model(cq.Workplane("XY").box(2, 2, 2))
    path = _path([(-3, 0, 0), (3, 0, 0)])
    assert _errors(_check(model, replace(path, coordinate_frame="machine")))[0].code == (
        "planar.support_cad_frame_unsupported"
    )
    model.shapes.clear()
    assert _errors(_check(model, path))[0].code == "planar.support_cad_unavailable"


def _support_path(model):
    layers = slice_planar_layers(
        model,
        ("body",),
        first_layer_z_mm=0.5,
        last_layer_z_mm=3,
        layer_height_mm=0.5,
    )
    parameters = SupportParameters(
        0.5,
        xy_gap_mm=0.4,
        z_gap_mm=0,
        bead_width_mm=0.6,
        line_spacing_mm=1,
        interface_spacing_mm=0.6,
        interface_layers=2,
        pattern="grid",
    )
    plan = generate_support_plan(layers, parameters)
    return generate_support_toolpath("support-op", plan, parameters)


def test_real_pillar_roof_support_has_rejected_travel_but_valid_deposition_centreline():
    pillar = cq.Workplane("XY").box(4, 6, 2.4).translate((6, 5, 1.2))
    roof = cq.Workplane("XY").box(12, 10, 1).translate((6, 5, 2.7))
    model = _model(pillar.union(roof))
    issues = _errors(_check(model, _support_path(model)))
    assert [issue.code for issue in issues] == ["planar.support_travel_intersects_target_cad"]
    assert issues[0].context["intersection_count"] > 0


def test_floating_roof_support_keeps_half_bead_inside_its_analytic_projection():
    model = _model(cq.Workplane("XY").box(8, 6, 1).translate((8, 5, 2.7)))
    path = _support_path(model)
    assert not _errors(_check(model, path))
    for previous, current in zip(path.points, path.points[1:]):
        if current.point_type == "deposition":
            for point in (previous.position, current.position):
                assert 4.3 - 1e-7 <= point[0] <= 11.7 + 1e-7
                assert 2.3 - 1e-7 <= point[1] <= 7.7 + 1e-7
                assert point[2] < 2.2


def test_pillar_roof_product_blocks_gcode_and_export_after_target_cad_check(tmp_path):
    from test_planar_support_product import _cad_model, _generate, _support_operation
    from five_axis_slicer.postprocessing.planar_product import export_planar_product

    pillar = cq.Workplane("XY").box(4, 6, 2.4).translate((6, 5, 1.2))
    roof = cq.Workplane("XY").box(12, 10, 1).translate((6, 5, 2.7))
    model = _cad_model(tmp_path, pillar.union(roof), "pillar-roof-motion")
    result = _generate(model, _support_operation(support_xy_gap_mm=0.4))
    assert result.manifest.status.value == "error"
    assert "planar.support_travel_intersects_target_cad" in result.manifest.issues
    assert "planar.support_joint_schedule_unverified" in result.manifest.issues
    assert not result.exportable
    assert result.gcode == ""
    with pytest.raises(ValueError, match="blocks export"):
        export_planar_product(result, tmp_path / "rejected-support")
    assert not (tmp_path / "rejected-support").exists()
