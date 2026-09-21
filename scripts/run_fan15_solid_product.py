"""Thin real-model regression driver for the public solid-fill product chain."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, TypedDict, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.freeform_operation_service import (  # noqa: E402
    configure_freeform_solid_operation,
    create_freeform_operation,
)
from five_axis_slicer.manufacturing.controller_profile import (  # noqa: E402
    OWN_AC_OFFLINE_CONTROLLER,
)
from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.freeform_solid_parameters import (  # noqa: E402
    SolidFillProcessParameters,
)
from five_axis_slicer.manufacturing.own_printer import own_ac_profile  # noqa: E402
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_PLA_175,
    NozzleProfile,
    ResourceSnapshot,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    ManufacturingObjectAssignments,
    ManufacturingSetup,
)
from five_axis_slicer.models import CadModel, SelectionState  # noqa: E402
from five_axis_slicer.project_io import load_project, save_project  # noqa: E402
from five_axis_slicer.postprocessing.freeform_product import (  # noqa: E402
    export_freeform_product,
    generate_freeform_product,
)
from five_axis_slicer.postprocessing.thermal_program import (  # noqa: E402
    ThermalProgramParameters,
)
from five_axis_slicer.step_loader import load_step  # noqa: E402


class CaseConfig(TypedDict):
    source: Path
    operation_type: str
    geometry: Callable[[CadModel], dict[str, Any]]
    parameters: dict[str, float]


CASES: dict[str, CaseConfig] = {
    "logo": {
        "source": ROOT / "example/球形NEU校徽/球形测试件.STEP",
        "operation_type": "spherical_solid_fill",
        "geometry": lambda model: {
            "body_ids": [item.body_id for item in model.bodies if item.body_id != "body_001"],
            "center_mm": [0.0, 0.0, 0.0],
            "substrate_body_id": "body_001",
        },
        "parameters": {
            "substrate_radius_mm": 40.0,
            "radial_thickness_mm": 0.5,
        },
    },
    "impeller": {
        "source": ROOT / "example/叶轮/叶轮.stp",
        "operation_type": "surface_solid_fill",
        "geometry": lambda _model: {
            "substrate_body_id": "body_001",
            "bodies": [
                {
                    "body_id": f"body_{index:03d}",
                    "surface_face_id": f"body_{index:03d}_face_0006",
                    "opposite_face_id": f"body_{index:03d}_face_0005",
                    "root_edge_id": f"body_{index:03d}_edge_0011",
                }
                for index in range(2, 10)
            ],
        },
        "parameters": {"solid_thickness_mm": 1.0},
    },
    "three_leaf": {
        "source": ROOT / "example/三叶扇/Supportless_sample.stp",
        "operation_type": "radial_solid_fill",
        "geometry": lambda _model: {
            "hub_body_id": "body_001",
            "substrate_body_id": "body_001",
            "axis_origin_mm": [0.0, 0.0, 0.0],
            "axis_direction": [0.0, 0.0, 1.0],
            "blades": [
                {
                    "body_id": f"body_{index:03d}",
                    "root_face_id": f"body_{index:03d}_face_0005",
                    "outer_face_id": f"body_{index:03d}_face_0006",
                }
                for index in range(2, 5)
            ],
        },
        "parameters": {"sampling_step_mm": 0.4},
    },
}


def reference_nozzle() -> NozzleProfile:
    return NozzleProfile(
        "offline-envelope", "Offline reference only", 0.4, 1.75,
        interface="M6", length_mm=12.5,
        outer_profile_rz_mm=((0.2, 0.0), (3.0, 2.0), (3.0, 12.5)),
    )


def _reference_frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id, frame_id,
        PointReference("numeric", (0, 0, 0), confirmed=True),
        DirectionReference("numeric", (0, 0, 1), confirmed=True),
        DirectionReference("numeric", (1, 0, 0), confirmed=True),
    )


def prepare_ui_project(destination: Path, model, operation) -> Path:
    """Prepare a realistic project fixture; generation remains in the public UI command."""

    setup = ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(
            part_body_ids=tuple(body.body_id for body in model.bodies),
        ),
        machine=ResourceSnapshot.capture("machine", own_ac_profile()),
        nozzle=ResourceSnapshot.capture("nozzle", reference_nozzle()),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("fan15-offline-pla")
        ),
        model_coordinate_system=_reference_frame("model"),
        build_coordinate_system=_reference_frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250, 250, 250), source_frame="build", target_frame="build_plate_mount"
        ),
    )
    operation = replace(operation, setup_id=setup.setup_id)
    saved = save_project(
        destination, model, SelectionState(), setup=setup, operations=(operation,),
        original_source_path=model.source_path,
    )
    restored = load_project(saved)
    if restored.operations != (operation,) or restored.setup != setup:
        raise RuntimeError("prepared UI project did not roundtrip")
    return saved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=tuple(CASES))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prepare-project", type=Path,
                        help="save a configured project for real GUI generate/export testing")
    args = parser.parse_args()
    case = CASES[args.case]
    destination = args.output or (
        ROOT
        / "docs/reviews/evidence/2026-09-20_fan15_repairs"
        / f"{args.case}_public_product_20260921"
    )
    started = time.perf_counter()
    model = load_step(case["source"])
    operation = create_freeform_operation(
        (), "fan15-public-setup", case["operation_type"], operation_id=f"fan15-{args.case}"
    )
    operation = configure_freeform_solid_operation(
        operation,
        model,
        geometry=case["geometry"](model),
        parameters=SolidFillProcessParameters(**cast(Any, case["parameters"])),
    )
    if args.prepare_project is not None:
        print(prepare_ui_project(args.prepare_project, model, operation))
        return
    nozzle = reference_nozzle()
    result = generate_freeform_product(
        model,
        operation,
        own_ac_profile(),
        nozzle,
        OWN_AC_OFFLINE_CONTROLLER,
        T_build_from_source=RigidTransform.identity("build"),
        source_path=case["source"],
        thermal_parameters=ThermalProgramParameters(195.0, 45.0),
    )
    if not result.offline_exportable:
        raise RuntimeError(json.dumps(result.to_json(), ensure_ascii=False))
    export_freeform_product(result, destination)
    summary = {
        "case": args.case,
        "source": str(case["source"]),
        "source_sha256": model.source_hash,
        "operation_semantic_sha256": operation.semantic_sha256(),
        "output": str(destination.resolve()),
        "points": len(result.toolpath.points),
        "events": len(result.toolpath.events),
        "status": str(getattr(result.manifest.status, "value", result.manifest.status)),
        "readback": result.readback.to_json(),
        "thermal": result.to_json()["thermal_parameters"],
        "plan": result.plan.to_json(),
        "elapsed_s": time.perf_counter() - started,
    }
    (destination / "acceptance.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
