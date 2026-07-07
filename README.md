# 5AxisSclicer V2.0

5AxisSclicer V2.0 当前聚焦论文优先版界面：以 Workbench 为入口，进入 Operation Session 后完成 STEP 对象定义、打印参数占位、材料与机器配置占位、导入 NC/G-code 路径预览和基础检查。当前可交互主线是 `Imported NC Review`，适合把已有 G-code 的空间路径、层范围和路径类型分色展示出来。

当前范围：

- Workbench 首页展示 Planar、Curve、Freeform、Rotary、Tube、Research 六类工作台。
- Operation Session 包含 Objects、Print、Material、Machine、Preview、Checks 六个页签。
- Objects 页保留 STEP/STP 的 body 列表选择和 edge 空间点选。
- Preview 页叠加半透明 STEP 模型和 G-code 路径，支持 Feature Type 图例、层范围、travel/extrusion 显隐、五轴姿态抽样和路径段属性面板。
- G-code 分色采用路径段数据结构中的 `move_type` 与 `extrusion_role` 字段，再由颜色映射表决定渲染颜色。`;TYPE:`、`;LAYER_CHANGE`、`;Layer` 等注释只作为解析线索。
- 第一版先读取已有 G-code，不重写完整切片算法，不做完整机床运动仿真。

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

载入默认论文演示样例：

```powershell
.\scripts\run_app.ps1 -Demo
```

指定 STEP 与 G-code：

```powershell
.\scripts\run_app.ps1 -Model "example\扇叶\风扇扇叶.STEP" -GCode "example\扇叶\风扇扇叶_PLA_1h50m.gcode" -Port 8769
```

直接走 Python 入口：

```powershell
& "C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe" run_app.py --demo --port 8769
```

默认演示文件：

- `example/扇叶/风扇扇叶.STEP`
- `example/扇叶/风扇扇叶_PLA_1h50m.gcode`

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
curl http://127.0.0.1:8765/preview/state
curl -Method POST http://127.0.0.1:8765/preview/layers -Body '{"layer_min":0,"layer_max":12}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/preview/visibility -Body '{"show_travel":false,"show_extrusion":true,"visible_roles":["external_perimeter","internal_infill"]}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/selection/set -Body '{"body_ids":["body_001"],"edge_ids":[]}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/project/save -Body '{"directory":"C:\\tmp\\five_axis_project"}' -ContentType 'application/json'
```

预览区固定用于 edge 点选。脚本需要设置 body 时，使用 `/selection/set` 写入 `body_ids`。

PowerShell 转义复杂时，可用脚本的 base64 JSON 入口：

```powershell
python scripts\automation_client.py /selection/set --payload64 eyJib2R5X2lkcyI6WyJib2R5XzAwMSJdLCJlZGdlX2lkcyI6W119
```

## 项目文件

保存目录包含：

- `source/`：STEP 与 G-code 源文件副本。
- `project.json`：workbench、operation、源文件路径、模型枚举、body/edge 选择、G-code 摘要、颜色映射、层范围和显示开关。
- `preview/`：预留预览产物目录。

旧版 body/edge 选择字段继续保留，已有对象选择可随项目 JSON 恢复。

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
