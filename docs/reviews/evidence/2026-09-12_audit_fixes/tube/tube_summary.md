# Tube 审查缺陷修复交接（2026-09-12）

用户已授权实施。修复基于当前工作区，未回写冻结副本；已重读当前文件、时间戳、Git 状态和阶段门槛。使用 `five-axis-workbench-development`、`five-axis-slicer-validation`，环境复用本轮已核验的 `tmp/pytest9/Scripts/python.exe`。未修改共享台账或总报告，未运行 Qt 或全仓回归。

## 已实施

- 新增 `tube_generation_context.py`。在 Controller 产品入口核验 Ready Setup、草稿、操作归属和源文件版本；保留 Source CAD 权威数据，复制并刚性变换完整拓扑描述和 OCCT shape 到 Build CS。装夹矩阵只包含 Mount 相对工件端点的静态关系，动态 A/C 旋转由机床运动链执行。非工件端点上不受支持的 Mount 明确拒绝。
- `tube_generation_service.py` 传入上述 Build 模型、静态 Placement、基体/fixture AABB 和开启的 IPW 检查。Setup Error、未应用草稿阻止生成；GUI 生成按钮使用同一 Ready/草稿条件。Setup Warning 随产品报告与导出保留，参考机型输出因此显示 Warning。
- 生成依赖指纹纳入源文件与几何、Operation（含 enabled）、资源内容哈希、Build、Placement、对象分配、碰撞设置和上下文版本。参数/Setup/资源改变使缓存 Stale；生成发布前和导出时再次核对。源文件在磁盘改变时拒绝用旧 CAD 继续生成。失败或取消保留上一份结果对象；生成中输入改变不能发布已过时的新结果。
- Tube 状态 schema 升为 2，保存上下文及指纹。缺少完整输入指纹的旧版 Ready/Warning 状态迁移为 Stale，保留历史结果内容。
- Indexed 与 Buildup 的真实 STEP 截交分支传入 chord 参数，使用 OCCT deflection 采样；内壁匹配改为投影到内环线段，避免不同采样点数下采用最近顶点造成配对误差。参数未被 Controller 重置。
- Indexed 几何检查按解析中心线量径向距离，避免把弯管斜切环误当作以层中心为球心的圆。新增四分点/中点线段内部偏差量测 `maximum_sampled_chord_error`，与用户 chord 限值比较；不再仅凭端点位于截面就接受粗弦。
- 配合 G-code Agent 的严格事件合同，Tube 回读 wrapper 传必需 nozzle。Buildup 跨操作连接增加真实 depart/travel 点，回抽具有显式带符号 E 量，safe_depart/operation_change/safe_approach 按实际运动序位插入，沿用目标路径原有 approach 后 prime；删除原来把五个事件放在同一序位的做法。

`postprocessing/indexed_tube.py` 未由本 Agent 编辑；其后处理/回读由 G-code Agent 负责。Planar 及共享报告文件保持其他执行者所有权。

## 本轮验证

最终纯 Tube 集合：**94 passed、6 subtests passed，57.63 s**。日志与 JUnit：`docs/reviews/evidence/2026-09-12_audit_fixes/tube/pure_tube_final.log`、`pure_tube_final.xml`。覆盖 11 个新增上下文/资格反例及已有 Indexed、Continuous、Buildup、Controller、资源选择和状态集成。

新增独立判据包括：非默认 Build 平移/旋转；源几何不被修改；物理机床 FK 对装夹变换后的点与喷嘴轴闭合；非零 A/C 回转中心和 Mount 偏置；Placement 改变使 NC 改变；资源/fixture 变化后 Stale 及导出阻断；Setup Error/草稿阻断；真实相交 fixture 阻断；源文件变化；取消；生成中编辑；旧版状态迁移；真实 STEP 弦中点误差。

首轮领域集合 40/42 通过，失败是两条历史测试的旧假设：缺完整 Setup 仍生成、把后续穿出障碍的 departure 混入“允许沉积接触”用例。已分别改为确认无效 Setup 被拒绝并保存 Error，以及把沉积接触验证限定到其实际接触段；未放宽产品碰撞或误差阈值。先前挑选单个测试时还暴露历史 unittest 类之间初始化依赖，随后完整模块串行运行正常；该失败没有被用于改产品代码。

本组 Ruff 检查、14 文件格式检查通过；Mypy 指定的 6 个产品/领域模块通过。Context budget 本组模块满足；最后一次全仓静态输出剩 `postprocessing/planar_product.py` 的 1002/1000 行问题，已告知主审，由对应执行者处理。全仓/Qt 和最终统一质量门禁仍归主审执行。

## 原审查直管反例的修复后产物

沿用审查时同一真实 STEP，使用完整 Ready Setup 和实际开启的基体/IPW 检查。保留现有离线线性空间夹具（XYZ ±1000 mm），旋转限位/速度/加速度未放宽，绝不据此声称真实设备通过。

| 案例 | 点数 | 状态与导出 | 独立最大 FK 误差 / mm |
|---|---:|---|---:|
| Placement X=250 | 346 | Warning / 六件套成功 | 1.2711e-13 |
| Placement X=350 | 346 | Warning / 六件套成功 | 1.6078e-13 |
| 平移且旋转的 Build CS | 346 | Warning / 六件套成功 | 1.2711e-13 |

三组 G-code 哈希不同。chord=.001 mm 时由旧版 129 点变为 346 点，独立线段中点偏差满足 .001 mm；Warning 为 `MACHINE_REFERENCE_ONLY`。产物在 `tube/products/placement_0/`、`placement_100/`、`rotated_build/`，汇总 `products/summary.json`。

## pipe2 实际 1 mm 壁厚资格结果

使用项目 `example/pipe2/弯管新.stp`，道宽/层高为 1/1 mm、喷口 1 mm、进给/空移 100 mm/min、chord=.01 mm、安全间隙 3 mm。完整几何为 **15479 点、67 层**。Setup Ready，源/配置/基体与 IPW 输入全部记录；完整生成在 22.52 s 被 IK 拒绝，无 NC 导出。

具体失败：`point-0007377`、第 34 层、`region-0007` 的 travel，工件喷嘴轴为 `(0, -0.8450882255, 0.5346268709)`，解析两分支要求 **A=±122.318610°**，所选参考机型 A 软限为 **±120°**，因此报 `xyzac.orientation_unreachable`。C 限位保留 ±360°。未套用旧软件 fixture 的所有旋转轴 ±1000 rad，也未改变姿态或阈值追求通过。

该案例说明产品正确阻止了当前机型/装夹不支持的路径；**不能称作真实 pipe2 已获得合格 G-code**。IK 失败在碰撞阶段之前，不能声称 pipe2 已通过 IPW 或基体检查。证据在 `tube/pipe2_wall_1mm/`：`inputs.json` 保存机型/喷嘴/Setup/参数/源哈希；`summary.json` 保留异常与状态；`blocked_point.json` 给出所需 A 与限位；`geometry_only_toolpath.json` 仅供几何审查。若继续获取 pipe2 合格 NC，需要独立处理机型/装夹适用性或可达姿态规划，保留正确限位。

## 范围与剩余条件

- 线段内部误差报告明示 sampled：采用四分点与中点检查，配合 OCCT 边界 deflection 控制；不宣称已完成任意复杂曲线的解析全段极值证明。
- 基体/fixture 使用 Build CS AABB，IPW 使用已有 capsule/喷嘴 R-Z 近似。它们有明确有碰撞/无碰撞对照；没有真实机床结构、标定或现场试切资格。
- 新上下文共用于三类 Tube 操作；非默认坐标下完整底座实体覆盖/制造效果不由本轮 Indexed 独立 FK 测试替代。既有 Buildup/Continuous 领域回归通过，真实 pipe2 资格限制单独保留。
- 当前文件已冻结交主审统一集成。后续全仓新增失败必须结合与本组接口直接关系处理，不能只用上述 94 项代替完整产品验收。

归档复制了诊断脚本，并用 `tube/manifest.json` 固定当前源码及产物 SHA256。没有修改本机资源库、全局配置、示例输入文件或冻结审查副本。
