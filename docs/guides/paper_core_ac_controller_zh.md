# 自有 AC 控制器离线后处理指南

`builtin.controller.own_ac.offline.v1` 是论文核心版本的审查方言。它绑定 `builtin.machine.own_ac_fdm.v1`，固定长度为 mm、回转轴为 deg，并使用：

- `G90`：机床轴绝对模式；
- `M83`：挤出机相对 E；
- `G94`：每分钟进给；
- `G92 E0`：建立明确挤出原点；
- 结束前恢复 `G90/M83/G94`，再发 `M400` 和 `M2`。

每个点前都有可回读的 `PAC POINT` 标记，材料事件有 `PAC EVENT` 和 JSON 上下文。回读器逐项比较完整命令流、点顺序、控制器轴字、F、相对 E、材料/通道和事件顺序。插入额外命令、把 M83 改成 M82、篡改 E/F/轴值、互换两种 Z20 动作或破坏 footer 都会失败。

## 资格判断

离线 profile 仍缺少：

- 控制器/固件版本；
- T0—T3 与切刀/恢复宏版本和文件哈希；
- 协调 XYZAC 能力确认；
- 机床累计 C 允许值。

因此 `machine_executable=false`。已知 A±180°、C±360°仍会参与单点轴限检查；实际累计 C 运动量和跨度写入 qualification。没有累计上限时产生 `controller.cumulative_c_limit_unknown` Warning；配置已知上限后，超限产生 Error。

## 本轮样例

pipe2 的当前 Tube 产品有 1,591 个点，现有离线后处理和自有 AC 后处理均严格回读通过。Indexed 的 `index_start` 中可见绝对 `Z=20 mm`。材料切换的相对 `Z+20 mm` 在多材料 Freeform 案例中验证。四个 Freeform/Tube 项目和五类产品都保存在[论文核心 AC 证据目录](../reviews/evidence/2026-09-13_paper_core_ac/validation_manifest.json)。

这些结果不能直接下发机床。取得实机资格前还需冻结控制器与宏版本、回转中心/零偏/轴方向、工具与夹具扫掠、速度/加速度、传感器协议，并完成现场空运行、碰撞检查和试切。
