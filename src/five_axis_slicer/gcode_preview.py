from __future__ import annotations

from dataclasses import dataclass, field
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


NUMBER_RE = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
AXIS_RE = re.compile(rf"([XYZABCUVWEFxyzabcuvwef])\s*({NUMBER_RE})")
COMMAND_RE = re.compile(r"\bG(0|1|20|21|28|90|91|92)\b", re.IGNORECASE)
LAYER_RE = re.compile(r"^Layer\s+(-?\d+)", re.IGNORECASE)
TYPE_RE = re.compile(r"^TYPE\s*:\s*(.+)$", re.IGNORECASE)
WIDTH_RE = re.compile(rf"^WIDTH\s*:\s*({NUMBER_RE})", re.IGNORECASE)
HEIGHT_RE = re.compile(rf"^HEIGHT\s*:\s*({NUMBER_RE})", re.IGNORECASE)
CACHE_VERSION = "gcode-preview-v4-timeline-beads"
AC_INVERSE_TRANSFORM = "ac_inverse_rz_minus_c_after_rx_minus_a"
MACHINE_COORDINATE_TRANSFORM = "machine_xyz"
PROGRESS_DOMAIN = "layer_filtered_gcode_order"
DEFAULT_BEAD_WIDTH = 0.4
DEFAULT_LAYER_HEIGHT = 0.2


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
        return any(abs(left - right) > 1e-9 for left, right in zip(self.start, self.end))

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
            "machine_start": None if self.machine_start is None else list(self.machine_start),
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
            "machine_start": None if self.machine_start is None else list(self.machine_start),
            "machine_end": None if self.machine_end is None else list(self.machine_end),
            "coordinate_transform": self.coordinate_transform,
            "has_spatial_axis": self.has_spatial_axis,
            "has_spatial_length": self.has_spatial_length,
            "path_segment_index": self.path_segment_index,
        }


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
            "timeline_step_count": len(self.timeline),
            "height_range": None
            if self.height_min is None or self.height_max is None
            else {
                "min": self.height_min,
                "max": self.height_max,
            },
            "progress_domain": PROGRESS_DOMAIN,
            "bounds": None
            if self.bounds is None
            else {
                "min": list(self.bounds[0]),
                "max": list(self.bounds[1]),
            },
        }

    def timeline_count_for_layers(self, layer_min: int, layer_max: int) -> int:
        return sum(1 for step in self.timeline if layer_min <= step.layer <= layer_max)

    def timeline_step_for_layer_progress(
        self,
        layer_min: int,
        layer_max: int,
        progress_index: int,
    ) -> GCodeTimelineStep | None:
        if not self.timeline:
            return None
        target = max(0, progress_index)
        local_index = 0
        last_step: GCodeTimelineStep | None = None
        for step in self.timeline:
            if layer_min <= step.layer <= layer_max:
                last_step = step
                if local_index == target:
                    return step
                local_index += 1
        return last_step

    def progress_state(self, layer_min: int, layer_max: int, progress_index: int) -> dict[str, Any]:
        count = 0
        target = max(0, progress_index)
        step: GCodeTimelineStep | None = None
        last_step: GCodeTimelineStep | None = None
        for candidate in self.timeline:
            if layer_min <= candidate.layer <= layer_max:
                if count == target:
                    step = candidate
                last_step = candidate
                count += 1
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
        index = max(0, min(progress_index, count - 1))
        if step is None or target >= count:
            step = last_step
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
            "role_colors": {role: rgb_to_hex(color) for role, color in ROLE_COLORS.items()},
            "move_colors": {move: rgb_to_hex(color) for move, color in MOVE_OPTION_COLORS.items()},
        }


def load_gcode(path: str | Path) -> GCodePreview:
    source_path = Path(path).expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"G-code file not found: {source_path}")
    if source_path.suffix.lower() not in {".gcode", ".nc", ".tap", ".txt"}:
        raise ValueError(f"Expected .gcode, .nc, .tap or .txt file: {source_path}")
    cached = _load_preview_cache(source_path)
    if cached is not None:
        return cached
    sample_stride = max(1, math.ceil(source_path.stat().st_size / 25_000_000))
    with source_path.open("r", encoding="utf-8", errors="replace") as stream:
        preview = parse_gcode_lines(stream, source_path, sample_stride=sample_stride)
    _write_preview_cache(preview)
    return preview


def parse_gcode(text: str, source_path: str | Path = "<memory>", sample_stride: int = 1) -> GCodePreview:
    return parse_gcode_lines(text.splitlines(), source_path, sample_stride=sample_stride)


def parse_gcode_lines(lines: Any, source_path: str | Path = "<memory>", sample_stride: int = 1) -> GCodePreview:
    source = Path(source_path)
    state = _ParserState()
    segments: list[GCodePathSegment] = []
    timeline: list[GCodeTimelineStep] = []
    stats = _PreviewStats()
    sample_stride = max(1, int(sample_stride))

    for line_number, raw_line in enumerate(lines, start=1):
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
            display_start = _preview_xyz(values.start_xyz, values.rotary_start)
            display_end = _preview_xyz(values.end_xyz, values.rotary_end)
            transform_name = _coordinate_transform_name(values.rotary_start, values.rotary_end)
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
            )
            path_segment_index = None
            if values.count_path_segment and stats.total_segment_count % sample_stride == 0:
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

    return _build_preview(source, segments, timeline, stats)


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
            machine_start=None
            if item.get("machine_start") is None
            else tuple(item["machine_start"]),
            machine_end=None
            if item.get("machine_end") is None
            else tuple(item["machine_end"]),
            coordinate_transform=item.get("coordinate_transform", summary.get("coordinate_transform", MACHINE_COORDINATE_TRANSFORM)),
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
            machine_start=None
            if item.get("machine_start") is None
            else tuple(item["machine_start"]),
            machine_end=None
            if item.get("machine_end") is None
            else tuple(item["machine_end"]),
            coordinate_transform=item.get("coordinate_transform", summary.get("coordinate_transform", MACHINE_COORDINATE_TRANSFORM)),
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
        None if summary.get("height_range") is None else float(summary["height_range"]["min"]),
        None if summary.get("height_range") is None else float(summary["height_range"]["max"]),
    )


class _ParserState:
    def __init__(self) -> None:
        self.axes = {axis: 0.0 for axis in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W", "E")}
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
    for axis in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W", "E"):
        if axis not in words:
            continue
        state.axes[axis] = words[axis] * state.units if axis in {"X", "Y", "Z"} else words[axis]


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
    start_xyz = tuple(state.axes[axis] for axis in ("X", "Y", "Z"))
    start_rotary = {axis: state.axes[axis] for axis in ("A", "B", "C", "U", "V", "W")}
    start_e = state.axes["E"]
    if "F" in words:
        state.feedrate = words["F"]

    has_spatial_axis = any(axis in words for axis in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W"))
    for axis in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W"):
        if axis in words:
            value = words[axis] * state.units if axis in {"X", "Y", "Z"} else words[axis]
            state.axes[axis] = state.axes[axis] + value if not state.absolute_xyz else value

    if "E" in words:
        if state.relative_e:
            delta_e = words["E"]
            state.axes["E"] += words["E"]
        else:
            delta_e = words["E"] - start_e
            state.axes["E"] = words["E"]
    else:
        delta_e = 0.0

    end_xyz = tuple(state.axes[axis] for axis in ("X", "Y", "Z"))
    end_rotary = {axis: state.axes[axis] for axis in ("A", "B", "C", "U", "V", "W")}
    linear_motion = any(abs(left - right) > 1e-9 for left, right in zip(start_xyz, end_xyz))
    rotary_motion = any(abs(start_rotary[axis] - end_rotary[axis]) > 1e-9 for axis in start_rotary)
    e_motion = abs(delta_e) > 1e-12
    if not has_spatial_axis and not e_motion:
        return None

    move_type = _classify_move(command, linear_motion or rotary_motion, linear_motion, delta_e)
    if has_spatial_axis and not e_motion and move_type == "noop":
        move_type = "travel"
    rotary_start = {axis: value for axis, value in start_rotary.items() if abs(value) > 1e-9}
    rotary_end = {axis: value for axis, value in end_rotary.items() if abs(value) > 1e-9}
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


def _points_differ(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> bool:
    return any(abs(left - right) > 1e-9 for left, right in zip(start, end))


def _coordinate_transform_name(rotary_start: dict[str, float], rotary_end: dict[str, float]) -> str:
    axes = set(rotary_start) | set(rotary_end)
    if "A" in axes or "C" in axes:
        return AC_INVERSE_TRANSFORM
    return MACHINE_COORDINATE_TRANSFORM


def _preview_xyz(
    machine_xyz: tuple[float, float, float],
    rotary: dict[str, float],
) -> tuple[float, float, float]:
    if "A" in rotary or "C" in rotary:
        return _inverse_rotary_ac_to_xyz(
            machine_xyz,
            rotary.get("A", 0.0),
            rotary.get("C", 0.0),
        )
    return machine_xyz


def _inverse_rotary_ac_to_xyz(
    machine_xyz: tuple[float, float, float],
    a_deg: float,
    c_deg: float,
) -> tuple[float, float, float]:
    # 与 MATLAB 叶轮脚本保持一致：P_part = Rz(-C) * Rx(-A) * P_machine。
    x, y, z = machine_xyz
    ax = math.radians(-a_deg)
    cx = math.radians(-c_deg)
    cos_a = math.cos(ax)
    sin_a = math.sin(ax)
    x1 = x
    y1 = y * cos_a - z * sin_a
    z1 = y * sin_a + z * cos_a
    cos_c = math.cos(cx)
    sin_c = math.sin(cx)
    x2 = x1 * cos_c - y1 * sin_c
    y2 = x1 * sin_c + y1 * cos_c
    return (x2, y2, z1)


def _classify_move(command: str, has_motion: bool, linear_motion: bool, delta_e: float) -> str:
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
    def __init__(self) -> None:
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
    ) -> None:
        self.timeline_step_count += 1
        if count_path_segment:
            self.total_segment_count += 1
        if coordinate_transform != MACHINE_COORDINATE_TRANSFORM:
            self.coordinate_transform = coordinate_transform
        self.move_counts[move_type] = self.move_counts.get(move_type, 0) + 1
        if move_type == "extrude":
            self.role_counts[extrusion_role] = self.role_counts.get(extrusion_role, 0) + 1
        if height is not None:
            self.height_min = height if self.height_min is None else min(self.height_min, height)
            self.height_max = height if self.height_max is None else max(self.height_max, height)
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
                        self.bounds_min[index] = min(self.bounds_min[index], point[index])
                        self.bounds_max[index] = max(self.bounds_max[index], point[index])


def _build_preview(
    source: Path,
    segments: list[GCodePathSegment],
    timeline: list[GCodeTimelineStep],
    stats: _PreviewStats,
) -> GCodePreview:
    if stats.total_segment_count == 0 and stats.timeline_step_count == 0:
        return GCodePreview(source, [], 0, 0, -1, None, {}, {}, [], timeline=[])

    bounds = None
    if stats.bounds_min is not None and stats.bounds_max is not None:
        bounds = (tuple(stats.bounds_min), tuple(stats.bounds_max))

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
    )


def _cache_path(source_path: Path) -> Path:
    stat = source_path.stat()
    key_source = f"{CACHE_VERSION}|{source_path}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8", errors="replace")
    key = hashlib.sha1(key_source).hexdigest()
    return Path.cwd() / "outputs" / "gcode_preview_cache" / f"{key}.json.gz"


def _load_preview_cache(source_path: Path) -> GCodePreview | None:
    if source_path.stat().st_size < 25_000_000:
        return None
    cache_path = _cache_path(source_path)
    if not cache_path.exists():
        return None
    try:
        with gzip.open(cache_path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
        return preview_from_json(payload, source_path)
    except Exception:
        return None


def _write_preview_cache(preview: GCodePreview) -> None:
    if preview.source_path == Path("<memory>") or preview.source_path.stat().st_size < 25_000_000:
        return
    cache_path = _cache_path(preview.source_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": preview.summary(),
        "segments": [segment.to_json() for segment in preview.segments],
        "timeline": [step.to_json() for step in preview.timeline],
    }
    with gzip.open(cache_path, "wt", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False)
