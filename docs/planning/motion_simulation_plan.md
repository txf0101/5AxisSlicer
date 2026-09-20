# 五轴运动仿真与动画视频导出开发计划

版本：2026-09-20 v1。执行状态见[运动仿真开发台账](motion_simulation_tracker.md)，资料判断见[专项调研](motion_simulation_research.md)。本计划不授权自动安装FFmpeg、对外发布或实机运行。

## 1 目标和首版范围

用户在软件中生成或载入有效结果后，可以进入“运动仿真”页面，看到机床床台、A/C转台、喷头、工件和已完成路径随统一时间轴运动。用户可以播放、暂停、单步、拖动时间，选择1×、8×、32×、64×、165×或自定义倍速，并选择一个连续区间导出视频。

首版提供自有AC机床的参数化示意场景。床台和喷头由盒体、圆柱、圆盘、圆台等简易几何组合，尺寸来自Machine/Nozzle Profile；缺失尺寸明确显示Warning。用户加载自定义模型作为后续阶段，首版数据结构预留visual/collision asset字段。

输入优先使用当前generated product的 `MachineAxisTrajectory`、Toolpath和事件。严格回读通过的imported NC可在已注册机型语义下恢复轴时间；缺少时间或机型映射的NC只允许路径预览，禁止伪装成机床运动仿真。

## 2 产品结构

```text
Generated Product / Qualified Imported NC
  → SimulationSourceSnapshot
  → MachineSceneDefinition
  → TimeSampler + JointInterpolator
  → MachineScenePose
  → VTK Scene Adapter
  → Interactive Playback
  → Deterministic Frame Renderer
  → PNG frames → MP4 encoder
  → simulation_manifest.json
```

领域层不依赖Qt/VTK：场景定义、关节映射、时间采样、区间、速度和导出请求均可独立测试。VTK层只负责Actor、相机和像素输出。视频编码单独封装，避免将FFmpeg命令散落在UI中。

## 3 关键契约

- `MachineScenePart`保存部件ID、父节点、visual/collision资产、局部变换、绑定关节、颜色和可见性。
- 内部长度为mm、角度为rad；导入模型必须声明源单位和Source→Part变换。
- 视觉模型和碰撞模型分开，高面数外观模型不能自动作为实时碰撞真值。
- 以 `MachineAxisTrajectory.time_s` 为主时间轴；线性轴线性插值，已展开旋转轴沿当前连续分支插值。
- 运动仿真显示已发布轴轨迹，不重新求另一套IK；32×和165×只改变时间映射，不修改轨迹、轴限或碰撞结果。
- 导出请求冻结来源哈希、区间、倍速、fps、分辨率、相机、可见层、场景版本和编码器版本。
- 默认MP4/H.264、1920×1080、30 fps；逐帧按公式计算仿真时间，尾帧准确包含终点。
- 使用临时帧目录和临时视频，成功后原子替换目标；同目录写 `simulation_manifest.json`。

## 4 UI方案

成果页增加“运动仿真”入口，进入独立三栏页面：左侧是场景树和模型来源，中间是VTK机床场景，右侧是区间、倍速、视频参数和导出队列；底部显示播放控制、当前/总时间、轴值、事件、碰撞/限位状态和导出进度。

交互播放与视频导出共享同一 `MotionSimulationSession`。修改相机或颜色只改变渲染快照；修改机型、关节映射、碰撞资产或源轨迹使仿真结果Stale。

## 5 实施阶段

1. 冻结来源、场景、时间和视频清单契约，建立解析正常/失败夹具。
2. 实现参数化AC机床部件树和XYZAC关节变换，核对非零回转中心与喷头长度。
3. 接入generated product，完成真实时间播放、单步、事件和沉积进度。
4. 加入区间、32×/165×与自定义倍速，完成确定性帧计划器。
5. 实现无损帧导出和编码器探测，再接MP4；无编码器时明确阻止MP4并保留可核验帧。
6. 增加自定义床台/喷头/机架visual model加载和保存重开。
7. 增加独立碰撞模型、逐段扫掠近似和问题定位；必要时评估PyBullet后端。
8. 完成双语UI、三尺寸布局、长轨迹性能、取消/恢复、脚本/HTTP、图文手册和阶段验收。

## 6 验收矩阵

至少覆盖解析XYZAC夹具、非零A/C回转中心、喷头长度、连续C跨±π、纯转位、混合平移/回转；1×/32×/165×帧数和时长；区间首尾与超界拒绝；三种来源资格；内置/损坏/单位错误资产；三档窗口中英文；导出取消和编码失败；长轨迹的有界内存；视频、清单、相机与编码参数哈希。

最终验收只证明离线运动可视化和确定性视频导出。碰撞近似、真实设备轴响应、热-材料行为和成形质量分别说明，不使用动画外观替代制造资格。

