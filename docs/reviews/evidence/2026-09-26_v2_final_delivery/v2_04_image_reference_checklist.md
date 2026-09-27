# V2-04 教程图片逐处检查清单

生成日期：2026-09-27。范围：当前 `docs/guides/**/*.md` 的本地行内图片引用。机器可读条目、图片尺寸、对比度、文档及图片 SHA-256 见同名 JSON。

## 当前盘点

- 本地图片引用 83 处，唯一图片 45 张，缺失 0。
- 英文教程引用文件名含 `_zh` 的图片 13 处。计划中的 12 处是历史记录，本清单采用当前文件结果。
- 低对比度候选为 15 张唯一图片；一张图片可能在多个文档中引用。
- 全部视觉及图注状态均为“待核”；本清单不计入视觉验收通过数。

## 方法与使用

按文档路径排序、按行读取 Markdown 图片语法，排除远程 URL 与页内锚点。语言取文档名 `_en` / `_zh` 后缀；英文引用 `_zh` 仅按图片路径识别，不能代替读取图片内容。低对比规则与 `scripts/audit_guide_images.py` 一致：转 RGB、缩略至 128×72，三个通道标准差均值小于 20.0。

逐张检查 45 个唯一图片的文字、路径、按钮、状态、旧版本号、鼠标光晕及遮挡；再逐处检查 83 个引用的上下文与图注。复用图片只需一次图像检查，但不同图注须分别核对。低对比候选须记录替换结果或保留理由。文件存在及低对比统计均不能证明视觉合格；本轮未打开图片作视觉判断。

正文和图片可能继续变化。检查前核对同名 JSON 中的哈希与行号，变化时重新定位；不要把旧清单状态用于新图片。

## 逐处条目

文档列给出仓库相对路径与行号；图片列为仓库相对路径。唯一图片编号用于合并重复图像检查。

| 引用 | 文档与行号 | 唯一图 | 图片路径 | 语言 | 英文引用 _zh | 低对比候选 | 视觉 | 图注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| REF-001 | `docs/guides/curve_workbench_en.md:7` | IMG-001 | `docs/guides/assets/product_delivery/20_curve_edge_selected_en.png` | en | 否 | 否 | 待核 | 待核 |
| REF-002 | `docs/guides/curve_workbench_zh.md:20` | IMG-002 | `docs/guides/assets/product_delivery/20_curve_edge_selected_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-003 | `docs/guides/curve_workbench_zh.md:40` | IMG-003 | `docs/guides/assets/product_delivery/06_curve_pick_edge_face_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-004 | `docs/guides/curve_workbench_zh.md:44` | IMG-004 | `docs/guides/assets/curve/current_c01_c05/06_curve_buildup_zh_1366x768_path_only.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-005 | `docs/guides/curve_workbench_zh.md:46` | IMG-005 | `docs/guides/assets/curve/current_c01_c05/07_curve_multi_pass_en_1600x900_path_only.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-006 | `docs/guides/curve_workbench_zh.md:48` | IMG-006 | `docs/guides/assets/curve/current_c01_c05/08_curve_offset_buildup_en_1920x1080_path_only.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-007 | `docs/guides/curve_workbench_zh.md:102` | IMG-007 | `docs/guides/assets/curve/current_c01_c05/04_offset_failure_zh_1366x768.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-008 | `docs/guides/curve_workbench_zh.md:106` | IMG-008 | `docs/guides/assets/curve/current_c01_c05/05_offset_recovered_zh_1366x768.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-009 | `docs/guides/freeform_workbench_en.md:19` | IMG-009 | `docs/guides/assets/product_delivery/04_freeform_mode_zh.jpg` | en | 是 | 否 | 待核 | 待核 |
| REF-010 | `docs/guides/freeform_workbench_zh.md:21` | IMG-009 | `docs/guides/assets/product_delivery/04_freeform_mode_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-011 | `docs/guides/gcode_preview_en.md:21` | IMG-010 | `docs/guides/assets/product_delivery/10_gcode_file_preview_zh.jpg` | en | 是 | 否 | 待核 | 待核 |
| REF-012 | `docs/guides/gcode_preview_zh.md:21` | IMG-010 | `docs/guides/assets/product_delivery/10_gcode_file_preview_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-013 | `docs/guides/gcode_preview_zh.md:52` | IMG-011 | `docs/guides/assets/product_delivery/pipe2_full_path_zh_20260923.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-014 | `docs/guides/machine_profiles_en.md:5` | IMG-012 | `docs/guides/assets/product_delivery/08_machine_setup_zh.png` | en | 是 | 否 | 待核 | 待核 |
| REF-015 | `docs/guides/machine_profiles_zh.md:9` | IMG-012 | `docs/guides/assets/product_delivery/08_machine_setup_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-016 | `docs/guides/machine_profiles_zh.md:37` | IMG-013 | `docs/guides/assets/machine_profiles/rotary_axis_words_zh.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-017 | `docs/guides/material_channels_en.md:14` | IMG-014 | `docs/guides/assets/product_delivery/19_material_table_two_color_en.png` | en | 否 | 否 | 待核 | 待核 |
| REF-018 | `docs/guides/material_channels_zh.md:14` | IMG-015 | `docs/guides/assets/product_delivery/19_material_table_two_color_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-019 | `docs/guides/material_channels_zh.md:16` | IMG-016 | `docs/guides/assets/product_delivery/18_tool_change_station_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-020 | `docs/guides/planar_workbench_en.md:15` | IMG-017 | `docs/guides/assets/product_delivery/07_planar_full_lines_zh.png` | en | 是 | 否 | 待核 | 待核 |
| REF-021 | `docs/guides/planar_workbench_zh.md:25` | IMG-017 | `docs/guides/assets/product_delivery/07_planar_full_lines_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-022 | `docs/guides/planar_workbench_zh.md:79` | IMG-018 | `docs/guides/assets/planar/current_p01_p07/p07/00_support_grid_zh_1366x768_parameters.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-023 | `docs/guides/planar_workbench_zh.md:103` | IMG-019 | `docs/guides/assets/planar/current_p01_p07/p07/01_support_grid_zh_1366x768_ready.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-024 | `docs/guides/planar_workbench_zh.md:105` | IMG-020 | `docs/guides/assets/planar/current_p01_p07/p07/02_support_lines_en_1600x900_ready.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-025 | `docs/guides/planar_workbench_zh.md:109` | IMG-021 | `docs/guides/assets/planar/current_p01_p07/p07/04_support_error_en_1366x768.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-026 | `docs/guides/planar_workbench_zh.md:138` | IMG-022 | `docs/guides/assets/planar/current_p01_p07/p06/07_planar_spiral_error_zh_1366x768.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-027 | `docs/guides/planar_workbench_zh.md:142` | IMG-023 | `docs/guides/assets/planar/current_p01_p07/p06/08_planar_spiral_recovered_en_1600x900.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-028 | `docs/guides/quickstart_clickthrough_en.md:20` | IMG-024 | `docs/guides/assets/product_delivery/01_home_zh.jpg` | en | 是 | 否 | 待核 | 待核 |
| REF-029 | `docs/guides/quickstart_clickthrough_en.md:32` | IMG-017 | `docs/guides/assets/product_delivery/07_planar_full_lines_zh.png` | en | 是 | 否 | 待核 | 待核 |
| REF-030 | `docs/guides/quickstart_clickthrough_en.md:40` | IMG-003 | `docs/guides/assets/product_delivery/06_curve_pick_edge_face_zh.png` | en | 是 | 否 | 待核 | 待核 |
| REF-031 | `docs/guides/quickstart_clickthrough_en.md:48` | IMG-025 | `docs/guides/assets/product_delivery/09_rotary_around_part_paths_zh.png` | en | 是 | 否 | 待核 | 待核 |
| REF-032 | `docs/guides/quickstart_clickthrough_en.md:56` | IMG-026 | `docs/guides/assets/product_delivery/12_tube_geometry_selected_zh.jpg` | en | 是 | 否 | 待核 | 待核 |
| REF-033 | `docs/guides/quickstart_clickthrough_en.md:66` | IMG-027 | `docs/guides/assets/product_delivery/13_freeform_role_fields_zh.jpg` | en | 是 | 否 | 待核 | 待核 |
| REF-034 | `docs/guides/quickstart_clickthrough_en.md:74` | IMG-010 | `docs/guides/assets/product_delivery/10_gcode_file_preview_zh.jpg` | en | 是 | 否 | 待核 | 待核 |
| REF-035 | `docs/guides/quickstart_clickthrough_zh.md:16` | IMG-024 | `docs/guides/assets/product_delivery/01_home_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-036 | `docs/guides/quickstart_clickthrough_zh.md:22` | IMG-028 | `docs/guides/assets/product_delivery/11_setup_part_ready_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-037 | `docs/guides/quickstart_clickthrough_zh.md:32` | IMG-029 | `docs/guides/assets/product_delivery/14_workbench_common_setup_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-038 | `docs/guides/quickstart_clickthrough_zh.md:43` | IMG-030 | `docs/guides/assets/product_delivery/15_workbench_local_editor_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-039 | `docs/guides/quickstart_clickthrough_zh.md:47` | IMG-031 | `docs/guides/assets/product_delivery/16_workbench_local_scope_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-040 | `docs/guides/quickstart_clickthrough_zh.md:57` | IMG-017 | `docs/guides/assets/product_delivery/07_planar_full_lines_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-041 | `docs/guides/quickstart_clickthrough_zh.md:69` | IMG-003 | `docs/guides/assets/product_delivery/06_curve_pick_edge_face_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-042 | `docs/guides/quickstart_clickthrough_zh.md:79` | IMG-032 | `docs/guides/assets/rotary/live_qt/02_selection_overview_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-043 | `docs/guides/quickstart_clickthrough_zh.md:81` | IMG-025 | `docs/guides/assets/product_delivery/09_rotary_around_part_paths_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-044 | `docs/guides/quickstart_clickthrough_zh.md:93` | IMG-026 | `docs/guides/assets/product_delivery/12_tube_geometry_selected_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-045 | `docs/guides/quickstart_clickthrough_zh.md:97` | IMG-011 | `docs/guides/assets/product_delivery/pipe2_full_path_zh_20260923.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-046 | `docs/guides/quickstart_clickthrough_zh.md:109` | IMG-009 | `docs/guides/assets/product_delivery/04_freeform_mode_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-047 | `docs/guides/quickstart_clickthrough_zh.md:111` | IMG-027 | `docs/guides/assets/product_delivery/13_freeform_role_fields_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-048 | `docs/guides/quickstart_clickthrough_zh.md:119` | IMG-010 | `docs/guides/assets/product_delivery/10_gcode_file_preview_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-049 | `docs/guides/rotary_workbench_en.md:17` | IMG-025 | `docs/guides/assets/product_delivery/09_rotary_around_part_paths_zh.png` | en | 是 | 否 | 待核 | 待核 |
| REF-050 | `docs/guides/rotary_workbench_zh.md:35` | IMG-025 | `docs/guides/assets/product_delivery/09_rotary_around_part_paths_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-051 | `docs/guides/rotary_workbench_zh.md:49` | IMG-032 | `docs/guides/assets/rotary/live_qt/02_selection_overview_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-052 | `docs/guides/rotary_workbench_zh.md:55` | IMG-033 | `docs/guides/assets/rotary/fan_blade_check/04_fan_selection_decision.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-053 | `docs/guides/rotary_workbench_zh.md:74` | IMG-034 | `docs/guides/assets/rotary/live_qt/03_coordinates_zh.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-054 | `docs/guides/rotary_workbench_zh.md:101` | IMG-025 | `docs/guides/assets/product_delivery/09_rotary_around_part_paths_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-055 | `docs/guides/rotary_workbench_zh.md:107` | IMG-035 | `docs/guides/assets/rotary/current_r01_r05/06_rotary_cross_zero_zh_1366x768.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-056 | `docs/guides/rotary_workbench_zh.md:191` | IMG-036 | `docs/guides/assets/rotary/current_r01_r05/07_rotary_axis_limit_error_zh_1366x768.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-057 | `docs/guides/rotary_workbench_zh.md:195` | IMG-037 | `docs/guides/assets/rotary/live_qt/06_acceleration_limit_error_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-058 | `docs/guides/rotary_workbench_zh.md:197` | IMG-038 | `docs/guides/assets/rotary/current_r01_r05/08_rotary_axis_limit_recovered_zh_1366x768.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-059 | `docs/guides/rotary_workbench_zh.md:216` | IMG-039 | `docs/guides/assets/rotary/current_r01_r05/09_rotary_export_zh_1600x900.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-060 | `docs/guides/rotary_workbench_zh.md:227` | IMG-040 | `docs/guides/assets/rotary/live_qt/07_input_change_stale_zh.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-061 | `docs/guides/rotary_workbench_zh.md:229` | IMG-041 | `docs/guides/assets/rotary/current_r01_r05/10_rotary_reopen_stale_en_1920x1080.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-062 | `docs/guides/tube_coordinate_setup_zh.md:15` | IMG-024 | `docs/guides/assets/product_delivery/01_home_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-063 | `docs/guides/tube_coordinate_setup_zh.md:52` | IMG-028 | `docs/guides/assets/product_delivery/11_setup_part_ready_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-064 | `docs/guides/tube_coordinate_setup_zh.md:101` | IMG-042 | `docs/guides/assets/tube_coordinate_setup/03_model_cs_editor.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-065 | `docs/guides/tube_coordinate_setup_zh.md:111` | IMG-043 | `docs/guides/assets/tube_coordinate_setup/04_build_cs_editor.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-066 | `docs/guides/tube_coordinate_setup_zh.md:124` | IMG-044 | `docs/guides/assets/tube_coordinate_setup/05_placement_editor.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-067 | `docs/guides/tube_workbench_en.md:27` | IMG-011 | `docs/guides/assets/product_delivery/pipe2_full_path_zh_20260923.png` | en | 是 | 否 | 待核 | 待核 |
| REF-068 | `docs/guides/tube_workbench_zh.md:23` | IMG-026 | `docs/guides/assets/product_delivery/12_tube_geometry_selected_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-069 | `docs/guides/tube_workbench_zh.md:35` | IMG-028 | `docs/guides/assets/product_delivery/11_setup_part_ready_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-070 | `docs/guides/tube_workbench_zh.md:45` | IMG-042 | `docs/guides/assets/tube_coordinate_setup/03_model_cs_editor.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-071 | `docs/guides/tube_workbench_zh.md:47` | IMG-043 | `docs/guides/assets/tube_coordinate_setup/04_build_cs_editor.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-072 | `docs/guides/tube_workbench_zh.md:53` | IMG-044 | `docs/guides/assets/tube_coordinate_setup/05_placement_editor.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-073 | `docs/guides/tube_workbench_zh.md:100` | IMG-011 | `docs/guides/assets/product_delivery/pipe2_full_path_zh_20260923.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-074 | `docs/guides/user_learning_manual_zh.md:98` | IMG-024 | `docs/guides/assets/product_delivery/01_home_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-075 | `docs/guides/user_learning_manual_zh.md:112` | IMG-028 | `docs/guides/assets/product_delivery/11_setup_part_ready_zh.jpg` | zh | 否 | 否 | 待核 | 待核 |
| REF-076 | `docs/guides/user_learning_manual_zh.md:127` | IMG-042 | `docs/guides/assets/tube_coordinate_setup/03_model_cs_editor.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-077 | `docs/guides/user_learning_manual_zh.md:133` | IMG-012 | `docs/guides/assets/product_delivery/08_machine_setup_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-078 | `docs/guides/user_learning_manual_zh.md:154` | IMG-045 | `docs/guides/assets/curve/current_c01_c05/09_curve_overview_edge_normal_zh_1366x768.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-079 | `docs/guides/user_learning_manual_zh.md:158` | IMG-025 | `docs/guides/assets/product_delivery/09_rotary_around_part_paths_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-080 | `docs/guides/user_learning_manual_zh.md:189` | IMG-017 | `docs/guides/assets/product_delivery/07_planar_full_lines_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-081 | `docs/guides/user_learning_manual_zh.md:229` | IMG-040 | `docs/guides/assets/rotary/live_qt/07_input_change_stale_zh.png` | zh | 否 | 是 | 待核 | 待核 |
| REF-082 | `docs/guides/user_learning_manual_zh.md:233` | IMG-037 | `docs/guides/assets/rotary/live_qt/06_acceleration_limit_error_zh.png` | zh | 否 | 否 | 待核 | 待核 |
| REF-083 | `docs/guides/user_learning_manual_zh.md:247` | IMG-039 | `docs/guides/assets/rotary/current_r01_r05/09_rotary_export_zh_1600x900.png` | zh | 否 | 否 | 待核 | 待核 |

## 使用的 Skills

- `five-axis-workbench-development`：教程图片、引用及内部证据的边界，另读 `references/product-delivery-lessons.md`。
- `five-axis-slicer-validation`：使用已知解释器做只读检查，区分文件检查与真实视觉验收。

本轮未修改现有教程、图片或主台账，未启动 Qt。
