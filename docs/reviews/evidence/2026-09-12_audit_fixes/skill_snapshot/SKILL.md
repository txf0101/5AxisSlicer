---
name: five-axis-workbench-development
description: 开发或扩展 5AxisSclicer_V2.0 的 Tube、Planar、Curve、Freeform、Rotary、Research 工作台，复用既有制造契约、算法分层、生成/验证/回读、UI、图文手册和证据链。用于进度台账中的 P/C/F/R/X/I 实施与阶段收尾；普通状态问答只读台账，单纯测试故障使用 five-axis-slicer-validation。
---

# 五轴切片工作台开发复用

## 入口与范围

- 以当前仓库的 `AGENTS.md` 和 `docs/planning/progress_tracker.md` 为准。读取本轮任务行、直接依赖、最近相关复盘和当前 diff；不要重读全部历史材料。
- 一轮围绕一个台账编号或经台账记录的子编号完成最小闭环。缺少某项可选偏好时使用现有工作台约定；会改变支持范围、控制器语义或不可逆输出时才要求用户决定。
- 本 Skill 负责开发方法。进入测试、Qt/VTK 回归、失败诊断或阶段验收前，读取 `C:/Users/Tang Xufeng/.codex/skills/five-axis-slicer-validation/SKILL.md`，按其解释器、Qt 串行和停止条件执行。
- 只回答状态时读取台账和必要证据，不启动测试或创建新产物。

开始或关闭一个台账任务时，读取[阶段门槛](references/stage-gates.md)。局部代码修改只需使用其中与本轮影响有关的门槛。

修改生成、制造检查、缓存资格或 NC 回读，以及关闭算法阶段时，按影响读取[制造验证经验](references/manufacturing-validation.md)。它记录 AUD-02 的独立反例、局部量测和真实模型判据，后续 Curve、Rotary、Freeform、Research 沿用判断方法，具体容差由各自制造契约确定。

## 先复用的项目骨架

新增工作台能力前，优先检查并复用以下职责，不复制一套平行实现：

| 职责 | 当前复用入口 |
| --- | --- |
| Setup、坐标、资源和几何引用 | `manufacturing/setup.py`、`coordinates.py`、`resources.py`、`references.py` |
| 规范化路径、事件和来源 | `manufacturing/toolpath.py` |
| 操作定义、命令与持久化 | Tube controller/service/commands 的状态和事务做法；共享接口放入通用模块 |
| 轴轨迹与机型语义 | `kinematics/`、`manufacturing/machine.py`、`preview_kinematics.py` |
| 几何、运动和碰撞检查 | `validation/`、`manufacturing/nozzle_envelope.py` |
| 生成状态、六件套和回读 | `postprocessing/tube_product.py` 及对应后处理模块 |
| Viewer、后台任务与取消 | 现有 preview adapter、background load 和 UI 状态边界 |

复用概念和契约即可；Tube 专属几何不得硬塞入其他工作台。某项抽象只有两个以上工作台确实共享时再提升到公共层。

## 开发闭环

1. **确定受限范围。** 从计划和任务行写清正常输入、失败输入、坐标系、单位、输出和完成判据。保留未支持范围，输入超界时给可定位诊断。
2. **查资料并登记。** 几何、运动学、后处理或研究方法需要外部依据时，先查官方文档、成熟开源实现和可复算论文。记录固定链接或 commit、实际借鉴点和许可证；私有传阅不消除第三方许可条件。按本项目契约独立实现，不逐行翻译外部代码。
3. **建立独立真值。** 至少准备一个解析或独立测量正常案例和一个有意义的失败案例。旧手工 G-code 用于观察工序和覆盖，不自动成为逐点复制目标。
4. **实现纯领域链。** 保持 `Geometry → SlicePlan → Toolpath → MachineAxisTrajectory → ValidationReport → Postprocessor` 的边界。算法结果先形成 Toolpath，再适配 Viewer 和 G-code。
5. **接入产品状态。** 输入或参数变化使旧结果 Stale；Error 阻止导出；Warning 随结果保留。取消生成不得破坏上一份有效结果。保存重开、脚本和 HTTP 与 GUI 使用同一领域命令。
6. **完成可见流程。** 用户应能选择输入、理解参数、生成、取消、定位问题、查看路径、导出和重开。中英文帮助、单位、禁用原因和窗口尺寸均需核对。
7. **验证和归档。** 运行与改动相称的测试，保存必要摘要、输入/源码指纹和产物。更新同一任务复盘、图文手册、文档索引和唯一进度台账，再按用户要求提交或推送。

## 不可破坏的语义

- 内部长度用 mm、角度用 rad；UI 和外部文件显式声明角度单位。每个坐标和变换写清 Source、Model、Build、Workpiece 或 Machine frame。
- `ToolpathPoint` 保留 position、surface normal、tangent、nozzle axis、工艺参数、operation/stage/layer/region 和运动/挤出语义。Retract、Prime、Dwell 等事件不伪装成有长度的几何段。
- `imported_nc` 与 `generated_toolpath` 来源分开。修改显示质量不改变路径；修改工艺参数必须更新语义哈希并使结果过期。
- G-code 回读按已注册控制器语义进行。未确认语义、轴字不支持或限位异常时保留安全回退，不混合 Machine XYZ 与工件坐标。
- FK 回算、整段运动限制和碰撞检查分别有证据。单点无碰撞、离屏图形正常或参考机型通过都不能替代真实设备标定和现场资格。
- 几何误差、层高、道宽、路径间距和材料体积使用各自指标，避免用一个容差代替全部制造要求。

## UI 与图文手册

- 沿用当前 Workbench、操作树、编辑器、Viewer、问题列表和底部控制台的布局语言。修复根因，避免为单一窗口尺寸堆叠位置特判。
- 至少检查项目要求的中文/英文和代表性窗口尺寸。截图前完成真实操作；含缺失、过期或失败状态的图片必须标成错误示例。
- 阶段完成前更新 `docs/guides/`。手册包含入口、参数、正常流程、典型错误与恢复、三维结果、导出、保存重开和能力边界；图片进入稳定 assets 或带清单的 evidence 目录。

## 节省上下文和模型成本

- 给执行者只提供任务行、直接依赖、相关接口、当前 diff 和新增失败，不反复发送整份计划、全仓日志或长历史。
- 用户允许委派时，把文件盘点、固定格式文档、日志归纳和机械性测试矩阵交给低成本模型；几何歧义、IK、碰撞、跨模块根因和阶段判定保留给具备相应推理能力的执行者。
- 专项测试通过后按影响补一次必要回归。没有代码、证据或环境变化时，不重复同一失败尝试。

## 记录 Skill 调用

- 每个任务复盘增加“使用的 Skills”一项，写明 `five-axis-workbench-development`；执行测试或阶段验收时同时写 `five-axis-slicer-validation`。
- 在 `progress_tracker.md` 的 Skill 调用记录中登记日期、任务编号、Skill、用途和证据链接。只记录实际加载并影响本轮工作的 Skill，不预填未来调用。
- Skill 带来的范围、门槛或方法变化写入台账变更记录；普通重复调用不重复扩写计划。
