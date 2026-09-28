# Offline slicing examples

These models, original G-code files, and saved offline comparison outputs are practice material. The original programs are references for motion-path comparison. A saved output's status applies only to its recorded model, parameters, and machine profile; if you slice again with different Setup or software settings, use the new Warning/Error and readback rather than assuming the older file is exportable. Actual settings and print results depend on your equipment trials.

| Example | STEP model | Original G-code | Saved offline output |
| --- | --- | --- | --- |
| Bent tube | [Model](pipe2/弯管新.stp) | [Original](pipe2/弯管.gcode) | [Offline NC](pipe2/弯管_新算法_离线检查_20260921_v5.gcode) |
| Spherical NEU emblem | [Model](球形NEU校徽/球形测试件.STEP) | [Original](球形NEU校徽/NEU校徽划线.gcode) | [Offline NC](球形NEU校徽/球形NEU校徽_新算法_离线检查_20260921.gcode) |
| Impeller | [Model](叶轮/叶轮.stp) | [Original](叶轮/叶轮完整.gcode) | [Offline NC](叶轮/叶轮_新算法_离线检查_20260921.gcode) |
| Three-blade fan | [Model](三叶扇/Supportless_sample.stp) | [Original](三叶扇/EXAMPLE.gcode) | [Offline NC](三叶扇/三叶扇_新算法_离线检查_20260921.gcode) |


The original three-blade program's B-axis and macro meanings have not been confirmed against its machine configuration. Do not interpret B as the new program's C axis without checking the controller, offsets, and kinematics. Before any machine trial, verify the nozzle, fixture, cutter macro, travel limits, and complete path for the target equipment.
