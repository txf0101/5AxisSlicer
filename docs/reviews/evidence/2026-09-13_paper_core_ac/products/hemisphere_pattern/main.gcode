; 5AxisSclicer paper-core AC offline review program
; CONTROLLER_PROFILE {"axis_mode":"absolute","controller_family":"custom-klipper-derived","controller_version":null,"coordinated_xyzac_verified":false,"cutter_relative_z_mm":20.0,"extrusion_mode":"relative","feed_mode":"units_per_minute","machine_executable":false,"machine_profile_id":"builtin.machine.own_ac_fdm.v1","macro_version":null,"maximum_cumulative_c_rad":null,"profile_id":"builtin.controller.own_ac.offline.v1","qualification_issues":["controller.version_unknown","controller.macros_unverified","controller.xyzac_coordination_unverified","controller.cumulative_c_limit_unknown"],"reorientation_absolute_z_mm":20.0,"schema_version":1}
; EXECUTION_QUALIFICATION offline_only
G21 ; millimetres
G90 ; absolute machine axes
M83 ; relative extrusion
G94 ; units per minute
G92 E0 ; explicit extrusion origin
; PAC POINT 1 point-0000001 approach - -
G1 A-13.363492 C-0.000000 X0.000000 Y-0.000000 Z42.500000 F3000.000000
; PAC EVENT material-0001-retract retract
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":-1.0,"material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
G1 E-1.000000000000 F900.000000
; PAC EVENT material-0001-cut cut
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
M98 P100 ; OFFLINE _5AXIS_CUT macro semantic
; PAC EVENT material-0001-park park
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
G91
G1 Z20.000000 F900.000000
G90
; PAC EVENT material-0001-switch switch
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
T0
; PAC EVENT material-0001-load load
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":0.0,"material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
G1 E0.000000000000 F900.000000
; PAC EVENT material-0001-temperature_wait temperature_wait
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":1,"target_temperature_c":195.0,"timeout_s":180.0,"tool_command":"T0"}
M109 S195.000
; PAC EVENT material-0001-purge purge
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":5.0,"material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
G1 E5.000000000000 F900.000000
; PAC EVENT material-0001-prime prime
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":1.0,"material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
G1 E1.000000000000 F900.000000
; PAC EVENT material-0001-resume resume
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
M98 P101 ; OFFLINE _5AXIS_RESUME macro semantic
; PAC EVENT event-0000001 prime
; PAC EVENT_CONTEXT {"extrusion_length_mm":1.0,"sequence_index":1}
G1 E1.000000000000 F900.000000
; PAC POINT 2 point-0000002 deposition PLA T0
G1 A-15.191052 C-13.199791 X-0.000000 Y-0.000000 Z42.500000 E0.087480431685 F900.000000
; PAC POINT 3 point-0000003 deposition PLA T0
G1 A-17.557739 C-23.419533 X0.000000 Y0.000000 Z42.500000 E0.087445943365 F900.000000
; PAC POINT 4 point-0000004 deposition PLA T0
G1 A-19.994289 C-32.174248 X-0.000000 Y-0.000000 Z42.500000 E0.087419660820 F900.000000
; PAC POINT 5 point-0000005 deposition PLA T0
G1 A-22.517222 C-39.734782 X0.000000 Y-0.000000 Z42.500000 E0.087457700964 F900.000000
; PAC POINT 6 point-0000006 deposition PLA T0
G1 A-25.161409 C-46.224340 X-0.000000 Y-0.000000 Z42.500000 E0.087464153132 F900.000000
; PAC POINT 7 point-0000007 deposition PLA T0
G1 A-27.806388 C-52.097144 X0.000000 Y-0.000000 Z42.500000 E0.087429003888 F900.000000
; PAC POINT 8 point-0000008 deposition PLA T0
G1 A-30.516219 C-57.338794 X-0.000000 Y0.000000 Z42.500000 E0.087479881744 F900.000000
; PAC POINT 9 point-0000009 deposition PLA T0
G1 A-33.131027 C-62.324816 X-0.000000 Y0.000000 Z42.500000 E0.087118613143 F900.000000
; PAC EVENT event-0000002 retract
; PAC EVENT_CONTEXT {"extrusion_length_mm":-1.0,"sequence_index":9}
G1 E-1.000000000000 F3000.000000
; PAC POINT 10 point-0000010 travel - -
G1 A-19.503288 C-2.672359 X0.000000 Y-0.000000 Z42.500000 F3000.000000
; PAC EVENT material-0002-retract retract
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":-1.0,"material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":10,"tool_command":"T1"}
G1 E-1.000000000000 F900.000000
; PAC EVENT material-0002-cut cut
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":10,"tool_command":"T1"}
M98 P100 ; OFFLINE _5AXIS_CUT macro semantic
; PAC EVENT material-0002-park park
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":10,"tool_command":"T1"}
G91
G1 Z20.000000 F900.000000
G90
; PAC EVENT material-0002-switch switch
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":10,"tool_command":"T1"}
T1
; PAC EVENT material-0002-load load
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":0.0,"material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":10,"tool_command":"T1"}
G1 E0.000000000000 F900.000000
; PAC EVENT material-0002-temperature_wait temperature_wait
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":10,"target_temperature_c":235.0,"timeout_s":180.0,"tool_command":"T1"}
M109 S235.000
; PAC EVENT material-0002-purge purge
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":6.0,"material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":10,"tool_command":"T1"}
G1 E6.000000000000 F900.000000
; PAC EVENT material-0002-prime prime
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":1.0,"material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":10,"tool_command":"T1"}
G1 E1.000000000000 F900.000000
; PAC EVENT material-0002-resume resume
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":10,"tool_command":"T1"}
M98 P101 ; OFFLINE _5AXIS_RESUME macro semantic
; PAC EVENT event-0000003 prime
; PAC EVENT_CONTEXT {"extrusion_length_mm":1.0,"sequence_index":10}
G1 E1.000000000000 F900.000000
; PAC POINT 11 point-0000011 deposition PETG T1
G1 A-19.072232 C-0.000000 X0.000000 Y-0.000000 Z42.500000 E0.023092116095 F900.000000
; PAC EVENT event-0000004 retract
; PAC EVENT_CONTEXT {"extrusion_length_mm":-1.0,"sequence_index":11}
G1 E-1.000000000000 F3000.000000
; PAC POINT 12 point-0000012 travel - -
G1 A-22.401981 C-0.000000 X0.000000 Y-0.000000 Z42.500000 F3000.000000
; PAC EVENT material-0003-prepare_pause prepare_pause
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":12,"tool_command":"T2"}
M0 ; operator material preparation
; PAC EVENT material-0003-retract retract
; PAC EVENT_CONTEXT {"channel_id":"T2","extrusion_length_mm":-1.0,"material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":12,"tool_command":"T2"}
G1 E-1.000000000000 F900.000000
; PAC EVENT material-0003-cut cut
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":12,"tool_command":"T2"}
M98 P100 ; OFFLINE _5AXIS_CUT macro semantic
; PAC EVENT material-0003-park park
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":12,"tool_command":"T2"}
G91
G1 Z20.000000 F900.000000
G90
; PAC EVENT material-0003-switch switch
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":12,"tool_command":"T2"}
T2
; PAC EVENT material-0003-load load
; PAC EVENT_CONTEXT {"channel_id":"T2","extrusion_length_mm":0.0,"material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":12,"tool_command":"T2"}
G1 E0.000000000000 F900.000000
; PAC EVENT material-0003-temperature_wait temperature_wait
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":12,"target_temperature_c":275.0,"timeout_s":180.0,"tool_command":"T2"}
M109 S275.000
; PAC EVENT material-0003-purge purge
; PAC EVENT_CONTEXT {"channel_id":"T2","extrusion_length_mm":7.0,"material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":12,"tool_command":"T2"}
G1 E7.000000000000 F900.000000
; PAC EVENT material-0003-prime prime
; PAC EVENT_CONTEXT {"channel_id":"T2","extrusion_length_mm":1.0,"material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":12,"tool_command":"T2"}
G1 E1.000000000000 F900.000000
; PAC EVENT material-0003-resume resume
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":12,"tool_command":"T2"}
M98 P101 ; OFFLINE _5AXIS_RESUME macro semantic
; PAC EVENT event-0000005 prime
; PAC EVENT_CONTEXT {"extrusion_length_mm":1.0,"sequence_index":12}
G1 E1.000000000000 F900.000000
; PAC POINT 13 point-0000013 deposition PA T2
G1 A-23.430596 C-4.741300 X-0.000000 Y-0.000000 Z42.500000 E0.049665564400 F900.000000
; PAC EVENT event-0000006 retract
; PAC EVENT_CONTEXT {"extrusion_length_mm":-1.0,"sequence_index":13}
G1 E-1.000000000000 F3000.000000
; PAC POINT 14 point-0000014 travel - -
G1 A-26.369991 C-5.972285 X-0.000000 Y-0.000000 Z42.500000 F3000.000000
; PAC EVENT material-0004-prepare_pause prepare_pause
; PAC EVENT_CONTEXT {"channel_id":"T3","material_id":"ABS","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":14,"tool_command":"T3"}
M0 ; operator material preparation
; PAC EVENT material-0004-retract retract
; PAC EVENT_CONTEXT {"channel_id":"T3","extrusion_length_mm":-1.0,"material_id":"ABS","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":14,"tool_command":"T3"}
G1 E-1.000000000000 F900.000000
; PAC EVENT material-0004-cut cut
; PAC EVENT_CONTEXT {"channel_id":"T3","material_id":"ABS","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":14,"tool_command":"T3"}
M98 P100 ; OFFLINE _5AXIS_CUT macro semantic
; PAC EVENT material-0004-park park
; PAC EVENT_CONTEXT {"channel_id":"T3","material_id":"ABS","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":14,"tool_command":"T3"}
G91
G1 Z20.000000 F900.000000
G90
; PAC EVENT material-0004-switch switch
; PAC EVENT_CONTEXT {"channel_id":"T3","material_id":"ABS","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":14,"tool_command":"T3"}
T3
; PAC EVENT material-0004-load load
; PAC EVENT_CONTEXT {"channel_id":"T3","extrusion_length_mm":0.0,"material_id":"ABS","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":14,"tool_command":"T3"}
G1 E0.000000000000 F900.000000
; PAC EVENT material-0004-temperature_wait temperature_wait
; PAC EVENT_CONTEXT {"channel_id":"T3","material_id":"ABS","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":14,"target_temperature_c":250.0,"timeout_s":180.0,"tool_command":"T3"}
M109 S250.000
; PAC EVENT material-0004-purge purge
; PAC EVENT_CONTEXT {"channel_id":"T3","extrusion_length_mm":8.0,"material_id":"ABS","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":14,"tool_command":"T3"}
G1 E8.000000000000 F900.000000
; PAC EVENT material-0004-prime prime
; PAC EVENT_CONTEXT {"channel_id":"T3","extrusion_length_mm":1.0,"material_id":"ABS","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":14,"tool_command":"T3"}
G1 E1.000000000000 F900.000000
; PAC EVENT material-0004-resume resume
; PAC EVENT_CONTEXT {"channel_id":"T3","material_id":"ABS","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":14,"tool_command":"T3"}
M98 P101 ; OFFLINE _5AXIS_RESUME macro semantic
; PAC EVENT event-0000007 prime
; PAC EVENT_CONTEXT {"extrusion_length_mm":1.0,"sequence_index":14}
G1 E1.000000000000 F900.000000
; PAC POINT 15 point-0000015 deposition ABS T3
G1 A-24.897988 C-0.000000 X0.000000 Y0.000000 Z42.500000 E0.069863020685 F900.000000
; PAC EVENT event-0000008 retract
; PAC EVENT_CONTEXT {"extrusion_length_mm":-1.0,"sequence_index":15}
G1 E-1.000000000000 F3000.000000
; PAC POINT 16 point-0000016 travel - -
G1 A-28.097862 C-12.085929 X0.000000 Y0.000000 Z42.500000 F3000.000000
; PAC EVENT material-0005-retract retract
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":-1.0,"material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":16,"tool_command":"T0"}
G1 E-1.000000000000 F900.000000
; PAC EVENT material-0005-cut cut
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":16,"tool_command":"T0"}
M98 P100 ; OFFLINE _5AXIS_CUT macro semantic
; PAC EVENT material-0005-park park
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":16,"tool_command":"T0"}
G91
G1 Z20.000000 F900.000000
G90
; PAC EVENT material-0005-switch switch
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":16,"tool_command":"T0"}
T0
; PAC EVENT material-0005-load load
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":0.0,"material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":16,"tool_command":"T0"}
G1 E0.000000000000 F900.000000
; PAC EVENT material-0005-temperature_wait temperature_wait
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":16,"target_temperature_c":195.0,"timeout_s":180.0,"tool_command":"T0"}
M109 S195.000
; PAC EVENT material-0005-purge purge
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":5.0,"material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":16,"tool_command":"T0"}
G1 E5.000000000000 F900.000000
; PAC EVENT material-0005-prime prime
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":1.0,"material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":16,"tool_command":"T0"}
G1 E1.000000000000 F900.000000
; PAC EVENT material-0005-resume resume
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":16,"tool_command":"T0"}
M98 P101 ; OFFLINE _5AXIS_RESUME macro semantic
; PAC EVENT event-0000009 prime
; PAC EVENT_CONTEXT {"extrusion_length_mm":1.0,"sequence_index":16}
G1 E1.000000000000 F900.000000
; PAC POINT 17 point-0000017 deposition PLA T0
G1 A-29.725748 C-17.928369 X0.000000 Y0.000000 Z42.500000 E0.076595725614 F900.000000
; PAC POINT 18 point-0000018 deposition PLA T0
G1 A-31.385778 C-23.450053 X0.000000 Y-0.000000 Z42.500000 E0.076625963906 F900.000000
; PAC POINT 19 point-0000019 deposition PLA T0
G1 A-33.131027 C-28.610547 X0.000000 Y-0.000000 Z42.500000 E0.076618838149 F900.000000
; PAC EVENT event-0000010 retract
; PAC EVENT_CONTEXT {"extrusion_length_mm":-1.0,"sequence_index":19}
G1 E-1.000000000000 F3000.000000
; PAC POINT 20 point-0000020 travel - -
G1 A-33.131027 C-35.964740 X-0.000000 Y-0.000000 Z42.500000 F3000.000000
; PAC EVENT material-0006-retract retract
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":-1.0,"material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":20,"tool_command":"T1"}
G1 E-1.000000000000 F900.000000
; PAC EVENT material-0006-cut cut
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":20,"tool_command":"T1"}
M98 P100 ; OFFLINE _5AXIS_CUT macro semantic
; PAC EVENT material-0006-park park
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":20,"tool_command":"T1"}
G91
G1 Z20.000000 F900.000000
G90
; PAC EVENT material-0006-switch switch
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":20,"tool_command":"T1"}
T1
; PAC EVENT material-0006-load load
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":0.0,"material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":20,"tool_command":"T1"}
G1 E0.000000000000 F900.000000
; PAC EVENT material-0006-temperature_wait temperature_wait
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":20,"target_temperature_c":235.0,"timeout_s":180.0,"tool_command":"T1"}
M109 S235.000
; PAC EVENT material-0006-purge purge
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":6.0,"material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":20,"tool_command":"T1"}
G1 E6.000000000000 F900.000000
; PAC EVENT material-0006-prime prime
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":1.0,"material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":20,"tool_command":"T1"}
G1 E1.000000000000 F900.000000
; PAC EVENT material-0006-resume resume
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":20,"tool_command":"T1"}
M98 P101 ; OFFLINE _5AXIS_RESUME macro semantic
; PAC EVENT event-0000011 prime
; PAC EVENT_CONTEXT {"extrusion_length_mm":1.0,"sequence_index":20}
G1 E1.000000000000 F900.000000
; PAC POINT 21 point-0000021 deposition PETG T1
G1 A-31.096805 C-30.481290 X-0.000000 Y-0.000000 Z42.500000 E0.083515991103 F900.000000
; PAC POINT 22 point-0000022 deposition PETG T1
G1 A-29.044994 C-24.683273 X0.000000 Y-0.000000 Z42.500000 E0.083558236496 F900.000000
; PAC POINT 23 point-0000023 deposition PETG T1
G1 A-27.152243 C-18.288664 X0.000000 Y0.000000 Z42.500000 E0.083560737235 F900.000000
; PAC POINT 24 point-0000024 deposition PETG T1
G1 A-25.278644 C-11.450362 X-0.000000 Y-0.000000 Z42.500000 E0.083492688242 F900.000000
; PAC EVENT event-0000012 retract
; PAC EVENT_CONTEXT {"extrusion_length_mm":-1.0,"sequence_index":24}
G1 E-1.000000000000 F3000.000000
; PAC POINT 25 point-0000025 travel - -
G1 A-21.191407 C-10.811142 X0.000000 Y0.000000 Z42.500000 F3000.000000
; PAC EVENT material-0007-prepare_pause prepare_pause
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":25,"tool_command":"T2"}
M0 ; operator material preparation
; PAC EVENT material-0007-retract retract
; PAC EVENT_CONTEXT {"channel_id":"T2","extrusion_length_mm":-1.0,"material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":25,"tool_command":"T2"}
G1 E-1.000000000000 F900.000000
; PAC EVENT material-0007-cut cut
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":25,"tool_command":"T2"}
M98 P100 ; OFFLINE _5AXIS_CUT macro semantic
; PAC EVENT material-0007-park park
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":25,"tool_command":"T2"}
G91
G1 Z20.000000 F900.000000
G90
; PAC EVENT material-0007-switch switch
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":25,"tool_command":"T2"}
T2
; PAC EVENT material-0007-load load
; PAC EVENT_CONTEXT {"channel_id":"T2","extrusion_length_mm":0.0,"material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":25,"tool_command":"T2"}
G1 E0.000000000000 F900.000000
; PAC EVENT material-0007-temperature_wait temperature_wait
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":25,"target_temperature_c":275.0,"timeout_s":180.0,"tool_command":"T2"}
M109 S275.000
; PAC EVENT material-0007-purge purge
; PAC EVENT_CONTEXT {"channel_id":"T2","extrusion_length_mm":7.0,"material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":25,"tool_command":"T2"}
G1 E7.000000000000 F900.000000
; PAC EVENT material-0007-prime prime
; PAC EVENT_CONTEXT {"channel_id":"T2","extrusion_length_mm":1.0,"material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":25,"tool_command":"T2"}
G1 E1.000000000000 F900.000000
; PAC EVENT material-0007-resume resume
; PAC EVENT_CONTEXT {"channel_id":"T2","material_id":"PA","material_plan_id":"hemisphere_pattern-materials","sensor_required":true,"sequence_index":25,"tool_command":"T2"}
M98 P101 ; OFFLINE _5AXIS_RESUME macro semantic
; PAC EVENT event-0000013 prime
; PAC EVENT_CONTEXT {"extrusion_length_mm":1.0,"sequence_index":25}
G1 E1.000000000000 F900.000000
; PAC POINT 26 point-0000026 deposition PA T2
G1 A-23.397813 C-19.537215 X0.000000 Y-0.000000 Z42.500000 E0.093383333226 F900.000000
; PAC POINT 27 point-0000027 deposition PA T2
G1 A-25.728097 C-27.293034 X0.000000 Y-0.000000 Z42.500000 E0.093401532865 F900.000000
; PAC POINT 28 point-0000028 deposition PA T2
G1 A-28.159261 C-34.239591 X-0.000000 Y-0.000000 Z42.500000 E0.093401341772 F900.000000
; PAC POINT 29 point-0000029 deposition PA T2
G1 A-30.641723 C-40.567302 X-0.000000 Y-0.000000 Z42.500000 E0.093399319333 F900.000000
; PAC POINT 30 point-0000030 deposition PA T2
G1 A-33.131027 C-46.435988 X-0.000000 Y-0.000000 Z42.500000 E0.093396058059 F900.000000
G90 ; restore absolute axes
M83 ; restore relative extrusion
G94 ; restore units per minute
M400
M2
