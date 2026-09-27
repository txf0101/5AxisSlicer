# V2-05 提交范围审查

日期：2026-09-27。只读核查后按主任务授权创建本报告；没有恢复、删除、暂存、提交或推送其他文件，没有运行测试或操作 GUI。使用 five-axis-slicer-validation Skill。此报告供主任务显式选择提交范围，不是已完成发布的证明。

## 当前基线与历史 YAML 差异

当前分支 master，HEAD 为 `edacd49af9cb1766439526b171910d9f7538044d`。本地缓存 origin/master 与 HEAD 差异为 0/0，未 fetch，不作为远端实时同步证明。远端为 `https://github.com/txf0101/5AxisSlicer.git`。

需单独处理的已跟踪文件：

`docs/reviews/evidence/2026-09-24_product_delivery_ui_audit/impeller_gui_root_growth_live/manufacturing-setup.yaml`

| 对象 | 指纹 |
| --- | --- |
| 工作区文件 SHA256 | `3b915af12513f89b53f1052864f2d51afbf7c572c724995eff6e85b5f65030b6` |
| HEAD 文件原始字节 SHA256 | `804ea1d5338943a44f651a6a17c1be99822b8d34616047e09661e1c98feb39bc` |
| HEAD Git blob ID | `412c1eccc64f941a9335161e7a0d8ecbe6e8011e` |

当前差异：metadata revision 1→12，content_sha256 从 `7f00ebaf203df078f8c034dfc0fc4f99e93d2f484a6b6cd55c337bb15f09b8fd` 改为 `f2655f53b9da024e5860f0e1e3342f11129619a01822d22348dedcf84d9db784`；机床 profile_version/version 1→2，平台直径180→150mm，名称改为 Own AC usable circular platform，资源哈希同步变化；Placement 局部 translation_mm 从三个0改为三个−250。

这些变化与当前 GUI 装夹修正一致，可能由 GUI 自动保存产生。本报告未独立跟踪写入进程，不把“自动保存”写成已证实根因。建议暂不纳入正式提交，保留现状由主任务明确处理。历史证据不能静默更新成当前验收结果；新的居中项目应以本轮证据路径独立保留。不得未经核对直接恢复此文件。

## 建议纳入的类别

- 当前目标所需产品代码及对应测试：`src/five_axis_slicer/`、`tests/`。新增调用依赖必须完整带入，特别是 `src/five_axis_slicer/postprocessing/printed_segment_index.py`、`src/five_axis_slicer/tube_placement_ui.py`、有界 Tube 模块及其测试。此项是范围建议，不授权盲目加入所有文件。
- 运行依赖与安装说明：`pyproject.toml`、`README.md`。
- 用户指南及当前图片：本轮修改的 `docs/guides/*.md`、`docs/guides/assets/current_delivery/`；教程代理仍可能写入，暂存前重新核对。
- 当前计划和状态：`docs/planning/v2_final_delivery_plan_20260925.md`、`docs/planning/progress_tracker.md`、`docs/reviews/2026-09-26_v2_final_delivery_review.md`、`docs/README.md`。
- 8份用户素材目录过程记录的迁移应成组处理：`docs/guides/assets/machine_profiles/summary.json`、`docs/guides/assets/planar/summary.json`、`docs/guides/assets/planar/current_p01_p07/p02/summary.json`、同目录p06与p07的summary.json、`docs/guides/assets/rotary/current_r01_r05/summary.json`、`docs/guides/assets/rotary/fan_blade_check/figure_summary.json`、`docs/guides/assets/rotary/live_qt/summary.json`。对应迁入目录是 `docs/reviews/evidence/2026-09-26_v2_final_delivery/guide_capture_records/`，需保留 README、relocation_manifest.json及原件，不仅提交删除。关联的9月12日P07与9月13日Rotary复盘链接调整也应同批核对。
- 本轮证据只明确选取摘要、哈希清单、必要日志/XML和关键截图；完整六件套保留本地交付，不整目录暂存。

## 建议排除并保留本地的内容

锁文件 `.project-save.lock`（包括历史项目内同名文件）、`.pytest-temp/`、根目录 `manufacturing-setup.yaml` 不应顺手加入。当前 .gitignore 未覆盖这些项目。本报告没有新增忽略规则或删除它们。

下列为审查时发现的较大文件，路径均相对 `docs/reviews/evidence/2026-09-26_v2_final_delivery/`；不是全部大文件清单：

| 路径 | 字节数 |
| --- | ---: |
| v2_02_live_service_v7.json | 155930198 |
| tube_v7_gui_export/manifest.json | 155748867 |
| logo_current150_gui_export/toolpath.json | 93174657 |
| tube_v7_gui_export/toolpath.json | 90421820 |
| v2_02_tube_current150_export/manifest.json | 72350666 |
| tube_pipe2_export/manifest.json | 72350658 |
| logo_current150_gui_export/preview.json | 71999700 |
| v2_02_combined_diagnostic_toolpath.json | 61045148 |

不得使用 `git add -A` 或整体加入 evidence 目录。`docs/planning/fan_complete_program_plan.md`、`2026-09-26_fan_sequential_audit*`、`2026-09-26_paper_screenshot_refresh*`及9月20/24大量未跟踪产物属于相邻或既有工作，需确认归属；本报告不把它们自动算成本轮 Agent 修改，不擅自暂存。

## 定向检查与局限

当前修改/新增的源码、测试、脚本及用户文档中，常见 GitHub/OpenAI/AWS 密钥和私钥头模式未命中。指南 Markdown/JSON 中未检出 Computer Use、捕获工具标识或个人绝对路径。这只是定向文本筛查，不是整仓秘密审计，不覆盖图片内文字或所有可能的凭据形式。

`MANIFEST.in` 排除了 reviews、tmp、tests、example等目录，保留指南Markdown与格式文档。包检查和Git提交范围是不同检查；包未包含临时产物不能证明暂存内容合格。最终以主任务重新读取的实际暂存差异为准。
