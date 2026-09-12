# 六个工作台开发参考资料

初次检索：2026-09-10；更新至：2026-09-12。本文服务于[开发计划](development_plan.md)与[进度台账](progress_tracker.md)。资料来自当前项目、相邻参考项目、Siemens 官方页面、项目官方 GitHub README/许可证和部分源码。已实际读取的网页与未运行的代码分别说明，公开介绍不能替代本项目的算法验证。

## 1 检索结论

管状首版采用中心线辅助的分块定向路线：NX 2412 提供楔角、分块和恒定道高的公开工艺依据；Fractal Cortex 提供通用多方向分块流程的学习材料；精确几何、中心线提取、分块交界和当前机型的连接/运动学仍由本项目独立实现。

后续自由曲面可对照 MAGE 的 NURBS 路径组织、Open5x 的点与法向处理，以及 COMPAS Slicer 的插值和等值线方法。平面算法对照 PrusaSlicer/CuraEngine 的成熟流程。研究工作台采用有限、可复算的基线，不把某个原型的 README 功能描述直接当作已具备的本地能力。

NX 产品页明确列出 Planar、Rotary、Freeform、Tube 四类；Curve 与 Research 是本项目的入口划分。六工作台及本版 20 种操作属于本项目的产品范围，不能声称与 NX 菜单逐项一致。

## 2 Siemens 官方公开来源

以下七页均在本轮通过 HTTPS 实际读取并返回 HTTP 200。表中日期为网页标注的发布日期，产品页未指定发布日期。

| 编号 | 官方来源与日期 | 本轮实际核对的内容 | 开发用途与适用边界 |
| --- | --- | --- | --- |
| NX-01 | [Additive manufacturing multi-axis](https://plm.sw.siemens.com/en-US/nx/products/nx-am-multi-axis/) | 四类沉积；feature decomposition；拆为独立 additive operations；重排工序；区分 infill/finish；沉积仿真和喷头碰撞 | 参考制造对象、操作、资源和共同验证流程。页面还提到 planar zigzag/spiral、回转特征、曲面皮层和管状 helical motion；未公开数学实现 |
| NX-02 | [The ultimate guide to CAM software](https://blogs.sw.siemens.com/nx-manufacturing/ultimate-cam-software-guide-2025/)，2025-01-10 | Load CAD → Choose operations → Generate toolpaths → Simulate and verify → Postprocessing → Transfer | 参考现有 UI 的生成/检查/输出组织。此为一般 CAM 指南；Dirty 状态、事务和数据契约是本项目设计 |
| NX-03 | [What’s new in NX for manufacturing December 2412](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-december-2412/)，2024-12-16 | Tube Thinwall 可由用户设置 wedge angle，将管分为 wedges 并保持 constant bead heights；此前用于 Tube Additive Buildup；另有 Printer/Material Library、Build Styles/Rules 及按 layer/region/pattern 的报告 | 对应 T03/T04/T09。未公开中心线算法、壁厚阈值、分块交界几何、安全转位和碰撞实现 |
| NX-04 | [What’s new in NX for manufacturing June 2506](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-june-2506/)，2025-06-23 | Freeform Thinwall 沿/跨驱动面自动多道偏置，控制方向和 step-over；逐层沉积长度和切片面积分布检查 | 对应 F03/F05 和公共统计；几何面积变化不能解释为热变形预测 |
| NX-05 | [What’s new in NX for manufacturing December 2512](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-december-2512/)，2025-12-15 | Rotary Buildup 的 profile slicing、infill ramp、pattern 改进；可对 corners/overhangs 设置区域参数 | 对应 R03 的轮廓、层间接头和工艺参数。供应商描述的 void-free 不作为本项目保证 |
| NX-06 | [What’s new in NX for manufacturing 2606](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-2606-june-2026/)，2026-06-19 | 连续回转 Circular NCM/Rotary spline NCM，主要用于圆柱面多个凸台的 Rotary Buildup；Freeform finish 支持 CW/CCW/交替方向 | 对应 R04/F03 的适用场景；不能据此宣称任意弯管的连续五轴算法已公开 |
| NX-07 | [What’s new in NX for Manufacturing December 2023](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-december-2023/)，2023-12-11 | 逐层 In-Process Workpiece 检查潜在 voids；Morph Across 的驱动曲线、往复路径与 min/max stepover | 对应 T07 的沉积几何近似和 Curve/Freeform 方法研究；IPW 不能替代真实打印或热仿真 |

NX-03 的直接短引文为 “By splitting tubes into wedges with constant bead heights”。本项目用最大楔角产生候选区段，再计算几何误差的方案属于设计推导，不能当作 NX 公布的内部算法。

## 3 公开项目及代码学习入口

许可证在本轮读取了官方原文。表中的代码入口以本地实际文件及官方当前目录树核对；本轮未安装、编译或运行这些项目。

| 编号 | 项目与实际许可证 | 适用工作台 | 已核对的入口与可学习内容 | 本项目采用方式及边界 |
| --- | --- | --- | --- | --- |
| OS-01 | [Fractal Cortex](https://github.com/fractalrobotics/Fractal-Cortex)，[GPLv3](https://github.com/fractalrobotics/Fractal-Cortex/blob/main/LICENSE)；Fractal Robotics；README 标注 Copyright (C) 2025 Daniel Brogan | Tube Indexed、Planar、连接与输出 | `fractal-cortex/slicing_functions.py` 的 `all_5_axis_calculations`、`create_chunkList`、`align_mesh_base_to_xy`、`checkForBedNozzleCollisions`、`write_5_axis_gcode`；管接头 STL/G-code 示例 | T01—T07 已学习手动分割面、多方向分块、坐标和路径顺序，并按当前 B-Rep、Toolpath、XYZAC 与检查契约重写。固定版本和逐文件哈希见[来源登记](tube_reference_provenance.md) |
| OS-02 | [MAGE Slicer](https://github.com/gear2nd-droid/MageSlicer)，[PolyForm Shield 1.0.0](https://github.com/gear2nd-droid/MageSlicer/blob/main/LICENSE.txt) | Freeform、Tube 曲面、Research | `OCCTProxy/SliceObjects.cpp` 的 `calcLayer`、`calcPoints`、`calcBottomPoints`、`calcPeelerLayer`；`SliceTools.cpp` 的曲面、UV/XYZ 填充；`example/BendingPipe` | 研究 Sandwich/Bottom/Peeler、NURBS 与中间 CSV。许可证含 Noncompete；默认不移植其源码。机床后处理和碰撞位于独立 MAGE Simulator；自动体积分解在 README 中列为后续功能 |
| OS-03 | [Open5x](https://github.com/FreddieHong19/Open5x)，[MIT](https://github.com/FreddieHong19/Open5x/blob/main/LICENSE) | Curve、Freeform、Rotary、Tube 的公共姿态与运动 | 原版 `Grasshopper_Definition/Open5x_Gcode_0503.gh`、旋转平台与 `Duet2_Configuration`；[上游说明](https://github.com/FreddieHong19/Open5x/blob/main/Grasshopper_Definition/README.md) | 点与法向、轴运动、挤出和进给的参考，可评估组件复用并保留通知。本地 Python port 是既往本地补充，reference replay 不能证明上游自动几何切片 |
| OS-04 | [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer)，[AGPLv3](https://github.com/prusa3d/PrusaSlicer/blob/master/LICENSE) | Planar、参数、作业状态、预览与输出 | 本轮目录树为 `src/libslic3r/src/libslic3r/` 下的 `TriangleMeshSlicer.cpp`、`PerimeterGenerator.cpp`、`Fill/FillRectilinear.cpp`、`PrintObject.cpp`、`GCode.cpp` | 对照流程与可观察行为，独立实现本项目所需平面核心；不直接推定连续五轴与管状能力 |
| OS-05 | [CuraEngine](https://github.com/Ultimaker/CuraEngine)，[AGPLv3](https://github.com/Ultimaker/CuraEngine/blob/main/LICENSE) | Planar、计算后端与路径输出 | `src/slicer.cpp`、`src/infill.cpp`、`src/FffGcodeWriter.cpp`；[官方 README](https://github.com/Ultimaker/CuraEngine/blob/main/README.md) | 学习计算与 UI 分离、层内路径和输出。README 链接的 [Internals](https://github.com/Ultimaker/CuraEngine/wiki/Internals) 本轮未逐页阅读 |
| OS-06 | [COMPAS Slicer](https://github.com/compas-dev/compas_slicer)，[MIT](https://github.com/compas-dev/compas_slicer/blob/master/LICENSE) | Planar、Curve、Freeform、Research | `src/compas_slicer/slicers/` 中 planar/interpolation/scalar_field/uv slicer；`slice_utilities/scalar_field_contours.py`；`print_organization/`；`examples/5_non_planar_slicing_on_custom_base/scalar_field_slicing.py` | 可评估方法及组件，先核对 COMPAS/CGAL 等依赖。实读 ScalarFieldSlicer 是三角网格顶点场的等值线，不能直接当作实体内部等值曲面和填充 |
| OS-07 | [CurviSlicer](https://github.com/mfx-inria/curvislicer)，[AGPLv3](https://github.com/mfx-inria/curvislicer/blob/master/LICENSE.md) | Research、Freeform 对照 | `src/main.cpp`、`TetMesh.cpp`、`uncurve.cpp`、`gcode.cpp`、`resources/curvi`；[作者论文入口](https://hal.archives-ouvertes.fr/hal-02120033/document) | 研究形变模型、平面切片、逆映射曲线路径。面向普通三轴轻度曲层；master 的 OSQP 与论文 Gurobi 路线有差异，不宣称已复现论文性能；论文全文本轮未逐页审读 |

PrusaSlicer 等上游目录可能继续变化，实际实施时固定所读版本和必要文件哈希。MIT 项目也需要保留通知并核对依赖，当前计划不要求整个项目开源。任何改写工作都应从公开方法、独立设计和本项目验收出发，不能仅以改名作为来源处理方式。

## 4 本地参考位置

| 对象 | 本地目录或文件 | 可用于本计划的内容 |
| --- | --- | --- |
| Fractal 原始参考 | [本地 Fractal Cortex](../../../5AxisSlicer/Fractal-Cortex-main/Fractal-Cortex-main/README.md)；commit `db29bacc5615fce206b05dc49bd6c52ab92d5351` | 管接头分块示例和通用多方向切片流程；完整指纹见[来源登记](tube_reference_provenance.md) |
| V1.0 复现工程 | [5AxisSlicer README](../../../5AxisSlicer/README.md)；`src/five_axis_slicer/core/legacy_engine.py`；`Open5X/five_axis_slicer/fractal.py` | T01—T07 用于了解历史行为、接口和失败边界；新代码已聚拢到 V2.0 且运行时不依赖相邻目录 |
| MAGE | [本地 MAGE README](../../../5AxisCutting/MageSlicer-main/MageSlicer-main/README.md) | NURBS 切片与 BendingPipe 工程 |
| Open5x 与本地移植 | [本地 Open5x](../../../5AxisSlicer/Open5X/Open5x-main/Grasshopper_Definition/README.md) | Python port 与上游 Grasshopper 的范围区别 |
| 当前目标 | [开发目标文档](../../圭臬/开发目标文档.docx) | 19 个原操作、统一前处理、ToolpathPoint 和最终交付目标 |
| 当前结构 | [项目结构](../project_structure.md)、[README](../../README.md) | 现有模块及用户入口 |
| Tube 范围 | [7/22 规划](../reviews/2026-07-22_tube_slicing_user_workflow_review.md)、[7/24 实施](../reviews/2026-07-24_tube_setup_coordinate_implementation_review.md)、[7/31 实施](../reviews/2026-07-31_tube_script_console_review.md) | 用后续实施修正早期规划中的过时状态 |

本地相邻项目链接仅在当前目录结构有效；重新检出本仓库时需自行提供参考项目。正式算法实现不应依赖这些目录存在。

## 5 当前源码证据

以下表格记录本轮静态核查的源码入口；T01—T07 的执行验证见[实施审查](../reviews/2026-09-11_t01_t07_indexed_tube_review.md)和[证据清单](../reviews/evidence/2026-09-11_t01_t07/manifest.json)。

| 当前事实 | 源码入口 | 对计划的影响 |
| --- | --- | --- |
| 六工作台目录存在 | [workbenches.py](../../src/five_axis_slicer/workbenches.py) | 保留入口，逐项接真实生成器 |
| 成果页动作读取已有 G-code | [ui.py](../../src/five_axis_slicer/ui.py) 中 `slice_results`；[result_state.py](../../src/five_axis_slicer/result_state.py) 中 `parameters_affect_toolpath` | T08 必须接入真实生成并区分来源 |
| Tube Operation 已含四个几何角色和九项工艺参数 | [setup.py](../../src/five_axis_slicer/manufacturing/setup.py) 中 `TubeOperationDefinition` | T01 已接入 UI、脚本、HTTP、Dirty 和项目 JSON |
| 圆柱/环面中心线及精确截交已实现 | [geometry.py](../../src/five_axis_slicer/algorithms/tube/geometry.py)、[section.py](../../src/five_axis_slicer/algorithms/tube/section.py) | T02—T04 支持单支恒定圆截面直管/圆弧管和手动 edge 链 |
| Generic XYZAC 参考 IK 与检查已实现 | [xyzac.py](../../src/five_axis_slicer/kinematics/xyzac.py)、[indexed_tube.py](../../src/five_axis_slicer/validation/indexed_tube.py) | T06—T07 提供 FK 回代、轴限制、保守碰撞与 IPW 近似；不构成实机资格 |
| 已有命令事务 | [command_kernel.py](../../src/five_axis_slicer/command_kernel.py) | 避免 GUI/脚本/HTTP 分别实现生成参数校验 |

## 6 研究算法与连续标架的直接依据

以下三组来源在本轮实际读取了作者仓库 README、许可证或研究机构摘要。尚未逐页研读论文全文，也未编译或复现算法。

| 编号 | 直接来源 | 已核对的方法及实现边界 | 对应任务 |
| --- | --- | --- | --- |
| M-01 | Zhang 等，S³-Slicer，ACM TOG 2022，[DOI](https://doi.org/10.1145/3550454.3555516)；[作者仓库 S3_DeformFDM](https://github.com/zhangty019/S3_DeformFDM)，[BSD-3-Clause](https://github.com/zhangty019/S3_DeformFDM/blob/main/LICENSE) | 同时考虑少支撑、强度与表面质量，旋转驱动变形后将高度场映回原实体，等值面形成曲层。源码依赖 VS/Qt、oneMKL、四面体网格，部分步骤使用 MeshLab；G-code/运动规划另属独立仓库。本轮作者项目网页返回 404，采用可读的作者仓库作为依据 | X03/X05 的场与层；X04 的多目标研究参照。不能把论文改善值当本软件效果 |
| M-02 | Wang 等，Computation of rotation minimizing frames，ACM TOG 2008；[作者机构摘要](https://www.microsoft.com/en-us/research/publication/computation-rotation-minimizing-frames/)，[DOI](https://doi.org/10.1145/1330511.1330513) | double reflection 从前一标架构造下一标架，摘要给出四阶全局逼近误差。只解决低扭转几何标架；不保证轴位可达、速度或碰撞。本轮未找到已核验的官方源码许可证；ACM 页面访问受限，实际阅读来自机构摘要 | T10 的 RMF；检查右手性、正交、切向、直线/反曲/重复点等退化输入，完整公式在实施前阅读 |
| M-03 | Fang 等，Reinforced FDM，ACM TOG 2020，[DOI](https://doi.org/10.1145/3414685.3417834)；[作者仓库](https://github.com/GuoxinFang/ReinforcedFDM)，[BSD-3-Clause](https://github.com/GuoxinFang/ReinforcedFDM/blob/master/LICENSE.txt) | FEA 结果→主应力方向→向量/标量场→曲层→应力对齐路径；输出 x,y,z,nx,ny,nz。作者明确 Fabrication Enabling 尚未完整，依赖 Qt/VS 等工具，机床运动另行处理 | X04 的真实应力输入、场处理与路径对齐；不把 waypoint 文件当可直接上机的 G-code |

Conical Buildup 的第一版采用独立解析几何基线。对指定轴建立半径 `r`，取标量场 `φ = z − k r`，其等值面形成一组平移锥面；`k` 为无量纲斜率。避开轴上 `r = 0` 的顶点奇异区，并用解析截交验证法向间距 `Δφ / sqrt(1 + k²)`。这属于本项目拟定的验证方案，未声称上述论文提供专用锥面切片实现。

## 7 证据保存和未完成的研究

网页 HTML、文本、GitHub README/LICENSE/目录树及文件指纹暂存 `tmp/planning_research/nx/` 和 `tmp/planning_research/opensource/`；本轮原目标抽取与基线指纹保存在 `tmp/planning_research/`。这些是可再生成的临时资料，正式判断与精确 URL 已集中到本文，不将临时目录作为唯一来源。

本轮没有复现开源算法、测定其精度/速度、核验真实机床或阅读付费 NX 文档。实际算法任务开始后，针对当项方法继续读取必要数学/源码并固定版本。研究工作台的应力场样例、算法误差阈值和实际性能仍需在 X01 等任务中建立，不能由此次资料检索直接给出完成结论。

## 8 T08—T12 新实现的可核对来源边界

T08—T12 的实现是本项目独立复写，受本地 Fractal/V1 项目启发，但运行时不依赖相邻目录；当前代码在本项目内部使用，仍保留下列来源说明。来源用于核对术语、公开算法思路或接口语义，不等同于移植源码、上游认证或实机资格。

| 主题 | 可核对来源与实现边界 |
| --- | --- |
| RMF（T10） | Wang 等，*Computation of rotation minimizing frames*，DOI [10.1145/1330511.1330513](https://doi.org/10.1145/1330511.1330513)；同时核对 [Microsoft Research PDF/摘要页](https://www.microsoft.com/en-us/research/publication/computation-rotation-minimizing-frames/)。本地仅独立复写 double-reflection 标架计算及退化处理；来源只支持几何低扭转标架，不保证机床轴位、速度或碰撞。 |
| G-code 基础语义（T08/T09） | [LinuxCNC G-code 页面](https://www.linuxcnc.org/docs/html/gcode/g-code.html)用于核对 G0/G1、G90/G91 的公开语义。M82 属 Marlin/RepRap 语义，依据 [Marlin M082](https://marlinfw.org/docs/gcode/M082.html)，不能称为 LinuxCNC 定义；项目解析器仍按显式控制器配置和离线边界处理。 |
| 时间参数化（T11） | [MoveIt 时间参数化教程](https://moveit.picknik.ai/main/doc/examples/time_parameterization/time_parameterization_tutorial.html)用于 TOTG 与 Ruckig 的术语和限制：TOTG 可能偏离原路径，需复查碰撞；Ruckig 用于 jerk 约束。这里是离线轨迹参考，不构成控制器后处理或实机认证。 |
| 碰撞/截交（T09/T12） | [FCL](https://github.com/flexible-collision-library/fcl)是碰撞检测参考；[OCCT BRepAlgoAPI_Section](https://dev.opencascade.org/doc/refman/html/class_b_rep_algo_a_p_i___section.html)是 B-Rep 截交 API 参考。本项目按自身几何与检查契约独立调用/复写，结果仍属于离线检查。 |
| 轴与资格边界（T08—T12） | Generic XYZAC 仅作离线参考（含 IK/FK、轴限位、扫掠和检查），不代表具体控制器、后处理器或实机资格。Generic XYZAC 离线参考和本地 Fractal/V1 经验均不能替代注册控制器语义、碰撞复核和现场试切。 |

## 9 P07 支撑行为的公开来源边界

P07 关闭时于 2026-09-12 重新固定上游版本。PrusaSlicer `master` 为 [`6f510128d7c2e543b62919b74bea7e876f564205`](https://github.com/prusa3d/PrusaSlicer/tree/6f510128d7c2e543b62919b74bea7e876f564205)，CuraEngine `main` 为 [`553d59ca44ae3a562034d6593c238c46783a1d32`](https://github.com/Ultimaker/CuraEngine/tree/553d59ca44ae3a562034d6593c238c46783a1d32)。本轮只读取官方 REST 元数据、许可证和公开帮助页；本机 Git 代理 `127.0.0.1:7890` 不可用，所以未以 `git ls-remote` 作为版本证据。Prusa Support material 页面 UTF-8 内容 SHA-256 为 `6D7CE83040917872165BA89B9F6CF07E87ECAAF23CFF3E22B28BDBF4E6FE6E65`。

| 编号 | 公开来源与许可证 | 本轮实际核对的行为 | 本项目实现边界 |
| --- | --- | --- | --- |
| P07-01 | [Prusa Support material](https://help.prusa3d.com/article/support-material_1698)，Prusa 官方 Support 文档；访问日 2026-09-12，内容哈希见上文 | 已核对 `Supports on build plate only`、`Overhang threshold`、`Top contact Z distance`、`Top interface layers` 四项支撑参数及其公开说明 | 用于定义 P07 的可观察参数语义和验收边界；文档不公开本项目所需的完整几何、分区、接口生成或五轴路径算法 |
| P07-02 | 固定 [PrusaSlicer commit](https://github.com/prusa3d/PrusaSlicer/tree/6f510128d7c2e543b62919b74bea7e876f564205) 及其 [AGPLv3](https://github.com/prusa3d/PrusaSlicer/blob/6f510128d7c2e543b62919b74bea7e876f564205/LICENSE)；固定 [CuraEngine commit](https://github.com/Ultimaker/CuraEngine/tree/553d59ca44ae3a562034d6593c238c46783a1d32) 及其 [AGPLv3](https://github.com/Ultimaker/CuraEngine/blob/553d59ca44ae3a562034d6593c238c46783a1d32/LICENSE) | 两个公开项目的许可证均为 AGPLv3；本登记只用于许可证和公开可观察行为边界核对 | P07 采用 clean-room 独立实现：不复制、翻译或改写 PrusaSlicer/CuraEngine 源码、测试和内部数据结构；本项目的支撑几何、状态契约、独立真值和 Toolpath 输出均由本项目验证 |

## 10 Curve C01—C05 的几何与许可证边界

Curve 本轮复用 OCCT/OCP 的公开几何 API：`BRepAdaptor_Curve`、`GCPnts_UniformAbscissa`、`GeomAPI_ProjectPointOnSurf` 和 `BRepClass_FaceClassifier`。运行环境为 OCP `7.8.1.1.post1`；它们分别用于权威 STEP 曲线适配、弧长采样、曲面投影和 trimmed face 分类。Curve 链顺序、方向、法向所有权、局部横向标架、状态机、Toolpath、验证和回读均由本项目独立设计。

Open5x 与 COMPAS Slicer 的公开 MIT README 仅是早期术语和路径组织背景，本轮没有用其源码、Grasshopper 图、内部组件、数据结构或实现公式。2026-09-12 尝试重新固定两者 HEAD 时，GitHub 连接分别返回 reset/connection failure，因此不把未固定的 `master` 作为 C01—C05 验收来源。C01—C05 实际实现依据固定为 OCP `7.8.1.1.post1` 的公开 API、CadQuery `2.7.0` 的解析夹具生成和本项目独立真值。CuraEngine 与 PrusaSlicer 均为 AGPLv3，Curve C01—C05 没有读取、复制或改写其源码、测试和内部结构；P07 已登记的公开可观察行为也没有用作 Curve 实现公式。

CadQuery 2.7.0 仅用于测试中生成解析 STEP 夹具，工具许可证为 Apache-2.0；产品运行时不依赖 CadQuery。真实叶轮 STEP 的作者、建模工具和再分发许可证未知，当前只作为本地验收输入，详见[样例来源登记](example_source_inventory.md)。
