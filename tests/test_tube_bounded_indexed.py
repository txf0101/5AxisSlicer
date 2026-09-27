from pathlib import Path
from unittest.mock import patch

from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
import pytest

from five_axis_slicer.algorithms.tube.bounded_indexed import generate_bounded_indexed_toolpath
from five_axis_slicer.algorithms.tube.geometry import CenterlinePrimitive, TubeFeature
from five_axis_slicer.algorithms.tube.indexed import plan_indexed_slices
from five_axis_slicer.manufacturing.setup import TubeProcessParameters
from five_axis_slicer.models import CadModel


def inputs():
    shape = BRepAlgoAPI_Cut(BRepPrimAPI_MakeCylinder(2, .6).Shape(),
                            BRepPrimAPI_MakeCylinder(1, .6).Shape()).Shape()
    model = CadModel(Path('analytic.step'), 'analytic', [], [], {'body': shape}, {})
    feature = TubeFeature('body', 'entry', 'exit', 2, 1,
        (CenterlinePrimitive('line', (0, 0, 0), (0, 0, .6), .6),))
    parameters = TubeProcessParameters(layer_height_mm=.2, bead_width_mm=.6)
    return model, feature, plan_indexed_slices(feature, parameters), parameters


def test_live_brep_multitrack_layers_and_material():
    plan, path, residuals = generate_bounded_indexed_toolpath('op', *inputs())
    assert plan.generation_strategy == 'bounded_wall_tracks_v1'
    assert len(plan.layers) == 3
    assert len(plan.layer_bands) == 3
    assert len(plan.band_records) >= 3
    deposition = [p for p in path.points if p.point_type == 'deposition']
    assert {p.layer_id for p in deposition} == {p.layer_id for p in plan.layers}
    assert all(0 < p.bead_width_mm <= .6 for p in deposition)
    assert all(.1 <= p.layer_height_mm <= .3 for p in deposition)
    # Polygonal contours approximate the exact annular solid within chord error.
    import math
    assert sum(p.material_volume_mm3 for p in deposition) == pytest.approx(math.pi * 3 * .6, rel=.02)
    assert residuals >= 0
    assert len([p for p in path.points if p.point_type == 'approach']) == 6


def test_section_failure_is_not_silently_skipped():
    with patch('five_axis_slicer.algorithms.tube.bounded_indexed.section_tube_layer',
               side_effect=ValueError('section failure')):
        with pytest.raises(ValueError, match='section failure'):
            generate_bounded_indexed_toolpath('op', *inputs())


def test_checkpoint_interrupts_generation():
    calls = []
    def stop():
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'):
        generate_bounded_indexed_toolpath('op', *inputs(), checkpoint=stop)
    assert len(calls) == 3


def test_formal_service_generates_serializes_and_reads_back():
    from types import SimpleNamespace
    from five_axis_slicer.manufacturing.own_printer import own_ac_profile
    from five_axis_slicer.manufacturing.resources import NozzleProfile
    from five_axis_slicer.postprocessing.indexed_tube import TubeIndexedProductService
    from five_axis_slicer.postprocessing.tube_product import _plan_json
    model, feature, _, parameters = inputs()
    operation = SimpleNamespace(operation_id='op', enabled=True, parameters=parameters,
        geometry=SimpleNamespace(is_complete=True, to_json=lambda: {'test': 'analytic'}))
    nozzle = NozzleProfile(resource_id='test', display_name='Test', orifice_diameter_mm=.4,
        filament_diameter_mm=1.75, interface='M6', length_mm=18,
        outer_profile_rz_mm=((.2, 0), (1, 18)))
    with patch('five_axis_slicer.postprocessing.indexed_tube.recognise_tube', return_value=feature):
        result = TubeIndexedProductService().generate(model, operation, own_ac_profile(), nozzle)
    assert result.exportable, [i.to_json() for i in result.validation.issues]
    assert result.readback.passed
    assert result.manifest.algorithm_version == 'tube-indexed-product-v7'
    assert 'tube.bounded_boundary_accuracy_deferred' in {i.code for i in result.validation.issues}
    assert result.to_json()['slice_plan']['generation_strategy'] == 'bounded_wall_tracks_v1'
    assert len(_plan_json(result.plan)['layer_bands']) == 3
    assert result.gcode.count('; Layer ') == 3


def test_bounded_contract_retains_errors_for_bad_dimensions_and_identity():
    from dataclasses import replace
    from five_axis_slicer.validation.bounded_tube_geometry import bounded_geometry_validation
    model, feature, oldplan, parameters = inputs()
    plan, path, _ = generate_bounded_indexed_toolpath('op', model, feature, oldplan, parameters)
    index = next(i for i, p in enumerate(path.points) if p.point_type == 'deposition')
    points = list(path.points)
    points[index] = replace(points[index], bead_width_mm=2)
    _, issues = bounded_geometry_validation(feature, plan, replace(path, points=tuple(points)), .01)
    assert any(i.code == 'tube.bounded_contract_invalid' and i.severity.value == 'error' for i in issues)

