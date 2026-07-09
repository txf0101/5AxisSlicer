# 项目结构说明

本文件按 2026-07-06 工作区状态整理。读取依据包括 `README.md`、`圭臬/开发目标文档.docx`、`docs/reviews/` 复盘、`src/` 源码、`scripts/` 脚本、`tests/` 测试、`example/` 样例和 `outputs/` 生成产物。`圭臬/开发目标文档.docx` 已确认更新时间为 2026-07-06 13:45，大小为 492214 字节，内容包含 Workbench、Operation Session、机器/材料/路径参数、五轴姿态和路径预览要求。

## 总体链路

程序入口位于 `run_app.py` 和 `scripts/run_app.ps1`。入口调用 `five_axis_slicer.app.main()` 创建 PyQt5 主窗口，主窗口显示 Workbench 首页；用户选择工作台后进入 Operation Session。当前可交互操作为 `Imported NC Review`，它承接 STEP 对象定义、导入 G-code 路径预览、层范围过滤、Feature Type 图例、路径段属性和检查摘要。

CAD 读取由 `step_loader.py` 完成，body/edge 选择状态由 `models.py` 和 `selection_list.py` 维护。默认预览使用 `opengl_viewer.py`，VTK fallback 和后端选择入口保留在 `viewer.py`。G-code 注释、运动命令、挤出量、宽高、进度 timeline 和二进制索引缓存在 `gcode_preview.py` 内完成。项目保存由 `project_io.py` 写出 `project.json`，HTTP 自动化由 `automation.py` 调度回主线程执行。

## 根目录

- `.git/`：Git 版本库元数据。由 Git 工具维护。
- `.idea/`：本机 JetBrains/PyCharm 配置，当前属于未跟踪个人 IDE 状态。
- `docs/`：长期说明和阶段复盘。
- `example/`：真实 STEP/STP、STL、G-code 和参考图片样例。
- `outputs/`：测试截图、G-code 预览缓存、GUI 冒烟测试结果和临时项目保存产物。
- `scripts/`：运行、HTTP 客户端、样本生成、模型检查和桌面冒烟测试脚本。
- `src/`：Python 包源码，采用 `src` layout，包名为 `five_axis_slicer`。
- `tests/`：单元测试。
- `圭臬/`：项目目标和开发约束文档。
- `.gitignore`：忽略缓存、输出和临时文件。
- `README.md`：面向运行和验收的主说明。
- `pyproject.toml`：包元数据、依赖、命令行入口和 pybind11 构建依赖。
- `requirements.txt`：简化依赖清单。
- `run_app.py`：仓库根目录 GUI 启动入口。
- `setup.py`：可选 native 扩展构建入口，存在 C++ 编译链时生成 `five_axis_slicer_native`。
- `native/`：C++/pybind11 源码目录，当前用于预览索引数组打包。

## `src/five_axis_slicer/`

- `__init__.py`：包初始化文件，声明版本号。
- `__main__.py`：支持 `python -m five_axis_slicer` 的入口。
- `app.py`：CLI 参数解析和 QApplication 创建。支持 `--model`、`--gcode`、`--demo`、`--host`、`--port`。
- `automation.py`：本地 HTTP 服务。网络请求进入后台线程后，经 Qt signal 投递到主线程，避免后台线程直接操作 Qt 控件；实体路径场景下命令等待窗口为 120 秒。
- `gcode_preview.py`：G-code/NC 路径解析与缓存。路径段记录工件坐标起点/终点、机床原始起点/终点、层号、运动类型、挤出角色、进给速度、E 增量、线宽、层高、A/B/C/U/V/W 轴角度、`step_index` 和注释来源；A/C 路径按 `P_part = Rz(-C) * Rx(-A) * P_machine` 反算工件坐标；全量 timeline 记录挤出、空走、回抽和 prime，纯 E 动作只进入进度读数与运动统计；颜色由 `move_type`、`extrusion_role` 和颜色映射表确定。v5 缓存采用小 JSON 元信息加 `.npz` 数组，保存 layer/timeline 前缀、segment step 索引、role/move chunk 和预览几何字段。
- `geometry_vtk.py`：OCP 拓扑到 VTK polydata 的转换层。
- `localization.py`：中英翻译表和 `tr()`。
- `models.py`：`BodyInfo`、`EdgeInfo`、`CadModel`、`SelectionState` 等共享数据结构。
- `native_preview_index.py`：预览索引打包入口。优先调用 `five_axis_slicer_native`，构建链不可用时使用 NumPy/Python fallback，输出同形状数组。
- `opengl_viewer.py`：默认 OpenGL 预览后端。使用 `QOpenGLWidget`、PyOpenGL shader、VBO buffer、轻量线模式、实体道实例化数组、当前步高亮、姿态抽样和 edge color-id picking；VTK 后端仍保留为 fallback。
- `project_io.py`：项目保存。复制 STEP/G-code 源文件，写入 workbench、operation、选择状态、G-code 摘要和预览设置。
- `selection_list.py`：body/edge 多选列表组件，保证选择输出顺序稳定。
- `step_loader.py`：STEP/STP 加载器，负责路径校验、OpenCascade 读取、solid/edge 枚举和源文件哈希。
- `styles.py`：集中 QSS，延续当前深色玻璃风格。
- `ui.py`：主窗口和 Workbench/Operation Session 编排。包含首页卡片、左侧操作面板、Objects/Print/Material/Machine/Preview/Checks 页签、中英切换、横向 G-code 进度条和 HTTP 命令入口。
- `viewer.py`：VTK 视窗与后端选择入口。保留 STEP body actor、edge actor、G-code 实体道 actor、轻量线 actor、当前步骤高亮、姿态抽样 actor、相机命令和 edge 点选；默认尝试 OpenGL 后端，`FIVE_AXIS_RENDER_BACKEND=vtk` 或 offscreen 测试环境回到 VTK。

## `scripts/`

- `automation_client.py`：HTTP 自动化命令行客户端，支持普通 JSON 和 base64 JSON。
- `desktop_click_smoke.py`：早期 body/edge 选择桌面点击冒烟测试。
- `desktop_workbench_smoke.py`：Workbench 与 NC 预览桌面冒烟测试。等待 `/state` 中出现可见路径后截图，输出到 `outputs/workbench_smoke/`；实体道本轮另用 PID 锁定脚本保存到 `outputs/workbench_smoke_progress_solid_pid_v2/`。
- `generate_sample_step.py`：用 CadQuery 生成两 body STEP 样本。
- `inspect_step_models.py`：批量检查 STEP/STP 可读性和网格化统计。
- `run_app.ps1`：PowerShell 启动脚本。参数包括 `-Python`、`-Model`、`-GCode`、`-Demo`、`-Port`。

## `tests/`

- `test_gcode_preview.py`：覆盖 Prusa/Orca 风格 `;TYPE:`、Fractal Cortex 风格 `;Layer`、`;WIDTH:`、`;HEIGHT:`、相对/绝对挤出、回抽、prime、A/B 与 A/C 轴、未知角色、timeline 和层内进度。
- `test_project_io.py`：覆盖项目保存、旧选择字段、workbench 状态、G-code 摘要和预览设置。
- `test_selection_list.py`：覆盖列表重建、选择读取、文本标记同步和稳定输出顺序。
- `test_step_loader.py`：覆盖 CadQuery 生成 STEP 后的 solid、edge 和哈希读取。
- `test_ui_state.py`：覆盖 workbench 选择、中英切换、Preview 显隐状态、进度接口和路径段属性面板。
- `test_preview_index.py`：覆盖 layer/timeline 前缀索引、native/Python 索引入口形状和 `.npz` 往返。
- `test_viewer_geometry.py`：覆盖五轴旋转姿态下实体道截面基向量的正交性。

## `docs/`

- `project_structure.md`：当前结构说明。
- `reviews/2026-06-11_frontend_step_selection_review.md`：前置选择器首版复盘。
- `reviews/2026-07-03_edge_preview_selection_review.md`：预览区 edge 点选分工复盘。
- `reviews/2026-07-03_readability_structure_review.md`：选择链路可读性整理复盘。
- `reviews/2026-07-03_project_structure_annotation_review.md`：结构索引整理复盘。
- `reviews/2026-07-06_workbench_nc_preview_review.md`：论文优先 Workbench 与 NC 预览实现复盘。
- `reviews/2026-07-06_gcode_3d_preview_refactor_review.md`：叶轮 G-code MATLAB 三维预览初版重构复盘。
- `reviews/2026-07-07_gcode_ac_inverse_preview_fix_review.md`：叶轮 G-code AC 反算三维预览修正复盘。
- `reviews/2026-07-07_gcode_volume_progress_preview_review.md`：五轴 G-code 实体道、timeline 和横向进度预览复盘。

## `example/`

- `叶轮/叶轮.stp` 与 `叶轮/叶轮完整.gcode`：当前默认论文演示样例。
- `叶轮/render_gcode_complete_path_matlab.m`：MATLAB G-code 路径渲染脚本，输出 C 轴展开顶视图、原始机床 X/Y 顶视图和 AC 反算三维 FIG。
- `扇叶/风扇扇叶.STEP` 与 `扇叶/风扇扇叶_PLA_1h50m.gcode`：扇叶示例，用于后续多样例对照。
- `pipe/pipe_fitting_40pct_recommended_XYZAB_backup.gcode` 与 `pipe/pipe_fitting_40pct_recommended_XYZAC.gcode`：管件五轴轴名样例，用于 A/B 与 A/C 解析回归。
- `球形NEU校徽/`、`三叶扇/`、`pipe/` 其他文件：模型、图片和旧阶段测试资产。

## `outputs/`

`outputs/` 存放可再生成产物，已被 `.gitignore` 忽略。近期相关目录：

- `gcode_preview_cache/`：大 G-code 解析缓存，文件名由源路径、大小、修改时间和解析版本哈希得到；当前 v5 缓存由 `.json.gz` 元信息和 `.npz` 二进制数组组成，旧 v4 JSON.gz 可兼容读取并回写 v5。
- `workbench_smoke/`：Workbench/NC 预览冒烟测试截图和 `summary.json`。
- `desktop_click_*`、`example_models/`、`http_smoke_project*`：旧阶段选择、真实模型和 HTTP 保存验证产物。

## `圭臬/`

- `开发目标文档.docx`：五轴塑料/树脂增材切片软件开发目标文档。当前文档已补写，内容覆盖 Workbench、工作台类型、统一前处理流程、机器/材料/路径参数、ToolpathPoint、五轴运动学和参考依据。

## 维护提示

新增源码文件时应同步更新本说明。G-code 解析规则、颜色映射、五轴角度处理和 VTK actor 分组属于高维护成本区域，注释应说明规则来源和数据边界。测试截图、缓存和临时项目保存结果继续放入 `outputs/`，不要混入源码目录。
