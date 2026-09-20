from __future__ import annotations

from pathlib import Path

import cadquery as cq

from five_axis_slicer.algorithms.freeform.layer_domain import audit_blade_layer_domain
from five_axis_slicer.models import BodyInfo, BoundingBox, CadModel


def _box_model() -> CadModel:
    shape = cq.Workplane("XY").box(20.0, 10.0, 2.0, centered=(True, True, False)).val()
    bounds = BoundingBox((-10.0, -5.0, 0.0), (10.0, 5.0, 2.0))
    body = BodyInfo("blade", 1, "Blade", (0.5, 0.5, 0.5), bounds=bounds, volume=400.0)
    return CadModel(
        Path("analytic.step"), "a" * 64, [body], [], {"blade": shape.wrapped}, {}, bounds=bounds
    )


def test_fixed_90_degree_domain_integrates_the_complete_solid() -> None:
    audit = audit_blade_layer_domain(
        _box_model(), "blade", layer_height_mm=0.5, convergence_stride=5
    )
    assert audit.a_angle_deg == 90.0
    assert audit.nonempty_layer_count == 20
    assert not audit.internal_empty_layer_ids
    assert audit.relative_volume_error < 1.0e-6
    assert audit.jacobian_min == 1.0
    assert audit.fk_position_error_mm <= 0.001
    assert audit.fk_angle_error_deg <= 0.001
    assert audit.geometry_feasible
    assert audit.machine_qualification_pending


def test_fixed_pose_outside_axis_limit_is_not_feasible() -> None:
    audit = audit_blade_layer_domain(
        _box_model(), "blade", layer_height_mm=1.0, a_limit_deg=(-45.0, 45.0)
    )
    assert not audit.fixed_a_within_limit
    assert not audit.geometry_feasible
