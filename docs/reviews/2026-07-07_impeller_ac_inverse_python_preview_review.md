# 2026-07-07 叶轮 AC 反算 Python 预览复盘

## 问题定位

截图中的路径出现毛团和斜刺，根源是 Python/VTK 预览直接使用 G-code 里的机床 XYZ 坐标。叶轮后段 G-code 含连续 A/C 轴位，机床坐标需要反算回工件坐标后再叠加到 STEP 模型上。MATLAB 脚本 `example/叶轮/render_gcode_complete_path_matlab.m` 已经给出稳定口径：`P_part = Rz(-C) * Rx(-A) * P_machine`。

## 本轮修正

- 默认演示样例从扇叶切换为 `example/叶轮/叶轮.stp` 与 `example/叶轮/叶轮完整.gcode`。
- `gcode_preview.py` 为路径段同时保存工件坐标 `start/end` 和机床原始坐标 `machine_start/machine_end`。
- A/C 轴路径按 MATLAB 公式反算为工件坐标，summary 写入 `coordinate_transform = ac_inverse_rz_minus_c_after_rx_minus_a`。
- 预览面板显示坐标口径，路径段属性同时显示工件起止点和机床起止点。
- G-code 缓存 key 加入解析版本，避免旧 raw XYZ 缓存污染新预览。
- 纯 E 回抽和 prime 只进入 `move_counts`，不进入可见路径段统计；零长度空间轴行保留在路径段统计中，使 Python 口径与 MATLAB `movement_segments` 一致。
- 默认 GUI 预览优先显示正挤出路径，空走路径和五轴姿态抽样保留为可打开的检查项。
- 单元测试新增 AC 反算、纯 E 计数、零长度空间段、模态 `G1`、`G20/G92` 样例，防止后续改动退回旧口径。

## 验证记录

- `python -m compileall src tests scripts`：通过。
- `python -m unittest discover -s tests`：17 个测试通过。
- 真实解析 `example/叶轮/叶轮完整.gcode`：得到 1,011,023 个空间路径段，其中正挤出段 1,005,400 个，travel 或零长度空间段 5,623 个。
- Python AC 反算边界为 X `[-57.635, 57.635]`、Y `[-57.633, 57.633]`、Z `[0, 60.8469640175]`。
- MATLAB 统计文件记录的 AC 反算 Z 边界为 `[0, 60.8469640175]`，正挤出段同为 1,005,400 个。
- 纯 E 回抽 484 次、prime 483 次，保留在运动类型统计中，不进入 VTK 画线。

## 保留判断

后续五轴预览要持续区分机床轴位坐标和工件几何坐标。MATLAB 后处理、Python 解析和 VTK 显示应共享同一套旋转顺序命名；若后续加入 Machine Profile，需要把当前固定的 AC 反算顺序迁入机器配置，避免不同设备轴定义混用。

本轮沉淀的可复用方法是“三份证据互校”：MATLAB 统计文件给出成熟口径，Python 解析摘要复核段数与边界，GUI 冒烟截图确认渲染层没有偏离。这个链条比单看截图更稳，后续换叶轮、扇叶或管件样例时，可以快速定位问题属于文件选择、解析状态、旋转顺序还是渲染默认开关。
