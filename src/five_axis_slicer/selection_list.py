from __future__ import annotations

from collections.abc import Collection, Iterable

from PyQt5.QtCore import Qt, QSignalBlocker
from PyQt5.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem


ID_ROLE = Qt.UserRole
TEXT_ROLE = Qt.UserRole + 1
SelectionRow = tuple[str, str]


class SelectionList(QListWidget):
    """面向 body/edge 的多选列表。

    窗口层只需要读写对象 ID。Qt item 的自定义 role、勾选符号和信号屏蔽
    全部收在这里，避免主窗口同时处理界面布局和列表内部细节。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.MultiSelection)

    def set_rows(self, rows: Iterable[SelectionRow], selected_ids: Collection[str]) -> None:
        """重建列表，并按当前选择状态显示勾选符号。

        刷新列表常由模型加载、HTTP 写入或预览区点选触发。这里用
        QSignalBlocker 包住重建过程，防止程序同步状态时误触发用户选择回调。
        """

        selected = set(selected_ids)
        blocker = QSignalBlocker(self)
        try:
            self.clear()
            for obj_id, text in rows:
                self._add_item(obj_id, text, obj_id in selected)
        finally:
            del blocker

    def selected_ids(self) -> list[str]:
        ids: list[str] = []
        # Qt selectedItems() 的返回顺序可能跟点击顺序有关。按行扫描可让
        # HTTP 状态和 project.json 在同一选择集合下保持稳定输出。
        for row in range(self.count()):
            item = self.item(row)
            if not item.isSelected():
                continue
            obj_id = item.data(ID_ROLE)
            if obj_id is not None:
                ids.append(str(obj_id))
        return ids

    def sync_marks(self) -> None:
        """用户在列表中改选后，只刷新文本前缀，不重建整张列表。"""

        for row in range(self.count()):
            item = self.item(row)
            text = item.data(TEXT_ROLE)
            if text is not None:
                item.setText(self._text(str(text), item.isSelected()))

    def _add_item(self, obj_id: str, text: str, selected: bool) -> None:
        item = QListWidgetItem(self._text(text, selected))
        item.setData(ID_ROLE, obj_id)
        item.setData(TEXT_ROLE, text)
        self.addItem(item)
        item.setSelected(selected)

    @staticmethod
    def _text(text: str, selected: bool) -> str:
        return f"{'✓ ' if selected else ''}{text}"
