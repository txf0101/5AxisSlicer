"""Shared page routing kept outside the legacy main-window monolith."""

from __future__ import annotations

from typing import Any

from . import curve_shell, planar_shell
from .workbenches import WORKBENCHES


def enter_workbench(host: Any, key: str) -> None:
    if key not in {workbench.key for workbench in WORKBENCHES}:
        raise RuntimeError(f"Unknown workbench: {key}")
    if key == "planar" and planar_shell.sync_shared_setup(
        host.planar_page.controller, host.tube_page.controller.setup
    ):
        host.planar_page.refresh()
    if key == "curve" and curve_shell.sync_shared_setup(
        host.curve_page.controller, host.tube_page.controller.setup
    ):
        host.curve_page.refresh()
    host.current_workbench_key = key
    if key == "tube":
        host.current_operation = (
            host.tube_page.controller.operations[0].operation_type
            if host.tube_page.controller.operations
            else "tube_setup"
        )
    elif key == "planar":
        host.current_operation = planar_shell.current_operation(host.planar_page.controller)
    elif key == "curve":
        host.current_operation = curve_shell.current_operation(host.curve_page.controller)
    else:
        host.current_operation = "imported_nc_review"
    host._update_operation_combo()
    host._show_session()
    if key == "tube":
        host.tube_page.activate_coordinate_entry()
    host._update_workbench_texts()
    host._update_checks()


def active_workbench_viewer(host: Any) -> Any:
    pages = {
        "tube": host.tube_page,
        "planar": host.planar_page,
        "curve": host.curve_page,
    }
    page = pages.get(host.current_workbench_key)
    return host.viewer if page is None else page.viewer


def refresh_active_workbench(host: Any) -> None:
    pages = {
        "tube": host.tube_page,
        "planar": host.planar_page,
        "curve": host.curve_page,
    }
    page = pages.get(host.current_workbench_key)
    if page is None:
        host.refresh_lists()
    else:
        page.refresh()


def show_session(host: Any) -> None:
    pages = {
        "tube": host.tube_page,
        "planar": host.planar_page,
        "curve": host.curve_page,
    }
    host.stack.setCurrentWidget(pages.get(host.current_workbench_key, host.session_page))


def show_home(host: Any) -> None:
    host.stack.setCurrentWidget(host.home_page)


def show_after_model_import(host: Any, started_from_home: bool) -> None:
    if started_from_home:
        host.stack.setCurrentWidget(host.session_page)
    else:
        show_session(host)


def open_gcode_from_shell(host: Any) -> None:
    if host.stack.currentWidget() is host.session_page:
        host.open_gcode_dialog()
    else:
        host.open_result_gcode_dialog()


def current_page_name(host: Any) -> str:
    if host.stack.currentWidget() is host.curve_page:
        return "curve"
    return planar_shell.page_name(host)


def active_viewer(host: Any) -> Any:
    pages = (host.result_page, host.tube_page, host.planar_page, host.curve_page)
    current = host.stack.currentWidget()
    for page in pages:
        if current is page:
            return page.viewer
    return host.viewer


__all__ = [
    "active_viewer",
    "active_workbench_viewer",
    "current_page_name",
    "enter_workbench",
    "refresh_active_workbench",
    "open_gcode_from_shell",
    "show_home",
    "show_after_model_import",
    "show_session",
]
