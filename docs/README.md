# 项目文档索引

## 六个工作台算法开发

- [FAN15 修复执行计划](planning/fan15_repair_execution.md)：公共层域、四例逐项修复、选边操作测试与完整程序验收；继续工作时回读。

- [FAN15 四示例切片与旧程序对照](reviews/2026-09-20_fan15_example_acceptance.md)：弯管、球形校徽、三叶扇、叶轮逐例生成和失败记录，完整诊断图及未通过验收的原因。

- [扇叶完整五轴程序详细计划](planning/fan_complete_program_plan.md)：全高填充底座、90°换姿、三片叶片完整填充、总后处理，含独立验证和12项电脑点击验收。
- [扇叶完整程序借鉴项目调研](planning/fan_complete_program_research.md)：六个仓库固定版本、许可、已读内容、适用任务和未验证项。
- [FAN00—FAN15开发台账](planning/progress_tracker.md#主表)：FAN04/FAN07 原验收撤回，正在纠正径向曲层及叶根承接。
- [扇叶径向曲层纠正复盘](reviews/2026-09-20_fan_radial_correction.md)：旧 NC 模态证据、柱面起印、原工艺误判和修正边界。
- [扇叶完整程序规划复盘](reviews/2026-09-20_fan_complete_program_planning_review.md)：证据纠正、路线取舍和SIM接口关系。
- [五轴运动仿真专项调研](planning/motion_simulation_research.md)：Vismach、FreeCAD、CAMotics、PyBullet、VTK和FFmpeg的可复用设计、许可证与取舍。
- [五轴运动仿真与视频导出开发计划](planning/motion_simulation_plan.md)：机床场景、真实轴时间、分段倍速、确定性逐帧和视频导出架构。
- [五轴运动仿真开发台账](planning/motion_simulation_tracker.md)：SIM00—SIM10的依赖、状态、完成判据和下一步。
- [五轴运动仿真规划复盘](reviews/2026-09-20_motion_simulation_planning_review.md)：现有基础、技术选择、未验证项和本轮边界。
- [示例模型 PLA 五轴代码生成复盘](reviews/2026-09-20_example_pla_gcode_generation_review.md)：六类示例的工作台选择、论文参数、四份新代码的严格回读结果，以及三叶扇和 STL pipe 的当前阻塞边界。
- [CI 依赖修复与分支统一复盘](reviews/2026-09-13_ci_branch_consolidation_review.md)：默认 `master` 主线、Actions 隔离环境、依赖漂移原因和本轮验证边界。
- [论文核心 AC 范围与开源复用研究](planning/paper_core_ac_scope.md)：当前优先路线、四例覆盖缺口、论文批判性核对、固定版本及许可边界；状态统一见台账PC00—PC07。
- [论文核心范围调整复盘](reviews/2026-09-13_paper_core_ac_planning_review.md)：资源取舍、证据限制和本轮实际Skill使用。
- [PC01 输入、材料与控制器契约](planning/paper_core_input_contract.md)：单位、frame、G90/M83/G94、两种 Z20、T0—T3、容差、输入指纹和失败矩阵。
- [PC01—PC07 实施与验收复盘](reviews/2026-09-13_paper_core_ac_implementation_review.md)：受限 Freeform、多材料、自有 AC、Tube 收口、五个产品、测试/构建/封装及实机边界。
- [PC01—PC07 机器可读证据](reviews/evidence/2026-09-13_paper_core_ac/validation_manifest.json)：五个产品六件套、四个可重开项目、失败案例、双语多尺寸 UI 和逐文件 SHA-256。

- [AUD-02 缺陷修复、真实模型与 Skill 更新](reviews/2026-09-12_algorithm_audit_fixes.md)：含2026-09-13 Tube再检查、末层材料/固定喷嘴姿态修复、IPW加速与pipe2当前六件套；更正旧轴限解释。

- [当前完成情况与算法独立审查（AUD-01）](reviews/2026-09-12_project_algorithm_audit.md)：真实模型、坐标/道宽/截层/回读/空移反例及本轮验证边界。
- [算法审查后的修改方案](planning/2026-09-12_algorithm_audit_fix_plan.md)：六步修复顺序、具体改动范围和验收矩阵；已实施，结果见下方 AUD-02。

- [开发进度台账](planning/progress_tracker.md)：任务主表；每轮更新依赖、状态、验收证据、下一步和日期。
- [开发计划](planning/development_plan.md)：论文核心AC优先，保留长期六工作台20操作目录及原阶段完成条件。
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
- [扇叶完整程序计划](planning/fan_complete_program_plan.md)：FAN00—FAN15 的依赖、参数、验证和电脑点击验收路线。
- [扇叶 FAN01—FAN05 实施复盘](reviews/2026-09-20_fan_complete_program_fan01_fan05_review.md)：制造契约、独立旧NC基线、作业DAG、A=90°真实层域和公共内部填充的实现与限制。
- [扇叶 FAN01—FAN05 证据清单](reviews/evidence/2026-09-20_fan_complete_program/validation_manifest.json)：真实输入、机器可读契约、层域数据、JUnit、质量门禁和SHA-256。
- [Planar P01—P06 历史阶段交接](planning/planar_handoff.md)：P07 加入前的四操作真实 STEP、六件套、回读和 UI 证据；当前状态以 P01—P07 最终证据和进度台账为准。
- [多对话工作台开发启动提示词](planning/workbench_multi_chat_prompts.md)：P07、Curve、Rotary、Freeform、Research 与最终集成的可复制任务提示词及统一完成条件。
- [多对话工作台提示词编制复盘](reviews/2026-09-12_multi_chat_workbench_prompt_review.md)：依赖、工作树、多 Agent、完整验收和 Planar Support 计数边界。

以上计划采用 2026-09-10 用户确定的“管状优先”和“自用、暂无开源计划”。旧目标中的开发顺序与定位在本阶段按最新决定执行，原始资料保留。

## 当前软件与使用说明

- [5AxisSclicer V2.0 学习手册](guides/user_learning_manual_zh.md)：从 IDE/PowerShell 启动、界面、Setup、工作台选择到生成、错误恢复、回读、六件套和独立迁移的主课程；随附案例只作为练习。
- [学习与参考手册中心](guides/README.md)：学习路线、工作台课程、参考手册、教程编写矩阵和图片要求。
- [DOC-01 学习手册重组复盘](reviews/2026-09-13_user_learning_manual_reorganization.md)：课程结构、图片依据、启动入口检查、Computer Use 限制和文档验收结果。
- [Tube 工作台完整图文手册](guides/tube_workbench_zh.md)：三种操作、生成、检查、预览、导出及错误处理。
- [Planar 工作台图文手册](guides/planar_workbench_zh.md)：Region、Zigzag、Offset、Thin Wall、Spiral 与 buildplate-only Planar Support 的离线生成链与恢复说明。
- [Curve 工作台图文手册](guides/curve_workbench_zh.md)：Buildup、Multi-pass Buildup 与 Offset Buildup 的完整离线工作流。
- [Rotary 工作台图文手册](guides/rotary_workbench_zh.md)：Spiral、Thin Wall 与 Around Part 的完整离线工作流。
- [Freeform 工作台图文手册](guides/freeform_workbench_zh.md)：受限面组、多导引线、曲面贴合/薄壁、三入口、六件套和错误恢复。
- [多材料通道指南](guides/material_channels_zh.md)：显式材料区域、T0—T3 事件链、温控/传感器门禁和统计口径。
- [自有 AC 离线控制器指南](guides/paper_core_ac_controller_zh.md)：模式、Z20、宏展开、累计 C、严格回读和实机资格缺口。
- [扇叶完整程序 FAN06—FAN07 复盘](reviews/2026-09-20_fan_complete_program_fan06_fan07_review.md)：全高底座与支撑、A=90° 单叶片完整填充、真实路径图和当前材料量偏差。
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
