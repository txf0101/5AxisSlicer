# 管状切片用户流程与首版范围复盘

## 1 调研边界

本轮讨论面向 Tube Workbench 的产品流程和首版实现边界，未修改切片代码与目标 DOCX。读取前核对了 `圭臬/开发目标文档.docx`：文件大小 492214 字节，最后修改时间为 2026-07-06 13:45:16；目录中存在 Word 锁定文件，分析期间仅进行只读抽取。

开发目标文档已经给出 Workbench、Operation Session、制造对象、Machine Profile、ToolpathPoint、运动学、检查和后处理等总框架。现有程序的真实可执行主线仍是 Imported NC Review：STEP 和外部 G-code 可以加载、选择、解析和预览，Print、Material、Machine 页面尚未驱动路径生成。对应证据见 `README.md:3-13`、`src/five_axis_slicer/ui.py:839-848`、`src/five_axis_slicer/result_state.py:241-269`。

## 2 核心判断

Tube Workbench 的首个完整操作建议定为 `Tube Thin Wall Indexed`，中文名称采用“管状薄壁分块定向切片”。它面向单支、无分叉、近圆截面的薄壁管；系统按中心线方向变化把管件划分为若干定向区段，每个区段采用固定构建方向和平行层面，回转轴只在安全抬升和空移阶段转位。

该范围与项目现有 `pipe2` 数据相符，也有 Siemens NX 公开资料支撑。Siemens 2024 年 12 月的 NX 2412 说明明确提到：Tube Thinwall 支持用户定义 wedge angle，将薄壁管拆分为 wedges，并保持 constant bead heights；这一方法此前用于 Tube Additive Buildup。公开资料没有给出两类操作的完整几何判据、壁厚阈值和填充细节，因此本项目只借鉴已公开的工艺组织，不扩写 NX 未公开的算法定义。

连续五轴管面螺旋另设 `Tube Continuous` 操作。该操作需要旋转最小标架、管面参数化、连续姿态、轴速度规划、奇异规避和碰撞检查，不与首版的分块定向参数混放。

## 3 推荐的用户主流程

模型只在项目层导入一次。Workbench 和 Operation 引用项目中的几何对象，避免二次导入造成对象 ID、单位、坐标和文件版本分叉。

| 阶段 | 用户动作 | 系统响应与门禁 |
| --- | --- | --- |
| 项目 | 新建或打开项目，导入 STEP | 记录文件指纹，检查单位、实体数量、包围盒、空几何和拓扑读取状态 |
| 工艺 | 进入 Tube Workbench，新建 Tube Thin Wall Indexed | 创建可重生成的 Operation，显示该操作支持的几何和参数组 |
| 资源 | 选择 Machine、Nozzle、Material 和 Build Style | 载入轴系、回转中心、行程、速度、喷嘴包络、层高和道宽约束 |
| 制造对象 | 指定打印体、基体或底座、夹具、忽略体 | 建立对象引用；缺少打印体时阻止后续生成 |
| 装夹 | 定义工件原点、初始构建方向和模型到机床的装夹变换 | 显示 Model CS、Build CS、Machine CS，检查右手性和轴向映射 |
| 管特征 | 选择入口与出口，确认流向；选择自动中心线、已有曲线或手工导引 | 识别内外壁、端口、中心线、截面、半径、壁厚、曲率与分支 |
| 局部方向 | 指定起始截面零角方向和接缝参考方向 | 沿中心线计算稳定局部标架；分块模式输出每个区段的构建方向 |
| 切片策略 | 设置目标层高、道宽、壁道数、最大楔角或允许道高误差、表面偏置和接缝规则 | 预览分块边界、层面、预计层数和局部误差；参数越界时给出定位信息 |
| 路径 | 点击生成 | 生成工件坐标下的轮廓、空移、回抽、挤出量和 ToolpathPoint，不直接拼接 G-code 字符串 |
| 运动 | 选择运动学解并计算机床轴位 | 求解 XYZAC、XYZAB 或目标机型轴位，处理回转中心、刀长、角度展开和安全转位 |
| 验证 | 查看分块、逐层、沉积体和机床仿真 | 分开呈现几何路径检查与后处理后 G-code 驱动检查；Error 阻止输出，Warning 写入报告 |
| 输出 | 选择后处理器并导出 | 生成 G-code、`toolpath.json`、`machine_axes.csv`、`warnings.json` 和参数审计信息 |

建议采用左侧 Operation Tree、中部三维视窗、右侧属性编辑器、底部问题列表。顶部进度条可概括为“设置、几何、切片、运动、验证、输出”。用户可回到任一节点修改；上游变化只使依赖的下游结果进入 Dirty 状态，重新生成后再恢复 Valid。该组织方式比一次性模态向导更适合工程软件的反复调整和关联更新。

## 4 坐标系分层

“定义坐标系”需要拆成四类对象，界面中不应只放一个 XYZ 输入框。

| 坐标对象 | 来源 | 用户需要确认的内容 | 用途 |
| --- | --- | --- | --- |
| Model CS | STEP 文件 | 单位和模型朝向 | 保存 CAD 原始几何，不随工艺参数改变 |
| Build CS | 当前装夹 | 原点、初始构建轴、基板平面 | 表达工件路径和初始沉积方向 |
| Machine CS | Machine Profile | 机型与装夹位置 | 定义线性轴、回转轴、回转中心、行程和后处理映射 |
| Tube Frame | 中心线与起始参考方向 | 起点、流向、零角或接缝参考 | 定义截面方位、分块方向和后续连续管面参数 |

Machine Profile 应先于装夹变换确认，因为回转中心和轴方向属于机床定义。Tube Frame 在中心线确认后生成，用户只需指定起始参考方向。连续模式宜采用旋转最小标架；Frenet 标架在直线段、低曲率段和反曲点附近存在不稳定风险。

## 5 几何输入方式

目标产品应保留两种入口：

- 几何识别：用户选择管体、入口和出口，系统提取中心线、截面和壁厚，随后要求用户确认。
- 中心线驱动：用户选择或导入连续曲线，再输入圆形截面尺寸和壁厚。该模式也是识别失败时的可控回退。

`pipe2` STEP 没有可直接选取的中心线，端口、接缝和曲面边界 edge 也不能充当中心线。首个可验收版本可限定为单支、无分叉、恒定圆截面，并要求用户选择管体、入口和出口；系统针对圆柱面、环面和端部截面生成中心线。一般扫掠管、变径管、非圆截面和分支管进入后续范围。

## 6 `pipe2` 证据与验收价值

`example/pipe2/弯管新(1).stp` 含两个实体：半径 25 mm、高 5 mm 的底座，以及外半径 16 mm、内半径 15 mm、名义壁厚 1 mm 的弯管。弯管由入口直段、中心半径 35 mm 且转角 70.513331° 的圆弧、出口直段组成。

`example/pipe2/弯管(1).gcode` 共 679277 行，正式统计记录 669892 个正挤出段。管体包含 852 条闭合挤出轮廓，主要固定姿态为 A=0°、30.379°、50.678°、70.513°。全部 15 条带 A/C 的指令均为 G0，C 恒为 0；出口切线相对 +Z 的夹角与末段 A=70.513°吻合。这组数据支持分块定向判断，可作为几何覆盖、稳定姿态、安全转位和坐标边界的黄金回归样例。

该 G-code 没有层注释和特征类型注释，当前解析器把全部挤出段归入 unknown，层范围为 0..0。后续生成器应输出语义 sidecar 或稳定注释，使分块、层、轮廓、空移、回抽和警告能够被现有预览层可靠识别。

## 7 工程接入边界

现有 STEP 读取、选择状态、源文件指纹、G-code 解析缓存、OpenGL/VTK 预览、后台任务取消和原子提交可以保留。Tube 领域逻辑需要独立于 `ui.py` 和 `gcode_preview.py`，建议形成以下数据边界：

```text
TubeOperationDefinition
→ TubeGeometryAnalysis
→ TubeSlicePlan
→ ToolpathPoint / Toolpath
→ MachineAxisState
→ Postprocessor
→ ValidationReport
```

当前 `ui.py` 已承担首页、会话、成果页、路由和大量控件逻辑，不宜继续堆入 Tube 特例。工作台能力、操作类型、参数页和生成器应由注册表装配。几何分析、路径生成、运动学、后处理和验证各自保留可测试接口，项目文件保存输入指纹、参数版本、几何引用、生成状态和检查结果。

接入前还需处理几项基础风险：现有 Tube 卡片虽然标记 Locked，点击后仍会进入 Imported NC Review；Machine 控件未驱动运动学；`manufacturable_feature_groups` 保存为空；STEP loader 缺少 face 和邻接关系；当前 AC 反算忽略非零 B，旧 AB/AC 样例只是轴名字母替换，不能充当两类机床等价依据。

## 8 方法与差异化沉淀

界面借鉴 NX 的 Setup、Operation Navigator、Generate、Verify 和 Post 组织。项目的技术壁垒应落在可追溯的数据链：输入几何和装夹定义可复现，管特征与分块结果可视化，几何路径与机床轴位分层，错误能定位到对象和路径点，后处理产物带参数与来源指纹。

这套边界可复用于 Rotary、Freeform 和 Curve Workbench。各工作台替换 Feature 与 SlicePlan，MachineAxisState、验证框架、预览层和后处理链保持共享。后续算法改进可用同一组真实样例、结构化报告和黄金数据比较，避免每个工作台形成独立脚本和孤立界面。

## 9 公开依据

- Siemens， [What’s new in NX for manufacturing (December 2412)](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-december-2412/)，2024-12-16。公开说明 Tube Thinwall 的 wedge angle 与 constant bead height 能力，以及 Printer Library、Build Style、Build Rule 和 Material Library。
- Siemens， [What’s new in NX for manufacturing (December 2023)](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-december-2023/)，2023-12-11。公开说明多轴增材的逐层 In-Process Workpiece 检查。
- Siemens， [What’s new in NX for Manufacturing 2606](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-2606-june-2026/)，2026-06-19。公开说明多轴增材的连续回转空移和方向控制等后续能力。
- Siemens， [The ultimate guide to CAM software in 2025](https://blogs.sw.siemens.com/nx-manufacturing/ultimate-cam-software-guide-2025/)。公开给出加载 CAD、选择工序、生成路径、仿真验证、后处理和传输的主链。
- University of Cincinnati Siemens Simulation Technology Center， [Instructions to Start with NX CAM](https://www.ceas.uc.edu/research/centers-labs/siemens-simulation-technology-center/courses---projects/nx-cam/manufacturing-processes-course/manufacturing-processes-example/instructions-nx-cam.html)。页面展示 MCS、WORKPIECE、操作类型、参数、Generate 和 Verify 的交互顺序。
- Hong F, Hodges S. [Open5x: Accessible 5-axis 3D printing and conformal slicing](https://dl.acm.org/doi/10.1145/3491101.3519782). CHI 2022。
- Wang W, Jüttler B, Zheng D, Liu Y. [Computation of rotation minimizing frames](https://dl.acm.org/doi/10.1145/1330511.1330513). ACM Transactions on Graphics, 2008, 27(1)。
