# 5AxisSclicer V2.0 学习与参考手册中心

English readers: start with the [click-through guide](quickstart_clickthrough_en.md), then use the [learning manual](user_learning_manual_en.md) and topic guides below. The Chinese guides remain available in the Chinese index.

这里是软件使用者的统一入口。按顺序使用：[五工作台图文点击教程](quickstart_clickthrough_zh.md)完成一次操作 → [学习总册](user_learning_manual_zh.md)理解判断与错误恢复 → 下方的工作台专项与参数参考。

快速操作可从[点击教程](quickstart_clickthrough_zh.md)开始，系统学习再读[《5AxisSclicer V2.0 学习手册》](user_learning_manual_zh.md)。pipe2、平面件、叶轮、扇叶和半球是练手材料；模型 ID、参数、点数和轴范围都不应复制到自己的零件。

机床、喷嘴、材料和坐标可设为所有工作台共用，也可复制成某个工作台的独立设置。入口、保存范围及旧路径何时需要重新生成，见[公共设置与本工作台设置](quickstart_clickthrough_zh.md#公共设置与本工作台设置)。

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
| 有限修剪面组和明确导引线 | [Freeform 工作台](freeform_workbench_zh.md) | 曲面贴合、薄壁、有限多道/多层，导引模式最多 16 面、32 条导引线；实体模式的几何选择见下方说明 |
| 已有 NC 的查看和诊断 | [G-code 预览](gcode_preview_zh.md) | 模型叠加、层/角色筛选、代码定位和安全回退 |

Research 入口不可用，请选择上表中的工作台。

## 公共参考手册

| 主题 | 手册 | 使用时机 |
| --- | --- | --- |
| 对象、坐标和装夹 | [Tube 坐标设置](tube_coordinate_setup_zh.md) | L02—L03；其中 Setup 方法供各制造工作台复用 |
| 实体生长模式选择 | [实体生长模式选择与检查](solid_fill_method_zh.md) · [English](solid_fill_method_en.md) | 比较管体、球面、一般曲面和径向叶片的几何要求与拒绝条件 |
| 机型和旋转轴字 | [机型选择、旋转轴输出字与自定义](machine_profiles_zh.md) | 选择参考/自有机型、保存用户配置或核对 A/B/C 映射 |
| 多材料 | [预定义材料区域与 T0—T3](material_channels_zh.md) · [English](material_channels_en.md) | Freeform 或多通道产品需要显式区域和材料事件时 |
| 自有 AC 后处理 | [论文核心 AC 离线封装](paper_core_ac_controller_zh.md) | 核对 G90/M83/G94、换料站移动、事件回读和累计 C 时 |
| 脚本与 YAML | [Tube 设置脚本与 YAML](tube_setup_script_console_zh.md) | GUI 基础掌握后，再学习事务和自动化入口 |

## 使用范围

本手册指导生成、检查、回读、导出和保存重开。软件仍在测试和持续完善中；示例参数与打印效果以用户设备的实际调试结果为准。自有 AC 输出中的 `machine_executable=false` 表示尚未完成针对具体设备的自动核验。上机调试前请核对控制器与宏、轴和装夹参数、路径安全；操作报告 Error 或输入已变为 Stale 时不要导出，Warning 应逐项核对。

## English guides

Start with the [five-Workbench click-through guide](quickstart_clickthrough_en.md), then use the [learning manual](user_learning_manual_en.md) to choose and review a workflow.

| Topic | English guide | Chinese guide |
| --- | --- | --- |
| First operation across Workbenches | [Click-through guide](quickstart_clickthrough_en.md) | [五工作台点击教程](quickstart_clickthrough_zh.md) |
| Learning route and migration | [Learning manual](user_learning_manual_en.md) | [学习手册](user_learning_manual_zh.md) |
| Planar sections, paths, and support | [Planar Workbench](planar_workbench_en.md) | [Planar 工作台](planar_workbench_zh.md) |
| Ordered edge-chain deposition | [Curve Workbench](curve_workbench_en.md) | [Curve 工作台](curve_workbench_zh.md) |
| Fixed-axis rotary deposition | [Rotary Workbench](rotary_workbench_en.md) | [Rotary 工作台](rotary_workbench_zh.md) |
| Tube operations | [Tube Workbench](tube_workbench_en.md) | [Tube 工作台](tube_workbench_zh.md) |
| Coordinates and placement | [Tube Setup](tube_coordinate_setup_en.md) | [坐标与装夹](tube_coordinate_setup_zh.md) |
| Finite Freeform guide and solid modes | [Freeform Workbench](freeform_workbench_en.md) | [Freeform 工作台](freeform_workbench_zh.md) |
| Solid-growth method selection | [Solid-growth method guide](solid_fill_method_en.md) | [实体生长模式选择与检查](solid_fill_method_zh.md) |
| Existing NC/G-code inspection | [G-code preview](gcode_preview_en.md) | [G-code 预览](gcode_preview_zh.md) |
| Machine profile and axis mapping | [Machine profiles](machine_profiles_en.md) | [机型选择与自定义](machine_profiles_zh.md) |
| Multicolour materials and tool-change station | [Material channels](material_channels_en.md) | [材料通道](material_channels_zh.md) |
| Own AC offline postprocessor | [Offline postprocessor](paper_core_ac_controller_en.md) | [自有 AC 后处理](paper_core_ac_controller_zh.md) |
| Restricted Setup script console | [Setup script console](tube_setup_script_console_en.md) | [设置脚本控制台](tube_setup_script_console_zh.md) |

These guides describe offline inspection and export. Example parameters are not universal machine settings. Review warnings and strict readback; `machine_executable=false` means device-specific automated qualification is incomplete. Before machine use, verify the controller and macros, axes, fixture, path safety, and trial results on the target equipment.
