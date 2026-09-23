# 四个模型的离线切片示例

以下模型、原始 G-code 与软件生成的代码放在各示例目录。原始代码用于路径对照。软件生成的代码只适用于离线查看与分析；碰撞、机床标定、控制器宏和试打未取得资格，禁止直接上机。

| 示例 | STEP 模型 | 原 G-code | 新离线 G-code | 对比图 | 路径中间文件 |
| --- | --- | --- | --- | --- | --- |
| 弯管 | [弯管新.stp](pipe2/弯管新.stp) | [弯管.gcode](pipe2/弯管.gcode) | [v5](pipe2/弯管_新算法_离线检查_20260921_v5.gcode) | [图](../docs/reviews/evidence/2026-09-20_fan15_repairs/pipe_offline_nc_v5_20260921/nc_comparison.png) | [toolpath.json.gz](../docs/reviews/evidence/2026-09-20_fan15_repairs/pipe_offline_nc_v5_20260921/toolpath.json.gz) |
| 球形 NEU 校徽 | [球形测试件.STEP](球形NEU校徽/球形测试件.STEP) | [NEU校徽划线.gcode](球形NEU校徽/NEU校徽划线.gcode) | [新代码](球形NEU校徽/球形NEU校徽_新算法_离线检查_20260921.gcode) | [图](../docs/reviews/evidence/2026-09-20_fan15_repairs/logo_offline_nc_20260921/nc_comparison.png) | [toolpath.json.gz](../docs/reviews/evidence/2026-09-20_fan15_repairs/logo_offline_nc_20260921/toolpath.json.gz) |
| 叶轮 | [叶轮.stp](叶轮/叶轮.stp) | [叶轮完整.gcode](叶轮/叶轮完整.gcode) | [新代码](叶轮/叶轮_新算法_离线检查_20260921.gcode) | [图](../docs/reviews/evidence/2026-09-20_fan15_repairs/impeller_offline_nc_20260921/nc_comparison.png) | [toolpath.json.gz](../docs/reviews/evidence/2026-09-20_fan15_repairs/impeller_offline_nc_20260921/toolpath.json.gz) |
| 三叶扇 | [Supportless_sample.stp](三叶扇/Supportless_sample.stp) | [EXAMPLE.gcode](三叶扇/EXAMPLE.gcode) | [新代码](三叶扇/三叶扇_新算法_离线检查_20260921.gcode) | [图](../docs/reviews/evidence/2026-09-20_fan15_repairs/three_leaf_offline_nc_20260921/nc_comparison.png) | [toolpath.json.gz](../docs/reviews/evidence/2026-09-20_fan15_repairs/three_leaf_offline_nc_20260921/toolpath.json.gz) |

每个对比图旁的 `nc_readback_paths.npz` 可用于复核代码中的空间路径。数据格式和检查结果见[离线清单](../docs/reviews/evidence/2026-09-20_fan15_repairs/fan15_offline_acceptance_manifest.json)及各示例的 `report.json` 或 `delivery.json`。

新加入的 `.gcode`、`toolpath.json.gz` 和 `nc_readback_paths.npz` 由 Git LFS 保存。安装 Git LFS 后运行 `git lfs pull` 才能取得文件内容。模型与对比图为普通仓库文件。原始三叶扇程序的 B 轴语义及宏未获得机床配置确认，不能将其直接当作新程序的 C 轴解释。
