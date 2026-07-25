# 项目结构说明

本说明对应 2026-07-25 工作区源码。结构核对范围为 `pyproject.toml`、`.github/`、`src/`、`scripts/`、`tests/`、`native/`、`example/` 和 `docs/reviews/`。`圭臬/开发目标文档.docx` 保持只读；已核对时间为 2026-07-06 13:45:16，大小为 492214 字节。

## 1 根目录与工程配置

- `pyproject.toml`：Python 包元数据与依赖入口，同时配置 Ruff、Mypy、Pytest 和源码上下文预算。开发环境使用 `pip install -e ".[dev,cad-tests]"`。
- `.github/workflows/quality.yml`：Windows 3.10/3.12 回归、Linux 领域测试、发行包检查、依赖审计和 Windows native smoke。
- `.pre-commit-config.yaml`：提交前检查基础文件、Ruff 与上下文预算；推送前运行完整静态质量门禁。
- `.editorconfig`、`.gitattributes`：统一文本编码、换行和 Git 文本属性。
- `LICENSE`、`MANIFEST.in`：许可证及源码发行包清单。
- `run_app.py`、`scripts/run_app.ps1`：GUI 启动入口。
- `setup.py`、`native/`：可选 C++/pybind11 预览索引扩展。未启用 native 构建时保留 Python/NumPy 路径。
- `docs/`：长期结构说明；同项目阶段复盘集中在 `docs/reviews/`。
- `example/`：STEP、G-code、MATLAB 与参考图样例。
- `outputs/`、`tmp/`：可再生成结果和临时检查产物，均不承担源码职责。
- `圭臬/`：项目目标和开发约束文档。

## 2 应用源码

Python 包位于 `src/five_axis_slicer/`，采用 `src` layout。

### 2.1 应用壳与自动化

- `app.py`、`__main__.py`：命令行参数、QApplication 创建和模块入口。
- `ui.py`：主窗口、页面导航、加载任务连接和用户动作编排。
- `automation.py`：本机 HTTP 服务、鉴权边界和 Qt 主线程命令投递。
- `automation_routes.py`：稳定路由表与请求参数解析，路由实现从主窗口生命周期代码中分离。
- `background_load.py`：STEP、G-code、项目和成果页共享的可取消后台加载协调器。
- `model_commit.py`：异步编辑基线检查及主线程可见状态事务，统一回滚 Model、G-code、Setup、双 Viewer 和 Tube 坐标编辑上下文。
- `localization.py`、`styles.py`、`theme.py`：双语文本、QSS 与视觉 token。

### 2.2 CAD 与制造领域

- `step_loader.py`：STEP 导入事务、源文件指纹、取消边界和兼容 API。
- `step_reader.py`：OCP/XCAF 文件读取、单位上下文和装配名称。
- `step_topology.py`：solid/sheet 分类、四级拓扑枚举、几何签名和坐标候选。
- `geometry_vtk.py`：OCP 拓扑到 VTK polydata 的转换。
- `models.py`：CAD 拓扑描述、选择状态、统一 Pick 类型和 Viewer 覆盖层数据。
- `manufacturing/coordinates.py`：列向量、右手系、毫米/弧度刚体变换，三参考坐标定义及局部六自由度微调。
- `manufacturing/machine.py`：机床轴链、安装位、打印板、配置校验和正运动学。
- `manufacturing/resources.py`、`manufacturing/library.py`：机床、喷嘴、材料 Profile，内置模板、用户库和项目冻结快照。
- `manufacturing/references.py`：几何引用服务的稳定兼容门面，仅重导出公共入口。
- `manufacturing/reference_descriptors.py`：拓扑索引、几何签名构造及点和方向解析。
- `manufacturing/reference_rebind.py`：源更新后的容差比较、唯一重绑定、歧义处理和问题去重。
- `manufacturing/reference_audit.py`：坐标定义中的几何引用审计和失效问题生成。
- `manufacturing/setup.py`：Setup 聚合、节点状态、稳定问题码和 Tube Operation。
- `manufacturing/preview_kinematics.py`：NC 预览的控制器语义与坐标重建策略。
- `manufacturing/json_contract.py`：领域 JSON 的严格字段读取与类型检查。

### 2.3 G-code 预览

- `gcode_preview.py`：公共数据类型和兼容入口，调用解析、数组和缓存模块。
- `gcode_parser.py`：流式 G-code 解析及文件级坐标回退规则。
- `gcode_arrays.py`：路径段与 timeline 的稠密 NumPy 编解码。
- `gcode_cache.py`：内容寻址缓存、源文件指纹校验和原子 manifest 发布。
- `gcode_source.py`：mmap 行索引、上下文读取、搜索和阶段标记。
- `native_preview_index.py`：native/Python 预览索引统一入口。

### 2.4 项目持久化

- `project_io.py`：v1/v2 读取、内存迁移、领域对象编排和保存事务入口。
- `project_contract.py`：项目格式、完整性、版本及取消异常。
- `project_assets.py`：项目内 STEP/G-code 权威副本验证与加载。
- `project_storage.py`：路径边界、跨进程保存锁、临时文件发布、原子替换和 fsync。

### 2.5 成果预览与导出

- `result_state.py`：成果页状态、不可变加载请求和加载结果。
- `result_preview.py`：成果页交互协调。
- `result_preview_layout.py`：三栏 Qt 控件构建和布局。
- `result_preview_text.py`：成果页双语文本绑定。
- `result_commit.py`：加载结果校验、原子呈现提交和失败回滚。
- `paper_export.py`：论文图合成、PNG/JSON 合同、跨进程锁和成对提交。

### 2.6 Viewer 后端

- `viewer_common.py`：OpenGL/VTK 共用协议、坐标安全检查和预览几何算法。
- `viewer_overlays.py`：方向立方体、坐标轴和叠加层绘制辅助。
- `viewer.py`：VTK 后端与后端选择入口。
- `opengl_viewer.py`：QOpenGLWidget 生命周期、交互和 GPU 提交。
- `opengl_scene.py`：不持有 GL context 的 CPU scene 数组构建。
- `opengl_picking.py`：屏幕射线、线段距离和拾取数学。

### 2.7 Tube Setup 第一阶段

- `tube_controller.py`：Setup 工作流入口，管理 Part、资源选择、坐标 Apply、Placement、Dirty 传播和项目序列化。
- `tube_drafts.py`：Body 角色及坐标、装夹 Draft 值对象。Draft 位于已应用 Setup 之外，Apply 失败和 Cancel 不改动上次有效状态。
- `tube_validation.py`：Part、坐标引用、机床、装夹、资源库和 Operation 校验规则。
- `tube_resource_context.py`：用户资源库目录、项目冻结快照审计和资源目录缓存。
- `tube_resource_selection.py`：自动化资源构造边界；完整喷嘴要求调用方提供明确的物理字段。
- `tube_serialization.py`：Setup、Operation 与项目资源镜像的 JSON 编解码边界。
- `tube_ui.py`：Qt 页面、树、编辑控件、问题跳转和用户事件编排。
- `tube_ui_presenter.py`：Qt 无关的坐标拾取解析、Source CS 到显示坐标的变换和 Viewer 展示快照。

### 2.8 包资源

- `package_assets.py`、`assets/`：随 wheel 和 sdist 发布的只读资源定位。
- `selection_list.py`：通用 body/edge 多选控件。

## 3 工程脚本

- `scripts/check_quality.py`：依次运行基础 Ruff、已迁移文件的 I/UP/B、关键 I/O 边界的 Security Ruff、格式检查、上下文预算和 Mypy。
- `scripts/check_context_budget.py`：按模块、类、函数行数和 McCabe 风格复杂度执行源码规模棘轮。
- `scripts/automation_client.py`：HTTP 自动化客户端。
- `scripts/desktop_click_smoke.py`、`scripts/desktop_workbench_smoke.py`：真实桌面交互冒烟测试。
- `scripts/generate_sample_step.py`、`scripts/inspect_step_models.py`：STEP 样本生成与批量检查。
- `scripts/build_four_panel_paper_figure.py`：论文面板与审计 sidecar 导出。

## 4 测试分组

- `test_automation.py`、`test_ui_state.py`：HTTP 安全边界、路由兼容和主窗口状态。
- `test_gcode_preview.py`、`test_preview_kinematics.py`、`test_preview_index.py`、`test_cache_resilience.py`：解析、坐标策略、数组、索引与缓存恢复。
- `test_project_io.py`、`test_project_background_load.py`：原子保存、项目内资产、迁移、路径安全和取消。
- `test_step_loader.py`、`test_step_topology.py`、`test_geometry_rebinding.py`、`test_source_update_workflow.py`：STEP 拓扑、单位、签名和显式源更新。
- `test_manufacturing_*.py`、`test_machine_profiles.py`：坐标数学、机床、资源和 Setup 门禁。
- `test_result_backend.py`、`test_result_preview.py`、`test_paper_export.py`、`test_paper_panel_export.py`：成果加载、页面布局和论文导出事务。
- `test_viewer_common.py`、`test_viewer_geometry.py`、`test_viewer_overlays.py`、`test_opengl_viewer.py`：共享 Viewer 算法与覆盖层。
- `test_tube_controller.py`、`test_tube_resource_library_ui.py`、`test_tube_resource_selection.py`、`test_tube_ui.py`：Tube 状态传播、资源审计、显式喷嘴字段和 Qt 编辑流程。
- `test_opengl_tube_viewer.py`、`test_vtk_tube_offscreen_smoke.py`：Tube 双后端拾取、坐标架、打印板和装夹显示一致性。

## 5 维护边界

领域对象、文件事务和解析策略放在 Qt 无关模块；页面负责事件编排和展示。涉及 Source CS、毫米/弧度、Draft 原子提交、线程切换、缓存或项目发布失败边界时保留解释性注释。其余代码优先采用短函数、明确类型和可直接测试的纯逻辑。新增模块或职责迁移后同步更新本说明，阶段判断与真实测试过程记录到同项目 `docs/reviews/`。
