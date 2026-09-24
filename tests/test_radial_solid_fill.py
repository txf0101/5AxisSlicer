from pathlib import Path

import cadquery as cq
import pytest

from five_axis_slicer.algorithms.fan.radial_solid_fill import (
    RadialSolidBladeSelection,
    RadialSolidFillParameters,
    _projected_gap,
    generate_radial_solid_fill,
)
from five_axis_slicer.postprocessing.indexed_tube import GenerationCancelled
from five_axis_slicer.step_loader import load_step


def test_radial_solid_fill_bridges_explicit_hub_gap(tmp_path: Path):
    hub = cq.Workplane("XY").circle(10).extrude(4)
    blade = cq.Workplane("XY").box(1.5, 1, 2, centered=(False, True, False)).translate((10.5, 0, 1))
    source = tmp_path / "radial-gap.step"
    cq.exporters.export(cq.Compound.makeCompound([hub.val(), blade.val()]), str(source))
    model = load_step(source)
    hub_body = max(model.bodies, key=lambda item: item.volume or 0)
    blade_body = min(model.bodies, key=lambda item: item.volume or 0)
    side_faces = [
        face
        for face in model.faces
        if face.body_id == blade_body.body_id
        and face.normal is not None
        and abs(face.normal[0]) > 0.9
    ]
    root = min(side_faces, key=lambda face: face.centroid[0])
    outer = max(side_faces, key=lambda face: face.centroid[0])
    paths, audit = generate_radial_solid_fill(
        model,
        (
            RadialSolidBladeSelection(
                blade_body.body_id,
                hub_body.body_id,
                root.face_id,
                outer.face_id,
            ),
        ),
        "analytic",
        RadialSolidFillParameters(sample_segments=32, face_metric_samples=17),
    )
    assert len(paths) == 1
    assert audit.bridge_layer_counts[0] >= 1
    assert audit.supported_first_radii_mm[0] < audit.cad_root_section_radii_mm[0]
    assert audit.first_layer_hub_gap_max_mm <= 0.201
    assert audit.maximum_radial_spacing_mm == 0.2
    assert audit.maximum_segment_length_mm <= 0.4 + 1e-6
    assert any(point.point_type == "deposition" for point in paths[0].points)


def test_radial_solid_fill_rejects_invalid_parameters():
    try:
        RadialSolidFillParameters(bead_width_mm=0)
    except ValueError as error:
        assert "bead_width_mm" in str(error)
    else:
        raise AssertionError("zero bead width accepted")


def test_hub_gap_distance_search_checks_cancellation_before_native_query():
    with pytest.raises(GenerationCancelled):
        _projected_gap(((10.0, 0.0, 0.0),), object(), 9.0, cancelled=lambda: True)
