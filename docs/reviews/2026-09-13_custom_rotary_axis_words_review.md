# 跨工作台旋转轴 G-code 输出字实施复盘

本轮在 `codex/custom-rotary-axis-words` 分支实现 I01-AXIS。起点为 `c518b66904d124113086134e8901830530891830`，该提交已经包含 Rotary R01—R05 与扇叶补充报告。目标是允许用户保留机床内部 A/B/C 物理关节语义，同时把实际存在的旋转关节映射为固件使用的 G-code 单字母地址。

## 实现判断

`MachineProfile` 原本已有 `JointSpec.post_axis_map`，Tube、Planar、Curve 和 Rotary 也已经复用同一 `postprocess_indexed_gcode()`。因此本轮沿用现有契约，没有重命名内部关节或改写 IK。新增的领域 API 原子更新旋转关节输出字，保留轴向、运动侧、串联拓扑、限位、单位、比例和零偏。GUI 根据机型实际存在的旋转关节动态显示行；AC 机型只显示 A/C，只有机型配置真正包含 B 时才显示 B。

输出地址属于可执行控制器语义。`E/F/G/M/N/P/S/T` 在当前生成方言或控制器命令中已有固定作用，因此机型验证会拒绝这些字，也拒绝重复字、未知关节、线性关节误编辑和缺失映射。`controller_values()` 不再静默省略被请求但没有映射的关节。G-code 头部记录真实机型信息和完整 `CONTROLLER_AXIS_MAP`，便于审计和回读。

GUI 专用对话框会把映射另存为用户机型副本，并经现有 `set_machine` 领域命令应用。受限脚本新增 `tube.set_machine_axis_words()`；HTTP 新增 `/setup/machine/axis-map`，两者走相同 Tube Setup 命令内核。发布后会立即同步已加载的 Planar、Curve 和 Rotary Setup，并刷新各命令内核的并发 epoch。机型快照内容变化进入生成语义哈希，旧产品需重新生成。

## 验证结果

解析真值使用 A→U、C→W。测试确认运动块含 U/W 而不含 A/C，严格回读通过；把首个 U 坐标由 0 改为 1 后，回读精确报告 `p1:U`。架构测试确认四个生成工作台绑定同一后处理和回读函数；同步测试确认三类非 Tube 工作台接收同一 Machine 快照并更新命令 epoch。故障注入还确认 Planar 页面刷新抛错时，Curve 和 Rotary 的 Setup、命令 epoch 与 Stale 失效仍先完成，界面刷新故障不会留下可导出的旧轴字结果。JSON 往返、小写转大写、单位/比例/零偏保持、重复字、保留字、未知/非旋转关节、缺失映射、撤销、GUI 另存应用、脚本解析和 HTTP 路由均有自动化覆盖。

最终聚焦集为 122 passed、55 subtests passed。当前源码全仓结果为 834 passed、3 skipped、138 subtests passed；3 个 skip 均为 Windows 缺少符号链接权限。全仓第一次重跑曾在无关 Planar 导出目录替换处出现一次 WinError 5，单测立即通过，随后完整回归通过。补充刷新异常测试后，聚焦集首次使用系统临时目录时又因目录权限产生 2 个 fixture setup error，改用仓库内 `--basetemp` 后全部通过；失败、复现和最终 JUnit 均保留。`scripts/check_quality.py` 最终 exit 0，覆盖 Ruff、Security Ruff、上下文预算和 148 个源码文件的 Mypy。sdist、wheel 构建及 Twine 检查通过。详细命令、JUnit、环境、哈希和失败历史见[验证清单](evidence/2026-09-13_custom_rotary_axis_words/validation_manifest.json)。

## 文档与界面

[机型配置图文指南](../guides/machine_profiles_zh.md)增加 A/C→U/W 流程、当前 Qt 对话框截图、Stale、脚本、HTTP、保存重开和错误规则；根 README、手册索引、文档索引与 Rotary 手册均已链接。截图为当前 Windows Qt 生产对话框的 `QWidget.grab()` 结果，证明控件和中文文本可见，不替代真人点击、控制器连接或实机试切。

## 能力边界

轴字映射只决定 G-code 地址，不定义新的物理轴。DIY 异形机床仍需在 `MachineProfile` 中提供真实关节拓扑、轴向、运动侧、旋转中心、顺序、限位、单位、比例、零偏、工具与工件链接，并需要对应 IK/FK、碰撞和控制器语义验证。本轮没有新增物理 B 轴算法，也没有取得目标固件、机床标定、现场碰撞和试切证据。独立 Imported NC Review 对任意自定义字仍要求另行注册控制器语义；生成产品的严格回读已经按所选 Machine 快照验证。

## 可复用方法

后续增加真实 XYZAB 或三转轴机型时，应继续保留“内部关节 ID 负责运动学、PostAxisMap 负责控制器地址”的分层。测试至少包含独立轴值真值、错误字拒绝、G-code 篡改回读、项目重开、Stale、四工作台共享发布和目标控制器离线/现场证据。不要用地址重命名掩盖缺失的物理轴、IK、限位或碰撞模型。
