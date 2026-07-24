# 5AxisSclicer V2.0

5AxisSclicer V2.0 以 Workbench 为入口。当前有两条可交互主线：`Imported NC Review` 用于已有 NC/G-code 的空间路径、层范围和路径类型预览；Tube Workbench 已完成第一阶段 Setup 与坐标闭环，可定义 Part、Machine、Nozzle、Material、Model CS、Build CS 和 Placement，并保存、重开项目。

当前范围：

- Workbench 首页展示 Planar、Curve、Freeform、Rotary、Tube、Research 六类工作台。
- Operation Session 包含 Objects、Print、Material、Machine、Preview、Checks 六个页签。
- Objects 页保留 STEP/STP 的 body 列表选择和 edge 空间点选。
- Tube Workbench 显式创建 `Tube Thin-Wall Indexed` 操作，Part 可包含多个封闭 solid；sheet、Ignore 和未分配实体保留显示且不进入后续制造计算。
- Tube 坐标编辑采用原点、Z 方向、X 方向三参考定义，支持几何拾取、数值输入、方向翻转、Draft、Apply/Cancel 和六自由度装夹微调。
- Machine、Nozzle、Material 使用内置模板、用户资源库和项目冻结快照；参考机型会产生 Warning，资源不完整或材料未审核会阻止 Setup Ready。
- Preview 页叠加半透明 STEP 模型和 G-code 路径，支持 Feature Type 图例、层范围、travel/extrusion 显隐、五轴姿态抽样和路径段属性面板；默认优先显示正挤出路径，空走和姿态抽样可在面板中打开。
- G-code 分色采用路径段数据结构中的 `move_type` 与 `extrusion_role` 字段，再由颜色映射表决定渲染颜色。`;TYPE:`、`;LAYER_CHANGE`、`;Layer` 等注释只作为解析线索。
- A/C 五轴 G-code 仅在调用方显式确认已注册的控制器语义后，采用 `P_part = Rz(-C) * Rx(-A) * P_machine` 反算工件坐标。未确认语义、非零 B、U/V/W 或运动学诊断会让整份文件统一保留 Machine XYZ；纯 E 回抽和 prime 只进入运动类型统计，不写入路径线。
- 当前解析链路读取已有 G-code；完整五轴路径生成与机床运动仿真列入后续算法阶段。

## 环境

项目名与论文环境命名采用 `5AxisSclicer`。当前这台机器已存在的可用 conda 解释器路径为：

```powershell
C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe
```

`scripts/run_app.ps1` 默认指向该现有路径。若后续新建了名为 `5AxisSclicer` 的环境，可用 `-Python` 参数指定解释器。

安装依赖：

```powershell
& "C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe" -m pip install -r requirements.txt
```

## 快速启动

打开内置叶轮项目：

```powershell
.\scripts\run_app.ps1 -Demo
```

指定 STEP 与 G-code：

```powershell
.\scripts\run_app.ps1 -Model "example\叶轮\叶轮.stp" -GCode "example\叶轮\叶轮完整.gcode" -Port 8769
```

直接走 Python 入口：

```powershell
& "C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe" run_app.py --demo --port 8769
```

内置叶轮项目文件：

- `example/叶轮/叶轮.stp`
- `example/叶轮/叶轮完整.gcode`

## 快捷键

- `Ctrl+O` 打开 STEP/STP
- `Ctrl+G` 打开 NC/G-code
- `Ctrl+S` 保存项目
- `Ctrl+W` 返回 Workbench 首页
- `F` 适配视图
- `H` 重置视角
- `Esc` 清空选择
- 方向键旋转视图
- `Shift+方向键` 平移视图
- `Ctrl++` / `Ctrl+-` 缩放

## HTTP 自动化接口

GUI 启动后默认监听 `127.0.0.1:8765`。

```powershell
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/state
curl -Method POST http://127.0.0.1:8765/demo/load -Body '{}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/workbench/select -Body '{"key":"curve"}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/model/open -Body '{"path":"C:\\tmp\\model.step"}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/gcode/open -Body '{"path":"C:\\tmp\\path.gcode"}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/project/open -Body '{"path":"C:\\tmp\\five_axis_project"}' -ContentType 'application/json'
curl http://127.0.0.1:8765/preview/state
curl -Method POST http://127.0.0.1:8765/preview/layers -Body '{"layer_min":0,"layer_max":12}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/preview/visibility -Body '{"show_travel":false,"show_extrusion":true,"visible_roles":["external_perimeter","internal_infill"]}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/selection/set -Body '{"body_ids":["body_001"],"edge_ids":[]}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/selection/mode -Body '{"mode":"face"}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/selection/set -Body '{"face_ids":["face_001_001"],"vertex_ids":[]}' -ContentType 'application/json'
curl http://127.0.0.1:8765/tube/state
curl -Method POST http://127.0.0.1:8765/project/save -Body '{"directory":"C:\\tmp\\five_axis_project"}' -ContentType 'application/json'
```

普通 Operation Session 默认用于 edge 点选。Tube Workbench 可把 `/selection/mode` 设为 `body`、`face`、`edge` 或 `vertex`，再由 `/selection/set` 写入对应 ID；`/state` 和 `/tube/state` 返回当前 Setup、坐标与问题状态。

PowerShell 转义复杂时，可用脚本的 base64 JSON 入口：

```powershell
python scripts\automation_client.py /selection/set --payload64 eyJib2R5X2lkcyI6WyJib2R5XzAwMSJdLCJlZGdlX2lkcyI6W119
```

## 项目文件

保存目录包含：

- `source/`：按 SHA-256 内容寻址保存的 STEP 与 G-code 权威副本。
- `project.json`：v2 清单，保存 workbench、`setups[]`、`operations[]`、资源快照、四级拓扑描述、body/face/edge/vertex 选择和预览状态。
- `preview/`：预留预览产物目录。

项目保存使用临时清单和原子替换。v1 项目在内存迁移，第一次保存 v2 时备份原清单；未来版本、路径越界、源文件哈希变化、冻结快照损坏、顶层资源镜像与 Setup 快照冲突、拓扑签名漂移会被拒绝。用户资源库后来发生分叉时，项目继续使用冻结快照并报告 Warning。

## 验证

推荐验证命令：

```powershell
& "C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe" -m compileall src tests
& "C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe" -m unittest discover -s tests
```

真实 GUI 冒烟测试：

```powershell
$python='C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe'
$p = Start-Process -FilePath $python -ArgumentList @('run_app.py','--demo','--port','8769') -WorkingDirectory 'F:\【项目和任务】\5AxisSclicer_V2.0' -PassThru -WindowStyle Normal
try {
    & $python scripts\desktop_workbench_smoke.py --base http://127.0.0.1:8769 --out outputs\workbench_smoke
} finally {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force }
}
```

截图输出位置：`outputs/workbench_smoke/01_workbench_preview.png`。

## 论文级切片成果预览

成果页是 Workbench 与 Operation Session 之外的独立页面。首页“切片成果预览 / Slicing Result Preview”进入空态成果页，可打开内置叶轮项目、已有 G-code 或 STEP。左栏管理输入文件与工艺参数，中栏显示工件坐标路径和阶段进度，右栏给出源文件统计、固定缩略图、真实代码上下文及论文图导出。导入路径保持源 G-code 的坐标与统计，参数值写入项目状态时不触发重新解析。

直接打开空态成果页：

```powershell
.\scripts\run_app.ps1 -Results
```

加载叶轮 STEP 与完整 G-code：

```powershell
.\scripts\run_app.ps1 -Demo
```

`--demo` 是内置叶轮项目的兼容启动参数；原有 `/demo/load`、`/gcode/open` 和 `/preview/*` 保持 Operation Session 的兼容行为。成果页自动化接口如下：

```powershell
curl -Method POST http://127.0.0.1:8765/results/demo -Body '{}' -ContentType 'application/json'
curl http://127.0.0.1:8765/results/state
curl -Method POST http://127.0.0.1:8765/results/quality -Body '{"mode":"paper"}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/results/export -Body '{"language":"both","strict":true}' -ContentType 'application/json'
curl http://127.0.0.1:8765/results/perf
```

正式导出固定使用 1920 × 1080 逻辑布局与 2 倍离屏合成，并要求 OpenGL 全量路径能力；严格模式拒绝 VTK 抽样路径降级。默认产物位于 `outputs/paper_preview_acceptance/`，包含中英文 3840 × 2160 PNG 及同名 JSON。PNG 写入 sRGB、300 dpi 和不透明背景信息，JSON 记录加载时来源快照、统计、相机、显隐状态与渲染参数；同名文件对采用异常回滚和跨进程锁。视觉参考图归档在包资源 `src/five_axis_slicer/assets/impeller_four_panel_reference.png`，仅用于实现审计和视觉核查，不进入成果页可见内容。

成果页采用统一字号 token：正文与控件 15 px、次要文字 13 px、表单标签 13 px、G-code 14 px、卡片标题 15 px、栏目标题 16 px、页面标题 22 px、徽标 12 px。中英文按钮、标签、统计项和显隐选项按实际字体宽度布局；换行文字在语言切换后重新计算高度，长路径在界面中间省略，并在 tooltip 与无障碍文本中保留完整内容。顶部工具栏只放置高频动作，其余动作保留在菜单中；1600 × 900 的中英文界面均无工具栏隐藏项，左右栏横向滚动范围为 0。成果页采用正式功能文案，参考依据、参数作用边界和代码定位行号保存在审计 JSON 与维护文档中。

参考图对应的四个论文面板按独立 4K 图片导出，便于后续在论文中统一调整尺寸、间距与题注：

```powershell
python scripts\build_four_panel_paper_figure.py `
  --overall outputs\paper_preview_acceptance\impeller_result_preview_zh_3840x2160.png `
  --step example\叶轮\叶轮.stp `
  --gcode example\叶轮\叶轮完整.gcode `
  --output-dir outputs\paper_preview_acceptance\individual_panels `
  --language zh
```

英文版及无压缩 TIFF：

```powershell
python scripts\build_four_panel_paper_figure.py `
  --overall outputs\paper_preview_acceptance\impeller_result_preview_en_3840x2160.png `
  --step example\叶轮\叶轮.stp `
  --gcode example\叶轮\叶轮完整.gcode `
  --output-dir outputs\paper_preview_acceptance\individual_panels `
  --language en `
  --uncompressed-tiff
```

输出目录包含界面总览、工艺参数、五轴路径和机床可执行 G-code 四张 3840 × 2160 图片。中文交付为 PNG；英文同时保留 PNG 预览和无压缩 RGB TIFF，每个文件配有审计 JSON，汇总 manifest 记录语言、顺序、格式、哈希及 TIFF 压缩标记。英文 TIFF 使用基线 `Compression=1`，保持 8-bit RGB、300 dpi 和逐像素一致，不执行二次缩放。五轴路径图由 OpenGL FBO 捕获完整路径，再重绘贴合 TOP、FRONT、RIGHT 投影面的方向立方体文字、Part XYZ 轴标和起终点图例。G-code 单图采用两行标题区，文件名与四组语法色说明分行显示；正文优先采用 22 px 等宽字体，并在 18 至 22 px 范围内按最长真实指令、行号栏和 21 行上下文自适应。任一中英文标题、语法标签或代码行无法完整容纳时，导出直接报错。四张单图不内嵌 `(a)` 至 `(d)` 题注，排版与题注由用户在论文编辑环境中完成。2026-07-24 全仓回归结果为 271 passed、2 skipped；23 条 warning 均来自 CadQuery 测试辅助函数 `save()` 的 FutureWarning。
