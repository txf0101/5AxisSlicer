# 2026-06-11 前置选择器首版复盘

## 目标

本轮实现面向教学和实验用途，核心任务是把外部 STEP/STP 中的多实体和拓扑边线变成可视、可选、可保存的对象。当前软件不推断制造语义，所有分组都以用户显式选择为依据。

## 取舍

- CAD 内核选用 OCP/CadQuery。STEP 读取、solid 展开、edge 枚举均来自 BRep 拓扑，避免把 STEP 先转网格后丢失拓扑。
- 界面按 PyQt5 实现。用户已明确改用 PyQt5，本机 base 环境也具备 PyQt5、VTK、OCP、CadQuery；`5AxisSlicer` 环境已有 CAD 与渲染依赖，后续补 PyQt5 即可运行 GUI。
- 渲染层采用 VTK。body 作为独立 actor，edge 以 polyline actor 表达；选择高亮集中由 viewer 管理，方便 HTTP 接口和鼠标操作共享同一套状态。
- 自动化接口采用本地 HTTP。GUI 操作、模式切换、视角控制、保存项目都可由脚本触发，后续可以接入桌面自动化或回归测试。

## 可复用方法

1. 测试样本由 CadQuery Assembly 生成，能稳定得到两个 solid，适合做多实体导入回归。
2. `project.json` 保存源 STEP 哈希、body/edge ID 和选择结果，后续特征分组可追加到 `manufacturable_feature_groups`。
3. 所有外部资料路径和测试产物都由脚本生成，避免依赖手工样本。

## 后续工作

- 补充真实工业 STEP 样本，记录不同导出器的 assembly/body 表现。
- 对 edge picking 做更细的像素命中校验，必要时合并为单一边线 polydata 并用 cell data 回溯 edge ID。
- 为大模型增加渐进加载和边线显示抽稀开关。
