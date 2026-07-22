# 2026-07-09 球形 NEU 校徽论文图渲染复盘

## 源文件核对

本轮工作目录为 `example/球形NEU校徽`。处理前读取了项目说明、结构文档、叶轮渲染复盘和旧 MATLAB 脚本，确认叶轮最终版使用 `P_part = Rz(-C) * Rx(-A) * P_machine` 作为 A/C 反算公式，并采用 `legacy_full_positive` 保留全部 `deltaE > 0` 正挤出段。

源文件状态如下：

- `球形测试件(1).STEP`：修改时间 2026-05-29 12:54:55，大小 9601742 字节。
- `NEU校徽划线.gcode`：修改时间 2026-07-08 11:38:38，大小 5688471 字节。

目录内已有 `render_outputs_4k`，来自上一轮临时可见性增强渲染。本轮保留该目录。严格遮挡口径产物保存在 `render_outputs`、`render_outputs_16k_continuous` 和 `render_outputs_8k_detail_continuous`；表面示意口径产物保存在 `render_outputs_surface_schematic`、`render_outputs_16k_surface_schematic` 和 `render_outputs_8k_surface_schematic`。

## 代码口径

新增两个 MATLAB 文件：

- `example/球形NEU校徽/render_paper_model_toolpath.m`
- `example/球形NEU校徽/render_paper_model_toolpath_engine.m`

`render_paper_model_toolpath.m` 是批处理主入口，默认读取当前目录的球形 STEP 与 NEU G-code，也可通过 `userConfig` 指定新的 STEP/STP 与 G-code/NC。该入口依次生成普通论文图、16K 连续线全图，并从 16K 版本裁剪 8K 局部图。

`render_paper_model_toolpath_engine.m` 由叶轮最终脚本复制后改为通用 engine。保留的技术口径包括：

- CadQuery/OCP 将 STEP/STP 转成 STL 缓存，MATLAB `stlread` 读取三角网格。
- G-code 解析支持 `G90/G91`、`M82/M83`、`G20/G21`、`G92`、`X/Y/Z/A/C/E/F` 字段，并保留 `G2/G3` 圆弧离散入口。
- A/C 反算为先 `rotateXVector(..., -A)`，再 `rotateZVector(..., -C)`。
- 路径选择为 `legacy_full_positive`。
- `maxRealSegmentsToRender = inf`，`maxRenderedRealSegmentLength = inf`。
- `pathDisplayLift = 0.18 mm`。
- `pathJoinTolerance = 0.02 mm`。

本轮去掉了旧脚本中的 `uistack` 强制置顶动作，保留深度排序与相机方向微抬升。模型为不透明灰色实体，路径为高饱和蓝色线条。

球形件的真实路径在严格深度遮挡下被实体覆盖。为生成论文中的表面路径示意图，新增 `pathSurfaceMode = upper_z_envelope`：正挤出路径仍取自真实 G-code 和 A/C 反算结果，显示阶段按 XY 投影到 STEP/STL 的上包络表面，随后增加 `surfaceProjectionLift = 0.12 mm`。该模式保留 `legacy_full_positive`、不抽样和连续 polyline 拼接，统计文件会记录投影口径。

上一轮的 `render_spherical_neu_model_toolpath.m` 已改为兼容入口，内部转调 `render_paper_model_toolpath`。

## 输出与验证

正式运行命令：

```powershell
matlab -batch "render_paper_model_toolpath"
```

MATLAB 主渲染与写文件完成后，本机退出钩子仍打印 `Settings` 相关报错；产物和统计文件已写出。

严格遮挡普通图输出：

- `example/球形NEU校徽/render_outputs/model_real_gcode_toolpath.png`
- `example/球形NEU校徽/render_outputs/model_real_gcode_toolpath.tif`
- `example/球形NEU校徽/render_outputs/model_real_gcode_toolpath.fig`
- `example/球形NEU校徽/render_outputs/model_toolpath_stats.txt`

严格遮挡 16K 连续线全图输出：

- `example/球形NEU校徽/render_outputs_16k_continuous/model_real_gcode_toolpath.png`
- `example/球形NEU校徽/render_outputs_16k_continuous/model_real_gcode_toolpath.tif`
- `example/球形NEU校徽/render_outputs_16k_continuous/model_real_gcode_toolpath.fig`
- `example/球形NEU校徽/render_outputs_16k_continuous/model_toolpath_stats.txt`

严格遮挡 8K 局部图输出：

- `example/球形NEU校徽/render_outputs_8k_detail_continuous/model_real_gcode_detail_8k.png`
- `example/球形NEU校徽/render_outputs_8k_detail_continuous/model_real_gcode_detail_8k.tif`
- `example/球形NEU校徽/render_outputs_8k_detail_continuous/model_real_gcode_detail_preview.png`
- `example/球形NEU校徽/render_outputs_8k_detail_continuous/model_real_gcode_detail_8k_stats.txt`

表面示意普通图输出：

- `example/球形NEU校徽/render_outputs_surface_schematic/model_real_gcode_toolpath.png`
- `example/球形NEU校徽/render_outputs_surface_schematic/model_real_gcode_toolpath.tif`
- `example/球形NEU校徽/render_outputs_surface_schematic/model_real_gcode_toolpath.fig`
- `example/球形NEU校徽/render_outputs_surface_schematic/model_toolpath_stats.txt`

表面示意 16K 全图输出：

- `example/球形NEU校徽/render_outputs_16k_surface_schematic/model_real_gcode_toolpath.png`
- `example/球形NEU校徽/render_outputs_16k_surface_schematic/model_real_gcode_toolpath.tif`
- `example/球形NEU校徽/render_outputs_16k_surface_schematic/model_real_gcode_toolpath.fig`
- `example/球形NEU校徽/render_outputs_16k_surface_schematic/model_toolpath_stats.txt`

表面示意 8K 局部图输出：

- `example/球形NEU校徽/render_outputs_8k_surface_schematic/model_real_gcode_detail_8k.png`
- `example/球形NEU校徽/render_outputs_8k_surface_schematic/model_real_gcode_detail_8k.tif`
- `example/球形NEU校徽/render_outputs_8k_surface_schematic/model_real_gcode_detail_preview.png`
- `example/球形NEU校徽/render_outputs_8k_surface_schematic/model_real_gcode_detail_8k_stats.txt`

关键统计：

- STEP/STL 网格：868118 个顶点，1736157 个三角面。
- 模型包围盒：X `[-50, 50] mm`，Y `[-50, 49.9901161194] mm`，Z `[-3.49148146376e-13, 51.6777114868] mm`。
- G-code 行数：151621。
- 运动段数：145800。
- 正挤出段数：143535。
- A 轴范围：`[0, 57.4000015259] deg`。
- C 轴范围：`[-1529.94995117, 73.7099990845] deg`。
- A/C 反算后 Z 范围：`[0.20000000298, 40.0689434187] mm`。
- 表面示意普通 PNG/TIF 尺寸：4080 x 2880。
- 表面示意 16K PNG/TIF 尺寸：16320 x 11520。
- 表面示意局部 PNG/TIF 尺寸：8192 x 6276。
- 表面示意局部预览 PNG 尺寸：1800 x 1380。
- 表面示意普通图蓝色像素比例约 0.154367。
- 表面示意 16K 全图蓝色像素比例约 0.148787。
- 表面示意局部图蓝色像素比例约 0.445931。

`matlab -batch "checkcode('render_paper_model_toolpath.m'); checkcode('render_paper_model_toolpath_engine.m')"` 无 Code Analyzer 输出。

## 可见性诊断

严格叶轮遮挡口径下，当前球形源数据导出的普通图蓝色像素为 0，五个低分辨率视角试验也均为 0。模型本体非空，普通图非白像素比例约 0.492842。该结果与源数据空间范围一致：反算路径 Z 上界约 40.07 mm，STEP 顶部约 51.68 mm，完整正挤出路径主要位于不透明实体内部。

表面示意口径采用 `upper_z_envelope` 后，普通图蓝色像素比例约 0.154367，局部图线条连续，模型顶部校徽结构仍可辨认。统计文件记录 `surface_projection_enabled = 1`、`surface_projection_nan_points = 0`，投影后 Z 范围为 `[30.2199765581, 51.792204289] mm`。

该口径适合论文中说明“五轴增材路径覆盖在模型表面”的示意效果。严格三维深度关系仍由 `render_outputs` 等目录保留，表面示意图的 stats 中单独记录投影参数，避免混用。

## V2 高质量模型

用户随后替换了源模型。新文件为 `example/球形NEU校徽/球形测试件.STEP`，修改时间 2026-07-09 19:55:10，大小 4780139 字节。旧的 `球形测试件(1).STEP` 已不在当前目录。脚本默认输入已切换到新 STEP，输出目录改为：

- `example/球形NEU校徽/render_outputs_surface_schematic_v2`
- `example/球形NEU校徽/render_outputs_16k_surface_schematic_v2`
- `example/球形NEU校徽/render_outputs_8k_surface_schematic_v2`

新模型的 STL 网格统计为 179545 个顶点、358994 个三角面。G-code 文件未变化，仍为 `NEU校徽划线.gcode`，修改时间 2026-07-08 11:38:38，大小 5688471 字节。

为避免表面示意图把内部层全部投到外表面，本轮增加近表面带筛选。筛选方法为：先计算每段正挤出路径端点到上包络表面的垂向间距，取 1% 分位作为当前模型的外层偏置，再保留偏置外 0.8 mm 内的路径段。正式 v2 输出中，143535 段正挤出路径保留 42831 段，过滤 100704 段，保留比例约 0.298402。统计文件记录：

- `surface_projection_visible_only = 1`
- `surface_projection_band_mm = 0.8`
- `surface_projection_offset_percentile = 1`
- `surface_projection_gap_offset_mm = -0.655991279669`
- `surface_projection_gap_threshold_mm = 0.144008720331`
- `surface_projection_gap_bounds_mm = [-0.828890319938, 10.4576655813]`
- `surface_projection_nan_points = 0`

v2 图像核验结果如下：

- 普通 PNG/TIF 尺寸：4080 x 2880，蓝色像素比例约 0.039228。
- 16K PNG/TIF 尺寸：16320 x 11520，蓝色像素比例约 0.036347。
- 8K 局部 PNG/TIF 尺寸：8192 x 6276，蓝色像素比例约 0.085152。
- 局部预览 PNG 尺寸：1800 x 1380。
- `matlab -batch "checkcode('render_paper_model_toolpath.m'); checkcode('render_paper_model_toolpath_engine.m'); checkcode('render_spherical_neu_model_toolpath.m')"` 无 Code Analyzer 输出。

目视检查结果：蓝色路径集中在模型外表面和顶部校徽区域，内部层没有大面积铺满外表面；灰色模型主体、文字和校徽浮雕仍可辨认，局部放大图中线条保持连续。

## 方法沉淀

本轮把叶轮图的最终做法拆成两层：engine 负责网格、G-code、A/C 反算、深度渲染和可选表面投影；主入口负责多分辨率批处理、16K 到 8K 裁剪、像素尺寸记录和输出目录管理。这个结构适合后续更换 STEP/STP 与 G-code/NC，同时保留来源文件时间戳、路径段数、A/C 范围、投影模式和图像尺寸，便于论文插图复核。

## V2 Z 向 180 度旋转修正

用户复核 v2 图像方向后指出，模型需要绕 Z 方向并围绕中心旋转 180 度。2026-07-09 20:22 后的修正把该角度写入 `render_paper_model_toolpath.m` 默认配置，并传递给 `render_paper_model_toolpath_engine.m`：

- `visualRotationZDeg = 180`
- `visualRotationCenterMode = mesh_bounds_center`
- `visualRotationCenterXY = []`

engine 在完成 STEP/STL 网格读取和 G-code A/C 反算后，仅对可视化用网格顶点与路径端点执行 Z 向旋转。A/C 反算公式、`legacy_full_positive` 选段口径、近表面带筛选、表面投影和路径连续拼接参数均未改变。本次实际使用的旋转中心记录为 `[0, -0.00395393371582]`，来自新 STEP 网格包围盒中心。

本轮覆盖生成当前 v2 目录中的同名产物，保留目录结构如下：

- `example/球形NEU校徽/render_outputs_surface_schematic_v2`
- `example/球形NEU校徽/render_outputs_16k_surface_schematic_v2`
- `example/球形NEU校徽/render_outputs_8k_surface_schematic_v2`

源文件核对结果保持为：`球形测试件.STEP` 修改时间 2026-07-09 19:55:10，大小 4780139 字节；`NEU校徽划线.gcode` 修改时间 2026-07-08 11:38:38，大小 5688471 字节。统计文件新增 `visual_rotation_z_deg`、`visual_rotation_center_mode`、`visual_rotation_center_xy_config` 和 `visual_rotation_center_xy_used` 字段，便于后续复现实验口径。

独立图像读取核验结果：

- 普通 PNG/TIF 尺寸为 4080 x 2880，普通 PNG 抽样蓝色像素比例约 0.103103，非白像素比例约 0.494219。
- 16K PNG/TIF 尺寸为 16320 x 11520。
- 8K 局部 PNG/TIF 尺寸为 8192 x 6276，局部预览 PNG 尺寸为 1800 x 1380。
- 局部预览抽样蓝色像素比例约 0.227061，非白像素比例约 0.978653。
- `checkcode` 对三个 MATLAB 脚本均无输出。

目视检查显示，NEU 字样和顶部校徽已处于旋转修正后的朝向；蓝色路径保留在外表面和顶部可见区域，灰色模型主体、浮雕文字和校徽结构仍可辨认，局部放大图中连续路径没有被裁剪成大段空缺。

## 2026-07-10 字形套准角度试验

用户继续复核后指出，关键问题在于灰色模型浮雕文字与蓝色 G-code 字形需要套准。上一轮 `visualRotationZDeg = 180` 属于画面整体旋转，模型与路径一起转动，相对位置保持不变，无法修正字形错位。为把视角与坐标套准分开，本轮在 engine 中新增模型相对路径旋转字段：

- `modelAlignmentRotationZDeg`
- `modelAlignmentRotationCenterMode`
- `modelAlignmentRotationCenterXY`

engine 当前顺序为：读取 STEP/STL 网格后，先按 `modelAlignmentRotationZDeg` 旋转灰色模型；真实 G-code 仍按已验证公式 `P_part = Rz(-C) * Rx(-A) * P_machine` 反算；表面示意投影使用旋转后的模型上包络；随后再按 `visualRotationZDeg` 对模型和路径做整体画面旋转。这样可以单独评价模型坐标系与 G-code 坐标系之间的 Z 向偏差。

角度试验目录为 `example/球形NEU校徽/render_outputs_angle_trials`。本轮生成了 0 至 345 度、步长 15 度的候选预览，并围绕 180 度补充 170、175、185、190 度细化试验。候选图仅用于诊断，清理后保留 PNG、stats 和拼图，删除了重复 STL 缓存、TIF 与 FIG 中间产物。保留的拼图包括：

- `model_alignment_z_15deg_full_contact_sheet.png`
- `model_alignment_z_15deg_front_text_contact_sheet.png`
- `model_alignment_z_fine_front_text_contact_sheet.png`

角度判断采用两类证据。目视上，180 度候选中前排 `NORTHEASTERN 1923` 的灰色浮雕与蓝色路径覆盖处在同一环带，顶部校徽的路径覆盖也更连贯。统计上，表面近邻筛选保留的路径段数在 180 度处最高：

- 150 度：47192 段，保留比例 0.328784。
- 170 度：47361 段，保留比例 0.329961。
- 175 度：47878 段，保留比例 0.333563。
- 180 度：49606 段，保留比例 0.345602。
- 185 度：47371 段，保留比例 0.330031。
- 190 度：46895 段，保留比例 0.326715。
- 195 度：47417 段，保留比例 0.330351。

正式 v2 图随后覆盖生成，配置为：

- `modelAlignmentRotationZDeg = 180`
- `modelAlignmentRotationCenterMode = mesh_bounds_center`
- `modelAlignmentRotationCenterXY = []`
- `visualRotationZDeg = 180`
- `pathSurfaceMode = upper_z_envelope`
- `pathDisplayLift = 0.18 mm`
- `pathJoinTolerance = 0.02 mm`

正式统计文件记录的模型相对旋转中心为 `[0, -0.00395393371582]`，整体画面旋转中心同为 `[0, -0.00395393371582]`。普通图与 16K 图的 `surface_projection_kept_segments` 均为 49606，`surface_projection_kept_ratio = 0.34560211795`。

独立图像读取结果如下：

- 普通 PNG/TIF：4080 x 2880。
- 16K PNG/TIF：16320 x 11520。
- 8K 局部 PNG/TIF：8192 x 6276。
- 局部预览 PNG：1800 x 1380。
- 普通 PNG 抽样蓝色像素比例约 0.144906，非白像素比例约 0.494295。
- 局部预览抽样蓝色像素比例约 0.251775，非白像素比例约 0.978815。

`checkcode` 对 `render_paper_model_toolpath.m`、`render_paper_model_toolpath_engine.m` 和 `render_spherical_neu_model_toolpath.m` 均无输出。正式普通图和局部预览目视检查显示，模型本体可见，蓝色路径集中在外表面和文字区域，局部放大图线条保持连续，背面路径没有形成整体穿透。

## 2026-07-10 Custom 末层描线路径修正

用户提供实物照片后，图像问题被重新定位为路径选段口径错误。照片中的蓝色材料只对应模型顶层的校徽、文字、外圈和小图案描线；G-code 文件同时包含白色基体的内壁、外壁、底面、稀疏填充、实体填充和桥接路径。上一版按所有正挤出段绘制蓝色路径，导致基体成型路径也被染成蓝色，画面出现大面积密集线。

本轮先读取 `NEU校徽划线.gcode` 的注释与层信息，得到以下统计：

- G-code 行数：151621。
- 运动段数：145800。
- `Custom` 正挤出段：38917，正挤出量约 147.030572。
- `Inner wall` 正挤出段：47416，正挤出量约 2148.405240。
- `Outer wall` 正挤出段：24236，正挤出量约 1094.678740。
- `Internal solid infill` 正挤出段：22837，正挤出量约 1994.616737。
- `Sparse infill` 正挤出段：9161，正挤出量约 2674.514241。
- `Custom` 被选中的层号：167。

engine 增加了 `;TYPE:` 注释和层号解析，保留每个运动段的 `featureTypeId` 与 `layerIndex`。正式渲染改用如下配置：

- `realPathSelectionMode = feature_positive`
- `realPathFeatureTypes = {Custom}`
- `realPathFeatureLayerMode = last`
- `pathSurfaceMode = none`
- `pathDisplayLift = 0.18 mm`
- `pathJoinTolerance = 0.02 mm`
- `modelAlignmentRotationZDeg = 180`
- `visualRotationZDeg = 180`

选段逻辑从 G-code 注释直接定位 Custom 末层描线，避免把白色基体的内外壁和填充路径画成蓝色。由于 Custom 路径本身已处于表面附近，最终版关闭 `upper_z_envelope` 投影，保留 A/C 反算后的真实几何轨迹，并使用相机方向微抬升处理表面重合处的闪烁。该处理使外圈、文字和校徽线条比投影版本更顺直，也更接近实物照片中的蓝色胶线。

正式输出覆盖当前 v2 三个目录，诊断用角度与预览目录已删除，仅保留最终产物。核验结果如下：

- 普通 PNG/TIF：4080 x 2880。
- 16K PNG/TIF：16320 x 11520。
- 8K 局部 PNG/TIF：8192 x 6276。
- 局部预览 PNG：1800 x 1380。
- 普通 PNG 抽样蓝色像素比例约 0.032401，非白像素比例约 0.493654。
- 局部预览抽样蓝色像素比例约 0.082514，非白像素比例约 0.977783。
- 普通图与 16K 图 stats 均记录 `selected_positive_extrusion_segments = 38917`、`selected_layer_bounds = [167, 167]`、`surface_projection_enabled = 0`。
- `checkcode` 对三个 MATLAB 脚本均无输出。

本轮沉淀的关键做法是把“物理上应显示的蓝色实验材料路径”绑定到 G-code 的 `Custom` 特征与末层层号，避免依赖所有正挤出段、空间近表面距离或人工裁剪。该口径能保留来源依据，后续更换实验件时也可以继续从 G-code 注释中恢复材料或工艺语义。
