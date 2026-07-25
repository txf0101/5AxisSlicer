from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from five_axis_slicer.manufacturing.resources import (  # noqa: E402
    GENERIC_NOZZLE_0_4,
)
from five_axis_slicer.tube_resource_selection import (  # noqa: E402
    configured_nozzle_copy,
)


def measured_nozzle_fields() -> dict[str, object]:
    return {
        "interface": "M6",
        "length_mm": 12.5,
        "construction_material": "brass",
        "flow_category": "standard",
        "temperature_limit_c": 300.0,
        "wear_resistance_rating": "standard",
        "outer_profile_rz_mm": ((0.2, 0.0), (3.0, 2.0), (3.0, 12.5)),
    }


def test_complete_nozzle_requires_explicit_physical_fields() -> None:
    with pytest.raises(ValueError, match="outer_profile_rz_mm"):
        configured_nozzle_copy(
            GENERIC_NOZZLE_0_4,
            {
                key: value
                for key, value in measured_nozzle_fields().items()
                if key != "outer_profile_rz_mm"
            },
        )


def test_measured_nozzle_copy_is_ready_without_mutating_template() -> None:
    profile = configured_nozzle_copy(GENERIC_NOZZLE_0_4, measured_nozzle_fields())

    assert profile.is_ready
    assert profile.outer_profile_rz_mm[-1] == (3.0, 12.5)
    assert not profile.is_builtin
    assert not GENERIC_NOZZLE_0_4.is_ready
    assert GENERIC_NOZZLE_0_4.outer_profile_rz_mm == ()
