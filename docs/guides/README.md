# 使用手册索引与编写要求

本目录集中保存面向软件使用者的操作手册。开发计划、算法依据和验收复盘仍放在 `docs/planning/` 与 `docs/reviews/`；使用手册只说明用户在界面中怎样完成任务、怎样判断结果和怎样处理错误。

## 当前可用手册

| 模块 | 手册 | 当前状态 |
| --- | --- | --- |
| 机型配置 | [机型选择、旋转轴输出字与自定义](machine_profiles_zh.md) | A/B/C 内部轴到固件轴字的映射、用户配置另存、JSON 导入导出及快照重开 |
| Tube 坐标与装夹 | [管状坐标设置](tube_coordinate_setup_zh.md) | 已有图文步骤 |
| Tube 设置脚本与 YAML | [设置脚本与 YAML](tube_setup_script_console_zh.md) | 已有命令说明，界面截图仍需随控制台改版补拍 |
| Tube 三种操作 | [Tube 工作台完整手册](tube_workbench_zh.md) | 覆盖 Indexed、Buildup、Continuous 及生成和导出 |
| Planar 路径与支撑操作 | [Planar 工作台手册](planar_workbench_zh.md) | 覆盖 Region、Zigzag、Offset、Thin Wall、Spiral、Planar Support（P07）、真实 STEP、离线检查、导出和错误恢复；真人桌面点击仍未验证 |
| Curve 曲线沉积 | [Curve 工作台手册](curve_workbench_zh.md) | 覆盖有向边链、法向、Buildup、Multi-pass、Offset、真实 STEP、六件套、脚本/HTTP 和错误恢复 |
| Rotary 回转沉积 | [Rotary 工作台手册](rotary_workbench_zh.md) | 覆盖回转坐标、Spiral、Thin Wall、Around Part、跨周期、G93 回读、六件套和错误恢复 |
| 受限 Freeform | [Freeform 工作台手册](freeform_workbench_zh.md) | 论文核心有限面组、多导引线、曲面贴合/薄壁、离线导出和失败恢复 |
| 多材料通道 | [预定义材料区域与 T0—T3](material_channels_zh.md) | 显式区域分配、切换/剪切/回抽/park/上料/温控/清洗/恢复事件链 |
| 自有 AC 控制器 | [论文核心 AC 离线封装](paper_core_ac_controller_zh.md) | G90/M83/G94、两种 Z20 动作、宏展开、严格回读与 `machine_executable=false` 边界 |
| Rotary/Tube/Freeform 选择辅助 | [pipe2 与扇叶模型、手工 G-code 可视化对比](../reviews/2026-09-13_pipe2_model_manual_gcode_comparison.md) | 对比连续弯管、三叶自由曲面、选面结果和手工 XYZAC，说明各工作台的支持边界 |
| G-code 与成果预览 | [G-code 可视化手册](gcode_preview_zh.md) | 覆盖普通 Preview、成果页和五轴坐标回读边界 |

Planar P01—P07、Curve C01—C05、Rotary R01—R05、Tube T01—T12 与 PC00—PC07 论文核心 AC 离线版已完成。PC02 只关闭论文所需的受限 Freeform 子集，不自动关闭通用 F01—F06 父阶段；Research 仍未完成。

## 每个模块的交付门槛

每个工作台及跨工作台公共模块完成时，手册至少包含以下内容：

1. 适用范围、前置条件、可复现示例和当前限制。
2. 从入口到结果的完整操作顺序，按钮和页签名称与当前中英文 UI 一致。
3. 参数表，写明单位、默认值、作用、有效范围和修改后是否使结果过期。
4. 输入角色、生成、检查、预览、导出、保存与重开的实际行为。
5. 至少一条正常流程和一条典型失败或恢复流程。
6. 输出文件的用途和判断成功的方法，避免只写“已生成”。
7. 真实界面图片。关键流程至少应有界面总览、主要参数、生成结果和错误定位四类图；复杂选择或坐标操作应增加局部图。

## 图片与内容规则

- 图片优先使用当前版本真实运行截图，保存到 `docs/guides/assets/<module>/`，或引用具有固定日期和清单的 `docs/reviews/evidence/` 证据。
- 截图要显示足够上下文，正文紧邻图片说明用户应查看的位置和状态。含测试故障的画面必须标成错误示例。
- 涉及路径、模型或加工结果时，至少提供一个三维视图；仅有表单截图不算图文完整。
- 密钥、用户名、外部绝对路径和设备敏感参数应遮蔽。图片不能替代数值、单位和安全边界说明。
- UI、参数语义或输出结构变更时，同一任务内更新手册文字并重拍受影响图片。旧图仍有审计价值时留在 `docs/reviews/evidence/`，不继续作为当前操作图。
- 参考机型的离线通过不能写成真实机床验证。需要实测、标定或现场资格的步骤单独标明。

## 后续模块手册清单

| 阶段 | 计划手册 | 最少配图 |
| --- | --- | --- |
| Planar | Region、Zigzag、Offset、Thin Wall、Spiral、Planar Support | 区域/孔岛、五种制造操作、主体/interface、路径检查、失败与恢复 |
| Curve | 边链与法向、Buildup、Multi-pass、Offset | 边链顺序、法向、三类结果、自交或断链错误 |
| Freeform | 曲面区域、Coating、Thin Wall、Buildup | UV/边界、投影结果、姿态、接缝与多解错误 |
| Research | 四种研究操作及可复现实例 | 数据来源、基线、结果图、失败或负结果 |
| 整体交付 | 安装、项目管理、资源库、自动化和故障排查 | 首次启动、保存重开、资源冲突、API 状态 |
