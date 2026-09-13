# PC01—PC07 论文核心 AC 实施与验收复盘

日期：2026-09-13。范围为半球贴面、扇叶薄壁、pipe2 Tube、叶轮有限面组和预装双通道的离线版本。本轮没有发布、上传或取得实机资格。

## 完成内容

PC01 冻结 mm/rad/deg、Source→Build→Workpiece/Machine frame、G90/M83/G94、独立容差、材料表、失败矩阵和未知项。复核时发现半球 CAD 与历史 NC 实际存在于本机，契约改为未跟踪用户资产并记录 SHA-256；没有用解析夹具替代原件。

PC02 新增受限 Freeform：最多 16 面和 32 条导引线，支持单面/有限面组、曲面贴合、薄壁、有限多道和多层。导引线按弧长采样并投影回明确修剪面；trim 越界、退化、零段和法向跳变失败关闭。产品接入 shared Toolpath、XYZAC、状态、取消、Stale、保存重开、GUI、受限脚本和 HTTP。

PC03 把 `material_id/channel_id` 写入路径点，并实现显式区域、T0—T3 事件链、材料体积/选择/实际切换/purge 分口径统计。未分配区域、传感器和温控问题均失败关闭；恢复路径有直接测试。

PC04 新增自有 AC 离线控制器 profile 和后处理。它固定 G90/M83/G94，区分转位绝对 Z20 与材料 park 相对 Z+20，展开材料宏语义并进行完整命令流回读。累计 C 实际量写入 qualification；未知限值保留 Warning，已知超限变为 Error。

PC05 对当前 pipe2 重新生成：1,591 个点，现有六件套回读与自有 AC 25 个事件回读均通过。Tube 三种操作页面的 1366×768、1600×900、1920×1080 中英证据无按钮截断或碰撞；页面产品状态由证据脚本注入用于表现 Ready/Stale/Error，算法真值来自独立产品链。T04、T07、T08、T12 可关闭到受限离线资格，真实机床边界不变。

PC06 从当前 CAD 生成 5 个产品：半球 7 路径/30 点、扇叶 3 路径/123 点、叶轮 16 路径/384 点、pipe2 1,591 点、预装双通道 48 点。每例六件套完整并严格回读；半球 edge 0018 的 trim 越界保留为定位反例。四份项目均保存并重新读取。历史 NC 只统计 frame、模式、运动/T 指令差异，没有作为当前几何或材料真值。

PC07 完成了最终质量、全仓、构建、包检查、native smoke、隔离安装和本地交付收口。联合 PC/Tube UI 回归为 57 passed、6 subtests passed；最终全仓为 856 passed、3 skipped、141 subtests passed。质量脚本的 Ruff、迁移规则、安全规则、格式、上下文预算和 Mypy 全部通过，Mypy 检查 162 个源码文件。普通 wheel/sdist 和 CPython 3.12 Windows native wheel 构建通过，Twine 检查通过。native wheel 在新建虚拟环境中安装后 `NATIVE_INDEX_AVAILABLE=True`，预览索引结果和 `five-axis-slicer --help` 入口正常。该虚拟环境启用 `--system-site-packages` 复用已验证的 Qt/VTK/OCP 依赖，只证明包隔离安装与入口可用，不冒充完全无缓存环境。

验收中发现并修复了三类问题：新增模块的变量复用和可空类型使 Mypy 报错，Freeform 在未挂载 CAD 时缺少明确拒绝，Tube 1366×768 页面的返回/恢复原文件按钮有 3 px 矩形重叠。修复后相关两项 UI 用例、57 项联合回归和最终全仓回归均通过。用户指定的 Computer Use 在启动应用前后都未能枚举出任何 Windows 应用窗口，已按 Skill 规则重置并重试一次。本轮因此依赖串行 Qt 控件操作、尺寸回归和证据截图，没有声称完成了真人桌面点击验证。

## 关键取舍

- 没有放宽 trim 容差来接受越界路径；选择实际落在面内的导引边，越界边保留为负例。
- 材料区域保持显式，不实现自动分区。这样可审查每次 T 指令及温控/清洗语义。
- 控制器未知项保留为 Warning 并把输出命名为 offline review program。单点轴限通过不能替代累计 C、标定或现场碰撞证据。
- 生产 VTK/OpenGL 在当前无显示会话无法建立 pixel format。产品与 Qt 控件测试继续，图像改用真实 generated preview payload 的 Qt 证据绘制器，并在清单中记录限制。

## 可复用内容与局限

Freeform 的稳定几何引用、共享 Toolpath、产品六件套、命令内核、状态和回读链可供后续 F01—F06 扩展。材料计划可被其他工作台复用，但当前只在论文核心 Freeform 中接入。自有 AC profile 是离线封装；固件、宏、机床标定、完整工具/夹具扫掠、传感通信、现场空运行和试切仍需外部证据。

机器可读证据见[验证清单](evidence/2026-09-13_paper_core_ac/validation_manifest.json)，输入契约见[PC01 契约](../planning/paper_core_input_contract.md)，操作说明见[Freeform 手册](../guides/freeform_workbench_zh.md)。
