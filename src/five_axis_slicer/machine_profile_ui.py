"""Machine catalog editing and portable JSON files for the shared setup page."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .manufacturing.machine import MachineProfile
from .manufacturing.own_printer import OWN_AC_ID, own_ac_document


def display_name(profile: MachineProfile, language: str) -> str:
    if profile.profile_id == OWN_AC_ID:
        return "自有 AC 五轴打印机" if language == "zh" else "Own AC FDM"
    return profile.name


def read_machine(text: str) -> MachineProfile:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Machine configuration must be a JSON object")
    if "profile" in payload:
        if payload.get("resource_type") != "machine" or payload.get("schema_version") != 1:
            raise ValueError("Expected a version 1 machine configuration")
        payload = payload["profile"]
    if (
        not isinstance(payload, dict)
        or not {"joints", "mount_datums", "build_surfaces"} <= payload.keys()
    ):
        raise ValueError("Expected 5AxisSclicer MachineProfile JSON")
    return MachineProfile.from_json(payload)


def save_copy(page: Any, profile: MachineProfile, name: str) -> MachineProfile:
    if not name.strip():
        raise ValueError("Machine name is required")
    copied = replace(profile, profile_id=f"user.machine.{uuid4()}", name=name.strip())
    page.resource_library.save(copied)
    page.reload_resource_library()
    page.machine_combo.setCurrentIndex(page.machine_combo.findData(copied.profile_id))
    return copied


def _text(page: Any, zh: str, en: str) -> str:
    return zh if page.language == "zh" else en


def remap_rotary_axis_words(
    profile: MachineProfile,
    axis_words: dict[str, str],
) -> MachineProfile:
    """Return a validated profile with only rotary controller words changed.

    Logical joint IDs, directions, motion sides, transforms, limits and all
    other post settings remain unchanged.  Profiles with unmapped rotary
    joints remain invalid for this customer-facing output editor.
    """

    rotary_ids = tuple(joint.joint_id for joint in profile.joints if joint.joint_type == "rotary")
    if not rotary_ids:
        raise ValueError("Machine profile has no rotary joints")
    normalized = {str(key): str(value).strip().upper() for key, value in axis_words.items()}
    if set(normalized) != set(rotary_ids):
        raise ValueError("Axis-word mapping must contain every rotary joint exactly once")

    return profile.with_rotary_axis_words(normalized)


class RotaryAxisWordDialog(QDialog):
    """Small customer-facing editor for rotary G-code address words."""

    def __init__(self, page: Any, profile: MachineProfile) -> None:
        super().__init__(page)
        self.profile = profile
        self.language = "zh" if page.language == "zh" else "en"
        self.axis_word_edits: dict[str, QLineEdit] = {}
        self.result_profile: MachineProfile | None = None
        self.setWindowTitle(
            "旋转轴 G-code 输出字" if self.language == "zh" else "Rotary G-code axis words"
        )
        self.resize(680, 360)
        layout = QVBoxLayout(self)
        self.help_label = QLabel(_axis_word_help(self.language))
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)
        self._add_axis_word_grid(layout, profile)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        layout.addWidget(self._dialog_buttons())

    def _add_axis_word_grid(self, layout: QVBoxLayout, profile: MachineProfile) -> None:
        grid = QGridLayout()
        headings = (
            ("内部轴", "Internal joint"),
            ("G-code 输出字", "G-code word"),
            ("轴方向（只读）", "Axis direction (read-only)"),
            ("运动侧（只读）", "Motion side (read-only)"),
        )
        for column, (zh, en) in enumerate(headings):
            grid.addWidget(QLabel(zh if self.language == "zh" else en), 0, column)

        rotary_joints = tuple(joint for joint in profile.joints if joint.joint_type == "rotary")
        if not rotary_joints:
            raise ValueError("Machine profile has no rotary joints")
        for row, joint in enumerate(rotary_joints, start=1):
            current_word = joint.post_axis_map.word if joint.post_axis_map is not None else ""
            word_edit = QLineEdit(current_word)
            word_edit.setMaxLength(1)
            word_edit.setObjectName(f"rotaryAxisWord_{joint.joint_id}")
            word_edit.setToolTip(
                "仅修改输出地址，不重命名内部关节。"
                if self.language == "zh"
                else "Changes the output address only; the internal joint is not renamed."
            )
            self.axis_word_edits[joint.joint_id] = word_edit
            direction = ", ".join(f"{value:g}" for value in joint.axis_direction)
            motion_side = {
                "tool": ("刀具侧", "Tool side"),
                "workpiece": ("工件侧", "Workpiece side"),
            }.get(joint.motion_side, (joint.motion_side, joint.motion_side))
            grid.addWidget(QLabel(joint.joint_id), row, 0)
            grid.addWidget(word_edit, row, 1)
            grid.addWidget(QLabel(f"({direction})"), row, 2)
            grid.addWidget(
                QLabel(motion_side[0] if self.language == "zh" else motion_side[1]), row, 3
            )
        layout.addLayout(grid)

    def _dialog_buttons(self) -> QDialogButtonBox:
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存" if self.language == "zh" else "Save")
        buttons.button(QDialogButtonBox.Cancel).setText(
            "取消" if self.language == "zh" else "Cancel"
        )
        buttons.accepted.connect(self.accept_mapping)
        buttons.rejected.connect(self.reject)
        return buttons

    def mapped_profile(self) -> MachineProfile:
        return remap_rotary_axis_words(
            self.profile,
            {joint_id: editor.text() for joint_id, editor in self.axis_word_edits.items()},
        )

    def accept_mapping(self) -> None:
        try:
            self.result_profile = self.mapped_profile()
        except (TypeError, ValueError) as exc:
            self.error_label.setText(str(exc))
            return
        self.accept()


def _axis_word_help(language: str) -> str:
    if language == "zh":
        return (
            "这里只修改控制器 G-code 地址字；内部 A/B/C 关节、轴方向、运动侧和运动学保持不变。"
            "每个输出字必须是一个英文字母。"
        )
    return (
        "This changes only controller G-code address words. Internal A/B/C joints, axis "
        "directions, motion sides, and kinematics remain unchanged. Each output word must "
        "be one Latin letter."
    )


def edit_rotary_axis_words(page: Any, profile: MachineProfile) -> MachineProfile | None:
    dialog = RotaryAxisWordDialog(page, profile)
    return dialog.result_profile if dialog.exec_() == QDialog.Accepted else None


def build_editor(page: Any) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    page.machine_help = QLabel()
    page.machine_help.setWordWrap(True)
    from PyQt5.QtWidgets import QComboBox

    page.machine_combo = QComboBox()
    page.machine_combo.setMinimumContentsLength(15)
    page.machine_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    for key, profile in page._machine_profiles.items():
        page.machine_combo.addItem(page._resource_choice_label("machine", key, profile), key)
    page.machine_detail = QLabel()
    page.machine_detail.setWordWrap(True)
    page.machine_combo.currentIndexChanged.connect(page._update_machine_detail)
    page.machine_apply_button = QPushButton()
    page.machine_apply_button.setObjectName("primaryButton")
    page.machine_apply_button.clicked.connect(page._apply_machine)
    for control in (
        page.machine_help,
        page.machine_combo,
        page.machine_detail,
        page.machine_apply_button,
    ):
        layout.addWidget(control)
    page.machine_file_buttons = []
    for action in ("axis_words", "edit", "import", "export"):
        button = QPushButton()
        button.clicked.connect(lambda checked=False, mode=action: file_action(page, mode))
        page.machine_file_buttons.append(button)
        layout.addWidget(button)
    layout.addStretch(1)
    return widget


def update_detail(page: Any) -> None:
    for button, zh, en in zip(
        page.machine_file_buttons,
        (
            "旋转轴 G-code 输出字…",
            "高级 JSON 自定义并另存…",
            "导入机型配置…",
            "导出机型配置…",
        ),
        (
            "Rotary G-code axis words…",
            "Advanced JSON: customize and save copy…",
            "Import machine…",
            "Export machine…",
        ),
    ):
        button.setText(_text(page, zh, en))
    profile = page._machine_profiles.get(str(page.machine_combo.currentData()))
    if profile is None:
        page.machine_detail.clear()
        return
    axes = ", ".join(joint.joint_id for joint in profile.joints)
    rotary_mapping = ", ".join(
        f"{joint.joint_id}→{joint.post_axis_map.word}"
        for joint in profile.joints
        if joint.joint_type == "rotary" and joint.post_axis_map is not None
    )
    status = (
        _text(page, "参考配置，实机标定待核验", "Reference configuration; calibration unverified")
        if profile.reference_only
        else _text(page, "用户机型配置", "User machine configuration")
    )
    detail = f"{display_name(profile, page.language)}\n{axes}\n{status}"
    if rotary_mapping:
        detail += _text(
            page,
            f"\n旋转轴输出：{rotary_mapping}",
            f"\nRotary output: {rotary_mapping}",
        )
    if profile.profile_id == OWN_AC_ID:
        detail += _text(
            page,
            "\n默认机型 · 台面180 mm，建议160 mm，试验150 mm。\nA ±180°；C ±360°。XYZ行程、轴速度及回转中心待标定。",
            "\nDefault · table 180 mm, recommended 160 mm, tested 150 mm.\nA ±180°; C ±360°. XYZ travel, axis speeds and rotary centers need calibration.",
        )
    page.machine_detail.setText(detail)
    page.machine_detail.setToolTip(profile.source_uri)


def edit_profile(page: Any, profile: MachineProfile) -> MachineProfile | None:
    dialog = QDialog(page)
    dialog.setWindowTitle(_text(page, "自定义机型配置", "Customize machine profile"))
    dialog.resize(720, 620)
    layout = QVBoxLayout(dialog)
    hint = QLabel(
        _text(
            page,
            "修改名称和机型参数后另存到用户库。长度 mm，内部角度 rad；未知限值保留 null。",
            "Save a named copy to the user library. Lengths: mm; internal angles: rad. Keep unknown limits null.",
        )
    )
    hint.setWordWrap(True)
    layout.addWidget(hint)
    editor = QPlainTextEdit(json.dumps(profile.to_json(), ensure_ascii=False, indent=2))
    layout.addWidget(editor)
    error = QLabel()
    error.setWordWrap(True)
    layout.addWidget(error)
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    layout.addWidget(buttons)
    result: list[MachineProfile] = []

    def accept() -> None:
        try:
            result.append(read_machine(editor.toPlainText()))
            dialog.accept()
        except (ValueError, TypeError, KeyError) as exc:
            error.setText(str(exc))

    buttons.accepted.connect(accept)
    buttons.rejected.connect(dialog.reject)
    return result[0] if dialog.exec_() == QDialog.Accepted else None


def file_action(page: Any, mode: str) -> None:
    try:
        selected = page._machine_profiles[str(page.machine_combo.currentData())]
        if mode == "export":
            path, _ = QFileDialog.getSaveFileName(
                page, "Export machine", "machine.json", "JSON (*.json)"
            )
            if path:
                payload = (
                    own_ac_document()
                    if selected.profile_id == OWN_AC_ID
                    else {
                        "schema_version": 1,
                        "resource_type": "machine",
                        "profile": selected.to_json(),
                    }
                )
                Path(path).write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            return
        if mode == "import":
            path, _ = QFileDialog.getOpenFileName(page, "Import machine", "", "JSON (*.json)")
            if not path:
                return
            selected = read_machine(Path(path).read_text(encoding="utf-8-sig"))
        elif mode == "axis_words":
            edited = edit_rotary_axis_words(page, selected)
            if edited is None:
                return
            selected = edited
        else:
            edited = edit_profile(page, selected)
            if edited is None:
                return
            selected = edited
        name, accepted = QInputDialog.getText(
            page,
            _text(page, "另存机型", "Save machine copy"),
            _text(page, "型号名称", "Model name"),
            text=selected.name,
        )
        if accepted:
            save_copy(page, selected, name)
            if mode == "axis_words":
                page._apply_machine()
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        page._report_error(exc)
