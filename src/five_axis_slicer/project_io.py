from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CadModel, SelectionState

PROJECT_VERSION = 1


def save_project(directory: str | Path, model: CadModel, selection: SelectionState) -> Path:
    project_dir = Path(directory).expanduser().resolve()
    source_dir = project_dir / "source"
    preview_dir = project_dir / "preview"
    source_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    source_copy = source_dir / model.source_path.name
    shutil.copy2(model.source_path, source_copy)

    payload: dict[str, Any] = {
        "version": PROJECT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "original_path": str(model.source_path),
            "project_path": str(Path("source") / source_copy.name),
            "sha256": model.source_hash,
        },
        "model": {
            "body_count": len(model.bodies),
            "edge_count": len(model.edges),
            "bodies": [body.to_json() for body in model.bodies],
            "edges": [edge.to_json() for edge in model.edges],
        },
        "selection": selection.to_json(),
        "manufacturable_feature_groups": [],
        "preview": {
            "glb": None,
        },
    }

    output = project_dir / "project.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output

