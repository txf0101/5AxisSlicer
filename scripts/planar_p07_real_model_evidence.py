"""Generate reproducible P07 support evidence from an analytic STEP model."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import sys

import cadquery as cq

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


SIX_FILE_BUNDLE = {
    "machine_axes.csv",
    "main.gcode",
    "manifest.json",
    "preview.json",
    "toolpath.json",
    "warnings.json",
}
ANALYTIC_DEFINITION = {
    "kind": "floating_rectangular_beam",
    "bounds_mm": {"minimum": [4.0, 2.0, 2.2], "maximum": [12.0, 8.0, 3.2]},
    "requested_layers_mm": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
    "expected_empty_part_layers_mm": [0.5, 1.0, 1.5, 2.0],
    "expected_support_stage_by_z_mm": {
        "0.5": "planar_support",
        "1.0": "planar_support",
        "1.5": "planar_support_interface",
        "2.0": "planar_support_interface",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "planar-p07-nozzle",
        "Planar P07 evidence nozzle",
        0.6,
        1.75,
        interface="M6",
        length_mm=2.0,
        outer_profile_rz_mm=((0.3, 0.0), (0.4, 2.0)),
    )


def _setup(model, body_id: str) -> ManufacturingSetup:
    return ManufacturingSetup(
        assignments=ManufacturingObjectAssignments(
            part_body_ids=(body_id,),
            ignored_body_ids=tuple(
                body.body_id for body in model.bodies if body.body_id != body_id
            ),
        ),
        machine=ResourceSnapshot.capture("machine", _machine()),
        nozzle=ResourceSnapshot.capture("nozzle", _nozzle()),
        material=ResourceSnapshot.capture(
            "material", GENERIC_PLA_175.reviewed_copy("p07-evidence-pla")
        ),
        model_coordinate_system=_frame("model"),
        build_coordinate_system=_frame("build"),
        mount_datum_id="build_plate_mount",
        T_mount_from_build=RigidTransform.from_translation(
            (250.0, 250.0, 250.0),
            source_frame="build",
            target_frame="build_plate_mount",
        ),
    )


def _support_parameters(
    *,
    first_layer_z_mm: float = 0.5,
    last_layer_z_mm: float = 3.0,
    layer_height_mm: float = 0.5,
    pattern: str = "grid",
) -> PlanarProcessParameters:
    return PlanarProcessParameters(
        first_layer_z_mm=first_layer_z_mm,
        last_layer_z_mm=last_layer_z_mm,
        layer_height_mm=layer_height_mm,
        bead_width_mm=0.6,
        line_spacing_mm=0.6,
        feedrate_mm_min=100.0,
        travel_feedrate_mm_min=100.0,
        retract_length_mm=1.0,
        support_overhang_angle_deg=45.0,
        support_xy_gap_mm=0.0,
        support_z_gap_mm=0.0,
        support_line_spacing_mm=1.0,
        support_interface_layers=2,
        support_interface_spacing_mm=0.6,
        support_pattern=pattern,
    )


def _write_floating_beam(path: Path) -> Path:
    """Write the analytic beam used by the independent geometry checks."""

    path.parent.mkdir(parents=True, exist_ok=True)
    beam = cq.Workplane("XY").box(8.0, 6.0, 1.0).translate((8.0, 5.0, 2.7))
    cq.exporters.export(beam, str(path))
    return path


def _operation(
    controller: PlanarController,
    body_id: str,
    parameters: PlanarProcessParameters,
    operation_id: str,
):
    created = controller.create_operation(
        "planar_support", operation_id=operation_id, name="P07 Planar Support"
    )
    return controller.configure_operation(
        operation_id=created.operation_id,
        body_id=body_id,
        parameters=parameters,
    )


def _deposition_segments(result):
    return tuple(
        (previous, current)
        for previous, current in zip(result.toolpath.points, result.toolpath.points[1:])
        if current.point_type == "deposition"
    )


def _state_summary(state) -> dict[str, object] | None:
    if state is None:
        return None
    return {
        "operation_id": state.operation_id,
        "parameter_semantic_sha256": state.parameter_semantic_sha256,
        "status": state.status,
    }


def _check_analytic_truth(result) -> dict[str, object]:
    expected_layers = ANALYTIC_DEFINITION["requested_layers_mm"]
    actual_layers = [layer.z_mm for layer in result.layers]
    if len(actual_layers) != len(expected_layers) or any(
        not math.isclose(actual, expected, abs_tol=1.0e-7)
        for actual, expected in zip(actual_layers, expected_layers)
    ):
        raise RuntimeError(f"P07 did not preserve the requested platform layers: {actual_layers}")
    if any(layer.regions for layer in result.layers[:4]):
        raise RuntimeError("Analytic floating beam unexpectedly intersects a platform-side layer")

    segments = _deposition_segments(result)
    if not segments:
        raise RuntimeError("P07 analytic model produced no deposition segment")
    stage_counts: dict[str, int] = {}
    measured_volume = 0.0
    for previous, current in segments:
        midpoint = tuple(
            (left + right) / 2.0 for left, right in zip(previous.position, current.position)
        )
        if not (
            4.3 - 1.0e-6 <= midpoint[0] <= 11.7 + 1.0e-6
            and 2.3 - 1.0e-6 <= midpoint[1] <= 7.7 + 1.0e-6
            and midpoint[2] < 2.2
        ):
            raise RuntimeError(f"Support centreline escaped the analytic domain: {midpoint}")
        expected_stage = (
            "planar_support" if midpoint[2] <= 1.0 + 1.0e-9 else ("planar_support_interface")
        )
        expected_role = (
            "support_material"
            if expected_stage == "planar_support"
            else "support_interface"
        )
        if current.stage_id != expected_stage or current.extrusion_role != expected_role:
            raise RuntimeError(
                f"Unexpected support provenance at {midpoint}: "
                f"{current.stage_id}/{current.extrusion_role}"
            )
        stage_counts[current.stage_id] = stage_counts.get(current.stage_id, 0) + 1
        measured_volume += math.dist(previous.position, current.position) * 0.6 * 0.5

    recorded_volume = sum(point.material_volume_mm3 for point in result.toolpath.points)
    if not math.isclose(recorded_volume, measured_volume, rel_tol=1.0e-9, abs_tol=1.0e-7):
        raise RuntimeError(
            f"Support material volume mismatch: recorded={recorded_volume}, "
            f"independent={measured_volume}"
        )
    return {
        "passed": True,
        "deposition_segment_count": len(segments),
        "stage_segment_counts": stage_counts,
        "independent_material_volume_mm3": measured_volume,
        "recorded_material_volume_mm3": recorded_volume,
    }


def _result_summary(controller, operation, result, product_dir: Path) -> dict[str, object]:
    artifacts = {
        item.name: _sha256(item) for item in sorted(product_dir.iterdir()) if item.is_file()
    }
    if set(artifacts) != SIX_FILE_BUNDLE:
        raise RuntimeError(f"P07 export bundle mismatch: {sorted(artifacts)}")
    state = controller.product_state(operation.operation_id)
    return {
        "operation": operation.to_json(),
        "product_state": _state_summary(state),
        "exportable": result.exportable,
        "toolpath_point_count": len(result.toolpath.points),
        "trajectory_sample_count": len(result.trajectory.samples),
        "measurement": asdict(result.validation.measurement),
        "issues": [issue.to_json() for issue in result.validation.issues],
        "readback": result.readback.to_json(),
        "stage_ids": sorted({point.stage_id for point in result.toolpath.points}),
        "artifacts_sha256": artifacts,
    }


def _run_analytic(output: Path) -> dict[str, object]:
    model_path = _write_floating_beam(output / "input" / "analytic_floating_beam.step")
    model = load_step(model_path)
    if len(model.bodies) != 1:
        raise RuntimeError(f"Analytic STEP should contain one body, found {len(model.bodies)}")
    body_id = model.bodies[0].body_id
    controller = PlanarController(model, setup=_setup(model, body_id))
    operation = _operation(
        controller,
        body_id,
        _support_parameters(),
        "p07-analytic-floating-beam",
    )
    result = controller.generate_operation(operation.operation_id)
    if not result.exportable or not result.readback.passed:
        raise RuntimeError("P07 analytic product was not exportable with passing G-code readback")
    product_dir = controller.export_operation_product(
        operation.operation_id, str(output / "analytic_product")
    )
    return {
        "input": {
            "path": str(model_path),
            "sha256": _sha256(model_path),
            "selected_body": body_id,
            "definition": ANALYTIC_DEFINITION,
        },
        "independent_truth": _check_analytic_truth(result),
        "result": _result_summary(controller, operation, result, product_dir),
    }


def _run_optional_fan(
    model_path: Path,
    output: Path,
    *,
    body_id: str | None,
    first_z_mm: float,
    last_z_mm: float | None,
    layer_height_mm: float,
) -> dict[str, object]:
    model = load_step(model_path)
    selected = body_id or model.bodies[0].body_id
    body = next((item for item in model.bodies if item.body_id == selected), None)
    if body is None or body.bounds is None:
        raise ValueError(f"Body {selected!r} with bounds is not present in {model_path}")
    inferred_last = math.floor(body.bounds.maximum[2] / layer_height_mm) * layer_height_mm
    last = inferred_last if last_z_mm is None else last_z_mm
    controller = PlanarController(model, setup=_setup(model, selected))
    operation = _operation(
        controller,
        selected,
        _support_parameters(
            first_layer_z_mm=first_z_mm,
            last_layer_z_mm=last,
            layer_height_mm=layer_height_mm,
            pattern="lines",
        ),
        "p07-existing-fan",
    )
    try:
        result = controller.generate_operation(operation.operation_id)
    except Exception as exc:
        state = controller.product_state(operation.operation_id)
        return {
            "input": {
                "path": str(model_path),
                "sha256": _sha256(model_path),
                "selected_body": selected,
                "bounds_mm": [list(body.bounds.minimum), list(body.bounds.maximum)],
                "first_layer_z_mm": first_z_mm,
                "last_layer_z_mm": last,
                "layer_height_mm": layer_height_mm,
            },
            "generation_error": str(exc),
            "product_state": _state_summary(state),
            "exported": False,
        }
    record: dict[str, object] = {
        "input": {
            "path": str(model_path),
            "sha256": _sha256(model_path),
            "selected_body": selected,
            "bounds_mm": [list(body.bounds.minimum), list(body.bounds.maximum)],
            "first_layer_z_mm": first_z_mm,
            "last_layer_z_mm": last,
            "layer_height_mm": layer_height_mm,
        },
        "exported": result.exportable,
    }
    if result.exportable:
        product_dir = controller.export_operation_product(
            operation.operation_id, str(output / "existing_fan_product")
        )
        record["result"] = _result_summary(controller, operation, result, product_dir)
    else:
        state = controller.product_state(operation.operation_id)
        record["result"] = {
            "product_state": _state_summary(state),
            "exportable": False,
            "issues": [issue.to_json() for issue in result.validation.issues],
            "readback": result.readback.to_json(),
        }
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate P07 analytic STEP, support product, bundle, and hash evidence."
    )
    parser.add_argument(
        "--out",
        default="docs/reviews/evidence/2026-09-12_p07_planar_support/real_model",
    )
    parser.add_argument(
        "--fan-model",
        help="Optional existing STEP to test after the mandatory analytic model.",
    )
    parser.add_argument("--fan-body", help="Body ID in --fan-model; defaults to its first body.")
    parser.add_argument("--fan-first-z", type=float, default=0.5)
    parser.add_argument("--fan-last-z", type=float)
    parser.add_argument("--fan-layer-height", type=float, default=0.5)
    args = parser.parse_args()

    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {
        "schema_version": 1,
        "task": "P07",
        "scope": "buildplate-only Grid/Lines support",
        "implementation_boundary": (
            "Clean-room implementation from public slicer behavior; no CuraEngine or "
            "PrusaSlicer AGPLv3 source was copied or translated."
        ),
        "analytic_case": _run_analytic(output),
        "generic_xyzac_boundary": (
            "Generic XYZAC is an offline reference only; controller semantics, real machine "
            "calibration, collision qualification and physical deposition were not verified."
        ),
    }
    if args.fan_model:
        summary["existing_fan_case"] = _run_optional_fan(
            Path(args.fan_model).resolve(),
            output,
            body_id=args.fan_body,
            first_z_mm=args.fan_first_z,
            last_z_mm=args.fan_last_z,
            layer_height_mm=args.fan_layer_height,
        )

    source_files = (
        Path(__file__).resolve(),
        Path("src/five_axis_slicer/algorithms/planar/support.py").resolve(),
        Path("src/five_axis_slicer/algorithms/planar/support_geometry.py").resolve(),
        Path("src/five_axis_slicer/postprocessing/planar_support_product.py").resolve(),
        Path("src/five_axis_slicer/postprocessing/planar_product.py").resolve(),
    )
    summary["source_sha256"] = {str(path): _sha256(path) for path in source_files}
    summary_path = output / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
