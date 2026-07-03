from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class EdgeInfo:
    edge_id: str
    body_id: str
    index: int
    point_count: int
    length_hint: float | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.edge_id,
            "body_id": self.body_id,
            "index": self.index,
            "point_count": self.point_count,
            "length_hint": self.length_hint,
        }


@dataclass(slots=True)
class BodyInfo:
    body_id: str
    index: int
    name: str
    color: tuple[float, float, float]
    edge_ids: list[str] = field(default_factory=list)
    triangle_count: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.body_id,
            "index": self.index,
            "name": self.name,
            "color": list(self.color),
            "edge_ids": list(self.edge_ids),
            "triangle_count": self.triangle_count,
        }


@dataclass(slots=True)
class CadModel:
    source_path: Path
    source_hash: str
    bodies: list[BodyInfo]
    edges: list[EdgeInfo]
    shapes: dict[str, Any]
    edge_shapes: dict[str, Any]

    @property
    def edge_map(self) -> dict[str, EdgeInfo]:
        return {edge.edge_id: edge for edge in self.edges}

    @property
    def body_map(self) -> dict[str, BodyInfo]:
        return {body.body_id: body for body in self.bodies}

    def to_json(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_hash": self.source_hash,
            "bodies": [body.to_json() for body in self.bodies],
            "edges": [edge.to_json() for edge in self.edges],
        }


@dataclass(slots=True)
class SelectionState:
    mode: str = "edge"
    body_ids: set[str] = field(default_factory=set)
    edge_ids: set[str] = field(default_factory=set)

    def clear(self) -> None:
        self.body_ids.clear()
        self.edge_ids.clear()

    def to_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "body_ids": sorted(self.body_ids),
            "edge_ids": sorted(self.edge_ids),
        }
