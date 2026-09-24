"""Shared product adapter for bounded Freeform solid-fill algorithms."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from ..algorithms.fan.radial_solid_fill import (
    RadialSolidBladeSelection,
    RadialSolidFillAudit,
    RadialSolidFillParameters,
    generate_radial_solid_fill,
)
from ..algorithms.freeform.spherical_domain import SphericalChart
from ..algorithms.freeform.spherical_fill import (
    SphericalFillAudit,
    SphericalFillParameters,
    generate_spherical_solid_fill,
)
from ..algorithms.freeform.surface_solid_fill import (
    SurfaceSolidBodySelection,
    SurfaceSolidFillAudit,
    SurfaceSolidFillParameters,
    generate_surface_solid_fill,
)
from ..algorithms.planar.feature_toolpath import FeatureToolpathParameters
from ..algorithms.planar.substrate import generate_substrate_toolpath
from ..manufacturing.coordinates import RigidTransform
from ..manufacturing.freeform_parameters import FreeformOperationDefinition
from ..manufacturing.freeform_solid_parameters import (
    RadialSolidGeometrySelection,
    SphericalSolidGeometrySelection,
    SurfaceSolidGeometrySelection,
)
from ..manufacturing.material_plan import apply_material_plan
from ..manufacturing.toolpath import GeneratedToolpath
from ..models import CadModel
from .toolpath_sequence import merge_toolpath_sequence, transform_toolpath

CancelCheck = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class SolidFillPlan:
    """Inspectable summary of one generated solid-fill operation."""

    operation_id: str
    operation_type: str
    source_toolpath_ids: tuple[str, ...]
    audit: Mapping[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "source_toolpath_ids": list(self.source_toolpath_ids),
            "audit": dict(self.audit),
        }


def generate_solid_fill_product_path(
    model: CadModel,
    operation: FreeformOperationDefinition,
    *,
    T_build_from_source: RigidTransform,
    cancelled: CancelCheck | None = None,
) -> tuple[SolidFillPlan, GeneratedToolpath]:
    """Generate any persisted solid-fill operation through one domain entry point."""

    geometry = operation.solid_geometry
    parameters = operation.solid_parameters
    if geometry is None or parameters is None:
        raise ValueError("solid-fill operation requires selected geometry and parameters")
    if (
        not isinstance(geometry, SurfaceSolidGeometrySelection)
        and parameters.surface_growth_strategy != "surface_thickness"
    ):
        raise ValueError("root-edge outward growth requires surface solid geometry")
    _checkpoint(cancelled)
    raw_paths: tuple[GeneratedToolpath, ...]
    audit: SphericalFillAudit | SurfaceSolidFillAudit | RadialSolidFillAudit
    if isinstance(geometry, SphericalSolidGeometrySelection):
        raw, audit = generate_spherical_solid_fill(
            model,
            tuple(item.object_id for item in geometry.bodies),
            operation.operation_id,
            SphericalFillParameters(
                substrate_radius_mm=parameters.substrate_radius_mm,
                radial_thickness_mm=parameters.radial_thickness_mm,
                layer_height_mm=parameters.layer_height_mm,
                bead_width_mm=parameters.bead_width_mm,
                deposition_feedrate_mm_min=parameters.deposition_feedrate_mm_min,
                travel_feedrate_mm_min=parameters.travel_feedrate_mm_min,
                retract_length_mm=parameters.retract_length_mm,
                sample_segments=parameters.sample_segments,
            ),
            chart=SphericalChart(geometry.center_mm),
            cancelled=cancelled,
        )
        raw_paths = (raw,)
    elif isinstance(geometry, SurfaceSolidGeometrySelection):
        raw_paths, audit = generate_surface_solid_fill(
            model,
            tuple(
                SurfaceSolidBodySelection(
                    item.body.object_id,
                    item.surface_face.object_id,
                    item.opposite_face.object_id,
                    item.root_edge.object_id,
                    None if geometry.substrate_body is None else geometry.substrate_body.object_id,
                )
                for item in geometry.bodies
            ),
            operation.operation_id,
            SurfaceSolidFillParameters(
                solid_thickness_mm=parameters.solid_thickness_mm,
                layer_height_mm=parameters.layer_height_mm,
                bead_width_mm=parameters.bead_width_mm,
                path_spacing_mm=parameters.path_spacing_mm,
                sampling_step_mm=parameters.sampling_step_mm,
                deposition_feedrate_mm_min=parameters.deposition_feedrate_mm_min,
                travel_feedrate_mm_min=parameters.travel_feedrate_mm_min,
                retract_length_mm=parameters.retract_length_mm,
                metric_across_samples=parameters.metric_across_samples,
                metric_along_samples=parameters.metric_along_samples,
                surface_growth_strategy=parameters.surface_growth_strategy,
            ),
            cancelled=cancelled,
        )
    elif isinstance(geometry, RadialSolidGeometrySelection):
        _require_source_z_axis(geometry)
        raw_paths, audit = generate_radial_solid_fill(
            model,
            tuple(
                RadialSolidBladeSelection(
                    item.body.object_id,
                    geometry.hub_body.object_id,
                    item.root_face.object_id,
                    item.outer_face.object_id,
                )
                for item in geometry.blades
            ),
            operation.operation_id,
            RadialSolidFillParameters(
                layer_height_mm=parameters.layer_height_mm,
                bead_width_mm=parameters.bead_width_mm,
                sampling_step_mm=parameters.sampling_step_mm,
                deposition_feedrate_mm_min=parameters.deposition_feedrate_mm_min,
                travel_feedrate_mm_min=parameters.travel_feedrate_mm_min,
                retract_length_mm=parameters.retract_length_mm,
                sample_segments=parameters.sample_segments,
                face_metric_samples=parameters.face_metric_samples,
            ),
            cancelled=cancelled,
        )
    else:  # pragma: no cover - guarded by the operation contract
        raise ValueError(f"unsupported solid-fill geometry: {type(geometry).__name__}")

    _checkpoint(cancelled)
    substrate = geometry.substrate_body
    if substrate is not None:
        base_path = generate_substrate_toolpath(
            model,
            substrate.object_id,
            f"{operation.operation_id}-base",
            FeatureToolpathParameters(
                bead_width_mm=parameters.bead_width_mm,
                layer_height_mm=parameters.layer_height_mm,
                deposition_feedrate_mm_min=parameters.deposition_feedrate_mm_min,
                travel_feedrate_mm_min=parameters.travel_feedrate_mm_min,
                retract_length_mm=parameters.retract_length_mm,
            ),
        )
        raw_paths = (base_path, *raw_paths)
    source_ids = tuple(path.toolpath_id for path in raw_paths)
    source_path = (
        raw_paths[0]
        if len(raw_paths) == 1
        else merge_toolpath_sequence(
            operation.operation_id,
            raw_paths,
            safe_clearance_mm=parameters.safe_clearance_mm,
            travel_feedrate_mm_min=parameters.travel_feedrate_mm_min,
            retract_length_mm=parameters.retract_length_mm,
        )
    )
    toolpath = transform_toolpath(source_path, T_build_from_source)
    if operation.material_plan is not None:
        toolpath = apply_material_plan(toolpath, operation.material_plan)
    return (
        SolidFillPlan(
            operation.operation_id,
            operation.operation_type,
            source_ids,
            asdict(audit),
        ),
        toolpath,
    )


def _require_source_z_axis(geometry: RadialSolidGeometrySelection) -> None:
    tolerance = 1.0e-9
    if any(abs(value) > tolerance for value in geometry.axis_origin_mm) or any(
        abs(actual - expected) > tolerance
        for actual, expected in zip(geometry.axis_direction, (0.0, 0.0, 1.0), strict=True)
    ):
        raise ValueError(
            "radial_solid_fill currently requires the selected rotation axis to be source +Z "
            "through the source origin; use the model-to-build transform for machine placement"
        )


def _checkpoint(cancelled: CancelCheck | None) -> None:
    if cancelled is not None and cancelled():
        from .indexed_tube import GenerationCancelled

        raise GenerationCancelled("solid-fill product generation cancelled")


__all__ = ["SolidFillPlan", "generate_solid_fill_product_path"]
