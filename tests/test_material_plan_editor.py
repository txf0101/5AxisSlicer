"""Material table stays equivalent to the validated public plan schema."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from five_axis_slicer.manufacturing.material_plan import MaterialPlan  # noqa: E402
from five_axis_slicer.manufacturing.coordinates import GeometryReference  # noqa: E402
from five_axis_slicer.manufacturing.freeform_solid_parameters import (  # noqa: E402
    RadialSolidBladeGeometry,
    RadialSolidGeometrySelection,
    SphericalSolidGeometrySelection,
    SurfaceSolidBodyGeometry,
    SurfaceSolidGeometrySelection,
)
from five_axis_slicer.material_plan_editor import (  # noqa: E402
    MaterialPlanEditor,
    stage_candidates_for_operation,
)


APP = QApplication.instance() or QApplication([])


def test_table_creates_three_colour_stage_mapping_and_preserves_advanced_fields() -> None:
    source = {
        "schema_version": 1,
        "plan_id": "fan-colours",
        "channels": [{
            "channel_id": "T0", "material_id": "PLA-red", "tool_command": "T0",
            "nozzle_temperature_c": 195, "retract_length_mm": 1,
            "unload_length_mm": 11, "load_length_mm": 20,
            "purge_length_mm": 8, "purge_feedrate_mm_min": 90,
        }],
        "regions": [{"stage_prefix": "op01-", "region_id": "*", "channel_id": "T0"}],
        "sensor_required": False,
        "context": {"note": "example"},
    }
    editor = MaterialPlanEditor(source)
    editor.add_channel()
    editor.channels_table.item(1, 1).setText("PLA-blue")
    editor.channels_table.item(1, 4).setText("12")
    editor.add_region()
    editor.regions_table.item(1, 0).setText("op02-")
    editor.regions_table.item(1, 2).setText("T1")
    editor._submit()
    assert editor.result_payload is not None
    plan = MaterialPlan.from_json(editor.result_payload)
    assert [region.channel_id for region in plan.regions] == ["T0", "T1"]
    assert plan.channels[0].purge_feedrate_mm_min == 90
    assert plan.channels[1].unload_length_mm == 12
    assert plan.sensor_required is False
    assert dict(plan.context) == {"note": "example"}
    assert source["channels"][0]["purge_feedrate_mm_min"] == 90
    editor.close()


def test_table_rejects_unknown_region_channel_without_emitting_plan() -> None:
    editor = MaterialPlanEditor()
    editor.add_channel()
    editor.add_region()
    editor.regions_table.item(0, 2).setText("T9")
    editor._submit()
    assert editor.result_payload is None
    assert "declared channel" in editor.error_label.text()
    editor.regions_table.item(0, 2).setText("T0")
    editor._submit()
    assert editor.result_payload is not None
    editor.close()


def test_selected_radial_bodies_offer_ordered_stages_without_typing_internal_ids() -> None:
    def ref(name: str, kind: str) -> GeometryReference:
        return GeometryReference(name, kind, {"identity": name})

    geometry = RadialSolidGeometrySelection(
        ref("hub", "body"),
        tuple(
            RadialSolidBladeGeometry(
                ref(f"blade-{index}", "body"),
                ref(f"root-{index}", "face"),
                ref(f"outer-{index}", "face"),
            )
            for index in range(1, 4)
        ),
        substrate_body=ref("base", "body"),
    )
    choices = stage_candidates_for_operation(SimpleNamespace(solid_geometry=geometry))
    assert [item[1] for item in choices] == ["op01-", "op02-", "op03-", "op04-"]
    assert "blade-1" in choices[1][0]
    editor = MaterialPlanEditor(stage_candidates=choices)
    editor.stage_combo.setCurrentIndex(2)
    editor.add_suggested_region()
    editor.add_suggested_region()
    assert editor.channels_table.rowCount() == 1
    assert editor.regions_table.rowCount() == 1
    assert editor.regions_table.item(0, 0).text() == "op03-"
    assert editor.regions_table.item(0, 1).text() == "*"
    editor.close()


def test_generated_surface_stage_is_selectable_and_custom_region_still_available() -> None:
    toolpath = SimpleNamespace(points=(
        SimpleNamespace(point_type="travel", stage_id="operation-transition"),
        SimpleNamespace(point_type="deposition", stage_id="surface-1", region_id="path-1"),
        SimpleNamespace(point_type="deposition", stage_id="surface-1", region_id="path-2"),
        SimpleNamespace(point_type="deposition", stage_id="surface-2", region_id="path-3"),
    ))
    choices = stage_candidates_for_operation(
        SimpleNamespace(solid_geometry=None), toolpath=toolpath, language="en"
    )
    assert [item[1] for item in choices] == ["surface-1", "surface-2"]
    editor = MaterialPlanEditor(stage_candidates=choices, language="en")
    editor.stage_combo.setCurrentIndex(1)
    editor.add_suggested_region()
    assert editor.regions_table.item(0, 0).text() == "surface-2"
    editor.add_region()
    assert editor.regions_table.item(1, 0).text() == ""
    editor.close()


def test_spherical_and_root_outward_regions_use_stable_body_ids() -> None:
    def ref(name: str, kind: str) -> GeometryReference:
        return GeometryReference(name, kind, {"identity": name})

    sphere = SimpleNamespace(
        solid_geometry=SphericalSolidGeometrySelection(
            (ref("logo-a", "body"), ref("logo-b", "body")),
            substrate_body=ref("base", "body"),
        ),
        solid_parameters=SimpleNamespace(surface_growth_strategy="surface_thickness"),
    )
    assert stage_candidates_for_operation(sphere) == (
        ("底座", "op01-", "*"),
        ("球面实体 1 · logo-a", "", "logo-a"),
        ("球面实体 2 · logo-b", "", "logo-b"),
    )
    surface = SimpleNamespace(
        solid_geometry=SurfaceSolidGeometrySelection((
            SurfaceSolidBodyGeometry(
                ref("blade-a", "body"), ref("top", "face"),
                ref("bottom", "face"), ref("root", "edge"),
            ),
        )),
        solid_parameters=SimpleNamespace(surface_growth_strategy="root_edge_outward"),
    )
    assert stage_candidates_for_operation(surface) == (
        ("曲面实体 1 · blade-a", "", "blade-a"),
    )
