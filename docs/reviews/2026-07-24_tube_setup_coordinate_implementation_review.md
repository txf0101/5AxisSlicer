# 管状切片第一阶段 Setup 与坐标闭环实施复盘

## 1 实施范围与基线

本轮工作位于 `codex/tube-setup-coordinate` 分支，起点为 `main@1c30f50`。交付边界止于 `Coordinates Valid`、`Setup Ready` 及项目保存重开。中心线、Tube Frame、分块、切层、路径生成、逆运动学和 NC 输出仍属于后续阶段。

开发前核对了 `圭臬/开发目标文档.docx`：文件大小 492214 字节，修改时间为 2026-07-06 13:45:16。本轮保持该文档只读，并阅读了 `docs/reviews/2026-07-22_tube_slicing_user_workflow_review.md`。既有复盘给出的 NX 式对象组织、坐标分层和 Tube Thinwall 范围构成此次实现的产品依据。

首版界面限定一个 Manufacturing Setup 和一条交互创建的 `Tube Thin-Wall Indexed` 操作。项目 JSON 继续采用 `setups[]`、`operations[]` 数组，为后续格式扩展保留空间；当前 UI 遇到多 Setup 项目会明确拒绝打开，防止重存时遗漏数据。

## 2 已落地的用户流程

| 用户动作 | 应用行为 | 完成门禁 |
| --- | --- | --- |
| 导入 STEP | 后台读取单位、solid、sheet、四级拓扑、装配名称和几何签名 | 未知或非法单位要求用户选择 |
| 进入 Tube Workbench | 显式创建 `Tube Thin-Wall Indexed` | 交互创建上限为一条 |
| 确认 Part | 所有封闭 solid 初始处于未分配候选区，可把多个 solid 放入同一 Part | Part 至少含一个真实 CAD solid |
| 选择资源 | 从内置模板、用户库或项目快照选择 Machine、Nozzle、Material | 资源缺失不妨碍坐标编辑 |
| 定义 Model CS | 依次确认原点、Z、X，可拾取、数值输入和 Flip | 三项引用均确认且形成右手刚体坐标 |
| 定义 Build CS | 独立采用三参考法，数值默认在 Model CS 输入 | 保存前换算到 Source CS |
| 定义 Placement | 选择 Machine Profile 安装位，编辑局部六自由度微调 | 安装位属于当前机床，矩阵帧标签精确匹配 |
| 保存并重开 | 保存内嵌 STEP、资源快照、坐标定义、安装位和选择 | 哈希、拓扑、资源和刚体变换全部复核 |

`pipe2` 中的圆盘和弯管均进入 Part，实测对应 `body_001`、`body_002`。sheet、Ignore、Fixture 预留实体和未分配实体不会进入后续制造计算。Fixture 角色保留在领域枚举中，首版页面未开放夹具或导入式 Substrate。

## 3 架构边界与坐标约定

Tube 业务没有继续堆入 `ui.py`。当前职责划分为：

- `manufacturing/coordinates.py`：刚体变换、坐标引用、坐标定义、四元数和局部微调；
- `manufacturing/references.py`：几何签名、候选审计和唯一重绑定；
- `manufacturing/machine.py`：轴链、安装位、打印板、控制器字映射和正运动学；
- `manufacturing/resources.py`、`manufacturing/library.py`：资源模板、冻结快照、用户库和分叉审计；
- `manufacturing/setup.py`：制造对象、节点状态、稳定问题码和 Setup 汇总；
- `tube_controller.py`：Draft、Apply/Cancel、依赖传播和领域权威校验；
- `tube_ui.py`：固定树、编辑器、问题列表、视图切换和自动化适配；
- `ui.py`：应用壳、后台任务和项目提交边界。

全部几何计算采用列向量、右手系、毫米和弧度。界面角度显示为度。`RigidTransform` 使用 `T_target_from_source` 命名，构造时检查有限值、齐次末行、正交性和行列式；缩放、剪切和左手矩阵无法进入已应用状态。

```text
p_target = T_target_from_source · p_source

T_model_from_build = T_model_from_source · inverse(T_build_from_source)
T_machine_from_build = T_machine_from_mount · T_mount_from_build
T_machine_from_source = T_machine_from_build · T_build_from_source
```

Model CS 的数值参考位于 Source CS。Build CS 的数值输入默认位于 Model CS，controller 在提交前换算到 Source CS。X 先投影到 Z 的法平面，再计算 `Y = Z × X`。零向量、X/Z 共线及非有限值会中止 Apply。

Placement 把几何基准和微调分开保存，组合顺序固定为：

```text
T_ref · Translate(dx,dy,dz) · Rx · Ry · Rz
```

持久化旋转以正交基和规范化四元数表达，Euler XYZ 只服务于编辑器。180° 旋转的四元数符号已经规范化，避免等价姿态在保存重开后出现正负跳变。

Draft 位于已应用 Setup 之外。Apply 先完成全部校验，再原子替换已应用对象；Cancel 丢弃草稿。批量 Apply 按 Model CS、Build CS、Placement 的依赖顺序提交，任一环节失败会恢复提交前状态。保存遇到未应用 Draft 时要求 Apply、Discard 或取消。

## 4 STEP、拓扑引用与源文件更新

STEP 读取现在覆盖 solid、free shell、独立 free face、face、edge、vertex、邻接、包围盒、表面积、体积、质心、曲面/曲线类型、半径、轴线、单位和 XCAF 装配名称。独立 free face 会提升为 `sheet` body；solid 或 free shell 内已经拥有的 face 使用 OCCT shape map 去重。

已识别长度单位换算为毫米。毫米声明会忽略多余 override，英寸只换算一次；缺少声明或遇到不支持的声明时，用户选择构成明确的换算依据。混杂单位上下文会被拒绝。

遍历 ID 仅承担当前 CAD 会话的定位。持久引用另存结构化签名，描述父体、拓扑类型、尺寸、质心、包围盒、曲线或曲面参数、半径、轴线和邻接。显式“从原文件更新”会比较旧模型与新模型，只接受唯一候选；缺失或歧义结果进入 Invalid。项目重开针对权威内嵌 STEP 采用更严格的 ID 到签名映射复核，OCCT 遍历次序变化会触发完整性错误。

坐标引用接入当前 CadModel 后会重建规范引用，核对 object ID、geometry type、父体、完整签名和解析值。`face_pick` 还要验证命中点的物理归属：真实拓扑使用 OCCT 求 trimmed face 最近点，无内核测试模型只在平面与边界都可证明时采用回退。篡改点、远离面域的点或无法权威复算的引用均进入 Invalid。

STEP 导入、STEP 源更新、项目重开和 Result Preview G-code 读取由 QThread 协调器执行。取消检查分布在哈希、解析阶段边界和项目校验阶段。OCCT 原生 `ReadFile` 调用本身没有可注入的中断点，运行到该调用返回后才能响应取消；这个限制保留在已知边界中。

## 5 Machine、Nozzle、Material 与资源快照

Machine Profile 使用父子 Link 轴链，保存轴类型、方向、回转中心、零偏、软限位、速度、加速度、工具侧或工件侧归属及控制器字映射。配置校验覆盖重复 ID、父子环路、非法轴向、限位和串联开链。当前运动学服务实现正运动学与安装位变换。

内置 `Cartesian Reference` 和 `Generic XYZAC Reference` 均带 `reference_only`。它们可以完成装夹和坐标验证，同时产生 `MACHINE_REFERENCE_ONLY` Warning。机床标定、逆运动学、多解选择、奇异区和碰撞求解尚未进入本轮。

Nozzle 内置 0.4、0.6、0.8 mm 身份模板。模板保留接口、孔径、丝径、结构材料、流量类别、耐温、耐磨、来源和 `outer_profile_rz_mm` 字段。内置身份模板没有虚构长度和碰撞外形，因而不能单独达到 Setup Ready；手工验收使用了一份字段完整的临时 0.4 mm brass profile。

Material 仅覆盖 1.75 mm FFF/FDM PLA、PETG、ABS。固定上游为 Ultimaker `fdm_materials` commit `886e7ad927463493cc9c64f427b1ae2cf4ce12c1`，保存来源 URL、revision、文件路径和 SHA-256。模板中的单点建议值分别为 PLA 200/60 °C、PETG 215/70 °C、ABS 230/80 °C，均取自各自固定来源文件。模板带 `review_required`，用户确认后才进入 Valid。

内置模板为不可变对象。编辑操作会生成新 UUID 并写入用户资源库。项目保存完整冻结快照；用户库后来发生分叉、缺失或单条 JSON 损坏时，旧项目仍使用快照，并在问题列表记录 Warning。Setup 内快照是 Tube 权威值，顶层同类资源字段仅作兼容镜像，两份数据同时存在时必须完全一致。

喷嘴温度、热床温度、层高、道宽、冷却、回抽和体积流量仍归入后续 Process Profile。

## 6 项目 v2 与保存安全

项目目录继续采用 `project.json`、`source/`、`preview/`。STEP 和可用 G-code 以完整 SHA-256 加原后缀命名。G-code 加载结果绑定 SHA-256、字节数和纳秒时间戳；保存前后重新核对源文件，拒绝摘要与实际字节分叉。内容寻址副本先写临时文件并校验，再原子发布；正确的既有目标直接复用，失败保存不会提前覆盖旧清单引用的权威副本。项目根、`source/`、`preview/`、清单和发布目标同时检查 symlink、junction 与 reparse point 边界。

v2 重开检查：

- `project_path` 必须为项目目录内的安全相对路径；
- STEP、G-code 和资源快照哈希必须一致；
- body、face、edge、vertex 的数量及 ID 到 signature 映射必须一致；
- Setup、Operation、坐标和刚体矩阵必须可反序列化并满足领域约束；
- 顶层资源镜像与单一 Setup 内同类快照不能分叉。

项目内 STEP 是重开的权威来源，外部原始路径只用于用户显式发起“从原文件更新”。v1 在内存迁移成未配置 Setup，第一次保存 v2 前生成 `project.v1.json`。高于当前版本的项目直接拒绝。

内容寻址文件目前没有自动垃圾回收。多次更新可能留下旧的未引用副本；保留旧副本有利于失败恢复，后续可在具备引用扫描和恢复策略后增加安全清理。

## 7 NC 预览坐标安全修订

旧预览会默认套用 Generic XYZAC，并按单段决定是否降级。同一文件含 A 段和非零 B 段时，画面可能同时出现工件坐标与 Machine XYZ。

当前默认 `controller_semantics=None`。调用方显式传入已注册语义后，解析器才执行 AC 重建。解析结束时执行文件级预检：

- 非零 B；
- U、V、W 字；
- 未注册或未确认的控制器语义；
- 任一运动学诊断。

命中任一条件时，全部 segment 和 timeline 统一恢复 Machine XYZ，并生成稳定问题码。缓存版本升级为 v7，cache key 含控制器语义，Machine 与 AC 结果不会互相复用。

已确认的 AC 语义仍采用 `Rz(-C) · Rx(-A)`。A=70.513°、C=0° 时，固定机头 `-Z` 在工件系回归为约 `(0, -0.942719, -0.333588)`。

## 8 真实检查过程与验收结果

初版实现达到 `216 passed` 后进行了独立工程审查。首轮审查发现旧 manifest 可能在序列化失败前失去固定名源文件、v2 未复核拓扑映射、NC 可产生段级混合坐标、Operation Setup 失配仍可能显示 Ready、无 CAD Part 与伪造安装位缺少权威校验、无模型项目会残留 Viewer 状态。后续门禁继续发现 G-code 跨项目串扰、坐标槽位标签错配、Dirty Placement 被派生变换继续消费、源 G-code 摘要与字节分叉、失败保存提前覆盖内容寻址旧副本、symlink/reparse point 越界、GeometryReference 及 `face_pick` 篡改、同步兼容入口冻结 Qt 事件分发，以及嵌套事件循环遗留计时器造成的 Windows offscreen 退出崩溃。每项问题均形成稳定失败用例后再修复。

第一次全仓门禁在约 79% 处出现 5 个断言失败，随后于 `pipe2` 保存重开用例触发 Windows access violation。3 个失败来自后台 G-code 审计与新指纹契约的衔接，2 个来自源更新测试仍按旧的静默错误与状态语义断言。崩溃根因是 Model 与 Project 两条同步兼容入口保留了 parented QEventLoop 及未停止的轮询计时器；统一改为局部事件循环、具名临时连接、显式断开并等待 QThread 完整回收后，Tube UI 17 项和第二轮全仓均正常退出。

最终检查记录如下：

| 检查 | 结果 |
| --- | --- |
| `python -X faulthandler -m pytest -q` | 271 passed，2 skipped，23 warnings |
| 坐标、Setup、资源、项目、Tube UI 专项 | 118 passed，2 skipped |
| `tests/test_tube_ui.py` | 17 passed，无退出崩溃 |
| Black check | 通过 |
| 本轮变更 Python 文件的 Flake8，忽略 `E203,W503,E402,E501` | 通过 |
| Mypy，制造领域及 Tube、项目、STEP 核心模块 | 通过 |
| `git diff --check` | 通过 |

23 条 warning 均来自 CadQuery 测试辅助函数 `save()` 的 FutureWarning，没有领域校验、线程或渲染 warning。2 个 skipped 是当前 Windows 权限无法创建符号链接，相关路径防护仍由可创建 symlink 的环境执行对应回归。

`pipe2` 手工保存重开脚本的结果为：

```json
{
  "solids": 2,
  "faces_per_solid": [3, 8],
  "part_body_ids": ["body_001", "body_002"],
  "coordinates_valid": true,
  "setup_ready": true,
  "warning_codes": ["MACHINE_REFERENCE_ONLY"],
  "reopened_coordinates_valid": true,
  "reopened_setup_ready": true,
  "round_trip_equal": true,
  "embedded_step_name": "116e99fd43492bd1f4f519c80c93cd1f7cd0bf2cb6861b3e123148e4031a0d4b.stp"
}
```

材料来源在 2026-07-24 联网重新读取固定 commit，字节数和 SHA-256 如下：

| 文件 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `generic_pla_175.xml.fdm_material` | 9840 | `5bc7c562e14cb10c15323bca26f1afddedcf6e18166c92adf4d638611907a4be` |
| `generic_petg_175.xml.fdm_material` | 4564 | `d1e41783828696f374f6267bc9f07b8336a0ceedfafbf32dcbaf930d5595c0e3` |
| `generic_abs_175.xml.fdm_material` | 5276 | `6687016b42e144e8ae717cf87024f383815c61b3ae300ac1adb6045093c9d1b4` |

OpenGL 与 VTK 用例均覆盖 body、face、edge、vertex 拾取，坐标标架、打印板和装夹变换。Qt offscreen 用例覆盖操作创建、Part 确认、三参考拾取、两点方向、Flip、Apply/Cancel、Dirty 传播、问题跳转、模型/机床视图和中英文 1600 × 900 布局。

## 9 未完成边界与下一阶段入口

- Tube 中心线、Tube Frame、分块、层面和路径点尚未生成；
- Process Profile 尚未建立，Material Profile 不保存工艺参数；
- 参考机型没有真实标定值，未来 NC 输出需继续受阻；
- 逆运动学、多解、奇异区、碰撞和软限位轨迹检查尚未求解；
- 夹具和导入式 Substrate 未开放交互；
- UI 当前只接受一个 Setup，项目格式中的多 Setup 需要后续工作台注册和导航设计；
- OCCT 原生读取阶段只能在调用边界响应取消；
- Operation Session 的 `/gcode/open` 仍采用同步解析；Result Preview G-code 与项目重开已进入后台协调器；
- `preview.gcode` 与 `result_preview` 尚未形成完整的保存恢复闭环；
- 手工验收使用的完整喷嘴碰撞包络没有实物测量依据，Setup Ready 只表达当前字段与审核门禁完整，碰撞及 NC 输出仍需真实标定；
- 当前任何非零 B 都回退 Machine XYZ；未来注册含工具侧 B 轴的控制器语义时，需要补齐工具链与工件链的相对正运动学；
- 内容寻址旧副本尚无自动垃圾回收；
- 用户资源库采用本机目录，团队共享、签名发布和权限治理尚未设计。

## 10 可复用资产与工程判断

本轮沉淀的核心资产集中在四条可审计数据链。

几何引用链把“用户选中了哪个遍历序号”提升为签名、邻接、候选证据和唯一匹配结果。它可直接服务 Planar 的加工面、Rotary 的回转轴参考和 Freeform 的导引面。

坐标链把 Source、Model、Build、Mount、Machine 的方向写进类型和矩阵标签。任何工作台都可复用同一刚体服务，减少局部矩阵乘法和轴顺序分支。

资源链把模板、用户副本、项目快照、来源 revision 和内容哈希连成闭环。旧项目的可重复性不依赖用户库当前状态，这项约束可延伸到 Process Profile、Build Style 和后处理器。

Viewer 合同统一了四类拾取、命中位置、坐标架、打印板和模型变换。OpenGL 与 VTK 的一致性由相同领域数据和双后端测试约束，后续几何算法无需分别维护界面语义。

这些资产形成的差异点可以用失败行为检验：歧义引用会 Invalid，资源分叉会 Warning，非刚体矩阵无法 Apply，未知 NC 语义保留 Machine XYZ，失败保存不会破坏旧项目。约束均有问题码、序列化证据和测试用例，后续算法可沿用同一审计边界。

## 11 资料依据与证据等级

- [NXOpen CAM Geometry](https://nxopencsdocumentation.thescriptingengineer.com/NX2022_1/NXOpen.CAM.Geometry.html)：由 NXOpen.dll 生成的公开文档镜像，用于核对 CAM Geometry 对象组织；证据等级为公开 API 镜像。
- [NXOpen MillGeomBuilder](https://nxopencsdocumentation.thescriptingengineer.com/NX2022_1/NXOpen.CAM.MillGeomBuilder.html)：由 NXOpen.dll 生成的公开文档镜像，用于核对几何容器与 Builder 关系；证据等级为公开 API 镜像。
- [University of Cincinnati, Instructions to Start with NX CAM](https://www.ceas.uc.edu/research/centers-labs/siemens-simulation-technology-center/courses---projects/nx-cam/manufacturing-processes-course/manufacturing-processes-example/instructions-nx-cam.html)：高校 Siemens 技术中心教程，用于核对 MCS、WORKPIECE、Operation、Generate、Verify 的交互顺序；证据等级为公开教学资料。
- [Open CASCADE Technology 7.8.0 Reference Manual](https://dev.opencascade.org/doc/occt-7.8.0/refman/html/)：用于核对 STEPControl、XCAF、TopExp 和 shape map 接口；本机 OCP 版本为 7.8.1.1。
- Ultimaker `fdm_materials` 固定 commit： [PLA](https://github.com/Ultimaker/fdm_materials/blob/886e7ad927463493cc9c64f427b1ae2cf4ce12c1/generic_pla_175.xml.fdm_material)、[PETG](https://github.com/Ultimaker/fdm_materials/blob/886e7ad927463493cc9c64f427b1ae2cf4ce12c1/generic_petg_175.xml.fdm_material)、[ABS](https://github.com/Ultimaker/fdm_materials/blob/886e7ad927463493cc9c64f427b1ae2cf4ce12c1/generic_abs_175.xml.fdm_material)；证据等级为固定 revision 的上游原始文件，内容哈希已在本轮复核。
