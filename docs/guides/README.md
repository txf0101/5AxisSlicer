# 5AxisSclicer V2.0 学习与参考手册中心

这里是软件使用者的统一入口。教程按工业软件常见的三层结构组织：**学习总册**负责从零开始建立完整工作流，**工作台课程**负责不同几何和工艺的专项训练，**参考手册**用于查询参数、文件和高级入口。

初次使用请从[《5AxisSclicer V2.0 学习手册》](user_learning_manual_zh.md)开始，不要直接挑一个案例照抄。pipe2、平面件、叶轮、扇叶和半球是练手材料，目的是帮助理解可迁移的方法；模型 ID、参数、点数和轴范围都不应复制到自己的零件。

## 学习路线

| 阶段 | 建议课程 | 学习成果 | 进入下一阶段前的检查 |
| --- | --- | --- | --- |
| 入门 | L01 界面、L02 几何、L03 Setup | 能打开项目、理解对象角色并建立坐标和资源 | 能解释 Source/Model/Build/Machine，设置问题可定位 |
| 决策 | L04 工作台选择 | 能根据几何和制造意图选 Planar/Curve/Rotary/Tube/Freeform | 写出选择理由和拒绝条件 |
| 操作 | L05 参数、L06 状态与恢复 | 能创建操作、应用参数、生成并处理 Warning/Error/Stale | Error 阻止导出，参数变化触发 Stale |
| 专项 | W01—W05 任选一条工作台支线 | 掌握该类几何的选择、路径与失败边界 | 完成随附材料练习和一个迁移练习 |
| 收口 | L07 检查回读、L08 六件套、L09 独立迁移 | 能交叉检查路径、运动和代码，保存重开并迁移到新零件 | 六件套可解释，未知设备资格继续保留 |

完整课程目标、练习、自检和迁移检查单见[总册中的教程矩阵](user_learning_manual_zh.md#3-教程矩阵)。

## 工作台课程

| 几何/制造问题 | 课程 | 当前离线范围 |
| --- | --- | --- |
| 平行层面、截面、孔岛、平面支撑 | [Planar 工作台](planar_workbench_zh.md) | Region、Zigzag、Offset、Thin Wall、Spiral、buildplate-only Planar Support |
| 有向 edge 链上的沉积 | [Curve 工作台](curve_workbench_zh.md) | Buildup、Multi-pass Buildup、Offset Buildup |
| 固定轴圆柱/圆锥上的回转沉积 | [Rotary 工作台](rotary_workbench_zh.md) | Spiral、Thin Wall、Around Part、跨周期区间 |
| 单支恒定圆截面管体 | [Tube 工作台](tube_workbench_zh.md) | Indexed、Buildup、Continuous |
| 有限修剪面组和明确导引线 | [受限 Freeform 工作台](freeform_workbench_zh.md) | 曲面贴合、薄壁、有限多道/多层，最多 16 面、32 条导引线 |
| 已有 NC 的查看和诊断 | [G-code 预览](gcode_preview_zh.md) | 模型叠加、层/角色筛选、代码定位和安全回退 |

Research 工作台仍未完成，不提供操作教程。计划中的入口、名称或效果图不能写成当前可用能力。

## 公共参考手册

| 主题 | 手册 | 使用时机 |
| --- | --- | --- |
| 对象、坐标和装夹 | [Tube 坐标设置](tube_coordinate_setup_zh.md) | L02—L03；其中 Setup 方法供各制造工作台复用 |
| 机型和旋转轴字 | [机型选择、旋转轴输出字与自定义](machine_profiles_zh.md) | 选择参考/自有机型、保存用户配置或核对 A/B/C 映射 |
| 多材料 | [预定义材料区域与 T0—T3](material_channels_zh.md) | Freeform 或多通道产品需要显式区域和材料事件时 |
| 自有 AC 后处理 | [论文核心 AC 离线封装](paper_core_ac_controller_zh.md) | 核对 G90/M83/G94、两种 Z20、宏展开和累计 C 时 |
| 脚本与 YAML | [Tube 设置脚本与 YAML](tube_setup_script_console_zh.md) | GUI 基础掌握后，再学习事务和自动化入口 |
| 工作台辨别 | [pipe2 与扇叶模型、手工 G-code 可视化对比](../reviews/2026-09-13_pipe2_model_manual_gcode_comparison.md) | 难以区分 Rotary、Tube、Curve 和 Freeform 时 |

## 教程编写矩阵

新增或修订一节课程时，应同时覆盖下表。只有“案例步骤”一列有内容的文档不能进入学习主线。

| 教学层 | 必须回答的问题 | 最低证据 |
| --- | --- | --- |
| 学习目标 | 学完后使用者能够独立完成什么？ | 可观察的自检结果 |
| 通用概念 | 哪些规则可以迁移到其他零件？ | 当前 UI 名称、单位和领域契约 |
| 引导练习 | 随附案例用于练习哪个概念？ | 当前版本界面或三维结果图 |
| 判断方法 | 如何判断结果正确、警告可接受或必须停止？ | Ready/Warning/Error/Stale、问题列表和检查结果 |
| 错误恢复 | 怎样制造一个有意义的失败并恢复？ | 错误态和恢复态，不能只展示成功 |
| 迁移任务 | 换成自己的同类零件后，哪些内容必须重新选择或核定？ | 不复制 ID、坐标、参数、点数和轴范围的检查单 |
| 能力边界 | 哪些内容尚未得到软件、控制器或现场资格？ | `machine_executable`、机型和实机边界 |

## 图片与内容规则

- 图片优先使用当前版本真实运行截图，保存到 `docs/guides/assets/<module>/`，或引用具有日期和清单的 `docs/reviews/evidence/`。
- 正文紧邻图片说明观察目标。错误态、Stale 或参考机型 Warning 必须明确标注，不能当成成功画面。
- 涉及路径、模型或加工结果时至少提供一个三维视图；只有表单截图不能构成完整课程。
- 参数必须写单位、作用和变更影响。示例值标为练习值，不能暗示适用于所有零件。
- 案例用于练习后必须给迁移任务或替换规则。禁止把 body/face/edge ID、绝对坐标、点数或轴范围写成通用操作答案。
- 密钥、用户名、外部绝对路径和设备敏感参数应遮蔽。图片不能替代安全边界说明。
- UI、参数语义或输出结构变化时，同一任务更新正文和受影响图片。旧图有审计价值时留在 evidence，不继续作为当前操作图。
- QWidget grab、证据绘制器、生产 VTK/OpenGL、Computer Use 和真人现场操作是不同证据，图注要说明来源。

## 当前资格说明

Planar P01—P07、Curve C01—C05、Rotary R01—R05、Tube T01—T12 和 PC00—PC07 已完成受限离线验收。PC02 只关闭论文所需的 Freeform 子集；通用 F01—F06、Research 和完整第二机型仍未完成。

当前手册可以指导离线生成、检查、回读、导出和保存重开。真实控制器、宏版本、机床标定、生产环境完整碰撞和试切需要另行取得证据；自有 AC 输出保持 `machine_executable=false`。
