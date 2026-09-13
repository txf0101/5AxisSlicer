# 预定义材料区域与 T0—T3 通道指南

论文核心 AC 版本使用显式材料计划。软件不会按颜色、曲率或模型名称自动猜测材料。每个沉积区域都必须关联一个已声明的 `channel_id`，再由通道给出 `material_id`、`Tn` 指令、喷嘴目标温度、回抽、装载和清洗长度。

## 数据关系

```text
guide-NN-pass-NN 区域
        ↓ MaterialRegion
T0 / T1 / T2 / T3 通道
        ↓ MaterialChannel
PLA / PETG / PA / ABS 与温度、装载、清洗参数
```

区域 ID 来自 Freeform 生成计划。多层复用同一道的材料分配；材料身份会写入每个沉积 `ToolpathPoint`、轴表和预览数据。旧版 Toolpath JSON 没有材料字段时仍可读取，值为 `null`。

## 切换事件

当首个区域选择通道或后续区域改变通道时，事件按下列顺序写入：

```text
prepare_pause（仅需人工准备时）
→ retract → cut → park → switch → load
→ temperature_wait → purge → prime → resume
```

`park` 在自有 AC 离线方言中固定展开为 `G91 → 相对 Z+20 mm → G90`。转位开始的 `index_start` 使用 `G90 → 绝对 Z=20 mm`，两种动作不能互换。

统计口径分开保存：

- `selection_command_count` 包含第一次 T 指令；
- `effective_channel_transition_count` 只计算已有活动通道后的实际变化；
- `deposition_volume_mm3_by_material` 只累计沉积体积；
- `purge_length_mm` 只累计清洗长度。

连续区域使用同一通道时不会重复发 T 指令。预装 T0/T1 案例将 `requires_prepare_pause=false`，当前证据为 2 次选择、1 次有效切换且没有准备暂停。

## 运行前检查

`MaterialRuntimeState` 保存各通道传感器就绪状态和实测温度。需要传感器时，未到位产生 `material.sensor_not_ready:Tn`；缺温度或超出容差产生对应温控问题。任何问题都会在发送到机床前失败关闭。状态恢复到全部就绪、温度在容差内后，可重新执行检查。

当前软件没有连接实际传感器协议，也没有声称完成温控超时的设备级联调。离线事件链和恢复逻辑已经测试，现场通信仍需控制器版本、宏文件和实测记录。
