# FAN15 四例离线交付

以下模型、原始 G-code 与新代码放在原示例目录。新代码由仓库内切片脚本生成，已完成完整 NC 流回读和坐标反算检查；旧代码只作为路径参考。所有新代码均为离线诊断产物，未通过碰撞、机床标定、控制器宏和试打资格，禁止直接上机。

| 示例 | STEP 模型 | 原 G-code | 新离线 G-code | 对比图 | 路径中间文件 |
| --- | --- | --- | --- | --- | --- |
| 弯管 | [弯管新.stp](pipe2/弯管新.stp) | [弯管.gcode](pipe2/弯管.gcode) | [v5](pipe2/弯管_新算法_离线检查_20260921_v5.gcode) | [图](../docs/reviews/evidence/2026-09-20_fan15_repairs/pipe_offline_nc_v5_20260921/nc_comparison.png) | [toolpath.json.gz](../docs/reviews/evidence/2026-09-20_fan15_repairs/pipe_offline_nc_v5_20260921/toolpath.json.gz) |
| 球形 NEU 校徽 | [球形测试件.STEP](球形NEU校徽/球形测试件.STEP) | [NEU校徽划线.gcode](球形NEU校徽/NEU校徽划线.gcode) | [新代码](球形NEU校徽/球形NEU校徽_新算法_离线检查_20260921.gcode) | [图](../docs/reviews/evidence/2026-09-20_fan15_repairs/logo_offline_nc_20260921/nc_comparison.png) | [toolpath.json.gz](../docs/reviews/evidence/2026-09-20_fan15_repairs/logo_offline_nc_20260921/toolpath.json.gz) |
| 叶轮 | [叶轮.stp](叶轮/叶轮.stp) | [叶轮完整.gcode](叶轮/叶轮完整.gcode) | [新代码](叶轮/叶轮_新算法_离线检查_20260921.gcode) | [图](../docs/reviews/evidence/2026-09-20_fan15_repairs/impeller_offline_nc_20260921/nc_comparison.png) | [toolpath.json.gz](../docs/reviews/evidence/2026-09-20_fan15_repairs/impeller_offline_nc_20260921/toolpath.json.gz) |
| 三叶扇 | [Supportless_sample.stp](三叶扇/Supportless_sample.stp) | [EXAMPLE.gcode](三叶扇/EXAMPLE.gcode) | [新代码](三叶扇/三叶扇_新算法_离线检查_20260921.gcode) | [图](../docs/reviews/evidence/2026-09-20_fan15_repairs/three_leaf_offline_nc_20260921/nc_comparison.png) | [toolpath.json.gz](../docs/reviews/evidence/2026-09-20_fan15_repairs/three_leaf_offline_nc_20260921/toolpath.json.gz) |

每个对比图旁还保存 `nc_readback_paths.npz`，用于复核从新代码回读的空间路径。生成与验收摘要见[离线清单](../docs/reviews/evidence/2026-09-20_fan15_repairs/fan15_offline_acceptance_manifest.json)，各示例对比图旁的 `report.json` 或 `delivery.json` 记录具体结果。历史审查文档[保留初次失败记录](../docs/reviews/2026-09-20_fan15_example_acceptance.md)，不能代替这次离线结果。

新加入的 `.gcode`、`toolpath.json.gz` 和 `nc_readback_paths.npz` 由 Git LFS 保存。安装 Git LFS 后运行 `git lfs pull` 才能取得文件内容。模型与对比图为普通仓库文件。原始三叶扇程序的 B 轴语义及宏未获得机床配置确认，不能将其直接当作新程序的 C 轴解释。
