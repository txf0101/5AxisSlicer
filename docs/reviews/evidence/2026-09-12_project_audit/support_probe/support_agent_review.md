# P07 Planar 支撑独立审阅

审阅时间：2026-09-12 12:29（Asia/Shanghai）。范围为 P07 的支撑域、XY/Z 间隙、路径检查、G-code 输出和阶段证据。本轮只读产品源码，新增解析复现和审阅产物；没有修改产品代码、项目测试或台账。

使用的 Skills：`five-axis-workbench-development`、`five-axis-slicer-validation`。环境复用主审本轮已通过的 `tmp/pytest9/Scripts/python.exe` 预检；未运行 Qt 测试或全仓回归。本次纯领域探针退出码为 0。

## 当前完成情况

12:29:10 归档的 live 台账版本（修改时间 12:23:06）将 P07 列为“进行中”，P01—P06 已完成。live 手册（修改时间 12:26:22）开头已写 P01—P07 完成；当前存在其他任务并行收尾，应由主审在最终时点核对状态，不能据此直接认定发布文档错误。

固定源码位于 `tmp/project_audit/frozen`。该快照已有 Grid/Lines、悬垂与空中岛检测、平台连通性、主体/接触层、共享 Toolpath、六件套、回读和单操作产品状态。不可达区域会形成 Error 并阻断 G-code；没有支撑时产品适配层抛出 `planar.support_not_required`，控制器记录 Error。

截至上述时点，P07 `real_model/summary.json` 只有新建的解析悬空长方体 STEP，33 条沉积段，66 个路径点，支撑体积 61.86 mm³，回读通过。该摘要没有 `existing_fan_case`。脚本 `planar_p07_real_model_evidence.py:293` 支持可选现有模型分支，但入口 `:401` 只在给出 `--fan-model` 时调用。现有三叶扇模型的 P06 证据不能转记为 P07 现有模型支撑验证。

## 确认发现：支撑空移穿过目标零件体积，检查仍允许导出

建议优先级：P1；影响离线 G-code 的路径规划与检查。这里确认的是目标 CAD 体积相交，不能从这一点独立推断真实设备已经发生碰撞。是否与“已打印体”相撞，还取决于支撑和零件的实际生成顺序。

解析模型为一个连通实体：柱体 `X=4..8, Y=2..8, Z=0..2.4 mm`，顶部平板 `X=0..12, Y=0..10, Z=2.2..3.2 mm`。采用层高 0.5 mm、首层 0.5 mm、末层 3 mm、道宽 0.6 mm、XY gap 0.4 mm、Z gap 0、Grid、主体间距 1 mm、接触层 2 层、接触间距 0.6 mm；参数完整记录于探针摘要。

实测结果：178 个路径点、57 条 travel 与柱体内部相交，`exportable=true`、`status=warning`、`readback_passed=true`。唯一诊断为 `xyzac.rotary_singularity`。检查报告中沉积越界 0、体积差 0。

最简单的证据段是 `point-0000008 → point-0000009`：Build 坐标 `(0.3, 2.8, 0.5) → (8.8, 2.8, 0.5)`，其中 X=4..8 穿过柱体。六件套中的 G-code 确实保留该直线空移，并没有插入抬升或绕行。G-code 使用已记录的参考机床变换与 2 mm 工具长度，不能把其 Machine XYZ 数值直接当作 Build 坐标。

源代码依据（行号针对固定副本）：

- [`support.py:281`](F:/【项目和任务】/5AxisSclicer_V2.0/tmp/project_audit/frozen/src/five_axis_slicer/algorithms/planar/support.py:281) 将各支撑线逐条交给共享 `_ZigzagBuilder._add_path`。
- [`zigzag.py:99`](F:/【项目和任务】/5AxisSclicer_V2.0/tmp/project_audit/frozen/src/five_axis_slicer/algorithms/planar/zigzag.py:99) 在两条路径之间直接发出目标点 travel，没有障碍物输入或避让逻辑。
- [`validation/planar.py:65`](F:/【项目和任务】/5AxisSclicer_V2.0/tmp/project_audit/frozen/src/five_axis_slicer/validation/planar.py:65) 跳过所有非 deposition 段。
- [`planar_product.py:567`](F:/【项目和任务】/5AxisSclicer_V2.0/tmp/project_audit/frozen/src/five_axis_slicer/postprocessing/planar_product.py:567) 支撑资格只合并轴轨迹诊断、沉积域越界和体积差；没有空移障碍检查。

最小修改建议：先补充明确的已打印层/实体障碍输入，至少检测 travel 中段与这些障碍的相交；无安全路径时产生可定位 Error 并阻断导出。有可行避让时生成显式抬升、平移、下降，或平面绕行 Toolpath，再复用现有轴轨迹和回读。抬升不能直接使用固定数值，需由障碍高度、喷嘴外形和当前层序确定。

验收条件：本解析模型中，一旦柱体被纳入已打印障碍，57 条原始相交空移必须被安全替换或阻断导出；保留无障碍直线路径案例，确认没有无条件增加长距离空移；对中段碰撞、端点无碰撞的情况有独立几何真值；新的移动和回抽/补料事件在 G-code 回读后保持顺序。

证据目录：[`support_probe`](F:/【项目和任务】/5AxisSclicer_V2.0/docs/reviews/evidence/2026-09-12_project_audit/support_probe)。其中包含真实 STEP、六件套、完整参数与57条相交线的 `summary.json`、执行脚本副本、输入/源码/脚本/各产物 SHA256。独立真值用线段与解析盒的 slab 区间相交，不调用支撑算法的包含函数；为排除边界触碰，将盒边界内缩 1 μm。

## 能力边界：支撑与零件目前按操作独立导出

[`planar_controller.py:230`](F:/【项目和任务】/5AxisSclicer_V2.0/tmp/project_audit/frozen/src/five_axis_slicer/planar_controller.py:230) 和 [`planar_controller.py:277`](F:/【项目和任务】/5AxisSclicer_V2.0/tmp/project_audit/frozen/src/five_axis_slicer/planar_controller.py:277) 均接受单个 operation，生成或导出对应产品。当前支撑 Toolpath 自身按层递增，但源码未见 Planar 支撑/零件多个操作按层合并的产品入口；P07 G-code 只包含支撑沉积。

台账的 P07 判据没有明确写入联合逐层编排，因此不把缺失该入口单独列为已承诺功能 bug。不过它限制了“打印完整带支撑零件”的端到端结论，也使空移碰撞的已打印障碍时序缺少依据。不能把两个完整 G-code 文件直接拼接当作联合制造验证。

修改方案建议把逐层合并列为单独的集成工作包：统一层网格、支撑/零件参数兼容性、同层顺序和起终点移动，保留 operation/stage/layer 来源；用中央柱+顶板模型验证零件从平台打印、支撑同步增长、到达顶板时已完成必要支撑；对不同层高/坐标/喷嘴等不兼容输入给出明确拒绝。是否纳入首批修复由主审向用户提出具体范围。

## XY/Z 间隙与检查口径

本次未确认 XY/Z 间隙计算本身有错误。现有实现与已声明的离散层口径一致：

- [`support.py:142`](F:/【项目和任务】/5AxisSclicer_V2.0/tmp/project_audit/frozen/src/five_axis_slicer/algorithms/planar/support.py:142) 对 Z gap 除以层高向上取整，接触层与最高支撑沉积平面分离至少一个层高加量化间隙。该参数不等同于与原始 BRep 任意底面的精确最短距离。
- [`support.py:146`](F:/【项目和任务】/5AxisSclicer_V2.0/tmp/project_audit/frozen/src/five_axis_slicer/algorithms/planar/support.py:146) 把每层零件按 XY gap 扩张作为障碍，`:155` 只保留平台连通竖直柱，`:263` 再内缩半道宽来放置支撑中心线。
- [`planar_support_product.py:33`](F:/【项目和任务】/5AxisSclicer_V2.0/tmp/project_audit/frozen/src/five_axis_slicer/postprocessing/planar_support_product.py:33) 要求产品层范围从 Build Z=0 上方一个层高开始，避免截掉平台层。

现有 `test_planar_support.py` 含非零 XY gap、分数 Z gap 向上取整、孔洞保留和下方实体阻断等解析断言。普通支撑是稀疏结构，覆盖率小于100%本身不是算法错误。检查模块目前为离散 XY 沉积中心线与体积一致性检查，不能直接证明整段喷嘴扫掠、层间附着、强度或可拆性。

## 并行修改和本轮局限

主审固定副本回归发现的取消异常被包装问题，live `support.py` 相比固定副本已增加 `GenerationCancelled` 重抛；该文件修改时间为12:22:21。主审随后报告当前 P07 三个相关测试文件复测为 46 passed / 6.52 s，冻结副本的两个失败均在并行任务修复后复测通过，不列为剩余缺陷。它们与本探针的 travel 结果无关：本次检查的两版 `support.py` 差异只在异常处理分支。

没有重新执行 P07 全仓或 Qt 测试，没有真实控制器、机床标定或现场试打印。本审阅没有把未规划的 Tree/Organic、多材料、模型中途起撑列为缺陷。建议主审把“真实现有模型 P07 证据”“单操作到完整带支撑零件的编排范围”“空移碰撞检查”分开说明并纳入具体修改方案。
