# 工作台开发复用入口

在本项目实施或收尾 Tube、Planar、Curve、Freeform、Rotary、Research 及整体验收任务前，读取个人 Skill：

`C:/Users/Tang Xufeng/.codex/skills/five-axis-workbench-development/SKILL.md`

它把 Tube T01—T12 的可复用做法整理为受限范围、资料检索、独立真值、共享 Toolpath、生成状态、验证回读、UI、图文手册和证据归档闭环。开始或关闭台账任务时按 Skill 路由读取 `references/stage-gates.md`；局部工作只使用相关门槛。

每次实际调用在 `docs/planning/progress_tracker.md` 的“Skill 调用记录”中登记，并在对应任务复盘列出使用的 Skills。普通状态问答只读台账，不加载完整开发流程。

Skill 不在当前技能列表时，直接读取上述文件；路径失效时仅查找同名 Skill，仍缺失则使用 `docs/reviews/2026-09-11_workbench_development_skill_review.md` 与 `docs/planning/development_plan.md`，并在本轮记录中说明缺失。

# 项目验证经验入口

在本项目执行开发验证、Qt/VTK 测试、测试失败诊断或阶段验收前，读取个人 Skill：

`C:/Users/Tang Xufeng/.codex/skills/five-axis-slicer-validation/SKILL.md`

它记录已验证解释器、只读预检、QSettings 权限问题、Qt 串行测试要求、重试停止条件和证据归档位置。先复用这些经验，再检查本轮变化，不从零重复试环境。Skill 不在当前技能列表时，直接读取上述文件；路径失效时仅查找同名 Skill，仍缺失则使用 `docs/reviews/2026-09-11_b01_b03_acceptance_review.md` 的证据并说明缺失。

普通状态问答只读 `docs/planning/progress_tracker.md` 对应行及必要证据，不为回答状态启动测试。历史验收不自动代表当前代码通过；当前任务范围和权限优先。
