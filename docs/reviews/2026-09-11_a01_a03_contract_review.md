# A01-A03 契约实施复盘

任务编号：A01、A02、A03。

时间：2026-09-11。

## 范围

本轮完成管状算法基线、样例来源登记和通用路径结果契约。未实现中心线识别、切片、IK、碰撞、后处理或 UI 生成按钮。真实机床未验证。

## 已完成

- 读取 `progress_tracker.md`、`development_plan.md`、`reference_research.md` 和项目验证 Skill。
- 执行只读预检，确认 `tmp/pytest9/Scripts/python.exe`、依赖、质量工具和 QSettings 当前可用。
- 建立 [管状算法基线、样例与 Toolpath 契约](../planning/tube_algorithm_contract.md)。
- 建立 [样例来源登记](../planning/example_source_inventory.md)。
- 固定 `tests/fixtures/analytic_tube_truth.json`，记录独立直管和圆弧管参数、公式及期望量。
- 新增 `src/five_axis_slicer/manufacturing/toolpath.py`，定义 `ToolpathPoint`、`ToolpathEvent`、`GeneratedToolpath` 和 `GeneratedResultManifest`。
- 为 `GeneratedToolpath` 增加现有结果查看器路径段适配；机床轴姿态仍留在后续运动学阶段。
- 新增 `tests/test_toolpath_contract.py`，覆盖 JSON 往返、单位归一、导出状态、非法材料体积、解析真值和预览适配。

## 外部资料处理

本轮按用户要求主动查找了 Siemens 多轴增材、Tube Thinwall、五轴增材运动规划和 RMF 相关资料方向。已有 `reference_research.md` 中的 Siemens NX、Fractal Cortex、MAGE、Open5x、COMPAS Slicer、RMF 等来源继续作为入口。由于 A01-A03 是契约任务，本轮没有把外部公式或源码迁入项目；后续 T02/T03/T06/T10 按对应算法再固定版本、许可证和具体公式。

## 验证

预检命令：

```powershell
& "tmp/pytest9/Scripts/python.exe" -X utf8 "C:/Users/Tang Xufeng/.codex/skills/five-axis-slicer-validation/scripts/preflight.py" --repo "F:/【项目和任务】/5AxisSclicer_V2.0"
```

结果：依赖匹配，`issues` 为空，QSettings 可写。

新增测试：

```powershell
& "tmp/pytest9/Scripts/python.exe" -m pytest tests/test_toolpath_contract.py -q
```

结果：`6 passed in 0.41s`；JUnit 见 [toolpath_contract_pytest.xml](evidence/2026-09-11_a01_a03/toolpath_contract_pytest.xml)。

质量检查：

```powershell
& "tmp/pytest9/Scripts/python.exe" scripts/check_quality.py
```

结果：Ruff、格式、上下文预算和 Mypy 均通过，Mypy 检查 74 个源文件无问题。

全仓串行回归：

```powershell
& "tmp/pytest9/Scripts/python.exe" -X faulthandler -m pytest -q -ra --junitxml="docs/reviews/evidence/2026-09-11_a01_a03/full_pytest.xml"
```

结果：`408 passed, 3 skipped, 130 subtests passed in 178.78s`。3 项跳过均为 Windows 无符号链接创建权限，与既有边界一致；未把跳过计为通过。命令、文件指纹和结果摘要见 [证据清单](evidence/2026-09-11_a01_a03/manifest.json)。

## 验收结论

A01 的环境、支持边界、输入角色、容差和分阶段验收入口已明确。A02 的逐文件来源、pipe2 指纹和独立解析真值可追溯。A03 的路径、事件、结果、来源与版本契约可序列化，并已接入现有预览段结构。三项完成判据均有当前代码和本轮验证支撑，正式状态为“已完成”，下一项为 T01。

## 局限

样例来源中仍有未知项，尤其历史 G-code 的外部切片软件、人工拼接范围和控制器配置。A02 已登记这些未知项，后续不能用未知来源文件替代独立真值。解析 STEP 实体与 pipe2 的拓扑测量属于 T02。A03 当前覆盖生成路径层，`MachineAxisTrajectory` 和 `ValidationReport` 留到 T06-T07。真人桌面全流程和真实机床仍未验证。
