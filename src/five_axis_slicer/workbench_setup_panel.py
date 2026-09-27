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
    QMessageBox,
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


def confirm_setup_change(parent: QWidget, language: str, message: str) -> bool:
    """Use the application's language without depending on Qt translation bundles."""
    prompt = QMessageBox(parent)
    prompt.setIcon(QMessageBox.Question)
    prompt.setWindowTitle("制造设置" if language == "zh" else "Manufacturing Setup")
    prompt.setText(message)
    prompt.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    for role, label in (
        (QMessageBox.Yes, "是" if language == "zh" else "Yes"),
        (QMessageBox.No, "否" if language == "zh" else "No"),
    ):
        button = prompt.button(role)
        if button is not None:
            button.setText(label)
    prompt.setDefaultButton(QMessageBox.No)
    prompt.setEscapeButton(QMessageBox.No)
    return prompt.exec_() == QMessageBox.Yes


def draft_setup_prompt(parent: QWidget, language: str, *, saving: bool = False) -> QMessageBox:
    """Keep standard result codes while displaying the selected application language."""
    prompt = QMessageBox(parent)
    prompt.setWindowTitle("制造设置" if language == "zh" else "Manufacturing Setup")
    messages = {
        (True, "zh"): "制造设置含未应用草稿，请选择应用、丢弃或取消保存。",
        (True, "en"): "Manufacturing Setup has unapplied drafts. Apply, discard, or cancel saving.",
        (False, "zh"): "本工作台设置有未应用草稿。应用、丢弃，还是继续编辑？",
        (False, "en"): "Local Setup has unapplied drafts. Apply, discard, or continue editing?",
    }
    prompt.setText(messages[saving, language])
    prompt.setStandardButtons(QMessageBox.Apply | QMessageBox.Discard | QMessageBox.Cancel)
    labels = ("应用", "丢弃", "取消") if language == "zh" else ("Apply", "Discard", "Cancel")
    for role, label in zip((QMessageBox.Apply, QMessageBox.Discard, QMessageBox.Cancel), labels):
        button = prompt.button(role)
        if button is not None:
            button.setText(label)
    prompt.setDefaultButton(QMessageBox.Cancel)
    prompt.setEscapeButton(QMessageBox.Cancel)
    return prompt


def _resource_label(snapshot: object | None, missing: str) -> str:
    if snapshot is None:
        return missing
    payload = getattr(snapshot, "payload", {})
    name = payload.get("display_name") or payload.get("name") if hasattr(payload, "get") else None
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
        self.copy_button.setText("导入公共设置" if zh else "Copy common Setup")
        self.copy_button.setToolTip(
            "从公共设置创建本工作台的独立副本。"
            if zh
            else "Create an independent Setup for this workbench from the common Setup."
        )
        self.save_local_button.setText("保存本工作台设置…" if zh else "Save local Setup…")
        self.use_common_button.setText("改用公共设置" if zh else "Use common Setup")
        self.publish_button.setText("保存到公共制造设置" if zh else "Save to common Setup")
        self.note.setText(
            "点上方项目可编辑当前设置。保存项目会保留本工作台设置。"
            if zh
            else "Open a node to edit the active Setup. Save Project keeps local settings."
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
