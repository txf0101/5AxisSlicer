"""Shared page routing kept outside the legacy main-window monolith."""

from __future__ import annotations

from typing import Any, cast

from . import curve_shell, freeform_shell, planar_shell, rotary_shell
from .localization import tr
from .workbenches import WORKBENCHES


_SHELLS = {
    "planar": planar_shell,
    "curve": curve_shell,
    "freeform": freeform_shell,
    "rotary": rotary_shell,
}


def _page(host: Any, key: str) -> Any | None:
    return getattr(host, f"{key}_page", None)


def enter_workbench(host: Any, key: str) -> None:
    commit_editor = getattr(host, "_commit_local_setup_editor", None)
    if callable(commit_editor) and not commit_editor():
        return
    if key not in {workbench.key for workbench in WORKBENCHES}:
        raise RuntimeError(f"Unknown workbench: {key}")
    shell = _SHELLS.get(key)
    page = _page(host, key)
    if shell is not None and page is None:
        raise RuntimeError(f"Workbench page is unavailable: {key}")
    page = cast(Any, page)
    common_setup = host.tube_page.controller.setup
    if (
        shell is not None
        and page.controller.setup.setup_id == common_setup.setup_id
        and shell.sync_shared_setup(page.controller, common_setup)
    ):
        page.refresh()
    refresh_panels = getattr(host, "_refresh_setup_panels", None)
    if callable(refresh_panels):
        refresh_panels()
    host.current_workbench_key = key
    if key == "tube":
        host.tube_page.set_common_setup_mode(False)
        host.current_operation = (
            host.tube_page.controller.operations[0].operation_type
            if host.tube_page.controller.operations
            else "tube_setup"
        )
    elif shell is not None:
        host.current_operation = shell.current_operation(page.controller)
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
        "freeform": host.freeform_page,
        "rotary": host.rotary_page,
    }
    page = pages.get(host.current_workbench_key)
    return host.viewer if page is None else page.viewer


def refresh_active_workbench(host: Any) -> None:
    pages = {
        "tube": host.tube_page,
        "planar": host.planar_page,
        "curve": host.curve_page,
        "freeform": host.freeform_page,
        "rotary": host.rotary_page,
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
        "freeform": host.freeform_page,
        "rotary": host.rotary_page,
    }
    host.stack.setCurrentWidget(pages.get(host.current_workbench_key, host.session_page))


def show_home(host: Any) -> None:
    commit_editor = getattr(host, "_commit_local_setup_editor", None)
    if callable(commit_editor) and not commit_editor():
        return
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
    if host.stack.currentWidget() is host.freeform_page:
        return "freeform"
    if host.stack.currentWidget() is host.rotary_page:
        return "rotary"
    return planar_shell.page_name(host)


def populate_operation_combo(host: Any, combo: Any, language: str) -> None:
    key = host.current_workbench_key
    if key == "tube":
        operations = host.tube_page.controller.operations
        if operations:
            combo.addItem(operations[0].name, operations[0].operation_type)
        else:
            combo.addItem("Tube Setup", "tube_setup")
        return
    shell = _SHELLS.get(key)
    if shell is not None:
        page = _page(host, key)
        if page is None:
            raise RuntimeError(f"Workbench page is unavailable: {key}")
        shell.populate_operation_combo(combo, page.controller)
        return
    combo.addItem(tr(language, "operation_imported_nc"), "imported_nc_review")
    combo.addItem(tr(language, "operation_curve"), "curve_buildup")
    combo.addItem(tr(language, "operation_freeform"), "freeform_coating")


def operation_label(host: Any, language: str) -> str:
    key = host.current_workbench_key
    if key == "tube":
        operations = host.tube_page.controller.operations
        return operations[0].name if operations else "Tube Setup"
    shell = _SHELLS.get(key)
    if shell is not None:
        page = _page(host, key)
        if page is None:
            raise RuntimeError(f"Workbench page is unavailable: {key}")
        return shell.operation_label(page.controller)
    if host.current_operation == "imported_nc_review":
        return tr(language, "operation_imported_nc")
    return host.current_operation


def active_viewer(host: Any) -> Any:
    pages = (
        host.result_page,
        host.tube_page,
        host.planar_page,
        host.curve_page,
        host.freeform_page,
        host.rotary_page,
    )
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
    "operation_label",
    "populate_operation_combo",
    "show_home",
    "show_after_model_import",
    "show_session",
]
