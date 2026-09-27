import numpy as np
from dataclasses import replace

from five_axis_slicer.models import BuildSurfaceOverlay
from five_axis_slicer.opengl_scene import build_surface_grid, build_surface_triangles
from five_axis_slicer.build_surface_presentation import source_build_surface
from five_axis_slicer.manufacturing.own_printer import default_printer_setup
from five_axis_slicer.manufacturing.coordinates import (
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
    RigidTransform,
)


def test_circle_grid_stays_on_rotated_150_mm_platform():
    surface = BuildSurfaceOverlay(
        "plate",
        "circle",
        origin=(4.0, 7.0, 9.0),
        x_axis=(0.0, 2.0, 0.0),
        y_axis=(0.0, 0.0, 3.0),
        diameter_mm=150.0,
    )
    grid = np.asarray(build_surface_grid(surface))
    local = grid - surface.origin
    np.testing.assert_allclose(local[:, 0], 0.0)
    np.testing.assert_allclose(np.linalg.norm(local, axis=1), 75.0)
    assert len(grid) == 60
    triangles = np.asarray(build_surface_triangles(surface)).reshape(-1, 3, 3)
    area = (
        np.linalg.norm(
            np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1
        ).sum()
        / 2
    )
    assert abs(area / (np.pi * 75**2) - 1) < 0.002


def test_rectangle_grid_respects_unequal_dimensions():
    grid = np.asarray(
        build_surface_grid(BuildSurfaceOverlay("plate", "rectangle", width_mm=40.0, depth_mm=20.0))
    )
    np.testing.assert_allclose(grid.min(axis=0), (-20.0, -10.0, 0.0))
    np.testing.assert_allclose(grid.max(axis=0), (20.0, 10.0, 0.0))


def test_blank_project_shows_default_platform_but_unplaced_model_does_not():
    setup = default_printer_setup()
    plate = source_build_surface(setup, has_model=False)
    assert plate is not None and plate.diameter_mm == 150
    assert source_build_surface(setup, has_model=True) is None


def test_placed_platform_uses_source_frame_and_hides_stale_placement():
    build = CoordinateFrameDefinition.from_references(
        "build",
        "Build",
        PointReference("numeric", (100, 200, 300), confirmed=True),
        DirectionReference("numeric", (0, 0, 1), confirmed=True),
        DirectionReference("numeric", (0, 1, 0), confirmed=True),
    )
    placement = RigidTransform.from_rotation_translation(
        ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
        (10, 20, 30),
        source_frame="build",
        target_frame="build_plate_mount",
    )
    setup = replace(
        default_printer_setup(),
        build_coordinate_system=build,
        mount_datum_id="build_plate_mount",
        T_mount_from_build=placement,
        dirty_nodes=frozenset(),
    )
    plate = source_build_surface(setup, has_model=True)
    assert plate is not None
    np.testing.assert_allclose(plate.origin, (130, 190, 320))
    np.testing.assert_allclose(plate.x_axis, (0, 1, 0))
    np.testing.assert_allclose(plate.y_axis, (0, 0, -1))
    for field in ("dirty_nodes", "draft_nodes", "invalid_nodes"):
        for node in ("placement", "build_cs"):
            stale = replace(setup, **{field: frozenset({node})})
            assert source_build_surface(stale, has_model=True) is None
