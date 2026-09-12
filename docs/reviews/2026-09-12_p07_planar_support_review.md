# P07 Planar Grid/Lines 支撑实施复盘

日期：2026-09-12。本复盘记录 P07 的 buildplate-only 垂直支撑实现、代码审查修复、真实模型与 UI 证据及验证边界。任务台账仍由 `docs/planning/progress_tracker.md` 统一维护，本文不替代台账状态。

## 范围与来源边界

P07 首版检测相邻截层形成的悬垂和空中岛，按 XY/Z gap 构造从 Build Z=0 平台连通的竖直支撑柱，并把稀疏 body 与靠近模型的 interface 分开。路径支持 `Lines` 和 `Grid`；Grid 采用逐层交替的正交 Lines，避免同层交叉处重复挤出。模型中途起撑、Tree/Organic、桥接专用路径、双材料和支撑/零件联合逐层编排不在本轮范围。

Prusa 官方 Support 文档用于核对 `Supports on build plate only`、悬垂阈值、顶部 Z 接触距离和界面层数等公开参数语义。PrusaSlicer 与 CuraEngine 均采用 AGPLv3，本轮只参考公开可观察行为和许可证边界。支撑几何、分区、状态与 Toolpath 均按本项目契约 clean-room 独立实现，没有复制、翻译或改写其源码、测试和内部数据结构。固定来源见 [`reference_research.md` 第 9 节](../planning/reference_research.md#9-p07-支撑行为的公开来源边界)。

## 实现闭环

`algorithms/planar/support.py` 保留显式空层，计算悬垂接触域、XY 膨胀障碍和按层高向上量化的 Z gap，再将候选柱逐层与上一层平台连通域求交。输出按 `planar_support` 和 `planar_support_interface` 标记 body/interface，并使用共享 `GeneratedToolpath` 的 deposition、travel、retract、prime 语义。参数校验覆盖角度、非负间隙、主体/界面线距、0—100 个界面层及 Lines/Grid 图案。

产品链沿用 Planar 的 `Geometry → SlicePlan → Toolpath → Generic XYZAC 参考轨迹 → ValidationReport → G-code → readback`，当前产物算法版本为 `planar-support-product-v3`。输入、名称、启用状态、Setup 或支撑参数变化会使旧结果 Stale；Error 阻止 G-code 和导出；取消生成保留上一份有效结果。GUI、受限脚本与 HTTP 经同一 `PlanarCommandService` 修改操作，HTTP 已覆盖 issues、validate、cancel、undo 和 redo。项目保存重开保留操作、引用、参数和资格摘要；运行时 Toolpath/G-code 不序列化，所以原 Ready/Warning 在重开后转为 Stale，必须重新生成。可导出结果包含 `main.gcode`、`toolpath.json`、`machine_axes.csv`、`warnings.json`、`preview.json` 和 `manifest.json` 六件套。

## 代码审查后的修复

实现期间按源码审查和针对性反例修复了以下问题：

- 操作元数据、启用状态、Setup 和替换输入未完整使旧结果 Stale；补齐语义与控制器失效边界。
- XY gap 有意留下的无支撑区曾被计入平台不可达；诊断现先扣除配置间隙域，再判断真实阻断。
- 全部候选支撑不可达时，空路径曾退化为 `support_not_required`；现保留 `planar.support_unreachable_from_buildplate` 的真实 Error。
- CadQuery/OCCT 几何工作期间的取消异常曾被包装成内核失败；关键循环加入 checkpoint，并原样重抛 `GenerationCancelled`。
- buildplate-only 输入若从高于首个平台沉积层开始，会截断连通链；现要求 `first_layer_z_mm == layer_height_mm`，否则明确拒绝。
- `support_interface_layers` 曾缺少可控上限；领域参数、持久化参数和 UI 统一限制为 0—100。
- 支撑 travel 和 deposition 曾只按端点判断；现对每个完整线段与目标 CAD 做相交检查，命中时阻止导出。该检查不包含零件 Toolpath、已打印状态和完整喷嘴体扫掠，所以继续保留 `planar.support_joint_schedule_unverified` Warning。
- 长英文诊断和支撑控件曾使编辑区横向溢出；布局改为只允许纵向滚动，并新增 1366×768 与 1920×1080 的可见区域断言。

这些修复均由回归测试覆盖，包括附着悬臂的非零 XY gap、部分/全部不可达、取消、首层平台约束、界面层上下界、输入替换和 UI 长文本。

最终复核还修复了多操作 UI 始终选中最后一个操作、活动生成候选未共享取消 token、撤销丢失运行时结果、重开误报 Ready、主体/interface Viewer 角色未区分、HTTP 缺少问题与事务入口等缺口。Viewer 直接读取共享 Toolpath：`support_material` 为浅绿色，`support_interface` 为深绿色；`toolpath.json` 和 `preview.json` 保留两种角色。当前通用 G-code marker 不编码 extrusion role，独立回读核对点身份、类型、坐标、进给、挤出量和顺序；该边界没有被转写成角色级 G-code 资格。

## 解析真值、导出与回读

解析输入为悬空矩形梁 `X=4..12 mm、Y=2..8 mm、Z=2.2..3.2 mm`。层高和首层均为 0.5 mm，请求 Z=0.5—3.0 mm；零件下方四个空截层被显式保留。Grid 支撑得到 33 条沉积段，其中 body 12 条、interface 21 条；独立复算材料体积为 61.86 mm³，与结果记录一致，沉积域最大越界为 0。Toolpath 与轨迹均为 66 点，G-code 独立回读为 66/66。独立手算测试还固定了 Lines 为 15 段、30 点、39.0 mm、15.60 mm³；Grid 为 14 段、28 点、39.4 mm、15.76 mm³；窄区为 2.6 mm、1.04 mm³，消失区完整拒绝。阈值敏感性、XY/Z gap、主体/interface 分层、路径方向、间距、顺序和材料量均不复制实现公式。

仓库真实复杂 STEP `example/三叶扇/Supportless_sample.stp` 的 `body_002` 在 Z=0.5—60.0 mm、层高 0.5 mm 下成功生成 9,662 点，材料量 5,663.310163 mm³，9,662/9,662 回读通过并导出六件套。另一个风扇 `example/扇叶/风扇扇叶(1).STEP` 在 Build Z=57 mm 需要 0.00100791389 mm 端点修正，超过 0.001 mm 上限，报告 `planar.section_endpoint_gap_exceeds_limit`，进入 Error 且未导出。两者与解析梁见[当前真实模型证据](evidence/2026-09-12_p07_planar_final/real_model/)。

## UI 证据

[当前 UI 摘要](../guides/assets/planar/current_p01_p07/p07/summary.json)包含 9 个 Qt/OpenGL 控件抓图案例：中文与英文，1366×768、1600×900、1920×1080 三种窗口尺寸，覆盖顶部参数、Grid/Lines Warning、过窄 Error 及恢复、参数变化 Stale 及重新生成。参数标签、单位、帮助、按钮和紧凑问题索引均可见；全部案例 `horizontal_scroll_max=0`、`collisions=[]`，可见按钮无文字裁切。该证据是 Qt widget grab 加项目 OpenGL Viewer，不是真人桌面点击；Planar 页面不使用 VTK 后端。

## 性能补充观察

一次 60 层纯领域即时探针使用前 59 层为空、顶层为 10 mm × 10 mm、层高 0.2 mm 的合成输入和默认支撑参数。`generate_support_plan` 用时 0.579038 s，`generate_support_toolpath` 用时 0.359642 s；结果有 58 个非空支撑层、656 points、655 events，且无诊断。`cancel_after=8` 在第 8 个 checkpoint 抛出 `GenerationCancelled`，用时 0.000143 s。

该结果是单次合成解析输入的补充观察，未形成统计基准。输入以空层为主，不能代表复杂多岛、孔或真实 STEP；探针未插桩 OCCT 内部布尔次数，也未覆盖 Qt、G-code、回读和实机。因此这些时长不作为性能承诺或阶段硬证据。

## 测试与质量门禁

串行验证使用项目已核验的 `tmp/pytest9/Scripts/python.exe`（Python 3.12.7、pytest 9.1.1）。最终源码下 P07 目标集合为 **150 passed**，全部 Planar 为 **223 passed**，全仓为 **753 passed、3 skipped、130 subtests passed**。3 个 skip 是既有 Windows 符号链接权限覆盖，不计为通过。JUnit 和日志位于[当前 tests 目录](evidence/2026-09-12_p07_planar_final/tests/)。

首次命令包装曾因 PowerShell 拆分动态 JUnit 路径、未展开带引号 glob 而以 exit 4 结束，均无测试执行；受影响集合曾以 113 passed、3 failed 暴露测试夹具和 UI 操作选择问题，Windows `os.replace` 还出现一次 WinError 5，换新临时目录后通过。最终质量首次发现 `AutomationRouter.__init__` 61 行和 `PlanarPage` 629 行超过上下文预算；提取 Planar 基类/交互子类并压缩一行路由注释后，`scripts/check_quality.py` exit 0，Ruff、Security Ruff、format、context budget 和 mypy 120 个源码文件全部通过。日志位于[quality 目录](evidence/2026-09-12_p07_planar_final/quality/)。

## 尚未验证的边界

Generic XYZAC 只提供离线轴轨迹、限位/格式检查和回读参考。P07 已检查支撑 travel/deposition 的完整中心线段是否与目标 CAD 相交；具体控制器语义、真实机床标定、完整喷嘴体与夹具/已打印体碰撞资格、材料工艺、支撑强度与可拆卸性、热行为及现场试切仍未验证。单操作 P07 G-code 也不证明支撑与零件已按层联合编排。进入真实制造前仍需注册控制器和后处理语义、标定机床及工装，并完成碰撞复核和现场资格验证。

## 使用的 Skills

- `five-axis-workbench-development`：用于受限范围、clean-room 来源边界、共享 Toolpath、状态、六件套、UI/手册和阶段复盘门槛。
- `five-axis-slicer-validation`：用于解释器选择、Qt 串行、专项与全仓结果、skip 分类、质量门禁和证据边界。
