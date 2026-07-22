# 2026-07-09 扇叶 G-code 重出图复盘

## 本轮对象

本轮任务针对 `example/扇叶/风扇扇叶完整.gcode` 重新生成扇叶路径图。动手前核对到该 G-code 的修改时间为 2026-07-09 10:40:05，晚于目录内 2026-07-07 20:04 前后的旧图产物，重跑判断成立。

相关依据来自本地文件和既有复盘：`example/扇叶/pic.m`、`example/扇叶/fan_blade_toolpath_render_stats_matlab.txt`、`docs/reviews/2026-07-07_fan_blade_matlab_toolpath_review.md`。脚本入口仍为 `pic`，默认读取当前目录体积最大的 G-code，并输出 C 轴展开顶视图、AC 反算三维图、机床 XY 图和统计文件。

## 执行记录

MATLAB 版本为 R2021b。`matlab -batch "checkcode('pic.m')"` 未输出代码分析器告警。随后运行 `matlab -batch "pic"` 完成全量解析和渲染，解析耗时 261.16 s，主图产物均写回 2026-07-09 10:50 左右。

MATLAB 批处理退出阶段仍出现 `函数或变量 'Settings' 无法识别` 提示。该现象已在 2026-07-07 复盘中记录为本机 MATLAB 退出环境提示；本轮文件保存、统计写入、PNG 抽样检查均已完成，未观察到图像生成中断。

目录中原有 `fan_blade_toolpath_ac_inverse_3d_light_matlab.fig/png` 仍停留在 2026-07-07。为避免轻量图和主图对应不同 G-code，本轮从新生成的完整 3D FIG 中按线段保持颜色抽稀，保留 290849 / 2906316 个三维渲染段，重新写出轻量 FIG 与 PNG。

## 结果

新统计文件记录如下：

- `line_count = 2932467`
- `movement_segments = 2906316`
- `print_segments_positive_E = 2887201`
- `travel_or_nonextrude_segments = 19115`
- `G0_segments = 3`
- `G1_segments = 2906313`
- `arc_motion_lines_total = 0`
- `total_positive_E = 17626.5861304`
- `machine_x_bounds_mm = [-20.2719993591, 20.2719993591]`
- `machine_y_bounds_mm = [-58.8400001526, 20.2719993591]`
- `machine_z_bounds_mm = [0, 93.1999969482]`
- `A_bounds_deg = [0, 90]`
- `C_bounds_deg = [-269.779998779, 66.4700012207]`
- `ac_inverse_x_bounds_mm = [-88.5869071864, 72.9222570451]`
- `ac_inverse_y_bounds_mm = [-74.3317542853, 91.1957426233]`
- `ac_inverse_z_bounds_mm = [0, 65.4000015259]`

和 2026-07-07 旧统计相比，这版 G-code 的运动段数从约 398 万降至约 291 万，G2/G3 圆弧命令从 26475 条降为 0，C 轴范围也发生明显变化。图像判断不能沿用旧版圆弧离散口径，应以本轮统计文件作为新基线。

## 产物检查

本轮重写的文件：

- `example/扇叶/fan_blade_toolpath_c_unwrapped_top_matlab.png`
- `example/扇叶/fan_blade_toolpath_ac_inverse_3d_matlab.fig`
- `example/扇叶/fan_blade_toolpath_ac_inverse_3d_matlab.png`
- `example/扇叶/fan_blade_toolpath_machine_xy_matlab.png`
- `example/扇叶/fan_blade_toolpath_render_stats_matlab.txt`
- `example/扇叶/fan_blade_toolpath_ac_inverse_3d_light_matlab.fig`
- `example/扇叶/fan_blade_toolpath_ac_inverse_3d_light_matlab.png`

PNG 抽样采用 25 x 25 网格检查非白像素：

- C 轴展开顶视图：4013 x 3756，63 / 625
- AC 反算三维图：5558 x 3607，82 / 625
- AC 反算轻量三维图：2215 x 1427，72 / 625
- 机床 XY 图：2299 x 3756，98 / 625

这些检查覆盖了文件重写、尺寸、非空渲染和轻量图同步四个环节，符合可追溯出图的工程口径。

## 方法沉淀

本轮价值点集中在可核对的统计锚点，而非只看 PNG 是否打开。后续每次更换 G-code，应固定执行时间戳核对、`checkcode`、全量 `pic`、统计文件对照、PNG 非白像素抽样。若目录内存在派生轻量图，也要随主 FIG 同步重建或明确标为历史文件。

这套流程的壁垒来自真实大文件、五轴姿态、AC 反算边界、图像产物和统计文本的闭环。单纯调用绘图脚本容易遗漏旧轻量图、路径范围变化或圆弧命令口径变化；把这些数字落到复盘文档后，后续论文图、GUI 预览和 MATLAB 后处理可以共用同一组事实锚点。
