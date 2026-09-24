"""Stable catalog metadata for the application workbench chooser."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkbenchInfo:
    key: str
    title_zh: str
    title_en: str
    summary_zh: str
    summary_en: str
    status_zh: str
    status_en: str


WORKBENCHES: tuple[WorkbenchInfo, ...] = (
    WorkbenchInfo(
        "planar",
        "平面工作台",
        "Planar Workbench",
        "平面沉积、基体打印、层状填充和薄壁轮廓。",
        "Planar layers, base, fill, and thin walls.",
        "离线可用",
        "Offline Ready",
    ),
    WorkbenchInfo(
        "curve",
        "曲线工作台",
        "Curve Workbench",
        "沿 STEP 边线和空间曲线生成单道或多道沉积路径。",
        "Single- and multi-pass STEP edge paths.",
        "离线可用",
        "Offline Ready",
    ),
    WorkbenchInfo(
        "freeform",
        "自由曲面工作台",
        "Freeform Workbench",
        "面向曲面贴合、曲面加强和导电线路沉积。",
        "Conformal surfaces and conductive traces.",
        "离线可用",
        "Offline Ready",
    ),
    WorkbenchInfo(
        "rotary",
        "回转工作台",
        "Rotary Workbench",
        "圆柱/圆锥螺旋、回转薄壁和局部多区域沉积。",
        "Cylinder/cone spirals and thin walls.",
        "离线可用",
        "Offline Ready",
    ),
    WorkbenchInfo(
        "tube",
        "管状工作台",
        "Tube Workbench",
        "管状薄壁的设置、Indexed、Buildup 与 Continuous 离线生成。",
        "Tube setup, indexed and continuous paths.",
        "离线可用",
        "Offline Ready",
    ),
    WorkbenchInfo(
        "research",
        "研究工作台",
        "Research Workbench",
        "锥面层、标量场曲面切片和强度导向路径研究。",
        "Conical and scalar-field slicing.",
        "暂不可用",
        "Unavailable",
    ),
)


__all__ = ["WORKBENCHES", "WorkbenchInfo"]
