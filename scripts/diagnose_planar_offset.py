"""Inspect a failed section offset at an explicit source and height."""

import argparse
from dataclasses import replace
from pathlib import Path
import sys

import cadquery as cq
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
from OCP.GeomAbs import GeomAbs_Arc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from five_axis_slicer.step_loader import load_step
from five_axis_slicer.algorithms.planar.region import slice_planar_layers
from five_axis_slicer.algorithms.planar.offset import (
    _prepare_region,
    _wire_loop,
    _segments_intersect,
    _area,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("height", type=float)
    parser.add_argument("--simplify", action="store_true")
    args = parser.parse_args()
    model = load_step(args.source)
    layer = slice_planar_layers(
        model,
        tuple(b.body_id for b in model.bodies),
        first_layer_z_mm=args.height,
        last_layer_z_mm=args.height,
        layer_height_mm=0.2,
    )[0]
    for region in layer.regions:
        if args.simplify:
            from five_axis_slicer.algorithms.fan.chart_fill import _closed_reduce

            region = replace(
                region,
                outer=_closed_reduce(region.outer),
                holes=tuple(_closed_reduce(hole) for hole in region.holes),
            )
        print(
            region.region_id,
            "area",
            _area(region.outer),
            "holes",
            len(region.holes),
            "vertices",
            len(region.outer),
            flush=True,
        )
        face, error = _prepare_region(region)
        if error:
            print(error)
            continue
        for distance in (0.2, 0.6, 0.8):
            operation = BRepOffsetAPI_MakeOffset()
            operation.Init(face.wrapped, GeomAbs_Arc, False)
            operation.Perform(-distance)
            print("distance", distance, "done", operation.IsDone(), flush=True)
            if not operation.IsDone():
                continue
            for wire in cq.Shape.cast(operation.Shape()).Wires():
                loop = _wire_loop(wire)
                segments = list(zip(loop, loop[1:]))
                crossing = [
                    (i, j, a, b)
                    for i, a in enumerate(segments)
                    for j, b in enumerate(segments[i + 2 :], i + 2)
                    if not (i == 0 and j == len(segments) - 1) and _segments_intersect(*a, *b)
                ]
                print(
                    "points", len(loop), "area", _area(loop), "crossings", crossing[:3], flush=True
                )


if __name__ == "__main__":
    main()
