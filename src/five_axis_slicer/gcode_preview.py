from __future__ import annotations

from dataclasses import dataclass, field
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping
import uuid

import numpy as np

from .gcode_source import application_cache_dir
from .manufacturing.preview_kinematics import (
    AC_INVERSE_TRANSFORM,
    DEFAULT_PREVIEW_KINEMATICS_REGISTRY,
    MACHINE_COORDINATE_TRANSFORM,
    NC_PREVIEW_OBJECT_ID,
    reconstruct_preview_motion,
)
from .manufacturing.setup import IssueSeverity, ValidationIssue
from .native_preview_index import build_preview_index


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
    def from_json(cls, payload: Mapping[str, Any]) -> "GCodeSourceFingerprint":
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
            abs(left - right) > 1e-9 for left, right in zip(self.start, self.end)
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
            "machine_start": (
                None if self.machine_start is None else list(self.machine_start)
            ),
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
            "machine_start": (
                None if self.machine_start is None else list(self.machine_start)
            ),
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
    ) -> "GCodeRenderIndex":
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
    def from_npz(
        cls, path: Path, segments: list[GCodePathSegment]
    ) -> "GCodeRenderIndex":
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
        return int(
            self.layer_prefix_counts[high_offset] - self.layer_prefix_counts[low_offset]
        )

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
        location = int(
            np.searchsorted(self.segment_step_indices, int(step_index), side="left")
        )
        if location >= int(self.segment_step_indices.size):
            return None
        if int(self.segment_step_indices[location]) != int(step_index):
            return None
        return int(self.segment_indices[location])

    def nearest_segment_index_for_step(self, step_index: int) -> int | None:
        if self.segment_step_indices.size == 0:
            return None
        location = (
            int(
                np.searchsorted(
                    self.segment_step_indices, int(step_index), side="right"
                )
            )
            - 1
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
        return (
            0
            if self.layer_max < self.layer_min
            else self.layer_max - self.layer_min + 1
        )

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

    def progress_state(
        self, layer_min: int, layer_max: int, progress_index: int
    ) -> dict[str, Any]:
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


def _build_role_move_chunks(segments: list[GCodePathSegment]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    if not segments:
        return chunks

    start = 0
    previous = (
        segments[0].layer,
        segments[0].move_type,
        segments[0].extrusion_role,
        segments[0].color_key(),
    )
    for index, segment in enumerate(segments[1:], start=1):
        current = (
            segment.layer,
            segment.move_type,
            segment.extrusion_role,
            segment.color_key(),
        )
        if current == previous:
            continue
        layer, move_type, role, color_key = previous
        chunks.append(
            {
                "start": start,
                "end": index,
                "layer": layer,
                "move_type": move_type,
                "extrusion_role": role,
                "color_key": color_key,
            }
        )
        start = index
        previous = current

    layer, move_type, role, color_key = previous
    chunks.append(
        {
            "start": start,
            "end": len(segments),
            "layer": layer,
            "move_type": move_type,
            "extrusion_role": role,
            "color_key": color_key,
        }
    )
    return chunks


def _timeline_arrays_from_steps(steps: list[GCodeTimelineStep]) -> GCodeTimelineArrays:
    count = len(steps)
    return GCodeTimelineArrays(
        line_numbers=np.asarray([step.line_number for step in steps], dtype=np.int32),
        layers=np.asarray([step.layer for step in steps], dtype=np.int32),
        starts=_points_array([step.start for step in steps]),
        ends=_points_array([step.end for step in steps]),
        rotary_starts=_rotary_array([step.rotary_start for step in steps]),
        rotary_ends=_rotary_array([step.rotary_end for step in steps]),
        move_codes=np.asarray(
            [MOVE_CODES.get(step.move_type, MOVE_CODES["noop"]) for step in steps],
            dtype=np.uint8,
        ),
        role_codes=np.asarray(
            [
                ROLE_CODES.get(step.extrusion_role, ROLE_CODES["unknown"])
                for step in steps
            ],
            dtype=np.uint8,
        ),
        feedrates=np.asarray(
            [_nan_if_none(step.feedrate) for step in steps], dtype=np.float32
        ),
        delta_es=np.asarray([step.delta_e for step in steps], dtype=np.float32),
        widths=np.asarray(
            [_nan_if_none(step.width) for step in steps], dtype=np.float32
        ),
        heights=np.asarray(
            [_nan_if_none(step.height) for step in steps], dtype=np.float32
        ),
        machine_starts=_optional_points_array([step.machine_start for step in steps]),
        machine_ends=_optional_points_array([step.machine_end for step in steps]),
        flags=np.asarray([_timeline_flags(step) for step in steps], dtype=np.uint8),
        path_segment_indices=(
            np.asarray(
                [
                    -1 if step.path_segment_index is None else step.path_segment_index
                    for step in steps
                ],
                dtype=np.int32,
            )
            if count
            else np.empty((0,), dtype=np.int32)
        ),
    )


def _timeline_arrays_from_npz(payload: Any) -> GCodeTimelineArrays:
    return GCodeTimelineArrays(
        line_numbers=np.asarray(payload["timeline_line_numbers"], dtype=np.int32),
        layers=np.asarray(payload["timeline_layers"], dtype=np.int32),
        starts=np.asarray(payload["timeline_starts"], dtype=np.float32),
        ends=np.asarray(payload["timeline_ends"], dtype=np.float32),
        rotary_starts=np.asarray(payload["timeline_rotary_starts"], dtype=np.float32),
        rotary_ends=np.asarray(payload["timeline_rotary_ends"], dtype=np.float32),
        move_codes=np.asarray(payload["timeline_move_codes"], dtype=np.uint8),
        role_codes=np.asarray(payload["timeline_role_codes"], dtype=np.uint8),
        feedrates=np.asarray(payload["timeline_feedrates"], dtype=np.float32),
        delta_es=np.asarray(payload["timeline_delta_es"], dtype=np.float32),
        widths=np.asarray(payload["timeline_widths"], dtype=np.float32),
        heights=np.asarray(payload["timeline_heights"], dtype=np.float32),
        machine_starts=np.asarray(payload["timeline_machine_starts"], dtype=np.float32),
        machine_ends=np.asarray(payload["timeline_machine_ends"], dtype=np.float32),
        flags=np.asarray(payload["timeline_flags"], dtype=np.uint8),
        path_segment_indices=np.asarray(
            payload["timeline_path_segment_indices"], dtype=np.int32
        ),
    )


def _segment_npz_arrays(segments: list[GCodePathSegment]) -> dict[str, np.ndarray]:
    return {
        "segment_step_indices": np.asarray(
            [segment.step_index for segment in segments], dtype=np.int32
        ),
        "segment_line_numbers": np.asarray(
            [segment.line_number for segment in segments], dtype=np.int32
        ),
        "segment_layers": np.asarray(
            [segment.layer for segment in segments], dtype=np.int32
        ),
        "segment_starts": _points_array([segment.start for segment in segments]),
        "segment_ends": _points_array([segment.end for segment in segments]),
        "segment_rotary_starts": _rotary_array(
            [segment.rotary_start for segment in segments]
        ),
        "segment_rotary_ends": _rotary_array(
            [segment.rotary_end for segment in segments]
        ),
        "segment_move_codes": np.asarray(
            [
                MOVE_CODES.get(segment.move_type, MOVE_CODES["noop"])
                for segment in segments
            ],
            dtype=np.uint8,
        ),
        "segment_role_codes": np.asarray(
            [
                ROLE_CODES.get(segment.extrusion_role, ROLE_CODES["unknown"])
                for segment in segments
            ],
            dtype=np.uint8,
        ),
        "segment_feedrates": np.asarray(
            [_nan_if_none(segment.feedrate) for segment in segments], dtype=np.float32
        ),
        "segment_delta_es": np.asarray(
            [segment.delta_e for segment in segments], dtype=np.float32
        ),
        "segment_widths": np.asarray(
            [_nan_if_none(segment.width) for segment in segments], dtype=np.float32
        ),
        "segment_heights": np.asarray(
            [_nan_if_none(segment.height) for segment in segments], dtype=np.float32
        ),
        "segment_machine_starts": _optional_points_array(
            [segment.machine_start for segment in segments]
        ),
        "segment_machine_ends": _optional_points_array(
            [segment.machine_end for segment in segments]
        ),
        "segment_flags": np.asarray(
            [
                (
                    TIMELINE_FLAG_AC_TRANSFORM
                    if segment.coordinate_transform == AC_INVERSE_TRANSFORM
                    else 0
                )
                for segment in segments
            ],
            dtype=np.uint8,
        ),
    }


def _segments_from_npz(payload: Any) -> list[GCodePathSegment]:
    step_indices = np.asarray(payload["segment_step_indices"], dtype=np.int32)
    line_numbers = np.asarray(payload["segment_line_numbers"], dtype=np.int32)
    layers = np.asarray(payload["segment_layers"], dtype=np.int32)
    starts = np.asarray(payload["segment_starts"], dtype=np.float32)
    ends = np.asarray(payload["segment_ends"], dtype=np.float32)
    rotary_starts = np.asarray(payload["segment_rotary_starts"], dtype=np.float32)
    rotary_ends = np.asarray(payload["segment_rotary_ends"], dtype=np.float32)
    move_codes = np.asarray(payload["segment_move_codes"], dtype=np.uint8)
    role_codes = np.asarray(payload["segment_role_codes"], dtype=np.uint8)
    feedrates = np.asarray(payload["segment_feedrates"], dtype=np.float32)
    delta_es = np.asarray(payload["segment_delta_es"], dtype=np.float32)
    widths = np.asarray(payload["segment_widths"], dtype=np.float32)
    heights = np.asarray(payload["segment_heights"], dtype=np.float32)
    machine_starts = np.asarray(payload["segment_machine_starts"], dtype=np.float32)
    machine_ends = np.asarray(payload["segment_machine_ends"], dtype=np.float32)
    flags = np.asarray(payload["segment_flags"], dtype=np.uint8)

    segments: list[GCodePathSegment] = []
    for index in range(int(step_indices.size)):
        transform = (
            AC_INVERSE_TRANSFORM
            if int(flags[index]) & TIMELINE_FLAG_AC_TRANSFORM
            else MACHINE_COORDINATE_TRANSFORM
        )
        segments.append(
            GCodePathSegment(
                step_index=int(step_indices[index]),
                line_number=int(line_numbers[index]),
                layer=int(layers[index]),
                start=_tuple3(starts[index]),
                end=_tuple3(ends[index]),
                rotary_start=_rotary_row_to_dict(rotary_starts[index]),
                rotary_end=_rotary_row_to_dict(rotary_ends[index]),
                move_type=_move_from_code(int(move_codes[index])),
                extrusion_role=_role_from_code(int(role_codes[index])),
                feedrate=_none_if_nan(float(feedrates[index])),
                delta_e=float(delta_es[index]),
                width=_none_if_nan(float(widths[index])),
                height=_none_if_nan(float(heights[index])),
                comment="",
                raw="",
                machine_start=_tuple3_or_none(machine_starts[index]),
                machine_end=_tuple3_or_none(machine_ends[index]),
                coordinate_transform=transform,
            )
        )
    return segments


def _timeline_flags(step: GCodeTimelineStep) -> int:
    flags = 0
    if step.has_spatial_axis:
        flags |= TIMELINE_FLAG_HAS_SPATIAL_AXIS
    if step.has_spatial_length:
        flags |= TIMELINE_FLAG_HAS_SPATIAL_LENGTH
    if step.coordinate_transform == AC_INVERSE_TRANSFORM:
        flags |= TIMELINE_FLAG_AC_TRANSFORM
    return flags


def _points_array(points: list[tuple[float, float, float]]) -> np.ndarray:
    if not points:
        return np.empty((0, 3), dtype=np.float32)
    return np.asarray(points, dtype=np.float32).reshape((-1, 3))


def _optional_points_array(
    points: list[tuple[float, float, float] | None]
) -> np.ndarray:
    if not points:
        return np.empty((0, 3), dtype=np.float32)
    output = np.full((len(points), 3), np.nan, dtype=np.float32)
    for index, point in enumerate(points):
        if point is not None:
            output[index, :] = point
    return output


def _rotary_array(rotaries: list[dict[str, float]]) -> np.ndarray:
    if not rotaries:
        return np.empty((0, len(ROTARY_AXES)), dtype=np.float32)
    output = np.full((len(rotaries), len(ROTARY_AXES)), np.nan, dtype=np.float32)
    for row, rotary in enumerate(rotaries):
        for column, axis in enumerate(ROTARY_AXES):
            if axis in rotary:
                output[row, column] = rotary[axis]
    return output


def _rotary_row_to_dict(row: np.ndarray) -> dict[str, float]:
    values: dict[str, float] = {}
    for index, axis in enumerate(ROTARY_AXES):
        value = float(row[index])
        if not math.isnan(value) and abs(value) > 1e-9:
            values[axis] = value
    return values


def _tuple3(row: np.ndarray) -> tuple[float, float, float]:
    return (float(row[0]), float(row[1]), float(row[2]))


def _tuple3_or_none(row: np.ndarray) -> tuple[float, float, float] | None:
    if np.isnan(row).any():
        return None
    return _tuple3(row)


def _none_if_nan(value: float) -> float | None:
    return None if math.isnan(value) else value


def _nan_if_none(value: float | None) -> float:
    return float("nan") if value is None else float(value)


def _index_or_none(value: int) -> int | None:
    return None if value < 0 else value


def _move_from_code(code: int) -> str:
    if 0 <= code < len(MOVE_NAMES):
        return MOVE_NAMES[code]
    return "noop"


def _role_from_code(code: int) -> str:
    if 0 <= code < len(ROLE_NAMES):
        return ROLE_NAMES[code]
    return "unknown"


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
            "role_colors": {
                role: rgb_to_hex(color) for role, color in ROLE_COLORS.items()
            },
            "move_colors": {
                move: rgb_to_hex(color) for move, color in MOVE_OPTION_COLORS.items()
            },
        }


def load_gcode(
    path: str | Path,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
) -> GCodePreview:
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"G-code file not found: {source_path}")
    if source_path.suffix.lower() not in {".gcode", ".nc", ".tap", ".txt"}:
        raise ValueError(f"Expected .gcode, .nc, .tap or .txt file: {source_path}")
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
        _raise_if_cancelled(cancel_check)
        final_fingerprint = _capture_source_fingerprint(
            source_path,
            expected_sha256=initial_fingerprint.sha256,
            cancel_check=cancel_check,
        )
        if final_fingerprint != initial_fingerprint:
            raise GCodeSourceIntegrityError(
                f"G-code source changed while loading: {source_path}"
            )
        cached.source_fingerprint = initial_fingerprint
        if progress_callback is not None:
            progress_callback(1.0, "cache")
        return cached
    sample_stride = max(1, math.ceil(source_size_bytes / 25_000_000))
    source_size = max(1, source_size_bytes)
    with source_path.open("r", encoding="utf-8", errors="replace") as stream:

        def iter_lines():
            line_count = 0
            while True:
                raw_line = stream.readline()
                if not raw_line:
                    break
                line_count += 1
                if line_count % 4096 == 0:
                    _raise_if_cancelled(cancel_check)
                    if progress_callback is not None:
                        try:
                            fraction = min(0.97, max(0.03, stream.tell() / source_size))
                        except OSError:
                            fraction = 0.03
                        progress_callback(fraction, "parse")
                yield raw_line

        preview = parse_gcode_lines(
            iter_lines(),
            source_path,
            sample_stride=sample_stride,
            progress_callback=None,
            cancel_check=cancel_check,
            controller_semantics=controller_semantics,
        )
    _raise_if_cancelled(cancel_check)
    final_fingerprint = _capture_source_fingerprint(
        source_path,
        expected_sha256=initial_fingerprint.sha256,
        cancel_check=cancel_check,
    )
    if final_fingerprint != initial_fingerprint:
        raise GCodeSourceIntegrityError(
            f"G-code source changed while loading: {source_path}"
        )
    preview.source_fingerprint = initial_fingerprint
    if progress_callback is not None:
        progress_callback(0.98, "cache_write")
    try:
        _write_preview_cache(
            preview,
            cancel_check=cancel_check,
            source_sha256=cache_source_sha256,
        )
    except GCodeLoadCancelled:
        raise
    except Exception:
        # A cache is optional. Keep a valid parsed result when persistence is
        # unavailable, then re-check cancellation before reporting readiness.
        _raise_if_cancelled(cancel_check)
    _raise_if_cancelled(cancel_check)
    if progress_callback is not None:
        progress_callback(1.0, "ready")
    return preview


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
    source = Path(source_path)
    state = _ParserState()
    segments: list[GCodePathSegment] = []
    timeline: list[GCodeTimelineStep] = []
    stats = _PreviewStats(controller_semantics)
    sample_stride = max(1, int(sample_stride))

    total_lines = len(lines) if hasattr(lines, "__len__") else None
    for line_number, raw_line in enumerate(lines, start=1):
        if line_number == 1 or line_number % 4096 == 0:
            _raise_if_cancelled(cancel_check)
            if progress_callback is not None and total_lines:
                progress_callback(min(1.0, line_number / max(1, total_lines)), "parse")
        raw = raw_line.strip()
        if not raw:
            continue

        code, comment = _split_comment(raw)
        if comment:
            _apply_comment_tag(state, comment)
        if not code:
            continue

        command, words = _parse_code(code)
        if command is None:
            _apply_modal_command(state, code)
            if state.motion_command in {"G0", "G1"} and words:
                command = state.motion_command
            else:
                continue

        if command in {"G90", "G91"}:
            state.absolute_xyz = command == "G90"
            continue
        if command in {"G20", "G21"}:
            state.units = 25.4 if command == "G20" else 1.0
            continue
        if command == "G92":
            _apply_g92_words(state, words)
            continue
        if command == "G28":
            for axis in ("X", "Y", "Z"):
                if axis in words or not any(key in words for key in ("X", "Y", "Z")):
                    state.axes[axis] = 0.0
            continue
        if command not in {"G0", "G1"}:
            continue

        state.motion_command = command
        values = _apply_motion_words(state, command, words)
        if values is not None:
            step_index = stats.timeline_step_count
            reconstruction = reconstruct_preview_motion(
                values.start_xyz,
                values.end_xyz,
                values.rotary_start,
                values.rotary_end,
                controller_semantics=controller_semantics,
            )
            display_start = reconstruction.start
            display_end = reconstruction.end
            transform_name = reconstruction.coordinate_transform
            has_spatial_length = _points_differ(display_start, display_end)
            stats.add_values(
                values.move_type,
                values.extrusion_role,
                values.layer,
                display_start,
                display_end,
                values.rotary_start,
                values.rotary_end,
                has_spatial_length,
                transform_name,
                values.count_path_segment,
                values.height,
                reconstruction.issues,
            )
            path_segment_index = None
            if (
                values.count_path_segment
                and stats.total_segment_count % sample_stride == 0
            ):
                path_segment_index = len(segments)
                segments.append(
                    _make_segment(
                        values,
                        step_index,
                        line_number,
                        raw,
                        comment,
                        display_start,
                        display_end,
                        transform_name,
                    )
                )
            timeline.append(
                _make_timeline_step(
                    values,
                    step_index,
                    line_number,
                    raw,
                    comment,
                    display_start,
                    display_end,
                    transform_name,
                    has_spatial_length,
                    path_segment_index,
                )
            )

    _finalize_file_coordinate_policy(segments, timeline, stats)
    _raise_if_cancelled(cancel_check)
    if progress_callback is not None:
        progress_callback(1.0, "parse")
    return _build_preview(source, segments, timeline, stats)


def role_label(role: str, language: str) -> str:
    labels = ROLE_LABELS_EN if language == "en" else ROLE_LABELS_ZH
    return labels.get(role, role)


def rgb_to_hex(color: tuple[float, float, float]) -> str:
    return "#" + "".join(
        f"{max(0, min(255, int(round(channel * 255)))):02X}" for channel in color
    )


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
    bounds_payload = summary.get("bounds")
    bounds = None
    if bounds_payload is not None:
        bounds = (tuple(bounds_payload["min"]), tuple(bounds_payload["max"]))
    segments = [
        GCodePathSegment(
            step_index=item.get("step_index", item.get("line_number", 0) - 1),
            line_number=item["line_number"],
            layer=item["layer"],
            start=tuple(item["start"]),
            end=tuple(item["end"]),
            rotary_start=dict(item.get("rotary_start", {})),
            rotary_end=dict(item.get("rotary_end", {})),
            move_type=item["move_type"],
            extrusion_role=item["extrusion_role"],
            feedrate=item.get("feedrate"),
            delta_e=item.get("delta_e", 0.0),
            width=item.get("width"),
            height=item.get("height"),
            comment=item.get("comment", ""),
            machine_start=(
                None
                if item.get("machine_start") is None
                else tuple(item["machine_start"])
            ),
            machine_end=(
                None if item.get("machine_end") is None else tuple(item["machine_end"])
            ),
            coordinate_transform=item.get(
                "coordinate_transform",
                summary.get("coordinate_transform", MACHINE_COORDINATE_TRANSFORM),
            ),
        )
        for item in payload.get("segments", [])
    ]
    timeline = [
        GCodeTimelineStep(
            step_index=item["step_index"],
            line_number=item["line_number"],
            layer=item["layer"],
            start=tuple(item["start"]),
            end=tuple(item["end"]),
            rotary_start=dict(item.get("rotary_start", {})),
            rotary_end=dict(item.get("rotary_end", {})),
            move_type=item["move_type"],
            extrusion_role=item["extrusion_role"],
            feedrate=item.get("feedrate"),
            delta_e=item.get("delta_e", 0.0),
            width=item.get("width"),
            height=item.get("height"),
            comment=item.get("comment", ""),
            machine_start=(
                None
                if item.get("machine_start") is None
                else tuple(item["machine_start"])
            ),
            machine_end=(
                None if item.get("machine_end") is None else tuple(item["machine_end"])
            ),
            coordinate_transform=item.get(
                "coordinate_transform",
                summary.get("coordinate_transform", MACHINE_COORDINATE_TRANSFORM),
            ),
            has_spatial_axis=bool(item.get("has_spatial_axis", False)),
            has_spatial_length=bool(item.get("has_spatial_length", False)),
            path_segment_index=item.get("path_segment_index"),
        )
        for item in payload.get("timeline", [])
    ]
    return GCodePreview(
        source_path,
        segments,
        int(summary["segment_count"]),
        int(summary["layer_min"]),
        int(summary["layer_max"]),
        bounds,
        dict(summary.get("move_counts", {})),
        dict(summary.get("role_counts", {})),
        list(summary.get("rotary_axes", [])),
        summary.get("coordinate_transform", MACHINE_COORDINATE_TRANSFORM),
        timeline,
        (
            None
            if summary.get("height_range") is None
            else float(summary["height_range"]["min"])
        ),
        (
            None
            if summary.get("height_range") is None
            else float(summary["height_range"]["max"])
        ),
        controller_semantics=summary.get("controller_semantics"),
        validation_issues=tuple(
            ValidationIssue.from_json(item)
            for item in summary.get("validation_issues", ())
        ),
    )


def _preview_from_binary_cache(
    payload: dict[str, Any], source_path: Path, index_path: Path
) -> GCodePreview:
    summary = payload["summary"]
    bounds_payload = summary.get("bounds")
    bounds = None
    if bounds_payload is not None:
        bounds = (tuple(bounds_payload["min"]), tuple(bounds_payload["max"]))
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
        bounds,
        dict(summary.get("move_counts", {})),
        dict(summary.get("role_counts", {})),
        list(summary.get("rotary_axes", [])),
        summary.get("coordinate_transform", MACHINE_COORDINATE_TRANSFORM),
        [],
        (
            None
            if summary.get("height_range") is None
            else float(summary["height_range"]["min"])
        ),
        (
            None
            if summary.get("height_range") is None
            else float(summary["height_range"]["max"])
        ),
        render_index,
        timeline_arrays,
        summary.get("controller_semantics"),
        tuple(
            ValidationIssue.from_json(item)
            for item in summary.get("validation_issues", ())
        ),
    )


class _ParserState:
    def __init__(self) -> None:
        self.axes = {
            axis: 0.0 for axis in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W", "E")
        }
        self.unregistered_rotary_words_seen: set[str] = set()
        self.feedrate: float | None = None
        self.absolute_xyz = True
        self.relative_e = True
        self.units = 1.0
        self.motion_command: str | None = None
        self.layer = -1
        self.current_role = "unknown"
        self.current_width: float | None = DEFAULT_BEAD_WIDTH
        self.current_height: float | None = DEFAULT_LAYER_HEIGHT


@dataclass(slots=True)
class _MotionValues:
    move_type: str
    extrusion_role: str
    layer: int
    start_xyz: tuple[float, float, float]
    end_xyz: tuple[float, float, float]
    rotary_start: dict[str, float]
    rotary_end: dict[str, float]
    has_linear_motion: bool
    feedrate: float | None
    delta_e: float
    width: float | None
    height: float | None
    count_path_segment: bool


def _split_comment(line: str) -> tuple[str, str]:
    if ";" not in line:
        return line.strip(), ""
    code, comment = line.split(";", 1)
    return code.strip(), comment.strip()


def _parse_words(code: str) -> dict[str, float]:
    return {axis.upper(): float(value) for axis, value in AXIS_RE.findall(code)}


def _parse_code(code: str) -> tuple[str | None, dict[str, float]]:
    command: str | None = None
    words: dict[str, float] = {}
    for token in code.split():
        if not token:
            continue
        head = token[0].upper()
        value = token[1:]
        if head == "G":
            try:
                number = int(float(value))
            except ValueError:
                continue
            if number in {0, 1, 20, 21, 28, 90, 91, 92}:
                command = f"G{number}"
        elif head in "XYZABCUVWEF" and value:
            try:
                words[head] = float(value)
            except ValueError:
                continue
    if command is None and "G" in code.upper():
        command_match = COMMAND_RE.search(code)
        if command_match is not None:
            command = f"G{command_match.group(1)}".upper()
    if not words and any(axis in code.upper() for axis in "XYZABCUVWEF"):
        words = _parse_words(code)
    return command, words


def _apply_modal_command(state: _ParserState, code: str) -> None:
    upper = code.upper()
    if "M82" in upper:
        state.relative_e = False
    elif "M83" in upper:
        state.relative_e = True


def _apply_g92_words(state: _ParserState, words: dict[str, float]) -> None:
    state.unregistered_rotary_words_seen.update(
        axis for axis in ("U", "V", "W") if axis in words
    )
    for axis in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W", "E"):
        if axis not in words:
            continue
        state.axes[axis] = (
            words[axis] * state.units if axis in {"X", "Y", "Z"} else words[axis]
        )


def _apply_comment_tag(state: _ParserState, comment: str) -> None:
    type_match = TYPE_RE.match(comment)
    if type_match is not None:
        state.current_role = normalize_role(type_match.group(1))
        return

    width_match = WIDTH_RE.match(comment)
    if width_match is not None:
        state.current_width = float(width_match.group(1))
        return

    height_match = HEIGHT_RE.match(comment)
    if height_match is not None:
        state.current_height = float(height_match.group(1))
        return

    if comment.upper().startswith("LAYER_CHANGE"):
        state.layer = 0 if state.layer < 0 else state.layer + 1
        return

    layer_match = LAYER_RE.match(comment)
    if layer_match is not None:
        state.layer = int(layer_match.group(1))
        return

    hinted = _role_from_comment_hint(comment)
    if hinted is not None:
        state.current_role = hinted


def normalize_role(raw_role: str) -> str:
    role = re.sub(r"\s+", " ", raw_role.strip()).lower()
    role = role.replace("_", " ")
    return TYPE_ROLE_MAP.get(role, "unknown")


def _role_from_comment_hint(comment: str) -> str | None:
    cleaned = re.sub(r"[^A-Za-z ]+", " ", comment).lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for token, role in COMMENT_ROLE_HINTS:
        if token in cleaned:
            return role
    return None


def _apply_motion_words(
    state: _ParserState,
    command: str,
    words: dict[str, float],
) -> _MotionValues | None:
    start_xyz = (state.axes["X"], state.axes["Y"], state.axes["Z"])
    start_rotary = {axis: state.axes[axis] for axis in ("A", "B", "C", "U", "V", "W")}
    start_e = state.axes["E"]
    if "F" in words:
        state.feedrate = words["F"]

    has_spatial_axis = any(
        axis in words for axis in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W")
    )
    state.unregistered_rotary_words_seen.update(
        axis for axis in ("U", "V", "W") if axis in words
    )
    for axis in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W"):
        if axis in words:
            value = (
                words[axis] * state.units if axis in {"X", "Y", "Z"} else words[axis]
            )
            state.axes[axis] = (
                state.axes[axis] + value if not state.absolute_xyz else value
            )

    if "E" in words:
        if state.relative_e:
            delta_e = words["E"]
            state.axes["E"] += words["E"]
        else:
            delta_e = words["E"] - start_e
            state.axes["E"] = words["E"]
    else:
        delta_e = 0.0

    end_xyz = (state.axes["X"], state.axes["Y"], state.axes["Z"])
    end_rotary = {axis: state.axes[axis] for axis in ("A", "B", "C", "U", "V", "W")}
    linear_motion = any(
        abs(left - right) > 1e-9 for left, right in zip(start_xyz, end_xyz)
    )
    rotary_motion = any(
        abs(start_rotary[axis] - end_rotary[axis]) > 1e-9 for axis in start_rotary
    )
    e_motion = abs(delta_e) > 1e-12
    if not has_spatial_axis and not e_motion:
        return None

    move_type = _classify_move(
        command, linear_motion or rotary_motion, linear_motion, delta_e
    )
    if has_spatial_axis and not e_motion and move_type == "noop":
        move_type = "travel"
    rotary_start = {
        axis: value
        for axis, value in start_rotary.items()
        if abs(value) > 1e-9 or axis in state.unregistered_rotary_words_seen
    }
    rotary_end = {
        axis: value
        for axis, value in end_rotary.items()
        if abs(value) > 1e-9 or axis in state.unregistered_rotary_words_seen
    }
    return _MotionValues(
        move_type=move_type,
        extrusion_role=state.current_role,
        layer=max(state.layer, 0),
        start_xyz=start_xyz,
        end_xyz=end_xyz,
        rotary_start=rotary_start,
        rotary_end=rotary_end,
        has_linear_motion=linear_motion,
        feedrate=state.feedrate,
        delta_e=delta_e,
        width=state.current_width,
        height=state.current_height,
        count_path_segment=has_spatial_axis,
    )


def _make_segment(
    values: _MotionValues,
    step_index: int,
    line_number: int,
    raw: str,
    comment: str,
    display_start: tuple[float, float, float],
    display_end: tuple[float, float, float],
    coordinate_transform: str,
) -> GCodePathSegment:
    return GCodePathSegment(
        step_index=step_index,
        line_number=line_number,
        layer=values.layer,
        start=display_start,
        end=display_end,
        rotary_start=values.rotary_start,
        rotary_end=values.rotary_end,
        move_type=values.move_type,
        extrusion_role=values.extrusion_role,
        feedrate=values.feedrate,
        delta_e=values.delta_e,
        width=values.width,
        height=values.height,
        comment=comment,
        raw=raw,
        machine_start=values.start_xyz,
        machine_end=values.end_xyz,
        coordinate_transform=coordinate_transform,
    )


def _make_timeline_step(
    values: _MotionValues,
    step_index: int,
    line_number: int,
    raw: str,
    comment: str,
    display_start: tuple[float, float, float],
    display_end: tuple[float, float, float],
    coordinate_transform: str,
    has_spatial_length: bool,
    path_segment_index: int | None,
) -> GCodeTimelineStep:
    return GCodeTimelineStep(
        step_index=step_index,
        line_number=line_number,
        layer=values.layer,
        start=display_start,
        end=display_end,
        rotary_start=values.rotary_start,
        rotary_end=values.rotary_end,
        move_type=values.move_type,
        extrusion_role=values.extrusion_role,
        feedrate=values.feedrate,
        delta_e=values.delta_e,
        width=values.width,
        height=values.height,
        comment=comment,
        raw=raw,
        machine_start=values.start_xyz,
        machine_end=values.end_xyz,
        coordinate_transform=coordinate_transform,
        has_spatial_axis=values.count_path_segment,
        has_spatial_length=has_spatial_length,
        path_segment_index=path_segment_index,
    )


def _finalize_file_coordinate_policy(
    segments: list[GCodePathSegment],
    timeline: list[GCodeTimelineStep],
    stats: _PreviewStats,
) -> None:
    """Commit one coordinate space for every motion in an imported NC file."""

    present_words: set[str] = set()
    active_words: set[str] = set()
    for step in timeline:
        for rotary_values in (step.rotary_start, step.rotary_end):
            present_words.update(rotary_values)
            active_words.update(
                word
                for word, value in rotary_values.items()
                if abs(float(value)) > 1.0e-12
            )

    semantics_required_words = active_words | (present_words & {"U", "V", "W"})
    if not semantics_required_words:
        _apply_file_coordinate_result(
            segments,
            timeline,
            stats,
            MACHINE_COORDINATE_TRANSFORM,
            (),
        )
        return

    semantics = DEFAULT_PREVIEW_KINEMATICS_REGISTRY.get(stats.controller_semantics)
    if semantics is None:
        issue = ValidationIssue(
            code="nc_preview.controller_semantics_unknown",
            severity=IssueSeverity.WARNING,
            object_id=NC_PREVIEW_OBJECT_ID,
            context={
                "controller_semantics": (
                    ""
                    if stats.controller_semantics is None
                    else str(stats.controller_semantics)
                ),
                "active_rotary_words": sorted(active_words),
                "present_rotary_words": sorted(present_words),
            },
        )
        _apply_file_coordinate_result(
            segments,
            timeline,
            stats,
            MACHINE_COORDINATE_TRANSFORM,
            (issue,),
        )
        return

    unsupported_words = sorted(
        (active_words - semantics.supported_rotary_words)
        | ((present_words & {"U", "V", "W"}) - semantics.supported_rotary_words)
    )
    if unsupported_words:
        issue = ValidationIssue(
            code="nc_preview.rotary_words_unsupported",
            severity=IssueSeverity.WARNING,
            object_id=NC_PREVIEW_OBJECT_ID,
            context={
                "controller_semantics": semantics.semantics_id,
                "unsupported_rotary_words": unsupported_words,
                "active_rotary_words": sorted(active_words),
                "present_rotary_words": sorted(present_words),
            },
        )
        _apply_file_coordinate_result(
            segments,
            timeline,
            stats,
            MACHINE_COORDINATE_TRANSFORM,
            (issue,),
        )
        return

    if stats.validation_issues:
        _apply_file_coordinate_result(
            segments,
            timeline,
            stats,
            MACHINE_COORDINATE_TRANSFORM,
            tuple(stats.validation_issues),
        )
        return

    _apply_file_coordinate_result(
        segments,
        timeline,
        stats,
        semantics.transform_name,
        (),
    )


def _apply_file_coordinate_result(
    segments: list[GCodePathSegment],
    timeline: list[GCodeTimelineStep],
    stats: _PreviewStats,
    coordinate_transform: str,
    issues: tuple[ValidationIssue, ...],
) -> None:
    use_machine_coordinates = coordinate_transform == MACHINE_COORDINATE_TRANSFORM
    for segment in segments:
        if use_machine_coordinates:
            if segment.machine_start is not None:
                segment.start = segment.machine_start
            if segment.machine_end is not None:
                segment.end = segment.machine_end
        segment.coordinate_transform = coordinate_transform

    for step in timeline:
        if use_machine_coordinates:
            if step.machine_start is not None:
                step.start = step.machine_start
            if step.machine_end is not None:
                step.end = step.machine_end
        step.coordinate_transform = coordinate_transform
        step.has_spatial_length = _points_differ(step.start, step.end)

    stats.finalize_coordinate_result(timeline, coordinate_transform, issues)


def _points_differ(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> bool:
    return any(abs(left - right) > 1e-9 for left, right in zip(start, end))


def _classify_move(
    command: str, has_motion: bool, linear_motion: bool, delta_e: float
) -> str:
    if command == "G0":
        return "travel"
    if delta_e < -1e-12:
        return "travel" if has_motion else "retract"
    if delta_e > 1e-12:
        if has_motion:
            return "extrude"
        return "prime"
    if linear_motion or has_motion:
        return "travel"
    return "noop"


class _PreviewStats:
    def __init__(self, controller_semantics: str | None = None) -> None:
        self.total_segment_count = 0
        self.timeline_step_count = 0
        self.move_counts: dict[str, int] = {}
        self.role_counts: dict[str, int] = {}
        self.rotary_axes: set[str] = set()
        self.layer_min: int | None = None
        self.layer_max: int | None = None
        self.bounds_min: list[float] | None = None
        self.bounds_max: list[float] | None = None
        self.height_min: float | None = None
        self.height_max: float | None = None
        self.coordinate_transform = MACHINE_COORDINATE_TRANSFORM
        self.controller_semantics = controller_semantics
        self.validation_issues: list[ValidationIssue] = []
        self._issue_keys: set[str] = set()
        self._coordinate_transforms: set[str] = set()

    def add(self, segment: GCodePathSegment) -> None:
        self.add_values(
            segment.move_type,
            segment.extrusion_role,
            segment.layer,
            segment.start,
            segment.end,
            segment.rotary_start,
            segment.rotary_end,
            segment.has_spatial_length,
            segment.coordinate_transform,
            True,
            segment.height,
        )

    def add_values(
        self,
        move_type: str,
        extrusion_role: str,
        layer: int,
        start: tuple[float, float, float],
        end: tuple[float, float, float],
        rotary_start: dict[str, float],
        rotary_end: dict[str, float],
        has_spatial_length: bool,
        coordinate_transform: str = MACHINE_COORDINATE_TRANSFORM,
        count_path_segment: bool = True,
        height: float | None = None,
        validation_issues: tuple[ValidationIssue, ...] = (),
    ) -> None:
        self.timeline_step_count += 1
        if count_path_segment:
            self.total_segment_count += 1
        self._coordinate_transforms.add(coordinate_transform)
        for issue in validation_issues:
            key = json.dumps(issue.to_json(), ensure_ascii=True, sort_keys=True)
            if key not in self._issue_keys:
                self._issue_keys.add(key)
                self.validation_issues.append(issue)
        if (
            AC_INVERSE_TRANSFORM in self._coordinate_transforms
            and not self.validation_issues
        ):
            self.coordinate_transform = AC_INVERSE_TRANSFORM
        else:
            self.coordinate_transform = MACHINE_COORDINATE_TRANSFORM
        self.move_counts[move_type] = self.move_counts.get(move_type, 0) + 1
        if move_type == "extrude":
            self.role_counts[extrusion_role] = (
                self.role_counts.get(extrusion_role, 0) + 1
            )
        if height is not None:
            self.height_min = (
                height if self.height_min is None else min(self.height_min, height)
            )
            self.height_max = (
                height if self.height_max is None else max(self.height_max, height)
            )
        for axis in set(rotary_start) | set(rotary_end):
            self.rotary_axes.add(axis)
        self.layer_min = layer if self.layer_min is None else min(self.layer_min, layer)
        self.layer_max = layer if self.layer_max is None else max(self.layer_max, layer)
        if has_spatial_length:
            for point in (start, end):
                if self.bounds_min is None or self.bounds_max is None:
                    self.bounds_min = [point[0], point[1], point[2]]
                    self.bounds_max = [point[0], point[1], point[2]]
                else:
                    for index in range(3):
                        self.bounds_min[index] = min(
                            self.bounds_min[index], point[index]
                        )
                        self.bounds_max[index] = max(
                            self.bounds_max[index], point[index]
                        )

    def finalize_coordinate_result(
        self,
        timeline: list[GCodeTimelineStep],
        coordinate_transform: str,
        issues: tuple[ValidationIssue, ...],
    ) -> None:
        self.coordinate_transform = coordinate_transform
        self._coordinate_transforms = {coordinate_transform}
        self.validation_issues = []
        self._issue_keys = set()
        for issue in issues:
            key = json.dumps(issue.to_json(), ensure_ascii=True, sort_keys=True)
            if key not in self._issue_keys:
                self._issue_keys.add(key)
                self.validation_issues.append(issue)

        self.bounds_min = None
        self.bounds_max = None
        for step in timeline:
            if not step.has_spatial_length:
                continue
            for point in (step.start, step.end):
                if self.bounds_min is None or self.bounds_max is None:
                    self.bounds_min = [point[0], point[1], point[2]]
                    self.bounds_max = [point[0], point[1], point[2]]
                    continue
                for index in range(3):
                    self.bounds_min[index] = min(self.bounds_min[index], point[index])
                    self.bounds_max[index] = max(self.bounds_max[index], point[index])


def _build_preview(
    source: Path,
    segments: list[GCodePathSegment],
    timeline: list[GCodeTimelineStep],
    stats: _PreviewStats,
) -> GCodePreview:
    if stats.total_segment_count == 0 and stats.timeline_step_count == 0:
        return GCodePreview(
            source,
            [],
            0,
            0,
            -1,
            None,
            {},
            {},
            [],
            timeline=[],
            controller_semantics=stats.controller_semantics,
            validation_issues=tuple(stats.validation_issues),
        )

    bounds = None
    if stats.bounds_min is not None and stats.bounds_max is not None:
        bounds = (
            (
                stats.bounds_min[0],
                stats.bounds_min[1],
                stats.bounds_min[2],
            ),
            (
                stats.bounds_max[0],
                stats.bounds_max[1],
                stats.bounds_max[2],
            ),
        )

    return GCodePreview(
        source,
        segments,
        stats.total_segment_count,
        stats.layer_min or 0,
        stats.layer_max if stats.layer_max is not None else -1,
        bounds,
        stats.move_counts,
        stats.role_counts,
        sorted(stats.rotary_axes),
        stats.coordinate_transform,
        timeline,
        stats.height_min,
        stats.height_max,
        controller_semantics=stats.controller_semantics,
        validation_issues=tuple(stats.validation_issues),
    )


def _file_sha256(source_path: Path, *, cancel_check: CancelCheck | None = None) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            _raise_if_cancelled(cancel_check)
            digest.update(chunk)
    _raise_if_cancelled(cancel_check)
    return digest.hexdigest()


def _capture_source_fingerprint(
    source_path: Path,
    *,
    expected_sha256: str | None = None,
    cancel_check: CancelCheck | None = None,
) -> GCodeSourceFingerprint:
    """Hash a stable file snapshot and optionally bind it to an expected hash."""

    before = source_path.stat()
    digest = _file_sha256(source_path, cancel_check=cancel_check)
    after = source_path.stat()
    if int(after.st_size) != int(before.st_size) or int(after.st_mtime_ns) != int(
        before.st_mtime_ns
    ):
        raise GCodeSourceIntegrityError(
            f"G-code source changed while hashing: {source_path}"
        )
    fingerprint = GCodeSourceFingerprint(
        sha256=digest,
        size_bytes=int(after.st_size),
        mtime_ns=int(after.st_mtime_ns),
    )
    if expected_sha256 is not None:
        normalized_expected = str(expected_sha256).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized_expected):
            raise GCodeSourceIntegrityError(
                "expected G-code source SHA-256 must contain 64 hex digits"
            )
        if fingerprint.sha256 != normalized_expected:
            raise GCodeSourceIntegrityError(
                f"G-code source hash mismatch: {source_path}"
            )
    return fingerprint


def _cache_stem(
    source_path: Path,
    version: str = CACHE_VERSION,
    *,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
) -> Path:
    stat = source_path.stat()
    identity = source_sha256
    if version == CACHE_VERSION:
        identity = identity or _file_sha256(source_path)
        semantics_key = (
            "<unconfirmed>"
            if controller_semantics is None
            else str(controller_semantics).strip()
        )
        key_text = (
            f"{version}|{source_path}|{stat.st_size}|{stat.st_mtime_ns}|"
            f"{identity}|{semantics_key}"
        )
    else:
        key_text = f"{version}|{source_path}|{stat.st_size}|{stat.st_mtime_ns}"
    key_source = key_text.encode("utf-8", errors="replace")
    key = hashlib.sha1(key_source).hexdigest()
    return application_cache_dir("gcode_preview_cache") / key


def _cache_path(
    source_path: Path,
    version: str = CACHE_VERSION,
    *,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
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
    return stem.with_suffix(".json.gz")


def _cache_index_path(
    source_path: Path,
    version: str = CACHE_VERSION,
    *,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
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
    return stem.with_suffix(".npz")


def _raise_if_cancelled(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise GCodeLoadCancelled("G-code loading cancelled")


def _load_preview_cache(
    source_path: Path,
    *,
    source_sha256: str | None = None,
    controller_semantics: str | None = None,
) -> GCodePreview | None:
    if source_path.stat().st_size < 25_000_000:
        return None
    for version in (CACHE_VERSION, *LEGACY_CACHE_VERSIONS):
        try:
            cache_path = _cache_path(
                source_path,
                version,
                source_sha256=source_sha256 if version == CACHE_VERSION else None,
                controller_semantics=(
                    controller_semantics if version == CACHE_VERSION else None
                ),
            )
            if not cache_path.exists():
                continue
            with gzip.open(cache_path, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            index_path = _cache_index_path(
                source_path,
                version,
                source_sha256=source_sha256 if version == CACHE_VERSION else None,
                controller_semantics=(
                    controller_semantics if version == CACHE_VERSION else None
                ),
            )
            binary_name = payload.get("binary_arrays")
            if isinstance(binary_name, str) and binary_name:
                index_path = cache_path.parent / Path(binary_name).name
            if payload.get("binary_arrays") and index_path.exists():
                preview = _preview_from_binary_cache(payload, source_path, index_path)
                if preview.controller_semantics != controller_semantics:
                    continue
                preview._index().source = "cache"
                return preview
            preview = preview_from_json(payload, source_path)
            if preview.controller_semantics != controller_semantics:
                continue
            if index_path.exists():
                try:
                    preview.render_index = GCodeRenderIndex.from_npz(
                        index_path, preview.segments
                    )
                except Exception:
                    preview.render_index = None
            if preview.render_index is None and version != CACHE_VERSION:
                preview._index().cache_format = "legacy-json.gz+rebuilt-render-index-v2"
            if version != CACHE_VERSION:
                try:
                    _write_preview_cache(preview)
                except Exception:
                    pass
            preview._index().source = "cache"
            return preview
        except Exception:
            continue
    return None


def _write_preview_cache(
    preview: GCodePreview,
    *,
    cancel_check: CancelCheck | None = None,
    source_sha256: str | None = None,
) -> None:
    if (
        preview.source_path == Path("<memory>")
        or preview.source_path.stat().st_size < 25_000_000
    ):
        return
    _raise_if_cancelled(cancel_check)
    cache_path = _cache_path(
        preview.source_path,
        source_sha256=source_sha256,
        controller_semantics=preview.controller_semantics,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    index = preview._index()
    index.cache_format = "json.gz+npz-render-index-v2"
    timeline_arrays = preview.timeline_arrays or _timeline_arrays_from_steps(
        preview.timeline
    )
    legacy_index_path = _cache_index_path(
        preview.source_path,
        source_sha256=source_sha256,
        controller_semantics=preview.controller_semantics,
    )
    previous_index_path: Path | None = None
    if cache_path.exists():
        try:
            with gzip.open(cache_path, "rt", encoding="utf-8") as stream:
                previous_payload = json.load(stream)
            previous_name = previous_payload.get("binary_arrays")
            if isinstance(previous_name, str) and previous_name:
                previous_index_path = cache_path.parent / Path(previous_name).name
            elif previous_name:
                previous_index_path = legacy_index_path
        except Exception:
            previous_index_path = None

    temporary_index: Path | None = None
    temporary_cache: Path | None = None
    generation_index: Path | None = None
    manifest_committed = False
    try:
        _raise_if_cancelled(cancel_check)
        with tempfile.NamedTemporaryFile(
            dir=legacy_index_path.parent, suffix=".npz", delete=False
        ) as temporary:
            temporary_index = Path(temporary.name)
            np.savez(
                temporary,
                layer_min=np.asarray([index.layer_min], dtype=np.int32),
                layer_max=np.asarray([index.layer_max], dtype=np.int32),
                layer_prefix_counts=index.layer_prefix_counts.astype(
                    np.int32, copy=False
                ),
                timeline_indices=index.timeline_indices.astype(np.int32, copy=False),
                segment_indices=index.segment_indices.astype(np.int32, copy=False),
                source=np.asarray([index.source]),
                timeline_line_numbers=timeline_arrays.line_numbers,
                timeline_layers=timeline_arrays.layers,
                timeline_starts=timeline_arrays.starts,
                timeline_ends=timeline_arrays.ends,
                timeline_rotary_starts=timeline_arrays.rotary_starts,
                timeline_rotary_ends=timeline_arrays.rotary_ends,
                timeline_move_codes=timeline_arrays.move_codes,
                timeline_role_codes=timeline_arrays.role_codes,
                timeline_feedrates=timeline_arrays.feedrates,
                timeline_delta_es=timeline_arrays.delta_es,
                timeline_widths=timeline_arrays.widths,
                timeline_heights=timeline_arrays.heights,
                timeline_machine_starts=timeline_arrays.machine_starts,
                timeline_machine_ends=timeline_arrays.machine_ends,
                timeline_flags=timeline_arrays.flags,
                timeline_path_segment_indices=timeline_arrays.path_segment_indices,
                **_segment_npz_arrays(preview.segments),
            )
        _raise_if_cancelled(cancel_check)
        generation_index = legacy_index_path.with_name(
            f"{legacy_index_path.stem}.{uuid.uuid4().hex}{legacy_index_path.suffix}"
        )
        os.replace(temporary_index, generation_index)
        temporary_index = None

        payload = {
            "summary": preview.summary(),
            "binary_arrays": generation_index.name,
        }
        with tempfile.NamedTemporaryFile(
            dir=cache_path.parent, suffix=".json.gz", delete=False
        ) as temporary:
            temporary_cache = Path(temporary.name)
        with gzip.open(temporary_cache, "wt", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        _raise_if_cancelled(cancel_check)
        os.replace(temporary_cache, cache_path)
        temporary_cache = None
        manifest_committed = True
        for obsolete_path in (previous_index_path, legacy_index_path):
            if obsolete_path is None or obsolete_path == generation_index:
                continue
            try:
                obsolete_path.unlink(missing_ok=True)
            except OSError:
                # The committed manifest already points at the new generation.
                # A locked obsolete generation can be collected on a later run.
                pass
    finally:
        if temporary_index is not None:
            try:
                temporary_index.unlink(missing_ok=True)
            except OSError:
                pass
        if temporary_cache is not None:
            try:
                temporary_cache.unlink(missing_ok=True)
            except OSError:
                pass
        if generation_index is not None and not manifest_committed:
            try:
                generation_index.unlink(missing_ok=True)
            except OSError:
                pass
