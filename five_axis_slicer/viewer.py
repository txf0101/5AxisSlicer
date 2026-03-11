from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection

PATH_STYLE_MAP = {
    "planar-perimeter": {"color": "#c0392b", "width": 1.5},
    "planar-infill": {"color": "#f39c12", "width": 0.9},
    "conformal-perimeter": {"color": "#146356", "width": 1.6},
    "conformal-infill": {"color": "#1f77b4", "width": 1.0},
}


class PreviewCanvas(FigureCanvasQTAgg):
    """Fast-ish matplotlib preview for mesh + toolpaths.

    Matplotlib is not a full 3D engine, so interaction can get slow on dense
    meshes. To improve the experience we switch to a lighter preview while the
    user is dragging the mouse, then restore the full filtered scene after the
    mouse button is released.
    """

    def __init__(self) -> None:
        self.figure = Figure(figsize=(8, 6), tight_layout=True)
        super().__init__(self.figure)
        self.axes = self.figure.add_subplot(111, projection="3d")

        self._vertices = np.empty((0, 3), dtype=float)
        self._faces = np.empty((0, 3), dtype=np.int32)
        self._segments_by_kind: dict[str, np.ndarray] = {}
        self._show_mesh = True
        self._visible_kinds: set[str] = set(PATH_STYLE_MAP)
        self._interaction_active = False
        self._view_initialized = False
        self._bounds_min: np.ndarray | None = None
        self._bounds_max: np.ndarray | None = None
        self._mesh_triangles_full = np.empty((0, 3, 3), dtype=float)
        self._mesh_triangles_interactive = np.empty((0, 3, 3), dtype=float)
        self._mesh_edges_full = np.empty((0, 2, 3), dtype=float)
        self._mesh_edges_interactive = np.empty((0, 2, 3), dtype=float)

        self.mpl_connect("button_press_event", self._on_mouse_press)
        self.mpl_connect("button_release_event", self._on_mouse_release)

        self._reset_axes()

    def clear(self) -> None:
        self._vertices = np.empty((0, 3), dtype=float)
        self._faces = np.empty((0, 3), dtype=np.int32)
        self._segments_by_kind = {}
        self._bounds_min = None
        self._bounds_max = None
        self._mesh_triangles_full = np.empty((0, 3, 3), dtype=float)
        self._mesh_triangles_interactive = np.empty((0, 3, 3), dtype=float)
        self._mesh_edges_full = np.empty((0, 2, 3), dtype=float)
        self._mesh_edges_interactive = np.empty((0, 2, 3), dtype=float)
        self._interaction_active = False
        self._view_initialized = False
        self._reset_axes()
        self.draw_idle()

    def plot_mesh(self, vertices: np.ndarray, faces: np.ndarray) -> None:
        self._set_scene(vertices, faces, [])

    def plot_toolpaths(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        toolpaths: list[tuple[np.ndarray, str]],
    ) -> None:
        self._set_scene(vertices, faces, toolpaths)

    def set_visibility(self, show_mesh: bool | None = None, visible_kinds: set[str] | None = None) -> None:
        if show_mesh is not None:
            self._show_mesh = bool(show_mesh)
        if visible_kinds is not None:
            self._visible_kinds = set(visible_kinds)
        self._render_scene(interactive=self._interaction_active)

    def _set_scene(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        toolpaths: list[tuple[np.ndarray, str]],
    ) -> None:
        self._vertices = np.asarray(vertices, dtype=float)
        self._faces = np.asarray(faces, dtype=np.int32)
        if len(self._vertices) > 0:
            self._bounds_min = self._vertices.min(axis=0)
            self._bounds_max = self._vertices.max(axis=0)
        else:
            self._bounds_min = None
            self._bounds_max = None
        self._mesh_triangles_full = self._sample_mesh_triangles(max_faces=7000)
        self._mesh_triangles_interactive = self._sample_mesh_triangles(max_faces=1400)
        self._mesh_edges_full = self._triangles_to_edges(self._mesh_triangles_full)
        self._mesh_edges_interactive = self._triangles_to_edges(self._mesh_triangles_interactive)
        self._segments_by_kind = self._build_segment_cache(toolpaths)
        self._interaction_active = False
        self._view_initialized = False
        self._render_scene(interactive=False)

    def _sample_mesh_triangles(self, max_faces: int) -> np.ndarray:
        if len(self._faces) == 0 or len(self._vertices) == 0:
            return np.empty((0, 3, 3), dtype=float)
        stride = max(1, int(np.ceil(len(self._faces) / max(max_faces, 1))))
        sampled_faces = self._faces[::stride]
        return np.asarray(self._vertices[sampled_faces], dtype=float)

    def _triangles_to_edges(self, triangles: np.ndarray) -> np.ndarray:
        if len(triangles) == 0:
            return np.empty((0, 2, 3), dtype=float)
        return np.concatenate([
            triangles[:, [0, 1], :],
            triangles[:, [1, 2], :],
            triangles[:, [2, 0], :],
        ], axis=0)

    def _build_segment_cache(self, toolpaths: list[tuple[np.ndarray, str]]) -> dict[str, np.ndarray]:
        grouped: dict[str, list[np.ndarray]] = {kind: [] for kind in PATH_STYLE_MAP}
        for points, kind in toolpaths:
            pts = np.asarray(points, dtype=float)
            if len(pts) < 2:
                continue
            segments = np.stack([pts[:-1], pts[1:]], axis=1)
            grouped.setdefault(kind, []).append(segments)

        cache: dict[str, np.ndarray] = {}
        for kind, segments_list in grouped.items():
            if segments_list:
                cache[kind] = np.concatenate(segments_list, axis=0)
            else:
                cache[kind] = np.empty((0, 2, 3), dtype=float)
        return cache

    def _on_mouse_press(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.inaxes != self.axes:
            return
        if self._interaction_active:
            return
        if len(self._mesh_triangles_full) == 0 and not any(len(segments) for segments in self._segments_by_kind.values()):
            return
        self._interaction_active = True
        self._render_scene(interactive=True)

    def _on_mouse_release(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self._interaction_active:
            return
        self._interaction_active = False
        self._render_scene(interactive=False)

    def _render_scene(self, interactive: bool) -> None:
        view_state = self._capture_view_state()
        self._reset_axes()

        if self._show_mesh:
            triangles = self._mesh_triangles_interactive if interactive else self._mesh_triangles_full
            edges = self._mesh_edges_interactive if interactive else self._mesh_edges_full
            if len(triangles) > 0:
                mesh = Poly3DCollection(
                    triangles,
                    facecolors="#7fa6bf",
                    edgecolors="none",
                    linewidths=0.0,
                    alpha=0.34 if not interactive else 0.16,
                )
                self.axes.add_collection3d(mesh)
            if len(edges) > 0:
                wireframe = Line3DCollection(
                    edges,
                    colors="#5f7382" if not interactive else "#748896",
                    linewidths=0.40 if not interactive else 0.22,
                    alpha=0.58 if not interactive else 0.34,
                )
                self.axes.add_collection3d(wireframe)

        if not interactive:
            for kind, style in PATH_STYLE_MAP.items():
                if kind not in self._visible_kinds:
                    continue
                segments = self._segments_by_kind.get(kind)
                if segments is None or len(segments) == 0:
                    continue
                collection = Line3DCollection(
                    segments,
                    colors=style["color"],
                    linewidths=style["width"],
                    alpha=0.96,
                )
                self.axes.add_collection3d(collection)

        if view_state is None:
            self._autoscale()
        else:
            self._restore_view_state(view_state)
        self.draw_idle()

    def _reset_axes(self) -> None:
        self.axes.clear()
        self.axes.set_facecolor("#fbfbfd")
        self.axes.set_xlabel("X (mm)", color="#4f4f55")
        self.axes.set_ylabel("Y (mm)", color="#4f4f55")
        self.axes.set_zlabel("Z (mm)", color="#4f4f55")
        self.axes.tick_params(colors="#6e6e73")
        self.axes.grid(True, color="#d2d2d7", alpha=0.55)
        for axis in (self.axes.xaxis, self.axes.yaxis, self.axes.zaxis):
            try:
                axis.set_pane_color((0.984, 0.984, 0.992, 1.0))
                axis.line.set_color("#b8b8be")
            except Exception:
                pass
        self.axes.set_box_aspect((1, 1, 1))

    def _capture_view_state(self) -> dict[str, object] | None:
        if self._bounds_min is None or self._bounds_max is None or not self._view_initialized:
            return None
        return {
            "xlim": self.axes.get_xlim3d(),
            "ylim": self.axes.get_ylim3d(),
            "zlim": self.axes.get_zlim3d(),
            "elev": float(self.axes.elev),
            "azim": float(self.axes.azim),
        }

    def _restore_view_state(self, view_state: dict[str, object]) -> None:
        self.axes.set_xlim(view_state["xlim"])
        self.axes.set_ylim(view_state["ylim"])
        self.axes.set_zlim(view_state["zlim"])
        self._apply_box_aspect()
        self.axes.view_init(elev=float(view_state["elev"]), azim=float(view_state["azim"]))
        self._view_initialized = True

    def _apply_box_aspect(self) -> None:
        if self._bounds_min is None or self._bounds_max is None:
            self.axes.set_box_aspect((1, 1, 1))
            return
        spans = np.maximum(self._bounds_max - self._bounds_min, 1.0)
        self.axes.set_box_aspect(tuple(float(value) for value in spans))

    def _autoscale(self) -> None:
        if self._bounds_min is None or self._bounds_max is None:
            return
        spans = np.maximum(self._bounds_max - self._bounds_min, 1.0)
        padding = np.maximum(spans * 0.08, 1.0)
        lower = self._bounds_min - padding
        upper = self._bounds_max + padding
        self.axes.set_xlim(float(lower[0]), float(upper[0]))
        self.axes.set_ylim(float(lower[1]), float(upper[1]))
        self.axes.set_zlim(float(lower[2]), float(upper[2]))
        self._apply_box_aspect()
        self._view_initialized = True



