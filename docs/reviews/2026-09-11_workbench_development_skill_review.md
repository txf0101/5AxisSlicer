# 工作台开发复用 Skill 建立复盘

日期：2026-09-11

## 使用的 Skills

- `skill-creator`：确定 Skill 的触发范围、目录结构、渐进式参考文件和校验方式。
- `five-axis-workbench-development`：创建后重新读取，用于核对开发闭环、阶段门槛及台账登记方式。
- `five-axis-slicer-validation`：复用项目解释器、Qt 串行、证据归档和重试停止边界，并与开发 Skill 分工。

## 从 Tube 阶段提炼的经验

Tube T01—T12 表明，其他工作台可以复用的核心内容包括：

1. 以唯一进度台账限定任务范围、依赖、完成判据和下一步，避免入口完成后过早声明整个工作台完成。
2. 修改算法前查官方资料、成熟实现和论文，记录固定版本、借鉴点与许可证。外部项目提供思路，当前项目按自身 B-Rep、路径和验证契约独立实现。
3. 用解析几何或独立测量建立正常、边界和失败真值。手工 G-code可用于观察工序和覆盖，不自动成为逐点复制目标。
4. 保持 `Geometry → SlicePlan → Toolpath → MachineAxisTrajectory → ValidationReport → Postprocessor` 分层。Viewer 和 G-code 都消费结构化结果，避免把解析后的 G-code 当作唯一算法数据。
5. GUI、受限脚本和 HTTP 共用领域命令；输入变化、Dirty/Stale、取消、Error/Warning、旧结果保留和保存重开使用一致状态语义。
6. 几何、材料、轴位、FK、速度/加速度、碰撞和 NC 回读分别验证。参考机型离线结果与真实控制器、机床标定和现场资格分开表述。
7. UI 验收包含真实交互、中英文、代表性窗口尺寸、文字适配和按钮碰撞；阶段交付同步完成图文手册、错误示例和稳定截图。
8. 为节省上下文，执行任务只提供任务行、直接依赖、相关接口、当前 diff 和新增失败；获得用户委派授权时，机械盘点和固定格式整理可交给低成本模型。

## Skill 结构与调用方式

个人 Skill 位于：

`C:/Users/Tang Xufeng/.codex/skills/five-axis-workbench-development/`

- `SKILL.md`：触发范围、共享入口、开发闭环、语义约束、UI/手册和调用登记规则。
- `references/stage-gates.md`：任务开始、契约与算法、产品闭环、UI/手册、测试证据和阶段完成门槛。
- `agents/openai.yaml`：Codex UI 名称、说明和默认调用提示；保持自动发现。

项目 `AGENTS.md` 已加入固定入口。后续 P/C/F/R/X/I 或新增 Tube 任务实际加载 Skill 后，在台账“Skill 调用记录”和该任务复盘中登记。普通状态问答不加载完整开发流程。

## 校验与指纹

使用 `skill-creator/scripts/quick_validate.py` 校验，结果为 `Skill is valid!`。

| 文件 | SHA-256 |
| --- | --- |
| `SKILL.md` | `8046C5568CC1AB884094B55428869639BF9AC84E168183AD784BF3FF416CEF8E` |
| `references/stage-gates.md` | `D28B0D4E5D790E2776E0149A3E33F77D2A8010617431E8BD7C92686B119AAC75` |
| `agents/openai.yaml` | `02EF3BB2CC3078C1F036EBF807525DCFAE8F0F3407D98D7AB872CB83CED8FB42` |

本轮只新增个人 Skill 并修改项目文档，没有修改算法、UI 或测试。按 `five-axis-slicer-validation` 的范围，不运行应用全仓回归；Skill 结构校验、文档链接和 Git diff 检查足以覆盖本轮变化。P01 仍为未开始，首次用于实际工作台开发时应重新记录调用和任务证据。

