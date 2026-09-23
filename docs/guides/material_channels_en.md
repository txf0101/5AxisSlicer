# Multicolour materials and the tool-change station

In Freeform, the Material plan JSON assigns deposition regions to T0, T1, and other channels. CAD colours do not select filament automatically. Channels may use different colours of the same material, such as red, blue, and yellow PLA for three fan blades.

## Set up a Freeform operation

1. Create and select a solid-fill operation. Select its hub, blade bodies, and root faces as described in the [solid-fill geometry guide](fan15_solid_fill_method_notes.md).
2. Enter the channel assignments in Material plan JSON. For the three-blade example, `op01-` is the base and `op02-` through `op04-` are the blades in selection order. Check `stage_id` and `channel_id` in the exported `toolpath.json`. Use the actual operation order for another model.
3. Enter calibrated machine-frame nozzle-tip positions in Tool-change station JSON: clearance height, cutter, exchange, purge, and wipe start/end. A real channel transition without a station blocks NC export.
4. Click Apply and then Generate. Inspect the issues, path preview, and `PAC SERVICE`/`PAC EVENT` records and T commands in the NC. Saving the project also saves the plan and station.

Example region mapping for three PLA colours:

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

Example station input for offline practice only:

```json
{"clearance_z_mm":180,"cutter_xyz_mm":[130,100,80],"exchange_xyz_mm":[140,100,80],"purge_xyz_mm":[150,100,80],"wipe_start_xyz_mm":[160,100,80],"wipe_end_xyz_mm":[170,100,80],"travel_feedrate_mm_min":3000,"wipe_feedrate_mm_min":1200,"wipe_passes":2,"cutter_command":"M98 P100"}
```

`region_id="*"` covers every path within a stage; use an exact region ID for a specific path. Adjacent regions on the same channel do not trigger another change. Initial T0 selection only selects the tool and waits for temperature. An actual change retracts, moves to the cutter and cuts, moves to exchange and unloads the old channel, selects the new channel, waits for temperature, loads, purges, wipes, and returns. Unload length belongs to the old channel; load and purge lengths belong to the new one.

The service route and existing inter-operation travels are checked against already deposited beads using the configured nozzle envelope. At a new blade root, only limited tip contact near the end of the approach is allowed; nozzle-body and other travel collisions still block export. Fixture, cutter, cabling, machine frame, firmware macros, and sensors still require physical calibration and separate checks. The values above are examples only: set temperature, extrusion lengths, positions, and limits for your own PLA and machine. Output remains `machine_executable=false` and must not be sent directly to hardware.
