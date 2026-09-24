# Curve 工作台图文手册

> 初次使用请先完成[学习总册](user_learning_manual_zh.md)的 L01—L06；本页是 Curve 专项参考。叶轮边链用于练习有向链和法向，换零件后必须重新选择 edge、邻面和工艺参数。

Curve 工作台沿 STEP 有向 edge 链生成 Buildup、Multi-pass Buildup 和 Offset Buildup。内部长度为 mm、角度为 rad；界面长度显示 mm。路径从 Source/Model frame 转换到 Build frame，再进入 Workpiece/Machine frame 做离线轨迹检查。

左侧“制造设置”栏默认使用公共设置。需要只为 Curve 调整机床、喷嘴、材料或坐标时，先点“导入公共设置到本工作台”，编辑后保存项目；需要让其他共用工作台也使用这份设置，再点“保存到公共制造设置”。具体按钮和作用范围见[图文点击教程](quickstart_clickthrough_zh.md#公共设置与本工作台设置)。

## 1. 前置条件与入口

1. 打开 STEP，并在公共制造设置中完成零件、Model CS、Build CS、机型、喷嘴、已审阅材料和安装位置。
2. 回到工作台首页，进入“曲线工作台 / Curve Workbench”。
3. 在“Viewer 选取类型”中选“边”，按行进顺序逐条点击；需要邻面时切到“面”再点该面。向下滚动单击“采用 Viewer 已选边”。也可以直接填写稳定 edge ID。
4. 双邻面的边必须确认“法向邻面 ID”；若没有权威邻面，选择“用户指定方向”并填写单位法向 X,Y,Z。

生成后，右侧默认隐藏 CAD 模型以显示完整沉积线。需要核对路径与零件的相对位置时勾选“显示模型”；“完整线条（快速）”适合检查全程，“沉积道宽”适合查看局部线宽。

项目保存的是 edge/face 的完整 `GeometryReference` 描述符、父实体信息和 kernel signature。STEP 更新后会做唯一重绑；缺失、重复候选或拓扑漂移会使操作无效并要求重新选择。

![在 Viewer 中选边并写入有向边链](assets/product_delivery/20_curve_edge_selected_zh.png)

图中蓝色边已通过“采用 Viewer 已选边”写入“有向边链”；这是几何选择状态，还没有创建或生成操作。选择自己的模型时，边 ID 会不同。左侧设置栏和中间操作栏均可独立滚动。

## 2. 边链顺序、反向和法向

- “有向边链”按逗号分隔，顺序就是生成顺序。
- “反向标志”与 edge 一一对应，`0` 保持 STEP 方向，`1` 反向。反向会同时改变起止端、切向和 Offset 的横向侧别。
- 相邻 edge 的端点距离必须小于“链连接容差”。断链不会自动跳过或用空移掩盖。
- “明确邻面”从指定 trimmed face 计算每个采样点的曲面法向；双邻面时不猜测。
- “用户指定方向”适用于没有权威邻面的空间曲线。方向与切向平行时无法定义喷嘴姿态，生成会报错。

## 3. 三种操作

| 操作 | 路径规则 | 关键检查 |
| --- | --- | --- |
| Buildup | 沿链按弧长生成一条沉积道 | 精确端点、弧长、连续切向、法向/nozzle axis、材料量、起止事件 |
| Multi-pass Buildup | 按层高沿法向累计抬升；相邻层交替方向 | 层数、累计高度、换向、Retract/Prime/Dwell 与沉积段分离 |
| Offset Buildup | 以原链为第 0 道，沿 `normal × tangent` 正方向生成横向多道 | 道间距、道序、局部标架反转、自交、trimmed face 越界 |

![当前界面选面和选边；橙色为面、蓝色为边](assets/product_delivery/06_curve_pick_edge_face_zh.png)

图中只完成了 Viewer 几何拾取，还没有创建或生成操作。生成后请在结果预览中单独检查路径；不能以 CAD 高亮代替路径检查。

![Buildup 生成 Toolpath 的路径专用视图](assets/curve/current_c01_c05/06_curve_buildup_zh_1366x768_path_only.png)

![Multi-pass 三层路径专用视图](assets/curve/current_c01_c05/07_curve_multi_pass_en_1600x900_path_only.png)

![Offset Buildup 三道横向路径专用视图](assets/curve/current_c01_c05/08_curve_offset_buildup_en_1920x1080_path_only.png)

后两图关闭了模型显示，避免 CAD 遮住路径。生成时先打开模型核对路径落在哪片面上，再关闭模型查看所有道；该显示切换不改变输出 G-code。

图中叶轮样条的 Offset 示例把反向标志设为 `1`，使 `normal × tangent` 的正方向进入所选 trimmed face。道间距输入为 3.0 mm；若路径被拒绝为 `curve.offset_outside_face`，应检查所选面和边方向，再重新生成，不能用重叠路径冒充多道。示例数值仅适用于该模型。

## 4. 参数

表中默认值和叶轮截图中的设置用于学习界面。自己的曲线模型须按实际机床、喷嘴、材料、目标道宽和试验结果重新确定，不能照抄案例数值。

| 参数 | 默认值 | 作用与有效范围 |
| --- | ---: | --- |
| 弧长采样步长 | 1.0 mm | 大于 0；控制相邻采样目标距离 |
| 弦误差 | 0.05 mm | 大于 0；进入路径长度验收容差 |
| 链连接容差 | 0.01 mm | 大于 0；用于相邻边端点和闭合判断 |
| 道宽 | 0.6 mm | 大于 0；参与沉积体积和碰撞包络 |
| 层高 | 0.2 mm | 大于 0，且不超过道宽的 2 倍 |
| 沉积进给 | 900 mm/min | 大于 0；写入沉积点与 G-code |
| 空移进给 | 1800 mm/min | 大于 0；只用于 approach/travel |
| 回抽长度 | 1.0 mm | 大于 0；写入独立 Retract/Prime 事件 |
| 层间停留 | 0 s | 大于等于 0；非零时写入 Dwell 事件 |
| 层数 | 3 | 1—100；仅 Multi-pass 使用 |
| 横向道数 | 3 | 1—100；仅 Offset 使用 |
| 横向道间距 | 0.6 mm | 大于 0；沿局部横向标架累计 |

修改几何、Setup、资源或工艺参数后，已有结果显示 Stale，必须重新 Generate。显示质量、相机和可见性不参与语义哈希，不改变路径。

## 5. 生成、取消、检查与 Viewer

单击“应用”把界面值送入统一领域命令，再单击“生成与检查”。生成链为：

`Geometry → CurvePlan → shared Toolpath/events → MachineAxisTrajectory → ValidationReport → Postprocessor → G-code readback`

状态含义：

- Ready：离线生成和回读通过，可以导出。
- Warning：可以导出，警告随结果保存；应查看问题列表和 `warnings.json`。
- Error：生成、运动检查或回读失败，禁止导出。
- Stale：输入已变化，旧结果不可导出，重新生成后恢复。

生成期间“取消生成”可用。取消不会破坏上一份有效 Toolpath；界面继续显示原 Ready/Warning 结果。Viewer 中单道、多层和横向多道都来自生成结果，不从历史 G-code 伪造。

## 6. 典型错误与恢复

### 6.1 断链、方向和法向

- `curve.chain_disconnected`：检查 edge 顺序；必要时将对应反向标志改为 `1`。
- `curve.normal_ambiguous`：该 edge 有多个邻面，填写权威 face ID。
- `curve.normal_missing`：整条链没有共同邻面，重新选择链/邻面，或使用明确的用户法向。
- `curve.normal_parallel_tangent`：用户法向与局部切向平行，改用可定义喷嘴姿态的方向。
- `curve.edge_degenerate`：零长或退化边不能生成，回到 STEP 修复或重选。

### 6.2 Offset 越界

![Offset 跨出 trimmed face，Error 阻止导出](assets/curve/current_c01_c05/04_offset_failure_zh_1366x768.png)

该例在 8 × 6 × 1 mm 解析 STEP 上选择了会向面外偏移的边，第三道越过 trimmed face，状态显示 `curve.offset_outside_face`，导出按钮禁用。

![改选可偏置边后的恢复结果](assets/curve/current_c01_c05/05_offset_recovered_zh_1366x768.png)

改选面内方向的 edge、重新“应用”和“生成与检查”后恢复为 Warning；警告来自 Generic XYZAC 参考机型，不影响离线六件套导出。

## 7. 六件套与回读

每个 Ready/Warning 结果导出一个目录，必须同时包含：

| 文件 | 用途 |
| --- | --- |
| `main.gcode` | 按注册 Generic XYZAC 语义生成的离线 NC |
| `toolpath.json` | shared Toolpath 点、事件、层/区域、姿态和材料量 |
| `machine_axes.csv` | XYZAC 轴轨迹、时间和 FK 误差 |
| `warnings.json` | Warning/Error 代码、对象和上下文 |
| `preview.json` | Viewer 使用的预览数据 |
| `manifest.json` | 输入、算法版本、语义哈希、输出哈希和导出资格 |

导出前会按同一注册控制器语义独立回读 `main.gcode`，核对点数、轴值、进给、挤出和事件。Error 或回读失败时六件套导出被阻止。

## 8. 撤销、保存重开与 STEP 更新

- Create、Apply 和参数修改支持 Undo/Redo；撤销恢复运行时有效结果，不把旧结果误标成新参数结果。
- 项目保存 Curve 操作、稳定几何引用、Setup、资源和当前工作台。生成 Toolpath 不嵌入 `project.json`。
- 重开后引用和参数恢复，旧 Ready/Warning 结果按 Stale 处理，需要重新生成。
- “更新原始 STEP”在后台解析。解析期间若 Tube、Planar 或 Curve 输入发生变化，提交会拒绝，避免覆盖并发编辑。

## 9. 受限脚本与 HTTP

脚本只接受字面量和 `curve/曲线` namespace，不执行 Python、文件、进程或网络调用。事务不能跨工作台。

```python
curve.create_operation(operation_type="curve_buildup", operation_id="curve-1")
curve.set_operation(
    operation_id="curve-1",
    edge_ids=["body_002_edge_0011"],
    reversed_flags=[False],
    normal_mode="adjacent_face",
    normal_face_id="body_002_face_0006",
    feedrate_mm_min=900.0,
)
curve.generate_operation(operation_id="curve-1")
curve.export_operation(operation_id="curve-1", destination="output/curve-1")
```

HTTP 使用同一命令内核：`/curve/state`、`/curve/issues`、`/curve/validate`、`/curve/operation/create`、`/curve/operation/set`、`/curve/operation/generate`、`/curve/generation/cancel`、`/curve/operation/export`、`/curve/undo`、`/curve/redo`。远程访问、token 和绑定地址仍受应用 HTTP 设置约束。

## 10. 当前能力边界

Curve 适用于沿 STEP edge 链的有限沉积操作。锐角标架反转、自交、裁剪和退化区域按错误退出，不静默丢道。Tree/Organic、自由曲面区域填充、一般工业支撑和实机工艺资格不属于该工作台的适用范围。

Generic XYZAC、离线 IK/FK、轴限、速度/加速度、奇异检查、保守碰撞接口、G-code 回读和 OpenGL Viewer 已验证。真实控制器语义、真实机床标定、现场夹具/喷嘴完整碰撞、材料适配、可拆卸性和试切均未验证。

示例模型的许可证不随软件仓库许可证自动授予。将模型或 G-code 用于再分发前，请单独核对其来源与授权。
