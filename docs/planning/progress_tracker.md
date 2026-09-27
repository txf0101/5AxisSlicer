# 六个工作台开发进度台账

最近更新：2026-09-27。关联[开发计划](development_plan.md)、[产品交付计划](product_delivery_20260923.md)、[参考资料](reference_research.md)与[文档索引](../README.md)。**下方主表是任务进度的唯一维护位置**，计划和复盘引用任务编号，不另行维护一份状态表。

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

2026-09-27 PRODUCT-01-V2C 使用开发/验证Skills接入Indexed分区端点承接门禁并升v5，旧pipe2数据检出699个Error；共享边界计划新增。41项模块测试通过，新增禁止导出集成断言后承接7项通过；完整回归和新GUI尚待，仍须完成有效过渡路径，不能以拒绝结果关闭V2-02。见收尾复盘与v2_02_support_integration_tests.xml。

2026-09-27 PRODUCT-01-V2C 使用开发与验证Skills完成直线珠道裁剪体积模块wedge_volume.py，边界/截面/体积共32项解析测试通过，局部Ruff通过。证据v2_02_wedge_volume_tests.xml；尚未接入Indexed变厚路径、承接或扫掠，旧弯管资格继续撤回，目标未完成。

2026-09-27 PRODUCT-01-V2C 使用开发与验证Skills新增有限道宽截面裁剪wedge_material.py，与共同边界模块共22项解析测试通过，局部Ruff通过；尚需沿程材料体积、喷嘴位置与实际承接验证，未接入生成链，旧弯管资格不恢复。证据v2_02_wedge_material_tests.xml；见收尾复盘。

2026-09-27 PRODUCT-01-V2C 使用开发与验证Skills实施弯管分区修复基础模块：wedge_boundary.py及9项独立解析测试通过；尚未接生成、材料积分和承接检查，旧弯管资格保持撤回。证据v2_02_wedge_boundary_tests.xml，实施说明见收尾复盘。下一步完成区内路径和有限道宽边界材料处理。

2026-09-27 PRODUCT-01-V2C 使用开发阶段门槛、验证及computer-use完成Freeform双语1920差异验收，V2-01矩阵30/30；复用范围见[记录](../reviews/evidence/2026-09-26_v2_final_delivery/freeform_1920_difference_record.md)。V2-02—V2-05继续进行。

2026-09-27 PRODUCT-01-V2C 使用开发、验证及computer-use推进V2-02：弯管150 mm项目实际生成、路径预览、六件套导出及本轮另存重开完成，独立磁盘回读43775/43775通过，CSV/工具路径一致；局部首层承接、生长和空移视觉检查待补。多Agent证据定位与独立回读完成。见[弯管记录](../reviews/evidence/2026-09-26_v2_final_delivery/v2_02_tube_current150_record.md)。

2026-09-27 PRODUCT-01-V2C后续检查：弯管分区0011→0012出现1.79024 mm局部分离；对全部此前253层32462条实际沉积段复核后距离不变，53/128端点超出0.6×0.2 mm截面保守接触上界，确认该包络假设下局部无承接。当前导出仅保留为诊断证据，撤回制造承接通过资格。下一步修复Indexed共同边界与残余沉积、补独立承接检查，不能仅用拒绝关闭案例。真实NC空移显隐已检查；默认显示后续路径且统一蓝色，不能用进度画面证明逐层承接。Skills：开发、验证、computer-use；证据同弯管记录及v2_02_tube_prior_support_measurements.json。

2026-09-27 PRODUCT-01-V2C 使用开发阶段门槛、验证及computer-use完成Tube双语1920差异验收，197个源码哈希与复用证据一致，累计28/30。见[记录](../reviews/evidence/2026-09-26_v2_final_delivery/tube_1920_difference_record.md)。

2026-09-27 PRODUCT-01-V2C 使用开发阶段门槛、验证及computer-use，完成Rotary双语1920差异验收；197个源码哈希与复用基线一致，累计26/30。见[记录](../reviews/evidence/2026-09-26_v2_final_delivery/rotary_1920_difference_record.md)。

2026-09-27 PRODUCT-01-V2C 使用开发、验证和computer-use完成Curve双语1920差异验收，源码指纹与英文1366共用证据一致，累计24/30；见curve_1920_difference_record.md。

2026-09-27 PRODUCT-01-V2C 主Agent使用computer-use继续差异验收准备，子Agent使用开发、验证Skills建立[83处教程图片清单](../reviews/evidence/2026-09-26_v2_final_delivery/v2_04_image_reference_checklist.md)，45张图片视觉及图注待核；完成数仍21/30。

2026-09-27 PRODUCT-01-V2C 使用开发 Skill 阶段门槛、验证及 computer-use，完成 Planar 英文1920×1080失效引用拒绝恢复与整组证据核对，累计21/30；见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/planar_en1920_click_record.md)。

2026-09-27 PRODUCT-01-V2C Freeform 中文 1366×768 已补齐角色拒绝恢复、导引/实体切换、双模式保存重开；导引重新生成9点/1事件严格回读通过。累计15/30，余15组。Skills：开发、验证、computer-use；见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/freeform_zh1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C 沿用开发、验证与 computer-use Skills，推进 Freeform 中文 1366×768：空白门禁、边面拾取、公共七节点、9点/1事件回读和独立/公共两次 Stale 已实测；模式角色和保存重开待补，累计仍14/30。见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/freeform_zh1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C Tube 中文 1366×768 重开后实际生成 Warning、43775/43775 严格回读通过，预览/导出恢复；本组合关闭，累计 14/30，余 16 组。Skills：开发、验证、computer-use；见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/tube_zh1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C 使用开发、验证和 computer-use Skills，推进 Tube 中文 1366×768：公共七节点、四角色与错误恢复、43775 点回读、材料 Stale 及保存重开已实测；重开后再生成待核对。累计仍 13/30，见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/tube_zh1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C 沿用开发、验证和 computer-use Skills，完成 Rotary 中文 1366×768 公共七节点、端面拒绝与侧面恢复、两次 Stale、保存重开及 75/75 严格回读；放大后轴边 Viewer 拾取及应用生成补验通过。累计 13/30，见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/rotary_zh1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C 沿用开发、验证和 computer-use Skills，完成 Curve 中文 1366×768 空白入口、公共七节点、Viewer 有向拾取与断链恢复、两次 Stale、保存重开及 17/17 严格回读。累计 12/30，见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/curve_zh1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C 沿用开发、验证与 computer-use Skills，完成 Planar 中文 1366×768 保存重开、27/27 严格回读、空零件与失效引用恢复及坐标中文提示桌面复验；完整组合累计 11/30，见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/planar_zh1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C 沿用开发、验证及computer-use Skills，启动Planar中文1366×768真实检查，公共七节点完成；修复坐标确认临时状态英文残留，六项文本断言和Ruff通过，重启显示待验。累计10/30，见收尾复盘。

2026-09-27 PRODUCT-01-V2C 使用 five-axis-workbench-development、five-axis-slicer-validation、computer-use，完成 Tube 中文公共七节点、150 mm设置、角色拒绝恢复、Stale及保存重开生成；43775/43775严格回读通过，完整组合累计10/30。证据见[逐项记录](../reviews/evidence/2026-09-26_v2_final_delivery/tube_zh1600_click_record.md)。


2026-09-27 使用开发 Skill stage-gates、验证证据规则和 computer-use 汇总 [Rotary 中文验收](../reviews/evidence/2026-09-26_v2_final_delivery/rotary_zh1600_click_record.md)，25个证据引用存在且指纹归档，累计9/30。仅关闭本组合，目标仍进行中。

2026-09-27 使用 computer-use 完成 Curve 中文两次 Stale、保存重开与再生成，按开发 Skill stage-gates 与验证证据规则汇总 [Curve 中文记录](../reviews/evidence/2026-09-26_v2_final_delivery/curve_zh1600_click_record.md)，累计 8/30。无源码修改，目标仍进行中。

2026-09-27 PRODUCT-01-V2C 使用开发 Skill 阶段门槛与验证证据规则，核对 Freeform 中文真实点击记录并关闭中文 1600×900 单组合，累计 7/30；[逐项记录](../reviews/evidence/2026-09-26_v2_final_delivery/freeform_zh1600_click_record.md)。使用 computer-use 完成缺设置恢复、角色恢复、模式切换、项目重开和新增中文提示复验；草稿确认相关回归 31 项直接通过、4 项临时目录权限修正后通过。整体目标仍进行中。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 补验 Freeform 中文公共七节点、150 mm 机床及装夹失效恢复，证据 freeform_zh1600_machine150_placement_recovered.png/json；中文生成及独立/公共两次 Stale 已实测；恢复公共确认框标题及 Yes/No 已修复代码，设置作用域回归 35 passed，中文新弹窗及是/否行为已桌面复验，最新源码中文空白缺项门禁、直接 STEP 和视口选边已补验；中文组合继续进行中。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 实测 Freeform 缺少对侧面时拒绝及禁用；沿用开发、验证 Skills 补齐双语恢复说明，5 项直接回归、Ruff、Context budget 通过，真实中英文新文案及补回对侧面后的 Apply 恢复已通过，模式编辑器切换、几何角色保留及独立生成后恢复公共的新一轮 Stale 已实测，完整组合已汇总为 [Freeform 英文点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/freeform_en1600_click_record.md)，累计 6/30。见同一收尾复盘、freeform_missing_opposite.xml 及 freeform_missing_opposite_recovered_live_en.png/json。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 实际补齐 Tube 英文空白首页、四角色缺失 Apply 提示及底部按钮门禁，按开发阶段门槛汇总 [Tube 英文点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/tube_en1600_click_record.md)，英文 1600×900 通过，累计 5/30。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 补验 Rotary 独立生成后恢复公共设置的新一轮 Stale，按开发阶段门槛汇总 [Rotary 英文点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/rotary_en1600_click_record.md)；英文 1600×900 通过，累计 4/30。

2026-09-27 PRODUCT-01-V2C 使用 five-axis-workbench-development 阶段门槛核对 Curve 历次 computer-use 实际证据，形成 [Curve 英文点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/curve_en1600_click_record.md)，英文 1600×900 单组合通过，矩阵累计 3/30。其余组合及五个完整工作包不随之关闭。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 补齐 Curve 公共七节点实际点击，保存并重开 curve_en1600_current150；150 mm 配置与有向边链保留，坐标编辑 Cancel 恢复 Valid。待汇总既有证据核对整格，完整组合仍为 2/30。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 补齐 Curve 英文 1600×900 独立喷嘴长度拒绝与恢复、17/17 点重新生成回读，以及恢复公共设置后的新一轮 Stale；证据 curve_en1600_*，公共设置逐节点覆盖仍待核对，完整组合仍为 2/30。

2026-09-27 PRODUCT-01-V2C 使用开发、验证和 computer-use Skills 修复首页 STEP 误入预览的路由遗漏；旧代码新增反例失败，修复后 3 项回归及 3 项子测试、Ruff、Context budget 通过；真实首页载入后公共 Part 可见 body_001。见同一收尾复盘与 home_step_route_* 证据。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 完成中文 Planar 生成、独立/公共设置 Stale、失效引用恢复和保存重开；按开发 Skill 阶段门槛核对证据，仅关闭中文 1600×900 内部入口组合。共享首页 STEP 路由差异及其余矩阵仍待处理，见[中文点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/planar_zh1600_click_record.md)。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 恢复插件读取后，完成中文 Planar 小平板实体角色、机床、喷嘴、材料、两个坐标和装夹的实际设置；Part 与喷嘴缺项及补回恢复已有截图。组合保持进行中，见同一复盘。

2026-09-27 PRODUCT-01-V2C 使用开发、验证及 computer-use Skills 核对当前证据并更新主表：Planar 英文 1600×900 为唯一完整通过组合；已完成的 Tube 遗漏出口恢复和 Freeform 两面拾取不再标为待复验。电脑插件窗口状态读取两次失败，本次不新增 GUI 通过项，见同一收尾复盘。

2026-09-27 PRODUCT-01-V2C 沿用开发、验证及 computer-use Skills 开始 Planar 中文 1600×900 流程；发现并修复公共 Part 空实体提示遗漏中文，局部 2 项语言/角色测试、Ruff、Context budget 通过，重启后的中文弹窗已实测。该组合仍进行中，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#planar-中文-1600900-首次使用)。

2026-09-27 PRODUCT-01-V2C 沿用开发、验证及 computer-use Skills，补齐 Planar 英文 1600×900 失效引用拒绝/恢复，新增中英文恢复说明，29 项诊断回归及 Ruff 通过；本组合 V2-01 点击记录已逐项归档。其余组合和 V2-02—V2-05 保持待完成，见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/planar_en1600_click_record.md)。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 重启修复后的源码，实际重开 Planar 项目，确认从 Placement 返回后打开 Part 不产生草稿；完成空 Part 拒绝、恢复及确认按钮滚动检查。见[真实复验记录](../reviews/2026-09-26_v2_final_delivery_review.md#planar-英文-1600900-首次使用)，其余矩阵和失效引用恢复继续待验。

2026-09-27 PRODUCT-01-V2C 使用开发、验证及 computer-use Skills 检查 Planar 英文 1600×900 首次使用，发现公共设置入口意外创建 Placement 草稿，保存现场并修复进入顺序。矩阵继续进行，见[本轮记录](../reviews/2026-09-26_v2_final_delivery_review.md#planar-英文-1600900-首次使用)。

2026-09-27 PRODUCT-01-V2C 使用开发、验证及 computer-use Skills 完成旧项目 180 mm 快照保留、新 150 mm 配置应用、过期装夹隐藏/恢复及 RX 30°双视图检查；修正高 DPI 线宽并加入原生抗锯齿，16 项 Viewer/几何测试及 2 项子测试通过。完整矩阵继续待验，见[平台复验记录](../reviews/2026-09-26_v2_final_delivery_review.md#平台桌面复验的空白显示诊断)。

2026-09-27 PRODUCT-01-V2C 使用开发、验证 Skills 核对非零旋转/平移的平台 Source 坐标，发现并修复过期装夹仍显示平台；六种失效状态与相关配置测试通过，桌面装夹和旧项目复验待完成，见[同一平台记录](../reviews/2026-09-26_v2_final_delivery_review.md#平台桌面复验的空白显示诊断)。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 重启复验英文窄视口 Fit，并真实进入 Curve、Freeform、Rotary、Tube 确认空白圆台可见；连同先前 Planar 留存五工作台平台入口证据。网格质量、装夹/旧项目及正式矩阵尚未完成，见[平台记录](../reviews/2026-09-26_v2_final_delivery_review.md#平台桌面复验的空白显示诊断)。

2026-09-27 PRODUCT-01-V2C 沿用开发、验证 Skills 修复空白圆台随视口变窄而裁切，新增窄视口投影反例并通过相关回归；实际重启复验和网格清晰度待完成，见[平台诊断记录](../reviews/2026-09-26_v2_final_delivery_review.md#平台桌面复验的空白显示诊断)。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 恢复原生 Windows 显示后，实际完成 Planar 圆台与公共 Machine 双语 150.0 mm 核对；保存原生截图与状态。当前尺寸不计入正式矩阵，网格质量、窄视口 Fit、其他工作台及旧项目继续待验，见[同一诊断记录](../reviews/2026-09-26_v2_final_delivery_review.md#平台桌面复验的空白显示诊断)。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 复验平台，发现窗口截图空白但控件响应；修复绘制调用遗漏的必需参数并通过类型检查，软件渲染对照仍空白，保留待诊断与真实验收状态。见[诊断记录](../reviews/2026-09-26_v2_final_delivery_review.md#平台桌面复验的空白显示诊断)。

2026-09-27 PRODUCT-01-V2C 沿用开发、验证 Skills，接入五工作台圆平台显示和 VTK 共享几何；原生烟测、设置 36 项、后续几何/Rotary 17 项及 Tube 5 项回归通过，真实显示待验。相关 Ruff、Mypy 和 Context budget 通过，见[同一复盘](../reviews/2026-09-26_v2_final_delivery_review.md#150-mm-可用平台配置)。

2026-09-27 PRODUCT-01-V2C 继续使用开发、验证 Skills，完成 OpenGL 圆平台填充和边界内网格，24 项测试及 2 项子测试通过；Context budget 通过，完整质量检查受新增截图脚本规则错误影响。VTK、工作台入口和真实显示继续待验，见[平台记录](../reviews/2026-09-26_v2_final_delivery_review.md#150-mm-可用平台配置)。

2026-09-27 PRODUCT-01-V2C 使用开发、验证 Skills，将用户确认的直径 150 mm 圆形可用平台写入默认机型版本 2，并同步双语说明；9 项配置测试通过。平台预览样式与真实界面检查待完成，原 V2 全部完成判据保持不变。见[同一复盘](../reviews/2026-09-26_v2_final_delivery_review.md#150-mm-可用平台配置)。

2026-09-27 DOC-IMG-01 沿用开发、验证及截图 Skills，针对路径密集反馈恢复 CAD 遮挡并调整独立捕获进程的线色、线宽请求及深度偏移，保留全部路径；交付新版左图，代码图不变，见[同一复盘](../reviews/2026-09-26_paper_screenshot_refresh.md#2026-09-27-密集路径显示调整)。

2026-09-27 DOC-IMG-01 沿用本任务开发、验证和截图 Skills，按用户反馈改用 1366×900 窗口并截取 24 行代码，完成两图视觉检查和哈希核对；见[同一复盘的 A4 调整](../reviews/2026-09-26_paper_screenshot_refresh.md#2026-09-27-a4-文字可读性调整)。

2026-09-27 PRODUCT-01-V2C 使用 computer-use 重启当前源码，完成 Freeform 不可达姿态说明的双语真实复验：说明换行完整、代码与点编号保留、导出禁用；见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#9-月-27-日不可达姿态说明的真实复验)。

2026-09-26 PRODUCT-01-V2C 使用开发、验证 Skills 整理主窗口项目恢复，9 项发布/回滚测试通过；当前完整质量门禁通过，Mypy 覆盖 194 个源文件。完整 GUI 与发行验收继续待办，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#主窗口项目恢复整理与质量门禁通过)。

2026-09-26 PRODUCT-01-V2C 使用开发、验证 Skills 整理 Rotary 显示/按钮/回填和 Tube 碰撞筛选，分别 23 项、33 项及 3 子测试通过，5 项超限消除；余 ui.py 四项，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#rotary-显示与碰撞筛选职责整理)。

2026-09-26 PRODUCT-01-V2C 使用开发、验证 Skills 分离 Tube 设置诊断显示，62 项测试和 2 项子测试通过，Tube 三项质量超限消除。整体仍余 9 项，未替代真实多尺寸验收，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#tube-设置诊断显示职责整理)。

2026-09-26 PRODUCT-01-V2C 使用开发与验证 Skills 整理 Freeform 路径起点、数值回填和父操作合并职责，15 项回归与三文件类型检查通过；三项超限消除，剩余 12 项。归档截图脚本设置精确 E402 例外并保留原件，Ruff/安全/格式通过，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#freeform-质量整理与相关回归)。

2026-09-26 PRODUCT-01-V2C 使用 computer-use 实测 Freeform 双语 Error 首屏排序；沿用开发和验证 Skills 补齐不可达姿态恢复提示，7 项相关测试通过，Curve 长度门槛恢复合格，其余 15 项仍待处理。新增提示待桌面复验，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#错误首屏实测与不可达姿态提示)。

2026-09-26 PRODUCT-01-V2C 使用开发、验证和 computer-use Skills 拆分诊断显示职责（双语测试 2 passed，类型检查通过），并完成 Tube 遗漏出口的双语真实拒绝、禁用及补回恢复复验。完整矩阵和质量门禁仍未完成，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#诊断显示职责拆分与-tube-缺失角色实测)。

2026-09-26 DOC-IMG-01 使用 `five-axis-workbench-development`、`five-axis-slicer-validation`、`screenshot`，追溯旧图后用当前 Qt/OpenGL 与 9 月 24 日叶轮离线程序重新取两张无后期标注截图；完成最终视觉检查、代码无横向裁切检查及来源哈希记录，见[复盘](../reviews/2026-09-26_paper_screenshot_refresh.md)。

2026-09-26 PRODUCT-01-V2C 使用开发、验证 Skills 检查累计修改的质量门禁：修复一处 UP038 与四个文件格式偏差，Ruff、安全及格式检查通过，Mypy 193 个源文件通过；Context budget 尚有 16 项超限，保留待处理。桌面存在另一论文截图进程，暂避开窗口操作，错误优先级和 Tube 缺失角色的真实复验继续待办。见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#累计修改的质量检查)。

2026-09-26 PRODUCT-01-V2C 使用 `five-axis-slicer-validation` 核查并修复 Curve/Freeform 错误显示优先级，双语回归 2 passed；桌面复验和 Tube 遗漏角色继续待验，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#阻止导出的错误优先显示)。

2026-09-26 PRODUCT-01-V2C 使用 `computer-use` 完成 v4 底面承载角色编辑及实际生成：首层 Z=0.2 mm、体积误差 5%，原层间方向拒绝消失，同层喷嘴接触继续阻止导出；完整恢复尚未通过，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#v4-底面承载角色的真实生成)。

2026-09-26 PRODUCT-01-V2C 使用 `five-axis-slicer-validation` 确认厚度方向修改后的产品回归 2 passed，并补充层间转换拒绝的双语提示及详情回归 2 passed；真实 v4 与承接仍待验，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#厚度模式喷嘴轴修复)。

2026-09-26 PRODUCT-01-V2C 按开发与验证 Skills 修复厚度模式喷嘴轴，保留承载面向对面的层序；8 项算法测试通过，产品回归及真实 v4 界面复验继续，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#厚度模式喷嘴轴修复)。

2026-09-26 PRODUCT-01-V2C 复用开发 Skill 的承接/生长门槛及验证 Skill，建立 Surface Solid 厚度模式方向反例：层间位移与喷嘴轴同向，新增测试当前失败。需明确面角色并修正层序或轴向，未放行实体结果，见[复盘](../reviews/2026-09-26_v2_final_delivery_review.md#厚度模式生长方向反例)。

2026-09-26 PRODUCT-01-V2C 继续使用 `computer-use`：双语生成诊断实际换行与导出禁用复验通过；厚度 1 mm 恢复后体积错误消失，剩余层间转换接触须结合角色生长方向检查，见[本轮复盘](../reviews/2026-09-26_v2_final_delivery_review.md#双语实测与厚度错误恢复)。

2026-09-26 PRODUCT-01-V2C 使用 `computer-use`、`five-axis-slicer-validation` 核查 Freeform 中文诊断，补充体积偏差及空移拒绝的双语恢复说明和数值详情；2 项界面测试通过，实际重启显示及参数恢复待验，详见[本轮复盘](../reviews/2026-09-26_v2_final_delivery_review.md#实体生成诊断的双语说明)。

2026-09-26 PRODUCT-01-V2C 使用 `computer-use` 保存重开实体项目并实测最新生成修复：工序 ID 异常消失，结果被厚度体积误差与当前喷嘴接触检查拒绝，导出正确禁用；具体设置及恢复待验项见[本轮复盘](../reviews/2026-09-26_v2_final_delivery_review.md#实体项目保存重开与生成修复实测)。

2026-09-26 PRODUCT-01-V2C 使用 `computer-use`、`five-axis-slicer-validation` 继续检查 Freeform：实际生成复现单实体子路径工序 ID 不一致，已修复适配器并增加回归；导引模式恢复单面拾取已实测。测试和修复后桌面生成证据继续补齐，见[本轮复盘](../reviews/2026-09-26_v2_final_delivery_review.md#单个实体子路径的工序身份修复)。

2026-09-26 PRODUCT-01-V2C 继续使用 `computer-use`，重启最新源码并完成 Freeform 英文 1600×900 实体根边与两面逐次拾取、回填及 Apply 复验；修复有效，生成及其余矩阵继续核查。证据见[本轮复盘](../reviews/2026-09-26_v2_final_delivery_review.md#多面选择修复后的桌面复验)。

2026-09-12 AUD-02 收尾另实际调用 `skill-creator`，更新个人工作台开发 Skill 的制造验证经验；[归档快照](../reviews/evidence/2026-09-12_audit_fixes/skill_snapshot/)随项目提交。

实施或收尾 P/C/F/R/X/I 及后续 Tube 工作台任务时，先调用 `five-axis-workbench-development`；进入测试、Qt/VTK 回归、失败诊断或阶段验收时再调用 `five-axis-slicer-validation`。每次只登记实际加载并影响工作的 Skill，详细判断放入对应复盘。

| 日期 | 任务 | Skill | 本轮用途 | 证据 |
| --- | --- | --- | --- | --- |
| 2026-09-26 | PRODUCT-01-V2C | `five-axis-workbench-development`、`five-axis-slicer-validation`、`computer-use` | 建立五工作台双语三尺寸矩阵；实际检查 Planar、Curve、Rotary、Tube、Freeform 的入口、设置、几何选择及恢复，修复布局、双语提示、选边顺序、编辑保留、失败应用门禁和 Tube 取消响应；核查并修正尖端球包络误报；各尺寸按实际证据逐项核查 | [收尾复核](../reviews/2026-09-26_v2_final_delivery_review.md) |
| 2026-09-26 | FAN00/FAN01 顺序复核 | `five-axis-workbench-development`、`five-axis-slicer-validation` | 核对当前 STEP 四实体签名与契约，重扫旧 NC；纠正计划旧资格，重新打开未完整冻结判据的 FAN01 | [复核记录](../reviews/2026-09-26_fan_sequential_audit.md) |
| 2026-09-25 | CI-QUALITY V2.6.2 后续修复 | `gh-fix-ci`、`five-axis-slicer-validation`、`five-axis-workbench-development` | 核对最新 Actions 失败步骤；本地修复 37 条 Mypy 错误，把上下文预算改成对象级精确旧债务约束，并验证新对象仍受默认上限 | [质量门禁复盘](../reviews/2026-09-25_ci_quality_recovery.md)；本地完整质量通过，CI 同域及相关测试 188 passed、2 skipped、89 subtests；托管检查待新提交 |
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
| DOC-IMG-01 | 叶轮论文双图更新 | 旧图制作记录与现有离线程序 | 已完成 | 当前软件界面及同源代码两张独立 PNG，无后期标注，来源可追溯 | [复盘及图片](../reviews/2026-09-26_paper_screenshot_refresh.md)；3840×2560 / 2300×1500；最终视觉检查及代码横向范围为零 | 本截图任务完成；不变更其他开发或制造资格 | 2026-09-26 |
| PRODUCT-01 | 离线产品交付闭环 | FAN11/FP01—FP06、现有五工作台 | 已完成（离线范围） | 首次使用和四例真实点击：加载、Setup、选几何、生成/取消、预览、六件套导出、严格回读、保存重开；界面和图文教程完成 | V2-01至V2-05完成；30/30组合、四例GUI完整链、取消响应、教程及隔离包验证通过。最终全仓1280 passed、3 skipped、146 subtests passed，后续诊断类型修改36项通过；源码d3a2b50四项CI成功，220个包内源码一致。见[最终判据复核](../reviews/evidence/2026-09-26_v2_final_delivery/completion_audit.md)及[收尾复盘](../reviews/2026-09-26_v2_final_delivery_review.md)。 | 本轮离线验收关闭；实机标定、试打及微小接缝精度列入后续，machine_executable=false。 | 2026-09-27 |
| PRODUCT-01-V2C | 第二代离线产品收尾计划 | PRODUCT-01 当前证据、用户确定的第三代边界 | 已完成（离线范围） | 五工作台首次使用与代表案例界面闭环、长任务、双语图片和发行核验按计划逐项通过 | V2-01至V2-05完成；30/30组合、四例GUI完整链、取消响应、教程及隔离包验证通过。最终全仓1280 passed、3 skipped、146 subtests passed，后续诊断类型修改36项通过；源码d3a2b50四项CI成功，220个包内源码一致。见[最终判据复核](../reviews/evidence/2026-09-26_v2_final_delivery/completion_audit.md)及[收尾复盘](../reviews/2026-09-26_v2_final_delivery_review.md)。 | 本轮离线验收关闭；实机标定、试打及微小接缝精度列入后续，machine_executable=false。 | 2026-09-27 |
| PRODUCT-01-MC01 | 五轴安全换姿与多色换料 | PRODUCT-01、Freeform 实体路径 | 离线验收完成，实机待标定 | 配置换料站、三色 PLA 叶片分区；生成切断/退丝/进丝/排料/擦嘴/返回的完整 NC，避开已沉积材料，严格回读通过；无站位或无安全路线阻止导出 | 当前三叶扇340193点、62716事件，T0→T1→T2、两次切刀与完整退离/换料/排料/两遍擦嘴/返回顺序核对通过；4142条Warning、0条Error。真实GUI生成、导出、NC空移/工序预览、保存重开完成，见[磁盘核查](../reviews/evidence/2026-09-26_v2_final_delivery/v2_02_three_color_disk_audit.json)与[收尾复盘](../reviews/2026-09-26_v2_final_delivery_review.md)。`machine_executable=false`。 | 喷嘴/夹具、切刀宏、传感器与现场站位标定属于后续实机资格，不纳入本轮离线完成条件。 | 2026-09-27 |
| FAN00 | 规划与项目调研 | 用户计划授权 | 已完成 | 详细计划、六仓库研究、电脑验收方案齐全 | [任务设计与边界](fan_complete_program_plan.md)；[研究](fan_complete_program_research.md)，仅规划完成 | FAN01 | 2026-09-20 |
| FAN01 | 输入与制造契约 | FAN00 | 进行中 | 参数来源、实体角色、坐标、姿态及误差阈值冻结 | [本轮复核](../reviews/2026-09-26_fan_sequential_audit.md)：STEP 与四实体签名/体积匹配；候选契约补齐 12 项来源，来源失配与待测拒绝 9 项通过，质量检查通过；局部覆盖/空洞/承接判据尚缺，实机参数仍待测 | 解析夹具量测与收敛，冻结局部判据后继续 FAN02 | 2026-09-26 |
| FAN02 | 旧NC和CAD独立基线 | FAN01 | 重新核查中 | 分工序模态解析、径向层序、坐标注册与填充覆盖 | [模态运动统计](../reviews/evidence/2026-09-20_fan_complete_program/radial_correction/legacy_motion.json)：叶片A90、C连续联动；原全文件TYPE统计不能证明叶片内部填充 | FAN04纠正 | 2026-09-20 |
| FAN03 | 作业依赖和状态模型 | FAN01 | 已完成 | 序列化、依赖图、Stale、取消、程序索引 | [作业JSON](../reviews/evidence/2026-09-20_fan_complete_program/fan_job_v1.json)；循环/缺依赖、下游失效、JSON和取消事务已测；G-code行号索引属FAN10 | FAN06 | 2026-09-20 |
| FAN04 | 全体积层域和90°可行性 | FAN01,FAN02 | 撤回原验收，修正中 | 柱面起印、径向曲层、层间承接、AC联动与独立FK | 原固定A平面截层只证明几何积分，不符合绕轴生长；[纠正复盘](../reviews/2026-09-20_fan_radial_correction.md) | 曲层域与承接验证 | 2026-09-20 |
| FAN05 | 公共壳层和内部填充 | FAN01,FAN02 | 待验证 | 带孔/多岛/窄缝、顶底层、0/20/100%矩阵 | [历史248项回归](../reviews/evidence/2026-09-20_fan_complete_program/pytest_fan01_fan05_final_retry.xml)保留；FAN15发现偏置异常吞并、原边界回退及多实体嵌套误判孔，[原完整资格撤回](../reviews/2026-09-20_fan15_example_acceptance.md) | 修复反例后重新验收 | 2026-09-20 |
| FAN06 | 全高底座和支撑联合调度 | FAN03,FAN05 | 历史已验收 | 全部层、孔和接口保留，支撑逐层排序 | [历史统计](../reviews/evidence/2026-09-20_fan_complete_program/fan06_fan07/fan06_fan07_summary.json)：325/325层、309层支撑；上游 FAN05 已撤回，本轮未重新验证底座，不能据此放行 FAN09 | FAN05 重新验收后复核底座与支撑 | 2026-09-26 |
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
| 2026-09-25 | 用户要求消除最新 Actions 红叉 | 修复类型错误与上下文预算旧债务登记方式；保留新对象默认上限并补回归，执行本地质量、领域测试与隔离打包 | 本地质量及相关测试通过；GitHub 最终状态以新提交的 Actions 结果为准，未将旧红叉误报为已消失 |
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

2026-09-27 Skill 调用补记：PRODUCT-01-V2C 使用开发/验证 Skills 与 computer-use 定位 Rotary 中文草稿阻止提示，补齐双语恢复说明；4 项纯呈现断言、Ruff 与上下文预算通过，新提示真实桌面复验待补。详见收尾复盘，整体状态不变。



2026-09-27 PRODUCT-01-V2C：Planar 英文1366×768公共七节点实际设置完成，150 mm圆台、坐标和装夹有效；生成等余项待补，累计仍15/30。Skills：开发、验证、computer-use；见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/planar_en1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C：Planar英文1366×768完成公共/独立生成、两次Stale、保存重开再生成，三次27/27严格回读通过；空零件/失效引用恢复待补，累计15/30不变。Skills：开发、验证、computer-use。

2026-09-27 PRODUCT-01-V2C：Planar英文1366×768空Part拒绝恢复、失效引用拒绝恢复完成，四次生成27/27回读通过，本组合关闭，累计16/30。Skills：five-axis-workbench-development（阶段门槛）、five-axis-slicer-validation、computer-use。见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/planar_en1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C：Curve英文1366×768空白入口、缺项门禁、实际STEP和Viewer两边拾取回填已完成，公共设置等待补，累计16/30不变。Skills：开发、验证、computer-use。见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/curve_en1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C：Curve英文1366×768公共七节点全部实际确认，150 mm圆台及坐标/装夹有效；待生成及错误恢复，累计16/30不变。Skills：开发、验证、computer-use。

2026-09-27 PRODUCT-01-V2C：Curve英文1366×768断链8 mm拒绝与方向恢复、公共/独立两次17/17回读、独立/公共两次Stale已实测；保存重开待补，仍16/30。Skills：开发、验证、computer-use。

2026-09-27 PRODUCT-01-V2C：Curve英文1366×768实际保存重开及再生成17/17回读通过，按V2-01核对完整记录，本组合关闭，累计17/30。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/curve_en1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C：Rotary英文1366×768已重新空白启动，检查缺STEP/设置提示、底部动作可达与直接加载圆柱；组合进行中，累计17/30。Skills：开发、验证、computer-use。见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/rotary_en1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C：Rotary英文1366×768公共七节点全部实际应用，150 mm圆台、坐标及零偏移装夹Valid；Viewer放大拾取轴边0002并回填。回转面和后续生成待补，累计17/30不变。Skills：开发、验证、computer-use。

2026-09-27 PRODUCT-01-V2C：Rotary英文1366×768端面拒绝/侧面恢复、两次Stale、实际保存重开和三次75/75严格回读完成，本组合关闭，累计18/30。Skills：five-axis-workbench-development（阶段门槛）、five-axis-slicer-validation、computer-use。见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/rotary_en1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C：Tube英文1366×768重新空白启动，缺四角色拒绝及底部生成/预览/导出禁用已检查；原生载入弯管，两实体Part实际确认有效。其余公共设置及工序检查待补，累计18/30。Skills：开发、验证、computer-use。见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/tube_en1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C：Tube英文1366×768公共七节点全部实际应用，150 mm平台、喷嘴/材料、两坐标及装夹有效；四角色与生成验证待补，累计18/30不变。Skills：开发、验证、computer-use。

2026-09-27 PRODUCT-01-V2C：Tube英文1366×768四角色实际选择、遗漏出口拒绝恢复、43775/43775严格回读及材料Stale门禁完成；材料已恢复有效，错误内圆及保存重开待补，累计18/30。Skills：开发、验证、computer-use。

2026-09-27 PRODUCT-01-V2C：Tube英文1366×768内圆拒绝/外圆恢复、保存重开及再次43775/43775严格回读完成，本组合关闭，累计19/30，余11组。Skills：five-axis-workbench-development（阶段门槛）、five-axis-slicer-validation、computer-use。见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/tube_en1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C：Freeform英文1366×768空白启动、缺项门禁、原生小STEP及Viewer边0012/面0006实际拾取已完成；公共设置及后续待补，累计19/30。Skills：开发、验证、computer-use。见[点击记录](../reviews/evidence/2026-09-26_v2_final_delivery/freeform_en1366_click_record.md)。

2026-09-27 PRODUCT-01-V2C：Freeform英文1366×768公共七节点实际应用，导引生成与独立设置重新生成均9/9点、1/1事件严格回读通过；独立/公共两次Stale及导出禁用已实测。角色恢复与保存重开待补，累计19/30。Skills：开发、验证、computer-use。

2026-09-27 PRODUCT-01-V2C：Freeform英文1366×768实际保存重开、再生成9点1事件严格回读通过；实体角色缺少对侧面拒绝和补齐恢复已实测，双模式切换与实体项目重开待补，累计19/30。Skills：开发、验证、computer-use。

2026-09-27 PRODUCT-01-V2C：Freeform英文1366×768双模式切换和角色项目保存重开完成；公共/独立/重开三次9点1事件回读通过，本组合关闭，累计20/30，余10组。Skills：five-axis-workbench-development（阶段门槛）、five-axis-slicer-validation、computer-use。见freeform_en1366_click_record.md。

2026-09-27 PRODUCT-01-V2C：开始Planar英文1920×1080，真实空白启动和尺寸核对完成，缺项门禁、载入STEP、Part及150 mm机床已实际确认，组合进行中，累计20/30。Skills：开发、验证、computer-use。见planar_en1920_click_record.md。

2026-09-27 PRODUCT-01-V2C：Planar英文1920×1080公共七节点实际完成，区域预览门禁及zigzag生成27/27严格回读通过；Stale、错误恢复、保存重开待补，累计20/30。Skills：开发、验证、computer-use。见planar_en1920_click_record.md。

2026-09-27 PRODUCT-01-V2C：Planar英文1920×1080两次Stale、保存重开再生成、空Part拒绝恢复已完成；独立和重开均27/27回读通过，失效引用恢复待补，累计20/30。Skills：开发、验证、computer-use。

2026-09-27 V2-02层带规划：wedge_layers.py按完整凸截面投影计算入口最低点和出口最高点，避免仅按中心线端点截断倾斜区域。新增5项解析测试全部通过（v2_02_wedge_layers_tests.xml），覆盖短尾层、斜出口柱厚守恒、中心线/共线输入拒绝和交叉边界拒绝；局部Ruff通过。当前仍为候选层带，未接入实际沉积路径，不能恢复弯管制造资格。支撑错误补充中英文提示，真实GUI复验待做。用户截图仍为旧NC，不能作为修复后结果。使用Skills：five-axis-workbench-development、five-axis-slicer-validation。下一步需将完整CAD截面投影与开放残余路径接入，并分别验证可沉积厚度、支撑及喷嘴运动；不得仅凭裁剪体积正确放行。

2026-09-27 V2-02用户指出NC预览形状不符：独立检查确认Tube输出MACHINE_PROFILE，预览器只认CONTROLLER_PROFILE，且缺TOOL_LENGTH_MM，实际自动识别(None,0)并显示machine_xyz。已让预览识别自有AC机床的明确标准轴映射，补齐Tube刀长声明，并兼容旧Tube manifest中的machine_trajectory；未知映射或缺刀长仍不猜测。4项专项通过，首次系统pytest临时目录WinError5改用项目独立临时目录后通过，失败JUnit保留。实际旧NC全部43775点与生成Toolpath比较，正确还原最大误差0.00000104394mm，原机床坐标最大偏差83.80316mm。证据：v2_02_nc_shape_audit.py/.json、v2_02_nc_preview_header_tests_localtemp.xml。该证据仅证明NC坐标还原，尚未证明与CAD完整珠道一致或制造承接正确。GUI仍为旧运行实例，尚未重启验证；统计栏固定逆变换公式在降级时仍显示的问题待修。使用Skills：开发、验证；独立Agent只读核对。V2-02不关闭。

2026-09-27预览坐标提示修复：移除统计栏固定逆变换文字，改为根据实际coordinate_transform显示机床XYZ未还原、含实际刀长的AC逆变换或路径坐标系。中英文6项呈现断言与局部Ruff通过。已通过computer-use关闭旧实例并启动新实例（窗口349965134），实际打开同一main.gcode，解析正在进行；尚未记录完成画面或CAD叠加。使用Skills：开发、验证、computer-use。

2026-09-27真实GUI复验：新实例完成同一旧NC加载，恢复直立弯管形状；实际打开example/pipe2/弯管新.stp并在同相机切换实体显示。弯管整体位置/轮廓对应，CAD基底存在而该工序只打印管体；实体遮挡路径，不能用此图证明逐段覆盖或承接。三张原生截图为v2_02_nc_corrected_gui.png、v2_02_nc_corrected_with_step.png、v2_02_nc_corrected_step_hidden.png。未更改诊断NC字节。坐标形状显示问题已获当前GUI证据；制造承接错误仍未修复，V2-02继续进行。Skills：开发、验证、computer-use。

2026-09-27 NC修复回归补充：既有GCodeSourceIndexTests、PreviewCacheTests连同首版新用例13项通过（v2_02_nc_preview_regression.xml）。新增实际postprocess_indexed_gcode→独立文件→load_gcode闭环，采用Rx(90°)与18mm刀长解析真值，不依赖manifest；新文件5项通过（v2_02_nc_export_roundtrip.xml）。Ruff通过。此项关闭文件声明互操作的测试缺口，不恢复弯管承接资格。Skills：开发、验证。

2026-09-27 CAD区域接入准备：新增wedge_footprint.py，从实际BRep与共同半空间交集计算容差扩展的保守投影，5项解析测试通过。真实pipe2全部14区的footprint→layer bands组成成功，合计450候选带，见v2_02_cad_wedge_probe.py/json；尚无沉积路径且保守矩形可能增加空候选，不把层数当制造通过。同步拆分新增超长函数，未修改预算；本轮check_context_budget.py exit0。拆分后承接7项、wedge layers/plan/volume18项、NC预览14项通过（v2_02_tube_prior_support_refactor_junit.xml、wedge_responsibility_split.xml、v2_02_nc_preview_refactor.xml）。新增gcode_preview_profile.py和result_statistics_text.py承接解析/提示职责，GUI此前证据早于该等价拆分，后续相关GUI仍需复验。Skills：开发、验证；多Agent分文件实施。下一步真实候选截面与开放过渡路径，V2-02不关闭。

2026-09-27过渡首末截面实测：14区各首末带共28次原始环截交成功，12个末带在中面裁中心线后为空，见v2_02_cad_wedge_sections.py/json。独立用实际CAD与共同半空间及层带上下平面求交体积，region2/3/4各0.01150559mm³、region13为0.001507026mm³仍有材料；region5-12尾带为0。证据v2_02_cad_wedge_tail_volume.py/json。因此不能以中面无中心线直接丢弃层带，需残余材料任务与完整带厚检查。这些量是完整CAD壁体积，不是0.6mm珠道实际体积；未生成新沉积路径或恢复制造资格。Skills：开发、验证。开放残余候选模块正在独立实现，V2-02继续。

2026-09-27全部层带候选检查：450次真实CAD截面无错误（v2_02_cad_all_sections.py/json）。新增wedge_path_candidates.py与6项解析测试，保留跨中面残余、零厚边界、闭环接缝及缺失截面的任务，尚未接入Indexed输出。真实数据形成430条候选路径/430个含路径层带，233个零厚几何端点和14738个残余任务（v2_02_all_path_candidates.py/json）。按0.6mm道宽与实际层带厚度的直线矩形棱柱逐段裁剪，14182任务为零体积，556任务为正体积，无计算错误；逐段体积和0.1633263323mm³，范围8.27e-9至0.0031133mm³，见v2_02_residual_prism_probe.py/json。此和不是几何并集体积，不计角点珠道重叠，也不是可成形或承接证明；零厚端点不能变成沉积命令，残余不能静默丢弃。Skills：开发、验证。V2-02保持进行中。
2026-09-27残余方案依据补充：查阅Song等原文并提出有界柱厚重分配，避免趋零独立沉积，具体公式及限制写入v2_02_tube_transition_design.md。58616个真实截面顶点柱厚抽样最小1.9618147mm，证据v2_02_region_column_height_probe.json；尚未证明有限道宽或可打印性。Skills：开发、验证。V2-02继续。

2026-09-27新增column_partition.py几何残余并层，14项解析测试通过；未接实际沉积。独立Agent及主线程核对发现Tube珠道中心/TCP混用：indexed中心层面首层Z5.1，OpenGL按±h/2显示5.0—5.2；xyzac._solve_linear却直接将point.position作为contact，NC23.1减18刀长后尖端5.1，距基底5仅0.1mm。此为物理契约冲突，FK/严格回读只能证明该目标自洽。需明确中心与尖端转换并同步碰撞、预览、后处理及读回，不能直接全局平移共享Toolpath影响其他工作台。V2-02不关闭；下一步优先核对并修复该接口与残余路径的统一语义。Skills：开发、验证。

2026-09-27 TCP接口修复进行中：新增manufacturing/tube_tcp.py，仅按Indexed连接语义从材料中心转换尖端；depart取前一沉积层高，travel/approach取后一沉积层高，保留IDs/events/体积。已接indexed_tube._solve_and_validate；碰撞新增独立nozzle_toolpath，仅喷嘴采样使用TCP，IPW记录仍用材料中心。Indexed算法版本两处升v6。16相关测试通过（首次PYTHONPATH缺失、随后旧简化夹具缺depart/travel失败，修正环境和夹具后通过，失败记录保留）；上下文门禁通过。真实旧路径首两个点独立转换与求解得中心Z5.1、尖端5.2、机器Z23.2、基底5，见v2_02_tcp_first_layer.json。当前修复未完成NC珠道中心元数据/预览及全路径回归，GUI仍早于此变更，不能据此关闭V2-02或恢复旧导出资格。下一步补齐NC明确位置语义并与中心线预览一致。Skills：开发、验证。

2026-09-27 NC中心/TCP闭环：Indexed专属声明与逐点宽高/偏移元数据已接后处理及独立预览，机器轴保持真实TCP。水平、倾斜、不同层高、旧NC兼容、未知/缺失元数据拒绝及严格回读共19项测试通过，证据v2_02_tube_nc_material_preview_junit.xml；Agent完成Ruff/Mypy/context检查，未运行Qt。新增bounded_wedge_paths.py将柱厚并层转换为候选路径，厚度突变保留双侧端点并断开挤出，4项解析检查通过（v2_02_bounded_wedge_paths.xml），局部Ruff和context通过。仍未接完整弯管生产生成，有限道宽覆盖、承接、碰撞及当前GUI复验待做。V2-02不关闭。使用Skills：five-axis-workbench-development、five-axis-slicer-validation；本轮实际调用登记。方法限制：中心柱区间守恒不能替代真实珠道覆盖证明。

2026-09-27有界候选完整数据检查：复用已保存的450个实际CAD截面，形成429个含路径层带、800条开放/闭合候选路径，厚度0.1—0.3mm（浮点尾差约3e-15），零厚端点0，15532项残余检查任务，见v2_02_bounded_path_candidates.py/json。对13处分区转换的首层全部候选端点，与此前所有候选线段作连续最近距离和保守包络半径检查，明确不接触点为0，见v2_02_bounded_transition_probe.py/json；这只是必要条件，不能证明足够支撑、有限宽覆盖、无重叠或无碰撞，也未输出实际制造路径。45项组合领域回归通过（v2_02_tube_v6_combined.xml）。下一步核对移动后中心线是否仍符合真实管壁，并处理有限道宽/残余任务及生产接入。Skills：开发、验证。V2-02继续。

2026-09-27变高路径接口补充：发现开放弧起点approach不能沿用首个沉积终点的高度，否则斜变厚段的起点TCP偏移错误。tube_tcp.py优先使用点上显式layer_height_mm，旧无显式值连接继续使用相邻沉积高度。独立0.1→0.3mm反例验证起点偏移0.05mm、终点0.15mm；16项TCP/碰撞/NC相关测试通过（v2_02_tcp_variable_start.xml），局部Ruff通过。该接口准备尚未接入新候选路径生成，真实管壁贴合量测由独立Agent进行，V2-02不关闭。使用Skills：开发、验证。

2026-09-27开放路径生成接口与独立壁厚核查：现有_PathBuilder.add_layer增加逐点层厚与外部积分段体积输入，变高路径缺体积拒绝，路径间保持depart/travel/approach而不补闭合挤出；approach/travel显式保存起点层厚。32项相关测试及3子测试通过（v2_02_open_builder.xml），Ruff/Mypy/context通过。既有碰撞回归首轮2失败源于障碍仍放材料中心，按解析h=1mm将障碍移至真实TCP后21项及3子测试通过，保留v2_02_pipeline_v6.xml失败与tipfixture成功证据。Agent独立v2_02_bounded_shape_audit.py/json/md量测44202中心点轴向移动max0.05mm，径向中壁偏差max0.00721281mm；88404横向边缘点未越壁，但实际壁厚1mm，0.6mm单珠留下两侧约0.2mm未覆盖材料。现有0.02弦误差和0.05分区弧垂误差不可挪作覆盖容差。新候选尚未接正式生成；下一步明确并实现完整壁厚覆盖和有限珠道验证，不能只以单中心线形状接近CAD恢复资格。Skills：开发、验证。V2-02继续。

2026-09-27壁厚分道与逐点宽度：参考Prusa官方Arachne说明 https://help.prusa3d.com/article/arachne-perimeter-generator_352769 的变道宽填壁方向，独立实现受限wall_tracks.py等分截面柱候选，不复现Arachne。Agent完成8项解析测试、Ruff/Mypy；1mm圆环/.6目标形成两道.5mm，保留斜截面宽度/完整覆盖/未校准最小宽度限制。主线程_PathBuilder增加widths_mm并要求外部段体积，NC逐点宽度不再按layer_id取最后值，避免同层多道宽度串用。29项相关测试及3子测试通过（v2_02_width_builder.xml），Ruff/context通过。真实450截面的wall_tracks_probe运行中，尚未生产接入及制造放行。使用Skills：开发、验证。
2026-09-27真实分道候选完成：450个实际CAD截面全部生成2道，各点宽度0.500000—0.509035mm（浮点尾差忽略于显示），见v2_02_wall_tracks_probe.py/json。该结果仅覆盖截面柱几何，尚未与共同边界、残余层和完整珠道并集组合。主线程2源码Mypy通过。V2-02继续。

2026-09-27双道残余完整诊断组合：新增wedge_tracks按严格投影匹配插值道宽/法向，5项测试通过；ruled_bead_volume按固定生长轴及线性横向跨度/层厚解析积分Jacobian，4项解析测试通过，拒绝折叠单元。19项组合测试通过（v2_02_combination.xml）；Mypy首次发现依赖wedge_volume的cap center三元组类型问题，复用_vector修复后Mypy及10项体积回归通过。真实450截面形成1600条诊断开放/闭合路径、91516点，其中86718沉积点，31150残余任务，组合错误0，见v2_02_combined_diagnostic.py/toolpath.json/summary.json。逐段体积和6477.4620mm³，对解析圆环扫掠6473.0720mm³偏多4.3900mm³（0.06782%），见v2_02_combined_volume_comparison.json；总量不能证明局部无遗漏/重叠，未做CAD裁剪/并集、碰撞或完整承接。禁止视为合格制造路径，未接正式入口。下一步局部有限珠道检查及变尺寸段包络一致性。Skills：开发、验证。V2-02继续。

2026-09-27组合路径承接与角点核查：tube_support对变尺寸前段采用两个端点最大包络半径，防止只用终点小尺寸误报悬空；8项测试（v2_02_taper_support.xml）、Mypy/context通过。91516点诊断路径执行transition_support_issues得到0问题（v2_02_combined_support.py/json），仅为分区首层端点必要接触条件。独立Agent角点核查86718段693744个起止角点，entry越界仅浮点尾差；exit最大0.0256528921mm、内壁最大0.0114693172mm、外壁0.0109477930mm，见v2_02_combined_corners_audit.py/json/md。1e-8仅数值统计阈值，不是新增制造容差。总量近似正确不能掩盖这些局部偏差；需处理有限道宽斜边界、重叠/缺料与当前IPW变尺寸包络，不能直接放行制造。Skills：开发、验证。V2-02继续。

2026-09-27变尺寸IPW与实际诊断碰撞：_record_deposition改为两个端点宽高最大值建立既有椭圆珠道胶囊，防止较宽起点漏入索引，未把该模型称为矩形珠道完整几何。14项碰撞相关测试通过（v2_02_variable_ipw.xml），Ruff通过。完整91516点诊断路径经TCP转换，在0.05mm采样参数下对IPW检查1947046次，0碰撞（v2_02_combined_ipw_probe.py/json）；该轮无基底/夹具，另已启动加入原source/settings对应基底AABB的补查。用户已收到独立CAD几何验收公差问题（0.02/0.01/自行指定），当前未据已测偏差反设容差；仍继续独立工作。Skills：开发、验证。V2-02不关闭。
2026-09-27基底补查完成：同一完整诊断路径加入已保存基底AABB后，1947046次采样检查仍无碰撞，见v2_02_combined_substrate_probe.py/json。来源基底范围与原输入/设置对应，未增加不存在的夹具。保留采样/椭圆胶囊及未放行限制。

2026-09-27完整诊断机器轴与NC回读：91516点完成真实自有AC机型、18mm喷嘴TCP求解，生成明确标注DIAGNOSTIC ONLY/NOT MANUFACTURING QUALIFIED/machine_executable=false的v2_02_combined_diagnostic_only.gcode。严格磁盘回读91516/91516通过，坐标/进给/挤出/事件顺序差异均0；文件预览94715时间步中91516空间点，材料中心恢复最大偏差1.2155744e-6mm，见v2_02_combined_nc_roundtrip.py/json。唯一轴警告为首19049点直立奇异段保留C=0，未产生轴错误。该证据验证诊断路径忠实转换，不证明局部几何、材料并集或真实GUI；没有恢复生产导出资格。Skills：开发、验证。V2-02继续。

2026-09-27当前GUI诊断预览复验：旧窗口已不存在，使用当前源码启动新实例（窗口148573352，运行会话50416），真实点击打开v2_02_combined_diagnostic_only.gcode并完成加载，再打开example/pipe2/弯管新.stp、同相机切换实体显示。截图v2_02_combined_gui_nc.png、v2_02_combined_gui_with_step.png、v2_02_combined_gui_step_hidden.png；整体位置与轮廓对应，实体遮挡及密集路径不能证明局部覆盖。界面检测层数仍1，需Indexed NC明确层标记，已分派修复，截图早于该修复。加载过程持续推进但耗时较长；只读代码审查v2_03_nc_parse_code_audit.md发现每运动段起终点重复完整FK/机型验证（约183032次），未测性能占比，候选改进为会话内精确姿态缓存，不能删校验或取消。生产几何与V2-02全链未关闭。使用Skills：开发、验证、computer-use（本轮实际调用登记）。

2026-09-27层导航与解析性能：Indexed专属后处理新增indexed_layers.py，按真实layer_id首次顺序输出标准Layer标记，同层双道/开放弧不增层、非平面Z不猜层、空移沿源目标层；Agent后处理→parse及头声明7项通过，尚未重生成完整带层NC/GUI复验。小样本cProfile定位2000运动中4000次机床变换，5.262s中4.903s在该路径；新增每parse会话独立128项精确姿态缓存，保持每次轴字/异常回退验证，不舍入角度、不缓存失败、机型对象强引用隔离。19项及3子测试通过（v2_03_pose_cache.xml）、Ruff/Mypy/context通过。相同2000运动剖析0.332s；完整原诊断NC不使用磁盘缓存的parse耗时6.591s，91516点最大中心偏差仍1.2155744e-6mm，道宽误差0、层厚误差8.19e-15mm（v2_03_full_parse_cached_pose.py/json）。这是纯解析测量，未将其当作GUI加载/取消验收。Skills：开发、验证。V2-02及V2-03均未关闭。

2026-09-27带层诊断NC归档：核对v2_02_combined_layered_roundtrip.json与实际G-code SHA256一致（46b50f726b9a4d0e5819574ceee9cfce252e4aee7b3a894c9ff0cc814b5ee1be），严格回读91516/91516通过。新增独立v2_02_layer_identity_audit.py/json逐点比较源layer_id与文件预览层编号：91516个空间点、429层，层身份差异0，避免仅凭层数相等判断正确。该证据只关闭诊断文件的层标记对应检查，GUI层导航尚未复验，生产几何越界、覆盖及正式生成接入仍未完成，V2-02保持开放。使用Skills：five-axis-workbench-development、five-axis-slicer-validation，本轮实际调用登记。上一轮为用户解释未改变项目状态，本轮补充当前磁盘核验与逐点证据。

2026-09-27真实GUI带层复验：当前窗口569313924真实打开带层诊断NC，观察加载进度23.9%→92.9%→完成；界面检测429层、91516空间段、86718正挤出段。实际下拉选择层0—24后仅显示底部环带，点击下一组后显示层25—49及上移环带。截图v2_02_layered_gui_loaded.png、v2_02_layered_gui_first25.png、v2_02_layered_gui_next25.png。本轮证明该文件层范围过滤及下一组按钮可用；没有量测端到端加载时间或取消，不扩大为V2-03通过。几何后续调整检查方向：内部共同分区面的越界需与相邻沉积材料组合检查，不能直接当作CAD外表面误差；已委派最坏分区局部覆盖/重叠量测，暂停增加仅返回残余任务的候选模块。V2-02仍开放。使用Skills：computer-use、five-axis-workbench-development、five-axis-slicer-validation。

2026-09-27局部并集与加载测量：独立Agent完成v2_02_boundary_union_probe.py/md/json及fine.json。region12内部越界656角点中630仍在CAD壁内，全部在region13平面域；不能将0.02565mm内部归属越界误报为外形误差。最坏接缝0.8×0.8×0.12mm区域以0.005mm采样，CAD体积0.0768mm³、材料并集0.07324425、重叠0.003393、未填0.00355575，局部外超0；未填全部在region12侧。下一步应调整有限宽末层及邻区起始层，沿同一局部区域比较，再扩大到完整接缝。V2-02不关闭。
V2-03新增可复现v2_03_finalize_cancel_probe.py/json：10万运动输入耗尽时请求取消，最终处理后0.331s抛出取消，未据静态怀疑增加无依据改动。真实GUI重载后读只读状态记录request3 complete、端到端7.377614s、worker6.765127s、cache_hit=false（v2_03_gui_reload_metrics.json）。两次尝试点击取消时，最终状态都是complete，未证明取消成功；不可将旧图保留当取消证据。后续需在耗时更长的实际任务中检查取消。使用Skills：开发、验证、computer-use；当前目标保持active。

2026-09-27按用户最新要求调整：计划§7明确暂缓新弯管诊断方案微小接缝优化，保留局部缺口/重叠证据和未验证限制；不恢复旧单道欠填及大间隙方案资格，不放宽公差、不删除核心Error。后续优先新方案生产接入与完整GUI六件套/回读/保存重开，再推进其余工作包。用户关于实物鲁棒性的判断不替代实机证据，machine_executable=false保持。此次是任务优先级调整，非验收通过。使用Skills：five-axis-workbench-development、five-axis-slicer-validation（沿用本任务已读流程）；目标active。

2026-09-27正式接入准备已实现：新增bounded_indexed.py从当前BRep实时生成双道/有界厚度Toolpath及BoundedIndexedSlicePlan，保留全部band、非空layer映射与residual_task_count，逐band/track/path取消检查，异常不吞、空region明确报错。Agent实时CAD直管3项测试、Ruff/Mypy/context通过，尚未切换产品入口。新增bounded_tube_geometry.sampled_wall_errors为多道中心采用真实内外半径包含检查及段内弦误差，避免旧中壁半径检查误报；5项解析测试通过，Ruff/Mypy通过。首次测试夹具遗漏extrusion_role导致5失败，修正后证据v2_02_bounded_geometry_fixed.xml；失败XML保留。中心包含不能证明珠道完整覆盖。下一步将策略接到product生成、序列化及策略对应验证，并用真实弯管全链复验。Skills：开发、验证。V2-02继续，微小接缝优化按计划§7暂缓。

2026-09-27用户明确要求“不要钻牛角尖”，已写入交付计划§8：停止微小接缝精细采样/新候选模块，非阻塞项登记后推进，不新增交付门槛，不无变化重复验证；优先现有方案正式接入和完整案例，减少细碎回合。此执行纪律覆盖此前继续优化微小接缝的后续建议，核心错误和原计划必要验证仍保留。目标继续active。

2026-09-27 V2-04独立推进：将教程assets内8份捕获过程JSON移至本轮evidence/guide_capture_records，逐字节及SHA256核对，relocation_manifest保留原路径，README说明历史相对图片路径解析；更新2份历史复盘显式链接，未修改历史事实。图片审计83引用/0缺失，15低对比仍待视觉，独立Agent进行实际逐图检查。新Tube正式service接入由领域Agent执行中，未宣称完成。当前不再深挖微小接缝，按计划§8并行推进独立交付项。

2026-09-27 V2-02正式产品链已接bounded实时CAD生成，原支撑/碰撞/轴/回读保留，边界精度待验证为Warning，计划序列化含策略/bands/layer映射/残余计数，版本v7。Agent相关领域回归及Ruff/Mypy/context通过；真实pipe2正式service已启动，执行会话23630仍运行，证据脚本v2_02_live_service_v7.py，不重复启动。GUI闭环待做。
V2-05新建tmp/v2_clean_install，include-system-site-packages=false，按README执行pip install -e .退出0，pip check无冲突，OCP/Qt/VTK/NumPy导入通过；日志及freeze归档。此为干净运行依赖安装，不是最终wheel或完整新环境GUI验收，V2-05不关闭。V2-04修正rotary_workbench_zh图注：原图只显示Warning路径，不声称展示导出目录/六文件；图片替换仍待做。使用Skills：开发、验证。

2026-09-27正式pipe2服务完成：v2_02_live_service_v7.py/log/json，209.226s，429层/91516点，exportable=true、strict readback=true，仅xyzac.rotary_singularity与tube.bounded_boundary_accuracy_deferred警告，check_ipw=true及原基底AABB保留。此为正式服务真实CAD链证据，GUI闭环仍待完成。V2-04累计48唯一图已实际复核（含4普通图片链接），重拍归并11组连续场景，见v2_04_visual_review.md与replacement_candidates.json。
V2-05首次独立GUI启动失败：ModuleNotFoundError cadquery，定位Planar offset/support在运行时导入CadQuery，而原pyproject仅列cad-tests。已把既有2.7范围移入运行依赖并修正README，不改算法；参考CadQuery官方安装说明与实际源码。修正后独立环境重装会话2796正在运行，日志v2_05_clean_install_runtime_fix.log；旧GUI已正常退出，尚未启动替代实例。此失败说明仅pip check/import OCP不等于应用启动通过，保留未完成状态。

2026-09-27独立环境Qt启动修复：用户提供无Qt平台插件弹窗。实际QLibraryInfo.PluginsPath返回F:/???????/...，路径不存在；PyQt5.__file__计算真实中文路径，qwindows.dll实际存在。参考Qt QCoreApplication.addLibraryPath官方API，在app.main仅默认插件目录失效时加入绑定包内真实Qt5/plugins目录，不改系统环境。Windows QApplication最小实测platformName=windows、退出0，Ruff通过；同一独立环境真实主界面成功启动，窗口4131906，会话65755，截图v2_05_clean_start_fixed.png。CadQuery补依赖重装亦已退出0、pip check通过，freeze已归档。启动通过不替代示例生成/导出与最终wheel验收；下一步在此界面继续项目闭环。

2026-09-27 V2-02 v7非Qt产品回归收口：使用合法短直管夹具替换旧10mm道宽/层高快速夹具；低速正常流程与真实加速度超限拒绝导出分开验证。独立双道半径5.25/5.75mm、材料中心到TCP半层偏移及v7版本断言更新，保留坐标变换/FK、弦误差、取消状态、旧上下文失效、六件套和严格回读断言，未放宽产品校验。19 passed、2 subtests passed，见evidence/2026-09-26_v2_final_delivery/v2_02_v7_product_regression_final.xml；两轮发现过期断言的失败XML保留，Ruff通过。仅测试文件修改，未运行Qt或重复大pipe2，不替代GUI验收。实际使用Skills：five-axis-slicer-validation、five-axis-workbench-development。

2026-09-27 V2-02/V2-03真实GUI推进：独立安装环境窗口4131906打开tube_en1366_current150，点击生成后实际取消，界面显示生成已取消、生成按钮恢复且导出未误启用（v2_03_tube_generating.png、v2_03_tube_cancelled.png）。本次取消前没有有效结果，尚不证明旧结果保留。随后重新完整生成、查看路径及缩放、实际导出tube_v7_gui_export六件套；manifest严格回读91516/91516点通过，四类差异均空，collision_check_complete=true，511685采样，仅奇异/边界暂缓/参考设备Warning。保存tube_v7_gui_project并真实重开，参数及几何引用恢复；路径运行时未恢复、查看/导出禁用，待核对持久化设计，不宣称全部闭环完成。截图v2_02_v7_gui_path/exported/reopened.png。使用Skills：computer-use、five-axis-workbench-development、five-axis-slicer-validation；本次实际调用登记。V2-02/V2-03/V2-05保持进行中，微接缝按计划§7暂缓。

2026-09-27弯管重开行为核清：tube_generation_service恢复product_states但不恢复内存product_results，tube_serialization只保存状态；tube_workbench_zh.md第132行明确重开恢复输入后需重新生成，属于既有合同，不新增运行时缓存恢复要求。当前GUI另实际打开tube_v7_gui_export/main.gcode，429层、91516空间点，切换空移并拖动旋转，路径及方向标响应，截图v2_02_v7_gui_nc_travel_rotated.png。弯管本次正式生成/预览/六件套/严格回读/输入保存重开已形成证据；微小接缝限制保留。V2-02其余代表案例、V2-03有效旧结果取消保留及V2-04/V2-05剩余门槛继续。

2026-09-27 V2-02校徽当前配置复验启动：真实GUI载入gui_agent_logo/project.json/project.json，原机型快照v1为180mm；通过机型下拉选择内置自有AC v2、应用并重新应用Placement，当前machine hash ac7738eb81c857223aca1a69db9e81710d37dcd659f34cd1821c4f837673714c（150mm）。进入Freeform点击生成与检查，窗口4131906仍运行，HTTP generation_in_progress=true，状态归档v2_02_logo_current150_generating.json；尚未报告成功或重启计算。V2-04仅修正Tube中英文教程v7多道/实际层厚/TCP及暂缓Warning说明，原有重开输入合同保留，旧截图明确为操作示例，本地链接通过，图片重制仍待做。实际Skills：开发、验证、computer-use。目标active。

2026-09-27 V2-05当前完整静态门禁通过：quality_v7_current.log首次因诊断脚本格式/导入失败；对22份证据脚本仅作格式与等价静态整理，前后SHA见v7_static_script_changes.json，历史结果未修改、未重跑模型。产品源码仅导入/格式及workbench_issue_ui局部变量重命名消除str与str|None复用。最终quality_v7_static_final.log中Ruff、迁移Ruff、安全规则、61文件格式、上下文预算及Mypy218源码全部通过，退出0；没有排除目录或放宽基线。校徽GUI当前仍generation_in_progress，应用会话65755确认存活，未重启。此静态通过不等同于完整回归、最终包或托管CI完成。实际Skills：开发、验证；目标active。

2026-09-27 V2-05当前源码包检查：python -m build --outdir tmp/v2_release_current退出0，wheel/sdist版本2.6.3.dev3+gedacd49.d20260927，twine check两包PASSED。日志v2_05_build_current.log、v2_05_twine_current.log；v2_05_package_current.json记录SHA并核对wheel包含bounded_indexed、bounded_tube_geometry及own_ac_fdm资源，METADATA包含运行时CadQuery。当前为未封版工作区构建，不称最终提交CI或wheel新环境完整流程已通过。校徽仍为原GUI生成任务，未重复启动。Skills：five-axis-slicer-validation、five-axis-workbench-development。目标继续active。

2026-09-27 V2-02校徽GUI完成生成及六件套导出：logo_current150_gui_export含六文件，manifest严格回读102969/102969点、21984/21984事件通过、issues为空，machine_executable=false；ready状态见v2_02_logo_current150_ready.json。V2-03补齐真实有效结果取消保留：在同窗口点击再次生成后取消，HTTP生成状态false且提示已取消，产品与取消前完整JSON相等，GUI导出重新启用、路径保留；证据v2_03_logo_cancel_state.json及v2_03_logo_cancel_preserved.png。不把工具调用耗时当精确取消延迟。校徽尚需补预览细看、保存重开；整体目标不关闭。使用Skills：computer-use、开发、验证。

2026-09-27校徽保存重开通过：真实GUI保存logo_current150_gui_project并重新选择其project.json载入，正常使用项目内STEP副本；与生成前ready快照比较，freeform.operations完整JSON一致，机型仍v2及150mm资源hash一致。状态v2_02_logo_reopened.json。生成路径依既有合同不持久化，未误称恢复运行时结果。生成路径已实际缩放，完整密集显示尚不能辨清校徽局部沉积，后续用导出NC阶段筛选补查，不重跑生成。V2-02继续，整体目标未完成。

2026-09-27校徽NC真实预览补验：打开logo_current150_gui_export/main.gcode，实际选择操作2、切换空移、放大后文字/环线/顶部图案可辨，点击上一操作切至底座工序，截图v2_02_logo_nc_stage2.png、v2_02_logo_nc_stage1.png。该预览连同前述GUI生成、六件套严格回读及输入保存重开构成当前校徽流程证据，不当作实物精度证明。V2-05补查wheel全部218个Python文件与src逐字节一致，v2_05_wheel_source_match.json差异为空。下一代表案例为叶轮，目标active。

2026-09-27 V2-02叶轮装夹纠正：用户指出模型远离圆台。核对原impeller_gui_root_growth_live/project.json，Build CS为单位变换，Placement的T_mount_from_build却含XYZ各+250mm，局部adjustment为0；因此界面零微调不等于绝对居中。真实GUI取消旧装夹生成，设置局部DX/DY/DZ各-250mm并应用，显示模型后叶轮与150mm圆台同心、底面落台（v2_02_impeller_centered.png）。保存impeller_centered150_gui_project/project.json，回读确认实际T_mount_from_build为单位矩阵、圆台diameter_mm=150；未改源STEP、未缩放、未仅移动相机。已按新装夹重新生成，尚未完成该轮路径检查，旧偏移结果不作为本轮居中验收。UI补充显式重置安装位入口由独立Agent处理。外部参考为Prusa官方对象操作面板的落台/位置操作，https://help.prusa3d.com/article/object-manipulation-panel_1757 ，具体修正依据本项目实际持久化矩阵。使用Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use；本次实际调用登记。目标保持active。

2026-09-27装夹防复发补充：Placement新增中英文“重置到安装位原点”按钮，清除历史reference与局部adjustment，仅更新草稿，保留应用/取消语义；帮助说明零微调不代表平台中心，模型底面位置仍由Build CS定义。独立Agent完成tube_controller纯领域回归12 passed、6 subtests，证据placement_reset_domain.xml；Ruff、context和新helper Mypy通过。主Agent复核helper/调用和测试；正在运行的GUI尚未重启，新增按钮真实点击未验收，不计为界面通过。用户当前叶轮居中操作已通过旧界面实际完成并保存。无新增精度优化范围，后续继续原计划。

2026-09-27 V2-04本轮完成实质替换：当前真实GUI拍摄中英首页、中英150mm机床、叶轮现有曲面操作、Model CS和Build CS编辑器；坐标编辑未修改，拍摄后均取消草稿。复用已验证Tube导出图及校徽阶段2局部。独立Agent逐图查看、裁除外围光晕/内部路径，更新6张旧图共20处引用，另新增校徽局部图；来源/裁剪/SHA及逐批链接核验见v2_04_current_image_replacements.md/json，candidate相应replacement_applied=true。原证据不变，设置草稿不冒称生成完成，其余图片仍待。使用Skills：five-axis-workbench-development、computer-use。
V2-05装夹重置后完整质量检查：首次quality_placement_current.log发现tube_ui导入排序，修正后quality_placement_fixed.log退出0，Ruff/security/format/context/Mypy219全部通过；无修改基线。V2-03本机为i7-12700H、14核20线程、31.8GB、Windows11，归档v2_03_machine_environment.json。居中叶轮生成期间曾实际响应显隐、语言及页面切换；15:55附近出现未响应，v2_03_impeller_busy_observed.png。15:56进程57380仍在、CPU累计2588.17s、Responding=false，HTTP15s观察超时，不当作任务终止、不重启生成；该长任务响应判据仍待核对恢复。v2_02_impeller_centered_generating.json保留此前活跃快照。完整目标保持active；本轮有教程替换及质量证据进展。

2026-09-27 V2-03叶轮长任务热点确认与修复：临时工具py-spy按官方dump用法只读采样进程57380，两次均停在_PrintedSegmentIndex.candidates；第二次局部量显示sequence=682。原查询对重复样本反复合并含未来沉积的大桶且无检查点。已在postprocessing/printed_segment_index.py保持原空间桶及精确碰撞判定，按网格去重、bisect_left取index<sequence前缀、批量调用既有checkpoint。25项相关回归通过，合成基准候选681个完全一致，1.129792s→0.001925s；不外推整件耗时。简报impeller_candidate_fix.md、栈v2_03_impeller_stack.txt、测试impeller_candidate_index_final.xml、基准impeller_candidate_benchmark.json。确认源码热点、保存项目哈希并尝试UI返回无响应后，结束本任务旧进程57380，session65755退出1；不是把HTTP超时当自然终止。
新版独立环境GUI会话4797、窗口53152702已启动，真实打开impeller_centered150_gui_project，点击新增重置/取消/再次重置/应用；保存impeller_reset150_gui_project并回读actualT为单位矩阵、adjustment全0，v2_03_placement_reset_applied.png。取消后树恢复有效，但控件仍保留草稿显示，不误称字段自动刷新；领域取消语义已有测试。随后真实点击完整生成，起始观察时刻见v2_03_impeller_fixed_start.txt，当前进程2448、generation_in_progress=true且last_error=null；完成/导出仍待。新增源码后quality_impeller_candidate_final.log全套门禁退出0。使用Skills：开发、验证、computer-use；目标继续active。

2026-09-27 V2-04追加实际替换：独立Agent逐张查看12个当前V2-01候选，新增Curve中英选边、Planar本地编辑器、Rotary侧面选取4张旧图的5处替换，累计10张旧图、25处引用，另新增校徽局部图。保留状态和用途，不用Zigzag冒充三角填充、不用Spiral冒充Around Part；最新51相关链接有效。中英坐标指南同步说明重置安装位需Apply、按Build CS配对而非自动寻找底面；不用-250补偿作为用户操作要求。来源和裁图仍见v2_04_current_image_replacements.md/json。使用Skill：five-axis-workbench-development。
V2-02下一输入已定位：2026-09-24_three_color_fan_gui_project_corrected/project.json/project.json可同时检查三叶整件与T0/T1/T2换料，需换当前150mm机型；原保存层高0.4/采样0.8，历史0.8/1.6粗参数仅功能证据，不当作0.4喷嘴打印资格。机床/站位仍离线。新叶轮16:13状态正常响应，16:14栈在solve_xyzac_trajectory，v2_03_impeller_fixed_stack.txt及fixed_generating.json；尚未完成整件。V2-03/04/05均不提前关闭。

2026-09-27 V2-04第二批复用完成：独立Agent实际查看12张候选，替换IMG-010/026/029/031共4张旧图9处引用，累计14张旧图34处引用，另新增校徽局部图；52个相关链接有效。Part空面板不能代替实体表、Placement光晕贴应用按钮，均未伪造替换。来源与保留判断见v2_04_current_image_replacements.md/json。V2-05已启动包含装夹重置和候选索引修复的当前包构建，session75541，完成状态待核对。叶轮进程2448仍存活、Responding=true且generation_in_progress=true；实际截图确认居中及生成状态，不将等待记为完成。Skills沿用开发、验证、computer-use。

2026-09-27 V2-05当前包构建完成：session75541退出0，tmp/v2_release_final的wheel与sdist经Twine均PASSED；v2_05_build_final.log、v2_05_twine_final.log、v2_05_final_package_hashes.json保留结果。逐文件核对wheel内220个Python源码与当前src字节一致，无遗漏/差异，见v2_05_final_wheel_source_check.json。此包包含装夹重置与候选索引修复；安装启动、最终全回归和提交CI尚待，源码再改需重新构建，不关闭V2-05。

2026-09-27 V2-03当前叶轮运行观察：16:25—16:28进程2448保持Responding=true，实际点击显示模型关闭/恢复均响应，截图v2_03_impeller_fixed_hide_responsive.png；16:26只读栈位于_sample_move/forward_kinematics的换姿空移规划，已进入原热点所属阶段，尚未证明整件完成。16:27:59仍generation_in_progress=true、last_error=null、CPU累计1033.3125s。未重启计算。V2-05独立只读提交范围审查发现历史输入manufacturing-setup.yaml被GUI自动保存，当前不stage历史变更；新证据含超100MiB文件，后续明确选择摘要及必要文件，不整目录加入。Skills：开发、验证、computer-use。

2026-09-27 V2-04保留与补拍收口：独立Agent逐图判定16张编号图及3张普通链接图可按原教学用途保留，新增当前Planar Zigzag替换5处，累计15张旧图39处引用；修正Rotary零原点和Spiral导出状态图注，218本地链接有效，剩余14张旧图归并7组，见v2_04_minimum_remaining_captures.md。主GUI本轮实拍中文/英文材料T0/T1草稿表和中文换料站空字段，文件v2_04_material_zh_draft_raw.png、material_en_draft_raw.png、station_zh_fields_raw.png（均v2_04前缀）；两次材料草稿和换料站均Cancel，未应用到叶轮。已交独立Agent替换相关教程，尚未计入上述累计。16:33叶轮仍运行无last_error，语言及对话框实际响应；不重启。Skills：开发、验证、computer-use。

2026-09-27 V2-02叶轮完整GUI生成成功：当前产品generated_at为16:33:54.992，起始观察16:09:53，相差约24分02秒（非独立精确点击计时）。真实自由曲面界面显示完整叶轮沉积路径、生成恢复及导出可用，仅Warning；v2_02_impeller_fixed_generated.png和completed_state.json。严格回读810990/810990路径点、16983/16983事件，issues空，offline_exportable=true、machine_executable=false；摘要v2_02_impeller_fixed_summary.json。导出目录已建但两次工具检测到用户正在操作窗口而拒绝点击，因此尚未导出，不与用户抢鼠标，六件套/重开待继续。V2-04材料三图已替换，累计18图42引用；又实拍Part角色和Placement编辑控件，未改字段并取消，已交Agent整理。Skills：开发、验证、computer-use。

2026-09-27 V2-02叶轮GUI导出与保存完成：用户截图窗口关闭后真实点击导出，impeller_reset150_gui_export生成main.gcode、machine_axes.csv、manifest.json、preview.json、toolpath.json、warnings.json共六文件；manifest回读810990点/16983事件一致，issues空，machine_executable=false。逐文件大小与SHA256见v2_02_impeller_export_hashes.json，导出后截图v2_02_impeller_fixed_exported.png。实际Ctrl+S保存到impeller_completed150_gui_project，project.json及STEP/Setup已落盘；重开及NC界面预览仍待。V2-04 Part/Placement两图已替换，累计20旧图48处引用，剩余9图5组，218链接有效。Skills：开发、验证、computer-use。

2026-09-27 V2-02叶轮保存重开完成：真实打开impeller_completed150_gui_project/project.json，source_hash保持3776fe6e…f21f，操作1项恢复、last_error=null；模型显隐后确认仍位于圆台中心。v2_02_impeller_reopened.png及reopened_state.json。产品内存结果0、导出禁用符合此前已核实的输入持久化合同，不新增重算要求。随后真实打开impeller_reset150_gui_export/main.gcode进入NC页，request1正在parse，进度约30.6%；空移和阶段导航待载入完成。用户已表示叶轮路径视觉无明显问题，本轮不追加几何精度优化。Skills：开发、验证、computer-use。

2026-09-27 V2-02叶轮代表案例GUI链完成：导出NC request1首次加载complete，worker403.274s、端到端407.922s、cache_hit=false。实际显示全部沉积、打开橙色空移、下拉操作2、缩放并拖动旋转、下一阶段到操作3，单叶片及转场可见且操作响应；v2_02_impeller_nc_travel.png、stage2_rotated.png、stage3.png及nc_preview_summary.json。NC页未单独加载STEP的Warning解释明确，不是生成Error。输入保存重开、生成六件套与严格回读证据已齐，本例不再重复生成或精度优化。首次NC加载较慢如实保留，不宣称快速。V2-02整体仍待三叶/多色案例；V2-04剩余9图5组、V2-05最终回归/安装包启动/CI继续。Skills：开发、验证、computer-use。

2026-09-27 V2-02三叶扇多色当前流程启动：复制历史输入到three_color_current150_gui_project后真实GUI打开，取消残留Placement草稿，应用内置150mm机型并重新应用零微调装夹，树恢复有效。实际打开材料表核对T0/T1/T2（v2_02_three_color_materials.png），取消未修改的表格后点击生成与检查。当前generation_in_progress=true、last_error=null，进程2448响应正常；状态v2_02_three_color_generating_state.json。保存参数为层高0.4mm、采样0.8mm，未为加速改成历史粗参数。生成、导出和回读尚待完成，不提前计为通过。使用Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use；本次调用登记。


2026-09-27 V2-03完成：按计划逐项复核明确生成状态、空结果取消、校徽有效结果取消保留、索引检查点25项回归、修复后81万点叶轮生成期间显隐/语言/对话框响应、完整NC路线与工序过滤/旋转/放大真实操作。证据映射见v2_03_v2_05_remaining_current.md。首次无缓存NC载入407.922秒保留为性能限制，不宣称快速或所有阶段相同取消延迟；不因该限制新增优化门槛。V2-04当前角色图IMG027已替换，两指南如实说明生成期间设置及角色待核对，累计21图50引用，剩余8图4组；最短操作见next_capture_steps.md。三叶扇换料站实际打开核对并取消未修改草稿，v2_02_three_color_station.png；生成仍在运行，未重启。V2-05独立新venv tmp/v2_wheel_install_final已启动最终候选wheel安装，session90351，结果待核对；未修改运行中GUI环境。Skills：开发、验证、computer-use。PRODUCT-01仍进行中。


2026-09-27 V2-05最终候选wheel独立安装通过：session90351退出0，全新tmp/v2_wheel_install_final不继承系统site-packages；pip check输出No broken requirements found。清除PYTHONPATH后导入来自该环境Lib/site-packages，direct_url记录wheel SHA256为6402ac8d6b08bdffa36bebfb52f33a9a2f0e0fd301ae8985697fe7f06ba400a9，与候选包一致，证据v2_05_final_wheel_install.log及v2_05_final_wheel_installed.json。尚需实际启动、最终串行回归及最终提交CI，不提前关闭V2-05。三叶扇原任务仍generation_in_progress且无last_error，未重启。使用Skills：five-axis-slicer-validation、five-axis-workbench-development。


2026-09-27 V2-05最终候选wheel实际短流程完成：独立环境真实启动窗口787998（session76309、端口8766；原三叶扇窗口53152702端口8765继续运行）。打开tutorial_rotary_limits_reference，实际生成得到acceleration_limit_exceeded且导出禁用；角速度改0.1rad/s、空移300mm/min并应用、再生成恢复Warning和导出。真实导出tutorial_rotary_wheel_export六文件，manifest严格回读75/75点通过，坐标/挤出/进给/顺序差异均空。真实保存tutorial_rotary_wheel_saved并重开，参数恢复，界面Stale及导出禁用符合输入恢复合同。截图v2_05_final_wheel_started.png、v2_04_rotary_acceleration_error_raw.png、recovered_raw.png、reopened_raw.png（后三者均v2_04_rotary前缀），生成状态v2_05_wheel_rotary_generated_state.json。错误/恢复/重开图交教程Agent替换，尚不预填替换数。该独立参考机型仅教学离线验证，不修改真实公共机型，也不证明上机资格。V2-05仍待最终回归及提交CI；Skills：开发、验证、computer-use。


2026-09-27 V2-04教程补拍继续：独立wheel窗口实际选择圆柱平端面并点击应用，显示rotary.surface_reference_invalid且生成/导出禁用，截图v2_04_rotary_flat_face_rejected_raw.png；仅证明平端面拒绝，不称本轮已测试叶片拒绝。Curve实际点击两条相邻边及顶面，截图v2_04_curve_edges_normal_face_raw.png；采用后v2_04_curve_edges_adopted_raw.png为未应用草稿，边序0008/0012且默认反向0/0，教程需明确方向仍需核对，不称路径已生成。两组交教程Agent更新；此前累计25旧图55引用，新增替换尚待完成。三叶扇原进程2448本轮只读确认Responding=true、CPU3537.30s、generation_in_progress=true、last_error=null，继续原计算。Skill实际调用：computer-use；沿用开发与验证流程。目标保持active。

2026-09-27 V2-04最后场景已真实生成：先完成IMG003/033替换，累计27图59引用、218本地链接有效。独立wheel GUI新建Rotary Around Part，实际点选侧面face0001与轴向边edge0002并采用，输入350:20;120:210、CCW，应用由CAD解析R20/H20后生成WARNING、导出可用。保留默认轴步2mm、采样5°、进给900/空移1800mm/min、角速度0.5rad/s，并未使用建议草案的缩小参数；本例仅离线教程。隐藏模型并放大，真实截图v2_04_rotary_around_two_regions_raw.png同时显示两分离蓝色区域与跨零输入；状态v2_04_rotary_around_generated_state.json确认crosses_zero分别true/false。无空移显示，不称截图显示旅行连接。交Agent替换最后IMG025/035并最终核链，完成前不关闭V2-04。三叶扇原进程2448仍Responding=true、CPU3998.97s、生成中无last_error，未重启。使用Skills：computer-use，沿用开发/验证流程。

2026-09-27发行收口核对：教程累计29原图/66引用已替换、48唯一原图均有处置；主线程运行audit_guide_images.py退出0，当前84图片引用missing0，23低对比度仅人工候选，不自动判失败。教程Agent正迁移6张已无指南引用的旧过程标记图并完成最终说明，尚不提前关闭V2-04。独立wheel窗口已实际点击关闭，session76309退出0；三叶扇原窗口继续，v2_02_three_color_stack_followup.txt显示从freeform_product.py:285空移规划推进到:320空移安全检查，当前生成中无last_error，不重启。提交候选v2_05_commit_candidates.json列249项及排除项，尚未暂存/提交；git ls-remote核实远端master仍edacd49。gh未登录但已有GitHub连接工具可核对CI，不因此提前判阻塞。全仓回归待运行中GUI验收完成后串行执行，避免QSettings相互影响。使用Skills：five-axis-slicer-validation、five-axis-workbench-development、computer-use。

2026-09-27 V2-04关闭：主线程复核v2_04_final_closure.md与final_disposition.json，原始83引用及15低对比候选均有最终处置；29原图66引用替换、16编号图+3普通链接图按用途保留，48唯一原图覆盖完整。6张退役过程标记图迁移后逐项SHA一致且旧assets路径不存在，8份过程JSON迁移有清单。218本地链接有效，84内嵌图missing0。两处非关键光晕按计划§8保留并明确记录，不称绝无光晕；英文复用中文图有说明。主表PRODUCT-01/V2C同步当前状态，V2-01/03/04完成、V2-02/05未关闭。使用Skills：five-axis-workbench-development阶段门槛、five-axis-slicer-validation；证据不替代实机验收。

2026-09-27 V2-02三叶扇多色生成完成：原进程2448生成结束、last_error=null，真实GUI显示路径、Warning及可用导出。v2_02_three_color_completed_state.json确认offline_exportable=true、machine_executable=false，strict readback340193/340193点、62716/62716事件、issues为空。实际点击导出到three_color_current150_gui_export，六文件已落盘（main.gcode59135880、toolpath.json330029556、preview.json236696908、manifest.json1522272、machine_axes.csv38330179、warnings.json1418956字节）；generated截图已保存，磁盘独立摘要及哈希由Agent核对。尝试Ctrl+S时工具报告用户正在操作，刷新确认用户在放大查看，故未继续抢输入；当前保存重开及NC空移/工序可视核验待做，不预报V2-02关闭。使用Skills：computer-use、开发与验证。目标active。

2026-09-27 Skill 调用记录：V2.7 发布使用 five-axis-workbench-development 与 five-axis-slicer-validation，统一界面/命令行/包回退版本标识，复用刚完成的离线验收，执行发行质量核查；发布说明见 ../reviews/2026-09-27_v2_7_release.md。
