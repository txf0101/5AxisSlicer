"""Resolve the physical platform into the source frame used by workbench viewers."""

from typing import Any

from .manufacturing.machine import MachineProfile
from .manufacturing.setup import BUILD_CS_NODE, PLACEMENT_NODE, ManufacturingSetup, NodeState
from .models import BuildSurfaceOverlay


def source_build_surface(
    setup: ManufacturingSetup, *, has_model: bool
) -> BuildSurfaceOverlay | None:
    if setup.machine is None:
        return None
    profile = MachineProfile.from_json(setup.machine.payload)
    mount_id = setup.mount_datum_id
    if mount_id is None and not has_model and len(profile.mount_datums) == 1:
        mount_id = profile.mount_datums[0].mount_id
    mount = profile.mount_map.get(mount_id or "")
    if mount is None or mount.build_surface_id not in profile.build_surface_map:
        return None
    surface = profile.build_surface_map[mount.build_surface_id]
    if has_model:
        report = setup.validation_report()
        if any(
            report.state_for(node) is not NodeState.VALID
            for node in (BUILD_CS_NODE, PLACEMENT_NODE)
        ):
            return None
        build = setup.build_coordinate_system
        placement = setup.T_mount_from_build
        if build is None or not build.is_valid or placement is None:
            return None
        transform = build.T_target_from_source.inverse() @ placement.inverse()
    else:
        transform = profile.mount_transform(mount.mount_id)
    return BuildSurfaceOverlay(
        surface.surface_id,
        surface.shape,
        origin=transform.transform_point((0.0, 0.0, 0.0)),
        x_axis=transform.transform_vector((1.0, 0.0, 0.0)),
        y_axis=transform.transform_vector((0.0, 1.0, 0.0)),
        width_mm=surface.width_mm,
        depth_mm=surface.depth_mm,
        diameter_mm=surface.diameter_mm,
    )


def refresh_source_platform(page: Any) -> None:
    page.viewer.set_build_surface(
        source_build_surface(page.controller.setup, has_model=page.controller.cad_model is not None)
    )
