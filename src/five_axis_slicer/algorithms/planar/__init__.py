"""Planar slicing primitives shared by the Planar workbench operations."""

from .region import PlanarRegion, PlanarSectionError, PlanarSliceLayer, slice_planar_layers
from .zigzag import PlanarZigzagError, ZigzagParameters, generate_zigzag_toolpath
from .thin_wall import ThinWallParameters, generate_open_wall_toolpath, thin_wall_pass_count
from .spiral import PlanarSpiralError, SpiralParameters, generate_spiral_toolpath
from .offset import (
    OffsetDiagnostic,
    OffsetResult,
    PlanarOffsetError,
    inward_offsets,
    inward_offsets_for_regions,
)
from .support import (
    PlanarSupportError,
    SupportDiagnostic,
    SupportLayer,
    SupportParameters,
    SupportPlan,
    generate_support_plan,
    generate_support_toolpath,
)

__all__ = [
    "PlanarRegion",
    "PlanarSectionError",
    "PlanarSliceLayer",
    "slice_planar_layers",
    "PlanarZigzagError",
    "ZigzagParameters",
    "generate_zigzag_toolpath",
    "ThinWallParameters",
    "generate_open_wall_toolpath",
    "thin_wall_pass_count",
    "PlanarSpiralError",
    "SpiralParameters",
    "generate_spiral_toolpath",
    "OffsetDiagnostic",
    "OffsetResult",
    "PlanarOffsetError",
    "inward_offsets",
    "inward_offsets_for_regions",
    "PlanarSupportError",
    "SupportDiagnostic",
    "SupportLayer",
    "SupportParameters",
    "SupportPlan",
    "generate_support_plan",
    "generate_support_toolpath",
]
