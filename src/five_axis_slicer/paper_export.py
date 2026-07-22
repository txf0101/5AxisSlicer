from __future__ import annotations

"""Deterministic paper-figure export for the result preview page.

The exporter deliberately keeps UI composition separate from the result-page
implementation.  A caller supplies the application widget and the active 3-D
viewer; this module lays the widget out at 1920 x 1080 logical pixels, renders
the Qt hierarchy at 2x, and replaces the viewport area with an explicit scene
capture from the viewer backend.
"""

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import time
from types import MappingProxyType
from typing import Any, Iterator
import uuid
import zlib

from PyQt5.QtCore import (
    QBuffer,
    QEvent,
    QEventLoop,
    QIODevice,
    QPoint,
    QRect,
    QSaveFile,
    QThread,
    Qt,
    PYQT_VERSION_STR,
    QT_VERSION_STR,
)
from PyQt5.QtGui import QColor, QImage, QImageWriter, QPainter, QRegion
from PyQt5.QtWidgets import QApplication, QWidget

from .theme import LIGHT_THEME


PAPER_EXPORT_SCHEMA_VERSION = 1
LOGICAL_WIDTH = 1920
LOGICAL_HEIGHT = 1080
OUTPUT_SCALE = 2
OUTPUT_WIDTH = LOGICAL_WIDTH * OUTPUT_SCALE
OUTPUT_HEIGHT = LOGICAL_HEIGHT * OUTPUT_SCALE
OUTPUT_DPI = 300
PIXELS_PER_METER = round(OUTPUT_DPI / 0.0254)
PAPER_EXPORT_LOCK_TIMEOUT_SECONDS = 5.0
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DEFAULT_DISPLAY_ITEMS: Mapping[str, bool] = MappingProxyType(
    {
        "model": True,
        "positive_extrusion": True,
        "travel": False,
        "pose_samples": False,
        "start_end": True,
        "part_axes": True,
        "orientation_cube": True,
    }
)


class PaperExportError(RuntimeError):
    """Raised when a deterministic paper figure cannot be produced."""


@dataclass(frozen=True, slots=True)
class SourceFileAudit:
    """Stable evidence for one file referenced by the exported figure."""

    role: str
    path: str
    exists: bool
    size_bytes: int | None
    mtime_ns: int | None
    mtime_utc: str | None
    sha256: str | None

    @property
    def name(self) -> str:
        return Path(self.path).name

    def to_json(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "path": self.path,
            "name": self.name,
            "exists": self.exists,
            "size_bytes": self.size_bytes,
            "mtime_ns": self.mtime_ns,
            "mtime_utc": self.mtime_utc,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class RenderSnapshot:
    """Immutable audit state captured for a single rendered artifact."""

    captured_at_utc: str
    language: str
    sources: tuple[SourceFileAudit, ...]
    statistics: Mapping[str, Any]
    camera: Mapping[str, Any]
    display_items: Mapping[str, Any]
    render_parameters: Mapping[str, Any]
    artifact: Mapping[str, Any]

    def __post_init__(self) -> None:
        language = _normalise_language(self.language)
        object.__setattr__(self, "language", language)
        object.__setattr__(self, "sources", tuple(self.sources))
        for name in ("statistics", "camera", "display_items", "render_parameters", "artifact"):
            value = _normalise_json_value(getattr(self, name), path=name)
            if not isinstance(value, dict):
                raise TypeError(f"{name} must be a mapping")
            object.__setattr__(self, name, _freeze_json(value))

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": PAPER_EXPORT_SCHEMA_VERSION,
            "captured_at_utc": self.captured_at_utc,
            "language": self.language,
            "sources": {source.role: source.to_json() for source in self.sources},
            "statistics": _thaw_json(self.statistics),
            "camera": _thaw_json(self.camera),
            "display_items": _thaw_json(self.display_items),
            "render_parameters": _thaw_json(self.render_parameters),
            "artifact": _thaw_json(self.artifact),
        }


@dataclass(frozen=True, slots=True)
class PaperExportResult:
    image_path: Path
    sidecar_path: Path
    snapshot: RenderSnapshot

    def to_json(self) -> dict[str, Any]:
        return {
            "image_path": str(self.image_path),
            "sidecar_path": str(self.sidecar_path),
            "audit": self.snapshot.to_json(),
        }


def export_paper_preview(
    root_widget: QWidget,
    viewer: QWidget,
    output_path: str | Path,
    *,
    language: str,
    sources: Mapping[str, str | Path | None] | None = None,
    source_audits: Mapping[str, Any] | Sequence[Any] | None = None,
    precomputed_source_audits: Mapping[str, Any] | Sequence[Any] | None = None,
    statistics: Mapping[str, Any] | None = None,
    display_items: Mapping[str, Any] | None = None,
    viewport_widget: QWidget | None = None,
    overlay_widgets: Sequence[QWidget] | None = None,
    camera: Mapping[str, Any] | None = None,
    render_parameters: Mapping[str, Any] | None = None,
    allow_scene_fallback: bool = True,
    strict: bool = False,
) -> PaperExportResult:
    """Export one exact 3840 x 2160 paper-preview PNG and audit JSON.

    ``root_widget`` should be the application-owned widget whose title row,
    menu, toolbar and result page belong in the figure.  ``viewport_widget``
    defaults to ``viewer`` and controls where the separately rendered scene is
    composited.  The function must run on Qt's GUI thread.

    The formal path requires the OpenGL backend, its complete-timeline paper
    capability, and ``viewer.render_scene_image(width, height)``.  ``strict``
    rejects a missing formal capability before rendering or writing output.
    Passing ``allow_scene_fallback=False`` retains its historical strict-scene
    behaviour and also enables the capability gate.  A non-strict export stays
    usable while recording every formal-path gap in the sidecar.
    """

    _require_gui_thread()
    if not isinstance(root_widget, QWidget):
        raise TypeError("root_widget must be a QWidget")
    if not isinstance(viewer, QWidget):
        raise TypeError("viewer must be a QWidget")
    viewport = viewer if viewport_widget is None else viewport_widget
    if not isinstance(viewport, QWidget):
        raise TypeError("viewport_widget must be a QWidget")

    destination = _normalise_output_path(output_path)
    sidecar_path = destination.with_suffix(".json")
    language_value = _normalise_language(language)
    strict_mode = bool(strict) or not allow_scene_fallback

    degradations: list[dict[str, str]] = []
    capabilities = _viewer_capabilities(viewer, degradations)
    capability_degradations = _formal_capability_degradations(capabilities)
    if strict_mode and capability_degradations:
        details = "; ".join(item["reason"] for item in capability_degradations)
        raise PaperExportError(f"Strict paper export capability check failed: {details}")
    degradations.extend(capability_degradations)

    captured_at = _utc_now()
    precomputed_audits = _select_precomputed_source_audits(
        source_audits,
        precomputed_source_audits,
    )
    if precomputed_audits is None:
        source_values = collect_viewer_sources(viewer) if sources is None else dict(sources)
        if strict_mode and any(value not in (None, "") for value in source_values.values()):
            raise PaperExportError(
                "Strict paper export requires load-time source_audits for every source"
            )
        source_audit_values = tuple(
            audit_source_file(role, value)
            for role, value in sorted(source_values.items(), key=lambda item: str(item[0]))
            if value not in (None, "")
        )
        source_audit_basis = "export_time"
        source_snapshot_checked = False
    else:
        source_audit_values = _normalise_precomputed_source_audits(precomputed_audits)
        source_audit_basis = "load_snapshot"
        source_snapshot_checked = sources is not None
        if sources is not None:
            source_degradations = _source_snapshot_degradations(
                dict(sources),
                source_audit_values,
            )
            if strict_mode and source_degradations:
                details = "; ".join(item["reason"] for item in source_degradations)
                raise PaperExportError(f"Source snapshot validation failed: {details}")
            degradations.extend(source_degradations)
    statistics_value = collect_viewer_statistics(viewer) if statistics is None else dict(statistics)

    requested_display = dict(DEFAULT_DISPLAY_ITEMS)
    if display_items:
        requested_display.update(display_items)

    with _fixed_logical_layout(root_widget):
        viewport_rect = _viewport_rect(root_widget, viewport)
        canvas = _render_qt_widget(root_widget)
        scene_width = viewport_rect.width() * OUTPUT_SCALE
        scene_height = viewport_rect.height() * OUTPUT_SCALE
        if strict_mode:
            _require_formal_viewer_state(viewer, stage="before scene capture")
        scene_image, capture_method, requested_scene_size = _capture_scene(
            viewer,
            scene_width,
            scene_height,
            allow_fallback=allow_scene_fallback and not strict_mode,
            degradations=degradations,
        )
        actual_scene_size = (scene_image.width(), scene_image.height())
        _composite_scene(canvas, scene_image, viewport_rect)
        rendered_overlays = _render_overlay_widgets(
            canvas,
            root_widget,
            tuple(overlay_widgets or ()),
        )
        camera_value = dict(camera) if camera is not None else _viewer_camera(viewer, degradations)
        if strict_mode:
            _require_formal_viewer_state(viewer, stage="after scene capture")

    # RGB888 makes the PNG background unambiguously opaque, including when a
    # backend returns an RGBA framebuffer.
    opaque_canvas = canvas.convertToFormat(QImage.Format_RGB888)
    opaque_canvas.setDotsPerMeterX(PIXELS_PER_METER)
    opaque_canvas.setDotsPerMeterY(PIXELS_PER_METER)
    png_payload = _encode_png(opaque_canvas)
    png_info = _inspect_png(png_payload)
    _verify_png_contract(png_info)
    image_sha256 = hashlib.sha256(png_payload).hexdigest()

    parameters = {
        "preset": "paper_result_preview_4k",
        "logical_layout_px": {"width": LOGICAL_WIDTH, "height": LOGICAL_HEIGHT},
        "output_scale": OUTPUT_SCALE,
        "output_px": {"width": OUTPUT_WIDTH, "height": OUTPUT_HEIGHT},
        "dpi_requested": OUTPUT_DPI,
        "pixels_per_meter": PIXELS_PER_METER,
        "dpi_encoded": PIXELS_PER_METER * 0.0254,
        "color_space": "sRGB",
        "png_color_profile": "sRGB rendering intent",
        "background": LIGHT_THEME.window,
        "opaque_background": True,
        "qt_capture_method": "QWidget.render",
        "qt_overlay_widgets": rendered_overlays,
        "scene_capture_method": capture_method,
        "scene_request_px": {
            "width": requested_scene_size[0],
            "height": requested_scene_size[1],
        },
        "scene_image_px": {
            "width": actual_scene_size[0],
            "height": actual_scene_size[1],
        },
        "viewport_rect_logical_px": {
            "x": viewport_rect.x(),
            "y": viewport_rect.y(),
            "width": viewport_rect.width(),
            "height": viewport_rect.height(),
        },
        "viewer_capabilities": capabilities,
        "source_audit_basis": source_audit_basis,
        "source_snapshot_checked": source_snapshot_checked,
        "degraded": bool(degradations),
        "degradations": degradations,
        "qt_version": QT_VERSION_STR,
        "pyqt_version": PYQT_VERSION_STR,
    }
    if render_parameters:
        # Caller-owned details live below a named key so fixed acceptance
        # parameters cannot be accidentally overwritten.
        parameters["caller"] = dict(render_parameters)

    artifact = {
        "file_name": destination.name,
        "path": str(destination),
        "width_px": int(png_info["width"]),
        "height_px": int(png_info["height"]),
        "sha256": image_sha256,
        "byte_size": len(png_payload),
        "png_color_type": int(png_info["color_type"]),
        "opaque": int(png_info["color_type"]) not in {4, 6} and "tRNS" not in png_info["chunks"],
        "color_space": "sRGB",
        "dpi": OUTPUT_DPI,
    }
    snapshot = RenderSnapshot(
        captured_at_utc=captured_at,
        language=language_value,
        sources=source_audit_values,
        statistics=statistics_value,
        camera=camera_value,
        display_items=requested_display,
        render_parameters=parameters,
        artifact=artifact,
    )
    sidecar_payload = (
        json.dumps(
            snapshot.to_json(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")

    destination.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_pair(
        destination,
        png_payload,
        sidecar_path,
        sidecar_payload,
    )
    return PaperExportResult(destination, sidecar_path, snapshot)


def audit_source_file(role: str, path: str | Path) -> SourceFileAudit:
    """Hash one source while guarding against a concurrent file rewrite."""

    source = Path(path).expanduser().resolve()
    role_value = str(role).strip()
    if not role_value:
        raise ValueError("Source role cannot be empty")
    if not source.is_file():
        return SourceFileAudit(role_value, str(source), False, None, None, None, None)

    for attempt in range(2):
        before = source.stat()
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        after = source.stat()
        stable = before.st_size == after.st_size and before.st_mtime_ns == after.st_mtime_ns
        if stable:
            timestamp = (
                datetime.fromtimestamp(after.st_mtime, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
            return SourceFileAudit(
                role=role_value,
                path=str(source),
                exists=True,
                size_bytes=after.st_size,
                mtime_ns=after.st_mtime_ns,
                mtime_utc=timestamp,
                sha256=digest.hexdigest(),
            )
        if attempt == 1:
            raise PaperExportError(f"Source changed while hashing: {source}")
    raise AssertionError("unreachable")


def _select_precomputed_source_audits(
    source_audits: Mapping[str, Any] | Sequence[Any] | None,
    precomputed_source_audits: Mapping[str, Any] | Sequence[Any] | None,
) -> Mapping[str, Any] | Sequence[Any] | None:
    if source_audits is not None and precomputed_source_audits is not None:
        raise ValueError(
            "source_audits and precomputed_source_audits are aliases; provide only one"
        )
    return source_audits if source_audits is not None else precomputed_source_audits


def _normalise_precomputed_source_audits(
    values: Mapping[str, Any] | Sequence[Any],
) -> tuple[SourceFileAudit, ...]:
    """Copy serialized load-time evidence into immutable audit records."""

    if isinstance(values, Mapping):
        if "path" in values:
            entries: list[tuple[Any, Any]] = [(values.get("role"), values)]
        else:
            entries = list(values.items())
    elif isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)):
        entries = [(None, item) for item in values]
    else:
        raise TypeError("source_audits must be a mapping or a sequence of audit records")

    output: list[SourceFileAudit] = []
    seen_roles: set[str] = set()
    for role_hint, value in entries:
        if isinstance(value, SourceFileAudit):
            payload: Mapping[str, Any] = value.to_json()
        elif isinstance(value, Mapping):
            payload = dict(value)
        else:
            raise TypeError(
                "Each precomputed source audit must be SourceFileAudit or a mapping"
            )

        hinted_role = "" if role_hint is None else str(role_hint).strip()
        payload_role = str(payload.get("role", "")).strip()
        if hinted_role and payload_role and hinted_role != payload_role:
            raise ValueError(
                f"Source audit role mismatch: mapping key {hinted_role!r}, record {payload_role!r}"
            )
        role = hinted_role or payload_role
        if not role:
            raise ValueError("A precomputed source audit role is required")
        if role in seen_roles:
            raise ValueError(f"Duplicate precomputed source audit role: {role}")

        required = ("path", "size_bytes", "mtime_ns", "sha256")
        missing = [name for name in required if name not in payload]
        if missing:
            raise ValueError(
                f"Precomputed source audit {role!r} is missing: {', '.join(missing)}"
            )
        if payload["path"] in (None, ""):
            raise ValueError(f"Precomputed source audit {role!r} has an empty path")
        path_text = str(payload["path"]).strip()
        if not path_text:
            raise ValueError(f"Precomputed source audit {role!r} has an empty path")
        path = Path(path_text).expanduser().resolve()
        recorded_name = str(payload.get("name", path.name)).strip()
        if not recorded_name or recorded_name != path.name:
            raise ValueError(
                f"Precomputed source audit {role!r} name does not match its path"
            )

        exists_value = payload.get("exists", True)
        if not isinstance(exists_value, bool):
            raise TypeError(f"Precomputed source audit {role!r} exists must be boolean")
        size_bytes = _optional_nonnegative_int(payload["size_bytes"], role, "size_bytes")
        mtime_ns = _optional_nonnegative_int(payload["mtime_ns"], role, "mtime_ns")
        sha256 = _normalise_optional_sha256(payload["sha256"], role)
        if exists_value and (size_bytes is None or mtime_ns is None or sha256 is None):
            raise ValueError(
                f"Existing precomputed source audit {role!r} requires size, mtime, and SHA-256"
            )

        mtime_utc_value = payload.get("mtime_utc")
        if mtime_utc_value is None and mtime_ns is not None:
            mtime_utc = (
                datetime.fromtimestamp(mtime_ns / 1_000_000_000, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
        elif mtime_utc_value is None:
            mtime_utc = None
        else:
            mtime_utc = str(mtime_utc_value)

        output.append(
            SourceFileAudit(
                role=role,
                path=str(path),
                exists=exists_value,
                size_bytes=size_bytes,
                mtime_ns=mtime_ns,
                mtime_utc=mtime_utc,
                sha256=sha256,
            )
        )
        seen_roles.add(role)
    return tuple(sorted(output, key=lambda audit: audit.role))


def _optional_nonnegative_int(value: Any, role: str, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(
            f"Precomputed source audit {role!r} {field} must be a non-negative integer or null"
        )
    return value


def _normalise_optional_sha256(value: Any, role: str) -> str | None:
    if value is None:
        return None
    digest = str(value).strip().lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"Precomputed source audit {role!r} has an invalid SHA-256")
    return digest


def _source_snapshot_degradations(
    sources: Mapping[str, str | Path | None],
    source_audits: Sequence[SourceFileAudit],
) -> list[dict[str, str]]:
    """Compare selected files with load-time evidence without replacing it."""

    snapshots = {audit.role: audit for audit in source_audits}
    output: list[dict[str, str]] = []
    seen_roles: set[str] = set()
    for raw_role, path in sorted(sources.items(), key=lambda item: str(item[0])):
        if path in (None, ""):
            continue
        role = str(raw_role).strip()
        if not role:
            raise ValueError("Source role cannot be empty")
        if role in seen_roles:
            raise ValueError(f"Duplicate source role after normalization: {role}")
        seen_roles.add(role)
        snapshot = snapshots.get(role)
        if snapshot is None:
            output.append(
                {
                    "component": "source_snapshot",
                    "reason": f"Source {role!r} has no load-time audit record",
                    "fallback": "unverified selected source",
                }
            )
            continue
        try:
            current = audit_source_file(role, path)
        except Exception as exc:
            output.append(
                {
                    "component": "source_snapshot",
                    "reason": (
                        f"Source {role!r} could not be checked against its load-time audit: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                    "fallback": "load-time source audit retained",
                }
            )
            continue

        changed_fields: list[str] = []
        if os.path.normcase(current.path) != os.path.normcase(snapshot.path):
            changed_fields.append("path")
        for field in ("exists", "size_bytes", "mtime_ns", "sha256"):
            if getattr(current, field) != getattr(snapshot, field):
                changed_fields.append(field)
        if changed_fields:
            output.append(
                {
                    "component": "source_snapshot",
                    "reason": (
                        f"Source {role!r} changed after loading; differing fields: "
                        + ", ".join(changed_fields)
                    ),
                    "fallback": "load-time source audit retained",
                }
            )
    return output


def collect_viewer_sources(viewer: Any) -> dict[str, Path]:
    """Collect source paths from the common VTK/OpenGL viewer contract."""

    output: dict[str, Path] = {}
    model = getattr(viewer, "model", None)
    model_path = getattr(model, "source_path", None)
    if model_path:
        output["model"] = Path(model_path)
    preview = getattr(viewer, "gcode_preview", None)
    gcode_path = getattr(preview, "source_path", None)
    if gcode_path:
        output["gcode"] = Path(gcode_path)
    return output


def collect_viewer_statistics(viewer: Any) -> dict[str, Any]:
    """Collect model, G-code and drawn-scene counts without parsing sources."""

    output: dict[str, Any] = {}
    model = getattr(viewer, "model", None)
    if model is not None:
        bodies = getattr(model, "bodies", ())
        edges = getattr(model, "edges", ())
        output["model"] = {
            "body_count": len(bodies),
            "edge_count": len(edges),
        }
    preview = getattr(viewer, "gcode_preview", None)
    summary = getattr(preview, "summary", None)
    if callable(summary):
        output["gcode"] = summary()
    preview_state = getattr(viewer, "preview_state", None)
    if callable(preview_state):
        try:
            state = preview_state()
        except Exception as exc:  # pragma: no cover - defensive backend boundary
            output["scene_state_error"] = f"{type(exc).__name__}: {exc}"
        else:
            if isinstance(state, Mapping):
                output["scene"] = dict(state)
    return output


def _require_gui_thread() -> None:
    app = QApplication.instance()
    if app is None:
        raise PaperExportError("A QApplication is required for paper export")
    if QThread.currentThread() is not app.thread():
        raise PaperExportError("Paper export must run on the Qt GUI thread")


def _normalise_output_path(path: str | Path) -> Path:
    destination = Path(path).expanduser()
    if not destination.suffix:
        destination = destination.with_suffix(".png")
    if destination.suffix.lower() != ".png":
        raise ValueError("Paper export output must use the .png extension")
    return destination.resolve()


def _normalise_language(language: str) -> str:
    value = str(language).strip().lower().replace("-", "_")
    if value.startswith("zh"):
        return "zh"
    if value.startswith("en"):
        return "en"
    raise ValueError(f"Unsupported paper-export language: {language}")


@contextmanager
def _fixed_logical_layout(root: QWidget) -> Iterator[None]:
    old_size = root.size()
    old_minimum = root.minimumSize()
    old_maximum = root.maximumSize()
    old_state = root.windowState() if root.isWindow() else None
    try:
        root.setMinimumSize(0, 0)
        root.setMaximumSize(16_777_215, 16_777_215)
        if old_state is not None and old_state & (Qt.WindowMaximized | Qt.WindowFullScreen):
            root.setWindowState(old_state & ~Qt.WindowMaximized & ~Qt.WindowFullScreen)
        root.resize(LOGICAL_WIDTH, LOGICAL_HEIGHT)
        _flush_layout(root)
        if root.width() != LOGICAL_WIDTH or root.height() != LOGICAL_HEIGHT:
            raise PaperExportError(
                f"Fixed logical layout unavailable: received {root.width()}x{root.height()}"
            )
        yield
    finally:
        root.setMinimumSize(old_minimum)
        root.setMaximumSize(old_maximum)
        root.resize(old_size)
        if old_state is not None:
            root.setWindowState(old_state)
        _flush_layout(root)


def _flush_layout(root: QWidget) -> None:
    root.ensurePolished()
    for widget in (root, *root.findChildren(QWidget)):
        layout = widget.layout()
        if layout is not None:
            layout.activate()
    app = QApplication.instance()
    if app is not None:
        app.sendPostedEvents(None, QEvent.LayoutRequest)
        app.processEvents(QEventLoop.ExcludeUserInputEvents)


def _viewport_rect(root: QWidget, viewport: QWidget) -> QRect:
    origin = viewport.mapTo(root, QPoint(0, 0))
    rect = QRect(origin, viewport.size()).intersected(root.rect())
    if rect.width() <= 0 or rect.height() <= 0:
        raise PaperExportError("The 3-D viewport is outside the exported widget")
    return rect


def _render_qt_widget(root: QWidget) -> QImage:
    image = QImage(OUTPUT_WIDTH, OUTPUT_HEIGHT, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor(LIGHT_THEME.window))
    painter = QPainter(image)
    if not painter.isActive():
        raise PaperExportError("Could not start the Qt paper-export painter")
    try:
        painter.scale(OUTPUT_SCALE, OUTPUT_SCALE)
        flags = QWidget.DrawWindowBackground | QWidget.DrawChildren
        root.render(painter, QPoint(0, 0), QRegion(), flags)
    finally:
        painter.end()
    return image


def _capture_scene(
    viewer: QWidget,
    width: int,
    height: int,
    *,
    allow_fallback: bool,
    degradations: list[dict[str, str]],
) -> tuple[QImage, str, tuple[int, int]]:
    if width <= 0 or height <= 0:
        raise PaperExportError("The 3-D viewport has no drawable area")
    formal_error: Exception | None = None
    renderer = getattr(viewer, "render_scene_image", None)
    if callable(renderer):
        try:
            image = _coerce_qimage(renderer(width, height))
            if image.isNull():
                raise PaperExportError("render_scene_image returned a null image")
            return image, "viewer.render_scene_image", (width, height)
        except Exception as exc:  # backend boundary; sidecar keeps the evidence
            formal_error = exc
    else:
        formal_error = PaperExportError("viewer.render_scene_image is unavailable")

    if not allow_fallback:
        raise PaperExportError(f"Formal scene capture failed: {formal_error}") from formal_error
    degradations.append(
        {
            "component": "scene_capture",
            "reason": f"{type(formal_error).__name__}: {formal_error}",
            "fallback": "current framebuffer/widget grab",
        }
    )

    framebuffer = getattr(viewer, "grabFramebuffer", None)
    if callable(framebuffer):
        try:
            image = _coerce_qimage(framebuffer())
            if not image.isNull():
                return image, "viewer.grabFramebuffer (degraded)", (width, height)
        except Exception as exc:  # pragma: no cover - backend-dependent fallback
            degradations.append(
                {
                    "component": "scene_framebuffer_fallback",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "fallback": "QWidget.grab",
                }
            )

    try:
        pixmap = viewer.grab()
        image = pixmap.toImage()
    except Exception as exc:  # pragma: no cover - defensive Qt boundary
        raise PaperExportError(f"Scene fallback capture failed: {exc}") from exc
    if image.isNull():
        raise PaperExportError("Scene fallback capture returned a null image")
    return image, "QWidget.grab (degraded)", (width, height)


def _coerce_qimage(value: Any) -> QImage:
    if isinstance(value, QImage):
        return value.copy()
    to_image = getattr(value, "toImage", None)
    if callable(to_image):
        image = to_image()
        if isinstance(image, QImage):
            return image.copy()
    raise TypeError("Scene renderer must return QImage or QPixmap")


def _composite_scene(canvas: QImage, scene: QImage, logical_rect: QRect) -> None:
    target = QRect(
        logical_rect.x() * OUTPUT_SCALE,
        logical_rect.y() * OUTPUT_SCALE,
        logical_rect.width() * OUTPUT_SCALE,
        logical_rect.height() * OUTPUT_SCALE,
    )
    painter = QPainter(canvas)
    if not painter.isActive():
        raise PaperExportError("Could not start the scene-composition painter")
    try:
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawImage(target, scene)
    finally:
        painter.end()


def _render_overlay_widgets(
    canvas: QImage,
    root: QWidget,
    widgets: Sequence[QWidget],
) -> list[str]:
    """Restore Qt overlays that sit above the separately captured viewport."""

    rendered: list[str] = []
    if not widgets:
        return rendered
    painter = QPainter(canvas)
    painter.scale(OUTPUT_SCALE, OUTPUT_SCALE)
    try:
        for widget in widgets:
            if not isinstance(widget, QWidget) or not widget.isVisible():
                continue
            top_left = widget.mapTo(root, QPoint(0, 0))
            painter.save()
            painter.translate(top_left)
            widget.render(
                painter,
                QPoint(0, 0),
                QRegion(),
                QWidget.DrawChildren,
            )
            painter.restore()
            rendered.append(widget.objectName() or widget.__class__.__name__)
    finally:
        painter.end()
    return rendered


def _viewer_capabilities(viewer: Any, degradations: list[dict[str, str]]) -> dict[str, Any]:
    method = getattr(viewer, "capabilities", None)
    if callable(method):
        try:
            value = method()
            if isinstance(value, Mapping):
                return dict(value)
            raise TypeError("capabilities() did not return a mapping")
        except Exception as exc:  # pragma: no cover - defensive backend boundary
            degradations.append(
                {
                    "component": "viewer_capabilities",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "fallback": "backend attribute",
                }
            )
    return {"backend": str(getattr(viewer, "backend", "unknown"))}


def _formal_capability_degradations(
    capabilities: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Return auditable gaps against the formal OpenGL paper path."""

    output: list[dict[str, str]] = []
    backend = str(capabilities.get("backend", "unknown")).strip().casefold()
    if backend != "opengl":
        output.append(
            {
                "component": "paper_export_backend",
                "reason": (
                    "Formal paper export requires backend='opengl'; "
                    f"reported backend={backend or 'unknown'!r}"
                ),
                "fallback": "non-acceptance viewer backend",
            }
        )

    if capabilities.get("full_timeline_paper_path") is not True:
        if "full_timeline_paper_path" in capabilities:
            reported = repr(capabilities["full_timeline_paper_path"])
            reason = f"full_timeline_paper_path must be True; reported {reported}"
        else:
            reason = "full_timeline_paper_path capability is missing"
        output.append(
            {
                "component": "full_timeline_paper_path",
                "reason": reason,
                "fallback": "scene export without verified complete timeline",
            }
        )
    quality_mode = str(capabilities.get("quality_mode", "")).strip().casefold()
    paper_quality_active = capabilities.get("paper_quality_active")
    if quality_mode != "paper" or paper_quality_active is not True:
        output.append(
            {
                "component": "paper_quality_mode",
                "reason": (
                    "Formal paper export requires active paper quality without an "
                    f"interaction LOD; reported quality_mode={quality_mode or 'unknown'!r}, "
                    f"paper_quality_active={paper_quality_active!r}"
                ),
                "fallback": "interactive or unverified path buffer",
            }
        )
    return output


def _require_formal_viewer_state(viewer: Any, *, stage: str) -> None:
    degradations: list[dict[str, str]] = []
    capabilities = _viewer_capabilities(viewer, degradations)
    degradations.extend(_formal_capability_degradations(capabilities))
    if degradations:
        details = "; ".join(item["reason"] for item in degradations)
        raise PaperExportError(f"Strict paper export state changed {stage}: {details}")


def _viewer_camera(viewer: Any, degradations: list[dict[str, str]]) -> dict[str, Any]:
    method = getattr(viewer, "camera_state", None)
    if callable(method):
        try:
            value = method()
            if isinstance(value, Mapping):
                return dict(value)
            raise TypeError("camera_state() did not return a mapping")
        except Exception as exc:  # pragma: no cover - defensive backend boundary
            degradations.append(
                {
                    "component": "camera_audit",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "fallback": "empty camera record",
                }
            )
    return {}


def _encode_png(image: QImage) -> bytes:
    buffer = QBuffer()
    if not buffer.open(QIODevice.WriteOnly):
        raise PaperExportError("Could not allocate the PNG output buffer")
    writer = QImageWriter(buffer, b"png")
    writer.setText("Software", "5AxisSclicer V2.0")
    writer.setText("Description", "Paper result preview; fixed 1920x1080 logical layout at 2x")
    if not writer.write(image):
        message = writer.errorString() or "unknown Qt PNG writer error"
        raise PaperExportError(f"PNG encoding failed: {message}")
    payload = bytes(buffer.data())
    buffer.close()
    return _replace_png_contract_chunks(payload)


def _replace_png_contract_chunks(payload: bytes) -> bytes:
    chunks = _parse_png_chunks(payload)
    if not chunks or chunks[0][0] != b"IHDR":
        raise PaperExportError("PNG encoder produced an invalid chunk order")
    output = bytearray(PNG_SIGNATURE)
    output.extend(_pack_png_chunk(*chunks[0]))
    # PNG stores physical resolution as integer pixels per metre.  The nearest
    # representation of 300 dpi is 11811 pixels/m.
    output.extend(_pack_png_chunk(b"sRGB", b"\x00"))
    physical_resolution = struct.pack(
        ">IIB",
        PIXELS_PER_METER,
        PIXELS_PER_METER,
        1,
    )
    output.extend(_pack_png_chunk(b"pHYs", physical_resolution))
    for kind, data in chunks[1:]:
        if kind in {b"sRGB", b"iCCP", b"pHYs"}:
            continue
        output.extend(_pack_png_chunk(kind, data))
    return bytes(output)


def _parse_png_chunks(payload: bytes) -> list[tuple[bytes, bytes]]:
    if not payload.startswith(PNG_SIGNATURE):
        raise PaperExportError("Qt did not return a PNG payload")
    offset = len(PNG_SIGNATURE)
    chunks: list[tuple[bytes, bytes]] = []
    while offset + 12 <= len(payload):
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(payload):
            raise PaperExportError("Truncated PNG chunk")
        kind = payload[offset + 4 : offset + 8]
        data = payload[offset + 8 : offset + 8 + length]
        stored_crc = struct.unpack(">I", payload[offset + 8 + length : end])[0]
        actual_crc = zlib.crc32(kind + data) & 0xFFFFFFFF
        if stored_crc != actual_crc:
            raise PaperExportError(f"Invalid PNG CRC for {kind!r}")
        chunks.append((kind, data))
        offset = end
        if kind == b"IEND":
            break
    if not chunks or chunks[-1][0] != b"IEND" or offset != len(payload):
        raise PaperExportError("Incomplete PNG payload")
    return chunks


def _pack_png_chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def _inspect_png(payload: bytes) -> dict[str, Any]:
    chunks = _parse_png_chunks(payload)
    ihdr = chunks[0][1]
    if len(ihdr) != 13:
        raise PaperExportError("Invalid PNG IHDR")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    chunk_names = [kind.decode("ascii") for kind, _data in chunks]
    physical = next((data for kind, data in chunks if kind == b"pHYs"), None)
    if physical is None or len(physical) != 9:
        ppm_x = ppm_y = unit = None
    else:
        ppm_x, ppm_y, unit = struct.unpack(">IIB", physical)
    return {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
        "compression": compression,
        "filter": filter_method,
        "interlace": interlace,
        "chunks": chunk_names,
        "pixels_per_meter_x": ppm_x,
        "pixels_per_meter_y": ppm_y,
        "physical_unit": unit,
    }


def _verify_png_contract(info: Mapping[str, Any]) -> None:
    if (info["width"], info["height"]) != (OUTPUT_WIDTH, OUTPUT_HEIGHT):
        raise PaperExportError(
            f"PNG dimensions violate the 4K contract: {info['width']}x{info['height']}"
        )
    if info["color_type"] in {4, 6} or "tRNS" in info["chunks"]:
        raise PaperExportError("PNG contains an alpha channel")
    if "sRGB" not in info["chunks"]:
        raise PaperExportError("PNG has no sRGB rendering-intent metadata")
    if (
        info["pixels_per_meter_x"] != PIXELS_PER_METER
        or info["pixels_per_meter_y"] != PIXELS_PER_METER
        or info["physical_unit"] != 1
    ):
        raise PaperExportError("PNG does not contain the required 300 dpi physical metadata")


def _atomic_write(path: Path, payload: bytes) -> None:
    output = QSaveFile(str(path))
    if not output.open(QIODevice.WriteOnly):
        raise PaperExportError(f"Could not open atomic output: {path}: {output.errorString()}")
    try:
        written = output.write(payload)
        if written != len(payload):
            raise PaperExportError(f"Short write for {path}: {written}/{len(payload)} bytes")
        if not output.commit():
            raise PaperExportError(
                f"Could not commit atomic output: {path}: {output.errorString()}"
            )
    except Exception:
        output.cancelWriting()
        raise


def _atomic_write_pair(
    first_path: Path,
    first_payload: bytes,
    second_path: Path,
    second_payload: bytes,
) -> None:
    """Commit two artifacts together and restore the previous pair on error.

    Both payloads are first written with ``QSaveFile`` to transaction-specific
    paths in the destination directory.  Existing targets are then renamed to
    backups before the staged files are installed with ``os.replace``.  A
    failed second replacement restores both original targets, including on
    Windows where an open-file overwrite may be rejected.
    """

    if first_path == second_path:
        raise ValueError("Atomic artifact paths must be distinct")
    if first_path.parent != second_path.parent:
        raise ValueError("Atomic artifact paths must share one directory")

    with _interprocess_artifact_lock(first_path, second_path):
        _atomic_write_pair_locked(first_path, first_payload, second_path, second_payload)


def _atomic_write_pair_locked(
    first_path: Path,
    first_payload: bytes,
    second_path: Path,
    second_payload: bytes,
) -> None:
    token = uuid.uuid4().hex
    parent = first_path.parent
    targets = (first_path, second_path)
    payloads = (first_payload, second_payload)
    staged = tuple(parent / f".paper-{token}-{index}.new" for index in range(2))
    backups = tuple(parent / f".paper-{token}-{index}.bak" for index in range(2))
    backup_created = [False, False]
    installed = [False, False]

    try:
        for stage_path, payload in zip(staged, payloads):
            _atomic_write(stage_path, payload)

        for index, (target, backup) in enumerate(zip(targets, backups)):
            if target.exists():
                os.replace(target, backup)
                backup_created[index] = True

        for index, (stage_path, target) in enumerate(zip(staged, targets)):
            os.replace(stage_path, target)
            installed[index] = True
    except Exception as exc:
        recovery_errors: list[str] = []
        for index in range(len(targets) - 1, -1, -1):
            target = targets[index]
            backup = backups[index]
            try:
                if backup_created[index]:
                    os.replace(backup, target)
                    backup_created[index] = False
                elif installed[index]:
                    target.unlink(missing_ok=True)
            except Exception as recovery_exc:  # pragma: no cover - second filesystem fault
                recovery_errors.append(
                    f"{target}: {type(recovery_exc).__name__}: {recovery_exc}"
                )
        for stage_path in staged:
            try:
                stage_path.unlink(missing_ok=True)
            except OSError as cleanup_exc:  # pragma: no cover - requires a second filesystem fault
                recovery_errors.append(
                    f"{stage_path}: {type(cleanup_exc).__name__}: {cleanup_exc}"
                )

        detail = f"{type(exc).__name__}: {exc}"
        if recovery_errors:
            detail += "; recovery incomplete: " + "; ".join(recovery_errors)
        raise PaperExportError(f"Could not commit paper export artifact pair: {detail}") from exc
    else:
        for backup in backups:
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                # The committed PNG and JSON are already consistent.  A stale
                # backup is safer than reporting a failed export after commit.
                pass
    finally:
        for stage_path in staged:
            try:
                stage_path.unlink(missing_ok=True)
            except OSError:
                pass


@contextmanager
def _interprocess_artifact_lock(
    first_path: Path,
    second_path: Path,
    *,
    timeout_seconds: float = PAPER_EXPORT_LOCK_TIMEOUT_SECONDS,
) -> Iterator[None]:
    """Serialize commits to one artifact pair across application processes."""

    canonical_paths = sorted(
        os.path.normcase(str(path.expanduser().resolve()))
        for path in (first_path, second_path)
    )
    lock_key = hashlib.sha256("\0".join(canonical_paths).encode("utf-8")).hexdigest()
    lock_directory = Path(tempfile.gettempdir()) / "5AxisSclicer_V2.0" / "paper_export_locks"
    try:
        lock_directory.mkdir(parents=True, exist_ok=True)
        lock_stream = (lock_directory / f"{lock_key}.lock").open("a+b")
    except OSError as exc:
        raise PaperExportError(f"Could not open paper-export lock: {exc}") from exc

    acquired = False
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    try:
        lock_stream.seek(0, os.SEEK_END)
        if lock_stream.tell() == 0:
            lock_stream.write(b"\0")
            lock_stream.flush()
        while True:
            try:
                _lock_stream_nonblocking(lock_stream)
                acquired = True
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise PaperExportError(
                        "Timed out waiting for another process to finish the same paper export"
                    ) from exc
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            try:
                _unlock_stream(lock_stream)
            except OSError:
                # Closing the handle releases the operating-system lock.  The
                # committed artifact pair remains valid if explicit unlock fails.
                pass
        lock_stream.close()


def _lock_stream_nonblocking(stream: Any) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_stream(stream: Any) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _normalise_json_value(value: Any, *, path: str = "root") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite number in audit data at {path}")
        return value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _normalise_json_value(asdict(value), path=path)
    to_json = getattr(value, "to_json", None)
    if callable(to_json):
        return _normalise_json_value(to_json(), path=path)
    if isinstance(value, Mapping):
        return {
            str(key): _normalise_json_value(item, path=f"{path}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _normalise_json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        return _normalise_json_value(to_list(), path=path)
    item = getattr(value, "item", None)
    if callable(item):
        return _normalise_json_value(item(), path=path)
    raise TypeError(f"Unsupported audit value at {path}: {type(value).__name__}")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "DEFAULT_DISPLAY_ITEMS",
    "LOGICAL_HEIGHT",
    "LOGICAL_WIDTH",
    "OUTPUT_DPI",
    "OUTPUT_HEIGHT",
    "OUTPUT_SCALE",
    "OUTPUT_WIDTH",
    "PAPER_EXPORT_SCHEMA_VERSION",
    "PIXELS_PER_METER",
    "PaperExportError",
    "PaperExportResult",
    "RenderSnapshot",
    "SourceFileAudit",
    "audit_source_file",
    "collect_viewer_sources",
    "collect_viewer_statistics",
    "export_paper_preview",
]
