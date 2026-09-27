from dataclasses import replace

import pytest

from five_axis_slicer.algorithms.tube.geometry import CenterlinePrimitive, TubeFeature
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from five_axis_slicer.validation.bounded_tube_geometry import sampled_wall_errors


def case(radius):
    feature = TubeFeature('body', 'entry', 'exit', 16, 15,
                          (CenterlinePrimitive('line', (0, 0, 0), (0, 0, 10), 10),))
    first = ToolpathPoint('a', (radius, 0, 1), (0, 1, 0), (0, 0, -1),
                         'op', 'stage', 'layer', 'region', 'approach')
    last = replace(first, point_id='b', position=(radius, 0.1, 1),
                   point_type='deposition', material_volume_mm3=0.01, extrusion_role='thin_wall')
    return feature, GeneratedToolpath('path', 'op', points=(first, last))


@pytest.mark.parametrize('radius', [15.25, 15.75])
def test_two_tracks_inside_wall_are_not_required_to_lie_on_midwall(radius):
    feature, path = case(radius)
    outside, chord = sampled_wall_errors(feature, path)
    assert outside == 0
    assert 0 < chord < 0.001


@pytest.mark.parametrize('radius,expected', [(14.9, 0.1), (16.1, 0.1)])
def test_actual_wall_escape_is_retained(radius, expected):
    feature, path = case(radius)
    assert sampled_wall_errors(feature, path)[0] == pytest.approx(expected, abs=0.001)


def test_mismatched_deposition_identity_is_rejected():
    feature, path = case(15.25)
    path = replace(path, points=(path.points[0], replace(path.points[1], layer_id='other')))
    with pytest.raises(ValueError, match='identity'):
        sampled_wall_errors(feature, path)
