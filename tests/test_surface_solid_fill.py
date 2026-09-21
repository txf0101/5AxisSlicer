from pathlib import Path

import cadquery as cq

from five_axis_slicer.algorithms.freeform.surface_solid_fill import (
    SurfaceSolidBodySelection,
    SurfaceSolidFillParameters,
    generate_surface_solid_fill,
)
from five_axis_slicer.step_loader import load_step


def _box_case(tmp_path: Path):
    substrate = cq.Workplane("XY").box(12, 3, 1, centered=(True, True, False))
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
        key=lambda edge: sum(point[2] for point in edge.endpoints),
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
