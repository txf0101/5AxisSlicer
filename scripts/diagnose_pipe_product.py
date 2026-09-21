"""Run the real complete pipe product with stage timings and actual path evidence."""

import argparse
from dataclasses import replace
import functools
import gzip
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.tube_controller import TubeSetupController
from five_axis_slicer.manufacturing.own_printer import own_ac_profile
from five_axis_slicer.manufacturing.resources import NozzleProfile
from five_axis_slicer.manufacturing.setup import TubeProcessParameters, TubeBuildupOperationConfig
from five_axis_slicer.postprocessing import tube_product as product


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="pipe_profile_optimized_20260921")
    parser.add_argument("--defer-ipw", action="store_true",
                        help="Offline NC inspection only; explicitly defer IPW collision qualification")
    args = parser.parse_args()
    folder = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs" / args.output
    folder.mkdir(parents=True, exist_ok=True)
    timings = []

    def wrap(name):
        original = getattr(product, name)

        @functools.wraps(original)
        def timed(*args, **kwargs):
            start = time.perf_counter()
            print("START", name, flush=True)
            result = original(*args, **kwargs)
            timings.append({"stage": name, "seconds": time.perf_counter() - start})
            (folder / "timings.json").write_text(json.dumps(timings, indent=2), encoding="utf-8")
            print("END", timings[-1], flush=True)
            if name == "_merge_buildup_sequence":
                with gzip.open(folder / "toolpath.json.gz", "wt", encoding="utf-8") as stream:
                    json.dump(result.to_json(), stream)
            return result

        setattr(product, name, timed)

    for name in (
        "generate_tube_buildup_toolpath",
        "_cad_substrate_toolpath",
        "_plan_buildup_sequence",
        "_merge_buildup_sequence",
        "solve_xyzac_trajectory",
        "_validate_buildup",
        "_finish_product",
    ):
        wrap(name)
    with (folder / "run.txt").open("w", encoding="utf-8") as evidence:
        evidence.write("Full real STEP product run; offline reference nozzle only.\n")
        model = load_step(ROOT / "example/pipe2/弯管新.stp")
        controller = TubeSetupController(model)
        controller.create_operation(operation_type="tube_buildup")
        operation = controller.configure_operation(
            tube_body_id="body_002",
            entry_port_id="body_002_edge_0003",
            exit_port_id="body_002_edge_0014",
            substrate_body_id="body_001",
            parameters=TubeProcessParameters(bead_width_mm=1 / 3, layer_height_mm=0.2),
        )
        operation = replace(
            operation,
            type_config=TubeBuildupOperationConfig(
                maximum_pass_spacing_mm=1 / 3, include_planar_base=True, base_order="before_tube"
            ),
        )
        nozzle = NozzleProfile(
            resource_id="offline-envelope",
            display_name="Offline reference only",
            orifice_diameter_mm=0.4,
            filament_diameter_mm=1.75,
            interface="M6",
            length_mm=12.5,
            outer_profile_rz_mm=((0.2, 0), (3, 2), (3, 12.5)),
        )
        result = product.generate_tube_product(
            model, operation, own_ac_profile(), nozzle, check_ipw=not args.defer_ipw,
            source_path=ROOT / "example/pipe2/弯管新.stp",
        )
        with gzip.open(folder / "toolpath.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(result.toolpath.to_json(), stream)
        (folder / "validation.json").write_text(
            json.dumps(result.validation.to_json(), indent=2), encoding="utf-8"
        )
        scope = {
            "qualification": "offline_diagnostic_only",
            "ipw_collision": "deferred_by_user" if args.defer_ipw else "requested",
            "physical_machine_qualified": False,
            "readback": result.readback.to_json(),
            "nc_generated": bool(result.gcode),
        }
        if result.gcode:
            header = "; OFFLINE DIAGNOSTIC ONLY - NOT QUALIFIED FOR MACHINE EXECUTION\n"
            if args.defer_ipw:
                header += "; IPW COLLISION CHECK DEFERRED BY USER - NOT A COLLISION PASS\n"
            code = header + result.gcode
            scope["readback"] = product.readback_tube_gcode(
                code, result.toolpath, result.trajectory, own_ac_profile(), nozzle
            ).to_json()
            (folder / "offline_diagnostic.gcode").write_text(code, encoding="utf-8")
        (folder / "inspection_scope.json").write_text(
            json.dumps(scope, indent=2), encoding="utf-8"
        )
        print("RESULT", result.manifest.status, "points", len(result.toolpath.points), flush=True)


if __name__ == "__main__":
    main()
