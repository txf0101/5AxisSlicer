# 项目文档索引

## 六个工作台算法开发

- [AUD-02 缺陷修复、真实模型与 Skill 更新](reviews/2026-09-12_algorithm_audit_fixes.md)：最终合格输出、拒绝案例、回归及后续开发方法。

- [当前完成情况与算法独立审查（AUD-01）](reviews/2026-09-12_project_algorithm_audit.md)：真实模型、坐标/道宽/截层/回读/空移反例及本轮验证边界。
- [算法审查后的修改方案](planning/2026-09-12_algorithm_audit_fix_plan.md)：六步修复顺序、具体改动范围和验收矩阵；已实施，结果见下方 AUD-02。

- [开发进度台账](planning/progress_tracker.md)：任务主表；每轮更新依赖、状态、验收证据、下一步和日期。
- [开发计划](planning/development_plan.md)：管状优先，六个工作台、20 种操作、当前 UI 接入、算法接口和完成条件。
- [参考资料检索](planning/reference_research.md)：NX 官方资料、公开参考项目、研究论文与当前源码依据。
- [A01-A03 管状算法基线、样例与 Toolpath 契约](planning/tube_algorithm_contract.md)：环境、支持范围、样例真值、生成路径和结果清单契约。
- [A02 样例来源登记](planning/example_source_inventory.md)：当前示例文件的来源状态、哈希和后续真值计划。
- [本次计划编制复盘](reviews/2026-09-10_six_workbench_plan_review.md)：范围判断、用户决策、验证和局限。
- [B01–B03 基础能力验收](reviews/2026-09-11_b01_b03_acceptance_review.md)：当前回归、pipe2 流程、环境限制及可核对证据。
- [分阶段模型与 token 预算复盘](reviews/2026-09-11_model_token_budget_review.md)：44 项待办的模型分工、悲观上限、风险储备与节省规则。
- [A01-A03 契约实施复盘](reviews/2026-09-11_a01_a03_contract_review.md)：本轮契约、外部资料处理、验证和局限。
- [A01-A03 正式验收证据](reviews/evidence/2026-09-11_a01_a03/manifest.json)：源码、输入和 JUnit 指纹及本轮门禁摘要。
- [T01—T07 Tube Indexed 实施审查](reviews/2026-09-11_t01_t07_indexed_tube_review.md)：实现范围、参考来源、本轮验证结果及 T08、真实机床边界。
- [T01—T07 正式验收证据](reviews/evidence/2026-09-11_t01_t07/manifest.json)：当前源码、pipe2、解析夹具、JUnit 和质量门禁指纹。
- [T01—T07 UI 审查](reviews/2026-09-11_t01_t07_ui_audit.md)：三种窗口尺寸的中英截图、修复项和最终 UI 回归边界。
- [T08—T12 Tube Workbench 阶段审查](reviews/2026-09-11_t08_t12_tube_workbench_review.md)：三种 Tube 操作、生成/回读、来源边界、质量门禁、UI 证据和未验证的真实机床限制。
- [T08—T12 正式验收证据](reviews/evidence/2026-09-11_t08_t12/manifest.json)：JUnit、首次 targeted 失败与串行通过、三尺寸 UI、pipe2 六件套及 SHA-256。
- [T08—T12 来源与实现边界](planning/reference_research.md#8-t08t12-新实现的可核对来源边界)：RMF、G-code 语义、时间参数化、FCL/OCCT 参考及 Generic XYZAC 离线资格边界。
- [图文使用手册体系复盘](reviews/2026-09-11_user_manual_framework_review.md)：手册范围、图片依据、检查结果和待补成功流程。
- [工作台开发复用 Skill 建立复盘](reviews/2026-09-11_workbench_development_skill_review.md)：Tube 经验提炼、Skill 结构、调用登记方式、校验和文件指纹。
- [P01—P06 平面算法与工作台复盘](reviews/2026-09-12_planar_algorithm_foundation_review.md)：区域、填充、偏置、薄壁、螺旋、产品接入与阶段验收；P07 使用说明见下方手册。
- [Planar 工作台图文手册](guides/planar_workbench_zh.md)：P01—P07 的五操作参数、正常流程、错误恢复、导出、保存重开、截图与能力边界。
- [P07 Planar Grid/Lines 支撑实施复盘](reviews/2026-09-12_p07_planar_support_review.md)：clean-room 来源边界、支撑领域链、代码审查修复、解析真值、UI、测试、质量门禁和实机限制。
- [P07 与 Planar P01—P07 当前验收证据](reviews/evidence/2026-09-12_p07_planar_final/manifest.json)：最终源码、独立真值、真实 STEP、六件套、UI、JUnit、质量门禁及逐文件 SHA-256。
- [Curve C01—C05 工作台图文手册](guides/curve_workbench_zh.md)：有向边链、明确法向、三种 Curve 操作、状态、六件套、脚本/HTTP 和错误恢复。
- [Curve C01—C05 实施与验收复盘](reviews/2026-09-12_curve_workbench_review.md)：独立真值、真实 STEP、产品链接入、失败修复、UI 和离线能力边界。
- [Curve C01—C05 当前验收证据](reviews/evidence/2026-09-12_curve_workbench_final/validation_manifest.json)：真实叶轮三操作、六件套、Qt/OpenGL 截图、JUnit、质量/构建/native 门禁、失败历史和逐文件 SHA-256。
- [Rotary R01—R05 工作台图文手册](guides/rotary_workbench_zh.md)：回转坐标、圆柱/圆锥 Spiral、Thin Wall、Around Part、状态、六件套与错误恢复。
- [Rotary R01—R05 实施与验收复盘](reviews/2026-09-13_rotary_workbench_review.md)：Open5x/NX 资料边界、独立真值、周期/运动语义、产品链、UI 和离线资格限制。
- [Rotary R01—R05 当前验收证据](reviews/evidence/2026-09-13_rotary_workbench_final/validation_manifest.json)：真实 STEP、四组六件套、G93 回读、Qt 多尺寸截图、JUnit、质量与包检查及逐文件 SHA-256。
- [跨工作台旋转轴 G-code 输出字实施复盘](reviews/2026-09-13_custom_rotary_axis_words_review.md)：内部物理轴与控制器地址分离、危险字拒绝、共享发布、回读和实机边界。
- [pipe2 与扇叶模型、手工 G-code 可视化对比](reviews/2026-09-13_pipe2_model_manual_gcode_comparison.md)：连续弯管、三叶自由曲面、选面契约、XYZAC 策略、180° 坐标注册及 Rotary/Tube/Freeform 适用性判断。
- [Planar P01—P06 历史阶段交接](planning/planar_handoff.md)：P07 加入前的四操作真实 STEP、六件套、回读和 UI 证据；当前状态以 P01—P07 最终证据和进度台账为准。
- [多对话工作台开发启动提示词](planning/workbench_multi_chat_prompts.md)：P07、Curve、Rotary、Freeform、Research 与最终集成的可复制任务提示词及统一完成条件。
- [多对话工作台提示词编制复盘](reviews/2026-09-12_multi_chat_workbench_prompt_review.md)：依赖、工作树、多 Agent、完整验收和 Planar Support 计数边界。

以上计划采用 2026-09-10 用户确定的“管状优先”和“自用、暂无开源计划”。旧目标中的开发顺序与定位在本阶段按最新决定执行，原始资料保留。

## 当前软件与使用说明

- [图文使用手册索引与交付要求](guides/README.md)：当前手册入口、图片要求和后续各工作台的手册门槛。
- [Tube 工作台完整图文手册](guides/tube_workbench_zh.md)：三种操作、生成、检查、预览、导出及错误处理。
- [Planar 工作台图文手册](guides/planar_workbench_zh.md)：Region、Zigzag、Offset、Thin Wall、Spiral 与 buildplate-only Planar Support 的离线生成链与恢复说明。
- [Curve 工作台图文手册](guides/curve_workbench_zh.md)：Buildup、Multi-pass Buildup 与 Offset Buildup 的完整离线工作流。
- [Rotary 工作台图文手册](guides/rotary_workbench_zh.md)：Spiral、Thin Wall 与 Around Part 的完整离线工作流。
- [机型选择与旋转轴输出字指南](guides/machine_profiles_zh.md)：把内部 A/B/C 映射到固件轴字，并说明保存、重开、Stale 与安全限制。
- [pipe2 与扇叶回转特征对比报告](reviews/2026-09-13_pipe2_model_manual_gcode_comparison.md)：用当前 STEP 与手工 G-code 说明固定轴 Rotary、中心线随动 Tube 和自由曲面多轴路径的差异。
- [G-code 可视化图文手册](guides/gcode_preview_zh.md)：普通 Preview、成果页、分色、层范围与五轴回读边界。
- [根目录 README](../README.md)：启动、当前能力、自动化接口和验证入口。
- [项目结构](project_structure.md)：现有模块及职责；该文档有自身的核查日期。
- [管状坐标设置图文指南](guides/tube_coordinate_setup_zh.md)。
- [设置脚本与 YAML 指南](guides/tube_setup_script_console_zh.md)。
- [YAML 格式定义](formats/manufacturing-setup-yaml.md)。
- [pipe2 坐标示例](../example/pipe2/tube_setup_coordinate_demo/README.md)。
- [原开发目标文档](../圭臬/开发目标文档.docx)：历史目标与示意图，阅读时结合最新计划和实现状态。

## 历史规划与阶段复盘

项目既有复盘继续集中在 `docs/reviews/`，不迁移或重命名原文件。

- [管状切片流程与首版范围](reviews/2026-07-22_tube_slicing_user_workflow_review.md)。
- [Tube Setup 和坐标实施](reviews/2026-07-24_tube_setup_coordinate_implementation_review.md)。
- [工程质量重构](reviews/2026-07-24_engineering_quality_refactor_review.md)。
- [鼠标导航和坐标入口](reviews/2026-07-27_bambu_navigation_and_tube_coordinate_entry_review.md)。
- [视图与字段帮助](reviews/2026-07-27_view_rotation_and_tube_field_help_review.md)。
- [脚本控制台与开放配置](reviews/2026-07-31_tube_script_console_review.md)。

后续算法任务使用台账编号关联代码、样例和复盘。同一任务更新同一份记录；其余既有评审仍可从 `docs/reviews/` 文件名按日期查找。

## 自有打印机参考资料

- [自有 AC 五轴打印机参数依据](planning/own_ac_printer_parameters.md)：论文设备规格、材料工艺、选取依据及待标定项。
- [参数归档复盘](reviews/2026-09-12_own_ac_printer_parameters_review.md)：来源核验、复用方式与边界。

- [机型选择与自定义配置](guides/machine_profiles_zh.md)：默认自有 AC、用户库与 JSON 文件交换。
- [I01-OWN 默认机型实施复盘](reviews/2026-09-12_own_printer_profile_review.md)。
