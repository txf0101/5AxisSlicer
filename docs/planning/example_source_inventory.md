# A02 样例来源登记

日期：2026-09-11。本文对应 `A02`，集中登记当前 `example` 目录中与首轮 Tube 和后续工作台相关的可见文件。未知项保持“未知”，不按目录整体推断来源。

## 首轮 Tube 样例

| 编号 | 文件 | SHA-256 | 用途 | 来源与限制 |
| --- | --- | --- | --- | --- |
| PIPE2-STEP | `example/pipe2/弯管新.stp` | `116e99fd43492bd1f4f519c80c93cd1f7cd0bf2cb6861b3e123148e4031a0d4b` | T01-T08 首例 CAD | 建模来源未知；当前只确认文件哈希和历史使用记录 |
| PIPE2-GCODE | `example/pipe2/弯管.gcode` | `4d6630c01f63d6f802ae6955752fa41b35abfea23509c661fcd855f7064ff70a` | NC 回读、历史轨迹观察 | 用户说明存在外部切片和人工拼接；不能作为新算法真值 |
| PIPE2-SETUP | `example/pipe2/tube_setup_coordinate_demo/manufacturing-setup.yaml` | `7b1551bb7824a35e5220f8a9bf96c45f091b5694d3482d248b805551f32d4e90` | Setup/YAML 回归 | B02-B03 已验证保存重开和脚本入口；T01 增加角色后需登记新哈希 |

## 相邻 Tube 参考

| 编号 | 文件 | SHA-256 | 用途 | 来源与限制 |
| --- | --- | --- | --- | --- |
| PIPE-STL | `example/pipe/pipe_fitting.stl` | `14046ec2666df2650caf143606a103b9fbdc108e0b09a12a7cc21031dada539e` | 观察历史管接头形状 | STL 不能提供精确 BRep 管面真值 |
| PIPE-GCODE | `example/pipe/pipe_fitting.gcode` | `468884cf5938bb06ef577ede23ee6a0a1213d09544a97788114873b782d5fd7c` | NC 观察 | 来源和人工修改范围未知 |
| PIPE40-STL | `example/pipe/pipe_fitting_40pct.stl` | `76247c7e5cee868541550cf477181743cbb90ea59ea26fab78a373446bc13ff7` | 观察缩放/变体 | STL 不能作为 STEP 拓扑识别真值 |
| PIPE40-GCODE | `example/pipe/pipe_fitting_40pct_recommended.gcode` | `9ef9fa04328d316872e4c8b2e6ae71c70807b7f70cba657cd4f4e33290b59260` | NC 观察 | 来源和控制器语义需另查 |

## 后续工作台参考

叶轮、扇叶、球形 NEU 校徽和三叶扇目录暂不进入 Tube 首轮验收。它们可以在 Curve、Freeform、Rotary 或 Research 任务中重新登记。使用前必须逐文件记录模型来源、G-code 来源、人工调整、控制器、单位、哈希和可比较指标。

## 独立解析真值

机器可读真值位于 `tests/fixtures/analytic_tube_truth.json`，SHA-256 为 `e3d02045c104aadfd86a54ca3f4089a2dd019d6bf737663e772ef9c97f1159e8`。直管由起点、轴向和长度定义；圆弧管由圆心、平面法向、中心线半径和 90° 扫掠角定义。预期端点、切向、恒定内外半径和中心线长度均由登记参数直接计算，且明确独立于历史 G-code。`tests/test_toolpath_contract.py` 会读取该文件并复核关键公式。

## 后续真值实体计划

1. T01：保存管体、入口、出口、基体和忽略体的稳定引用，验证保存重开。
2. T02：按已登记解析真值生成直管和圆弧管 STEP，登记实体哈希和测量误差。
3. T02：对 `PIPE2-STEP` 做独立拓扑测量，记录管体和底座区分依据。
4. T03-T05：建立分块、截交、偏置和连接段的正常及失败样例。
