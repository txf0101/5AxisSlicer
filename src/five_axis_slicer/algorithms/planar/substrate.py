"""CAD-derived planar substrate; never infer a disk from a bounding box."""

from __future__ import annotations

import math

from ...manufacturing.toolpath import GeneratedToolpath
from ...models import CadModel
from .feature_fill import FeatureFillParameters, plan_feature_fill
from .feature_toolpath import FeatureToolpathParameters, generate_feature_toolpath
from .region import slice_planar_layers


def generate_substrate_toolpath(
    model: CadModel,
    body_id: str,
    operation_id: str,
    parameters: FeatureToolpathParameters,
) -> GeneratedToolpath:
    """Slice a selected +Z substrate with two walls, skins and 20% infill.

    This entry point assumes the caller has established the +Z build pose.
    Equal thickness layers fit the entire height without overextruding a short
    final layer. Actual CAD sections retain holes and non-circular outlines.
    """
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    shape = model.shapes.get(body_id)
    if shape is None:
        raise ValueError("substrate body has no CAD shape")
    bounds = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, bounds, False, False)
    _, _, lower, _, _, upper = bounds.Get()
    height = upper - lower
    if not math.isfinite(height) or height <= 0:
        raise ValueError("substrate has no finite positive build height")
    count = math.ceil(height / parameters.layer_height_mm - 1.0e-10)
    step = height / max(1, count)
    layers = slice_planar_layers(
        model,
        (body_id,),
        first_layer_z_mm=lower + step,
        last_layer_z_mm=upper,
        layer_height_mm=step,
        sample_segments=128,
    )
    if any(not layer.regions for layer in layers):
        raise ValueError("substrate contains an empty build layer")
    filled = plan_feature_fill(
        layers, FeatureFillParameters(bead_width_mm=parameters.bead_width_mm)
    )
    from dataclasses import replace

    return generate_feature_toolpath(
        operation_id, filled, replace(parameters, layer_height_mm=step), stage_prefix="base"
    )
