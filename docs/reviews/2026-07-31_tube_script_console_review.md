# Tube Setup 脚本控制台与开放配置实施复盘

## 1 实施范围与基线

本轮分支为 `codex/tube-script-console`，起点为 `main@ad451dc`。交付内容限定在 Tube Setup 的脚本化设置、事务提交、会话撤销、开放 YAML 工作文件和桌面控制台。中心线、Tube Frame、分块、切层、路径生成、逆运动学与 NC 输出没有进入本轮。

修改前再次核对 `圭臬/开发目标文档.docx`，文件大小为 492214 字节，修改时间为 2026-07-06 13:45:16；交付结束前复查结果相同。该文档全程只读。实现沿用 `docs/reviews/2026-07-24_tube_setup_coordinate_implementation_review.md` 已确认的 Source、Model、Build、Mount、Machine 坐标分层和项目 v2 权威边界。

用户提出的交互参照 PowerShell 窗口和求解器关键字文件。产品决策保留命令行手感，将执行面收缩为 Tube 领域指令。`.py` 文件只承担受限命令文本的载体，运行时不会调用 Python 解释器。可移植配置采用标准 `.yaml` 后缀，没有另造项目专属扩展名。

## 2 用户可见结果

Tube Workbench 激活后，主窗口底部显示“设置脚本” Dock。窗口可以拖动、收起、关闭和重新打开；展开高度、折叠状态与最近 200 条输入保存在本机 `QSettings`。1600 × 900 的 Qt 回归中，默认 Dock 约 190 px，三维区保留 420 px 以上高度。

交互入口包括单行执行、脚本块执行、命令历史搜索和上下文补全。补全候选覆盖公开命令、中文别名、资源 ID、安装位 ID 与实体 ID；UUID、点号和连字符均按同一 token 区间替换。Dock 内任一子控件获得焦点时，Viewer 的 `F`、`H`、`Esc`、`Ctrl++` 和 `Ctrl+-` 暂停，页面切换、收起或隐藏 Dock 后恢复原 QAction 状态。

工具区提供脚本载入、YAML 导入、YAML 副本导出、配置目录打开、输出清空、草稿应用和草稿放弃。中文与英文界面的对话框、错误位置、配置状态和恢复提示均有对应文本。输出区最多保留 2000 个文本块，避免长时间会话持续增长。

公开 API 固定使用 `tube.*`，中文入口使用 `管状.*`。一条成功命令分别显示修订号、修改字段、受影响节点、配置同步状态、`Coordinates Valid`、`Setup Ready` 和问题码。错误中的相关节点以链接显示，可跳转到 Setup 树。Part 指令明确标注“项目专属，YAML 未变化”。

## 3 命令权威与事务边界

实现新增 `CommandKernel`、`TubeCommandProvider` 和精简的 Controller 状态边界。GUI Apply、受限脚本与本地 HTTP Tube 写路由提交同一种 `CommandInvocation`，三条入口共享参数校验、资源解析、状态传播、撤销记录和 YAML 持久化。

单条修改采用以下顺序：

```text
复制 Controller 的 Python 工作态
→ 在候选状态执行领域命令
→ 计算候选 ValidationReport
→ 生成并持久化候选 YAML
→ 发布候选 Controller
→ 增加修订号并记录 undo
→ 刷新 GUI、Viewer 和问题列表一次
```

CAD/OCP 原生对象与资源库保持共享只读，不参与深拷贝。候选状态只复制 Setup、Operations、Draft 映射和资源上下文，减少原生对象复制带来的线程与生命周期风险。发布前会核对 CAD model 身份、源哈希、源路径、拓扑目录和 body 目录，防止候选脱离当前模型权威。

`with tube.transaction():` 在一个候选状态内顺序执行修改命令，只写一次 YAML、发布一次 UI、增加一次修订并形成一条撤销记录。查询、撤销、重做和嵌套事务在解析阶段被拒绝。任何领域错误、资源错误或 YAML 发布错误都会丢弃整个候选。

undo 与 redo 保存前后不可变检查点，当前会话最多 100 步；新修改截断 redo 分支。修订号持续递增，项目打开、STEP 更新或 Controller 替换会建立新的并发纪元并清空状态历史。HTTP 的 `expected_revision` 用于拒绝陈旧写入，`command_id` 随结果返回，原有不携带这两个字段的请求继续有效。

坐标或装夹存在 Draft 时，普通脚本修改返回 `E_DRAFT_ACTIVE`。后台模型或项目加载期间，查询仍可运行，修改返回 `E_LOAD_BUSY`。UI 发布观察者发生异常时，已提交命令保持成功并记录内部错误；ValidationReport 已在持久化前由候选状态计算，避免提交后才暴露派生校验错误。

## 4 受限脚本语法与安全面

`restricted_script.py` 使用 Python 标准库 `ast` 读取语法树，只接受直接的 `tube.<公开命令>` 或 `管状.<中文别名>` 调用。参数限定为有限数字、字符串、布尔值、`None`、tuple、list 和字符串键 dict，负号只用于数值字面量。

解析器明确拒绝 import、赋值、变量、下标、运算、lambda、推导式、循环、条件、异常处理、dunder、属性链、星号参数、分号拼接和事务上下文绑定。解析结果是不可执行的 `ScriptCall` 数据，后续逐条交给命令内核。PowerShell、文件系统、网络、线程、子进程、`eval` 和 `exec` 没有可达入口。

脚本文件采用 UTF-8，读取上限为 256 KiB；单个文件最多 500 条命令，AST 与参数容器最多 32 层。文件对话框的读取采用 `limit + 1` 字节，避免先看文件大小、随后无界读取的换档风险。超大整数字面量进入数值转换时会稳定返回 `E_ARGUMENT_INVALID`，不会泄漏 `OverflowError` 或 Python traceback。

## 5 YAML 格式与物理字段语义

`manufacturing-setup.yaml` 使用 YAML 1.2.2 语法、UTF-8、LF 和固定英文键。仓库公开 `schemas/manufacturing-setup-v1.schema.json`，结构校验采用 JSON Schema Draft 2020-12。运行时依赖约束为 `ruamel.yaml>=0.18.6,<0.19` 和 `jsonschema>=4.23,<5`；本轮测试环境分别为 0.18.6 与 4.23.0。

YAML 保存 Machine、Nozzle、Material 的完整冻结快照，坐标保存 Source CS 下的原点、Z、X 与来源类型。长度单位固定为 mm，脚本角度固定为 deg，内部变换仍使用 rad。Placement 将安装位参考变换和局部调整分开保存，旋转采用规范化 `(x, y, z, w)` 四元数，重建顺序为：

```text
T_reference · Translate(dx,dy,dz) · Rx · Ry · Rz
```

几何拾取坐标只保存解析后的数值和 `geometry_resolved` 标记，应用到当前模型后生成复核 Warning。v1 最多保存一条 Tube Operation，只携带类型、名称和 enabled。Part、STEP 路径与哈希、body ID、拓扑签名、项目内 Setup/Operation ID、Draft、Viewer 状态和派生问题不写入 YAML。

解析安全子集拒绝重复键、任何显式 tag、anchor、alias、merge key、NaN、Inf、非字符串键和未知字段。文件限制为 2 MiB、32 层和 50000 个节点。资源快照除 Schema 检查外，还要用现有领域类型反序列化并重新计算内容哈希，额外字段无法借助合法外层哈希进入项目。

已有 YAML 使用 round-trip 节点更新，仍存在字段附近的注释、引号和兼容排版会保留。固定字段顺序及语义哈希使文本排版变化与制造语义变化可以分开判断。

## 6 项目主档、实时工作态与恢复

`project.json` 保持完整项目主档，项目格式仍为 v2。未保存项目只维护内存 YAML；项目第一次保存后在根目录创建工作文件。每条可移植修改先发布 YAML，再替换 Controller。Part 进入同一撤销链，但不会触碰 YAML 字节。

`metadata.content_sha256` 描述可移植语义，`base_project_setup_sha256` 记录最近一次项目保存时的 Setup 语义。项目打开前比较项目值、YAML 当前值和基准值，得到 equal、recoverable、project_newer 或 diverged。交互打开会显示字段差异，并提供“使用 YAML”“使用项目”“取消打开项目”；非交互入口遇到待决分叉时返回错误，避免自动选择恢复方向。

外部编辑在下一次写入时由精确文件指纹发现，自动覆盖随即暂停。载入预览和正式接受之间再次比较完整字节指纹，注释、revision 或基准哈希的变化也会要求重新确认。外部 YAML 只把语义配置应用到当前项目，Part、setup_id 和已有 operation_id 保持不变。

文件读取使用单个、限长的文件描述符，同一批字节同时生成配置、文本和 SHA-256；打开句柄与读取后的路径身份也会复核。写入采用同目录临时文件、文件 `fsync`、双重目标指纹检查和 `os.replace`。替换后的目录 `fsync` 若失败，磁盘文件已经提交，此时记录耐久性 Warning 并继续发布 Controller，避免 YAML 与内存产生相反结论。

项目 JSON 已保存而 YAML 元数据更新失败时，项目保存结果保留，控制台给出未同步 Warning。用户可在处理磁盘或外部编辑问题后重试。

## 7 代码组织与上下文控制

本轮没有继续扩大 `tube_ui.py` 和 `tube_controller.py` 的职责。新增模块的边界如下：

| 模块 | 单一职责 |
| --- | --- |
| `restricted_script.py` | 受限语法解析与位置错误 |
| `command_kernel.py` | 候选事务、修订、undo/redo 和发布顺序 |
| `tube_commands.py` | Tube 命令参数与领域适配 |
| `tube_controller_state.py` | Controller 检查点、fork 和 publish 合同 |
| `setup_config.py` | YAML 领域模型、Schema 校验和 round-trip 编码 |
| `setup_config_io.py` | 限长读取、指纹与原子文件发布 |
| `setup_config_session.py` | 项目/YAML 三方比较和恢复会话 |
| `script_console.py` | Qt Dock、输入、历史、补全和焦点隔离 |
| `tube_script_service.py` | 应用装配、对话框和一次刷新协调 |
| `qt_load_wait.py` | 同步兼容入口的有界 Qt 等待 |

拆分后的新增模块均低于 `pyproject.toml` 的 1000 行模块、500 行类、60 行函数和复杂度 15 门禁。注释集中解释状态权威、安全边界和提交顺序，普通控件赋值与直接数据搬运没有增加复述式注释。

## 8 真实审查过程与测试结果

第一轮完整回归为 389 passed、2 skipped。随后安排独立安全审查与 Qt 审查。安全审查复现了显式 Python YAML tag 绕过、三次读取造成 A/B 快照混合、`os.replace` 后目录同步失败引起的磁盘/内存分裂、Observer 异常伪装成命令失败、超大整数逃逸稳定错误码，以及外部预览只比较语义哈希等问题。各问题均补充失败用例并修复。

Qt 审查复现了 Dock 隐藏后快捷键仍被禁用、工具按钮焦点未隔离、拖动高度没有持久化、带连字符资源 ID 补全重复前缀、英文界面残留中文，以及 GUI 命令重复刷新 Viewer。修订后，焦点保护覆盖整个 Dock，所有代表性 GUI 写路径均断言一次提交只发生一次完整刷新。

提交前终审发现成功输出混用了修改字段与受影响节点、错误节点无法点击，以及标题栏关闭按钮承担折叠动作。命令结果随后增加独立 `changed_fields`，节点标记由受限文本渲染为 Setup 树链接；标题栏关闭恢复 Qt 隐藏语义，折叠改为“工具”菜单中的独立动作。对应测试覆盖字段输出、链接信号、节点选择和关闭后的显示偏好。

最终门禁记录如下：

| 检查 | 结果 |
| --- | --- |
| `python -m pytest -q` | 402 passed，3 skipped |
| Ruff | 通过 |
| Mypy | 73 个源码文件无问题 |
| `scripts/check_context_budget.py` | 通过 |
| `git diff --check` | 通过 |
| wheel 与 sdist 构建 | 通过 |
| `python -m twine check` | wheel、sdist 均通过 |
| 项目依赖隔离审计 | `No known vulnerabilities found, 3 ignored` |

3 个 ignored 项沿用 CI 对 OCP 固定版本的已登记豁免。直接扫描本机 Anaconda 会命中大量与本项目无关的 Jupyter、Scrapy、Streamlit 等旧包，因此交付结论采用 `pip-audit` 的项目路径解析结果。3 个 skipped 用例对应当前 Windows 权限下无法创建文件或目录符号链接；普通文件、路径身份、reparse 检查和原子替换用例已执行。

全量回归中的 `pipe2` 黄金用例执行了真实脚本事务：创建 Operation，确认两个 solid 为同一 Part，选择 Generic XYZAC、0.4 mm 喷嘴和 PLA，设置 Model CS、Build CS 与安装位。事务只增加一个命令修订，达到 `Coordinates Valid` 和 `Setup Ready`，保存后生成 YAML，项目重开保持 Ready 与 synchronized。

OpenGL 与 VTK 既有测试分别验证坐标架、打印板和装夹模型的渲染接口；Tube UI 测试验证命令提交到 Viewer presentation 的同步。构建产物核对到 wheel 与 sdist 均包含 JSON Schema、YAML 格式说明和脚本控制台源码；用户指南也进入安装文档目录与 sdist。

## 9 可复用资产与工程判断

这轮工作的核心资产是可审计的命令提交链。领域状态、可移植配置、项目主档和 Viewer 各有单一权威，失败点位于发布边界之前；Part 这种项目专属数据也能进入统一 undo，而不会污染可移植模板。Planar、Rotary 和 Freeform Workbench 可以复用 CommandKernel、配置指纹、三方恢复和 Dock 交互，只需替换 provider 与 Schema 中的领域段。

安全价值来自可证明的不可达面。脚本解析结果只是数据对象，攻击样例覆盖属性链、dunder、表达式、导入、进程与 YAML tag；文件读取和原子发布也有换档、链接、指纹冲突和提交后失败用例。该证据链比界面上放置一个通用 Python 控制台更适合制造软件，因为制造 Setup 的变换、资源快照和恢复方向都能留下稳定结果。

开放 YAML 同时承担可读配置和未保存工作恢复。完整项目仍由 project.json 管理，YAML 没有复制几何身份与 Part，从结构上压低了跨模型误用风险。`geometry_resolved` Warning、资源内容哈希和基准哈希让复用保持显式，后续可以围绕相同字段开发批量模板、版本比较和团队审阅工具。

## 10 已知边界

- 控制台没有变量、算术、条件、循环和用户函数；复杂批处理应由外部工具生成受限命令文件或 YAML。
- 不提供远程脚本执行端点；HTTP 只接受单条领域写请求。
- undo/redo 的撤销栈和状态检查点仅覆盖当前会话的 100 步；控制台输入历史仍由 `QSettings` 跨会话保存 200 条。
- YAML 外部修改在下一次写入或用户主动导入时发现，当前没有文件系统 watcher。
- `os.replace` 前仍存在极短的本地父目录换档窗口；当前已检查真实目录、reparse point、打开句柄与路径身份。需要对抗本机高权限恶意进程时，应改用 Windows 目录句柄和 `ReplaceFile` 或 POSIX `renameat`。
- 目录 `fsync` 失败只写内部 Warning，当前控制台没有独立的耐久性状态字段。
- round-trip 只保留仍存在字段附近的注释和样式，删除字段的注释不会迁移。
- v1 YAML 只允许一条 Tube Operation；多 Setup 与多 Operation 的交互仍需后续格式版本和工作台导航设计。
- 参考机床、编辑器生成的喷嘴碰撞包络和材料确认只满足当前 Setup 门禁，真实 NC 输出仍受机床标定、实物喷嘴数据、碰撞、逆运动学和 Process Profile 约束。

## 11 资料依据

- [YAML Language Specification 1.2.2](https://yaml.org/spec/1.2.2/)：YAML 语法、节点和 tag 依据。
- [RFC 9512: YAML Media Type](https://www.rfc-editor.org/rfc/rfc9512)：`.yaml` 文件的 `application/yaml` 媒体类型依据。
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)：公开结构契约和未知字段校验依据。
- [Python `ast` documentation](https://docs.python.org/3/library/ast.html)：受限命令语法树的节点定义依据；项目只读取 AST，不执行编译结果。
- [Python `os.replace` documentation](https://docs.python.org/3/library/os.html#os.replace)：同文件系统原子替换语义依据。
- [Qt QDockWidget](https://doc.qt.io/qt-5/qdockwidget.html) 与 [QSettings](https://doc.qt.io/qt-5/qsettings.html)：可停靠窗口和本机状态持久化依据。
- [ruamel.yaml documentation](https://yaml.dev/doc/ruamel.yaml/)：注释、引号与 round-trip 节点更新依据。
- 仓库 MIT `LICENSE`：Schema、格式说明和实现代码的许可依据；资源快照继续保留各自来源字段。
