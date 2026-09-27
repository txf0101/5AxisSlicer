"""NC round trips preserve TCP axes and reconstruct Indexed material centers."""

import math
import pytest

from five_axis_slicer.gcode_preview import load_gcode, parse_gcode
from five_axis_slicer.kinematics.xyzac import solve_xyzac_trajectory
from five_axis_slicer.manufacturing.own_printer import own_ac_profile
from five_axis_slicer.manufacturing.resources import NozzleProfile
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from five_axis_slicer.manufacturing.tube_tcp import indexed_centerline_to_tcp
from five_axis_slicer.postprocessing.indexed_tube import postprocess_indexed_gcode


def fixture(axis):
    kinds = ["approach", "deposition", "depart", "travel", "approach", "deposition"]
    points = tuple(
        ToolpathPoint(
            point_id=f"p{i}",
            position=(i, 0, 5.1),
            tangent=(1, 0, 0),
            nozzle_axis=axis,
            operation_id="op",
            stage_id="s",
            layer_id="l1" if i < 2 else "l2",
            region_id="r",
            point_type=kind,
            extrusion_role="thin_wall" if kind == "deposition" else "none",
            bead_width_mm=0.6 if kind == "deposition" else None,
            layer_height_mm=(0.2 if i == 1 else 0.4) if kind == "deposition" else None,
            material_volume_mm3=0.1 if kind == "deposition" else 0,
            feedrate_mm_min=1200,
        )
        for i, kind in enumerate(kinds)
    )
    path = GeneratedToolpath("t", "op", points=points)
    nozzle = NozzleProfile(
        resource_id="n",
        display_name="N",
        orifice_diameter_mm=0.4,
        filament_diameter_mm=1.75,
        interface="M6",
        length_mm=18,
        outer_profile_rz_mm=((0.2, 0), (1, 18)),
    )
    machine = own_ac_profile()
    trajectory = solve_xyzac_trajectory(indexed_centerline_to_tcp(path), machine, tool_length_mm=18)
    return path, trajectory, machine, nozzle


@pytest.mark.parametrize("axis", [(0, 0, -1), (0, -math.sqrt(0.5), -math.sqrt(0.5))])
def test_actual_postprocess_load_material_and_machine_coordinates(tmp_path, axis):
    source, trajectory, machine, nozzle = fixture(axis)
    nc = postprocess_indexed_gcode(source, trajectory, machine, nozzle, indexed_tip_preview=True)
    from five_axis_slicer.postprocessing.gcode_readback import readback_absolute_xyzac

    assert readback_absolute_xyzac(nc, source, trajectory, machine, nozzle).passed
    target = tmp_path / "tube.gcode"
    target.write_text(nc)
    preview = load_gcode(target)
    assert len(preview.timeline) == len(source.points)
    for step, point, sample in zip(preview.timeline, source.points, trajectory.samples):
        assert step.end == pytest.approx(point.position, abs=2e-6)
        assert step.machine_end == pytest.approx(
            tuple(sample.joint_positions[k] for k in "XYZ"), abs=1e-6
        )
    assert preview.segments[-1].bead_height == pytest.approx(0.4)


def test_old_no_declaration_preserves_tcp(tmp_path):
    source, trajectory, machine, nozzle = fixture((0, 0, -1))
    target = tmp_path / "old.gcode"
    target.write_text(postprocess_indexed_gcode(source, trajectory, machine, nozzle))
    assert load_gcode(target).timeline[-1].end == pytest.approx((5, 0, 5.3))


@pytest.mark.parametrize(
    "text",
    [
        "; INDEXED_TUBE_POSITION unknown\nG1 X1",
        "; INDEXED_TUBE_POSITION tip_from_center_v1\nG1 X1",
        "; INDEXED_TUBE_POINT {}\nG1 X1",
    ],
)
def test_unknown_or_missing_metadata_never_guesses(text):
    with pytest.raises(ValueError):
        parse_gcode(text)
