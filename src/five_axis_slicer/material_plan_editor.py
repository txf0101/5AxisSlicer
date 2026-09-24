"""Editable material-channel and deposition-region mapping for Freeform."""

from __future__ import annotations

from copy import deepcopy

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from .manufacturing.freeform_solid_parameters import (
    RadialSolidGeometrySelection,
    SphericalSolidGeometrySelection,
    SurfaceSolidGeometrySelection,
)
from .manufacturing.material_plan import MaterialPlan


def stage_candidates_for_operation(operation, *, language: str = "zh", toolpath=None):
    """Prefer stable body regions; use operation stages only where they stay grouped."""

    zh = language == "zh"
    geometry = None if operation is None else operation.solid_geometry
    actual_regions = set()
    if toolpath is not None:
        for point in toolpath.points:
            if point.point_type == "deposition":
                actual_regions.add(point.region_id)
            if len(actual_regions) > 128:
                break
    if isinstance(geometry, SphericalSolidGeometrySelection):
        features = [
            ((f"球面实体 {index}" if zh else f"Spherical solid {index}"), item.object_id)
            for index, item in enumerate(geometry.bodies, 1)
        ]
    elif isinstance(geometry, SurfaceSolidGeometrySelection):
        features = [
            ((f"曲面实体 {index}" if zh else f"Surface solid {index}"), item.body.object_id)
            for index, item in enumerate(geometry.bodies, 1)
        ]
    elif isinstance(geometry, RadialSolidGeometrySelection):
        features = [
            ((f"叶片 {index}" if zh else f"Blade {index}"), item.body.object_id)
            for index, item in enumerate(geometry.blades, 1)
        ]
    else:
        features = []
    if features:
        candidates = []
        if geometry is not None and geometry.substrate_body is not None:
            # The planar substrate currently uses planar region IDs, not the CAD body ID.
            if toolpath is not None:
                base_regions = actual_regions - {body_id for _, body_id in features}
                if len(base_regions) == 1:
                    candidates.append(("底座" if zh else "Substrate", "", next(iter(base_regions))))
                else:
                    candidates.append(("底座" if zh else "Substrate", "op01-", "*"))
            else:
                candidates.append(("底座" if zh else "Substrate", "op01-", "*"))
        stable_body_regions = isinstance(geometry, SphericalSolidGeometrySelection) or (
            isinstance(geometry, SurfaceSolidGeometrySelection)
            and getattr(getattr(operation, "solid_parameters", None), "surface_growth_strategy", "")
            == "root_edge_outward"
        )
        if stable_body_regions or all(body_id in actual_regions for _, body_id in features):
            candidates.extend(
                (f"{label} · {body_id}", "", body_id)
                for label, body_id in features
            )
            return tuple(candidates)
        if isinstance(geometry, RadialSolidGeometrySelection):
            offset = 2 if geometry.substrate_body is not None else 1
            candidates.extend(
                (f"{label} · {body_id}", f"op{index:02d}-" if len(features) > 1 or offset == 2 else "", "*")
                for index, (label, body_id) in enumerate(features, offset)
            )
            return tuple(candidates)
        # Thickness strips can have many stages per body; no single stage prefix
        # denotes a complete CAD body in that mode.
        return tuple(candidates) or (("全部沉积路径" if zh else "All deposition paths", "", "*"),)
    if toolpath is not None:
        stages: dict[str, None] = {}
        for point in toolpath.points:
            if point.point_type == "deposition":
                stages[point.stage_id] = None
            if len(stages) > 32:
                return (("全部沉积路径" if zh else "All deposition paths", "", "*"),)
        if stages:
            label = "已生成阶段" if zh else "Generated stage"
            return tuple((f"{label} · {stage}", stage, "*") for stage in stages)
    return (("全部沉积路径" if zh else "All deposition paths", "", "*"),)


class MaterialPlanEditor(QDialog):
    """Edit a plan without changing its public JSON or generation semantics."""

    def __init__(
        self, payload: dict | None = None, *, language: str = "zh",
        stage_candidates=(), parent=None,
    ):
        super().__init__(parent)
        self._original = deepcopy(payload) if payload is not None else {}
        self.result_payload: dict | None = None
        zh = language == "zh"
        self.setWindowTitle("材料通道与区域" if zh else "Material channels and regions")
        self.resize(850, 570)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("计划名称" if zh else "Plan name"))
        self.plan_id_edit = QLineEdit(str(self._original.get("plan_id", "material-plan")))
        layout.addWidget(self.plan_id_edit)
        layout.addWidget(QLabel(
            "通道参数为示例起点；温度、进退丝和排料长度须按设备调试。"
            if zh else "Channel values are starting examples; tune temperature, feed and purge for your equipment."
        ))
        self.channels_table = QTableWidget(0, 7)
        self.channels_table.setHorizontalHeaderLabels(
            ("通道", "材料", "温度 °C", "回抽 mm", "退丝 mm", "进丝 mm", "排料 mm")
            if zh else ("Channel", "Material", "Temp °C", "Retract mm", "Unload mm", "Load mm", "Purge mm")
        )
        self.channels_table.setMinimumHeight(155)
        layout.addWidget(self.channels_table)
        channel_buttons = QHBoxLayout()
        add_channel = QPushButton("添加通道" if zh else "Add channel")
        remove_channel = QPushButton("移除通道" if zh else "Remove channel")
        add_channel.clicked.connect(self.add_channel)
        remove_channel.clicked.connect(lambda: self._remove_selected(self.channels_table))
        channel_buttons.addWidget(add_channel)
        channel_buttons.addWidget(remove_channel)
        channel_buttons.addStretch()
        layout.addLayout(channel_buttons)
        hint = QLabel(
            "先应用几何与生长方式，再按沉积顺序选择区域；高级用户也可手填阶段前缀。"
            if zh else "Apply geometry and growth mode first, then select regions in deposition order. Stage prefixes remain editable."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.stage_combo = QComboBox()
        for label, stage_prefix, region_id in stage_candidates or (
            ("全部沉积路径" if zh else "All deposition paths", "", "*"),
        ):
            self.stage_combo.addItem(label, (stage_prefix, region_id))
        layout.addWidget(self.stage_combo)
        self.regions_table = QTableWidget(0, 3)
        self.regions_table.setHorizontalHeaderLabels(
            ("阶段前缀", "区域 ID", "通道") if zh else ("Stage prefix", "Region ID", "Channel")
        )
        self.regions_table.setMinimumHeight(150)
        layout.addWidget(self.regions_table)
        region_buttons = QHBoxLayout()
        add_suggested = QPushButton("添加所选区域" if zh else "Add selected region")
        add_suggested.clicked.connect(self.add_suggested_region)
        add_region = QPushButton("手动添加（高级）" if zh else "Add manually (advanced)")
        remove_region = QPushButton("移除区域" if zh else "Remove region")
        add_region.clicked.connect(self.add_region)
        remove_region.clicked.connect(lambda: self._remove_selected(self.regions_table))
        region_buttons.addWidget(add_suggested)
        region_buttons.addWidget(add_region)
        region_buttons.addWidget(remove_region)
        region_buttons.addStretch()
        layout.addLayout(region_buttons)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for channel in self._original.get("channels", ()):
            self._append_row(self.channels_table, (
                channel["channel_id"], channel["material_id"],
                channel["nozzle_temperature_c"], channel.get("retract_length_mm", 1),
                channel.get("unload_length_mm", 0), channel.get("load_length_mm", 0),
                channel.get("purge_length_mm", 0),
            ), source=channel)
        for region in self._original.get("regions", ()):
            self._append_row(self.regions_table, (
                region.get("stage_prefix", ""), region["region_id"], region["channel_id"]
            ))

    @staticmethod
    def _append_row(table: QTableWidget, values, *, source=None) -> None:
        row = table.rowCount()
        table.insertRow(row)
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            if column == 0 and source is not None:
                item.setData(Qt.ItemDataRole.UserRole, deepcopy(source))
            table.setItem(row, column, item)

    @staticmethod
    def _remove_selected(table: QTableWidget) -> None:
        row = table.currentRow()
        if row >= 0:
            table.removeRow(row)

    @staticmethod
    def _cell(table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return "" if item is None else item.text().strip()

    def add_channel(self) -> None:
        used = {self._cell(self.channels_table, row, 0)
                for row in range(self.channels_table.rowCount())}
        index = next(index for index in range(100) if f"T{index}" not in used)
        self._append_row(self.channels_table, (f"T{index}", "PLA", 195, 1, 0, 0, 0))

    def add_region(self) -> None:
        channel = self._cell(self.channels_table, 0, 0) if self.channels_table.rowCount() else "T0"
        self._append_row(self.regions_table, ("", "*", channel))

    def add_suggested_region(self) -> None:
        stage_prefix, region_id = self.stage_combo.currentData()
        for row in range(self.regions_table.rowCount()):
            if (self._cell(self.regions_table, row, 0), self._cell(self.regions_table, row, 1)) == (
                stage_prefix, region_id,
            ):
                self.regions_table.selectRow(row)
                return
        if not self.channels_table.rowCount():
            self.add_channel()
        channel = self._cell(self.channels_table, 0, 0)
        self._append_row(self.regions_table, (stage_prefix, region_id, channel))

    def build_payload(self) -> dict:
        payload = deepcopy(self._original)
        payload["schema_version"] = 1
        payload["plan_id"] = self.plan_id_edit.text().strip()
        channels = []
        for row in range(self.channels_table.rowCount()):
            first = self.channels_table.item(row, 0)
            original = first.data(Qt.ItemDataRole.UserRole) if first is not None else None
            channel = deepcopy(original) if isinstance(original, dict) else {}
            channel_id = self._cell(self.channels_table, row, 0)
            channel.update(
                channel_id=channel_id,
                material_id=self._cell(self.channels_table, row, 1),
                tool_command=(channel.get("tool_command") if channel_id == channel.get("channel_id")
                              else channel_id),
                nozzle_temperature_c=float(self._cell(self.channels_table, row, 2)),
                retract_length_mm=float(self._cell(self.channels_table, row, 3)),
                unload_length_mm=float(self._cell(self.channels_table, row, 4)),
                load_length_mm=float(self._cell(self.channels_table, row, 5)),
                purge_length_mm=float(self._cell(self.channels_table, row, 6)),
            )
            channels.append(channel)
        payload["channels"] = channels
        payload["regions"] = [
            {"stage_prefix": self._cell(self.regions_table, row, 0),
             "region_id": self._cell(self.regions_table, row, 1),
             "channel_id": self._cell(self.regions_table, row, 2)}
            for row in range(self.regions_table.rowCount())
        ]
        return MaterialPlan.from_json(payload).to_json()

    def _submit(self) -> None:
        try:
            self.result_payload = self.build_payload()
        except (TypeError, ValueError) as exc:
            self.error_label.setText(str(exc))
            return
        self.accept()
