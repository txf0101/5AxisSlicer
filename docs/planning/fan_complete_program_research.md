# 扇叶完整程序开发借鉴项目调研

> 2026-09-20 纠正补充：此前仅核对 Open5X 仓库和静态记录不足以约束扇叶层域，导致 FAN04/FAN07 误用固定姿态平面切层。现已阅读原论文曲层与位置/法向章节，并独立解析旧 NC 的 A90/C 联动。来源、实际读取范围、视频访问失败及径向实现边界集中记于[纠正复盘](../reviews/2026-09-20_fan_radial_correction.md)，不得将旧阶段完成表述继续用于工艺验收。

日期：2026-09-20。用于[开发计划](fan_complete_program_plan.md)，范围为实体内填充、曲层路径组织、程序编排与五轴后处理。今日通过GitHub官方REST API核对以下六仓库默认分支commit及许可证元数据；读取官方项目页、下列明确列出的源码/文档。未编译或运行上游，不将候选方法写为本项目已实现。

## 1 优先采用的路线

现有OCP/OCCT负责权威STEP实体、截交、距离、法向和修剪域。现有Planar、Curve、Freeform、XYZAC、Toolpath和命令层继续复用。新增工作集中在实体层域、壳层与填充区域、已打印体调度和总程序状态。上游选择以具体缺陷和成本为依据，不整体引入第二套切片平台。

| 项目 | 本次固定commit | 许可证核对 | 对应工作包与决定 |
| --- | --- | --- | --- |
| [COMPAS Slicer](https://github.com/compas-dev/compas_slicer/tree/680d1749a4b7c3b1300ebb447257d6af44e19324) | `680d1749a4b7c3b1300ebb447257d6af44e19324` | API为MIT；[LICENSE](https://github.com/compas-dev/compas_slicer/blob/680d1749a4b7c3b1300ebb447257d6af44e19324/LICENSE) | FAN04/05/07/09：曲层数据、打印组织、窄区骨架候选；适配成本中至高，先做独立小夹具 |
| [Open5x](https://github.com/FreddieHong19/Open5x/tree/500a786e51447b47e00d2a5ca3dcc938ae542926) | `500a786e51447b47e00d2a5ca3dcc938ae542926` | API为MIT；[LICENSE](https://github.com/FreddieHong19/Open5x/blob/500a786e51447b47e00d2a5ca3dcc938ae542926/LICENSE) | FAN01/09/10：位置/方向、挤出和转位组织；已有本地静态研究可复用，机型适配成本中 |
| [Clipper2](https://github.com/AngusJohnson/Clipper2/tree/f9c5eb6e14a59f6f5d65fbfb3564519a561cf4fd) | `f9c5eb6e14a59f6f5d65fbfb3564519a561cf4fd` | API为BSL-1.0；[许可证正文](https://github.com/AngusJohnson/Clipper2/blob/main/LICENSE) | FAN05：多边形布尔/偏置备选；仅在现有OCCT被具体反例或性能限制阻塞时引入 |
| [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer/tree/6f510128d7c2e543b62919b74bea7e876f564205) | `6f510128d7c2e543b62919b74bea7e876f564205` | API为AGPL-3.0；[LICENSE](https://github.com/prusa3d/PrusaSlicer/blob/6f510128d7c2e543b62919b74bea7e876f564205/LICENSE) | FAN05/06/11/13：填充率、实心层和用户参数语义；本轮以公开行为为主要参考 |
| [CuraEngine](https://github.com/Ultimaker/CuraEngine/tree/27c70acfac154a5215fe52f8d1ee6229084ae7d2) | `27c70acfac154a5215fe52f8d1ee6229084ae7d2` | API为AGPL-3.0；[LICENSE](https://github.com/Ultimaker/CuraEngine/blob/27c70acfac154a5215fe52f8d1ee6229084ae7d2/LICENSE) | FAN03/05/06/10：feature区域到路径与工序顺序；采用公开流程设计参考，直接集成引擎暂不选 |
| [MAGE Slicer](https://github.com/gear2nd-droid/MageSlicer/tree/0026f8013e589a8f1c8dea6f60e34773f3fa6d55) | `0026f8013e589a8f1c8dea6f60e34773f3fa6d55` | API为NOASSERTION；[正文](https://raw.githubusercontent.com/gear2nd-droid/MageSlicer/0026f8013e589a8f1c8dea6f60e34773f3fa6d55/LICENSE.txt)为PolyForm Shield 1.0.0 | 有NURBS几何研究背景；源码移植排除在推荐方案外，须取得适用授权再评估 |

许可证是项目选择约束。MIT/Boost部件复用仍需保留通知并核查依赖；COMPAS所需CGAL包不能随主项目一起视为MIT。AGPL项目若实际复制或集成，需要按交付方式专项核查义务；进程隔离、翻译语言或改名不能自动解决许可问题。本计划不新增许可证承诺，也不要求公开本项目源码。

## 2 本次读到的具体内容及工程差距

### COMPAS Slicer

已通过固定commit的Git树确认 `print_organization/`、`slicers/uv_slicer.py`、`post_processing/infill/medial_axis_infill.py` 和 `examples/7_medial_axis_infill/`。其中本次实际阅读全文为[骨架填充](https://raw.githubusercontent.com/compas-dev/compas_slicer/680d1749a4b7c3b1300ebb447257d6af44e19324/src/compas_slicer/post_processing/infill/medial_axis_infill.py)与[安全点](https://raw.githubusercontent.com/compas-dev/compas_slicer/680d1749a4b7c3b1300ebb447257d6af44e19324/src/compas_slicer/print_organization/print_organization_utilities/safety_printpoints.py)。前者把闭轮廓投到XY，调用CGAL直骨架后生成路径，并过滤短边；这种实现不能直接处理扇叶空间填充，直骨架也不能普遍等同欧氏中轴。需自行处理局部面域、孔、道宽、短路径材料和三维映射。后者在挤出开关已知时插入抬升点，只能借鉴事件组织；不构成AC转位扫掠检查。

`base_print_organizer.py`、`interpolation_print_organizer.py` 和UV算法列为后续精读入口，本轮只核验路径存在。采用前须检查数据依赖、参数域度量、错误传播和现有Toolpath适配。

### CuraEngine与PrusaSlicer

实际读取[CuraEngine官方Generating Paths](https://ultimaker.github.io/CuraEngine/docs/generating_paths.html)和[Prusa官方Infill](https://help.prusa3d.com/article/infill_42)。Cura资料支持先形成feature区域再排路径的设计，并讨论墙、内部填充、skin、缝隙及空移的关系。Prusa文档用于参数语义对照。本项目将这些概念写成独立数据契约和解析测试；具体三维层域、覆盖量测和AC控制由本项目实现。

`src/infill.cpp`、`src/FffGcodeWriter.cpp`、Prusa的Fill和Perimeter相关源码是既有研究登记入口，目录实施前按固定版本再次解析。本轮未逐文件阅读这些实现，不宣称已经复现其算法。后续可以用独立安装的上游生成平面基准，但必须在同几何、参数和坐标条件下比较；上游三轴G-code不能直接拼进五轴总程序。

### Clipper2与Open5x

已核验Clipper2固定树内 `CPP/Clipper2Lib/src/clipper.engine.cpp`、`clipper.offset.cpp` 以及对应头文件。可用于FAN05局部二维轮廓布尔和偏置；需测试整数缩放、最小特征、孔方向和Python/native打包。它不提供曲面体积层域、XYZAC或支撑顺序。

Open5x本轮重查项目页、commit和许可证，复用[原研究](reference_research.md#11-rotary-r01r05-的-open5x-与-nx-资料核对)中Grasshopper定义的静态记录。相关入口是 `Grasshopper_Definition/Open5x_Gcode_0503.gh`。本轮未运行Rhino/Grasshopper，也未重新解析二进制图。可对照点/方向、E与非沉积事件组织，不能据此声称已有扇叶自动全体积填充。

### MAGE与其他已有研究

MAGE许可证正文含Noncompete，本轮据此排除直接源码移植。原本地Fractal/V1可用于追踪旧文件生成流程，但任何组件复用先查来源和许可。S³-Slicer/CurviSlicer属于更广泛的变形/场切片方向，沿用[已有研究](reference_research.md)，本轮没有重新核验版本和实现；首个显式分区扇叶闭环不以它们为前置依赖。

## 3 开发时的复用核验清单

每个实际采用部件登记仓库、commit、文件、SHA-256、许可证及依赖、原始用途、修改范围和测试。首轮优先验证：二维带孔/窄区布尔、局部域三维映射收敛、显式打印依赖，以及90°姿态可达性。出现不适配时记录失败夹具和替代决策，不为引入候选项目扩大产品范围。

当前可确认的是参考内容和适用边界；尚未确认其在本项目的速度、精度、二进制兼容性与整件扇叶效果。这些由FAN04/05/13实际验证。
