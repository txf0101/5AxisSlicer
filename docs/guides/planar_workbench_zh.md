# Planar 平面工作台使用手册

> 初次使用请先完成[学习总册](user_learning_manual_zh.md)的 L01—L06；本页是 Planar 专项参考。随附平面件用于练习区域、层、道距和孔岛判断，示例参数不是其他零件的默认答案。

本手册覆盖 Region 截面预览、Zigzag Fill、Offset Fill、Thin Wall、Spiral，以及 buildplate-only 垂直支撑。导出前请检查报告和回读状态；离线参考结果不代表真实设备资格。

## 使用前检查

路径操作要求零件、坐标、机型、喷嘴、已审阅材料和装夹全部应用。源 STEP 或这些输入变化会使结果 Stale，需要重新生成。Error 禁止导出；Warning 需查看具体限制。

左侧“制造设置”栏可直接打开七项设置。默认共用公共制造设置；需要只为 Planar 调整时，点“导入公共设置到本工作台”，编辑并返回后可选择保存项目中的独立副本，或“保存到公共制造设置”供其他工作台使用。各按钮的位置和影响范围见[图文点击教程](quickstart_clickthrough_zh.md#公共设置与本工作台设置)。

Zigzag 检查道宽包络、逐区域材料量和未覆盖区域。线间距变小可能导致过填，间距变大可能留下空隙；请结合切层预览和问题列表调整，不要把能导出等同于实体已填满。

Spiral 使用中间 Z 的真实实体有限采样；支撑检查完整运动段与目标 CAD，但零件/支撑联合逐层调度和完整喷嘴扫掠仍未验证。下文图片和数值用于说明界面操作与结果判断，模型和参数变化后须重新检查。

## 入口、前置条件与范围

从 Workbench 首页选择“平面切片 / Planar Slicing”，或在导入 STEP/STP 后进入该工作台。需要有效 STEP 实体、Setup、Model CS、Build CS、Machine、Nozzle 和 Placement。内部长度单位为 mm，进给为 mm/min；截层使用 Workpiece Build-XY 语义。

练习模型为 `example/三叶扇/Supportless_sample.stp` 的 `body_002`。示例值：首层 `Z=60 mm`、层高 `0.6 mm`、道宽 `0.6 mm`、进给 `100 mm/min`。Zigzag、Offset 和 Thin Wall 为单层；Spiral 使用 `Z=60.0` 到 `60.6 mm` 两个相邻层。

工作台包含一个预览操作和五个制造操作。`Planar Region` 只显示分层区域、孔和岛，不生成 NC，也不导出六件套；`Planar Zigzag`、`Planar Offset`、`Planar Thin Wall`、`Planar Spiral` 和 `Planar Support` 都进入共享 Toolpath、MachineAxisTrajectory、ValidationReport、后处理与 G-code 回读链。新建类型和现有操作使用两个独立选择框，可在一个项目中切换多个操作及其 Viewer 结果。

![Planar Zigzag 单层填充线和显示选项](assets/product_delivery/07_planar_full_lines_zh.png)

图中已取消“显示模型”，预览方式为“完整线条（快速）”，因此可以直接看到整层路径。这个单层示例使用 `body_001`、`Z=0.2 mm`；本手册下方的 `body_002`、`Z=60 mm` 是另一组练习设置，不能混用。需要检查路径与模型的贴合关系时重新勾选“显示模型”；需要观察道宽时切换为“沉积道宽”。

## 创建操作与参数

点击“新建操作 / Create operation”，选择 `Planar Region`、`Planar Zigzag`、`Planar Offset`、`Planar Thin Wall`、`Planar Spiral` 或 `Planar Support`，填写下表参数后点击“应用 / Apply”。修改参数、实体或坐标会使已有结果变为 Stale，必须重新生成。

| 参数 | 单位 | 适用操作 | 说明 |
| --- | --- | --- | --- |
| 实体 / Body | — | 全部 | 必填；稳定几何引用参与结果语义哈希。 |
| 首层 Z、末层 Z | mm | 全部 | 截层范围；末层不得低于首层。Spiral 必须形成至少两个相邻层；Support 还要求 `first_layer_z_mm = layer_height_mm`，即首个沉积平面位于 Build Z=0 上方一层高。 |
| 层高 / Layer height | mm | 全部 | 必须大于 0，并受当前道宽高宽比约束。 |
| 道宽 / Bead width | mm | 五种路径操作 | 用于路径、覆盖和材料体积估算。 |
| 进给、空移进给 | mm/min | 五种路径操作 | 分别控制沉积与非沉积移动。 |
| 回抽长度 / Retract length | mm | 五种路径操作 | 路径切换时的回抽与恢复量。 |
| 填充间距 / Line spacing | mm | Zigzag | 往复填充线间距，必须大于 0。 |
| 偏置圈数 / Offset pass count | 次 | Offset | 向内轮廓偏置的最大圈数；窄区、消失区会保留诊断。 |
| 壁厚 / Wall thickness | mm | Thin Wall | 目标壁厚；不足道宽按检查结果处理。 |
| 最大壁道数 / Thin-wall max passes | 道 | Thin Wall | 限制可生成的并行壁道数。 |
| 每轮廓采样数 / Spiral samples per contour | 点 | Spiral | 控制连续 Z 轮廓采样密度。 |
| 悬垂阈值 / Support overhang angle | deg | Support | 相对竖直方向的悬垂判定阈值；范围为 0 至 90，两个端点均不接受。 |
| 支撑 XY 间隙 / Support XY gap | mm | Support | 支撑柱与模型侧壁的水平脱离距离；必须非负。这是有意保留的无支撑区，不应误报为平台不可达。 |
| 支撑 Z 间隙 / Support Z gap | mm | Support | 支撑与接触模型层之间的垂直间隙；必须非负。 |
| 支撑主体线间距 / Support line spacing | mm | Support | 支撑主体 hatch 的线间距；必须大于 0。 |
| 支撑界面层数 / Support interface layers | 层 | Support | 靠近模型的界面层数量，范围 0—100。 |
| 支撑界面间距 / Interface spacing | mm | Support | 界面层 hatch 的线间距；必须大于 0。 |
| 支撑图案 / Support pattern | — | Support | `Lines`（线形）或 `Grid`（网格）；Grid 是相邻层交替正交的 Lines，不在同层重复交叉挤出。 |

### Region 与五种制造操作

- `Planar Region`：检查指定 Z 范围的截面、孔、岛和稳定实体引用。Viewer 可预览区域；该操作没有 MachineAxisTrajectory、G-code 或导出按钮资格。
- `Planar Zigzag`：轮廓优先的往复填充，核对间距、方向、顺序、道宽包络、逐区域材料量与残余。
- `Planar Offset`：从边界向内生成指定圈数的偏置路径；窄区部分消失为 Warning，全部消失为 Error。
- `Planar Thin Wall`：处理开放/闭合薄壁和有限多道；壁厚不足或残余覆盖会给出可定位诊断。
- `Planar Spiral`：受限于单岛无孔且至少两个相邻层，生成连续 Z 路径；多岛、孔或单层输入会拒绝。
- `Planar Support`：从 buildplate 向上建立垂直 Lines/Grid 支撑，分开主体和 interface；范围见“平台垂直支撑”小节。

## 正常流程

1. 打开 STEP，选择 body，确认 Setup 和资源均为有效状态。
2. 新建操作并选择类型；填写参数，点击“应用”。
3. 点击“生成预览 / Generate preview”。路径操作会生成共享 Toolpath、检查报告、Generic XYZAC 离线参考轨迹、G-code 和独立回读。
4. 在三维预览中先显示模型，核对路径与 STEP 的相对位置；模型遮挡路径时取消“显示模型”，用“完整线条（快速）”核对全部沉积线和空移。再切换“沉积道宽”观察宽度，并查看 Warning/Error 与导出按钮状态。
5. 只有状态为 Ready 或允许导出的 Warning，且没有阻止性 Error 时，点击“导出结果 / Export result”。
6. 用“保存项目 / Save project”保存并重新打开。操作、稳定引用、参数和既有资格摘要会恢复；运行时 Toolpath/G-code 不写入项目文件，所以原 Ready/Warning 会在重开后显示 Stale，重新 Generate 后才能查看或导出当前结果。
7. “撤销 / Undo”和“重做 / Redo”覆盖创建、编辑等领域命令；撤销参数修改会恢复上一份有效 Viewer/导出结果。问题列表是可定位索引，激活条目会显示完整 code/object，并尽量定位到对应层或路径点。

### 平台垂直支撑

选择 `Planar Support` 后，系统从首层构建平面向上投影可达的支撑柱，只保留与 buildplate 连通的竖直支撑；支撑主体和靠近模型的 interface 分开记录。悬垂判定使用 `Support overhang angle`，支撑 hatch 可选 `Lines` 或 `Grid`。该操作适合需要从平台起撑的悬垂区域，不提供从模型中途起撑、树状/自由形支撑或多材料支撑。

绑定有效 STEP body，将 `first_layer_z_mm` 设为与 `layer_height_mm` 相等，使首个沉积平面位于 Build Z=0 上方一层高，再设置末层 Z 和其余支撑参数，点击“应用 / Apply”后“生成预览 / Generate preview”。在三维预览中分别检查浅绿色 `support_material` 主体和深绿色 `support_interface` 接触层，确认 Warning/Error、路径顺序和模型间隙，再按通用流程导出、保存和重开。生成时间较长时可点击“取消生成 / Cancel generation”；上一份有效结果和 Viewer 保留。

![平台支撑中文参数与模型总览](assets/planar/current_p01_p07/p07/00_support_grid_zh_1366x768_parameters.png)

以下情况应按问题列表处理：

- `planar.support_not_required` 表示没有检测到需要支撑的悬垂；本次生成不产生可导出结果。它是明确的无输出条件，不是几何内核崩溃；检查模型方向、阈值和层范围后，可保留模型原状或改用普通路径操作。
- `planar.support_region_too_narrow` 表示候选区域窄于当前道宽/间距，不能静默生成；减小道宽或线间距、调整间隙/界面间距，或接受该区域不支撑后重新生成。
- `planar.support_buildplate_first_layer_required` 表示首层 Z 未等于层高，截断了从 buildplate 开始的支撑链；将 `first_layer_z_mm` 改为 `layer_height_mm` 后 Apply 并重新生成。
- `planar.support_unreachable_from_buildplate` 仅表示区域确实被下方模型阻断或无法与 buildplate 连通；XY gap 造成的有意无支撑区不属于此错误。检查下方几何、模型朝向和层范围，必要时拆分模型或改用受支持的几何输入。
- `planar.support_layers_insufficient` 表示至少需要两个有效层；提高末层 Z 或修正层高后重新生成。
- `planar.support_parameter_invalid` 表示角度、间隙、间距、界面层数或图案不在允许范围；按字段修正后 Apply。
- 取消生成：长时间生成可安全取消；上一份有效 Ready 结果保留，确认输入后再重新生成。

## 脚本与 HTTP

受限脚本和 HTTP 与 GUI 使用同一个 `PlanarCommandService`。脚本命令包括 `planar.create_operation`、`planar.set_operation`、`planar.generate_operation`、`planar.export_operation`、`planar.cancel_generation`、`planar.issues`、`planar.validate`、`undo` 和 `redo`。HTTP 对应入口为 `/planar/operation/create`、`/planar/operation/set`、`/planar/operation/generate`、`/planar/operation/export`、`/planar/generation/cancel`、`/planar/issues`、`/planar/validate`、`/planar/undo` 和 `/planar/redo`。创建和设置请求携带 `operation_type`、`operation_id`、`body_id` 及允许的参数字段；生成、导出和取消仍遵守 Ready/Warning/Error/Stale 与事务回滚规则。

## 平台支撑导出与能力边界

允许导出的支撑结果包含六个文件：`main.gcode`、`toolpath.json`、`machine_axes.csv`、`warnings.json`、`preview.json`、`manifest.json`。用 `toolpath.json` 检查 `planar_support`、`planar_support_interface` 等 stage/region 语义，用 `warnings.json` 判断是否存在未服务区域；`main.gcode` 仍应在 G-code 预览页核对。

平台支撑只适用于 buildplate-only 的垂直支撑和 Lines/Grid hatch。路径检查支撑线段与目标 CAD 的相交情况；零件与支撑联合逐层调度、已打印状态和完整喷嘴体扫掠不在此操作的检查范围，结果会保留 `planar.support_joint_schedule_unverified` Warning。它不保证真实打印中的支撑强度、可拆卸性、热传导、材料兼容、复杂悬空腔体或现场碰撞安全。Generic XYZAC、离线回读和 OpenGL 预览不能替代控制器注册、机床标定、试切和现场资格。

在下图的浮空梁练习中，检查平台到模型悬垂区是否存在连续支撑，主体和 Interface 是否分开显示。若出现 `xyzac.rotary_singularity` Warning，须核对机型约束，不要把它当成无警告的 Ready。

![Grid 支撑中文结果](assets/planar/current_p01_p07/p07/01_support_grid_zh_1366x768_ready.png)

![Lines 支撑英文结果](assets/planar/current_p01_p07/p07/02_support_lines_en_1600x900_ready.png)

下图是道宽大于支撑域后的真实错误示例。长错误码完整换行，导出按钮禁用；恢复道宽后可重新生成，见 [中文恢复截图](assets/planar/current_p01_p07/p07/05_support_error_recovered_zh_1600x900.png)。

![支撑区域过窄的错误状态](assets/planar/current_p01_p07/p07/04_support_error_en_1366x768.png)

修改支撑线间距后旧结果进入 Stale、保留预览并禁止导出；对照[输入变化后的状态图](assets/planar/current_p01_p07/p07/06_support_stale_en_1920x1080.png)和[重新生成后的状态图](assets/planar/current_p01_p07/p07/07_support_stale_recovered_zh_1600x900.png)。

对于 `Supportless_sample.stp`，选择 `body_002` 后核对支撑是否从平台连续到悬垂区。若提示端点修正超过容差，操作进入 Error，检查模型、层高和目标 Z；不要绕过该诊断导出。

下表数值是同一练习模型的示例输出。换模型或参数后，以自己的检查报告和 G-code 回读为准；`Warning` 仍须按下节含义处理。

| 操作 | 参数要点 | 路径点 | 结果摘要 |
| --- | --- | ---: | --- |
| Zigzag | 单层，间距 0.6 mm | 142 | 材料量 120.023964 mm³，回读通过。 |
| Offset | 单层，3 圈偏置 | 16 | 材料量 108.863714 mm³，回读通过。 |
| Thin Wall | 单层，壁厚 0.6 mm、最多 3 道 | 6 | 材料量 38.015905 mm³，残余覆盖 Warning，回读通过。 |
| Spiral | 两层，Z=60.0–60.6 mm，64 点/轮廓 | 129 | 连续 Z 路径；离散层投影 Warning，回读通过。 |

查看 Offset、Thin Wall 或 Spiral 时，先保留模型确认截面位置，再取消“显示模型”，用“完整线条（快速）”检查轮廓和道间连接。上方 Zigzag 图片示范了该切换。Thin Wall 的残余覆盖 Warning 表示参数与区域尚未完全覆盖，应逐项审阅。Spiral 必须至少跨两个相邻层；单层输入会被拒绝。

## Warning、Error 与恢复

| 提示或状态 | 含义 | 恢复动作 |
| --- | --- | --- |
| `planar.spiral_layers_insufficient` | Spiral 没有至少两个相邻层。 | 把末层 Z 调高至少一个有效层高，应用后重新生成。 |
| `planar.coverage_residual_high` Warning | 路径未覆盖完整采样区域。 | 检查壁厚、道宽、最大壁道数和区域；需要完整覆盖时调整参数或改用合适操作，再生成。 |
| `planar.spiral_discrete_layer_projection_only` Warning | Spiral 使用离散层投影近似。 | 审阅最大投影偏差和预览；它不代表连续实体资格。 |
| `xyzac.rotary_singularity` Warning | 离线参考轴轨迹在回转奇异邻域保留了 C 轴。 | 查看 `warnings.json` 与机型约束；不得据此认定真实控制器可运行。 |
| 参数、坐标或资源 Error | 层高、道宽、进给、Setup 或资源不合法，或运动检查阻止导出。 | 按问题列表修正具体字段；Error 存在时导出保持禁用。 |
| Stale | 参数、实体引用、坐标或资源在生成后改变。 | 不使用旧结果导出，重新 Generate。 |
| 取消生成 | 用户取消或后台任务中断。 | 上一份 Ready 结果保留；确认输入后重新生成。 |

![Spiral 单层输入：首层与末层 Z 相同](assets/planar/current_p01_p07/p06/07_planar_spiral_error_zh_1366x768.png)

图中首层和末层都为 60 mm，尚未构成连续螺旋所需的两个相邻层；导出按钮禁用。错误详情需在右侧参数区向下滚动查看。将末层改为相邻层后，再应用、生成并检查回读：

![Spiral 恢复后的英文结果，1600×900](assets/planar/current_p01_p07/p06/08_planar_spiral_recovered_en_1600x900.png)

## 导出文件

每次允许导出的路径操作生成六个文件：`main.gcode`、`toolpath.json`、`machine_axes.csv`、`warnings.json`、`preview.json` 与 `manifest.json`。`toolpath.json` 保留 operation、layer、region、事件和材料语义；`machine_axes.csv` 仅为参考轴轨迹。导出后核对 `manifest.json` 的文件清单和 `warnings.json` 的剩余问题。

## 能力边界

Generic XYZAC 仅为离线参考 profile，用于轴轨迹、格式和回读检查。控制器语义、真实机床标定、现场碰撞资格和试切沉积均未验证。
