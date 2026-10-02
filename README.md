# 5AxisSclicer V2.9

5AxisSclicer 是用于五轴增材制造的 Windows 桌面切片软件。打开 STEP/STP 模型后，可以设置零件、机床和材料，按几何形状选择工作台，生成并查看路径，最后导出供离线检查的 NC/G-code 文件。

![自由曲面工作台中的叶轮模型](docs/guides/assets/hd_v27/freeform_existing_surface_solid_zh.png)

*自由曲面工作台中的叶轮示例。*

## 从这里开始

- [五个工作台图文教程](docs/guides/quickstart_clickthrough_zh.md)：跟着界面完成一次打开模型、设置、生成和导出。
- [学习手册](docs/guides/user_learning_manual_zh.md)：了解软件界面，以及如何把示例步骤用到自己的模型。
- [示例文件](example/README.md)：下载模型和离线 G-code，练习查看与对比路径。
- [English README](README.en.md) · [English quick start](docs/guides/quickstart_clickthrough_en.md)

## 功能与说明

| 模块 | 适合做什么 | 详细说明 |
| --- | --- | --- |
| 公共制造设置 | 设置零件、机床、喷嘴、材料和坐标 | [设置与操作教程](docs/guides/quickstart_clickthrough_zh.md#公共设置与本工作台设置) |
| Planar 平面工作台 | 对平面截层生成填充、轮廓和支撑路径 | [Planar 指南](docs/guides/planar_workbench_zh.md) |
| Curve 曲线工作台 | 沿模型边线生成单道或多道沉积路径 | [Curve 指南](docs/guides/curve_workbench_zh.md) |
| Rotary 回转工作台 | 围绕固定轴生成圆柱、圆锥等回转路径 | [Rotary 指南](docs/guides/rotary_workbench_zh.md) |
| Tube 管状工作台 | 沿管体生成分段或连续生长路径 | [Tube 指南](docs/guides/tube_workbench_zh.md) |
| Freeform 自由曲面工作台 | 在曲面或指定实体区域上生成路径 | [Freeform 指南](docs/guides/freeform_workbench_zh.md) |
| G-code 文件预览 | 打开已有 NC/G-code，查看三维路径和代码 | [预览指南](docs/guides/gcode_preview_zh.md) |

更多关于机型、材料和坐标的说明见[手册目录](docs/guides/README.md)。软件仍在测试和完善中；实际打印前请按自己的设备检查设置和路径。

## 日常预览更新（2026-10-02）

已有 G-code 的层注释兼容 `;LAYER:0` 与 `;Layer 0`；取消加载后保留上一份路径、文件来源和警告，后台结束后显示“加载已取消”。FIT/ISO 使用独立布局，显隐复选框两态对齐，普通 Preview 的图例与路径段属性可以滚动查看。

跟随更新后的 [G-code 预览教程](docs/guides/gcode_preview_zh.md)练习八层文件、路径进度、取消及重开。截图来自修复后的日常预览候选；名义料条仍采用近似姿态与 NC/默认宽厚，不代表实测沉积形状。

### 可复用 Skill

[five-axis-daily-ui-review](skills/five-axis-daily-ui-review/SKILL.md)整理了实际 Windows 界面验收、候选资源核查、层范围、取消恢复及截图归档方法。可下载 [Skill ZIP](skills/packages/five-axis-daily-ui-review.zip)，将其中的 `five-axis-daily-ui-review` 文件夹放入自己的 Codex skills 目录，也可在仓库根目录执行：

```powershell
$skillHome = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME 'skills' } else { Join-Path $env:USERPROFILE '.codex/skills' }
New-Item -ItemType Directory -Path $skillHome -Force | Out-Null
Copy-Item -LiteralPath 'skills/five-axis-daily-ui-review' -Destination $skillHome -Recurse
```

调用示例：`使用 $five-axis-daily-ui-review 验收当前候选的日常界面，保留已有窗口，不连接机器。`

修复、测试及仍缺少的两项截图见 [界面修复与 Skill 交付记录](docs/verification/daily_ui_20261002.md)。
