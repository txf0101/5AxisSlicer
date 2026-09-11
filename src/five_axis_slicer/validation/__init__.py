"""Inspectable validation reports for generated manufacturing results."""

from .indexed_tube import (
    CollisionBox,
    IndexedValidationReport,
    ValidationMetric,
    validate_indexed_tube,
)

__all__ = [
    "CollisionBox",
    "IndexedValidationReport",
    "ValidationMetric",
    "validate_indexed_tube",
]
