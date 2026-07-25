from __future__ import annotations

import json
import math
import os  # noqa: F401
import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO, cast

import numpy as np

from .gcode_arrays import (
    _build_role_move_chunks,
    _index_or_none,
    _move_from_code,
    _none_if_nan,
    _role_from_code,
    _rotary_row_to_dict,
    _segments_from_npz,
    _timeline_arrays_from_npz,
    _timeline_arrays_from_steps,  # noqa: F401 - compatibility re-export
    _tuple3,
    _tuple3_or_none,
)
from .manufacturing.preview_kinematics import (
    AC_INVERSE_TRANSFORM,
    MACHINE_COORDINATE_TRANSFORM,
)
from .manufacturing.setup import ValidationIssue
from .native_preview_index import build_preview_index

# Existing failure-injection callers patch this module's ``os.replace``;
# gcode_cache observes the same module object during atomic publication.
NUMBER_RE = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
AXIS_RE = re.compile(rf"([XYZABCUVWEFxyzabcuvwef])\s*({NUMBER_RE})")
COMMAND_RE = re.compile(r"\bG(0|1|20|21|28|90|91|92)\b", re.IGNORECASE)
LAYER_RE = re.compile(r"^Layer\s+(-?\d+)", re.IGNORECASE)
TYPE_RE = re.compile(r"^TYPE\s*:\s*(.+)$", re.IGNORECASE)
WIDTH_RE = re.compile(rf"^WIDTH\s*:\s*({NUMBER_RE})", re.IGNORECASE)
HEIGHT_RE = re.compile(rf"^HEIGHT\s*:\s*({NUMBER_RE})", re.IGNORECASE)
CACHE_VERSION = "gcode-preview-v7-file-coordinate-policy"
# Older preview caches may contain silently ignored rotary axes.  They are
# intentionally invalidated at this safety boundary and rebuilt from source.
LEGACY_CACHE_VERSIONS: tuple[str, ...] = ()
PROGRESS_DOMAIN = "layer_filtered_gcode_order"
DEFAULT_BEAD_WIDTH = 0.4
DEFAULT_LAYER_HEIGHT = 0.2
ProgressCallback = Callable[[float, str], None]
CancelCheck = Callable[[], bool]


class GCodeLoadCancelled(RuntimeError):
    pass


class GCodeSourceIntegrityError(ValueError):
    """The source bytes no longer match the snapshot used by the preview."""


@dataclass(frozen=True, slots=True)
class GCodeSourceFingerprint:
    """Stable identity of the file bytes consumed by ``load_gcode``."""

    sha256: str
    size_bytes: int
    mtime_ns: int

    def __post_init__(self) -> None:
        normalized_hash = str(self.sha256).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized_hash):
            raise ValueError("G-code source SHA-256 must contain 64 hex digits")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise ValueError("G-code source size must be an integer")
        if self.size_bytes < 0:
            raise ValueError("G-code source size cannot be negative")
        if isinstance(self.mtime_ns, bool) or not isinstance(self.mtime_ns, int):
            raise ValueError("G-code source mtime must be an integer")
        if self.mtime_ns < 0:
            raise ValueError("G-code source mtime cannot be negative")
        object.__setattr__(self, "sha256", normalized_hash)

    def to_json(self) -> dict[str, int | str]:
        return {
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
        }

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> GCodeSourceFingerprint:
        if not isinstance(payload, Mapping):
            raise ValueError("G-code source fingerprint must be an object")
        sha256 = payload.get("sha256")
        size_bytes = payload.get("size_bytes")
        mtime_ns = payload.get("mtime_ns")
        if not isinstance(sha256, str):
            raise ValueError("G-code source fingerprint SHA-256 must be a string")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
            raise ValueError("G-code source fingerprint size must be an integer")
        if isinstance(mtime_ns, bool) or not isinstance(mtime_ns, int):
            raise ValueError("G-code source fingerprint mtime must be an integer")
        return cls(
            sha256=sha256,
            size_bytes=size_bytes,
            mtime_ns=mtime_ns,
        )


MOVE_OPTION_COLORS: dict[str, tuple[float, float, float]] = {
    "travel": (0.28, 0.40, 0.86),
    "retract": (0.82, 0.25, 0.84),
    "prime": (0.28, 0.72, 0.86),
    "wipe": (0.98, 0.88, 0.20),
    "noop": (0.38, 0.38, 0.38),
}

ROLE_COLORS: dict[str, tuple[float, float, float]] = {
    "unknown": (0.78, 0.70, 0.70),
    "perimeter": (0.98, 0.84, 0.30),
    "external_perimeter": (1.0, 0.46, 0.24),
    "overhang_perimeter": (0.22, 0.32, 1.0),
    "internal_infill": (0.76, 0.24, 0.20),
    "solid_infill": (0.58, 0.34, 0.78),
    "top_solid_infill": (0.94, 0.28, 0.30),
    "bridge_infill": (0.34, 0.52, 0.82),
    "gap_fill": (0.96, 0.96, 0.88),
    "skirt_brim": (0.00, 0.60, 0.50),
    "support_material": (0.20, 0.82, 0.20),
    "support_interface": (0.12, 0.56, 0.22),
    "wipe_tower": (0.60, 0.78, 0.54),
    "custom": (0.38, 0.86, 0.60),
}

ROLE_LABELS_ZH: dict[str, str] = {
    "unknown": "未知",
    "perimeter": "内壁",
    "external_perimeter": "外壁",
    "overhang_perimeter": "悬垂外壁",
    "internal_infill": "稀疏填充",
    "solid_infill": "实体填充",
    "top_solid_infill": "顶面填充",
    "bridge_infill": "桥接",
    "gap_fill": "间隙填充",
    "skirt_brim": "裙边/边缘",
    "support_material": "支撑",
    "support_interface": "支撑界面",
    "wipe_tower": "擦拭塔",
    "custom": "自定义",
}

ROLE_LABELS_EN: dict[str, str] = {
    "unknown": "Unknown",
    "perimeter": "Perimeter",
    "external_perimeter": "External perimeter",
    "overhang_perimeter": "Overhang perimeter",
    "internal_infill": "Internal infill",
    "solid_infill": "Solid infill",
    "top_solid_infill": "Top solid infill",
    "bridge_infill": "Bridge",
    "gap_fill": "Gap fill",
    "skirt_brim": "Skirt/Brim",
    "support_material": "Support",
    "support_interface": "Support interface",
    "wipe_tower": "Wipe tower",
    "custom": "Custom",
}

MOVE_NAMES: tuple[str, ...] = ("travel", "retract", "prime", "wipe", "noop", "extrude")
MOVE_CODES: dict[str, int] = {name: index for index, name in enumerate(MOVE_NAMES)}
ROLE_NAMES: tuple[str, ...] = tuple(ROLE_COLORS)
ROLE_CODES: dict[str, int] = {name: index for index, name in enumerate(ROLE_NAMES)}
ROTARY_AXES: tuple[str, ...] = ("A", "B", "C", "U", "V", "W")
TIMELINE_FLAG_HAS_SPATIAL_AXIS = 1
TIMELINE_FLAG_HAS_SPATIAL_LENGTH = 2
TIMELINE_FLAG_AC_TRANSFORM = 4


TYPE_ROLE_MAP: dict[str, str] = {
    "inner wall": "perimeter",
    "wall-inner": "perimeter",
    "perimeter": "perimeter",
    "outer wall": "external_perimeter",
    "wall-outer": "external_perimeter",
    "external perimeter": "external_perimeter",
    "overhang wall": "overhang_perimeter",
    "overhang perimeter": "overhang_perimeter",
    "sparse infill": "internal_infill",
    "fill": "internal_infill",
    "infill": "internal_infill",
    "internal infill": "internal_infill",
    "solid infill": "solid_infill",
    "internal solid infill": "solid_infill",
    "solid-fill": "solid_infill",
    "bottom surface": "solid_infill",
    "skin": "solid_infill",
    "top surface": "top_solid_infill",
    "top solid infill": "top_solid_infill",
    "gap infill": "gap_fill",
    "gap fill": "gap_fill",
    "bridge": "bridge_infill",
    "internal bridge": "bridge_infill",
    "bridge infill": "bridge_infill",
    "brim": "skirt_brim",
    "skirt": "skirt_brim",
    "raft": "skirt_brim",
    "support": "support_material",
    "support material": "support_material",
    "support-interface": "support_interface",
    "support interface": "support_interface",
    "prime tower": "wipe_tower",
    "prime-tower": "wipe_tower",
    "wipe tower": "wipe_tower",
    "custom": "custom",
}

COMMENT_ROLE_HINTS: tuple[tuple[str, str], ...] = (
    ("brim", "skirt_brim"),
    ("skirt", "skirt_brim"),
    ("support interface", "support_interface"),
    ("support", "support_material"),
    ("bridge", "bridge_infill"),
    ("infill", "internal_infill"),
    ("perimeter", "perimeter"),
)


@dataclass(slots=True)
class GCodePathSegment:
    step_index: int
    line_number: int
    layer: int
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    rotary_start: dict[str, float] = field(default_factory=dict)
    rotary_end: dict[str, float] = field(default_factory=dict)
    move_type: str = "noop"
    extrusion_role: str = "unknown"
    feedrate: float | None = None
    delta_e: float = 0.0
    width: float | None = None
    height: float | None = None
    comment: str = ""
    raw: str = ""
    machine_start: tuple[float, float, float] | None = None
    machine_end: tuple[float, float, float] | None = None
    coordinate_transform: str = MACHINE_COORDINATE_TRANSFORM

    @property
    def has_spatial_length(self) -> bool:
        return any(
            abs(left - right) > 1e-9 for left, right in zip(self.start, self.end, strict=False)
        )

    @property
    def bead_width(self) -> float:
        return self.width if self.width is not None else DEFAULT_BEAD_WIDTH

    @property
    def bead_height(self) -> float:
        return self.height if self.height is not None else DEFAULT_LAYER_HEIGHT

    def color_key(self) -> str:
        if self.move_type == "extrude":
            return self.extrusion_role
        return self.move_type

    def color(self) -> tuple[float, float, float]:
        if self.move_type == "extrude":
            return ROLE_COLORS.get(self.extrusion_role, ROLE_COLORS["unknown"])
        return MOVE_OPTION_COLORS.get(self.move_type, MOVE_OPTION_COLORS["noop"])

    def to_json(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "line_number": self.line_number,
            "layer": self.layer,
            "start": list(self.start),
            "end": list(self.end),
            "rotary_start": dict(self.rotary_start),
            "rotary_end": dict(self.rotary_end),
            "move_type": self.move_type,
            "extrusion_role": self.extrusion_role,
            "feedrate": self.feedrate,
            "delta_e": self.delta_e,
            "width": self.width,
            "height": self.height,
            "comment": self.comment,
            "machine_start": (None if self.machine_start is None else list(self.machine_start)),
            "machine_end": None if self.machine_end is None else list(self.machine_end),
            "coordinate_transform": self.coordinate_transform,
        }


@dataclass(slots=True)
class GCodeTimelineStep:
    step_index: int
    line_number: int
    layer: int
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    rotary_start: dict[str, float] = field(default_factory=dict)
    rotary_end: dict[str, float] = field(default_factory=dict)
    move_type: str = "noop"
    extrusion_role: str = "unknown"
    feedrate: float | None = None
    delta_e: float = 0.0
    width: float | None = None
    height: float | None = None
    comment: str = ""
    raw: str = ""
    machine_start: tuple[float, float, float] | None = None
    machine_end: tuple[float, float, float] | None = None
    coordinate_transform: str = MACHINE_COORDINATE_TRANSFORM
    has_spatial_axis: bool = False
    has_spatial_length: bool = False
    path_segment_index: int | None = None

    @property
    def bead_width(self) -> float:
        return self.width if self.width is not None else DEFAULT_BEAD_WIDTH

    @property
    def bead_height(self) -> float:
        return self.height if self.height is not None else DEFAULT_LAYER_HEIGHT

    def color_key(self) -> str:
        if self.move_type == "extrude":
            return self.extrusion_role
        return self.move_type

    def color(self) -> tuple[float, float, float]:
        if self.move_type == "extrude":
            return ROLE_COLORS.get(self.extrusion_role, ROLE_COLORS["unknown"])
        return MOVE_OPTION_COLORS.get(self.move_type, MOVE_OPTION_COLORS["noop"])

    def to_json(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "line_number": self.line_number,
            "layer": self.layer,
            "start": list(self.start),
            "end": list(self.end),
            "rotary_start": dict(self.rotary_start),
            "rotary_end": dict(self.rotary_end),
            "move_type": self.move_type,
            "extrusion_role": self.extrusion_role,
            "feedrate": self.feedrate,
            "delta_e": self.delta_e,
            "width": self.width,
            "height": self.height,
            "comment": self.comment,
            "machine_start": (None if self.machine_start is None else list(self.machine_start)),
            "machine_end": None if self.machine_end is None else list(self.machine_end),
            "coordinate_transform": self.coordinate_transform,
            "has_spatial_axis": self.has_spatial_axis,
            "has_spatial_length": self.has_spatial_length,
            "path_segment_index": self.path_segment_index,
        }


@dataclass(slots=True)
class GCodeTimelineArrays:
    line_numbers: np.ndarray
    layers: np.ndarray
    starts: np.ndarray
    ends: np.ndarray
    rotary_starts: np.ndarray
    rotary_ends: np.ndarray
    move_codes: np.ndarray
    role_codes: np.ndarray
    feedrates: np.ndarray
    delta_es: np.ndarray
    widths: np.ndarray
    heights: np.ndarray
    machine_starts: np.ndarray
    machine_ends: np.ndarray
    flags: np.ndarray
    path_segment_indices: np.ndarray

    @property
    def count(self) -> int:
        return int(self.line_numbers.size)

    def step_at(self, index: int) -> GCodeTimelineStep | None:
        if index < 0 or index >= self.count:
            return None
        flags = int(self.flags[index])
        return GCodeTimelineStep(
            step_index=index,
            line_number=int(self.line_numbers[index]),
            layer=int(self.layers[index]),
            start=_tuple3(self.starts[index]),
            end=_tuple3(self.ends[index]),
            rotary_start=_rotary_row_to_dict(self.rotary_starts[index]),
            rotary_end=_rotary_row_to_dict(self.rotary_ends[index]),
            move_type=_move_from_code(int(self.move_codes[index])),
            extrusion_role=_role_from_code(int(self.role_codes[index])),
            feedrate=_none_if_nan(float(self.feedrates[index])),
            delta_e=float(self.delta_es[index]),
            width=_none_if_nan(float(self.widths[index])),
            height=_none_if_nan(float(self.heights[index])),
            comment="",
            raw="",
            machine_start=_tuple3_or_none(self.machine_starts[index]),
            machine_end=_tuple3_or_none(self.machine_ends[index]),
            coordinate_transform=(
                AC_INVERSE_TRANSFORM
                if flags & TIMELINE_FLAG_AC_TRANSFORM
                else MACHINE_COORDINATE_TRANSFORM
            ),
            has_spatial_axis=bool(flags & TIMELINE_FLAG_HAS_SPATIAL_AXIS),
            has_spatial_length=bool(flags & TIMELINE_FLAG_HAS_SPATIAL_LENGTH),
            path_segment_index=_index_or_none(int(self.path_segment_indices[index])),
        )


@dataclass(slots=True)
class GCodeRenderIndex:
    layer_min: int
    layer_max: int
    layer_prefix_counts: np.ndarray
    timeline_indices: np.ndarray
    segment_step_indices: np.ndarray
    segment_indices: np.ndarray
    role_move_chunks: list[dict[str, Any]]
    source: str = "python"
    cache_format: str = "memory+render-index-v2"

    @classmethod
    def build(
        cls,
        timeline: list[GCodeTimelineStep],
        segments: list[GCodePathSegment],
        layer_min: int,
        layer_max: int,
    ) -> GCodeRenderIndex:
        packed = build_preview_index(
            [step.layer for step in timeline],
            [segment.step_index for segment in segments],
            layer_min,
            layer_max,
        )
        return cls(
            layer_min,
            layer_max,
            packed.layer_prefix_counts,
            packed.timeline_indices,
            packed.segment_step_indices,
            packed.segment_indices,
            _build_role_move_chunks(segments),
            packed.source,
        )

    @classmethod
    def from_npz(cls, path: Path, segments: list[GCodePathSegment]) -> GCodeRenderIndex:
        with np.load(path, allow_pickle=False) as payload:
            return cls(
                int(payload["layer_min"][0]),
                int(payload["layer_max"][0]),
                np.asarray(payload["layer_prefix_counts"], dtype=np.int32),
                np.asarray(payload["timeline_indices"], dtype=np.int32),
                np.asarray(payload["segment_step_indices"], dtype=np.int32),
                np.asarray(payload["segment_indices"], dtype=np.int32),
                _build_role_move_chunks(segments),
                str(payload["source"][0]) if "source" in payload else "npz",
                "json.gz+npz-render-index-v2",
            )

    def to_npz(self, path: Path) -> None:
        np.savez_compressed(
            path,
            layer_min=np.asarray([self.layer_min], dtype=np.int32),
            layer_max=np.asarray([self.layer_max], dtype=np.int32),
            layer_prefix_counts=self.layer_prefix_counts.astype(np.int32, copy=False),
            timeline_indices=self.timeline_indices.astype(np.int32, copy=False),
            segment_step_indices=self.segment_step_indices.astype(np.int32, copy=False),
            segment_indices=self.segment_indices.astype(np.int32, copy=False),
            source=np.asarray([self.source]),
        )

    def count_for_layers(self, layer_min: int, layer_max: int) -> int:
        if self.layer_max < self.layer_min:
            return 0
        low = max(self.layer_min, min(layer_min, layer_max))
        high = min(self.layer_max, max(layer_min, layer_max))
        if high < low:
            return 0
        low_offset = low - self.layer_min
        high_offset = high - self.layer_min + 1
        return int(self.layer_prefix_counts[high_offset] - self.layer_prefix_counts[low_offset])

    def timeline_index_for_layer_progress(
        self,
        layer_min: int,
        layer_max: int,
        progress_index: int,
    ) -> tuple[int | None, int, int]:
        count = self.count_for_layers(layer_min, layer_max)
        if count == 0:
            return None, 0, 0

        low = max(self.layer_min, min(layer_min, layer_max))
        low_offset = low - self.layer_min
        base = int(self.layer_prefix_counts[low_offset])
        index = max(0, min(progress_index, count - 1))
        absolute = base + index
        if absolute < 0 or absolute >= int(self.timeline_indices.size):
            return None, index, count
        return int(self.timeline_indices[absolute]), index, count

    def segment_index_for_step(self, step_index: int) -> int | None:
        if self.segment_step_indices.size == 0:
            return None
        location = int(np.searchsorted(self.segment_step_indices, int(step_index), side="left"))
        if location >= int(self.segment_step_indices.size):
            return None
        if int(self.segment_step_indices[location]) != int(step_index):
            return None
        return int(self.segment_indices[location])

    def nearest_segment_index_for_step(self, step_index: int) -> int | None:
        if self.segment_step_indices.size == 0:
            return None
        location = (
            int(np.searchsorted(self.segment_step_indices, int(step_index), side="right")) - 1
        )
        if location < 0:
            location = 0
        return int(self.segment_indices[location])


@dataclass(slots=True)
class GCodePreview:
    source_path: Path
    segments: list[GCodePathSegment]
    total_segment_count: int
    layer_min: int
    layer_max: int
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]] | None
    move_counts: dict[str, int]
    role_counts: dict[str, int]
    rotary_axes: list[str]
    coordinate_transform: str = MACHINE_COORDINATE_TRANSFORM
    timeline: list[GCodeTimelineStep] = field(default_factory=list)
    height_min: float | None = None
    height_max: float | None = None
    render_index: GCodeRenderIndex | None = None
    timeline_arrays: GCodeTimelineArrays | None = None
    controller_semantics: str | None = None
    validation_issues: tuple[ValidationIssue, ...] = ()
    source_fingerprint: GCodeSourceFingerprint | None = None

    @property
    def layer_count(self) -> int:
        return 0 if self.layer_max < self.layer_min else self.layer_max - self.layer_min + 1

    @property
    def has_five_axis_words(self) -> bool:
        return bool(self.rotary_axes)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "segment_count": self.total_segment_count,
            "stored_segment_count": len(self.segments),
            "layer_min": self.layer_min,
            "layer_max": self.layer_max,
            "layer_count": self.layer_count,
            "move_counts": dict(self.move_counts),
            "role_counts": dict(self.role_counts),
            "rotary_axes": list(self.rotary_axes),
            "coordinate_transform": self.coordinate_transform,
            "controller_semantics": self.controller_semantics,
            "validation_issues": [issue.to_json() for issue in self.validation_issues],
            "timeline_step_count": self._timeline_count(),
            "height_range": (
                None
                if self.height_min is None or self.height_max is None
                else {
                    "min": self.height_min,
                    "max": self.height_max,
                }
            ),
            "progress_domain": PROGRESS_DOMAIN,
            "cache_format": self._index().cache_format,
            "render_index_source": self._index().source,
            "role_move_chunk_count": len(self._index().role_move_chunks),
            "bounds": (
                None
                if self.bounds is None
                else {
                    "min": list(self.bounds[0]),
                    "max": list(self.bounds[1]),
                }
            ),
        }

    def timeline_count_for_layers(self, layer_min: int, layer_max: int) -> int:
        return self._index().count_for_layers(layer_min, layer_max)

    def timeline_step_for_layer_progress(
        self,
        layer_min: int,
        layer_max: int,
        progress_index: int,
    ) -> GCodeTimelineStep | None:
        if not self.timeline and self.timeline_arrays is None:
            return None
        (
            timeline_index,
            _index,
            _count,
        ) = self._index().timeline_index_for_layer_progress(
            layer_min,
            layer_max,
            progress_index,
        )
        if timeline_index is None:
            return None
        if self.timeline:
            return self.timeline[timeline_index]
        return (
            self.timeline_arrays.step_at(timeline_index)
            if self.timeline_arrays is not None
            else None
        )

    def progress_state(self, layer_min: int, layer_max: int, progress_index: int) -> dict[str, Any]:
        timeline_index, index, count = self._index().timeline_index_for_layer_progress(
            layer_min,
            layer_max,
            progress_index,
        )
        if count == 0:
            return {
                "domain": PROGRESS_DOMAIN,
                "layer_min": layer_min,
                "layer_max": layer_max,
                "layer_step_count": 0,
                "progress_index": 0,
                "progress_percent": 0.0,
                "current_global_step": None,
                "current_step": None,
            }
        if timeline_index is None:
            step = None
        elif self.timeline:
            step = self.timeline[timeline_index]
        elif self.timeline_arrays is not None:
            step = self.timeline_arrays.step_at(timeline_index)
        else:
            step = None
        return {
            "domain": PROGRESS_DOMAIN,
            "layer_min": layer_min,
            "layer_max": layer_max,
            "layer_step_count": count,
            "progress_index": index,
            "progress_percent": 0.0 if count <= 1 else index / (count - 1),
            "current_global_step": None if step is None else step.step_index,
            "current_step": None if step is None else step.to_json(),
        }

    def segment_index_for_step(self, step_index: int) -> int | None:
        return self._index().segment_index_for_step(step_index)

    def nearest_segment_index_for_step(self, step_index: int) -> int | None:
        return self._index().nearest_segment_index_for_step(step_index)

    def _index(self) -> GCodeRenderIndex:
        if self.render_index is None:
            self.render_index = GCodeRenderIndex.build(
                self.timeline,
                self.segments,
                self.layer_min,
                self.layer_max,
            )
        return self.render_index

    def _timeline_count(self) -> int:
        if self.timeline_arrays is not None:
            return self.timeline_arrays.count
        return len(self.timeline)


@dataclass(slots=True)
class PreviewSettings:
    layer_min: int = 0
    layer_max: int = 0
    show_travel: bool = True
    show_extrusion: bool = True
    show_pose_samples: bool = True
    visible_roles: set[str] = field(default_factory=lambda: set(ROLE_COLORS))
    progress_index: int = 0
    show_upcoming: bool = True
    solid_rendering: bool = True
    quality_mode: str = "auto"
    render_backend: str = "opengl"

    def to_json(self) -> dict[str, Any]:
        return {
            "layer_min": self.layer_min,
            "layer_max": self.layer_max,
            "show_travel": self.show_travel,
            "show_extrusion": self.show_extrusion,
            "show_pose_samples": self.show_pose_samples,
            "visible_roles": sorted(self.visible_roles),
            "progress_index": self.progress_index,
            "show_upcoming": self.show_upcoming,
            "solid_rendering": self.solid_rendering,
            "quality_mode": self.quality_mode,
            "render_backend": self.render_backend,
            "role_colors": {role: rgb_to_hex(color) for role, color in ROLE_COLORS.items()},
            "move_colors": {move: rgb_to_hex(color) for move, color in MOVE_OPTION_COLORS.items()},
        }


def load_gcode(
    path: str | Path,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
) -> GCodePreview:
    source_path = _validated_gcode_path(path)
    _raise_if_cancelled(cancel_check)
    if progress_callback is not None:
        progress_callback(0.02, "cache")
    initial_fingerprint = _capture_source_fingerprint(
        source_path,
        expected_sha256=source_sha256,
        cancel_check=cancel_check,
    )
    source_size_bytes = initial_fingerprint.size_bytes
    cache_source_sha256 = initial_fingerprint.sha256
    cached = _load_preview_cache(
        source_path,
        source_sha256=cache_source_sha256,
        controller_semantics=controller_semantics,
    )
    if cached is not None:
        _assert_source_unchanged(source_path, initial_fingerprint, cancel_check)
        cached.source_fingerprint = initial_fingerprint
        if progress_callback is not None:
            progress_callback(1.0, "cache")
        return cached

    preview = _parse_gcode_file(
        source_path,
        source_size_bytes,
        progress_callback,
        cancel_check,
        controller_semantics,
    )
    _assert_source_unchanged(source_path, initial_fingerprint, cancel_check)
    preview.source_fingerprint = initial_fingerprint
    if progress_callback is not None:
        progress_callback(0.98, "cache_write")
    _persist_preview_cache(preview, cache_source_sha256, cancel_check)
    _raise_if_cancelled(cancel_check)
    if progress_callback is not None:
        progress_callback(1.0, "ready")
    return preview


def _validated_gcode_path(path: str | Path) -> Path:
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"G-code file not found: {source_path}")
    if source_path.suffix.lower() not in {".gcode", ".nc", ".tap", ".txt"}:
        raise ValueError(f"Expected .gcode, .nc, .tap or .txt file: {source_path}")
    return source_path


def _parse_gcode_file(
    source_path: Path,
    source_size: int,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck | None,
    controller_semantics: str | None,
) -> GCodePreview:
    sample_stride = max(1, math.ceil(source_size / 25_000_000))
    with source_path.open("r", encoding="utf-8", errors="replace") as stream:
        return parse_gcode_lines(
            _iter_source_lines(stream, source_size, progress_callback, cancel_check),
            source_path,
            sample_stride=sample_stride,
            cancel_check=cancel_check,
            controller_semantics=controller_semantics,
        )


def _iter_source_lines(
    stream: TextIO,
    source_size: int,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck | None,
) -> Iterator[str]:
    line_count = 0
    while True:
        raw_line = stream.readline()
        if not raw_line:
            return
        line_count += 1
        if line_count % 4096 == 0:
            _raise_if_cancelled(cancel_check)
            if progress_callback is not None:
                try:
                    fraction = min(0.97, max(0.03, stream.tell() / max(1, source_size)))
                except OSError:
                    fraction = 0.03
                progress_callback(fraction, "parse")
        yield raw_line


def _assert_source_unchanged(
    source_path: Path,
    initial: GCodeSourceFingerprint,
    cancel_check: CancelCheck | None,
) -> None:
    final = _capture_source_fingerprint(
        source_path,
        expected_sha256=initial.sha256,
        cancel_check=cancel_check,
    )
    if final != initial:
        raise GCodeSourceIntegrityError(f"G-code source changed while loading: {source_path}")


def _persist_preview_cache(
    preview: GCodePreview,
    source_sha256: str,
    cancel_check: CancelCheck | None,
) -> None:
    """Keep a valid parse when persistence fails; cancellation still propagates."""

    try:
        _write_preview_cache(
            preview,
            cancel_check=cancel_check,
            source_sha256=source_sha256,
        )
    except GCodeLoadCancelled:
        raise
    except Exception:
        _raise_if_cancelled(cancel_check)


def parse_gcode(
    text: str,
    source_path: str | Path = "<memory>",
    sample_stride: int = 1,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    controller_semantics: str | None = None,
) -> GCodePreview:
    return parse_gcode_lines(
        text.splitlines(),
        source_path,
        sample_stride=sample_stride,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        controller_semantics=controller_semantics,
    )


def parse_gcode_lines(
    lines: Any,
    source_path: str | Path = "<memory>",
    sample_stride: int = 1,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    controller_semantics: str | None = None,
) -> GCodePreview:
    from .gcode_parser import parse_lines

    return parse_lines(
        lines,
        source_path,
        sample_stride,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        controller_semantics=controller_semantics,
    )


def normalize_role(raw_role: str) -> str:
    from .gcode_parser import normalize_role as parse_role

    return parse_role(raw_role)


def role_label(role: str, language: str) -> str:
    labels = ROLE_LABELS_EN if language == "en" else ROLE_LABELS_ZH
    return labels.get(role, role)


def rgb_to_hex(color: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(channel * 255)))):02X}" for channel in color)


def preview_to_json(preview: GCodePreview) -> str:
    return json.dumps(
        {
            "summary": preview.summary(),
            "segments": [segment.to_json() for segment in preview.segments],
            "timeline": [step.to_json() for step in preview.timeline],
        },
        ensure_ascii=False,
        indent=2,
    )


def preview_from_json(payload: dict[str, Any], source_path: Path) -> GCodePreview:
    summary = payload["summary"]
    default_transform = summary.get("coordinate_transform", MACHINE_COORDINATE_TRANSFORM)
    height_min, height_max = _summary_height_range(summary)
    return GCodePreview(
        source_path,
        [_segment_from_json(item, default_transform) for item in payload.get("segments", [])],
        int(summary["segment_count"]),
        int(summary["layer_min"]),
        int(summary["layer_max"]),
        _summary_bounds(summary),
        dict(summary.get("move_counts", {})),
        dict(summary.get("role_counts", {})),
        list(summary.get("rotary_axes", [])),
        default_transform,
        [_timeline_step_from_json(item, default_transform) for item in payload.get("timeline", [])],
        height_min,
        height_max,
        controller_semantics=summary.get("controller_semantics"),
        validation_issues=_summary_issues(summary),
    )


def _segment_from_json(item: Mapping[str, Any], default_transform: str) -> GCodePathSegment:
    return GCodePathSegment(
        step_index=item.get("step_index", item.get("line_number", 0) - 1),
        line_number=item["line_number"],
        layer=item["layer"],
        start=_json_point(item["start"]),
        end=_json_point(item["end"]),
        rotary_start=dict(item.get("rotary_start", {})),
        rotary_end=dict(item.get("rotary_end", {})),
        move_type=item["move_type"],
        extrusion_role=item["extrusion_role"],
        feedrate=item.get("feedrate"),
        delta_e=item.get("delta_e", 0.0),
        width=item.get("width"),
        height=item.get("height"),
        comment=item.get("comment", ""),
        machine_start=_optional_json_point(item.get("machine_start")),
        machine_end=_optional_json_point(item.get("machine_end")),
        coordinate_transform=item.get("coordinate_transform", default_transform),
    )


def _timeline_step_from_json(item: Mapping[str, Any], default_transform: str) -> GCodeTimelineStep:
    return GCodeTimelineStep(
        step_index=item["step_index"],
        line_number=item["line_number"],
        layer=item["layer"],
        start=_json_point(item["start"]),
        end=_json_point(item["end"]),
        rotary_start=dict(item.get("rotary_start", {})),
        rotary_end=dict(item.get("rotary_end", {})),
        move_type=item["move_type"],
        extrusion_role=item["extrusion_role"],
        feedrate=item.get("feedrate"),
        delta_e=item.get("delta_e", 0.0),
        width=item.get("width"),
        height=item.get("height"),
        comment=item.get("comment", ""),
        machine_start=_optional_json_point(item.get("machine_start")),
        machine_end=_optional_json_point(item.get("machine_end")),
        coordinate_transform=item.get("coordinate_transform", default_transform),
        has_spatial_axis=bool(item.get("has_spatial_axis", False)),
        has_spatial_length=bool(item.get("has_spatial_length", False)),
        path_segment_index=item.get("path_segment_index"),
    )


def _json_point(value: Any) -> tuple[float, float, float]:
    return cast(tuple[float, float, float], tuple(value))


def _optional_json_point(value: Any) -> tuple[float, float, float] | None:
    return None if value is None else _json_point(value)


def _summary_bounds(
    summary: Mapping[str, Any],
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    payload = summary.get("bounds")
    if payload is None:
        return None
    return (_json_point(payload["min"]), _json_point(payload["max"]))


def _summary_height_range(
    summary: Mapping[str, Any],
) -> tuple[float | None, float | None]:
    payload = summary.get("height_range")
    if payload is None:
        return None, None
    return float(payload["min"]), float(payload["max"])


def _summary_issues(summary: Mapping[str, Any]) -> tuple[ValidationIssue, ...]:
    return tuple(ValidationIssue.from_json(item) for item in summary.get("validation_issues", ()))


def _preview_from_binary_cache(
    payload: dict[str, Any], source_path: Path, index_path: Path
) -> GCodePreview:
    summary = payload["summary"]
    height_min, height_max = _summary_height_range(summary)
    with np.load(index_path, allow_pickle=False) as arrays:
        segments = _segments_from_npz(arrays)
        timeline_arrays = _timeline_arrays_from_npz(arrays)
        render_index = GCodeRenderIndex.from_npz(index_path, segments)
    return GCodePreview(
        source_path,
        segments,
        int(summary["segment_count"]),
        int(summary["layer_min"]),
        int(summary["layer_max"]),
        _summary_bounds(summary),
        dict(summary.get("move_counts", {})),
        dict(summary.get("role_counts", {})),
        list(summary.get("rotary_axes", [])),
        summary.get("coordinate_transform", MACHINE_COORDINATE_TRANSFORM),
        [],
        height_min,
        height_max,
        render_index,
        timeline_arrays,
        summary.get("controller_semantics"),
        _summary_issues(summary),
    )


def _file_sha256(source_path: Path, *, cancel_check: CancelCheck | None = None) -> str:
    from .gcode_cache import file_sha256

    return file_sha256(source_path, cancel_check=cancel_check)


def _capture_source_fingerprint(
    source_path: Path,
    *,
    expected_sha256: str | None = None,
    cancel_check: CancelCheck | None = None,
) -> GCodeSourceFingerprint:
    from .gcode_cache import capture_source_fingerprint

    return capture_source_fingerprint(
        source_path,
        expected_sha256=expected_sha256,
        cancel_check=cancel_check,
    )


def _cache_stem(
    source_path: Path,
    version: str = CACHE_VERSION,
    *,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
) -> Path:
    from .gcode_cache import cache_stem

    return cache_stem(
        source_path,
        version,
        source_sha256=source_sha256,
        controller_semantics=controller_semantics,
    )


def _cache_file(
    source_path: Path,
    version: str,
    suffix: str,
    source_sha256: str | None,
    controller_semantics: str | None,
) -> Path:
    if source_sha256 is None and controller_semantics is None:
        stem = _cache_stem(source_path, version)
    else:
        stem = _cache_stem(
            source_path,
            version,
            source_sha256=source_sha256,
            controller_semantics=controller_semantics,
        )
    return stem.with_suffix(suffix)


def _cache_path(
    source_path: Path,
    version: str = CACHE_VERSION,
    *,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
) -> Path:
    return _cache_file(
        source_path,
        version,
        ".json.gz",
        source_sha256,
        controller_semantics,
    )


def _cache_index_path(
    source_path: Path,
    version: str = CACHE_VERSION,
    *,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
) -> Path:
    return _cache_file(
        source_path,
        version,
        ".npz",
        source_sha256,
        controller_semantics,
    )


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise GCodeLoadCancelled("G-code loading cancelled")


def _load_preview_cache(
    source_path: Path,
    *,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
) -> GCodePreview | None:
    from .gcode_cache import load_preview_cache

    return load_preview_cache(
        source_path,
        stem_factory=_cache_stem,
        source_sha256=source_sha256,
        controller_semantics=controller_semantics,
    )


def _write_preview_cache(
    preview: GCodePreview,
    *,
    cancel_check: CancelCheck | None = None,
    source_sha256: str | None = None,
) -> None:
    from .gcode_cache import write_preview_cache

    write_preview_cache(
        preview,
        stem_factory=_cache_stem,
        cancel_check=cancel_check,
        source_sha256=source_sha256,
    )
