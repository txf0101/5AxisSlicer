"""Shared CAD topology, selection, and viewer-overlay value types.

CAD entities and ``PickHit.position_source`` use Source CS in millimetres.
Overlay origins and axes are already expressed in the viewer display frame;
renderers must not apply the model transform to them a second time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Vector3 = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class PickRequest:
    """Constrain one pick mode; ``None`` allows every ID of the chosen kind."""

    kind: str
    allowed_ids: frozenset[str] | None = None
    multiple: bool = False

    def __post_init__(self) -> None:
        if self.kind not in {"body", "face", "edge", "vertex"}:
            raise ValueError(f"Unsupported pick kind: {self.kind}")


@dataclass(frozen=True, slots=True)
class PickHit:
    """A hit resolved back to Source CS; position is None when unavailable."""

    kind: str
    entity_id: str
    position_source: Vector3 | None = None


@dataclass(frozen=True, slots=True)
class CoordinateFrameOverlay:
    """Display-space right-handed unit axes with a millimetre draw scale."""

    frame_id: str
    name: str
    origin: Vector3
    x_axis: Vector3 = (1.0, 0.0, 0.0)
    y_axis: Vector3 = (0.0, 1.0, 0.0)
    z_axis: Vector3 = (0.0, 0.0, 1.0)
    scale: float = 10.0
    visible: bool = True


@dataclass(frozen=True, slots=True)
class BuildSurfaceOverlay:
    """A display-space build plane whose physical dimensions are millimetres."""

    surface_id: str
    shape: str
    origin: Vector3 = (0.0, 0.0, 0.0)
    x_axis: Vector3 = (1.0, 0.0, 0.0)
    y_axis: Vector3 = (0.0, 1.0, 0.0)
    width_mm: float | None = None
    depth_mm: float | None = None
    diameter_mm: float | None = None


@dataclass(frozen=True, slots=True)
class BoundingBox:
    minimum: Vector3
    maximum: Vector3

    @property
    def diagonal(self) -> float:
        return (
            sum(
                (right - left) ** 2 for left, right in zip(self.minimum, self.maximum, strict=False)
            )
            ** 0.5
        )

    def to_json(self) -> dict[str, list[float]]:
        return {
            "minimum": list(self.minimum),
            "maximum": list(self.maximum),
        }


@dataclass(frozen=True, slots=True)
class CadUnitInfo:
    source_length_unit: str
    internal_length_unit: str = "millimetre"
    scale_to_mm: float = 1.0
    angle_unit: str | None = None
    solid_angle_unit: str | None = None
    override_applied: bool = False
    declared_length_unit: str | None = None
    conversion_source: str = "step_declaration"

    def to_json(self) -> dict[str, Any]:
        return {
            "source_length_unit": self.source_length_unit,
            "internal_length_unit": self.internal_length_unit,
            "scale_to_mm": self.scale_to_mm,
            "angle_unit": self.angle_unit,
            "solid_angle_unit": self.solid_angle_unit,
            "override_applied": self.override_applied,
            "declared_length_unit": self.declared_length_unit,
            "conversion_source": self.conversion_source,
        }


@dataclass(slots=True)
class VertexInfo:
    vertex_id: str
    body_id: str
    index: int
    point: Vector3
    edge_ids: list[str] = field(default_factory=list)
    signature: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.vertex_id,
            "body_id": self.body_id,
            "index": self.index,
            "point": list(self.point),
            "edge_ids": list(self.edge_ids),
            "signature": self.signature,
        }


@dataclass(slots=True)
class FaceInfo:
    face_id: str
    body_id: str
    index: int
    surface_type: str
    area: float
    centroid: Vector3
    bounds: BoundingBox
    edge_ids: list[str] = field(default_factory=list)
    normal: Vector3 | None = None
    axis_origin: Vector3 | None = None
    axis_direction: Vector3 | None = None
    radius: float | None = None
    secondary_radius: float | None = None
    semi_angle_rad: float | None = None
    orientation: str = "forward"
    signature: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.face_id,
            "body_id": self.body_id,
            "index": self.index,
            "surface_type": self.surface_type,
            "area": self.area,
            "centroid": list(self.centroid),
            "bounds": self.bounds.to_json(),
            "edge_ids": list(self.edge_ids),
            "normal": None if self.normal is None else list(self.normal),
            "axis_origin": None if self.axis_origin is None else list(self.axis_origin),
            "axis_direction": (None if self.axis_direction is None else list(self.axis_direction)),
            "radius": self.radius,
            "secondary_radius": self.secondary_radius,
            "semi_angle_rad": self.semi_angle_rad,
            "orientation": self.orientation,
            "signature": self.signature,
        }


@dataclass(slots=True)
class EdgeInfo:
    edge_id: str
    body_id: str
    index: int
    point_count: int
    length_hint: float | None = None
    curve_type: str = "other"
    exact_length: float | None = None
    vertex_ids: list[str] = field(default_factory=list)
    face_ids: list[str] = field(default_factory=list)
    endpoints: tuple[Vector3, Vector3] | None = None
    arc_length_midpoint: Vector3 | None = None
    center: Vector3 | None = None
    axis_direction: Vector3 | None = None
    radius: float | None = None
    signature: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.edge_id,
            "body_id": self.body_id,
            "index": self.index,
            "point_count": self.point_count,
            "length_hint": self.length_hint,
            "curve_type": self.curve_type,
            "exact_length": self.exact_length,
            "vertex_ids": list(self.vertex_ids),
            "face_ids": list(self.face_ids),
            "endpoints": (
                None
                if self.endpoints is None
                else [list(self.endpoints[0]), list(self.endpoints[1])]
            ),
            "arc_length_midpoint": (
                None if self.arc_length_midpoint is None else list(self.arc_length_midpoint)
            ),
            "center": None if self.center is None else list(self.center),
            "axis_direction": (None if self.axis_direction is None else list(self.axis_direction)),
            "radius": self.radius,
            "signature": self.signature,
        }


@dataclass(slots=True)
class BodyInfo:
    body_id: str
    index: int
    name: str
    color: tuple[float, float, float]
    kind: str = "solid"
    assembly_path: str | None = None
    bounds: BoundingBox | None = None
    volume: float | None = None
    surface_area: float | None = None
    centroid: Vector3 | None = None
    edge_ids: list[str] = field(default_factory=list)
    face_ids: list[str] = field(default_factory=list)
    vertex_ids: list[str] = field(default_factory=list)
    triangle_count: int = 0
    signature: str = ""

    @property
    def is_solid(self) -> bool:
        return self.kind == "solid"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.body_id,
            "index": self.index,
            "name": self.name,
            "color": list(self.color),
            "kind": self.kind,
            "assembly_path": self.assembly_path,
            "bounds": None if self.bounds is None else self.bounds.to_json(),
            "volume": self.volume,
            "surface_area": self.surface_area,
            "centroid": None if self.centroid is None else list(self.centroid),
            "edge_ids": list(self.edge_ids),
            "face_ids": list(self.face_ids),
            "vertex_ids": list(self.vertex_ids),
            "triangle_count": self.triangle_count,
            "signature": self.signature,
        }


@dataclass(slots=True)
class CadModel:
    """In-memory CAD model with serializable topology metadata.

    OpenCascade shapes stay in the dedicated maps. Project files persist only
    their descriptors and reload the authoritative STEP copy on open.
    """

    source_path: Path
    source_hash: str
    bodies: list[BodyInfo]
    edges: list[EdgeInfo]
    shapes: dict[str, Any]
    edge_shapes: dict[str, Any]
    faces: list[FaceInfo] = field(default_factory=list)
    vertices: list[VertexInfo] = field(default_factory=list)
    face_shapes: dict[str, Any] = field(default_factory=dict)
    vertex_shapes: dict[str, Any] = field(default_factory=dict)
    units: CadUnitInfo = field(default_factory=lambda: CadUnitInfo(source_length_unit="millimetre"))
    bounds: BoundingBox | None = None
    source_size_bytes: int | None = None
    source_mtime_ns: int | None = None

    @property
    def edge_map(self) -> dict[str, EdgeInfo]:
        return {edge.edge_id: edge for edge in self.edges}

    @property
    def body_map(self) -> dict[str, BodyInfo]:
        return {body.body_id: body for body in self.bodies}

    @property
    def face_map(self) -> dict[str, FaceInfo]:
        return {face.face_id: face for face in self.faces}

    @property
    def vertex_map(self) -> dict[str, VertexInfo]:
        return {vertex.vertex_id: vertex for vertex in self.vertices}

    @property
    def solid_bodies(self) -> list[BodyInfo]:
        return [body for body in self.bodies if body.is_solid]

    def to_json(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_hash": self.source_hash,
            "source_size_bytes": self.source_size_bytes,
            "source_mtime_ns": self.source_mtime_ns,
            "units": self.units.to_json(),
            "bounds": None if self.bounds is None else self.bounds.to_json(),
            "bodies": [body.to_json() for body in self.bodies],
            "faces": [face.to_json() for face in self.faces],
            "edges": [edge.to_json() for edge in self.edges],
            "vertices": [vertex.to_json() for vertex in self.vertices],
        }


@dataclass(slots=True)
class SelectionState:
    """Transient viewer selection; manufacturing semantics live in Setup."""

    mode: str = "edge"
    body_ids: set[str] = field(default_factory=set)
    face_ids: set[str] = field(default_factory=set)
    edge_ids: set[str] = field(default_factory=set)
    vertex_ids: set[str] = field(default_factory=set)

    def clear(self) -> None:
        self.body_ids.clear()
        self.face_ids.clear()
        self.edge_ids.clear()
        self.vertex_ids.clear()

    def to_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "body_ids": sorted(self.body_ids),
            "face_ids": sorted(self.face_ids),
            "edge_ids": sorted(self.edge_ids),
            "vertex_ids": sorted(self.vertex_ids),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any] | None) -> SelectionState:
        values = payload or {}
        return cls(
            mode=str(values.get("mode", "edge")),
            body_ids=set(map(str, values.get("body_ids", []))),
            face_ids=set(map(str, values.get("face_ids", []))),
            edge_ids=set(map(str, values.get("edge_ids", []))),
            vertex_ids=set(map(str, values.get("vertex_ids", []))),
        )
