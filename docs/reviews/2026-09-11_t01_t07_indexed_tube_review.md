# T01—T07 Tube Indexed 实施审查

日期：2026-09-11

本记录用于审查当前工作区中 T01—T07 的实现范围、参考来源和本轮验收证据。任务状态以 `docs/planning/progress_tracker.md` 为准。

## 审查结论

当前源码已经形成一条受限的 Tube Indexed 算法链：Operation 输入 → 单支恒定圆截面管体识别 → 中心线楔块分区 → OCCT 截交和 mid-wall 薄壁路径 → 安全转位事件 → Generic XYZAC 参考轴轨迹 → 离线几何、运动和障碍物检查。实现集中在 `src/five_axis_slicer/`，运行时不依赖相邻 `5AxisSlicer` 目录。

这条链覆盖了 T01—T07 的验收范围。本轮已使用项目解释器重新执行算法、UI、相关回归、质量门禁和全仓串行测试，JUnit 与源码/输入指纹保存在 `docs/reviews/evidence/2026-09-11_t01_t07/`。依据下列范围和证据，T01—T07 可以在进度台账中登记为已完成。

## T01—T07 范围核对

| 任务 | 当前实现入口 | 本轮核对的能力 | 保留边界 |
| --- | --- | --- | --- |
| T01 | `manufacturing/setup.py`、`tube_parameters.py`、`tube_controller.py`、`tube_commands.py`、`tube_ui.py` | 管体、入口、出口、基体角色；九项带单位参数；Dirty、范围反馈、JSON 持久化和旧字段默认值；GUI、命令、HTTP、保存重开与引用重绑定回归通过 | 管体角色由用户或上游选择结果确定，不自动把底座并入管体 |
| T02 | `algorithms/tube/geometry.py` | 直管/圆弧管、圆柱/环面恒定圆截面、入口到出口有向中心线、手动 line/arc edge 链、pipe2 实测和稳定错误码 | 支持范围限于单支、无分叉、恒定圆截面 |
| T03 | `algorithms/tube/indexed.py` | 最大楔角和弦高误差共同控制区段；固定构建方向；半开区间归属；尾段居中层；覆盖与边界断言通过 | 分区策略属于当前项目设计推导，不声称复现供应商内部算法 |
| T04 | `algorithms/tube/section.py`、`algorithms/tube/indexed.py` | OCCT 实体/平面截交、闭环恢复、内外环方向、mid-wall 单道路径、弦高采样、材料体积；解析实体和 pipe2 测试通过 | 多道 buildup 属于 T09 |
| T05 | `algorithms/tube/indexed.py` | retract、depart、index start/end、travel、approach、prime 事件；转位零材料体积；安全间隙失败可定位 | Indexed 转位期间不生成沉积材料 |
| T06 | `kinematics/xyzac.py` | Generic XYZAC 两分支、C 角展开、行程、奇异、速度/加速度、刀长、非零回转中心、工件装夹变换和 FK 回代 | 该机型是离线参考模型，不构成实际设备资格 |
| T07 | `validation/indexed_tube.py` | 半径/层位置/楔块误差、喷嘴 R–Z 保守包络、基体/夹具/机床 AABB、已打印 bead capsule、连续运动细分、Error 阻止导出；碰撞与非碰撞样例通过 | 保守离线近似不覆盖热变形、材料流动、机床柔顺性或控制器跟随误差 |

## 本轮验证结果

所有命令均使用 `tmp/pytest9/Scripts/python.exe` 串行执行：

- 只读预检：Python 3.12.7；OCP、CadQuery、Qt、VTK、pytest、Ruff 和 mypy 依赖匹配；QSettings 可写；`issues: []`。
- `scripts/check_quality.py`：Ruff、增量 Ruff、安全 Ruff、格式、context-budget 和 mypy 全部通过；mypy 检查 86 个源码文件。
- `tests/test_tube_indexed_pipeline.py`：19 passed，3.12 s。
- `tests/test_tube_ui.py`：30 passed，2 subtests passed。
- 最终 UI 联合回归：49 passed，6 subtests passed，170.33 s；质量门禁通过。
- 控制器、自动化、项目 IO、重绑定、source update、toolpath、资源、坐标和预览相关回归：158 passed，2 skipped，85 subtests passed，21.88 s。
- 全仓 pytest：430 passed，3 skipped，130 subtests passed，308.59 s。JUnit 计 563 个 testcase，0 failure、0 error。该次运行已覆盖标题宽度调整；随后修正的英文动态反馈由最终 UI 联合回归和质量门禁覆盖。

3 个全仓跳过项都是 Windows 当前权限不允许创建测试符号链接，分别覆盖项目外目标、source 目录和 YAML 文件符号链接拒绝逻辑。它们沿用已登记的环境边界，没有隐藏 Tube 算法失败。命令摘要、跳过项、环境和 SHA-256 见[质量摘要](evidence/2026-09-11_t01_t07/quality_summary.md)及[证据清单](evidence/2026-09-11_t01_t07/manifest.json)。

## 参考来源与独立重写

管状算法的主要工程参考是相邻项目 `F:\【项目和任务】\5AxisSlicer` 中的 Fractal Cortex。固定来源为：

- Fractal Cortex commit：`db29bacc5615fce206b05dc49bd6c52ab92d5351`。
- `fractal-cortex/slicing_functions.py` SHA-256：`87a502cd8d1224d65b5119293eee062624c743355b30a068dea650c6785fba02`。
- Fractal Cortex `LICENSE` SHA-256：`3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`。
- Fractal Cortex `README.md` SHA-256：`c3dc99cf641e418caa718422986671f9c46e4b82d088a802b27b6f0c8b498619`。

本项目从该参考中学习多方向分块、逐块切层、坐标对齐、路径顺序和转位检查的组织方式，再按 V2.0 的 STEP B-Rep、`GeneratedToolpath`、Generic XYZAC 和 `ValidationReport` 契约重新实现。参考文件没有复制进 `src/`，当前运行时也不读取相邻目录。OCCT Modeling Data、`BRepAdaptor_Curve`、`BRepAlgoAPI_Section`、`BRepGProp`，CGAL Straight Skeleton，MoveIt Kinematics 和 FCL 仅作为可核对的公开技术依据；对应链接和适用边界见 [参考资料检索](../planning/reference_research.md)。完整来源表、方法映射和边界见 [Tube Indexed 参考来源登记](../planning/tube_reference_provenance.md)。

当前使用范围是内部传阅，暂无公开发布计划。这一范围说明不能替代第三方许可证事实：Fractal Cortex 的仓库许可证记录为 GPLv3。若未来复制、链接、发布或向外部提供代码或派生版本，应在发布前重新核对完整许可证、对应源码和通知义务；本记录不提供法律结论。

## 未完成事项

T08 仍需把核心算法接入 Generate、成果页、NC 后处理、结果归档和 G-code 回读，形成 STEP → 生成 → 检查 → NC → 回读的产品闭环。T09 的多道 Tube Buildup、T10—T11 的连续螺旋/连续标架和真实机床资格也不属于 T01—T07 的完成范围。当前结果只支持已写明的单支恒定圆截面 Tube Indexed 约束，不能外推为完整 Tube 工作台或实机安全认证。

## 复用方法

后续任务应继续固定所读参考项目版本和文件哈希，分别保存历史测试与本轮测试，先执行与改动直接相关的测试，再执行质量门禁和全仓串行回归。任何由外部资料得到的流程描述、术语或设计推导，都应在文档中区分来源事实、当前实现和尚未验证的假设。
