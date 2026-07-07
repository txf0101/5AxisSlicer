from __future__ import annotations

from dataclasses import dataclass, field
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


AXIS_RE = re.compile(r"([XYZABCUVEFxyzabcuvwef])\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))")
COMMAND_RE = re.compile(r"\bG(0|1|28|90|91|92)\b", re.IGNORECASE)
LAYER_RE = re.compile(r"^Layer\s+(-?\d+)", re.IGNORECASE)
TYPE_RE = re.compile(r"^TYPE\s*:\s*(.+)$", re.IGNORECASE)
WIDTH_RE = re.compile(r"^WIDTH\s*:\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))", re.IGNORECASE)


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
    comment: str = ""
    raw: str = ""

    @property
    def has_spatial_length(self) -> bool:
        return any(abs(left - right) > 1e-9 for left, right in zip(self.start, self.end))

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
            "comment": self.comment,
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
            "bounds": None
            if self.bounds is None
            else {
                "min": list(self.bounds[0]),
                "max": list(self.bounds[1]),
            },
        }


@dataclass(slots=True)
class PreviewSettings:
    layer_min: int = 0
    layer_max: int = 0
    show_travel: bool = True
    show_extrusion: bool = True
    show_pose_samples: bool = True
    visible_roles: set[str] = field(default_factory=lambda: set(ROLE_COLORS))

    def to_json(self) -> dict[str, Any]:
        return {
            "layer_min": self.layer_min,
            "layer_max": self.layer_max,
            "show_travel": self.show_travel,
            "show_extrusion": self.show_extrusion,
            "show_pose_samples": self.show_pose_samples,
            "visible_roles": sorted(self.visible_roles),
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
            continue

        if command in {"G90", "G91"}:
            state.absolute_xyz = command == "G90"
            continue
        if command == "G92":
            if "E" in words:
                state.axes["E"] = words["E"]
            continue
        if command == "G28":
            for axis in ("X", "Y", "Z"):
                if axis in words or not any(key in words for key in ("X", "Y", "Z")):
                    state.axes[axis] = 0.0
            continue
        if command not in {"G0", "G1"}:
            continue

        values = _apply_motion_words(state, command, words)
        if values is not None:
            stats.add_values(*values[:8])
            if stats.total_segment_count % sample_stride == 0:
                segments.append(_make_segment(values, line_number, raw, comment))

    return _build_preview(source, segments, stats)


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
            comment=item.get("comment", ""),
        )
        for item in payload.get("segments", [])
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
    )


class _ParserState:
    def __init__(self) -> None:
        self.axes = {axis: 0.0 for axis in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W", "E")}
        self.feedrate: float | None = None
        self.absolute_xyz = True
        self.relative_e = False
        self.layer = -1
        self.current_role = "unknown"
        self.current_width: float | None = None


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
            if number in {0, 1, 28, 90, 91, 92}:
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


def _apply_comment_tag(state: _ParserState, comment: str) -> None:
    type_match = TYPE_RE.match(comment)
    if type_match is not None:
        state.current_role = normalize_role(type_match.group(1))
        return

    width_match = WIDTH_RE.match(comment)
    if width_match is not None:
        state.current_width = float(width_match.group(1))
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
) -> tuple[
    str,
    str,
    int,
    tuple[float, float, float],
    tuple[float, float, float],
    dict[str, float],
    dict[str, float],
    bool,
    float | None,
    float,
    float | None,
] | None:
    start_xyz = tuple(state.axes[axis] for axis in ("X", "Y", "Z"))
    start_rotary = {axis: state.axes[axis] for axis in ("A", "B", "C", "U", "V", "W")}
    start_e = state.axes["E"]
    if "F" in words:
        state.feedrate = words["F"]

    for axis in ("X", "Y", "Z", "A", "B", "C", "U", "V", "W"):
        if axis in words:
            state.axes[axis] = state.axes[axis] + words[axis] if not state.absolute_xyz else words[axis]

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
    if not linear_motion and not rotary_motion and not e_motion:
        return None

    move_type = _classify_move(command, linear_motion or rotary_motion, linear_motion, delta_e)
    rotary_start = {axis: value for axis, value in start_rotary.items() if abs(value) > 1e-9}
    rotary_end = {axis: value for axis, value in end_rotary.items() if abs(value) > 1e-9}
    return (
        move_type,
        state.current_role,
        max(state.layer, 0),
        start_xyz,
        end_xyz,
        rotary_start,
        rotary_end,
        linear_motion,
        state.feedrate,
        delta_e,
        state.current_width,
    )


def _make_segment(
    values: tuple[
        str,
        str,
        int,
        tuple[float, float, float],
        tuple[float, float, float],
        dict[str, float],
        dict[str, float],
        bool,
        float | None,
        float,
        float | None,
    ],
    line_number: int,
    raw: str,
    comment: str,
) -> GCodePathSegment:
    move_type, role, layer, start_xyz, end_xyz, rotary_start, rotary_end, _has_spatial, feedrate, delta_e, width = values
    return GCodePathSegment(
        line_number=line_number,
        layer=layer,
        start=start_xyz,
        end=end_xyz,
        rotary_start=rotary_start,
        rotary_end=rotary_end,
        move_type=move_type,
        extrusion_role=role,
        feedrate=feedrate,
        delta_e=delta_e,
        width=width,
        comment=comment,
        raw=raw,
    )


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
        self.move_counts: dict[str, int] = {}
        self.role_counts: dict[str, int] = {}
        self.rotary_axes: set[str] = set()
        self.layer_min: int | None = None
        self.layer_max: int | None = None
        self.bounds_min: list[float] | None = None
        self.bounds_max: list[float] | None = None

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
    ) -> None:
        self.total_segment_count += 1
        self.move_counts[move_type] = self.move_counts.get(move_type, 0) + 1
        if move_type == "extrude":
            self.role_counts[extrusion_role] = self.role_counts.get(extrusion_role, 0) + 1
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


def _build_preview(source: Path, segments: list[GCodePathSegment], stats: _PreviewStats) -> GCodePreview:
    if stats.total_segment_count == 0:
        return GCodePreview(source, [], 0, 0, -1, None, {}, {}, [])

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
    )


def _cache_path(source_path: Path) -> Path:
    stat = source_path.stat()
    key_source = f"{source_path}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8", errors="replace")
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
    }
    with gzip.open(cache_path, "wt", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False)
