# 五轴运动仿真与视频导出调研

更新：2026-09-20。范围是切片结果生成后的机床运动回放、床台和喷头场景、分段倍速与视频导出。本文只记录可核对的设计依据，不表示第三方项目已经集成。

## 1 当前项目基础与缺口

当前项目已经保存完整 G-code timeline，并在成果页提供播放、暂停、进度和阶段过滤；各制造工作台还会生成带严格递增 `time_s` 的 `MachineAxisTrajectory`。因此运动仿真的时间真值应来自轴轨迹，G-code timeline用于命令、事件和源码定位，不能另建一套按行号匀速播放的时间模型。

还缺少机床部件树与关节变换、床台/喷头模型、沉积增量显示、碰撞状态、离线逐帧渲染和视频编码。运动画面只能表达所提供的运动学、场景和碰撞近似，不能自动证明机床标定、动态跟随、真实喷嘴扫掠或试切安全。

## 2 可参考项目

| 项目 | 可借鉴内容 | 限制与许可证判断 |
| --- | --- | --- |
| [LinuxCNC Vismach](https://www.linuxcnc.org/docs/stable/html/gui/vismach.html) | Python 定义机床部件，支持盒体/圆柱等简易几何、STL导入、平移/回转关节和子装配；LinuxCNC还提供 [XYZAC/XYZBC五轴转台配置](https://github.com/LinuxCNC/linuxcnc/blob/master/docs/src/motion/switchkins.adoc) | 架构最接近本需求。LinuxCNC为GPL系列项目，不复制其实现代码；只借鉴公开的部件树和关节驱动思路 |
| [FreeCAD CAM Simulator](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/CAM_Workbench.md) | 工件、刀具、时间控制和加工结果显示；CAD/Qt组合与本项目接近 | 重点是减材扫掠，不作为五轴增材运动真值。FreeCAD核心为LGPL-2.1，若未来直接链接代码需单独核对模块许可 |
| [CAMotics](https://github.com/CauldronDevelopmentLLC/CAMotics) | G-code仿真、工程配置、重算和加工结果交互 | 官方定位为三轴CNC，主项目为GPL-2.0+；不嵌入或复制代码，只参考交互和项目组织 |
| [PyBullet](https://github.com/bulletphysics/bullet3) | URDF/SDF/MJCF关节模型、碰撞查询、正逆运动学和DIRECT无窗口运行 | 适合作为后续独立碰撞对照。首版引入会形成第二套场景/渲染/坐标链，暂不作为主引擎 |
| [VTK](https://vtk.org/doc/nightly/html/classvtkWindowToImageFilter.html) | 当前项目已经使用；`vtkWindowToImageFilter`可把渲染窗口逐帧转为图像 | VTK wheel是否带MP4 writer取决于构建选项；官方构建说明显示Windows `vtkMP4Writer`需要Media Foundation，不能假定当前wheel可直接编码MP4 |
| [FFmpeg](https://ffmpeg.org/ffmpeg.html) | 把无损PNG帧序列稳定编码为H.264/MP4；可记录固定帧率、分辨率和编码参数 | 作为外部可选编码器探测，不自动安装。不可用时保留PNG帧与清单，并明确视频导出受阻 |

## 3 推荐技术路线

首版沿用PyQt5 + VTK，不把完整物理引擎放入主路径。核心分为四层：

1. `MachineSceneDefinition`：部件、父子关系、视觉模型、碰撞模型、局部坐标和外观。
2. `MachineScenePose`：在给定仿真时间从 `MachineAxisTrajectory` 插值关节值，计算部件的Machine-frame变换。
3. `MotionSimulationSession`：统一播放范围、速度、相机、可见层、沉积进度和诊断；GUI与导出使用同一快照。
4. `SimulationVideoExporter`：按仿真时间采样逐帧渲染，再调用已探测的编码器生成视频和 `simulation_manifest.json`。

内置场景用参数化盒体、圆柱、圆盘和圆台组合出基座、XYZ龙门、A/C床台和喷头。后续自定义模型加载作为独立任务：每个部件可选择内置几何或外部STEP/STL/OBJ/glTF，必须显式填写单位、局部原点、轴向和缩放，保存文件哈希；加载失败回退到内置示意体，不静默套用未知单位。

## 4 时间、倍速和分段语义

视频采用固定输出帧率。选择仿真区间 `[t0, t1]` 和倍速 `s` 时，视频时长为 `(t1-t0)/s`，第 `k` 帧对应 `min(t1, t0+k*s/fps)`。32×和165×是预设，另提供1×、8×、64×与自定义正数。

首版只支持一个连续区间，可用拖柄、时间输入、操作、阶段、层或G-code行范围确定。交互播放可以为保持流畅跳帧，导出则逐帧计算确定性姿态，允许取消，失败不覆盖上一份有效视频。

## 5 结论

该功能可在当前架构上实施。首版采用“内置参数化AC机床场景 + 当前MachineAxisTrajectory + VTK确定性逐帧渲染 + FFmpeg可选编码”。用户自定义床台和喷头模型、精确碰撞体、复杂沉积实体和物理动力学分阶段加入。LinuxCNC Vismach是机床装配建模的主要设计参照，FreeCAD/CAMotics用于交互对照，PyBullet保留为后续独立碰撞后端候选。

