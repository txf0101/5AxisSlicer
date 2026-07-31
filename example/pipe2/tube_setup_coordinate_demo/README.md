# pipe2 管状坐标设置演示

本目录保存 `弯管新.stp` 的可重开演示项目。项目已完成 Part、Model CS、Build CS、参考机床与装夹定位，并附带一份可重复执行的受限设置脚本。

## 直接打开

在仓库根目录启动软件：

```powershell
python run_app.py
```

点击顶部“打开项目”，选择：

```text
example/pipe2/tube_setup_coordinate_demo/project.json
```

软件会进入“管状切片”工作台。可依次查看左侧的“零件”“模型坐标系”“构建坐标系”和“装夹定位”。底部状态应显示：

| 项目 | 演示结果 |
| --- | --- |
| Part | `body_001` 圆盘与 `body_002` 弯管 |
| Model CS | 原点 `(0, 0, 0)`，Z `(0, 0, 1)`，X `(1, 0, 0)` |
| Build CS | 与 Model CS 重合 |
| Machine | `Generic XYZAC Reference` |
| Placement | `build_plate_mount`，六自由度微调均为 0 |
| Coordinates Valid | 是 |
| Setup Ready | 是，仅代表演示字段满足当前门禁 |

问题列表中的 `MACHINE_REFERENCE_ONLY` 属于预期警告。当前机床是参考 Profile，没有真实设备的标定、限位核验和控制器语义，不能据此输出可执行 NC。

## 坐标的几何依据

STEP 使用毫米，包含两个封闭 solid：圆盘 3 个面，弯管 8 个面。两者属于同一打印件，均已归入 Part。

- 原点取圆盘下表面 `body_001_face_0003` 的中心 `(0, 0, 0)`。
- 该面的原始法向为 `-Z`，翻转后将 `+Z` 作为构建方向。
- `+X` 取圆盘中心指向 `body_001_vertex_0002` 的方向；该顶点坐标为 `(25, 0, 0)`。
- Model CS 与 Build CS 在本演示中重合，便于核对 Source、Model、Build 三套坐标的变换链。

源 STEP 的 SHA-256 为：

```text
116e99fd43492bd1f4f519c80c93cd1f7cd0bf2cb6861b3e123148e4031a0d4b
```

项目正常重开使用 `source/` 中的同哈希 STEP 副本。`project.json` 内记录的原始路径只供显式“从原文件更新”。

## 从原 STEP 重演

1. 导入 `example/pipe2/弯管新.stp`。
2. 点击“进入管状设置（定义坐标）”，或从顶部“工作台”进入“管状切片”。
3. 在底部“设置脚本”工具栏点击“加载脚本”。窗口被关闭时，可从“工具 > 设置脚本”恢复。
4. 选择本目录的 `setup_demo.py`。
5. 查看控制台输出，确认 `Coordinates Valid: true`。随后可将结果保存到新的项目文件夹。

`setup_demo.py` 只包含软件白名单内的 `管状.*` 指令，软件不会调用 Python 执行器。存在坐标或装夹草稿时，先在控制台工具栏选择“应用草稿”或“放弃草稿”。

## 演示数据边界

为展示完整 Setup 状态，项目给 0.4 mm 喷嘴填入 `M6×1`、总长 `12.5 mm` 和简化碰撞外形，并确认了内置 PLA 参考材料。这组喷嘴字段没有实物图纸或测量依据，只能用于界面与保存流程演示。真实设备需要按热端图纸或实测值替换接口、总长和外形，并重新核对材料与 Machine Profile。

坐标设置的中文操作图见仓库文档 [`docs/guides/tube_coordinate_setup_zh.md`](../../../docs/guides/tube_coordinate_setup_zh.md)，脚本控制台说明见 [`docs/guides/tube_setup_script_console_zh.md`](../../../docs/guides/tube_setup_script_console_zh.md)。

## 文件说明

- `project.json`：完整项目主档，含 Part、资源快照和坐标定义。
- `manufacturing-setup.yaml`：实时可移植 Setup 工作态，不包含模型 body ID。
- `setup_demo.py`：从原 STEP 重演本配置的受限命令脚本。
- `source/*.stp`：项目重开使用的 STEP 副本。
