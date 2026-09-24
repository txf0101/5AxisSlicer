"""A consistent in-workbench entry to the active manufacturing Setup."""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QLabel,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .manufacturing.setup import ManufacturingSetup


_NODES = (
    ("part", "零件 / Part"),
    ("machine", "机床 / Machine"),
    ("nozzle", "喷嘴 / Nozzle"),
    ("material", "材料 / Material"),
    ("model_cs", "模型坐标 / Model CS"),
    ("build_cs", "构建坐标 / Build CS"),
    ("placement", "装夹 / Placement"),
)


def _resource_label(snapshot: object | None, missing: str) -> str:
    if snapshot is None:
        return missing
    payload = getattr(snapshot, "payload", {})
    name = (
        payload.get("display_name") or payload.get("name")
        if hasattr(payload, "get")
        else None
    )
    readable = str(name or getattr(snapshot, "resource_id", "")).split("\ufffd", 1)[0].strip()
    return readable or str(getattr(snapshot, "resource_id", missing))


class WorkbenchSetupPanel(QScrollArea):
    def __init__(
        self,
        key: str,
        *,
        edit_node: Callable[[str, str], None],
        copy_common: Callable[[str], None],
        use_common: Callable[[str], None],
        publish_common: Callable[[str], None],
        save_local: Callable[[], None],
    ) -> None:
        super().__init__()
        self.key = key
        self._edit_node = edit_node
        self.setObjectName(f"{key}SetupPanel")
        self.setMinimumWidth(230)
        self.setMaximumWidth(270)
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.title = QLabel()
        self.title.setObjectName("panelTitle")
        self.scope = QLabel()
        self.scope.setWordWrap(True)
        self.scope.setObjectName(f"{key}SetupScope")
        self.resources = QLabel()
        self.resources.setWordWrap(True)
        self.resources.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.nodes = QListWidget()
        self.nodes.setObjectName(f"{key}SetupNodes")
        self.nodes.setMinimumHeight(225)
        for node, label in _NODES:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, node)
            self.nodes.addItem(item)
        self.nodes.itemActivated.connect(self._open_node)
        self.nodes.itemClicked.connect(self._open_node)
        self.copy_button = QPushButton()
        self.copy_button.setObjectName(f"{key}CopyCommonSetup")
        self.copy_button.clicked.connect(lambda: copy_common(key))
        self.save_local_button = QPushButton()
        self.save_local_button.setObjectName(f"{key}SaveLocalSetup")
        self.save_local_button.clicked.connect(save_local)
        self.use_common_button = QPushButton()
        self.use_common_button.setObjectName(f"{key}UseCommonSetup")
        self.use_common_button.clicked.connect(lambda: use_common(key))
        self.publish_button = QPushButton()
        self.publish_button.setObjectName(f"{key}PublishCommonSetup")
        self.publish_button.clicked.connect(lambda: publish_common(key))
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setObjectName("mutedText")
        for widget in (
            self.title,
            self.scope,
            self.resources,
            self.nodes,
            self.copy_button,
            self.save_local_button,
            self.use_common_button,
            self.publish_button,
            self.note,
        ):
            layout.addWidget(widget)
        layout.addStretch(1)
        self.setWidget(content)
        self.set_language("zh")

    def _open_node(self, item: QListWidgetItem) -> None:
        self._edit_node(self.key, str(item.data(Qt.ItemDataRole.UserRole)))

    def set_language(self, language: str) -> None:
        zh = language != "en"
        self.title.setText("制造设置" if zh else "Manufacturing Setup")
        self.copy_button.setText("导入公共设置到本工作台" if zh else "Import common into this workbench")
        self.save_local_button.setText("保存本工作台设置…" if zh else "Save local Setup…")
        self.use_common_button.setText("改用公共设置" if zh else "Use common Setup")
        self.publish_button.setText("保存到公共制造设置" if zh else "Save to common Setup")
        self.note.setText(
            "点上方项目可编辑当前设置。保存项目会保留本工作台设置。"
            if zh else "Open a node to edit the active Setup. Save Project keeps local settings."
        )
        for index, (node, label) in enumerate(_NODES):
            item = self.nodes.item(index)
            if item is not None:
                item.setText(label if zh else label.split(" / ")[-1])

    def refresh_setup(self, setup: ManufacturingSetup, *, local: bool, language: str) -> None:
        self.set_language(language)
        self.scope.setText(
            ("本工作台独立设置" if local else "使用公共制造设置")
            if language != "en"
            else ("Local workbench Setup" if local else "Using common Setup")
        )
        missing = "未设置" if language != "en" else "Not set"
        self.resources.setText(
            "\n".join(
                f"{label}: {_resource_label(snapshot, missing)}"
                for label, snapshot in (
                    ("机床 / Machine" if language != "en" else "Machine", setup.machine),
                    ("喷嘴 / Nozzle" if language != "en" else "Nozzle", setup.nozzle),
                    ("材料 / Material" if language != "en" else "Material", setup.material),
                )
            )
        )
        self.copy_button.setEnabled(True)
        self.save_local_button.setEnabled(local)
        self.use_common_button.setEnabled(local)
        self.publish_button.setEnabled(local)
