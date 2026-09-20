"""Tube Setup labels and the coordinate-entry order shared by Qt shells."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PyQt5.QtCore import Qt

from .manufacturing.setup import (
    BUILD_CS_NODE,
    MACHINE_NODE,
    MATERIAL_NODE,
    MODEL_CS_NODE,
    NOZZLE_NODE,
    PART_NODE,
    PLACEMENT_NODE,
    NodeState,
    SetupValidationReport,
)

TUBE_TEXT: dict[str, dict[str, str]] = {
    "zh": {
        "title": "管状工作台",
        "subtitle": "管状分度薄壁、加厚与连续螺旋：制造 Setup、生成、检查与输出",
        "back": "工作台",
        "open": "打开 STEP",
        "update_source": "从原文件更新",
        "save": "保存项目",
        "create_operation": "创建 Tube 操作",
        "operation_type": "操作类型",
        "operation_type_tube_thin_wall_indexed": "Tube 薄壁分度",
        "operation_type_tube_buildup": "Tube 加厚与底座",
        "operation_type_tube_continuous": "Tube 连续螺旋",
        "project": "项目",
        "model": "模型",
        "setup": "制造设置 1",
        "operations": "操作",
        "part": "零件（Part）",
        "machine": "机床（Machine）",
        "nozzle": "喷嘴",
        "material": "材料",
        "model_cs": "模型坐标系（Model CS）",
        "build_cs": "构建坐标系（Build CS）",
        "placement": "装夹定位（Placement）",
        "operation": "Tube Thin-Wall Indexed",
        "tube_body": "管体实体",
        "entry_port": "入口端口",
        "exit_port": "出口端口",
        "substrate": "既有基体",
        "bead_width": "道宽 (mm)",
        "layer_height": "层高 (mm)",
        "max_wedge_angle": "最大楔角 (deg)",
        "max_bead_error": "最大道高误差 (mm)",
        "safe_clearance": "安全间隙 (mm)",
        "retract_length": "回抽长度 (mm)",
        "deposition_feedrate": "沉积进给 (mm/min)",
        "travel_feedrate": "空移进给 (mm/min)",
        "chord_error": "弦高误差 (mm)",
        "maximum_pass_spacing": "最大道间距 (mm)",
        "include_planar_base": "包含平面底座",
        "base_order": "底座工序顺序",
        "before_tube": "底座在管体之前",
        "after_tube": "底座在管体之后",
        "seam_angle": "接缝角 (deg)",
        "operation_applied": "操作几何角色和工艺参数已应用。",
        "operation_pick": "拾取",
        "operation_pick_pending": "请在模型中点击对应实体或圆边。",
        "operation_pick_bound": "已选入几何草稿；点击应用后生效。",
        "generate": "生成",
        "cancel_generation": "取消生成",
        "preview_result": "查看路径",
        "export_result": "导出结果",
        "generation_draft": "尚未生成当前操作。",
        "generation_running": "正在生成操作路径…",
        "generation_ready": "路径、检查与 NC 回读已就绪。",
        "generation_warning": "路径已生成，但包含需要核对的警告。",
        "generation_error": "生成失败；请查看问题并修正输入。",
        "generation_stale": "操作已更改，已有结果过期；请重新生成。",
        "generation_cancel_requested": "已请求取消生成。",
        "generation_cancelled": "生成已取消，上一份结果保持不变。",
        "generation_preview_ready": "已在查看器中显示逐层路径。",
        "generation_preview_unavailable": "当前没有可预览的生成路径。",
        "generation_exported": "已导出生成结果。",
        "model_view": "模型视图",
        "machine_view": "机床视图",
        "editor_empty": "从左侧树选择 Setup 节点。",
        "part_help": "一个 Part 可包含多个封闭 solid；未分配和 Ignore 不参与后续计算。",
        "body": "实体",
        "kind": "类型",
        "role": "角色",
        "role_part": "零件",
        "role_ignore": "忽略",
        "role_unassigned": "未分配",
        "confirm": "确认",
        "apply": "应用",
        "cancel": "取消",
        "flip": "翻转",
        "resource_help": "内置资源是只读模板，项目保存冻结快照。",
        "resource_origin_builtin": "内置",
        "resource_origin_user": "用户库",
        "resource_origin_snapshot": "项目快照",
        "resource_status_diverged": "已分叉",
        "resource_status_missing": "库中缺失",
        "select_machine": "选择 Machine Profile",
        "select_nozzle": "选择喷嘴身份模板",
        "select_material": "选择 Cura 材料模板",
        "interface": "安装接口（螺纹/型号）",
        "length": "总长 (mm)",
        "collision_profile": "使用 R–Z 碰撞外形（缺失时生成简化外形）",
        "not_set": "未填写",
        "nozzle_interface_placeholder": "例如：M6×1 螺纹 / 厂家接口型号",
        "nozzle_collision_length_required": "勾选 R–Z 外形前，请先填写正数总长。",
        "nozzle_collision_length_changed": (
            "已有 R–Z 外形与原总长绑定。要修改总长，请先取消勾选并应用，"
            "再重新勾选以生成匹配新总长的简化外形。"
        ),
        "review": "已核对来源中的材料单点建议值",
        "coordinate_help_model": "数值输入基于 Source CS。原点、Z 和 X 需要逐项确认。",
        "coordinate_help_build": "数值输入默认基于 Model CS，保存时换算到 Source CS。",
        "origin": "原点",
        "z_direction": "Z方向",
        "x_direction": "X方向",
        "pick": "拾取",
        "numeric": "数值输入",
        "pick_vertex": "拾取顶点",
        "pick_face": "拾取面上点",
        "pick_line": "拾取直边",
        "pick_axis_face": "拾取平面/圆柱/圆锥面",
        "pick_two_vertices": "拾取两个顶点",
        "coordinate_reconfirm_error": "原点、Z 或 X 已修改，请重新确认后再应用。",
        "placement_help": "Build CS 与打印板安装位配对；微调顺序为平移、Rx、Ry、Rz。",
        "mount": "打印板安装位",
        "coordinates_valid": "坐标有效",
        "setup_ready": "设置就绪",
        "issues": "问题列表",
        "no_issues": "当前没有问题。",
        "ready_warning": "就绪（有警告）",
        "status_missing": "缺失",
        "status_draft": "草稿",
        "status_valid": "有效",
        "status_dirty": "待更新",
        "status_invalid": "无效",
        "help_open": "导入一个可含多个实体的 STEP，并生成零件与坐标参考候选。",
        "help_update_source": (
            "重新读取原始 STEP，并按几何签名唯一重绑定实体和坐标引用。"
            "缺失或歧义引用会进入无效状态。"
        ),
        "help_save": (
            "保存项目内 STEP、资源快照、坐标和装夹。存在草稿时会要求应用、放弃或取消保存。"
        ),
        "help_create_operation": ("选择 Tube 操作类型后创建；每个 Setup 最多三条操作。"),
        "help_operation": (
            "选择管体、入口圆边、出口圆边和既有基体，并填写带明确单位的切层与转位参数。"
            "应用后几何或参数变化会把操作标记为待更新。"
        ),
        "help_model_view": "在 STEP Source CS 中显示模型、Model CS 和 Build CS。",
        "help_machine_view": (
            "按当前装夹变换显示模型、Machine CS 和 Machine Profile 提供的打印板。"
        ),
        "help_part_role": (
            "零件纳入当前打印件；忽略表示明确排除；未分配表示尚未决定。"
            "忽略和未分配实体均不参与后续计算。"
        ),
        "help_role_part": "纳入当前 Part。只接受封闭 solid，多实体可属于同一个 Part。",
        "help_role_ignore": "明确排除该实体，并在项目中保存排除意图。",
        "help_role_unassigned": "暂不决定归属；不参与后续计算，也不阻止继续设置。",
        "help_part_confirm": "提交当前实体归属。Part 至少需要一个封闭 solid。",
        "help_machine_profile": (
            "选择包含轴链、Machine CS、打印板和安装位的机床 Profile。"
            "名称带 Reference 的内置项只供坐标设置和预览。"
        ),
        "help_machine_apply": (
            "把所选机床 Profile 的冻结快照应用到当前 Setup。更换机床会使装夹定位待更新。"
        ),
        "help_nozzle_profile": (
            "内置 0.4、0.6、0.8 mm 项只固定喷孔和丝径。"
            "安装接口、实测总长和碰撞外形需按图纸或实物补齐。"
        ),
        "help_nozzle_interface": (
            "填写喷嘴与加热块或热端的机械连接规格，例如 M6×1 螺纹；"
            "专用接口可填写厂家系列和接口型号。未知时留空，设置保持未就绪。"
            "当前只检查文本非空，不执行接口兼容性判断。"
        ),
        "help_nozzle_length": (
            "沿喷嘴轴线测量：喷尖为 Z=0，+Z 指向安装端，总长是到安装端最远点的距离，单位 mm。"
            "请采用厂家图纸或实测值；未知时保留“未填写”。"
        ),
        "help_nozzle_collision": (
            "Profile 已有 R–Z 外形时保留原轮廓；缺失时按喷孔直径和总长生成简化外形。"
            "修改总长需先取消勾选并应用，再重新勾选生成。当前不渲染外形，也不执行碰撞检查。"
        ),
        "help_nozzle_apply": (
            "保存已编辑的用户喷嘴 Profile，并把冻结快照应用到 Setup。"
            "接口、正数总长和 R–Z 外形齐全后喷嘴节点才有效。"
        ),
        "help_material_profile": (
            "选择固定来源版本的 Cura Generic 材料。下方温度是来源文件中的单点建议值；"
            "实际工艺参数归入后续 Process Profile。"
        ),
        "help_material_detail": (
            "显示材料、丝径、来源单点温度和固定 revision。审核时应对照来源记录。"
        ),
        "help_material_review": (
            "勾选表示已核对当前材料的来源、revision 及温度单点值。"
            "该确认只解除资源审核门禁，不表示工艺已经验证。"
        ),
        "help_material_apply": (
            "勾选审核后创建用户副本并冻结到项目；未勾选时材料节点保持草稿状态。"
        ),
        "help_origin_reference": (
            "选择数值输入、几何拾取方式或系统识别的原点候选。拾取方式需先点击“拾取”。"
        ),
        "help_direction_reference": (
            "选择数值向量、直边、面法向、回转面轴线、两个顶点或系统识别的方向候选。"
        ),
        "help_z_reference": ("定义目标坐标系的 +Z。结合预览核对方向，方向相反时使用“翻转”。"),
        "help_x_reference": (
            "提供目标坐标系的 +X 参考。系统移除其沿 Z 的分量，再按 Y=Z×X 建立右手系；"
            "X 与 Z 共线会阻止应用。"
        ),
        "help_origin_numeric_model": "Model CS 原点在 Source CS 中的 X、Y、Z 坐标，单位 mm。",
        "help_origin_numeric_build": (
            "Build CS 原点在 Model CS 中的 X、Y、Z 坐标，单位 mm；应用时转换到 Source CS。"
        ),
        "help_direction_numeric_model": "方向向量在 Source CS 中的 X、Y、Z 分量，无单位。",
        "help_direction_numeric_build": (
            "方向向量在 Model CS 中的 X、Y、Z 分量，无单位；应用时转换到 Source CS。"
        ),
        "help_coordinate_pick": (
            "进入当前参考类型的拾取状态。两点方向按起点、终点依次拾取，方向指向终点。"
        ),
        "help_coordinate_confirm": (
            "把当前数值或拾取结果写入坐标草稿。修改数值或候选后需要重新确认。"
        ),
        "help_coordinate_flip": "将当前 Z 或 X 参考方向乘以 −1，几何引用保持不变。",
        "help_coordinate_apply": (
            "校验原点、Z、X 和右手刚体矩阵后原子提交。三项需分别确认；"
            "零向量、X/Z 共线和非有限值会阻止提交。"
        ),
        "help_coordinate_cancel": "丢弃当前坐标草稿，保留上一次已应用的有效坐标系。",
        "help_candidate_numeric": "手工输入 XYZ；原点单位为 mm，方向向量无单位。",
        "help_candidate_vertex": "使用精确拓扑顶点作为原点。",
        "help_candidate_face": "把点击位置投影到所选面的有效面域。",
        "help_candidate_line": "使用直线边的轴向；方向可翻转。",
        "help_candidate_axis_face": "使用平面法向、圆柱轴线或圆锥轴线；方向可翻转。",
        "help_candidate_two_vertices": "依次选择两个顶点，方向为第二点减第一点。",
        "help_detected_candidate": "使用 STEP 几何识别出的候选参考；确认前请在预览中核对。",
        "help_mount": (
            "选择 Machine Profile 中命名的打印板安装基准，与 Build CS 配对。"
            "列表为空时请先应用带安装位的机床 Profile。"
        ),
        "help_placement_translation": (
            "沿配对后 Build CS 的局部 +{axis} 方向进行装夹平移补偿，单位 mm；没有测量偏差时保持 0。"
        ),
        "help_placement_rotation": (
            "绕配对后的局部 {axis} 轴按右手定则旋转，单位为度。"
            "组合公式为 T_ref·Translate·Rx·Ry·Rz；没有测量偏差时保持 0。"
        ),
        "help_placement_apply": (
            "Build CS 和机床有效后，提交安装位与六自由度微调，并切换到机床视图。"
        ),
        "help_placement_cancel": "丢弃当前装夹草稿，恢复上一次已应用的装夹定位。",
        "help_coordinates_valid": (
            "要求 Part、Machine、Model CS、Build CS 和 Placement 均有效；喷嘴和材料不参与此门禁。"
        ),
        "help_setup_ready": (
            "还要求喷嘴完整、材料已审核且没有 Error。参考机型允许带警告就绪，可执行 NC 仍受限制。"
        ),
        "help_issues": "双击或按 Enter 跳转到对应 Setup 节点；稳定问题码用于保存与自动化定位。",
    },
    "en": {
        "title": "Tube Workbench",
        "subtitle": "Indexed, buildup, and continuous Tube operations: Setup, generate, validate, and export",
        "back": "Workbench",
        "open": "Open STEP",
        "update_source": "Update from Source",
        "save": "Save Project",
        "create_operation": "Create Tube Operation",
        "operation_type": "Operation type",
        "operation_type_tube_thin_wall_indexed": "Tube Thin-Wall Indexed",
        "operation_type_tube_buildup": "Tube Buildup and Base",
        "operation_type_tube_continuous": "Tube Continuous Helix",
        "project": "Project",
        "model": "Model",
        "setup": "Manufacturing Setup 1",
        "operations": "Operations",
        "part": "Part",
        "machine": "Machine",
        "nozzle": "Nozzle",
        "material": "Material",
        "model_cs": "Model CS",
        "build_cs": "Build CS",
        "placement": "Placement",
        "operation": "Tube Thin-Wall Indexed",
        "tube_body": "Tube body",
        "entry_port": "Entry port",
        "exit_port": "Exit port",
        "substrate": "Existing substrate",
        "bead_width": "Bead width (mm)",
        "layer_height": "Layer height (mm)",
        "max_wedge_angle": "Max wedge angle (deg)",
        "max_bead_error": "Max bead-height error (mm)",
        "safe_clearance": "Safe clearance (mm)",
        "retract_length": "Retract length (mm)",
        "deposition_feedrate": "Deposition feedrate (mm/min)",
        "travel_feedrate": "Travel feedrate (mm/min)",
        "chord_error": "Chord error (mm)",
        "maximum_pass_spacing": "Maximum pass spacing (mm)",
        "include_planar_base": "Include planar base",
        "base_order": "Base operation order",
        "before_tube": "Base before tube",
        "after_tube": "Base after tube",
        "seam_angle": "Seam angle (deg)",
        "operation_applied": "Operation geometry roles and process parameters applied.",
        "operation_pick": "Pick",
        "operation_pick_pending": "Click the required solid or circular edge in the model.",
        "operation_pick_bound": "Geometry selected in draft; click Apply to commit.",
        "generate": "Generate",
        "cancel_generation": "Cancel Generate",
        "preview_result": "Preview Path",
        "export_result": "Export Result",
        "generation_draft": "This operation has not been generated.",
        "generation_running": "Generating operation path…",
        "generation_ready": "Path, validation, and NC readback are ready.",
        "generation_warning": "Path generated with warnings that require review.",
        "generation_error": "Generation failed. Review the issues and correct the input.",
        "generation_stale": "The operation changed; the existing result is stale. Generate again.",
        "generation_cancel_requested": "Generation cancellation requested.",
        "generation_cancelled": "Generation cancelled; the previous result is unchanged.",
        "generation_preview_ready": "The layered path is visible in the viewer.",
        "generation_preview_unavailable": "There is no generated path available for preview.",
        "generation_exported": "Generated result exported.",
        "model_view": "Model View",
        "machine_view": "Machine View",
        "editor_empty": "Select a Setup node in the tree.",
        "part_help": "One Part may contain several closed solids. Unassigned and Ignore bodies are excluded.",
        "body": "Body",
        "kind": "Kind",
        "role": "Role",
        "role_part": "Part",
        "role_ignore": "Ignore",
        "role_unassigned": "Unassigned",
        "confirm": "Confirm",
        "apply": "Apply",
        "cancel": "Cancel",
        "flip": "Flip",
        "resource_help": "Built-in resources are read-only templates; projects store frozen snapshots.",
        "resource_origin_builtin": "Built-in",
        "resource_origin_user": "User library",
        "resource_origin_snapshot": "Project snapshot",
        "resource_status_diverged": "Diverged",
        "resource_status_missing": "Missing from library",
        "select_machine": "Select Machine Profile",
        "select_nozzle": "Select nozzle identity template",
        "select_material": "Select Cura material template",
        "interface": "Mount interface (thread/model)",
        "length": "Overall length (mm)",
        "collision_profile": "Use R–Z collision shape (generate a coarse shape when missing)",
        "not_set": "Not set",
        "nozzle_interface_placeholder": "e.g. M6×1 thread / vendor interface ID",
        "nozzle_collision_length_required": (
            "Enter a positive overall length before enabling the R–Z shape."
        ),
        "nozzle_collision_length_changed": (
            "The existing R–Z shape is tied to its original length. Clear the checkbox and Apply first, "
            "then enable it again to generate a coarse shape for the new length."
        ),
        "review": "Pinned material recommendations reviewed",
        "coordinate_help_model": "Numeric values use Source CS. Confirm origin, Z, and X separately.",
        "coordinate_help_build": "Numeric values use Model CS by default and are persisted in Source CS.",
        "origin": "Origin",
        "z_direction": "Z direction",
        "x_direction": "X direction",
        "pick": "Pick",
        "numeric": "Numeric",
        "pick_vertex": "Pick vertex",
        "pick_face": "Pick point on face",
        "pick_line": "Pick straight edge",
        "pick_axis_face": "Pick plane/cylinder/cone face",
        "pick_two_vertices": "Pick two vertices",
        "coordinate_reconfirm_error": "Origin, Z, or X changed. Confirm it again before Apply.",
        "placement_help": "Pair Build CS to a plate mount; adjustment order is translate, Rx, Ry, Rz.",
        "mount": "Build-plate mount",
        "coordinates_valid": "Coordinates Valid",
        "setup_ready": "Setup Ready",
        "issues": "Issues",
        "no_issues": "No current issues.",
        "ready_warning": "Ready with Warnings",
        "status_missing": "Missing",
        "status_draft": "Draft",
        "status_valid": "Valid",
        "status_dirty": "Dirty",
        "status_invalid": "Invalid",
        "help_open": "Import one STEP containing one or more bodies and create Part and coordinate candidates.",
        "help_update_source": (
            "Reload the original STEP and uniquely rebind bodies and coordinate references by geometry "
            "signature. Missing or ambiguous references become Invalid."
        ),
        "help_save": (
            "Save the embedded STEP, resource snapshots, coordinates, and placement. Pending drafts "
            "require Apply, Discard, or Cancel."
        ),
        "help_create_operation": (
            "Choose a Tube operation type, then create it. Each Setup permits at most three operations."
        ),
        "help_operation": (
            "Select the tube body, circular entry and exit edges, and existing substrate, then enter "
            "the slicing and indexing parameters in the displayed units. Applying a changed role or "
            "parameter marks the operation Dirty."
        ),
        "help_model_view": "Show the model, Model CS, and Build CS in STEP Source CS.",
        "help_machine_view": (
            "Show the placed model, Machine CS, and build surface supplied by the Machine Profile."
        ),
        "help_part_role": (
            "Part includes a body in the manufactured part. Ignore explicitly excludes it. Unassigned "
            "leaves the decision open. Ignore and Unassigned bodies are excluded downstream."
        ),
        "help_role_part": (
            "Include this body in the Part. Only closed solids are eligible; one Part may contain several."
        ),
        "help_role_ignore": "Explicitly exclude this body and preserve that decision in the project.",
        "help_role_unassigned": (
            "Leave the role undecided. The body is excluded downstream and does not block setup editing."
        ),
        "help_part_confirm": "Commit the body assignments. Part requires at least one closed solid.",
        "help_machine_profile": (
            "Select a profile containing the axis chain, Machine CS, build surface, and mount datums. "
            "Built-in Reference profiles support setup and preview only."
        ),
        "help_machine_apply": (
            "Apply a frozen snapshot of the selected Machine Profile. Changing it makes Placement dirty."
        ),
        "help_nozzle_profile": (
            "Built-in 0.4, 0.6, and 0.8 mm entries contain nozzle and filament identity only. Complete "
            "the interface, measured length, and collision shape from drawings or physical data."
        ),
        "help_nozzle_interface": (
            "Enter the mechanical connection to the heater block or hot end, for example M6×1 thread. "
            "For proprietary interfaces, enter the vendor family and interface ID. Leave blank when "
            "unknown. This field is checked for non-empty text only; compatibility is not inferred."
        ),
        "help_nozzle_length": (
            "Measure along the nozzle axis: the tip is Z=0, +Z points toward the mount, and overall "
            "length reaches the farthest mounting end, in mm. Use drawing or measured data."
        ),
        "help_nozzle_collision": (
            "Keep an existing Profile R–Z shape, or generate a coarse one from orifice diameter and length "
            "when missing. To change length, clear and Apply the shape first, then enable it again. This "
            "version neither renders the shape nor runs collision checks."
        ),
        "help_nozzle_apply": (
            "Save edited data as a user nozzle profile and apply its frozen snapshot. Interface, positive "
            "length, and a valid R–Z shape are required for a Valid nozzle node."
        ),
        "help_material_profile": (
            "Select a Cura Generic material pinned to a source revision. Values below are source-provided "
            "nominal temperatures; process settings belong to a future Process Profile."
        ),
        "help_material_detail": (
            "Shows material, filament diameter, source nominal temperatures, and pinned revision. "
            "Compare them with the recorded source before review."
        ),
        "help_material_review": (
            "Check after reviewing the source, revision, and nominal temperatures. This clears the resource "
            "review gate only; it does not validate the manufacturing process."
        ),
        "help_material_apply": (
            "After review, create a user copy and freeze it into the project. Without review, the Material "
            "node remains Draft."
        ),
        "help_origin_reference": (
            "Choose numeric input, a geometry pick mode, or a detected origin candidate. Pick modes require "
            "pressing Pick before selecting geometry."
        ),
        "help_direction_reference": (
            "Choose a numeric vector, straight edge, face normal, surface axis, two vertices, or a detected "
            "direction candidate."
        ),
        "help_z_reference": (
            "Define target +Z. Verify the sign in the preview and use Flip when it is reversed."
        ),
        "help_x_reference": (
            "Provide target +X. Its component along Z is removed, then Y=Z×X forms a right-handed frame. "
            "Collinear X and Z are rejected."
        ),
        "help_origin_numeric_model": "Model CS origin X, Y, and Z in Source CS, in mm.",
        "help_origin_numeric_build": (
            "Build CS origin X, Y, and Z in Model CS, in mm. Apply converts values to Source CS."
        ),
        "help_direction_numeric_model": "Dimensionless direction X, Y, and Z in Source CS.",
        "help_direction_numeric_build": (
            "Dimensionless direction X, Y, and Z in Model CS. Apply converts values to Source CS."
        ),
        "help_coordinate_pick": (
            "Start the selected pick mode. For a two-point direction, pick start then end; the vector points "
            "toward the end."
        ),
        "help_coordinate_confirm": (
            "Write the current value or pick into the coordinate draft. Confirm again after changing a value "
            "or candidate."
        ),
        "help_coordinate_flip": "Multiply the current Z or X direction by −1 without changing its geometry reference.",
        "help_coordinate_apply": (
            "Atomically apply after validating origin, Z, X, and the right-handed rigid transform. All three "
            "references must be confirmed; zero, collinear, and non-finite values are rejected."
        ),
        "help_coordinate_cancel": "Discard this coordinate draft and retain the last applied frame.",
        "help_candidate_numeric": "Enter XYZ manually; origins use mm and directions are dimensionless.",
        "help_candidate_vertex": "Use the exact topology vertex as the origin.",
        "help_candidate_face": "Project the clicked position onto the selected trimmed face.",
        "help_candidate_line": "Use the straight-edge direction; its sign can be flipped.",
        "help_candidate_axis_face": "Use a plane normal, cylinder axis, or cone axis; its sign can be flipped.",
        "help_candidate_two_vertices": "Pick two vertices in order; direction equals second point minus first.",
        "help_detected_candidate": "Use a candidate detected from STEP geometry; verify it in the preview before confirming.",
        "help_mount": (
            "Select a named build-surface mount datum from the Machine Profile and pair it with Build CS. "
            "Apply a machine with mount datums when this list is empty."
        ),
        "help_placement_translation": (
            "Translate along paired local Build CS +{axis}, in mm. Keep zero when no measured offset exists."
        ),
        "help_placement_rotation": (
            "Rotate about paired local {axis} using the right-hand rule, in degrees. Composition is "
            "T_ref·Translate·Rx·Ry·Rz. Keep zero when no measured angular offset exists."
        ),
        "help_placement_apply": (
            "After Build CS and Machine are valid, apply the mount and six-DOF adjustment, then show Machine View."
        ),
        "help_placement_cancel": "Discard this Placement draft and restore the last applied placement.",
        "help_coordinates_valid": (
            "Requires valid Part, Machine, Model CS, Build CS, and Placement. Nozzle and Material are outside this gate."
        ),
        "help_setup_ready": (
            "Also requires a complete Nozzle, reviewed Material, and no Errors. A reference machine may be "
            "ready with warnings while executable NC remains restricted."
        ),
        "help_issues": (
            "Double-click or press Enter to open the related Setup node. Stable issue codes support persistence "
            "and automation."
        ),
    },
}

TUBE_CONTROL_TEXT = (
    ("title_label", "title"),
    ("subtitle_label", "subtitle"),
    ("back_button", "back"),
    ("open_button", "open"),
    ("update_source_button", "update_source"),
    ("save_button", "save"),
    ("create_operation_button", "create_operation"),
    ("model_view_button", "model_view"),
    ("machine_view_button", "machine_view"),
    ("empty_editor", "editor_empty"),
    ("part_help", "part_help"),
    ("part_confirm_button", "confirm"),
    ("machine_help", "resource_help"),
    ("machine_apply_button", "apply"),
    ("nozzle_help", "resource_help"),
    ("nozzle_interface_label", "interface"),
    ("nozzle_length_label", "length"),
    ("nozzle_collision", "collision_profile"),
    ("nozzle_apply_button", "apply"),
    ("material_help", "resource_help"),
    ("material_review", "review"),
    ("material_apply_button", "apply"),
    ("operation_help", "help_operation"),
    ("operation_apply_button", "apply"),
    ("operation_generate_button", "generate"),
    ("operation_cancel_button", "cancel_generation"),
    ("operation_preview_button", "preview_result"),
    ("operation_export_button", "export_result"),
    ("coordinate_apply_button", "apply"),
    ("coordinate_cancel_button", "cancel"),
    ("placement_help", "placement_help"),
    ("mount_label", "mount"),
    ("placement_apply_button", "apply"),
    ("placement_cancel_button", "cancel"),
    ("issue_title", "issues"),
)

TUBE_HELP_BINDINGS = (
    ("help_open", ("open_button",)),
    ("help_update_source", ("update_source_button",)),
    ("help_save", ("save_button",)),
    ("help_create_operation", ("create_operation_button", "operation_type_combo")),
    ("help_model_view", ("model_view_button",)),
    ("help_machine_view", ("machine_view_button",)),
    ("help_part_role", ("part_table",)),
    ("help_part_confirm", ("part_confirm_button",)),
    ("help_machine_profile", ("machine_combo", "machine_detail")),
    ("help_machine_apply", ("machine_apply_button",)),
    ("help_nozzle_profile", ("nozzle_combo",)),
    ("help_nozzle_interface", ("nozzle_interface_label", "nozzle_interface")),
    ("help_nozzle_length", ("nozzle_length_label", "nozzle_length")),
    ("help_nozzle_collision", ("nozzle_collision",)),
    ("help_nozzle_apply", ("nozzle_apply_button",)),
    ("help_material_profile", ("material_combo",)),
    ("help_material_detail", ("material_detail",)),
    ("help_material_review", ("material_review",)),
    ("help_material_apply", ("material_apply_button",)),
    (
        "help_operation",
        (
            "operation_help",
            "operation_apply_button",
            "operation_generate_button",
            "operation_cancel_button",
            "operation_preview_button",
            "operation_export_button",
        ),
    ),
    ("help_coordinate_apply", ("coordinate_apply_button",)),
    ("help_coordinate_cancel", ("coordinate_cancel_button",)),
    ("help_mount", ("mount_label", "mount_combo")),
    ("help_placement_apply", ("placement_apply_button",)),
    ("help_placement_cancel", ("placement_cancel_button",)),
    ("help_coordinates_valid", ("coordinate_status",)),
    ("help_setup_ready", ("setup_status",)),
    ("help_issues", ("issue_title", "issue_list")),
)

_ROLE_HELP = {
    "part": "help_role_part",
    "ignore": "help_role_ignore",
    "unassigned": "help_role_unassigned",
}
_CANDIDATE_HELP = {
    "numeric": "help_candidate_numeric",
    "pick_vertex": "help_candidate_vertex",
    "pick_face": "help_candidate_face",
    "pick_line": "help_candidate_line",
    "pick_axis_face": "help_candidate_axis_face",
    "pick_two_vertices": "help_candidate_two_vertices",
}


def apply_tube_help(page: Any) -> None:
    """Apply one localized help contract to visible, status, and assistive surfaces."""

    text = TUBE_TEXT[page.language]
    for key, control_names in TUBE_HELP_BINDINGS:
        for control_name in control_names:
            _set_help(getattr(page, control_name), text[key])
    page.nozzle_interface.setPlaceholderText(text["nozzle_interface_placeholder"])
    page.nozzle_length.setSpecialValueText(text["not_set"])
    _apply_role_help(page, text)
    _apply_coordinate_help(page, text)
    for key, spin in page.placement_spins.items():
        help_key = (
            "help_placement_rotation" if key.startswith("r") else "help_placement_translation"
        )
        description = text[help_key].format(axis=key[-1].upper())
        _set_help(page.placement_labels[key], description)
        _set_help(spin, description)


def _apply_role_help(page: Any, text: Mapping[str, str]) -> None:
    for combo in page._role_combos.values():
        _set_help(combo, text["help_part_role"])
        for index in range(combo.count()):
            key = _ROLE_HELP.get(str(combo.itemData(index)))
            if key is not None:
                combo.setItemData(index, text[key], Qt.ToolTipRole)


def _apply_coordinate_help(page: Any, text: Mapping[str, str]) -> None:
    basis = "model" if page._coordinate_node == MODEL_CS_NODE else "build"
    for component, controls in page.coordinate_inputs.items():
        combo, values, pick, title = controls
        reference_key = (
            "help_origin_reference" if component == "origin" else "help_direction_reference"
        )
        title_key = reference_key if component == "origin" else f"help_{component}_reference"
        numeric_key = (
            f"help_origin_numeric_{basis}"
            if component == "origin"
            else f"help_direction_numeric_{basis}"
        )
        _set_help(combo, text[reference_key])
        _set_help(title, text[title_key])
        for spin in values:
            _set_help(spin, text[numeric_key])
        _set_help(pick, text["help_coordinate_pick"])
        _set_help(getattr(page, f"{component}_confirm_button"), text["help_coordinate_confirm"])
        if component != "origin":
            _set_help(getattr(page, f"{component}_flip_button"), text["help_coordinate_flip"])
        for index in range(combo.count()):
            payload = combo.itemData(index)
            kind = str(payload.get("kind", "")) if isinstance(payload, Mapping) else ""
            key = _CANDIDATE_HELP.get(kind, "help_detected_candidate")
            combo.setItemData(index, text[key], Qt.ToolTipRole)


def _set_help(widget: Any, description: str) -> None:
    widget.setToolTip(description)
    widget.setStatusTip(description)
    widget.setAccessibleDescription(description)


_COORDINATE_SETUP_ORDER = (
    PART_NODE,
    MACHINE_NODE,
    MODEL_CS_NODE,
    BUILD_CS_NODE,
    PLACEMENT_NODE,
)
_EDITABLE_SETUP_NODES = frozenset((*_COORDINATE_SETUP_ORDER, NOZZLE_NODE, MATERIAL_NODE))


def setup_tree_node(
    selected: object,
    items: Mapping[str, object],
    report: SetupValidationReport,
) -> str:
    """Keep a valid selection or choose the next coordinate prerequisite."""

    if isinstance(selected, str) and selected in _EDITABLE_SETUP_NODES and selected in items:
        return selected
    return next(
        (node for node in _COORDINATE_SETUP_ORDER if report.state_for(node) is not NodeState.VALID),
        PART_NODE,
    )


def tube_language(language: str) -> str:
    if language not in TUBE_TEXT:
        raise ValueError(f"unsupported Tube UI language: {language}")
    return language


__all__ = [
    "TUBE_CONTROL_TEXT",
    "TUBE_HELP_BINDINGS",
    "TUBE_TEXT",
    "apply_tube_help",
    "setup_tree_node",
    "tube_language",
]
