from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt5.QtWidgets import QApplication

from five_axis_slicer.selection_list import SelectionList


class SelectionListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_rebuilds_rows_and_reads_selected_ids(self) -> None:
        widget = SelectionList()
        widget.set_rows(
            [("body_001", "body_001  Solid 1"), ("body_002", "body_002  Solid 2")], {"body_002"}
        )

        self.assertEqual(widget.count(), 2)
        self.assertEqual(widget.selected_ids(), ["body_002"])
        self.assertEqual(widget.item(1).text(), "✓ body_002  Solid 2")

        widget.item(0).setSelected(True)
        widget.sync_marks()

        self.assertEqual(widget.selected_ids(), ["body_001", "body_002"])
        self.assertEqual(widget.item(0).text(), "✓ body_001  Solid 1")


if __name__ == "__main__":
    unittest.main()
