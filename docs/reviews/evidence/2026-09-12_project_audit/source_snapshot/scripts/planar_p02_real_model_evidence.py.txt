"""Generate reproducible P02 evidence from the repository's real STEP sample."""

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
    # Keep the production kinematic contract while making this repository
    # sample's translated offline envelope explicit and reproducible.
    return replace(
        GENERIC_XYZAC_REFERENCE,
        joints=tuple(
            replace(joint, soft_limit_min=-1000.0, soft_limit_max=1000.0)
            for joint in GENERIC_XYZAC_REFERENCE.joints
        ),
    )


def _nozzle() -> NozzleProfile:
    return NozzleProfile(
        "planar-evidence-nozzle",
        "Planar P02 evidence nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2.0,
        outer_profile_rz_mm=((0.3, 0.0), (0.4, 2.0)),
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="example/三叶扇/Supportless_sample.stp")
    parser.add_argument("--body", default="body_002")
    parser.add_argument("--z", type=float, default=60.0)
    parser.add_argument("--out", default="docs/reviews/evidence/2026-09-12_p02_planar/real_model")
    args = parser.parse_args()

    model_path = Path(args.model).resolve()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    model = load_step(model_path)
    if args.body not in model.shapes:
        raise ValueError(f"Body {args.body!r} is not present in {model_path}")

    machine = _machine()
    nozzle = _nozzle()
    setup = ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(
            part_body_ids=(args.body,),
            ignored_body_ids=tuple(
                body.body_id for body in model.bodies if body.body_id != args.body
            ),
        ),
        machine=ResourceSnapshot.capture("machine", machine),
        nozzle=ResourceSnapshot.capture("nozzle", nozzle),
        material=ResourceSnapshot.capture("material", GENERIC_PLA_175),
        model_coordinate_system=_frame("model"),
        build_coordinate_system=_frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250.0, 250.0, 250.0),
            source_frame="build",
            target_frame="build_plate_mount",
        ),
    )
    controller = PlanarController(model, setup=setup)
    operation = controller.create_operation(
        "planar_zigzag", operation_id="p02-real-model", name="P02 real STEP zigzag"
    )
    operation = controller.configure_operation(
        operation_id=operation.operation_id,
        body_id=args.body,
        parameters=PlanarProcessParameters(
            first_layer_z_mm=args.z,
            last_layer_z_mm=args.z,
            layer_height_mm=0.6,
            bead_width_mm=0.6,
            line_spacing_mm=0.6,
            feedrate_mm_min=100.0,
            travel_feedrate_mm_min=100.0,
            retract_length_mm=1.0,
        ),
    )
    result = controller.generate_operation(operation.operation_id)
    artifact_dir = controller.export_operation_product(
        operation.operation_id, str(output / "six_file_product")
    )
    measurement = result.validation.measurement
    artifact_hashes = {
        item.name: _sha256(item) for item in sorted(artifact_dir.iterdir()) if item.is_file()
    }
    summary = {
        "schema_version": 1,
        "model": {
            "path": str(model_path),
            "sha256": _sha256(model_path),
            "body_count": len(model.bodies),
            "selected_body": args.body,
            "bounds_mm": None
            if model.bounds is None
            else [list(model.bounds.minimum), list(model.bounds.maximum)],
        },
        "operation": operation.to_json(),
        "result": {
            "status": controller.product_state(operation.operation_id).status,
            "exportable": result.exportable,
            "readback_passed": result.readback.passed,
            "layer_count": len(result.layers),
            "toolpath_point_count": len(result.toolpath.points),
            "trajectory_sample_count": len(result.trajectory.samples),
            "measurement": asdict(measurement),
            "issue_codes": [issue.code for issue in result.validation.issues],
        },
        "qualification_boundary": (
            "Generic XYZAC offline reference only; no controller, machine-limit, "
            "collision, dry-run, or physical-print qualification was performed."
        ),
        "artifacts": artifact_hashes,
    }
    summary_path = output / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
