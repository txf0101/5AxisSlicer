from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:  # pragma: no cover - availability depends on the local C++ toolchain.
    import five_axis_slicer_native as _native

    NATIVE_INDEX_AVAILABLE = True
except Exception:  # pragma: no cover - Python fallback is covered by unit tests.
    _native = None
    NATIVE_INDEX_AVAILABLE = False


@dataclass(frozen=True, slots=True)
class PackedPreviewIndex:
    layer_prefix_counts: np.ndarray
    timeline_indices: np.ndarray
    segment_step_indices: np.ndarray
    segment_indices: np.ndarray
    source: str


def build_preview_index(
    timeline_layers: list[int],
    segment_step_indices: list[int],
    layer_min: int,
    layer_max: int,
) -> PackedPreviewIndex:
    """Pack layer and segment lookup arrays for slider navigation."""

    timeline_array = np.asarray(timeline_layers, dtype=np.int32)
    segment_steps = np.asarray(segment_step_indices, dtype=np.int32)
    if NATIVE_INDEX_AVAILABLE and _native is not None:
        packed = _native.build_preview_index(timeline_array, segment_steps, int(layer_min), int(layer_max))
        return PackedPreviewIndex(
            layer_prefix_counts=np.asarray(packed["layer_prefix_counts"], dtype=np.int32),
            timeline_indices=np.asarray(packed["timeline_indices"], dtype=np.int32),
            segment_step_indices=np.asarray(packed["segment_step_indices"], dtype=np.int32),
            segment_indices=np.asarray(packed["segment_indices"], dtype=np.int32),
            source="native",
        )
    return _build_preview_index_python(timeline_array, segment_steps, int(layer_min), int(layer_max))


def _build_preview_index_python(
    timeline_layers: np.ndarray,
    segment_step_indices: np.ndarray,
    layer_min: int,
    layer_max: int,
) -> PackedPreviewIndex:
    if layer_max < layer_min:
        return PackedPreviewIndex(
            layer_prefix_counts=np.asarray([0], dtype=np.int32),
            timeline_indices=np.empty((0,), dtype=np.int32),
            segment_step_indices=segment_step_indices,
            segment_indices=np.arange(segment_step_indices.size, dtype=np.int32),
            source="python",
        )

    layer_count = layer_max - layer_min + 1
    counts = np.zeros(layer_count, dtype=np.int32)
    valid_layers = (timeline_layers >= layer_min) & (timeline_layers <= layer_max)
    for layer in timeline_layers[valid_layers]:
        counts[int(layer) - layer_min] += 1

    prefix = np.empty(layer_count + 1, dtype=np.int32)
    prefix[0] = 0
    np.cumsum(counts, out=prefix[1:])

    cursor = prefix[:-1].copy()
    timeline_indices = np.empty(int(prefix[-1]), dtype=np.int32)
    for index, layer in enumerate(timeline_layers):
        if layer < layer_min or layer > layer_max:
            continue
        offset = int(layer) - layer_min
        write_at = int(cursor[offset])
        timeline_indices[write_at] = index
        cursor[offset] += 1

    return PackedPreviewIndex(
        layer_prefix_counts=prefix,
        timeline_indices=timeline_indices,
        segment_step_indices=segment_step_indices,
        segment_indices=np.arange(segment_step_indices.size, dtype=np.int32),
        source="python",
    )
