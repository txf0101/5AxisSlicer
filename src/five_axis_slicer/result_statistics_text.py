"""Translate result statistics labels and current coordinate evidence."""

from .localization import tr
from .preview_coordinate_text import coordinate_text


def retranslate_statistics(self) -> None:
    self.coordinate_formula.setText(coordinate_text(self._preview, self.language))
    keys = {
        "bodies": "statistics_bodies",
        "edges": "statistics_edges",
        "base_layers": "statistics_base_layers",
        "blade_stages": "statistics_blade_stages",
        "spatial_segments": "statistics_spatial_segments",
        "extrusion_segments": "statistics_extrusion_segments",
        "travel_segments": "statistics_travel_segments",
        "layer_range": "statistics_layer_range",
        "a_range": "statistics_a_range",
        "c_range": "statistics_c_range",
    }
    for name, key in keys.items():
        self.statistic_labels[name].setText(tr(self.language, key))
    self.statistics_evidence.setText(tr(self.language, "statistics_actual_data"))
    self.continuity_label.setText(
        f"{tr(self.language, 'statistics_continuity_tolerance')}: 0.02 mm"
    )
