# 论文核心 AC 版本范围与来源审查

更新：2026-09-13。任务状态只在 [progress_tracker.md](progress_tracker.md#主表) 维护；本文定义 PC00—PC07 的范围、取舍和证据要求。用户本轮要求优先完成论文案例，并批判性核对论文。六工作台完整产品仍作为长期规划，不再阻塞论文核心版交付。

## 1 证据基线与论文可信边界

软件基线：`9203debccb42f142da02f852e4b45bb0d60feb11`。论文源为用户提供的 `manuscript.docx`，与仓库 [存档](../references/own_ac_printer/manuscript.docx) 的 SHA-256 均为 `3a4fa546b0468f114b9d86c1125f9b03a363286f67caaafb3d44d34974b25c59`。本轮用已存档的[正文与表格抽取](../references/own_ac_printer/manuscript_text.txt)核对摘要、2.1—2.4、3.1—3.3 和案例表；未重新审查公式对象、图片原始数据或实验仪器记录。抽取文件的 TABLE 0 为正文 Table 1，引用以论文标题及正文编号为准。

证据优先顺序：可追溯 CAD/NC/控制器配置/原始实验记录与当前运行结果 → 可复算的几何及运动真值 → 论文叙述。发现冲突时保留差异并修正技术契约或论文表述，不能为迎合文字而改出错误算法。完成软件实现也不能倒推历史实验全部由本版本生成。

| 论文主张或数字 | 当前核对结果 | PC01/PC04/PC06 必须解决的事项 |
| --- | --- | --- |
| 摘要与 §3.1 称四案例由集成软件生成 | 用户已说明部分历史 NC 来自外部切片及手工拼接；V2.0 Freeform 仍无生成器 | 每例登记 CAD→几何路径→后处理→人工修改→实测文件来源；需修改论文时明确“历史流程”与“当前复现版本” |
| §2.2/§3.1 使用相对 E | 当前 `postprocessing/indexed_tube.py` 固定输出 M82 绝对 E | 以目标固件及 NC 实际模式为准，注册 E 模式并独立回读；绝对 E 与相对 E 可表达相同体积，模式不一致且误读才产生错误 |
| A±180°、C±360°，且限制累计 C | 自有机型 JSON 已记录这两个位置范围；速度、加速度及线性轴限仍为空 | 实测或确认参数来源；位置范围与累计绕线指标分别定义，不能把两轴都写为±180°；不虚构绕线阈值 |
| 转位前绝对 Z=20 mm | 只规定位置，不能证明所有几何的扫掠净空；也未证明 Z 正方向与退离方向一致 | 确认 Machine frame、机床零点和整段扫掠；不安全时拒绝该流程，不能无条件插入“安全高度” |
| 换料时相对 Z+20 mm | §2.3 明确与绝对转位位置不同 | 宏保存/恢复 G90/G91、M82/M83、E 基准、F、A/C 和返回位置；相对动作在固件实际语义下核验 |
| 一条 G1 协调 XYZAC/E/F | 当前 Rotary 用 G93 逆时间，论文只给出 F 示例，未证明该固件支持 G93 | 固定控制器版本、定制运动学和 F 单位；不能由 G1 中出现 A/C 或轴字重命名推出协调控制已成立 |
| 扇叶4次、叶轮8次选择命令 | T0 初次选择、同通道重复选择和实际材料转换数量可不同 | 分别统计选择命令、有效通道变化、人工准备暂停；不把4/8次命令直接等同4/8次成功换料 |
| 85→47 min、24.00→18.79 g | 按文中数值为44.7%时间、21.7%总丝材下降；原文未单独称量支撑 | 数值可作该次实验描述，不能声称支撑材料下降21.7%，也不能用模拟时间验证实测时间；核查匹配参数及重复次数 |
| 厚度偏差 −3.82%～+7.67% | 论文明确为代表性测量，未建立重复性或统计过程能力 | PC06 不设置必须复现这些实验改善率的算法门槛；无原始测量时列未核实 |
| 其他旋转配置适配 | I01-AXIS 已支持输出字；当前实测/验证主线限 AC | 字母映射与不同机构 IK/FK 分开；未知第二机构不写“已支持任意异形机” |

## 2 四种模型的覆盖判断

| 论文案例 | 可复用的当前能力 | 仍需开发或重新验证 | 首版验收范围 |
| --- | --- | --- | --- |
| 半球预制基体上的图案 | STEP 选面、Curve 已有边链和指定法向、共享 AC/产品链 | 图案投影、trim 裁剪、法向连续与接缝；图案不是现成 STEP edge 时 Curve 不能自动生成 | PC02 单个修剪面上的图案轨迹；不要求打印整个半球实体 |
| 扇叶薄壁及多材料版本 | Planar 底座、Rotary 圆柱轮毂；Curve 可沿给定边生成筋条 | 三片 B-spline 叶片表面路径、90°工序转位、分区材料切换和完整覆盖 | PC02 有限导引线与叶片面组；PC03 切换；PC04 工序连接 |
| 弯管 pipe2 | Tube Indexed 最接近论文分段策略；Planar 可作三轴对照 | T04/T07/T08/T12 仍待验证；需按自有 A±180°、C±360°及真实控制器重验 | PC05 完成 pipe2 全流程；不以不同 Continuous 策略强求逐点重现 Indexed NC |
| 叶轮及多材料版本 | Curve 已验证单条真实边的三种产品；Planar/Rotary 可做部分基础 | 单条边通过不能证明全部叶片覆盖；缺有限多面、多层路径及材料计划 | PC02 有限连续面组与显式工序；PC03 通道转换；PC06 全件回归 |

结论：现有工作台能复用大量基础，但尚不能覆盖四例完整功能。最低新增算法是受限 Freeform 和材料事件调度；无需先完成 Research 的场优化、应力路径或完整第二机型。已有 Rotary 圆柱/圆锥限制不能因叶片具有回转外观而放宽。详见[扇叶与 pipe2 量测报告](../reviews/2026-09-13_pipe2_model_manual_gcode_comparison.md)。

## 3 核心版执行约定

执行顺序为 PC01 契约与来源 → PC02 受限 Freeform → PC03 多材料 → PC04 自有 AC 后处理 → PC05 Tube 收口 → PC06 四例回归 → PC07 本地封装。控制器资料盘点在 PC01 即开始，不必等几何算法完成。PC00 只表示本轮范围和候选资料审查完成。

- PC01：冻结四例 CAD、面/边选择、预定义材料区域、历史 NC、机床及宏文件的来源、版本和哈希；确认坐标、单位、E/F 模式、几何容差及失败条件。未获原始宏/标定时可定义离线契约，但实机资格保持未验证。
- PC02：复用 F01—F05 中四例所需的子集；单修剪面或有限连续面组加边界/导引线，完成贴面、薄壁、有限多层。检查 UV 到三维度量、弦高、真实道间距、极点/周期、trim 孔洞、法向方向、投影多解、层间自交、覆盖遗漏和安全跨区连接。共用 Toolpath/events 与生成状态，不创建重复框架。交付 PC02 不自动关闭整个 F06。
- PC03：增加 material_id、channel_id、材料区域与可序列化计划；结构化 switch/cut/retract/park/load/temperature-wait/purge/prime/resume 与显式准备暂停。覆盖传感器未到位、温控超时、缺通道、取消及恢复。T0—T3 宏既保留调用，又有可检查的语义展开；包含清洗损耗与沉积体积的分别统计。计划进入 hash/Stale、撤销和 project I/O；仅支持用户预定义区域。
- PC04：沿用 I01-OWN/I01-AXIS，封装目标 AC 的真实链、工具长度、零偏、旋转中心、位置/速度/加速度限位、分支、累计 C、FK 回代及扫掠检查。固化 G90/G91、M82/M83、G93/G94 的目标固件含义，区分两种20 mm动作，保留宏模式恢复；拒绝未注册控制器解释的可执行导出。
- PC05：逐项复核 AUD-01/AUD-02 对 Tube 的剩余问题，以独立 pipe2 几何/体积/覆盖和自有 AC 运动测试决定 T04/T07/T08 是否关闭。T12 仍要求三操作完整阶段门；仅通过 pipe2 Indexed 不足以关闭整个 Tube。修正首页 Planar Preview、Tube Setup 旧标签，使显示能力与验收资格分别表达。
- PC06：从当前 CAD 和材料区域生成四例全部所需工序，各例输出六件套；核对法向、A/C 连续性、端点/长度/道间距、覆盖、材料量/切换、历史 NC frame 与策略差异。追加双通道无中途准备暂停的独立案例。GUI/脚本/HTTP 共用命令，检查取消、Error 阻断、Warning 保留、Stale、重开/重绑；真实 Viewer、双语三尺寸图与恢复记录齐全。
- PC07：范围内最终 pytest、质量检查、构建、包检查及干净环境启动；安装包、当前图文教程、四例项目、许可证通知与结果清单可找到。逐文件指纹；大体积中间输出留在制品归档，Git 保留摘要/代表性证据，具体证据搬迁另行执行。论文历史实验和本轮软件验证分开报告。

软件离线完成门与真实机器资格分列。缺原始标定不能伪造数字，也不阻止已定义范围内的离线研发；如果 PC07 只完成离线封装，交付标题和 README 必须明确这一点。

延期范围：F01—F06 超出四例的完整通用操作、任意实体自动曲层分解、自动多面规划、自动材料分区/优化、X01—X06、完整 XYZAB/任意新机构、Tree/Organic 支撑、六工作台20操作总验收 I01—I04。原编号与验收条件保留，恢复时单独排期。

## 4 本轮开源资料核查与采用决定

2026-09-13 实际通过 GitHub HTTPS API 核对下列仓库 commit、README、许可证，并读取表列关键入口。未安装或运行上游程序，未复制第三方实现进入产品。许可证许可复用与技术上可直接运行是两个独立判断。

| 项目与固定版本 | 本轮实际检查 | 可用部分及集成成本 | 决定 |
| --- | --- | --- | --- |
| [Open5x](https://github.com/FreddieHong19/Open5x/tree/500a786e51447b47e00d2a5ca3dcc938ae542926)，[MIT](https://github.com/FreddieHong19/Open5x/blob/500a786e51447b47e00d2a5ca3dcc938ae542926/LICENSE) | `Grasshopper_Definition/README.md`；`.gh` 路径与先前静态提取记录 | 点/法向、五轴输出、挤出组织优先参考；MIT 允许按条件复用。运行完整图依赖商业 Rhino、Grasshopper/Heteroptera；本地静态解析不能代替执行 | 优先小组件移植候选，保留作者/许可和修改记录；不整体引入 Rhino 为产品依赖 |
| [COMPAS Slicer](https://github.com/compas-dev/compas_slicer/tree/680d1749a4b7c3b1300ebb447257d6af44e19324)，[MIT](https://github.com/compas-dev/compas_slicer/blob/680d1749a4b7c3b1300ebb447257d6af44e19324/LICENSE) | `slicers/uv_slicer.py` 全文、`scalar_field_contours.py` 接口、`pyproject.toml` | UVSlicer 是带 UV 顶点的三角网格等值线，等 UV 步进并不保证等三维道距；代码有边界启发式 `0.05`。当前依赖 COMPAS≥2.15、compas_cgal≥0.9.3 | 可挑选 MIT 部件经适配复用；不直接替代 STEP trimmed BRep。compas_cgal 许可实读为 LGPLv3，CGAL 下游包仍需逐项核查，不能称全依赖 MIT |
| [CadQuery](https://github.com/CadQuery/cadquery/tree/a6bedc0d7ceac1829290037259465e918fc00e80)，[Apache-2.0 正文](https://github.com/CadQuery/cadquery/blob/a6bedc0d7ceac1829290037259465e918fc00e80/LICENSE) | README、LICENSE；API 的 SPDX 自动识别为 NOASSERTION，按正文核对 Apache-2.0 | 现有 CadQuery 2.7.0 继续用于解析 STEP 真值；产品几何优先复用已有 OCP/OCCT 投影、微分、trim 分类 API | 最高优先级复用已有栈；不为本轮研究升级运行环境。OCP/OCCT 自有许可另列，不能沿用 CadQuery 许可覆盖 |
| [Clipper2](https://github.com/AngusJohnson/Clipper2/tree/f9c5eb6e14a59f6f5d65fbfb3564519a561cf4fd)，[Boost 1.0](https://github.com/AngusJohnson/Clipper2/blob/f9c5eb6e14a59f6f5d65fbfb3564519a561cf4fd/LICENSE) | README、LICENSE、`CPP/Clipper2Lib` engine/offset 路径 | 可直接集成多边形布尔/偏置部件；C++17/DLL 或另选绑定有打包成本。用于 UV 裁剪后还需曲面度量及周期处理 | 备选，现有 OCCT 不满足具体反例时再引入；本轮未深入实现或编译 |
| [Klipper](https://github.com/Klipper3d/klipper/tree/2d7717e3b62ea2fe3401b27f54f8681f80451c69)，[GPLv3](https://github.com/Klipper3d/klipper/blob/2d7717e3b62ea2fe3401b27f54f8681f80451c69/COPYING) | README、COPYING、`docs/Command_Templates.md` 中保存/恢复模式与模板求值时序 | 宏调用接口与状态恢复可参考；官方版本不能直接证明用户定制 XYZAC 或 G93 支持 | PC04 以实际固件/宏为准，优先独立控制器接口；不复制固件进切片核心 |
| [Happy Hare](https://github.com/moggieuk/Happy-Hare/tree/ef8431c420231ca52e0ee3c9d8dfafaa7af544ea)，[GPLv3](https://github.com/moggieuk/Happy-Hare/blob/ef8431c420231ca52e0ee3c9d8dfafaa7af544ea/LICENSE) | README、LICENSE、`config/macros/mmu_sequence.cfg` 的 pre/post load/unload、park、模式恢复 | 换料状态机、切断/退料/装料/恢复回调参考；依赖 Klipper 和适配硬件，不保证兼容用户凸轮送料器 | 优先接口/流程参考。若实际集成或分发 GPL 代码需满足许可，独立进程不自动豁免；首版不引入整套 MMU 驱动 |
| [MAGE Slicer](https://github.com/gear2nd-droid/MageSlicer/tree/0026f8013e589a8f1c8dea6f60e34773f3fa6d55)，[PolyForm Shield 1.0.0](https://github.com/gear2nd-droid/MageSlicer/blob/0026f8013e589a8f1c8dea6f60e34773f3fa6d55/LICENSE.txt) | README、完整 LICENSE.txt；NURBS 方法及既有研究登记 | 几何方向相关，但 Noncompete 明确覆盖不同语言/平台、免费产品；公开可见不代表宽松开源 | 阅读公开方法和产品说明；本版不移植源码，获得额外合适许可后再评估 |

Siemens [多轴增材产品页](https://plm.sw.siemens.com/en-US/nx/products/nx-am-multi-axis/)及 [2506 Freeform Thinwall 发布说明](https://blogs.sw.siemens.com/nx-manufacturing/whats-new-in-nx-for-manufacturing-june-2506/)本轮访问均为 HTTP 200，用于支持选面、驱动方向及步距的产品语义。它们不提供可复制算法源码；私有 NX 手册正文仍未获得开放访问证据。PrusaSlicer/CuraEngine、S³-Slicer、ReinforcedFDM 的既有来源保留在[参考资料](reference_research.md)，本版不新增平面引擎或场优化依赖。

允许的代码复用在实施时应冻结到具体文件和 commit，保存许可证/版权通知、依赖清单、修改说明和独立反例；达到本项目工具链、路径/坐标语义、单测和包检查条件后才合入。许可审查不得用“翻译代码”或“仅内部传阅”代替。

## 5 本轮局限

本轮完成范围调整、静态代码比对和来源研究，不代表 PC01—PC07 已开发或已运行上游。论文实验数字未获得新的原始记录核验，固件/宏和现场设备均未执行。此前 834 passed、3 skipped 属 `9203deb` 验证记录，本轮文档变更没有重跑 pytest，也不改写该历史记录。
