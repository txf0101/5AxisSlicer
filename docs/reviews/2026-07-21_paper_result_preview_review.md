# 2026-07-21 论文级切片成果预览页复盘

## 1 对象与来源证据

本轮对象为 `5AxisSclicer V2.0` 的论文级切片成果预览页。动手前已核对 `README.md`、`docs/project_structure.md`、OpenGL 预览复盘、AC 反算复盘、叶轮模型与路径成图复盘，以及工作区中尚未提交的 `ui.py`、`localization.py` 和 `test_ui_state.py`。原有修改均按增量方式保留。

验收数据取自下列文件：

- STEP：`example/叶轮/叶轮.stp`，454,267 B，修改时间 2026-05-25 11:28:49，SHA-256 为 `3776fe6e1c384e03a7dab20e7ab8d8028210b86ec7c2ced3d3518a8011fdf21f`。
- G-code：`example/叶轮/叶轮完整.gcode`，62,753,499 B，1,021,062 行，修改时间 2026-07-01 15:49:32，SHA-256 为 `5b33b1fa3569f2027e7628c0b7211e125267fc73b25e88e6b774cb1de338fe33`。
- 视觉参考图：用户提供的 `b524d5e0de405e373e30a17f3c56a10b.png`，703,633 B，SHA-256 为 `28fba3b49b6a8e7525a0850ba69f866d8e9f0a6a835c455a487c7c04dc99df58`；验收副本归档在包资源 `src/five_axis_slicer/assets/impeller_four_panel_reference.png`，并由 `pyproject.toml` 的 package data 规则纳入发布包。
- 连续路径对照：`example/叶轮/render_outputs_16k_continuous/impeller_model_real_gcode_toolpath.png`。

五轴坐标口径沿用 MATLAB 与 Python 已核对的公式：

\[
P_{part}=R_z(-C)R_x(-A)P_{machine}.
\]

深度偏移仅写入 OpenGL 裁剪空间，源坐标、段数和审计统计保持原值。

## 2 实现组织

成果页与既有 Workbench、Operation Session 并列，`ui.py` 保留应用壳、导航、共享动作和自动化调度。数据状态、后台加载、源代码索引、页面组件与论文导出分别放入独立模块。该边界限制了主窗口继续膨胀，也使加载取消、代码检索和图像合成可以单独测试。

`ResultPreviewState` 保存来源选择、有效来源、五类状态、工艺参数记录和显隐设置。加载结果只有在状态为 `loading` 且请求标识一致时才可提交；替代请求立即屏蔽旧信号。失败、取消和陈旧结果均不会清除已提交场景。工艺参数位于独立命名空间，参数保存没有调用 G-code 解析器。`IllustrativeProcessParameters` 类名和 `parameters_affect_toolpath=false` 继续承担旧项目兼容及审计职责，均未进入可见文案。

大文件代码区采用 mmap 与 uint64 行偏移表。页面只读取当前行前后各 20 行，代码搜索在线程池执行。索引同时识别 `;叶轮1` 至 `;叶轮8`，普通文件回退到全部路径和层范围。STEP、G-code 与 mmap 来源签名均按 1 MiB 分块计算 SHA-256，哈希和拓扑枚举之间设置取消检查点。大 G-code 缓存采用生成号 NPZ 与原子 manifest；manifest 替换成功前，旧缓存仍可读取。

交互质量继续使用原有 LOD。论文质量直接读取完整 timeline 数组，以 `deltaE > 0` 选择正挤出段，0.02 mm 连续性容差得到 3,362 条 polyline，渲染段数为 1,005,400。路径数组约 26.96 MB，构建测试耗时 0.10 s。模型用中性灰色，正挤出路径用蓝色，起点和终点分别使用绿色与红色。

论文导出在 1920 × 1080 逻辑尺寸下重新布局主窗口，Qt 控件按 2 倍绘制，OpenGL 场景由 FBO 单独捕获。合成阶段重新绘制工具轨、Part XYZ、方向立方体和起终点图例，避免 FBO 覆盖 Qt 叠加层。PNG 合同包含 3840 × 2160 像素、sRGB、300 dpi、不透明 RGB 背景；同名 JSON 记录来源哈希、统计、相机、显隐和渲染参数。PNG 与 JSON 使用可回滚的成对提交，同名产物还由操作系统文件锁串行化，两个应用进程不会交叉安装各自的图像和审计文件。

方向立方体的 `TOP`、`FRONT`、`RIGHT` 字形先由 `QPainterPath` 构造，再用 `QTransform.quadToQuad` 投影到三个可见面内。面多边形仍负责鼠标命中，文字投影没有改动原有点击区域。Windows Qt 可见桌面实测中，三组字形随面透视贴合，顶面、前面和右面的点击结果分别保持为 `top`、`front` 和 `right`。

导出排队后由应用级事件过滤器冻结成果页输入，主窗口动作另设统一门禁。语言、页面导航、视角、显隐、质量、文件对话框和项目保存均不能在捕获期间改变画面。事件过滤器不创建覆盖控件，锁定前后的 `QWidget.render()` 像素保持一致；导出结束后恢复原语言、交互质量和显隐状态。

## 3 数据核对

真实叶轮成果页返回的数据如下。

| 项目 | 结果 |
|---|---:|
| Body | 9 |
| Edge | 206 |
| 底座层 | 220 |
| 叶片阶段 | 8 |
| 空间运动段 | 1,011,023 |
| 正挤出段 | 1,005,400 |
| 空走或非挤出段 | 5,623 |
| A 轴范围 | [0, 90]° |
| C 轴范围 | [-344.100006104, 135.559997559]° |

上述结果同时写入中英文 sidecar。G-code 代表行固定为第 146,983 行，原文为 `G1 F600 X0.000 Y-42.000 Z22.200 A90.000 C-162.000 E0`，包含 F、XYZ、A/C 和 E 字段。

## 4 桌面与自动化验证

真实桌面进程使用 `C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe` 启动，渲染后端为 OpenGL。缓存迁移后的首次加载用于建立用户级缓存，worker 时间为 54.960929 s，端到端提交时间为 60.750140 s；最终 warm cache 验收明确返回 `cache_hit: true`，worker 时间为 4.461045 s，端到端提交时间为 7.333978 s，缓存格式为 `json.gz+npz-render-index-v2`。加载期间状态查询和取消入口仍由主线程响应。

可见桌面条件下，1280 × 720 交互 FBO 的平均绘制时间为 15.527417 ms/frame，对应 64.402 FPS；本轮隐藏窗口自动化复测为 20.017633 ms/frame，对应 49.956 FPS。最新严格导出的论文质量准备时间为 0.115417 s，中英文总导出耗时为 1.781291 s。完整回归共执行 94 项测试，结果全部通过。测试集覆盖翻译键及占位符对称、正式产品文案、参数保存、后台成功与失败、取消与替代、分块哈希取消、陈旧结果、不可协作 STEP 关闭、页面提交回滚、加载与导出互斥、导出交互门禁、源代码索引、阶段识别、包资源发布、用户级缓存与写失败降级、内容哈希缓存键、项目 JSON 兼容、三栏页面、窄栏中英文布局、长来源名省略、代码窗口、OpenGL 与 VTK 模型几何清理、OpenGL 全量路径门槛、加载时来源快照、跨进程产物锁、双文件提交恢复、方向立方体投影与点击热区、叠加层恢复、四张独立论文图及 4K sidecar。

## 5 同轮视觉核查

初版严格导出暴露了两项画面问题：默认相机俯角偏高，百万段路径在 4 px 线宽下形成蓝色块面；FBO 后合成覆盖了 Qt 绘制的坐标轴与方向立方体。修订后降低观察仰角，缩短相机距离，将论文线宽控制在约 1.4 px，并调整视觉深度偏移。灰色模型轮廓、蓝色层线和叶片空间关系均可辨认。Qt 叠加层改为场景合成后的独立重绘，最终图可见工具轨、Part XYZ、方向立方体、起终点图例和真实代码窗口。方向立方体的三组字形经四边形变换贴合对应面，Windows Qt 实测没有改变六面视角入口的点击热区。底部状态栏固定为“就绪 / Ready”，瞬时导出提示不再进入正式插图。

参考图的四类证据改为四张独立 3840 × 2160 PNG，由用户在论文排版阶段自行拼版。a 图为中文成果总览，b 图为输入文件与工艺参数，c 图来自真实 OpenGL FBO 并叠加 Qt 工具轨、方向立方体、Part XYZ 和起终点图例，d 图直接读取第 146,983 行附近的真实 G-code，并沿用 F、XYZ、A/C、E 四组语法颜色。每张图的 sidecar 均记录 `caption_baked=false`；汇总 manifest 记录 `precomposed_grid_generated=false` 和固定顺序 `a、b、c、d`。

c 图的审计记录为 `backend=opengl`、`paper_quality_active=true`、`full_timeline_paper_path=true` 和 `path_render_mode=opengl_paper_full_timeline`。可见路径段与实际绘制路径段均为 1,005,400，几何统计为 9 个 body、206 条 edge。该记录把 OpenGL 全量路径场景与 Qt overlays 的最终成图关联到同一份 sidecar，未采用总览界面裁切或复合图反裁。

## 6 价值判断与可复用方法

本轮较有价值的部分是将论文图与源文件证据绑定。界面统计来自解析对象，代码窗口来自 mmap 源文件，成图参数来自渲染快照，PNG 与 JSON 互相记录哈希。STEP、G-code 和参考图在加载时形成内容快照，严格导出会在写图前复核当前磁盘文件；源文件变化、后端缺少全量 timeline 能力、交互状态漂移或双文件提交失败均会中止正式产物。同名导出加入跨进程锁后，证据链还覆盖并发写入边界。任一数字出现偏差时，可沿“源文件、解析摘要、timeline 数组、渲染快照、图像产物”逐层定位，避免只凭截图判断路径是否完整。

原子状态提交和生成号缓存适用于后续扇叶、球面校徽与管件样例。完整 timeline 与交互 LOD 分离的做法也可复用于局部路径放大、轴限位检查和碰撞结果叠加。独立面板导出把界面、参数、几何和代码组织成同一组物理证据，单图可单独复核、替换和排版；后续更换模型时可沿用同一份 manifest 与 sidecar 结构。

可复核链条与真实百万段渲染构成本轮的差异化。源文件行号、运动学公式、段数锚点、OpenGL 全量数组和 PNG 元数据均进入自动化检查，其他模型迁移时可以复用同一验收方法。

## 7 已知边界

- “解析 G-code”动作读取已导入路径；从 STEP 生成新的完整五轴路径属于后续算法阶段。
- TCP、回转中心标定、碰撞检查、打印时间及耗材估算未进入本轮统计。
- 正式论文图以 OpenGL FBO 为验收后端；严格模式拒绝 VTK 或缺少全量 timeline 能力的后端。非严格诊断导出仍可使用降级后端，并在 sidecar 记录原因。
- 全量正挤出路径在总览尺度下仍会形成局部密集蓝面，局部层纹分析应使用放大图或现有 16K 连续路径产物。
- 左右栏在 1600 × 900 下允许内部滚动。总览图固定展示状态、统计、缩略图和代码区上部，完整导出控件可在应用内滚动查看。
- PNG 写入标准 sRGB 块，当前未嵌入独立 ICC profile；若投稿平台明确要求 ICC 文件，还需按目标规范补充。
- PNG 与 JSON 的成对回滚可处理常规写入和重命名异常；若进程在两次目标文件替换之间被操作系统强制终止，文件系统无法提供跨文件的单事务提交。下次正常导出会重新生成并覆盖完整文件对。
- 四张独立面板没有内置 `(a)` 至 `(d)` 子图题注，用户拼版时需按论文版式补入题注并保持 manifest 规定的顺序。现有历史 composite 仍保留在输出目录，当前交付清单和哈希核对不再采用该文件。

## 8 产物

- `outputs/paper_preview_acceptance/impeller_result_preview_zh_3840x2160.png`
- `outputs/paper_preview_acceptance/impeller_result_preview_zh_3840x2160.json`
- `outputs/paper_preview_acceptance/impeller_result_preview_en_3840x2160.png`
- `outputs/paper_preview_acceptance/impeller_result_preview_en_3840x2160.json`
- `outputs/paper_preview_acceptance/individual_panels/impeller_paper_panel_a_overall_zh_3840x2160.png`
- `outputs/paper_preview_acceptance/individual_panels/impeller_paper_panel_a_overall_zh_3840x2160.json`
- `outputs/paper_preview_acceptance/individual_panels/impeller_paper_panel_b_process_settings_zh_3840x2160.png`
- `outputs/paper_preview_acceptance/individual_panels/impeller_paper_panel_b_process_settings_zh_3840x2160.json`
- `outputs/paper_preview_acceptance/individual_panels/impeller_paper_panel_c_five_axis_toolpath_zh_3840x2160.png`
- `outputs/paper_preview_acceptance/individual_panels/impeller_paper_panel_c_five_axis_toolpath_zh_3840x2160.json`
- `outputs/paper_preview_acceptance/individual_panels/impeller_paper_panel_d_machine_gcode_zh_3840x2160.png`
- `outputs/paper_preview_acceptance/individual_panels/impeller_paper_panel_d_machine_gcode_zh_3840x2160.json`
- `outputs/paper_preview_acceptance/individual_panels/impeller_paper_panels_zh_manifest.json`

最终 PNG 均为 3840 × 2160、8-bit RGB、sRGB、11811 px/m，不含 Alpha 通道。a 图按审计总览作同一性复制，故字节数和 SHA-256 与中文总览一致。四张独立面板没有烘焙子图题注，汇总 manifest 明确禁止预合成网格。

| 产物 | 字节数 | SHA-256 |
|---|---:|---|
| 中文总览 | 651,743 | `c6e2faa32ac790bd8070e099c4f3ee338f415b5f9c6bb28196df73d6e793d145` |
| 英文总览 | 613,111 | `4bade4154f95b86c3da0bd42898d6d58c2ab5f299f350f8df423b0a455d6c777` |
| a 总览 | 651,743 | `c6e2faa32ac790bd8070e099c4f3ee338f415b5f9c6bb28196df73d6e793d145` |
| b 参数 | 123,497 | `23b35a829bfd7c0a6ecdefd88ec90b889289a7064ee94ff13af9e24dfc92d9d4` |
| c 五轴路径 | 567,540 | `b28f3657e6f0ac50ab2c55e8a25dbe755a4576cea87c2da71473420b284a0cde` |
| d 真实 G-code | 322,470 | `326bda2051cd6de5a7c2861ee34116f027666f587d8e6660c94062b8021e456d` |

目录中原有 `impeller_four_panel_paper_preview_zh_3840x2160.png` 及同名 JSON 作为历史 composite 保留，未删除，也未列入本次交付与最终哈希表。

## 9 窄栏遮挡修订

1600 × 900 主窗口中的成果页实际高度为 792 px，左栏 viewport 宽度为 269 px。初版参数按钮采用单行排列，英文按钮、横排参数标题和数值输入框共同抬高了布局最小宽度；包内参考图文件名属于无空格长字符串，又将真实内容宽度推至 480 px。水平滚动条固定关闭后，超出的区域被直接裁切。1920 × 1080 逻辑导出中的 viewport 为 327 px，同一长文件名仍会产生约 153 px 的溢出。

修订后的参数卡采用单列字段，编辑与保存位于第一行，重置按钮占据第二行；标题改为上下排列，数值控件允许水平收缩。中英文按钮显示短文案，完整语义保留在 tooltip。STEP 与 G-code 使用中间省略来源标签，完整文件名、绝对路径及无障碍文本仍保存在控件中；视觉参考文件只进入审计记录，不占用左栏。真实应用样式下，中英文内容最小宽度均为 225 px；1600 × 900 与 1920 × 1080 两种布局的横向滚动范围均为 0。

回归用例分别覆盖中文、英文、两种验收尺寸及三个超长无空格来源名，同时核对中间省略字符、完整 tooltip、内容宽度和水平滚动范围。三栏 stretch 保持 `18 / 56 / 26`。参数卡增加的纵向长度仍由原定内部滚动承担，中央 FBO 尺寸和 3840 × 2160 输出合同未改变。修订后已重新导出中英文总览，并生成 a 至 d 四张独立论文图；PNG、JSON 和 manifest 的哈希、字节数、尺寸、sRGB、300 dpi、不透明 RGB、题注与拼版标志均已核对。

## 10 字号与双语完整显示修订

用户在 3840 × 2160 总览中复核发现，原字号在高分辨率画面上偏小，部分英文按钮、显隐选项与语法说明存在被截断的风险。本轮保留 1920 × 1080 逻辑布局、2 倍离屏合成和 `18 / 56 / 26` 三栏比例，新增不可变 `TypographyTokens` 作为应用级字号契约。当前 token 依次为正文与控件 15 px、次要文字 13 px、表单标签 13 px、代码 14 px、卡片标题 15 px、栏目标题 16 px、页面标题 22 px、徽标 12 px。全局 QSS 与成果页局部样式读取同一组 token，后续调整无需在多个组件内逐项改写常量。

成果页对可见文字重新划分了单行与换行边界。场景显隐项采用两列布局；统计标签允许换行；G-code 行范围单独占行；输出目录按钮独占一行。来源路径在栏内使用中间省略，tooltip 与无障碍文本保存完整绝对路径。语言切换后，页面会根据当前栏宽刷新换行标签的高度，避免旧语言的尺寸缓存压住新文本。中英文按钮、标签、组合框选项和显隐项由字体度量值参与边界检查，左右栏在验收尺寸下不产生横向滚动。

成果页移除了研发阶段说明文字，代码定位行号继续写入 sidecar。独立 G-code 面板将文件名标题与 F、XYZ、A/C、E 四组语法标签分为上下两行，标签宽度由 `QFontMetricsF` 计算。正文优先采用 22 px Cascadia Mono，并根据最长真实指令、动态行号栏和 21 行上下文逐级调整，允许范围为 18 至 22 px；最低字号仍无法完整显示时终止导出，避免产物携带被裁切的代码。

四类论文证据继续分别导出为 3840 × 2160 PNG，单图不写入 `(a)` 至 `(d)`，拼版与题注由论文编辑阶段统一处理。自动化用例覆盖中英文字号层级、按钮与标签边界、换行高度、横向滚动范围、正式产品文案、G-code 两行标题区、语法标签边界和代码正文完整性。最新完整回归为 94 项，结果全部通过。

## 11 交付文案核查

本轮按正式软件界面重新核对首页、菜单、成果页、工具提示和导出脚本。窗口标题调整为“五轴切片工作台 / 5-Axis Slicing Workbench”，首页入口使用“切片成果预览 / Slicing Result Preview”，叶轮入口、G-code 解析、加载状态、质量模式和论文图导出均按实际动作命名。单实体 STEP 的状态提示改为“作为一个制造对象处理”，避免在用户界面陈述开发阶段和范围判断。

视觉参考、缓存组织、参数作用边界与代码定位行号属于复核信息，继续保存在 sidecar、兼容字段和维护文档中。`--demo`、`/results/demo`、`IllustrativeProcessParameters` 与 `representative_gcode_line` 暂时保留，以维持自动化接口及既有 `project.json` 的读取能力。可见文案测试同时扫描标签、按钮、复选框、组合框和工具提示，并禁止研发阶段词语重新进入成果页。

## 12 英文独立图与无压缩 TIFF

2026-07-22 补充英文 a 至 d 四张独立图。a 图读取已验收英文总览，b 图按英文词典直接绘制输入文件与工艺参数，c 图重新调用 OpenGL 完整路径渲染并使用英文起终点图例，d 图读取同一 G-code 上下文并绘制英文语法标签。STEP 与 G-code 文件名保持源文件原名，界面标题、按钮、参数名称及图例使用英文，来源证据没有因语言切换而改写。

导出脚本新增 `--uncompressed-tiff`。该选项在同一渲染结果上生成 PNG 与 TIFF，TIFF 转换只改变封装格式，像素数组不缩放。四张 TIFF 均为 3840 × 2160、8-bit RGB、300 dpi，基线压缩标记为 `Compression=1`。逐像素对照结果与对应英文 PNG 完全一致；每张 TIFF 均有 `.tif.json` 审计文件，英文 manifest 的 `formats` 为 `png、tiff_uncompressed`，`precomposed_grid_generated=false`。

| 英文 TIFF | 字节数 | SHA-256 |
|---|---:|---|
| a 界面总览 | 24,883,923 | `086a1f4b8e2814414ad194e2b0ff830a7db4b85ef59601e2ce0a031419af8312` |
| b 工艺参数 | 24,883,923 | `9ed140ae5d5cd2ea1142f86badbd9c3b96bf7312821d41425ec86da47faa13bb` |
| c 五轴路径 | 24,883,923 | `49e456681c4c10ac41d2da626ef37c375ed800ca19ef65e31367c60a8153d240` |
| d 真实 G-code | 24,883,923 | `a39d434ee788dd0407008cbd66980865e273c30f0ea9e52be6e1619c4709f4d7` |

英文交付文件位于 `outputs/paper_preview_acceptance/individual_panels/`，命名后缀为 `_en_3840x2160.tif`；同目录保留英文 PNG 预览、sidecar 和 `impeller_paper_panels_en_manifest.json`。
