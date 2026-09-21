# FAN15 四例算法产品化计划

日期：2026-09-21。输入基线为提交 `4834caa` 的四例完整离线 NC。该基线证明算法、AC 逆解、全流回读和实际路径图；它没有证明三种新增实体填充已能从软件界面或公共命令入口使用。

## 当前差距

- 弯管使用现有 Tube 产品链，但模型旁最终温控包装仍由 `scripts/finalize_pipe_offline_nc.py` 完成。
- 球面实体、一般曲面实体和径向叶片填充算法已经位于 `src/five_axis_slicer/algorithms/`，模型选择、基体路径装入、工序组合和最终导出仍由三个 `scripts/finalize_*_offline_nc.py` 编排。
- Freeform 工作台当前只持久化有限面组和导引线，不能表达球面 body 组、曲面实体的 face/opposite-face/root-edge 组或径向叶片的 hub/root-face 组。
- 弯管完成过真实模型加载和四角色鼠标拾取；其余三例没有完成真实 GUI 的选择、生成、预览、导出和保存重开。最近一次 Computer Use 在应用枚举阶段返回 `nodeRepl.fetch request failed`。
- 算法经验已进入复盘和个人 Skill；学习总册仍声明受限 Freeform，不包含三种新增完整实体操作。

## 实施顺序

| 子项 | 实施内容 | 完成判据 |
| --- | --- | --- |
| FP01 操作契约 | 增加球面实体填充、一般曲面实体填充和径向实体填充操作；全部几何角色使用稳定引用，参数和选择可 JSON 往返、重绑和产生语义哈希 | 不含示例 body/face/edge ID；正常、重复、错类型、缺引用和拓扑漂移测试通过 |
| FP02 公共产品链 | Freeform 控制器按操作类型调用相应生成器；公共工序序列、AC IK、温控、严格回读和六件套导出取代 finalizer 中的重复编排 | GUI、脚本、HTTP 调用同一命令；finalizer 只允许作为薄的回归驱动器，不保存另一套生成逻辑 |
| FP03 完整作业组合 | 用显式作业顺序组合 Planar/Tube/Freeform/转位路径，保留来源、非挤出转移、取消、Stale 和旧结果 | 四例完整程序可由项目状态重建；缺工序、错误顺序和挤出转位拒绝 |
| FP04 UI | 为三种操作提供实体/面/根边拾取、参数、生成/取消、问题、预览、导出和保存重开 | Qt 控件测试覆盖选错类型、漏选、应用、Stale、Error 禁止导出和重开；中英文代表尺寸无关键遮挡 |
| FP05 真实流程 | 用四个真实 STEP 执行加载、选边/面/体、生成、预览、导出、回读和项目重开 | 自动化脚本与 Computer Use 证据分开；Computer Use 不可用时只把真实点击列为受阻，不能用脚本冒充 |
| FP06 教程与封装 | 更新学习总册、Freeform/Tube 手册、案例迁移检查单、Skill、台账和复盘 | 示例只作练习；说明怎样判断操作模式、怎样重新选择几何和参数，以及离线/实机边界 |

## 普适性边界

- `spherical_solid_fill` 支持可由同一球心、同一基底半径和上半球图表描述的实体组；不把任意双曲率面自动归类为球面。
- `surface_solid_fill` 支持有明确受支撑根边、成对近似法向偏置面和可建立单调面内距离的修剪实体；任意拓扑、分叉面和多值投影必须拒绝。
- `radial_solid_fill` 支持围绕明确旋转中心/轴、从 hub 有限道宽承接并径向增长的叶片；不假设 hub 必须是圆柱，也不把该策略推广到所有叶片。
- 自动建议可以给候选，正式生成必须保存用户确认的几何角色；算法不得依赖示例拓扑编号。
- 参考 AC、PLA 和默认喷嘴参数仍为离线参考。碰撞、真实机床标定、动态限制、控制器宏和试切分别保留。

## 恢复入口

继续工作先读本计划、`progress_tracker.md` 的 FAN11—FAN15、`2026-09-20_fan15_repairs.md` 和当前 diff。FP01 从 `manufacturing/freeform_parameters.py`、`freeform_operation_service.py`、`freeform_controller.py` 和 `postprocessing/freeform_product.py` 接入，不直接从 UI 调算法。每完成一个子项，实际重切至少一个真实模型，并把首次失败与最终证据写入同一复盘。
