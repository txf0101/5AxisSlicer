"""Adapt a prescribed Rotary plan to the shared generated Toolpath contract."""

from __future__ import annotations

from collections.abc import Callable

from ...manufacturing.coordinates import RigidTransform
from ...manufacturing.rotary_parameters import RotaryOperationDefinition
from ...manufacturing.toolpath import GeneratedToolpath, ToolpathPoint
from .geometry import RotaryPlan, RotaryPlanningError, build_rotary_plan

CancelCheck = Callable[[], bool]


def generate_rotary_toolpath(
    plan: RotaryPlan,
    operation: RotaryOperationDefinition,
) -> GeneratedToolpath:
    """Convert plan points one-to-one without changing prescribed angles."""

    if plan.operation_id != operation.operation_id:
        raise RotaryPlanningError("rotary.plan_operation_mismatch")
    if plan.operation_type != operation.operation_type:
        raise RotaryPlanningError("rotary.plan_type_mismatch")
    points = tuple(
        ToolpathPoint(
            point_id=item.point_id,
            position=item.position,
            tangent=item.tangent,
            nozzle_axis=item.nozzle_axis,
            operation_id=operation.operation_id,
            stage_id=item.stage_id,
            layer_id=item.layer_id,
            region_id=item.region_id,
            point_type=item.point_type,
            extrusion_role=item.extrusion_role,
            surface_normal=item.surface_normal,
            feedrate_mm_min=item.feedrate_mm_min,
            bead_width_mm=item.bead_width_mm,
            layer_height_mm=item.layer_height_mm,
            material_volume_mm3=item.material_volume_mm3,
        )
        for item in plan.points
    )
    if len(points) < 2:
        raise RotaryPlanningError("rotary.toolpath_empty")
    return GeneratedToolpath(
        f"{operation.operation_id}-{operation.operation_type}-v1",
        operation.operation_id,
        coordinate_frame="workpiece_build",
        points=points,
        events=plan.events,
    )


def generate_rotary_operation_toolpath(
    operation: RotaryOperationDefinition,
    *,
    T_build_from_source: RigidTransform | None = None,
    cancelled: CancelCheck | None = None,
) -> tuple[RotaryPlan, GeneratedToolpath]:
    """Convenience entry point used by GUI, script and HTTP command adapters."""

    plan = build_rotary_plan(
        operation,
        T_build_from_source=T_build_from_source,
        cancelled=cancelled,
    )
    return plan, generate_rotary_toolpath(plan, operation)


__all__ = ["generate_rotary_operation_toolpath", "generate_rotary_toolpath"]
