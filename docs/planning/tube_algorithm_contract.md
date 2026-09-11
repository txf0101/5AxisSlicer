# A01-A03 管状算法基线、样例与 Toolpath 契约

日期：2026-09-11。本文对应进度台账 `A01`—`A03` 和 `T01`—`T07`，作为 `T08` 及后续 Tube 工作的本地执行依据。A01—A03 定义首轮管状算法边界、样例来源、数据契约和验收入口；T01—T07 已实现受限的 Indexed 算法核心。

## A01 基线与学习边界

本轮只读预检使用 `tmp/pytest9/Scripts/python.exe`，Python 版本 3.12.7。预检脚本为 `C:/Users/Tang Xufeng/.codex/skills/five-axis-slicer-validation/scripts/preflight.py --repo F:/【项目和任务】/5AxisSclicer_V2.0`，结果显示项目依赖匹配，`ruff`、`mypy` 可用，QSettings 可写。该检查不运行 GUI、渲染或算法测试。

当前可复用基础为 B01-B03：STEP 拓扑、四级选择、Tube Setup、坐标闭环、命令事务、YAML、NC 预览和 Generic XYZAC 参考机型。它们不包含中心线识别、切层、路径生成、IK、碰撞、后处理输出和实机资格。

首轮 Tube Indexed 支持范围如下：

| 项 | 首轮采用 | 暂不采用 |
| --- | --- | --- |
| 管型 | 单支无分叉、恒定圆截面直管和圆弧管 | 分叉管、任意非圆截面、一般变径 |
| 输入角色 | 管体、入口、出口、既有基体、夹具或忽略体 | 把 Part 下所有 solid 自动当作待切管体 |
| 坐标 | Source CS 到 Model CS、Build CS、Mount 的现有链路 | 直接在 G-code 机床坐标里做几何算法 |
| 机型 | `builtin.machine.generic_xyzac_reference.v1` 离线参考 | 未标定的真实设备安全认证 |
| 容差起点 | 几何长度 0.01 mm；姿态往返 0.01 deg；哈希和单位必须显式 | 把这些起点写成制造精度保证 |

后续算法任务必须按问题再查外部资料。当前外部依据分三类使用：Siemens NX 公开资料用于工作流和多轴增材概念对照；公开项目用于学习数据流和边界处理；论文用于 RMF、场切片或运动学细节。许可证不清、非公开或只描述产品能力的资料不得直接转写成源码实现。

## A02 样例来源和独立真值

首例仍使用 `example/pipe2`。旧 G-code 只能作为工序观察和回读预览输入，不作为新算法逐点复制目标。

| 文件 | SHA-256 | 当前角色 | 来源状态 | 后续可比较指标 |
| --- | --- | --- | --- | --- |
| `example/pipe2/弯管新.stp` | `116e99fd43492bd1f4f519c80c93cd1f7cd0bf2cb6861b3e123148e4031a0d4b` | 首例 CAD；含管体和底座 | 已登记；原始建模来源未知 | solid 数、管体候选、端口、圆柱/环面面、独立测量尺寸 |
| `example/pipe2/弯管.gcode` | `4d6630c01f63d6f802ae6955752fa41b35abfea23509c661fcd855f7064ff70a` | 历史 NC 观察输入 | 用户说明存在外部切片和人工拼接 | A/C 范围、层/区段顺序、空移/沉积角色、回读可视化 |
| `example/pipe2/tube_setup_coordinate_demo/manufacturing-setup.yaml` | 本轮不改 | Setup/YAML 示例 | B02-B03 已回归 | T01 后验证管体角色和参数持久化 |

解析真值分两级建立。T01 只登记用户选择的管体、入口、出口和基体角色，并保存引用重绑定证据。T02 再从当前 STEP 重新测量管几何，历史“外半径 16 mm、内半径 15 mm、圆弧中心半径 35 mm、弯曲角约 70.513331 deg”只作为待核对线索。

独立夹具要求：

1. 解析直管：用已知半径、壁厚和长度的程序生成 STEP，真值来自生成参数。
2. 解析圆弧管：用已知中心半径、截面半径和弯曲角生成 STEP，真值来自中心线公式。
3. pipe2：从 STEP 拓扑测量后生成真值记录，不能反用 `弯管.gcode` 填几何尺寸。
4. 失败样例：双管体、缺入口、非圆端口、分叉或歧义面必须给出定位错误。

A02 已在 `tests/fixtures/analytic_tube_truth.json` 固定直管和 90° 圆弧管的参数、端点、切向、半径、中心线长度、公式及来源说明。T02 据此生成 STEP 实体并检查识别误差，不能用算法输出反写真值。

## A03 通用路径、事件和结果契约

新增代码入口为 `src/five_axis_slicer/manufacturing/toolpath.py`。契约版本为 `TOOLPATH_SCHEMA_VERSION = 1`。

`ToolpathPoint` 表达生成路径点，坐标系为 `workpiece_build`，长度单位 mm，角度单位 rad。字段包含位置、切向、喷嘴轴、可选表面法向、进给、道宽、层高、材料体积、operation/stage/layer/region 标识、`point_type`、`extrusion_role` 和问题引用。`deposition` 点必须有沉积角色；非沉积点不能携带材料体积。

`ToolpathEvent` 表达回抽、prime、dwell、安全转位、接近和离开等离散事件。事件不伪装成零长度线段，可带持续时间和结构化上下文。

`GeneratedToolpath` 聚合点和事件。它只到几何路径层，不包含机床轴。`GeneratedResultManifest` 聚合输入源哈希、参数语义哈希、算法版本、机型 ID、状态和导出资格。只有 `ready` 或 `warning` 且包含路径点的结果可导出。

`GeneratedToolpath.to_preview_segments()` 将相邻路径点转换为现有 `GCodePathSegment`，映射沉积/空移类型、层序、道宽、层高、体积和显示角色，坐标标记为 `workpiece_build`。该适配用于几何路径预览；旋转轴和喷嘴姿态仍由 T06 的 `MachineAxisTrajectory` 提供。

后续输出链路按以下顺序实现：

```text
GeneratedToolpath
  -> MachineAxisTrajectory
  -> ValidationReport
  -> main.gcode / toolpath.json / machine_axes.csv / warnings.json / preview.json
  -> G-code 回读核对
```

这种分层来自当前项目需要，也吸收了多轴增材资料的共同经验：几何路径、事件、机床轴和后处理要分层记录，否则很难定位不可达、奇异、碰撞或人工拼接痕迹。

## T01—T07 当前实现契约

| 层 | 代码入口 | 已实现的稳定边界 |
| --- | --- | --- |
| Operation 输入 | `manufacturing/setup.py`、`tube_controller.py`、`tube_commands.py`、`tube_ui.py` | 管体、入口、出口、基体、可选手动中心线 edge；九项正数参数含显式 mm、deg、mm/min 单位；几何/参数 Dirty；JSON 旧字段默认值 |
| 管特征 | `algorithms/tube/geometry.py` | 单支、无分叉、恒定圆截面直管/圆弧管；圆柱/环面和圆形端口；入口到出口有向中心线；手动 line/arc edge 链；稳定错误码 |
| 分区与切层 | `algorithms/tube/indexed.py` | 最大楔角和圆弧弦高误差共同控制区段；每区固定构建方向；半开区间归属；末尾不足整层时仍生成居中层 |
| 截交与薄壁路径 | `algorithms/tube/section.py`、`algorithms/tube/indexed.py` | OCCT 实体/平面截交、闭环恢复、内外环定向、mid-wall 单道路径、弦高采样、层/区段/材料体积语义 |
| 连接与转位 | `algorithms/tube/indexed.py` | 回抽、退离、index start/end、空移、接近、prime；转位段零材料体积；安全间隙小于沉积包络时定位失败 |
| 参考运动学 | `kinematics/xyzac.py` | Generic XYZAC 两分支、C 角展开、行程、奇异、速度/加速度、刀长、非零回转中心和 `T_workpiece_from_build`；逐点 FK 回代 |
| 检查报告 | `validation/indexed_tube.py` | 半径和层位置误差、轴轨迹问题、喷嘴 R–Z 包络、基体/夹具/机床 AABB、已打印 bead capsule、连续运动细分；Error 阻止导出 |

所有坐标路径仍以 `workpiece_build` 表达。碰撞检查采用轴对称喷嘴球包络、AABB 障碍物和 bead capsule 的保守离散近似；`motion_sample_error_mm` 控制相邻采样的平移量加旋转包络位移上界。它不包含热变形、材料流动、机床柔顺性或控制器跟随误差。

pipe2 当前 STEP 的实测管体为外半径 16 mm、内半径 15 mm；中心线为 `line → arc → line`，长度分别约 14.642637 mm、43.074143 mm、8.749117 mm，圆弧中心半径 35 mm、扫角约 −70.513331°。输入 SHA-256 为 `116e99fd43492bd1f4f519c80c93cd1f7cd0bf2cb6861b3e123148e4031a0d4b`。

T08 仍需把当前核心接入 Generate、成果页、后处理 NC、结果归档和 G-code 回读。T09 的多道 buildup、T10—T11 的连续螺旋及真实机床资格不属于 T01—T07 完成范围。

## 参考资料使用规则

已登记的 `reference_research.md` 继续作为入口。实施每个后续任务前，需要按任务再查资料：

| 任务 | 必查方向 |
| --- | --- |
| T01-T02 | STEP/OCC 圆柱、环面、边界环和中心线识别资料；必要时对照 CadQuery/OCP 文档 |
| T03-T05 | Siemens Tube Thinwall 公开流程、Fractal Cortex 分块思路、平面截交和偏置资料 |
| T06-T07 | 五轴 IK、奇异、角展开、速度/加速度约束、喷嘴包络和碰撞检查资料 |
| T10-T11 | RMF/double reflection、连续螺旋、低曲率和反曲退化处理资料 |

所有外部资料只作为可核对依据。产品网页不提供公式时，只能引用其工作流和术语；开源项目代码若许可证不适合，默认学习思想并独立实现。
