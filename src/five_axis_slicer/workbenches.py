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
        "Planar deposition, base build, layer fill, and thin-wall contours.",
        "预览",
        "Preview",
    ),
    WorkbenchInfo(
        "curve",
        "曲线工作台",
        "Curve Workbench",
        "沿 STEP 边线和空间曲线生成单道或多道沉积路径。",
        "Single-pass or multi-pass deposition along STEP edges and spatial curves.",
        "可用",
        "Ready",
    ),
    WorkbenchInfo(
        "freeform",
        "自由曲面工作台",
        "Freeform Workbench",
        "面向曲面贴合、曲面加强和导电线路沉积。",
        "Conformal coating, surface reinforcement, and conductive traces.",
        "预览",
        "Preview",
    ),
    WorkbenchInfo(
        "rotary",
        "回转工作台",
        "Rotary Workbench",
        "圆柱/圆锥螺旋、回转薄壁和局部多区域沉积。",
        "Cylinder/cone spirals, rotary thin walls, and local multi-region deposition.",
        "可用",
        "Ready",
    ),
    WorkbenchInfo(
        "tube",
        "管状工作台",
        "Tube Workbench",
        "管状薄壁切片的制造设置与坐标定义。",
        "Preprocessing for tubes, channels, and centerline-driven structures.",
        "设置",
        "Setup",
    ),
    WorkbenchInfo(
        "research",
        "研究工作台",
        "Research Workbench",
        "锥面层、标量场曲面切片和强度导向路径研究。",
        "Conical layers, scalar-field surface slicing, and research paths.",
        "研发",
        "R&D",
    ),
)


__all__ = ["WORKBENCHES", "WorkbenchInfo"]
