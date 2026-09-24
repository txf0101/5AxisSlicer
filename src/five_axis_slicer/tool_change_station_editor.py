"""Machine-frame station editor for a Freeform material change."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
)

from .manufacturing.controller_profile import ToolChangeStation


_FIELDS = (
    ("clearance_z_mm", "安全退离 Z (mm)", "Clearance Z (mm)"),
    ("cutter_xyz_mm", "切刀位置 X,Y,Z (mm)", "Cutter X,Y,Z (mm)"),
    ("exchange_xyz_mm", "换料位置 X,Y,Z (mm)", "Exchange X,Y,Z (mm)"),
    ("purge_xyz_mm", "排料位置 X,Y,Z (mm)", "Purge X,Y,Z (mm)"),
    ("wipe_start_xyz_mm", "擦嘴起点 X,Y,Z (mm)", "Wipe start X,Y,Z (mm)"),
    ("wipe_end_xyz_mm", "擦嘴终点 X,Y,Z (mm)", "Wipe end X,Y,Z (mm)"),
    ("travel_feedrate_mm_min", "空移速度 (mm/min)", "Travel speed (mm/min)"),
    ("wipe_feedrate_mm_min", "擦嘴速度 (mm/min)", "Wipe speed (mm/min)"),
    ("wipe_passes", "擦嘴次数", "Wipe passes"),
    ("cutter_command", "切刀命令", "Cutter command"),
)
_XYZ_FIELDS = {
    "cutter_xyz_mm", "exchange_xyz_mm", "purge_xyz_mm",
    "wipe_start_xyz_mm", "wipe_end_xyz_mm",
}


class ToolChangeStationEditor(QDialog):
    """Validate station coordinates in the same contract used by NC generation."""

    def __init__(self, payload: dict | None = None, *, language: str = "zh", parent=None):
        super().__init__(parent)
        self.result_payload: dict | None = None
        zh = language == "zh"
        self._zh = zh
        self.setWindowTitle("换料站" if zh else "Tool-change station")
        layout = QVBoxLayout(self)
        note = QLabel(
            "输入喷嘴尖端的机床坐标。示例位置和切刀宏须按实际设备标定。"
            if zh else "Enter machine-frame nozzle-tip coordinates. Calibrate station positions and cutter command for your equipment."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.edits: dict[str, QLineEdit] = {}
        values = payload or {}
        for name, label_zh, label_en in _FIELDS:
            value = values.get(name, "")
            if isinstance(value, (tuple, list)):
                value = ", ".join(str(part) for part in value)
            edit = QLineEdit(str(value))
            if name in _XYZ_FIELDS:
                edit.setPlaceholderText("X, Y, Z")
            self.edits[name] = edit
            form.addRow(label_zh if zh else label_en, edit)
        layout.addLayout(form)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def build_payload(self) -> dict:
        values: dict[str, object] = {}
        for name, _, _ in _FIELDS:
            text = self.edits[name].text().strip()
            if name in _XYZ_FIELDS:
                coords = tuple(float(part.strip()) for part in text.split(","))
                if len(coords) != 3:
                    raise ValueError(f"{name} requires X, Y, Z")
                values[name] = coords
            elif name == "wipe_passes":
                values[name] = int(text)
            elif name == "cutter_command":
                values[name] = text
            else:
                values[name] = float(text)
        return ToolChangeStation.from_json(values).to_json()

    def _submit(self) -> None:
        try:
            self.result_payload = self.build_payload()
        except (TypeError, ValueError) as exc:
            message = str(exc)
            if self._zh:
                if "requires X, Y, Z" in message:
                    message = "每个站位需要填写 X、Y、Z 三个坐标。"
                elif "must be below clearance_z_mm" in message:
                    message = "切刀、换料、排料及擦嘴站位的 Z 必须低于安全退离 Z。"
                elif "wipe_passes" in message:
                    message = "擦嘴次数须为 1–20 的整数。"
                elif "cutter_command" in message:
                    message = "切刀命令须为单条 G-code 指令。"
                else:
                    message = "请填写有效数值，并核对站位、速度和安全退离高度。"
            self.error_label.setText(message)
            return
        self.accept()
