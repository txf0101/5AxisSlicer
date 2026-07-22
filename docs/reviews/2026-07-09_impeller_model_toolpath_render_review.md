# 2026-07-09 叶轮模型与路径论文图复盘

## 对象

本轮面向 `example/叶轮` 目录新增论文插图脚本。动手前核对到 `叶轮.stp` 修改时间为 2026-05-25 11:28:49，大小为 454267 字节；`叶轮完整.gcode` 修改时间为 2026-07-01 15:49:32，大小为 62753499 字节。目录内旧版 `render_gcode_complete_path_matlab.m` 和旧图保留不改，本轮新增独立入口 `render_impeller_model_toolpath.m`。

旧版 `gcode_complete_path_ac_inverse_3d_matlab.png` 的 A/C 轴反算代码采用 `P_part = Rz(-C) * Rx(-A) * P_machine`。本轮脚本沿用同一公式，并把真实路径模式调整为 `legacy_full_positive`：所有 `deltaE > 0` 的正挤出段都叠加到 STEP 模型上，保留旧图底部外圈和超长接续线等全量路径特征。

## 实现判断

本机 MATLAB 为 R2021b，`importGeometry` 对当前 STEP 文件不可用，直接导入会要求 STL 扩展名。脚本采用 Python CadQuery 生成 STL 缓存，再由 MATLAB `stlread` 读取三角网格。这样保留 MATLAB 出图入口，也减少手动 CAD 转存带来的版本差异。

自动示意图由 STL 网格切层得到 160 层等高线，输出灰色模型叠加蓝色层线。真实路径图解析 `叶轮完整.gcode`，保留 G90/G91、M82/M83、G92、A/C 字段和 G2/G3 圆弧入口；当前文件没有实际 G2/G3 圆弧命令。真实路径图不再按 A/C 姿态筛选，也不做长度过滤，`maxRealSegmentsToRender = inf`，`maxRenderedRealSegmentLength = inf`。模型与路径重合时采用显示层微抬升策略，路径沿相机方向偏移 0.18 mm；该做法保留模型深度遮挡，只解决表面路径被模型吃掉的问题，避免背面路径整体穿透出来。

## 验证

- `matlab -batch "checkcode('render_impeller_model_toolpath.m')"` 无 Code Analyzer 输出。
- 正式运行 `matlab -batch "render_impeller_model_toolpath"` 成功生成两组 PNG、TIF、FIG 和统计文件。
- 输出图片尺寸均为 4080 x 2880；真实路径 PNG 和 TIF 的非白像素比例约 0.424。
- 额外导出 16K 真实路径图，配置为 `renderAutoPath = false`、`outputDir = render_outputs_16k`、`resolutionDPI = 2400`；PNG 和 TIF 实际尺寸均为 16320 x 11520，缩略抽样非白像素比例约 0.444。
- 为左侧叶片区域导出 8K 放大分析图。为避免放大后出现线段端点缝隙，渲染阶段按 `path_join_tolerance_mm = 0.02` 将首尾连续的 G-code 小段拼成 polyline，仅在真实跳转处断开。连续线版 16K 全图位于 `render_outputs_16k_continuous`，左部裁剪图实际尺寸为 8192 x 6276。
- STL 网格统计为 15427 个顶点、30818 个面；模型包围盒为 X/Y `[-52, 52] mm`，Z `[0, 44] mm`。
- 真实 G-code 统计为 1021062 行、1011023 个运动段、1005400 个正挤出段；A 轴 `[0, 90] deg`，C 轴 `[-344.100006104, 135.559997559] deg`。
- 全量正挤出模式下，选中并渲染的真实路径段为 1005400 段；其中 A/C 正挤出段为 873316 段；长度过滤数为 0。
- 路径优先显示策略为 `path_on_top = 1`、`path_display_lift_mm = 0.18`。
- 所有正挤出段 A/C 反算后的范围为 X `[-57.6349983215, 57.6349983215] mm`，Y `[-57.6329994202, 57.6329994202] mm`，Z `[0.20000000298, 49.9092016766] mm`。旧统计中的 Z 上界 60.8469640175 来自全部运动段边界，包含非正挤出或空走段。

## 产物

- `example/叶轮/render_impeller_model_toolpath.m`
- `example/叶轮/render_outputs/impeller_model_auto_toolpath.png`
- `example/叶轮/render_outputs/impeller_model_auto_toolpath.tif`
- `example/叶轮/render_outputs/impeller_model_auto_toolpath.fig`
- `example/叶轮/render_outputs/impeller_model_real_gcode_toolpath.png`
- `example/叶轮/render_outputs/impeller_model_real_gcode_toolpath.tif`
- `example/叶轮/render_outputs/impeller_model_real_gcode_toolpath.fig`
- `example/叶轮/render_outputs/impeller_model_toolpath_stats.txt`
- `example/叶轮/render_outputs_16k/impeller_model_real_gcode_toolpath.png`
- `example/叶轮/render_outputs_16k/impeller_model_real_gcode_toolpath.tif`
- `example/叶轮/render_outputs_16k/impeller_model_real_gcode_toolpath.fig`
- `example/叶轮/render_outputs_16k/impeller_model_toolpath_stats.txt`
- `example/叶轮/render_outputs_16k_continuous/impeller_model_real_gcode_toolpath.png`
- `example/叶轮/render_outputs_8k_detail_continuous/impeller_real_gcode_left_detail_continuous_8k.png`
- `example/叶轮/render_outputs_8k_detail_continuous/impeller_real_gcode_left_detail_continuous_8k.tif`
- `example/叶轮/render_outputs_8k_detail_continuous/impeller_real_gcode_left_detail_continuous_preview.png`

## 方法沉淀

这次的价值点在于把论文效果图做成可重复运行的证据链：源模型和源 G-code 有时间戳，STEP 转 STL 有缓存，路径解析有统计锚点，图像尺寸和非空检查有数字记录。后续换模型时，应同步核对模型包围盒、运动段数、正挤出段数、A/C 范围、路径选择模式、长度过滤数和输出尺寸。

可复用做法集中在三个位置：STEP 网格化独立成缓存步骤；真实路径图把路径选择模式写入配置和统计文件；视觉样式只处理画布、相机、颜色和线宽，不改动 A/C 反算公式。这样论文图、GUI 预览和 MATLAB 后处理可以共享同一组事实锚点。
