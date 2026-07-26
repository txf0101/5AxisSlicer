"""Bilingual text binding for the result preview page."""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import QSignalBlocker

from .localization import tr

_SOURCE_TEXT = (
    ("title_label", "result_preview_title"),
    ("subtitle_label", "result_preview_subtitle"),
    ("back_button", "result_back_to_workbench"),
    ("sources_heading", "result_column_sources"),
    ("viewer_heading", "result_column_viewer"),
    ("analysis_heading", "result_column_analysis"),
    ("source_card_title", "result_current_source"),
    ("model_source_title", "result_model_source"),
    ("gcode_source_title", "result_gcode_source"),
    ("demo_button", "result_load_impeller_demo"),
    ("open_gcode_button", "result_open_existing_gcode"),
    ("open_step_button", "result_open_step"),
    ("slice_button", "result_slice_and_preview"),
    ("parameters_title", "process_parameters"),
    ("shell_checkbox", "parameter_process_mode_shell"),
    ("edit_parameters_button", "parameter_edit"),
    ("save_parameters_button", "parameter_save"),
    ("reset_parameters_button", "parameter_reset"),
)

_PARAMETER_TEXT = (
    ("layer_height", "parameter_layer_height"),
    ("print_speed", "parameter_print_speed"),
    ("extrusion_width", "parameter_extrusion_width"),
    ("nozzle_diameter", "parameter_nozzle_diameter"),
    ("process_mode", "parameter_process_mode"),
    ("top_bottom", "parameter_top_bottom_layers"),
)

_ANALYSIS_TEXT = (
    ("status_card_title", "result_state"),
    ("statistics_title", "result_summary"),
    ("thumbnail_title", "result_thumbnail"),
    ("thumbnail_note", "result_thumbnail_fixed_camera"),
    ("context_title", "gcode_context"),
    ("jump_button", "gcode_jump_go"),
)

_TOOLTIPS = (
    ("demo_button", "tooltip_load_demo"),
    ("open_gcode_button", "tooltip_open_gcode"),
    ("open_step_button", "tooltip_open_step"),
    ("slice_button", "tooltip_slice_preview"),
    ("cancel_button", "tooltip_cancel_loading"),
    ("edit_parameters_button", "tooltip_parameter_edit"),
    ("save_parameters_button", "tooltip_parameter_save"),
    ("reset_parameters_button", "tooltip_parameter_reset"),
    ("search_edit", "tooltip_gcode_search"),
    ("jump_edit", "tooltip_gcode_jump"),
    ("stage_combo", "tooltip_stage_navigation"),
    ("previous_stage_button", "result_progress_previous"),
    ("next_stage_button", "result_progress_next"),
    ("progress_slider", "tooltip_progress"),
    ("quality_combo", "tooltip_quality_mode"),
)


def retranslate_result_preview(page: Any, language: str) -> None:
    page.language = language if language in {"zh", "en"} else "zh"
    _set_text(page, _SOURCE_TEXT)
    _set_parameter_text(page)
    _set_viewer_text(page)
    _set_text(page, _ANALYSIS_TEXT)
    _set_analysis_inputs(page)
    _set_tooltips(page)
    _refresh_translated_state(page)


def _set_text(page: Any, bindings: tuple[tuple[str, str], ...]) -> None:
    for attribute, key in bindings:
        getattr(page, attribute).setText(tr(page.language, key))


def _set_parameter_text(page: Any) -> None:
    for name, key in _PARAMETER_TEXT:
        page.parameter_labels[name].setText(tr(page.language, key))
    page.parameter_feedback.setText("")


def _set_viewer_text(page: Any) -> None:
    canvas = page.viewer_canvas
    canvas.fit_button.setToolTip(tr(page.language, "tooltip_fit_view"))
    canvas.home_button.setToolTip(tr(page.language, "tooltip_home_view"))
    canvas.orientation_cube.setToolTip(tr(page.language, "tooltip_orientation_cube"))
    canvas.axis_triad.setToolTip(tr(page.language, "view_part_axes"))
    canvas.legend.set_texts(tr(page.language, "legend_start"), tr(page.language, "legend_end"))

    _set_text(
        page,
        (
            ("stage_title", "stage_navigation"),
            ("stage_fallback_label", "stage_marker_fallback"),
            ("progress_title", "result_progress"),
            ("quality_title", "quality_mode"),
            ("visibility_title", "visibility_title"),
        ),
    )
    page.quality_combo.setItemText(0, tr(page.language, "quality_interactive"))
    page.quality_combo.setItemText(1, tr(page.language, "quality_paper"))
    visibility_keys = (
        "visibility_model",
        "visibility_extrusion",
        "visibility_travel",
        "visibility_pose",
        "visibility_start_end",
        "visibility_part_axes",
        "visibility_orientation_cube",
    )
    for checkbox, key in zip(page.visibility_checks, visibility_keys, strict=True):
        checkbox.setText(tr(page.language, key))


def _set_analysis_inputs(page: Any) -> None:
    page.search_edit.setPlaceholderText(tr(page.language, "gcode_search_placeholder"))
    page.search_previous_button.setToolTip(tr(page.language, "gcode_search_previous"))
    page.search_next_button.setToolTip(tr(page.language, "gcode_search_next"))
    page.jump_edit.setPlaceholderText(tr(page.language, "gcode_jump_placeholder"))


def _set_tooltips(page: Any) -> None:
    for attribute, key in _TOOLTIPS:
        getattr(page, attribute).setToolTip(tr(page.language, key))


def _refresh_translated_state(page: Any) -> None:
    page._retranslate_statistics()
    if page.stage_combo.count():
        with QSignalBlocker(page.stage_combo):
            for index in range(page.stage_combo.count()):
                entry = page.stage_combo.itemData(index)
                if isinstance(entry, dict):
                    page.stage_combo.setItemText(index, page._stage_text(entry))
    else:
        page._rebuild_stage_combo(preserve_id=page.state.selected_stage)
    for refresh in (
        page._update_sources,
        page._update_status,
        page._update_statistics,
        page._update_context_labels,
        page._update_thumbnail_label,
        page._refresh_wrapped_text_geometry,
    ):
        refresh()
