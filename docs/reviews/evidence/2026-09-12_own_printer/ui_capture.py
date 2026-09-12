import json
import os
from pathlib import Path
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "windows"
sys.path.insert(0, str(Path("src").resolve()))

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QWidget

from five_axis_slicer.machine_profile_ui import save_copy
from five_axis_slicer.manufacturing.library import UserResourceLibrary
from five_axis_slicer.manufacturing.own_printer import own_ac_profile
from five_axis_slicer.tube_ui import TubeSetupPage

app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 10))
out = Path("docs/guides/assets/machine_profiles")
records = []
with tempfile.TemporaryDirectory(dir="tmp") as tmp:
    page = TubeSetupPage(
        viewer_factory=QWidget,
        resource_library=UserResourceLibrary(tmp),
    )
    page.setAttribute(Qt.WA_DontShowOnScreen, True)
    page.tree.setCurrentItem(page._tree_items["machine"])
    for language, width, height in [
        ("zh", 1366, 768),
        ("zh", 1600, 900),
        ("en", 1920, 1080),
    ]:
        page.set_language(language)
        page.resize(width, height)
        page.show()
        app.processEvents()
        filename = f"{language}_{width}x{height}.png"
        page.grab().save(str(out / filename))
        records.append(
            {
                "file": filename,
                "size": [page.width(), page.height()],
                "buttons_visible": [
                    button.isVisible() for button in page.machine_file_buttons
                ],
            }
        )
    copy = save_copy(page, own_ac_profile(), "实验室 AC 自定义")
    page._apply_machine()
    app.processEvents()
    page.set_language("zh")
    page.resize(1600, 900)
    app.processEvents()
    page.grab().save(str(out / "custom_selected.png"))
    assert page.controller.machine_profile() == copy
    page.close()
(out / "summary.json").write_text(
    json.dumps(records, indent=2), encoding="utf-8"
)
print(records)
