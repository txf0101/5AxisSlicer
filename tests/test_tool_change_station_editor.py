"""Station form uses the same machine-frame validation as NC generation."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from five_axis_slicer.manufacturing.controller_profile import ToolChangeStation  # noqa: E402
from five_axis_slicer.tool_change_station_editor import ToolChangeStationEditor  # noqa: E402


APP = QApplication.instance() or QApplication([])


def _station() -> dict:
    return ToolChangeStation(
        clearance_z_mm=180,
        cutter_xyz_mm=(130, 100, 80),
        exchange_xyz_mm=(140, 100, 80),
        purge_xyz_mm=(150, 100, 80),
        wipe_start_xyz_mm=(160, 100, 80),
        wipe_end_xyz_mm=(170, 100, 80),
    ).to_json()


def test_station_form_roundtrips_machine_frame_values() -> None:
    editor = ToolChangeStationEditor(_station(), language="en")
    editor.edits["wipe_passes"].setText("3")
    editor._submit()
    assert editor.result_payload is not None
    assert ToolChangeStation.from_json(editor.result_payload).wipe_passes == 3
    assert editor.edits["cutter_xyz_mm"].text() == "130.0, 100.0, 80.0"
    editor.close()


def test_station_form_rejects_incomplete_or_unsafe_coordinates() -> None:
    editor = ToolChangeStationEditor(_station())
    editor.edits["cutter_xyz_mm"].setText("130, 100")
    editor._submit()
    assert editor.result_payload is None
    assert "X、Y、Z" in editor.error_label.text()
    editor.edits["cutter_xyz_mm"].setText("130, 100, 185")
    editor._submit()
    assert editor.result_payload is None
    assert "安全退离 Z" in editor.error_label.text()
    editor.close()
