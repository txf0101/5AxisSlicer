from __future__ import annotations

import ctypes.util
import importlib.util
import math
import os
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from .core import MeshModel

_GMSH_DLL_HANDLES: list[object] = []
_GMSH_DLL_DIRS: set[str] = set()


def _conda_package_cache_dirs(dll_names: tuple[str, ...]) -> list[Path]:
    if not sys.platform.startswith("win"):
        return []

    roots: list[Path] = []
    seen_roots: set[str] = set()

    def add_root(path: Path | None) -> None:
        if path is None:
            return
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = os.path.normcase(str(resolved))
        if key in seen_roots or not resolved.exists():
            return
        seen_roots.add(key)
        roots.append(resolved)

    prefix = Path(sys.prefix).resolve()
    prefix_parent = prefix.parent
    if prefix_parent.name.lower() == "envs":
        add_root(prefix_parent.parent / "pkgs")

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        conda_prefix_path = Path(conda_prefix).resolve()
        conda_parent = conda_prefix_path.parent
        if conda_parent.name.lower() == "envs":
            add_root(conda_parent.parent / "pkgs")

    add_root(Path.home() / ".conda" / "pkgs")

    package_dirs: list[Path] = []
    seen_dirs: set[str] = set()
    for root in roots:
        for dll_name in dll_names:
            for match in sorted(root.glob(f"*/Library/bin/{dll_name}"), reverse=True):
                directory = match.parent
                key = os.path.normcase(str(directory))
                if key in seen_dirs:
                    continue
                seen_dirs.add(key)
                package_dirs.append(directory)
    return package_dirs


def _gmsh_runtime_dirs() -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path | None) -> None:
        if path is None:
            return
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = os.path.normcase(str(resolved))
        if key in seen or not resolved.exists():
            return
        seen.add(key)
        roots.append(resolved)

    module_dir = Path(__file__).resolve().parent
    executable_dir = Path(sys.executable).resolve().parent
    prefix_dir = Path(sys.prefix)
    bundle_dir = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", None) else None

    gmsh_spec = importlib.util.find_spec("gmsh")
    gmsh_module_dir = None
    if gmsh_spec and gmsh_spec.origin:
        gmsh_module_dir = Path(gmsh_spec.origin).resolve().parent

    candidate_roots = [
        bundle_dir,
        executable_dir,
        prefix_dir,
        module_dir,
        module_dir.parent,
        gmsh_module_dir,
        gmsh_module_dir.parent if gmsh_module_dir else None,
        gmsh_module_dir.parents[1] if gmsh_module_dir and len(gmsh_module_dir.parents) > 1 else None,
    ]
    subdirs = [
        None,
        Path("Lib"),
        Path("lib"),
        Path("DLLs"),
        Path("bin"),
        Path("Scripts"),
        Path("Library") / "bin",
        Path("Library") / "mingw-w64" / "bin",
    ]

    for root in candidate_roots:
        if root is None:
            continue
        for subdir in subdirs:
            add(root if subdir is None else root / subdir)

    # Some conda-forge Windows gmsh builds still depend on cairo.dll even when
    # newer cairo packages expose cairo-2.dll inside the active env. Fall back
    # to compatible DLLs in the local conda package cache so STEP import keeps
    # working without requiring a manual environment repair first.
    for package_dir in _conda_package_cache_dirs(("cairo.dll",)):
        add(package_dir)

    return roots



def _prepend_search_paths(env_var: str, directories: list[Path]) -> None:
    existing = [entry for entry in os.environ.get(env_var, "").split(os.pathsep) if entry]
    seen = {os.path.normcase(entry) for entry in existing}
    additions: list[str] = []
    for directory in directories:
        directory_str = str(directory)
        key = os.path.normcase(directory_str)
        if key in seen:
            continue
        additions.append(directory_str)
        seen.add(key)
    if additions:
        os.environ[env_var] = os.pathsep.join(additions + existing)



def _find_gmsh_library(directories: list[Path]) -> str | None:
    if sys.platform.startswith("win"):
        patterns = ("gmsh-*.dll", "gmsh.dll")
    elif sys.platform == "darwin":
        patterns = ("libgmsh*.dylib",)
    else:
        patterns = ("libgmsh*.so*",)

    for directory in directories:
        for pattern in patterns:
            matches = sorted(directory.glob(pattern))
            if matches:
                return str(matches[0])
    return None



def load_mesh(path: str | Path) -> MeshModel:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".stl":
        return load_stl(path)
    if suffix in {".step", ".stp"}:
        return load_step(path)
    raise ValueError(f"Unsupported file format: {path.suffix}")



def load_stl(path: str | Path) -> MeshModel:
    path = Path(path)
    data = path.read_bytes()
    if _is_binary_stl(data):
        triangles = _read_binary_stl(data)
    else:
        triangles = _read_ascii_stl(data)
    return _mesh_from_triangles(path.stem, triangles, str(path))



def load_step(path: str | Path) -> MeshModel:
    path = Path(path)

    try:
        gmsh = _import_gmsh()
    except Exception as exc:
        gmsh = None
        gmsh_error = exc
    else:
        gmsh_error = None

    if gmsh is None:
        raise RuntimeError(
            "STEP import is wired through gmsh, but gmsh is not usable in the current 5AxisSlicer environment. "
            "Use the STL version of the model for now, or repair the gmsh runtime first. "
            f"Original error: {gmsh_error}"
        )

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add(path.stem)
        gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        gmsh.model.mesh.generate(2)

        node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
        node_xyz = np.asarray(node_coords, dtype=float).reshape(-1, 3)
        node_map = {int(tag): idx for idx, tag in enumerate(node_tags)}

        tri_vertices: list[np.ndarray] = []
        for entity_dim, entity_tag in gmsh.model.getEntities(2):
            elem_types, _, elem_nodes = gmsh.model.mesh.getElements(entity_dim, entity_tag)
            for elem_type, nodes in zip(elem_types, elem_nodes):
                element_name, dim, _, node_count, _, _ = gmsh.model.mesh.getElementProperties(elem_type)
                if dim != 2 or "triangle" not in element_name.lower():
                    continue
                reshaped = np.asarray(nodes, dtype=int).reshape(-1, node_count)[:, :3]
                for tri in reshaped:
                    tri_vertices.append(node_xyz[[node_map[int(tag)] for tag in tri]])

        if not tri_vertices:
            raise ValueError("STEP meshing backend returned no triangles.")
        return _mesh_from_triangles(path.stem, np.asarray(tri_vertices), str(path))
    finally:
        gmsh.finalize()



def generate_demo_dome_mesh(radius_mm: float = 25.0, height_mm: float = 15.0, resolution: int = 48) -> MeshModel:
    theta = np.linspace(0.0, 2.0 * math.pi, resolution, endpoint=False)
    radial = np.linspace(0.0, radius_mm, resolution // 2 + 1)
    rr, tt = np.meshgrid(radial, theta, indexing="xy")

    x = rr * np.cos(tt)
    y = rr * np.sin(tt)
    normalized = np.clip(rr / max(radius_mm, 1e-6), 0.0, 1.0)
    z = height_mm * np.cos(normalized * math.pi * 0.5) ** 2

    top_vertices = np.column_stack([x.ravel(), y.ravel(), z.ravel()])
    center_bottom = np.array([[0.0, 0.0, 0.0]])
    ring = np.column_stack([radius_mm * np.cos(theta), radius_mm * np.sin(theta), np.zeros_like(theta)])
    vertices = np.vstack([top_vertices, center_bottom, ring])

    faces: list[list[int]] = []
    radial_count = len(radial)
    theta_count = len(theta)

    for ti in range(theta_count):
        next_t = (ti + 1) % theta_count
        for ri in range(radial_count - 1):
            a = ti * radial_count + ri
            b = ti * radial_count + ri + 1
            c = next_t * radial_count + ri
            d = next_t * radial_count + ri + 1
            if ri == 0:
                faces.append([a, b, d])
            else:
                faces.append([a, b, d])
                faces.append([a, d, c])

    bottom_center_idx = len(top_vertices)
    ring_offset = bottom_center_idx + 1
    for ti in range(theta_count):
        next_t = (ti + 1) % theta_count
        faces.append([bottom_center_idx, ring_offset + next_t, ring_offset + ti])

    return _mesh_from_vertices_faces("Demo Dome", vertices, np.asarray(faces, dtype=np.int32), None)



def resample_polyline(points: np.ndarray, spacing_mm: float, closed: bool = False) -> np.ndarray:
    points = np.asarray(points, dtype=float)
    if len(points) < 2:
        return points.copy()

    if closed and np.linalg.norm(points[0] - points[-1]) > 1e-6:
        points = np.vstack([points, points[0]])

    diffs = np.diff(points, axis=0)
    seg_lengths = np.linalg.norm(diffs, axis=1)
    total = float(seg_lengths.sum())
    if total <= spacing_mm:
        return points

    cumulative = np.concatenate([[0.0], np.cumsum(seg_lengths)])
    samples = np.arange(0.0, total, max(spacing_mm, 1e-6))
    if len(samples) == 0 or not math.isclose(samples[-1], total, rel_tol=1e-6, abs_tol=1e-6):
        samples = np.append(samples, total)

    result = []
    seg_idx = 0
    for target in samples:
        while seg_idx < len(seg_lengths) - 1 and cumulative[seg_idx + 1] < target:
            seg_idx += 1
        seg_start = cumulative[seg_idx]
        seg_end = cumulative[seg_idx + 1]
        ratio = 0.0 if math.isclose(seg_end, seg_start) else (target - seg_start) / (seg_end - seg_start)
        result.append(points[seg_idx] * (1.0 - ratio) + points[seg_idx + 1] * ratio)

    result_array = np.asarray(result, dtype=float)
    if closed and np.linalg.norm(result_array[0] - result_array[-1]) > 1e-6:
        result_array = np.vstack([result_array, result_array[0]])
    return result_array


def face_adjacency(mesh: MeshModel) -> list[set[int]]:
    """Return edge-based neighbouring faces for every triangle in the mesh."""

    if len(mesh.faces) == 0:
        return []

    edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(mesh.faces):
        a_idx, b_idx, c_idx = map(int, face)
        for start_idx, end_idx in ((a_idx, b_idx), (b_idx, c_idx), (c_idx, a_idx)):
            if start_idx > end_idx:
                start_idx, end_idx = end_idx, start_idx
            edge_to_faces[(start_idx, end_idx)].append(face_index)

    adjacency = [set() for _ in range(len(mesh.faces))]
    for attached_faces in edge_to_faces.values():
        if len(attached_faces) < 2:
            continue
        for face_index in attached_faces:
            adjacency[face_index].update(other_face for other_face in attached_faces if other_face != face_index)
    return adjacency


def face_centers(mesh: MeshModel) -> np.ndarray:
    if len(mesh.faces) == 0:
        return np.empty((0, 3), dtype=float)
    return mesh.face_vertices.mean(axis=1)


def selection_boundary_edges(mesh: MeshModel, face_indices: np.ndarray | list[int] | set[int]) -> list[tuple[int, int]]:
    """Return mesh edges that sit on the boundary of the selected face set."""

    selected = {int(index) for index in np.asarray(tuple(face_indices), dtype=np.int32).tolist()}
    if not selected:
        return []

    edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_index, face in enumerate(mesh.faces):
        a_idx, b_idx, c_idx = map(int, face)
        for start_idx, end_idx in ((a_idx, b_idx), (b_idx, c_idx), (c_idx, a_idx)):
            if start_idx > end_idx:
                start_idx, end_idx = end_idx, start_idx
            edge_to_faces[(start_idx, end_idx)].append(face_index)

    boundary_edges: list[tuple[int, int]] = []
    for edge, attached_faces in edge_to_faces.items():
        selected_count = sum(1 for face_index in attached_faces if face_index in selected)
        if selected_count == 1:
            boundary_edges.append(edge)
    return boundary_edges


def grow_face_selection(
    mesh: MeshModel,
    face_indices: np.ndarray | list[int] | set[int],
    center_xy: np.ndarray,
    *,
    max_layers: int = 2,
    max_added_faces: int = 48,
    normal_dot_threshold: float = 0.35,
) -> tuple[np.ndarray, np.ndarray]:
    """Expand a face selection conservatively across nearby, similarly oriented faces.

    This is intentionally conservative: it only grows into adjacent faces whose
    normals and radial location remain close to the already selected region.
    The GUI uses this as a "small gap closing" helper rather than a full repair
    algorithm for arbitrary meshes.
    """

    selected = {int(index) for index in np.asarray(tuple(face_indices), dtype=np.int32).tolist()}
    if not selected or len(mesh.faces) == 0:
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)

    adjacency = face_adjacency(mesh)
    centers = face_centers(mesh)
    normals = np.asarray(mesh.face_normals, dtype=float)
    center_xy = np.asarray(center_xy, dtype=float)

    selected_array = np.asarray(sorted(selected), dtype=np.int32)
    selected_centers = centers[selected_array]
    radial_distances = np.linalg.norm(selected_centers[:, :2] - center_xy[None, :], axis=1)
    z_values = selected_centers[:, 2]

    radial_span = float(np.ptp(radial_distances)) if len(radial_distances) > 1 else 0.0
    z_span = float(np.ptp(z_values)) if len(z_values) > 1 else 0.0
    radial_low = float(np.percentile(radial_distances, 5.0)) - max(radial_span * 0.18, 2.0)
    radial_high = float(np.percentile(radial_distances, 95.0)) + max(radial_span * 0.18, 2.0)
    z_low = float(np.min(z_values)) - max(z_span * 0.12, 2.0)
    z_high = float(np.max(z_values)) + max(z_span * 0.12, 2.0)

    frontier = set(selected)
    added_faces: list[int] = []
    for _ in range(max(max_layers, 0)):
        candidates: set[int] = set()
        for face_index in frontier:
            candidates.update(adjacency[face_index])
        candidates.difference_update(selected)
        if not candidates:
            break

        accepted: list[int] = []
        for candidate in sorted(candidates):
            candidate_center = centers[candidate]
            radial_value = float(np.linalg.norm(candidate_center[:2] - center_xy))
            if radial_value < radial_low or radial_value > radial_high:
                continue
            if candidate_center[2] < z_low or candidate_center[2] > z_high:
                continue

            attached_selected = [neighbor for neighbor in adjacency[candidate] if neighbor in selected]
            if not attached_selected:
                continue
            best_dot = max(float(np.dot(normals[candidate], normals[neighbor])) for neighbor in attached_selected)
            if best_dot < normal_dot_threshold:
                continue
            accepted.append(candidate)

        if not accepted:
            break

        selected.update(accepted)
        frontier = set(accepted)
        added_faces.extend(accepted)
        if len(added_faces) >= max_added_faces:
            break

    return np.asarray(sorted(selected), dtype=np.int32), np.asarray(sorted(added_faces), dtype=np.int32)


def split_mesh_into_components(mesh: MeshModel) -> list[MeshModel]:
    """Split a mesh into face-connected sub-meshes."""

    if len(mesh.faces) == 0:
        return []

    adjacency = face_adjacency(mesh)
    components: list[MeshModel] = []
    visited = np.zeros(len(mesh.faces), dtype=bool)
    for face_index in range(len(mesh.faces)):
        if visited[face_index]:
            continue
        stack = [face_index]
        visited[face_index] = True
        component_faces: list[int] = []
        while stack:
            current_face = stack.pop()
            component_faces.append(current_face)
            for next_face in adjacency[current_face]:
                if visited[next_face]:
                    continue
                visited[next_face] = True
                stack.append(next_face)
        components.append(extract_submesh(mesh, np.asarray(component_faces, dtype=np.int32), name=f"{mesh.name} [Component {len(components)}]"))
    return components


def extract_submesh(mesh: MeshModel, face_indices: np.ndarray, name: str | None = None) -> MeshModel:
    face_indices = np.asarray(face_indices, dtype=np.int32)
    selected_faces = mesh.faces[face_indices]
    unique_vertices, inverse = np.unique(selected_faces.reshape(-1), return_inverse=True)
    vertices = mesh.vertices[unique_vertices]
    faces = inverse.reshape(-1, 3).astype(np.int32)
    return _mesh_from_vertices_faces(name or mesh.name, vertices, faces, mesh.source_path)


def combine_meshes(meshes: list[MeshModel], name: str | None = None) -> MeshModel:
    if not meshes:
        raise ValueError("Cannot combine an empty mesh list.")
    if len(meshes) == 1:
        mesh = meshes[0]
        return MeshModel(
            name=name or mesh.name,
            vertices=mesh.vertices.copy(),
            faces=mesh.faces.copy(),
            face_normals=mesh.face_normals.copy(),
            vertex_normals=mesh.vertex_normals.copy(),
            source_path=mesh.source_path,
        )

    vertices_list: list[np.ndarray] = []
    faces_list: list[np.ndarray] = []
    vertex_offset = 0
    for mesh in meshes:
        vertices_list.append(mesh.vertices)
        faces_list.append(mesh.faces + vertex_offset)
        vertex_offset += len(mesh.vertices)
    vertices = np.vstack(vertices_list)
    faces = np.vstack(faces_list)
    source_path = meshes[0].source_path if all(mesh.source_path == meshes[0].source_path for mesh in meshes) else None
    return _mesh_from_vertices_faces(name or meshes[0].name, vertices, faces, source_path)



def _import_gmsh():
    runtime_dirs = _gmsh_runtime_dirs()
    _prepend_search_paths("PATH", runtime_dirs)
    if sys.platform == "darwin":
        _prepend_search_paths("DYLD_LIBRARY_PATH", runtime_dirs)
    elif not sys.platform.startswith("win"):
        _prepend_search_paths("LD_LIBRARY_PATH", runtime_dirs)

    if sys.platform.startswith("win") and hasattr(os, "add_dll_directory"):
        for dll_dir in runtime_dirs:
            dll_dir_str = str(dll_dir)
            if dll_dir_str not in _GMSH_DLL_DIRS:
                _GMSH_DLL_HANDLES.append(os.add_dll_directory(dll_dir_str))
                _GMSH_DLL_DIRS.add(dll_dir_str)

    gmsh_library = _find_gmsh_library(runtime_dirs)
    original_find_library = ctypes.util.find_library

    def _patched_find_library(name: str | None) -> str | None:
        if name:
            normalized = name.lower()
            if normalized.startswith("gmsh") and gmsh_library:
                return gmsh_library
        return original_find_library(name)

    ctypes.util.find_library = _patched_find_library
    try:
        import gmsh  # type: ignore
    finally:
        ctypes.util.find_library = original_find_library

    return gmsh



def _is_binary_stl(data: bytes) -> bool:
    if len(data) < 84:
        return False
    tri_count = struct.unpack("<I", data[80:84])[0]
    return 84 + tri_count * 50 == len(data)



def _read_binary_stl(data: bytes) -> np.ndarray:
    tri_count = struct.unpack("<I", data[80:84])[0]
    triangles = np.empty((tri_count, 3, 3), dtype=float)
    offset = 84
    for idx in range(tri_count):
        offset += 12
        coords = struct.unpack("<9f", data[offset : offset + 36])
        triangles[idx] = np.asarray(coords, dtype=float).reshape(3, 3)
        offset += 38
    return triangles



def _read_ascii_stl(data: bytes) -> np.ndarray:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")

    vertices = []
    for line in text.splitlines():
        stripped = line.strip().lower()
        if not stripped.startswith("vertex"):
            continue
        _, x, y, z = stripped.split()
        vertices.append([float(x), float(y), float(z)])

    if len(vertices) % 3 != 0 or not vertices:
        raise ValueError("Failed to parse ASCII STL triangles.")
    return np.asarray(vertices, dtype=float).reshape(-1, 3, 3)



def _mesh_from_triangles(name: str, triangles: np.ndarray, source_path: str | None) -> MeshModel:
    flat = triangles.reshape(-1, 3)
    scale = 1_000_000.0
    quantized = np.round(flat * scale).astype(np.int64)
    unique_quantized, inverse = np.unique(quantized, axis=0, return_inverse=True)
    vertices = unique_quantized.astype(float) / scale
    faces = inverse.reshape(-1, 3).astype(np.int32)
    return _mesh_from_vertices_faces(name, vertices, faces, source_path)



def _mesh_from_vertices_faces(
    name: str,
    vertices: np.ndarray,
    faces: np.ndarray,
    source_path: str | None,
) -> MeshModel:
    vertices = np.asarray(vertices, dtype=float)
    faces = np.asarray(faces, dtype=np.int32)
    tri_vertices = vertices[faces]
    face_normals = np.cross(tri_vertices[:, 1] - tri_vertices[:, 0], tri_vertices[:, 2] - tri_vertices[:, 0])
    face_normals = _normalize_vectors(face_normals)

    vertex_normals = np.zeros_like(vertices)
    np.add.at(vertex_normals, faces[:, 0], face_normals)
    np.add.at(vertex_normals, faces[:, 1], face_normals)
    np.add.at(vertex_normals, faces[:, 2], face_normals)
    vertex_normals = _normalize_vectors(vertex_normals)

    return MeshModel(
        name=name,
        vertices=vertices,
        faces=faces,
        face_normals=face_normals,
        vertex_normals=vertex_normals,
        source_path=source_path,
    )



def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    safe_norms = np.where(norms < 1e-9, 1.0, norms)
    normalized = vectors / safe_norms
    normalized[norms[:, 0] < 1e-9] = np.array([0.0, 0.0, 1.0])
    return normalized
