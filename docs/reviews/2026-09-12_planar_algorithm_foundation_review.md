# P01—P06 平面算法与工作台复盘

日期：2026-09-12。本文先记录 P01 的区域/层截面起步及 P02—P05 纯领域原型，随后在同一文件补记 P01—P06 的产品接入和阶段验收。P01—P06 已于本日按依赖顺序关闭，下一项为 C01。

## 已完成的领域基础

- `algorithms/planar/region.py` 使用 OCCT 的实体—平面截交恢复闭环。输出按岛、外环和孔组织的 `PlanarRegion`，层面固定在 Workpiece Build-XY；空层保留，避免把不连续高度静默合并。
- `zigzag.py` 生成带孔裁剪的往复填充，并使用共享 `GeneratedToolpath` 区分 approach、travel 和 deposition。非沉积点没有材料体积。
- `offset.py` 暂只处理凸形、无孔区域的内缩。孔、凹形和会使区域消失的情形返回诊断，不制造不可信路径。
- `thin_wall.py` 规定不足最小道宽时拒绝；开放壁单中心线可生成。未给出区域法向时，多道开放壁拒绝。
- `spiral.py` 只接受至少两层、每层一个无孔岛的轮廓，生成连续 Z 插值；多岛输入明确拒绝。

## 真值与验证

CadQuery 构造了含孔和独立岛的实体，验证截交拓扑。专项测试还覆盖缺失 body、非法层高、孔内不沉积、非沉积零体积、窄区消失、凹区拒绝、开放壁体积、不足道宽、多岛螺旋拒绝和连续 Z。

`tmp/pytest9/Scripts/python.exe -m pytest -q tests/test_planar_region.py tests/test_planar_zigzag.py tests/test_planar_offset.py tests/test_planar_thin_wall.py tests/test_planar_spiral.py`：10 passed。

同一解释器的 `scripts/check_quality.py`（Ruff、格式、复杂度、mypy）通过；平面模块单独 mypy 也通过。预检显示 Qt QSettings 可写；本轮尚未运行 Qt 或 VTK 测试，因为没有改动 UI 或渲染层。

## 来源、判断与限制

CuraEngine 和 PrusaSlicer 可用来核对平面切片的数据流、孔岛行为和错误边界。两者均为 AGPLv3；本项目维持 MIT，因此本轮没有复制、翻译或改写其源码、测试或内部数据结构。实现只使用本项目的 OCCT、Toolpath 契约和独立测试。稳定入口和许可证已登记在 `docs/planning/reference_research.md` 的 OS-04、OS-05。

领域原型建立时尚未接入 Manufacturing Setup、Build 坐标变换、稳定几何引用/重绑、操作参数持久化、语义哈希或生成状态，也没有 Planar controller、GUI/脚本/HTTP 共享命令、取消、六件套后处理、轴轨迹、碰撞检查、G-code 回读、保存重开、双语 UI 和使用手册。这些缺口已在后续 P01—P06 产品接入中逐项处理，不能用本节的原型测试数字代替后续阶段证据。

## P01 产品接入与关闭

P01 已增加独立的 Planar operation、controller、command、product 和 Qt 页面。实体选择保存完整 `GeometryReference`，源更新执行唯一重绑；失败保留原引用并将操作置为 Invalid。层面现按 `T_model_from_build` 在模型中构造，并把截交点回算到 Workpiece Build CS，非默认 Build 原点已有独立案例。

GUI、受限脚本和 HTTP 使用同一个 `PlanarCommandService` 与 `CommandKernel`。参数和引用变化更新语义哈希，使已有结果 Stale；取消在发布前终止并保留上一份 Ready 结果。P01 结果只包含区域轮廓预览，清单显式写入 `planar.region_preview_only` 且禁止 NC 导出，避免把尚未完成的 P02 路径当成可制造结果。项目默认 operation loader 已能区分 Tube 与 Planar 类型，MainWindow 保存时合并两类操作，加载时按类型恢复。

专项命令覆盖 P01、共享命令内核、受限脚本和 Qt 页面，共 `54 passed, 32 subtests passed`。质量门禁的 Ruff、format、context budget 与 mypy（105 个源码文件）通过。最初组合测试因系统 pytest 临时目录拒绝访问失败；按验证 SOP 改用项目内独立 `--basetemp` 后通过。第一次质量检查发现截层函数、Planar UI 和既有 MainWindow 超出结构预算，拆分为小函数和 `planar_shell.py` 后通过，没有放宽门槛。证据见 [P01 清单](evidence/2026-09-12_p01_planar/manifest.json)。

P01 的完成范围是 Setup、Build CS、稳定引用、层截面、状态、保存和最小可见预览。沉积轮廓、材料覆盖、机轴、碰撞、G-code 回读、六件套和 Planar 图文手册仍由 P02—P06 完成。下一项按顺序进入 P02。

## P02 Zigzag Fill 产品接入与关闭

P02 在 P01 区域/层截面基础上接入 perimeter-first zigzag。每层和每个岛按稳定键排序，外轮廓与孔边界先生成闭合 skin deposition，再生成带孔裁剪的交替 infill。不同路径之间显式记录 retract、travel、prime；非沉积点的材料体积为零。`PlanarProcessParameters` 已保存填充间距、沉积/空移进给和回抽长度，参数进入语义哈希并参与 Stale 判断。

产品链现为“区域截面→共享 Toolpath→独立格点量测→Generic XYZAC 参考轨迹→G-code→独立 readback”。GUI、受限脚本和 HTTP 继续使用 `PlanarCommandService` 与 `CommandKernel`，并提供六件套导出。覆盖与残余面积按格点中心和道宽扫掠近似；越界指标核对沉积中心线，尚未重建完整熔道包络。当前单圈 perimeter 沿截面边界中心线生成，半道宽外扩风险留待 P03 的可靠布尔偏置处理。该限制不应被解释为尺寸合格证明。

第一次产品测试使用 900 mm/min 进给时，参考机型在直角轮廓处报告加速度超限，清单按设计进入 Error 并阻止导出。正常真值案例改用 100 mm/min 后通过；这是测试机型约束变化后的有效复测。重复的平面姿态奇异警告按代码和严重度汇总并保留计数，避免结果文件被逐点重复信息淹没。

正式专项为 44 passed；全仓串行回归为 509 passed、3 skipped、130 subtests passed。3 个 skip 是既有 Windows 符号链接权限覆盖，不计为通过。Ruff、format、context budget 与 mypy（106 个源码文件）通过。证据见 [P02 清单](evidence/2026-09-12_p02_planar/manifest.json)。Generic XYZAC 只用于离线轨迹和格式回读；具体控制器、真实机床标定、碰撞资格和试切尚未验证。

CuraEngine 和 PrusaSlicer 适合核对“截层→周边→填充→排序→G-code”的公开行为。两者均为 AGPLv3，本项目只参考可观察流程并独立实现，没有复制、翻译或改写其源码、测试和内部数据结构。固定来源与许可边界继续由 `docs/planning/reference_research.md` 维护。

P02 使用手册已归档到 [`docs/guides/planar_workbench_zh.md`](../guides/planar_workbench_zh.md)，覆盖真实 STEP 示例 `example/三叶扇/Supportless_sample.stp`、`body_002` 单层约 Z=60 mm、100 mm/min 建议、参数、生成/预览、六件套、保存重开和错误恢复。`assets/planar/` 已保存 1366×768、1600×900、1920×1080 的中英文 Qt/OpenGL 实际渲染图及 `summary.json`；三种尺寸按钮文字均适配且无碰撞，生成预览记录 327 个可见段。Computer Use 无法可靠识别此应用窗口，所以这些图只作为直接 Qt 渲染证据，不写成真人桌面点击证据。

## P03 Offset Fill 产品接入与关闭

P03 将原有凸形无孔原型替换为基于 OCCT `BRepOffsetAPI_MakeOffset` 的轮廓偏置。多轮偏置保留外环与孔的方向和包含关系，覆盖凹区、多岛、窄颈分裂及局部消失。产品链输出共享 Toolpath、残余轮廓、残余面积、Generic XYZAC 参考轨迹、G-code、独立 readback 和六件套。部分区域消失保留 `Warning` 并允许导出；全部区域消失进入 `Error`，控制器阻止导出。

首次失败显示，自交输入在进入 OCCT 后才暴露，诊断顺序无法稳定指出原始拓扑问题。修复后先检查自交、非法孔和退化轮廓，再调用偏置内核。高密度 STEP 截面还使组合测试一度约需 212 秒；后续先删除共线点，并让 OCCT 直线边只保留端点，不再固定采样 12 段，50 项相关组合测试降至约 9 秒。P03 阶段测试为 12 passed，JUnit 见 [P03 证据目录](evidence/2026-09-12_p03_planar/)。

## P04 Thin Wall 产品接入与关闭

P04 支持开放壁单道与多道、闭壁同心多道，以及由平面区域驱动的实体内偏置。产品路径的第一条中心线位于实体边界内半道宽处；闭壁使用一致的 miter 偏置。壁厚不足目标道数时统一采用 `reduce` 策略，生成 `planar.thin_wall_width_reduced` Warning，不静默制造超出区域的路径。参数 `wall_thickness_mm` 和 `thin_wall_max_passes` 已进入 JSON 往返、语义哈希、GUI、脚本与 HTTP，参数变化使旧结果进入 Stale。

P04 输出共享 Toolpath、G-code、独立 readback 和六件套。单/多道、开放/闭合、道数限制、可见 Warning、Stale 和产品导出共 7 项阶段测试通过，证据见 [P04 证据目录](evidence/2026-09-12_p04_planar/)。

## P05 Spiral 产品接入与关闭

P05 的受限范围为至少两个严格递增 Z 层、每层单岛且无孔。生成前检查 region 对应、轮廓方向、闭合和拓扑一致性；轮廓经统一弧长重采样后形成连续 Z 插值，并在插值截面上采样检查沉积点处于实体内。材料体积由几何长度和工艺参数独立复算。路径包含 `finish` 事件，沉积与空移进给均来自操作参数，不使用固定 600 mm/min。

真实 STEP 首次生成时，旧 P02 离散层量测把连续 Z 中间点强行投影到下层轮廓，误报 `planar.deposition_outside_region = 0.264886 mm`。修复后 Spiral 使用连续插值截面的专用验证语义，同时保留 `planar.spiral_discrete_layer_projection_only` Warning，明确离散层投影仅供参考；材料体积误差仍为 0。单层、孔、多岛、拓扑变化、错误层序和退化轮廓继续明确拒绝。P05 阶段测试为 10 passed，证据见 [P05 证据目录](evidence/2026-09-12_p05_planar/)。

## 成熟项目参考与许可边界

CuraEngine 和 PrusaSlicer 提供成熟的公开流程，可用于核对“截层→周边→填充→排序→G-code”、孔岛行为及失败边界。两者均采用 AGPLv3；本项目维持 MIT，因此只参考公开数据流和可观察行为，没有复制、翻译或逐行改写其源码。P03—P05 使用 OCCT、项目共享 Toolpath 和独立测试自行实现。固定链接和许可证记录见 `docs/planning/reference_research.md` 的 OS-04、OS-05。

## P06 Planar 工作台阶段验收与关闭

四种操作现共用稳定 body 引用、Setup/Build 坐标、`PlanarCommandService`、状态机和产品输出。`offset_pass_count`、`wall_thickness_mm`、`thin_wall_max_passes`、`spiral_samples_per_contour` 已进入 JSON 往返、语义哈希、GUI、脚本和 HTTP。UI 允许 Zigzag、Offset、Thin Wall、Spiral 在结果可导出时导出；生成错误显示在状态区，语言切换和 refresh 后仍保留。Spiral 单层错误显示 `planar.spiral_layers_insufficient：螺旋至少需要两个相邻层。`，导出按钮禁用；修正层范围后能够重新生成并恢复导出。

真实输入使用 `example/三叶扇/Supportless_sample.stp` 的 `body_002`，文件 SHA256 为 `291155b64dace255937bbcddb496da4f11f8319a2fe6b9d32aa29a340686befc`。Zigzag、Offset 和 Thin Wall 使用 Z=60 mm，Spiral 使用 Z=60.0→60.6 mm；沉积和空移进给均为 100 mm/min。四种输出分别为 399、15、5、129 个 Toolpath 点，均为可导出的 Warning 状态、材料体积误差 0，六件套齐全且 readback passed。实际文件及逐文件 SHA256 见 [真实模型摘要](evidence/2026-09-12_p06_planar/real_model/summary.json)。

UI 证据覆盖 Offset、Thin Wall、Spiral，包含中文/英文、1366×768、1600×900、1920×1080、正常生成、Spiral 单层错误及修复恢复。所有记录均为 `collisions=[]`、`text_fits=true`；正常与恢复状态 `export_enabled=true`，错误状态为 false。首次截图脚本误选默认 `body_001`，发现后改为显式选择 `body_002` 并重新生成全部截图和摘要。证据来自 Qt 控件抓图及项目 OpenGL 查看器直接渲染，不代表真人桌面点击。记录见 [UI 摘要](evidence/2026-09-12_p06_planar/ui/summary.json)。

最终串行验证使用 `tmp/pytest9/Scripts/python.exe`（Python 3.12.7、pytest 9.1.1）。全部 `tests/test_planar*.py` 为 77 passed；全仓为 542 passed、3 skipped、130 subtests passed。3 个 skip 是既有 Windows 符号链接权限覆盖，不计为通过。`scripts/check_quality.py` 的 Ruff、format、context budget 和 mypy 全部通过。JUnit 和阶段证据见 [P06 清单](evidence/2026-09-12_p06_planar/manifest.json)。

P06 关闭的是离线软件工作流。Generic XYZAC 带约 250 mm 的 XYZ 装夹平移，仅用于离线轨迹、格式输出和回读参考；具体控制器语义、真实机床标定、现场碰撞资格、材料工艺和试切没有验证。Planar 使用手册及索引已更新，下一项按台账进入 C01；Curve 完成后依照已调整顺序进入 Rotary。

## 使用的 Skills

- `five-axis-workbench-development`：确定 P01—P06 阶段门槛、共享 Toolpath 边界、来源登记、真实流程、手册和任务闭环规则。
- `five-axis-slicer-validation`：选择 `tmp/pytest9` 解释器，执行只读预检、P03—P06 阶段测试、Qt 串行检查、全仓回归与质量门禁，并按规则记录 skip 和证据边界。
