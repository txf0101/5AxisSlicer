# 项目验证经验入口

在本项目执行开发验证、Qt/VTK 测试、测试失败诊断或阶段验收前，读取个人 Skill：

`C:/Users/Tang Xufeng/.codex/skills/five-axis-slicer-validation/SKILL.md`

它记录已验证解释器、只读预检、QSettings 权限问题、Qt 串行测试要求、重试停止条件和证据归档位置。先复用这些经验，再检查本轮变化，不从零重复试环境。Skill 不在当前技能列表时，直接读取上述文件；路径失效时仅查找同名 Skill，仍缺失则使用 `docs/reviews/2026-09-11_b01_b03_acceptance_review.md` 的证据并说明缺失。

普通状态问答只读 `docs/planning/progress_tracker.md` 对应行及必要证据，不为回答状态启动测试。历史验收不自动代表当前代码通过；当前任务范围和权限优先。
