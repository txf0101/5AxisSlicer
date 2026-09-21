from __future__ import annotations

import cadquery as cq
import pytest

from five_axis_slicer.freeform_operation_service import (
    configure_freeform_solid_operation,
    create_freeform_operation,
)
from five_axis_slicer.manufacturing.coordinates import GeometryReference, RigidTransform
from five_axis_slicer.manufacturing.freeform_solid_parameters import (
    RadialSolidBladeGeometry,
    RadialSolidGeometrySelection,
    SolidFillProcessParameters,
    SphericalSolidGeometrySelection,
    SurfaceSolidBodyGeometry,
    SurfaceSolidGeometrySelection,
    solid_geometry_from_json,
)
from five_axis_slicer.manufacturing.freeform_parameters import FreeformOperationDefinition
from five_axis_slicer.manufacturing.setup import NodeState
from five_axis_slicer.postprocessing.freeform_solid_product import (
    generate_solid_fill_product_path,
)
from five_axis_slicer.step_loader import load_step


def _ref(object_id: str, geometry_type: str) -> GeometryReference:
    return GeometryReference(object_id, geometry_type, {"identity": object_id})


@pytest.mark.parametrize(
    "selection",
    (
        SphericalSolidGeometrySelection((_ref("logo-1", "body"),), (1.0, 2.0, 3.0)),
        SurfaceSolidGeometrySelection(
            (
                SurfaceSolidBodyGeometry(
                    _ref("blade", "body"),
                    _ref("surface", "face"),
                    _ref("opposite", "face"),
                    _ref("root", "edge"),
                ),
            )
        ),
        RadialSolidGeometrySelection(
            _ref("hub", "body"),
            (
                RadialSolidBladeGeometry(
                    _ref("blade", "body"),
                    _ref("root", "face"),
                    _ref("outer", "face"),
                ),
            ),
            axis_direction=(0.0, 0.0, 2.0),
        ),
    ),
)
def test_solid_geometry_roundtrip_keeps_stable_roles(selection) -> None:
    assert solid_geometry_from_json(selection.to_json()) == selection


def test_solid_geometry_rejects_duplicate_bodies_and_wrong_role_types() -> None:
    body = _ref("same", "body")
    with pytest.raises(ValueError, match="non-empty and unique"):
        SphericalSolidGeometrySelection((body, body))
    with pytest.raises(ValueError, match="root_edge must be a edge"):
        SurfaceSolidBodyGeometry(body, _ref("a", "face"), _ref("b", "face"), body)
    with pytest.raises(ValueError, match="axis_direction must be non-zero"):
        RadialSolidGeometrySelection(
            _ref("hub", "body"),
            (RadialSolidBladeGeometry(body, _ref("r", "face"), _ref("o", "face")),),
            axis_direction=(0.0, 0.0, 0.0),
        )


def test_solid_process_parameters_roundtrip_and_spacing_guard() -> None:
    parameters = SolidFillProcessParameters(
        substrate_radius_mm=40.0,
        radial_thickness_mm=0.5,
        solid_thickness_mm=1.0,
    )
    assert SolidFillProcessParameters.from_json(parameters.to_json()) == parameters
    with pytest.raises(ValueError, match="path_spacing_mm"):
        SolidFillProcessParameters(bead_width_mm=0.4, path_spacing_mm=0.5)


def test_freeform_operation_roundtrip_keeps_solid_contract() -> None:
    geometry = SphericalSolidGeometrySelection((_ref("logo", "body"),), (1.0, 2.0, 3.0))
    operation = FreeformOperationDefinition(
        "solid-1",
        "setup-1",
        "Logo fill",
        "spherical_solid_fill",
        NodeState.DIRTY,
        ("operation_created",),
        solid_geometry=geometry,
        solid_parameters=SolidFillProcessParameters(substrate_radius_mm=40.0),
    )
    assert FreeformOperationDefinition.from_json(operation.to_json()) == operation
    assert operation.semantic_hash_input()["solid_geometry"] == geometry.to_json()


def test_solid_operation_rejects_mismatched_geometry_type() -> None:
    geometry = SphericalSolidGeometrySelection((_ref("logo", "body"),))
    with pytest.raises(ValueError, match="solid geometry type"):
        FreeformOperationDefinition(
            "solid-1",
            "setup-1",
            operation_type="radial_solid_fill",
            solid_geometry=geometry,
        )


def test_spherical_product_adapter_uses_selection_and_build_transform(tmp_path) -> None:
    base = cq.Workplane("XY").sphere(10)
    feature = (
        cq.Workplane("XY")
        .sphere(10.6)
        .intersect(cq.Workplane("XY").box(6, 4, 20).translate((0, 0, 5)))
        .cut(cq.Workplane("XY").sphere(10))
    )
    source = tmp_path / "solid-product.step"
    cq.exporters.export(cq.Compound.makeCompound([base.val(), feature.val()]), str(source))
    model = load_step(source)
    selected = min(model.bodies, key=lambda item: item.volume or 0.0)
    substrate = max(model.bodies, key=lambda item: item.volume or 0.0)
    operation = create_freeform_operation(
        (), "setup", "spherical_solid_fill", operation_id="solid-product"
    )
    operation = configure_freeform_solid_operation(
        operation,
        model,
        geometry={
            "body_ids": [selected.body_id],
            "center_mm": [0, 0, 0],
            "substrate_body_id": substrate.body_id,
        },
        parameters=SolidFillProcessParameters(
            substrate_radius_mm=10.0,
            radial_thickness_mm=0.6,
            sample_segments=32,
        ),
    )
    plan, path = generate_solid_fill_product_path(
        model,
        operation,
        T_build_from_source=RigidTransform.from_translation(
            (20, 30, 40), source_frame="model", target_frame="build"
        ),
    )

    assert plan.operation_type == "spherical_solid_fill"
    assert plan.audit["layer_count"] == 3
    assert len(plan.source_toolpath_ids) == 2
    assert path.operation_id == operation.operation_id
    assert path.coordinate_frame == "workpiece_build"
    assert min(point.position[2] for point in path.points) >= 30.0
