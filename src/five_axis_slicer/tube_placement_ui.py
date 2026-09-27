"""Explicit Placement draft actions for the shared manufacturing settings page."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QPushButton

from .tube_controller import DraftNotFoundError

if TYPE_CHECKING:
    from .tube_ui import TubeSetupPage


def create_reset_button(page: TubeSetupPage) -> QPushButton:
    button = QPushButton()
    button.clicked.connect(lambda: reset_to_mount(page))
    return button


def reset_to_mount(page: TubeSetupPage) -> None:
    """Discard both the hidden reference offset and the local draft adjustment."""
    mount_id = page.mount_combo.currentData()
    if mount_id is None:
        return
    try:
        try:
            page.controller.placement_draft()
        except DraftNotFoundError:
            page.controller.begin_placement_draft(mount_datum_id=str(mount_id))
        page.controller.set_placement_mount(str(mount_id))
        page.controller.set_placement_adjustment((0.0, 0.0, 0.0))
        page._begin_placement_editor()
        page.placement_feedback.setText(page._t("placement_reset_pending"))
    except Exception as exc:
        page._report_error(exc, page.placement_feedback)
