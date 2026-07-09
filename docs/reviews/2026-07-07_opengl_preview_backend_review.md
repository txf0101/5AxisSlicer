# 2026-07-07 OpenGL 预览后端与索引缓存复盘

## 本轮目标

本轮按叶轮百万段样例推进预览性能重构。原 VTK 链路在拖动进度时会反复扫描 Python 路径段并重建 actor，大文件交互容易被主线程构网拖慢。本轮保留 Workbench、项目保存和 HTTP 自动化的外部接口，把渲染后端、进度索引和缓存格式换成更适合大路径预览的结构。

参考依据来自用户给出的 Bambu Studio、PrusaSlicer G-code Viewer 和 libbgcode 链接。落实到当前项目时，保留成熟软件的思路：渲染层使用 OpenGL buffer，导航层使用索引，解析语义仍由项目内的 G-code 数据结构维护。

## 实现记录

- 新增 `opengl_viewer.py`，默认使用 `QOpenGLWidget`、PyOpenGL shader 和 VBO 绘制 STEP 三角面、edge、G-code 线模式、实体道实例化数组、当前步高亮和姿态抽样。
- `viewer.py` 保留 VTK 后端并承担 fallback 选择。`FIVE_AXIS_RENDER_BACKEND=vtk` 或 offscreen 测试环境会回到 VTK，现有 UI 调用入口继续使用 `load_model()`、`load_gcode_preview()`、`set_preview_progress()` 等方法。
- 新增 `native/five_axis_slicer_native.cpp` 和 `native_preview_index.py`。索引打包优先走 pybind11 native，构建链不可用时走 NumPy/Python fallback，两条路径输出同形状数组。
- `GCodePreview` 增加 `render_index` 和二进制 timeline arrays。`progress_state()`、`timeline_count_for_layers()`、`timeline_step_for_layer_progress()` 改成前缀索引查询，纯 E 当前步可定位到最近可绘制 segment。
- 缓存升级为 `gcode-preview-v5-opengl-index`。新格式使用小 JSON 元信息加 `.npz` 数组，旧 v4 JSON.gz 可读取并回写 v5。
- OpenGL 交互策略改成自动模式：加载后先显示轻量线，进度拖动和旋转只更新当前步小 buffer；交互结束 150 ms 后恢复实体道。首次加载的实体道恢复延迟为 1200 ms，避免启动阶段大 VBO 上传抢占自动化命令。
- edge 点选增加隐藏 color-id pass，投影距离点选保留为兜底路径。
- `/preview/state` 增加 backend、quality、frame_ms、gpu_draw_count、cache_format；新增 `/preview/perf` 返回最近帧耗时、FPS、进度更新时间、GPU buffer 数量和显存估算。

## 验证记录

- `python -m compileall src tests scripts`：通过。
- `python -m unittest discover -s tests`：25 个测试通过。
- `python setup.py build_ext --inplace`：已在本机 MSVC 与 pybind11 环境下生成 `five_axis_slicer_native`。
- 叶轮 v5 warm cache 加载：`example/叶轮/叶轮完整.gcode`，62,753,499 字节，加载 4.40 s；路径段 1,011,023，抽样存储 337,007，timeline 1,011,990。
- 进度索引查询：0%、50%、100% 查询分别约 0.057 ms、0.033 ms、0.023 ms。
- OpenGL HTTP 冒烟：`/preview/progress` 三次跳转耗时约 59.59 ms、32.60 ms、26.87 ms；释放后 1 s 内回到 `opengl_solid_adaptive_19`。
- `/preview/perf` 记录：backend 为 `opengl`，平均帧耗时约 5.33 ms，最大帧耗时约 16.28 ms，显存估算约 17.78 MB，GPU draw count 为 4。
- 桌面截图冒烟输出到 `outputs/workbench_smoke_opengl/01_workbench_preview.png`，画面包含 STEP 叶轮、路径点和当前步高亮。

## 质量判断

本轮的核心价值在于把百万段预览从“对象重建”推进到“索引加 buffer 更新”。进度条拖动时不再遍历完整 timeline，也不再重建整批路径 buffer；主要工作变成一次索引查找和一个当前步小 buffer 更新。这个结构和 G-code 解析语义解耦，后续接入时间估算、轴限位检查或 role mask 时，可以复用同一套 layer/timeline 前缀。

native 扩展只处理数组打包，解析规则仍留在 Python。这个边界降低了维护风险：G-code 模态、AC 反算、纯 E 计数和 role 识别继续由已有测试保护；C++ 层负责可替换的性能段。构建链缺失时 fallback 仍能跑同一批测试。

实体道上限最终定为 18,000 个抽样段。这个数值来自真实叶轮压测：约 0.52 s 可构建实体数组，GPU 上传规模约 17.8 MB。继续提高抽样量会增加截图细节，同时拉长主线程阻塞；当前配置更适合论文预览、自动化拖动和桌面交互的综合目标。

## 后续观察

- 目前 v5 缓存会保存 float32 预览数组，适合交互显示。若后续要做计量级几何复核，应继续读取原始解析对象或源 G-code。
- OpenGL 实体道仍是抽样实例化显示，段间没有融合。若要做局部精细截图，可增加“当前窗口实体道”模式，只对当前步附近的连续段提高采样密度。
- 旧 VTK fallback 仍可用，但进度 POST 在百万段样例下约 600 ms。后续性能验收应优先使用 OpenGL backend。
