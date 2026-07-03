from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class EdgeInfo:
    """从 STEP 拓扑枚举得到的边线元数据。

    edge_id 是界面、HTTP 和 project.json 共用的稳定标识；length_hint 来自采样点
    的近似长度，只用于列表辅助判断，不参与几何计算。
    """

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
    """一个 STEP solid 对应一个 body。

    当前版本不推断制造分区，body 只代表导入阶段发现的拓扑实体。
    edge_ids 保持原始枚举顺序，便于右侧列表和保存文件稳定复现。
    """

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
    """加载后的内存模型。

    shapes 和 edge_shapes 保存 OCP 原始拓扑对象，渲染层按需转换为 VTK。
    这样项目保存可记录轻量 JSON，界面刷新仍能使用真实 CAD 拓扑。
    """

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
    """全局选择状态。

    右侧列表、左侧预览区、HTTP 自动化和项目保存共享这一份状态。
    mode 保留为 edge，便于旧脚本读取；body 选择由 body_ids 显式表达。
    """

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
