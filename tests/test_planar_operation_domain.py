from dataclasses import replace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.coordinates import GeometryReference
from five_axis_slicer.manufacturing.planar_parameters import (
    PlanarGeometrySelection,
    PlanarOperationDefinition,
    PlanarProcessParameters,
    planar_operation_semantic_sha256,
)
from five_axis_slicer.manufacturing.reference_rebind import (
    GeometryRebindResult,
    RebindStatus,
)
from five_axis_slicer.manufacturing.setup import NodeState
from five_axis_slicer.planar_operation_service import (
    configure_planar_operation,
    create_planar_operation,
    rebind_planar_operation_geometry,
)


def _body(identifier: str = "body-1") -> GeometryReference:
    return GeometryReference(identifier, "body", {"schema_version": 1})


@pytest.mark.parametrize(
    "operation_type",
    [
        "planar_region",
        "planar_zigzag",
        "planar_offset",
        "planar_thin_wall",
        "planar_spiral",
        "planar_support",
    ],
)
def test_planar_operation_json_round_trip_and_semantic_input(operation_type: str) -> None:
    operation = PlanarOperationDefinition(
        "op-1",
        "setup-1",
        operation_type=operation_type,
        geometry=PlanarGeometrySelection(_body()),
        parameters=PlanarProcessParameters(
            0.2,
            0.2,
            1.0,
            0.6,
            900.0,
            offset_pass_count=5,
            wall_thickness_mm=1.2,
            thin_wall_max_passes=2,
            spiral_samples_per_contour=80,
        ),
    )

    restored = PlanarOperationDefinition.from_json(operation.to_json())

    assert restored == operation
    assert restored.semantic_hash_input() == {
        "operation_id": "op-1",
        "name": "Planar Region",
        "operation_type": operation_type,
        "enabled": True,
        "geometry": operation.geometry.to_json(),
        "parameters": operation.parameters.to_json(),
    }
    assert len(planar_operation_semantic_sha256(restored)) == 64


@pytest.mark.parametrize(
    "kwargs",
    [
        {"first_layer_z_mm": float("nan")},
        {"layer_height_mm": 0.0},
        {"last_layer_z_mm": 0.1, "first_layer_z_mm": 0.2},
        {"bead_width_mm": -0.1},
        {"feedrate_mm_min": float("inf")},
        {"offset_pass_count": 0},
        {"offset_pass_count": True},
        {"thin_wall_max_passes": 0},
        {"spiral_samples_per_contour": 7},
        {"spiral_samples_per_contour": 8.0},
    ],
)
def test_planar_parameters_reject_non_finite_and_out_of_range_values(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        PlanarProcessParameters(**kwargs)


def test_geometry_selection_requires_a_stable_body_reference() -> None:
    with pytest.raises(ValueError, match="body geometry"):
        PlanarGeometrySelection(GeometryReference("face-1", "face"))

    assert (
        PlanarGeometrySelection.from_json(PlanarGeometrySelection(_body()).to_json()).body
        == _body()
    )


def test_create_and_configure_marks_only_changed_operation_dirty() -> None:
    created = create_planar_operation((), "setup-1", operation_id="op-1")
    assert created.state is NodeState.DIRTY
    assert created.dirty_reasons == ("operation_created",)

    configured = configure_planar_operation(
        created,
        lambda identifier, kind: _body(identifier),
        body_id="body-2",
        parameters=PlanarProcessParameters(last_layer_z_mm=2.0),
    )
    assert configured.geometry.body == _body("body-2")
    assert configured.state is NodeState.DIRTY
    assert {"operation_geometry_changed", "operation_parameters_changed"} <= set(
        configured.dirty_reasons
    )
    assert (
        configure_planar_operation(
            configured, lambda identifier, kind: _body(identifier), body_id="body-2"
        )
        == configured
    )


def test_rebind_failure_marks_operation_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    operation = replace(
        create_planar_operation((), "setup-1"), geometry=PlanarGeometrySelection(_body())
    )
    monkeypatch.setattr(
        "five_axis_slicer.planar_operation_service.rebind_geometry_reference",
        lambda *args, **kwargs: GeometryRebindResult(_body(), RebindStatus.MISSING),
    )

    rebound = rebind_planar_operation_geometry(operation, object(), object())

    assert rebound.state is NodeState.INVALID
    assert "geometry_rebind_failed" in rebound.dirty_reasons
