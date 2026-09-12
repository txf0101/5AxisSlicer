# Tube 生成链专项审查（冻结源码，2026-09-12）

本审查只运行纯领域诊断，未修改产品源码、测试、共享台账或资源库，未运行 Qt/全仓测试。使用 `five-axis-workbench-development`、`five-axis-slicer-validation`；环境沿用主审已做的预检。解释器为项目内 `tmp/pytest9/Scripts/python.exe`。源码固定于 `tmp/project_audit/frozen`，下面行号均对应该副本 `src/five_axis_slicer/` 下的文件；不能把结果解释为并行 P07 修改后的实时 HEAD 已通过。

## 核心结论

Tube 的底层生成、IK、验证、后处理入口都有实现，但产品 Controller 没有把 Setup 的 Source→Build、Placement、碰撞环境和完整失效依赖接到生成链。已在正常 Ready Setup 下生成可导出的错误坐标结果，属于产品集成缺陷，不能用已有底层 IK 测试通过替代闭环验收。

### 1. P1：有效 Placement 与 Build CS 被生成入口忽略

- `tube_generation_service.py:55` 调用 `TubeProductService.generate` 时，仅传 CAD、Operation、Machine、Nozzle、source_path、cancelled；没有坐标或环境上下文。
- `postprocessing/tube_product.py:195` 将 `T_workpiece_from_build` 默认设为 None；`kinematics/xyzac.py:168` 在 None 时原样返回路径点。
- `algorithms/tube/geometry.py:140` 从原始 CAD 边中心识别管特征；`algorithms/tube/indexed.py:119` 从原始 CAD shape 截交。此链没有 Source→Build 变换，返回路径又使用 `manufacturing/toolpath.py:301` 的默认 `workpiece_build` 标签。
- `tube_controller.py:967` 的 `T_machine_from_source` 确实正确组合了 Build 与 Placement，但生成入口没有调用它或等效转换。`tube_ui_presenter.py:159` 只在 Machine 显示模式使用此矩阵；返回显示矩阵，不修改 `_cad_model`。因此没有找到上游或下游补偿。

独立复现：新建真实 STEP 直管，外半径 6 mm、内半径 5 mm、高 0.5 mm，源坐标中心 (50,50,20)，另有独立基体。参数 bead=1、layer=.5、feed=1 mm/min，沿用既有离线参考机型测试夹具及其 ±1000 软限；未放宽误差、速度、加速度或碰撞判据。Material 使用项目已有 `reviewed_copy` 创建内存内测试资源，未写资源库。两组 Setup 均 Ready，唯一 Setup issue 是 `MACHINE_REFERENCE_ONLY` Warning。

| 输入/检查 | 运行 1 | 运行 2 |
|---|---:|---:|
| Placement X / mm | 250 | 350 |
| `T_machine_from_source` 作用于源原点的 X / mm | 250 | 350 |
| 生成点数 | 129 | 129 |
| 第一轴点 (X,Y,Z) / mm | (-50,-20.25,57.5) | (-50,-20.25,57.5) |
| 产品状态 / 实际导出 | Ready / 成功 | Ready / 成功 |

两组所有轴点、G-code 完全相同；G-code SHA256 都是 `35d6cb0a29d00eddf6b27d911eadea8b07884f3b86ce7694e213f251f9c238c3`。另将 Build CS 的源空间原点改为 (10,0,0)，明确得到 Source→Build 原点 (-10,0,0)；Setup 仍 Ready，生成 Toolpath/G-code 仍完全相同且可导出。

边界：Model CS 负责输入/显示坐标，不能推断“只改 Model CS 必须改变 NC”。保持同一 Source/Build/Placement 几何关系时 Model 显示变化应保持输出稳定。修复必须明确每个 frame，避免把 Model 与 Build 重复应用。

### 2. P1：Setup/资源变化后旧结果保持 Ready 并可再次导出

`tube_controller.py:842` 的 Placement 更新调用 `_mark_operations_dirty`；后者在 :1063 只给操作加 Dirty/state/reasons，再调用 `_mark_product_stale`。`postprocessing/tube_product.py:545` 的语义哈希只含 operation_id、operation_type、geometry、parameters、type_config，不含 Setup、资源、enabled、state 或 dirty_reasons。`:152` 的 `stale_for` 在哈希未变时直接返回自身。`tube_generation_service.py:90` 的导出只查缓存 ProductState 和结果，不核对当前依赖。

实测：Ready 结果生成后，用公开 `begin_placement_draft → set_placement_adjustment → apply_placement_draft` 再加 X=100；操作已有 `placement_changed`，语义哈希仍不变，ProductState 仍 Ready，旧六件套再次导出成功。对应产物保存在 `ready_setup/stale_export/`。

同一根因适用于代码中 `_mark_operations_dirty` 覆盖的 machine/nozzle/material/part/model/build 变更（:451、:522、:525、:528、:731、:734）；这些额外路径属于静态推断，本轮逐步动态证明的是 Placement。不要为此次结论增加“全部变更已逐个实测”的说法。

### 3. P1：产品入口默认跳过基体/夹具和已打印体碰撞

`postprocessing/tube_product.py:196–197` 默认为 `obstacles=()`、`check_ipw=False`，Controller 没有覆盖。`validation/indexed_tube.py:217` 只遍历传入 obstacles；`:232` 只有 check_ipw 为真才检查 deposited capsules。Controller 的 substrate_body 选择和 Setup fixture 分配不会自动构造 CollisionBox；底层测试中显式传入障碍物不能证明 GUI/脚本/HTTP 已执行相同检查。

本条证据是完整调用链静态审查和产品默认值，未在本轮加入真实相交夹具动态案例。应在修改验收中增加有碰撞/无碰撞成对案例，并明确 collision coverage。报告 `issues=[]` 和 sampled count 不能代表执行了夹具或 IPW 检查。

### 4. P2：真实 STEP 的 chord 参数不控制采样，且验证只查顶点

`algorithms/tube/indexed.py:119` 的精确 STEP 分支没有传 `contour_chord_error_mm`；`:330` 的 `_exact_section_loop` 不接收该参数，`section.py:42` 固定默认 `sample_segments=128`。参数只进入未传 CAD 的解析圆分支。`validation/indexed_tube.py:148` 只量路径顶点到层中心的半径，不检查线段弦中点偏差。

Ready 直管案例请求 chord=.001 mm，但半径 5.5 mm 的相邻弦中点最大径向偏差为 **0.001656497170882787 mm**，超过指定值；产品仍 Ready。此测量由输出线段中点到已知解析圆心的距离独立计算。129 点对应 128 段圆周，并非用户参数被 Controller 初始化重置；本轮快照确认参数完整保留。

主审 pipe2 将 chord 改为 .001 而仍有 1171 点也符合此根因。径向误差问题还可能包含弯管斜切层的指标口径，不能仅凭固定采样缺陷就宣布已解释其全部 radial Error。

### 5. P1：Setup 的 Error 没有阻止生成和导出

首轮沿用未确认的材料模板，Setup 只有 `MATERIAL_REVIEW_REQUIRED` Error，Model/Build/Placement 均 Valid；Controller 仍生成 Ready 并实际导出。`tube_generation_service.py:46–50` 仅检查 CAD/Nozzle 存在，未检查完整 Setup；GUI 的 `tube_operation_ui.py:346、352` 也仅按 model 是否存在启用生成按钮。此首轮独立证据保留在 `initial_unreviewed_material/`。最终坐标复现已使用 Ready Setup 排除该干扰。

## 最小完整修改方案（待用户确认后实施）

1. 建立一个 Tube 生成上下文入口，集中验证有效 Setup、已应用草稿、完整/最新几何引用、当前资源；GUI、脚本、HTTP 复用该入口。明确哪些 Warning 允许参考导出，Error 不能产出可导出结果。失败/取消保留上一份结果但不能赋予其“当前有效”的资格。
2. 明确管几何/层计划/Toolpath/碰撞形体各自坐标。Source→Build 在规范化输出前应用一次；点、法线、切向、喷嘴方向以及层面/中心线使用同一规则。复用机床运动链计算 Workpiece endpoint→Mount→Build 的静态关系；Mount 不在支持的刚性工件链上应拒绝。不要把已含动态旋转的 `T_machine_from_source(q)` 再作为 `T_workpiece_from_build` 输入而重复旋转。
3. 建立当前生成依赖指纹，纳入源码/几何来源、操作参数、enabled、Build/Placement、Machine/Nozzle/Material 内容哈希、基体/夹具、碰撞配置及算法版本。Setup 变更立即使旧状态 Stale；生成发布和导出时都核对。Model CS 是否影响指纹按其实际语义决定，不以显示质量变化制造失效。
4. 按同一坐标构造基体/夹具环境，显式启用 IPW 或给出清楚的未检查状态和导出资格；同时保存覆盖范围与输入指纹。保留 AABB/capsule 近似的适用范围，真实机床资格继续独立处理。
5. 将 chord 参数传到 STEP 曲线采样，用曲线误差上界/自适应采样控制真实几何偏差，加入线段内部误差验收。不要只为通过案例放宽径向阈值或扩大参考机床限制。

## 必要验收

- Ready Setup 下默认/非默认 Build、Placement 平移/旋转、非零回转中心和非默认 Mount 成对输入；用独立 Source→Build→Workpiece→Machine FK 核对物理点与法线，避免同一个错误变换同时用于正反向验证。
- GUI/脚本/HTTP 各一条相同结果链；源几何、Setup、机型、喷嘴长度/直径、材料和 fixture 变化后缓存均失效，旧导出被挡；纯显示变化稳定；取消/失败/保存重开状态清楚。
- 有意穿过基体/夹具/前层打印体的案例不能 Ready；相邻但有间隙案例不能被无条件阻挡；报告区分执行、跳过和不支持。
- 小/大半径圆和弯管 STEP 的 chord=.01/.001 对应独立线段偏差均不超限；收紧参数后应增加必要采样或保持已满足的精度；不能只验顶点。
- pipe2 使用与 1 mm 实际壁厚相符的道宽/层高重新出合格示例。历史 bead/layer=10 mm 的包仅作软件链回归，不作为管壁制造效果证据。

## 归档与边界

稳定证据根目录：`docs/reviews/evidence/2026-09-12_project_audit/tube_probe/`。`ready_setup/summary.json` 记录 Ready Setup、坐标矩阵、轴点、状态、哈希、独立 chord 测量；`placement_0/`、`placement_100/`、`stale_export/` 为实际导出六件套。`initial_unreviewed_material/` 保留首轮与其导出。`probe.py.txt` 是可复算脚本，`manifest.json` 固定证据及相关源码 SHA256。

这些 G-code 是故障复现产物，仅供离线审查。参考机床采用既有测试 profile，无设备标定与现场试切证据。没有进行整机碰撞、材料挤出模型或真人桌面观感验收。修复尚未实施，本审查不改台账完成状态；应由主审把上述缺陷关联到原 T08/T12 的后续修正和验收条件。
