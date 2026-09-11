# T08—T12 Tube Workbench 阶段审查

日期：2026-09-11。范围为 T08 Indexed 输出与 UI 闭环、T09 Buildup 与底座多工序、T10 Continuous 几何与 RMF、T11 连续运动与输出、T12 整个 Tube Workbench 阶段验收。

## 实现与来源边界

- T08 完成 STEP → Generate → 检查 → NC → 回读、取消/过期状态、保存重开和 pipe2 Indexed 产品归档；实际生成 1171 points，readback passed。
- T09 完成多道厚壁/加厚、底座独立操作、确定性工序排序和跨操作安全衔接。
- T10 完成空间中心线 RMF、连续螺旋、接缝、层和退化输入诊断；T11 完成连续姿态、C 轴展开、速度/加速度限制、全运动碰撞检查和 NC 回读。
- T12 覆盖三种操作、错误样例、UI/脚本/HTTP 路由、保存重开、帮助入口和阶段回归。
- 算法为本项目独立复写，受相邻 Fractal Cortex/V1 项目启发，运行时不依赖相邻目录。RMF 参考 Wang 等论文；G-code 语义区分 LinuxCNC 与 Marlin/RepRap M82；时间参数化参考 MoveIt；碰撞/截交参考 FCL/OCCT。详见 [参考资料](../planning/reference_research.md#8-t08t12-新实现的可核对来源边界)。
- Generic XYZAC 是离线参考模型，测试通过不构成具体控制器、后处理器、机床标定、现场试切或真实机床资格。

## 验证与证据

- 质量门禁：Ruff、format、context-budget、mypy（92 files）全通过。
- 专项回归：98 passed、1 skipped、2 subtests；全仓回归：465 passed、3 skipped、130 subtests。3 个 skip 均为 Windows `WinError 1314` 符号链接权限。
- 首次 targeted 回归发现 1366×768 下按钮行高相压；调整左侧操作区布局和英文长标签宽度后，串行重跑形成 `pytest-targeted-pass.xml`。最终 Tube UI 回归为 30 passed、2 subtests。后续通过结果作为交付证据，首次失败记录仍保留在 `pytest-targeted.xml`。
- 真人 Windows 渲染证据覆盖 1366×768、1600×900、1920×1080，中英文 Tube Indexed/Buildup/Continuous 页面；`summary.json` 显示 `collisions=[]` 且所有 `text_fits=true`。
- pipe2 Indexed 六件套位于 `evidence/2026-09-11_t08_t12/product/pipe2-indexed/`：`main.gcode`、`machine_axes.csv`、`preview.json`、`toolpath.json`、`warnings.json`、`manifest.json`。

## 限制

当前仍是离线软件验收；未验证真实控制器、真实设备参数、机床标定、现场碰撞或试切。Continuous 和 Buildup 的证据证明软件路径、状态和检查契约，不替代生产工艺资格。后续任务进入 P01，复用本阶段 Toolpath、结果状态、检查和证据结构。
