; 5AxisSclicer paper-core AC offline review program
; CONTROLLER_PROFILE {"axis_mode":"absolute","controller_family":"custom-klipper-derived","controller_version":null,"coordinated_xyzac_verified":false,"cutter_relative_z_mm":20.0,"extrusion_mode":"relative","feed_mode":"units_per_minute","machine_executable":false,"machine_profile_id":"builtin.machine.own_ac_fdm.v1","macro_version":null,"maximum_cumulative_c_rad":null,"profile_id":"builtin.controller.own_ac.offline.v1","qualification_issues":["controller.version_unknown","controller.macros_unverified","controller.xyzac_coordination_unverified","controller.cumulative_c_limit_unknown"],"reorientation_absolute_z_mm":20.0,"schema_version":1}
; EXECUTION_QUALIFICATION offline_only
G21 ; millimetres
G90 ; absolute machine axes
M83 ; relative extrusion
G94 ; units per minute
G92 E0 ; explicit extrusion origin
; PAC POINT 1 point-0000001 approach - -
G1 A-69.343889 C-71.999992 X12.000000 Y39.300010 Z17.315844 F3000.000000
; PAC EVENT material-0001-retract retract
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":-1.0,"material_id":"PLA","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
G1 E-1.000000000000 F900.000000
; PAC EVENT material-0001-cut cut
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
M98 P100 ; OFFLINE _5AXIS_CUT macro semantic
; PAC EVENT material-0001-park park
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
G91
G1 Z20.000000 F900.000000
G90
; PAC EVENT material-0001-switch switch
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
T0
; PAC EVENT material-0001-load load
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":0.0,"material_id":"PLA","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
G1 E0.000000000000 F900.000000
; PAC EVENT material-0001-temperature_wait temperature_wait
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":1,"target_temperature_c":195.0,"timeout_s":180.0,"tool_command":"T0"}
M109 S195.000
; PAC EVENT material-0001-purge purge
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":5.0,"material_id":"PLA","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
G1 E5.000000000000 F900.000000
; PAC EVENT material-0001-prime prime
; PAC EVENT_CONTEXT {"channel_id":"T0","extrusion_length_mm":1.0,"material_id":"PLA","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
G1 E1.000000000000 F900.000000
; PAC EVENT material-0001-resume resume
; PAC EVENT_CONTEXT {"channel_id":"T0","material_id":"PLA","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":1,"tool_command":"T0"}
M98 P101 ; OFFLINE _5AXIS_RESUME macro semantic
; PAC EVENT event-0000001 prime
; PAC EVENT_CONTEXT {"extrusion_length_mm":1.0,"sequence_index":1}
G1 E1.000000000000 F900.000000
; PAC POINT 2 point-0000002 deposition PLA T0
G1 A-69.531132 C-62.323780 X12.057448 Y37.092924 Z15.292439 E0.098727812132 F900.000000
; PAC POINT 3 point-0000003 deposition PLA T0
G1 A-70.027495 C-53.330323 X12.244068 Y34.909299 Z13.193633 E0.098726410891 F900.000000
; PAC POINT 4 point-0000004 deposition PLA T0
G1 A-70.677832 C-44.919019 X12.574445 Y32.729542 Z11.096426 E0.098725561295 F900.000000
; PAC POINT 5 point-0000005 deposition PLA T0
G1 A-71.461512 C-37.013279 X13.052944 Y30.567881 Z8.993843 E0.098724610624 F900.000000
; PAC POINT 6 point-0000006 deposition PLA T0
G1 A-72.377404 C-29.558338 X13.671076 Y28.435929 Z6.871635 E0.098721183893 F900.000000
; PAC POINT 7 point-0000007 deposition PLA T0
G1 A-73.358620 C-22.465666 X14.415644 Y26.341434 Z4.743149 E0.098720152807 F900.000000
; PAC POINT 8 point-0000008 deposition PLA T0
G1 A-74.484449 C-15.827947 X15.285488 Y24.287256 Z2.595063 E0.098718706918 F900.000000
; PAC POINT 9 point-0000009 deposition PLA T0
G1 A-75.731578 C-9.649035 X16.272848 Y22.268918 Z0.445809 E0.098716496601 F900.000000
; PAC POINT 10 point-0000010 deposition PLA T0
G1 A-77.034138 C-3.895442 X17.368038 Y20.288814 Z-1.677527 E0.098716441662 F900.000000
; PAC POINT 11 point-0000011 deposition PLA T0
G1 A-78.444258 C1.259539 X18.594067 Y18.331235 Z-3.731144 E0.098716246500 F900.000000
; PAC POINT 12 point-0000012 deposition PLA T0
G1 A-79.903609 C5.834664 X19.955069 Y16.400471 Z-5.683072 E0.098716468658 F900.000000
; PAC POINT 13 point-0000013 deposition PLA T0
G1 A-81.348077 C9.856935 X21.455006 Y14.510361 Z-7.504370 E0.098717570395 F900.000000
; PAC POINT 14 point-0000014 deposition PLA T0
G1 A-82.791019 C13.179657 X23.136659 Y12.659077 Z-9.124415 E0.098718186521 F900.000000
; PAC POINT 15 point-0000015 deposition PLA T0
G1 A-84.173641 C15.845148 X25.009687 Y10.872397 Z-10.518632 E0.098719340574 F900.000000
; PAC POINT 16 point-0000016 deposition PLA T0
G1 A-85.450548 C17.849066 X27.091986 Y9.177655 Z-11.646292 E0.098720547549 F900.000000
; PAC POINT 17 point-0000017 deposition PLA T0
G1 A-86.631821 C19.020569 X29.442475 Y7.588168 Z-12.392482 E0.098721076440 F900.000000
; PAC POINT 18 point-0000018 deposition PLA T0
G1 A-87.664973 C19.408382 X32.060328 Y6.144719 Z-12.721271 E0.098720930974 F900.000000
; PAC POINT 19 point-0000019 deposition PLA T0
G1 A-88.514391 C18.959115 X34.957837 Y4.882897 Z-12.536236 E0.098719615317 F900.000000
; PAC POINT 20 point-0000020 deposition PLA T0
G1 A-89.189774 C17.439239 X38.170565 Y3.824693 Z-11.613614 E0.098717019526 F900.000000
; PAC POINT 21 point-0000021 deposition PLA T0
G1 A-89.654373 C14.908962 X41.620050 Y3.004508 Z-9.875444 E0.098710060239 F900.000000
; PAC POINT 22 point-0000022 deposition PLA T0
G1 A-89.913264 C11.185628 X45.225707 Y2.434698 Z-7.059804 E0.098696921334 F900.000000
; PAC POINT 23 point-0000023 deposition PLA T0
G1 A-90.000842 C6.222805 X48.787433 Y2.106796 Z-2.983949 E0.098678817141 F900.000000
; PAC POINT 24 point-0000024 deposition PLA T0
G1 A-90.000000 C0.000000 X52.000000 Y2.000000 Z2.500000 E0.098662400051 F900.000000
; PAC EVENT event-0000002 retract
; PAC EVENT_CONTEXT {"extrusion_length_mm":-1.0,"sequence_index":24}
G1 E-1.000000000000 F3000.000000
; PAC POINT 25 point-0000025 travel - -
G1 A-90.000000 C-45.000000 X52.000000 Y2.000000 Z2.500000 F3000.000000
; PAC EVENT material-0002-retract retract
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":-1.0,"material_id":"PETG","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":25,"tool_command":"T1"}
G1 E-1.000000000000 F900.000000
; PAC EVENT material-0002-cut cut
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":25,"tool_command":"T1"}
M98 P100 ; OFFLINE _5AXIS_CUT macro semantic
; PAC EVENT material-0002-park park
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":25,"tool_command":"T1"}
G91
G1 Z20.000000 F900.000000
G90
; PAC EVENT material-0002-switch switch
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":25,"tool_command":"T1"}
T1
; PAC EVENT material-0002-load load
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":0.0,"material_id":"PETG","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":25,"tool_command":"T1"}
G1 E0.000000000000 F900.000000
; PAC EVENT material-0002-temperature_wait temperature_wait
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":25,"target_temperature_c":235.0,"timeout_s":180.0,"tool_command":"T1"}
M109 S235.000
; PAC EVENT material-0002-purge purge
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":6.0,"material_id":"PETG","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":25,"tool_command":"T1"}
G1 E6.000000000000 F900.000000
; PAC EVENT material-0002-prime prime
; PAC EVENT_CONTEXT {"channel_id":"T1","extrusion_length_mm":1.0,"material_id":"PETG","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":25,"tool_command":"T1"}
G1 E1.000000000000 F900.000000
; PAC EVENT material-0002-resume resume
; PAC EVENT_CONTEXT {"channel_id":"T1","material_id":"PETG","material_plan_id":"dual_channel_preloaded-materials","sensor_required":true,"sequence_index":25,"tool_command":"T1"}
M98 P101 ; OFFLINE _5AXIS_RESUME macro semantic
; PAC EVENT event-0000003 prime
; PAC EVENT_CONTEXT {"extrusion_length_mm":1.0,"sequence_index":25}
G1 E1.000000000000 F900.000000
; PAC POINT 26 point-0000026 deposition PETG T1
G1 A-90.000842 C-38.777195 X48.787433 Y2.106796 Z-2.983949 E0.098662400051 F900.000000
; PAC POINT 27 point-0000027 deposition PETG T1
G1 A-89.913264 C-33.814372 X45.225707 Y2.434698 Z-7.059804 E0.098678817140 F900.000000
; PAC POINT 28 point-0000028 deposition PETG T1
G1 A-89.654373 C-30.091038 X41.620050 Y3.004508 Z-9.875444 E0.098696921335 F900.000000
; PAC POINT 29 point-0000029 deposition PETG T1
G1 A-89.189774 C-27.560761 X38.170565 Y3.824693 Z-11.613614 E0.098710060239 F900.000000
; PAC POINT 30 point-0000030 deposition PETG T1
G1 A-88.514391 C-26.040885 X34.957837 Y4.882897 Z-12.536236 E0.098717019526 F900.000000
; PAC POINT 31 point-0000031 deposition PETG T1
G1 A-87.664973 C-25.591618 X32.060328 Y6.144719 Z-12.721271 E0.098719615317 F900.000000
; PAC POINT 32 point-0000032 deposition PETG T1
G1 A-86.631821 C-25.979431 X29.442475 Y7.588168 Z-12.392482 E0.098720930974 F900.000000
; PAC POINT 33 point-0000033 deposition PETG T1
G1 A-85.450548 C-27.150934 X27.091986 Y9.177655 Z-11.646292 E0.098721076440 F900.000000
; PAC POINT 34 point-0000034 deposition PETG T1
G1 A-84.173641 C-29.154852 X25.009687 Y10.872397 Z-10.518632 E0.098720547549 F900.000000
; PAC POINT 35 point-0000035 deposition PETG T1
G1 A-82.791019 C-31.820343 X23.136659 Y12.659077 Z-9.124415 E0.098719340574 F900.000000
; PAC POINT 36 point-0000036 deposition PETG T1
G1 A-81.348077 C-35.143065 X21.455006 Y14.510361 Z-7.504370 E0.098718186521 F900.000000
; PAC POINT 37 point-0000037 deposition PETG T1
G1 A-79.903609 C-39.165336 X19.955069 Y16.400471 Z-5.683072 E0.098717570395 F900.000000
; PAC POINT 38 point-0000038 deposition PETG T1
G1 A-78.444258 C-43.740461 X18.594067 Y18.331235 Z-3.731144 E0.098716468658 F900.000000
; PAC POINT 39 point-0000039 deposition PETG T1
G1 A-77.034138 C-48.895442 X17.368038 Y20.288814 Z-1.677527 E0.098716246500 F900.000000
; PAC POINT 40 point-0000040 deposition PETG T1
G1 A-75.731578 C-54.649035 X16.272848 Y22.268918 Z0.445809 E0.098716441662 F900.000000
; PAC POINT 41 point-0000041 deposition PETG T1
G1 A-74.484447 C-60.827959 X15.285486 Y24.287260 Z2.595067 E0.098716691358 F900.000000
; PAC POINT 42 point-0000042 deposition PETG T1
G1 A-73.358620 C-67.465666 X14.415644 Y26.341434 Z4.743149 E0.098718512157 F900.000000
; PAC POINT 43 point-0000043 deposition PETG T1
G1 A-72.377405 C-74.558326 X13.671077 Y28.435926 Z6.871631 E0.098719998066 F900.000000
; PAC POINT 44 point-0000044 deposition PETG T1
G1 A-71.461510 C-82.013291 X13.052943 Y30.567885 Z8.993846 E0.098721487432 F900.000000
; PAC POINT 45 point-0000045 deposition PETG T1
G1 A-70.677832 C-89.919019 X12.574445 Y32.729542 Z11.096426 E0.098724461830 F900.000000
; PAC POINT 46 point-0000046 deposition PETG T1
G1 A-70.027495 C-98.330323 X12.244068 Y34.909299 Z13.193633 E0.098725561295 F900.000000
; PAC POINT 47 point-0000047 deposition PETG T1
G1 A-69.531132 C-107.323780 X12.057448 Y37.092924 Z15.292439 E0.098726410891 F900.000000
; PAC POINT 48 point-0000048 deposition PETG T1
G1 A-69.343889 C-116.999992 X12.000000 Y39.300010 Z17.315844 E0.098727812132 F900.000000
G90 ; restore absolute axes
M83 ; restore relative extrusion
G94 ; restore units per minute
M400
M2
