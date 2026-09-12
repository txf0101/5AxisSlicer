# 六个工作台开发进度台账

最近更新：2026-09-12。关联[开发计划](development_plan.md)、[参考资料](reference_research.md)与[文档索引](../README.md)。**下方主表是任务进度的唯一维护位置**，计划和复盘引用任务编号，不另行维护一份状态表。

当前顺序：**管状 → 平面 → 曲线 → 回转 → 自由曲面 → 研究 → 整体验收**。用户已确定管状优先，并于 2026-09-12 将回转 R01—R05 调整到 Curve C05 之后、Freeform 之前；Research 仍使用 X01—X06 编号。Planar P01—P07 已按当前源码重新验收并全部完成，当前没有进行中的支撑任务；AUD-01 保留的 Tube T04、T07、T08、T12 待验证状态不因 Planar 关闭而撤销。后续工作台首项为 **C01**。

本表保留规划、基础、算法、工作台和整体验收任务的唯一状态。2026-09-12 的 AUD-01 已完成检查和修改方案，确认的 Planar 缺陷已在 AUD-02 和 P07 最终验收中修复。P07 以 clean-room 独立实现的 Grid/Lines 支撑首版关闭：解析悬垂真值为 33 段、61.86 mm³、66/66 回读，复杂 STEP 为 9,662/9,662 回读；9 张 Qt/OpenGL UI 图覆盖参数、正常、错误恢复和 Stale 恢复；最终 Planar 223 passed，全仓 753 passed、3 skipped、130 subtests，官方质量脚本全绿。Tree/Organic、桥接专用路径、双材料不在首版范围。Generic XYZAC 仍仅为离线参考，真实控制器语义、机床标定、完整喷嘴扫掠和现场试切未验证。

本轮新增用户授权子任务 **I01-OWN**：自有机型默认配置、选择、自定义及文件导入导出；独立于 I01 的第二运动学与控制器完整验收。

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
| 2026-09-12 | DOC-MULTICHAT | `five-axis-workbench-development` | 编制 P07、C、R、F、X 与 I 阶段的多对话启动提示词，统一完整工作台、验证、图文手册和分支交接门槛；未启动新开发任务 | [启动提示词](workbench_multi_chat_prompts.md)与[编制复盘](../reviews/2026-09-12_multi_chat_workbench_prompt_review.md) |

| 2026-09-12 | AUD-01 | `five-axis-workbench-development` | 独立真值、真实模型、生成/回读与阶段资格审查；GPT-6 子 Agent 复核 Tube 和支撑，只出方案 | [独立审查](../reviews/2026-09-12_project_algorithm_audit.md) |
| 2026-09-12 | AUD-01 | `five-axis-slicer-validation` | 只读预检、串行回归、固定源码复测、P07 并行修改分类、Qt/OpenGL 图像和证据指纹 | [审查证据](../reviews/evidence/2026-09-12_project_audit/manifest.json) |

| 2026-09-12 | AUD-02 | `five-axis-workbench-development`、`five-axis-slicer-validation` | 按已批准方案修复坐标/状态/NC/截层/道宽/运动缺陷，GPT-6 子 Agent 并行领域验证，Qt 与全仓串行 | [修复方案](2026-09-12_algorithm_audit_fix_plan.md)；[证据目录](../reviews/evidence/2026-09-12_audit_fixes/) |

## 主表

| 编号 | 阶段与交付 | 依赖 | 状态 | 完成判据 | 证据或阻塞 | 下一步 | 更新日期 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUD-01 | 跨工作台独立审查与修改方案 | 当前工作区与项目示例 | 已完成 | 文档/实现核对、真实模型、独立反例、证据和待实施方案齐全 | [审查报告](../reviews/2026-09-12_project_algorithm_audit.md)；[修改方案](2026-09-12_algorithm_audit_fix_plan.md)；本轮未修改产品代码 | 用户确认方案后实施；P07 并行工作保留 | 2026-09-12 |
| AUD-02 | 跨工作台缺陷修复与重新验证 | AUD-01 | 已完成 | 原始反例拒绝、正确解析/真实模型通过、旧资格失效、全仓与图文证据齐全 | [修改方案](2026-09-12_algorithm_audit_fix_plan.md)；[本轮证据](../reviews/evidence/2026-09-12_audit_fixes/) | [修复复盘](../reviews/2026-09-12_algorithm_audit_fixes.md)；窄壁实心、自适应道宽、联合调度和实机资格保留 | 2026-09-12 |
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
| T04 | Indexed 薄壁轮廓与挤出路径 | T03 | 待验证 | 截交闭环、内外环、偏置、接缝、材料体积与层语义正确 | OCCT 精确截交、内外环定向、mid-wall、弦高采样、pipe2 实体路径、体积与层语义通过；[AUD-01 独立审查](../reviews/2026-09-12_project_algorithm_audit.md)发现当前缺陷，历史通过不代表当前完整资格 | 按 AUD-01 修改方案修复并重新验收；本轮只出方案 | 2026-09-12 |
| T05 | 区段连接与安全转位 | T04 | 已完成 | 回抽/退离/转位/接近/恢复事件完整；无沉积旋转混入 Indexed | retract/depart/index/travel/approach/prime 事件、零材料转位和安全间隙失败测试通过 | T08 将事件交给后处理并做 NC 回读核对 | 2026-09-11 |
| T06 | 参考 XYZAC 逆运动学与轴轨迹 | T05 | 已完成 | FK 回代、分支/角展开/行程/速度/加速度检查；刀长与回转中心生效 | Generic XYZAC 两分支、C 展开、软限、速度/加速度、刀长、装夹变换、非零回转中心和 FK 回代测试通过 | T08 生成参考轴轨迹；真实机型参数仍需独立标定 | 2026-09-11 |
| T07 | Indexed 路径、IPW 与运动检查 | T06 | 待验证 | 几何误差、沉积近似、喷嘴/基体/夹具/已打印体及转位扫掠检查 | 半径/层/分区误差、喷嘴 R–Z 包络、AABB、bead capsule 和连续运动细分通过；Error 阻止导出；[AUD-01 独立审查](../reviews/2026-09-12_project_algorithm_audit.md)发现当前缺陷，历史通过不代表当前完整资格 | 按 AUD-01 修改方案修复并重新验收；本轮只出方案 | 2026-09-12 |
| T08 | Indexed 输出与当前 UI 完整流程 | T07 | 待验证 | STEP→生成→检查→NC→回读；改参、取消、保存重开；pipe2 通过 | [T08—T12 审查](../reviews/2026-09-11_t08_t12_tube_workbench_review.md)；pipe2 生成 1171 points、readback passed、六件套已归档；专项/全仓回归见证据清单；[AUD-01 独立审查](../reviews/2026-09-12_project_algorithm_audit.md)发现当前缺陷，历史通过不代表当前完整资格 | 按 AUD-01 修改方案修复并重新验收；本轮只出方案 | 2026-09-12 |
| T09 | Tube Buildup 与底座多工序 | T08 | 已完成 | 多道厚壁/加厚及底座独立生成、工序顺序、跨操作衔接和格式迁移 | 同上；专项测试覆盖 multi-pass、底座独立操作和安全排序 | P01 复用多工序状态边界 | 2026-09-11 |
| T10 | Tube Continuous 几何与标架 | T09 | 已完成 | 空间中心线 RMF、连续螺旋、接缝与多层路径；低曲率无翻转 | 同上；专项测试覆盖 RMF 退化拒绝、螺旋 seam/volume 和 G1 空间链 | P01 复用连续路径契约 | 2026-09-11 |
| T11 | Tube Continuous 运动与输出 | T10 | 已完成 | 连续姿态、轴速/加速度、奇异、全运动碰撞和 NC 回读通过 | 同上；连续 FK/C 展开、运动限制、碰撞阻止导出及六件套 readback 通过 | P01 复用离线运动检查边界 | 2026-09-11 |
| T12 | 整个 Tube 工作台验收 | T08,T09,T11 | 待验证 | 三操作、错误样例、UI/脚本/HTTP、保存重开和帮助均验证 | [阶段审查](../reviews/2026-09-11_t08_t12_tube_workbench_review.md)；三尺寸中英 UI，summary collisions=[]/text_fits 全 true；真实机床状态单列未验证；[AUD-01 独立审查](../reviews/2026-09-12_project_algorithm_audit.md)发现当前缺陷，历史通过不代表当前完整资格 | 按 AUD-01 修改方案修复并重新验收；本轮只出方案 | 2026-09-12 |
| P01 | Planar Region 与层截面 | T12 | 已完成 | 通用 Setup 接入、平面区域及实体分层、孔/岛拓扑有效 | [最终证据](../reviews/evidence/2026-09-12_p07_planar_final/manifest.json)；当前源码重新覆盖稳定引用、Build CS、截层、保存重开→Stale、GUI/脚本/HTTP、问题定位和错误恢复；Planar 223 passed | P02—P07 已完成；进入 C01 | 2026-09-12 |
| P02 | Planar Zigzag Fill | P01 | 已完成 | 轮廓/填充、带孔裁剪、路径排序、覆盖/残余/越界和材料用量可核对；离线轨迹、G-code、回读和使用手册齐全 | [最终证据](../reviews/evidence/2026-09-12_p07_planar_final/manifest.json)；当前真实 STEP 142 点，六件套和 142/142 回读通过；三尺寸中英 Qt/OpenGL 图、独立覆盖/材料检查和错误恢复已复核 | P03—P07 已完成；进入 C01 | 2026-09-12 |
| P03 | Planar Offset Fill | P02 | 已完成 | 多轮偏置、窄区/消失区、多岛、接缝正确 | [P03 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p03-offset-fill-产品接入与关闭)与[证据](../reviews/evidence/2026-09-12_p03_planar/manifest.json)；OCCT 偏置覆盖孔、凹区、多岛、窄颈分裂，部分消失为可导出 Warning、全部消失为阻止导出的 Error；12 passed | 进入 P04；沿用共享 Toolpath、状态和残余量测 | 2026-09-12 |
| P04 | Planar Thin Wall | P03 | 已完成 | 单/多道、开放壁和不足道宽规则可验证 | [P04 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p04-thin-wall-产品接入与关闭)与[证据](../reviews/evidence/2026-09-12_p04_planar/manifest.json)；开放壁及闭壁同心多道、区域驱动内偏置、半道宽内移和 `reduce` Warning 已验证；7 passed | 进入 P05；保留不足道宽策略和可见诊断 | 2026-09-12 |
| P05 | Planar Spiral | P04 | 已完成 | 单连通连续 Z 路径和层间过渡；多岛输入明确拒绝 | [P05 复盘](../reviews/2026-09-12_planar_algorithm_foundation_review.md#p05-spiral-产品接入与关闭)与[证据](../reviews/evidence/2026-09-12_p05_planar/manifest.json)；至少两层、单岛无孔、拓扑对应、连续 Z、实体内插值、进给和体积检查已验证；10 passed | 进入 P06；在真实 STEP 与 UI 中核对正常、失败及恢复流程 | 2026-09-12 |
| P06 | 整个 Planar 工作台验收 | P02,P03,P04,P05 | 已完成 | 四操作生成/检查/输出/回读、改参重开和帮助通过 | [最终证据](../reviews/evidence/2026-09-12_p07_planar_final/manifest.json)与[使用手册](../guides/planar_workbench_zh.md)；当前真实 STEP Zigzag/Offset/Thin Wall/Spiral 为 142/16/6/129 点，四项六件套及回读通过；操作切换、取消、撤销/重做、问题定位、重开 Stale、三尺寸双语 UI 和恢复流程通过 | P07 已完成；进入 C01 | 2026-09-12 |
| P07 | Planar Grid/Lines 支撑生成 | P06 | 已完成 | 检测悬垂和空中岛；按 XY/Z 间隙生成支撑主体与接触层路径；共享 Toolpath、检查、G-code、回读、六件套、保存重开、脚本/HTTP、双语 UI、真实模型和图文手册通过 | [最终证据](../reviews/evidence/2026-09-12_p07_planar_final/manifest.json)与[复盘](../reviews/2026-09-12_p07_planar_support_review.md)；解析 33 段、61.86 mm³、66/66，复杂 STEP 9,662/9,662；Lines/Grid 独立方向、间距、顺序和材料真值；主体/interface Viewer 可辨；P07 150 passed、Planar 223 passed、全仓 753 passed、3 skipped、130 subtests，质量 exit 0；严格失败模型未导出 | C01：验证反向边、断链与法向歧义 | 2026-09-12 |
| C01 | Curve Region、边链与姿态输入 | P07 | 未开始 | 有向 edge 链、弧长采样、邻面或指定法向可追溯 | 可复用 STEP 选择；当前下拉项未生成路径 | 验证反向边、断链、法向歧义 | 2026-09-12 |
| C02 | Curve Buildup | C01 | 未开始 | 直线/圆弧/样条单道，端点与挤出量正确 | 待实现 | 生成单道并走共享后处理链 | 2026-09-10 |
| C03 | Curve Multi-pass Buildup | C02 | 未开始 | 多层重复堆叠、累计道高和层间连接正确 | 待实现 | 实现重复层与端点衔接规则 | 2026-09-10 |
| C04 | Curve Offset Buildup | C03 | 未开始 | 横向多道、锐角、自交和偏置失败可定位 | 待实现 | 实现横向框架与偏置裁剪 | 2026-09-10 |
| C05 | 整个 Curve 工作台验收 | C02,C03,C04 | 未开始 | 三操作全流程、边引用重绑定、参数与持久化通过 | 实机状态未验证 | 回归边链与多道例子，完善帮助 | 2026-09-10 |
| R01 | Rotary Region 与回转坐标 | C05 | 未开始 | 回转轴、轮廓、半径与角度范围有效，去除无效锁定行为 | 当前卡片 Locked 仍进入通用会话；可直接复用 Tube 连续运动和轴轨迹契约，不依赖 Freeform 曲面算法 | 注册回转操作和周期几何规则 | 2026-09-12 |
| R02 | Rotary Spiral | R01 | 未开始 | 圆柱/圆锥螺旋、螺距/方向/角速度可核对 | NX-01、OS-03 | 生成解析回转路径并走轴轨迹链 | 2026-09-10 |
| R03 | Rotary Thin Wall | R02 | 未开始 | 圆周、轴向步进、径向多道和轮廓变化可验证 | NX-05 提供轮廓层与连接参考 | 实现轮廓层与层间连接规则 | 2026-09-10 |
| R04 | Rotary Around Part | R03 | 未开始 | 局部覆盖、多周向区域、跨零点和连续回转空移检查 | NX-06 的 NCM 仅在适用回转场景参考 | 实现区域裁剪与安全连接 | 2026-09-10 |
| R05 | 整个 Rotary 工作台验收 | R02,R03,R04 | 未开始 | 三操作的轴速、周期、碰撞、输出回读与 UI 通过 | 实机状态未验证 | 验收不同回转中心、方向和限位案例 | 2026-09-10 |
| F01 | Freeform Region 与曲面计算 | R05 | 未开始 | face/边界/导引引用、UV 度量、法向、周期和修剪正确 | OS-02/03/06；当前只有选择与预览 | 构造曲面度量及投影基础并验证 | 2026-09-12 |
| F02 | Freeform Coating 单面路径 | F01 | 未开始 | UV/投影单层覆盖，三维道间距、边界和法向正确 | 待实现 | 在修剪 NURBS 与圆柱上验证路径 | 2026-09-10 |
| F03 | Freeform Thin Wall | F02 | 未开始 | 曲面导引多道/多层筋壁，沿/跨方向偏置有效 | NX-04 可参考操作与偏置语义 | 实现驱动线、壁道和起停规则 | 2026-09-10 |
| F04 | Freeform Buildup 与多面接缝 | F03 | 未开始 | 有限多层/多面覆盖、接缝连续、偏置自交与投影多解诊断 | 任意实体自动曲层分解不在本版 | 实现多面投影和受限法向加厚 | 2026-09-10 |
| F05 | 自由曲面姿态和覆盖检查 | F04 | 未开始 | Lead/Side Tilt、朝向、轴约束、碰撞及覆盖报告 | 与 Tube 连续轨迹共享基础 | 增加曲面专属误差和多解样例 | 2026-09-10 |
| F06 | 整个 Freeform 工作台验收 | F02,F03,F04,F05 | 未开始 | 三操作全流程、修改曲面引用/参数重算及保存通过 | 实机状态未验证 | 验收正常/失败曲面矩阵及帮助 | 2026-09-10 |
| X01 | Research 数据与复现实验约定 | F06 | 未开始 | 场的坐标/单位/来源、网格质量、固定基线、误差和结果模板齐备 | 研究方法不能仅挂入口名称 | 选定公开可复算案例与有限实现版本 | 2026-09-12 |
| X02 | Conical Buildup | X01 | 未开始 | 圆锥层截交、顶点奇异处理、层间距及姿态链验证 | 待实现 | 建立解析圆锥和悬垂反例 | 2026-09-10 |
| X03 | Scalar Field Surface Slicing | X02 | 未开始 | 网格标量场、层/路径提取、间距和临界点诊断完整 | OS-06 是表面等值线参考，不等同体内等值面 | 明确场所在域并实现等值提取与路径 | 2026-09-10 |
| X04 | Stress-oriented Toolpath | X03 | 未开始 | 真实张量场→主方向→连续路径；奇异/弱应力区规则和对齐指标 | 尚无已确认力学案例；不虚构强度提升 | 从公开可复算场建立数据与路径对照 | 2026-09-10 |
| X05 | Support-reduction Toolpath | X04 | 未开始 | 有约束的方向/场优化、固定基准、悬垂代理与可达检查 | 改善幅度未测，不设虚构提升率 | 固定基线并报告改善或负结果 | 2026-09-10 |
| X06 | 整个 Research 工作台验收 | X02,X03,X04,X05 | 未开始 | 四方法按计划 7.1 完成生成/检查/输出回读、改参重开；限制和失败记录完整 | 尚未实施；研究完成不能替代实验验证 | 形成四方法报告及可重开项目 | 2026-09-10 |
| I01-OWN | 自有机型默认配置与文件管理 | 用户专项授权 | 已完成 | 自有机型默认选择、自定义、导入导出、保存重开和双语界面 | [本轮复盘](../reviews/2026-09-12_own_printer_profile_review.md) | 729 passed、3 skipped；最终专项6 passed，质量门禁通过；实机标定与品牌库另列 | 2026-09-12 |
| I01 | 机型配置与后处理完整性 | X06 | 未开始 | XYZAC、XYZAB 独立模型及控制器注册、FK/IK/回读验证 | 实际设备参数/标定未核验 | 补齐第二机型与来源说明，分开记录实机资格 | 2026-09-10 |
| I02 | 全软件工作流与质量回归 | I01 | 未开始 | 六工作台、20 操作、多工序、错误恢复、双语/双后端及数值矩阵通过 | 待前述阶段完成 | 完整 pytest、质量检查、GUI 冒烟与性能基线 | 2026-09-10 |
| I03 | 本地安装包、帮助与复现实例 | I02 | 未开始 | 本地构建/包检查、干净环境启动、20 操作帮助与案例可找到 | 不包含对外发布或上传 | 生成本地交付包，核验文件清单与版本 | 2026-09-10 |
| I04 | 本版软件总验收 | I03 | 未开始 | 20 操作验收证据、范围/限制、未验证设备状态及文档齐全 | 软件验收与实机验证分别列明 | 逐项核对计划与证据，完成本地交付 | 2026-09-10 |

## 模型分工与悲观 token 预算

以下预算最初覆盖 A01—A03 完成后的 44 项任务。P07 已关闭；主表中 C01—C05、R01—R05、F01—F06、X01—X06、I01—I04 共 26 项后续未开始任务，另有 AUD-01 指出的 7 项待验证任务；当前进行中的支撑任务为 0 项。由于产品没有提供本轮精确 token，本表保留原阶段上限，不用消息字数推算消耗。单位为百万 token（M），按模型看到的输入、推理和输出总量规划；它是任务上下文预算，不是人民币账单或 ChatGPT Credits 换算。实际消耗受模型、上下文缓存、重试次数和产品计量方式影响。

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
