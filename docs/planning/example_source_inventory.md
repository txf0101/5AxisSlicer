# A02 样例来源登记

更新至：2026-09-12。本文对应 `A02`，集中登记当前 `example` 目录中与首轮 Tube 和后续工作台相关的可见文件。未知项保持“未知”，不按目录整体推断来源。

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

扇叶、球形 NEU 校徽和三叶扇目录暂不进入当前阶段验收。它们可以在 Freeform、Rotary 或 Research 任务中重新登记。使用前必须逐文件记录模型来源、G-code 来源、人工调整、控制器、单位、哈希和可比较指标。

## Curve C01—C05 样例

| 编号 | 文件 | SHA-256 | 用途 | 来源与限制 |
| --- | --- | --- | --- | --- |
| CURVE-IMPELLER | `example/叶轮/叶轮.stp` | `3776fe6e1c384e03a7dab20e7ab8d8028210b86ec7c2ced3d3518a8011fdf21f` | 真实 STEP 样条、圆弧、邻面法向和三操作六件套 | 作者、建模工具、原许可证及允许再分发状态未知；文件声明 mm；只用于当前仓库本地验收，仓库许可证不自动覆盖该 CAD |
| CURVE-RECTANGLE | `docs/reviews/evidence/2026-09-12_project_audit/frozen_cases/analytic/rectangle_8x6x1.step` | `02e6adf319958391e8d74a1ef32fa4c22a0d1e32025a92701ad91e0ad39f8518` | 8 mm 直线、双邻面、断链、trimmed face 偏置成功/失败 | 本项目使用 CadQuery 2.7.0 生成的解析长方体；生成器记录位于同一审查证据目录；CadQuery 为 Apache-2.0 工具依赖，STEP 数值真值由尺寸独立定义 |

CURVE-IMPELLER 固定对象只对上述 SHA 有效。`body_001_edge_0005` 为半径 40 mm、圆心 `(-52,0,42)`、圆心角 π/2 的解析圆弧，长度 `62.83185307179585 mm`；`body_002_edge_0011` 为真实非圆样条，OCCT 精确长度 `68.27612913311773 mm`，100000 段独立弦长为 `68.276129132436 mm`。该样条在 `body_002_face_0006` 上做 3.0 mm Offset 时必须明确反向，实测相邻道三维点距为 2.947—3.000 mm；正向投影塌回修剪边界并应拒绝。项目保存完整描述符和 kernel signature，不只保存遍历 ID。

## Rotary R01—R05 样例

| 编号 | 文件 | SHA-256 | 用途 | 来源与限制 |
| --- | --- | --- | --- | --- |
| ROTARY-CYLINDER | `docs/reviews/evidence/2026-09-13_rotary_workbench_final/inputs/rotary_cylinder_nonzero_center.step` | `e2804dcf8db30e0d829f2ae5b7a711ab436089d40187426dcbe88afd5fea80d0` | 非零中心圆柱 Spiral、Thin Wall、跨零点 Around Part 与六件套 | 本项目使用 CadQuery 2.7.0 生成；圆心、半径和轴长由生成器显式定义；只用于 Generic XYZAC 离线资格 |
| ROTARY-CONE | `docs/reviews/evidence/2026-09-13_rotary_workbench_final/inputs/rotary_cone_nonzero_center.step` | `b19f19ed20d4d391f979d8593b1cc71c561c4cad57ae9af8c4875da47e59a26e` | 半径线性变化圆锥 Spiral、面派生 profile 与六件套 | 本项目使用 CadQuery 2.7.0 生成；附加同轴细杆仅提供稳定轴向参考边，不进入沉积面 |
| ROTARY-TRUTH | `tests/fixtures/analytic_rotary_truth.json` | `850a0c17165be7ff17df888900d270c8ff92f8ca6507beb85af4d9bbdef144e4` | 圆柱/圆锥 Spiral、Thin Wall 和 350°→20° Around Part 独立真值 | `derive_analytic_rotary_truth.py` 不导入项目算法；圆锥长度用复合 Simpson 积分，其余用独立闭式量测 |

生成入口为 `scripts/generate_rotary_evidence.py`。四组产品目录严格包含 `main.gcode`、`toolpath.json`、`machine_axes.csv`、`warnings.json`、`preview.json` 与 `manifest.json`；逐文件哈希见同目录 `products_summary.json`。

## 独立解析真值

机器可读真值位于 `tests/fixtures/analytic_tube_truth.json`，SHA-256 为 `e3d02045c104aadfd86a54ca3f4089a2dd019d6bf737663e772ef9c97f1159e8`。直管由起点、轴向和长度定义；圆弧管由圆心、平面法向、中心线半径和 90° 扫掠角定义。预期端点、切向、恒定内外半径和中心线长度均由登记参数直接计算，且明确独立于历史 G-code。`tests/test_toolpath_contract.py` 会读取该文件并复核关键公式。

## 后续真值实体计划

1. T01：保存管体、入口、出口、基体和忽略体的稳定引用，验证保存重开。
2. T02：按已登记解析真值生成直管和圆弧管 STEP，登记实体哈希和测量误差。
3. T02：对 `PIPE2-STEP` 做独立拓扑测量，记录管体和底座区分依据。
4. T03-T05：建立分块、截交、偏置和连接段的正常及失败样例。
