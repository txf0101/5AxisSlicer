# T01—T07 质量门禁摘要

日期：2026-09-11。解释器：`tmp/pytest9/Scripts/python.exe`（Python 3.12.7）。所有 pytest 命令串行执行。

## 结果

- 预检：依赖匹配，QSettings 可写，`issues: []`。
- `scripts/check_quality.py`：Ruff、增量 Ruff、安全 Ruff、格式、context-budget、mypy 全部通过；mypy 为 `Success: no issues found in 86 source files`。
- `pytest tests/test_tube_indexed_pipeline.py -q`：19 passed，3.12 s。
- UI 审查前的 `pytest tests/test_tube_ui.py -q`：29 passed，2 subtests passed，75.06 s；最终 UI 联合回归中 Tube UI 为 30 passed，2 subtests passed。
- 最终 UI 联合回归：49 passed，6 subtests passed，170.33 s；质量门禁通过。Tube UI 数量为 30 passed，2 subtests passed；该次运行覆盖英文动态反馈修正。
- 相关回归：158 passed，2 skipped，85 subtests passed，21.88 s。
- `pytest -q`：430 passed，3 skipped，130 subtests passed，308.59 s；JUnit 记录 563 testcase、0 failure、0 error。该次运行在英文动态反馈修正前完成，修正后的 UI 专项与质量门禁均通过。

## 全仓跳过项

1. `tests.test_project_io.ProjectIoTests::test_content_addressed_symlink_target_outside_project_is_rejected`
2. `tests.test_project_io.ProjectIoTests::test_project_source_directory_symlink_is_rejected`
3. `tests.test_setup_config.SetupConfigStorageTests::test_file_reader_rejects_symbolic_links`

三项均因当前 Windows 用户缺少创建符号链接所需权限（WinError 1314）而跳过。该限制已在既有验证记录中登记；它不影响本轮 Tube Indexed 算法、UI、运动学或碰撞断言。
