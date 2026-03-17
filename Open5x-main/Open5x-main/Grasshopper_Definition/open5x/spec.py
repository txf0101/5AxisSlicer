from __future__ import annotations

import json
from pathlib import Path

from .models import MachineConfig, PathSpec, PrintSettings, ProjectSpec
from .vector_math import as_array_2d


def _path_from_dict(data: dict) -> PathSpec:
    points = as_array_2d(data["points"], expected_width=3)
    normals = as_array_2d(data["normals"], expected_width=3)
    if len(points) != len(normals):
        raise ValueError("Each path needs the same number of points and normals")
    return PathSpec(
        name=data.get("name", "path"),
        points_mm=points,
        normals=normals,
        extrude=bool(data.get("extrude", True)),
        closed=bool(data.get("closed", False)),
    )


def load_project_spec(path: str | Path) -> ProjectSpec:
    file_path = Path(path)
    data = json.loads(file_path.read_text(encoding="utf-8"))
    machine = MachineConfig(**data.get("machine", {}))
    print_settings = PrintSettings(**data.get("print_settings", {}))
    paths = [_path_from_dict(item) for item in data["paths"]]
    return ProjectSpec(
        name=data.get("name", file_path.stem),
        comment=data.get("comment", ""),
        machine=machine,
        print_settings=print_settings,
        paths=paths,
        start_gcode=list(data.get("start_gcode", [])),
        end_gcode=list(data.get("end_gcode", [])),
    )


def write_project_spec(project: ProjectSpec, path: str | Path) -> None:
    payload = {
        "name": project.name,
        "comment": project.comment,
        "machine": {
            "translation_axes": list(project.machine.translation_axes),
            "rotation_axes": list(project.machine.rotation_axes),
            "rotation_order": list(project.machine.rotation_order),
            "tool_axis": list(project.machine.tool_axis),
            "origin_mm": list(project.machine.origin_mm),
            "tool_offset_mm": project.machine.tool_offset_mm,
            "rotation_radius_mm": project.machine.rotation_radius_mm,
        },
        "print_settings": {
            "line_width_mm": project.print_settings.line_width_mm,
            "layer_height_mm": project.print_settings.layer_height_mm,
            "filament_diameter_mm": project.print_settings.filament_diameter_mm,
            "flow_multiplier": project.print_settings.flow_multiplier,
            "bead_area_scale": project.print_settings.bead_area_scale,
            "print_feed_mm_s": project.print_settings.print_feed_mm_s,
            "travel_feed_mm_s": project.print_settings.travel_feed_mm_s,
            "retraction_length_mm": project.print_settings.retraction_length_mm,
            "retraction_feed_mm_s": project.print_settings.retraction_feed_mm_s,
            "prime_length_mm": project.print_settings.prime_length_mm,
            "travel_lift_mm": project.print_settings.travel_lift_mm,
            "max_feed_scale": project.print_settings.max_feed_scale,
        },
        "start_gcode": project.start_gcode,
        "end_gcode": project.end_gcode,
        "paths": [
            {
                "name": path_spec.name,
                "extrude": path_spec.extrude,
                "closed": path_spec.closed,
                "points": path_spec.points_mm.round(6).tolist(),
                "normals": path_spec.normals.round(6).tolist(),
            }
            for path_spec in project.paths
        ],
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
