# 多色材料与换料站

Freeform 的“材料计划 JSON”把沉积区域分配给 T0、T1 等通道。软件不会根据 CAD 颜色自动选料。每个通道可以使用同一种材料的不同颜色；例如三片叶片分别使用红、蓝、黄 PLA。

## 在 Freeform 中设置

1. 选择 Freeform，创建并选中实体操作，按[实体几何选择说明](fan15_solid_fill_method_notes.md)选轮毂、叶片和根面。
2. 在右侧“材料计划 JSON”输入区域与通道的对应关系。`stage_prefix` 指向该实体在合并路径中的顺序：三叶扇底座为 `op01-`，依次三片叶片为 `op02-`、`op03-`、`op04-`。导出后可在 `toolpath.json` 核对每个沉积点的 `stage_id` 和 `channel_id`。其他模型应按自己的实体顺序填写，不能照抄这里的编号。
3. 在“换料站坐标 JSON”填入机床坐标系下标定的喷嘴尖端位置：安全高度、切刀、换料、排料、擦嘴起点和终点。没有站位时，真正的 T 通道切换会阻止 NC 导出。
4. 点击“应用”，再点击“生成”。检查问题列表、路径预览及导出 NC 中的 `PAC SERVICE`、`PAC EVENT`、T 指令与相对 E。保存项目后，换料站设置和材料计划会一起保留。

三色 PLA 的区域映射示例：

```json
{
  "schema_version": 1,
  "plan_id": "fan-three-colour-pla",
  "channels": [
    {"channel_id":"T0","material_id":"PLA-red","tool_command":"T0","nozzle_temperature_c":195,"purge_length_mm":8,"load_length_mm":20,"unload_length_mm":20},
    {"channel_id":"T1","material_id":"PLA-blue","tool_command":"T1","nozzle_temperature_c":195,"purge_length_mm":8,"load_length_mm":20,"unload_length_mm":20},
    {"channel_id":"T2","material_id":"PLA-yellow","tool_command":"T2","nozzle_temperature_c":195,"purge_length_mm":8,"load_length_mm":20,"unload_length_mm":20}
  ],
  "regions": [
    {"region_id":"*","channel_id":"T0","stage_prefix":"op01-"},
    {"region_id":"*","channel_id":"T0","stage_prefix":"op02-"},
    {"region_id":"*","channel_id":"T1","stage_prefix":"op03-"},
    {"region_id":"*","channel_id":"T2","stage_prefix":"op04-"}
  ]
}
```

换料站输入格式示例（坐标仅用于离线练习）：

```json
{"clearance_z_mm":180,"cutter_xyz_mm":[130,100,80],"exchange_xyz_mm":[140,100,80],"purge_xyz_mm":[150,100,80],"wipe_start_xyz_mm":[160,100,80],"wipe_end_xyz_mm":[170,100,80],"travel_feedrate_mm_min":3000,"wipe_feedrate_mm_min":1200,"wipe_passes":2,"cutter_command":"M98 P100"}
```

`region_id="*"` 表示该阶段的全部路径；如需某一条路径单独换色，改用导出数据中的确切 `region_id`。同一通道的相邻区域不会重复执行换料。第一次选 T0 只发送 T0 和目标温度；有效换色依次回抽、退出、到切刀、切断、到换料位退丝、选新通道、等待温度、进丝、到排料位排料、擦嘴、返回路径。退丝使用旧通道的长度，进丝和排料使用新通道的长度。

## 安全边界

安全路径由机床站位、五轴姿态和已经沉积的线段计算，逐段检查配置的喷嘴轮廓。软件也检查原有的跨工序空走。新叶片接近叶根时，只允许喷嘴尖端在终点附近与已打印外壳发生有限道宽内的轻微接触；喷嘴锥体或其他空走碰撞仍会拒绝导出。没有喷嘴轮廓或夹具模型时，结果保留 Warning 和离线资格。切刀、夹具、线缆、整机外壳、真实宏和传感器需要按实际设备另外标定与验证。

示例中的 195 °C、长度及位置只用于说明字段和离线练习。请按自己的 PLA、送料机构、喷嘴、刀臂和机床行程标定。`Tn` 与切刀宏必须在实际控制器中有对应实现。项目当前输出保持 `machine_executable=false`，不得直接用于实机打印。
