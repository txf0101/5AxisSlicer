# 5AxisSclicer V2.6.2

5AxisSclicer 是面向五轴增材制造的 Windows 桌面切片软件。它导入 STEP/STP 模型，按零件几何选择平面、曲线、回转、管体或自由曲面工作台，设置机床与材料，生成并预览路径，检查运动和 G-code 回读后导出离线 NC 结果。本项目正在测试和持续完善中；实际参数与打印效果以用户设备调试为准。

2026 年 3 月之后，Codex 参与了本项目的代码编写。

**English:** [Product README](README.en.md) · [Quick start](docs/guides/quickstart_clickthrough_en.md) · [Learning manual](docs/guides/user_learning_manual_en.md) · [Guide index](docs/guides/README.md#english-guides)

**第一次使用：**先看[五个工作台图文点击教程](docs/guides/quickstart_clickthrough_zh.md)，依次完成公共制造设置、选几何、应用参数、生成检查和离线导出。按对象跳转：[Planar](docs/guides/quickstart_clickthrough_zh.md#1-planar平面切片) · [Curve](docs/guides/quickstart_clickthrough_zh.md#2-curve沿边沉积) · [Rotary](docs/guides/quickstart_clickthrough_zh.md#3-rotary固定轴回转) · [Tube](docs/guides/quickstart_clickthrough_zh.md#4-tube管体生长) · [Freeform](docs/guides/quickstart_clickthrough_zh.md#5-freeform曲面与实体) · [已有 G-code 预览](docs/guides/quickstart_clickthrough_zh.md#6-查看已有-g-code)。参数和排错见[学习总册](docs/guides/user_learning_manual_zh.md)与[手册索引](docs/guides/README.md)。Research 入口暂不可用；本项目正在测试并持续完善。

四个示例的模型、原始代码、离线切片代码及路径文件见[示例文件索引](example/README.md)。大文件使用 Git LFS；克隆后需安装 Git LFS 并执行 `git lfs pull`。示例参数和打印效果以用户设备的实际调试结果为准；上机调试前请核对机床设置、装夹和路径安全。

5AxisSclicer V2.6.2 以 Workbench 为入口。“G-code 文件预览”用于已有 NC/G-code 的空间路径、层范围和路径类型预览。Tube 支持 Indexed、Buildup、Continuous；Planar 支持 Region、Zigzag、Offset、Thin Wall、Spiral 和 buildplate-only Planar Support；Curve 支持 Buildup、Multi-pass Buildup 和 Offset Buildup；Rotary 支持圆柱/圆锥 Spiral、圆周多道 Thin Wall 和跨周期 Around Part；Freeform 支持有限修剪面组、曲面贴合、薄壁及明确几何角色的实体填充。这五类制造入口共用路径、状态、检查、回读、保存重开和六件套离线导出链。

Freeform 的球面、一般曲面与径向实体填充需要明确选择对应的实体角色和几何参考。实际参数和打印效果以用户设备的调试结果为准；运行前请核对控制器、喷嘴、装夹及路径。

初次使用请从[《5AxisSclicer V2.6.2 学习手册》](docs/guides/user_learning_manual_zh.md)开始。手册首页写明 IDE 的 `run_app.py` 和 PowerShell 的 `scripts/run_app.ps1` 启动方式，并按界面、Setup、工作台选择、操作、生成恢复、回读、六件套和独立迁移组织课程。pipe2、平面件、叶轮、扇叶和半球只作为练手材料，不要求复制案例 ID 或参数。熟悉公共流程后，可从[学习与参考手册中心](docs/guides/README.md)进入 Tube、Planar、Curve、Rotary、Freeform、多材料、机型和 G-code 专项参考。

开发计划、验证记录与公开资料统一从[开发文档索引](docs/README.md)进入。Research 入口不可用；第二机型需要独立配置与验证。

Tube 的 Indexed 支持受限圆管的分块切层和安全转位，Buildup 支持多道加厚和可选平面底座工序，Continuous 支持沿单支管中心线的连续螺旋。三种操作共用生成、检查、参考 XYZAC 求解、NC 后处理、回读、导出和结果过期状态。Generic XYZAC 是离线参考机型；实际机床参数和打印效果以用户设备的调试结果为准，本项目持续完善中。

Tube Indexed 的参考来源、方法映射和许可证边界见[来源登记](docs/planning/tube_reference_provenance.md)。

当前范围：

- Workbench 首页展示 Planar、Curve、Freeform、Rotary、Tube、Research 六类工作台。
- Planar 工作台支持 Region 截面预览，以及 Zigzag、Offset、Thin Wall、Spiral 和 buildplate-only Planar Support 五种路径操作的独立检查、G-code 回读和六件套离线导出。
- Curve 工作台支持稳定有向 edge 链、邻面或用户法向、Buildup、Multi-pass Buildup、Offset Buildup、引用重绑、真实 Toolpath Viewer、G-code 回读和六件套离线导出。
- Rotary 工作台支持稳定回转轴/面/轮廓引用、非零回转中心、连续角展开、圆柱/圆锥 Spiral、多层多道 Thin Wall、跨零点多区域 Around Part、G93 逆时间 XYZAC 后处理与完整回读。Generic XYZAC 资格仍仅限离线参考。
- 论文核心 Freeform 子集限制为最多 16 个面和 32 条导引线，支持曲面贴合、薄壁、有限多道/多层、显式 T0—T3 材料区域事件和自有 AC 离线后处理；trim 越界、法向跳变、退化、传感器/温控未就绪及命令回读不一致都会阻止导出。
- 自有 AC 输出固定 G90/M83/G94，分开 Indexed 绝对 Z20 与材料 park 相对 Z+20，并记录累计 C。当前控制器/宏版本、协调 XYZAC 语义和累计 C 上限未获得外部证据，所以 `machine_executable=false`。
- Operation Session 包含 Objects、Print、Material、Machine、Preview、Checks 六个页签。
- Objects 页保留 STEP/STP 的 body 列表选择和 edge 空间点选。
- Tube Workbench 显式创建 `Tube Thin-Wall Indexed` 操作，Part 可包含多个封闭 solid；sheet、Ignore 和未分配实体保留显示且不进入后续制造计算。
- Tube Operation 编辑器可指定管体、入口圆边、出口圆边和既有基体，并编辑道宽、层高、最大楔角、道高误差、安全间隙、回抽、沉积/空移进给和轮廓弦高误差。
- Tube 坐标编辑采用原点、Z 方向、X 方向三参考定义，支持几何拾取、数值输入、方向翻转、Draft、Apply/Cancel 和六自由度装夹微调。
- Machine、Nozzle、Material 使用内置模板、用户资源库和项目冻结快照；旋转关节保留内部 A/B/C 运动学语义，同时可映射为固件使用的单字母 G-code 地址，并由四个制造工作台共用；参考机型会产生 Warning，资源不完整或材料未审核会阻止 Setup Ready。
- Preview 页叠加半透明 STEP 模型和 G-code 路径，支持 Feature Type 图例、层范围、travel/extrusion 显隐、五轴姿态抽样和路径段属性面板；默认优先显示正挤出路径，空走和姿态抽样可在面板中打开。
- G-code 分色采用路径段数据结构中的 `move_type` 与 `extrusion_role` 字段，再由颜色映射表决定渲染颜色。`;TYPE:`、`;LAYER_CHANGE`、`;Layer` 等注释只作为解析线索。
- A/C 五轴 G-code 仅在调用方显式确认已注册的控制器语义后，采用 `P_part = Rz(-C) * Rx(-A) * P_machine` 反算工件坐标。未确认语义、非零 B、U/V/W 或运动学诊断会让整份文件统一保留 Machine XYZ；纯 E 回抽和 prime 只进入运动类型统计，不写入路径线。
- Tube 使用 RMF、时间参数化、离线检查和 G-code 回读；运行不依赖相邻项目目录。Generic XYZAC 是离线参考配置，实际参数和效果以用户设备调试为准。
- Planar 的 Generic XYZAC 是离线参考配置。平台支撑仅支持从 buildplate 连通的垂直支撑，使用 Lines/Grid 图案和主体/界面分层；控制器、装夹和打印效果以用户设备调试为准。
- Curve 的 Generic XYZAC 包含 FK、运动限制、夹具 AABB 扫掠和 G-code 回读等离线检查；控制器、机床标定和打印效果以用户设备调试为准。

公开来源、术语边界和控制器语义限制见[参考资料检索](docs/planning/reference_research.md)；其中 M82 按 Marlin/RepRap 语义处理，不称为 LinuxCNC 定义。

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

已安装项目依赖时，也可直接走 Python 入口：

```powershell
python run_app.py --demo --port 8769
```

内置叶轮项目文件：

- `example/叶轮/叶轮.stp`
- `example/叶轮/叶轮完整.gcode`

### STEP 导入后的坐标入口

载入 STEP 后，点击顶部“公共制造设置”，依次核对零件、机床、喷嘴、材料、模型坐标系、构建坐标系和装夹定位。完成后返回“工作台”，选择适合该模型的切片方式。各工作台可沿用公共设置，也可保留独立设置或将修改保存回公共设置；按钮位置和作用范围见[图文教程](docs/guides/quickstart_clickthrough_zh.md#公共设置与本工作台设置)。

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

保存项目时，请选择专用文件夹。重开时选择其中的 `project.json`。若源文件、资源快照或几何引用不一致，软件会提示检查；请核对来源后再更新项目或重新生成路径。

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

## G-code 文件预览

首页“G-code 文件预览 / G-code File Preview”用于打开已有 G-code 或 STEP，并检查路径、统计和代码位置。工作台刚生成的路径在对应工作台内查看；要在此页检查代码，先导出并打开 `main.gcode`。左栏管理输入文件与工艺参数，中栏显示工件坐标路径和阶段进度，右栏显示源文件统计、固定缩略图及代码上下文。导入路径保持源 G-code 的坐标与统计；参数值写入项目状态时不触发重新解析。

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
