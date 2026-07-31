# Manufacturing Setup YAML v1

## 1. 用途与权威边界

`manufacturing-setup.yaml` 是 Tube Setup 的可移植工作态文件，采用 UTF-8、LF 和标准
`.yaml` 后缀。`project.json` 继续保存完整项目主档；两份内容分叉时，由上层会话显示字段
差异并让用户选择恢复方向。

配置包含以下内容：

- Machine、Nozzle、Material 的完整 `ResourceSnapshot`，含资源内容哈希；
- Model CS、Build CS 在 Source CS 中解析后的原点、Z 方向、X 方向和来源类型；
- 安装位、参考变换以及局部六自由度微调；
- 至多一条 `tube_thin_wall_indexed` 操作的名称和启用状态。

Part 分配、STEP 路径与哈希、拓扑对象 ID、几何签名、Setup/Operation 项目 ID、草稿、
问题列表、节点状态和派生矩阵不进入该文件。`part_policy: preserve_current` 要求载入时保留
当前项目的 Part。资源快照内部的资源 ID、机床 Link/轴 ID 和标定矩阵属于资源定义，必须
完整保存，才能核验快照并复现机床语义。

该格式随仓库 MIT 许可证开放。机器、喷嘴和材料快照仍受各自来源声明约束。

## 2. 标准依据

- [YAML 1.2.2](https://yaml.org/spec/1.2.2/) 定义文本语法；
- [RFC 9512](https://www.rfc-editor.org/rfc/rfc9512) 注册 `application/yaml` 媒体类型；
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) 定义结构校验；
- 仓库中的
  [`manufacturing-setup-v1.schema.json`](../../schemas/manufacturing-setup-v1.schema.json)
  是 v1 的机器可读契约。

解析器使用 YAML 1.2 的布尔值语义。`yes`、`no` 等 YAML 1.1 写法会作为字符串读取，若
字段要求布尔值，Schema 校验会拒绝。

## 3. 文档结构

未配置资源和坐标时的最小文档如下：

```yaml
format: five-axis-slicer.manufacturing-setup
schema_version: 1
units:
  length: mm
  script_angle: deg
coordinate_convention: source_mm_right_handed_column_vector
part_policy: preserve_current
metadata:
  revision: 1
  content_sha256: 7a3dd749d0eee536b285e60817fa06babc433393fe0478364bb17f4f3fb88de8
  base_project_setup_sha256: null
setup:
  name: Manufacturing Setup 1
  resources:
    machine: null
    nozzle: null
    material: null
  coordinate_systems:
    model: null
    build: null
  placement: null
operations: []
```

坐标字段始终使用 Source CS 数值。几何拾取结果只保留解析值和来源，不携带拓扑引用：

```yaml
model:
  name: Model CS
  origin_in_source_mm: [0.0, 0.0, 0.0]
  z_direction_in_source: [0.0, 0.0, 1.0]
  x_direction_in_source: [1.0, 0.0, 0.0]
  provenance:
    origin: face_centroid
    z_direction: plane_normal
    x_direction: numeric
    geometry_resolved: true
```

载入带 `geometry_resolved: true` 的坐标时，上层应提示用户复核。方向必须有限且非零，X
与 Z 不得共线。坐标域采用毫米、右手系和列向量约定。

装夹的 `reference` 与 `adjustment` 分开保存：

```yaml
placement:
  mount_datum_id: build_plate_mount
  reference:
    translation_mm: [0.0, 0.0, 0.0]
    quaternion_xyzw: [0.0, 0.0, 0.0, 1.0]
  adjustment:
    translation_mm: [1.0, 2.0, 3.0]
    quaternion_xyzw: [0.0, 0.0, 0.0, 1.0]
```

四元数顺序固定为 `(x, y, z, w)`。读取时会归一化并采用唯一符号表示。有效变换按
`T_reference · Translate · Rx · Ry · Rz` 的领域约定重建。

## 4. 哈希、分叉与原子发布

`metadata.content_sha256` 是配置语义的 SHA-256。计算输入涵盖 `format`、版本、单位、
坐标约定、Part 策略、Setup 和 Operations；整个 `metadata` 块及 YAML 注释、引号和排版
均不参与计算。`base_project_setup_sha256` 记录最近一次同步项目主档时的 Setup 语义哈希。

外部编辑造成声明哈希与实际语义哈希不同后，严格读取仍返回结构有效的配置，并设置分叉
状态供上层预览。正式写入前，编码器刷新 `content_sha256`。原子写接口校验期望的文件字节
指纹，写入同目录临时文件，执行 `fsync`，再次核对指纹，再用 `os.replace` 发布。目标发生
变化时返回 `E_CONFIG_DIVERGED`，原文件保持完整。临时文件的 `fsync` 是发布门禁；替换完成
后的目录 `fsync` 只影响断电耐久性，失败会记录内部 Warning，已替换的 YAML 与 Controller 仍按
同一次成功提交处理，避免磁盘状态领先于内存状态。

编码器以固定字段顺序输出。更新已有 YAML 时，仍存在字段附近的注释、字符串引号样式和
映射对象会被复用；删去的字段及其注释不会保留。

## 5. 安全子集

读取器在领域对象构造前执行事件扫描、JSON Schema 校验和资源快照校验。以下内容会被
拒绝：

- 重复键、任何显式 tag、anchor、alias 和 merge key；
- `NaN`、正负无穷、非字符串映射键和未知字段；
- 高于 v1 的版本、超过一条的 Operations；
- 超过 2 MiB、32 层嵌套或 50,000 个节点的文档；
- 内容哈希错误、类型错位或包含未知 Profile 字段的资源快照；
- 零方向、共线坐标、非单位四元数无法归一化、机床中不存在的安装位。

解析过程不会注册自定义 YAML 构造器，也不会根据 tag 构造任意或可执行 Python 对象；文件、网络和 Qt 对象不在配置语义内。

## 6. Python codec API

公共入口位于 `five_axis_slicer.setup_config`：

```python
config = export_setup_config(setup, operations, base_project_setup_sha256=base_hash)
document = config.to_document()
text = dump_setup_config(config, existing_text=old_text)

loaded = load_setup_config(text)
candidate_setup, candidate_operations = loaded.apply_to_domain(
    current_setup,
    current_operations,
    new_operation_id="provider-generated-id",
)

fingerprint = setup_config_fingerprint(path)
new_fingerprint = atomic_write_setup_config(
    path,
    dump_setup_config(loaded),
    expected_fingerprint=fingerprint,
)

# 首次创建时同时约束“读取时不存在”和“发布前仍不存在”
new_fingerprint = atomic_write_setup_config(path, text, expect_missing=True)
```

`apply_to_domain()` 保留当前 `setup_id`、Part 分配和已有 `operation_id`。当前没有操作且 YAML
包含操作时，命令 provider 负责生成 ID，并通过 `new_operation_id` 传入。候选状态应在领域
校验、YAML 编码和持久化全部成功后，再由命令内核一次性发布给 Controller、GUI 和 Viewer。
