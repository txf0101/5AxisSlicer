# 2026-07-06 G-code 三维预览重构复盘

## 本轮目标

本轮围绕 `example/叶轮/render_gcode_complete_path_matlab.m` 增加 MATLAB 三维预览输出。已有脚本能解析完整 G-code 并生成二维顶视图，本轮保留解析器和既有二维对照图，将渲染层拆成二维顶视图、C 轴展开三维预览和统计写出三块，减少后续改视角、线宽、输出格式时对解析逻辑的扰动。

## 关键判断

- 继续复用原有 G0/G1 解析链路，保留 G90/G91、M82/M83、G20/G21、G92、A/C/E/F 字段处理。叶轮文件约 102 万行，重新写解析器风险高，收益有限。
- 三维预览采用 C 轴反向展开后的 X/Y 与 Z 组合生成 `.fig`。这一做法和原二维 C 轴展开视图口径一致，便于和已有 PNG 对照。
- A 轴仍只进入解析和统计。当前脚本缺少机床运动学链参数，直接把 A 轴写进空间坐标会给出缺乏依据的几何结果。
- `.fig` 是目标产物，额外导出 PNG 快照用于快速检查。`.fig` 适合 MATLAB 内交互旋转，PNG 适合文件管理和沟通确认。

## 本轮改动

- 入口增加 `userConfig` 可选结构，原有 `render_gcode_complete_path_matlab('叶轮完整.gcode')` 调用方式保持可用。
- 新增 `defaultRenderConfig()` 和 `mergeConfig()`，集中管理画布尺寸、3D 视角、线宽、是否输出 3D PNG 等配置。
- 将原渲染函数改名为 `renderToolpath2DFigure()`，新增 `renderToolpath3DFigure()` 与 `plotSegments3D()`。
- 统计文件新增 3D 画布尺寸、输出开关、视角和 3D 文件路径，便于追踪一张图由哪组配置生成。
- `formatCount()` 改为预分配 cell，MATLAB `checkcode` 不再报增长数组提示。

## 验证记录

- `matlab -batch "checkcode('render_gcode_complete_path_matlab.m')"`：无代码分析器提示。
- 真实运行 `render_gcode_complete_path_matlab('叶轮完整.gcode')`：解析 1,021,062 行，得到 1,011,023 个运动段，其中正挤出段 1,005,400 个。
- 已生成 `gcode_complete_path_c_unwrapped_3d_matlab.fig`，文件大小 26,757,770 字节。
- 已生成 `gcode_complete_path_c_unwrapped_3d_matlab.png`，文件大小 7,872,518 字节。
- 用 MATLAB 反向打开 `.fig`，检测到 1 个 axes 和 146 个 line 对象。
- 对 3D PNG 做抽样像素检查，6,480 个采样点中 1,379 个为非白像素，并已人工查看图像内容。

## 可复用方法

大体量 G-code 预览应把解析、坐标口径、渲染、统计分开维护。解析器给出完整运动段数组；坐标口径负责把机床坐标或 C 轴展开坐标显式命名；渲染函数只关心线段、颜色、视角和输出文件；统计文件记录输入规模、坐标边界和生成产物。这个拆法能让后续增加按层过滤、抽稀预览、原始 XYZ 三维图或机床运动学变换时有稳定入口。

本轮的差异化沉淀在两点：一是保留全量 G-code 级验证证据，产物来自真实叶轮文件，样例规模接近实际加工预览；二是把 C 轴展开口径写入文件名、标题和统计文件，避免后续把它误读成完整五轴运动学仿真。

## 后续观察

- 当前 `.fig` 保存全量路径，文件体积约 25.5 MB，MATLAB 打开需要等待。若后续处理更大的 G-code，可增加显式抽稀配置，并在标题和统计文件中写明抽稀比例。
- MATLAB 批处理退出时会输出 `函数或变量 'Settings' 无法识别`。最小 `disp` 批处理也会出现同一提示，判断为本机 MATLAB 退出环境问题。本轮渲染、静态检查和 `.fig` 打开验证均已完成。
