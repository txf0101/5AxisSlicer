from pathlib import Path

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
import pytest

from five_axis_slicer.algorithms.tube.wedge_footprint import cad_wedge_footprint
from five_axis_slicer.algorithms.tube.wedge_plan import WedgeBoundaryPlane, WedgeRegionBoundary
from five_axis_slicer.models import CadModel


def model(shape):
    return CadModel(Path("analytic.step"), "analytic", [], [], {"body": shape}, {})


def boundary(z0, z1, exit_normal=(0, 0, 1)):
    return WedgeRegionBoundary("r", WedgeBoundaryPlane((0, 0, z0), (0, 0, 1)),
                               WedgeBoundaryPlane((0, 0, z1), exit_normal))


def test_box_region_projection_preserves_full_section():
    result = cad_wedge_footprint(model(BRepPrimAPI_MakeBox(2, 3, 10).Shape()),
                                 "body", boundary(2, 4), (0, 0, 1))
    assert min(p[0] for p in result.vertices) == pytest.approx(0, abs=1e-6)
    assert max(p[0] for p in result.vertices) == pytest.approx(2, abs=1e-6)
    assert max(p[1] for p in result.vertices) == pytest.approx(3, abs=1e-6)
    assert all(p[2] == 2 for p in result.vertices)
    assert result.positive_boundary_columns


def test_cylinder_extrema_do_not_depend_on_mesh_sampling():
    result = cad_wedge_footprint(model(BRepPrimAPI_MakeCylinder(2, 10).Shape()),
                                 "body", boundary(1, 3), (0, 0, 1))
    assert max(p[0] for p in result.vertices) == pytest.approx(2, abs=1e-6)
    assert min(p[1] for p in result.vertices) == pytest.approx(-2, abs=1e-6)


def test_sloping_exit_reports_overbounding_degenerate_corner():
    result = cad_wedge_footprint(model(BRepPrimAPI_MakeBox(2, 3, 10).Shape()),
                                 "body", boundary(0, 1, (1, 0, 1)), (0, 0, 1))
    assert max(p[0] for p in result.vertices) == pytest.approx(1, abs=1e-6)
    assert not result.positive_boundary_columns


def test_empty_wedge_rejected():
    with pytest.raises(ValueError, match="empty"):
        cad_wedge_footprint(model(BRepPrimAPI_MakeBox(2, 3, 1).Shape()),
                            "body", boundary(3, 4), (0, 0, 1))


def test_missing_body_rejected():
    with pytest.raises(ValueError, match="missing"):
        cad_wedge_footprint(model(BRepPrimAPI_MakeBox(1, 1, 1).Shape()),
                            "absent", boundary(0, 1), (0, 0, 1))
