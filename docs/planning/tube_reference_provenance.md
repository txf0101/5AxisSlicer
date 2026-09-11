# Tube Indexed 算法参考来源与重写边界

登记日期：2026-09-11。本文件记录 T01—T07 实施时实际阅读的相邻工程和上游源码，供当前项目内部传阅、复核和后续维护。当前项目暂无公开发布计划。

## 主要参考项目

管状分块定向切片的主要工程经验来自相邻目录 `F:/【项目和任务】/5AxisSlicer`。其中的 Fractal Cortex 副本来自 Fractal Robotics 的多方向五轴 FDM 切片器；README 标注 Copyright (C) 2025 Daniel Brogan，仓库许可证为 GNU GPL v3。

| 对象 | 固定版本或 SHA-256 | 本轮使用方式 |
| --- | --- | --- |
| Fractal Cortex Git 工作树 | commit `db29bacc5615fce206b05dc49bd6c52ab92d5351` | 固定所读版本 |
| `Fractal-Cortex-main/Fractal-Cortex-main/LICENSE` | `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986` | 核对 GPLv3 全文 |
| `Fractal-Cortex-main/Fractal-Cortex-main/README.md` | `c3dc99cf641e418caa718422986671f9c46e4b82d088a802b27b6f0c8b498619` | 核对多方向分块、用户流程与作者声明 |
| `Fractal-Cortex-main/Fractal-Cortex-main/fractal-cortex/slicing_functions.py` | `87a502cd8d1224d65b5119293eee062624c743355b30a068dea650c6785fba02` | 学习分块、对齐、逐块切层、碰撞检查和转位事件顺序 |
| `5AxisSlicer/README.md` | `bb15f01674a1b5fa1b88311c769ecd0a467cfff8f5c70c290727827b048e224c` | 了解相邻工程的复现范围 |
| `5AxisSlicer/src/five_axis_slicer/core/legacy_engine.py` | `064afdca672d161c36935ac087e2d1aea88435f44f309bc73681936908716cf3` | 了解既有 Python 重写的行为和失败边界 |
| `5AxisSlicer/Open5X/five_axis_slicer/fractal.py` | `4d5c21ad4d2d2fc5a5d92135fc54428ab3e6233db719c6ac1fcdd244b28f88d9` | 了解旧接口如何组织区段和路径数据 |

上游项目入口为 [fractalrobotics/Fractal-Cortex](https://github.com/fractalrobotics/Fractal-Cortex)。本地 Git remote 指向用户保存的副本，所以上表同时记录 commit 与逐文件哈希，避免仅依赖 remote 名称判断来源。

## 方法映射

| 参考流程 | 当前项目的重写位置 | 当前差异 |
| --- | --- | --- |
| 用户定义多个切片方向并把模型分成 chunks | `algorithms/tube/indexed.py` 的中心线楔块和固定构建方向 | 当前方向由有向中心线、最大楔角和弦高误差计算 |
| 把各 chunk 对齐到 XY 后逐层切片 | `algorithms/tube/section.py` 的 OCCT 实体/平面截交 | 当前保留工件坐标，直接构造任意平面截面，不搬移 STL 网格 |
| shell、offset、infill 路径 | `section_tube_layer()` 与 mid-wall 薄壁轮廓 | T01—T07 只实现单道薄壁；多道 buildup 属于 T09 |
| 换块前回抽、抬升、转台运动、接近和恢复挤出 | `_PathBuilder` 的显式事件和非沉积运动点 | 事件、几何路径和轴轨迹分层保存；转位期间材料体积为零 |
| 喷嘴/床碰撞检查 | `validation/indexed_tube.py` 的喷嘴 R–Z 保守包络、障碍物和 IPW 检查 | 当前增加连续运动细分、夹具与已打印体；仍属于离线近似 |

## 重写与许可证边界

T01—T07 的新代码按 V2.0 的 STEP B-Rep、`TubeOperationDefinition`、`GeneratedToolpath`、Generic XYZAC 和验证报告契约重新编写，没有把上述参考文件复制进 `src/`，也没有让运行时依赖相邻目录。现有测试使用解析直管、解析圆弧管和当前 pipe2 STEP 的独立尺寸与拓扑断言。

“内部传阅、暂无公开计划”是当前使用范围，不改变第三方代码的许可证事实。若以后复制、链接或对外提供受 GPLv3 约束的代码或派生版本，应随交付核对完整许可证、对应源码和通知义务。本文是工程来源记录，不替代针对具体发布形态的法律判断。

## 其他技术依据

几何与验证还参考了 OCCT 的 Modeling Data、`BRepAdaptor_Curve`、`BRepAlgoAPI_Section`、`BRepGProp` 文档，二维偏置研究入口为 CGAL Straight Skeleton，运动学组织参考 MoveIt Kinematics，连续碰撞研究入口为 FCL。可核对链接和适用边界集中在[参考资料检索](reference_research.md)。
