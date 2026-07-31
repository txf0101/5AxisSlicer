# Tube Setup 设置脚本使用说明

## 1. 打开窗口

进入“管状切片”工作台后，底部显示“设置脚本”。标题栏关闭按钮隐藏 Dock，
“工具 > 设置脚本”恢复显示，“工具 > 折叠设置脚本”只收起或展开内容。窗口高度写入本机
Qt 设置，不进入项目文件。

输入区采用以下按键：

- `Enter`：执行光标所在的一条命令；
- `Shift+Enter`：插入换行；
- `Ctrl+Enter`：执行输入区中的脚本块；
- `Tab`：补全命令、资源 ID、安装位 ID 或实体 ID；
- `↑`、`↓`：浏览最近 200 条输入；
- `Ctrl+R`：搜索输入历史。

控制台聚焦期间，Viewer 的 `F`、`H`、`Esc`、`Ctrl++` 和 `Ctrl+-` 快捷键暂停。

## 2. 最小设置流程

模型导入后，可依次执行：

```python
tube.create_operation()
tube.confirm_part()
tube.set_machine("<机床资源 ID>")
tube.set_model_cs()
tube.set_build_cs()
tube.set_placement("<安装位 ID>")
```

`tube.confirm_part()` 的空参数表示选取当前所有未忽略的封闭 solid。Part 属于当前项目，
不会写入可移植 YAML。

使用 `tube.state()` 查看完整状态，`tube.issues()` 查看稳定问题码，`tube.validate()` 重新
计算 `Coordinates Valid` 与 `Setup Ready`。`tube.help()` 返回公开命令清单，
`tube.help("set_nozzle")` 返回单条签名。

成功结果分别列出实际修改字段和受影响树节点。领域错误会显示稳定错误码、行列和相关节点；
点击节点链接可跳转到左侧 Setup 树。

中文别名与英文 API 一一对应，例如：

```python
管状.设置喷嘴(
    "<喷嘴资源 ID>",
    interface="M6×1",
    length_mm=12.5,
    use_collision_envelope=True,
)
```

## 3. 原子事务

需要成组提交的修改放入事务。任一命令校验或 YAML 写入失败时，整组修改均不发布：

```python
with tube.transaction():
    tube.set_machine("<机床资源 ID>")
    tube.set_model_cs(
        origin=(0, 0, 0),
        z=(0, 0, 1),
        x=(1, 0, 0),
    )
```

事务内仅接受修改命令。查询、撤销、重做和嵌套事务会返回稳定错误码。

## 4. 坐标与装夹

Model CS 数值默认位于 Source CS；Build CS 数值默认位于 Model CS。内部存储仍统一为
Source CS 下的毫米、右手系和列向量：

```python
tube.set_model_cs(
    origin=(0, 0, 0),
    z=(0, 0, 1),
    x=(1, 0, 0),
    input_frame="source",
)

tube.set_build_cs(
    origin=(0, 0, 0),
    z=(0, 0, 1),
    x=(1, 0, 0),
    input_frame="model",
)

tube.set_placement(
    "build_plate_mount",
    translation_mm=(0, 0, 0),
    rotation_xyz_deg=(0, 0, 0),
)
```

坐标或装夹编辑器存在草稿时，脚本修改返回 `E_DRAFT_ACTIVE`。控制台工具区会显示“应用
草稿”和“放弃草稿”，避免脚本覆盖尚未确认的拾取结果。

## 5. YAML 工作文件

未保存项目只维护内存配置。项目首次保存后，根目录生成
`manufacturing-setup.yaml`。每条成功的可移植修改都会先原子写入该文件，再发布到界面和
Viewer。Part 修改会明确显示“项目专属，YAML 未变化”。

项目打开时会比较项目主档、YAML 当前语义和 `base_project_setup_sha256`：

- 内容一致时直接附着；
- YAML 是上次未保存工作时，显示差异并询问恢复方向；
- 两边分别变化时，提供“使用 YAML”“使用项目”“取消打开项目”；
- 外部程序改写 YAML 后，自动覆盖暂停，用户可载入预览或以当前 Setup 覆盖。

“导入配置”只应用语义配置，当前 Part 保持不变。“导出副本”写出独立 YAML，不改变工作
文件位置。格式契约见
[Manufacturing Setup YAML v1](../formats/manufacturing-setup-yaml.md)。

## 6. 安全边界

输入文本只交给受限 AST 解析器，不调用 Python 执行器。允许值限定为有限数字、字符串、
布尔值、`None`、tuple、list 和字符串键 dict。以下语法会被拒绝：

- `import`、赋值、变量引用、运算表达式和属性链；
- 循环、条件、异常处理、lambda、推导式和星号参数；
- `eval`、`exec`、dunder、分号拼接；
- 文件系统、网络、线程、子进程和 PowerShell 命令。

`.py` 设置脚本仅是该受限语言的载体，文件上限为 256 KiB、500 条命令和 32 层嵌套。

语法与配置格式分别依据 [Python AST](https://docs.python.org/3/library/ast.html)、
[YAML 1.2.2](https://yaml.org/spec/1.2.2/)、[RFC 9512](https://www.rfc-editor.org/rfc/rfc9512)
和 [JSON Schema 2020-12](https://json-schema.org/draft/2020-12)。
