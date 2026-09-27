"""Necessary contact checks with independent straight-segment fixtures."""

from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from five_axis_slicer.validation.tube_support import transition_support_issues


def point(i, x, z, layer, region, kind):
    return ToolpathPoint(
        point_id=f"p{i}",
        position=(x, 0, z),
        tangent=(1, 0, 0),
        nozzle_axis=(0, 0, -1),
        operation_id="op",
        stage_id=region,
        layer_id=layer,
        region_id=region,
        point_type=kind,
        extrusion_role="thin_wall" if kind == "deposition" else "none",
        bead_width_mm=0.6,
        layer_height_mm=0.2,
    )


def path(height):
    return GeneratedToolpath(
        "path",
        "op",
        points=(
            point(0, 0, 0, "a", "r1", "approach"),
            point(1, 2, 0, "a", "r1", "deposition"),
            point(2, 0, height, "b", "r2", "approach"),
            point(3, 1, height, "b", "r2", "deposition"),
        ),
    )


def test_nominal_adjacent_layer_has_possible_contact():
    assert transition_support_issues(path(0.2)) == ()


def test_gap_is_rejected_even_with_current_layer_travel_beneath_it():
    issues = transition_support_issues(path(2))
    assert any(issue.code == "tube.transition_support_gap" for issue in issues)


def test_prior_segment_interior_counts_not_just_endpoints():
    # Current x=1 is one millimetre from either old vertex, but only .2 from its segment.
    assert transition_support_issues(path(0.2)) == ()


def test_substrate_box_prevents_false_rejection():
    assert transition_support_issues(path(2), substrate_bounds=(((0, -1, 1.8), (2, 1, 2)),)) == ()


def test_earlier_layer_can_support_when_latest_one_does_not():
    original = path(0.2)
    points = (
        original.points[:2]
        + (
            point(4, 0, -2, "middle", "r1", "approach"),
            point(5, 2, -2, "middle", "r1", "deposition"),
        )
        + original.points[2:]
    )
    assert transition_support_issues(replace(original, points=points)) == ()


def test_missing_bead_dimensions_cannot_silently_pass():
    original = path(2)
    points = tuple(replace(p, bead_width_mm=None) for p in original.points)
    assert transition_support_issues(replace(original, points=points))


def test_tapered_prior_segment_envelope_includes_its_wide_start():
    original = path(0.8)
    points = list(original.points)
    points[0] = replace(points[0], bead_width_mm=2.0, layer_height_mm=0.2)
    points[3] = replace(points[3], position=(0, 0, 0.8))
    assert transition_support_issues(replace(original, points=tuple(points))) == ()
    # A farther point is outside even that conservative bound.
    points[3] = replace(points[3], position=(0, 0, 2))
    assert any(i.code == "tube.transition_support_gap"
               for i in transition_support_issues(replace(original, points=tuple(points))))


def test_product_validation_cannot_export_a_known_support_gap(monkeypatch):
    from five_axis_slicer.validation import indexed_tube

    toolpath = path(2)
    # Aggregate Indexed validation consumes the actual builder connection order.
    toolpath = replace(
        toolpath,
        points=(
            *toolpath.points[:2],
            replace(toolpath.points[0], point_id="depart", point_type="depart"),
            replace(toolpath.points[2], point_id="travel", point_type="travel"),
            *toolpath.points[2:],
        ),
    )
    # Isolate contact from independent radial/motion checks; the aggregate
    # report must retain its Error even when the other checks report success.
    monkeypatch.setattr(indexed_tube, "_geometry_metrics", lambda *args: [])
    monkeypatch.setattr(indexed_tube, "_collision_issues", lambda *args, **kwargs: ([], 0))
    trajectory = SimpleNamespace(samples=toolpath.points, issues=(), trajectory_id="axes")
    report = indexed_tube.validate_indexed_tube(
        None, None, toolpath, trajectory, SimpleNamespace(is_ready=True)
    )
    assert report.has_errors
    assert not report.ready_for_export
    assert any(issue.code == "tube.transition_support_gap" for issue in report.issues)
