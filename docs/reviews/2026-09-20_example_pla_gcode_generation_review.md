# 示例模型 PLA 五轴代码生成复盘

日期：2026-09-20。任务编号：EXAMPLE-PLA-01。本轮读取 `example/manuscript.docx`，按论文明确参数和当前软件的受限离线制造契约，为可由现有工作台可靠表达的示例生成单材料 PLA 五轴 G-code。输出只用于离线审查，没有取得真实控制器、机床标定、现场碰撞或试切资格。

## 模式判断

| 示例 | 推荐模式 | 本轮结果 |
| --- | --- | --- |
| 球形 NEU 校徽 | Freeform Surface，沿球面明确导引边贴面 | 已生成，7 条路径、30 点，严格回读通过 |
| 三叶扇 `Supportless_sample.stp` | 当前版本优先用 Planar Zigzag/Support 做固定姿态切片；若要求主动 A/C 无支撑分解，应等待 Research 支撑缩减/方向场能力 | 未生成五轴代码；现有工作台没有对整个实体自动分解并独立验收的五轴流程 |
| 扇叶 | Freeform Thin Wall；轮毂局部才适合 Rotary | 已生成，3 条路径、123 点，严格回读通过 |
| 叶轮 | Freeform Surface 有限面组；局部边链任务可用 Curve | 已生成，16 条路径、384 点，严格回读通过 |
| `pipe` STL | 几何上属于 Tube；当前 Tube 制造流程需要 STEP 的 body/入口/出口拓扑 | 未生成；STL 在该流程中不能提供稳定拓扑引用 |
| `pipe2` 弯管 STEP | Tube Indexed；需要连续中心线随动时可改用 Tube Continuous | 已生成 Indexed，43,775 点，严格回读通过 |

## 参数和输出

论文明确给出 0.4 mm 喷嘴、1.75 mm 丝材、AC 转台、A 轴 ±180°、C 轴 ±360°和计划性非沉积换姿前绝对 Z=20 mm。论文没有给出本轮所需的层高、道宽、PLA 温度和常规进给速度，因此采用 0.20 mm 层高、0.40 mm 道宽、205 ℃、沉积 1200 mm/min、空移 3000 mm/min和回抽 1.0 mm。所有案例只使用 T0/PLA。

生成文件位于模型旁：

- `example/球形NEU校徽/球形测试件_本软件五轴_PLA_20260920.gcode`
- `example/扇叶/风扇扇叶_本软件五轴_PLA_20260920.gcode`
- `example/叶轮/叶轮_本软件五轴_PLA_20260920.gcode`
- `example/pipe2/弯管新_本软件五轴_PLA_20260920.gcode`
- `example/本软件五轴PLA切片_20260920.json` 保存参数、点数、输出路径和 SHA-256。

四份代码均包含 `G90`、`M83`、`G94`、A/C 轴字和 `M109 S205`，并由当前自有 AC 离线后处理严格回读。状态均为 Warning，未把离线通过表述为可直接上机。

## 失败、取舍和局限

半球首次使用 0.45 mm 道宽和 1.0 mm 采样时触发 `curve.offset_outside_face`。改成与论文喷嘴同宽的 0.40 mm 后仍因加密采样触发同一拒绝；恢复该案例已验收的 3.0 mm 导引采样后生成通过。没有放宽修剪面容差，也没有改换未经验证的导引边。

三叶扇和 `pipe` 没有强行输出。三叶扇已有 Planar 离线资格，但该路径不会产生所要求的主动五轴 A/C 运动；`pipe` 只有 STL，缺少 Tube 所需的解析 body 和端口边。后续若提供 `pipe` STEP，可按 Tube 重新识别；三叶扇若要求真正无支撑五轴分区，需要先完成相应算法和独立真值验收。

## 使用的 Skills

- `five-axis-workbench-development`：模式边界、产品生成、严格回读、台账和复盘要求。
- `five-axis-slicer-validation`：使用已验证解释器和只读预检，按新增证据决定重试并停止无变化尝试。
- `documents`：只读提取论文 DOCX 中的参数和表格；未修改或交付 DOCX，因此不触发文档渲染门。
