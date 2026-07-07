# 2026-07-07 扇叶 G-code MATLAB 路径作图复盘

## 目标

本轮任务是把 `example/叶轮/render_gcode_complete_path_matlab.m` 的路径渲染逻辑迁移到 `example/扇叶/pic.m`。动手前确认 `pic.m` 时间戳为 2026-07-06 14:25:46，大小为 0 字节；扇叶 G-code 时间戳为 2026-06-13 18:36:40，大小为 219589182 字节。

## 依据

- 扇叶 G-code 头部来自 OrcaSlicer 2.4.0-alpha，使用 `G90`、`G21` 和 `M83`，默认按相对挤出处理。
- `rg` 抽查显示第 91622 行后出现 `A90` 与连续变化的 `C` 轴字段，尾段仍保留 `A90 C...` 的五轴姿态数据。
- 隔壁叶轮脚本已经沉淀出较稳定的分层：G-code 解析、C 轴展开坐标、AC 反算三维坐标、二维和三维渲染、统计文件写出。沿用这条链路能减少重新实现解析器带来的偏差。

## 实现判断

扇叶文件前段含普通 Orca 路径，后段进入 A/C 轴姿态。脚本保留三类视图：C 轴展开俯视图用于观察旋转展开后的口径；原始机床 XY 图用于对照 G-code 坐标；AC 反算三维图用于恢复工件坐标中的扇叶空间形态。默认反算顺序沿用叶轮复盘中确认过的 `P_part = Rz(-C) * Rx(-A) * P_machine`。

`pic.m` 采用函数入口，用户直接运行 `pic` 即可默认读取当前目录体积最大的 G-code。新增 `maxLines`、`maxSegments` 和 `outputPrefix` 配置，主要服务调试与复核；默认值仍面向全量作图。解析器继续支持 `G90/G91`、`M82/M83`、`G20/G21`、`G92` 和大小写混合轴字段，兼容扇叶尾段里小写 `z` 与缺少数值的 `F` 字段。

## 验证

- `matlab -batch "checkcode('pic.m')"` 无 MATLAB Code Analyzer 输出。
- 快速抽查使用真实 G-code 前 100000 行，解析 72447 个运动段，其中正挤出段 52289 个；A 轴范围为 0 到 90 deg，C 轴范围为 -177.65 到 0 deg。
- 全量运行 `matlab -batch "pic"`，解析 3703597 行和 3675992 个运动段，正挤出段 3655222 个；A 轴范围为 0 到 90 deg，C 轴范围为 -179.94 到 152.77 deg。
- 正式输出文件已生成：`fan_blade_toolpath_c_unwrapped_top_matlab.png`、`fan_blade_toolpath_machine_xy_matlab.png`、`fan_blade_toolpath_ac_inverse_3d_matlab.fig`、`fan_blade_toolpath_ac_inverse_3d_matlab.png`、`fan_blade_toolpath_render_stats_matlab.txt`。
- PNG 抽样检查显示三张正式图均有非白像素：C 展开图 66/625，AC 三维图 107/625，机床 XY 图 135/625。

MATLAB 批处理退出阶段仍输出 `函数或变量 'Settings' 无法识别`。同一提示已在叶轮复盘中出现；本轮文件保存、统计写出和图片抽样均已完成，判断它属于本机 MATLAB 退出环境提示。

## 方法沉淀

五轴 G-code 后处理脚本应把解析语义、坐标口径和渲染产物拆开维护。解析器只负责把运动段、挤出量和轴角度写成数组；坐标变换函数显式命名 C 展开与 AC 反算；渲染函数只处理线段、颜色、视角和导出格式。这个结构便于后续接入机床配置，也方便把 MATLAB 产物与 Python/VTK 预览互相校验。

本轮值得保留的差异化做法是用真实扇叶 G-code 完成全量跑通，并把边界、段数、输出文件路径写进统计文件。后续换模型时，不应只看一张图是否好看，还要核对轴角范围、正挤出段数、坐标边界和图片非空抽样；这些数字能快速定位解析模式、旋转顺序或文件截断问题。
