from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, Mapping


RESULT_PREVIEW_SCHEMA_VERSION = 1
RESULT_PREVIEW_STATUSES = frozenset({"empty", "loading", "ready", "warning", "error"})


def _path_or_none(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    return Path(value).expanduser().resolve()


def _json_path(value: Path | None) -> str | None:
    return None if value is None else str(value)


@dataclass(slots=True)
class IllustrativeProcessParameters:
    """Editable values shown beside an imported toolpath.

    These values are presentation metadata in schema version 1. They are kept
    separate from the parsed G-code so editing them cannot invalidate geometry
    or statistics caches.
    """

    layer_height_mm: float = 0.20
    print_speed_mm_min: float = 1200.0
    extrusion_width_mm: float = 0.48
    nozzle_diameter_mm: float = 0.40
    shell_enabled: bool = True
    top_layers: int = 5
    bottom_layers: int = 5

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        positive_values = {
            "layer_height_mm": self.layer_height_mm,
            "print_speed_mm_min": self.print_speed_mm_min,
            "extrusion_width_mm": self.extrusion_width_mm,
            "nozzle_diameter_mm": self.nozzle_diameter_mm,
        }
        for name, value in positive_values.items():
            if not math.isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"{name} must be a finite positive number")
        for name, value in (
            ("top_layers", self.top_layers),
            ("bottom_layers", self.bottom_layers),
        ):
            if isinstance(value, bool) or int(value) != value or int(value) < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    def to_json(self) -> dict[str, Any]:
        return {
            "layer_height_mm": float(self.layer_height_mm),
            "print_speed_mm_min": float(self.print_speed_mm_min),
            "extrusion_width_mm": float(self.extrusion_width_mm),
            "nozzle_diameter_mm": float(self.nozzle_diameter_mm),
            "shell_enabled": bool(self.shell_enabled),
            "top_layers": int(self.top_layers),
            "bottom_layers": int(self.bottom_layers),
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any] | None) -> "IllustrativeProcessParameters":
        values = payload or {}
        return cls(
            layer_height_mm=float(values.get("layer_height_mm", 0.20)),
            print_speed_mm_min=float(values.get("print_speed_mm_min", 1200.0)),
            extrusion_width_mm=float(values.get("extrusion_width_mm", 0.48)),
            nozzle_diameter_mm=float(values.get("nozzle_diameter_mm", 0.40)),
            shell_enabled=bool(values.get("shell_enabled", True)),
            top_layers=int(values.get("top_layers", 5)),
            bottom_layers=int(values.get("bottom_layers", 5)),
        )


@dataclass(frozen=True, slots=True)
class LoadRequest:
    """One immutable background-load request."""

    request_id: int | str = 0
    model_path: Path | None = None
    gcode_path: Path | None = None
    project_path: Path | None = None
    length_unit_override: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_path", _path_or_none(self.model_path))
        object.__setattr__(self, "gcode_path", _path_or_none(self.gcode_path))
        object.__setattr__(self, "project_path", _path_or_none(self.project_path))
        unit_override = (
            None
            if self.length_unit_override is None
            else str(self.length_unit_override).strip() or None
        )
        object.__setattr__(self, "length_unit_override", unit_override)
        if self.model_path is None and self.gcode_path is None and self.project_path is None:
            raise ValueError("A model_path, gcode_path, or project_path is required")
        if self.project_path is not None and (
            self.model_path is not None or self.gcode_path is not None
        ):
            raise ValueError("project_path cannot be combined with model_path or gcode_path")

    def to_json(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "model_path": _json_path(self.model_path),
            "gcode_path": _json_path(self.gcode_path),
            "project_path": _json_path(self.project_path),
            "length_unit_override": self.length_unit_override,
        }


@dataclass(slots=True)
class LoadResult:
    """Objects prepared by a worker and ready for one main-thread commit."""

    request_id: int | str
    model_path: Path | None = None
    gcode_path: Path | None = None
    project_path: Path | None = None
    length_unit_override: str | None = None
    model: Any | None = None
    project: Any | None = None
    gcode_preview: Any | None = None
    gcode_source_index: Any | None = None
    source_audits: dict[str, dict[str, Any]] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def __post_init__(self) -> None:
        self.model_path = _path_or_none(self.model_path)
        self.gcode_path = _path_or_none(self.gcode_path)
        self.project_path = _path_or_none(self.project_path)
        self.length_unit_override = (
            None
            if self.length_unit_override is None
            else str(self.length_unit_override).strip() or None
        )
        self.source_audits = {str(role): dict(audit) for role, audit in self.source_audits.items()}

    @property
    def preview(self) -> Any | None:
        return self.gcode_preview

    @property
    def source_index(self) -> Any | None:
        return self.gcode_source_index

    def close(self) -> None:
        index = self.gcode_source_index
        if index is not None and hasattr(index, "close"):
            index.close()

    def to_json(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "model_path": _json_path(self.model_path),
            "gcode_path": _json_path(self.gcode_path),
            "project_path": _json_path(self.project_path),
            "length_unit_override": self.length_unit_override,
            "has_model": self.model is not None,
            "has_gcode": self.gcode_preview is not None,
            "has_project": self.project is not None,
            "source_audits": {role: dict(audit) for role, audit in self.source_audits.items()},
            "elapsed_seconds": float(self.elapsed_seconds),
        }


@dataclass(slots=True)
class ResultPreviewState:
    """Serializable result-page state with atomic load transition helpers."""

    selected_model_path: Path | None = None
    selected_gcode_path: Path | None = None
    active_model_path: Path | None = None
    active_gcode_path: Path | None = None
    status: str = "empty"
    progress: float = 0.0
    message: str = ""
    parameters: IllustrativeProcessParameters = field(default_factory=IllustrativeProcessParameters)
    quality_mode: str = "paper"
    selected_stage: str = "all"
    playback_progress: float = 1.0
    show_model: bool = True
    show_extrusion: bool = True
    show_travel: bool = False
    show_pose_samples: bool = False
    show_start_end: bool = True
    show_axes: bool = True
    show_orientation_cube: bool = True
    current_request_id: int | str | None = None

    def __post_init__(self) -> None:
        self.selected_model_path = _path_or_none(self.selected_model_path)
        self.selected_gcode_path = _path_or_none(self.selected_gcode_path)
        self.active_model_path = _path_or_none(self.active_model_path)
        self.active_gcode_path = _path_or_none(self.active_gcode_path)
        self._validate_runtime_values()

    def _validate_runtime_values(self) -> None:
        if self.status not in RESULT_PREVIEW_STATUSES:
            raise ValueError(f"Unsupported result preview status: {self.status}")
        self.progress = max(0.0, min(1.0, float(self.progress)))
        self.playback_progress = max(0.0, min(1.0, float(self.playback_progress)))
        self.parameters.validate()

    def begin_load(self, request: LoadRequest) -> None:
        if request.model_path is not None:
            self.selected_model_path = request.model_path
        if request.gcode_path is not None:
            self.selected_gcode_path = request.gcode_path
        self.current_request_id = request.request_id
        self.status = "loading"
        self.progress = 0.0
        self.message = ""

    def update_progress(self, request_id: int | str, fraction: float, message: str = "") -> bool:
        if request_id != self.current_request_id or self.status != "loading":
            return False
        self.progress = max(self.progress, max(0.0, min(1.0, float(fraction))))
        if message:
            self.message = message
        return True

    def commit_load(self, result: LoadResult) -> bool:
        if self.status != "loading" or result.request_id != self.current_request_id:
            return False
        if result.model_path is not None:
            self.active_model_path = result.model_path
            self.selected_model_path = result.model_path
        if result.gcode_path is not None:
            self.active_gcode_path = result.gcode_path
            self.selected_gcode_path = result.gcode_path
        self.status = "ready"
        self.progress = 1.0
        self.message = ""
        self.current_request_id = None
        return True

    def fail_load(self, request_id: int | str, message: str) -> bool:
        if self.status != "loading" or request_id != self.current_request_id:
            return False
        self.status = "error"
        self.message = str(message)
        self.current_request_id = None
        return True

    def cancel_load(self, request_id: int | str) -> bool:
        if self.status != "loading" or request_id != self.current_request_id:
            return False
        self.status = (
            "ready"
            if self.active_model_path is not None or self.active_gcode_path is not None
            else "empty"
        )
        self.progress = 0.0
        self.message = ""
        self.current_request_id = None
        return True

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": RESULT_PREVIEW_SCHEMA_VERSION,
            "parameters_affect_toolpath": False,
            "parameters": self.parameters.to_json(),
            "sources": {
                "selected_model_path": _json_path(self.selected_model_path),
                "selected_gcode_path": _json_path(self.selected_gcode_path),
                "active_model_path": _json_path(self.active_model_path),
                "active_gcode_path": _json_path(self.active_gcode_path),
            },
            "status": {
                "name": self.status,
                "progress": self.progress,
                "message": self.message,
            },
            "display": {
                "quality_mode": self.quality_mode,
                "selected_stage": self.selected_stage,
                "playback_progress": self.playback_progress,
                "show_model": self.show_model,
                "show_extrusion": self.show_extrusion,
                "show_travel": self.show_travel,
                "show_pose_samples": self.show_pose_samples,
                "show_start_end": self.show_start_end,
                "show_axes": self.show_axes,
                "show_orientation_cube": self.show_orientation_cube,
            },
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any] | None) -> "ResultPreviewState":
        values = payload or {}
        sources = values.get("sources") if isinstance(values.get("sources"), Mapping) else {}
        status = values.get("status") if isinstance(values.get("status"), Mapping) else {}
        display = values.get("display") if isinstance(values.get("display"), Mapping) else {}
        parameters = (
            values.get("parameters") if isinstance(values.get("parameters"), Mapping) else {}
        )
        return cls(
            selected_model_path=sources.get("selected_model_path"),
            selected_gcode_path=sources.get("selected_gcode_path"),
            active_model_path=sources.get("active_model_path"),
            active_gcode_path=sources.get("active_gcode_path"),
            status=str(status.get("name", "empty")),
            progress=float(status.get("progress", 0.0)),
            message=str(status.get("message", "")),
            parameters=IllustrativeProcessParameters.from_json(parameters),
            quality_mode=str(display.get("quality_mode", "paper")),
            selected_stage=str(display.get("selected_stage", "all")),
            playback_progress=float(display.get("playback_progress", 1.0)),
            show_model=bool(display.get("show_model", True)),
            show_extrusion=bool(display.get("show_extrusion", True)),
            show_travel=bool(display.get("show_travel", False)),
            show_pose_samples=bool(display.get("show_pose_samples", False)),
            show_start_end=bool(display.get("show_start_end", True)),
            show_axes=bool(display.get("show_axes", True)),
            show_orientation_cube=bool(display.get("show_orientation_cube", True)),
        )
