# 第二代离线产品收尾复核

日期：2026-09-26。用户纠正计划文件后，本任务改按 [第二代收尾计划](../planning/v2_final_delivery_plan_20260925.md) 推进，不再按 FAN00—FAN15 主线扩大工作。唯一进度状态保存在总台账 `PRODUCT-01-V2C`。

## 范围与当前起点

交付五个工作台、公共制造流程、离线六件套及严格回读、项目重开、双语教程和可安装 Python 包。Research、物理/机床仿真与视频属于第三代；实机标定与现场试打单列。计划中的历史发布和测试结论仅用来定位，本轮尚未重新核验托管 CI 或桌面流程。

原错误计划下已产生参数来源检查、有限道宽量测及相关测试、文档；保留这些未提交修改，不自动删除、回滚或归入第二代已验收成果。被中断的检查句柄已回读到退出码 0，`quality_coverage.log` 显示 Ruff、上下文预算、Mypy 通过；此前相关测试 15 项通过。这些结果不替代 V2-01—V2-05。之后代码变动的相关性应在发行复核时逐项处理。

本轮已读取新计划、PRODUCT-01 当前行、最近交付复盘和产品交付经验，建立[V2-01 点击矩阵](evidence/2026-09-26_v2_final_delivery/v2_01_click_matrix.md)。矩阵初始全部未执行，不把历史截图或 Qt 测试填成当前点击通过。先用小模型完成入口检查，再运行代表案例。

使用的 Skills：`five-axis-workbench-development`、`five-axis-slicer-validation`。已读取 `computer-use` 入口以准备桌面验证，并发现可调用的 `node_repl` 工具；尚未初始化桌面运行时或执行点击，不能据此报告桌面已验证或不可用。

目标面板仍保存已暂停的 FAN 目标。当前目标工具只允许创建新目标或变更状态，不能替换未完成目标文字。执行范围遵从用户最新纠正；不以完成旧目标的方式强行替换。

## 新目标启用与首次桌面观察

用户随后清除旧目标并明确要求重新开始。工具确认原目标为空后，已成功创建 V2-01—V2-05 新目标，状态 active，以计划全部检查完成为结束条件。上段旧目标限制仅为此前状态。用户要求遇到问题查阅官方文档、相关开源项目与 NX 技术资料，后续修复需保留实际依据。

本轮实际使用 `computer-use` Skill，读取 guidance、API、confirmations，并通过 `node_repl` 的 `@oai/sky` 初始化和枚举应用。使用项目解释器启动 `run_app.py` 后，插件识别到唯一 V2.6.2 窗口；从英文空白首页实际点击 Planar，保存[截图](evidence/2026-09-26_v2_final_delivery/planar_initial_en.png)及[可访问性和截图元数据](evidence/2026-09-26_v2_final_delivery/planar_initial_en.json)。当前窗口尺寸尚未按矩阵调整，此次观察不计任何尺寸组合完整通过。

首页五个工作台可用，Research 禁用，首次使用说明可见。Planar 提示先打开 STEP，生成和导出禁用；右侧有滚动条。首次观察发现左侧 Import common 按钮文字右端被裁切，问题摘要包含未解释的 `MODEL_CS_MISSING`、`BUILD_CS_MISSING`、`PLACEMENT_DIRTY`，问题列表也直接显示内部代码；后续需核对窄窗和中英文并定位源码。

布局调查已检索 [Qt 官方布局说明](https://doc.qt.io/qt-6/layout.html)与[尺寸策略说明](https://doc.qt.io/qt-6/qsizepolicy.html)。资料解释 sizeHint、minimumSizeHint、sizePolicy 及换行控件的高度随宽度变化；它们尚不能证明本项目具体根因，且当前项目使用 Qt 5.15，采用具体 API 前需核对版本。尚未据此修改界面代码。

## V2-01 首次问题修复

源码确认侧栏最大宽度为 270，横向滚动关闭，长英文按钮超出可用宽度。按钮简化为“导入公共设置 / Copy common Setup”，完整的独立副本说明保留在悬停提示中，动作与设置作用域不变。Planar 摘要补齐 MODEL_CS_MISSING、BUILD_CS_MISSING、PLACEMENT_MISSING、PLACEMENT_DIRTY 的中英文操作说明。紧凑问题列表仍显示代码，后续继续核查其可读性和跳转。

首次相关测试为 24 passed、8 failed、2 errors，保留[首次 JUnit](evidence/2026-09-26_v2_final_delivery/ui_fixes01.xml)。8 个失败均为旧文字断言仍要求“已应用 / applied Setup”，而当前既有界面改为引导打开 Manufacturing Setup；更新断言后仍检查生成未调用、生成禁用、提示与 tooltip 一致及缺项存在。2 个错误来自系统默认 pytest 临时目录 WinError 5；按[pytest 官方临时目录说明](https://docs.pytest.org/en/stable/how-to/tmp_path.html)，改用项目 tmp 下新的唯一目录，不重用已有目录。

修复后相关测试 **34 passed**，见[第二次 JUnit](evidence/2026-09-26_v2_final_delivery/ui_fixes02.xml)，定向 Ruff 和 diff 检查通过。测试结束后旧应用会话已正常退出，重新启动当前源码。电脑插件一次无截图的元素点击返回 `coordinate input geometry is unavailable`；重新选窗并捕获截图后，按新截图坐标点击成功，没有重复使用失效索引。

真实中英文切换确认按钮不再裁切，新增诊断文案存在，见[英文截图](evidence/2026-09-26_v2_final_delivery/planar_fixed_en.png)、[中文截图](evidence/2026-09-26_v2_final_delivery/planar_fixed_zh.png)及同名 JSON。截图仍包含光晕，只作内部证据，不进入用户教程。尚未调整三种指定尺寸，未完成模型/设置/生成流程，不把本轮局部复查记作矩阵完整通过。下一步继续小模型入口、设置、几何选择及三尺寸检查；最终教程需同步新的按钮文字。

## 小模型真实设置流程

使用 CadQuery 构造 8×8×1 mm 平板作为入口检查输入，见证据目录 `small_plate.step` 与带哈希的 `small_plate_input.json`。Windows 原生文件对话框拒绝正斜杠路径；改用反斜杠后成功加载一个实体。路径处理依据 [Microsoft 文件路径说明](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)。此失败属于文件对话框输入，不记作 STEP 几何加载失败。

实际点击 Planar 左侧零件进入公共制造设置，选择实体角色“零件”，滚动后点击确认，Part 从缺失变为有效。切换喷嘴页时发现滚动位置沿用零件页，顶部说明和输入被隐藏；根据 [Qt QScrollArea 文档](https://doc.qt.io/qt-6/qscrollarea.html)使用已有滚动条 API，在设置入口激活后回到顶部。当前已修改源码，真实界面重启复验待完成。

内置喷嘴身份配置缺少安装接口、总长和碰撞外形，应用后正确保持无效；已有用户库配置提供总长 18 mm 和碰撞外形，但安装接口仍为空，应用后仍无效。源码 `resources.py` 确认接口缺失是 readiness blocker。当前界面仅显示 `SETUP_NOZZLE_INVALID`，缺少具体字段提示，是待修复的首次使用问题；不能猜测真实接口填入。见 [GUI 截图](evidence/2026-09-26_v2_final_delivery/setup_nozzle_invalid.png)及同名 JSON。完整 Setup、生成及三尺寸矩阵尚未通过。

`test_tube_ui.py` 回归为 35 passed、1 failed、2 subtests passed，见 `setup_scroll.xml`。失败来自旧断言要求多 Setup 报“at most one”；当前实现允许有明确工作台绑定的多 Setup，该样本未提供绑定，实际正确拒绝并提示 `require explicit workbench setup_bindings`。修正测试名称及错误断言后，单项复测 1 passed（`setup_scroll_retry.xml`）；其余行为不变。定向 Ruff 和 diff 检查通过。滚动定位尚需重启真实应用复验，喷嘴字段提示修复仍待实施。

## 喷嘴字段诊断与真实错误恢复

已按应用配置的 `readiness_blockers` 显示具体待补全或修正字段，未知字段保留原始代码；配置解析失败提示重新选择配置。问题项仍保留原始 code、跳转数据与 tooltip。资源库界面回归 8 passed，包含中英文安装接口提示、有效长度不误报及修复后错误清除，见 `nozzle_diagnostics.xml`；定向 Ruff 与 diff 检查通过。

通过真实保存对话框将小模型和未完成设置保存到 `planar_gui_small`，正常关闭后启动当前源码，再用真实打开项目对话框重开。模型与有效 Part 恢复，缺失接口保持无效；中英文均显示具体安装接口提示，见 `setup_nozzle_fixed_zh.png`、`setup_nozzle_fixed_en.png`。随后在界面填写 `OFFLINE-TEST-INTERFACE` 并应用，喷嘴变为 Valid，错误移到缺失材料，见 `setup_nozzle_recovered_en.png`。该字符串明确为离线软件验收输入，不代表真实接口或机床资格；恢复后的接口尚未再次保存。

新发现待处理项：公共设置保存重开后进入 Tube 页面；英文切换后右侧设置区裁切，当前页标题仍为中文。源码显示英文固定宽度 tree=380、editor=580，两个视图按钮各最小宽度 220，需结合实际逻辑窗口尺寸检查布局约束。滚动回顶仍需在修复版本完成“先滚动后换页”的真实复验。完整首次使用矩阵尚无组合通过。

## 公共设置视图、标题与窄窗布局修复

项目保存增加 `common_setup_view`，重开时明确恢复公共设置或普通 Tube 视图；旧项目缺少该字段仍按普通 Tube 处理。初次回归 14 passed、1 failed（`setup_view.xml`），新测试指出恢复普通 Tube 时还必须清除前一项目的公共视图状态，修复后双向重开 2 passed（`setup_view_retry.xml`）。切换语言单独更新当前设置页标题，不重新初始化编辑器；相关资源界面测试已检查喷嘴标题的中英文值。

布局诊断参考 [Qt 布局约束](https://doc.qt.io/qt-6/qlayout.html)和[表单布局说明](https://doc.qt.io/qt-6/qformlayout.html)，并以本机 Qt 5 控件实际 minimumSizeHint 测量定位。首次仅缩小视图按钮最小宽度仍有英文窄窗失败：预览模式下拉框也撑宽。当前调整为左树 340、英文编辑区 540，视图按钮最小宽度 128，预览模式下拉框采用最小字符数尺寸策略。测量与失败记录保留在 `setup_layout.xml`、`setup_layout_retry.xml`；最终面板边界检查 6 passed（`setup_layout_final.xml`）。

随后改为切换整个主窗口语言并选择喷嘴页，检查精确窗口尺寸、面板边界、视图按钮及喷嘴输入和应用按钮的水平可达性，六种组合全部通过（`setup_controls.xml`）。定向 Ruff 与 diff 检查通过。这些是 Qt 回归证据；当前桌面应用仍运行上一版，尚需重启并做实际滚动、语言切换及保存重开复验，不能据此填入完整点击矩阵。

## 当前源码桌面复验与小平板生成

正常重启当前源码后，实际完成英文零件页滚动到底、切换喷嘴页，编辑区回到顶部，标题显示 Nozzle，字段与应用按钮可见，见 `setup_layout_scroll_fixed_en.png`。材料先未确认应用，保持 Draft 并提示需复核；勾选复核后应用变为 Valid。模型坐标和构建坐标使用数值原点 (0,0,0)、Z (0,0,1)、X (1,0,0)，分别确认并应用；装夹选择回转台中心且六个偏移为零，应用后坐标有效、Setup 为 Ready with Warnings，仅保留参考机床离线提示，见 `setup_ready_en.png`。

通过原生保存与打开项目对话框，验证公共设置视图与有效设置恢复，见 `setup_reopened_en.png`；保存文件当时包含 `common_setup_view: true`。随后实际进入 Planar，创建并应用 planar_region，生成截面预览，导出保持禁用且说明不含沉积路径，见 `planar_region_generated_en.png`。再选择 planar_zigzag、创建、应用和生成，界面报告路径生成及 G-code 回读通过，保留参考机床与旋转奇异位形警告，见 `planar_zigzag_generated_en.png`。

通过 GUI 导出到 `planar_zigzag_export`，目录包含 main.gcode、toolpath.json、machine_axes.csv、preview.json、warnings.json、manifest.json 六件套。只读核对 manifest：expected_points=27、read_points=27、passed=true，坐标、挤出、进给和顺序不匹配列表均为空。warnings 状态为 warning、ready_for_export=true；离线警告不代表实机资格。当前只生成 Z=0.2 mm 的单层入口样本，不是计划代表案例验收。

隐藏实体后路径可见，见 `planar_zigzag_lines_en.png`，但线条偏细且对比度低，待 V2-03 继续核查；尚未验证沉积/空移筛选。生成后的项目已通过 GUI 保存到 `planar_gui_small`，当前保存页为 Planar，操作重开复验待继续。窗口仍未按三种逻辑尺寸量测，局部设置、错误恢复、生成与导出证据不计为任何完整矩阵组合通过。下一步检查局部 Setup、Stale、几何错误恢复及指定尺寸。

## 独立设置语言与 Stale 实际验证

在上述真实生成结果上点击 Copy common Setup，首次创建的独立编辑页显示中文，而主窗口仍为英文，见 `planar_local_language_before.png`。源码确认延迟创建编辑页后未初始化当前语言。参考 [Qt 动态语言更新说明](https://doc.qt.io/qt-6/i18n-source-translation.html)，沿用项目已有 `set_language` 方法，在独立编辑页装入控制器前同步主窗口语言；未引入新的翻译框架。设置作用域相关回归 17 passed，包含四个支持独立副本的工作台首次英文创建与切回中文，见 `local_language.xml`；定向 Ruff、diff 检查通过。关闭旧应用并启动当前源码后，实际从英文空白 Planar 点击 Copy common Setup，标题、说明、按钮和节点均显示英文，见 `planar_local_language_fixed_en.png`。

旧应用中的真实设置切换检查也已完成：独立副本建立后返回 Planar，提示 Inputs changed / stale，Export result 禁用，见 `planar_local_stale_en.png`。点击 Use common Setup 并确认后，左栏恢复 Using common Setup，旧结果仍保持 Stale 且不能导出，见 `planar_common_restored_stale_en.png`。再次点击 Generate preview，界面报告回读通过、导出恢复可用，见 `planar_stale_regenerated_en.png`。本次重新生成只验证状态恢复，未覆盖此前导出目录；磁盘项目仍保留前一轮保存的操作。完整三尺寸矩阵、几何错误恢复和其余工作台仍待检查。

## 设置缺项提示与尺寸证据条件

当前英文独立设置页再次观察到缺少零件时仅显示 SETUP_PART_MISSING，缺少下一步。已按实际状态代码补齐七个设置节点的 Missing、Invalid、Draft、Dirty 中英文说明，每项指出应打开的节点与确认/应用动作；材料复核单独提示。喷嘴的具体缺失字段诊断继续优先使用实际配置。问题项原始 code、跳转数据和 tooltip 保留。相关资源界面回归 9 passed（`setup_actions.xml`），新增检查缺少零件时显示闭合实体与确认操作，诊断身份仍可读取；定向 Ruff 与 diff 检查通过。当前应用尚未重启加载本次文案，真实显示复验待继续。

重新阅读电脑插件 API：支持原生拖拽，未提供直接设置精确窗口尺寸的接口。当前插件截图元数据为 1701×1067、origin=(9,0)；该值尚未与 Qt 客户区逻辑尺寸和屏幕缩放建立对应关系，不能填为 1600×900 或其他指定组合。下一步需量测并记录对应关系，再执行指定尺寸点击；现有 Qt 布局测试不替代实际桌面记录。

## Curve 语言刷新与选边检查

重启后的公共设置缺少零件提示已实际检查中英文，均包含选择闭合实体及确认动作，见 `setup_missing_action_en.png`、`setup_missing_action_zh.png`。Curve 空白入口的操作按钮可滚动到达，未创建操作时应用、生成和导出禁用，见 `curve_empty_zh.png`。

实际切换英文发现 Curve 问题列表仍保留中文，见 `curve_language_before.png`。按前述 Qt 动态语言更新说明，在 `set_language` 中重新取得设置诊断与当前操作结果并刷新问题列表；避免调用会重装输入的完整 refresh。`test_curve_integration.py` 10 passed（`curve_language.xml`），新增测试检查语言切换不清空未应用的边与反向标记。定向 Ruff 与 diff 检查通过。当前桌面进程尚未加载此修改，真实语言切换复验待完成。

通过真实打开项目重开 `planar_gui_small`，模型、设置和 Planar 操作恢复；进入 Curve 后点击可见模型边界，再采用 Viewer 已选边，输入仍为空，见 `curve_pick_pending_en.png`。当前尚未确认原因，不能计为几何选择或错误恢复通过。已对照 Curve 手册、VTK 后端拾取与坐标转换代码，并查阅 [Qt 高 DPI 坐标说明](https://doc.qt.io/qt-6.8/highdpi.html)和 [QMouseEvent 坐标说明](https://doc.qt.io/qt-6/qmouseevent.html)；需继续区分实际点击位置、显示缩放和拾取行为，不能凭截图猜测修改拾取容差。本段截图含操作光圈，仅用于内部验收记录。

后续实际切到 Face 模式点击平板顶面，出现橙色选中面；切回 Edge 后点击左侧可见上边，出现蓝色选中边，见 `curve_edge_selected_en.png`。滚动到按钮区采用已选边，UIA 回读 `body_001_edge_0008` 和反向标记 `0`。此前未命中的点击尚不足以认定拾取算法缺陷，本次未修改拾取容差或坐标转换。默认渲染后端由 `viewer.py` 选择 OpenGL；VTK 的实现检查不能直接证明当前 OpenGL 行为。

创建 Curve 操作后重新采用选边，未指定双邻面边的法向，实际应用被阻止并提示 `curve.normal_ambiguous: choose one adjacent face`，生成和导出保持禁用，见 `curve_normal_error_en.png`。返回输入区发现应用失败后边 ID 被清空。源码 `_apply` 无论成功或失败均调用会重载已提交值的 refresh；已增加可跳过输入重载的刷新参数，在应用失败时保留草稿，继续刷新诊断和按钮。Curve 集成回归 10 passed（`curve_recovery.xml`），其中缺失边失败后保留原输入、修正并生成成功的检查通过；定向 Ruff 与 diff 检查通过。此修复及前述语言刷新尚需重启当前桌面进程实测，完整几何错误恢复和三尺寸矩阵仍未关闭。

## Curve 修复版本真实恢复

正常关闭旧进程后，启动当前源码并用原生打开项目对话框加载小平板。实际创建 Curve Buildup，选取 `body_001_edge_0008`，采用 Viewer 已选边，应用时复现法向不明确错误。切换中文再切回英文，问题列表随语言更新，见 `curve_language_fixed_zh.png`、`curve_language_fixed_en.png`；返回输入区，边 ID 和反向标记 `0` 保留，见 `curve_rejected_draft_preserved_en.png`。

只把法向来源改为 User-specified direction，使用已有 `(0,0,1)`，再次应用后错误消失且生成按钮恢复。实际生成完成，状态为 warning，导出按钮可用，保留参考机床与旋转奇异位形警告，见 `curve_recovered_generated_en.png`。本次未导出或保存 Curve 操作，不计入代表案例六件套或保存重开验收。当前窗口尺寸仍未量测，不能关闭完整矩阵组合。

新观察：中文状态栏仍显示原始英文 `curve.normal_ambiguous` 错误，需补齐用户可操作的中文提示并保留原始诊断；生成后 Full lines (fast) 下等待稳定显示出现道宽外观，需在 V2-03 对照显示模式实际状态检查，不能仅凭按钮文字判断渲染模式。

## Curve 提示和初次预览模式同步

已为 `curve.normal_ambiguous` 提供中英文操作说明，提示选择相邻面并填写 ID 或改用指定方向；原始错误保留在状态数据及 tooltip，错误清除时同时清除 tooltip。仅翻译已识别错误，其他错误仍保留原文，避免隐藏未知诊断。

初次预览模式问题已定位：下拉框默认是 paper（完整线条），渲染器默认是 interactive（道宽），此前只有下拉框 currentIndexChanged 才同步模式。参照 [Qt QComboBox 信号说明](https://doc.qt.io/qt-6/qcombobox.html)，加载生成预览后显式应用下拉框当前模式，使首次生成无需手动切换即可一致。Curve 集成回归 11 passed（`curve_display.xml`），包含首次生成的渲染模式、中英文错误显示、原始诊断保留及清除；定向 Ruff、diff 检查通过。共享该刷新实现的 Freeform 集成回归 21 passed，耗时 163.23 秒，见 `freeform_shared_display.xml`。这两项真实界面复验待完成。

2026-09-26 19:08 后续检查确认旧桌面进程已结束，启动当前源码并通过原生打开项目对话框重开 `planar_gui_small/project.json`，实际观察模型、公共设置和 Planar Zigzag 操作恢复。电脑插件本轮能直接显示截图，但 `get_window_state` 的 JavaScript 返回值为 undefined，未取得可归档的截图对象；上述观察保留于任务工具记录，不新增本地截图通过项。现有 HTTP `/state` 也未提供窗口或屏幕尺寸，仍不能把截图分辨率作为指定逻辑窗口尺寸证明。下一步继续 Curve 当前版本实测及窗口尺寸证据核对，完整矩阵保持未完成。

## 实际窗口逻辑尺寸测量

在现有只读 `/state` 增加 `display`，分别报告客户区、带边框尺寸、像素比、最大化状态、可用屏幕尺寸和逻辑 DPI。六组布局回归同时验证尺寸回报，6 passed（`display_metrics.xml`）；定向 Ruff、diff 检查通过。依据为 [Qt QScreen](https://doc.qt.io/qt-6/qscreen.html) 与 [High DPI 测试说明](https://doc.qt.io/qt-6/highdpi.html#testing)。

实际桌面进程原生像素比为 2，可用屏幕 1280×764，窗口客户区 1282×785，见 `display_native_scale.json`，此前截图不能充作 1600×900 的证据。正常关闭空白窗口后，仅在新应用进程设置 `QT_SCALE_FACTOR=0.5`，未修改系统缩放；当前实际客户区 1600×900、带框 1602×946、像素比 1、可用屏幕 2560×1528，见 `display_test_scale.json`。已实际观察英文空白首页；三尺寸完整点击矩阵仍未完成。后续记录应注明此测试缩放，不与原生 200% 缩放混用。

## Curve 1600×900 英文实际点击进展

同一测试缩放下从空白首页进入 Curve，滚动两次到操作区，缺少 Part、Nozzle、Material 的提示包含打开对应设置和应用动作；未建操作时生成、导出禁用。通过原生文件对话框重开小平板，创建 Buildup，点击可见边并采用 Viewer 选边。应用时法向不明确，英文状态说明选择相邻面或指定方向；实际切换中文后对应说明正确显示。改回英文，选择 User-specified direction `(0,0,1)` 后应用及生成成功。首次生成显示细线，状态接口确认 `quality_mode=paper`，无须手动切换显示模式。

随后实际点击 Copy common Setup，独立页为英文，返回 Curve 后状态 Stale、导出禁用。点击 Use common Setup 并确认，恢复公共设置，旧结果仍为 Stale。只读状态归档为 `curve_1600_en_blank_state.json`、`curve_1600_normal_error_zh.json`、`curve_1600_generated_en.json`、`curve_1600_local_stale_en.json`、`curve_1600_common_stale_en.json`；点击截图在本任务工具记录中，插件仍未返回可保存的截图对象。状态数据中的旧结果 validation.ready_for_export 是生成时的验证快照，不能单独覆盖当前 Stale 状态。

此次未修改代码。矩阵英文 1600×900 改为进行中，未标通过：有向多边链的顺序、反向、不连续诊断与恢复，以及直接打开 STEP 的本尺寸步骤仍待核查。中文只检查了错误翻译，不能计为完整中文组合。本次 Curve 操作尚未保存，当前应用保留恢复公共设置后的 Stale 状态。

## Viewer 选边顺序修复

实际显示模型并追加相邻边，已选边为 `body_001_edge_0008`、`body_001_edge_0012`。进一步源码检查确认 SelectionState 仅有集合，Curve 采用选边时调用 sorted，无法兑现手册“按行进顺序逐条点击”的约定。依据 [Python 集合说明](https://docs.python.org/3/tutorial/datastructures.html#sets)，增加瞬态点击顺序，公共拾取逻辑记录新增、取消及重新选中；显式替换选择重置顺序，OpenGL 旧边切换入口复用同一逻辑。Curve 采用该顺序，反向标志仍由用户明确填写。旧项目无点击历史时保持稳定排序；操作中已经应用的有向边顺序继续由原有制造数据持久化。

相关回归 15 passed（`edge_order.xml`）；OpenGL 与项目读写兼容回归 44 passed、2 skipped、16 subtests passed（`edge_order_compat.xml`）。两项跳过均为 Windows 符号链接权限 WinError 1314，不计通过。新增按钮级顺序测试初次遗漏必需 controller 参数而失败（`edge_order_ui.xml`），补齐既有模型/控制器夹具后 1 passed（`edge_order_ui_retry.xml`）。定向 Ruff、diff 检查通过。当前桌面仍运行修改前版本；重启后的真实逆 ID 顺序点击、反向和断链恢复尚待完成，矩阵不关闭。

## 选边顺序与断链恢复的真实复验

保存旧进程只读状态 `curve_before_order_restart.json` 后正常关闭，启动最新源码，继续采用进程级测试缩放。通过原生项目对话框重开小平板，进入 Curve，先点击前侧边 `0012`，再点击相邻边 `0008`，新建操作后采用选边。返回输入区实际观察顺序为 `body_001_edge_0012,body_001_edge_0008`，默认反向标志 `0,0`，证明未按 ID 重排。

选择指定法向 `(0,0,1)` 后应用和生成，实际拒绝并报告 `curve.chain_disconnected [body_001_edge_0008]: gap 8 mm exceeds 0.01 mm`，导出禁用。只读端点核对显示第一条边终点 `(4,4,1)`、第二条边原起点 `(4,-4,1)`。仅在界面把反向标志改为 `0,1`，保持容差 0.01 mm，再应用、生成，出现连续折线路径，状态 warning，导出可用。错误与恢复状态见 `curve_reverse_pick_generation.json`、`curve_reverse_pick_recovered.json`，均包含实际窗口尺寸；截图保留在任务工具记录。

本次验证未改代码，Curve 双边操作仍未保存。断链拒绝目前显示原始英文诊断，需补齐双语可操作提示。英文 1600×900 的直接打开 STEP 步骤仍缺，故矩阵保持进行中；该两边入口样本不代表完整制造案例验收。

## 断链操作提示与可重开样本

为已复现的 `curve.chain_disconnected` 增加中英文说明，提示检查行进顺序、反向标志及相邻端点连接；界面同时保留原始错误行，因此边 ID、间隙和容差仍可见，tooltip 和状态接口也保留原始诊断。Curve 集成回归 13 passed（`chain_guidance.xml`），定向 Ruff、diff 检查通过。当前桌面尚未加载此文案修改，真实显示复验待重启完成。

实际使用 File → Save Project（Ctrl+S）及原生文件夹对话框，将已生成的双边操作保存到 `curve_gui_two_edges/project.json`，磁盘同时存在制造设置和源模型目录。随后从工具栏 Open STEP 直接载入 `small_plate.step`，状态栏报告 1 body、12 edges；勾选 Show model 后平板可见，原有生成结果变为 Stale、导出禁用，见只读状态 `curve_1600_direct_step.json`。此操作在已量测的 1600×900 英文窗口执行。新保存项目尚未实际重开；本轮未覆盖它。

## Curve 保存重开和双语断链提示复验

正常重启最新源码后，通过原生项目打开对话框读取 `curve_gui_two_edges/project.json`，Curve 页面、`0012,0008` 顺序、反向标志 `0,1`、指定法向 `(0,0,1)` 及公共设置恢复，见 `curve_two_edges_reopened.json`。在未保存的当前会话中将反向改为 `0,0`，应用并生成，实际出现断链说明；切换中英文均能看到顺序、反向和相邻端点连接提示，原始边 ID、间隙、容差仍显示，导出禁用。

实际截图已归档为 `curve_chain_guidance_live_en.jpg`、`curve_chain_guidance_live_zh.jpg`，状态见 `curve_chain_guidance_live_zh.json`。本轮找到截图归档途径：读取电脑工具返回的 image 内容块，分段写入原始 JPEG；未编辑图像。单次传递超过 64000 字节曾被自动审核拒绝，随后以较小分段完成。此处截图仅作内部证据，含操作光圈，不作为教程素材。磁盘项目保持有效反向版本；当前桌面为英文断链测试状态，未保存。完整矩阵仍需核对各步骤证据和设置编辑覆盖，不能据单项复验关闭全部 V2-01。

## Rotary 选择按钮布局修复

在英文 1600×900 原生界面进入 Rotary，两个并排的选边按钮出现文字裁切。参考 [Qt QGridLayout 文档](https://doc.qt.io/qt-6/qgridlayout.html)，将三类选择操作各放一行。首轮尺寸检查仍发现英文轴向边按钮 sizeHint 为 611，而实际宽度为 440；保留失败证据 `rotary_buttons.xml`（3 passed、3 failed）。随后将英文按钮改为完整的两行文字，不扩大编辑区。中英文三种目标尺寸共 6 项通过，见 `rotary_buttons_wrapped.xml`；定向 Ruff 和 diff 检查通过。首次测试命令的 PowerShell 内联 basetemp 表达式未正确传参，pytest 未执行；改用独立变量后运行上述检查。

本轮复用 five-axis-workbench-development、five-axis-slicer-validation 和 computer-use 流程。该结果是控件尺寸证据，当前桌面仍运行修改前进程，需重启后完成实际显示和滚动复验；Rotary 的实际设置、选面、生成与恢复流程尚未完成。

## Rotary 实际布局与空白门禁复验

正常关闭旧进程（退出码 0）后启动最新源码，经工作台卡片进入 Rotary。只读状态 `rotary_blank_live_en.json` 确认窗口客户区 1600×900、DPR 1、逻辑 DPI 96。英文三类选择按钮均完整显示，见 `rotary_buttons_live_en.jpg`；逐段滚动可到达工艺参数和底部创建、应用、生成、导出动作。空白状态生成和导出禁用；创建操作后提示先打开 STEP，未误报 Ready。切换中文后缺模型提示正确，见 `rotary_blank_gate_live_zh.jpg`；向上滚回选择区，三个中文按钮完整可见，见 `rotary_buttons_live_zh.jpg`。本轮仅关闭该尺寸的布局疑点，尚未覆盖 Rotary 导入、Setup 编辑、有效生成及 Stale；其他两种尺寸仍只有控件测试证据。

## Rotary 平面引用拒绝与恢复说明

中文 1600×900 窗口中通过原生对话框打开 `small_plate.step`，实际选择竖直边 `body_001_edge_0007` 并采用，再切换面选择并采用顶面 `body_001_face_0006`。应用几何与参数后出现 `rotary.surface_reference_invalid`，生成和导出禁用，见 `rotary_invalid_surface_live_zh.json` 与同名 JPG。原始中文界面仅有错误码，缺少恢复操作说明。

查阅 [Open CASCADE 表面类型文档](https://dev.opencascade.org/doc/occt-7.8.0/refman/html/GeomAbs__SurfaceType_8hxx.html)，并对照项目 Rotary 的圆柱/圆锥支持边界，增加中英文提示：选择与回转轴同轴的圆柱面或圆锥面，采用后重新应用。保留原始错误码。控件测试实际采用圆柱端部平面触发拒绝、切换语言、重新选圆柱侧面恢复，另验证既有选边选面生成流程；2 passed，见 `rotary_surface_guidance.xml`。定向 Ruff 与 diff 检查通过。桌面进程尚未加载此说明修改，实际错误恢复和有效样本生成仍待继续。

## Rotary 圆柱端面拒绝和侧面恢复复验

准备半径 20 mm、高 20 mm、Z 轴圆柱 `rotary_cylinder.step`，参数与 SHA256 记录于同名 JSON。该样本用作已有圆柱基底的入口测试，后续若生成仅验证单道螺旋贴附，不宣称完整零件或实机资格。重启最新源码，实际重开已有公共设置项目，再从 Rotary 打开此 STEP；直接更换 STEP 后公共设置恢复缺输入状态，未把旧模型设置自动当作当前已应用设置。

实际选取轴向边 `body_001_edge_0002`、端部平面 `body_001_face_0002`，应用后拒绝。中文及英文恢复说明已实际显示，原始错误码保留，见 `rotary_surface_guidance_live_zh.jpg`、`rotary_surface_guidance_live_en.jpg`。随后选择侧面 `body_001_face_0001`，重新采用轴边和表面并应用，几何错误消失，状态明确要求完整 Setup；见 `rotary_geometry_recovered_live_en.json` 与同名 JPG。尚未生成或导出。

复验发现失败刷新和语言切换会把未应用的几何输入恢复为旧值。为此让 Rotary 刷新支持保留编辑内容：失败应用与语言切换不重新加载操作字段；正常操作切换和成功应用仍按既有逻辑加载。扩展恢复测试检查轴边、错误面在失败和双语切换后保留，Rotary 集成 14 passed（`rotary_draft_recovery.xml`），Ruff 与 diff 检查通过。此项编辑保留修复尚待桌面重启复验；当前桌面保留已应用圆柱引用、未完成 Setup 的会话。

## Rotary 公共设置、保存重开与 Stale

在英文 1600×900 界面完成圆柱公共设置：实体分配 Part 并确认；采用内置 Generic 0.4 mm 喷嘴，测试接口 `OFFLINE-TEST-INTERFACE`、长度 18 mm、启用粗略 R–Z 碰撞外形；核对内置 Cura Generic PLA 1.75 mm 的示例建议 200/60 °C 后应用；Model CS、Build CS 分别确认零原点、Z=(0,0,1)、X=(1,0,0)；Placement 应用转台中心及零偏置。七项均 Valid，Setup 为 Ready with Warnings，见 `rotary_common_setup_live_en.json` 与 JPG。此处参数只用于离线软件检查。

通过 Ctrl+S 和原生目录对话框保存 `rotary_gui_cylinder/project.json`，SHA256=`6542fad907402a39f042495802dc22d805d8802d5f14278d1f3fc6c3e69bd1f9`。正常关闭旧进程后，最新源码实际重开项目，七项设置与圆柱轴边/表面引用恢复。返回 Rotary 后为 Stale 且禁止导出；实际点击生成，状态 Warning，导出可用，见 `rotary_generated_live_en.json`。警告为参考机床、基底碰撞几何缺失及机床碰撞几何缺失，不宣称已完成碰撞或实机资格。

实际 Copy common Setup 打开英文 Rotary 独立编辑器，返回后旧结果 Stale、导出禁用；随后 Use common Setup 并确认，结果仍 Stale，必须重新生成。见 `rotary_local_stale_live_en.json`、`rotary_common_stale_live_en.json`。本轮未导出六件套，也未完成全部尺寸矩阵；编辑保留修复虽已加载，仍需针对失败与语言切换做实际复验。

## Rotary 编辑保留实测与失败应用门禁

最新已运行源码中，将表面输入由有效侧面 `body_001_face_0001` 改为已核对的端面 `body_001_face_0002`，应用失败后切换中文、滚回顶部，轴边与端面输入仍完整保留，见 `rotary_draft_preserved_live_zh.jpg`。因此编辑保留修复已有实际证据。

同时观察到失败应用后生成按钮仍可用；代码 `_generate` 直接调用已应用操作，可能在用户看到失败输入时生成旧参数。增加页面的失败应用门禁，失败时禁用生成和导出，成功应用或重新加载操作后恢复按原资格判断。参考 [Qt QWidget enabled 属性](https://doc.qt.io/qt-6/qwidget.html#enabled-prop)，沿用现有按钮门禁，不改底层已应用结果。扩展测试先生成有效结果，再应用无效面，核对两种语言下按钮禁用、点击不替换旧结果，修正面并成功应用后生成恢复可用。Rotary 集成 14 passed（`rotary_apply_gate.xml`），Ruff 与 diff 检查通过。新门禁尚未加载到当前桌面，需重启复验；未把局部测试计为整个 V2-01 完成。

## Rotary 失败门禁与预览实际复验

正常重启最新源码并从原生对话框重开圆柱项目后，将侧面引用改为端面并应用。中文界面生成、导出均禁用，英文切换后仍禁用；见 `rotary_apply_gate_live_zh.json` 与中英文同名前缀 JPG。修正为侧面 `body_001_face_0001` 后成功应用，生成恢复可用；实际生成回到 Warning 且导出可用，见 `rotary_apply_recovered_live_en.jpg`。该门禁修复已有实际界面证据。

隐藏模型后观察到完整单道螺旋及起止标记，状态接口记录 72 个可见段、72 个绘制段，paper 模式，见 `rotary_path_hidden_model_live_en.json`、JPG。切换道宽模式后路径连续可辨，见 `rotary_bead_preview_live_en.jpg`。完整细线在工具缩小截图中部分线段较淡，尚不能作为最终教程素材通过依据。此小模型不替代高点数预览、过滤与取消验收。

## Tube pipe2 首次角色拾取（英文 1600×900）

实际从 Workbench 进入 Tube 并通过原生文件对话框导入 `example/pipe2/弯管新.stp`。导入后 Part、Nozzle、Material、Model CS、Build CS 为 Missing，Placement 为 Dirty；旧圆柱公共设置没有被当作新模型已确认设置。创建 Tube Thin-Wall Indexed 后从树节点打开编辑器，四项角色及 Apply 可见，底部 Generate、Preview、Export 在 Setup 未完成时禁用。

实际在模型中拾取管体 `body_002`、入口外圆 `body_002_edge_0003`（R=16）、基底 `body_001`。出口第一次拾取到相邻内圆 `body_002_edge_0012`（R=15），Apply 接受角色存储；此时因公共 Setup 缺失尚未执行几何生成验证，不能声称已经验证内外圆误选诊断。核对算法 `algorithms/tube/geometry.py` 会在生成几何时检查入口与出口均为外半径。随后在放大视图中实际改选出口外圆 `body_002_edge_0014`（R=16）并 Apply，见 `tube_pipe2_roles_live_en.json` 与 JPG。滚动可到达生成区并返回角色区。公共 Setup、生成、误选生成诊断、保存重开、导出和严格回读仍待执行；本段仅记录角色拾取的局部进展。

## Tube 公共设置与默认生成发现的问题

英文 1600×900 实际把 body_001、body_002 分配为 Part 并确认；内置 Generic 0.4 mm 喷嘴使用离线测试接口、18 mm 长度和粗略 R–Z 外形，材料采用内置 Cura PLA 1.75 mm 并核对 200/60 °C 示例值。Model CS、Build CS 分别确认零原点、Z=(0,0,1)、X=(1,0,0)，Placement 采用转台中心零偏置。七项均 Valid，Setup Ready with Warnings。每次应用后缺项提示转到下一未完成节点。

保持 Tube 默认道宽 0.6 mm、层高 0.2 mm、楔角 15°、净空 5 mm 等参数，实际 Generate 后点击 Cancel Generate。窗口短时显示“未响应”，随后仍为生成中；最终生成 Error，而非及时取消。状态快照 `tube_pipe2_default_generation_live_en.json` 记录生成时刻 2026-09-26T12:41:50.444308+00:00、ready_for_export=false，问题代码包括 xyzac.rotary_singularity、tube.nozzle_obstacle_collision、MACHINE_REFERENCE_ONLY。同名 JPG 记录最终界面。没有导出，取消与响应项判为待修复。

已查阅 [Qt QCoreApplication 事件处理说明](https://doc.qt.io/qt-6/qcoreapplication.html#processEvents) 和 [Qt 线程基础](https://doc.qt.io/qtforpython-6.8/overviews/qtdoc-thread-basics.html)。代码核查发现 Tube UI 当前同步生成并在取消回调中泵送事件；indexed_tube 产品链仅阶段间检查取消，切层循环未提供检查，且求解器已有 checkpoint 参数没有沿该链传入。后续应补齐长步骤的可取消性并进行实际点击复验；碰撞需独立核对姿态、喷嘴和基底关系，不应移除碰撞检查换取通过。本轮尚未修改这部分代码，也未把默认生成失败计为案例闭环完成。

## Tube 分度取消检查传递修复

将产品链的取消回调传入逐层截交、XYZAC 求解和验证。逐层生成在每层开始前检查；几何误差检查按每 64 点/段检查；碰撞阶段复用已有 checkpoint 接口。回调抛出既有 GenerationCancelled，沿现有路径保留旧状态。没有改变几何、误差阈值或碰撞资格。

新增测试在进入截交、求解、验证阶段后请求取消，并确认当前阶段被中断、旧状态不被发布结果覆盖。初次运行因测试使用不合法的短哈希失败，修正测试数据后产品流程 6 passed、2 subtests passed（tube_cancel_regression_fixed.xml）；加强“阶段内部中断”断言后，取消用例 2 passed、2 subtests passed（tube_cancel_phase_interruption.xml）。Ruff 与 git diff --check 通过。使用既有 five-axis-workbench-development、five-axis-slicer-validation 与 computer-use Skills；环境预检沿用当前会话已核验结果。桌面进程尚未重启，实际取消复验仍待完成。

实际 Save Project 保存 tube_gui_pipe2/project.json，SHA256=c81019eeba6458625308feab5f75dd8700a42be1a446b5306e830ef1cdb2fe1a。此项目保存当前有效 Setup 与生成 Error 的证据，用于重开后复现及修复检查，不是合格导出交付物。

## Tube 取消修复实际复验与碰撞定位

正常关闭旧进程并启动最新源码，通过原生 Open Project 重开 tube_gui_pipe2/project.json。七项 Setup、管体、入口、出口、基底和默认参数恢复；操作页显示尚未生成，因此本次实际检查不宣称恢复了旧 Error 产品状态。保持相同默认参数启动 Generate，在生成中点击 Cancel Generate；点击加截图工具耗时 339 ms，截图已显示 Generation cancelled，Generate 与 Apply 恢复、Preview/Export 禁用。见 tube_cancelled_live_en.jpg、JSON。该数值是一次工具观察耗时，不是统计性能基准。旧结果保留由前述回归测试覆盖。

原失败快照含 43775 个路径点。首个碰撞对应 point-0000128 的 depart：从 z=5.1 到 z=10.1 mm；随后 approach 从 z=10.3 到 z=5.3 mm。基底上表面 z≈5 mm，喷嘴粗略 R–Z 外形为 (0.9,0)、(2,18) mm。当前验证把截面半径作为球包络，只有沉积段及离开段起点可放行尖端接触，离开段后续采样和接近段仍按球包络检查。这说明应进一步核查近基底过渡接触的保守误报；尚未据此改动碰撞判据或声称已无碰撞。姿态 -Z 对应喷嘴指向工件，现有碰撞实现以反轴向计算喷嘴外形中心，不能仅凭 -Z 判定姿态错误。

## Tube 尖端平面分离判据修复

参考 [CGAL 有向平面定义](https://doc.cgal.org/latest/Kernel_23/classCGAL_1_1Plane__3.html)，以喷嘴尖端为平面原点、喷嘴轴为法向，对整个障碍 AABB 求最小投影。仅当 R–Z 外形全部在尖端后方，且障碍盒整体在尖端前方有严格正间隙时，排除球包络在尖端前方延伸造成的误报。接触、穿入、跨平面盒仍按原碰撞检查执行；1e-9 mm 只用于保守排除浮点边界，不增加可穿入制造容差。IPW 检查保持原规则。

新增正间隙/接触/穿入、基底/夹具、双向接近和离开、斜轴与跨平面盒测试。初次新增测试误把沉积材料量保留在非沉积点，修正构造后 7 passed（tube_tip_plane_fixed.xml）；此前同轮已有相关测试 51 passed、3 subtests passed（tube_tip_plane.xml，包含首次新增测试失败记录）。Ruff 与 diff 检查通过。碰撞判据版本变动同步提升 Tube context 到 v6，三种 Tube 产品算法版本分别提升，避免复用旧资格。

对原实际失败快照的全部 43775 点重放碰撞检查，含基底障碍及 IPW，检查 227309 个采样，未报告碰撞，耗时约 2.59 s，见 tube_tip_plane_replay.json。该检查未重生成路径，不替代最新 GUI 生成、预览、严格回读和导出；这些仍待执行。使用五轴开发、验证和制造前置检查经验，首层仍沿原管体中心线从 z=5.1 mm 开始，基底顶面 z≈5 mm，没有变更生长策略或阈值。

## Tube 最新 GUI 生成、导出与重开状态问题

重启到包含取消及尖端平面修复的源码，通过原生对话框重开 pipe2 项目，实际 Generate、Preview Path、Export Result。生成最终为 Warning，保留 xyzac.rotary_singularity 与 MACHINE_REFERENCE_ONLY，无碰撞 Error。38 秒观察时仍在生成，期间实际缩放可响应；100.873 秒观察时已完成，这只是观察区间，不是精确生成耗时。完整线条预览与状态见 tube_generated_preview_live_en.jpg、JSON。

GUI 导出目录 tube_pipe2_export 含六件套。直接读取磁盘 main.gcode，验证 200/60 °C 包装并严格回读：43775/43775 点，坐标、进给、挤出及顺序均无差异。machine_axes.csv 的 43775 行 ID、时间及五轴值与 manifest 一致，toolpath 原始 JSON 与 manifest 内嵌内容一致。初次辅助核查对反序列化再序列化的浮点向量作精确比较触发断言，改为核对文件原始结构并单独严格回读；没有改动导出文件。摘要及六文件 SHA256 见 tube_pipe2_export_readback.json。machine_executable=false。

实际另存 tube_gui_pipe2_generated/project.json，SHA256=ad50895730e59ec50154d64b66487dab463a52a5be858a6dee725f49224c01f1。通过 Open Project 重开后发现界面残留旧路径、“已导出”文字和可用预览/导出按钮，而只读状态 products=[]，见 tube_generated_reopened_live_en.jpg、JSON。不能把该画面当作生成结果已持久化的证据。

核查发现 set_controller 切换控制器时没有清理运行时路径，且树重建阻断信号后未重新绑定编辑器。参考 [Qt QTreeWidget 当前项信号说明](https://doc.qt.io/qt-6.10/qtreewidget.html#currentItemChanged)，补齐控制器更换时清理路径、重置产品按钮/提示，并显式激活新当前项。新增同一操作 ID 的替换反例；首次测试未选中操作，修正测试前置操作后，完整 Tube UI 回归 36 passed、2 subtests passed、1 failed（tube_reopen_state_fixed.xml）。失败定位到语言切换时通用标题刷新覆盖操作类型翻译；标题改为按当前操作类型翻译。随后重开状态与标题针对性回归 3 passed（tube_reopen_title_fixed.xml）。Ruff 与 diff 检查通过，桌面复验尚待重启。本轮继续使用 five-axis-workbench-development、five-axis-slicer-validation、computer-use；沉积/空移细查、错误角色生成恢复及设置变更 Stale 仍未完成。

## Tube 重开状态修复桌面复验

正常关闭旧进程，以当前源码启动。原生 Open Project 重开 tube_gui_pipe2_generated/project.json，Setup 七项和四个几何角色恢复，操作显示尚未生成、Preview/Export 禁用。再实际 Generate 得到 Warning、Preview Path 显示完整路径，然后在同一进程重开同一项目：旧路径清除，按钮禁用，提示恢复为尚未生成。见 tube_reopen_fixed_live_en.jpg、JSON；这覆盖了实际发现问题的同操作 ID 场景。模型显隐保留用户开关状态，截图中模型隐藏。

双语 Tube 手册补充保存重开语义：Setup 与操作输入保存，运行时路径需重新生成；英文 Preview Path 按钮文字同步当前界面。Tube 左侧树直接编辑公共 Setup，没有其他四工作台的独立副本入口，依据 quickstart_clickthrough_zh.md 公共/独立设置说明；矩阵中 Tube 独立副本项应记不适用，公共设置改变后的 Stale 仍须实测。

## Tube 公共设置 Stale 与端口错误恢复实测

实际生成 Warning 后，在 Material 节点取消“已核对”并 Apply。Material 转 Draft，Operations 转 Dirty；操作显示 Stale，Generate、Preview、Export 禁用，问题列表明确要求核对材料并应用。重新勾选并 Apply 后 Setup 恢复 Ready with Warnings，旧产品仍需重新生成。见 tube_setup_stale_live_en.jpg、JSON。

将出口改为 body_002_edge_0012（R15 内圆），Apply 后 Generate 立即拒绝，代码 tube.port_not_outer_boundary，导出禁用。滚动可查看完整原因。切换中文后标题翻译正常，但具体端口原因仍为英文，见 tube_port_error_live_en/zh.jpg 与中文状态 JSON。随后恢复 body_002_edge_0014（R16 外圆），Apply、Generate，回到 Warning，预览/导出恢复可用，见 tube_port_recovered_live_zh.jpg、JSON。本次没有另导出或覆盖原六件套。

参考 [Qt 用户可见文字翻译说明](https://doc.qt.io/qt-6.10/i18n-source-translation.html)，在项目现有错误码映射中加入端口外圆的中英文可操作提示，保留代码；不改变算法诊断。针对性翻译及标题测试 2 passed（tube_port_error_translation.xml）。另外实际发现 Apply 修正角色后旧错误提示暂留，补齐 Apply 后产品状态刷新。新增反例初次缺少四角色，错误对话框触发测试进程 access violation；捕获错误后定位为测试前置条件缺失（tube_apply_status_diagnostic.xml），补齐角色后 2 passed（tube_apply_status_fixed.xml）。Ruff 与 diff 检查通过。新翻译及 Apply 即时刷新还需重启后的桌面复验。

材料反复确认时，项目配置显示名会累加“project profile”，本次观察到三次后文字被截断；这是待处理的显示名问题，尚未修改。其余待验收包含遗漏角色、三尺寸完整覆盖、Freeform、代表案例沉积/空移与发行门槛。

## Tube 双语错误和 Apply 刷新复验、遗漏角色修复

重启最新源码后，打开已保存项目遇到上次测试产生的 YAML 工作态差异，实际选择“使用项目”，恢复已保存的有效设置。再次将出口改为内圆并 Generate，中文显示“端口必须使用管体外圆边”，英文显示重新选择 inlet/outlet outer edges；错误码保留。见 tube_error_fixed_live_zh/en.jpg。恢复外圆并 Apply 后，无需重选操作，状态立即转为 Stale，见 tube_apply_fixed_live_en.jpg。此两项桌面复验通过。

实际把出口设为“未填写”并 Apply，发现原实现仍提示成功；命令层允许部分字段修改，UI 忽略空值后沿用了旧出口。见 tube_missing_role_before_fix_live_en.jpg。已在 UI 完整表单提交前要求四角色齐全；缺失时显示双语补齐提示、保留原领域操作、禁用生成与预览/导出。失败门禁保持到成功 Apply 或显式重新载入编辑器；语言切换不解除门禁。同步更新角色下拉框首项“未填写/Not set”的语言，避免切换后残留。针对性 4 passed（tube_missing_roles.xml），桌面复验待重启。

材料和喷嘴编辑共用项目名称后缀规范化，旧重复后缀也会在下次编辑时合并为一次。参考 [Python 精确后缀处理](https://docs.python.org/3/library/stdtypes.html#str.removesuffix)，仅处理末尾完整的既有标记，不改名称主体。资源选择与命令回归 31 passed（tube_profile_name.xml），0 至 3 个后缀输入均核对为一个；Ruff 与 diff 检查通过。此显示名修复的实际重复材料确认仍待核对。

使用的 Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use（沿用本任务已读流程）。本轮没有重跑 NC 几何或修改原六件套；主要剩余项是 Tube 新遗漏角色门禁复验、Freeform 首次使用和全尺寸证据覆盖，后续仍按完整 V2-01—V2-05 范围执行。

## Freeform 空白入口及导引拾取实测

当前源码重新启动，逻辑客户区 1600×900，检查中文空白入口并切换英文。编辑区滚到底部后创建 Surface 草稿；缺失 Part、喷嘴、材料和坐标的提示包含下一步操作，Generate、Export 保持禁用。原始截图为 freeform_blank_live_zh.jpg、freeform_blank_live_en.jpg、freeform_blank_bottom_live_en.jpg，创建后的只读状态为 freeform_blank_live_en.json。

实际 Open STEP 加载 small_plate.step（SHA256 a7d7037077db31d15c6784f25d20de3f964bb5b28480f707c7f1b6bd81ff5dc1）。在视口选顶面边，再切换 Face 选相邻顶面，点击 Use selected edges 后正确回填 body_001_edge_0012、反向标志 0 和 body_001_face_0006，见 freeform_selected_live_en.jpg。打开左侧 Part，指定 body_001 为 Part 并 Confirm 后节点转 Valid，见 freeform_part_live_en.json。其余 Setup、两种模式的遗漏角色恢复、生成和 Stale 尚未验证，不关闭此尺寸组合。

本段使用 computer-use，沿用已读的工作台开发和验证门槛。截图为真实桌面原件，仅用于内部检查；蓝色鼠标提示未作为教程插图。本次没有新增代码修改或重跑算法回归。

## Freeform 公共设置、实际生成与独立设置失效检查

在同一英文 1600×900 桌面进程中补齐公共 Setup：Generic 0.4 mm 喷嘴使用 OFFLINE-TEST-INTERFACE、总长 18 mm、启用粗略 R-Z 包络；Cura Generic PLA 1.75 mm 的 200/60 °C 预设标记已核对；Model CS 与 Build CS 分别确认原点 (0,0,0)、Z=(0,0,1)、X=(1,0,0)；Placement 使用转台中心和零偏移。七节点均 Valid，整体 Ready with Warnings，见 freeform_setup_valid_live_en.jpg。以上仅为离线检查设置。

材料连续执行已核对应用、取消核对应用、重新核对应用，状态 Valid→Draft→Valid，显示名始终只有一次 project profile，见 material_profile_name_fixed_live_en.jpg。共享材料名称修复的桌面复验通过。

返回工作台时未应用的导引字段已清空，但视口选择保留；重新 Use selected edges 并 Apply，Generate 启用。实际生成得到 Warning、8 个沉积线段，导出启用；见 freeform_generated_live_en.jpg/JSON。随后 Copy common Setup 打开独立设置，返回工作台显示 Stale、导出禁用，见 freeform_local_stale_live_en.jpg。再 Use common Setup 并确认恢复，当前只读状态仍为 Stale，见 freeform_common_stale_live_en.json。末次截图遇到窗口最小化及用户输入提示，未反复抢占窗口；恢复公共后的稳定截图仍待补充。

Full lines 画面线条较细，仍待路径显示专项核对。检查了继承的 CurvePage 实现，paper 是 Full lines 的既有模式标识，不能仅凭该名字判断模式不一致；参考 [Qt QComboBox 信号说明](https://doc.qt.io/qt-6/qcombobox.html)。本轮没有改算法或 UI 代码，使用 computer-use，沿用 five-axis-workbench-development 与 five-axis-slicer-validation 门槛。遗漏角色、模式切换、未应用编辑保留、保存重开和完整尺寸覆盖仍未完成。

## Setup 更新保留未应用操作输入

针对实际观察到的 Freeform 返回 Setup 后导引被清空，检查主窗口和工作台导航：公共同步、复制独立设置、恢复公共设置、提交独立设置及重新进入工作台均可能调用默认 refresh，重新载入已保存操作并覆盖编辑值。将这些纯 Setup 刷新改为 reload_controls=False；Planar 补齐与 Curve、Freeform、Rotary 相同的刷新参数，并在此模式保留实体勾选及参数。显式重新载入仍恢复领域操作。此修改不把未应用草稿写进已保存操作，也不解除旧结果 Stale。

新增四工作台反例：编辑进给值而不 Apply，依次执行公共设置修改后进入工作台、公共同步、复制独立设置、提交独立设置、恢复公共设置，编辑值保留；显式刷新恢复原值。首次测试遗漏 replace_setup 的必填 reason，4 failed（setup_operation_drafts.xml），补齐后完整 Setup 集 27 passed（setup_operation_drafts_fixed.xml）。导航入口补齐后针对性 4 passed（setup_operation_drafts_navigation.xml）。Ruff 与 git diff --check 通过。当前桌面进程尚未重启，此修复的真实返回流程仍待复验。

使用 five-axis-workbench-development、five-axis-slicer-validation，复用本轮已验证解释器及串行 Qt 规则。Freeform 自身 Apply 失败后的编辑保留仍须单独检查，不能用本次 Setup 同步测试代替该失败场景。

## Freeform Apply 失败保留、保存重开与桌面恢复

回归复现了 Freeform 自身 Apply 失败后 refresh 重载输入的问题：错误的多导引 JSON 被旧内容替换（freeform_apply_draft_before.xml，1 failed）。参考 [Qt 手动提交与恢复语义](https://doc.qt.io/qt-6/qdatawidgetmapper.html)，在现有命令结构中保留失败草稿，并设置失败门禁，阻止生成和导出沿用旧操作；成功 Apply 或显式载入解除门禁。没有引入新的 Qt mapper。导引失败、旧结果禁用及恢复和相关 GUI 回归 5 passed（freeform_apply_draft_fixed.xml）；实体 JSON 失败保留、语言切换和成功恢复补充 1 passed（freeform_solid_apply_draft.xml）。Ruff 与 diff 检查通过。

真实界面保存 freeform_gui_small/project.json，SHA256=98078decb1f03ba160c0bc9b26ce97690b830ec874217bff4083080549b1065b。正常退出旧进程、以最新源码启动后 Open Project 重开：导引边 body_001_edge_0012、标志 0、法向面 body_001_face_0006 与公共资源恢复，旧路径不显示；见 freeform_reopened_live_en.jpg/JSON。

英文 1600×900 实际把标志改为 0,1（一条边对应两项标志）并 Apply，显示 one reverse flag is required for each edge，Generate/Export 禁用（freeform_apply_failed_live_en.jpg）。随后 Copy common Setup 并返回，错误门禁仍保持，顶部 0,1 草稿未丢失（freeform_draft_preserved_live_en.jpg）。修正为 0 时按钮仍禁用，再成功 Apply 后恢复 Generate、Export 仍禁用，见 freeform_apply_recovered_live_en.jpg。此次完成 Freeform 的失败保留和独立 Setup 返回实测；另外三工作台及公共设置更改返回仍需桌面覆盖，未据此关闭整个矩阵。当前项目处于独立 Setup，修改未覆盖保存的公共版项目。

使用 five-axis-workbench-development、five-axis-slicer-validation、computer-use。中文错误提示、实体模式实际拾取与遗漏角色、各尺寸覆盖仍待继续。

## Freeform 实体模式实际拾取发现单面限制

英文 1600×900 新建 Surface Solid 操作，空选择 Apply 显示 solid-fill selection JSON is required，生成/导出禁用，见 freeform_solid_missing_live_en.jpg。随后真实拾取根边 body_001_edge_0012、顶面，再左键拖动旋转平板拾取底面。Use selected geometry 仍报缺少两面；只读状态证实 face_ids 只剩 body_001_face_0005。见 freeform_solid_pick_before_live_en.jpg/JSON。

根因是 Freeform 继承 Curve 的默认面单选协议，已有实体测试直接 set_selection 写入两面，未覆盖逐面拾取。改为根据当前操作类型配置 PickRequest：实体模式 face 多选，导引模式 face 单选；操作切换和重开时同步协议，body/edge 保留既有多选。参考 [Qt 多选的逐项切换语义](https://doc.qt.io/qt-6/qabstractitemview.html#SelectionMode-enum)，复用项目现有 apply_pick_selection 实现，没有改变全局 Viewer 默认。

原实体角色测试改为逐个命中共享拾取协议，覆盖根边与两面回填、Apply、失败恢复以及切回导引单选。首次测试遇到旧 stub 的 set_mode 不设置 PickRequest（freeform_face_pick_before.xml，1 failed）；生产现场的单面问题已由真实截图与状态证明。新页面显式设置协议后，相关 GUI、重开、失败恢复集 8 passed（freeform_face_pick_fixed.xml），Ruff 通过。双语 Freeform 手册补充多面点击和旋转操作。当前桌面仍为修复前进程，修复后实际两面回填与 Apply 待复验。

使用 five-axis-workbench-development、five-axis-slicer-validation、computer-use。本次仅修复拾取，不声称小平板实体生成或代表实体案例验收通过。

### 多面选择修复后的桌面复验

重启最新源码后，在英文 1600×900 界面重开 freeform_gui_small/project.json，新建 Surface Solid Fill。实际点击根边 body_001_edge_0012、顶面 body_001_face_0006，左键拖动旋转模型后点击底面 body_001_face_0005。只读状态确认两个面及根边同时保留。点击 Use selected geometry 显示 Selection captured; apply to persist it；点击 Apply 后无 last_error，Generate 启用、Export 禁用，状态 draft。证据为 freeform_solid_pick_fixed_live_en.jpg 和同名 JSON，原截图保存在本轮内部证据目录。

本次使用 computer-use，沿用已读取的开发与验证门槛，没有新增代码修改或重复运行已通过测试。此结果关闭实体模式逐面点击和应用的修复复验；尚未验证该实体操作生成、切回导引模式的真实单选行为，也未关闭 Freeform 整个尺寸与语言矩阵。

### 单个实体子路径的工序身份修复

随后实际点击 Generate，出现 toolpath operation_id must match manifest operation_id，Export 保持禁用，见 freeform_single_solid_error_live_en.jpg/JSON。单层 Surface Solid 算法返回带实体与层后缀的子工序 ID；适配器在只有一条路径时跳过合并，使结果清单的父工序 ID 与路径不一致。新增 controller 回归得到相同异常（freeform_single_solid_before.xml，1 failed），确认不是几何拾取问题。

修复保留已经匹配父 ID 的单路径；其余情况复用 merge_toolpath_sequence，将路径、点和事件归属父工序，同时保留 source_toolpath_ids 追溯。该合并入口只在第二条路径起添加转换，因此单路径不增加 operation_change。参考 [Python dataclasses.replace 官方语义](https://docs.python.org/3/library/dataclasses.html#dataclasses.replace)，复用现有点和事件复制实现；没有仅改清单来绕过一致性检查。产品算法版本升为 v3。新增回归检查父 ID、点和事件一致及无伪工序转换；与原碰撞拒绝回归串行运行，结果待记录。Ruff 通过。

测试等待期间实际切回 Freeform Surface，并再次点击当前底面，只读 face_ids 变为仅 body_001_face_0005，根边保留（freeform_guide_single_face_live_en.json）；导引单选协议复验通过。使用 computer-use、five-axis-slicer-validation，沿用 five-axis-workbench-development。本次生成修复仍需重启后的桌面复验。

串行回归结束：2 passed、21 deselected，173.14 s，见 freeform_single_solid_fixed.xml。单路径身份检查和原有不安全工序转换拒绝均通过；实际桌面进程尚未载入生成修复。

### 实体项目保存重开与生成修复实测

真实 Save Project 保存到 freeform_gui_solid/project.json，SHA256=c91cab02b73c046cd399720c8183a6829fb81873923eb2b2d8e4d83f8b2e736a。正常退出后启动最新源码，以 Open Project 重开，实体工序恢复，旧路径为空，Generate 启用、Export 禁用。点击 Generate 后工序身份异常消失，v3 结果清单、路径与父工序一致，得到 882 点、41 事件的 Error 结果，见 freeform_single_solid_generated_live_en.jpg/JSON。

两项拒绝有具体依据：默认 solid_thickness_mm=0.2，而所选两面的距离及 CAD 厚度为 1 mm，单层材料体积 13.44 mm³、CAD 体积 64 mm³，相对误差 0.79。空移目标接触报告对应当前测试喷嘴尖端外半径 0.9 mm、道距约 0.39 mm；报告所列旧线段至目标喷嘴中心最近距离约 0.8725 mm，处于该尖端截面内部，几何距离为零与当前包络相符。参照 [CGAL 距离查询文档](https://doc.cgal.org/latest/AABB_tree/classCGAL_1_1AABB__tree.html)区分距离计算与后续间隙判据；本轮没有修改碰撞门槛。Export 保持禁用，readback=blocked，不能把身份修复通过记为实体输出合格。

使用 computer-use，沿用开发和验证 Skills。本次补齐修复后的真实生成证据；厚度与喷嘴配置恢复流程、中文诊断可读性及完整矩阵继续检查。没有重复运行未改动源码的测试。

### 实体生成诊断的双语说明

实际切换中文后，两项 Error 仍仅显示内部代码，无法从列表得知恢复步骤（freeform_diagnostics_before_live_zh.jpg）。在现有共享标签中补充实体体积偏差和无安全空移路线的中英文原因与操作建议；复用 Curve/Freeform 问题列表，将原始 context 数值加入悬停详情，保留 Qt.UserRole 的完整问题数据与定位 ID。依据 [Qt QListWidgetItem 的文本、数据与提示接口](https://doc.qt.io/qt-6/qlistwidgetitem.html)，未修改领域验证或导出门槛。

新增双语界面检查验证恢复提示、0.79 体积误差、0.2 mm 间隙、point-43 定位和原始数据仍可读。首次测试导入了不存在的 manufacturing.validation（freeform_diagnostics.xml，2 failed），修正为既有 manufacturing.setup 后 2 passed（freeform_diagnostics_fixed.xml）；Ruff 通过。使用 computer-use、five-axis-slicer-validation，沿用开发 Skill。桌面进程尚未重启加载文字修复，实际显示与参数恢复继续检查。

### 双语实测与厚度错误恢复

重启最新源码、重开 freeform_gui_solid 项目，中文实际 Generate 后体积与空移错误显示原因及恢复建议，列表正常换行；切换英文仍保留结果与导出禁用，见 freeform_diagnostics_fixed_live_zh/en.jpg。悬停提示未通过桌面工具触发，其内容由上一轮 Qt 测试证明，不声称已完成实际悬停检查。

实际在附加参数 JSON 将 solid_thickness_mm 改为 1.0，Apply 后旧结果 Stale，重新 Generate。只读结果确认 5 层、材料体积 67.2 mm³、CAD 体积 64 mm³、误差 0.05，体积错误消失。仍有 motion.transition_route_unavailable，目标 Z=18.6 mm，第二层目标姿态与既有沉积材料的间隙 0.06339 mm 小于 0.2 mm 要求。当前从顶面向下的实体角色需要进一步核查承接和生长方向，不能仅缩小喷嘴包络来取得通过。见 freeform_thickness_recovery_live_en.jpg/JSON；此次参数未覆盖原保存项目。

本轮使用 computer-use，沿用开发与验证 Skills，无代码修改。下一步核查实体角色方向与层间转换提示，再完成参数恢复；全尺寸矩阵继续保留未完成状态。

### 厚度模式生长方向反例

对照制造验证 Skill 的承接与方向规则，发现 surface_thickness 分支的偏移为 surface_point - depth * normal，depth 按层递增，而 nozzle_axis 同样为 -normal。层间增长与喷嘴朝向同向，不能仅交换两面的角色修复。新增独立盒体反例 test_thickness_growth_moves_away_from_nozzle，比较相邻层中心位移与喷嘴轴的点积：实测 +0.2 mm，预期应为负，1 failed（freeform_thickness_direction_before.xml）。此反例当前保留为失败，尚未改生产算法，不能声明回归全绿。

参考 [Prusa 官方逐层支承说明](https://help.prusa3d.com/article/first-print-with-prusaslicer-2-9_1753?product=prusaslicer)，同时保留本项目喷嘴轴指向沉积面的约定。修正前还需明确 selected surface 与 opposite face 的起始承接角色，选择符合既有操作语义的层序或轴向修复，并检查首层实际承接；不得仅以方向点积转负作为制造放行条件。root_edge_outward 是独立分支，不能据本反例撤回或认可其资格。使用 five-axis-workbench-development 的 manufacturing-validation 规则及 five-axis-slicer-validation；当前实体生成失败仍阻止导出。

### 厚度模式喷嘴轴修复

核对现有双语方法说明及 Freeform 手册，selected surface 的既有定义为承载面，层沿 inward 方向向对面增长。保留该层序，修正厚度模式 nozzle_axis 为承载面的外法向，使喷嘴朝向承载面并与层间增长相反；root_edge_outward 仍由独立 growth_reference 求轴。产品算法版本升为 v4，避免复用旧资格。

方向反例补充独立盒体层中心 Y=-0.3、-0.1、0.1、0.3、0.5 mm 和喷嘴轴 (0,-1,0) 的解析断言。完整 surface_solid_fill 集 8 passed（freeform_thickness_direction_fixed.xml），含上下根边的 outward 生长检查；Ruff 通过。产品身份和不安全转换拒绝回归正在串行运行，freeform_thickness_product_fixed.xml 待结束。双语实体方法手册说明首层距承载面一个有效层高、几何角色不创建基体及向上打印应选择底面。当前桌面仍载入 v3；承接和 v4 实际生成未验收，不能由方向测试关闭制造资格。

产品回归完成：2 passed、23 deselected，184.28 s（freeform_thickness_product_fixed.xml）。单路径父工序身份与原有不安全转换拒绝均通过。继续修复恢复流程实际出现的 motion.transition_route_unavailable 缺少双语说明，在既有标签中补充承载面、生长方向、喷嘴外形及目标姿态的核查建议；诊断测试覆盖 transition-02-depart 和实测间隙 0.06339，2 passed（freeform_transition_diagnostics.xml），Ruff 通过。使用 five-axis-slicer-validation，沿用开发门槛。桌面 v4 和首层承接仍待复验。

### v4 底面承载角色的真实生成

正常重启源码、重开实体项目后，先从 STEP 只读核对底面 face_0005 的根边 edge_0011：端点 Z 均为 0。再实际在角色 JSON 编辑器设置底面为 surface_face、顶面 face_0006 为 opposite_face、edge_0011 为 root_edge，厚度设为 1 mm；Apply 后实际 Generate。此项是角色编辑器操作，不冒充 Viewer 重新拾取。设置尚未覆盖原保存项目。

状态记录证实产品 v4、5 层体积误差 0.05 通过，首层接触报告位置 Z=0.2 mm，原层间转换方向拒绝消失。仍在第一层第二道入口被 motion.non_deposition_route_unavailable 拒绝：旧线段与目标均在 Z=0.2 mm，当前 0.9 mm 尖端外半径包络仍相交，距离 0、要求 0.2 mm。没有降低碰撞门槛或改变喷嘴。证据为 freeform_v4_bottom_support_live_en.jpg/JSON，Export 禁用。

使用 computer-use，沿用开发/验证门槛。当前结果只证明 v4 按底面角色进入正确高度并保留同层拒绝；尚未完成整个首层承接、完整预览和导出验收。问题列表初始可视区被五条奇异位姿 Warning 占据，具体 Error 需向下滚动，后续应检查诊断呈现优先级及正常参数恢复。

### 阻止导出的错误优先显示

针对上轮真实界面中 Error 被五条 Warning 推出初始可视区的问题，在 Curve/Freeform 共享列表填充前按是否为 error 稳定排序。领域报告、诊断上下文和导出判据不变，同级问题保留原顺序。依据 [Python 稳定排序保证](https://docs.python.org/3/howto/sorting.html#sort-stability-and-complex-sorts)，无需在领域报告中重排或删除 Warning。

双语诊断回归加入五条前置 Warning，检查三条 Error 仍排在首位、各项数值与定位信息保留、Warning 原顺序完整，2 passed（freeform_error_priority.xml）；Ruff 通过。使用 five-axis-slicer-validation，沿用开发 Skill。真实桌面排序仍待重启复验；随后继续 Tube 遗漏角色等已有待验项，未将当前小平板的拒绝替代代表案例完整验收。

### 累计修改的质量检查

准备桌面复验时识别到另一进程 tmp/capture_paper_refresh.py 正在生成论文截图，本轮保留双方窗口，转做静态检查。自己的 v4 应用尚未加载错误优先级修复，不能用当前窗口证明该项完成。

运行 scripts/check_quality.py，先发现 viewer_common.py 的 UP038，再发现 tube_ui_text.py、ui.py、viewer_common.py、test_tube_ui.py 格式偏差。按仓库现有工具规则修改类型组合写法并格式化四文件；复查 Ruff、Migrated Ruff、Security Ruff、61 文件格式通过。日志依次为 quality_current_2322.log、quality_current_2322_fixed.log、quality_current_2322_format.log，均位于本任务 evidence 目录。另行运行 Mypy，193 个源文件无错误，见 mypy_current_2324.log。

[Ruff 官方 UP038 文档](https://docs.astral.sh/ruff/rules/non-pep604-isinstance/)说明该规则已在新版移除，联合类型写法并非当前通用推荐。本轮只满足项目现有版本门禁，未升级工具或推广改写其他模块。

质量脚本仍在 Context budget 停止：16 项超限涉及 Surface Solid 路径构建、Curve/Freeform/Rotary/Tube 页面、主窗口重开项目和 Tube 碰撞检查。完整清单保留在 quality_current_2322_format.log；后续按职责整理直接相关代码，不提高基线掩盖增长。类型检查通过不能替代这项门禁、运行时回归或桌面验收。使用 five-axis-workbench-development、five-axis-slicer-validation；目标仍进行中。

### 诊断显示职责拆分与 Tube 缺失角色实测

将 Curve/Freeform 共用的问题列表排序、文字、详情和几何定位移到 workbench_issue_ui.py，原页面方法保留委托接口。双语诊断测试 2 passed（issue_presenter_refactor.xml），两文件 Mypy 与 Ruff 通过；CurvePage 从 570 行降为 542 行，仍超 539 行门槛，其他超限未处理，不声明质量检查通过。

确认论文截图进程结束后，关闭本任务旧窗口并重启最新源码。实际重开 tube_gui_pipe2_generated/project.json，选择 Tube 操作，将出口改为 Not set 后 Apply：草稿保留，英文明确要求补齐四角色；滚动至底部，Generate、Preview Path、Export Result 均禁用。切换中文后仍保留未填写出口及中文提示，三按钮仍禁用。重新选择 body_002_edge_0014（R16）并应用，提示应用成功，生成恢复可用；当前没有重新生成，预览和导出仍禁用。

四张原始截图为 tube_missing_role_fixed_live_en.jpg、tube_missing_role_gates_live_en.jpg、tube_missing_role_gates_live_zh.jpg、tube_missing_role_recovered_live_zh.jpg；源码、截图和保存项目指纹见 tube_missing_role_live_manifest.json，恢复后只读状态见 tube_missing_role_recovered_live_zh.json。没有覆盖保存项目。本轮完成遗漏角色修复的真实拒绝与恢复复验，未完成任何完整语言/尺寸格。错误优先级的实际 Freeform 显示仍待验。

使用 five-axis-workbench-development、five-axis-slicer-validation、computer-use。复用上轮 Qt 列表接口和 Python 稳定排序依据；此次职责移动不改变领域判据。后续继续 V2-01 矩阵及质量问题，不把已保存项目重开替代空白首次使用。

### 错误首屏实测与不可达姿态提示

当前进程重开 freeform_gui_solid，保存项目的旧顶面角色在 v4 下产生 xyzac.orientation_unreachable at op01-point-00000001，中文状态栏仅显示内部代码，见 freeform_orientation_raw_live_zh.jpg。该拒绝来自现有 XYZAC 求解器对姿态及轴范围的检查，不将它解释为几何算法可以任意翻转喷嘴的理由。

实际编辑角色为底面 face_0005、对面 face_0006、根边 edge_0011，保留 0.2 mm 厚度作为失败案例，Apply 后 Generate。体积偏差与安全空移路线两条 Error 位于问题列表首屏，Warning 排在后面；切换英文仍保持这一顺序，导出禁用。见 freeform_error_priority_live_zh/en.jpg、freeform_error_priority_live_en.json。此项证明错误显示优先级，厚度/碰撞拒绝仍存在，不代表完整实体通过。修改未覆盖保存项目。

针对新发现的不可达姿态提示，按 [LinuxCNC 五轴运动学文档](https://linuxcnc.org/docs/stable/html/motion/5-axis-kinematics.html)中工具朝向、工件坐标与旋转轴关系，结合本项目 _solve_rotary 实际拒绝条件，补充中英文检查建议：承载面和生长方向、喷嘴轴、模型放置、A/C 轴范围。保留原始错误及点编号，未改变 IK 或导出判据。状态文字整理到已有 workbench_issue_ui.py，CurvePage 的长度门槛通过，其他 15 项超限保留。

双语新提示与诊断回归 4 passed（orientation_status_guidance.xml）；原 Curve 法向、断链和语言切换回归 3 passed（curve_status_refactor.xml），两文件 Mypy 与 Ruff 通过。当前桌面尚未加载新增姿态说明，真实提示复验待下一次重启；本轮截图证明此前排序修改。源码指纹见 orientation_guidance_source_sha256.json。使用 computer-use，沿用开发和验证 Skills，目标继续。

### Freeform 质量整理与相关回归

本轮在当前文件上作三项职责整理：Surface Solid 路径起点的 approach/travel 写入合并，仍仅在已有路径时产生 retract，再统一 prime；Freeform 数值控件回填从角色和材料回填中分离；实体产品的单路径保留或父操作合并集中到 _combine_operation_paths。保留原始顺序、坐标、法向、运动类型、挤出事件和身份条件，未调整任何碰撞或制造容差。

15 项相关回归通过，耗时 176.28 秒（freeform_quality_refactor.xml）：8 项 Surface Solid 算法、4 项 GUI 角色/草稿行为、父操作身份、危险工序转换拒绝、球面产品变换。三文件 Mypy 通过。三项 Freeform 超限已消除，剩余 12 项见 quality_freeform_refactor_capture_rule.log；Ruff、Migrated Ruff、安全及 61 文件格式检查通过，完整质量门禁仍未通过。

复查还发现另一任务刚归档的论文截图 capture.py 在初始化 ROOT/OUT、Qt 环境和源码路径后导入 Qt，触发三个 E402（quality_freeform_refactor.log）。依据 [Ruff E402 文档](https://docs.astral.sh/ruff/rules/module-import-not-at-top-of-file/)对环境和路径初始化的说明，给该具体归档文件添加带原因的 per-file E402 例外。保留归档脚本字节和证据哈希，未排除整个证据目录或其他规则。源码及配置指纹见 freeform_quality_refactor_sha256.json。

使用 five-axis-workbench-development 与 five-axis-slicer-validation，并复读制造验证参考以保留工艺门槛。该整理不构成新的桌面验收；不可达姿态新提示、完整语言/尺寸矩阵及后续工作包继续待验。

### Tube 设置诊断显示职责整理

将 Tube 设置树状态文字/颜色、坐标与 Setup 就绪提示、诊断列表和喷嘴缺项说明移到 workbench_issue_ui.py。TubeSetupPage.refresh 保留报告查询、按钮资格、覆盖层与状态信号更新。问题数据、对象定位、顺序、颜色、双语文字和读取异常分支保持原逻辑，不更改领域状态或导出资格。

Tube 模块 1726 行、页面类 1453 行，分别低于原门槛 1740/1454；refresh 复杂度也恢复合格。两文件 Mypy、Ruff、迁移规则、安全和 61 文件格式检查通过。整体 Context budget 仍有 9 项失败，详见 quality_tube_feedback_refactor.log，不能声明质量全绿。

串行运行 test_tube_ui.py、test_tube_resource_library_ui.py、test_tube_ui_help.py，62 passed、2 subtests passed，236.42 秒；见 tube_feedback_refactor.xml。覆盖喷嘴实际缺项和修复、坐标 Dirty 与问题跳转、语言与帮助、四角色拒绝/恢复以及项目界面流程。源码指纹和行数见 tube_feedback_refactor_sha256.json。未用 Qt 回归替代尚未完成的真实多尺寸矩阵。

使用 five-axis-workbench-development、five-axis-slicer-validation，沿用共享诊断呈现入口，避免在 Qt-free tube_ui_presenter 中加入控件依赖。下一步继续 Rotary、主窗口及碰撞检查剩余质量问题，并恢复真实界面验收。

### Rotary 显示与碰撞筛选职责整理

将 Rotary 问题列表和状态文字移动到已有 workbench_issue_ui.py，保留失败 payload、去重键、诊断编号、原始详情及双语恢复文字。页面 refresh 分离按钮资格更新，参数回填分离数值控件；失败 Apply 标志、生成互斥、导出就绪条件均沿用原逻辑。Rotary 四项长度/复杂度超限已消除，23 项集成和失败场景通过（rotary_feedback_refactor.xml，6.71 秒），两文件 Mypy 通过。

Tube 碰撞检查把每个运动采样点的障碍物筛选移到 _nozzle_side_obstacles，保留原来的 behind_tip 条件、所有障碍物角点判断和顺序。没有修改包络、间隙、采样、接触豁免或早停。33 项测试、3 项子测试通过（collision_filter_refactor.xml，4.06 秒），覆盖尖端平面接触/穿透、斜轴、沉积索引与 Indexed 路径检查；该文件 Mypy 通过。碰撞函数复杂度超限已消除。

完整质量脚本的 Ruff、迁移规则、安全及格式通过，仍有主窗口 ui.py 的四项长度/复杂度超限，见 quality_rotary_collision_refactor.log；中间日志 quality_rotary_feedback_refactor.log 保留碰撞整理前的五项结果。源码指纹见 rotary_collision_refactor_sha256.json。使用开发与验证 Skills，继续保留完整 GUI 矩阵、新姿态提示实测及后续交付门槛，未宣称当前质量全绿。

### 主窗口项目恢复整理与质量门禁通过

把项目来源路径解析和主 Viewer 的模型、选择、G-code 及播放按钮恢复移动到现有 model_commit 模块。来源解析仍在事务前，Viewer 发布仍在原 publication_transaction 内；控制器验证、绑定和后续命令服务切换保持原顺序。移除 ui.py 不再使用的 Mapping 导入。未改变保存格式、旧项目兼容或失败回滚边界。

9 项项目载入及发布相关测试通过，16.37 秒（project_publication_refactor.xml），涵盖无效项目、多个 Setup 绑定拒绝、嵌入源权威性及外部来源路径、G-code 替换/清空和界面发布失败恢复。41 项不相关用例未选择，未称全仓回归。

当前 scripts/check_quality.py 完整退出码 0：Ruff、迁移规则、安全、61 文件格式、Context budget 和 Mypy 全部通过；194 个源文件无类型错误。见 quality_project_publication_refactor.log，源码指纹见 project_publication_refactor_sha256.json。此前 16 项超限经过分次职责整理消除，没有提高门槛基线。使用开发与验证 Skills；该结果只证明当前静态门禁与上述相关测试，V2-01 真实矩阵、代表案例、新安装环境和最终提交 CI 尚未完成。

### 9 月 27 日不可达姿态说明的真实复验

确认旧测试进程正常结束后，用当前源码重新启动；实际重开原 freeform_gui_solid 项目，滚动至生成区并点击生成。保存的顶面角色仍被 xyzac.orientation_unreachable 拒绝。中文说明显示承载面、生长方向、喷嘴轴、模型放置和 A/C 范围检查建议，自动换行，原始点编号完整；切换英文后说明与原始诊断仍显示，Export 禁用。

见 freeform_orientation_fixed_live_zh/en.jpg 及 freeform_orientation_fixed_live_en.json。此项补齐此前新增说明的真实复验，同时实际经过本轮整理后的项目重开路径。未改动保存项目，未生成或导出合格产品。使用 computer-use；完整语言/尺寸格与其他交付工作仍待完成。

### 150 mm 可用平台配置

2026-09-27 按用户确认，把内置自有 AC 机型的圆形 build surface 直径更新为 150 mm，资源版本升为 2，身份保持不变。来源记录新增用户确认日期，论文 180 mm 物理台面保留为历史数据；未知厚度、轴行程和标定字段不作推定。界面说明读取所选配置的直径，避免旧项目快照显示成新尺寸；旧项目继续保留保存的资源。

使用 five-axis-workbench-development、five-axis-slicer-validation。配置相关测试 9 passed，证据 plate150_profile_final.xml；覆盖默认配置、文件交换、保存项目和显式空设置。双语机型指南已更新。圆形平台的网格和填充预览、当前桌面设置及真实显示尚待完成，不能将本次配置测试当作平台 GUI 验收或 V2 完成。

随后为 OpenGL 平台增加深色填充和按实际圆形边界截取的网格；标准平台采用 10 mm 间距，大尺寸自适应限制线条数量。坐标使用平台的原点及归一化轴，保留任意刚性姿态，不添加虚构厚度。参考 [Bambu Studio 官方 3DBed.cpp](https://github.com/bambulab/BambuStudio/blob/master/src/slic3r/GUI/3DBed.cpp) 的床面与网格分层呈现概念，独立实现解析圆裁剪，未复制代码或贴图；此处读取的是可变 master，不作为固定版本视觉验收。

24 项 OpenGL/平台测试及 2 项子测试通过（plate150_geometry_final.xml），独立核对倾斜平台网格端点半径 75 mm、圆面面积误差小于 0.2% 和非正方形尺寸。为保持原质量长度门槛，将原场景网格几何移至 opengl_scene；Context budget 通过，未提高基线。整体质量脚本在另一截图任务新增的 capture_a4.py、capture_clear_paths.py 的 E402/F401 停止，见 quality_plate150_geometry.log；本轮相关文件 Ruff 通过。VTK 一致呈现、各工作台入口和真实桌面视觉检查仍待完成。

VTK 随后复用相同的轮廓、网格与填充几何，以单个不可拾取 actor 呈现；单元颜色与相对多边形深度偏移参照 [VTK mapper 官方接口](https://vtk.org/doc/nightly/html/classvtkPolyDataMapper.html)。原生离屏烟测通过（plate150_vtk.xml），验证矩形平台真实范围、填充存在及原拾取/变换流程。

新增 source_build_surface 统一换算到 Source CS；Planar、Curve、Freeform、Rotary 刷新时使用各自已绑定 Setup，Tube 的模型视图也显示已装夹平台。空项目采用唯一机床装夹基准；已有模型但构建坐标或装夹不完整时不显示平台。Tube 机器视图保留草稿变换，不在机器变换缺失时混画平台。原测试中“切回模型视图隐藏平台”断言按新行为改为保留所选机型尺寸，失败记录 plate150_tube.xml 保留，复测 5 passed（plate150_tube_final.xml）。

设置相关测试 36 passed（plate150_entry.xml）；显示调用随后集中到共享入口，Rotary 问题定位原逻辑移动到已有 workbench_issue_ui，以遵守原长度门槛。改动后几何与 Rotary 17 passed（plate150_entry_final.xml），Ruff、相关 Mypy 和 Context budget 通过。上述入口及 VTK 的真实桌面显示仍未验收，尚需检查倾斜装夹和不同机型切换、空白 Fit 范围及重开项目；完整 V2 目标保持进行中。

### 平台桌面复验的空白显示诊断

2026-09-27 使用 computer-use 启动当前源码，原生窗口标题与可访问控件存在，截图客户区空白。检查发现新增填充调用遗漏 _draw_buffer 的必需 line_width，已补为 1.0，opengl_viewer.py 的 Mypy 通过。重启后截图仍空白，故该调用缺陷不能解释全部现象。实际通过可访问控件点击 Planar 后，HTTP 只读状态确认工作台切换，程序可正常关闭；不能将有响应视为视觉验收通过。

参照 [Qt Windows 图形加速说明](https://doc.qt.io/qt-6.8/windows-graphics.html)，仅给诊断进程设置 QT_OPENGL=software 作对照，截图仍空白。没有修改系统设置或认定显卡故障；当前需区分应用绘制与窗口捕获问题。保存 plate150_blank_software.png 和 plate150_blank_accessibility.json，均为失败诊断证据。本轮未完成平台桌面验收，继续保持 V2 目标进行中。

后续独立诊断进程使用原生 Windows Qt，窗口 grab 与 render_scene_image 均生成非空圆台图像，OpenGL context valid、program=3；见 plate150_qt_widget_diagnostic.png、plate150_gl_diagnostic.png。该程序化捕获只作诊断。随后正常启动应用，显式设置 QT_QPA_PLATFORM=windows，省略之前的 QT_SCALE_FACTOR=0.5 和软件渲染覆盖，computer-use 捕获恢复可见。因同时改变了启动平台与缩放条件，不能把原因单独归于缩放或认定捕获插件故障。

真实点击首页 Planar → 左侧 Machine → English，确认圆台显示、当前机型中文与英文均显示 150.0 mm；保存 plate150_planar_live_zh.png、plate150_machine_live_zh.png、plate150_machine_live_en.png 与同名英文状态 JSON。设备像素比 2，实际 client 1282×785，未计入指定尺寸矩阵。圆台网格在当前显示下呈锯齿/断续，英文 Setup 较窄视口还存在平台左右裁切，需继续改善 Fit 与显示质量；其余工作台、旧项目和倾斜装夹仍待实测。

针对空白平台在语言切换后视口变窄而裁切的问题，OpenGL resizeGL 在仅有平台、没有模型或路径时重新 Fit，复用现有视场角和包围球计算。新增 300×800 视口反例，逐个投影圆台轮廓顶点验证其处于视口内；12 项 Viewer 测试及 2 项子测试通过（plate150_fit_final.xml），之前受影响几何与 Viewer 合计 25 项及 2 项子测试通过（plate150_fit.xml）。Context budget 和相关 Ruff 通过。该修复尚需重新启动实际窗口验证；网格清晰度继续待检查。

正常关闭旧进程并重新启动最新源码后，实际点击英文公共设置与 Machine，圆台完整落在窄视口中（plate150_fit_live_en.png），补齐该裁切修复的桌面证据。继续通过首页实际进入 Curve、Freeform、Rotary、Tube，均显示圆台，Tube 同时显示配置直径 150.0 mm。对应 plate150_curve/freeform/rotary/tube_live_en.png，截图指纹 plate150_live_sha256.json。连同此前 Planar，五工作台空白平台已有可见证据；这不证明模型装夹后坐标、旧项目兼容、双语三尺寸矩阵或制造结果完成。网格断续感仍存在，继续保留清晰度待办。

独立检查非零坐标：构建原点 (100,200,300)、绕 Z 旋转 90°，装夹绕 X 旋转 90°并平移 (10,20,30)，手算 Source 中平台原点 (130,190,320)、X 轴 (0,1,0)、Y 轴 (0,0,-1)，与实现一致。新增反例发现 Dirty 装夹仍显示旧平台（plate150_coordinates_before.xml）。现复用 setup.validation_report，在构建坐标或装夹不为 Valid 时隐藏模型视图的平台，避免陈旧位置误导。

首次复测的测试装配遗漏清除 default_printer_setup 原有 Dirty 装夹标志，正常分支被正确拒绝，保留 plate150_coordinates_final.xml；修正测试准备后 13 项几何/配置回归通过（plate150_coordinates_verified.xml）。随后扩展到构建坐标与装夹各自 Dirty、Draft、Invalid 六种状态，4 项几何测试通过（plate150_coordinate_states.xml）。相关 Mypy、Ruff、Context budget 通过；使用开发与验证 Skills。该状态修复与非零装夹尚待桌面复验，旧项目尺寸保留的实际检查继续待办。

2026-09-27 真实重开 tube_gui_pipe2_generated/project.json，Machine 明确显示 Project snapshot · Diverged 与 180.0 mm，证明新默认值没有覆盖旧项目快照；见 plate150_old_snapshot_live_en.png/json。随后重启最新源码，手动选择 Built-in 150.0 mm 并 Apply，Placement 变为待重应用，模型视图旧圆台隐藏，错误提示可双击进入 Placement。重新 Apply 后圆台恢复，Operations 保持 Dirty；见 plate150_dirty_placement_live_en.png、plate150_placement_recovered_live_en.png。原项目文件未保存覆盖。

实际把 RX 改为 30°并 Apply：Machine View 中模型倾斜而平台保持机床装夹平面，切回 Model View 后模型恢复 Source 姿态、平台相对反向倾斜。截图 plate150_tilt_machine_live_en.png、plate150_tilt_source_live_en.png 与只读状态 plate150_tilt_live_state.json 归档。30°仅是显示坐标检查值，不作为该管件的制造参数；本轮没有以此姿态生成产品。

网格清晰度先按 [Qt 高 DPI 绘制说明](https://doc.qt.io/qt-6.8/highdpi.html) 修正 paintGL 的物理像素尺寸，原生线宽随设备像素比变化，导出图像仍使用请求的像素尺寸。单独修正后仍有可见锯齿，继续按 [QOpenGLWidget 多重采样接口](https://doc.qt.io/qt-6/qopenglwidget.html) 请求 4 samples；当前 Qt 5 同名接口实际运行成功。重启后的 plate150_msaa_live_en.png 显示网格连续性改善。该请求会依设备支持降级，不声称所有显卡得到 4 个样本，也不把静态图当作大模型性能通过。几何/Viewer 16 passed、2 subtests（plate150_msaa.xml）；相关 Ruff、3 文件 Mypy 与原 Context budget 通过，未提高基线。使用开发、验证及 computer-use Skills。

150 mm 默认配置、五工作台空白入口、旧快照保留、过期装夹隐藏/恢复和倾斜坐标已有针对性证据。全部中英文三尺寸矩阵、代表案例完整链、教程重制和发行门禁继续进行，PRODUCT-01-V2C 未关闭。

### Planar 英文 1600×900 首次使用

2026-09-27 正常启动当前源码，进程显式设置 QT_QPA_PLATFORM=windows、QT_SCALE_FACTOR=0.5，HTTP 只读状态确认 client 1600×900、DPR 1；因此先前空白现象不能单独归因于 0.5 缩放。实际从空白 Planar 导入 small_plate.step（8×8×1 mm，SHA256 a7d7037077db31d15c6784f25d20de3f964bb5b28480f707c7f1b6bd81ff5dc1），逐项设置 Part、Machine、Nozzle、Material、Model CS、Build CS 和 Placement。缺喷嘴接口/长度/RZ 包络时 Apply 拒绝，补齐离线示例参数后恢复。使用直径 150 mm 默认平台，完成 Zigzag 实体选择、创建、Apply、27 点生成及严格回读。截图以前缀 planar_en1600_ 保存于本证据目录。

实际复制公共设置为独立设置，修改喷嘴接口为 M6 demo local 后 Apply、返回，原结果转 Stale 且导出禁用；再次生成成功后恢复公共设置，同样转 Stale。随后点击 Part，发现已应用的 Placement 意外变为 Draft，阻止提交实体角色。失败截图为 planar_en1600_unexpected_placement_draft.png。撤销意外草稿后经原生保存对话框保存至 planar_en1600_current，保留实际 GUI 创建的项目和内嵌 STEP。

原因是公共设置入口先激活树上旧 Placement 节点，再选择用户请求的 Part，前一步创建了草稿。查阅 [Qt QTreeWidget 官方说明](https://doc.qt.io/qt-6.10/qtreewidget.html)，结合本项目 activate_coordinate_entry 调用定位；改为先选择请求节点再进入公共设置。新增覆盖 Planar、Curve、Freeform、Rotary 的回归，旧代码四例全部在意外草稿断言失败（common_part_route_before.xml），失败记录保留。相关 Ruff 和原 Context budget 通过；修复后设置回归结果另记。真实重启复验与实体角色错误恢复仍待完成，不将当前组合计为通过。

使用的 Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

修复后整文件回归为 27 passed、4 errors：四个 errors 均发生于 pytest 创建系统临时目录阶段，原因为 WinError 5，未进入产品断言。依据 [pytest 临时目录官方说明](https://docs.pytest.org/en/stable/how-to/tmp_path.html)，使用本项目中尚不存在的专用 --basetemp，仅重跑这四项保存重开测试，4 passed（common_part_route_reopen.xml）。因此本次 31 项均已执行通过，分属两份日志；未改变系统临时目录权限。源码、测试和 GUI 保存项目的 SHA256 见 common_part_route_fingerprints.json。修复后的真实点击仍待补。

本次继续重启修复后的正常程序，通过 Open Project 原生对话框重开 planar_en1600_current/project.json。进入 Placement 后 Cancel，返回首页进入 Planar，再点击 Part，Placement 保持 Valid，没有产生意外草稿（planar_en1600_route_fixed.png）。将唯一实体改为 Ignore 后 Confirm，实际拒绝并提示 Part must contain at least one solid；返回选择 Part 再 Confirm 成功。失败与恢复截图为 planar_en1600_empty_part_rejected.png、planar_en1600_part_recovered.png，右侧向下滚动后 Confirm 完整可见，见 planar_en1600_confirm_scroll.png。

只读状态 planar_en1600_route_fixed_state.json 证实语言 en、client 1600×900、DPR 1、草稿为空。HEAD 仍为 edacd49af9cb1766439526b171910d9f7538044d，实际运行包含未提交修改；ui.py SHA256 为 1CE9EEAC0EB3D572EF32E6470DA27E9891DE0CE260CAA285EF1A896C4E65DB2D，测试文件为 8C3A71C1BCD872DC30ACB7076A63502AC377F66FBE41C8FA11B343EC948A7BAA。矩阵附加的失效引用恢复尚待核对，未关闭整个组合；本次未修改产品源码，不重复运行已经通过的回归。使用 computer-use Skill，原开发与验证规则继续沿用。

失效引用补验使用独立的 planar_invalid_reference_fixture，复制实际 GUI 保存项目，只改变操作实体 ID 和签名体积，FIXTURE.txt 明确标记为错误输入；原项目保持不变。实际 Open Project → Planar → Generate 得到 planar.body_missing，导出禁用；Apply 当前 body_001 后 Generate 恢复 27/27 点严格回读。发现错误只显示代码，已在 planar_ui_diagnostics.py 补充中英文重新选实体/Apply 的说明。参照 Qt 官方 QComboBox 文档确认非编辑下拉框不能直接输入不存在的实体 ID，因此使用明确标注的项目副本触发错误；没有把程序化夹具构造计为首次使用操作。

29 项诊断回归通过（planar_missing_body_diagnostics.xml），Ruff 通过。重启后重新打开原失效夹具，实际生成拒绝，英文和中文说明均完整显示，导出禁用；再次 Apply/Generate 恢复，见 planar_missing_body_live_en.png、planar_missing_body_live_zh.png、planar_missing_body_recovered_final.png/JSON。引用 https://doc.qt.io/qt-6/qcombobox.html，仅用于控件行为核对，本项目仍运行 Qt 5。

Planar 英文 1600×900 的 V2-01 步骤现已逐项映射到 planar_en1600_click_record.md，标为本组合通过；其余 29 组合不随之通过，V2-02—V2-05 仍按原计划继续。使用开发、验证及 computer-use Skills。源码和截图指纹见 planar_en1600_final_fingerprints.json。

### Planar 中文 1600×900 首次使用

2026-09-27 从正常空白启动切换中文并进入 Planar，滚至底部，确认“请先打开 STEP 模型”及生成/导出禁用；截图 planar_zh1600_blank_gate.png。实际打开同一 small_plate.step 后进入公共 Part，未分配角色时 Confirm 正确拒绝，但弹窗仍是英文，记录 planar_zh1600_part_english_error.png。

参照 [Qt 5 国际化说明](https://doc.qt.io/archives/qt-5.15/internationalization.html)，沿用现有应用文字表，在 UI 错误发布处把该确定的领域异常映射到当前语言，补上选择角色及确认的下一步说明。领域异常和数据验证不变。已有角色语言及帮助测试 2 passed（part_required_language.xml），Ruff 和原 Context budget 通过；这些测试只覆盖原角色/语言行为，新弹窗另由真实桌面验证。重启后进入公共设置，对空 Part 点击确认，中文说明完整显示（part_required_fixed_live_zh.png）。本次复验启动未载入模型，不能代替后续实际实体恢复和生成流程。

使用的 Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。中文组合保持进行中；本轮新实例停留公共 Part，尚需重新载入小板并完成剩余设置和操作。源码与本轮截图指纹另存 part_required_language_fingerprints.json。

### 进度一致性复核与桌面读取中断

2026-09-27 继续验收时，computer-use 的 list_windows 两次均返回切片程序窗口 3083636，但 get_window/状态读取连续两次返回 foreground window did not report a process id。按插件恢复规则刷新选择后仅重试一次，未继续使用旧坐标，也未重启仍有窗口的应用。当前未确定是前台会话还是插件状态问题，不推断产品故障，不把本次中文操作计为已执行。

只读核对点击矩阵和既有证据后，修正主表中“尚无完整尺寸组合通过”及 Tube 遗漏角色、Freeform 两面拾取仍待桌面复验的过时描述。当前仅 Planar 英文 1600×900 完整通过，30 个组合的其余 29 个尚未完整通过；五个工作包均未关闭。文档更新未修改产品，不重跑产品测试。使用的 Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

### 中文公共设置恢复与完整应用

2026-09-27 查询进程确认原应用仍在；查阅 Microsoft GetForegroundWindow 文档（https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getforegroundwindow），其说明前台窗口在失去激活等情形可为空，不能据此确定本次原因。重置 node_repl 插件会话后重新绑定原窗口，再激活切片程序，正常截图恢复；没有重启应用或改变系统设置。

从工具栏打开 small_plate.step 实际进入 G-code 预览，随后公共 Part 仍为空；再从 Planar 内部打开 STEP 才载入制造模型。该入口差异已观察，首次使用说明和入口路由仍需核对，未声称已解决。载入后不分配角色直接确认，中文拒绝说明完整；选择 body_001 为零件并确认后有效。默认自有 AC 机型显示可用圆台 150.0 mm，实际点击应用。喷嘴直接应用时问题列表列出接口、总长及 R-Z 包络缺项；填写 M6 demo、12 mm 并勾选简化包络后应用，恢复有效。材料使用 Cura Generic PLA 1.75 mm，核对 200/60 摄氏度后应用。上述数值仅供离线小模型验收。

Model CS 与 Build CS 均使用原点 (0,0,0)、Z (0,0,1)、X (1,0,0)，逐项点击确认并应用；Placement 使用 Rotary table center、六个偏移均为零并应用。七项设置显示有效，界面显示就绪（有警告），操作尚未创建。本次截图为 planar_zh1600_loaded_part_reject.png、planar_zh1600_part_recovered.png、planar_zh1600_nozzle_missing.png、planar_zh1600_nozzle_recovered.png、planar_zh1600_common_setup_ready.png；只读状态同名前缀 JSON。中文组合继续待操作生成、独立设置及 Stale 检查。本次未修改源码，不重复既有测试；使用 computer-use Skill，并沿用开发及验证证据规则。

### 中文 Planar 生成、设置切换与引用恢复

2026-09-27 从上一轮有效公共设置继续，实际创建并应用 Zigzag 小模型操作，生成及严格回读均为 27 点。复制公共设置为 Planar 独立设置，喷嘴接口追加 local zh 并应用后返回，旧结果 stale、导出禁用；重新生成后改用公共设置，旧结果再次 stale。截图和只读状态分别为 planar_zh1600_generated、planar_zh1600_local_stale、planar_zh1600_common_stale。随后重新生成，通过原生对话框保存 planar_zh1600_current 项目。

打开原有明确标记的失效实体引用诊断副本，生成拒绝、中文恢复说明可见、导出禁用；点击应用当前 body_001 后重新生成，27/27 点回读通过，坐标、进给、挤出和顺序失配列表为空。最后重开本轮中文项目，设置和操作恢复，公共 Part 确认按钮经滚动完整显示；生成产品按当前持久化设计未恢复，不把该操作声称为结果缓存恢复。

逐项证据见 planar_zh1600_click_record.md，中文 1600×900 内部入口组合通过，矩阵累计两个组合。共享首页 STEP 路由差异仍未处理，其他组合及 V2-02—V2-05 不随之通过。使用 computer-use 和开发 Skill 阶段门槛，沿用验证 Skill 的证据规则；本轮未修改源码，不重跑产品回归。

### 首页 STEP 入口路由修复

2026-09-27 检查 ui.py 的 _open_model_from_shell，发现制造页面集合漏掉 home_page，首页工具栏因此进入 open_result_model_dialog，仅修改文件预览状态。现有 _commit_model 已负责发布模型到五工作台，保留原事务边界；只在路由集合补上首页。参照 Qt 官方 QStackedWidget currentWidget 说明（https://doc.qt.io/qt-6.8/qstackedwidget.html）核对当前页面判断；本项目仍为 Qt 5，并未升级框架。

在 test_tube_ui.py 新增工具栏实际 QAction 触发回归，覆盖首页、Planar 和文件预览页。旧代码首页子项失败，制造加载调用次数为零（home_step_route_before.xml）；修复后相关文件对话框与模型加载导航合计 3 passed、3 subtests（home_step_route_after.xml）。Ruff 和既有 Context budget 通过。运行 Qt 回归前关闭已保存的真实程序，测试完成后重新启动，避免 QSettings 并行影响。

实际中文空白首页点击工具栏打开 STEP，选择 small_plate.step，载入后点击公共制造设置；Part 表出现 body_001，证明无需再次导入制造模型。截图及只读状态为 home_step_route_fixed_live_zh.png/JSON，指纹另存。导入后使用既有 session 页面，未改其导航布局；文件预览页的独立入口由回归确认保持预览加载。此项关闭共享路由缺陷，不增加完整尺寸组合计数。使用的 Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

### Curve 英文独立设置修改与两次 Stale 补验

2026-09-27 使用 computer-use，在当前 1600×900、DPR 1、英文窗口实际打开 curve_gui_two_edges 项目，保留历史项目文件不覆盖。向下滚动后点击 Generate and validate，当前 Curve Buildup 可生成。复制公共 Setup 后进入独立 Nozzle，将长度由 18 mm 改为 19 mm；Apply 明确拒绝沿用原长度的 R-Z 包络，并说明清除后应用、再勾选生成的方法。按提示操作后 Nozzle 恢复 Valid。此处长度仅为离线验收输入，不是实机标定值。

返回工作台，结果 stale 且导出禁用；重新生成后结果 warning、17/17 点严格回读通过；再点击 Use common Setup 并确认，结果重新变为 stale、导出禁用。三个只读状态分别为 curve_en1600_local_edit_stale.json、curve_en1600_local_regenerated.json、curve_en1600_common_after_regenerate_stale.json，原始 JSON 完整保存。不能用 stale 产品里保留的旧 readback.passed 判定当前可导出，应同时核对产品状态及实际按钮。

本轮补上独立喷嘴编辑、具体错误恢复以及“有效结果→恢复公共→失效”的直接证据。历史机型快照的 180 mm 平台显示为 Project snapshot / Diverged，未静默改写为当前默认 150 mm。截图以 curve_en1600_ 为前缀保存在同一证据目录。本轮未修改源代码；公共设置逐节点覆盖仍待核对，Curve 组合保持进行中，完整矩阵仍为 2/30。使用 Skill：computer-use；沿用开发和验证 Skill 已读证据要求。

### Curve 公共 Part、机型及装夹补验

2026-09-27 computer-use 读取目标窗口时两次返回 foreground window did not report a process id。重置插件并枚举窗口后目标不在列表；原 exec 会话 15984 返回 exit 0，无 five_axis_slicer 命令行进程且 8765 端口不通，才重新启动。未将窗口暂时捕获到 Codex 的图片用于产品验收，也不把退出原因推断为崩溃。

新会话 18120 正常启动，通过原生 Open Project 再打开 curve_gui_two_edges。Curve 左侧 Part 进入公共编辑器，body_001 的 Part 角色保留，Placement 仍 Valid；右侧滚动后 Confirm 完整可见，实际点击成功。截图 curve_en1600_common_part_route.png。随后 Machine 下拉明确选择 Own AC FDM [Built-in]，摘要显示 150.0 mm；Apply 后 Placement Dirty，提示重新核对装夹，平台隐藏。进入 Placement，Rotary table center 和六项零偏移保留；Apply 后 Valid、Setup Ready with Warnings、平台恢复，截图和原始只读状态 curve_en1600_machine150_placement_recovered.png/json，失效截图 curve_en1600_machine150_placement_dirty.png。

机型切换只发生于当前内存验收项目，原历史项目文件未保存覆盖。后续需完成公共 Nozzle、Material、Model CS 和 Build CS 的当前点击覆盖，并保存当前 150 mm 副本；完整组合计数仍为 2/30。本轮无源码修改，无新增测试结论。使用 Skill：computer-use。

### Curve 公共资源、坐标及 150 mm 项目保存重开

2026-09-27 在同一真实英文 1600×900 窗口补齐公共 Nozzle、Material、Model CS、Build CS。喷嘴 0.4 mm、长度 18 mm、OFFLINE-TEST-INTERFACE 和已有近似包络实际 Apply；材料 Cura Generic PLA 1.75 mm、案例建议 200/60 °C、已核对复选框实际 Apply。以上均为离线案例值。两个坐标分别确认原点 (0,0,0)、Z=(0,0,1)、X=(1,0,0)，再 Apply，节点恢复 Valid。截图为 curve_en1600_common_nozzle.png、common_material.png、common_model_cs.png、common_build_cs.png（均带 curve_en1600_ 前缀）。

通过 Save Project 原生文件夹对话框保存 curve_en1600_current150，再通过 Open Project 实际重开 project.json。保存文件含 150.0 mm 平台及原 Curve Buildup，有向链 0012→0008，反向 0,1。重开时当前选中 Build CS，编辑器自动进入 Draft；点击 Cancel 后已保存坐标恢复 Valid，再从 Workbench 首页进入 Curve，边链、法向和操作均正确恢复。截图和完整只读状态为 curve_en1600_current150_reopened.png/json。原 curve_gui_two_edges 项目未覆盖。

本轮补齐公共七节点的分段点击证据及新配置保存重开。待将历次空白入口、STEP 打开、几何错误恢复、两次 Stale 与本轮设置证据逐项汇总核对，再关闭该组合；完整矩阵仍维持 2/30。无代码修改，不重复产品回归。使用 Skill：computer-use。

### Curve 英文 1600×900 组合证据核对关闭

2026-09-27 逐项读取真实状态、点击复盘、当前保存项目及截图清单，形成 curve_en1600_click_record.md。空白入口、直接 STEP、公共七节点、选边顺序、法向和断链恢复、独立设置及两次有效结果 Stale、滚动、150 mm 副本保存重开均有对应证据。明确早期局部 JSON 缺语言字段由实际点击记录及英文截图补充，不伪造缺失截图；重开不恢复生成缓存。仅关闭本组合 V2-01，矩阵累计 3/30，V2-01—V2-05 均仍未整体完成。采用 five-axis-workbench-development 阶段门槛及既有 computer-use 证据。本轮仅汇总文档，不重复运行测试。

### Rotary 英文 1600×900 补验及组合关闭

2026-09-27 实际打开 rotary_gui_cylinder 项目，退出保留坐标编辑页的 Draft 后进入 Rotary，逐段滚到生成区并生成。复制公共设置后返回 Stale，独立设置重新生成 Warning、严格回读通过、导出可用，再恢复公共设置后出现新的 Stale、导出禁用。原始状态和截图为 rotary_en1600_local_stale_current、rotary_en1600_local_regenerated、rotary_en1600_common_after_regenerate_stale。未覆盖历史保存项目。

核对既有空白入口、直接 STEP、公共七节点、选轴和端面拒绝/侧面恢复、编辑保留及失败门禁、保存重开证据，形成 rotary_en1600_click_record.md。仅本组合通过，矩阵累计 4/30。三个离线警告保留，不声称碰撞或实机资格；完整工作包仍未关闭。本轮无代码修改，使用 computer-use 和开发 Skill 阶段门槛，不重复测试。

### Tube 英文 1600×900 空白补验及组合关闭

2026-09-27 前一会话正常退出后启动空白英文窗口，首页进入 Tube，Part 缺项提示明确。创建 Indexed 后四角色均 Not set，Apply 拒绝并说明补齐四项；滚动可见 Generate、Preview、Export 全禁用。截图和状态为 tube_en1600_blank_current、tube_en1600_blank_apply_rejected、tube_en1600_blank_gates。当前空白进程未保存测试操作。

核对既有四角色拾取、公共七项设置、生成与导出、材料 Stale、端口/遗漏角色拒绝恢复及保存重开，形成 tube_en1600_click_record.md，仅关闭英文 1600×900 首次使用组合，累计 5/30。独立 Setup 对 Tube 不适用。材料名称重复确认的桌面复核及代表案例沉积/空移审查继续保留为后续事项。本轮无代码修改，使用 computer-use 和开发阶段门槛，不重复生成测试。

### Freeform 实体遗漏对侧面的诊断补充

2026-09-27 实际重开 freeform_gui_solid，编辑 Solid-fill selection JSON，仅删除 opposite_face_id，保留 body_001、承载面 0006 和根边 0012；Apply 正确拒绝，Generate/Export 禁用，但只显示 opposite_face_id is required。原始截图及完整只读状态为 freeform_en1600_missing_opposite_raw.png/json，历史项目未保存覆盖。

参照 Qt 用户可见文字翻译说明 https://doc.qt.io/qt-6.8/i18n-source-translation.html，在现有 workbench_issue_ui.operation_status_text 中给这个明确错误增加中英文说明：填写该实体与承载面相对的面 ID，再 Apply，保留原错误。未更改几何规则或制造资格。新增真实页面按钮测试覆盖双语失败草稿保留、生成/导出禁用及补回角色后恢复应用；与原朝向提示和失败恢复检查合计 5 passed，24 deselected，7.57 秒，JUnit freeform_missing_opposite.xml。定向 Ruff 和 Context budget 通过。

Qt 测试前正常关闭桌面会话并确认退出，未并行写 QSettings。重启后已在真实界面确认中英文恢复说明，截图 freeform_missing_opposite_live_en.png、freeform_missing_opposite_live_zh.png。英文界面补回 opposite_face_id=body_001_face_0005 并 Apply 后，错误消失、Status: draft、Generate 可用、Export 禁用；截图及只读状态为 freeform_missing_opposite_recovered_live_en.png/json。模式切换及有效结果恢复公共设置后的新一轮 Stale 继续待验，Freeform 组合未关闭，完整组合仍为 5/30。Skills：computer-use、five-axis-workbench-development、five-axis-slicer-validation。

### Freeform 模式切换和两次设置过期补验

2026-09-27 在英文 1600×900 窗口从已有 Surface Solid Fill 切到 Freeform Surface，导引边 0012、法向面 0006、反向标志 0 和指定法向 0,0,1 正确恢复，实体角色输入隐藏。实际生成后为 Warning、Export 可用；复制公共设置进入独立设置，返回后 Stale 且 Export 禁用。独立设置再次生成后 Warning、Export 可用；只读状态 freeform_local_regenerated_current.json 证明 9/9 点、1/1 事件严格回读通过。随后 Use common Setup 并确认，新的 Stale 出现、Export 禁用，证据 freeform_common_after_regenerate_stale.png/json。该旧项目保留 180 mm 机床快照，未改写为新默认值，也未覆盖历史项目。

再切回 Surface Solid Fill，导引字段隐藏，实体 JSON 中承载面 0006、对侧面 0005、根边 0012 保留。截图 freeform_mode_surface_restored_en.png、freeform_mode_solid_restored_en.png，后者有同名只读状态。本轮仅补齐模式编辑器切换和设置过期证据，不声明实体填充生成或代表案例验收完成；完整组合需与已有逐项证据汇总后判定，暂保持 5/30。使用 Skills：computer-use、five-axis-workbench-development、five-axis-slicer-validation；没有改代码，不重复 Qt 回归。
### Freeform 英文 1600×900 组合关闭

2026-09-27 按开发 Skill 阶段门槛逐项核对既有空白、直接 STEP、七节点设置、导引与实体拾取、错误恢复、模式切换、保存重开，以及最新实际生成后的两次 Stale，形成 freeform_en1600_click_record.md 和源码/证据指纹。仅本组合 V2-01 通过，累计 6/30。Surface Solid 制造拒绝、代表案例链、路径显示专项和最终发行仍未关闭。本轮只汇总证据，无代码修改，不重复测试。使用 five-axis-workbench-development、five-axis-slicer-validation。

### Freeform 中文公共设置续验

2026-09-27 从当前 Freeform 切换中文，实际进入公共 Part 并确认 body_001，进入 Machine 将当前会话的旧 180 mm 项目快照切换为内置 150 mm 配置并应用。Placement 转待更新，问题列表提示打开装夹定位、核对安装面及偏移；实际进入零偏移转台中心装夹并应用后恢复有效。截图和只读状态 freeform_zh1600_machine150_placement_recovered.png/json。历史项目未保存覆盖，中文其余设置节点、生成、角色和 Stale 继续待验，累计仍 6/30。沿用 computer-use、开发及验证 Skills 的真实点击与证据规则，本轮无代码修改。

2026-09-27 中文公共设置续验：实际打开喷嘴并应用 18 mm、OFFLINE-TEST-INTERFACE 和已启用 R-Z 包络；材料已核对状态应用正常。Model CS、Build CS 分别确认原点零、Z=(0,0,1)、X=(1,0,0) 并应用，七节点均恢复有效。经首页中文自由曲面入口返回，实体角色保留、150 mm 平台显示。截图 freeform_zh1600_nozzle/material/model_cs/build_cs.png，只读完整状态 freeform_zh1600_common_setup_complete.json。中文生成、几何选择和独立/公共 Stale 尚待补齐，6/30 不变。

2026-09-27 中文实际切到 Freeform Surface，滚动到生成区：公共设置 Generate 得到有警告且导出可用；导入公共设置为独立副本，返回后待更新且导出禁用；独立设置重新生成，再改用公共设置并确认，新的待更新和导出禁用生效。状态文件 freeform_zh1600_common_generated.json、freeform_zh1600_local_regenerated.json、freeform_zh1600_common_stale.json；两次过期截图 freeform_zh1600_local_stale.png、freeform_zh1600_common_stale.png。确认框正文中文，但标题 Manufacturing Setup、Yes/No 仍英文，登记为本地化待处理，不能据此关闭中文组合。没有代码修改。

### 设置作用域确认框本地化修复

2026-09-27 针对中文实测确认框残留英文，依据 https://doc.qt.io/qt-6/qmessagebox.html 的标准按钮与 button() 接口，在 workbench_setup_panel 增加 confirm_setup_change，显式设置中英文标题及是/否文字，保留 Yes/No 返回身份，默认及 Escape 为 No。复制覆盖、恢复公共、发布公共三个同类入口统一使用。新增双语及两种回答测试，既有设置作用域测试改为模拟该确认边界。桌面正常关闭并确认原进程退出后串行运行完整 test_workbench_setup_scope.py，JUnit setup_confirmation_language.xml；本条记录时会话 8397 仍运行，未宣布通过。Ruff、格式整理和 Context budget 通过。实际新弹窗待重启复验，完整矩阵保持 6/30。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

确认框修复回归结束：35 passed，193.19 s，退出码 0，JUnit setup_confirmation_language.xml。启动最新源码后，中文空白 Freeform 导入独立设置，实际打开恢复公共确认框：标题制造设置、按钮是/否，默认否。点否后仍为独立设置，再打开点是后恢复公共设置；截图 setup_confirmation_fixed_live_zh.png、恢复只读状态 setup_confirmation_fixed_restored_zh.json。该局部显示与回答行为复验通过，中文整个组合仍未完成。

2026-09-27 最新源码中文空白 Freeform 新建 Surface，滚动可见缺少 Part、喷嘴、材料、两个坐标及装夹的明确下一步提示，生成/导出禁用，截图 freeform_zh1600_blank_gates.png。真实打开 small_plate.step，视口选中近侧顶边并采用 Viewer 已选边；完整只读状态 freeform_zh1600_direct_step_edge.json。当前为空白设置的新模型会话，法向面、应用恢复及完整几何流程仍待继续，不能计为中文整格通过。

2026-09-27 中文导引几何补验：顶部拾取类型切到面，实际点击平板顶面，边保持蓝色、顶面高亮；滚动至采用 Viewer 已选边并点击，再应用。只读状态确认 freeform-operation-1 的 faces=body_001_face_0006、guides.edge=body_001_edge_0012，last_error 为空；截图和状态 freeform_zh1600_geometry_applied.png/json。此新会话仍缺 Part/喷嘴/材料/坐标；应用后生成按钮外观发生变化，缺设置时实际生成行为待核对，暂不判断为完整门禁通过。完整组合保持 6/30。

### 中文缺制造设置生成拒绝补验

2026-09-27 实际点击 Generate，正确拒绝为 Freeform Generate requires a valid applied Setup，导出保持禁用，未形成有效产品。现场 freeform_zh1600_missing_setup_generate_raw.png/json。按 Qt 用户可见文字翻译说明 https://doc.qt.io/qt-6.8/i18n-source-translation.html，在既有状态呈现器补上双语下一步提示，保留原错误；不改生成判据。精确错误映射统一为表以保持复杂度门槛。4 项直接文字检查、Ruff 通过，新增文案仍待重启实际复验。中文整格保持未完成，6/30 不变。

2026-09-27 缺设置提示已完成真实桌面复验：用保存项目对话框保存 freeform_zh1600_missing_setup_project，正常退出原进程（exit 0），启动最新源码并用打开项目对话框重开。导引边 body_001_edge_0012 与法向面 body_001_face_0006 保留。滚动后实际点击生成，显示中文补齐零件、喷嘴、材料、坐标和装夹的恢复步骤，并保留原错误；导出禁用。截图 freeform_zh1600_missing_setup_fixed_live.png 与只读状态同名 JSON 已归档。该文案复验通过，有效设置恢复及中文整格仍待完成，矩阵维持 6/30。沿用 computer-use Skill。

2026-09-27 在同一缺设置项目内逐项恢复：未分配实体时确认被中文提示拒绝，指定 body_001 为零件并确认后有效；设置 18 mm 离线复验喷嘴接口并启用 R-Z 包络，核对 PLA 1.75 mm、200/60 ℃并应用，分别确认模型/构建坐标的原点与 Z/X，应用零偏移装夹。全部设置有效后返回 Freeform 实际生成成功，状态有警告、导出可用，9 点且 machine_executable=false。证据 freeform_zh1600_setup_recovered_live.png、freeform_zh1600_missing_setup_recovery_generated.png/json。真实保存对话框另存 freeform_zh1600_recovered_project，保留此前缺设置项目用于复现。缺设置拒绝到恢复生成已闭环；新有效项目重开和中文模式覆盖待补齐，矩阵仍 6/30。沿用 computer-use，无代码修改。

2026-09-27 实际打开 freeform_zh1600_recovered_project/project.json：设置和导引几何保留，重开结果为草稿、导出禁用；点击生成后再次恢复有警告及导出可用。证据 freeform_zh1600_reopened_generated.png/json。随后选择 Surface Solid 并实际新建操作，实体角色编辑器显示；通过现有操作下拉切回 Freeform Surface，导引边 body_001_edge_0012、反向 0、法向面 body_001_face_0006 与指定法向 0,0,1 均保留。证据 freeform_zh1600_mode_surface_restored.png/json。新建实体的角色恢复和切回实体仍待继续，中文整格保持进行中、总数 6/30。使用 computer-use，无代码修改。

2026-09-27 中文实际切回 Surface Solid Fill，编辑实体角色 JSON。初次输入缺少 bodies 列表包装时被拒绝，原始英文 bodies must be a non-empty array of objects 仍需中文恢复说明；核对现有测试中的格式后补齐列表。遗漏 opposite_face_id 时实际应用拒绝，中文提示补对侧面，生成和导出禁用；添加 body_001_face_0005 并应用后错误消失、生成恢复可用。其余角色为 body_001、surface_face_id=body_001_face_0006、root_edge_id=body_001_edge_0012。证据 freeform_zh1600_solid_missing_opposite.png、freeform_zh1600_solid_role_recovered.png/json。角色恢复已通过；格式错误中文提示及完整证据核对仍待处理，6/30 不变。使用 computer-use，无代码修改。

2026-09-27 对现场发现的 bodies must be a non-empty array of objects，在 workbench_issue_ui 的精确诊断映射补齐双语恢复说明：填写 bodies 角色对象列表，或显示模型后采用 Viewer 已选几何建立候选，再应用。沿用前述 Qt 用户可见文字翻译依据，不改变 JSON 校验或生成门禁。3 项直接呈现检查、Ruff、格式检查、Context budget 通过；当前桌面进程仍运行旧文案，真实新文案尚待重启复验，不据代码检查关闭中文组合。Skills：five-axis-workbench-development、five-axis-slicer-validation。

2026-09-27 保存当前双模式角色项目到 freeform_zh1600_roles_project，草稿保存确认选择 Apply 后成功写盘。正常退出原进程（exit 0）并重启最新源码，真实打开该项目；四项实体角色保留，截图 freeform_zh1600_roles_reopened.png。将角色 JSON 改为空对象后实际应用，新增中文格式恢复说明可见，生成/导出禁用；截图和状态 freeform_zh1600_bodies_format_fixed.png/json。新增格式提示桌面复验通过。另在保存过程中发现草稿确认框正文和 Apply/Discard/Cancel 混用英文，已登记为中文组合剩余问题，尚未修复；完整矩阵仍 6/30。使用 computer-use。

2026-09-27 草稿保存确认本地化：公共保存与独立设置离开两个入口复用 workbench_setup_panel.draft_setup_prompt，中文标题、正文及应用/丢弃/取消完整显示，保留标准按钮结果码，默认与 Escape 均为取消。沿用前述 Qt QMessageBox 官方接口依据。Ruff、格式、Context budget 通过；关闭桌面原进程 exit 0 后，串行核对两语言×两用途四组真实 QMessageBox 的文字、默认及 Escape 按钮全部通过。主窗口对结果码的判断未变。实际桌面新弹窗仍待复验，完整矩阵保持 6/30。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

2026-09-27 草稿确认修复后串行执行完整设置作用域回归：31 passed、4 errors，4 项均在 tmp_path 准备阶段因系统临时目录 WinError 5 拒绝访问，未进入产品逻辑；JUnit draft_dialog_scope_regression.xml 保留原始失败。改用项目内独立 basetemp，仅重跑四项保存重开测试，4 passed、31 deselected、9.10 s，exit 0，JUnit draft_dialog_scope_retry.xml。合计 35 项相关测试获得通过证据，不能把第一次报告写成全绿，也不代表三种按钮真实点击已验收。桌面新确认框仍待实际复验，6/30 不变。沿用 five-axis-slicer-validation 的串行 Qt 与权限诊断规则。

2026-09-27 最新源码桌面启动并真实打开 freeform_zh1600_roles_project；进入 Model CS 创建编辑草稿，Ctrl+S 选择独立 draft_cancel_probe 目录。新保存确认框标题制造设置、正文及应用/丢弃/取消全中文，默认取消，截图 draft_save_confirm_fixed_live_zh.png。实际点击取消，返回草稿编辑，目标 project.json 不存在（Test-Path=False），取消保存行为通过。其他按钮与独立编辑入口仍须按所需范围核对，未据此关闭中文整格。使用 computer-use，完整矩阵仍 6/30。

### Freeform 中文 1600×900 组合关闭

2026-09-27 按 V2-01 判据核对空白入口、直接 STEP 与导引拾取、公共七节点、独立/公共两次 Stale、缺设置与角色错误恢复、模式切换、按钮滚动和项目重开证据，21 个引用文件均存在，形成 freeform_zh1600_click_record.md 与当前源码/证据指纹。仅本组合通过，累计 7/30，余 23 组。完整实体生成、代表案例及余下四工作包未关闭。保存确认三种行为不扩展为本组合新的全量验收门；已记录的中文显示和取消实测、配置检查、相关回归支撑本次文字修复。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

### Curve 中文 1600×900 开始补验

2026-09-27 取消上一项目坐标草稿，正常关闭进程 exit 0，空白启动进入中文曲线工作台。实际滚动到底部，按钮可达，Part、喷嘴、材料、坐标缺失均有中文下一步说明，生成及导出禁用；实际新建 Buildup 操作后门禁保持。截图 curve_zh1600_blank_gates.png（新建前）、完整状态 curve_zh1600_blank_gates.json（新建后）。本组合进行中，几何、设置、生成、错误恢复和 Stale 继续补齐；总数仍 7/30。使用 computer-use，复用开发/验证 Skills 的证据规则，无代码修改。

2026-09-27 Curve 中文直接 STEP 与有向拾取：从工具栏打开 small_plate.step，实际点击近侧顶边再点击左侧相邻顶边，采用 Viewer 已选边后回填 body_001_edge_0012→body_001_edge_0008，顺序未按编号重排，默认反向 0,0。截图与完整状态 curve_zh1600_direct_step_edges.png/json。当前公共设置仍缺项，法向来源为明确邻面且未指定面；应用、错误恢复及完整生成尚未核对，不将选边成功视为组合通过。总数 7/30，使用 computer-use。

2026-09-27 Curve 中文当前边链实际 Apply 成功进入草稿，生成按钮可用但公共设置缺项仍显示；尚未执行生成，不宣称断链或法向检查通过。随后从 Curve 左侧 Part 进入公共零件，指定 body_001 为零件并确认有效；进入 Machine 显示内置 150.0 mm 有效平台直径，实际应用。证据 curve_zh1600_common_part.png、curve_zh1600_common_machine150.png/json。喷嘴、材料、坐标及装夹继续待补齐，中文整格进行中，总数仍 7/30。使用 computer-use，无代码修改。

2026-09-27 Curve 中文公共喷嘴与材料已实际核对并应用：喷嘴接口 OFFLINE-TEST-INTERFACE、长度 18 mm、R-Z 包络启用；PLA 1.75 mm，喷嘴/热床 200/60 ℃，勾选材料参数已核对后应用。两节点均有效，问题列表继续提示模型坐标未设置。截图 curve_zh1600_common_nozzle.png、curve_zh1600_common_material.png。参数仅为离线案例，坐标及装夹尚待补齐；总数 7/30，使用 computer-use，无代码修改。
2026-09-27 Curve 中文补齐 Model CS、Build CS 与 Placement，公共七节点全部有效；证据 curve_zh1600_common_model_cs.png、curve_zh1600_common_build_cs.png、curve_zh1600_common_placement.png 与 curve_zh1600_setup_complete.json。返回 Curve 实际生成，反向标志 0,0 触发中文断链说明，原始诊断 gap 8 mm exceeds 0.01 mm；截图 curve_zh1600_chain_gap.png。按提示将第二条边反向改为 0,1，实际应用并生成恢复至有警告状态，导出按钮可用，显示 150 mm 圆形平台；证据 curve_zh1600_chain_recovered.png/json。当前界面邻面字段已为 body_001_face_0006，以本次实际截图/状态为准，不沿用前文未指定面描述。剩余独立/公共 Stale、保存重开尚未关闭，本组合继续进行中，总数仍 7/30。使用 computer-use，沿用开发/验证 Skills；无代码修改。
2026-09-27 Curve 中文实际复制公共设置为独立设置，返回后状态待更新且导出禁用（curve_zh1600_local_stale.png）；重新生成恢复有警告并可导出（curve_zh1600_local_regenerated.png）。再点击改用公共设置，在中文是/否确认框选择是，旧结果再次待更新并禁用导出（curve_zh1600_common_stale.png/json）。随后实际保存 curve_zh1600_current150/project.json；保存时状态仍待更新，不能声称已重新生成。原生文件夹对话框拒绝正斜杠路径，改为 Windows 反斜杠后保存成功。重开与再生成留待继续，总数仍 7/30。使用 computer-use，无代码修改。

### Curve 中文 1600×900 组合关闭

2026-09-27 实际重开 current150/project.json，草稿及禁用导出符合预期；点击生成恢复 Warning、17 点路径及回读通过，machine_executable=false。证据 reopened_draft、reopened_generated PNG/JSON。汇总公共七节点、选边、断链恢复、两次 Stale、滚动和保存重开，23个证据文件存在，源码和证据指纹归档。仅本组合通过，累计8/30，余22组。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。无源码修改。
2026-09-27 Rotary 中文补验：实际打开 rotary_gui_cylinder/project.json，旧机床快照180 mm且显示分叉，重开进入Placement草稿。选择当前内置150 mm后Apply被E_DRAFT_ACTIVE阻止，中文界面弹出英文 unapplied Setup drafts are active，证据 rotary_zh1600_unapplied_draft_error.png；此前 rotary_zh1600_machine150.png 是失败瞬间，不能当应用成功证据。实际返回Placement取消草稿，再进入Machine应用成功，证据 rotary_zh1600_machine150_applied.png。错误源定位command_kernel.py:338，后续应修复UI恢复说明并复验；尚未修改代码。本组合继续进行中，累计8/30。使用computer-use，沿用开发/验证Skills。
2026-09-27 草稿阻止提示修复：在 workbench_issue_ui.command_error_text 中为确切 E_DRAFT_ACTIVE 文本增加中英文下一步说明，ui.show_error 统一使用，保留原始诊断且未知错误原样返回，不修改命令内核门禁。依据 Qt QMessageBox 官方文档 https://doc.qt.io/qt-6/qmessagebox.html 的消息说明能力；采用现有静态提示入口，避免扩大弹窗行为改动。4 项纯呈现断言通过（双语、原诊断保留、未知错误），Ruff check、format check、context budget 通过；未创建 QApplication，不与运行桌面并发 Qt 测试。现有桌面仍运行旧代码，新提示需重启后实际复验，不能称中文组合通过。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。累计8/30。
2026-09-27 新提示真实复验：正常关闭旧进程exit0，启动最新源码，重开原圆柱项目出现YAML/项目差异，实际选择使用项目。进入Placement创建草稿，再Machine Apply，出现中文恢复说明并保留原始诊断，截图rotary_zh1600_draft_guidance_fixed.png。按钮仍为Qt原生OK，本次修复只覆盖错误内容。确认中文恢复说明已实际显示，整组合仍待后续设置和生成；累计8/30。使用computer-use。
2026-09-27 Rotary 中文按新提示取消装夹草稿，切换当前内置150 mm机床并Apply，装夹转待更新；重新进入零偏移Placement并Apply后有效。随后确认body_001零件，核对并应用18 mm测试喷嘴及R-Z包络、PLA1.75 mm和200/60℃案例材料。证据rotary_zh1600_placement150_recovered.png、part_confirmed.png、nozzle_applied.png、material_applied.png（后3者同rotary_zh1600_前缀）。两坐标中文实际确认及后续生成尚待补齐，8/30不变。使用computer-use，无新代码修改。
2026-09-27 Rotary 中文 Model CS、Build CS 原点零/Z001/X100 均逐项确认并应用，截图rotary_zh1600_model_cs.png、rotary_zh1600_build_cs.png。返回回转工作台，轴边0002及侧面0001保留，逐段滚动到底部，实际生成恢复WARNING并启用导出；证据rotary_zh1600_generated150.png/json。警告仍包括参考机床、基底及机床碰撞几何不可用，不代表碰撞或实机资格。后续独立/公共两次Stale及150 mm副本保存重开尚待补齐，8/30不变。使用computer-use，无新代码修改。
2026-09-27 Rotary 中文实际复制公共设置、返回工作台，旧有效结果Stale且导出禁用；独立设置重新生成Warning，再改用公共设置并在中文确认框选择是，新结果再次Stale且导出禁用。截图rotary_zh1600_local_stale.png、local_regenerated.png、common_stale.png（同前缀），完整状态rotary_zh1600_common_stale.json。实际保存rotary_zh1600_current150副本，重开待补；8/30不变。使用computer-use，无代码修改。
2026-09-27 Rotary 中文实际从工具栏重开rotary_zh1600_current150/project.json，保持Stale且导出禁用；实际生成恢复Warning、导出可用、完整只读状态中readback.passed=true，machine_executable=false。证据rotary_zh1600_reopened_stale.png、rotary_zh1600_reopened_generated.png/json。滚回顶部核对轴边0002及侧面0001保留。关闭前还需补齐中文无效表面恢复操作，未以早期英文恢复替代；累计8/30。使用computer-use。
2026-09-27 Rotary 中文表面恢复补验：将表面0001改为已知端平面0002，Apply拒绝，中文提示选择同轴圆柱/圆锥侧面，生成和导出禁用；滚回顶部，失败输入0002仍保留。改回0001并Apply，随后实际点击生成，恢复Warning和可导出。证据rotary_zh1600_invalid_surface.png、rotary_zh1600_surface_recovered.png/json。该缺口已补齐，下一步汇总整组合逐项证据与指纹后更新矩阵；暂仍8/30。使用computer-use，无源码修改。

### Rotary 中文 1600×900 组合关闭

2026-09-27 逐项核对空白入口、几何拒绝恢复、公共七节点、独立与公共两次Stale、150 mm副本保存重开和再生成，形成rotary_zh1600_click_record.md，引用文件及源码/证据指纹已核对。仅本组合通过，累计9/30，余21组。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。整体V2-01—V2-05尚未关闭。
2026-09-27 Tube 中文1600×900开始：正常关闭回转会话exit0，空白启动从首页进入管状工作台，零件缺失提示给出下一步。实际创建Indexed操作、滚动树并选中操作，四角色未填写；Apply显示中文补齐四角色提示。右侧滚动后生成、预览、导出均禁用，未误报成功。证据tube_zh1600_blank.png、tube_zh1600_blank_rejected.png、tube_zh1600_blank_gates.png/json。后续STEP四角色、公共设置及生成待补；累计9/30。使用computer-use，沿用开发/验证Skills。
2026-09-27 Tube 中文实际从原生对话框打开example/pipe2/弯管新.stp，拾取body_002管体；原缩放入口未命中，放大后拾取入口外圆0003。出口第一次为内圆0012，实际重新拾取外圆0014，再拾取body_001基体，Apply接受四角色。证据tube_zh1600_roles_applied.png/json。尚未补齐公共设置或生成，不能称内圆生成拒绝已本轮实测。累计9/30，使用computer-use，无源码修改。

2026-09-27 Tube 中文公共七节点完成真实操作：两个实体确认为Part，内置机床150 mm应用；喷嘴先缺安装信息，按提示补齐OFFLINE-TEST-INTERFACE、18 mm与R-Z包络后有效；PLA案例200/60℃勾选已核对后有效。Model CS、Build CS原点零/Z001/X100逐项确认，Placement转台中心零偏移应用，setup_ready=true、has_drafts=false。证据tube_zh1600_part_confirmed、machine150_applied、nozzle_completed、material_applied、model_cs、build_cs、placement.png；nozzle_applied.png保留的是补齐前缺项状态，不当作通过。已实际点击生成，当前仍在生成，不能计为成功。使用five-axis-workbench-development、five-axis-slicer-validation、computer-use；累计9/30不变，无源码修改。

2026-09-27 同一Tube中文生成已完成Warning，ready_for_export=true，严格回读43775/43775且passed=true；警告为xyzac.rotary_singularity与MACHINE_REFERENCE_ONLY。证据tube_zh1600_generated150.png/json。随后真实取消材料已核对并Apply，操作转待更新；返回Tube滚到底部，显示已有结果过期且生成/预览/导出全部禁用，证据tube_zh1600_material_stale.png。尚待恢复材料、保存重开及中文角色错误恢复，整格未关闭，累计9/30。

### Tube 中文 1600×900 组合关闭

2026-09-27 材料恢复有效后，实际遗漏出口Apply拒绝；误选内圆0012并生成被拒，中文说明改选外圆。恢复0014并Apply，GUI保存tube_zh1600_current150/project.json再重开，七项设置与四角色保留、旧缓存不恢复、预览导出禁用；实际重新生成Warning、43775/43775严格回读通过。证据missing_outlet、inner_outlet_rejected、reopened_draft、reopened_generated PNG及生成摘要（同tube_zh1600_前缀）。逐项点击记录与源码/证据指纹已归档，引用文件存在。仅本组合通过，累计10/30，余20组；V2-01—V2-05尚未整体关闭。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。本轮无源码修改。

### Planar 中文 1366×768 开始复核

2026-09-27 正常关闭Tube会话exit0后空白启动，用computer-use拖动窗口边框；只读状态确认client_size=[1366,768]、DPR1。首页进入Planar，右侧两段滚动可访问底部按钮和完整缺项说明；原生对话框载入small_plate.step并新建操作。公共Part、150 mm机床、18 mm离线测试喷嘴与包络、PLA案例材料、Model/Build逐项坐标、转台中心装夹均真实应用有效，设置与截图归planar_zh1366_*。窄窗坐标X与应用按钮需滚动，可达。当前几何应用、生成、独立/公共Stale和保存重开尚待补齐，本组合进行中，累计10/30不变。

坐标临时反馈发现中文界面残留X confirmed/Z confirmed，证据planar_zh1366_coordinate_english_status.png；定位tube_ui._confirm_coordinate_component硬编码，改为现有TUBE_TEXT双语键，原点/Z/X共六条文本。依据Qt QLabel文本接口官方文档 https://doc.qt.io/qt-6/qlabel.html#text-prop ，保留现有setText流程与领域确认行为。六项纯文本断言、两文件Ruff检查与格式检查通过，无QApplication并发；当前运行进程仍旧代码，重启后的真实显示复验待办。使用Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

### Planar 中文 1366×768 组合关闭

2026-09-27 补齐 Region 仅预览与 Zigzag 正常生成、独立/公共两次 Stale、GUI 保存 current150 后退出重启再打开。客户区用系统大小菜单调整并只读确认 1366×768、DPR 1；重开后导出禁用，实际重新生成 Warning、27/27 严格回读通过。诊断副本失效实体拒绝后重新选择 body_001、应用及生成恢复，另验未分配零件角色的中文拒绝及恢复。最新源码原点、Z、X 确认文字均实际显示中文，取消草稿恢复有效设置。证据和边界见 [点击记录](evidence/2026-09-26_v2_final_delivery/planar_zh1366_click_record.md) 与指纹清单。仅本组合关闭，累计 11/30，余 19 组；完整 V2-01—V2-05 未关闭。

本轮可复用经验：边角拖动未生效时，Windows 系统大小菜单配合方向键和 Ctrl 微调可以调整精确尺寸，仍须读取实际客户区复核；坐标区滚动应避开下拉框，以免轮动改变模式。诊断项目的恢复不写回原始失效样例。使用 Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use；本轮为真实复验和证据归档，无新增源码修改。

### Curve 中文 1366×768 组合关闭

2026-09-27 正常退出前一会话后空白启动，实际调整并核对客户区 1366×768、DPR 1。首页进入 Curve，新建 Buildup 并检查缺设置门禁；直接打开小平板，Viewer 依次拾取 0008、0012，公共七节点逐项确认。返回后重新采用已选边并应用，邻面 0006；0,0 方向触发 8 mm 断链拒绝，维持 0.01 mm 容差、改 0,1 后生成恢复。独立副本与恢复公共两次 Stale 均禁用导出，实际再生成恢复。GUI 保存 current150 并重开，products 为空、导出禁用；重新生成 Warning、17/17 严格回读通过，边顺序与方向保留。证据见[点击记录](evidence/2026-09-26_v2_final_delivery/curve_zh1366_click_record.md)及指纹清单。累计 12/30，余 18 组；V2-01—V2-05 尚未整体关闭。

本轮复用系统菜单精确调窗和面板边缘滚动方法。先拾取后进入公共设置时，尚未应用的文本不作为已保存操作；返回后重新采用仍保留的 Viewer 选择并明确应用。没有修改算法或放宽容差，错误恢复由方向修正完成。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。无源码修改，不启动重复回归；完整路径可辨性和六件套代表案例另按后续工作包验收。

### Rotary 中文 1366×768 组合关闭

2026-09-27 正常退出前一会话后空白启动，客户区实际调整并确认 1366×768、DPR 1。空白新建说明先打开 STEP；载入 R20/H20 圆柱，公共七节点逐项确认有效。轴边初次点击未命中，先由输入框绑定 0002；Viewer 端面 0002 应用被拒，中文说明完整，生成/导出禁用；改选侧面 0001 并采用、应用，生成恢复 Warning。独立/公共两次 Stale 均禁用导出，重新生成恢复。实际保存 current150 再重开，Stale 禁止导出，重新生成 75/75 严格回读通过。随后 Viewer 放大两次并实际拾取轴向直边 0002，蓝色高亮、回填与只读选择状态一致，采用、应用后再次生成并回读通过。

证据见[点击记录](evidence/2026-09-26_v2_final_delivery/rotary_zh1366_click_record.md)和指纹清单；累计 13/30，余 17 组。初次未命中没有伪记为成功，放大后补齐实际拾取，无须修改容差或源码。公共设置中的角色/坐标按钮与 Rotary 底部动作通过滚动访问。参考机型及缺失碰撞几何警告保留；高点数预览与代表案例六件套继续按后续包检查。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。无源码修改，不重复产品回归。


### Tube 中文 1366×768 检查进展

2026-09-27 实际完成公共七节点、150 mm 圆台设置及四角色下拉选择；缺出口门禁、外圆正常生成 43775/43775 严格回读、材料核对取消后的 Stale 均通过。误选出口内圆 0012 时拒绝，中文提示改选外圆；恢复 0014 后实际保存并重开 current150 项目，旧结果不恢复、预览导出禁用。重开后重新生成已启动，尚未据此关闭组合，累计仍 13/30。具体截图和设置见 [点击记录](evidence/2026-09-26_v2_final_delivery/tube_zh1366_click_record.md)。窄窗底部错误说明需继续滚动才能完全显示，按钮均可滚到；保留原有诊断与离线限制。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。无源码修改。


### Tube 中文 1366×768 组合关闭

2026-09-27 重开后的实际生成完成 Warning，预览和导出恢复可用；43775/43775 严格回读通过，坐标、进给、挤出、顺序不一致均为空。最新截图与只读摘要归 tube_zh1366_reopened_generated；保存项目、逐项记录、源码/输入/证据指纹均归同目录。本组合关闭，累计 14/30，余 16 组；完整五个工作包仍未关闭。未改源码、参数容差或机床资格。Skills 沿用本节进展记录。下一组合为 Freeform 中文 1366×768。


### Freeform 中文 1366×768 检查进展

2026-09-27 正常关闭 Tube 后空白启动，系统菜单精确调整并只读确认客户区1366×768、DPR1。空白 Surface 缺设置门禁、直接 STEP、Viewer 导引边0012和顶面0006实际拾取均有证据；公共七节点全部逐项确认并恢复就绪。导引生成 Warning、9点/1事件严格回读通过；复制独立设置后Stale，独立重新生成通过；恢复公共确认“是”后新的Stale与导出禁用已实测。当前待补实体角色/模式恢复和保存重开，不关闭组合，累计14/30不变。证据见[点击记录](evidence/2026-09-26_v2_final_delivery/freeform_zh1366_click_record.md)。

可复用方法：Freeform长面板底部按钮可滚到，可拖动可见滚动条快速往返；恢复公共弹窗退场时截图有动画残影，另取稳定画面作为证据。无源码修改，不重复Qt回归。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。


### Freeform 中文 1366×768 组合关闭

2026-09-27 current150 项目实际保存重开，草稿状态、导出禁用，重新生成 Warning，9/9点和1/1事件严格回读通过。实体角色反例使用界面JSON输入，遗漏opposite_face_id时中文拒绝，补齐0005后Apply恢复生成入口；该证据不冒称四角色均由Viewer拾取。已有操作实体→导引→实体切换保留各自字段。保存双模式项目时实际处理中文草稿提示“应用”，重开后四角色保留、products为空。详见[点击记录](evidence/2026-09-26_v2_final_delivery/freeform_zh1366_click_record.md)、两个保存项目和closure指纹。

仅本组合V2-01关闭，累计15/30；五工作台1600×900双语和1366×768中文均已通过，余1366×768英文五组及1920×1080双语十组。角色编辑通过不证明实体生成，制造诊断继续留待代表案例检查。本轮没有源码修改、回归重复运行或实机资格升级。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

### Planar 英文1366×768公共设置检查

公共七节点已实际确认，底部控件经滚动可触达；只读显示尺寸核对一致。无源码修改，不重复回归。生成、失效恢复和重开仍待补，本组合不关闭。见[点击记录](evidence/2026-09-26_v2_final_delivery/planar_en1366_click_record.md)。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

Planar英文1366×768续验：公共及独立生成和保存重开后生成均27/27严格回读通过；两次Stale禁用导出已实测。current150项目由GUI保存并重开。剩余空零件/失效引用恢复，组合仍进行中。证据见同一点击记录，无源码修改。

### Planar英文1366×768组合关闭

空Part英文拒绝与补回恢复、已有Placement草稿Cancel恢复、实际加载失效引用夹具后的生成拒绝和Body重绑恢复均已实测。公共/独立/重开/引用恢复四次生成均27/27严格回读通过。新增证据及current150保存项目见同一点击记录和closure指纹。本组合关闭，累计16/30；余英文1366四组及1920双语十组。V2-02—05未关闭。未修改源码，不重复回归；不保存覆盖反例夹具。Skills：开发（stage-gates）、验证、computer-use。

### Curve英文1366×768检查启动

前进程正常退出后重新空白启动，尺寸只读核对一致；缺项门禁、直接STEP和实际两边拾取回填完成。边链0008→0012、反向0,0，后续按实际生成检查方向诊断；本组合尚未通过。证据见curve_en1366点击记录。无源码修改。Skills：开发、验证、computer-use。

Curve英文1366×768续验：公共七节点逐项实际设置完成，坐标确认与Apply经滚动可达，150 mm机床快照和零偏移装夹有效；保留离线警告。七张截图和只读setup状态已归档，生成与后续恢复待补，无源码修改。

Curve英文1366×768续验：0008→0012反向0,0被8 mm断链诊断拒绝，改0,1恢复17/17回读。独立生成同样17/17，两次设置切换Stale和导出禁用已实测。法向面由界面回填0006，本轮没有法向错误，记录不冒称法向拒绝通过。保存重开待补，矩阵仍16/30。

### Curve英文1366×768组合关闭

GUI保存current150并实际重开，draft状态导出禁用；再次生成Warning、17/17严格回读通过。按原计划的有向边、错误恢复及Stale要求核对，断链反例已满足错误恢复项，不额外冒称法向错误验收。本组合关闭，累计17/30。余英文1366三组和1920双语十组。证据见点击记录、保存项目与closure指纹。无源码修改，完整目标继续。Skills：开发、验证、computer-use。

### Rotary英文1366×768检查启动

前一进程正常退出后重新空白启动，客户区尺寸只读确认。空白Create明确提示先打开STEP，生成导出禁用；实际载入圆柱后提示补齐公共设置。底部操作经滚动可达。后续公共七节点及几何生成待补，无源码修改。Skills：开发、验证、computer-use。

2026-09-27 Rotary英文1366×768：公共七节点全部实际应用，界面确认坐标有效并保留离线机床警告；放大视口后轴边0002实际拾取回填。截图及只读设置状态保存在rotary_en1366前缀。无源码改动，未重复回归。组合尚未关闭，仍17/30。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

2026-09-27 Rotary英文1366×768组合完成：端面0003应用拒绝并禁用生成/导出，侧面0001恢复；公共、独立、保存重开后三次75/75严格回读通过。两次设置作用域切换均Stale并禁用导出。累计18/30，余12组。证据见rotary_en1366_click_record.md及闭合指纹。采用小圆柱检查入口与恢复，不替代V2-02代表案例六件套；保留离线碰撞几何不可用限制。无源码变更，无新增技术故障。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

2026-09-27 Tube英文1366×768启动：Rotary正常退出后新开空白会话，真实系统菜单设置尺寸并只读核对。空四角色Apply英文拒绝、底部三个动作禁用；原生加载弯管2实体17边，两个Part逐项指定并确认Valid。证据tube_en1366前缀，矩阵仍18/30，无源码改动。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

2026-09-27 Tube英文1366×768公共设置完成：机床150 mm、喷嘴18 mm离线案例与R-Z包络、PLA材料、模型/构建坐标及零装夹逐项真实应用，界面Ready with Warnings。证据tube_en1366_common_setup.json及六张新增设置截图。返回四角色编辑器，未将尚未执行的角色/生成计为完成。累计18/30，无代码变更。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

2026-09-27 Tube英文1366×768：下拉实际选四角色，遗漏出口Apply拒绝；补0014恢复生成，43775/43775回读通过。材料取消核对并Apply令旧结果Stale且生成/预览/导出禁用，材料已恢复。保留Warning与离线机床限制；未把本轮局部验证当整组完成。证据tube_en1366_generated_summary.json及截图。无源码修改，无新技术故障。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

2026-09-27 Tube英文1366×768关闭：出口内圆0012生成明确拒绝，英文说明选择外圆；恢复0014并Apply，实际保存重开后角色及设置保留，未生成时预览/导出禁用。再次生成43775/43775回读通过，四类差异为空。累计19/30，余11组。证据见tube_en1366_click_record.md与closure_fingerprints。独立设置不适用，完整代表案例导出留在V2-02。无源码改动，无新技术故障。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

2026-09-27 Freeform英文1366×768启动：Tube正常关闭后重新空白启动，系统菜单设置尺寸；缺项英文提示及生成/导出门禁已核对，小平板实际载入，边0012与面0006均经Viewer选择并只读核对。待公共设置及应用生成，不提前关闭组合，累计19/30。证据freeform_en1366前缀。Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use。

## Freeform英文1366公共设置与生成补验

实际应用公共七节点和150 mm圆台；采用Viewer已选导引后公共/独立两次生成9点1事件，严格回读通过。切独立与恢复公共均正确Stale且禁用导出。角色及保存重开待补，不关闭组合，累计19/30。台账旧余12组改为余11组。使用开发、验证和computer-use Skills；无新源码修改或技术故障。证据见freeform_en1366_click_record.md及对应截图/JSON。

## Freeform英文1366保存重开与角色恢复

导引项目实际保存重开和再生成9点1事件回读通过；实体角色先被格式门禁拒绝，核对现有UI序列化后改用bodies对象数组。缺对侧面英文拒绝与补齐后Apply恢复已实测。未生成实体产品，双模式切换与角色项目重开待补，完整矩阵19/30。使用开发、验证、computer-use Skills，无代码修改。证据见freeform_en1366_click_record.md。

## Freeform英文1366组合完成

双模式切换字段保留、实体角色项目保存及实际重开通过，products为空，实体尚未生成。结合已有公共设置、导引三次9点1事件回读、两次Stale和缺项恢复证据，本组合V2-01关闭，累计20/30。余10组1920×1080，后续V2-02—V2-05未关闭。使用开发阶段门槛、验证和computer-use Skills，无源码修改。详见freeform_en1366_click_record.md与closure_fingerprints.json。

## Planar英文1920开始

Freeform正常关闭后重新空白启动，原生系统菜单设置1920×1080并只读核实。Planar空白缺项提示、底部动作可达、实际STEP载入、Part及150 mm机床确认完成；其他设置和工序待补。累计20/30，未关闭本组合。使用开发、验证及computer-use Skills，无代码修改。见planar_en1920_click_record.md。

## Planar英文1920公共设置与生成

公共七节点全部实际应用；默认region只生成区域预览且导出禁用，另建zigzag后生成27/27回读通过，四类差异为空。common_generated.json记录region，zigzag_generated.json才是沉积回读结果，防止混淆。后续Stale、错误恢复、保存重开待补，20/30不变。使用开发、验证和computer-use Skills，无源码修改。

## Planar英文1920设置切换与重开

两次Stale正确禁用导出，独立/保存重开均27点严格回读通过。先取消既有Placement草稿，再完成空Part拒绝与恢复。失效引用检查待补，不关闭组合，累计20/30；无源码修改。Skills：开发、验证、computer-use。证据见planar_en1920_click_record.md。


## Planar英文1920组合关闭

实际失效引用生成报告planar.body_missing并禁用Export，重新选择body_001、Apply、Generate后27/27严格回读通过，四类差异为空。核对此前公共设置、两次Stale、空Part恢复、保存重开证据后关闭本组合，累计21/30。区域预览证据与沉积回读证据分别标注；六件套留在V2-02。无源码修改，未重复运行无关回归。Skills：five-axis-workbench-development（stage-gates）、five-axis-slicer-validation、computer-use。


## 剩余矩阵采用差异验收

2026-09-27用户明确答复“采用差异验收并更新计划”。剩余9组按目标语言和尺寸实测交互与布局，共用功能复用同源码证据，异常触发相关完整流程。计划第6节记录边界，其他四个工作包门槛未变。主Agent串行操作桌面，子Agent tutorial_audit只读盘点教程引用；未用推断增加通过数。此前Planar英文1920归档30个文件哈希及源码指纹均一致，四次27/27回读复核通过。


## 多Agent教程引用盘点

2026-09-27子Agent tutorial_audit只读运行scripts/audit_guide_images.py（退出0），当前83处引用、45个唯一图片、缺失0、15个低对比候选。英文引用中文_zh图片13处，计划中的12处保留为2026-09-25历史数据；当前新增差异包含tube_workbench_en.md:27。此结果只证明引用统计，视觉与图注仍待逐项验收。子Agent继续建立83行清单，主Agent负责桌面，避免并发输入。使用开发、验证Skills及product-delivery-lessons。

主Agent确认新应用会话51822正常退出exit0，当前无切片窗口；未将该退出认定为产品崩溃。Planar英文1920已有30个产物哈希及源码指纹一致，累计21/30保持。


## V2-04逐图清单建立

子Agent已生成[83处引用清单](evidence/2026-09-26_v2_final_delivery/v2_04_image_reference_checklist.md)及同名JSON，包含45张唯一图片、13处英文引用中文图和15张低对比候选，视觉及图注均待核。主Agent已回读清单与JSON，不将引用存在性计为视觉通过。

尺寸调整查阅Qt官方QGuiApplication文档https://doc.qt.io/qt-6/qguiapplication.html，支持-qwindowgeometry；但当前app.py的argparse无该选项，QApplication仅接收sys.argv[:1]，故不直接使用该参数，不修改启动代码来替代验收。当前新会话72641，尚未完成1920尺寸设置，本次不增加通过组合。


## Planar中文1920差异验收通过

实际检查首页、入口、缺项提示、滚动按钮、项目重开、实体选择、独立编辑器与中文恢复公共弹窗。源码指纹与英文1920完整证据一致，复用其共用功能，未重复生成。累计22/30，证据见planar_zh1920_click_record.md。使用开发、验证和computer-use Skills。


## Curve双语1920差异验收通过

双语首页入口、视口选边回填、滚动按钮、状态文字及确认弹窗已实际检查。英文1366源码哈希与当前一致，复用共用功能记录；交互选择的两条平行边未作为连续链生成样例。累计24/30，剩余6组。Skills：开发、验证、computer-use。见curve_1920_difference_record.md。


## Rotary双语1920差异验收通过

双语首页入口、轴边/侧面拾取、底部滚动按钮、状态与单位、150 mm独立设置及确认弹窗已实测。197个源码指纹与英文1366基线一致，共用生成、75/75回读、Stale、错误恢复和保存重开明确复用。未重复生成或导出，累计26/30，剩余Tube和Freeform双语1920。Skills：开发（阶段门槛）、验证、computer-use。证据见rotary_1920_difference_record.md及rotary_1920_closure_fingerprints.json。


## Tube双语1920差异验收通过

双语四角色下拉选择应用、首页卡片、滚动及动作状态、项目弹窗取消均实测；独立Setup切换不适用。当前197个源码哈希与英文1366基线一致，共用生成/回读/Stale/错误恢复/保存重开明确复用，累计28/30。首次原生文件框拒绝正斜杠路径，经微软路径文档核对并改用反斜杠后恢复，未修改源码。证据：tube_1920_difference_record.md及tube_1920_closure_fingerprints.json。Skills：开发、验证、computer-use。


## V2-01矩阵收口

Freeform双语1920入口、导引选边/选面回填、滚动、状态与确认弹窗实测完成；197个源码指纹匹配英文1366基线，共用功能按计划第6节复用。矩阵30/30，其中21组完整、9组差异验收。未把本组导引交互当作代表案例实体生成，V2-02—V2-05保持未关闭。Skills：开发阶段门槛、验证、computer-use。证据见freeform_1920_difference_record.md及其指纹清单。

## V2-02当前弯管导出

2026-09-27承接门禁接入：新增validation/tube_support.py，对分区首个沉积层端点与此前不同层的全部真实沉积段比较保守珠道外包络，基底使用保守包围盒；无接触报Error，接触不等于完整承接证明。已接validate_indexed_tube，Indexed两处算法版本统一升至v5。失败pipe2复核检出699个端点错误，见v2_02_transition_support_current_result.json。初次测试夹具缺extrusion_role导致6项失败，修正夹具后通过；首次JSON写出mappingproxy失败，转dict后复核完成。共享边界计划wedge_plan.py同时新增，3项解析测试通过；新模块合计41项通过，之后新增聚合报告禁止导出的集成断言，承接文件7项通过。JUnit分别为v2_02_support_and_boundaries_tests.xml和v2_02_support_integration_tests.xml，局部Ruff通过。尚未执行完整生成回归、GUI重启或新路径修复；旧运行实例仍加载旧代码，不能据当前窗口声称门禁已生效。门禁是临时防漏，不能替代有效弯管生成。Skills：开发、验证。

2026-09-27沿程体积补充：新增wedge_volume.py，对直线矩形珠道棱柱作浮点凸多面体半空间裁剪，以内部参考点四面体求体积，避免固定采样遗漏窄片。新增10项独立解析体积测试，涵盖单位立方体三轴斜切1/6、互补、1e-6 mm窄条、重复面、切触、刚体变换及反向路径；连同边界/截面模块32项通过，JUnit为v2_02_wedge_volume_tests.xml。局部Ruff与格式处理完成。本模块限直线、固定正交矩形截面；不能用于倾斜补齐路径而不核对截面契约，也不证明喷嘴能制造任意裁剪体。尚未接入Indexed，后续必须完成变厚路径与承接/扫掠验证，旧pipe2资格不恢复。Skills：开发、验证。

2026-09-27有限道宽补充：新增wedge_material.py，对完整矩形截面按共同边界半空间裁剪，返回截面积；不使用中心高度乘宽度近似。解析三角形、互补分区、刚体变换、平行边界及非法输入等与边界模块合计22项通过，JUnit为v2_02_wedge_material_tests.xml，四个新增源码/测试文件Ruff通过。参考Sutherland–Hodgman 1974原始算法 DOI:10.1145/360767.360802；本轮原始摘要检索可见，ACM正文访问403，独立实现且用解析真值验证。此截面积只是几何目标，未证明喷嘴能形成裁剪形状，也未完成沿程体积积分或接入Indexed。旧弯管资格仍不恢复。Skills：开发、验证。

2026-09-27分区修复实施：新增algorithms/tube/wedge_boundary.py，提供共享有向半空间、固定轴柱与层带求交、开放折线裁剪；不补闭合直线。独立解析测试test_tube_wedge_boundary.py共9项通过，JUnit为evidence/2026-09-26_v2_final_delivery/v2_02_wedge_boundary_tests.xml。斜界面体积分区与残余厚度用解析值核对；它只证明几何基础模块，尚未接入Indexed、有限道宽材料积分或完整承接验证，不能恢复旧pipe2资格。局部Ruff检查通过，测试文件按格式检查结果规范化。Skills：开发、验证。

后续复核：独立磁盘回读43775/43775及本轮保存重开已通过。进一步量测发现253→254层的分区转换处有1.79024 mm局部距离，法向分量远大于0.2 mm层高，不能以回读通过代替承接通过。已保留真实NC空移截图与局部数据图，参考Siemens US11292201B2的共同分界面说明继续定位。该导出只作诊断证据，V2-02弯管制造承接门槛未通过。详见同目录v2_02_tube_current150_record.md与v2_02_tube_geometry_review.md；Skills：开发、验证、computer-use。

实际重开150 mm平台项目、生成、查看路径并导出六件套，manifest严格回读43775/43775通过。整体预览不能代替首层承接及空移局部检查，独立磁盘回读和本轮保存重开待补，V2-02保持进行中。多Agent完成历史证据定位，叶轮完整脚本成果未计入当前GUI通过。详见 evidence/2026-09-26_v2_final_delivery/v2_02_tube_current150_record.md 和 v2_02_existing_evidence_audit.md。Skills：开发、验证、computer-use。

2026-09-27 V2-02层带规划：wedge_layers.py按完整凸截面投影计算入口最低点和出口最高点，避免仅按中心线端点截断倾斜区域。新增5项解析测试全部通过（v2_02_wedge_layers_tests.xml），覆盖短尾层、斜出口柱厚守恒、中心线/共线输入拒绝和交叉边界拒绝；局部Ruff通过。当前仍为候选层带，未接入实际沉积路径，不能恢复弯管制造资格。支撑错误补充中英文提示，真实GUI复验待做。用户截图仍为旧NC，不能作为修复后结果。使用Skills：five-axis-workbench-development、five-axis-slicer-validation。下一步需将完整CAD截面投影与开放残余路径接入，并分别验证可沉积厚度、支撑及喷嘴运动；不得仅凭裁剪体积正确放行。

2026-09-27 V2-02用户指出NC预览形状不符：独立检查确认Tube输出MACHINE_PROFILE，预览器只认CONTROLLER_PROFILE，且缺TOOL_LENGTH_MM，实际自动识别(None,0)并显示machine_xyz。已让预览识别自有AC机床的明确标准轴映射，补齐Tube刀长声明，并兼容旧Tube manifest中的machine_trajectory；未知映射或缺刀长仍不猜测。4项专项通过，首次系统pytest临时目录WinError5改用项目独立临时目录后通过，失败JUnit保留。实际旧NC全部43775点与生成Toolpath比较，正确还原最大误差0.00000104394mm，原机床坐标最大偏差83.80316mm。证据：v2_02_nc_shape_audit.py/.json、v2_02_nc_preview_header_tests_localtemp.xml。该证据仅证明NC坐标还原，尚未证明与CAD完整珠道一致或制造承接正确。GUI仍为旧运行实例，尚未重启验证；统计栏固定逆变换公式在降级时仍显示的问题待修。使用Skills：开发、验证；独立Agent只读核对。V2-02不关闭。

2026-09-27预览坐标提示修复：移除统计栏固定逆变换文字，改为根据实际coordinate_transform显示机床XYZ未还原、含实际刀长的AC逆变换或路径坐标系。中英文6项呈现断言与局部Ruff通过。已通过computer-use关闭旧实例并启动新实例（窗口349965134），实际打开同一main.gcode，解析正在进行；尚未记录完成画面或CAD叠加。使用Skills：开发、验证、computer-use。

2026-09-27真实GUI复验：新实例完成同一旧NC加载，恢复直立弯管形状；实际打开example/pipe2/弯管新.stp并在同相机切换实体显示。弯管整体位置/轮廓对应，CAD基底存在而该工序只打印管体；实体遮挡路径，不能用此图证明逐段覆盖或承接。三张原生截图为v2_02_nc_corrected_gui.png、v2_02_nc_corrected_with_step.png、v2_02_nc_corrected_step_hidden.png。未更改诊断NC字节。坐标形状显示问题已获当前GUI证据；制造承接错误仍未修复，V2-02继续进行。Skills：开发、验证、computer-use。

2026-09-27 NC修复回归补充：既有GCodeSourceIndexTests、PreviewCacheTests连同首版新用例13项通过（v2_02_nc_preview_regression.xml）。新增实际postprocess_indexed_gcode→独立文件→load_gcode闭环，采用Rx(90°)与18mm刀长解析真值，不依赖manifest；新文件5项通过（v2_02_nc_export_roundtrip.xml）。Ruff通过。此项关闭文件声明互操作的测试缺口，不恢复弯管承接资格。Skills：开发、验证。

2026-09-27 CAD区域接入准备：新增wedge_footprint.py，从实际BRep与共同半空间交集计算容差扩展的保守投影，5项解析测试通过。真实pipe2全部14区的footprint→layer bands组成成功，合计450候选带，见v2_02_cad_wedge_probe.py/json；尚无沉积路径且保守矩形可能增加空候选，不把层数当制造通过。同步拆分新增超长函数，未修改预算；本轮check_context_budget.py exit0。拆分后承接7项、wedge layers/plan/volume18项、NC预览14项通过（v2_02_tube_prior_support_refactor_junit.xml、wedge_responsibility_split.xml、v2_02_nc_preview_refactor.xml）。新增gcode_preview_profile.py和result_statistics_text.py承接解析/提示职责，GUI此前证据早于该等价拆分，后续相关GUI仍需复验。Skills：开发、验证；多Agent分文件实施。下一步真实候选截面与开放过渡路径，V2-02不关闭。

2026-09-27过渡首末截面实测：14区各首末带共28次原始环截交成功，12个末带在中面裁中心线后为空，见v2_02_cad_wedge_sections.py/json。独立用实际CAD与共同半空间及层带上下平面求交体积，region2/3/4各0.01150559mm³、region13为0.001507026mm³仍有材料；region5-12尾带为0。证据v2_02_cad_wedge_tail_volume.py/json。因此不能以中面无中心线直接丢弃层带，需残余材料任务与完整带厚检查。这些量是完整CAD壁体积，不是0.6mm珠道实际体积；未生成新沉积路径或恢复制造资格。Skills：开发、验证。开放残余候选模块正在独立实现，V2-02继续。

2026-09-27全部层带候选检查：450次真实CAD截面无错误（v2_02_cad_all_sections.py/json）。新增wedge_path_candidates.py与6项解析测试，保留跨中面残余、零厚边界、闭环接缝及缺失截面的任务，尚未接入Indexed输出。真实数据形成430条候选路径/430个含路径层带，233个零厚几何端点和14738个残余任务（v2_02_all_path_candidates.py/json）。按0.6mm道宽与实际层带厚度的直线矩形棱柱逐段裁剪，14182任务为零体积，556任务为正体积，无计算错误；逐段体积和0.1633263323mm³，范围8.27e-9至0.0031133mm³，见v2_02_residual_prism_probe.py/json。此和不是几何并集体积，不计角点珠道重叠，也不是可成形或承接证明；零厚端点不能变成沉积命令，残余不能静默丢弃。Skills：开发、验证。V2-02保持进行中。
2026-09-27残余方案依据补充：查阅Song等原文并提出有界柱厚重分配，避免趋零独立沉积，具体公式及限制写入v2_02_tube_transition_design.md。58616个真实截面顶点柱厚抽样最小1.9618147mm，证据v2_02_region_column_height_probe.json；尚未证明有限道宽或可打印性。Skills：开发、验证。V2-02继续。

2026-09-27新增column_partition.py几何残余并层，14项解析测试通过；未接实际沉积。独立Agent及主线程核对发现Tube珠道中心/TCP混用：indexed中心层面首层Z5.1，OpenGL按±h/2显示5.0—5.2；xyzac._solve_linear却直接将point.position作为contact，NC23.1减18刀长后尖端5.1，距基底5仅0.1mm。此为物理契约冲突，FK/严格回读只能证明该目标自洽。需明确中心与尖端转换并同步碰撞、预览、后处理及读回，不能直接全局平移共享Toolpath影响其他工作台。V2-02不关闭；下一步优先核对并修复该接口与残余路径的统一语义。Skills：开发、验证。

2026-09-27 TCP接口修复进行中：新增manufacturing/tube_tcp.py，仅按Indexed连接语义从材料中心转换尖端；depart取前一沉积层高，travel/approach取后一沉积层高，保留IDs/events/体积。已接indexed_tube._solve_and_validate；碰撞新增独立nozzle_toolpath，仅喷嘴采样使用TCP，IPW记录仍用材料中心。Indexed算法版本两处升v6。16相关测试通过（首次PYTHONPATH缺失、随后旧简化夹具缺depart/travel失败，修正环境和夹具后通过，失败记录保留）；上下文门禁通过。真实旧路径首两个点独立转换与求解得中心Z5.1、尖端5.2、机器Z23.2、基底5，见v2_02_tcp_first_layer.json。当前修复未完成NC珠道中心元数据/预览及全路径回归，GUI仍早于此变更，不能据此关闭V2-02或恢复旧导出资格。下一步补齐NC明确位置语义并与中心线预览一致。Skills：开发、验证。

2026-09-27 NC中心/TCP闭环：Indexed专属声明与逐点宽高/偏移元数据已接后处理及独立预览，机器轴保持真实TCP。水平、倾斜、不同层高、旧NC兼容、未知/缺失元数据拒绝及严格回读共19项测试通过，证据v2_02_tube_nc_material_preview_junit.xml；Agent完成Ruff/Mypy/context检查，未运行Qt。新增bounded_wedge_paths.py将柱厚并层转换为候选路径，厚度突变保留双侧端点并断开挤出，4项解析检查通过（v2_02_bounded_wedge_paths.xml），局部Ruff和context通过。仍未接完整弯管生产生成，有限道宽覆盖、承接、碰撞及当前GUI复验待做。V2-02不关闭。使用Skills：five-axis-workbench-development、five-axis-slicer-validation；本轮实际调用登记。方法限制：中心柱区间守恒不能替代真实珠道覆盖证明。

2026-09-27有界候选完整数据检查：复用已保存的450个实际CAD截面，形成429个含路径层带、800条开放/闭合候选路径，厚度0.1—0.3mm（浮点尾差约3e-15），零厚端点0，15532项残余检查任务，见v2_02_bounded_path_candidates.py/json。对13处分区转换的首层全部候选端点，与此前所有候选线段作连续最近距离和保守包络半径检查，明确不接触点为0，见v2_02_bounded_transition_probe.py/json；这只是必要条件，不能证明足够支撑、有限宽覆盖、无重叠或无碰撞，也未输出实际制造路径。45项组合领域回归通过（v2_02_tube_v6_combined.xml）。下一步核对移动后中心线是否仍符合真实管壁，并处理有限道宽/残余任务及生产接入。Skills：开发、验证。V2-02继续。

2026-09-27变高路径接口补充：发现开放弧起点approach不能沿用首个沉积终点的高度，否则斜变厚段的起点TCP偏移错误。tube_tcp.py优先使用点上显式layer_height_mm，旧无显式值连接继续使用相邻沉积高度。独立0.1→0.3mm反例验证起点偏移0.05mm、终点0.15mm；16项TCP/碰撞/NC相关测试通过（v2_02_tcp_variable_start.xml），局部Ruff通过。该接口准备尚未接入新候选路径生成，真实管壁贴合量测由独立Agent进行，V2-02不关闭。使用Skills：开发、验证。

2026-09-27开放路径生成接口与独立壁厚核查：现有_PathBuilder.add_layer增加逐点层厚与外部积分段体积输入，变高路径缺体积拒绝，路径间保持depart/travel/approach而不补闭合挤出；approach/travel显式保存起点层厚。32项相关测试及3子测试通过（v2_02_open_builder.xml），Ruff/Mypy/context通过。既有碰撞回归首轮2失败源于障碍仍放材料中心，按解析h=1mm将障碍移至真实TCP后21项及3子测试通过，保留v2_02_pipeline_v6.xml失败与tipfixture成功证据。Agent独立v2_02_bounded_shape_audit.py/json/md量测44202中心点轴向移动max0.05mm，径向中壁偏差max0.00721281mm；88404横向边缘点未越壁，但实际壁厚1mm，0.6mm单珠留下两侧约0.2mm未覆盖材料。现有0.02弦误差和0.05分区弧垂误差不可挪作覆盖容差。新候选尚未接正式生成；下一步明确并实现完整壁厚覆盖和有限珠道验证，不能只以单中心线形状接近CAD恢复资格。Skills：开发、验证。V2-02继续。

2026-09-27壁厚分道与逐点宽度：参考Prusa官方Arachne说明 https://help.prusa3d.com/article/arachne-perimeter-generator_352769 的变道宽填壁方向，独立实现受限wall_tracks.py等分截面柱候选，不复现Arachne。Agent完成8项解析测试、Ruff/Mypy；1mm圆环/.6目标形成两道.5mm，保留斜截面宽度/完整覆盖/未校准最小宽度限制。主线程_PathBuilder增加widths_mm并要求外部段体积，NC逐点宽度不再按layer_id取最后值，避免同层多道宽度串用。29项相关测试及3子测试通过（v2_02_width_builder.xml），Ruff/context通过。真实450截面的wall_tracks_probe运行中，尚未生产接入及制造放行。使用Skills：开发、验证。
2026-09-27真实分道候选完成：450个实际CAD截面全部生成2道，各点宽度0.500000—0.509035mm（浮点尾差忽略于显示），见v2_02_wall_tracks_probe.py/json。该结果仅覆盖截面柱几何，尚未与共同边界、残余层和完整珠道并集组合。主线程2源码Mypy通过。V2-02继续。

2026-09-27双道残余完整诊断组合：新增wedge_tracks按严格投影匹配插值道宽/法向，5项测试通过；ruled_bead_volume按固定生长轴及线性横向跨度/层厚解析积分Jacobian，4项解析测试通过，拒绝折叠单元。19项组合测试通过（v2_02_combination.xml）；Mypy首次发现依赖wedge_volume的cap center三元组类型问题，复用_vector修复后Mypy及10项体积回归通过。真实450截面形成1600条诊断开放/闭合路径、91516点，其中86718沉积点，31150残余任务，组合错误0，见v2_02_combined_diagnostic.py/toolpath.json/summary.json。逐段体积和6477.4620mm³，对解析圆环扫掠6473.0720mm³偏多4.3900mm³（0.06782%），见v2_02_combined_volume_comparison.json；总量不能证明局部无遗漏/重叠，未做CAD裁剪/并集、碰撞或完整承接。禁止视为合格制造路径，未接正式入口。下一步局部有限珠道检查及变尺寸段包络一致性。Skills：开发、验证。V2-02继续。

2026-09-27组合路径承接与角点核查：tube_support对变尺寸前段采用两个端点最大包络半径，防止只用终点小尺寸误报悬空；8项测试（v2_02_taper_support.xml）、Mypy/context通过。91516点诊断路径执行transition_support_issues得到0问题（v2_02_combined_support.py/json），仅为分区首层端点必要接触条件。独立Agent角点核查86718段693744个起止角点，entry越界仅浮点尾差；exit最大0.0256528921mm、内壁最大0.0114693172mm、外壁0.0109477930mm，见v2_02_combined_corners_audit.py/json/md。1e-8仅数值统计阈值，不是新增制造容差。总量近似正确不能掩盖这些局部偏差；需处理有限道宽斜边界、重叠/缺料与当前IPW变尺寸包络，不能直接放行制造。Skills：开发、验证。V2-02继续。

2026-09-27变尺寸IPW与实际诊断碰撞：_record_deposition改为两个端点宽高最大值建立既有椭圆珠道胶囊，防止较宽起点漏入索引，未把该模型称为矩形珠道完整几何。14项碰撞相关测试通过（v2_02_variable_ipw.xml），Ruff通过。完整91516点诊断路径经TCP转换，在0.05mm采样参数下对IPW检查1947046次，0碰撞（v2_02_combined_ipw_probe.py/json）；该轮无基底/夹具，另已启动加入原source/settings对应基底AABB的补查。用户已收到独立CAD几何验收公差问题（0.02/0.01/自行指定），当前未据已测偏差反设容差；仍继续独立工作。Skills：开发、验证。V2-02不关闭。
2026-09-27基底补查完成：同一完整诊断路径加入已保存基底AABB后，1947046次采样检查仍无碰撞，见v2_02_combined_substrate_probe.py/json。来源基底范围与原输入/设置对应，未增加不存在的夹具。保留采样/椭圆胶囊及未放行限制。

2026-09-27完整诊断机器轴与NC回读：91516点完成真实自有AC机型、18mm喷嘴TCP求解，生成明确标注DIAGNOSTIC ONLY/NOT MANUFACTURING QUALIFIED/machine_executable=false的v2_02_combined_diagnostic_only.gcode。严格磁盘回读91516/91516通过，坐标/进给/挤出/事件顺序差异均0；文件预览94715时间步中91516空间点，材料中心恢复最大偏差1.2155744e-6mm，见v2_02_combined_nc_roundtrip.py/json。唯一轴警告为首19049点直立奇异段保留C=0，未产生轴错误。该证据验证诊断路径忠实转换，不证明局部几何、材料并集或真实GUI；没有恢复生产导出资格。Skills：开发、验证。V2-02继续。

2026-09-27当前GUI诊断预览复验：旧窗口已不存在，使用当前源码启动新实例（窗口148573352，运行会话50416），真实点击打开v2_02_combined_diagnostic_only.gcode并完成加载，再打开example/pipe2/弯管新.stp、同相机切换实体显示。截图v2_02_combined_gui_nc.png、v2_02_combined_gui_with_step.png、v2_02_combined_gui_step_hidden.png；整体位置与轮廓对应，实体遮挡及密集路径不能证明局部覆盖。界面检测层数仍1，需Indexed NC明确层标记，已分派修复，截图早于该修复。加载过程持续推进但耗时较长；只读代码审查v2_03_nc_parse_code_audit.md发现每运动段起终点重复完整FK/机型验证（约183032次），未测性能占比，候选改进为会话内精确姿态缓存，不能删校验或取消。生产几何与V2-02全链未关闭。使用Skills：开发、验证、computer-use（本轮实际调用登记）。

2026-09-27层导航与解析性能：Indexed专属后处理新增indexed_layers.py，按真实layer_id首次顺序输出标准Layer标记，同层双道/开放弧不增层、非平面Z不猜层、空移沿源目标层；Agent后处理→parse及头声明7项通过，尚未重生成完整带层NC/GUI复验。小样本cProfile定位2000运动中4000次机床变换，5.262s中4.903s在该路径；新增每parse会话独立128项精确姿态缓存，保持每次轴字/异常回退验证，不舍入角度、不缓存失败、机型对象强引用隔离。19项及3子测试通过（v2_03_pose_cache.xml）、Ruff/Mypy/context通过。相同2000运动剖析0.332s；完整原诊断NC不使用磁盘缓存的parse耗时6.591s，91516点最大中心偏差仍1.2155744e-6mm，道宽误差0、层厚误差8.19e-15mm（v2_03_full_parse_cached_pose.py/json）。这是纯解析测量，未将其当作GUI加载/取消验收。Skills：开发、验证。V2-02及V2-03均未关闭。

2026-09-27带层诊断NC归档：核对v2_02_combined_layered_roundtrip.json与实际G-code SHA256一致（46b50f726b9a4d0e5819574ceee9cfce252e4aee7b3a894c9ff0cc814b5ee1be），严格回读91516/91516通过。新增独立v2_02_layer_identity_audit.py/json逐点比较源layer_id与文件预览层编号：91516个空间点、429层，层身份差异0，避免仅凭层数相等判断正确。该证据只关闭诊断文件的层标记对应检查，GUI层导航尚未复验，生产几何越界、覆盖及正式生成接入仍未完成，V2-02保持开放。使用Skills：five-axis-workbench-development、five-axis-slicer-validation，本轮实际调用登记。上一轮为用户解释未改变项目状态，本轮补充当前磁盘核验与逐点证据。

2026-09-27真实GUI带层复验：当前窗口569313924真实打开带层诊断NC，观察加载进度23.9%→92.9%→完成；界面检测429层、91516空间段、86718正挤出段。实际下拉选择层0—24后仅显示底部环带，点击下一组后显示层25—49及上移环带。截图v2_02_layered_gui_loaded.png、v2_02_layered_gui_first25.png、v2_02_layered_gui_next25.png。本轮证明该文件层范围过滤及下一组按钮可用；没有量测端到端加载时间或取消，不扩大为V2-03通过。几何后续调整检查方向：内部共同分区面的越界需与相邻沉积材料组合检查，不能直接当作CAD外表面误差；已委派最坏分区局部覆盖/重叠量测，暂停增加仅返回残余任务的候选模块。V2-02仍开放。使用Skills：computer-use、five-axis-workbench-development、five-axis-slicer-validation。

2026-09-27局部并集与加载测量：独立Agent完成v2_02_boundary_union_probe.py/md/json及fine.json。region12内部越界656角点中630仍在CAD壁内，全部在region13平面域；不能将0.02565mm内部归属越界误报为外形误差。最坏接缝0.8×0.8×0.12mm区域以0.005mm采样，CAD体积0.0768mm³、材料并集0.07324425、重叠0.003393、未填0.00355575，局部外超0；未填全部在region12侧。下一步应调整有限宽末层及邻区起始层，沿同一局部区域比较，再扩大到完整接缝。V2-02不关闭。
V2-03新增可复现v2_03_finalize_cancel_probe.py/json：10万运动输入耗尽时请求取消，最终处理后0.331s抛出取消，未据静态怀疑增加无依据改动。真实GUI重载后读只读状态记录request3 complete、端到端7.377614s、worker6.765127s、cache_hit=false（v2_03_gui_reload_metrics.json）。两次尝试点击取消时，最终状态都是complete，未证明取消成功；不可将旧图保留当取消证据。后续需在耗时更长的实际任务中检查取消。使用Skills：开发、验证、computer-use；当前目标保持active。

2026-09-27按用户最新要求调整：计划§7明确暂缓新弯管诊断方案微小接缝优化，保留局部缺口/重叠证据和未验证限制；不恢复旧单道欠填及大间隙方案资格，不放宽公差、不删除核心Error。后续优先新方案生产接入与完整GUI六件套/回读/保存重开，再推进其余工作包。用户关于实物鲁棒性的判断不替代实机证据，machine_executable=false保持。此次是任务优先级调整，非验收通过。使用Skills：five-axis-workbench-development、five-axis-slicer-validation（沿用本任务已读流程）；目标active。

2026-09-27正式接入准备已实现：新增bounded_indexed.py从当前BRep实时生成双道/有界厚度Toolpath及BoundedIndexedSlicePlan，保留全部band、非空layer映射与residual_task_count，逐band/track/path取消检查，异常不吞、空region明确报错。Agent实时CAD直管3项测试、Ruff/Mypy/context通过，尚未切换产品入口。新增bounded_tube_geometry.sampled_wall_errors为多道中心采用真实内外半径包含检查及段内弦误差，避免旧中壁半径检查误报；5项解析测试通过，Ruff/Mypy通过。首次测试夹具遗漏extrusion_role导致5失败，修正后证据v2_02_bounded_geometry_fixed.xml；失败XML保留。中心包含不能证明珠道完整覆盖。下一步将策略接到product生成、序列化及策略对应验证，并用真实弯管全链复验。Skills：开发、验证。V2-02继续，微小接缝优化按计划§7暂缓。

2026-09-27用户明确要求“不要钻牛角尖”，已写入交付计划§8：停止微小接缝精细采样/新候选模块，非阻塞项登记后推进，不新增交付门槛，不无变化重复验证；优先现有方案正式接入和完整案例，减少细碎回合。此执行纪律覆盖此前继续优化微小接缝的后续建议，核心错误和原计划必要验证仍保留。目标继续active。

2026-09-27 V2-04独立推进：将教程assets内8份捕获过程JSON移至本轮evidence/guide_capture_records，逐字节及SHA256核对，relocation_manifest保留原路径，README说明历史相对图片路径解析；更新2份历史复盘显式链接，未修改历史事实。图片审计83引用/0缺失，15低对比仍待视觉，独立Agent进行实际逐图检查。新Tube正式service接入由领域Agent执行中，未宣称完成。当前不再深挖微小接缝，按计划§8并行推进独立交付项。

2026-09-27 V2-02正式产品链已接bounded实时CAD生成，原支撑/碰撞/轴/回读保留，边界精度待验证为Warning，计划序列化含策略/bands/layer映射/残余计数，版本v7。Agent相关领域回归及Ruff/Mypy/context通过；真实pipe2正式service已启动，执行会话23630仍运行，证据脚本v2_02_live_service_v7.py，不重复启动。GUI闭环待做。
V2-05新建tmp/v2_clean_install，include-system-site-packages=false，按README执行pip install -e .退出0，pip check无冲突，OCP/Qt/VTK/NumPy导入通过；日志及freeze归档。此为干净运行依赖安装，不是最终wheel或完整新环境GUI验收，V2-05不关闭。V2-04修正rotary_workbench_zh图注：原图只显示Warning路径，不声称展示导出目录/六文件；图片替换仍待做。使用Skills：开发、验证。

2026-09-27正式pipe2服务完成：v2_02_live_service_v7.py/log/json，209.226s，429层/91516点，exportable=true、strict readback=true，仅xyzac.rotary_singularity与tube.bounded_boundary_accuracy_deferred警告，check_ipw=true及原基底AABB保留。此为正式服务真实CAD链证据，GUI闭环仍待完成。V2-04累计48唯一图已实际复核（含4普通图片链接），重拍归并11组连续场景，见v2_04_visual_review.md与replacement_candidates.json。
V2-05首次独立GUI启动失败：ModuleNotFoundError cadquery，定位Planar offset/support在运行时导入CadQuery，而原pyproject仅列cad-tests。已把既有2.7范围移入运行依赖并修正README，不改算法；参考CadQuery官方安装说明与实际源码。修正后独立环境重装会话2796正在运行，日志v2_05_clean_install_runtime_fix.log；旧GUI已正常退出，尚未启动替代实例。此失败说明仅pip check/import OCP不等于应用启动通过，保留未完成状态。

2026-09-27独立环境Qt启动修复：用户提供无Qt平台插件弹窗。实际QLibraryInfo.PluginsPath返回F:/???????/...，路径不存在；PyQt5.__file__计算真实中文路径，qwindows.dll实际存在。参考Qt QCoreApplication.addLibraryPath官方API，在app.main仅默认插件目录失效时加入绑定包内真实Qt5/plugins目录，不改系统环境。Windows QApplication最小实测platformName=windows、退出0，Ruff通过；同一独立环境真实主界面成功启动，窗口4131906，会话65755，截图v2_05_clean_start_fixed.png。CadQuery补依赖重装亦已退出0、pip check通过，freeze已归档。启动通过不替代示例生成/导出与最终wheel验收；下一步在此界面继续项目闭环。

2026-09-27 V2-02 v7非Qt产品回归收口：使用合法短直管夹具替换旧10mm道宽/层高快速夹具；低速正常流程与真实加速度超限拒绝导出分开验证。独立双道半径5.25/5.75mm、材料中心到TCP半层偏移及v7版本断言更新，保留坐标变换/FK、弦误差、取消状态、旧上下文失效、六件套和严格回读断言，未放宽产品校验。19 passed、2 subtests passed，见evidence/2026-09-26_v2_final_delivery/v2_02_v7_product_regression_final.xml；两轮发现过期断言的失败XML保留，Ruff通过。仅测试文件修改，未运行Qt或重复大pipe2，不替代GUI验收。实际使用Skills：five-axis-slicer-validation、five-axis-workbench-development。

2026-09-27 V2-02/V2-03真实GUI推进：独立安装环境窗口4131906打开tube_en1366_current150，点击生成后实际取消，界面显示生成已取消、生成按钮恢复且导出未误启用（v2_03_tube_generating.png、v2_03_tube_cancelled.png）。本次取消前没有有效结果，尚不证明旧结果保留。随后重新完整生成、查看路径及缩放、实际导出tube_v7_gui_export六件套；manifest严格回读91516/91516点通过，四类差异均空，collision_check_complete=true，511685采样，仅奇异/边界暂缓/参考设备Warning。保存tube_v7_gui_project并真实重开，参数及几何引用恢复；路径运行时未恢复、查看/导出禁用，待核对持久化设计，不宣称全部闭环完成。截图v2_02_v7_gui_path/exported/reopened.png。使用Skills：computer-use、five-axis-workbench-development、five-axis-slicer-validation；本次实际调用登记。V2-02/V2-03/V2-05保持进行中，微接缝按计划§7暂缓。

2026-09-27弯管重开行为核清：tube_generation_service恢复product_states但不恢复内存product_results，tube_serialization只保存状态；tube_workbench_zh.md第132行明确重开恢复输入后需重新生成，属于既有合同，不新增运行时缓存恢复要求。当前GUI另实际打开tube_v7_gui_export/main.gcode，429层、91516空间点，切换空移并拖动旋转，路径及方向标响应，截图v2_02_v7_gui_nc_travel_rotated.png。弯管本次正式生成/预览/六件套/严格回读/输入保存重开已形成证据；微小接缝限制保留。V2-02其余代表案例、V2-03有效旧结果取消保留及V2-04/V2-05剩余门槛继续。

2026-09-27 V2-02校徽当前配置复验启动：真实GUI载入gui_agent_logo/project.json/project.json，原机型快照v1为180mm；通过机型下拉选择内置自有AC v2、应用并重新应用Placement，当前machine hash ac7738eb81c857223aca1a69db9e81710d37dcd659f34cd1821c4f837673714c（150mm）。进入Freeform点击生成与检查，窗口4131906仍运行，HTTP generation_in_progress=true，状态归档v2_02_logo_current150_generating.json；尚未报告成功或重启计算。V2-04仅修正Tube中英文教程v7多道/实际层厚/TCP及暂缓Warning说明，原有重开输入合同保留，旧截图明确为操作示例，本地链接通过，图片重制仍待做。实际Skills：开发、验证、computer-use。目标active。

2026-09-27 V2-05当前完整静态门禁通过：quality_v7_current.log首次因诊断脚本格式/导入失败；对22份证据脚本仅作格式与等价静态整理，前后SHA见v7_static_script_changes.json，历史结果未修改、未重跑模型。产品源码仅导入/格式及workbench_issue_ui局部变量重命名消除str与str|None复用。最终quality_v7_static_final.log中Ruff、迁移Ruff、安全规则、61文件格式、上下文预算及Mypy218源码全部通过，退出0；没有排除目录或放宽基线。校徽GUI当前仍generation_in_progress，应用会话65755确认存活，未重启。此静态通过不等同于完整回归、最终包或托管CI完成。实际Skills：开发、验证；目标active。

2026-09-27 V2-05当前源码包检查：python -m build --outdir tmp/v2_release_current退出0，wheel/sdist版本2.6.3.dev3+gedacd49.d20260927，twine check两包PASSED。日志v2_05_build_current.log、v2_05_twine_current.log；v2_05_package_current.json记录SHA并核对wheel包含bounded_indexed、bounded_tube_geometry及own_ac_fdm资源，METADATA包含运行时CadQuery。当前为未封版工作区构建，不称最终提交CI或wheel新环境完整流程已通过。校徽仍为原GUI生成任务，未重复启动。Skills：five-axis-slicer-validation、five-axis-workbench-development。目标继续active。

2026-09-27 V2-02校徽GUI完成生成及六件套导出：logo_current150_gui_export含六文件，manifest严格回读102969/102969点、21984/21984事件通过、issues为空，machine_executable=false；ready状态见v2_02_logo_current150_ready.json。V2-03补齐真实有效结果取消保留：在同窗口点击再次生成后取消，HTTP生成状态false且提示已取消，产品与取消前完整JSON相等，GUI导出重新启用、路径保留；证据v2_03_logo_cancel_state.json及v2_03_logo_cancel_preserved.png。不把工具调用耗时当精确取消延迟。校徽尚需补预览细看、保存重开；整体目标不关闭。使用Skills：computer-use、开发、验证。

2026-09-27校徽保存重开通过：真实GUI保存logo_current150_gui_project并重新选择其project.json载入，正常使用项目内STEP副本；与生成前ready快照比较，freeform.operations完整JSON一致，机型仍v2及150mm资源hash一致。状态v2_02_logo_reopened.json。生成路径依既有合同不持久化，未误称恢复运行时结果。生成路径已实际缩放，完整密集显示尚不能辨清校徽局部沉积，后续用导出NC阶段筛选补查，不重跑生成。V2-02继续，整体目标未完成。

2026-09-27校徽NC真实预览补验：打开logo_current150_gui_export/main.gcode，实际选择操作2、切换空移、放大后文字/环线/顶部图案可辨，点击上一操作切至底座工序，截图v2_02_logo_nc_stage2.png、v2_02_logo_nc_stage1.png。该预览连同前述GUI生成、六件套严格回读及输入保存重开构成当前校徽流程证据，不当作实物精度证明。V2-05补查wheel全部218个Python文件与src逐字节一致，v2_05_wheel_source_match.json差异为空。下一代表案例为叶轮，目标active。

2026-09-27 V2-02叶轮装夹纠正：用户指出模型远离圆台。核对原impeller_gui_root_growth_live/project.json，Build CS为单位变换，Placement的T_mount_from_build却含XYZ各+250mm，局部adjustment为0；因此界面零微调不等于绝对居中。真实GUI取消旧装夹生成，设置局部DX/DY/DZ各-250mm并应用，显示模型后叶轮与150mm圆台同心、底面落台（v2_02_impeller_centered.png）。保存impeller_centered150_gui_project/project.json，回读确认实际T_mount_from_build为单位矩阵、圆台diameter_mm=150；未改源STEP、未缩放、未仅移动相机。已按新装夹重新生成，尚未完成该轮路径检查，旧偏移结果不作为本轮居中验收。UI补充显式重置安装位入口由独立Agent处理。外部参考为Prusa官方对象操作面板的落台/位置操作，https://help.prusa3d.com/article/object-manipulation-panel_1757 ，具体修正依据本项目实际持久化矩阵。使用Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use；本次实际调用登记。目标保持active。

2026-09-27装夹防复发补充：Placement新增中英文“重置到安装位原点”按钮，清除历史reference与局部adjustment，仅更新草稿，保留应用/取消语义；帮助说明零微调不代表平台中心，模型底面位置仍由Build CS定义。独立Agent完成tube_controller纯领域回归12 passed、6 subtests，证据placement_reset_domain.xml；Ruff、context和新helper Mypy通过。主Agent复核helper/调用和测试；正在运行的GUI尚未重启，新增按钮真实点击未验收，不计为界面通过。用户当前叶轮居中操作已通过旧界面实际完成并保存。无新增精度优化范围，后续继续原计划。

2026-09-27 V2-04本轮完成实质替换：当前真实GUI拍摄中英首页、中英150mm机床、叶轮现有曲面操作、Model CS和Build CS编辑器；坐标编辑未修改，拍摄后均取消草稿。复用已验证Tube导出图及校徽阶段2局部。独立Agent逐图查看、裁除外围光晕/内部路径，更新6张旧图共20处引用，另新增校徽局部图；来源/裁剪/SHA及逐批链接核验见v2_04_current_image_replacements.md/json，candidate相应replacement_applied=true。原证据不变，设置草稿不冒称生成完成，其余图片仍待。使用Skills：five-axis-workbench-development、computer-use。
V2-05装夹重置后完整质量检查：首次quality_placement_current.log发现tube_ui导入排序，修正后quality_placement_fixed.log退出0，Ruff/security/format/context/Mypy219全部通过；无修改基线。V2-03本机为i7-12700H、14核20线程、31.8GB、Windows11，归档v2_03_machine_environment.json。居中叶轮生成期间曾实际响应显隐、语言及页面切换；15:55附近出现未响应，v2_03_impeller_busy_observed.png。15:56进程57380仍在、CPU累计2588.17s、Responding=false，HTTP15s观察超时，不当作任务终止、不重启生成；该长任务响应判据仍待核对恢复。v2_02_impeller_centered_generating.json保留此前活跃快照。完整目标保持active；本轮有教程替换及质量证据进展。

2026-09-27 V2-03叶轮长任务热点确认与修复：临时工具py-spy按官方dump用法只读采样进程57380，两次均停在_PrintedSegmentIndex.candidates；第二次局部量显示sequence=682。原查询对重复样本反复合并含未来沉积的大桶且无检查点。已在postprocessing/printed_segment_index.py保持原空间桶及精确碰撞判定，按网格去重、bisect_left取index<sequence前缀、批量调用既有checkpoint。25项相关回归通过，合成基准候选681个完全一致，1.129792s→0.001925s；不外推整件耗时。简报impeller_candidate_fix.md、栈v2_03_impeller_stack.txt、测试impeller_candidate_index_final.xml、基准impeller_candidate_benchmark.json。确认源码热点、保存项目哈希并尝试UI返回无响应后，结束本任务旧进程57380，session65755退出1；不是把HTTP超时当自然终止。
新版独立环境GUI会话4797、窗口53152702已启动，真实打开impeller_centered150_gui_project，点击新增重置/取消/再次重置/应用；保存impeller_reset150_gui_project并回读actualT为单位矩阵、adjustment全0，v2_03_placement_reset_applied.png。取消后树恢复有效，但控件仍保留草稿显示，不误称字段自动刷新；领域取消语义已有测试。随后真实点击完整生成，起始观察时刻见v2_03_impeller_fixed_start.txt，当前进程2448、generation_in_progress=true且last_error=null；完成/导出仍待。新增源码后quality_impeller_candidate_final.log全套门禁退出0。使用Skills：开发、验证、computer-use；目标继续active。

2026-09-27 V2-04追加实际替换：独立Agent逐张查看12个当前V2-01候选，新增Curve中英选边、Planar本地编辑器、Rotary侧面选取4张旧图的5处替换，累计10张旧图、25处引用，另新增校徽局部图。保留状态和用途，不用Zigzag冒充三角填充、不用Spiral冒充Around Part；最新51相关链接有效。中英坐标指南同步说明重置安装位需Apply、按Build CS配对而非自动寻找底面；不用-250补偿作为用户操作要求。来源和裁图仍见v2_04_current_image_replacements.md/json。使用Skill：five-axis-workbench-development。
V2-02下一输入已定位：2026-09-24_three_color_fan_gui_project_corrected/project.json/project.json可同时检查三叶整件与T0/T1/T2换料，需换当前150mm机型；原保存层高0.4/采样0.8，历史0.8/1.6粗参数仅功能证据，不当作0.4喷嘴打印资格。机床/站位仍离线。新叶轮16:13状态正常响应，16:14栈在solve_xyzac_trajectory，v2_03_impeller_fixed_stack.txt及fixed_generating.json；尚未完成整件。V2-03/04/05均不提前关闭。

2026-09-27 V2-04第二批复用完成：独立Agent实际查看12张候选，替换IMG-010/026/029/031共4张旧图9处引用，累计14张旧图34处引用，另新增校徽局部图；52个相关链接有效。Part空面板不能代替实体表、Placement光晕贴应用按钮，均未伪造替换。来源与保留判断见v2_04_current_image_replacements.md/json。V2-05已启动包含装夹重置和候选索引修复的当前包构建，session75541，完成状态待核对。叶轮进程2448仍存活、Responding=true且generation_in_progress=true；实际截图确认居中及生成状态，不将等待记为完成。Skills沿用开发、验证、computer-use。

2026-09-27 V2-05当前包构建完成：session75541退出0，tmp/v2_release_final的wheel与sdist经Twine均PASSED；v2_05_build_final.log、v2_05_twine_final.log、v2_05_final_package_hashes.json保留结果。逐文件核对wheel内220个Python源码与当前src字节一致，无遗漏/差异，见v2_05_final_wheel_source_check.json。此包包含装夹重置与候选索引修复；安装启动、最终全回归和提交CI尚待，源码再改需重新构建，不关闭V2-05。

2026-09-27 V2-03当前叶轮运行观察：16:25—16:28进程2448保持Responding=true，实际点击显示模型关闭/恢复均响应，截图v2_03_impeller_fixed_hide_responsive.png；16:26只读栈位于_sample_move/forward_kinematics的换姿空移规划，已进入原热点所属阶段，尚未证明整件完成。16:27:59仍generation_in_progress=true、last_error=null、CPU累计1033.3125s。未重启计算。V2-05独立只读提交范围审查发现历史输入manufacturing-setup.yaml被GUI自动保存，当前不stage历史变更；新证据含超100MiB文件，后续明确选择摘要及必要文件，不整目录加入。Skills：开发、验证、computer-use。

2026-09-27 V2-04保留与补拍收口：独立Agent逐图判定16张编号图及3张普通链接图可按原教学用途保留，新增当前Planar Zigzag替换5处，累计15张旧图39处引用；修正Rotary零原点和Spiral导出状态图注，218本地链接有效，剩余14张旧图归并7组，见v2_04_minimum_remaining_captures.md。主GUI本轮实拍中文/英文材料T0/T1草稿表和中文换料站空字段，文件v2_04_material_zh_draft_raw.png、material_en_draft_raw.png、station_zh_fields_raw.png（均v2_04前缀）；两次材料草稿和换料站均Cancel，未应用到叶轮。已交独立Agent替换相关教程，尚未计入上述累计。16:33叶轮仍运行无last_error，语言及对话框实际响应；不重启。Skills：开发、验证、computer-use。

2026-09-27 V2-02叶轮完整GUI生成成功：当前产品generated_at为16:33:54.992，起始观察16:09:53，相差约24分02秒（非独立精确点击计时）。真实自由曲面界面显示完整叶轮沉积路径、生成恢复及导出可用，仅Warning；v2_02_impeller_fixed_generated.png和completed_state.json。严格回读810990/810990路径点、16983/16983事件，issues空，offline_exportable=true、machine_executable=false；摘要v2_02_impeller_fixed_summary.json。导出目录已建但两次工具检测到用户正在操作窗口而拒绝点击，因此尚未导出，不与用户抢鼠标，六件套/重开待继续。V2-04材料三图已替换，累计18图42引用；又实拍Part角色和Placement编辑控件，未改字段并取消，已交Agent整理。Skills：开发、验证、computer-use。

2026-09-27 V2-02叶轮GUI导出与保存完成：用户截图窗口关闭后真实点击导出，impeller_reset150_gui_export生成main.gcode、machine_axes.csv、manifest.json、preview.json、toolpath.json、warnings.json共六文件；manifest回读810990点/16983事件一致，issues空，machine_executable=false。逐文件大小与SHA256见v2_02_impeller_export_hashes.json，导出后截图v2_02_impeller_fixed_exported.png。实际Ctrl+S保存到impeller_completed150_gui_project，project.json及STEP/Setup已落盘；重开及NC界面预览仍待。V2-04 Part/Placement两图已替换，累计20旧图48处引用，剩余9图5组，218链接有效。Skills：开发、验证、computer-use。

2026-09-27 V2-02叶轮保存重开完成：真实打开impeller_completed150_gui_project/project.json，source_hash保持3776fe6e…f21f，操作1项恢复、last_error=null；模型显隐后确认仍位于圆台中心。v2_02_impeller_reopened.png及reopened_state.json。产品内存结果0、导出禁用符合此前已核实的输入持久化合同，不新增重算要求。随后真实打开impeller_reset150_gui_export/main.gcode进入NC页，request1正在parse，进度约30.6%；空移和阶段导航待载入完成。用户已表示叶轮路径视觉无明显问题，本轮不追加几何精度优化。Skills：开发、验证、computer-use。

2026-09-27 V2-02叶轮代表案例GUI链完成：导出NC request1首次加载complete，worker403.274s、端到端407.922s、cache_hit=false。实际显示全部沉积、打开橙色空移、下拉操作2、缩放并拖动旋转、下一阶段到操作3，单叶片及转场可见且操作响应；v2_02_impeller_nc_travel.png、stage2_rotated.png、stage3.png及nc_preview_summary.json。NC页未单独加载STEP的Warning解释明确，不是生成Error。输入保存重开、生成六件套与严格回读证据已齐，本例不再重复生成或精度优化。首次NC加载较慢如实保留，不宣称快速。V2-02整体仍待三叶/多色案例；V2-04剩余9图5组、V2-05最终回归/安装包启动/CI继续。Skills：开发、验证、computer-use。

2026-09-27 V2-02三叶扇多色当前流程启动：复制历史输入到three_color_current150_gui_project后真实GUI打开，取消残留Placement草稿，应用内置150mm机型并重新应用零微调装夹，树恢复有效。实际打开材料表核对T0/T1/T2（v2_02_three_color_materials.png），取消未修改的表格后点击生成与检查。当前generation_in_progress=true、last_error=null，进程2448响应正常；状态v2_02_three_color_generating_state.json。保存参数为层高0.4mm、采样0.8mm，未为加速改成历史粗参数。生成、导出和回读尚待完成，不提前计为通过。使用Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use；本次调用登记。


2026-09-27 V2-03完成：按计划逐项复核明确生成状态、空结果取消、校徽有效结果取消保留、索引检查点25项回归、修复后81万点叶轮生成期间显隐/语言/对话框响应、完整NC路线与工序过滤/旋转/放大真实操作。证据映射见v2_03_v2_05_remaining_current.md。首次无缓存NC载入407.922秒保留为性能限制，不宣称快速或所有阶段相同取消延迟；不因该限制新增优化门槛。V2-04当前角色图IMG027已替换，两指南如实说明生成期间设置及角色待核对，累计21图50引用，剩余8图4组；最短操作见next_capture_steps.md。三叶扇换料站实际打开核对并取消未修改草稿，v2_02_three_color_station.png；生成仍在运行，未重启。V2-05独立新venv tmp/v2_wheel_install_final已启动最终候选wheel安装，session90351，结果待核对；未修改运行中GUI环境。Skills：开发、验证、computer-use。PRODUCT-01仍进行中。


2026-09-27 V2-05最终候选wheel独立安装通过：session90351退出0，全新tmp/v2_wheel_install_final不继承系统site-packages；pip check输出No broken requirements found。清除PYTHONPATH后导入来自该环境Lib/site-packages，direct_url记录wheel SHA256为6402ac8d6b08bdffa36bebfb52f33a9a2f0e0fd301ae8985697fe7f06ba400a9，与候选包一致，证据v2_05_final_wheel_install.log及v2_05_final_wheel_installed.json。尚需实际启动、最终串行回归及最终提交CI，不提前关闭V2-05。三叶扇原任务仍generation_in_progress且无last_error，未重启。使用Skills：five-axis-slicer-validation、five-axis-workbench-development。


2026-09-27 V2-05最终候选wheel实际短流程完成：独立环境真实启动窗口787998（session76309、端口8766；原三叶扇窗口53152702端口8765继续运行）。打开tutorial_rotary_limits_reference，实际生成得到acceleration_limit_exceeded且导出禁用；角速度改0.1rad/s、空移300mm/min并应用、再生成恢复Warning和导出。真实导出tutorial_rotary_wheel_export六文件，manifest严格回读75/75点通过，坐标/挤出/进给/顺序差异均空。真实保存tutorial_rotary_wheel_saved并重开，参数恢复，界面Stale及导出禁用符合输入恢复合同。截图v2_05_final_wheel_started.png、v2_04_rotary_acceleration_error_raw.png、recovered_raw.png、reopened_raw.png（后三者均v2_04_rotary前缀），生成状态v2_05_wheel_rotary_generated_state.json。错误/恢复/重开图交教程Agent替换，尚不预填替换数。该独立参考机型仅教学离线验证，不修改真实公共机型，也不证明上机资格。V2-05仍待最终回归及提交CI；Skills：开发、验证、computer-use。


2026-09-27 V2-04教程补拍继续：独立wheel窗口实际选择圆柱平端面并点击应用，显示rotary.surface_reference_invalid且生成/导出禁用，截图v2_04_rotary_flat_face_rejected_raw.png；仅证明平端面拒绝，不称本轮已测试叶片拒绝。Curve实际点击两条相邻边及顶面，截图v2_04_curve_edges_normal_face_raw.png；采用后v2_04_curve_edges_adopted_raw.png为未应用草稿，边序0008/0012且默认反向0/0，教程需明确方向仍需核对，不称路径已生成。两组交教程Agent更新；此前累计25旧图55引用，新增替换尚待完成。三叶扇原进程2448本轮只读确认Responding=true、CPU3537.30s、generation_in_progress=true、last_error=null，继续原计算。Skill实际调用：computer-use；沿用开发与验证流程。目标保持active。

2026-09-27 V2-04最后场景已真实生成：先完成IMG003/033替换，累计27图59引用、218本地链接有效。独立wheel GUI新建Rotary Around Part，实际点选侧面face0001与轴向边edge0002并采用，输入350:20;120:210、CCW，应用由CAD解析R20/H20后生成WARNING、导出可用。保留默认轴步2mm、采样5°、进给900/空移1800mm/min、角速度0.5rad/s，并未使用建议草案的缩小参数；本例仅离线教程。隐藏模型并放大，真实截图v2_04_rotary_around_two_regions_raw.png同时显示两分离蓝色区域与跨零输入；状态v2_04_rotary_around_generated_state.json确认crosses_zero分别true/false。无空移显示，不称截图显示旅行连接。交Agent替换最后IMG025/035并最终核链，完成前不关闭V2-04。三叶扇原进程2448仍Responding=true、CPU3998.97s、生成中无last_error，未重启。使用Skills：computer-use，沿用开发/验证流程。

2026-09-27发行收口核对：教程累计29原图/66引用已替换、48唯一原图均有处置；主线程运行audit_guide_images.py退出0，当前84图片引用missing0，23低对比度仅人工候选，不自动判失败。教程Agent正迁移6张已无指南引用的旧过程标记图并完成最终说明，尚不提前关闭V2-04。独立wheel窗口已实际点击关闭，session76309退出0；三叶扇原窗口继续，v2_02_three_color_stack_followup.txt显示从freeform_product.py:285空移规划推进到:320空移安全检查，当前生成中无last_error，不重启。提交候选v2_05_commit_candidates.json列249项及排除项，尚未暂存/提交；git ls-remote核实远端master仍edacd49。gh未登录但已有GitHub连接工具可核对CI，不因此提前判阻塞。全仓回归待运行中GUI验收完成后串行执行，避免QSettings相互影响。使用Skills：five-axis-slicer-validation、five-axis-workbench-development、computer-use。

2026-09-27 V2-04关闭：主线程复核v2_04_final_closure.md与final_disposition.json，原始83引用及15低对比候选均有最终处置；29原图66引用替换、16编号图+3普通链接图按用途保留，48唯一原图覆盖完整。6张退役过程标记图迁移后逐项SHA一致且旧assets路径不存在，8份过程JSON迁移有清单。218本地链接有效，84内嵌图missing0。两处非关键光晕按计划§8保留并明确记录，不称绝无光晕；英文复用中文图有说明。主表PRODUCT-01/V2C同步当前状态，V2-01/03/04完成、V2-02/05未关闭。使用Skills：five-axis-workbench-development阶段门槛、five-axis-slicer-validation；证据不替代实机验收。

2026-09-27 V2-02三叶扇多色生成完成：原进程2448生成结束、last_error=null，真实GUI显示路径、Warning及可用导出。v2_02_three_color_completed_state.json确认offline_exportable=true、machine_executable=false，strict readback340193/340193点、62716/62716事件、issues为空。实际点击导出到three_color_current150_gui_export，六文件已落盘（main.gcode59135880、toolpath.json330029556、preview.json236696908、manifest.json1522272、machine_axes.csv38330179、warnings.json1418956字节）；generated截图已保存，磁盘独立摘要及哈希由Agent核对。尝试Ctrl+S时工具报告用户正在操作，刷新确认用户在放大查看，故未继续抢输入；当前保存重开及NC空移/工序可视核验待做，不预报V2-02关闭。使用Skills：computer-use、开发与验证。目标active。

2026-09-27 V2-02三叶扇闭环完成：用户目视确认路径无问题，停止形状优化。实际Ctrl+S保存three_color_completed150_gui_project/project.json并用打开项目重开；reopen_comparison确认operations、controller和source_hash一致、无last_error，产品缓存不持久化，重新打开后导出禁用符合合同。真实打开当前六件套main.gcode，首次加载161.578204秒、worker158.543572秒；实际选择全部工序、放大、空移开关、旋转、操作1基体与操作2叶片过滤，截图及nc_preview_state已归档。磁盘独立核对340193点、62716事件，XYZAC无超限差异，T0→T1→T2和两次完整换料动作一致，4142条Warning、0条Error；见v2_02_three_color_disk_audit.json与export_hashes.json。GUI正常关闭，session4797退出0。V2-02完成，PRODUCT-01仍待V2-05最终回归与提交CI；machine_executable=false。沿用Skills：computer-use、five-axis-workbench-development、five-axis-slicer-validation。

2026-09-27 V2-05最终回归首次失败记录：session67271在90%附近以0xc0000005退出，Windows事件1000指向nvoglv64.dll；单独test_home_gcode_viewer_entry_opens_empty_result_preview同样崩溃，故不是仅全仓累积资源问题。栈为构造Tube页面刷新平台→VtkModelViewer.render直接native Render。依据VTK官方QVTKRenderWindowInteractor实现（https://raw.githubusercontent.com/Kitware/VTK/v9.3.1/Wrapping/Python/vtkmodules/qt/QVTKRenderWindowInteractor.py），普通刷新改super().Render()交Qt update/paint调度，render_scene_image同步截图渲染保持；原崩溃用例修复后通过。另两项普通失败分别为Curve语言测试替身缺_t、连续Tube算法版本断言仍v2；补齐测试接口、对齐已实际使用的v3，原结果和语言断言保留。一次双项复测因默认系统临时目录WinError5未运行Tube，改用项目内独立basetemp后定位到版本断言。相关四文件回归含真实VTK离屏绘图正在串行执行，未提前称通过；原失败日志保留。发行wheel需随viewer源码修复重新构建匹配。Skills沿用开发、验证；VTK生命周期只读Agent提供源码依据，无驱动或系统配置修改。

2026-09-27渲染修复后验证：v2_05_targeted_final为30 passed、4 subtests passed，包含Curve、连续Tube完整导出、主界面状态和VTK真实离屏绘图；v2_05_quality_after_render_fix退出0。v2_release_render_fix的wheel/sdist构建及Twine均通过，220源文件与wheel逐字节一致，wheel SHA256=8cfb343f0bdcc535d1b80e2dc527f0723559fdc9a9e7ff4943f4f76dc44b1fd8；独立venv无依赖重装此wheel、pip check通过。完整回归session24505仍运行，尚无终态，不计最终通过。证据为v2_05_package_render_fix.json、install_render_fix.log、full_after_render_fix.log。

2026-09-27发行回归补充：完整回归session24505在95%后因QApplication.setStyle(Fusion)反复刷新全应用控件达到180秒超时，退出1，非通过。依据Qt QApplication.setStyle官方文档与当前栈，已有Fusion时不重复设置全局样式；公共设置及主界面专项45 passed、4 subtests passed，30.13秒，保留180秒门槛。完整回归session37975进行中。提交da82276已推送，CI36314354446原生smoke通过，其余三任务同在Mypy失败：workbench_issue_ui的item可空与Qt.UserRole类型声明。改直接构造QListWidgetItem、使用Qt.ItemDataRole.UserRole，不改变诊断内容；本地quality_style_fix退出0，独立环境类型核查和必要运行回归继续。V2-05仍未完成；da82276包已构建，但后续两处源码修复需更新最终版本映射。

2026-09-27 最终收口：完整回归session37975退出0，1280 passed、3 skipped、146 subtests passed，366.80秒（v2_05_full_style_fix.log/xml）；3项均为Windows符号链接WinError1314。诊断列表类型修正在全回归启动后完成，因此补跑当前代码36 passed（v2_05_diagnostic_types_final），不将早先全回归冒称覆盖该后续改动。质量脚本及独立类型检查通过。源码提交d3a2b50bfd3d23d061b33318d42ae87e22e72988已推送，CI36314845862四项全部成功，GitHub连接器再次核实并归档v2_05_ci_d3a2b50_verified.json。

最终包tmp/v2_release_d3a2b50的wheel与sdist构建及Twine通过，包内220个Python文件与提交和当前源码逐字节一致；SHA及文件大小见v2_05_package_d3a2b50.json。独立环境重新安装此wheel、pip check通过，实际启动首页、点击NC入口并切英文，截图v2_05_d3a2b50_installed_home.png及preview_en.png；正常关闭session87012退出0。此前隔离包的Rotary错误恢复、生成、六件套75/75回读及保存重开按差异验收复用：后续变更仅VTK渲染调度、重复全局样式、诊断项类型，相关回归及最新包真实入口已补验；未声称重新生成四个大案例。发行包固定对应d3a2b50，后续文档证据归档提交不改变源码，不为文档提交重新跑整件或重建同源码包。

V2-01—V2-05离线门槛满足，主表PRODUCT-01/PRODUCT-01-V2C关闭，最终判据见evidence/2026-09-26_v2_final_delivery/completion_audit.md。保留machine_executable=false、首次大NC载入缓慢、微小接缝精度及两处非关键光晕；实机标定和试打另行验证。用户已接受叶轮和三叶路径，不继续形状优化。此次复用Skills：five-axis-workbench-development、five-axis-slicer-validation、computer-use；可复用经验是Qt构造阶段使用事件调度渲染、避免反复替换应用级样式，以及源码/安装包逐文件映射。
