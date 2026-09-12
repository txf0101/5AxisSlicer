"""Bilingual Planar generation outcomes and inspectable issue explanations."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re
from typing import Any

_MESSAGES = {
    "MACHINE_REFERENCE_ONLY": (
        "当前为内置参考机型，仅用于离线检查。",
        "The selected built-in reference machine is for offline checks only.",
    ),
    "planar.region_preview_only": (
        "当前结果是区域截面预览，尚未生成沉积路径。",
        "This result previews layer sections; it does not contain deposition paths.",
    ),
    "xyzac.axis_limit": (
        "所需机器轴位置超出配置行程，无法求解有效姿态。",
        "The required machine-axis position exceeds its configured travel limit.",
    ),
    "planar.deposition_outside_region": (
        "沉积中心线超出层截面边界。",
        "A deposition centreline leaves the layer boundary.",
    ),
    "planar.bead_envelope_outside_region": (
        "计入道宽后，沉积包络超出层截面边界。",
        "The deposited bead extends beyond the layer boundary when its width is included.",
    ),
    "planar.material_volume_mismatch": (
        "指令材料体积与路径几何计算不一致。",
        "Commanded material volume disagrees with the path geometry.",
    ),
    "planar.material_exceeds_solid_volume": (
        "指令材料体积超过目标实体体积；请检查道宽、间距及重复覆盖。",
        "Commanded material exceeds the target solid volume; check bead width, spacing and overlapping passes.",
    ),
    "planar.coverage_residual_high": (
        "层截面仍有较大未覆盖区域，请检查填充间距和道宽。",
        "A substantial part of the layer remains uncovered; check line spacing and bead width.",
    ),
    "planar.gcode_readback_failed": (
        "输出 G-code 与生成路径或事件不一致，回读检查未通过。",
        "G-code does not match the generated path or events; readback failed.",
    ),
    "planar.thin_wall_width_reduced": (
        "目标壁厚低于当前道宽适用范围；已采用受限道数，请核对实际道宽。",
        "The requested wall is thinner than this bead setting; a limited pass count is used. Check the actual bead width.",
    ),
    "planar.support_travel_intersects_target_cad": (
        "支撑空移穿过目标零件；需要调整连接路径或打印次序。",
        "Support travel intersects the target part; revise the connecting moves or print order.",
    ),
    "planar.support_deposition_intersects_target_cad": (
        "支撑沉积路径进入目标零件；请检查支撑间隙。",
        "Support deposition enters the target part; check support clearance.",
    ),
    "planar.support_joint_schedule_unverified": (
        "当前为独立支撑路径，尚未验证零件与支撑的联合逐层次序和完整喷嘴扫掠。",
        "This is an independent support path; combined part/support layer order and full nozzle sweep remain unverified.",
    ),
    "planar.support_cad_unavailable": (
        "缺少目标零件实体，无法检查支撑路径相交。",
        "The target solid is unavailable, so support intersections cannot be checked.",
    ),
    "planar.support_cad_check_failed": (
        "目标实体相交检查失败，无法确认支撑运动。",
        "The target-solid intersection check failed; support motion could not be qualified.",
    ),
    "planar.support_cad_frame_unsupported": (
        "支撑路径与目标实体的坐标关系不受当前检查器支持。",
        "The support-to-solid coordinate relationship is unsupported by this check.",
    ),
    "planar.support_unreachable_from_buildplate": (
        "部分支撑区域无法从打印平台到达。",
        "Some support regions cannot be reached from the build plate.",
    ),
    "planar.support_region_too_narrow": (
        "支撑区域小于可容纳的道宽，无法生成有效沉积段。",
        "The support region is too narrow for a printable bead.",
    ),
    "planar.support_buildplate_first_layer_required": (
        "支撑首层必须对应打印平台上的首个沉积层。",
        "Support must start at the first deposition layer on the build plate.",
    ),
    "planar.support_not_required": (
        "所选层未检测到需要支撑的区域。",
        "No support is required for the selected layers.",
    ),
    "planar.spiral_layers_insufficient": (
        "螺旋至少需要两个相邻层。",
        "Spiral requires at least two adjacent layers.",
    ),
    "planar.spiral_bead_outside_cad": (
        "螺旋在层间过渡时，道宽包络超出真实零件实体。",
        "The spiral bead extends outside the actual solid between layers.",
    ),
    "planar.spiral_interpolation_outside": (
        "螺旋层间连接超出对应截面，无法连续生成。",
        "The spiral connection leaves the corresponding sections between layers.",
    ),
    "planar.spiral_cad_unavailable": (
        "缺少真实零件实体，无法核对螺旋层间路径。",
        "The actual solid is unavailable for checking the spiral between layers.",
    ),
    "planar.spiral_cad_sampling_limit": (
        "螺旋实体检查超过采样上限，当前结果未完成验证。",
        "The spiral solid check reached its sampling limit; verification is incomplete.",
    ),
    "planar.spiral_cad_sampled": (
        "螺旋已通过离散实体采样检查；该检查尚未证明完整连续扫掠安全。",
        "The spiral passed discrete solid sampling; this does not qualify the full continuous sweep.",
    ),
    "planar.spiral_volume_inconsistent": (
        "螺旋材料体积与路径几何不一致。",
        "Spiral material volume disagrees with its path geometry.",
    ),
    "planar.spiral_topology_changed": (
        "相邻层的轮廓对应关系改变，无法直接连接螺旋。",
        "Contour correspondence changes between layers, preventing a direct spiral connection.",
    ),
    "planar.spiral_inset_topology_changed": (
        "按半道宽内缩后，轮廓拓扑发生变化。",
        "The contour topology changes after the half-bead-width inset.",
    ),
    "planar.spiral_multiple_regions": (
        "螺旋要求每层只有一个连通区域。",
        "Spiral requires one connected region per layer.",
    ),
    "planar.spiral_holes_unsupported": (
        "当前螺旋算法不支持含孔截面。",
        "The current spiral algorithm does not support sections with holes.",
    ),
    "xyzac.rotary_singularity": (
        "路径经过参考机型的回转奇异姿态，请核对轴姿态与连续性。",
        "The path reaches a rotary singularity of the reference machine; review axis orientation and continuity.",
    ),
    "xyzac.acceleration_limit_exceeded": (
        "机器轴加速度超出配置限值。",
        "Machine-axis acceleration exceeds the configured limit.",
    ),
    "xyzac.velocity_limit_exceeded": (
        "机器轴速度超出配置限值。",
        "Machine-axis speed exceeds the configured limit.",
    ),
    "MATERIAL_REVIEW_REQUIRED": (
        "材料参数尚未完成来源审阅。",
        "Material parameters have not been reviewed.",
    ),
    "material.review_required": (
        "材料参数尚未完成来源审阅。",
        "Material parameters have not been reviewed.",
    ),
    "SETUP_MATERIAL_MISSING": ("尚未选择材料。", "Select a material."),
    "SETUP_NOZZLE_MISSING": ("尚未选择喷嘴。", "Select a nozzle."),
    "SETUP_MACHINE_MISSING": ("尚未选择机型。", "Select a machine."),
    "SETUP_PART_MISSING": ("尚未指定制造零件。", "Assign the manufacturing part."),
}
_CODE = re.compile(r"(?:planar|xyzac|material)\.[a-z_]+")
_SEVERITIES = {"error": ("错误", "Error"), "warning": ("警告", "Warning"), "info": ("提示", "Info")}


def diagnostic_text(code: str, language: str) -> str:
    message = _MESSAGES.get(code)
    return code if message is None else f"{code}: {message[language == 'en']}"


def generation_error_text(message: str, language: str) -> str:
    match = _CODE.search(message)
    return diagnostic_text(match[0], language) if match else message


def product_status_text(
    operation_type: str,
    reason: str | None,
    product: Any,
    result: Any,
    translate: Callable[[str], str],
) -> str:
    status = None if product is None else product.status
    if status == "error":
        return translate("error")
    if status == "stale":
        return translate("stale")
    if status in {"ready", "warning"} and result is not None:
        if operation_type != "planar_region" and not result.exportable:
            return translate("error")
        if status == "warning":
            return translate(
                "preview_warning" if operation_type == "planar_region" else "generated_warning"
            )
        return translate("preview" if operation_type == "planar_region" else "generated_path")
    if reason is not None:
        return reason
    return translate("ready" if operation_type == "planar_region" else "ready_path")


def product_issues_text(
    setup_issues: Iterable[Any], product: Any, language: str, generation_error: str | None = None
) -> str:
    issues = [issue.to_json() for issue in setup_issues]
    payload = {} if product is None else product.result_payload or {}
    validation = payload.get("validation", {})
    if isinstance(validation, Mapping):
        issues.extend(issue for issue in validation.get("issues", ()) if isinstance(issue, Mapping))
    manifest = payload.get("manifest", {})
    if isinstance(manifest, Mapping):
        known = {issue.get("code") for issue in issues}
        issues.extend(
            {"code": code, "severity": getattr(product, "status", "info")}
            for code in manifest.get("issues", ())
            if isinstance(code, str) and code not in known
        )
    lines = [_issue_line(issue, language) for issue in issues]
    if payload.get("error"):
        lines.append(generation_error_text(str(payload["error"]), language))
    if generation_error:
        lines.append(generation_error_text(generation_error, language))
    return "\n".join(dict.fromkeys(lines))


def _issue_line(issue: Mapping[str, Any], language: str) -> str:
    code = str(issue.get("code", ""))
    severity = _SEVERITIES.get(str(issue.get("severity")), _SEVERITIES["info"])[language == "en"]
    return f"{severity} — {diagnostic_text(code, language)}{_context_suffix(issue, language)}"


def _context_suffix(issue: Mapping[str, Any], language: str) -> str:
    context = issue.get("context", {})
    if not isinstance(context, Mapping):
        return ""
    details = []
    for key, labels in (
        ("maximum_mm", ("最大越界", "Maximum outside")),
        ("tolerance_mm", ("容差", "Tolerance")),
        ("target_mm3", ("目标体积", "Target volume")),
        ("commanded_mm3", ("指令体积", "Commanded volume")),
        ("difference_mm3", ("体积差", "Volume difference")),
        ("intersection_count", ("相交段数", "Intersections")),
    ):
        value = context.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            unit = " mm³" if key.endswith("mm3") else " mm" if key.endswith("mm") else ""
            details.append(f"{labels[language == 'en']} {value:.6g}{unit}")
    identifier = issue.get("object_id") or context.get("point_id") or context.get("body_id")
    if identifier:
        details.append(str(identifier))
    return " (" + "; ".join(details) + ")" if details else ""
