# B01–B03 基础能力验收复盘

日期：2026-09-11。用户要求完成 B01、B02、B03，本轮按三个既有判据联合验收。任务状态统一维护于[进度台账](../planning/progress_tracker.md)。范围止于 STEP 与已有 NC 预览、Tube Setup 坐标闭环、受限脚本和 YAML 命令事务。

## 1 当前基线与环境

Git 基线为 `5502d0e47c8041b2b0909f8344ef4394d9ab42e8`。开始时 README、pyproject.toml、tube_controller.py、tube_ui.py 已有未提交修改，规划文档及索引尚未跟踪。本轮保留这些内容，以当前工作区源码进行验收，不把现有导入排序调整记为本轮功能修复。

README 中的 `C:/Users/Tang Xufeng/.conda/envs/5AxisSlicer/python.exe` 缺少 pytest。系统 Anaconda 有运行依赖，但 pytest 为 7.4.4，低于当前项目要求。正式回归采用已有的 `tmp/pytest9/Scripts/python.exe`：Python 3.12.7、pytest 9.1.1；该环境继承系统 site-packages，不属于干净安装验证。OCP 7.8.1.1.post1、CadQuery 2.7.0、PyQt5 5.15.10、VTK 9.3.1、NumPy 1.26.4、ruamel.yaml 0.18.6。本轮未安装组件。

## 2 判据与实现证据

| 任务 | 当前实现 | 本轮核对的验收用例 |
| --- | --- | --- |
| B01 | `step_reader.py`、`step_topology.py`、`gcode_parser.py`、双 Viewer | `test_step_topology.py` 的真实 pipe2；`test_gcode_preview.py` 的单位、模态、AC 重建及整文件回退；`test_opengl_tube_viewer.py` 的四级拾取；`test_vtk_tube_offscreen_smoke.py` 的真实拓扑与装夹渲染 |
| B02 | `tube_controller.py`、`manufacturing/coordinates.py`、资源与项目持久化模块 | `test_tube_ui.py::TubeUiTests::test_pipe2_setup_reaches_ready_with_warning_and_round_trips`；几何拾取、两点方向、Flip、Apply/Cancel、Dirty 传播和装夹原子提交用例 |
| B03 | `restricted_script.py`、`command_kernel.py`、`tube_commands.py`、`setup_config*.py`、`tube_script_service.py` | `test_pipe2_script_transaction_reaches_ready_and_reopens_with_yaml`、`test_http_tube_mutation_reports_shared_revision_conflicts`、`test_command_adapters_publish_one_full_refresh`；命令失败回滚、undo/redo、外部 YAML 冲突及恢复用例 |

上表源码均位于 `src/five_axis_slicer/`，测试位于 `tests/`。精确版本以证据清单中的逐文件 SHA-256 为准。

pipe2 脚本用例使用两个 solid 组成 Part，选择 Generic XYZAC、0.4 mm 喷嘴和 PLA；喷嘴接口 M6×1、长度 12.5 mm、启用测试包络，材料审核确认。Model CS、Build CS 采用命令默认值，安装位为 `build_plate_mount`。用例断言整组事务只增加一次修订，达到 Coordinates Valid 和 Setup Ready，保存并重开后仍为 Ready，YAML 状态为 synced。参数是软件测试配置，不构成实物喷嘴测量或机床标定证据。

## 3 执行与结果

正式命令在获准的沙箱外环境执行：

```powershell
& './tmp/pytest9/Scripts/python.exe' -X faulthandler -m pytest -q -ra --junitxml=tmp/b01_b03_acceptance/pytest9.xml
```

退出码 0，结果为 **402 passed、3 skipped、130 subtests passed，218.04 秒**。B01–B03 的现有完成判据通过，无需增加或修改产品代码；台账据此关闭三个任务。三个跳过项分别是项目内容寻址文件符号链接、项目 source 目录符号链接、YAML 文件符号链接检查，原因均为 WinError 1314，不能算作检查通过。

正式证据已归档：[JUnit 报告](evidence/2026-09-11_b01_b03/pytest9.xml)、[测试摘要](evidence/2026-09-11_b01_b03/pytest9.log)、[静态门禁](evidence/2026-09-11_b01_b03/quality.log)、[环境及逐文件 SHA-256](evidence/2026-09-11_b01_b03/manifest.json)。初轮与串行失败复测也保留为 [初轮记录](evidence/2026-09-11_b01_b03/pytest.log)、[串行复测](evidence/2026-09-11_b01_b03/recheck.log)。日志中的部分 Windows 中文错误信息受原进程编码影响，错误码、用例名及结果可核对。

静态门禁命令为 `C:/ProgramData/anaconda3/python.exe scripts/check_quality.py`，退出码 0；Ruff、迁移文件规则、Security Ruff、格式检查、上下文预算及 Mypy 均通过，Mypy 检查 73 个源码文件。

沙箱内先后两轮全仓均为 400 passed、3 skipped、2 failed，失败为语言偏好和成果页后台加载超时，pytest 9 另外记录 130 个通过的 subtest。两轮曾并行运行，现有测试会清空同一 QSettings，因此先怀疑跨进程干扰；随后使用 pytest 9 单独串行复测两个失败用例，仍然失败，排除了并行作为唯一原因。读取 QSettings 的 `isWritable()` 返回 False，存储位置为 Windows HKCU 注册表。Qt offscreen 日志还出现 OpenGL 上下文警告；该警告与加载超时的因果关系没有独立证明。获准在沙箱外重新运行正式回归后，两项均通过，期间保留原应用实现。沙箱失败记录不作为验收通过证据。

## 4 验证边界与后续

Qt 用例验证当前页面控件、命令路由和保存重开行为；OpenGL 用例验证拾取及展示数据合同，VTK 独立进程用例验证原生上下文中的离屏渲染。没有执行真人桌面逐项点击或全页截图视觉审阅，不宣称完成实机验收。

Windows 符号链接权限受限的用例单列记录，不计为通过。普通文件的指纹冲突、原子发布与错误恢复由其余用例验证。项目和 YAML 往返产物使用测试临时目录，运行后不保留；保留测试断言源码、JUnit 结果及输入指纹，不虚构输出文件哈希。

当前仍限定单 Setup 与单 Tube Operation，撤销栈只覆盖当前会话，YAML 外部修改在写入或主动导入时发现。中心线、切层、路径生成、逆运动学、碰撞和 NC 生成由 A/T 后续任务承担。B01 的已有 NC 预览不能计作路径生成成果。

可复用的方法是以完成判据定位真实流程和失败恢复用例，再记录当前源码与输入指纹。测试涉及共享 QSettings 时应串行执行；未来若需要并行回归，应先隔离设置存储。下一项算法开发仍为 A01，本轮未提前实施。

## 5 经验固化为 Skill

同日按用户要求，将环境预检、Qt 串行约束、权限诊断、重试停止条件和证据复用整理为个人 Skill `five-axis-slicer-validation`，位于 `C:/Users/Tang Xufeng/.codex/skills/five-axis-slicer-validation/SKILL.md`。项目根目录 [AGENTS.md](../../AGENTS.md) 提供后续读取入口；规则正文只在 Skill 维护，不在项目中复制一份。

Skill 配套 `scripts/preflight.py` 只读检查解释器、当前 pyproject.toml 依赖约束及 QSettings 可写性。使用已有 `tmp/pytest9/Scripts/python.exe` 实际执行后，依赖检查通过，当前权限下 QSettings 可写。该预检不启动 GUI、不证明渲染或完整运行依赖可用，也不写注册表。

Skill 官方校验器通过。首次校验因 Windows 默认 GBK 读取 UTF-8 文件失败，使用 `python -X utf8` 后通过；此处调整有明确错误证据，无需更换环境。此次仅增加 Skill、只读脚本和项目读取入口，补充本节；应用代码未变，不重跑应用全仓。后续每次重试应有新增证据、代码变化或环境变化，否则停止同样尝试。
