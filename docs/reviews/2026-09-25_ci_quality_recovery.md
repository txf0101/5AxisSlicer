# GitHub Actions 质量门禁修复复盘

日期：2026-09-25。对象：`master` 的 `quality` 工作流；原失败运行 [#14](https://github.com/txf0101/5AxisSlicer/actions/runs/36034655720)。

## 判断与证据

三个失败任务均停在 `python scripts/check_quality.py`；Windows 原生冒烟任务通过。公开 GitHub 页面未提供完整原始日志，本地使用项目 `tmp/pytest9` Python 3.12 环境重现：Ruff、格式、安全规则通过，随后上下文预算拒绝 81 项；单独继续运行 Mypy 又发现 8 个文件中的 37 条类型错误。最新 README 提交只改文档，不能据此把失败归因于 README。

## 修复取舍

- 修复类型标注、可空几何检查和事件索引变量复用。G-code 边界用明确三元坐标；换料站校验沿用 `ToolChangeStation.from_json`。未改动切片、碰撞或换料运动算法。
- 原预算表按文件统一放宽函数及复杂度阈值，且未覆盖近阶段新增对象。改为按完整对象名记录当前发布版本的精确上限；新函数、类仍使用默认上限。101 个对象、128 项超出默认预算的现存指标作为可见重构债务保留。这个修复恢复“不得继续增长”的门槛，不表示大型函数已完成拆分。
- 增加回归测试，证明旧对象例外不会放行同文件的新函数。此后发布前必须先跑完整质量脚本并核对退出码，推送后等待 Actions 完成；对应规则已记入个人 `five-axis-slicer-validation` Skill。

## 本地验证与边界

`scripts/check_quality.py` 全部通过，Mypy 对 191 个源码文件无错误；与 CI 相同的领域集连同直接相关测试为 188 passed、2 skipped、89 subtests passed。Freeform 扩展测试中 3 项先因本机默认 pytest 临时目录拒绝访问而在设置阶段报错，改用独立项目内 `--basetemp` 后 3 passed。隔离构建成功，新的 sdist 和 wheel 均通过 Twine 检查。本机旧版 setuptools 下的非隔离构建失败，不代表隔离 CI 构建失败；`dist/*` 还包含旧 ZIP，故 Twine 只核查本轮两个新包。

此处核验的是静态门禁、领域测试和打包。桌面完整交互、实机控制器及材料测试不在本轮范围。GitHub 托管检查须在推送后以新运行结果单独判定；本地通过不能替代托管 CI。

使用的 Skills：`gh-fix-ci` 用于确认失败任务与实施边界；`five-axis-slicer-validation` 用于解释器、质量门禁和环境错误分类。项目工作台开发 Skill 仅用于核对既有领域契约，未启动新的算法阶段验收。
