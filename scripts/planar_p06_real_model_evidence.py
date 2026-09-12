"""Run the deterministic P06 Planar operation matrix on a real STEP sample."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from five_axis_slicer.manufacturing.coordinates import (  # noqa: E402
    CoordinateFrameDefinition,
    DirectionReference,
    PointReference,
    RigidTransform,
)
from five_axis_slicer.manufacturing.machine import GENERIC_XYZAC_REFERENCE  # noqa: E402
from five_axis_slicer.manufacturing.planar_parameters import (  # noqa: E402
    PlanarProcessParameters,
)
from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_PLA_175,
    NozzleProfile,
    ResourceSnapshot,
)
from five_axis_slicer.manufacturing.setup import (  # noqa: E402
    ManufacturingObjectAssignments,
    ManufacturingSetup,
)
from five_axis_slicer.planar_controller import PlanarController  # noqa: E402
from five_axis_slicer.step_loader import load_step  # noqa: E402


def _frame(frame_id: str) -> CoordinateFrameDefinition:
    return CoordinateFrameDefinition.from_references(
        frame_id,
        frame_id,
        PointReference("numeric", (0.0, 0.0, 0.0), confirmed=True),
        DirectionReference("numeric", (0.0, 0.0, 1.0), confirmed=True),
        DirectionReference("numeric", (1.0, 0.0, 0.0), confirmed=True),
    )


def _machine():
    return replace(
        GENERIC_XYZAC_REFERENCE,
        joints=tuple(
            replace(joint, soft_limit_min=-1000.0, soft_limit_max=1000.0)
            for joint in GENERIC_XYZAC_REFERENCE.joints
        ),
    )


def _nozzle() -> NozzleProfile:
    return NozzleProfile(
        "planar-p06-nozzle",
        "Planar P06 evidence nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2.0,
        outer_profile_rz_mm=((0.3, 0.0), (0.4, 2.0)),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _setup(model, body_id: str) -> ManufacturingSetup:
    return ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(
            part_body_ids=(body_id,),
            ignored_body_ids=tuple(body.body_id for body in model.bodies if body.body_id != body_id),
        ),
        machine=ResourceSnapshot.capture("machine", _machine()),
        nozzle=ResourceSnapshot.capture("nozzle", _nozzle()),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("p06-evidence-pla")
        ),
        model_coordinate_system=_frame("model"),
        build_coordinate_system=_frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250.0, 250.0, 250.0), source_frame="build", target_frame="build_plate_mount"
        ),
    )


def _parameters(first: float, last: float) -> PlanarProcessParameters:
    return PlanarProcessParameters(
        first_layer_z_mm=first,
        last_layer_z_mm=last,
        layer_height_mm=0.6,
        bead_width_mm=0.6,
        line_spacing_mm=0.6,
        feedrate_mm_min=100.0,
        travel_feedrate_mm_min=100.0,
        retract_length_mm=1.0,
        offset_pass_count=3,
        wall_thickness_mm=0.6,
        thin_wall_max_passes=3,
        spiral_samples_per_contour=64,
    )


def _operation(controller: PlanarController, kind: str, body_id: str, first: float, last: float):
    operation = controller.create_operation(
        kind, operation_id=f"p06-{kind}", name=f"P06 real STEP {kind}"
    )
    return controller.configure_operation(
        operation_id=operation.operation_id,
        body_id=body_id,
        parameters=_parameters(first, last),
    )


def _result_summary(controller: PlanarController, operation, result, artifacts: Path) -> dict:
    measurement = result.validation.measurement
    return {
        "operation": operation.to_json(),
        "status": controller.product_state(operation.operation_id).status,
        "exportable": result.exportable,
        "toolpath_point_count": len(result.toolpath.points),
        "trajectory_sample_count": len(result.trajectory.samples),
        "measurement": asdict(measurement),
        "issues": [issue.to_json() for issue in result.validation.issues],
        "readback": result.readback.to_json(),
        "artifacts": {item.name: _sha256(item) for item in sorted(artifacts.iterdir()) if item.is_file()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="example/三叶扇/Supportless_sample.stp")
    parser.add_argument("--body", default="body_002")
    parser.add_argument("--z", type=float, default=60.0)
    parser.add_argument("--out", default="docs/reviews/evidence/2026-09-12_p06_planar/real_model")
    args = parser.parse_args()

    model_path = Path(args.model).resolve()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    model = load_step(model_path)
    if args.body not in model.shapes:
        raise ValueError(f"Body {args.body!r} is not present in {model_path}")
    controller = PlanarController(model, setup=_setup(model, args.body))
    operations: list[dict] = []
    for kind in ("planar_zigzag", "planar_offset", "planar_thin_wall"):
        operation = _operation(controller, kind, args.body, args.z, args.z)
        result = controller.generate_operation(operation.operation_id)
        artifacts = controller.export_operation_product(operation.operation_id, str(output / kind))
        operations.append(_result_summary(controller, operation, result, artifacts))

    spiral_attempts: list[dict[str, object]] = []
    spiral_result = None
    spiral_operation = None
    for first, last in ((args.z, args.z + 0.6), (args.z - 0.6, args.z), (args.z + 0.6, args.z + 1.2)):
        operation = _operation(controller, "planar_spiral", args.body, first, last)
        try:
            result = controller.generate_operation(operation.operation_id)
            spiral_operation, spiral_result = operation, result
            spiral_attempts.append({"first_z_mm": first, "last_z_mm": last, "selected": True, "status": "ok"})
            break
        except Exception as exc:
            spiral_attempts.append({"first_z_mm": first, "last_z_mm": last, "selected": False, "status": "failed", "error": str(exc)})
    if spiral_result is None or spiral_operation is None:
        raise RuntimeError(f"P05 spiral candidates all failed: {spiral_attempts}")
    artifacts = controller.export_operation_product(spiral_operation.operation_id, str(output / "planar_spiral"))
    spiral_summary = _result_summary(controller, spiral_operation, spiral_result, artifacts)
    spiral_summary["selection_attempts"] = spiral_attempts
    operations.append(spiral_summary)

    source_files = [
        Path(__file__).resolve(),
        Path("src/five_axis_slicer/algorithms/planar/region.py").resolve(),
        Path("src/five_axis_slicer/algorithms/planar/zigzag.py").resolve(),
        Path("src/five_axis_slicer/algorithms/planar/offset.py").resolve(),
        Path("src/five_axis_slicer/algorithms/planar/thin_wall.py").resolve(),
        Path("src/five_axis_slicer/algorithms/planar/spiral.py").resolve(),
        Path("src/five_axis_slicer/postprocessing/planar_product.py").resolve(),
    ]
    summary = {
        "schema_version": 1,
        "task": "P06",
        "model": {"path": str(model_path), "sha256": _sha256(model_path), "selected_body": args.body, "body_count": len(model.bodies)},
        "operations": operations,
        "source_sha256": {str(path): _sha256(path) for path in source_files},
        "generic_xyzac_boundary": "Generic XYZAC is an offline reference only; controller semantics, real machine calibration, collision qualification and physical trial deposition were not verified.",
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
