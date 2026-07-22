from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gcode_preview import GCodePreview, PreviewSettings
from .models import CadModel, SelectionState

PROJECT_VERSION = 1


def save_project(
    directory: str | Path,
    model: CadModel | None,
    selection: SelectionState,
    workbench_state: dict[str, Any] | None = None,
    gcode_preview: GCodePreview | None = None,
    preview_settings: PreviewSettings | None = None,
    result_preview_state: Any | None = None,
) -> Path:
    project_dir = Path(directory).expanduser().resolve()
    source_dir = project_dir / "source"
    preview_dir = project_dir / "preview"
    source_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    source_payload = None
    model_payload = None
    if model is not None:
        source_copy = source_dir / model.source_path.name
        shutil.copy2(model.source_path, source_copy)
        source_payload = {
            "original_path": str(model.source_path),
            "project_path": str(Path("source") / source_copy.name),
            "sha256": model.source_hash,
        }
        model_payload = {
            "body_count": len(model.bodies),
            "edge_count": len(model.edges),
            "bodies": [body.to_json() for body in model.bodies],
            "edges": [edge.to_json() for edge in model.edges],
        }

    gcode_payload = None
    if gcode_preview is not None:
        gcode_copy = source_dir / gcode_preview.source_path.name
        if gcode_preview.source_path.exists():
            shutil.copy2(gcode_preview.source_path, gcode_copy)
        gcode_payload = {
            "original_path": str(gcode_preview.source_path),
            "project_path": str(Path("source") / gcode_copy.name),
            "summary": gcode_preview.summary(),
        }

    payload: dict[str, Any] = {
        "version": PROJECT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workbench": workbench_state or {},
        "source": source_payload,
        "gcode": gcode_payload,
        "model": model_payload,
        "selection": selection.to_json(),
        "manufacturable_feature_groups": [],
        "preview": {
            "glb": None,
            "gcode": None if preview_settings is None else preview_settings.to_json(),
        },
    }
    if result_preview_state is not None:
        state_payload = (
            result_preview_state.to_json()
            if hasattr(result_preview_state, "to_json")
            else dict(result_preview_state)
        )
        payload["result_preview"] = state_payload

    output = project_dir / "project.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
