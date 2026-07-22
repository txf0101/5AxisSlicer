from __future__ import annotations

"""Export four independent, auditable paper-figure panels.

The historical entry-point name is retained for callers.  The script now
produces four separate 3840 x 2160 PNG/JSON pairs and a collection manifest.
An optional delivery mode writes matching uncompressed RGB TIFF/JSON pairs;
it never assembles a 2 x 2 raster.  The toolpath panel can be rendered from
STEP plus G-code with the application's OpenGL backend, or supplied as an
independently rendered 4K image.  The settings and G-code panels are drawn
directly with Qt at the final output resolution.
"""

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
from typing import Any, Mapping, Sequence
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt5.QtCore import (
    QBuffer,
    QEventLoop,
    QIODevice,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    Qt,
)
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QImageWriter,
    QPainter,
    QPen,
    QRegion,
)
from PyQt5.QtWidgets import QApplication, QWidget

from five_axis_slicer.gcode_source import GCodeSourceIndex
from five_axis_slicer.paper_export import (
    PIXELS_PER_METER,
    _atomic_write,
    _atomic_write_pair,
    _inspect_png,
    _replace_png_contract_chunks,
    _verify_png_contract,
)


CANVAS_WIDTH = 3840
CANVAS_HEIGHT = 2160
LOGICAL_WIDTH = 1920
LOGICAL_HEIGHT = 1080
OUTPUT_SCALE = 2
OUTPUT_DPI = 300
DEFAULT_OUTPUT_DIRECTORY = ROOT / "outputs" / "paper_preview_acceptance" / "individual_panels"
DEFAULT_PREFIX = "impeller"
CONTEXT_RADIUS = 10

PANEL_SPECS: tuple[tuple[str, str], ...] = (
    ("a", "overall"),
    ("b", "process_settings"),
    ("c", "five_axis_toolpath"),
    ("d", "machine_gcode"),
)


@dataclass(frozen=True, slots=True)
class PanelPayload:
    panel_id: str
    role: str
    image_path: Path
    sidecar_path: Path
    png_bytes: bytes
    audit: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PanelTiffPayload:
    panel_id: str
    role: str
    image_path: Path
    sidecar_path: Path
    tiff_bytes: bytes
    audit: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class LiveToolpathRender:
    png_bytes: bytes
    sources: Mapping[str, Any]
    backend: str
    capabilities: Mapping[str, Any]
    camera: Mapping[str, Any]
    statistics: Mapping[str, Any]
    display_items: Mapping[str, Any]
    overlay_widgets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GCodeHeaderLayout:
    """Measured two-row header that keeps the title and syntax chips disjoint."""

    title_rect: QRect
    chip_band_rect: QRect
    chip_rects: tuple[QRect, ...]


@dataclass(frozen=True, slots=True)
class GCodeBodyLayout:
    """Measured code geometry using the largest font that fits every source line."""

    font: QFont
    pixel_size: int
    line_height: int
    code_top: int
    gutter_rect: QRect
    code_clip_rect: QRect


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export four independent impeller paper-figure panels"
    )
    parser.add_argument(
        "--overall",
        required=True,
        help="Audited 3840x2160 overall result-preview PNG for panel a",
    )
    parser.add_argument(
        "--overall-sidecar",
        help="Audit JSON for --overall; defaults to the same stem with .json",
    )
    toolpath_source = parser.add_mutually_exclusive_group(required=True)
    toolpath_source.add_argument(
        "--toolpath-image",
        help="Independent 3840x2160 FBO/toolpath PNG for panel c",
    )
    toolpath_source.add_argument(
        "--step",
        help="STEP/STP source rendered directly with --gcode for panel c",
    )
    parser.add_argument(
        "--toolpath-sidecar",
        help="Optional audit JSON for --toolpath-image",
    )
    parser.add_argument("--gcode", required=True, help="G-code source used for panel d")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIRECTORY),
        help="Directory receiving four PNG/JSON pairs and the manifest",
    )
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="ASCII artifact name prefix")
    parser.add_argument("--language", choices=("zh", "en"), default="zh")
    parser.add_argument(
        "--uncompressed-tiff",
        action="store_true",
        help="Also write matching 3840x2160 RGB TIFF files with Compression=1",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _validate_cli_arguments(args)
    app = QApplication.instance() or QApplication([])

    overall_path = Path(args.overall).expanduser().resolve()
    gcode_path = Path(args.gcode).expanduser().resolve()
    output_directory = Path(args.output_dir).expanduser().resolve()
    prefix = _normalise_prefix(args.prefix)
    language = str(args.language)

    overall_sidecar_path = (
        Path(args.overall_sidecar).expanduser().resolve()
        if args.overall_sidecar
        else overall_path.with_suffix(".json")
    )
    toolpath_sidecar_path: Path | None = (
        Path(args.toolpath_sidecar).expanduser().resolve()
        if args.toolpath_sidecar
        else None
    )

    overall_bytes, overall_info = _read_exact_4k_png(overall_path, role="overall preview")
    overall_source = _source_audit(overall_path)

    overall_audit = _read_json(overall_sidecar_path, role="overall sidecar")
    _validate_image_sidecar(
        overall_audit,
        overall_source,
        language=language,
        role="overall preview",
    )
    _validate_gcode_source(overall_audit, gcode_path)

    live_toolpath: LiveToolpathRender | None = None
    toolpath_audit: Mapping[str, Any] | None = None
    toolpath_source: Mapping[str, Any] | None = None
    toolpath_info: Mapping[str, Any] | None = None
    if args.toolpath_image:
        toolpath_path = Path(args.toolpath_image).expanduser().resolve()
        toolpath_bytes, toolpath_info = _read_exact_4k_png(
            toolpath_path,
            role="independent toolpath image",
        )
        toolpath_source = _source_audit(toolpath_path)
        if overall_source["sha256"] == toolpath_source["sha256"]:
            raise RuntimeError(
                "The toolpath image must be an independent render, not the overall preview"
            )
        if toolpath_sidecar_path is not None:
            toolpath_audit = _read_json(toolpath_sidecar_path, role="toolpath sidecar")
            _validate_image_sidecar(
                toolpath_audit,
                toolpath_source,
                language=None,
                role="toolpath image",
            )
    else:
        step_path = Path(args.step).expanduser().resolve()
        _validate_step_source(overall_audit, step_path)
        live_toolpath = _render_live_toolpath_panel(
            step_path,
            gcode_path,
            language=language,
            app=app,
        )
        toolpath_bytes = live_toolpath.png_bytes

    captured_at = _utc_now()
    collection_id = uuid.uuid4().hex
    output_directory.mkdir(parents=True, exist_ok=True)
    output_paths = {
        panel_id: output_directory
        / f"{prefix}_paper_panel_{panel_id}_{role}_{language}_3840x2160.png"
        for panel_id, role in PANEL_SPECS
    }

    settings_bytes = _render_settings_panel(overall_audit, language)
    gcode_bytes, representative_line, context_line_numbers = _render_gcode_panel(
        gcode_path,
        language,
    )

    shared_sources = _normalise_source_records(overall_audit.get("sources", {}))
    illustrative_parameters = {
        "parameters_affect_toolpath": False,
        "layer_height_mm": 0.20,
        "print_speed_mm_min": 1200,
        "extrusion_width_mm": 0.48,
        "nozzle_diameter_mm": 0.40,
        "process_mode": "Shell",
        "top_layers": 5,
        "bottom_layers": 5,
    }

    payloads: list[PanelPayload] = []
    payloads.append(
        _make_payload(
            "a",
            "overall",
            output_paths["a"],
            overall_bytes,
            language=language,
            captured_at=captured_at,
            collection_id=collection_id,
            sources={
                **shared_sources,
                "overall_preview_artifact": overall_source,
                "overall_preview_sidecar": _source_audit(overall_sidecar_path),
            },
            capture_method="audited_overall_preview_identity_copy",
            extra={
                "input_image_px": {
                    "width": int(overall_info["width"]),
                    "height": int(overall_info["height"]),
                },
                "source_snapshot": _snapshot_summary(overall_audit),
            },
        )
    )
    payloads.append(
        _make_payload(
            "b",
            "process_settings",
            output_paths["b"],
            settings_bytes,
            language=language,
            captured_at=captured_at,
            collection_id=collection_id,
            sources={
                **shared_sources,
                "overall_preview_sidecar": _source_audit(overall_sidecar_path),
            },
            capture_method="direct_qt_vector_paint",
            extra={
                "logical_layout_px": {"width": LOGICAL_WIDTH, "height": LOGICAL_HEIGHT},
                "output_scale": OUTPUT_SCALE,
                "illustrative_process_parameters": illustrative_parameters,
            },
        )
    )
    if live_toolpath is None:
        if toolpath_source is None or toolpath_info is None:
            raise AssertionError("Independent toolpath source was not prepared")
        toolpath_sources: dict[str, Any] = {
            **shared_sources,
            "independent_toolpath_image": toolpath_source,
        }
        if toolpath_sidecar_path is not None:
            toolpath_sources["independent_toolpath_sidecar"] = _source_audit(
                toolpath_sidecar_path
            )
        toolpath_capture_method = "independent_fbo_or_toolpath_image_identity_copy"
        toolpath_extra: dict[str, Any] = {
            "input_image_px": {
                "width": int(toolpath_info["width"]),
                "height": int(toolpath_info["height"]),
            },
            "toolpath_source_snapshot": (
                _snapshot_summary(toolpath_audit) if toolpath_audit is not None else None
            ),
        }
        toolpath_audit_context: Mapping[str, Any] | None = None
    else:
        toolpath_sources = dict(live_toolpath.sources)
        toolpath_capture_method = "direct_opengl_fbo_with_qt_overlays"
        toolpath_extra = {
            "fbo_request_px": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
            "overlay_widgets": list(live_toolpath.overlay_widgets),
            "quality_mode": "paper",
            "standard_view": "isometric",
        }
        toolpath_audit_context = {
            "backend": live_toolpath.backend,
            "viewer_capabilities": dict(live_toolpath.capabilities),
            "camera": dict(live_toolpath.camera),
            "statistics": dict(live_toolpath.statistics),
            "display_items": dict(live_toolpath.display_items),
        }
    payloads.append(
        _make_payload(
            "c",
            "five_axis_toolpath",
            output_paths["c"],
            toolpath_bytes,
            language=language,
            captured_at=captured_at,
            collection_id=collection_id,
            sources=toolpath_sources,
            capture_method=toolpath_capture_method,
            extra=toolpath_extra,
            audit_context=toolpath_audit_context,
        )
    )
    payloads.append(
        _make_payload(
            "d",
            "machine_gcode",
            output_paths["d"],
            gcode_bytes,
            language=language,
            captured_at=captured_at,
            collection_id=collection_id,
            sources={"gcode": _source_audit(gcode_path)},
            capture_method="direct_qt_vector_paint_from_gcode_index",
            extra={
                "representative_gcode_line": representative_line,
                "context_radius": CONTEXT_RADIUS,
                "context_source_line_numbers": context_line_numbers,
                "line_number_mode": "absolute_source_line",
                "syntax_colors": {
                    "feedrate_f": "#2563EB",
                    "coordinates_xyz": "#16845B",
                    "rotary_ac": "#E26A00",
                    "extrusion_e": "#7A5AF8",
                },
            },
        )
    )

    tiff_payloads = (
        [_make_tiff_payload(payload) for payload in payloads]
        if bool(args.uncompressed_tiff)
        else []
    )

    for payload in payloads:
        sidecar_bytes = (
            json.dumps(payload.audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _atomic_write_pair(
            payload.image_path,
            payload.png_bytes,
            payload.sidecar_path,
            sidecar_bytes,
        )
    for payload in tiff_payloads:
        sidecar_bytes = (
            json.dumps(payload.audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        _atomic_write_pair(
            payload.image_path,
            payload.tiff_bytes,
            payload.sidecar_path,
            sidecar_bytes,
        )

    manifest = _build_manifest(
        payloads,
        tiff_payloads=tiff_payloads,
        language=language,
        captured_at=captured_at,
        collection_id=collection_id,
        prefix=prefix,
    )
    manifest_path = output_directory / f"{prefix}_paper_panels_{language}_manifest.json"
    _atomic_write(
        manifest_path,
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
    )

    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "panels": [str(payload.image_path) for payload in payloads],
                "uncompressed_tiff_panels": [
                    str(payload.image_path) for payload in tiff_payloads
                ],
            },
            ensure_ascii=False,
        )
    )
    app.processEvents()
    return 0


def _normalise_prefix(value: str) -> str:
    prefix = str(value).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", prefix):
        raise ValueError("--prefix must contain only ASCII letters, numbers, dot, dash or underscore")
    return prefix


def _validate_cli_arguments(args: argparse.Namespace) -> None:
    toolpath_image = bool(getattr(args, "toolpath_image", None))
    step = bool(getattr(args, "step", None))
    if toolpath_image == step:
        raise ValueError("Exactly one of --toolpath-image or --step is required")
    if getattr(args, "toolpath_sidecar", None) and not toolpath_image:
        raise ValueError("--toolpath-sidecar can only be used with --toolpath-image")
    if step and not getattr(args, "gcode", None):
        raise ValueError("--step requires --gcode")


def _read_exact_4k_png(path: Path, *, role: str) -> tuple[bytes, dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {role}: {path}")
    payload = path.read_bytes()
    try:
        info = _inspect_png(payload)
        _verify_png_contract(info)
    except Exception as exc:
        raise RuntimeError(
            f"{role} must be an opaque sRGB 3840x2160 PNG with 300 dpi metadata: {path}: {exc}"
        ) from exc
    return payload, info


def _read_json(path: Path, *, role: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {role}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read {role}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{role} must contain a JSON object: {path}")
    return value


def _validate_image_sidecar(
    sidecar: Mapping[str, Any],
    source_audit: Mapping[str, Any],
    *,
    language: str | None,
    role: str,
) -> None:
    artifact = sidecar.get("artifact")
    if not isinstance(artifact, Mapping):
        raise RuntimeError(f"{role} sidecar has no artifact record")
    if artifact.get("sha256") != source_audit.get("sha256"):
        raise RuntimeError(f"{role} sidecar SHA-256 does not match the supplied PNG")
    if (artifact.get("width_px"), artifact.get("height_px")) != (
        CANVAS_WIDTH,
        CANVAS_HEIGHT,
    ):
        raise RuntimeError(f"{role} sidecar does not describe a 3840x2160 artifact")
    if language is not None and sidecar.get("language") not in (None, language):
        raise RuntimeError(
            f"{role} sidecar language {sidecar.get('language')!r} does not match {language!r}"
        )


def _validate_gcode_source(overall_audit: Mapping[str, Any], path: Path) -> None:
    sources = overall_audit.get("sources")
    if not isinstance(sources, Mapping):
        raise RuntimeError("Overall sidecar has no source snapshot")
    record = sources.get("gcode")
    if not isinstance(record, Mapping) or not record.get("sha256"):
        raise RuntimeError("Overall sidecar has no audited G-code source")
    actual = _source_audit(path)
    if record.get("sha256") != actual["sha256"]:
        raise RuntimeError("G-code SHA-256 does not match the overall preview source snapshot")


def _validate_step_source(overall_audit: Mapping[str, Any], path: Path) -> None:
    sources = overall_audit.get("sources")
    if not isinstance(sources, Mapping):
        raise RuntimeError("Overall sidecar has no source snapshot")
    record = sources.get("step_model")
    if not isinstance(record, Mapping) or not record.get("sha256"):
        raise RuntimeError("Overall sidecar has no audited STEP source")
    actual = _source_audit(path)
    if record.get("sha256") != actual["sha256"]:
        raise RuntimeError("STEP SHA-256 does not match the overall preview source snapshot")


def _render_live_toolpath_panel(
    step_path: Path,
    gcode_path: Path,
    *,
    language: str,
    app: QApplication,
) -> LiveToolpathRender:
    from five_axis_slicer.gcode_preview import load_gcode
    from five_axis_slicer.step_loader import load_step
    from five_axis_slicer.viewer import ModelViewer

    step_source = _source_audit(step_path)
    gcode_source = _source_audit(gcode_path)
    viewer = ModelViewer()
    try:
        backend = str(getattr(viewer, "backend", "unknown"))
        if backend.casefold() != "opengl":
            raise RuntimeError(
                "Direct STEP toolpath export requires the OpenGL ModelViewer backend; "
                f"received {backend!r}"
            )

        viewer.resize(960, 540)
        viewer.show()
        app.processEvents(QEventLoop.ExcludeUserInputEvents)

        model = load_step(step_path)
        preview = load_gcode(gcode_path, source_sha256=str(gcode_source["sha256"]))
        viewer.load_model(model)
        viewer.load_gcode_preview(preview)
        viewer.set_preview_visibility(
            show_travel=False,
            show_extrusion=True,
            show_pose_samples=False,
        )
        viewer.set_result_visibility(model=True, start_end=True, grid=True)
        viewer.set_quality_mode("paper")
        viewer.set_standard_view("isometric")
        app.processEvents(QEventLoop.ExcludeUserInputEvents)

        capabilities = dict(viewer.capabilities())
        if capabilities.get("full_timeline_paper_path") is not True:
            raise RuntimeError("OpenGL viewer did not report the full-timeline paper path")
        if capabilities.get("paper_quality_active") is not True:
            raise RuntimeError("OpenGL viewer paper quality is not active")

        scene = viewer.render_scene_image(CANVAS_WIDTH, CANVAS_HEIGHT)
        if scene.isNull() or (scene.width(), scene.height()) != (
            CANVAS_WIDTH,
            CANVAS_HEIGHT,
        ):
            raise RuntimeError(
                "OpenGL viewer returned an invalid toolpath image: "
                f"{scene.width()}x{scene.height()}"
            )
        composited, overlay_widgets = _compose_toolpath_overlays(
            scene,
            viewer,
            language=language,
        )
        summary = preview.summary()
        total = int(preview.total_segment_count)
        extrusion = int(preview.move_counts.get("extrude", 0))
        statistics = {
            "geometry": {
                "bodies": len(model.bodies),
                "edges": len(model.edges),
            },
            "toolpath": {
                **summary,
                "positive_extrusion_segments": extrusion,
                "travel_or_non_extrusion_segments": max(0, total - extrusion),
            },
            "render": {
                "visible_path_segment_count": int(viewer.visible_path_segment_count),
                "drawn_path_segment_count": int(viewer.drawn_path_segment_count),
                "path_render_mode": str(viewer.path_render_mode),
            },
        }
        display_items = {
            "model": True,
            "positive_extrusion": True,
            "travel": False,
            "pose_samples": False,
            "start_end": True,
            "grid": True,
            "part_axes": True,
            "orientation_cube": True,
            "tool_rail": True,
        }
        return LiveToolpathRender(
            png_bytes=_encode_png(composited.convertToFormat(QImage.Format_RGB888)),
            sources={"step_model": step_source, "gcode": gcode_source},
            backend=backend,
            capabilities=capabilities,
            camera=dict(viewer.camera_state()),
            statistics=statistics,
            display_items=display_items,
            overlay_widgets=overlay_widgets,
        )
    finally:
        viewer.hide()
        viewer.close()
        viewer.deleteLater()
        app.processEvents(QEventLoop.ExcludeUserInputEvents)


def _compose_toolpath_overlays(
    scene: QImage,
    viewer: QWidget,
    *,
    language: str,
) -> tuple[QImage, tuple[str, ...]]:
    from five_axis_slicer.viewer_overlays import AxisTriadOverlay, OrientationCubeOverlay

    canvas = scene.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    painter = QPainter(canvas)
    if not painter.isActive():
        raise RuntimeError("Could not start toolpath-overlay painter")
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.scale(OUTPUT_SCALE, OUTPUT_SCALE)

    cube = OrientationCubeOverlay(viewer)
    axis = AxisTriadOverlay(viewer)
    overlays: tuple[tuple[QWidget, QPoint], ...] = (
        (cube, QPoint(LOGICAL_WIDTH - cube.width() - 24, 24)),
        (axis, QPoint(24, LOGICAL_HEIGHT - axis.height() - 24)),
    )
    try:
        _draw_tool_rail(painter, QRect(24, 24, 154, 52))
        _draw_start_end_legend(
            painter,
            QRect(LOGICAL_WIDTH - 304, LOGICAL_HEIGHT - 80, 280, 56),
            language,
        )
        flags = QWidget.DrawChildren
        for widget, position in overlays:
            widget.ensurePolished()
            widget.render(painter, position, QRegion(), flags)
    finally:
        painter.end()
        cube.deleteLater()
        axis.deleteLater()
    return canvas, (
        "viewToolRail",
        "OrientationCubeOverlay",
        "AxisTriadOverlay",
        "StartEndLegend",
    )


def _draw_tool_rail(painter: QPainter, rect: QRect) -> None:
    painter.setPen(QPen(QColor("#D7DEE8"), 1))
    painter.setBrush(QColor(255, 255, 255, 236))
    painter.drawRoundedRect(QRectF(rect), 6, 6)
    button_width = 62
    for index, label in enumerate(("FIT", "ISO")):
        button = QRect(rect.x() + 8 + index * (button_width + 8), rect.y() + 7, button_width, 38)
        painter.setPen(QPen(QColor("#D7DEE8"), 1))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(QRectF(button), 4, 4)
        _draw_text(painter, button, label, 12, color="#475569", align=Qt.AlignCenter)


def _draw_start_end_legend(painter: QPainter, rect: QRect, language: str) -> None:
    painter.setPen(QPen(QColor("#D7DEE8"), 1))
    painter.setBrush(QColor(255, 255, 255, 236))
    painter.drawRoundedRect(QRectF(rect), 6, 6)
    labels = ("Start", "End") if language == "en" else ("起点", "终点")
    entries = (("#16845B", labels[0]), ("#D92D20", labels[1]))
    for index, (color, label) in enumerate(entries):
        start_x = rect.x() + 20 + index * 130
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRect(start_x, rect.y() + 21, 12, 12))
        _draw_text(
            painter,
            QRect(start_x + 20, rect.y(), 96, rect.height()),
            label,
            13,
            align=Qt.AlignLeft | Qt.AlignVCenter,
        )


def _normalise_source_records(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    records: dict[str, Any] = {}
    for key, record in value.items():
        if isinstance(record, Mapping):
            records[str(key)] = dict(record)
    return records


def _snapshot_summary(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    summary: dict[str, Any] = {}
    for key in ("schema_version", "captured_at_utc", "language", "statistics", "camera", "display_items"):
        if key in value:
            summary[key] = value[key]
    return summary


def _make_payload(
    panel_id: str,
    role: str,
    output_path: Path,
    png_bytes: bytes,
    *,
    language: str,
    captured_at: str,
    collection_id: str,
    sources: Mapping[str, Any],
    capture_method: str,
    extra: Mapping[str, Any] | None = None,
    audit_context: Mapping[str, Any] | None = None,
) -> PanelPayload:
    info = _inspect_png(png_bytes)
    _verify_png_contract(info)
    artifact = {
        "file_name": output_path.name,
        "path": str(output_path),
        "width_px": int(info["width"]),
        "height_px": int(info["height"]),
        "dpi": OUTPUT_DPI,
        "color_space": "sRGB",
        "sha256": hashlib.sha256(png_bytes).hexdigest(),
        "byte_size": len(png_bytes),
        "png_color_type": int(info["color_type"]),
        "opaque": int(info["color_type"]) not in {4, 6} and "tRNS" not in info["chunks"],
    }
    panel = {
        "id": panel_id,
        "role": role,
        "capture_method": capture_method,
        "crop_from_composite": None,
        "resampling": False,
        "caption_baked": False,
    }
    if extra:
        panel.update(dict(extra))
    audit = {
        "schema_version": 1,
        "collection_id": collection_id,
        "captured_at_utc": captured_at,
        "language": language,
        "panel": panel,
        "artifact": artifact,
        "sources": dict(sources),
        "render_parameters": {
            "preset": "paper_individual_panel_4k",
            "output_px": {"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT},
            "dpi_requested": OUTPUT_DPI,
            "pixels_per_meter": PIXELS_PER_METER,
            "dpi_encoded": PIXELS_PER_METER * 0.0254,
            "color_space": "sRGB",
            "background": "#F3F5F7",
            "opaque_background": True,
        },
    }
    if audit_context:
        audit.update(dict(audit_context))
    return PanelPayload(
        panel_id,
        role,
        output_path,
        output_path.with_suffix(".json"),
        png_bytes,
        audit,
    )


def _make_tiff_payload(payload: PanelPayload) -> PanelTiffPayload:
    """Convert one audited PNG panel to an uncompressed, pixel-identical RGB TIFF."""

    tiff_bytes, info = _encode_uncompressed_tiff(payload.png_bytes)
    tiff_path = payload.image_path.with_suffix(".tif")
    artifact = {
        "file_name": tiff_path.name,
        "path": str(tiff_path),
        "width_px": int(info["width"]),
        "height_px": int(info["height"]),
        "dpi": OUTPUT_DPI,
        "color_space": "sRGB",
        "sha256": hashlib.sha256(tiff_bytes).hexdigest(),
        "byte_size": len(tiff_bytes),
        "tiff_compression_tag": int(info["compression"]),
        "compression": "none",
        "bits_per_sample": list(info["bits_per_sample"]),
        "samples_per_pixel": int(info["samples_per_pixel"]),
        "photometric_interpretation": int(info["photometric_interpretation"]),
        "opaque": True,
    }
    panel = dict(payload.audit["panel"])
    panel["capture_method"] = "pixel_identity_rgb_tiff_from_panel_png"
    audit = {
        "schema_version": 1,
        "collection_id": payload.audit["collection_id"],
        "captured_at_utc": payload.audit["captured_at_utc"],
        "language": payload.audit["language"],
        "panel": panel,
        "artifact": artifact,
        "sources": {
            **dict(payload.audit.get("sources", {})),
            "source_panel_png": dict(payload.audit["artifact"]),
        },
        "render_parameters": {
            **dict(payload.audit["render_parameters"]),
            "delivery_format": "TIFF",
            "tiff_compression": "none",
            "tiff_compression_tag": 1,
            "pixel_resampling": False,
        },
    }
    for key in ("backend", "viewer_capabilities", "camera", "statistics", "display_items"):
        if key in payload.audit:
            audit[key] = payload.audit[key]
    return PanelTiffPayload(
        payload.panel_id,
        payload.role,
        tiff_path,
        Path(f"{tiff_path}.json"),
        tiff_bytes,
        audit,
    )


def _build_manifest(
    payloads: Sequence[PanelPayload],
    *,
    tiff_payloads: Sequence[PanelTiffPayload] = (),
    language: str,
    captured_at: str,
    collection_id: str,
    prefix: str,
) -> dict[str, Any]:
    tiff_by_panel = {payload.panel_id: payload for payload in tiff_payloads}
    panel_records: list[dict[str, Any]] = []
    for payload in payloads:
        png_record = {
            "image_file": payload.image_path.name,
            "sidecar_file": payload.sidecar_path.name,
            "sha256": payload.audit["artifact"]["sha256"],
            "width_px": CANVAS_WIDTH,
            "height_px": CANVAS_HEIGHT,
        }
        record: dict[str, Any] = {
            "id": payload.panel_id,
            "role": payload.role,
            **png_record,
            "deliverables": {"png": dict(png_record)},
        }
        tiff_payload = tiff_by_panel.get(payload.panel_id)
        if tiff_payload is not None:
            record["deliverables"]["tiff_uncompressed"] = {
                "image_file": tiff_payload.image_path.name,
                "sidecar_file": tiff_payload.sidecar_path.name,
                "sha256": tiff_payload.audit["artifact"]["sha256"],
                "byte_size": tiff_payload.audit["artifact"]["byte_size"],
                "width_px": CANVAS_WIDTH,
                "height_px": CANVAS_HEIGHT,
                "compression": "none",
                "tiff_compression_tag": 1,
            }
        panel_records.append(record)
    return {
        "schema_version": 1,
        "collection_id": collection_id,
        "captured_at_utc": captured_at,
        "language": language,
        "prefix": prefix,
        "formats": ["png"] + (["tiff_uncompressed"] if tiff_payloads else []),
        "assembly": {
            "panel_order": [payload.panel_id for payload in payloads],
            "captions_baked": False,
            "precomposed_grid_generated": False,
            "intended_for_user_composition": True,
        },
        "panels": panel_records,
    }


def _render_settings_panel(overall_audit: Mapping[str, Any], language: str) -> bytes:
    names = _source_names(overall_audit)
    image = _new_canvas()
    painter = QPainter(image)
    if not painter.isActive():
        raise RuntimeError("Could not start settings-panel painter")
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.scale(OUTPUT_SCALE, OUTPUT_SCALE)
    try:
        background = QColor("#F3F5F7")
        painter.fillRect(QRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT), background)
        margin = 38
        gap = 24
        card_width = (LOGICAL_WIDTH - margin * 2 - gap) // 2
        card_height = LOGICAL_HEIGHT - margin * 2
        source_rect = QRect(margin, margin, card_width, card_height)
        parameter_rect = QRect(margin + card_width + gap, margin, card_width, card_height)
        _draw_source_card(painter, source_rect, names, language)
        _draw_parameter_card(painter, parameter_rect, language)
    finally:
        painter.end()
    return _encode_png(image.convertToFormat(QImage.Format_RGB888))


def _source_names(overall_audit: Mapping[str, Any]) -> dict[str, str]:
    sources = overall_audit.get("sources")
    if not isinstance(sources, Mapping):
        sources = {}

    def name(key: str) -> str:
        record = sources.get(key)
        if isinstance(record, Mapping):
            value = str(record.get("name") or "").strip()
            if value:
                return value
            path = str(record.get("path") or "").strip()
            if path:
                return Path(path).name
        return "—"

    return {
        "step": name("step_model"),
        "gcode": name("gcode"),
        "reference": name("visual_reference"),
    }


def _draw_source_card(
    painter: QPainter,
    rect: QRect,
    names: Mapping[str, str],
    language: str,
) -> None:
    text = _settings_text(language)
    _draw_card_background(painter, rect)
    x = rect.x() + 34
    width = rect.width() - 68
    y = rect.y() + 36
    _draw_text(painter, QRect(x, y, width, 46), text["source_title"], 26, bold=True)
    y += 70
    rows = (
        (text["step_model"], names["step"]),
        (text["gcode_path"], names["gcode"]),
    )
    for label, value in rows:
        _draw_text(painter, QRect(x, y, width, 30), label, 17, color="#667085")
        y += 32
        _draw_value_box(painter, QRect(x, y, width, 54), value, enabled=True)
        y += 78

    y += 12
    buttons = (
        (text["load_demo"], True),
        (text["open_gcode"], False),
        (text["open_step"], False),
        (text["slice_preview"], True),
    )
    for label, primary in buttons:
        _draw_button(painter, QRect(x, y, width, 58), label, primary=primary)
        y += 72


def _draw_parameter_card(painter: QPainter, rect: QRect, language: str) -> None:
    text = _settings_text(language)
    _draw_card_background(painter, rect)
    x = rect.x() + 34
    width = rect.width() - 68
    y = rect.y() + 34
    _draw_text(
        painter,
        QRect(x, y, width, 42),
        text["parameter_title"],
        26,
        bold=True,
    )
    y += 78

    rows = (
        (text["layer_height"], "0.20 mm"),
        (text["print_speed"], "1200 mm/min"),
        (text["extrusion_width"], "0.48 mm"),
        (text["nozzle_diameter"], "0.40 mm"),
    )
    label_width = 210 if language == "zh" else 290
    value_x = x + label_width
    value_width = width - label_width
    for label, value in rows:
        _draw_text(painter, QRect(x, y + 10, label_width - 12, 40), label, 18, color="#667085")
        _draw_value_box(painter, QRect(value_x, y, value_width, 56), value, enabled=False)
        y += 76

    _draw_text(
        painter,
        QRect(x, y + 8, label_width - 12, 40),
        text["process_mode"],
        18,
        color="#667085",
    )
    _draw_checkbox(painter, QRect(value_x, y, value_width, 56), "Shell", checked=False)
    y += 76

    _draw_text(
        painter,
        QRect(x, y + 8, label_width - 12, 40),
        text["top_bottom"],
        18,
        color="#667085",
    )
    half = (value_width - 42) // 2
    _draw_value_box(painter, QRect(value_x, y, half, 56), "5", enabled=False)
    _draw_text(painter, QRect(value_x + half, y, 42, 56), "/", 18, align=Qt.AlignCenter)
    _draw_value_box(
        painter,
        QRect(value_x + half + 42, y, half, 56),
        "5",
        enabled=False,
    )
    y += 88

    button_gap = 14
    button_width = (width - button_gap * 2) // 3
    for index, key in enumerate(("edit", "save", "reset")):
        _draw_button(
            painter,
            QRect(x + index * (button_width + button_gap), y, button_width, 58),
            text[key],
            primary=False,
            enabled=key == "edit",
        )


def _settings_text(language: str) -> dict[str, str]:
    if language == "en":
        return {
            "source_title": "Input files",
            "step_model": "STEP model",
            "gcode_path": "G-code file",
            "load_demo": "Open impeller project",
            "open_gcode": "Open existing G-code",
            "open_step": "Open STEP",
            "slice_preview": "Parse G-code",
            "parameter_title": "Process parameters",
            "layer_height": "Layer height",
            "print_speed": "Print speed",
            "extrusion_width": "Extrusion width",
            "nozzle_diameter": "Nozzle diameter",
            "process_mode": "Path mode",
            "top_bottom": "Top / bottom layers",
            "edit": "Edit",
            "save": "Save",
            "reset": "Reset",
        }
    return {
        "source_title": "输入文件",
        "step_model": "STEP 模型",
        "gcode_path": "G-code 文件",
        "load_demo": "打开叶轮项目",
        "open_gcode": "打开现有 G-code",
        "open_step": "打开 STEP",
        "slice_preview": "解析 G-code",
        "parameter_title": "工艺参数",
        "layer_height": "层高",
        "print_speed": "打印速度",
        "extrusion_width": "挤出宽度",
        "nozzle_diameter": "喷嘴直径",
        "process_mode": "路径模式",
        "top_bottom": "顶底层",
        "edit": "编辑参数",
        "save": "保存参数",
        "reset": "恢复默认值",
    }


def _draw_card_background(painter: QPainter, rect: QRect) -> None:
    painter.setPen(QPen(QColor("#D7DEE8"), 1))
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawRoundedRect(QRectF(rect), 10, 10)


def _draw_value_box(
    painter: QPainter,
    rect: QRect,
    text: str,
    *,
    enabled: bool,
) -> None:
    painter.setPen(QPen(QColor("#D7DEE8"), 1))
    painter.setBrush(QColor("#F8FAFC" if enabled else "#EEF2F6"))
    painter.drawRoundedRect(QRectF(rect), 6, 6)
    _draw_text(
        painter,
        rect.adjusted(16, 0, -16, 0),
        text,
        18,
        color="#1F2937" if enabled else "#98A2B3",
        align=Qt.AlignLeft | Qt.AlignVCenter,
    )


def _draw_button(
    painter: QPainter,
    rect: QRect,
    text: str,
    *,
    primary: bool,
    enabled: bool = True,
) -> None:
    if not enabled:
        border = "#D7DEE8"
        background = "#EEF2F6"
        foreground = "#98A2B3"
    elif primary:
        border = "#2563EB"
        background = "#2563EB"
        foreground = "#FFFFFF"
    else:
        border = "#D7DEE8"
        background = "#FFFFFF"
        foreground = "#1F2937"
    painter.setPen(QPen(QColor(border), 1))
    painter.setBrush(QColor(background))
    painter.drawRoundedRect(QRectF(rect), 6, 6)
    _draw_text(
        painter,
        rect,
        text,
        18,
        color=foreground,
        bold=primary,
        align=Qt.AlignCenter,
    )


def _draw_checkbox(painter: QPainter, rect: QRect, text: str, *, checked: bool) -> None:
    box = QRect(rect.x() + 8, rect.y() + 14, 28, 28)
    painter.setPen(QPen(QColor("#C9D2DF"), 2))
    painter.setBrush(QColor("#F8FAFC"))
    painter.drawRect(box)
    if checked:
        painter.setPen(QPen(QColor("#2563EB"), 3))
        painter.drawLine(box.x() + 5, box.center().y(), box.center().x(), box.bottom() - 5)
        painter.drawLine(box.center().x(), box.bottom() - 5, box.right() - 4, box.y() + 5)
    _draw_text(
        painter,
        QRect(box.right() + 12, rect.y(), rect.width() - 52, rect.height()),
        text,
        18,
        color="#667085",
        align=Qt.AlignLeft | Qt.AlignVCenter,
    )


def _draw_text(
    painter: QPainter,
    rect: QRect,
    text: str,
    pixel_size: int,
    *,
    color: str = "#1F2937",
    bold: bool = False,
    align: int = Qt.AlignLeft | Qt.AlignVCenter,
    word_wrap: bool = False,
) -> None:
    font = _pixel_font(
        "Microsoft YaHei UI",
        pixel_size,
        QFont.DemiBold if bold else QFont.Normal,
    )
    painter.setFont(font)
    painter.setPen(QColor(color))
    flags = align | (Qt.TextWordWrap if word_wrap else 0)
    painter.drawText(rect, flags, str(text))


def _pixel_font(family: str, pixel_size: int, weight: int = QFont.Normal) -> QFont:
    """Create a deterministic font for the fixed 1920 x 1080 logical canvas."""

    if pixel_size <= 0:
        raise ValueError("Font pixel size must be positive")
    font = QFont(family)
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def _render_gcode_panel(path: Path, language: str) -> tuple[bytes, int, list[int]]:
    with GCodeSourceIndex(path) as index:
        representative = index.representative_five_axis_line()
        if representative is None:
            raise RuntimeError("G-code contains no five-axis instruction with F/XYZ/A/C/E fields")
        context = index.read_context(representative, radius=CONTEXT_RADIUS)

    image = _new_canvas()
    painter = QPainter(image)
    if not painter.isActive():
        raise RuntimeError("Could not start G-code-panel painter")
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.scale(OUTPUT_SCALE, OUTPUT_SCALE)
    try:
        painter.fillRect(QRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT), QColor("#F3F5F7"))
        target = QRect(24, 24, LOGICAL_WIDTH - 48, LOGICAL_HEIGHT - 48)
        painter.setPen(QPen(QColor("#D7DEE8"), 1))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(QRectF(target), 10, 10)

        header = QRect(target.x(), target.y(), target.width(), 132)
        painter.fillRect(header.adjusted(1, 1, -1, 0), QColor("#F3F6FA"))
        header_layout = _gcode_header_layout(header, language)
        _draw_text(
            painter,
            header_layout.title_rect,
            path.name,
            24,
            bold=True,
        )
        _draw_syntax_chips(painter, header_layout, language)

        body_layout = _fit_gcode_body_layout(
            target,
            context,
            code_top=target.y() + 150,
            preferred_pixel_size=22,
            minimum_pixel_size=18,
        )
        metrics = QFontMetricsF(body_layout.font)
        for row, (line_number, source) in enumerate(context):
            y = body_layout.code_top + row * body_layout.line_height
            line_rect = QRect(
                target.x() + 12,
                y - 3,
                target.width() - 24,
                body_layout.line_height,
            )
            if line_number == representative:
                painter.fillRect(line_rect, QColor("#EAF2FF"))
            painter.setFont(body_layout.font)
            painter.setPen(QColor("#667085"))
            painter.drawText(
                QRect(
                    body_layout.gutter_rect.x(),
                    y,
                    body_layout.gutter_rect.width(),
                    body_layout.line_height - 4,
                ),
                Qt.AlignRight | Qt.AlignVCenter,
                str(line_number),
            )
            painter.save()
            painter.setClipRect(body_layout.code_clip_rect)
            baseline = y + int((body_layout.line_height + metrics.ascent() - metrics.descent()) / 2)
            _draw_syntax_line(
                painter,
                source,
                body_layout.code_clip_rect.x(),
                baseline,
                metrics,
            )
            painter.restore()
    finally:
        painter.end()
    return (
        _encode_png(image.convertToFormat(QImage.Format_RGB888)),
        representative,
        [line_number for line_number, _source in context],
    )


def _syntax_chips(language: str) -> tuple[tuple[str, str], ...]:
    if language == "en":
        return (
            ("Feedrate F", "#2563EB"),
            ("X/Y/Z coordinates", "#16845B"),
            ("A/C rotary axes", "#E26A00"),
            ("Extrusion E", "#7A5AF8"),
        )
    return (
        ("进给 F", "#2563EB"),
        ("X/Y/Z 坐标", "#16845B"),
        ("A/C 转轴", "#E26A00"),
        ("挤出 E", "#7A5AF8"),
    )


def _gcode_header_layout(header: QRect, language: str) -> GCodeHeaderLayout:
    """Lay out a two-row header and fail loudly if translated chips cannot fit."""

    title_rect = QRect(header.x() + 24, header.y() + 8, header.width() - 48, 48)
    chip_band = QRect(header.x() + 24, header.y() + 66, header.width() - 48, 50)
    chip_font = _pixel_font("Microsoft YaHei UI", 16, QFont.DemiBold)
    metrics = QFontMetricsF(chip_font)
    chips = _syntax_chips(language)
    widths = [math.ceil(metrics.horizontalAdvance(text)) + 24 for text, _color in chips]
    gap = 14
    total_width = sum(widths) + gap * (len(chips) - 1)
    if total_width > chip_band.width():
        raise RuntimeError(
            f"The {language!r} syntax labels require {total_width}px but the header provides "
            f"{chip_band.width()}px"
        )
    chip_x = chip_band.right() - total_width + 1
    chip_rects = tuple(
        QRect(chip_x + sum(widths[:index]) + gap * index, chip_band.y() + 2, width, 46)
        for index, width in enumerate(widths)
    )
    return GCodeHeaderLayout(title_rect, chip_band, chip_rects)


def _draw_syntax_chips(
    painter: QPainter,
    layout: GCodeHeaderLayout,
    language: str,
) -> None:
    chip_font = _pixel_font("Microsoft YaHei UI", 16, QFont.DemiBold)
    painter.setFont(chip_font)
    for (text, color), rect in zip(_syntax_chips(language), layout.chip_rects):
        painter.setPen(QPen(QColor(color), 1))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(QRectF(rect), 5, 5)
        _draw_text(painter, rect, text, 16, color=color, bold=True, align=Qt.AlignCenter)


def _fit_gcode_body_layout(
    target: QRect,
    context: Sequence[tuple[int, str]],
    *,
    code_top: int,
    preferred_pixel_size: int,
    minimum_pixel_size: int,
) -> GCodeBodyLayout:
    """Choose the largest readable monospace font that shows every line in full."""

    if not context:
        raise RuntimeError("The selected G-code context is empty")
    if minimum_pixel_size <= 0 or preferred_pixel_size < minimum_pixel_size:
        raise ValueError("Invalid G-code font-size range")
    for pixel_size in range(preferred_pixel_size, minimum_pixel_size - 1, -1):
        font = _pixel_font("Cascadia Mono", pixel_size)
        font.setStyleHint(QFont.Monospace)
        metrics = QFontMetricsF(font)
        gutter_width = math.ceil(
            max(metrics.horizontalAdvance(str(line_number)) for line_number, _source in context)
        ) + 14
        gutter_rect = QRect(target.x() + 18, code_top, gutter_width, target.bottom() - code_top - 12)
        code_left = gutter_rect.right() + 22
        code_clip = QRect(
            code_left,
            code_top - 4,
            target.right() - code_left - 12,
            target.bottom() - code_top - 8,
        )
        line_height = max(40, math.ceil(metrics.height()) + 9)
        widest_line = max(metrics.horizontalAdvance(source) for _line_number, source in context)
        vertical_required = line_height * len(context)
        if widest_line <= code_clip.width() and vertical_required <= code_clip.height():
            return GCodeBodyLayout(
                font=font,
                pixel_size=pixel_size,
                line_height=line_height,
                code_top=code_top,
                gutter_rect=gutter_rect,
                code_clip_rect=code_clip,
            )
    raise RuntimeError(
        "The selected G-code context cannot fit the paper panel without clipping"
    )


_WORD = re.compile(
    r"(?<![A-Za-z])([FXYZACE])([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)",
    re.IGNORECASE,
)


def _draw_syntax_line(
    painter: QPainter,
    source: str,
    x: int,
    baseline: int,
    metrics: QFontMetricsF,
) -> None:
    comment_at = source.find(";")
    code = source if comment_at < 0 else source[:comment_at]
    cursor = 0
    draw_x = float(x)
    colors = {
        "F": "#2563EB",
        "X": "#16845B",
        "Y": "#16845B",
        "Z": "#16845B",
        "A": "#E26A00",
        "C": "#E26A00",
        "E": "#7A5AF8",
    }
    for match in _WORD.finditer(code):
        plain = code[cursor : match.start()]
        painter.setPen(QColor("#1F2937"))
        painter.drawText(QPointF(draw_x, baseline), plain)
        draw_x += metrics.horizontalAdvance(plain)
        token = match.group(0)
        painter.setPen(QColor(colors[match.group(1).upper()]))
        painter.drawText(QPointF(draw_x, baseline), token)
        draw_x += metrics.horizontalAdvance(token)
        cursor = match.end()
    tail = code[cursor:]
    painter.setPen(QColor("#1F2937"))
    painter.drawText(QPointF(draw_x, baseline), tail)
    draw_x += metrics.horizontalAdvance(tail)
    if comment_at >= 0:
        painter.setPen(QColor("#98A2B3"))
        painter.drawText(QPointF(draw_x, baseline), source[comment_at:])


def _new_canvas() -> QImage:
    image = QImage(CANVAS_WIDTH, CANVAS_HEIGHT, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor("#F3F5F7"))
    return image


def _encode_png(image: QImage) -> bytes:
    image.setDotsPerMeterX(PIXELS_PER_METER)
    image.setDotsPerMeterY(PIXELS_PER_METER)
    buffer = QBuffer()
    if not buffer.open(QIODevice.WriteOnly):
        raise RuntimeError("Could not open PNG output buffer")
    writer = QImageWriter(buffer, b"png")
    if not writer.write(image):
        raise RuntimeError(writer.errorString())
    payload = bytes(buffer.data())
    buffer.close()
    payload = _replace_png_contract_chunks(payload)
    _verify_png_contract(_inspect_png(payload))
    return payload


def _encode_uncompressed_tiff(png_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    image = QImage.fromData(png_bytes, b"png")
    if image.isNull():
        raise RuntimeError("Could not decode the panel PNG for TIFF export")
    image = image.convertToFormat(QImage.Format_RGB888)
    image.setDotsPerMeterX(PIXELS_PER_METER)
    image.setDotsPerMeterY(PIXELS_PER_METER)
    buffer = QBuffer()
    if not buffer.open(QIODevice.WriteOnly):
        raise RuntimeError("Could not open TIFF output buffer")
    writer = QImageWriter(buffer, b"tiff")
    writer.setCompression(0)
    if not writer.write(image):
        raise RuntimeError(writer.errorString())
    payload = bytes(buffer.data())
    buffer.close()
    info = _inspect_tiff(payload)
    _verify_uncompressed_tiff(info, expected_width=image.width(), expected_height=image.height())
    return payload, info


def _inspect_tiff(payload: bytes) -> dict[str, Any]:
    """Read the baseline TIFF fields needed to prove an RGB file is uncompressed."""

    if len(payload) < 8 or payload[:2] not in {b"II", b"MM"}:
        raise RuntimeError("Invalid TIFF byte-order marker")
    endian = "<" if payload[:2] == b"II" else ">"
    if struct.unpack_from(f"{endian}H", payload, 2)[0] != 42:
        raise RuntimeError("Invalid TIFF magic value")
    ifd_offset = struct.unpack_from(f"{endian}I", payload, 4)[0]
    if ifd_offset < 8 or ifd_offset + 2 > len(payload):
        raise RuntimeError("Invalid TIFF IFD offset")
    entry_count = struct.unpack_from(f"{endian}H", payload, ifd_offset)[0]
    entries_end = ifd_offset + 2 + entry_count * 12
    if entries_end + 4 > len(payload):
        raise RuntimeError("Truncated TIFF IFD")

    type_sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8}
    tags: dict[int, list[int] | list[tuple[int, int]]] = {}
    for index in range(entry_count):
        offset = ifd_offset + 2 + index * 12
        tag, field_type, count = struct.unpack_from(f"{endian}HHI", payload, offset)
        size = type_sizes.get(field_type)
        if size is None or count <= 0:
            continue
        byte_count = size * count
        if byte_count <= 4:
            raw = payload[offset + 8 : offset + 8 + byte_count]
        else:
            value_offset = struct.unpack_from(f"{endian}I", payload, offset + 8)[0]
            if value_offset + byte_count > len(payload):
                raise RuntimeError(f"TIFF tag {tag} points outside the file")
            raw = payload[value_offset : value_offset + byte_count]
        if field_type == 3:
            tags[tag] = list(struct.unpack(f"{endian}{count}H", raw))
        elif field_type == 4:
            tags[tag] = list(struct.unpack(f"{endian}{count}I", raw))
        elif field_type == 5:
            tags[tag] = [
                struct.unpack_from(f"{endian}II", raw, item * 8)
                for item in range(count)
            ]

    def scalar(tag: int) -> int:
        values = tags.get(tag)
        if not values or isinstance(values[0], tuple):
            raise RuntimeError(f"TIFF tag {tag} is missing or invalid")
        return int(values[0])

    def rational(tag: int) -> float | None:
        values = tags.get(tag)
        if not values or not isinstance(values[0], tuple):
            return None
        numerator, denominator = values[0]
        return float(numerator) / float(denominator) if denominator else None

    bits = tags.get(258)
    if not bits or isinstance(bits[0], tuple):
        raise RuntimeError("TIFF BitsPerSample is missing or invalid")
    x_resolution = rational(282)
    y_resolution = rational(283)
    resolution_unit = scalar(296) if 296 in tags else 1
    if resolution_unit == 3:
        x_dpi = x_resolution * 2.54 if x_resolution is not None else None
        y_dpi = y_resolution * 2.54 if y_resolution is not None else None
    else:
        x_dpi = x_resolution
        y_dpi = y_resolution
    return {
        "width": scalar(256),
        "height": scalar(257),
        "bits_per_sample": [int(value) for value in bits],
        "compression": scalar(259),
        "photometric_interpretation": scalar(262),
        "samples_per_pixel": scalar(277),
        "resolution_unit": resolution_unit,
        "x_dpi": x_dpi,
        "y_dpi": y_dpi,
    }


def _verify_uncompressed_tiff(
    info: Mapping[str, Any],
    *,
    expected_width: int = CANVAS_WIDTH,
    expected_height: int = CANVAS_HEIGHT,
) -> None:
    if (int(info["width"]), int(info["height"])) != (
        expected_width,
        expected_height,
    ):
        raise RuntimeError("TIFF dimensions do not match the source panel")
    if int(info["compression"]) != 1:
        raise RuntimeError("TIFF is compressed; expected baseline Compression=1")
    if int(info["photometric_interpretation"]) != 2:
        raise RuntimeError("TIFF is not encoded as RGB")
    if int(info["samples_per_pixel"]) != 3:
        raise RuntimeError("TIFF must contain exactly three RGB samples per pixel")
    if list(info["bits_per_sample"]) != [8, 8, 8]:
        raise RuntimeError("TIFF must contain 8-bit RGB samples")
    for key in ("x_dpi", "y_dpi"):
        value = info.get(key)
        if value is None or abs(float(value) - OUTPUT_DPI) > 0.05:
            raise RuntimeError("TIFF resolution metadata is not 300 dpi")


def _source_audit(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    stat = resolved.stat()
    return {
        "path": str(resolved),
        "name": resolved.name,
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
