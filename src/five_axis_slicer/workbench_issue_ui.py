"""Setup and operation diagnostic presentation for the workbench pages."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QLabel, QListWidget, QTreeWidgetItem

from .manufacturing.setup import (
    OPERATION_NODE,
    IssueSeverity,
    ManufacturingSetup,
    NodeState,
    SetupValidationReport,
)
from .tube_ui_text import TUBE_ISSUE_LABELS, TUBE_TEXT, nozzle_readiness_text


def refresh_issue_list(
    issue_list: QListWidget, setup_issues: Any, result: Any, language: str, empty_text: str
) -> None:
    issue_list.clear()
    issues = list(setup_issues)
    if result is not None:
        issues.extend(result.validation.issues)
    issues.sort(
        key=lambda issue: (str(getattr(issue.severity, "value", issue.severity)).lower() != "error")
    )
    for issue in issues:
        severity = getattr(issue.severity, "value", issue.severity).upper()
        label = TUBE_ISSUE_LABELS[language].get(issue.code)
        item_text = (
            f"[{severity}] {label}" if label else f"[{severity}] {issue.code} · {issue.object_id}"
        )
        issue_list.addItem(item_text)
        item = issue_list.item(issue_list.count() - 1)
        item.setData(Qt.UserRole, issue.to_json())
        item.setToolTip(
            f"{issue.code} · {issue.object_id}\n"
            + json.dumps(issue.to_json().get("context", {}), ensure_ascii=False, indent=2)
        )
    if not issues:
        issue_list.addItem(empty_text)


def jump_to_issue(issue_list: QListWidget, viewer: Any, status_label: QLabel) -> None:
    item = issue_list.currentItem()
    payload = None if item is None else item.data(Qt.UserRole)
    if isinstance(payload, Mapping):
        object_id = str(payload.get("object_id", ""))
        if object_id.startswith("edge-"):
            viewer.set_selection(edge_ids=[object_id])
        elif object_id.startswith("face-"):
            viewer.set_selection(face_ids=[object_id])
        status_label.setText(f"{payload.get('code', '')} · {object_id}")


def command_error_text(message: str, language: str) -> str:
    """Explain recoverable command failures without changing the kernel contract."""
    if message == "unapplied Setup drafts are active":
        guidance = {
            "zh": "制造设置有未应用草稿：返回标为“草稿”的坐标或装夹节点，应用或取消草稿后，再重试当前操作。",
            "en": "Manufacturing Setup has unapplied drafts: return to the coordinate or Placement node marked Draft, Apply or Cancel the draft, then retry this action.",
        }[language]
        return f"{guidance}\n{message}"
    return message


def operation_status_text(status: str, error: str | None, language: str) -> str:
    if language == "zh":
        labels = {
            "draft": "草稿",
            "ready": "就绪",
            "warning": "有警告",
            "error": "错误",
            "stale": "待更新",
            "invalid": "无效",
        }
        message = f"状态：{labels.get(status, status)}"
    else:
        message = f"Status: {status}"
    if error and error.startswith("curve.chain_disconnected"):
        guidance = (
            "边链不连续：检查边的行进顺序和对应反向标志（0/1），使前一条边的终点连接下一条边的起点。"
            if language == "zh"
            else "Edge chain is disconnected: check traversal order and reverse flags (0/1) so each edge ends at the next edge's start."
        )
        error = f"{guidance}\n{error}"
    if error and error.startswith("curve.normal_ambiguous:"):
        error = (
            "法向不明确：请选择一个相邻面并填写法向邻面 ID，或改用用户指定方向。"
            if language == "zh"
            else "Normal is ambiguous: select an adjacent face and enter its ID, or use a specified direction."
        )
    if error and error.startswith("xyzac.orientation_unreachable"):
        guidance = (
            "当前机床无法达到该喷嘴朝向：核对承载面与生长方向、喷嘴轴向、模型放置和 A/C 轴范围，再应用并重新生成。"
            if language == "zh"
            else "The current machine cannot reach this nozzle orientation: check the supporting face and growth direction, nozzle axis, model placement and A/C axis ranges; apply and regenerate."
        )
        error = f"{guidance}\n{error}"
    exact_guidance: dict[str | None, str] = {
        "Freeform Generate requires a valid applied Setup": (
            "制造设置尚未就绪：按下方问题列表补齐零件、喷嘴、材料、坐标和装夹，确认并应用后重新生成。"
            if language == "zh"
            else "Manufacturing Setup is not ready: resolve the Part, nozzle, material, coordinates and placement issues below, confirm and Apply, then generate again."
        ),
        "bodies must be a non-empty array of objects": {
            "zh": "实体角色格式不完整：请在 bodies 列表内填写至少一个实体的角色对象，或显示模型后从 Viewer 已选几何建立候选，再重新应用。",
            "en": "Solid role format is incomplete: put at least one body role object in the bodies list, or show the model and build candidates from selected Viewer geometry, then Apply again.",
        }[language],
        "opposite_face_id is required": (
            "缺少对侧面：在实体填充几何中，为该实体填写与承载面相对的面 ID（opposite_face_id），然后重新应用。"
            if language == "zh"
            else "Opposite face is missing: in Solid-fill selection JSON, set opposite_face_id to the face opposite the supporting face on this body, then Apply again."
        ),
    }
    exact_message = exact_guidance.get(error)
    if exact_message:
        error = f"{exact_message}\n{error}"
    return error or message


def refresh_setup_feedback(
    issue_list: QListWidget,
    coordinate_status: QLabel,
    setup_status: QLabel,
    report: SetupValidationReport,
    setup: ManufacturingSetup,
    language: str,
) -> None:
    text = TUBE_TEXT[language]
    coordinate_status.setText(
        f"{text['coordinates_valid']}: {'✓' if report.coordinates_valid else '—'}"
    )
    ready_label = text["setup_ready"]
    if report.setup_ready and report.has_warnings:
        ready_value = text["ready_warning"]
    else:
        ready_value = "✓" if report.setup_ready else "—"
    setup_status.setText(f"{ready_label}: {ready_value}")
    issue_list.clear()
    for issue in report.issues:
        marker = {
            IssueSeverity.ERROR: "E",
            IssueSeverity.WARNING: "W",
            IssueSeverity.INFO: "I",
        }[issue.severity]
        label = TUBE_ISSUE_LABELS[language].get(issue.code, issue.code)
        if issue.code == "SETUP_NOZZLE_INVALID" and setup.nozzle is not None:
            try:
                profile = setup.nozzle.as_nozzle_profile()
            except (AttributeError, KeyError, TypeError, ValueError):
                label = (
                    "喷嘴配置无法读取，请重新选择配置"
                    if language == "zh"
                    else "Cannot read nozzle profile; select another profile"
                )
            else:
                if profile.readiness_blockers:
                    label = nozzle_readiness_text(profile, language)
        issue_list.addItem(f"[{marker}] {label}")
        item = issue_list.item(issue_list.count() - 1)
        item.setData(Qt.UserRole, issue.to_json())
        item.setToolTip(f"{issue.code} · {issue.object_id or setup.setup_id}")
    if not report.issues:
        issue_list.addItem(text["no_issues"])


def refresh_setup_tree(
    items: Mapping[str, QTreeWidgetItem], report: SetupValidationReport, language: str
) -> None:
    text = TUBE_TEXT[language]
    for node, item in items.items():
        if node not in report.node_states:
            continue
        state = report.node_states[node]
        base = text["operations"] if node == OPERATION_NODE else text[node]
        item.setText(0, f"{base}  [{text['status_' + state.value]}]")
        item.setForeground(0, _state_color(state))


def _state_color(state: NodeState) -> QColor:
    return {
        NodeState.MISSING: QColor("#C27825"),
        NodeState.DRAFT: QColor("#8B5CF6"),
        NodeState.VALID: QColor("#20815D"),
        NodeState.DIRTY: QColor("#B7791F"),
        NodeState.INVALID: QColor("#C43D4E"),
    }[state]


def rotary_status_text(
    product: Any, reason: str | None, error: str | None, language: str, text: Mapping[str, str]
) -> str:
    if error:
        if error.startswith("rotary.surface_reference_invalid"):
            guidance = (
                "所选表面不适用于回转加工。请选择与回转轴同轴的圆柱面或圆锥面，"
                "采用已选表面后重新应用几何与参数。"
                if language == "zh"
                else "Select a cylindrical or conical surface coaxial with the rotary axis, "
                "use the selected surface, then apply geometry and parameters again."
            )
            return f"{text['status']}: {guidance}\n{error}"
        return f"{text['status']}: {error}"
    if product is not None:
        return f"{text['status']}: {product.status.upper()} · {text[product.status]}"
    return f"{text['status']}: {reason or text['draft']}"


def refresh_rotary_issues(
    issue_list: QListWidget, setup_issues: Any, result: Any, state: Any, empty_text: str
) -> None:
    issue_list.clear()
    issues: list[Any] = list(setup_issues)
    if result is not None:
        issues.extend(result.validation.issues)
    failure = (
        None
        if state is None or not isinstance(state.result_payload, Mapping)
        else state.result_payload.get("issue")
    )
    if isinstance(failure, Mapping):
        issues.append(failure)
    seen: set[tuple[str, str]] = set()
    for index, issue in enumerate(issues, 1):
        payload = issue if isinstance(issue, Mapping) else issue.to_json()
        code = str(payload.get("code", ""))
        object_id = str(payload.get("object_id", ""))
        key = (code, object_id)
        if key in seen:
            continue
        seen.add(key)
        severity = str(payload.get("severity", "error")).upper()
        text = f"{severity[:1]}{index}: {code.rsplit('.', 1)[-1]}"
        issue_list.addItem(text)
        item = issue_list.item(issue_list.count() - 1)
        item.setData(Qt.UserRole, dict(payload))
        item.setToolTip(f"[{severity}] {code} · {object_id}")
    if not seen:
        issue_list.addItem(empty_text)


def jump_to_rotary_issue(page: Any) -> None:
    item = page.issue_list.currentItem()
    payload = None if item is None else item.data(Qt.UserRole)
    if not isinstance(payload, Mapping):
        return
    object_id = str(payload.get("object_id", ""))
    model = page.controller.cad_model
    if model is not None and object_id in model.edge_map:
        page.viewer.set_selection(edge_ids=[object_id])
    elif model is not None and object_id in model.face_map:
        page.viewer.set_selection(face_ids=[object_id])
    else:
        result = page._selected_result()
        if result is not None:
            for index, point in enumerate(result.preview_toolpath.points):
                if point.point_id == object_id and hasattr(page.viewer, "set_preview_progress"):
                    page.viewer.set_preview_progress(max(0, index - 1))
                    break
    page.status_label.setText(
        f"{page.status_label.text()}\n{payload.get('code', '')} · {object_id}"
    )
