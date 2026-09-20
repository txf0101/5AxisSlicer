"""Prepare the live GUI via shared commands after real mouse geometry picks.

The nozzle envelope is an explicit offline fixture, NOT a measured machine.
No NC is exported and no real printer is contacted.
"""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    folder = (
        Path(__file__).resolve().parents[1]
        / "docs/reviews/evidence/2026-09-20_fan15_repairs/live_pipe_pick"
    )
    folder.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{args.port}"
    records = []

    def call(route, payload=None):
        request = Request(
            base + route,
            None if payload is None else json.dumps(payload).encode(),
            {"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=120) as response:
            result = json.load(response)
        records.append({"route": route, "payload": payload, "result": result})
        (folder / "commands.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result

    state = call("/tube/state")["tube"]
    geometry = state["operations"][0]["geometry"]
    roles = {
        name + "_id": geometry[name]["object_id"]
        for name in ("tube_body", "entry_port", "exit_port", "substrate_body")
    }
    call("/tube/part/confirm", {"part_body_ids": ["body_001", "body_002"]})
    call(
        "/tube/resource/select",
        {
            "kind": "nozzle",
            "identifier": "0.4",
            "complete": True,
            "interface": "M6",
            "length_mm": 12.5,
            "construction_material": "brass",
            "flow_category": "standard",
            "temperature_limit_c": 300,
            "wear_resistance_rating": "standard",
            "outer_profile_rz_mm": [[0.2, 0], [3, 2], [3, 12.5]],
        },
    )
    call(
        "/tube/resource/select", {"kind": "material", "identifier": "PLA", "review_confirmed": True}
    )
    for node in ("model_cs", "build_cs"):
        call("/tube/coordinate/apply", {"node": node})
    call("/tube/placement/apply", {"mount_datum_id": "build_plate_mount"})
    call(
        "/tube/operation/create",
        {"operation_type": "tube_buildup", "operation_id": "fan15-live-buildup"},
    )
    call(
        "/tube/operation/set",
        {
            "operation_id": "fan15-live-buildup",
            **roles,
            "bead_width_mm": 1 / 3,
            "maximum_pass_spacing_mm": 1 / 3,
            "layer_height_mm": 0.2,
            "include_planar_base": True,
            "base_order": "before_tube",
        },
    )
    print("Prepared live Buildup using mouse-picked roles:", roles, flush=True)
    print("OFFLINE fixture envelope only; machine remains reference_only.", flush=True)


if __name__ == "__main__":
    main()
