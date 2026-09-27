"""Persist the actual bounded strategy independently of legacy plan summaries."""
from dataclasses import asdict
from ..algorithms.tube.bounded_indexed import BoundedIndexedSlicePlan


def bounded_plan_metadata(plan):
    if not isinstance(plan, BoundedIndexedSlicePlan):
        return {}
    return {'generation_strategy': plan.generation_strategy,
            'residual_task_count': plan.residual_task_count,
            'maximum_track_width_mm': plan.maximum_track_width_mm,
            'nominal_layer_height_mm': plan.nominal_layer_height_mm,
            'band_records': [asdict(band) for band in plan.band_records],
            'layer_bands': [{'layer_id': layer_id, 'band': asdict(band)} for layer_id, band in plan.layer_bands],
            'finite_width_accuracy_deferred': True, 'machine_executable': False}
