"""Generate the reproducible Rotary R01--R05 product evidence set."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys

import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE  # noqa: E402
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_PLA_175,
    NozzleProfile,
    ResourceSnapshot,
)
from five_axis_slicer.manufacturing.rotary_parameters import (  # noqa: E402
    RotaryAngularRegion,
    RotaryProcessParameters,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    ManufacturingObjectAssignments,
    ManufacturingSetup,
)
from five_axis_slicer.postprocessing.rotary_product import export_rotary_product  # noqa: E402
from five_axis_slicer.rotary_controller import RotaryController  # noqa: E402
from five_axis_slicer.rotary_operation_service import (  # noqa: E402
    bind_rotary_geometry_references,
)
from five_axis_slicer.step_loader import load_step  # noqa: E402

EVIDENCE_ROOT = ROOT / "docs" / "reviews" / "evidence" / "2026-09-13_rotary_workbench_final"
PRODUCT_ROOT = EVIDENCE_ROOT / "products"
INPUT_ROOT = EVIDENCE_ROOT / "inputs"


def _frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", (0, 0, 0), confirmed=True),
        DirectionReference("numeric", (0, 0, 1), confirmed=True),
        DirectionReference("numeric", (1, 0, 0), confirmed=True),
    )


def _setup(body_id: str) -> ManufacturingSetup:
    nozzle = NozzleProfile(
        "rotary-evidence-nozzle",
        "Rotary evidence nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2.0,
        outer_profile_rz_mm=((0.3, 0.0), (0.4, 2.0)),
    )
    evidence_machine = replace(
        GENERIC_XYZAC_REFERENCE,
        profile_id="generic_xyzac_rotary_evidence_v1",
        name="Generic XYZAC Rotary evidence fixture",
        joints=tuple(
            replace(joint, soft_limit_min=-500.0, soft_limit_max=500.0)
            if joint.joint_id in {"X", "Y", "Z"}
            else joint
            for joint in GENERIC_XYZAC_REFERENCE.joints
        ),
    )
    return ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(part_body_ids=(body_id,)),
        machine=ResourceSnapshot.capture("machine", evidence_machine),
        nozzle=ResourceSnapshot.capture("nozzle", nozzle),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("rotary-evidence-pla")
        ),
        model_coordinate_system=_frame("model"),
        build_coordinate_system=_frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250, 250, 250),
            source_frame="build",
            target_frame="build_plate_mount",
        ),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_inputs() -> tuple[Path, Path]:
    INPUT_ROOT.mkdir(parents=True, exist_ok=True)
    cylinder = INPUT_ROOT / "rotary_cylinder_nonzero_center.step"
    cone = INPUT_ROOT / "rotary_cone_nonzero_center.step"
    cq.exporters.export(
        cq.Workplane("XY", origin=(10, -20, 5)).circle(12).extrude(24),
        str(cylinder),
    )
    cone_shape = (
        cq.Workplane("XY", origin=(10, -20, 5))
        .circle(15)
        .workplane(offset=12)
        .circle(9)
        .loft(combine=True)
    )
    stem = cq.Workplane("XY", origin=(10, -20, 0)).circle(2).extrude(5)
    cq.exporters.export(cone_shape.union(stem), str(cone))
    return cylinder, cone


def _controller(step_path: Path, operation_type: str) -> tuple[RotaryController, object]:
    model = load_step(step_path)
    surface_type = "cone" if "cone" in step_path.name else "cylinder"
    surface = next(face for face in model.faces if face.surface_type == surface_type)
    axis = next(
        edge
        for edge in model.edges
        if edge.curve_type == "line"
        and edge.axis_direction is not None
        and abs(edge.axis_direction[2]) > 0.999
    )
    controller = RotaryController(model, setup=_setup(model.bodies[0].body_id))
    operation = controller.create_operation(operation_type)
    geometry = bind_rotary_geometry_references(
        model,
        operation.geometry,
        axis_edge_id=axis.edge_id,
        surface_face_ids=(surface.face_id,),
    )
    return controller, replace(operation, geometry=geometry)


def _generate(
    name: str,
    step_path: Path,
    operation_type: str,
    parameters: RotaryProcessParameters,
    *,
    axial_end_mm: float,
    regions: tuple[RotaryAngularRegion, ...] = (),
) -> dict[str, object]:
    controller, operation = _controller(step_path, operation_type)
    geometry = replace(
        operation.geometry,
        profile=replace(
            operation.geometry.profile,
            axial_start_mm=0.0,
            axial_end_mm=axial_end_mm,
        ),
        angular_regions=regions,
    )
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        geometry=geometry,
        parameters=parameters,
    )
    result = controller.generate_operation(operation.operation_id)
    if not result.exportable:
        raise RuntimeError(f"{name} is not exportable: {result.validation.to_json()}")
    target = export_rotary_product(result, PRODUCT_ROOT / name)
    files = {path.name: _sha256(path) for path in sorted(target.iterdir()) if path.is_file()}
    if set(files) != {
        "main.gcode",
        "toolpath.json",
        "machine_axes.csv",
        "warnings.json",
        "preview.json",
        "manifest.json",
    }:
        raise RuntimeError(f"{name} did not produce the exact six-file contract")
    return {
        "operation_type": operation_type,
        "status": result.manifest.status.value,
        "readback_passed": result.readback.passed,
        "point_count": len(result.toolpath.points),
        "path_count": len(result.plan.paths),
        "deposition_length_mm": result.plan.deposition_length_mm,
        "material_volume_mm3": result.plan.material_volume_mm3,
        "files": files,
    }


def main() -> int:
    cylinder, cone = _write_inputs()
    PRODUCT_ROOT.mkdir(parents=True, exist_ok=True)
    shared = {
        "sampling_angle_rad": math.radians(5),
        "angular_velocity_rad_s": 0.1,
    }
    products = {
        "rotary_spiral_cylinder": _generate(
            "rotary_spiral_cylinder",
            cylinder,
            "rotary_spiral",
            RotaryProcessParameters(
                pitch_mm=8,
                end_angle_rad=math.tau,
                feedrate_mm_min=300,
                travel_feedrate_mm_min=300,
                **shared,
            ),
            axial_end_mm=8,
        ),
        "rotary_spiral_cone": _generate(
            "rotary_spiral_cone",
            cone,
            "rotary_spiral",
            RotaryProcessParameters(
                pitch_mm=6,
                end_angle_rad=math.tau,
                feedrate_mm_min=240,
                travel_feedrate_mm_min=240,
                **shared,
            ),
            axial_end_mm=6,
        ),
        "rotary_thin_wall": _generate(
            "rotary_thin_wall",
            cylinder,
            "rotary_thin_wall",
            RotaryProcessParameters(
                axial_step_mm=0.8,
                radial_pass_count=3,
                radial_spacing_mm=0.8,
                wall_thickness_mm=2.4,
                feedrate_mm_min=120,
                travel_feedrate_mm_min=120,
                **shared,
            ),
            axial_end_mm=2.4,
        ),
        "rotary_around_part_cross_zero": _generate(
            "rotary_around_part_cross_zero",
            cylinder,
            "rotary_around_part",
            RotaryProcessParameters(
                axial_step_mm=0.8,
                feedrate_mm_min=120,
                travel_feedrate_mm_min=120,
                **shared,
            ),
            axial_end_mm=1.6,
            regions=(
                RotaryAngularRegion("cross-zero", math.radians(350), math.radians(20)),
                RotaryAngularRegion("local-sector", math.radians(120), math.radians(210)),
            ),
        ),
    }
    summary = {
        "schema_version": 1,
        "machine_qualification": "Generic XYZAC reference; offline only",
        "controller_g93_verified_by_readback": True,
        "inputs": {path.name: _sha256(path) for path in (cylinder, cone)},
        "products": products,
    }
    path = EVIDENCE_ROOT / "products_summary.json"
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
