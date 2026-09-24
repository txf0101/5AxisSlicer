# Offline Postprocessor Guide for the Own AC Controller

`builtin.controller.own_ac.offline.v1` is the built-in offline AC G-code format for `builtin.machine.own_ac_fdm.v1`. It uses millimetres, degrees for rotary axes, `G90` for absolute machine axes, `M83` for relative extrusion, and `G94` for feed per minute. It establishes extrusion zero with `G92 E0` and restores `G90/M83/G94` before `M400` and `M2`.

Each point has a readable `PAC POINT` marker. Material events include `PAC EVENT` and JSON context; station moves use `PAC SERVICE`. Readback compares the full command stream, point order, controller axis words, F, relative E, material channels, and event order. Extra commands, a change from M83 to M82, altered E/F/axis values, or a damaged footer cause readback to fail.

## Qualification

Device qualification is incomplete because the controller and firmware versions, T0–T3 and cutter/recovery macro versions and hashes, coordinated XYZAC capability, and cumulative C limit have not been confirmed. Therefore `machine_executable=false`.

The known A ±180° and C ±360° limits are checked per point. Actual cumulative C travel and span are recorded in qualification data. If the cumulative limit is unknown, the result has `controller.cumulative_c_limit_unknown` Warning. A configured limit that is exceeded causes an Error.

## Tool changes

Multichannel Freeform jobs require a configured [tool-change station and material regions](material_channels_en.md). Clearance, cutter, exchange, purge, wipe, and return positions are explicit absolute XYZAC moves. `index_start` does not insert a hidden fixed Z move. Export is blocked if a required station is missing or its route intersects deposited material. A job that selects only the initial channel and never changes colour does not need a station.

Before using a machine, verify its controller and macro versions, rotary centre, offsets, axis directions, tool and fixture swept volumes, speed and acceleration limits, and sensor protocol. Perform an on-site air run, collision check, and trial print. Example values and print results must be determined on the user's own equipment.
