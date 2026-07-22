# 2026-07-10 扇叶模型与真实路径论文图复盘

## 源文件核对

本轮工作目录为 `example/扇叶`。动手前检查了当前目录和项目上级目录中的 Markdown、旧 MATLAB 脚本、旧统计文件和已生成图片。目录内已有 `pic.m`、`fan_blade_toolpath_*.png/.fig` 和 `fan_blade_toolpath_render_stats_matlab.txt`，修改时间集中在 2026-07-07 至 2026-07-09。本轮保留这些文件，新增独立脚本和独立输出目录。

源模型为 `example/扇叶/风扇扇叶.STEP`，大小 822787 字节，修改时间为 2026-07-03 15:26:09。源路径为 `example/扇叶/风扇扇叶完整.gcode`，大小 186766355 字节，修改时间为 2026-07-09 10:40:05。

项目复盘和旧脚本给出的 A/C 反算口径保持一致：`P_part = Rz(-C) * Rx(-A) * P_machine`。MATLAB 中对应写法为先用 `ad = -double(aDeg(:)) * pi / 180` 调用 `rotateXVector`，再用 `cd = -double(cDeg(:)) * pi / 180` 调用 `rotateZVector`。

## 实现口径

新增文件：

- `example/扇叶/render_fan_blade_model_toolpath.m`
- `example/扇叶/render_fan_blade_model_toolpath_engine.m`

主入口负责默认源文件、输出目录、普通图、16K 全图和 8K 局部裁剪。engine 负责 STEP/STP 到 STL 缓存、MATLAB `stlread` 网格读取、G-code 解析、A/C 反算、深度渲染和统计写出。该结构沿用叶轮最终版和球形 NEU engine 的成熟分层，便于后续替换 STEP/STP 与 G-code/NC。

G-code 解析覆盖 `G90/G91`、`M82/M83`、`G20/G21`、`G92`、`X/Y/Z/A/C/E/F` 字段，并保留 `G2/G3` 圆弧离散入口。本轮真实路径选择模式为 `legacy_full_positive`，所有 `deltaE > 0` 的正挤出段进入渲染；`maxRealSegmentsToRender = Inf`，`maxRenderedRealSegmentLength = Inf`，未按 A/C 姿态筛选，未剔除前段裙边，未做长度过滤。

模型采用灰色不透明实体，路径采用高饱和蓝色线。路径显示阶段沿相机方向偏移 0.18 mm，`pathJoinTolerance = 0.02 mm`。engine 中没有 `uistack`、`childorder` 或强制置顶逻辑，只设置 MATLAB 深度排序，并保留模型遮挡关系。

## 验证数据

`matlab -batch "checkcode('render_fan_blade_model_toolpath.m'); checkcode('render_fan_blade_model_toolpath_engine.m')"` 无输出。

正式运行命令为：

```powershell
matlab -batch "render_fan_blade_model_toolpath"
```

MATLAB 退出阶段仍打印本机环境中的 `Settings` 提示；该提示在旧扇叶和叶轮复盘中也出现过，图像和统计文件已经写盘完成。

关键统计如下：

- STEP/STL 网格：2740 个顶点，5464 个三角面。
- 模型包围盒：X `[-73.6499023438, 82.5022964478] mm`，Y `[-82.8006362915, 73.5003814697] mm`，Z `[0, 65] mm`。
- G-code 行数：2932467。
- 运动段数：2906316。
- 正挤出段数：2887201。
- A 轴范围：`[0, 90] deg`。
- C 轴范围：`[-269.779998779, 66.4700012207] deg`。
- A/C 反算后范围：X `[-82.5005444472, 72.9222570451] mm`，Y `[-74.3317542853, 81.994274055] mm`，Z `[0.20000000298, 65] mm`。
- 选中并渲染的真实路径段数：2887201。
- A/C 正挤出段数：2603709。
- 长度过滤段数：0。

图像读取工具复核了真实像素尺寸和抽样非空情况：

- 普通 PNG/TIF：4080 × 2880，抽样非白像素比例约 0.336050，蓝色路径像素比例约 0.187516。
- 16K PNG/TIF：16320 × 11520，抽样非白像素比例约 0.336128，蓝色路径像素比例约 0.179630。
- 8K 局部 PNG/TIF：8192 × 6276，抽样非白像素比例约 0.683135，蓝色路径像素比例约 0.353996。
- 局部预览 PNG：1800 × 1380，抽样非白像素比例约 0.682907，蓝色路径像素比例约 0.354412。

目视复核显示，灰色模型本体仍可辨认，蓝色路径在可见表面和圆柱侧壁区域露出；背面路径没有形成整片穿透；局部放大图来自 16K 连续线版本裁剪，圆柱侧壁和顶部文字区域的线条保持连续。

## 输出产物

- `example/扇叶/render_outputs/model_real_gcode_toolpath.png`
- `example/扇叶/render_outputs/model_real_gcode_toolpath.tif`
- `example/扇叶/render_outputs/model_real_gcode_toolpath.fig`
- `example/扇叶/render_outputs/model_toolpath_stats.txt`
- `example/扇叶/render_outputs_16k_continuous/model_real_gcode_toolpath.png`
- `example/扇叶/render_outputs_16k_continuous/model_real_gcode_toolpath.tif`
- `example/扇叶/render_outputs_16k_continuous/model_real_gcode_toolpath.fig`
- `example/扇叶/render_outputs_16k_continuous/model_toolpath_stats.txt`
- `example/扇叶/render_outputs_8k_detail_continuous/model_real_gcode_detail_8k.png`
- `example/扇叶/render_outputs_8k_detail_continuous/model_real_gcode_detail_8k.tif`
- `example/扇叶/render_outputs_8k_detail_continuous/model_real_gcode_detail_preview.png`
- `example/扇叶/render_outputs_8k_detail_continuous/model_real_gcode_detail_8k_stats.txt`
- `example/扇叶/fan_blade_model_toolpath_run_stats.txt`

## 方法沉淀

这轮工作把论文效果图的依据链固定为四类文件：源 STEP/STP、源 G-code/NC、MATLAB 脚本和 stats。每次换模型时，需要同步核对文件时间戳、网格面数、运动段数、正挤出段数、A/C 范围、A/C 反算后 XYZ 范围、路径选择模式、路径微抬升量、连续拼接阈值和图像实际像素尺寸。

和只导出一张渲染图相比，本轮更值得保留的是可复核流程：STEP 网格化独立缓存，G-code 解析保留运动学口径，真实路径选择写入 stats，16K 全图作为局部裁剪母图，抽样像素检查和目视检查共同确认图像有效。后续论文插图可以沿用同一套脚本，只调整源文件、视角和局部裁剪框。

## 2026-07-10 V2 模型替换

用户指出源模型已更换为 `example/扇叶/风扇扇叶(1).STEP`。重新运行前核对文件状态：新 STEP 大小为 707751 字节，修改时间为 2026-07-08 17:52:56；G-code 仍为 `example/扇叶/风扇扇叶完整.gcode`，大小 186766355 字节，修改时间为 2026-07-09 10:40:05。上一轮 `render_outputs`、`render_outputs_16k_continuous` 和 `render_outputs_8k_detail_continuous` 已保留，本轮输出改写到 v2 目录。

主入口 `render_fan_blade_model_toolpath.m` 的默认配置已更新：

- `modelFile = '风扇扇叶(1).STEP'`
- `normalOutputDir = 'render_outputs_v2'`
- `full16kOutputDir = 'render_outputs_16k_continuous_v2'`
- `detailOutputDir = 'render_outputs_8k_detail_continuous_v2'`
- `summaryStatsFile = 'fan_blade_model_toolpath_v2_run_stats.txt'`

其余渲染口径保持不变：`legacy_full_positive` 选取全部 `deltaE > 0` 正挤出段，`maxRealSegmentsToRender = Inf`，`maxRenderedRealSegmentLength = Inf`，A/C 反算采用 `P_part = Rz(-C) * Rx(-A) * P_machine`，路径沿相机方向微抬升 0.18 mm，连续拼接阈值为 0.02 mm。

`matlab -batch "checkcode('render_fan_blade_model_toolpath.m'); checkcode('render_fan_blade_model_toolpath_engine.m')"` 无输出。正式运行 `matlab -batch "render_fan_blade_model_toolpath"` 已生成 v2 图像和统计文件；MATLAB 退出阶段仍打印本机环境中的 `Settings` 提示，产物写盘完整。

v2 关键统计如下：

- STEP/STL 网格：2623 个顶点，5230 个三角面。
- 模型包围盒：X `[-72.9207458496, 82.502571106] mm`，Y `[-81.9919433594, 74.3160705566] mm`，Z `[0, 65] mm`。
- G-code 行数：2932467。
- 运动段数：2906316。
- 正挤出段数：2887201。
- A 轴范围：`[0, 90] deg`。
- C 轴范围：`[-269.779998779, 66.4700012207] deg`。
- A/C 反算后范围：X `[-82.5005444472, 72.9222570451] mm`，Y `[-74.3317542853, 81.994274055] mm`，Z `[0.20000000298, 65] mm`。
- 选中并渲染的真实路径段数：2887201。
- A/C 正挤出段数：2603709。
- 长度过滤段数：0。

图像读取复核结果：

- 普通 PNG/TIF：4080 × 2880，抽样非白像素比例约 0.337428，蓝色路径像素比例约 0.186406。
- 16K PNG/TIF：16320 × 11520，抽样非白像素比例约 0.337538，蓝色路径像素比例约 0.178784。
- 8K 局部 PNG/TIF：8192 × 6276，抽样非白像素比例约 0.686134，蓝色路径像素比例约 0.352434。
- 局部预览 PNG：1800 × 1380，抽样非白像素比例约 0.685837，蓝色路径像素比例约 0.352843。

目视复核显示，新模型灰色实体可辨，蓝色路径仍按深度关系被模型遮挡，背面路径未形成整片穿透。局部预览来自 16K v2 连续线母图，圆柱侧壁、底部外圈和顶部字形区域的线条保持连续。

v2 产物如下：

- `example/扇叶/render_outputs_v2/model_real_gcode_toolpath.png`
- `example/扇叶/render_outputs_v2/model_real_gcode_toolpath.tif`
- `example/扇叶/render_outputs_v2/model_real_gcode_toolpath.fig`
- `example/扇叶/render_outputs_v2/model_toolpath_stats.txt`
- `example/扇叶/render_outputs_16k_continuous_v2/model_real_gcode_toolpath.png`
- `example/扇叶/render_outputs_16k_continuous_v2/model_real_gcode_toolpath.tif`
- `example/扇叶/render_outputs_16k_continuous_v2/model_real_gcode_toolpath.fig`
- `example/扇叶/render_outputs_16k_continuous_v2/model_toolpath_stats.txt`
- `example/扇叶/render_outputs_8k_detail_continuous_v2/model_real_gcode_detail_8k.png`
- `example/扇叶/render_outputs_8k_detail_continuous_v2/model_real_gcode_detail_8k.tif`
- `example/扇叶/render_outputs_8k_detail_continuous_v2/model_real_gcode_detail_preview.png`
- `example/扇叶/render_outputs_8k_detail_continuous_v2/model_real_gcode_detail_8k_stats.txt`
- `example/扇叶/fan_blade_model_toolpath_v2_run_stats.txt`

## 2026-07-10 叶片方位诊断

用户复核 v2 图后指出，中心顶面字母位置正确，三个叶片区域存在相对方位偏差，可能来自切片阶段的 X/Y 轴处理或局部 180° 旋转。该判断说明整条路径不能整体旋转，否则顶面字母会被破坏。本轮新增诊断脚本 `example/扇叶/render_fan_blade_alignment_trials.m`，从已核验的 v2 FIG 读取模型和路径，生成局部变换候选图；诊断图只用于判断方位关系，未覆盖正式 v2 输出。

第一组候选只变换蓝色路径中半径大于 24 mm 的外侧点，输出目录为 `example/扇叶/render_outputs_alignment_trials_v2`：

- `outer_rotate_180.png`
- `outer_swap_xy.png`
- `outer_swap_xy_rotate_180.png`

该组会把底部外圈也纳入变换，底部路径被移到错误位置。随后追加 `minZ = 20 mm` 条件，仅变换外侧且高 Z 的叶片路径，输出目录为 `example/扇叶/render_outputs_alignment_trials_v2_z20`。保留底部外圈后，蓝色叶片仍未稳定贴合灰色叶片，说明路径侧单一 X/Y 对调或 180° 旋转不足以解释全部偏差。

第二组候选保持蓝色路径和中心区域不动，只变换灰色 STEP 模型中半径大于 24 mm 的外侧网格，输出目录为 `example/扇叶/render_outputs_alignment_trials_v2_mesh`。外侧网格 180° 旋转后的图像比路径侧变换更接近，但叶根和叶尖仍有局部错位；X/Y 对调及 X/Y 对调后再 180° 的候选偏差更明显。

当前判断：中心字母对齐，叶片区域偏差集中出现，后处理阶段可以生成诊断图，但不宜把这些候选直接作为论文正式图。更稳妥的处理路径是回到切片源模型或切片坐标设置，确认叶片几何与顶面字形是否在同一坐标系下导入；重新导出 G-code 后再按原 `legacy_full_positive`、A/C 反算和 16K 裁剪流程生成正式图。

## 2026-07-10 叶片角度细扫

用户希望围绕上一轮结果逐步试角度。本轮新增 `example/扇叶/render_fan_blade_angle_sweep.m`，默认从 `render_outputs_v2/model_real_gcode_toolpath.fig` 读取已核验图像，保持中心顶面、字母路径和蓝色真实路径不动，只旋转半径大于 24 mm 的灰色外侧叶片网格。该脚本用于诊断叶片相对角度，未改动正式 v2 图。

扫描过程如下：

- `render_outputs_angle_sweep_v2_mesh_150_210_step5`：150° 到 210°，步长 5°，并生成 `contact_sheet_mesh_angle_150_210_step5.png`。
- `render_outputs_angle_sweep_v2_mesh_196_208_step2`：196° 到 208°，步长 2°，并生成 `contact_sheet_mesh_angle_196_208_step2.png`。
- `render_outputs_angle_sweep_v2_mesh_200_204_step1`：200° 到 204°，步长 1°，并生成 `contact_sheet_mesh_angle_200_204_step1.png`。
- `render_outputs_angle_sweep_v2_mesh_202_204_step0p5`：202° 到 204°，步长 0.5°，并生成 `contact_sheet_mesh_angle_202_204_step0p5.png`。
- `render_outputs_angle_sweep_v2_mesh_203_203p75_step0p25`：203° 到 203.75°，步长 0.25°，并生成 `contact_sheet_mesh_angle_203_203p75_step0p25.png`。

目视判断中，203° 到 203.5° 区间比 180°更接近；203.25°在右侧叶片外缘和下方叶片露出量之间较平衡。本轮另导出一张 600 DPI 单图：

- `example/扇叶/render_outputs_angle_candidate_v2_mesh_203p25/angle_p203p25deg.png`

该图可作为后续复核坐标方位的候选。若要进入论文正式图，仍应回到切片或模型导入环节确认叶片局部方位，再用真实 STEP 和真实 G-code 重新生成 16K 全图与 8K 局部图。

## 2026-07-10 叶片方位微调试验

用户提出继续小步试验后，本轮沿三个方向做诊断：角度、外圈半径阈值和旋转中心。所有试验均基于 `example/扇叶/render_outputs_v2/model_real_gcode_toolpath.fig`，只生成诊断图，不覆盖 v2 正式图、16K 全图或 8K 局部图。

角度微扫固定 `outerRadius = 24 mm`，保持中心 `[4.79091262817, -3.83793640137]` 不变，输出目录为 `example/扇叶/render_outputs_angle_sweep_v2_mesh_202p8_203p7_step0p1`。该组覆盖 202.80° 到 203.70°，步长 0.10°，并生成 `contact_sheet_mesh_angle_202p8_203p7_step0p1.png`。随后生成 600 DPI 细扫图，输出目录为 `example/扇叶/render_outputs_angle_sweep_v2_mesh_203p10_203p40_step0p05_r24`，覆盖 203.10° 到 203.40°，步长 0.05°，并生成两张对比图：

- `contact_sheet_mesh_angle_203p10_203p40_step0p05_r24.png`
- `detail_crop_sheet_angle_203p15_203p35_r24.png`

局部裁剪对比显示，203.20° 到 203.30° 的整体差别很小；203.25°在右侧叶片外缘、下方叶根和左上叶尖之间较均衡，203.35°以后右侧叶片灰边变厚。

半径阈值试验固定角度为 203.25°，输出 `render_outputs_angle_sweep_v2_mesh_203p25_radius_trials_contact_sheet.png`。`outerRadius = 20 mm` 和 `22 mm` 会牵动中心柱侧壁，字母附近露出不自然灰色断面；`26 mm` 和 `28 mm` 对叶根修正不足。`24 mm` 仍是当前较稳的外圈阈值。

旋转中心九宫格试验固定角度 203.25°、`outerRadius = 24 mm`，中心偏移量为 `dx, dy = {-1.5, 0, 1.5} mm`，输出 `render_outputs_center_trials_v2_mesh_203p25_r24_contact_sheet.png`。非零中心偏移会在中心柱附近产生灰色侧壁或破坏字母区域的观感，中心保持 `[4.79091262817, -3.83793640137]` 更合适。

Z 阈值试验固定角度 203.25°，组合 `outerRadius = 20, 22, 24 mm` 与 `minZ = 10, 15, 20, 25 mm`，输出 `render_outputs_z_trials_v2_mesh_203p25_contact_sheet.png`。提高 `minZ` 能减少低处侧壁被带动的概率，但 R=20 mm 和 R=22 mm 仍会影响中心附近区域；R=24 mm 与不限 Z 的结果接近，未形成更可靠的替代口径。

回看 `render_outputs_alignment_trials_v2_mesh` 中的 X/Y 对调候选，`outer_swap_xy.png` 和 `outer_swap_xy_rotate_180.png` 的三叶片相位更散。当前诊断结论保持不变：论文正式图不应直接采用 X/Y 对调方案；若只为做视觉校核，`outerRadius = 24 mm`、中心 `[4.79091262817, -3.83793640137]`、角度 203.25° 是本轮最稳的候选。

## 2026-07-10 临时产物清理

用户要求删除无用试验产物后，本轮清理了 38 个诊断目标，均位于 `example/扇叶` 目录内。清理对象包括粗角度扫描、X/Y 对调候选、半径阈值候选、旋转中心九宫格、Z 阈值组合以及这些试验对应的拼图文件。

保留内容如下：

- v2 正式论文图目录：`render_outputs_v2`、`render_outputs_16k_continuous_v2`、`render_outputs_8k_detail_continuous_v2`。
- 上一版正式输出目录：`render_outputs`、`render_outputs_16k_continuous`、`render_outputs_8k_detail_continuous`，未在本轮删除。
- 当前最有用的诊断候选：`render_outputs_angle_candidate_v2_mesh_203p25`。
- 细扫复核目录：`render_outputs_angle_sweep_v2_mesh_203p10_203p40_step0p05_r24`。

清理前已做路径保护检查，所有待删除路径均解析到 `F:\【项目和任务】\5AxisSclicer_V2.0\example\扇叶` 下。清理后复核显示，`angle_p203p25deg.png`、细扫局部拼图、v2 普通图、v2 16K 全图和 v2 8K 局部图仍存在。

## 2026-07-10 三片扇叶路径 180° 诊断

用户根据截图标注要求，将三片扇叶区域的蓝色路径旋转 180° 查看效果。本轮只变换路径侧外圈点，灰色 STEP 模型、中心顶面字母和底部圆柱路径保持原位置。诊断参数如下：

- 源图：`example/扇叶/render_outputs_v2/model_real_gcode_toolpath.fig`。
- 目标：`targetMode = path`。
- 旋转中心：`[4.79091262817, -3.83793640137]`。
- 外圈阈值：`outerRadius = 24 mm`。
- 高度阈值：`minZ = 20 mm`。
- 变换：外侧扇叶路径绕中心旋转 180°。
- 变换路径点数：2485165。
- 导出分辨率：4080 × 2880，600 DPI。

输出目录为 `example/扇叶/render_outputs_path_blades_rotate180_v2`，保留文件如下：

- `outer_rotate_180.png`
- `outer_rotate_180.tif`
- `compare_original_vs_path_rotate180.png`
- `alignment_trial_stats.txt`

为了保持目录干净，脚本顺手生成的 X/Y 对调候选已经删除，stats 也只保留 180° 路径旋转记录。并排图显示，三片扇叶路径被换到对侧，中心字母和底部圆柱路径没有发生整体旋转。

## 2026-07-10 扇叶路径 180° 后 XY 平移诊断

用户复核 180° 旋转路径图后判断，扇叶路径角度接近，但 XY 平面位置存在整体偏移。本轮新增 `example/扇叶/render_fan_blade_path_shift_trials.m`，在三片扇叶路径旋转 180° 后追加统一 XY 平移；灰色模型、顶面字母和底部圆柱路径不参与平移。

沿用的选择条件如下：

- 源图：`example/扇叶/render_outputs_v2/model_real_gcode_toolpath.fig`。
- 旋转中心：`[4.79091262817, -3.83793640137]`。
- 外圈阈值：`outerRadius = 24 mm`。
- 高度阈值：`minZ = 20 mm`。
- 基础旋转：180°。

运行前用 FIG 中的外侧高 Z 路径点和模型网格点做质心估算。路径旋转 180° 后的外侧点质心约为 `[10.2399586483, -7.9579555221] mm`，模型外侧网格质心约为 `[-0.817370088889, 0.575195793511] mm`，对应平移估计约为 `[-11.0573287372, 8.53315131561] mm`。该估算只作为试验中心，最终仍按图像贴合关系判断。

粗扫输出目录为 `example/扇叶/render_outputs_path_blades_rotate180_shift_trials_v2`，覆盖 `dx = -19, -11, -3 mm` 与 `dy = 0.5, 8.5, 16.5 mm`，并保留无平移的 180° 对照图。拼图文件为：

- `contact_sheet_rotate180_shift_trials.png`

细扫输出目录为 `example/扇叶/render_outputs_path_blades_rotate180_shift_fine_v2`，覆盖 `dx = -14, -11, -8 mm` 与 `dy = 5.5, 8.5, 11.5 mm`。拼图和候选对比图为：

- `contact_sheet_rotate180_shift_fine.png`
- `compare_rotate180_shift_candidates.png`

当前观察：`dx = -14 mm, dy = +8.5 mm` 和 `dx = -11 mm, dy = +8.5 mm` 是这一轮更接近的候选。`dx = -14 mm, dy = +8.5 mm` 的叶根位置略收，`dx = -11 mm, dy = +8.5 mm` 的外缘覆盖更饱满。该诊断仍属于基于 FIG 的局部图像变换，未改写正式 v2 输出。

## 2026-07-10 角点微调与线条化显示

用户根据局部截图指出，当前版本的整体角度接近，但需要继续观察几个叶片角点，同时要求表面路径不要呈现大块蓝色，改为能辨认路径线的显示方式。本轮扩展 `example/扇叶/render_fan_blade_path_shift_trials.m`，新增参数：

- `trialList`：按 `[rotationDeg, dx, dy]` 同时控制旋转角和平移量。
- `pathLineWidth`：控制路径线宽。
- `pathColor`：降低蓝色饱和感。
- `bladePathStride`：保留每隔若干条扇叶路径的稀疏显示入口。

先试验 `bladePathStride = 10` 和 `bladePathStride = 3`，结果显示按断点稀疏会让三片叶片路径保留不均匀。随后采用不删路径、压低线宽和降低蓝色饱和度的方式。当前微调图使用：

- `bladePathStride = 1`
- `pathLineWidth = 0.025`
- `pathColor = [0.05, 0.28, 0.82]`
- `resolutionDPI = 450`

第一组角点微调输出目录为 `example/扇叶/render_outputs_path_blades_corner_micro_v2`，覆盖 `rotationDeg = 179.2, 180.0, 180.8`，并联动试验 `dx, dy` 组合。拼图为：

- `contact_sheet_corner_micro.png`

目视结果显示，180.8° 一排的右上叶片灰色边缘露出更明显，179.2° 一排部分叶根略偏。第二组缩小到 `rotationDeg = 179.6, 180.0, 180.4`，固定 `dy = +8.5 mm`，并将 `dx` 调整为 `-14.5, -14.0, -13.5 mm`。输出目录为 `example/扇叶/render_outputs_path_blades_corner_micro2_v2`，拼图和候选对比图为：

- `contact_sheet_corner_micro2.png`
- `compare_best_179p6_vs_180p0.png`

当前判断：`rotationDeg = 179.6°`、`dx = -14.0 mm`、`dy = +8.5 mm` 是这一轮较均衡的候选；`rotationDeg = 180.0°`、`dx = -14.0 mm`、`dy = +8.5 mm` 也接近，但右上角和左侧叶片内缘的灰色露出略多。该轮仍为 FIG 层面的诊断图，未修改正式 v2 输出。

## 2026-07-10 手动调整入口

为便于用户手动调整扇叶路径位置，本轮新增 `example/扇叶/render_fan_blade_manual_adjust.m`。该脚本只保留常用参数入口，复杂的路径选择、旋转和平移逻辑仍由 `render_fan_blade_path_shift_trials.m` 执行。

用户主要修改脚本顶部三项：

- `rotationDeg`：三片扇叶路径旋转角，单位为 deg。
- `shiftXmm`：三片扇叶路径在 X 方向的整体平移量，单位为 mm。
- `shiftYmm`：三片扇叶路径在 Y 方向的整体平移量，单位为 mm。

默认参数为 `rotationDeg = 179.6`、`shiftXmm = -14.0`、`shiftYmm = 8.5`。默认输出目录为 `example/扇叶/render_outputs_manual_adjust`。本轮试跑生成 `rotp179p6_dxm014p0_dyp008p5.png`，图像尺寸为 3060 × 2160，抽样检查非空。

## 2026-07-10 新 G-code 预览与旧产物清理

用户提供新路径文件 `example/扇叶/风扇扇叶完整新.gcode` 后，要求删除旧渲染产物并直接查看新路径。执行前核对源文件状态：`风扇扇叶完整新.gcode` 大小为 186891627 字节，修改时间为 2026-07-10 16:26:43；模型仍为 `风扇扇叶(1).STEP`，大小为 707751 字节，修改时间为 2026-07-08 17:52:56。

本轮清理了当前扇叶目录下 20 个旧输出目标，包括所有旧 `render_outputs*` 目录和旧 run stats 文本。源 STEP、源 G-code、MATLAB 脚本和复盘文档未删除。清理后只保留新路径预览输出目录：

- `example/扇叶/render_outputs_new_gcode_preview`

新增入口 `example/扇叶/render_fan_blade_new_gcode_preview.m`。该入口自动选取当前目录最新的 `.gcode` 文件，避免 MATLAB 命令行中文路径转码问题。预览采用新 G-code、`legacy_full_positive`、A/C 反算 `RzMinusC_after_RxMinusA`、路径微抬升 0.18 mm、连续拼接阈值 0.02 mm。为了减少蓝色块状遮盖，本轮预览使用 `pathLineWidth = 0.025` 和 `pathColor = [0.05, 0.28, 0.82]`。

输出文件如下：

- `render_outputs_new_gcode_preview/model_real_gcode_toolpath.png`
- `render_outputs_new_gcode_preview/model_real_gcode_toolpath.tif`
- `render_outputs_new_gcode_preview/model_real_gcode_toolpath.fig`
- `render_outputs_new_gcode_preview/model_toolpath_stats.txt`

新 G-code 关键统计：G-code 行数 2936410，运动段数 2910683，正挤出段数 2890849，A 轴范围 `[0, 90] deg`，C 轴范围 `[-269.779998779, 66.4700012207] deg`，A/C 反算后 X/Y/Z 范围分别为 `[-82.5005444472, 72.9222570451] mm`、`[-74.3317542853, 81.994274055] mm`、`[0.20000000298, 65] mm`。解析耗时约 265.84 s。

图像读取复核：PNG/TIF 均为 4080 × 2880，抽样非白像素比例约 0.3333，蓝色路径像素比例约 0.1597。目视检查显示，新路径已经回到模型原始坐标口径上，三片扇叶路径与中心字母未再使用此前的手动 180° 平移诊断。

## 2026-07-10 新 G-code 与模型整体 180° 旋转预览

用户判断新路径图中灰色模型整体绕 Z 轴旋转 180° 后可能接近目标。新增入口 `example/扇叶/render_fan_blade_new_gcode_model_rot180_preview.m`，继续使用 `风扇扇叶完整新.gcode`，路径保持原始 A/C 反算结果，只对 STEP 模型网格应用 `modelAlignmentRotationZDeg = 180`。旋转中心采用模型包围盒中心，stats 中记录为 `[4.79091262817, -3.83793640137]`。

输出目录为 `example/扇叶/render_outputs_new_gcode_model_rot180_preview`，主要文件如下：

- `model_real_gcode_toolpath.png`
- `model_real_gcode_toolpath.tif`
- `model_real_gcode_toolpath.fig`
- `model_toolpath_stats.txt`
- `compare_model_original_vs_rot180.png`

图像读取复核：PNG/TIF 均为 4080 × 2880，抽样非白像素比例约 0.2931，蓝色路径像素比例约 0.1533。stats 明确记录 `model_alignment_rotation_z_deg = 180`，新 G-code 行数、运动段数、正挤出段数与上一版新路径预览一致。MATLAB 退出阶段仍打印本机 `Settings` 提示，图像和统计文件已完整写盘。

## 2026-07-10 模型绕中间圆柱中心 180° 旋转

用户指出上一版模型旋转使用的是包围盒中心，受叶片外形影响，旋转中心偏离中间圆柱。按用户判断，本轮将模型旋转中心改为 `[0, 0]`，继续只旋转 STEP 模型网格，新 G-code 路径保持原始 A/C 反算结果。入口 `example/扇叶/render_fan_blade_new_gcode_model_rot180_preview.m` 已更新为：

- `modelAlignmentRotationZDeg = 180`
- `modelAlignmentRotationCenterXY = [0, 0]`
- `outputDir = 'render_outputs_new_gcode_model_rot180_center00_preview'`

新输出目录为 `example/扇叶/render_outputs_new_gcode_model_rot180_center00_preview`。主要文件如下：

- `model_real_gcode_toolpath.png`
- `model_real_gcode_toolpath.tif`
- `model_real_gcode_toolpath.fig`
- `model_toolpath_stats.txt`
- `compare_model_original_vs_rot180_center00.png`

stats 记录 `model_alignment_rotation_center_xy_config = [0, 0]`，`model_alignment_rotation_center_xy_used = [0, 0]`。图像读取复核：PNG/TIF 均为 4080 × 2880，抽样非白像素比例约 0.2681，蓝色路径像素比例约 0.2131。上一版绕包围盒中心的目录 `render_outputs_new_gcode_model_rot180_preview` 已删除，避免与本轮结果混淆。

## 2026-07-10 模型绕 `[0,0]` 旋转版本 16K 输出

用户要求将当前确认的图生成 16K 高清图片。本轮新增入口 `example/扇叶/render_fan_blade_new_gcode_model_rot180_center00_16k.m`，沿用新 G-code、模型绕 `[0,0]` 旋转 180°、`legacy_full_positive` 路径选择、A/C 反算 `RzMinusC_after_RxMinusA`、路径微抬升 0.18 mm 和连续拼接阈值 0.02 mm。输出目录为：

- `example/扇叶/render_outputs_new_gcode_model_rot180_center00_16k`

输出文件如下：

- `model_real_gcode_toolpath.png`
- `model_real_gcode_toolpath.tif`
- `model_real_gcode_toolpath.fig`
- `model_real_gcode_toolpath_preview_1800.png`
- `model_toolpath_stats.txt`

16K 图像读取复核：PNG 和 TIF 的真实像素尺寸均为 16320 × 11520。抽样非白像素比例约 0.2665，蓝色路径像素比例约 0.0645。stats 记录 `resolution_dpi = 2400`、`figure_inches = [6.8, 4.8]`、`model_alignment_rotation_z_deg = 180`、`model_alignment_rotation_center_xy_used = [0, 0]`。本轮解析新 G-code 2910683 个运动段，正挤出段数为 2890849，解析耗时约 171.23 s。

为便于快速查看 16K 内容，另从 PNG 生成 `model_real_gcode_toolpath_preview_1800.png`，预览尺寸为 1800 × 1271。预览仅用于目视确认，正式插图以 16K PNG/TIF 为准。

## 2026-07-10 右侧叶片路径局部 16K 放大图

用户在截图中标出右侧叶片内凹边与下缘附近区域，用于论文正文展示局部路径细节。本轮没有重新改变 MATLAB 渲染口径，直接从已经核验的 16K 连续线母图裁剪，母图为 `example/扇叶/render_outputs_new_gcode_model_rot180_center00_16k/model_real_gcode_toolpath.png`，尺寸为 16320 × 11520。源 STEP 文件仍为 `风扇扇叶(1).STEP`，大小 707751 字节，修改时间 2026-07-08 17:52:56；源 G-code 文件仍为 `风扇扇叶完整新.gcode`，大小 186891627 字节，修改时间 2026-07-10 16:26:43。

局部裁剪框按 16K 母图像素坐标记录为 `(left, top, right, bottom) = (10800, 4700, 16050, 7600)`，原始裁剪尺寸为 5250 × 2900。为了满足局部放大插图的分辨率要求，将该裁剪区域按原比例放大到长边 16320 px，放大后尺寸为 16320 × 9015，重采样方法为 LANCZOS。该处理保留母图中的路径选择、遮挡关系、线条颜色和连续 polyline 风格；局部图未添加文字、坐标轴、图例、色条或网格线。

输出目录为 `example/扇叶/render_outputs_new_gcode_model_rot180_center00_detail16k`，正式产物如下：

- `detail_right_blade_path_16k.png`：16320 × 9015，大小 71166832 字节。
- `detail_right_blade_path_16k.tif`：16320 × 9015，大小 119147770 字节。
- `detail_right_blade_path_native_crop.png`：5250 × 2900，大小 3669918 字节。
- `detail_right_blade_path_native_crop.tif`：5250 × 2900，大小 7416656 字节。
- `detail_right_blade_path_16k_preview_2200.png`：2200 × 1215，供快速目视检查使用。
- `detail_right_blade_path_16k_stats.txt`：记录源文件、裁剪框、放大比例、输出尺寸和抽样检查结果。

图像读取复核显示，PNG 与 TIF 的真实像素尺寸均为 16320 × 9015。抽样检查得到非白像素比例约 0.3716，蓝色路径像素比例约 0.3146，图像内容非空。目视检查显示，右侧叶片内凹边、下缘轮廓和表面路径线连续可辨，背面路径未出现整体穿透，局部放大图保持了 16K 母图的灰色模型与蓝色路径叠加关系。
