# 多对话工作台开发启动提示词

更新日期：2026-09-12。

本文件提供可直接复制到独立 Codex 任务中的启动提示词。每个开发任务的终点都是一个功能完整、经过当前版本验证、带真实图文手册和可追溯证据的工作台。入口、算法原型、局部测试或单张截图都不算完成。

## 使用顺序

当前台账依赖仍是：

`P07 → C01—C05 → R01—R05 → F01—F06 → X01—X06 → I01—I04`

建议按以下顺序创建独立 worktree，并在前一任务分支完成验收、提交且合入稳定集成基线后，再从该基线创建下一任务：

1. P07 Planar 支撑收尾：优先继续使用已经包含当前 P07 未提交成果的工作区，避免丢失或重复复制现有修改。
2. Curve：`codex/curve-workbench-c01-c05`。
3. Rotary：`codex/rotary-workbench-r01-r05`。
4. Freeform：`codex/freeform-workbench-f01-f06`。
5. Research：`codex/research-workbench-x01-x06`。
6. 最终集成：`codex/full-workbench-integration`。

这些工作台不宜从当前脏 `main` 同时开工。每个任务内部可以使用多 Agent 并行处理互不写同一文件的盘点、真值、测试矩阵、资料和手册核对；Qt/QSettings、VTK/OpenGL、完整回归、共享接口决策和阶段关闭由主 Agent 串行负责。

## 提示词一：P07 收尾与完整 Planar 工作台复验

```text
你正在 5AxisSclicer_V2.0 的 Codex 本地任务中工作。本任务的唯一终点是：完成 P07 Planar Grid/Lines 支撑，并重新确认 P01—P07 组成的 Planar 工作台功能完整、当前版本验证通过、图文使用说明齐全、证据可追溯，最后形成可合并的本地 Git 提交。不要停在计划、代码片段、单一算法、局部测试、占位入口或“后续再补”。

优先继续使用已经包含当前 P07 未提交成果的 checkout/worktree；不要从干净旧提交重新实现，也不要把当前大量未提交 Planar 文件遗漏在另一个目录。开始前读取当前 AGENTS.md、progress_tracker.md 的 P07 与直接依赖、Planar 最近复盘和手册、当前 git status/diff。完整读取并遵守 five-axis-workbench-development/SKILL.md 与 stage-gates.md；进入测试、失败诊断、Qt/VTK 回归和阶段验收前读取 five-axis-slicer-validation/SKILL.md。每次修改文档前重新读取当前版本和时间戳，保留用户及其他任务的修改。

你已获授权在本任务范围内持续实施、修复、运行常规本地验证、更新代码/文档/证据并创建本地提交。普通可逆实现选择自行决定，不因 token 或对话长度缩减范围。可以创建多 Agent 处理互相独立的代码盘点、解析真值、测试矩阵、证据和手册审查；不要让多个 Agent 同时编辑共享热点文件，主 Agent 负责架构、整合、Qt/完整回归、阶段判定和提交。不推送远端、不发布、不操作真实机床、不删除其他任务成果。

P07 保持当前已批准的受限范围：buildplate-only 垂直支撑、Lines/Grid、悬垂与空中岛检测、XY/Z 间隙、支撑主体和接触界面层。CuraEngine/PrusaSlicer 为 AGPLv3，只允许参考公开可观察行为并 clean-room 独立实现；记录固定来源、版本、借鉴点和许可证边界，禁止复制或改写其源码、测试和内部数据结构。Tree/Organic、桥接专用路径、双材料、一般工业支撑生态和实机资格不进入本任务。

必须建立不复制实现公式的独立真值，覆盖悬垂阈值、层间投影、平台连通性、空中岛、XY/Z 间隙、主体/interface 分层、Lines/Grid 方向与间距、窄区/消失区、路径顺序和材料量。至少保留解析或独立测量正常案例、真实 STEP 悬垂案例、无需支撑案例，以及无法连接平台、非法参数或退化区域等有意义的失败案例。

P07 必须接入项目统一产品链：Geometry/Region → SlicePlan → shared Toolpath/events → MachineAxisTrajectory → ValidationReport → Postprocessor → G-code readback。复用 Setup、坐标、资源、稳定引用、Toolpath、运动学、验证、Viewer、后台生成和后处理，不另建私有平行链。内部长度 mm、角度 rad；坐标和变换注明 Source/Model/Build/Workpiece/Machine frame。工艺、几何、Setup 或资源变化更新语义哈希并令结果 Stale，显示质量变化不得改变路径。

完成 GUI、受限脚本和 HTTP 的统一领域命令入口，覆盖创建、编辑、生成、取消、问题定位、三维查看、导出、撤销、保存重开和输入变化后重算。验证 Ready/Warning/Error/Stale，Error 阻止导出，Warning 随结果保留，取消不破坏上一份有效结果。Viewer 直接读取生成 Toolpath，支撑主体与 interface 可辨认。每个可导出结果实际生成并核对 main.gcode、toolpath.json、machine_axes.csv、warnings.json、preview.json、manifest.json；按已注册控制器语义独立回读 G-code。

重新验收 Planar 的 Region 预览以及 Zigzag、Offset、Thin Wall、Spiral、Planar Support 五种制造操作。当前源码中的创建、参数、生成、检查、Viewer、六件套、回读、保存重开和错误恢复都要可用；历史 P06 结果只能辅助定位，不能冒充本轮通过。共享文件发生变化时回归 P01—P06。

完成中文/英文 UI，并检查项目规定的代表性窗口尺寸和适用 Viewer 后端。按钮、滚动区、问题列表、单位、帮助和错误文字不能遮挡或截断。截图必须来自当前提交的真实 Qt 操作和真实渲染；widget grab、桌面点击、OpenGL/VTK 离屏证据分别如实标注。

更新 docs/guides/planar_workbench_zh.md、手册索引和稳定图片目录。手册至少包含工作台总览、Region 和五种制造操作、P07 参数与 Lines/Grid、主体/interface 三维结果、正常流程、典型错误与恢复、检查与六件套、保存重开、脚本/HTTP 和能力边界。至少补 P07 成功、错误、恢复及中英文真实截图；过期图片不继续作为当前功能证据。

按验证 Skill 先做只读 preflight，再依次运行 P07 专项、完整 Planar 专项、真实 STEP 生成/回读/UI、必要共享回归、完整 pytest 和 scripts/check_quality.py。Qt 和全仓回归串行。记录实际命令、解释器、退出码、passed/failed/skipped/subtests、首次失败、修复、JUnit/日志以及源码、输入和关键产物 SHA-256；必需门禁未完成时不得标记完成。

更新同一 P07/Planar 复盘、docs/README.md、唯一进度台账和实际 Skill 调用记录。只有上述判据全部满足，才把 P07 登记为已完成并把下一项指向 C01。Generic XYZAC、离线 FK/运动检查、回读和界面预览不得写成真实控制器、机床标定、现场碰撞、材料适配、支撑可拆卸性或试切合格；无真实证据的项目明确写“未验证”。

在 codex/p07-planar-workbench-final 分支形成职责清晰的提交，检查最终 diff 和 git status，不夹带无关修改，不 push、不自行合并 main。最终回复列出起点与最终 commit、完成范围、真实/失败案例、准确测试结果、六件套和证据路径、图文手册与截图路径、台账状态、实机未验证边界、遗留修改，以及是否已可交给后续任务合并。
```

## 提示词二：完整 Curve 工作台（C01—C05）

```text
你正在 5AxisSclicer_V2.0 的独立 Codex worktree 中。本任务的唯一终点是：按 C01→C02→C03→C04→C05 完成并验收整个 Curve 工作台，交付 Buildup、Multi-pass Buildup、Offset Buildup 三种真实可用操作、完整产品链、当前版本验证证据和图文使用说明，并形成可合并的本地 Git 提交。不要停在计划、算法原型、占位页面、单个按钮、局部测试或最小演示；只有 C05 阶段门全部满足才能报告完成。

本 worktree 的起点必须是已经包含 P07 完成提交的干净集成基线。开始前核对实际提交、台账和代码；依赖未满足时不要复制其他脏工作区或伪造完成，可先完成只读盘点和真值设计，并明确缺少的提交。读取当前 AGENTS.md、progress_tracker.md 的 P07/C01—C05、development_plan.md 的 Curve 范围、相关来源、最近复盘、当前 diff。完整读取 five-axis-workbench-development/SKILL.md 和 stage-gates.md；进入测试、Qt/VTK、失败诊断及 C05 验收前读取 five-axis-slicer-validation/SKILL.md。

你已获授权持续完成本任务范围内的实现、修复、常规本地验证、文档、证据和本地提交。普通可逆选择自行决定。可使用多 Agent 并行处理接口盘点、解析真值、失败夹具、测试矩阵、截图与手册核对；不要并发编辑共享热点，主 Agent 负责领域契约、共享文件、整合、Qt/完整回归和阶段关闭。不推送、不发布、不操作真实机床。

C01 要实现稳定保存和可重绑定的 STEP 有向 edge 链引用，检查连接、顺序、方向、开放/闭合和拓扑漂移；按弧长采样直线、圆弧、样条，产生连续位置和切向；法向来自明确邻面或用户指定方向。反向 edge、断链、双邻面歧义、缺失法向、零长或退化边必须有可定位诊断，不能静默猜测。

C02 要沿直线、圆弧和样条生成单道 Buildup，独立核对端点、弧长、切向、法向/nozzle axis、进给、挤出量和起止事件。C03 要实现有限多层 Multi-pass、累计道高及明确的换向/返回和层间连接规则；空移、Retract、Prime、Dwell 不得伪装为沉积段。C04 要用明确的局部标架生成横向多道 Offset，验证道间距、道序、锐角、反曲、标架退化、自交、裁剪和失败诊断，不得静默丢道或跨越无效区域。

建立独立真值与失败矩阵：解析直线、已知半径和圆心角的圆弧、真实 STEP 样条；使用解析几何、OCCT 独立量测或独立高密度采样核对弧长、端点、采样误差、层高、道间距、体积。失败案例覆盖反向边、断链、法向歧义/缺失、退化链、锐角/反曲自交和偏置失败。测试不能复制产品实现公式作为唯一真值。

全部结果接入 Geometry → CurvePlan/SlicePlan → shared Toolpath/events → MachineAxisTrajectory → ValidationReport → Postprocessor → G-code readback。复用 Setup、坐标、资源、引用、运动学、验证、Viewer、状态和后处理；Curve 特有几何放入独立模块，不把 Tube/Planar 专属逻辑硬塞入 Curve，也不复制公共状态机。内部长度 mm、角度 rad，坐标架明确。

完成 GUI、受限脚本和 HTTP 的统一命令入口，覆盖三种操作、边链排序/反向、法向来源、改参、Generate、Cancel、Ready/Warning/Error/Stale、问题定位、Viewer、六件套导出、回读、撤销、保存重开、引用重绑和格式迁移。Error 阻止导出，Warning 可追溯，取消保留旧有效结果。验证适用的 FK 回代、轴限、速度/加速度、奇异和整段碰撞。

每种操作生成并核对 main.gcode、toolpath.json、machine_axes.csv、warnings.json、preview.json、manifest.json；G-code 按已注册控制器语义独立回读。Viewer 必须直接读取生成 Toolpath，清楚显示单道、多层和横向多道结果。

完成中文/英文 UI 和项目规定的代表性窗口尺寸、适用 Viewer 后端检查。新建 docs/guides/curve_workbench_zh.md 并更新手册/文档索引和稳定图片目录。手册包含入口、边链顺序与反向、法向选择、三种操作参数表、正常流程、生成/取消/检查/导出、六件套、保存重开、脚本/HTTP、错误恢复和能力边界；图片来自当前版本真实操作，至少展示三种路径结果和一个断链、法向歧义或偏置失败的恢复流程，错误图清楚标注。

按验证 Skill 做 preflight；每个编号先跑直接测试，C05 再跑完整 Curve 专项、真实 STEP 三操作生成/回读/UI、必要 Tube/Planar 共享回归、完整 pytest、scripts/check_quality.py 和项目已有构建检查。Qt/全仓回归串行。记录准确命令、环境、退出码、passed/failed/skipped/subtests、首次失败及修复、JUnit/日志和 SHA-256；必需验证缺失时不得关闭 C05。

逐项更新 C01—C05、同一 Curve 复盘、唯一台账、Skill 调用记录和文档索引。Generic XYZAC 与离线检查不能证明真实控制器、真实机床标定、现场碰撞或试切；无真实证据时明确未验证，但不妨碍已定义的离线工作台关闭。

使用 codex/curve-workbench-c01-c05 分支，按 C01—C04 和 C05/文档证据形成可审查提交。最终工作区干净，不混入无关修改，不 push、不自行合并 main。最终回复列出基线/最终 commit、C01—C05 证据、真实与失败案例、准确测试结果、六件套、手册/截图/复盘/台账路径、实机边界和共享热点合并注意事项。
```

## 提示词三：完整 Rotary 工作台（R01—R05）

```text
你正在 5AxisSclicer_V2.0 的独立 Codex worktree 中。本任务的唯一终点是：按 R01→R02→R03→R04→R05 完成并验收整个 Rotary 工作台，交付 Rotary Spiral、Thin Wall、Around Part 三种真实可用操作、完整产品链、当前版本验证证据和图文使用说明，并形成可合并的本地 Git 提交。不要停在计划、单条螺旋、路径显示、G-code 输出或局部测试；只有 R05 阶段门满足才可报告完成。

起点必须是已包含 C05 完成提交的干净集成基线。开始前读取当前 AGENTS.md、progress_tracker.md 的 C05/R01—R05、development_plan.md 的 Rotary 范围、reference_research.md 的相关条目、最近 Tube/Curve 复盘和当前 diff。核对依赖的实际提交、证据和代码。完整读取 five-axis-workbench-development/SKILL.md 与 stage-gates.md；进入测试、失败诊断、Qt/VTK 和 R05 验收前读取 five-axis-slicer-validation/SKILL.md。

你已获授权持续实施、修复、运行常规本地验证、更新文档/证据并创建本地提交。可以使用多 Agent 并行处理接口盘点、解析真值、周期失败矩阵、资料许可证、测试和手册检查；禁止并发编辑共享热点，主 Agent 负责坐标/周期/运动语义、整合、Qt/全仓回归和阶段关闭。不复制其他脏工作区，不 push、不发布、不操作真实机床。

R01 实现真实 Rotary 操作及回转 Region，去除无效 Locked/通用会话占位行为。领域模型包含回转轴原点和单位方向、正方向、零角、轮廓、半径、角度范围、周期展开、非零回转中心和稳定几何引用；验证非默认 Build CS、不同轴向和拓扑漂移。Region 若只分析/预览，明确 preview-only。

R02 实现圆柱和圆锥 Spiral，参数覆盖螺距、方向、起止角、回转角速度、道宽、层高、进给和挤出；核对角速度与线速度、机床轴限的关系，角度连续展开，0/360° 不跳变。R03 实现圆周、轴向步进、径向单/多道及受限轮廓变化，明确定义接缝、层间连接、Retract/Prime 等事件和不足道宽/退化区域诊断。R04 实现局部表面区域、多周向区域、跨零点裁剪及结构化安全连接，检查覆盖遗漏、跨区空移、连续方向和不必要长绕行。

建立独立真值：已知轴、非零中心、半径、轴长、螺距和圈数的圆柱螺旋；半径线性变化的圆锥螺旋；已知圆周、轴向层数和径向道数的 Thin Wall；350°→20° 等跨零点 Around Part。独立核对端点、角度、螺距、路径长度、法向/切向、层数、道数、体积和周期连接。失败矩阵覆盖零轴、无效半径/螺距、锥顶退化、周期歧义、不可达、轴限、速度/加速度、碰撞、控制器轴语义和回读不一致。测试不能复制实现公式作为唯一证据。

接入 Geometry/RotaryRegion → SlicePlan → shared Toolpath/events → MachineAxisTrajectory → ValidationReport → Postprocessor → G-code readback。内部 mm/rad，明确 Source/Model/Build/Workpiece/Machine frame。保留 ToolpathPoint 的位置、法向、切向、喷嘴轴、工艺、operation/stage/layer/region 和事件语义，严格分离 imported_nc 与 generated_toolpath。输入、工艺参数或回转坐标变化必须更新语义哈希、触发 Stale，并验证修复后的重新生成；显示质量变化不改变路径语义。连续角展开、工具长度、IK 解支、限位、奇异、速度/加速度、整段运动、FK 回代以及喷嘴/基体/夹具/机床/已打印体碰撞均按影响检查。

GUI、受限脚本和 HTTP 走同一领域命令，覆盖创建/编辑三种操作、回转坐标、生成、取消、状态、问题定位、Viewer、导出、回读、撤销、保存重开、引用重绑和迁移。验证 Ready/Warning/Error/Stale，Error 阻止导出，Warning 进入结果，取消保留旧有效结果。每种操作实际生成并回读六件套：main.gcode、toolpath.json、machine_axes.csv、warnings.json、preview.json、manifest.json。

完成中文/英文 UI，分别检查 1366×768、1600×900、1920×1080 和适用 Viewer 后端；核对参数名、单位、范围、默认值、帮助和禁用原因。创建 docs/guides/rotary_workbench_zh.md 并更新索引和 docs/guides/assets/rotary/。手册包含支持范围、回转轴与坐标、三种操作、参数、状态、正常流程、取消/失败恢复、周期接缝、三维路径与轴轨迹、检查、六件套、保存重开和实机边界。当前版本真实截图至少覆盖总览、坐标设置、三种结果、跨周期、一个轴限/碰撞错误恢复、导出和重开；错误图明确标注。

按验证 Skill 做 preflight，完成 Rotary 解析真值与失败矩阵、三操作领域/产品链、GUI/脚本/HTTP、project I/O、Toolpath/IK/FK/运动/碰撞、真实 CAD 完整流程、六件套/回读、双语多尺寸 UI、scripts/check_quality.py、项目构建和包检查及完整 pytest。Qt/全仓回归串行，不硬编码历史测试数；保存本轮准确数字、退出码、JUnit/日志、环境与输入/源码/产物指纹，skip 和未验证项单列。

更新 R01—R05、同一 Rotary 复盘、唯一台账、文档索引和实际 Skill 记录。Generic XYZAC 仅是参考机型离线资格；真实控制器语义、实际机床参数/标定、现场碰撞和试切无证据时明确未验证。

使用 codex/rotary-workbench-r01-r05 分支形成可审查提交。最终工作区干净，不夹带无关文件，不 push、不自行合并 main。最终回复列出起点/最终 commit、R01—R05 完成证据、真实/失败案例、准确测试结果、六件套、手册/截图/复盘/台账路径、实机边界和共享热点合并注意事项。
```

## 提示词四：完整 Freeform 工作台（F01—F06）

```text
你正在 5AxisSclicer_V2.0 的独立 Codex worktree 中。本任务的唯一终点是：按 F01→F02→F03→F04→F05→F06 完成并验收整个 Freeform 工作台，交付 Coating、Thin Wall、Buildup 三种真实可用操作、姿态/覆盖/运动检查、完整产品链、当前版本证据和图文使用说明，并形成可合并的本地 Git 提交。不要停在单个投影算法、UV 线条、占位 UI、局部测试或概念演示；只有 F06 阶段门满足才可报告完成。

起点必须是已包含 R05 完成提交的干净集成基线。开始前读取当前 AGENTS.md、progress_tracker.md 的 R05/F01—F06、development_plan.md 的 Freeform 范围、reference_research.md 的 NX-04/NX-06/OS-02/OS-03/OS-06、相关复盘和当前 diff。核对依赖的实际提交、证据和代码。完整读取 five-axis-workbench-development/SKILL.md 与 stage-gates.md；进入测试、失败诊断、Qt/VTK 和 F06 验收前读取 five-axis-slicer-validation/SKILL.md。

你已获授权持续实施、修复、运行常规本地验证、更新文档/证据并创建本地提交。可以使用多 Agent 并行处理接口盘点、曲面真值、失败样例、资料许可证、测试矩阵和手册检查；禁止并发编辑共享热点，主 Agent 负责 UV/修剪/投影/姿态边界、整合、Qt/完整回归和阶段关闭。不复制其他脏工作区，不 push、不发布、不操作真实机床。

F01 实现 face、修剪边界、孔、导引线和有限多面邻接的稳定引用、保存重绑和拓扑漂移诊断；建立 UV 参数域、三维度量、法向、周期、修剪分类，处理方向反转、周期缝、退化区和法向歧义。Region 若只分析/预览，明确 preview-only。

F02 的 Coating 提供 UV 裁剪与投影两种受限入口，以三维物理距离控制道间距，处理修剪边界、孔、断开、排序、空移和周期缝。F03 的 Thin Wall 由曲面边界或导引线驱动，实现沿/跨方向的有限多道、多层筋壁，明确定义层高、道宽、step-over、起停和连接。F04 的 Buildup 实现有限层数法向加厚及有限多面连续区域投影，诊断法向偏置自交、投影多解、接缝断裂、间隙/重叠和不支持拓扑。任意实体自动曲层分解不进入本版。

F05 明确定义 Lead Tilt、Side Tilt、法向、切向、nozzle axis 和朝向符号；参数必须真实改变姿态与轴轨迹。检查连续性、翻转、IK 多解/跳支、奇异、限位、速度/加速度和 FK 回代；碰撞范围包含喷嘴、基体、夹具、机床及已打印体，并执行整段插值检查或采用写明误差边界的保守包络。覆盖报告分别给出三维道间距、边界残余、遗漏、重叠、曲面/姿态误差和体积，不用单一容差替代全部指标。

建立独立真值：解析平面/参数面、解析圆柱周期缝、真实修剪 NURBS、法向连续和不连续的多面接缝、投影多解、法向偏置自交。使用解析公式、独立采样/积分、CAD 内核量测、Toolpath 检查和 FK 回算核对 UV→XYZ、弧长、法向、三维间距、边界、材料量和姿态；测试不能复制实现算法作为唯一证据。

全部操作接入 Geometry/SurfaceRegion → SlicePlan → shared Toolpath/events → MachineAxisTrajectory → ValidationReport → Postprocessor → G-code readback。复用 Setup、坐标、资源、引用、运动学、验证、Viewer、状态和后处理，Freeform 的 UV/投影逻辑留在独立模块，严格分离 imported_nc 与 generated_toolpath。内部 mm/rad，所有坐标架和变换明确；输入、引用或工艺变化更新语义哈希、使结果 Stale，并验证修复或改参后的重新生成，显示变化不改语义哈希。

完成 GUI、受限脚本和 HTTP 统一入口，覆盖曲面/边界/导引选择、三操作、姿态参数、Generate/Cancel、Ready/Warning/Error/Stale、问题定位、Viewer、撤销、导出/回读、保存重开、引用重绑和迁移。Error 阻止导出，Warning 随结果保存，取消不破坏旧有效结果。每种操作生成并核对六件套和控制器独立回读。

完成中文/英文 UI，分别检查 1366×768、1600×900、1920×1080 和适用 Viewer 后端；核对参数名、单位、范围、默认值、帮助和禁用原因。创建 docs/guides/freeform_workbench_zh.md，更新索引和 docs/guides/assets/freeform/。手册包含支持曲面和边界、Region、UV 与投影区别、三种操作、Lead/Side Tilt、参数、正常流程、取消、投影多解/自交/法向/不可达/碰撞恢复、三维路径/接缝/覆盖/轴轨迹、六件套、保存重开和能力边界。图片必须来自当前提交真实操作，至少覆盖工作台总览、主要参数、三种操作、姿态、多面接缝、一个错误恢复、导出和保存重开。

按验证 Skill 做 preflight，完成 UV/修剪/周期/法向/投影真值、NURBS/圆柱/多面/失败矩阵、三操作产品链、引用与项目 I/O、GUI/脚本/HTTP、Toolpath/姿态/IK/FK/运动/碰撞、覆盖报告、真实 CAD、六件套/回读、双语多尺寸 UI、scripts/check_quality.py、构建和包检查及完整 pytest。Qt/全仓回归串行，记录准确结果、skip、退出码、日志/JUnit 和指纹；必需门禁未完成不得关闭 F06。

更新 F01—F06、同一 Freeform 复盘、唯一台账、文档索引和实际 Skill 记录。外部来源固定版本/许可证和实际借鉴点；不得把供应商宣传或外部 README 当作本地正确性证据。Generic 参考机型、真实控制器、实际标定、现场碰撞和试切分别表述。

使用 codex/freeform-workbench-f01-f06 分支形成可审查提交。最终工作区干净，不夹带无关修改，不 push、不自行合并 main。最终回复列出起点/最终 commit、F01—F06 证据、真实与失败曲面、准确测试结果、六件套、手册/截图/复盘/台账路径、范围限制、实机边界和共享热点合并注意事项。
```

## 提示词五：完整 Research 工作台（X01—X06）

```text
你正在 5AxisSclicer_V2.0 的独立 Codex worktree 中。本任务的唯一终点是：按 X01→X02→X03→X04→X05→X06 完成并验收整个 Research 工作台，交付 Conical Buildup、Scalar Field Surface Slicing、Stress-oriented Toolpath、Support-reduction Toolpath 四种真实可复算操作、完整产品链、当前版本证据和图文使用说明，并形成可合并的本地 Git 提交。不要停在研究计划、数据格式、算法原型、离线脚本或示意图；只有 X06 阶段门满足才可报告完成。

起点必须是已包含 F06 完成提交的干净集成基线。开始前读取当前 AGENTS.md、progress_tracker.md 的 F06/X01—X06、development_plan.md 的 Research 范围和验收规则、reference_research.md、相关复盘与当前 diff。完整读取 five-axis-workbench-development/SKILL.md 与 stage-gates.md；进入测试、失败诊断、Qt/VTK 和 X06 验收前读取 five-axis-slicer-validation/SKILL.md。依赖缺失时不得伪造，可先完成不依赖它的数据合同和只读盘点并报告准确缺口。

你已获授权持续实施、修复、运行常规本地验证、更新文档/证据并创建本地提交。可以使用多 Agent 并行核验公开数据、解析真值、测试矩阵、截图和手册；主 Agent 必须亲自负责研究结论边界、复杂算法、共享集成、Qt/完整回归和阶段判定。不 push、不发布、不使用付费外部计算、不操作真实机床。

X01 先建立可执行的数据与复现实验合同：场所在表面或体域、节点/单元关联、坐标架、单位、张量顺序、网格质量、缺失值、插值、来源、版本/哈希/许可证、确定性随机种子、固定基线、误差指标、结果模板和复现命令。选择公开可复算案例，固定 URL/commit 和实际借鉴点；按项目契约独立实现。

X02 的 Conical Buildup 实现圆锥层与网格或 BRep 截交，验证层间距、姿态链、顶点奇异区；至少有解析圆锥正常例和悬垂/顶点退化例。X03 明确 Scalar Field 的域、关联、单位和插值，实现等值层/路径、间距、断裂分支和临界点诊断；不能把表面等值线资料扩写为未实现的体内等值面。

X04 的输入必须是真实、公开、可复算且固定版本的应力张量场，记录几何、材料、载荷、边界、网格/求解、坐标/单位、张量约定、来源和哈希；实现主方向、符号连续、退化特征值/弱应力区、路径追踪和方向对齐指标。缺少张量、单位或坐标时明确拒绝。X05 在运行优化前冻结基准路径、方向、机型约束、阈值、代理指标和种子，实现受限方向/层场优化、悬垂代理、可达性和必要运动/碰撞检查；改善为零或变差也保存负结果。

结论严格受证据约束：方向对齐不能写成强度或寿命提升；没有对应力学计算或实验时强度保持“未验证”；悬垂代理降低不能写成实际支撑材料减少或打印成功。禁止虚构应力场、改善比例、求解器结果、实验或试切；来源未知、负结果、失败、skip 和未验证项如实保留。

四种方法都接入 Geometry/Field → SlicePlan → shared Toolpath/events → MachineAxisTrajectory → ValidationReport → Postprocessor → G-code readback，不形成孤立脚本。完成 GUI、受限脚本和 HTTP 的统一命令，覆盖创建/编辑、数据来源、生成/取消、Ready/Warning/Error/Stale、Viewer、方向场/诊断覆盖层、验证、六件套、回读、保存重开、引用/指纹变化和错误恢复。内部 mm/rad，坐标架明确；Error 阻止导出，Warning 随结果保留。

每种方法至少有正常、边界和有意义的失败案例，并核对适用的轴轨迹、FK、限位、运动、碰撞和控制器回读。每个可导出结果生成六件套；研究来源、固定基线、方法参数、候选结果和指标另以结构化报告随包保存。

完成中文/英文 UI、两个适用 Viewer 后端和项目规定的代表性窗口尺寸检查。创建 docs/guides/research_workbench_zh.md 并更新索引和稳定图片目录。手册包含入口、四操作、场数据格式/来源、固定基线、参数、正常流程、错误恢复、方向场/三维结果判读、验证、六件套、保存重开和结论边界；截图来自当前版本真实运行，覆盖四方法和错误恢复。

按验证 Skill 做 preflight，再跑当前编号专项；X06 运行完整 Research 矩阵、真实数据/模型、GUI/脚本/HTTP、保存重开、六件套/回读、双语多尺寸 UI、scripts/check_quality.py、构建和包检查、性能基线及完整 pytest。Qt/全仓回归串行。保存准确命令、环境、退出码、passed/failed/skipped、构建/包检查结果、日志/JUnit、输入/源码/产物指纹和首次失败/修复。不得用历史测试冒充本轮结果。

逐项更新 X01—X06、同一 Research 复盘、唯一台账、文档索引和实际 Skill 记录。参考机型离线结果与真实控制器、真实机床、现场碰撞、试切和材料/力学实验资格分开表述。

使用 codex/research-workbench-x01-x06 分支形成可审查提交。最终工作区干净，不夹带无关修改，不 push、不自行合并 main。最终回复列出起点/最终 commit、四方法与 X01—X06 证据、数据/基线来源、正常/负面/失败案例、准确测试结果、六件套和研究报告、手册/截图/复盘/台账路径、结论边界、实机/实验未验证项和共享热点合并注意事项。
```

## 提示词六：多分支最终集成与全软件验收（I01—I04）

```text
你正在 5AxisSclicer_V2.0 的独立最终集成 worktree 中。本任务的唯一终点是：语义正确地集成已完成的 P07、Curve C01—C05、Rotary R01—R05、Freeform F01—F06、Research X01—X06 分支，完成 I01—I04，交付六个工作台、本版 21 种制造操作（原计划 20 种＋1 个 Planar Support）都真实可用且经过当前版本验证的完整软件、本地交付包、可重开实例、总图文使用说明和完整证据。Git 合并成功、应用启动、单项测试或历史截图都不算验收完成。

你已获授权在本集成 worktree 内持续完成分支盘点、非破坏性合并、冲突修复、跨模块实现、常规本地测试、真实 GUI 检查、截图、手册、交付包、证据、复盘、台账和本地提交。可使用多 Agent 做只读提交图盘点、操作矩阵、证据/手册审计、静态接口扫描和互不冲突的非 Qt 专项；主 Agent 亲自读取适用 Skill，负责合并策略、共享语义、Qt/完整回归、I01—I04 判定和最终提交。不 push、不发布、不操作真实机床。

开始前读取当前 AGENTS.md、progress_tracker.md 的 P07/C/R/F/X/I 全部相关行、development_plan.md 的操作和验收规则、reference_research.md、各分支复盘/交接和手册索引。完整读取 five-axis-workbench-development/SKILL.md、stage-gates.md 和测试前的 five-axis-slicer-validation/SKILL.md；制作可追溯 ZIP 时再读取 artifact-package-verify Skill。核对当前分支、工作树、提交图、merge-base、候选分支 tip、未提交修改和证据，不猜分支名。

先建立“分支/ref/SHA → 台账编号 → 主要文件 → 共享热点 → 测试/证据 → 依赖”清单。按可靠基线 → P07 → Curve → Rotary → Freeform → Research → I01—I04 的顺序集成；根据提交图避免重复 cherry-pick。使用保留历史、可审查的非破坏性 merge/cherry-pick，禁止 reset --hard、整文件 ours/theirs 覆盖和未经核对的删除。每合入一个工作台，先运行该模块关键契约/导入/产品流程测试再继续。

共享热点必须做语义三方合并：工作台/操作注册、ui.py、controller/service、project_io/schema/migration、command_kernel、automation_routes、Toolpath/events、机型/运动学、validation、postprocessing、Viewer、翻译、测试夹具、索引和 progress_tracker。检查重复 operation id、路由/菜单覆盖、schema 漂移、GUI/脚本/HTTP 默认值与校验不一致、坐标/单位/来源/哈希漂移、状态机不一致、六件套和回读语义不一致、翻译键丢失及 QSettings/全局注册串扰。冲突标记消失不等于语义正确。

验收范围共 21 种制造操作：Tube 的 Thin Wall Indexed/Buildup/Continuous；Planar 的 Zigzag/Offset/Thin Wall/Spiral，加上 P07 Planar Support；Curve 的 Buildup/Multi-pass/Offset；Rotary 的 Spiral/Thin Wall/Around Part；Freeform 的 Coating/Thin Wall/Buildup；Research 的 Conical/Scalar Field/Stress-oriented/Support-reduction。Lines/Grid 是 Planar Support 的两种 pattern，不另计为两个操作；Region 等节点属于预览/分析入口，不计制造操作，也不得当作可制造 NC。入口锁定、空实现、假数据、只有脚本、只有路径显示或只有历史证据的项目不计完成。

I01：XYZAC 与 XYZAB 是独立注册的参考机型/控制器语义，明确轴顺序、旋转中心/方向、坐标、工具长度、单位、零位、限位、速度/加速度、角度展开、奇异和解支。分别验证 IK、FK 回代、后处理与回读，以及非零回转中心、刀长、不可达、限位和连续运动。建立 21×2＝42 个操作—机型组合的双机型离线资格矩阵，每项记录通过、失败或明确不支持；覆盖 42 项不等于全部通过。确实不支持的组合用领域约束和 UI 原因明确表达，不能声称通过。全部醒目标记为参考机型离线仿真。

I02：建立六工作台完整操作矩阵，逐项覆盖输入、参数生效、Generate/Cancel、Ready/Warning/Error/Stale、旧结果、撤销、问题定位、Viewer、轴轨迹、验证、六件套、回读、改参、保存重开、引用重绑/数据指纹。GUI、受限脚本和 HTTP 走同一领域命令。检查多 Operation 顺序、基体/IPW、空移与事件、项目迁移、跨工作台切换、错误修复。核对中文/英文、适用的两个 Viewer 后端及代表性窗口尺寸，截图来自当前集成提交真实操作。

I03：构建本地安装/交付包并做干净环境启动验证，不对外发布。记录版本、commit、依赖/许可证、BOM、文件清单和逐文件 SHA-256。六个工作台的示例可找到、可重开；21 种制造操作均有正常输入、参数、期望指标以及失败/恢复说明。整理总览、安装、Setup、六工作台、所有操作、机型/控制器、检查/回放、导出/回读、脚本/HTTP、保存重开、错误恢复和边界的总图文手册，复核各模块手册与当前 UI。

I04：独立做证据到判据审计。每个“通过”能追到当前源码/输入指纹、命令、产物或真实截图。确认可导出操作的六件套、Error 阻止输出、Warning 随报告、回读独立核验。保留首次失败、负结果、skip、性能和未验证边界。真实机床/控制器参数与标定、现场碰撞和试切可以保持未验证，但本版离线软件必要功能或证据缺失时必须继续修复，不能用限制说明规避验收。

全部集成稳定后，按验证 Skill 串行运行受影响专项、完整 pytest、scripts/check_quality.py、GUI 冒烟、必要性能基线、构建/安装检查。保留准确命令、环境、退出码、passed/failed/skipped、JUnit/日志、截图、源码/输入/产物指纹。Qt/QSettings、VTK/OpenGL 与完整回归不得并发启动两套；没有新证据、代码或环境变化时不重复相同失败尝试。

每个合并阶段和 I01—I04 更新对应复盘、唯一台账、实际 Skill 记录、docs/README.md 和手册索引。证据和交付包使用稳定目录、manifest 和 SHA-256，不覆盖失败日志，不编造已清理产物。把“本版 21 种制造操作＝原计划 20 种＋1 个 Planar Support”的口径同步到 development_plan.md、progress_tracker.md、I02/I04 验收矩阵、交付包 manifest/BOM、示例索引和总手册；Lines/Grid 和 Region 的计数规则保持一致。

使用 codex/full-workbench-integration 分支形成职责清晰的提交，最终工作区干净。不要自行 push、发布或合并 main。最终回复列出最终分支/commit、实际合入的 refs/SHA/顺序、共享冲突及解决、I01—I04 结果、完整操作矩阵和双机型离线矩阵、GUI/脚本/HTTP/双语/Viewer/全仓/质量/构建/安装/性能的准确结果与 skip、交付包/BOM/哈希、可重开案例、总手册/真实截图/证据路径、实机/实验未验证范围，以及合入 main 的最短非破坏性步骤。
```

## 统一完成定义

所有开发提示词都采用以下关闭标准：

- 工作台全部计划操作都是真实领域功能，不是入口或假数据。
- GUI、受限脚本、HTTP、Viewer、状态机、保存重开、六件套和 G-code 回读形成同一产品闭环。
- 有独立正常真值、边界案例、失败案例和真实模型/数据案例。
- 当前提交完成专项、必要共享回归、完整回归、质量门禁和真实 UI 检查；结果数字和 skip 如实归档。
- 图文手册使用当前提交生成的真实截图，包含正常流程、错误恢复、输出、保存重开和能力边界。
- 复盘、证据、唯一台账和 Skill 调用记录一致。
- 本地分支提交清晰且可合并；对外推送、发布和真实机床操作仍需单独授权。
