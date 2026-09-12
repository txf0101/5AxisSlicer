# Rotary R01—R05 实施与验收复盘

日期：2026-09-13。分支：`codex/rotary-workbench-r01-r05`。C05 完成基线：`859d590b7178403cb08c9791164655c057e54a35`。本轮不 push、不发布、不合并 `main`。

> 复盘状态：R01—R05 离线阶段门已满足。当前已有 37 项 Rotary 专项、820 项全仓通过、质量门、四个真实 STEP 产品六件套、10 张当前 Qt 证据图，以及 wheel/sdist 构建、Twine 检查和隔离安装导入证据。Generic XYZAC 与真实机床资格边界仍按第 10 节执行。

## 1. 任务范围和制造契约

R01 将原有 Locked/通用会话入口替换为真实 Rotary 操作、Rotary Region 和回转坐标。R02—R04 对应 Rotary Spiral、Rotary Thin Wall 和 Around Part。R05 要求三操作进入同一产品链，并通过 GUI/受限脚本/HTTP、项目 I/O、轨迹、运动、碰撞、回读、六件套、双语多尺寸 UI 和全仓回归。

当前链路为：

`Geometry/RotaryRegion → RotaryPlan → shared Toolpath/events → prescribed MachineAxisTrajectory → ValidationReport → Postprocessor → G-code readback`

几何在 Source 坐标定义，经过已应用的 `T_build_from_source` 进入 Build Toolpath，再通过安装变换和机床拓扑进入 Workpiece/Machine。内部长度为 mm、角度为 rad。每个 ToolpathPoint 保留位置、法向、切向、喷嘴轴、工艺参数、operation/stage/layer/region 和点类型；imported NC 与 generated Toolpath 使用不同的来源标识和加载路径。

## 2. 修改前的 Open5x 与 NX 资料研究

### 2.1 Open5x Grasshopper 原始定义

本轮固定上游 [FreddieHong19/Open5x commit `500a786e51447b47e00d2a5ca3dcc938ae542926`](https://github.com/FreddieHong19/Open5x/tree/500a786e51447b47e00d2a5ca3dcc938ae542926)，而非将相邻工作区的 Python port 当作上游真值。许可证为 MIT，Copyright © 2022 Freddie Hong。

为读取二进制 `.gh`，在仓库 `tmp/gh_extract_env` 中建立隔离 Python 3.12.7 环境，安装 `pythonnet==3.0.5`，并使用 McNeel 官方 NuGet 的 Grasshopper/GH_IO 与 RhinoCommon `8.35.26251.13001` net48 DLL。三份定义均与固定上游提交的原始字节一致；GH_IO 内存重跑均为 `ReadFromFile=True`、`MessageCount=0`，提取目录为 `tmp/grasshopper_extracted/`。当前机器没有 Rhino/Grasshopper 或 Heteroptera 运行环境，而 `open5x_supportless_slicing_ver2.gh` 还记录了 Heteroptera `0.6.2.4` 和 GhPython 依赖；因此证据只支持静态解析，不支持声称 Grasshopper 定义已执行。

| 上游文件 | SHA-256 | 文档对象数 | 可核对内容 |
| --- | --- | ---: | --- |
| `Open5x_Gcode_0503.gh` | `891506E19DCA0005683860038BBAE99ECFBC2086F6FEC9723BF01A2E26FE2565` | 104 | IK、Simulation、Speed Compensation、Extrusion、Travel、Retract/Deretraction、Tool Path 和 G-code |
| `open5x_supportless_slicing_ver2.gh` | `96B856187A6D8FA06F8F3BBF1DC7483F7A664650F4FE203745EC4444EC378990` | 116 | 支撑减少切片的点/法向/路径数据流 |
| `2022_03_22_open5x_supportless_surface_Lite.gh` | `6E0259CD5FBDD1F34F3B99D17D0BB18F0A5997AF1C4FDCDDA8B667859EFAEA0E` | 122 | 表面路径、运动、挤出和模拟组织 |

提取到的 C# 挤出脚本使用道截面 `(w-h)h + π(h/2)²`，再结合段长、丝材直径和 extrusion multiplier 计算 E；另一脚本在 Travel 索引前后插入 Retract/Deretraction 索引。`LITE_conformal_pathing` 的可见输入包含 Supportless brep、Layer Height、`z_edge`、Path Width 和 Number of Perimeter；`Tool Path Evaluation` 把 Curve、Guide Surface 和 Travel Height 组织为 Plane、Segment Length、Entering/Exiting Vector、Path Changing Points 和 Travel Path Length。这些事实支持稳定选边、路径几何、导向面、姿态、机床轴、进给、挤出和离散事件分层；原始 `EdgeIndex=5` 也说明直接拓扑索引会有漂移风险，不能取代本项目的几何签名和唯一重绑。Open5x 没有给出当前任务所需的 Rotary Region、圆柱/圆锥解析螺旋、350°→20° 周期裁剪、最近等价相位、当前机型轴限和整段碰撞实现。当前本地算法为独立实现，未复制或移植 Grasshopper 定义，运行时不新增 Open5x 依赖。

### 2.2 Siemens NX 公开页面

本轮核对了以下 Siemens 官方公开内容：

- [NX Additive Manufacturing Multi-Axis](https://plm.sw.siemens.com/en-US/nx/products/nx-am-multi-axis/)：列出 rotary deposition、沿零件轴生成圆形特征、在圆件上添加局部特征、按 draft angle 对齐打印头，以及用于 flange 等特征的 Thin Wall；
- [NX 2512 发布说明](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-december-2512/)：列出 Rotary Buildup 的 profile slicing、infill ramp、slice boundary 和局部 build-style 改进；
- [NX 2606 发布说明](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-2606-june-2026/)：列出圆柱零件多区域之间的 continuous rotary non-cutting moves，其中 Circular NCM 保持回转运动，Rotary spline NCM 用于不同高度间的平滑连接。

Siemens Documentation Center 中 `Manufacturing Additive` 产品 ID 为 `289330135`，相关 NX Additive Manufacturing 条目元数据为 `PUBLISHED`，正文访问属性为 private，公开 landing URL 只返回通用应用外壳。当前没有找到可开放访问且包含 Rotary Buildup/Thin Wall 算法正文的 NX 技术手册或 PDF。因此，本轮只使用官方公开页的可观察产品语义，没有声称读取私有 NX Help，也没有将公开功能介绍当作本地数学真值。

## 3. 设计判断

### 3.1 规定相位与机床轴分离

RotaryPlan 在每个点保留 `unwrapped_angle_rad`、轴向坐标、半径、位置/法向/切向/喷嘴轴和工艺语义。它与 ToolpathPoint 一一对应。通用 XYZAC IK 可以在等价解中选支；Rotary 必须额外保留连续工艺相位，用于周期连续和时间计算。工艺相位不直接等于通用机型的 C 轴字，实际 A/C 仍由机床拓扑和姿态 IK 求解并做 FK 回代。

审计曾发现规定相位只参与段时间，没有约束 `_solve_rotary()` 的 C 轴等价解支。当前 prescribed solver 已用前两个非奇异样本建立 phase→C 的正/负映射，之后使用 `preferred_c` 选择连续等价分支，不一致时报 `rotary.phase_machine_axis_mismatch`。每段时间同时受线路径进给和计划角速度约束。这一映射是 Generic XYZAC 离线参考机型的约束，不把工艺 phase 普遍宣称为任意控制器的 C 轴字。

### 3.2 速度、事件和连接

每段时间取线路径进给所需时间、回转相位变化/设定角速度所需时间两者的较大值。机床轴速度、相邻样本加速度、从静止到首段和末段到静止的起停加速度由生成后的轴样本检查。后处理现以 `G93` 逆时间进给写入这些段时长，回读要求 `G93/G94` 切换和逐段 `F=60/Δt` 一致；删除 `G93` 或篡改逆时间进给均失败。

沉积路径用 `index_start/prime/index_end/retract`。首道前从净空点 safe approach；多道之间先 Retract，再径向 Depart 到净空半径，在净空半径上插值相位和轴向位置，然后 Approach/Prime；末道后执行 Retract、safe depart 和 finish。入口、段间和出口因此都进入 IK/限位/碰撞链。非零 Dwell 在共享 G-code 尚无 G4 事件回读契约，所以当前明确报 `rotary.dwell_unsupported`，不生成伪停留。

## 4. R01—R04 实现

### R01：Rotary Region 与回转坐标

领域模型包含非零轴原点、轴单位方向、零角方向、回转正方向、轴向轮廓、半径起止值、有向角区域、周期展开以及 axis/contour/surface 的稳定 `GeometryReference`。选面只接受 STEP 解析为圆柱或圆锥的 face；axis edge 作为轴向稳定参考且必须与主面轴向平行，轴原点来自选定回转面的解析轴线。`preview_only` 保留为区域分析属性，产品生成明确禁止。

已有解析用例对非零中心 `O=(10,-20,5)`、`positive_direction=-1`、CW 和非默认 Build 变换 `(x',y',z')=(z+7,x-11,y+13)` 做逐点检查。审计后已将轴向范围从 face AABB 角点改为 face 边界 edge/vertex 的实际几何点投影，并对多面补充表面类型、轴向平行、轴线同轴、圆柱半径一致以及圆锥参数/半径连续性检查；圆锥方向反转时的半径斜率也显式按轴向修正。真实 X 轴圆柱经 Build 变换对齐机器 C 轴后完成产品链；未对齐的装夹使用 `rotary.axis_not_aligned_with_machine_c` 显式拒绝。拓扑 ID 漂移重绑后重新从 face 派生轴心与 profile，测试核对了轴心、方向、半径、轴向范围和路径不变。

### R02：Rotary Spiral

圆柱螺旋使用常半径，圆锥螺旋按轴向坐标线性改变半径，法向含锥度。起止角按 CCW/CW 连续展开，轴向终点由展开圈数乘螺距决定，超出 profile 报 `rotary.pitch_exceeds_profile`，接近零半径报 `rotary.cone_apex_degenerate`。

现有独立常数夹具覆盖三圈圆柱和两圈圆锥的端点、角度、长度、体积、线性半径斜率、法向/切向正交，并覆盖 CW 和反正方向。产品链测试增加 phase/C 连续等价映射，逐段断言时长不小于 `|Δphase|/ω`，并用 G93 回读核对实际 NC 段时间语义。实体 STEP 圆锥从 15 mm 线性变为 9 mm，完成生成、轴轨迹、检查、后处理、回读和六件套。

### R03：Rotary Thin Wall

Thin Wall 按轴向步距取层，每层生成设定径向道数，道之间按设定间距改变半径。每条路径为完整圆周，连续道交替方向。目标壁厚不足时支持 Error 或减为单道的 Warning 策略；设定道数/间距超出壁厚时拒绝。

当前受限轮廓支持常半径或沿轴向线性变半径。contour edge 引用可保存和重绑，也已参与 profile 轴向起止范围裁剪；当前仍不支持沿任意 contour edge 生成非线性径向轮廓。不整除的轴向步距保留 profile 终点，径向道宽和间距超出目标壁厚时拒绝；12 圈真值与首段 safe approach、段间 Retract→Travel→Prime、末段 safe depart/finish 顺序均有专项断言。

### R04：Around Part

Around Part 支持手工定义的多个有向角区域，每个区域按轴向步距生成局部周向道。`350°→20°` CCW 展开为 `350°→380°`；下一区域的起点选择距前一终点最近的等价相位。区域重叠、空区域和退化道都拒绝。区域/层间使用径向净空半径上的结构化连接。

当前局部表面区域的受限形式是：在已选圆柱/圆锥 face 上由用户明确输入一个或多个有向角区间，不从局部修剪 face/contour 自动提取角边界。专项真值核对 `350°→380°`、第二区的最近等价相位 `480°→570°`、6 条道、覆盖长度/体积、跨区非沉积连接和首末净空。区域空集、重叠或退化均明确拒绝；不支持自动修剪面角边界依然作为已公开的产品边界。

## 5. 解析真值

机器可读夹具为 `tests/fixtures/analytic_rotary_truth.json`，声明单位为 mm/rad/mm³，基准轴框架为 `O=(10,-20,5)`、`u=(0,0,1)`、`e0=(1,0,0)`。当前常数如下：

| 案例 | 输入 | 独立期望 |
| --- | --- | --- |
| 圆柱 Spiral | `R=12`，轴向起点 4，30°→1110°，3 圈，螺距 8，道宽 0.8，层高 0.4 | 起点 `(20.3923048454,-14,9)`，终点 `(20.3923048454,-14,33)`，长度 `227.464347129934`，体积 `72.788591081579` |
| 圆锥 Spiral | `R:15→9`，轴向 0→12，0→4π，螺距 6，道宽 0.75，层高 0.3 | 半径斜率 `-0.5`，长度 `151.404863120125`，体积 `34.0660942020281` |
| Thin Wall | 轴向 `[2,6,10,14]`，半径 `[10.4,11.2,12.0]`，道宽 0.8，层高 0.4 | 4 层 × 3 径向道 = 12 圈，长度 `844.460105284936`，体积 `270.227233691180` |
| Around Part | `R=20`，轴向 `[0,0.8,1.6]`，A=350°→20°，B=120°→210° | A 展开为 350°→380°，B 等价相位为 480°→570°，6 条 stripe，长度 `125.663706143592`，体积 `40.2123859659494` |

独立推导脚本为 `tests/fixtures/derive_analytic_rotary_truth.py`，不导入产品模块；圆柱、Thin Wall 和 Around Part 使用闭式关系，圆锥长度使用 100,000 区间复合 Simpson 积分，与产品的路径弦长求和不同。专项测试要求其输出与 `analytic_rotary_truth.json` 一致，避免把实现采样公式作为唯一证据。

## 6. 失败矩阵

失败矩阵包含：零轴、无效零角方向、无效半径/螺距、锥顶退化、起止角相同、区域重叠/空区域、薄壁不足/径向道超宽、受限 C 轴不可达、轴速度与起停/连续加速度超限、夹具线段中部碰撞、C 轴字、Prime 事件、G93 模式与逆时间 `F` 回读篡改、控制器轴字语义冲突、prescribed phase 缺失/多余/非有限，以及 Dwell 未建立回读契约时的明确拒绝。计划和 IK 异常保存结构化 `code/severity/object_id/context`，GUI/脚本/HTTP 可读取同一错误对象。

当前碰撞障碍物由 Setup 的 fixture body 保守 AABB 构建，早先沉积段进入 IPW 离散近似；工具长度参与 IK/FK。原始基体和机床壳体尚未作为可精确查询的障碍集接入，完整机器关节插补扫掠、现场夹具和试切也没有证据。它们在结果中保留明确 Warning，只给予 Generic XYZAC 离线资格。

## 7. 产品链、接口和项目 I/O

产品对象保存 RotaryPlan、GeneratedToolpath、MachineAxisTrajectory、RotaryValidationReport、GeneratedResultManifest、G-code 和回读报告。Spiral、Thin Wall、Around Part 分别使用 R02/R03/R04 标记进入 shared absolute XYZAC 后处理，并以 G93 逆时间语义回读轨迹段时长。Error 或回读失败禁止导出。六件套发布使用 stage/旧目录备份/失败恢复的本地原子流程。

生成输入指纹包含算法版本、操作语义哈希、Setup 分配、Source 文件内容、拓扑描述符、Build CS、机型/喷嘴/材料快照、安装和碰撞配置。输入变化会 Stale；显示相机和质量参数不进入操作语义。取消和生成期间指纹变化不替换上一份有效运行时结果。

GUI、受限脚本和 HTTP 使用同一 `RotaryCommandService`。命令覆盖 create/set/generate/cancel/export/state/issues/validate/undo/redo；HTTP 使用 `/rotary/...` 路由。项目保存操作、稳定引用、参数和状态摘要，不嵌入运行时 Toolpath/G-code；重开后原 Ready/Warning 资格改为 Stale。STEP 更新后 axis/contour/surface 引用进入唯一重绑，并与 Tube/Planar/Curve 一起参与后台模型提交冲突检查。

## 8. UI 和手册

RotaryPage 是当前 Qt 双语页面，包含操作类型/已有操作、轴 edge/轮廓 edge/表面 face 选择、回转坐标、角区域、三操作参数、Create/Apply/Generate/Cancel/Export/Undo/Redo、状态、问题列表和 Viewer。参数行根据操作类型显示/隐藏，左侧使用禁止水平滚动的可滚动编辑区。

中文图文手册为 `docs/guides/rotary_workbench_zh.md`，已写入选边/选面、坐标、周期、三操作、参数、状态、取消恢复、路径/轴轨迹、检查、六件套、脚本/HTTP、保存重开、公开资料和实机边界。预留截图目录为 `docs/guides/assets/rotary/current_r01_r05/`。

截图目录已有 10 张图，覆盖总览、坐标设置、三操作结果、跨周期、轴限 Error 与恢复、导出和重开 Stale，并包含 1366×768 中文、1600×900 英文和 1920×1080 英文。`summary.json` 记录每图尺寸、语言、状态、导出按钮和 SHA-256。图像是 Windows Qt 当前 RotaryPage 控件与真实 generated preview payload 的 evidence paint harness，用于布局/状态/载荷核对；它避开 VTK/OpenGL，所以不单独证明生产 Viewer 后端通过。

## 9. 当前验证记录和 R05 关闭结果

`five-axis-slicer-validation` preflight 使用 `tmp/pytest9/Scripts/python.exe`，Python 3.12.7；依赖探针、Ruff 0.12.12、Mypy 1.11.2 和 QSettings 可写性通过。这是环境预检，不代表 GUI、VTK 或全仓通过。

当前已有的直接记录：

| 检查 | 当前结果 | 限制 |
| --- | --- | --- |
| Rotary 算法/失败/产品/Qt 专项 | 37 passed，退出码 0 | 包含独立真值、三操作、G93 回读、项目 I/O 和 Qt 页面；不代表全仓 |
| `scripts/check_quality.py` | 退出码 0 | Ruff、format、context budget、Mypy 通过；147 个源文件 |
| 真实 STEP 产品 | 4 个 Warning 产品，六件套和回读全部通过 | 圆柱 Spiral 75 点，圆锥 Spiral 75 点，Thin Wall 892 点/12 道，Around Part 109 点/6 道 |
| 当前 Qt 截图 | 10 张，三尺寸、中英文、错误/恢复/重开 | evidence paint harness；不声称 VTK/OpenGL 后端通过 |
| 全仓串行回归 | 820 passed、3 skipped、130 subtests passed，退出码 0 | 首轮 819 passed/1 failed/3 skipped；失败为既有 Planar P03 `os.replace` 的一次 WinError 5，单测复跑 1 passed，换新 basetemp 后全仓通过；两次日志均保留 |
| wheel/sdist 构建与包检查 | `five_axis_slicer-2.0.2.dev26+ga28395b-py3-none-any.whl` 与 `five_axis_slicer-2.0.2.dev26+ga28395b.tar.gz` 构建退出码 0；Twine 两包 PASSED；隔离环境安装 wheel 及导入 `rotary_controller`、`rotary_ui` 退出码 0 | 包来自源码提交 `a28395b`；未发布 |

R05 离线关闭证据汇总于 `docs/reviews/evidence/2026-09-13_rotary_workbench_final/validation_manifest.json`。其中单列首轮全仓回归的 Planar P03 一次性 Windows `WinError 5`、单用例恢复和换新 basetemp 后的最终全仓结果，也记录 3 项因 Windows 缺少符号链接权限而跳过的测试。源码与包对应提交 `a28395b130d1a195960e8d03b9a1cca5b3e9276f`，tree 为 `39fa66245341e9ac65cad2849623da598d5ee265`。

## 10. 实机边界

即使 R05 离线门禁全部通过，Generic XYZAC 仍只是参考机型的离线资格。真实控制器轴字、回转正方向、角度单位、比例和零偏、绝对/增量模式、轴软限和动态性能、回转中心、工具长度、喷嘴/基体/夹具/机床/已打印体的现场碰撞、材料工艺窗口、连接段滴料与试切都没有实机证据。

这些项在现场标定、干跑、碰撞验证和材料试验完成前统一标为“未验证”。当前输出不得直接下发真实机床。

使用的 Skills：`five-axis-workbench-development`、`five-axis-slicer-validation`。公开资料及许可边界同步记录在 `docs/planning/reference_research.md`。产品证据为 `docs/reviews/evidence/2026-09-13_rotary_workbench_final/products_summary.json`，图片证据为 `docs/guides/assets/rotary/current_r01_r05/summary.json`，最终综合证据为 `docs/reviews/evidence/2026-09-13_rotary_workbench_final/validation_manifest.json`。
