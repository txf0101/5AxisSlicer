"""Restricted guide-driven Freeform surface path generation."""

from .core import FreeformGeometryError, FreeformPath, FreeformPlan, build_freeform_plan
from .toolpath import generate_freeform_toolpath
from .layer_domain import (
    BladeLayerDomainAudit,
    audit_blade_layer_domain,
    fixed_a_model_from_build,
)

__all__ = [
    "FreeformGeometryError",
    "FreeformPath",
    "FreeformPlan",
    "build_freeform_plan",
    "generate_freeform_toolpath",
    "BladeLayerDomainAudit",
    "audit_blade_layer_domain",
    "fixed_a_model_from_build",
]
