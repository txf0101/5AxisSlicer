from pathlib import Path
import math

import cadquery as cq
import pytest

from five_axis_slicer.algorithms.freeform.surface_solid_fill import (
    SurfaceSolidBodySelection,
    SurfaceSolidFillParameters,
    generate_surface_solid_fill,
)
from five_axis_slicer.step_loader import load_step


def _box_case(tmp_path: Path, *, substrate_width=3.0, substrate_center_y=0.0, root_on_top=False):
    substrate = (
        cq.Workplane("XY")
        .box(12, substrate_width, 1, centered=(True, True, False))
        .translate((0, substrate_center_y, 5 if root_on_top else 0))
    )
    blade = cq.Workplane("XY").box(10, 1, 4, centered=(True, True, False)).translate((0, 0, 1))
    source = tmp_path / "surface-solid.step"
    cq.exporters.export(cq.Compound.makeCompound([substrate.val(), blade.val()]), str(source))
    model = load_step(source)
    body = min(model.bodies[1:], key=lambda item: abs((item.volume or 0) - 40))
    faces = [face for face in model.faces if face.body_id == body.body_id]
    selected = min(
        (face for face in faces if face.normal is not None and abs(face.normal[1]) > 0.9),
        key=lambda face: face.centroid[1],
    )
    opposite = max(
        (face for face in faces if face.normal is not None and abs(face.normal[1]) > 0.9),
        key=lambda face: face.centroid[1],
    )
    root = min(
        (model.edge_map[edge_id] for edge_id in selected.edge_ids),
        key=lambda edge: (-1 if root_on_top else 1) * sum(point[2] for point in edge.endpoints),
    )
    return model, SurfaceSolidBodySelection(
        body.body_id,
        selected.face_id,
        opposite.face_id,
        root.edge_id,
        next(item.body_id for item in model.bodies if item.body_id != body.body_id),
    )


def test_surface_solid_fill_covers_face_and_thickness_from_supported_root(tmp_path):
    model, selection = _box_case(tmp_path)
    paths, audit = generate_surface_solid_fill(
        model,
        (selection,),
        "box",
        SurfaceSolidFillParameters(1.0),
    )
    assert audit.body_count == 1
    assert audit.depth_layer_count == 5
    assert len(paths) == 5
    assert len(set(audit.paths_per_body_layer)) == 1
    assert audit.paths_per_body_layer[0] == 11
    assert audit.maximum_cross_path_spacing_mm <= 0.4 + 1e-9
    assert audit.maximum_segment_length_mm <= 0.2 + 1e-6
    assert 0.99 <= audit.thickness_min_mm <= audit.thickness_max_mm <= 1.01
    assert audit.relative_volume_error <= 0.11
    assert audit.root_edge_max_gap_mm <= 1e-6
    roles = {
        point.extrusion_role
        for path in paths
        for point in path.points
        if point.point_type == "deposition"
    }
    assert roles == {"skin", "infill"}


def test_surface_solid_fill_rejects_root_edge_on_another_face(tmp_path):
    model, selection = _box_case(tmp_path)
    wrong = next(
        edge.edge_id
        for edge in model.edges
        if edge.body_id == selection.body_id and selection.face_id not in edge.face_ids
    )
    bad = SurfaceSolidBodySelection(
        selection.body_id, selection.face_id, selection.opposite_face_id, wrong
    )
    try:
        generate_surface_solid_fill(model, (bad,), "box", SurfaceSolidFillParameters(1.0))
    except ValueError as error:
        assert "root edge" in str(error)
    else:
        raise AssertionError("unrelated root edge accepted")


def test_root_edge_outward_fills_each_growth_layer_across_thickness(tmp_path):
    model, selection = _box_case(tmp_path)
    parameters = SurfaceSolidFillParameters(1.0, surface_growth_strategy="root_edge_outward")
    paths, audit = generate_surface_solid_fill(model, (selection,), "box", parameters)

    # The blade rises four millimetres from the supported plate. The first
    # contour sits half a layer above the root, then each layer fills the wall.
    assert len(paths) == 1
    assert audit.growth_layer_count == 20
    assert audit.depth_layer_count == 3
    assert audit.paths_per_body_layer == (3,) * 20
    assert audit.relative_volume_error < 0.01
    assert audit.maximum_cross_path_spacing_mm <= parameters.path_spacing_mm
    first_heights = []
    path = paths[0]
    assert path.operation_id.endswith("-growth")
    deposition_points = [point for point in path.points if point.point_type == "deposition"]
    for index in range(1, 21):
        deposition = [
            point for point in deposition_points if point.layer_id == f"growth-{index:03d}"
        ]
        assert deposition
        assert {point.layer_id for point in deposition} == {f"growth-{index:03d}"}
        assert {point.region_id for point in deposition} == {selection.body_id}
        assert {round(point.position[1], 3) for point in deposition} == {-0.333, 0.0, 0.333}
        first_heights.append(deposition[0].position[2])
        for point in deposition:
            assert point.nozzle_axis == pytest.approx((0, 0, -1), abs=1e-8)
            assert (
                abs(math.dist(point.nozzle_axis, point.surface_normal or (0, 0, 0)) - 2**0.5) < 1e-8
            )
            assert point.bead_width_mm == pytest.approx(0.4)
    assert first_heights == pytest.approx([1.1 + 0.2 * index for index in range(20)])


def test_root_edge_outward_requires_a_supported_root(tmp_path):
    model, selection = _box_case(tmp_path)
    unsupported = SurfaceSolidBodySelection(
        selection.body_id,
        selection.face_id,
        selection.opposite_face_id,
        selection.root_edge_id,
    )
    with pytest.raises(ValueError, match="root_support_missing"):
        generate_surface_solid_fill(
            model,
            (unsupported,),
            "box",
            SurfaceSolidFillParameters(1.0, surface_growth_strategy="root_edge_outward"),
        )

    top_edge = max(
        (model.edge_map[edge_id] for edge_id in model.face_map[selection.face_id].edge_ids),
        key=lambda edge: sum(point[2] for point in edge.endpoints),
    )
    wrong_support = SurfaceSolidBodySelection(
        selection.body_id,
        selection.face_id,
        selection.opposite_face_id,
        top_edge.edge_id,
        selection.substrate_body_id,
    )
    with pytest.raises(ValueError, match="root_support_gap"):
        generate_surface_solid_fill(
            model,
            (wrong_support,),
            "box",
            SurfaceSolidFillParameters(1.0, surface_growth_strategy="root_edge_outward"),
        )


def test_root_edge_outward_rejects_substrate_supporting_only_one_wall_side(tmp_path):
    model, selection = _box_case(tmp_path, substrate_width=0.1, substrate_center_y=-0.5)
    with pytest.raises(ValueError, match="first_layer_unsupported"):
        generate_surface_solid_fill(
            model,
            (selection,),
            "box",
            SurfaceSolidFillParameters(1.0, surface_growth_strategy="root_edge_outward"),
        )


def test_root_edge_outward_can_fill_from_a_supported_first_thickness_track(tmp_path):
    model, selection = _box_case(tmp_path, substrate_width=0.3, substrate_center_y=-0.35)
    paths, audit = generate_surface_solid_fill(
        model,
        (selection,),
        "box-side-support",
        SurfaceSolidFillParameters(1.0, surface_growth_strategy="root_edge_outward"),
    )
    assert len(paths) == 1
    assert audit.paths_per_body_layer == (3,) * 20
    first_layer = [
        point
        for point in paths[0].points
        if point.point_type == "deposition" and point.layer_id == "growth-001"
    ]
    assert {round(point.position[1], 3) for point in first_layer} == {-0.333, 0.0, 0.333}


def test_root_edge_outward_handles_the_other_parametric_boundary(tmp_path):
    model, selection = _box_case(tmp_path, root_on_top=True)
    paths, audit = generate_surface_solid_fill(
        model,
        (selection,),
        "box-top",
        SurfaceSolidFillParameters(1.0, surface_growth_strategy="root_edge_outward"),
    )
    deposition = [point for point in paths[0].points if point.point_type == "deposition"]
    assert audit.growth_layer_count == 20
    assert deposition[0].position[2] == pytest.approx(4.9)
    assert deposition[0].nozzle_axis == pytest.approx((0, 0, 1))
    assert deposition[-1].position[2] < 1.2
