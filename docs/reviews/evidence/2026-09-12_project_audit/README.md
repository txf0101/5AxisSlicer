# AUD-01 证据说明

本目录记录 2026-09-12 的独立软件审查。这里的 G-code 包括已确认有缺陷的复现结果，仅用于离线检查，不能视为经过设备资格验证的程序。`INVALID_*.txt` 是故意损坏的回读反例。

- `source_before.json`、`git_status_before.txt`：开始时的工作区指纹和已有修改。
- `frozen_source_manifest.json`、`source_snapshot/`：固定副本的 197 份源码、测试、脚本与配置。归档文件追加 `.txt`，内容字节不变；它们是审查证据，不加入项目执行或质量工具的扫描范围。
- `pytest.log/xml`：初次工作区全仓，期间存在并行修改。
- `pytest_frozen.log/xml`：固定副本全仓，保留两个当时的 P07 失败。
- `pytest_p07_followup.log/xml`：并行任务修改后 46 项最小复测通过。
- `quality.log`、`quality_frozen.log`、`mypy.log`：各时点门禁原始结果，不能合并为全通过。
- `model_inventory.json`：五个项目 STEP 的 SHA256、导入时间和 body 包围盒。
- `fan_zigzag_3layers/`、`pipe_zigzag_3layers/`、`tube_baseline/`：实际生成产品、参数、路径图和摘要。
- `impeller_thin_3layers/`、`fan_full_height/`、`frozen_cases/`：失败记录与固定版本复现。
- `section_topology_probe.json`：独立原生拓扑、容差与曲线端点量测。
- `tube_probe/ready_setup/`：完整 Ready Setup 下坐标与状态失效的复现；`initial_unreviewed_material/` 保留首轮 Setup Error 未阻断的证据。
- `support_probe/`：柱体/顶板解析 STEP、实际六件套、57 条穿柱空移及独立盒相交量测。
- `ui/`：8 个真实 Qt/OpenGL 正常、错误和恢复截图及布局检查摘要；不是真人桌面点击证明。
- `document_before/`、`document_update.json`：本轮更新文档之前的版本、时间戳和哈希。
- `manifest.json`：本证据目录的逐文件最终指纹、验证结论及范围。

复算使用已有 `tmp/pytest9/Scripts/python.exe`。固定工作副本位于项目 `tmp/project_audit/frozen`，未修改产品源码；临时目录以后可被清理，持久副本在 `source_snapshot/`。恢复时把其中每个文件末尾的 `.txt` 去掉，保持相对路径，再放入已登记哈希一致的 `example/` 输入。

主探针的原执行位置为 `tmp/project_audit/audit_cases.py`，归档为 `audit_cases.py.txt`；独立截线脚本同理。固定版主探针使用 `AUDIT_SOURCE_ROOT=<固定工作副本>` 和 `AUDIT_EVIDENCE_SUBDIR=frozen_cases`。Tube/Support 探针的执行环境与文件指纹见各自摘要和清单。复算应输出到新目录，不覆盖首次失败证据。

审查报告与实施方案分别位于 `docs/reviews/2026-09-12_project_algorithm_audit.md`、`docs/planning/2026-09-12_algorithm_audit_fix_plan.md`。本轮完成检查和方案，没有实施产品修复。
