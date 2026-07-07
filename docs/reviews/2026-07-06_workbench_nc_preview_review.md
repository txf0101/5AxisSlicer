# 2026-07-06 Workbench 与 NC 预览复盘

## 本轮目标

本轮按 `圭臬/开发目标文档.docx` 和论文优先计划，把原有 STEP 前置选择器扩展为 Workbench 入口加 Operation Session 的界面框架。短期交互主线锁定为 `Imported NC Review`：已有 G-code 可导入、解析、分层预览、按 Feature Type 分色，并与半透明 STEP 模型叠加显示。

目标文档在 2026-07-06 13:45 已更新，文件大小 492214 字节。文档明确要求软件先进入 workbench，再选择增材处理类型，后续前处理包含制造对象、模型检查、机器材料参数、路径参数、ToolpathPoint、五轴姿态和导出检查。

## 实现内容

- 新增 Workbench 首页，覆盖 Planar、Curve、Freeform、Rotary、Tube、Research 六类入口。未完成工艺以 Preview、Locked、R&D 等状态显示。
- 新增 Operation Session 壳层，页签为 Objects、Print、Material、Machine、Preview、Checks。Objects 页继续保留 body 列表选择和 edge 预览区点选。
- 新增 `Imported NC Review` 操作。当前论文版主打导入已有 G-code 后检查路径，不在这一版重写完整切片算法。
- 新增 `gcode_preview.py`，解析路径段并保存起点、终点、层号、运动类型、挤出角色、进给速度、E 增量、线宽、旋转轴角度和注释来源。
- `viewer.py` 支持 STEP 半透明叠加路径；G-code actor 按颜色键分组，travel、retract、prime 与挤出角色分开着色；A/B/C/U/V/W 角度用于抽样显示喷头轴线。
- Preview 页加入 Feature Type 图例、层范围、travel/extrusion 开关、五轴姿态开关、当前摘要和路径段属性面板。
- 项目保存写入 workbench、operation、STEP 路径、G-code 路径、解析摘要、颜色映射、可见层范围和显隐开关。旧 body/edge 选择字段继续保留。
- HTTP 自动化新增 `/gcode/open`、`/preview/state`、`/preview/layers`、`/preview/visibility`、`/workbench/select`、`/demo/load`。
- CLI 与 PowerShell 启动脚本新增 `--gcode`、`--demo`、`-GCode`、`-Demo`。

## 路径分色依据

PrusaSlicer 的 G-code 预览逻辑核心是解析后的路径语义，注释文本不直接决定最终颜色。本轮采用同一类数据组织：路径段保留 `move_type` 和 `extrusion_role` 两个字段，颜色表再按字段映射到渲染颜色。

`move_type` 覆盖 `travel`、`retract`、`prime`、`extrude` 等运动状态；`extrusion_role` 覆盖 perimeter、external perimeter、internal infill、solid infill、support、bridge、skirt/brim、custom 等特征角色。`;TYPE:`、`;LAYER_CHANGE`、`;Layer`、`;Brim` 等注释只用于识别状态。注释缺失时，解析器按 G0/G1、XYZ 变化、E 轴变化和相对/绝对挤出模式推断。

本轮参考链接：

- PrusaSlicer `GCodeProcessor.cpp`：https://github.com/prusa3d/PrusaSlicer/blob/master/src/libslic3r/GCode/GCodeProcessor.cpp
- PrusaSlicer `MoveVertex`：https://github.com/prusa3d/PrusaSlicer/blob/master/src/libslic3r/GCode/GCodeProcessor.hpp#L123-L135
- PrusaSlicer Viewer 颜色映射：https://github.com/prusa3d/PrusaSlicer/blob/master/src/libvgcode/src/ViewerImpl.cpp#L283-L311

## 质量判断

本轮没有把界面改成只服务截图的静态壳。G-code 解析、保存结构、HTTP 状态和 VTK 渲染共享同一份路径段数据，后续论文截图、回归测试和机器后处理都能沿这条数据链继续扩展。

更值得保留的是方法：外部成熟软件给出参数组织和颜色语义，项目内部只沉淀可维护的数据结构、解析规则、可视化 actor 分组和自动化接口。这个组合比单独堆 UI 控件更耐用，也更接近桌面工程软件的常规质量闭环。

短期壁垒来自三点：真实大 G-code 的缓存解析，STEP 拓扑选择与 NC 路径预览同屏联动，本地 HTTP 接口支撑截图和回归测试。后续如果继续做 Curve 与 Freeform 前处理，这些结构可以直接承接 ToolpathPoint、姿态规划和限位检查。

## 验证记录

- `python -m compileall src tests`：已通过。
- `python -m unittest discover -s tests`：12 个测试通过。
- `scripts/desktop_workbench_smoke.py`：真实 GUI 冒烟测试用于默认演示样例，截图输出到 `outputs/workbench_smoke/01_workbench_preview.png`。
- G-code 单测覆盖 Orca/Prusa 风格 `;TYPE:`、Fractal Cortex 风格 `;Layer`、A/B 与 A/C 轴、相对挤出、绝对挤出、回抽、prime、空走和未知标签。
- UI 状态测试覆盖 workbench 选择、中英切换、预览显隐设置和路径段属性面板。

## 当前限制

- 第一版只读取已有 G-code，不生成完整五轴切片路径。
- 五轴角度当前作为路径段属性和抽样姿态展示，还没有完整机床运动仿真、碰撞检查或轴限位求解。
- 参数页已按 PrusaSlicer 与 NX 多轴增材逻辑搭好页面，当前多数值仍是论文演示占位。
- VTK 在 Windows 下会覆盖右侧普通控件，当前布局采用左侧 Workbench 面板、中间页签、右侧 VTK 视图，避免控件被遮挡。
- 大文件预览采用抽样保存路径段，统计值保留全量；后续若要做逐段拾取，需要增加分块加载或索引表。
