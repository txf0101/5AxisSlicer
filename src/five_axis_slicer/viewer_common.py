"""Backend-neutral Viewer contracts and coordinate-safe preview geometry."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from typing import Protocol, runtime_checkable

import numpy as np
from PyQt5.QtGui import QImage

from .gcode_preview import (
    GCodePathSegment,
    GCodePreview,
    GCodeTimelineStep,
    PreviewSettings,
)
from .manufacturing.preview_kinematics import reconstruct_preview_pose
from .models import (
    BuildSurfaceOverlay,
    CadModel,
    CoordinateFrameOverlay,
    PickHit,
    PickRequest,
    SelectionState,
)

SelectionCallback = Callable[[str | None, str | None], None]
PickCallback = Callable[[PickHit], None]
PICK_KINDS = frozenset({"body", "face", "edge", "vertex"})


@runtime_checkable
class ViewerProtocol(Protocol):
    """Stable operations shared by the VTK and OpenGL widgets."""

    backend: str
    model: CadModel | None
    selection: SelectionState
    pick_request: PickRequest
    gcode_preview: GCodePreview | None
    preview_settings: PreviewSettings

    def load_model(self, model: CadModel) -> None: ...

    def clear_model(self) -> None: ...

    def load_gcode_preview(self, preview: GCodePreview) -> None: ...

    def clear_gcode_preview(self) -> None: ...

    def set_pick_request(self, request: PickRequest) -> None: ...

    def set_selection(
        self,
        body_ids: list[str] | None = None,
        edge_ids: list[str] | None = None,
        face_ids: list[str] | None = None,
        vertex_ids: list[str] | None = None,
    ) -> None: ...

    def set_selection_callback(self, callback: SelectionCallback) -> None: ...

    def set_pick_callback(self, callback: PickCallback | None) -> None: ...

    def set_coordinate_frames(
        self,
        frames: Iterable[CoordinateFrameOverlay],
        active_frame_id: str | None = None,
    ) -> None: ...

    def set_build_surface(self, surface: BuildSurfaceOverlay | None) -> None: ...

    def set_model_transform(self, matrix: Iterable[Iterable[float]]) -> None: ...

    def set_quality_mode(self, mode: str) -> None: ...

    def set_standard_view(self, view: str) -> None: ...

    def preview_state(self) -> dict[str, object]: ...

    def performance_state(self) -> dict[str, object]: ...


@runtime_checkable
class SceneCaptureCapability(Protocol):
    """Optional offscreen capture used by thumbnails and render benchmarks."""

    def render_scene_image(self, width: int, height: int) -> QImage: ...

    def capabilities(self) -> Mapping[str, object]: ...


def pick_request_for_mode(mode: str) -> PickRequest:
    if mode not in PICK_KINDS:
        raise ValueError(f"Unsupported picking mode: {mode}")
    return PickRequest(mode, multiple=mode in {"body", "edge"})


def replace_selection(
    selection: SelectionState,
    *,
    body_ids: Iterable[str] | None = None,
    edge_ids: Iterable[str] | None = None,
    face_ids: Iterable[str] | None = None,
    vertex_ids: Iterable[str] | None = None,
) -> None:
    for kind, values in (
        ("body", body_ids),
        ("face", face_ids),
        ("edge", edge_ids),
        ("vertex", vertex_ids),
    ):
        if values is not None:
            setattr(selection, f"{kind}_ids", set(values))


def apply_pick_selection(
    selection: SelectionState,
    request: PickRequest,
    kind: str,
    entity_id: str,
) -> bool:
    """Apply one accepted hit and report whether it matched the active request."""

    if kind != request.kind:
        return False
    if request.allowed_ids is not None and entity_id not in request.allowed_ids:
        return False
    selected: set[str] = getattr(selection, f"{kind}_ids")
    if request.multiple and entity_id in selected:
        selected.remove(entity_id)
    else:
        if not request.multiple:
            selected.clear()
        selected.add(entity_id)
    return True


def preview_settings_for(
    preview: GCodePreview,
    *,
    backend: str,
    quality_mode: str = "interactive",
    solid_rendering: bool | None = None,
) -> PreviewSettings:
    settings = PreviewSettings(
        layer_min=preview.layer_min,
        layer_max=preview.layer_max,
        show_travel=False,
        show_extrusion=True,
        show_pose_samples=False,
        quality_mode=quality_mode,
        render_backend=backend,
    )
    if solid_rendering is not None:
        settings.solid_rendering = solid_rendering
    settings.progress_index = max(
        0,
        preview.timeline_count_for_layers(preview.layer_min, preview.layer_max) - 1,
    )
    return settings


def set_preview_layers(
    preview: GCodePreview,
    settings: PreviewSettings,
    layer_min: int,
    layer_max: int,
) -> None:
    settings.layer_min = max(preview.layer_min, min(layer_min, layer_max))
    settings.layer_max = min(preview.layer_max, max(layer_min, layer_max))
    clamp_progress_index(preview, settings)


def update_preview_visibility(
    settings: PreviewSettings,
    *,
    show_travel: bool | None = None,
    show_extrusion: bool | None = None,
    visible_roles: Iterable[str] | None = None,
    show_pose_samples: bool | None = None,
) -> None:
    if show_travel is not None:
        settings.show_travel = bool(show_travel)
    if show_extrusion is not None:
        settings.show_extrusion = bool(show_extrusion)
    if visible_roles is not None:
        settings.visible_roles = set(visible_roles)
    if show_pose_samples is not None:
        settings.show_pose_samples = bool(show_pose_samples)


def clamp_progress_index(
    preview: GCodePreview | None,
    settings: PreviewSettings,
) -> None:
    if preview is None:
        settings.progress_index = 0
        return
    count = preview.timeline_count_for_layers(settings.layer_min, settings.layer_max)
    settings.progress_index = 0 if count == 0 else max(0, min(settings.progress_index, count - 1))


def progress_state(
    preview: GCodePreview | None,
    settings: PreviewSettings,
) -> dict[str, object]:
    if preview is None:
        return {
            "domain": "layer_filtered_gcode_order",
            "layer_step_count": 0,
            "progress_index": 0,
            "current_global_step": None,
            "current_step": None,
        }
    return preview.progress_state(
        settings.layer_min,
        settings.layer_max,
        settings.progress_index,
    )


def current_progress_step(
    preview: GCodePreview | None,
    settings: PreviewSettings,
) -> GCodeTimelineStep | None:
    if preview is None:
        return None
    return preview.timeline_step_for_layer_progress(
        settings.layer_min,
        settings.layer_max,
        settings.progress_index,
    )


def segment_visible(segment: GCodePathSegment, settings: PreviewSettings) -> bool:
    if not settings.layer_min <= segment.layer <= settings.layer_max:
        return False
    if segment.move_type == "extrude":
        return settings.show_extrusion and segment.extrusion_role in settings.visible_roles
    if segment.move_type == "travel":
        return settings.show_travel
    return settings.show_travel and segment.has_spatial_length


def representative_path_segment(
    preview: GCodePreview | None,
    settings: PreviewSettings,
) -> GCodePathSegment | None:
    if preview is None:
        return None
    current = current_progress_step(preview, settings)
    if current is not None:
        index = current.path_segment_index
        if index is None:
            index = preview.segment_index_for_step(current.step_index)
        if index is None:
            index = preview.nearest_segment_index_for_step(current.step_index)
        if index is not None and 0 <= index < len(preview.segments):
            return preview.segments[index]
    visible = [segment for segment in preview.segments if segment_visible(segment, settings)]
    spatial = [segment for segment in visible if segment.has_spatial_length]
    return next(
        (segment for segment in spatial if segment.move_type == "extrude"),
        spatial[0] if spatial else (visible[0] if visible else None),
    )


def preview_state_payload(
    preview: GCodePreview | None,
    settings: PreviewSettings,
    *,
    backend: str,
    visible_count: int,
    drawn_count: int,
    render_mode: str,
    frame_ms: float,
    gpu_draw_count: int,
    result_visibility: Mapping[str, bool] | None = None,
) -> dict[str, object]:
    summary = None if preview is None else preview.summary()
    state: dict[str, object] = {
        "summary": summary,
        "settings": settings.to_json(),
        "visible_path_segment_count": visible_count,
        "drawn_path_segment_count": drawn_count,
        "render_mode": render_mode,
        "progress": progress_state(preview, settings),
        "backend": backend,
        "quality_mode": settings.quality_mode,
        "frame_ms": frame_ms,
        "gpu_draw_count": gpu_draw_count,
        "cache_format": None if summary is None else summary.get("cache_format"),
    }
    if result_visibility is not None:
        state["result_visibility"] = dict(result_visibility)
    return state


def nozzle_axis_from_rotary(
    rotary: Mapping[str, float],
    *,
    controller_semantics: str | None = None,
    coordinate_transform: str | None = None,
) -> tuple[float, float, float]:
    """Return the fixed machine-head axis in the segment preview space."""

    reconstruction = reconstruct_preview_pose(
        (0.0, 0.0, 0.0),
        rotary,
        controller_semantics=controller_semantics,
    )
    if (
        coordinate_transform is not None
        and reconstruction.coordinate_transform != coordinate_transform
    ):
        return (0.0, 0.0, -1.0)
    return reconstruction.nozzle_axis


def preview_pose_for_segment(
    segment: GCodePathSegment,
    *,
    controller_semantics: str | None = None,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return the endpoint and nozzle axis in one registered coordinate space."""

    if segment.machine_end is None:
        return segment.end, nozzle_axis_from_rotary(
            segment.rotary_end,
            controller_semantics=controller_semantics,
            coordinate_transform=segment.coordinate_transform,
        )
    reconstruction = reconstruct_preview_pose(
        segment.machine_end,
        segment.rotary_end,
        controller_semantics=controller_semantics,
    )
    if reconstruction.coordinate_transform != segment.coordinate_transform:
        return segment.end, (0.0, 0.0, -1.0)
    return reconstruction.point, reconstruction.nozzle_axis


def bead_frame(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    rotary: Mapping[str, float],
    *,
    controller_semantics: str | None = None,
    coordinate_transform: str | None = None,
) -> (
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    | None
):
    tangent = normalize3((end[0] - start[0], end[1] - start[1], end[2] - start[2]))
    if tangent is None:
        return None
    nozzle = normalize3(
        nozzle_axis_from_rotary(
            rotary,
            controller_semantics=controller_semantics,
            coordinate_transform=coordinate_transform,
        )
    ) or (0.0, 0.0, -1.0)
    width_axis = normalize3(cross3(nozzle, tangent))
    for helper in ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)):
        if width_axis is None:
            width_axis = normalize3(cross3(helper, tangent))
    if width_axis is None:
        return None
    height_axis = normalize3(cross3(tangent, width_axis))
    if height_axis is None:
        return None
    if dot3(height_axis, nozzle) < 0:
        height_axis = (-height_axis[0], -height_axis[1], -height_axis[2])
    return tangent, width_axis, height_axis


def normalize3(
    vector: tuple[float, float, float],
) -> tuple[float, float, float] | None:
    length = math.sqrt(sum(value * value for value in vector))
    if length <= 1e-12:
        return None
    return vector[0] / length, vector[1] / length, vector[2] / length


def vector3(values: Iterable[float]) -> tuple[float, float, float]:
    """Materialize a coordinate only after its three-component shape is known."""

    result = tuple(float(value) for value in values)
    if len(result) != 3:
        raise ValueError("expected a three-component vector")
    return result[0], result[1], result[2]


def cross3(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def dot3(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return sum(left[index] * right[index] for index in range(3))


def render_stride(count: int, limit: int) -> int:
    return 1 if count <= 0 or limit <= 0 else max(1, math.ceil(count / limit))


def is_rigid_transform(values: np.ndarray, tolerance: float = 1e-7) -> bool:
    if values.shape != (4, 4) or not np.isfinite(values).all():
        return False
    if not np.allclose(values[3], (0.0, 0.0, 0.0, 1.0), atol=tolerance, rtol=0.0):
        return False
    rotation = values[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=tolerance, rtol=0.0):
        return False
    return bool(abs(np.linalg.det(rotation) - 1.0) <= tolerance)


def validated_rigid_transform(matrix: Iterable[Iterable[float]]) -> np.ndarray:
    values = np.asarray(tuple(tuple(row) for row in matrix), dtype=np.float64)
    if values.shape != (4, 4) or not np.isfinite(values).all():
        raise ValueError("model transform must be a finite 4x4 matrix")
    if not np.allclose(values[3], (0.0, 0.0, 0.0, 1.0), atol=1e-7, rtol=0.0):
        raise ValueError("model transform must use homogeneous rigid coordinates")
    rotation = values[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6, rtol=0.0):
        raise ValueError("model transform rotation must be orthonormal")
    if not math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-6):
        raise ValueError("model transform must preserve right-handed orientation")
    return values
