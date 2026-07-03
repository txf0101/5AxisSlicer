# 5AxisSclicer V2.0

5AxisSclicer V2.0 是一个面向教学和实验的小型 STEP 前置选择器。首版聚焦多实体 STEP/STP 模型导入、body 选择、edge 选择、高亮预览和项目 JSON 保存，为后续可制造增材特征分组留下接口。

当前边界：

- 支持多实体 STEP/STP 的 body 枚举和 edge 枚举。
- 支持右侧列表选择 body；支持右侧列表或左侧预览区选择 edge，并保存选择结果。
- 不做完整路径规划、单实体中心区识别、外周区识别、曲面特征分解、中心轴识别、锐边自动分类。
- 不回写 STEP；选择信息保存到项目目录。

## 环境

推荐使用已有 `5AxisSlicer` conda 环境：

```powershell
& "C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe" -m pip install -r requirements.txt
```

当前实现使用 PyQt5、VTK、OCP/CadQuery。若环境中 CadQuery 已可用，通常已经包含 OCP。

## 运行

```powershell
.\scripts\run_app.ps1
```

也可以直接指定模型和自动化端口：

```powershell
.\scripts\run_app.ps1 -Model path\to\model.step -Port 8765
```

## 快捷键

- `Ctrl+O` 打开 STEP/STP
- `Ctrl+S` 保存项目
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
curl -Method POST http://127.0.0.1:8765/model/open -Body '{"path":"C:\\tmp\\model.step"}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/selection/mode -Body '{"mode":"edge"}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/selection/set -Body '{"body_ids":["body_001"],"edge_ids":[]}' -ContentType 'application/json'
curl -Method POST http://127.0.0.1:8765/project/save -Body '{"directory":"C:\\tmp\\five_axis_project"}' -ContentType 'application/json'
```

预览区固定用于 edge 点选。脚本需要设置 body 时，使用 `/selection/set` 写入 `body_ids`；`/selection/mode` 只接受 `edge`。

PowerShell 转义复杂时，可用脚本的 base64 JSON 入口：

```powershell
python scripts\automation_client.py /selection/mode --payload64 eyJtb2RlIjoiZWRnZSJ9
```

## 桌面点击冒烟测试

启动 GUI 后，可以运行真实鼠标点选脚本。该脚本会调整窗口位置并截图，使用 Windows 鼠标事件点击右侧 body 列表和左侧 VTK 视图，并用 HTTP 状态确认 body 与 edge 被选中。

```powershell
conda activate 5AxisSlicer
python scripts\generate_sample_step.py outputs\desktop_click_test\two_boxes.step
python run_app.py --model outputs\desktop_click_test\two_boxes.step --port 8767
python scripts\desktop_click_smoke.py --base http://127.0.0.1:8767 --out outputs\desktop_click_test
```

## 项目文件

保存目录包含：

- `source/model.step`：源 STEP 副本
- `project.json`：模型元信息、body/edge 列表、选择结果、预留分组
- `preview/`：预留目录，首版不强制导出 GLB

`project.json` 不承载制造语义，只记录用户显式选择，为后续分组流程提供稳定入口。
