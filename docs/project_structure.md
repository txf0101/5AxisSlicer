# 项目结构说明

本文件按 2026-07-24 工作区状态整理。读取依据包括 `README.md`、`圭臬/开发目标文档.docx`、`docs/reviews/` 复盘、`src/` 源码、`scripts/` 脚本、`tests/` 测试、`example/` 样例和 `outputs/` 生成产物。`圭臬/开发目标文档.docx` 已确认更新时间为 2026-07-06 13:45:16，大小为 492214 字节，内容包含 Workbench、Operation Session、机器/材料/路径参数、五轴姿态和路径预览要求。

## 总体链路

程序入口位于 `run_app.py` 和 `scripts/run_app.ps1`。入口调用 `five_axis_slicer.app.main()` 创建 PyQt5 主窗口。应用保留 Workbench 首页、Operation Session 和独立 Result Preview；Tube Workbench 增加一套独立页面与 controller，负责第一阶段制造 Setup 和坐标定义。

CAD 读取由 `step_loader.py` 完成，body、face、edge、vertex 选择状态和统一拾取类型位于 `models.py`。`manufacturing/` 保存坐标、机床、资源、Setup、几何引用和预览运动学领域规则，`tube_controller.py` 负责状态传播，`tube_ui.py` 负责交互。默认预览使用 `opengl_viewer.py`，VTK fallback 保留在 `viewer.py`。项目保存由 `project_io.py` 写出 v2 清单，HTTP 自动化由 `automation.py` 调度回 Qt 主线程执行。

## 根目录

- `.git/`：Git 版本库元数据。由 Git 工具维护。
- `.idea/`：本机 JetBrains/PyCharm 配置，当前属于未跟踪个人 IDE 状态。
- `docs/`：长期说明和阶段复盘。
- `example/`：真实 STEP/STP、STL、G-code 和参考图片样例。
- `outputs/`：测试截图、论文图、GUI 冒烟测试结果和临时项目保存产物。
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
- `app.py`：CLI 参数解析和 QApplication 创建。支持 `--model`、`--gcode`、`--results`、`--demo`、`--host`、`--port`。
- `automation.py`：本地 HTTP 服务。网络请求进入后台线程后，经 Qt signal 投递到主线程，避免后台线程直接操作 Qt 控件；实体路径场景下命令等待窗口为 120 秒。
- `gcode_preview.py`：G-code/NC 路径解析与 v7 缓存。路径段同时保留显示坐标和 Machine XYZ；调用方显式确认已注册控制器语义后才进行 AC 工件坐标重建。非零 B、U/V/W、未知语义或运动学诊断触发文件级 Machine XYZ 回退，所有 segment 与 timeline 使用同一坐标空间。加载结果绑定源文件 SHA-256、字节数和纳秒时间戳，缓存键另含解析版本和控制器语义。
- `geometry_vtk.py`：OCP 拓扑到 VTK polydata 的转换层。
- `localization.py`：中英翻译表和 `tr()`。
- `manufacturing/`：Qt 无关领域层。`coordinates.py` 维护刚体变换、三参考坐标与四元数微调；`machine.py` 维护父子轴链、安装位、打印板和正运动学；`resources.py` 与 `library.py` 维护冻结快照和用户库；`references.py` 维护唯一几何重绑定；`setup.py` 维护节点状态、问题码和 Tube Operation。
- `models.py`：`BodyInfo`、`FaceInfo`、`EdgeInfo`、`VertexInfo`、`CadModel`、`SelectionState`、`PickRequest`、`PickHit` 和 Viewer 覆盖层共享类型。
- `native_preview_index.py`：预览索引打包入口。优先调用 `five_axis_slicer_native`，构建链不可用时使用 NumPy/Python fallback，输出同形状数组。
- `package_assets.py` 与 `assets/`：定位随 wheel 和源码安装发布的只读包资源；叶轮论文界面参考图位于 `assets/impeller_four_panel_reference.png`。
- `opengl_viewer.py`：默认 OpenGL 预览后端。使用 `QOpenGLWidget`、PyOpenGL shader、VBO buffer、轻量线模式、实体道实例化数组、当前步高亮、姿态抽样和 edge color-id picking；VTK 后端仍保留为 fallback。
- `project_io.py`：v2 项目边界。STEP/G-code 采用 SHA-256 内容寻址副本，副本在临时文件校验后发布，清单原子替换；重开时检查相对路径、哈希、四级拓扑 ID 与签名、资源镜像和刚体变换；v1 在内存迁移并于首次保存前备份。用户资源库分叉只产生 Warning，冻结快照损坏或顶层资源镜像冲突会拒绝项目。
- `selection_list.py`：body/edge 多选列表组件，保证选择输出顺序稳定。
- `step_loader.py`：STEP/STP 加载器，负责单位换算、装配名称、solid/sheet 分类、face/edge/vertex 邻接、几何签名、坐标候选和源文件哈希。独立 free face 会提升为 sheet body；读取任务由后台协调器调用并支持阶段间协作取消。
- `styles.py`：集中 QSS，统一采用浅色工程主题；颜色 token 与 `TypographyTokens` 由 `theme.py` 管理。当前字号层级为正文与控件 15 px、次要文字 13 px、表单标签 13 px、G-code 14 px、卡片标题 15 px、栏目标题 16 px、页面标题 22 px、徽标 12 px。
- `tube_controller.py` 与 `tube_ui.py`：Tube 第一阶段工作流。controller 管理 Part、资源、Model/Build CS、Placement、Draft 和 Dirty 传播；页面提供固定树、问题列表、三参考拾取、模型/机床视图和保存接口。
- `ui.py`：应用壳与页面编排，包含共享菜单、中英切换、后台任务连接、论文导出调度和 HTTP 自动化路由。Tube 领域判断保留在独立 controller。
- `viewer.py`：VTK 视窗与后端选择入口。OpenGL/VTK 均支持 body、face、edge、vertex 拾取、三套坐标架、打印板和刚体装夹显示。

## `scripts/`

- `automation_client.py`：HTTP 自动化命令行客户端，支持普通 JSON 和 base64 JSON。
- `desktop_click_smoke.py`：早期 body/edge 选择桌面点击冒烟测试。
- `desktop_workbench_smoke.py`：Workbench 与 NC 预览桌面冒烟测试。等待 `/state` 中出现可见路径后截图，输出到 `outputs/workbench_smoke/`；实体道本轮另用 PID 锁定脚本保存到 `outputs/workbench_smoke_progress_solid_pid_v2/`。
- `build_four_panel_paper_figure.py`：从已验收总览图、叶轮 STEP 和 G-code 生成四张独立 4K 论文面板。中文输出 PNG；`--uncompressed-tiff` 为英文交付增加逐像素一致的无压缩 RGB TIFF。PNG、TIFF 均写入独立 sidecar JSON，目录另含汇总 manifest；单图不写入 `(a)` 至 `(d)` 题注。G-code 面板将文件名与四组语法色标签分为两行，正文按最长真实指令、动态行号栏和 21 行上下文在 18 至 22 px 间选择最大可用等宽字号，文字溢出时终止导出。
- `generate_sample_step.py`：用 CadQuery 生成两 body STEP 样本。
- `inspect_step_models.py`：批量检查 STEP/STP 可读性和网格化统计。
- `run_app.ps1`：PowerShell 启动脚本。参数包括 `-Python`、`-Model`、`-GCode`、`-Demo`、`-Port`。

## `tests/`

- `test_gcode_preview.py` 与 `test_preview_kinematics.py`：覆盖运动解析、显式控制器语义、AC 反算、文件级 Machine XYZ 回退、timeline 和缓存往返。
- `test_project_io.py` 与 `test_project_background_load.py`：覆盖 v2 原子保存、内容寻址副本、四级拓扑复核、v1 迁移、路径安全、资源快照和取消。
- `test_selection_list.py`：覆盖列表重建、选择读取、文本标记同步和稳定输出顺序。
- `test_step_loader.py` 与 `test_step_topology.py`：覆盖单位、solid/sheet/free face、四级拓扑、装配名、邻接、签名、坐标候选和 `pipe2` 黄金样例。
- `test_ui_state.py`：覆盖 workbench 选择、中英切换、Preview 显隐状态、进度接口和路径段属性面板。
- `test_preview_index.py`：覆盖 layer/timeline 前缀索引、native/Python 索引入口形状和 `.npz` 往返。
- `test_viewer_geometry.py`：覆盖五轴旋转姿态下实体道截面基向量的正交性。
- `test_manufacturing_*.py`、`test_machine_profiles.py`、`test_geometry_rebinding.py`：覆盖刚体数学、机床轴链、资源门禁、Setup 状态和唯一重绑定。
- `test_tube_controller.py`、`test_tube_ui.py`、`test_opengl_tube_viewer.py`、`test_vtk_tube_offscreen_smoke.py`：覆盖 Tube 操作、Draft、拾取、装夹、双后端覆盖层、1600 × 900 布局和保存重开。

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
- `reviews/2026-07-22_tube_slicing_user_workflow_review.md`：Tube 操作类型、NX 式用户流程、坐标分层和首版范围复盘。
- `reviews/2026-07-24_tube_setup_coordinate_implementation_review.md`：Tube Setup、坐标闭环、项目 v2、真实测试与后续边界复盘。

## `example/`

- `叶轮/叶轮.stp` 与 `叶轮/叶轮完整.gcode`：内置叶轮验收项目。
- `叶轮/render_gcode_complete_path_matlab.m`：MATLAB G-code 路径渲染脚本，输出 C 轴展开顶视图、原始机床 X/Y 顶视图和 AC 反算三维 FIG。
- `扇叶/风扇扇叶.STEP` 与 `扇叶/风扇扇叶_PLA_1h50m.gcode`：扇叶示例，用于后续多样例对照。
- `pipe/pipe_fitting_40pct_recommended_XYZAB_backup.gcode` 与 `pipe/pipe_fitting_40pct_recommended_XYZAC.gcode`：管件五轴轴名样例，用于 A/B 与 A/C 解析回归。
- `球形NEU校徽/`、`三叶扇/`、`pipe/` 其他文件：模型、图片和旧阶段测试资产。

## `outputs/`

`outputs/` 存放可再生成产物，已被 `.gitignore` 忽略。近期相关目录：

- G-code 解析缓存与 mmap 行索引默认写入 `QStandardPaths.CacheLocation/5AxisSclicer_V2.0/`，不可写时回退到系统临时目录。当前 v7 缓存键包含源路径、大小、修改时间、内容 SHA-256、解析版本和控制器语义，产物由 `.json.gz` 元信息与生成号 `.npz` 数组组成。
- `paper_preview_acceptance/individual_panels/`：中英文界面总览、工艺参数、五轴路径和 G-code 独立 3840 × 2160 论文图，以及各图 sidecar JSON 和分语言 manifest。英文 TIFF 为 8-bit RGB、`Compression=1`、300 dpi；五轴路径图使用 OpenGL FBO 捕获路径场景，随后重绘贴面方向立方体、Part XYZ 和起终点图例，最终排版由用户完成。
- `workbench_smoke/`：Workbench/NC 预览冒烟测试截图和 `summary.json`。
- `desktop_click_*`、`example_models/`、`http_smoke_project*`：旧阶段选择、真实模型和 HTTP 保存验证产物。

## `圭臬/`

- `开发目标文档.docx`：五轴塑料/树脂增材切片软件开发目标文档。当前文档已补写，内容覆盖 Workbench、工作台类型、统一前处理流程、机器/材料/路径参数、ToolpathPoint、五轴运动学和参考依据。

## 维护提示

新增源码文件时应同步更新本说明。G-code 解析规则、颜色映射、五轴角度处理和 VTK actor 分组属于高维护成本区域，注释应说明规则来源和数据边界。测试截图和临时项目保存结果放入 `outputs/`，运行缓存使用系统用户缓存目录，不要混入源码目录。

## 2026-07-21 成果预览页增量

本轮在应用壳内加入第三个页面 `ResultPreviewPage`，Workbench 与 Operation Session 的数据和接口继续保留。新增模块的职责边界如下：

- `result_state.py`：成果页可序列化状态、工艺参数记录、不可变加载请求与原子提交结果。`IllustrativeProcessParameters` 类名作为 `project.json` 兼容标识保留，不进入可见文案。
- `background_load.py`：可取消 QThread 加载协调器，替代请求会屏蔽旧信号，失败和取消保留有效场景。
- `gcode_source.py`：mmap 行偏移索引、41 行上下文、正反搜索、完整五轴指令定位和 `;叶轮1` 至 `;叶轮8` 阶段识别。
- `result_preview.py`：18% / 56% / 26% 三栏成果页、状态、参数、阶段导航、显隐、缩略图和代码区。控件共享 `UI_TYPOGRAPHY` 字号层级，中英文切换会刷新换行标签的高度；按钮、统计项、显隐选项和代码范围按可用宽度重新排布。页面采用正式功能文案，视觉参考、参数作用边界与代码定位行号只进入审计数据。
- `paper_export.py`：固定逻辑布局、Qt 与 OpenGL 合成、PNG 合同检查、审计 JSON、成对回滚提交和跨进程同名产物锁。
- `theme.py` 与 `viewer_overlays.py`：浅色 token、Part XYZ 轴标和六面方向立方体。
- `opengl_viewer.py`：交互 LOD 与完整 timeline 论文路径共用的 OpenGL 后端，论文路径按 0.02 mm 连续性容差合并折线。

应用入口新增 `--results`。兼容参数 `--demo` 加载内置叶轮成果页，`scripts/run_app.ps1` 对应提供 `-Results`。`ui.py` 负责页面导航、共享菜单、语言偏好、后台任务连接、论文导出调度和 `/results/*` 路由，解析、索引与合成逻辑留在独立模块。主工具栏仅保留工作台、成果页、STEP、G-code 和语言五组高频入口；保存、清空、Fit、Home 等动作继续由菜单提供，1600 × 900 的中英文工具栏均可完整显示。

成果预览阶段新增 `test_result_backend.py`、`test_result_preview.py`、`test_paper_export.py`、`test_opengl_viewer.py` 和 `test_cache_resilience.py`。双语用例核对正式产品文案、按钮、标签、显隐选项、代码视图、换行高度、工具栏完整性和横向滚动范围；论文面板用例核对两行 G-code 标题区、语法标签边界和代码正文自适应结果。叠加 Tube 第一阶段用例后，2026-07-24 全仓结果为 271 passed、2 skipped、23 个 CadQuery FutureWarning。真实 4K 总览产物放在 `outputs/paper_preview_acceptance/`；`scripts/build_four_panel_paper_figure.py` 将论文内容导出至 `individual_panels/`，交付四张独立 PNG、同名 sidecar JSON 和汇总 manifest。五轴路径面板采用 OpenGL FBO，并在场景图之上恢复贴面方向立方体、Part XYZ 和起终点图例；单图不含子图题注。
