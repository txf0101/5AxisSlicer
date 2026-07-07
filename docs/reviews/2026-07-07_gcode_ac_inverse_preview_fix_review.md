# 2026-07-07 G-code AC 反算三维预览修正复盘

## 本轮目标

本轮修正 `example/叶轮/render_gcode_complete_path_matlab.m` 的三维路径口径。上一轮 3D FIG 使用 C 轴反向展开后的 X/Y 和原始 Z，适合做顶视图代理；叶轮后段 G-code 含大量 A/C 轴位，完整三维预览需要把机床轴位反算回工件 XYZ。

## 依据和判断

- `圭臬/开发目标文档.docx` 更新时间为 2026-07-06 13:45，大小 492214 字节，文档包含 Machine Profile、ToolpathPoint、五轴姿态和五轴运动学开发顺序。
- 目标文档给出 `kinematics: xyz_plus_uv_rotary_bed`，当前叶轮样例使用 A/C 轴名。项目 `viewer.py` 已采用 A 或 U 绕 X、B 或 V 绕 Y、C 绕 Z 的姿态约定。
- 叶轮 G-code 中 A/C 轴从约第 146982 行进入连续变化段，A 范围为 0 到 90 deg，C 范围为 -344.1 到 135.56 deg，旋转轴字段覆盖 873916 行。三维预览继续忽略 A 会把路径几何压在错误的坐标口径上。
- 默认反算公式采用 `P_part = Rz(-C) * Rx(-A) * P_machine`。该公式在 A 为 0 时退化为原有 C 轴反向展开，和旧顶视图保持连续；对叶轮样例计算得到的重建 Z 范围为 0 到 60.846964 mm，未出现另一候选顺序带来的大段负 Z。

## 本轮改动

- 新增 `inverseRotaryACToXYZ()`，对路径段起点和终点做向量化 AC 反算。
- 新增 `acInverseOrder` 配置，默认值为 `RzMinusC_after_RxMinusA`，保留 `RxMinusA_after_RzMinusC` 作为可切换候选。
- 3D FIG 输出改名为 `gcode_complete_path_ac_inverse_3d_matlab.fig`，PNG 快照改名为 `gcode_complete_path_ac_inverse_3d_matlab.png`。
- 统计文件新增 AC 反算后的 X/Y/Z 边界、反算顺序和新输出路径。
- 原 C 展开顶视图和原始机床 X/Y 顶视图保留，作为坐标口径对照。

## 验证记录

- `matlab -batch "checkcode('render_gcode_complete_path_matlab.m')"`：无代码分析器提示。
- 真实运行 `render_gcode_complete_path_matlab('叶轮完整.gcode')`：解析 1,021,062 行，生成 1,011,023 个运动段，正挤出段 1,005,400 个。
- 已生成 `gcode_complete_path_ac_inverse_3d_matlab.fig`，文件大小 31,561,188 字节。
- 已生成 `gcode_complete_path_ac_inverse_3d_matlab.png`，文件大小 6,262,812 字节。
- MATLAB 反向打开 FIG，检测到 1 个 axes 和 116 个 line 对象。
- 3D PNG 抽样 6,400 个像素点，其中 1,200 个为非白像素，并已人工查看图像。

## 可复用方法

五轴路径预览需要把“机床轴位坐标”和“工件几何坐标”分开命名。二维 C 展开可以保留为诊断视图；三维工件预览应记录完整旋转矩阵顺序、轴正方向和重建边界。后续如果接入正式 Machine Profile，应把 `acInverseOrder` 从脚本配置迁移到机器配置，并让 MATLAB 后处理、Python 预览和 VTK 姿态抽样共享同一套运动学定义。

## 遗留观察

- 旧的 `gcode_complete_path_c_unwrapped_3d_matlab.fig/png` 仍留在样例目录中，时间戳为 2026-07-06，属于上一版 C 展开三维图。新产物使用 `ac_inverse_3d` 文件名。
- MATLAB 批处理退出时仍会输出 `函数或变量 'Settings' 无法识别`。最小 `disp` 批处理也能复现，判断来自本机 MATLAB 退出环境；本轮静态检查、真实渲染和 FIG 打开验证均已完成。
