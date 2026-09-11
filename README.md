# 5AxisSclicer V2.0

5AxisSclicer V2.0 以 Workbench 为入口。当前有两条可交互主线：`Imported NC Review` 用于已有 NC/G-code 的空间路径、层范围和路径类型预览；Tube Workbench 已完成 T01—T12，可配置 Setup，使用 Indexed、Buildup、Continuous 三种操作生成、检查、后处理、回读和导出离线结果，并保存、重开项目。

使用者可从[图文使用手册索引](docs/guides/README.md)进入。Tube 的完整流程见[Tube 工作台手册](docs/guides/tube_workbench_zh.md)，坐标设置见[管状坐标设置](docs/guides/tube_coordinate_setup_zh.md)，G-code 阅读见[G-code 可视化手册](docs/guides/gcode_preview_zh.md)，底部控制台与 YAML 工作文件见[设置脚本说明](docs/guides/tube_setup_script_console_zh.md)。当前只有管状工作台接入完整制造 Setup 和生成闭环；其他工作台继续使用通用 Operation Session。

六个工作台的算法开发按[开发计划](docs/planning/development_plan.md)推进，优先完成管状工作台。每轮任务状态、验收证据和下一步更新到[进度台账主表](docs/planning/progress_tracker.md#主表)；NX 与公开项目资料见[参考资料](docs/planning/reference_research.md)，全部开发文档从[文档索引](docs/README.md)进入。

Tube 的 T01—T12 实现已经聚拢到本仓库：Indexed 支持受限圆管的分块切层和安全转位，Buildup 支持多道加厚和可选平面底座工序，Continuous 支持沿单支管中心线的连续螺旋。三种操作共用生成、检查、参考 XYZAC 求解、NC 后处理、回读、导出和结果过期状态。Generic XYZAC 仍是离线参考机型，尚未取得真实机床资格。

管状算法主要学习了相邻 `5AxisSlicer` 工程中的 Fractal Cortex 多方向分块、逐块切层和安全转位流程。Fractal Cortex 由 Fractal Robotics 开发，README 标注 Copyright (C) 2025 Daniel Brogan，许可证为 GPLv3。本项目当前仅内部传阅、暂无公开计划；新实现按 V2.0 的 B-Rep、路径、运动学和验证契约重写。固定 commit、逐文件 SHA-256、方法映射和许可证边界见[Tube Indexed 参考来源登记](docs/planning/tube_reference_provenance.md)。

当前范围：

- Workbench 首页展示 Planar、Curve、Freeform、Rotary、Tube、Research 六类工作台。
- Operation Session 包含 Objects、Print、Material、Machine、Preview、Checks 六个页签。
- Objects 页保留 STEP/STP 的 body 列表选择和 edge 空间点选。
- Tube Workbench 显式创建 `Tube Thin-Wall Indexed` 操作，Part 可包含多个封闭 solid；sheet、Ignore 和未分配实体保留显示且不进入后续制造计算。
- Tube Operation 编辑器可指定管体、入口圆边、出口圆边和既有基体，并编辑道宽、层高、最大楔角、道高误差、安全间隙、回抽、沉积/空移进给和轮廓弦高误差。
- Tube 坐标编辑采用原点、Z 方向、X 方向三参考定义，支持几何拾取、数值输入、方向翻转、Draft、Apply/Cancel 和六自由度装夹微调。
- Machine、Nozzle、Material 使用内置模板、用户资源库和项目冻结快照；参考机型会产生 Warning，资源不完整或材料未审核会阻止 Setup Ready。
- Preview 页叠加半透明 STEP 模型和 G-code 路径，支持 Feature Type 图例、层范围、travel/extrusion 显隐、五轴姿态抽样和路径段属性面板；默认优先显示正挤出路径，空走和姿态抽样可在面板中打开。
- G-code 分色采用路径段数据结构中的 `move_type` 与 `extrusion_role` 字段，再由颜色映射表决定渲染颜色。`;TYPE:`、`;LAYER_CHANGE`、`;Layer` 等注释只作为解析线索。
- A/C 五轴 G-code 仅在调用方显式确认已注册的控制器语义后，采用 `P_part = Rz(-C) * Rx(-A) * P_machine` 反算工件坐标。未确认语义、非零 B、U/V/W 或运动学诊断会让整份文件统一保留 Machine XYZ；纯 E 回抽和 prime 只进入运动类型统计，不写入路径线。
- T08—T12 已补齐生成/后处理/回读、RMF、时间参数化与离线检查相关实现；其算法为本项目独立复写，受本地 Fractal/V1 项目启发，运行不依赖相邻目录。Generic XYZAC 仅为离线参考，不能作为实机资格。

T08—T12 的公开来源、术语边界和控制器语义限制见[参考资料检索](docs/planning/reference_research.md)；其中 M82 按 Marlin/RepRap 语义处理，不称为 LinuxCNC 定义。

## 环境

项目支持 Python 3.10 至 3.12。建议使用独立虚拟环境并以 editable 模式安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

开发工具由 `pyproject.toml` 的 `dev` extra 统一维护；完整测试另需用于生成 STEP 测试件的 `cad-tests` extra：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,cad-tests]"
```

应用运行时直接使用 `cadquery-ocp`，兼容 NumPy 1.26 至 2.2。`cad-tests` 会引入 CadQuery 及其 NLopt 依赖，干净环境中的解析器可能选择 NumPy 2.x；只运行应用时无需安装该 extra。

`scripts/run_app.ps1` 默认调用当前 `PATH` 中的 `python`。可用 `-Python` 传入虚拟环境或 conda 解释器的完整路径。

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

### STEP 导入后的坐标入口

STEP 在平面、曲面、自由曲面、回转工作台或通用操作会话中载入后，点击左侧“进入管状设置（定义坐标）”。当前模型会直接带入管状工作台。也可返回“工作台”并选择“管状工作台”。模型坐标系、构建坐标系和装夹定位只在该页面中提供。

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

### Bambu 式预览鼠标操作

| 鼠标操作 | 结果 |
| --- | --- |
| 左键短按几何 | 按当前拾取类型选择 |
| 左键短按空白处 | 清空选择 |
| 左键拖动 | 旋转视图 |
| 中键或右键拖动 | 沿屏幕平面平移视图 |
| 滚轮 | 围绕鼠标指针所在的焦平面位置缩放 |

拖动越过系统阈值后，松开不会触发拾取。当前鼠标手势只处理相机与几何选择，尚未提供对象拖拽、Gizmo、框选和右键菜单。

## HTTP 自动化接口

GUI 启动后默认监听 `127.0.0.1:8765`。

非 loopback 监听需要显式传入 `-AllowRemoteAutomation`，并在进程环境中提供至少 32 字符的 `FIVE_AXIS_SLICER_AUTOMATION_TOKEN`。`scripts/automation_client.py` 会自动读取该变量。令牌不写入命令行、项目文件或日志；远程入口应限制在受信网络并配置主机防火墙。

```powershell
$env:FIVE_AXIS_SLICER_AUTOMATION_TOKEN = "<由密码管理器提供的随机令牌>"
.\scripts\run_app.ps1 -BindHost "0.0.0.0" -AllowRemoteAutomation -Port 8765
```

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
curl -Method POST http://127.0.0.1:8765/tube/operation/set -Body '{"tube_body_id":"body_002","entry_port_id":"body_002_edge_0003","exit_port_id":"body_002_edge_0014","substrate_body_id":"body_001","layer_height_mm":0.25}' -ContentType 'application/json'
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
python scripts\check_quality.py
python -X faulthandler -m pytest -q
python -m build
python -m twine check dist\*
```

`check_quality.py` 统一执行 Ruff、Mypy 和上下文预算检查。常规模块的预算为 1,000 行，类为 500 行，函数为 60 行，圈复杂度为 15；`pyproject.toml` 记录现存超限对象的精确上限。新代码不得扩大这些上限，完成拆分后应同步下调对应豁免。`python scripts\check_context_budget.py --print-baseline` 可输出当前审计值。

原生预览索引是可选加速层。发布原生 wheel 时显式开启构建开关：

```powershell
$env:FIVE_AXIS_BUILD_NATIVE = "1"
python -m build --wheel
Remove-Item Env:FIVE_AXIS_BUILD_NATIVE
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

## 切片成果预览

成果页与 Workbench、Operation Session 并列。首页“切片成果预览 / Slicing Result Preview”进入空态页面，可打开内置叶轮项目、已有 G-code 或 STEP。左栏管理输入文件与工艺参数，中栏显示工件坐标路径和阶段进度，右栏显示源文件统计、固定缩略图及真实代码上下文。导入路径保持源 G-code 的坐标与统计；参数值写入项目状态时不触发重新解析。

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
curl http://127.0.0.1:8765/results/perf
```

界面中的“完整路径 / Full Path”质量档读取完整正挤出 timeline，适合检查路径连续性和局部密集区域。自动化参数 `mode="paper"` 为兼容值，含义与界面的“完整路径”一致，只切换预览质量。软件界面不提供论文图导出。

成果页采用统一字号 token，并按实际字体宽度处理双语按钮、统计项和显隐选项。长路径在界面中间省略，tooltip 与无障碍文本保留完整内容。1600 × 900 的中英文界面无横向滚动。
