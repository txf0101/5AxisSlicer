# Curve C01—C05 实施与验收复盘

日期：2026-09-12。分支：`codex/curve-workbench-c01-c05`。P07 集成基线为 `125942f2863009f4a20e273bc1207dbd4d992eb8`；Curve 主实现提交为 `be81c67`、`25f7ac1`，最终几何/验证修复提交为 `999946e`，NumPy 2.2 类型门兼容提交为 `95ce8fc`。本轮未推送、未合并 `main`。

## 1. 完成范围

C01 保存 STEP 有向 edge 链的完整稳定描述符，按顺序和反向标志做弧长采样，并要求明确邻面或用户法向。重开和 STEP 更新使用签名唯一重绑；反向、断链、双邻面、缺失法向、零长 edge 和法向平行切向均有对象级诊断。

C02 的 Buildup 沿直线、圆弧和真实样条生成单道。C03 的 Multi-pass 按法向累计层高，奇偶层换向，Travel、Retract、Prime、Dwell 与 deposition 分开。C04 的 Offset Buildup 使用 `normal × tangent` 的显式局部横向方向；原链是第 0 道，反向 edge 改变偏置侧。锐角标架反转、自交、trimmed face 越界和投影塌缩均拒绝，不静默丢道。

C05 把三种操作接入同一产品链：

`Geometry → CurvePlan → shared Toolpath/events → MachineAxisTrajectory → ValidationReport → Postprocessor → G-code readback`

GUI、受限脚本和 HTTP 使用同一命令内核。Create、Apply、Generate、Cancel、Undo/Redo、Ready/Warning/Error/Stale、问题定位、真实 Toolpath Viewer、六件套导出、保存重开、引用重绑和格式迁移已接入。脚本保留 `tube/planar/curve` namespace，跨工作台事务被拒绝。取消保留上一份有效结果；重开后运行时结果按 Stale 处理。

## 2. 独立真值与真实案例

| 案例 | 独立依据 | 当前结果 |
| --- | --- | --- |
| 解析直线 | CadQuery 盒体的 20 mm 直边；端点和等弧长间隔独立核对 | 端点、弧长、反向切向通过 |
| 解析圆弧 | 叶轮 `body_001_edge_0005`；圆心 `(-52,0,42)`、R=40 mm、圆心角 π/2 | `62.83185307179585 mm`，每个采样点半径误差在测试阈值内 |
| 真实 STEP 样条 | `example/叶轮/叶轮.stp`，SHA-256 `3776fe6e...1fdf21f`；`body_002_edge_0011` | OCCT 长度 `68.27612913311773 mm`；100000 段独立弦长 `68.276129132436 mm` |
| 真实 Offset | 同一叶轮样条、邻面 `body_002_face_0006`、反向 edge、3 道、3.0 mm | 相邻道独立三维点距 2.947—3.000 mm；三道长度约 68.2742/65.0066/62.3040 mm |
| 解析失败 STEP | `rectangle_8x6x1.step`，SHA-256 `02e6adf3...39f8518` | 修剪面外偏置报 `curve.offset_outside_face`，Error 禁止导出 |

真实三操作均生成并按注册 Generic XYZAC 语义回读：Buildup 70 点/69 段/32.771862137049 mm³；Multi-pass 210 点/207 段/98.251453807514 mm³；Offset 210 点/207 段/93.880702147199 mm³。每项有一套六件套和逐文件 SHA-256。

失败矩阵还覆盖反向 edge、断链、法向歧义/缺失、退化 edge、法向平行切向、锐角标架反转、人工交叉路径自交、修剪面越界、边界投影塌缩、运动速度/加速度超限、旋转奇异 Warning 和 Setup 夹具 AABB 的连续扫掠碰撞。材料量按每个实际沉积段长度、道宽和层高独立重算；曲面 Offset 不再错误假设每道长度都等于基准 edge 长度。

## 3. 产品、界面和文档证据

三操作六件套位于 `docs/reviews/evidence/2026-09-12_curve_workbench_final/products/`。Viewer 直接读取生成的 shared Toolpath；Buildup、三层 Multi-pass 和三道 Offset 的路径专用图分别为 `06`、`07`、`08`，`09` 展示 edge 顺序、反向和邻面法向。1366×768 中文、1600×900 英文、1920×1080 英文的可见按钮均未截断，编辑区横向滚动最大值为 0。

截图是当前 Qt `QWidget.grab`，页面为真实 CurvePage，Viewer 后端为项目 OpenGL；它们不是桌面点击截图。一次 `QT_QPA_PLATFORM=offscreen` 的 VTK 初始化因 Win32 pixel format/GLEW 失败，日志保留；后续成功截图使用当前桌面 Qt/OpenGL 上下文。未把该失败写成 VTK 离屏通过。

使用说明见 `docs/guides/curve_workbench_zh.md`，包含入口、边链/反向、法向、三操作参数、状态、生成/取消/检查/导出、六件套、保存重开、脚本/HTTP、错误恢复、图片和能力边界。

## 4. 验证与失败修复

验证解释器为 `tmp/pytest9/Scripts/python.exe`，Python 3.12.7、pytest 9.1.1、OCP 7.8.1.1、Qt 5.15.2、VTK 9.3.1；每轮 pytest 使用唯一仓库内 `--basetemp`，Qt 和全仓串行。

| 阶段 | 结果 |
| --- | --- |
| Curve 初次环境运行 | 1 passed、13 errors；系统 `%TEMP%` 无权创建 pytest 目录。改用仓库内唯一 basetemp 后 14 passed |
| C05 集成与重构门 | 50 passed/32 subtests；重构后 44 passed/32 subtests |
| Curve 首次最终 | 23 passed、1 failed；测试误把 `GeometryReference.kernel_signature` 当属性，改读签名字典后 24 passed |
| Tube 共享回归首轮 | 166 passed、1 failed、613 deselected、8 subtests；STEP 导入后错误进入 CurvePage。统一 `show_after_model_import` 后完整重试 167 passed、613 deselected、8 subtests |
| Planar 共享回归 | 225 passed、555 deselected |
| Offset/失败矩阵迭代 | 发现正向投影塌缩和浮点阈值两次失败；补塌缩诊断并使用反向 edge 后通过 |
| Curve 专项 | 算法/产品最终为 32 passed、754 deselected；当前收尾直接集为 40 passed、2 subtests，exit 0 |
| 最终全仓（NumPy 2.2.6） | 783 passed、3 skipped、130 subtests，exit 0，300.54 s |
| 质量脚本 | 实现阶段先修 2 个 `Vector3` 标注；收尾阶段再复现 `np.savez` 与 ndarray shape 两个 NumPy 2.2 stub 问题。首次修复多占一行触发上下文预算，合并注解后 Ruff、格式、上下文预算、Mypy 134 个源码文件全通过 |
| 构建与包 | 当前验收提交的 sdist/wheel 构建成功，Twine 两件均 PASSED；Windows native preview index 导入和 3 tests 通过 |
| 依赖一致性 | 污染环境因用户 site-packages 冲突失败；新建仓库内干净 Python 3.12 环境后 `pip check` 为 `No broken requirements found` |

新干净环境直接启动全仓时在测试输出前以 Windows 原生码 `0xC0000409` 退出；该环境只用于独立 `pip check` 和 native build。按验证 Skill，最终 Qt/全仓资格来自项目已核验解释器的串行通过。首次失败、重试、JUnit、stdout 和环境日志全部保留，没有用重试覆盖失败记录。

收尾直接测试首次使用含中文的绝对 `--junitxml` 路径时被 PowerShell 转码破坏，pytest 在收集前 exit 4；改为仓库相对路径和新的 `--basetemp` 后 40 passed、2 subtests。该环境故障及修复也保留在最终清单中。

## 5. 来源和许可证边界

产品实现固定使用 OCP `7.8.1.1.post1` 的 `BRepAdaptor_Curve`、`GCPnts_UniformAbscissa`、`GeomAPI_ProjectPointOnSurf` 和 `BRepClass_FaceClassifier`；CadQuery `2.7.0` 只生成解析测试 STEP。Curve 的边链、采样、标架、偏置、状态、Toolpath、验证和回读为本项目独立实现。

Open5x/COMPAS Slicer 的 MIT README 只作为早期术语背景，没有复制实现；本轮 GitHub 连接失败，未固定的 `master` 不作为验收来源。CuraEngine/PrusaSlicer 为 AGPLv3，本轮 Curve 未读取、复制或改写其源码、测试和内部数据结构。真实叶轮 CAD 的作者、工具、许可证和再分发许可未知，仓库 MIT 不自动覆盖该文件。

## 6. 未验证边界与下一项

当前通过的是 Generic XYZAC、离线 IK/FK、轴限/速度/加速度、保守夹具 AABB 扫掠、注册参考语义回读和 OpenGL 预览。它们不证明真实控制器、真实机床标定、现场完整碰撞、材料适配、支撑可拆卸性或试切。上述项目均为“未验证”。

C01—C05 满足阶段门后，唯一台账下一项为 R01。Freeform 曲面区域、Coating、Thin Wall 和 Buildup 仍未实现，不能由 Curve 的 edge 链能力推定完成。

使用的 Skills：`five-axis-workbench-development`、`five-axis-slicer-validation`。完整命令、环境、六件套、截图、日志与 SHA-256 见 `docs/reviews/evidence/2026-09-12_curve_workbench_final/validation_manifest.json`。
