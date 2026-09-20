"""Full base and multipass wall candidate, explicitly not machine-qualified NC."""

from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.tube_controller import TubeSetupController
from five_axis_slicer.algorithms.tube.geometry import recognise_tube
from five_axis_slicer.algorithms.tube.buildup import (
    TubeBuildupParameters,
    plan_tube_buildup,
    generate_tube_buildup_toolpath,
)
from five_axis_slicer.postprocessing.tube_product import _cad_substrate_toolpath


def main():
    folder = ROOT / "docs/reviews/evidence/2026-09-20_fan15_repairs/pipe2_cadbase_20260921"
    folder.mkdir(parents=True, exist_ok=True)
    model = load_step(ROOT / "example/pipe2/弯管新.stp")
    controller = TubeSetupController(model)
    controller.create_operation()
    operation = controller.configure_operation(
        tube_body_id="body_002",
        entry_port_id="body_002_edge_0003",
        exit_port_id="body_002_edge_0014",
        substrate_body_id="body_001",
    )
    feature = recognise_tube(model, operation.geometry)
    # Three equal lanes partition this 1 mm wall; fixed .4 mm x 3 would overfeed 20%.
    width = feature.wall_thickness_mm / 3
    parameters = TubeBuildupParameters(
        bead_width_mm=width, layer_height_mm=0.2, maximum_pass_spacing_mm=width
    )
    plan = plan_tube_buildup(feature, parameters)
    tube = generate_tube_buildup_toolpath("pipe2-wall", feature, plan, parameters, model=model)
    print("tube", len(tube.points), "points", flush=True)
    base = _cad_substrate_toolpath(model, operation, feature, parameters)
    arrays = {}
    for name, path in (("base", base), ("wall", tube)):
        with gzip.open(folder / f"{name}_toolpath.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(path.to_json(), stream, ensure_ascii=False)
        arrays[name] = np.asarray(
            [
                (a.position, b.position)
                for a, b in zip(path.points, path.points[1:])
                if b.point_type == "deposition"
            ]
        )
    np.savez_compressed(folder / "paths.npz", **arrays)
    report = {
        "source_hash": model.source_hash,
        "wall_parameters": asdict(parameters),
        "geometry": operation.geometry.to_json(),
        "pass_count": plan.pass_count,
        "wall_layers": len(plan.layers),
        "base_layers": len({p.layer_id for p in base.points if p.point_type == "deposition"}),
        "wall_volume_mm3": sum(p.material_volume_mm3 for p in tube.points),
        "cad_wall_volume_mm3": model.body_map["body_002"].volume,
        "base_volume_mm3": sum(p.material_volume_mm3 for p in base.points),
        "complete_nc": False,
        "accepted": False,
        "limits": [
            "candidate domain generation only",
            "no joint base-wall transition qualification",
            "no full swept-nozzle or local prior-material qualification",
            "equal lane width requires process calibration",
            "no machine program exported",
        ],
        "array_sha256": hashlib.sha256((folder / "paths.npz").read_bytes()).hexdigest(),
    }
    (folder / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in ("pass_count", "wall_layers", "wall_volume_mm3", "accepted")}), flush=True)


if __name__ == "__main__":
    main()
