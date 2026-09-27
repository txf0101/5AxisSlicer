from dataclasses import replace
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.resources import NozzleProfile
from five_axis_slicer.manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from five_axis_slicer.manufacturing.tube_tcp import indexed_centerline_to_tcp
from five_axis_slicer.validation.indexed_tube import CollisionBox, _collision_issues


def test_nozzle_collision_uses_tip_above_material_center():
    approach = ToolpathPoint(
        "p1", (0, 0, 5.1), (1, 0, 0), (0, 0, -1), "op", "s", "l", "r", "approach"
    )
    deposition = replace(
        approach,
        point_id="p2",
        position=(1, 0, 5.1),
        point_type="deposition",
        extrusion_role="thin_wall",
        bead_width_mm=0.6,
        layer_height_mm=0.2,
        material_volume_mm3=0.12,
    )
    path = GeneratedToolpath("path", "op", points=(approach, deposition))
    nozzle = NozzleProfile(
        resource_id="n",
        display_name="n",
        orifice_diameter_mm=0.4,
        filament_diameter_mm=1.75,
        interface="M6",
        length_mm=1,
        outer_profile_rz_mm=((0.2, 0), (0.2, 1)),
    )
    fixture = CollisionBox("fixture", "fixture", (-10, -10, 0), (10, 10, 5.15))
    raw, _ = _collision_issues(path, nozzle, (fixture,), 0.1, check_ipw=False)
    corrected, _ = _collision_issues(
        path,
        nozzle,
        (fixture,),
        0.1,
        check_ipw=False,
        nozzle_toolpath=indexed_centerline_to_tcp(path),
    )
    assert raw
    assert not corrected
    assert path.points[1].position[2] == 5.1
