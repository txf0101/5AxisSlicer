from five_axis_slicer.gcode_parser import parse_lines
from five_axis_slicer.kinematics.xyzac import MachineAxisSample, MachineAxisTrajectory
from five_axis_slicer.manufacturing.own_printer import own_ac_profile
from five_axis_slicer.manufacturing.preview_kinematics import OWN_AC_PREVIEW_SEMANTICS
from five_axis_slicer.manufacturing.resources import NozzleProfile
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from five_axis_slicer.postprocessing.indexed_tube import postprocess_indexed_gcode


def program(explicit):
    kinds = ('approach', 'deposition', 'deposition', 'depart', 'travel', 'approach',
             'deposition', 'depart', 'travel', 'approach', 'deposition')
    layers = ('curved',) * 7 + ('next',) * 4
    points = tuple(ToolpathPoint(f'p{i}', (i, 0, 5 + i * .1), (1, 0, 0), (0, 0, -1),
        'op', 's', layer, 'r', kind, bead_width_mm=.5, layer_height_mm=.2,
        material_volume_mm3=.1 if kind == 'deposition' else 0,
        extrusion_role='thin_wall' if kind == 'deposition' else 'none')
        for i, (kind, layer) in enumerate(zip(kinds, layers)))
    toolpath = GeneratedToolpath('path', 'op', points=points)
    machine = own_ac_profile()
    samples = tuple(MachineAxisSample(p.point_id, i,
        {'X': p.position[0], 'Y': 0, 'Z': p.position[2] + 18.1, 'A': 0, 'C': 0})
        for i, p in enumerate(points))
    trajectory = MachineAxisTrajectory('axes', machine.profile_id, 'path', samples, tool_length_mm=18)
    nozzle = NozzleProfile(resource_id='test', display_name='Test', orifice_diameter_mm=.4,
        filament_diameter_mm=1.75, interface='M6', length_mm=18, outer_profile_rz_mm=((.2, 0), (1, 18)))
    return postprocess_indexed_gcode(toolpath, trajectory, machine, nozzle, indexed_tip_preview=explicit)


def test_explicit_layers_follow_identity_across_nonplanar_multitrack_moves():
    nc = program(True)
    assert nc.count('; Layer 0\n') == 1
    assert nc.count('; Layer 1\n') == 1
    preview = parse_lines(nc.splitlines(), controller_semantics=OWN_AC_PREVIEW_SEMANTICS, tool_length_mm=18)
    assert preview.layer_count == 2
    assert [step.layer for step in preview.timeline] == [0] * 7 + [1] * 4
    assert preview.timeline[2].end[2] != preview.timeline[1].end[2]
    assert preview.timeline[8].layer == 1  # Destination travel uses the new layer.


def test_shared_postprocessor_default_preserves_legacy_layer_behavior():
    nc = program(False)
    assert '; Layer ' not in nc
    assert 'INDEXED_TUBE_POINT' not in nc
    preview = parse_lines(nc.splitlines(), controller_semantics=OWN_AC_PREVIEW_SEMANTICS, tool_length_mm=18)
    assert preview.layer_count == 1
