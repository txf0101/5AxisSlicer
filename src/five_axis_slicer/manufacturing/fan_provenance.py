"""Recorded-input checks for FAN contracts, independent of path qualification."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .resources import canonical_json_bytes

if TYPE_CHECKING:
    from .fan_job import FanManufacturingContract


def provenance_issues(contract: FanManufacturingContract) -> tuple[str, ...]:
    """Check every process value against its saved source without inventing sources."""
    issues = []
    for name, value in contract.parameters.to_json().items():
        source = contract.parameter_sources.get(name)
        if source is None:
            issues.append(f"{name}: missing source")
        elif source.source == "pending_measurement":
            issues.append(f"{name}: pending measurement")
        elif canonical_json_bytes(source.value) != canonical_json_bytes(value):
            issues.append(f"{name}: source value differs from parameter")
        elif not source.note.strip():
            issues.append(f"{name}: missing source reference")
    return tuple(issues)


def measurements_recorded(contract: FanManufacturingContract) -> bool:
    """Require recorded measurements as well as the legacy completion flag."""
    if not contract.machine_measurements_complete:
        return False
    for name in ("nozzle_envelope", "machine_zero", "controller_macro_version"):
        source = contract.parameter_sources.get(name)
        if source is None or source.source != "measured":
            return False
        if source.value is None or not source.note.strip():
            return False
    return True
