# 工程质量与上下文收敛复盘

## 1 审查范围

本轮审查覆盖 Tube Setup 与坐标闭环所在分支的 Python、C++、PowerShell、项目存储、HTTP 自动化、测试、构建和持续集成配置。开始前只读核对了 `圭臬/开发目标文档.docx`，文件大小 492214 字节，修改时间为 2026-07-06 13:45:16；同时读取 Tube 用户流程和实施复盘，确认功能边界仍止于 `Coordinates Valid`、`Setup Ready` 和项目保存重开。终检于 2026-07-25 完成。

审查采用可执行门禁和独立代码复核。行业实践在不同组织中存在差异，本项目用可复现的检查项表达质量要求，不使用无法验证的“完全符合某公司标准”结论。

## 2 结构收敛

原有功能集中在少数 Qt 与解析模块。此次按稳定数据边界拆分，公共入口保持兼容：

- G-code 分为公共模型、流式解析、NumPy 数组和缓存事务；
- STEP 分为导入事务、OCP/XCAF 读取和拓扑签名；
- 几何引用服务保留 `manufacturing/references.py` 稳定门面，描述解析、唯一重绑定和引用审计分别进入三个独立模块；
- 项目存储分为格式异常、资产验证、文件发布和 v2 编排；
- OpenGL 分为 Widget 生命周期、CPU scene 和拾取数学，Viewer 共享坐标检查进入独立模块；
- 成果页分为交互协调、布局、文本绑定和原子提交；
- Tube 分为 Draft、领域校验、资源上下文、资源构造和显示 presenter；
- STEP 源更新的异步编辑基线与可见状态回滚进入 `model_commit.py`；
- HTTP 路由从 `MainWindow` 生命周期代码中移出。

拆分依据是状态所有权和失败边界。兼容模块只保留稳定类型与薄入口，文件事务、几何规则和 Qt 事件不交叉复制。新模块均处于 Ruff 严格清单和 Mypy 检查范围。

## 3 工程门禁

`pyproject.toml` 成为唯一 Python 依赖和工具配置入口。运行依赖、开发工具及 CadQuery 测试依赖分层维护；`requirements.txt` 删除，避免两份依赖清单漂移。Python 支持范围固定为 3.10 至 3.12，版本由 Git tag 和 setuptools-scm 生成。

`scripts/check_quality.py` 依次执行：

- 全仓 Ruff 语法、导入错误和未使用名称检查；
- 已迁移模块的导入顺序、现代语法和 Bugbear 规则；
- 自动化与项目 I/O 边界的 Ruff Security 规则；
- 已迁移模块格式检查；
- 模块、类、函数行数及圈复杂度预算；
- 全部 60 个源码模块的 Mypy 检查。

常规预算为模块 1000 行、类 500 行、函数 60 行、复杂度 15。超限遗留项在 `tool.context-budget.legacy` 保存当前精确高水位；任何增长都会失败，完成拆分后应下调或删除对应值。该机制把上下文成本变成可持续下降的仓库约束。

Mypy 对领域、存储、解析和共享 Viewer 模块保持检查。Qt、VTK 及旧成果页中仍有动态接口债务，当前采用逐模块 override；新增模块不得进入忽略列表。

## 4 构建、依赖与供应链

新增 MIT 许可证、源码发行清单、EditorConfig、Git attributes、pre-commit 和 GitHub Actions。CI 在 Windows Python 3.10/3.12 运行完整回归，在 Linux 运行领域测试、构建、Twine 和依赖审计；可选 native 扩展由独立 Windows job 验证。外部 GitHub Action 使用完整 commit SHA。

应用直接依赖 `cadquery-ocp==7.8.1.1.post1` 和 `vtk==9.3.1`，CadQuery 只用于测试件生成。CadQuery 2.7 的 NLopt 依赖会在干净测试环境选择 NumPy 2.2.x，普通应用环境可使用 NumPy 1.26.x。两类环境已分别执行解析 dry-run，避免把本机 Anaconda 中 NLopt 2.10 与 NumPy 1.26 的既有冲突误判为项目锁定结果。

OCP 当前固定的 VTK 9.3.1 命中三项上游安全公告，CI 使用明确编号的临时例外。升级条件是 OCP 提供兼容的新 VTK 组合；该风险需要在每次 OCP 更新时重新评估。

## 5 安全边界

项目保存采用内容寻址副本、临时文件、摘要复核、原子替换、目录同步和跨进程锁。项目根、子目录和发布目标检查 symlink、junction 与 reparse point；读取时复核安全相对路径、资产哈希、拓扑映射和资源镜像。

HTTP 自动化默认绑定回环地址。非回环监听需要显式开关和至少 32 字符的 bearer token。独立审查补充了本机浏览器攻击面：GET 仅开放只读路由，POST 强制 `application/json`，回环服务校验 Host 和 Origin。Windows 会在服务端留下未读请求体时偶发重置连接，因此媒体类型错误在有界读取后返回 415；重复测试覆盖了该行为。

静态扫描未发现 `shell=True`、动态 `eval/exec`、pickle、明文口令、裸 `except` 或可变默认参数。自动化 URL 客户端只接受 HTTP/HTTPS。

## 6 P1 缺陷与修复

独立复核发现四类会破坏用户已确认状态的 P1 缺陷，修复均围绕事务边界展开：

- 项目保存会先 Apply 或 Discard 未提交 Draft。若文件发布失败，旧实现会留下已改动的 Setup。`draft_resolution_transaction()` 现同时快照 Setup、Operations、Draft、修改标记、body 目录和 CAD 模型权威状态，外层保存失败时完整恢复。回归用例分别覆盖 Apply 与 Discard，两条路径均恢复保存前状态。
- Build CS 的数值控件按 Model CS 定义，旧回填直接显示 Source CS 中的已解析值。用户再次确认后会重复执行 Model 到 Source 的换算，引起坐标漂移。`reference_display_value()` 现仅对 Build CS 数值引用执行 Source 到 Model 的显示转换；测试以非单位 Model CS 验证编辑、Apply、保存和重开后的坐标一致。
- STEP 源更新的解析、引用重绑定和 Viewer 发布跨越后台线程与 Qt 主线程。旧提交边界无法覆盖加载期间的并发编辑，也无法在第二个 Viewer 发布失败后恢复全部可见状态。`model_commit.py` 现记录加载前 controller 身份与编辑 token；提交前拒绝过期结果，发布事务在重绑定或渲染失败时恢复模型、源路径、Setup controller、两套 Viewer 的选择及拾取请求。专项测试覆盖重绑定失败、加载期间编辑和 Viewer 提交失败。
- 终检故障注入显示，普通 STEP 导入、项目打开及 STEP 与 G-code 组合加载仍可能在多 Viewer 发布中途留下新旧混合状态。可重入 `publication_transaction()` 现统一保护 Model、G-code、Controller、预览参数、双 Viewer、工作台、页签、播放状态和 Tube 坐标拾取上下文；嵌套提交只在最外层快照与回滚。四条新增测试分别从同源 STEP、派生 UI 刷新、项目末端展示和组合加载第二阶段触发失败，均确认恢复旧对象及可见状态。

这些用例记录了真实故障路径，后续保存或源更新改动应继续维持同一原子性约束。

## 7 已完成验证

当前已取得以下独立证据：

- 最终 `scripts/check_quality.py` 全绿，Ruff、Security Ruff、格式、上下文预算和 60 个源码模块的 Mypy 检查均通过；
- 最终全仓回归为 `297 passed, 2 skipped`；跳过项来自当前 Windows 无符号链接权限；
- 最终事务修复完成后，`tmp/final_quality_dist_20260725_v2/` 中的纯 Python sdist 与 wheel 重新构建成功，两个发行包均通过 Twine 检查；质量脚本进入 sdist，文档、测试、样例和目标 DOCX 未进入发行包；
- 设置 `FIVE_AXIS_BUILD_NATIVE=1` 后生成 CPython 3.12 Windows native wheel，隔离安装可导入扩展并执行 native 预览索引；
- MSVC 使用 C++17 与 `/W4` 编译成功，编译器提示来自 Python/pybind11 外部头文件；
- PowerShell 语法解析通过；
- 终检修正了 PSScriptAnalyzer `severity` 数组输入，补齐两份源更新测试的严格 Ruff 清单，并让 pre-push 完整门禁在任何文件组合下运行。本机未安装 PSScriptAnalyzer，规则执行仍由固定 Action SHA 的 Windows CI job 承担；
- 自动化安全专项 10 项通过，错误媒体类型另执行 20 次重复测试；
- 项目拆分专项 33 项通过、2 项因当前 Windows 无符号链接权限跳过；
- Result 拆分相关 38 项通过；Tube 拆分模块的 Ruff、格式和 Mypy 通过。

本机全局 Anaconda 环境含其他项目遗留的 NLopt 与 NumPy 组合，直接运行 `pip check` 或 `pip-audit` 会混入环境级冲突，无法代表本项目的隔离安装结果。依赖解析与审计证据来自干净 resolver 检查和 CI 配置；发布前仍需在 CI 的隔离环境复核安全公告状态。

## 8 剩余债务与后续入口

`ui.py`、`opengl_viewer.py`、`result_preview.py`、`tube_controller.py` 和 `tube_ui.py` 仍含超大类。此次拆出了稳定纯逻辑，Qt 控件构建与事件协调尚未完全组件化。高水位门禁阻止继续增长，后续应按页面区域和 controller capability 拆分，同时保持项目格式与自动化 API 不变。

G-code 与成果页为保持旧导入路径使用少量延迟导入。它们避免了启动时硬循环，仍增加理解成本；公共类型后续可移入只含数据结构的 contract 模块。

依赖尚无跨平台哈希锁文件。当前使用受限版本范围、干净 resolver 验证和 CI 审计；待 uv 或等价解析器在目标环境可用时，应生成按 Python 版本和平台维护的锁定产物。

这轮工作的可复用成果是三类约束：状态所有权决定模块边界，原子提交定义失败行为，精确高水位控制上下文增长。它们可直接用于下一阶段 Tube Frame、切层和路径生成，也适用于 Planar、Rotary 与 Freeform 工作台。
