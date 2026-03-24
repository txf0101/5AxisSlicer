"""Common imports for the five-axis slicer package.

五轴切片器包里最常用的一组对外导入。

Most scripts only need the shared data models and the default machine-profile
helpers, so they are re-exported here.
大多数脚本只会用到共享数据模型和默认机床预设辅助函数，这里就统一导出了。
"""

__version__ = "0.3.0"

from .core import (
    MachineParameters,
    MeshModel,
    SliceParameters,
    SliceSelection,
    SliceResult,
    SurfaceMap,
    Toolpath,
)
from .hardware import machine_profile_summary, open5x_freddi_hong_machine

__all__ = [
    "__version__",
    "MachineParameters",
    "MeshModel",
    "SliceParameters",
    "SliceSelection",
    "SliceResult",
    "SurfaceMap",
    "Toolpath",
    "machine_profile_summary",
    "open5x_freddi_hong_machine",
]
