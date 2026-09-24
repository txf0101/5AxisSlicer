# 六个工作台开发进度台账

最近更新：2026-09-25。关联[开发计划](development_plan.md)、[产品交付计划](product_delivery_20260923.md)、[参考资料](reference_research.md)与[文档索引](../README.md)。**下方主表是任务进度的唯一维护位置**，计划和复盘引用任务编号，不另行维护一份状态表。

当前优先版本：**论文核心 AC（Paper Core AC）**。PC00—PC07 已于 2026-09-13 按 **契约/来源 → 受限 Freeform → 多材料 → 自有 AC 后处理 → Tube 收口 → 四例与双通道回归 → 本地封装** 完成受限离线验收。DOC-01 随后把使用文档整理为学习总册、五条工作台支线和参考手册，当前入口为[学习总册](../guides/user_learning_manual_zh.md)。范围和许可证依据见[论文核心说明](paper_core_ac_scope.md)，实施、失败和验收见[本轮复盘](../reviews/2026-09-13_paper_core_ac_implementation_review.md)。六工作台完整目标保留为后续路线，不作为核心版前置依赖。

Planar P01—P07、Curve C01—C05、Rotary R01—R05 保留既有离线阶段验收。PC05 已使 T04、T07、T08、T12 在受限离线范围内统一为已完成：当前 pipe2 六件套与自有 AC 回读通过，Tube 三操作的双语多尺寸证据、长 Warning、Ready/Stale/Error 展示和首页标签已收口。F01—F06 中论文需要的子集由 PC02 交付，原完整阶段仍暂缓；X01—X06、完整 I01—I04 暂缓。原编号和完成判据不删除，子集通过不自动关闭完整父阶段。当前 PC00—PC07 八项全部完成；完整路线 F/X/I 的 16 项仍暂缓，不将离线结果升级为真实控制器资格。

本表保留规划、基础、算法、工作台和整体验收任务的唯一状态。2026-09-12 的 AUD-01 已完成检查和修改方案，确认的 Planar 缺陷已在 AUD-02 和 P07 最终验收中修复。P07 以 clean-room 独立实现的 Grid/Lines 支撑首版关闭：解析悬垂真值为 33 段、61.86 mm³、66/66 回读，复杂 STEP 为 9,662/9,662 回读；9 张 Qt/OpenGL UI 图覆盖参数、正常、错误恢复和 Stale 恢复；最终 Planar 223 passed，全仓 753 passed、3 skipped、130 subtests，官方质量脚本全绿。Tree/Organic、桥接专用路径、双材料不在首版范围。Generic XYZAC 仍仅为离线参考，真实控制器语义、机床标定、完整喷嘴扫掠和现场试切未验证。

Curve C01—C05 已完成有向 STEP edge 链、弧长采样、明确法向、Buildup、Multi-pass 和 Offset 三操作及统一产品链。真实叶轮样条长 `68.27612913311773 mm`，三操作 70/210/210 点均完成六件套和回读；反向 Offset 的相邻道独立点距为 2.947—3.000 mm，正向投影塌缩会拒绝。当前 Curve/共享直接集 40 passed、2 subtests；全仓 783 passed、3 skipped、130 subtests；质量、sdist/wheel、Twine、依赖一致性和 Windows native preview smoke 已通过。Generic XYZAC 与保守 AABB 扫掠仍只提供离线资格，实机未验证。

Rotary R01—R05 已完成稳定回转轴/面/轮廓引用、非零中心、连续角展开、圆柱/圆锥 Spiral、Thin Wall 和跨零点多区域 Around Part，并接入 shared Toolpath/events、规定相位 XYZAC、整段离线检查、G93 逆时间后处理和回读。四组真实 STEP 产品均输出严格六件套并回读通过；当前 Rotary 专项 37 passed，全仓 820 passed、3 skipped、130 subtests，质量、sdist/wheel、Twine 与隔离安装导入通过。Qt 当前控件和真实 generated preview payload 的 10 张三尺寸中英证据图已归档；该截图 harness 不替代生产 VTK/OpenGL 资格。经典扇叶补充检查确认 B-spline 叶片面被拒绝、R17.5 mm 轮毂圆柱面可绑定，并把手工 XYZAC 的 180° frame 差异、三段叶片程序和长跨步风险纳入可视报告。Generic XYZAC、基体/机床精确碰撞、真实控制器语义、机床标定、现场碰撞与试切仍未验证。

本轮新增用户授权子任务 **I01-OWN**：自有机型默认配置、选择、自定义及文件导入导出；独立于 I01 的第二运动学与控制器完整验收。

用户授权子任务 **I01-AXIS** 已完成跨工作台旋转轴 G-code 输出字：内部物理关节继续使用 A/B/C 语义，客户可把实际存在的旋转关节映射为固件单字母地址。A→U、C→W 的生成、篡改回读、GUI、受限脚本、HTTP、用户库副本、项目快照、四工作台同步和 Stale 已验证；危险保留字与缺映射 fail closed。最终聚焦 122 passed、55 subtests，全仓 834 passed、3 skipped、138 subtests，质量与包检查通过。该子任务不替代 I01 规划的第二运动学，也不代表真实固件、机床标定或试切资格。

## 状态与更新规则

状态只使用：`未开始`、`进行中`、`待验证`、`已完成`、`受阻`、`历史已验收`。

- `已完成`：本行判据已满足，有本轮可核对的证据；有代码但缺验证时使用 `待验证`。
- `历史已验收`：已有代码和历史验收记录；本轮仅静态核对。它不能计作本轮测试通过。
- `受阻`：在证据列写明缺失条件、影响和已做准备；其他独立任务可继续。尚未轮到的任务保持 `未开始`。
- 每次执行先读取当前主表并检查时间戳；更新状态、证据、下一步、日期。写回前检查文件变化，保留用户新增内容。
- 一轮选一个编号任务完成。若任务过大，在原行下增加同前缀子任务，记录拆分理由与父任务验收条件，不删除原编号。
- 证据包含实际源码/提交、测试命令及结果、案例参数/输入输出指纹、复盘链接；缺项明确写出。引用相对路径，避免仅写“测试通过”。
- 阶段完成行必须依赖其所有操作任务。不能用最小流程完成替代整个工作台完成，也不能用六张首页卡片表示六工作台开发完成。
- 每个工作台阶段标记完成前，必须同步完成该模块的图文使用手册。手册应包含真实界面总览、参数、正常结果、典型错误和恢复、输出及能力边界；统一入口见[使用手册索引](../guides/README.md)。
- 不按对话次数自动增加百分比。本表由每轮实际工作更新，没有后台自动轮询、定时任务或未经核验的状态同步。

## Skill 调用记录

2026-09-12 AUD-02 收尾另实际调用 `skill-creator`，更新个人工作台开发 Skill 的制造验证经验；[归档快照](../reviews/evidence/2026-09-12_audit_fixes/skill_snapshot/)随项目提交。

实施或收尾 P/C/F/R/X/I 及后续 Tube 工作台任务时，先调用 `five-axis-workbench-development`；进入测试、Qt/VTK 回归、失败诊断或阶段验收时再调用 `five-axis-slicer-validation`。每次只登记实际加载并影响工作的 Skill，详细判断放入对应复盘。

| 日期 | 任务 | Skill | 本轮用途 | 证据 |
| --- | --- | --- | --- | --- |
| 2026-09-25 | PRODUCT-01 V2.6.2 双语教程发布检查 | `five-axis-workbench-development` | 核对 14 个中英文主题成对、教程链接与图片；清理用户教程中的内部对照过程，补充英文 Planar 支撑及 Rotary 选几何步骤，统一公开版本标识 | [教程索引](../guides/README.md)、[交付复盘](../reviews/2026-09-23_product_delivery_review.md) |
| 2026-09-25 | PRODUCT-01 NC 预览与问题归档 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`skill-creator` | 校徽曲面预览补偿 12.5 mm 刀长，完整 NC 回读路径包络恢复与 Toolpath 一致；产品化过程失效模式归入复用 Skill，并核验有效性 | [交付复盘](../reviews/2026-09-23_product_delivery_review.md)、[校徽六件套](../reviews/evidence/2026-09-24_product_delivery_ui_audit/gui_agent_logo_output/manifest.json) |
| 2026-09-24 | PRODUCT-01 导出与换姿复核 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`computer-use` | 真实校徽 GUI 暴露导出目标误选会覆盖项目，五类导出器加统一目录保护；叶轮/三叶扇诊断证实模型 Z 抬升不足以保证转台换姿安全，保留错误阻断并转向机床坐标规划 | [交付复盘](../reviews/2026-09-23_product_delivery_review.md)、[交付计划](product_delivery_20260923.md) |
| 2026-09-24 | PRODUCT-01-MC01 界面复核 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`computer-use` | 实际桌面打开三色项目、编辑换料站、验证错误高度拒绝、生成两种密度的完整扇叶并导出六件套；修复项目控制器站位丢失及 Freeform 路径被模型遮挡 | [GUI 清单](../reviews/evidence/2026-09-24_three_color_fan_gui_release/manifest.json)、[无遮挡路径图](../reviews/evidence/2026-09-24_three_color_fan_gui_release/freeform_path_visible.jpg)、[复盘](../reviews/2026-09-23_product_delivery_review.md) |
| 2026-09-24 | PRODUCT-01-MC01 多色换料 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`skill-creator` | 公共产品链完成材料分区、机床站位、换料动作与喷嘴包络检查；三色扇叶 116,893 点、两次切换、31,636 事件严格回读通过，保留实机资格限制；反例与有限根部接触边界写入工艺 Skill | [三色验收](../reviews/evidence/2026-09-24_three_color_fan_final_check/acceptance.json)、[三色路径图](../reviews/evidence/2026-09-24_three_color_fan_final_check/three_color_fan_candidate_preview.png)、[复盘](../reviews/2026-09-23_product_delivery_review.md) |
| 2026-09-23 | PRODUCT-01 启动 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`computer-use`、`plugin-management` | 读当前基线与来源，确认电脑控制可列出桌面窗口，制定真实点击与离线交付门槛；后续测试结果待逐项登记 | [交付计划](product_delivery_20260923.md) |
| 2026-09-23 | PRODUCT-01 预览与教程 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`computer-use`、`screenshot` | 真实界面生成 pipe2，修复生成路径仅含 segments 时全线预览空白、模型遮挡和语言状态残留；按当前界面抓取完整路径图；案例数值说明改为仅供练习并要求按自有设备调整 | [交付计划](product_delivery_20260923.md)、[Tube 教程](../guides/tube_workbench_zh.md)、[复盘](../reviews/2026-09-23_product_delivery_review.md) |
| 2026-09-21 | FAN15-R02/R06 长任务 | `five-axis-workbench-development`、`five-axis-slicer-validation` | 分阶段定位、逆解缓存/取消、碰撞批量筛选与失败早退；实际 208232 点重切返回底座首圈碰撞，完整图已查，未放行 NC | [修复过程](../reviews/2026-09-20_fan15_repairs.md) |
| 2026-09-21 | FAN15-R02/R06 离线 NC | `five-axis-workbench-development`、`five-axis-slicer-validation` | 按用户要求暂缓 IPW，弯管完整重切与 208232 点回读通过，温控包装/篡改回归 62 项通过，新旧 NC 图及 OFFLINE 文件已保存；其余三例和制造资格仍未完成 | [修复过程](../reviews/2026-09-20_fan15_repairs.md) |
| 2026-09-21 | FAN15-R03—R06 四例离线闭环 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`skill-creator`、`computer-use` | 校徽 76098、叶轮 681718、三叶扇 1034535 点完整 AC NC 及严格回读通过；与弯管合计四例完成真实 NC 路径图；222 passed/28 subtests，Ruff/Mypy 通过；新经验写入 Skill。Computer Use 重置后仍无法读取应用清单，本轮真实点击复验受阻 | [修复过程](../reviews/2026-09-20_fan15_repairs.md) |
| 2026-09-21 | FAN11/FP01 产品化复核 | `five-axis-workbench-development`、`five-axis-slicer-validation` | 核对新增三类填充只由 finalizer 调用，确认尚未进入 Freeform 公共操作契约、GUI和三入口；建立 FP01—FP06 计划与教程素材，禁止把离线脚本验收描述成界面产品完成 | [产品化计划](fan15_productization_plan.md)、[方法说明](../guides/fan15_solid_fill_method_notes.md) |
| 2026-09-21 | FAN11/FP01—FP05 续做 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`computer-use`、`skill-creator` | 三种实体进入公共 Freeform 操作与产品链；修复实体项目加载分派与测试夹具 Setup ID，真实 GUI 校徽重开、生成 76098 点并导出六件套严格回读；大结果状态清单改摘要；其余界面和跨工作台作业仍未验收 | [产品化计划](fan15_productization_plan.md)、[修复过程](../reviews/2026-09-20_fan15_repairs.md) |
| 2026-09-21 | FAN15-R06 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`computer-use` | 原生文件加载、四角色鼠标拾取、内圆失败与外圆重试；修复拾取入口/失败详情，长生成响应继续排查 | [修复过程](../reviews/2026-09-20_fan15_repairs.md) |
| 2026-09-21 | FAN15-R03 | `five-axis-workbench-development`、`five-axis-slicer-validation` | 完整球面实体截交、孔与度量，37 实体/111 截层恢复；仅层域，待有限道宽及 NC | [修复过程](../reviews/2026-09-20_fan15_repairs.md) |
| 2026-09-21 | FAN15-R02 | `five-axis-workbench-development`、`five-axis-slicer-validation` | 自动底座从包围盒圆盘替换为共享 CAD 截层/填充；带孔矩形反例和产品入口验证；四例仍未完成整件验收 | [修复过程](../reviews/2026-09-20_fan15_repairs.md) |
| 2026-09-20 | FAN15-R01/R02 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`computer-use` | 公共材料并集、偏置失败传播、薄环偏置、轴向喷嘴修复与真实工作台点击；逐项继续 | [执行计划](fan15_repair_execution.md)、[修复过程](../reviews/2026-09-20_fan15_repairs.md) |
| 2026-09-20 | FAN15四例核查 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`skill-creator` | 重跑Tube两模式、Freeform粗细采样、四例全高Planar诊断及旧NC对照；保留覆盖缺失、未知轴语义与多实体面积失败，并写入Skill | [四例审查](../reviews/2026-09-20_fan15_example_acceptance.md) |
| 2026-09-20 | FAN旧NC完整图 | `five-axis-slicer-validation` | 复用MATLAB既有脚本读取全部旧NC并还原中心柱/三叶；不以参考图替代新算法验收 | [参考图记录](../reviews/2026-09-20_fan_radial_correction.md#旧代码完整参考图重新输出) |
| 2026-09-20 | FAN工艺教训固化 | `skill-creator`、`five-axis-workbench-development`、`five-axis-slicer-validation` | 将基底、生长方向、逐层承接及轴联动设为开发/验收前置条件；两项Skill结构校验通过；复核并展示现有局部路径图，未恢复FAN04/FAN07资格 | [纠正复盘：Skill固化](../reviews/2026-09-20_fan_radial_correction.md#skill固化与本次图片复核) |
| 2026-09-20 | FAN02/FAN04/FAN07纠正 | `five-axis-workbench-development`、`five-axis-slicer-validation` | 旧NC模态解析、撤回错误验收、柱面起印解析与拒绝测试、研发资格隔离 | [纠正复盘](../reviews/2026-09-20_fan_radial_correction.md) |
| 2026-09-20 | FAN01—FAN05 | `five-axis-workbench-development`、`five-axis-slicer-validation` | 落地制造契约、旧NC/CAD基线、作业DAG、A=90°全体积层域审计和公共壳层/填充；真实STEP与248项领域回归验证 | [实施复盘](../reviews/2026-09-20_fan_complete_program_fan01_fan05_review.md)、[证据](../reviews/evidence/2026-09-20_fan_complete_program/validation_manifest.json) |
| 2026-09-20 | FAN00 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`computer-use` | 规划完整扇叶填充、90°换姿、总程序和真实点击；六仓库核对；未启动实施 | [计划](fan_complete_program_plan.md)、[研究](fan_complete_program_research.md)、[复盘](../reviews/2026-09-20_fan_complete_program_planning_review.md) |
| 2026-09-20 | SIM00 | `five-axis-workbench-development` | 核对现有timeline、MachineAxisTrajectory和VTK基础；调研Vismach、FreeCAD、CAMotics、PyBullet、VTK/FFmpeg；制定SIM01—SIM10计划和独立台账 | [调研](motion_simulation_research.md)、[计划](motion_simulation_plan.md)、[独立台账](motion_simulation_tracker.md)、[复盘](../reviews/2026-09-20_motion_simulation_planning_review.md) |
| 2026-09-20 | EXAMPLE-PLA-01 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`documents` | 读取论文参数；按 0.4 mm 喷嘴和单材料 PLA 重新生成半球、扇叶、叶轮、pipe2 的自有 AC 离线代码并严格回读；拒绝为缺少受限五轴流程的三叶扇和仅有 STL 的 pipe 伪造输出 | [生成复盘](../reviews/2026-09-20_example_pla_gcode_generation_review.md)；[参数与指纹清单](../../example/本软件五轴PLA切片_20260920.json) |
| 2026-09-14 | CI-QUALITY | `five-axis-slicer-validation`、`gh-fix-ci` | 读取 Actions `34758493547` 三个失败任务的原始日志；确认 Node.js 提示不致命，修复 Freeform 的 PyQt 类型枚举访问并保留静态门禁；安装官方 GitHub CLI 以跟踪后续运行 | [CI 与分支复盘](../reviews/2026-09-13_ci_branch_consolidation_review.md)；质量检查 162 个源码文件通过，13 文件领域集 161 passed、2 skipped、89 subtests，论文核心 9 passed；Actions `34770465207` 四项全部通过 |
| 2026-09-13 | DOC-01 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`computer-use` | 把案例平铺手册重组为 L01—L09 公共课程、W01—W05 工作台支线和参考手册；核对 IDE/PWSH 启动、链接、图片、错误恢复与迁移学习；Computer Use 三次均因 `nodeRepl.fetch request failed` 无法枚举 Windows 窗口 | [学习总册](../guides/user_learning_manual_zh.md)、[本轮复盘](../reviews/2026-09-13_user_learning_manual_reorganization.md) |
| 2026-09-13 | PC01—PC07 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`artifact-package-verify`、`computer-use` | 完成受限 Freeform、显式多材料、自有 AC 离线后处理、Tube 收口、五产品证据、严格回读、串行 Qt/全仓、质量/构建/原生 wheel/隔离安装和显式清单 ZIP；Computer Use 在应用启动后仍无法枚举 Windows 窗口，不将其冒充为真人桌面操作通过 | [实施复盘](../reviews/2026-09-13_paper_core_ac_implementation_review.md)、[验证清单](../reviews/evidence/2026-09-13_paper_core_ac/validation_manifest.json) |
| 2026-09-13 | CI-BRANCH | `five-axis-slicer-validation`、`gh-fix-ci` | 核对默认分支和全部分支祖先关系；读取 Actions 原始日志；用隔离 Python 3.12 环境修复 runner 预装包、CasADi/PyQt/mypy 漂移、Linux 平台存根和托管 VTK 崩溃边界 | [CI 与分支复盘](../reviews/2026-09-13_ci_branch_consolidation_review.md)；干净环境质量通过，13文件领域集161 passed、2 skipped、89 subtests；Actions `34747228928` 四项全部通过 |
| 2026-09-13 | AUD-02-TUBE、T04/T07、PC05子项 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`artifact-package-verify` | 原反例复核；修复末层材料、固定方向姿态和IPW性能；独立体积/候选对照、串行Qt/全仓、六件套压缩逐文件核验；区分缺陷关闭与整阶段验收 | [同一AUD-02复盘](../reviews/2026-09-12_algorithm_audit_fixes.md)、[当前证据](../reviews/evidence/2026-09-13_tube_recheck/validation_manifest.json) |
| 2026-09-13 | PC00 | `five-axis-workbench-development` | 按阶段门重排论文核心范围；批判性核对论文/当前代码、固定开源版本与许可；保留原阶段资格和延期范围 | [核心范围/研究](paper_core_ac_scope.md)、[复盘](../reviews/2026-09-13_paper_core_ac_planning_review.md)；本轮仅文档检查，未运行产品测试 |
| 2026-09-13 | I01-AXIS | `five-axis-workbench-development`、`five-axis-slicer-validation` | 按共享机型/后处理契约分离内部关节与控制器地址；复用已验证解释器、Qt 串行、WinError 5 诊断、JUnit、质量和构建规则 | [实施复盘](../reviews/2026-09-13_custom_rotary_axis_words_review.md)；[验证清单](../reviews/evidence/2026-09-13_custom_rotary_axis_words/validation_manifest.json) |
| 2026-09-13 | R01—R05 | `five-axis-workbench-development` | 按阶段门完成资料边界、稳定几何引用、三操作、共享产品链、双语 UI、手册和证据归档 | [Rotary 复盘](../reviews/2026-09-13_rotary_workbench_review.md) |
| 2026-09-13 | R01—R05/R05 验收 | `five-axis-slicer-validation` | 复用指定解释器、仓库内 basetemp、串行 Qt/全仓、WinError 5 分类、质量、构建和指纹规则 | [Rotary 最终证据](../reviews/evidence/2026-09-13_rotary_workbench_final/validation_manifest.json) |
| 2026-09-13 | R05 图文补充/pipe2 对比 | `five-axis-workbench-development`、`technical-evidence-report`、`visualize`、`computer-use` | 用当前 STEP/G-code 独立量测解释固定轴 Rotary 与弯管 Tube 的差异；补生产 `RotaryPage` + `ModelViewer` 截图。Computer Use 未枚举到 Qt 窗口，截图改由 Qt 自身捕获并在清单中明示 | [Rotary 手册](../guides/rotary_workbench_zh.md)；[pipe2 对比报告](../reviews/2026-09-13_pipe2_model_manual_gcode_comparison.md) |
| 2026-09-13 | R05 扇叶补充检查 | `five-axis-workbench-development`、`five-axis-slicer-validation`、`technical-evidence-report`、`visualize`、`computer-use` | 对经典扇叶 STEP 与手工 XYZAC 做独立流式解析、180° frame 可视对齐和叶片/轮毂选面测试；Computer Use 与生产 VTK 截图均受当前执行环境限制，替代图和限制已逐图标注 | [pipe2 与扇叶对比报告](../reviews/2026-09-13_pipe2_model_manual_gcode_comparison.md)；[机器可读证据](../reviews/evidence/2026-09-13_pipe2_manual_comparison/fan_blade_analysis.json) |
| 2026-09-12 | I01-OWN | `five-axis-workbench-development`、`five-axis-slicer-validation` | 自有机型接入、默认值、用户库、保存重开、双语 UI 与相关验证 | [本轮复盘](../reviews/2026-09-12_own_printer_profile_review.md) |
| 2026-09-11 | DOC-SKILL | `skill-creator` | 把 Tube T01—T12 方法提炼为可发现、可校验的个人 Skill | [Skill 建立复盘](../reviews/2026-09-11_workbench_development_skill_review.md) |
| 2026-09-11 | DOC-SKILL | `five-axis-workbench-development` | 自检开发闭环、阶段门槛和调用登记规则；尚未启动 P01 | [Skill 建立复盘](../reviews/2026-09-11_workbench_development_skill_review.md) |
| 2026-09-11 | DOC-SKILL | `five-axis-slicer-validation` | 划分开发与验证职责，并采用“纯 Skill/文档修改不跑全仓”的验证边界 | [Skill 建立复盘](../reviews/2026-09-11_workbench_development_skill_review.md) |
| 2026-09-12 | P01 | `five-axis-workbench-development` | Planar 区域/层截面与后续操作原型的受限范围、来源和共享 Toolpath 边界 | [P01—P06 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md) |
| 2026-09-12 | P01 | `five-axis-slicer-validation` | 已核验解释器预检、Planar 专项测试和质量门禁 | [P01—P06 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md) |
| 2026-09-12 | P01 | `five-axis-workbench-development` | 更新唯一台账并编制给后续执行者的范围、顺序和验收交接说明 | [Planar 交接说明](planar_handoff.md) |
| 2026-09-12 | P01 | `five-axis-slicer-validation` | 交接说明固化已验证解释器、预检、Qt 串行和测试停止条件 | [Planar 交接说明](planar_handoff.md) |
| 2026-09-12 | P01 | `five-axis-workbench-development` | 完成稳定引用、Build CS 截层、状态、命令、保存和最小 Qt 预览闭环 | [P01 正式证据](../reviews/evidence/2026-09-12_p01_planar/manifest.json) |
| 2026-09-12 | P01 | `five-axis-slicer-validation` | 处理 pytest 临时目录权限分支，执行串行专项与质量门禁 | [P01 正式证据](../reviews/evidence/2026-09-12_p01_planar/manifest.json) |
| 2026-09-12 | P02 | `five-axis-workbench-development` | 按阶段门槛接入 perimeter-first Zigzag、共享 Toolpath、产品状态、G-code 回读和六件套 | [P02 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p02-zigzag-fill-产品接入与关闭) |
| 2026-09-12 | P02 | `five-axis-slicer-validation` | 使用项目内独立 pytest 临时目录执行专项、全仓串行回归和质量门禁 | [P02 证据](../reviews/evidence/2026-09-12_p02_planar/manifest.json) |
| 2026-09-12 | P02 补充验收 | `five-axis-workbench-development` | 接入独立 Planar 三维查看器，修复操作类型和窄屏按钮布局，补真实 STEP 图文手册 | [Planar 手册](../guides/planar_workbench_zh.md) |
| 2026-09-12 | P02 补充验收 | `five-axis-slicer-validation` | 用三叶扇 STEP 核验 399 点路径、六件套和回读，并完成三尺寸中英 Qt/OpenGL 截图、44 项专项与当前全仓回归 | [P02 证据](../reviews/evidence/2026-09-12_p02_planar/manifest.json) |
| 2026-09-12 | PLAN-R-ORDER | `five-axis-workbench-development` | 核对工作台复用关系，将 Rotary R01—R05 调整到 Curve C05 后、Freeform 前；不改变任务状态或验收门槛 | [计划变更记录](#计划变更记录) |
| 2026-09-12 | P03 | `five-axis-workbench-development` | 用 OCCT 完成孔、凹区、多岛、窄颈分裂和消失区的多轮偏置，并接入共享 Toolpath、产品状态与六件套 | [P03 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p03-offset-fill-产品接入与关闭) |
| 2026-09-12 | P03 | `five-axis-slicer-validation` | 核对自交失败顺序与高密度截面性能，执行 12 项阶段测试并保留 JUnit | [P03 证据](../reviews/evidence/2026-09-12_p03_planar/manifest.json) |
| 2026-09-12 | P04 | `five-axis-workbench-development` | 完成开放壁、闭壁、区域驱动多道和统一不足道宽 reduce 策略，并接入产品链 | [P04 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p04-thin-wall-产品接入与关闭) |
| 2026-09-12 | P04 | `five-axis-slicer-validation` | 核对单/多道、闭合、多道数量、Stale 与可见 Warning，执行 7 项阶段测试 | [P04 证据](../reviews/evidence/2026-09-12_p04_planar/manifest.json) |
| 2026-09-12 | P05 | `five-axis-workbench-development` | 完成受限单岛无孔连续 Z 螺旋、弧长重采样、实体内插值检查和独立体积核对 | [P05 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p05-spiral-产品接入与关闭) |
| 2026-09-12 | P05 | `five-axis-slicer-validation` | 定位连续 Z 被离散层量测误报的问题，执行 10 项阶段测试并保留 JUnit | [P05 证据](../reviews/evidence/2026-09-12_p05_planar/manifest.json) |
| 2026-09-12 | P06 | `five-axis-workbench-development` | 完成四操作产品闭环、参数入口、真实 STEP 输出、双语图文手册和阶段边界归档 | [P06 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p06-planar-工作台阶段验收与关闭) |
| 2026-09-12 | P06 | `five-axis-slicer-validation` | 串行执行 77 项平面专项、全仓回归和质量门禁，并核对三尺寸中英 UI、错误恢复与导出状态 | [P06 证据](../reviews/evidence/2026-09-12_p06_planar/manifest.json) |
| 2026-09-12 | P07 | `five-axis-workbench-development` | 按公开行为独立实现平面 Grid/Lines 支撑，复用区域、共享 Toolpath、产品状态、输出与手册闭环 | [P07 任务行](#主表) |
| 2026-09-12 | P07 | `five-axis-slicer-validation` | 复用已核验解释器、Qt 串行、失败分类和证据归档规则 | [P07 任务行](#主表) |
| 2026-09-12 | P07/Planar 最终验收 | `five-axis-workbench-development`、`five-axis-slicer-validation` | 收敛统一命令、取消/撤销/重开、主体/interface Viewer、独立真值、真实 STEP、当前 UI、全仓与质量门禁 | [最终证据](../reviews/evidence/2026-09-12_p07_planar_final/manifest.json) |
| 2026-09-12 | C01—C05 | `five-axis-workbench-development` | 按阶段门实现稳定有向引用、三种 Curve 操作、共享产品链、统一命令、项目生命周期、双语 UI 和图文手册 | [Curve 复盘](../reviews/2026-09-12_curve_workbench_review.md) |
| 2026-09-12 | C01—C05/C05 验收 | `five-axis-slicer-validation` | 只读 preflight、唯一 basetemp、失败诊断、Qt/共享/全仓串行回归、质量、构建和证据归档 | [Curve 最终证据](../reviews/evidence/2026-09-12_curve_workbench_final/validation_manifest.json) |
| 2026-09-12 | DOC-MULTICHAT | `five-axis-workbench-development` | 编制 P07、C、R、F、X 与 I 阶段的多对话启动提示词，统一完整工作台、验证、图文手册和分支交接门槛；未启动新开发任务 | [启动提示词](workbench_multi_chat_prompts.md)与[编制复盘](../reviews/2026-09-12_multi_chat_workbench_prompt_review.md) |

| 2026-09-12 | AUD-01 | `five-axis-workbench-development` | 独立真值、真实模型、生成/回读与阶段资格审查；GPT-6 子 Agent 复核 Tube 和支撑，只出方案 | [独立审查](../reviews/2026-09-12_project_algorithm_audit.md) |
| 2026-09-12 | AUD-01 | `five-axis-slicer-validation` | 只读预检、串行回归、固定源码复测、P07 并行修改分类、Qt/OpenGL 图像和证据指纹 | [审查证据](../reviews/evidence/2026-09-12_project_audit/manifest.json) |

| 2026-09-12 | AUD-02 | `five-axis-workbench-development`、`five-axis-slicer-validation` | 按已批准方案修复坐标/状态/NC/截层/道宽/运动缺陷，GPT-6 子 Agent 并行领域验证，Qt 与全仓串行 | [修复方案](2026-09-12_algorithm_audit_fix_plan.md)；[证据目录](../reviews/evidence/2026-09-12_audit_fixes/) |
| 2026-09-20 | FAN06—FAN07 | `five-axis-workbench-development` | 接入全高轮毂、20%填充、支撑逐层调度、A=90° 单叶片完整填充，并将 Indexed Build 叶片路径映射回公共装配 Build 预览 | [阶段复盘](../reviews/2026-09-20_fan_complete_program_fan06_fan07_review.md) |
| 2026-09-20 | FAN06—FAN07 | `five-axis-slicer-validation` | 复用项目解释器和仓库内 basetemp，执行真实模型证据、坐标相关专项、合并路径图人工检查、质量门与文件指纹 | [证据目录](../reviews/evidence/2026-09-20_fan_complete_program/fan06_fan07/) |

## 主表

| 编号 | 阶段与交付 | 依赖 | 状态 | 完成判据 | 证据或阻塞 | 下一步 | 更新日期 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PRODUCT-01 | 离线产品交付闭环 | FAN11/FP01—FP06、现有五工作台 | 进行中 | 首次使用和四例真实点击：加载、Setup、选几何、生成/取消、预览、六件套导出、严格回读、保存重开；界面和图文教程完成 | pipe2 已真实点击生成、全线预览、六件套导出并严格回读 140,644 点；三色扇叶 GUI 回读 116,852 点通过；校徽 GUI 完整 NC 回读通过，预览刀长纠正后曲面半径 33.7384 mm 小于基体 39.7998 mm；叶轮八片[离线完整程序](../reviews/evidence/2026-09-24_product_delivery_ui_audit/impeller_root_growth_offline/acceptance.json)183,342 点、16,983 事件严格回读通过，尚未完成 GUI 全链。工作台作用域、选边、材料表、阶段预览和方向标已做 UI 定向复核；[复盘](../reviews/2026-09-23_product_delivery_review.md)。其余首次使用/窄窗与实机参数仍待复核 | 日常以弯管、校徽、叶轮为主；三叶扇按相关变更和最终门槛运行；继续核对 GUI 导出与教程 | 2026-09-25 |
| PRODUCT-01-MC01 | 五轴安全换姿与多色换料 | PRODUCT-01、Freeform 实体路径 | 进行中 | 配置换料站、三色 PLA 叶片分区；生成切断/退丝/进丝/排料/擦嘴/返回的完整 NC，避开已沉积材料，严格回读通过；无站位或无安全路线阻止导出 | 三色材料切换的受限离线链和 GUI 已通过：[GUI NC](../reviews/evidence/2026-09-24_three_color_fan_gui_release/manifest.json) 116,852 点、T0/T1/T2、两次切换、31,636 事件严格回读。叶轮原首道换姿碰撞已由机床坐标候选路线和同体安全空移处理；[完整离线程序](../reviews/evidence/2026-09-24_product_delivery_ui_audit/impeller_root_growth_offline/acceptance.json)183,342 点严格回读、无碰撞 Error。实机喷嘴/夹具、切刀宏和传感器尚未标定，`machine_executable=false` | 用现有结果做界面预览与重开验证，实机资格另行核准 | 2026-09-25 |
| FAN00 | 规划与项目调研 | 用户计划授权 | 已完成 | 详细计划、六仓库研究、电脑验收方案齐全 | [任务设计与边界](fan_complete_program_plan.md)；[研究](fan_complete_program_research.md)，仅规划完成 | FAN01 | 2026-09-20 |
| FAN01 | 输入与制造契约 | FAN00 | 已完成 | 参数来源、实体角色、坐标、姿态及误差阈值冻结 | [契约JSON](../reviews/evidence/2026-09-20_fan_complete_program/fan_contract_v1.json)；机床包络、零点、宏版本保持实机资格待测 | FAN02 | 2026-09-20 |
| FAN02 | 旧NC和CAD独立基线 | FAN01 | 重新核查中 | 分工序模态解析、径向层序、坐标注册与填充覆盖 | [模态运动统计](../reviews/evidence/2026-09-20_fan_complete_program/radial_correction/legacy_motion.json)：叶片A90、C连续联动；原全文件TYPE统计不能证明叶片内部填充 | FAN04纠正 | 2026-09-20 |
| FAN03 | 作业依赖和状态模型 | FAN01 | 已完成 | 序列化、依赖图、Stale、取消、程序索引 | [作业JSON](../reviews/evidence/2026-09-20_fan_complete_program/fan_job_v1.json)；循环/缺依赖、下游失效、JSON和取消事务已测；G-code行号索引属FAN10 | FAN06 | 2026-09-20 |
| FAN04 | 全体积层域和90°可行性 | FAN01,FAN02 | 撤回原验收，修正中 | 柱面起印、径向曲层、层间承接、AC联动与独立FK | 原固定A平面截层只证明几何积分，不符合绕轴生长；[纠正复盘](../reviews/2026-09-20_fan_radial_correction.md) | 曲层域与承接验证 | 2026-09-20 |
| FAN05 | 公共壳层和内部填充 | FAN01,FAN02 | 待验证 | 带孔/多岛/窄缝、顶底层、0/20/100%矩阵 | [历史248项回归](../reviews/evidence/2026-09-20_fan_complete_program/pytest_fan01_fan05_final_retry.xml)保留；FAN15发现偏置异常吞并、原边界回退及多实体嵌套误判孔，[原完整资格撤回](../reviews/2026-09-20_fan15_example_acceptance.md) | 修复反例后重新验收 | 2026-09-20 |
| FAN06 | 全高底座和支撑联合调度 | FAN03,FAN05 | 已完成 | 全部层、孔和接口保留，支撑逐层排序 | [真实模型统计与路径图](../reviews/evidence/2026-09-20_fan_complete_program/fan06_fan07/fan06_fan07_summary.json)：325/325层有实体路径，309层支撑，零支撑诊断；图示按层抽样，完整统计未抽样 | FAN09 | 2026-09-20 |
| FAN07 | 单叶片完整Freeform填充 | FAN04,FAN05 | 撤回原验收，修正中 | 真实曲层填充、叶根和逐层承接、材料覆盖、非穿透路径 | 旧平面生成入口已拒绝继续生成；径向替代仅研发预览，G2撤回；[纠正复盘](../reviews/2026-09-20_fan_radial_correction.md) | 修复并验证后才进入FAN08 | 2026-09-20 |
| FAN08 | 三叶片推广与接口归属 | FAN07 | 实施中，未验收 | 三份稳定引用、无漏片、无重复体积 | [三实体独立生成](../reviews/evidence/2026-09-20_fan_complete_program/radial_repair_full/summary.json)：各329径向层，六对体积交集为零，叶根间隙近零；沉积覆盖与承接未关闭 | 完成FAN07物理覆盖后验收 | 2026-09-20 |
| FAN09 | 换姿与已打印体碰撞 | FAN06,FAN08 | 部分实现，未验收 | 90°转位和跨叶片全段验证、Z20方向与扫掠 | `fan/transitions.py`：外绕候选和线段/球形尖端距离；穿柱及先打印叶片障碍反例已测；完整喷头与机器插补扫掠未接通 | 整件轨迹及换姿扫掠 | 2026-09-20 |
| FAN10 | 统一后处理和总程序回读 | FAN03,FAN09 | 部分实现，未验收 | 全局C、E/F/模式、起止温控、事件及行号映射 | `postprocessing/fan_merge.py`：结构化合并、事件偏移、来源和NC行号索引；夹具全局IK/回读及模态篡改拒绝通过，真实整件总NC未生成 | FAN09后联调整件及温控 | 2026-09-20 |
| FAN11 | 作业GUI和三入口持久化 | FAN10 | 实施中 | GUI/脚本/HTTP共核、后台取消、重开和依赖失效 | 三类实体已入公共 Freeform 命令与产品链，真实校徽界面生成通过；跨工作台依赖和长任务响应仍缺；[产品化计划](fan15_productization_plan.md) | FP03 作业组合和 FP04 交互拾取 | 2026-09-21 |
| FAN12 | 电脑真实用户点击验收 | FAN11 | 部分执行 | UI01—UI12、双语三尺寸、GUI生成文件hash | 弯管四角色拾取及校徽真实加载/重开/生成/导出已见证，校徽 NC SHA256 见[复盘](../reviews/2026-09-20_fan15_repairs.md)；叶轮、三叶扇及双语尺寸矩阵未通过 | 完成其余真实点击矩阵 | 2026-09-21 |
| FAN13 | 独立全件与长程序回归 | FAN10,FAN12 | 未开始 | 覆盖/材料/姿态/收敛、新旧对照和百万级负载 | [任务设计与边界](fan_complete_program_plan.md)；尚无实施证据 | FAN14 | 2026-09-20 |
| FAN14 | 完整扇叶交付与封装 | FAN13 | 未开始 | 总NC、项目、产品和索引、报告手册及相关回归 | [任务设计与边界](fan_complete_program_plan.md)；尚无实施证据 | FAN15 | 2026-09-20 |
| FAN15 | 其他示例逐件迁移 | FAN14 | 四例离线 NC 已验收；产品化回迁中 | 叶轮/管件/半球/三叶扇逐例子项和判据 | [四例审查](../reviews/2026-09-20_fan15_example_acceptance.md)；[修复过程](../reviews/2026-09-20_fan15_repairs.md)。四例 OFFLINE NC 通过；三类实体公共链重切并回读，校徽 GUI 六件套通过；跨工作台作业和余下界面未验收 | 按 FP03—FP06 完整验收；实机/IPW 单列 | 2026-09-21 |
| AUD-01 | 跨工作台独立审查与修改方案 | 当前工作区与项目示例 | 已完成 | 文档/实现核对、真实模型、独立反例、证据和待实施方案齐全 | [审查报告](../reviews/2026-09-12_project_algorithm_audit.md)；[修改方案](2026-09-12_algorithm_audit_fix_plan.md)；本轮未修改产品代码 | 用户确认方案后实施；P07 并行工作保留 | 2026-09-12 |
| AUD-02 | 跨工作台缺陷修复与重新验证 | AUD-01 | 已完成 | 原始反例拒绝、正确解析/真实模型通过、旧资格失效、全仓与图文证据齐全 | [修改方案](2026-09-12_algorithm_audit_fix_plan.md)；[本轮证据](../reviews/evidence/2026-09-12_audit_fixes/) | [修复复盘](../reviews/2026-09-12_algorithm_audit_fixes.md)；窄壁实心、自适应道宽、联合调度和实机资格保留 | 2026-09-12 |
| AUD-02-TUBE | Tube 原缺陷复核与本轮发现修复 | AUD-02、用户本轮授权 | 已完成 | 原坐标/Stale/碰撞漏接/弦高/NC反例；末层体积与固定姿态；真实pipe2当前生成/碰撞/回读；失败与回归归档 | [同一复盘](../reviews/2026-09-12_algorithm_audit_fixes.md)；839 passed、3 skipped、141 subtests，质量通过；pipe2 15479/15479回读，六件套ZIP逐文件核验 | T04/T07恢复受限离线资格；T08/T12保留实际界面与整阶段门，实机未验证 | 2026-09-13 |
| PC00 | 论文批判性审查、核心范围和复用研究 | 用户本轮授权、当前源码与论文存档 | 已完成 | 四例能力差距、论文与代码冲突、候选代码/许可证、延期范围及依赖可核对 | [范围/研究](paper_core_ac_scope.md)、[复盘](../reviews/2026-09-13_paper_core_ac_planning_review.md)；原件/存档 SHA 一致，7个候选项目固定 commit；未执行上游或实验 | PC01；本行完成不表示论文实验主张全部核实 | 2026-09-13 |
| PC01 | 四例输入、材料、控制器与独立真值契约 | PC00 | 已完成 | CAD/选择/材料区域/历史NC/宏/标定来源、frame、E/F模式、几何容差、失败矩阵冻结；论文差异逐项定论或列未知 | [人读契约](paper_core_input_contract.md)与[机器契约](paper_core_input_contract.json)；半球 CAD/NC 本机资产指纹已核对，再分发许可仍未知 | PC02—PC07已完成；保留宏版本、标定与现场参数未知项 | 2026-09-13 |
| PC02 | 论文所需受限 Freeform 核心 | PC01 | 已完成 | 单修剪面/有限连续面组与边界/导引线；贴面、薄壁、有限多层；三维道距/trim/周期/法向/投影多解/覆盖和事件；三入口、取消、Stale、重开 | [实施复盘](../reviews/2026-09-13_paper_core_ac_implementation_review.md)与[产品清单](../reviews/evidence/2026-09-13_paper_core_ac/validation_manifest.json)；最多16面/32导引线，trim越界反例保留 | 只关闭论文子集；通用 F01—F06 仍按原判据暂缓 | 2026-09-13 |
| PC03 | 预定义材料区域与四通道事件链 | PC01,PC02 | 已完成 | material_id/channel_id、准备暂停、switch/cut/retract/park/load/温控等待/purge/prime/resume；hash/Stale/撤销/重开；传感/温控失败阻断与恢复 | [多材料指南](../guides/material_channels_zh.md)；五个产品包含 T0—T3 选择和分口径统计，双通道事件链及传感/温控失败恢复有直接测试 | 显式区域完成；自动材料分区/优化不在范围 | 2026-09-13 |
| PC04 | 自有 AC 控制器后处理封装 | PC01,PC03,I01-OWN,I01-AXIS | 已完成 | 真实机型/宏版本、A±180°/C±360°按来源确认；累计C、工具长度、IK/FK、轴限/动态/扫掠；E/F模式、两种20mm动作、宏展开/模式恢复和严格回读 | [控制器指南](../guides/paper_core_ac_controller_zh.md)；G90/M83/G94、Indexed绝对Z20、材料park相对Z+20、宏展开、完整命令回读和累计C门禁通过 | 离线注册完成；控制器/宏版本、协调XYZAC和累计C上限未知，`machine_executable=false` | 2026-09-13 |
| PC05 | Tube 论文案例收口与状态统一 | PC04,AUD-02 | 已完成 | 自有AC真实pipe2几何/体积/覆盖/运动/回读；逐项决定T04/T07/T08/T12资格；README与中英首页标签一致 | pipe2 1,591点，原六件套与自有AC 25/25事件严格回读；三操作双语多尺寸证据无截断/碰撞；笔记本尺寸顶部动作重叠已修复 | T04/T07/T08/T12均关闭到受限离线资格；实机限制不变 | 2026-09-13 |
| PC06 | 四论文案例及多材料完整回归 | PC02,PC03,PC04,PC05 | 已完成 | 当前CAD生成四例六件套并严格回读；增加预装双通道案例；独立法向/道距/体积/AC连续/材料切换/NC差异；三入口、project I/O、真实Viewer、双语三尺寸 | [验证清单](../reviews/evidence/2026-09-13_paper_core_ac/validation_manifest.json)：半球7路径30点、扇叶3路径123点、叶轮16路径384点、pipe2 1,591点、双通道48点；五套六件套和四项目重开通过 | 生产VTK/OpenGL截图受无显示会话限制；Qt证据绘制器不冒充生产Viewer资格 | 2026-09-13 |
| PC07 | 论文核心 AC 本地封装与交付 | PC06 | 已完成 | 范围内最终pytest/质量/包检查/干净环境启动；4例项目、指南/截图、许可通知、证据索引；论文声明与验证边界一致 | 57 passed/6 subtests 联合回归；全仓 856 passed、3 skipped、141 subtests；质量门 162 源码无问题；wheel/sdist、Twine、原生wheel及包隔离安装/命令入口通过；[实施复盘](../reviews/2026-09-13_paper_core_ac_implementation_review.md) | 已本地封装；隔离环境继承已验证依赖，不声称完全无缓存干净安装；实机资格单列 | 2026-09-13 |
| DOC-01 | 学习手册总册与教程矩阵 | PC07 | 已完成 | 开篇明确 IDE/PWSH 启动；课程按通用能力、工作台支线、自检、错误恢复和迁移到自有零件组织；案例只作为练习 | [学习总册](../guides/user_learning_manual_zh.md)、[手册中心](../guides/README.md)、[复盘](../reviews/2026-09-13_user_learning_manual_reorganization.md)；11个相关Markdown链接通过，10图可读取，入口帮助和PS1语法通过 | 作为当前用户手册入口；后续 UI/参数变化时同步更新，印刷版按需单向生成 | 2026-09-13 |
| Q00 | 资料检索、计划与台账 | 无 | 已完成 | 六入口、20 操作、依赖与验收完整；来源、链接和台账一致 | [本轮复盘](../reviews/2026-09-10_six_workbench_plan_review.md)；51 行、20 操作、59 链接及依赖检查通过 | A01—A03 已完成；按台账进入 T01 | 2026-09-11 |
| B01 | 既有 STEP、选择与 NC 预览 | 无 | 已完成 | 已有导入、拓扑选择和路径预览可复用 | [本轮验收](../reviews/2026-09-11_b01_b03_acceptance_review.md)；真实 STEP、四级选择、NC 解析与坐标回退、VTK 离屏通过；全仓 402 passed、3 skipped | T01 复用已核验环境、输入指纹与预览入口 | 2026-09-11 |
| B02 | Tube Setup 与坐标闭环 | B01 | 已完成 | Part、资源、Model/Build CS、Placement、项目重开 | [本轮验收](../reviews/2026-09-11_b01_b03_acceptance_review.md)；pipe2 GUI 达到 Ready，坐标/装夹、资源与保存重开通过；符号链接权限边界单列 | T01 接入几何节点时回归 | 2026-09-11 |
| B03 | 受限脚本、YAML 与命令事务 | B02 | 已完成 | GUI/脚本/HTTP 共享提交、撤销与冲突恢复 | [本轮验收](../reviews/2026-09-11_b01_b03_acceptance_review.md)；pipe2 脚本与 YAML 重开、三入口修订、undo/redo、冲突恢复通过；[报告与指纹](../reviews/evidence/2026-09-11_b01_b03/manifest.json) | 新命令沿用该入口；多操作时扩展格式 | 2026-09-11 |
| A01 | 管状算法基线与契约 | Q00 | 已完成 | 记录环境、支持机型、输入角色、数值容差、阶段数据与生成验收方案 | [A01-A03 契约](tube_algorithm_contract.md)；[正式验收](../reviews/2026-09-11_a01_a03_contract_review.md)；只读预检通过；外部资料使用规则已列入 | T01 使用该契约接入管体/入口/出口/基体角色 | 2026-09-11 |
| A02 | 案例来源与独立真值 | A01 | 已完成 | 建立逐文件来源表；pipe2 哈希、角色与解析直管/圆弧管真值可追溯 | [样例来源登记](example_source_inventory.md)；解析真值夹具已登记并由测试复核公式；未知来源单列 | T01 绑定 pipe2 角色；T02 由已登记真值生成 STEP 并核对识别误差 | 2026-09-11 |
| A03 | 通用路径、事件和结果契约 | A01 | 已完成 | 位置/姿态/层/区段/挤出事件、来源、哈希与版本可序列化和预览适配 | `src/five_axis_slicer/manufacturing/toolpath.py`；`tests/test_toolpath_contract.py`；JSON 往返、导出状态、解析真值和预览段适配 6 项通过 | T01/T02 使用契约保存生成输入；T06/T07 扩展 MachineAxisTrajectory 和 ValidationReport | 2026-09-11 |
| T01 | 管状输入与 Operation 参数 | A02,A03,B02,B03 | 已完成 | 指定管体/入口/出口/基体；参数单位、范围、Dirty 与持久化生效 | [T01—T07 验收](../reviews/2026-09-11_t01_t07_indexed_tube_review.md)；四角色、手动中心线、九项参数、GUI/脚本/HTTP、Dirty、JSON 和引用重绑定通过 | T08 接入 Generate 时复用 Operation 契约 | 2026-09-11 |
| T02 | 管特征和中心线 | T01 | 已完成 | 圆柱/环面单支恒定圆截面识别及手动中心线入口；歧义可定位 | pipe2 外/内半径 16/15 mm，`line → arc → line`；解析直管、90° 圆弧管、手动 edge 和失败样例通过；[证据清单](../reviews/evidence/2026-09-11_t01_t07/manifest.json) | T08 使用当前受限管特征；分叉/变径维持不支持 | 2026-09-11 |
| T03 | 楔块与固定方向切层 | T02 | 已完成 | 最大楔角与道高误差控制分段；层面、归属和覆盖可检查 | 楔角/弦高误差分区、固定方向、半开区间、连续覆盖和尾段居中层测试通过 | T08 保存分区结果并展示检查状态 | 2026-09-11 |
| T04 | Indexed 薄壁轮廓与挤出路径 | T03 | 已完成 | 截交闭环、内外环、偏置、接缝、材料体积与层语义正确 | [当前复核](../reviews/2026-09-12_algorithm_audit_fixes.md)：原弦高/坐标反例通过；新增末层实际厚度/材料修复、固定喷嘴方向；真实pipe2 67层，径向误差0.003645 mm，体积与独立圆环值偏差约0.0112% | 限受支持恒定圆截面单道离线语义；不含任意窄壁填充或熔融材料实测资格；T08继续产品实际界面验收 | 2026-09-13 |
| T05 | 区段连接与安全转位 | T04 | 已完成 | 回抽/退离/转位/接近/恢复事件完整；无沉积旋转混入 Indexed | 原事件/零材料测试保留；2026-09-13修正径向姿态误用，分区内固定喷嘴轴，退离保留前段轴向、接近采用新层轴向；当前pipe2回读通过 | [当前更正](../reviews/2026-09-12_algorithm_audit_fixes.md)；实际控制器与现场安全另行验证 | 2026-09-13 |
| T06 | 参考 XYZAC 逆运动学与轴轨迹 | T05 | 已完成 | FK 回代、分支/角展开/行程/速度/加速度检查；刀长与回转中心生效 | Generic XYZAC 两分支、C 展开、软限、速度/加速度、刀长、装夹变换、非零回转中心和 FK 回代测试通过 | T08 生成参考轴轨迹；真实机型参数仍需独立标定 | 2026-09-11 |
| T07 | Indexed 路径、IPW 与运动检查 | T06 | 已完成 | 几何误差、沉积近似、喷嘴/基体/夹具/已打印体及转位扫掠检查 | [当前复核](../reviews/2026-09-12_algorithm_audit_fixes.md)：真实相交夹具/IPW/段内失败与Error禁止导出通过；保守空间筛选与暴力遍历一致；pipe2当前52380运动采样、无碰撞Error、FK约1.27e-13 mm | 限AABB/喷嘴球/bead capsule离散模型；未标定的真实机床、完整物理扫掠/动态跟随不在本资格内 | 2026-09-13 |
| T08 | Indexed 输出与当前 UI 完整流程 | T07 | 已完成 | STEP→生成→检查→NC→回读；改参、取消、保存重开；pipe2 通过 | [PC05/PC06证据](../reviews/evidence/2026-09-13_paper_core_ac/validation_manifest.json)：pipe2当前1,591点，六件套和自有AC 25/25事件严格回读；双语多尺寸、长Warning、Stale/错误展示与首页状态统一通过 | 限受支持的恒定圆截面离线流程；真实Viewer/OpenGL、控制器和实机另行验证 | 2026-09-13 |
| T09 | Tube Buildup 与底座多工序 | T08 | 已完成 | 多道厚壁/加厚及底座独立生成、工序顺序、跨操作衔接和格式迁移 | 同上；专项测试覆盖 multi-pass、底座独立操作和安全排序 | P01 复用多工序状态边界 | 2026-09-11 |
| T10 | Tube Continuous 几何与标架 | T09 | 已完成 | 空间中心线 RMF、连续螺旋、接缝与多层路径；低曲率无翻转 | 同上；专项测试覆盖 RMF 退化拒绝、螺旋 seam/volume 和 G1 空间链 | P01 复用连续路径契约 | 2026-09-11 |
| T11 | Tube Continuous 运动与输出 | T10 | 已完成 | 连续姿态、轴速/加速度、奇异、全运动碰撞和 NC 回读通过 | 同上；连续 FK/C 展开、运动限制、碰撞阻止导出及六件套 readback 通过 | P01 复用离线运动检查边界 | 2026-09-11 |
| T12 | 整个 Tube 工作台验收 | T08,T09,T11 | 已完成 | 三操作、错误样例、UI/脚本/HTTP、保存重开和帮助均验证 | [PC05实施复盘](../reviews/2026-09-13_paper_core_ac_implementation_review.md)与[Tube UI证据](../reviews/evidence/2026-09-13_paper_core_ac/validation_manifest.json)：Indexed/Buildup/Continuous、Ready/Stale/Error、1366×768/1600×900/1920×1080、中英界面与当前手册通过；笔记本尺寸动作按钮重叠回归已修复 | Tube阶段关闭到受限离线资格；生产VTK/OpenGL、真实控制器/标定/现场碰撞/试切单列未验证 | 2026-09-13 |
| P01 | Planar Region 与层截面 | T12 | 已完成 | 通用 Setup 接入、平面区域及实体分层、孔/岛拓扑有效 | [最终证据](../reviews/evidence/2026-09-12_p07_planar_final/manifest.json)；当前源码重新覆盖稳定引用、Build CS、截层、保存重开→Stale、GUI/脚本/HTTP、问题定位和错误恢复；Planar 223 passed | P02—P07 已完成；进入 C01 | 2026-09-12 |
| P02 | Planar Zigzag Fill | P01 | 已完成 | 轮廓/填充、带孔裁剪、路径排序、覆盖/残余/越界和材料用量可核对；离线轨迹、G-code、回读和使用手册齐全 | [最终证据](../reviews/evidence/2026-09-12_p07_planar_final/manifest.json)；当前真实 STEP 142 点，六件套和 142/142 回读通过；三尺寸中英 Qt/OpenGL 图、独立覆盖/材料检查和错误恢复已复核 | P03—P07 已完成；进入 C01 | 2026-09-12 |
| P03 | Planar Offset Fill | P02 | 已完成 | 多轮偏置、窄区/消失区、多岛、接缝正确 | [P03 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p03-offset-fill-产品接入与关闭)与[证据](../reviews/evidence/2026-09-12_p03_planar/manifest.json)；OCCT 偏置覆盖孔、凹区、多岛、窄颈分裂，部分消失为可导出 Warning、全部消失为阻止导出的 Error；12 passed | 进入 P04；沿用共享 Toolpath、状态和残余量测 | 2026-09-12 |
| P04 | Planar Thin Wall | P03 | 已完成 | 单/多道、开放壁和不足道宽规则可验证 | [P04 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p04-thin-wall-产品接入与关闭)与[证据](../reviews/evidence/2026-09-12_p04_planar/manifest.json)；开放壁及闭壁同心多道、区域驱动内偏置、半道宽内移和 `reduce` Warning 已验证；7 passed | 进入 P05；保留不足道宽策略和可见诊断 | 2026-09-12 |
| P05 | Planar Spiral | P04 | 已完成 | 单连通连续 Z 路径和层间过渡；多岛输入明确拒绝 | [P05 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p05-spiral-产品接入与关闭)与[证据](../reviews/evidence/2026-09-12_p05_planar/manifest.json)；至少两层、单岛无孔、拓扑对应、连续 Z、实体内插值、进给和体积检查已验证；10 passed | 进入 P06；在真实 STEP 与 UI 中核对正常、失败及恢复流程 | 2026-09-12 |
| P06 | 整个 Planar 工作台验收 | P02,P03,P04,P05 | 已完成 | 四操作生成/检查/输出/回读、改参重开和帮助通过 | [最终证据](../reviews/evidence/2026-09-12_p07_planar_final/manifest.json)与[使用手册](../guides/planar_workbench_zh.md)；当前真实 STEP Zigzag/Offset/Thin Wall/Spiral 为 142/16/6/129 点，四项六件套及回读通过；操作切换、取消、撤销/重做、问题定位、重开 Stale、三尺寸双语 UI 和恢复流程通过 | P07 已完成；进入 C01 | 2026-09-12 |
| P07 | Planar Grid/Lines 支撑生成 | P06 | 已完成 | 检测悬垂和空中岛；按 XY/Z 间隙生成支撑主体与接触层路径；共享 Toolpath、检查、G-code、回读、六件套、保存重开、脚本/HTTP、双语 UI、真实模型和图文手册通过 | [最终证据](../reviews/evidence/2026-09-12_p07_planar_final/manifest.json)与[复盘](../reviews/2026-09-12_p07_planar_support_review.md)；解析 33 段、61.86 mm³、66/66，复杂 STEP 9,662/9,662；Lines/Grid 独立方向、间距、顺序和材料真值；主体/interface Viewer 可辨；P07 150 passed、Planar 223 passed、全仓 753 passed、3 skipped、130 subtests，质量 exit 0；严格失败模型未导出 | C01—C05 已完成；进入 R01 | 2026-09-12 |
| C01 | Curve Region、边链与姿态输入 | P07 | 已完成 | 有向 edge 链、弧长采样、邻面或指定法向可追溯 | [复盘](../reviews/2026-09-12_curve_workbench_review.md)与[最终证据](../reviews/evidence/2026-09-12_curve_workbench_final/validation_manifest.json)；完整 GeometryReference、反向、断链、法向歧义/缺失、退化 edge、拓扑重绑均验证 | C02 已完成 | 2026-09-12 |
| C02 | Curve Buildup | C01 | 已完成 | 直线/圆弧/样条单道，端点与挤出量正确 | 20 mm 解析直线、R40 四分之一圆和真实 STEP 样条通过；单道 70 点、69 沉积段、32.771862137049 mm³、回读与六件套通过 | C03 已完成 | 2026-09-12 |
| C03 | Curve Multi-pass Buildup | C02 | 已完成 | 多层重复堆叠、累计道高和层间连接正确 | 3 层 210 点、207 沉积段；累计层高、奇偶换向、Travel/Retract/Prime/Dwell 分离、材料量和回读通过 | C04 已完成 | 2026-09-12 |
| C04 | Curve Offset Buildup | C03 | 已完成 | 横向多道、锐角、自交和偏置失败可定位 | 真实叶轮反向 edge 三道相邻点距 2.947—3.000 mm；210 点、93.880702147199 mm³；正向投影塌缩、trim 越界、标架反转和自交拒绝 | C05 已完成 | 2026-09-12 |
| C05 | 整个 Curve 工作台验收 | C02,C03,C04 | 已完成 | 三操作全流程、边引用重绑定、参数与持久化通过 | [图文手册](../guides/curve_workbench_zh.md)、[复盘](../reviews/2026-09-12_curve_workbench_review.md)、[最终证据](../reviews/evidence/2026-09-12_curve_workbench_final/validation_manifest.json)；GUI/脚本/HTTP、取消、撤销、Stale、Viewer、保存重开、三操作六件套、当前直接集 40 passed/2 subtests、全仓 783 passed/3 skipped/130 subtests，质量/构建/native 门通过；实机未验证 | 既有离线结果复用；当前进入PC01/PC02论文核心路线 | 2026-09-13 |
| R01 | Rotary Region 与回转坐标 | C05 | 已完成 | 回转轴、轮廓、半径与角度范围有效，去除无效锁定行为 | 稳定 axis/face/contour 描述符、非零中心、正方向/零角、非默认 Build CS、不同轴向、重绑几何不漂移和 preview-only 阻断均验证；扇叶 B-spline 面拒绝、轮毂圆柱面绑定及修剪面不自动推导角区也已实测；[复盘](../reviews/2026-09-13_rotary_workbench_review.md) | 既有离线结果复用；当前进入PC01/PC02论文核心路线 | 2026-09-13 |
| R02 | Rotary Spiral | R01 | 已完成 | 圆柱/圆锥螺旋、螺距/方向/角速度可核对 | 三圈圆柱与两圈线性变径圆锥独立端点/长度/体积/法切向真值通过；规定相位连续展开、机床 C 对齐、G93 段时间与回读验证；[六件套](../reviews/evidence/2026-09-13_rotary_workbench_final/products/) | 既有离线结果复用；当前进入PC01/PC02论文核心路线 | 2026-09-13 |
| R03 | Rotary Thin Wall | R02 | 已完成 | 圆周、轴向步进、径向多道和轮廓变化可验证 | 4 层×3 道独立真值、奇偶蛇形、轴向裁剪、窄壁 error/reduce、超宽拒绝、Retract/Prime 与首末净空连接通过；任意非线性径向 contour 不在当前支持范围 | 既有离线结果复用；当前进入PC01/PC02论文核心路线 | 2026-09-13 |
| R04 | Rotary Around Part | R03 | 已完成 | 局部覆盖、多周向区域、跨零点和连续回转空移检查 | `350°→380°` 与 `480°→570°` 多区域/多层独立真值、无跨区沉积、连续方向、结构化 depart/travel/approach 和最终安全离开通过；区域为数值角带并保存全局 surface refs | 既有离线结果复用；当前进入PC01/PC02论文核心路线 | 2026-09-13 |
| R05 | 整个 Rotary 工作台验收 | R02,R03,R04 | 已完成 | 三操作的轴速、周期、碰撞、输出回读与 UI 通过 | [图文手册](../guides/rotary_workbench_zh.md)、[复盘](../reviews/2026-09-13_rotary_workbench_review.md)、[最终证据](../reviews/evidence/2026-09-13_rotary_workbench_final/validation_manifest.json)；GUI/脚本/HTTP、取消、撤销、Stale、保存重开、四组六件套、37 项专项、820 项全仓、质量/构建/Twine/包导入和三尺寸中英 Qt 图通过；[扇叶补充报告](../reviews/2026-09-13_pipe2_model_manual_gcode_comparison.md)已登记手工 imported NC 与 generated Rotary 的边界；3 项符号链接权限 skip 单列 | 既有离线结果复用；当前进入PC01/PC02论文核心路线 | 2026-09-13 |
| F01 | Freeform Region 与曲面计算 | R05 | 未开始 | face/边界/导引引用、UV 度量、法向、周期和修剪正确 | OS-02/03/06；当前只有选择与预览 | 暂缓完整范围；PC02优先交付论文子集；恢复后按原判据验收 | 2026-09-13 |
| F02 | Freeform Coating 单面路径 | F01 | 未开始 | UV/投影单层覆盖，三维道间距、边界和法向正确 | 待实现 | 暂缓完整范围；PC02优先交付论文子集；恢复后按原判据验收 | 2026-09-13 |
| F03 | Freeform Thin Wall | F02 | 未开始 | 曲面导引多道/多层筋壁，沿/跨方向偏置有效 | NX-04 可参考操作与偏置语义 | 暂缓完整范围；PC02优先交付论文子集；恢复后按原判据验收 | 2026-09-13 |
| F04 | Freeform Buildup 与多面接缝 | F03 | 未开始 | 有限多层/多面覆盖、接缝连续、偏置自交与投影多解诊断 | 任意实体自动曲层分解不在本版 | 暂缓完整范围；PC02优先交付论文子集；恢复后按原判据验收 | 2026-09-13 |
| F05 | 自由曲面姿态和覆盖检查 | F04 | 未开始 | Lead/Side Tilt、朝向、轴约束、碰撞及覆盖报告 | 与 Tube 连续轨迹共享基础 | 暂缓完整范围；PC02优先交付论文子集；恢复后按原判据验收 | 2026-09-13 |
| F06 | 整个 Freeform 工作台验收 | F02,F03,F04,F05 | 未开始 | 三操作全流程、修改曲面引用/参数重算及保存通过 | 实机状态未验证 | 暂缓完整范围；PC02优先交付论文子集；恢复后按原判据验收 | 2026-09-13 |
| X01 | Research 数据与复现实验约定 | F06 | 未开始 | 场的坐标/单位/来源、网格质量、固定基线、误差和结果模板齐备 | 研究方法不能仅挂入口名称 | 暂缓，移出论文核心版关键路径；PC07后另行排期 | 2026-09-13 |
| X02 | Conical Buildup | X01 | 未开始 | 圆锥层截交、顶点奇异处理、层间距及姿态链验证 | 待实现 | 暂缓，移出论文核心版关键路径；PC07后另行排期 | 2026-09-13 |
| X03 | Scalar Field Surface Slicing | X02 | 未开始 | 网格标量场、层/路径提取、间距和临界点诊断完整 | OS-06 是表面等值线参考，不等同体内等值面 | 暂缓，移出论文核心版关键路径；PC07后另行排期 | 2026-09-13 |
| X04 | Stress-oriented Toolpath | X03 | 未开始 | 真实张量场→主方向→连续路径；奇异/弱应力区规则和对齐指标 | 尚无已确认力学案例；不虚构强度提升 | 暂缓，移出论文核心版关键路径；PC07后另行排期 | 2026-09-13 |
| X05 | Support-reduction Toolpath | X04 | 未开始 | 有约束的方向/场优化、固定基准、悬垂代理与可达检查 | 改善幅度未测，不设虚构提升率 | 暂缓，移出论文核心版关键路径；PC07后另行排期 | 2026-09-13 |
| X06 | 整个 Research 工作台验收 | X02,X03,X04,X05 | 未开始 | 四方法按计划 7.1 完成生成/检查/输出回读、改参重开；限制和失败记录完整 | 尚未实施；研究完成不能替代实验验证 | 暂缓，移出论文核心版关键路径；PC07后另行排期 | 2026-09-13 |
| I01-OWN | 自有机型默认配置与文件管理 | 用户专项授权 | 已完成 | 自有机型默认选择、自定义、导入导出、保存重开和双语界面 | [本轮复盘](../reviews/2026-09-12_own_printer_profile_review.md) | 729 passed、3 skipped；最终专项6 passed，质量门禁通过；实机标定与品牌库另列 | 2026-09-12 |
| I01-AXIS | 跨工作台旋转轴 G-code 输出字 | 用户专项授权、I01-OWN | 已完成 | 保留内部 A/B/C 运动学语义；按实际旋转关节配置单字母输出地址；GUI/脚本/HTTP、用户库、项目快照、四工作台 Stale、共享后处理和严格回读通过 | [图文指南](../guides/machine_profiles_zh.md)、[复盘](../reviews/2026-09-13_custom_rotary_axis_words_review.md)、[证据清单](../reviews/evidence/2026-09-13_custom_rotary_axis_words/validation_manifest.json)；122 passed/55 subtests；全仓 834 passed/3 skipped/138 subtests；质量、sdist/wheel 与 Twine 通过 | I01 仍需真实 XYZAB/第二运动学与控制器注册；目标固件、标定、现场碰撞和试切未验证 | 2026-09-13 |
| I01 | 机型配置与后处理完整性 | X06 | 未开始 | XYZAC、XYZAB 独立模型及控制器注册、FK/IK/回读验证 | 实际设备参数/标定未核验 | 暂缓完整六工作台/第二机型范围；核心版由PC04/PC06/PC07单独验收 | 2026-09-13 |
| I02 | 全软件工作流与质量回归 | I01 | 未开始 | 六工作台、20 操作、多工序、错误恢复、双语/双后端及数值矩阵通过 | 待前述阶段完成 | 暂缓完整六工作台/第二机型范围；核心版由PC04/PC06/PC07单独验收 | 2026-09-13 |
| I03 | 本地安装包、帮助与复现实例 | I02 | 未开始 | 本地构建/包检查、干净环境启动、20 操作帮助与案例可找到 | 不包含对外发布或上传 | 暂缓完整六工作台/第二机型范围；核心版由PC04/PC06/PC07单独验收 | 2026-09-13 |
| I04 | 本版软件总验收 | I03 | 未开始 | 20 操作验收证据、范围/限制、未验证设备状态及文档齐全 | 软件验收与实机验证分别列明 | 暂缓完整六工作台/第二机型范围；核心版由PC04/PC06/PC07单独验收 | 2026-09-13 |
| SIM | 五轴运动仿真与视频导出 | PC06、I01-OWN | 进行中 | 参数化/自定义机床场景、真实轴时间回放、分段倍速、确定性帧和视频清单形成闭环 | [专项计划](motion_simulation_plan.md)、[独立台账](motion_simulation_tracker.md)、[调研](motion_simulation_research.md)；SIM00已完成，产品实现未开始 | 从SIM01冻结来源、时间和帧计划契约 | 2026-09-20 |

## 模型分工与悲观 token 预算

以下为六工作台全范围的历史预算，**不再作为当前版本必须执行或消耗的预算**。PC00—PC07 已完成；F/X/I 完整 16 项暂缓，Tube T01—T12 已关闭到受限离线资格。此前“7项待验证”包含后来已关闭的 Planar 项，现予更正。核心版不预填未经校准的新 token/工期总额；单位为百万 token（M），下表保留供完整路线恢复时参考。

模型选择依据为 [OpenAI Codex Models](https://developers.openai.com/codex/models)：Luna 适合明确、重复且高吞吐的任务，Terra 适合日常开发，Sol 适合复杂开放问题，Astra 用于最困难的跨步骤判断。官方说明也建议从较低推理强度开始，只在任务确有更深规划或检查需求时提高；模型可用性随账户和发布批次变化。

| 阶段 | 范围 | 主执行模型与强度 | 独立检查 | 阶段验收 | 悲观预算（执行＋检查＋验收） | 选择说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 共性契约（已完成） | A01—A03 | 后续机械性维护用 Luna Low；契约变更用 Terra Medium | 影响多个工作台时用 Sol Medium | 仅重大破坏性变更用 Astra High | 0（不计未来预算） | 复用现有契约与证据；发生范围变化时另行登记预算 |
| Tube | T01—T12 | Terra Medium；T02—T07、T10—T11 的几何、IK、碰撞难点升级 Sol High | Sol High；纯 UI/持久化回归由 Luna Low 归纳 | Astra High，仅 T08 首流程门和 T12 阶段门 | 7.50 M（5.40＋1.50＋0.60） | 任务最多，且建立后续复用的几何、运动和检查基础 |
| Planar | P01—P07 | Terra Medium；偏置、自交、支撑区域布尔失败升级 Sol/Astra High | Sol Medium | Astra High，用于 P06/P07 阶段门 | 4.10 M（2.80＋0.80＋0.50） | 复用 Tube 截交和结果契约；支撑按 clean-room 独立实现 |
| Curve | C01—C05 | Terra Medium；样条框架、锐角和自交升级 Sol High | Sol Medium | Astra High，仅 C05 | 2.70 M（1.80＋0.55＋0.35） | 规模较小，主要风险在链方向、法向与偏置 |
| Rotary | R01—R05 | Terra Medium；周期边界、连续回转运动升级 Sol High | Sol Medium | Astra High，仅 R05 | 3.00 M（2.00＋0.60＋0.40） | 可复用 Tube 运动链，新增风险集中在周期与跨零点 |
| Freeform | F01—F06 | Sol High 处理 UV、修剪、投影多解和姿态；UI 接入、序列化用 Terra Medium | Sol High，关键数值样例抽查用 Astra High | Astra High，仅 F06 | 4.40 M（3.00＋0.90＋0.50） | 几何歧义和数值失败模式多，强模型投入高于平面与曲线 |
| Research | X01—X06 | Sol High；数据整理、固定格式实验和表格归纳用 Luna Low | Astra High，检查基线、指标、负结果和结论边界 | Astra Extra High，仅 X06 | 5.40 M（3.60＋1.20＋0.60） | 研究任务开放度最高，需要防止场定义、指标和结论失真 |
| 集成与总验收 | I01—I04 | Terra Medium；双机型运动学与跨模块根因升级 Sol High | Sol High | Astra Extra High，I04 做一次总门禁 | 3.00 M（1.60＋0.70＋0.70） | 重点是证据覆盖、跨模块一致性和交付完整性 |
| **合计** | **44 项** |  |  |  | **29.50 M 基础上限** | 最初七个阶段之和；已完成额度不转作额外复查 |
| **风险储备** | 新增失败、上下文重建、必要复测 | 沿用触发该储备的任务模型 | 不单独启动检查 | 不新增阶段门 | **5.90 M（20%）** | 只有新证据、代码或环境变化才允许重试 |
| **项目悲观总上限** |  |  |  |  | **35.40 M token** | 含 20% 储备；超过时先拆任务和压缩证据，不直接升级模型 |

### 单任务使用规则

1. 每次只处理台账中的一个编号。开始时给模型任务行、直接依赖、相关接口、当前 diff 和失败证据，不反复输入整份计划、全仓日志或历史对话。
2. 明确的检索、格式转换、测试输出归纳、文档机械更新优先 Luna Low；常规编码和局部调试用 Terra Medium；复杂几何、IK、碰撞、研究方法及原因不明的跨模块失败用 Sol High；Astra 只用于阶段门、总验收或 Sol 两轮仍无法收敛且出现新证据的难题。
3. 单项实现完成后先运行直接相关验证。高风险算法由不同模型读取精简证据包做独立检查；低风险 UI、文档或机械修改不逐项调用 Astra。检查模型提出问题后，由主执行模型修正一次，再把差异交回检查模型确认。
4. 建议单项软上限：A/T/P/C/F/R/X 普通实现 0.35 M，复杂算法 0.65 M，阶段验收 0.60 M，总验收 0.70 M。达到 80% 时先写证据摘要并开启同编号的新任务；达到上限仍未收敛则在本行记为受阻或拆分子任务。
5. 每个任务在证据列或复盘中记录模型、推理强度、输入/输出 token（产品可提供时）、重试原因和累计值。产品未提供精确 token 时记录“不可得”，不得用消息字数伪装实测 token。
6. 预算不是消耗目标。未用额度不转化为额外复查；已有判据和证据满足后立即归档。阶段实际累计达到表内预算的 80% 时复核剩余范围；达到 100% 时暂停同类重试，只有拆分方案或新增证据才能动用风险储备。

## 证据记录模板

后续复盘沿用 `docs/reviews/`，同一任务持续更新同一文件。每份任务记录至少包含：

```text
任务编号、范围和开始/完成日期
输入文件及哈希、参数版本、资源快照、算法版本
实现文件和提交（未提交时写工作区及实际文件）
验证命令、环境、实际结果、生成产物与指纹
正常案例、失败案例、数值误差及 UI 观察
已完成、未验证、受阻条件、下一步
```

## 计划变更记录

| 日期 | 变更依据 | 变更内容 | 影响 |
| --- | --- | --- | --- |
| 2026-09-14 | 用户要求修复截图中的多个 Actions 红叉，并允许安装 `gh` | 读取运行 `34758493547` 的三个失败任务日志；将 Freeform 的两处旧式 `QFormLayout` 枚举访问改为类型存根与运行时均支持的带类型写法；安装 GitHub CLI 2.100.0 | 三个失败任务共用的 Mypy 根因已修复，运行 `34770465207` 四项全绿；本地质量、同 CI 领域集和论文核心测试通过；无头 Freeform Qt 专项仍受当前 Windows 原生退出限制，不计为通过 |
| 2026-09-13 | 用户要求按工业软件学习思路整理图文教程矩阵，案例只作练习，并在开篇写明 IDE/PWSH 启动入口 | 新增学习总册；重组手册中心为公共课程、五工作台支线和参考层；加入自检、错误恢复、迁移检查单和编写矩阵；核对 `run_app.py` 与 `scripts/run_app.ps1` | DOC-01 已完成；现有模块手册保留为参考，不再以具体案例组织总学习路线；Computer Use 无法连接窗口，复用当前可追溯 Qt/VTK 图片并单列限制 |
| 2026-09-13 | 用户要求检查并完成 PC00—PC07，发现问题必须修复 | 冻结输入契约，完成受限 Freeform、T0—T3 多材料事件、自有 AC 离线后处理、Tube 收口、五产品/四项目证据及本地封装；修复质量门发现的可空CAD/输入类型问题和1366×768 Tube顶部按钮重叠 | PC00—PC07、T08、T12改为已完成（受限离线）；57 passed/6 subtests、全仓856 passed/3 skipped/141 subtests、质量/构建/Twine/原生包隔离安装通过；真实控制器、标定、生产VTK/OpenGL、现场碰撞和试切未验证 |
| 2026-09-13 | 用户要求按 GitHub 默认主线统一本地与远端分支，并解决当前 CI 依赖冲突 | 确认默认分支为 `master`，所有功能分支均已进入主线后删除其引用；Actions 改用隔离虚拟环境，固定 mypy、CasADi 与 PyQt5，修复 Linux 平台存根，并把托管 Windows 回归限定为无头领域集 | 本地和远端均只保留 `master`；干净 Python 3.12 的依赖、质量和161项领域测试通过；完整 Qt/VTK 桌面回归仍须在真实显示环境执行 |
| 2026-09-13 | 用户要求再检查旧错误，存在则修复、消失则标记完成 | AUD-02-TUBE原反例通过；新增末层材料、固定打印方向与IPW性能修复；当前pipe2全链通过，撤回旧A≈±122.3°固有需求解释；839 passed、3 skipped、141 subtests，质量通过，六件套压缩校验 | T04/T07受限离线资格恢复；T08/T12仍待当前实际界面与整阶段门；PC05仅复核子项先行，整体仍依赖PC04 |
| 2026-09-13 | 用户要求资源优先完成论文案例，并批判性核对论文、寻找可复用项目 | 新增PC00—PC07；四例能力矩阵、材料事件、自有AC后处理、Tube收口和本地封装；核对7个项目固定commit/许可；README纠正Tube全完成声明 | PC00已完成，PC01—PC07未开始；完整F/X/I共16项暂缓，Tube4项待验证保留；论文实验数字和旧NC不作为当前软件能力真值 |
| 2026-09-13 | 用户要求客户可定义原生 A/B/C 对应的固件轴名，并在所有工作台最终 G-code 中生效 | 新增 I01-AXIS：机型领域校验/不可变映射、客户友好双语 UI、用户库副本、共享 Setup 发布、受限脚本与 HTTP 命令、G-code 审计头、严格回读、图文教程和当前回归证据 | I01-AXIS 已完成；Tube/Planar/Curve/Rotary 共用映射。I01 第二运动学仍未开始，轴字改名不增加物理 B 轴或异形机构 IK，也不取得实机资格 |
| 2026-09-13 | 用户要求从含 C05 的干净基线按 R01→R05 完成整个 Rotary 工作台，并先研究 Open5x Grasshopper 与公开 NX 资料 | 完成稳定回转几何引用、Spiral/Thin Wall/Around Part、连续相位 XYZAC、G93 回读、失败矩阵、四组六件套、双语三尺寸 Qt 图文手册、当前全仓/质量/构建证据；Open5x 仅静态解析，NX 私有正文不冒充公开来源 | R01—R05 改为已完成；后续未开始任务为 16 项；下一项为 F01；Generic XYZAC、精确基体/机床碰撞、真实控制器/标定/现场/试切仍未验证 |
| 2026-09-13 | 用户要求用经典扇叶模型和对应手工代码检查差异、选面并形成可视报告 | 独立解析 2,936,410 行手工代码，区分 XYZ 基础与三段 XYZAC 叶片程序；确认 180° frame 注册候选、叶片 B-spline 拒绝、轮毂圆柱面接受及修剪面角区语义限制；更新报告、教程、索引和证据 | R01—R05 状态不变；新增的是补充诊断证据，不把 imported NC 外观对齐升级为控制器、碰撞或实机资格 |
| 2026-09-12 | 用户要求从 P07 干净基线按 C01→C05 完成整个 Curve 工作台 | 完成有向 edge 链、三种 Curve 操作、统一产品链、GUI/脚本/HTTP、保存重开、真实 STEP、失败矩阵、六件套、图文手册、当前串行回归、质量与构建证据 | C01—C05 改为已完成；后续未开始任务为 21 项；下一项为 R01；Generic XYZAC、真实控制器/机床/材料/试切边界继续单列未验证 |
| 2026-09-12 | 用户要求检查完成情况、运行示例并先出修改方案 | AUD-01 核对实际源码和生成结果；T04/T07/T08/T12/P01/P02/P06 调整为待验证，保留历史证据；归档独立反例、版本快照、修改顺序和验收矩阵 | 本轮审查完成，产品修复尚未实施；P07 并行修改的已解决失败单列，不覆盖其他任务成果 |
| 2026-09-12 | 用户要求为平面切片补充成熟切片器式支撑功能 | 在已关闭 P06 后新增 P07：首版 Grid/Lines 支撑，包含悬垂/空中岛检测、XY/Z 间隙、接触层、共享 Toolpath、输出、UI、真实模型和手册；C01 依赖改为 P07 | 当前任务由 C01 改为 P07；Tree/Organic、桥接专用路径、双材料与实机资格留作后续；不复制 AGPLv3 上游源码 |
| 2026-09-12 | P07 阶段证据关闭 | P07 Grid/Lines 支撑的解析真值、六件套、66/66 回读、7 图 UI 审计、211 项专项、741 项全仓回归与最终质量门禁已归档；支撑完整中心线段与目标 CAD 相交检查已覆盖；风扇在 Z=57 mm 的端点修正超限保留为未导出 Error | P07 改为已完成，当前任务回到 C01；主表后续未开始任务为 26 项，联合逐层调度、完整喷嘴扫掠、真实控制器和实机资格仍未验证 |
| 2026-09-12 | 用户要求按顺序完成 P03—P06，并检查算法、UI、真实模型输出和使用文档 | 关闭 Offset、Thin Wall、Spiral 和整个 Planar 阶段；归档专项/全仓/质量门禁、真实 STEP 四操作六件套及三尺寸中英 Qt/OpenGL 证据 | Planar P01—P06 全部完成；下一项为 C01；工作台顺序保持 Tube → Planar → Curve → Rotary → Freeform → Research |
| 2026-09-12 | 用户要求 Curve 完成后优先开发 R 系列工作台 | 将 Rotary R01—R05 从 Freeform 之后移到 Curve C05 之后；R01 依赖改为 C05，F01 依赖改为 R05，X01 依赖改为 F06；明确 Research 使用 X 编号 | 新顺序为 Curve → Rotary → Freeform → Research；任务数量、范围、状态、完成判据和预算均不变；本轮 P06 关闭后当前任务为 C01 |
| 2026-09-11 | 用户要求把本轮开发经验整理为后续工作台可调用的 Skill，并在日志和台账记录调用 | 新建个人 Skill `five-axis-workbench-development` 及阶段门槛参考；项目 `AGENTS.md` 增加入口；台账增加实际调用记录 | P/C/F/R/X/I 开发复用同一闭环；验证仍由 `five-axis-slicer-validation` 管理；P01 状态保持未开始 |
| 2026-09-11 | 用户要求各模块制作形象、图文并茂的使用手册 | 建立手册索引、图片规则和阶段门槛；先补齐已完成 Tube 与 G-code 预览，后续五个工作台在各自阶段验收前同步交付手册 | 图文手册成为后续 P06/C05/F06/R05/X06 与 I03/I04 的完成条件，不为尚未实现功能编写伪操作说明 |
| 2026-09-11 | 用户要求完成 T01—T07，并明确管状算法参考相邻项目后在当前项目重写聚拢 | 完成受限 Tube Indexed 的输入、中心线、切层、薄壁路径、转位、Generic XYZAC 与离线检查；记录 Fractal Cortex 来源、commit、SHA-256 和内部传阅边界；完成三档分辨率 UI 审查；质量门禁通过，全仓 430 passed、3 skipped、130 subtests passed | T01—T07 登记为已完成；下一项为 T08；不扩大为完整 Tube 工作台、NC 闭环或真实机床资格 |
| 2026-09-11 | 用户要求完成 T08—T12 并归档阶段证据 | 完成 Indexed 生成/后处理/回读、Buildup 多工序、Continuous RMF/螺旋/运动、三操作集成及 UI/脚本/HTTP 阶段验收；质量门禁全通过，专项 98 passed、1 skipped、2 subtests，全仓 465 passed、3 skipped、130 subtests；首次 targeted 回归失败后串行重跑通过；1366x768/1600x900/1920x1080 UI summary 无碰撞且文字全适配；pipe2 1171 points readback passed | T08—T12 登记为已完成；下一项为 P01；Generic XYZAC 仍仅离线参考，真实机床资格与现场试切未验证 |
| 2026-09-11 | 用户要求检查 A01—A03，满足判据后正式完成 | 补齐解析真值夹具和现有结果查看器适配；质量门禁通过；全仓 408 passed、3 skipped、130 subtests passed；A01—A03 正式维持为已完成 | 下一项开发任务改为 T01；不提前声明中心线、切片、IK、碰撞或实机能力完成 |
| 2026-09-11 | 用户要求按阶段规划节省 token 的模型组合，并按偏悲观口径估算 | 新增 44 项待办的执行、独立检查、阶段验收模型和 35.40 M token 含储备上限；记录[本轮复盘](../reviews/2026-09-11_model_token_budget_review.md) | 不改变任务范围、顺序或状态；后续按实际消耗校准，不把额度视为必须用完 |
| 2026-09-11 | 用户要求完成 B01–B03 | 联合回归三个既有基础任务并归档当前证据，状态改为已完成 | 不扩大算法范围；下一项仍为 A01；符号链接、真人桌面与实机验证边界单列 |
| 2026-09-10 | 用户选择管状优先 | 将 Tube 放在首位，首里程碑设为 pipe2 Indexed | 取代旧目标中 Curve 优先；其他工作台仍逐个完成 |
| 2026-09-10 | 原目标 19 操作与近期管状规划 | Thin Wall 明确 Indexed，新增独立 Continuous，共 20 操作 | T08 只是首流程，T12 才是整个 Tube 验收 |
| 2026-09-10 | 用户说明成果来源 | 外部切片和人工拼接逐文件登记 | 不把旧 G-code 当本软件算法结果或唯一真值 |
| 2026-09-10 | 用户说明没有开源计划 | 计划采用自用定位及公开方法独立实现 | 不沿用旧目标的开源交付要求；现有许可文件本轮未改 |

本表新增任务或改变范围时同步记录变更，并更新顶部任务数量。未来若估算工时，先用已完成任务的实际记录校准；当前不填没有依据的工期。
