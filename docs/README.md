# 项目文档索引

## 六个工作台算法开发

- [开发进度台账](planning/progress_tracker.md)：任务主表；每轮更新依赖、状态、验收证据、下一步和日期。
- [开发计划](planning/development_plan.md)：管状优先，六个工作台、20 种操作、当前 UI 接入、算法接口和完成条件。
- [参考资料检索](planning/reference_research.md)：NX 官方资料、公开参考项目、研究论文与当前源码依据。
- [本次计划编制复盘](reviews/2026-09-10_six_workbench_plan_review.md)：范围判断、用户决策、验证和局限。
- [B01–B03 基础能力验收](reviews/2026-09-11_b01_b03_acceptance_review.md)：当前回归、pipe2 流程、环境限制及可核对证据。

以上计划采用 2026-09-10 用户确定的“管状优先”和“自用、暂无开源计划”。旧目标中的开发顺序与定位在本阶段按最新决定执行，原始资料保留。

## 当前软件与使用说明

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
